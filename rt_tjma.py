"""A retificação de área e o georreferenciamento no Código de Normas do TJMA.

    «vamos criar o módulo de processos de retificação de área e
     georreferenciamento» — o oficial, 29/08/2026
    «para o módulo do processo de georreferenciamento, leve em conta o código de
     normas do tjma que esta na pasta downloads» — ele, no mesmo dia

DE ONDE ISTO SAIU
    Do `Código de normas TJMA atualizado.pdf`, 249 páginas, lido em 29/08/2026.
    **Cada regra traz o artigo ao lado**, para o oficial conferir — é a forma de
    `us_tjma.py`, e ela existe porque regra sem endereço é regra que ninguém
    confere.

AS FAIXAS SAEM DO ÍNDICE DO PRÓPRIO CÓDIGO, E ELE CONFERE CONSIGO MESMO
    A Seção VIII começa no 621, o que fecha a VII em 620. **Faixa de artigo se lê
    no cabeçalho da seção seguinte**, e não no fim do trecho em que se parou de
    ler — no usucapião eu quase gravei que a Seção XIV terminava no 760 quando o
    761 é dela.

O QUE ESTE MÓDULO É, E O QUE NÃO É
    Ele **não decide nada e não guarda nada**: é a norma, em forma que o programa
    e a tela conseguem mostrar. Quem decide é o delegatário, e quem lavra é a
    tela do Registro de Imóveis — que tem a corrente de hash, o selo, os
    emolumentos e o nome de quem assina.
"""
from __future__ import annotations

# ------------------------------------------------------------- as três seções
#
# Lidas no indice do proprio Codigo, e nao contadas a mao.
SECOES: tuple[dict, ...] = (
    {"secao": "V", "titulo": "Da Retificação Administrativa Registral",
     "do": 587, "ao": 605},
    {"secao": "VI",
     "titulo": "Da Retificação e Ratificação dos Atos Notariais e Registrais",
     "do": 606, "ao": 609},
    {"secao": "VII", "titulo": "Do Georreferenciamento", "do": 610, "ao": 620},
)

# As duas especies, e a distincao E DA CASA — nao minha.
#
# Medido nas 1.508 fichas com teor: esta serventia ja escreveu
# «AVERBAÇÃO DE RETIFICAÇÃO DE ÁREA GEORREFERENCIADA» (5 vezes) e
# «AVERBAÇÃO DE RETIFICAÇÃO DE ÁREA NÃO GEORREFERENCIADA» (2). Ela mesma separa
# os dois casos no rotulo do ato, e e essa separacao que o modulo imita.
GEORREFERENCIADA = "GEORREFERENCIADA"
NAO_GEORREFERENCIADA = "NAO_GEORREFERENCIADA"

NOME_DA_ESPECIE = {
    GEORREFERENCIADA: "Retificação de área georreferenciada",
    NAO_GEORREFERENCIADA: "Retificação de área não georreferenciada",
}

# Os dois fundamentos do art. 213 da Lei 6.015/1973, e eles NAO sao a mesma
# coisa. Deixar o balcao escolher seria deixar corrigir de oficio o que precisa
# da anuencia do vizinho — e o vizinho descobre quando vai vender.
DE_OFICIO = "213_I"
A_REQUERIMENTO = "213_II"

NOME_DO_FUNDAMENTO = {
    DE_OFICIO: "Art. 213, I — de ofício, erro evidente",
    A_REQUERIMENTO: "Art. 213, II — a requerimento do interessado",
}


