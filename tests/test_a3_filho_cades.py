"""O processo filho assinando em CAdES — 13/10/2026, sem token de verdade.

O «token» aqui é um dublê com a mesma interface que `a3_assinador_filho.Modulo`
usa (slots, sessão, login, objetos, C_Sign); por dentro, uma chave RSA de
ensaio. O que se guarda: o envelope que sai do filho confere, o PIN vazio é
recusado antes de chegar ao token, e o logout acontece mesmo quando o token
recusa.
"""
from __future__ import annotations

import base64
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import a3_assinador_filho as F  # noqa: E402  (em teste pode; no Flask, nunca)
import cades  # noqa: E402

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding, rsa  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402


class TokenDeEnsaio:
    def __init__(self, recusa_pin=False):
        self.chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "DELEGATARIO DE ENSAIO:00000000191")])
        agora = datetime.now(timezone.utc)
        self.cert = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome)
                     .public_key(self.chave.public_key()).serial_number(7)
                     .not_valid_before(agora - timedelta(days=1))
                     .not_valid_after(agora + timedelta(days=30))
                     .sign(self.chave, hashes.SHA256())).public_bytes(serialization.Encoding.DER)
        self.recusa_pin, self.saiu, self.assinados = recusa_pin, False, []

    def slots_com_token(self):
        return [1]

    def abrir_sessao(self, slot):
        return 11

    def fechar_sessao(self, sessao):
        pass

    def login(self, sessao, pin):
        if self.recusa_pin:
            raise F.Pkcs11Error("PIN incorreto")

    def logout(self, sessao):
        self.saiu = True

    def achar_objetos(self, sessao, *, classe, limite=32, id_=None):
        return [101] if classe == F.CKO_CERTIFICATE else [202]

    def achar_objeto(self, sessao, *, classe, id_=None):
        return 202 if classe == F.CKO_PRIVATE_KEY else 101

    def ler_atributo(self, sessao, obj, tipo):
        if tipo == F.CKA_VALUE:
            return self.cert
        if tipo == F.CKA_ID:
            return b"\x01"
        return b"ENSAIO"

    def assinar(self, sessao, chave, mecanismo, dados):
        assert mecanismo == F.CKM_SHA256_RSA_PKCS
        self.assinados.append(dados)
        return self.chave.sign(dados, padding.PKCS1v15(), hashes.SHA256())


PAYLOAD = b'{"Timestamp":"2026-10-13T22:39:04+00:00","RequestPath":"/api/exports/record-sets/00000000191"}'


def test_o_filho_devolve_x_signature_que_confere():
    token = TokenDeEnsaio()
    r = F._op_assinar(token, "1234", PAYLOAD, None, cades_anexado=True)
    assert r["formato"] == "CAdES-BES-anexado"
    visto = cades.conferir(base64.b64decode(r["x_signature_b64"]))
    assert visto["conteudo"] == PAYLOAD
    assert token.assinados[0] != PAYLOAD          # o token assinou os atributos, e não o JSON
    assert token.saiu


def test_pin_vazio_nao_chega_ao_token():
    token = TokenDeEnsaio()
    with pytest.raises(F.Pkcs11Error, match="PIN"):
        F._op_assinar(token, "", PAYLOAD, None, cades_anexado=True)
    assert token.assinados == []


def test_pin_recusado_explica_e_nao_assina():
    token = TokenDeEnsaio(recusa_pin=True)
    with pytest.raises(F.Pkcs11Error, match="recusado"):
        F._op_assinar(token, "0000", PAYLOAD, None, cades_anexado=True)
    assert token.assinados == []


def test_o_pdf_sai_em_cades_e_nao_mais_no_envelope_que_nao_conferia():
    token = TokenDeEnsaio()
    pdf = b"%PDF-1.4\n%ensaio\n"
    r = F._op_assinar(token, "1234", pdf, None, cades_anexado=True)
    assert cades.conferir(base64.b64decode(r["cms_b64"]))["conteudo"] == pdf
    assert not hasattr(F, "_montar_cms_anexado")
