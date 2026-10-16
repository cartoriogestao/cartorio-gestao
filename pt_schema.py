"""
Protesto — o titulo e os atos da vida dele.

POR QUE DUAS TABELAS, E NAO AS 190 COLUNAS DO ACERVO
    `tbAvisoProtesto` do E-Oficio tem uma coluna de selo, um emolumento e um
    FERC/MP/DP/ferrfis PARA CADA ETAPA — apontamento, intimacao, diligencia,
    arquivamento, certidao, cancelamento. Sao 190 colunas numa tabela so, e e
    o mesmo defeito de `tbRegistroESC`: quem deixa para preencher depois nao
    preenche (ver LEVANTAMENTO_PROTESTO.md).

    Aqui: uma linha por TITULO em `pt_titulos`, e uma linha por ATO em
    `pt_atos` — apontamento, intimacao, protesto, pagamento, cancelamento,
    arquivamento, certidao, desistencia, retirada. Cada ato tem o seu selo e
    a sua data; as custas ficam no lancamento do caixa, ligado por
    `lancamento_id`, do mesmo jeito que o resto da casa.

ONDE ISTO ENCOSTA NO NUCLEO
    `pt_atos` grava `livro_id`, `folha`, `verso`, `numero_ordem` e `rotulo` —
    o lugar que `escrituracao.reservar()` devolveu ao ocupar uma face do
    Livro de Apontamento, do Livro de Registro de Protestos ou do Livro de
    Registro de Pagamentos (series PT_APONTAMENTO, PT_PROTESTO, PT_PAGAMENTO
    de `livro_nucleo.py`). Protesto e a primeira atribuicao a usar o nucleo
    de verdade — RI ainda tem numeracao propria, em `ri_numeracao`.

SOBRE A INTIMACAO, E O QUE O ACERVO NAO TEM
    `tbAvisoProtesto` guarda selo separado para intimacao pessoal e para
    edital, taxa de diligencia, codigo do edital e uma marca de "intimado
    digitalmente" — mas NENHUMA coluna de data da intimacao. O E-Oficio
    nunca controlou prazo de intimacao de verdade; a unica data proxima e
    `dtmOcorrencia`, generica e ja sabida ambigua (a ocorrencia `C`, usada
    1.027 vezes, sem significado identificado).

    Por isso `lancar_intimacao()` REGISTRA — modo, diligencia, comprovante —
    e NAO CALCULA vencimento nenhum. Contar o prazo de 3 dias (corrido ou
    util, a partir de que marco) e decisao juridica do oficial, tomada em
    24/08/2026: "so registrar, sem contar prazo" ate ele decidir a regra.

O QUE AINDA NAO ENTROU
    Protesto propriamente dito, pagamento e cancelamento sao os proximos
    passos de LEVANTAMENTO_PROTESTO.md — itens 4 a 6. `TIPOS_ATO`, em
    `protesto.py`, ja lista o vocabulario inteiro do ciclo — porque ele esta
    medido e documentado, nao inventado —, mas so `APONTAMENTO` e
    `INTIMACAO` tem funcao que grava.

FUNDAMENTO
    Lei 9.492/1997, arts. 1o (titulo sujeito a protesto), 3o (apontamento),
        33 e 34 (livros).
    LEVANTAMENTO_PROTESTO.md — o acervo medido em 21/08/2026.
"""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS pt_titulos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    especie TEXT NOT NULL,                  -- codigo CRA: DMI, CDA, ATC ...
    numero_titulo TEXT NOT NULL,
    nosso_numero TEXT,
    chave_cenprot TEXT,                     -- quando o arquivo trouxer

    data_emissao TEXT,
    data_vencimento TEXT,
    tipo_moeda TEXT NOT NULL DEFAULT '1',
    valor_centavos INTEGER NOT NULL DEFAULT 0,
    saldo_centavos INTEGER NOT NULL DEFAULT 0,

    praca_protesto TEXT,
    tipo_protesto TEXT,
    tipo_endosso TEXT,
    aceite TEXT,
    motivo_protesto TEXT,
    irregularidades_json TEXT,              -- lista de codigos da CRA, ate 9

    -- QUEM APRESENTOU, que e para quem o retorno volta. Vem do cabecalho do
    -- arquivo da CRA (posicoes 2 a 19) e sem ele nao ha como montar o retorno:
    -- `montar_retorno` precisa do codigo para saber a letra da posicao 566.
    apresentante_codigo TEXT,
    apresentante_nome TEXT,

    -- O PROTOCOLO DA CASA, que volta no retorno na posicao 448.
    --
    -- Medido em 25/08/2026: no acervo ele e `intProtocolo`, igual a `strCB`
    -- nos 1.365 (100%), e desde 2024 tem forma AAMMDD + sequencial do dia —
    -- 928 dos 931. Antes de 2024 o E-Oficio usava outro esquema, que nao se
    -- reproduz aqui: o que vale e o que a casa faz HOJE.
    protocolo TEXT,

    cedente_nome TEXT,
    cedente_documento TEXT,
    cedente_endereco TEXT,
    cedente_cep TEXT,
    cedente_cidade TEXT,
    cedente_uf TEXT,

    -- RECEBIDO -> APONTADO. O resto do ciclo (INTIMADO, PROTESTADO, PAGO,
    -- CANCELADO, DEVOLVIDO, RETIRADO) esta documentado e ainda nao gravado
    -- por nenhuma funcao — ver o cabecalho deste arquivo.
    situacao TEXT NOT NULL DEFAULT 'RECEBIDO',

    origem TEXT NOT NULL DEFAULT 'MANUAL',  -- CRA | CENPROT | MANUAL
    origem_chave TEXT,                      -- chave do lote/arquivo, p/ carga repetivel
    importacao_id INTEGER,

    criado_em TEXT NOT NULL,
    criado_por INTEGER,
    UNIQUE(origem, origem_chave)
);

