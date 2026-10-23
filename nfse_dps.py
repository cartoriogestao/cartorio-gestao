"""A DPS DA NFS-e NACIONAL — o XML que vai à Sefin, e a assinatura dele.

POR QUE EXISTE (LG01, 19/10/2026)
    O oficial precisa emitir NFS-e dos emolumentos, uma por cliente, e a
    prefeitura usa o EMISSOR NACIONAL (gov.br/nfse — confirmado por ele em
    19/10). No padrão nacional quem emite não manda a nota: manda a
    **Declaração de Prestação de Serviço (DPS)**, assinada com o certificado A1
    da serventia, e a Sefin Nacional devolve a NFS-e com a chave de acesso.

    Este módulo só MONTA e ASSINA. Não fala com rede, não abre banco, não lê
    configuração: recebe os dados prontos e devolve bytes. É por isso que ele
    se testa sozinho — e é por isso que um provedor municipal, no dia em que a
    prefeitura trocar de sistema, pode ignorá-lo sem mexer no resto
    (`nfse_provedor`).

O LEIAUTE
    O da DPS versão 1.00, namespace `http://www.sped.fazenda.gov.br/nfse`, com
    os grupos mínimos de um serviço tributável no município: prestador,
    tomador, serviço (código de tributação nacional — item 21.01 da LC 116,
    serviços de registros públicos, cartorários e notariais) e valores. Os
    campos opcionais que a casa não usa ficam de fora de propósito: campo que
    vai vazio é campo que a Sefin recusa.

    **CONFERIR NA HOMOLOGAÇÃO** (a «produção restrita» da Sefin) antes de ligar
    a produção: o algoritmo da assinatura (`ALGORITMO_*`), a forma do `Id` do
    pedido de cancelamento e se o município aceita a alíquota informada na
    DPS. Estão escritos aqui pelo manual do contribuinte que se conhecia em
    19/10/2026, e o manual muda por nota técnica.

A ASSINATURA
    XMLDSig envelopada, sobre o elemento `infDPS` (referência `#Id`), com C14N
    inclusiva e RSA com SHA-256, e o certificado inteiro em `X509Certificate`.
    A chave do A1 só existe na memória enquanto se assina: ela vem do `.pfx`
    que mora fora do banco (`nfse.ler_certificado`) e não é gravada em lugar
    nenhum por aqui.
"""
from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from lxml import etree

NS = "http://www.sped.fazenda.gov.br/nfse"
NS_DS = "http://www.w3.org/2000/09/xmldsig#"
VERSAO = "1.00"

ALGORITMO_C14N = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
ALGORITMO_ENVELOPADA = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
ALGORITMO_ASSINATURA = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
ALGORITMO_RESUMO = "http://www.w3.org/2001/04/xmlenc#sha256"

# tpAmb da DPS: 1 = produção, 2 = homologação (produção restrita).
AMBIENTES = {"producao": "1", "homologacao": "2"}

# Evento de cancelamento da NFS-e e os motivos que o leiaute aceita.
EVENTO_CANCELAMENTO = "101101"
MOTIVOS_DE_CANCELAMENTO = {
    "1": "Erro na emissão",
    "2": "Serviço não prestado",
    "9": "Outros",
}

LIMITE_DESCRICAO = 2000


class DpsError(ValueError):
    """Dado que não cabe no leiaute, com a frase pronta para a tela."""


@dataclass(frozen=True)
class Prestador:
    documento: str            # CNPJ da serventia ou CPF do delegatário
    inscricao_municipal: str
    municipio: str            # código IBGE, 7 dígitos
    optante_simples: str = "1"     # opSimpNac: 1 = não optante
    regime_especial: str = "4"     # regEspTrib: 4 = notário ou registrador


@dataclass(frozen=True)
class Tomador:
    documento: str
    nome: str
    cep: str = ""
    municipio: str = ""
    logradouro: str = ""
    numero: str = ""
    complemento: str = ""
    bairro: str = ""
    email: str = ""

    @property
    def tem_endereco(self) -> bool:
        return all((self.cep, self.municipio, self.logradouro, self.numero,
                    self.bairro))


@dataclass(frozen=True)
class Servico:
    codigo_tributacao: str    # cTribNac, 6 dígitos (210101 = item 21.01)
    descricao: str
    valor_centavos: int
    aliquota: str = ""        # «5,00» por cento; vazio = o município decide
    codigo_municipal: str = ""


def digitos(valor: Any) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def valor_decimal(centavos: int) -> str:
    """Centavos em «1234.56», que é como o leiaute escreve dinheiro."""
    c = int(centavos)
    return f"{'-' if c < 0 else ''}{abs(c) // 100}.{abs(c) % 100:02d}"


