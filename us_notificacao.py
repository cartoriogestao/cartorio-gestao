"""A notificação do usucapião — relatos #30 e #21 do oficial, 30/08/2026.

    «o módulo de processo de usucapião precisa ter campo para subir as
     informações necessárias aos atos que o cartório precisará praticar, como as
     notificações, e gerar modelo e manual de como efetuar»

    «o cadastramento é muito simples e não parece ser maduro para processar um
     usucapião no RI com confiança»

O QUE FALTAVA, MEDIDO NO PRÓPRIO MÓDULO
    A notificação **já existia como movimento**: `us_movimentos` guarda o
    destinatário, o papel dele, o prazo e a resposta. O que não existia era
    tudo o que faz dela um **ato praticado**:

    1. **O endereço.** A norma dá três lugares possíveis (art. 598, § 1º) e o
       sistema não guardava nenhum — quem fosse expedir teria de procurar.
    2. **A forma, e em que tentativa se está.** São quatro formas, **em ordem**,
       e o edital só cabe «caso frustradas as tentativas anteriores». Sem
       registrar a tentativa, ninguém prova que as anteriores se frustraram.
    3. **O papel.** Não havia modelo: a notificação saía como o escrevente
       escrevesse, e duas sairiam diferentes.
    4. **O prazo.** O rito tem prazo e o sistema não o sabia — `PRAZOS` do
       usucapião não trazia um só.

A REGRA NÃO É INVENTADA AQUI: ELA É IMPORTADA
    **O art. 754 do Código de Normas manda aplicar, na notificação de
    confrontante, «no que couber, o procedimento de retificação de registro».**
    E este sistema já leu esses artigos — `rt_tjma.py`, arts. 587 a 620.

    Por isso as formas e os endereços **vêm de lá**, e não são recopiados. Copiar
    produziria duas listas para divergirem no primeiro conserto — é a
    `normalizar_nome` pela quinta vez neste projeto: onde a igualdade importa,
    ela se constrói, não se supõe. Há teste que compara as duas.

A PROCEDÊNCIA DE CADA PRAZO FICA MARCADA, e isso não é zelo
    `MEDIDO` é o que se leu **no PDF que está na casa** — o Código de Normas do
    TJMA. `CITADO` é o que vem da Lei de Registros Públicos, cujo texto oficial
    **não foi lido aqui dentro**.

    A diferença importa porque um prazo errado numa notificação não aparece
    como erro: aparece como impugnação perdida meses depois. Onde a procedência
    é `CITADO`, **o sistema mostra o prazo e não o impõe** — quem confirma é
    quem responde pela serventia, com a lei aberta.

O QUE ESTE MÓDULO NÃO FAZ
    **Não expede, não entrega e não dá por notificado.** Ele monta o papel e diz
    o que falta. Quem entrega é a serventia, e o que prova a entrega é o
    comprovante que volta — não uma linha que alguém digitou.
"""
from __future__ import annotations

from typing import Any

import rt_tjma as RT

# AS FORMAS E OS ENDEREÇOS VÊM DA RETIFICAÇÃO — art. 754 manda aplicá-la.
#
#   Não são recopiados: são os mesmos objetos. Se o Código mudar e `rt_tjma`
#   for corrigido, isto acompanha no mesmo instante.
FORMAS = RT.COMO_NOTIFICAR
ONDE = RT.ONDE_NOTIFICAR
BASE_DA_REMISSAO = {
    "artigo": "Código TJMA, art. 754",
    "o_que": "A notificação de confrontante observa, no que couber, o "
             "procedimento de **retificação de registro** — arts. 587 a 620.",
}

FORMA_POR_CHAVE = {f["forma"]: f for f in FORMAS}
ORDEM_DAS_FORMAS = tuple(f["forma"] for f in FORMAS)

# O EDITAL É O ÚLTIMO, e a ordem é da norma: «caso frustradas as tentativas
# anteriores». Um sistema que o oferecesse de saída faria a serventia publicar
# edital sem ter tentado — e o edital custa e demora.
FORMA_DE_ULTIMO_RECURSO = "EDITAL"

