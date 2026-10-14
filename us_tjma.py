"""O que o Codigo de Normas do TJMA exige da usucapiao extrajudicial.

DE ONDE VEIO, E POR QUE ISTO E UM MODULO E NAO UM COMENTARIO
    O oficial relatou, pela janela da ajuda: «o cadastramento e muito simples e
    nao parece ser maduro para processar um usucapiao no RI com confianca».
    Ele pediu referencias, e em 28/08/2026 decidiu: «eu monto do Codigo de
    Normas do TJMA e da lei, e voce confere».

    O CODIGO ESTA NA CASA. `Codigo de normas TJMA atualizado.pdf`, 249
    paginas, na pasta de Downloads do oficial. A Secao XIV — «Da Usucapiao
    Extrajudicial» — sao os **arts. 747 a 761**, e os arts. 738 e 739 tratam
    dela dentro da regularizacao fundiaria rural.

    Cada linha deste arquivo saiu de um artigo LIDO, e o texto do artigo esta
    aqui do lado.

    > **E EU QUASE GRAVEI UMA CORRECAO ERRADA AQUI.** `usucapiao.py` citava
    > «Codigo de Normas TJMA, arts. 747 a 761», e eu escrevi que a faixa estava
    > errada porque a Secao terminaria no 760. Fui conferir no PDF antes de
    > deixar a frase de pe, e a Secao XV («Das Cedulas de Credito») so comeca no
    > **762**: o 761 e de usucapiao, sim — e o imovel edificado. **A citacao que
    > ja estava no codigo estava certa, e a minha correcao e que estava errada.**
    >
    > A licao nao e sobre o artigo: e sobre a ordem. Eu tinha lido do 737 ao
    > 760 e concluido a faixa **pelo que eu tinha lido**, e nao pelo que estava
    > escrito. Faixa de artigos se le no cabecalho da secao seguinte, e nao no
    > fim do trecho que a gente parou de ler.

O QUE ESTE MODULO NAO FAZ
    Nao julga. Nao decide se a impugnacao procede, se a posse esta provada, se
    o obice esta justificado. Ele diz o que o Codigo manda perguntar, com o
    artigo do lado, e quem responde e o delegatario. E a mesma regra do
    usucapiao, das fraudes e do impedimento de casamento — terceira, quarta e
    quinta vez.
"""
from __future__ import annotations

# =========================================================================
# ART. 748 — A JUSTIFICACAO DO OBICE, que o modulo nao tinha de jeito nenhum
# =========================================================================
#
#   «Para o processamento da usucapiao, devera ser justificado o obice a
#    correta escrituracao das transacoes para evitar o uso deste instituto
#    como meio de burla dos requisitos legais do sistema notarial e registral
#    e da tributacao dos impostos de transmissao (...), devendo o registrador
#    alertar o requerente e as testemunhas de que a prestacao de declaracao
#    falsa na referida justificacao configurara crime de falsidade, sujeito as
#    penas da lei.»                                    — Codigo TJMA, art. 748
#
# ESTE E O ITEM QUE MAIS FALTAVA, e nao e papelada: e a pergunta que separa a
# usucapiao de uma compra e venda que alguem nao quis registrar para nao pagar
# ITBI. Sem ela o cartorio vira o caminho barato da transmissao — que e
# exatamente o que o artigo diz que ele nao pode ser.
#
# As sete hipoteses do § 1o sao «entre outras»: a lista NAO e fechada, e por
# isso ha `OUTRO`, com o motivo escrito. Fechar a lista faria o balcao recusar
# um caso legitimo que o Codigo admite.
OBICES_DO_ART_748: dict[str, str] = {
    "IMOVEL_INVADIDO": "Imóvel invadido, sem negócio jurídico com o proprietário",
    "ALIENANTE_NAO_LOCALIZADO": "O alienante não foi localizado",
    "PJ_EXTINTA_IRREGULARMENTE": "A pessoa jurídica que alienou foi extinta "
                                 "irregularmente",
    "TRANSMITENTE_SEM_CND": "O transmitente é pessoa jurídica sem certidão "
                            "negativa de débitos",
    "LOTEAMENTO_IRREGULAR": "O imóvel está em loteamento irregular ou clandestino",
    "HERDEIROS_RECUSAM_INVENTARIO": "Os herdeiros do alienante recusam-se a "
                                    "fazer o inventário",
    "INVENTARIOS_SUCESSIVOS": "Inventários sucessivos, de onerosidade excessiva",
    "OUTRO": "Outra situação — escreva qual",
}

