"""As abas da ficha do protocolo geral: o que a régua mostra e o que espera ação. SÓ LÊ.

ONZE QUADROS SEGUIDOS, E OS ITENS NO MEIO DA PÁGINA — projeto do novo layout, 30/10/2026. Quem
vinha quitar rolava por exigências, tarefas e documentos antes de achar o botão. Os quadros
continuam os mesmos, nas mesmas rotas e com os mesmos formulários. O que muda é quais aparecem
juntos, e a ficha abre em Itens e quitação, que é o que o balcão faz o dia inteiro.

ABAS, E NÃO FASES. Documentos, tarefas e exigências não têm ordem entre si, e o que o servidor
recusa continua sendo recusado por ele.

AS ABAS DE LISTA VAZIA FICAM QUANDO O FORMULÁRIO MORA NELA. Documentos, Exigências e Tarefas é
onde se cria o primeiro. Vínculos, Acompanhamento e Movimento só existem quando se aplicam.

O QUE ESPERA AÇÃO SÓ FALA DO QUE ESTÁ FORA DE VISTA. Os itens a quitar já estão na aba que abre,
com o botão, e repeti-los seria ruído. «Sem vínculo com a prenotação» também não entra: pedido de
certidão do RI nunca terá vínculo, e alarme que soa sempre é alarme que ninguém ouve. A exigência
entra porque muda o que se diz ao cliente que chega ao balcão, embora dependa dele.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

ITENS = "itens"
DADOS = "dados"
DOCUMENTOS = "documentos"
EXIGENCIAS = "exigencias"
TAREFAS = "tarefas"
VINCULOS = "vinculos"
ACOMPANHAMENTO = "acompanhamento"
MOVIMENTO = "movimento"


def e_do_ri(p: Mapping[str, Any]) -> bool:
    """A mesma condição do quadro de vínculo da ficha."""
    return bool(p.get("ri_protocolo_id")) or str(p.get("atribuicao") or "").upper() == "RI"


def o_que_espera(*, encerrado: bool = False, exigencias: Sequence = ()) -> list[dict]:
    """O que a ficha pede e não está à vista. Vazia, o quadro não sai."""
    if encerrado or not exigencias:
        return []
    return [{"texto": f"{len(exigencias)} nota(s) de exigência aguardando o interessado",
             "ir": EXIGENCIAS, "botao": "Ver"}]


def abas_do_protocolo(p: Mapping[str, Any], *, atos: Sequence = (), faltam: int = 0,
                      encerrado: bool = False, documentos: Sequence = (), exigencias: Sequence = (),
                      tarefas: Sequence = (), lancamentos: Sequence = (),
                      acompanhamento: Mapping[str, Any] | None = None) -> dict:
    """A régua da ficha. Só calcula. A forma é a de `notas_fases`: `_fases.html` desenha as duas."""
    a_quitar = 0 if encerrado or p.get("tipo") == "ORCAMENTO" else int(faltam or 0)
    apoio = [{"chave": ITENS, "rotulo": "Itens e quitação", "contagem": len(atos), "alerta": a_quitar},
             {"chave": DADOS, "rotulo": "Dados e encerramento", "contagem": 0, "alerta": 0},
             {"chave": DOCUMENTOS, "rotulo": "Documentos", "contagem": len(documentos), "alerta": 0},
             {"chave": EXIGENCIAS, "rotulo": "Exigências", "contagem": 0,
              "alerta": 0 if encerrado else len(exigencias)},
             {"chave": TAREFAS, "rotulo": "Tarefas", "contagem": len(tarefas), "alerta": 0}]
    if e_do_ri(p):
        apoio.append({"chave": VINCULOS, "rotulo": "Vínculos", "contagem": 0, "alerta": 0})
    if acompanhamento and acompanhamento.get("elegivel"):
        apoio.append({"chave": ACOMPANHAMENTO, "rotulo": "Acompanhamento", "contagem": 0, "alerta": 0})
    if lancamentos:
        apoio.append({"chave": MOVIMENTO, "rotulo": "Movimento", "contagem": len(lancamentos), "alerta": 0})
    return {"fases": [], "apoio": apoio, "foco": "", "inicial": ITENS,
            "espera": o_que_espera(encerrado=encerrado, exigencias=exigencias)}
