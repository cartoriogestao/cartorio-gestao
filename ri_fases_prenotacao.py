"""As fases da prenotação: o que a régua mostra e onde a ficha abre. SÓ LÊ.

OITO QUADROS SEGUIDOS, E O PRAZO NO MEIO DA PÁGINA — projeto do novo layout, 30/10/2026. Os
quadros continuam os mesmos, nas mesmas rotas. O que muda é quais aparecem juntos, e o prazo
vai para o título, de onde não some ao rolar.

SÓ TRÊS FASES, E NÃO AS CINCO DO DESENHO. O desenho punha Registro e Entrega depois da
Qualificação, mas esta tela não tem esses quadros: o registro é lavrado na matrícula, e a
tela leva até lá. Fase vazia seria uma aba que não responde nada.

A NOTA DEVOLUTIVA FICA NA QUALIFICAÇÃO. O oficial a pôs no alto em 25/10/2026, porque ninguém
a cadastrava pela tela; ela sai da qualificação, e é lá que quem qualifica está.

A TRAVA NÃO EXISTE AQUI. O título pode ser conferido em qualquer ordem, e o servidor continua
recusando o que recusava.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

TITULO = "titulo"
EMOLUMENTOS = "emolumentos"
QUALIFICACAO = "qualificacao"
DOCUMENTOS = "documentos"
NOTAS = "notas"
ONR = "onr"
HISTORICO = "historico"

FEITA = "feita"
LIBERADA = "liberada"


def fases_da_prenotacao(p: Mapping[str, Any], *, documentos: Sequence = (), notas: Sequence = (),
                        qualificacoes: Sequence = (), historico: Sequence = (),
                        depositos: Sequence = (), tem_onr: bool = False) -> dict:
    """A régua da prenotação. A forma é a de `notas_fases`: `_fases.html` desenha as duas."""
    aberta = (p.get("situacao") or "") == "ABERTO"
    nota_aberta = any(n.get("situacao") == "ABERTA" for n in notas)
    qualificada = bool(qualificacoes)
    com_selo = bool((p.get("selo_prenotacao") or "").strip())
    fases = [
        {"chave": TITULO, "rotulo": "Título", "numero": 1, "pendencias": 0 if com_selo else 1,
         "estado": FEITA if com_selo else LIBERADA, "aviso": "", "trava": None},
        {"chave": EMOLUMENTOS, "rotulo": "Emolumentos", "numero": 2, "pendencias": 0,
         "estado": FEITA if depositos else LIBERADA, "aviso": "", "trava": None},
        {"chave": QUALIFICACAO, "rotulo": "Qualificação", "numero": 3,
         "pendencias": 1 if nota_aberta else 0,
         "estado": FEITA if qualificada and not nota_aberta else LIBERADA,
         "aviso": "Há nota devolutiva em aberto: o prazo depende dela." if nota_aberta else "",
         "trava": None},
    ]
    for i, fase in enumerate(fases):
        fase["voltar"] = {k: fases[i - 1][k] for k in ("chave", "rotulo")} if i else None
        fase["avancar"] = {k: fases[i + 1][k] for k in ("chave", "rotulo")} if i < len(fases) - 1 else None
    apoio = [{"chave": DOCUMENTOS, "rotulo": "Documentos", "contagem": len(documentos), "alerta": 0}]
    if notas:
        apoio.append({"chave": NOTAS, "rotulo": "Notas", "contagem": len(notas), "alerta": 0})
    if tem_onr:
        apoio.append({"chave": ONR, "rotulo": "ONR", "contagem": 0, "alerta": 0})
    if historico:
        apoio.append({"chave": HISTORICO, "rotulo": "Histórico", "contagem": len(historico), "alerta": 0})
    if not aberta:
        inicial = TITULO
    elif nota_aberta or (documentos and not qualificada):
        inicial = QUALIFICACAO
    else:
        inicial = TITULO
    return {"fases": fases, "apoio": apoio, "foco": "", "inicial": inicial}
