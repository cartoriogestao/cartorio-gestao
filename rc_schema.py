"""
RCPN — Registro Civil das Pessoas Naturais: os assentos e os seus atos.

POR QUE UMA TABELA DE ASSENTO, E NAO UMA POR LIVRO
    O E-Oficio tem `tbRegistroNascimento` (54 colunas), `tbRegistroCasamento`
    (94) e `tbRegistroObito` (71) — tres tabelas com o mesmo esqueleto e
    campos proprios de cada especie. Copiar isso daria tres tabelas
    divergentes do mesmo conceito, e o casamento (94 colunas) e a prova de
    onde isso chega.

    Aqui: uma linha por ASSENTO em `rc_assentos`, com o que TODO assento tem
    (livro, folha, numero, data, matricula, teor), e os campos proprios de
    cada especie em `dados_json`. Uma linha por ATO em `rc_atos` —
    REGISTRO, AVERBACAO, ANOTACAO, RETIFICACAO —, que e a divisao tripartite
    que a inspecao de 12/08/2026 cobrou do Livro A.

A DIVISAO TRIPARTITE, QUE E EXIGENCIA DA INSPECAO
    A inspecao cobra que cada assento tenha "campo proprio para nota,
    averbacao e retificacao, inclusive no verso". Isso NAO e um campo de
    texto com tres subtitulos: sao atos distintos, cada um com data, quem
    lavrou e o seu teor. `rc_atos.tipo` guarda qual dos tres, e por isso a
    ficha do assento pode mostrar cada bloco separado, como o livro fisico
    faz.

A MATRICULA DE 32 DIGITOS
    Campo proprio (`matricula`), porque e a chave nacional do registro civil
    — e por ela que CRC, SIRC e a certidao se referem ao assento. O acervo a
    guarda em `strNumeroMatricula` (nascimento) e `strMatricula` (casamento e
    obito). Ainda NAO e gerada nem validada por este modulo: gerar matricula
    exige o algoritmo oficial do CNJ, que nao esta medido. Fica como campo
    recebido, e o backlog registra a falta — o mesmo tratamento que o CNM
    tem no RI.

O QUE NAO ENTRA AINDA
    SIRC, CRC, IBGE, Unidade Interligada e DNV: sao remessas e integracoes
    externas, no mesmo estagio em que o selo esta para o Protesto. O que
    entra aqui e o assento e os seus atos, que e o que as remessas leem.

FUNDAMENTO
    Lei 6.015/1973, arts. 9o, 29 e 33 (livros do registro civil), 50 a 66
        (nascimento), 67 a 76 (casamento), 77 a 88 (obito).
    Lei 8.560/1992 — investigacao de paternidade.
    Inspecao ordinaria de 12/08/2026 — divisao tripartite do assento,
        continuidade da numeracao ao migrar do livro fisico.
    LEVANTAMENTO_QUATRO_ATRIBUICOES.md, secao 3.
"""
from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS rc_assentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    serie TEXT NOT NULL,                    -- RC_A, RC_B, RC_C, RC_D, RC_E ...
    especie TEXT NOT NULL,                  -- NASCIMENTO | CASAMENTO | OBITO |
                                            -- PROCLAMAS | NATIMORTO | OUTRO
    numero INTEGER,                         -- numero_ordem do ato, no nucleo
    matricula TEXT,                         -- a de 32 dígitos, quando houver
    nome TEXT NOT NULL,                     -- de quem é o assento
    data_ato TEXT,                          -- a data do assento
    data_fato TEXT,                         -- nascimento, casamento, óbito

    -- Os campos próprios de cada espécie. O casamento tem 94 colunas no
    -- acervo; um campo por coluna aqui encheria a tabela de vazios para as
    -- outras cinco espécies.
    dados_json TEXT NOT NULL DEFAULT '{}',

    teor TEXT,
    teor_formato TEXT NOT NULL DEFAULT 'texto',

    situacao TEXT NOT NULL DEFAULT 'ATIVO', -- ATIVO | CANCELADO
    origem TEXT NOT NULL DEFAULT 'MANUAL',  -- MANUAL | EOFICIO
    origem_chave TEXT,
    importacao_id INTEGER,

    criado_em TEXT NOT NULL,
    criado_por INTEGER,
    UNIQUE(origem, origem_chave)
);

CREATE INDEX IF NOT EXISTS ix_rc_assentos_serie ON rc_assentos(serie, situacao);
CREATE INDEX IF NOT EXISTS ix_rc_assentos_nome ON rc_assentos(nome);
CREATE INDEX IF NOT EXISTS ix_rc_assentos_matricula ON rc_assentos(matricula);

