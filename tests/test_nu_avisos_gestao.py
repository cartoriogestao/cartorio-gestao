# -*- coding: utf-8 -*-
"""Modulo de avisos — CRUD ADMIN, dispensa diaria, contagem N, modo teste."""
from __future__ import annotations

import re
import sqlite3

import nu_avisos_gestao as NAV
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
