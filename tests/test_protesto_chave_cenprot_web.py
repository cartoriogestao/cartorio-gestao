"""O quadro «Chave da CENPROT» da tela de Configurações.

A conta é a do layout oficial, igual para toda serventia. O quadro fica só com o
que é da casa: o IBGE e o código CRA. O campo de pesos saiu.
"""
from __future__ import annotations

import re

from test_protesto_aviso_web import _token, s  # noqa: F401

ROTA = "/configuracoes/cenprot-chave"
CODIGOS = {"ibge_uf": "12", "ibge_municipio": "34567", "ibge_cartorio": "3"}


def _db(s):  # noqa: F811
    from database import Database
    return Database(s["banco"])


def _salvar(s, **campos):  # noqa: F811
    tela = s["c"].get("/configuracoes").get_data(as_text=True)
    return s["c"].post(ROTA, data={"csrf_token": _token(tela), **campos},
                       follow_redirects=True).get_data(as_text=True)


def _formulario(html: str) -> str:
    form = re.search(rf'<form[^>]*action="{ROTA}"[^>]*>(.*?)</form>', html, re.S)
    assert form, "o quadro da chave sumiu da tela"
    return form.group(1)


def test_o_quadro_tem_os_codigos_e_o_token(s):  # noqa: F811
    form = _formulario(s["c"].get("/configuracoes").get_data(as_text=True))
    for nome in ("csrf_token", *CODIGOS):
        assert f'name="{nome}"' in form
    assert "Código CRA do tabelionato" in form


def test_o_campo_de_pesos_saiu_da_tela(s):  # noqa: F811
    html = s["c"].get("/configuracoes").get_data(as_text=True)
    assert "cenprot_chave_pesos" not in html
    assert "gravar_mesmo_assim" not in html
    assert "Pesos da conta" not in html


def test_a_linha_antiga_dos_pesos_nao_quebra_a_tela(s):  # noqa: F811
    _db(s).set_settings({"cenprot_chave_pesos": "torto"})
    resposta = s["c"].get("/configuracoes")
    assert resposta.status_code == 200
    assert "torto" not in resposta.get_data(as_text=True)
    assert s["c"].get("/protesto/cenprot-xml").status_code == 200


def test_os_codigos_se_gravam(s):  # noqa: F811
    html = _salvar(s, **CODIGOS)
    assert "Códigos da chave da CENPROT salvos" in html
    for chave, valor in CODIGOS.items():
        assert _db(s).get_setting(chave, "") == valor


def test_formato_errado_nao_se_grava(s):  # noqa: F811
    html = _salvar(s, ibge_uf="123")
    assert "Nada foi gravado" in html
    assert not _db(s).get_setting("ibge_uf", "")


def test_codigo_em_falta_avisa_que_nao_calcula(s):  # noqa: F811
    html = _salvar(s, ibge_uf="12")
    assert "não calcula a chave" in html


def test_campo_vazio_nao_apaga_o_que_esta_gravado(s):  # noqa: F811
    _db(s).set_settings(CODIGOS)
    _salvar(s, ibge_uf="", ibge_municipio="", ibge_cartorio="")
    assert _db(s).get_setting("ibge_municipio", "") == "34567"


def test_o_salvar_geral_nao_escreve_o_quadro():
    import inspect

    import app as APP
    fonte = inspect.getsource(APP)
    corpo = fonte[fonte.index("    def settings():"):
                  fonte.index("    def configuracoes_cenprot_chave():")]
    assert "ibge_cartorio" not in corpo


def test_a_tela_do_xml_diz_onde_preencher(s):  # noqa: F811
    html = s["c"].get("/protesto/cenprot-xml").get_data(as_text=True)
    assert "não está calculando a chave" in html
    assert "Chave da CENPROT" in html
    _db(s).set_settings(CODIGOS)
    html = s["c"].get("/protesto/cenprot-xml").get_data(as_text=True)
    assert "não está calculando a chave" not in html
