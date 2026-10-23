"""A carga de trabalho da equipe, as tarefas repetidas e as que se agrupam.

    «precisamos evitar tarefas repetidas, equalizar melhor a carga de trabalho
     e consolidar os relatos diários»               — o oficial, 12/10/2026

MEDIDO ANTES (produção, 12/10/2026, só leitura):
    - 149 tarefas abertas; escrevente A 44 (17 vencidas), oficial 26, escrevente B 22,
      escrevente C 18, escrevente D 15, escrevente E 13, escrevente F 11;
    - 124 das 149 marcadas ALTA ou CRÍTICA — quando quase tudo é crítico, a
      prioridade deixa de ordenar;
    - «repetidas» de verdade quase não há: as seis do CNIB com o mesmo título
      são ordens DIFERENTES sobre a mesma matrícula (duas ordens contra a
      mesma empresa em cada uma de três fichas); os três «GEORREFERENCIAMENTO»
      são processos diferentes com título pobre. São AGRUPÁVEIS, e não cópias.

O QUE ESTE MÓDULO FAZ: mede e sugere. Não reatribui nem fecha nada — passar
tarefa e juntar tarefas é decisão de quem distribui (a tela já tem «passar»).
A única coisa que ele impede é a tarefa IGUAL nascer de novo
(`tarefa_igual_aberta`, chamada por `database.create_task`).
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import date
from typing import Any

from bd_nativo import banco

#: Peso de cada tarefa aberta na carga. Vencida pesa mais: é a que trava.
PESO = {"CRITICA": 3, "ALTA": 2, "MEDIA": 1, "BAIXA": 1}
PESO_VENCIDA = 2
#: Sugere passar ao substituto quando o titular carrega pelo menos isto a mais.
FOLGA_PARA_SUGERIR = 1.5
FECHADAS = ("CONCLUIDA", "CANCELADA")


def _norm(texto: Any) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", str(texto or ""))
                if unicodedata.category(c) != "Mn").lower()
    t = re.sub(r"[^\w#]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _familia(titulo: Any) -> str:
    """O título sem os números: «cnib revisar ... matricula # #-h»."""
    return re.sub(r"\d+", "#", _norm(titulo))


def _nomes(con: Any) -> dict:
    return {r["id"]: (r["full_name"] or r["username"]) for r in banco(con).ler(
        "SELECT id, full_name, username FROM users ORDER BY id")}


# ------------------------------------------------------------- a guarda

def tarefa_igual_aberta(con: Any, dados: dict) -> int | None:
    """Já existe tarefa ABERTA igual a esta? Igual = mesmo título (sem acento,
    caixa e pontuação, mas COM os números), mesmo responsável, e — quando a nova
    traz `source_ref` — a mesma referência; sem referência, o mesmo começo de
    descrição. Devolve o id da que já existe."""
    titulo = _norm(dados.get("title"))
    if not titulo:
        return None
    ref = (dados.get("source_ref") or "").strip()
    desc = _norm(dados.get("description"))[:200]
    # A MESMA RÉGUA DE «ABERTA» DA LISTA (`tarefa_processo.condicao_aberta`), e não
    # o filtro negativo: tarefa com palavra fora do vocabulário não é serviço em
    # aberto conhecido, e não pode engolir a tarefa nova. Correção do mesmo dia
    # (12/10/2026): a primeira versão usava `NOT IN (CONCLUIDA, CANCELADA)`, e o
    # teste do relato #59 com uma tarefa «PENDENTE» pegou.
    import tarefa_processo as TP
    cond, params = TP.condicao_aberta("status")
    # `condicao_aberta` ainda devolve `?` (módulo fora do lote): troca aqui.
    for r in banco(con).ler(
            f"SELECT id, title, source_ref, description FROM tasks WHERE {cond.replace('?', '%s')} "
            "AND COALESCE(assigned_user_id, 0) = COALESCE(%s, 0) ORDER BY id",
            (*params, dados.get("assigned_user_id"))):
        if _norm(r["title"]) != titulo:
            continue
        if ref:
            if (r["source_ref"] or "").strip() == ref:
                return int(r["id"])
        elif _norm(r["description"])[:200] == desc:
            return int(r["id"])
    return None


# ------------------------------------------------------------- a carga

def carga(con: Any, hoje: date | None = None) -> list[dict]:
    """Por pessoa: abertas, vencidas, alta/crítica e pontos."""
    hoje_iso = (hoje or date.today()).isoformat()
    por: dict[int, dict] = {}
    nomes = _nomes(con)
    # A SUSPENSA NÃO PESA NA CARGA (relato #132): enquanto espera o cliente ou
    # a data, ela não é serviço na mão de ninguém, nem vencida.
    import tarefa_suspensao as TS
    nao_suspensa, params_suspensao = TS.condicao_nao_suspensa(None, hoje_iso, con=con)
    for r in banco(con).ler(
            "SELECT assigned_user_id, priority, due_date FROM tasks WHERE status NOT IN (%s, %s) "
            f"AND assigned_user_id IS NOT NULL AND {nao_suspensa.replace('?', '%s')} ORDER BY id",
            (*FECHADAS, *params_suspensao)):
        uid, prio, venc = r["assigned_user_id"], r["priority"], r["due_date"]
        d = por.setdefault(uid, {"usuario_id": uid, "nome": nomes.get(uid, str(uid)), "abertas": 0,
                                 "vencidas": 0, "altas": 0, "pontos": 0})
        d["abertas"] += 1
        d["pontos"] += PESO.get(prio or "MEDIA", 1)
        if prio in ("CRITICA", "ALTA"):
            d["altas"] += 1
        if venc and str(venc)[:10] < hoje_iso:
            d["vencidas"] += 1
            d["pontos"] += PESO_VENCIDA
    return sorted(por.values(), key=lambda d: -d["pontos"])


