"""
RCPJ e RTD — o registro e os atos, num módulo só.

POR QUE UM MODULO SO PARA DUAS ATRIBUICOES
    `LEVANTAMENTO_QUATRO_ATRIBUICOES.md`: RTD e RCPJ compartilham a mesma
    estrutura no E-Oficio — `livroTDPJ`, `tbTipoLivros_TDPJ` e o controlador
    `tbTD_Propriedade` contam os dois. Escrever dois módulos quase iguais
    seria o mesmo erro que o núcleo existe para evitar.

    O que distingue as duas é o VOCABULARIO (o que se registra) e uma regra:
    a averbação consome protocolo no RTD e não no RCPJ. O resto — livro,
    folha, termo, numeração — é o mesmo código, com a série dizendo qual
    atribuição é dela (`livro_nucleo.Serie.atribuicao`).

POR QUE CADA ATO OCUPA FOLHA NOVA, E NAO CONTINUA NA DO REGISTRO
    As séries PJ_A, PJ_B, TD_B, TD_C e TD_F têm `folha_nova=True` — medido
    de `tbTD_Propriedade`. Ao contrário da matrícula do RI, que é uma ficha
    contínua, o Livro A de pessoa jurídica e os livros do RTD são de
    trasladação integral: cada ato — registro, averbação ou cancelamento —
    é uma escritura nova, em folha nova. Por isso `lancar_averbacao()` e
    `lancar_cancelamento()` chamam `escrituracao.reservar()` de novo, e não
    reaproveitam o lugar do registro original.

O QUE AINDA NAO ENTRA
    O consumo de um novo número do protocolo específico na averbação do RTD —
    a regra está medida (RTD consome, RCPJ não), mas esse segundo lançamento
    ainda não está ligado à tela de averbação. Selo e custas já entram pela
    camada web, na mesma transação do ato.

FUNDAMENTO
    Lei 6.015/1973, arts. 114 a 148 (RCPJ) e 127 a 130 (RTD).
    LEVANTAMENTO_QUATRO_ATRIBUICOES.md — o acervo medido em 20/08/2026.
"""
from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS rg_registros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    atribuicao INTEGER NOT NULL,            -- 3 (RCPJ) ou 4 (RTD)
    serie TEXT NOT NULL,                    -- PJ_A, PJ_B, TD_B, TD_C, TD_F
    numero INTEGER,                         -- numero_ordem do ato de registro, no nucleo
    -- O VOLUME DO LIVRO, como o acervo o tem: '7', '05', '5', '04'. O
    -- E-Oficio nao guarda a LETRA (A e B do RCPJ; B, C e F do RTD), so o
    -- numero do volume — e a certidao de inteiro teor precisa dele para dizer
    -- "no Livro A-5", que e como as 38 certidoes do acervo escrevem.
    volume TEXT,
    natureza TEXT,                          -- o que se registra, em texto livre
    requerente_nome TEXT,
    requerente_documento TEXT,
    situacao TEXT NOT NULL DEFAULT 'ATIVO', -- ATIVO | CANCELADO
    teor TEXT,
    teor_formato TEXT NOT NULL DEFAULT 'texto',
    origem TEXT NOT NULL DEFAULT 'MANUAL',  -- MANUAL | EOFICIO
    origem_chave TEXT,
    importacao_id INTEGER,
    criado_em TEXT NOT NULL,
    criado_por INTEGER,
    UNIQUE(origem, origem_chave)
);

CREATE INDEX IF NOT EXISTS ix_rg_registros_serie ON rg_registros(serie, situacao);
CREATE INDEX IF NOT EXISTS ix_rg_registros_requerente ON rg_registros(requerente_documento);

