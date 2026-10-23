"""
Tabelionato de Notas — esquema de dados.

O QUE ESTE MODULO GUARDA
    O balcao de notas e, em volume, quase todo reconhecimento de firma e
    autenticacao de copia: no acervo do E-Oficio sao 13.209 reconhecimentos e
    3.539 autenticacoes contra 258 atos de livro. O esquema reflete isso — o
    cartao de autografo e o reconhecimento tem tratamento de primeira classe,
    e o livro de notas vem em seguida.

COMO SE LIGAM AS COISAS
    cartao de autografo  quem assina, com a assinatura digitalizada ao lado
      -> reconhecimento  cada firma reconhecida, com selo e codigo de seguranca
      -> presenca        o comparecimento, quando o reconhecimento e por
                         autenticidade e a pessoa assina na hora
    autenticacao         copia conferida com o original, por folha
    livro / ato          escritura, procuracao, testamento, ata notarial

    No E-Oficio a ligacao entre o reconhecimento e o cartao e feita pelo SELO,
    nao por um numero de registro — conferi nos 13.199 pares e casam todos,
    menos um de cada lado. Aqui a ligacao e por chave propria, e o selo fica
    como o identificador externo que ele e.

DE ONDE VEIO O DESENHO
    Do esquema real do E-Oficio, exportado em 14/08/2026, e nao de suposicao.
    A tabela tbFirma tem 62 colunas e tbRegistroESC tem 84; nem tudo aproveita,
    mas o que aproveita esta aqui com o nome que se usa no balcao.

SOBRE AS CENTRAIS
    Os dominios da CENSEC (CEP, CESDI, RCTO) e da DOI vem prontos do E-Oficio,
    com os codigos oficiais. Ficam em tabelas de dominio proprias, e o ato ja
    nasce com os campos que a remessa exige — que e a razao de tbRegistroESC
    ter 84 colunas: quem deixa para preencher depois, nao preenche.

SOBRE DADO PESSOAL
    O cartao de autografo e o cadastro mais sensivel do sistema: nome, CPF, RG,
    filiacao, endereco de casa e do trabalho, telefone, e-mail. Sai mascarado
    em qualquer papel que deixe o cartorio, pelo mesmo `serventia.py` que ja
    faz isso no recibo e no protocolo.
"""
from __future__ import annotations

import re
from typing import Any

import modelos_da_casa as MODELOS
from bd_nativo import banco

# --------------------------------------------------------------- dominios

ESPECIES_RECONHECIMENTO = {
    "SEMELHANCA": "Por semelhança — confronto com o cartão de autógrafo",
    "AUTENTICIDADE": "Por autenticidade — a pessoa assina na presença do tabelião",
}

# Codigos da tabela do TJMA, ja carregados em cx_servicos. Ficam aqui para que
# o lancamento saia com o emolumento certo sem ninguem digitar codigo.
SERVICOS = {
    # O CADASTRO DO AUTOGRAFO E ATO, e cobra o seu item — medido em
    # 27/08/2026: os 2.667 selos de `/selo/notas/cartao-assinatura` levam
    # `13.17.1` nos 2.667, e no cadastro desta casa esse item e o servico 412.
    "CARTAO": 412,            # 13.17.1 registro de firma: cadastro
    "SEMELHANCA": 413,        # 13.17.2 reconhecimento por assinatura
    "AUTENTICIDADE": 413,     # mesmo item; a especie muda o texto, nao o preco
    "VEICULO": 414,           # 13.17.3 transferencia de veiculo
    "FINANCEIRO": 416,        # 13.17.4 documento com conteudo financeiro
    "AUTENTICACAO": 415,      # 13.18 autenticacao por pagina
    # Mesmo item 413: cx_servicos cobre «Reconhecimento de sinal, letra
    # e firma». Abertura do sinal NAO usa isto — so o reconhecimento
    # autonomo (nt_sinais_reconhecimentos).
    "SINAL": 413,             # 13.17.2 reconhecimento de sinal publico
}

# O TEXTO DE CADA AUTENTICACAO saiu daqui no LF06D (19/10/2026): mora em
# `modelos_padrao/notas/NOTAS_AUTENTICACAO*.txt` e chega pela base dos padroes
# (ajuste da casa -> padrao). Aqui fica o que e do codigo: o papel de cada tipo
# e o item da tabela que ele cobra. `TIPOS_AUTENTICACAO` — `{tipo: (texto,
# item)}`, o nome antigo — continua respondendo, lido da base (`__getattr__`).
AUTENTICACOES = {
    "PADRAO": ("NOTAS_AUTENTICACAO", "13.18"),
    "INTERNET": ("NOTAS_AUTENTICACAO_INTERNET", "43.04"),
}

# Livros do tabelionato, na nomenclatura do Codigo de Normas da CGJ/MA.
TIPOS_LIVRO = {
    "ESCRITURA": "Livro de Escrituras",
    "PROCURACAO": "Livro de Procurações",
    "TESTAMENTO": "Livro de Testamentos Públicos",
    "TESTAMENTO_CERRADO": "Livro de Registro de Testamentos Cerrados",
    "ATA": "Livro de Atas Notariais",
    "SUBSTABELECIMENTO": "Livro de Substabelecimentos",
}

TIPOS_ATO = {
    "ESCRITURA": "Escritura pública",
    "PROCURACAO": "Procuração",
    "PROCURACAO_PREVIDENCIARIA": "Procuração para fins previdenciários",
    "SUBSTABELECIMENTO": "Substabelecimento",
    "REVOGACAO": "Revogação de procuração",
    "RENUNCIA": "Renúncia de procuração",
    "TESTAMENTO": "Testamento público",
    "TESTAMENTO_CERRADO": "Testamento cerrado — auto de aprovação",
    "ATA": "Ata notarial",
    "ATA_USUCAPIAO": "Ata notarial para usucapião extrajudicial",
}

SITUACOES_ATO = {
    # EM_LAVRATURA e a situacao em que o ato NASCE, desde a versao 3.3.8.
    #
    # POR QUE ELA PRECISOU EXISTIR
    #     Antes o ato ja nascia LAVRADO, e a folha era digitada a mao. Com a
    #     numeracao automatica a folha e ATRIBUIDA, e atribuir folha a um ato
    #     que talvez nao se lavre deixaria BURACO no livro — folha reservada e
    #     nunca usada, que ninguem explica em correicao.
    #
    #     Entao o ato nasce sem livro, sem folha e sem termo; recebe os tres
    #     quando o teor esta pronto e se sabe quantas paginas ele tem. So ai
    #     vira LAVRADO. O acervo importado ja entra LAVRADO, como sempre foi.
    #
    #     A remessa as centrais filtra por `situacao = 'LAVRADO'`
    #     (notas_censec.py), entao o rascunho fica de fora sozinho.
    "EM_LAVRATURA": "Em lavratura — ainda não lançado no livro",
    "SUSPENSO_SELO": "Suspenso — selo não emitido",
    "LAVRADO": "Lavrado",
    "SEM_EFEITO": "Sem efeito",
    "REVOGADO": "Revogado",
    "CANCELADO": "Cancelado",
}

# ------------------------------------------------ anotacao a margem
#
# A ANOTACAO A MARGEM E O QUE FAZ A CERTIDAO DIZER A VERDADE
#     Lavrar a revogacao num livro e deixar a procuracao de 2024 intacta no
#     outro produz duas verdades no mesmo acervo. Quem pede certidao da
#     procuracao recebe uma certidao que nao diz que ela foi revogada — e a
#     certidao do ato notarial vale pelo que o livro diz.
#
#     A tabela `nt_ato_anotacoes` existia no esquema desde o inicio e nao era
#     usada por linha nenhuma do sistema. Isto e o dominio que faltava.
TIPOS_ANOTACAO = {
    "REVOGACAO": "Revogação",
    "RENUNCIA": "Renúncia do mandatário",
    "SUBSTABELECIMENTO": "Substabelecimento",
    "RETIFICACAO": "Retificação",
    "ADITAMENTO": "Aditamento",
    "CANCELAMENTO": "Cancelamento",
    "ORDEM_JUDICIAL": "Ordem judicial",
    "OUTRA": "Outra anotação",
}

