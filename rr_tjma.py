"""Retificação, restauração e suprimento no Registro Civil — arts. 348 a 355.

    «o cartório está precisando do sistema pronto e amadurecido para o quanto
     antes» — o oficial

OS TRÊS INSTITUTOS NÃO SÃO A MESMA COISA, e o balcão os confunde
    **retificação** corrige o que está errado; **restauração** reconstitui o que
    foi danificado ou extraviado; **suprimento** lança o que falta. Um menu que
    os juntasse num «corrigir assento» faria o escrevente escolher o caminho
    errado — e cada um tem requisito e fundamento próprios.

O QUE ESTE MÓDULO É
    A norma **lida no PDF que está na casa**, com o artigo ao lado de cada regra.
    Ele **não decide nada**: é a régua que a tela consulta. É a forma de
    `us_tjma.py` e `rt_tjma.py`.

A REGRA QUE MUDA O DESENHO INTEIRO
    **A consulta à CRC é condição de validade da decisão** (art. 348, § 2º).
    Até aqui, neste projeto, a CRC era destino de carga e de comunicação; aqui
    ela é o que a norma exige **antes** de decidir. Decidir sem consultar é
    decidir sem o que a norma manda — e o motivo é o art. 365: a duplicidade de
    assentos, que quando aparece manda comunicar ao juiz corregedor com bloqueio
    cautelar do registro mais recente.

E A REGRA QUE MUDA O ATO
    **§ 4º: o deferido lança-se NO LIVRO CORRENTE**, e não no livro antigo, «com
    as devidas anotações e remissões recíprocas ao assento original, caso
    existente». Quem lançasse no livro velho estaria escrevendo em livro
    encerrado; quem lançasse no corrente sem a remissão deixaria dois assentos
    da mesma pessoa sem um apontar para o outro — que é como nasce a
    duplicidade que o art. 365 manda bloquear.
"""
from __future__ import annotations

from typing import Any


class RetificacaoRcpnError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


SECAO = "Código de Normas do TJMA — arts. 348 a 355"
FONTE = ("lido no «Código de normas TJMA atualizado.pdf», que está na casa — e "
         "não de memória")


# ------------------------------------------------------------ os tres institutos
#
# **NAO SAO A MESMA COISA**, e o requisito de cada um e diferente. Junta-los
# faria o escrevente escolher o caminho errado no balcao.
INSTITUTOS: tuple[dict, ...] = (
    {"chave": "RETIFICACAO",
     "nome": "Retificação",
     "o_que": "corrigir o que está errado no assento, na averbação ou na "
              "anotação",
     "artigo": "art. 352",
     "requisito": "erro que não exija indagação, ou erro na transposição de "
                  "ordem, mandado, termo, requerimento ou outro título"},
    {"chave": "RESTAURACAO",
     "nome": "Restauração",
     "o_que": "reconstituir o assento danificado ou extraviado",
     "artigo": "art. 348",
     "requisito": "prova documental suficiente para reconstituir os dados"},
    {"chave": "SUPRIMENTO",
     "nome": "Suprimento",
     "o_que": "lançar o assento que falta",
     "artigo": "art. 348",
     "requisito": "prova documental suficiente para reconstituir os dados"},
)

CHAVES = tuple(x["chave"] for x in INSTITUTOS)


# ------------------------------------------------------ como o pedido comeca
#
# § 1o, e sao TRES formas. **A VERBAL IMPORTA PARA O BALCAO**: quem chega dizendo
# «meu nome esta errado na certidao» esta formulando um requerimento, e a norma
# manda reduzi-lo a termo NA HORA — e nao mandar a pessoa voltar com peticao.
FORMAS_DO_PEDIDO: tuple[dict, ...] = (
    {"chave": "ESCRITO", "inciso": "I",
     "nome": "Escrito, com a assinatura física do requerente", "exige": ""},
    {"chave": "ELETRONICO", "inciso": "II",
     "nome": "Eletrônico, pelas centrais de serviços eletrônicos "
             "compartilhados ou com assinatura digital ICP-Brasil",
     "exige": ""},
    {"chave": "VERBAL", "inciso": "III",
     "nome": "Verbal, reduzido a termo",
     "exige": "deverá ser **imediatamente** reduzido a termo pelo oficial ou "
              "preposto, colhendo-se a assinatura do declarante — sem o termo "
              "assinado o pedido não existe no papel"},
)

FORMAS = tuple(x["chave"] for x in FORMAS_DO_PEDIDO)

