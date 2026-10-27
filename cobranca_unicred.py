"""A COBRANÇA PELA UNICRED — a API de cobrança v2 do portal de desenvolvedores.

O CONTRATO (os sete PDFs do portal Unicred Developers que o oficial juntou
em 27/10/2026: Emissão, Consulta, PDF do boleto, Baixa, e os três marcados
«[PILOTO]» — concessão de abatimento, cancelamento de abatimento e manutenção
de protesto automático)
    Base: https://api.e-unicred.com.br/cobranca/... na produção e
    https://api.e-unicred.com.br/homolog/cobranca/... na homologação. TLS 1.2.
    Cabeçalhos em toda chamada: `Authorization: Bearer`, `cooperativa`,
    `apiKey`, `content-type: application/json`.

    - Emitir: POST /cobranca/v2/beneficiarios/{id_beneficiario}/titulos
      {beneficiarioVariacaoCarteira, seuNumero(15), valor, vencimento,
      pagador{nomeRazaoSocial(40), tipoPessoa F|J, tipoDocumento,
      numeroDocumento, nomeFantasia (OBRIGATÓRIO para PJ), email,
      endereco{logradouro(60), numero(5), complemento(30), bairro(40),
      cidade(50), uf, cep}}, mensagensFichaCompensacao (6 de 80)}
      → 200 com o `id_titulo`. Assíncrona: o registro na CIP vem depois.
    - Consultar: GET .../titulos/{id_titulo}/status → 200 {status ABERTO |
      BAIXADO | LIQUIDADO | EM_PROCESSAMENTO, motivo (DECURSO_PRAZO |
      PROTESTADO), codBarras(44), linhaDigitavel, nossoNumero, qrCodePix,
      pagamentos{data, valor}}, ou 202 sem corpo (ainda processando).
    - PDF: GET .../titulos/{id_titulo} → o PDF binário, ou 202.
    - Baixa: POST .../titulos/{id_titulo}/baixa {tipo: SOLICITACAO_CEDENTE,
      justificativa RECEBIDO | NAO_RECEBIDO | NAO_INFORMADO} → 201
      {codigoInstrucao}. É o CANCELAMENTO deste sistema (NAO_RECEBIDO).
    - Abatimento: POST .../v2/.../concessao-abatimento {valorAbatimento,
      justificativa} → 201; o último enviado vale.
    - Cancelar abatimento: POST /cobranca/**v1**/.../cancelamento-concessao-
      abatimento {justificativa} → 201. O documento escreve v1 nos três
      lugares — homologação, produção e o exemplo —, ao contrário dos outros
      seis caminhos; transcrito como está.
    - Protesto automático: POST .../v2/.../protesto-automatico
      {enviaProtestoAposVencimento, quantidadeDiasProtesto,
      protestoDiasUteis} → 201.

    **AS INSTRUÇÕES SÃO ASSÍNCRONAS.** Baixa, abatimento e protesto devolvem
    201 com um código de instrução: o banco RECEBEU, e não aplicou. O
    resultado vem pelo webhook ou pelo CNAB de retorno — e pela consulta,
    que é o que este sistema usa. A tela diz «pedido», e não «feito».

    **JUROS E MULTA VÊM DO CADASTRO DO BENEFICIÁRIO** quando não informados
    («caso o beneficiário tenha juros padrão em seu cadastro e este não for
    informado, o sistema assume o padrão»). Este módulo NÃO os informa: quem
    decide juros e multa de emolumento é o cadastro que a casa combinou com a
    cooperativa, e não um campo de tela.

O QUE NÃO VEIO NA DOCUMENTAÇÃO, E FICA DECLARADO
    1. **A AUTENTICAÇÃO.** Os sete documentos dizem «o token gerado na API de
       autenticação» e «o mesmo usuário e senha já fornecidos», e nenhum é a
       API de autenticação. O que está escrito aqui vem da ÚNICA fonte
       pública — a biblioteca PHP `gildonei/unicred` (2022):
       POST {base}/oauth2/v2/grant-token {nomeUsuario, senha} com o
       cabeçalho `apiKey`, resposta {accessToken}. **A CONFERIR na
       homologação**: se falhar, é aqui, e a frase da tela diz isso.
       E sem `expires_in` medido o token não se guarda além de uma rodada
       (`VIDA_DO_TOKEN`): guardar «para sempre» faria a casa mandar token
       vencido sem saber.
    2. **A busca por seu número.** Não há: `procurar` devolve None, e a
       emissão que ficou sem resposta vira FALHOU com a frase que manda
       conferir no internet banking antes de emitir outra.
    3. **Pagar, Pix de saída e extrato.** Nada disso está nos sete
       documentos. Pedir ao gerente.
    4. **O tamanho da linha digitável.** A consulta declara 46; o boleto
       FEBRABAN tem 47. Não se confere o tamanho do que a Unicred devolve.
"""
from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

