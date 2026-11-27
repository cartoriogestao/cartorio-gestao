# -*- coding: utf-8 -*-
"""O relógio que volta e a sessão dos testes (25/11/2026).

A suíte da CI caía de vez em quando com o cliente logado mandado para /login,
cada rodada num teste diferente. A causa: o cookie da sessão é assinado com a
hora em segundos inteiros, e a assinatura de idade negativa é recusada calada —
basta o relógio da máquina de teste voltar um segundo. A trava mora no
`conftest` (`RELOGIO_DA_ASSINATURA`); aqui se prova o defeito, a trava e o
`cg_login` que passou a falhar na hora.
"""
from __future__ import annotations

import time

import pytest
from itsdangerous import SignatureExpired, TimestampSigner

import conftest

SENHA = "Senha#12345"


def test_sem_a_trava_a_assinatura_do_futuro_e_recusada(monkeypatch):
    """O que o `itsdangerous` faz sozinho: é isso que a trava do `conftest` segura."""
    monkeypatch.setattr(TimestampSigner, "get_timestamp", lambda self: int(time.time()))
    assinado = TimestampSigner("chave-de-teste").sign("sessao")
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() - 2)
    with pytest.raises(SignatureExpired):
        TimestampSigner("chave-de-teste").unsign(assinado, max_age=3600)


def test_o_relogio_que_volta_nao_derruba_a_sessao(cg_casa_logada, monkeypatch):
    c = cg_casa_logada["c"]
    assert c.get("/caixa/protocolos").status_code == 200
    antes = conftest.RELOGIO_DA_ASSINATURA.recuos
    real = time.time
    # Dois segundos para trás logo depois da tela: sem a trava, as duas respostas
    # seriam 302 para /login (a do `roles_required` e a do `login_required`).
    monkeypatch.setattr(time, "time", lambda: real() - 2)
    r = c.get("/caixa/protocolos")
    assert r.status_code == 200, r.headers.get("Location")
    r = c.get("/")
    assert r.status_code == 200, r.headers.get("Location")
    assert conftest.RELOGIO_DA_ASSINATURA.recuos == antes + 1
    assert "voltou" in conftest.RELOGIO_DA_ASSINATURA.resumo()


def test_cg_login_que_nao_entra_falha_na_hora_e_diz_por_que(cg_casa):
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    with pytest.raises(AssertionError) as erro:
        conftest.cg_login(cg_casa["c"], "mario", "senha-errada")
    mensagem = str(erro.value)
    assert mensagem.startswith("cg_login('mario'): o login não abriu a sessão")
    assert "Usuário ou senha inválidos" in mensagem
    assert "relógio" in mensagem
    # E o login certo segue devolvendo a tela de entrada, como antes.
    assert conftest.cg_login(cg_casa["c"], "mario", SENHA).status_code == 200


def test_cg_login_com_recusa_exige_a_recusa(cg_casa):
    """O teste que quer a senha recusada pede `recusa=True`: a recusa passa, e o login
    que entra por engano é que cai — a conferência não afrouxa em nenhum sentido."""
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    r = conftest.cg_login(cg_casa["c"], "mario", "senha-errada", recusa=True)
    assert "Usuário ou senha inválidos" in r.get_data(as_text=True)
    with pytest.raises(AssertionError, match="devia ser recusado e abriu a sessão"):
        conftest.cg_login(cg_casa["app"].test_client(), "mario", SENHA, recusa=True)