-- A divisão tripartite que a inspeção cobra: nota, averbação e retificação
-- como ATOS, cada um com data e teor, e não como três parágrafos de um
-- campo de texto.
-- ------------------------------------------------- as pessoas do assento
--
-- Uma linha por pessoa que o assento NOMEIA e que nao e o proprio registrado
-- (esse mora em `rc_assentos.nome`).
--
-- POR QUE TABELA, E NAO `dados_json`
--   1. A CERTIDAO precisa delas em ordem e por papel: "FILIAÇÃO: pai e mãe.
--      AVÓS: PATERNOS: … MATERNOS: …". Escavar JSON para montar isso daria
--      um de-para diferente em cada lugar que precisasse.
--   2. A LISTA DE ATENÇÃO PARA FRAUDES procura pessoa por nome. Nome dentro
--      de JSON nao se procura por indice — e mae de registrado e exatamente
--      o tipo de nome que aparece numa comunicacao de fraude.
--
-- OS PAPEIS SAO OS DO ACERVO, medidos:
--   `tbFiliacao.intCodigoFiliacao` 1 = pai, 2 = mae — 2 por registro em 196
--   de 196, e ela serve as tres especies (392 nascimento, 48 casamento, 62
--   obito).
--   `tbProgenitor` e SO de nascimento (784 linhas, todas tipo 1): filiacao 1
--   sao os avos PATERNOS e 2 os MATERNOS, com o sexo separando avo de avo.
CREATE TABLE IF NOT EXISTS rc_pessoas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assento_id INTEGER NOT NULL REFERENCES rc_assentos(id),

    papel TEXT NOT NULL,                    -- PAI | MAE | AVO_PATERNO | ...
    nome TEXT NOT NULL,
    -- A BUSCA E PELA FORMA NORMALIZADA, com a funcao da casa. `UPPER()` do
    -- SQLite e ASCII e deixa `josé` como `JOSé` — e no Registro Civil quase
    -- todo nome tem acento.
    nome_norm TEXT,

    sexo TEXT,
    documento_tipo TEXT,                    -- CPF | RG
    documento_numero TEXT,

    -- A QUALIFICACAO, como o acervo a tem. A certidao de inteiro teor a
    -- reproduz; a de breve relato so usa o nome.
    profissao TEXT,
    nacionalidade TEXT,
    naturalidade_cidade TEXT,
    naturalidade_uf TEXT,
    data_nascimento TEXT,
    estado_civil TEXT,
    endereco TEXT,
    bairro TEXT,
    cidade TEXT,
    uf TEXT,
    cep TEXT,

    ordem INTEGER NOT NULL DEFAULT 1,       -- para o pai vir antes da mae
    origem TEXT NOT NULL DEFAULT 'MANUAL',  -- MANUAL | EOFICIO
    origem_chave TEXT,
    criado_em TEXT NOT NULL,
    UNIQUE(origem, origem_chave)
);

CREATE INDEX IF NOT EXISTS ix_rc_pessoas_assento
    ON rc_pessoas(assento_id, papel);
CREATE INDEX IF NOT EXISTS ix_rc_pessoas_nome ON rc_pessoas(nome_norm);
CREATE INDEX IF NOT EXISTS ix_rc_pessoas_doc
    ON rc_pessoas(documento_numero);

-- ------------------------------------------ as COMUNICAÇÕES devidas
--
-- NOVE DESTINOS, CINCO PRAZOS, e o sistema nao acompanhava nenhum. Medido no
-- Codigo de Normas do TJMA em 29/08/2026:
--
--   | destino                      | o que          | prazo         |
--   |------------------------------|----------------|---------------|
--   | SIRC/INSS (art. 225)         | tudo           | 1 dia util    |
--   | IBGE (art. 224)              | mapa trimestral| dia 8         |
--   | FUNAI (art. 253, § 2o)       | indigena       | imediato      |
--   | juiz eleitoral (art. 226, I) | obitos 16+     | 5o dia util   |
--   | Economia, Receita, Ident./MA | obitos         | 5o dia util   |
--   | Junta Militar (Lei 4.375/64) | obitos H 17-45 | mensal        |
--
-- E as sancoes sao reais: o art. 224, § 2o traz **multa de um a cinco salarios
-- minimos** «sem prejuizo da acao penal»; o art. 225, § 4o, a penalidade do
-- art. 92 da Lei 8.212/1991 **e acao regressiva do INSS**; o art. 226, § 2o, a
-- responsabilizacao do delegatario.
--
-- `UNIQUE(destino, competencia)` — uma remessa por destino por mes. Gerar duas
-- vezes o mesmo mes nao pode produzir duas obrigacoes; produz a mesma, e o que
-- muda e o conteudo, que se remonta.

CREATE TABLE IF NOT EXISTS rc_comunicacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    destino TEXT NOT NULL,                  -- ver rc_comunicacoes.DESTINOS
    competencia TEXT NOT NULL,              -- AAAA-MM
    situacao TEXT NOT NULL DEFAULT 'PENDENTE',

    -- O TEOR FICA GUARDADO INTEIRO, e nao so o nome do arquivo.
    --
    -- Art. 226, § 1o, III: «A comunicacao de obito devera ser **arquivada** em
    -- meio fisico ou virtual na serventia, **organizada por periodos mensais**,
    -- pelo prazo minimo de **dois anos**.» E o § 1o, IV: passado o prazo, so se
    -- descarta «apos comunicacao ao juiz da vara de registros publicos».
    --
    -- E o que se mostra numa correicao — e por isso o texto congela, como o
    -- teor da certidao e o do edital.
    teor TEXT,
    quantos INTEGER,                        -- quantos atos entraram
    hash_teor TEXT,

    -- Quando saiu, por onde, e a prova de que chegou.
    enviada_em TEXT,
    canal TEXT,
    protocolo TEXT,

    motivo TEXT,                            -- so quando dispensada
    prazo_ate TEXT,                         -- calculado por quem conta dia util
    criado_em TEXT NOT NULL,
    criado_por TEXT,
    resolvida_por TEXT,
    UNIQUE(destino, competencia)
);

-- ------------------------------------- o checklist obrigatorio da inspecao
--
-- **NAO E CONVENIENCIA: E EXIGENCIA COM PRAZO VENCIDO.** O Relatorio de Inspecao
-- Ordinaria de 12/08/2026 manda, na pagina 50, «aplicar **checklist
-- obrigatorio** antes da conclusao de novos atos» — prazo **zero dias**,
-- prioridade **critica**. A da pagina 49 diz o mesmo para os nascimentos.
--
-- **O QUE FICOU POR CONFERIR FICA ESCRITO**, e nao so o que foi conferido: uma
-- marca que registra apenas o bom deixa o silencio significar duas coisas — «nao
-- faltou nada» e «ninguem olhou».
CREATE TABLE IF NOT EXISTS rc_checklists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tabela TEXT NOT NULL,               -- em que tabela mora o ato
    ato_id INTEGER NOT NULL,
    especie TEXT NOT NULL,
    conferidos INTEGER NOT NULL DEFAULT 0,
    esperados INTEGER NOT NULL DEFAULT 0,
    faltaram TEXT,                      -- as chaves do que ficou por conferir
    resumo TEXT NOT NULL,               -- a frase que a correicao le
    criado_em TEXT NOT NULL,
    criado_por TEXT
);

