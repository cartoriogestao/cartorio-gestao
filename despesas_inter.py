"""O BANCO INTER — quem paga a despesa autorizada, e o extrato que prova o pagamento.

POR QUE O INTER, E DIRETO (24/10/2026)
    O oficial primeiro pediu a Pluggy e, no mesmo dia, trocou pela API do
    Banco Inter, que é o banco da conta da serventia. A Pluggy não serviria de
    qualquer modo: o pagamento dela que dispensa a pessoa (Smart Transfers)
    só transfere entre contas do mesmo CPF/CNPJ.

O CONTRATO (API Banking v2 do Inter, especificação OpenAPI servida em
developers.inter.co, lida em 24/10/2026)
    - Token: POST /oauth/v2/token, client_credentials, com o certificado do
      Inter na conexão (mTLS). Vale 1 hora, e o Inter aceita 5 pedidos de
      token por minuto — por isso ele se guarda e se reaproveita.
    - Boleto e conta/guia/tributo com código de barras: POST /banking/v2/
      pagamento {codBarraLinhaDigitavel, valorPagar, dataVencimento,
      dataPagamento?, cpfCnpjBeneficiario?} → {statusPagamento,
      codigoTransacao}. Consulta: GET /banking/v2/pagamento.
    - Pix: POST /banking/v2/pix, com o cabeçalho `x-id-idempotente`, destino
      por CHAVE ou PIX_COPIA_E_COLA → {tipoRetorno, codigoSolicitacao}.
      Consulta: GET /banking/v2/pix/{codigoSolicitacao}.
    - Extrato: GET /banking/v2/extrato/completo (até 90 dias, paginado), com
      o detalhe de cada débito — código de barras, codigoSolicitacao e
      endToEnd do Pix. É por ele que a casa CONFERE o pagamento.

    **O PAGAMENTO PODE FICAR ESPERANDO APROVAÇÃO NO BANCO.** A especificação
    avisa que, «dependendo das configurações da conta», o pagamento feito pela
    API «pode exigir aprovação manual» (Internet Banking → Aprovar → Gestão de
    Aprovações). O oficial diz que na conta da serventia sai sozinho; o
    sistema trata os dois casos — AGUARDANDO_APROVACAO é situação de banco, a
    despesa fica ENVIADA e o extrato decide.

O QUE ESTE MÓDULO NUNCA FAZ
    Não autoriza: só paga despesa AUTORIZADA (`despesas`). Não segura
    transação do banco de dados durante a rede: marca ENVIADA antes, fala com
    o Inter, e grava a resposta depois — se a resposta se perder, a
    `atualizar` pergunta ao banco antes de mandar de novo, e o Pix reenvia
    com a MESMA chave de idempotência. Não lança no Livro Diário o que o
    extrato não mostrou.

A CREDENCIAL
    Client ID, Client Secret, o certificado (.crt) e a chave (.key) que o
    Inter entrega na integração. Moram FORA do banco: no cofre da automação
    (`automacao_cofre`, item «banco_inter»), quando ele existe; até lá, num
    arquivo da pasta de dados, só do serviço, como o A1 da NFS-e. O cofre
    trancado (ninguém digitou a senha-mestra depois de a máquina reiniciar)
    não é erro do banco: o pagamento espera, e a despesa não muda.
"""
from __future__ import annotations

import json
import re
import ssl
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import despesas as DP
from bd_nativo import banco
from caixa_schema import reais

ENDERECOS = {
    "producao": "https://cdpj.partners.bancointer.com.br",
    "sandbox": "https://cdpj-sandbox.partners.uatinter.co",
}
ESCOPOS = "extrato.read pagamento-boleto.write pagamento-boleto.read pagamento-pix.write pagamento-pix.read"
NOME_NO_COFRE = "banco_inter"
ARQUIVO_DA_CREDENCIAL = "banco_inter.json"
CAMPOS_DA_CREDENCIAL = ("client_id", "client_secret", "crt_pem", "key_pem")
PRAZO_SEGUNDOS = 30
DIAS_DE_EXTRATO = 10