# ------------------------------------------------------------- os prazos
#
# **A PROCEDÊNCIA DE CADA UM FICA MARCADA.** Ver o cabeçalho.
MEDIDO = "MEDIDO"        # lido no Código de Normas do TJMA, que está na casa
CITADO = "CITADO"        # da Lei 6.015/1973, cujo texto não foi lido aqui

PRAZOS: tuple[dict, ...] = (
    {"chave": "CONFRONTANTE", "dias": 15, "uteis": True, "procedencia": MEDIDO,
     "base": "Código TJMA, art. 599, c/c art. 754",
     "de_quem": "CONFRONTANTE",
     "o_que": "Impugnar, contado **individualmente para cada notificado**, do "
              "recebimento da notificação ou da última publicação do edital"},
    {"chave": "ENTE_PUBLICO", "dias": 15, "uteis": True, "procedencia": MEDIDO,
     "base": "Código TJMA, art. 599, § 4º, c/c art. 754",
     "de_quem": "ENTE_PUBLICO",
     "o_que": "Prorrogação por igual período para União, Estado e Município, "
              "**mediante solicitação justificada dentro do prazo original**"},
    {"chave": "TITULAR_TABULAR", "dias": 15, "uteis": False,
     "procedencia": CITADO,
     "base": "Lei 6.015/1973, art. 216-A, § 2º",
     "de_quem": "TITULAR_TABULAR",
     "o_que": "O titular que consta do registro manifesta consentimento "
              "expresso — **e o silêncio é interpretado como concordância**"},
)
PRAZO_POR_CHAVE = {p["chave"]: p for p in PRAZOS}

# O SILÊNCIO TEM EFEITO, e é por isso que o prazo do titular tabular é o mais
# perigoso de errar: errado para menos, dá-se por concordante quem ainda tinha
# prazo. `usucapiao.RESPOSTAS` já trata o silêncio como valor, e não como
# ausência de valor — aqui a consequência é dita junto do prazo.
SILENCIO_CONCORDA = {
    "base": "Lei 6.015/1973, art. 216-A, § 2º",
    "procedencia": CITADO,
    "o_que": "Decorrido o prazo sem manifestação, o silêncio é interpretado "
             "como **concordância** — e por isso o prazo errado para menos "
             "produz anuência de quem ainda podia impugnar.",
}

# ------------------------------------------- o que o papel exige para sair
#
# **CAMPO QUE FALTA É DITO ANTES, e não depois de o papel sair torto.** Cada um
# aparece no papel; sem ele o texto sairia com um buraco que ninguém percebe ao
# assinar.
EXIGE: tuple[dict, ...] = (
    {"campo": "destinatario", "rotulo": "Nome de quem se notifica"},
    {"campo": "destinatario_papel",
     "rotulo": "Em que qualidade ele é notificado (confrontante, titular, "
               "credor com ônus na matrícula, ente público)"},
    {"campo": "endereco", "rotulo": "Endereço para onde o papel vai",
     "nota": ONDE["o_que"], "base": ONDE["artigo"]},
    {"campo": "forma", "rotulo": "Por qual das quatro formas se notifica"},
    {"campo": "prazo_dias", "rotulo": "Prazo para se manifestar"},
)


class NotificacaoError(ValueError):
    """Erro de regra, em português de balcão."""


def _texto(v: Any) -> str:
    return "" if v is None else str(v).strip()


def prazo(chave: str) -> dict:
    """O prazo daquele destinatário, **com a procedência**. Só calcula."""
    p = PRAZO_POR_CHAVE.get(chave)
    if p is None:
        raise NotificacaoError(
            f"Não conheço o prazo «{chave}». Conheço: "
            + ", ".join(PRAZO_POR_CHAVE) + ".")
    return p


def forma_seguinte(tentadas: Any) -> str | None:
    """A próxima forma a tentar, na ordem da norma. Só calcula.

    **O EDITAL É O ÚLTIMO E A ORDEM É DA NORMA** — «caso frustradas as
    tentativas anteriores» (art. 598). Oferecer o edital de saída faria a
    serventia publicar sem ter tentado, e o edital custa e demora.

    Devolve `None` quando não há mais o que tentar: aí não é a vez de escolher
    forma, é a vez de o oficial decidir.
    """
    ja = {_texto(x).upper() for x in (tentadas or [])}
    for f in ORDEM_DAS_FORMAS:
        if f not in ja:
            return f
    return None


