"""As abas dos autos de usucapião: a conta da régua, e o que a ficha não pode perder.

O QUE ELES DEFENDEM
    Que nenhum quadro fica fora de alcance, e que a régua conta como os quadros contam. Quadro sem
    aba some da tela sem erro nenhum. A parte de baixo usa o sistema de pé, e roda na outra máquina.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import usucapiao_abas as UA  # noqa: E402

FICHA = (RAIZ / "templates" / "usucapiao_ficha.html").read_text(encoding="utf-8-sig")
CHAVES = (UA.PROCESSO, UA.CONFERENCIA, UA.PECAS, UA.ANDAMENTO, UA.QUALIFICACAO, UA.DECISAO)


def _p(**campos) -> dict:
    return {"id": 1, "numero": "US-2026-001", "situacao": "EM_ANDAMENTO", **campos}


def _aba(r: dict, chave: str) -> dict:
    return next(x for x in r["apoio"] if x["chave"] == chave)


def test_seis_abas_e_abre_no_processo():
    r = UA.abas_do_processo(_p())
    assert [x["chave"] for x in r["apoio"]] == list(CHAVES)
    assert r["inicial"] == UA.PROCESSO
    assert r["fases"] == [], "o rito já tem o seu quadro, que recusa pular e aceita voltar"


def test_as_contagens():
    r = UA.abas_do_processo(_p(), pecas=[1, 2], movimentos=[{}], analises=[{"conferida_por_humano": 1}], decisoes=[1])
    assert _aba(r, UA.PECAS)["contagem"] == 2
    assert _aba(r, UA.ANDAMENTO)["contagem"] == 1
    assert _aba(r, UA.QUALIFICACAO)["contagem"] == 1
    assert _aba(r, UA.DECISAO)["contagem"] == 1


def test_o_que_falta_marca_a_aba():
    r = UA.abas_do_processo(_p(), conferencia={"pendentes": [1, 2]}, analises=[{"conferida_por_humano": 0}],
                            movimentos=[{"prazo_fim": "2026-10-01"}], hoje="2026-10-30")
    assert _aba(r, UA.CONFERENCIA)["alerta"] == 2
    assert _aba(r, UA.QUALIFICACAO)["alerta"] == 1
    assert _aba(r, UA.ANDAMENTO)["alerta"] == 1


def test_o_prazo_conta_como_o_quadro_conta():
    assert not UA.prazos_vencidos([{"prazo_fim": "2026-10-30"}], "2026-10-30"), "vence no fim do dia"
    assert not UA.prazos_vencidos([{"prazo_fim": "2026-10-01", "respondido_em": "2026-10-02"}], "2026-10-30")
    assert not UA.prazos_vencidos([{"prazo_fim": None}], "2026-10-30")
    assert UA.prazos_vencidos([{"prazo_fim": "2026-10-29"}], "2026-10-30")
    assert "not m.respondido_em and m.prazo_fim < hoje" in FICHA, "a condição do quadro mudou"


def test_o_que_terminou_nao_cobra():
    for situacao in UA.SITUACOES_FINAIS:
        r = UA.abas_do_processo(_p(situacao=situacao), conferencia={"pendentes": [1]}, analises=[{}],
                                movimentos=[{"prazo_fim": "2026-10-01"}], hoje="2026-10-30")
        assert all(x["alerta"] == 0 for x in r["apoio"]), situacao


def test_as_situacoes_finais_sao_as_do_modulo():
    fonte = (RAIZ / "usucapiao.py").read_text(encoding="utf-8")
    bloco = fonte[fonte.index("SITUACOES_FINAIS:"):]
    assert set(re.findall(r'"([A-Z_]+)"', bloco[:bloco.index(")")])) == set(UA.SITUACOES_FINAIS)


def test_todo_quadro_diz_em_que_aba_mora():
    corpo = re.sub(r"\{%.*?%\}", "", re.sub(r"\{#.*?#\}", "", FICHA, flags=re.S), flags=re.S)
    corpo = corpo[corpo.index("<div class=\"actions\">"):]
    abertos = re.findall(r"<section\b[^>]*\bclass=\"panel[^>]*>", corpo)
    assert len(abertos) == 8, "o varredor deixou de achar os quadros"
    assert [t for t in abertos if "data-fase" not in t] == []


def test_toda_aba_tem_endereco_e_quadro():
    for chave in CHAVES:
        assert f'id="{chave}"' in FICHA, chave
        assert f'data-fase="{chave}"' in FICHA, chave


def test_quem_continua_no_layout_antigo_nao_recebe_nada():
    assert "{% set abas = abas_da_ficha() if layout_novo else none %}" in FICHA
    assert "{% if abas %}</div>{% endif %}" in FICHA


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


def test_as_duas_molduras_oferecem_o_mesmo(cg_app):
    c = _entrar(cg_app, "usucapiao_a")
    html = c.get("/usucapiao").get_data(as_text=True)
    modalidade = re.search(r'name="modalidade"[^>]*>.*?<option value="([^"]+)"', html, flags=re.S).group(1)
    r = c.post("/usucapiao/novo", data={"numero": "US-ABAS-1", "modalidade": modalidade, "requerente_nome": "Ana Exemplo",
                                        "csrf_token": _token(html)})
    endereco = re.search(r"/usucapiao/\d+", r.headers["Location"]).group(0)
    corpo = lambda h: h[h.index('class="content"'):]        # noqa: E731
    formularios = lambda h: {e for e in re.findall(r'<form[^>]*\baction="([^"]+)"', corpo(h)) if "/usucapiao/" in e}  # noqa: E731
    _layout(c, "antigo")
    antigo = c.get(endereco).get_data(as_text=True)
    assert "data-cg-regua" not in antigo
    _layout(c, "novo")
    novo = c.get(endereco).get_data(as_text=True)
    assert "data-cg-regua" in novo
    assert formularios(antigo) == formularios(novo)
    assert len(formularios(novo)) >= 6, "o varredor deixou de achar os formulários"
