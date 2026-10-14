# -*- coding: utf-8 -*-
"""Livro 3 - editor de modelos e rota de previa."""
from __future__ import annotations

import re

import modelos_da_casa as MOD
import pytest

pytestmark = pytest.mark.usefixtures("cg_casa_logada")


def _token(html: str) -> str:
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert m, "csrf_token ausente"
    return m.group(1)


def test_livro3_modelos_tela_200_com_editor(cg_casa_logada):
    c = cg_casa_logada["c"]
    html = c.get("/livro3/modelos?editar=RI_LIVRO3_FICHA").get_data(as_text=True)
    assert c.get("/livro3/modelos").status_code == 200
    assert "data-modelo-editor" in html
    assert "data-modelo-previa" in html
    assert "Visualiza" in html
    assert "livro3_modelos_previa" in html or "/livro3/modelos/previa" in html
    assert "textarea" in html


def test_livro3_previa_usa_ensaio_registro_1243(cg_casa_logada):
    c = cg_casa_logada["c"]
    pagina = c.get("/livro3/modelos?editar=RI_LIVRO3_FICHA")
    token = _token(pagina.get_data(as_text=True))
    corpo = MOD.padrao_de("RI_LIVRO3_FICHA")
    r = c.post(
        "/livro3/modelos/previa",
        data={"csrf_token": token, "ato": "RI_LIVRO3_FICHA", "parte_corpo": corpo},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code == 200
    dados = r.get_json()
    assert dados["ok"] is True
    assert "1243" in dados["html"]
    assert "HIPOTECA" in dados["html"]
    assert "BANCO DO BRASIL" in dados["html"]


def test_modelos_admin_previa_livro3_ficha_ensaio(cg_casa_logada):
    c = cg_casa_logada["c"]
    pagina = c.get("/modelos", query_string={"editar": "RI_LIVRO3_FICHA"})
    token = _token(pagina.get_data(as_text=True))
    corpo = MOD.padrao_de("RI_LIVRO3_FICHA")
    r = c.post(
        "/modelos/previa",
        data={"csrf_token": token, "ato": "RI_LIVRO3_FICHA", "parte_corpo": corpo},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert r.status_code == 200
    dados = r.get_json()
    assert dados["ok"] is True
    assert "1243" in dados["html"]