def conferir(dados: dict) -> list[str]:
    """O que falta para o papel poder sair. Só calcula — **não recusa**.

    Devolve a lista do que falta, em português. Quem recusa é `montar`, e
    recusa **antes** de imprimir: papel de notificação com buraco é papel que
    alguém assina sem ver.
    """
    faltando = []
    for e in EXIGE:
        if not _texto(dados.get(e["campo"])):
            faltando.append(e["rotulo"])
    forma = _texto(dados.get("forma")).upper()
    if forma and forma not in FORMA_POR_CHAVE:
        faltando.append(
            f"a forma «{forma}» não é uma das quatro da norma: "
            + ", ".join(ORDEM_DAS_FORMAS))
    return faltando


# ------------------------------------------------------------- o papel


CABECA = ("NOTIFICAÇÃO — PROCEDIMENTO DE USUCAPIÃO EXTRAJUDICIAL")

CORPO = """{cabeca}

Autos nº {numero}{do_ano} — {modalidade}
Requerente: {requerente}

NOTIFICADO(A): {destinatario}
Na qualidade de: {papel}
Endereço: {endereco}

Pelo presente, fica V. Sa. NOTIFICADO(A) de que tramita nesta serventia \
procedimento de USUCAPIÃO EXTRAJUDICIAL, requerido nos termos do art. 216-A da \
Lei nº 6.015/1973, sobre o imóvel a seguir descrito:

{imovel}

{sobre_a_posse}Fica V. Sa. cientificado(a) de que poderá MANIFESTAR-SE sobre o \
pedido no prazo de {prazo_texto}, contado do recebimento desta.

{sobre_o_silencio}

A manifestação, a anuência ou a impugnação podem ser apresentadas nesta \
serventia, por escrito, ou por qualquer meio que permita a identificação de \
quem as apresenta.

{lugar_e_data}

_______________________________________
{oficial}
{cargo}
{serventia}

--------------------------------------------------------------------------
RECIBO — a ser assinado por quem recebe

Recebi a notificação acima, em ____/____/________, às ______h______.

Nome de quem recebe: ______________________________________________________
Documento: ________________________________  Assinatura: __________________

Forma da notificação: {forma_texto}
{base_da_forma}"""


