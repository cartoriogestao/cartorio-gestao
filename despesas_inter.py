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
    `atualizar` pergunta ao banco; só o Pix se reenvia, uma vez, com a MESMA
    chave de idempotência. Não lança no Livro Diário o que o extrato não
    mostrou.

A CREDENCIAL
    Client ID, Client Secret, o certificado (.crt) e a chave (.key) que o
    Inter entrega na integração. Moram FORA do banco: no cofre da automação
    (`automacao_cofre`, item «banco_inter»), quando ele existe; senão, no
    `banco_inter.cred` da pasta de dados, CIFRADO pelo `cofre_cred` — o mesmo
    caminho das chaves dos robôs e do token do WhatsApp. O cofre trancado
    (ninguém digitou a senha-mestra depois de a máquina reiniciar) não é erro
    do banco: o pagamento espera, e a despesa não muda.

    Correção de 26/10/2026 (revisão de segurança dos PRs abertos, MÉDIA): a
    primeira versão deste ramo gravava `banco_inter.json` em TEXTO CLARO — o
    Client Secret e a chave privada do banco ficariam legíveis por qualquer
    conta da máquina se o `icacls` falhasse, e o `.json` está fora dos padrões
    que a subida reaperta (`permissao_local.SEGREDOS_DA_PASTA`). O arquivo
    antigo ainda se lê: na primeira leitura ele vai para o `.cred` cifrado e é
    apagado — e também ao gravar a credencial pela tela.

O REENVIO DE QUEM FICOU SEM RESPOSTA (26/10/2026, revisão de segurança, ALTA)
    `atualizar` reenviava a despesa ENVIADA/SEM_RESPOSTA sem conferir o
    interruptor nem o ambiente — e `pagar_autorizadas` roda `atualizar` em
    toda ENVIADA. Um boleto de TESTE do sandbox com a resposta perdida, depois
    de o oficial trocar para a produção e ligar o pagamento, sairia na conta
    de verdade, sem teto e sem autorização em produção. Agora:
      - despesa enviada noutro ambiente NUNCA vai ao banco de agora, nem para
        consulta: a que ficou sem resposta vira FALHOU, com a frase;
      - o reenvio passa pelas travas de `pagar` (pagamento ligado, mesmo
        ambiente) e é decidido com a linha presa (FOR UPDATE), regravando
        `banco_status` para REENVIANDO antes de soltar a trava: o botão da
        ficha e o despachante no mesmo minuto não reenviam os dois;
      - só o Pix se reenvia, e uma vez só (`tentativas` vai a 2): ele leva
        `x-id-idempotente`, e o Inter devolve a mesma solicitação. O boleto
        NÃO tem chave de idempotência: sem resposta e sem rastro na consulta
        depois de PRAZO_DE_ESPERA, vira FALHOU, e o oficial confere no
        Internet Banking antes de devolver à autorização.
