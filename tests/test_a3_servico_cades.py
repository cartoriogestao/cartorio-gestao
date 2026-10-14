"""O serviço local A3 assinando CAdES para o CCN — 13/10/2026.

Sem token: o processo filho é trocado por um dublê. O que se guarda: página da
internet não chega ao token (o risco é bloqueá-lo com PIN errado), a rota
devolve o `x_signature_b64`, e o driver escolhido é o que ENXERGA o
certificado, e não o primeiro da lista de nomes.
"""
from __future__ import annotations

import base64
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import a3_servico_local as SVC  # noqa: E402

SAFEID = r"C:\Windows\System32\aetpkss1.dll"
SAFENET = r"C:\Windows\System32\eTPKCS11.dll"


@pytest.fixture()
def dois_drivers(monkeypatch):
    """SafeID não enxerga token; SafeNet enxerga o certificado do delegatário."""
    monkeypatch.setattr(SVC, "_DRIVER_FORCADO", None)
    monkeypatch.delenv(SVC.ENV_DRIVER, raising=False)
    monkeypatch.setattr(SVC, "_ler_config_json", lambda: None)
    monkeypatch.setattr(SVC, "detectar_driver", lambda: Path(SAFEID))
    monkeypatch.setattr(SVC, "listar_candidatos_no_disco", lambda: [
        {"nome": "aetpkss1.dll", "caminho": SAFEID, "origem": "System32"},
        {"nome": "eTPKCS11.dll", "caminho": SAFENET, "origem": "System32"}])
    monkeypatch.setattr(SVC, "_DRIVER_DO_CERTIFICADO", {})
    pedidos = []

    def filho(pedido):
        pedidos.append(dict(pedido))
        if pedido["op"] == "listar":
            if pedido["driver"] == SAFEID:
                raise SVC.ServicoA3Error("C_GetSlotList falhou: código 0x00000006")
            return {"certificados": [{"subject": "DELEGATARIO", "thumbprint": "AB" * 20}]}
        return {"formato": "CAdES-BES-anexado", "x_signature_b64": "WFNJRw==",
                "cms_b64": "WFNJRw==", "subject": "DELEGATARIO", "thumbprint": "AB" * 20}

    monkeypatch.setattr(SVC, "_chamar_filho", filho)
    return pedidos


def test_pagina_da_internet_e_recusada_e_extensao_e_cg_passam():
    assert SVC.origem_recusada("https://site-qualquer.com", "application/json", "POST")
    assert SVC.origem_recusada(None, "text/plain", "POST")          # sem preflight, não
    assert SVC.origem_recusada("chrome-extension://abc", "application/json", "POST") is None
    assert SVC.origem_recusada(None, "application/json", "POST") is None
    assert SVC.origem_recusada(None, None, "GET") is None


def test_pin_vazio_nao_chega_ao_filho(dois_drivers):
    with pytest.raises(SVC.ServicoA3Error, match="PIN"):
        SVC.assinar_cades(b'{"x":1}', "")
    assert dois_drivers == []


def test_assina_com_o_driver_que_enxerga_o_certificado(dois_drivers):
    r = SVC.assinar_cades(b'{"Timestamp":"t","RequestPath":"/p"}', "1234")
    assert r["x_signature_b64"] == "WFNJRw=="
    assinatura = [p for p in dois_drivers if p["op"] == "assinar_cades"][0]
    assert assinatura["driver"] == SAFENET and assinatura["anexado"] is True
    certs = SVC.listar_certificados()
    assert certs["certificados"][0]["driver"] == SAFENET
    assert certs["falhas"] and "0x00000006" in certs["falhas"][0]


def _servidor():
    srv = SVC.ThreadingHTTPServer(("127.0.0.1", 0), SVC.Manipulador)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def _post(porta, corpo, **cab):
    req = urllib.request.Request(f"http://127.0.0.1:{porta}/assinar/cades",
                                 data=json.dumps(corpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **cab})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_a_rota_devolve_o_x_signature_e_recusa_a_pagina(dois_drivers):
    srv, porta = _servidor()
    try:
        codigo, dados = _post(porta, {"payload_utf8": '{"a":1}', "pin": "1234"},
                              Origin="chrome-extension://idqualquer")
        assert codigo == 200 and dados["x_signature_b64"] == "WFNJRw=="
        codigo, dados = _post(porta, {"payload_utf8": '{"a":1}', "pin": "1234"},
                              Origin="https://pagina.hostil.example")
        assert codigo == 403 and "página da internet" in dados["erro"]
        assert sum(p["op"] == "assinar_cades" for p in dois_drivers) == 1
    finally:
        srv.shutdown()
        srv.server_close()


def test_o_pin_nao_vai_para_o_log(dois_drivers):
    srv, porta = _servidor()
    linhas = []
    try:
        with mock.patch.object(SVC.log, "info", side_effect=lambda m, *a: linhas.append(m % a if a else m)):
            _post(porta, {"payload_utf8": '{"a":1}', "pin": "PIN-SECRETO-9876"})
    finally:
        srv.shutdown()
        srv.server_close()
    assert not any("PIN-SECRETO" in l for l in linhas)
    assert base64                                    # import usado no módulo