# ------------------------------------------------------- o que instrui o pedido
#
# Art. 592, nove incisos, com os sub-itens do rural. **Sao duas plantas, e nao
# uma** (II e III): a da area como fica e a da area como esta na matricula. Quem
# levar so a primeira volta com nota devolutiva.
DOCUMENTOS_DO_ART_592: tuple[dict, ...] = (
    {"inciso": "I", "artigo": "art. 592, I",
     "o_que": "Requerimento do proprietário ou interessado E do profissional "
              "habilitado, com firmas reconhecidas",
     "detalhe": "Tem de constar a declaração de que os direitos dos "
                "confrontantes foram respeitados."},
    {"inciso": "II", "artigo": "art. 592, II",
     "o_que": "Planta e memorial descritivo da ÁREA RETIFICADA — como o imóvel "
              "fica",
     "detalhe": "Assinados com firma reconhecida pelo profissional, pelo "
                "proprietário E pelos confrontantes. Com coordenadas UTM Datum "
                "SIRGAS 2000 e a identificação de cada confrontante: "
                "logradouro, número, quadra, bairro, matrícula ou transcrição, "
                "livro, folha e a serventia."},
    {"inciso": "III", "artigo": "art. 592, III",
     "o_que": "Planta e memorial descritivo da ÁREA COMO ESTÁ NA MATRÍCULA",
     "detalhe": "É a segunda planta, e ela costuma ser esquecida. Assinada com "
                "firma reconhecida por profissional habilitado, também com UTM "
                "SIRGAS 2000."},
    {"inciso": "IV", "artigo": "art. 592, IV",
     "o_que": "Prova de responsabilidade técnica quitada — ART, RRT ou TRT",
     "detalhe": "Em nome do profissional, com referência a ESTE procedimento "
                "de retificação."},
    {"inciso": "V", "artigo": "art. 592, V",
     "o_que": "Prova da qualidade de confrontante",
     "detalhe": "Certidão imobiliária; em área possessória, quaisquer "
                "documentos comprobatórios — são admitidos todos os meios de "
                "prova."},
    {"inciso": "VI", "artigo": "art. 592, VI",
     "o_que": "Requerimento de notificação dos confinantes faltantes",
     "detalhe": "Quando for o caso, com tantas cópias quantas necessárias "
                "para as notificações. Alcança também proprietários e "
                "titulares de direito real que não assinaram a planta."},
    {"inciso": "VII", "artigo": "art. 592, VII",
     "o_que": "Se o imóvel for RURAL: CCIR, quitação do ITR dos últimos 5 "
              "exercícios, recibo do CAR e prova de inscrição no SIGEF/INCRA",
     "detalhe": "Nos termos e prazos do Decreto 4.449/2002."},
    {"inciso": "VIII", "artigo": "art. 592, VIII",
     "o_que": "Declaração do valor de mercado do imóvel, ou certidão de "
              "avaliação fiscal",
     "detalhe": "Quando possível."},
    {"inciso": "IX", "artigo": "art. 592, IX",
     "o_que": "Boletim de cadastro imobiliário",
     "detalhe": "Se o imóvel for urbano."},
)

# Art. 612 e seguintes — o que o georreferenciamento acrescenta.
DOCUMENTOS_DO_GEORREFERENCIAMENTO: tuple[dict, ...] = (
    {"artigo": "art. 612, I",
     "o_que": "Planta e memorial de CADA matrícula a ser georreferenciada, "
              "certificados pelo INCRA, com o número da certificação",
     "detalhe": "Com as coordenadas dos vértices definidores dos limites "
                "georreferenciadas ao Sistema Geodésico Brasileiro, na "
                "precisão que o INCRA estabelecer."},
    {"artigo": "art. 612, II",
     "o_que": "ART no CREA, RRT no CAU ou TRT no Conselho dos Técnicos "
              "Industriais, com prova de quitação",
     "detalhe": "Assinada pelo profissional E pelo contratante, sem "
                "reconhecimento de firma (art. 614)."},
    {"artigo": "art. 612, III",
     "o_que": "Declarações expressas e inequívocas dos confinantes, com "
              "vértices, medidas, ângulos e azimutes",
     "detalhe": "Assinadas por todos os declarantes, com firma reconhecida "
                "(art. 615)."},
    {"artigo": "art. 613",
     "o_que": "O memorial tem de ser o certificado pelo INCRA, sem alteração "
              "nenhuma",
     "detalhe": "Não se aceita documento que contenha alteração em relação ao "
                "que o INCRA emitiu ou aprovou. Se o memorial vier do SIGEF, "
                "fica dispensada a assinatura física e o reconhecimento de "
                "firma."},
)

