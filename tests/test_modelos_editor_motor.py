"""Cliente do motor — mock do contrato e fallback local."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from unittest import mock

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import modelos_editor_motor as MOTOR
import modelos_elementos_schema as ESQ
import ri_schema
from modelos_editor_schema import init_modelos_editor_schema


@pytest.fixture()
def con(tmp_path):
    c = sqlite3.connect(tmp_path / "t.sqlite3")
    c.row_factory = sqlite3.Row
    ri_schema.init_ri_schema(c)
    ESQ.init_modelos_elementos_schema(c)
    init_modelos_editor_schema(c)
    yield c
    c.close()


def test_fallback_previa_marca_aproximada(con, monkeypatch):
    monkeypatch.setattr(MOTOR, "motor_disponivel", lambda: False)
    resp = MOTOR.previa(
        con, area="RCPN", template_id="RC_TERMO_NASCIMENTO",
        form_fallback={"parte_corpo": ""})
    assert resp.get("aproximada") is True
    assert any("aproximada" in a.lower() or "motor" in a.lower()
               for a in (resp.get("avisos") or []))
    assert "html" in resp or resp.get("ok") is False


def test_fallback_campos_locais(monkeypatch):
    monkeypatch.setattr(MOTOR, "motor_disponivel", lambda: False)
    r = MOTOR.campos(area="RCPN", tipo="RC_TERMO_NASCIMENTO")
    assert r["fonte"] == "fallback"
    assert isinstance(r["campos"], list)
    nomes = {c["nome"] for c in r["campos"]}
    assert "serventia.cns" in nomes or "serventia.nome" in nomes


def test_fallback_bloqueados_vazios(monkeypatch):
    monkeypatch.setattr(MOTOR, "motor_disponivel", lambda: False)
    r = MOTOR.trechos_bloqueados(area="RCPN", tipo="RC_TERMO_NASCIMENTO")
    assert r["fonte"] == "fallback"
    assert r["trechos"] == []
    assert r["avisos"]


def test_motor_mock_contrato_previa(con):
    payload_esperado = {
        "area": "RCPN",
        "template_id": "RC_TERMO_NASCIMENTO",
        "versao": None,
        "conteudo": {"CORPO": "x"},
        "dados": {},
        "assento_id": None,
        "papel": "a4",
        "formato": "html",
    }
    resposta = {
        "html": "<p>ok</p>",
        "bytes": None,
        "paginas": 1,
        "avisos": [],
        "erros": [],
        "placeholders_usados": ["numero"],
        "placeholders_desconhecidos": [],
    }

    def fake_http(method, url, body=None, timeout=8.0):
        assert method == "POST"
        assert url.endswith("/modelos/api/previa")
        assert body["template_id"] == "RC_TERMO_NASCIMENTO"
        assert body["papel"] in ("a4", "seguranca")
        assert body["formato"] in ("html", "pdf", "odt")
        return resposta, 200

    with mock.patch.object(MOTOR, "_http_json", side_effect=fake_http):
        out = MOTOR.previa_via_motor_http(payload_esperado, app_url="http://x")
    assert out["html"] == "<p>ok</p>"
    assert out["placeholders_usados"] == ["numero"]


def test_motor_mock_campos():
    lista = [{"nome": "numero", "rotulo": "{{numero}}", "tipo": "texto",
              "obrigatorio": True, "exemplo": "1", "grupo": "Ato"}]

    def fake_http(method, url, body=None, timeout=8.0):
        assert method == "GET"
        assert "/modelos/api/campos" in url
        return lista, 200

    with mock.patch.object(MOTOR, "_http_json", side_effect=fake_http):
        out = MOTOR.campos_via_motor_http(area="RCPN", tipo="RC_TERMO_NASCIMENTO",
                                         app_url="http://x")
    assert out[0]["nome"] == "numero"


def test_motor_404_dispara_indisponivel():
    def boom(method, url, body=None, timeout=8.0):
        raise MOTOR.MotorIndisponivel("404")

    with mock.patch.object(MOTOR, "_http_json", side_effect=boom):
        with pytest.raises(MOTOR.MotorIndisponivel):
            MOTOR.previa_via_motor_http({"area": "RCPN"}, app_url="http://x")


def test_motor_real_quando_presente():
    """Se modelos_motor* estiver instalado, o cliente usa o contrato real."""
    if not MOTOR.motor_disponivel():
        import pytest
        pytest.skip("modelos_motor ausente neste ambiente")
    r = MOTOR.campos(area="RCPN", tipo="RC_TERMO_NASCIMENTO")
    assert r["fonte"] == "motor"
    assert isinstance(r["campos"], list)
    tb = MOTOR.trechos_bloqueados(area="RCPN", tipo="RC_MOLDE_NASCIMENTO")
    assert tb["fonte"] == "motor"
    assert isinstance(tb["trechos"], list)


def test_previa_motor_real_contrato(con):
    if not MOTOR.motor_disponivel():
        import pytest
        pytest.skip("modelos_motor ausente neste ambiente")
    resp = MOTOR.previa(
        con, area="RCPN", template_id="RC_MOLDE_NASCIMENTO",
        papel="a4", formato="html")
    assert resp.get("fonte") == "motor"
    assert resp.get("aproximada") in (False, None)
    # Contrato: chaves esperadas
    for k in ("avisos", "erros", "placeholders_usados",
              "placeholders_desconhecidos"):
        assert k in resp
    # Sem selo / sem gravação — só checa que não explode
    assert isinstance(resp.get("erros"), list)
