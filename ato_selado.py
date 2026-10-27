"""
A amarracao do ato: custas calculadas e selo conferido, gravados no ato.

O QUE FALTAVA, E POR QUE ISTO E UM MODULO E NAO UM PEDACO DE CADA TELA
    As pecas ja existiam todas: `custas.py` sabe quanto custa, `selo.py` sabe
    ler o codigo de 28 caracteres, `selador_cliente.py` sabe pedir selo ao
    aparelho, `sd_selos` e o razao. O que nao existia era o LUGAR onde elas se
    encontram na ordem certa — e sem ele cada atribuicao inventaria a sua, com
    quatro versoes divergentes da parte que mexe em dinheiro e em selo.

A ORDEM, E ELA NAO E A OBVIA
    1. CUSTAS PRIMEIRO, selo depois. Custas e conta local e barata, e falha
       por regra — servico que nao esta na tabela, data sem vigencia,
       gratuidade sem motivo. Pedir selo antes de saber que a conta fecha
       compraria selo para ato que nao vai existir, e selo comprado nao se
       devolve: vira orfao, como os 1.304 do acervo.

    2. O SELO NAO SE PEDE DENTRO DA TRANSACAO DO ATO. `db.transaction()` e
       `BEGIN IMMEDIATE` — um escritor por vez —, e a chamada ao selador tem
       prazo de 20 segundos. Segurar a trava de escrita da casa inteira
       durante uma chamada de rede poria todo outro balcao no `busy_timeout`,
       que e o defeito que este projeto ja pagou uma vez com a tela de leitura
       que consumia contador.

       Por isso `obter_selo()` recebe `db` e nao `con`: ela abre a sua propria
       transacao curta, so para gravar em `sd_selos`.

    3. VINCULAR DEPOIS que o ato existe. O selo entra no razao assim que chega
       — antes de o ato terminar — e so depois ganha `tabela` e `ato_id`. Se o
       ato falhar no meio, o selo aparece na tela de "selo obtido e nao usado"
       em vez de sumir.

O E-OFICIO SELAVA AUTOMATICO EM TUDO — E EU TINHA ESCRITO O CONTRARIO
    A primeira versao deste cabecalho dizia que "nesta casa o selo de Protesto
    e de RCPN e manual", porque `atribuicoes.CAMINHOS_OBSERVADOS_DO_SELADOR`
    so tem caminhos de RTD/RCPJ. O oficial, que operou o sistema, corrigiu: o
    E-Oficio selava automatico no RCPN e no RI tambem.

    Medido depois da correcao, em `tbSeloIndividual`: as 26.130 linhas tem
    `memJson` — o payload enviado ao selador — preenchido em TODAS as
    atribuicoes, e `strURLAto` guarda o caminho de cada selo. Sao **26.123
    selos em 34 caminhos**, cobrindo Notas, RI, RCPN, Protesto e RTD/RCPJ. E
    os 34 estao todos no contrato de `selador.py`.

    Ver `atribuicoes.CAMINHOS_USADOS_POR_ESTA_CASA`, que e a medida de
    verdade, e `caminhos_da_atribuicao()` para os de uma atribuicao so.

    A licao, que vale para o resto do projeto: coluna vazia nao prova que a
    coisa nao acontecia — prova que aquela coluna nao era onde ela ficava.

E O SELO A MAO CONTINUA EXISTINDO, PARA O QUE FALHA
    `registrar_selo_obtido_a_mao()` nao e o caminho normal, mas e necessario:
    o selador e uma maquina da rede local, e quando ela nao responde o balcao
    nao pode parar. O escrevente tira o selo no portal e digita aqui.

    O que o sistema acrescenta ao que o E-Oficio fazia: o codigo e LIDO, o CNS
    e conferido contra o da serventia, e o selo repetido e recusado dizendo em
    que ato ja esta. O E-Oficio aceitava qualquer coisa digitada.

FUNDAMENTO
    Resolucao-GP TJMA n. 143/2025 — tabela de emolumentos.
    Codigo de Normas do Foro Extrajudicial do Maranhao, Provimento TJMA 28/2026.
"""
from __future__ import annotations

import nome_humano as NOMEHUM

import logging
import sqlite3
from typing import Any

import atribuicoes as ATR
import custas as CU
from bd_nativo import banco
import identidade_do_robo as IDR

# `selador` E O CONTRATO, e entra aqui para CONFERIR o caminho composto do
# civil em vez de confiar nele. No topo porque `caminho_do_civil` e
# chamada de tela, e nao so de quem sela.
import selador
import selo as SELO

_LOG = logging.getLogger(__name__)

# As tabelas de ato que este modulo sabe selar. E lista fechada de proposito:
# escrever selo numa tabela que nao e de ato seria gravar em qualquer lugar.
TABELAS_DE_ATO: dict[str, str] = {
    "pt_atos": "Protesto",
    # A CERTIDAO NAO MORA EM `pt_atos`, e por isso entra aqui por fora:
    # `pt_atos.titulo_id` e NOT NULL, e a certidao NEGATIVA — 46 das 65 do
    # acervo — nao tem titulo nenhum. Ela e ato da SERVENTIA sobre uma pessoa,
    # e tem selo e custas como qualquer outro (`/selo/protesto/certidao`,
    # usado 57 vezes na casa).
    "pt_certidoes": "Protesto — certidões",
    # A certidao de inteiro teor do RCPJ/RTD e do Livro 3, pela mesma razao:
    # ela nao e ato de um registro, e por isso tem tabela propria.
    "at_certidoes": "Certidões das demais atribuições",
    # E a certidao do RCPN, pela terceira vez a mesma razao: ela nao mora em
    # `rc_atos` porque nao ocupa folha, nao entra na divisao tripartite, e sai
    # muitas vezes do mesmo assento sem que o assento mude.
    #
    # Ela FALTAVA aqui, e faltar era pior do que parece: o selo era recusado
    # com "nao e tabela de ato", e a rota — fazendo o que a casa manda, selo
    # recusado derruba o lancamento inteiro — desfazia a transacao. Quem
    # digitasse o selo emitia a certidao, via um aviso vermelho, e a CERTIDAO
    # SUMIA. Quem nao digitasse nunca veria nada.
    "rc_certidoes": "Registro Civil — certidões",
    "rc_atos": "Registro Civil das Pessoas Naturais",
    "rg_atos": "RCPJ / RTD",
    "ra_atos": "Registro Auxiliar",
    "ri_atos": "Registro de Imóveis",
    "nt_atos": "Notas",
    # A CERTIDÃO DAS NOTAS (15/10/2026), pela razão das outras certidões: não
    # é ato de livro, e a negativa nem ato tem. Faltando aqui, o selo seria
    # recusado DEPOIS de comprado e a certidão sumiria.
    "nt_certidoes": "Notas — certidões",
    # O BALCAO DAS NOTAS TEM TRES TABELAS PROPRIAS, e nenhuma delas e `nt_atos`
    # (que e o ato de LIVRO — escritura, procuracao, testamento).
    #
    #   Elas faltavam aqui, e faltar tem consequencia conhecida: o selo seria
    #   recusado com "nao e tabela de ato". E o reconhecimento de firma e
    #   METADE do movimento desta casa — 13.776 dos 26.130 selos medidos.
    "nt_reconhecimentos": "Notas — reconhecimento de firma",
    "nt_autenticacoes": "Notas — autenticação de cópia",
    "nt_cartoes": "Notas — cartão de autógrafo",
    # **O RECONHECIMENTO AUTONOMO DO SINAL PUBLICO FALTAVA AQUI — achado pelo
    # SANDBOX em 15/09/2026, no primeiro caso de uso que o exercitou.**
    #
    #   Ele e ato: tem `selo`, `lancamento_id` e `cancelado`, e a tela
    #   `notas_web.selar_reconhecimento_sinal` o sela pelo item 413
    #   («Reconhecimento de sinal, letra e firma», o mesmo do reconhecimento de
    #   firma — o que nao sela e a ABERTURA do sinal, que e cadastro).
    #
    #   Faltando aqui, `vincular_ao_ato` recusava DEPOIS de o selo ter sido
    #   comprado: o ato ficava sem selo, o selo ia para «obtido e nao usado», e
    #   a tela dizia «O selo saiu, mas nao consegui amarra-lo ao ato». E o
    #   prejuizo nao e o do `rc_certidoes` pela metade: ali a rota desfazia o
    #   lancamento, e o escrevente refazia; aqui o SELO JA FOI PAGO, e o que
    #   sobra e selo orfao — a forma como o E-Oficio acumulou 1.304.
    #
    #   **Nenhum varredor via, e o motivo esta escrito no proprio
    #   `tests/test_ato_selado._tabelas_que_as_telas_selam`**: ele procura as
    #   funcoes `_selar_se_pedido`, `registrar_selo_obtido_a_mao` e `cobrar`, e
    #   esta tela sela por `selar_o_ato_lavrado`. A regua tinha um buraco
    #   declarado, e o caso que passou por ele so existe porque o sandbox
    #   exercita o ato inteiro — com selo — em vez de so gravar a linha.
    "nt_sinais_reconhecimentos": "Notas — reconhecimento de sinal público",
    # A PRENOTACAO E ATO DE LIVRO — Livro 1-A —, cobra e sela. Ela nao mora em
    # `ri_atos` porque e anterior ao registro e existe mesmo quando o titulo e
    # devolvido sem registro nenhum.
    "ri_protocolos": "Registro de Imóveis — prenotação",
    # A HABILITACAO DE CASAMENTO SELA — decisao do oficial em 28/08/2026: dois
    # selos, um aqui e outro no assento. Ela nao mora em `rc_atos` porque e
    # PROCESSO, e nao ato de livro: existe por semanas, e existe mesmo quando o
    # casamento nao chega a se realizar.
    "hc_habilitacoes": "Registro Civil — habilitação de casamento",
    # **A CERTIDAO DO RI NAO ESTAVA AQUI, e e o mesmo defeito que
    # `rc_certidoes` teve**: o escrevente digitava o selo, via o aviso
    # vermelho, e a certidao **deixava de existir** — porque a rota faz
    # o que a casa manda (selo recusado derruba o lancamento) sobre uma
    # premissa errada. Relato #43 do oficial, 07/09/2026.
    "ri_certidoes": "Registro de Imóveis — certidão",
    # A ABERTURA E ATO QUE CUSTA E SELA, e por isso entra aqui: e esta lista
    # que `selar_o_ato_lavrado` consulta antes de comprar selo.
    #
    #   E FICA DECLARADO O QUE ELA ENCOSTA. `acervo_carga` percorre esta
    #   lista para amarrar o selo do acervo ao ato, e procura `a.selo`
    #   ESCRITO A MAO — nao pelo `COLUNA_DO_SELO` que existe neste arquivo.
    #   Medido em 16/09/2026: **quatro** das dezesseis tabelas nao tem coluna
    #   `selo` (`nt_cartoes`, `ri_atos`, `ri_certidoes`, `ri_protocolos`), e
    #   para elas aquele `UPDATE` estoura dentro de um `try` e a amarracao
    #   **falha calada** — sao **9.141 selos com `tabela` nula** no razao.
    #   Esta entrada vira a quinta. O conserto e de uma linha e e naquele
    #   modulo, que nao e o desta passada: declarado ao oficial.
    "ri_matriculas": "Registro de Imóveis — abertura de matrícula",
    # OS ATOS DO LG04 (19/10/2026), cada um com `selo` e `lancamento_id`, pela
    # razão das certidões acima: nenhum mora em `rg_atos` nem em `nt_atos`. A
    # diligência da notificação é selo por destinatário e por ida (15.8.1); a
    # certidão dela, outro (15.8.2); a autenticação do livro contábil, a
    # pública forma e a comunicação de venda de veículo (13.22) são atos de
    # balcão sem livro de ato.
    "rg_notificacao_diligencias": "RTD — diligência de notificação",
    "rg_notificacao_certidoes": "RTD — certidão de notificação",
    "rg_livros_contabeis": "RCPJ — autenticação de livro",
    "nt_publicas_formas": "Notas — pública forma",
    "nt_comunicacoes_veiculo": "Notas — comunicação de venda de veículo",
}


# De que caminho do selador e cada ato dos nossos modulos de dominio.
#
# NAO E ADIVINHACAO: os nomes dos endpoints que a casa usou dizem o ato —
# `/selo/protesto/pagamento` e o pagamento, `/selo/protesto/baixa-cancelamento`
# e o cancelamento. Sao os mesmos 34 caminhos de
# `atribuicoes.CAMINHOS_USADOS_POR_ESTA_CASA`, medidos em 26.123 selos.
#
# Onde a casa nunca usou caminho proprio, fica `atos-em-geral` — que e o que
# ela de fato usou para o resto. A intimacao do Protesto e assim: nao ha
# endpoint de intimacao no uso, e o item 17.2 (intimacao) sai junto com o
# pagamento, a baixa e a retirada. E o "um selo por etapa" outra vez.
CAMINHO_DO_ATO: dict[tuple[str, str], str] = {
    ("pt_atos", "APONTAMENTO"): "/selo/protesto/titulo",
    ("pt_atos", "INTIMACAO"): "/selo/protesto/atos-em-geral",
    ("pt_atos", "PROTESTO"): "/selo/protesto/titulo",
    ("pt_atos", "PAGAMENTO"): "/selo/protesto/pagamento",
    ("pt_atos", "CANCELAMENTO"): "/selo/protesto/baixa-cancelamento",
    ("pt_atos", "DESISTENCIA"): "/selo/protesto/retirada",
    ("pt_atos", "CERTIDAO"): "/selo/protesto/certidao",
    # A certidao pelo tipo dela: os tres saem pelo mesmo caminho do selador.
    ("pt_certidoes", "NEGATIVA"): "/selo/protesto/certidao",
    ("pt_certidoes", "POSITIVA"): "/selo/protesto/certidao",
    ("pt_certidoes", "CANCELAMENTO"): "/selo/protesto/certidao",
    # A casa selou certidao de RTD/RCPJ por `atos-em-geral`, que e o caminho
    # que ela usou para o resto do RTD/RCPJ. O Livro 3 e do Registro de
    # Imoveis, e sela pela familia `imovel`.
    ("at_certidoes", "CERTIDAO"): "/selo/rtdpj/atos-em-geral",
    # O RCPN NAO ESTA AQUI, e isso e correcao de 27/08/2026.
    #
    # ATE AQUI ESTAVA ESCRITO que os tres atos do civil selavam por
    # `/selo/civil/atos-em-geral`, e que o `codigoAto` fora mandado vazio nos
    # 1.238 — logo nao haveria receita medida. A MEDICAO DESMENTIU AS DUAS
    # COISAS (ver DOCUMENTACAO/SELO_DO_CIVIL_MEDIDO.md):
    #
    #   - o `codigoAto` esta preenchido em 1.228 dos 1.238. Quem mediu antes
    #     olhou a COLUNA `intCodigoAto`, que e NULL em todas as linhas, e nao o
    #     campo `codigoAto` de dentro do `memJson`. E a mesma licao que o
    #     oficial ensinou em 24/08: **coluna vazia nao prova que a coisa nao
    #     acontece; prova que aquela coluna nao e onde ela fica**;
    #
    #   - `atos-em-geral` foi o caminho ANTIGO, de 03/06/2020 a 23/09/2024, e
    #     98% do que saiu por ele foram CERTIDOES (918 em 14.5.1, 237 em
    #     14.5.6, 60 em 14.5.7). Desde 2023 a casa usa os caminhos por especie,
    #     e desde setembro de 2024 usa SO eles.
    #
    # O caminho do civil nao e uma tabela: e composto da ESPECIE e do TIPO do
    # ato, e conferido contra o contrato. Ver `caminho_do_civil`.
    # REGISTRO e CANCELAMENTO: a casa selou por `atos-em-geral` (53 usos).
    # AVERBACAO: caminho proprio por serie — PJ vs titulo/documento. Ver
    # `caminho_do_rtdpj`; as chaves abaixo ficam de fallback generico.
    ("rg_atos", "REGISTRO"): "/selo/rtdpj/atos-em-geral",
    ("rg_atos", "AVERBACAO"): "/selo/rtdpj/atos-em-geral",
    ("rg_atos", "CANCELAMENTO"): "/selo/rtdpj/atos-em-geral",
    # O Livro 3 e do Registro de Imoveis: o selo sai pela familia `imovel`.
    ("ra_atos", "R"): "/selo/imovel/atos-em-geral",
    ("ra_atos", "AV"): "/selo/imovel/atos-em-geral",
}


# ------------------------------------------------- o caminho do civil
#
# O RCPN NAO CABE NUMA TABELA DE PARES, e o contrato do selador diz por que:
# para cada especie ha uma familia inteira de caminhos, com a mesma forma.
#
#     /selo/civil/nascimento              o registro (e a primeira certidao)
#     /selo/civil/nascimento/averbacao
#     /selo/civil/nascimento/anotacao
#     /selo/civil/nascimento/retificacao
#     /selo/civil/nascimento/segunda-via  a certidao depois da primeira
#
# E as tres do meio sao exatamente a DIVISAO TRIPARTITE que a inspecao cobra e
# que `rc_assento` ja modela. O caminho, entao, nao se escreve: compoe-se da
# especie mais o tipo do ato — e se CONFERE contra o contrato.
#
# CONFERIR CONTRA O CONTRATO E O QUE IMPEDE O CHUTE. Compor sozinho produziria
# `/selo/civil/proclamas/averbacao`, que nao existe; o contrato responde que
# nao existe, e a casa nao sela por caminho inventado.
SEGMENTO_DA_ESPECIE: dict[str, str] = {
    "NASCIMENTO": "nascimento",
    "CASAMENTO": "casamento",
    "OBITO": "obito",
    "NATIMORTO": "natimorto",

    # O CASAMENTO RELIGIOSO SELA PELO CAMINHO DO CASAMENTO — decisao do oficial
    # em 27/08/2026. O contrato nao tem `casamento-religioso`, e o religioso com
    # efeito civil E registro de casamento: o que muda e o livro (B-Auxiliar), e
    # nao o ato.
    "CASAMENTO_RELIGIOSO": "casamento",

    # PROCLAMAS E A HABILITACAO. O contrato tem `/selo/civil/casamento/
    # habilitacao` e a certidao dela; proclamas e o edital da habilitacao, e e
    # no Livro D que ele mora. Decisao do oficial em 27/08/2026.
    "PROCLAMAS": "casamento/habilitacao",

    # AS SEIS DO LIVRO E, cada uma com a sua familia inteira no contrato.
    "AUSENCIA": "ausencia",
    "INTERDICAO": "interdicao",
    "TUTELA": "tutela",
    "EMANCIPACAO": "emancipacao",
    "UNIAO_ESTAVEL": "uniao-estavel",
    "OPCAO_NACIONALIDADE": "opcao-nacionalidade",

    # `OUTRO` NAO ESTA AQUI, e e o unico que fica de fora. Ele existe para o
    # que nao e nenhuma das seis — e para o que nao tem nome nao ha caminho de
    # selo. Sair sem selo, dizendo por que, e melhor que selar por um caminho
    # parecido.
}

SUFIXO_DO_ATO_DO_CIVIL: dict[str, str] = {
    "REGISTRO": "",
    "AVERBACAO": "/averbacao",
    "ANOTACAO": "/anotacao",
    "RETIFICACAO": "/retificacao",
    # A CERTIDAO DEPOIS DA PRIMEIRA. O nome do caminho e do selador, e nao
    # nosso: la ele se chama «segunda via» e serve da segunda em diante.
    "CERTIDAO": "/segunda-via",
}


def caminho_do_civil(especie: Any, tipo: Any) -> str | None:
    """O caminho do selo de um ato do RCPN. So calcula.

    Devolve None quando a especie nao tem segmento conhecido ou quando o
    caminho composto nao existe no contrato — e None aqui quer dizer «sai sem
    selo, e a tela diz por que», nunca «sela por outro caminho parecido».
    """
    segmento = SEGMENTO_DA_ESPECIE.get(str(especie or "").strip().upper())
    sufixo = SUFIXO_DO_ATO_DO_CIVIL.get(str(tipo or "").strip().upper())
    if not segmento or sufixo is None:
        return None
    caminho = f"/selo/civil/{segmento}{sufixo}"
    return caminho if caminho in selador.ENDPOINTS else None


# ------------------------------------- o envelope do selo do civil
#
# O QUE VAI DENTRO, MEDIDO NOS 175 SELOS DAS ESPECIES (27/08/2026)
#     Os 175 carregam a MESMA estrutura, sem excecao: o codigo do ato, o
#     `dadosSelo` com escrevente, livro, folha, termo e versao da tabela de
#     custas, o nome da parte em dois lugares, e o papel de seguranca.
#
#     Ver DOCUMENTACAO/SELO_DO_CIVIL_MEDIDO.md.
#
# O CODIGO DO ATO TEM DUAS PROCEDENCIAS, E ELAS FICAM MARCADAS
#     `MEDIDO` e o que saiu do que a casa mandou de verdade — 18 selos com
#     `14.a`, 8 com `14.c`, 109 com `14.5.1`. `TABELA` e o que saiu da tabela
#     de precos do TJMA, lida pela descricao do proprio item: «Assento de
#     natimorto, bem como pela primeira certidao respectiva. Isento» e `14.d`,
#     e nao ha como isso ser outra coisa.
#
#     Nenhum dos dois e chute. Onde nao ha nem um nem outro, o valor e None e
#     o ato sai sem selo dizendo por que — que e a regra da casa: nao se
#     inventa numero, nome nem codigo.
# --------------------------------- QUEM GASTA FOLHA DE SEGURANCA
#
# MEDIDO NO CONTRATO EM 28/08/2026, e desmentiu o que o sistema fazia.
#     `papelMoeda` aparece em **19 dos 100** caminhos do civil. Os outros 81 —
#     toda averbacao, toda anotacao, toda retificacao, toda certidao negativa,
#     a habilitacao e a conversao — nao tem o campo, porque nao imprimem
#     certidao em folha de seguranca.
#
# O QUE ISSO CONSERTA, E ERA CARO DOS DOIS LADOS
#     `_selar_o_ato` reservava e dava baixa numa folha para TODO ato do civil.
#     Uma averbacao a margem gastava uma folha que ninguem imprimia — e, pior,
#     com o estoque vazio ela era **lavrada sem selo**, com a tela dizendo que
#     faltava folha de seguranca para um ato que nao usa nenhuma.
#
# A REGRA FICA: a folha se gasta quando o ENVELOPE a leva. Nao e lista de
# espécies nem de tipos de ato — e o contrato quem diz.
CAMINHOS_QUE_GASTAM_FOLHA: frozenset[str] = frozenset({
    # os registros que ja saem com a primeira certidao
    "/selo/civil/casamento",
    "/selo/civil/nascimento",
    "/selo/civil/natimorto",
    "/selo/civil/obito",
    # e as segundas vias, que sao certidao por definicao
    "/selo/civil/ausencia/segunda-via",
    "/selo/civil/casamento/segunda-via",
    "/selo/civil/casamento/transcricao/segunda-via",
    "/selo/civil/curatela/segunda-via",
    "/selo/civil/emancipacao/segunda-via",
    "/selo/civil/interdicao/segunda-via",
    "/selo/civil/nascimento/segunda-via",
    "/selo/civil/nascimento/transcricao/segunda-via",
    "/selo/civil/natimorto/segunda-via",
    "/selo/civil/obito/segunda-via",
    "/selo/civil/obito/transcricao/segunda-via",
    "/selo/civil/opcao-nacionalidade/segunda-via",
    "/selo/civil/separacao-divorcio/segunda-via",
    "/selo/civil/tutela/segunda-via",
    "/selo/civil/uniao-estavel/segunda-via",
})


def gasta_folha_de_seguranca(caminho: Any) -> bool:
    """Se aquele selo leva `papelMoeda`, e portanto consome uma folha. So calcula."""
    return str(caminho or "") in CAMINHOS_QUE_GASTAM_FOLHA


MEDIDO, TABELA = "MEDIDO", "TABELA"

CODIGO_DO_REGISTRO_DO_CIVIL: dict[str, tuple[str, str]] = {
    "NASCIMENTO": ("14.a", MEDIDO),          # 18 selos
    "OBITO": ("14.c", MEDIDO),               # 8 selos
    "NATIMORTO": ("14.d", TABELA),
    "CASAMENTO": ("14.1.1", TABELA),
    "CASAMENTO_RELIGIOSO": ("14.1.1", TABELA),   # o item diz «inclusive o religioso»
    "PROCLAMAS": ("14.1.2", TABELA),             # afixacao e publicacao do edital
    "EMANCIPACAO": ("14.2", TABELA),
    "TUTELA": ("14.2", TABELA),
    "INTERDICAO": ("14.2", TABELA),
    "AUSENCIA": ("14.2", TABELA),
    "UNIAO_ESTAVEL": ("14.8", TABELA),
    "OPCAO_NACIONALIDADE": ("14.3.2", TABELA),
}

# OS TRES DO MEIO NAO MUDAM COM A ESPECIE. A averbacao a margem custa o mesmo
# no nascimento e no obito — o que muda e o caminho, e nao o item da tabela.
CODIGO_DO_ATO_DO_CIVIL: dict[str, tuple[str, str]] = {
    "AVERBACAO": ("14.4.1", TABELA),         # lavrada a margem do registro
    "ANOTACAO": ("14.7", TABELA),
    "RETIFICACAO": ("14.10", TABELA),        # retificacao simples
}

# A CERTIDAO TEM DUAS FORMAS, e as duas foram medidas: 109 selos com `14.5.1`
# (uma folha) e 237 com `14.5.6` (inteiro teor).
CODIGO_DA_CERTIDAO = ("14.5.1", MEDIDO)
CODIGO_DA_CERTIDAO_INTEIRO_TEOR = ("14.5.6", MEDIDO)

# O QUE A LEI ISENTA, e esta escrito na propria tabela de precos: «Registro de
# nascimento, bem como pela primeira certidao respectiva. **Isento**». O selo
# leva a isencao e o motivo dela — foi assim em 19 dos 28 selos de nascimento e
# em 7 dos 8 de obito.

# Averbação RCPN: o que sela (oficial 15/09/2026) — NÃO o quadro inteiro do
# protocolo. Só 14.4.1; arquivamento 14.12 vira UM pedido com quantidade=N
# (padrão RTD/RCPJ), nunca N selos.
CODIGO_AVERBACAO_RCPN = "14.4.1"
CODIGO_ARQUIVAMENTO_RCPN = "14.12"


def itens_selo_averbacao_rcpn(
        linhas_protocolo: list | None = None) -> list[tuple[str, int]]:
    """Itens que a averbação RCPN manda ao selador. Só calcula.

    Decisão do oficial (15/09/2026): sem escolher quais selos; não usar todos.
    Padrão: sempre 14.4.1; se protocolo tiver 14.12 com N → um 14.12 com N.
    """
    itens: list[tuple[str, int]] = [(CODIGO_AVERBACAO_RCPN, 1)]
    q_arquiv = 0
    for linha in (linhas_protocolo or []):
        if isinstance(linha, (tuple, list)) and len(linha) >= 2:
            codigo, quantidade = linha[0], linha[1]
        elif isinstance(linha, dict):
            codigo = linha.get("codigo_ato") or linha.get("codigo") or ""
            quantidade = linha.get("quantidade") or 1
        else:
            continue
        cod = str(codigo or "").strip()
        if cod == CODIGO_ARQUIVAMENTO_RCPN or cod.startswith("14.12"):
            try:
                q_arquiv += max(1, int(quantidade or 1))
            except (TypeError, ValueError):
                q_arquiv += 1
    if q_arquiv:
        itens.append((CODIGO_ARQUIVAMENTO_RCPN, q_arquiv))
    return itens


MOTIVO_DA_ISENCAO: dict[str, str] = {
    "14.a": "REGISTRO DE NASCIMENTO",
    "14.c": "REGISTRO DE ÓBITO",
    "14.d": "REGISTRO DE NATIMORTO",
}

FORNECEDOR_DO_PAPEL = "ARPENBRASIL"

# A VERSAO DA TABELA DE CUSTAS NAO E UMA SO, E ISSO FOI CORRECAO DE 27/08/2026.
#
#     Eu havia posto o valor do civil — `0120260101` — numa configuracao unica,
#     como se ele valesse para a casa inteira. A medicao dos selos de 2026
#     desmentiu na mesma tarde:
#
#         civil    0120260101      protesto  0320260101
#         imovel   0220260101      rtdpj     0420250101
#         notas    0520260101
#
#     Os dois ultimos algarismos NAO variam com o ano: variam com a ATRIBUICAO.
#     O prefixo e o numero da secao dela na tabela do TJMA, e o resto e a data
#     em que a tabela passou a valer.
#
#     Mandar `01` num selo de protesto seria dizer ao aparelho que o ato foi
#     cobrado por outra tabela — e o valor conferido do outro lado nao fecharia.
#
# A DATA E CONFIGURACAO; O PREFIXO E MEDIDO. A data muda quando o TJMA publica
# tabela nova (e ai o balcao nao pode esperar por programador); o prefixo e a
# secao da atribuicao, e essa nao muda.
PREFIXO_DA_TABELA_DE_CUSTAS: dict[str, str] = {
    "civil": "01",
    "imovel": "02",
    "protesto": "03",
    "rtdpj": "04",
    "notas": "05",
}


def versao_da_tabela_de_custas(caminho: Any, data_da_tabela: Any) -> str | None:
    """`/selo/protesto/titulo` + `20260101` -> `0320260101`. So calcula.

    Devolve None quando a atribuicao do caminho nao tem prefixo medido — e
    None aqui quer dizer «este selo nao sai», que e melhor que sair com a
    tabela de outra atribuicao.
    """
    partes = [x for x in str(caminho or "").split("/") if x]
    prefixo = PREFIXO_DA_TABELA_DE_CUSTAS.get(partes[1]) if len(partes) > 1         else None
    data = "".join(c for c in str(data_da_tabela or "") if c.isdigit())
    if not prefixo or len(data) != 8:
        return None
    return f"{prefixo}{data}"


def codigo_do_ato_do_civil(especie: Any, tipo: Any, *,
                           inteiro_teor: bool = False) -> tuple[str, str] | None:
    """O item da tabela de custas daquele ato, e de onde ele saiu. So calcula.

    Devolve `(codigo, procedencia)` ou None. None quer dizer «nao ha item
    conhecido para isto» — e o ato sai sem selo, dizendo por que.
    """
    t = str(tipo or "").strip().upper()
    if t == "CERTIDAO":
        return CODIGO_DA_CERTIDAO_INTEIRO_TEOR if inteiro_teor             else CODIGO_DA_CERTIDAO
    if t == "REGISTRO":
        return CODIGO_DO_REGISTRO_DO_CIVIL.get(
            str(especie or "").strip().upper())
    return CODIGO_DO_ATO_DO_CIVIL.get(t)