# Art. 610 § 1º e art. 619 — quando NAO se exige.
#
# ESTA LISTA EVITA O BALCAO INSEGURO EXIGIR O QUE A NORMA DISPENSA, que e o
# mesmo motivo pelo qual o usucapiao tem a lista do «o que nao impede».
DISPENSAS: tuple[dict, ...] = (
    {"artigo": "art. 610, § 1º, I",
     "o_que": "Dispensada a certificação de cada gleba quando os imóveis serão "
              "objeto de imediata e subsequente fusão, desde que o imóvel "
              "resultante tenha o perímetro certificado."},
    {"artigo": "art. 610, § 1º, II",
     "o_que": "Dispensada a certificação da gleba original, para "
              "desmembramento, desde que as glebas resultantes e a "
              "remanescente estejam certificadas."},
    {"artigo": "art. 610, § 1º, III",
     "o_que": "Dispensada a certificação da gleba original que já possua "
              "descrição georreferenciada, nas mesmas condições."},
    {"artigo": "art. 619",
     "o_que": "Dispensadas as declarações de reconhecimento de limites em "
              "desmembramento, remembramento e parcelamento sobre área JÁ "
              "certificada — não há alteração de medida nem de perímetro."},
    {"artigo": "art. 596, parágrafo único",
     "o_que": "Dispensada a anuência ou intimação dos confrontantes cujas "
              "medidas NÃO estejam sendo alteradas."},
    {"artigo": "art. 593",
     "o_que": "Dispensada a anuência prévia do credor real ou do senhorio "
              "direto: basta a notificação, e a impugnação dele tem de ser "
              "fundamentada — mera alegação de prejuízo não basta."},
)

# Art. 589 § 2º — e ele contraria a intuicao, por isso fica em destaque.
SEM_LIMITE_DE_AREA = {
    "artigo": "art. 589, § 2º",
    "o_que": "Respeitados os critérios de mérito do oficial, NÃO HÁ LIMITE de "
             "aumento ou de redução da mensuração de área, desde que reflita "
             "as reais divisas e seja compatível com a figura geométrica já "
             "existente.",
}

# Art. 594 a 596 — quem e confrontante.
QUEM_E_CONFRONTANTE: tuple[dict, ...] = (
    {"artigo": "art. 594",
     "o_que": "Proprietários e titulares de outros direitos reais aquisitivos "
              "sobre os imóveis CONTÍGUOS."},
    {"artigo": "art. 594, I",
     "o_que": "Condomínio geral: representado por qualquer um dos condôminos."},
    {"artigo": "art. 594, II",
     "o_que": "Condomínio edilício: pelo síndico ou pela comissão de "
              "representantes; sem síndico eleito, pode-se colher a anuência "
              "dos proprietários cujas casas toquem o imóvel retificando."},
    {"artigo": "art. 594, III",
     "o_que": "Condomínio especial por frações autônomas: pela comissão de "
              "representantes."},
    {"artigo": "art. 596",
     "o_que": "Só contam os confinantes das divisas AFETADAS pela inserção ou "
              "alteração de medidas perimetrais."},
    {"artigo": "art. 617",
     "o_que": "Havendo ônus ou direito real na matrícula (servidão, hipoteca, "
              "usufruto), os credores reais devem ser notificados."},
)

# Art. 595 — quando nao da para identificar todo mundo.
IMPOSSIVEL_IDENTIFICAR = {
    "artigo": "art. 595",
    "o_que": "Áreas extensas com muitos confinantes, ocupações irregulares, "
             "invasões, assentamentos: constatado por ATA NOTARIAL, a "
             "notificação vai por EDITAL — preservada, em qualquer caso, a "
             "impugnação de qualquer ocupante que demonstre essa condição.",
}

# Art. 598 — a ordem das tentativas, e ela E uma ordem: o edital so cabe
# «caso frustradas as tentativas anteriores».
COMO_NOTIFICAR: tuple[dict, ...] = (
    {"forma": "PESSOAL", "artigo": "art. 598",
     "o_que": "Pessoalmente, pelo oficial de registro de imóveis"},
    {"forma": "RTD", "artigo": "art. 598",
     "o_que": "Pelo oficial de registro de títulos e documentos da comarca da "
              "situação do imóvel, ou do domicílio de quem deva receber"},
    {"forma": "CORREIO", "artigo": "art. 598",
     "o_que": "Correio com aviso de recebimento"},
    {"forma": "EDITAL", "artigo": "art. 598",
     "o_que": "Por edital — SÓ depois de frustradas as tentativas anteriores"},
)