import cobranca as CB
from cobranca_banco import (
    BancoError,
    CredencialAusente,
    CredencialTrancada,
    Indisponivel,
    Recusa,
)
from despesas_inter import Resposta

ENDERECOS = {
    "producao": "https://api.e-unicred.com.br",
    "sandbox": "https://api.e-unicred.com.br/homolog",
}
CAMINHO_DO_TOKEN = "/oauth2/v2/grant-token"
PROCEDENCIA_DO_TOKEN = "biblioteca gildonei/unicred (2022) — A CONFERIR na homologação"
NOME_NO_COFRE = "banco_unicred"
ARQUIVO_DA_CREDENCIAL = "banco_unicred.cred"
CAMPOS_DA_CREDENCIAL = ("api_key", "usuario", "senha", "cooperativa", "beneficiario",
                        "variacao_carteira")
ROTULOS_DA_CREDENCIAL = {
    "api_key": "apiKey (Access token da aplicação no Portal API)",
    "usuario": "Usuário da API de cobrança",
    "senha": "Senha da API de cobrança",
    "cooperativa": "Código da cooperativa (4 dígitos)",
    "beneficiario": "id_beneficiario (vem na planilha de homologação/produção)",
    "variacao_carteira": "Variação da carteira (beneficiarioVariacaoCarteira)",
}
PRAZO_SEGUNDOS = 30
VIDA_DO_TOKEN = 300

# A situação da Unicred → a nossa.
SITUACAO = {
    "EM_PROCESSAMENTO": CB.EMITINDO,
    "ABERTO": CB.ABERTA,
    "LIQUIDADO": CB.RECEBIDA,
    "BAIXADO": CB.BAIXADA,
}
MOTIVO = {
    "DECURSO_PRAZO": "Baixada pela Unicred por decurso de prazo.",
    "PROTESTADO": "Baixada pela Unicred: o título foi protestado.",
}

Transporte = Callable[..., Resposta]


# --------------------------------------------------------------- a credencial

def _pasta(pasta: Any = None):
    from pathlib import Path
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
    """A credencial da Unicred: o cofre da automação primeiro; senão, o `.cred` cifrado."""
    cofre = _cofre()
    if cofre is not None:
        try:
            campos = cofre.ler(NOME_NO_COFRE)
        except Exception as erro:
            if getattr(erro, "cofre_trancado", False) or "Trancad" in type(erro).__name__:
                raise CredencialTrancada("O cofre está trancado: o oficial precisa "
                                         "desbloqueá-lo para a cobrança andar.") from erro
            campos = None
        if campos:
            return dict(campos)
    import cofre_cred
    campos = cofre_cred.ler(_pasta(pasta), ARQUIVO_DA_CREDENCIAL)
    if campos:
        return dict(campos)
    raise CredencialAusente("A credencial da Unicred não foi cadastrada "
                            "(Cobrança → Configuração).")


