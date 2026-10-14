"""O nome do registrador do RI não tinha tela — achado em 07/09/2026.

    Conferindo se a ficha nova do Registro de Imóveis já está pronta, o
    cabeçalho saiu com **"MARIO EXEMPLO DOS SANTOS"** — falta o "T". A mesma
    correção já tinha sido feita em `serventia.PADRAO["serventia_titular"]`
    em 30/08/2026 (ver `rc_cabecalho.py`), mas `ri_registrador` é OUTRO
    valor, que só a ficha do RI lê, e nenhuma tela o alcançava.

    E como `DEFAULT_SETTINGS` só entra com `INSERT OR IGNORE`, corrigir o
    valor de fábrica não corrige o que já está gravado: só uma tela que
    salva de novo resolve isso na instalação existente.
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


@pytest.fixture()
def s(cg_casa):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    cg_casa['db'].create_user("tabeliao", "Mario Exemplo dos Santos", SENHA, "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco}


def test_de_fabrica_o_registrador_do_ri_ja_sai_com_t(s):
    con = sqlite3.connect(s["banco"])
    valor = con.execute(
        "SELECT value FROM settings WHERE key='ri_registrador'").fetchone()[0]
    con.close()
    assert valor == "Mario Exemplo dos Santos"
    assert "EXEMPLO" not in valor


def test_A_TELA_DE_CONFIGURACOES_DEIXA_CORRIGIR_O_REGISTRADOR_DO_RI(s):
    # Simula a instalação existente, com o valor errado já gravado — o caso
    # que a correção do padrão de fábrica, sozinha, não alcança.
    con = sqlite3.connect(s["banco"])
    con.execute("UPDATE settings SET value='MARIO EXEMPLO DOS SANTOS' "
                "WHERE key='ri_registrador'")
    con.commit()
    con.close()

    html = s["c"].get("/configuracoes").get_data(as_text=True)
    assert 'name="ri_registrador"' in html
    assert "MARIO EXEMPLO DOS SANTOS" in html   # a tela mostra o que está lá

    r = s["c"].post("/configuracoes", data={
        "csrf_token": _token(html),
        "unit_name": "Ofício Único de Cidade Exemplo/MA",
        "ri_registrador": "Mario Exemplo dos Santos",
    }, follow_redirects=True)
    assert r.status_code == 200

    con = sqlite3.connect(s["banco"])
    valor = con.execute(
        "SELECT value FROM settings WHERE key='ri_registrador'").fetchone()[0]
    con.close()
    assert valor == "Mario Exemplo dos Santos"


def test_CAMPO_VAZIO_NAO_APAGA_O_QUE_JA_ESTAVA_GRAVADO(s):
    html = s["c"].get("/configuracoes").get_data(as_text=True)
    s["c"].post("/configuracoes", data={
        "csrf_token": _token(html),
        "unit_name": "Ofício Único de Cidade Exemplo/MA",
        "ri_registrador": "",
    }, follow_redirects=True)

    con = sqlite3.connect(s["banco"])
    valor = con.execute(
        "SELECT value FROM settings WHERE key='ri_registrador'").fetchone()[0]
    con.close()
    assert valor == "Mario Exemplo dos Santos"   # continua o de fábrica


def test_a_ficha_do_ri_le_o_registrador_das_configuracoes():
    import ri_web
    assert 'ri_registrador' in Path(ri_web.__file__).read_text(encoding="utf-8")


# ------------------- O DEFEITO QUE ISTO ACHOU DE PASSAGEM, E NÃO É DO
# SUBMÓDULO DE MODELOS: `base.html` usava `{% set s = namespace(n=0) %}`
# oito vezes, para colorir as seções do menu — e isso apaga QUALQUER `s`
# que uma tela passe para o próprio conteúdo, porque `{% block content %}`
# vem DEPOIS do menu no arquivo. A tela de Configurações usa `s` para os
# próprios dados há muito tempo: **"Nome da unidade" e outros treze campos
# saíam em branco na tela**, sempre, para quem visse o menu inteiro (ADMIN).
# Renomeado para `nsec` em `base.html`; nenhuma tela deveria voltar a usar
# `s`/`nsec` como nome de variável de template sem medir contra isto.

def test_A_TELA_DE_CONFIGURACOES_MOSTRA_O_NOME_DA_UNIDADE(s):
    html = s["c"].get("/configuracoes").get_data(as_text=True)
    assert 'value="Ofício Único de Cidade Exemplo/MA"' in html, (
        "campo 'Nome da unidade' saiu vazio — o menu (base.html) está "
        "sobrescrevendo a variável de template 's' de novo")


def test_BASE_HTML_NAO_REUTILIZA_S_PARA_O_CONTADOR_DE_SECAO():
    texto = Path("templates/base.html").read_text(encoding="utf-8")
    assert "set s = namespace" not in texto, (
        "'s' é o nome mais óbvio para uma tela passar os próprios dados "
        "(settings_dict() em várias rotas já se chama 's') — reaproveitá-lo "
        "aqui apaga o que a tela mandou, porque o menu vem antes de "
        "{% block content %} no arquivo"
    )
