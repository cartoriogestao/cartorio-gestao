"""As abas dos autos de usucapião: o que a régua mostra. SÓ LÊ.

SEIS QUADROS, E O FORMULÁRIO DA DECISÃO A SEIS MIL PIXELS DO ALTO — projeto do novo layout,
30/10/2026. Os quadros continuam os mesmos, nas mesmas rotas e com os mesmos formulários. O que
muda é quais aparecem juntos.

ABAS, E NÃO FASES. O rito tem etapas, e elas já têm o seu quadro: é ele que recusa pular e aceita
voltar. Peças, andamento e conferência correm ao mesmo tempo em qualquer etapa, e por isso uma
régua com fases diria uma ordem que os autos não têm.

A FICHA ABRE EM PROCESSO, e ele já começa pelo «O que fazer agora». Por isso esta ficha não tem o
quadro «O que espera ação»: ele existe desde agosto, e a régua só aponta onde está o que falta.

PROCESSO QUE TERMINOU NÃO COBRA NADA. Prazo vencido e item pendente continuam escritos nos seus
quadros, mas a aba não marca: registrado, rejeitado ou remetido ao juízo, ninguém vai agir.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

PROCESSO = "processo"
CONFERENCIA = "conferencia"
PECAS = "pecas"
ANDAMENTO = "andamento"
QUALIFICACAO = "qualificacao"
DECISAO = "decisao"

SITUACOES_FINAIS = ("REGISTRADO", "REJEITADO", "REMETIDO_AO_JUIZO")


def prazos_vencidos(movimentos: Sequence[Mapping[str, Any]], hoje: str) -> list:
    """A mesma conta do «vencido» do quadro de andamento."""
    return [m for m in movimentos
            if m.get("prazo_fim") and not m.get("respondido_em") and str(m["prazo_fim"]) < str(hoje)]


def abas_do_processo(p: Mapping[str, Any], *, conferencia: Mapping[str, Any] | None = None,
                     pecas: Sequence = (), movimentos: Sequence = (), analises: Sequence = (),
                     decisoes: Sequence = (), hoje: str = "") -> dict:
    """A régua da ficha. Só calcula. A forma é a de `notas_fases`: `_fases.html` desenha as duas."""
    em_curso = str(p.get("situacao") or "") not in SITUACOES_FINAIS
    pendentes = (conferencia or {}).get("pendentes") or ()
    por_conferir = [a for a in analises if not a.get("conferida_por_humano")]
    apoio = [{"chave": PROCESSO, "rotulo": "Processo", "contagem": 0, "alerta": 0},
             {"chave": CONFERENCIA, "rotulo": "Conferência", "contagem": 0,
              "alerta": len(pendentes) if em_curso else 0},
             {"chave": PECAS, "rotulo": "Peças", "contagem": len(pecas), "alerta": 0},
             {"chave": ANDAMENTO, "rotulo": "Andamento", "contagem": len(movimentos),
              "alerta": len(prazos_vencidos(movimentos, hoje)) if em_curso else 0},
             {"chave": QUALIFICACAO, "rotulo": "Relatório", "contagem": len(analises),
              "alerta": len(por_conferir) if em_curso else 0},
             {"chave": DECISAO, "rotulo": "Decisão", "contagem": len(decisoes), "alerta": 0}]
    return {"fases": [], "apoio": apoio, "foco": "", "inicial": PROCESSO}