CREATE INDEX IF NOT EXISTS ix_pt_titulos_numero ON pt_titulos(numero_titulo);
CREATE INDEX IF NOT EXISTS ix_pt_titulos_situacao ON pt_titulos(situacao);

CREATE TABLE IF NOT EXISTS pt_devedores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo_id INTEGER NOT NULL REFERENCES pt_titulos(id),
    nome TEXT NOT NULL,
    documento_tipo TEXT,                    -- CPF | CNPJ
    documento_numero TEXT,
    endereco TEXT,
    bairro TEXT,
    cep TEXT,
    cidade TEXT,
    uf TEXT,
    -- BUSCA SEM ACENTO E SEM CAIXA. `UPPER()` do SQLite e ASCII: ele passa
    -- 'jose' para 'JOSE' e deixa 'josé' como 'JOSé'. Quem digitasse o nome em
    -- minusculas com acento nao achava a pessoa — e certidao que nao acha por
    -- causa de grafia e certidao que mente.
    --
    -- A forma e a mesma de `nt_pessoas.nome_norm`, que ja roda nesta casa.
    nome_norm TEXT
);

CREATE INDEX IF NOT EXISTS ix_pt_devedores_titulo ON pt_devedores(titulo_id);
CREATE INDEX IF NOT EXISTS ix_pt_devedores_doc ON pt_devedores(documento_numero);

CREATE TABLE IF NOT EXISTS pt_atos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo_id INTEGER NOT NULL REFERENCES pt_titulos(id),
    tipo TEXT NOT NULL,                     -- ver protesto.TIPOS_ATO

    servico_codigo INTEGER,                 -- atribuicoes.ATOS, quando confirmado
    selo TEXT,
    protocolo_id INTEGER,                   -- protocolo do caixa, quando houver
    lancamento_id INTEGER,                  -- as custas, no caixa

    livro_id INTEGER REFERENCES nu_livros(id),
    folha INTEGER,
    verso INTEGER NOT NULL DEFAULT 0,
    numero_ordem INTEGER,
    rotulo TEXT,

    data_ato TEXT NOT NULL,
    observacao TEXT,
    -- O que varia de um tipo de ato para outro (modo da intimação, motivo
    -- do protesto, valor pago...). Um campo por tipo futuro encheria esta
    -- tabela de colunas vazias para os outros oito tipos — o defeito de
    -- `tbAvisoProtesto` outra vez, só que distribuído em vez de achatado.
    detalhe_json TEXT NOT NULL DEFAULT '{}',

    cancelado INTEGER NOT NULL DEFAULT 0,
    motivo_cancelamento TEXT,

    origem TEXT NOT NULL DEFAULT 'MANUAL',
    origem_chave TEXT,
    importacao_id INTEGER,

    -- Em que retorno este ato foi informado a CRA. Vazio e ato que a Central
    -- ainda nao sabe — e e essa a lista que a tela do retorno mostra.
    retorno_id INTEGER REFERENCES pt_retornos(id),

    criado_em TEXT NOT NULL,
    criado_por INTEGER
);