"""
from __future__ import annotations

import json
import logging
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
# O `.cred` cifrado pelo `cofre_cred` (26/10/2026). O `.json` é o arquivo em
# texto claro da primeira versão: só se lê, para migrar, e então se apaga.
ARQUIVO_DA_CREDENCIAL = "banco_inter.cred"
ARQUIVO_ANTIGO = "banco_inter.json"
CAMPOS_DA_CREDENCIAL = ("client_id", "client_secret", "crt_pem", "key_pem")
CAMPOS_GUARDADOS = (*CAMPOS_DA_CREDENCIAL, "conta_corrente")
PRAZO_SEGUNDOS = 30
DIAS_DE_EXTRATO = 10
# O REENVIO (26/10/2026): um envio e UM reenvio, e só do Pix. PRAZO_DE_ESPERA é
# quanto a casa espera a consulta do Inter mostrar o boleto que ficou sem
# resposta, e quanto um reenvio «em curso» pode durar antes de ser tido por
# interrompido — cada ida ao Inter tem PRAZO_SEGUNDOS, e quinze minutos sobram.
MAXIMO_DE_ENVIOS = 2
PRAZO_DE_ESPERA = timedelta(minutes=15)
SEM_RESPOSTA = "SEM_RESPOSTA"
REENVIANDO = "REENVIANDO"
REENVIAR = "REENVIAR"

LOG = logging.getLogger("cartorio.despesas")

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


def _do_arquivo_antigo(base: Path) -> dict | None:
    """O `banco_inter.json` em texto claro da primeira versão deste ramo, se existir."""
    antigo = base / ARQUIVO_ANTIGO
    if not antigo.is_file():
        return None
    try:
        campos = json.loads(antigo.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as erro:
        raise CredencialAusente("O arquivo antigo da credencial do Inter está ilegível. "
                                "Cadastre-a de novo (Despesas → Configuração).") from erro
    if not isinstance(campos, dict):
        return None
    limpos = {c: str(campos.get(c) or "").strip() for c in CAMPOS_GUARDADOS}
    return limpos if any(limpos.values()) else None


def _gravar_cifrado(base: Path, campos: dict) -> None:
    """Grava no `.cred` cifrado e LÊ DE VOLTA. ESCREVE EM DISCO.

    Campo vazio sai do arquivo (é a regra do `cofre_cred.gravar`): a credencial
    nova não herda a conta corrente da antiga. Falha vira `CofreError`.
    """
    import cofre_cred
    valores = {c: str(campos.get(c) or "").strip() for c in CAMPOS_GUARDADOS}
    try:
        cofre_cred.gravar(base, ARQUIVO_DA_CREDENCIAL, valores)
    except OSError as erro:
        raise cofre_cred.CofreError(f"não consegui gravar em «{base}»: {erro}") from erro
    conferido = cofre_cred.ler(base, ARQUIVO_DA_CREDENCIAL)
    if any(conferido.get(k, "") != v for k, v in valores.items()):
        raise cofre_cred.CofreError("o arquivo cifrado não voltou igual na conferência")


def _apagar_o_antigo(base: Path) -> None:
    """Apaga o `.json` em texto claro. Não derruba nada: a falha fica no log."""
    try:
        (base / ARQUIVO_ANTIGO).unlink(missing_ok=True)
    except OSError as erro:
        LOG.warning("CREDENCIAL DO INTER EM TEXTO CLARO NAO FOI APAGADA (%s): %s",
                    base / ARQUIVO_ANTIGO, erro)


def credencial(pasta: Any = None) -> dict:
    """A credencial do Inter. O cofre da automação primeiro; senão, o `.cred` cifrado.

    O `banco_inter.json` em texto claro da primeira versão deste ramo ainda se
    lê: na primeira leitura ele vai para o `.cred` cifrado, que é LIDO DE
    VOLTA, e só então é apagado (a ordem de `cofre_cred.migrar_da_tabela`). Se
    a migração falhar, o pagamento não para — a credencial vem do arquivo
    antigo, o log avisa, e a leitura seguinte tenta de novo.
    """
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
    import cofre_cred
    base = _pasta(pasta)
    campos = cofre_cred.ler(base, ARQUIVO_DA_CREDENCIAL)
    if campos:
        return dict(campos)
    antigo = _do_arquivo_antigo(base)
    if antigo:
        try:
            _gravar_cifrado(base, antigo)
        except cofre_cred.CofreError as erro:
            LOG.warning("CREDENCIAL DO INTER FICOU NO ARQUIVO EM TEXTO CLARO: o cofre "
                        "não gravou (%s)", erro)
        else:
            _apagar_o_antigo(base)
        return {k: v for k, v in antigo.items() if v}
    if cofre_cred.situacao(base, ARQUIVO_DA_CREDENCIAL) == "nao_abre":
        raise CredencialAusente("O arquivo cifrado da credencial do Inter não abre nesta "
                                "máquina (a chave do cofre não é a mesma). Cadastre-a de "
                                "novo (Despesas → Configuração).")
    raise CredencialAusente("A credencial do Banco Inter não foi cadastrada "
                            "(Despesas → Configuração).")


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
    """Grava no cofre da automação, se existir; senão, no `.cred` cifrado. ESCREVE EM DISCO.

    Nos dois caminhos, o `banco_inter.json` em texto claro da primeira versão
    deste ramo é apagado depois de a credencial nova estar gravada. A ACL do
    `.cred` é a do `cofre_cred` (restrita na hora, e reapertada na subida pelo
    padrão `*.cred`); se o `icacls` falhar, o arquivo continua CIFRADO — é o
    que «falhar é aviso» de `permissao_local` tolera, e o texto claro não.
    """
    resumo = conferir_credencial(campos)
    limpos = {c: str(campos.get(c) or "").strip() for c in CAMPOS_GUARDADOS}
    base = _pasta(pasta)
    cofre = _cofre()
    if cofre is not None:
        cofre.gravar(NOME_NO_COFRE, {k: v for k, v in limpos.items() if v},
                     tipo="CERTIFICADO", validade=resumo["valido_ate"], por="despesas")
        onde = "cofre"
    else:
        import cofre_cred
        base.mkdir(parents=True, exist_ok=True)
        try:
            _gravar_cifrado(base, limpos)
        except cofre_cred.CofreError as erro:
            raise DP.DespesaError(f"A credencial do Inter não foi gravada: {erro}.") from erro
        onde = "arquivo cifrado da pasta de dados"
    _apagar_o_antigo(base)
    return {**resumo, "onde": onde}


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
    """O Banking v2 do Inter, por um transporte injetável.

    `escopos` é atributo de classe para a cobrança (`cobranca_inter`) pedir os
    dela com a MESMA credencial e o mesmo token: o Inter entrega um token por
    conjunto de escopos, e a integração da conta pode ter os dois.
    """

    escopos = ESCOPOS

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
            "grant_type": "client_credentials", "scope": self.escopos})
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
        # `tentativas` conta os envios DESTA autorização (26/10/2026): começa em 1
        # aqui, e o único reenvio do Pix (`_reenviar_pix`) a leva a 2. Devolvida e
        # autorizada de novo, a despesa recomeça a conta.
        bd.escrever(
            """UPDATE dp_despesas SET situacao = 'ENVIADA', enviada_em = %s, ambiente = %s,
                      tentativas = 1, banco_status = 'SEM_RESPOSTA', mensagem = ''
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
        # A despesa fica ENVIADA/SEM_RESPOSTA: `atualizar` pergunta ao banco, e só
        # o Pix se reenvia (uma vez, com a mesma chave de idempotência).
        nova = _gravar(db, d["id"], situacao=DP.ENVIADA, status="SEM_RESPOSTA", codigo=None,
                       mensagem=str(erro), usuario=por, operacao="PAGAR")
    return {"situacao": nova["situacao"], "mensagem": nova["mensagem"]}