# O ALERTA E DO REGISTRADOR, E ELE E OBRIGATORIO. Nao e aviso de tela: e ato
# que o art. 748 manda praticar, e que a decisao depois vai dizer que foi
# praticado. Fica com estas palavras porque sao as do artigo.
ALERTA_DO_ART_748 = (
    "Declaração falsa nesta justificação configura crime de falsidade, "
    "sujeito às penas da lei. O requerente e as testemunhas foram alertados "
    "disso, nos termos do art. 748 do Código de Normas do TJMA."
)

# E O QUE O OFICIAL NAO PODE FAZER, no mesmo artigo:
#
#   «E vedado ao oficial formular exigencias tributarias com relacao a negocios
#    juridicos utilizados para comprovacao da posse ad usucapionem.»
#                                                 — art. 748, § 2o
#
# Vale como aviso na tela de exigencias: pedir ITBI dos negocios que provam a
# posse e exigencia que o Codigo proibe, e ela atrasa um rito de meses.
VEDACAO_EXIGENCIA_TRIBUTARIA = (
    "Não se formula exigência tributária sobre os negócios jurídicos usados "
    "para provar a posse (art. 748, § 2º, do Código de Normas do TJMA)."
)


# =========================================================================
# O QUE IMPEDE, E O QUE NAO IMPEDE
# =========================================================================
#
# A LISTA DO QUE **NAO** IMPEDE E MAIS IMPORTANTE QUE A DO QUE IMPEDE, e este
# e o ponto em que um balcao inseguro trava um pedido bom. Sao quatro casos em
# que a intuicao diz «isto derruba» e o Codigo diz que nao derruba — e cada um
# tem artigo.
NAO_IMPEDEM: tuple[dict, ...] = (
    {"caso": "SEM_REGISTRO",
     "rotulo": "O imóvel não tem registro nenhum",
     "base": "Código TJMA, art. 738",
     "texto": "A inexistência de registro, em nome de particular ou de ente "
              "público, não impede — a matrícula será aberta sem indicação de "
              "proprietário e sem registro anterior."},
    {"caso": "AREA_MENOR_QUE_A_MINIMA",
     "rotulo": "A área é menor que a fração mínima de parcelamento",
     "base": "Código TJMA, art. 758",
     "texto": "Registra-se ainda que a área seja inferior à fração mínima de "
              "parcelamento rural ou à área mínima de lote urbano."},
    {"caso": "ONUS_OU_GRAVAME",
     "rotulo": "Há ônus real ou gravame na matrícula",
     "base": "Código TJMA, art. 759",
     "texto": "Não impede, **desde que os titulares sejam notificados** no "
              "curso do procedimento."},
    {"caso": "INDISPONIBILIDADE_POSTERIOR",
     "rotulo": "Há indisponibilidade averbada depois do início da posse",
     "base": "Código TJMA, art. 760",
     "texto": "Não impede o reconhecimento. Mas cria três deveres — ver "
              "`DEVERES_DA_INDISPONIBILIDADE`."},
)

# O QUE IMPEDE E UM SO, e e categorico.
#
#   «E vedado o reconhecimento de usucapiao de imovel objeto de garantia no
#    Sistema Financeiro da Habitacao.»                — Codigo TJMA, art. 749
VEDACAO_SFH = {
    "rotulo": "Imóvel objeto de garantia no Sistema Financeiro da Habitação",
    "base": "Código TJMA, art. 749",
    "texto": "O reconhecimento é vedado. Não é caso de exigência nem de "
             "diligência: o pedido não pode ser processado por esta via.",
}

# E O QUE E EXPRESSAMENTE PERMITIDO, para ninguem recusar por dúvida:
#
#   «E permitida a usucapiao de dominio util e outros direitos reais.»
#                                                     — Codigo TJMA, art. 750
PERMITIDO_DOMINIO_UTIL = (
    "Usucapião de domínio útil e de outros direitos reais é permitida "
    "(art. 750 do Código de Normas do TJMA)."
)


