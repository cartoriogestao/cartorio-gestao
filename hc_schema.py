"""A habilitação de casamento — o processo que antecede todo casamento.

POR QUE ISTO É MÓDULO PRÓPRIO, E NÃO UM CAMPO DO ASSENTO
    O casamento é UM ato; a habilitação é um PROCESSO de semanas, com
    documentos, edital, prazo, oposição possível e uma decisão do oficial no
    fim. É a mesma forma do usucapião, e pelo mesmo motivo: fluxo com prazo e
    decisão não cabe num campo de texto.

    Código Civil arts. 1.525 a 1.532, Lei 6.015/1973 arts. 67 a 69, e Código de
    Normas da CGJ/MA.

O QUE O ACERVO TEM, E O QUE NÃO TEM — medido em 27/08/2026
    O E-Ofício **não guardava o processo**: não há tabela de habilitação nem de
    proclamas nele. Guardava só o resultado, dentro do assento de casamento —
    `dtmDataPublicacaoProclamas` (20 de 20), `dtmDataHabilitacao` (4 de 20),
    `bitHabilitado` (20 de 20) — e o contador do Livro D, que marca
    **1.358 proclamas registrados**.

    Ou seja: mil trezentas e cinquenta e oito habilitações aconteceram nesta
    casa, e nenhuma delas deixou rastro além de três datas no assento final.

    Então não há precedente de FORMA a imitar, e o que se imita é a LEI. Onde a
    lei não decide, o campo fica e a decisão é do oficial.

O PRAZO DO EDITAL é a razão de o edital existir: é o tempo em que terceiros podem
    opor impedimento. Publicar e habilitar no mesmo dia é o mesmo que não publicar.

    Redação vigente Lei 6.015/1973, art. 67, §1º (Lei 14.382/2022): publicidade
    eletrônica e certificado em até cinco dias, com documentação em ordem. O CC
    art. 1.527 (quinze dias) permanece citado na doutrina e em fluxos antigos —
    o oficial valida o procedimento local; o software reflete cinco dias corridos
    conforme orientação operacional pendente de confirmação escrita.

A CERTIDÃO DE HABILITAÇÃO VALE NOVENTA DIAS (CC art. 1.532). Casamento
    celebrado depois disso é casamento sem habilitação — e a habilitação é o
    que o oficial atesta ao celebrar.
"""
from __future__ import annotations

import re

from bd_nativo import banco

# ONDE O EDITAL DESTA CASA É PUBLICADO — informação do oficial em 28/08/2026:
# **no e-Proclamas, pela CRC** (Central de Informações do Registro Civil).
#
#   Não é afixação no lugar de costume nem publicação na imprensa local — que
#   eram as duas hipóteses que eu tinha. Por isso o item `14.1.10` da tabela,
#   que cobra a publicação na imprensa, **não entra** nesta casa.
ONDE_SE_PUBLICA = "e-Proclamas (CRC)"

# Prazo do edital de proclamas — Lei 6.015/1973, art. 67, §1º (redação vigente).
#
#   Contagem em dias CORRIDOS (mesma regra que o código já usava para os 15 d
#   do CC art. 1.527). Não são dias úteis do CPC. Legado: PRAZO_DO_EDITAL = 15
#   (CC art. 1.527). Ensaio sandbox acelera datas em rcpn_casamento_habilitacao_
#   ensaio.py — não altere este valor para ensaio.
PRAZO_DO_EDITAL = 5

# Aviso fixo na ficha HC — não substitui parecer do oficial.
AVISO_REVISAO_JURIDICA_HC = (
    "Revisão jurídica local: antes de expedir certidão de habilitação ou "
    "prometer prazo às partes, confirme com o oficial o fluxo aplicável "
    "(Lei 6.015/1973, art. 67, §1º)."
)

# A validade da certidão de habilitação — CC art. 1.532.
VALIDADE_DA_HABILITACAO = 90

