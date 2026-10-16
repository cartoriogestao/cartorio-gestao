"""
Registro de Imoveis - esquema de dados.

Modulo oficial da serventia: os assentos sao imutaveis e encadeados por hash,
de modo que qualquer alteracao posterior a lavratura seja detectavel.

Convivem dois tipos de matricula, conforme decisao da serventia:

  ESTRUTURADA  a ficha tem atos destacados (R-1, AV-1 ...), navegaveis um a um.
  ACERVO       a ficha veio do acervo como um unico bloco de teor, sem atos
               destacados. Continua valida e consultavel, mas nao e navegavel.

A diferenca e sempre exibida ao usuario - nunca silenciada - porque muda o que
se pode fazer com a ficha: em matricula de acervo o proximo ato precisa ser
numerado a mao, ja que o sistema nao consegue deduzir a sequencia do texto.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, timedelta
from typing import Any

# ---------------------------------------------------------------- constantes

TIPO_FICHA = ("ESTRUTURADA", "ACERVO")
TIPO_ATO = ("R", "AV")
SITUACOES = ("ATIVA", "ANULADA", "ENCERRADA", "CANCELADA", "INEXISTENTE")
ORIGENS = ("EOFICIO", "JSON", "MANUAL")
FORMATOS_TEOR = ("texto", "rtf", "html", "odt")

# REGRA DA SERVENTIA, confirmada em 17/09/2026: a serie anterior a 4.015 e
# acervo. O numero 4.015 e o primeiro que pode ser aberto como ficha nova do
# sistema. Esta fronteira nao depende de a importacao ter conseguido separar
# atos: abaixo dela, o documento historico e o conteudo importado sao a fonte.
PRIMEIRA_MATRICULA_DO_SISTEMA = 4015

# Rotulo legivel para a tela. O usuario nunca ve o codigo cru.
ROTULO_TIPO_FICHA = {
    "ESTRUTURADA": "Estruturada",
    "ACERVO": "Acervo (bloco unico)",
}


SCHEMA = """
CREATE TABLE IF NOT EXISTS ri_matriculas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero TEXT NOT NULL,
    complemento TEXT NOT NULL DEFAULT '',
    cnm TEXT,
    livro TEXT,
    livro_norm TEXT,
    folha TEXT,
    folha_complemento TEXT,
    data_abertura TEXT,
    selo_abertura_texto TEXT,
    selo_abertura_qr TEXT,
    selo_abertura_qr_mime TEXT,
    selo_abertura_qr_2 TEXT,
    selo_abertura_qr_2_mime TEXT,
    emolumentos_abertura TEXT,

    tipo_ficha TEXT NOT NULL DEFAULT 'ESTRUTURADA',
    situacao TEXT NOT NULL DEFAULT 'ATIVA',

    -- O acervo herdado do E-Oficio e reconhecidamente precario. Enquanto uma
    -- ficha nao for conferida contra o livro fisico, ela aparece marcada na
    -- tela: vale para consulta, mas nao se apresenta como conferida.
    conferido INTEGER NOT NULL DEFAULT 0,
    conferido_em TEXT,
    conferido_por INTEGER,

    encerrada INTEGER NOT NULL DEFAULT 0,
    motivo_encerramento TEXT,
    data_encerramento TEXT,

    tipo_imovel TEXT,
    rural_urbano TEXT,
    logradouro TEXT,
    numero_predial TEXT,
    complemento_endereco TEXT,
    bairro TEXT,
    cidade TEXT,
    uf TEXT,
    cep TEXT,
    area_valor TEXT,
    area_unidade TEXT,
    descricao_perimetro TEXT,
    confrontacoes TEXT,

    car TEXT,
    nirf TEXT,
    incra TEXT,
    sigef TEXT,
    ccir TEXT,
    cmc TEXT,
    inscricao_municipal TEXT,
    iptu TEXT,

    registro_anterior TEXT,
    observacao TEXT,

    teor TEXT,
    teor_formato TEXT NOT NULL DEFAULT 'texto',

    origem TEXT NOT NULL DEFAULT 'MANUAL',
    origem_chave TEXT,
    importacao_id INTEGER,

    criado_em TEXT NOT NULL,
    criado_por INTEGER,
    atualizado_em TEXT,
    atualizado_por INTEGER,
    FOREIGN KEY(criado_por) REFERENCES users(id),
    FOREIGN KEY(importacao_id) REFERENCES ri_importacoes(id)
);

CREATE INDEX IF NOT EXISTS ix_ri_mat_numero ON ri_matriculas(numero);
CREATE INDEX IF NOT EXISTS ix_ri_mat_cnm ON ri_matriculas(cnm);
CREATE INDEX IF NOT EXISTS ix_ri_mat_tipo ON ri_matriculas(tipo_ficha);
CREATE INDEX IF NOT EXISTS ix_ri_mat_origem ON ri_matriculas(origem, origem_chave);

CREATE TABLE IF NOT EXISTS ri_atos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matricula_id INTEGER NOT NULL,
    tipo TEXT NOT NULL,
    numero INTEGER NOT NULL,
    data_ato TEXT,
    natureza_titulo TEXT,
    protocolo TEXT,
    prenotacao TEXT,

    teor TEXT,
    teor_formato TEXT NOT NULL DEFAULT 'texto',

    cancelado INTEGER NOT NULL DEFAULT 0,
    cancelado_por_ato_id INTEGER,
    -- POR QUE O ATO FOI CANCELADO, quando quem o cancelou NAO foi outra
    -- averbacao. Duas coisas cancelam ato neste sistema, e cada uma guarda o
    -- seu rastro: o cancelamento normal e lavrado como averbacao nova, e o
    -- motivo dele fica no teor dessa averbacao (`cancelado_por_ato_id` aponta
    -- para ela); e o ato que o selador recusou e o operador NAO autorizou
    -- seguir — esse nao tem averbacao nenhuma, e o motivo nao caberia em
    -- lugar nenhum sem esta coluna.
    motivo_cancelamento TEXT,
    acervo INTEGER NOT NULL DEFAULT 0,

    origem TEXT NOT NULL DEFAULT 'MANUAL',
    origem_chave TEXT,
    importacao_id INTEGER,
    selo_texto TEXT,
    selo_qr TEXT,
    selo_qr_mime TEXT,
    selo_qr_2 TEXT,
    selo_qr_2_mime TEXT,
    emolumentos TEXT,

    hash_ato TEXT NOT NULL,
    hash_anterior TEXT,
    lavrado_em TEXT NOT NULL,
    lavrado_por INTEGER,
    UNIQUE(matricula_id, tipo, numero),
    FOREIGN KEY(matricula_id) REFERENCES ri_matriculas(id),
    FOREIGN KEY(cancelado_por_ato_id) REFERENCES ri_atos(id),
    FOREIGN KEY(lavrado_por) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_ri_ato_matricula ON ri_atos(matricula_id, tipo, numero);

CREATE TABLE IF NOT EXISTS ri_partes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matricula_id INTEGER NOT NULL,
    ato_id INTEGER,
    nome TEXT NOT NULL,
    documento_tipo TEXT,
    documento_numero TEXT,
    documento_valido INTEGER,
    qualificacao TEXT,
    papel TEXT,
    proprietario INTEGER NOT NULL DEFAULT 0,
    proprietario_ativo INTEGER NOT NULL DEFAULT 0,
    participacao TEXT,
    origem TEXT NOT NULL DEFAULT 'MANUAL',
    origem_chave TEXT,
    FOREIGN KEY(matricula_id) REFERENCES ri_matriculas(id),
    FOREIGN KEY(ato_id) REFERENCES ri_atos(id)
);

CREATE INDEX IF NOT EXISTS ix_ri_parte_matricula ON ri_partes(matricula_id);
CREATE INDEX IF NOT EXISTS ix_ri_parte_doc ON ri_partes(documento_numero);
CREATE INDEX IF NOT EXISTS ix_ri_parte_nome ON ri_partes(nome);

CREATE TABLE IF NOT EXISTS ri_imagens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matricula_id INTEGER NOT NULL,
    nome_arquivo TEXT,
    caminho TEXT,
    ordem INTEGER,
    sha256 TEXT,
    ficha_digitalizada INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(matricula_id) REFERENCES ri_matriculas(id)
);

CREATE TABLE IF NOT EXISTS ri_numeracao (
    livro TEXT PRIMARY KEY,
    proximo_numero INTEGER NOT NULL,
    maior_em_uso INTEGER,
    fixado_em TEXT,
    fixado_por INTEGER,
    observacao TEXT,
    FOREIGN KEY(fixado_por) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS ri_expurgos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matricula_id INTEGER,
    matricula_numero TEXT,
    ato_rotulo TEXT NOT NULL,
    ato_tipo TEXT,
    ato_numero INTEGER,
    ato_data TEXT,
    ato_natureza TEXT,
    ato_selo TEXT,
    selo_cancelado TEXT,
    ato_hash TEXT,
    ato_teor TEXT,
    partes_json TEXT,
    motivo TEXT NOT NULL,
    ata TEXT NOT NULL,
    expurgado_em TEXT NOT NULL,
    expurgado_por TEXT
);

CREATE TABLE IF NOT EXISTS ri_modelos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL,
    corpo TEXT NOT NULL,
    formato TEXT NOT NULL DEFAULT 'odt',
    ativo INTEGER NOT NULL DEFAULT 1,
    versao INTEGER NOT NULL DEFAULT 1,
    atualizado_em TEXT,
    atualizado_por INTEGER,
    FOREIGN KEY(atualizado_por) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS ri_importacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    iniciada_em TEXT NOT NULL,
    concluida_em TEXT,
    usuario_id INTEGER,
    origem TEXT NOT NULL,
    arquivo TEXT,
    matriculas_lidas INTEGER NOT NULL DEFAULT 0,
    matriculas_gravadas INTEGER NOT NULL DEFAULT 0,
    atos_lidos INTEGER NOT NULL DEFAULT 0,
    atos_gravados INTEGER NOT NULL DEFAULT 0,
    partes_lidas INTEGER NOT NULL DEFAULT 0,
    partes_gravadas INTEGER NOT NULL DEFAULT 0,
    rejeitados INTEGER NOT NULL DEFAULT 0,
    relatorio TEXT,
    FOREIGN KEY(usuario_id) REFERENCES users(id)
);

