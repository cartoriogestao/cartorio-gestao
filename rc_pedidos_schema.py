"""Onde mora o que a Central de Certidões manda, e o que a casa respondeu.

Construído em 03/09/2026, item 2 do cronograma: *«siga no desenvolvimento das
integrações até terminar de todas»*.

**UMA TABELA PARA OS SETE MÓDULOS, e não sete.** A Central manda pedidos de
sete lugares — CRC, REG, JUD, EPR, P13, RSE e EOB —, e o que muda de um para
outro é **de onde veio**; a vida deles é a mesma: chega, alguém decide, a
resposta sobe. É a lição do núcleo, a de `as_documentos` e a de
`cn_pendencias`, que resolveu exatamente isto do lado do Protesto.

**MAS DOIS DELES NÃO PEDEM CERTIDÃO: PEDEM REGISTRO.** `P13` são solicitações
de **registro de nascimento** das Unidades Interligadas e `EOB` são
solicitações de **registro de óbito** do e-Óbito. Um se emite, o outro se
**lavra** — com número, folha, selo e corrente de hash. Por isso a situação
`REGISTRADO` existe ao lado de `ATENDIDO`, e por isso **este módulo não lavra
nada**: quem lavra é a tela do assento, que tem as quatro coisas. É a regra do
CNIB pela quinta vez — **avisar e preparar, ficando pendente o okay.**

**O AMBIENTE FAZ PARTE DA CHAVE.** É a lição da CENPROT, e vale igual aqui: a
homologação e a produção numeram pedidos no mesmo intervalo, e sem o ambiente
na chave o primeiro pedido de teste ocuparia o lugar do primeiro de verdade —
e o de verdade **não entraria, sem erro em lugar nenhum**.

**O TEOR CONGELA.** É o que a Central mandou naquele dia; ela pode mudar o dado
dela amanhã, e o que a casa respondeu foi sobre isto aqui. Sem o teor congelado
não há como explicar, seis meses depois, por que a casa rejeitou.

**E O PDF NÃO MORA NO BANCO.** O arquivo da certidão eletrônica é da Central e
se busca nela quando se precisa (`GET /get-certificate-json/{id}`, que devolve
também a situação corrente). Guardá-lo aqui poria binário num banco que **viaja
no backup**, e o backup já saiu da serventia — e ainda daria duas versões do
mesmo papel para divergirem. O que fica congelado é **o que a casa mandou**,
com hash, que é o que ela responde por.
"""
from __future__ import annotations

import sqlite3

# AS SITUAÇÕES DO PEDIDO.
#
#   `DISPENSADO` existe porque **aviso sem saída é aviso que fica para
#   sempre**: sem um jeito de tirar da lista o que não é desta casa, o balcão
#   vê a mesma linha todo dia e para de ler.
PENDENTE = "PENDENTE"
ATENDIDO = "ATENDIDO"
REGISTRADO = "REGISTRADO"
REJEITADO = "REJEITADO"
DISPENSADO = "DISPENSADO"

SITUACOES: tuple[str, ...] = (
    PENDENTE, ATENDIDO, REGISTRADO, REJEITADO, DISPENSADO)

# O QUE JÁ NÃO ESPERA NINGUÉM — é o que a lista do balcão tira da frente.
SITUACOES_TERMINAIS: frozenset[str] = frozenset(
    {ATENDIDO, REGISTRADO, REJEITADO, DISPENSADO})

# AS SITUAÇÕES DA CERTIDÃO ELETRÔNICA, do lado de lá.
CRIADA = "CRIADA"
ASSINADA = "ASSINADA"
CANCELADA = "CANCELADA"

SITUACOES_DA_CERTIDAO: tuple[str, ...] = (CRIADA, ASSINADA, CANCELADA)

