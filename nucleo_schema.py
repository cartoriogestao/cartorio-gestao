"""
O nucleo da escrituracao — as tabelas de livro, lugar, inutilizacao e termo,
para as SEIS atribuicoes.

POR QUE ESTAS TABELAS EXISTEM
    `livro_nucleo` diz como o livro e feito: quantas folhas, se tem verso, se
    cada registro comeca em folha nova. Nao grava nada — e geometria.

    Aqui e onde a geometria encosta no papel: qual livro esta aberto, qual
    folha esta livre, quem ocupa a folha 14v, o que ficou em branco e foi
    inutilizado, e em que numero de ordem a serie esta.

    Sao cinco tabelas e nenhuma delas conhece o ato. O ato mora na tabela da
    atribuicao dele — `nt_atos`, `ri_atos`, e as que virao para Protesto, RCPN,
    RCPJ e RTD. O nucleo guarda o LUGAR e aponta para o ato por (tabela, id).
    Foi de proposito: se o nucleo tivesse de conhecer as seis tabelas de ato,
    cada atribuicao nova mexeria no nucleo, e nucleo que se mexe a cada
    atribuicao nao e nucleo, e um sexto modulo.

A TRAVA QUE IMPORTA MAIS QUE O CODIGO
    `UNIQUE(livro_id, folha, verso, ordem)` em `nu_lugares`.

    Em 18/08/2026 a numeracao de matricula, contada por VOLUME em vez de por
    SERVENTIA, abriu a matricula 4011 depois de a 4013 existir. Nenhuma revisao
    de codigo pegou; o banco pegaria, se a regra estivesse escrita nele. Agora
    esta: dois atos na mesma face da mesma folha do mesmo livro nao entram, nem
    com dois balcoes lavrando ao mesmo tempo, nem com o `busy_timeout`
    estourando no meio.

    Pelo mesmo motivo `ux_nu_lugares_registro` e UNICO por (tabela,
    referencia) onde `inicio=1`: um ato tem um lugar de inicio e nao dois.

SOBRE O LIVRO DIARIO
    Protocolo de Protesto, de RCPJ e de RTD encerram TODO DIA, e nao quando
    enchem (exigencia da inspecao de 12/08/2026). Por isso `nu_livros.dia` e
    `nu_encerramentos_diarios`: o livro diario e o mesmo livro fisico, mas com
    um termo de encerramento por dia de expediente, e a tabela guarda o teor
    desse termo e a faixa de numeros do dia.

FUNDAMENTO
    Lei 8.935/1994, art. 30, I; art. 46.
    Lei 6.015/1973, arts. 3o a 6o; art. 33 (livros do registro civil).
    Lei 9.492/1997, arts. 33 e 34 (livros do protesto).
    Codigo de Normas do Foro Extrajudicial do Maranhao — Provimento TJMA n. 28,
        de 23/04/2026 — Secao "Dos Livros e da sua Escrituracao".
"""
from __future__ import annotations

import sqlite3

