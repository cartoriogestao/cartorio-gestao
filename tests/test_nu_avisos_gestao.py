# -*- coding: utf-8 -*-
"""Modulo de avisos — CRUD ADMIN, dispensa diaria, contagem N, modo teste."""
from __future__ import annotations

import re
import sqlite3
from datetime import date, timedelta

import nu_avisos_gestao as NAV
from bd_nativo import banco as _banco_lx17
from tests.conftest import cg_login

SENHA = "Senha#12345"


def _csrf(html: str) -> str:
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert m, "csrf na pagina"
    return m.group(1)


def _limpar_avisos(banco: str) -> None:
    with sqlite3.connect(banco) as con:
        con.execute("DELETE FROM nu_aviso_dispensa")
        con.execute("DELETE FROM nu_avisos")
        con.commit()


def test_admin_crud_aviso(cg_casa):
    db = cg_casa["db"]
    db.create_user("admin1", "Admin", SENHA, "ADMIN")
    c = cg_casa["c"]
    cg_login(c, "admin1", SENHA)

    html = c.get("/admin/avisos/novo").get_data(as_text=True)
    assert "Importante" in html
    assert "Prioridade" not in html
    r = c.post(
        "/admin/avisos/novo",
        data={
            "csrf_token": _csrf(html),
            "titulo": "Teste pytest",
            "corpo": "Corpo do aviso de teste.",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "Teste pytest" in r.get_data(as_text=True)

    with sqlite3.connect(cg_casa["banco"]) as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT id, prioridade FROM nu_avisos WHERE titulo=?", ("Teste pytest",)
        ).fetchone()
        assert row
        assert int(row["prioridade"]) == 0
        aid = int(row["id"])

    html_imp = c.get("/admin/avisos/novo").get_data(as_text=True)
    r_imp = c.post(
        "/admin/avisos/novo",
        data={
            "csrf_token": _csrf(html_imp),
            "titulo": "Teste importante",
            "corpo": "Corpo importante.",
            "importante": "1",
        },
        follow_redirects=True,
    )
    assert r_imp.status_code == 200
    with sqlite3.connect(cg_casa["banco"]) as con:
        row_imp = con.execute(
            "SELECT prioridade FROM nu_avisos WHERE titulo=?", ("Teste importante",)
        ).fetchone()
        assert row_imp and int(row_imp[0]) == 1
    assert "Importante" in r_imp.get_data(as_text=True)

    det = c.get(f"/avisos/{aid}").get_data(as_text=True)
    assert "Corpo do aviso de teste." in det

    edit = c.get(f"/admin/avisos/{aid}/editar").get_data(as_text=True)
    r2 = c.post(
        f"/admin/avisos/{aid}/editar",
        data={
            "csrf_token": _csrf(edit),
            "titulo": "Teste pytest editado",
            "corpo": "Novo corpo.",
        },
        follow_redirects=True,
    )
    assert "Teste pytest editado" in r2.get_data(as_text=True)

    lista = c.get("/avisos").get_data(as_text=True)
    r3 = c.post(
        f"/admin/avisos/{aid}/remover",
        data={"csrf_token": _csrf(lista)},
        follow_redirects=True,
    )
    assert r3.status_code == 200
    with sqlite3.connect(cg_casa["banco"]) as con:
        row = con.execute("SELECT id FROM nu_avisos WHERE id=?", (aid,)).fetchone()
        assert row is None


def test_user_nao_acessa_admin(cg_casa):
    db = cg_casa["db"]
    db.create_user("balcao", "Balcao", SENHA, "USER")
    c = cg_casa["c"]
    cg_login(c, "balcao", SENHA)
    assert c.get("/admin/avisos").status_code == 403


def test_dispensa_dia_e_contagem_n(cg_casa, monkeypatch):
    monkeypatch.delenv("NU_AVISOS_MODAL_SEMPRE", raising=False)
    _limpar_avisos(cg_casa["banco"])
    db = cg_casa["db"]
    db.create_user("u1", "User Um", SENHA, "USER")
    agora = db.now()
    with sqlite3.connect(cg_casa["banco"]) as con:
        con.row_factory = sqlite3.Row
        a1 = NAV.criar(
            con,
            titulo="A1",
            corpo="Um",
            ativo=True,
            prioridade=1,
            vigencia_inicio=None,
            vigencia_fim=None,
            agora=agora,
            criado_por="teste",
        )
        a2 = NAV.criar(
            con,
            titulo="A2",
            corpo="Dois",
            ativo=True,
            prioridade=0,
            vigencia_inicio=None,
            vigencia_fim=None,
            agora=agora,
            criado_por="teste",
        )
        con.commit()
        uid = con.execute(
            "SELECT id FROM users WHERE username=?", ("u1",)
        ).fetchone()[0]
        assert NAV.contar_pendentes(con, uid) == 2

    c = cg_casa["c"]
    cg_login(c, "u1", SENHA)
    home = c.get("/").get_data(as_text=True)
    assert "Pendências" in home
    assert "data-nu-avisos-overlay" in home
    assert "Dois" not in home

    csrf = _csrf(home)
    c.post(
        f"/avisos/{a2}/dispensar",
        data={"csrf_token": csrf, "next": "/"},
        follow_redirects=True,
    )
    home2 = c.get("/").get_data(as_text=True)
    assert "topbar-avisos-badge" not in home2
    assert "data-nu-avisos-overlay" in home2
    assert "A1" in home2
    with sqlite3.connect(cg_casa["banco"]) as con:
        con.row_factory = sqlite3.Row
        assert NAV.contar_pendentes(con, uid) == 1
    r_bad = c.post(
        f"/avisos/{a1}/dispensar",
        data={"csrf_token": _csrf(home2), "next": "/"},
        follow_redirects=True,
    )
    assert "encerrado por ADMIN" in r_bad.get_data(as_text=True)
    with sqlite3.connect(cg_casa["banco"]) as con:
        assert NAV.contar_pendentes(con, uid) == 1


def test_modal_nao_repete_mesmo_dia_apos_dispensar(cg_casa, monkeypatch):
    monkeypatch.setenv("NU_AVISOS_MODAL_SEMPRE", "0")
    _limpar_avisos(cg_casa["banco"])
    db = cg_casa["db"]
    db.create_user("u2", "User Dois", SENHA, "USER")
    agora = db.now()
    with sqlite3.connect(cg_casa["banco"]) as con:
        aid = NAV.criar(
            con,
            titulo="Unico",
            corpo="So hoje",
            ativo=True,
            prioridade=0,
            vigencia_inicio=None,
            vigencia_fim=None,
            agora=agora,
            criado_por="teste",
        )
        con.commit()
    c = cg_casa["c"]
    cg_login(c, "u2", SENHA)
    h1 = c.get("/").get_data(as_text=True)
    assert "Unico" in h1
    c.post(
        f"/avisos/{aid}/dispensar",
        data={"csrf_token": _csrf(h1), "next": "/"},
        follow_redirects=True,
    )
    h2 = c.get("/").get_data(as_text=True)
    assert "data-nu-avisos-overlay" not in h2
    assert "topbar-avisos-badge" not in h2


def test_modal_modo_teste_reaparece_apos_novo_login(cg_casa, monkeypatch):
    monkeypatch.setenv("NU_AVISOS_MODAL_SEMPRE", "1")
    _limpar_avisos(cg_casa["banco"])
    db = cg_casa["db"]
    db.create_user("u3", "User Tres", SENHA, "USER")
    agora = db.now()
    with sqlite3.connect(cg_casa["banco"]) as con:
        aid = NAV.criar(
            con,
            titulo="Repete login",
            corpo="Corpo longo",
            ativo=True,
            prioridade=0,
            vigencia_inicio=None,
            vigencia_fim=None,
            agora=agora,
            criado_por="teste",
        )
        con.commit()

    c = cg_casa["c"]
    cg_login(c, "u3", SENHA)
    h1 = c.get("/").get_data(as_text=True)
    assert "data-nu-avisos-overlay" in h1
    c.post(
        f"/avisos/{aid}/dispensar",
        data={"csrf_token": _csrf(h1), "next": "/"},
        follow_redirects=True,
    )
    assert "data-nu-avisos-overlay" not in c.get("/").get_data(as_text=True)

    page = c.get("/").get_data(as_text=True)
    c.post("/logout", data={"csrf_token": _csrf(page)}, follow_redirects=True)
    cg_login(c, "u3", SENHA)
    h3 = c.get("/").get_data(as_text=True)
    assert "data-nu-avisos-overlay" in h3


def test_modal_js_fecha_overlay_em_link_lista():
    from pathlib import Path

    js = Path(__file__).resolve().parents[1].joinpath("static", "nu_avisos_modal.js").read_text(
        encoding="utf-8"
    )
    assert "fecharModal" in js
    assert "exibirFaixasCompactas" in js
    assert "persistirOverlayFechado" in js
    assert "requestSubmit" in js
    assert "data-nu-avisos-fechar" in js
    assert "data-main-compact-banners" in js

def test_modal_nao_na_pagina_lista(cg_casa, monkeypatch):
    monkeypatch.delenv('NU_AVISOS_MODAL_SEMPRE', raising=False)
    _limpar_avisos(cg_casa['banco'])
    db = cg_casa['db']
    db.create_user('ul', 'User Lista', SENHA, 'USER')
    agora = db.now()
    with sqlite3.connect(cg_casa['banco']) as con:
        NAV.criar(
            con,
            titulo='Na lista',
            corpo='Corpo',
            ativo=True,
            prioridade=1,
            vigencia_inicio=None,
            vigencia_fim=None,
            agora=agora,
            criado_por='teste',
        )
        con.commit()
    c = cg_casa['c']
    cg_login(c, 'ul', SENHA)
    home = c.get('/').get_data(as_text=True)
    assert 'data-nu-avisos-overlay' in home
    lista = c.get('/avisos').get_data(as_text=True)
    assert 'data-nu-avisos-overlay' not in lista
    assert 'nu-avisos-link-lista' not in lista

def test_modal_x_fecha_dispensa_overlay_e_banner(cg_casa, monkeypatch):
    monkeypatch.setenv("NU_AVISOS_MODAL_SEMPRE", "1")
    monkeypatch.setattr(NAV, "banco_e_sandbox", lambda _con: True)
    _limpar_avisos(cg_casa["banco"])
    db = cg_casa["db"]
    db.create_user("ux1", "User UX", SENHA, "USER")
    agora = db.now()
    with sqlite3.connect(cg_casa["banco"]) as con:
        NAV.criar(
            con,
            titulo="Banner A",
            corpo="Corpo A",
            ativo=True,
            prioridade=1,
            vigencia_inicio=None,
            vigencia_fim=None,
            agora=agora,
            criado_por="teste",
        )
        NAV.criar(
            con,
            titulo="Banner B",
            corpo="Corpo B",
            ativo=True,
            prioridade=2,
            vigencia_inicio=None,
            vigencia_fim=None,
            agora=agora,
            criado_por="teste",
        )
        con.commit()
    c = cg_casa["c"]
    cg_login(c, "ux1", SENHA)
    h1 = c.get("/").get_data(as_text=True)
    assert "data-nu-avisos-overlay" in h1
    assert "nu-avisos-modal-fechar" in h1
    assert "nu-avisos-icone-importante" in h1
    assert 'badge-danger">Importante</span>' not in h1
    assert "Li / Dispensar" not in h1
    r = c.post(
        "/avisos/fechar-modal",
        data={"csrf_token": _csrf(h1), "next": "/"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    h2 = c.get("/").get_data(as_text=True)
    assert "data-nu-avisos-overlay" not in h2
    assert "flash-compact-aviso-critico" in h2
    assert "Banner B" in h2
    assert "1 aviso(s) importante(s)" in h2
    assert "Banner A" in h2
    assert 'class="nu-avisos-link-lista">Ver todos</a>' in h2
    h3 = c.get("/").get_data(as_text=True)
    assert "data-nu-avisos-overlay" not in h3


def test_modal_x_modo_teste_nao_reabre_ate_novo_login(cg_casa, monkeypatch):
    monkeypatch.setenv("NU_AVISOS_MODAL_SEMPRE", "1")
    monkeypatch.setattr(NAV, "banco_e_sandbox", lambda _con: True)
    _limpar_avisos(cg_casa["banco"])
    db = cg_casa["db"]
    db.create_user("ux2", "User UX2", SENHA, "USER")
    agora = db.now()
    with sqlite3.connect(cg_casa["banco"]) as con:
        aid = NAV.criar(
            con,
            titulo="Sessao",
            corpo="Corpo",
            ativo=True,
            prioridade=0,
            vigencia_inicio=None,
            vigencia_fim=None,
            agora=agora,
            criado_por="teste",
        )
        con.commit()
    c = cg_casa["c"]
    cg_login(c, "ux2", SENHA)
    h1 = c.get("/").get_data(as_text=True)
    c.post(
        "/avisos/fechar-modal",
        data={"csrf_token": _csrf(h1), "next": "/"},
        follow_redirects=True,
    )
    assert "data-nu-avisos-overlay" not in c.get("/").get_data(as_text=True)
    page = c.get("/").get_data(as_text=True)
    c.post("/logout", data={"csrf_token": _csrf(page)}, follow_redirects=True)
    cg_login(c, "ux2", SENHA)
    assert "data-nu-avisos-overlay" in c.get("/").get_data(as_text=True)

def test_admin_lista_unificada_em_avisos(cg_casa):
    db = cg_casa["db"]
    db.create_user("admin2", "Admin Dois", SENHA := "Senha#12345", "ADMIN")
    c = cg_casa["c"]
    cg_login(c, "admin2", SENHA)
    with sqlite3.connect(cg_casa["banco"]) as con:
        con.row_factory = sqlite3.Row
        aid = NAV.criar(
            con,
            titulo="Unificado",
            corpo="Corpo",
            ativo=True,
            prioridade=0,
            vigencia_inicio=None,
            vigencia_fim=None,
            agora=db.now(),
            criado_por="admin2",
        )
        con.commit()
    lista = c.get("/avisos").get_data(as_text=True)
    assert "Novo aviso" in lista
    assert 'aria-label="Editar"' in lista
    assert "aviso-admin-ativo-checkbox" in lista
    assert "Desativar" not in lista
    assert "Unificado" in lista
    r = c.get("/admin/avisos", follow_redirects=True)
    assert r.status_code == 200
    assert r.request.path == "/avisos" or "/avisos" in (r.request.url or "")


def test_desativar_e_ativar_aviso(cg_casa):
    db = cg_casa["db"]
    db.create_user("admin3", "Admin Tres", SENHA := "Senha#12345", "ADMIN")
    c = cg_casa["c"]
    cg_login(c, "admin3", SENHA)
    html = c.get("/admin/avisos/novo").get_data(as_text=True)
    r = c.post(
        "/admin/avisos/novo",
        data={
            "csrf_token": _csrf(html),
            "titulo": "Toggle ativo",
            "corpo": "Teste toggle.",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    with sqlite3.connect(cg_casa["banco"]) as con:
        row = con.execute(
            "SELECT id, ativo FROM nu_avisos WHERE titulo=?", ("Toggle ativo",)
        ).fetchone()
        assert row is not None
        aid = int(row[0])
        assert int(row[1]) == 1
    lista = c.get("/avisos").get_data(as_text=True)
    r_off = c.post(
        f"/admin/avisos/{aid}/desativar",
        data={"csrf_token": _csrf(lista)},
        follow_redirects=True,
    )
    assert r_off.status_code == 200
    assert "Aviso desativado" in r_off.get_data(as_text=True)
    with sqlite3.connect(cg_casa["banco"]) as con:
        assert int(con.execute("SELECT ativo FROM nu_avisos WHERE id=?", (aid,)).fetchone()[0]) == 0
    lista2 = c.get("/avisos").get_data(as_text=True)
    assert "aviso-admin-ativo-checkbox" in lista2
    assert "Desativar" not in lista2
    r_on = c.post(
        f"/admin/avisos/{aid}/desativar",
        data={"csrf_token": _csrf(lista2)},
        follow_redirects=True,
    )
    assert r_on.status_code == 200
    assert "Aviso ativado" in r_on.get_data(as_text=True)
    with sqlite3.connect(cg_casa["banco"]) as con:
        assert int(con.execute("SELECT ativo FROM nu_avisos WHERE id=?", (aid,)).fetchone()[0]) == 1


def test_faixas_vermelha_verde_separadas(cg_casa, monkeypatch):
    monkeypatch.setenv("NU_AVISOS_MODAL_SEMPRE", "1")
    monkeypatch.setattr(NAV, "banco_e_sandbox", lambda _con: True)
    _limpar_avisos(cg_casa["banco"])
    db = cg_casa["db"]
    db.create_user("mix1", "User Mix", SENHA, "USER")
    agora = db.now()
    with sqlite3.connect(cg_casa["banco"]) as con:
        NAV.criar(
            con,
            titulo="Imp",
            corpo="C",
            ativo=True,
            prioridade=1,
            vigencia_inicio=None,
            vigencia_fim=None,
            agora=agora,
            criado_por="t",
        )
        NAV.criar(
            con,
            titulo="Norm",
            corpo="C",
            ativo=True,
            prioridade=0,
            vigencia_inicio=None,
            vigencia_fim=None,
            agora=agora,
            criado_por="t",
        )
        con.commit()
    c = cg_casa["c"]
    cg_login(c, "mix1", SENHA)
    h1 = c.get("/").get_data(as_text=True)
    c.post(
        "/avisos/fechar-modal",
        data={"csrf_token": _csrf(h1), "next": "/"},
        follow_redirects=True,
    )
    h2 = c.get("/").get_data(as_text=True)
    assert "1 aviso(s) importante(s)" in h2
    assert "1 aviso(s)" in h2
    assert "flash-compact-aviso-importante" in h2
    assert "flash-compact-aviso-normal" in h2
    assert 'id="aviso-avisos-normais-detalhe"' in h2
    assert "Imp" in h2
    assert 'class="nu-avisos-faixa-aviso-titulo"' in h2
    assert 'class="nu-avisos-link-lista">Ver todos</a>' in h2
    idx_v = h2.find("flash-compact-aviso-normal")
    idx_g = h2.find("Ver todos", idx_v if idx_v >= 0 else 0)
    assert idx_v == -1 or idx_g == -1 or idx_g < idx_v


def test_user_nao_dispensa_importante(cg_casa, monkeypatch):
    monkeypatch.setenv("NU_AVISOS_MODAL_SEMPRE", "0")
    _limpar_avisos(cg_casa["banco"])
    db = cg_casa["db"]
    db.create_user("uimp", "User Imp", SENHA, "USER")
    agora = db.now()
    with sqlite3.connect(cg_casa["banco"]) as con:
        aid = NAV.criar(
            con,
            titulo="Só imp",
            corpo="C",
            ativo=True,
            prioridade=1,
            vigencia_inicio=None,
            vigencia_fim=None,
            agora=agora,
            criado_por="t",
        )
        con.commit()
    c = cg_casa["c"]
    cg_login(c, "uimp", SENHA)
    lista = c.get("/avisos").get_data(as_text=True)
    assert "Dispensar hoje" not in lista
    r = c.post(
        f"/avisos/{aid}/dispensar",
        data={"csrf_token": _csrf(lista), "next": "/avisos"},
        follow_redirects=True,
    )
    assert "encerrado por ADMIN" in r.get_data(as_text=True)


def test_recorrencia_reativa_apos_slot(cg_casa, monkeypatch):
    _limpar_avisos(cg_casa["banco"])
    agora = cg_casa["db"].now()
    with sqlite3.connect(cg_casa["banco"]) as con:
        con.row_factory = sqlite3.Row
        aid = NAV.criar(
            con,
            titulo="Rec",
            corpo="C",
            ativo=True,
            prioridade=1,
            vigencia_inicio=None,
            vigencia_fim=None,
            agora=agora,
            criado_por="t",
            recorrente=True,
            recorrencia_dia_semana=0,
            recorrencia_hora="08:00",
        )
        NAV.desativar(con, aid, agora="2026-09-22T10:00:00")
        con.commit()
    with sqlite3.connect(cg_casa["banco"]) as con:
        con.row_factory = sqlite3.Row
        n = NAV.processar_recorrencias(con, agora="2026-09-29T09:00:00")
        assert n == 1
        n2 = NAV.processar_recorrencias(con, agora="2026-09-29T09:00:00")
        assert n2 == 0
        row = con.execute("SELECT ativo FROM nu_avisos WHERE id=?", (aid,)).fetchone()
        assert int(row[0]) == 1


def test_banners_acima_do_titulo(cg_casa, monkeypatch):
    monkeypatch.setattr(NAV, "banco_e_sandbox", lambda _con: True)
    monkeypatch.setenv("NU_AVISOS_MODAL_SEMPRE", "1")
    _limpar_avisos(cg_casa["banco"])
    db = cg_casa["db"]
    db.create_user("lay1", "Lay", SENHA, "USER")
    agora = db.now()
    with sqlite3.connect(cg_casa["banco"]) as con:
        NAV.criar(
            con,
            titulo="Lay",
            corpo="C",
            ativo=True,
            prioridade=0,
            vigencia_inicio=None,
            vigencia_fim=None,
            agora=agora,
            criado_por="t",
        )
        con.commit()
    c = cg_casa["c"]
    cg_login(c, "lay1", SENHA)
    h = c.get("/avisos").get_data(as_text=True)
    pos_banner = h.find("main-compact-banners")
    pos_h1 = h.find("<h1>Avisos</h1>")
    assert pos_banner != -1 and pos_h1 != -1 and pos_banner < pos_h1

def test_recorrencia_multidia_bitmask(cg_casa, monkeypatch):
    _limpar_avisos(cg_casa["banco"])
    agora = cg_casa["db"].now()
    with sqlite3.connect(cg_casa["banco"]) as con:
        con.row_factory = sqlite3.Row
        aid = NAV.criar(
            con,
            titulo="Rec multi",
            corpo="C",
            ativo=True,
            prioridade=1,
            vigencia_inicio=None,
            vigencia_fim=None,
            agora=agora,
            criado_por="t",
            recorrente=True,
            recorrencia_dias=5,
            recorrencia_hora="08:00",
        )
        NAV.desativar(con, aid, agora="2026-09-22T10:00:00")
        con.commit()
    with sqlite3.connect(cg_casa["banco"]) as con:
        con.row_factory = sqlite3.Row
        n = NAV.processar_recorrencias(con, agora="2026-09-24T09:00:00")
        assert n == 1


def test_vigencia_fim_inativa(cg_casa):
    db = cg_casa["db"]
    agora = db.now()
    with sqlite3.connect(cg_casa["banco"]) as con:
        con.row_factory = sqlite3.Row
        NAV.criar(
            con,
            titulo="Expirado",
            corpo="C",
            ativo=True,
            prioridade=0,
            vigencia_inicio="2026-01-01",
            vigencia_fim="2026-01-02",
            agora=agora,
            criado_por="t",
        )
        con.commit()
        ativos = NAV.listar_ativos_vigentes(con, hoje="2026-09-29")
        assert not any(r["titulo"] == "Expirado" for r in ativos)


def test_admin_encerra_importante_lista_faixa_modal(cg_casa, monkeypatch):
    monkeypatch.setenv("NU_AVISOS_MODAL_SEMPRE", "1")
    monkeypatch.setattr(NAV, "banco_e_sandbox", lambda _con: True)
    _limpar_avisos(cg_casa["banco"])
    db = cg_casa["db"]
    db.create_user("adm4", "Admin Quatro", SENHA := "Senha#12345", "ADMIN")
    agora = db.now()
    with sqlite3.connect(cg_casa["banco"]) as con:
        aid = NAV.criar(
            con,
            titulo="Imp admin",
            corpo="Corpo longo",
            ativo=True,
            prioridade=1,
            vigencia_inicio=None,
            vigencia_fim=None,
            agora=agora,
            criado_por="adm4",
        )
        con.commit()
    c = cg_casa["c"]
    cg_login(c, "adm4", SENHA)
    h1 = c.get("/").get_data(as_text=True)
    assert "nu-avisos-modal-dispensar" in h1
    ov = h1[h1.find("data-nu-avisos-overlay") : h1.find("data-nu-avisos-overlay") + 12000]
    assert "nu-avisos-link-lista" not in ov
    c.post(
        "/avisos/fechar-modal",
        data={"csrf_token": _csrf(h1), "next": "/"},
        follow_redirects=True,
    )
    h2 = c.get("/").get_data(as_text=True)
    assert "dispensar-importantes-faixa" in h2 or "Dispensar importantes" in h2
    lista = c.get("/avisos").get_data(as_text=True)
    assert "Encerrar" in lista
    r = c.post(
        f"/avisos/{aid}/dispensar",
        data={"csrf_token": _csrf(lista), "next": "/avisos"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    with sqlite3.connect(cg_casa["banco"]) as con:
        assert int(con.execute("SELECT ativo FROM nu_avisos WHERE id=?", (aid,)).fetchone()[0]) == 0


def test_modal_coluna_avisos_sem_normais_copy(cg_casa, monkeypatch):
    monkeypatch.setenv("NU_AVISOS_MODAL_SEMPRE", "1")
    monkeypatch.setattr(NAV, "banco_e_sandbox", lambda _con: True)
    _limpar_avisos(cg_casa["banco"])
    db = cg_casa["db"]
    db.create_user("vaz1", "User Vazio", SENHA, "USER")
    agora = db.now()
    with sqlite3.connect(cg_casa["banco"]) as con:
        NAV.criar(
            con,
            titulo="So critico",
            corpo="Corpo",
            ativo=True,
            prioridade=2,
            vigencia_inicio=None,
            vigencia_fim=None,
            agora=agora,
            criado_por="t",
        )
        con.commit()
    c = cg_casa["c"]
    cg_login(c, "vaz1", SENHA)
    h = c.get("/").get_data(as_text=True)
    assert "nu-avisos-modal-col-avisos" in h
    assert "N\u00e3o h\u00e1 avisos" in h
    assert "Nenhum aviso normal pendente" not in h


def test_admin_encerra_critico_desativa(cg_casa, monkeypatch):
    monkeypatch.setenv("NU_AVISOS_MODAL_SEMPRE", "1")
    monkeypatch.setattr(NAV, "banco_e_sandbox", lambda _con: True)
    _limpar_avisos(cg_casa["banco"])
    db = cg_casa["db"]
    db.create_user("adm5", "Admin Cinco", SENHA, "ADMIN")
    agora = db.now()
    with sqlite3.connect(cg_casa["banco"]) as con:
        aid = NAV.criar(
            con,
            titulo="Crit admin",
            corpo="Corpo critico",
            ativo=True,
            prioridade=2,
            vigencia_inicio=None,
            vigencia_fim=None,
            agora=agora,
            criado_por="adm5",
        )
        con.commit()
    c = cg_casa["c"]
    cg_login(c, "adm5", SENHA)
    h = c.get("/").get_data(as_text=True)
    r = c.post(
        f"/avisos/{aid}/dispensar",
        data={"csrf_token": _csrf(h), "next": "/"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    with sqlite3.connect(cg_casa["banco"]) as con:
        assert int(con.execute("SELECT ativo FROM nu_avisos WHERE id=?", (aid,)).fetchone()[0]) == 0


def test_faixa_critica_tarefas_linha_dedicada(cg_casa, monkeypatch):
    monkeypatch.setenv("NU_AVISOS_MODAL_SEMPRE", "1")
    monkeypatch.setattr(NAV, "banco_e_sandbox", lambda _con: True)
    _limpar_avisos(cg_casa["banco"])
    db = cg_casa["db"]
    db.create_user("fx1", "Faixa", SENHA, "USER")
    agora = db.now()
    with sqlite3.connect(cg_casa["banco"]) as con:
        NAV.criar(
            con,
            titulo="Crit faixa",
            corpo="C",
            ativo=True,
            prioridade=2,
            vigencia_inicio=None,
            vigencia_fim=None,
            agora=agora,
            criado_por="t",
        )
        con.commit()
    c = cg_casa["c"]
    cg_login(c, "fx1", SENHA)
    c.post(
        "/avisos/fechar-modal",
        data={"csrf_token": _csrf(c.get("/").get_data(as_text=True)), "next": "/"},
        follow_redirects=True,
    )
    h = c.get("/").get_data(as_text=True)
    assert "nu-avisos-faixa-tarefas-linha-critica" in h or "flash-compact-aviso-critico" in h


# --------------------------------------------------------------------------
# LX17 — a barra fixa (pedido do oficial em 19/10/2026: «a janela de avisos
# tem sido ignorada pelos escreventes»). Nomes de pessoa aqui são inventados.
# --------------------------------------------------------------------------


def _uid(db, username: str) -> int:
    with db.connect() as con:
        return int(_banco_lx17(con).valor(
            "SELECT id FROM users WHERE username=%s", (username,)))


def _ferj(db) -> dict:
    with db.connect() as con:
        return _banco_lx17(con).um(
            "SELECT * FROM nu_avisos WHERE chave=%s", (NAV.CHAVE_FERJ,))


def _contar(db, sql: str, parametros=None) -> int:
    with db.connect() as con:
        return int(_banco_lx17(con).valor(sql, parametros))


def _barra(db, titulo: str, **extra) -> int:
    with db.transaction() as con:
        return NAV.criar(
            con, titulo=titulo, corpo="Corpo de " + titulo, ativo=True,
            prioridade=0, vigencia_inicio=None, vigencia_fim=None,
            agora=db.now(), criado_por="t", modo=NAV.MODO_BARRA, **extra)


def _entrar(cg_casa, username: str, papel: str, nome: str):
    cg_casa["db"].create_user(username, nome, SENHA, papel)
    c = cg_casa["app"].test_client()
    cg_login(c, username, SENHA)
    return c


def _so_a_barra(html: str) -> str:
    ini = html.find("data-barras-fixas")
    assert ini != -1, "a tela não trouxe a barra fixa"
    return html[ini:html.find('<header class="topbar">', ini)]


def test_a_subida_cria_a_barra_do_ferj_uma_vez_so(cg_casa):
    """«Crie-o na subida se não existir, sem duplicar» — e subir de novo não duplica.

    A subida roda em cada processo (servidor, agendador), e quem cria tem de
    ser idempotente: duas barras do FERJ seriam duas baixas por mês.
    """
    db = cg_casa["db"]
    for _ in range(2):
        with db.transaction() as con:
            NAV.init_nu_avisos_schema(con)
    assert _contar(db, "SELECT count(*) AS n FROM nu_avisos WHERE chave=%s",
                   (NAV.CHAVE_FERJ,)) == 1
    ferj = _ferj(db)
    assert ferj["modo"] == NAV.MODO_BARRA
    assert int(ferj["barra_dia_mes"]) == 1, "o padrão do pedido é o dia 1"
    assert ferj["barra_papeis"] == "ADMIN,MANAGER"
    assert int(ferj["ativo"]) == 1


def test_a_barra_do_ferj_desligada_continua_desligada_na_subida(cg_casa):
    """«Se não existir» quer dizer isso: desativada, ela existe e não renasce ligada."""
    db = cg_casa["db"]
    with db.transaction() as con:
        NAV.desativar(con, int(_ferj(db)["id"]), agora=db.now())
    with db.transaction() as con:
        NAV.init_nu_avisos_schema(con)
    assert int(_ferj(db)["ativo"]) == 0
    assert _contar(db, "SELECT count(*) AS n FROM nu_avisos WHERE chave=%s",
                   (NAV.CHAVE_FERJ,)) == 1


def test_a_barra_mensal_so_aparece_a_partir_do_dia_configurado(cg_casa):
    """Dia 10: no dia 9 não há barra; no dia 10 há, com o mês de referência.

    E o dia 31 em novembro vale o dia 30 — «a partir do dia 31» não pode
    querer dizer «nunca nos meses curtos».
    """
    db = cg_casa["db"]
    db.create_user("bm1", "Escrevente Um", SENHA, "USER")
    uid = _uid(db, "bm1")
    with db.transaction() as con:
        _banco_lx17(con).escrever(
            "UPDATE nu_avisos SET barra_dia_mes=10 WHERE chave=%s", (NAV.CHAVE_FERJ,))
    with db.connect() as con:
        assert NAV.barras_para_usuario(con, uid, hoje="2026-10-09") == []
        barras = NAV.barras_para_usuario(con, uid, hoje="2026-10-10")
    assert [b["mes_ref"] for b in barras] == ["2026-10"]
    with db.transaction() as con:
        _banco_lx17(con).escrever(
            "UPDATE nu_avisos SET barra_dia_mes=31 WHERE chave=%s", (NAV.CHAVE_FERJ,))
    with db.connect() as con:
        assert NAV.barras_para_usuario(con, uid, hoje="2026-11-29") == []
        assert len(NAV.barras_para_usuario(con, uid, hoje="2026-11-30")) == 1


def test_a_barra_esta_em_toda_tela_e_o_escrevente_nao_a_fecha(cg_casa):
    """A barra vem no topo do painel e da lista, sem X e sem «Pago» para o USER.

    É a diferença inteira para a janela: o escrevente aprendeu a fechar a
    janela sem ler. Ele vê o campo do «avisei», e só ele (a regra 2b).
    """
    c = _entrar(cg_casa, "bt1", "USER", "Escrevente Dois")
    for tela in ("/", "/avisos"):
        barra = _so_a_barra(c.get(tela).get_data(as_text=True))
        assert NAV.FERJ_TITULO in barra, f"a barra do FERJ sumiu de {tela}"
        assert "data-aviso-fechar" not in barra, "a barra fixa ganhou botão de fechar"
        assert "Pago — informar data/guia" not in barra, "o USER não marca pago"
        assert 'name="palavra"' in barra, "o campo do «avisei» sumiu"
    with cg_casa["db"].connect() as con:
        assert NAV.contar_pendentes(con, _uid(cg_casa["db"], "bt1")) == 0, (
            "a barra entrou na janela e na contagem N")


def test_o_escrevente_nao_marca_pago_e_o_admin_marca_com_registro(cg_casa):
    """«Pago» só para o papel do aviso; e a baixa fica no audit_logs: quem, quando, mês."""
    db = cg_casa["db"]
    aid = int(_ferj(db)["id"])
    usuario = _entrar(cg_casa, "bp1", "USER", "Escrevente Tres")
    html = usuario.get("/").get_data(as_text=True)
    r = usuario.post(f"/avisos/{aid}/pago", data={
        "csrf_token": _csrf(html), "next": "/", "data_pagamento": db.now()[:10],
        "guia": "123"}, follow_redirects=True).get_data(as_text=True)
    assert "marca esta barra como paga" in r
    assert _contar(db, "SELECT count(*) AS n FROM nu_aviso_baixa") == 0

    admin = _entrar(cg_casa, "bp2", "ADMIN", "Oficial Exemplo")
    html = admin.get("/").get_data(as_text=True)
    assert "Pago — informar data/guia" in _so_a_barra(html)
    r = admin.post(f"/avisos/{aid}/pago", data={
        "csrf_token": _csrf(html), "next": "/", "data_pagamento": db.now()[:10],
        "guia": "GUIA-0001"}, follow_redirects=True).get_data(as_text=True)
    mes = db.now()[:7]
    assert f"Marcado pago o mês {mes[5:7]}/{mes[:4]}" in r
    assert NAV.FERJ_TITULO not in r, "a barra continuou depois da baixa"
    assert NAV.FERJ_TITULO not in usuario.get("/").get_data(as_text=True), (
        "a baixa do ADMIN não tirou a barra do escrevente")
    with db.connect() as con:
        log = _banco_lx17(con).um(
            "SELECT * FROM audit_logs WHERE action=%s ORDER BY id DESC LIMIT 1",
            ("NU_AVISO_PAGO",))
    assert log and int(log["user_id"]) == _uid(db, "bp2")
    assert log["username_snapshot"] == "bp2" and log["ts"]
    assert int(log["entity_id"]) == aid
    assert f'"mes_referencia": "{mes}"' in log["details"]
    assert "GUIA-0001" in log["details"]


def test_quem_marca_pago_e_configuravel(cg_casa):
    """Só ADMIN marcado: o MANAGER, que podia pelo padrão, passa a ouvir não."""
    db = cg_casa["db"]
    db.create_user("bc1", "Substituto Exemplo", SENHA, "MANAGER")
    aid = int(_ferj(db)["id"])
    with db.transaction() as con:
        NAV.atualizar(con, aid, titulo=NAV.FERJ_TITULO, corpo=NAV.FERJ_CORPO,
                      ativo=True, prioridade=0, vigencia_inicio=None,
                      vigencia_fim=None, agora=db.now(), barra_papeis=["ADMIN"])
    with db.connect() as con:
        barras = NAV.barras_para_usuario(con, _uid(db, "bc1"), hoje="2026-10-19",
                                         papel="MANAGER")
    assert barras and not barras[0]["pode_marcar_pago"]
    with db.transaction() as con:
        try:
            NAV.marcar_pago(con, aid, user_id=_uid(db, "bc1"), papel="MANAGER",
                            data_pagamento="2026-10-19", guia=None,
                            agora="2026-10-19T10:00:00", hoje="2026-10-19")
        except NAV.AvisoGestaoError as erro:
            assert "Só ADMIN" in str(erro)
        else:
            raise AssertionError("o MANAGER marcou pago sem estar na lista do aviso")


def test_dois_cliques_no_pago_gravam_uma_baixa_so(cg_casa):
    """O segundo ouve quem já marcou — e o audit_logs não ganha baixa fantasma."""
    db = cg_casa["db"]
    db.create_user("bd1", "Oficial Dois", SENHA, "ADMIN")
    uid, aid = _uid(db, "bd1"), int(_ferj(db)["id"])
    argumentos = dict(user_id=uid, papel="ADMIN", data_pagamento="2026-10-15",
                      guia="G1", agora="2026-10-19T10:00:00", hoje="2026-10-19")
    with db.transaction() as con:
        assert NAV.marcar_pago(con, aid, **argumentos) == "2026-10"
    with db.transaction() as con:
        try:
            NAV.marcar_pago(con, aid, **argumentos)
        except NAV.AvisoGestaoError as erro:
            assert "já foi marcado pago por Oficial Dois" in str(erro)
        else:
            raise AssertionError("o segundo clique gravou outra baixa")
    assert _contar(db, "SELECT count(*) AS n FROM nu_aviso_baixa") == 1
    assert _contar(db, "SELECT count(*) AS n FROM audit_logs WHERE action=%s",
                   ("NU_AVISO_PAGO",)) == 1


def test_a_barra_mensal_volta_no_mes_seguinte(cg_casa):
    """Pago outubro, a barra some em outubro — e volta em 1º de novembro."""
    db = cg_casa["db"]
    db.create_user("bv1", "Oficial Tres", SENHA, "ADMIN")
    uid, aid = _uid(db, "bv1"), int(_ferj(db)["id"])
    with db.transaction() as con:
        NAV.marcar_pago(con, aid, user_id=uid, papel="ADMIN",
                        data_pagamento="2026-10-19", guia=None,
                        agora="2026-10-19T10:00:00", hoje="2026-10-19")
    with db.connect() as con:
        assert NAV.barras_para_usuario(con, uid, hoje="2026-10-31") == []
        novembro = NAV.barras_para_usuario(con, uid, hoje="2026-11-01")
    assert [b["mes_ref"] for b in novembro] == ["2026-11"]


def test_data_de_pagamento_futura_ou_vazia_e_recusada(cg_casa):
    """Baixa com data que não aconteceu é o «carimbo que mente»."""
    db = cg_casa["db"]
    db.create_user("bf1", "Oficial Quatro", SENHA, "ADMIN")
    uid, aid = _uid(db, "bf1"), int(_ferj(db)["id"])
    for data, frase in (("2026-10-20", "futura"), ("", "Informe a data")):
        with db.transaction() as con:
            try:
                NAV.marcar_pago(con, aid, user_id=uid, papel="ADMIN",
                                data_pagamento=data, guia=None,
                                agora="2026-10-19T10:00:00", hoje="2026-10-19")
            except NAV.AvisoGestaoError as erro:
                assert frase in str(erro)
            else:
                raise AssertionError(f"aceitou a data {data!r}")
    assert _contar(db, "SELECT count(*) AS n FROM nu_aviso_baixa") == 0


def test_avisei_so_vale_digitado_so_para_quem_digitou_e_so_ate_amanha(cg_casa):
    """A exceção 2b, inteira: digitar (clicar não basta), um usuário, um dia.

    E cada «avisei» fica registrado — no audit_logs e na lista do ADMIN.
    """
    db = cg_casa["db"]
    aid = int(_ferj(db)["id"])
    c = _entrar(cg_casa, "ba1", "USER", "Escrevente Quatro")
    db.create_user("ba2", "Escrevente Cinco", SENHA, "USER")
    html = c.get("/").get_data(as_text=True)
    r = c.post(f"/avisos/{aid}/avisei", data={
        "csrf_token": _csrf(html), "next": "/", "palavra": ""},
        follow_redirects=True).get_data(as_text=True)
    assert "digite a palavra «avisei»" in r
    assert NAV.FERJ_TITULO in _so_a_barra(r), "clicar sem digitar ocultou a barra"

    r = c.post(f"/avisos/{aid}/avisei", data={
        "csrf_token": _csrf(r), "next": "/", "palavra": "  Avisei "},
        follow_redirects=True).get_data(as_text=True)
    assert "Registrado o «avisei»" in r
    assert NAV.FERJ_TITULO not in r, "o «avisei» não ocultou a barra"

    hoje = db.now()[:10]
    amanha = (date.fromisoformat(hoje) + timedelta(days=1)).isoformat()
    with db.connect() as con:
        assert NAV.barras_para_usuario(con, _uid(db, "ba1"), hoje=hoje) == []
        assert NAV.barras_para_usuario(con, _uid(db, "ba2"), hoje=hoje), (
            "o «avisei» de um escrevente ocultou a barra dos outros")
        if amanha[:7] == hoje[:7]:
            assert NAV.barras_para_usuario(con, _uid(db, "ba1"), hoje=amanha), (
                "a barra não voltou no dia seguinte")
        log = _banco_lx17(con).um(
            "SELECT * FROM audit_logs WHERE action=%s ORDER BY id DESC LIMIT 1",
            ("NU_AVISO_AVISEI",))
    assert log and log["username_snapshot"] == "ba1"
    assert f'"oculto_ate": "{amanha}"' in log["details"]


def test_avisei_nao_oculta_outra_barra_fixa(cg_casa):
    """Só a do FERJ/FERC se oculta; as outras barras fixas não."""
    db = cg_casa["db"]
    db.create_user("bo1", "Escrevente Seis", SENHA, "USER")
    outra = _barra(db, "Certificado vencendo", barra_dia_mes=1)
    with db.transaction() as con:
        try:
            NAV.registrar_avisei(con, outra, user_id=_uid(db, "bo1"),
                                 palavra="avisei", agora="2026-10-19T10:00:00",
                                 hoje="2026-10-19")
        except NAV.AvisoGestaoError as erro:
            assert "Só a barra do FERJ/FERC" in str(erro)
        else:
            raise AssertionError("o «avisei» ocultou uma barra que não é a do FERJ")
    with db.connect() as con:
        barras = NAV.barras_para_usuario(con, _uid(db, "bo1"), hoje="2026-10-19")
    assert [b["aceita_avisei"] for b in barras] == [True, False]


def test_barra_fixa_nao_se_dispensa_como_janela(cg_casa):
    """O «Dispensar hoje» da janela não serve de porta dos fundos para a barra."""
    db = cg_casa["db"]
    db.create_user("bj1", "Oficial Cinco", SENHA, "ADMIN")
    with db.transaction() as con:
        try:
            NAV.dispensar(con, user_id=_uid(db, "bj1"), aviso_id=int(_ferj(db)["id"]),
                          agora="2026-10-19T10:00:00", papel="ADMIN")
        except NAV.AvisoGestaoError as erro:
            assert "barra fixa não se dispensa" in str(erro)
        else:
            raise AssertionError("a barra fixa foi dispensada como janela")


def test_o_auditor_nao_grava_baixa_nem_avisei(cg_casa):
    """AUDITOR confere e não pratica ato — as duas rotas novas o barram."""
    aid = int(_ferj(cg_casa["db"])["id"])
    c = _entrar(cg_casa, "bx1", "AUDITOR", "Auditor Exemplo")
    html = c.get("/").get_data(as_text=True)
    for acao in ("pago", "avisei"):
        r = c.post(f"/avisos/{aid}/{acao}", data={
            "csrf_token": _csrf(html), "palavra": "avisei",
            "data_pagamento": "2026-10-01"})
        assert r.status_code == 403, f"o AUDITOR gravou em /{acao}"


def test_varias_barras_empilham_duas_e_o_resto_vira_mais_n(cg_casa):
    """FERJ + três: duas à vista, «+2» guardando as outras duas."""
    db = cg_casa["db"]
    for titulo in ("Barra B", "Barra C", "Barra D"):
        _barra(db, titulo)
    c = _entrar(cg_casa, "be1", "USER", "Escrevente Sete")
    barra = _so_a_barra(c.get("/").get_data(as_text=True))
    mais = barra.find('class="barras-fixas-mais"')
    assert mais != -1 and "<summary>+2</summary>" in barra
    assert barra[:mais].count("data-barra-fixa=") == 2
    assert barra[mais:].count("data-barra-fixa=") == 2
    assert barra.find(NAV.FERJ_TITULO) < mais, "a do FERJ foi para trás do «+N»"


def test_a_barra_fica_no_fluxo_antes_do_titulo_e_fora_do_menu(cg_casa):
    """O teste de layout simples do pedido: a barra não cobre menu nem botões.

    Ela nasce DENTRO do `<main>` (o menu é o `<aside>`, antes dele), ANTES do
    `.topbar` — e o CSS dela não tem `position` nenhum: sem `fixed`,
    `absolute` ou `sticky`, ela ocupa o seu lugar e empurra a tela, em vez
    de flutuar por cima do que já estava ali.
    """
    from pathlib import Path

    c = _entrar(cg_casa, "bl1", "USER", "Escrevente Oito")
    html = c.get("/").get_data(as_text=True)
    fim_menu = html.find("</aside>")
    main = html.find('<main class="main">')
    barra = html.find("data-barras-fixas")
    topo = html.find('<header class="topbar">')
    assert -1 < fim_menu < main < barra < topo
    css = Path(__file__).resolve().parents[1].joinpath("static", "app.css").read_text(
        encoding="utf-8")
    regras = re.findall(r"([^{}]*\bbarras?-fixas?[^{}]*)\{([^}]*)\}", css)
    assert len(regras) >= 3, "o varredor do CSS da barra deixou de achar as regras"
    for seletor, corpo in regras:
        assert "position" not in corpo, f"{seletor.strip()} ganhou position: {corpo}"


def test_a_gestao_tem_o_modo_e_a_lista_de_quem_pagou(cg_casa):
    """O formulário grava o modo; a lista mostra a baixa, o «avisei» e o mês sem baixa."""
    db = cg_casa["db"]
    admin = _entrar(cg_casa, "bg1", "ADMIN", "Oficial Seis")
    html = admin.get("/admin/avisos/novo").get_data(as_text=True)
    assert 'name="modo"' in html and 'name="barra_dia_mes"' in html
    admin.post("/admin/avisos/novo", data={
        "csrf_token": _csrf(html), "titulo": "Barra pelo formulário",
        "corpo": "Corpo.", "barra_campos": "1", "modo": "BARRA",
        "barra_dia_mes": "5", "barra_papeis": ["ADMIN", "USER"]},
        follow_redirects=True)
    with db.connect() as con:
        nova = _banco_lx17(con).um(
            "SELECT * FROM nu_avisos WHERE titulo=%s", ("Barra pelo formulário",))
    assert nova["modo"] == "BARRA" and int(nova["barra_dia_mes"]) == 5
    assert nova["barra_papeis"] == "ADMIN,USER"

    db.create_user("bg2", "Escrevente Nove", SENHA, "USER")
    aid = int(_ferj(db)["id"])
    hoje = db.now()[:10]
    with db.transaction() as con:
        NAV.registrar_avisei(con, aid, user_id=_uid(db, "bg2"), palavra="avisei",
                             agora=db.now(), hoje=hoje)
    lista = admin.get("/avisos").get_data(as_text=True)
    assert "quem marcou pago em cada mês" in lista
    assert "Escrevente Nove" in lista and "Não marcado" in lista
    with db.transaction() as con:
        NAV.marcar_pago(con, aid, user_id=_uid(db, "bg1"), papel="ADMIN",
                        data_pagamento=hoje, guia="GX-77", agora=db.now(), hoje=hoje)
    lista = admin.get("/avisos").get_data(as_text=True)
    assert "Oficial Seis" in lista and "GX-77" in lista


def test_editar_sem_os_campos_da_barra_nao_desfaz_a_barra(cg_casa):
    """Quem chama `atualizar` como antes do LX17 não troca a barra por janela.

    E o FERJ/FERC não volta para a janela nem pela tela: é o pedido do oficial.
    """
    db = cg_casa["db"]
    aid = int(_ferj(db)["id"])
    with db.transaction() as con:
        NAV.atualizar(con, aid, titulo="FERJ/FERC — texto da casa",
                      corpo="Texto editado.", ativo=True, prioridade=0,
                      vigencia_inicio=None, vigencia_fim=None, agora=db.now())
    ferj = _ferj(db)
    assert ferj["modo"] == NAV.MODO_BARRA and int(ferj["barra_dia_mes"]) == 1
    assert ferj["corpo"] == "Texto editado."
    with db.transaction() as con:
        try:
            NAV.atualizar(con, aid, titulo="x", corpo="y", ativo=True, prioridade=0,
                          vigencia_inicio=None, vigencia_fim=None, agora=db.now(),
                          modo=NAV.MODO_JANELA, manter_barra=False)
        except NAV.AvisoGestaoError as erro:
            assert "sempre barra fixa mensal" in str(erro)
        else:
            raise AssertionError("o FERJ/FERC virou janela")


def test_o_aviso_do_sistema_nao_se_remove(cg_casa):
    """Removido, renasceria na subida sem a lista de quem pagou — desliga-se."""
    db = cg_casa["db"]
    with db.transaction() as con:
        try:
            NAV.remover(con, int(_ferj(db)["id"]))
        except NAV.AvisoGestaoError as erro:
            assert "não se remove" in str(erro)
        else:
            raise AssertionError("o aviso do FERJ/FERC foi removido")
    assert _ferj(db) is not None
