"""O PAPEL DA NOTIFICAÇÃO DO CONFRONTANTE — retificação de área e
georreferenciamento.

    «faça ser possível imprimir as notificações da usucapião e da
     georreferenciamento em pdf»            — o oficial, 21/09/2026

**AQUI NÃO HAVIA PAPEL NENHUM, e é essa a diferença para a usucapião.** Lá
`us_notificacao.montar` compõe o teor e o movimento o congela desde sempre; na
retificação o sistema **registrava que notificou** — `notificado_em`, `forma`,
`prazo_ate` — e o texto entregue ao confrontante era escrito fora do sistema,
à mão. Medido em 21/09/2026: `rt_confrontantes` não tinha uma coluna de teor, e
`retificacao.notificar` não recebia nem devolvia texto.

    Registro de que se notificou, sem o papel que sustenta a notificação, é
    uma linha dizendo que a serventia notificou alguém — e a prova do que foi
    dito não existe em lugar nenhum. É a mesma régua que a usucapião já seguia.

**O TEOR SAI DA NORMA, E CADA FRASE LEVA O ARTIGO.** As regras estão medidas no
Código de Normas do TJMA (`rt_tjma`), lido do PDF que está na casa:

  * **art. 598** — quem se notifica, e as quatro formas, nesta ordem;
  * **art. 598, § 1º** — onde se notifica;
  * **art. 599** — quinze dias ÚTEIS para impugnar, contados
    **individualmente** do recebimento;
  * **art. 599, § 1º** — *o silêncio presume a anuência*, e é por isso que ele
    tem de estar escrito no papel: quem não responde precisa saber, antes, o
    que o seu silêncio vale;
  * **art. 599, § 3º** — a impugnação fora do prazo, mas **antes da
    averbação**, ainda é recebida. Calar isso faria o papel afirmar um prazo
    mais duro que o da norma.

**ESTE MÓDULO SÓ MONTA TEXTO.** Não grava, não notifica, não conta prazo e não
decide nada — quem conta dia útil é o núcleo, que conhece os feriados desta
comarca, e quem decide é quem assina. Há teste que varre os nomes públicos.
"""
from __future__ import annotations

from typing import Any

import rt_tjma as NORMA


class NotificacaoError(ValueError):
    """Impedimento de regra, com frase pronta para o balcão."""


# O PRAZO QUE O PAPEL ANUNCIA É O DE IMPUGNAR (art. 599), e não o de
# «manifestar-se» do art. 598: é o da impugnação que corre individualmente e é
# ele que o silêncio consome.
PRAZO_DO_PAPEL = "IMPUGNAR"

MODELO = """{serventia}

NOTIFICAÇÃO — RETIFICAÇÃO DE ÁREA
Processo n. {numero}{do_ano}{sobre_matricula}

Ao(À) Sr.(a) {nome}{qualidade}
{endereco}

Na qualidade de confrontante do imóvel adiante descrito, fica V. S.ª
NOTIFICADO(A) de que tramita nesta Serventia pedido de retificação de área
formulado por {requerente}, nos termos dos arts. 594 e seguintes do Código de
Normas da Corregedoria Geral da Justiça do Estado do Maranhão.

DO IMÓVEL RETIFICANDO
{imovel}

{sobre_a_planta}O inteiro teor do pedido, a planta e o memorial descritivo
estão à disposição para exame nesta Serventia, no horário de expediente.

DO PRAZO
V. S.ª tem o prazo de {prazo_texto}, contado do recebimento desta, para
impugnar o pedido (art. 599 do Código de Normas). O prazo corre
individualmente para cada notificado.

DO SILÊNCIO
{silencio} ({silencio_artigo}).

A impugnação apresentada fora do prazo, mas antes da averbação da retificação,
ainda assim será recebida e processada ({atrasada_artigo}).

A impugnação deve ser fundamentada e apresentada por escrito nesta Serventia.

{lugar_e_data}

_______________________________________
{oficial}
{cargo}


- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
RECIBO

Recebi, nesta data, a notificação acima, referente ao processo n. {numero}.

Data: ____/____/________

Nome legível: ______________________________________________________

Documento: ________________________  Assinatura: ___________________
"""


def _texto(v: Any) -> str:
    return str(v or "").strip()


def _por_extenso(n: int) -> str:
    """Quinze vira «quinze». Só os números que os prazos desta seção usam."""
    nomes = {5: "cinco", 10: "dez", 15: "quinze", 30: "trinta"}
    return nomes.get(int(n), str(int(n)))


def prazo_para_impugnar() -> dict:
    """O prazo que o papel anuncia, lido da norma — e não escrito aqui."""
    return NORMA.prazo(PRAZO_DO_PAPEL)