# O que a anotacao faz com a SITUACAO do ato anotado.
#
# SOBRE A RENUNCIA CAIR EM 'REVOGADO'
#     Nao e a mesma coisa: revogacao e do outorgante, renuncia e do mandatario
#     (Codigo Civil, art. 682, I e II). Mas o efeito no acervo e o mesmo — o
#     mandato deixa de estar em vigor —, e `SITUACOES_ATO` nao tem verbo para
#     cada causa. A situacao e a marca grossa; QUAL das duas foi esta na
#     anotacao, que e de onde a certidao tira o texto. Inventar uma situacao
#     nova aqui quebraria a separacao da remessa, que filtra por 'LAVRADO'.
#
# SOBRE O SUBSTABELECIMENTO NAO ENTRAR NESTA LISTA
#     Substabelecer nao extingue a procuracao: com reserva, o outorgado
#     continua com os poderes; sem reserva, os poderes passam, mas a
#     procuracao segue sendo o titulo de onde eles vieram. A anotacao se faz
#     — e obrigatoria para quem le o livro — e a situacao nao muda.
ANOTACAO_ENCERRA = {
    "REVOGACAO": "REVOGADO",
    "RENUNCIA": "REVOGADO",
    "CANCELAMENTO": "CANCELADO",
}

# Ato que, ao ser lavrado, PEDE anotacao a margem de um ato anterior.
ATO_PEDE_ANOTACAO = {
    "REVOGACAO": "REVOGACAO",
    "RENUNCIA": "RENUNCIA",
    "SUBSTABELECIMENTO": "SUBSTABELECIMENTO",
}

# Centrais que recebem remessa.
CENTRAIS = {
    "CEP": "CENSEC — Central de Escrituras e Procurações",
    "CESDI": "CENSEC — Separações, Divórcios e Inventários",
    "RCTO": "CENSEC — Registro Central de Testamentos On-line",
    # Quarto modulo da CENSEC, achado no art. 880 do Codigo de Normas: a
    # escritura de Diretiva Antecipada de Vontade tem comunicacao OBRIGATORIA,
    # GRATUITA E SIGILOSA ao RCDUV. A DAV vai as duas: a CEP, como escritura de
    # natureza 55, e o RCDUV, pela comunicacao propria.
    "RCDUV": "CENSEC — Registro Central de Disposições de Última Vontade",
    "DOI": "Receita Federal — Declaração de Operações Imobiliárias",
    "ENOTARIADO": "e-Notariado — atos notariais eletrônicos",
}

# Destas o sistema sabe montar a carga. As demais estao em CENTRAIS porque
# existem e obrigam a serventia — nao porque ja estejam construidas. Separar as
# duas listas evita a tela oferecer um botao que geraria arquivo em branco.
CENTRAIS_COM_REMESSA = ("CEP", "CESDI", "RCTO")

SITUACOES_REMESSA = {
    "PENDENTE": "Ainda não enviada",
    "GERADA": "Arquivo gerado, aguardando envio",
    "ENVIADA": "Enviada",
    "CONFIRMADA": "Confirmada pela central",
    "REJEITADA": "Rejeitada",
}


