"""Relato #116: data do teor alinhada ao dia do selo."""
from __future__ import annotations

import sqlite3
from datetime import datetime

import notas_teor as NT
import pytest


@pytest.fixture
def con():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE nt_atos (
            id INTEGER PRIMARY KEY,
            tipo TEXT, data TEXT, hora TEXT, teor TEXT, teor_formato TEXT,
            modelo_codigo TEXT, modelo_valores TEXT, lavrado_nome TEXT,
            lavrado_titulo TEXT
        );
        CREATE TABLE nt_modelos (
            codigo TEXT PRIMARY KEY, corpo TEXT, origem TEXT, ativo INTEGER
        );
        CREATE TABLE nt_ato_partes (
            id INTEGER PRIMARY KEY, ato_id INTEGER, nome TEXT, documento TEXT,
            testemunha INTEGER, ordem INTEGER, qualificacao TEXT,
            tipo_pessoa TEXT, nacionalidade TEXT, estado_civil TEXT,
            profissao TEXT, endereco TEXT
        );
        """
    )
    yield c
    c.close()


def test_montar_eoficio_atualiza_data_no_teor(con):
    con.execute(
        "INSERT INTO nt_modelos (codigo, corpo, origem, ativo) VALUES (?,?,?,1)",
        ("M1", "<p>clausula de poderes</p>", "EOFICIO"),
    )
    con.execute(
        """INSERT INTO nt_atos
           (id, tipo, data, hora, teor, modelo_codigo, lavrado_nome, lavrado_titulo)
           VALUES (1, 'ESCRITURA', '2026-09-20', '10:00', '', 'M1', 'Tabeliao', 'Tabeliao')"""
    )
    con.execute(
        """INSERT INTO nt_ato_partes
           (ato_id, nome, documento, testemunha, ordem, qualificacao, tipo_pessoa,
            nacionalidade, estado_civil, profissao, endereco)
           VALUES (1, 'JOAO', '123', 0, 1, 'OUTORGANTE', 'F', 'br', 'sol', 'adv', 'rua')"""
    )
    con.execute(
        """INSERT INTO nt_ato_partes
           (ato_id, nome, documento, testemunha, ordem, qualificacao, tipo_pessoa,
            nacionalidade, estado_civil, profissao, endereco)
           VALUES (1, 'MARIA', '456', 0, 2, 'OUTORGADO', 'F', 'br', 'sol', 'adv', 'rua')"""
    )
    quando = datetime(2026, 9, 30, 15, 30)
    sv = {"ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
    NT.atualizar_teor_para_data_de_selo(
        con, 1, quando=quando, sv=sv, lavrado_nome="Tabeliao", lavrado_titulo="Tabeliao"
    )
    row = con.execute("SELECT data, teor FROM nt_atos WHERE id=1").fetchone()
    assert row["data"] == "2026-09-30"
    assert "30 de setembro de 2026" in (row["teor"] or "")


def test_teor_livre_substitui_data_por_extenso(con):
    con.execute(
        """INSERT INTO nt_atos (id, tipo, data, hora, teor)
           VALUES (2, 'ESCRITURA', '2026-09-20', '09:00',
                   '<p>Aos 20 de setembro de 2026 nesta cidade.</p>')"""
    )
    quando = datetime(2026, 9, 30, 11, 0)
    NT.atualizar_teor_para_data_de_selo(
        con,
        2,
        quando=quando,
        sv={"ri_cidade": "Cidade Exemplo", "ri_uf": "MA"},
        lavrado_nome="T",
        lavrado_titulo="T",
    )
    row = con.execute("SELECT data, teor FROM nt_atos WHERE id=2").fetchone()
    assert row["data"] == "2026-09-30"
    assert "30 de setembro de 2026" in row["teor"]
    assert "20 de setembro de 2026" not in row["teor"]