SCHEMA = """
-- ------------------------------------------------------------ o livro

CREATE TABLE IF NOT EXISTS nu_livros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    serie TEXT NOT NULL,                    -- codigo de livro_nucleo.SERIES
    atribuicao INTEGER NOT NULL,            -- 1..6, congelado no livro
    numero TEXT NOT NULL,
    complemento TEXT NOT NULL DEFAULT '',   -- '2S', 'A', quando a casa usa
    descricao TEXT,
    folhas INTEGER NOT NULL,
    folha_inicial INTEGER NOT NULL DEFAULT 1,
    folha_atual INTEGER NOT NULL DEFAULT 1,
    dia TEXT,                               -- so em serie diaria: AAAA-MM-DD
    abertura TEXT,
    encerramento TEXT,
    termo_abertura TEXT,
    termo_encerramento TEXT,
    motivo_encerramento TEXT,
    encerrado INTEGER NOT NULL DEFAULT 0,
    ativo INTEGER NOT NULL DEFAULT 1,
    origem TEXT NOT NULL DEFAULT 'MANUAL',  -- MANUAL | ACERVO
    criado_em TEXT NOT NULL,
    criado_por TEXT,
    UNIQUE(serie, numero, complemento)
);

CREATE INDEX IF NOT EXISTS ix_nu_livros_serie
    ON nu_livros(serie, encerrado, ativo);

-- ------------------------------------------------------------ o lugar
--
-- Uma linha por FACE ocupada. O ato que ocupa tres faces tem tres linhas, e a
-- primeira leva inicio=1. Assim a trava de face unica e a de ato unico cabem
-- na mesma tabela sem se atrapalharem.

CREATE TABLE IF NOT EXISTS nu_lugares (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    livro_id INTEGER NOT NULL REFERENCES nu_livros(id),
    serie TEXT NOT NULL,
    folha INTEGER NOT NULL,
    verso INTEGER NOT NULL DEFAULT 0,
    ordem INTEGER NOT NULL DEFAULT 1,       -- posicao dentro da face
    rotulo TEXT NOT NULL,                   -- '14' ou '14v'
    inicio INTEGER NOT NULL DEFAULT 1,
    paginas INTEGER NOT NULL DEFAULT 1,     -- do ato inteiro, na linha inicial
    numero_ordem INTEGER,                   -- numeracao continua da serie
    tabela TEXT NOT NULL,                   -- 'nt_atos', 'ri_atos', ...
    referencia INTEGER NOT NULL,            -- id naquela tabela
    ocupado_em TEXT NOT NULL,
    ocupado_por TEXT,
    UNIQUE(livro_id, folha, verso, ordem)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_nu_lugares_registro
    ON nu_lugares(tabela, referencia) WHERE inicio = 1;

-- Um numero de ordem aparece UMA vez por livro.
--
-- A numeracao continua e servida por um contador em `nu_numeracao`, sob
-- transacao; a numeracao DIARIA — o protocolo do protesto, que reinicia todo
-- dia — sai de um MAX() sobre o livro do dia. O MAX() basta porque a casa
-- grava sob BEGIN IMMEDIATE, um escritor por vez; este indice e a garantia
-- que sobra se algum dia isso mudar.
CREATE UNIQUE INDEX IF NOT EXISTS ux_nu_lugares_ordem
    ON nu_lugares(livro_id, numero_ordem) WHERE inicio = 1;

CREATE INDEX IF NOT EXISTS ix_nu_lugares_livro
    ON nu_lugares(livro_id, folha, verso);

CREATE INDEX IF NOT EXISTS ix_nu_lugares_registro
    ON nu_lugares(tabela, referencia);

-- ------------------------------------------------------------ a inutilizacao
--
-- Folha em branco dentro de livro escriturado e a porta aberta do art. 795,
-- par. 2o. A inspecao cobrou isto de RCPN, Protesto, RCPJ e RTD, e cada face
-- inutilizada tem de ter motivo, data, quem e o teor que sai impresso.

CREATE TABLE IF NOT EXISTS nu_inutilizacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    livro_id INTEGER NOT NULL REFERENCES nu_livros(id),
    serie TEXT NOT NULL,
    folha INTEGER NOT NULL,
    verso INTEGER NOT NULL DEFAULT 0,
    rotulo TEXT NOT NULL,
    motivo TEXT NOT NULL,
    teor TEXT NOT NULL,
    origem TEXT NOT NULL DEFAULT 'MANUAL',  -- MANUAL | SOBRA | ENCERRAMENTO
    inutilizado_em TEXT NOT NULL,
    inutilizado_por TEXT,
    UNIQUE(livro_id, folha, verso)
);

-- ------------------------------------------------------------ a numeracao
--
-- O numero de ordem do ato, continuo por SERIE e por SERVENTIA — nunca por
-- volume. Foi contar por volume que abriu a matricula 4011 depois da 4013.

CREATE TABLE IF NOT EXISTS nu_numeracao (
    serie TEXT PRIMARY KEY,
    proximo INTEGER NOT NULL,
    maior_em_uso INTEGER,
    semeado_de TEXT,                        -- de onde saiu o valor inicial
    fixado_em TEXT,
    fixado_por TEXT,
    observacao TEXT
);

-- ------------------------------------------------------------- implantacao
--
-- O QUE SO O OFICIAL PODE INFORMAR, e que trava o balcao se ninguem informar.
--
-- Esta tabela existe porque o sistema esteve SUSPENSO e vai voltar: quando ele
-- voltar, ha coisas que o acervo nao sabe dizer e que so quem conhece o livro
-- fisico responde — o proximo numero de um livro que o E-Oficio nunca guardou,
-- por exemplo. Deixar isso na cabeca de alguem e o mesmo que nao ter.
--
-- CADA PENDENCIA E DECLARADA POR QUEM A DESCOBRE, e nao adivinhada aqui: a
-- carga do acervo declara as series que nao soube semear, com o motivo medido.
-- Por isso um sistema NOVO, sem carga nenhuma, nao tem pendencia alguma — e
-- comecar do numero 1 nele esta certo. Aviso que soa em sistema vazio e aviso
-- que ninguem ouve.
CREATE TABLE IF NOT EXISTS nu_implantacao (
    chave TEXT PRIMARY KEY,                 -- `numeracao:RC_D`, `decisao:...`
    tipo TEXT NOT NULL,                     -- NUMERO | DECISAO
    atribuicao INTEGER,                     -- 1 a 6, quando e de uma so
    titulo TEXT NOT NULL,
    motivo TEXT NOT NULL,                   -- por que so o oficial sabe
    consequencia TEXT,                      -- o que acontece se ninguem informar
    serie TEXT,                             -- quando e de um livro do nucleo

    situacao TEXT NOT NULL DEFAULT 'ABERTA', -- ABERTA | RESOLVIDA | DISPENSADA
    valor TEXT,                             -- o que o oficial informou
    observacao TEXT,                        -- o que ele escreveu ao resolver

    declarada_em TEXT NOT NULL,
    declarada_por TEXT,
    resolvida_em TEXT,
    resolvida_por TEXT
);

CREATE INDEX IF NOT EXISTS ix_nu_implantacao_situacao
    ON nu_implantacao(situacao);

-- ------------------------------------------------------- encerramento diario

CREATE TABLE IF NOT EXISTS nu_encerramentos_diarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    serie TEXT NOT NULL,
    dia TEXT NOT NULL,                      -- AAAA-MM-DD
    livro_id INTEGER REFERENCES nu_livros(id),
    primeiro INTEGER,
    ultimo INTEGER,
    quantidade INTEGER NOT NULL DEFAULT 0,
    teor TEXT NOT NULL,
    encerrado_em TEXT NOT NULL,
    encerrado_por TEXT,
    UNIQUE(serie, dia)
);
"""

# Colunas acrescentadas depois. Aditivo, no padrao do sistema.
MIGRACOES: tuple[tuple[str, str, str], ...] = ()


def init_nucleo_schema(con: sqlite3.Connection) -> None:
    """Cria as tabelas do nucleo. Idempotente."""
    con.executescript(SCHEMA)
    for tabela, coluna, tipo in MIGRACOES:
        existentes = {linha[1] for linha in con.execute(f"PRAGMA table_info({tabela})")}
        if coluna not in existentes:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