def envelope_do_civil(*, especie: Any, tipo: Any, escrevente: Any, livro: Any,
                      folha: Any, termo: Any, nome_parte: Any,
                      versao_tabela: Any, papel: Any = None,
                      inteiro_teor: bool = False,
                      codigo_tj: Any = None,
                      isento: bool = False,
                      motivo_isencao: Any = None) -> dict:
    """O que vai dentro do pedido de selo do civil. So calcula.

    NAO FALA COM A REDE E NAO GRAVA — para a tela poder MOSTRAR o envelope
    antes de ele sair, como a ajuda ja faz com a pergunta. Quem manda dado
    para fora tem direito de ver o que esta mandando.

    RECUSA COM FRASE DE BALCAO o que falta, e nomeia o que falta. Um envelope
    incompleto sai daqui como erro de regra; se saisse pela rede, voltaria como
    HTTP 400 com o texto do fornecedor, que ninguem no balcao entende.
    """
    # O ITEM VEM DE FORA QUANDO O ESCREVENTE MARCOU UM — decisao do oficial em
    # 27/08/2026: «todos os selos sao automaticos, escolhendo pelo item da
    # tabela de emolumentos». O item medido continua valendo para o que a LEI
    # ja resolve sozinha: o registro de nascimento e o de obito sao ISENTOS, e
    # o item deles (`14.a`, `14.c`) nao e escolha de ninguem.
    achado = ((str(codigo_tj).strip(), MEDIDO) if str(codigo_tj or "").strip()
              else codigo_do_ato_do_civil(especie, tipo,
                                          inteiro_teor=inteiro_teor))
    if not achado:
        raise AtoError(
            f"Não há item da tabela de custas conhecido para "
            f"{str(tipo).lower()} de {str(especie).lower().replace('_', ' ')}. "
            f"O ato fica sem selo até alguém medir qual é.")
    codigo, _procedencia = achado

    faltando = [nome for nome, valor in
                (("o escrevente", escrevente), ("o livro", livro),
                 ("a folha", folha), ("o termo", termo),
                 ("o nome da parte", nome_parte),
                 ("a versão da tabela de custas", versao_tabela))
                if not str(valor or "").strip()]
    if faltando:
        raise AtoError(
            f"O selo do Registro Civil não sai sem {', '.join(faltando)}. "
            f"Isso vem do próprio ato — se está faltando, o ato foi lavrado "
            f"sem essa informação.")

    dados_selo: dict[str, Any] = {
        "escrevente": str(escrevente).strip(),
        "livro": str(livro).strip(),
        "folha": str(folha).strip(),
        "termo": str(termo).strip(),
        "versaoTabelaDeCustas": str(versao_tabela).strip(),
    }
    motivo = MOTIVO_DA_ISENCAO.get(codigo)
    if motivo:
        dados_selo["isentoGratuito"] = "ISENTO"
        dados_selo["motivoIsentoGratuito"] = motivo
    elif isento:
        # **O CAMPO DA ISENÇÃO SE CHAMA `isento`, E ISSO ESTÁ MEDIDO EM TRÊS
        # LUGARES — correção de 10/09/2026, do relato do oficial: «verifique o
        # problema do selo gratuito de certidão do Marcos Dione».**
        #
        # Aqui ia **só** `isentoGratuito: "GRATUITO"`, e esse par não existe:
        #
        #   · o CONTRATO do selador não tem `isentoGratuito` em schema nenhum
        #     (zero ocorrências em `selador.py`, que é gerado da documentação
        #     oficial). O que ele declara é `CAMPOS_ISENTO = ("value",
        #     "motivo")` — o campo é `isento`;
        #   · o ACERVO concorda: `selador.ALEM_DA_DOCUMENTACAO` registra
        #     `DadosSeloCertidaoRI.isento` com **667 usos** medidos nos
        #     envelopes reais desta casa;
        #   · e a palavra `GRATUITO` aparece em **ZERO dos 26.177 selos** que
        #     esta serventia já emitiu.
        #
        # **O QUE O APARELHO ACEITOU, MEDIDO CONTRA ELE MESMO EM 08/09/2026:**
        # a averbação do CPF passou com `dadosSelo.isento = true` (HTTP 200,
        # selo `AVERBA000000VBKH58VIXU0CLW81`, texto «Selo Isento»), e a forma
        # que **falhou** foi justamente a do `isentoGratuito` sozinho. A
        # prenotação do RI manda a mesma coisa — `isento` booleano mais
        # `motivoIsentoGratuito` —, e ali são 48 envelopes isentos em 829
        # medidos.
        #
        # **A CONSEQUÊNCIA ERA CERTIDÃO SEM SELO.** Marcado o selo gratuito, o
        # envelope saía com um campo que o aparelho não conhece e o selo não
        # vinha; a certidão ficava lavrada sem selo, e a folha de segurança
        # nem se gastava (ela só se gasta se o selo sair). Medido na produção:
        # as certidões 16, 17 e 23 do assento 1233 — três tentativas, dois
        # cancelamentos e nenhuma folha consumida.
        #
        # **`isentoGratuito` FICA, e não é teimosia:** ele é o que os 26 selos
        # de REGISTRO de nascimento levaram (ramo de cima, `MOTIVO_DA_ISENCAO`)
        # e esses funcionam. Tirá-lo daqui mexeria num envelope que passa hoje
        # para consertar outro que não passa. O que entra é o campo do
        # contrato, ao lado.
        motivo_escrito = str(motivo_isencao or "").strip()
        if not motivo_escrito:
            raise AtoError(
                "Ato gratuito / isento precisa do motivo escrito — é ele que a "
                "conferência do Tribunal lê no selo.")
        dados_selo["isento"] = True
        dados_selo["isentoGratuito"] = "GRATUITO"
        dados_selo["motivoIsentoGratuito"] = motivo_escrito.upper()

    nome = str(nome_parte).strip()
    envelope: dict[str, Any] = {
        # O NOME DO CAMPO MUDA COM O ATO, e foi medido assim: o registro manda
        # `codigoTipoAtoRegistro` e a certidao manda `codigoTipoAtoCertidao`.
        ("codigoTipoAtoCertidao"
         if str(tipo).strip().upper() == "CERTIDAO"
         else "codigoTipoAtoRegistro"): codigo,
        "dadosSelo": dados_selo,
        # O NOME VAI EM DOIS LUGARES, e vai nos 175 medidos. Mandar so um dos
        # dois seria supor qual deles o aparelho le.
        "nomeParte": nome,
        "parte": {"nome": nome},
    }
    if papel:
        envelope["papelMoeda"] = {"codigo": str(papel).strip(),
                                  "fornecedor": FORNECEDOR_DO_PAPEL,
                                  "utilizado": False}
    return envelope



# ------------------------------- o envelope do selo da averbação do civil
#
# Schema oficial `DadosSeloAverbacaoRegistroCivil` (selador_reais.json):
#   alteracao, codigoAto, dadosSelo  — required
#   tipoAverbacao                    — required
#   seloRetificacao                  — optional
#
# O envelope genérico `envelope_do_civil` manda `codigoTipoAtoRegistro` — certo
# para registro/certidão, ERRADO para `/selo/civil/{especie}/averbacao`.
#
# MEDIÇÃO (08/09/2026): zero memJson desta casa com tipoAverbacao/alteracao —
# a casa NUNCA selou civil/averbação pelo caminho específico. TipoAverbacao.jsonl
# só tem códigos de RI (206 retificação, 207 baixa). Não há CPF/inclusão medido.
#
# Por isso `tipoAverbacao` é parâmetro obrigatório do chamador. O atalho do CPF
# (art. 347) usa `TIPO_AVERBACAO_CPF_ART_347` — constante **UNMEASURED**: se o
# Tribunal recusar, a mensagem do aparelho sobe ao balcão; NÃO se inventa selo.

TIPO_AVERBACAO_CPF_ART_347 = 0
# O contrato DadosSeloAverbacaoRegistroCivil limita `alteracao` a 1..500.
# O teor completo fica em rc_atos.teor; o envelope manda resumo ≤500.
ALTERACAO_SELO_MAX = 500

def recortar_alteracao_do_selo(alteracao: Any) -> str:
    """Padrão da casa: `alteracao` do envelope civil tem teto 1..500 (TJMA).

    O teor completo continua em `rc_atos.teor`. Só o envelope do selador
    leva o recorte — senão o Tribunal responde «tamanho ... entre 1 e 500»
    e o lançamento é desfeito. Não inventar texto: só corta o que passou.
    """
    texto = str(alteracao or "").strip()
    if not texto:
        return ""
    if len(texto) <= ALTERACAO_SELO_MAX:
        return texto
    return texto[: ALTERACAO_SELO_MAX - 3].rstrip() + "..."



# Naturezas do formulário de averbação RCPN (lista/select no balcão).
# MEDIDO nesta casa: só `cpf_347` → tipo_selo 0 (= TIPO_AVERBACAO_CPF_ART_347).
# PENDENTE (tipo_selo=None): alteração de nome, retificação, reconhecimento de
# filiação, outra — NÃO há enum civil medido; TipoAverbacao.jsonl é RI (206/207);
# selador_reais.json sem enum civil. NÃO inventar código do Tribunal para
# alteração de nome (caso Guilhermy etc.).
NATUREZAS_AVERBACAO_CIVIL = [
    # MEDIDO 15/09/2026: nesta casa TODOS os selos de
    # /selo/civil/nascimento|casamento/averbacao saíram com tipoAverbacao=0
    # (dezenas de CPF). O schema não traz enum; o teor vai em `alteracao`.
    # Sem outro valor medido — 0 é o código que o aparelho já aceita neste
    # caminho. Natureza distinta = texto da averbação, não outro inteiro.
    {"codigo_form": "cpf_347",
     "rotulo": "Inclusão de CPF (art. 347)",
     "tipo_selo": TIPO_AVERBACAO_CPF_ART_347},  # MEDIDO (=0)
    {"codigo_form": "alteracao_nome",
     "rotulo": "Alteração / inclusão de prenome ou sobrenome",
     "tipo_selo": TIPO_AVERBACAO_CPF_ART_347},  # MEDIDO no mesmo endpoint (=0)
    {"codigo_form": "retificacao",
     "rotulo": "Retificação de assento",
     "tipo_selo": TIPO_AVERBACAO_CPF_ART_347},  # MEDIDO no mesmo endpoint (=0)
    {"codigo_form": "reconhecimento_filiacao",
     "rotulo": "Reconhecimento de filiação",
     "tipo_selo": TIPO_AVERBACAO_CPF_ART_347},  # MEDIDO no mesmo endpoint (=0)
    {"codigo_form": "outra",
     "rotulo": "Outra averbação civil",
     "tipo_selo": TIPO_AVERBACAO_CPF_ART_347},  # MEDIDO no mesmo endpoint (=0)
]


def tipo_selo_da_natureza_averbacao(codigo_form):
    """Resolve chave do formulário → tipo_selo (int) ou None se pendente.

    Desconhecida / vazia → None. Não inventa número do Tribunal.
    """
    chave = str(codigo_form or "").strip()
    if not chave:
        return None
    for item in NATUREZAS_AVERBACAO_CIVIL:
        if item["codigo_form"] == chave:
            return item["tipo_selo"]
    return None



def envelope_da_averbacao_civil(*, escrevente: Any, livro: Any, folha: Any,
                                termo: Any, versao_tabela: Any,
                                alteracao: Any, tipo_averbacao: Any,
                                codigo_tj: Any = None,
                                isento: bool = False,
                                motivo_isencao: Any = None,
                                selo_retificacao: Any = None,
                                quantidade: Any = 1) -> dict:
    """Envelope `DadosSeloAverbacaoRegistroCivil`. Só calcula.

    NÃO FALA COM A REDE E NÃO GRAVA. Recusa com frase de balcão o que falta.
    """
    codigo = str(codigo_tj or CODIGO_DO_ATO_DO_CIVIL["AVERBACAO"][0]).strip()
    if not codigo:
        raise AtoError(
            "A averbação do Registro Civil não tem item da tabela de custas "
            "conhecido (14.4.1). O ato fica sem selo.")

    faltando = [nome for nome, valor in
                (("o escrevente", escrevente), ("o livro", livro),
                 ("a folha", folha), ("o termo", termo),
                 ("a versão da tabela de custas", versao_tabela),
                 ("o teor da alteração (alteracao)", alteracao))
                if not str(valor or "").strip()]
    if faltando:
        raise AtoError(
            f"O selo da averbação do Registro Civil não sai sem "
            f"{', '.join(faltando)}.")

    if tipo_averbacao is None or str(tipo_averbacao).strip() == "":
        raise AtoError(
            "O selo da averbação exige o tipoAverbacao do Tribunal, e esta "
            "casa ainda não tem valor medido para esse tipo de averbação "
            "(nunca selou /selo/civil/.../averbacao). Informe o código na "
            "tela ou aguarde a conferência com o selador.")

    try:
        tipo_int = int(tipo_averbacao)
    except (TypeError, ValueError) as erro:
        raise AtoError(
            f"tipoAverbacao tem de ser um número do contrato do selador — "
            f"veio «{tipo_averbacao}».") from erro

    
    alteracao = recortar_alteracao_do_selo(alteracao)

    dados_selo: dict[str, Any] = {
        "escrevente": str(escrevente).strip(),
        "livro": str(livro).strip(),
        "folha": str(folha).strip(),
        "termo": str(termo).strip(),
        "versaoTabelaDeCustas": str(versao_tabela).strip(),
    }
    # dadosSelo.isento (Boolean) - required by /averbacao; isentoGratuito alone
    # is not enough (HTTP 400: precisa informar se o selo e isento).
    motivo_top: str | None = None
    motivo = MOTIVO_DA_ISENCAO.get(codigo)
    if motivo:
        dados_selo["isentoGratuito"] = "ISENTO"
        dados_selo["motivoIsentoGratuito"] = motivo
        motivo_top = motivo
    elif isento:
        motivo_escrito = str(motivo_isencao or "").strip()
        if not motivo_escrito:
            raise AtoError(
                "Ato gratuito / isento precisa do motivo escrito — é ele que a "
                "conferência do Tribunal lê no selo.")
        dados_selo["isentoGratuito"] = "GRATUITO"
        dados_selo["motivoIsentoGratuito"] = motivo_escrito.upper()
        motivo_top = motivo_escrito.upper()

    # MEDIDO via erro Jackson 08/09/2026: DadosSelo.isento e java.lang.Boolean
    # (nao DadosIsento object; nao top-level). Sem ele o Tribunal responde
    # HTTP 400: precisa informar se o selo e isento. isentoGratuito continua
    # para a gratuidade (forma medida em 14.a/14.c).
    dados_selo["isento"] = bool(motivo_top)

    envelope: dict[str, Any] = {
        "codigoAto": codigo,
        "alteracao": str(alteracao).strip(),
        "tipoAverbacao": tipo_int,
        "dadosSelo": dados_selo,
    }
    q = max(1, int(quantidade or 1))
    if q > 1 or str(codigo).strip() == CODIGO_ARQUIVAMENTO_RCPN:
        envelope["quantidade"] = q
    if selo_retificacao and str(selo_retificacao).strip():
        envelope["seloRetificacao"] = str(selo_retificacao).strip()
    return envelope


# ------------------------------- o envelope do selo da habilitação de casamento
#
# DECISÃO DO OFICIAL EM 28/08/2026: **dois selos** — um na habilitação e outro
# no assento de casamento.
#
#   Perguntei porque não havia o que imitar, e o quadro era claro: o contrato
#   TEM os caminhos (`/selo/civil/casamento/habilitacao` e
#   `/selo/civil/casamento`), e **esta casa nunca selou por nenhum deles** —
#   nem usou item `14.1.*` em envelope algum. Os 20 casamentos do acervo são
#   quase todos de 1957 a 1988, anteriores ao selo eletrônico, que começou aqui
#   em 19/03/2020.
#
# O CONTRATO CONFIRMA O DESENHO DELE, e isso não é coincidência: o campo
# `seloReferencia` do selo do ASSENTO existe para citar **o selo do ato de
# habilitação**. Um selo só não teria o que referenciar.

# O tipo de casamento, do contrato (`DadosSeloHabilitacaoCasamento.tipoCasamento`):
#
#   0 - Civil; 1 - Religioso com efeito civil; 2 - Conversão em casamento civil
#
# São os mesmos três de `hc_schema.TIPOS`, e a tradução mora aqui — no lugar
# onde o envelope se monta, e não espalhada por quem chama.
TIPO_DE_CASAMENTO: dict[str, int] = {
    "CIVIL": 0,
    "RELIGIOSO": 1,
    "CONVERSAO": 2,
}

# O item da tabela de custas da habilitação, medido no cadastro desta casa:
# `14.1.1 — Habilitação e registro, lavratura de assento de casamento,
# inclusive o religioso`.
CODIGO_DA_HABILITACAO = "14.1.1"

# DE QUE CAMINHO SELA CADA TIPO DE HABILITACAO, do contrato.
#
#   Os tres tipos de `hc_schema.TIPOS` nao selam pelos tres mesmos lugares: o
#   civil e o religioso com efeito civil sao habilitacao comum, e a conversao
#   de uniao estavel tem endpoint e schema so dela.
CAMINHO_DA_HABILITACAO: dict[str, str] = {
    "CIVIL": "/selo/civil/casamento/habilitacao",
    "RELIGIOSO": "/selo/civil/casamento/habilitacao",
    "CONVERSAO": "/selo/civil/casamento/conversao",
}


def envelope_da_habilitacao(*, escrevente: Any, versao_tabela: Any,
                            tipo: Any, numero_processo: Any = None,
                            nubente1: Any = None, nubente2: Any = None,
                            codigo_tj: Any = None, livro: Any = None,
                            folha: Any = None, termo: Any = None) -> dict:
    """O que vai dentro do pedido de selo da habilitação. So calcula.

    NAO FALA COM A REDE E NAO GRAVA — a tela pode mostrar o envelope antes de
    ele sair, como a ajuda faz com a pergunta.

    O LIVRO E A FOLHA SAO OPCIONAIS AQUI, e no assento nao serao: a habilitacao
    e processo, e nao ato de livro. O `dadosSelo` do contrato os aceita vazios,
    e mandar livro inventado seria dizer ao Tribunal que a habilitacao ocupou
    face de livro que ela nao ocupa.
    """
    faltando = [nome for nome, valor in
                (("o escrevente", escrevente),
                 ("a versão da tabela de custas", versao_tabela))
                if not str(valor or "").strip()]
    if faltando:
        raise AtoError(
            f"O selo da habilitação não sai sem {', '.join(faltando)}.")
    chave = str(tipo or "").strip().upper()
    if chave not in TIPO_DE_CASAMENTO:
        raise AtoError(
            f"Não sei que tipo de casamento é {tipo!r} — o selo pede civil, "
            f"religioso com efeito civil ou conversão de união estável.")
    # NA CONVERSAO O NUMERO DO PROCESSO E OBRIGATORIO, e nao e o desta
    # habilitacao: `DadosSeloHabilitacaoCasamentoConversao.numeroProcesso` diz,
    # com todas as letras, «numero do processo da uniao estavel». Deixar em
    # branco faria o aparelho recusar depois — e recusar no balcao, com a frase
    # que diz o que buscar, custa menos que recusar na rede.
    if chave == "CONVERSAO" and not str(numero_processo or "").strip():
        raise AtoError(
            "O selo da conversão de união estável não sai sem o número do "
            "processo da união estável — é o que o Tribunal pede para ligar a "
            "conversão à união que ela converte.")

    dados_selo: dict[str, Any] = {
        "escrevente": str(escrevente).strip(),
        "versaoTabelaDeCustas": str(versao_tabela).strip(),
    }
    for campo, valor in (("livro", livro), ("folha", folha), ("termo", termo)):
        if str(valor or "").strip():
            dados_selo[campo] = str(valor).strip()

    def _parte(quem) -> dict | None:
        nome = str((quem or {}).get("nome") or "").strip()
        if not nome:
            return None
        documento = "".join(c for c in str((quem or {}).get("documento") or "")
                            if c.isdigit())
        parte: dict[str, Any] = {"nome": nome}
        if documento:
            parte["documento"] = documento
        return parte

    envelope: dict[str, Any] = {
        "codigoTipoAtoRegistro": str(codigo_tj or CODIGO_DA_HABILITACAO).strip(),
        "dadosSelo": dados_selo,
        "tipoCasamento": TIPO_DE_CASAMENTO[chave],
    }
    if str(numero_processo or "").strip():
        envelope["numeroProcesso"] = str(numero_processo).strip()
    # O NOME VAI EM DOIS LUGARES, como no envelope do civil: o contrato tem
    # `nomePrimeiroNubente` (texto) e `primeiroNubente` (ParteAto). Mandar so um
    # dos dois seria supor qual deles o aparelho le.
    for n, (rotulo, campo, quem) in enumerate(
            (("nomePrimeiroNubente", "primeiroNubente", nubente1),
             ("nomeSegundoNubente", "segundoNubente", nubente2)), start=1):
        parte = _parte(quem)
        if parte:
            envelope[rotulo] = parte["nome"]
            envelope[campo] = parte
    return envelope


# ---------------------- O SELO DO ASSENTO DE CASAMENTO, E O UNICO CASO DELE
#
# UM SELO SO, E ELE E O DA HABILITACAO — decisao do oficial em 28/08/2026:
#
#     «O selo é emitido uma vez apenas. Ele é reaproveitado apenas no assento,
#      mas já foi emitido na habilitação.»
#
# E a tabela de custas concorda: o item `14.1.1` e um so — «Habilitacao **e
# registro**, lavratura de assento de casamento (...) compreendendo todas as
# despesas». Um item, um selo. Eu havia construido este envelope lendo o
# CONTRATO (que tem dois endpoints) em vez da TABELA (que e quem diz quanto se
# cobra), cheguei a apaga-lo, e ele volta por um motivo so.
#
# O UNICO CASO: A HABILITACAO E DE OUTRA SERVENTIA (item 14.1.6 da tabela —
# «lavratura de assento de casamento a vista de certidao de habilitacao emitida
# por outra serventia»). Ai nao ha selo desta casa a reaproveitar, porque quem
# habilitou e selou foi o outro cartorio, e o oficial decidiu em 28/08/2026 que
# este assento **compra selo proprio, citando o de fora**.
#
# E O CONTRATO TEM OS DOIS CAMPOS EXATAMENTE PARA ISSO:
#   `seloReferencia`              o selo do ato de habilitacao — o de la
#   `localRealizacaoHabilitacao`  onde a habilitacao foi feita
#
# A TRAVA CONTRA COBRAR DUAS VEZES NAO MORA AQUI, e isso e deliberado: esta
# funcao so calcula. Quem decide comprar ou reaproveitar e a tela, e ela decide
# por uma coisa que o escrevente RESPONDE — de que serventia veio a habilitacao
# —, e nao por deducao. Os dois caminhos sao exclusivos por construcao:
# `rc_assentos.habilitacao_serventia` preenchida quer dizer «de fora».


def envelope_do_casamento(*, escrevente: Any, versao_tabela: Any, tipo: Any,
                          livro: Any, folha: Any, termo: Any,
                          papel: Any, numero_processo: Any = None,
                          nubente1: Any = None, nubente2: Any = None,
                          codigo_tj: Any = None,
                          selo_da_habilitacao: Any = None,
                          local_da_habilitacao: Any = None) -> dict:
    """O que vai dentro do pedido de selo do assento de casamento. So calcula.

    SO SE USA QUANDO A HABILITACAO E DE OUTRA SERVENTIA. Ver o bloco acima: no
    caso comum o assento nao compra selo nenhum — ele recebe o da habilitacao.

    O PAPEL DE SEGURANCA E OBRIGATORIO AQUI, e quem o exige e o contrato
    (`papelMoeda` required em `DadosSeloCasamento`) — diferente da habilitacao,
    que nao imprime certidao e por isso nao gasta folha.
    """
    envelope = envelope_da_habilitacao(
        escrevente=escrevente, versao_tabela=versao_tabela, tipo=tipo,
        numero_processo=numero_processo, nubente1=nubente1, nubente2=nubente2,
        codigo_tj=codigo_tj, livro=livro, folha=folha, termo=termo)
    faltando = [nome for nome, valor in
                (("o livro", livro), ("a folha", folha), ("o termo", termo),
                 ("a folha de segurança", papel))
                if not str(valor or "").strip()]
    if faltando:
        raise AtoError(
            f"O selo do assento de casamento não sai sem {', '.join(faltando)}. "
            f"Isso vem do próprio ato — se está faltando, o ato foi lavrado "
            f"sem essa informação.")
    envelope["papelMoeda"] = {"codigo": str(papel).strip(),
                              "fornecedor": FORNECEDOR_DO_PAPEL,
                              "utilizado": False}
    if str(selo_da_habilitacao or "").strip():
        envelope["seloReferencia"] = str(selo_da_habilitacao).strip()
    if str(local_da_habilitacao or "").strip():
        envelope["localRealizacaoHabilitacao"] = str(local_da_habilitacao).strip()
    return envelope


# ------------------------------------ o envelope do selo do Protesto
#
# A NATUREZA NAO ERA ADIVINHACAO: ESTAVA NA DOCUMENTACAO OFICIAL.
#     Medindo os selos, `natureza.tipo` variava dentro do mesmo caminho — 8 em
#     431 pagamentos e 0 em 34 — e eu escrevi que «sai de outra coisa, que nao
#     medi». Saia do contrato: o `selador-doc` do protesto traz o enum inteiro.
#
#         0 Intimacao por Carta Protocolada   6 Certidao por inteiro teor
#         1 Intimacao por Carta Registrada    7 Protesto de titulo
#         2 Intimacao por Edital              8 Pagamento de titulo
#         3 Certidao por nome                 9 Retirada de titulo
#         4 Certidao por titulo acrescido    10 Outro
#         5 Certidao por titulo digitado
#
#     E aí a medicao encaixa: pagamento 8 (431 selos), retirada 9 (147),
#     certidao 0 (57 de 57 — esta casa busca por nome).
NATUREZA_DO_PROTESTO: dict[str, int] = {
    "PROTESTO": 7,
    "PAGAMENTO": 8,
    "RETIRADA": 9,
    "DESISTENCIA": 9,
    "CANCELAMENTO": 9,
    # A CERTIDAO TEM O SEU PROPRIO ENUM, e este foi um defeito meu de dois
    # minutos: escrevi `3` porque no enum do TITULO o 3 e «Certidao por nome».
    # So que a certidao nao usa o enum do titulo — ela usa
    # `DadosNaturezaCertidaoProtesto`, onde:
    #
    #     0 Certidao por nome        2 Certidao por titulo digitado
    #     1 Certidao por titulo acrescido   3 Certidao por inteiro teor
    #
    # O que me pegou foi o proprio comentario: eu tinha escrito «57 de 57 com
    # tipo 0» e codificado 3. **Campo com o mesmo nome em dois schemas nao tem
    # o mesmo significado** — e a casa emite por NOME, medido nos 57 selos e na
    # propria busca da certidao, que procura pelo nome e pelo documento.
    "CERTIDAO": 0,
    # OS TRES TIPOS DE CERTIDAO SELAM PELO MESMO ENUM. O que muda entre a
    # negativa, a positiva e a de cancelamento e o TEOR do papel, e nao a forma
    # da busca — e o enum da certidao pergunta pela BUSCA: por nome, por titulo
    # acrescido, por titulo digitado, por inteiro teor. Esta casa busca por
    # nome nos tres casos.
    "NEGATIVA": 0,
    "POSITIVA": 0,
}

# A INTIMACAO E O UNICO ATO CUJA NATUREZA DEPENDE DE COMO ELA ACONTECEU, e o
# sistema ja sabe disso: `protesto_aviso` grava o modo — PESSOAL quando o papel
# chegou na mao, EDITAL quando nao chegou.
#
# PESSOAL E «CARTA PROTOCOLADA», E NAO «REGISTRADA»: quem entrega nesta casa e
# a propria casa (`ENTREGADORES = ('CARTORIO',)`), e as 1.618 entregas saíram
# com taxa de AR zero — ninguem mandou pelos Correios.
NATUREZA_DA_INTIMACAO: dict[str, int] = {"PESSOAL": 0, "EDITAL": 2}


def natureza_do_protesto(tipo: Any, modo: Any = None,
                         tabela: Any = None) -> int | None:
    """O codigo da natureza daquele ato, pelo contrato do selador. So calcula.

    A TABELA DESEMPATA `CANCELAMENTO`, e isso foi defeito meu de um minuto: a
    palavra vale para duas coisas diferentes nesta casa — a BAIXA do protesto
    (`pt_atos`), que e natureza 9, e a CERTIDAO de cancelamento
    (`pt_certidoes`), que e certidao como as outras e sai por busca de nome.

    E a mesma armadilha do enum da certidao, meia hora depois: **a mesma
    palavra em dois lugares nao quer dizer a mesma coisa.**
    """
    t = str(tipo or "").strip().upper()
    if str(tabela or "") == "pt_certidoes":
        # Toda certidao do Protesto sai pelo enum DA CERTIDAO, onde 0 e «por
        # nome» — que e como esta casa busca, nos tres tipos de certidao.
        return 0
    if t in ("INTIMACAO", "APONTAMENTO"):
        return NATUREZA_DA_INTIMACAO.get(str(modo or "PESSOAL").strip().upper())
    return NATUREZA_DO_PROTESTO.get(t)


# O QUE A CASA MANDOU NA CERTIDÃO DO PROTESTO, que não tem título — medido nos
# 57 envelopes de `/selo/protesto/certidao` (15/10/2026): protocolo «0» em 51
# (os outros 6 citam o protocolo de um título achado) e livro «1» em 57.
PROTOCOLO_DA_CERTIDAO_DO_PROTESTO = "0"
LIVRO_DA_CERTIDAO_DO_PROTESTO = "1"


def envelope_do_protesto(*, tipo: Any, codigo_tj: Any, escrevente: Any,
                         protocolo: Any, versao_tabela: Any,
                         partes: Any = None, livro: Any = None,
                         folha: Any = None, valor_centavos: Any = None,
                         modo: Any = None, tabela: Any = None) -> dict:
    """O que vai dentro do pedido de selo do Protesto. So calcula.

    UM ENVELOPE POR ITEM DE CUSTA, e nao um por ato — decisao do oficial em
    27/08/2026, e e o que o E-Oficio fazia: na retirada, os itens `17.10.1`,
    `17.4` e `17.2` saem SEMPRE JUNTOS, 49 vezes cada. Quem chama monta um
    envelope para cada item que o escrevente marcou para cobrar.

    O `convenio` NAO VAI, e isso e medido: ele esta ausente em 440 dos 465
    selos de pagamento. Mandar campo que a casa nao mandava e inventar.
    """
    natureza = natureza_do_protesto(tipo, modo, tabela)
    if natureza is None:
        raise AtoError(
            f"Não sei que natureza de selo corresponde a {str(tipo).lower()} "
            f"no Protesto. O ato fica sem selo.")
    # A CERTIDÃO POR NOME NÃO TEM TÍTULO, E POR ISSO NÃO TEM PROTOCOLO —
    # conserto pedido pelo oficial em 15/10/2026. Esta função exigia o
    # protocolo do título também da certidão, e a certidão (busca por nome ou
    # documento) nunca tem título vinculado: o selo automático dela não saía
    # nunca. Medido nos 57 envelopes de `/selo/protesto/certidao` do acervo:
    # `selo.protocolo` = «0» em 51 e `selo.livro` = «1» em 57 — é o que a
    # casa mandou quando não havia título, e é o que vai.
    eh_certidao = str(tabela or "") == "pt_certidoes"
    if eh_certidao:
        protocolo = str(protocolo or "").strip() or PROTOCOLO_DA_CERTIDAO_DO_PROTESTO
        livro = livro or LIVRO_DA_CERTIDAO_DO_PROTESTO
    faltando = [nome for nome, valor in
                (("o item da tabela de custas", codigo_tj),
                 ("o escrevente", escrevente), ("o protocolo", protocolo),
                 ("a versão da tabela de custas", versao_tabela))
                if not str(valor or "").strip()]
    if faltando:
        raise AtoError(
            f"O selo do Protesto não sai sem {', '.join(faltando)}.")

    selo: dict[str, Any] = {"escrevente": str(escrevente).strip(),
                            "protocolo": str(protocolo).strip()}
    if livro:
        selo["livro"] = str(livro)
    if folha:
        selo["folha"] = str(folha)
    if valor_centavos is not None:
        # O VALOR VAI EM REAIS, e o caixa desta casa conta em centavos. A
        # divisao acontece na fronteira, num lugar so.
        selo["valorTitulo"] = round(int(valor_centavos) / 100, 2)
    if eh_certidao:
        # `quantidade` 1 nos 57 envelopes da certidão, e só neles: os outros
        # caminhos do Protesto não o mandavam, e não passam a mandar.
        return {
            "natureza": {"tipo": int(natureza)},
            "quantidade": 1,
            "selo": selo,
            "ato": {"codigo": str(codigo_tj).strip(),
                    "codigoTabelaCusta": str(versao_tabela).strip()},
            "partes": {"nomePartes": [],
                       "parteAto": [{"nome": str(p.get("nome") or "").strip(),
                                     "documento": "".join(
                                         c for c in str(p.get("documento") or "")
                                         if c.isdigit())}
                                    for p in (partes or [])]},
        }
    return {
        "natureza": {"tipo": int(natureza)},
        "selo": selo,
        "ato": {"codigo": str(codigo_tj).strip(),
                "codigoTabelaCusta": str(versao_tabela).strip()},
        # `nomePartes` VAZIO E O QUE A CASA MANDAVA: o contrato diz que ele
        # existe «apenas para compatibilidade com versoes anteriores», e os
        # 1.308 selos do protesto o mandaram vazio, com o nome em `parteAto`.
        "partes": {"nomePartes": [],
                   "parteAto": [{"nome": str(p.get("nome") or "").strip(),
                                 "documento": "".join(
                                     c for c in str(p.get("documento") or "")
                                     if c.isdigit())}
                                for p in (partes or [])]},
    }



# ---------------------------------------------- o envelope do selo do RTDPJ
#
# Pedido do oficial (11/09/2026): averbacao RCPJ/RTD sela sozinha ao lavrar,
# como o RCPN. Os caminhos proprios da averbacao, por serie:
#
#     PJ   /selo/rtdpj/pessoa-juridica/averbacao
#     TD   /selo/rtdpj/ato-declarado/averbacao/integral/sem-valor
#
# Ambos usam o schema `RtdpjSemValorDeclarado` (medido no
# `ato-declarado/integral/sem-valor`, 27 usos). REGISTRO e CANCELAMENTO
# seguem em `atos-em-geral` (53 usos) — AtosEmGeral, sem protocolo.
#
# SEM PROTOCOLO NA AVERBACAO ESPECIFICA: nao se inventa numero. Quem chama
# cai no caminho generico `atos-em-geral` (mesmo item, envelope mais curto)
# ou devolve o ato SEM SELO — nunca com selo inventado.

SERIES_RCPJ_DO_SELO = ("PJ_A", "PJ_B")
SERIES_RTD_DO_SELO = ("TD_B", "TD_C", "TD_F")