ONDE_NOTIFICAR = {
    "artigo": "art. 598, § 1º",
    "o_que": "No endereço indicado pelo requerente, no endereço do confrontante "
             "que consta da matrícula do imóvel contíguo, ou no endereço do "
             "próprio imóvel que faz divisa com o retificando.",
}


# ------------------------------------------------------------------- os prazos
#
# TODOS EM DIAS UTEIS, menos o do SIGEF — que o artigo escreve «30 (trinta)
# dias», sem qualificar, e por isso fica em dias corridos. Inventar «uteis» ali
# daria a serventia mais prazo do que a norma deu.
PRAZOS: tuple[dict, ...] = (
    {"chave": "QUALIFICAR", "artigo": "art. 597", "dias": 10, "uteis": True,
     "de_quem": "OFICIAL",
     "o_que": "Analisar os documentos e, se for o caso, emitir nota devolutiva"},
    {"chave": "CUMPRIR_NOTA", "artigo": "art. 597, § 1º", "dias": 10,
     "uteis": True, "de_quem": "REQUERENTE",
     "o_que": "Prazo adicional, fundamentado, para cumprir nota devolutiva "
              "subsequente que o requerente não causou"},
    {"chave": "QUALIFICAR_DE_NOVO", "artigo": "art. 597, § 2º", "dias": 10,
     "uteis": True, "de_quem": "OFICIAL",
     "o_que": "O prazo de qualificação é devolvido ao oficial depois das "
              "diligências"},
    {"chave": "MANIFESTAR", "artigo": "art. 598", "dias": 15, "uteis": True,
     "de_quem": "CONFRONTANTE",
     "o_que": "O confrontante notificado se manifesta"},
    {"chave": "IMPUGNAR", "artigo": "art. 599", "dias": 15, "uteis": True,
     "de_quem": "NOTIFICADO",
     "o_que": "Impugnar, contado INDIVIDUALMENTE para cada notificado, do "
              "recebimento da notificação ou da última publicação do edital"},
    {"chave": "IMPUGNAR_ENTE_PUBLICO", "artigo": "art. 599, § 4º", "dias": 15,
     "uteis": True, "de_quem": "ENTE_PUBLICO",
     "o_que": "Prorrogação por igual período para União, Estado e Município, "
              "mediante solicitação justificada dentro do prazo original"},
    {"chave": "RESPONDER_IMPUGNACAO", "artigo": "art. 600", "dias": 5,
     "uteis": True, "de_quem": "REQUERENTE",
     "o_que": "O requerente e o profissional que assinou a planta se "
              "manifestam sobre a impugnação"},
    {"chave": "TRANSACAO", "artigo": "art. 600, § 2º", "dias": 15, "uteis": True,
     "de_quem": "AS_PARTES",
     "o_que": "Formalizar a transação amigável ou agendar a mediação — "
              "prorrogável, a pedido, uma única vez por mais 15 dias úteis"},
    {"chave": "SUSCITAR_DUVIDA", "artigo": "art. 604, § 2º", "dias": 15,
     "uteis": True, "de_quem": "REQUERENTE",
     "o_que": "Requerer, fundamentadamente, que o oficial suscite dúvida, se o "
              "pedido foi julgado improcedente"},
    {"chave": "SIGEF", "artigo": "art. 620, § 2º", "dias": 30, "uteis": False,
     "de_quem": "A_SERVENTIA",
     "o_que": "Requerer o registro no SIGEF, com o número da nova matrícula e "
              "os dados dos proprietários, anexando a certidão de inteiro teor "
              "da nova matrícula e da anterior encerrada"},
)

PRAZO_POR_CHAVE = {p["chave"]: p for p in PRAZOS}

