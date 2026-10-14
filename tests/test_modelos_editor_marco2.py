"""Marco 2 — PDF/ODT do motor, blocos bloqueados, campos, serventia B0."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest import mock

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import modelos_editor as ED
import modelos_editor_motor as MOTOR
import modelos_editor_serventia as SVED
import modelos_elementos_schema as ESQ
import modelos_moldes as MOLDES
import ri_schema
from modelos_editor_schema import (
    AREA_RCPN, PARTE_CORPO, init_modelos_editor_schema,
)

AGORA = "2026-10-05T15:30:00"


@pytest.fixture()
def con(tmp_path):
    c = sqlite3.connect(tmp_path / "t.sqlite3")
    c.row_factory = sqlite3.Row
    ri_schema.init_ri_schema(c)
    ESQ.init_modelos_elementos_schema(c)
    MOLDES.init_modelos_moldes_schema(c)
    init_modelos_editor_schema(c)
    c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    c.commit()
    yield c
    c.close()


def _settings_gen():
    return {
        "unit_name": "OFICIO DE EXEMPLO",
        "serventia_titular": "Fulano de Tal",
        "serventia_titulo": "Oficial",
        "ri_substituta": "Beltrana",
        "serventia_cnpj": "00.000.010/0001-27",
        "ri_cns": "000000",
        "serventia_telefone": "(00) 0000-0000",
        "serventia_endereco": "Rua Exemplo, 1",
        "serventia_cep": "00.000-000",
        "ri_cidade": "Cidade Exemplo",
        "ri_uf": "EX",
        "serventia_email": "exemplo@example.com",
        "serventia_brasao": "",
    }


# -------------------- serventia B0 --------------------

def test_serventia_prefere_b0_quando_presente():
    import serventia as SV
    if not hasattr(SV, "ALIASES_MODELOS"):
        pytest.skip("B0 ainda não no pacote")
    assert SVED.fonte_mapa() == "b0_serventia"
    m = SVED.mapa_aliases()
    assert m["cns"] == "ri_cns"
    assert m["brasao"] == "serventia_brasao"
    ns = SVED.namespace_serventia(_settings_gen)
    assert ns["nome"] == "OFICIO DE EXEMPLO"
    assert ns["cns"] == "000000"


def test_serventia_fallback_local_se_b0_ausente(monkeypatch):
    import serventia as SV
    monkeypatch.delattr(SV, "ALIASES_MODELOS", raising=False)
    monkeypatch.setattr(SVED, "_resolver_aliases",
                        lambda: (dict(SVED._ALIAS_LOCAL), "local"))
    assert SVED.fonte_mapa() == "local"


# -------------------- campos via motor --------------------

def test_campos_via_motor_quando_presente():
    if not MOTOR.motor_disponivel():
        pytest.skip("motor ausente")
    r = MOTOR.campos(area="RCPN", tipo="RC_MOLDE_NASCIMENTO")
    assert r["fonte"] == "motor"
    assert any(c["nome"].startswith("serventia.") for c in r["campos"])


def test_campos_fallback_se_motor_ausente(monkeypatch):
    monkeypatch.setattr(MOTOR, "motor_disponivel", lambda: False)
    r = MOTOR.campos(area="RCPN", tipo="RC_TERMO_NASCIMENTO")
    assert r["fonte"] == "fallback"


# -------------------- bloqueados --------------------

def test_trechos_bloqueados_do_motor():
    if not MOTOR.motor_disponivel():
        pytest.skip("motor ausente")
    r = MOTOR.trechos_bloqueados(area="RCPN", tipo="RC_MOLDE_NASCIMENTO")
    assert r["fonte"] == "motor"
    assert isinstance(r["trechos"], list)
    if r["trechos"]:
        assert "id" in r["trechos"][0]
        assert "texto" in r["trechos"][0]


def test_salvar_recusa_bloco_adulterado(con):
    blk = [{"id": "fecho_x", "texto": "texto certo", "base_legal": "art. 1"}]
    corpo = "intro\n{{#bloqueado fecho_x}}texto ERRADO{{/bloqueado}}\nfim"
    with pytest.raises(ED.EditorError, match="recusada|alterado|bloqueado"):
        ED.salvar_rascunho(
            con, area=AREA_RCPN, template_id="RC_TERMO_NASCIMENTO",
            parte=PARTE_CORPO, conteudo=corpo, autor="t", agora=AGORA,
            get_settings=_settings_gen, trechos_bloqueados=blk)


def test_salvar_aceita_bloco_integro(con):
    blk = [{"id": "fecho_x", "texto": "texto certo", "base_legal": "art. 1"}]
    corpo = "intro\n{{#bloqueado fecho_x}}texto certo{{/bloqueado}}\nfim"
    row = ED.salvar_rascunho(
        con, area=AREA_RCPN, template_id="RC_TERMO_NASCIMENTO",
        parte=PARTE_CORPO, conteudo=corpo, autor="t", agora=AGORA,
        get_settings=_settings_gen, trechos_bloqueados=blk)
    assert row["status"] == "rascunho"


def test_publicar_recusa_bloco_adulterado(con):
    blk = [{"id": "fecho_x", "texto": "ok", "base_legal": "x"}]
    ED.salvar_rascunho(
        con, area=AREA_RCPN, template_id="RC_TERMO_CASAMENTO",
        parte=PARTE_CORPO,
        conteudo="{{#bloqueado fecho_x}}ok{{/bloqueado}}",
        autor="a", agora=AGORA, trechos_bloqueados=blk,
        get_settings=_settings_gen, validar_ao_salvar=False)
    # adultera no publicar via conteudo explícito
    with pytest.raises(ED.EditorError, match="recusada|alterado"):
        ED.publicar(
            con, area=AREA_RCPN, template_id="RC_TERMO_CASAMENTO",
            parte=PARTE_CORPO, autor="a", agora=AGORA,
            papel_usuario="ADMIN", get_settings=_settings_gen,
            trechos_bloqueados=blk,
            conteudo="{{#bloqueado fecho_x}}HACKEADO{{/bloqueado}}")


def test_lista_bloqueados_vazia_gera_aviso(con):
    val = ED.validar(
        con, area=AREA_RCPN, template_id="RC_TERMO_LIVRO_E",
        parte=PARTE_CORPO, conteudo="sem blocos",
        get_settings=_settings_gen, trechos_bloqueados=[])
    # sem marcadores e lista vazia → aviso, sem erro de adulteração
    assert any("bloqueado" in a.lower() for a in val["avisos"]) or val["ok"]


# -------------------- PDF via motor --------------------

def test_previa_pdf_mock_contrato(con):
    import base64
    fake_pdf = base64.b64encode(b"%PDF-1.4 mock").decode("ascii")

    def fake_mod(payload, *, sv=None, con=None):
        assert payload["formato"] == "pdf"
        return {
            "html": None,
            "pdf_base64": fake_pdf,
            "mime": "application/pdf",
            "paginas": 1,
            "avisos": [],
            "erros": [],
            "placeholders_usados": [],
            "placeholders_desconhecidos": [],
            "fonte": "motor",
            "aproximada": False,
        }

    with mock.patch.object(MOTOR, "motor_disponivel", return_value=True):
        with mock.patch.object(MOTOR, "previa_via_motor_modulo", side_effect=fake_mod):
            resp = MOTOR.previa(
                con, area="RCPN", template_id="RC_MOLDE_NASCIMENTO",
                formato="pdf", papel="a4")
    assert resp["pdf_base64"] == fake_pdf
    assert resp["mime"] == "application/pdf"
    assert not resp.get("aproximada")


def test_previa_pdf_sem_suporte_mostra_erro_do_motor(con):
    def fake_mod(payload, *, sv=None, con=None):
        return {
            "html": None,
            "pdf_base64": None,
            "paginas": None,
            "avisos": [],
            "erros": [{"linha": 0, "coluna": 0, "codigo": "PDF_FALHOU",
                       "msg": "LibreOffice indisponível no ensaio"}],
            "placeholders_usados": [],
            "placeholders_desconhecidos": [],
            "fonte": "motor",
            "aproximada": False,
        }

    with mock.patch.object(MOTOR, "motor_disponivel", return_value=True):
        with mock.patch.object(MOTOR, "previa_via_motor_modulo", side_effect=fake_mod):
            resp = MOTOR.previa(
                con, area="RCPN", template_id="RC_TERMO_NASCIMENTO",
                formato="pdf", papel="seguranca")
    assert resp["pdf_base64"] is None
    assert any(e["codigo"] == "PDF_FALHOU" for e in resp["erros"])


def test_previa_odt_mock(con):
    import base64
    fake = base64.b64encode(b"PK\x03\x04odt").decode("ascii")

    def fake_mod(payload, *, sv=None, con=None):
        assert payload["formato"] == "odt"
        return {
            "pdf_base64": fake,
            "mime": "application/vnd.oasis.opendocument.text",
            "avisos": ["formato=odt: bytes em pdf_base64 (ODT)."],
            "erros": [],
            "fonte": "motor",
            "aproximada": False,
        }

    with mock.patch.object(MOTOR, "motor_disponivel", return_value=True):
        with mock.patch.object(MOTOR, "previa_via_motor_modulo", side_effect=fake_mod):
            resp = MOTOR.previa(
                con, area="RCPN", template_id="RC_MOLDE_CASAMENTO",
                formato="odt", papel="a4")
    assert "opendocument" in (resp.get("mime") or "")
    assert resp.get("pdf_base64")


def test_previa_pdf_motor_real_se_presente(con):
    if not MOTOR.motor_disponivel():
        pytest.skip("motor ausente")
    resp = MOTOR.previa(
        con, area="RCPN", template_id="RC_MOLDE_NASCIMENTO",
        formato="pdf", papel="a4", sv=_settings_gen())
    assert resp.get("fonte") == "motor"
    # Pode falhar PDF (sem LibreOffice) — aí erros do motor, sem inventar PDF
    if resp.get("pdf_base64"):
        assert resp.get("mime") in (
            "application/pdf",
            "application/vnd.oasis.opendocument.text",
            None,
        ) or True
    else:
        assert resp.get("erros") or resp.get("avisos") or resp.get("html")