SCHEMA = """
CREATE TABLE IF NOT EXISTS rc_pedidos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- DE ONDE VEIO, E DE QUE AMBIENTE. O ambiente entra na chave única.
    modulo TEXT NOT NULL,                   -- CRC REG JUD EPR P13 RSE EOB
    ambiente TEXT NOT NULL,                 -- HOMOLOGACAO | PRODUCAO

    -- COMO A CENTRAL CHAMA ISTO. Ela devolve `pedido_certidao_id` e exige
    -- `numero_pedido` de volta — **o mesmo número, dois nomes**, e ainda com
    -- tipos diferentes conforme o caminho. Guarda-se como TEXTO, que é a
    -- forma que não perde zero à esquerda nem estoura tamanho.
    numero_pedido TEXT NOT NULL,

    -- A LETRA CRUA DO `tipo_registro` do pedido, e a espécie que se derivou
    -- dela. **A espécie fica NULA quando a letra não é conhecida** — só o «N»
    -- está medido no contrato.
    letra_registro TEXT,
    especie TEXT,

    -- O ASSENTO DESTA CASA, quando se achou. **Vazio quer dizer que não se
    -- achou**, e isso é informação: pedido sem assento é o que o balcão
    -- precisa olhar primeiro.
    assento_id INTEGER REFERENCES rc_assentos(id),
    casamento_motivo TEXT,                  -- como se achou, ou por que não

    -- O QUE A CENTRAL MANDOU, congelado, como veio. JSON.
    teor TEXT NOT NULL,
    -- A LINHA QUE O BALCÃO LÊ, montada na baixa.
    resumo TEXT NOT NULL DEFAULT '',
    -- O DEPÓSITO PRÉVIO **como a Central o escreveu** (com vírgula) e já
    -- convertido. Guardar só o texto obrigaria a converter em toda leitura;
    -- guardar só o número perderia o que ela disse.
    deposito_previo TEXT,
    deposito_previo_valor REAL,

    baixado_em TEXT NOT NULL,
    baixado_por TEXT,

    situacao TEXT NOT NULL DEFAULT 'PENDENTE',

    -- O QUE SUBIU, e o que a Central respondeu.
    respondido_em TEXT,
    respondido_por TEXT,
    resposta TEXT,
    -- O CORPO QUE A CASA MANDOU, congelado com hash.
    corpo_enviado TEXT,
    corpo_hash TEXT,

    -- POR QUE SE REJEITOU — o requerente lê esta frase.
    rejeicao_motivo TEXT,
    -- POR QUE SAIU DA LISTA SEM RESPOSTA. Dispensar exige motivo escrito,
    -- como no usucapião e na pendência de numeração.
    dispensa_motivo TEXT
);

CREATE INDEX IF NOT EXISTS idx_rc_pedidos_fila
    ON rc_pedidos(situacao, modulo);
CREATE INDEX IF NOT EXISTS idx_rc_pedidos_assento
    ON rc_pedidos(assento_id);

-- O MESMO PEDIDO NÃO ENTRA DUAS VEZES. Baixar de novo é rotina, e sem esta
-- trava a segunda baixa duplicaria a fila — uma cópia já respondida e outra
-- em branco, com o balcão respondendo a mesma coisa duas vezes.
CREATE UNIQUE INDEX IF NOT EXISTS ux_rc_pedidos_central
    ON rc_pedidos(ambiente, modulo, numero_pedido);


CREATE TABLE IF NOT EXISTS rc_certidoes_eletronicas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- DE QUE ASSENTO ELA É. **NOT NULL**: certidão eletrônica sem assento
    -- seria papel afirmando um registro que a casa não tem.
    assento_id INTEGER NOT NULL REFERENCES rc_assentos(id),
    -- DE QUE PEDIDO ELA NASCEU, quando nasceu de um. Vazio é a emissão avulsa
    -- do balcão, que é caso legítimo e não falta de dado.
    pedido_id INTEGER REFERENCES rc_pedidos(id),

    ambiente TEXT NOT NULL,
    tipo_registro TEXT NOT NULL,            -- nascimento casamento obito inteiro_teor
    tipo_certidao TEXT,                     -- só quando inteiro_teor
    modalidade TEXT NOT NULL DEFAULT 'eletronica',

    -- O IDENTIFICADOR DA CENTRAL. É ele que serve de `id_verificador` ao
    -- cumprir o pedido.
    certidao_id TEXT,

    -- O QUE A CASA MANDOU, congelado, com hash.
    corpo_enviado TEXT NOT NULL,
    corpo_hash TEXT NOT NULL,
    resposta TEXT,

    situacao TEXT NOT NULL DEFAULT 'CRIADA',

    -- A ASSINATURA ACONTECE NA CENTRAL — ver `onrcpn_certidao_api.assinar`.
    -- Aqui só se guarda o que ela devolveu.
    assinatura_link TEXT,
    assinatura_id TEXT,
    assinada_em TEXT,

    cancelada_em TEXT,
    cancelada_por TEXT,

    criada_em TEXT NOT NULL,
    criada_por TEXT
);

CREATE INDEX IF NOT EXISTS idx_rc_cert_elet_assento
    ON rc_certidoes_eletronicas(assento_id, criada_em);
CREATE INDEX IF NOT EXISTS idx_rc_cert_elet_pedido
    ON rc_certidoes_eletronicas(pedido_id);

-- O MESMO IDENTIFICADOR DA CENTRAL NÃO SE GUARDA DUAS VEZES. O ambiente entra
-- pela mesma razão da fila.
CREATE UNIQUE INDEX IF NOT EXISTS ux_rc_cert_elet_central
    ON rc_certidoes_eletronicas(ambiente, certidao_id)
    WHERE certidao_id IS NOT NULL;
"""

# Colunas acrescentadas depois. Aditivo, no padrão do sistema — e índice sobre
# coluna de migração **não vai aqui**: vai em `INDICES_DEPOIS_DA_MIGRACAO`.
MIGRACOES: tuple[tuple[str, str, str], ...] = ()

INDICES_DEPOIS_DA_MIGRACAO: tuple[str, ...] = ()


def init_rc_pedidos_schema(con: sqlite3.Connection) -> None:
    """Cria a fila de pedidos e as certidões eletrônicas. Idempotente."""
    con.executescript(SCHEMA)
    for tabela, coluna, tipo in MIGRACOES:
        existentes = {linha[1] for linha in con.execute(
            f"PRAGMA table_info({tabela})")}
        if coluna not in existentes:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
    for comando in INDICES_DEPOIS_DA_MIGRACAO:
        con.execute(comando)