# AS DUAS REGRAS DO SILENCIO E DO ATRASO, E ELAS PUXAM PARA LADOS OPOSTOS.
#
# Um sistema que trate «prazo vencido» como «acabou» erraria, e erraria contra
# quem nao foi ouvido: a porta so fecha quando a averbacao sai.
SILENCIO_VALE_ANUENCIA = {
    "artigo": "art. 599, § 1º",
    "o_que": "Será presumida a anuência do confrontante que deixar de "
             "apresentar impugnação no prazo legal.",
}

IMPUGNACAO_ATRASADA_ENTRA = {
    "artigo": "art. 599, § 3º",
    "o_que": "Mesmo apresentada fora de prazo, MAS ANTES DA AVERBAÇÃO da "
             "retificação, a impugnação será recebida e processada.",
}


# ------------------------------------------------------------------ o desfecho
#
# Os dois ritos terminam do mesmo jeito, e e a maior operacao registral que este
# sistema vai encostar: matricula nova, matricula velha encerrada, onus
# transportados. Por isso o modulo PREPARA e a tela do RI LAVRA — que e a
# decisao do CNIB, pelo mesmo motivo.
DESFECHO_DA_RETIFICACAO: tuple[dict, ...] = (
    {"passo": 1, "artigo": "art. 604",
     "o_que": "O oficial decide, por decisão FUNDAMENTADA, sobre a "
              "possibilidade da retificação"},
    {"passo": 2, "artigo": "art. 604, § 1º",
     "o_que": "Procedente: averba a retificação, ENCERRA a matrícula "
              "retificanda e inaugura NOVA matrícula com a especialização do "
              "imóvel, transportando todos os ônus e averbações não cancelados"},
    {"passo": 3, "artigo": "art. 604, § 2º",
     "o_que": "Improcedente: o interessado tem 15 dias úteis para requerer, "
              "fundamentadamente, a suscitação de dúvida"},
    {"passo": 4, "artigo": "art. 605",
     "o_que": "Concluída positivamente, o polígono e seus dados são publicados "
              "no Mapa do Registro de Imóveis do Brasil"},
)

DESFECHO_DO_GEORREFERENCIAMENTO: tuple[dict, ...] = (
    {"passo": 1, "artigo": "art. 620",
     "o_que": "Averba-se a retificação de área"},
    {"passo": 2, "artigo": "art. 620",
     "o_que": "Depois, a certificação do georreferenciamento"},
    {"passo": 3, "artigo": "art. 620",
     "o_que": "Em ato contínuo, abre-se NOVA matrícula, cuja descrição "
              "perimetral observa o memorial gerado automaticamente pelo SIGEF "
              "e contém o número da certificação do INCRA"},
    {"passo": 4, "artigo": "art. 620, § 1º",
     "o_que": "Encerra-se a matrícula anterior; havendo ônus ativo, ele é "
              "transportado para a nova"},
    {"passo": 5, "artigo": "art. 620, § 2º",
     "o_que": "Em até 30 DIAS, requerimento de registro no SIGEF com o número "
              "da nova matrícula e os dados dos proprietários, anexando a "
              "certidão de inteiro teor da nova e da anterior encerrada"},
)


# ------------------------------------------------------------- a circunscrição
CIRCUNSCRICAO: tuple[dict, ...] = (
    {"artigo": "art. 590",
     "o_que": "O procedimento tramita perante o oficial da circunscrição ATUAL "
              "de localização do imóvel."},
    {"artigo": "art. 590, § 1º",
     "o_que": "Verificado que o imóvel é de outra circunscrição, cancela-se o "
              "protocolo e devolve-se a documentação, cobrando os emolumentos "
              "dos atos até então praticados."},
    {"artigo": "art. 590, § 2º",
     "o_que": "Se o imóvel passou a pertencer a outra circunscrição, abre-se "
              "matrícula na nova serventia para nela se fazer a retificação, "
              "comunicando-se a de origem para encerrar a anterior."},
    {"artigo": "art. 590, § 3º",
     "o_que": "Imóvel em DUAS circunscrições: tramita na da MAIOR área, "
              "averbando-se a circunstância na outra, sem conteúdo financeiro."},
    {"artigo": "art. 590, § 4º",
     "o_que": "Áreas idênticas nas duas: na serventia de escolha do "
              "interessado, averbada a circunstância na outra, sem conteúdo "
              "financeiro."},
)