def _em_curso(desde: Any, quando: datetime) -> bool:
    """A ida ao banco que começou em `desde` (carimbo da casa) ainda pode estar no ar?"""
    return bool(desde) and str(desde) > DP._carimbo(quando - PRAZO_DE_ESPERA)


def _falhou(bd, d: dict, *, mensagem: str, por: str, quando: datetime) -> dict:
    """Marca FALHOU com a frase, na transação (e com a linha presa) de quem chama."""
    bd.escrever("UPDATE dp_despesas SET situacao = 'FALHOU', mensagem = %s WHERE id = %s",
                (mensagem[:500], int(d["id"])))
    DP._evento(bd, d["id"], "ATUALIZAR", "falhou", mensagem, por, DP._carimbo(quando))
    return {"situacao": DP.FALHOU, "mensagem": mensagem}


def _outro_ambiente(db, despesa_id: int, *, cliente: ClienteInter, por: str,
                    quando: datetime) -> dict:
    """A despesa foi enviada noutro ambiente: nada vai ao banco de agora.

    A que ficou sem resposta (sem código do banco) vira FALHOU — reenviá-la
    aqui seria mandar à conta de verdade o boleto de teste do sandbox. A que
    tem resposta fica como está: a consulta dela é com o ambiente dela.
    """
    with db.transaction() as con:
        bd = banco(con)
        d = DP._prender(bd, despesa_id)
        de_la = d["ambiente"] or "desconhecido"
        if d["situacao"] == DP.ENVIADA and not d["banco_codigo"]:
            return _falhou(bd, d, por=por, quando=quando, mensagem=(
                f"Enviada ao banco no ambiente «{de_la}» e sem resposta; o ambiente "
                f"configurado agora é «{cliente.ambiente}». Não reenvio noutro ambiente: "
                f"confira no banco de «{de_la}» e, se precisar, cadastre de novo."))
    return {"situacao": d["situacao"], "mensagem": (
        f"Enviada no ambiente «{de_la}»; o banco configurado agora é «{cliente.ambiente}». "
        f"A consulta desta despesa só se faz com o ambiente em que ela saiu.")}


