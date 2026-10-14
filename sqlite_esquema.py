"""PERGUNTAR O ESQUEMA AO BANCO, NUM LUGAR SÓ — 12/10/2026.

Módulo de domínio que precisa saber se uma coluna existe (migração aditiva,
coluna que nasceu depois) pergunta aqui, e não ao SQLite direto. O `PRAGMA`
é a forma do SQLite de responder; no dia em que o banco for outro, muda-se
este arquivo, e não os módulos que perguntam (ver
`DOCUMENTACAO/MIGRAR_DE_BANCO.md` e `tests/test_portabilidade.py`).

Nasceu de três módulos que perguntavam cada um à sua maneira —
`gestor_conferencia`, `produtividade` e `rc_averbacao_modelos_web`.
"""
from __future__ import annotations

import re
import sqlite3

_NOME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def colunas(con: sqlite3.Connection, tabela: str) -> set[str]:
    """Os nomes das colunas da tabela; vazio se ela não existe. Só lê.

    O nome da tabela vai dentro do comando (o PRAGMA não aceita parâmetro),
    e por isso só passa nome de identificador — nada que venha de fora."""
    if not _NOME.match(tabela or ""):
        raise ValueError(f"nome de tabela inválido: {tabela!r}")
    return {str(linha[1]) for linha in con.execute(f"PRAGMA table_info({tabela})")}
