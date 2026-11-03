"""O tamanho da letra e as colunas da esquerda são da pessoa, e valem nas duas molduras.

Pedidos do oficial, 02/11/2026: «não tem também como configurar a proporção manualmente? Alguém que não
enxerga tão bem poder aumentar as fontes e logos do sistema?» e «precisa também ter uma opção de recolher
as colunas da esquerda para deixar mais campo pra tela». O que o navegador vê (o zoom sem estourar a
janela, a faixa de ícones, a tecla «[») está em `test_layout_no_navegador`.

Os nomes são fictícios, como em todo teste desta casa.
"""
from __future__ import annotations

import re

import pytest

from conftest import cg_login

SENHA = "Senha#12345"


def _token(c) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', c.get("/").get_data(as_text=True)).group(1)


def _postar(c, **dados):
    return c.post("/preferencias/aparencia", data={"csrf_token": _token(c), "next": "/", **dados})


@pytest.fixture
def mario(cg_casa_logada):
    return cg_casa_logada


def test_a_escala_escolhida_vai_ao_html_da_pessoa(mario):
    c = mario["c"]
    assert 'data-escala=' not in c.get("/").get_data(as_text=True)
    assert _postar(c, escala="130").status_code == 302
    html = c.get("/").get_data(as_text=True)
    assert 'data-escala="130"' in html and "--cg-escala:1.3" in html


def test_escala_que_nao_existe_nao_se_grava(mario):
    c = mario["c"]
    _postar(c, escala="400")
    assert 'data-escala=' not in c.get("/").get_data(as_text=True)
    assert mario["db"].get_setting("escala_usuario_1", "") in ("", "100")


def test_as_colunas_recolhidas_pelo_botao_nao_recarregam_e_ficam(mario):
    c = mario["c"]
    r = c.post("/preferencias/aparencia", data={"csrf_token": _token(c), "colunas": "recolhidas"},
               headers={"X-Requested-With": "fetch"})
    assert r.status_code == 204
    html = c.get("/").get_data(as_text=True)
    assert re.search(r'class="cg-app[^"]*cg-recolhido', html)
    assert 'name="colunas" value="abertas"' in html and 'aria-pressed="true"' in html
    _postar(c, colunas="abertas")
    assert not re.search(r'class="cg-app[^"]*cg-recolhido', c.get("/").get_data(as_text=True))


def test_a_escala_vale_tambem_na_moldura_antiga(mario):
    c = mario["c"]
    _postar(c, escala="150")
    c.post("/preferencias/layout", data={"csrf_token": _token(c), "layout": "antigo", "next": "/"})
    html = c.get("/").get_data(as_text=True)
    assert 'data-layout="novo"' not in html
    assert 'data-escala="150"' in html and 'class="sidebar-escalas"' in html


def test_a_escolha_e_de_cada_um(mario, cg_app):
    c = mario["c"]
    _postar(c, escala="150", colunas="recolhidas")
    mario["db"].create_user("beatriz", "BEATRIZ EXEMPLO DE SOUZA", SENHA, "USER")
    outra = cg_app.test_client()
    cg_login(outra, "beatriz", SENHA)
    html = outra.get("/").get_data(as_text=True)
    assert 'data-escala=' not in html and not re.search(r'class="cg-app[^"]*cg-recolhido', html)
