"""O catálogo de modelos no layout novo: 202 papéis não ficam abertos na mesma página.

O QUE ELES DEFENDEM
    Projeto do novo layout, 30/10/2026. A tela media 16 mil pixels, com o editor no fim. O risco é um
    grupo sumir, o editor sair junto da lista, ou o layout antigo mudar. A parte de baixo usa o sistema
    de pé, e roda na outra máquina.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

MOLDE = (RAIZ / "templates" / "modelos.html").read_text(encoding="utf-8-sig")


def test_cada_details_fecha():
    assert MOLDE.count("<details") - 1 == MOLDE.count("{% if layout_novo %}</details>{% endif %}")  # o da diferença fecha sozinho


def test_o_layout_antigo_mantem_os_titulos():
    assert "<h2>{{ g.atribuicao }}</h2>" in MOLDE
    assert "<h2>Papéis das certidões do Registro Civil</h2>" in MOLDE


def test_editando_so_o_editor_aparece():
    assert "{% set so_o_editor = layout_novo and editando %}" in MOLDE
    assert "{% if not so_o_editor %}" in MOLDE
    assert MOLDE.index("{% endif %}{# so_o_editor #}") < MOLDE.index('id="modelo-em-edicao"')


def test_cada_atribuicao_sai_uma_vez():
    import modelos_da_casa as MODELOS
    nomes = [a for a, _ in MODELOS.por_atribuicao()]
    assert len(nomes) == len(set(nomes))
    assert sum(len(i) for _, i in MODELOS.por_atribuicao()) == len(MODELOS.CATALOGO)


def test_a_busca_so_existe_no_layout_novo():
    assert "data-cg-procurar-papel" in MOLDE
    assert "{% if layout_novo and not editando %}" in MOLDE


# ------------------------------------------------------------- com o sistema de pé


def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _entrar(app, usuario: str):
    d = app.extensions["db"]
    try:
        d.create_user(usuario, "Operador Exemplo", "Senha#12345", "ADMIN")
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


def test_os_grupos_vem_recolhidos_e_o_filtro_abre(cg_app):
    c = _entrar(cg_app, "modelos_a")
    _layout(c, "novo")
    todos = c.get("/modelos").get_data(as_text=True)
    assert "data-cg-grupo-de-papeis open" not in todos
    filtrado = c.get("/modelos?atribuicao=Protesto").get_data(as_text=True)
    assert "data-cg-grupo-de-papeis open" in filtrado


def test_o_editor_aparece_sozinho(cg_app):
    c = _entrar(cg_app, "modelos_b")
    _layout(c, "novo")
    html = c.get("/modelos?editar=RI_CABECALHO").get_data(as_text=True)
    assert 'id="modelo-em-edicao"' in html and "data-cg-grupo-de-papeis" not in html
    assert "Todos os papéis" in html


def test_o_layout_antigo_nao_mudou(cg_app):
    c = _entrar(cg_app, "modelos_c")
    _layout(c, "antigo")
    html = c.get("/modelos").get_data(as_text=True)
    assert "data-cg-grupo-de-papeis" not in html and "<h2>Registro de Imóveis</h2>" in html
