# -*- coding: utf-8 -*-
"""Robos nao selam automaticamente; humano sela ao salvar e pelo botao Selar.

Regra permanente do oficial (05/10/2026): contas Grok Bot (users.eh_robo=1)
deixam o ato pendente de selo. O balcao humano continua igual.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from tests.selador_de_bancada import ligar_o_selador, tem_cryptography

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


def _login(cliente, user, senha=SENHA):
    html = cliente.get("/login").get_data(as_text=True)
    return cliente.post(
        "/login",
        data={"username": user, "password": senha, "csrf_token": _token(html)},
        follow_redirects=True,
    )


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _insere_cartao(casa, nome, documento):
    con = _con(casa)
    with con:
        cur = con.execute(
            "INSERT INTO nt_cartoes (nome, documento, criado_em) "
            "VALUES (?,?,datetime('now'))",
            (nome, documento),
        )
        return int(cur.lastrowid)


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    db.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user(
        "robo_teste", "Robo Teste Notas", SENHA, "USER", eh_robo=1)
    # Sem codigo_tj no cx_servicos o balcao humano recusa antes da rede
    # (mesmo padrao de test_etiqueta_reconhecimento). O caminho do robo
    # nao chega nessa checagem — por isso so os testes humanos falhavam.
    con = sqlite3.connect(cg_casa["banco"])
    with con:
        for codigo, item, desc in (
            (412, "13.17.1", "Registro de firma (cartao)"),
            (413, "13.17.2", "Reconhecimento de firma, por assinatura"),
            (415, "13.18", "Autenticacao de documento"),
        ):
            con.execute(
                "UPDATE cx_servicos SET codigo_tj=? WHERE codigo=?",
                (item, codigo),
            )
            if con.execute(
                "SELECT 1 FROM cx_servicos WHERE codigo=?", (codigo,)
            ).fetchone() is None:
                con.execute(
                    """INSERT INTO cx_servicos
                           (codigo, codigo_tj, descricao, descricao_norm, ativo)
                       VALUES (?,?,?,?,1)""",
                    (codigo, item, desc, desc.upper()),
                )
    con.close()
    return cg_casa


def test_usuario_e_robo_e_pode_selar():
    import selo_robo as SR
    assert SR.usuario_e_robo({"eh_robo": 1, "full_name": "X", "username": "x"})
    assert not SR.pode_selar_automatico({"eh_robo": 1})
    assert SR.pode_selar_automatico(
        {"eh_robo": 0, "full_name": "JEAN", "username": "jean"})
    assert SR.usuario_e_robo(
        {"eh_robo": 0, "full_name": "Robo Debora", "username": "x"})


def test_migracao_eh_robo_existe(casa):
    cols = [r[1] for r in _con(casa).execute("PRAGMA table_info(users)")]
    assert "eh_robo" in cols
    row = _con(casa).execute(
        "SELECT eh_robo FROM users WHERE username='robo_teste'").fetchone()
    assert int(row["eh_robo"]) == 1


def test_robo_abre_cartao_sem_chamar_selo_e_nao_apaga(casa):
    if not tem_cryptography():
        pytest.skip("cryptography")
    c = casa["app"].test_client()
    _login(c, "robo_teste")
    with ligar_o_selador(casa) as aparelho:
        antes = len(aparelho.selos_por_sid)
        html = c.get("/notas/cartoes").get_data(as_text=True)
        r = c.post(
            "/notas/cartoes",
            data={
                "acao": "novo", "nome": "MARIA ROBO CARTAO",
                "documento": "00000001082",
                "csrf_token": _token(html),
            },
            follow_redirects=True,
        )
        body = r.get_data(as_text=True)
        assert r.status_code == 200
        assert "Pendente de selo" in body
        assert len(aparelho.selos_por_sid) == antes, "robo nao pode pedir selo"
        n = _con(casa).execute(
            "SELECT id, selo_abertura FROM nt_cartoes WHERE nome=?",
            ("MARIA ROBO CARTAO",)).fetchone()
        assert n is not None, "cartao nao pode ser apagado quando robo nao sela"
        assert not (n["selo_abertura"] or "").strip()


def test_humano_reconhecimento_sela_com_aparelho(casa):
    """Balcao humano continua selando ao salvar (comportamento intacto)."""
    if not tem_cryptography():
        pytest.skip("cryptography")
    cid = _insere_cartao(casa, "FIRMA HUMANA", "00000001082")
    c = casa["app"].test_client()
    _login(c, "tabeliao")
    with ligar_o_selador(casa) as aparelho:
        html = c.get("/notas/reconhecimento").get_data(as_text=True)
        r = c.post(
            "/notas/reconhecimento",
            data={
                "acao": "reconhecer", "cartao_id": str(cid),
                "especie": "SEMELHANCA", "csrf_token": _token(html),
            },
            follow_redirects=True,
        )
        body = r.get_data(as_text=True)
        assert "NÃO lavrado" not in body, body[:400]
        assert len(aparelho.selos_por_sid) >= 1
        row = _con(casa).execute(
            "SELECT selo FROM nt_reconhecimentos ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row and (row["selo"] or "").strip()


def test_botao_selar_cartao_humano_apos_robo_e_403_no_robo(casa):
    if not tem_cryptography():
        pytest.skip("cryptography")
    c = casa["app"].test_client()
    _login(c, "robo_teste")
    with ligar_o_selador(casa) as aparelho:
        html = c.get("/notas/cartoes").get_data(as_text=True)
        c.post(
            "/notas/cartoes",
            data={
                "acao": "novo", "nome": "ANA PENDENTE",
                "documento": "39053344705",
                "csrf_token": _token(html),
            },
            follow_redirects=True,
        )
        cid = _con(casa).execute(
            "SELECT id FROM nt_cartoes WHERE nome=?",
            ("ANA PENDENTE",)).fetchone()["id"]
        html2 = c.get(f"/notas/cartoes/{cid}").get_data(as_text=True)
        r403 = c.post(
            f"/notas/cartoes/{cid}/selar",
            data={"csrf_token": _token(html2)},
            follow_redirects=False,
        )
        assert r403.status_code == 403
        assert not (_con(casa).execute(
            "SELECT selo_abertura FROM nt_cartoes WHERE id=?", (cid,)
        ).fetchone()["selo_abertura"] or "").strip()

        # nova sessao humana
        c2 = casa["app"].test_client()
        _login(c2, "tabeliao")
        html3 = c2.get(f"/notas/cartoes/{cid}").get_data(as_text=True)
        assert "Pendente de selo" in html3
        antes = len(aparelho.selos_por_sid)
        r = c2.post(
            f"/notas/cartoes/{cid}/selar",
            data={"csrf_token": _token(html3)},
            follow_redirects=True,
        )
        body = r.get_data(as_text=True)
        assert r.status_code == 200
        selo = _con(casa).execute(
            "SELECT selo_abertura FROM nt_cartoes WHERE id=?",
            (cid,)).fetchone()["selo_abertura"]
        assert (selo or "").strip(), body[:500]
        assert len(aparelho.selos_por_sid) > antes


def test_robo_reconhecimento_fica_pendente_sem_apagar(casa):
    if not tem_cryptography():
        pytest.skip("cryptography")
    cid = _insere_cartao(casa, "FIRMA ROBO", "00000001082")
    c = casa["app"].test_client()
    _login(c, "robo_teste")
    with ligar_o_selador(casa) as aparelho:
        antes = len(aparelho.selos_por_sid)
        html = c.get("/notas/reconhecimento").get_data(as_text=True)
        r = c.post(
            "/notas/reconhecimento",
            data={
                "acao": "reconhecer", "cartao_id": str(cid),
                "especie": "SEMELHANCA", "csrf_token": _token(html),
            },
            follow_redirects=True,
        )
        body = r.get_data(as_text=True)
        assert "NÃO lavrado" not in body
        assert "Pendente de selo" in body
        assert len(aparelho.selos_por_sid) == antes
        assert _con(casa).execute(
            "SELECT COUNT(*) n FROM nt_reconhecimentos").fetchone()["n"] == 1


def test_robo_autenticacao_fica_pendente(casa):
    if not tem_cryptography():
        pytest.skip("cryptography")
    c = casa["app"].test_client()
    _login(c, "robo_teste")
    with ligar_o_selador(casa) as aparelho:
        antes = len(aparelho.selos_por_sid)
        html = c.get("/notas/autenticacao").get_data(as_text=True)
        r = c.post(
            "/notas/autenticacao",
            data={
                "acao": "autenticar", "folhas": "1", "tipo": "PADRAO",
                "csrf_token": _token(html),
            },
            follow_redirects=True,
        )
        body = r.get_data(as_text=True)
        assert "NÃO lavrada" not in body
        assert "Pendente de selo" in body
        assert len(aparelho.selos_por_sid) == antes
        n = _con(casa).execute(
            "SELECT id, selo FROM nt_autenticacoes ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert n is not None
        assert not (n["selo"] or "").strip()


def test_robo_403_na_rota_selar_autenticacao(casa):
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO nt_autenticacoes
               (data, hora, tipo, servico_codigo, folhas, texto, origem, criado_em)
               VALUES (date('now'), '10:00', 'PADRAO', 13, 1, 'x', 'MANUAL',
                       datetime('now'))""")
        aid = int(cur.lastrowid)
    c = casa["app"].test_client()
    _login(c, "robo_teste")
    html = c.get("/notas/autenticacao").get_data(as_text=True)
    r = c.post(
        f"/notas/autenticacao/{aid}/selar",
        data={"csrf_token": _token(html)},
        follow_redirects=False,
    )
    assert r.status_code == 403


def test_abrir_cartao_desmarcado_por_padrao():
    html = (RAIZ / "templates" / "notas_ato.html").read_text(encoding="utf-8")
    m = re.search(r'name="abrir_cartao"[^>]*>', html)
    assert m, "checkbox abrir_cartao sumiu"
    assert "checked" not in m.group(0)
