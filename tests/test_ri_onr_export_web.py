"""Smoke — exportação ONR e Next Cloud (papéis ADMIN)."""

from onr_web_smoke_routes import path_for


def test_exportacao_onr_abre(cg_casa_logada):
    r = cg_casa_logada["c"].get(path_for("ri_onr"))
    assert r.status_code == 200


def test_next_cloud_abre(cg_casa_logada):
    r = cg_casa_logada["c"].get(path_for("ri_onr_next_cloud"))
    assert r.status_code == 200
