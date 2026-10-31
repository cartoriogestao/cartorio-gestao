"""As listas de Notas e o painel: lavrar direto, as vistas, e o layout antigo intacto.

O QUE ELES DEFENDEM
    O pedido que abriu este trabalho: «ausencia de click facil para lavrar procuracoes
    publicas». Lavrar na lista abre o ato da espécie, sem tela de escolher no meio; e o que
    está em lavratura vem primeiro. Quem continua no layout antigo vê a lista de sempre.

    A primeira parte lê arquivo. A segunda usa o sistema de pé, e roda na máquina do balcão.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import navegacao as NAV  # noqa: E402
import notas_familias as NF  # noqa: E402
import notas_modelos as NMOD  # noqa: E402
from notas_schema import TIPOS_ATO  # noqa: E402

LISTA = (RAIZ / "templates" / "notas_atos.html").read_text(encoding="utf-8")
PAINEL = (RAIZ / "templates" / "notas_painel.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("tipo,codigo", sorted(NAV.LAVRAR_DIRETO.items()))
def test_a_especie_abre_o_modelo_dela(tipo, codigo):
    """Modelo de outra espécie abriria o livro errado: `notas_ato_novo` obedece ao modelo."""
    assert tipo in TIPOS_ATO
    modelo = NMOD.por_codigo(codigo)
    assert modelo, codigo
    assert NF.tipo_ato_do_modelo(modelo["tipo"]) == tipo


def test_toda_lista_de_especie_do_menu_lavra_direto():
    tipos = {i["args"]["tipo"] for m in NAV.MODULOS_DA_BARRA if m["chave"] == "NOTAS"
             for _n, itens in m["secoes"] for i in itens if i["endpoint"] == "notas_atos" and "tipo" in i["args"]}
    assert tipos == set(NAV.LAVRAR_DIRETO), tipos ^ set(NAV.LAVRAR_DIRETO)


def test_a_lista_tem_o_nome_que_o_menu_da_a_ela():
    assert NAV.titulo_da_lista("PROCURACAO") == "Procurações"
    assert NAV.titulo_da_lista("RENUNCIA") == "Renúncias"
    assert NAV.titulo_da_lista("") == ""


def test_as_listas_novas_estao_declaradas():
    """A paridade com o menu antigo aceita só o que foi declarado como novo."""
    assert ("notas_atos", (("familia", "escrituras"),)) in NAV.ENTRADAS_NOVAS
    assert ("notas_atos", (("familia", "atas"),)) in NAV.ENTRADAS_NOVAS


def test_o_layout_antigo_continua_com_a_fileira_de_botoes():
    corpo = LISTA[LISTA.index("{% block content %}"):]
    assert corpo.index("{% if layout_novo %}") < corpo.index("{% else %}") < corpo.index("&larr;")
    assert "{% if layout_novo %}" in PAINEL
    assert "url_for('notas_reconhecimentos') }}\">Reconhecimentos</a>" in PAINEL


def test_as_vistas_nao_se_perdem_ao_mudar_de_pagina_nem_ao_filtrar():
    assert LISTA.count("vista=vista or none") == 2
    assert '<input type="hidden" name="vista" value="{{ vista }}">' in LISTA


# ------------------------------------------------------------- com o sistema de pé

def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _entrar(app, usuario: str, papel: str = "ADMIN"):
    d = app.extensions["db"]
    try:
        d.create_user(usuario, "Operador Exemplo", "Senha#12345", papel)
    except Exception:                                              # noqa: BLE001
        pass
    c = app.test_client()
    c.post("/login", data={"username": usuario, "password": "Senha#12345",
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


def _layout(c, qual: str) -> None:
    c.post("/preferencias/layout", data={
        "layout": qual, "next": "/", "csrf_token": _token(c.get("/").get_data(as_text=True))})


def test_na_lista_das_procuracoes_lavrar_abre_o_ato_direto(cg_app):
    c = _entrar(cg_app, "lista_a")
    _layout(c, "novo")
    html = c.get("/notas/atos?tipo=PROCURACAO").get_data(as_text=True)
    assert 'name="modelo_codigo" value="NT-PROC-PUBLICA"' in html
    assert "Lavrar procuração" in html
    r = c.post("/notas/atos/novo", data={"tipo": "PROCURACAO", "modelo_codigo": "NT-PROC-PUBLICA",
                                         "csrf_token": _token(html)})
    assert re.search(r"/notas/atos/\d+$", r.headers["Location"])


def test_o_que_esta_em_lavratura_abre_primeiro(cg_app):
    c = _entrar(cg_app, "lista_b")
    _layout(c, "novo")
    html = c.get("/").get_data(as_text=True)
    c.post("/notas/atos/novo", data={"tipo": "RENUNCIA", "modelo_codigo": "NT-RENUNCIA-MANDATO",
                                     "csrf_token": _token(html)})
    html = c.get("/notas/atos?tipo=RENUNCIA").get_data(as_text=True)
    assert re.search(r'cg-vista atual"[^>]*aria-current="true"\s+href="[^"]*vista=em_lavratura', html)
    assert "Continuar" in html
    assert "Continuar" not in c.get("/notas/atos?tipo=RENUNCIA&vista=lavrados").get_data(as_text=True)


def test_quem_continua_no_layout_antigo_ve_a_lista_de_sempre(cg_app):
    c = _entrar(cg_app, "lista_c")
    _layout(c, "antigo")
    html = c.get("/notas/atos?tipo=PROCURACAO").get_data(as_text=True)
    assert "cg-vistas" not in html and "Continuar" not in html


def test_o_painel_tem_as_portas_e_o_que_espera(cg_app):
    c = _entrar(cg_app, "lista_d")
    _layout(c, "novo")
    html = c.get("/notas").get_data(as_text=True)
    assert "Lavrar agora" in html and "O que espera você" in html
    assert 'value="NT-PROC-PUBLICA"' in html


def test_quem_so_confere_nao_recebe_porta_de_lavrar(cg_app):
    c = _entrar(cg_app, "lista_e", "AUDITOR")
    _layout(c, "novo")
    assert 'value="NT-PROC-PUBLICA"' not in c.get("/notas").get_data(as_text=True)
    assert 'value="NT-PROC-PUBLICA"' not in c.get("/notas/atos?tipo=PROCURACAO").get_data(as_text=True)
