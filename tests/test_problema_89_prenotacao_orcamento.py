"""Problema #89 — emolumentos/orçamento dentro da prenotação RI.

Sugestão oficial (impressão 8f7ddaf5ab458883): «colocar a aba de cálculo de
emolumentos e orçamento dentro da prenotação». A passada mínima expõe o painel
na tela do título, reusa `ri_protocolo_id` e delega tabela/quitação ao caixa.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import caixa_protocolo as CXP

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    c = cg_casa["cliente"]
    db.create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post(
        "/login",
        data={
            "username": "jean",
            "password": SENHA,
            "csrf_token": _token(c.get("/login").get_data(as_text=True)),
        },
        follow_redirects=True,
    )
    return cg_casa


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _prenotacao(con, *, numero=11589):
    cur = con.execute(
        """INSERT INTO ri_protocolos (numero, livro, data_prenotacao,
               apresentante, situacao, criado_em)
           VALUES (?, '1A', '2026-09-21', 'Beatriz Teste', 'ABERTO',
                   '2026-09-21T14:30')""",
        (numero,),
    )
    return int(cur.lastrowid)


def _caixa_ligado(con, ri_id, *, numero="2026.09.89", itens=()):
    cur = con.execute(
        """INSERT INTO cx_protocolos (numero, data_abertura, atribuicao,
               interessado, situacao, ri_protocolo_id, criado_em)
           VALUES (?, '2026-09-21', 'RI', 'Beatriz Teste', 'ABERTO', ?,
                   '2026-09-21T14:30')""",
        (numero, ri_id),
    )
    pid = int(cur.lastrowid)
    for codigo in itens:
        con.execute(
            """INSERT INTO cx_protocolo_atos (protocolo_id, codigo_ato,
                   descricao, quantidade, valor_total, quitado, origem)
               VALUES (?, ?, 'registro', 1, '100,00', 0, 'MANUAL')""",
            (pid, codigo),
        )
    return pid


def test_painel_emolumentos_na_prenotacao_sem_caixa(casa):
    con = _con(casa)
    with con:
        pid = _prenotacao(con)
    tela = casa["cliente"].get(
        f"/registro-imoveis/protocolo/{pid}").get_data(as_text=True)
    assert "Emolumentos e orçamento" in tela
    assert "Abrir protocolo de caixa deste título" in tela
    assert 'id="emolumentos-orcamento"' in tela


def test_abrir_caixa_pela_prenotacao_vincula_fk(casa):
    con = _con(casa)
    with con:
        pid = _prenotacao(con, numero=11590)
    html = casa["cliente"].get(
        f"/registro-imoveis/protocolo/{pid}").get_data(as_text=True)
    casa["cliente"].post(
        f"/registro-imoveis/protocolo/{pid}",
        data={"csrf_token": _token(html), "acao": "abrir_caixa"},
        follow_redirects=True,
    )
    row = _con(casa).execute(
        "SELECT id, ri_protocolo_id FROM cx_protocolos "
        "WHERE ri_protocolo_id=?",
        (pid,),
    ).fetchone()
    assert row is not None
    tela = casa["cliente"].get(
        f"/registro-imoveis/protocolo/{pid}").get_data(as_text=True)
    assert "Acrescentar serviços" in tela
    assert f"/caixa/protocolos/{row['id']}/orcamento" not in tela


def test_prenotacao_com_itens_mostra_orcamento_no_painel(casa):
    con = _con(casa)
    with con:
        pid = _prenotacao(con, numero=11591)
        cx = _caixa_ligado(con, pid, itens=("16.3",))
    tela = casa["cliente"].get(
        f"/registro-imoveis/protocolo/{pid}").get_data(as_text=True)
    assert "Emolumentos e orçamento" in tela
    assert f"/caixa/protocolos/{cx}/orcamento" in tela
    assert "16.3" in tela
