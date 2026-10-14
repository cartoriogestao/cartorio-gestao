"""Relato #107 - andamento na tarefa #110 sem passagem deixa o responsavel em debito."""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import tarefa_processo as TP

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
        return int(con.execute("SELECT id FROM users WHERE username=?",
                               (login,)).fetchone()["id"])
    finally:
        con.close()


def _tarefa(casa, criada_por: int | None = None, **campos) -> int:
    jean = _uid(casa, "jean")
    dados = {"title": "Encaminhar malote", "sector": "Malote",
             "evidence_required": 0, "assigned_user_id": jean}
    dados.update(campos)
    return casa["db"].create_task(dados, criada_por or jean)


def test_andamento_com_passagem_pela_lista_tira_de_comigo(casa):
    jean, lei = _uid(casa, "jean"), _uid(casa, "beatriz")
    tid = _tarefa(casa, jean, assigned_user_id=jean)
    html = casa["cliente"].get(f"/tarefas/{tid}").get_data(as_text=True)
    assert "Passar a responsabilidade para" in html
    texto = "Beatriz, dar os demais encaminhamentos desta semana."
    casa["cliente"].post(
        f"/tarefas/{tid}",
        data={"action": "note", "note": texto, "para_user_id": str(lei),
              "csrf_token": _token(html)},
        follow_redirects=True)
    con = sqlite3.connect(str(casa["banco"]))
    con.row_factory = sqlite3.Row
    try:
        linha = con.execute("SELECT assigned_user_id FROM tasks WHERE id=?",
                            (tid,)).fetchone()
        assert linha["assigned_user_id"] == lei
        comigo = TP.contagem_por_vista(con, jean)[TP.VISTA_COMIGO]
        assert comigo == 0
    finally:
        con.close()
    ficha = casa["cliente"].get(f"/tarefas/{tid}").get_data(as_text=True)
    assert "Passou para outro respons" in ficha
    assert texto in ficha


def test_andamento_sem_passagem_mantem_comigo(casa):
    jean = _uid(casa, "jean")
    tid = _tarefa(casa, assigned_user_id=jean)
    html = casa["cliente"].get(f"/tarefas/{tid}").get_data(as_text=True)
    casa["cliente"].post(
        f"/tarefas/{tid}",
        data={"action": "note", "note": "Aguardando retorno do setor.",
              "para_user_id": "", "csrf_token": _token(html)},
        follow_redirects=True)
    con = sqlite3.connect(str(casa["banco"]))
    con.row_factory = sqlite3.Row
    try:
        assert con.execute("SELECT assigned_user_id FROM tasks WHERE id=?",
                           (tid,)).fetchone()["assigned_user_id"] == jean
        assert TP.contagem_por_vista(con, jean)[TP.VISTA_COMIGO] == 1
    finally:
        con.close()


def test_atalho_registrar_e_passar_ao_substituto(casa):
    jean, lei = _uid(casa, "jean"), _uid(casa, "beatriz")
    tid = _tarefa(casa, assigned_user_id=jean, backup_user_id=lei)
    html = casa["cliente"].get(f"/tarefas/{tid}").get_data(as_text=True)
    assert "Registrar e passar ao substituto" in html
    casa["cliente"].post(
        f"/tarefas/{tid}",
        data={"action": "note",
              "note": "Substituta, continuar os encaminhamentos pendentes.",
              "passar_destino": "substituto",
              "csrf_token": _token(html)},
        follow_redirects=True)
    con = sqlite3.connect(str(casa["banco"]))
    try:
        assert con.execute("SELECT assigned_user_id FROM tasks WHERE id=?",
                           (tid,)).fetchone()[0] == lei
    finally:
        con.close()