CREATE INDEX IF NOT EXISTS ix_pt_atos_titulo ON pt_atos(titulo_id, tipo);
-- `ix_pt_atos_retorno` NAO fica aqui: `retorno_id` e coluna de MIGRACAO, e
-- num banco que ja existia ela so aparece no `ALTER TABLE`. Ver
-- `INDICES_DEPOIS_DA_MIGRACAO` — e o mesmo tropeco de `nome_norm`, que eu
-- documentei de manha e repeti a tarde. O comentario nao basta: o lugar do
-- indice e que tem de ser o certo.
CREATE INDEX IF NOT EXISTS ix_pt_atos_selo ON pt_atos(selo);

-- A CERTIDAO NAO E ATO DE UM TITULO, e por isso nao mora em `pt_atos`:
-- `pt_atos.titulo_id` e NOT NULL, e a certidao NEGATIVA — 46 das 65 do
-- acervo — nao tem titulo nenhum. Certidao e ato da SERVENTIA sobre uma
-- pessoa, e nao sobre um papel.
--
-- Numeracao por exercicio, teor congelado e hash: e a mesma forma do recibo
-- do caixa (`cx_recibos`), que ja roda nesta casa. Duas formas para o papel
-- que o cliente leva para casa seria uma a mais.
CREATE TABLE IF NOT EXISTS pt_certidoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero INTEGER NOT NULL,
    ano INTEGER NOT NULL,

    tipo TEXT NOT NULL,                     -- NEGATIVA | POSITIVA | CANCELAMENTO

    -- De quem se buscou. O nome entra como foi pedido; o documento entra so
    -- com digitos, para a busca nao depender de ponto e traco.
    nome TEXT NOT NULL,
    documento TEXT,
    documento_tipo TEXT,                    -- CPF | CNPJ
    requerente TEXT,
    finalidade TEXT,

    periodo_anos INTEGER,                   -- 5, como o E-Oficio fazia
    desde TEXT,                             -- a data-limite da busca

    achados INTEGER NOT NULL DEFAULT 0,     -- quantos protestos entraram
    achados_json TEXT NOT NULL DEFAULT '[]',-- o que entrou, congelado
    teor TEXT NOT NULL,                     -- congelado na emissao
    hash_certidao TEXT,

    selo TEXT,
    lancamento_id INTEGER,                  -- as custas, no caixa

    cancelada INTEGER NOT NULL DEFAULT 0,
    motivo_cancelamento TEXT,
    cancelada_em TEXT,
    cancelada_por TEXT,
    declaracao_selo_tjma_em TEXT,
    declaracao_selo_tjma_por TEXT,

    emitida_em TEXT NOT NULL,
    emitida_por TEXT,
    UNIQUE(numero, ano)
);

-- O INSTRUMENTO DE PROTESTO — o papel que se entrega ao apresentante.
--
-- Lei 9.492/1997, art. 20: lavrado e registrado o protesto, o instrumento
-- fica a disposicao do apresentante no primeiro dia util seguinte.
--
-- O TEOR CONGELA, E AQUI POR UMA RAZAO A MAIS: ele vai ser ASSINADO. A
-- assinatura digital e sobre bytes determinados — teor que se remonta faz a
-- firma deixar de conferir sem ninguem ter mexido em nada. Ver
-- `assinatura_digital` e `as_documentos`.
--
-- SEGUNDA VIA E OUTRA LINHA, e nao a mesma reescrita: reaproveitar faria a
-- segunda via sobrescrever o teor que a primeira levou assinado.
CREATE TABLE IF NOT EXISTS pt_instrumentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero INTEGER NOT NULL,
    ano INTEGER NOT NULL,

    titulo_id INTEGER NOT NULL,
    ato_id INTEGER NOT NULL,                -- o ato de PROTESTO que ele declara

    teor TEXT NOT NULL,                     -- congelado na emissao
    corpo_json TEXT NOT NULL DEFAULT '{}',  -- os campos do art. 22, congelados
    hash_instrumento TEXT,

    emitido_em TEXT NOT NULL,
    emitido_por TEXT,
    UNIQUE(numero, ano)
);