def _reenviar_pix(db, despesa_id: int, *, cliente: ClienteInter, por: str,
                  quando: datetime) -> dict:
    """O Pix sem resposta: reenvia UMA vez, com a mesma chave e as travas de `pagar`.

    A decisão é tomada com a linha presa (FOR UPDATE) e grava REENVIANDO antes
    de soltar a trava — a segunda rodada do mesmo minuto acha o reenvio em
    curso e não manda de novo. O reenvio interrompido (o processo caiu no meio)
    deixa de contar como «em curso» depois de PRAZO_DE_ESPERA, e aí a despesa
    vira FALHOU como a que não respondeu duas vezes.
    """
    with db.transaction() as con:
        bd = banco(con)
        d = DP._prender(bd, despesa_id)
        if d["situacao"] != DP.ENVIADA or d["banco_codigo"]:
            return {"situacao": d["situacao"], "mensagem": "Outra rodada já tratou desta "
                    "despesa."}
        status = d["banco_status"]
        if status == REENVIANDO and _em_curso(bd.valor(
                "SELECT max(quando) FROM dp_eventos WHERE despesa_id = %s AND operacao = %s",
                (int(despesa_id), REENVIAR)), quando):
            return {"situacao": DP.ENVIADA, "mensagem": "Um reenvio deste Pix ao Inter está "
                    "em curso."}
        if status not in (SEM_RESPOSTA, REENVIANDO):
            return {"situacao": DP.ENVIADA, "mensagem": f"Inter: {status}"}
        if int(d["tentativas"] or 0) >= MAXIMO_DE_ENVIOS:
            return _falhou(bd, d, por=por, quando=quando, mensagem=(
                "O Inter não respondeu ao envio nem ao reenvio do Pix, e não mando uma "
                "terceira vez. Confira no Internet Banking se o Pix saiu ANTES de devolver "
                "à autorização: a nova autorização muda a chave de idempotência, e o Inter "
                "não reconheceria o Pix repetido. Se saiu, registre como pago fora do banco."))
        cfg = DP.configuracao(bd)
        if cfg.get("despesas_pagamento_ligado") != "1":
            return {"situacao": DP.ENVIADA, "mensagem": "O Pix ficou sem resposta do Inter e o "
                    "pagamento automático está desligado: não reenvio. Ligue o pagamento "
                    "para a rodada reenviar, ou confira no Internet Banking."}
        if cfg.get("despesas_ambiente") != cliente.ambiente:
            return {"situacao": DP.ENVIADA, "mensagem": "O ambiente do banco mudou; não "
                    "reenvio."}
        bd.escrever("""UPDATE dp_despesas SET tentativas = tentativas + 1, banco_status = %s,
                              mensagem = '' WHERE id = %s""", (REENVIANDO, int(despesa_id)))
        DP._evento(bd, despesa_id, REENVIAR, "em curso", "Pix sem resposta: reenvio com a "
                   "mesma chave de idempotência", por, DP._carimbo(quando))
        d = DP.despesa(bd, despesa_id)
    return _enviar(db, d, cliente=cliente, por=por, hoje=quando.date().isoformat())


def _boleto_sem_rastro(db, despesa_id: int, *, por: str, quando: datetime) -> dict:
    """O boleto sem resposta que a consulta não mostra: NUNCA se reenvia sozinho.

    O POST do boleto não tem chave de idempotência: se o Inter aceitou e a
    resposta se perdeu, mandar de novo paga duas vezes. A casa espera
    PRAZO_DE_ESPERA (a consulta pode demorar a mostrar), e depois marca
    FALHOU — o oficial confere no Internet Banking antes de devolver.
    """
    with db.transaction() as con:
        bd = banco(con)
        d = DP._prender(bd, despesa_id)
        if (d["situacao"] != DP.ENVIADA or d["banco_codigo"]
                or d["banco_status"] != SEM_RESPOSTA):
            return {"situacao": d["situacao"], "mensagem": "O Inter não achou o pagamento."}
        if _em_curso(d["enviada_em"], quando):
            return {"situacao": DP.ENVIADA, "mensagem": "Sem resposta do Inter, e a consulta "
                    "ainda não mostra o pagamento: pergunto de novo na próxima rodada. Boleto "
                    "não se reenvia sozinho."}
        return _falhou(bd, d, por=por, quando=quando, mensagem=(
            "O Inter não respondeu ao envio do boleto e a consulta não mostra o pagamento. "
            "Boleto não se reenvia sozinho (não tem chave de idempotência): confira no "
            "Internet Banking. Se não saiu, devolva à autorização; se saiu, registre como "
            "pago fora do banco."))


def atualizar(db, despesa_id: int, *, cliente: ClienteInter, por: str,
              agora: datetime | None = None) -> dict:
    """Pergunta ao Inter como está a despesa ENVIADA. Reenvia só o Pix que nunca chegou.

    (26/10/2026) Nada vai ao banco de outro ambiente, e o reenvio passa pelas
    travas de `pagar` — ver «O REENVIO DE QUEM FICOU SEM RESPOSTA», no alto.
    """
    quando = agora or _agora()
    with db.connect() as con:
        d = DP.despesa(con, despesa_id)
    if not d or d["situacao"] not in (DP.ENVIADA, DP.PAGA):
        return {"situacao": d["situacao"] if d else None, "mensagem": ""}
    if (d["ambiente"] or "") != cliente.ambiente:
        return _outro_ambiente(db, despesa_id, cliente=cliente, por=por, quando=quando)
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
            return _reenviar_pix(db, despesa_id, cliente=cliente, por=por, quando=quando)
        inicio = (date.fromisoformat(d["enviada_em"][:10]) - timedelta(days=1)).isoformat()
        fim = max(d["vencimento"], quando.date().isoformat())
        achados = cliente.pagamentos(d["codigo_barras"] or d["codigo"], inicio, fim)
        vivos = [a for a in achados if str(a.get("statusPagamento") or "") not in BOLETO_FALHOU]
        escolhido = next((a for a in vivos if a.get("codigoTransacao") == d["banco_codigo"]),
                         vivos[0] if vivos else (achados[0] if achados else None))
        if escolhido is None:
            return _boleto_sem_rastro(db, despesa_id, por=por, quando=quando)
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