# Os documentos do art. 1.525 do Código Civil, na ordem dos incisos.
#
#   A lista é a da lei, e não a do balcão: o balcão pede outros papéis conforme
#   o caso (a autorização judicial do menor, a certidão de óbito do cônjuge
#   anterior), e esses entram como item acrescentado — com o motivo escrito.
DOCUMENTOS_DA_HABILITACAO: tuple[tuple[str, str, str], ...] = (
    ("CERTIDAO_NASCIMENTO", "Certidão de nascimento ou documento equivalente",
     "CC art. 1.525, I"),
    ("AUTORIZACAO", "Autorização das pessoas sob cuja dependência legal "
                    "estiverem, ou ato judicial que a supra",
     "CC art. 1.525, II"),
    ("DECLARACAO_TESTEMUNHAS",
     "Declaração de duas testemunhas, parentes ou não, que atestem conhecê-los "
     "e afirmem não existir impedimento",
     "CC art. 1.525, III"),
    ("DECLARACAO_ESTADO_CIVIL",
     "Declaração do estado civil, do domicílio e da residência atual dos "
     "contraentes e de seus pais, se forem conhecidos",
     "CC art. 1.525, IV"),
    ("PROVA_DISSOLUCAO",
     "Certidão de óbito do cônjuge falecido, de sentença declaratória de "
     "nulidade ou de anulação de casamento, ou do registro da sentença de "
     "divórcio — quando for o caso",
     "CC art. 1.525, V"),
)

# As situações do processo, na ordem em que acontecem.
#
#   ARQUIVADA e COM_OPOSICAO não são o fim da fila: são desvios. Um processo
#   com oposição volta a andar quando o oficial decide; um arquivado pode ser
#   desarquivado. Por isso a ordem aqui é a do caminho comum, e não uma
#   máquina de estados fechada.
SITUACOES: dict[str, str] = {
    "EM_ANALISE": "Em análise — conferindo os documentos",
    "EDITAL_PUBLICADO": f"Edital publicado — correndo o prazo de {PRAZO_DO_EDITAL} dias",
    "COM_OPOSICAO": "Com oposição — aguardando decisão do oficial",
    "HABILITADO": "Habilitado — certidão emitida",
    "CELEBRADO": "Casamento celebrado",
    "ARQUIVADO": "Arquivado",
}

# O tipo de casamento a que a habilitação leva.
#
#   Ele muda o livro do assento final: o civil vai para o Livro B; o religioso
#   com efeito civil vai para o B-Auxiliar. `rc_assento.SERIE_DA_ESPECIE` já
#   sabe disso — aqui só se registra qual foi pedido.
TIPOS: dict[str, str] = {
    "CIVIL": "Casamento civil",
    "RELIGIOSO": "Casamento religioso com efeito civil",
    "CONVERSAO": "Conversão de união estável em casamento",
}

# Os regimes de bens. Medido no acervo: «Comunhão Parcial» em 19 dos 20
# casamentos e «Separação de Bens» em 1 — mas a lista é a da lei, porque o
# regime que a casa nunca usou continua sendo regime que alguém pode escolher.
REGIMES: dict[str, str] = {
    "COMUNHAO_PARCIAL": "Comunhão parcial de bens",
    "COMUNHAO_UNIVERSAL": "Comunhão universal de bens",
    "SEPARACAO_TOTAL": "Separação total de bens",
    "SEPARACAO_OBRIGATORIA": "Separação obrigatória de bens (CC art. 1.641)",
    "PARTICIPACAO_FINAL": "Participação final nos aquestos",
}


