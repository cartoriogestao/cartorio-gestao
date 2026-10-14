"""A assinatura CAdES-BES do `X-Signature` do CCN — 13/10/2026.

Sem token: uma chave RSA de ensaio faz o papel do A3, com a MESMA conta que o
token faz (`CKM_SHA256_RSA_PKCS` = PKCS#1 v1.5 sobre SHA-256). O que se guarda:
o envelope confere aqui E num verificador que não é este código (OpenSSL), e o
envelope de 05/10 — que assinava o conteúdo cru — não passaria por aqui.
"""
from __future__ import annotations

import base64
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import cades  # noqa: E402

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding, rsa  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

PAYLOAD = (b'{"Timestamp":"2026-10-13T22:39:04.1525417+00:00",'
           b'"RequestPath":"/api/exports/record-sets/00000000191"}')


@pytest.fixture(scope="module")
def chave_e_cert():
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ENSAIO A3:00000000191")])
    agora = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome)
            .public_key(chave.public_key()).serial_number(424242)
            .not_valid_before(agora - timedelta(days=1)).not_valid_after(agora + timedelta(days=30))
            .sign(chave, hashes.SHA256()))
    return chave, cert.public_bytes(serialization.Encoding.DER)


def _como_o_token(chave):
    return lambda dados: chave.sign(dados, padding.PKCS1v15(), hashes.SHA256())


def test_o_envelope_anexado_confere_e_traz_o_json(chave_e_cert):
    chave, cert = chave_e_cert
    pronto = cades.assinar(PAYLOAD, cert, _como_o_token(chave))
    visto = cades.conferir(pronto)
    assert visto["conteudo"] == PAYLOAD and visto["anexado"]
    assert "ENSAIO A3" in visto["assinante"]
    assert visto["cadeia_icp_conferida"] is False        # não se afirma o que não se conferiu


def test_o_destacado_pede_o_conteudo(chave_e_cert):
    chave, cert = chave_e_cert
    pronto = cades.assinar(PAYLOAD, cert, _como_o_token(chave), anexado=False)
    with pytest.raises(cades.CadesError):
        cades.conferir(pronto)
    assert cades.conferir(pronto, PAYLOAD)["conteudo"] == PAYLOAD


def test_conteudo_trocado_nao_confere(chave_e_cert):
    chave, cert = chave_e_cert
    pronto = cades.assinar(PAYLOAD, cert, _como_o_token(chave), anexado=False)
    with pytest.raises(cades.CadesError, match="resumo"):
        cades.conferir(pronto, PAYLOAD.replace(b"191", b"272"))


def test_assinatura_sobre_o_conteudo_cru_nao_passa(chave_e_cert):
    """O defeito de 05/10: assinar o conteúdo, e não os atributos."""
    chave, cert = chave_e_cert
    attrs = cades.atributos(PAYLOAD, cert)
    errado = cades.envelope(PAYLOAD, cert, attrs, _como_o_token(chave)(PAYLOAD))
    with pytest.raises(cades.CadesError, match="não confere"):
        cades.conferir(errado)


def test_os_atributos_do_cades_bes_estao_la(chave_e_cert):
    from asn1crypto import cms
    chave, cert = chave_e_cert
    si = cms.ContentInfo.load(cades.assinar(PAYLOAD, cert, _como_o_token(chave)))["content"]["signer_infos"][0]
    nomes = [a["type"].native for a in si["signed_attrs"]]
    assert nomes == ["content_type", "signing_time", "message_digest", "signing_certificate_v2"]


@pytest.mark.skipif(not shutil.which("openssl"), reason="sem OpenSSL nesta máquina")
def test_o_openssl_aceita_o_envelope(chave_e_cert, tmp_path):
    """Um verificador que não é este código: se só o nosso `conferir` aceitasse,
    a prova seria da nossa ideia do CAdES, e não do CAdES."""
    chave, cert = chave_e_cert
    p7 = tmp_path / "x.p7m"
    p7.write_bytes(cades.assinar(PAYLOAD, cert, _como_o_token(chave)))
    r = subprocess.run(["openssl", "cms", "-verify", "-noverify", "-inform", "DER",
                        "-in", str(p7), "-binary"], capture_output=True)
    assert r.returncode == 0, r.stderr.decode(errors="replace")
    assert r.stdout == PAYLOAD
    assert base64.b64encode(p7.read_bytes())          # vai no cabeçalho em Base64