CREATE TABLE IF NOT EXISTS rg_atos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    registro_id INTEGER NOT NULL REFERENCES rg_registros(id),
    tipo TEXT NOT NULL,                     -- REGISTRO | AVERBACAO | CANCELAMENTO

    servico_codigo INTEGER,                 -- atribuicoes.ATOS, quando confirmado
    selo TEXT,
    protocolo_id INTEGER,
    lancamento_id INTEGER,

    livro_id INTEGER REFERENCES nu_livros(id),
    folha INTEGER,
    verso INTEGER NOT NULL DEFAULT 0,
    numero_ordem INTEGER,
    rotulo TEXT,

    data_ato TEXT NOT NULL,
    teor TEXT,
    teor_formato TEXT NOT NULL DEFAULT 'texto',
    motivo_cancelamento TEXT,

    origem TEXT NOT NULL DEFAULT 'MANUAL',
    origem_chave TEXT,
    importacao_id INTEGER,

    criado_em TEXT NOT NULL,
    criado_por INTEGER
);

CREATE INDEX IF NOT EXISTS ix_rg_atos_registro ON rg_atos(registro_id, tipo);
CREATE INDEX IF NOT EXISTS ix_rg_atos_selo ON rg_atos(selo);

-- ===================================================================== o
-- TITULO APRESENTADO — o protocolo do RCPJ e do RTD.
--
-- O PEDIDO DO OFICIAL, EM 03/09/2026:
--     «Preciso que o sistema receba o titulo em protocolo, esteja disponivel
--      para analisar no visualizador de pdf direto no sistema, disponivel
--      para baixar, se positiva a qualificacao possa imprimir a etiqueta de
--      registro para o titulo apresentado em papel, ou encaminhamento pela
--      ONRTDPJ para os eletronicos.»
--
-- POR QUE UMA TABELA NOVA, E NAO UM CAMPO EM `rg_registros`
--     Porque o titulo existe ANTES do registro, e pode nunca virar um. Ele
--     entra, e a qualificacao decide: registra, ou volta com exigencia. Um
--     campo «situacao» em `rg_registros` faria o registro nascer para depois
--     ser desfeito — e registro desfeito e numero de livro gasto a toa.
--
--     E o Protesto ja ensinou isto nesta casa: o titulo existe antes do
--     apontamento. Aqui e o mesmo desenho.
--
-- O NUMERO SAI DO LIVRO DE PROTOCOLO DO NUCLEO, E ELE JA EXISTIA
--     `livro_nucleo` declara `PJ_PROTOCOLO` e `TD_PROTOCOLO` desde 21/08/2026
--     — diarias, com termo continuo — e **nenhuma tela jamais escreveu
--     nelas**. Sao a «funcao pronta que nenhuma tela chama» pela enesima vez
--     neste projeto. Esta tabela e a tela que faltava.
--
-- OS DOIS NUMEROS DO TITULO, MEDIDOS NO E-OFICIO EM 03/09/2026
--     `tbRegistroTD` guarda **dois**: `strProtocoloGeral` ('2026.01.164') e
--     `intProtocolo` (1275). O primeiro e o do balcao, que serve as seis
--     atribuicoes; o segundo e o do RTD/RCPJ, e cada atribuicao tem o seu
--     contador (`tbTD_Propriedade.intProtocolo_RTD` = 1275 e
--     `intProtocolo_RPJ` = 1273). Guardar so um perderia metade da amarracao.
CREATE TABLE IF NOT EXISTS rg_titulos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    atribuicao INTEGER NOT NULL,             -- 3 (RCPJ) ou 4 (RTD)
    numero INTEGER,                          -- o numero no Livro de Protocolo
    livro_id INTEGER REFERENCES nu_livros(id),
    folha INTEGER,
    verso INTEGER NOT NULL DEFAULT 0,
    rotulo TEXT,

    data_apresentacao TEXT NOT NULL,
    hora TEXT,

    apresentante TEXT,
    apresentante_documento TEXT,
    telefone TEXT,
    email TEXT,

    natureza TEXT,                           -- o que e o titulo, em texto livre
    serie TEXT,                              -- o livro pretendido: PJ_A .. TD_F
    valor_declarado TEXT,
    vias INTEGER NOT NULL DEFAULT 1,

    -- PAPEL ou ELETRONICO. **E ESTA COLUNA QUE PARTE O CAMINHO EM DOIS**: o
    -- de papel recebe etiqueta colada no titulo; o eletronico volta pela
    -- Central. O oficial pediu os dois na mesma frase, e sao dois destinos.
    forma TEXT NOT NULL DEFAULT 'PAPEL',

    situacao TEXT NOT NULL DEFAULT 'APRESENTADO',
    prazo_ate TEXT,

    -- A PONTE COM O PROTOCOLO DO BALCAO, do mesmo feitio de
    -- `cx_protocolos.ri_protocolo_id`, que ja liga a prenotacao do RI.
    protocolo_geral_id INTEGER REFERENCES cx_protocolos(id),
    -- E a ponte com o registro, quando a qualificacao foi positiva.
    registro_id INTEGER REFERENCES rg_registros(id),

    observacao TEXT,
    origem TEXT NOT NULL DEFAULT 'MANUAL',
    origem_chave TEXT,
    importacao_id INTEGER,
    criado_em TEXT NOT NULL,
    criado_por INTEGER,
    UNIQUE(origem, origem_chave)
);