# QUEM PODE ASSINAR A PETICAO — art. 352, redacao do Provimento no 8/2023.
# **Nao e so o interessado**, e recusar a procuracao no balcao seria negar o que
# a norma permite.
QUEM_ASSINA = ("o próprio interessado", "representante legal", "procurador")


# ------------------------------------------------------------------- os prazos
#
# DIAS UTEIS PORQUE O ARTIGO QUALIFICA (§ 3o: «10 (dez) dias uteis»). Onde ele
# nao qualifica — como o art. 253, § 2o da FUNAI, que diz «imediatamente» — nao
# se empresta a folga do dia util.
PRAZO_DECISAO_DIAS_UTEIS = 10

# «DEVIDAMENTE INSTRUIDO» E A CONDICAO, e nao enfeite: o relogio conta do
# protocolo COMPLETO. Um sistema que contasse da chegada poria o oficial em
# atraso por falta de documento que o requerente ainda nao trouxe.
DE_QUANDO_CONTA = ("do protocolo do requerimento **devidamente instruído** "
                   "(art. 348, § 3º) — e não do dia em que o interessado "
                   "apareceu")

# OS PRAZOS DO CAMINHO JUDICIAL, que sao do JUIZ e nao da serventia. Estao aqui
# para o balcao saber responder «e quanto tempo demora?», e nao para o sistema
# controla-los.
PRAZOS_JUDICIAIS: tuple[dict, ...] = (
    {"artigo": "art. 349, § 2º", "dias": 5,
     "o_que": "o juiz decide após a oitiva do Ministério Público e dos "
              "eventuais interessados, em prazo que corre em cartório"},
    {"artigo": "art. 349, § 3º", "dias": 10,
     "o_que": "havendo impugnação, o juiz determina a produção da prova"},
    {"artigo": "art. 349, § 3º", "dias": 3,
     "o_que": "ouvidos sucessivamente os interessados e o Ministério Público"},
    {"artigo": "art. 350", "dias": 5,
     "o_que": "**sem impugnação nem necessidade de mais provas**, o juiz decide"},
)


# --------------------------------------------------- a conferencia obrigatoria
CONSULTA_CRC = {
    "artigo": "art. 348, § 2º",
    "texto": ("Antes de proferir a decisão, o oficial deverá realizar consulta "
              "obrigatória à Central de Informações de Registro Civil (CRC) "
              "para verificar a eventual existência de duplicidade ou a prévia "
              "lavratura do ato em outra serventia."),
    "por_que": ("é **condição de validade da decisão**, e não zelo: decidir sem "
                "consultar é decidir sem o que a norma exige"),
    "se_achar": ("o art. 365 manda comunicar **imediatamente** ao juiz "
                 "corregedor, com bloqueio cautelar do registro mais recente"),
}


# ------------------------------------------- onde o deferido e lancado (§ 4o)
#
# **E A REGRA QUE MUDA O ATO, e o balcao erraria os dois lados.** Lancar no livro
# antigo seria escrever em livro encerrado; lancar no corrente sem a remissao
# deixaria dois assentos da mesma pessoa sem um apontar para o outro — que e
# como nasce a duplicidade que o art. 365 manda bloquear.
ONDE_SE_LANCA = {
    "artigo": "art. 348, § 4º",
    "livro": "o livro **corrente em uso na serventia**",
    "pode_ser": ("parcial", "total"),
    "remissoes": ("efetuando-se as devidas anotações e **remissões recíprocas** "
                  "ao assento original, caso existente"),
}

# E A AVERBACAO DA RETIFICACAO DEFERIDA — art. 355, com o que ela tem de dizer.
AVERBACAO_DA_RETIFICACAO = {
    "artigo": "art. 355",
    "onde": "à margem do registro",
    "menciona": ("o número do protocolo",
                 "a data da sentença e o seu trânsito em julgado, quando for "
                 "o caso"),
}


# ------------------------------------------------- o que o oficial faz sozinho
#
# **SAO DUAS HIPOTESES, E ELAS SAO ESTREITAS DE PROPOSITO.** Fora delas o caminho
# e o judicial (art. 349), e oferecer o administrativo para o que nao cabe faria
# o oficial decidir o que nao e dele.
HIPOTESES_DO_ART_352: tuple[dict, ...] = (
    {"inciso": "I",
     "texto": "erros que não exijam qualquer indagação para a constatação "
              "imediata da necessidade de correção"},
    {"inciso": "II",
     "texto": "erro na transposição dos elementos constantes em ordens e "
              "mandados judiciais, termos ou requerimentos, bem como outros "
              "títulos"},
)

SEM_AUTORIZACAO_JUDICIAL = (
    "independentemente de prévia autorização judicial ou manifestação do "
    "Ministério Público (art. 352, redação do Provimento nº 8/2023)")