-- Livro 1 - Protocolo. A prenotacao e o que fixa a prioridade do titulo:
-- entre dois titulos sobre o mesmo imovel, prevalece o prenotado primeiro.
CREATE TABLE IF NOT EXISTS ri_protocolos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero INTEGER NOT NULL,
    livro TEXT NOT NULL DEFAULT '1A',
    data_prenotacao TEXT NOT NULL,
    hora TEXT,
    apresentante TEXT,
    apresentante_documento TEXT,
    natureza_titulo TEXT,
    objeto TEXT,
    matricula_id INTEGER,
    matricula_numero TEXT,
    data_limite TEXT,
    data_reingresso TEXT,
    situacao TEXT NOT NULL DEFAULT 'ABERTO',
    ato_id INTEGER,
    selo_prenotacao TEXT,
    suscitacao_duvida TEXT,
    anotacao TEXT,
    origem TEXT NOT NULL DEFAULT 'MANUAL',
    origem_chave TEXT,
    importacao_id INTEGER,
    criado_em TEXT NOT NULL,
    criado_por INTEGER,
    UNIQUE(livro, numero),
    FOREIGN KEY(matricula_id) REFERENCES ri_matriculas(id),
    FOREIGN KEY(ato_id) REFERENCES ri_atos(id),
    FOREIGN KEY(criado_por) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_ri_prot_situacao ON ri_protocolos(situacao, data_limite);
CREATE INDEX IF NOT EXISTS ix_ri_prot_matricula ON ri_protocolos(matricula_id);

-- Central Nacional de Indisponibilidade de Bens.
-- Copia local para consulta previa: uma ordem com cancelamento registrado
-- deixa de valer, por isso 'ativa' e derivada, nao informada.
-- O ATO ANTES DE SER ATO. Os dois debitos do balcao — «pre-visualizar matricula
-- com o ato novo» e «rascunho de ato sem consumir numero» — sao um so.
--
--   TABELA PROPRIA, E NAO UMA SITUACAO EM `ri_atos`. Medido em 28/08/2026:
--   `ri_atos` NAO TEM coluna de situacao, e todo ato entra ja tomando o numero
--   (`MAX(numero)+1`) e entrando na CORRENTE DE HASH, que e o que prova que
--   nenhum ato foi mexido depois. Rascunho ali dentro seria um ato que existe e
--   nao devia: ou ocupa numero alheio, ou quebra a corrente ao ser apagado.
--
--   UM POR MATRICULA (`UNIQUE`): dois rascunhos abertos na mesma ficha fariam
--   o escrevente lavrar o errado, e no RI lavrar o errado nao se desfaz.
-- OS MODELOS DOS PAPEIS QUE A CASA EMITE — relato #28 do oficial:
-- «preciso ter controle geral sobre os modelos, em especial os cabecalhos
--  padrao de cada atribuicao e ato, corpo, encerramento, eventual notas de
--  rodape».
--
--   UMA TABELA SO, DAS SEIS ATRIBUICOES. Espalhar por `ri_modelos`,
--   `cx_modelos` e outros daria quatro telas, e a pergunta «onde eu mudo o
--   cabecalho?» continuaria sem resposta — que e o relato.
--
--   E ELA GUARDA O AJUSTE, E NAO O PADRAO. O texto de fabrica mora no codigo
--   (`modelos_da_casa.CATALOGO` diz onde), e sem linha aqui o papel sai do
--   jeito de fabrica. Assim nada se perde, «voltar ao padrao» e apagar a
--   linha, e instalacao nova ja nasce funcionando sem carga de modelos.
--
--   Medido em 29/08/2026: dos dez papeis, QUATRO ja liam de tabela (e
--   `ri_modelos` esta com zero linhas) e CINCO estavam fixos no codigo — o
--   recibo, o orcamento e a recepcao do caixa, o traslado das notas e o
--   comprovante de prenotacao.
CREATE TABLE IF NOT EXISTS mo_modelos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chave TEXT NOT NULL,
    corpo TEXT NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1,
    atualizado_em TEXT NOT NULL,
    atualizado_por TEXT,
    UNIQUE(chave)
);

CREATE TABLE IF NOT EXISTS ri_rascunhos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matricula_id INTEGER NOT NULL,
    tipo TEXT NOT NULL,                  -- R | AV
    teor TEXT NOT NULL,
    modelo_codigo TEXT,
    natureza_titulo TEXT,
    protocolo TEXT,
    prenotacao TEXT,
    data_ato TEXT,
    criado_por TEXT,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    UNIQUE(matricula_id),
    FOREIGN KEY(matricula_id) REFERENCES ri_matriculas(id)
);

-- A MINUTA: o ato ESCRITO que ainda nao foi lavrado.
--
--   Ordem do oficial em 15/09/2026, sobre as tres averbacoes que a
--   importacao das minutas lavrou direto na matricula 3.110: «aquela av 4, 5
--   e 6 nao podem ficar como atos prontos, precisam ficar como atos para
--   serem revistos e lavrados».
--
-- POR QUE NAO E `ri_rascunhos`, que parece a mesma coisa e nao e:
--
--   1. CARDINALIDADE. Aquela tem `UNIQUE(matricula_id)` — **um** rascunho por
--      ficha, porque nasceu para a caixa de digitar da propria tela. A
--      importacao traz um PACOTE: a 3.110 chegou com tres de uma vez.
--   2. PROCEDENCIA. O rascunho e o que o operador esta escrevendo agora; a
--      minuta ja veio escrita, de um arquivo, e traz o **numero pretendido**
--      conforme o livro, que o rascunho nao tem.
--
--   As duas continuam existindo e cada uma diz a que veio. Fundi-las exigiria
--   derrubar o UNIQUE de uma tabela que a tela de rascunho usa — e a regra da
--   casa e que MIGRACOES e so `ALTER TABLE ADD COLUMN`.
--
-- O QUE ELA NAO FAZ: nao toma numero, nao entra na corrente de hash, nao
-- sela e nao cobra. Nada disso acontece antes de a minuta virar ato pela
-- tela de lavrar — que e a mesma de sempre, com os campos ja preenchidos.
CREATE TABLE IF NOT EXISTS ri_minutas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matricula_id INTEGER NOT NULL,
    tipo TEXT NOT NULL,                  -- R | AV
    numero_pretendido INTEGER,           -- o numero do livro, quando a minuta o traz
    data_pretendida TEXT,
    teor TEXT NOT NULL,
    natureza_titulo TEXT,
    protocolo TEXT,
    prenotacao TEXT,
    modelo_codigo TEXT,
    -- DE ONDE ELA VEIO. `DESFEITO_DE_ATO` e a minuta que voltou de um ato que
    -- nao devia ter sido lavrado — e `origem_chave` guarda qual era, para a
    -- conferencia depois saber que aquele numero ja esteve ocupado.
    origem TEXT NOT NULL DEFAULT 'MANUAL',
    origem_chave TEXT,
    observacao TEXT,
    situacao TEXT NOT NULL DEFAULT 'A_REVISAR',   -- A_REVISAR | LAVRADA | DESCARTADA
    ato_id INTEGER,                      -- preenchido quando vira ato
    criado_em TEXT NOT NULL,
    criado_por TEXT,
    atualizado_em TEXT,
    atualizado_por TEXT,
    FOREIGN KEY(matricula_id) REFERENCES ri_matriculas(id)
);

CREATE INDEX IF NOT EXISTS ix_ri_minutas_ficha
    ON ri_minutas(matricula_id, situacao);

-- AS PARTES DA MINUTA — 16/09/2026, e ela nasceu de um estrago medido.
--
--   O oficial mandou devolver a AV-05 da 3.110 a condicao de minuta. A
--   ferramenta apagou o ato e, com ele, as `ri_partes` — e `ri_minutas`
--   **nao tinha onde guardar parte nenhuma** (as 19 colunas dela nao tinham
--   uma so). A minuta voltou para a fila com o teor inteiro e sem as duas
--   partes; ao ser lavrada de novo, o ato nasceu sem elas, e o envelope do
--   selo **exige `nomesPartes`**: «O ato foi lavrado SEM SELO: Os nomes das
--   partes devem ser informados.»
--
--   E ISSO VIROU PRECONDICAO DE OUTRA ORDEM DELE, no mesmo dia: «selo
--   recusado suspende ato (fica salvo como minuta para lavrar de novo)».
--   Sem as partes, o ato suspenso voltaria a minuta, seria lavrado de novo,
--   o selo falharia pelo mesmo motivo — e o circulo nao fecharia nunca.
--
-- TABELA PROPRIA, E NAO COLUNA EM `ri_minutas`: sao varias por minuta, e a
-- regra da casa e que tabela nova entra no SCHEMA como `CREATE TABLE IF NOT
-- EXISTS` — `MIGRACOES` e so `ALTER TABLE ADD COLUMN`.
--
-- AS COLUNAS SAO AS DE `ri_partes` QUE A LAVRATURA LE, e nao todas: a tela de
-- lavrar manda cinco campos por parte — `parte_nome`, `parte_documento` e
-- `parte_papel` (visiveis) mais `parte_qualificacao` e `parte_documento_tipo`
-- (escondidos, porque a tela nao os edita mas a parte que volta de um ato
-- suspenso os traz) —, e e isso que precisa sobreviver a ida e volta.
-- `proprietario_ativo` NAO vem junto, de proposito: quem e dono ATUAL se
-- decide ao lavrar, e nao na minuta.
CREATE TABLE IF NOT EXISTS ri_minuta_partes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    minuta_id INTEGER NOT NULL,
    nome TEXT NOT NULL,
    documento_tipo TEXT,
    documento_numero TEXT,
    qualificacao TEXT,
    papel TEXT,
    ordem INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(minuta_id) REFERENCES ri_minutas(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_ri_minuta_partes_minuta
    ON ri_minuta_partes(minuta_id, ordem);

CREATE TABLE IF NOT EXISTS ri_cnib_ordens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    protocolo_cnib TEXT NOT NULL,
    data_pedido TEXT,
    processo TEXT,
    instituicao TEXT,
    forum_vara TEXT,
    solicitante TEXT,
    cancelamento_protocolo TEXT,
    cancelamento_data TEXT,
    ativa INTEGER NOT NULL DEFAULT 1,
    origem_chave TEXT
);