CAMINHO_AVERBACAO_PJ = "/selo/rtdpj/pessoa-juridica/averbacao"
CAMINHO_AVERBACAO_TD = "/selo/rtdpj/ato-declarado/averbacao/integral/sem-valor"
CAMINHO_RTDPJ_GERAL = "/selo/rtdpj/atos-em-geral"


def caminho_do_rtdpj(tipo: Any, serie: Any = None) -> str | None:
    """O endpoint do selador do RCPJ/RTD, pela serie. So calcula.

    A SERIE DECIDE A FAMILIA: PJ_A/PJ_B sao pessoa juridica; TD_* sao titulo
    e documento. Averbar um estatuto pelo caminho de titulo mentiria na
    conferencia, e o contrario tambem.
    """
    tipo_u = str(tipo or "").strip().upper()
    serie_u = str(serie or "").strip().upper()
    eh_pj = serie_u in SERIES_RCPJ_DO_SELO or serie_u.startswith("PJ_")
    if tipo_u == "AVERBACAO":
        return CAMINHO_AVERBACAO_PJ if eh_pj else CAMINHO_AVERBACAO_TD
    if tipo_u in ("REGISTRO", "CANCELAMENTO"):
        return CAMINHO_RTDPJ_GERAL
    return CAMINHO_DO_ATO.get(("rg_atos", tipo_u))


def _partes_rtdpj(partes: Any) -> dict:
    return {"nomePartes": [],
            "parteAto": [{"nome": str(p.get("nome") or "").strip(),
                          "documento": "".join(
                              c for c in str(p.get("documento") or "")
                              if c.isdigit())}
                         for p in (partes or [])
                         if str((p or {}).get("nome") or "").strip()]}


def envelope_do_rtdpj(*, caminho: Any, codigo_tj: Any, escrevente: Any,
                      versao_tabela: Any, partes: Any = None,
                      natureza_descricao: Any = None,
                      natureza_tipo: Any = 0, livro: Any = None,
                      folha: Any = None, protocolo: Any = None,
                      registro_averbacao: Any = None,
                      quantidade: Any = 1, isento: bool = False,
                      motivo_isencao: Any = None) -> dict:
    """O que vai dentro do pedido de selo do RCPJ/RTD. So calcula.

    Dois formatos, pelo caminho:
      - `atos-em-geral`        → AtosEmGeral (escrevente, partes, ato)
      - averbacao PJ/TD        → RtdpjSemValorDeclarado (natureza, selo, ...)

    O PROTOCOLO NA AVERBACAO ESPECIFICA E OBRIGATORIO no schema. Sem ele, esta
    funcao recusa — quem chama decide cair no caminho generico ou deixar o
    ato sem selo. Inventar protocolo aqui seria o mesmo vicio do selo inventado.

    O ATO GRATUITO LEVA `isento` (LD05, 21/10/2026) — CN-MA art. 133: o ato
    isento ou gratuito tem selo de categoria propria, e sem este campo o
    RTD/RCPJ nao tinha como lavrar um. E a forma `DadosIsento` do AtosEmGeral
    (`selador.CAMPOS_ISENTO`: value + motivo), a mesma do arquivamento do RI e
    das Notas, com o motivo escrito — e ele que a correicao le. No caminho
    proprio da averbacao (RtdpjSemValorDeclarado) a isencao NAO esta medida:
    recusa, em vez de mandar um campo que o aparelho nunca viu.
    """
    caminho = str(caminho or "").strip()
    faltando = [nome for nome, valor in
                (("o item da tabela de custas", codigo_tj),
                 ("o escrevente", escrevente),
                 ("a versão da tabela de custas", versao_tabela))
                if not str(valor or "").strip()]
    if faltando:
        raise AtoError(
            f"O selo do RCPJ/RTD não sai sem {', '.join(faltando)}.")

    ato = {"codigo": str(codigo_tj).strip(),
           "codigoTabelaCusta": str(versao_tabela).strip()}
    pessoas = _partes_rtdpj(partes)
    motivo = str(motivo_isencao or "").strip()
    if isento and not motivo:
        raise AtoError(
            "Ato gratuito precisa do fundamento escrito — é ele que a "
            "correição lê no selo (CN-MA art. 133).")

    if caminho == CAMINHO_RTDPJ_GERAL or caminho.endswith("/atos-em-geral"):
        envelope = {"escrevente": str(escrevente).strip(),
                    "partes": pessoas,
                    "quantidade": max(1, int(quantidade or 1)),
                    "ato": ato}
        if isento:
            envelope["isento"] = {"value": True, "motivo": motivo}
        return envelope
    if isento:
        raise AtoError(
            "O selo isento da averbação do RCPJ/RTD pelo caminho próprio não "
            "está medido; o ato gratuito sela pelo caminho geral.")

    # RtdpjSemValorDeclarado — pessoa-juridica/averbacao e
    # ato-declarado/averbacao/integral/sem-valor.
    precisa = [nome for nome, valor in
               (("o livro", livro),
                ("o protocolo", protocolo),
                ("o número do registro/averbação", registro_averbacao))
               if not str(valor or "").strip()]
    if precisa:
        raise AtoError(
            f"O selo da averbação RCPJ/RTD não sai sem {', '.join(precisa)}.")

    descricao = str(natureza_descricao or "").strip() or "AVERBACAO"
    selo: dict[str, Any] = {
        "escrevente": str(escrevente).strip(),
        "livro": str(livro).strip(),
        "protocolo": str(protocolo).strip(),
        "registroAverbacao": str(registro_averbacao).strip(),
    }
    if folha is not None and str(folha).strip():
        selo["folha"] = str(folha).strip()
    return {
        "natureza": {"tipo": int(natureza_tipo or 0), "descricao": descricao},
        "partes": pessoas,
        "quantidade": max(1, int(quantidade or 1)),
        "selo": selo,
        "ato": ato,
    }


# --------------------------------------- o envelope do selo das NOTAS
#
# METADE DO MOVIMENTO DESTA CASA SAI POR AQUI: 13.776 selos de reconhecimento de
# firma, 3.664 de autenticacao e 2.667 de cartao — 96% dos 20.883 selos de
# notas do acervo.
#
# AS TRES FORMAS SAO DIFERENTES, e nenhuma se monta a partir da outra:
#
#     reconhecimento  escrevente, natureza{tipo}, nomesReconhecido{...}, ato{}
#     autenticacao    escrevente, quantidade, ato{}
#     cartao          escrevente, partes{...}, ato{}
#
# Repare que o reconhecimento chama o campo de `nomesReconhecido`, e o cartao
# chama de `partes`. E o mesmo conteudo com dois nomes — e mandar o nome errado
# e o aparelho recusar.
CAMINHO_DAS_NOTAS: dict[str, str] = {
    "nt_reconhecimentos": "/selo/notas/reconhecimento-firma",
    # Mesmo caminho e mesmo item 413 («sinal, letra e firma»). Tabela propria
    # para o reconhecimento AUTONOMO do sinal — a abertura NAO sela.
    "nt_sinais_reconhecimentos": "/selo/notas/reconhecimento-firma",
    "nt_autenticacoes": "/selo/notas/autenticacao",
    "nt_cartoes": "/selo/notas/cartao-assinatura",
}

# A NATUREZA DA FIRMA JA ESTAVA NO CONTRATO — `selador.NATUREZA_FIRMA`:
#
#     0 Reconhecimento de firma por autenticidade
#     1 Reconhecimento de firma por semelhanca
#
# E o sistema ja guarda qual e: `nt_reconhecimentos.especie`. Medido, os dois
# lados batem — SEMELHANCA sao 11.410 atos no sistema para 11.919 selos com
# `tipo: 1`; AUTENTICIDADE, 1.802 para 1.857 com `tipo: 0`.
NATUREZA_DA_FIRMA: dict[str, int] = {"AUTENTICIDADE": 0, "SEMELHANCA": 1}


def envelope_das_notas(*, tabela: Any, codigo_tj: Any, escrevente: Any,
                       versao_tabela: Any, especie: Any = None,
                       partes: Any = None, quantidade: Any = None) -> dict:
    """O que vai dentro do pedido de selo das Notas. So calcula.

    O ITEM DE CUSTA NAO SE ADIVINHA: ele vem de `servico_codigo`, que o ato ja
    guarda. Medido nos 13.776 reconhecimentos — o servico 413 e o item
    `13.17.2`, o 416 e o `13.17.4` (documento com conteudo financeiro) e o 414
    e o `13.17.3` (transferencia de veiculo). Quem escolheu foi quem atendeu.
    """
    caminho = CAMINHO_DAS_NOTAS.get(str(tabela or ""))
    if not caminho:
        raise AtoError(
            f"Não há caminho de selo medido para {tabela!r} nas Notas.")
    faltando = [nome for nome, valor in
                (("o item da tabela de custas", codigo_tj),
                 ("o escrevente", escrevente),
                 ("a versão da tabela de custas", versao_tabela))
                if not str(valor or "").strip()]
    if faltando:
        raise AtoError(f"O selo das Notas não sai sem {', '.join(faltando)}.")

    def _pessoas() -> dict:
        return {"nomePartes": [],
                "parteAto": [{"nome": str(p.get("nome") or "").strip(),
                              "documento": "".join(
                                  c for c in str(p.get("documento") or "")
                                  if c.isdigit())}
                             for p in (partes or [])]}

    envelope: dict[str, Any] = {
        "escrevente": str(escrevente).strip(),
        "ato": {"codigo": str(codigo_tj).strip(),
                "codigoTabelaCusta": str(versao_tabela).strip()},
    }
    if tabela in ("nt_reconhecimentos", "nt_sinais_reconhecimentos"):
        # Sinal autonomo usa o mesmo envelope medido do reconhecimento-firma
        # (item 413). Especie padrao SEMELHANCA: confronto com o PDF da central.
        natureza = NATUREZA_DA_FIRMA.get(str(especie or "").strip().upper())
        if natureza is None:
            raise AtoError(
                f"Não sei se {str(especie).lower()} é reconhecimento por "
                f"semelhança ou por autenticidade — e o selo pede um dos dois.")
        envelope["natureza"] = {"tipo": natureza}
        # O NOME DO CAMPO E `nomesReconhecido` AQUI, e `partes` no cartao.
        envelope["nomesReconhecido"] = _pessoas()
    elif tabela == "nt_cartoes":
        envelope["partes"] = _pessoas()
    else:
        # A autenticacao manda QUANTIDADE, e nao parte: o que se autentica e
        # copia, e o que se cobra e por copia. Medido: 1 em 3.664 de 3.664.
        envelope["quantidade"] = int(quantidade or 1)
    return envelope


# ---------------------------------------------- o selo da prenotacao do RI
#
# MEDIDO EM 829 ENVELOPES de `/selo/imovel/prenotacao`, e cada valor abaixo tem
# a sua contagem. Nada aqui e suposicao.
#
#   livro                 "1A" em 829/829  — e o Livro 1-A de PROTOCOLO, e nao
#                                            o livro de destino do titulo
#   folha                 0     em 773/829
#   naturezaTitulo        126.0 em 829/829
#   percentualDesconto    0.0   em 829/829
#   descontoProvimento279 False em 829/829  — Provimento do AMAZONAS, ver selador
#   reterIss              False em 829/829
#   codigoTipoAto         16.1  em 797/829, 16.39 em 32
#   isento                False em 781, True em 48 (com motivoIsentoGratuito)

LIVRO_DO_PROTOCOLO_DO_RI = "1A"
NATUREZA_DO_TITULO_DA_PRENOTACAO = 126.0
CODIGO_DA_PRENOTACAO = "16.1"


# ------------------------------------------ o ato do RI: registro e averbacao
#
# **O CAMINHO DO ATO DO RI NAO E `atos-em-geral`, E A MEDICAO DESMENTIU O
# PALPITE.** `/selo/imovel/atos-em-geral` parece o obvio pelo nome, e a casa o
# usou 451 vezes — mas medindo o `ato.codigo` dos 451 envelopes, 371 deles sao
# `16.24.4` e `16.24.4.1`, que sao itens de CERTIDAO. Aquele caminho foi o
# guarda-chuva do E-Oficio para o que nao tinha caminho proprio.
#
# Os dois caminhos do registro e da averbacao sao outros, e duas fontes
# independentes concordam:
#
#   1. O ACERVO — 86 envelopes em `/selo/imovel/ato-declarado/sem-valor` e 34
#      em `/selo/imovel/ato-declarado/com-valor`, todos com `matricula`,
#      `protocolo` e `registroAverbacao` no topo: e o ato da matricula.
#   2. O CONTRATO — a descricao dos dois, em `selador.py`, diz com todas as
#      letras «gerar o selo de registro/averbacao de imovel para o ato com (ou
#      sem) valor declarado».
#
# QUEM ESCOLHE ENTRE ELES E O VALOR DECLARADO, e nao o tipo do ato: ha
# averbacao com valor e registro sem. Por isso `caminho_do_ato` NAO responde
# por `ri_atos` — quem responde e `caminho_do_ato_do_ri(base_calculo)`.
#
# O que se mediu nos 120 envelopes, campo por campo:
#
#   naturezaTitulo        126.0 em 120/120
#   percentualDesconto    0.0   em 120/120
#   descontoProvimento279 False em 120/120
#   reterIss              False em 120/120
#   isento                False em 120/120
#   partes.nomePartes     []    em 120/120  — sempre vazia; quem vale e parteAto
#   quantidade            1     em 86/86 no SEM valor; ausente nos 34 com valor
#   baseCalculo           presente nos 34 com valor; ausente nos 86 sem
#   registroAverbacao     o NUMERO do ato como texto ('1','2','4','5','16')
#   livro                 o VOLUME da matricula ('2S','2R','2-Q'), nao o "1A"
#   folha                 AUSENTE em 78/120, e `'0'` (TEXTO) nos outros 42
#                         — nunca outro valor. Sai daqui ausente, que e a forma
#                         da maioria; `folha` zero nao e folha nenhuma.
#
#                         E O TIPO MERECE NOTA, porque o irmao diverge: no
#                         acervo da PRENOTACAO `folha` e o texto `'0'` em
#                         773/829, e `envelope_da_prenotacao` manda o INTEIRO
#                         `0`. Parecia defeito; nao e — aquele envelope saiu de
#                         verdade em 09/09/2026 e o selo voltou. **O aparelho
#                         aceita as duas formas**, e por isso o que funciona
#                         fica como esta.
#   codigoTipoAto         VARIA, e por isso a tela pergunta:
#                           sem valor: 16.22.2 (48), 16.5 (18), 16.9 (10),
#                                      16.22.4 (7), 16.24.1 (1), 16.2 (1)
#                           com valor: 16.3 (19), 16.9 (10), 16.11 (2),
#                                      16.45 (2), 16.22.4 (1)
#
# E `parteAto` vem de DUAS FORMAS no acervo: `{nome, documento}` em 190 e
# `{nome}` sozinho em 46. Mandar `documento: ""` onde a casa mandava so o nome
# seria inventar um campo vazio que ela nunca mandou.

CAMINHO_DO_ATO_DO_RI_SEM_VALOR = "/selo/imovel/ato-declarado/sem-valor"
CAMINHO_DO_ATO_DO_RI_COM_VALOR = "/selo/imovel/ato-declarado/com-valor"
NATUREZA_DO_TITULO_DO_ATO_DO_RI = 126.0

def itens_medidos_do_ato_do_ri() -> list[tuple[str, int]]:
    """Os itens de custa que esta casa usou no selo do ato, por uso. So le.

    **A LISTA NAO SE ESCREVE AQUI: ela ja e medida do acervo**, em
    `atribuicoes.ITENS_DE_CUSTA_POR_CAMINHO`, que e gerado dos 24.849 selos
    reais. Escrever uma segunda copia foi o que eu fiz na primeira versao
    desta funcao — e ela **ja nasceu divergente**: faltava o `16.22.4.2`, de
    um uso so, que a lista gerada tem e a minha, digitada a olho, nao.
    Duas reguas para o mesmo fato divergem no primeiro conserto; esta
    divergiu antes do primeiro.

    AS DUAS FAMILIAS VEM JUNTAS porque quem esta digitando ainda nao disse se
    o ato tem valor declarado — e o item que serve a um caminho pode servir ao
    outro: `16.9` e `16.22.4` aparecem nos dois.
    """
    soma: dict[str, int] = {}
    for caminho in (CAMINHO_DO_ATO_DO_RI_SEM_VALOR,
                    CAMINHO_DO_ATO_DO_RI_COM_VALOR):
        for codigo, usos in ATR.itens_de_custa_do_ato(caminho).items():
            soma[codigo] = soma.get(codigo, 0) + usos
    return sorted(soma.items(), key=lambda p: (-p[1], p[0]))


# OS MOTIVOS DE GRATUIDADE QUE ESTA CASA ESCREVEU NO SELO DO RI — medidos nos
# 48 envelopes isentos da prenotacao, que sao o unico precedente da atribuicao.
#
# **A GRATUIDADE E EXCECAO NO RI, E O NUMERO DIZ ISSO**: 48 de 829 prenotacoes
# (5,8%), e **ZERO dos 120 atos** de registro/averbacao. O ato gratuito e caso
# raro, e a tela o trata como tal.
#
# **POR QUE UM CATALOGO, SE O CAMPO CONTINUA LIVRE.** Os 48 motivos sao, em
# sua maioria, a MESMA coisa escrita de quinze maneiras — e com erro de
# digitacao que vai impresso no selo: «INTERESE SOCILA», «PAGAEMENTO»,
# «RELACINADOS», e um «LEI N 13.465, DE 2022» onde a lei e de 2017. O
# catalogo oferece a forma canonica na ordem de uso; **quem atende continua
# podendo escrever outra**, porque motivo de isencao e afirmacao juridica e ha
# casos que lista nenhuma cobre — o proprio acervo tem um com numero de
# processo dentro.
#
# O QUE ELE NAO DECIDE: se a serventia compensa o valor junto ao fundo. Isso
# nao esta medido e e decisao de quem responde pela casa.
MOTIVOS_DA_GRATUIDADE_DO_RI: tuple[dict, ...] = (
    {"texto": "O REGISTRO DISPENSA O PAGAMENTO DE EMOLUMENTOS PREVISTO NA "
              "LEI Nº 13.465, DE 2017.",
     "rotulo": "REURB-S — regularização fundiária de interesse social",
     "fundamento": "Lei n. 13.465/2017, art. 13, § 1º",
     "usos": 40},
    {"texto": "MANDADO JUDICIAL.",
     "rotulo": "Mandado judicial",
     "fundamento": "decisão judicial que determinou o ato",
     "usos": 2},
    {"texto": "JUSTIÇA GRATUITA DEFERIDA NOS AUTOS.",
     "rotulo": "Justiça gratuita deferida",
     "fundamento": "CPC, art. 98",
     "usos": 1},
    {"texto": "ART. 26-A DA LEI Nº 8.629, DE 1993, E ART. 290-A DA LEI "
              "Nº 6.015, DE 1973.",
     "rotulo": "Regularização fundiária rural / reforma agrária",
     "fundamento": "Lei n. 8.629/1993, art. 26-A; LRP, art. 290-A",
     "usos": 1},
)



# Itens da tabela TJMA em que a BASE enviada ao selador NAO e o valor cheio
# do imovel. Medido no caso de 21/09/2026 (AV-7 da matricula 4967): o item
# 16.22.4.1 foi selado com baseCalculo = valor total, e o TJ cobrou a faixa
# cheia. O texto do proprio item manda: emolumentos pela tabela 16.9, com
# reducao de 1/2 na base de calculo aferida no valor da area total do imovel.
CODIGOS_TJ_BASE_METADE = frozenset({
    "16.22.4.1",
})


def _codigo_tj_so_sem_valor_ri(codigo: str) -> bool:
    """Item medido so no caminho sem-valor do RI (ex.: 16.5).

    Beatriz 24/09/2026 — AV-01 da 4001: multi-selo com valor do imovel
    mandava 16.5 pelo /com-valor e o TJ recusou («valor declarado fora da
    faixa»). No acervo, 16.5 aparece 18 vezes em sem-valor e zero em
    com-valor; misturar a base do 16.22.8.1 nele e o erro.
    """
    cod = str(codigo or "").strip()
    if not cod:
        return False
    sem = ATR.itens_de_custa_do_ato(CAMINHO_DO_ATO_DO_RI_SEM_VALOR)
    com = ATR.itens_de_custa_do_ato(CAMINHO_DO_ATO_DO_RI_COM_VALOR)
    return cod in sem and cod not in com


def base_calculo_do_selo_ri(codigo_tj: Any, base_calculo: Any) -> float:
    """Base em reais que o envelope manda ao TJ.

    A tela guarda o valor do imovel; alguns itens da tabela pedem que o
    selador receba so uma fracao desse valor. Sem este corte o TJ calcula
    sobre o valor cheio e o ato sai mais caro do que a norma permite.

    Itens historicamente so-sem-valor (16.5 etc.) zeram a base: o caminho
    e o envelope ficam em /sem-valor mesmo quando o ato declara valor para
    outro item da mesma fila multi-selo.
    """
    try:
        valor = float(base_calculo or 0)
    except (TypeError, ValueError):
        valor = 0.0
    if valor <= 0:
        return 0.0
    codigo = str(codigo_tj or "").strip()
    if codigo in CODIGOS_TJ_BASE_METADE:
        return valor / 2.0
    if _codigo_tj_so_sem_valor_ri(codigo):
        return 0.0
    return valor


def caminho_do_ato_do_ri(base_calculo: Any = None) -> str:
    """Com valor declarado ou sem — e e o VALOR que decide, nao o tipo do ato.

    Nao devolve None: os dois caminhos existem e a casa usou os dois. Um
    registro de compra e venda vai pelo `com-valor`; uma averbacao de
    georreferenciamento, pelo `sem-valor`.
    """
    try:
        valor = float(base_calculo or 0)
    except (TypeError, ValueError):
        valor = 0.0
    return (CAMINHO_DO_ATO_DO_RI_COM_VALOR if valor > 0
            else CAMINHO_DO_ATO_DO_RI_SEM_VALOR)


#: HOTFIX-2026-10-13-02 (AV-08/1196, escrevente, 13/10/2026): o TJMA recusa
#: «O tamanho do campo "protocolo" deve estar entre 1 e 50». Ato de ofício
#: (encerramento por mudança da técnica, sem prenotação) mandava "". Vazio vira
#: PROTOCOLO_DE_OFICIO; acima de 50 caracteres, corta em 50.
PROTOCOLO_DE_OFICIO = "DE OFICIO"
LIMITE_DO_PROTOCOLO_NO_TJ = 50


def protocolo_para_o_tj(protocolo: Any) -> str:
    texto = " ".join(str(protocolo or "").split())
    if not texto:
        return PROTOCOLO_DE_OFICIO
    return texto[:LIMITE_DO_PROTOCOLO_NO_TJ]


def envelope_do_ato_do_ri(*, matricula: Any, numero_do_ato: Any,
                          escrevente: Any, versao_tabela: Any,
                          descricao_natureza: Any, livro: Any,
                          codigo_tj: Any, protocolo: Any = None,
                          base_calculo: Any = None, partes: Any = None,
                          isento: bool = False,
                          motivo_isencao: Any = None) -> dict:
    """O que vai dentro do pedido de selo do registro ou da averbacao do RI.

    So calcula: NAO FALA COM A REDE E NAO GRAVA — a tela pode mostrar o
    envelope antes de ele sair.

    O `livro` E O VOLUME DA MATRICULA ('2S', '2-Q'), e nao o `1A` da
    prenotacao: sao dois selos de dois atos diferentes, e mandar `1A` aqui
    diria ao Tribunal que o registro foi lavrado no livro de protocolo.
    """
    faltando = [nome for nome, valor in
                (("a matrícula", matricula),
                 ("o número do ato", numero_do_ato),
                 ("o escrevente", escrevente),
                 ("a versão da tabela de custas", versao_tabela),
                 ("a descrição da natureza", descricao_natureza),
                 ("o item da tabela de custas", codigo_tj))
                if not str(valor or "").strip()]
    if faltando:
        raise AtoError(
            f"O selo do ato do Registro de Imóveis não sai sem "
            f"{', '.join(faltando)}.")
    if isento and not str(motivo_isencao or "").strip():
        raise AtoError(
            "Ato isento precisa do motivo escrito — é ele que a inspeção lê "
            "para saber por que não se cobrou.")

    parte_ato = []
    for p in (partes or []):
        nome = str(p.get("nome") or "").strip()
        if not nome:
            continue
        documento = "".join(c for c in str(p.get("documento") or "")
                            if c.isdigit())
        # SO MANDA `documento` QUANDO ELE EXISTE — a casa mandou `{nome}`
        # sozinho em 46 dos 236 blocos de parte, e um `documento: ""` seria
        # campo inventado.
        parte_ato.append({"nome": nome, "documento": documento} if documento
                         else {"nome": nome})

    dados: dict[str, Any] = {
        "codigoTipoAto": str(codigo_tj).strip(),
        "descontoProvimento279": False,
        "descricaoNatureza": str(descricao_natureza).strip().upper(),
        "escrevente": str(escrevente).strip(),
        "isento": bool(isento),
        "livro": str(livro or "").strip(),
        "naturezaTitulo": NATUREZA_DO_TITULO_DO_ATO_DO_RI,
        "partes": {"nomePartes": [], "parteAto": parte_ato},
        "percentualDesconto": 0.0,
        "reterIss": False,
        "versaoTabelaDeCustas": str(versao_tabela).strip(),
    }
    if isento:
        dados["motivoIsentoGratuito"] = str(motivo_isencao).strip().upper()

    envelope: dict[str, Any] = {
        "matricula": str(matricula).strip(),
        "protocolo": protocolo_para_o_tj(protocolo),
        "registroAverbacao": str(numero_do_ato).strip(),
        "dadosSelo": dados,
    }
    # AS DUAS FORMAS SAO EXCLUSIVAS, e foi assim nos 120: `quantidade` no sem
    # valor, `baseCalculo` no com valor. Mandar os dois faria o envelope nao
    # ser nenhum dos dois que a casa mandou.
    # A BASE QUE O TJ VE PODE SER MENOR QUE A DECLARADA NA TELA — ver
    # base_calculo_do_selo_ri (16.22.4.1 e metade do valor do imovel).
    base_para_o_selo = base_calculo_do_selo_ri(codigo_tj, base_calculo)
    if caminho_do_ato_do_ri(base_para_o_selo) == CAMINHO_DO_ATO_DO_RI_COM_VALOR:
        envelope["baseCalculo"] = float(base_para_o_selo)
    else:
        envelope["quantidade"] = 1
    return envelope


# ---------------------------------------------- a ABERTURA da matricula


# O QUE O TRIBUNAL CHAMA DE NATUREZA DO TITULO NA ABERTURA — **127.0**, e nao
# os 126.0 do registro e da averbacao. Medido em 15/09/2026 nos 41 selos que
# esta casa emitiu por `/selo/imovel/lote/subdivisao`: 127.0 em 41 de 41.
#
#   MANDAR 126.0 AQUI SERIA DIZER AO TRIBUNAL QUE A ABERTURA E UM REGISTRO.
#   Os dois numeros estao a um digito de distancia e nenhum erro apareceria na
#   tela — a diferenca sairia no relatorio do TJMA, meses depois.
NATUREZA_DO_TITULO_DA_ABERTURA = 127.0

# O CAMINHO E MEDIDO, E NAO ESCOLHIDO POR PARECENCA. O item `16.2` («Matricula
# de imoveis no Registro Geral») saiu por tres caminhos nesta casa:
#
#   | caminho                              | usos do 16.2 |
#   |--------------------------------------|--------------|
#   | `/selo/imovel/lote/subdivisao`       | **41** — e o 16.2 e o UNICO item dele |
#   | `/selo/imovel/atos-em-geral`         | 3 |
#   | `/selo/imovel/ato-declarado/sem-valor` | 1 |
#
#   O nome do endpoint e do Tribunal e nao descreve bem o ato; **o que decide
#   e o que a casa mandou**, e ela mandou por aqui em 41 de 45. «Nao se sela
#   por caminho que a casa nunca usou» — e este ela usou, com exclusividade.

# ------------------------------------ arquivamento do RI (item 16.39)
#
# Pedido Beatriz 23/09/2026: na lavratura de registro/averbacao do RI,
# opcao (nao obrigatoria) de gerar tambem o selo de arquivamento, com a
# quantidade de folhas do documento/processo apresentado.
#
# MEDIDO NO ACERVO E NO PROTOCOLO:
#   - codigo TJ `16.39` = "Arquivamento, por folha do documento"
#   - caminho `/selo/imovel/atos-em-geral` (schema AtosEmGeral) — 22 usos
#     do 16.39 neste caminho; tambem apareceu em prenotacao (32x), mas o
#     arquivamento LIGADO A UM ATO da matricula sai pelo guarda-chuva
#     atos-em-geral, como o balcao ja fazia no E-Oficio
#   - quantidade = N folhas → UM pedido com quantidade=N (padrao RCPN
#     14.12 / RTDPJ 15.22), nunca N selos

CODIGO_ARQUIVAMENTO_RI = "16.39"
CAMINHO_ARQUIVAMENTO_RI = "/selo/imovel/atos-em-geral"


def envelope_do_arquivamento_do_ri(
        *, escrevente: Any, versao_tabela: Any, quantidade: Any,
        partes: Any = None, isento: bool = False,
        motivo_isencao: Any = None) -> dict:
    """Envelope AtosEmGeral do item 16.39 (arquivamento por folha). So calcula.

    Nao fala com a rede e nao grava. `quantidade` e o numero de folhas do
    documento/processo arquivado — o aparelho cobra por folha.

    ISENCAO HERDA DO ATO (Beatriz 23/09/2026, mat. 4019 / art. 290-A): o
    schema `AtosEmGeral` tem `isento` opcional (`DadosIsento`: value +
    motivo) — o mesmo formato das Notas. Sem isto o 16.39 saia cobrado mesmo
    quando o registro/averbacao era gratuito. Motivo escrito e obrigatorio
    quando isento (regra da casa desde 14/09/2026).
    """
    faltando = [nome for nome, valor in
                (("o escrevente", escrevente),
                 ("a versao da tabela de custas", versao_tabela))
                if not str(valor or "").strip()]
    if faltando:
        raise AtoError(
            f"O selo de arquivamento do RI nao sai sem "
            f"{', '.join(faltando)}.")
    try:
        q = int(quantidade)
    except (TypeError, ValueError) as erro:
        raise AtoError(
            "Informe quantas folhas o documento/processo tem "
            "(numero inteiro >= 1).") from erro
    if q < 1:
        raise AtoError(
            "Informe quantas folhas o documento/processo tem "
            "(numero inteiro >= 1).")
    if isento and not str(motivo_isencao or "").strip():
        raise AtoError(
            "Arquivamento isento precisa do motivo escrito — e o mesmo do "
            "ato (art. 290-A / REURB / etc.), e e ele que a correicao le.")
    pessoas = {"nomePartes": [],
               "parteAto": [{"nome": str(p.get("nome") or "").strip(),
                             "documento": "".join(
                                 c for c in str(p.get("documento") or "")
                                 if c.isdigit())}
                            for p in (partes or [])
                            if str((p or {}).get("nome") or "").strip()]}
    envelope: dict[str, Any] = {
        "escrevente": str(escrevente).strip(),
        "partes": pessoas,
        "quantidade": q,
        "ato": {"codigo": CODIGO_ARQUIVAMENTO_RI,
                "codigoTabelaCusta": str(versao_tabela).strip()},
    }
    if isento:
        # DadosIsento do contrato (CAMPOS_ISENTO = value, motivo) — medido
        # tambem nas Notas; AtosEmGeral.isento e optional no schema oficial.
        envelope["isento"] = {
            "value": True,
            "motivo": str(motivo_isencao).strip().upper(),
        }
    return envelope


CAMINHO_DA_ABERTURA = "/selo/imovel/lote/subdivisao"