CREATE INDEX IF NOT EXISTS ix_rc_checklists_ato
    ON rc_checklists(tabela, ato_id);

CREATE INDEX IF NOT EXISTS ix_rc_com_situacao
    ON rc_comunicacoes(situacao, competencia);

-- ------------------------------------------------ a comunicacao a FUNAI
--
-- Art. 253, § 2o: «O oficial devera comunicar **imediatamente** a FUNAI o
-- assento de nascimento do indigena, para as providencias necessarias ao
-- **registro administrativo**.»
--
-- TABELA PROPRIA, E NAO UMA LINHA EM `rc_comunicacoes`. Aquela tem
-- `UNIQUE(destino, competencia)` porque as comunicacoes do art. 226 sao
-- MENSAIS — uma por mes por destino. Esta e **por assento**, e o prazo e
-- «imediatamente»: enfia-la la faria duas criancas nascidas no mesmo mes
-- caberem numa linha so, e a segunda sumiria calada no `UNIQUE`.
CREATE TABLE IF NOT EXISTS rc_funai (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assento_id INTEGER NOT NULL REFERENCES rc_assentos(id),
    situacao TEXT NOT NULL DEFAULT 'PENDENTE',  -- ENVIADA | DISPENSADA

    -- O TEOR CONGELA, como o da certidao, o do edital e o das comunicacoes do
    -- art. 226: e o papel que a serventia afirma ter mandado, e numa correicao
    -- e ele que se mostra.
    teor TEXT,
    hash_teor TEXT,

    -- O QUE O SISTEMA NAO SABE E NAO DEDUZ. O § 1o permite que o povo seja
    -- lancado como sobrenome **a pedido do declarante** — permite, nao obriga.
    -- Tirar a etnia do sobrenome acertaria os quatro casos desta casa e
    -- erraria o primeiro que chegasse sem ele.
    etnia TEXT,
    aldeia TEXT,

    enviada_em TEXT,
    canal TEXT,
    protocolo TEXT,

    motivo TEXT,                            -- so quando dispensada
    criado_em TEXT NOT NULL,
    criado_por TEXT,
    resolvida_por TEXT,
    UNIQUE(assento_id)
);

CREATE INDEX IF NOT EXISTS ix_rc_funai_situacao
    ON rc_funai(situacao);


-- ------------------------------------------------ as ANOTACOES devidas
--
-- QUANDO ESTA CASA LAVRA UM CASAMENTO OU UM OBITO, os assentos anteriores
-- daquela pessoa tem de ser anotados — o casamento no nascimento, o obito no
-- nascimento e no casamento (art. 372 do Codigo de Normas do TJMA). Se o
-- assento anterior e daqui, anota-se aqui; se e de outra serventia, manda-se
-- comunicacao. E ha **cinco dias** para isso (art. 367).
--
-- E O TERCEIRO PRAZO DA CASA QUE NINGUEM DE FORA COBRA. O primeiro foi o do
-- SIGEF (30 dias); o segundo, a relacao mensal da Junta Militar. Este e o mais
-- curto e o mais frequente: nasce em TODO casamento e em TODO obito.
--
-- `UNIQUE(assento_id, especie_alvo)` — lavrar, corrigir e salvar de novo nao
-- pode multiplicar a obrigacao. A pendencia e declarada uma vez por (ato,
-- especie que ele obriga a anotar).

CREATE TABLE IF NOT EXISTS rc_anotacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assento_id INTEGER NOT NULL REFERENCES rc_assentos(id),
    especie_alvo TEXT NOT NULL,             -- NASCIMENTO | CASAMENTO
    situacao TEXT NOT NULL DEFAULT 'PENDENTE',

    -- Quando o registro anterior e DESTA serventia: qual assento foi anotado.
    -- O modulo NAO escreve no assento alvo — o art. 370 manda o oficial
    -- conferir a compatibilidade dos atos antes, e anotar sozinho seria decidir
    -- que dois assentos sao da mesma pessoa. Aqui fica o rastro de que ele
    -- conferiu e anotou.
    assento_alvo_id INTEGER REFERENCES rc_assentos(id),

    -- Quando e de OUTRA serventia: por onde foi, para quem, e o protocolo.
    -- A ordem dos canais e da norma — **a CRC vem primeiro** (Provimento
    -- 46/2015 do CNJ) —, e o protocolo e exigido porque a norma pede
    -- confirmacao de recebimento.
    canal TEXT,                             -- CRC | MALOTE | CARTA
    serventia_destino TEXT,
    protocolo TEXT,

    motivo TEXT,                            -- so quando dispensada
    resolvida_em TEXT,
    resolvida_por TEXT,
    criado_em TEXT NOT NULL,
    criado_por TEXT,
    UNIQUE(assento_id, especie_alvo)
);

CREATE INDEX IF NOT EXISTS ix_rc_anot_situacao
    ON rc_anotacoes(situacao, assento_id);

CREATE TABLE IF NOT EXISTS rc_atos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assento_id INTEGER NOT NULL REFERENCES rc_assentos(id),
    tipo TEXT NOT NULL,                     -- REGISTRO | AVERBACAO |
                                            -- ANOTACAO | RETIFICACAO

    servico_codigo INTEGER,
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
    fundamento TEXT,                        -- a ordem, a lei, o mandado

    origem TEXT NOT NULL DEFAULT 'MANUAL',
    origem_chave TEXT,
    importacao_id INTEGER,

    criado_em TEXT NOT NULL,
    criado_por INTEGER
);

CREATE INDEX IF NOT EXISTS ix_rc_atos_assento ON rc_atos(assento_id, tipo);
CREATE INDEX IF NOT EXISTS ix_rc_atos_selo ON rc_atos(selo);

