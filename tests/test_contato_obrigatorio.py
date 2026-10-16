"""Telefone OU e-mail, pelo menos um, ao abrir prenotação e protocolo geral — ordem do oficial, 10/10/2026.

    «colocar telefone ou email como obrigatorios na prenotacao ou protocolo geral»

Medido antes, na produção: das 19 prenotações do sistema novo, nenhuma com e-mail e 9 sem
telefone; dos 112 protocolos gerais, 100 sem contato nenhum.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import contato_do_cliente as CONTATO  # noqa: E402

SENHA = "Senha#12345"


# ------------------------------------------------------------------ a regra

def test_basta_o_telefone():
    assert CONTATO.exigir("(99) 98888-7777", "") == ("(99) 98888-7777", None)


def test_basta_o_email():
    assert CONTATO.exigir("", " cliente@provedor.com ") == (None, "cliente@provedor.com")


def test_sem_nenhum_e_recusado():
    with pytest.raises(CONTATO.ContatoError, match="pelo menos um"):
        CONTATO.exigir("  ", None)


def test_telefone_sem_ddd_e_recusado():
    with pytest.raises(CONTATO.ContatoError, match="DDD"):
        CONTATO.exigir("98412-0529", "")


def test_email_incompleto_e_recusado():
    with pytest.raises(CONTATO.ContatoError, match="não está completo"):
        CONTATO.exigir("", "cliente@provedor")


def test_e_erro_de_regra_e_nao_500():
    assert issubclass(CONTATO.ContatoError, ValueError)


# ------------------------------------------------------------------ as telas

def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    c = cg_casa["cliente"]
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login", data={"username": "mario", "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa


def _n(casa, tabela):
    con = sqlite3.connect(casa["banco"])
    try:
        return con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
    finally:
        con.close()


def _prenotar(casa, **extra):
    html = casa["cliente"].get("/registro-imoveis/protocolo").get_data(as_text=True)
    dados = {"apresentante": "MARIA DA SILVA", "natureza_titulo": "COMPRA E VENDA",
             "objeto": "escritura", "livro_destino": "2", "csrf_token": _token(html)}
    dados.update(extra)
    return casa["cliente"].post("/registro-imoveis/protocolo", data=dados, follow_redirects=True)


def _abrir_protocolo(casa, **extra):
    html = casa["cliente"].get("/caixa/protocolos").get_data(as_text=True)
    dados = {"acao": "novo", "interessado": "JOÃO DA SILVA", "atribuicao": "RI",
             "tipo": "SERVICO", "csrf_token": _token(html)}
    dados.update(extra)
    return casa["cliente"].post("/caixa/protocolos", data=dados, follow_redirects=True)


def test_prenotacao_sem_contato_nao_entra(casa):
    antes = _n(casa, "ri_protocolos")
    html = _prenotar(casa).get_data(as_text=True)
    assert "pelo menos um" in html
    assert _n(casa, "ri_protocolos") == antes


def test_prenotacao_com_telefone_entra_e_grava(casa):
    antes = _n(casa, "ri_protocolos")
    _prenotar(casa, telefone="(99) 98888-7777")
    assert _n(casa, "ri_protocolos") == antes + 1
    con = sqlite3.connect(casa["banco"])
    tel = con.execute("SELECT telefone FROM ri_protocolos ORDER BY id DESC LIMIT 1").fetchone()[0]
    con.close()
    assert tel == "(99) 98888-7777"


def test_protocolo_geral_sem_contato_nao_entra(casa):
    antes = _n(casa, "cx_protocolos")
    html = _abrir_protocolo(casa).get_data(as_text=True)
    assert "pelo menos um" in html
    assert _n(casa, "cx_protocolos") == antes


def test_protocolo_geral_com_email_entra(casa):
    antes = _n(casa, "cx_protocolos")
    _abrir_protocolo(casa, email="joao@provedor.com")
    assert _n(casa, "cx_protocolos") == antes + 1


def test_as_duas_telas_dizem_que_e_obrigatorio(casa):
    for url in ("/registro-imoveis/protocolo", "/caixa/protocolos"):
        html = casa["cliente"].get(url).get_data(as_text=True)
        assert "pelo menos um é obrigatório" in html, url
