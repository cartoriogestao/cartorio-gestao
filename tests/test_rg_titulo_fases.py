"""As fases da ficha do título do RCPJ e do RTD.

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

import rg_titulo_fases as RF  # noqa: E402

TELA = (RAIZ / "templates" / "rcpj_rtd_titulo.html").read_text(encoding="utf-8-sig")


def _f(situacao, pode_decidir=True, **kw):
    return RF.fases_do_titulo({"situacao": situacao}, pode_decidir=pode_decidir, **kw)


def _estado(r):
    return [x["estado"] for x in r["fases"]]


def _pendencias(r):
    return [x["pendencias"] for x in r["fases"]]


def _apoio(r):
    return {x["chave"]: x for x in r["apoio"]}


def test_apresentado_abre_na_qualificacao_e_o_registro_trava():
    r = _f(RF.APRESENTADO)
    assert r["inicial"] == RF.QUALIFICACAO
    assert _estado(r) == [RF.FEITA, RF.LIBERADA, RF.TRAVADA]
    assert _pendencias(r) == [0, 1, 0]
    assert r["fases"][2]["trava"]["ir"] == RF.QUALIFICACAO


def test_com_exigencia_volta_a_qualificacao_sem_cobrar_de_quem_nao_pode_agir():
    """Requalificar é linha nova, e quem age agora é o apresentante."""
    r = _f(RF.EXIGENCIA)
    assert r["inicial"] == RF.QUALIFICACAO
    assert _estado(r) == [RF.FEITA, RF.LIBERADA, RF.TRAVADA]
    assert _pendencias(r) == [0, 0, 0]
    assert "de novo" in r["fases"][1]["aviso"]


def test_qualificado_abre_no_registro():
    r = _f(RF.QUALIFICADO)
    assert r["inicial"] == RF.REGISTRO
    assert _estado(r) == [RF.FEITA, RF.FEITA, RF.LIBERADA]
    assert _pendencias(r) == [0, 0, 1]


def test_registrado_abre_no_registro_e_nao_cobra_nada():
    r = _f(RF.REGISTRADO, tem_registro=True)
    assert r["inicial"] == RF.REGISTRO
    assert _estado(r) == [RF.FEITA, RF.FEITA, RF.FEITA]
    assert _pendencias(r) == [0, 0, 0]


@pytest.mark.parametrize("situacao", [RF.DEVOLVIDO, RF.CANCELADO])
def test_titulo_que_saiu_sem_registro_abre_onde_esta_o_motivo(situacao):
    r = _f(situacao)
    assert r["inicial"] == RF.APRESENTACAO
    assert r["fases"][2]["estado"] == RF.TRAVADA
    assert r["fases"][2]["trava"]["ir"] == RF.APRESENTACAO
    assert _pendencias(r) == [0, 0, 0]


def test_quem_saiu_sem_qualificar_nao_diz_que_qualificou():
    assert _estado(_f(RF.CANCELADO))[1] == RF.LIBERADA
    assert _estado(_f(RF.DEVOLVIDO, qualificacoes=[{}]))[1] == RF.FEITA


def test_o_balcao_nao_recebe_cobranca_do_que_e_do_oficial():
    r = _f(RF.APRESENTADO, pode_decidir=False)
    assert _pendencias(r) == [0, 0, 0]
    assert "oficial" in r["fases"][1]["aviso"]


def test_para_o_balcao_o_titulo_qualificado_nao_abre_numa_trava():
    r = _f(RF.QUALIFICADO, pode_decidir=False)
    assert r["inicial"] == RF.QUALIFICACAO
    assert r["fases"][2]["estado"] == RF.TRAVADA
    assert "oficial" in r["fases"][2]["trava"]["titulo"]
    assert _pendencias(r) == [0, 0, 0]


def test_a_ponte_entre_as_fases():
    a, b, c = _f(RF.APRESENTADO)["fases"]
    assert a["voltar"] is None and a["avancar"]["chave"] == RF.QUALIFICACAO
    assert b["voltar"]["chave"] == RF.APRESENTACAO and b["avancar"]["chave"] == RF.REGISTRO
    assert c["voltar"]["chave"] == RF.QUALIFICACAO and c["avancar"] is None


def test_as_abas_de_apoio():
    assert set(_apoio(_f(RF.APRESENTADO))) == {RF.CENTRAL, RF.ENCERRAR}
    assert _apoio(_f(RF.APRESENTADO, encaminhamentos=[{}, {}]))[RF.CENTRAL]["contagem"] == 2
    for situacao in RF.SITUACOES_TERMINAIS:
        assert set(_apoio(_f(situacao))) == {RF.CENTRAL}, "título que saiu não se encerra"
    assert set(_apoio(_f(RF.APRESENTADO, pode_decidir=False))) == {RF.CENTRAL}, "encerrar é do oficial"


def test_a_central_fora_do_ar_marca_a_aba():
    assert _apoio(_f(RF.APRESENTADO))[RF.CENTRAL]["alerta"] == 0
    assert _apoio(_f(RF.APRESENTADO, central_falhou=True))[RF.CENTRAL]["alerta"] == 1


# ------------------------------------------------------------ o domínio é o mesmo


def test_as_situacoes_sao_as_do_modulo():
    import rg_titulo as TIT
    assert tuple(RF.SITUACOES_TERMINAIS) == tuple(TIT.SITUACOES_TERMINAIS)
    for nome in ("APRESENTADO", "QUALIFICADO", "EXIGENCIA", "REGISTRADO", "DEVOLVIDO", "CANCELADO"):
        assert getattr(RF, nome) == getattr(TIT, nome) and getattr(RF, nome) in TIT.SITUACOES


def test_a_trava_repete_a_recusa_do_servidor():
    fonte = (RAIZ / "rg_titulo.py").read_text(encoding="utf-8")
    assert "Só se registra título com qualificação positiva" in fonte
    assert "Só se registra título com qualificação positiva" in RF._TRAVA_SEM_QUALIFICACAO["texto"]
    assert 'if titulo["situacao"] != QUALIFICADO:' in fonte, "a regra do registro mudou"


def test_quem_decide_na_regua_e_quem_a_rota_aceita():
    fonte = (RAIZ / "rg_web.py").read_text(encoding="utf-8")
    assert 'QUEM_QUALIFICA = ("ADMIN", "MANAGER")' in fonte
    for rota in ("qualificar", "registrar", "concluir", "encerrar"):
        assert re.search(rf"@roles_required\(\*QUEM_QUALIFICA\)\s+def rcpj_rtd_titulo_{rota}\(", fonte), rota
    assert "abas_da_ficha(user.role in ['ADMIN','MANAGER'])" in TELA


# ------------------------------------------------------------ o molde


def test_todo_quadro_diz_a_fase():
    """Quadro novo sem `data-fase` apareceria em todas as abas, sem ninguém pedir."""
    sem_fase = [m for m in re.findall(r"<section\b[^>]*>", TELA) if "data-fase" not in m]
    assert sem_fase == ['<section style="grid-column:1/-1;margin-top:8px">']  # o selo, dentro do formulário


def test_cada_chave_do_molde_existe_na_regua():
    r = _f(RF.APRESENTADO)
    chaves = {x["chave"] for x in r["fases"]} | {x["chave"] for x in r["apoio"]}
    no_molde = set(re.findall(r'data-fase="([a-z]+)"', TELA))
    assert no_molde == chaves, no_molde ^ chaves


def test_o_documento_fica_ao_lado_da_decisao():
    """É a promessa do comentário no alto do molde, e o motivo de a Qualificação ter o foco."""
    for titulo in ("O título", "A qualificação"):
        m = re.search(r'<section class="([^"]*)" data-fase="([a-z]+)">\s*<div class="panel-head">\s*<span>' + titulo, TELA)
        assert m, titulo
        assert m.group(1) == "panel{% if abas %} cg-lado{% endif %}" and m.group(2) == RF.QUALIFICACAO
    assert _f(RF.APRESENTADO)["foco"] == RF.QUALIFICACAO


def test_o_layout_antigo_nao_chama_as_fases():
    assert "{% set abas = abas_da_ficha(user.role in ['ADMIN','MANAGER']) if layout_novo else none %}" in TELA
    assert "{% if abas %}{{ travas_e_barras(abas) }}</div>{% endif %}" in TELA


def test_o_estilo_novo_so_vale_no_layout_novo():
    assert TELA.count("<style>") == 1
    assert re.search(r"\{% if abas %\}\{\{ abre_ficha\(VERSION\) \}\}[^\n]*\n[^\n]*\n<style>[^\n]*</style>\{% endif %\}", TELA)


def test_a_frase_nao_aponta_para_o_botao_que_mudou_de_fase():
    assert "Quem toma o número do livro é {% if abas %}a fase Registro.{% else %}o botão" in TELA


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
            """INSERT INTO rg_titulos (atribuicao, numero, data_apresentacao, apresentante, natureza, situacao, origem, criado_em)
               VALUES (4, 1, '2026-10-30', 'Ana Exemplo', 'Contrato de locação', %s, 'MANUAL', %s) RETURNING id""",
            (situacao, d.now()))["id"]


def _layout(c, qual: str) -> None:
    c.post("/preferencias/layout", data={
        "layout": qual, "next": "/", "csrf_token": _token(c.get("/").get_data(as_text=True))})


def test_a_regua_aparece_so_no_layout_novo(cg_app):
    tid = _titulo(cg_app, RF.APRESENTADO)
    c = _entrar(cg_app, "fases_rtd_a")
    _layout(c, "antigo")
    antigo = c.get(f"/rcpj-rtd/titulo/{tid}").get_data(as_text=True)
    assert "data-cg-regua" not in antigo and "Encerrar sem registro" in antigo
    _layout(c, "novo")
    novo = c.get(f"/rcpj-rtd/titulo/{tid}").get_data(as_text=True)
    assert "data-cg-regua" in novo and 'data-inicial="qualificacao"' in novo
    assert "Antes, a qualificação positiva" in novo


def test_para_o_balcao_a_regua_nao_oferece_encerrar(cg_app):
    tid = _titulo(cg_app, RF.QUALIFICADO)
    c = _entrar(cg_app, "fases_rtd_b", "USER")
    _layout(c, "novo")
    novo = c.get(f"/rcpj-rtd/titulo/{tid}").get_data(as_text=True)
    assert 'data-inicial="qualificacao"' in novo
    assert "O registro é ato do oficial" in novo
    assert 'data-cg-fase="encerrar"' not in novo
    assert "Lavrar o registro" not in novo