def aliquota_decimal(aliquota: Any) -> str:
    """«5,00» ou «5» em «5.00». Vazio fica vazio."""
    texto = str(aliquota or "").strip().replace("%", "").replace(",", ".")
    if not texto:
        return ""
    try:
        numero = float(texto)
    except ValueError as erro:
        raise DpsError(f"Alíquota do ISS ilegível: «{aliquota}».") from erro
    if not 0 < numero <= 5:
        # LC 116, art. 8º, II: o máximo é 5%; o mínimo da LC 157 é 2%.
        raise DpsError(f"Alíquota do ISS fora da lei: «{aliquota}» (máximo 5%).")
    return f"{numero:.2f}"


def _texto(valor: Any, limite: int) -> str:
    """Uma linha só, sem caractere de controle, no tamanho do leiaute."""
    limpo = re.sub(r"[\x00-\x1f\x7f]", " ", str(valor or ""))
    return " ".join(limpo.split())[:limite]


def id_da_dps(municipio: str, documento_prestador: str, serie: Any,
              numero: Any) -> str:
    """O `Id` da DPS: «DPS» + município + tipo e número da inscrição + série + número.

    É ele que torna o reenvio idempotente: a mesma DPS mandada duas vezes tem
    o mesmo `Id`, e a Sefin não emite a segunda nota — responde que ela já
    existe, e a casa consulta a chave (`nfse.enviar`).
    """
    mun = digitos(municipio)
    doc = digitos(documento_prestador)
    if len(mun) != 7:
        raise DpsError("O município da serventia precisa do código IBGE de 7 dígitos.")
    if len(doc) not in (11, 14):
        raise DpsError("O documento do prestador precisa ser CPF ou CNPJ.")
    tipo = "1" if len(doc) == 11 else "2"
    serie_d = digitos(serie)
    if not serie_d or len(serie_d) > 5:
        raise DpsError("A série da DPS é um número de até 5 dígitos.")
    return (f"DPS{mun}{tipo}{doc.zfill(14)}{serie_d.zfill(5)}"
            f"{int(numero):015d}")


def _sub(pai, nome: str, texto: Any = None):
    el = etree.SubElement(pai, f"{{{NS}}}{nome}")
    if texto is not None:
        el.text = str(texto)
    return el


def _documento(pai, documento: str) -> None:
    doc = digitos(documento)
    if len(doc) == 11:
        _sub(pai, "CPF", doc)
    elif len(doc) == 14:
        _sub(pai, "CNPJ", doc)
    else:
        raise DpsError("CPF ou CNPJ com número de dígitos errado.")


def _data_hora(quando: datetime) -> str:
    """«2026-10-19T10:00:00-03:00»: o leiaute exige o fuso."""
    if quando.tzinfo is None:
        quando = quando.astimezone()
    return quando.replace(microsecond=0).isoformat()