def conferir_credencial(campos: Mapping[str, Any]) -> dict:
    """Confere a forma de cada campo. Só calcula. Sem segredo na frase."""
    limpos = {c: str(campos.get(c) or "").strip() for c in CAMPOS_DA_CREDENCIAL}
    faltam = [ROTULOS_DA_CREDENCIAL[c] for c, v in limpos.items() if not v]
    if faltam:
        raise CB.CobrancaError("Faltam na credencial da Unicred: " + "; ".join(faltam) + ".")
    if not limpos["cooperativa"].isdigit():
        raise CB.CobrancaError("O código da cooperativa tem só dígitos (ex.: 0001).")
    if not re.fullmatch(r"[0-9A-Fa-f]{32}", limpos["beneficiario"]):
        raise CB.CobrancaError("O id_beneficiario da Unicred tem 32 caracteres "
                               "hexadecimais, como na planilha da cooperativa.")
    if not limpos["variacao_carteira"].isdigit():
        raise CB.CobrancaError("A variação da carteira é um número.")
    return limpos


def gravar_credencial(campos: Mapping[str, Any], pasta: Any = None) -> dict:
    """Grava no cofre da automação, se existir; senão, no `.cred` cifrado. ESCREVE EM DISCO."""
    limpos = conferir_credencial(campos)
    cofre = _cofre()
    if cofre is not None:
        try:
            cofre.gravar(NOME_NO_COFRE, limpos, tipo="API", por="cobranca")
        except Exception as erro:
            # Cofre trancado é o caso comum: a frase do cofre diz o que fazer.
            raise CB.CobrancaError(f"O cofre não gravou a credencial da Unicred: {erro}") from erro
        return {"onde": "cofre"}
    import cofre_cred
    base = _pasta(pasta)
    base.mkdir(parents=True, exist_ok=True)
    try:
        cofre_cred.gravar(base, ARQUIVO_DA_CREDENCIAL, limpos)
        conferido = cofre_cred.ler(base, ARQUIVO_DA_CREDENCIAL)
    except (OSError, cofre_cred.CofreError) as erro:
        raise CB.CobrancaError(f"A credencial da Unicred não foi gravada: {erro}.") from erro
    if any(conferido.get(k, "") != v for k, v in limpos.items()):
        raise CB.CobrancaError("A credencial da Unicred não voltou igual na conferência.")
    return {"onde": "arquivo cifrado da pasta de dados"}


def resumo_da_credencial(pasta: Any = None) -> dict | None:
    """Para a tela: onde mora e a cooperativa. Sem nenhum segredo.

    Com o cofre instalado lê só os METADADOS: o cofre recusa entregar o
    segredo dentro de uma requisição web.
    """
    cofre = _cofre()
    if cofre is not None:
        try:
            cofre.metadados(NOME_NO_COFRE)
        except Exception as erro:
            if type(erro).__name__ == "ItemInexistente":
                return None
            return {"erro": str(erro)}
        return {"onde": "cofre"}
    try:
        campos = credencial(pasta)
    except BancoError:
        return None
    return {"onde": "arquivo cifrado", "cooperativa": campos.get("cooperativa", "")}


# ---------------------------------------------------------------- o transporte

def transporte_https(prazo: int = PRAZO_SEGUNDOS) -> Transporte:
    """HTTPS com TLS 1.2 ou mais. Abre rede: não roda em teste."""
    contexto = ssl.create_default_context()
    contexto.minimum_version = ssl.TLSVersion.TLSv1_2

    def chamar(metodo: str, url: str, *, json_corpo: Any = None,
               cabecalhos: dict | None = None) -> Resposta:
        cab = dict(cabecalhos or {})
        dados = None
        if json_corpo is not None:
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
                return Resposta(status, bruto, tipo)
        return Resposta(status, bruto, tipo)

    return chamar