SCHEMA = """
CREATE TABLE IF NOT EXISTS hc_habilitacoes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    numero INTEGER,
    ano INTEGER,
    data_entrada TEXT NOT NULL,
    tipo TEXT NOT NULL,                     -- CIVIL | RELIGIOSO | CONVERSAO
    regime TEXT,
    situacao TEXT NOT NULL DEFAULT 'EM_ANALISE',

    -- OS NUBENTES FICAM EM COLUNAS, E NÃO EM TABELA DE PARTES.
    --   São sempre dois, nunca mais nem menos, e cada um tem os mesmos campos.
    --   Uma tabela de partes aqui só acrescentaria um JOIN para responder «quem
    --   vai casar», que é a pergunta que esta tela mais responde.
    nubente1_nome TEXT NOT NULL,
    nubente1_nome_norm TEXT,
    nubente1_nome_pos TEXT,                 -- como passa a assinar
    nubente1_sexo TEXT,
    nubente1_nascimento TEXT,
    nubente1_documento TEXT,
    nubente1_estado_civil TEXT,
    nubente1_profissao TEXT,
    nubente1_nacionalidade TEXT,
    nubente1_naturalidade TEXT,
    nubente1_endereco TEXT,
    nubente1_pai TEXT,
    nubente1_mae TEXT,

    nubente2_nome TEXT NOT NULL,
    nubente2_nome_norm TEXT,
    nubente2_nome_pos TEXT,
    nubente2_sexo TEXT,
    nubente2_nascimento TEXT,
    nubente2_documento TEXT,
    nubente2_estado_civil TEXT,
    nubente2_profissao TEXT,
    nubente2_nacionalidade TEXT,
    nubente2_naturalidade TEXT,
    nubente2_endereco TEXT,
    nubente2_pai TEXT,
    nubente2_mae TEXT,

    -- O EDITAL E O PRAZO
    edital_em TEXT,
    edital_prazo_ate TEXT,
    edital_teor TEXT,
    edital_hash TEXT,
    proclamas_assento_id INTEGER,           -- o registro no Livro D

    -- A OPOSIÇÃO, quando há
    oposicao_em TEXT,
    oposicao_quem TEXT,
    oposicao_teor TEXT,
    oposicao_decidida_em TEXT,
    oposicao_decisao TEXT,                  -- ACOLHIDA | REJEITADA
    oposicao_fundamento TEXT,

    -- A HABILITAÇÃO
    habilitado_em TEXT,
    habilitado_por TEXT,
    habilitacao_vale_ate TEXT,
    certidao_numero INTEGER,
    certidao_ano INTEGER,
    certidao_teor TEXT,
    certidao_hash TEXT,

    -- O CASAMENTO, quando celebrado
    casamento_assento_id INTEGER,
    celebrado_em TEXT,

    arquivado_em TEXT,
    arquivado_motivo TEXT,
    observacao TEXT,
    selo TEXT,
    lancamento_id INTEGER,
    origem TEXT NOT NULL DEFAULT 'MANUAL',
    origem_chave TEXT,
    criado_em TEXT NOT NULL,
    criado_por TEXT,
    FOREIGN KEY (proclamas_assento_id) REFERENCES rc_assentos(id),
    FOREIGN KEY (casamento_assento_id) REFERENCES rc_assentos(id)
);

-- O NÚMERO DA HABILITAÇÃO NÃO REPETE DENTRO DO ANO, e a trava mora no banco.
--   É a regra da casa: onde a regra pode morar no banco, ela mora no banco.
CREATE UNIQUE INDEX IF NOT EXISTS ux_hc_numero
    ON hc_habilitacoes(ano, numero) WHERE numero IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_hc_situacao ON hc_habilitacoes(situacao);
CREATE INDEX IF NOT EXISTS ix_hc_nubente1 ON hc_habilitacoes(nubente1_nome_norm);
CREATE INDEX IF NOT EXISTS ix_hc_nubente2 ON hc_habilitacoes(nubente2_nome_norm);
CREATE INDEX IF NOT EXISTS ix_hc_prazo ON hc_habilitacoes(edital_prazo_ate);

CREATE TABLE IF NOT EXISTS hc_documentos (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    habilitacao_id INTEGER NOT NULL,
    codigo TEXT NOT NULL,
    descricao TEXT NOT NULL,
    fundamento TEXT,
    de_quem TEXT,                           -- NUBENTE1 | NUBENTE2 | AMBOS
    apresentado INTEGER NOT NULL DEFAULT 0,
    apresentado_em TEXT,
    apresentado_por TEXT,
    -- DISPENSAR EXIGE MOTIVO ESCRITO, como no usucapião. Dispensar é decisão do
    -- oficial; ignorar não é.
    dispensado INTEGER NOT NULL DEFAULT 0,
    dispensado_motivo TEXT,
    dispensado_em TEXT,
    dispensado_por TEXT,
    observacao TEXT,
    criado_em TEXT NOT NULL,
    FOREIGN KEY (habilitacao_id) REFERENCES hc_habilitacoes(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_hc_doc
    ON hc_documentos(habilitacao_id, codigo, de_quem);

CREATE TABLE IF NOT EXISTS hc_andamento (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    habilitacao_id INTEGER NOT NULL,
    quando TEXT NOT NULL,
    o_que TEXT NOT NULL,
    detalhe TEXT,
    situacao_antes TEXT,
    situacao_depois TEXT,
    quem TEXT,
    FOREIGN KEY (habilitacao_id) REFERENCES hc_habilitacoes(id)
);

CREATE INDEX IF NOT EXISTS ix_hc_andamento
    ON hc_andamento(habilitacao_id, quando);

-- O QUE FOI MANDADO AO e-PROCLAMAS, E O QUE A CENTRAL RESPONDEU.
--
--   Construída em 03/09/2026, quando a integração deixou de ser pendência.
--   Até aqui o envio era manual e o sistema guardava só o protocolo em
--   `hc_habilitacoes.eproclamas_protocolo` — o que se podia fazer com verdade
--   enquanto a API não existia.
--
--   **O TEOR CONGELA, e a razão é a mesma do termo e do instrumento**: isto é
--   uma publicação que a serventia pagou e que alguém pode contestar meses
--   depois. O que a Central mostra hoje pode ser outra coisa; o que a casa
--   mandou foi isto.
--
--   **E O AMBIENTE ENTRA NA LINHA**, como em `cn_pendencias`: envio de
--   homologação com cara de envio real é o carimbo que mente na pior forma —
--   quem o lesse diria ao casal que o edital está publicado.
CREATE TABLE IF NOT EXISTS hc_eproclamas (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    habilitacao_id INTEGER NOT NULL,
    matricula TEXT NOT NULL,                -- a de 32 dígitos do Livro D
    publicacao INTEGER NOT NULL DEFAULT 0,
    livro_eletronico INTEGER NOT NULL DEFAULT 0,
    ambiente TEXT NOT NULL,                 -- HOMOLOGACAO | PRODUCAO
    corpo_enviado TEXT NOT NULL,            -- congelado, como foi
    corpo_hash TEXT NOT NULL,
    resposta TEXT,
    -- O QUE A CENTRAL DEVOLVE É O `batchId`, O NÚMERO DO LOTE — e não um
    -- protocolo por proclama. Medido no esquema da resposta em 03/09/2026.
    --
    --   A coluna guarda esse número e continua com este nome porque é ele que
    --   alimenta `hc_habilitacoes.eproclamas_protocolo`, que existe desde
    --   28/08 e é onde o balcão já procura «o número que a Central devolveu».
    --   **Duas colunas para o mesmo fato divergiriam no primeiro conserto.**
    --
    --   **E ela fica VAZIA quando a Central recusou o proclama**: sem isso uma
    --   recusa contaria como publicação feita, e a trava contra publicar duas
    --   vezes ficaria ligada sobre nada.
    protocolo TEXT,
    enviado_em TEXT NOT NULL,
    enviado_por TEXT,
    FOREIGN KEY (habilitacao_id) REFERENCES hc_habilitacoes(id)
);

CREATE INDEX IF NOT EXISTS ix_hc_eproclamas
    ON hc_eproclamas(habilitacao_id, enviado_em);
"""