SCHEMA = """
-- ------------------------------------------------ cartao de autografo

CREATE TABLE IF NOT EXISTS nt_cartoes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    numero INTEGER,                       -- numero do cartao na serventia
    nome TEXT NOT NULL,
    nome_norm TEXT,                       -- busca sem acento e sem caixa
    tipo_pessoa TEXT NOT NULL DEFAULT 'F',-- F fisica, J juridica
    documento TEXT,                       -- CPF ou CNPJ, so digitos
    rg TEXT,
    rg_orgao TEXT,
    rg_uf TEXT,
    rg_emissao TEXT,
    nascimento TEXT,
    sexo TEXT,
    nacionalidade TEXT,
    naturalidade TEXT,
    estado_civil TEXT,
    conjuge TEXT,
    profissao TEXT,
    pai TEXT,
    mae TEXT,
    endereco TEXT,
    endereco_numero TEXT,
    endereco_complemento TEXT,
    bairro TEXT,
    cidade TEXT,
    uf TEXT,
    cep TEXT,
    telefone TEXT,
    celular TEXT,
    email TEXT,
    local_trabalho TEXT,
    endereco_trabalho TEXT,
    como_assina TEXT,                     -- a forma abreviada que ela usa
    -- Prevencao a lavagem de dinheiro: Lei 9.613/98 e Provimento CNJ 88/2019
    -- exigem que a serventia saiba se o cliente e pessoa exposta.
    pessoa_exposta INTEGER NOT NULL DEFAULT 0,
    restricao_terrorismo INTEGER NOT NULL DEFAULT 0,
    -- Bloqueio: cartao bloqueado nao serve para reconhecer.
    bloqueado INTEGER NOT NULL DEFAULT 0,
    motivo_bloqueio TEXT,
    bloqueado_em TEXT,
    bloqueado_por TEXT,
    somente_autenticidade INTEGER NOT NULL DEFAULT 0,
    ativo INTEGER NOT NULL DEFAULT 1,
    biometria TEXT,                       -- molde do leitor, como veio
    biometria_dedo INTEGER,
    selo_abertura TEXT,
    observacao TEXT,
    abertura TEXT,                        -- data de abertura do cartao
    origem TEXT NOT NULL DEFAULT 'MANUAL',
    origem_chave TEXT,
    importacao_id INTEGER,
    criado_em TEXT NOT NULL,
    criado_por TEXT,
    atualizado_em TEXT,
    atualizado_por TEXT
);

CREATE INDEX IF NOT EXISTS ix_nt_cartoes_nome ON nt_cartoes(nome_norm);
CREATE INDEX IF NOT EXISTS ix_nt_cartoes_doc ON nt_cartoes(documento);
CREATE INDEX IF NOT EXISTS ix_nt_cartoes_ativo ON nt_cartoes(ativo, bloqueado);

-- Imagem da assinatura. No E-Oficio ela mora em disco, em \\\\servidor\\C11\\
-- Firmas, e o banco guarda so o nome do arquivo. Aqui guardamos os dois: o
-- caminho de origem, para nao perder a referencia, e a copia interna, que
-- entra no backup e sobrevive ao desligamento do E-Oficio.
CREATE TABLE IF NOT EXISTS nt_cartao_imagens (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    cartao_id INTEGER NOT NULL,
    ordem INTEGER NOT NULL DEFAULT 1,
    nome_arquivo TEXT,
    caminho TEXT,
    caminho_interno TEXT,
    sha256 TEXT,
    bytes INTEGER,
    favorita INTEGER NOT NULL DEFAULT 0,
    data TEXT,
    copiado_em TEXT,
    criado_em TEXT NOT NULL,
    FOREIGN KEY(cartao_id) REFERENCES nt_cartoes(id)
);

CREATE INDEX IF NOT EXISTS ix_nt_img_cartao ON nt_cartao_imagens(cartao_id, ordem);

-- Foto e digitais do CADASTRO, nao da ficha de papel. A ficha impressa nao
-- muda (decisao de 31/08/2026): estas imagens moram na pessoa e vao ao CCN
-- depois. NAO reusa nt_cartoes.biometria — aqueles 462 moldes do E-Oficio
-- nao sao imagem e nao servem ao CCN. Blob nunca entra no SQLite.
--
-- UNIQUE(cartao_id, especie, dedo) NA TABELA NAO TRAVA DUAS FOTOS: no SQLite
-- NULL nao se iguala a NULL, e a foto tem dedo NULL. Duas indices parciais
-- fazem o que a regra pede — uma foto e uma imagem por dedo.
CREATE TABLE IF NOT EXISTS nt_cadastro_imagens (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    cartao_id INTEGER NOT NULL,
    especie TEXT NOT NULL,                -- FOTO | DIGITAL
    dedo INTEGER,                         -- NULL na foto; 1, 2, 6 ou 7 na digital
    caminho TEXT NOT NULL,
    nome_arquivo TEXT,
    sha256 TEXT,
    bytes INTEGER,
    presencial INTEGER NOT NULL DEFAULT 1,-- fotoVerificada no CCN
    colhido_em TEXT,
    colhido_por TEXT,
    FOREIGN KEY(cartao_id) REFERENCES nt_cartoes(id)
);

CREATE INDEX IF NOT EXISTS ix_nt_cadastro_img_cartao
    ON nt_cadastro_imagens(cartao_id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_nt_cadastro_img_foto
    ON nt_cadastro_imagens(cartao_id)
    WHERE especie = 'FOTO';

CREATE UNIQUE INDEX IF NOT EXISTS ux_nt_cadastro_img_digital
    ON nt_cadastro_imagens(cartao_id, dedo)
    WHERE especie = 'DIGITAL';


-- ------------------------------------------------ reconhecimento de firma

CREATE TABLE IF NOT EXISTS nt_reconhecimentos (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    data TEXT NOT NULL,
    hora TEXT,
    especie TEXT NOT NULL DEFAULT 'SEMELHANCA',
    selo TEXT,
    codigo_seguranca TEXT,
    servico_codigo INTEGER,               -- item da tabela do TJMA
    quantidade INTEGER NOT NULL DEFAULT 1,-- firmas na mesma etiqueta
    documento_descricao TEXT,             -- o que foi apresentado
    documento_tipo TEXT,
    veiculo_placa TEXT,                   -- reconhecimento de DUT
    conteudo_financeiro INTEGER NOT NULL DEFAULT 0,
    sinal_publico INTEGER NOT NULL DEFAULT 0,
    texto TEXT,                           -- o teor que sai impresso
    oficial TEXT,                         -- quem reconheceu
    oficial_funcao TEXT,
    protocolo_id INTEGER,                 -- protocolo do caixa, quando houver
    lancamento_id INTEGER,
    cancelado INTEGER NOT NULL DEFAULT 0,
    motivo_cancelamento TEXT,
    cancelado_em TEXT,
    cancelado_por TEXT,
    origem TEXT NOT NULL DEFAULT 'MANUAL',
    origem_chave TEXT,
    importacao_id INTEGER,
    criado_em TEXT NOT NULL,
    criado_por TEXT
);

CREATE INDEX IF NOT EXISTS ix_nt_rec_data ON nt_reconhecimentos(data);
CREATE INDEX IF NOT EXISTS ix_nt_rec_selo ON nt_reconhecimentos(selo);

-- Quem assinou. Uma etiqueta pode reconhecer mais de uma firma.
CREATE TABLE IF NOT EXISTS nt_reconhecimento_partes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    reconhecimento_id INTEGER NOT NULL,
    cartao_id INTEGER,
    nome TEXT,                            -- congelado no momento do ato
    documento TEXT,
    papel TEXT,                           -- vendedor, comprador, outorgante...
    criado_em TEXT NOT NULL,
    FOREIGN KEY(reconhecimento_id) REFERENCES nt_reconhecimentos(id),
    FOREIGN KEY(cartao_id) REFERENCES nt_cartoes(id)
);

CREATE INDEX IF NOT EXISTS ix_nt_recp_rec ON nt_reconhecimento_partes(reconhecimento_id);
CREATE INDEX IF NOT EXISTS ix_nt_recp_cartao ON nt_reconhecimento_partes(cartao_id);

-- Termo de presenca: quando o reconhecimento e por autenticidade, a pessoa
-- comparece e assina diante do tabeliao. O termo e a prova disso.
CREATE TABLE IF NOT EXISTS nt_presencas (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    data TEXT NOT NULL,
    ordem INTEGER,
    nome TEXT NOT NULL,
    documento TEXT,
    cartao_id INTEGER,
    reconhecimento_id INTEGER,
    selo TEXT,
    quantidade INTEGER NOT NULL DEFAULT 1,
    conteudo TEXT,
    oficial TEXT,
    origem TEXT NOT NULL DEFAULT 'MANUAL',
    origem_chave TEXT,
    importacao_id INTEGER,
    criado_em TEXT NOT NULL,
    FOREIGN KEY(cartao_id) REFERENCES nt_cartoes(id),
    FOREIGN KEY(reconhecimento_id) REFERENCES nt_reconhecimentos(id)
);

CREATE INDEX IF NOT EXISTS ix_nt_presenca_data ON nt_presencas(data);

-- ------------------------------------------------ autenticacao de copia

CREATE TABLE IF NOT EXISTS nt_autenticacoes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    data TEXT NOT NULL,
    hora TEXT,
    tipo TEXT NOT NULL DEFAULT 'PADRAO',  -- PADRAO ou INTERNET
    selo TEXT,
    codigo_seguranca TEXT,
    servico_codigo INTEGER,
    folhas INTEGER NOT NULL DEFAULT 1,    -- a tabela cobra por pagina
    documento_descricao TEXT,
    documento_tipo TEXT,
    apresentante TEXT,
    apresentante_documento TEXT,
    texto TEXT,
    oficial TEXT,
    oficial_funcao TEXT,
    protocolo_id INTEGER,
    lancamento_id INTEGER,
    cancelado INTEGER NOT NULL DEFAULT 0,
    motivo_cancelamento TEXT,
    origem TEXT NOT NULL DEFAULT 'MANUAL',
    origem_chave TEXT,
    importacao_id INTEGER,
    criado_em TEXT NOT NULL,
    criado_por TEXT
);

CREATE INDEX IF NOT EXISTS ix_nt_aut_data ON nt_autenticacoes(data);
CREATE INDEX IF NOT EXISTS ix_nt_aut_selo ON nt_autenticacoes(selo);

-- ------------------------------------------------ livros e atos

CREATE TABLE IF NOT EXISTS nt_livros (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tipo TEXT NOT NULL,                   -- ESCRITURA, PROCURACAO, ...
    numero TEXT NOT NULL,
    complemento TEXT NOT NULL DEFAULT '',
    descricao TEXT,
    folhas INTEGER,                       -- quantas folhas o livro comporta
    folha_atual INTEGER,
    abertura TEXT,
    encerramento TEXT,
    termo_abertura TEXT,                  -- o teor do termo, art. 4 da 8.935
    termo_encerramento TEXT,
    encerrado INTEGER NOT NULL DEFAULT 0,
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT NOT NULL,
    UNIQUE(tipo, numero, complemento)
);

CREATE TABLE IF NOT EXISTS nt_atos (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tipo TEXT NOT NULL,                   -- ESCRITURA, PROCURACAO, ...
    numero_ordem INTEGER,                 -- numeracao continua do tabelionato
    livro_id INTEGER,
    livro TEXT,                           -- congelado, para o acervo antigo
    folha TEXT,
    folha_final TEXT,
    data TEXT NOT NULL,
    hora TEXT,
    situacao TEXT NOT NULL DEFAULT 'LAVRADO',
    natureza TEXT,                        -- compra e venda, doacao, ...
    natureza_censec INTEGER,              -- codigo da CENSEC
    modelo_codigo TEXT,
    interessado TEXT,
    teor TEXT,
    teor_formato TEXT NOT NULL DEFAULT 'html',
    traslado TEXT,
    folhas INTEGER,
    selo TEXT,
    selo_arquivamento TEXT,
    valor_transacao INTEGER,              -- CENTAVOS, nunca ponto flutuante
    valor_lavrado INTEGER,
    base_itbi INTEGER,
    -- assinatura e testemunha
    assinado_serventia INTEGER NOT NULL DEFAULT 0,
    dispensou_testemunha INTEGER NOT NULL DEFAULT 0,
    local_assinatura TEXT,
    -- ato anterior, exigido pela CENSEC nas revogacoes e substabelecimentos
    anterior_livro TEXT,
    anterior_folha TEXT,
    anterior_data TEXT,
    anterior_cartorio TEXT,
    anterior_cidade TEXT,
    anterior_uf TEXT,
    -- CESDI: separacao, divorcio e inventario
    casamento_data TEXT,
    regime_bens TEXT,
    filhos_menores INTEGER,
    filhos_maiores INTEGER,
    responsavel_menores TEXT,
    responsavel_maiores TEXT,
    -- DOI: transmissao de imovel
    doi_transacao INTEGER,
    doi_tipo_imovel INTEGER,
    doi_endereco TEXT,
    doi_area TEXT,
    doi_matricula TEXT,
    com_imovel INTEGER NOT NULL DEFAULT 0,
    protocolo_id INTEGER,
    lancamento_id INTEGER,
    sem_efeito_motivo TEXT,
    revogado_em TEXT,
    revogado_por TEXT,
    acervo INTEGER NOT NULL DEFAULT 0,    -- veio de delegatario anterior
    lavrado_nome TEXT,                    -- quem praticou, congelado
    lavrado_titulo TEXT,
    observacao TEXT,
    origem TEXT NOT NULL DEFAULT 'MANUAL',
    origem_chave TEXT,
    importacao_id INTEGER,
    criado_em TEXT NOT NULL,
    criado_por TEXT,
    FOREIGN KEY(livro_id) REFERENCES nt_livros(id)
);

CREATE INDEX IF NOT EXISTS ix_nt_atos_data ON nt_atos(data);
CREATE INDEX IF NOT EXISTS ix_nt_atos_tipo ON nt_atos(tipo, situacao);
CREATE INDEX IF NOT EXISTS ix_nt_atos_livro ON nt_atos(livro_id, folha);

CREATE TABLE IF NOT EXISTS nt_ato_partes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    ato_id INTEGER NOT NULL,
    cartao_id INTEGER,
    nome TEXT NOT NULL,
    nome_norm TEXT,
    documento TEXT,
    tipo_pessoa TEXT NOT NULL DEFAULT 'F',
    qualificacao TEXT,                    -- outorgante, herdeiro, testador...
    qualificacao_censec INTEGER,
    nacionalidade TEXT,
    estado_civil TEXT,
    profissao TEXT,
    endereco TEXT,
    testemunha INTEGER NOT NULL DEFAULT 0,
    ordem INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT NOT NULL,
    FOREIGN KEY(ato_id) REFERENCES nt_atos(id),
    FOREIGN KEY(cartao_id) REFERENCES nt_cartoes(id)
);

CREATE INDEX IF NOT EXISTS ix_nt_partes_ato ON nt_ato_partes(ato_id, ordem);
CREATE INDEX IF NOT EXISTS ix_nt_partes_nome ON nt_ato_partes(nome_norm);

-- Anotacao a margem do ato: revogacao, substabelecimento, retificacao.
CREATE TABLE IF NOT EXISTS nt_ato_anotacoes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    ato_id INTEGER NOT NULL,
    data TEXT NOT NULL,
    tipo TEXT,
    texto TEXT NOT NULL,
    selo TEXT,
    ato_relacionado_id INTEGER,
    lavrado_por TEXT,
    criado_em TEXT NOT NULL,
    FOREIGN KEY(ato_id) REFERENCES nt_atos(id),
    FOREIGN KEY(ato_relacionado_id) REFERENCES nt_atos(id)
);

CREATE INDEX IF NOT EXISTS ix_nt_anot_ato ON nt_ato_anotacoes(ato_id, data);

-- A COMUNICACAO A SERVENTIA DE ORIGEM — relato #129, 14/10/2026, vindo da
-- inspecao. Codigo de Normas TJMA, art. 831, § 1o: substabelecimento de
-- mandato lavrado em OUTRA serventia se comunica imediatamente ao tabeliao que
-- o lavrou, com comprovante de recebimento. Uma linha por ato; ela nasce
-- ABERTA e so vira CUMPRIDA por uma das duas providencias (comprovante juntado
-- ou envio do oficio anotado). Nao se apaga nem se reabre — ver
-- `notas_comunicacao_origem.py`.
CREATE TABLE IF NOT EXISTS nt_comunicacoes_origem (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    ato_id INTEGER NOT NULL UNIQUE,
    situacao TEXT NOT NULL DEFAULT 'ABERTA',   -- ABERTA | CUMPRIDA
    destinatario TEXT NOT NULL,                -- a serventia de origem
    destinatario_cns TEXT,
    procuracao_livro TEXT,
    procuracao_folha TEXT,
    procuracao_data TEXT,
    nascida_em TEXT NOT NULL,
    nascida_por TEXT,
    nascida_como TEXT NOT NULL,                -- LAVRATURA | TELA
    providencia TEXT,                          -- COMPROVANTE | OFICIO
    cumprida_em TEXT,
    cumprida_por TEXT,
    envio_data TEXT,
    envio_meio TEXT,
    envio_numero TEXT,                         -- numero do oficio ou rastreio
    envio_por TEXT,                            -- quem enviou
    comprovante_attachment_id INTEGER,         -- attachments.id
    comprovante_sha256 TEXT,
    comprovante_nome TEXT,
    comprovante_recebido_em TEXT,
    comprovante_em TEXT,
    comprovante_por TEXT,
    observacao TEXT,
    FOREIGN KEY(ato_id) REFERENCES nt_atos(id)
);

CREATE INDEX IF NOT EXISTS ix_nt_comunicacoes_origem_situacao
    ON nt_comunicacoes_origem(situacao, nascida_em);

-- Contador do numero de TERMO, uma linha por serie de livro.
--
-- POR QUE CONTADOR E NAO MAX()+1
--     O MAX()+1 que existia antes filtrava pelo ano de HOJE, nao pelo ano da
--     DATA DO ATO: lavrar hoje um ato datado do ano passado devolvia um numero
--     ja usado. E se o acervo viesse sem numero de ordem, o contador
--     reiniciava em 1 por cima de quarenta anos de livro.
--
--     O Registro de Imoveis ja resolveu isso com `ri_numeracao`, e esta tabela
--     e o mesmo desenho: contador explicito, quem fixou, quando e por que. O
--     `maior_em_uso` e o que impede alguem baixar o contador e criar termo
--     repetido.
CREATE TABLE IF NOT EXISTS nt_termos (
    serie TEXT PRIMARY KEY,               -- ESCRITURA, PROCURACAO, ...
    proximo INTEGER NOT NULL,
    maior_em_uso INTEGER,
    fixado_em TEXT,
    fixado_por TEXT,
    observacao TEXT
);

-- ------------------------------------------------ biblioteca de modelos

CREATE TABLE IF NOT EXISTS nt_modelos (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    codigo TEXT UNIQUE,
    tipo TEXT NOT NULL,                   -- ESCRITURA, PROCURACAO, ...
    nome TEXT NOT NULL,
    nome_norm TEXT,
    corpo TEXT NOT NULL,
    natureza_censec INTEGER,
    tipo_ato_censec INTEGER,
    doi_transacao INTEGER,
    com_imovel INTEGER NOT NULL DEFAULT 0,
    fins_previdenciarios INTEGER NOT NULL DEFAULT 0,
    fundamento TEXT,                      -- a base legal do ato
    ativo INTEGER NOT NULL DEFAULT 1,
    origem TEXT NOT NULL DEFAULT 'MANUAL',
    origem_chave TEXT,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT
);

CREATE INDEX IF NOT EXISTS ix_nt_modelos_tipo ON nt_modelos(tipo, ativo);

-- ------------------------------------------------ dominios das centrais

CREATE TABLE IF NOT EXISTS nt_censec_tipos (
    central TEXT NOT NULL,                -- CEP, CESDI, RCTO
    codigo INTEGER NOT NULL,
    descricao TEXT NOT NULL,
    PRIMARY KEY (central, codigo)
);

CREATE TABLE IF NOT EXISTS nt_censec_naturezas (
    codigo INTEGER NOT NULL,
    tipo_ato INTEGER NOT NULL,
    descricao TEXT NOT NULL,
    PRIMARY KEY (codigo, tipo_ato)
);

CREATE TABLE IF NOT EXISTS nt_censec_qualificacoes (
    codigo INTEGER PRIMARY KEY,
    central TEXT,
    descricao TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nt_doi_transacoes (
    codigo INTEGER PRIMARY KEY,           -- o codigo da Receita
    descricao TEXT NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS nt_doi_tipos_imovel (
    codigo INTEGER PRIMARY KEY,
    descricao TEXT NOT NULL
);

-- ------------------------------------------------ remessas as centrais

CREATE TABLE IF NOT EXISTS nt_remessas (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    central TEXT NOT NULL,                -- CEP, CESDI, RCTO, DOI, ENOTARIADO
    competencia TEXT,                     -- AAAA-MM da remessa
    periodo_inicio TEXT,
    periodo_fim TEXT,
    situacao TEXT NOT NULL DEFAULT 'PENDENTE',
    quantidade INTEGER NOT NULL DEFAULT 0,
    arquivo_nome TEXT,
    arquivo_sha256 TEXT,
    protocolo_central TEXT,               -- o numero que a central devolve
    mensagem TEXT,
    gerada_em TEXT,
    gerada_por TEXT,
    enviada_em TEXT,
    enviada_por TEXT,
    criado_em TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_nt_remessa ON nt_remessas(central, competencia);

-- Que ato entrou em que remessa. Sem isto nao se sabe o que ja foi informado,
-- e a serventia ou repete ou esquece — os dois dao problema em correicao.
CREATE TABLE IF NOT EXISTS nt_remessa_itens (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    remessa_id INTEGER NOT NULL,
    ato_id INTEGER NOT NULL,
    situacao TEXT NOT NULL DEFAULT 'PENDENTE',
    mensagem TEXT,
    criado_em TEXT NOT NULL,
    FOREIGN KEY(remessa_id) REFERENCES nt_remessas(id),
    FOREIGN KEY(ato_id) REFERENCES nt_atos(id)
);

CREATE INDEX IF NOT EXISTS ix_nt_rem_item ON nt_remessa_itens(remessa_id);
CREATE INDEX IF NOT EXISTS ix_nt_rem_ato ON nt_remessa_itens(ato_id);


-- ------------------------------------------------ sinal publico (CNSIP / Censec)
--
-- ABERTURA NAO SELA — regra do oficial em 07/09/2026.
--     O PDF do sinal vem BAIXADO da central (CNSIP/Censec) e se anexa; nao se
--     redesenha. O banco guarda o caminho em disco, como nt_cartao_imagens —
--     blob gigante nao entra no SQLite.
--
-- NAO SOBRECARREGA nt_cartoes.
--     Cartao de autografo e uma coisa; sinal publico cadastrado pela central e
--     outra. Tabelas proprias, rotas proprias.
--
-- O RECONHECIMENTO AUTONOMO mora em nt_sinais_reconhecimentos.
--     O checkbox «reconhecer tambem o sinal» no reconhecimento de FIRMA
--     continua em nt_reconhecimentos.sinal_publico — nao se mistura.

CREATE TABLE IF NOT EXISTS nt_sinais_publicos (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    titular TEXT NOT NULL,                -- nome de quem titulariza o sinal
    titular_norm TEXT,                    -- busca sem acento e sem caixa
    documento TEXT,                       -- CPF/CNPJ do titular, se houver
    data_abertura TEXT,                   -- data do cadastro / abertura
    origem TEXT NOT NULL DEFAULT 'MANUAL',-- CNSIP | CENSEC | MANUAL
    origem_chave TEXT,                    -- id externo na central, se houver
    caminho_pdf TEXT,                     -- relativo a archive_root (ou absoluto legado)
    nome_arquivo_pdf TEXT,
    sha256 TEXT,
    bytes INTEGER,
    metadados TEXT,                       -- JSON livre (protocolo, CNS, etc.)
    observacao TEXT,
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT NOT NULL,
    criado_por TEXT,
    atualizado_em TEXT,
    atualizado_por TEXT
);

CREATE INDEX IF NOT EXISTS ix_nt_sinais_titular ON nt_sinais_publicos(titular_norm);
CREATE INDEX IF NOT EXISTS ix_nt_sinais_doc ON nt_sinais_publicos(documento);
CREATE INDEX IF NOT EXISTS ix_nt_sinais_origem ON nt_sinais_publicos(origem, origem_chave);

-- Reconhecimento AUTONOMO do sinal publico (sem firma).
-- Item TJMA: 413 / 13.17.2 «Reconhecimento de sinal, letra e firma»
-- (mesmo do reconhecimento de firma). ABERTURA do sinal NAO sela.
CREATE TABLE IF NOT EXISTS nt_sinais_reconhecimentos (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sinal_id INTEGER NOT NULL,
    data TEXT NOT NULL,
    hora TEXT,
    selo TEXT,
    codigo_seguranca TEXT,
    servico_codigo INTEGER,               -- 413 quando selado; NULL se falhou
    documento_descricao TEXT,             -- o que foi apresentado
    texto TEXT,
    oficial TEXT,
    oficial_funcao TEXT,
    protocolo_id INTEGER,
    lancamento_id INTEGER,
    cancelado INTEGER NOT NULL DEFAULT 0,
    motivo_cancelamento TEXT,
    cancelado_em TEXT,
    cancelado_por TEXT,
    origem TEXT NOT NULL DEFAULT 'MANUAL',
    origem_chave TEXT,
    criado_em TEXT NOT NULL,
    criado_por TEXT,
    FOREIGN KEY(sinal_id) REFERENCES nt_sinais_publicos(id)
);

CREATE INDEX IF NOT EXISTS ix_nt_sinais_rec_sinal ON nt_sinais_reconhecimentos(sinal_id);
CREATE INDEX IF NOT EXISTS ix_nt_sinais_rec_data ON nt_sinais_reconhecimentos(data);
CREATE INDEX IF NOT EXISTS ix_nt_sinais_rec_selo ON nt_sinais_reconhecimentos(selo);

-- ------------------------------------------------ importacao e quarentena

CREATE TABLE IF NOT EXISTS nt_importacoes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    iniciada_em TEXT NOT NULL,
    terminada_em TEXT,
    origem TEXT,
    pasta TEXT,
    resumo TEXT,                          -- JSON com as contagens
    situacao TEXT NOT NULL DEFAULT 'EM_ANDAMENTO'
);

CREATE TABLE IF NOT EXISTS nt_rejeitados (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    importacao_id INTEGER,
    tabela TEXT,
    chave TEXT,
    motivo TEXT,
    conteudo TEXT,
    criado_em TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_nt_rejeitados ON nt_rejeitados(importacao_id, tabela);
"""