CREATE TABLE IF NOT EXISTS ri_cnib_pessoas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ordem_id INTEGER NOT NULL,
    nome TEXT,
    documento TEXT,
    origem_chave TEXT,
    FOREIGN KEY(ordem_id) REFERENCES ri_cnib_ordens(id)
);

-- O OKAY DO CARTORIO SOBRE CADA ORDEM DA CNIB.
--
--   Decisao do oficial em 28/08/2026: «avisar e preparar a averbacao, ficando
--   pendente okay do cartorio». O sistema deixa o texto pronto; quem assina
--   decide — e a decisao FICA, senao a mesma linha volta amanha e na terceira
--   vez ninguem le mais.
--
--   A chave e (matricula, protocolo, pessoa): a mesma ordem pode atingir duas
--   matriculas, e a mesma matricula pode ser atingida por duas ordens.
CREATE TABLE IF NOT EXISTS ri_cnib_decisoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matricula_id INTEGER NOT NULL,
    protocolo_cnib TEXT NOT NULL,
    pessoa_nome TEXT,
    pessoa_documento TEXT,
    criterio TEXT,                    -- 'documento' ou 'nome'
    decisao TEXT NOT NULL,            -- AVERBADA | NAO_E_A_PESSOA
    motivo TEXT,
    ato_id INTEGER,
    decidido_por TEXT,
    decidido_em TEXT NOT NULL,
    FOREIGN KEY(matricula_id) REFERENCES ri_matriculas(id),
    UNIQUE(matricula_id, protocolo_cnib, pessoa_documento, pessoa_nome)
);

CREATE INDEX IF NOT EXISTS ix_cnib_dec_mat ON ri_cnib_decisoes(matricula_id);

-- A CONSULTA CNIB QUE SUSTENTOU CADA ATO LAVRADO (TJMA 506).
--
--   Gravada na mesma transacao do ato: quem, quando, contra qual base (copia
--   local ate tal data, ou protocolo da Central), quais CPF/CNPJ e nomes, e o
--   que voltou. `ato_id` SEM chave estrangeira de proposito: o ato que o selo
--   suspende volta a ser minuta e a linha de `ri_atos` sai; a consulta
--   aconteceu e fica, com `ato_id` NULL, presa a matricula.
CREATE TABLE IF NOT EXISTS ri_atos_cnib (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ato_id INTEGER,
    matricula_id INTEGER NOT NULL,
    ato_rotulo TEXT,
    fonte TEXT NOT NULL,              -- COPIA_LOCAL | CENTRAL
    base_ate TEXT,
    protocolo_consulta TEXT,
    documentos TEXT,                  -- JSON
    nomes TEXT,                       -- JSON
    resultado TEXT NOT NULL,          -- NADA_CONSTA | POSITIVO
    ordens TEXT,                      -- JSON
    consultado_por TEXT,
    consultado_em TEXT NOT NULL,
    FOREIGN KEY(matricula_id) REFERENCES ri_matriculas(id)
);

CREATE INDEX IF NOT EXISTS ix_ri_atos_cnib_ato ON ri_atos_cnib(ato_id);
CREATE INDEX IF NOT EXISTS ix_ri_atos_cnib_mat ON ri_atos_cnib(matricula_id);

CREATE INDEX IF NOT EXISTS ix_cnib_doc ON ri_cnib_pessoas(documento);
CREATE INDEX IF NOT EXISTS ix_cnib_nome ON ri_cnib_pessoas(nome);
CREATE INDEX IF NOT EXISTS ix_cnib_ordem ON ri_cnib_pessoas(ordem_id);

-- CADA IDA DO ATUALIZADOR A CENTRAL, INCLUSIVE AS QUE DERAM ERRADO.
--
--   ELA E A UNICA RESPOSTA HONESTA PARA «ATE QUANDO ESTA COPIA VALE». A tela
--   respondia isso com `MAX(data_pedido)`, e isso deixou de bastar quando a
--   Central passou a responder: a janela filtra pela data da ATIVIDADE, e uma
--   janela de junho/2026 devolveu ordem com `datapedido` de 2012, porque o
--   que se moveu foi o cancelamento. Pela data do pedido, aquela leitura teria
--   ENVELHECIDO a copia.
--
--   E AS QUE DERAM ERRADO FICAM. Sem elas, «nao ha ordem nova» e «faz uma
--   semana que nao se fala com a Central» viram a mesma tela — e a segunda e
--   a que precisa de gente.
CREATE TABLE IF NOT EXISTS ri_cnib_leituras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    de TEXT NOT NULL,
    ate TEXT NOT NULL,
    pedida_em TEXT NOT NULL,
    terminada_em TEXT,
    situacao TEXT NOT NULL DEFAULT 'PEDIDA',   -- PEDIDA | OK | VAZIA | RECUSADA | ERRO
    lidas INTEGER NOT NULL DEFAULT 0,
    novas INTEGER NOT NULL DEFAULT 0,
    atualizadas INTEGER NOT NULL DEFAULT 0,
    canceladas INTEGER NOT NULL DEFAULT 0,
    paginas INTEGER NOT NULL DEFAULT 0,
    parou_no_teto INTEGER NOT NULL DEFAULT 0,
    mensagem TEXT,
    automatica INTEGER NOT NULL DEFAULT 0,
    pedida_por INTEGER,
    FOREIGN KEY(pedida_por) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_cnib_leitura_janela ON ri_cnib_leituras(de, ate);
CREATE INDEX IF NOT EXISTS ix_cnib_leitura_dia ON ri_cnib_leituras(pedida_em);

-- Certidoes emitidas. O corpo e CONGELADO no momento da emissao: a certidao
-- retrata a matricula como ela estava naquele instante. Se a matricula receber
-- ato novo depois, a certidao ja expedida nao pode mudar - ela circula no mundo
-- e alguem confiou nela.
CREATE TABLE IF NOT EXISTS ri_certidoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero INTEGER NOT NULL,
    ano INTEGER NOT NULL,
    tipo TEXT NOT NULL,
    matricula_id INTEGER,
    matricula_numero TEXT,
    requerente TEXT,
    requerente_documento TEXT,
    finalidade TEXT,
    data_emissao TEXT NOT NULL,
    validade_ate TEXT,
    corpo TEXT,
    corpo_formato TEXT NOT NULL DEFAULT 'html',
    protocolo TEXT,
    selo_texto TEXT,
    selo_qr TEXT,
    selo_qr_mime TEXT,
    emolumentos TEXT,
    hash_certidao TEXT,
    cancelada INTEGER NOT NULL DEFAULT 0,
    motivo_cancelamento TEXT,
    cancelada_em TEXT,
    cancelada_por TEXT,
    declaracao_selo_tjma_em TEXT,
    declaracao_selo_tjma_por TEXT,
    origem TEXT NOT NULL DEFAULT 'MANUAL',
    origem_chave TEXT,
    importacao_id INTEGER,
    emitida_em TEXT NOT NULL,
    emitida_por INTEGER,
    FOREIGN KEY(matricula_id) REFERENCES ri_matriculas(id),
    FOREIGN KEY(emitida_por) REFERENCES users(id)
);

-- A unicidade vale so para o que ESTA serventia emite. As certidoes herdadas
-- do E-Oficio sao identificadas por protocolo + sequencia dentro dele, e la o
-- mesmo numero de sequencia se repete em protocolos diferentes: dos 368
-- registros existem apenas 7 valores distintos de sequencia. Forcar numero
-- unico nelas obrigaria a inventar numeracao, e certidao ja expedida nao se
-- renumera.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ri_cert_numero_ano
    ON ri_certidoes(numero, ano) WHERE origem = 'MANUAL';
CREATE INDEX IF NOT EXISTS ix_ri_cert_protocolo ON ri_certidoes(protocolo, numero);

CREATE INDEX IF NOT EXISTS ix_ri_cert_matricula ON ri_certidoes(matricula_id);
CREATE INDEX IF NOT EXISTS ix_ri_cert_data ON ri_certidoes(data_emissao);

-- Nota devolutiva: a qualificacao negativa do titulo.
-- Vinculada ao protocolo, porque e a prenotacao que corre enquanto o
-- interessado cumpre as exigencias - e o reingresso no prazo aproveita o
-- mesmo numero de ordem (Codigo TJMA, art. 44).
CREATE TABLE IF NOT EXISTS ri_notas_devolutivas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    protocolo_id INTEGER NOT NULL,
    numero INTEGER NOT NULL,
    data_nota TEXT NOT NULL,
    exigencias TEXT NOT NULL,
    fundamentacao TEXT,
    prazo_ate TEXT,
    situacao TEXT NOT NULL DEFAULT 'ABERTA',
    data_reingresso TEXT,
    observacao_reingresso TEXT,
    emitida_em TEXT NOT NULL,
    emitida_por INTEGER,
    FOREIGN KEY(protocolo_id) REFERENCES ri_protocolos(id),
    FOREIGN KEY(emitida_por) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_ri_nota_protocolo ON ri_notas_devolutivas(protocolo_id);

CREATE TABLE IF NOT EXISTS ri_rejeitados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    importacao_id INTEGER NOT NULL,
    entidade TEXT NOT NULL,
    chave_origem TEXT,
    motivo TEXT NOT NULL,
    conteudo TEXT,
    FOREIGN KEY(importacao_id) REFERENCES ri_importacoes(id)
);

