"""Schema do editor de modelos — versionamento e chave por área (Marco 1).

Tabela nova `mo_versoes`: rascunhos, publicadas e arquivadas.
A chave liga/desliga por área mora em `settings` (chave
`modelos_editor_usar_publicada_<AREA>`), desligada por padrão.
Criação idempotente, no estilo dos demais `*_schema.py`.
"""
from __future__ import annotations

import sqlite3

AREA_RCPN = "RCPN"

STATUS_RASCUNHO = "rascunho"
STATUS_PUBLICADA = "publicada"
STATUS_ARQUIVADA = "arquivada"

STATUS_OK = (STATUS_RASCUNHO, STATUS_PUBLICADA, STATUS_ARQUIVADA)

PARTE_CORPO = "CORPO"
PARTE_ENCERRAMENTO = "ENCERRAMENTO"
PARTE_RODAPE = "RODAPE"
PARTE_MOLDE = "MOLDE"

PARTES_TEXTO = (PARTE_CORPO, PARTE_ENCERRAMENTO, PARTE_RODAPE)

# Chave de settings: modelos_editor_usar_publicada_RCPN = "0"|"1"
PREFIXO_CHAVE_AREA = "modelos_editor_usar_publicada_"


def chave_da_area(area: str) -> str:
    return f"{PREFIXO_CHAVE_AREA}{(area or '').strip().upper()}"


SCHEMA = """
CREATE TABLE IF NOT EXISTS mo_versoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    area TEXT NOT NULL,
    template_id TEXT NOT NULL,
    parte TEXT NOT NULL DEFAULT 'CORPO',
    conteudo TEXT,
    conteudo_blob BLOB,
    sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    autor TEXT,
    criado_em TEXT NOT NULL,
    nota TEXT
);

CREATE INDEX IF NOT EXISTS idx_mo_versoes_tpl
    ON mo_versoes(area, template_id, parte, status);

CREATE INDEX IF NOT EXISTS idx_mo_versoes_hist
    ON mo_versoes(area, template_id, parte, criado_em DESC);
"""

MIGRACOES: tuple[tuple[str, str, str], ...] = ()
INDICES_DEPOIS_DA_MIGRACAO: tuple[str, ...] = ()


def init_modelos_editor_schema(con: sqlite3.Connection) -> None:
    """Cria a tabela de versões do editor. Idempotente."""
    con.executescript(SCHEMA)
    for tabela, coluna, tipo in MIGRACOES:
        existentes = {linha[1] for linha in con.execute(
            f"PRAGMA table_info({tabela})")}
        if coluna not in existentes:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
    for comando in INDICES_DEPOIS_DA_MIGRACAO:
        con.execute(comando)
