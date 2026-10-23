# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3

import dev_projetos as DP
import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

AGORA = "2026-10-01T16:00:00"


def _mem() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    return con


def test_init_schema_cria_tabelas():
    con = _mem()
    DP.init_dev_projetos_schema(con)
    tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "dev_projetos" in tables
    assert "dev_projetos_andamento" in tables


def test_init_schema_coluna_proximo_passo():
    con = _mem()
    DP.init_dev_projetos_schema(con)
    cols = {row[1] for row in con.execute("PRAGMA table_info(dev_projetos)").fetchall()}
    assert "proximo_passo" in cols


def test_seed_sandbox_oito_projetos():
    con = _mem()
    DP.init_dev_projetos_schema(con)
    DP.seed_sandbox_exemplo(con, agora=AGORA)
    rows = DP.listar_projetos(con)
    assert len(rows) == 8


def test_seed_idempotente():
    con = _mem()
    DP.init_dev_projetos_schema(con)
    DP.seed_sandbox_exemplo(con, agora=AGORA)
    DP.seed_sandbox_exemplo(con, agora=AGORA)
    assert len(DP.listar_projetos(con)) == 8


def test_alterar_status():
    con = _mem()
    DP.init_dev_projetos_schema(con)
    DP.seed_sandbox_exemplo(con, agora=AGORA)
    pid = int(DP.listar_projetos(con)[0]["id"])
    DP.alterar_status(con, pid, DP.STATUS_CONCLUIDO, agora=AGORA)
    row = DP.obter_projeto(con, pid)
    assert row["status_geral"] == DP.STATUS_CONCLUIDO


def test_alterar_proximo_passo():
    con = _mem()
    DP.init_dev_projetos_schema(con)
    DP.seed_sandbox_exemplo(con, agora=AGORA)
    pid = int(DP.listar_projetos(con)[0]["id"])
    DP.alterar_proximo_passo(con, pid, "Aguardando IEPTB", agora=AGORA)
    row = DP.obter_projeto(con, pid)
    assert row["proximo_passo"] == "Aguardando IEPTB"


def test_registrar_andamento():
    con = _mem()
    DP.init_dev_projetos_schema(con)
    DP.seed_sandbox_exemplo(con, agora=AGORA)
    pid = int(DP.listar_projetos(con)[0]["id"])
    DP.registrar_andamento(con, pid, "Nota pytest", autor="admin", agora=AGORA)
    hist = DP.listar_andamento(con, pid)
    assert any(h["texto"] == "Nota pytest" for h in hist)


def test_aplicar_pendencias_20261001_idempotente():
    con = _mem()
    DP.init_dev_projetos_schema(con)
    DP.seed_sandbox_exemplo(con, agora=AGORA)
    n1 = DP.aplicar_atualizacao_pendencias_20261001(con)
    n2 = DP.aplicar_atualizacao_pendencias_20261001(con)
    assert n1 == 8
    assert n2 == 8
    cra = con.execute(
        "SELECT proximo_passo FROM dev_projetos WHERE titulo=?",
        ("Homologação CRA21 (API)",),
    ).fetchone()
    assert cra[0] and "IEPTB" in cra[0]
    cnt = con.execute(
        "SELECT COUNT(*) FROM dev_projetos_andamento WHERE autor=?",
        (DP.ATUALIZACAO_20261001_AUTOR,),
    ).fetchone()[0]
    assert cnt == 8
def test_formatar_atualizado_em_local_naive_iso():
    assert DP.formatar_atualizado_em_local("2026-10-01T17:30:00") == "01/10/26 - 17:30"


def test_listar_projetos_inclui_atualizado_em_exibicao():
    con = _mem()
    DP.init_dev_projetos_schema(con)
    DP.seed_sandbox_exemplo(con, agora=AGORA)
    rows = DP.listar_projetos(con)
    assert rows
    assert "atualizado_em_exibicao" in rows[0]
    assert rows[0]["atualizado_em_exibicao"] != "—"
