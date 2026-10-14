"""A régua de FILTRAR e ORDENAR tarefas — uma só, para Processos e Tarefas.

Pedido do oficial em 13/10/2026: «preciso ter como ordenar as tarefas, tem
poucas opções de filtros (não tem por prioridade, etc) e não tem nenhuma opção
de ordenar por prioridade, por data, por setor... quero todas opções».

POR QUE UM MÓDULO, E NÃO DUAS LISTAS
    A tela «Tarefas» (`database.list_tasks`) filtrava só por situação e setor,
    e não ordenava; a de Processos (`processos.listar`) tinha mais filtros e
    quatro ordens. Escrever a régua duas vezes faria as duas telas divergirem
    no primeiro conserto — a mesma pergunta («o que vence esta semana, da
    Leidiane?») daria duas respostas. Aqui moram os filtros que as duas têm em
    comum e TODAS as ordens; cada tela só diz como se chamam, na consulta
    dela, o nome do responsável e o último andamento.

O QUE NÃO ESTÁ AQUI: a vista (abertas, comigo, vencidas…), que é de
`tarefa_processo`, e a busca por texto, que em Processos olha também o
expediente — cada tela junta tabelas diferentes.

Data calculada no SQL custa acoplamento ao SQLite (`test_portabilidade`): os
limites de data são feitos em Python e chegam como texto ISO.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

#: Quem não tem responsável — o valor do filtro.
SEM_RESPONSAVEL = "NINGUEM"

PRAZOS = {"VENCIDO": "vencido", "HOJE": "vence hoje", "SEMANA": "vence em 7 dias",
          "MES": "vence em 30 dias", "SEM_PRAZO": "sem prazo"}
PARADOS = {"7": "sem andamento há 7 dias ou mais", "15": "há 15 dias ou mais",
           "30": "há 30 dias ou mais"}

#: Os filtros que esta régua sabe aplicar, pelo nome que vai no endereço.
FILTROS = ("responsavel", "substituto", "prazo", "prazo_de", "prazo_ate",
           "abertura_de", "abertura_ate", "prioridade", "situacao", "parado",
           "ordem", "inverter")

#: TODAS AS ORDENS. O rótulo diz o sentido normal; «inverter» vira ao contrário.
ORDENS = {
    "PRAZO": "pelo prazo (o que vence antes primeiro)",
    "PRIORIDADE": "pela prioridade (crítica primeiro)",
    "ABERTURA": "pela data de abertura (a mais nova primeiro)",
    "ANDAMENTO": "pelo último andamento (o mais parado primeiro)",
    "SETOR": "pelo setor (A→Z)",
    "RESPONSAVEL": "pelo responsável (A→Z)",
    "SITUACAO": "pela situação (A→Z)",
    "ASSUNTO": "pelo assunto (A→Z)",
    "ORIGEM": "pela origem (A→Z)",
    "TIPO": "pelo tipo de processo (A→Z)",
    "NUMERO": "pelo número (o maior primeiro)",
}
#: As duas ordens que existiam antes de 13/10 continuam valendo no endereço —
#: um favorito antigo não pode cair na ordem errada sem avisar.
APELIDOS = {"PARADO": "ANDAMENTO", "RECENTE": "ABERTURA"}
#: A ordem que a tela usa quando ninguém escolheu.
PADRAO = "PRAZO"

_RANK_DA_PRIORIDADE = ("CASE t.priority WHEN 'CRITICA' THEN 0 WHEN 'ALTA' THEN 1 "
                       "WHEN 'MEDIA' THEN 2 WHEN 'BAIXA' THEN 3 ELSE 4 END")


def _vazio_por_ultimo(expr: str) -> str:
    """Vazio vai para o fim nos dois sentidos — lista que começa por linhas sem
    setor ou sem responsável esconde o que se queria ver."""
    return f"CASE WHEN {expr} IS NULL OR {expr} = '' THEN 1 ELSE 0 END"


def ordens_da_tela(*, tem_tipo: bool) -> dict[str, str]:
    """As ordens que aquela tela oferece — a de Tarefas não junta o tipo."""
    return {k: v for k, v in ORDENS.items() if tem_tipo or k != "TIPO"}


def ordem_sql(ordem: str | None, inverter: Any = False, *,
              responsavel: str = "ua.full_name",
              andamento: str = "ultimo_andamento",
              tipo: str | None = "pe.especie") -> str:
    """O `ORDER BY` da ordem pedida. Só a chave principal se inverte; o
    desempate (prazo e número) fica sempre igual, para a lista não pular."""
    chave = APELIDOS.get((ordem or "").upper(), (ordem or "").upper())
    if chave not in ORDENS or (chave == "TIPO" and not tipo):
        chave = PADRAO
    # (expressão, sentido normal) — o «vazio por último» nunca se inverte.
    principal: dict[str, tuple[list[str], str, str]] = {
        "PRAZO": ([_vazio_por_ultimo("t.due_date")], "t.due_date", "ASC"),
        "PRIORIDADE": ([], _RANK_DA_PRIORIDADE, "ASC"),
        "ABERTURA": ([], "t.created_at", "DESC"),
        "ANDAMENTO": ([], andamento, "ASC"),
        "SETOR": ([_vazio_por_ultimo("t.sector")], "t.sector", "ASC"),
        "RESPONSAVEL": ([_vazio_por_ultimo(responsavel)], responsavel, "ASC"),
        "SITUACAO": ([], "t.status", "ASC"),
        "ASSUNTO": ([], "t.title", "ASC"),
        "ORIGEM": ([], "t.source_type", "ASC"),
        "TIPO": ([_vazio_por_ultimo(tipo or "''")], tipo or "''", "ASC"),
        "NUMERO": ([], "t.id", "DESC"),
    }
    fixos, expr, sentido = principal[chave]
    if _verdade(inverter):
        sentido = "DESC" if sentido == "ASC" else "ASC"
    partes = [*fixos, f"{expr} {sentido}"]
    if chave != "PRAZO":
        partes += [_vazio_por_ultimo("t.due_date"), "t.due_date ASC"]
    if chave != "NUMERO":
        partes.append("t.id DESC")
    return ", ".join(partes)


def _verdade(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "sim", "on")


def filtros_sql(filtros: dict[str, Any], *, hoje: date, cond_aberta: str,
                args_aberta: list[Any], andamento: str) -> tuple[list[str], list[Any]]:
    """As condições dos filtros pedidos. Vazio = não filtra. Só calcula.

    `andamento` é a expressão do último andamento NA CONSULTA de quem chama —
    a de Processos já a seleciona; a de Tarefas a escreve por inteiro."""
    f = {k: str(v).strip() for k, v in filtros.items() if v not in (None, "")}
    hoje_iso = hoje.isoformat()
    where: list[str] = []
    args: list[Any] = []
    resp = f.get("responsavel")
    if resp == SEM_RESPONSAVEL:
        where.append("t.assigned_user_id IS NULL")
    elif resp and resp.isdigit():
        where.append("t.assigned_user_id = ?")
        args.append(int(resp))
    if (f.get("substituto") or "").isdigit():
        where.append("t.backup_user_id = ?")
        args.append(int(f["substituto"]))
    prazo = f.get("prazo")
    if prazo == "VENCIDO":
        where += ["t.due_date IS NOT NULL AND t.due_date < ?", cond_aberta]
        args += [hoje_iso, *args_aberta]
    elif prazo == "HOJE":
        where.append("t.due_date = ?")
        args.append(hoje_iso)
    elif prazo in ("SEMANA", "MES"):
        ate = (hoje + timedelta(days=7 if prazo == "SEMANA" else 30)).isoformat()
        where.append("t.due_date >= ? AND t.due_date <= ?")
        args += [hoje_iso, ate]
    elif prazo == "SEM_PRAZO":
        where.append("t.due_date IS NULL")
    if f.get("prazo_de"):
        where.append("t.due_date >= ?")
        args.append(f["prazo_de"][:10])
    if f.get("prazo_ate"):
        where.append("t.due_date <= ?")
        args.append(f["prazo_ate"][:10])
    # A ABERTURA guarda data E hora; «até 13/10» inclui o dia 13 inteiro, e o
    # `z` passa de qualquer hora na comparação de texto (a régua do razão dos
    # selos, relato #33).
    if f.get("abertura_de"):
        where.append("t.created_at >= ?")
        args.append(f["abertura_de"][:10])
    if f.get("abertura_ate"):
        where.append("t.created_at <= ?")
        args.append(f["abertura_ate"][:10] + "z")
    if f.get("prioridade"):
        where.append("t.priority = ?")
        args.append(f["prioridade"])
    if f.get("situacao"):
        where.append("t.status = ?")
        args.append(f["situacao"])
    if (f.get("parado") or "").isdigit():
        limite_ts = (hoje - timedelta(days=int(f["parado"]))).isoformat()
        where.append(f"{andamento} < ?")
        args.append(limite_ts)
    return where, args