# Indices unicos PARCIAIS: tornam a importacao repetivel sem duplicar, e ao
# mesmo tempo deixam o lancamento feito a mao em paz — ele nao tem origem
# externa e por isso fica de fora da restricao. Foi o que funcionou no caixa.
INDICES_IMPORTACAO = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_nt_cartoes_origem
    ON nt_cartoes(origem, origem_chave)
    WHERE origem <> 'MANUAL' AND origem_chave IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_nt_rec_origem
    ON nt_reconhecimentos(origem, origem_chave)
    WHERE origem <> 'MANUAL' AND origem_chave IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_nt_aut_origem
    ON nt_autenticacoes(origem, origem_chave)
    WHERE origem <> 'MANUAL' AND origem_chave IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_nt_presenca_origem
    ON nt_presencas(origem, origem_chave)
    WHERE origem <> 'MANUAL' AND origem_chave IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_nt_atos_origem
    ON nt_atos(origem, origem_chave)
    WHERE origem <> 'MANUAL' AND origem_chave IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_nt_modelos_origem
    ON nt_modelos(origem, origem_chave)
    WHERE origem <> 'MANUAL' AND origem_chave IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_nt_img_arquivo
    ON nt_cartao_imagens(cartao_id, nome_arquivo)
    WHERE nome_arquivo IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_nt_sinais_origem
    ON nt_sinais_publicos(origem, origem_chave)
    WHERE origem <> 'MANUAL' AND origem_chave IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_nt_sinais_rec_origem
    ON nt_sinais_reconhecimentos(origem, origem_chave)
    WHERE origem <> 'MANUAL' AND origem_chave IS NOT NULL;