-- Quem respondia pela serventia em cada periodo.
--
-- POR QUE ISTO EXISTE
--   A ficha impressa tem de dizer quem praticou cada ato. Os atos do acervo
--   foram lavrados por delegatarios anteriores, e imprimir o nome de quem
--   esta hoje na serventia seria atribuir a uma pessoa ato que ela nao
--   praticou. O periodo resolve o ato antigo; o nome gravado no proprio ato
--   resolve o ato novo.
CREATE TABLE IF NOT EXISTS ri_delegatarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    cargo TEXT NOT NULL DEFAULT 'TITULAR',   -- TITULAR | SUBSTITUTO | INTERINO | ESCREVENTE
    tratamento TEXT NOT NULL DEFAULT 'O',    -- O | A  (concordancia: "O Tabeliao" / "A Tabelia")
    titulo TEXT,                             -- como assina: "Tabeliao Registrador", "Tabelia Registradora Substituta"
    inicio TEXT,                             -- AAAA-MM-DD; vazio = desde sempre
    fim TEXT,                                -- AAAA-MM-DD; vazio = ate hoje
    confirmado INTEGER NOT NULL DEFAULT 0,   -- 0 = periodo ainda nao conferido por gente
    observacao TEXT,
    criado_em TEXT,
    criado_por INTEGER,
    FOREIGN KEY(criado_por) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS ix_ri_deleg_periodo ON ri_delegatarios(inicio, fim);

-- CTP - Comunicacao de Transacoes as Prefeituras (CENSEC / CNB-CF).
-- Uma remessa por competencia mensal. A competencia e unica de proposito: o
-- fechamento da carga na CENSEC e mensal, e duas remessas do mesmo mes seriam
-- duas comunicacoes do mesmo fato.
CREATE TABLE IF NOT EXISTS ri_ctp_remessas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competencia TEXT NOT NULL,
    situacao TEXT NOT NULL DEFAULT 'ABERTA',
    quantidade INTEGER NOT NULL DEFAULT 0,
    sem_transacoes INTEGER NOT NULL DEFAULT 0,
    arquivo_nome TEXT,
    arquivo_hash TEXT,
    conteudo TEXT,
    observacao TEXT,
    gerado_em TEXT,
    gerado_por INTEGER,
    fechado_em TEXT,
    fechado_por INTEGER,
    UNIQUE(competencia),
    FOREIGN KEY(gerado_por) REFERENCES users(id),
    FOREIGN KEY(fechado_por) REFERENCES users(id)
);

-- Os dados que a CTP exige e a matricula nao tem (valor do negocio, base de
-- calculo do ITBI, forma de pagamento) sao digitados aqui, por ato, e ficam
-- guardados. Nao vao para o teor do ato: teor lavrado nao se altera.
CREATE TABLE IF NOT EXISTS ri_ctp_itens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competencia TEXT NOT NULL,
    ato_id INTEGER NOT NULL,
    matricula_id INTEGER NOT NULL,
    operacao TEXT,
    dados TEXT,
    incluir INTEGER NOT NULL DEFAULT 1,
    atualizado_em TEXT,
    atualizado_por INTEGER,
    UNIQUE(competencia, ato_id),
    FOREIGN KEY(ato_id) REFERENCES ri_atos(id),
    FOREIGN KEY(matricula_id) REFERENCES ri_matriculas(id)
);
CREATE INDEX IF NOT EXISTS ix_ri_ctp_itens_comp ON ri_ctp_itens(competencia);

-- DOI — Declaracao sobre Operacoes Imobiliarias, para a Receita Federal.
--
-- TABELA SEPARADA DA CTP, E OS ITENS COMPARTILHADOS.
--     A CTP vai a CENSEC e dali aos municipios; a DOI vai a Receita. Sao
--     obrigacoes diferentes, com prazos diferentes e recibos diferentes — por
--     isso duas remessas. Mas o que o operador DIGITA (valor do negocio, base
--     de calculo, forma de pagamento) e o mesmo, e fica so em ri_ctp_itens:
--     digitar duas vezes seria pedir para as duas divergirem.
--
-- `negativa` E O QUE A INSPECAO COBRA.
--     O AUDITUS pede "comprovacoes de DOI OU DECLARACOES NEGATIVAS dos meses
--     sem atos imobiliarios". O mes sem ato tambem precisa de prova, e e o que
--     mais escapa, porque nao aparece em lista nenhuma por estar vazio.
CREATE TABLE IF NOT EXISTS ri_doi_remessas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competencia TEXT NOT NULL,
    situacao TEXT NOT NULL DEFAULT 'ABERTA',
    quantidade INTEGER NOT NULL DEFAULT 0,
    negativa INTEGER NOT NULL DEFAULT 0,
    prazo TEXT,                           -- ultimo dia util do mes seguinte
    arquivo_nome TEXT,
    arquivo_hash TEXT,
    conteudo TEXT,
    recibo TEXT,                          -- o que a DOI-Web devolve
    protocolo TEXT,
    observacao TEXT,
    gerado_em TEXT,
    gerado_por INTEGER,
    entregue_em TEXT,
    entregue_por INTEGER,
    UNIQUE(competencia),
    FOREIGN KEY(gerado_por) REFERENCES users(id),
    FOREIGN KEY(entregue_por) REFERENCES users(id)
);


-- O QUE FALTA CONFERIR NUM ATO, E QUE NAO PODE MORAR NUMA CONVERSA
--
-- O ato entra no sistema para ser revisto e selado aqui. O que a revisao
-- apontou — «esta area foi retificada em 35%», «o remanescente nao foi
-- apurado» — nao pode ficar num .docx nem num recado: some, e quem sela
-- semanas depois nao sabe que havia o que olhar.
--
-- A NOTA NAO TRAVA NADA, e isso e deliberado. Quando ela existe o ato ja
-- esta lavrado, e recusar ou desfazer ato e decisao do delegatario, nunca
-- de uma lista — e a regra do CNIB, das fraudes e do usucapiao pela oitava
-- vez. O que ela faz e nao deixar esquecer: a ficha mostra as abertas ao
-- lado do teor, e ha tela com todas.
--
-- BAIXAR EXIGE ESCREVER O QUE SE DECIDIU. Sem isso a baixa seria um clique
-- que apaga a pergunta sem responde-la, e a correicao, meses depois, leria
-- «conferido» sem saber conferido como. E a mesma razao da dispensa com
-- motivo escrito do usucapiao.
CREATE TABLE IF NOT EXISTS ri_revisoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matricula_id INTEGER NOT NULL,
    ato_id INTEGER,
    assunto TEXT NOT NULL,
    nota TEXT NOT NULL,
    origem TEXT NOT NULL DEFAULT 'MANUAL',
    situacao TEXT NOT NULL DEFAULT 'ABERTA',
    anotada_em TEXT NOT NULL,
    anotada_por INTEGER,
    baixada_em TEXT,
    baixada_por INTEGER,
    baixa_decisao TEXT,
    FOREIGN KEY(matricula_id) REFERENCES ri_matriculas(id),
    FOREIGN KEY(ato_id) REFERENCES ri_atos(id),
    FOREIGN KEY(anotada_por) REFERENCES users(id),
    FOREIGN KEY(baixada_por) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_ri_revisao_matricula
    ON ri_revisoes(matricula_id, situacao);
CREATE INDEX IF NOT EXISTS ix_ri_revisao_ato ON ri_revisoes(ato_id);

-- A QUALIFICACAO DO TITULO PRENOTADO — 12/10/2026, pedido do oficial («saber
-- o que esta pendente de qualificacao e o que esta pendente de registro»).
--
--   A decisao de qualificar nao tinha onde ficar: a positiva nao existia em
--   coluna nenhuma, e a negativa era so a nota. Medido na producao: 31
--   prenotacoes abertas, nenhuma dizendo em que pe estava o titulo.
--
--   E A FORMA DE `rg_qualificacoes` (RTD/RCPJ): uma linha por qualificacao,
--   com a ordem, POSITIVA ou NEGATIVA. A NEGATIVA aponta a nota devolutiva
--   que a escreveu — a nota e a exigencia; esta linha e a decisao. A etapa do
--   pedido NAO se grava: ela se calcula daqui, do ato e do prazo
--   (`ri_pedidos.etapa`).
CREATE TABLE IF NOT EXISTS ri_qualificacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    protocolo_id INTEGER NOT NULL,
    ordem INTEGER NOT NULL,
    resultado TEXT NOT NULL,              -- POSITIVA | NEGATIVA
    fundamentacao TEXT,
    nota_id INTEGER,                      -- so na NEGATIVA: a nota que a escreveu
    data_qualificacao TEXT NOT NULL,
    qualificada_por TEXT,
    criado_em TEXT NOT NULL,
    criado_por INTEGER,
    UNIQUE(protocolo_id, ordem),
    FOREIGN KEY(protocolo_id) REFERENCES ri_protocolos(id),
    FOREIGN KEY(nota_id) REFERENCES ri_notas_devolutivas(id),
    FOREIGN KEY(criado_por) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_ri_qualificacoes_protocolo
    ON ri_qualificacoes(protocolo_id, ordem);
