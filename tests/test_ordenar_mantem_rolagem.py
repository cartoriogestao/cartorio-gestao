"""Ordenar pelo título da coluna sem voltar ao topo (of-0143).

Estes testes defendem a ligação: quem ordena carrega o script, nos dois layouts, e quem não ordena não
carrega. Eles NÃO provam a rolagem, que só existe num navegador: essa conferência fica registrada no PR.
"""
from __future__ import annotations

import re

import pytest

SCRIPT = re.compile(r'<script defer src="[^"]*/ordenar_rolagem\.js\?v=([^"]*)"></script>')
TELAS = ["/processos?vista=TODOS", "/tarefas","/administrativo/produtividade"]


def _usar_layout(c, layout: str) -> None:
    pagina = c.get("/").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', pagina).group(1)
    r = c.post("/preferencias/layout", data={"layout": layout, "next": "/", "csrf_token": token})
    assert r.status_code == 302


def _pagina(c, endereco: str, layout: str) -> str:
    r = c.get(endereco)
    assert r.status_code == 200, endereco
    html = r.get_data(as_text=True)
    assert ("cg-app" in html) == (layout == "novo"), "a moldura não é a pedida"
    return html


@pytest.mark.parametrize("layout", ["antigo", "novo"])
@pytest.mark.parametrize("tela", TELAS)
def test_a_tela_que_ordena_carrega_o_script_com_a_versao(cg_casa_logada, tela, layout):
    c = cg_casa_logada["c"]
    _usar_layout(c, layout)
    achados = SCRIPT.findall(_pagina(c, tela, layout))
    assert len(achados) == 1, "o script deve vir uma vez"
    # A macro importada não enxerga o VERSION da tela: sem o argumento, sairia `?v=` vazio.
    assert re.fullmatch(r"\d+\.\d+\.\d+", achados[0]), achados[0]


@pytest.mark.parametrize("layout", ["antigo", "novo"])
@pytest.mark.parametrize("tela", TELAS)
def test_o_titulo_continua_link_e_a_ordem_continua_no_endereco(cg_casa_logada, tela, layout):
    c = cg_casa_logada["c"]
    _usar_layout(c, layout)
    links = re.findall(r'<a href="([^"]*)" class="ordenar[^"]*"', _pagina(c, tela, layout))
    assert links, "sumiram os títulos que ordenam"
    assert all("ordem=" in h for h in links)


@pytest.mark.parametrize("layout", ["antigo", "novo"])
def test_tela_sem_ordenacao_nao_carrega_o_script(cg_casa_logada, layout):
    c = cg_casa_logada["c"]
    _usar_layout(c, layout)
    assert "ordenar_rolagem" not in _pagina(c, "/selos", layout)
