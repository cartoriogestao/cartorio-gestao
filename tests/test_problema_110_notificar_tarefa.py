"""Relato #110 — notificar alguém na tarefa sem passar a responsabilidade."""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import tarefa_processo as TP
from conftest import cg_login

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa_logada):
    casa = cg_casa_logada
    casa["db"].create_user("beatriz", "BEATRIZ COSTA", SENHA, "USER")
    return casa


def _uid(casa, login: str) -> int:
    con = sqlite3.connect(str(casa["banco"]))
    con.row_factory = sqlite3.Row
    try:
        return int(
            con.execute(
                "SELECT id FROM users WHERE username=?", (login,)
            ).fetchone()["id"]
        )
    finally:
        con.close()


def _tarefa(casa, **campos) -> int:
    jean = _uid(casa, "jean")
    dados = {
        "title": "Docs no endereco indicado",
        "sector": "Malote",
        "evidence_required": 0,
        "assigned_user_id": jean,
    }
    dados.update(campos)
    return casa["db"].create_task(dados, jean)


def test_notificar_mantem_comigo_e_lista_pediram_resposta(casa):
    jean, lei = _uid(casa, "jean"), _uid(casa, "beatriz")
    tid = _tarefa(casa, assigned_user_id=jean)
    texto = (
        "Nao achamos os docs referidos; preciso entender por que nao aparecem "
        "no endereco indicado."
    )
    html = casa["cliente"].get(f"/tarefas/{tid}").get_data(as_text=True)
    assert "Notificar para andamento ou resposta" in html
    casa["cliente"].post(
        f"/tarefas/{tid}",
        data={
            "action": "note",
            "note": texto,
            "notificar_user_id": str(lei),
            "para_user_id": "",
            "csrf_token": _token(html),
        },
        follow_redirects=True,
    )
    con = sqlite3.connect(str(casa["banco"]))
    con.row_factory = sqlite3.Row
    try:
        assert (
            con.execute(
                "SELECT assigned_user_id FROM tasks WHERE id=?", (tid,)
            ).fetchone()["assigned_user_id"]
            == jean
        )
        assert TP.contagem_por_vista(con, jean)[TP.VISTA_COMIGO] == 1
        assert TP.contagem_por_vista(con, lei)[TP.VISTA_PEDIRAM_RESPOSTA] == 1
        notif = con.execute(
            "SELECT old_value, new_value, note FROM task_history "
            "WHERE task_id=? AND action='NOTIFICACAO'",
            (tid,),
        ).fetchone()
        assert notif["old_value"] == "BEATRIZ COSTA"
        assert notif["new_value"] == str(lei)
        assert notif["note"] == texto
    finally:
        con.close()


def test_mencao_no_texto_notifica_sem_select(casa):
    jean, lei = _uid(casa, "jean"), _uid(casa, "beatriz")
    tid = _tarefa(casa, assigned_user_id=jean)
    texto = (
        "@beatriz, pode confirmar se os arquivos foram enviados ao endereco?"
    )
    html = casa["cliente"].get(f"/tarefas/{tid}").get_data(as_text=True)
    casa["cliente"].post(
        f"/tarefas/{tid}",
        data={
            "action": "note",
            "note": texto,
            "csrf_token": _token(html),
        },
        follow_redirects=True,
    )
    con = sqlite3.connect(str(casa["banco"]))
    try:
        assert con.execute(
            "SELECT 1 FROM task_history WHERE task_id=? AND action='NOTIFICACAO'"
            " AND new_value=?",
            (tid, str(lei)),
        ).fetchone()
        assert TP.contagem_por_vista(con, lei)[TP.VISTA_PEDIRAM_RESPOSTA] == 1
    finally:
        con.close()


def test_resposta_da_notificada_tira_da_vista(casa):
    jean, lei = _uid(casa, "jean"), _uid(casa, "beatriz")
    tid = _tarefa(casa, assigned_user_id=jean)
    html = casa["cliente"].get(f"/tarefas/{tid}").get_data(as_text=True)
    casa["cliente"].post(
        f"/tarefas/{tid}",
        data={
            "action": "note",
            "note": "Beatriz, favor verificar pasta compartilhada.",
            "notificar_user_id": str(lei),
            "csrf_token": _token(html),
        },
        follow_redirects=True,
    )
    con = sqlite3.connect(str(casa["banco"]))
    try:
        assert TP.contagem_por_vista(con, lei)[TP.VISTA_PEDIRAM_RESPOSTA] == 1
    finally:
        con.close()

    cg_login(casa["cliente"], "beatriz", SENHA)
    html2 = casa["cliente"].get(f"/tarefas/{tid}").get_data(as_text=True)
    casa["cliente"].post(
        f"/tarefas/{tid}",
        data={
            "action": "note",
            "note": "Os docs estavam na subpasta errada; ja indiquei o caminho.",
            "csrf_token": _token(html2),
        },
        follow_redirects=True,
    )
    con = sqlite3.connect(str(casa["banco"]))
    try:
        assert TP.contagem_por_vista(con, lei)[TP.VISTA_PEDIRAM_RESPOSTA] == 0
    finally:
        con.close()
