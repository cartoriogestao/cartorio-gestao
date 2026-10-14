"""As tabelas da retificação de área e do georreferenciamento.

    «vamos criar o módulo de processos de retificação de área e
     georreferenciamento» — o oficial, 29/08/2026

POR QUE É PROCESSO, E NÃO UM CAMPO NA MATRÍCULA
    `REVISAO_MODULO_RI.md` já dizia: *«estes não se resolvem com um modelo de
    texto. São fluxos com prazo, notificação e decisão»*. A retificação é um
    deles — Lei 6.015/1973, art. 213, e arts. 587 a 620 do Código de Normas do
    TJMA —, e ela tem a peça que define tudo: **a notificação dos confrontantes,
    com prazo de 15 dias úteis, cujo silêncio vale anuência**.

    É a forma do usucapião, e por isso as tabelas são as dele com outro nome:
    processo, peças, andamento e conferência. O que muda é a peça central, que
    aqui é o CONFRONTANTE.

E ISSO NÃO É EXCEÇÃO NESTA CASA
    Medido em 29/08/2026 nas 1.508 fichas de matrícula com teor: **767** citam o
    INCRA, **385** o memorial descritivo, **182** o georreferenciamento, **157**
    o SIGEF e **96** a retificação. Numa serventia rural, georreferenciamento é o
    pão de cada dia — o que não é o que a intuição diz.

A TABELA QUE NÃO EXISTE NO USUCAPIÃO, E É A MAIS IMPORTANTE
    `rt_confrontantes`. **O prazo conta individualmente para cada notificado**
    (art. 599), e por isso a data mora na linha de cada um, e não no processo.
    Um prazo só para todos faria a averbação sair antes de o último notificado
    ter tido os seus quinze dias — e é justamente a notificação malfeita que
    anula a averbação depois.
"""
from __future__ import annotations

import sqlite3

