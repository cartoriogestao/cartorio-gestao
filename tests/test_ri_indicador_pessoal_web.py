"""Smoke — tela Indicador Pessoal (consulta local; sem envio ONR)."""

from onr_web_smoke_routes import path_for


def test_indicador_pessoal_responde_200(cg_casa_logada):
    r = cg_casa_logada.get(path_for("ri_indicador_pessoal"))
    assert r.status_code == 200
