"""Hotfix de 06/10/2026: a evidência não é mais exigida por padrão, e a tela
da tarefa liga e desliga a exigência com um clique.

Ordem do oficial: «tire a regra de exigir evidencia para todas as tarefas e
facilite a edicao para nao exigir mais evidencia quando entender nao cabivel».
"""
from __future__ import annotations

import sqlite3

AGORA = "2026-10-06T18:00:00"


def _tarefa(banco, exige=1):
    con = sqlite3.connect(banco)
    tid = con.execute(
        """INSERT INTO tasks (source_type, title, status, priority, evidence_required,
               created_at, updated_at) VALUES ('MANUAL', 'T', 'ABERTA', 'MEDIA', ?, ?, ?)""",
        (exige, AGORA, AGORA)).lastrowid
    con.commit()
    con.close()
    return tid


def _token(c):
    with c.session_transaction() as s:
        return s.get("csrf_token")


def test_o_formulario_de_nova_tarefa_nao_vem_marcado(cg_casa_logada):
    html = cg_casa_logada["c"].get("/tarefas").get_data(as_text=True)
    assert 'name="evidence_required" value="1" checked' not in html


def test_criar_sem_dizer_nada_nao_exige(cg_casa_logada):
    tid = cg_casa_logada["db"].create_task({"title": "Sem evidência"}, None)
    con = sqlite3.connect(cg_casa_logada["banco"])
    assert con.execute("SELECT evidence_required FROM tasks WHERE id=?", (tid,)).fetchone()[0] == 0
    con.close()


def test_um_clique_dispensa_e_a_tarefa_conclui(cg_casa_logada):
    c, banco = cg_casa_logada["c"], cg_casa_logada["banco"]
    tid = _tarefa(banco, exige=1)
    pagina = c.get(f"/tarefas/{tid}").get_data(as_text=True)
    # 12/10/2026: o botão passou de «Não exigir evidência» a «Dispensar a
    # evidência» — o oficial não entendeu o campo «Por que não cabe?» ao lado.
    assert "Dispensar a evidência" in pagina
    c.post(f"/tarefas/{tid}", data={"action": "evidencia", "exigir": "0",
                                    "motivo": "ato interno", "csrf_token": _token(c)})
    c.post(f"/tarefas/{tid}", data={"action": "concluir", "csrf_token": _token(c)})
    con = sqlite3.connect(banco)
    assert con.execute("SELECT evidence_required, status FROM tasks WHERE id=?",
                       (tid,)).fetchone() == (0, "CONCLUIDA")
    assert con.execute("SELECT count(*) FROM audit_logs WHERE action='TASK_EVIDENCIA_ALTERADA'"
                       ).fetchone()[0] == 1
    con.close()


def test_e_volta_a_exigir_com_outro_clique(cg_casa_logada):
    c, banco = cg_casa_logada["c"], cg_casa_logada["banco"]
    tid = _tarefa(banco, exige=0)
    assert "Passar a exigir evidência" in c.get(f"/tarefas/{tid}").get_data(as_text=True)
    c.post(f"/tarefas/{tid}", data={"action": "evidencia", "exigir": "1", "csrf_token": _token(c)})
    con = sqlite3.connect(banco)
    assert con.execute("SELECT evidence_required FROM tasks WHERE id=?", (tid,)).fetchone()[0] == 1
    con.close()
