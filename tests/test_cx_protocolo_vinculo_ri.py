"""Vinculo cx_protocolos.ri_protocolo_id <-> prenotacao do RI.

O debito do oficial («faca o vinculo»): a FK existia, mas 0 de ~21 mil
protocolos a preenchiam. O lavrar so auto-liga itens quando a ponte esta
gravada — e a ponte so nasce de escolha humana (ou de evidencia ja
apontada no deposito), nunca de junção por nome.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

sys.path.insert(0, str(RAIZ / "tests"))
from banco_de_teste import conexao_de_teste  # noqa: E402

import caixa_protocolo as CXP  # noqa: E402


def _base() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE cx_protocolos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero TEXT NOT NULL UNIQUE,
            data_abertura TEXT NOT NULL,
            hora TEXT, atribuicao TEXT, interessado TEXT,
            interessado_documento TEXT, telefone TEXT, email TEXT,
            assunto TEXT, observacao TEXT, previsao_entrega TEXT,
            tipo TEXT DEFAULT 'SERVICO',
            documento_tipo TEXT, documento_numero TEXT, documento_descricao TEXT,
            situacao TEXT NOT NULL DEFAULT 'ABERTO',
            finalizado INTEGER NOT NULL DEFAULT 0,
            data_finalizacao TEXT,
            ri_protocolo_id INTEGER, ri_matricula_id INTEGER,
            criado_em TEXT NOT NULL, criado_por INTEGER,
            encerramento_motivo TEXT, encerrado_por TEXT
        );
        CREATE TABLE ri_protocolos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero INTEGER, livro TEXT, situacao TEXT,
            apresentante TEXT, natureza_titulo TEXT,
            matricula_id INTEGER, matricula_numero TEXT,
            data_prenotacao TEXT
        );
        CREATE TABLE cx_depositos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero TEXT, protocolo_id INTEGER, ri_protocolo_id INTEGER,
            data TEXT, depositante TEXT, valor TEXT, saldo TEXT,
            encerrado INTEGER DEFAULT 0, observacao TEXT
        );
        CREATE TABLE cx_protocolo_atos(
            id INTEGER PRIMARY KEY, protocolo_id INTEGER, quitado INTEGER
        );
    """)
    return con


def test_vincular_grava_fk_e_matricula_quando_conhecida():
    con = _base()
    con.execute(
        """INSERT INTO ri_protocolos
           (id, numero, livro, situacao, apresentante, matricula_id, matricula_numero)
           VALUES (7, 11570, '1A', 'ABERTO', 'Fulano', 4533, '1421')""")
    aberto = CXP.abrir(con, data_abertura="2026-09-15", agora="2026-09-15 12:00:00",
                       atribuicao="RI", interessado="Fulano",
                       ri_protocolo_id=7)
    assert aberto["ri_protocolo_id"] == 7
    assert aberto["prenotacao_numero"] == 11570
    assert aberto["ri_matricula_id"] == 4533
    row = con.execute("SELECT ri_protocolo_id, ri_matricula_id FROM cx_protocolos WHERE id=?",
                      (aberto["protocolo_id"],)).fetchone()
    assert row["ri_protocolo_id"] == 7
    assert row["ri_matricula_id"] == 4533


def test_vincular_nao_inventa_matricula_sem_id():
    con = _base()
    con.execute(
        """INSERT INTO ri_protocolos
           (id, numero, livro, situacao, matricula_id, matricula_numero)
           VALUES (8, 11571, '1A', 'ABERTO', NULL, 'QUADRA 03')""")
    feito = CXP.abrir(con, data_abertura="2026-09-15", agora="2026-09-15 12:00:00",
                      atribuicao="RI", interessado="Beltrano")
    lig = CXP.vincular_ri(con, feito["protocolo_id"], 8)
    assert lig["ri_protocolo_id"] == 8
    assert lig["ri_matricula_id"] is None
    row = con.execute("SELECT ri_matricula_id FROM cx_protocolos WHERE id=?",
                      (feito["protocolo_id"],)).fetchone()
    assert row["ri_matricula_id"] is None


def test_vincular_recusa_prenotacao_inexistente():
    con = _base()
    feito = CXP.abrir(con, data_abertura="2026-09-15", agora="2026-09-15 12:00:00",
                      interessado="X")
    with pytest.raises(CXP.ProtocoloError):
        CXP.vincular_ri(con, feito["protocolo_id"], 99999)


def test_desvincular_limpa_ponte():
    con = _base()
    con.execute(
        """INSERT INTO ri_protocolos (id, numero, livro, situacao)
           VALUES (9, 1, '1A', 'ABERTO')""")
    aberto = CXP.abrir(con, data_abertura="2026-09-15", agora="2026-09-15 12:00:00",
                       interessado="Y", ri_protocolo_id=9)
    CXP.desvincular_ri(con, aberto["protocolo_id"])
    row = con.execute("SELECT ri_protocolo_id, ri_matricula_id FROM cx_protocolos WHERE id=?",
                      (aberto["protocolo_id"],)).fetchone()
    assert row["ri_protocolo_id"] is None
    assert row["ri_matricula_id"] is None


def test_backfill_por_deposito_dry_run_e_aplica():
    con = _base()
    con.execute(
        """INSERT INTO ri_protocolos (id, numero, livro, situacao)
           VALUES (10, 100, '1A', 'ABERTO')""")
    cx = CXP.abrir(con, data_abertura="2026-09-15", agora="2026-09-15 12:00:00",
                   interessado="Z")
    con.execute(
        """INSERT INTO cx_depositos (numero, protocolo_id, ri_protocolo_id)
           VALUES ('DP1', ?, 10)""", (cx["protocolo_id"],))
    seco = CXP.backfill_por_deposito(con, dry_run=True)
    assert seco["candidatos"] == 1
    assert seco["aplicados"] == 0
    assert con.execute(
        "SELECT ri_protocolo_id FROM cx_protocolos WHERE id=?",
        (cx["protocolo_id"],)).fetchone()["ri_protocolo_id"] is None
    molhado = CXP.backfill_por_deposito(con, dry_run=False)
    assert molhado["aplicados"] == 1
    assert con.execute(
        "SELECT ri_protocolo_id FROM cx_protocolos WHERE id=?",
        (cx["protocolo_id"],)).fetchone()["ri_protocolo_id"] == 10


def test_backfill_sem_candidatos_quando_deposito_nao_tem_protocolo_caixa():
    """O acervo real desta casa: deposito aponta ao RI, mas nao ao cx."""
    con = _base()
    con.execute(
        """INSERT INTO ri_protocolos (id, numero, livro, situacao)
           VALUES (11, 101, '1A', 'ABERTO')""")
    con.execute(
        """INSERT INTO cx_depositos (numero, protocolo_id, ri_protocolo_id)
           VALUES ('DP2', NULL, 11)""")
    r = CXP.backfill_por_deposito(con, dry_run=True)
    assert r["candidatos"] == 0