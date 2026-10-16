"""Folha do NASCIMENTO: selo dentro da margem e linhas de assinatura.

Elisa (escrevente), 09/10/2026, termo 19579: (1) a URL de consulta do selo
nao quebrava e invadia a coluna de notas; (2) faltavam as linhas de assinatura
do DECLARANTE e de QUEM LAVROU, com os nomes vindos do ato.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from test_rc_folha_tela import (  # noqa: F401
    casa, _con, _abrir, _assento, _pessoa, _nascimento, _obito, _casamento,
)

SELO = "REGNAS000000YAGQMNVGI8T80C30"
AGORA = "2026-10-09T08:56:40"


def _registro(casa, aid, *, criado_por, selo=SELO):
    con = _con(casa)
    with con:
        con.execute(
            "INSERT INTO rc_atos (assento_id, tipo, selo, data_ato, criado_em, criado_por)"
            " VALUES (?, 'REGISTRO', ?, ?, ?, ?)", (aid, selo, AGORA, AGORA, criado_por))


def _escrevente(casa):
    casa["db"].create_user("vteste", "Elisa Ficticia de Teste", "Senha#12345", "USER")
    con = _con(casa)
    with con:
        con.execute("UPDATE users SET funcao='Escrevente Autorizada' WHERE username='vteste'")


def test_nascimento_traz_declarante_e_quem_lavrou(casa):
    _escrevente(casa)
    aid = _nascimento(casa)
    _registro(casa, aid, criado_por="Elisa Ficticia de Teste")
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    assert 'class="assinaturas-do-termo"' in html
    assert "JOSE ENSAIO NASCIMENTO, Declarante" in html
    assert "Elisa Ficticia de Teste, Escrevente Autorizada" in html
    # o verso continua em branco
    assert html.count('class="assinaturas-do-termo"') == 1
    # o selo quebra dentro da caixa
    assert "word-break: break-all" in html and ".carimbo-do-selo .carimbo-link" in html
    destino = os.environ.get("SELO_MARGEM_SAIDA")
    if destino:
        Path(destino).write_text(html, encoding="utf-8")


def test_lavrou_por_id_do_usuario(casa):
    _escrevente(casa)
    con = _con(casa)
    uid = con.execute("SELECT id FROM users WHERE username='vteste'").fetchone()[0]
    aid = _nascimento(casa)
    _registro(casa, aid, criado_por=str(uid))
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    assert "Elisa Ficticia de Teste, Escrevente Autorizada" in html


def test_dado_que_falta_sai_em_branco_sem_quebrar(casa):
    aid = _assento(casa, especie="NASCIMENTO", numero="8700",
                   nome="SEM DECLARANTE DE TESTE")
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    assert 'class="assinaturas-do-termo"' in html
    assert '<div class="nome-ass">Declarante</div>' in html
    assert '<div class="nome-ass"></div>' in html


def test_obito_traz_declarante_e_quem_lavrou(casa):
    _escrevente(casa)
    aid = _obito(casa)
    _registro(casa, aid, criado_por="Elisa Ficticia de Teste")
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    assert 'class="assinaturas-do-termo"' in html
    assert "MARIA ENSAIO OBITO, Declarante" in html
    assert "Elisa Ficticia de Teste, Escrevente Autorizada" in html
    assert html.count('class="assinaturas-do-termo"') == 1


def test_casamento_traz_nubentes_e_quem_lavrou(casa):
    _escrevente(casa)
    aid = _casamento(casa)
    _registro(casa, aid, criado_por="Elisa Ficticia de Teste")
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    # Desde a resposta do oficial ao relato #124 (15/10/2026) o casamento
    # leva também testemunhas e juiz de paz, e as linhas saem em par.
    assert 'class="assinaturas-do-termo em-par"' in html
    assert "JOAO ENSAIO CASAMENTO, Primeiro nubente" in html
    assert "MARIA ENSAIO CASAMENTO, Segundo nubente" in html
    assert "Elisa Ficticia de Teste, Escrevente Autorizada" in html
    assert html.count('class="assinaturas-do-termo') == 1


def test_odt_da_folha_traz_as_linhas(casa):
    import io
    import zipfile
    _escrevente(casa)
    aid = _nascimento(casa)
    _registro(casa, aid, criado_por="Elisa Ficticia de Teste")
    r = casa["cliente"].get(f"/rcpn/{aid}/folha/papel?formato=odt")
    assert r.status_code == 200
    xml = zipfile.ZipFile(io.BytesIO(r.data)).read("content.xml").decode("utf-8")
    assert "JOSE ENSAIO NASCIMENTO, Declarante" in xml
    assert "Elisa Ficticia de Teste, Escrevente Autorizada" in xml
    destino = os.environ.get("SELO_MARGEM_ODT")
    if destino:
        Path(destino).write_bytes(r.data)
