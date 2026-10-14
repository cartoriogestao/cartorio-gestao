# -*- coding: utf-8 -*-
"""Titulo e fecho de prenotacao na certidao RI de inteiro teor (3.6.188)."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ri_web import (  # noqa: E402
    clausula_html_prenotacoes_abertas,
    prenotacoes_abertas_da_matricula,
)


def _fmt(d):
    if not d:
        return ""
    # espelho minimo de fmt_date ISO -> DD/MM/AAAA
    s = str(d)[:10]
    if len(s) == 10 and s[4] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"
    return s


def test_clausula_negativa_quando_nao_ha_prenotacao():
    html = clausula_html_prenotacoes_abertas([], fmt_date=_fmt)
    assert "CERTIFICO ainda que" in html
    assert "não há" in html or "nÃ£o hÃ¡" in html or "n\u00e3o h\u00e1" in html
    assert "6.015" in html
    assert "149/2023" in html
    assert "Protocolo" not in html


def test_clausula_positiva_lista_protocolo_real():
    html = clausula_html_prenotacoes_abertas(
        [{"id": 1, "numero": 11546, "data_prenotacao": "2026-08-04",
          "natureza_titulo": None, "objeto": "TITULO DE DOMINIO"}],
        fmt_date=_fmt,
    )
    assert "há" in html or "h\u00e1" in html
    assert "11546" in html
    assert "04/08/2026" in html
    assert "TITULO DE DOMINIO" in html
    assert "não há" not in html and "n\u00e3o h\u00e1" not in html


def test_molde_fabrica_tem_titulo_e_clausula():
    from ri_odt import MODELO_CERTIDAO_PADRAO
    assert "tipo_certidao_nome|upper" in MODELO_CERTIDAO_PADRAO
    # titulo tambem no ramo INTEIRO_TEOR (nao so no else)
    trecho = MODELO_CERTIDAO_PADRAO.split('tipo_certidao == "INTEIRO_TEOR"')[1]
    trecho = trecho.split("{% else %}")[0]
    assert "tipo_certidao_nome|upper" in trecho
    assert "clausula_prenotacoes_abertas" in trecho


def test_prenotacoes_ligam_por_ato_mesmo_com_matricula_id_divergente(tmp_path):
    """Caso 4019/11546: ato cita o protocolo; ri_protocolos.matricula_id e outra."""
    db = tmp_path / "t.sqlite3"
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    con.executescript(
        """
        CREATE TABLE ri_protocolos (
            id INTEGER PRIMARY KEY, numero INTEGER, data_prenotacao TEXT,
            data_limite TEXT, situacao TEXT, natureza_titulo TEXT, objeto TEXT,
            matricula_id INTEGER, matricula_numero TEXT);
        CREATE TABLE ri_atos (
            id INTEGER PRIMARY KEY, matricula_id INTEGER, protocolo TEXT);
        INSERT INTO ri_protocolos VALUES
            (1, 11546, '2026-08-04', NULL, 'ABERTO', NULL, 'TITULO', 999, NULL);
        INSERT INTO ri_atos VALUES (10, 5381, '11546');
        """
    )
    lista = prenotacoes_abertas_da_matricula(con, 5381, "4019")
    assert len(lista) == 1
    assert str(lista[0]["numero"]) == "11546"


def test_prenotacoes_por_matricula_id_direto(tmp_path):
    db = tmp_path / "t.sqlite3"
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    con.executescript(
        """
        CREATE TABLE ri_protocolos (
            id INTEGER PRIMARY KEY, numero INTEGER, data_prenotacao TEXT,
            data_limite TEXT, situacao TEXT, natureza_titulo TEXT, objeto TEXT,
            matricula_id INTEGER, matricula_numero TEXT);
        CREATE TABLE ri_atos (
            id INTEGER PRIMARY KEY, matricula_id INTEGER, protocolo TEXT);
        INSERT INTO ri_protocolos VALUES
            (1, 11573, '2026-09-22', NULL, 'ABERTO', 'REGISTRO', NULL, 3507, '824');
        INSERT INTO ri_protocolos VALUES
            (2, 1, '2026-01-01', NULL, 'ENCERRADO', NULL, NULL, 3507, '824');
        """
    )
    lista = prenotacoes_abertas_da_matricula(con, 3507, "824")
    assert len(lista) == 1
    assert lista[0]["numero"] == 11573
