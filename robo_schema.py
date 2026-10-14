"""Tabelas dos robos de rascunho — dentro do Cartorio Gestao.

Decisao do oficial em 07/09/2026: gerenciador de robos no mesmo Flask/SQLite.
Um robo = um tipo de ato. Treino = prompt + exemplos (sem fine-tune nesta fatia).

TABELA NOVA VAI NO SCHEMA, nao em MIGRACAO. MIGRACOES so ALTER TABLE ADD
COLUMN. Indice de coluna nova iria em INDICES_DEPOIS_DA_MIGRACAO.

Chaves de API nunca no codigo: api_key_* e provedor_padrao comecam vazios.
Nunca logar API key. Nunca gravar rascunho de teste no livro/RCPN.
"""
from __future__ import annotations

import sqlite3
from typing import Any

PROVEDORES = ("grok", "gpt", "claude", "deepseek")

CHAVE_GROK = "api_key_grok"
CHAVE_GPT = "api_key_gpt"
CHAVE_CLAUDE = "api_key_claude"
CHAVE_DEEPSEEK = "api_key_deepseek"
CHAVE_PADRAO = "provedor_padrao"

CHAVES_API = {
    "grok": CHAVE_GROK,
    "gpt": CHAVE_GPT,
    "claude": CHAVE_CLAUDE,
    "deepseek": CHAVE_DEEPSEEK,
}

CHAVES_CONFIG = (
    CHAVE_GROK, CHAVE_GPT, CHAVE_CLAUDE, CHAVE_DEEPSEEK, CHAVE_PADRAO,
)

MODO_LOCAL = "local"
MODO_API = "api"

SCHEMA = """
CREATE TABLE IF NOT EXISTS robo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    ato TEXT NOT NULL,
    provedor TEXT NOT NULL DEFAULT 'grok',
    prompt TEXT NOT NULL DEFAULT '',
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT,
    atualizado_em TEXT
);
CREATE INDEX IF NOT EXISTS idx_robo_ativo ON robo(ativo, nome);

CREATE TABLE IF NOT EXISTS robo_exemplo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    robo_id INTEGER NOT NULL REFERENCES robo(id),
    entrada TEXT NOT NULL,
    saida_esperada TEXT NOT NULL,
    peso INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_robo_exemplo_robo
    ON robo_exemplo(robo_id);

CREATE TABLE IF NOT EXISTS robo_config (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS robo_teste_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    robo_id INTEGER NOT NULL REFERENCES robo(id),
    usuario TEXT,
    pedido TEXT,
    rascunho TEXT,
    modo TEXT NOT NULL DEFAULT 'local',
    criado_em TEXT
);
CREATE INDEX IF NOT EXISTS idx_robo_teste_log_robo
    ON robo_teste_log(robo_id, criado_em);
"""

MIGRACOES: tuple[tuple[str, str, str], ...] = ()
INDICES_DEPOIS_DA_MIGRACAO: tuple[str, ...] = ()


def init_robo_schema(con: sqlite3.Connection) -> None:
    """Cria as tabelas dos robos. Idempotente."""
    con.executescript(SCHEMA)
    for tabela, coluna, tipo in MIGRACOES:
        existentes = {linha[1] for linha in con.execute(
            f"PRAGMA table_info({tabela})")}
        if coluna not in existentes:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
    for comando in INDICES_DEPOIS_DA_MIGRACAO:
        con.execute(comando)
    for chave in CHAVES_CONFIG:
        con.execute(
            "INSERT OR IGNORE INTO robo_config(chave, valor) VALUES (?, '')",
            (chave,),
        )


def ler_config(con: sqlite3.Connection, chave: str) -> str:
    row = con.execute(
        "SELECT valor FROM robo_config WHERE chave = ?", (chave,)
    ).fetchone()
    if not row:
        return ""
    return (row[0] if not hasattr(row, "keys") else row["valor"]) or ""


def gravar_config(con: sqlite3.Connection, chave: str, valor: str) -> None:
    con.execute(
        "INSERT INTO robo_config(chave, valor) VALUES (?, ?) "
        "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
        (chave, valor or ""),
    )


