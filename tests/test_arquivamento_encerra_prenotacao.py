# -*- coding: utf-8 -*-
"""Arquivamento 16.39 encerra a prenotação do ato (3.6.190)."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

from bd_nativo import banco  # noqa: E402
from banco_de_teste import conexao_de_teste  # noqa: E402

WEB = RAIZ / "ri_web.py"


def _load_helpers():
    src = WEB.read_text(encoding="utf-8")
    start = src.index("def encerrar_prenotacao_do_ato_apos_arquivamento")
    end = src.index("\n    def amarrar_prenotacao", start)
    chunk = src[start:end]
    linhas = []
    for ln in chunk.splitlines(True):
        if ln.startswith("    "):
            linhas.append(ln[4:])
        else:
            linhas.append(ln)
    ns: dict = {"banco": banco}
    exec("".join(linhas), ns)
    return ns


@pytest.fixture(scope="module")
def fns():
    return _load_helpers()


def _db(tmp_path):
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.executescript(
        """
        CREATE TABLE ri_protocolos (
            id INTEGER PRIMARY KEY, numero INTEGER, situacao TEXT,
            situacao_anterior TEXT,
            encerrado_em TEXT, encerrado_por TEXT,
            motivo_encerramento TEXT, obs_encerramento TEXT);
        CREATE TABLE ri_atos (
            id INTEGER PRIMARY KEY, protocolo TEXT);
        """
    )
    return con


def test_encerra_quando_aberto(fns, tmp_path):
    con = _db(tmp_path)
    con.execute(
        "INSERT INTO ri_protocolos (id, numero, situacao, situacao_anterior) "
        "VALUES (1, 11546, 'ABERTO', NULL)")
    con.execute("INSERT INTO ri_atos VALUES (10, '11546')")
    r = fns["encerrar_prenotacao_do_ato_apos_arquivamento"](con, 10)
    assert r["encerrou"] is True
    assert r["numero"] == 11546
    sit = con.execute(
        "SELECT situacao, motivo_encerramento, obs_encerramento, encerrado_em "
        "FROM ri_protocolos WHERE id=1").fetchone()
    assert sit[0] == "ENCERRADO"
    assert sit[1] == "Título registrado"
    assert sit[2] == "arquivamento 16.39"
    assert sit[3]
    frase = fns["recado_do_encerramento_por_arquivamento"](r)
    assert "ENCERRADA" in frase
    assert "11546" in frase


def test_nao_falha_sem_protocolo_no_ato(fns, tmp_path):
    con = _db(tmp_path)
    con.execute("INSERT INTO ri_atos VALUES (10, NULL)")
    assert fns["encerrar_prenotacao_do_ato_apos_arquivamento"](con, 10) is None


def test_ja_encerrada_nao_reescreve(fns, tmp_path):
    con = _db(tmp_path)
    con.execute(
        "INSERT INTO ri_protocolos (id, numero, situacao, situacao_anterior) "
        "VALUES (1, 11546, 'ENCERRADO', 'ABERTO')")
    con.execute("INSERT INTO ri_atos VALUES (10, '11.546')")
    r = fns["encerrar_prenotacao_do_ato_apos_arquivamento"](con, 10)
    assert r["ja_encerrada"] is True
    assert r.get("encerrou") is not True


def test_protocolo_inexistente(fns, tmp_path):
    con = _db(tmp_path)
    con.execute("INSERT INTO ri_atos VALUES (10, '99999')")
    r = fns["encerrar_prenotacao_do_ato_apos_arquivamento"](con, 10)
    assert r["achou"] is False
