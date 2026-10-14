"""
A LISTA DE ATENÇÃO PARA FRAUDES — o esquema.

POR QUE ISTO EXISTE
    O oficial, em 26/08/2026: *"recebemos pelo malote continuamente
    comunicações de fraudes. Quero incluir um módulo no sistema de controle, em
    que colocamos nomes e/ou documentos de pessoas envolvidas em fraudes, seja
    vítima ou fraudador ou nome que conste em documento fraudado, e o sistema
    alerta quando um ato for requerido ou cadastrado com um nome que consta na
    lista de atenção para fraudes."*

    As comunicações chegam **continuamente** e em papel. Hoje elas viram uma
    pasta, e a pasta só serve para quem lembra de abrir. O que protege a casa é
    o nome ser reconhecido **na hora em que alguém o digita no balcão**.

AS TRÊS REGRAS QUE O ESQUEMA CARREGA

    **ALERTA NÃO É TRAVA, e por isso não há campo de bloqueio.** Homônimo é a
    regra e não a exceção — há muitos José da Silva. Travar o ato pararia o
    balcão para gente inocente, e a decisão de recusar um ato é do oficial, não
    de uma lista.

    **A VÍTIMA É QUEM SE PROTEGE, e não quem se barra.** Ela está na lista
    porque o nome dela foi usado; barrá-la seria fazer com o inocente o que o
    fraudador fez. Por isso o papel é campo obrigatório: sem ele o alerta não
    sabe o que dizer.

    **ALERTA SEM PROCEDÊNCIA NÃO SE AVALIA.** "Fulano está na lista" não ajuda
    ninguém. "Fulano consta na comunicação tal, do dia tal, do órgão tal, como
    vítima" é o que permite a quem está no balcão decidir. Por isso `origem` é
    NOT NULL.

A BUSCA É PELA FORMA NORMALIZADA, e o motivo já custou caro nesta casa:
`UPPER()` do SQLite é ASCII e deixa `josé` como `JOSé`. A função é a mesma que
`pt_devedores.nome_norm` e `nt_pessoas.nome_norm` usam — três formas de
normalizar nome fariam três buscas diferentes acharem coisas diferentes.
"""
from __future__ import annotations

import sqlite3
from typing import Any

