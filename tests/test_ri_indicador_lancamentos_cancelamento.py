"""Cancelamento nos Livros 2/3 gera lançamento próprio nos Indicadores 4 e 5.

Pedido do oficial em 18/09/2026: além da averbação, histórico próprio.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import ra_registro as RA
import ri_indicador_lancamentos as RILANC
from ri_schema import init_ri_schema
from ra_schema import init_ra_schema
from banco_de_teste import conexao_de_teste  # noqa: E402


@pytest.fixture()
def con(tmp_path):
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=OFF")
    c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT)")
    init_ri_schema(c)
    init_ra_schema(c)
    c.commit()
    yield c
    c.close()


def test_schema_cria_tabela(con):
    cols = {r[1] for r in con.execute("PRAGMA table_info(ri_indicador_lancamentos)")}
    assert "livro" in cols and "especie" in cols


def test_cancelamento_livro2_gera_lancamentos_4_e_5(con):
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
               tipo_ficha, criado_em, logradouro, bairro)
           VALUES ('3999', '2-Q', '2-Q', 'ATIVO', 'ACERVO', '2026-09-18',
                   'Rua Teste 10', 'Centro')""")
    mid = int(cur.lastrowid)
    cur = con.execute(
        """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato,
               natureza_titulo, teor, teor_formato, cancelado, acervo,
               origem, hash_ato, lavrado_em)
           VALUES (?, 'R', 1, '2026-01-10', 'Compra e venda', 'teor',
                   'texto', 0, 0, 'MANUAL', 'h1', '2026-01-10')""",
        (mid,))
    ato_id = int(cur.lastrowid)
    con.execute(
        """INSERT INTO ri_partes (matricula_id, ato_id, nome, documento_tipo,
               documento_numero, papel, proprietario, proprietario_ativo)
           VALUES (?, ?, 'MARIA TESTE', 'CPF', '12345678901', 'adquirente',
                   1, 1)""",
        (mid, ato_id))
    con.execute(
        """INSERT INTO ri_partes (matricula_id, ato_id, nome, documento_tipo,
               documento_numero, papel, proprietario, proprietario_ativo)
           VALUES (?, ?, 'JOAO ANTIGO', 'CPF', '00000005070', 'transmitente',
                   0, 0)""",
        (mid, ato_id))
    con.commit()

    m = con.execute("SELECT * FROM ri_matriculas WHERE id=?", (mid,)).fetchone()
    alvo = con.execute("SELECT * FROM ri_atos WHERE id=?", (ato_id,)).fetchone()
    cur = con.execute(
        """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato,
               natureza_titulo, teor, teor_formato, cancelado, acervo,
               origem, hash_ato, lavrado_em)
           VALUES (?, 'AV', 2, '2026-09-18', 'Cancelamento de ato', 'canc',
                   'texto', 0, 0, 'MANUAL', 'h2', '2026-09-18')""",
        (mid,))
    av_id = int(cur.lastrowid)
    con.execute("UPDATE ri_atos SET cancelado=1, cancelado_por_ato_id=? WHERE id=?",
                (av_id, ato_id))
    out = RILANC.registrar_cancelamento_livro2(
        con, matricula=m, ato_alvo=alvo, averbacao_id=av_id,
        averbacao_numero=2, motivo="Pedido judicial de anulacao.",
        usuario="mario", agora="2026-09-18T12:00:00",
        data_lancamento="2026-09-18")
    con.commit()

    assert out["n_pessoas"] == 1
    rows4 = RILANC.listar(con, 4)
    rows5 = RILANC.listar(con, 5)
    assert len(rows4) == 1
    assert rows4[0]["origem_livro"] == 2
    assert rows4[0]["matricula_numero"] == "3999"
    assert "CANCELAMENTO" in rows4[0]["teor"]
    assert len(rows5) == 1
    assert rows5[0]["pessoa_nome"] == "MARIA TESTE"
    assert rows5[0]["averbacao_rotulo"] == "AV-02"


def test_cancelamento_livro3_gera_lancamentos_4_e_5(con):
    agora = "2026-09-18T12:00:00"
    cur = con.execute(
        """INSERT INTO ra_registros(numero, livro, natureza, titulo_tipo,
               titulo_numero, situacao, origem, teor_formato, criado_em)
           VALUES (1888, '3', 'CEDULA_CREDITO_RURAL', 'Cedula Rural',
                   '99/0001', 'ATIVO', 'MANUAL', 'texto', ?)""",
        (agora,))
    rid = int(cur.lastrowid)
    con.execute(
        """INSERT INTO ra_partes (registro_id, nome, documento_tipo,
               documento_numero, papel)
           VALUES (?, 'BANCO TESTE S/A', 'CNPJ', '00000041000188', 'credor')""",
        (rid,))
    con.commit()
    out = RA.cancelar(con, rid, motivo="Quitacao integral comprovada.",
                      agora=agora, usuario="mario")
    con.commit()

    rows4 = [x for x in RILANC.listar(con, 4) if x["origem_livro"] == 3]
    rows5 = [x for x in RILANC.listar(con, 5) if x["origem_livro"] == 3]
    assert len(rows4) == 1
    assert len(rows5) == 1
    assert rows5[0]["pessoa_nome"] == "BANCO TESTE S/A"
    assert out["rotulo"].startswith("AV-")
    situ = con.execute("SELECT situacao FROM ra_registros WHERE id=?",
                       (rid,)).fetchone()["situacao"]
    assert situ == "CANCELADO"