MIGRACOES: tuple[tuple[str, str, str], ...] = (
    # O EDITAL DESTA CASA VAI PARA O e-PROCLAMAS DA CRC — informação do oficial
    # em 28/08/2026, quando perguntei se ele era publicado na imprensa ou só
    # afixado. Não é nem um nem outro: é **publicação digital na Central**.
    #
    #   Isso muda o que o processo tem de guardar. Edital afixado se prova com
    #   o papel na parede; edital publicado na Central se prova com o
    #   **protocolo que ela devolve** — e sem esse número, meses depois,
    #   ninguém consegue mostrar que a publicação aconteceu.
    #
    #   O envio à Central é integração que este sistema ainda não tem. Até
    #   tê-la, o escrevente publica no e-Proclamas e anota aqui o protocolo:
    #   guardar o número é o que se pode fazer com verdade hoje, e é mais do
    #   que não guardar nada.
    ("hc_habilitacoes", "eproclamas_protocolo", "TEXT"),
    ("hc_habilitacoes", "eproclamas_em", "TEXT"),
    # A CONVERSÃO DE UNIÃO ESTÁVEL PRECISA DIZER QUE UNIÃO ELA CONVERTE, e o
    # contrato do selador é quem cobra: o schema próprio da conversão
    # (`DadosSeloHabilitacaoCasamentoConversao`) tem `numeroProcesso`
    # **obrigatório**, e a descrição dele diz «número do processo da união
    # estável» — não é o número desta habilitação.
    #
    #   Ele não se adivinha e não se deriva: é o número da escritura, do
    #   processo ou do registro que declarou a união — papel que o casal traz.
    #   Sem ele o selo não sai, e a tela diz isso na hora, e não na rede.
    ("hc_habilitacoes", "uniao_estavel_processo", "TEXT"),
)


def init_hc_schema(con) -> None:
    """Cria as tabelas da habilitação de casamento."""
    bd = banco(con)
    for comando in re.split(r";[ \t]*\n", SCHEMA):
        if re.sub(r"--[^\n]*", "", comando).strip():
            bd.escrever(comando)
    for tabela, coluna, tipo in MIGRACOES:
        if not bd.tem_coluna(tabela, coluna):    # já existe
            bd.escrever(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
