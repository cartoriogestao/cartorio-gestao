"""A fila do WhatsApp mora DENTRO do Cartorio Gestao.

Decisao do oficial em 02/09/2026: o balcao do WhatsApp nao e Chatwoot,
nem n8n, nem Evolution, nem WhatsApp Web. E o mesmo login, o mesmo Flask
e o mesmo SQLite. BSP (360dialog/Twilio) fica de fora desta fatia.

TABELA NOVA VAI NO SCHEMA, nao em MIGRACAO. MIGRACOES so ALTER TABLE ADD
COLUMN. Indice de coluna nova iria em INDICES_DEPOIS_DA_MIGRACAO.

Nenhum segredo da Meta entra no codigo: verify_token, app_secret,
phone_number_id, access_token, caixa_url e caixa_segredo comecam vazios.

A serventia NAO expoe a porta 8765. Nao ha tunel no SERVIDOR do Cartorio
Gestao. A Meta entrega o inbound numa caixa-postal na VPS Hostinger
(Apache em https://equipetextual.com.br; o nome srv750938.hstgr.cloud
NAO tem TLS). Worker em 127.0.0.1 na VPS; CG puxa. Sem tunel no Windows.
"""
from __future__ import annotations

import sqlite3

ABERTA = "aberta"
AGUARDANDO = "aguardando"
RESOLVIDA = "resolvida"
STATUS = (ABERTA, AGUARDANDO, RESOLVIDA)

ETIQUETAS = (
    "horario", "endereco", "documentos", "certidao",
    "firma", "protesto", "outros",
)

CHAVE_VERIFY = "verify_token"
CHAVE_APP_SECRET = "app_secret"
CHAVE_PHONE = "phone_number_id"
CHAVE_TOKEN = "access_token"
CHAVE_CAIXA_URL = "caixa_url"
CHAVE_CAIXA_SEGREDO = "caixa_segredo"

# URL publica documentada da caixa-postal (TLS do site, nao hstgr.cloud).
# Path /pendentes e o GET que o CG puxa. Alternativa: prefixo /wa-caixa.
CAIXA_URL_DOCUMENTADA = "https://equipetextual.com.br/pendentes"
WEBHOOK_PUBLICO_DOCUMENTADO = "https://equipetextual.com.br/whatsapp/webhook"

# Token de desenvolvimento. Nao e segredo de producao: so libera o GET de
# verify e o POST de teste (X-Wa-Test) enquanto a casa ainda nao gravou o
# verify_token da Meta. Documentado em DOCUMENTACAO/PROJETO_BALCAO_WHATSAPP.md.
VERIFY_TOKEN_DEV = "cartorio-teste"

CHAVES_CONFIG = (
    CHAVE_VERIFY, CHAVE_APP_SECRET, CHAVE_PHONE, CHAVE_TOKEN,
    CHAVE_CAIXA_URL, CHAVE_CAIXA_SEGREDO,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS wa_conversa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wa_id TEXT NOT NULL,
    nome TEXT,
    etiqueta TEXT,
    status TEXT NOT NULL DEFAULT 'aberta',
    rascunho TEXT,
    auto_ok INTEGER NOT NULL DEFAULT 0,
    atualizado_em TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_wa_conversa_wa_id
    ON wa_conversa(wa_id);
CREATE INDEX IF NOT EXISTS idx_wa_conversa_atualizado
    ON wa_conversa(atualizado_em);

CREATE TABLE IF NOT EXISTS wa_mensagem (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversa_id INTEGER NOT NULL REFERENCES wa_conversa(id),
    direcao TEXT NOT NULL,
    texto TEXT,
    bruto_json TEXT,
    criado_em TEXT,
    meta_id TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_wa_mensagem_meta_id
    ON wa_mensagem(meta_id) WHERE meta_id IS NOT NULL AND meta_id != '';
CREATE INDEX IF NOT EXISTS idx_wa_mensagem_conversa
    ON wa_mensagem(conversa_id, criado_em);

CREATE TABLE IF NOT EXISTS wa_config (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL DEFAULT ''
);
"""

MIGRACOES: tuple[tuple[str, str, str], ...] = ()
INDICES_DEPOIS_DA_MIGRACAO: tuple[str, ...] = ()


def init_wa_schema(con: sqlite3.Connection) -> None:
    """Cria as tabelas da fila do WhatsApp. Idempotente."""
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
            "INSERT OR IGNORE INTO wa_config(chave, valor) VALUES (?, '')",
            (chave,),
        )
