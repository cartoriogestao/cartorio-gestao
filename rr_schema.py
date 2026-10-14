"""As tabelas da retificação, restauração e suprimento do Registro Civil.

POR QUE É PROCESSO, E NÃO UM CAMPO NO ASSENTO
    Tem entrada, prazo de **10 dias úteis**, uma **conferência obrigatória** sem
    a qual não se decide (a consulta à CRC, art. 348, § 2º) e uma **decisão
    fundamentada**. É a forma do usucapião e da retificação de área, pelo mesmo
    motivo — e é a terceira vez que ela aparece neste projeto.

O QUE ESTAS TABELAS TÊM QUE AS OUTRAS DUAS NÃO TÊM
    **A consulta à CRC como peça obrigatória, com resultado gravado.** Ela é
    *condição de validade da decisão*: decidir sem consultar é decidir sem o que
    a norma exige. Por isso ela não é um campo de texto solto — é uma linha com
    data, com o que se procurou e com o que se achou, e `decidir()` recusa sem
    ela.

    **E a marca «erro imputável à serventia», que tem dinheiro dentro.** O art.
    353 a transforma em gratuidade, comunicação ao FERC **e** ao FERJ, e cobrança
    contra **o delegatário titular da época** — uma pessoa nomeada. Por isso ela
    exige fundamento escrito, como a decisão do usucapião.
"""
from __future__ import annotations

import sqlite3

