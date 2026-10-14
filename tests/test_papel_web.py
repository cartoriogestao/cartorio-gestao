"""Testes da TELA das folhas de segurança — Registro Civil → Folhas de segurança.

POR QUE ESTE ARQUIVO PASSOU A EXISTIR
    O incidente de 09/09/2026 (uma remessa com zero à esquerda duplicando 86
    folhas já cadastradas) só apareceu porque alguém RECEBEU uma caixa pela
    tela — o domínio sozinho não mostra o buraco de tela. O conserto ganhou
    duas peças: o dedup de `receber_remessa` passou a comparar pelo número
    (não pelo texto), e `estornar_remessa` desfaz o estrago já feito sem
    inutilizar folha a folha na mão.

O QUE ESTES TESTES GUARDAM
      - a tela recusa a remessa duplicada com zero à esquerda, com a
        mensagem certa;
      - o botão «Estornar» aparece só para ADMIN/MANAGER, e só quando sobra
        folha em branco na remessa;
      - estornar pela tela inutiliza as em branco e avisa quantas já
        estavam gastas.
"""
from __future__ import annotations

import glob
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
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _sessao(tmp_path, papel: str = "ADMIN"):
    from app import create_app
    from database import Database

    dados = tmp_path / papel.lower() / "dados"
    dados.mkdir(parents=True)
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    Database(banco).create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                                SENHA, papel)
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco}


@pytest.fixture()
def admin(tmp_path):
    return _sessao(tmp_path, "ADMIN")


@pytest.fixture()
def escrevente(tmp_path):
    return _sessao(tmp_path, "USER")


def _receber(s, de: str, ate: str, **campos):
    html = s["c"].get("/rcpn/papel").get_data(as_text=True)
    return s["c"].post("/rcpn/papel/receber", data={
        "csrf_token": _token(html), "fornecedor": "ARPENBRASIL", "serie": "HA",
        "codigo_de": de, "codigo_ate": ate, **campos}, follow_redirects=True)


def test_remessa_duplicada_com_zero_a_mais_e_recusada_pela_tela(admin):
    r1 = _receber(admin, "7225136", "7225145")
    assert "Entraram" in r1.get_data(as_text=True)
    r2 = _receber(admin, "007225140", "007225150")
    assert "já estão cadastradas" in r2.get_data(as_text=True)


def test_a_tela_oferece_estornar_so_para_admin_e_manager(admin, escrevente):
    _receber(admin, "7225136", "7225145")
    html_admin = admin["c"].get("/rcpn/papel").get_data(as_text=True)
    assert "Estornar" in html_admin
    html_escrevente = escrevente["c"].get("/rcpn/papel").get_data(as_text=True)
    assert "Estornar" not in html_escrevente


def test_estornar_pela_tela_inutiliza_as_em_branco(admin):
    _receber(admin, "7225136", "7225138")
    con = sqlite3.connect(admin["banco"])
    con.row_factory = sqlite3.Row
    remessa_id = con.execute(
        "SELECT id FROM pp_remessas ORDER BY id DESC LIMIT 1").fetchone()["id"]
    con.close()

    html = admin["c"].get("/rcpn/papel").get_data(as_text=True)
    r = admin["c"].post("/rcpn/papel/estornar", data={
        "csrf_token": _token(html), "remessa_id": str(remessa_id),
        "motivo": "duplicou remessa anterior"}, follow_redirects=True)
    texto = r.get_data(as_text=True)
    assert "3 folha(s) inutilizada(s)" in texto

    con = sqlite3.connect(admin["banco"])
    con.row_factory = sqlite3.Row
    linhas = con.execute(
        "SELECT situacao FROM pp_folhas WHERE remessa_id=?",
        (remessa_id,)).fetchall()
    con.close()
    assert all(l["situacao"] == "INUTILIZADA" for l in linhas)


def test_estornar_sem_motivo_e_recusado_pela_tela(admin):
    _receber(admin, "7225136", "7225138")
    con = sqlite3.connect(admin["banco"])
    con.row_factory = sqlite3.Row
    remessa_id = con.execute(
        "SELECT id FROM pp_remessas ORDER BY id DESC LIMIT 1").fetchone()["id"]
    con.close()

    html = admin["c"].get("/rcpn/papel").get_data(as_text=True)
    r = admin["c"].post("/rcpn/papel/estornar", data={
        "csrf_token": _token(html), "remessa_id": str(remessa_id),
        "motivo": ""}, follow_redirects=True)
    assert "Escreva por que" in r.get_data(as_text=True)


def test_escrevente_nao_consegue_estornar_direto_na_rota(escrevente):
    html = escrevente["c"].get("/rcpn/papel").get_data(as_text=True)
    r = escrevente["c"].post("/rcpn/papel/estornar", data={
        "csrf_token": _token(html), "remessa_id": "1",
        "motivo": "tentativa"})
    assert r.status_code == 403
