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
