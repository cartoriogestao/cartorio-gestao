"""
AS AFIRMAÇÕES EXPRESSAS — a tela do oficial e o contador do roteiro.

Ordem do oficial, 29/10/2026: *«se insistir em algo que eh erro, precisa
afirmar expressamente e deixar log»*. As travas gravam pelo contrato comum —
`audit("AFIRMACAO_EXPRESSA", entidade, id, {"regra", "afirmacao",
"o_que_faltava"})` —, e o que estes testes guardam é a LEITURA:

      - o filtro por período e por regra devolve só o que pediu;
      - linha fora do contrato não some (vira afirmação, sem regra declarada);
      - o contador conta sete dias, e sem a tabela é `None`, e não zero;
      - a tela é do ADMIN: o balcão não entra, e o menu dele não mostra.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import afirmacoes_expressas as AFX  # noqa: E402

SENHA = "Senha#12345"
HOJE = "2026-10-29"


def _afirmar(con, ts, regra, afirmacao, *, faltava="o comprovante",
             entidade="pt_titulos", entidade_id=7, detalhes=None) -> None:
    det = detalhes if detalhes is not None else {
        "regra": regra, "afirmacao": afirmacao, "o_que_faltava": faltava}
    con.execute(
        """INSERT INTO audit_logs(ts, username_snapshot, action, entity_type,
               entity_id, details) VALUES (?, 'MARIA', ?, ?, ?, ?)""",
        (ts, AFX.ACAO, entidade, entidade_id,
         det if isinstance(det, str) else json.dumps(det)))
    con.commit()


@pytest.fixture()
def casa(cg_casa):
    con = sqlite3.connect(cg_casa["banco"])
    con.row_factory = sqlite3.Row
    yield con
    con.close()


def test_o_contrato_e_o_que_os_outros_modulos_gravam():
    assert AFX.ACAO == "AFIRMACAO_EXPRESSA"
    assert AFX.DIAS_DO_CONTADOR == 7


def test_filtra_por_periodo_e_por_regra(casa):
    _afirmar(casa, "2026-10-10T09:00:00", "PROTESTO_SEM_PROVA", "fora do período")
    _afirmar(casa, "2026-10-28T09:00:00", "PROTESTO_SEM_PROVA",
             "o devedor assinou no balcão")
    _afirmar(casa, "2026-10-29T17:59:59", "SELO_FALTANDO", "selo vem amanhã")
    casa.execute("INSERT INTO audit_logs(ts, action) VALUES (?, 'OUTRA')",
                 ("2026-10-29T10:00:00",))
    casa.commit()

    tudo = AFX.listar(casa, hoje=HOJE, de="2026-10-20", ate=HOJE)
    assert tudo["total"] == 2, "a do dia 29 às 17:59 entra: o dia é inteiro"
    assert tudo["regras"] == ["PROTESTO_SEM_PROVA", "SELO_FALTANDO"]
    assert tudo["linhas"][0]["regra"] == "SELO_FALTANDO", "a mais nova primeiro"

    uma = AFX.listar(casa, hoje=HOJE, de="2026-10-20", ate=HOJE,
                     regra="PROTESTO_SEM_PROVA")
    assert [x["afirmacao"] for x in uma["linhas"]] == [
        "o devedor assinou no balcão"]
    assert uma["linhas"][0]["o_que_faltava"] == "o comprovante"
    assert uma["linhas"][0]["quem"] == "MARIA"
    assert uma["regras"] == ["PROTESTO_SEM_PROVA", "SELO_FALTANDO"], (
        "a caixa de regras mostra as do período, e não só a escolhida")


def test_o_periodo_padrao_e_de_trinta_dias_e_datas_ruins_nao_quebram(casa):
    r = AFX.listar(casa, hoje=HOJE, de="não é data", ate="")
    assert (r["de"], r["ate"]) == ("2026-09-29", HOJE)
    invertido = AFX.listar(casa, hoje=HOJE, de=HOJE, ate="2026-10-01")
    assert (invertido["de"], invertido["ate"]) == ("2026-10-01", HOJE)


def test_linha_fora_do_contrato_nao_some(casa):
    _afirmar(casa, "2026-10-29T09:00:00", "", "", detalhes="texto solto")
    linha = AFX.listar(casa, hoje=HOJE)["linhas"][0]
    assert linha["regra"] == AFX.SEM_REGRA
    assert linha["afirmacao"] == "texto solto"


def test_o_contador_conta_sete_dias(casa):
    _afirmar(casa, "2026-10-21T09:00:00", "R", "fora")
    _afirmar(casa, "2026-10-23T09:00:00", "R", "dentro")
    _afirmar(casa, "2026-10-29T09:00:00", "R", "dentro")
    assert AFX.contar(casa, hoje=HOJE) == 2


def test_sem_a_tabela_e_none_e_nao_zero():
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    assert AFX.contar(con, hoje=HOJE) is None
    assert AFX.listar(con, hoje=HOJE)["total"] is None


# ------------------------------------------------------------------ a tela


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado
    return achado.group(1)


def _entrar(cg_casa, usuario: str, papel: str):
    cg_casa["db"].create_user(usuario, usuario.upper(), SENHA, papel)
    cg_casa["db"].set_settings({"modulo_protesto_ligado": "1"})
    c = cg_casa["app"].test_client()
    c.post("/login", data={"username": usuario, "password": SENHA,
                           "csrf_token": _token(
                               c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


def test_o_oficial_ve_a_afirmacao_e_filtra(cg_casa, casa):
    _afirmar(casa, cg_casa["db"].now()[:10] + "T09:00:00", "PROTESTO_SEM_PROVA",
             "o devedor assinou no balcão")
    c = _entrar(cg_casa, "oficial", "ADMIN")
    r = c.get("/protesto/afirmacoes")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "o devedor assinou no balcão" in html
    assert "PROTESTO_SEM_PROVA" in html
    assert "1 afirmação(ões)" in html
    vazio = c.get("/protesto/afirmacoes?regra=OUTRA").get_data(as_text=True)
    assert "o devedor assinou no balcão" not in vazio
    # O MENU DO PROTESTO LEVA A ELA, e o roteiro conta a semana.
    menu = c.get("/protesto/roteiro").get_data(as_text=True)
    assert 'href="/protesto/afirmacoes"' in menu
    assert "1 afirmações nos últimos 7 dias" in menu


def test_o_balcao_nao_entra(cg_casa):
    c = _entrar(cg_casa, "escrevente", "USER")
    assert c.get("/protesto/afirmacoes").status_code == 403
    assert 'href="/protesto/afirmacoes"' not in c.get(
        "/protesto/roteiro").get_data(as_text=True)


def test_o_filtro_e_get_e_a_tela_nao_grava(cg_casa):
    """A tela só LÊ: o que se afirmou fica, e não há botão que apague."""
    c = _entrar(cg_casa, "oficial", "ADMIN")
    html = c.get("/protesto/afirmacoes").get_data(as_text=True)
    assert 'method="get" action="/protesto/afirmacoes"' in html
    assert not re.search(
        r'<form[^>]*method="post"[^>]*action="/protesto/afirmacoes', html, re.I)
