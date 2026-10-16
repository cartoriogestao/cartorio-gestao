"""Relato #109 — andamento (resposta) limpo quando a passagem falha."""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa_logada):
    casa = cg_casa_logada
    casa["db"].create_user("gisele", "GISELE SOUZA LIMA", SENHA, "USER")
    return casa


def _uid(casa, login: str) -> int:
    con = sqlite3.connect(str(casa["banco"]))
    con.row_factory = sqlite3.Row
    try:
        return int(con.execute(
            "SELECT id FROM users WHERE username=?", (login,)
        ).fetchone()["id"])
    finally:
        con.close()


def _tarefa(casa, **campos) -> int:
    mario = _uid(casa, "mario")
    dados = {
        "title": "Tramitar resposta",
        "sector": "Malote",
        "evidence_required": 0,
        "assigned_user_id": None,
    }
    dados.update(campos)
    return casa["db"].create_task(dados, mario)


def test_passagem_falha_grava_nota_limpa(casa):
    """Sem responsavel, passagem recusa — o texto do andamento fica so na NOTA."""
    mario, gisele = _uid(casa, "mario"), _uid(casa, "gisele")
    tid = _tarefa(casa)
    resposta = "Resposta do setor: documentos conferidos."
    html = casa["cliente"].get(f"/tarefas/{tid}").get_data(as_text=True)
    r = casa["cliente"].post(
        f"/tarefas/{tid}",
        data={
            "action": "note",
            "note": resposta,
            "para_user_id": str(gisele),
            "csrf_token": _token(html),
        },
        follow_redirects=True,
    )
    pagina = r.get_data(as_text=True)
    assert resposta in pagina
    assert "passagem nao foi feita" in pagina.lower() or "passagem não foi feita" in pagina.lower()
    con = sqlite3.connect(str(casa["banco"]))
    con.row_factory = sqlite3.Row
    try:
        notas = con.execute(
            "SELECT note FROM task_history WHERE task_id=? AND action='NOTA'",
            (tid,),
        ).fetchall()
        assert len(notas) == 1
        assert notas[0]["note"] == resposta
        assert "passagem" not in notas[0]["note"].lower()
        assert "responsavel" not in notas[0]["note"].lower()
        assert con.execute(
            "SELECT assigned_user_id FROM tasks WHERE id=?", (tid,)
        ).fetchone()[0] is None
        assert not con.execute(
            "SELECT 1 FROM task_history WHERE task_id=? AND action='PASSAGEM'",
            (tid,),
        ).fetchone()
    finally:
        con.close()
