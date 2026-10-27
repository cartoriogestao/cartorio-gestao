"""Puxar da caixa-postal: cabeçalhos, envelope e confirmação. Sem rede."""
from __future__ import annotations

import io
import json
import logging
import sys
import urllib.error
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import wa_puxar as PUXAR
import wa_schema as SCH

CAIXA = "https://caixa.exemplo/pendentes"
SEGREDO = "segredo-teste"


def _webhook(marca: str = "a") -> dict:
    return {"object": "whatsapp_business_account", "marca": marca, "entry": []}


class _Resposta:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Caixa:
    def __init__(self, corpo: bytes, *, ack_status: int = 200):
        self.corpo = corpo
        self.ack_status = ack_status
        self.pedidos: list = []

    def urlopen(self, req, timeout=None):
        self.pedidos.append(req)
        if req.get_method() == "POST":
            if self.ack_status >= 400:
                raise urllib.error.HTTPError(
                    req.full_url, self.ack_status, "falhou",
                    hdrs=None, fp=io.BytesIO(b'{"ok":false}'))
            return _Resposta(self.ack_status, b'{"ok":true}')
        return _Resposta(200, self.corpo)


def _configurar(monkeypatch, caixa: _Caixa | None = None):
    def ler(con, chave):
        if chave == SCH.CHAVE_CAIXA_URL:
            return CAIXA
        if chave == SCH.CHAVE_CAIXA_SEGREDO:
            return SEGREDO
        return ""

    monkeypatch.setattr(PUXAR.WA, "ler_config", ler)
    if caixa is not None:
        monkeypatch.setattr(PUXAR.urllib.request, "urlopen", caixa.urlopen)


def _aplicar(monkeypatch, resultados: list[dict] | None = None) -> list:
    vistos: list = []

    def aplicar(con, item, serventia=None, agora=None):
        vistos.append(item)
        if resultados is not None:
            return resultados[len(vistos) - 1]
        return {"criadas": 1, "repetidas": 0}

    monkeypatch.setattr(PUXAR.WA, "aplicar_entrada", aplicar)
    return vistos


def _na_rede(req) -> dict:
    """O urllib title-caseia o nome antes de enviar."""
    return {k.title(): v for k, v in req.header_items()}


def _post(caixa: _Caixa):
    posts = [p for p in caixa.pedidos if p.get_method() == "POST"]
    assert len(posts) == 1
    return posts[0]


def test_get_e_ack_levam_bearer_e_x_caixa_segredo(monkeypatch):
    payload = _webhook("m-cab")
    corpo = json.dumps({"ok": True, "items": [
        {"id": "evt-1", "recebido_em": 1, "payload": payload},
    ]}).encode()
    caixa = _Caixa(corpo)
    _configurar(monkeypatch, caixa)
    _aplicar(monkeypatch)

    r = PUXAR.puxar_pendentes(object())

    assert r["ok"] is True
    assert len(caixa.pedidos) == 2
    for req in caixa.pedidos:
        enviados = _na_rede(req)
        assert enviados["Authorization"] == f"Bearer {SEGREDO}"
        assert enviados["X-Caixa-Segredo"] == SEGREDO


def test_envelope_entrega_o_payload_e_confirma_os_ids(monkeypatch):
    primeiro = _webhook("m-1")
    segundo = _webhook("m-2")
    corpo = json.dumps({"ok": True, "items": [
        {"id": "evt-1", "recebido_em": 1, "payload": primeiro},
        {"id": "evt-2", "recebido_em": 2, "payload": segundo},
    ]}).encode()
    caixa = _Caixa(corpo)
    _configurar(monkeypatch, caixa)
    vistos = _aplicar(monkeypatch, [
        {"criadas": 1, "repetidas": 0},
        {"criadas": 0, "repetidas": 1},
    ])

    r = PUXAR.puxar_pendentes(object())

    assert r == {"ok": True, "aplicadas": 1, "repetidas": 1}
    assert vistos == [primeiro, segundo]
    post = _post(caixa)
    assert post.full_url == CAIXA + "/ack"
    assert json.loads(post.data.decode()) == {"ids": ["evt-1", "evt-2"]}


def test_item_sem_envelope_passa_inteiro_e_nao_confirma(monkeypatch):
    item = {"id": "nao-e-envelope", "object": "whatsapp_business_account",
            "entry": []}
    corpo = json.dumps({"ok": True, "items": [item]}).encode()
    caixa = _Caixa(corpo)
    _configurar(monkeypatch, caixa)
    vistos = _aplicar(monkeypatch)

    r = PUXAR.puxar_pendentes(object())

    assert r["ok"] is True and r["aplicadas"] == 1
    assert vistos == [item]
    assert [p.get_method() for p in caixa.pedidos] == ["GET"]


def test_falha_no_ack_nao_quebra_a_puxada(monkeypatch, caplog):
    payload = _webhook("m-ack")
    corpo = json.dumps({"ok": True, "items": [
        {"id": "evt-9", "recebido_em": 1, "payload": payload},
    ]}).encode()
    caixa = _Caixa(corpo, ack_status=500)
    _configurar(monkeypatch, caixa)
    _aplicar(monkeypatch)

    with caplog.at_level(logging.WARNING, logger="wa_puxar"):
        r = PUXAR.puxar_pendentes(object())

    assert r == {"ok": True, "aplicadas": 1, "repetidas": 0}
    assert _post(caixa).full_url == CAIXA + "/ack"
    assert any("ack falhou" in rec.message for rec in caplog.records)
    assert SEGREDO not in caplog.text


def test_excecao_no_ack_nao_quebra_a_puxada(monkeypatch, caplog):
    payload = _webhook("m-exc")

    def http_get(url, segredo):
        return 200, json.dumps({"items": [
            {"id": "evt-7", "payload": payload},
        ]})

    def http_post(url, segredo, corpo):
        raise RuntimeError("ack fora")

    _configurar(monkeypatch)
    vistos = _aplicar(monkeypatch)

    with caplog.at_level(logging.WARNING, logger="wa_puxar"):
        r = PUXAR.puxar_pendentes(object(), http_get=http_get, http_post=http_post)

    assert r["ok"] is True and r["aplicadas"] == 1
    assert vistos == [payload]
    assert any(rec.message == "caixa-postal: ack falhou" for rec in caplog.records)
    assert SEGREDO not in caplog.text
    assert CAIXA not in caplog.text


def test_sem_ids_nao_chama_ack(monkeypatch):
    """Envelope sem id processa o payload e não confirma."""
    payload = _webhook("m-sem-id")
    corpo = json.dumps({"items": [
        {"recebido_em": 1, "payload": payload},
        {"id": "  ", "payload": _webhook("m-vazio")},
    ]}).encode()
    caixa = _Caixa(corpo)
    _configurar(monkeypatch, caixa)
    vistos = _aplicar(monkeypatch)

    r = PUXAR.puxar_pendentes(object())

    assert r["aplicadas"] == 2
    assert len(vistos) == 2
    assert [p.get_method() for p in caixa.pedidos] == ["GET"]
