"""O TRANSPORTE SOAP DA CRC NACIONAL — `cargaRegistrosCompleto.cfc`.

Ordem do oficial em 10/09/2026: *«vamos ficar na integração, para envio
automático de cargas e de certidão automática»*, depois **«siga»** — autorizando
construir o cliente SOAP com a estrutura medida por analogia num endpoint
irmão do mesmo servidor, já que o endereço real está fora do alcance deste
sandbox (confirmado: `curl` e `WebFetch` para `wsh.registrocivil.org.br`
esgotam o tempo).

O QUE ESTÁ MEDIDO, DIRETO DO MANUAL (`FONTES_EXTERNAS/CRC_manual.txt`, p. 5-6)
    - Os dois endereços, exatos:
      `http://wsh.registrocivil.org.br/cargaRegistrosCompleto.cfc?wsdl`
      (homologação) e `https://ws.registrocivil.org.br/cargaRegistrosCompleto.cfc?wsdl`
      (produção).
    - **Homologação NÃO valida a assinatura**: «não será feita a validação da
      assinatura do arquivo como um usuário cadastrado». Produção valida.
      Isso é o que torna um teste em homologação possível MESMO com um
      WS-Security montado sem confirmação byte a byte contra um servidor real.
    - **Autenticação é WS-Security, X.509 Token Profile**: o certificado do
      usuário vai no cabeçalho do pacote SOAP (`BinarySecurityToken`); o
      próprio pacote é assinado com **XML Signature** (não é o CMS do
      `crc_cms.py` — são dois mecanismos distintos, ver abaixo); e o
      timestamp de segurança fica no mesmo cabeçalho.
    - O XML de carga vai **assinado com e-CPF e em BASE64** — este é o
      `crc_cms.assinar_anexado()`, que já existe e já foi validado (CMS
      `SignedData` anexado, a mesma forma que `assinatura_digital.py` lê).

O QUE É MEDIDO POR ANALOGIA, E NÃO CONFIRMADO NESTE ENDPOINT ESPECÍFICO
    A forma do envelope SOAP em si (`rpc/encoded`, parâmetro único do tipo
    `anyType`, `SOAPAction` vazio, falha como `CFCInvocationException`) foi
    medida no endpoint IRMÃO `enviarCertidao.cfc?wsdl`, no mesmo servidor
    ColdFusion — arquivado no Wayback Machine e lido em 10/09/2026, porque o
    `cargaRegistrosCompleto.cfc?wsdl` nunca foi arquivado com o `?wsdl`. **É a
    mesma casa (mesmo servidor, mesma tecnologia CFC), e não a mesma porta.**
    O nome do parâmetro único do `cargaRegistrosCompleto` **não está medido**
    — nenhuma fonte desta casa o declara — e por isso `PARAMETRO_DA_CARGA`
    fica marcado como tal: é o palpite mais razoável (o nome do próprio
    método, em minúscula, como o ColdFusion costuma gerar para `anyType` sem
    documentação), e SÓ um envio de teste em homologação confirma.

DUAS ASSINATURAS DIFERENTES, PARA DUAS COISAS DIFERENTES
    1. O CONTEÚDO (o XML da carga) é assinado por `crc_cms.assinar_anexado()`
       — CMS `SignedData`, a forma que este projeto já mede e já lê.
    2. O PACOTE SOAP é assinado por ESTE módulo — XML Signature (RFC do
       W3C), porque é isso que WS-Security X.509 Token Profile exige: um
       `ds:Signature` sobre o `wsu:Timestamp` e o `soap:Body`, com C14N
       exclusivo e RSA-SHA256. As duas usam a MESMA chave do A3 (a mesma
       chamada a `crc_a3.assinar()`), mas produzem bytes diferentes porque
       assinam mensagens diferentes, em formatos diferentes.

    **A ASSINATURA XML NÃO FOI CONFERIDA CONTRA SERVIDOR REAL NENHUM** — ao
    contrário do CMS, que se conferiu sozinho (assina, reconstrói, verifica
    com uma chave de teste). XML Signature com C14N exclusivo depende de
    detalhes finos (namespaces, ordem de atributos) que só um servidor real
    confirma. É por isso que a homologação, que **não valida a assinatura**,
    é o primeiro teste possível — e não uma prova de que o formato está
    certo, e sim de que o TRANSPORTE (envelope, WS-Security bem-formado,
    resposta) funciona.
"""
from __future__ import annotations

