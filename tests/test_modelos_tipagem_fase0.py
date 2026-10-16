# -*- coding: utf-8 -*-
"""Fase 3 — tipagem e inventário dos papéis (aditivo; não mexe em texto maduro)."""
from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

import modelos_da_casa as MOD

TIPOS_OK = {"TEXTO", "MOLDE_ODT", "MINUTA_ATO", "DOC_AVULSO", "MONTADO_POR_CAMPO"}
ROOT = Path(__file__).resolve().parents[1]


def test_toda_chave_do_catalogo_tem_tipo():
    for c in MOD.CATALOGO:
        assert c.get("tipo") in TIPOS_OK, c["chave"]
        assert c["chave"] in MOD.TIPOS_POR_CHAVE


def test_tipos_por_chave_cobre_o_catalogo_e_so_ele():
    assert set(MOD.TIPOS_POR_CHAVE) == {c["chave"] for c in MOD.CATALOGO}


def test_todo_padrao_ainda_importa_depois_da_tipagem():
    for c in MOD.CATALOGO:
        mod, const = c["padrao"]
        val = getattr(importlib.import_module(mod), const)
        assert val is not None


def test_override_notas_cartao_ficha_permanece(tmp_path=None):
    """O único override maduro medido na produção não pode sumir no código."""
    db = Path(r"C:\ProgramData\CartorioGestao\cartorio_gestao.sqlite3")
    if not db.is_file():
        return  # CI sem o banco da casa
    con = sqlite3.connect(str(db))
    row = con.execute(
        "SELECT atualizado_por, length(corpo) FROM mo_elementos "
        "WHERE ato=? AND parte=?",
        ("NOTAS_CARTAO_FICHA", "CORPO"),
    ).fetchone()
    assert row is not None, "override NOTAS_CARTAO_FICHA sumiu do banco"
    # quem ajustou é gente da casa: o nome sai do banco, e não se escreve aqui
    # (este arquivo vai ao GitHub — 14/10/2026)
    assert (row[0] or "").strip()
    assert row[1] > 100
    corpo = MOD.corpo_de(con, "NOTAS_CARTAO_FICHA")
    assert corpo and len(corpo) > 100


def test_inventario_modelos_exit_zero():
    import runpy
    import sys
    script = ROOT / "tools" / "inventario_modelos.py"
    assert script.is_file()
    old = sys.argv[:]
    try:
        sys.argv = [str(script)]
        try:
            runpy.run_path(str(script), run_name="__main__")
            code = 0
        except SystemExit as e:
            code = int(e.code or 0)
    finally:
        sys.argv = old
    assert code == 0


def test_inventario_minutas_exit_zero():
    import runpy
    import sys

    script = ROOT / "tools" / "inventario_modelos.py"
    old = sys.argv[:]
    try:
        sys.argv = [str(script), "--minutas"]
        try:
            runpy.run_path(str(script), run_name="__main__")
            code = 0
        except SystemExit as e:
            code = int(e.code or 0)
    finally:
        sys.argv = old
    assert code == 0
