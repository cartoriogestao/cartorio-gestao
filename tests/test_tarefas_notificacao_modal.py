# -*- coding: utf-8 -*-
"""Modal e faixa compacta de tarefas pendentes (avisos v2, sandbox)."""
from __future__ import annotations

import re

import pytest

import nu_avisos_gestao as NAV
from conftest import cg_login

SENHA = "Senha#12345"


def _csrf(html: str) -> str:
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert m, "csrf ausente"
    return m.group(1)


def _limpar_avisos(banco: str) -> None:
    import sqlite3

    with sqlite3.connect(banco) as con:
        con.execute("DELETE FROM nu_aviso_dispensa")
        con.execute("DELETE FROM nu_avisos")
        con.commit()


@pytest.fixture()
def sandbox_avisos(cg_casa):
    import sqlite3

    monkey = pytest.MonkeyPatch()
    monkey.setenv("NU_AVISOS_MODAL_SUPRIMIR", "1")
    _limpar_avisos(str(cg_casa["banco"]))
    monkey.setattr(NAV, "banco_e_sandbox", lambda _con: True)
    cg_casa["db"].create_user("tuser", "T User", SENHA, "USER")
    con = sqlite3.connect(str(cg_casa["banco"]))
    uid = int(con.execute("SELECT id FROM users WHERE username='tuser'").fetchone()[0])
    con.close()
    cg_login(cg_casa["cliente"], "tuser", SENHA)
    yield cg_casa, uid
    monkey.undo()


def _overlay_html(html: str) -> str:
    start = html.find("data-nu-avisos-overlay")
    assert start >= 0, "overlay ausente"
    end = html.find("</div>", html.find("nu-avisos-modal", start))
    end = html.find("</div>", end + 6)
    return html[start:end]




def test_modal_só_tarefas_contagem_sem_titulos(sandbox_avisos):
    casa, uid = sandbox_avisos
    tid = casa["db"].create_task(
        {"title": "Titulo secreto no modal", "assigned_user_id": uid, "sector": "Geral"},
        uid,
    )
    assert tid
    html = casa["cliente"].get("/").get_data(as_text=True)
    assert "data-nu-avisos-overlay" in html
    assert "Você possui 1 tarefa:" in html
    assert 'class="badge media">1 Média</span>' in html
    assert "Ver tarefas" in html
    assert "Titulo secreto no modal" not in _overlay_html(html)


def test_faixa_no_dom_oculta_enquanto_modal(sandbox_avisos):
    casa, uid = sandbox_avisos
    casa["db"].create_task(
        {"title": "Oculta", "assigned_user_id": uid, "sector": "Geral"},
        uid,
    )
    html = casa["cliente"].get("/").get_data(as_text=True)
    assert "data-nu-avisos-overlay" in html
    assert "flash-compact-tarefas" in html
    assert re.search(r"data-main-compact-banners[^>]*\shidden", html)


def test_faixa_apos_fechar_modal(sandbox_avisos):
    casa, uid = sandbox_avisos
    casa["db"].create_task(
        {"title": "Outra", "assigned_user_id": uid, "sector": "Geral"},
        uid,
    )
    h1 = casa["cliente"].get("/").get_data(as_text=True)
    casa["cliente"].post(
        "/avisos/fechar-modal",
        data={"csrf_token": _csrf(h1), "next": "/"},
        follow_redirects=True,
    )
    h2 = casa["cliente"].get("/").get_data(as_text=True)
    assert "data-nu-avisos-overlay" not in h2
    assert "flash-compact-tarefas" in h2
    assert "Você possui 1 tarefa:" in h2
    assert 'class="badge media">1 Média</span>' in h2
    assert "Ver tarefas" in h2


def test_sem_faixa_quando_zero(sandbox_avisos):
    casa, _uid = sandbox_avisos
    h = casa["cliente"].get("/").get_data(as_text=True)
    assert "flash-compact-tarefas" not in h


def test_admin_sem_responsavel_bloco_separado(cg_casa):
    import sqlite3

    monkey = pytest.MonkeyPatch()
    monkey.setenv("NU_AVISOS_MODAL_SUPRIMIR", "1")
    _limpar_avisos(str(cg_casa["banco"]))
    monkey.setattr(NAV, "banco_e_sandbox", lambda _con: True)
    cg_casa["db"].create_user("adm", "Admin T", SENHA, "ADMIN")
    cg_login(cg_casa["cliente"], "adm", SENHA)
    cg_casa["db"].create_task(
        {"title": "Sem dono", "assigned_user_id": None, "sector": "Geral"},
        1,
    )
    html = cg_casa["cliente"].get("/").get_data(as_text=True)
    ov = _overlay_html(html)
    assert "sem responsável" in ov.lower() or "sem responsavel" in ov.lower()
    assert "nu-tarefas-modal-sem-responsavel" in ov
    assert "nu-tarefas-modal-media-baixa" in ov
    assert "Ver tarefas" in ov
    assert "Sem dono" not in ov
    monkey.undo()

def test_tarefa_vencida_tier_critico(sandbox_avisos):
    casa, uid = sandbox_avisos
    from datetime import date, timedelta

    casa["db"].create_task(
        {
            "title": "Vencida media",
            "assigned_user_id": uid,
            "sector": "Geral",
            "priority": "MEDIA",
            "due_date": (date.today() - timedelta(days=1)).isoformat(),
        },
        uid,
    )
    html = casa["cliente"].get("/").get_data(as_text=True)
    assert "crítica ou com prazo vencido" in html.lower() or "critica ou com prazo vencido" in html.lower()
    assert 'class="badge media">MEDIA</span>' not in _overlay_html(html)


def test_tarefa_alta_tier_importante(sandbox_avisos):
    casa, uid = sandbox_avisos
    casa["db"].create_task(
        {"title": "Alta", "assigned_user_id": uid, "sector": "Geral", "priority": "ALTA"},
        uid,
    )
    html = casa["cliente"].get("/").get_data(as_text=True)
    ov = _overlay_html(html)
    assert "nu-avisos-bloco-importante" in ov
    assert "Você possui 1 tarefa:" in ov
    assert 'class="badge alta">1 Alta</span>' in ov
    assert "prioridade ALTA" not in ov
    assert ">Alta</a>" not in ov