def conferir(*, processo: dict, confrontante: dict) -> list[str]:
    """O que falta para o papel poder sair. SÓ LÊ — devolve as faltas.

    **A CONFERÊNCIA VEM ANTES DE O MOVIMENTO EXISTIR**, como na usucapião:
    notificação registrada sem papel que a sustente é pior que notificação
    nenhuma, porque ela consome o prazo de alguém que não foi avisado.
    """
    faltas = []
    if not _texto(confrontante.get("nome")):
        faltas.append("o nome do confrontante")
    if not _texto(confrontante.get("endereco")):
        faltas.append(
            "o endereço do confrontante — art. 598, § 1º: o indicado pelo "
            "requerente, o que consta da matrícula contígua, ou o do próprio "
            "imóvel que faz divisa")
    if not _texto(processo.get("numero")):
        faltas.append("o número do processo")
    if not _texto(processo.get("requerente_nome")):
        faltas.append("o requerente")
    return faltas


def montar(*, processo: dict, confrontante: dict, serventia: dict,
           hoje_extenso: str = "") -> str:
    """O teor da notificação do confrontante. SÓ MONTA — não grava nada.

    O texto que sair daqui é **congelado** pelo movimento que o expede: o que
    o confrontante leu é o de então, e remontá-lo depois traria o processo
    como ele está hoje. Mesma regra do termo do Registro Civil, da certidão do
    Protesto e da notificação da usucapião.
    """
    faltas = conferir(processo=processo, confrontante=confrontante)
    if faltas:
        raise NotificacaoError(
            "A notificação não sai sem: " + "; ".join(faltas) + ".")

    p = prazo_para_impugnar()
    dias = int(p["dias"])
    uteis = " úteis" if p.get("uteis") else ""

    partes: list[str] = []
    for rotulo, chave in (("Matrícula", "matricula_numero"),
                          ("Área na matrícula", "area_na_matricula"),
                          ("Área pretendida", "area_pretendida"),
                          ("Perímetro", "perimetro")):
        if _texto(processo.get(chave)):
            partes.append(f"{rotulo}: {_texto(processo[chave])}")
    if _texto(confrontante.get("divisa_afetada")):
        partes.append("Divisa que toca o imóvel de V. S.ª: "
                      + _texto(confrontante["divisa_afetada"]))
    if _texto(confrontante.get("matricula_contigua")):
        partes.append("Imóvel contíguo de V. S.ª: matrícula "
                      + _texto(confrontante["matricula_contigua"]))
    if not partes:
        partes.append("A descrição está no pedido, à disposição na Serventia.")

    profissional = _texto(processo.get("profissional_nome"))
    conselho = _texto(processo.get("profissional_conselho"))
    art = _texto(processo.get("art_numero"))
    sobre_a_planta = ""
    if profissional:
        registro = _texto(processo.get("profissional_registro"))
        credencial = " ".join(x for x in (conselho, registro) if x)
        sobre_a_planta = (
            f"A planta e o memorial descritivo foram assinados por "
            f"{profissional}"
            + (f" ({credencial})" if credencial else "")
            + (f", ART/TRT n. {art}" if art else "") + ".\n\n")

    #  O ANO SO ENTRA SE O NUMERO NAO O TROUXER — nesta seccao o processo se
    #  numera «9/2026», e repetir daria «9/2026/2026». Na usucapiao e o
    #  contrario (o numero e «2026.001» e o ano vem separado), e por isso a
    #  regra e olhar o numero em vez de copiar o vizinho.
    ano = processo.get("ano")
    numero = _texto(processo.get("numero"))
    if ano and str(ano) in numero:
        ano = None
    matricula = _texto(processo.get("matricula_numero"))
    qualidade = _texto(confrontante.get("papel"))
    return MODELO.format(
        serventia=_texto(serventia.get("nome")),
        numero=numero,
        do_ano=f"/{ano}" if ano else "",
        sobre_matricula=f" — matrícula {matricula}" if matricula else "",
        nome=_texto(confrontante.get("nome")),
        qualidade=f", {qualidade.lower()}" if qualidade else "",
        endereco=_texto(confrontante.get("endereco")),
        requerente=_texto(processo.get("requerente_nome")),
        imovel="\n".join(partes),
        sobre_a_planta=sobre_a_planta,
        prazo_texto=f"{dias} ({_por_extenso(dias)}) dias{uteis}",
        silencio=_texto(NORMA.SILENCIO_VALE_ANUENCIA["o_que"]),
        silencio_artigo=_texto(NORMA.SILENCIO_VALE_ANUENCIA["artigo"]),
        atrasada_artigo=_texto(NORMA.IMPUGNACAO_ATRASADA_ENTRA["artigo"]),
        lugar_e_data=_texto(hoje_extenso),
        oficial=_texto(serventia.get("oficial")) or "____________",
        cargo=_texto(serventia.get("cargo")) or "Oficial",
    )