"""


# Colunas acrescentadas depois que o modulo ja estava em producao. Como o
# SCHEMA usa CREATE TABLE IF NOT EXISTS, tabela existente nao ganharia campo
# novo - por isso a migracao explicita.
MIGRACOES = (
    ("ri_certidoes", "cancelada_em", "TEXT"),
    ("ri_certidoes", "cancelada_por", "TEXT"),
    ("ri_certidoes", "declaracao_selo_tjma_em", "TEXT"),
    ("ri_certidoes", "declaracao_selo_tjma_por", "TEXT"),
    # A FORMA NORMALIZADA DO NOME DA PESSOA DO CNIB.
    #
    #   Sem ela a busca por nome comparava `UPPER(p.nome)` do SQLite com o
    #   `.upper()` do Python, e os dois nao sao a mesma coisa: `UPPER('josé')`
    #   no SQLite devolve `JOSé`, porque `UPPER` ali e ASCII. Medido em
    #   28/08/2026: `ri_partes` tem **1.257** nomes acentuados, e nenhum deles
    #   jamais acharia a ordem correspondente.
    #
    #   A funcao e a `normalizar_busca` DESTE modulo — a mesma que preenche
    #   `ri_partes.nome_norm`, do outro lado da comparacao. Trazer a de outro
    #   modulo poria dois normalizadores no mesmo arquivo, e onde a igualdade
    #   importa ela tem de ser construida, e nao suposta.
    #
    #   E a coluna tambem e o que torna a busca VIAVEL: comparar 50.054 nomes
    #   passando cada um por uma funcao Python, para cada uma das 1.701
    #   matriculas, sao 85 milhoes de chamadas. Com a coluna e um indice, e uma
    #   consulta.
    ("ri_cnib_pessoas", "nome_norm", "TEXT"),
    # O LIVRO DE DESTINO DO TITULO — pedido do oficial em 27/08/2026: «em vez
    # de campo livre, uma caixa de selecao: livro 2 (matriculas) ou livro 3
    # (demais atos do RI)».
    #
    # E CAMPO NOVO, E NAO O `livro` QUE JA EXISTIA. Medindo para atende-lo
    # descobri que `ri_protocolos.livro` nao e o livro de destino: e o **Livro
    # 1-A de Protocolo**, e esta `1A` em **783 dos 784** registros. A unica
    # linha com `2` e alguem tendo digitado no campo livre — que e exatamente o
    # defeito apontado. O selo confirma: `livro: "1A"` em **829 de 829**
    # envelopes de `/selo/imovel/prenotacao`.
    #
    # Entao sao duas coisas diferentes, e passam a ter dois campos: o de
    # protocolo, que nao se escolhe, e o de destino, que se escolhe entre dois.
    ("ri_protocolos", "livro_destino", "TEXT"),
    # Encerramento desfeito. NAO e "apagar o encerramento": e registrar que
    # houve um, que foi errado, e por que se voltou atras. Prenotacao e ato de
    # livro; correcao de ato de livro se documenta, nao se esconde.
    ("ri_protocolos", "reaberto_em", "TEXT"),
    ("ri_protocolos", "reaberto_por", "TEXT"),
    ("ri_protocolos", "motivo_reabertura", "TEXT"),
    ("ri_protocolos", "situacao_anterior", "TEXT"),
    # A MARCA REURB-S, que a tela lia e jogava fora.
    #
    #   O prazo da prenotacao e de 20 dias uteis, ou **40 na REURB-S** (Lei
    #   6.015/1973, art. 205, e Codigo de Normas do TJMA arts. 436 e 452). A
    #   tela ja perguntava, ja calculava os 40 — e nao guardava a resposta.
    #
    #   O PRAZO FICAVA SEM EXPLICAR POR QUE. Seis meses depois, quem olhasse
    #   uma prenotacao com 40 dias nao teria como saber se era REURB-S ou se
    #   alguem digitou a data errada; e numa correicao a pergunta e exatamente
    #   essa. Dado que muda a consequencia e nao fica guardado e dado que
    #   ninguem consegue conferir.
    ("ri_protocolos", "reurb", "INTEGER"),
    # Modalidade REURB: S | E | MISTO (30/09/2026). `reurb=1` continua = S (prazo 40).
    ("ri_protocolos", "reurb_tipo", "TEXT"),
    ("ri_atos", "selo_texto", "TEXT"),
    ("ri_atos", "selo_qr", "TEXT"),
    ("ri_atos", "selo_qr_mime", "TEXT"),
    ("ri_atos", "selo_qr_2", "TEXT"),
    ("ri_atos", "selo_qr_2_mime", "TEXT"),
    ("ri_atos", "emolumentos", "TEXT"),
    # O QUE O SELO AUTOMATICO DO ATO PRECISA, e que o ato nao guardava —
    # 14/09/2026, quando o selador passou a sair de dentro do sistema.
    #
    #   `/selo/imovel/ato-declarado/com-valor` manda `baseCalculo`, e
    #   `sem-valor` nao manda. **E o valor que escolhe o caminho**, entao ele
    #   precisa estar gravado no ato: sem isso, um ato que ficou sem selo
    #   (selador fora do ar) nao teria como ser selado depois pelo mesmo
    #   caminho — e o segundo selo sairia por um caminho diferente do primeiro.
    #
    #   EM CENTAVOS INTEIROS, como todo dinheiro desta casa (`ra_registros.
    #   valor_centavos`, `cx_lancamentos`): «dinheiro em ponto flutuante erra».
    #   A conversao para o `float` que o selador quer acontece no envelope, num
    #   lugar so.
    ("ri_atos", "base_calculo_centavos", "INTEGER"),
    # O ITEM DA TABELA DE CUSTAS ESCOLHIDO, e ele nao sai do tipo do ato: nos
    # 120 envelopes medidos o mesmo `sem-valor` saiu com 16.22.2, 16.5, 16.9,
    # 16.22.4, 16.24.1 e 16.2. Quem escolhe e quem atende, e o que ele escolheu
    # fica escrito — numa correicao a pergunta e por que se cobrou aquele item.
    ("ri_atos", "codigo_tj", "TEXT"),
    # O ATO GRATUITO, E O MOTIVO ESCRITO — 14/09/2026, pedido do oficial:
    # «permitir emissao de registros com gratuidade (assinalando que e excecao
    # dentro do RI)».
    #
    #   **A MARCA SOZINHA NAO SERVE, E O MOTIVO E A RAZAO DE ELA EXISTIR.** Um
    #   `1` na coluna diz que nao se cobrou; numa correicao a pergunta e POR
    #   QUE nao se cobrou, e essa resposta so existe escrita. E a mesma regra
    #   do `livro_a_confirmar` do civil, que e TEXTO e nao `1` pelo mesmo
    #   motivo: quem ler daqui a cinco anos precisa saber.
    #
    #   E ELE VAI DENTRO DO SELO: o aparelho grava `motivoIsentoGratuito` e o
    #   Tribunal o le na conferencia. Guardar aqui e guardar o que saiu.
    ("ri_atos", "isento", "INTEGER"),
    ("ri_atos", "motivo_isencao", "TEXT"),
    # SELO DE ARQUIVAMENTO OPCIONAL (16.39) — Beatriz 23/09/2026.
    # Coluna propria: `vincular_ao_ato` grava em `selo_texto`, e um segundo
    # selo no mesmo ato sobrescreveria o do registro/averbacao (mesmo
    # defeito medido no RCPJ Santa Isabel). Aqui fica o numero do 16.39;
    # `folhas_arquivamento` e a quantidade pedida ao aparelho.
    ("ri_atos", "selo_arquivamento", "TEXT"),
    ("ri_atos", "folhas_arquivamento", "INTEGER"),
    ("ri_matriculas", "selo_abertura_texto", "TEXT"),
    ("ri_matriculas", "selo_abertura_qr", "TEXT"),
    ("ri_matriculas", "selo_abertura_qr_mime", "TEXT"),
    ("ri_matriculas", "selo_abertura_qr_2", "TEXT"),
    ("ri_matriculas", "selo_abertura_qr_2_mime", "TEXT"),
    ("ri_matriculas", "emolumentos_abertura", "TEXT"),
    ("ri_protocolos", "selo_qr", "TEXT"),
    ("ri_protocolos", "selo_qr_mime", "TEXT"),
    # Caminho relativo a pasta de arquivos do proprio sistema. Guardado
    # separado do caminho de origem para que a copia interna sobreviva ao
    # desligamento do E-Oficio e acompanhe o backup.
    ("ri_imagens", "caminho_interno", "TEXT"),
    ("ri_imagens", "copiado_em", "TEXT"),
    ("ri_imagens", "bytes", "INTEGER"),
    # Busca sem acento e sem caixa. O SQLite nao remove acento sozinho, entao
    # guardamos a forma normalizada ao lado - indexavel e previsivel.
    ("ri_partes", "nome_norm", "TEXT"),
    ("ri_matriculas", "imovel_norm", "TEXT"),
    # Codigo do modelo usado na lavratura. Guardado para que a exportacao da
    # CTP saiba a operacao imobiliaria sem ter de adivinhar pelo texto livre
    # de natureza_titulo.
    ("ri_atos", "modelo_codigo", "TEXT"),
    # Quem praticou o ato, congelado no momento da lavratura. Nao se resolve
    # por periodo depois: se o cadastro de delegatarios for corrigido, o ato ja
    # lavrado tem de continuar dizendo o que dizia quando foi impresso.
    ("ri_atos", "lavrado_nome", "TEXT"),
    ("ri_atos", "lavrado_titulo", "TEXT"),
    ("ri_atos", "lavrado_tratamento", "TEXT"),
    # Contato e descricao do titulo apresentado. O comprovante de prenotacao
    # que fica com o apresentante tem de dizer o que foi entregue, e o
    # telefone e o que permite chamar quando a exigencia sai (Codigo de
    # Normas CGJ/MA, art. 447 — ciencia da nota devolutiva).
    ("ri_protocolos", "telefone", "TEXT"),
    ("ri_protocolos", "email", "TEXT"),
    ("ri_protocolos", "documento_descricao", "TEXT"),
    # A REABERTURA DA MATRICULA — pedido do oficial em 15/09/2026.
    #
    #   O encerramento era caminho de ida sem volta: havia rota para encerrar
    #   e NENHUMA para reabrir. Medido no dia: a matricula 3.110, encerrada
    #   pela AV-06 que veio das minutas importadas, ficou com os tres atos
    #   SEM SELO e sem um unico botao na ficha — «lavrar», «lavrar a partir
    #   de modelo» e «editar cadastro» estao todos atras de `nao encerrada`.
    #
    #   O QUE ESTAS TRES COLUNAS GUARDAM E POR QUE: sem elas, uma matricula
    #   reaberta fica identica a uma que nunca foi encerrada, com um ato de
    #   encerramento no meio da ficha e ninguem sabendo por que ela esta
    #   aberta. `motivo_encerramento` e `data_encerramento` NAO se apagam na
    #   reabertura — o encerramento aconteceu, e apagar o rastro dele seria o
    #   «carimbo que mente» pelo lado do silencio.
    ("ri_matriculas", "reaberta_em", "TEXT"),
    ("ri_matriculas", "reaberta_por", "TEXT"),
    ("ri_matriculas", "motivo_reabertura", "TEXT"),
    # QUEM ABRIU A MATRICULA ASSINA O PAPEL — 16/09/2026, pedido do oficial:
    # «precisa ter espaco pra quem abriu a matricula assinar».
    #
    #   AS TRES COLUNAS SAO AS DO ATO, e nao um desenho novo: `ri_atos`
    #   guarda `lavrado_nome`, `lavrado_titulo` e `lavrado_tratamento`
    #   **congelados na lavratura** — «se a funcao de quem assinou mudar
    #   amanha, este ato continua dizendo o que dizia hoje». A abertura
    #   e a mesma necessidade, e inventar outra forma aqui daria dois
    #   modos de responder «quem praticou?» na mesma ficha.
    #
    #   E ELAS NASCEM VAZIAS NAS 1.982 QUE JA EXISTEM, de proposito:
    #   `criado_por` esta NULL em 1.982 de 1.982 (a rota que abre
    #   matricula gravava `NULL` fixo), e nao ha de onde tirar o nome.
    #   O papel sai com a LINHA em branco para quem abriu assinar —
    #   «melhor faltar o nome do que atribuir o ato a quem nao o
    #   praticou», que e a regra que `fecho_do_ato` ja tem escrita.
    ("ri_matriculas", "aberta_nome", "TEXT"),
    ("ri_matriculas", "aberta_titulo", "TEXT"),
    ("ri_matriculas", "aberta_tratamento", "TEXT"),
    # POR QUE O ATO FOI CANCELADO, quando nao foi por averbacao.
    #
    #   Achado em 15/09/2026, ao rodar a suite: o caminho que cancela o ato
    #   quando o SELO NAO SAI e o operador nao marcou a autorizacao expressa
    #   (`ri_web.py`, o trecho de lavrar com minuta) escrevia
    #   `SET cancelado=1, motivo_cancelamento=?` — e `ri_atos` nao tinha essa
    #   coluna. `sqlite3.OperationalError: no such column` no caminho em que a
    #   resposta certa ja tinha sido decidida: em vez de cancelar o ato e dizer
    #   por que, o sistema devolvia erro, e o ato ficava no livro sem selo e
    #   sem marca de desfeito.
    #
    #   A coluna existe em treze tabelas de ato desta casa (`ri_certidoes`,
    #   `nt_*`, `at_certidoes`, `ra_*`), sempre com este nome. Criar um
    #   segundo nome aqui seria a quarta vez que a mesma palavra quer dizer
    #   duas coisas neste projeto.
    ("ri_atos", "motivo_cancelamento", "TEXT"),
    # Digitalizacao OFICIAL da matricula (arquivo atualizado no balcao).
    #
    #   Pedido de 16/09/2026: certidao de inteiro teor pode ser a reproducao
    #   da digitalizacao (com selo ao final) OU o texto extraido. O arquivo
    #   oficial mora nestas colunas; o historico fica em disco. ONR pendente
    #   marca que ha arquivo novo para enviar quando a integracao existir.
    ("ri_matriculas", "digi_path", "TEXT"),
    ("ri_matriculas", "digi_nome", "TEXT"),
    ("ri_matriculas", "digi_sha256", "TEXT"),
    ("ri_matriculas", "digi_em", "TEXT"),
    ("ri_matriculas", "digi_por", "TEXT"),
    ("ri_matriculas", "digi_onr_pendente", "INTEGER NOT NULL DEFAULT 0"),
    ("ri_matriculas", "digi_onr_em", "TEXT"),
    # Como a certidao foi montada: TEXTO (modelo) ou DIGITALIZACAO (scan).
    ("ri_certidoes", "fonte_corpo", "TEXT"),
    # QUEM ASSINA A CERTIDAO — 16/09/2026, pedido do oficial: «precisa
    # constar o nome e funcao do usuario logado».
    #
    #   **E `emitida_por` NAO SERVE PARA ISSO**: ela e INTEGER, com
    #   `FOREIGN KEY(emitida_por) REFERENCES users(id)`. A homonima do
    #   civil (`rc_certidoes.emitida_por`) e TEXT e guarda o nome — a
    #   mesma palavra querendo dizer coisas diferentes em duas tabelas,
    #   pela sexta vez neste projeto. Escrever o nome aqui estoura na
    #   chave estrangeira, e foi o banco que me corrigiu.
    #
    #   **SAO FOTOGRAFIA, e nao ponteiro**: a pessoa pode mudar de funcao
    #   amanha, e a certidao tem de continuar dizendo o que era verdade
    #   no dia em que foi expedida. Seguir o `users(id)` ao imprimir
    #   traria o nome de hoje para um papel de dois anos atras. E a mesma
    #   razao do `audit_logs.username_snapshot`.
    ("ri_certidoes", "emitida_por_nome", "TEXT"),
    ("ri_certidoes", "emitida_por_funcao", "TEXT"),
    ("ri_certidoes", "digi_path", "TEXT"),
    ("ri_certidoes", "digi_sha256", "TEXT"),
    # GRATUIDADE NA CERTIDAO DO RI — 23/09/2026 (Beatriz, matricula 582).
    # Espelho de ri_atos: isento + motivo_isencao. Sem marcar, cobrado
    # (comportamento de hoje). O motivo vai no selo (motivoIsentoGratuito).
    ("ri_certidoes", "isento", "INTEGER"),
    ("ri_certidoes", "motivo_isencao", "TEXT"),
    # A ORIGEM DA LINHA DO CNIB — 18/09/2026, e e ela que impede a carga do
    # E-Oficio de apagar o trabalho do atualizador.
    #
    #   A carga do espelho (`ri_web`, o trecho do `substituir`) grava por
    #   substituicao desde sempre, e as duas linhas do `DELETE` estavam SEM
    #   FILTRO: `DELETE FROM ri_cnib_ordens` apagava tudo, embora o
    #   comentario ao lado dissesse «remove so o que veio do E-Oficio».
    #   Medido em 18/09/2026: as 50.054 ordens do espelho vieram TODAS da
    #   carga — entao o defeito nunca apareceu, e apareceria no dia em que a
    #   Central trouxesse a primeira ordem nova, levando junto as que o
    #   atualizador acabou de gravar.
    #
    #   Sem estas colunas nao ha como separar as duas origens: a tabela nao
    #   tem de onde saber. `EOFICIO` e `CNIB` sao as duas palavras — a
    #   segunda e o que a Central e, e a primeira e o que as 50.054 linhas
    #   de hoje sao (o backfill logo abaixo as marca uma a uma).
    ("ri_cnib_ordens", "origem", "TEXT"),
    ("ri_cnib_pessoas", "origem", "TEXT"),
    # SUSPENSAO DO PRAZO DA PRENOTACAO (TJMA 452, § 3º) — 3.6.194. Enquanto
    # `prazo_suspenso_desde` estiver preenchido o prazo nao corre; ao retomar,
    # `data_limite` avanca os dias uteis suspensos (ver `ri_prenotacao_prazo`).
    ("ri_protocolos", "prazo_suspenso_desde", "TEXT"),
    ("ri_protocolos", "prazo_suspenso_motivo", "TEXT"),
    ("ri_protocolos", "prazo_suspenso_por", "TEXT"),
    # CIB — Cadastro Imobiliário Brasileiro (imóvel rural), relato #93.
    ("ri_matriculas", "cib", "TEXT"),
    # A CERTIDÃO DE ÔNUS POSITIVA OU NEGATIVA — 13/10/2026, pedido do oficial.
    #   O que o escrevente escolheu (POSITIVA | NEGATIVA, para ônus e para
    #   ações), de qual leitura da IA ele partiu, e — quando escolheu NEGATIVA
    #   contra a sugestão da IA — por quê. Ver `ri_onus_ia.py`.
    ("ri_certidoes", "resultado_onus", "TEXT"),
    ("ri_certidoes", "resultado_acoes", "TEXT"),
    ("ri_certidoes", "onus_sugestao_id", "INTEGER"),
    ("ri_certidoes", "onus_justificativa", "TEXT"),
    ("ri_certidoes", "onus_escolhido_por", "TEXT"),
    # A IA CONFERE O PROPRIETÁRIO — 15/10/2026, ordem do oficial depois da
    #   certidão de ônus 64/2026 (matrícula 3371) sair com o dono da
    #   matrícula-mãe: CONFERE | DIVERGE | CONFERIDO_NO_BALCAO, e por quê.
    ("ri_certidoes", "onus_proprietario_conferencia", "TEXT"),
    ("ri_certidoes", "onus_proprietario_justificativa", "TEXT"),

)


def init_ri_schema(con: sqlite3.Connection) -> None:
    """Cria as tabelas do modulo. Idempotente, no mesmo padrao do sistema."""
    con.executescript(SCHEMA)
    # Lancamentos proprios dos Indicadores (Livros 4 e 5) — cancelamento.
    from ri_indicador_lancamentos import init_indicador_lancamentos
    init_indicador_lancamentos(con)
    criadas = []
    for tabela, coluna, tipo in MIGRACOES:
        existentes = {linha[1] for linha in con.execute(f"PRAGMA table_info({tabela})")}
        if coluna not in existentes:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
            criadas.append((tabela, coluna))

    # Preenche a forma normalizada uma unica vez, logo apos criar a coluna.
    # Como o ALTER so acontece na primeira vez, o backfill tambem so roda uma vez.
    if ("ri_partes", "nome_norm") in criadas:
        for pid, nome in con.execute(
                "SELECT id, nome FROM ri_partes WHERE nome IS NOT NULL").fetchall():
            con.execute("UPDATE ri_partes SET nome_norm=? WHERE id=?",
                        (normalizar_busca(nome), pid))
    if ("ri_cnib_pessoas", "nome_norm") in criadas:
        for pid, nome in con.execute(
                """SELECT id, nome FROM ri_cnib_pessoas
                    WHERE nome IS NOT NULL""").fetchall():
            con.execute("UPDATE ri_cnib_pessoas SET nome_norm=? WHERE id=?",
                        (normalizar_busca(nome), pid))
    if ("ri_matriculas", "imovel_norm") in criadas:
        for mid, *campos in con.execute(
                """SELECT id, logradouro, bairro, cidade, descricao_perimetro
                   FROM ri_matriculas""").fetchall():
            con.execute("UPDATE ri_matriculas SET imovel_norm=? WHERE id=?",
                        (normalizar_busca(" ".join(c or "" for c in campos)), mid))

    # AS 50.054 ORDENS DO CNIB DE HOJE SAO DO E-OFICIO, e o backfill diz isso
    # em vez de deixar a coluna nula.
    #
    #   Coluna nula aqui seria pior que coluna ausente: o `DELETE ... WHERE
    #   origem='EOFICIO'` nao alcancaria linha nenhuma, a carga deixaria de
    #   substituir o espelho, e cada substituicao somaria uma copia nova de
    #   todas as 50.054 ordens sem ninguem ver. Medido em 18/09/2026: as
    #   50.054 vieram da carga, e sao EOFICIO uma a uma.
    if ("ri_cnib_ordens", "origem") in criadas:
        con.execute("UPDATE ri_cnib_ordens SET origem='EOFICIO' WHERE origem IS NULL")
    if ("ri_cnib_pessoas", "origem") in criadas:
        con.execute("UPDATE ri_cnib_pessoas SET origem='EOFICIO' WHERE origem IS NULL")

    # ESTE INDICE MORA AQUI, E NAO NO `SCHEMA`: a coluna so aparece pelo
    # `ALTER TABLE` acima, e num banco que ja existe o `CREATE INDEX` dentro do
    # SCHEMA estouraria ao abrir. A casa ja errou isso duas vezes no mesmo dia.
    con.execute("CREATE INDEX IF NOT EXISTS ix_cnib_nome_norm "
                "ON ri_cnib_pessoas(nome_norm)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_ri_parte_nome_norm ON ri_partes(nome_norm)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_ri_mat_imovel_norm ON ri_matriculas(imovel_norm)")

    # O ATUALIZADOR DO CNIB PRECISA DESTA TRAVA, e ela e MEDIDA ANTES de
    # nascer — nao se cria indice que estoura na abertura do banco.
    #
    #   `protocolo_cnib` e unico nas 50.054 ordens de 18/09/2026, sem uma nula
    #   e sem uma vazia. E sem a trava o UPSERT do atualizador (que casa por
    #   esta coluna) gravaria a mesma ordem duas vezes no dia em que a Central
    #   repetisse uma linha entre paginas — o que ela faz: numa varredura de
    #   3.000 ordens vieram 2.996 distintas, quatro repetidas.
    #
    #   A GUARDA NAO E ZELO: a casa ja criou indice sobre coluna que estourava
    #   e o banco nao abriu. Se houver duplicata — nao ha hoje —, ela fica
    #   declarada aqui e o espelho abre do mesmo jeito; o que nao se faz e
    #   derrubar a abertura por causa de um indice.
    if con.execute("""SELECT protocolo_cnib FROM ri_cnib_ordens
                      GROUP BY protocolo_cnib HAVING COUNT(*) > 1
                      LIMIT 1""").fetchone() is None:
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_cnib_protocolo "
                    "ON ri_cnib_ordens(protocolo_cnib)")


# ------------------------------------------------------- normalizacao


def normalizar_busca(texto: Any) -> str:
    """Forma canonica para busca: sem acento, sem caixa, sem espaco sobrando.

    'FAZENDA ÁGUA BOA' e 'fazenda agua boa' passam a casar. O acervo tem os
    dois estilos, e quem atende no balcao digita sem acento.
    """
    import unicodedata
    bruto = str(texto or "")
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", bruto)
        if unicodedata.category(c) != "Mn"
    )
    return " ".join(sem_acento.upper().split())


def norm(value: Any) -> str:
    """Tira espacos das pontas. O E-Oficio usa char(10), que vem preenchido
    com espacos a direita - e e por ai que os vinculos se perdem."""
    if value is None:
        return ""
    return str(value).strip()


def norm_livro(livro: Any) -> str:
    """Unifica as variantes de nome de livro.

    O acervo do E-Oficio grava o mesmo livro de duas formas ('2-F' e '2F'),
    o que quebraria a contagem por livro e a numeracao. Aqui vira '2F'.
    """
    return norm(livro).upper().replace("-", "").replace(" ", "")


def so_digitos(value: Any) -> str:
    return "".join(c for c in norm(value) if c.isdigit())


def matricula_de_acervo(numero: Any) -> bool:
    """Diz se o numero pertence ao acervo anterior ao sistema.

    Aceita tambem a grafia com separador (``4.014``), usada em alguns
    documentos. Valor vazio ou sem digitos nao e classificado por palpite.
    """
    digitos = so_digitos(numero)
    return bool(digitos) and 0 < int(digitos) < PRIMEIRA_MATRICULA_DO_SISTEMA


def valida_cpf_cnpj(numero: str) -> bool:
    """Confere o digito verificador. Serve para marcar a qualidade do dado
    importado, nao para recusar a parte: acervo antigo tem documento ilegivel."""
    n = so_digitos(numero)
    if len(n) == 11:
        if n == n[0] * 11:
            return False
        for corte in (9, 10):
            soma = sum(int(n[i]) * ((corte + 1) - i) for i in range(corte))
            dv = (soma * 10) % 11 % 10
            if dv != int(n[corte]):
                return False
        return True
    if len(n) == 14:
        if n == n[0] * 14:
            return False
        pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        pesos2 = [6] + pesos1
        for pesos, corte in ((pesos1, 12), (pesos2, 13)):
            soma = sum(int(n[i]) * pesos[i] for i in range(corte))
            resto = soma % 11
            dv = 0 if resto < 2 else 11 - resto
            if dv != int(n[corte]):
                return False
        return True
    return False


# ------------------------------------------------------ CNM
# Codigo Nacional de Matricula. Estrutura do Provimento CNJ 143/2023:
#
#     CCCCCC . L . NNNNNNN - DD
#     |        |   |         `- 2 digitos verificadores, modulo 97 base 10
#     |        |   `----------- 7 digitos: numero de ordem no livro
#     |        `--------------- 1 digito: 2 = Livro 2, 3 = Livro 3
#     `------------------------ 6 digitos: CNS da serventia
#
# O algoritmo do DV foi CONFERIDO contra o acervo: as 1.656 matriculas que
# vieram do E-Oficio com CNM preenchido batem, 1.656 de 1.656. Nao e suposicao.

LIVRO_REGISTRO_GERAL = 2
LIVRO_REGISTRO_AUXILIAR = 3


def dv_mod97(base: str) -> str:
    """Digito verificador ISO 7064 MOD 97-10, com dois digitos."""
    return f"{98 - (int(base + '00') % 97):02d}"


def gerar_cnm(cns: str, numero: Any, livro: int = LIVRO_REGISTRO_GERAL) -> str:
    """Monta o CNM a partir do CNS, do livro e do numero de ordem.

    Devolve string vazia se o numero nao for utilizavel — matricula com
    complemento alfabetico ou numero fora de faixa nao ganha CNM automatico,
    porque um CNM errado e pior do que CNM nenhum.
    """
    c = so_digitos(cns).rjust(6, "0")[:6]
    n = so_digitos(numero)
    if not n or len(n) > 7 or int(n) == 0 or livro not in (2, 3):
        return ""
    base = f"{c}{livro}{int(n):07d}"
    return f"{c}.{livro}.{int(n):07d}-{dv_mod97(base)}"


def valida_cnm(cnm: Any) -> bool:
    n = so_digitos(cnm)
    return len(n) == 16 and dv_mod97(n[:14]) == n[14:]


# ------------------------------------------------------- imutabilidade


def hash_certidao(numero: int, ano: int, tipo: str, matricula: str,
                  corpo: str, data_emissao: str) -> str:
    """Sela o conteudo da certidao no momento da emissao.

    Serve para provar depois que a via apresentada por terceiro e identica a
    que saiu daqui.
    """
    payload = json.dumps(
        {"numero": int(numero), "ano": int(ano), "tipo": norm(tipo),
         "matricula": norm(matricula), "corpo": corpo or "", "data": norm(data_emissao)},
        ensure_ascii=False, sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hash_ato(matricula_numero: str, tipo: str, numero: int, data_ato: str,
             teor: str, hash_anterior: str | None) -> str:
    """Encadeia o ato ao anterior da mesma matricula.

    Alterar um teor ja lavrado quebra o hash dele e o de todos os posteriores,
    o que a tela de Integridade passa a acusar. E o mesmo principio que o
    sistema ja usa para os anexos.
    """
    payload = json.dumps(
        {
            "matricula": norm(matricula_numero),
            "tipo": norm(tipo).upper(),
            "numero": int(numero),
            "data": norm(data_ato),
            "teor": teor or "",
            "anterior": hash_anterior or "",
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------- prazos em dias uteis
#
# Lei 6.015/73, art. 205, na redacao da Lei 14.382/2022:
#   "Cessarao automaticamente os efeitos da prenotacao se, decorridos 20
#   (vinte) dias da data do seu lancamento no Protocolo, o titulo nao tiver
#   sido registrado por omissao do interessado em atender as exigencias legais."
#   Paragrafo unico: nos procedimentos de regularizacao fundiaria de interesse
#   social (REURB-S), o prazo e de 40 (quarenta) dias.
#
# Codigo de Normas da CGJ/TJMA:
#   Art. 436 - "Todos os prazos do registro de imoveis serao contados em dias e
#   horas uteis, inclusive os prazos estabelecidos para a vigencia da
#   prenotacao (...), exceto naqueles contados em meses e anos."
#   Art. 452 - "A prenotacao devera ser cancelada apos 20 dias uteis do seu
#   lancamento no livro de protocolo, independentemente de notificacao (...)."

PRAZO_PRENOTACAO = 20        # dias uteis
PRAZO_PRENOTACAO_REURB = 40  # dias uteis - REURB-S
PRAZO_QUALIFICACAO = 10      # dias uteis - Codigo TJMA, art. 450

# Certidao de inteiro teor, de matricula e negativa de onus valem 30 dias
# corridos - o Codigo de Normas do TJMA repete esse prazo em varios artigos
# ("expedidas ha, no maximo, 30 (trinta) dias").
VALIDADE_CERTIDAO_DIAS = 30

# OS TRES TIPOS DA TELA DA MATRICULA, e a "negativa de matricula" saiu em
# 18/09/2026 — problema #75, relatado pelo oficial:
#
#     «nao faz sentido ter opcao de emitir certidao negativa de matricula
#      dentro da tela da matricula»
#
# E ele tem razao, pelo que o proprio texto dela dizia: «NADA CONSTA em nome
# do requerente nos livros de Registro de Imoveis desta Serventia». Isso nao e
# certidao DESTA matricula — e busca pelo NOME da pessoa nos livros todos, que
# e outra pergunta, de outra tela (e que esta casa nao emite por aqui).
#
# Os tres que ficam respondem todos a mesma pergunta — o que esta nesta
# matricula: o inteiro teor dela, os onus que a atingem, e quem e o dono.
# Ver `DOCUMENTACAO/PROBLEMA_75_A_CERTIDAO_DA_MATRICULA.md`.
#
# E A DOMINIAL E A VINTENARIA RESPONDEM A MESMA PERGUNTA, olhando para tras —
# 28/09/2026, construidas direto na producao (3.6.233, `_apply_dominial_patch`)
# e PERDIDAS quando os pacotes da 3.6.282 em diante sobrescreveram aquele
# codigo, que nunca entrou na arvore. Reconstituidas em 14/10/2026 a partir das
# copias de seguranca de `backups_patch/dominial_*` e do corpo da certidao
# 394/2026 (31/2026, matricula 3472), a unica emitida. A chave `DOMINIAL` e a
# que a 394 tem gravada em `ri_certidoes.tipo`: mudar o nome a deixaria orfa.
TIPOS_CERTIDAO = {
    "INTEIRO_TEOR": "Certidão de inteiro teor",
    "ONUS": "Certidão de ônus reais (positiva ou negativa)",
    "PROPRIEDADE": "Certidão de propriedade",
    "DOMINIAL": "Certidão dominial / cadeia dominial",
    "VINTENARIA": "Certidão vintenária",
}

# Rotulos do LIVRO de certidoes (lista + PDF). Inclui a negativa de imovel,
# que NAO entra em TIPOS_CERTIDAO — aquela e so da tela da matricula (#75).
ROTULOS_CERTIDAO_RI = {
    **TIPOS_CERTIDAO,
    "NEGATIVA_IMOVEL": "Certidão negativa de imóvel",
}


def _pascoa(ano: int) -> date:
    """Domingo de Pascoa pelo algoritmo de Meeus/Jones/Butcher."""
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes, dia = divmod(h + l - 7 * m + 114, 31)
    return date(ano, mes, dia + 1)


def feriados_nacionais(ano: int) -> set[date]:
    """Feriados nacionais fixos e moveis.

    Carnaval e Corpus Christi sao ponto facultativo na esfera federal, mas o
    foro extrajudicial costuma seguir o calendario do tribunal. Ficam incluidos
    por padrao; a serventia ajusta pela lista de feriados locais se for o caso.
    """
    p = _pascoa(ano)
    return {
        date(ano, 1, 1),    # Confraternizacao Universal
        date(ano, 4, 21),   # Tiradentes
        date(ano, 5, 1),    # Dia do Trabalho
        date(ano, 9, 7),    # Independencia
        date(ano, 10, 12),  # Nossa Senhora Aparecida
        date(ano, 11, 2),   # Finados
        date(ano, 11, 15),  # Proclamacao da Republica
        date(ano, 11, 20),  # Consciencia Negra (Lei 14.759/2023)
        date(ano, 12, 25),  # Natal
        p - timedelta(days=48),  # segunda de carnaval
        p - timedelta(days=47),  # terca de carnaval
        p - timedelta(days=2),   # sexta-feira santa
        p + timedelta(days=60),  # corpus christi
    }


def eh_dia_util(dia: date, feriados_locais: set[date] | None = None) -> bool:
    if dia.weekday() >= 5:
        return False
    if dia in feriados_nacionais(dia.year):
        return False
    return not (feriados_locais and dia in feriados_locais)


def soma_dias_uteis(inicio: date, dias: int, feriados_locais: set[date] | None = None) -> date:
    """Data em que o prazo se esgota, contando apenas dias uteis.

    O dia do lancamento nao conta: a contagem comeca no dia util seguinte.
    """
    atual = inicio
    restantes = dias
    while restantes > 0:
        atual += timedelta(days=1)
        if eh_dia_util(atual, feriados_locais):
            restantes -= 1
    return atual


def dias_uteis_entre(inicio: date, fim: date, feriados_locais: set[date] | None = None) -> int:
    """Dias uteis decorridos, para saber quanto falta ou quanto passou."""
    if fim < inicio:
        return -dias_uteis_entre(fim, inicio, feriados_locais)
    total, atual = 0, inicio
    while atual < fim:
        atual += timedelta(days=1)
        if eh_dia_util(atual, feriados_locais):
            total += 1
    return total


def ler_feriados_locais(texto: str | None) -> set[date]:
    """Le a lista de feriados estaduais e municipais das configuracoes.

    Formato: uma data ISO por linha, com comentario opcional apos '#'.
    """
    resultado: set[date] = set()
    for linha in (texto or "").splitlines():
        linha = linha.split("#")[0].strip()
        if not linha:
            continue
        try:
            resultado.add(date.fromisoformat(linha))
        except ValueError:
            continue
    return resultado


def consultar_cnib(con, documentos: list[str], nomes: list[str] | None = None) -> list[dict]:
    """Procura indisponibilidade ATIVA por documento e, opcionalmente, por nome.

    A busca por nome existe porque o acervo tem parte sem documento: 71% das
    partes importadas nao trazem CPF. Homonimo gera alarme falso, entao o
    resultado diz por qual criterio bateu, e cabe ao usuario julgar.

    DOIS DEFEITOS ACHADOS EM 28/08/2026, e os dois desligavam a busca por nome
    inteira — em silencio, que e o pior jeito de um alerta falhar.

    1. A EXCLUSAO OLHAVA A TABELA TODA, E NAO O QUE SE PROCUROU. Estava escrito
       `p.documento NOT IN (SELECT documento FROM ri_cnib_pessoas ...)`, que e
       o conjunto de TODOS os documentos do CNIB — logo a condicao so deixava
       passar quem nao tem documento nenhum. Medido: das 50.054 pessoas do
       CNIB, **zero** estao sem documento. A busca por nome devolvia lista
       vazia sempre, em qualquer instalacao onde o CNIB traga documento.

       O que ela queria dizer era «nao repita quem eu ja achei pelo documento»
       — e isso e `docs`, a lista que se procurou, e nao a tabela inteira.

    2. `UPPER` NO SQLite E ASCII. `UPPER('josé')` devolve `JOSé`, enquanto o
       `.upper()` do Python devolve `JOSÉ`: os dois lados da comparacao nunca
       se encontravam em nome com acento. Medido: `ri_partes` tem **1.257**
       nomes acentuados. E a mesma pedra em que a lista de atencao para fraudes
       ja tropecou — a correcao e a mesma, `nome_da_casa()` registrada na
       conexao, em vez de confiar no `UPPER` do banco.

    Com os dois de pe, o aviso de indisponibilidade da ficha da matricula so
    podia sair pelo documento. E por documento, nesta casa, o numero de
    achados e zero: o alerta nunca apareceu para ninguem.
    """
    achados = []
    docs = [so_digitos(d) for d in documentos if so_digitos(d)]
    if docs:
        marcas = ",".join("?" * len(docs))
        achados += [dict(r) | {"criterio": "documento"} for r in con.execute(
            f"""SELECT p.nome, p.documento, o.protocolo_cnib, o.data_pedido,
                       o.processo, o.instituicao, o.forum_vara
                FROM ri_cnib_pessoas p JOIN ri_cnib_ordens o ON o.id = p.ordem_id
                WHERE o.ativa = 1 AND p.documento IN ({marcas})""", docs)]

    limpos = [normalizar_busca(n) for n in (nomes or [])
              if n and len(str(n).strip()) > 6]
    limpos = sorted({n for n in limpos if n})
    if limpos:
        marcas = ",".join("?" * len(limpos))
        # `NOT IN (docs)` — o que se PROCUROU, e nao a tabela toda. Com lista
        # vazia o `NOT IN ()` seria erro de sintaxe, entao a condicao so entra
        # quando ha documento procurado.
        sem_repetir = (f"AND (p.documento IS NULL OR p.documento NOT IN "
                       f"({','.join('?' * len(docs))}))" if docs else "")
        achados += [dict(r) | {"criterio": "nome"} for r in con.execute(
            f"""SELECT p.nome, p.documento, o.protocolo_cnib, o.data_pedido,
                       o.processo, o.instituicao, o.forum_vara
                FROM ri_cnib_pessoas p JOIN ri_cnib_ordens o ON o.id = p.ordem_id
                WHERE o.ativa = 1 AND p.nome_norm IN ({marcas})
                  {sem_repetir}""",
            limpos + docs)]
    return achados


def verifica_cadeia(atos: list[dict]) -> list[dict]:
    """Recalcula a cadeia e devolve os atos que nao conferem.

    Recebe os atos de uma matricula em ordem de lavratura.
    """
    quebrados = []
    anterior = None
    for ato in atos:
        esperado = hash_ato(
            ato["matricula_numero"], ato["tipo"], ato["numero"],
            ato.get("data_ato") or "", ato.get("teor") or "", anterior,
        )
        if esperado != ato.get("hash_ato"):
            quebrados.append({
                "id": ato.get("id"),
                "ato": f"{ato['tipo']}-{ato['numero']}",
                "esperado": esperado,
                "gravado": ato.get("hash_ato"),
            })
        anterior = ato.get("hash_ato")
    return quebrados
