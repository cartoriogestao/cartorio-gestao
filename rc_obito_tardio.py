"""Óbito fora do prazo — a regra que avisa, e só.

    «tirar o óbito tardio, e indicar a necessidade de determinação judicial»
        — o oficial, 30/08/2026

POR QUE NÃO HÁ PROCEDIMENTO AQUI
    Cheguei a montar um: fases, exigências, acompanhamento do pedido em juízo.
    O oficial mandou tirar, e tem razão — **o procedimento não é da serventia**.

    O art. 258 do Código de Normas do TJMA:

        «Excedido o prazo legal, nos termos do art. 78 da Lei nº 6.015/1973, o
         assento de óbito só será lavrado por determinação judicial.
         Parágrafo único. O pedido de registro de óbito tardio deverá indicar
         os elementos exigidos no art. 255 deste Código e ser subscrito pelo
         declarante e duas testemunhas, os quais poderão ser inquiridos
         pelo(a) juiz(íza) competente, que decidirá depois de ouvido o
         Ministério Público.»

    Quem instrui, inquire e decide é o **juízo**, ouvido o **Ministério
    Público**. Um módulo aqui que fingisse acompanhar isso estaria
    representando um processo que não corre neste sistema — e telas assim
    envelhecem mentindo, porque ninguém as atualiza com o que acontece no
    fórum.

    **O que a serventia precisa é saber a hora de parar e dizer isso.** É o
    que este arquivo faz.

    O óbito tardio, portanto, **não se parece com o registro tardio de
    nascimento**: aquele o oficial lavra (art. 249, administrativo); este não.
"""
from __future__ import annotations

from datetime import date
from typing import Any

ARTIGO = "art. 258 do Código de Normas do TJMA; art. 78 da Lei nº 6.015/1973"

# O PRAZO. Art. 78 da Lei 6.015 manda lavrar em 24 horas; o art. 254, § 3º do
# Código de Normas admite lavrar depois «com a maior urgência», dentro dos
# prazos do art. 50 — quinze dias, ou três meses onde o lugar fica a mais de
# trinta quilômetros da sede.
PRAZO_DIAS = 15
PRAZO_DIAS_DISTANTE = 90
ARTIGO_DO_PRAZO = "art. 78 da Lei nº 6.015/1973 c/c art. 254, § 3º"

AVISO = (
    "**Este óbito está fora do prazo.** Excedido o prazo legal, o assento de "
    "óbito **só será lavrado por determinação judicial** (art. 258 do Código "
    "de Normas do TJMA). A serventia não o lavra no balcão."
)

O_QUE_O_PEDIDO_LEVA = (
    "O pedido feito em juízo deve **indicar os elementos do art. 255** e ser "
    "**subscrito pelo declarante e por duas testemunhas**, que poderão ser "
    "inquiridos. O juiz decide **depois de ouvido o Ministério Público**."
)

# A DO SEMPRE, E ISTO É REGRA DESTA CASA — não da norma.
#
#   O art. 254 admitiria, onde não houver médico, «duas pessoas qualificadas
#   que tiverem presenciado ou verificado a morte». O oficial decidiu exigir a
#   Declaração de Óbito em todo caso, inclusive aqui. Fica dito que é escolha
#   da casa: quem ler daqui a dois anos precisa saber qual das duas coisas
#   está lendo.
DECLARACAO_DE_OBITO_SEMPRE = True
SOBRE_A_DO = (
    "**A Declaração de Óbito é exigida em todo caso** — decisão desta casa, "
    "de 30/08/2026, mais estrita que o art. 254, que admitiria duas pessoas "
    "qualificadas onde não houvesse médico."
)


class ObitoTardioError(ValueError):
    """Erro de regra, em português de balcão."""


def _dia(valor: Any) -> date | None:
    texto = ("" if valor is None else str(valor)).strip()[:10]
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return None


def dias_desde(data_obito: Any, hoje: Any) -> int:
    """Quantos dias correram desde o falecimento. **Corridos.**

    O art. 78 não qualifica o prazo, e prazo que a norma não qualifica se conta
    corrido — a mesma leitura que se fez no art. 253, § 2º da FUNAI.
    """
    obito, agora = _dia(data_obito), _dia(hoje)
    if not obito or not agora:
        raise ObitoTardioError(
            "Preciso da data do falecimento e da data de hoje, as duas em "
            "aaaa-mm-dd, para contar o prazo.")
    return (agora - obito).days


def esta_fora_do_prazo(data_obito: Any, hoje: Any, *,
                       distante: bool = False) -> bool:
    """Se o prazo foi excedido — e por isso o caminho é o judicial.

    `distante` é o lugar a mais de trinta quilômetros da sede, que o art. 50
    trata com prazo maior. **Não se adivinha**: quem sabe se o lugar é distante
    é quem está atendendo, e por isso é parâmetro e não dedução.
    """
    limite = PRAZO_DIAS_DISTANTE if distante else PRAZO_DIAS
    return dias_desde(data_obito, hoje) > limite


def situacao(data_obito: Any, hoje: Any, *, distante: bool = False) -> dict:
    """O que dizer ao balcão sobre este óbito. Só calcula.

    **NÃO TRAVA A LAVRATURA, E ISSO NÃO É DESCUIDO.** Quem decide se o caso é
    tardio é quem tem os papéis na mão: a data do falecimento pode estar errada
    na declaração, o lugar pode ser dos distantes, pode haver determinação
    judicial já em mãos. O sistema **diz o que a norma manda** e deixa a
    decisão com quem responde por ela.
    """
    dias = dias_desde(data_obito, hoje)
    limite = PRAZO_DIAS_DISTANTE if distante else PRAZO_DIAS
    # A CONTA E A DE `esta_fora_do_prazo`, E NAO UMA COPIA DELA. Refaze-la aqui
    # daria duas leituras do mesmo prazo, e elas divergem no primeiro conserto
    # — foi o varredor de funcao sem tela que apontou, em 30/08/2026.
    fora = esta_fora_do_prazo(data_obito, hoje, distante=distante)
    return {
        "dias": dias,
        "limite": limite,
        "fora_do_prazo": fora,
        "aviso": AVISO if fora else "",
        "o_que_o_pedido_leva": O_QUE_O_PEDIDO_LEVA if fora else "",
        "artigo": ARTIGO if fora else ARTIGO_DO_PRAZO,
    }
