# -*- coding: utf-8 -*-
"""Os relatos do dia, a carga da equipe e a tarefa repetida.

    «precisamos evitar tarefas repetidas, equalizar melhor a carga de trabalho
     e consolidar os relatos diários. não acho interessante todo dia criar um
     relatório geral em tarefa para o gestor (...) talvez seja interessante os
     relatos diários ficarem num campo próprio, um módulo ou janela no painel»
                                                    — o oficial, 12/10/2026
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date

import carga_da_equipe as CARGA
import relatos_diarios as RD
import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

HOJE = date(2026, 10, 12)


def _con():
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, full_name TEXT,
        role TEXT)""")
    con.execute("""CREATE TABLE tasks (id INTEGER PRIMARY KEY, source_type TEXT, source_ref TEXT,
        title TEXT, description TEXT, priority TEXT, status TEXT, due_date TEXT,
        assigned_user_id INTEGER, backup_user_id INTEGER, completed_at TEXT, updated_at TEXT)""")
    con.execute("""CREATE TABLE task_history (id INTEGER PRIMARY KEY, task_id INTEGER, ts TEXT,
        user_id INTEGER, action TEXT, old_value TEXT, new_value TEXT, note TEXT)""")
    con.executemany("INSERT INTO users VALUES (?,?,?,?)", [
        (1, "mario", "Mario Exemplo dos Santos", "ADMIN"),
        (2, "beatriz", "Beatriz Exemplo de Souza", "USER"),
        (3, "carla", "Carla Exemplo Lima", "USER")])
    return con


def _um(db, sql, args=()):
    with db.connect() as con:
        return con.execute(sql, args).fetchone()


def _tarefa(con, titulo, dono, prio="MEDIA", prazo=None, sub=None, ref=None, status="ABERTA"):
    return con.execute("INSERT INTO tasks(source_type, source_ref, title, priority, status, due_date, "
                       "assigned_user_id, backup_user_id) VALUES ('MANUAL',?,?,?,?,?,?,?)",
                       (ref, titulo, prio, status, prazo, dono, sub)).lastrowid


# ------------------------------------------------------------ os relatos

def test_relato_do_dia_renova_e_volta_a_nao_lido_quando_muda():
    con = _con()
    a = RD.publicar(con, dia=HOJE, origem="GESTOR_DESPACHO", titulo="Despacho", corpo="um")
    assert RD.marcar_lido(con, a, usuario_id=1, ve_a_gestao=True)
    b = RD.publicar(con, dia=HOJE, origem="GESTOR_DESPACHO", titulo="Despacho", corpo="um")
    assert a == b and not [r for r in RD.do_dia(con, dia=HOJE, usuario_id=1, ve_a_gestao=True) if not r["lido_em"]]
    RD.publicar(con, dia=HOJE, origem="GESTOR_DESPACHO", titulo="Despacho", corpo="dois")
    assert RD.do_dia(con, dia=HOJE, usuario_id=1, ve_a_gestao=True)[0]["lido_em"] is None


def test_cada_um_ve_os_seus_e_so_a_gestao_ve_os_da_gestao():
    con = _con()
    RD.publicar(con, dia=HOJE, origem="GESTOR_DESPACHO", titulo="Despacho", corpo="x")
    RD.publicar(con, dia=HOJE, origem="GESTOR_COBRANCA", destinatario_id=2, titulo="Cobrança",
                corpo="y")
    assert [r["origem"] for r in RD.do_dia(con, dia=HOJE, usuario_id=2, ve_a_gestao=False)] == [
        "GESTOR_COBRANCA"]
    assert len(RD.do_dia(con, dia=HOJE, usuario_id=1, ve_a_gestao=True)) == 1
    gestao = RD.do_dia(con, dia=HOJE, usuario_id=1, ve_a_gestao=True)[0]["id"]
    assert not RD.marcar_lido(con, gestao, usuario_id=2, ve_a_gestao=False)


def test_aposentar_fecha_a_tarefa_relatorio_com_o_porque():
    con = _con()
    con.execute("INSERT INTO tasks(source_type, title, status) VALUES ('DESPACHO','[Despacho]','ABERTA')")
    assert RD.aposentar_tarefas_diarias(con, "DESPACHO", "virou relato") == 1
    assert con.execute("SELECT status FROM tasks").fetchone()[0] == "CONCLUIDA"
    assert con.execute("SELECT note FROM task_history").fetchone()[0] == "virou relato"


# ----------------------------------------------------- a tarefa repetida

def test_tarefa_igual_aberta_acha_o_mesmo_pedido_e_nao_o_de_outro_numero():
    con = _con()
    t = _tarefa(con, "Conferir prenotação 11.548", 2)
    _tarefa(con, "Conferir prenotação 11.548", 3)                       # outra pessoa
    _tarefa(con, "Conferir prenotação 11.548", 2, status="CONCLUIDA")   # já fechada
    assert CARGA.tarefa_igual_aberta(con, {"title": "conferir  prenotação 11.548",
                                           "assigned_user_id": 2}) == t
    assert CARGA.tarefa_igual_aberta(con, {"title": "Conferir prenotação 11.549",
                                           "assigned_user_id": 2}) is None


