"""Onde mora o papel que espera assinatura, e o que voltou assinado.

**UMA FILA PARA A CASA INTEIRA, e nao uma por atribuicao** — decisao do
oficial em 01/09/2026: *«ela vai ser util em muitos modulos»*. Hoje o sistema
emite nove papeis (as certidoes do RI, do RCPN, do RCPJ/RTD e do Livro 3, os
termos de livro, os recibos, o traslado, o comprovante de prenotacao e os
editais), e o instrumento de protesto e o decimo.

**O QUE MUDA DE UM PARA O OUTRO E O DOCUMENTO, E NAO A ASSINATURA.** Escrever
esta tabela dez vezes daria dez versoes divergentes do pedaco que responde
«este papel esta assinado?» — a licao do nucleo, aplicada mais uma vez.

A LIGACAO COM O ATO E POR `(entidade, entidade_id)`, E NAO POR CHAVE
ESTRANGEIRA
    Os dez papeis moram em dez tabelas diferentes, e nao ha uma so para
    apontar. E a mesma forma que `attachments` e `sd_selos` ja usam nesta
    casa, e pelo mesmo motivo.

O DOCUMENTO SE GUARDA PELO SHA256, E O ARQUIVO EM DISCO
    O papel gerado e o assinado sao dois arquivos, e nenhum dos dois entra no
    banco: o banco viaja no backup, e ja saiu da serventia. O que fica aqui e
    **o sha256 do que a casa emitiu** — que e do que a conferencia precisa — e
    o caminho de cada arquivo.
"""
from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS as_documentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- DE QUE ATO E ESTE PAPEL. `entidade` e o nome da tabela do ato
    -- (`pt_atos`, `rc_certidoes`, ...) e `entidade_id` a linha dela.
    entidade TEXT NOT NULL,
    entidade_id INTEGER NOT NULL,
    titulo TEXT NOT NULL,                   -- o que o balcao le na fila

    -- O QUE A CASA EMITIU. O sha256 e o que a conferencia compara; sem ele
    -- nao ha como saber se o assinado que voltou e este papel.
    sha256_documento TEXT NOT NULL,
    caminho_documento TEXT,                 -- o arquivo, em disco
    tamanho_documento INTEGER NOT NULL DEFAULT 0,

    -- O QUE VOLTOU ASSINADO. Vazio enquanto espera.
    caminho_assinado TEXT,
    sha256_assinado TEXT,
    assinado_em TEXT,                       -- quando o arquivo assinado entrou
    assinado_por_nome TEXT,                 -- lido do certificado, nao digitado
    assinado_por_cpf TEXT,
    recebido_por TEXT,                      -- quem subiu o arquivo no sistema

    criado_em TEXT NOT NULL,
    criado_por TEXT
);

CREATE INDEX IF NOT EXISTS idx_as_documentos_ato
    ON as_documentos(entidade, entidade_id);
CREATE INDEX IF NOT EXISTS idx_as_documentos_espera
    ON as_documentos(assinado_em);

-- UM PAPEL POR ATO. Dois registros do mesmo ato fariam a fila mostrar o
-- mesmo papel duas vezes, e o balcao assinaria duas — com o segundo
-- sobrescrevendo o primeiro sem ninguem ver qual vale.
CREATE UNIQUE INDEX IF NOT EXISTS ux_as_documentos_ato
    ON as_documentos(entidade, entidade_id);
"""

# Colunas acrescentadas depois. Aditivo, no padrao do sistema.
MIGRACOES: tuple[tuple[str, str, str], ...] = ()


def init_as_schema(con: sqlite3.Connection) -> None:
    """Cria a tabela da fila de assinatura. Idempotente."""
    con.executescript(SCHEMA)
    for tabela, coluna, tipo in MIGRACOES:
        existentes = {linha[1] for linha in con.execute(
            f"PRAGMA table_info({tabela})")}
        if coluna not in existentes:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
