# -*- coding: utf-8 -*-
"""Máquina não assina ato, e ninguém assina por ela — 23/10/2026, «solução 1».

Até aqui `usuario_nome` trocava a sessão de robô pela substituta, e o ato
saía no nome de quem não o praticou. Agora sai `MARCA_PENDENTE`, e quem
selar assina: a marca vira o nome de quem obteve o selo.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import nome_humano as NOMEHUM  # noqa: E402
from tests.selador_de_bancada import ligar_o_selador, tem_cryptography  # noqa: E402
from tests.test_selo_travado_para_robos import _login, _token, casa  # noqa: E402,F401

HUMANO = "MARIO EXEMPLO DOS SANTOS"


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def test_a_marca_conta_como_maquina():
    assert NOMEHUM.eh_rotulo_de_maquina(NOMEHUM.MARCA_PENDENTE)
    assert NOMEHUM.nome_humano_para_ato(NOMEHUM.MARCA_PENDENTE) == ""


def test_robo_com_acento_e_pego_pelo_prefixo():
    # o prefixo dizia `rob[o?]` desde a 3.6.160: «Robô» só caía na régua de baixo
    assert NOMEHUM._RE_PREFIXO_ROBO.search("Robô Certidão")
    assert not NOMEHUM._RE_PREFIXO_ROBO.search("Robson")


def _nome_na_sessao(casa, username):
    from flask import session
    app = casa["app"]
    uid = None
    if username:
        uid = _con(casa).execute(
            "SELECT id FROM users WHERE username=?", (username,)).fetchone()["id"]
    with app.test_request_context():
        if uid is not None:
            session["user_id"] = int(uid)
        return app.extensions["usuario_nome"]()


def test_sessao_de_robo_nao_sai_no_nome_da_substituta(casa):
    casa["db"].set_settings({"ri_substituta": "BEATRIZ EXEMPLO DE SOUZA"})
    assert _nome_na_sessao(casa, "robo_teste") == NOMEHUM.MARCA_PENDENTE


def test_ninguem_logado_tambem_fica_pendente(casa):
    casa["db"].set_settings({"ri_substituta": "BEATRIZ EXEMPLO DE SOUZA"})
    assert _nome_na_sessao(casa, None) == NOMEHUM.MARCA_PENDENTE


def test_humano_continua_assinando_com_o_proprio_nome(casa):
    assert _nome_na_sessao(casa, "tabeliao") == HUMANO


def test_so_a_coluna_que_e_a_marca_recebe_o_nome(casa):
    import ato_selado as AS
    from bd_nativo import banco
    db = casa["db"]
    with db.transaction() as con:
        cid = int(banco(con).escrever(
            """INSERT INTO nt_cartoes (nome, documento, criado_em,
                   conferente_nome, observacao)
               VALUES (%s,%s,%s,%s,%s) RETURNING id""",
            ("FULANA PENDENTE", "00000001082", "2026-10-23T10:00:00",
             NOMEHUM.MARCA_PENDENTE, "texto com " + NOMEHUM.MARCA_PENDENTE))[0]["id"])
        trocadas = AS.assinar_o_que_ficou_pendente(
            con, tabela="nt_cartoes", ato_id=cid, quem=HUMANO)
    assert trocadas == ["conferente_nome"]
    linha = _con(casa).execute(
        "SELECT conferente_nome, observacao FROM nt_cartoes WHERE id=?",
        (cid,)).fetchone()
    assert linha["conferente_nome"] == HUMANO
    # teor com a marca no meio não se reescreve
    assert linha["observacao"] == "texto com " + NOMEHUM.MARCA_PENDENTE


def test_maquina_nao_assina_nem_por_esta_porta(casa):
    import ato_selado as AS
    from bd_nativo import banco
    db = casa["db"]
    with db.transaction() as con:
        cid = int(banco(con).escrever(
            """INSERT INTO nt_cartoes (nome, documento, criado_em, conferente_nome)
               VALUES (%s,%s,%s,%s) RETURNING id""",
            ("SICRANO", "00000001082", "2026-10-23T10:00:00",
             NOMEHUM.MARCA_PENDENTE))[0]["id"])
        assert AS.assinar_o_que_ficou_pendente(
            con, tabela="nt_cartoes", ato_id=cid, quem="Robo Teste Notas") == []


def test_robo_abre_cartao_pendente_e_quem_sela_assina(casa):
    if not tem_cryptography():
        pytest.skip("cryptography")
    c = casa["app"].test_client()
    _login(c, "robo_teste")
    with ligar_o_selador(casa):
        html = c.get("/notas/cartoes").get_data(as_text=True)
        c.post("/notas/cartoes",
               data={"acao": "novo", "nome": "ANA ASSINA DEPOIS",
                     "documento": "39053344705", "csrf_token": _token(html)},
               follow_redirects=True)
        linha = _con(casa).execute(
            "SELECT id, conferente_nome FROM nt_cartoes WHERE nome=?",
            ("ANA ASSINA DEPOIS",)).fetchone()
        assert linha["conferente_nome"] == NOMEHUM.MARCA_PENDENTE

        c2 = casa["app"].test_client()
        _login(c2, "tabeliao")
        html2 = c2.get(f"/notas/cartoes/{linha['id']}").get_data(as_text=True)
        c2.post(f"/notas/cartoes/{linha['id']}/selar",
                data={"csrf_token": _token(html2)}, follow_redirects=True)
        depois = _con(casa).execute(
            "SELECT selo_abertura, conferente_nome FROM nt_cartoes WHERE id=?",
            (linha["id"],)).fetchone()
        assert (depois["selo_abertura"] or "").strip()
        assert depois["conferente_nome"] == HUMANO