def _frase(corpo: Any) -> str:
    """A frase de erro, nas TRÊS formas que os documentos mostram.

    `message` em todos; `body: [{Fields, message}]` na emissão (422);
    `details: ["campo: mensagem"]` e `errorCode` nas instruções.
    """
    if not isinstance(corpo, dict):
        return ""
    partes = [str(corpo.get("message") or "")]
    for item in corpo.get("body") or []:
        if isinstance(item, dict):
            campo = item.get("Fields") or item.get("fields") or ""
            partes.append(f"{campo}: {item.get('message') or ''}".strip(": "))
    partes += [str(d) for d in (corpo.get("details") or [])]
    if corpo.get("errorCode"):
        partes.append(f"(código {corpo['errorCode']})")
    return " — ".join(p for p in partes if p)[:400]


# ------------------------------------------------------------------ o cliente

class ClienteCobrancaUnicred:
    """A cobrança v2 da Unicred, por um transporte injetável."""

    banco = CB.UNICRED

    def __init__(self, ambiente: str, transporte: Transporte, campos: Mapping[str, Any]):
        if ambiente not in ENDERECOS:
            raise BancoError(f"Ambiente desconhecido: «{ambiente}».")
        self.ambiente = ambiente
        self.base = ENDERECOS[ambiente]
        self._transporte = transporte
        self._campos = {c: str(campos.get(c) or "").strip() for c in CAMPOS_DA_CREDENCIAL}
        self._token = ""
        self._vence = 0.0

    def _titulos(self, versao: str = "v2") -> str:
        benef = urllib.parse.quote(self._campos["beneficiario"])
        return f"{self.base}/cobranca/{versao}/beneficiarios/{benef}/titulos"

    def _ir(self, metodo: str, url: str, **kw) -> Resposta:
        try:
            r = self._transporte(metodo, url, **kw)
        except BancoError:
            raise
        except (OSError, TimeoutError, ValueError) as erro:
            raise Indisponivel(f"Sem resposta da Unicred ({type(erro).__name__}).") from erro
        if r.status >= 500 or r.status in (408, 429):
            raise Indisponivel(f"A Unicred respondeu HTTP {r.status}; tento de novo depois.")
        return r

    def token(self) -> str:
        if self._token and time.monotonic() < self._vence:
            return self._token
        r = self._ir("POST", f"{self.base}{CAMINHO_DO_TOKEN}",
                     json_corpo={"nomeUsuario": self._campos["usuario"],
                                 "senha": self._campos["senha"]},
                     cabecalhos={"apiKey": self._campos["api_key"],
                                 "accept": "application/json"})
        corpo = r.corpo if isinstance(r.corpo, dict) else {}
        token = corpo.get("accessToken") or corpo.get("access_token")
        if r.status not in (200, 201) or not token:
            raise Recusa(f"A Unicred recusou a autenticação (HTTP {r.status}). Confira usuário, "
                         f"senha e apiKey. O endereço do token veio da {PROCEDENCIA_DO_TOKEN}: "
                         f"se a credencial estiver certa, é ele que precisa ser conferido.")
        vida = int(corpo.get("expires_in") or corpo.get("expiresIn") or VIDA_DO_TOKEN)
        self._token = str(token)
        self._vence = time.monotonic() + max(30, min(vida, 3600) - 60)
        return self._token

    def _cab(self) -> dict:
        return {"Authorization": f"Bearer {self.token()}",
                "cooperativa": self._campos["cooperativa"],
                "apiKey": self._campos["api_key"], "accept": "application/json",
                "cache-control": "no-cache"}

    # --------------------------------------------------------- as operações

    def corpo(self, c: Mapping[str, Any]) -> dict:
        """A emissão, montada da linha de `cb_cobrancas`. Só calcula.

        Campo opcional VAZIO NÃO VAI: o documento pede «não informar conteúdo
        igual a null ou brancos nos campos não obrigatórios».
        """
        end = CB.endereco(c)
        doc = c["pagador_documento"]
        juridica = len(doc) == 14
        endereco = {"logradouro": end.get("logradouro", "")[:60],
                    "cidade": end.get("cidade", "")[:50], "uf": end.get("uf", ""),
                    "cep": end.get("cep", "")}
        for chave, limite in (("numero", 5), ("complemento", 30), ("bairro", 40)):
            if end.get(chave):
                endereco[chave] = end[chave][:limite]
        pagador = {"nomeRazaoSocial": c["pagador_nome"][:40],
                   "tipoPessoa": "J" if juridica else "F",
                   "tipoDocumento": "CNPJ" if juridica else "CPF",
                   "numeroDocumento": doc, "endereco": endereco}
        if juridica:
            pagador["nomeFantasia"] = c["pagador_nome"][:256]
        if c.get("pagador_email"):
            pagador["email"] = c["pagador_email"]
        corpo = {"beneficiarioVariacaoCarteira": int(self._campos["variacao_carteira"]),
                 "seuNumero": c["seu_numero"], "valor": round(int(c["valor"]) / 100, 2),
                 "vencimento": c["vencimento"], "pagador": pagador}
        linhas = CB.linhas_da_mensagem(c.get("mensagem"), largura=80, maximo=6)
        if linhas:
            corpo["mensagensFichaCompensacao"] = linhas
        return corpo

    def emitir(self, c: Mapping[str, Any]) -> str:
        r = self._ir("POST", self._titulos(), json_corpo=self.corpo(c), cabecalhos=self._cab())
        if r.status in (200, 201):
            achado = id_do_titulo(r.corpo)
            if achado:
                return achado
            raise Recusa("A Unicred aceitou, mas a resposta não trouxe o id do título. "
                         "Confira no internet banking pelo seu número antes de emitir de novo.")
        raise Recusa(_frase(r.corpo) or f"A Unicred recusou a emissão (HTTP {r.status}).")

    def consultar(self, c: Mapping[str, Any]) -> dict | None:
        url = f"{self._titulos()}/{urllib.parse.quote(str(c['banco_id']))}/status"
        r = self._ir("GET", url, cabecalhos=self._cab())
        if r.status == 202:
            return None
        if r.status == 200 and isinstance(r.corpo, dict):
            return ler(r.corpo)
        if r.status == 404:
            return None
        raise Recusa(_frase(r.corpo) or f"A Unicred recusou a consulta (HTTP {r.status}).")

    def procurar(self, c: Mapping[str, Any], *, data_inicial: str, data_final: str) -> None:
        """A Unicred não tem busca por seu número nos documentos: não se adivinha."""
        return None

    def pdf(self, c: Mapping[str, Any]) -> bytes:
        url = f"{self._titulos()}/{urllib.parse.quote(str(c['banco_id']))}"
        r = self._ir("GET", url, cabecalhos={**self._cab(), "accept": "application/pdf"})
        if r.status == 202:
            raise Recusa("A Unicred ainda está gerando o PDF. Tente de novo em instantes.")
        if r.status == 200 and isinstance(r.corpo, (bytes, bytearray)) and \
                bytes(r.corpo[:5]) == b"%PDF-":
            return bytes(r.corpo)
        raise Recusa(_frase(r.corpo) or f"A Unicred não entregou o PDF (HTTP {r.status}).")

    def _instrucao(self, caminho: str, corpo: dict, *, versao: str = "v2") -> str:
        url = f"{self._titulos(versao)}/{caminho}"
        r = self._ir("POST", url, json_corpo=corpo, cabecalhos=self._cab())
        if r.status in (200, 201):
            return str((r.corpo or {}).get("codigoInstrucao") or "") if isinstance(r.corpo, dict) else ""
        raise Recusa(_frase(r.corpo) or f"A Unicred recusou a instrução (HTTP {r.status}).")

    def cancelar(self, c: Mapping[str, Any], motivo: str) -> str:
        """A baixa pedida pelo beneficiário, com «não recebido». Devolve a instrução."""
        return self._instrucao(f"{urllib.parse.quote(str(c['banco_id']))}/baixa",
                               {"tipo": "SOLICITACAO_CEDENTE", "justificativa": "NAO_RECEBIDO"})

    def abatimento(self, c: Mapping[str, Any], valor_centavos: int, justificativa: str) -> str:
        if not 0 < int(valor_centavos) < int(c["valor"]):
            raise CB.CobrancaError("O abatimento tem de ser maior que zero e menor que o "
                                   "valor do boleto.")
        return self._instrucao(
            f"{urllib.parse.quote(str(c['banco_id']))}/concessao-abatimento",
            {"valorAbatimento": round(int(valor_centavos) / 100, 2),
             "justificativa": CB._texto(justificativa, 200)})

    def cancelar_abatimento(self, c: Mapping[str, Any], justificativa: str) -> str:
        return self._instrucao(
            f"{urllib.parse.quote(str(c['banco_id']))}/cancelamento-concessao-abatimento",
            {"justificativa": CB._texto(justificativa, 200)}, versao="v1")

    def protesto_automatico(self, c: Mapping[str, Any], *, ligado: bool, dias: int,
                            dias_uteis: bool) -> str:
        if int(dias) < 0 or (ligado and int(dias) < 1):
            raise CB.CobrancaError("Informe os dias depois do vencimento para o protesto.")
        return self._instrucao(
            f"{urllib.parse.quote(str(c['banco_id']))}/protesto-automatico",
            {"enviaProtestoAposVencimento": bool(ligado),
             "quantidadeDiasProtesto": int(dias), "protestoDiasUteis": bool(dias_uteis)})