NAO_GERA_PRIORIDADE = {
    "artigo": "art. 591",
    "o_que": "O requerimento de retificação do art. 213, II NÃO gera "
             "prioridade nem impede a qualificação e o registro dos demais "
             "títulos que não sejam excludentes ou contraditórios.",
}


# --------------------------------------------------------------------- funções


def artigos_citados() -> list[str]:
    """Todo artigo que este módulo cita, em ordem. Só calcula.

    SERVE PARA CONFERIR CONTRA O PDF, e é o que torna a leitura auditável: quem
    quiser saber se eu inventei alguma coisa pega esta lista e abre o Código.
    """
    import re
    vistos: set[int] = set()
    fontes: list = [SEM_LIMITE_DE_AREA, IMPOSSIVEL_IDENTIFICAR, ONDE_NOTIFICAR,
                    SILENCIO_VALE_ANUENCIA, IMPUGNACAO_ATRASADA_ENTRA,
                    NAO_GERA_PRIORIDADE]
    for grupo in (DOCUMENTOS_DO_ART_592, DOCUMENTOS_DO_GEORREFERENCIAMENTO,
                  DISPENSAS, QUEM_E_CONFRONTANTE, COMO_NOTIFICAR, PRAZOS,
                  DESFECHO_DA_RETIFICACAO, DESFECHO_DO_GEORREFERENCIAMENTO,
                  CIRCUNSCRICAO):
        fontes.extend(grupo)
    for item in fontes:
        achado = re.search(r"art\.\s*(\d+)", str(item.get("artigo", "")))
        if achado:
            vistos.add(int(achado.group(1)))
    return [f"art. {n}" for n in sorted(vistos)]


def fora_das_secoes() -> list[str]:
    """Os artigos citados que NÃO caem nas três seções medidas.

    ESTE É O CONFERIDOR DA MINHA PRÓPRIA LEITURA. Se eu tiver copiado um artigo
    de outra parte do Código achando que era daqui, ele aparece nesta lista — e
    há teste que exige a lista vazia.

    Foi o engano que eu quase cometi no usucapião, e o que me salvou lá foi ir
    conferir o cabeçalho da seção seguinte. Aqui a conferência é automática.
    """
    import re
    faixas = [(s["do"], s["ao"]) for s in SECOES]
    fora = []
    for citado in artigos_citados():
        n = int(re.search(r"(\d+)", citado).group(1))
        if not any(do <= n <= ao for do, ao in faixas):
            fora.append(citado)
    return fora


def prazo(chave: str) -> dict:
    """O prazo pela chave, com o artigo junto.

    NÃO CALCULA DATA. Contar dia útil é do `feriados`/`livro_nucleo`, que já
    conhecem os feriados desta comarca; uma segunda contagem aqui divergiria da
    da prenotação e da do edital do usucapião — e num prazo, divergir por um dia
    é recomeçar o prazo.
    """
    achado = PRAZO_POR_CHAVE.get(str(chave or "").upper())
    if not achado:
        raise KeyError(
            f"«{chave}» não é um prazo desta seção. Os que existem: "
            + ", ".join(PRAZO_POR_CHAVE) + ".")
    return dict(achado)


def checklist(*, georreferenciada: bool, rural: bool) -> list[dict]:
    """O que o procedimento exige, no caso concreto. Só calcula.

    O INCISO VII DO ART. 592 SÓ VALE PARA IMÓVEL RURAL, e os documentos do
    georreferenciamento só entram quando ele existe. Mostrar tudo sempre faria o
    balcão exigir CCIR de apartamento — e exigência que não se aplica é
    exigência que o cliente cumpre à toa.
    """
    # O VII e do rural (CCIR, ITR, CAR, SIGEF); o IX e do urbano (boletim de
    # cadastro imobiliario). Cada imovel e um dos dois, e por isso um dos dois
    # incisos sempre sai.
    sai = "IX" if rural else "VII"
    itens = [dict(x) for x in DOCUMENTOS_DO_ART_592 if x["inciso"] != sai]
    if georreferenciada:
        itens.extend(dict(x) for x in DOCUMENTOS_DO_GEORREFERENCIAMENTO)
    return itens