def montar(*, processo: dict, notificacao: dict, serventia: dict,
           hoje_extenso: str = "") -> str:
    """O papel da notificação, pronto para imprimir e entregar. Só monta.

    **RECUSA ANTES DE IMPRIMIR**, e não depois: papel de notificação com buraco
    é papel que alguém assina sem ver, e o buraco só aparece quando o notificado
    disser que não entendeu do que foi notificado.

    **O RECIBO VAI NO MESMO PAPEL.** O que prova a notificação não é a linha
    que alguém digitou no sistema: é o comprovante que volta assinado — e um
    recibo que sai em folha separada é o recibo que se perde.
    """
    faltando = conferir(notificacao)
    if faltando:
        raise NotificacaoError(
            "A notificação não sai sem: " + "; ".join(faltando) + ".")

    p = PRAZO_POR_CHAVE.get(_texto(notificacao.get("prazo_chave")))
    dias = int(notificacao.get("prazo_dias") or (p or {}).get("dias") or 0)
    uteis = bool((p or {}).get("uteis"))
    prazo_texto = (f"{dias} ({_por_extenso(dias)}) dias"
                   + (" úteis" if uteis else ""))

    forma = _texto(notificacao.get("forma")).upper()
    f = FORMA_POR_CHAVE.get(forma, {})

    imovel = _texto(processo.get("imovel_descricao")) or "____________"
    endereco_imovel = _texto(processo.get("imovel_endereco"))
    municipio = _texto(processo.get("imovel_municipio"))
    area = _texto(processo.get("imovel_area"))
    partes_do_imovel = [imovel]
    if endereco_imovel:
        partes_do_imovel.append(f"Situado em: {endereco_imovel}")
    if municipio:
        partes_do_imovel.append(f"Município: {municipio}"
                                + (f"/{_texto(processo.get('imovel_uf'))}"
                                   if _texto(processo.get("imovel_uf")) else ""))
    if area:
        partes_do_imovel.append(f"Área: {area}")

    # O QUE NÃO SE SABE NÃO SE AFIRMA. A posse alegada só entra se estiver no
    # processo — uma frase genérica sobre posse num papel que a serventia
    # assina é afirmação sobre fato que ninguém mediu.
    posse = _texto(processo.get("posse_tempo_alegado"))
    desde = _texto(processo.get("posse_inicio"))
    sobre_a_posse = ""
    if posse or desde:
        pedaco = posse or f"desde {desde}"
        sobre_a_posse = (f"O requerente alega posse {pedaco}.\n\n")

    sobre_o_silencio = (
        "DECORRIDO O PRAZO SEM MANIFESTAÇÃO, O SILÊNCIO SERÁ INTERPRETADO "
        "COMO CONCORDÂNCIA, na forma do art. 216-A, § 2º, da Lei nº "
        "6.015/1973.")

    ano = processo.get("ano")
    return CORPO.format(
        cabeca=CABECA,
        numero=_texto(processo.get("numero")) or "____",
        do_ano=f"/{ano}" if ano else "",
        modalidade=_texto(processo.get("modalidade_rotulo")
                          or processo.get("modalidade")),
        requerente=_texto(processo.get("requerente_nome")) or "____________",
        destinatario=_texto(notificacao.get("destinatario")),
        papel=_texto(notificacao.get("destinatario_papel")),
        endereco=_texto(notificacao.get("endereco")),
        imovel="\n".join(partes_do_imovel),
        sobre_a_posse=sobre_a_posse,
        prazo_texto=prazo_texto,
        sobre_o_silencio=sobre_o_silencio,
        lugar_e_data=_texto(hoje_extenso),
        oficial=_texto(serventia.get("oficial")) or "____________",
        cargo=_texto(serventia.get("cargo")) or "Oficial",
        serventia=_texto(serventia.get("nome")) or "",
        forma_texto=_texto(f.get("o_que")) or forma,
        base_da_forma=f"({_texto(f.get('artigo'))})" if f.get("artigo") else "",
    )


def _por_extenso(n: int) -> str:
    """O número por extenso, para os prazos que o papel cita.

    Curto de propósito: os prazos desta norma são 5, 10, 15 e 30. Um conversor
    geral aqui seria peça a mais para manter, e `livro_nucleo.por_extenso` já
    existe para o resto da casa.
    """
    nomes = {5: "cinco", 10: "dez", 15: "quinze", 30: "trinta"}
    return nomes.get(int(n), str(n))


# ------------------------------------------------------------- o manual


