"""O ENVELOPE ASSINADO (CMS/PKCS#7) do XML da carga da CRC — via o A3 isolado.

O manual da CRC diz que o web service exige o arquivo *«assinado digitalmente,
utilizando o seu certificado digital e-CPF, e enviado formatado em BASE64»*.
Ele não descreve o formato exato do "assinado" — mas esta casa já tem um
precedente real e medido para "documento assinado digitalmente" com e-CPF:
`assinatura_digital.py`, que **lê** exatamente isto — PKCS#7 `signedData`,
com o documento **dentro** (anexado, e não destacado), medido byte a byte no
instrumento de protesto real de 09/06/2025.

**ESTE MÓDULO PRODUZ O QUE AQUELE JÁ SABE LER.** É a mesma forma — CMS
`SignedData` anexado — porque duas formas de "documento assinado" nesta casa
divergiriam no primeiro conserto, e porque é o único formato de assinatura
e-CPF que este projeto já mediu contra um arquivo real.

**A CONTA CRIPTOGRÁFICA ACONTECE EM DUAS METADES, E SÓ UMA DELAS TOCA O
TOKEN.** O RFC 5652 exige que, havendo atributos assinados, a assinatura
recaia sobre o DER dos atributos — não sobre o documento cru. Este módulo
monta esses atributos (tipo do conteúdo + resumo SHA-256 do documento) aqui,
no processo principal; manda só o DER deles para `crc_a3.assinar()`, que os
assina no processo isolado; e monta o envelope final com o que voltou. **A
chave nunca sai do token, e o processo que a toca nunca é este.**

O QUE NÃO FOI MEDIDO, E FICA DITO
    O manual não diz se o formato exigido é este CMS anexado, um XML-DSig,
    ou outra coisa — só diz "assinado, em base64". Isto é a hipótese mais
    fundamentada que existe nesta casa (o mesmo formato que ela já lê), e não
    uma confirmação da CRC. **Só um envio de teste em homologação confirma.**
"""
from __future__ import annotations

import hashlib
from typing import Any

from asn1crypto import cms, core, x509

import crc_a3

# O OID de "dados" (id-data), que é o conteúdo de um XML assinado sem
# semântica de e-mail nem de outro tipo — o mesmo que `assinatura_digital.py`
# aceita ao ler (ela não exige um OID específico do conteúdo interno).
_ID_DATA = "1.2.840.113549.1.7.1"

# O algoritmo de resumo. `assinatura_digital.py` mediu SHA-1 no instrumento
# de 2025 (o assinador de mercado que o delegatário usa escolheu SHA-1); a
# CRC não declara o dela. SHA-256 é o mínimo que qualquer validador moderno
# aceita, e não há motivo para escolher o mais fraco quando não há norma
# obrigando.
_ALGORITMO = "sha256"


class CmsError(ValueError):
    """Erro de regra, com mensagem pronta para o balcão."""


def _atributos_assinados(conteudo: bytes) -> cms.CMSAttributes:
    """Os dois atributos que o RFC 5652 exige quando há atributos: o tipo do
    conteúdo, e o resumo dele. Sem os dois, um validador correto recusa."""
    return cms.CMSAttributes([
        cms.CMSAttribute({
            "type": "content_type",
            "values": [cms.ContentType(_ID_DATA)],
        }),
        cms.CMSAttribute({
            "type": "message_digest",
            "values": [core.OctetString(
                hashlib.new(_ALGORITMO, conteudo).digest())],
        }),
    ])


def assinar_anexado(conteudo: bytes, *, driver: str, pin: str) -> bytes:
    """O CMS `SignedData` ANEXADO de `conteudo`, assinado pelo A3 isolado.

    Devolve os bytes DER prontos para `base64.b64encode` — é isso que vai
    como parâmetro único da chamada SOAP. Não grava nada, não guarda o PIN.
    """
    atributos = _atributos_assinados(conteudo)
    # **É O DER DOS ATRIBUTOS QUE SE ASSINA, NÃO O CONTEÚDO CRU** — RFC 5652
    # § 5.4. `CMSAttributes` sem argumento de tag serializa como
    # `SET OF` universal, que é a forma exigida para o cálculo da
    # assinatura; a forma com a tag `[0] IMPLICIT` só aparece quando ela é
    # embutida dentro do `SignerInfo`, mais abaixo — e o `asn1crypto` troca
    # a tag sozinho nesse momento.
    para_assinar = atributos.dump(force=True)

    resultado = crc_a3.assinar(para_assinar, driver=driver, pin=pin)
    assinatura = bytes.fromhex(_b64_para_hex(resultado["assinatura_b64"]))
    certificado_der = bytes.fromhex(_b64_para_hex(resultado["certificado_b64"]))

    certificado = x509.Certificate.load(certificado_der)

    signer_info = cms.SignerInfo({
        "version": "v1",
        "sid": cms.SignerIdentifier({
            "issuer_and_serial_number": cms.IssuerAndSerialNumber({
                "issuer": certificado["tbs_certificate"]["issuer"],
                "serial_number":
                    certificado["tbs_certificate"]["serial_number"],
            }),
        }),
        "digest_algorithm": cms.DigestAlgorithm(
            {"algorithm": _ALGORITMO}),
        "signed_attrs": atributos,
        "signature_algorithm": cms.SignedDigestAlgorithm(
            {"algorithm": "sha256_rsa"}),
        "signature": assinatura,
    })

    signed_data = cms.SignedData({
        "version": "v1",
        "digest_algorithms": cms.DigestAlgorithms([
            cms.DigestAlgorithm({"algorithm": _ALGORITMO}),
        ]),
        "encap_content_info": cms.ContentInfo({
            "content_type": _ID_DATA,
            # ANEXADO: o documento vai DENTRO do envelope, byte a byte
            # — a mesma forma que `assinatura_digital.py` já confere.
            "content": core.OctetString(conteudo),
        }),
        "certificates": [cms.CertificateChoices({"certificate": certificado})],
        "signer_infos": [signer_info],
    })

    envelope = cms.ContentInfo({
        "content_type": "signed_data",
        "content": signed_data,
    })
    return envelope.dump()


def _b64_para_hex(valor_b64: str) -> str:
    import base64
    return base64.b64decode(valor_b64).hex()