CREATE INDEX IF NOT EXISTS idx_pt_instrumentos_titulo
    ON pt_instrumentos(titulo_id);

-- O ARQUIVO DE RETORNO que a casa mandou a CRA.
--
-- Guarda o teor inteiro, e nao so o nome: o arquivo que saiu daqui e o que a
-- Central recebeu, e quando ela reclamar de um titulo e este teor que se le.
-- E a mesma razao do teor congelado da certidao.
-- O XML DIÁRIO QUE A CASA SOBE À CENPROT (15/10/2026). P = protestos, com o
-- instrumento eletrônico assinado dentro; D = pagos, retirados e cancelados.
-- O arquivo INTEIRO fica guardado (com o BOM), porque é ele que se baixa e se
-- sobe no portal, e é ele que se confere quando a Central reclamar.
CREATE TABLE IF NOT EXISTS pt_cenprot_xml (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    letra TEXT NOT NULL,                    -- P | D
    dia TEXT NOT NULL,                      -- AAAA-MM-DD do arquivo
    sequencial INTEGER NOT NULL,
    nome_arquivo TEXT NOT NULL UNIQUE,
    conteudo BLOB NOT NULL,
    sha256 TEXT NOT NULL,
    titulos INTEGER NOT NULL,
    gerado_em TEXT NOT NULL,
    gerado_por TEXT
);

-- O CADASTRO DOS APRESENTANTES, para o XML da CENPROT — 15/10/2026.
-- O arquivo da CRA traz o codigo e o nome do apresentante, e o XML pede
-- tambem o CNPJ e o tipo dele. Medido: na amostra de 28 arquivos que a casa
-- mandou, 13 dos 14 apresentantes casam pelo codigo com `tbCobrador`
-- (`strCodigoBanco`, unico nas 56 linhas que o tem), com o mesmo CNPJ, o mesmo
-- tipo e o mesmo nome. O que nao casa se cadastra na tela do XML.
CREATE TABLE IF NOT EXISTS pt_apresentantes (
    codigo TEXT PRIMARY KEY,                -- o codigo da CRA (3 posicoes)
    nome TEXT NOT NULL,
    documento TEXT,                         -- CNPJ ou CPF, so digitos
    tipo_apresentante TEXT,                 -- o codigo do XML (0, 1, 3, 4...)
    origem TEXT NOT NULL DEFAULT 'MANUAL',  -- EOFICIO | MANUAL
    atualizado_em TEXT NOT NULL,
    atualizado_por TEXT
);

-- A BASE NACIONAL DE ENDERECOS DA CENPROT — o que se perguntou e o que se
-- mandou, por aviso (15/10/2026). Consultar manda o CPF do devedor para
-- fora, e cadastrar manda o endereco dele: as duas coisas ficam escritas,
-- com quem fez e quando. A resposta da consulta fica guardada porque e com
-- ela que o balcao decide reemitir o aviso noutro endereco.
CREATE TABLE IF NOT EXISTS pt_base_endereco (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    aviso_id INTEGER NOT NULL REFERENCES pt_avisos(id),
    titulo_id INTEGER NOT NULL REFERENCES pt_titulos(id),
    acao TEXT NOT NULL,                     -- CONSULTA | CADASTRO
    ambiente TEXT NOT NULL,
    documento TEXT NOT NULL,
    enviado TEXT,                           -- o corpo do cadastro, JSON
    resposta TEXT,                          -- o que a Central devolveu, JSON
    achados INTEGER NOT NULL DEFAULT 0,     -- quantos enderecos a consulta trouxe
    feito_em TEXT NOT NULL,
    feito_por TEXT
);