"""

# Colunas acrescentadas depois. Mesmo mecanismo do RI e do caixa.
MIGRACOES: tuple[tuple[str, str, str], ...] = (
    # A PARTICIPACAO DE CADA PARTE NA OPERACAO, QUE A DOI EXIGE.
    #
    #   A Receita valida que a soma fique entre 99,00% e 100,00% e recusa o
    #   arquivo inteiro fora dessa faixa — `notas_doi.conferir_participacoes`
    #   ja sabia disso, e nao tinha de onde ler o numero: a coluna nao existia
    #   em `nt_ato_partes`. O Registro de Imoveis ja a tem, em `ri_partes`, e
    #   e TEXT tambem ali — a mesma forma, para as duas nao divergirem.
    #
    #   O oficial decidiu em 28/08/2026: campo por parte, SUGERIDO em partes
    #   iguais e editavel, com a sugestao a vista. Dividir sozinho seria mandar
    #   um numero que ninguem viu, e dois vendedores podem nao ser meeiros.
    ("nt_ato_partes", "participacao", "TEXT"),
    # Papel fiscal deste vínculo; não altera o cartão de autógrafos.
    ("nt_ato_partes", "doi_lado", "TEXT"),
    # Torna em moeda corrente, em centavos. NULL significa não informado.
    ("nt_atos", "doi_torna_dinheiro", "INTEGER"),
    # Campos que a remessa as centrais exige e que o esquema nao tinha.
    # Conferidos contra o layout do CNB-CF em 15/08/2026 — vide notas_censec.py.
    #
    # O livro e a folha ganham complemento porque a CENSEC identifica o ato
    # pela chave (livro, livroComplemento, folha, folhaComplemento): sem o
    # complemento, dois atos na mesma folha sao recusados por duplicidade. No
    # acervo isso ja acontece em quatro pares do livro 27.
    ("nt_atos", "livro_complemento", "TEXT"),
    ("nt_atos", "folha_complemento", "TEXT"),
    # O SELO DE CADA FIRMA, e nao um selo por ato.
    #
    #   Medido em 27/08/2026: no E-Oficio cada firma era um ato e um selo —
    #   13.213 reconhecimentos, TODOS com uma firma so, e o envelope do selo
    #   levava UMA pessoa em `nomesReconhecido.parteAto` nos 13.776 medidos.
    #
    #   Este sistema deixa o escrevente marcar varios cartoes de uma vez, e
    #   ai o ato tem N firmas. Cada uma cobra o seu item e leva o SEU selo:
    #   um selo para tres firmas seria a serventia cobrando tres e selando
    #   uma. `nt_reconhecimentos.selo` continua guardando o do ato — e o que
    #   a tela e a etiqueta mostram —, e aqui fica o de cada firma.
    ("nt_reconhecimento_partes", "selo", "TEXT"),
    # A ETIQUETA DA AUTENTICACAO — relatada pelo oficial em 27/08/2026: «gera o
    # selo de autenticacao de copia, mas nao da opcao de imprimir a etiqueta».
    #
    #   A maquina da etiqueta ja existia inteira, e servia so o reconhecimento.
    #   Faltavam as duas colunas que contam a impressao — e contar importa: a
    #   segunda via de uma etiqueta e o mesmo selo colado em dois papeis, e e
    #   isso que a conferencia precisa enxergar.
    ("nt_autenticacoes", "etiqueta_impressa_em", "TEXT"),
    ("nt_autenticacoes", "etiqueta_impressoes", "INTEGER"),
    # Matricula Notarial Eletronica: obrigatoria quando o ato foi digital ou
    # hibrido pelo e-Notariado. Nos atos em papel vai nula, e e o correto.
    # O QUE O ESCREVENTE PREENCHEU NO MODELO — relato #78, 17/09/2026.
    # Sem isto, voltar a tela de preenchimento significaria redigitar
    # todos os campos: a rota lia os valores do formulario, montava o
    # teor e os jogava fora. JSON, porque os campos mudam com o modelo.
    ("nt_atos", "modelo_valores", "TEXT"),
    # A ANOTACAO ANTES DA LAVRATURA — 17/09/2026, pedido do oficial. A coluna
    # `observacao` JA EXISTIA e estava vazia em **263 de 263**: nenhuma tela a
    # escrevia. O que faltava era quem escreveu e quando — sem isso, a nota
    # aparece na tela sem dono, e daqui a um mes ninguem sabe se ela ainda
    # vale.
    ("nt_atos", "observacao_em", "TEXT"),
    ("nt_atos", "observacao_por", "TEXT"),
    ("nt_atos", "mne", "TEXT"),
    ("nt_atos", "tipo_cesdi", "INTEGER"),        # tipoAtoCesdi, 1 a 11
    ("nt_atos", "tipo_testamento", "INTEGER"),   # tipoTestamento do RCTO, 1 a 6
    ("nt_atos", "natureza_ata_usucapiao", "INTEGER"),
    ("nt_atos", "data_validade", "TEXT"),        # validade da procuracao
    # O ato antecessor ja tinha livro, folha, data, cartorio, cidade e UF. O
    # que faltava e o que a versao 2.3 do layout passou a exigir: o CNS.
    ("nt_atos", "anterior_cns", "TEXT"),
    ("nt_atos", "anterior_tipo_cep", "INTEGER"),
    ("nt_atos", "anterior_livro_complemento", "TEXT"),
    ("nt_atos", "anterior_folha_complemento", "TEXT"),
    # A CESDI pede o municipio de residencia pelo codigo do IBGE, nao pelo
    # nome. Fica na parte do ato, congelado como o resto: o ato ja informado
    # nao muda porque a pessoa mudou de cidade depois.
    ("nt_ato_partes", "municipio_ibge", "TEXT"),
    ("nt_ato_partes", "uf_residencia", "TEXT"),
    ("nt_ato_partes", "pais_residencia", "TEXT"),
    ("nt_ato_partes", "pais_nascimento", "TEXT"),
    ("nt_ato_partes", "uf_nascimento", "TEXT"),
    ("nt_ato_partes", "qualidade_cesdi", "TEXT"),
    ("nt_ato_partes", "conjuge_tipo", "INTEGER"),
    ("nt_ato_partes", "estrangeiro", "INTEGER NOT NULL DEFAULT 0"),
    ("nt_ato_partes", "oab_uf", "TEXT"),
    # O modelo diz a que central o ato pertence, e o codigo que ele carrega
    # muda de significado conforme ela: na CEP e natureza de escritura, na
    # CESDI e tipo de ato, no RCTO e tipo de testamento. Guardar os tres no
    # mesmo campo produziria numero certo no lugar errado.
    ("nt_modelos", "central_censec", "TEXT"),
    ("nt_modelos", "tipo_cesdi", "INTEGER"),
    ("nt_modelos", "tipo_testamento", "INTEGER"),
    # A remessa guarda a quinzena, nao so a competencia: o fechamento e
    # quinzenal por forca do Provimento CNJ 149/2023, art. 267.
    ("nt_remessas", "quinzena", "INTEGER"),
    ("nt_remessas", "ano_referencia", "INTEGER"),
    ("nt_remessas", "mes_referencia", "INTEGER"),
    # ---------------------------------------------------------------------
    # NUMERACAO AUTOMATICA DE LIVRO, FOLHA E TERMO — versao 3.3.8
    #
    # A regra desta serventia, definida pelo delegatario em 17/08/2026: cada
    # ato comeca em FOLHA NOVA, conta-se FRENTE E VERSO, o ato ocupa folhas
    # inteiras (logo, numero PAR de paginas), o TERMO e continuo por serie e
    # nao reinicia, e livro cheio encerra e o seguinte abre sozinho.
    #
    # Por que colunas numericas ao lado das de texto que ja existiam:
    # `folha` e `folha_final` sao TEXT e assim tem de continuar — o acervo tem
    # "139" e a CENSEC recebe texto. Mas ordenar, somar e garantir unicidade em
    # cima de texto e como somar em cima de "12v". Entao a folha passa a ter
    # duas caras: a de TEXTO, que sai no papel e na remessa, e a NUMERICA, que
    # e a que o sistema usa para contar. O acervo importado fica com as
    # numericas em NULO, e e de proposito: ele nao se renumera.
    ("nt_atos", "termo", "INTEGER"),
    ("nt_atos", "serie", "TEXT"),            # a serie de livro em que caiu
    ("nt_atos", "folha_inicial_num", "INTEGER"),
    ("nt_atos", "folha_final_num", "INTEGER"),
    ("nt_atos", "paginas", "INTEGER"),       # faces reservadas — sempre par
    ("nt_atos", "verso_final", "INTEGER NOT NULL DEFAULT 0"),
    ("nt_atos", "lancado_em", "TEXT"),
    ("nt_atos", "lancado_por", "TEXT"),
    ("nt_atos", "folhas_arquivamento", "INTEGER"),
    # A CONFIRMACAO DAS FOLHAS ARQUIVADAS — pedido do oficial, 15/10/2026: o
    # numero sai da contagem dos anexos e o escrevente confirma, podendo
    # corrigir. Guarda-se o sugerido, de onde ele veio, quem confirmou e
    # quando; o confirmado e `folhas_arquivamento`. Ver notas_arquivamento.py.
    ("nt_atos", "arquivamento_folhas_sugeridas", "INTEGER"),
    ("nt_atos", "arquivamento_origem_sugestao", "TEXT"),
    ("nt_atos", "arquivamento_confirmado_em", "TEXT"),
    ("nt_atos", "arquivamento_confirmado_por", "TEXT"),
    # A primeira folha do livro nem sempre e a 1: livro de continuacao comeca
    # onde o anterior parou em algumas serventias.
    ("nt_livros", "folha_inicial", "INTEGER NOT NULL DEFAULT 1"),
    ("nt_livros", "aberto_por", "TEXT"),
    ("nt_livros", "encerrado_por", "TEXT"),
    # Livro aberto pelo sistema quando o anterior encheu no meio do
    # atendimento. Fica marcado para a correicao saber que ninguem decidiu
    # aquilo a mao — o sistema decidiu, pela regra.
    ("nt_livros", "automatico", "INTEGER NOT NULL DEFAULT 0"),
    # "181-200": as folhas que sobraram em branco e que o termo de
    # encerramento declarou inutilizadas.
    ("nt_livros", "folhas_inutilizadas", "TEXT"),
    # ---------------------------------------------------------------------
    # ANOTACAO A MARGEM — versao 3.3.8
    #
    # O ato que revoga aponta para o que foi revogado. As colunas `anterior_*`
    # ja existiam, mas guardam TEXTO (livro, folha, cartorio) porque a CENSEC
    # pede assim e porque o ato anterior pode ser de outra serventia. Faltava
    # o vinculo interno, que e o que permite escrever a anotacao sozinho.
    ("nt_atos", "anterior_ato_id", "INTEGER"),
    # Quando o ato que gerou a anotacao foi lavrado em OUTRA serventia. A
    # revogacao lavrada em Imperatriz anota a procuracao lavrada aqui, e quem
    # digita a anotacao precisa dizer de onde ela veio.
    ("nt_ato_anotacoes", "origem_externa", "INTEGER NOT NULL DEFAULT 0"),
    ("nt_ato_anotacoes", "serventia_externa", "TEXT"),
    ("nt_ato_anotacoes", "cns_externa", "TEXT"),
    ("nt_ato_anotacoes", "criado_por", "TEXT"),
    # Quantas vezes a etiqueta ja saiu, e quando saiu a ultima.
    #
    # NAO E ESTATISTICA. Etiqueta termica enrosca, sai torta e sai em branco
    # quando o rolo acaba — reimprimir e rotina, e nao excecao. O que a tela
    # precisa dizer e se aquele ato JA TEVE etiqueta, para o balcao nao colar
    # duas no mesmo documento nem deixar um sem nenhuma.
    ("nt_reconhecimentos", "etiqueta_impressa_em", "TEXT"),
    ("nt_reconhecimentos", "etiqueta_impressoes", "INTEGER NOT NULL DEFAULT 0"),
    # A ETIQUETA DO RECONHECIMENTO DE SINAL PÚBLICO — LD02, 21/10/2026. O ato
    # selava e não tinha papel: o documento saía do balcão sem o selo nele
    # (CN-MA art. 131: o selo «deverá constar expressamente no corpo do ato
    # físico»). A etiqueta é a mesma do reconhecimento de firma, e conta a
    # impressão pela mesma razão.
    ("nt_sinais_reconhecimentos", "etiqueta_impressa_em", "TEXT"),
    ("nt_sinais_reconhecimentos", "etiqueta_impressoes", "INTEGER NOT NULL DEFAULT 0"),
    # O ENDEREÇO ELETRÔNICO DA AUTENTICAÇÃO DE DOCUMENTO DA INTERNET — LD02. A
    # autenticação «mencionará o endereço eletrônico de acesso, a data e o
    # horário da conferência» (CN-MA art. 839, § 1º); a data e a hora já
    # existiam, o endereço não tinha onde morar.
    ("nt_autenticacoes", "endereco_eletronico", "TEXT"),
    # A RESSALVA DO ORIGINAL DA AUTENTICACAO — LD07, 21/10/2026. A rasura ou o
    # defeito que o tabeliao ve no original «serao ressalvados na
    # autenticacao» (CN-MA art. 836): a frase vai no teor, e o que se viu fica
    # aqui tambem, para a busca e a correicao.
    ("nt_autenticacoes", "ressalva", "TEXT"),
    # O TITULO ELEITORAL DO DEPOSITANTE — LD07. A abertura de firma traz, «se
    # houver, o numero do titulo eleitoral» (CN-MA art. 864, § 1º, III); o
    # cartao nao tinha onde guarda-lo, e a ficha nao o imprimia.
    ("nt_cartoes", "titulo_eleitor", "TEXT"),
    # O QUE O CNN ART. 111 POS NA QUALIFICACAO DA PARTE — LD07. «o documento de
    # identificacao, ou, na sua falta, a filiacao; ... a existencia de uniao
    # estavel», e o conjuge e o regime de bens de quem e casado (CC art. 215,
    # § 1º, III; CN-MA art. 798, V). A parte do ato so tinha os seis do Codigo
    # Civil; `notas_teor.qualificar` le estes, e marca o que faltar.
    ("nt_ato_partes", "identidade", "TEXT"),
    ("nt_ato_partes", "filiacao", "TEXT"),
    ("nt_ato_partes", "uniao_estavel", "TEXT"),   # SIM | NAO — o que a parte declarou
    ("nt_ato_partes", "conjuge", "TEXT"),         # o conjuge, ou o companheiro
    ("nt_ato_partes", "regime_bens", "TEXT"),
    # QUEM CONFERIU O PREENCHIMENTO DA FICHA DE FIRMA — LH13, 21/10/2026. A ficha
    # traz o «nome, assinatura e carimbo do tabeliao ou do seu substituto ou
    # outro preposto designado que verificou a regularidade do preenchimento»
    # (CN-MA art. 864, § 1º, VI), e o oficial decidiu (pergunta 9, letra b) que
    # e o escrevente que abriu o cartao. Nome e funcao sao gravados NA ABERTURA,
    # e nao lidos de `users` na impressao: a segunda via da ficha tem de dizer
    # quem conferiu naquele dia, ainda que a pessoa mude de nome ou de funcao.
    # Cartao aberto antes disto fica sem: nao se deduz quem conferiu.
    ("nt_cartoes", "conferente_nome", "TEXT"),
    ("nt_cartoes", "conferente_funcao", "TEXT"),
)


# Indices da numeracao. Vao DEPOIS das migracoes porque falam de colunas que
# as migracoes acabaram de criar.
#
# SAO PARCIAIS, E ESSA E A PARTE QUE IMPORTA
#     A condicao `IS NOT NULL` deixa o ACERVO INTEIRO de fora. O acervo tem
#     quatro pares de atos na mesma folha do livro 27 — herdados do E-Oficio,
#     reais, e que nao se corrigem inventando folha. Um indice unico sem a
#     condicao recusaria criar-se, e a atualizacao morreria na largada.
#
#     Os atos novos, que nascem com folha atribuida pelo sistema, entram no
#     indice e nao conseguem repetir folha nem termo. Que e exatamente onde a
#     garantia serve.
INDICES_NUMERACAO = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_nt_atos_folha
    ON nt_atos(livro_id, folha_inicial_num)
    WHERE livro_id IS NOT NULL AND folha_inicial_num IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_nt_atos_termo
    ON nt_atos(serie, termo)
    WHERE serie IS NOT NULL AND termo IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_nt_atos_situacao_livro
    ON nt_atos(situacao, livro_id);

CREATE INDEX IF NOT EXISTS ix_nt_livros_serie
    ON nt_livros(tipo, encerrado, ativo);

CREATE INDEX IF NOT EXISTS ix_nt_atos_anterior
    ON nt_atos(anterior_ato_id);

-- Uma anotacao por par (ato anotado, ato que a gerou, tipo). Impede que
-- clicar duas vezes escreva duas vezes a mesma revogacao na margem — no papel
-- ninguem escreve a mesma coisa duas vezes, e no banco tambem nao deve.
CREATE UNIQUE INDEX IF NOT EXISTS ux_nt_anotacao_par
    ON nt_ato_anotacoes(ato_id, ato_relacionado_id, tipo)
    WHERE ato_relacionado_id IS NOT NULL;
"""