# =========================================================================
# ART. 760 — OS TRES DEVERES QUANDO HA INDISPONIBILIDADE
# =========================================================================
#
# E o artigo que amarra este modulo ao CNIB, e os tres deveres acontecem em
# MOMENTOS DIFERENTES do rito. Escrito num paragrafo so, o do meio se perde —
# e e o unico que pode indeferir o pedido.
DEVERES_DA_INDISPONIBILIDADE: tuple[dict, ...] = (
    {"quando": "NOTIFICACAO",
     "rotulo": "Notificar, por malote digital, o juízo que decretou a "
               "indisponibilidade",
     "base": "Código TJMA, art. 760, § 1º",
     "nota": "com a indicação do número do processo judicial, durante a fase "
             "destinada às notificações"},
    {"quando": "CONCLUSAO",
     "rotulo": "Na análise de mérito, verificar se houve má-fé na cessão de "
               "direitos por quem tinha os bens indisponíveis",
     "base": "Código TJMA, art. 760, § 2º",
     "nota": "constatada a má-fé, o oficial PODE indeferir com base na "
             "indisponibilidade — é decisão dele, e o artigo diz «poderá»"},
    {"quando": "REGISTRO",
     "rotulo": "Depois do registro, notificar o juízo de novo, com cópia da "
               "matrícula atualizada",
     "base": "Código TJMA, art. 760, § 3º",
     "nota": "por malote digital, como a primeira"},
)


# =========================================================================
# ART. 753 — O QUE A PLANTA E O MEMORIAL TEM DE TRAZER
# =========================================================================
#
# O modulo pedia «Planta do imovel» e «Memorial descritivo» e parava ai. O
# artigo lista o conteudo, e e nele que um pedido volta em exigencia depois de
# semanas. Cada linha e um campo do artigo, na ordem dele.
CONTEUDO_DA_PLANTA: tuple[str, ...] = (
    "localização do imóvel",
    "medidas e área",
    "perímetro",
    "configuração geométrica",
    "coordenadas UTM, Datum SIRGAS 2000",
    # Os parenteses sao explicitos: numa tupla, duas linhas de texto coladas
    # sem eles parecem uma virgula esquecida — e este item viraria dois.
    ("identificação de cada confrontante: logradouro, número, quadra, bairro, "
     "número da matrícula ou transcrição, livro, folha e serventia"),
)
BASE_DA_PLANTA = "Código TJMA, art. 753 (imóvel sem origem registrária)"

# O QUE FAZER QUANDO A AREA NAO BATE COM A MATRICULA — art. 753, §§ 2o a 4o.
# Sao quatro situacoes distintas, e cada uma leva o registro a um lugar
# diferente. Perguntar isso na entrada evita a diligencia do terceiro mes.
AREA_CONTRA_A_MATRICULA: tuple[dict, ...] = (
    {"caso": "SEM_MATRICULA", "rotulo": "O imóvel não está matriculado",
     "efeito": "abre-se matrícula nova, sem proprietário e sem registro "
               "anterior",
     "base": "Código TJMA, art. 738"},
    {"caso": "IGUAL", "rotulo": "Matriculado, e o pedido é do imóvel inteiro, "
                                "sem mudar a descrição do perímetro",
     "efeito": "o registro é feito NA PRÓPRIA MATRÍCULA existente — não se "
               "abre matrícula nova",
     "base": "Código TJMA, art. 753, § 2º"},
    {"caso": "MAIOR", "rotulo": "A área usucapida é MAIOR que a da matrícula",
     "efeito": "o requerente indica no pedido a razão da diferença e se há "
               "outra área, matriculada ou não; sem essa indicação, a diferença "
               "é averbada na matrícula de origem",
     "base": "Código TJMA, art. 753, § 3º"},
    {"caso": "MENOR", "rotulo": "A área usucapida é MENOR que a da matrícula",
     "efeito": "o requerente informa se haverá remanescente na matrícula ou se "
               "está sendo usucapida a área total",
     "base": "Código TJMA, art. 753, § 4º"},
)