def id_do_titulo(corpo: Any) -> str:
    """O id_titulo da resposta da emissão. Só calcula.

    O documento mostra a resposta de DUAS formas — «Preview: id_titulo:…» e um
    JSON com `id_titulo` (sem aspas no valor, o que nem é JSON válido). Aceita
    o campo do JSON e, no texto, os 32 hexadecimais depois de «id_titulo».
    """
    if isinstance(corpo, dict):
        for chave in ("id_titulo", "idTitulo", "id"):
            if corpo.get(chave):
                return str(corpo[chave])
        return ""
    texto = corpo.decode("utf-8", "replace") if isinstance(corpo, (bytes, bytearray)) else str(corpo or "")
    achado = re.search(r"id_titulo\W{0,4}([0-9A-Fa-f]{32})", texto)
    return achado.group(1) if achado else ""


def ler(corpo: Mapping[str, Any]) -> dict:
    """A resposta da consulta → a forma comum de `cobranca.gravar_resposta`. Só calcula."""
    status = str(corpo.get("status") or "").upper()
    motivo = str(corpo.get("motivo") or "").upper()
    saida = {
        "banco_status": status,
        "banco_motivo": MOTIVO.get(motivo, motivo if motivo not in ("", "NULL", "NONE") else ""),
        "nosso_numero": corpo.get("nossoNumero") or "",
        "linha_digitavel": corpo.get("linhaDigitavel") or "",
        "codigo_barras": corpo.get("codBarras") or "",
        "pix_copia_e_cola": corpo.get("qrCodePix") or "",
    }
    if status in SITUACAO:
        saida["situacao"] = SITUACAO[status]
    if status == "LIQUIDADO":
        pagamentos = corpo.get("pagamentos") or []
        if isinstance(pagamentos, dict):
            pagamentos = [pagamentos]
        valores = [CB.centavos_do_banco(p.get("valor")) for p in pagamentos if isinstance(p, dict)]
        valores = [v for v in valores if v]
        if valores:
            saida["valor_recebido"] = sum(valores)
        datas = sorted(str(p.get("data") or "")[:10] for p in pagamentos if isinstance(p, dict))
        if datas and datas[-1]:
            saida["data_pagamento"] = datas[-1]
        saida["forma_recebida"] = "BOLETO"
    return saida


def cliente_da_casa(cfg: Mapping[str, str], *, pasta: Any = None,
                    transporte: Transporte | None = None) -> ClienteCobrancaUnicred:
    campos = credencial(pasta)
    return ClienteCobrancaUnicred(cfg.get("cobranca_ambiente") or "sandbox",
                                  transporte or transporte_https(), campos)