CREATE TABLE IF NOT EXISTS pt_retornos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- SDTBFORTP (retorno) | SDTBFOAND (andamento) | SDTBFOCRT (confirmacao).
    -- O retorno e o andamento saem em PAR: e regra da casa, do roteiro do
    -- protesto que o oficial trouxe — "SEMPRE QUE GERAR RETORNO (FINAL),
    -- GERAR ANDAMENTO".
    tipo TEXT NOT NULL DEFAULT 'SDTBFORTP',
    par_id INTEGER,                         -- o irmao, quando saem juntos
    apresentante_codigo TEXT NOT NULL,
    apresentante_nome TEXT,
    dia TEXT NOT NULL,                      -- data do movimento
    numero_da_remessa INTEGER NOT NULL DEFAULT 1,
    marca TEXT,                             -- a letra da posicao 566
    titulos INTEGER NOT NULL DEFAULT 0,
    soma_centavos INTEGER NOT NULL DEFAULT 0,
    nome_arquivo TEXT NOT NULL,
    conteudo TEXT NOT NULL,                 -- o arquivo inteiro, como saiu
    hash_arquivo TEXT,
    gerado_em TEXT NOT NULL,
    gerado_por TEXT
);

CREATE INDEX IF NOT EXISTS ix_pt_retornos_dia ON pt_retornos(dia);

-- A REMESSA QUE CHEGOU, guardada inteira. E o outro lado de `pt_retornos`:
-- ali fica o que sai, aqui o que entra.
--
-- 93% DOS TITULOS DESTA CASA ENTRAM POR AQUI, e o roteiro do oficial poe o
-- recebimento no meio-dia: "recebimento de remessa, confirmacao e emissao do
-- aviso". Guardar o arquivo inteiro, e nao so o nome, e a mesma regra do
-- retorno: quando a Central reclamar de um titulo, e este teor que se le.
--
-- `hash_arquivo` E UNICO, E ESSA E A TRAVA QUE IMPORTA. Subir o mesmo arquivo
-- duas vezes apontaria todos os titulos de novo — e apontamento nao se
-- desfaz. Aqui a regra mora no banco, e nao na tela.
CREATE TABLE IF NOT EXISTS pt_remessas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL,                     -- BFOSDTTPR
    apresentante_codigo TEXT NOT NULL,
    apresentante_nome TEXT,
    dia TEXT NOT NULL,                      -- a data do movimento, do cabecalho
    numero_da_remessa TEXT,

    nome_arquivo TEXT,
    conteudo TEXT NOT NULL,                 -- o arquivo inteiro, como chegou
    hash_arquivo TEXT NOT NULL,

    titulos INTEGER NOT NULL DEFAULT 0,     -- quantos vieram no arquivo
    recebidos INTEGER NOT NULL DEFAULT 0,   -- quantos entraram
    recusados INTEGER NOT NULL DEFAULT 0,   -- quantos o contrato da CRA recusou
    apontados INTEGER NOT NULL DEFAULT 0,
    recusas_json TEXT,                      -- o motivo de cada recusa, por titulo
    achados_json TEXT,                      -- o que o proprio arquivo nao fechou

    -- A CONFIRMACAO mora em `pt_retornos`, com tipo SDTBFOCRT: ela e arquivo
    -- que SAI, e o lugar do que sai ja existe. Aqui fica so o ponteiro.
    confirmacao_id INTEGER REFERENCES pt_retornos(id),

    -- IDENTIDADE XML (CRA21): preparacao para importacao futura. Remessa TXT
    -- legado fica NULL nestes tres campos. `origem_xml_chave` e a saida de
    -- `protesto_cra_xml.chave_idempotencia(ambiente, hash_lote)`.
    origem_xml_ambiente TEXT,               -- HOMOLOGACAO | PRODUCAO
    origem_xml_hash_lote TEXT,              -- SHA-256 dos atributos hd/tr/tl
    origem_xml_chave TEXT,                  -- UNIQUE quando preenchida

    recebida_em TEXT NOT NULL,
    recebida_por TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_pt_remessas_hash
    ON pt_remessas(hash_arquivo);
CREATE INDEX IF NOT EXISTS ix_pt_remessas_dia ON pt_remessas(dia);