# =========================================================================
# ART. 751 E 752 — AS CERTIDOES, E QUANDO ELAS SE DISPENSAM
# =========================================================================
#
# O checklist tratava «Certidoes negativas dos distribuidores» como exigencia
# fechada. O Codigo tem uma dispensa expressa, e uma equivalencia — e as duas
# resolvem casos que, sem elas, param o processo para sempre.
DISPENSA_DE_CERTIDAO = {
    "base": "Código TJMA, art. 751",
    "texto": "Dispensam-se as certidões negativas dos distribuidores quando "
             "for impossível obter os dados de qualificação pessoal dos "
             "titulares do domínio — basta a impressão do resultado da "
             "pesquisa online apenas com o nome.",
}
EQUIVALE_A_QUITACAO = {
    "base": "Código TJMA, art. 752",
    "texto": "Equivale à prova de quitação a certidão emitida após 5 anos do "
             "vencimento da última prestação, pelos distribuidores da Justiça "
             "Estadual e da Federal do local do imóvel e do domicílio do "
             "requerente, se diverso, explicitando que não há ação sobre a "
             "posse ou a propriedade contra o adquirente ou seus cessionários.",
}


# =========================================================================
# ART. 755 — O EDITAL, E DE QUANDO SE CONTA O PRAZO
# =========================================================================
#
# ESTA E A REGRA QUE FAZ O PRAZO SER OUTRO, e errar por um dia num edital e
# recomecar. Sao DOIS «primeiro dia util seguinte» encadeados, e nao um:
#
#   «Sera considerada como data da publicacao o primeiro dia util subsequente
#    ao da disponibilizacao da informacao no meio eletronico, e os prazos
#    passarao a contar a partir do primeiro dia util seguinte ao considerado
#    como data da publicacao.»                    — Codigo TJMA, art. 755, § 1o
EDITAL_NA_CENTRAL = {
    "base": "Código TJMA, art. 755",
    "texto": "Os editais podem ser divulgados pela Central Eletrônica de "
             "Registro de Imóveis, dispensada a publicação em jornal de "
             "grande circulação.",
}
EDITAL_SEM_ORIGEM = {
    "base": "Código TJMA, art. 755, § 2º",
    "texto": "Para imóvel sem origem registrária, ou cuja origem não foi "
             "encontrada, o edital deve consignar expressamente essa "
             "circunstância.",
}


def data_da_publicacao(disponibilizado_em: str, e_dia_util) -> str:
    """A data de publicacao do edital: o primeiro dia util APOS a disponibilizacao.

    `e_dia_util` e uma funcao que recebe `AAAA-MM-DD` e diz se e dia util —
    quem a fornece e quem sabe os feriados desta comarca, que ja moram em
    `ri_schema.ler_feriados_locais`. Nao se embute calendario aqui: feriado
    municipal e coisa de cada casa, e um calendario escrito neste arquivo
    envelheceria calado.
    """
    return _proximo_util(disponibilizado_em, e_dia_util)


def inicio_do_prazo(disponibilizado_em: str, e_dia_util) -> str:
    """De quando os prazos passam a contar — o primeiro dia util APOS a publicacao.

    SAO DOIS SALTOS, E NAO UM. Quem ler o § 1o com pressa conta o prazo da
    disponibilizacao; o artigo manda achar a data da publicacao (um salto) e
    so entao comecar a contar (outro salto). Num edital, errar por um dia e
    recomecar o edital.
    """
    return _proximo_util(data_da_publicacao(disponibilizado_em, e_dia_util),
                         e_dia_util)


def _proximo_util(dia: str, e_dia_util) -> str:
    from datetime import date, timedelta
    d = date.fromisoformat(str(dia)[:10]) + timedelta(days=1)
    for _ in range(30):
        if e_dia_util(d.isoformat()):
            return d.isoformat()
        d += timedelta(days=1)
    # Trinta dias sem achar dia util nao e feriado: e calendario errado. Melhor
    # devolver o que se sabe do que inventar uma data que ninguem conferiu.
    raise ValueError(
        "Não encontrei dia útil nos 30 dias seguintes a "
        f"{dia} — confira o calendário de feriados da serventia.")