SCHEMA = """
-- ------------------------------------------------------------- o processo
--
-- `especie` distingue GEORREFERENCIADA de NAO_GEORREFERENCIADA, e **essa
-- distincao e da casa**: medido nas fichas, esta serventia ja escreveu
-- «AVERBACAO DE RETIFICACAO DE AREA GEORREFERENCIADA» e «... NAO
-- GEORREFERENCIADA» no rotulo do proprio ato.
--
-- `fundamento` separa os dois incisos do art. 213 da Lei 6.015/1973, e eles NAO
-- sao a mesma coisa: o I e de oficio, para erro evidente que nao altera direito
-- de ninguem; o II e a requerimento, e exige planta, memorial com ART e a
-- anuencia dos confrontantes. Deixar o balcao escolher seria deixar corrigir de
-- oficio o que precisa da anuencia do vizinho — e o vizinho descobre quando vai
-- vender.

CREATE TABLE IF NOT EXISTS rt_processos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero TEXT NOT NULL,                   -- o numero dos autos nesta casa
    ano INTEGER,
    especie TEXT NOT NULL,                  -- ver rt_tjma.NOME_DA_ESPECIE
    fundamento TEXT NOT NULL,               -- ver rt_tjma.NOME_DO_FUNDAMENTO
    fase TEXT NOT NULL DEFAULT 'AUTUACAO',  -- ver retificacao.FASES
    situacao TEXT NOT NULL DEFAULT 'EM_ANDAMENTO',

    -- A MATRICULA RETIFICANDA E OBRIGATORIA, e e a diferenca em relacao ao
    -- usucapiao: la o imovel pode nao ter matricula nenhuma; aqui o que se
    -- retifica E o registro, e sem ele nao ha o que retificar.
    matricula_id INTEGER NOT NULL REFERENCES ri_matriculas(id),
    rural INTEGER NOT NULL DEFAULT 0,       -- decide o inciso VII ou o IX

    requerente_nome TEXT,
    requerente_documento TEXT,

    -- O profissional responde pelos trabalhos tecnicos, e a norma o cobra por
    -- nome: art. 592, IV (ART/RRT/TRT quitada, com referencia a ESTE
    -- procedimento) e art. 600 (ele e intimado junto com o requerente quando ha
    -- impugnacao).
    profissional_nome TEXT,
    profissional_conselho TEXT,             -- CREA, CAU ou CFT
    profissional_registro TEXT,
    art_numero TEXT,                        -- a ART/RRT/TRT

    -- A area. Texto, e nao numero: o que vem do memorial e uma medida com
    -- unidade — «12,4567 ha», «3.450,00 m2» —, e guardar so o numero perderia a
    -- unidade, que e o que faz a medida querer dizer alguma coisa.
    --
    -- E NAO HA LIMITE de aumento nem de reducao (art. 589, § 2o), desde que
    -- reflita as reais divisas: nao ha trava a escrever aqui.
    area_na_matricula TEXT,
    area_pretendida TEXT,
    perimetro TEXT,

    -- O georreferenciamento. `certificacao_incra` e o numero que o INCRA
    -- expediu, e o art. 613 diz que o memorial tem de ser o dele, sem alteracao
    -- nenhuma.
    certificacao_incra TEXT,
    sigef_codigo TEXT,

    -- A prenotacao. O art. 591 diz que o requerimento do 213, II **nao gera
    -- prioridade** — ao contrario da prenotacao comum, que existe para isso. O
    -- campo guarda o protocolo do atendimento, e nao uma prioridade.
    protocolo_id INTEGER,
    prenotacao TEXT,

    -- A ata notarial do art. 595, quando nao da para identificar todos os
    -- confrontantes (area extensa, ocupacao irregular, invasao, assentamento).
    ata_notarial_livro TEXT,
    ata_notarial_folha TEXT,
    ata_notarial_data TEXT,
    ata_notarial_cartorio TEXT,

    -- A decisao do art. 604. `decisao_fundamento` e NOT NULL na regra, e nao no
    -- esquema: o modulo recusa decidir sem ela, e a mensagem diz por que.
    decidido_em TEXT,
    decidido_por TEXT,
    decisao TEXT,                           -- PROCEDENTE | IMPROCEDENTE
    decisao_fundamento TEXT,

    -- O DESFECHO, e ele e a maior operacao registral deste sistema: averba,
    -- ENCERRA a matricula retificanda e abre uma NOVA, transportando os onus
    -- (art. 604, § 1o e art. 620, § 1o). O modulo NAO faz isso: ele guarda o
    -- que a tela do RI lavrou.
    ato_id INTEGER REFERENCES ri_atos(id),
    matricula_nova_id INTEGER REFERENCES ri_matriculas(id),
    averbado_em TEXT,

    -- O PRAZO QUE SO ESTE MODULO CONHECE — art. 620, § 2o: averbada a poligonal
    -- certificada, a serventia tem **30 dias** para requerer o registro no
    -- SIGEF. E obrigacao da casa, nasce DEPOIS do ato (quando o cliente ja foi
    -- embora), e nada no sistema a acompanhava.
    sigef_requerido_em TEXT,
    sigef_protocolo TEXT,

    observacao TEXT,
    criado_em TEXT NOT NULL,
    criado_por TEXT,
    atualizado_em TEXT,
    encerrado_em TEXT,
    UNIQUE(numero)
);

CREATE INDEX IF NOT EXISTS ix_rt_proc_fase ON rt_processos(fase, situacao);
CREATE INDEX IF NOT EXISTS ix_rt_proc_matricula ON rt_processos(matricula_id);

-- ------------------------------------------------------- os confrontantes
--
-- A TABELA QUE DEFINE ESTE MODULO.
--
-- `prazo_ate` mora AQUI, e nao no processo, porque o art. 599 diz que o prazo
-- «conta-se individualmente para cada notificado». Um prazo so para todos faria
-- a averbacao sair antes de o ultimo ter tido os seus quinze dias uteis.
--
-- `divisa_afetada` existe por causa do art. 596: **so contam os confinantes das
-- divisas afetadas** pela alteracao, e o paragrafo unico dispensa a anuencia e
-- ate a intimacao de quem nao tem medida alterada. Sem esta coluna, o balcao
-- notificaria vizinho que a norma nao manda notificar — trabalho, custo e
-- espera a toa.
--
-- `papel` separa o confrontante do credor real: o art. 593 e o 617 dizem que o
-- credor real e o senhorio direto **nao precisam anuir, basta a notificacao**, e
-- que a impugnacao deles tem de ser fundamentada.

CREATE TABLE IF NOT EXISTS rt_confrontantes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    processo_id INTEGER NOT NULL REFERENCES rt_processos(id),
    papel TEXT NOT NULL DEFAULT 'CONFRONTANTE',  -- ver retificacao.PAPEIS
    nome TEXT NOT NULL,
    nome_norm TEXT,
    documento TEXT,

    -- Onde ele mora, e o art. 598, § 1o da tres enderecos possiveis: o que o
    -- requerente indicou, o que consta da matricula do imovel contiguo, e o
    -- proprio imovel que faz divisa.
    endereco TEXT,
    matricula_contigua TEXT,
    serventia_contigua TEXT,

    divisa_afetada INTEGER NOT NULL DEFAULT 1,
    assinou_planta INTEGER NOT NULL DEFAULT 0,
    carta_anuencia INTEGER NOT NULL DEFAULT 0,

    -- A notificacao. `forma` segue a ORDEM do art. 598 — pessoal, RTD, correio
    -- com AR e, so «caso frustradas as tentativas anteriores», edital.
    notificado_em TEXT,
    forma TEXT,                             -- ver rt_tjma.COMO_NOTIFICAR
    recebido_em TEXT,                       -- de onde o prazo conta (§ 2o)
    prazo_ate TEXT,

    -- A resposta. SILENCIO nao e ausencia de resposta: e a **anuencia
    -- presumida** do art. 599, § 1o, e por isso tem nome proprio.
    resposta TEXT,                          -- ver retificacao.RESPOSTAS
    respondido_em TEXT,
    impugnacao TEXT,

    criado_em TEXT NOT NULL,
    criado_por TEXT
);

CREATE INDEX IF NOT EXISTS ix_rt_confr_processo
    ON rt_confrontantes(processo_id, papel);
CREATE INDEX IF NOT EXISTS ix_rt_confr_nome ON rt_confrontantes(nome_norm);

-- -------------------------------------------------------------- as peças
--
-- O ARQUIVO FICA EM DISCO; aqui ficam o caminho e o sha256 — banco que guarda
-- PDF nao cabe no backup diario. E a mesma decisao do usucapiao.
--
-- `dispensado` existe porque a norma DISPENSA coisas (arts. 610, § 1o; 619;
-- 596, paragrafo unico; 593), e dispensa se registra com o artigo ao lado —
-- «dispensar exige motivo escrito» e regra desta casa desde o usucapiao.

CREATE TABLE IF NOT EXISTS rt_pecas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    processo_id INTEGER NOT NULL REFERENCES rt_processos(id),
    tipo TEXT NOT NULL,                     -- o inciso ou o artigo que a pede
    descricao TEXT,
    arquivo TEXT,
    sha256 TEXT,
    entregue_em TEXT,
    dispensado INTEGER NOT NULL DEFAULT 0,
    dispensa_motivo TEXT,
    dispensa_artigo TEXT,
    criado_em TEXT NOT NULL,
    criado_por TEXT
);

CREATE INDEX IF NOT EXISTS ix_rt_pecas_processo
    ON rt_pecas(processo_id, tipo);

-- ----------------------------------------------------------- o andamento
--
-- Tudo o que aconteceu, na ordem. Num rito de meses com prazo de dias uteis,
-- «quando foi que isso andou?» e a pergunta que mais se repete — e a resposta
-- nao pode ser a memoria de quem estava no balcao.

CREATE TABLE IF NOT EXISTS rt_andamento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    processo_id INTEGER NOT NULL REFERENCES rt_processos(id),
    quando TEXT NOT NULL,
    tipo TEXT NOT NULL,
    o_que TEXT NOT NULL,
    artigo TEXT,                            -- o endereco da norma, quando ha
    confrontante_id INTEGER REFERENCES rt_confrontantes(id),
    quem TEXT
);

CREATE INDEX IF NOT EXISTS ix_rt_andamento_processo
    ON rt_andamento(processo_id, quando);

-- --------------------------------------------------------- a conferência
--
-- O checklist do art. 592, item a item, com o artigo ao lado. E a forma da
-- `us_conferencia`, e pelo mesmo motivo: **nao se decide procedente com item
-- pendente**, e dispensar exige motivo escrito.

CREATE TABLE IF NOT EXISTS rt_conferencia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    processo_id INTEGER NOT NULL REFERENCES rt_processos(id),
    item TEXT NOT NULL,
    artigo TEXT,
    situacao TEXT NOT NULL DEFAULT 'PENDENTE',
    nota TEXT,
    marcado_em TEXT,
    marcado_por TEXT,
    UNIQUE(processo_id, item)
);
"""