import base64
import hashlib
import http.client

import centrais_trava_sandbox as TRAVA
import re
import ssl
import time
import urllib.parse
from typing import Any
from xml.sax import saxutils

from lxml import etree

import crc_a3
import crc_carga
import crc_cms

# OS DOIS ENDEREÇOS, exatos do manual (p. 5-6). **`http` de homologação vira
# `https` por decisão da casa** — a mesma do selador e da CRA21: quando a
# rede é o meio, quem decide o transporte é a casa, e a senha/certificado não
# viaja em texto puro. O manual não diz que homologação aceita https, mas
# ela é a mesma tecnologia (ColdFusion) do `wsh.` da CRA — HTTPS costuma
# funcionar mesmo quando não anunciado; se não funcionar, o erro de conexão
# aparece na hora, e não vaza credencial.
HOMOLOGACAO, PRODUCAO = "HOMOLOGACAO", "PRODUCAO"

ENDERECO_DO_AMBIENTE: dict[str, str] = {
    HOMOLOGACAO: "https://wsh.registrocivil.org.br/cargaRegistrosCompleto.cfc",
    PRODUCAO: "https://ws.registrocivil.org.br/cargaRegistrosCompleto.cfc",
}

# O NOME DO MÉTODO SOAP. Confirmado pelo próprio nome do arquivo `.cfc`.
OPERACAO = "cargaRegistrosCompleto"

# **A CONFERIR** — o nome do parâmetro único (`anyType`) não está medido
# nesta casa. Ver o cabeçalho do módulo.
PARAMETRO_DA_CARGA = "arquivoBase64"

PRAZO_PADRAO = 180
VALIDADE_DO_TIMESTAMP_SEGUNDOS = 300

_NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
_NS_WSSE = ("http://docs.oasis-open.org/wss/2004/01/oasis-200401-"
            "wss-wssecurity-secext-1.0.xsd")
_NS_WSU = ("http://docs.oasis-open.org/wss/2004/01/oasis-200401-"
           "wss-wssecurity-utility-1.0.xsd")
_NS_DS = "http://www.w3.org/2000/09/xmldsig#"
_NS_C14N_EXC = "http://www.w3.org/2001/10/xml-exc-c14n#"
_TIPO_X509_DER = ("http://docs.oasis-open.org/wss/2004/01/oasis-200401-"
                  "wss-x509-token-profile-1.0#X509v3")
_TIPO_VALUE_BASE64 = ("http://docs.oasis-open.org/wss/2004/01/oasis-200401-"
                      "wss-soap-message-security-1.0#Base64Binary")


class CrcSoapError(RuntimeError):
    """Falha de transporte ou de credencial, com a frase para o balcão."""


class CrcSoapRecusou(CrcSoapError):
    """A Central respondeu, e respondeu não. O motivo dela vem junto."""


def endereco_do_ambiente(ambiente: Any) -> str:
    nome = str(ambiente or "").strip().upper()
    return ENDERECO_DO_AMBIENTE.get(nome, ENDERECO_DO_AMBIENTE[HOMOLOGACAO])


def _partes(endereco: str) -> tuple[str, int, str]:
    p = urllib.parse.urlsplit(endereco)
    if p.scheme != "https":
        raise CrcSoapError(
            f"O endereço da CRC tem de ser https, e veio «{endereco}». O "
            f"certificado do delegatário não pode viajar em texto puro.")
    return p.hostname or "", p.port or 443, p.path or "/"


def _c14n_exc(elemento) -> bytes:
    """C14N exclusivo, sem comentários — a forma que XML Signature exige."""
    return etree.tostring(elemento, method="c14n", exclusive=True,
                          with_comments=False)


def _digest_sha256_b64(dados: bytes) -> str:
    return base64.b64encode(hashlib.sha256(dados).digest()).decode("ascii")


