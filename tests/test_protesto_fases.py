"""As fases da ficha do título de Protesto.

O QUE ELES DEFENDEM
    Projeto do novo layout, 30/10/2026. O risco é a fase esconder o que espera ação, abrir a ficha no
    lugar errado, ou um quadro novo não dizer a que fase pertence. A trava repete a recusa do servidor,
    e a parte de baixo usa o sistema de pé, e roda na outra máquina.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import protesto_fases as PF  # noqa: E402

TELA = (RAIZ / "templates" / "atrib_protesto_ficha.html").read_text(encoding="utf-8-sig")


def _f(situacao, cabem=(), **kw):
    return PF.fases_do_titulo({"situacao": situacao}, cabem=cabem, **kw)


def _estado(r):
    return [x["estado"] for x in r["fases"]]


def test_recebido_abre_no_apontamento_e_a_intimacao_trava():
    r = _f("RECEBIDO", ["APONTAMENTO", "DESISTENCIA", "PAGAMENTO", "SUSTACAO"])
    assert r["inicial"] == PF.APONTAMENTO
    assert _estado(r) == [PF.LIBERADA, PF.TRAVADA, PF.LIBERADA]
    assert r["fases"][0]["pendencias"] == 1
    assert r["fases"][1]["trava"]["ir"] == PF.APONTAMENTO


def test_apontado_abre_na_intimacao():
    r = _f("APONTADO", ["INTIMACAO", "DESISTENCIA", "PAGAMENTO", "SUSTACAO"])
    assert r["inicial"] == PF.INTIMACAO
    assert _estado(r) == [PF.FEITA, PF.LIBERADA, PF.LIBERADA]
    assert r["fases"][1]["pendencias"] == 1


@pytest.mark.parametrize("triduo,inicial,pendencias", [
    ("ANTES", PF.INTIMACAO, 0), ("NO_DIA", PF.DESFECHO, 1), ("ATRASADO", PF.DESFECHO, 1), ("", PF.DESFECHO, 1),
])
def test_intimado_abre_conforme_o_triduo(triduo, inicial, pendencias):
    r = _f("INTIMADO", ["INTIMACAO", "PROTESTO", "DESISTENCIA", "PAGAMENTO"], triduo=triduo)
    assert r["inicial"] == inicial
    assert r["fases"][2]["pendencias"] == pendencias


def test_o_aviso_do_desfecho_diz_o_triduo():
    assert "venceu" in _f("INTIMADO", ["PROTESTO"], triduo="ATRASADO")["fases"][2]["aviso"]
    assert "Ainda não" in _f("INTIMADO", ["PROTESTO"], triduo="ANTES")["fases"][2]["aviso"]


def test_protestado_abre_no_desfecho_e_sem_alarme():
    r = _f("PROTESTADO", ["CANCELAMENTO", "EFEITO_SUSPENSIVO"])
    assert r["inicial"] == PF.DESFECHO
    assert _estado(r) == [PF.FEITA, PF.FEITA, PF.LIBERADA]
    assert all(x["pendencias"] == 0 for x in r["fases"])


@pytest.mark.parametrize("situacao", PF.SITUACOES_FINAIS)
def test_titulo_encerrado_abre_na_vida_e_nao_cobra_nada(situacao):
    r = _f(situacao)
    assert r["inicial"] == PF.VIDA
    assert all(x["pendencias"] == 0 for x in r["fases"])
    assert r["fases"][2]["estado"] == PF.FEITA


def test_desistido_antes_de_intimar_nao_diz_que_intimou():
    assert _estado(_f("DESISTIDO"))[1] == PF.LIBERADA
    com_ato = _f("DESISTIDO", atos=[{"tipo": "INTIMACAO", "cancelado": 0}])
    assert _estado(com_ato)[1] == PF.FEITA
    desfeita = _f("DESISTIDO", atos=[{"tipo": "INTIMACAO", "cancelado": 1}])
    assert _estado(desfeita)[1] == PF.LIBERADA


def test_a_situacao_final_do_modulo_e_a_mesma():
    import protesto as PT
    assert tuple(PF.SITUACOES_FINAIS) == tuple(PT.SITUACOES_FINAIS)


def test_cada_ato_tem_a_sua_fase():
    import protesto as PT
    assert PF.fase_do_ato("APONTAMENTO") == PF.APONTAMENTO
    assert PF.fase_do_ato("INTIMACAO") == PF.INTIMACAO
    for ato in set(PT.TIPOS_ATO) - {"APONTAMENTO", "INTIMACAO"}:
        assert PF.fase_do_ato(ato) == PF.DESFECHO


def test_o_nome_do_ato_tem_acento():
    assert PF.rotulo_do_ato("INTIMACAO") == "Intimação"
    assert PF.rotulo_do_ato("REVOGACAO_SUSTACAO") == "Revogação da sustação"
    assert PF.rotulo_do_ato("PROTESTO") == "Protesto"


def test_o_formulario_em_vista():
    assert PF.atos_em_vista(["APONTAMENTO", "DESISTENCIA", "PAGAMENTO"]) == ["APONTAMENTO"]
    assert "PROTESTO" in PF.atos_em_vista(["INTIMACAO", "PROTESTO", "DESISTENCIA", "PAGAMENTO"])
    assert "PAGAMENTO" not in PF.atos_em_vista(["INTIMACAO", "PROTESTO", "DESISTENCIA", "PAGAMENTO"])
    assert PF.atos_em_vista(["CANCELAMENTO"]) == ["CANCELAMENTO"]


def test_as_abas_de_apoio():
    r = _f("PROTESTADO", atos=[{}, {}], imagens=[{}], emolumento={"pendentes": {"itens": [{}]}}, pode_averbar=True)
    assert {x["chave"]: x["contagem"] for x in r["apoio"]} == {
        PF.VIDA: 2, PF.EMOLUMENTOS: 1, PF.IMAGEM: 1, PF.AVERBACAO: 0}
    assert {x["chave"] for x in _f("PROTESTADO")["apoio"]} == {PF.VIDA, PF.IMAGEM}


# ------------------------------------------------------------ o molde


def test_todo_quadro_diz_a_fase():
    """Quadro novo sem `data-fase` apareceria em todas as abas, sem ninguém pedir."""
    sem_fase = [m for m in re.findall(r"<section\b[^>]*>", TELA) if "data-fase" not in m and "if not abas" not in m]
    assert sem_fase == ['<section class="panel">']  # o «Lançar o próximo ato» do layout antigo


def test_cada_chave_do_molde_existe_na_regua():
    r = _f("PROTESTADO", emolumento={"pendentes": {}}, pode_averbar=True)
    chaves = {x["chave"] for x in r["fases"]} | {x["chave"] for x in r["apoio"]}
    no_molde = set(re.findall(r'data-fase="([a-z]+)"', TELA))
    assert no_molde <= chaves, no_molde - chaves


def test_os_avisos_do_alto_saem_em_todas_as_fases():
    """O que está errado no título não pode ficar escondido numa aba."""
    for marca in ("data-situacao-sem-ato", "data-propostas-de-oficio", "data-pendencias-do-selo",
                  "data-pedidos-cra", "data-credor-a-averbar"):
        linha = next(x for x in TELA.splitlines() if marca in x)
        assert "data-fase" not in linha, marca


def test_a_ordem_sem_marca_sai_em_todas_e_a_marcada_vai_para_o_desfecho():
    assert '{% if suspensao.ordem_carater %} data-fase="desfecho"{% endif %}' in TELA


def test_o_layout_antigo_nao_chama_as_fases():
    assert "{% set abas = abas_da_ficha(user.role == 'ADMIN') if layout_novo else none %}" in TELA
    assert "{% if abas %}{{ travas_e_barras(abas) }}</div>{% endif %}" in TELA


def test_o_alvo_recolhido_abre():
    assert 'alvo.closest("details")' in (RAIZ / "static" / "fases.js").read_text(encoding="utf-8")


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


def _titulo(app, situacao: str) -> int:
    from bd_nativo import banco
    d = app.extensions["db"]
    with d.transaction() as con:
        return banco(con).um(
            """INSERT INTO pt_titulos (numero_titulo, especie, valor_centavos, saldo_centavos, situacao, origem, criado_em)
               VALUES (%s, 'DM', 10000, 10000, %s, 'MANUAL', %s) RETURNING id""",
            (f"F-{situacao}", situacao, d.now()))["id"]


def _layout(c, qual: str) -> None:
    c.post("/preferencias/layout", data={
        "layout": qual, "next": "/", "csrf_token": _token(c.get("/").get_data(as_text=True))})


def test_a_regua_aparece_so_no_layout_novo(cg_app):
    tid = _titulo(cg_app, "APONTADO")
    c = _entrar(cg_app, "fases_pt_a")
    _layout(c, "antigo")
    antigo = c.get(f"/protesto/{tid}").get_data(as_text=True)
    assert "data-cg-regua" not in antigo and "Lançar o próximo ato" in antigo
    _layout(c, "novo")
    novo = c.get(f"/protesto/{tid}").get_data(as_text=True)
    assert "data-cg-regua" in novo and 'data-inicial="intimacao"' in novo
    assert 'class="panel cg-ato-do-titulo" data-fase="intimacao" open' in novo


def test_o_formulario_de_cada_ato_continua_um_so(cg_app):
    tid = _titulo(cg_app, "RECEBIDO")
    c = _entrar(cg_app, "fases_pt_b")
    _layout(c, "novo")
    novo = c.get(f"/protesto/{tid}").get_data(as_text=True)
    assert novo.count('id="lancar-APONTAMENTO"') == 1
    assert 'data-fase="apontamento" open' in novo