MANUAL: tuple[dict, ...] = (
    {"passo": 1,
     "o_que": "Reúna quem precisa ser notificado",
     "como": "Titulares que constam do registro do imóvel usucapiendo e dos "
             "imóveis confinantes, e os cônjuges deles. Quem **assinou a "
             "planta** já anuiu e não se notifica.",
     "base": "LRP, art. 216-A, § 2º"},
    {"passo": 2,
     "o_que": "Acrescente os credores com ônus na matrícula",
     "como": "Havendo servidão, hipoteca ou usufruto, os credores reais **têm "
             "de ser notificados** — o ônus não impede o reconhecimento, mas "
             "notificar é condição.",
     "base": "Código TJMA, arts. 617 e 759"},
    {"passo": 3,
     "o_que": "Escolha o endereço",
     "como": ONDE["o_que"],
     "base": ONDE["artigo"]},
    {"passo": 4,
     "o_que": "Tente as formas NA ORDEM",
     "como": "Pessoalmente pelo oficial; pelo RTD da comarca do imóvel ou do "
             "domicílio; por correio com aviso de recebimento. **O edital só "
             "cabe depois de frustradas as anteriores** — e a frustração "
             "precisa estar registrada, senão ninguém prova que houve.",
     "base": "Código TJMA, art. 598"},
    {"passo": 5,
     "o_que": "Imprima o papel com o recibo junto",
     "como": "O sistema monta a notificação com o recibo no mesmo papel. O que "
             "prova a notificação é o comprovante que **volta assinado**, e "
             "não a linha que alguém digitou no sistema.",
     "base": "—"},
    {"passo": 6,
     "o_que": "Junte o comprovante ao processo",
     "como": "Como peça, no tipo «Comprovante de notificação». Sem ele, a "
             "notificação existe no papel e não existe nos autos.",
     "base": "—"},
    {"passo": 7,
     "o_que": "Conte o prazo de cada um, separadamente",
     "como": "O prazo é contado **individualmente para cada notificado**, do "
             "recebimento dele — e não de um marco comum. Contar de uma data "
             "só encurta o prazo de quem recebeu depois.",
     "base": "Código TJMA, art. 599, c/c art. 754"},
    {"passo": 8,
     "o_que": "Registre a resposta — inclusive o silêncio",
     "como": "Decorrido o prazo sem manifestação, o silêncio é **concordância**. "
             "Ele é uma resposta, e por isso se lança como resposta: um campo "
             "vazio não diz se ninguém respondeu ou se ninguém perguntou.",
     "base": "LRP, art. 216-A, § 2º"},
    {"passo": 9,
     "o_que": "Se não der para identificar todo mundo, o caminho é outro",
     "como": "Áreas extensas com muitos confinantes, ocupações irregulares ou "
             "assentamentos: **constatado por ATA NOTARIAL**, a notificação vai "
             "por edital — preservada a impugnação de qualquer ocupante que "
             "demonstre essa condição.",
     "base": "Código TJMA, art. 595"},
)


# =========================================================================
# O EDITAL, e o oficio aos entes publicos
# =========================================================================
#
# **SAO OS OUTROS DOIS ATOS DO RITO QUE PRODUZEM PAPEL**, e ate 30/08/2026
# nenhum dos dois tinha modelo: `EDITAL` e `CIENCIA_ENTES` eram etapas com
# nome e sem papel, e quem chegasse nelas escrevia o documento a mao.

import us_tjma as TJMA

# OS TRES ENTES, e os tres se avisam — art. 216-A, § 3o.
ENTES = ("União", "Estado", "Município")

PRAZO_DOS_ENTES = {
    "chave": "ENTE_PUBLICO", "dias": 15, "uteis": False, "procedencia": CITADO,
    "base": "Lei 6.015/1973, art. 216-A, § 3º",
    "o_que": "A União, o Estado e o Município são cientificados para se "
             "manifestarem sobre o pedido",
}

PRAZO_DO_EDITAL = {
    "chave": "EDITAL", "dias": 15, "uteis": False, "procedencia": CITADO,
    "base": "Lei 6.015/1973, art. 216-A, § 4º",
    "o_que": "Terceiros eventualmente interessados se manifestam, contado do "
             "**início do prazo** — que não é o dia da disponibilização",
}


EDITAL = """EDITAL DE USUCAPIÃO EXTRAJUDICIAL

{serventia}
{oficial}, {cargo}, FAZ SABER a quantos este edital virem ou dele \
conhecimento tiverem que, nos termos do art. 216-A da Lei nº 6.015/1973, \
tramita nesta serventia procedimento de USUCAPIÃO EXTRAJUDICIAL:

Autos nº {numero}{do_ano} — {modalidade}
Requerente: {requerente}

IMÓVEL:
{imovel}

{sobre_a_origem}{sobre_a_posse}FICAM CIENTIFICADOS terceiros eventualmente \
interessados de que poderão MANIFESTAR-SE no prazo de {prazo_texto}, contado \
na forma do art. 755, § 1º, do Código de Normas da CGJ/TJMA.

A manifestação pode ser apresentada nesta serventia, por escrito.

{lugar_e_data}

_______________________________________
{oficial}
{cargo}"""