# O status do Inter → a situação da despesa. O que não está nas listas fica
# ENVIADA: situação de banco desconhecida não vira «pago» nem «falhou».
BOLETO_PAGO = {"REALIZADO"}
BOLETO_FALHOU = {"CANCELADO", "AGENDADO_CANCELADO", "ERRO", "REPROVADO",
                 "APROVACAO_EXPIRADA", "NAO_COMPENSADO"}
PIX_PAGO = {"PAGO", "DEBITADO", "EFETIVADO"}
PIX_FALHOU = {"REPROVADO", "EXPIRADO", "CANCELADO", "CANCELADO_SEM_SALDO", "FALHA",
              "AGENDAMENTO_CANCELADO", "ERRO", "APROVACAO_EXPIRADA"}
_NS_IDEMPOTENCIA = uuid.UUID("3f6f2f4e-6a51-4a7e-9a46-6b1b2f0d7c11")


class InterError(RuntimeError):
    """Falha ao falar com o Inter, com a frase curta para a tela e o rastro."""


class Recusa(InterError):
    """O Inter respondeu «não» (4xx): mandar igual não adianta."""


class Indisponivel(InterError):
    """Rede, prazo ou servidor fora: tentar de novo é seguro."""


class CredencialAusente(InterError):
    """A credencial do Inter não foi cadastrada."""


class CredencialTrancada(InterError):
    """O cofre está trancado: o pagamento espera, a despesa não muda."""
    cofre_trancado = True


@dataclass
class Resposta:
    status: int
    corpo: Any = None
    tipo: str = ""


Transporte = Callable[..., Resposta]


# --------------------------------------------------------------- a credencial

def _pasta(pasta: Any = None) -> Path:
    if pasta:
        return Path(pasta)
    import centrais_cred
    return centrais_cred.pasta_de_dados()


def _cofre():
    try:
        import automacao_cofre  # type: ignore
    except ImportError:
        return None
    return automacao_cofre


