"""O TIPO DO PROCESSO — quatro, para classificar e filtrar (12/10/2026).

    «simplifique a parte do roteiro, deixe apenas tarefa administrativa, ordem
     judicial, processos da corregedoria e ato do cartório pendente» e, no mesmo
     dia, «não precisa de roteiro»                    — o oficial

O TIPO NÃO É ROTEIRO. Houve, por algumas horas de 12/10/2026, um roteiro por
espécie (lista de documentos com o artigo do Código de Normas, passos, marcação
«recebido / pedido / não se aplica» e aprovação do oficial). O oficial decidiu
que não precisa: o que falta num processo se diz no andamento, como sempre se
disse. Ficou o tipo, que serve para a lista e para o controle do administrador
filtrarem — e nada aqui trava coisa nenhuma.

O TIPO SE SUGERE E SE ESCOLHE. `sugerir` olha a origem e o texto e propõe; quem
grava é a pessoa, na ficha do processo ou ao abri-lo.
"""
from __future__ import annotations

from typing import Any

from bd_nativo import banco

CATALOGO: dict[str, dict[str, str]] = {
    "TAREFA_ADMINISTRATIVA": {"nome": "Tarefa administrativa",
                              "exemplos": "obrigação com órgão público, LGPD, PLD/FT, rotina interna"},
    "ORDEM_JUDICIAL": {"nome": "Ordem judicial",
                       "exemplos": "mandado de averbação ou de registro, ofício de juízo, penhora, indisponibilidade"},
    "CORREGEDORIA": {"nome": "Processo da Corregedoria",
                     "exemplos": "inspeção, correição, PJeCor, ofício ou circular da COGEX que pede providência"},
    "ATO_PENDENTE": {"nome": "Ato do cartório pendente",
                     "exemplos": "ato que ficou para outro dia, rascunho, ato com erro a corrigir, minuta a lavrar"},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS pr_especie_do_processo (
    task_id bigint PRIMARY KEY,
    especie text NOT NULL,
    definida_em text NOT NULL,
    definida_por bigint
);
"""

_CORREGEDORIA = ("corregedoria", "cogex", "cgj", "pjecor", "inspeção", "inspecao", "correição", "correicao",
                 "provimento", "auditus")
_JUDICIAL = ("mandado", "sentença", "sentenca", "juízo", "juizo", "vara ", "averba", "penhora",
             "indisponibilidade", "processo nº", "processo n.", "autos")


class EspecieError(ValueError):
    """Recusa com mensagem pronta para o balcão."""


def init_schema(con: Any) -> None:
    banco(con).escrever(SCHEMA)


def sugerir(task: dict) -> str | None:
    """O tipo mais provável pela origem e pelo texto. SÓ SUGERE."""
    origem = (task.get("source_type") or "").upper()
    texto = f"{task.get('title') or ''} {task.get('description') or ''}".lower()
    if origem == "RASCUNHO":
        return "ATO_PENDENTE"
    if origem == "INSPECAO":
        return "CORREGEDORIA"
    if origem == "MANUAL":
        return "TAREFA_ADMINISTRATIVA"
    if origem == "EXPEDIENTE":
        if any(p in texto for p in _CORREGEDORIA):
            return "CORREGEDORIA"
        if any(p in texto for p in _JUDICIAL):
            return "ORDEM_JUDICIAL"
    return None


def definir(con: Any, task_id: int, especie: str, *, agora: str, por: int | None) -> None:
    """Grava o tipo escolhido. ESCREVE."""
    init_schema(con)
    if especie not in CATALOGO:
        raise EspecieError("Esse tipo de processo não existe.")
    bd = banco(con)
    antes = bd.um("SELECT especie FROM pr_especie_do_processo WHERE task_id = %s", (int(task_id),))
    bd.escrever("INSERT INTO pr_especie_do_processo(task_id, especie, definida_em, definida_por) VALUES (%s,%s,%s,%s) "
                "ON CONFLICT(task_id) DO UPDATE SET especie=excluded.especie, definida_em=excluded.definida_em, "
                "definida_por=excluded.definida_por", (int(task_id), especie, agora, por))
    bd.escrever("INSERT INTO task_history(task_id, ts, user_id, action, old_value, new_value, note) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (int(task_id), agora, por, "NOTA", antes["especie"] if antes else None, especie,
                 f"Tipo do processo: {CATALOGO[especie]['nome']}."))


def tipo_do_processo(con: Any, task: dict) -> dict[str, Any]:
    """O que a ficha mostra: o tipo gravado (ou o sugerido) e o catálogo. Só lê.

    Tipo gravado que não está mais no catálogo (o das horas do roteiro, em
    12/10/2026) aparece como «sem tipo», com o sugerido, em vez de sumir calado."""
    init_schema(con)
    linha = banco(con).um("SELECT especie FROM pr_especie_do_processo WHERE task_id = %s", (int(task["id"]),))
    especie = linha["especie"] if linha and linha["especie"] in CATALOGO else None
    return {"especie": especie, "nome": CATALOGO[especie]["nome"] if especie else None,
            "sugerida": None if especie else sugerir(task), "catalogo": CATALOGO}