SCHEMA = """
-- ------------------------------------------------------- a lista de atenção
--
-- Uma linha por NOME ou DOCUMENTO comunicado. Uma comunicação pode gerar
-- várias linhas — a vítima, o envolvido e o nome que constava no documento
-- fraudado são três linhas, com papéis diferentes e a mesma origem.
CREATE TABLE IF NOT EXISTS fr_alertas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- O QUE SE PROCURA. Um dos dois basta, e os dois juntos são melhores:
    -- documento não tem homônimo, nome tem.
    nome TEXT,
    nome_norm TEXT,                         -- sem acento e sem caixa
    documento TEXT,                         -- só dígitos
    documento_tipo TEXT,                    -- CPF | CNPJ

    -- O PAPEL MUDA O QUE O ALERTA DIZ, e é por isso que é obrigatório:
    -- VITIMA    — o nome dela foi usado; é quem se protege
    -- ENVOLVIDO — consta como envolvida na fraude
    -- DOCUMENTO — nome que consta em documento fraudado
    papel TEXT NOT NULL,

    -- DE ONDE VEIO. Alerta sem procedência não se avalia.
    origem TEXT NOT NULL,                   -- a comunicação: ofício, e-mail, malote
    origem_data TEXT,                       -- a data dela
    origem_orgao TEXT,                      -- quem comunicou
    observacao TEXT,                        -- o que a comunicação diz, em resumo

    situacao TEXT NOT NULL DEFAULT 'ATIVO', -- ATIVO | INATIVO
    -- INATIVAR EXIGE MOTIVO. Comunicação de fraude é documento: não se apaga,
    -- e tirar da lista é decisão que alguém assina.
    inativado_motivo TEXT,
    inativado_em TEXT,
    inativado_por TEXT,

    criado_em TEXT NOT NULL,
    criado_por TEXT
);

CREATE INDEX IF NOT EXISTS ix_fr_alertas_nome ON fr_alertas(nome_norm);
CREATE INDEX IF NOT EXISTS ix_fr_alertas_doc ON fr_alertas(documento);
CREATE INDEX IF NOT EXISTS ix_fr_alertas_situacao ON fr_alertas(situacao);

-- ---------------------------------------------------- o rastro da conferência
--
-- O QUE PROTEGE A CASA NÃO É O ALERTA: É O RASTRO DE QUE ELE FOI VISTO.
-- Se um ato fraudado passar apesar do alerta, a pergunta que vem é "o sistema
-- avisou?". Sem esta tabela a resposta é uma opinião.
--
-- Grava-se quando o operador RECONHECE o alerta — nunca ao mostrá-lo. Tela de
-- leitura que grava é tela que fica presa no `busy_timeout` enquanto outro
-- balcão lavra.
CREATE TABLE IF NOT EXISTS fr_conferencias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alerta_id INTEGER REFERENCES fr_alertas(id),

    -- ONDE o alerta apareceu, e sobre o quê. Texto e não chave estrangeira:
    -- a conferência acontece nas seis atribuições, e amarrar a uma tabela só
    -- excluiria as outras cinco.
    onde TEXT,                              -- 'protesto/titulo', 'rcpn/assento'…
    referencia TEXT,                        -- o número do ato, do protocolo…

    nome_conferido TEXT,
    documento_conferido TEXT,

    -- PROSSEGUIU | RECUSOU | ANOTOU
    decisao TEXT NOT NULL,
    observacao TEXT,

    conferido_em TEXT NOT NULL,
    conferido_por TEXT
);

CREATE INDEX IF NOT EXISTS ix_fr_conferencias_alerta
    ON fr_conferencias(alerta_id);
CREATE INDEX IF NOT EXISTS ix_fr_conferencias_dia
    ON fr_conferencias(conferido_em);
"""

# Colunas acrescentadas depois. Aditivo, no padrão do sistema.
MIGRACOES: tuple[tuple[str, str, str], ...] = ()

# ÍNDICE SOBRE COLUNA DE MIGRAÇÃO VAI AQUI, e não no `SCHEMA` — num banco que
# já existe a coluna só aparece no `ALTER TABLE`, e o `CREATE INDEX` estoura ao
# abrir. Eu errei isso duas vezes em 25/08/2026.
INDICES_DEPOIS_DA_MIGRACAO: tuple[str, ...] = ()


def so_digitos(valor: Any) -> str | None:
    """`047.855.123-88` -> `04785512388`. Documento se guarda sem pontuação.

    Buscar com ponto e traço acharia só quem digitou igual — e cada balcão
    digita de um jeito.
    """
    d = "".join(c for c in str(valor or "") if c.isdigit())
    return d or None


def tipo_do_documento(valor: Any) -> str | None:
    """CPF, CNPJ, ou None quando o tamanho não é nem um nem outro.

    NÃO INVENTA: documento de 9 dígitos não vira CPF com zeros à esquerda —
    fica sem tipo, e o alerta diz que o tipo não se sabe.
    """
    d = so_digitos(valor)
    if not d:
        return None
    return {11: "CPF", 14: "CNPJ"}.get(len(d))


def init_fr_schema(con: sqlite3.Connection) -> None:
    """Cria as tabelas da lista de atenção. Idempotente."""
    con.executescript(SCHEMA)
    for tabela, coluna, tipo in MIGRACOES:
        existentes = {linha[1] for linha in con.execute(
            f"PRAGMA table_info({tabela})")}
        if coluna not in existentes:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
    for comando in INDICES_DEPOIS_DA_MIGRACAO:
        con.execute(comando)