def envelope_da_abertura_da_matricula(*, matricula: Any, escrevente: Any,
                                      versao_tabela: Any, livro: Any,
                                      codigo_tj: Any, protocolo: Any = None,
                                      folha: Any = None, partes: Any = None,
                                      isento: bool = False,
                                      motivo_isencao: Any = None) -> dict:
    """O que vai dentro do pedido de selo da ABERTURA de matricula.

    So calcula: NAO FALA COM A REDE E NAO GRAVA.

    **NAO E O ENVELOPE DO ATO**, e as diferencas sao medidas nos 41 selos
    reais desta casa, contra os 120 do registro/averbacao:

      - `naturezaTitulo` e **127.0**, e nao 126.0;
      - **nao ha `registroAverbacao`** — a abertura nao e ato numerado no
        livro, e mandar um numero ali seria inventar um R-1 que nao existe;
      - **nao ha `descricaoNatureza`** — o registro a exige, este nao a tem
        em nenhum dos 41;
      - **nao ha `quantidade` nem `baseCalculo`**: as duas formas que separam
        o «com valor» do «sem valor» no ato simplesmente nao aparecem aqui.

    A `matricula` VAI PREENCHIDA, e isso tambem e medido: 31 dos 41 a levam.
    Os dez vazios sao os mais antigos; mandar vazio hoje seria escolher a
    forma menos usada por comodidade.
    """
    faltando = [nome for nome, valor in
                (("a matrícula", matricula),
                 ("o escrevente", escrevente),
                 ("a versão da tabela de custas", versao_tabela),
                 ("o item da tabela de custas", codigo_tj))
                if not str(valor or "").strip()]
    if faltando:
        raise AtoError(
            f"O selo da abertura de matrícula não sai sem "
            f"{', '.join(faltando)}.")
    if isento and not str(motivo_isencao or "").strip():
        raise AtoError(
            "Abertura isenta precisa do motivo escrito — é ele que a inspeção "
            "lê para saber por que não se cobrou.")

    parte_ato = []
    for p in (partes or []):
        nome = str(p.get("nome") or "").strip()
        if not nome:
            continue
        documento = "".join(c for c in str(p.get("documento") or "")
                            if c.isdigit())
        parte_ato.append({"nome": nome, "documento": documento} if documento
                         else {"nome": nome})

    dados: dict[str, Any] = {
        "codigoTipoAto": str(codigo_tj).strip(),
        "descontoProvimento279": False,
        "escrevente": str(escrevente).strip(),
        "isento": bool(isento),
        "livro": str(livro or "").strip(),
        "naturezaTitulo": NATUREZA_DO_TITULO_DA_ABERTURA,
        "partes": {"nomePartes": [], "parteAto": parte_ato},
        "percentualDesconto": 0.0,
        "reterIss": False,
        "versaoTabelaDeCustas": str(versao_tabela).strip(),
    }
    # A `folha` E OPCIONAL, E ELA APARECEU EM 15 DOS 41 — sempre como `'0'`.
    # Quem a manda, manda zero; quem nao manda, omite. Escrever `'0'` sempre
    # seria acrescentar campo a 26 envelopes que nunca o tiveram.
    if folha is not None and str(folha).strip() != "":
        dados["folha"] = str(folha).strip()
    if isento:
        dados["motivoIsentoGratuito"] = str(motivo_isencao).strip().upper()

    return {
        "matricula": str(matricula).strip(),
        "protocolo": protocolo_para_o_tj(protocolo),
        "dadosSelo": dados,
    }


def envelope_da_prenotacao(*, protocolo: Any, escrevente: Any,
                           versao_tabela: Any, descricao_natureza: Any,
                           partes: Any = None, codigo_tj: Any = None,
                           isento: bool = False,
                           motivo_isencao: Any = None) -> dict:
    """O que vai dentro do pedido de selo da prenotacao. So calcula.

    NAO FALA COM A REDE E NAO GRAVA — a tela pode mostrar o envelope antes de
    ele sair, como a ajuda faz com a pergunta.

    O `livro` E O DE PROTOCOLO, e nao o de destino. Sao coisas diferentes e o
    balcao as confunde: o titulo vai para o Livro 2 ou para o 3, mas o selo da
    PRENOTACAO refere o Livro 1-A, onde a prenotacao mora. Mandar `2` aqui
    seria dizer ao Tribunal que a prenotacao foi lavrada no livro de
    matriculas.
    """
    faltando = [nome for nome, valor in
                (("o protocolo", protocolo),
                 ("o escrevente", escrevente),
                 ("a versão da tabela de custas", versao_tabela),
                 ("a natureza do título", descricao_natureza))
                if not str(valor or "").strip()]
    if faltando:
        raise AtoError(
            f"O selo da prenotação não sai sem {', '.join(faltando)}.")
    if isento and not str(motivo_isencao or "").strip():
        raise AtoError(
            "Prenotação isenta precisa do motivo escrito — é ele que a "
            "inspeção lê para saber por que não se cobrou.")
    dados: dict[str, Any] = {
        "codigoTipoAto": str(codigo_tj or CODIGO_DA_PRENOTACAO).strip(),
        "descontoProvimento279": False,
        "descricaoNatureza": str(descricao_natureza).strip().upper(),
        "escrevente": str(escrevente).strip(),
        "folha": 0,
        "isento": bool(isento),
        "livro": LIVRO_DO_PROTOCOLO_DO_RI,
        "naturezaTitulo": NATUREZA_DO_TITULO_DA_PRENOTACAO,
        "partes": {"parteAto": [
            {"nome": str(p.get("nome") or "").strip(),
             "documento": "".join(c for c in str(p.get("documento") or "")
                                  if c.isdigit())}
            for p in (partes or [])]},
        "percentualDesconto": 0.0,
        "reterIss": False,
        "versaoTabelaDeCustas": str(versao_tabela).strip(),
    }
    if isento:
        dados["motivoIsentoGratuito"] = str(motivo_isencao).strip().upper()
    return {"protocolo": protocolo_para_o_tj(protocolo), "dadosSelo": dados}


# **OS CODIGOS SAO DA TABELA, E NAO MEDIDOS PAR A PAR.** Nos 667 envelopes a
# casa usou tres: `16.24.1` (193), `16.24.4` (191) e `16.24.4.1` (148). O que
# NAO se mediu e qual deles foi com qual das nossas TRES especies de certidao —
# o acervo nao guarda o par. Entao a leitura e da tabela de
# emolumentos do TJMA, pela descricao do proprio item:
#
#     16.24.1    «Das certidoes: Com uma folha»
#     16.24.4    «Certidoes de inteiro teor, onus e de acoes reais e pessoais
#                 reipersecutorias e de cadeia dominial, com uma folha»
#
# `INTEIRO_TEOR` e `ONUS` estao nomeados no 16.24.4; o `PROPRIEDADE` cai no
# geral. **A procedencia fica marcada TABELA, e nao MEDIDO** — e a distincao
# importa: MEDIDO e o que a casa mandou, TABELA e o que a norma diz.
#
# **AS TRES ESPECIES, E NAO QUATRO** — problema #75, 18/09/2026. A «negativa
# de matricula» saiu da tela da matricula porque nao certifica a matricula: e
# busca pelo nome da pessoa nos livros (ver `ri_schema.TIPOS_CERTIDAO`). A
# chave sai daqui junto com o tipo, e nao por arrumacao: mapa de selo que
# aceita um tipo que a tela nao emite e porta aberta para o proximo codigo
# digitar `NEGATIVA` e o selador responder por uma busca que nao foi feita.
#
# **A DOMINIAL E A VINTENARIA SAO DO 16.24.4** — a descricao do item nomeia
# a «cadeia dominial» com todas as letras, e a vintenaria e a cadeia dominial
# recortada no tempo, com os onus do periodo (que o mesmo item tambem nomeia).
# Foi o mapa que a 3.6.233 usou em 28/09/2026 e com que a certidao 394/2026
# saiu selada (`CERELE…`); reposto em 14/10/2026, quando o codigo perdido foi
# reconstituido.
CODIGO_DA_CERTIDAO_DO_RI = {
    "INTEIRO_TEOR": "16.24.4",
    "ONUS": "16.24.4",
    "PROPRIEDADE": "16.24.1",
    "DOMINIAL": "16.24.4",
    "VINTENARIA": "16.24.4",
}
# Negativa de imovel — tela propria (indicador), nao a ficha (#75). Mesmo item
# 16.24.1 medido; mora fora de CODIGO_DA_CERTIDAO_DO_RI para o mapa bater com
# ri_schema.TIPOS_CERTIDAO (pytest #75).
CODIGO_DA_CERTIDAO_NEGATIVA_DE_IMOVEL = "16.24.1"
PROCEDENCIA_DO_CODIGO_DA_CERTIDAO_DO_RI = "TABELA"

# **A CERTIDAO DE MAIS DE UMA FOLHA SAO DOIS SELOS** — medido em 21/09/2026,
# nos 667 envelopes de `/selo/imovel/certidao` do acervo, agrupados pelo
# protocolo geral:
#
#   | o que saiu no protocolo | protocolos |
#   |---|---|
#   | `16.24.4` **+** `16.24.4.1` (inteiro teor + folha acrescida) | **99** |
#   | `16.24.1` **+** `16.24.2` (certidao comum + folha acrescida) | **94** |
#   | o item base sozinho | **88**, e a quantidade e **1** em todos |
#
#   E a quantidade diz o resto: o item BASE vai sempre com **1** (uma excecao
#   em 99), e quem carrega o numero e o item da FOLHA ACRESCIDA — 1, 2, 3, ate
#   12. A casa nao mandou «inteiro teor, quantidade 5»: mandou «inteiro teor,
#   1» **e** «folha acrescida, 4». A tabela diz o mesmo com todas as letras: o
#   `16.24.4.1` chama-se «por folha acrescida alem da primeira».
#
#   **O `16.24.1.1` APARECE UMA VEZ EM 667**, num protocolo que tem todos os
#   itens juntos. Um caso nao e regra, e por isso ele nao entra no mapa: o par
#   do `16.24.1` e o `16.24.2`, em 94 protocolos.
ITEM_DA_FOLHA_ACRESCIDA_DO_RI = {
    "16.24.4": "16.24.4.1",
    "16.24.1": "16.24.2",
}


def itens_da_certidao_do_ri(tipo: Any, folhas: int = 1) -> list[tuple[str, int]]:
    """Os itens de emolumento daquela certidao, na forma que a casa mandou.

    Devolve `[(codigo, quantidade), ...]` — **um selo por item**, que e a regra
    desta casa desde 27/08/2026 e que aqui tem 193 protocolos de prova. Uma
    folha da um item so; mais de uma da o par, com o excedente no segundo.

    **ISTO NAO ERA FEITO EM LUGAR NENHUM ATE 21/09/2026**: as duas telas que
    selam certidao — a do RI e a do Livro 3 — mandavam um item so, com
    quantidade 1, porque o campo que diria outra coisa nao existia em tela
    nenhuma. Dos 667 envelopes reais, **92 cobraram mais de uma folha**.
    """
    tipo_norm = str(tipo or "").strip().upper()
    base = CODIGO_DA_CERTIDAO_DO_RI.get(tipo_norm)
    if not base and tipo_norm == "NEGATIVA_IMOVEL":
        base = CODIGO_DA_CERTIDAO_NEGATIVA_DE_IMOVEL
    if not base:
        raise AtoError(
            f"não há código de emolumento medido para a certidão do tipo "
            f"«{tipo}». A certidão sai SEM SELO, e o selo se digita na ficha.")
    folhas = max(1, int(folhas or 1))
    itens = [(base, 1)]
    acrescida = ITEM_DA_FOLHA_ACRESCIDA_DO_RI.get(base)
    if folhas > 1 and acrescida:
        itens.append((acrescida, folhas - 1))
    return itens


def envelope_da_certidao_do_ri(*, tipo: Any, escrevente: Any, versao_tabela: Any,
                               quantidade: int = 1, requerente: Any = None,
                               requerente_documento: Any = None,
                               matricula: Any = None,
                               codigo_do_item: Any = None,
                               isento: bool = False,
                               motivo_isencao: Any = None) -> dict:
    """O corpo do pedido de `/selo/imovel/certidao`. **Medido em 667 envelopes.**

    Campo por campo, como esta casa os mandou:

    | campo | nos 667 |
    |---|---|
    | `descontoProvimento279` · `isento` · `reterIss` | `False` em 667 |
    | `percentualDesconto` | `0.0` em 667 |
    | `quantidade` | 1 em 575, 2 em 30, 3 em 29 — **e o numero de FOLHAS** |
    | `partes.nomePartes` | `[]` em 667 — vazio, e nao ausente |
    | `partes.parteAto` | um item, com `nome` e `documento` |

    **SEM REQUERENTE, VAI O NUMERO DA MATRICULA** — foi o que a casa fez:
    `{'documento': '00000000000', 'nome': 'MATRICULA 1116'}`. Mandar a lista
    vazia seria inventar um formato que ela nunca usou; inventar um nome seria
    pior.
    """
    # **O CODIGO PODE VIR PRONTO** — e o caso do item da folha acrescida, que
    # nao e um TIPO de certidao: e o segundo item do mesmo pedido, com o mesmo
    # corpo e outra linha da tabela. Ver `itens_da_certidao_do_ri`.
    tipo_norm = str(tipo or "").strip().upper()
    codigo = (str(codigo_do_item).strip() if codigo_do_item else
              CODIGO_DA_CERTIDAO_DO_RI.get(tipo_norm)
              or (CODIGO_DA_CERTIDAO_NEGATIVA_DE_IMOVEL
                  if tipo_norm == "NEGATIVA_IMOVEL" else None))
    if not codigo:
        raise AtoError(
            f"não há código de emolumento medido para a certidão do tipo "
            f"«{tipo}». A certidão sai SEM SELO, e o selo se digita na ficha.")
    if not str(versao_tabela or "").strip():
        raise AtoError(
            "falta a versão da tabela de custas, em Administrativo → "
            "Configurações.")

    nome = str(requerente or "").strip()
    doc = "".join(c for c in str(requerente_documento or "") if c.isdigit())
    if not nome:
        nome = f"MATRICULA {str(matricula or '').strip()}".strip()
        doc = doc or "00000000000"
    # GRATUIDADE NA CERTIDAO DO RI — 23/09/2026 (Beatriz, matricula 582).
    # Ate hoje `isento` ia False fixo (medido nos 667). Sem marcar continua
    # assim. Marcado, manda o mesmo par dos atos/prenotacao: `isento` True +
    # `motivoIsentoGratuito` (maiusculas). Motivo em branco recusa ANTES da
    # rede — e o limite do TJ e 500 caracteres.
    if isento and not str(motivo_isencao or "").strip():
        raise AtoError(
            "Certidao isenta precisa do motivo escrito — e ele que a "
            "inspecao le para saber por que nao se cobrou.")
    motivo_escrito = str(motivo_isencao or "").strip()
    if isento and len(motivo_escrito) > 500:
        raise AtoError(
            "Motivo da gratuidade tem no maximo 500 caracteres "
            "(limite do campo motivoIsentoGratuito no TJ).")
    dados = {
        "codigoTipoAto": codigo,
        "descontoProvimento279": False,
        "escrevente": str(escrevente or "").strip(),
        "isento": bool(isento),
        "partes": {"nomePartes": [],
                   "parteAto": [{"documento": doc or "00000000000",
                                 "nome": nome}]},
        "percentualDesconto": 0.0,
        "quantidade": max(1, int(quantidade or 1)),
        "reterIss": False,
        "versaoTabelaDeCustas": str(versao_tabela).strip(),
    }
    if isento:
        dados["motivoIsentoGratuito"] = motivo_escrito.upper()
    return dados



def caminho_do_ato(tabela: str, tipo: str,
                   especie: Any = None) -> str | None:
    """O endpoint do selador daquele ato, ou None se a casa nunca o usou.

    A ESPECIE SO IMPORTA NO CIVIL, e por isso ela e opcional: nas outras
    atribuicoes o par (tabela, tipo) basta. No RCPN, sem especie nao ha
    caminho — e devolver None e o certo, porque selar registro de obito pelo
    caminho do nascimento seria pior que nao selar.
    """
    if tabela in ("rc_atos", "rc_certidoes"):
        return caminho_do_civil(especie, tipo)
    if tabela == "hc_habilitacoes":
        # O CONTRATO TEM O CAMINHO, e a casa nunca o usou — mas aqui nao vale a
        # regra do «nao se sela por caminho que a casa nunca usou»: aquela
        # regra existe para nao ESCOLHER entre caminhos parecidos por
        # semelhanca. Aqui nao ha escolha: ha um caminho de habilitacao de
        # casamento, e o oficial decidiu que ela sela.
        #
        # A CONVERSAO DE UNIAO ESTAVEL TEM CAMINHO PROPRIO, e isto foi correcao
        # de 28/08/2026: eu mandava as tres pelo mesmo endpoint. O contrato tem
        # `/selo/civil/casamento/conversao`, com schema proprio
        # (`DadosSeloHabilitacaoCasamentoConversao`) onde `numeroProcesso` e
        # **required** — e o processo que ele pede e o da uniao estavel, nao o
        # da habilitacao. Mandar conversao pelo caminho comum e o mesmo erro de
        # selar obito pelo caminho do nascimento: passa perto e nao e.
        return CAMINHO_DA_HABILITACAO.get(
            str(especie or tipo or "").strip().upper(),
            "/selo/civil/casamento/habilitacao")
    if tabela == "ri_atos":
        # **O ATO DO RI NAO RESPONDE AQUI, E O None E DELIBERADO.** O caminho
        # dele depende do VALOR DECLARADO, que esta funcao nao recebe: quem
        # escolhe e `caminho_do_ato_do_ri(base_calculo)`, e quem sela passa o
        # `caminho=` pronto para `selar_o_ato_lavrado`.
        #
        # Sem esta guarda o `None` sairia do `.get()` la embaixo com a mesma
        # cara de «a casa nunca selou isto» — e a casa selou 120 vezes.
        return None
    # **O LIVRO 3 E DO REGISTRO DE IMOVEIS, E SELA PELA FAMILIA `imovel`.**
    #
    #   `at_certidoes` serve DUAS atribuicoes — RCPJ/RTD e Livro 3 —, e o
    #   par (tabela, tipo) nao as separa: os dois sao `CERTIDAO`. Ate
    #   21/09/2026 o mapa devolvia o caminho do RTD/PJ para os dois, e o
    #   comentario ao lado dele ja dizia que o Livro 3 e do RI — a regra
    #   estava escrita e nao valia.
    #
    #   **O ESTRAGO ERA DINHEIRO, e nao so o selo**: a receita de custas
    #   sai do CAMINHO, e a ficha do Livro 3 oferecia os itens do grupo
    #   **15** (RTD/PJ) onde a casa cobrou os do **16.24**.
    #
    #   **MEDIDO EM 21/09/2026**: as **9** certidoes do Livro 3 do acervo
    #   (`LivroAuxiliarCertidao`) tem, todas as 9, selo de
    #   `/selo/imovel/certidao` no protocolo geral delas — prefixo
    #   `CERIMV`. A amarracao e pelo PROTOCOLO, e nao pela linha da
    #   certidao (`Selado` esta vazia nas 9), e em duas delas — os
    #   protocolos 2020.06.48 e 2020.07.35 — **nao ha outro caminho
    #   nenhum** no protocolo inteiro.
    #
    #   A ESPECIE AQUI E A ATRIBUICAO, como no civil ela e a especie do
    #   assento: sem ela nao ha como separar os dois livros, e devolver o
    #   caminho errado e pior que devolver None.
    if (tabela == "at_certidoes"
            and str(especie or "").strip().upper() == "LIVRO3"):
        return "/selo/imovel/certidao"
    if tabela == "ri_certidoes":
        # **A CASA USOU ESTE CAMINHO 667 VEZES** — nao ha escolha por
        # semelhanca a fazer: `/selo/imovel/certidao` e o que ela mandou, e o
        # envelope esta medido nos 667.
        return "/selo/imovel/certidao"
    if tabela == "ri_protocolos":
        # A PRENOTACAO E ATO, e tem selo proprio — 829 no acervo. Ela nao mora
        # em `ri_atos`: e anterior a ele, e existe mesmo quando o titulo e
        # devolvido sem registro.
        return "/selo/imovel/prenotacao"
    if tabela in CAMINHO_DAS_NOTAS:
        # Nas Notas o caminho e da TABELA, e nao do tipo: cada tela sela uma
        # coisa so — firma, copia autenticada, cartao de autografo.
        return CAMINHO_DAS_NOTAS[tabela]
    if tabela == "rg_atos":
        # A SERIE (especie) decide PJ vs TD na averbacao. Sem serie, o
        # fallback generico de CAMINHO_DO_ATO ainda serve o REGISTRO.
        return caminho_do_rtdpj(tipo, especie)
    return CAMINHO_DO_ATO.get((tabela, str(tipo or "").strip().upper()))


class AtoError(ValueError):
    """Impedimento de regra, com mensagem pronta para o balcao."""


# ------------------------------------------------------------- as custas


def calcular_custas(con: sqlite3.Connection, *, servico: int,
                    data: Any = None, quantidade: int = 1,
                    base: Any = None,
                    gratuidade_codigo: str | None = None,
                    motivo_gratuidade: str | None = None) -> dict:
    """Quanto custa o ato, pela tabela do DIA DELE. So LE.

    E `custas.calcular` com a mensagem de balcao por cima: o erro que sobe
    daqui diz o que fazer, e nao o nome da funcao que falhou.

    A data e a DO ATO, e nao a de hoje: quem relavra ato de marco de 2023 ou
    reimprime recibo de 2024 tem de pagar o que valia naquele dia.
    """
    try:
        conta = CU.calcular(con, servico=servico, data=data,
                            quantidade=max(1, int(quantidade or 1)), base=base,
                            gratuidade_codigo=gratuidade_codigo,
                            motivo_gratuidade=motivo_gratuidade)
    except CU.CustasError as erro:
        raise AtoError(str(erro)) from erro
    return conta


def servico_do_codigo_tj(con: sqlite3.Connection, codigo_tj: str) -> dict | None:
    """O serviço da tabela do Tribunal, pelo código `16.1`, `17.2`. Só LÊ.

    É a ponte entre o que a casa cobrou (medido em `ITENS_DE_CUSTA_POR_CAMINHO`)
    e o preço (que mora em `cx_servicos`). Conferida contra o banco de
    produção: os 64 códigos medidos resolvem, sem falta nenhuma.
    """
    linha = banco(con).um(
        """SELECT codigo, codigo_tj, descricao FROM cx_servicos
            WHERE codigo_tj = %s ORDER BY codigo LIMIT 1""",
        (str(codigo_tj or "").strip(),))
    return dict(linha) if linha else None


def receita_de_custas(con: sqlite3.Connection, caminho: str, *,
                      data: Any = None) -> dict:
    """O que a casa cobra naquele ato, com o preço de cada item. Só LÊ.

    `caminho` é o endpoint do selador, que é como o ato se identifica —
    `/selo/protesto/pagamento`, `/selo/imovel/prenotacao`. De
    `atribuicoes.ITENS_DE_CUSTA_POR_CAMINHO` saem os itens da tabela do
    Tribunal que a casa cobrou naquele ato, medidos em 24.849 selos reais; de
    `cx_servicos` sai o preço de cada um.

    NÃO É ORÇAMENTO FECHADO, e a tela tem de dizer isso. É o que a casa cobrou
    ANTES, em ordem de frequência — item de um uso em oitocentos é exceção, e
    quem lavra decide o que cabe neste ato. Devolver isto como total a pagar
    faria o balcão cobrar pela média em vez de pelo caso.

    Item que não resolve em `cx_servicos`, ou cujo preço a tabela do dia não
    tem, entra com `preco=None` e o motivo — e não some da lista. Sumir seria
    cobrar a menos sem ninguém ver.
    """
    itens = []
    total = 0
    for codigo_tj, vezes in ATR.itens_de_custa_do_ato(caminho).items():
        item: dict[str, Any] = {"codigo_tj": codigo_tj, "vezes": vezes,
                                "preco": None, "motivo": None}
        servico = servico_do_codigo_tj(con, codigo_tj)
        if not servico:
            item["motivo"] = "não está na tabela de emolumentos importada"
            itens.append(item)
            continue
        item["servico"] = servico["codigo"]
        item["descricao"] = servico["descricao"]
        try:
            conta = calcular_custas(con, servico=servico["codigo"], data=data)
        except AtoError as erro:
            item["motivo"] = str(erro)
            itens.append(item)
            continue
        preco = conta["total_devido_centavos"]
        # ITEM DE CABECALHO NAO E ITEM DE GRACA.
        #
        # Na tabela do Tribunal ha linhas que terminam em "os emolumentos
        # serao de:" e valem 0,00 — o preco de verdade esta nos SUBITENS, por
        # faixa de valor do titulo. O 17.4 e assim, com subitens de 17.4.3 a
        # 17.4.25.
        #
        # Mostrar "R$ 0,00" ali sem dizer o que e faria o balcao cobrar zero
        # por um ato que custa. Sao 151 dos 1.317 servicos com total zerado.
        if preco == 0 and not conta.get("gratuito"):
            subitens = int(banco(con).valor(
                "SELECT count(*) AS n FROM cx_servicos WHERE codigo_tj ILIKE %s",
                (f"{codigo_tj}.%",)))
            if subitens:
                item["por_faixa"] = True
                item["subitens"] = subitens
                item["motivo"] = (
                    f"item de faixa: o preço depende do valor do título e está "
                    f"em {subitens} subitem(ns) de {codigo_tj}")
                itens.append(item)
                continue
        item["preco"] = preco
        item["gratuito"] = bool(conta.get("gratuito"))
        total += preco
        itens.append(item)
    return {"caminho": caminho, "itens": itens, "total_centavos": total,
            "medido_em": "24.849 selos reais",
            "por_faixa": [i["codigo_tj"] for i in itens if i.get("por_faixa")],
            "sem_preco": [i["codigo_tj"] for i in itens
                          if i["preco"] is None and not i.get("por_faixa")]}


def cobrar(con: sqlite3.Connection, *, tabela: str, ato_id: int,
           servico: int, agora: str, hoje: str, hora: str,
           caixa_id: int | None = None, protocolo_id: int | None = None,
           pagador: str | None = None, pagador_documento: str | None = None,
           forma_pagamento: str | None = None, descricao: str | None = None,
           quantidade: int = 1, base: Any = None, data_do_ato: Any = None,
           gratuidade_codigo: str | None = None,
           motivo_gratuidade: str | None = None, selo: str | None = None,
           usuario_id: int | None = None) -> dict:
    """Calcula e LANÇA no caixa o que o ato custou. ESCREVE.

    Fecha o ciclo do dinheiro: até aqui o ato era lavrado e o preço mostrado,
    mas nada era cobrado — e cartório que lavra sem lançar é cartório que não
    fecha o caixa.

    A CONTA SAI DA TABELA DO DIA DO ATO, e não da de hoje: quem relavra ato de
    2023 paga o que valia naquele dia. Por isso `data_do_ato`.

    ATO GRATUITO LANÇA COM ZERO, E NÃO DEIXA DE LANÇAR. O valor que TERIA é o
    que a serventia compensa junto ao fundo, e um ato gratuito que não aparece
    no caixa é compensação que ninguém pede. `custas.calcular` já devolve os
    dois números; aqui os dois vão para a linha.

    Devolve a conta e o `lancamento_id`.
    """
    if tabela not in TABELAS_DE_ATO:
        raise AtoError(
            f"{tabela!r} não é tabela de ato. As que são: "
            f"{', '.join(sorted(TABELAS_DE_ATO))}.")
    conta = calcular_custas(con, servico=servico, data=data_do_ato,
                            quantidade=quantidade, base=base,
                            gratuidade_codigo=gratuidade_codigo,
                            motivo_gratuidade=motivo_gratuidade)
    chave = f"{tabela}:{ato_id}:{servico}"
    bd = banco(con)
    ja = bd.um(
        """SELECT id FROM cx_lancamentos
            WHERE origem='ATO' AND origem_chave = %s ORDER BY id LIMIT 1""",
        (chave,))
    if ja:
        # Cobrar duas vezes o mesmo ato e o mesmo item e o erro que o cliente
        # descobre no extrato. O indice unico de (origem, origem_chave) ja
        # impede; aqui a mensagem diz o que houve, em vez de estourar.
        raise AtoError(
            f"O item {servico} deste ato já foi lançado no caixa "
            f"(lançamento {ja['id']}). Cobrar duas vezes o mesmo item é o que "
            f"o cliente descobre no extrato.")

    from caixa_schema import reais
    novo = bd.escrever(
        """INSERT INTO cx_lancamentos(caixa_id, protocolo_id, data, hora,
               natureza, sentido, forma_pagamento, descricao, pagador,
               pagador_documento, valor, emolumentos, ferc, fadep, femp,
               ferrfis, selo, origem, origem_chave, criado_em, criado_por)
           VALUES (%s,%s,%s,%s, 'RECEBIMENTO','ENTRADA',
                   %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                   'ATO', %s, %s, %s)
           RETURNING id""",
        (caixa_id, protocolo_id, hoje, hora, forma_pagamento,
         _texto_ou_none(descricao) or conta.get("descricao"),
         _texto_ou_none(pagador), _texto_ou_none(pagador_documento),
         reais(conta["total_centavos"]),
         reais(conta.get("emolumento_centavos") or 0),
         str(conta.get("ferc") or "0,00"), str(conta.get("fadep") or "0,00"),
         str(conta.get("femp") or "0,00"), str(conta.get("ferrfis") or "0,00"),
         _texto_ou_none(selo), chave, agora, usuario_id))
    lancamento_id = int(novo[0]["id"])
    bd.escrever(f"UPDATE {tabela} SET lancamento_id = %s WHERE id = %s",
                (lancamento_id, int(ato_id)))
    return {"lancamento_id": lancamento_id, "conta": conta,
            "total_centavos": conta["total_centavos"],
            "gratuito": bool(conta.get("gratuito")),
            "total_devido_centavos": conta.get("total_devido_centavos")}


def _texto_ou_none(v: Any) -> str | None:
    s = str(v or "").strip()
    return s or None


def lancamentos_do_ato(con: sqlite3.Connection, tabela: str,
                       ato_id: int) -> list[dict]:
    """O que já foi cobrado por este ato. So LE."""
    return banco(con).ler(
        """SELECT * FROM cx_lancamentos
            WHERE origem='ATO' AND origem_chave ILIKE %s
            ORDER BY id""", (f"{tabela}:{int(ato_id)}:%",))


def selos_do_ato(con: sqlite3.Connection, tabela: str,
                 ato_id: int) -> list[dict]:
    """TODOS os selos deste ato — e não só os dois que `rg_atos` guarda. SÓ LÊ.

    Achado do oficial em 11/09/2026: um ato pode consumir mais de um item da
    tabela de emolumentos (`15.1` e `15.9.1` no mesmo ato, por exemplo), e
    cada item vira o SEU PRÓPRIO selo — mas `rg_atos.selo`/`selo_arquivamento`
    só têm lugar para dois. `sd_selos` é o registro completo: toda chamada a
    `selar_o_ato_lavrado` grava aqui (`vincular_ao_ato`), com `tabela` e
    `ato_id`, antes de qualquer resumo em duas colunas. Quem quiser TODOS os
    selos de um ato — a ficha, o teor, a etiqueta — lê daqui, e não das duas
    colunas.
    """
    return banco(con).ler(
        """SELECT * FROM sd_selos WHERE tabela = %s AND ato_id = %s
            ORDER BY id""", (tabela, int(ato_id)))


# O ACERVO NAO VIRA PENDENCIA, e aqui ele viraria 2.783 vezes.
#
#   **Medido na producao em 30/08/2026**, ao atender o relato #13 do oficial
#   («pendencias antigas e do e-oficio nao devem aparecer»):
#
#   | tabela      | sem selo | do E-Oficio |
#   |-------------|----------|-------------|
#   | `nt_atos`   |      260 |     **258** |
#   | `rc_atos`   |      244 |     **244** |
#   | `pt_atos`   |    2.281 |   **2.281** |
#
#   Sao **dois** atos desta casa em 2.785. O selo dos outros existiu — foi
#   colado como imagem, ou ficou no acervo sem amarracao —, e comprar selo hoje
#   para um ato de 1990 nao e conserto: e inventar.
#
#   **Estas duas funcoes ainda nao tem tela** (estao declaradas em
#   `tests/test_funcao_sem_tela.py`), e e por isso que o defeito nunca chegou
#   ao balcao. Conserta-se agora **para que a tela, quando nascer, nao nasca
#   mentindo** — o contrario e o que aconteceu com o painel, onde a lista foi
#   para a tela com 21.342 protocolos do E-Oficio dentro.
#
#   E o que fica de fora **nao some calado**: as funcoes devolvem tambem
#   quantos foram excluidos, para a tela poder dizer.
MARCA_DO_ACERVO = "EOFICIO"


def _tem_coluna(con: sqlite3.Connection, tabela: str, coluna: str) -> bool:
    """Se aquela coluna existe naquela tabela. So le.

    **SEM O COMANDO DE ESQUEMA DO SQLite, DE PROPOSITO.** Este e modulo de
    dominio, e o teto de acoplamento conta aquele comando fora dos modulos de
    esquema — com razao: ele nao existe em nenhum outro banco.

    (O nome dele nao se escreve nesta frase: o varredor conta a palavra onde
    quer que ela apareca, e ja bateu na prosa de comentarios seis vezes neste
    projeto — duas so hoje.)

    `SELECT ... LIMIT 0` e
    `cursor.description` respondem a mesma pergunta e sao **padrao**: funcionam
    igual no PostgreSQL e no SQL Server.

    Aqui basta saber se a coluna existe — nao preciso do tipo nem de saber se e
    obrigatoria —, e por isso a forma portavel serve inteira. Onde ela nao
    servisse (como em `importar_padrao`, que precisa do «obrigatorio»), a
    divida se declara em vez de se disfarcar.

    Na migracao para o PostgreSQL nativo, a pergunta vai ao
    `information_schema` (via `bd_nativo`).
    """
    return banco(con).tem_coluna(tabela, coluna)


