"""A averbação do CPF no CASAMENTO — a TELA, com os DOIS nubentes.

    «precisamos averbar o cpf dos noivos no registro que importamos de
    acervo, mas o sistema só tem a opçao de averbar 1 cpf. Como fazer? dá
    pra colocar um depois do outro? o texto precisa mudar um pouco pq
    precisa dizer qual cpf se refere a cada cônjuge»
    — o oficial, 09/09/2026

O QUE SE MEDIU ANTES DE CONSTRUIR
    O formulário de averbar CPF (`/rcpn/<id>/averbar-cpf`) só conhecia o
    papel `REGISTRADO` — que existe no nascimento e no óbito, e não existe
    no casamento (lá são `NUBENTE1`/`NUBENTE2`). E a seção da ficha
    desaparecia inteira assim que `rc_assentos.cpf_registrado` (uma coluna
    só) recebia QUALQUER valor — não havia como o segundo cônjuge nem
    aparecer. Dois defeitos, um resultado: «só dá para averbar 1 CPF».

O QUE ESTES TESTES GUARDAM
      - a ficha mostra um botão POR NUBENTE, cada um com o nome;
      - averbar o primeiro NÃO faz o segundo sumir — ao contrário do
        nascimento, onde uma coluna só bastava;
      - o teor de cada averbação diz de quem é o CPF;
      - depois dos dois, a seção inteira some;
      - o nascimento continua exatamente como sempre foi (um botão, sem
        pedir para escolher ninguém).
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
AGORA = "2026-09-09T12:00:00"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def s(cg_casa):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    cg_casa['db'].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                                SENHA, "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    bancada = {"app": app, "c": c, "banco": banco,
               "dados": dados, "db": cg_casa["db"]}
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(bancada):
        yield bancada


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def _semear_casamento(s) -> int:
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO rc_assentos(serie, especie, numero, matricula,
                   nome, data_ato, data_fato, situacao, origem, criado_em)
               VALUES ('RC_B','CASAMENTO',111,
                       '000000015519971000111270020385 79',
                       'JOÃO / MARIA','2010-05-03','2010-05-03',
                       'ATIVO','EOFICIO',?)""", (AGORA,))
        assento_id = con.execute(
            "SELECT id FROM rc_assentos").fetchone()["id"]
        con.execute(
            """INSERT INTO rc_atos(assento_id, tipo, folha, numero_ordem,
                   rotulo, data_ato, origem, criado_em)
               VALUES (?,'REGISTRO',13,111,'13','2010-05-03','EOFICIO',?)""",
            (assento_id, AGORA))
        for papel, nome in (("NUBENTE1", "JOÃO DA SILVA"),
                           ("NUBENTE2", "MARIA DOS SANTOS")):
            con.execute(
                """INSERT INTO rc_pessoas(assento_id, papel, nome, origem,
                       criado_em)
                   VALUES (?,?,?,'EOFICIO',?)""",
                (assento_id, papel, nome, AGORA))
    con.close()
    return assento_id


def _averbar(s, assento_id, *, cpf, papel=None):
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    dados = {"csrf_token": _token(html), "cpf": cpf}
    if papel:
        dados["papel"] = papel
    return s["c"].post(f"/rcpn/{assento_id}/averbar-cpf", data=dados,
                       follow_redirects=True)


def test_a_ficha_do_casamento_mostra_um_botao_por_nubente(s):
    assento_id = _semear_casamento(s)
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    assert html.count('name="cpf"') == 2
    assert 'value="NUBENTE1"' in html and 'value="NUBENTE2"' in html
    assert "JOÃO DA SILVA" in html and "MARIA DOS SANTOS" in html


def test_averbar_o_primeiro_nao_faz_o_segundo_sumir(s):
    assento_id = _semear_casamento(s)
    r = _averbar(s, assento_id, cpf="000.000.045-02", papel="NUBENTE1")
    texto = r.get_data(as_text=True)
    assert "averbado gratuitamente" in texto
    assert "Primeiro nubente" in texto and "JOÃO DA SILVA" in texto

    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    # o formulario do PRIMEIRO sumiu; o do SEGUNDO continua de pé.
    assert html.count('name="cpf"') == 1
    assert 'value="NUBENTE2"' in html
    assert 'value="NUBENTE1"' not in html


def test_averbar_os_dois_faz_a_secao_inteira_sumir(s):
    assento_id = _semear_casamento(s)
    _averbar(s, assento_id, cpf="000.000.045-02", papel="NUBENTE1")
    _averbar(s, assento_id, cpf="000.000.015-97", papel="NUBENTE2")
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    assert "Averbar CPF" not in html
    assert 'name="cpf"' not in html