def _montar_seguranca(*, driver: str, pin: str,
                      agora: float | None = None) -> str:
    """O cabeçalho `wsse:Security`: token, timestamp e assinatura do pacote.

    **O CERTIFICADO SAI DA MESMA CHAMADA QUE ASSINA** — `crc_a3.assinar()`
    devolve os dois juntos, e por isso esta função não recebe o certificado
    como parâmetro: pedi-lo à parte exigiria uma segunda ida ao token só
    para ler o certificado, e o PIN é pedido a cada chamada.

    **ASSINA O TIMESTAMP E FICA NISSO** — não assina o corpo. O manual diz
    que «a assinatura do próprio pacote» e o timestamp «devem estar contidos
    no mesmo local» (o cabeçalho), sem detalhar o que exatamente entra na
    assinatura; o Timestamp sozinho é o mínimo que todo perfil WS-Security
    X.509 assina, e é o que se confirma primeiro. **Ampliar para assinar
    também o Body é o próximo passo, se a Central recusar por isso** — e a
    recusa, em homologação, não vem da assinatura (ela não é validada ali).
    """
    agora = agora if agora is not None else time.time()
    criado = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(agora))
    expira = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ",
        time.gmtime(agora + VALIDADE_DO_TIMESTAMP_SEGUNDOS))

    timestamp_xml = (
        f'<wsu:Timestamp xmlns:wsu="{_NS_WSU}" wsu:Id="ts-1">'
        f'<wsu:Created>{criado}</wsu:Created>'
        f'<wsu:Expires>{expira}</wsu:Expires>'
        f'</wsu:Timestamp>')
    timestamp_el = etree.fromstring(timestamp_xml.encode())
    digest = _digest_sha256_b64(_c14n_exc(timestamp_el))

    signed_info_xml = (
        '<ds:SignedInfo xmlns:ds="' + _NS_DS + '">'
        f'<ds:CanonicalizationMethod Algorithm="{_NS_C14N_EXC}"/>'
        '<ds:SignatureMethod Algorithm='
        '"http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>'
        '<ds:Reference URI="#ts-1">'
        f'<ds:Transforms><ds:Transform Algorithm="{_NS_C14N_EXC}"/>'
        '</ds:Transforms>'
        '<ds:DigestMethod Algorithm='
        '"http://www.w3.org/2001/04/xmlenc#sha256"/>'
        f'<ds:DigestValue>{digest}</ds:DigestValue>'
        '</ds:Reference>'
        '</ds:SignedInfo>')
    signed_info_el = etree.fromstring(signed_info_xml.encode())
    signed_info_c14n = _c14n_exc(signed_info_el)

    resultado = crc_a3.assinar(signed_info_c14n, driver=driver, pin=pin)
    assinatura_b64 = resultado["assinatura_b64"]
    certificado_der = base64.b64decode(resultado["certificado_b64"])
    token_b64 = base64.b64encode(certificado_der).decode("ascii")

    return (
        f'<wsse:Security xmlns:wsse="{_NS_WSSE}" '
        'soap:mustUnderstand="1">'
        f'<wsse:BinarySecurityToken wsu:Id="cert-1" '
        f'xmlns:wsu="{_NS_WSU}" '
        f'ValueType="{_TIPO_X509_DER}" '
        f'EncodingType="{_TIPO_VALUE_BASE64}">{token_b64}'
        '</wsse:BinarySecurityToken>'
        + signed_info_xml.replace(
            '<ds:SignedInfo xmlns:ds="' + _NS_DS + '">',
            f'<ds:Signature xmlns:ds="{_NS_DS}"><ds:SignedInfo>')
        + f'<ds:SignatureValue>{assinatura_b64}</ds:SignatureValue>'
        '<ds:KeyInfo><wsse:SecurityTokenReference>'
        '<wsse:Reference URI="#cert-1" '
        f'ValueType="{_TIPO_X509_DER}"/>'
        '</wsse:SecurityTokenReference></ds:KeyInfo>'
        '</ds:Signature>'
        + timestamp_xml
        + '</wsse:Security>'
    )


def envelope(conteudo_base64: str, *, driver: str, pin: str) -> bytes:
    """O envelope SOAP inteiro: `wsse:Security` no cabeçalho, a carga no corpo.

    **A FORMA DO CORPO É MEDIDA POR ANALOGIA** (RPC/encoded, parâmetro
    único) — ver o cabeçalho do módulo.
    """
    seguranca = _montar_seguranca(driver=driver, pin=pin)
    corpo_escapado = saxutils.escape(conteudo_base64)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<soap:Envelope xmlns:soap="{_NS_SOAP}" '
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f'<soap:Header>{seguranca}</soap:Header>'
        '<soap:Body>'
        f'<ns1:{OPERACAO} xmlns:ns1="cargaRegistrosCompleto" '
        'soap:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        f'<{PARAMETRO_DA_CARGA} xsi:type="xsd:string">{corpo_escapado}'
        f'</{PARAMETRO_DA_CARGA}>'
        f'</ns1:{OPERACAO}>'
        '</soap:Body></soap:Envelope>'
    ).encode()


