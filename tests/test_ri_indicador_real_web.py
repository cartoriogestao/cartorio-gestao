"""Smoke — tela Indicador Real (consulta/acervo)."""

from onr_web_smoke_routes import path_for


def test_indicador_real_responde_200(cg_casa_logada):
    r = cg_casa_logada.get(path_for("ri_indicador_real"))
    assert r.status_code == 200
