"""As tabelas de que a remessa do IBGE precisa, e que este sistema não tinha.

POR QUE ESTE MÓDULO EXISTE
    `ibge_remessa.py` sabe o LAYOUT do arquivo — as 25 posições do nascimento,
    as 21 do casamento, as 20 do óbito. Mas o layout pede coisas que o sistema
    não sabia responder:

        UF-PESQUISA, MUN-PESQUISA, DIST-PESQUISA, COD_CARTORIO
            Quem é esta serventia, na fala do IBGE.

        COD-UF-NASC, COD-MUNIC-NASC, COD-UF-RES-MAE, COD-MUNIC-RES-MAE,
        COD-UF-NASC-PAI, COD-UF-NASC-MAE
            Códigos numéricos de município e de UF. O sistema guarda o NOME da
            cidade em texto («Cidade Exemplo»); o IBGE quer `21` e `98765`.

    Sem uma tabela de-para, cada município teria de ser digitado em código pelo
    escrevente — e código digitado à mão numa remessa estatística é erro que
    ninguém confere, porque ninguém lê o arquivo depois.

O DE-PARA VEM DO ACERVO, E FOI MEDIDO (28/08/2026)
    O E-Ofício tem duas tabelas de município, e elas não são iguais:

        `tbMunicipio`  5.638 linhas, **5.570 códigos distintos** — que é
                       exatamente o número de municípios do Brasil. Traz a
                       sigla da UF e o código IBGE da UF.
        `MUNICIPIOS`   5.444 linhas. Faltam 126.

    Fica a primeira. As 68 linhas sem código são o que sobra de municípios
    renomeados ou desmembrados, e entram sem código: elas ainda casam pelo
    nome, e é melhor achar o nome e não ter o código do que não achar nada.

    **As duas guardam o texto em UTF-8**, e isso se conferiu nos bytes
    (`c3a1` = «á»), e não no que o console mostra — o console desta máquina
    mangia acento e por duas vezes me fez ler o contrário do que estava lá.

O CÓDIGO DO IBGE TEM SETE DÍGITOS, E O ARQUIVO QUER OS CINCO ÚLTIMOS
    `2198765` é Cidade Exemplo: `21` é o Maranhão e `98765` é o município dentro
    dele. O arquivo pede os dois em campos separados — `COD-UF-NASC` com 2 e
    `COD-MUNIC-NASC` com 5 —, e é por isso que se guardam os três: o código
    inteiro, o da UF e o do município. Recortar na hora de montar a linha
    poria a mesma conta em cinco lugares.

    Conferido contra `tbIBGE_Propriedades`, que é o que esta serventia mandava
    no cabeçalho: UF `21`, município `98765`, distrito `05`, cartório `01`.
"""
from __future__ import annotations

import sqlite3
import unicodedata

SCHEMA = """
-- O DE-PARA DE MUNICÍPIO E UF, para a remessa do IBGE.
--
--   Não é cadastro que alguém mantém: é tabela oficial, trazida do acervo e
--   substituída inteira quando mudar. Por isso `codigo_ibge` é a chave, e não
--   um `id` nosso: quem manda no número é o IBGE.
-- ------------------------------------------------ o que ja foi ao IBGE
--
-- **ESTE ERA UM BURACO DECLARADO NO PAINEL DAS COMUNICACOES**: o sistema montava
-- o mapa trimestral e nao guardava o que saiu — de modo que a linha do IBGE
-- mostrava o PRAZO e dizia, com todas as letras, que o envio nao era
-- acompanhado. Numero que responde a pergunta errada e pior que numero nenhum;
-- agora a pergunta certa tem resposta.
--
-- O TEOR CONGELA, com sha256, como o das comunicacoes do art. 226 e o do
-- edital: numa correicao e ele que se mostra, e o art. 224 pune com **multa de
-- 1 a 5 salarios minimos, «sem prejuizo da acao penal»**.
CREATE TABLE IF NOT EXISTS ib_entregas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ano INTEGER NOT NULL,
    trimestre INTEGER NOT NULL,         -- 1 a 4, o trimestre REPORTADO
    teor TEXT,                          -- o arquivo inteiro, e nao so o nome
    hash_teor TEXT,
    quantos INTEGER,                    -- quantas linhas foram
    enviada_em TEXT,
    canal TEXT,
    protocolo TEXT,
    criado_em TEXT NOT NULL,
    criado_por TEXT,
    -- UM TRIMESTRE, UMA ENTREGA. Duas linhas para o mesmo trimestre fariam a
    -- lista dizer que ele foi entregue e a correicao achar dois arquivos
    -- diferentes.
    UNIQUE(ano, trimestre)
);

CREATE TABLE IF NOT EXISTS ib_municipios (
    codigo_ibge   INTEGER PRIMARY KEY,     -- 2198765
    codigo_uf     INTEGER NOT NULL,        -- 21
    codigo_mun    TEXT NOT NULL,           -- '98765', com os zeros à esquerda
    uf            TEXT NOT NULL,           -- 'MA'
    nome          TEXT NOT NULL,
    nome_norm     TEXT NOT NULL,           -- sem acento e em minúscula
    origem        TEXT NOT NULL DEFAULT 'ACERVO',
    criado_em     TEXT
);

-- A BUSCA É PELO NOME NORMALIZADO, e não por `UPPER(nome)`.
--
--   `UPPER` e `LOWER` do SQLite são ASCII: `LOWER('SÃO')` devolve `SãO`, e
--   quem digitasse «sao luis» não acharia «São Luís». É a mesma lição que
--   custou dois defeitos no módulo de fraudes — a normalização mora em
--   Python, numa função só.
CREATE INDEX IF NOT EXISTS ix_ib_mun_nome ON ib_municipios(nome_norm);
CREATE INDEX IF NOT EXISTS ix_ib_mun_uf ON ib_municipios(uf, nome_norm);
"""

# O QUE ESTA SERVENTIA É, NA FALA DO IBGE — as quatro do cabeçalho.
#
#   Moram em `settings` e não numa tabela de uma linha só: são configuração da
#   casa, como o CNS e a data da tabela de custas, e é lá que o resto do
#   sistema procura configuração.
CONFIGURACOES_DO_IBGE: tuple[tuple[str, str], ...] = (
    ("ibge_uf", "Código da UF no IBGE (2 dígitos)"),
    ("ibge_municipio", "Código do município no IBGE (5 dígitos)"),
    ("ibge_distrito", "Código do distrito (2 dígitos)"),
    ("ibge_cartorio", "Código desta serventia junto ao IBGE (2 dígitos)"),
)


def normalizar_nome(nome) -> str:
    """A forma de comparar nome de município. Só calcula.

    Uma função só, e a mesma dos dois lados — quem grava e quem procura. Onde a
    igualdade importa, ela se constrói: não se supõe que duas normalizações
    parecidas dão no mesmo.
    """
    texto = unicodedata.normalize("NFKD", str(nome or "").strip())
    sem_acento = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(sem_acento.lower().split())


def init_ibge_schema(con: sqlite3.Connection) -> None:
    """Cria as tabelas do de-para do IBGE."""
    con.executescript(SCHEMA)