CREATE INDEX IF NOT EXISTS ix_rg_titulos_situacao
    ON rg_titulos(situacao, data_apresentacao);
CREATE INDEX IF NOT EXISTS ix_rg_titulos_atribuicao
    ON rg_titulos(atribuicao, situacao);
CREATE INDEX IF NOT EXISTS ix_rg_titulos_apresentante
    ON rg_titulos(apresentante_documento);

-- A QUALIFICACAO — a decisao registral sobre o titulo.
--
-- DUAS PALAVRAS, E NAO TRES: POSITIVA e NEGATIVA.
--     O oficial disse «se positiva a qualificacao». O oposto dela, no
--     registro, sai com as EXIGENCIAS escritas — que e o que o RI ja chama de
--     nota devolutiva (`ri_notas_devolutivas`). Inventar uma terceira palavra
--     («pendente», «parcial») criaria vocabulario novo tendo o antigo a mao.
--
-- UMA LINHA POR QUALIFICACAO, E NAO UMA POR TITULO.
--     O titulo volta com exigencia, o apresentante cumpre, e o titulo e
--     requalificado. Sobrescrever a primeira decisao apagaria a razao pela
--     qual ele voltou — e e ela que a correicao le.
CREATE TABLE IF NOT EXISTS rg_qualificacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo_id INTEGER NOT NULL REFERENCES rg_titulos(id),
    ordem INTEGER NOT NULL,                  -- 1a, 2a, 3a qualificacao daquele titulo
    resultado TEXT NOT NULL,                 -- POSITIVA | NEGATIVA
    fundamentacao TEXT,
    exigencias TEXT,                         -- so na NEGATIVA, e obrigatoria nela
    prazo_ate TEXT,
    data_qualificacao TEXT NOT NULL,
    qualificada_por TEXT,
    criado_em TEXT NOT NULL,
    criado_por INTEGER,
    UNIQUE(titulo_id, ordem)
);

CREATE INDEX IF NOT EXISTS ix_rg_qualificacoes_titulo
    ON rg_qualificacoes(titulo_id, ordem);

