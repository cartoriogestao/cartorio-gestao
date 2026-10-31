"""A ficha do ato em fases, com o sistema de pé: as duas molduras oferecem o mesmo.

O QUE ELES DEFENDEM
    Que trocar de layout não tira botão nenhum. A comparação é do que o servidor recebe, e
    não da aparência: toda ação e todo endereço de formulário da ficha têm de estar nas
    duas molduras. Só o papel na DOI sai da procuração no layout novo, de propósito.
"""
from __future__ import annotations

import re

import pytest


@pytest.fixture(scope="module")
def app(cg_app):
    return cg_app


def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _entrar(app, usuario: str = "fases_a", papel: str = "ADMIN"):
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


def _abrir_ato(c, tipo: str, modelo: str) -> str:
    r = c.post("/notas/atos/novo", data={
        "tipo": tipo, "modelo_codigo": modelo,
        "csrf_token": _token(c.get("/").get_data(as_text=True))})
    assert r.status_code == 302, r.status_code
    return r.headers["Location"]


def _conteudo(html: str) -> str:
    """Só a ficha: a barra, o Novo e o sino têm formulários próprios em cada
    moldura — e a nova ainda põe, depois do `</main>`, os formulários de busca
    de cada módulo (`nav.procurar`). A ficha acaba no `</main>`."""
    corpo = html[html.index('class="content"'):]
    fim = corpo.find("</main>")
    return corpo if fim < 0 else corpo[:fim]


def _o_que_o_servidor_recebe(html: str) -> tuple[set, set]:
    corpo = _conteudo(html)
    acoes = set(re.findall(r'name="acao"\s+value="([a-z_]+)"', corpo))
    enderecos = set(re.findall(r'<form[^>]*\baction="([^"]+)"', corpo))
    return acoes, {e for e in enderecos if "/preferencias/" not in e}


def test_o_layout_antigo_nao_tem_regua(app):
    c = _entrar(app, "fases_b")
    _layout(c, "antigo")
    html = c.get(_abrir_ato(c, "PROCURACAO", "NT-PROC-PUBLICA")).get_data(as_text=True)
    assert "data-cg-regua" not in html
    assert "cg-ficha" not in html
    assert "fases.js" not in html
    assert "no fim desta página" in html


def test_o_layout_novo_abre_em_preparar_com_a_regua(app):
    c = _entrar(app, "fases_c")
    _layout(c, "novo")
    html = c.get(_abrir_ato(c, "PROCURACAO", "NT-PROC-PUBLICA")).get_data(as_text=True)
    assert 'data-inicial="preparar"' in html
    assert 'data-cg-fase="teor"' in html
    assert 'data-cg-fase="doi"' not in html
    assert "fases.js" in html


@pytest.mark.parametrize("tipo,modelo", [("PROCURACAO", "NT-PROC-PUBLICA"),
                                         ("SUBSTABELECIMENTO", "NT-SUBSTABELECIMENTO"),
                                         ("REVOGACAO", "NT-REVOGACAO-MANDATO")])
def test_as_duas_molduras_oferecem_o_mesmo(app, tipo, modelo):
    c = _entrar(app, "fases_d")
    _layout(c, "antigo")
    endereco = _abrir_ato(c, tipo, modelo)
    antigo = c.get(endereco).get_data(as_text=True)
    _layout(c, "novo")
    novo = c.get(endereco).get_data(as_text=True)
    acoes_a, form_a = _o_que_o_servidor_recebe(antigo)
    acoes_n, form_n = _o_que_o_servidor_recebe(novo)
    assert form_a == form_n
    # sem parte não há linha de parte, e por isso o papel na DOI não entra na conta aqui
    assert acoes_a == acoes_n, acoes_a ^ acoes_n


def test_a_escritura_tem_a_doi_travada_ate_haver_teor(app):
    c = _entrar(app, "fases_e")
    _layout(c, "novo")
    html = c.get(_abrir_ato(c, "ESCRITURA", "")).get_data(as_text=True)
    assert re.search(r'data-cg-fase="doi"\s+data-travada', html)
    assert "A DOI abre quando a minuta estiver pronta" in html
    assert 'id="doi"' in html