def montar_dps(*, ambiente: str, emitida_em: datetime, serie: Any, numero: int,
               prestador: Prestador, tomador: Tomador, servico: Servico,
               versao_aplicativo: str = "CartorioGestao") -> bytes:
    """O XML da DPS, SEM assinatura. Não grava nada."""
    if ambiente not in AMBIENTES:
        raise DpsError(f"Ambiente desconhecido: «{ambiente}».")
    if int(servico.valor_centavos) <= 0:
        raise DpsError("Sem valor de serviço não há nota a emitir.")
    codigo = digitos(servico.codigo_tributacao)
    if len(codigo) != 6:
        raise DpsError("O código de tributação nacional tem 6 dígitos "
                       "(o item 21.01 da LC 116 é 210101).")
    nome = _texto(tomador.nome, 300)
    if not nome:
        raise DpsError("O tomador precisa de nome.")
    raiz = etree.Element(f"{{{NS}}}DPS", nsmap={None: NS})
    raiz.set("versao", VERSAO)
    inf = _sub(raiz, "infDPS")
    inf.set("Id", id_da_dps(prestador.municipio, prestador.documento, serie, numero))
    _sub(inf, "tpAmb", AMBIENTES[ambiente])
    _sub(inf, "dhEmi", _data_hora(emitida_em))
    _sub(inf, "verAplic", _texto(versao_aplicativo, 20))
    _sub(inf, "serie", digitos(serie))
    _sub(inf, "nDPS", int(numero))
    _sub(inf, "dCompet", emitida_em.date().isoformat())
    _sub(inf, "tpEmit", "1")              # 1 = o próprio prestador emite
    _sub(inf, "cLocEmi", digitos(prestador.municipio))

    prest = _sub(inf, "prest")
    _documento(prest, prestador.documento)
    if digitos(prestador.inscricao_municipal):
        _sub(prest, "IM", digitos(prestador.inscricao_municipal))
    reg = _sub(prest, "regTrib")
    _sub(reg, "opSimpNac", digitos(prestador.optante_simples) or "1")
    _sub(reg, "regEspTrib", digitos(prestador.regime_especial) or "0")

    toma = _sub(inf, "toma")
    _documento(toma, tomador.documento)
    _sub(toma, "xNome", nome)
    if tomador.tem_endereco:
        end = _sub(toma, "end")
        nac = _sub(end, "endNac")
        _sub(nac, "cMun", digitos(tomador.municipio))
        _sub(nac, "CEP", digitos(tomador.cep))
        _sub(end, "xLgr", _texto(tomador.logradouro, 255))
        _sub(end, "nro", _texto(tomador.numero, 60))
        if _texto(tomador.complemento, 156):
            _sub(end, "xCpl", _texto(tomador.complemento, 156))
        _sub(end, "xBairro", _texto(tomador.bairro, 60))
    if _texto(tomador.email, 80):
        _sub(toma, "email", _texto(tomador.email, 80))

    serv = _sub(inf, "serv")
    loc = _sub(serv, "locPrest")
    _sub(loc, "cLocPrestacao", digitos(prestador.municipio))
    cserv = _sub(serv, "cServ")
    _sub(cserv, "cTribNac", codigo)
    if digitos(servico.codigo_municipal):
        _sub(cserv, "cTribMun", digitos(servico.codigo_municipal)[:3])
    descricao = _texto(servico.descricao, LIMITE_DESCRICAO)
    if not descricao:
        raise DpsError("O serviço precisa de descrição.")
    _sub(cserv, "xDescServ", descricao)

    valores = _sub(inf, "valores")
    _sub(_sub(valores, "vServPrest"), "vServ", valor_decimal(servico.valor_centavos))
    trib = _sub(valores, "trib")
    mun = _sub(trib, "tribMun")
    _sub(mun, "tribISSQN", "1")            # 1 = operação tributável
    _sub(mun, "tpRetISSQN", "1")           # 1 = não retido: o delegatário recolhe
    aliquota = aliquota_decimal(servico.aliquota)
    if aliquota:
        _sub(mun, "pAliq", aliquota)
    _sub(_sub(trib, "totTrib"), "indTotTrib", "0")
    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8")


def id_do_cancelamento(chave: str, sequencia: int = 1) -> str:
    """«PRE» + chave da NFS-e + código do evento + número do pedido."""
    return f"PRE{digitos(chave)}{EVENTO_CANCELAMENTO}{int(sequencia):03d}"


def montar_cancelamento(*, ambiente: str, quando: datetime, autor: str,
                        chave: str, motivo: str, justificativa: str,
                        sequencia: int = 1,
                        versao_aplicativo: str = "CartorioGestao") -> bytes:
    """O pedido de registro do evento de cancelamento, SEM assinatura."""
    if motivo not in MOTIVOS_DE_CANCELAMENTO:
        raise DpsError("Motivo de cancelamento desconhecido.")
    texto = _texto(justificativa, 255)
    if len(texto) < 15:
        raise DpsError("A justificativa do cancelamento precisa de pelo menos "
                       "15 letras: é ela que a prefeitura lê.")
    if len(digitos(chave)) != 50:
        raise DpsError("A chave de acesso da NFS-e tem 50 dígitos.")
    raiz = etree.Element(f"{{{NS}}}pedRegEvento", nsmap={None: NS})
    raiz.set("versao", VERSAO)
    inf = _sub(raiz, "infPedReg")
    inf.set("Id", id_do_cancelamento(chave, sequencia))
    _sub(inf, "tpAmb", AMBIENTES[ambiente])
    _sub(inf, "verAplic", _texto(versao_aplicativo, 20))
    _sub(inf, "dhEvento", _data_hora(quando))
    doc = digitos(autor)
    _sub(inf, "CPFAutor" if len(doc) == 11 else "CNPJAutor", doc)
    _sub(inf, "chNFSe", digitos(chave))
    _sub(inf, "nPedRegEvento", int(sequencia))
    ev = _sub(inf, f"e{EVENTO_CANCELAMENTO}")
    _sub(ev, "xDesc", "Cancelamento de NFS-e")
    _sub(ev, "cMotivo", motivo)
    _sub(ev, "xMotivo", texto)
    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8")


# ---------------------------------------------------------------- assinatura

@dataclass(frozen=True)
class CertificadoA1:
    """A chave e o certificado do A1, só na memória."""
    chave: Any
    certificado: Any

    @property
    def titular(self) -> str:
        from cryptography.x509.oid import NameOID
        nomes = self.certificado.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        return nomes[0].value if nomes else ""

    @property
    def valido_ate(self) -> datetime:
        return self.certificado.not_valid_after_utc

    @property
    def valido_desde(self) -> datetime:
        return self.certificado.not_valid_before_utc


