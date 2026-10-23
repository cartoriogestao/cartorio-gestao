"""PROCESSOS — a lista única da casa (fase 3, 12/10/2026).

    «precisamos unir o modulo de tarefas e de expedientes para ser um unico
     modulo de Processos, em que reuniremos todos processos, protocolos e
     pedidos da serventia»                           — o oficial, 12/10/2026
    «apenas atendimentos que nao sao resolvidos na hora»   — no mesmo dia

O PROCESSO É A TAREFA CRESCIDA. A tabela `tasks` já tinha o que um processo
precisa — responsável, substituto, prazo, andamento, passagem, evidência — e é
nela que o gestor, a inspeção, o malote e a cobrança já escrevem. Trocar de
tabela obrigaria a reescrever todos eles; o que muda é o NOME e a LISTA.

O EXPEDIENTE É A ENTRADA, e não um segundo tipo de obrigação. O que chega pelo
malote continua registrado em `expedientes` (remetente, nº externo, data de
chegada, documento recebido), e de duas, uma: ou vira processo — com a pasta, o
tipo e o responsável — ou recebe «só ciência» (o que veio «para
conhecimento» e não pede nada). Medido em 12/10/2026: 33 expedientes, 19
tarefas ligadas a eles, 30 parados em RECEBIDO.

O NÚMERO DO PROCESSO não é coluna nova: é o da tarefa, com o ano em que nasceu
— `PROC-2026-000318`. Os endereços antigos (`/tarefas/318`) continuam abrindo.

Ler não grava nada.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from bd_nativo import banco
import processo_especies as ESP
import tarefa_ordem as TO
import tarefa_processo as TP
import tarefa_suspensao as TS

#: O despacho do gestor virou relato em 12/10/2026 e não é processo.
FORA_DOS_PROCESSOS = ("DESPACHO", "RCPN_DIA")

ORIGENS = {
    "EXPEDIENTE": "Malote",
    "INSPECAO": "Inspeção",
    "GESTOR": "Agente gestor",
    "MANUAL": "Interno",
    "RASCUNHO": "Rascunho de ato",
}

VISTAS = {
    "COMIGO": "Comigo",
    "PASSOU_POR_MIM": "Passou por mim",
    "PEDIRAM_RESPOSTA": "Pediram minha resposta",
    "ABERTOS": "Abertos",
    "VENCIDOS": "Vencidos",
    "ENCERRADOS": "Encerrados",
    "TODOS": "Todos",
}
#: As vistas que vêm prontas da lista de tarefas (relatos #59 e #110) — uma
#: régua só para «o que passou por mim» e «o que me pediram».
VISTAS_DA_REGUA = ("PASSOU_POR_MIM", "PEDIRAM_RESPOSTA")

ESTAGIOS_ENCERRADOS = ("RESPONDIDO", "ARQUIVADO")


def numero(created_at: str | None, task_id: int) -> str:
    ano = (created_at or "")[:4] if (created_at or "")[:4].isdigit() else str(date.today().year)
    return f"PROC-{ano}-{int(task_id):06d}"


def nome_da_origem(source_type: str | None) -> str:
    return ORIGENS.get((source_type or "").upper(), (source_type or "outro").capitalize())


#: Os filtros de controle e fiscalização (12/10/2026, o oficial: «dê opção de
#: controle e fiscalização ao administrador, preciso poder filtrar os processos
#: por responsável, por prazo, por setor e por outras informações relevantes»).
# OS FILTROS E AS ORDENS SÃO DA RÉGUA COMUM (`tarefa_ordem`) desde 13/10/2026 —
# a tela «Tarefas» usa a mesma, e as duas não podem responder diferente.
FILTROS = ("origem", "q", "setor", "especie", *TO.FILTROS)
PRAZOS = TO.PRAZOS
PARADOS = TO.PARADOS
ORDENS = TO.ordens_da_tela(tem_tipo=True)
SEM_RESPONSAVEL = TO.SEM_RESPONSAVEL


def listar(con: Any, *, vista: str = "ABERTOS", usuario_id: int | None = None,
           origem: str = "", q: str = "", setor: str = "", hoje: date | None = None,
           limite: int = 500, **filtros: Any) -> list[dict]:
    """Os processos da vista pedida, filtrados, com o que a lista mostra. Só lê.

    Os filtros de fiscalização (`FILTROS`) vêm por nome; vazio quer dizer «não
    filtra». O «parado» se mede pelo último andamento (`task_history`), e a
    conta de dias é feita em Python — data calculada no SQL custa acoplamento."""
    ESP.init_schema(con)
    bd = banco(con)
    hoje_d = hoje or date.today()
    hoje_iso = hoje_d.isoformat()
    f = {k: str(v).strip() for k, v in filtros.items() if v not in (None, "")}
    cond_aberta, args_aberta = TP.condicao_aberta("t.status")
    where = [f"t.source_type NOT IN ({','.join(['%s'] * len(FORA_DOS_PROCESSOS))})"]
    args: list[Any] = list(FORA_DOS_PROCESSOS)
    if vista in ("ABERTOS", "COMIGO", "VENCIDOS"):
        where.append(cond_aberta)
        args += args_aberta
    elif vista == "ENCERRADOS":
        where.append(f"NOT ({cond_aberta})")
        args += args_aberta
    if vista == "COMIGO":
        where.append("(t.assigned_user_id = %s OR t.backup_user_id = %s)")
        args += [usuario_id, usuario_id]
    if vista == "VENCIDOS":
        # A suspensa não está vencida — relato #132: o prazo não corre enquanto
        # ela espera, e «vencido» é a palavra da cobrança.
        nao_suspensa, args_suspensao = TS.condicao_nao_suspensa("t", hoje_d)
        where += ["t.due_date IS NOT NULL AND t.due_date < %s", nao_suspensa]
        args += [hoje_iso, *args_suspensao]
    if vista in VISTAS_DA_REGUA:
        conds, params = TP.filtro_da_vista(vista, usuario_id)
        where += conds
        args += params
    if setor:
        where.append("t.sector = %s")
        args.append(setor)
    if origem:
        where.append("t.source_type = %s")
        args.append(origem)
    # A BUSCA É A DA RÉGUA COMUM desde 15/10/2026 (relato #122): a de «Tarefas»
    # procura também o número e o responsável, e as duas telas não podem achar
    # coisas diferentes com a mesma palavra. Aqui ela olha ainda o expediente.
    conds, params = TO.busca_sql(q, responsavel="ua.full_name",
                                 extras=("e.internal_protocol", "e.sender"))
    where += conds
    args += params
    # ---- os filtros de fiscalização: a régua comum (`tarefa_ordem`)
    conds, params = TO.filtros_sql(f, hoje=hoje_d, cond_aberta=cond_aberta,
                                   args_aberta=list(args_aberta),
                                   andamento="COALESCE((SELECT MAX(h.ts) FROM task_history h WHERE h.task_id = t.id), t.created_at)")
    where += conds
    args += params
    if f.get("especie") == "SEM_TIPO":
        where.append("pe.especie IS NULL")
    elif f.get("especie"):
        where.append("pe.especie = %s")
        args.append(f["especie"])
    ordem = TO.ordem_sql(f.get("ordem"), f.get("inverter"))
    # Os pedaços que vêm da régua comum (`tarefa_ordem`, `tarefa_processo`,
    # `tarefa_suspensao`) ainda trazem `?` e `LIKE` do SQLite; aqui viram PostgreSQL.
    onde = " AND ".join(where).replace("?", "%s").replace(" LIKE ", " ILIKE ")
    linhas = bd.ler(
        f"""SELECT t.id, t.title, t.status, t.priority, t.due_date, t.created_at, t.source_type, t.sector,
                   t.system_name, t.evidence_required,
                   (SELECT COUNT(*) FROM attachments a WHERE a.entity_type='TASK' AND a.entity_id=t.id) AS evidencias,
                   t.assigned_user_id, ua.full_name AS responsavel, ub.full_name AS substituto,
                   e.internal_protocol AS expediente, e.sender AS remetente, pe.especie,
                   t.suspensa_desde, t.suspensa_ate, t.suspensa_condicao, t.suspensa_motivo,
                   COALESCE((SELECT MAX(h.ts) FROM task_history h WHERE h.task_id = t.id), t.created_at)
                       AS ultimo_andamento
              FROM tasks t
              LEFT JOIN users ua ON ua.id = t.assigned_user_id
              LEFT JOIN users ub ON ub.id = t.backup_user_id
              LEFT JOIN expedientes e ON e.id = t.linked_expediente_id
              LEFT JOIN pr_especie_do_processo pe ON pe.task_id = t.id
             WHERE {onde}
             ORDER BY {ordem}
             LIMIT %s""", (*args, int(limite)))
    saida = []
    for r in linhas:
        d = {k: r[k] for k in r.keys()}
        d["numero"] = numero(d["created_at"], d["id"])
        d["origem"] = nome_da_origem(d["source_type"])
        d["especie_nome"] = ESP.CATALOGO.get(d["especie"] or "", {}).get("nome")
        d["suspensao"] = TS.situacao(d, hoje_d)
        d["vencido"] = bool(d["due_date"] and str(d["due_date"])[:10] < hoje_iso
                            and TP.tem_servico_em_andamento(d["status"])
                            and not d["suspensao"])
        d["dias_parado"] = _dias_desde(d["ultimo_andamento"], hoje_d)
        saida.append(d)
    return saida


def _dias_desde(quando: Any, hoje: date) -> int | None:
    try:
        return (hoje - date.fromisoformat(str(quando)[:10])).days
    except (TypeError, ValueError):
        return None


def quadro_de_fiscalizacao(con: Any, hoje: date | None = None) -> dict:
    """O controle do administrador: por responsável e por setor, quantos
    processos abertos, vencidos e parados há 7 dias ou mais — e os buracos
    da casa (sem responsável, sem prazo, sem
    tipo). Cada número vira filtro na tela. Só lê."""
    abertos = listar(con, vista="ABERTOS", hoje=hoje, limite=100000)
    por_pessoa: dict[Any, dict] = {}
    por_setor: dict[str, dict] = {}

    def _soma(alvo: dict, p: dict) -> None:
        alvo["abertos"] += 1
        alvo["vencidos"] += 1 if p["vencido"] else 0
        alvo["parados"] += 1 if (p["dias_parado"] or 0) >= 7 else 0
        alvo["criticos"] += 1 if p["priority"] == "CRITICA" else 0

    zero = {"abertos": 0, "vencidos": 0, "parados": 0, "criticos": 0}
    for p in abertos:
        chave = p["assigned_user_id"] or SEM_RESPONSAVEL
        _soma(por_pessoa.setdefault(chave, {"chave": chave, "nome": p["responsavel"] or "sem responsável", **zero}), p)
        s = p["sector"] or ""
        _soma(por_setor.setdefault(s, {"chave": s, "nome": s or "sem setor", **zero}), p)
    ordem = lambda d: (-d["vencidos"], -d["abertos"])  # noqa: E731
    return {
        "total": len(abertos),
        "vencidos": sum(1 for p in abertos if p["vencido"]),
        "parados": sum(1 for p in abertos if (p["dias_parado"] or 0) >= 7),
        "sem_responsavel": sum(1 for p in abertos if not p["assigned_user_id"]),
        "sem_prazo": sum(1 for p in abertos if not p["due_date"]),
        "sem_tipo": sum(1 for p in abertos if not p["especie"]),
        # As suspensas (relato #132) entram em «abertos», com o selo, e não em
        # «vencidos»: o número delas fica à vista para ninguém as esquecer.
        "suspensas": sum(1 for p in abertos if p["suspensao"]),
        "por_pessoa": sorted(por_pessoa.values(), key=ordem),
        "por_setor": sorted(por_setor.values(), key=ordem),
    }


def contagem(con: Any, usuario_id: int | None, hoje: date | None = None) -> dict:
    return {v: len(listar(con, vista=v, usuario_id=usuario_id, hoje=hoje, limite=100000))
            for v in ("COMIGO", "PASSOU_POR_MIM", "PEDIRAM_RESPOSTA", "ABERTOS", "VENCIDOS")}


def entradas_sem_processo(con: Any) -> list[dict]:
    """O que chegou pelo malote e ainda não virou processo nem recebeu «só
    ciência». Só lê."""
    marcas = ",".join(["%s"] * len(ESTAGIOS_ENCERRADOS))
    linhas = banco(con).ler(
        f"""SELECT e.id, e.internal_protocol, e.subject, e.sender, e.received_at, e.category, e.sector,
                   e.deadline_date, e.stage,
                   (SELECT COUNT(*) FROM attachments a WHERE a.entity_type='EXPEDIENTE'
                       AND a.entity_id = e.id) AS documentos
              FROM expedientes e
             WHERE e.stage NOT IN ({marcas})
               AND NOT EXISTS (SELECT 1 FROM tasks t WHERE t.linked_expediente_id = e.id)
             ORDER BY e.received_at, e.id""", ESTAGIOS_ENCERRADOS)
    saida = []
    for r in linhas:
        d = {k: r[k] for k in r.keys()}
        d["especie_sugerida"] = ESP.sugerir({"source_type": "EXPEDIENTE", "title": d["subject"],
                                             "description": d["category"]})
        saida.append(d)
    return saida


def dados_do_processo_do_expediente(exp: dict) -> dict:
    """O que o processo herda da entrada do malote."""
    return {
        "source_type": "EXPEDIENTE", "source_ref": exp["internal_protocol"],
        "title": exp["subject"] or f"Expediente {exp['internal_protocol']}",
        "description": (f"Entrada do malote {exp['internal_protocol']}"
                        + (f", de {exp['sender']}" if exp.get("sender") else "")
                        + (f", recebida em {exp['received_at']}" if exp.get("received_at") else "")
                        + ". Os documentos recebidos estão na pasta do processo."),
        "sector": exp.get("sector"), "priority": exp.get("priority") or "MEDIA",
        "due_date": exp.get("deadline_date"), "assigned_user_id": exp.get("assigned_user_id"),
        "backup_user_id": exp.get("backup_user_id"), "linked_expediente_id": exp["id"],
    }
