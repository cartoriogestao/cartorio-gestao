"""A assinatura CAdES-BES — montar e conferir, SEM token e SEM driver.

POR QUE ESTE MÓDULO EXISTE — 13/10/2026
    Ordem do oficial: «vamos construir o submodulo de envio para o CCN e
    assinador a3 acessorio». O CCN pede, nas consultas por CPF, o cabeçalho
    `X-Signature`: «The Base64 CAdES Signature of
    {"Timestamp":"…","RequestPath":"/api/exports/record-sets/{cpf}"}»
    (contrato `Pessoas 2.99.2 RTM`, lido em 13/10/2026).

    O assinador filho de 05/10 (`a3_assinador_filho._montar_cms_anexado`)
    assinava o CONTEÚDO CRU e montava um SignedData sem atributos assinados —
    e por isso não era CAdES: CAdES-BES exige os atributos `content-type`,
    `message-digest` e `signing-certificate-v2`, e a assinatura é sobre ELES,
    e não sobre o conteúdo. O comentário de lá já dizia isso («para CMS
    "correto" com signedAttrs, a firma seria sobre os attrs DER»).

O QUE MORA AQUI, E O QUE NÃO MORA
    Aqui: montar os atributos, dizer quais bytes o token tem de assinar,
    embrulhar a assinatura e CONFERIR o envelope pronto. Tudo puro, com
    `asn1crypto` e `cryptography` — testável com uma chave de ensaio.

    Não mora aqui: falar com o token. Isso é do processo filho
    (`a3_assinador_filho.py`), e a razão é a de sempre: driver PKCS#11 que
    trava mata o processo que o carregou. Este módulo pode ser importado em
    qualquer lugar; o filho, só por subprocesso.

O FLUXO, em três passos
    1. `atributos(conteudo, cert_der)`  → os atributos assinados;
    2. `bytes_a_assinar(atributos)`     → o que vai ao token
       (CKM_SHA256_RSA_PKCS faz o SHA-256 dentro do token);
    3. `envelope(conteudo, cert_der, atributos, assinatura)` → o CMS em DER.
    E `conferir(cms_der)` refaz a conta do lado de quem recebe.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from asn1crypto import algos, cms, core, tsp, x509

FORMATO = "CAdES-BES"


class CadesError(ValueError):
    """Envelope que não confere — com a frase de por quê."""


def atributos(conteudo: bytes, cert_der: bytes, *,
              agora: datetime | None = None) -> cms.CMSAttributes:
    """Os quatro atributos assinados do CAdES-BES, na ordem de costume.

    `signing-certificate-v2` é o que faz disto CAdES, e não só CMS: ele amarra
    a assinatura ao certificado (SHA-256 do certificado inteiro), para que
    ninguém troque o certificado do envelope por outro da mesma chave.
    """
    if not cert_der:
        raise CadesError("sem certificado não há o que amarrar à assinatura")
    cert = x509.Certificate.load(cert_der)
    agora = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    ess = tsp.ESSCertIDv2({
        # hash_algorithm fica no padrão (SHA-256): em DER o valor padrão não
        # se escreve, e escrever faria o envelope ser recusado por quem confere
        # o DER ao pé da letra.
        "cert_hash": hashlib.sha256(cert_der).digest(),
        "issuer_serial": tsp.IssuerSerial({
            "issuer": [x509.GeneralName({"directory_name": cert.issuer})],
            "serial_number": cert.serial_number,
        }),
    })
    return cms.CMSAttributes([
        cms.CMSAttribute({"type": "content_type", "values": ["data"]}),
        cms.CMSAttribute({"type": "signing_time",
                          "values": [cms.Time({"utc_time": core.UTCTime(agora)})]}),
        cms.CMSAttribute({"type": "message_digest",
                          "values": [core.OctetString(hashlib.sha256(conteudo).digest())]}),
        cms.CMSAttribute({"type": "signing_certificate_v2",
                          "values": [tsp.SigningCertificateV2({"certs": [ess]})]}),
    ])


def _signer_info(cert: x509.Certificate, attrs: cms.CMSAttributes,
                 assinatura: bytes) -> cms.SignerInfo:
    return cms.SignerInfo({
        "version": "v1",
        "sid": cms.SignerIdentifier({
            "issuer_and_serial_number": cms.IssuerAndSerialNumber({
                "issuer": cert.issuer, "serial_number": cert.serial_number}),
        }),
        "digest_algorithm": algos.DigestAlgorithm({"algorithm": "sha256"}),
        "signed_attrs": attrs,
        "signature_algorithm": algos.SignedDigestAlgorithm({"algorithm": "rsassa_pkcs1v15"}),
        "signature": assinatura,
    })


def _atributos_como_set(si: cms.SignerInfo) -> bytes:
    """Os atributos como o verificador os refaz: o [0] implícito vira SET (0x31).

    É a regra do CMS (RFC 5652, 5.4): assina-se o DER do SET OF, e não o [0]
    com que ele viaja dentro do SignerInfo. Tirar daqui os bytes — e não
    remontá-los noutro lugar — garante que o que se assina é exatamente o que
    vai no envelope.
    """
    bruto = si["signed_attrs"].dump()
    return b"\x31" + bruto[1:]


def bytes_a_assinar(attrs: cms.CMSAttributes, cert_der: bytes) -> bytes:
    """O que o token assina (com CKM_SHA256_RSA_PKCS, que faz o hash dentro)."""
    cert = x509.Certificate.load(cert_der)
    return _atributos_como_set(_signer_info(cert, attrs, b"\x00"))


def envelope(conteudo: bytes, cert_der: bytes, attrs: cms.CMSAttributes,
             assinatura: bytes, *, anexado: bool = True,
             cadeia: list[bytes] | None = None) -> bytes:
    """O SignedData em DER. `anexado` põe o conteúdo dentro do envelope.

    No `X-Signature` do CCN o envelope vai ANEXADO: o pedido não leva o
    Timestamp em lugar nenhum além da assinatura, e quem recebe precisa ler o
    JSON assinado de dentro dela.
    """
    if not assinatura:
        raise CadesError("o token não devolveu assinatura")
    cert = x509.Certificate.load(cert_der)
    certs = [cert] + [x509.Certificate.load(c) for c in (cadeia or []) if c and c != cert_der]
    encap: dict[str, Any] = {"content_type": "data"}
    if anexado:
        encap["content"] = conteudo
    return cms.ContentInfo({
        "content_type": "signed_data",
        "content": cms.SignedData({
            "version": "v1",
            "digest_algorithms": [algos.DigestAlgorithm({"algorithm": "sha256"})],
            "encap_content_info": encap,
            "certificates": certs,
            "signer_infos": [_signer_info(cert, attrs, assinatura)],
        }),
    }).dump()


def assinar(conteudo: bytes, cert_der: bytes, assinar_fn, *, anexado: bool = True,
            agora: datetime | None = None, cadeia: list[bytes] | None = None) -> bytes:
    """Os três passos de uma vez. `assinar_fn(bytes) -> assinatura RSA PKCS#1 v1.5 SHA-256`."""
    attrs = atributos(conteudo, cert_der, agora=agora)
    assinatura = assinar_fn(bytes_a_assinar(attrs, cert_der))
    pronto = envelope(conteudo, cert_der, attrs, assinatura, anexado=anexado, cadeia=cadeia)
    conferir(pronto, None if anexado else conteudo)
    return pronto


def conferir(cms_der: bytes, conteudo: bytes | None = None) -> dict[str, Any]:
    """Refaz a conta de quem recebe. Devolve o conteúdo e quem assinou.

    Confere: a assinatura RSA sobre os atributos, o resumo do conteúdo, e que o
    `signing-certificate-v2` aponta para o certificado do envelope. NÃO confere
    cadeia ICP-Brasil nem revogação — isso esta casa não tem como conferir, e
    o módulo não afirma o que não conferiu.
    """
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.x509 import load_der_x509_certificate

    try:
        ci = cms.ContentInfo.load(cms_der)
        sd = ci["content"]
        si = sd["signer_infos"][0]
    except Exception as erro:                              # noqa: BLE001
        raise CadesError(f"o envelope não é um CMS legível: {erro}") from erro
    dentro = sd["encap_content_info"]["content"].native
    if dentro is None and conteudo is None:
        raise CadesError("envelope destacado: informe o conteúdo para conferir")
    if dentro is not None and conteudo is not None and dentro != conteudo:
        raise CadesError("o conteúdo de dentro do envelope não é o informado")
    dado = dentro if dentro is not None else conteudo

    sid = si["sid"].chosen
    cert = next((c.chosen for c in sd["certificates"]
                 if c.chosen.issuer == sid["issuer"] and c.chosen.serial_number == sid["serial_number"].native),
                None)
    if cert is None:
        raise CadesError("o certificado de quem assinou não está no envelope")
    attrs = {a["type"].native: a["values"][0] for a in si["signed_attrs"]}
    for nome in ("content_type", "message_digest", "signing_certificate_v2"):
        if nome not in attrs:
            raise CadesError(f"falta o atributo assinado «{nome}» — não é CAdES-BES")
    if attrs["message_digest"].native != hashlib.sha256(dado).digest():
        raise CadesError("o resumo assinado não bate com o conteúdo")
    ess = attrs["signing_certificate_v2"]["certs"][0]
    if ess["cert_hash"].native != hashlib.sha256(cert.dump()).digest():
        raise CadesError("o signing-certificate-v2 aponta para outro certificado")

    publica = load_der_x509_certificate(cert.dump()).public_key()
    try:
        publica.verify(si["signature"].native, _atributos_como_set(si),
                       padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature as erro:
        raise CadesError("a assinatura não confere com o certificado") from erro
    quando = attrs.get("signing_time")
    return {"formato": FORMATO, "conteudo": dado, "anexado": dentro is not None,
            "assinante": cert.subject.human_friendly,
            "assinado_em": quando.native.isoformat() if quando is not None else None,
            "cadeia_icp_conferida": False}