def _so_o_que_esta_casa_lavrou(con: sqlite3.Connection, tabela: str) -> str:
    """A condicao que tira o acervo, quando a tabela sabe distinguir. So le.

    Tabela sem coluna `origem` devolve condicao vazia — e isso e **honesto**:
    ali nao da para separar, e inventar um filtro produziria uma lista que
    esconde ato desta casa.
    """
    if not _tem_coluna(con, tabela, "origem"):
        return ""
    return f" AND COALESCE(origem,'') <> '{MARCA_DO_ACERVO}'"


def quantos_do_acervo_ficaram_de_fora(con: sqlite3.Connection, tabela: str,
                                      onde: str) -> int:
    """Quantos o filtro do acervo tirou daquela lista. So le.

    **O QUE SAI DA LISTA E DITO.** Uma lista que encolhe em silencio faz quem a
    le concluir que o trabalho acabou — e este numero e a frase que impede
    isso.
    """
    if not _so_o_que_esta_casa_lavrou(con, tabela):
        return 0
    return int(banco(con).valor(
        f"""SELECT count(*) AS n FROM {tabela}
             WHERE {onde} AND COALESCE(origem,'') = %s""",
        (MARCA_DO_ACERVO,)))


def atos_sem_cobranca(con: sqlite3.Connection, tabela: str,
                      limite: int = 200) -> list[dict]:
    """Os atos daquela tabela que ninguém cobrou. So LE.

    O par de `atos_sem_selo`, do lado do dinheiro: não basta o ato ter selo,
    ele tem de ter entrado no caixa. Ato lavrado e não cobrado é receita que
    some sem ninguém ver.

    **O ACERVO NAO ENTRA**, pelo mesmo motivo: cobrar hoje por ato de 1990 nao
    e conserto. Ver `atos_sem_selo`.
    """
    if tabela not in TABELAS_DE_ATO:
        raise AtoError(f"{tabela!r} não é tabela de ato.")
    onde = "COALESCE(lancamento_id, 0) = 0"
    return banco(con).ler(
        f"""SELECT * FROM {tabela}
             WHERE {onde}{_so_o_que_esta_casa_lavrou(con, tabela)}
             ORDER BY id DESC LIMIT %s""", (int(limite),))


def conferir_ato(codigo_do_ato: Any) -> dict:
    """O ato do catalogo, ou erro de balcao. So calcula.

    Recusa ato NAO LIBERADO. O acervo marcava dois assim — Apostila de Haia no
    Protesto e Certidao Unificada de Protesto —, e ato nao liberado nao se
    sela: se o Tribunal nao o reconhece, o selo nao sai.
    """
    try:
        codigo = int(codigo_do_ato)
    except (TypeError, ValueError):
        raise AtoError(f"Código de ato inválido: {codigo_do_ato!r}.") from None
    ato = ATR.ATOS.get(codigo)
    if not ato:
        raise AtoError(
            f"O ato {codigo} não está no catálogo do Tribunal. Os códigos "
            f"vêm de `atribuicoes.ATOS`, gerados do acervo.")
    if not ato.get("liberado"):
        raise AtoError(
            f"O ato {codigo} ({ato['nome']}) não está liberado pelo Tribunal "
            f"e por isso não pode ser selado.")
    return {"codigo": codigo, **ato}


# -------------------------------------------------- o selo obtido a mao



def _ambiente_do_selo(con) -> str:
    """Rotulo gravado em sd_selos.ambiente — vem da config, sem valor fixo.

    No sandbox a config diz SIMULADO/SANDBOX; na producao, PRODUCAO.

    A REGRA E A DO SELO AUTOMATICO: `selador_cliente.selar` grava o
    `ambiente` de `SC.situacao`, que e o da linha de `sd_config` — ou
    PRODUCAO, sem linha. Os dois caminhos do razao tem de dizer o mesmo.

    CHAMAVA `SC.estado`, QUE NAO EXISTE (achado da IA do servidor no ensaio
    de 21/10/2026). O `except Exception` engolia o AttributeError e o selo a
    mao saia sempre PRODUCAO — tambem no selador em homologacao, que e
    justamente quando o rotulo importa. Por isso nao ha mais `except`: so a
    falta de configuracao cai no padrao, e com log; erro de programacao
    sobe.
    """
    import selador_config as SC
    linha = SC._linha(con)
    if not linha:
        _LOG.warning("Selador sem configuracao (sd_config vazia): o selo "
                     "digitado a mao fica marcado PRODUCAO.")
        return "PRODUCAO"
    amb = str(linha.get("ambiente") or "").strip().upper()
    return amb or "PRODUCAO"


def _dados_do_selo_a_mao(texto: Any) -> dict:
    """O «envelope» que o selo digitado permite montar. Só calcula.

    O selo tirado no portal não tem envelope; o que ele tem é o TEXTO que o
    aparelho imprimiu — e é dele que saem as duas coisas que a cobertura lê:
    a marca «Selo Isento» (`selo_e_gratuito`: a gratuidade NÃO trava, regra do
    oficial de 19/10/2026) e o item da tabela (`codigoAto`, que escolhe o item
    do protocolo). Sem texto, o selo é tratado como pago.
    """
    lido = SELO.ler_texto(texto) if str(texto or "").strip() else {}
    dados: dict = {}
    if any(str(m).strip().lower() == "selo isento"
           for m in (lido.get("marcas") or [])):
        dados["isento"] = True
    if lido.get("ato"):
        dados["codigoAto"] = str(lido["ato"])
    return dados


def registrar_selo_obtido_a_mao(con: sqlite3.Connection, numero: Any, *,
                                tabela: str, ato_id: int, atribuicao: Any,
                                agora: str, cns: Any,
                                usuario: str | None = None,
                                texto: str | None = None) -> dict:
    """Grava no razao o selo que o escrevente tirou no portal. ESCREVE.

    E o caminho normal do Protesto e do RCPN nesta casa — ver o cabecalho.
    Escreve em `sd_selos` JA VINCULADO ao ato, porque aqui o ato existe antes
    do selo, ao contrario do selo automatico.

    O que o sistema acrescenta ao que o E-Oficio fazia:

      - o codigo e LIDO (`selo.ler_codigo`), entao erro de digitacao aparece
        na hora e nao na conferencia da inspecao;
      - o CNS e conferido contra o da serventia: selo de outro cartorio
        digitado por engano e recusado;
      - o selo repetido e recusado — `numero` e UNIQUE em `sd_selos`, e a
        mensagem diz em qual ato ele ja esta.

    O MESMO SELO NO MESMO ATO NAO E RECUSA (LD14, 21/10/2026): e o
    formulario enviado duas vezes. Nao duplica e fica registrado
    («SELO_REPETIDO»). Em OUTRO ato — ou cancelado — e recusa, com a
    auditoria «SELO_REPETIDO_RECUSADO» gravada por fora, porque a recusa
    desfaz a transacao de quem chama. Ver `selador_cliente.conferir_o_repetido`.

    O RAZAO E CONFERIDO PELO PROPRIO INSERT, e nao antes dele. O `SELECT`
    antes e o `INSERT` depois deixavam dois balcoes digitando o mesmo selo
    passarem os dois pelo «ainda nao existe» — e o segundo estourava o
    UNIQUE em HTTP 500, em vez de ouvir onde o selo ja estava. O
    `ON CONFLICT (numero)` decide sob a trava da propria chave.
    """
    if tabela not in TABELAS_DE_ATO:
        raise AtoError(
            f"{tabela!r} não é tabela de ato. As que são: "
            f"{', '.join(sorted(TABELAS_DE_ATO))}.")
    bruto = str(numero or "").strip().upper()
    if not bruto:
        raise AtoError("Informe o número do selo.")
    try:
        codigo = SELO.ler_codigo(bruto)
    except SELO.SeloError as erro:
        raise AtoError(str(erro)) from erro
    if cns and not SELO.do_nosso_cns(bruto, cns):
        raise AtoError(
            f"O selo {bruto} não é desta serventia: o CNS dele não é o "
            f"{cns}. Confira se o código foi copiado do selo certo.")
    if NOMEHUM.eh_rotulo_de_maquina(usuario):
        # a mesma regra de `obter_selo` (22/10/2026, A6): máquina não assina
        raise AtoError(
            f"O selo não entra em nome de máquina ({usuario}): um escrevente "
            "digita o selo na tela do ato.")

    import selador_cliente as CL
    bd = banco(con)
    # O SELO À MÃO PASSA PELA MESMA COBERTURA DO SELO AUTOMÁTICO (revisão de
    # segurança da 3.7.0, 22/10/2026, achado A9). Até aqui a trava do selo
    # pago vivia só em `obter_selo`: digitar o número de um selo tirado no
    # portal gravava o ato como selado sem protocolo, sem pagamento e sem
    # liberação — a porta ao lado da trava. Agora `cobrir_o_selo` decide com
    # a MESMA régua (gratuito pelo texto do selo, trava desligada, item ligado
    # ou quitado, lançamento, protocolo em atendimento, liberação do ADMIN) e,
    # como o selo já saiu do aparelho, a reserva é CONFIRMADA na mesma
    # transação, logo abaixo. Sem cobertura sobe `SeloSemCobertura`: a tela
    # mostra o quadro, e a transação de quem chama volta — nada fica gravado.
    # Banco sem o esquema da trava (teste de unidade montado à mão) sai pela
    # régua de antes, como `_gravar_cobertura` já fazia.
    cobertura: dict = {}
    if bd.tem_tabela("cx_selo_coberturas"):
        cobertura = cobrir_o_selo(
            con, tabela=tabela, ato_id=int(ato_id),
            referencia=f"{tabela}:{ato_id}", dados=_dados_do_selo_a_mao(texto),
            usuario=usuario, agora=agora, cns=cns, atribuicao=atribuicao)
        if not cobertura.get("coberto"):
            quadro = cobertura.get("quadro") or {}
            raise SeloSemCobertura(recado_da_cobertura(quadro), quadro)
    novo = bd.escrever(
        """INSERT INTO sd_selos(numero, texto, sid, caminho, atribuicao,
               referencia, tabela, ato_id, ambiente, obtido_em, obtido_por,
               usado_em)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (numero) DO NOTHING RETURNING id""",
        (bruto, texto, None, None, str(atribuicao),
         f"{tabela}:{ato_id}", tabela, int(ato_id), _ambiente_do_selo(con), agora,
         usuario, agora))
    if not novo:
        try:
            # O dono do selo digitado e o ATO; cancelado nao volta a valer.
            CL.conferir_o_repetido(
                bd, bruto, origem=CL.A_MAO,
                iguais={"tabela": tabela, "ato_id": int(ato_id),
                        "cancelado_em": None},
                chegou={"atribuicao": str(atribuicao), "texto": texto},
                agora=agora, usuario=usuario)
        except CL.SeloJaGravado as erro:
            raise AtoError(str(erro)) from erro
    # O selo já está no razão: a reserva da cobertura vira cobertura de
    # verdade, na mesma transação (22/10/2026).
    if cobertura.get("reserva"):
        _confirmar_reserva(con, cobertura.get("reserva"), agora=agora)
    assinar_o_que_ficou_pendente(con, tabela=tabela, ato_id=ato_id, quem=usuario)
    # A COLUNA DO SELO NAO SE CHAMA `selo` EM TODA TABELA DE ATO, e esta linha
    # supunha que sim. Achado em 15/09/2026, ao ligar «Selar este ato» do RI —
    # a primeira tela a chamar esta funcao com `ri_atos`:
    #
    #     sqlite3.OperationalError: no such column: selo
    #
    #   Medido: `ri_atos` e `ri_certidoes` guardam em `selo_texto`,
    #   `nt_cartoes` em `selo_abertura` e `ri_protocolos` em
    #   `selo_prenotacao` — e `COLUNA_DO_SELO`, neste mesmo arquivo, existe
    #   justamente por isso: `vincular_ao_ato` ja a consultava desde 27/08.
    #   **Era a metade do ciclo que nao a usava.**
    #
    #   O DEFEITO ERA LATENTE porque esta funcao nao tinha chamador: o
    #   CLAUDE.md registra, em 01/09, que a tela do reconhecimento de firma
    #   grava a coluna direto e «`registrar_selo_obtido_a_mao` nao e chamado».
    #   Peca pronta que ninguem usa tambem esconde defeito — nao so a arma que
    #   alguem religa depois.
    #
    #   E O ESTRAGO SERIA CARO: o selo entra em `sd_selos` na linha de cima, e
    #   a excecao aqui derrubaria a transacao inteira — o escrevente digitaria
    #   a etiqueta do selo que ja pagou e levaria um HTTP 500, com o ato
    #   continuando sem selo e sem nada no razao.
    bd.escrever(f"UPDATE {tabela} SET {COLUNA_DO_SELO.get(tabela, 'selo')} = %s "
                f"WHERE id = %s", (bruto, int(ato_id)))
    return {"numero": bruto, "prefixo": codigo.prefixo,
            "descricao": SELO.PREFIXOS.get(codigo.prefixo, ""),
            "tabela": tabela, "ato_id": int(ato_id)}


# --------------------------------------------- o selo pedido ao aparelho


def obter_selo(db, pasta_de_dados: Any, *, caminho: str, dados: dict,
               referencia: Any, atribuicao: str, agora: str, cns: Any,
               usuario: str | None = None, tabela: str | None = None,
               ato_id: Any = None) -> list:
    """Pede o selo ao aparelho da rede local. ESCREVE, em transacao PROPRIA.

    Recebe `db` e nao `con` DE PROPOSITO: a chamada tem prazo de 20 segundos e
    nao pode acontecer dentro do `BEGIN IMMEDIATE` do ato — seguraria a trava
    de escrita da casa inteira. Ver o cabecalho do modulo.

    Serve as CINCO atribuicoes: `atribuicoes.caminhos_da_atribuicao()` diz
    quais caminhos esta casa ja usou em cada uma, com quantos selos sairam por
    cada um — e todos eles estao no contrato de `selador.py`.

    E A TRAVA DO SELO PAGO MORA AQUI (LX16, 19/10/2026), antes do aparelho:
    sem protocolo e sem pagamento, o selo nao e pedido e sobe
    `SeloSemCobertura` com o quadro do que falta. Ver `cobrir_o_selo`.

    EM TRES PASSOS, E O APARELHO FICA NO DO MEIO, SEM NADA PRESO (LX21a,
    20/10/2026). A primeira versao cobria e pedia na MESMA transacao, para o
    debito voltar sozinho se o aparelho recusasse — e por isso segurava o
    deposito, o item e a trava unica da ponte durante os 20 segundos da
    rede: um aparelho lento parava o balcao inteiro.
        a) numa transacao curta, RESERVA a cobertura (`cobrir_o_selo`: o
           debito e a unidade ja saem do saldo, e a linha da cobertura fica
           «RESERVADA») e confirma — o outro balcao ja le o saldo de depois;
        b) pede o selo numa conexao SEM transacao aberta;
        c) na mesma conexao, CONFIRMA a reserva junto com o selo no razao, ou
           a ESTORNA se o aparelho falhou ou nao deu numero.
    A reserva que a queda deixou no meio e conferida por
    `estornar_reservas_orfas`, aqui mesmo e na subida.
    """
    import selador_cliente as CL  # importado aqui: so quem sela paga
    # SEGUNDA TRANCA: mesmo que `usuario_nome` falhe, o escrevente do envelope
    # e o `obtido_por` NAO podem ser robo. Achado 21/09/2026 (REGNAS...KM25).
    humano = NOMEHUM.nome_humano_para_ato(
        usuario, *NOMEHUM.fallbacks_da_casa(db))
    if not humano:
        raise AtoError(
            "Nao ha escrevente humano para o selo: a sessao parece robo/maquina "
            "e a substituta/oficial nao esta cadastrada. Faca login com um "
            "usuario da serventia antes de selar.")
    if NOMEHUM.eh_rotulo_de_maquina(usuario):
        # MÁQUINA NÃO ASSINA, E NINGUÉM ASSINA POR ELA (revisão de segurança
        # de 22/10/2026, A6). Até aqui o nome do robô era trocado pelo da
        # substituta — que não praticou o ato. O robô deixa o ato pendente
        # de selo; quem clica «Selar» é quem assina (`selo_robo`).
        raise AtoError(
            f"O selo não sai em nome de máquina ({usuario}). O ato fica "
            "pendente de selo: um escrevente abre o ato e clica em Selar.")
    dados = dict(dados or {})
    if NOMEHUM.eh_rotulo_de_maquina(dados.get("escrevente")):
        dados["escrevente"] = humano
    # UMA GRAFIA SÓ, DAQUI EM DIANTE (LX24): a cobertura, o SID do aparelho e
    # o razão usam a mesma referência — senão ` PT_ATOS : 1 ` e `pt_atos:1`
    # pagavam o selo do mesmo ato duas vezes. A grafia RECEBIDA fica guardada
    # (LX25): o que já está gravado com ela — cobertura e selo de antes do
    # LX24 — continua sendo achado, e não pago de novo.
    recebida = referencia
    referencia = referencia_do_selo(referencia, tabela, ato_id)
    if tabela is None or ato_id is None:
        tabela, ato_id = ato_da_referencia(referencia)
    _conferir_as_orfas(db, agora=agora)
    try:
        with db.transaction() as con:
            cobertura = cobrir_o_selo(con, tabela=tabela, ato_id=ato_id,
                                      referencia=recebida, dados=dados,
                                      usuario=usuario, agora=agora, cns=cns,
                                      atribuicao=atribuicao)
            # SEM COBERTURA, A TRANSACAO VOLTA (LX20, revisao do LX16): o
            # selo nao vai ser pedido, entao nada do que a cobertura tentou —
            # debito, quitacao, unidade — pode ficar.
            if not cobertura["coberto"]:
                raise _NaoCoberto(cobertura)
    except _NaoCoberto as falta:
        cobertura = falta.cobertura
    if cobertura["coberto"]:
        reserva = cobertura.get("reserva")
        # `connect`, e nao `transaction`: esta abre ja com a trava unica da
        # ponte, e o aparelho tem 20 segundos de prazo. O `with` confirma o
        # selo no razao e a reserva juntos, ou desfaz os dois.
        with db.connect() as con:
            try:
                # O SID DO ATO QUE JÁ TEM SELO É O GRAVADO (LX25): o selo de
                # antes do LX24 está no SID da grafia crua, e pedir pela
                # canônica seria outro SID — o aparelho venderia o segundo
                # selo do mesmo ato.
                do_sid = _selo_ja_obtido(
                    banco(con), cns=cns, atribuicao=atribuicao,
                    referencias=grafias_da_referencia(recebida, tabela, ato_id))
                selos = CL.selar(con, pasta_de_dados, caminho, dados,
                                 referencia=do_sid or referencia,
                                 atribuicao=atribuicao,
                                 agora=agora, cns=cns, usuario=usuario)
            except Exception:
                con.rollback()
                _estornar_sem_estourar(con, reserva, agora=agora,
                                       motivo="o selador falhou ou recusou")
                raise
            if selos:
                _confirmar_reserva(con, reserva, agora=agora)
            else:
                _estornar_reserva(con, reserva, agora=agora,
                                  motivo="o selador respondeu sem selo")
            _tirar_aguardando(con, tabela=tabela, ato_id=ato_id)
            if selos:
                assinar_o_que_ficou_pendente(con, tabela=tabela, ato_id=ato_id,
                                             quem=usuario)
        return selos
    # SEM COBERTURA: o ato fica «aguardando cobertura», com o motivo, numa
    # transacao propria — a de cima voltou atras.
    recado = recado_da_cobertura(cobertura.get("quadro") or {})
    with db.transaction() as con:
        _marcar_aguardando(con, tabela=tabela, ato_id=ato_id, motivo=recado,
                           usuario=usuario, agora=agora)
    raise SeloSemCobertura(recado, cobertura.get("quadro"))



def selar_o_ato_lavrado(db, pasta_de_dados: Any, *, tabela: str, ato_id: int,
                        tipo: str, atribuicao: str, agora: str, cns: Any,
                        dados: dict | None = None, referencia: Any = None,
                        usuario: str | None = None,
                        especie: Any = None,
                        caminho: Any = None) -> dict:
    """O SELO SAI QUANDO O ATO E PRATICADO — decisao do oficial em 27/08/2026.

        «O selo deve ser emitido quando praticado o ato. Igual o E-Ofício.»

    E e o que o E-Oficio fazia: 26.123 selos em 34 caminhos, sem perguntar a
    ninguem. Ate aqui este sistema tinha o caminho do selo automatico pronto e
    testado — `obter_selo` — e NENHUMA TELA O CHAMAVA. A unica forma de selar
    era o escrevente digitar o numero a mao.

    > E a quinta vez neste projeto que a mesma pergunta acha o mesmo defeito:
    > funcao de dominio pronta que tela nenhuma chama. O apontamento do
    > Protesto, a remessa da CRA, as telas do nucleo, o `montar_retorno()` — e
    > agora o selo.

    DEPOIS DO ATO, E NAO ANTES, e isso muda uma regra da casa
        O payload do selo leva livro, folha e numero de ordem: eles so existem
        depois de o ato ser lavrado. Entao a ordem aqui e ato -> selo ->
        vinculo, e a consequencia tem de ser dita: **selo recusado nao derruba
        mais o lancamento**, porque quando a recusa chega o ato ja esta
        gravado.

        Isso NAO afrouxa a regra do selo digitado a mao — aquele continua sendo
        conferido dentro da transacao do ato, e continua derrubando tudo se nao
        prestar. O que muda e so o caminho automatico, onde derrubar seria
        impossivel.

        E e o que a casa ja escolhia quando o balcao pesava mais: **ato sem
        selo entra e aparece em `atos_sem_selo`** — melhor que balcao parado, e
        melhor que ato com selo inventado.

    NUNCA ESTOURA
        O aparelho e maquina de rede local e cai; a internet do forum cai; o
        certificado vence. Nada disso pode derrubar um ato que ja existe. Toda
        falha volta como `{"selado": False, "motivo": ...}`, para a tela dizer
        ao escrevente o que aconteceu — e o ato segue vivo, sem selo, onde a
        tela de pendencia o mostra.

    A REFERENCIA E O ATO, e nao a hora
        `referencia` e o que vira SID no selador, e o SID e o que faz o
        aparelho devolver o selo que ja existe em vez de vender outro. Por isso
        ela e `tabela:ato_id` — estavel entre tentativas do MESMO ato. Foi a
        falta disso que deixou 1.304 selos orfaos no E-Oficio.
    """
    caminho = str(caminho or "").strip() or caminho_do_ato(tabela, tipo, especie)
    if not caminho:
        # NAO E FALHA: e a casa nunca ter selado esse ato por caminho nenhum.
        # Inventar um caminho aqui seria selar por onde ninguem selou.
        return {"selado": False, "caminho": None,
                "motivo": (f"Não há caminho de selo medido para "
                           f"{tipo.lower()} nesta atribuição — o ato ficou sem "
                           f"selo, e aparece na lista de atos sem selo.")}
    try:
        selos = obter_selo(db, pasta_de_dados, caminho=caminho,
                           dados=dict(dados or {}),
                           referencia=referencia or f"{tabela}:{int(ato_id)}",
                           atribuicao=atribuicao, agora=agora, cns=cns,
                           usuario=usuario, tabela=tabela, ato_id=ato_id)
    except SeloSemCobertura as falta:
        # NAO E FALHA DO APARELHO: o selo nem foi pedido. O quadro vai junto
        # para a tela mostrar os botoes; o recado e a mesma frase para o
        # robo e para o selo automatico.
        return {"selado": False, "caminho": caminho, "motivo": str(falta),
                "aguardando_cobertura": True, "quadro": falta.quadro}
    except Exception as erro:                                  # noqa: BLE001
        return {"selado": False, "caminho": caminho, "motivo": str(erro)}

    numeros = []
    try:
        with db.transaction() as con:
            for selo in selos:
                # `selador.SeloGerado.numero` — o campo tem nome, e supor um
                # segundo nome "por via das duvidas" seria esconder o dia em
                # que o contrato mudasse.
                numero = selo.numero
                if not numero:
                    continue
                vincular_ao_ato(con, numero, tabela=tabela, ato_id=ato_id,
                                agora=agora)
                numeros.append(str(numero))
    except Exception as erro:                                  # noqa: BLE001
        # O SELO JA EXISTE E JA ESTA NO RAZAO — o que falhou foi amarra-lo ao
        # ato. Ele aparece como "selo obtido e nao usado", que e exatamente a
        # tela que existe para este caso.
        return {"selado": False, "caminho": caminho, "numeros": [],
                "motivo": (f"O selo saiu, mas não consegui amarrá-lo ao ato "
                           f"({erro}). Ele está na lista de selo obtido e não "
                           f"usado.")}
    if not numeros:
        return {"selado": False, "caminho": caminho,
                "motivo": "O selador respondeu sem número de selo."}
    # O QUE O APARELHO DEVOLVEU A MAIS (o código de validação — 23/10/2026)
    # vai junto, do primeiro selo: a tela da CRC o mostra para copiar.
    extras = dict(getattr(selos[0], "extras", ()) or ()) if selos else {}
    return {"selado": True, "caminho": caminho, "numeros": numeros,
            "numero": numeros[0], "extras": extras}


# ONDE O NUMERO DO SELO MORA EM CADA TABELA DE ATO — medido no banco vivo em
# 27/08/2026, coluna por coluna, e NAO suposto.
#
#   Nove tabelas tem `selo`, e duas nao: `nt_cartoes` guarda em `selo_abertura`
#   e `ri_atos` em `selo_texto` (que as vezes leva a data e o item junto, como
#   `REGAVD000000… 18/08/2026 13:40:27, Ato: 16.3`).
#
#   Supor `selo` para todas fazia a amarracao estourar nessas duas — e estourar
#   DEPOIS de o selo ter sido comprado, que e o pior momento possivel: o selo
#   existe, foi pago, e nao esta em ato nenhum. Foi assim que o E-Oficio
#   acumulou 1.304 orfaos.
COLUNA_DO_SELO: dict[str, str] = {
    "hc_habilitacoes": "selo",
    "nt_cartoes": "selo_abertura",
    "ri_atos": "selo_texto",
    "ri_protocolos": "selo_prenotacao",
    # A ABERTURA DA MATRICULA GUARDA O SELO NA PROPRIA FICHA — 16/09/2026,
    # pedido do oficial: «como emito e coloco o selo de abertura de matricula
    # nessa 4016».
    #
    #   Medido antes de escrever: `ri_matriculas.selo_abertura_texto` existe
    #   desde sempre e esta preenchida em **ZERO das 1.982** fichas. A unica
    #   linha que a escrevia e o INSERT de matricula nova, lendo um campo de
    #   formulario que **nenhuma tela oferece** — a coluna era lida para o
    #   `.odt` da ficha e nunca escrita por ninguem.
    #
    #   E O `ato_id` AQUI E O `id` DA MATRICULA. A chave de `sd_selos` e
    #   `tabela` + `ato_id`, e por isso nao ha colisao com `ri_atos`: e a
    #   mesma razao pela qual os tres selos de firma de 2022 nao se
    #   confundiram com os atos 3728-3730 da 3.110.
    "ri_matriculas": "selo_abertura_texto",
    # medido no esquema: `ri_certidoes` guarda em `selo_texto`,
    # como `ri_atos` — e nao em `selo`.
    "ri_certidoes": "selo_texto",
    # A certidao das Notas (15/10/2026) guarda em `selo`, e fica escrito
    # para ninguem precisar abrir o esquema para saber.
    "nt_certidoes": "selo",
}


def vincular_ao_ato(con: sqlite3.Connection, numero: Any, *, tabela: str,
                    ato_id: int, agora: Any) -> None:
    """Amarra ao ato o selo que ja esta no razao. ESCREVE.

    Chamada DENTRO da transacao do ato, depois de ele existir. Antes disto o
    selo esta em `sd_selos` sem `tabela` nem `ato_id`, e e assim que ele
    aparece na tela de selo obtido e nao usado se o ato falhar.

    `agora` E OBRIGATORIO, e faltava: `selador_cliente.vincular` grava
    `usado_em`, e sem essa hora o selo nao se distingue de um selo que nunca
    foi usado. Ate 27/08/2026 esta funcao nao o passava, e a chamada estourava
    com `missing 1 required keyword-only argument` — **depois** de o selo ter
    sido comprado. O balcao viu: «O selo saiu, mas nao consegui amarra-lo ao
    ato».

    UM RELOGIO SO. `agora` vem de quem chama, que e quem ja carimbou o ato —
    ler a hora aqui faria o selo e o ato discordarem por um segundo.
    """
    if tabela not in TABELAS_DE_ATO:
        raise AtoError(f"{tabela!r} não é tabela de ato.")
    import selador_cliente as CL
    CL.vincular(con, str(numero), tabela=tabela, ato_id=int(ato_id),
                agora=str(agora))
    coluna = COLUNA_DO_SELO.get(tabela, "selo")
    banco(con).escrever(f"UPDATE {tabela} SET {coluna} = %s WHERE id = %s",
                        (str(numero), int(ato_id)))
    assinar_o_que_ficou_pendente(
        con, tabela=tabela, ato_id=ato_id,
        quem=banco(con).valor("SELECT obtido_por FROM sd_selos WHERE numero = %s",
                              (str(numero),)))


def assinar_o_que_ficou_pendente(con: Any, *, tabela: Any, ato_id: Any,
                                 quem: Any) -> list[str]:
    """Quem selou assina o que a máquina deixou pendente. ESCREVE.

    23/10/2026, ordem do oficial («solução 1»). Ato lavrado em sessão de robô
    guarda `nome_humano.MARCA_PENDENTE` onde iria o nome de quem o praticou.
    O selo não sai em nome de máquina (`obter_selo` e
    `registrar_selo_obtido_a_mao` recusam), então quem o obteve é gente — e
    é esse nome que entra no lugar da marca. São TRÊS as portas por onde um
    selo encontra o ato, e as três chamam aqui: o selo do aparelho
    (`obter_selo`), o digitado (`registrar_selo_obtido_a_mao`) e o amarrado
    depois (`vincular_ao_ato`, que lê `sd_selos.obtido_por`).

    SÓ A COLUNA QUE É EXATAMENTE A MARCA. Teor que a traz no meio do texto
    NÃO se reescreve: no RI ele está na corrente de hash, e ato lavrado não
    se edita. Ali a marca fica, e o carimbo do selo, ao lado, diz quem selou.

    Devolve as colunas trocadas (vazio quando não havia o que assinar).
    """
    quem = NOMEHUM.nome_humano_para_ato(quem)
    if not quem or tabela not in TABELAS_DE_ATO or ato_id in (None, ""):
        return []
    bd = banco(con)
    colunas = [l["column_name"] for l in bd.ler(
        """SELECT column_name FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = %s
              AND data_type IN ('text', 'character varying')""", (tabela,))]
    linha = bd.um(f"SELECT * FROM {tabela} WHERE id = %s", (int(ato_id),)) or {}
    trocadas = [c for c in colunas if linha.get(c) == NOMEHUM.MARCA_PENDENTE]
    for c in trocadas:
        bd.escrever(f"UPDATE {tabela} SET {c} = %s WHERE id = %s AND {c} = %s",
                    (quem, int(ato_id), NOMEHUM.MARCA_PENDENTE))
    return trocadas


# ------------------------------------------------------------ conferencia


# `selos_do_ato` MORAVA AQUI UMA SEGUNDA VEZ, e a segunda era a que valia —
# apagada em 21/09/2026. As duas liam a mesma coisa; o que mudava era a ordem
# (`obtido_em` contra `id`), e `obtido_em` tem DOIS formatos nesta casa:
# `2020-03-19 14:21:03` na carga do acervo e `2026-09-01T14:17:06` neste
# sistema. Ficou a documentada, que ordena por `id` — a ordem em que os selos
# entraram, que nao depende de formato de data.


