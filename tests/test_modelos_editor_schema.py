"""Schema mo_versoes — criação idempotente."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

from banco_de_teste import conexao_de_teste
from modelos_editor_schema import init_modelos_editor_schema, SCHEMA


@pytest.fixture()
def con(tmp_path):
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def test_schema_idempotente(con):
    init_modelos_editor_schema(con)
    init_modelos_editor_schema(con)
    cols = {r[1] for r in con.execute("PRAGMA table_info(mo_versoes)")}
    for obr in ("id", "area", "template_id", "parte", "conteudo",
                "conteudo_blob", "sha256", "status", "autor",
                "criado_em", "nota"):
        assert obr in cols
    # índices
    idxs = {r[1] for r in con.execute("PRAGMA index_list(mo_versoes)")}
    assert "idx_mo_versoes_tpl" in idxs
