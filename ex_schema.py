"""As duas tabelas do que começou e não terminou.

    «Sobre os expedientes, eles seriam de **abastecimento automático**, pegariam
     todos atos que começaram e não terminaram no sistema.» — o oficial

**DUAS TABELAS SÓ, E NENHUMA DELAS GUARDA ATO.**
    A lista dos inacabados é **medida na hora**, das tabelas onde os atos já
    moram. Copiar cada ato para cá seriam dois lugares guardando o mesmo fato — e
    a cópia diverge no primeiro conserto: o ato seria concluído e a linha daqui
    continuaria aberta, que é **exatamente o relato #24 do oficial** («a tarefa
    concluída e o expediente aberto»).

    O que se guarda aqui é só o que não existe em lugar nenhum: como cada fonte
    está ajustada, e a anotação do oficial sobre um item.

POR QUE SCHEMA PRÓPRIO, E NÃO DENTRO DE OUTRO
    Ele atravessa as seis atribuições — Notas, RI, RCPN, o balcão, os
    expedientes —, e é a mesma razão pela qual `implantacao.py` mora no núcleo.
    Pendurá-lo em `caixa_schema` diria que ele é do financeiro, e quem for
    procurar amanhã não olharia ali.
"""
from __future__ import annotations

import sqlite3

SCHEMA = """
-- Como cada fonte esta ajustada. O CODIGO E O PISO; ESTA TABELA E O AJUSTE —
-- sem linha aqui, a fonte funciona com o padrao declarado em `inacabados.py`, e
-- «voltar ao padrao» e apagar a linha. Instalacao nova nasce funcionando, que e
-- a mesma regra de `mo_modelos`.
--
-- **A FONTE EM SI NAO MORA AQUI**, e isso e deliberado: saber onde o ato mora e
-- o que o termina nao se digita numa tela. A tela liga, desliga e ajusta os
-- dias do que existe; ela nao inventa fonte.
CREATE TABLE IF NOT EXISTS ex_fontes (
    chave TEXT PRIMARY KEY,             -- ver inacabados.FONTES
    ligada INTEGER NOT NULL DEFAULT 1,  -- a fonte entra na lista
    dias INTEGER,                       -- quantos dias ate ser chamada de parada
    atualizado_em TEXT,
    atualizado_por TEXT
);

-- A anotacao do oficial sobre um item: quem esta cuidando, ate quando, o que
-- falta. **E O UNICO DADO NOVO DESTE MODULO** — todo o resto e medido.
--
-- `UNIQUE(tabela, item_id)`: uma anotacao por item. Duas fariam a tela mostrar
-- uma e o operador ter escrito a outra.
--
-- E ela NAO tem chave estrangeira, de proposito: aponta para nove tabelas
-- diferentes, e uma FK so pode apontar para uma. Quem garante que a tabela e
-- valida e `inacabados.anotar`, que recusa nome que nao esteja em `FONTES`.
CREATE TABLE IF NOT EXISTS ex_anotacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tabela TEXT NOT NULL,               -- a tabela onde o ato mora
    item_id INTEGER NOT NULL,
    texto TEXT NOT NULL,                -- o que falta
    responsavel TEXT,                   -- quem esta cuidando
    ate TEXT,                           -- ate quando
    criado_em TEXT NOT NULL,
    criado_por TEXT,
    UNIQUE(tabela, item_id)
);

CREATE INDEX IF NOT EXISTS ix_ex_anotacoes_item
    ON ex_anotacoes(tabela, item_id);
"""

# Nenhuma ainda — as duas tabelas nasceram juntas.
MIGRACOES: tuple[tuple[str, str, str], ...] = ()

INDICES_DEPOIS_DA_MIGRACAO: tuple[str, ...] = ()


def init_ex_schema(con: sqlite3.Connection) -> None:
    """Cria as duas tabelas. Idempotente.

    PODE SER CHAMADA A QUALQUER MOMENTO: nenhuma das duas aponta para tabela
    nenhuma — `ex_anotacoes` guarda o nome da tabela como TEXTO justamente
    porque serve nove delas.
    """
    con.executescript(SCHEMA)
    for tabela, coluna, tipo in MIGRACOES:
        existentes = {linha[1]
                      for linha in con.execute(f"PRAGMA table_info({tabela})")}
        if coluna not in existentes:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
    for comando in INDICES_DEPOIS_DA_MIGRACAO:
        con.execute(comando)