-- O ARQUIVO DE DESISTENCIA, guardado inteiro. E o quinto tipo da CRA, e o
-- unico que NAO tem 600 posicoes: tem 127, cinco tipos de registro e o
-- sequencial no fim. Ver `LAYOUT_DESISTENCIA_MEDIDO.md`.
--
-- O roteiro do oficial confere desistencia nos TRES TURNOS do dia — e a unica
-- coisa que aparece nos tres. O motivo esta na consequencia: titulo de que o
-- apresentante desistiu e a casa protestou e protesto que se cancela depois,
-- com carta.
--
-- `hash_arquivo` E UNICO, mas por motivo DIFERENTE do da remessa. La a trava
-- impede apontar tudo de novo; aqui ela so garante que o mesmo arquivo entre
-- UMA vez no registro — aplicar a desistencia duas vezes nao faz nada, porque
-- o dominio recusa desistir de titulo ja desistido. E o caso comum e o
-- segundo turno: aplicou-se metade de manha e volta-se ao meio-dia.
CREATE TABLE IF NOT EXISTS pt_desistencias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    apresentante_codigo TEXT,
    apresentante_nome TEXT,
    dia TEXT,                               -- a data do movimento, do cabecalho

    nome_arquivo TEXT,
    conteudo TEXT NOT NULL,                 -- o arquivo inteiro, como chegou
    hash_arquivo TEXT NOT NULL,

    titulos INTEGER NOT NULL DEFAULT 0,     -- quantos vieram no arquivo
    aplicados INTEGER NOT NULL DEFAULT 0,   -- quantos o oficial aplicou
    soma_centavos INTEGER NOT NULL DEFAULT 0,
    achados_json TEXT,

    recebida_em TEXT NOT NULL,
    recebida_por TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_pt_desistencias_hash
    ON pt_desistencias(hash_arquivo);
CREATE INDEX IF NOT EXISTS ix_pt_desistencias_dia ON pt_desistencias(dia);

-- O AVISO DE INTIMACAO — o papel que vai ate o devedor.
--
-- MEDIDO EM `tbBoletoApto` (1.618 linhas, `AVISO_DE_INTIMACAO_MEDIDO.md`):
-- 1.361 dos 1.370 titulos do acervo tem aviso, e **255 tem mais de um**.
-- Reemitir e rotina — endereco que muda, entrega que nao deu certo. Por isso
-- o aviso NAO e coluna do titulo: e tabela com uma linha por emissao.
--
-- O AVISO E O INSTRUMENTO; A INTIMACAO E O ATO. O ato continua em `pt_atos`,
-- lavrado por `protesto.lancar_intimacao` — este aviso guarda o papel que
-- circulou e o que aconteceu com ele. Juntar os dois faria a tentativa que
-- nao achou ninguem virar intimacao, e nao e.
CREATE TABLE IF NOT EXISTS pt_avisos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo_id INTEGER NOT NULL REFERENCES pt_titulos(id),
    numero INTEGER NOT NULL,
    ano INTEGER NOT NULL,

    -- Para quem foi, COMO ESTAVA NO DIA. Endereco que muda depois nao muda o
    -- aviso que ja saiu — e o segundo aviso e outra linha, com o novo.
    devedor_nome TEXT,
    devedor_documento TEXT,
    endereco TEXT,
    bairro TEXT,
    cep TEXT,
    cidade TEXT,
    uf TEXT,

    -- EMITIDO | ENTREGUE | NAO_ENTREGUE | EDITAL | CANCELADO
    situacao TEXT NOT NULL DEFAULT 'EMITIDO',

    emitido_em TEXT NOT NULL,
    emitido_por TEXT,

    -- A TENTATIVA. `entregador` e texto e nao codigo: o acervo tem dois
    -- cadastrados — CARTORIO e CORREIROS — e os Correios estao DESLIGADOS;
    -- as 1.618 entregas sairam pela mao da propria casa. Tabela de cadastro
    -- para duas linhas, uma delas morta, seria tabela para nada.
    entregador TEXT,
    entrega_em TEXT,
    entregue INTEGER NOT NULL DEFAULT 0,
    motivo INTEGER,                         -- do catalogo medido, 13 motivos
    recebido_por TEXT,
    observacao TEXT,

    -- O ato de intimacao que este aviso produziu, quando produziu.
    ato_id INTEGER REFERENCES pt_atos(id),
    edital_id INTEGER,

    criado_em TEXT NOT NULL
);