-- **O RASTRO DO ENVIO À CRC — relato do oficial em 11/09/2026: "os assentos
-- não ficaram lá nas cargas [e] já foram enviados", sem opção de dizer
-- isso ao sistema.** A tela de carga sempre mostrava os mesmos assentos,
-- sempre — `crc_carga.pendentes_de_carga()` não tinha onde guardar «este
-- já foi». É o oposto do `ib_entregas`: aquele nasceu porque a pergunta
-- «o trimestre passado foi entregue?» não tinha resposta; esta é a mesma
-- pergunta, para a CRC.
--
-- **DOIS CANAIS, E OS DOIS PRECISAM DO RASTRO.** O envio pelo web service
-- (`WEBSERVICE`) confirma sozinho — a Central responde — e se registra
-- automaticamente; o modelo por upload no próprio site da CRC
-- (`MANUAL`) não devolve nada a este sistema, e por isso precisa do
-- clique de quem fez o upload, como "Confirmei no livro de papel" do
-- núcleo.
CREATE TABLE IF NOT EXISTS rc_crc_lotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canal TEXT NOT NULL,                    -- WEBSERVICE | MANUAL
    ambiente TEXT,                           -- HOMOLOGACAO | PRODUCAO, só no WEBSERVICE
    quantos INTEGER NOT NULL,
    resposta TEXT,                           -- resposta completa da Central, só no WEBSERVICE
    nota TEXT,                               -- só no MANUAL: onde e quando fez o upload
    enviado_em TEXT NOT NULL,
    enviado_por TEXT
);

CREATE TABLE IF NOT EXISTS rc_crc_lote_assentos (
    lote_id INTEGER NOT NULL REFERENCES rc_crc_lotes(id),
    assento_id INTEGER NOT NULL REFERENCES rc_assentos(id),
    PRIMARY KEY (lote_id, assento_id)
);

CREATE INDEX IF NOT EXISTS ix_rc_crc_lote_assentos_assento
    ON rc_crc_lote_assentos(assento_id);