def atos_sem_selo(con: sqlite3.Connection, tabela: str,
                  limite: int = 200) -> list[dict]:
    """Os atos daquela tabela que ainda nao tem selo. So LE.

    E a tela que a inspecao pede do outro lado: nao basta o selo ter ato, o
    ato tem de ter selo. Os cinco atos de 18/08/2026 estao todos aqui, porque
    o selo foi colado como imagem e nunca entrou no banco.

    **O ACERVO NAO ENTRA** — relato #13, 30/08/2026. Eram **2.783** atos do
    E-Oficio contra **2** desta casa; ver `MARCA_DO_ACERVO`. Quantos ficaram de
    fora se pergunta a `quantos_do_acervo_ficaram_de_fora`, e a tela diz.
    """
    if tabela not in TABELAS_DE_ATO:
        raise AtoError(f"{tabela!r} não é tabela de ato.")
    # **A COLUNA DO SELO NAO SE CHAMA `selo` EM TODA TABELA, e esta funcao
    # supunha que sim — defeito achado em 14/09/2026, ao ligar o selo
    # automatico do ato do RI.**
    #
    #   Medido: ela QUEBRAVA com `no such column: selo` em **quatro das cinco**
    #   tabelas de ato — `ri_atos` (selo_texto), `ri_certidoes` (selo_texto),
    #   `ri_protocolos` (selo_prenotacao) e `nt_cartoes` (selo_abertura). So
    #   `rc_atos` respondia.
    #
    #   E ESTA E A MESMA LICAO QUE `vincular_ao_ato` JA TINHA APRENDIDO — o
    #   `COLUNA_DO_SELO` nasceu justamente disto, do outro lado do ciclo: la,
    #   para GRAVAR o numero; aqui, para PERGUNTAR quem esta sem. Uma regua
    #   aprendeu e a irma nao, e foi assim que a tela ficou cega para as quatro
    #   tabelas sobre as quais este projeto mais escreveu «o ato sem selo
    #   aparece em `atos_sem_selo`».
    coluna = COLUNA_DO_SELO.get(tabela, "selo")
    onde = f"COALESCE({coluna},'') = ''"
    return banco(con).ler(
        f"""SELECT * FROM {tabela}
             WHERE {onde}{_so_o_que_esta_casa_lavrou(con, tabela)}
             ORDER BY id DESC LIMIT %s""", (int(limite),))


def etiquetas_do_ato(con: sqlite3.Connection, tabela: Any, ato_id: Any,
                     numero: Any = "") -> list[dict]:
    """Os selos deste ato, com a ETIQUETA INTEIRA do razao. SO LE.

        «o carimbo de certidao sempre precisa ir completo, com os emolumentos
         do ato, esta faltando ali» — o oficial, 17/09/2026

    **A COLUNA GUARDA O NUMERO; A ETIQUETA MORA NO RAZAO.** Medido: a coluna
    de selo do ato tem os **28 caracteres** do codigo e `sd_selos.texto` tem os
    **264** com `Total R$ … Emol R$ … FERC R$ …`. O carimbo monta o que diz a
    partir do texto que recebe — com o numero, ele nao tem de onde tirar os
    valores.

    **A CHAVE E `tabela` MAIS `ato_id`**: por `ato_id` sozinho vem selo de
    outra atribuicao (medido em 15/09 — tres reconhecimentos de firma de 2022
    responderam por ids de `ri_atos`).

    **E HA UMA SEGUNDA PORTA, pelo NUMERO gravado no ato.** Ela existe porque
    **762 dos 765** selos de certidao do razao estao com `tabela` nula: vieram
    da carga do acervo, que gravou o selo dentro do ato sem amarrar o razao.
    Sem ela, toda certidao anterior a este sistema sairia sem valores.

    **E O NUMERO CONTINUA VALENDO QUANDO O RAZAO NAO TEM NADA**: devolve-se o
    numero sozinho, e o carimbo sai sem a linha de valores — que e a verdade.
    Remontar a conta aqui seria imprimir num papel assinado um valor que o
    selo nao declara.
    """
    achados: list[dict] = []
    try:
        bd = banco(con)
        if tabela and ato_id:
            achados = [dict(r) for r in bd.ler(
                """SELECT numero, texto FROM sd_selos
                    WHERE tabela = %s AND ato_id = %s ORDER BY obtido_em, id""",
                (str(tabela), int(ato_id)))]
        codigo = str(numero or "").strip()
        if not achados and codigo:
            achados = [dict(r) for r in bd.ler(
                "SELECT numero, texto FROM sd_selos WHERE numero = %s ORDER BY id",
                (codigo,))]
    except sqlite3.Error:
        achados = []
    if not achados and str(numero or "").strip():
        achados = [{"numero": str(numero).strip(), "texto": ""}]
    return achados


def etiqueta_do_ato(con: sqlite3.Connection, tabela: Any, ato_id: Any,
                    numero: Any = "") -> str:
    """O texto do selo deste ato, pronto para o carimbo. SO LE.

    Os selos do ato emendados — `separar_selos` os separa de volta no papel —,
    e o numero sozinho quando o razao nao guardou a etiqueta.
    """
    fora = []
    for item in etiquetas_do_ato(con, tabela, ato_id, numero):
        fora.append(str(item.get("texto") or "").strip()
                    or str(item.get("numero") or "").strip())
    return "\n".join(x for x in fora if x)


# ============================== o selo do ATO DE LIVRO das Notas
#
# MEDIDO EM 17/09/2026 nos 283 envelopes reais desta casa, e o que amarra cada
# caminho ao seu ato e o `selo{livro, folha}` de dentro do envelope, que casa
# com o livro e a folha do ato em `nt_atos`:
#
#   /selo/notas/procuracao/poderes-especificos  217  ->  204 PROCURACAO
#   /selo/notas/procuracao/simples               22  ->   22 PROCURACAO
#   /selo/notas/procuracao/venda                  1  ->    1 PROCURACAO
#   /selo/notas/ato-declarado/com-valor          28  ->   17 ESCRITURA
#   /selo/notas/ato-declarado/sem-valor          15  ->   14 ESCRITURA
#
# ZERO CRUZAMENTO: nenhum caminho de procuracao casou com escritura, e nenhum
# de ato declarado casou com procuracao.
#
# E `/selo/notas/atos-em-geral` NAO E ATO DE LIVRO, embora o nome diga que sim:
# 739 envelopes, **nenhum** com `selo{livro, folha}`, e 712 com o item 13.30 —
# «Arquivamento, por folha do documento». E o guarda-chuva do balcao.

CAMINHO_DA_ESCRITURA_COM_VALOR = "/selo/notas/ato-declarado/com-valor"
CAMINHO_DA_ESCRITURA_SEM_VALOR = "/selo/notas/ato-declarado/sem-valor"

# A ata comum e ato notarial sem valor declarado e usa o mesmo CONTRATO do
# ato declarado sem valor. Nao se trata de reutilizar o item da escritura: o
# caminho define a forma do envelope; o item 13.14.1 abaixo identifica a ata.
# A tabela ativa da propria serventia, conferida em 17/09/2026, traz:
#   13.14.1  Ata notarial, primeira folha
#   13.14.2  Ata notarial, por folha excedente (cobranca complementar)
# A ata de usucapiao remete ao item 13.1 e, portanto, exige valor do imovel.
CAMINHO_DA_ATA_SEM_VALOR = CAMINHO_DA_ESCRITURA_SEM_VALOR
CAMINHO_DA_ATA_USUCAPIAO = CAMINHO_DA_ESCRITURA_COM_VALOR

# As tres procuracoes, na ordem em que a casa as usou.
CAMINHO_DA_PROCURACAO: dict[str, str] = {
    "PODERES_ESPECIFICOS": "/selo/notas/procuracao/poderes-especificos",
    "SIMPLES": "/selo/notas/procuracao/simples",
    "VENDA": "/selo/notas/procuracao/venda",
}

# Os tipos de ato de livro que selam pelos tres caminhos acima (15/10/2026).
# A previdenciaria e a renuncia entraram no mesmo dia, por decisao dele.
TIPOS_QUE_SELAM_COMO_PROCURACAO = frozenset(
    {"PROCURACAO", "SUBSTABELECIMENTO", "REVOGACAO",
     "PROCURACAO_PREVIDENCIARIA", "RENUNCIA"})

# A natureza do ato declarado SEM valor, medida em 15 de 15 envelopes. Nao ha
# outra forma no acervo, e por isso ela nao se pergunta.
NATUREZA_DO_ATO_DECLARADO_SEM_VALOR = {"descricao": "Outros", "tipo": 41}

# OS ITENS QUE A CASA USOU EM CADA CAMINHO, em ordem de frequencia. Servem a
# TELA — item de um uso em duzentos e excecao, e nao regra —, e nao decidem
# nada: quem escolhe o item e quem atende.
ITENS_MEDIDOS_DO_ATO_DE_LIVRO: dict[str, tuple[tuple[str, int], ...]] = {
    CAMINHO_DA_ESCRITURA_COM_VALOR: (("13.1", 21), ("13.30", 6), ("13.2", 1)),
    CAMINHO_DA_ESCRITURA_SEM_VALOR: (("13.2", 13), ("13.30", 2)),
    CAMINHO_DA_PROCURACAO["PODERES_ESPECIFICOS"]: (
        ("13.9.3", 136), ("13.17.1", 39), ("13.9.2", 29), ("13.30", 10),
        ("13.18", 1), ("13.21.1", 1), ("13.17.2", 1)),
    CAMINHO_DA_PROCURACAO["SIMPLES"]: (
        ("13.9.3", 8), ("13.30", 7), ("13.9.2", 6), ("13.17.1", 1)),
    CAMINHO_DA_PROCURACAO["VENDA"]: (("13.9.3", 1),),
}

# A PROCURAÇÃO DO INSS TEM CAMINHO PRÓPRIO NO CONTRATO, e a casa nunca o usou
# (LG04, 19/10/2026). `/selo/notas/procuracao/inss` é o mesmo schema
# `ProcuracaoNotas` dos três de cima — o envelope é o mesmo, muda o endereço —,
# e por isso ele entra como QUARTA escolha da previdenciária, sem tirar as três
# que o oficial decidiu em 15/10/2026. Só a previdenciária o oferece: a
# procuração comum que saísse por ele seria selo do INSS em ato que não é.
CAMINHO_DA_PROCURACAO_DO_INSS = "/selo/notas/procuracao/inss"
ESPECIE_DA_PROCURACAO_DO_INSS = "INSS"

# O TESTAMENTO TEM CAMINHO PRÓPRIO NO CONTRATO (`/selo/notas/testamento`,
# schema `TestamentoNotas`) e ITENS PRÓPRIOS NA TABELA — conferidos na de 2026
# (`tests/custas_reais.json`, serviços 391 a 394):
#
#   13.10.1  Público sem conteúdo patrimonial
#   13.10.2  Público com valor patrimonial
#   13.10.3  Cerrado, incluindo todos os atos necessários
#   13.10.4  Revogação de testamento (a revogação se faz por outro testamento,
#            CC art. 1.969 — por isso o item é do público)
#
# Até o LG04 (19/10/2026) o caminho não existia aqui, e todo testamento lançado
# ia a SUSPENSO_SELO: a tela dizia «ainda não há caminho de selo» e o ato
# ficava com livro e folha reservados, sem selo e sem RCTO. O acervo não tem
# envelope de testamento para medir; a forma é a da procuração (`dadosSelo` do
# mesmo contrato, partes + quantidade + selo{livro, folha}), e a primeira
# emissão em homologação é quem confirma. O zero diz «previsto na tabela», como
# nos itens da ata — e não «nunca usado».
CAMINHO_DO_TESTAMENTO = "/selo/notas/testamento"
ITENS_DO_TESTAMENTO: dict[str, tuple[tuple[str, int], ...]] = {
    "TESTAMENTO": (("13.10.1", 0), ("13.10.2", 0), ("13.10.4", 0)),
    "TESTAMENTO_CERRADO": (("13.10.3", 0),),
}
ITENS_PREVISTOS_POR_CAMINHO: dict[str, tuple[tuple[str, int], ...]] = {
    # «Outras procurações»: a tabela não tem item próprio da previdenciária.
    # A gratuidade, quando couber, é o selo isento com o motivo escrito.
    CAMINHO_DA_PROCURACAO_DO_INSS: (("13.9.3", 0),),
}


def conferir_item_do_testamento(tipo: Any, codigo_tj: Any) -> str | None:
    """O item escolhido é de testamento DESTA espécie? Só calcula.

    O cerrado custa 13.10.3 e o público 13.10.1/13.10.2: cobrar um pelo outro
    é selo emitido com o valor errado, e selo não se desfaz. Devolve o recado
    da recusa, ou `None` quando o item serve (ou o ato não é testamento).
    """
    especie = str(tipo or "").strip().upper()
    itens = ITENS_DO_TESTAMENTO.get(especie)
    if itens is None:
        return None
    validos = [codigo for codigo, _ in itens]
    if str(codigo_tj or "").strip() not in validos:
        return (f"o item {str(codigo_tj or '').strip() or '(vazio)'} não é de "
                f"{'testamento cerrado' if especie == 'TESTAMENTO_CERRADO' else 'testamento público'}"
                f" — use {' ou '.join(validos)}")
    return None

# Itens proprios da ata. O zero no segundo campo significa "previsto na
# tabela", e nao zero usos: a tela distingue estes itens dos medidos no
# acervo. O 13.14.2 nao e o selo principal; e o acrescimo por folha excedente
# e deve ser cobrado separadamente, sem substituir o 13.14.1 do ato.
ITENS_DA_ATA: dict[str, tuple[tuple[str, int], ...]] = {
    "ATA": (("13.14.1", 0),),
    "ATA_USUCAPIAO": (("13.1", 0),),
}

# A ATA PARA USUCAPIAO SE COBRA PELA FAIXA, como a escritura com valor (LD02,
# 21/10/2026): «a ata notarial sera considerada ato de conteudo economico,
# devendo-se tomar por base para a cobranca de emolumentos o valor venal do
# imovel» — CNN (Prov. 149/2023) art. 423, I. O item da tela e o da faixa do
# 13.1 para o valor informado, e o selo recusa outro.
TIPOS_COBRADOS_PELA_FAIXA = frozenset({"ESCRITURA", "ATA_USUCAPIAO"})

# O ITEM PROPRIO DA ESPECIE NA TABELA (LD02, 21/10/2026). A tela do ato so
# oferecia os itens MEDIDOS no caminho do selo — no substabelecimento, na
# revogacao e na renuncia, os da procuracao; na separacao, no divorcio e na
# extincao da uniao estavel sem bens, os da escritura sem valor —, e a tabela
# de 2026 tem item proprio para eles (`tests/custas_reais.json`, servicos 385,
# 389 e 390):
#
#   13.7    Escritura de separacao, divorcio e extincao de uniao estavel sem
#           bens a partilhar
#   13.9.5  Nos substabelecimentos de procuracoes (os emolumentos do 13.9.3)
#   13.9.6  Revogacao de procuracao e de substabelecimento ou renuncia do
#           mandato
#
# O caixa cobra pelo proprio, e o selo pedido pelo item da tela nao achava o
# item pago no protocolo. O zero diz «previsto na tabela», como nos da ata.
ITENS_PROPRIOS_POR_TIPO: dict[str, tuple[tuple[str, int], ...]] = {
    "SUBSTABELECIMENTO": (("13.9.5", 0),),
    "REVOGACAO": (("13.9.6", 0),),
    "RENUNCIA": (("13.9.6", 0),),
}
ITEM_DA_FAMILIA_SEM_BENS = "13.7"
# Separacao (1), conversao da separacao em divorcio (3) e divorcio direto (4),
# no tipo da CESDI; a dissolucao da uniao estavel (20), na natureza da CEP.
TIPOS_CESDI_DO_13_7 = frozenset({1, 3, 4})
NATUREZAS_CEP_DO_13_7 = frozenset({20})


def itens_proprios_da_especie(ato: Any) -> list[tuple[str, int]]:
    """O item proprio da tabela para a especie deste ato de livro. So calcula.

    A escritura de familia so leva o 13.7 SEM BENS A PARTILHAR — sem valor
    declarado; com valor, quem decide o item e a faixa do 13.1. Quem escolhe
    continua sendo quem atende: a lista poe o proprio primeiro, e nao tira os
    medidos.
    """
    a = dict(ato or {})
    tipo = str(a.get("tipo") or "").strip().upper()
    if tipo in ITENS_PROPRIOS_POR_TIPO:
        return list(ITENS_PROPRIOS_POR_TIPO[tipo])
    if tipo == "ESCRITURA" and not a.get("valor_transacao"):
        def _int(v):
            try:
                return int(v)
            except (TypeError, ValueError):
                return None
        if (_int(a.get("tipo_cesdi")) in TIPOS_CESDI_DO_13_7
                or _int(a.get("natureza_censec")) in NATUREZAS_CEP_DO_13_7):
            return [(ITEM_DA_FAMILIA_SEM_BENS, 0)]
    return []


def caminho_do_ato_de_livro_das_notas(
        tipo: Any, *, com_valor: bool = False,
        especie_procuracao: Any = None) -> str:
    """De que caminho sai o selo deste ato de livro. So calcula.

    **A ESCRITURA ESCOLHE PELO VALOR DECLARADO**, e nao pelo tipo do ato — a
    mesma regra do ato do RI, e aqui ela esta escrita no proprio nome dos dois
    caminhos.

    **A PROCURACAO ESCOLHE POR QUEM ATENDE.** A natureza que este sistema
    guarda nao separa as tres: `OUTRA`, `DETRAN — Modelo Amplos` e `BANCO DO
    NORDESTE S/A — PRONAF` aparecem em mais de um caminho. Os 204 de poderes
    especificos contra 22 simples sao 90%, e **correlacao forte parece regra
    ate alguem contar as excecoes**.

    **A ATA COMUM E ATO DECLARADO SEM VALOR.** O contrato do selador usa a
    mesma forma de envelope da escritura sem valor; quem separa os atos e o
    item 13.14.1 da tabela de custas, nao um caminho inventado.

    **A ATA DE USUCAPIAO TEM VALOR.** O item 13.14.3 manda calcular pela faixa
    13.1 conforme o valor do imovel; sem esse valor o pedido seria falso e e
    recusado antes de chegar ao aparelho.

    **O TESTAMENTO, PUBLICO OU CERRADO, TEM CAMINHO PROPRIO** (LG04), e a
    previdenciaria ganha o do INSS como quarta escolha — ver
    `CAMINHO_DO_TESTAMENTO` e `CAMINHO_DA_PROCURACAO_DO_INSS`.
    """
    especie = str(tipo or "").strip().upper()
    if especie == "ESCRITURA":
        return (CAMINHO_DA_ESCRITURA_COM_VALOR if com_valor
                else CAMINHO_DA_ESCRITURA_SEM_VALOR)
    # O SUBSTABELECIMENTO E A REVOGACAO SELAM PELO CAMINHO DA PROCURACAO —
    # decisao do oficial, 15/10/2026. O acervo nao tem precedente (nenhum
    # substabelecimento, e a unica revogacao sem selo); quem decidiu foi ele.
    if especie in ITENS_DO_TESTAMENTO:
        return CAMINHO_DO_TESTAMENTO
    if especie in TIPOS_QUE_SELAM_COMO_PROCURACAO:
        qual = str(especie_procuracao or "").strip().upper()
        if (especie == "PROCURACAO_PREVIDENCIARIA"
                and qual == ESPECIE_DA_PROCURACAO_DO_INSS):
            return CAMINHO_DA_PROCURACAO_DO_INSS
        caminho = CAMINHO_DA_PROCURACAO.get(qual)
        if not caminho:
            raise AtoError(
                "O selo da procuração sai por três caminhos diferentes — "
                "poderes específicos, simples e para venda —, e esta casa usou "
                "os três. Diga qual é o desta procuração: a natureza gravada "
                "no ato não separa (as mesmas naturezas aparecem nos três).")
        return caminho
    if especie == "ATA":
        return CAMINHO_DA_ATA_SEM_VALOR
    if especie == "ATA_USUCAPIAO":
        if not com_valor:
            raise AtoError(
                "A ata para usucapião só pode ser selada depois de informar "
                "o valor do imóvel: o item 13.14.3 remete às faixas do item "
                "13.1 conforme esse valor.")
        return CAMINHO_DA_ATA_USUCAPIAO
    raise AtoError(
        f"Não há caminho de selo medido para {especie.lower() or 'este ato'} "
        f"nas Notas. Não se sela por um caminho inventado.")


def envelope_do_ato_de_livro_das_notas(
        *, tipo: Any, codigo_tj: Any, escrevente: Any, versao_tabela: Any,
        livro: Any, folha: Any, termo: Any = None, partes: Any = None,
        valor_declarado: Any = None, valor_avaliado: Any = None,
        especie_procuracao: Any = None, isento: bool = False,
        motivo_isencao: Any = None) -> tuple[dict, str]:
    """O pedido do selo da escritura, procuracao ou ata. So calcula.

    Devolve `(envelope, caminho)`, como o do RTD/RCPJ — quem chama precisa dos
    dois, e calcula-los em dois lugares seria deixa-los divergir.

    **AS DUAS FORMAS SAO DIFERENTES, e nenhuma se monta a partir da outra:**

        com valor   partes, selo{...}, valorDeclarado{...}, ato{}
        sem valor   natureza{}, partes, quantidade, selo{...}, ato{}
        procuracao  partes, quantidade, selo{...}, ato{}

    Medido: os 28 `com-valor` **nao mandam `quantidade`**, e os 15 `sem-valor`
    mandam `natureza{descricao: "Outros", tipo: 41}` em 15 de 15.

    **O `termo` VAI QUANDO HA**: 153 dos 283 envelopes o mandam, e este sistema
    o tem no lancamento.
    """
    com_valor = valor_declarado is not None
    caminho = caminho_do_ato_de_livro_das_notas(
        tipo, com_valor=com_valor, especie_procuracao=especie_procuracao)

    faltando = [nome for nome, valor in
                (("o item da tabela de custas", codigo_tj),
                 ("o escrevente", escrevente),
                 ("a versão da tabela de custas", versao_tabela),
                 ("o livro", livro),
                 ("a folha", folha))
                if not str(valor or "").strip()]
    if faltando:
        raise AtoError(
            f"O selo do ato de livro não sai sem {', '.join(faltando)}. "
            f"O livro e a folha entram no pedido, e por isso o selo sai "
            f"DEPOIS do lançamento — como no resto da casa.")

    # AS DUAS FORMAS DE `parteAto`, medidas: `{nome}` em 429 e
    # `{nome, documento}` em 185. Mandar `documento: ""` onde a casa mandava so
    # o nome seria inventar um campo vazio que ela nunca mandou.
    def _parte(p) -> dict:
        nome = str((p or {}).get("nome") or "").strip()
        doc = "".join(c for c in str((p or {}).get("documento") or "")
                      if c.isdigit())
        return {"nome": nome, "documento": doc} if doc else {"nome": nome}

    dados_do_selo: dict[str, Any] = {
        "escrevente": str(escrevente).strip(),
        "livro": str(livro).strip(),
        "folha": str(folha).strip(),
    }
    if str(termo or "").strip():
        dados_do_selo["termo"] = str(termo).strip()

    envelope: dict[str, Any] = {
        "partes": {"nomePartes": [],
                   "parteAto": [_parte(p) for p in (partes or [])]},
        "selo": dados_do_selo,
        "ato": {"codigo": str(codigo_tj).strip(),
                "codigoTabelaCusta": str(versao_tabela).strip()},
    }
    if caminho == CAMINHO_DA_ESCRITURA_COM_VALOR:
        envelope["valorDeclarado"] = {
            "valorDeclarado": float(valor_declarado or 0),
            "valorAvaliado": float(
                valor_avaliado if valor_avaliado is not None
                else valor_declarado or 0),
        }
    else:
        envelope["quantidade"] = 1
        if caminho == CAMINHO_DA_ESCRITURA_SEM_VALOR:
            envelope["natureza"] = dict(NATUREZA_DO_ATO_DECLARADO_SEM_VALOR)

    # A ISENCAO VEM COM O MOTIVO ESCRITO, e os 8 casos reais desta casa sao
    # todos a procuracao do INSS (art. 68-A da Lei 8.212/1991). Sem motivo nao
    # se marca: isento sem motivo e o que a conferencia nao consegue explicar.
    if isento:
        motivo = str(motivo_isencao or "").strip()
        if not motivo:
            raise AtoError(
                "Selo isento precisa do motivo escrito — é ele que a "
                "conferência lê no selo e no caixa.")
        envelope["isento"] = {"value": True, "motivo": motivo}
    return envelope, caminho


# ==================== A MARCA DO RECADO DO SELO — a regra do item 1
#
# **A REGRA VALE PARA TODA FALHA** — 16/09/2026: «se falhar o selo, sempre
# suspender o ato para corrigir o problema». Recusa do aparelho, configuração
# ausente e dado obrigatório não preenchido têm motivos diferentes, mas nenhum
# deles autoriza concluir um ato sem selo. A única exceção é o acervo do RI,
# tratada explicitamente no módulo daquela atribuição.
#
# **E A DISTINCAO NAO SE LE NA PROSA.** Adivinhar a especie pelo texto do
# recado seria o varredor batendo na propria prosa — e aqui o custo e um ato
# que nao se lavra. A marca vai PRESA ao recado, e o criterio e estrutural:
# o tipo conserva a causa para a tela, mas o lado seguro é sempre suspender.


class RecadoDoSelo(str):
    """O recado de um pedido de selo, com a especie da falha presa nele.

    **E UM `str` DE PROPOSITO**: as telas concatenam recados (`aviso += …`), e
    trocar o tipo quebraria todas elas. A concatenacao devolve `str` puro —
    por isso quem decide le o recado DO SELO, e nao a soma dos avisos.
    """

    suspende: bool = True

    def __new__(cls, texto: Any = "", *, suspende: bool = True):
        obj = super().__new__(cls, str(texto or ""))
        obj.suspende = bool(suspende)
        return obj


def recado_de_falta(texto: Any) -> RecadoDoSelo:
    """Falta de cadastro/preenchimento também impede concluir o ato.

    Item não marcado, data da tabela ausente ou folha indisponível não são
    autorização para criar ato sem selo. A diferença para a recusa da rede é
    apenas o motivo mostrado ao balcão; ambas suspendem. O ato histórico de
    acervo é tratado explicitamente pelo módulo do RI e não passa por esta
    regra.
    """
    return RecadoDoSelo(texto, suspende=True)


def recado_de_recusa(texto: Any) -> RecadoDoSelo:
    """O APARELHO nao devolveu o selo: o ato se suspende.

    Fora do ar, nao apontado, credencial vencida, recusa do TJMA. E o caso em
    que **corrigir e lavrar de novo resolve**, e e por isso que ele suspende —
    ordem do oficial em 16/09/2026.
    """
    return RecadoDoSelo(texto, suspende=True)


def suspende_o_ato(recado: Any) -> bool:
    """Este recado suspende o ato? So calcula.

    **O QUE NAO VEM MARCADO CONTA COMO RECUSA** — o lado seguro, que e o
    comportamento de antes desta marca existir. Produtor que esqueca de marcar
    nao deixa de suspender; quem o pega e o varredor que exige toda frase «SEM
    SELO» marcada.
    """
    if not str(recado or "").strip():
        return False
    return bool(getattr(recado, "suspende", True))


# ===================================================== selo × caixa (LX16)
#
# «os selos pagos precisam estar sempre vinculados a um protocolo geral e à
#  confirmação da entrada de um dinheiro. Não tem como permitir selo pago sem
#  um protocolo e sem o registro de que o item foi pago ou entrou antes em
#  depósito prévio. Essa cobrança precisa ser muito didática para os
#  escreventes.»                                    — o oficial, 19/10/2026
#
# E A CORREÇÃO DELE, NO MESMO DIA: a GRATUIDADE NÃO TRAVA. «Geralmente temos o
# comprovante da gratuidade só depois que o ato é praticado.» O selo gratuito
# sai sempre, e a cobrança do comprovante é aviso à pessoa
# (`gratuidade_comprovante`), como decidido em 11/10.
#
# A TRAVA MORA EM `obter_selo`, E SÓ ALI. É a única função que chama o
# aparelho (`selador_cliente.selar`): todas as telas — RI, Notas, RCPN,
# Protesto, RTD/RCPJ, certidões, robôs e selo automático — chegam a ela por
# `selar_o_ato_lavrado`. Pôr a trava numa tela seria deixar as outras vinte
# de fora; o teste `test_selo_e_caixa` percorre os caminhos e confere que
# nenhum chama o aparelho por fora.
#
# O QUE COBRE UM SELO PAGO, nesta ordem:
#   1. um item de PROTOCOLO GERAL ligado ao ato, e pago — quitado, ou pago
#      agora pelo DEPÓSITO PRÉVIO do protocolo (débito sob FOR UPDATE, sem
#      saldo negativo), ou DIFERIDO por lei (só o Protesto: a posteriori e
#      CRA, com quem paga e quando);
#   2. o lançamento do próprio ato no caixa (`cobrar`), com protocolo;
#   3. o item do PROTOCOLO EM ATENDIMENTO do escrevente, pelo código do selo
#      (uma unidade por selo);
#   4. a liberação do ADMIN, com justificativa — e aí a pendência continua.
# Com a trava desligada (só ADMIN, em Configurações), passa tudo, e a barra
# vermelha fica no topo de todas as telas enquanto ela estiver assim.
#
# A COBERTURA É RESERVADA ANTES DO APARELHO E CONFIRMADA DEPOIS (LX21a,
# 20/10/2026). O débito e a unidade saem do saldo numa transação curta, e a
# linha de `cx_selo_coberturas` fica «RESERVADA»; o selo é pedido sem nada
# preso; e a reserva vira «CONFIRMADA» junto com o selo no razão, ou é
# ESTORNADA (o dinheiro volta ao depósito, a unidade volta ao item, a linha
# sai e o porquê fica em `audit_logs`). Ver `obter_selo`.

CHAVE_DA_TRAVA = "selo_trava_caixa"
TRAVA_DESLIGADA = "DESLIGADA"
#: Desde quando o oficial confere os selos que saíram ANTES desta versão
#: (relatório «selos pagos sem protocolo/pagamento»). Configurável.
CHAVE_DESDE_DA_CONFERENCIA = "selo_conferencia_desde"
DESDE_DA_CONFERENCIA_PADRAO = "2026-01-01"
#: Justificativa de quem libera ou desliga: frase que diga alguma coisa a
#: quem ler daqui a dois anos, e não «ok».
MINIMO_DA_JUSTIFICATIVA = 15
PAPEL_QUE_LIBERA = "ADMIN"

FORMA_GRATUITO = "GRATUITO"
FORMA_ITEM_PAGO = "ITEM_PAGO"
FORMA_DEPOSITO = "DEPOSITO"
FORMA_DIFERIDO = "DIFERIDO"
FORMA_LANCAMENTO = "LANCAMENTO"
FORMA_LIBERADO = "LIBERADO"
FORMA_TRAVA_DESLIGADA = "TRAVA_DESLIGADA"
# A CERTIDÃO ELETRÔNICA DA CRC — 22/10/2026, o oficial: «o selo da
# certidão eletrônica funciona com valores da CRC, não entram
# imediatamente no caixa». O dinheiro vem pela Central, e a trava do selo
# pago (que procura o protocolo pago no caixa) não o enxerga. A forma vale
# SÓ para a certidão do RCPN gravada com a finalidade abaixo E com o item
# 14.5.7 no envelope — não abre a trava para nenhum outro selo.
FORMA_CENTRAL_CRC = "CENTRAL_CRC"
FINALIDADE_CERTIDAO_ELETRONICA_CRC = "Certidão eletrônica — CRC (item 14.5.7)"
CODIGO_CERTIDAO_ELETRONICA_CRC = "14.5.7"

# O CAMINHO DO SELO DA CERTIDÃO ELETRÔNICA É O GERAL DO CIVIL — 23/10/2026.
#
#   Pela segunda via (`DadosSegundaViaCertidao`) o aparelho recusou o pedido da
#   certidão 171: «É obrigatório informar os dados utilizados no papel moeda»
#   — o contrato diz que `papelMoeda` é opcional, e o aparelho o exige. A
#   certidão eletrônica não sai em folha de segurança. O oficial mandou testar
#   o caminho geral, que é o dos 60 selos 14.5.7 desta casa de 03/2022 a
#   06/2024, e SÓ para este selo: as outras certidões seguem pela segunda via.
#
#   O envelope é o dos 1.238 medidos em `/selo/civil/atos-em-geral` (o último
#   em 23/09/2024): `codigoAto`, `nomesPartes{nomePartes, parteAto}`,
#   `dadosSelo{escrevente, versaoTabelaDeCustas}` e `quantidade`. O isento ia
#   como `isentoGratuito: "ISENTO"` mais o motivo (17 dos 1.238).
CAMINHO_CERTIDAO_ELETRONICA_CRC = "/selo/civil/atos-em-geral"


def envelope_da_certidao_eletronica_crc(*, nome_parte: Any, documento: Any,
                                        escrevente: Any, versao_tabela: Any,
                                        isento: bool = False,
                                        motivo_isencao: Any = None) -> dict:
    """O pedido do selo 14.5.7 pelo caminho geral do civil. Só calcula."""
    nome = str(nome_parte or "").strip()
    faltando = [o for o, v in (("o nome da parte", nome),
                               ("o escrevente", escrevente),
                               ("a versão da tabela de custas", versao_tabela))
                if not str(v or "").strip()]
    if faltando:
        raise AtoError(f"O selo da certidão eletrônica não sai sem "
                       f"{', '.join(faltando)}.")
    doc = "".join(c for c in str(documento or "") if c.isdigit()) or "00000000000"
    dados_selo: dict[str, Any] = {"escrevente": str(escrevente).strip(),
                                  "versaoTabelaDeCustas": str(versao_tabela).strip()}
    if isento:
        motivo = str(motivo_isencao or "").strip()
        if not motivo:
            raise AtoError(
                "Ato gratuito / isento precisa do motivo escrito — é ele que a "
                "conferência do Tribunal lê no selo.")
        dados_selo["isentoGratuito"] = "ISENTO"
        dados_selo["motivoIsentoGratuito"] = motivo.upper()
    return {"codigoAto": CODIGO_CERTIDAO_ELETRONICA_CRC,
            "nomesPartes": {"nomePartes": [nome],
                            "parteAto": [{"documento": doc, "nome": nome}]},
            "dadosSelo": dados_selo,
            "quantidade": 1}
