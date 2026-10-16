"""Smoke — tela Indicador Pessoal (consulta local; sem envio ONR)."""

from onr_web_smoke_routes import path_for


def test_indicador_pessoal_responde_200(cg_casa_logada):
    # `cg_casa_logada` é o pacote da casa (dict), e não o cliente: `.get` do
    # dict devolvia None. O cliente mora em ["c"], como em
    # test_ri_onr_export_web.py (corrigido em 14/10/2026).
    r = cg_casa_logada["c"].get(path_for("ri_indicador_pessoal"))
    assert r.status_code == 200
