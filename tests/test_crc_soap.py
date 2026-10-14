"""O TRANSPORTE SOAP DA CRC — envelope, assinatura WS-Security e a resposta.

O QUE ESTES TESTES PROVAM
    - o envelope é XML bem formado, com `wsse:Security` no cabeçalho e o
      parâmetro único no corpo;
    - o `ds:Signature` sobre o `wsu:Timestamp` **confere de verdade** — o
      mesmo tipo de auto-teste que `crc_cms.py` já faz: assina com uma
      chave de teste, reconstrói e verifica com a chave pública, sem tocar
      em hardware nenhum;
    - `enviar_carga` recusa quando não há o que enviar, e não abre conexão
      nenhuma nesse caso;
    - a leitura da resposta separa sucesso, falha `CFCInvocationException`
      e resposta em forma desconhecida.

O QUE ESTES TESTES NÃO PROVAM
    Que a Central aceita este envelope. A forma do corpo (nome do parâmetro,
    RPC/encoded) é medida por analogia, e a assinatura XML nunca foi
    conferida contra um servidor real — ver o cabeçalho de `crc_soap.py`.
    **Só um envio de teste em homologação confirma.**
"""
from __future__ import annotations

import base64
import datetime
import sys
from pathlib import Path

import pytest
from lxml import etree

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import crc_a3
import crc_carga
import crc_soap


@pytest.fixture
def chave_e_certificado_de_teste():
    from cryptography import x509 as cx509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = cx509.Name([cx509.NameAttribute(NameOID.COMMON_NAME, "TESTE")])
    agora = datetime.datetime.now(datetime.timezone.utc)
    cert = (cx509.CertificateBuilder()
            .subject_name(nome).issuer_name(nome)
            .public_key(chave.public_key())
            .serial_number(cx509.random_serial_number())
            .not_valid_before(agora)
            .not_valid_after(agora + datetime.timedelta(days=1))
            .sign(chave, hashes.SHA256()))
    return chave, cert, cert.public_bytes(serialization.Encoding.DER)


@pytest.fixture
def token_falso(monkeypatch, chave_e_certificado_de_teste):
    """Substitui `crc_a3.assinar` por uma assinatura de verdade, com a chave
    de teste — nunca toca em PKCS#11 nem em processo isolado nenhum."""
    chave, _cert, cert_der = chave_e_certificado_de_teste

    def _assinar(mensagem, *, driver, pin):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        assinatura = chave.sign(mensagem, padding.PKCS1v15(), hashes.SHA256())
        return {
            "assinatura_b64": base64.b64encode(assinatura).decode(),
            "certificado_b64": base64.b64encode(cert_der).decode(),
            "mecanismo": "CKM_SHA256_RSA_PKCS",
        }

    monkeypatch.setattr(crc_a3, "assinar", _assinar)
    return chave


def test_envelope_e_xml_bem_formado(token_falso):
    corpo = crc_soap.envelope("QUJD", driver="fake.dll", pin="000000")
    raiz = etree.fromstring(corpo)
    assert raiz.tag == f"{{{crc_soap._NS_SOAP}}}Envelope"
    achado = raiz.find(f".//{{{crc_soap._NS_SOAP}}}Header"
                       f"/{{{crc_soap._NS_WSSE}}}Security")
    assert achado is not None


def test_assinatura_do_timestamp_confere(token_falso, chave_e_certificado_de_teste):
    """O mesmo auto-teste de `crc_cms.py`: assina, reconstrói, verifica."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    _chave, cert, _der = chave_e_certificado_de_teste
    corpo = crc_soap.envelope("QUJD", driver="fake.dll", pin="000000")
    raiz = etree.fromstring(corpo)
    ns = {"ds": crc_soap._NS_DS, "wsu": crc_soap._NS_WSU}
    timestamp = raiz.find(".//wsu:Timestamp", ns)
    signed_info = raiz.find(".//ds:SignedInfo", ns)
    assinatura_b64 = raiz.find(".//ds:SignatureValue", ns).text

    digest_calculado = crc_soap._digest_sha256_b64(
        crc_soap._c14n_exc(timestamp))
    digest_no_signed_info = signed_info.find(".//ds:DigestValue", ns).text
    assert digest_calculado == digest_no_signed_info

    cert.public_key().verify(
        base64.b64decode(assinatura_b64), crc_soap._c14n_exc(signed_info),
        padding.PKCS1v15(), hashes.SHA256())


def test_enviar_carga_recusa_sem_nada_para_enviar(monkeypatch, token_falso):
    def _montar_vazio(con, assentos, *, cns):
        return {"xml": "", "quantos": 0,
                "retidos": [{"assento_id": 1, "faltas": ["x"]}],
                "a_arrumar": []}
    monkeypatch.setattr(crc_carga, "montar", _montar_vazio)

    chamou = []
    monkeypatch.setattr(crc_soap, "_bater",
                        lambda *a, **k: chamou.append(1) or "")

    with pytest.raises(crc_soap.CrcSoapError, match="Nenhum"):
        crc_soap.enviar_carga(None, [1], cns="000000", driver="fake.dll",
                              pin="000000")
    assert not chamou, "nada devia ter tentado falar com a rede"


def test_enviar_carga_completa_com_transporte_simulado(monkeypatch, token_falso):
    def _montar(con, assentos, *, cns):
        return {"xml": "<CARGAREGISTROS><VERSAO>2.6</VERSAO></CARGAREGISTROS>",
                "quantos": 1, "retidos": [], "a_arrumar": []}
    monkeypatch.setattr(crc_carga, "montar", _montar)

    def _bater(ambiente, corpo, *, prazo=180):
        assert isinstance(corpo, (bytes, bytearray))
        etree.fromstring(corpo)  # o corpo tem de ser XML válido
        return "<return>OK-123</return>"
    monkeypatch.setattr(crc_soap, "_bater", _bater)

    resultado = crc_soap.enviar_carga(
        None, [1], cns="000000", driver="fake.dll", pin="000000")
    assert resultado["enviado"] == 1
    assert resultado["resposta"] == "OK-123"


def test_ler_resposta_reconhece_falha_cfc():
    texto = ("<soap:Envelope><soap:Body><soap:Fault>"
             "<faultstring>CFCInvocationException: XML inválido</faultstring>"
             "</soap:Fault></soap:Body></soap:Envelope>")
    with pytest.raises(crc_soap.CrcSoapRecusou, match="XML inválido"):
        crc_soap.ler_resposta(texto)


def test_ler_resposta_le_o_conteudo_de_sucesso():
    texto = "<ns1:cargaRegistrosCompletoResponse><return>123</return></ns1:cargaRegistrosCompletoResponse>"
    assert crc_soap.ler_resposta(texto) == "123"


def test_endereco_forca_https():
    assert crc_soap.endereco_do_ambiente(crc_soap.HOMOLOGACAO).startswith("https://")
    assert crc_soap.endereco_do_ambiente(crc_soap.PRODUCAO).startswith("https://")


def test_endereco_desconhecido_recusa():
    with pytest.raises(crc_soap.CrcSoapError):
        crc_soap._partes("http://exemplo.com/x")