-- A LAVRATURA FORÇADA — 11/10/2026. «como criar um bloqueio parcial que
-- orienta o caminho correto, mas permite, em caso de necessidade emergente,
-- fazer no modo bruto?» — o oficial.
--
-- A conferência dos dados travou, e quem responde pela serventia lavrou
-- mesmo assim, com o motivo escrito. **A trava não some: ela fica gravada
-- aqui, com o que travou e quem passou por cima**, e o agente do RCPN a
-- mostra todo dia até o assento ser arrumado. É o «modo bruto» com rastro —
-- o outro modo bruto, script direto no banco, não deixa rastro nenhum.
CREATE TABLE IF NOT EXISTS rc_lavraturas_forcadas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assento_id INTEGER NOT NULL UNIQUE REFERENCES rc_assentos(id),
    forcado_em TEXT NOT NULL,
    forcado_por TEXT NOT NULL,
    motivo TEXT NOT NULL,
    travas_json TEXT NOT NULL
);
"""

MIGRACOES: tuple[tuple[str, str, str], ...] = (
    # ------------------------------------ os tres incisos do art. 255 que
    # o assento nao guardava, e que o TERMO cobra
    #
    #   Achado em 31/08/2026, ao construir a ponte do obito: os campos do termo
    #   ja citavam o inciso de cada um — «art. 255, IX», «X», «VII» — e as tres
    #   colunas **nao existiam na tabela**. Eu as li com `get`, que nao estoura:
    #   o termo sairia sem a causa da morte, sem o lugar do sepultamento e sem o
    #   testamento, **e ninguem perceberia**, porque campo ocasional vazio some
    #   do texto de proposito.
    #
    #   Sao requisitos da norma, e nao enfeite: a causa e o que separa morte
    #   natural de violenta — o dado que o IBGE mais quer —, o sepultamento e o
    #   que a familia procura anos depois, e o testamento muda quem herda.
    ("rc_assentos", "causa_morte", "TEXT"),         # art. 255, IX
    ("rc_assentos", "local_sepultamento", "TEXT"),  # art. 255, X
    ("rc_assentos", "testamento", "TEXT"),          # art. 255, VII
    # O nome de quem atestou integra o mesmo item da causa da morte. O
    # documento profissional não substitui o nome; fica separado para a
    # certidão poder escrever os dois sem transformar "CRM 123" em pessoa.
    ("rc_assentos", "atestante", "TEXT"),            # Lei 6.015, art. 80, 8º
    ("rc_assentos", "atestante_documento", "TEXT"),  # CRM ou identificação

    # ------------------------------------------------ o que o TERMO cobra
    #
    # O TERMO E O TEXTO QUE VAI NO LIVRO, e este sistema nunca o construiu —
    # porque os 244 assentos do acervo vieram SEM TEOR NENHUM, com as tres
    # colunas de texto vazias nas tres tabelas de origem.
    #
    # Em 29/08/2026 se descobriu por que: **o E-Oficio nao guardava o teor; ele
    # o montava do modelo na hora de imprimir**. O termo existia — so nao
    # estava no banco. Os 13 modelos dele vivem em tbModelosRCPN no acervo, e o
    # termo de nascimento usa **62 campos**.
    #
    # Destes oito, nenhum existia aqui. Cada um esta no termo E numa remessa.

    # A HORA DO NASCIMENTO. Esta no termo, na certidao do modelo do CNJ e na
    # carga da CRC. O acervo a tem em strHoraNascimento e tmHoraNascimento.
    ("rc_assentos", "hora_fato", "TEXT"),

    # A COR OU RACA. O termo escreve «cor ...»; o IBGE a exige; a CRC a exige
    # com valores fechados — branca, preta, parda, amarela, indigena, ignorada.
    # Medida no acervo: strRacaCor preenchida em 15 dos 193 nascimentos —
    # pouco, e e por isso que o balcao precisa de campo para passar a perguntar.
    ("rc_assentos", "cor_raca", "TEXT"),

    # ---------------------------------------------- os gemeos, art. 234
    #
    # **`ibge_gemeo` NAO RESPONDE ESTA PERGUNTA.** Aquele campo e o do IBGE — 1
    # nao e gemeo, 2 gemeo, 3 trigemeo ou mais, 9 ignorado —, e diz **se** e
    # gemeo. O art. 234 exige **qual e a ordem de nascimento**, no assento de
    # CADA um. Usar um pelo outro faria o assento cumprir a remessa e descumprir
    # a lei: e a mesma armadilha da palavra que quer dizer duas coisas em dois
    # lugares, que este projeto ja pagou tres vezes.
    ("rc_assentos", "gemeo_ordem", "INTEGER"),
    # A LIGACAO COM O IRMAO, que o proprio modelo do E-Oficio pede: o termo diz
    # «e o primeiro gemeo a nascer, irmao de …, matricula n.o …».
    ("rc_assentos", "gemeo_irmao_id", "INTEGER"),

    # ONDE O FATO ACONTECEU, por nome e por endereco: o hospital, a casa, a via
    # publica. O acervo guarda em strNomeLocal e nos cinco campos strLN_*.
    ("rc_assentos", "local_fato_nome", "TEXT"),
    ("rc_assentos", "local_fato_endereco", "TEXT"),

    # A NATURALIDADE DECLARADA — e ela NAO e o municipio do parto.
    #
    # O termo desta casa diz, com o endereco da lei: «A naturalidade declarada
    # e de ..., na forma do art. 54, § 4o, da Lei Federal n.o 6.015/1973» — a
    # faculdade de declarar como naturalidade o municipio de residencia da mae,
    # e nao o do hospital.
    #
    # E ISSO JA CUSTOU CARO NESTA CASA, do outro lado: o E-Oficio mandava ao
    # IBGE o municipio do PARTO como residencia da mae em 27 das 28 linhas. Sao
    # TRES municipios diferentes num nascimento — onde nasceu, onde a mae mora,
    # e o que se declarou —, e confundi-los foi o defeito mais caro que a
    # comparacao com o arquivo real achou.
    ("rc_assentos", "naturalidade_declarada", "TEXT"),

    # O REGISTRO TARDIO tem forma propria (art. 46 da LRP), e o E-Oficio tem
    # modelo so dele. O acervo marca em bitRegistroTardio.
    ("rc_assentos", "registro_tardio", "INTEGER"),

    # ------------------------------------- AS QUATRO MARCAS DO OBITO
    #
    # Lidas no print do «Registro de Obito» do E-Oficio em 30/08/2026, onde sao
    # quatro caixas soltas na aba «Dados do Falecido»:
    #
    #     [x] Possui Filho  [ ] Eleitor  [ ] Desconhecido  [x] Possui Bens
    #
    # **NAO SAO ESTATISTICA: SAO GATILHOS.** Marcar «Eleitor» e o que faz a
    # comunicacao a Justica Eleitoral existir. E nenhuma delas se deduz do
    # assento: sao coisas que o declarante diz no balcao, com a familia na
    # frente. Depois viram telefonema — ou nao viram nada.
    #
    # SAO TEXT, E NAO INTEGER, DE PROPOSITO. Guardam tres estados: SIM, NAO e
    # **vazio = nao perguntado**. Um booleano faria «nao perguntei» e «ele
    # respondeu que nao» virarem o mesmo zero, e e essa ambiguidade que faz a
    # obrigacao sumir calada. E a mesma razao do `Ignorar Hora` do E-Oficio e
    # dos marcadores do SIRC. Ver `rc_marcas_do_obito`.
    ("rc_assentos", "obito_eleitor", "TEXT"),
    ("rc_assentos", "obito_possui_bens", "TEXT"),
    ("rc_assentos", "obito_possui_filho", "TEXT"),
    ("rc_assentos", "obito_desconhecido", "TEXT"),

    # O TITULO DE ELEITOR E O BENEFICIO SOCIAL, que ficam ao lado das caixas na
    # mesma tela. O titulo e o que a Justica Eleitoral usa para achar a pessoa;
    # sem ele a comunicacao vai por nome e data de nascimento, e homonimo em
    # cadastro eleitoral e problema conhecido.
    ("rc_assentos", "titulo_eleitor", "TEXT"),

    # O CPF DO REGISTRADO. **«CPF e importante no termo»** — o oficial, em
    # 30/08/2026, e o termo real desta casa o traz: «Inscrito no CPF n.º
    # 000.000.045-02.»
    #
    # E coluna do ASSENTO, e nao da pessoa, porque e o CPF **daquele
    # registro** — o que a Receita inscreveu por causa dele, e que sai na
    # certidao. O CPF da pessoa enquanto parte de outro ato mora em
    # `rc_pessoas`. Ver `rc_cpf`.
    ("rc_assentos", "cpf_registrado", "TEXT"),
    ("rc_assentos", "beneficio_social", "TEXT"),

    # A IDADE DA MAE NA OCASIAO DO PARTO. Esta no termo — «tendo a mae, na
    # ocasiao do parto, ... anos de idade» — **e na remessa do IBGE**, que a
    # cobra como campo proprio.
    #
    # NAO SE CALCULA da data de nascimento dela: o termo afirma a idade **no
    # dia do parto**, e a data de nascimento da mae falta em boa parte dos
    # assentos do acervo. Calcular onde falta daria idade errada num papel
    # assinado; guardar o que o declarante informou e o que o E-Oficio fazia.
    ("rc_pessoas", "idade_no_fato", "TEXT"),

    # O ORGAO QUE EXPEDIU O RG. O termo do obito o escreve, e a CRC o pede.
    ("rc_pessoas", "documento_orgao", "TEXT"),

    # O LIVRO FISICO DE ONDE O ASSENTO VEIO. A CERTIDAO COBROU — ela precisa
    # dizer "Livro A-22, folha 127", e o assento nao guardava o volume.
    #
    # Ele NAO sai de `nu_livros`: assento trazido do acervo nao tem livro
    # aberto no sistema, porque o livro dele e de papel e foi escriturado
    # antes. O `livro_id` do ato serve o ato NOVO; esta coluna serve o antigo.
    #
    # Medido: `strLivro` esta preenchida em 193/193 nascimentos, 20/20
    # casamentos e 31/31 obitos, e `strTipoLivro` da a letra no nascimento.
    ("rc_assentos", "livro_volume", "TEXT"),
    # O LIVRO DESTE ASSENTO ESTA POR CONFERIR NO LIVRO DE PAPEL.
    #
    # Decisao do oficial em 26/08/2026, sobre os tres casamentos que o acervo
    # separa em `intTipoRegistroLivro = 1`: "deixe como o E-Oficio guardou,
    # pendente de confirmacao quando forem consultados efetivamente".
    #
    # A marca existe para cumprir a SEGUNDA metade da frase. Deixar como esta
    # nao precisa de coluna nenhuma; avisar **no dia em que alguem abrir
    # aquele assento** precisa — e esse dia pode ser daqui a cinco anos, com
    # outro escrevente no balcao.
    ("rc_assentos", "livro_a_confirmar", "TEXT"),
    # QUANDO ALGUEM FOI AO LIVRO DE PAPEL E CONFERIU.
    #
    # Sem esta coluna, `livro_a_confirmar IS NULL` queria dizer duas coisas —
    # "nunca teve duvida" e "teve, e alguem resolveu" —, e a carga
    # RESSUSCITAVA a marca de quem ja tinha ido a estante. Marca que volta e
    # pior que marca que nunca existiu: ensina o balcao a ignorar o aviso.
    ("rc_assentos", "livro_conferido_em", "TEXT"),
    ("rc_assentos", "livro_conferido_por", "TEXT"),
    # --------------------------------- O QUE O IBGE PEDE E O ASSENTO NAO TINHA
    #
    # A remessa trimestral do IBGE (Lei 6.015/1973, art. 49) pede, do
    # nascimento, tres coisas que nao estao em lugar nenhum deste sistema — e
    # nem estavam no E-Oficio, que montava o arquivo por fora:
    #
    #   LOCAL-NASC   onde a crianca nasceu: hospital, outro estabelecimento de
    #                saude, domicilio, outro. E UM digito, e o catalogo esta em
    #                `ibge_remessa.LOCAL_DO_NASCIMENTO`.
    #   GEMEO        se foi parto unico, duplo, triplo ou mais.
    #   DNV          o numero da Declaracao de Nascido Vivo, o papel que o
    #                hospital entrega e sem o qual o registro nao se lavra.
    #
    # NENHUMA DELAS SE DEDUZ DO RESTO DO ASSENTO, e e por isso que sao coluna:
    # nao ha de onde inferir se o parto foi gemelar nem em que hospital foi.
    # Sao perguntas que se fazem ao declarante no balcao, uma vez so.
    #
    # AS OUTRAS DO LAYOUT JA EXISTEM, e por isso nao viraram coluna:
    #   - o lugar do nascimento e a naturalidade do REGISTRADO (`rc_pessoas`);
    #   - a residencia da mae e o endereco dela (`rc_pessoas.cidade/uf`);
    #   - a idade da genitora se calcula da data de nascimento dela;
    #   - o codigo IBGE de cada municipio sai de `ib_municipios`.
    #
    # Coluna para dado que ja existe e a segunda fonte que diverge da primeira.
    ("rc_assentos", "ibge_local_nascimento", "INTEGER"),
    ("rc_assentos", "ibge_gemeo", "INTEGER"),
    ("rc_assentos", "dnv", "TEXT"),
    # E O MESMO DO OUTRO LADO: o layout do obito pede `DO`, o numero da
    # Declaracao de Obito — o papel que o medico assina e sem o qual o assento
    # nao se lavra. E numero de documento, como a DNV: nao tem catalogo, nao se
    # deduz, e nao estava em lugar nenhum.
    ("rc_assentos", "numero_do", "TEXT"),
    # --------------------- A HABILITACAO DE OUTRA SERVENTIA, e o selo dela
    #
    # ITEM 14.1.6 DA TABELA: «lavratura de assento de casamento a vista de
    # certidao de habilitacao emitida por OUTRA serventia». O casal se habilita
    # la e vem casar aqui.
    #
    # ESTAS DUAS COLUNAS SAO A CHAVE DE UMA DECISAO DE DINHEIRO, e nao um
    # detalhe de cadastro. O oficial decidiu em 28/08/2026 que o casamento leva
    # UM selo so, comprado na habilitacao e reaproveitado no assento — e que,
    # quando a habilitacao e de fora, o assento **compra selo proprio, citando
    # o de la**.
    #
    #   `habilitacao_serventia` PREENCHIDA  -> veio de fora: o assento compra.
    #   `habilitacao_serventia` VAZIA       -> e daqui: o assento reaproveita.
    #
    # Os dois caminhos sao exclusivos por construcao, e o que os separa e uma
    # coisa que o escrevente RESPONDE na tela — nao uma deducao do sistema.
    # Deduzir aqui seria arriscar cobrar do casal duas vezes.
    #
    # `habilitacao_selo` e opcional porque `seloReferencia` e opcional no
    # contrato: nem toda certidao de habilitacao de fora traz o selo legivel, e
    # recusar o casamento por causa disso seria impedir o ato pelo acessorio.
    ("rc_assentos", "habilitacao_serventia", "TEXT"),
    ("rc_assentos", "habilitacao_selo", "TEXT"),
    # ------------------ A PESSOA DE QUEM O ASSENTO É, e nao so os pais dela
    #
    # ATE 28/08/2026 `rc_pessoas` guardava PAI, MAE e AVOS — que a carga trouxe
    # porque a certidao de nascimento os cobrou — e NAO guardava o registrado,
    # os nubentes nem o falecido. O assento tinha o NOME deles (em
    # `rc_assentos.nome`) e mais nada.
    #
    # ISSO TRAVAVA DUAS COISAS AO MESMO TEMPO, e por isso e uma passada so:
    #   - a REMESSA DO IBGE pede sexo, data de nascimento, naturalidade,
    #     residencia e estado civil dessas pessoas;
    #   - a CERTIDAO de casamento e a de obito descrevem essas mesmas pessoas,
    #     e sem elas as duas saem incompletas.
    #
    # AS COLUNAS QUE FALTAVAM SAO DUAS, e o resto ja existia:
    #
    #   `nome_pos`            o nome que o nubente passa a usar depois do
    #                         casamento. Medido nos 20 casamentos do acervo:
    #                         **o segundo conjuge muda de nome em 17 deles**, e
    #                         o primeiro em 2. E o nome que a certidao de
    #                         casamento tem de mostrar, e guardar so um dos
    #                         dois perderia o outro.
    #
    #                         (Eu havia escrito «13» aqui, de cabeca, antes de
    #                         contar. Comentario que afirma medicao sem ter
    #                         medido e pior que comentario nenhum: ele existe
    #                         justamente para dispensar a conferencia.)
    #
    #   `naturalidade_pais`   o CODIGO do pais de nascimento (`076` = Brasil),
    #                         que o IBGE pede quando a UF e `98` (estrangeiro).
    #                         Nao e a `nacionalidade`, que e texto livre
    #                         («BRASILEIRA») e serve a certidao: sao duas
    #                         coisas com nomes parecidos, e o acervo guarda as
    #                         duas em colunas separadas — `strNacionalidade` e
    #                         `strCodigoPais`.
    ("rc_pessoas", "nome_pos", "TEXT"),
    ("rc_pessoas", "naturalidade_pais", "TEXT"),
    # A NATUREZA E O LOCAL DO OBITO — e a correcao de uma decisao minha de
    # horas antes.
    #
    #   Eu havia deixado as duas de fora dizendo que os catalogos «nao foram
    #   medidos», e que campo sem catalogo e campo que alguem preenche por
    #   palpite. Estava certo na regra e errado no fato: os catalogos existiam,
    #   e foram fechados no mesmo dia por DOIS caminhos que se conferiram um ao
    #   outro —
    #
    #     MEDIDOS nas 13 linhas de obito que esta casa exportou, cruzadas com
    #     os 31 obitos do acervo: Hospital -> 1, Via Publica -> 4, Outros -> 5;
    #     e a unica linha com natureza 2 e justamente a morte em via publica de
    #     um homem de 26 anos, o que so encaixa com «violenta».
    #
    #     CONFIRMADOS pela especificacao oficial do IBGE (COPRE/GESIP,
    #     08/01/2015), que traz as listas inteiras.
    #
    #   `ibge_remessa.NATUREZA_DO_OBITO` e `LOCAL_DO_OBITO` guardam as duas.
    ("rc_assentos", "ibge_natureza_obito", "INTEGER"),
    ("rc_assentos", "ibge_local_obito", "INTEGER"),
    # O REGIME DE BENS E CAMPO OBRIGATORIO DA CERTIDAO DE CASAMENTO — Lei
    # 6.015/1973, art. 70, item 6 — e nao estava em lugar nenhum do ato novo.
    #
    #   Ele existia so dentro do blob do acervo (`strRegimeCasamento`), e por
    #   isso a certidao de um casamento lavrado por este sistema saia com o
    #   campo em branco. `hc_habilitacoes.regime` guarda o que o casal escolheu
    #   no processo; esta coluna guarda o que o ASSENTO afirma — e sao coisas
    #   diferentes, porque o casal pode mudar de regime entre a habilitacao e a
    #   celebracao.
    ("rc_assentos", "regime_bens", "TEXT"),
    # --------------------------- O TERMO ASSINADO, DIGITALIZADO — problema #121
    #
    # Pedido do oficial em 07/10/2026: «a obrigatoriedade de digitalizar o
    # termo no sistema depois da lavratura de registro, com visualização do
    # termo assinado [...] nos moldes que temos no RI». As cinco primeiras são
    # as `digi_*` de `ri_matriculas`, com o mesmo sentido; `digi_origem` é
    # nova e diz QUEM pôs o arquivo — `BALCAO` (pessoa, pela ficha) ou a
    # origem da carga (`ACERVO_TRANSCRITO`). A carga nunca passa por cima do
    # que uma pessoa enviou. Ver `rc_digitalizacao`.
    ("rc_assentos", "digi_path", "TEXT"),
    ("rc_assentos", "digi_nome", "TEXT"),
    ("rc_assentos", "digi_sha256", "TEXT"),
    ("rc_assentos", "digi_em", "TEXT"),
    ("rc_assentos", "digi_por", "TEXT"),
    ("rc_assentos", "digi_origem", "TEXT"),
    # ------------------------------------------- o que a lei pede e não tinha
    # onde ser informado — 13/10/2026, ordem do oficial («quero acrescentar»),
    # depois da reorganização do formulário. **Todos opcionais e
    # condicionais** («cuidar para não exigir o preenchimento deles para
    # todos os casos»): cada um só aparece na tela quando a situação existe,
    # e o termo só traz a frase quando há dado.
    #
    # ÓBITO — art. 80 da Lei 6.015/1973; art. 255 do Código de Normas.
    ("rc_assentos", "obito_conjuge_nome", "TEXT"),       # IV
    ("rc_assentos", "obito_conjuge_situacao", "TEXT"),   # IV: SOBREVIVENTE | PRE_MORTO
    ("rc_assentos", "obito_conjuge_cartorio", "TEXT"),   # IV: o cartório do casamento
    ("rc_assentos", "obito_filhos", "TEXT"),             # VIII: um por linha, nome e idade
    ("rc_assentos", "obito_herdeiros_menores", "TEXT"),  # XI: SIM | NAO | vazio
    # CASAMENTO — art. 70 da Lei 6.015/1973; art. 284 do Código de Normas.
    ("rc_assentos", "nubente1_conjuge_anterior", "TEXT"),   # III
    ("rc_assentos", "nubente1_dissolucao_data", "TEXT"),    # III
    ("rc_assentos", "nubente2_conjuge_anterior", "TEXT"),   # III
    ("rc_assentos", "nubente2_dissolucao_data", "TEXT"),    # III
    ("rc_assentos", "proclamas_data", "TEXT"),              # IV, habilitação de fora
    ("rc_assentos", "documentos_apresentados", "TEXT"),     # V, habilitação de fora
    ("rc_assentos", "pacto_data", "TEXT"),                  # VII
    ("rc_assentos", "pacto_serventia", "TEXT"),             # VII
    # NASCIMENTO — art. 54, 7º: «lugar e cartório onde se casaram» os pais.
    ("rc_assentos", "pais_casamento_lugar", "TEXT"),
    ("rc_assentos", "pais_casamento_cartorio", "TEXT"),
    # ------------------------------------------------------------ o LIVRO E
    # 13/10/2026, ordem do oficial: «preparemos o ambiente para viabilizar o
    # próximo registro e todos os modelos, nos moldes da casa». O que a lei
    # pede de cada registro do Livro E e não tinha onde ser informado. As
    # pessoas (curador, tutor, requerente, companheiros, pais) vão em
    # `rc_pessoas`; aqui fica o que é do TÍTULO e do fato.
    #
    # O TÍTULO QUE SE REGISTRA — sentença (arts. 90, 92, 94 e 94-A), escritura
    # (art. 90; art. 94-A, VI) ou termo declaratório (art. 94-A).
    ("rc_assentos", "livro_e_titulo", "TEXT"),             # SENTENCA | ESCRITURA | TERMO
    ("rc_assentos", "livro_e_titulo_data", "TEXT"),        # data da sentença/escritura/termo
    ("rc_assentos", "livro_e_juizo", "TEXT"),              # vara (arts. 92, 3º; 94, 5º)
    ("rc_assentos", "livro_e_juiz", "TEXT"),               # nome do juiz
    ("rc_assentos", "livro_e_processo", "TEXT"),
    ("rc_assentos", "livro_e_transito", "TEXT"),           # trânsito em julgado (94-A, V)
    ("rc_assentos", "livro_e_escritura_livro", "TEXT"),    # 94-A, VI
    ("rc_assentos", "livro_e_escritura_folha", "TEXT"),
    ("rc_assentos", "livro_e_tabelionato", "TEXT"),
    # O QUE A LEI PEDE DO TITULAR E DO FATO.
    ("rc_assentos", "livro_e_registro_nascimento", "TEXT"),  # data e cartório
    ("rc_assentos", "livro_e_registro_casamento", "TEXT"),   # idem; na UE, as anteriores
    ("rc_assentos", "livro_e_conjuge", "TEXT"),            # arts. 92, 2º; 94, 2º
    ("rc_assentos", "livro_e_causa", "TEXT"),              # art. 92, 5º
    ("rc_assentos", "livro_e_limites", "TEXT"),            # arts. 92, 6º; 94, 6º
    ("rc_assentos", "livro_e_internacao", "TEXT"),         # art. 92, 7º
    ("rc_assentos", "livro_e_ausencia_tempo", "TEXT"),     # art. 94, 3º
    ("rc_assentos", "livro_e_uniao_inicio", "TEXT"),       # data de início da união
    # QUEM PRESIDIU O CASAMENTO — 15/10/2026, decisão do oficial ao responder o
    # relato #124: o juiz de paz (presidente do ato, Lei 6.015/1973, art. 70)
    # assina o termo, e o nome dele sai embaixo da linha da folha. Até aqui não
    # havia onde guardá-lo: só o acervo trazia `strNomeCelebrante`, no blob.
    # Só o casamento CIVIL — no religioso quem presidiu foi o celebrante.
    # Opcional; sem índice, porque ninguém procura assento por ele.
    ("rc_assentos", "juiz_de_paz", "TEXT"),
)

#: O INSTANTE A PARTIR DO QUAL O REGISTRO LAVRADO TEM DE TER O TERMO
#: DIGITALIZADO (problema #121). Semeado UMA vez — na primeira abertura do
#: banco com esta versão —, e nunca regravado: é o «a partir da instalação».
#: Os registros lavrados antes não viram atraso de um dia para o outro; se o
#: oficial quiser que entrem, muda-se a data nesta configuração.
CHAVE_DO_CORTE_DA_DIGITALIZACAO = "rc_digitalizacao_obrigatoria_desde"


def _semear_corte_da_digitalizacao(con: sqlite3.Connection) -> None:
    """Grava o corte se ainda não houver. Sem `settings` (banco de ensaio
    montado só com o RCPN), não faz nada — e a obrigação fica desligada."""
    if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                       "AND name='settings'").fetchone():
        return
    from datetime import datetime
    con.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                (CHAVE_DO_CORTE_DA_DIGITALIZACAO,
                 datetime.now().replace(microsecond=0).isoformat()))


def init_rc_schema(con: sqlite3.Connection) -> None:
    """Cria as tabelas do RCPN. Idempotente. Chamar DEPOIS do núcleo."""
    con.executescript(SCHEMA)
    for tabela, coluna, tipo in MIGRACOES:
        existentes = {linha[1] for linha in con.execute(f"PRAGMA table_info({tabela})")}
        if coluna not in existentes:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
    _semear_corte_da_digitalizacao(con)