-- CADA TENTATIVA DE ENTREGA E UM REGISTRO, e nao a ultima sobrescrevendo a
-- anterior. Medido em `tbBoletoControleNEntrega`: 1.139 controles para 1.093
-- titulos — 1.054 com uma tentativa, 34 com duas, 3 com tres e 2 com quatro.
--
-- Sao 3,6% dos casos, e sao os que mais importam: guardar so a ultima apagaria
-- o rastro que JUSTIFICA o edital. "Tentou-se duas vezes e nao havia ninguem"
-- e o que a inspecao le; "entregue" sozinho nao conta essa historia.
--
-- O aviso continua guardando o DESFECHO — como `tbBoletoApto` guarda
-- `bitEntregue` ao lado da tabela de controle. Aqui fica o caminho ate ele.
CREATE TABLE IF NOT EXISTS pt_tentativas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    aviso_id INTEGER NOT NULL REFERENCES pt_avisos(id),
    titulo_id INTEGER NOT NULL REFERENCES pt_titulos(id),

    quando TEXT NOT NULL,
    entregador TEXT,
    entregue INTEGER NOT NULL DEFAULT 0,
    motivo INTEGER,
    recebido_por TEXT,
    observacao TEXT,

    criado_em TEXT NOT NULL,
    criado_por TEXT
);