def _rodar_script(bd, script: str) -> None:
    for comando in re.split(r";[ \t]*\n", script):
        if re.sub(r"--[^\n]*", "", comando).strip():
            bd.escrever(comando)


def init_notas_schema(con) -> None:
    """Cria as tabelas do tabelionato. Idempotente, como o resto do sistema."""
    bd = banco(con)
    _rodar_script(bd, SCHEMA)
    _rodar_script(bd, INDICES_IMPORTACAO)
    for tabela, coluna, tipo in MIGRACOES:
        if not bd.tem_coluna(tabela, coluna):
            bd.escrever(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
    _rodar_script(bd, INDICES_NUMERACAO)


# ------------------------------------------------------------- utilidades

def texto_reconhecimento(especie: str, nomes: list[str],
                         sinal_publico: bool = False, *, con: Any = None) -> str:
    """O teor que sai na etiqueta.

    Segue a formula que a serventia ja usa, vinda do acervo do E-Oficio:
    'RECONHECO POR SEMELHANCA A FIRMA DE FULANO. DOU FE.' A diferenca entre as
    duas especies nao e de estilo: por semelhanca o tabeliao confronta com o
    cartao; por autenticidade a pessoa assinou na sua frente. Dizer uma pela
    outra e falsidade.

    A FORMULA SAIU DAQUI NO LF06D (19/10/2026): mora na base dos padroes,
    um papel por especie (`NOTAS_RECONHECIMENTO_SEMELHANCA`, `..._AUTENTICIDADE`)
    e uma peca para varias firmas e para o sinal publico. A REGRA — qual
    especie, uma firma ou varias, com sinal ou sem — continua aqui. Com `con`,
    vale o ajuste da casa.
    """
    quem = ", ".join(n.strip().upper() for n in nomes if n and n.strip())
    if not quem:
        quem = "___________________"
    papel = ("NOTAS_RECONHECIMENTO_AUTENTICIDADE" if especie == "AUTENTICIDADE"
             else "NOTAS_RECONHECIMENTO_SEMELHANCA")
    if sinal_publico:
        papel += "__sinal"
    elif len(nomes) > 1:
        papel += "__firmas"
    return MODELOS.textos(con).preencher(papel, quem=quem)


# O fecho da etiqueta. O `texto_reconhecimento` acima para no "DOU FE." — o que
# basta na tela e nao basta na etiqueta, onde o fecho e o lugar do sinal publico
# e da data do ato.
#
# SEM O TRACO — decisao do oficial em 27/08/2026: «tire o espaco do "em test da
# verdade", nao gosto de espaco».
#
#     Estava "EM TEST.________ DA VERDADE.", e o comentario aqui afirmava que
#     eram "13.209 etiquetas assim no acervo". **Fui conferir e nao e verdade**:
#     `strTextoSelo` do acervo nao tem uma etiqueta com "VERDADE" sequer. A
#     afirmacao nunca foi medida — e afirmacao nao medida que diz "e assim que a
#     casa faz" e a pior especie de comentario, porque quem a le nao a confere.
#
#     Como nao ha precedente medido para imitar, quem decide a forma e o
#     oficial, que e quem assina o papel.
#
# `FECHO_ETIQUETA` — o texto — saiu daqui no LF06D (19/10/2026): mora em
# `modelos_padrao/notas/NOTAS_ETIQUETA_FECHO.txt`, e o nome antigo continua
# respondendo (`__getattr__`). O «DA VERDADE» de `texto_da_etiqueta` e outra
# coisa: e como se RECONHECE a etiqueta importada, que ja veio com o fecho.


def texto_da_etiqueta(teor: str, cidade: str, uf: str, data_iso: str, *,
                      con: Any = None) -> str:
    """O que sai impresso, no formato do E-Oficio.

    NAO DUPLICA O FECHO. Os 13.209 reconhecimentos importados ja trazem o texto
    completo no campo `texto`; os lavrados no sistema novo trazem so o teor.
    Reimprimir a segunda via de um ato de 2020 tinha de sair igual a primeira,
    e nao com "DA VERDADE" duas vezes.
    """
    teor = (teor or "").strip()
    if "DA VERDADE" in teor.upper():
        return teor
    local = f"{(cidade or '').strip().upper()}-{(uf or '').strip().upper()}".strip("-")
    try:
        from datetime import date as _date
        dia = _date.fromisoformat((data_iso or "")[:10]).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        dia = ""
    textos = MODELOS.textos(con)
    local_e_data = (textos.preencher("NOTAS_ETIQUETA_FECHO__local_e_data",
                                     local=local, dia=dia) if local or dia else "")
    fim = " ".join(x for x in (textos("NOTAS_ETIQUETA_FECHO"), local_e_data) if x)
    return f"{teor} {fim}".strip()


def tipos_autenticacao(con: Any = None) -> dict:
    """`{tipo: (texto, item da tabela)}` — o texto lido da base. So le."""
    textos = MODELOS.textos(con)
    return {tipo: (textos(papel), item) for tipo, (papel, item) in AUTENTICACOES.items()}


def texto_autenticacao(tipo: str = "PADRAO", *, con: Any = None,
                       endereco: Any = None, data: Any = None,
                       hora: Any = None, ressalva: Any = None) -> str:
    """O teor da autenticacao, pelo papel do tipo (ajuste da casa -> padrao).

    A DE DOCUMENTO DA INTERNET DIZ ONDE E QUANDO SE CONFERIU (LD02,
    21/10/2026): «A autenticacao mencionara o endereco eletronico de acesso, a
    data e o horario da conferencia» (CN-MA art. 839, § 1º). Com o endereco, a
    peca `NOTAS_AUTENTICACAO_INTERNET__conferencia` entra logo depois da
    formula; sem ele (o montador chamado avulso), o texto e o de antes.

    A RASURA OU O DEFEITO DO ORIGINAL SE RESSALVA NA AUTENTICACAO (LD07,
    21/10/2026): o tabeliao confere o original e verifica «se contem rasuras
    ou quaisquer outros defeitos, os quais serao ressalvados na autenticacao»
    (CN-MA art. 836). Ate aqui o papel nao tinha onde dize-lo. Com a
    ressalva, a peca `NOTAS_AUTENTICACAO__ressalva` entra no fim; sem ela, o
    texto e o de antes — original sem defeito nao pede frase.
    """
    papel = AUTENTICACOES.get(tipo, AUTENTICACOES["PADRAO"])[0]
    textos = MODELOS.textos(con)
    texto = textos(papel)
    if tipo == "INTERNET" and str(endereco or "").strip():
        texto += textos.preencher(
            "NOTAS_AUTENTICACAO_INTERNET__conferencia",
            endereco=str(endereco).strip(), data=str(data or "").strip(),
            hora=str(hora or "").strip())
    ressalva = " ".join(str(ressalva or "").split()).rstrip(" .;")
    if ressalva:
        texto += textos.preencher("NOTAS_AUTENTICACAO__ressalva", ressalva=ressalva)
    return texto


def servico_do_reconhecimento(especie: str, veiculo: bool = False,
                              financeiro: bool = False) -> int:
    """Qual item da tabela do TJMA cobrar.

    A ordem importa: documento de veiculo e de conteudo financeiro tem item
    proprio, e so caindo fora dos dois e que vale o reconhecimento comum.
    """
    if veiculo:
        return SERVICOS["VEICULO"]
    if financeiro:
        return SERVICOS["FINANCEIRO"]
    return SERVICOS["SEMELHANCA"]


# A FIRMA NO DOCUMENTO DE TRANSFERÊNCIA DE VEÍCULO É POR AUTENTICIDADE — Código
# de Normas do MA (Prov. COGEX 28/2026), art. 865, II e III:
#
#   É obrigatório o reconhecimento por autenticidade nos documentos e papéis
#   que visem: (...) II - transferência de veículos automotores (CRV ou DUT),
#   bem como nas procurações particulares outorgadas, exclusivamente ou não,
#   para esse fim; III - se o vendedor do veículo for empresa, (...) por
#   representante legal e juntada cópia autenticada do contrato social.
#
# Até o LG04 (19/10/2026) a caixa «Documento de veículo» só trocava o item
# (13.17.3) e a semelhança passava. O item cobre também a QUITAÇÃO e o mandato
# que não transfere, e por isso quem atende diz qual é o documento: só o
# «OUTRO» dispensa a autenticidade. Sem escolha, vale a regra — o caso comum
# do balcão é o CRV e a ATPV.
DOCUMENTOS_DE_VEICULO = {
    "CRV": "CRV / DUT — transferência",
    "ATPV": "ATPV ou ATPV-e — autorização para transferência",
    "PROCURACAO": "Procuração particular para transferir o veículo",
    "OUTRO": "Outro (quitação ou mandato que não transfere)",
}
DOCUMENTOS_DE_VEICULO_QUE_TRANSFEREM = frozenset({"CRV", "ATPV", "PROCURACAO"})


def recusa_da_firma_do_veiculo(especie: str, veiculo: bool,
                               documento: str | None = None) -> str | None:
    """A semelhança num documento de transferência de veículo. Só calcula.

    Devolve a frase da recusa, ou `None` quando a espécie serve.
    """
    if not veiculo:
        return None
    qual = str(documento or "").strip().upper()
    if qual == "OUTRO":
        return None
    if str(especie or "").strip().upper() == "AUTENTICIDADE":
        return None
    return ("Documento de transferência de veículo (CRV, DUT, ATPV ou "
            "procuração para esse fim) só admite reconhecimento por "
            "AUTENTICIDADE, com o signatário presente (Código de Normas, "
            "art. 865, II). Se o documento é só de quitação, escolha «Outro».")

# ------------------------------------------------------------- sinal publico

ORIGENS_SINAL = {
    "CNSIP": "CNSIP — PDF baixado da central",
    "CENSEC": "Censec — PDF baixado da central",
    "MANUAL": "Manual / outros",
}


def normalizar_nome_sinal(nome: str) -> str:
    """Busca sem acento e sem caixa — mesmo criterio do cartao."""
    import unicodedata
    bruto = unicodedata.normalize("NFD", (nome or "").strip().lower())
    return "".join(c for c in bruto if unicodedata.category(c) != "Mn")


def texto_reconhecimento_sinal(titular: str, *, con: Any = None) -> str:
    """Teor do reconhecimento AUTONOMO do sinal (sem firma).

    Distinto do checkbox «reconhecer tambem o sinal» no reconhecimento de
    firma (`texto_reconhecimento(..., sinal_publico=True)`), que junta firma e
    sinal no mesmo ato. A formula mora na base desde o LF06D.
    """
    quem = (titular or "").strip().upper() or "___________________"
    return MODELOS.textos(con).preencher("NOTAS_RECONHECIMENTO_SINAL", quem=quem)


def __getattr__(nome: str):
    """Os nomes antigos do texto de fabrica, lidos da base dos padroes.

    O TEXTO SAIU DESTE MODULO NO LF06D (19/10/2026) e mora em `modelos_padrao/`.
    Quem ainda importa o nome antigo recebe o padrao da base — o MESMO que o
    papel imprime. Nome que nao e de papel continua sendo `AttributeError`.
    """
    if nome.startswith("__"):
        raise AttributeError(nome)
    if nome == "TIPOS_AUTENTICACAO":
        return tipos_autenticacao()
    return MODELOS.constante_antiga(__name__, nome)
