"""As fases da ficha do título de Protesto: o que a régua mostra e onde a ficha abre. SÓ LÊ.

ONZE QUADROS E UM FORMULÁRIO POR ATO NA MESMA PÁGINA — projeto do novo layout, 30/10/2026. Os quadros
continuam os mesmos, nas mesmas rotas. O que muda é quais aparecem juntos: quem aponta não precisa
do formulário do protesto, e quem protesta não precisa do cadastro do apresentante.

AS FASES SÃO O RITO DA LEI 9.492/1997: apontar, intimar e o desfecho. O projeto previa uma quarta,
«Retorno», e ela não entrou: o retorno à CRA é por arquivo e tem tela própria, e aqui seria uma aba
em branco. A vida do título, os emolumentos, a imagem e a averbação correm fora do rito, como apoio.

A TRAVA NÃO INVENTA REGRA. A única é a intimação de título ainda não apontado, que a rota também
recusa. O desfecho nunca trava: desistência, pagamento e ordem judicial cabem antes de apontar, e
quem diz o que cabe em cada situação continua sendo `cabem`, da rota.

O QUE ESTÁ ERRADO NO TÍTULO NÃO FICA NUMA ABA: os avisos do alto (situação sem ato, selo que falta,
pedido da CRA, credor a averbar) saem em todas, porque cada um é uma obrigação de quem abriu a ficha.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

APONTAMENTO = "apontamento"
INTIMACAO = "intimacao"
DESFECHO = "desfecho"
EMOLUMENTOS = "emolumentos"
VIDA = "vida"
IMAGEM = "imagem"
AVERBACAO = "averbacao"

FEITA = "feita"
LIBERADA = "liberada"
TRAVADA = "travada"

SITUACOES_FINAIS = ("DESISTIDO", "PAGO", "CANCELADO", "DEVOLVIDO")
SITUACOES_DO_RITO_EM_CURSO = ("RECEBIDO", "APONTADO", "INTIMADO")
ATOS_DA_FASE = {"APONTAMENTO": APONTAMENTO, "INTIMACAO": INTIMACAO}
ROTULOS = {
    "INTIMACAO": "Intimação", "DESISTENCIA": "Desistência", "SUSTACAO": "Sustação",
    "REVOGACAO_SUSTACAO": "Revogação da sustação", "EFEITO_SUSPENSIVO": "Efeito suspensivo",
    "REVOGACAO_EFEITO_SUSPENSIVO": "Revogação do efeito suspensivo",
}

_TRAVA_DA_INTIMACAO = {
    "titulo": "Antes, o apontamento",
    "texto": "A intimação só se lança depois de apontar o título: é o apontamento que abre o prazo.",
    "ir": APONTAMENTO, "ir_rotulo": "Apontamento"}


def fase_do_ato(ato: Any) -> str:
    """A aba do formulário de cada ato. O que não é apontar nem intimar é desfecho."""
    return ATOS_DA_FASE.get(str(ato), DESFECHO)


def rotulo_do_ato(ato: Any) -> str:
    """O nome do ato na tela do layout novo, com acento. A chave continua a do banco."""
    return ROTULOS.get(str(ato)) or str(ato).replace("_", " ").capitalize()


def atos_em_vista(cabem: Sequence[str]) -> list[str]:
    """Os formulários que abrem sem clique: o único da fase e o protesto, que é o passo seguinte."""
    no_desfecho = [a for a in cabem if fase_do_ato(a) == DESFECHO]
    abertos = [a for a in cabem if fase_do_ato(a) != DESFECHO]
    if len(no_desfecho) == 1:
        abertos += no_desfecho
    elif "PROTESTO" in no_desfecho:
        abertos.append("PROTESTO")
    return abertos


def _fase(chave: str, rotulo: str, numero: int, estado: str, pendencias: int = 0, aviso: str = "",
          trava: dict | None = None) -> dict:
    return {"chave": chave, "rotulo": rotulo, "numero": numero, "estado": estado, "pendencias": pendencias,
            "aviso": aviso, "trava": trava}


def _lancados(atos: Sequence[Mapping[str, Any]], tipo: str) -> bool:
    return any(a.get("tipo") == tipo and not a.get("cancelado") for a in atos)


def _fase_inicial(situacao: str, triduo: str) -> str:
    """Abre no que espera ação. Título encerrado abre na vida dele, que é o que se vem ler."""
    if situacao == "RECEBIDO":
        return APONTAMENTO
    if situacao == "APONTADO":
        return INTIMACAO
    if situacao == "INTIMADO":
        return INTIMACAO if triduo == "ANTES" else DESFECHO
    if situacao == "PROTESTADO":
        return DESFECHO
    return VIDA


# OS CANAIS DE CADA FASE — pedido do oficial em 15/11/2026: «o curso manual do protesto seja de fácil
# acesso, mas privilegiando a didática do fluxo automatizado por meio das APIs e o cumprimento do rito».
#
# A FICHA SÓ TINHA O CAMINHO PELA MÃO: os formulários dos atos. Quem abria um título apontado não via
# que a intimação pode ir pela Intimação Digital ou pelo AR, nem que o pagamento pode entrar pelo
# boleto — essas telas só estavam no menu. Aqui a fase que espera ação diz primeiro o que a integração
# faz, com o link, e depois o que se faz pela mão, que é o que a ficha tem logo abaixo.
#
# `telas` SÃO ENDPOINTS DE VERDADE, sem argumento. O texto não promete o que a integração não faz: a
# Intimação Digital dá a ciência, e quem lavra a intimação continua sendo a casa.
CANAIS_DA_FASE: dict[str, dict] = {
    APONTAMENTO: {
        "rito": "Protocolize e aponte o título; confira a intimação e o prazo na ficha (Lei 9.492/1997, arts. 5º, 12 e 14).",
        "integracao": ("O recebimento da remessa da CRA cadastra, protocola e aponta. O pedido da CENPROT "
                       "entra por «Dar entrada no título» como RECEBIDO: depois, lance o apontamento na ficha."),
        "telas": (("Remessa da CRA", "protesto_remessas"), ("Pendências da CENPROT", "protesto_pendencias")),
        "manual": ("Este título está RECEBIDO e ainda não foi apontado, como o que chega ao balcão: "
                   "lance o apontamento no formulário abaixo."),
        "telas_da_mao": ()},
    INTIMACAO: {
        "rito": ("O devedor é intimado para pagar ou responder (Lei 9.492/1997, art. 14); não encontrado, "
                 "por edital (art. 15). A intimação só se lavra com a prova da entrega."),
        "integracao": ("Emitido o aviso, ele pode ir pelos Correios com AR digital — o canhoto que volta lavra a "
                       "intimação — e o que não foi entregue vai à Intimação Digital, que dá a ciência do "
                       "devedor por e-mail e WhatsApp, antes do edital."),
        "telas": (("Intimação Digital", "protesto_resolve"), ("AR digital", "protesto_ar")),
        "manual": ("Emita o aviso abaixo. A entrega pela mão da casa, com o canhoto, e o edital se registram em "
                   "Avisos e editais; a intimação já feita por outro meio se lança no formulário desta fase."),
        "telas_da_mao": (("Avisos e editais", "protesto_avisos"),)},
    DESFECHO: {
        "rito": ("Até a lavratura cabem o pagamento (Lei 9.492/1997, art. 19), a desistência (art. 16) e a "
                 "sustação (art. 17); esgotado o prazo, lavra-se o protesto (arts. 12 e 20)."),
        "integracao": ("O boleto do devedor dá baixa sozinho quando tudo bate, e o PIX vira pagamento com o "
                       "crédito conferido no banco. A desistência da CRA chega com o clique da remessa, e os "
                       "protestos do dia se lavram juntos em «A protestar»."),
        "telas": (("Boleto do devedor", "protesto_boletos"), ("Pedidos da CRA", "protesto_cra_pedidos"),
                  ("A protestar", "protesto_a_protestar")),
        "manual": ("O pagamento no balcão, a desistência pedida aqui, a ordem judicial e o protesto deste "
                   "título só se lançam nos formulários abaixo. Só aparecem os atos que cabem."),
        "telas_da_mao": ()},
}


def canais_do_titulo(situacao: Any, triduo: Any = "") -> dict | None:
    """Os dois caminhos da fase que espera ação. `None` fora do rito em curso.

    O protestado não tem: o que cabe depois da lavratura (cancelamento, ordem judicial) não tem dois
    caminhos, e o texto do desfecho falaria de pagamento que a serventia já não recebe.
    """
    if str(situacao or "") not in SITUACOES_DO_RITO_EM_CURSO:
        return None
    fase = _fase_inicial(str(situacao or ""), str(triduo or ""))
    canais = CANAIS_DA_FASE.get(fase)
    if not canais:
        return None
    return {"fase": fase, "rito": canais["rito"], "integracao": canais["integracao"], "manual": canais["manual"],
            "telas": [{"rotulo": r, "tela": t} for r, t in canais["telas"]],
            "telas_da_mao": [{"rotulo": r, "tela": t} for r, t in canais["telas_da_mao"]]}


def fases_do_titulo(titulo: Mapping[str, Any], *, cabem: Sequence[str] = (), atos: Sequence = (), avisos: Sequence = (),
                    imagens: Sequence = (), emolumento: Mapping[str, Any] | None = None, triduo: str = "",
                    pode_averbar: bool = False) -> dict:
    """A régua da ficha. A forma é a de `notas_fases`: `_fases.html` desenha as duas."""
    situacao = str(titulo.get("situacao") or "")
    apontar = "APONTAMENTO" in cabem
    intimar = "INTIMACAO" in cabem
    fase_1 = _fase(APONTAMENTO, "Apontamento", 1, LIBERADA if apontar else FEITA, int(apontar),
                   "Aponte o título: é o que abre o prazo." if apontar else "")
    if situacao == "RECEBIDO":
        fase_2 = _fase(INTIMACAO, "Intimação", 2, TRAVADA, trava=_TRAVA_DA_INTIMACAO)
    elif situacao == "APONTADO":
        fase_2 = _fase(INTIMACAO, "Intimação", 2, LIBERADA, 1 if intimar else 0,
                       "Emita o aviso e lance a intimação." if intimar else "")
    elif situacao in ("INTIMADO", "PROTESTADO") or _lancados(atos, "INTIMACAO"):
        fase_2 = _fase(INTIMACAO, "Intimação", 2, FEITA)
    else:
        fase_2 = _fase(INTIMACAO, "Intimação", 2, LIBERADA)

    pronto_para_protestar = "PROTESTO" in cabem and triduo != "ANTES"
    if situacao in SITUACOES_FINAIS:
        fase_3 = _fase(DESFECHO, "Desfecho", 3, FEITA)
    elif pronto_para_protestar:
        fase_3 = _fase(DESFECHO, "Desfecho", 3, LIBERADA, 1,
                       "O tríduo venceu: o protesto se lavra com o motivo do atraso."
                       if triduo == "ATRASADO" else "É dia de protestar.")
    elif "PROTESTO" in cabem:
        fase_3 = _fase(DESFECHO, "Desfecho", 3, LIBERADA, aviso="Ainda não é dia de protestar: o devedor está no prazo.")
    else:
        fase_3 = _fase(DESFECHO, "Desfecho", 3, LIBERADA)

    fases = [fase_1, fase_2, fase_3]
    for i, fase in enumerate(fases):
        fase["voltar"] = {k: fases[i - 1][k] for k in ("chave", "rotulo")} if i else None
        fase["avancar"] = {k: fases[i + 1][k] for k in ("chave", "rotulo")} if i < len(fases) - 1 else None

    apoio = [{"chave": VIDA, "rotulo": "Vida do título", "contagem": len(atos), "alerta": 0}]
    if emolumento:
        devidos = (emolumento.get("pendentes") or {}).get("itens") or ()
        apoio.append({"chave": EMOLUMENTOS, "rotulo": "Emolumentos", "contagem": len(devidos), "alerta": 0})
    apoio.append({"chave": IMAGEM, "rotulo": "Imagem", "contagem": len(imagens), "alerta": 0})
    if pode_averbar:
        apoio.append({"chave": AVERBACAO, "rotulo": "Averbação", "contagem": 0, "alerta": 0})
    return {"fases": fases, "apoio": apoio, "foco": "", "inicial": _fase_inicial(situacao, triduo),
            "atos_em_vista": atos_em_vista(cabem), "avisos": len(avisos)}