_RETORNO = re.compile(r"<return[^>]*>(.*?)</return>", re.DOTALL)
_FALHA = re.compile(r"<faultstring[^>]*>(.*?)</faultstring>", re.DOTALL)


def ler_resposta(texto: str) -> str:
    """O `return` da resposta, ou a frase do balcão. Não interpreta o conteúdo.

    **A FALHA CFC VEM COMO `CFCInvocationException`, medida no endpoint
    irmão** — e chega com HTTP 500, não 200.
    """
    falha = _FALHA.search(texto)
    if falha:
        raise CrcSoapRecusou(
            f"A CRC recusou a carga: {saxutils.unescape(falha.group(1))}")
    achado = _RETORNO.search(texto)
    if achado is None:
        # Sem `<return>` e sem falha declarada — resposta em forma que este
        # módulo não reconhece. Devolve o texto cru para quem for investigar,
        # em vez de inventar que deu certo.
        return texto
    return saxutils.unescape(achado.group(1))


def _bater(ambiente: str, corpo: bytes, *, prazo: int = PRAZO_PADRAO) -> str:
    hospedeiro, porta, caminho = _partes(endereco_do_ambiente(ambiente))
    # Trava sandbox: CRC so no simulador :8917 (ou recusa).
    hospedeiro, porta = TRAVA.destino_seguro(hospedeiro, porta)
    cabecas = {
        "Content-Type": "text/xml; charset=utf-8",
        # **SOAPAction VAZIO** — medido no endpoint irmão `enviarCertidao.cfc`,
        # que é como o ColdFusion costuma gerar operações sem WSDL anotado.
        "SOAPAction": '""',
        "User-Agent": "CartorioGestao",
        "Content-Length": str(len(corpo)),
    }
    contexto = ssl.create_default_context()
    conexao = None
    try:
        conexao = http.client.HTTPSConnection(
            hospedeiro, porta, timeout=prazo, context=contexto)
        conexao.request("POST", caminho, body=corpo, headers=cabecas)
        r = conexao.getresponse()
        bruto = r.read()
        return bruto.decode("utf-8", errors="replace")
    except (OSError, ssl.SSLError, http.client.HTTPException) as erro:
        raise CrcSoapError(
            f"Não consegui falar com a CRC em {hospedeiro}: {erro}. Confira "
            f"a internet da serventia e tente de novo; nada foi enviado.") from erro
    finally:
        if conexao is not None:
            conexao.close()


def enviar_carga(con, assentos: list[int], *, cns: str, driver: str,
                 pin: str, ambiente: str = HOMOLOGACAO) -> dict:
    """Monta, assina e envia a carga dos `assentos` dados. Faz tudo.

    Devolve `{"enviado", "retidos", "a_arrumar", "resposta"}`. **Não envia
    nada se não houver o que enviar** — carga vazia não vira chamada de
    rede. `retidos` e `a_arrumar` vêm de `crc_carga.montar()`, sem alteração:
    são os assentos que ficaram de fora e o porquê, e os que foram mas
    precisam de conserto.
    """
    montado = crc_carga.montar(con, assentos, cns=cns)
    if montado["quantos"] == 0:
        raise CrcSoapError(
            "Nenhum dos assentos indicados pôde entrar na carga — veja "
            "«retidos» para o motivo de cada um. Nada foi enviado.")

    xml_bytes = montado["xml"].encode("utf-8")
    envelope_cms = crc_cms.assinar_anexado(xml_bytes, driver=driver, pin=pin)
    conteudo_base64 = base64.b64encode(envelope_cms).decode("ascii")

    # **DUAS CHAMADAS AO TOKEN, E NÃO UMA** — uma para o CMS do conteúdo
    # (dentro de `crc_cms.assinar_anexado`, acima) e outra para o
    # `ds:Signature` do pacote SOAP (dentro de `envelope`, abaixo). São
    # assinaturas de bytes diferentes, em formatos diferentes; a mesma
    # chave assina as duas, mas nenhuma reaproveita o resultado da outra.
    # O PIN é pedido pelo delegatário a cada uma.
    corpo = envelope(conteudo_base64, driver=driver, pin=pin)
    texto_resposta = _bater(ambiente, corpo)
    resposta = ler_resposta(texto_resposta)

    return {"enviado": montado["quantos"], "retidos": montado["retidos"],
            "a_arrumar": montado["a_arrumar"], "resposta": resposta}