# So `ALTER TABLE ADD COLUMN`, como manda a casa. Tabela nova vai no SCHEMA.
# O TEOR DA NOTIFICACAO, CONGELADO — 21/09/2026, ordem do oficial: «faca ser
# possivel imprimir as notificacoes da usucapiao e da georreferenciamento em
# pdf».
#
#   Ate aqui esta tabela registrava QUE se notificou — `notificado_em`,
#   `forma`, `prazo_ate` — e o papel entregue ao confrontante era escrito fora
#   do sistema. Registro de notificacao sem o papel que a sustenta e uma linha
#   dizendo que a serventia notificou alguem, sem prova do que foi dito.
#
#   **CONGELADO, e nao remontado na hora de imprimir**: o que o confrontante
#   leu e o de entao. Mesma regra do termo do Registro Civil, da certidao do
#   Protesto e da notificacao da usucapiao.
MIGRACOES: tuple[tuple[str, str, str], ...] = (
    ("rt_confrontantes", "teor_expedido", "TEXT"),
)

# Indice sobre coluna de migracao NAO vai no SCHEMA: num banco que ja existe a
# coluna so aparece no `ALTER TABLE`, e o `CREATE INDEX` estoura ao abrir.
INDICES_DEPOIS_DA_MIGRACAO: tuple[str, ...] = ()


def init_rt_schema(con: sqlite3.Connection) -> None:
    """Cria as tabelas da retificação. Idempotente.

    CHAMAR DEPOIS DO `ri_schema`, porque `rt_processos` aponta para
    `ri_matriculas` e `ri_atos`.
    """
    con.executescript(SCHEMA)
    for tabela, coluna, tipo in MIGRACOES:
        existentes = {linha[1]
                      for linha in con.execute(f"PRAGMA table_info({tabela})")}
        if coluna not in existentes:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
    for comando in INDICES_DEPOIS_DA_MIGRACAO:
        con.execute(comando)