def test_create_task_repetida_nao_abre_outra_e_anota_na_existente(cg_casa_logada):
    db = cg_casa_logada["db"]
    uid = _um(db, "SELECT id FROM users WHERE username='mario'")[0]
    dados = {"source_type": "MANUAL", "title": "Pedir certidão ao cartório vizinho",
             "assigned_user_id": uid, "priority": "MEDIA"}
    a = db.create_task(dados, user_id=uid)
    b = db.create_task(dict(dados), user_id=uid)
    assert a == b
    assert _um(db, "SELECT count(*) AS n FROM tasks WHERE title=?", (dados["title"],))[0] == 1
    nota = _um(db, "SELECT note FROM task_history WHERE task_id=? AND action='NOTA' "
                  "ORDER BY id DESC", (a,))[0]
    assert "repetido" in nota


# ------------------------------------------------------------ a carga

def test_carga_pesa_prioridade_e_vencida():
    con = _con()
    _tarefa(con, "a", 2, "CRITICA", "2026-10-01")    # 3 + 2
    _tarefa(con, "b", 2, "MEDIA")                    # 1
    _tarefa(con, "c", 3, "ALTA")                     # 2
    c = {d["usuario_id"]: d for d in CARGA.carga(con, HOJE)}
    assert (c[2]["pontos"], c[2]["vencidas"], c[2]["altas"]) == (6, 1, 1)
    assert c[3]["pontos"] == 2


def test_sugere_passar_ao_substituto_so_quando_o_titular_carrega_mais():
    con = _con()
    for i in range(4):
        _tarefa(con, f"t{i}", 2, "ALTA", sub=3)
    _tarefa(con, "da carla", 3, "MEDIA")
    sug = CARGA.sugestoes_de_passagem(con, HOJE)
    assert sug and all(s["para"] == "Carla Exemplo Lima" for s in sug)
    con.execute("UPDATE tasks SET status='CONCLUIDA' WHERE assigned_user_id=2 AND title<>'t0'")
    _tarefa(con, "outra da carla", 3, "ALTA")
    assert CARGA.sugestoes_de_passagem(con, HOJE) == []     # 2 pontos contra 3: não sugere


def test_agrupaveis_junta_a_mesma_familia_de_titulo_da_mesma_pessoa():
    con = _con()
    _tarefa(con, "CNIB: ordem 101 sobre a matrícula 1234", 2)
    _tarefa(con, "CNIB: ordem 102 sobre a matrícula 1234", 2)
    _tarefa(con, "CNIB: ordem 103 sobre a matrícula 1234", 3)
    g = CARGA.agrupaveis(con)
    assert len(g) == 1 and len(g[0]["tarefas"]) == 2


# ------------------------------------------------------------- a tela

def test_janela_no_painel_e_marcar_como_lido(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    with db.transaction() as con:
        RD.publicar(con, dia=date.today(), origem="GESTOR_DESPACHO",
                    titulo="Despacho do gestor — teste", corpo="O QUE SÓ VOCÊ DECIDE: nada")
    html = c.get("/").get_data(as_text=True)
    assert "Relatos do dia" in html and "Despacho do gestor — teste" in html
    assert "Carga da equipe" in html or "Nenhum relato" not in html
    tok = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    rid = _um(db, "SELECT id FROM rd_relatos")[0]
    c.post(f"/relatos/{rid}/lido", data={"csrf_token": tok, "voltar": "/"})
    assert _um(db, "SELECT lido_em FROM rd_relatos WHERE id=?", (rid,))[0]
    pagina = c.get("/relatos").get_data(as_text=True)
    assert "Despacho do gestor — teste" in pagina and "A carga da equipe agora" in pagina


def test_ler_o_painel_nao_grava_nada(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    antes = _um(db, "SELECT count(*) AS n FROM rd_relatos")[0]
    c.get("/")
    c.get("/relatos")
    assert _um(db, "SELECT count(*) AS n FROM rd_relatos")[0] == antes


# ------------------------------------- os documentos do expediente na tarefa

def test_a_tarefa_mostra_os_documentos_do_expediente_de_onde_nasceu(cg_casa_logada):
    """12/10/2026: a tarefa da averbação de divórcio nasceu do malote e o
    mandado estava no expediente — a tela da tarefa não o mostrava."""
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    uid = _um(db, "SELECT id FROM users WHERE username='mario'")[0]
    exp = db.create_expediente({"source": "Malote Digital", "subject": "Mandado de averbação de divórcio",
                                "sender": "Vara de Exemplo", "category": "Para Cumprimento",
                                "received_at": "2026-08-19"}, uid)
    db.add_attachment("EXPEDIENTE", exp, {"original_name": "Mandado de Exemplo.pdf", "stored_name": "m.pdf",
                                          "stored_path": "m.pdf", "sha256": "0" * 64, "size_bytes": 10}, uid)
    tid = db.create_task({"source_type": "EXPEDIENTE", "title": "Cumprir o mandado de exemplo",
                          "assigned_user_id": uid, "linked_expediente_id": exp}, user_id=uid)
    html = c.get(f"/tarefas/{tid}").get_data(as_text=True)
    assert "Pasta do processo" in html and "Mandado de Exemplo.pdf" in html