def abrir_pfx(conteudo: bytes, senha: str) -> CertificadoA1:
    """Abre o `.pfx` com a senha. Erro de senha vira frase, sem a senha."""
    from cryptography.hazmat.primitives.serialization import pkcs12
    try:
        chave, cert, _cadeia = pkcs12.load_key_and_certificates(
            conteudo, (senha or "").encode("utf-8"))
    except (ValueError, TypeError) as erro:
        raise DpsError("Não consegui abrir o certificado A1: a senha não "
                       "confere ou o arquivo não é um .pfx.") from erro
    if chave is None or cert is None:
        raise DpsError("O arquivo do certificado não traz a chave e o certificado juntos.")
    return CertificadoA1(chave=chave, certificado=cert)


def _c14n(elemento) -> bytes:
    return etree.tostring(elemento, method="c14n", exclusive=False,
                          with_comments=False)


def assinar(xml: bytes, certificado: CertificadoA1) -> bytes:
    """Assina o primeiro filho da raiz (`infDPS` ou `infPedReg`) pelo `Id`."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    raiz = etree.fromstring(xml)
    alvo = raiz[0]
    ident = alvo.get("Id")
    if not ident:
        raise DpsError("O XML não tem o `Id` que a assinatura referencia.")
    resumo = base64.b64encode(hashlib.sha256(_c14n(alvo)).digest()).decode("ascii")

    ds = f"{{{NS_DS}}}"
    assinatura = etree.SubElement(raiz, f"{ds}Signature", nsmap={None: NS_DS})
    info = etree.SubElement(assinatura, f"{ds}SignedInfo")
    etree.SubElement(info, f"{ds}CanonicalizationMethod").set("Algorithm", ALGORITMO_C14N)
    etree.SubElement(info, f"{ds}SignatureMethod").set("Algorithm", ALGORITMO_ASSINATURA)
    ref = etree.SubElement(info, f"{ds}Reference")
    ref.set("URI", f"#{ident}")
    trans = etree.SubElement(ref, f"{ds}Transforms")
    etree.SubElement(trans, f"{ds}Transform").set("Algorithm", ALGORITMO_ENVELOPADA)
    etree.SubElement(trans, f"{ds}Transform").set("Algorithm", ALGORITMO_C14N)
    etree.SubElement(ref, f"{ds}DigestMethod").set("Algorithm", ALGORITMO_RESUMO)
    etree.SubElement(ref, f"{ds}DigestValue").text = resumo

    valor = certificado.chave.sign(_c14n(info), padding.PKCS1v15(), hashes.SHA256())
    etree.SubElement(assinatura, f"{ds}SignatureValue").text = (
        base64.b64encode(valor).decode("ascii"))
    der = certificado.certificado.public_bytes(serialization.Encoding.DER)
    x509 = etree.SubElement(etree.SubElement(assinatura, f"{ds}KeyInfo"), f"{ds}X509Data")
    etree.SubElement(x509, f"{ds}X509Certificate").text = (
        base64.b64encode(der).decode("ascii"))
    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8")


def conferir_assinatura(xml: bytes) -> bool:
    """A assinatura bate com o conteúdo e com o certificado que ela traz?

    Serve à casa para conferir o que vai sair antes de sair, e ao teste —
    o mesmo trabalho que a Sefin faz do lado de lá.
    """
    from cryptography import x509
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    raiz = etree.fromstring(xml)
    ns = {"ds": NS_DS}
    assinatura = raiz.find("ds:Signature", ns)
    if assinatura is None:
        return False
    alvo = raiz[0]
    ref = assinatura.find("ds:SignedInfo/ds:Reference", ns)
    if ref is None or ref.get("URI") != f"#{alvo.get('Id')}":
        return False
    # O resumo é do alvo SEM a assinatura (a transformação envelopada); como
    # a assinatura é irmã do alvo, e não filha, o alvo já está sem ela.
    resumo = base64.b64encode(hashlib.sha256(_c14n(alvo)).digest()).decode("ascii")
    if resumo != assinatura.findtext("ds:SignedInfo/ds:Reference/ds:DigestValue",
                                     namespaces=ns):
        return False
    cert = x509.load_der_x509_certificate(base64.b64decode(
        assinatura.findtext("ds:KeyInfo/ds:X509Data/ds:X509Certificate",
                            namespaces=ns) or ""))
    try:
        cert.public_key().verify(
            base64.b64decode(assinatura.findtext("ds:SignatureValue", namespaces=ns) or ""),
            _c14n(assinatura.find("ds:SignedInfo", ns)),
            padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature:
        return False
    return True
