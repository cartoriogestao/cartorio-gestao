"""As abas da ficha da matrícula: o que a régua mostra e o que espera ação. SÓ LÊ.

A FICHA CHEGAVA A 6.892 PX — pedido do oficial, 30/10/2026: «matriculas e escrituras que sao
excessivamente grandes em rolagem». Os quadros continuam os mesmos, nas mesmas rotas e com os
mesmos formulários. O que muda é quais aparecem juntos.

ABAS, E NÃO FASES. A matrícula é um registro vivo, sem ordem própria: ninguém «termina» a
aba Partes. Quem tem fases é o ato (`notas_fases`). Por isso aqui a régua não numera nem trava.

ELA ABRE NO RESUMO, E O RESUMO COMEÇA PELO QUE ESPERA AÇÃO. Selo que faltou, revisão, minuta:
o que estava espalhado pela página vem primeiro. Só aparece o que falta: alarme que soa
sempre é alarme que ninguém ouve, e por isso o ato do acervo não entra. A mesma conta do
«Ato(s) desta ficha sem selo» de `ri_ficha.html`: lavrado aqui, sem selo e sem cancelamento.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

RESUMO = "resumo"
ATOS = "atos"
TEOR = "teor"
PARTES = "partes"
PROTOCOLOS = "protocolos"
CERTIDOES = "certidoes"
REVISAR = "revisar"
NOVO_ATO = "novo-ato"


def _rotulo(ato: Mapping[str, Any]) -> str:
    return f'{ato["tipo"]}-{int(ato["numero"]):02d}'


def sem_selo(atos: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Os atos lavrados por este sistema que ficaram sem selo. O acervo não entra."""
    return [a for a in atos
            if a.get("origem") == "MANUAL" and not a.get("selo_texto") and not a.get("cancelado")]


def o_que_espera(atos: Sequence[Mapping[str, Any]], *, revisoes_abertas: Sequence = (),
                 minutas: Sequence = (), rascunho: Any = None,
                 certidoes_aguardando_selo: Sequence = ()) -> list[dict]:
    """O que a ficha pede agora, na ordem em que custa mais. Vazia, o quadro não sai."""
    itens = [{"texto": f"{_rotulo(a)} lavrado e sem selo", "ir": f'selar-ato-{a["id"]}', "botao": "Selar"}
             for a in sem_selo(atos)]
    if certidoes_aguardando_selo:
        itens.append({"texto": f"{len(certidoes_aguardando_selo)} certidão(ões) aguardando selo",
                      "ir": CERTIDOES, "botao": "Ver"})
    if revisoes_abertas:
        itens.append({"texto": f"{len(revisoes_abertas)} ponto(s) a revisar antes de selar",
                      "ir": REVISAR, "botao": "Ver"})
    if minutas:
        itens.append({"texto": f"{len(minutas)} minuta(s) na fila de revisão",
                      "ir": "minutas-para-lavrar", "botao": "Abrir"})
    if rascunho:
        itens.append({"texto": f'Rascunho de {rascunho["tipo"]} guardado', "ir": NOVO_ATO, "botao": "Abrir"})
    return itens


def proprietarios(partes: Sequence[Mapping[str, Any]]) -> list[str]:
    """Quem é dono hoje: `proprietario_ativo`, e nunca quem já vendeu."""
    return [str(p.get("nome") or "") for p in partes if p.get("proprietario_ativo")]


def abas_da_matricula(m: Mapping[str, Any], *, atos: Sequence = (), partes: Sequence = (),
                      protocolos: Sequence = (), certidoes_emitidas: int = 0,
                      revisoes_abertas: Sequence = (), minutas: Sequence = (), rascunho: Any = None,
                      certidoes_aguardando_selo: Sequence = (), onus: Sequence[str] = (),
                      foco: str = "") -> dict:
    """A régua da ficha. Só calcula. A forma é a de `notas_fases`: `_fases.html` desenha as duas.

    Aba de lista vazia não aparece. Revisar fica: «nada a revisar» é uma resposta, e o
    formulário de abrir uma nota mora lá. Novo ato também, mesmo em ficha encerrada: é lá
    que moram o rascunho e as minutas, e a ficha diz por que não aceita ato novo.
    """
    apoio = [{"chave": RESUMO, "rotulo": "Resumo", "contagem": 0, "alerta": 0}]
    if atos:
        apoio.append({"chave": ATOS, "rotulo": "Atos", "contagem": len(atos), "alerta": len(sem_selo(atos))})
    apoio.append({"chave": TEOR, "rotulo": "Teor e imagem", "contagem": 0, "alerta": 0})
    apoio.append({"chave": PARTES, "rotulo": "Partes", "contagem": len(partes), "alerta": 0})
    if protocolos:
        apoio.append({"chave": PROTOCOLOS, "rotulo": "Protocolos", "contagem": len(protocolos), "alerta": 0})
    apoio.append({"chave": CERTIDOES, "rotulo": "Certidões", "contagem": int(certidoes_emitidas or 0),
                  "alerta": len(certidoes_aguardando_selo)})
    apoio.append({"chave": REVISAR, "rotulo": "Revisar", "contagem": 0, "alerta": len(revisoes_abertas)})
    apoio.append({"chave": NOVO_ATO, "rotulo": "Novo ato", "contagem": 0, "alerta": 0, "principal": True})
    chaves = {x["chave"] for x in apoio}
    espera = o_que_espera(atos, revisoes_abertas=revisoes_abertas, minutas=minutas, rascunho=rascunho,
                          certidoes_aguardando_selo=certidoes_aguardando_selo)
    return {"fases": [], "apoio": apoio, "foco": TEOR, "inicial": foco if foco in chaves else RESUMO,
            "espera": espera, "proprietarios": proprietarios(partes), "onus": list(onus),
            "ultimos": [{"rotulo": _rotulo(a), "natureza": a.get("natureza_titulo") or "",
                         "data": a.get("data_ato") or ""}
                        for a in list(atos)[-3:][::-1]]}
