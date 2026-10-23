"""O WSOficio do ONR — o web service do Ofício Eletrônico (SAEC), por SOAP.

    «coloquei as chaves de api de producao no sistema, vamos fazer funcionar»
    — o oficial, 09/10/2026, com `especificacao_wsoficio_dev.pdf` (v4.43)

NÃO É A API REST DO ONR (`onr_api.py`), E ISSO FOI MEDIDO NO DIA.
    O par gravado em `onr.cred` (produção) foi recusado pela API REST com HTTP
    422 «Parâmetro inválido: client_id e client_secret». E o formato dele é o
    deste serviço, e não o daquele: um número de 4 dígitos e um GUID de 36
    caracteres — o `IDParceiroWS` (tipo int, no contrato) e a chave do hash, que
    o manual manda pedir em oficioeletronico@onr.org.br. Os dois serviços
    convivem: a REST leva o indicador real e o edital; este leva os pedidos do
    Ofício Eletrônico (ofícios, penhora online, certidões, e-Protocolo,
    intimações) e o BDLight, que é o Indicador Pessoal por web service.

COMO SE AUTENTICA (manual, cap. 2 e 3.1)
    1. `LoginUsuarioCertificado` com os dados PÚBLICOS do certificado do usuário
       cadastrado no Ofício Eletrônico (CN do titular, O do emissor, chave
       pública, número de série, validade), o CPF, o e-mail e o `IDParceiroWS`.
       **A chave privada do A3 não entra** — nada de PKCS#11, que dá segfault
       nesta máquina (ver `assinatura_digital.py`).
    2. Ele devolve 5 tokens de 6 caracteres, de uso único, válidos por 8 horas.
    3. Cada chamada leva `Hash = SHA-1(chave + token)`, em UTF-8.
    E o acesso é **restrito por IP** — o IP de saída da casa tem de estar
    cadastrado no ONR junto do `IDParceiroWS`.

MEDIDO EM PRODUÇÃO EM 09/10/2026 (com autorização do oficial, só leitura)
    Login aceito — usuário 827433, instituição 9087, ativo —; ofícios e penhora
    online responderam (0 pedidos nos 30 dias anteriores). **O hash vale em
    MAIÚSCULAS.** **O login devolveu 1 token, e não os 5 do manual** — a sessão
    entra de novo quando acaba, e cada chamada custa um login. E o
    `ListPedidosPO` estoura `NullReferenceException` do lado deles se os dois
    campos de data de resposta não vierem (presentes e vazios resolvem).

O QUE ERA A CONFERIR ANTES DA MEDIÇÃO
    - **A caixa do hash.** O manual não traz exemplo (o campo vem como «...Hash
      obtido na autenticação...»). Começa em MAIÚSCULAS — a forma do
      `FormsAuthentication` do .NET em que o serviço (`.asmx`) foi feito — e,
      se o ONR responder «Hash inválido» (sem «já utilizado» nem «expirado»),
      tenta UMA vez a outra caixa e passa a usar a que valeu.
    - **A forma de cada campo do certificado.** Sem exemplo no manual; vai como
      o .NET lê o certificado no Windows (`GetPublicKeyString`,
      `GetSerialNumberString`, `GetExpirationDateString`). O que confirma a
      leitura: `ISSUERO` é `string(10)` no manual, e «ICP-Brasil» tem 10.

O QUE ESTE MÓDULO FAZ HOJE
    Lê: login, as listas e fichas dos pedidos de ofício e de penhora online, a
    lista dos arquivos do BDLight e — desde 11/10/2026 — as certidões a emitir.
    **Responde só as certidões** (informar custas, anexar, finalizar, devolver),
    por ordem do oficial («faça a da onr certidões»), e só a partir da tela de
    `onr_certidoes_web`, um clique por pedido. Ofício, penhora e e-Protocolo
    continuam só leitura.

    **O BDLight recebe um LINK, e não o arquivo** (`ImportarArquivoBDL` leva
    `URLArquivo`; até 5 MB) — o ONR vai buscar o XML num endereço. Esta casa
    não tem endereço público, e por isso a importação não foi construída.

A REDE NUNCA ACONTECE DENTRO DE `db.transaction()` — este módulo nem recebe banco.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import centrais_cred as CRED
import centrais_http as HTTP

NS = "http://tempuri.org/WSOficio"
SOAP = "http://schemas.xmlsoap.org/soap/envelope/"

PRODUCAO = "PRODUCAO"
HOMOLOGACAO = "HOMOLOGACAO"

#: Os dois hosts. Homologação está no manual; produção foi medida em
#: 09/10/2026: os oito `.asmx?wsdl` respondem 200 nos dois, com o
#: `soap:address` apontando para o próprio host.
BASE = {PRODUCAO: "https://wsoficio.onr.org.br",
        HOMOLOGACAO: "https://hml3-wsoficio.onr.org.br"}

#: Os oito serviços, um `.asmx` cada. A grafia (com o «C» maiúsculo de
#: Certidoes) é a do manual e a do servidor.
SERVICOS = {"login": "login.asmx", "bdlight": "bdlight.asmx",
            "oficios": "oficios.asmx", "penhora": "penhoraonline.asmx",
            "certidoes": "Certidoes.asmx", "eprotocolo": "eprotocolo.asmx",
            "matricula": "matriculaonline.asmx", "intimacoes": "intimacoes.asmx"}

#: A ORDEM DOS CAMPOS DE CADA PEDIDO, transcrita do WSDL de produção. Em
#: document/literal a `sequence` é posicional: campo fora de ordem o .NET
#: ignora calado. Há teste que abre o WSDL e compara.
CAMPOS = {
    "LoginUsuarioCertificado": ("SUBJECTCN", "ISSUERO", "PUBLICKEY", "SERIALNUMBER",
                                "VALIDUNTIL", "CPF", "EMAIL", "IDParceiroWS"),
    "ListPedidosOE_V2": ("Hash", "MaxRowPerPage", "PageNumber", "Protocolo",
                         "IDInstituicao", "IDTipoPesquisa", "IDStatus",
                         "DataSolicitacaoInicial", "DataSolicitacaoFinal",
                         "DataRespostaInicial", "DataRespostaFinal"),
    "GetPedidoOE": ("Hash", "IDPedido"),
    "ListPedidosPO": ("Hash", "MaxRowPerPage", "PageNumber", "Protocolo", "IDVara",
                      "IDTipoPedido", "IDStatus", "DataSolicitacaoInicial",
                      "DataSolicitacaoFinal", "DataRespostaInicial",
                      "DataRespostaFinal"),
    "GetPedidoPO": ("Hash", "IDPedido"),
    "ListArquivosXMLBDL": ("Hash", "MaxRowPerPage", "PageNumber", "DataInicial",
                           "DataFinal"),
    # CERTIDÕES A EMITIR (manual 4.43, cap. 3.6, p. 75-90) — 11/10/2026, por
    # ordem do oficial («faça a da onr certidões»). A ordem é a do WSDL de
    # produção (`FONTES_EXTERNAS/onr_wsoficio/producao/Certidoes.wsdl`).
    "ObterXMLSolicitacoes_v6": ("Hash", "Protocolo", "Solicitante", "TipoCertidao",
                                "PesquisaPor", "Status", "TipoResposta", "DataPedidoDe",
                                "DataPedidoAte", "DataConferenciaDe", "DataConferenciaAte"),
    "InformarCustasCertidao": ("Hash", "Protocolo", "ValorCustas"),
    "EnviarAnexoCertidao": ("Hash", "Protocolo", "NomeArquivo", "ArquivoBase64"),
    "EnviarAnexosListCertidao": ("Hash", "Protocolo", "AnexoList"),
    "FinalizarRespostaCertidao": ("Hash", "Protocolo", "Matriculas", "InteresseSocial"),
    "DevolverCertidao": ("Hash", "Protocolo", "Motivo"),
}
#: Campo que é LISTA no contrato: o nome de cada item e os campos dele, em ordem.
LISTAS = {"AnexoList": ("AnexoListCertidao_WSReq", ("NomeArquivo", "ArquivoBase64"))}
SERVICO_DO_METODO = {
    "LoginUsuarioCertificado": "login",
    "ListPedidosOE_V2": "oficios", "GetPedidoOE": "oficios",
    "ListPedidosPO": "penhora", "GetPedidoPO": "penhora",
    "ListArquivosXMLBDL": "bdlight",
    "ObterXMLSolicitacoes_v6": "certidoes", "InformarCustasCertidao": "certidoes",
    "EnviarAnexoCertidao": "certidoes", "EnviarAnexosListCertidao": "certidoes",
    "FinalizarRespostaCertidao": "certidoes", "DevolverCertidao": "certidoes",
}

#: Os status do pedido de certidão (manual 3.6.5) e os tipos de certidão.
STATUS_CERTIDAO = {1: "Em aberto", 2: "Processando", 3: "Respondido",
                   10: "Informar valor dos emolumentos", 11: "Aguardando pagamento",
                   12: "Cancelado", 13: "Pendente de resposta",
                   23: "Cancelado pelo solicitante"}
TIPO_CERTIDAO = {1: "Propriedade / negativa de propriedade", 2: "Vintenária",
                 3: "Matrícula do imóvel", 4: "Transcrição", 5: "Pacto antenupcial",
                 6: "Ônus", 7: "Documento arquivado", 8: "Convenção de condomínio",
                 9: "Livro 3 — garantias", 10: "Outros registros Livro 3 — auxiliar",
                 11: "Outras certidões", 12: "Inteiro teor, ônus e ações",
                 13: "Por quesito", 14: "Negativa de penhor",
                 15: "Ônus reais e ações reipersecutórias", 16: "Usucapião",
                 17: "Propriedade, ônus e alienações",
                 18: "Cadeia dominial (filiação até a origem)",
                 19: "Ações reipersecutórias", 20: "Ônus reais",
                 21: "Situação jurídica atualizada do imóvel", 22: "Agronegócio"}
PESQUISA_POR = {4: "Matrícula", 5: "Transcrição", 6: "Pessoa", 7: "Número de registro",
                8: "Nome dos pactuantes", 9: "Endereço", 10: "Protocolo",
                11: "Nº do registro do Livro 3", 12: "Nome do condomínio",
                13: "Matrícula com complemento", 14: "Transcrição com complemento",
                15: "Busca de garantias"}
EXTENSOES_ACEITAS_NA_CERTIDAO = (".pdf", ".p7s")   # erro 25 do manual

#: Os status do pedido de penhora (manual 3.3.1). O dos ofícios está no 3.5.4.
STATUS_PENHORA = {1: "Aberto", 2: "Respondido", 3: "Devolvido",
                  5: "Finalizado sem pagamento", 7: "Nota de exigência",
                  8: "Reaberto não concluído", 9: "Prenotado",
                  10: "Aguardando pagamento", 11: "Aguardando pagamento — vencido",
                  12: "Não prenotado", 13: "Pagamento efetivado",
                  14: "Registro / averbação"}
TIPO_PEDIDO_PENHORA = {1: "Pedido de matrícula", 2: "Pedido de pessoa",
                       3: "Pedido de penhora"}

TOKENS_VALEM_SEGUNDOS = 8 * 3600
ARQUIVO_DA_CREDENCIAL = "wsoficio.cred"


class WSOficioError(ValueError):
    """Recusa com a frase pronta para o balcão."""


class WSOficioRecusou(WSOficioError):
    """O ONR respondeu RETORNO=false. Guarda o código e a descrição dele."""

    def __init__(self, metodo: str, codigo: Any, descricao: str):
        self.metodo, self.codigo, self.descricao = metodo, codigo, descricao
        super().__init__(f"O ONR recusou {metodo} (código {codigo}): {descricao}")


# ------------------------------------------------------------ a credencial

def caminho_da_credencial(pasta=None) -> Path:
    """Ao lado das outras credenciais das Centrais, FORA do banco."""
    return CRED.caminho(CRED.ONR, pasta).parent / ARQUIVO_DA_CREDENCIAL


def _ler_cred(pasta=None) -> dict:
    c = caminho_da_credencial(pasta)
    if not c.is_file():
        return {}
    try:
        return json.loads(c.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}


def situacao(ambiente: str = PRODUCAO, pasta=None) -> dict:
    """O que está configurado. **Não devolve a chave.**"""
    d = _ler_cred(pasta).get(ambiente) or {}
    return {"ambiente": ambiente,
            "id_parceiro": str(d.get("usuario") or ""),
            "tem_chave": bool(str(d.get("senha") or "").strip()),
            "cpf": str(d.get("cpf") or ""), "email": str(d.get("email") or ""),
            "certificado": str(d.get("certificado") or "")}


def configurar(*, ambiente: str = PRODUCAO, pasta=None, id_parceiro=None, chave=None,
               cpf=None, email=None, certificado=None) -> Path:
    """Grava o que vier (`None` = não mexe). A chave nunca volta por função."""
    tudo = _ler_cred(pasta)
    d = dict(tudo.get(ambiente) or {})
    for campo, valor in (("usuario", id_parceiro), ("senha", chave), ("cpf", cpf),
                         ("email", email), ("certificado", certificado)):
        if valor is not None:
            v = str(valor).strip()
            if campo == "cpf":
                v = re.sub(r"\D", "", v)
            d[campo] = v
    tudo[ambiente] = d
    destino = caminho_da_credencial(pasta)
    destino.write_text(json.dumps(tudo, ensure_ascii=False), encoding="utf-8")
    import centrais_cred as _CRED
    _CRED._so_do_servico(destino)          # a ACL na hora (22/10/2026, M6)
    return destino


_GUID = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")


def par_do_onr_cred_parece_wsoficio(pasta=None) -> bool:
    """O par de produção gravado como «API REST» tem a forma do WSOficio?
    (número inteiro + GUID). Só olha a forma — não devolve nem imprime nada."""
    try:
        d = json.loads(CRED.caminho(CRED.ONR, pasta).read_text(encoding="utf-8"))[PRODUCAO]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return str(d.get("usuario", "")).isdigit() and bool(_GUID.match(str(d.get("senha", ""))))


def trazer_do_onr_cred(pasta=None) -> bool:
    """Copia o par de produção de `onr.cred` para `wsoficio.cred`, se tiver a
    forma do WSOficio. **Copia, não move**: tirar de lá é decisão do oficial."""
    if not par_do_onr_cred_parece_wsoficio(pasta):
        return False
    d = json.loads(CRED.caminho(CRED.ONR, pasta).read_text(encoding="utf-8"))[PRODUCAO]
    configurar(ambiente=PRODUCAO, pasta=pasta, id_parceiro=d["usuario"], chave=d["senha"])
    return True


# ------------------------------------------------------------- o certificado

def certificados_do_windows(cpf: str = "") -> list[dict]:
    """Os certificados do usuário do Windows, **só a parte pública**, na forma
    em que o .NET os lê. Nada aqui toca a chave privada."""
    ps = (r"Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.NotAfter -gt (Get-Date) } | "
          r"ForEach-Object { [pscustomobject]@{ "
          r"SUBJECTCN=([regex]::Match($_.Subject,'CN=([^,]+)')).Groups[1].Value; "
          r"ISSUERO=([regex]::Match($_.Issuer,'O=([^,]+)')).Groups[1].Value; "
          r"EMISSOR=([regex]::Match($_.Issuer,'CN=([^,]+)')).Groups[1].Value; "
          r"PUBLICKEY=$_.GetPublicKeyString(); SERIALNUMBER=$_.GetSerialNumberString(); "
          r"VALIDUNTIL=$_.GetExpirationDateString(); ASSUNTO=$_.Subject } } | ConvertTo-Json")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True,
                       text=True, timeout=60)
    dados = json.loads(r.stdout or "[]")
    lista = dados if isinstance(dados, list) else [dados]
    cpf = re.sub(r"\D", "", cpf or "")
    return [c for c in lista if not cpf or cpf in (c.get("ASSUNTO") or "")]


def dados_do_login(*, cpf: str, email: str, id_parceiro: Any, certificado: dict) -> dict:
    """Os oito campos do `LoginUsuarioCertificado`, conferidos contra os tamanhos
    do manual antes de ir à rede."""
    campos = {"SUBJECTCN": certificado["SUBJECTCN"], "ISSUERO": certificado["ISSUERO"],
              "PUBLICKEY": certificado["PUBLICKEY"],
              "SERIALNUMBER": certificado["SERIALNUMBER"],
              "VALIDUNTIL": certificado["VALIDUNTIL"],
              "CPF": re.sub(r"\D", "", cpf or ""), "EMAIL": (email or "").strip(),
              "IDParceiroWS": id_parceiro}
    limites = {"SUBJECTCN": 100, "ISSUERO": 10, "PUBLICKEY": 1000, "SERIALNUMBER": 100,
               "CPF": 11, "EMAIL": 100}
    for campo, teto in limites.items():
        if not str(campos[campo] or ""):
            raise WSOficioError(f"Falta o {campo} para entrar no Ofício Eletrônico.")
        if len(str(campos[campo])) > teto:
            raise WSOficioError(f"O {campo} passa do tamanho do manual ({teto}).")
    if len(campos["CPF"]) != 11:
        raise WSOficioError("O CPF do usuário do Ofício Eletrônico precisa de 11 dígitos.")
    if not str(id_parceiro or "").strip().isdigit():
        raise WSOficioError("O IDParceiroWS é um número inteiro, dado pelo ONR.")
    return campos


# ----------------------------------------------------------- o hash e o SOAP

def hash_da_mensagem(chave: str, token: str, *, maiusculas: bool = True) -> str:
    """`SHA-1(chave + token)`, UTF-8 (manual, cap. 2). A caixa é A CONFERIR."""
    h = hashlib.sha1((str(chave) + str(token)).encode("utf-8")).hexdigest()
    return h.upper() if maiusculas else h


def envelope(metodo: str, campos: dict) -> bytes:
    """O envelope SOAP 1.1, com os campos NA ORDEM do contrato. Campo que não
    está no contrato é recusado aqui — o .NET o ignoraria calado."""
    ordem = CAMPOS[metodo]
    sobra = set(campos) - set(ordem)
    if sobra:
        raise WSOficioError(f"{metodo} não tem o(s) campo(s) {sorted(sobra)}.")
    partes = []
    for nome in ordem:
        if nome not in campos or campos[nome] is None:
            continue
        valor = campos[nome]
        if isinstance(valor, bool):
            valor = "true" if valor else "false"
        if nome in LISTAS:
            item, ordem_item = LISTAS[nome]
            itens = []
            for d in valor:
                filhos = "".join(f"<{c}>{escape(str(d[c]))}</{c}>" for c in ordem_item
                                 if d.get(c) is not None)
                itens.append(f"<{item}>{filhos}</{item}>")
            partes.append(f"<{nome}>" + "".join(itens) + f"</{nome}>")
            continue
        partes.append(f"<{nome}>{escape(str(valor))}</{nome}>")
    return ('<?xml version="1.0" encoding="utf-8"?>'
            f'<soap:Envelope xmlns:soap="{SOAP}"><soap:Body>'
            f'<{metodo} xmlns="{NS}"><oRequest>{"".join(partes)}</oRequest></{metodo}>'
            "</soap:Body></soap:Envelope>").encode("utf-8")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _para_python(el: ET.Element) -> Any:
    filhos = list(el)
    if not filhos:
        texto = (el.text or "").strip()
        return {"true": True, "false": False}.get(texto, texto)
    nomes = [_local(f.tag) for f in filhos]
    if len(set(nomes)) == 1 and (nomes[0] in ("string", "int")
                                 or nomes[0].endswith("_WSResp")
                                 or _local(el.tag).startswith("ArrayOf")
                                 or len(filhos) > 1):
        return [_para_python(f) for f in filhos]
    return {_local(f.tag): _para_python(f) for f in filhos}


def ler_resposta(metodo: str, texto: str) -> dict:
    """O `<Metodo>Result` como dicionário. Fault SOAP vira erro com a frase dele."""
    try:
        raiz = ET.fromstring(texto)
    except ET.ParseError as erro:
        raise WSOficioError(f"O ONR respondeu algo que não é XML: {texto[:200]!r}") from erro
    falha = raiz.find(f".//{{{SOAP}}}Fault")
    if falha is not None:
        msg = falha.findtext("faultstring") or ET.tostring(falha, encoding="unicode")[:300]
        raise WSOficioError(f"O ONR devolveu falha SOAP em {metodo}: {msg}")
    res = raiz.find(f".//{{{NS}}}{metodo}Result")
    if res is None:
        raise WSOficioError(f"A resposta de {metodo} veio sem {metodo}Result.")
    d = _para_python(res)
    return d if isinstance(d, dict) else {"valor": d}


# --------------------------------------------------------------- a sessão

class Sessao:
    """Uma conversa com o WSOficio: um login, cinco tokens, e o hash de cada chamada.

    `transporte(url, corpo, soap_action) -> (status, texto)` existe para os
    testes; na casa é `centrais_http.requisitar`.
    """

    def __init__(self, *, ambiente: str = PRODUCAO, pasta=None, transporte=None,
                 certificado: dict | None = None, agora=time.time):
        if ambiente not in BASE:
            raise WSOficioError(f"O WSOficio não tem ambiente «{ambiente}».")
        cred = _ler_cred(pasta).get(ambiente) or {}
        if not str(cred.get("usuario") or "").strip() or not str(cred.get("senha") or "").strip():
            raise WSOficioError(
                "Falta a credencial do WSOficio (IDParceiroWS e chave) em "
                f"{caminho_da_credencial(pasta).name}. Ela é pedida ao ONR em "
                "oficioeletronico@onr.org.br.")
        if not cred.get("cpf") or not cred.get("email"):
            raise WSOficioError(
                "Falta dizer qual usuário do Ofício Eletrônico entra: o CPF e o e-mail "
                "com que ele está cadastrado lá.")
        self.ambiente, self._cred, self._agora = ambiente, cred, agora
        self._transporte = transporte or _transporte_da_casa
        self._certificado = certificado
        self._tokens: list[str] = []
        self._tokens_em = 0.0
        self.maiusculas: bool | None = cred.get("hash_maiusculas")
        self.usuario: dict = {}

    # -- rede
    def _bater(self, metodo: str, campos: dict) -> dict:
        servico = SERVICOS[SERVICO_DO_METODO[metodo]]
        url = f"{BASE[self.ambiente]}/{servico}"
        status, texto = self._transporte(url, envelope(metodo, campos), f"{NS}/{metodo}")
        if status >= 500 and "Fault" not in (texto or ""):
            raise WSOficioError(f"O WSOficio respondeu HTTP {status} em {metodo}.")
        return ler_resposta(metodo, texto)

    # -- login
    def entrar(self) -> dict:
        cert = self._certificado
        if cert is None:
            serie = (self._cred.get("certificado") or "").upper()
            opcoes = certificados_do_windows(self._cred["cpf"])
            if serie:
                opcoes = [c for c in opcoes if (c.get("SERIALNUMBER") or "").upper() == serie]
            if not opcoes:
                raise WSOficioError(
                    "Não achei, no Windows deste usuário, um certificado válido do CPF "
                    f"{self._cred['cpf']}" + (f" com a série {serie}" if serie else "") + ".")
            cert = opcoes[0]
        campos = dados_do_login(cpf=self._cred["cpf"], email=self._cred["email"],
                                id_parceiro=self._cred["usuario"], certificado=cert)
        r = self._bater("LoginUsuarioCertificado", campos)
        if r.get("RETORNO") is not True:
            raise WSOficioRecusou("LoginUsuarioCertificado", r.get("CODIGOERRO"),
                                  r.get("ERRODESCRICAO") or "")
        tokens = r.get("Tokens") or []
        self._tokens = list(tokens) if isinstance(tokens, list) else [tokens]
        self._tokens_em = self._agora()
        self.usuario = {k: r.get(k) for k in ("IDUsuario", "IDInstituicao", "Ativo")}
        return dict(self.usuario, tokens=len(self._tokens))

    def _token(self) -> str:
        if not self._tokens or self._agora() - self._tokens_em > TOKENS_VALEM_SEGUNDOS - 300:
            self.entrar()
        if not self._tokens:
            raise WSOficioError("O login do WSOficio não devolveu token.")
        return self._tokens.pop(0)

    def chamar(self, metodo: str, **campos) -> dict:
        """Uma chamada com hash. «Hash inválido» puro (nem usado, nem vencido)
        na primeira vez faz UMA tentativa com a outra caixa — ver o cabeçalho."""
        tentativas = [self.maiusculas] if self.maiusculas is not None else [True, False]
        ultimo = None
        for maiusculas in tentativas:
            h = hash_da_mensagem(self._cred["senha"], self._token(), maiusculas=maiusculas)
            r = self._bater(metodo, dict(campos, Hash=h))
            if r.get("RETORNO") is True:
                self.maiusculas = maiusculas
                return r
            ultimo = WSOficioRecusou(metodo, r.get("CODIGOERRO"), r.get("ERRODESCRICAO") or "")
            descr = (r.get("ERRODESCRICAO") or "").strip().rstrip(".").lower()
            if descr != "hash inválido":
                break
        raise ultimo

    # -- as leituras
    def pedidos_de_oficio(self, *, de: str, ate: str, status: int = -1,
                          pagina: int = 1, por_pagina: int = 100) -> dict:
        return self.chamar("ListPedidosOE_V2", MaxRowPerPage=por_pagina, PageNumber=pagina,
                           Protocolo="", IDInstituicao=-1, IDTipoPesquisa=-1, IDStatus=status,
                           DataSolicitacaoInicial=de, DataSolicitacaoFinal=ate,
                           DataRespostaInicial="", DataRespostaFinal="")

    def pedido_de_oficio(self, id_pedido: int) -> dict:
        return self.chamar("GetPedidoOE", IDPedido=int(id_pedido))

    def pedidos_de_penhora(self, *, de: str, ate: str, status: int = -1, tipo: int = -1,
                           pagina: int = 1, por_pagina: int = 100) -> dict:
        return self.chamar("ListPedidosPO", MaxRowPerPage=por_pagina, PageNumber=pagina,
                           Protocolo="", IDVara=-1, IDTipoPedido=tipo, IDStatus=status,
                           DataSolicitacaoInicial=de, DataSolicitacaoFinal=ate,
                           # MEDIDO EM PRODUÇÃO, 09/10/2026: sem os dois campos de
                           # resposta o serviço estoura NullReferenceException
                           # (PenhoraOnline.asmx.vb:178). Vão presentes e vazios.
                           DataRespostaInicial="", DataRespostaFinal="")

    def pedido_de_penhora(self, id_pedido: int) -> dict:
        return self.chamar("GetPedidoPO", IDPedido=int(id_pedido))

    def arquivos_do_bdlight(self, *, de: str = "", ate: str = "", pagina: int = 1,
                            por_pagina: int = 100) -> dict:
        return self.chamar("ListArquivosXMLBDL", MaxRowPerPage=por_pagina, PageNumber=pagina,
                           DataInicial=de, DataFinal=ate)


    # -- as certidões a emitir (manual 3.6). As quatro últimas MUDAM COISA NO ONR:
    #    quem as chama é a tela, um clique por pedido, e nunca um laço.
    def certidoes_a_emitir(self, *, status: Any = "", protocolo: str = "",
                           de: str = "", ate: str = "") -> dict:
        """O XML do «Certidões a Emitir / Exportar». Código 200 do ONR
        («não foram localizados registros») vira lista vazia, e não erro."""
        try:
            return self.chamar("ObterXMLSolicitacoes_v6", Protocolo=protocolo,
                               Solicitante="", TipoCertidao="", PesquisaPor="",
                               Status=str(status or ""), TipoResposta="",
                               DataPedidoDe=de, DataPedidoAte=ate,
                               DataConferenciaDe="", DataConferenciaAte="")
        except WSOficioRecusou as e:
            if str(e.codigo) == "200":
                return {"RETORNO": True, "XML": "", "vazio": True}
            raise

    def informar_custas_da_certidao(self, protocolo: str, valor: Any) -> dict:
        return self.chamar("InformarCustasCertidao", Protocolo=str(protocolo),
                           ValorCustas=str(valor))

    def enviar_anexos_da_certidao(self, protocolo: str, anexos: list[dict]) -> dict:
        """`anexos`: [{NomeArquivo, ArquivoBase64}], só .pdf ou .p7s."""
        if not anexos:
            raise WSOficioError("Nenhum anexo para enviar.")
        for a in anexos:
            if not str(a.get("NomeArquivo") or "").lower().endswith(EXTENSOES_ACEITAS_NA_CERTIDAO):
                raise WSOficioError("O ONR só aceita anexo .pdf ou .p7s na certidão.")
            if not a.get("ArquivoBase64"):
                raise WSOficioError(f"O anexo {a.get('NomeArquivo')} está vazio.")
        if len(anexos) == 1:
            return self.chamar("EnviarAnexoCertidao", Protocolo=str(protocolo),
                               NomeArquivo=anexos[0]["NomeArquivo"],
                               ArquivoBase64=anexos[0]["ArquivoBase64"])
        return self.chamar("EnviarAnexosListCertidao", Protocolo=str(protocolo),
                           AnexoList=anexos)

    def finalizar_certidao(self, protocolo: str, *, interesse_social: bool,
                           matriculas: str = "") -> dict:
        return self.chamar("FinalizarRespostaCertidao", Protocolo=str(protocolo),
                           Matriculas=matriculas or None,
                           InteresseSocial=bool(interesse_social))

    def devolver_certidao(self, protocolo: str, motivo: str) -> dict:
        return self.chamar("DevolverCertidao", Protocolo=str(protocolo), Motivo=motivo)


def _transporte_da_casa(url: str, corpo: bytes, acao: str) -> tuple[int, str]:
    r = HTTP.requisitar("POST", url, corpo=corpo, cabecalhos={
        "Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{acao}"',
        "Accept": "text/xml"}, prazo=60, tentativas=0)
    return r.status, r.texto


def main(argv=None) -> int:
    """Para o oficial rodar à mão: `python onr_wsoficio.py --testar`.

    Só entra e lista o que chegou nos últimos 30 dias — não responde nada."""
    import argparse
    import sys
    from datetime import date, timedelta
    ap = argparse.ArgumentParser(description="WSOficio do ONR — só leitura.")
    ap.add_argument("--testar", action="store_true", help="entra e lista os pedidos")
    ap.add_argument("--ambiente", default=PRODUCAO, choices=sorted(BASE))
    ap.add_argument("--cpf")
    ap.add_argument("--email")
    ap.add_argument("--certificado", help="número de série do certificado a usar")
    ap.add_argument("--trazer-do-onr-cred", action="store_true",
                    help="copia o par IDParceiroWS/chave gravado como «ONR» em produção")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                   # noqa: BLE001
        pass
    if a.trazer_do_onr_cred:
        print("par copiado de onr.cred:", trazer_do_onr_cred())
    if a.cpf or a.email or a.certificado:
        configurar(ambiente=a.ambiente, cpf=a.cpf, email=a.email, certificado=a.certificado)
    print("situação:", situacao(a.ambiente))
    if not a.testar:
        return 0
    s = Sessao(ambiente=a.ambiente)
    print("login:", s.entrar())
    hoje = date.today()
    de = (hoje - timedelta(days=30)).isoformat()
    for nome, f in (("ofícios", s.pedidos_de_oficio), ("penhora online", s.pedidos_de_penhora)):
        r = f(de=de, ate=hoje.isoformat())
        print(f"{nome}: {r.get('QtdeRegistros')} pedido(s) desde {de}")
    if s.maiusculas is not None:
        configurar(ambiente=a.ambiente, certificado=None)
        tudo = _ler_cred()
        tudo.setdefault(a.ambiente, {})["hash_maiusculas"] = s.maiusculas
        caminho_da_credencial().write_text(json.dumps(tudo, ensure_ascii=False),
                                           encoding="utf-8")
        import centrais_cred as _CRED
        _CRED._so_do_servico(caminho_da_credencial())
        print("hash em", "MAIÚSCULAS" if s.maiusculas else "minúsculas", "(gravado)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
