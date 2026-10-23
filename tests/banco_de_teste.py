"""O banco solto de um teste de unidade — o substituto do `:memory:`.

Módulo já convertido para PostgreSQL nativo não roda num `sqlite3` em
memória. Este arquivo temporário é «banco da casa» para a ponte: no modo
PostgreSQL (CG_TEST_BACKEND=pg) ele vira um schema próprio no servidor de
teste; sem a variável, continua um SQLite comum.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import banco_pg


def conexao_de_teste() -> sqlite3.Connection:
    arquivo = Path(tempfile.mkdtemp(prefix="cg_teste_")) / "teste.sqlite3"
    banco_pg.registrar_banco(arquivo)
    return sqlite3.connect(str(arquivo))