-- O QUE PASSOU PELA CENTRAL — o encaminhamento do titulo eletronico.
--
-- **ESTA TABELA GUARDA O QUE ACONTECEU; QUEM FALA COM A CENTRAL E
-- `onrtdpj_api`.** Cada linha e uma passagem: o titulo veio de la (com o
-- protocolo de la), ou a resposta subiu daqui — a nota devolutiva, o registro.
--
-- **E ELA GUARDA TAMBEM O QUE PASSOU PELO PORTAL, e nao so pela API.** Nem
-- tudo o que acontece na Central passa pela integracao; o que se fez a mao
-- tambem precisa ficar escrito, senao a correicao ve um titulo que sumiu por
-- semanas.
--
-- **E O COMENTARIO QUE ESTAVA AQUI DIZIA QUE NAO HAVIA CONTRATO A MEDIR.**
-- Ele afirmava que «escrever um endereco, um nome de operacao ou um formato de
-- mensagem seria inventar numero», porque o acervo do E-Oficio nao tem uma
-- unica tabela nem uma unica coluna de RTDPJ. **Aquela medicao estava certa; a
-- conclusao estava errada** — o contrato da Central esta PUBLICO em
-- `centralinside.rtdbrasil.org.br/swagger/docs/v1`, Swagger 2.0, 81 caminhos,
-- como o WSDL da CRA estava. Nao achar onde eu procurei nao prova que nao
-- existe.
CREATE TABLE IF NOT EXISTS rg_encaminhamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo_id INTEGER NOT NULL REFERENCES rg_titulos(id),
    central TEXT NOT NULL DEFAULT 'ONRTDPJ',
    sentido TEXT NOT NULL,                   -- RECEBIDO | ENVIADO
    protocolo_central TEXT,
    data_encaminhamento TEXT NOT NULL,
    observacao TEXT,
    criado_em TEXT NOT NULL,
    criado_por INTEGER
);

CREATE INDEX IF NOT EXISTS ix_rg_encaminhamentos_titulo
    ON rg_encaminhamentos(titulo_id, id);
"""

MIGRACOES: tuple[tuple[str, str, str], ...] = (
    ("rg_registros", "volume", "TEXT"),
    # DE QUE TITULO SAIU AQUELE REGISTRO. A ponte existe nos dois sentidos de
    # proposito: da ficha do registro se chega ao titulo apresentado (e ao PDF
    # dele), e do titulo se chega ao registro que ele virou.
    ("rg_registros", "titulo_id", "INTEGER"),
    # QUANTAS VEZES A ETIQUETA JA SAIU, E QUANDO SAIU A ULTIMA.
    #
    #   As mesmas duas colunas de `nt_reconhecimentos` e `nt_autenticacoes`,
    #   com o mesmo nome e o mesmo porque: **segunda via de etiqueta e o mesmo
    #   selo colado em dois papeis**, e quem confere precisa ver que houve.
    #
    #   No ATO, e nao no titulo: a etiqueta declara livro, folha e numero de
    #   ordem, que sao do ato. Um titulo que gera registro e depois averbacao
    #   tem duas etiquetas diferentes, e uma contagem so as somaria.
    ("rg_atos", "etiqueta_impressa_em", "TEXT"),
    ("rg_atos", "etiqueta_impressoes", "INTEGER NOT NULL DEFAULT 0"),
    # O SELO DE ARQUIVAMENTO (TJ 15.22) É UM SEGUNDO NÚMERO, E NÃO O MESMO
    # `selo` — pedido do oficial em 11/09/2026: «precisa ir um selo de
    # averbação pra cada averbação, mais um selo de arquivamento na
    # primeira». Sem coluna própria, o segundo `vincular_ao_ato` (o da
    # arquivamento) SOBRESCREVIA o primeiro em `selo`, e o registro 361
    # (Santa Isabel) ficou com o selo da averbação PERDIDO da coluna — só o
    # de arquivamento sobrou. `selo` continua sendo o da averbação do
    # próprio ato; `selo_arquivamento` só é gravado na 1ª averbação do
    # pacote.
    ("rg_atos", "selo_arquivamento", "TEXT"),
)


def init_rg_schema(con: sqlite3.Connection) -> None:
    """Cria as tabelas de RCPJ/RTD. Idempotente. Chamar DEPOIS do núcleo."""
    con.executescript(SCHEMA)
    for tabela, coluna, tipo in MIGRACOES:
        existentes = {linha[1] for linha in con.execute(f"PRAGMA table_info({tabela})")}
        if coluna not in existentes:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