#: O que conta como dinheiro (ou diferimento legal) de verdade. Liberação e
#: trava desligada deixam o selo sair, mas NÃO fecham a pendência.
FORMAS_QUE_COBREM = frozenset({FORMA_ITEM_PAGO, FORMA_DEPOSITO,
                               FORMA_DIFERIDO, FORMA_LANCAMENTO,
                               FORMA_CENTRAL_CRC})

#: A cobertura enquanto o selo está sendo pedido, e depois que ele saiu.
RESERVADA = "RESERVADA"
CONFIRMADA = "CONFIRMADA"
COLUNAS_DA_RESERVA = (
    ("situacao", "TEXT NOT NULL DEFAULT 'CONFIRMADA'"),
    ("unidades_gastas", "integer NOT NULL DEFAULT 0"),
    ("confirmada_em", "TEXT"))
#: Reserva mais velha que isto é de um pedido que caiu no meio. O pedido mais
#: longo que existe é o token (20 s) mais duas voltas de duas tentativas de
#: 20 s no aparelho, mais a espera da trava — uns dois minutos; cinco dão folga
#: sem deixar o escrevente esperando a manhã inteira.
PRAZO_DA_RESERVA_EM_SEGUNDOS = 5 * 60

# As frases do quadro. Curtas, sem jargão, com o porquê em uma linha.
TITULO_DO_QUADRO = "Para selar este ato falta:"
POR_QUE_PROTOCOLO = ("o selo pago precisa do protocolo do balcão: é por ele "
                     "que o caixa sabe o que o cliente pediu.")
POR_QUE_PAGAMENTO = ("selo pago só sai com o dinheiro registrado — pago no "
                     "caixa ou guardado em depósito prévio.")
POR_QUE_GRATUITO = ("o Portal do Selo pede o comprovante de cada selo "
                    "gratuito.")
O_QUE_VAI_NO_PDF = "um PDF com: comprovante + certidão do ato"

SCHEMA_DA_TRAVA = """
CREATE TABLE IF NOT EXISTS cx_selo_coberturas (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    referencia TEXT NOT NULL UNIQUE,
    tabela TEXT,
    ato_id bigint,
    forma TEXT NOT NULL,
    protocolo_id bigint,
    item_id bigint,
    deposito_id bigint,
    lancamento_id bigint,
    liberacao_id bigint,
    valor_centavos bigint,
    usuario TEXT,
    criado_em TEXT NOT NULL,
    situacao TEXT NOT NULL DEFAULT 'CONFIRMADA',
    unidades_gastas integer NOT NULL DEFAULT 0,
    confirmada_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_cx_selo_coberturas_ato ON cx_selo_coberturas (tabela, ato_id);
CREATE TABLE IF NOT EXISTS cx_selo_liberacoes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tabela TEXT NOT NULL,
    ato_id bigint NOT NULL,
    justificativa TEXT NOT NULL,
    liberado_por TEXT,
    liberado_por_id bigint,
    liberado_em TEXT NOT NULL,
    usado_em TEXT,
    usado_por TEXT
);
CREATE INDEX IF NOT EXISTS ix_cx_selo_liberacoes_ato ON cx_selo_liberacoes (tabela, ato_id);
CREATE TABLE IF NOT EXISTS cx_selo_aguardando (
    tabela TEXT NOT NULL,
    ato_id bigint NOT NULL,
    motivo TEXT NOT NULL,
    usuario TEXT,
    desde TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    PRIMARY KEY (tabela, ato_id)
)
"""


def init_trava_do_selo_schema(con) -> None:
    """As tabelas da trava do selo e as do caixa que ela consulta.

    Idempotente. Vem DEPOIS de `init_caixa_schema`: o diferimento entra em
    `cx_protocolo_atos`.
    """
    import caixa_depositos as DEP
    import caixa_protocolo as CXP
    CXP.init_cobertura_schema(con)
    DEP.init_usos_schema(con)
    bd = banco(con)
    for comando in SCHEMA_DA_TRAVA.split(";\n"):
        if comando.strip():
            bd.escrever(comando)
    # A RESERVA (LX21a) chegou depois da tabela: quem já a tinha ganha as
    # colunas aqui. O que estava gravado antes saiu na mesma transação do
    # selo, e por isso é «CONFIRMADA» — o padrão da coluna.
    for coluna, tipo in COLUNAS_DA_RESERVA:
        if not bd.tem_coluna("cx_selo_coberturas", coluna):
            bd.escrever(f"ALTER TABLE cx_selo_coberturas ADD COLUMN {coluna} {tipo}")
    bd.escrever(
        """CREATE INDEX IF NOT EXISTS ix_cx_selo_coberturas_reservadas
               ON cx_selo_coberturas (criado_em) WHERE situacao = 'RESERVADA'""")
    # NA SUBIDA, a reserva que a queda deixou no meio é conferida.
    from datetime import datetime
    estornar_reservas_orfas(
        bd, agora=datetime.now().replace(microsecond=0).isoformat())


class SeloSemCobertura(AtoError):
    """O selo pago não foi pedido: falta protocolo ou pagamento.

    `falta` é o quadro, item por item, para a tela mostrar com os botões.
    """

    def __init__(self, recado: str, quadro: dict | None = None):
        super().__init__(recado)
        self.quadro = quadro or {}


class _NaoCoberto(Exception):
    """Só para `obter_selo` desfazer a transação da cobertura que não cobriu."""

    def __init__(self, cobertura: dict):
        super().__init__("sem cobertura")
        self.cobertura = cobertura


class SeloEmAndamento(AtoError):
    """O selo desta referência já está sendo pedido (outro balcão, outra aba).

    Deixar o segundo pedido seguir seria selar com a cobertura do primeiro —
    que pode ser estornada no instante seguinte, se o aparelho recusar.
    """


def _percorrer(dados: Any, profundidade: int = 3):
    """(chave, valor) do envelope, descendo nos blocos `dadosSelo`, `selo`..."""
    if profundidade < 0 or not isinstance(dados, dict):
        return
    for chave, valor in dados.items():
        yield chave, valor
        if isinstance(valor, dict):
            yield from _percorrer(valor, profundidade - 1)


def selo_e_gratuito(dados: Any) -> bool:
    """O envelope pede selo ISENTO/GRATUITO? Só calcula.

    É o que o aparelho lê: `isento: true` (o campo do contrato) ou
    `isentoGratuito` ISENTO/GRATUITO (o dos registros de nascimento e óbito).
    Os dois moram em `dadosSelo` na maioria dos envelopes.

    E AS NOTAS MANDAM `isento: {value: true, motivo}` (LT02, 20/10/2026) — a
    forma medida nos 8 selos isentos da procuração do INSS, que
    `envelope_do_ato_de_livro_das_notas`, o arquivamento e a certidão das
    Notas montam. Só o `true` solto era lido: a procuração previdenciária
    isenta e a certidão gratuita ficavam presas na trava do selo pago,
    contra a regra do oficial de 19/10 («a gratuidade NÃO trava»).
    """
    for chave, valor in _percorrer(dados):
        if chave == "isento" and valor is True:
            return True
        if (chave == "isento" and isinstance(valor, dict)
                and valor.get("value") is True):
            return True
        if (chave == "isentoGratuito"
                and str(valor or "").strip().upper() in ("ISENTO", "GRATUITO")):
            return True
    return False


_CHAVES_DO_CODIGO = ("codigoTipoAtoRegistro", "codigoTipoAtoCertidao",
                     "codigoTipoAto", "codigoAto")


def e_certidao_eletronica_da_crc(bd, tabela: Any, ato_id: Any, dados: Any) -> bool:
    """O selo é o da certidão eletrônica da CRC (o valor vem pela Central)?
    SÓ LÊ. Exige as duas coisas: a certidão do RCPN gravada com a finalidade
    da CRC, e o item 14.5.7 no envelope."""
    if tabela != "rc_certidoes" or ato_id is None:
        return False
    if codigo_do_envelope(dados) != CODIGO_CERTIDAO_ELETRONICA_CRC:
        return False
    linha = bd.um("SELECT finalidade FROM rc_certidoes WHERE id = %s",
                  (int(ato_id),))
    return bool(linha) and str(linha["finalidade"] or "").strip() == \
        FINALIDADE_CERTIDAO_ELETRONICA_CRC


def codigo_do_envelope(dados: Any) -> str | None:
    """O item da tabela do TJ que o envelope sela (`13.1`, `16.3`). Só calcula.

    Cada caminho dá um nome ao campo — medido nos envelopes deste módulo.
    """
    achados = dict(_percorrer(dados))
    for chave in _CHAVES_DO_CODIGO:
        if str(achados.get(chave) or "").strip():
            return str(achados[chave]).strip()
    for chave, valor in _percorrer(dados):
        if chave == "ato" and isinstance(valor, dict) and str(valor.get("codigo") or "").strip():
            return str(valor["codigo"]).strip()
    return None


def ato_da_referencia(referencia: Any) -> tuple[str | None, int | None]:
    """`tabela:ato_id[:...]` → (tabela, ato_id). Toda tela que sela usa essa forma.

    O que é só grafia (espaço, maiúscula) se normaliza: um ` RI_ATOS : 12`
    vindo de robô é o mesmo ato, e travar por isso seria segurar selo pago
    de verdade. O resto volta (None, None), e `cobrir_o_selo` diz no quadro
    o que chegou, em vez de pedir protocolo para um ato que ela não sabe qual é.
    """
    partes = [p.strip() for p in str(referencia or "").split(":")]
    if len(partes) >= 2 and partes[0].lower() in TABELAS_DE_ATO and partes[1].isdigit():
        return partes[0].lower(), int(partes[1])
    return None, None


def referencia_do_selo(referencia: Any, tabela: Any = None,
                       ato_id: Any = None) -> str:
    """A grafia ÚNICA da referência do selo: `tabela:ato_id[:resto]`. Só calcula.

    `ato_da_referencia` já lia ` PT_ATOS : 1 ` e `pt_atos:1` como o mesmo
    ato — mas a chave da cobertura (`cx_selo_coberturas.referencia`, única)
    e o SID do selador usavam o texto CRU (LX21a #1). Duas grafias do mesmo
    ato não se enxergavam: duas reservas, dois débitos no depósito e dois
    selos pagos ao aparelho para um ato só. `obter_selo` normaliza UMA vez,
    na entrada, e daí em diante a cobertura, o SID e o razão (`sd_selos`)
    usam esta forma.

    Só muda o que é grafia do ato: a tabela vai em minúscula, o número sem
    zero à esquerda e cada pedaço sem espaço em volta. O resto (`16.1:1`,
    o código do item) segue como veio — é ele que separa os selos de um
    mesmo ato. A referência que não é de ato (`robo:12`, `ATO-12`) só perde o
    espaço das pontas: a tela que a mandou continua recebendo o quadro
    «diga de que ato é».
    """
    texto = str(referencia or "").strip()
    if not texto and tabela is not None and ato_id is not None:
        texto = f"{tabela}:{ato_id}"
    tab, ident = ato_da_referencia(texto)
    if tab is None:
        return texto
    resto = [p.strip() for p in texto.split(":")[2:]]
    return ":".join([tab, str(ident), *resto])


def grafias_da_referencia(referencia: Any, tabela: Any = None,
                          ato_id: Any = None) -> list[str]:
    """As grafias em que a cobertura e o selo deste ato podem estar gravados. Só calcula.

    A canônica (`referencia_do_selo`) primeiro — é nela que se grava daqui em
    diante. Depois, se for outra, a CRUA, do jeito que o código de antes do
    LX24 a usava: `str(referencia or f"{tabela}:{ato_id}")` na chave de
    `cx_selo_coberturas`, e o mesmo texto no SID (`selador.sid` só tira o
    espaço das pontas). Sem ela, o ato antigo gravado como «PT_ATOS:01» não
    achava a própria cobertura nem o próprio selo, debitava de novo e ia ao
    aparelho com um SID novo: um segundo selo pago (revisão do LX24).

    Uma terceira grafia do mesmo ato (pedida como `pt_atos:1`, gravada como
    «PT_ATOS:01») não é procurada: `tools/conferir_referencias_de_selo.sql`
    mede se há referência fora da forma canônica na produção.
    """
    canonica = referencia_do_selo(referencia, tabela, ato_id)
    if referencia:
        crua = str(referencia)
    elif tabela is not None and ato_id is not None:
        crua = f"{tabela}:{ato_id}"
    else:
        crua = ""
    return [canonica] + ([crua] if crua and crua != canonica else [])


def _ler_setting(bd, chave: str) -> str:
    if not bd.tem_tabela("settings"):
        return ""
    linha = bd.um("SELECT value FROM settings WHERE key = %s", (chave,))
    return str((linha or {}).get("value") or "")


def trava_ligada(con) -> bool:
    """A trava do selo pago está valendo? Só LÊ. Ligada por padrão."""
    return _ler_setting(banco(con), CHAVE_DA_TRAVA).strip().upper() != TRAVA_DESLIGADA


def _auditar(bd, *, acao: str, usuario: Any, usuario_id: Any, entidade: str,
             entidade_id: Any, detalhes: dict, agora: str,
             agente: Any = None) -> None:
    """Pela função da casa (`identidade_do_robo.registrar`, 26/10/2026). Com
    `usuario_id`, a identidade sai da conta; sem ele, quem grava é a rotina do
    selo (`agente`), a mando de quem pediu o selo (`usuario`) ou, sem ninguém,
    do responsável pelas rotinas automáticas."""
    import json
    IDR.registrar(bd, ts=agora, user_id=usuario_id, username=usuario, action=acao,
                  entity_type=entidade,
                  entity_id=int(entidade_id) if str(entidade_id or "").isdigit() else None,
                  details=json.dumps(detalhes, ensure_ascii=False, default=str),
                  agente=agente if usuario_id is None else None,
                  a_mando_de=(usuario or IDR.PELO_RESPONSAVEL) if usuario_id is None else None)


def _so_admin(papel: Any, o_que: str) -> None:
    if str(papel or "").upper() != PAPEL_QUE_LIBERA:
        raise AtoError(f"Só o oficial (ADMIN) pode {o_que}. Peça a ele.")


def _justificativa(texto: Any) -> str:
    limpo = " ".join(str(texto or "").split())
    if len(limpo) < MINIMO_DA_JUSTIFICATIVA:
        raise AtoError(
            f"Escreva a justificativa com pelo menos {MINIMO_DA_JUSTIFICATIVA} "
            f"letras: ela fica na auditoria e é lida na correição.")
    return limpo


def ligar_trava(con, *, ligada: bool, papel: Any, usuario: Any,
                usuario_id: Any, justificativa: Any, agora: str) -> dict:
    """Liga ou desliga a trava do selo pago. ESCREVE. Só ADMIN.

    Desligar pede justificativa e fica na auditoria; enquanto desligada, a
    barra vermelha aparece para todos (`barra_da_trava`).
    """
    _so_admin(papel, "ligar ou desligar a trava do selo")
    motivo = _justificativa(justificativa) if not ligada else " ".join(
        str(justificativa or "").split())
    bd = banco(con)
    bd.escrever(
        """INSERT INTO settings (key, value) VALUES (%s, %s)
           ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
        (CHAVE_DA_TRAVA, "LIGADA" if ligada else TRAVA_DESLIGADA))
    _auditar(bd, acao="SELO_TRAVA_LIGADA" if ligada else "SELO_TRAVA_DESLIGADA",
             usuario=usuario, usuario_id=usuario_id, entidade="SETTINGS",
             entidade_id=None, detalhes={"justificativa": motivo}, agora=agora)
    return {"ligada": bool(ligada)}


def barra_da_trava(con) -> str | None:
    """A frase da barra vermelha, quando a trava está desligada. Só LÊ."""
    try:
        if trava_ligada(con):
            return None
    except sqlite3.Error:
        return None
    return ("A trava do selo pago está DESLIGADA: selos estão saindo sem "
            "protocolo e sem pagamento conferidos. Só o oficial religa, em "
            "Configurações.")


def liberar_selo(con, *, tabela: str, ato_id: int, justificativa: Any,
                 papel: Any, usuario: Any, usuario_id: Any, agora: str) -> dict:
    """A válvula de emergência: este ato sela sem cobertura. ESCREVE. Só ADMIN.

    Nunca do escrevente. Fica em `audit_logs` e na lista «selos liberados sem
    cobertura» do gestor — e a pendência (pagar) continua aberta para quem
    obteve o selo, até o caixa registrar o pagamento.
    """
    _so_admin(papel, "liberar um selo sem cobertura")
    if tabela not in TABELAS_DE_ATO:
        raise AtoError(f"{tabela!r} não é tabela de ato.")
    motivo = _justificativa(justificativa)
    bd = banco(con)
    novo = bd.escrever(
        """INSERT INTO cx_selo_liberacoes (tabela, ato_id, justificativa,
                                           liberado_por, liberado_por_id, liberado_em)
           VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
        (tabela, int(ato_id), motivo, usuario,
         int(usuario_id) if str(usuario_id or "").isdigit() else None, agora))
    lib_id = int(novo[0]["id"])
    _auditar(bd, acao="SELO_LIBERADO_SEM_COBERTURA", usuario=usuario,
             usuario_id=usuario_id, entidade=tabela, entidade_id=ato_id,
             detalhes={"liberacao_id": lib_id, "justificativa": motivo},
             agora=agora)
    return {"liberacao_id": lib_id, "tabela": tabela, "ato_id": int(ato_id)}


def _liberacao(bd, tabela: str, ato_id: int) -> dict | None:
    if not bd.tem_tabela("cx_selo_liberacoes"):
        return None
    return bd.um(
        """SELECT * FROM cx_selo_liberacoes WHERE tabela = %s AND ato_id = %s
            ORDER BY id LIMIT 1""", (tabela, int(ato_id)))


def _lancamento_do_ato(bd, tabela: str, ato_id: int) -> dict | None:
    """O lançamento do ato no caixa (`cobrar`), com protocolo. Só LÊ."""
    if not bd.tem_tabela("cx_lancamentos"):
        return None
    return bd.um(
        """SELECT * FROM cx_lancamentos
            WHERE origem = 'ATO' AND origem_chave LIKE %s
              AND sentido = 'ENTRADA' AND protocolo_id IS NOT NULL
              AND coalesce(estornado, 0) = 0 AND coalesce(excluido, 0) = 0
            ORDER BY id LIMIT 1""", (f"{tabela}:{int(ato_id)}:%",))


def _selo_ja_obtido(bd, *, cns: Any, atribuicao: Any,
                    referencias: list[str]) -> str | None:
    """O aparelho já deu o selo desta referência? Pedir de novo NÃO compra outro.

    `selador_cliente.selar` devolve o que está no razão pelo SID — e travar
    aí deixaria o ato sem o selo que já foi pago. Confere cada grafia
    (`grafias_da_referencia`, a canônica primeiro) e devolve AQUELA cujo SID
    tem selo: é por ela que o selo tem de ser pedido de novo. None se nenhuma.
    """
    if not cns or not bd.tem_tabela("sd_selos"):
        return None
    for ref in referencias:
        if not str(ref or "").strip():
            continue
        chave = selador.sid(cns, atribuicao, ref, 1)
        if bd.valor("SELECT count(*) AS n FROM sd_selos "
                    "WHERE sid = %s AND cancelado_em IS NULL", (chave,)):
            return ref
    return None


def _cobertura_gravada(bd, grafias: list[str]) -> dict | None:
    """A cobertura já gravada do ato, em qualquer das grafias. Só LÊ.

    Havendo duas (o ato pago duas vezes antes do LX24), vale a canônica.
    """
    if not bd.tem_tabela("cx_selo_coberturas"):
        return None
    return bd.um(
        """SELECT * FROM cx_selo_coberturas WHERE referencia = ANY(%s)
            ORDER BY (referencia = %s) DESC, id LIMIT 1""",
        (list(grafias), grafias[0]))


def _gravar_cobertura(bd, *, referencia: str, tabela: Any, ato_id: Any,
                      forma: str, usuario: Any, agora: str, item: Any = None,
                      deposito: Any = None, lancamento: Any = None,
                      liberacao: Any = None, unidades: int = 0) -> dict:
    """Grava a cobertura RESERVADA — o selo ainda não foi pedido. ESCREVE.

    A reserva leva tudo o que o estorno precisa para desfazer: o depósito e o
    valor debitados, o item e quantas unidades a trava gastou dele.
    """
    from caixa_schema import centavos
    reserva = {
        "referencia": referencia, "tabela": tabela, "ato_id": ato_id,
        "forma": forma,
        "protocolo_id": (item or {}).get("protocolo_id")
        or (lancamento or {}).get("protocolo_id"),
        "item_id": (item or {}).get("id"),
        "deposito_id": (deposito or {}).get("deposito_id"),
        "lancamento_id": (lancamento or {}).get("id"),
        "liberacao_id": (liberacao or {}).get("id"),
        "valor_centavos": (deposito or {}).get("valor_centavos")
        if deposito else (centavos((item or {}).get("valor_total")) if item else None),
        "usuario": usuario, "unidades_gastas": int(unidades),
        "situacao": RESERVADA}
    if not bd.tem_tabela("cx_selo_coberturas"):
        # Banco sem o esquema da trava (teste de unidade montado à mão): o
        # selo sai pela mesma régua, só não fica o rastro — e o estorno
        # trabalha com o que vai aqui.
        return {"coberto": True, "forma": forma, "reserva": reserva}
    bd.escrever(
        """INSERT INTO cx_selo_coberturas
               (referencia, tabela, ato_id, forma, protocolo_id, item_id,
                deposito_id, lancamento_id, liberacao_id, valor_centavos,
                usuario, criado_em, situacao, unidades_gastas)
           VALUES (%(referencia)s, %(tabela)s, %(ato_id)s, %(forma)s,
                   %(protocolo_id)s, %(item_id)s, %(deposito_id)s,
                   %(lancamento_id)s, %(liberacao_id)s, %(valor_centavos)s,
                   %(usuario)s, %(agora)s, %(situacao)s, %(unidades_gastas)s)
           ON CONFLICT (referencia) DO NOTHING""",
        reserva | {"agora": agora})
    return {"coberto": True, "forma": forma, "reserva": reserva,
            "protocolo": (item or {}).get("protocolo_numero"),
            "deposito": (deposito or {}).get("numero")}


#: De que atribuição é o protocolo que pode pagar o selo de cada tabela — na
#: língua de `cx_protocolos.atribuicao` (medido na produção em 22/10/2026:
#: RCPN, RI, NOTAS, FIRMAS e RTD nos últimos 30 dias). O balcão de firmas abre
#: protocolo como FIRMAS ou como NOTAS, e os dois valem para ele. Tabela fora
#: daqui não filtra — melhor mostrar a mais que esconder o pagamento certo.
ATRIBUICOES_DO_ATO: dict[str, frozenset] = {
    "pt_atos": frozenset({"PROTESTO"}),
    "pt_certidoes": frozenset({"PROTESTO"}),
    "at_certidoes": frozenset({"RTD", "RCPJ", "RI"}),
    "rc_certidoes": frozenset({"RCPN"}),
    "rc_atos": frozenset({"RCPN"}),
    "hc_habilitacoes": frozenset({"RCPN"}),
    "rg_atos": frozenset({"RTD", "RCPJ"}),
    "rg_notificacao_diligencias": frozenset({"RTD", "RCPJ"}),
    "rg_notificacao_certidoes": frozenset({"RTD", "RCPJ"}),
    "rg_livros_contabeis": frozenset({"RTD", "RCPJ"}),
    "ra_atos": frozenset({"RI"}),
    "ri_atos": frozenset({"RI"}),
    "ri_protocolos": frozenset({"RI"}),
    "ri_certidoes": frozenset({"RI"}),
    "ri_matriculas": frozenset({"RI"}),
    "nt_atos": frozenset({"NOTAS"}),
    "nt_certidoes": frozenset({"NOTAS"}),
    "nt_publicas_formas": frozenset({"NOTAS", "FIRMAS"}),
    "nt_comunicacoes_veiculo": frozenset({"NOTAS", "FIRMAS"}),
    "nt_reconhecimentos": frozenset({"FIRMAS", "NOTAS"}),
    "nt_autenticacoes": frozenset({"FIRMAS", "NOTAS"}),
    "nt_cartoes": frozenset({"FIRMAS", "NOTAS"}),
    "nt_sinais_reconhecimentos": frozenset({"FIRMAS", "NOTAS"}),
}


def atribuicoes_do_ato(tabela: Any) -> frozenset | None:
    """As atribuições de protocolo que pagam o selo desta tabela, ou None. Só calcula."""
    return ATRIBUICOES_DO_ATO.get(str(tabela or "").strip().lower())


#: O grupo da tabela do TJ de cada atribuição de protocolo — medido na
#: produção em 22/10/2026 (itens dos protocolos desde agosto): NOTAS e FIRMAS
#: 13, RCPN 14, RTD e RCPJ 15, RI 16, PROTESTO 17.
GRUPO_DA_ATRIBUICAO = {"NOTAS": "13", "FIRMAS": "13", "RCPN": "14", "RTD": "15",
                       "RCPJ": "15", "RI": "16", "PROTESTO": "17"}


def pedidos_padrao_do_ato(tabela: Any) -> list[tuple[str, int]]:
    """A família de códigos da tela que ainda não sabe o item exato. Só calcula.

    `[("14.*", 1)]` para o RCPN, por exemplo — o seletor mostra os protocolos
    com qualquer item do grupo, e a cobertura do selo continua conferindo o
    código exato quando o selo é pedido.
    """
    grupos = sorted({GRUPO_DA_ATRIBUICAO[a] for a in (atribuicoes_do_ato(tabela) or ())
                     if a in GRUPO_DA_ATRIBUICAO})
    return [(f"{g}.*", 1) for g in grupos]


def quantidade_do_envelope(dados: Any) -> int:
    """Quantas unidades o envelope pede (`quantidade`, folhas). Só calcula.

    Envelope sem o campo pede uma. A certidão do RI manda a folha acrescida
    (16.24.4.1) num selo só, com `quantidade` = folhas − 1.
    """
    for chave, valor in _percorrer(dados):
        if chave == "quantidade":
            try:
                return max(1, int(valor))
            except (TypeError, ValueError):
                return 1
    return 1


def candidatos_do_ato(con, *, tabela: Any, pedidos: Any,
                      pre_marcar_protocolo_id: Any = None,
                      hoje: Any = None) -> list[dict]:
    """Os protocolos que o escrevente pode escolher para pagar este ato. Só LÊ.

    É `caixa_protocolo.candidatos_para_o_selo` com a atribuição do ato — a
    mesma lista na tela do ato (macro `_protocolo_do_selo.html`) e no quadro.
    """
    import caixa_protocolo as CXP
    return CXP.candidatos_para_o_selo(
        con, pedidos, atribuicoes=atribuicoes_do_ato(tabela), hoje=hoje,
        pre_marcar_protocolo_id=pre_marcar_protocolo_id)


def seletor_do_ato(con, *, tabela: Any, usuario: Any, pedidos: Any = None,
                   hoje: Any = None) -> dict:
    """O que a macro `_protocolo_do_selo.html` precisa para esta tela. Só LÊ.

    `{"candidatos", "pedidos", "atendendo"}`. Com `pedidos`, a lista é a de
    `candidatos_do_ato`; sem eles, a família de códigos da atribuição
    (`pedidos_padrao_do_ato`), e as famílias valem como ALTERNATIVAS — a
    certidão do Livro 3 pode ser paga por item do RTD/RCPJ ou do RI, e um
    protocolo entra se pagar qualquer uma delas.
    """
    import caixa_protocolo as CXP
    atendendo = CXP.em_atendimento(con, usuario)
    pre = (atendendo or {}).get("id")
    explicitos = CXP.pedidos_do_selo(pedidos) if pedidos else []
    grupos = [explicitos] if explicitos else [[p] for p in pedidos_padrao_do_ato(tabela)]
    juntos: dict[int, dict] = {}
    for grupo in grupos:
        for c in candidatos_do_ato(con, tabela=tabela, pedidos=grupo,
                                   pre_marcar_protocolo_id=pre, hoje=hoje):
            ja = juntos.get(c["protocolo_id"])
            if not ja:
                juntos[c["protocolo_id"]] = c
                continue
            ids = {i["id"] for i in ja["itens"]}
            ja["itens"] += [i for i in c["itens"] if i["id"] not in ids]
            if c["cobre_tudo"] and not ja["cobre_tudo"]:
                ja["cobre_tudo"], ja["faltam"] = True, []
    lista = sorted(juntos.values(), key=lambda c: (not c["pre_marcado"],
                                                   not c["cobre_tudo"],
                                                   -c["protocolo_id"]))
    return {"candidatos": lista,
            "pedidos": explicitos or [p for g in grupos for p in g],
            "atendendo": dict(atendendo) if atendendo else None}


def escolher_protocolo_do_selo(con, *, usuario: Any, protocolo: Any,
                               agora: str) -> dict | None:
    """O protocolo que o escrevente ESCOLHEU na tela vira o «em atendimento». ESCREVE.

    `protocolo` é o id ou o número vindo do formulário; vazio não faz nada e
    devolve None (o atendimento que já havia continua). Quem chama grava a
    auditoria `SELO_PROTOCOLO_EM_ATENDIMENTO` FORA da transação (regra da
    casa), com o que esta função devolve. A cobertura continua pelo passo 3 de
    `cobrir_o_selo`: não há caminho novo de dinheiro, só o passo que faltava
    estar à vista.
    """
    import caixa_protocolo as CXP
    bruto = str(protocolo or "").strip()
    if not bruto:
        return None
    return CXP.atender(con, usuario=usuario, protocolo=bruto, agora=agora)


def _cobre_o_item(bd, it: dict, *, tabela: str, ato_id: int, usuario: Any,
                  agora: str) -> tuple[str, dict | None] | None:
    """Este item paga o selo? (forma, débito) ou None. Pode ESCREVER (débito)."""
    import caixa_depositos as DEP
    import caixa_protocolo as CXP
    if CXP.item_pago(it):
        return FORMA_ITEM_PAGO, None
    if tabela in CXP.TABELAS_QUE_DIFEREM and CXP.item_diferido(it):
        return FORMA_DIFERIDO, None
    pago = DEP.pagar_item(bd, it["id"], agora=agora, quem=usuario,
                          tabela=tabela, ato_id=ato_id)
    if pago and pago.get("ja_quitado"):
        return FORMA_ITEM_PAGO, None
    if pago:
        return FORMA_DEPOSITO, pago
    return None