def montar_edital(*, processo: dict, serventia: dict, hoje_extenso: str = "",
                  imovel_sem_origem: bool = False) -> str:
    """O edital para terceiros interessados. Só monta.

    **A CIRCUNSTÂNCIA DA ORIGEM VAI ESCRITA, quando é o caso** — art. 755, § 2º
    do Código de Normas: imóvel sem origem registrária, ou cuja origem não foi
    encontrada, tem de consignar isso **expressamente**. Um edital que cala
    sobre isso é edital que se refaz.

    **O PRAZO NÃO CONTA DA PUBLICAÇÃO, e o papel diz isso.** São dois «primeiro
    dia útil seguinte» encadeados (art. 755, § 1º): um para achar a data da
    publicação, outro para começar a contar. Quem lê com pressa conta da
    disponibilização — e num edital, errar por um dia é recomeçar o edital.
    Quem calcula é `us_tjma.inicio_do_prazo`, que sabe dos feriados desta
    comarca; aqui o papel remete ao artigo em vez de afirmar uma data que o
    montador não tem como saber.
    """
    faltando = [nome for nome, valor in
                (("o número dos autos", processo.get("numero")),
                 ("o requerente", processo.get("requerente_nome")),
                 ("a descrição do imóvel", processo.get("imovel_descricao")))
                if not _texto(valor)]
    if faltando:
        raise NotificacaoError(
            "O edital não sai sem: " + ", ".join(faltando) + ".")

    partes = [_texto(processo.get("imovel_descricao"))]
    for rotulo, chave in (("Situado em", "imovel_endereco"),
                          ("Município", "imovel_municipio"),
                          ("Área", "imovel_area")):
        if _texto(processo.get(chave)):
            partes.append(f"{rotulo}: {_texto(processo[chave])}")

    sobre_a_origem = ""
    if imovel_sem_origem:
        sobre_a_origem = (
            "CONSIGNA-SE EXPRESSAMENTE que o imóvel não tem origem "
            "registrária, ou que a origem não foi encontrada, na forma do "
            "art. 755, § 2º, do Código de Normas da CGJ/TJMA.\n\n")

    posse = _texto(processo.get("posse_tempo_alegado"))
    sobre_a_posse = f"O requerente alega posse {posse}.\n\n" if posse else ""

    ano = processo.get("ano")
    return EDITAL.format(
        serventia=_texto(serventia.get("nome")),
        oficial=_texto(serventia.get("oficial")) or "____________",
        cargo=_texto(serventia.get("cargo")) or "Oficial",
        numero=_texto(processo.get("numero")),
        do_ano=f"/{ano}" if ano else "",
        modalidade=_texto(processo.get("modalidade_rotulo")
                          or processo.get("modalidade")),
        requerente=_texto(processo.get("requerente_nome")),
        imovel="\n".join(partes),
        sobre_a_origem=sobre_a_origem,
        sobre_a_posse=sobre_a_posse,
        prazo_texto=f"{PRAZO_DO_EDITAL['dias']} "
                    f"({_por_extenso(PRAZO_DO_EDITAL['dias'])}) dias",
        lugar_e_data=_texto(hoje_extenso))


OFICIO_AO_ENTE = """{serventia}

Ofício — procedimento de usucapião extrajudicial
Autos nº {numero}{do_ano}

Ao/À {ente}

Senhor(a) Representante,

Comunico a V. Sa. que tramita nesta serventia procedimento de USUCAPIÃO \
EXTRAJUDICIAL, requerido por {requerente} nos termos do art. 216-A da Lei nº \
6.015/1973, sobre o imóvel a seguir descrito:

{imovel}

{sobre_a_posse}Nos termos do § 3º do referido artigo, fica esse ente \
CIENTIFICADO para, querendo, manifestar-se no prazo de {prazo_texto}.

{lugar_e_data}

_______________________________________
{oficial}
{cargo}"""


