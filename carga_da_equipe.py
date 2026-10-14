"""A carga de trabalho da equipe, as tarefas repetidas e as que se agrupam.

    «precisamos evitar tarefas repetidas, equalizar melhor a carga de trabalho
     e consolidar os relatos diários»               — o oficial, 12/10/2026

MEDIDO ANTES (produção, 12/10/2026, só leitura):
    - 149 tarefas abertas; Leidiane 44 (17 vencidas), jean 26, Vanessa 22,
      Gerlany 18, Andreia 15, alessandro 13, Matheus 11;
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
import sqlite3
import unicodedata
from collections import defaultdict
from datetime import date
from typing import Any

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


# ------------------------------------------------------------- a guarda

def tarefa_igual_aberta(con: sqlite3.Connection, dados: dict) -> int | None:
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
    for r in con.execute(
            f"SELECT id, title, source_ref, description FROM tasks WHERE {cond} "
            "AND COALESCE(assigned_user_id, 0) = COALESCE(?, 0)",
            (*params, dados.get("assigned_user_id"))).fetchall():
        if _norm(r[1]) != titulo:
            continue
        if ref:
            if (r[2] or "").strip() == ref:
                return int(r[0])
        elif _norm(r[3])[:200] == desc:
            return int(r[0])
    return None


# ------------------------------------------------------------- a carga

def carga(con: sqlite3.Connection, hoje: date | None = None) -> list[dict]:
    """Por pessoa: abertas, vencidas, alta/crítica e pontos."""
    hoje_iso = (hoje or date.today()).isoformat()
    por: dict[int, dict] = {}
    nomes = {r[0]: (r[1] or r[2]) for r in con.execute("SELECT id, full_name, username FROM users")}
    for uid, prio, venc in con.execute(
            "SELECT assigned_user_id, priority, due_date FROM tasks WHERE status NOT IN (?, ?) "
            "AND assigned_user_id IS NOT NULL", FECHADAS):
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


def sugestoes_de_passagem(con: sqlite3.Connection, hoje: date | None = None,
                          limite: int = 15) -> list[dict]:
    """Tarefas do titular sobrecarregado que o substituto (já gravado na
    tarefa) poderia assumir: o titular tem pelo menos 1,5× os pontos dele.
    As vencidas primeiro. Só sugere."""
    pontos = {d["usuario_id"]: d["pontos"] for d in carga(con, hoje)}
    nomes = {r[0]: (r[1] or r[2]) for r in con.execute("SELECT id, full_name, username FROM users")}
    hoje_iso = (hoje or date.today()).isoformat()
    saida = []
    for tid, titulo, dono, sub, venc, prio in con.execute(
            "SELECT id, title, assigned_user_id, backup_user_id, due_date, priority FROM tasks "
            "WHERE status NOT IN (?, ?) AND backup_user_id IS NOT NULL "
            "AND backup_user_id <> assigned_user_id "
            "ORDER BY CASE WHEN due_date < ? THEN 0 ELSE 1 END, due_date", (*FECHADAS, hoje_iso)):
        p_dono, p_sub = pontos.get(dono, 0), pontos.get(sub, 0)
        if p_dono and p_dono >= FOLGA_PARA_SUGERIR * max(p_sub, 1):
            saida.append({"id": tid, "titulo": titulo, "de": nomes.get(dono, dono),
                          "para": nomes.get(sub, sub), "prazo": venc, "prioridade": prio,
                          "vencida": bool(venc and str(venc)[:10] < hoje_iso)})
        if len(saida) >= limite:
            break
    return saida


def agrupaveis(con: sqlite3.Connection) -> list[dict]:
    """Grupos de tarefas abertas da mesma pessoa com o mesmo título-família
    (números à parte) — candidatas a virar uma tarefa só. Só sugere."""
    grupos: dict[tuple, list] = defaultdict(list)
    for tid, titulo, dono in con.execute(
            "SELECT id, title, assigned_user_id FROM tasks WHERE status NOT IN (?, ?)", FECHADAS):
        grupos[(dono, _familia(titulo))].append((tid, titulo))
    nomes = {r[0]: (r[1] or r[2]) for r in con.execute("SELECT id, full_name, username FROM users")}
    saida = [{"de": nomes.get(dono, dono), "familia": fam, "tarefas": v}
             for (dono, fam), v in grupos.items() if len(v) > 1]
    return sorted(saida, key=lambda g: -len(g["tarefas"]))


def prioridade_inflada(con: sqlite3.Connection) -> dict:
    """Quantas das abertas estão em ALTA/CRÍTICA."""
    total, altas = con.execute(
        "SELECT COUNT(*), SUM(CASE WHEN priority IN ('ALTA','CRITICA') THEN 1 ELSE 0 END) "
        "FROM tasks WHERE status NOT IN (?, ?)", FECHADAS).fetchone()
    return {"abertas": total or 0, "altas": altas or 0,
            "percentual": round(100 * (altas or 0) / total) if total else 0}


def texto_do_relato(con: sqlite3.Connection, hoje: date | None = None) -> tuple[str, int]:
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