CREATE INDEX IF NOT EXISTS ix_pt_tentativas_aviso
    ON pt_tentativas(aviso_id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_pt_avisos_numero
    ON pt_avisos(numero, ano);
CREATE INDEX IF NOT EXISTS ix_pt_avisos_titulo ON pt_avisos(titulo_id);
CREATE INDEX IF NOT EXISTS ix_pt_avisos_situacao ON pt_avisos(situacao);

-- O EDITAL — o que vem depois da entrega que nao deu certo, e nesta casa e
-- ROTINA e nao excecao: 1.092 dos 1.618 avisos foram publicados em edital, e
-- 1.068 dos 1.139 controles de nao-entrega dizem "Ausente".
--
-- UMA LINHA POR AVISO, como em `tbEdital` (1.086 linhas para 1.092 avisos
-- publicados). A folha que se prega na parede junta varios; isso e relatorio,
-- e nao registro.
CREATE TABLE IF NOT EXISTS pt_editais (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero INTEGER NOT NULL,
    ano INTEGER NOT NULL,
    aviso_id INTEGER NOT NULL REFERENCES pt_avisos(id),
    titulo_id INTEGER NOT NULL REFERENCES pt_titulos(id),

    publicado_em TEXT NOT NULL,             -- a data da publicacao
    publicado_por TEXT,
    cidade_ibge TEXT,                       -- 2198765 nas 1.086 do acervo

    -- O TEOR CONGELA, como na certidao e no recibo: edital publicado nao se
    -- redige de novo. E o papel que substitui a intimacao pessoal — se ele
    -- mudar depois, ninguem sabe o que foi afixado.
    teor TEXT NOT NULL,
    hash_teor TEXT,

    ato_id INTEGER REFERENCES pt_atos(id),
    criado_em TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_pt_editais_numero
    ON pt_editais(numero, ano);
CREATE INDEX IF NOT EXISTS ix_pt_editais_aviso ON pt_editais(aviso_id);
CREATE INDEX IF NOT EXISTS ix_pt_editais_dia ON pt_editais(publicado_em);

CREATE INDEX IF NOT EXISTS ix_pt_certidoes_doc ON pt_certidoes(documento);
CREATE INDEX IF NOT EXISTS ix_pt_certidoes_nome ON pt_certidoes(nome);
"""

# Colunas acrescentadas depois. Aditivo, no padrao do sistema.
MIGRACOES: tuple[tuple[str, str, str], ...] = (
    ("pt_certidoes", "declaracao_selo_tjma_em", "TEXT"),
    ("pt_certidoes", "declaracao_selo_tjma_por", "TEXT"),
    ("pt_devedores", "nome_norm", "TEXT"),
    ("pt_titulos", "apresentante_codigo", "TEXT"),
    ("pt_titulos", "apresentante_nome", "TEXT"),
    ("pt_titulos", "protocolo", "TEXT"),
    ("pt_atos", "retorno_id", "INTEGER"),
    # em que XML da CENPROT o ato já foi (15/10/2026) — nada sai duas vezes
    ("pt_atos", "cenprot_xml_id", "INTEGER"),
    ("pt_retornos", "tipo", "TEXT"),
    ("pt_retornos", "par_id", "INTEGER"),
    ("pt_titulos", "remessa_id", "INTEGER"),
    ("pt_atos", "desistencia_id", "INTEGER"),
    # O TEXTO QUE VAI NO LIVRO — `protesto_termo`. Ate 01/09/2026 o registro
    # do protesto saia sem uma palavra: livro, folha e numero de ordem, e mais
    # nada. Medido no acervo, o E-Oficio escrevia um `memInformativo` em
    # **1.132 de 1.164** protestos.
    #
    # Ele CONGELA: e o texto que foi escrito no livro naquele dia, e corrigir
    # protesto e averbar ao lado, nao reescrever.
    ("pt_atos", "teor", "TEXT"),
    ("pt_remessas", "origem_xml_ambiente", "TEXT"),
    ("pt_remessas", "origem_xml_hash_lote", "TEXT"),
    ("pt_remessas", "origem_xml_chave", "TEXT"),
    ("pt_retornos", "cra_enviado_em", "TEXT"),
    ("pt_retornos", "cra_enviado_ambiente", "TEXT"),
    ("pt_retornos", "cra_envio_resumo", "TEXT"),
    ("pt_retornos", "cra_envio_erro", "TEXT"),
    ("pt_retornos", "cra_enviado_por", "TEXT"),
)

# INDICE SOBRE COLUNA DE MIGRACAO VAI AQUI, E NAO NO `SCHEMA`.
#
# Eu tinha posto `ix_pt_devedores_nome` junto dos outros dois, dentro do
# SCHEMA — e num banco NOVO funcionava, porque o `CREATE TABLE` ali em cima
# ja cria a coluna. Num banco que JA EXISTIA o `CREATE TABLE IF NOT EXISTS`
# nao faz nada, a coluna so aparece no `ALTER TABLE` mais abaixo, e o
# `CREATE INDEX` estourava com "no such column: nome_norm" na hora de abrir
# o banco. Quem pegou foi `tests/test_menu.py`, que reaproveita a mesma pasta
# de dados entre execucoes e por isso tinha um banco da versao anterior.
INDICES_DEPOIS_DA_MIGRACAO: tuple[str, ...] = (
    ("CREATE INDEX IF NOT EXISTS ix_pt_devedores_nome "
     "ON pt_devedores(nome_norm)"),
    "CREATE INDEX IF NOT EXISTS ix_pt_atos_retorno ON pt_atos(retorno_id)",
    ("CREATE INDEX IF NOT EXISTS ix_pt_titulos_remessa "
     "ON pt_titulos(remessa_id)"),
    ("CREATE INDEX IF NOT EXISTS ix_pt_atos_desistencia "
     "ON pt_atos(desistencia_id)"),
    ("CREATE UNIQUE INDEX IF NOT EXISTS ux_pt_remessas_xml_chave "
     "ON pt_remessas(origem_xml_chave)"),
)


def normalizar_nome(texto: Any) -> str | None:
    """Forma sem acento e sem caixa, para busca. Igual a de `notas_import`.

    E a mesma funcao que preenche `nt_pessoas.nome_norm` desde a carga das
    Notas; duas formas de normalizar nome fariam a busca do Protesto achar
    coisa diferente da busca das Notas para o mesmo nome.
    """
    s = str(texto or "").strip()
    if not s:
        return None
    t = unicodedata.normalize("NFD", s.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip() or None


def init_pt_schema(con: sqlite3.Connection) -> None:
    """Cria as tabelas do Protesto. Idempotente. Chamar DEPOIS do nucleo."""
    con.executescript(SCHEMA)
    for tabela, coluna, tipo in MIGRACOES:
        existentes = {linha[1] for linha in con.execute(f"PRAGMA table_info({tabela})")}
        if coluna not in existentes:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
    for indice in INDICES_DEPOIS_DA_MIGRACAO:
        con.execute(indice)
