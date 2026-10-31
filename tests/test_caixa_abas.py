"""As abas da ficha do protocolo geral: a conta da régua, e o que a ficha não pode perder.

O QUE ELES DEFENDEM
    Que nenhum quadro fica fora de alcance, e que a porta de cada formulário continua à mão. Quadro
    sem aba some da tela sem erro nenhum. A parte de baixo usa o sistema de pé, e roda na outra
    máquina.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import caixa_abas as CA  # noqa: E402

FICHA = (RAIZ / "templates" / "caixa_protocolo.html").read_text(encoding="utf-8-sig")
CONFERENCIA = (RAIZ / "templates" / "_ri_conferencia.html").read_text(encoding="utf-8-sig")


def _p(**campos) -> dict:
    return {"id": 1, "numero": "21394", "situacao": "ABERTO", "tipo": "SERVICO", "atribuicao": "NOTAS", **campos}


def _chaves(r: dict) -> list[str]:
    return [x["chave"] for x in r["apoio"]]


def _aba(r: dict, chave: str) -> dict:
    return next(x for x in r["apoio"] if x["chave"] == chave)


def test_abre_nos_itens_e_nao_ha_fase():
    r = CA.abas_do_protocolo(_p())
    assert r["inicial"] == CA.ITENS
    assert r["fases"] == []


def test_as_abas_que_guardam_formulario_ficam_mesmo_vazias():
    """Documentos, Exigências e Tarefas é onde se cria o primeiro."""
    assert _chaves(CA.abas_do_protocolo(_p())) == [CA.ITENS, CA.DADOS, CA.DOCUMENTOS, CA.EXIGENCIAS, CA.TAREFAS]


def test_vinculos_so_no_que_e_do_ri():
    assert CA.VINCULOS not in _chaves(CA.abas_do_protocolo(_p()))
    assert CA.VINCULOS in _chaves(CA.abas_do_protocolo(_p(atribuicao="RI")))
    assert CA.VINCULOS in _chaves(CA.abas_do_protocolo(_p(atribuicao="ri")))
    assert CA.VINCULOS in _chaves(CA.abas_do_protocolo(_p(ri_protocolo_id=7)))


def test_acompanhamento_so_quando_elegivel():
    assert CA.ACOMPANHAMENTO not in _chaves(CA.abas_do_protocolo(_p(), acompanhamento={"elegivel": False}))
    assert CA.ACOMPANHAMENTO in _chaves(CA.abas_do_protocolo(_p(), acompanhamento={"elegivel": True}))


def test_movimento_so_com_lancamento():
    assert CA.MOVIMENTO not in _chaves(CA.abas_do_protocolo(_p()))
    r = CA.abas_do_protocolo(_p(), lancamentos=[1, 2])
    assert _aba(r, CA.MOVIMENTO)["contagem"] == 2


def test_as_contagens():
    r = CA.abas_do_protocolo(_p(), atos=[1, 2, 3], documentos=[1], tarefas=[1, 2])
    assert _aba(r, CA.ITENS)["contagem"] == 3
    assert _aba(r, CA.DOCUMENTOS)["contagem"] == 1
    assert _aba(r, CA.TAREFAS)["contagem"] == 2


def test_o_que_falta_quitar_marca_a_aba():
    assert _aba(CA.abas_do_protocolo(_p(), atos=[1, 2], faltam=2), CA.ITENS)["alerta"] == 2


def test_o_encerrado_e_o_orcamento_nao_cobram_quitacao():
    assert _aba(CA.abas_do_protocolo(_p(), atos=[1], faltam=1, encerrado=True), CA.ITENS)["alerta"] == 0
    assert _aba(CA.abas_do_protocolo(_p(tipo="ORCAMENTO"), atos=[1], faltam=1), CA.ITENS)["alerta"] == 0


def test_a_exigencia_espera_e_marca_a_aba():
    r = CA.abas_do_protocolo(_p(), exigencias=[{"onde": "x"}])
    assert [i["ir"] for i in r["espera"]] == [CA.EXIGENCIAS]
    assert _aba(r, CA.EXIGENCIAS)["alerta"] == 1


def test_encerrado_nao_espera_nada():
    r = CA.abas_do_protocolo(_p(), exigencias=[{"onde": "x"}], encerrado=True)
    assert r["espera"] == []
    assert _aba(r, CA.EXIGENCIAS)["alerta"] == 0


def test_itens_a_quitar_e_ri_sem_vinculo_nao_viram_alarme():
    """O primeiro já está na aba que abre, e o segundo é a regra do pedido de certidão do RI."""
    assert CA.abas_do_protocolo(_p(atribuicao="RI"), atos=[1], faltam=1)["espera"] == []


# ------------------------------------------------------------- o molde

def _sem_marcas(html: str) -> str:
    return re.sub(r"\{%.*?%\}", "", re.sub(r"\{#.*?#\}", "", html, flags=re.S), flags=re.S)


def test_todo_quadro_diz_em_que_aba_mora():
    corpo = _sem_marcas(FICHA[FICHA.index("{% block content %}"):])
    abertos = re.findall(r"<section\b[^>]*\bclass=\"(?:panel|cards)[^>]*>", corpo)
    assert len(abertos) >= 11, "o varredor deixou de achar os quadros"
    assert [t for t in abertos if "data-fase" not in t] == []
    assert 'data-fase="documentos"' in re.search(r"<section[^>]*conferencia-digital[^>]*>", CONFERENCIA).group(0)


def test_toda_aba_tem_endereco_e_quadro():
    for chave in (CA.ITENS, CA.DADOS, CA.DOCUMENTOS, CA.EXIGENCIAS, CA.TAREFAS, CA.VINCULOS,
                  CA.ACOMPANHAMENTO, CA.MOVIMENTO):
        assert f'id="{chave}"' in FICHA, chave
        assert f'data-fase="{chave}"' in FICHA, chave


def test_os_enderecos_antigos_continuam():
    """A volta de quem anexa, de quem cria tarefa e o link de quem não tem item."""
    for ancora in ('id="documentos-qualificacao"', 'id="tarefas"', 'id="exigencias"', 'id="acrescentar-item"'):
        assert ancora in FICHA, ancora


def test_quem_continua_no_layout_antigo_nao_recebe_nada():
    assert "{% set abas = abas_da_ficha() if layout_novo else none %}" in FICHA
    assert "{% if abas %}</div>{% endif %}" in FICHA
    assert "{%- if layout_novo %} <span class=\"small muted\">" in FICHA


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


def _protocolo(app) -> int:
    from bd_nativo import banco
    d = app.extensions["db"]
    with d.transaction() as con:
        return int(banco(con).escrever(
            """INSERT INTO cx_protocolos (numero, data_abertura, situacao, atribuicao, interessado, criado_em)
               VALUES ('990001', '2026-10-30', 'ABERTO', 'RI', 'Ana Exemplo', %s) RETURNING id""",
            (d.now(),))[0]["id"])


def test_as_duas_molduras_oferecem_o_mesmo(cg_app):
    c = _entrar(cg_app, "protocolo_a")
    endereco = f"/caixa/protocolos/{_protocolo(cg_app)}"
    corpo = lambda html: html[html.index('class="content"'):]        # noqa: E731
    acoes = lambda html: sorted(re.findall(r'name="acao" value="([a-z_]+)"', corpo(html)))  # noqa: E731
    _layout(c, "antigo")
    antigo = c.get(endereco).get_data(as_text=True)
    assert "data-cg-regua" not in antigo
    _layout(c, "novo")
    novo = c.get(endereco).get_data(as_text=True)
    assert "data-cg-regua" in novo
    assert acoes(antigo) == acoes(novo)
    assert len(acoes(novo)) >= 3, "o varredor deixou de achar as ações"