SCHEMA = """
-- ------------------------------------------------------------- o processo
--
-- `instituto` separa os TRES, e eles nao sao a mesma coisa: retificacao corrige
-- o que esta errado, restauracao reconstitui o danificado ou extraviado,
-- suprimento lanca o que falta. Junta-los num «corrigir assento» faria o
-- escrevente escolher o caminho errado, e cada um tem requisito proprio.
CREATE TABLE IF NOT EXISTS rr_processos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero TEXT NOT NULL,                   -- o numero dos autos nesta casa
    ano INTEGER,
    instituto TEXT NOT NULL,                -- ver rr_tjma.INSTITUTOS
    forma TEXT NOT NULL,                    -- ver rr_tjma.FORMAS_DO_PEDIDO
    fase TEXT NOT NULL DEFAULT 'PROTOCOLO',
    situacao TEXT NOT NULL DEFAULT 'EM_ANDAMENTO',

    -- O ASSENTO E OPCIONAL, e essa e a diferenca em relacao a retificacao de
    -- area do RI (onde a matricula e NOT NULL). **No SUPRIMENTO o assento nao
    -- existe** — e o que se supre. Exigi-lo aqui travaria justamente o
    -- instituto para o qual ele nao existe.
    assento_id INTEGER REFERENCES rc_assentos(id),
    assento_descricao TEXT,                 -- quando ele nao esta no sistema

    requerente_nome TEXT NOT NULL,
    requerente_documento TEXT,
    -- QUEM ASSINOU: o art. 352 permite o interessado, o representante legal ou
    -- **procurador** — e recusar a procuracao no balcao seria negar o que a
    -- norma permite.
    assinado_por TEXT,
    o_que_se_pede TEXT NOT NULL,

    -- O TERMO DO PEDIDO VERBAL. O § 1o, III manda reduzi-lo a termo
    -- **imediatamente**, colhendo a assinatura do declarante — e sem o termo
    -- assinado o pedido nao existe no papel.
    termo_verbal TEXT,
    termo_verbal_em TEXT,

    -- «DEVIDAMENTE INSTRUIDO» E A CONDICAO DO PRAZO (§ 3o): o relogio conta do
    -- protocolo COMPLETO, e nao do dia em que a pessoa apareceu. Um sistema que
    -- contasse da chegada poria o oficial em atraso por falta de documento que
    -- o requerente ainda nao trouxe.
    protocolado_em TEXT,                    -- quando o interessado chegou
    instruido_em TEXT,                      -- quando ficou completo
    prazo_ate TEXT,                         -- 10 dias uteis de `instruido_em`

    -- A DECISAO, e ela e FUNDAMENTADA por exigencia do § 3o.
    decidido_em TEXT,
    decisao TEXT,                           -- DEFERIDO | INDEFERIDO | JUDICIAL
    fundamento TEXT,
    decidido_por TEXT,

    -- O ART. 353 TEM DINHEIRO DENTRO. Ver `rr_erro_da_serventia` abaixo.
    erro_da_serventia INTEGER NOT NULL DEFAULT 0,
    erro_fundamento TEXT,

    -- O ATO QUE SAIU. O § 4o manda lancar **no livro corrente**, com remissoes
    -- reciprocas ao assento original — e nao no livro antigo, que esta
    -- encerrado.
    ato_id INTEGER REFERENCES rc_atos(id),
    assento_novo_id INTEGER REFERENCES rc_assentos(id),

    criado_em TEXT NOT NULL,
    criado_por TEXT,
    atualizado_em TEXT,
    UNIQUE(numero, ano)
);

-- ------------------------------------------------- a consulta obrigatoria a CRC
--
-- **E CONDICAO DE VALIDADE DA DECISAO** (art. 348, § 2o), e nao zelo. Ate aqui,
-- neste projeto, a CRC era destino de carga e de comunicacao; aqui ela e o que a
-- norma exige **antes** de decidir.
--
-- Por isso ela nao e um campo de texto no processo: e uma linha com data, com o
-- que se procurou e com o que se achou. Um campo solto seria preenchido com
-- «ok» — e «ok» nao responde a pergunta que a correicao faz.
CREATE TABLE IF NOT EXISTS rr_consultas_crc (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    processo_id INTEGER NOT NULL REFERENCES rr_processos(id),
    consultada_em TEXT NOT NULL,
    o_que_se_procurou TEXT NOT NULL,        -- nome, data, filiacao...
    achou_duplicidade INTEGER NOT NULL DEFAULT 0,
    achou_ato_em_outra_serventia INTEGER NOT NULL DEFAULT 0,
    resultado TEXT NOT NULL,                -- o que a CRC devolveu
    protocolo TEXT,
    -- O ART. 365 MANDA COMUNICAR AO JUIZ CORREGEDOR quando ha duplicidade, com
    -- bloqueio cautelar do registro mais recente. A marca fica aqui para a tela
    -- cobrar, e nao para o sistema comunicar sozinho.
    comunicado_ao_corregedor_em TEXT,
    criado_em TEXT NOT NULL,
    criado_por TEXT
);

-- ------------------------------------------------------------------- as pecas
CREATE TABLE IF NOT EXISTS rr_pecas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    processo_id INTEGER NOT NULL REFERENCES rr_processos(id),
    tipo TEXT NOT NULL,
    descricao TEXT,
    teor TEXT,
    arquivo TEXT,
    juntada_em TEXT NOT NULL,
    juntada_por TEXT
);

-- ------------------------------------------------------------ o andamento
CREATE TABLE IF NOT EXISTS rr_andamento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    processo_id INTEGER NOT NULL REFERENCES rr_processos(id),
    quando TEXT NOT NULL,
    o_que TEXT NOT NULL,
    quem TEXT
);

-- --------------------------------------- a comunicacao do art. 353 aos fundos
--
-- **SAO DOIS FUNDOS, E NAO UM**: FERC e FERJ. Comunicar so a um deixaria o
-- ressarcimento pela metade, e a norma nomeia os dois.
CREATE TABLE IF NOT EXISTS rr_comunicacoes_353 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    processo_id INTEGER NOT NULL REFERENCES rr_processos(id),
    fundo TEXT NOT NULL,                    -- FERC | FERJ
    situacao TEXT NOT NULL DEFAULT 'PENDENTE',
    teor TEXT,
    hash_teor TEXT,
    enviada_em TEXT,
    canal TEXT,
    protocolo TEXT,
    criado_em TEXT NOT NULL,
    criado_por TEXT,
    UNIQUE(processo_id, fundo)
);

CREATE INDEX IF NOT EXISTS ix_rr_processos_situacao
    ON rr_processos(situacao, prazo_ate);
CREATE INDEX IF NOT EXISTS ix_rr_consultas_processo
    ON rr_consultas_crc(processo_id);
"""

MIGRACOES: tuple[tuple[str, str, str], ...] = ()

INDICES_DEPOIS_DA_MIGRACAO: tuple[str, ...] = ()


def init_rr_schema(con: sqlite3.Connection) -> None:
    """Cria as tabelas. Idempotente.

    CHAMAR DEPOIS DO `rc_schema`, porque `rr_processos` aponta para
    `rc_assentos` e `rc_atos`.
    """
    con.executescript(SCHEMA)
    for tabela, coluna, tipo in MIGRACOES:
        existentes = {linha[1]
                      for linha in con.execute(f"PRAGMA table_info({tabela})")}
        if coluna not in existentes:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
    for comando in INDICES_DEPOIS_DA_MIGRACAO:
        con.execute(comando)