# =========================================================================
# ART. 761 — O IMOVEL EDIFICADO
# =========================================================================
#
#   «Nos casos de imovel edificado, sera aberta matricula para o TERRENO,
#    promovendo-se, na sequencia, a averbacao da benfeitoria ou da pendencia de
#    sua regularizacao.»                                — Codigo TJMA, art. 761
#
# Sao dois atos e nao um, e nessa ordem — o que resolve a duvida de quem tem um
# pedido sobre casa construida e nao sabe se abre a matricula da casa ou do
# terreno. Abre-se a do terreno.
IMOVEL_EDIFICADO: tuple[dict, ...] = (
    {"passo": "MATRICULA_DO_TERRENO",
     "rotulo": "Abrir a matrícula para o TERRENO",
     "base": "Código TJMA, art. 761"},
    {"passo": "AVERBAR_BENFEITORIA",
     "rotulo": "Em seguida, averbar a benfeitoria — ou a pendência de "
               "regularização dela",
     "base": "Código TJMA, art. 761"},
)

# E DUAS COISAS QUE O ARTIGO DISPENSA E DESTRAVA, e as duas evitam exigencia:
CONSTRUCAO_NO_IMOVEL: tuple[dict, ...] = (
    {"caso": "COM_DOCUMENTO_DO_247_A",
     "texto": "Apresentado o documento do art. 247-A da Lei 6.015/1973, a "
              "matrícula é aberta com a descrição do terreno E da construção, "
              "SEM certidão previdenciária e SEM declaração de dispensa.",
     "base": "Código TJMA, art. 761, § 1º"},
    {"caso": "CONSTRUCAO_NAO_REGULARIZADA",
     "texto": "Construção não regularizada no imóvel não impede a escrituração "
              "nem o registro de atos posteriores na matrícula.",
     "base": "Código TJMA, art. 761, § 2º"},
)


# =========================================================================
# ART. 747 — ONDE O PEDIDO CORRE
# =========================================================================
#
#   «O reconhecimento extrajudicial de usucapiao sera processado diretamente
#    perante o oficio de registro de imoveis da circunscricao em que estiver
#    situado o imovel usucapiendo, SEM PREJUIZO DA VIA JURISDICIONAL (...)»
#                                                      — Codigo TJMA, art. 747
#
# «Sem prejuizo da via jurisdicional» e a frase que o balcao precisa ter na
# ponta da lingua: o interessado nao perde o direito de ir a juizo por ter
# comecado aqui, e recusar aqui nao fecha a porta dele.
ONDE_CORRE = {
    "base": "Código TJMA, art. 747",
    "texto": "Corre no registro de imóveis da circunscrição onde o imóvel "
             "está situado, sem prejuízo da via jurisdicional — nos termos do "
             "art. 216-A da Lei 6.015/1973 e da regulamentação da Corregedoria "
             "Nacional de Justiça.",
}


# =========================================================================
# ARTS. 739 E 756 — A IMPUGNACAO
# =========================================================================
#
# O QUE O OFICIAL FAZ COM UMA IMPUGNACAO NAO E DECIDIR SE ELA PROCEDE: e
# tentar conciliar, e — num caso so — remeter ao juizo. Os dois artigos dizem
# a mesma coisa por dois lados, e o 739 traz a distincao que salva o pedido.
IMPUGNACAO_CAMINHOS: tuple[dict, ...] = (
    {"caso": "CONCILIAR",
     "rotulo": "Impugnação de titular, confrontante, ente público ou terceiro",
     "efeito": "o oficial diligencia para promover a conciliação ou a mediação "
               "entre as partes",
     "base": "Código TJMA, arts. 739 e 756"},
    {"caso": "REMETER",
     "rotulo": "Impugnação de ente público sobre matéria de direito "
               "indisponível",
     "efeito": "os autos vão ao juiz com jurisdição em Registros Públicos ou, "
               "onde não houver vara especializada, ao juízo cível",
     "base": "Código TJMA, art. 756"},
)