def credencial(pasta: Any = None) -> dict:
    """A credencial do Inter. Cofre primeiro; o arquivo é o caminho provisório."""
    cofre = _cofre()
    if cofre is not None:
        try:
            campos = cofre.ler(NOME_NO_COFRE)
        except Exception as erro:  # noqa: BLE001 — a classe é do outro módulo
            if getattr(erro, "cofre_trancado", False) or "Trancad" in type(erro).__name__:
                raise CredencialTrancada("O cofre está trancado: o oficial precisa "
                                         "desbloqueá-lo para o pagamento sair.") from erro
            campos = None
        if campos:
            return dict(campos)
    arquivo = _pasta(pasta) / ARQUIVO_DA_CREDENCIAL
    if not arquivo.is_file():
        raise CredencialAusente("A credencial do Banco Inter não foi cadastrada "
                                "(Despesas → Configuração).")
    try:
        return json.loads(arquivo.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as erro:
        raise CredencialAusente("O arquivo da credencial do Inter está ilegível. "
                                "Cadastre-a de novo.") from erro


def conferir_credencial(campos: dict) -> dict:
    """Confere que o .crt e o .key se abrem e são um par. Só calcula. Sem segredo na frase."""
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    faltam = [c for c in CAMPOS_DA_CREDENCIAL if not str(campos.get(c) or "").strip()]
    if faltam:
        raise DP.DespesaError("Faltam na credencial do Inter: " + ", ".join(faltam) + ".")
    try:
        cert = x509.load_pem_x509_certificate(campos["crt_pem"].encode("utf-8"))
        chave = serialization.load_pem_private_key(campos["key_pem"].encode("utf-8"), None)
    except (ValueError, TypeError) as erro:
        raise DP.DespesaError("O certificado (.crt) ou a chave (.key) do Inter não se abrem: "
                              "use os arquivos que o Internet Banking entregou.") from erro
    pub = serialization.PublicFormat.SubjectPublicKeyInfo
    enc = serialization.Encoding.PEM
    if cert.public_key().public_bytes(enc, pub) != chave.public_key().public_bytes(enc, pub):
        raise DP.DespesaError("O .crt e o .key do Inter não são um par.")
    return {"valido_ate": cert.not_valid_after_utc.date().isoformat(),
            "titular": cert.subject.rfc4514_string()[:120]}


def gravar_credencial(campos: dict, pasta: Any = None) -> dict:
    """Grava no cofre, se existir; senão, no arquivo só do serviço. ESCREVE EM DISCO."""
    resumo = conferir_credencial(campos)
    limpos = {c: str(campos.get(c) or "").strip() for c in (*CAMPOS_DA_CREDENCIAL,
                                                            "conta_corrente")}
    cofre = _cofre()
    if cofre is not None:
        cofre.gravar(NOME_NO_COFRE, {k: v for k, v in limpos.items() if v},
                     tipo="CERTIFICADO", validade=resumo["valido_ate"], por="despesas")
        return {**resumo, "onde": "cofre"}
    destino = _pasta(pasta)
    destino.mkdir(parents=True, exist_ok=True)
    alvo = destino / ARQUIVO_DA_CREDENCIAL
    provisorio = alvo.with_suffix(".novo")
    provisorio.write_text(json.dumps(limpos), encoding="utf-8")
    import os
    os.replace(provisorio, alvo)
    try:
        import centrais_cred
        centrais_cred._so_do_servico(alvo)
    except (ImportError, AttributeError, OSError):
        pass
    return {**resumo, "onde": "arquivo"}


def resumo_da_credencial(pasta: Any = None) -> dict | None:
    """Para a tela: validade e onde mora. Sem nenhum segredo.

    Com o cofre instalado, lê só os METADADOS: o cofre recusa entregar o
    segredo dentro de uma requisição web, e a validade está nos metadados.
    """
    cofre = _cofre()
    if cofre is not None:
        try:
            meta = cofre.metadados(NOME_NO_COFRE)
        except Exception as erro:  # noqa: BLE001 — a classe é do outro módulo
            if type(erro).__name__ == "ItemInexistente":
                return None
            return {"erro": str(erro)}
        return {"valido_ate": str(meta.get("validade") or "")[:10], "onde": "cofre"}
    try:
        campos = credencial(pasta)
    except CredencialTrancada as erro:
        return {"erro": str(erro)}
    except CredencialAusente:
        return None
    try:
        return conferir_credencial(campos)
    except DP.DespesaError as erro:
        return {"erro": str(erro)}


# ---------------------------------------------------------------- o transporte

def transporte_https(campos: dict, prazo: int = PRAZO_SEGUNDOS) -> Transporte:
    """HTTPS com o certificado do Inter na conexão. Abre rede: não roda em teste."""
    contexto = ssl.create_default_context()
    with tempfile.TemporaryDirectory(prefix="cg_inter_") as pasta:
        crt, key = Path(pasta) / "c.pem", Path(pasta) / "k.pem"
        crt.write_text(campos["crt_pem"], encoding="utf-8")
        key.write_text(campos["key_pem"], encoding="utf-8")
        contexto.load_cert_chain(str(crt), str(key))

    def chamar(metodo: str, url: str, *, json_corpo: Any = None, form: dict | None = None,
               cabecalhos: dict | None = None) -> Resposta:
        cab = dict(cabecalhos or {})
        dados = None
        if form is not None:
            dados = urllib.parse.urlencode(form).encode("utf-8")
            cab["Content-Type"] = "application/x-www-form-urlencoded"
        elif json_corpo is not None:
            dados = json.dumps(json_corpo).encode("utf-8")
            cab["Content-Type"] = "application/json"
        pedido = urllib.request.Request(url, data=dados, method=metodo, headers=cab)
        try:
            with urllib.request.urlopen(pedido, timeout=prazo, context=contexto) as r:
                status, tipo, bruto = r.status, r.headers.get("Content-Type", ""), r.read()
        except urllib.error.HTTPError as erro:
            status, tipo, bruto = erro.code, erro.headers.get("Content-Type", ""), erro.read()
        if re.search(r"json", tipo or "", re.I):
            try:
                return Resposta(status, json.loads(bruto.decode("utf-8") or "{}"), tipo)
            except ValueError:
                return Resposta(status, {}, tipo)
        return Resposta(status, bruto, tipo)

    return chamar


# ------------------------------------------------------------------ o cliente

def _frase(corpo: Any) -> str:
    if isinstance(corpo, dict):
        partes = [str(corpo.get(k) or "") for k in ("title", "detail")]
        return " — ".join(p for p in partes if p)[:300]
    return ""


class ClienteInter:
    """O Banking v2 do Inter, por um transporte injetável."""

    def __init__(self, ambiente: str, transporte: Transporte, campos: dict):
        if ambiente not in ENDERECOS:
            raise InterError(f"Ambiente desconhecido: «{ambiente}».")
        self.ambiente = ambiente
        self.base = ENDERECOS[ambiente]
        self._transporte = transporte
        self._campos = campos
        self._token = ""
        self._vence = 0.0

    def _cab(self) -> dict:
        cab = {"Authorization": f"Bearer {self.token()}"}
        if self._campos.get("conta_corrente"):
            cab["x-conta-corrente"] = str(self._campos["conta_corrente"])
        return cab

    def _ir(self, metodo: str, url: str, **kw) -> Resposta:
        try:
            r = self._transporte(metodo, url, **kw)
        except InterError:
            raise
        except (OSError, TimeoutError, ValueError) as erro:
            raise Indisponivel(f"Sem resposta do Inter ({type(erro).__name__}).") from erro
        if r.status >= 500 or r.status in (408, 429):
            raise Indisponivel(f"O Inter respondeu HTTP {r.status}; tento de novo depois.")
        return r

    def token(self) -> str:
        if self._token and time.monotonic() < self._vence:
            return self._token
        r = self._ir("POST", f"{self.base}/oauth/v2/token", form={
            "client_id": self._campos["client_id"],
            "client_secret": self._campos["client_secret"],
            "grant_type": "client_credentials", "scope": ESCOPOS})
        if r.status != 200 or not isinstance(r.corpo, dict) or not r.corpo.get("access_token"):
            raise Recusa(f"O Inter recusou a credencial (HTTP {r.status}). Confira o Client "
                         f"ID, o Client Secret e os escopos da integração.")
        self._token = str(r.corpo["access_token"])
        self._vence = time.monotonic() + max(60, int(r.corpo.get("expires_in") or 3600) - 120)
        return self._token

    def pagar_codigo(self, codigo: str, valor_centavos: int, vencimento: str,
                     data_pagamento: str, documento: str = "") -> dict:
        corpo = {"codBarraLinhaDigitavel": codigo, "valorPagar": f"{valor_centavos / 100:.2f}",
                 "dataVencimento": vencimento, "dataPagamento": data_pagamento}
        if documento:
            corpo["cpfCnpjBeneficiario"] = documento
        r = self._ir("POST", f"{self.base}/banking/v2/pagamento", json_corpo=corpo,
                     cabecalhos=self._cab())
        if r.status in (200, 201) and isinstance(r.corpo, dict):
            return r.corpo
        raise Recusa(_frase(r.corpo) or f"O Inter recusou o pagamento (HTTP {r.status}).")

    def pagar_pix(self, destinatario: dict, valor_centavos: int, descricao: str,
                  data_pagamento: str, idempotencia: str) -> dict:
        cab = {**self._cab(), "x-id-idempotente": idempotencia}
        corpo = {"valor": round(valor_centavos / 100, 2), "destinatario": destinatario,
                 "descricao": descricao[:140], "dataPagamento": data_pagamento}
        r = self._ir("POST", f"{self.base}/banking/v2/pix", json_corpo=corpo, cabecalhos=cab)
        if r.status in (200, 201) and isinstance(r.corpo, dict):
            return r.corpo
        raise Recusa(_frase(r.corpo) or f"O Inter recusou o Pix (HTTP {r.status}).")

    def pagamentos(self, codigo_barras: str, data_inicio: str, data_fim: str) -> list[dict]:
        consulta = urllib.parse.urlencode({"codBarraLinhaDigitavel": codigo_barras,
                                           "dataInicio": data_inicio, "dataFim": data_fim})
        r = self._ir("GET", f"{self.base}/banking/v2/pagamento?{consulta}",
                     cabecalhos=self._cab())
        if r.status == 200 and isinstance(r.corpo, list):
            return r.corpo
        if r.status == 404:
            return []
        raise Recusa(_frase(r.corpo) or f"Consulta de pagamento recusada (HTTP {r.status}).")

    def pix(self, codigo_solicitacao: str) -> dict:
        r = self._ir("GET", f"{self.base}/banking/v2/pix/{codigo_solicitacao}",
                     cabecalhos=self._cab())
        if r.status == 200 and isinstance(r.corpo, dict):
            return r.corpo
        raise Recusa(_frase(r.corpo) or f"Consulta do Pix recusada (HTTP {r.status}).")

    def extrato(self, data_inicio: str, data_fim: str) -> list[dict]:
        """Os DÉBITOS do período, todas as páginas."""
        transacoes, pagina = [], 0
        while True:
            consulta = urllib.parse.urlencode({
                "dataInicio": data_inicio, "dataFim": data_fim, "pagina": pagina,
                "tamanhoPagina": 500, "tipoOperacao": "D"})
            r = self._ir("GET", f"{self.base}/banking/v2/extrato/completo?{consulta}",
                         cabecalhos=self._cab())
            if r.status != 200 or not isinstance(r.corpo, dict):
                raise Recusa(_frase(r.corpo) or f"Extrato recusado (HTTP {r.status}).")
            transacoes += list(r.corpo.get("transacoes") or [])
            if r.corpo.get("ultimaPagina", True) or pagina > 200:
                return transacoes
            pagina += 1


def cliente_da_casa(cfg: dict, *, pasta: Any = None,
                    transporte: Transporte | None = None) -> ClienteInter:
    """O cliente configurado. A credencial vem do cofre (ou do arquivo provisório)."""
    campos = credencial(pasta)
    if transporte is None:
        transporte = transporte_https(campos)
    return ClienteInter(cfg.get("despesas_ambiente") or "sandbox", transporte, campos)


# --------------------------------------------------------- pagar e conferir

def _agora() -> datetime:
    return datetime.now().astimezone().replace(microsecond=0)


def idempotencia(d: dict) -> str:
    """A mesma despesa, na mesma autorização, tem sempre a mesma chave no Pix."""
    return str(uuid.uuid5(_NS_IDEMPOTENCIA, f"{d['id']}:{d['autorizada_em'] or ''}"))


def _destinatario_pix(d: dict) -> dict:
    if d["forma"] == DP.PIX_COPIA_E_COLA:
        return {"tipo": "PIX_COPIA_E_COLA", "pixCopiaECola": d["codigo"]}
    return {"tipo": "CHAVE", "chave": d["codigo"]}


def _situacao_do_boleto(status: str) -> str:
    if status in BOLETO_PAGO:
        return DP.PAGA
    if status in BOLETO_FALHOU:
        return DP.FALHOU
    return DP.ENVIADA


def _situacao_do_pix(status: str) -> str:
    if status in PIX_PAGO:
        return DP.PAGA
    if status in PIX_FALHOU:
        return DP.FALHOU
    return DP.ENVIADA


def _gravar(db, despesa_id: int, *, situacao: str, status: str, codigo: str | None,
            mensagem: str, usuario: str, operacao: str, e2e: str | None = None,
            data_pagamento: str | None = None) -> dict:
    with db.transaction() as con:
        bd = banco(con)
        bd.escrever(
            """UPDATE dp_despesas SET situacao = %s, banco_status = %s,
                      banco_codigo = COALESCE(%s, banco_codigo),
                      banco_e2e = COALESCE(%s, banco_e2e),
                      data_pagamento = COALESCE(%s, data_pagamento), mensagem = %s
                WHERE id = %s""",
            (situacao, status, codigo, e2e, data_pagamento, mensagem[:500], int(despesa_id)))
        DP._evento(bd, despesa_id, operacao, situacao.lower(), mensagem, usuario,
                   DP._carimbo(_agora()))
        return DP.despesa(bd, despesa_id)


def pagar(db, despesa_id: int, *, cliente: ClienteInter, por: str,
          agora: datetime | None = None) -> dict:
    """Manda ao Inter a despesa AUTORIZADA. Sem trava de banco durante a rede.

    Devolve {situacao, mensagem}. «Espera» (teto do dia, pagamento desligado)
    não é erro: a despesa continua AUTORIZADA e sai na rodada certa.
    """
    quando = agora or _agora()
    hoje = quando.date().isoformat()
    with db.transaction() as con:
        bd = banco(con)
        d = DP._prender(bd, despesa_id)
        cfg = DP.configuracao(bd)
        if d["situacao"] != DP.AUTORIZADA:
            return {"situacao": d["situacao"], "mensagem": "Não está autorizada."}
        if cfg.get("despesas_pagamento_ligado") != "1":
            return {"situacao": DP.AUTORIZADA, "mensagem": "O pagamento automático está "
                    "desligado (Despesas → Configuração)."}
        if cfg.get("despesas_ambiente") != cliente.ambiente:
            return {"situacao": DP.AUTORIZADA, "mensagem": "O ambiente do banco mudou; "
                    "a rodada seguinte usa o novo."}
        t = DP.tetos(cfg)
        valor = int(d["valor"])
        if valor > t["pagamento"] and not d["acima_do_teto"]:
            return {"situacao": DP.AUTORIZADA, "mensagem": f"Acima do teto por pagamento "
                    f"(R$ {reais(t['pagamento'])}): o oficial precisa autorizar acima do teto."}
        if DP.pagas_hoje(bd, hoje) + valor > t["dia"]:
            return {"situacao": DP.AUTORIZADA, "mensagem": f"O teto do dia (R$ {reais(t['dia'])})"
                    f" foi alcançado: sai na próxima rodada de amanhã."}
        if d["forma"] in (DP.BOLETO, DP.ARRECADACAO) and d["vencimento"] < hoje:
            bd.escrever("UPDATE dp_despesas SET situacao = 'FALHOU', mensagem = %s "
                        "WHERE id = %s",
                        ("Vencida antes de sair: o valor pode ter juros e multa. Cadastre de "
                         "novo com o código atualizado.", int(despesa_id)))
            DP._evento(bd, despesa_id, "PAGAR", "vencida", "vencida antes de sair", por,
                       DP._carimbo(quando))
            return {"situacao": DP.FALHOU, "mensagem": "Vencida antes de sair."}
        bd.escrever(
            """UPDATE dp_despesas SET situacao = 'ENVIADA', enviada_em = %s, ambiente = %s,
                      tentativas = tentativas + 1, banco_status = 'SEM_RESPOSTA', mensagem = ''
                WHERE id = %s""", (DP._carimbo(quando), cliente.ambiente, int(despesa_id)))
        d = DP.despesa(bd, despesa_id)
    return _enviar(db, d, cliente=cliente, por=por, hoje=hoje)


def _enviar(db, d: dict, *, cliente: ClienteInter, por: str, hoje: str) -> dict:
    data_pagamento = max(d["vencimento"], hoje)
    try:
        if d["forma"] in (DP.BOLETO, DP.ARRECADACAO):
            r = cliente.pagar_codigo(d["codigo_barras"] or d["codigo"], int(d["valor"]),
                                     d["vencimento"], data_pagamento,
                                     d["beneficiario_documento"] or "")
            status = str(r.get("statusPagamento") or "")
            nova = _gravar(db, d["id"], situacao=_situacao_do_boleto(status), status=status,
                           codigo=str(r.get("codigoTransacao") or "") or None,
                           data_pagamento=str(r.get("dataAgendamento") or data_pagamento),
                           mensagem=f"Inter: {status}", usuario=por, operacao="PAGAR")
        else:
            r = cliente.pagar_pix(_destinatario_pix(d), int(d["valor"]),
                                  f"{d['descricao']}"[:140], data_pagamento, idempotencia(d))
            retorno = str(r.get("tipoRetorno") or "")
            status = {"APROVACAO": "AGUARDANDO_APROVACAO", "AGENDADO": "AGENDADO"}.get(
                retorno, "PROCESSADO")
            nova = _gravar(db, d["id"], situacao=DP.ENVIADA, status=status,
                           codigo=str(r.get("codigoSolicitacao") or "") or None,
                           data_pagamento=str(r.get("dataPagamento") or data_pagamento),
                           mensagem=f"Inter: {retorno}", usuario=por, operacao="PAGAR")
    except Recusa as erro:
        nova = _gravar(db, d["id"], situacao=DP.FALHOU, status="RECUSADO", codigo=None,
                       mensagem=f"O Inter recusou: {erro}", usuario=por, operacao="PAGAR")
    except Indisponivel as erro:
        # A despesa fica ENVIADA/SEM_RESPOSTA: `atualizar` pergunta antes de mandar de novo.
        nova = _gravar(db, d["id"], situacao=DP.ENVIADA, status="SEM_RESPOSTA", codigo=None,
                       mensagem=str(erro), usuario=por, operacao="PAGAR")
    return {"situacao": nova["situacao"], "mensagem": nova["mensagem"]}


def atualizar(db, despesa_id: int, *, cliente: ClienteInter, por: str,
              agora: datetime | None = None) -> dict:
    """Pergunta ao Inter como está a despesa ENVIADA. Reenvia só o que nunca chegou."""
    quando = agora or _agora()
    with db.connect() as con:
        d = DP.despesa(con, despesa_id)
    if not d or d["situacao"] not in (DP.ENVIADA, DP.PAGA):
        return {"situacao": d["situacao"] if d else None, "mensagem": ""}
    eh_pix = d["forma"] in (DP.PIX_COPIA_E_COLA, DP.PIX_CHAVE)
    try:
        if eh_pix and d["banco_codigo"]:
            r = cliente.pix(d["banco_codigo"])
            t = r.get("transacaoPix") or {}
            status = str(t.get("status") or "")
            nova = _gravar(db, despesa_id, situacao=_situacao_do_pix(status), status=status,
                           codigo=None, e2e=str(t.get("endToEnd") or "") or None,
                           mensagem=f"Inter: {status}", usuario=por, operacao="ATUALIZAR")
            return {"situacao": nova["situacao"], "mensagem": nova["mensagem"]}
        if eh_pix:
            # A resposta do primeiro envio se perdeu: o mesmo x-id-idempotente
            # não paga duas vezes — o Inter devolve a mesma solicitação.
            return _enviar(db, d, cliente=cliente, por=por, hoje=quando.date().isoformat())
        inicio = (date.fromisoformat(d["enviada_em"][:10]) - timedelta(days=1)).isoformat()
        fim = max(d["vencimento"], quando.date().isoformat())
        achados = cliente.pagamentos(d["codigo_barras"] or d["codigo"], inicio, fim)
        vivos = [a for a in achados if str(a.get("statusPagamento") or "") not in BOLETO_FALHOU]
        escolhido = next((a for a in vivos if a.get("codigoTransacao") == d["banco_codigo"]),
                         vivos[0] if vivos else (achados[0] if achados else None))
        if escolhido is None:
            if d["banco_status"] == "SEM_RESPOSTA":
                return _enviar(db, d, cliente=cliente, por=por, hoje=quando.date().isoformat())
            return {"situacao": d["situacao"], "mensagem": "O Inter não achou o pagamento."}
        status = str(escolhido.get("statusPagamento") or "")
        nova = _gravar(db, despesa_id, situacao=_situacao_do_boleto(status), status=status,
                       codigo=str(escolhido.get("codigoTransacao") or "") or None,
                       mensagem=f"Inter: {status}", usuario=por, operacao="ATUALIZAR")
        return {"situacao": nova["situacao"], "mensagem": nova["mensagem"]}
    except InterError as erro:
        return {"situacao": d["situacao"], "mensagem": str(erro)}


def pagar_autorizadas(db, *, cliente: ClienteInter, por: str,
                      agora: datetime | None = None) -> dict:
    """A rodada do despachante: paga as autorizadas e pergunta pelas enviadas."""
    with db.connect() as con:
        ids = [int(r["id"]) for r in banco(con).ler(
            "SELECT id FROM dp_despesas WHERE situacao = 'AUTORIZADA' ORDER BY vencimento, id")]
        enviadas = [int(r["id"]) for r in banco(con).ler(
            "SELECT id FROM dp_despesas WHERE situacao = 'ENVIADA' ORDER BY id")]
    resumo = {"pagas": [], "esperam": [], "falharam": [], "atualizadas": []}
    for i in enviadas:
        r = atualizar(db, i, cliente=cliente, por=por, agora=agora)
        resumo["atualizadas"].append((i, r["situacao"]))
    for i in ids:
        r = pagar(db, i, cliente=cliente, por=por, agora=agora)
        chave = {DP.FALHOU: "falharam", DP.AUTORIZADA: "esperam"}.get(r["situacao"], "pagas")
        resumo[chave].append((i, r["mensagem"]))
    return resumo


# ---------------------------------------------------------------- o extrato

def _centavos(valor: Any) -> int:
    try:
        return round(abs(float(str(valor).replace(",", "."))) * 100)
    except ValueError:
        return -1


def _casa(d: dict, t: dict) -> bool:
    """O débito do extrato é o pagamento desta despesa? Valor e identidade, juntos."""
    if _centavos(t.get("valor")) != int(d["valor"]):
        return False
    det = t.get("detalhes") or {}
    if d["forma"] in (DP.PIX_COPIA_E_COLA, DP.PIX_CHAVE):
        return bool((d["banco_codigo"] and det.get("codigoSolicitacao") == d["banco_codigo"])
                    or (d["banco_e2e"] and det.get("endToEndId") == d["banco_e2e"]))
    codigos = {DP.digitos(det.get(k)) for k in ("codBarras", "linhaDigitavel", "codigoBarras")}
    return bool({DP.digitos(d["codigo_barras"]), DP.digitos(d["codigo"])} & (codigos - {""}))


def conciliar(db, *, cliente: ClienteInter, por: str, agora: datetime | None = None,
              dias: int = DIAS_DE_EXTRATO) -> dict:
    """Confere no extrato as despesas enviadas e pagas; só então lança no Livro Diário.

    Devolve as conciliadas e os DÉBITOS SEM DESPESA (o que saiu da conta e o
    sistema não conhece) — para o oficial ver, e não para cadastrar sozinho.
    """
    import livro_diario as LD
    quando = agora or _agora()
    hoje = quando.date()
    transacoes = cliente.extrato((hoje - timedelta(days=dias)).isoformat(), hoje.isoformat())
    with db.connect() as con:
        abertas = banco(con).ler(
            "SELECT * FROM dp_despesas WHERE situacao IN ('ENVIADA', 'PAGA') ORDER BY id")
        ja = {r["extrato_id"] for r in banco(con).ler(
            "SELECT extrato_id FROM dp_despesas WHERE extrato_id IS NOT NULL")}
    usadas: set[str] = set(ja)
    conciliadas = []
    for d in abertas:
        t = next((t for t in transacoes if str(t.get("idTransacao")) not in usadas
                  and _casa(d, t)), None)
        if t is None:
            continue
        ident = str(t.get("idTransacao") or "")
        usadas.add(ident)
        dia = str(t.get("dataTransacao") or t.get("dataInclusao") or hoje.isoformat())[:10]
        with db.transaction() as con:
            bd = banco(con)
            atual = DP._prender(bd, d["id"])
            if atual["situacao"] not in (DP.ENVIADA, DP.PAGA):
                continue
            ld_id = None
            if atual["natureza"] == DP.DESPESA:
                ld_id = LD.lancar_despesa(
                    con, hoje=hoje.isoformat(), agora=DP._carimbo(quando), por=por, data=dia,
                    descricao=f"{atual['descricao']} — {atual['beneficiario_nome']}",
                    documento_especie=atual["documento_especie"],
                    valor=reais(int(atual["valor"])),
                    documento_numero=atual["documento_numero"])
            bd.escrever(
                """UPDATE dp_despesas SET situacao = 'CONCILIADA', paga_em = %s,
                          extrato_id = %s, ld_despesa_id = %s WHERE id = %s""",
                (dia, ident, ld_id, int(d["id"])))
            DP._evento(bd, d["id"], "CONCILIAR", "ok",
                       f"débito de {DP._br(dia)} no extrato"
                       + (" — lançada no Livro Diário" if ld_id else " — repasse, fora do livro"),
                       por, DP._carimbo(quando))
        conciliadas.append(int(d["id"]))
    sem_despesa = [{"data": str(t.get("dataTransacao") or "")[:10],
                    "valor": _centavos(t.get("valor")),
                    "descricao": str(t.get("descricao") or t.get("titulo") or "")[:120],
                    "tipo": t.get("tipoTransacao")}
                   for t in transacoes if str(t.get("idTransacao")) not in usadas]
    return {"conciliadas": conciliadas, "sem_despesa": sem_despesa,
            "lidas": len(transacoes)}