def test_o_teor_diz_de_quem_e_o_cpf(s):
    assento_id = _semear_casamento(s)
    _averbar(s, assento_id, cpf="000.000.045-02", papel="NUBENTE1")
    _averbar(s, assento_id, cpf="000.000.015-97", papel="NUBENTE2")
    con = _con(s)
    teores = [r["teor"] for r in con.execute(
        "SELECT teor FROM rc_atos WHERE assento_id=? AND tipo='AVERBACAO' "
        "ORDER BY id", (assento_id,))]
    con.close()
    assert len(teores) == 2
    assert "referente ao primeiro nubente, JOÃO DA SILVA" in teores[0]
    assert "referente ao segundo nubente, MARIA DOS SANTOS" in teores[1]


def test_cada_cpf_vai_para_a_pessoa_certa_e_nao_para_a_coluna_do_assento(s):
    """O casamento não usa `rc_assentos.cpf_registrado` — não há coluna para
    um segundo número."""
    assento_id = _semear_casamento(s)
    _averbar(s, assento_id, cpf="000.000.045-02", papel="NUBENTE1")
    _averbar(s, assento_id, cpf="000.000.015-97", papel="NUBENTE2")
    con = _con(s)
    n1 = con.execute("SELECT documento_numero FROM rc_pessoas "
                     "WHERE assento_id=? AND papel='NUBENTE1'",
                     (assento_id,)).fetchone()["documento_numero"]
    n2 = con.execute("SELECT documento_numero FROM rc_pessoas "
                     "WHERE assento_id=? AND papel='NUBENTE2'",
                     (assento_id,)).fetchone()["documento_numero"]
    cpf_no_assento = con.execute(
        "SELECT cpf_registrado FROM rc_assentos WHERE id=?",
        (assento_id,)).fetchone()["cpf_registrado"]
    con.close()
    assert n1 == "00000004502"
    assert n2 == "00000001597"
    assert not cpf_no_assento


# ---------------------- o nascimento continua exatamente como sempre foi


def _semear_nascimento(s) -> int:
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO rc_assentos(serie, especie, numero, matricula,
                   nome, data_ato, data_fato, situacao, origem, criado_em)
               VALUES ('RC_A','NASCIMENTO',19552,
                       '000000015519971000111270010385 01','ANA CLARA',
                       '2010-05-03','2010-05-01','ATIVO','EOFICIO',?)""",
            (AGORA,))
        assento_id = con.execute(
            "SELECT id FROM rc_assentos").fetchone()["id"]
        con.execute(
            """INSERT INTO rc_atos(assento_id, tipo, folha, numero_ordem,
                   rotulo, data_ato, origem, criado_em)
               VALUES (?,'REGISTRO',127,19552,'127','2010-05-03','EOFICIO',
                       ?)""", (assento_id, AGORA))
        con.execute(
            """INSERT INTO rc_pessoas(assento_id, papel, nome, origem,
                   criado_em)
               VALUES (?,'REGISTRADO','ANA CLARA','EOFICIO',?)""",
            (assento_id, AGORA))
    con.close()
    return assento_id


def test_nascimento_continua_com_um_botao_so_sem_pedir_papel(s):
    assento_id = _semear_nascimento(s)
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    assert html.count('name="cpf"') == 1
    assert 'name="papel"' not in html
    assert "CPF do registrado" in html


def test_nascimento_averba_e_a_secao_some_e_a_coluna_do_assento_recebe(s):
    assento_id = _semear_nascimento(s)
    r = _averbar(s, assento_id, cpf="000.000.045-02")
    texto = r.get_data(as_text=True)
    assert "averbado gratuitamente" in texto
    assert "referente a" not in texto     # sem nome — um principal só

    con = _con(s)
    ato = con.execute(
        "SELECT teor FROM rc_atos WHERE assento_id=? AND tipo='AVERBACAO'",
        (assento_id,)).fetchone()
    cpf_no_assento = con.execute(
        "SELECT cpf_registrado FROM rc_assentos WHERE id=?",
        (assento_id,)).fetchone()["cpf_registrado"]
    con.close()
    assert ato["teor"].startswith(
        "Averbo neste assento o CPF n. 000.000.045-02.")
    assert "referente a" not in ato["teor"]
    assert cpf_no_assento == "00000004502"

    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    assert "Averbar CPF" not in html