# QUANDO O ADMINISTRATIVO NAO CABE — e a saida, que o balcao precisa saber
# apontar em vez de simplesmente recusar.
CAMINHO_JUDICIAL = {
    "artigo": "art. 349",
    "para_quem": "requerimento direto ao **juiz corregedor permanente**",
    "como": ("petição fundamentada, devidamente instruída com documentos ou "
             "com a indicação de testemunhas (§ 1º)"),
}

# E O MP PODE PUXAR PARA O RITO SUMARISSIMO — art. 354.
MAIOR_INDAGACAO = {
    "artigo": "art. 354",
    "texto": ("Entendendo o órgão do Ministério Público que o pedido exige "
              "maior indagação, requererá ao juiz a distribuição dos autos a "
              "um dos cartórios da circunscrição, caso em que se processará a "
              "retificação, com assistência de advogado, observado o rito "
              "sumaríssimo."),
}


# ------------------------------------------------------ o art. 353 tem dinheiro
#
# **«ERRO IMPUTAVEL A SERVENTIA» NAO E CAIXINHA DE MARCAR.** E decisao
# fundamentada do oficial, e ela produz tres coisas — gratuidade, DUAS
# comunicacoes, e uma cobranca contra **uma pessoa nomeada**: o delegatario
# titular da epoca do ato incorreto.
ERRO_DA_SERVENTIA = {
    "artigo": "art. 353",
    "gratuita": ("a retificação é processada de forma **gratuita** ao usuário, "
                 "**independentemente da gestão responsável** pela prática do "
                 "ato originário"),
    "comunicar": (
        {"sigla": "FERC", "nome": "Fundo Especial de Registro Civil"},
        {"sigla": "FERJ",
         "nome": "Fundo Especial de Modernização e Reaparelhamento do "
                 "Judiciário"},
    ),
    "cobranca": ("cabe ao FERJ adotar as medidas necessárias para cobrar os "
                 "valores despendidos do **delegatário titular da serventia à "
                 "época da prática do ato incorreto**"),
    "por_que_pede_fundamento": (
        "porque a marca gera gratuidade, duas comunicações e uma cobrança "
        "contra uma pessoa nomeada — e isso é juízo do oficial, não de uma "
        "caixinha"),
}

# E ATO GRATUITO LANCA COM ZERO, e nao deixa de lancar: o valor que TERIA e o
# que a serventia compensa junto ao fundo, e ato gratuito fora do caixa e
# compensacao que ninguem pede. E a mesma regra que o resto da casa ja segue.
GRATUITO_LANCA_COM_ZERO = True


# --------------------------------------- o mandado que nao precisa de cumpra-se
#
# ISTO EVITA UMA RECUSA COMUM NO BALCAO: o escrevente que recebe mandado de outra
# comarca tende a devolve-lo pedindo o «cumpra-se» daqui.
MANDADO_DE_OUTRA_COMARCA = {
    "artigo": "art. 351, parágrafo único",
    "texto": ("Se houver de ser cumprido em jurisdição diversa, o mandado ou "
              "ofício «de ordem» será remetido, por ofício, diretamente ao "
              "registrador civil para que o cumpra; **independente do "
              "«cumpra-se» do juízo local**."),
    "no_balcao": ("não devolva pedindo o «cumpra-se» daqui — a norma diz "
                  "expressamente que não precisa"),
}


def instituto(chave: str) -> dict:
    for x in INSTITUTOS:
        if x["chave"] == chave:
            return x
    raise RetificacaoRcpnError(
        f"«{chave}» não é retificação, restauração nem suprimento.")


def forma(chave: str) -> dict:
    for x in FORMAS_DO_PEDIDO:
        if x["chave"] == chave:
            return x
    raise RetificacaoRcpnError(f"«{chave}» não é uma forma de pedido do § 1º.")


def artigos_citados() -> tuple[str, ...]:
    """Todo artigo que este módulo cita. Só lê — serve à tela de conferência.

    **É PARA O OFICIAL CONFERIR CONTRA O PDF**, que está na casa. Foi o que ele
    pediu no usucapião, e vale aqui pelo mesmo motivo: régua que ninguém confere
    é régua que se acredita.
    """
    return ("art. 348", "art. 348, § 1º", "art. 348, § 2º", "art. 348, § 3º",
            "art. 348, § 4º", "art. 349", "art. 349, § 1º", "art. 349, § 2º",
            "art. 349, § 3º", "art. 350", "art. 351, parágrafo único",
            "art. 352", "art. 353", "art. 354", "art. 355", "art. 365")


def _texto(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()