def sugestoes_de_passagem(con: Any, hoje: date | None = None,
                          limite: int = 15) -> list[dict]:
    """Tarefas do titular sobrecarregado que o substituto (já gravado na
    tarefa) poderia assumir: o titular tem pelo menos 1,5× os pontos dele.
    As vencidas primeiro. Só sugere."""
    pontos = {d["usuario_id"]: d["pontos"] for d in carga(con, hoje)}
    nomes = _nomes(con)
    hoje_iso = (hoje or date.today()).isoformat()
    saida = []
    import tarefa_suspensao as TS
    nao_suspensa, params_suspensao = TS.condicao_nao_suspensa(None, hoje_iso, con=con)
    for r in banco(con).ler(
            "SELECT id, title, assigned_user_id, backup_user_id, due_date, priority FROM tasks "
            "WHERE status NOT IN (%s, %s) AND backup_user_id IS NOT NULL "
            f"AND backup_user_id <> assigned_user_id AND {nao_suspensa.replace('?', '%s')} "
            "ORDER BY CASE WHEN due_date < %s THEN 0 ELSE 1 END, due_date, id",
            (*FECHADAS, *params_suspensao, hoje_iso)):
        tid, titulo, dono, sub, venc, prio = (
            r["id"], r["title"], r["assigned_user_id"], r["backup_user_id"],
            r["due_date"], r["priority"])
        p_dono, p_sub = pontos.get(dono, 0), pontos.get(sub, 0)
        if p_dono and p_dono >= FOLGA_PARA_SUGERIR * max(p_sub, 1):
            saida.append({"id": tid, "titulo": titulo, "de": nomes.get(dono, dono),
                          "para": nomes.get(sub, sub), "prazo": venc, "prioridade": prio,
                          "vencida": bool(venc and str(venc)[:10] < hoje_iso)})
        if len(saida) >= limite:
            break
    return saida


def agrupaveis(con: Any) -> list[dict]:
    """Grupos de tarefas abertas da mesma pessoa com o mesmo título-família
    (números à parte) — candidatas a virar uma tarefa só. Só sugere."""
    grupos: dict[tuple, list] = defaultdict(list)
    for r in banco(con).ler(
            "SELECT id, title, assigned_user_id FROM tasks WHERE status NOT IN (%s, %s) ORDER BY id",
            FECHADAS):
        tid, titulo, dono = r["id"], r["title"], r["assigned_user_id"]
        grupos[(dono, _familia(titulo))].append((tid, titulo))
    nomes = _nomes(con)
    saida = [{"de": nomes.get(dono, dono), "familia": fam, "tarefas": v}
             for (dono, fam), v in grupos.items() if len(v) > 1]
    return sorted(saida, key=lambda g: -len(g["tarefas"]))


def prioridade_inflada(con: Any) -> dict:
    """Quantas das abertas estão em ALTA/CRÍTICA."""
    r = banco(con).um(
        "SELECT COUNT(*)::int AS total, "
        "SUM(CASE WHEN priority IN ('ALTA','CRITICA') THEN 1 ELSE 0 END)::int AS altas "
        "FROM tasks WHERE status NOT IN (%s, %s)", FECHADAS)
    total, altas = r["total"], r["altas"]
    return {"abertas": total or 0, "altas": altas or 0,
            "percentual": round(100 * (altas or 0) / total) if total else 0}


def texto_do_relato(con: Any, hoje: date | None = None) -> tuple[str, int]:
    """O relato diário da carga, para a Gestão. Devolve (texto, nº de itens)."""
    linhas = ["A CARGA DE CADA UM (pontos: crítica 3, alta 2, média 1; vencida +2)"]
    c = carga(con, hoje)
    for d in c:
        linhas.append(f"   {d['nome']}: {d['abertas']} aberta(s), {d['vencidas']} vencida(s), "
                      f"{d['altas']} alta/crítica — {d['pontos']} pontos")
    inf = prioridade_inflada(con)
    linhas += ["", f"PRIORIDADE: {inf['altas']} de {inf['abertas']} abertas ({inf['percentual']}%) "
               "estão em ALTA ou CRÍTICA. Quando quase tudo é crítico, a ordem da lista não ajuda."]
    sug = sugestoes_de_passagem(con, hoje)
    linhas += ["", f"PODERIAM PASSAR AO SUBSTITUTO ({len(sug)}) — o titular carrega 1,5× mais"]
    linhas += [f"   #{s['id']} {s['titulo']} — de {s['de']} para {s['para']}"
               + (" — VENCIDA" if s["vencida"] else "") for s in sug] or ["   nenhuma"]
    grp = agrupaveis(con)
    linhas += ["", f"PODERIAM VIRAR UMA TAREFA SÓ ({len(grp)} grupo(s))"]
    linhas += [f"   {g['de']}: " + ", ".join(f"#{t[0]}" for t in g["tarefas"]) + f" — «{g['tarefas'][0][1]}»"
               for g in grp[:15]] or ["   nenhum"]
    return "\n".join(linhas), len(sug) + len(grp)