def cobrir_o_selo(con, *, tabela: Any, ato_id: Any, referencia: Any,
                  dados: Any, usuario: Any, agora: str, cns: Any = None,
                  atribuicao: Any = None) -> dict:
    """O selo pago tem protocolo e dinheiro? RESERVA a cobertura. ESCREVE.

    Devolve `{"coberto": True, "forma": ..., "reserva": ...}` ou
    `{"coberto": False, "quadro": ...}`. O débito e a unidade já saem do
    saldo aqui, e a cobertura fica «RESERVADA»: quem a confirma ou estorna é
    `obter_selo`, depois do aparelho. A mesma referência pedida de novo não
    debita nem gasta outra unidade: a cobertura dela já está gravada. E a que
    está RESERVADA agora é de um pedido em voo — sobe `SeloEmAndamento`.
    """
    import caixa_protocolo as CXP
    bd = banco(con)
    if selo_e_gratuito(dados):
        return {"coberto": True, "forma": FORMA_GRATUITO}
    # A mesma grafia de `obter_selo`: chamada direta, sem passar por lá,
    # também não abre segunda cobertura para o mesmo ato. A procura é pela
    # canônica E pela crua (LX25) — a cobertura de antes do LX24 está na crua.
    grafias = grafias_da_referencia(referencia, tabela, ato_id)
    ref = grafias[0]
    # A TRAVA VEM ANTES DE OLHAR: dois pedidos da mesma referência ao mesmo
    # tempo leriam «sem cobertura» e debitariam duas vezes.
    bd.travar(f"cx_selo_coberturas:{ref}")
    ja = _cobertura_gravada(bd, grafias)
    if ja and ja["situacao"] == RESERVADA and _reserva_vencida(ja, agora):
        _resolver_reserva_orfa(bd, ja, agora=agora)
        ja = _cobertura_gravada(bd, grafias)
    if ja and ja["situacao"] == RESERVADA:
        raise SeloEmAndamento(
            "O selo deste ato já está sendo pedido ao selador (outro balcão ou "
            "outra aba). Espere o primeiro pedido terminar e confira o ato: "
            "pedir de novo agora gastaria o pagamento duas vezes. Se a máquina "
            "caiu no meio do pedido, o sistema desfaz a reserva sozinho em "
            f"{PRAZO_DA_RESERVA_EM_SEGUNDOS // 60} minutos.")
    if ja:
        return {"coberto": True, "forma": ja["forma"], "repetido": True}
    if _selo_ja_obtido(bd, cns=cns, atribuicao=atribuicao, referencias=grafias):
        return {"coberto": True, "forma": "JA_OBTIDO"}
    if e_certidao_eletronica_da_crc(bd, tabela, ato_id, dados):
        # O valor vem pela CRC, e não pelo caixa (22/10/2026).
        return _gravar_cobertura(bd, referencia=ref, tabela=tabela,
                                 ato_id=int(ato_id), forma=FORMA_CENTRAL_CRC,
                                 usuario=usuario, agora=agora)
    if not trava_ligada(bd):
        return _gravar_cobertura(bd, referencia=ref, tabela=tabela, ato_id=ato_id,
                                 forma=FORMA_TRAVA_DESLIGADA, usuario=usuario,
                                 agora=agora)
    if tabela is None or ato_id is None:
        return {"coberto": False, "quadro": _quadro_sem_ato(ref)}
    ato_id = int(ato_id)
    gravar = dict(referencia=ref, tabela=tabela, ato_id=ato_id,
                  usuario=usuario, agora=agora)
    # 1. o item ligado ao ato — POR CÓDIGO quando dá (22/10/2026). A certidão
    # do RI tem dois selos (16.24.4 e 16.24.4.1) com referências próprias:
    # ligado só o 16.24.4, o selo da folha acrescida passava por ele sem item
    # que o pagasse. Se nenhum item ligado tem o código do envelope — o ato
    # lavrado do RI, cujo envelope leva o `codigo_tj` do formulário —, vale
    # qualquer item ligado, como antes.
    ligados = CXP.itens_do_ato(bd, tabela, ato_id)
    codigo = codigo_do_envelope(dados)
    do_codigo = [it for it in ligados
                 if codigo and str(it.get("codigo_ato") or "").strip() == codigo]
    for it in (do_codigo or ligados):
        achou = _cobre_o_item(bd, it, tabela=tabela, ato_id=ato_id,
                              usuario=usuario, agora=agora)
        if achou:
            return _gravar_cobertura(bd, forma=achou[0], item=it,
                                     deposito=achou[1], **gravar)
    # 2. o lançamento do próprio ato
    lanc = _lancamento_do_ato(bd, tabela, ato_id)
    if lanc:
        return _gravar_cobertura(bd, forma=FORMA_LANCAMENTO, lancamento=lanc,
                                 **gravar)
    # 3. o protocolo em atendimento — as unidades que o envelope pede
    # (22/10/2026: era uma por selo, e a folha acrescida da certidão do RI
    # pede folhas − 1 num selo só; as outras ficavam «livres» para cobrir outro
    # ato). Gasta o que o envelope pede até o saldo, e nunca menos de uma —
    # cobrir com saldo menor que o pedido é o que já acontecia, e o que falta
    # volta em `parcial` para a tela dizer.
    pedidas = quantidade_do_envelope(dados)
    atendendo = CXP.em_atendimento(bd, usuario)
    if atendendo:
        for it in CXP.itens_para_o_selo(bd, atendendo["id"], codigo):
            # A LISTA FOI LIDA SEM PRENDER: outro ato do mesmo protocolo pode
            # ter gasto a última unidade entre ela e aqui. Prende o item e
            # confere o saldo de novo ANTES de pagar com o depósito — senão o
            # débito ficava num item que este selo não vai usar.
            bd._escrita()
            preso = bd.um("SELECT * FROM cx_protocolo_atos WHERE id = %s FOR UPDATE",
                          (int(it["id"]),))
            if not preso or CXP.saldo_do_item(preso) <= 0:
                continue
            it = it | dict(preso)
            achou = _cobre_o_item(bd, it, tabela=tabela, ato_id=ato_id,
                                  usuario=usuario, agora=agora)
            if not achou:
                continue
            gastas = CXP.consumir_item(bd, it["id"], ato_id=ato_id, tabela=tabela,
                                       agora=agora, quantas=pedidas,
                                       origem=CXP.ORIGEM_SELO, quem=usuario)
            if not gastas:
                # O ITEM ESTÁ PRESO DESDE A CONFERÊNCIA DO SALDO, e a unidade
                # não tinha como sumir. Se sumiu, o débito de cima NÃO pode
                # ficar sem o selo: a exceção desfaz a transação inteira.
                raise AtoError(
                    f"A unidade do item {it.get('codigo_ato') or ''} acabou "
                    f"enquanto o selo era coberto. Nada foi debitado: peça o "
                    f"selo de novo.")
            coberto = _gravar_cobertura(bd, forma=achou[0], item=it,
                                        deposito=achou[1], unidades=gastas,
                                        **gravar)
            if gastas < pedidas:
                coberto["parcial"] = {"codigo": codigo, "pedidas": pedidas,
                                      "gastas": gastas,
                                      "faltam": pedidas - gastas}
            return coberto
    # 4. a liberação do ADMIN — o «usado» só se grava quando o selo sai
    lib = _liberacao(bd, tabela, ato_id)
    if lib:
        return _gravar_cobertura(bd, forma=FORMA_LIBERADO, liberacao=lib, **gravar)
    quadro = quadro_para_selar(bd, tabela=tabela, ato_id=ato_id,
                               usuario=usuario, dados=dados)
    return {"coberto": False, "quadro": quadro,
            "faltam": quadro.get("faltam") or []}


#: Por que o selo pago precisa saber de que ato é.
POR_QUE_REFERENCIA = ("sem o ato, o caixa não acha o protocolo nem o pagamento "
                      "dele — e liberar às cegas seria selo pago sem dinheiro.")


def _quadro_sem_ato(referencia: str) -> dict:
    """O quadro do pedido que não diz de que ato é. Só calcula.

    Não é falta do escrevente — é a tela ou o robô que mandou a referência
    fora da forma `tabela:número`. O quadro diz o que chegou e onde se
    resolve, em vez de pedir um protocolo que não teria a que se ligar.
    """
    return {"titulo": TITULO_DO_QUADRO, "pode_selar": False, "gratuito": False,
            "sem_ato": True,
            "itens": [_linha(False,
                             f"Dizer de que ato é este selo: o pedido chegou com "
                             f"a referência «{referencia}», e não com "
                             f"«tabela:número do ato».",
                             POR_QUE_REFERENCIA, "Selar pela tela do ato",
                             "selar_pela_tela")]}


# --------------------------------------------- a reserva: confirmar ou estornar


def _reserva_vencida(reserva: dict, agora: str) -> bool:
    """A reserva é de um pedido que caiu no meio? Só calcula.

    A conta é no Python (regra da casa). Data que não se lê conta como
    vencida: reserva sem hora não é de pedido nenhum em voo.
    """
    from datetime import datetime
    try:
        feita = datetime.fromisoformat(str(reserva.get("criado_em") or "")[:19])
        hoje = datetime.fromisoformat(str(agora or "")[:19])
    except ValueError:
        return True
    return (hoje - feita).total_seconds() >= PRAZO_DA_RESERVA_EM_SEGUNDOS


def _reserva_presa(bd, reserva: dict | None) -> dict | None:
    """A linha da reserva, presa, se ainda está RESERVADA. ESCREVE (trava).

    A trava é a mesma de `cobrir_o_selo`, e vem antes da linha: confirmar,
    estornar e cobrir a mesma referência ficam um de cada vez.
    """
    if not reserva:
        return None
    if not bd.tem_tabela("cx_selo_coberturas"):
        return reserva if reserva.get("situacao") == RESERVADA else None
    bd.travar(f"cx_selo_coberturas:{reserva['referencia']}")
    bd._escrita()
    linha = bd.um("""SELECT * FROM cx_selo_coberturas
                      WHERE referencia = %s FOR UPDATE""", (reserva["referencia"],))
    return linha if linha and linha["situacao"] == RESERVADA else None


def _confirmar_reserva(con, reserva: dict | None, *, agora: str) -> bool:
    """O selo saiu: a reserva vira cobertura de verdade. ESCREVE.

    Vai na MESMA transação que grava o selo no razão — os dois ficam, ou
    nenhum. Devolve False quando não havia o que confirmar (selo gratuito,
    repetido, já obtido, ou reserva que a conferência das órfãs desfez — e
    aí o selo cai no relatório dos pagos sem cobertura, que é onde deve estar).
    """
    bd = banco(con)
    linha = _reserva_presa(bd, reserva)
    if not linha:
        return False
    if linha.get("forma") == FORMA_LIBERADO and linha.get("liberacao_id"):
        bd.escrever(
            """UPDATE cx_selo_liberacoes SET usado_em = coalesce(usado_em, %s),
                      usado_por = coalesce(usado_por, %s) WHERE id = %s""",
            (agora, linha.get("usuario"), int(linha["liberacao_id"])))
    if bd.tem_tabela("cx_selo_coberturas"):
        bd.escrever(
            """UPDATE cx_selo_coberturas SET situacao = %s, confirmada_em = %s
                WHERE referencia = %s""",
            (CONFIRMADA, agora, linha["referencia"]))
    return True


def _devolver_ao_deposito(bd, linha: dict, *, agora: str, motivo: str) -> None:
    """O débito da reserva volta ao depósito, e o item deixa de estar quitado.

    O espelho de `caixa_depositos.pagar_item`, com o mesmo cuidado: o
    depósito é lido com a linha presa, e o estorno fica em
    `cx_deposito_usos` como uma linha de valor negativo — o débito continua
    lá, e quem soma os usos chega ao saldo certo.

    PRENDE O ITEM ANTES DO DEPÓSITO (revisão do LX21a), na ordem de
    `pagar_item`. Ao contrário, o balcão que estorna (depósito → item) e o
    que cobre outro ato do mesmo protocolo (item → depósito) se esperavam um
    ao outro, e o PostgreSQL derrubava um dos dois por deadlock — a trava
    única da ponte só escondia isso.
    """
    import caixa_protocolo as CXP
    from caixa_schema import centavos, reais
    valor = int(linha.get("valor_centavos") or 0)
    if valor <= 0:
        return
    bd._escrita()
    item = (bd.um("SELECT * FROM cx_protocolo_atos WHERE id = %s FOR UPDATE",
                  (int(linha["item_id"]),))
            if linha.get("item_id") else None)
    d = bd.um("SELECT * FROM cx_depositos WHERE id = %s FOR UPDATE",
              (int(linha["deposito_id"]),))
    if d:
        novo = centavos(d["saldo"]) + valor
        bd.escrever(
            """UPDATE cx_depositos SET saldo = %s, encerrado = 0, atualizado_em = %s
                WHERE id = %s""", (reais(novo), agora, int(d["id"])))
        if bd.tem_tabela("cx_deposito_usos"):
            bd.escrever(
                """INSERT INTO cx_deposito_usos
                       (deposito_id, valor_centavos, saldo_depois_centavos,
                        protocolo_id, item_id, tabela, ato_id, motivo,
                        criado_em, criado_por)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (int(d["id"]), -valor, novo, linha.get("protocolo_id"),
                 linha.get("item_id"), linha.get("tabela"), linha.get("ato_id"),
                 f"Estorno da reserva do selo {linha['referencia']}: {motivo}",
                 agora, linha.get("usuario")))
    # Só desfaz a quitação que o depósito fez: a do caixa não é desta reserva.
    if item and str(item.get("quitado_por") or "").startswith("DEPÓSITO PRÉVIO"):
        bd.escrever(
            """UPDATE cx_protocolo_atos
                  SET quitado = 0, quitado_em = NULL, quitado_por = NULL
                WHERE id = %s""", (int(item["id"]),))
        CXP.atualizar_situacao(bd, item["protocolo_id"])


def _devolver_a_unidade(bd, linha: dict) -> None:
    """A unidade que a trava gastou volta ao item, e o rastro dela sai."""
    import caixa_protocolo as CXP
    unidades = int(linha.get("unidades_gastas") or 0)
    if unidades <= 0 or not linha.get("item_id"):
        return
    CXP.devolver_item(bd, int(linha["item_id"]), quantas=unidades)
    if bd.tem_tabela("cx_item_do_ato") and linha.get("ato_id") is not None:
        chave = (str(linha["tabela"]), int(linha["ato_id"]), int(linha["item_id"]),
                 CXP.ORIGEM_SELO)
        bd.escrever(
            """UPDATE cx_item_do_ato SET unidades = unidades - %s
                WHERE tabela = %s AND ato_id = %s AND item_id = %s AND origem = %s""",
            (unidades, *chave))
        bd.escrever(
            """DELETE FROM cx_item_do_ato
                WHERE tabela = %s AND ato_id = %s AND item_id = %s AND origem = %s
                  AND unidades <= 0""", chave)


def _estornar_reserva(con, reserva: dict | None, *, agora: str,
                      motivo: str) -> bool:
    """O selo NÃO saiu: o débito e a unidade voltam, e a reserva sai. ESCREVE.

    O rastro fica em `audit_logs` («SELO_RESERVA_ESTORNADA», com o depósito,
    o valor, o item e o porquê). A linha da cobertura sai para a referência
    poder ser coberta de novo — `referencia` é única. Devolve False quando
    não havia reserva em aberto.
    """
    bd = banco(con)
    linha = _reserva_presa(bd, reserva)
    if not linha:
        return False
    if linha.get("forma") == FORMA_DEPOSITO and linha.get("deposito_id"):
        _devolver_ao_deposito(bd, linha, agora=agora, motivo=motivo)
    _devolver_a_unidade(bd, linha)
    if bd.tem_tabela("cx_selo_coberturas"):
        bd.escrever("DELETE FROM cx_selo_coberturas WHERE referencia = %s",
                    (linha["referencia"],))
    if bd.tem_tabela("audit_logs"):
        _auditar(bd, acao="SELO_RESERVA_ESTORNADA", usuario=linha.get("usuario"),
                 usuario_id=None, agente="estorno da reserva do selo",
                 entidade=linha.get("tabela") or "SELO",
                 entidade_id=linha.get("ato_id"),
                 detalhes={"referencia": linha["referencia"],
                           "forma": linha.get("forma"),
                           "deposito_id": linha.get("deposito_id"),
                           "valor_centavos": linha.get("valor_centavos"),
                           "item_id": linha.get("item_id"),
                           "unidades": linha.get("unidades_gastas"),
                           "motivo": motivo},
                 agora=agora)
    return True


def _estornar_sem_estourar(con, reserva: dict | None, *, agora: str,
                           motivo: str) -> None:
    """Estorna e confirma já — chamado com a falha do aparelho na mão.

    Se o próprio estorno falhar (o banco caiu junto), quem sobe é a falha do
    aparelho, que é a que o escrevente precisa ler; a reserva fica para
    `estornar_reservas_orfas`, que a acha pelo prazo.
    """
    try:
        _estornar_reserva(con, reserva, agora=agora, motivo=motivo)
        con.commit()
    except Exception:                                          # noqa: BLE001
        # O rastro do estorno que falhou fica no log: sem ele, a reserva só
        # reaparecia na conferência das órfãs, sem ninguém saber por quê.
        _LOG.exception("estorno da reserva do selo %s falhou; fica para a "
                       "conferência das órfãs", (reserva or {}).get("referencia"))
        try:
            con.rollback()
        except Exception:                                      # noqa: BLE001
            pass


def _resolver_reserva_orfa(bd, linha: dict, *, agora: str) -> str:
    """Reserva de pedido que caiu no meio: o selo saiu ou não? ESCREVE.

    O razão responde. Selo da referência em `sd_selos` (e não cancelado) é
    selo que saiu — a reserva se confirma; sem ele, estorna. Os dois deixam
    rastro em `audit_logs`.
    """
    saiu = bd.tem_tabela("sd_selos") and bool(bd.valor(
        """SELECT count(*) AS n FROM sd_selos
            WHERE referencia = %s AND cancelado_em IS NULL""",
        (linha["referencia"],)))
    if saiu:
        if _confirmar_reserva(bd, linha, agora=agora) and bd.tem_tabela("audit_logs"):
            _auditar(bd, acao="SELO_RESERVA_CONFIRMADA_NA_CONFERENCIA",
                     usuario=linha.get("usuario"), usuario_id=None,
                     agente="conferência das reservas órfãs do selo",
                     entidade=linha.get("tabela") or "SELO",
                     entidade_id=linha.get("ato_id"),
                     detalhes={"referencia": linha["referencia"],
                               "forma": linha.get("forma")}, agora=agora)
        return CONFIRMADA
    _estornar_reserva(bd, linha, agora=agora,
                      motivo="o pedido do selo caiu no meio (reserva órfã)")
    return "ESTORNADA"


def estornar_reservas_orfas(con, *, agora: str) -> list[dict]:
    """Confere as reservas de pedidos que caíram no meio. ESCREVE.

    Roda na subida (`init_trava_do_selo_schema`) e antes de cada pedido de
    selo (`obter_selo`) — a consulta é pelo índice das reservadas, e quase
    sempre não acha nada. Só toca na reserva mais velha que
    `PRAZO_DA_RESERVA_EM_SEGUNDOS`: a mais nova é de um pedido em voo.
    Devolve o que fez, uma linha por reserva.
    """
    bd = banco(con)
    if not bd.tem_tabela("cx_selo_coberturas"):
        return []
    feitas = []
    for r in bd.ler("""SELECT * FROM cx_selo_coberturas WHERE situacao = %s
                        ORDER BY criado_em, id""", (RESERVADA,)):
        if not _reserva_vencida(r, agora):
            continue
        feitas.append({"referencia": r["referencia"],
                       "resultado": _resolver_reserva_orfa(bd, r, agora=agora)})
    return feitas


def _conferir_as_orfas(db, *, agora: str) -> None:
    """`estornar_reservas_orfas` antes do pedido, na transação DELA. ESCREVE.

    Fora da transação da cobertura por duas razões. A cobertura que não
    cobre volta inteira (LX20) — e levaria junto o estorno da órfã, que
    ficaria refeito e desfeito a cada pedido. E uma falha aqui (banco antigo,
    reserva com dado torto) não pode impedir selo nenhum: a órfã espera a
    próxima conferência, e o erro fica no log.

    A pergunta vem antes, sem transação: quase sempre não há órfã, e abrir
    uma transação a cada selo seria pegar a trava única da ponte à toa.
    """
    try:
        with db.connect() as con:
            bd = banco(con)
            vencidas = bd.tem_tabela("cx_selo_coberturas") and any(
                _reserva_vencida(r, agora) for r in bd.ler(
                    """SELECT criado_em FROM cx_selo_coberturas
                        WHERE situacao = %s ORDER BY criado_em, id""",
                    (RESERVADA,)))
        if not vencidas:
            return
        with db.transaction() as con:
            estornar_reservas_orfas(con, agora=agora)
    except Exception:                                          # noqa: BLE001
        _LOG.exception("conferência das reservas órfãs do selo falhou")


def _linha(ok: bool, texto: str, porque: str = "", botao: str | None = None,
           acao: str | None = None) -> dict:
    return {"ok": bool(ok), "marca": "✓" if ok else "✗", "texto": texto,
            "porque": porque, "botao": botao, "acao": acao}


def quadro_para_selar(con, *, tabela: Any, ato_id: Any, usuario: Any = None,
                      dados: Any = None) -> dict:
    """«Para selar este ato falta:» — item por item, com o botão de cada um. Só LÊ.

    É o mesmo quadro na tela do ato, na tela da cobertura e no recado que a
    rota mostra quando o selo não sai: o escrevente lê o que falta e onde se
    resolve, sem erro técnico.
    """
    import caixa_depositos as DEP
    import caixa_protocolo as CXP
    from caixa_schema import reais
    bd = banco(con)
    if selo_e_gratuito(dados):
        return {"titulo": TITULO_DO_QUADRO, "pode_selar": True, "gratuito": True,
                "itens": [_linha(True, "Ato gratuito: sela sem pagamento."),
                          _linha(True, f"Depois do ato, junte {O_QUE_VAI_NO_PDF}.",
                                 POR_QUE_GRATUITO, "Juntar o comprovante",
                                 "comprovante")]}
    itens: list[dict] = []
    if not trava_ligada(bd):
        return {"titulo": TITULO_DO_QUADRO, "pode_selar": True, "gratuito": False,
                "itens": [_linha(True, "A trava do selo está desligada pelo oficial.")]}
    ligados = (CXP.itens_do_ato(bd, tabela, int(ato_id))
               if tabela and ato_id is not None else [])
    lanc = (_lancamento_do_ato(bd, tabela, int(ato_id))
            if tabela and ato_id is not None else None)
    atendendo = CXP.em_atendimento(bd, usuario)
    candidatos = (CXP.itens_para_o_selo(bd, atendendo["id"], codigo_do_envelope(dados))
                  if atendendo else [])
    liberado = (_liberacao(bd, tabela, int(ato_id))
                if tabela and ato_id is not None else None)
    possiveis = ligados + candidatos

    # 1. o protocolo
    if ligados:
        itens.append(_linha(True, f"Protocolo {ligados[0]['protocolo_numero']} "
                                  f"ligado ao ato."))
    elif lanc:
        itens.append(_linha(True, "O ato foi lançado no caixa com protocolo."))
    elif candidatos:
        itens.append(_linha(True, f"Protocolo em atendimento: "
                                  f"{atendendo['numero']} (item "
                                  f"{candidatos[0].get('codigo_ato') or ''})."))
    elif atendendo:
        codigo = codigo_do_envelope(dados)
        itens.append(_linha(
            False, f"O protocolo {atendendo['numero']} não tem item "
                   f"{codigo or 'deste serviço'} com unidade sobrando.",
            POR_QUE_PROTOCOLO, "Abrir protocolo", "abrir_protocolo"))
    else:
        itens.append(_linha(False, "Ligar o ato a um protocolo do balcão.",
                            POR_QUE_PROTOCOLO, "Abrir protocolo",
                            "abrir_protocolo"))

    # 2. o dinheiro
    pago = bool(lanc) or any(CXP.item_pago(i) for i in possiveis) or any(
        tabela in CXP.TABELAS_QUE_DIFEREM and CXP.item_diferido(i)
        for i in possiveis)
    if pago:
        itens.append(_linha(True, "Pagamento registrado no caixa."))
    elif possiveis:
        alvo = possiveis[0]
        saldo = DEP.saldo_do_protocolo(bd, alvo["protocolo_id"], tabela=tabela,
                                       ato_id=ato_id)
        itens.append(_linha(False, f"Registrar o pagamento do item "
                                   f"{alvo.get('codigo_ato') or ''} do protocolo "
                                   f"{alvo.get('protocolo_numero') or ''}.",
                            POR_QUE_PAGAMENTO, "Registrar pagamento",
                            "registrar_pagamento"))
        if saldo > 0:
            itens.append(_linha(False, "Ou usar o depósito prévio do protocolo.",
                                "o dinheiro já entrou antes: o item é pago com ele.",
                                f"Usar depósito prévio (saldo R$ {reais(saldo)})",
                                "usar_deposito"))
        if tabela in CXP.TABELAS_QUE_DIFEREM:
            itens.append(_linha(False, "Ou registrar o diferimento (a posteriori / CRA).",
                                "a lei manda o devedor pagar no fim: diga quem paga e quando.",
                                "Registrar diferimento", "diferir"))
    else:
        itens.append(_linha(False, "Registrar o pagamento no caixa.",
                            POR_QUE_PAGAMENTO, "Registrar pagamento",
                            "registrar_pagamento"))
    if liberado:
        itens.append(_linha(True, "Liberado pelo oficial — o pagamento continua "
                                  "pendente."))
    pode = all(i["ok"] for i in itens[:2]) or bool(liberado)
    # OS CANDIDATOS E O QUE FALTA (22/10/2026): o quadro passa a mostrar os
    # protocolos pagos da atribuição do ato, para o escrevente escolher um e
    # pedir o selo de novo — em vez de mandá-lo procurar o «Atender» noutra
    # tela. E `faltam` diz, por código, quantas unidades pagas faltam.
    codigo = codigo_do_envelope(dados)
    pedidos = [(codigo, quantidade_do_envelope(dados))] if codigo else []
    candidatos: list[dict] = []
    faltam: list[dict] = []
    if not pode and pedidos:
        candidatos = candidatos_do_ato(
            bd, tabela=tabela, pedidos=pedidos,
            pre_marcar_protocolo_id=(atendendo or {}).get("id"))
        do_atendido = next((c for c in candidatos if atendendo
                            and c["protocolo_id"] == int(atendendo["id"])), None)
        faltam = (do_atendido["faltam"] if do_atendido else
                  [{"codigo": c, "pedidas": q, "saldo_pago": 0, "saldo": 0,
                    "faltam": q} for c, q in pedidos])
    return {"titulo": TITULO_DO_QUADRO, "pode_selar": pode, "gratuito": False,
            "itens": itens, "pedidos": pedidos, "candidatos": candidatos,
            "faltam": faltam}


def recado_da_cobertura(quadro: dict) -> str:
    """O quadro em uma frase, para as telas que só mostram o motivo."""
    faltas = [i for i in (quadro or {}).get("itens", []) if not i["ok"]]
    if (quadro or {}).get("sem_ato") and faltas:
        # Não há o que resolver em «Selo e caixa»: falta a tela mandar o ato.
        return (f"O selo não foi pedido. {TITULO_DO_QUADRO} "
                f"✗ {faltas[0]['texto'].rstrip('.')}. Por quê: {faltas[0]['porque']} "
                f"Peça o selo pela tela do ato, que manda a referência certa.")
    if not faltas:
        return "O selo não foi pedido: o ato está aguardando cobertura."
    linhas = "; ".join(f"✗ {i['texto'].rstrip('.')}" for i in faltas)
    porques = []
    for i in faltas:
        if i["porque"] and i["porque"] not in porques:
            porques.append(i["porque"])
    return (f"O selo não foi pedido — o ato está aguardando cobertura. "
            f"{TITULO_DO_QUADRO} {linhas}. Por quê: {' '.join(porques)} "
            f"Resolva em «Selo e caixa» e peça o selo de novo.")


def _marcar_aguardando(con, *, tabela: Any, ato_id: Any, motivo: str,
                       usuario: Any, agora: str) -> None:
    if tabela is None or ato_id is None or not banco(con).tem_tabela("cx_selo_aguardando"):
        return
    banco(con).escrever(
        """INSERT INTO cx_selo_aguardando (tabela, ato_id, motivo, usuario,
                                           desde, atualizado_em)
           VALUES (%s,%s,%s,%s,%s,%s)
           ON CONFLICT (tabela, ato_id) DO UPDATE
              SET motivo = EXCLUDED.motivo, usuario = EXCLUDED.usuario,
                  atualizado_em = EXCLUDED.atualizado_em""",
        (tabela, int(ato_id), motivo, usuario, agora, agora))


def _tirar_aguardando(con, *, tabela: Any, ato_id: Any) -> None:
    if tabela is None or ato_id is None or not banco(con).tem_tabela("cx_selo_aguardando"):
        return
    banco(con).escrever(
        "DELETE FROM cx_selo_aguardando WHERE tabela = %s AND ato_id = %s",
        (tabela, int(ato_id)))


def aguardando_cobertura(con, limite: int = 200) -> list[dict]:
    """Os atos que ficaram sem selo por falta de protocolo ou pagamento. Só LÊ.

    Ato que a tela desfez depois (o reconhecimento sem selo não fica de pé)
    sai da lista: não há o que selar.
    """
    bd = banco(con)
    saida = []
    for r in bd.ler("""SELECT * FROM cx_selo_aguardando
                        ORDER BY desde, tabela, ato_id LIMIT %s""", (int(limite),)):
        if r["tabela"] in TABELAS_DE_ATO and bd.um(
                f"SELECT id FROM {r['tabela']} WHERE id = %s", (int(r["ato_id"]),)):
            saida.append(r)
    return saida


def cobertura_de_verdade(con, tabela: str, ato_id: int) -> bool:
    """O ato tem dinheiro (ou diferimento) registrado? Só LÊ.

    É a pergunta da pendência: liberação e trava desligada deixam o selo sair,
    mas só isto fecha a cobrança.
    """
    import caixa_protocolo as CXP
    bd = banco(con)
    formas = sorted(FORMAS_QUE_COBREM)
    # A RESERVA NÃO CONTA: é selo em voo, que pode ser estornado.
    if bd.valor(f"""SELECT count(*) AS n FROM cx_selo_coberturas
                     WHERE tabela = %s AND ato_id = %s AND situacao = %s
                       AND forma IN ({', '.join(['%s'] * len(formas))})""",
                (tabela, int(ato_id), CONFIRMADA, *formas)):
        return True
    for it in CXP.itens_do_ato(bd, tabela, int(ato_id)):
        if CXP.item_pago(it) or (tabela in CXP.TABELAS_QUE_DIFEREM
                                 and CXP.item_diferido(it)):
            return True
    return bool(_lancamento_do_ato(bd, tabela, int(ato_id)))


def liberados_sem_cobertura(con) -> list[dict]:
    """A lista do gestor: selos que o ADMIN liberou e que ainda não foram pagos."""
    bd = banco(con)
    saida = []
    for lib in bd.ler("SELECT * FROM cx_selo_liberacoes ORDER BY liberado_em, id"):
        if cobertura_de_verdade(bd, lib["tabela"], lib["ato_id"]):
            continue
        selos = bd.ler("""SELECT numero, obtido_por, obtido_em FROM sd_selos
                           WHERE tabela = %s AND ato_id = %s AND cancelado_em IS NULL
                           ORDER BY id""", (lib["tabela"], int(lib["ato_id"])))
        saida.append(lib | {
            "rotulo": TABELAS_DE_ATO.get(lib["tabela"], lib["tabela"]),
            "selos": [s["numero"] for s in selos],
            "obtido_por": (selos[0]["obtido_por"] if selos else lib["usado_por"])})
    return saida


def _mesma_pessoa(a: Any, alvos: set[str]) -> bool:
    import unicodedata
    def norm(s):
        return "".join(c for c in unicodedata.normalize("NFD", str(s or ""))
                       if unicodedata.category(c) != "Mn").strip().lower()
    return norm(a) in {norm(x) for x in alvos} - {""}


def pagamentos_pendentes(con, *, nome: Any, username: Any = "") -> list[dict]:
    """O que esta pessoa selou liberado e ainda não foi pago — a cobrança dela."""
    alvos = {str(nome or ""), str(username or "")}
    return [lib for lib in liberados_sem_cobertura(con)
            if _mesma_pessoa(lib["obtido_por"], alvos)]


def desde_da_conferencia(con) -> str:
    import re
    valor = _ler_setting(banco(con), CHAVE_DESDE_DA_CONFERENCIA)
    return valor[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", valor) else DESDE_DA_CONFERENCIA_PADRAO


def selos_pagos_sem_cobertura(con, desde: str | None = None,
                              limite: int = 500) -> list[dict]:
    """Relatório do oficial: selo pago sem protocolo ou sem pagamento. Só LÊ.

    Os de ANTES desta versão não travaram nada — saíram como sempre saíram —,
    e é por isso que existe a lista: conferir a partir de uma data. O selo
    isento não entra (é a outra lista, a do comprovante).

    O LIMITE É DE SELOS SEM COBERTURA, e não de selos lidos (LX20, revisão
    do LX16). Cortar a leitura em 500 e só depois tirar os cobertos deixava
    os 500 mais antigos — quase todos pagos — ocuparem a lista, e o selo sem
    pagamento que veio depois sumia do relatório que existe para achá-lo.
    Por isso se lê de página em página, pela mesma ordem, até juntar
    `limite` descobertos. Quem quer saber se ficou algum de fora pede
    `limite + 1` (a tela da conferência faz assim).
    """
    bd = banco(con)
    inicio = (desde or desde_da_conferencia(bd))[:10]
    limite = max(1, int(limite))
    pagina = max(limite, 200)
    saida: list[dict] = []
    depois = None           # (obtido_em, id) do último selo lido
    while len(saida) < limite:
        filtro, args = "", [inicio, "%Selo Isento%"]
        if depois:
            filtro = "AND (obtido_em, id) > (%s, %s)"
            args += list(depois)
        lidos = bd.ler(
            f"""SELECT id, numero, tabela, ato_id, atribuicao, obtido_em, obtido_por
                  FROM sd_selos
                 WHERE obtido_em >= %s AND cancelado_em IS NULL
                   AND coalesce(texto, '') NOT ILIKE %s {filtro}
                 ORDER BY obtido_em, id LIMIT %s""",
            (*args, pagina))
        for s in lidos:
            if s["tabela"] and s["ato_id"] is not None and cobertura_de_verdade(
                    bd, s["tabela"], s["ato_id"]):
                continue
            saida.append(s | {"rotulo": TABELAS_DE_ATO.get(s["tabela"] or "", "sem ato")})
            if len(saida) >= limite:
                break
        if len(lidos) < pagina:
            break
        depois = (lidos[-1]["obtido_em"], lidos[-1]["id"])
    return saida
