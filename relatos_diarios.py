"""Os relatos do dia — um lugar próprio, fora da lista de tarefas.

    «não acho interessante todo dia criar um relatório geral em tarefa para o
     gestor, se ele não conseguir vencer num dia, fica acumulando muitas
     tarefas. talvez seja interessante os relatos diários ficarem num campo
     próprio, um módulo ou janela no painel»        — o oficial, 12/10/2026

MEDIDO ANTES (produção, 12/10/2026, só leitura): 149 tarefas abertas; uma tarefa
«[Despacho] O dia do oficial» nascia todo dia (7 desde 06/10), outra «[RCPN] O
dia do Registro Civil» idem, e a cobrança diária gravava uma NOTA em cada
tarefa vencida — 208 notas do robô na história das tarefas.

O QUE É UM RELATO: o que um agente tem a dizer naquele dia a uma pessoa (ou à
Gestão). NÃO É TAREFA: não tem prazo, não vence, não se conclui — se lê. Um por
origem, por pessoa, por dia: a rodada das 07:30, 14:00 e 14:30 RENOVA o do dia
em vez de empilhar, e o de ontem fica no histórico, sem cobrar ninguém.

`destinatario_id = 0` quer dizer «a Gestão» (o oficial): o NULL não serve na
chave única do SQLite, que trata dois NULL como diferentes.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS rd_relatos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dia TEXT NOT NULL,
    origem TEXT NOT NULL,
    destinatario_id INTEGER NOT NULL DEFAULT 0,
    setor TEXT,
    titulo TEXT NOT NULL,
    corpo TEXT NOT NULL,
    itens INTEGER NOT NULL DEFAULT 0,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    lido_em TEXT,
    lido_por INTEGER,
    UNIQUE(dia, origem, destinatario_id)
);
CREATE INDEX IF NOT EXISTS idx_rd_relatos_dia ON rd_relatos(dia DESC, destinatario_id);
"""

GESTAO = 0

#: Os nomes que a tela mostra para cada origem.
ORIGENS = {
    "GESTOR_DESPACHO": "Despacho do gestor — o dia do oficial",
    "GESTOR_COBRANCA": "Cobrança do dia — tarefas vencidas",
    "RCPN_BOLETIM": "O dia do Registro Civil",
    "CARGA_DA_EQUIPE": "A carga de trabalho da equipe",
}


def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def publicar(con: sqlite3.Connection, *, dia: date | str, origem: str, titulo: str,
             corpo: str, destinatario_id: int | None = None, setor: str | None = None,
             itens: int = 0) -> int:
    """Cria ou RENOVA o relato do dia (mesma origem, mesma pessoa).

    Renovar com texto diferente devolve o relato a «não lido»: o que mudou
    depois da leitura é coisa nova para quem lê."""
    init_schema(con)
    dia = dia.isoformat() if isinstance(dia, date) else str(dia)[:10]
    dest = int(destinatario_id or GESTAO)
    agora = _agora()
    atual = con.execute("SELECT id, corpo FROM rd_relatos WHERE dia=? AND origem=? AND destinatario_id=?",
                        (dia, origem, dest)).fetchone()
    if atual:
        mudou = (atual[1] or "") != corpo
        con.execute("UPDATE rd_relatos SET titulo=?, corpo=?, itens=?, setor=?, atualizado_em=?"
                    + (", lido_em=NULL, lido_por=NULL" if mudou else "") + " WHERE id=?",
                    (titulo, corpo, int(itens), setor, agora, atual[0]))
        return int(atual[0])
    cur = con.execute(
        "INSERT INTO rd_relatos(dia, origem, destinatario_id, setor, titulo, corpo, itens, "
        "criado_em, atualizado_em) VALUES (?,?,?,?,?,?,?,?,?)",
        (dia, origem, dest, setor, titulo, corpo, int(itens), agora, agora))
    return int(cur.lastrowid)


def do_dia(con: sqlite3.Connection, *, dia: date | str, usuario_id: int,
           ve_a_gestao: bool) -> list[dict]:
    """Os relatos do dia para quem está olhando: os dele e, para o oficial e o
    gerente, os da Gestão. Os não lidos primeiro."""
    init_schema(con)
    dia = dia.isoformat() if isinstance(dia, date) else str(dia)[:10]
    alvos = [int(usuario_id)] + ([GESTAO] if ve_a_gestao else [])
    marcas = ",".join("?" * len(alvos))
    con.row_factory = sqlite3.Row
    rows = con.execute(
        f"SELECT * FROM rd_relatos WHERE dia=? AND destinatario_id IN ({marcas}) "
        "ORDER BY CASE WHEN lido_em IS NULL THEN 0 ELSE 1 END, origem",
        (dia, *alvos)).fetchall()
    return [dict(r, nome_da_origem=ORIGENS.get(r["origem"], r["origem"])) for r in rows]


def dias_com_relato(con: sqlite3.Connection, *, usuario_id: int, ve_a_gestao: bool,
                    limite: int = 30) -> list[str]:
    init_schema(con)
    alvos = [int(usuario_id)] + ([GESTAO] if ve_a_gestao else [])
    marcas = ",".join("?" * len(alvos))
    return [r[0] for r in con.execute(
        f"SELECT DISTINCT dia FROM rd_relatos WHERE destinatario_id IN ({marcas}) "
        "ORDER BY dia DESC LIMIT ?", (*alvos, int(limite)))]


def marcar_lido(con: sqlite3.Connection, relato_id: int, *, usuario_id: int,
                ve_a_gestao: bool) -> bool:
    row = con.execute("SELECT destinatario_id FROM rd_relatos WHERE id=?", (int(relato_id),)).fetchone()
    if not row or (row[0] != int(usuario_id) and not (row[0] == GESTAO and ve_a_gestao)):
        return False
    con.execute("UPDATE rd_relatos SET lido_em=?, lido_por=? WHERE id=?",
                (_agora(), int(usuario_id), int(relato_id)))
    return True


def aposentar_tarefas_diarias(con: sqlite3.Connection, source_type: str, nota: str) -> int:
    """Fecha as tarefas-relatório que ainda estejam abertas (o despacho, o
    boletim): o relato do dia passa a morar em `rd_relatos`."""
    agora = _agora()
    ids = [r[0] for r in con.execute(
        "SELECT id FROM tasks WHERE source_type=? AND status NOT IN ('CONCLUIDA','CANCELADA')",
        (source_type,))]
    for tid in ids:
        con.execute("UPDATE tasks SET status='CONCLUIDA', completed_at=?, updated_at=? WHERE id=?",
                    (agora, agora, tid))
        con.execute("INSERT INTO task_history(task_id, ts, user_id, action, old_value, new_value, note) "
                    "VALUES (?,?,NULL,'ALTEROU_STATUS','ABERTA','CONCLUIDA',?)", (tid, agora, nota))
    return len(ids)
