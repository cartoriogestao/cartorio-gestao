"""A ficha da matrícula em abas, com o sistema de pé: as duas molduras oferecem o mesmo.

O QUE ELES DEFENDEM
    Que trocar de layout não tira botão nenhum. A comparação é do que o servidor recebe, e não
    da aparência: todo endereço de formulário da ficha tem de estar nas duas molduras.
"""
from __future__ import annotations

import re

import pytest


@pytest.fixture(scope="module")
def app(cg_app):
    return cg_app


def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _entrar(app, usuario: str = "mat_a", papel: str = "ADMIN"):
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


def _matricula(app) -> int:
    d = app.extensions["db"]
    with d.transaction() as con:
        from bd_nativo import banco
        return int(banco(con).escrever(
            """INSERT INTO ri_matriculas (numero, origem, tipo_ficha, teor, criado_em)
               VALUES (%s, 'MANUAL', 'ESTRUTURADA', 'Lote de teste.', %s) RETURNING id""",
            ("90001", d.now()))[0]["id"])


def _formularios(html: str) -> set:
    # A ficha acaba no `</main>`: depois dele a moldura nova põe os formulários
    # de busca de cada módulo (`nav.procurar`), que não são da ficha.
    corpo = html[html.index('class="content"'):]
    fim = corpo.find("</main>")
    corpo = corpo if fim < 0 else corpo[:fim]
    return {e for e in re.findall(r'<form[^>]*\baction="([^"]+)"', corpo) if "/preferencias/" not in e}


def test_o_layout_antigo_nao_tem_abas(app):
    c = _entrar(app, "mat_b")
    _layout(c, "antigo")
    html = c.get(f"/registro-imoveis/{_matricula(app)}").get_data(as_text=True)
    assert "data-cg-regua" not in html and "cg-ficha" not in html and "fases.js" not in html
    assert "O que espera ação" not in html


def test_o_layout_novo_abre_no_resumo(app):
    c = _entrar(app, "mat_c")
    _layout(c, "novo")
    html = c.get(f"/registro-imoveis/{_matricula(app)}").get_data(as_text=True)
    assert 'data-inicial="resumo"' in html
    assert 'data-cg-fase="novo-ato"' in html
    assert "Situação jurídica" in html


def test_quem_pede_para_lavrar_abre_em_novo_ato(app):
    c = _entrar(app, "mat_d")
    _layout(c, "novo")
    html = c.get(f"/registro-imoveis/{_matricula(app)}?lavrar=1").get_data(as_text=True)
    assert 'data-inicial="novo-ato"' in html


def test_as_duas_molduras_oferecem_o_mesmo(app):
    c = _entrar(app, "mat_e")
    endereco = f"/registro-imoveis/{_matricula(app)}"
    _layout(c, "antigo")
    antigo = c.get(endereco).get_data(as_text=True)
    _layout(c, "novo")
    novo = c.get(endereco).get_data(as_text=True)
    assert _formularios(antigo) == _formularios(novo)
    assert _formularios(novo), "o varredor deixou de achar os formulários"