def montar_oficio_ao_ente(*, ente: str, processo: dict, serventia: dict,
                          hoje_extenso: str = "") -> str:
    """O ofício de ciência a um dos três entes públicos. Só monta.

    **SÃO TRÊS, e os três se avisam** — art. 216-A, § 3º. Avisar dois e
    esquecer o terceiro é vício que só aparece quando o ente que faltou aparecer
    reclamando, depois de o registro estar feito.
    """
    if _texto(ente) not in ENTES:
        raise NotificacaoError(
            f"«{ente}» não é um dos entes que se cientificam. São: "
            + ", ".join(ENTES) + ".")
    faltando = [nome for nome, valor in
                (("o número dos autos", processo.get("numero")),
                 ("o requerente", processo.get("requerente_nome")),
                 ("a descrição do imóvel", processo.get("imovel_descricao")))
                if not _texto(valor)]
    if faltando:
        raise NotificacaoError(
            "O ofício não sai sem: " + ", ".join(faltando) + ".")

    partes = [_texto(processo.get("imovel_descricao"))]
    for rotulo, chave in (("Situado em", "imovel_endereco"),
                          ("Município", "imovel_municipio"),
                          ("Área", "imovel_area")):
        if _texto(processo.get(chave)):
            partes.append(f"{rotulo}: {_texto(processo[chave])}")
    posse = _texto(processo.get("posse_tempo_alegado"))
    ano = processo.get("ano")
    return OFICIO_AO_ENTE.format(
        serventia=_texto(serventia.get("nome")),
        numero=_texto(processo.get("numero")),
        do_ano=f"/{ano}" if ano else "",
        ente=_texto(ente),
        requerente=_texto(processo.get("requerente_nome")),
        imovel="\n".join(partes),
        sobre_a_posse=f"O requerente alega posse {posse}.\n\n" if posse else "",
        prazo_texto=f"{PRAZO_DOS_ENTES['dias']} "
                    f"({_por_extenso(PRAZO_DOS_ENTES['dias'])}) dias",
        lugar_e_data=_texto(hoje_extenso),
        oficial=_texto(serventia.get("oficial")) or "____________",
        cargo=_texto(serventia.get("cargo")) or "Oficial")


MANUAL_DO_EDITAL: tuple[dict, ...] = (
    {"passo": 1, "o_que": "Publique na Central, e não no jornal",
     "como": TJMA.EDITAL_NA_CENTRAL["texto"],
     "base": TJMA.EDITAL_NA_CENTRAL["base"]},
    {"passo": 2, "o_que": "Se o imóvel não tem origem, o edital diz isso",
     "como": TJMA.EDITAL_SEM_ORIGEM["texto"]
             + " **Um edital que cala sobre isso é edital que se refaz.**",
     "base": TJMA.EDITAL_SEM_ORIGEM["base"]},
    {"passo": 3, "o_que": "Anote a data em que foi disponibilizado",
     "como": "É dela que sai tudo o mais — e ela **não** é a data da "
             "publicação.",
     "base": "Código TJMA, art. 755, § 1º"},
    {"passo": 4, "o_que": "Conte o prazo com os DOIS saltos",
     "como": "A data da publicação é o primeiro dia útil **depois** da "
             "disponibilização; o prazo conta do primeiro dia útil **depois** "
             "dessa data. **São dois, e não um** — quem lê com pressa conta da "
             "disponibilização, e num edital errar por um dia é recomeçar o "
             "edital. O sistema calcula, com os feriados desta comarca.",
     "base": "Código TJMA, art. 755, § 1º"},
    {"passo": 5, "o_que": "Junte o edital publicado aos autos",
     "como": "Como peça, no tipo «Edital publicado», com o protocolo que a "
             "Central devolveu. Sem ele, o edital existe e não se prova.",
     "base": "—"},
)

MANUAL_DOS_ENTES: tuple[dict, ...] = (
    {"passo": 1, "o_que": "São três, e os três se avisam",
     "como": "União, Estado e Município. **Avisar dois e esquecer o terceiro** "
             "é vício que só aparece quando o que faltou reclamar — depois de o "
             "registro estar feito.",
     "base": "LRP, art. 216-A, § 3º"},
    {"passo": 2, "o_que": "Cada um recebe o seu ofício",
     "como": "O sistema monta um por ente, com o imóvel descrito e o prazo.",
     "base": "—"},
    {"passo": 3, "o_que": "O prazo deles pode dobrar",
     "como": "União, Estado e Município têm prorrogação por igual período "
             "**mediante solicitação justificada dentro do prazo original** — "
             "não é automática, e não é de ofício.",
     "base": "Código TJMA, art. 599, § 4º, c/c art. 754"},
    {"passo": 4, "o_que": "Junte os comprovantes",
     "como": "Os três, como peça. O que prova a ciência é o comprovante que "
             "volta, e não a linha no sistema.",
     "base": "—"},
)