# A DISTINCAO DO ART. 739, § 1o — e ela existe para impedir que um pedido bom
# morra numa frase de duas linhas do orgao publico:
#
#   «Considera-se INJUSTIFICADA a impugnacao apresentada pelo Orgao Publico que
#    se limita a dizer que o imovel objeto do pedido de usucapiao pertence ao
#    Estado e e considerada terra devoluta, pelo fato de nao possuir matricula
#    ou transcricao no Registro Imobiliario.»
#
#   «Caso o orgao publico apresente matricula com a descricao de localizacao
#    suficiente, indicando que o imovel esta localizado dentro do perimetro de
#    area arrecadada ou de propriedade do Estado, o Oficial devera considerar
#    JUSTIFICADA a impugnacao (...)»                — art. 739, §§ 1o e 2o
IMPUGNACAO_DE_ORGAO_PUBLICO = (
    {"quando": "INJUSTIFICADA",
     "texto": "Limitar-se a dizer que o imóvel é terra devoluta do Estado "
              "porque não tem matrícula nem transcrição — isso, sozinho, é "
              "impugnação INJUSTIFICADA.",
     "base": "Código TJMA, art. 739, § 1º"},
    {"quando": "JUSTIFICADA",
     "texto": "Apresentar matrícula com descrição de localização suficiente, "
              "mostrando que o imóvel está dentro do perímetro de área "
              "arrecadada ou de propriedade do Estado — aí a impugnação é "
              "JUSTIFICADA, e, não havendo ajuste na conciliação, os autos "
              "vão ao juízo competente da comarca da situação do imóvel.",
     "base": "Código TJMA, art. 739, § 2º"},
)


# =========================================================================
# ART. 757 — A DECISAO
# =========================================================================
#
#   «Processada a usucapiao, sem pendencia de diligencias complementares e
#    achando-se em ordem a documentacao, o oficial de registro de imoveis
#    emitira decisao fundamentada de indeferimento ou de deferimento, sendo que
#    esta servira de titulo para o registro da aquisicao do imovel com as
#    descricoes apresentadas.»                          — Codigo TJMA, art. 757
#
# «SEM PENDENCIA DE DILIGENCIAS COMPLEMENTARES» E CONDICAO, E NAO CONSELHO —
# e `usucapiao.decidir()` ja recusa decidir procedente com item pendente. O
# artigo confirma a regra que o modulo ja tinha.
A_DECISAO_E_O_TITULO = (
    "A decisão de deferimento SERVE DE TÍTULO para o registro da aquisição, "
    "com as descrições apresentadas (art. 757 do Código de Normas do TJMA). "
    "Não se pede outro título ao interessado."
)
CONDOMINIO_NAO_INSTITUIDO = {
    "base": "Código TJMA, art. 757, parágrafo único",
    "texto": "Unidade autônoma em condomínio edilício ainda não instituído, "
             "ou sem averbação de construção: a matrícula é aberta para a "
             "FRAÇÃO IDEAL, mencionando a unidade a que se refere e que ela "
             "está submetida ao regime de condomínio edilício.",
}

# Art. 754: a notificacao de confrontante segue, no que couber, o procedimento
# de retificacao de registro — e nao um rito proprio inventado aqui.
NOTIFICACAO_DE_CONFRONTANTE = {
    "base": "Código TJMA, art. 754",
    "texto": "A notificação de confrontante observa, no que couber, o "
             "procedimento de retificação de registro.",
}


def artigos_citados() -> tuple[str, ...]:
    """Os artigos do Codigo de Normas que este modulo usa, para conferencia.

    Existe para o oficial poder abrir o PDF e ler cada um — foi ele quem pediu
    para conferir. E ha teste que compara esta lista com o que os textos deste
    arquivo realmente citam: lista escrita a mao noutro lugar envelhece na
    tarde em que se escreve.
    """
    import re
    achados = set()
    for valor in globals().values():
        for texto in _textos(valor):
            # SO O QUE ESTA MARCADO COMO DO CODIGO DE NORMAS. A busca solta por
            # `art. NNN` trazia tambem o art. 216-A e o art. 247-A, que sao da
            # LEI DE REGISTROS PUBLICOS — e quem fosse conferir no PDF do
            # Codigo procuraria dois artigos que nao estao la. Lista de
            # conferencia que manda a pessoa ao lugar errado e pior que
            # nenhuma.
            # As duas formas em que o Codigo e citado neste arquivo: a curta,
            # dos campos `base`, e a longa, do texto corrido.
            for padrao in (r"C[oó]digo TJMA, art\.\s*(\d{3})",
                           r"art\.\s*(\d{3})[^.]{0,20}do C[oó]digo de Normas"):
                for n in re.findall(padrao, texto):
                    achados.add(int(n))
    return tuple(f"art. {n}" for n in sorted(achados))


def _textos(valor):
    if isinstance(valor, str):
        yield valor
    elif isinstance(valor, dict):
        for v in valor.values():
            yield from _textos(v)
    elif isinstance(valor, (list, tuple)):
        for v in valor:
            yield from _textos(v)