def mascarar_segredo(valor: str) -> str:
    """Mostra so os ultimos 4. Nunca a chave inteira."""
    t = (valor or "").strip()
    if not t:
        return ""
    if len(t) <= 4:
        return "****"
    return "••••" + t[-4:]


def api_key_do_provedor(con: sqlite3.Connection, provedor: str) -> str:
    chave = CHAVES_API.get((provedor or "").strip().lower())
    if not chave:
        return ""
    return ler_config(con, chave)


def config_para_tela(con: sqlite3.Connection) -> dict[str, Any]:
    out: dict[str, Any] = {
        "provedor_padrao": ler_config(con, CHAVE_PADRAO) or "grok",
        "provedores": list(PROVEDORES),
    }
    for prov, chave in CHAVES_API.items():
        val = ler_config(con, chave)
        out[f"tem_{prov}"] = bool(val)
        out[f"{prov}_mascarado"] = mascarar_segredo(val)
    return out


def gravar_tela_config(con: sqlite3.Connection, form: dict) -> None:
    """Grava o que a tela mandou. Campo de chave vazio = nao altera."""
    padrao = (form.get("provedor_padrao") or "").strip().lower()
    if padrao in PROVEDORES:
        gravar_config(con, CHAVE_PADRAO, padrao)
    for prov, chave in CHAVES_API.items():
        novo = (form.get(chave) or form.get(f"api_key_{prov}") or "").strip()
        if novo:
            gravar_config(con, chave, novo)


def listar_robos(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(con.execute(
        "SELECT * FROM robo ORDER BY ativo DESC, nome COLLATE NOCASE"
    ))


def obter_robo(con: sqlite3.Connection, robo_id: int) -> sqlite3.Row | None:
    return con.execute(
        "SELECT * FROM robo WHERE id = ?", (robo_id,)
    ).fetchone()


def exemplos_do_robo(con: sqlite3.Connection, robo_id: int) -> list[sqlite3.Row]:
    return list(con.execute(
        "SELECT * FROM robo_exemplo WHERE robo_id = ? "
        "ORDER BY peso DESC, id",
        (robo_id,),
    ))


def criar_robo(
    con: sqlite3.Connection,
    *,
    nome: str,
    ato: str,
    provedor: str,
    prompt: str,
    ativo: int,
    agora: str,
) -> int:
    cur = con.execute(
        "INSERT INTO robo(nome, ato, provedor, prompt, ativo, "
        "criado_em, atualizado_em) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (nome, ato, provedor, prompt, 1 if ativo else 0, agora, agora),
    )
    return int(cur.lastrowid)


def atualizar_robo(
    con: sqlite3.Connection,
    robo_id: int,
    *,
    nome: str,
    ato: str,
    provedor: str,
    prompt: str,
    ativo: int,
    agora: str,
) -> None:
    con.execute(
        "UPDATE robo SET nome=?, ato=?, provedor=?, prompt=?, ativo=?, "
        "atualizado_em=? WHERE id=?",
        (nome, ato, provedor, prompt, 1 if ativo else 0, agora, robo_id),
    )


def adicionar_exemplo(
    con: sqlite3.Connection,
    robo_id: int,
    entrada: str,
    saida_esperada: str,
    peso: int = 1,
) -> int:
    cur = con.execute(
        "INSERT INTO robo_exemplo(robo_id, entrada, saida_esperada, peso) "
        "VALUES (?, ?, ?, ?)",
        (robo_id, entrada, saida_esperada, int(peso) if peso else 1),
    )
    return int(cur.lastrowid)


def apagar_exemplo(con: sqlite3.Connection, robo_id: int, exemplo_id: int) -> None:
    con.execute(
        "DELETE FROM robo_exemplo WHERE id = ? AND robo_id = ?",
        (exemplo_id, robo_id),
    )


def registrar_teste(
    con: sqlite3.Connection,
    *,
    robo_id: int,
    usuario: str,
    pedido: str,
    rascunho: str,
    modo: str,
    agora: str,
) -> int:
    cur = con.execute(
        "INSERT INTO robo_teste_log(robo_id, usuario, pedido, rascunho, "
        "modo, criado_em) VALUES (?, ?, ?, ?, ?, ?)",
        (robo_id, usuario, pedido, rascunho, modo, agora),
    )
    return int(cur.lastrowid)
