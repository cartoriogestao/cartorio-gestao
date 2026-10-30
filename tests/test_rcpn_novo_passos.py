"""O novo registro do Registro Civil em passos: nenhum campo se perde.

O QUE ELES DEFENDEM
    O casamento tem 166 campos, e o risco de dividir é um campo ficar sem passo, ou o passo
    não aparecer para aquela espécie: ele sumiria da tela sem erro nenhum. A parte de baixo
    usa o sistema de pé, compara as duas molduras e roda na máquina do balcão.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
FICHA = (RAIZ / "templates" / "atrib_rcpn_novo.html").read_text(encoding="utf-8-sig")


def _sem_comentarios(html: str) -> str:
    return re.sub(r"\{#.*?#\}", "", html, flags=re.S)


def _passos_da_especie() -> dict[str, list[str]]:
    achados = {}
    for especie, lista in re.findall(r"\{% (?:el)?if (nascimento|natimorto|obito|casamento) %\}\{% set cg_passos = \[(.*?)\] %\}", FICHA):
        achados[especie] = re.findall(r"\('([a-z0-9]+)'", lista)
    return achados


def test_toda_especie_do_civil_tem_passos():
    assert set(_passos_da_especie()) == {"nascimento", "natimorto", "obito", "casamento"}


def test_todo_passo_tem_o_seu_bloco():
    blocos = set(re.findall(r'data-passo="([a-z0-9]+)"', FICHA))
    for especie, passos in _passos_da_especie().items():
        assert set(passos) <= blocos, especie


def test_nenhum_bloco_fica_sem_porta_na_especie_que_o_usa():
    """Bloco sem passo fica escondido para sempre: o que ele tem de campo some da tela."""
    p = _passos_da_especie()
    assert "perguntas" in p["obito"], "as perguntas do óbito só existem no óbito"
    for especie in ("nascimento", "natimorto", "obito"):
        assert {"fato", "pessoa", "filiacao", "declarante", "termo"} <= set(p[especie]), especie
    # o casamento põe os pais junto de cada cônjuge, e não tem bloco de filiação
    assert {"fato", "pessoa", "conjuge2", "declarante", "termo"} <= set(p["casamento"])


def test_os_blocos_abrem_e_fecham_em_ordem():
    corpo = _sem_comentarios(FICHA)
    aberturas = corpo.count('{% if cg_passos %}<div class="cg-passo-bloco"')
    fechos = corpo.count("{% if cg_passos %}</div>")
    assert aberturas == fechos == 7
    ordem = re.findall(r'cg-passo-bloco" data-passo="([a-z0-9]+)"', corpo)
    assert ordem == ["fato", "pessoa", "conjuge2", "filiacao", "perguntas", "declarante", "termo"]


def test_o_botao_de_conferir_e_o_ultimo_passo():
    assert FICHA.index('data-passo="termo"') < FICHA.index('name="acao" value="conferir"')


def test_vale_o_primeiro_campo_invalido():
    """Com vários em branco, o cursor vai ao primeiro: o passo aberto tem de ser o dele."""
    script = (RAIZ / "static" / "fases.js").read_text(encoding="utf-8")
    assert "if (avisado) return;" in script


def test_quem_continua_no_layout_antigo_nao_recebe_nada():
    assert "{% if layout_novo %}" in FICHA and "{% set cg_passos = none %}" in FICHA
    corpo = _sem_comentarios(FICHA)
    assert corpo.count('<div class="cg-passo-bloco"') == corpo.count('{% if cg_passos %}<div class="cg-passo-bloco"')


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


def _campos(html: str) -> list[str]:
    corpo = html[html.index('id="form-do-ato"'):html.index("</form>", html.index('id="form-do-ato"'))]
    return sorted(re.findall(r'name="([^"]+)"', corpo))


@pytest.mark.parametrize("especie", ["nascimento", "casamento", "obito"])
def test_as_duas_molduras_mandam_os_mesmos_campos(cg_app, especie):
    c = _entrar(cg_app, "rcpn_a")
    endereco = f"/rcpn/novo/{especie}"
    _layout(c, "antigo")
    antigo = c.get(endereco).get_data(as_text=True)
    assert "data-cg-passos" not in antigo
    _layout(c, "novo")
    novo = c.get(endereco).get_data(as_text=True)
    assert "data-cg-passos" in novo
    assert _campos(antigo) == _campos(novo)
    assert len(_campos(novo)) > 20, "o varredor deixou de achar os campos"
