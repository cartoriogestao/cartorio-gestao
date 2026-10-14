# -*- coding: utf-8 -*-
"""HOTFIX-2026-10-09-04 - tela do modelo de averbacao, perfil USER, caso Amanda (exemplo)."""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"
SLUG = "retificacao-data-registro"


def _token(html):
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert m
    return m.group(1)


@pytest.fixture()
def casa(cg_casa):
    db, c = cg_casa["db"], cg_casa["cliente"]
    db.create_user("debora_t", "Debora Teste", SENHA, "USER")
    c.post("/login", data={"username": "debora_t", "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    con = sqlite3.connect(cg_casa["banco"])
    for n, d in ((13703, "2001-04-09"), (13705, "2001-04-09"), (13708, "2001-04-20")):
        con.execute("INSERT INTO rc_assentos(serie,especie,numero,nome,data_ato,data_fato,situacao,"
                    "livro_volume,criado_em) VALUES('RC_A','NASCIMENTO',?,?,?,'2001-01-01','ATIVO','A-14',"
                    "'2026-10-09T09:00')", (n, f"VIZINHO {n}", d))
    cur = con.execute(
        "INSERT INTO rc_assentos(serie,especie,numero,nome,data_ato,data_fato,situacao,livro_volume,"
        "matricula,dados_json,criado_em) VALUES('RC_A','NASCIMENTO',13706,'NAIR DA SILVA GARCEZ',"
        "'2001-04-18','2001-03-17','ATIVO','A-14','00000001552001100014157001370605',?,'2026-10-09T09:00')",
        (json.dumps({"data_registro_teor": "dezoito de abril de dois mil"}),))
    con.commit()
    cg_casa["aid"] = cur.lastrowid
    con.close()
    return cg_casa


def test_fluxo_completo_usuario_user(casa):
    c, aid = casa["cliente"], casa["aid"]
    html = c.get(f"/rcpn/{aid}/averbar").get_data(as_text=True)
    assert f"/rcpn/{aid}/averbar/modelo/{SLUG}" in html
    assert "Retificação — erro na data do registro" in html

    r = c.get(f"/rcpn/{aid}/averbar/modelo/{SLUG}")
    assert r.status_code == 200
    form = r.get_data(as_text=True)
    assert 'value="01/13.706"' in form
    assert "dezoito de abril de dois mil" in form
    assert 'value="2001-04-18"' in form
    assert "termo 13.705, de 09/04/2001" in form

    dados = {"csrf_token": _token(form), "acao": "gerar", "numero_av": "01/13.706",
             "data_como_consta": "dezoito de abril de dois mil", "data_correta": "2001-04-18",
             "elementos_prova": ("a sequência dos termos vizinhos (termo 13.703, de "
                                 "09/04/2001; termo 13.705, de 09/04/2001; termo 13.708, de 20/04/2001) "
                                 "e a data de nascimento do registrando, 17/03/2001, constante do próprio assento"),
             "requerente_tipo": "oficio", "requerente_nome": "",
             "fundamento": "Artigo 110, §§1º e 3º, da Lei 6.015/1973", "data_averbacao": "2026-10-09",
             "cidade": "Cidade Exemplo/MA", "subscritor_nome": "Debora Teste",
             "subscritor_funcao": "Escrevente Autorizada"}
    prev = c.post(f"/rcpn/{aid}/averbar/modelo/{SLUG}", data=dados).get_data(as_text=True)
    m = re.search(r'white-space:pre-wrap">(.*?)</div>', prev, re.S)
    assert m, prev[:2000]
    texto = m.group(1)
    Path(__import__("tempfile").gettempdir(), "_saida_averb_amanda.txt").write_text(texto, encoding="utf-8")
    assert texto.startswith("AVERBAÇÃO 01/13.706 – RETIFICAÇÃO: Em 9 de Outubro de 2026, de ofício")
    assert "Levar para a averbação" in prev

    dados["acao"] = "levar"
    r = c.post(f"/rcpn/{aid}/averbar/modelo/{SLUG}", data=dados)
    assert r.status_code in (302, 303) and r.headers["Location"].endswith(f"/rcpn/{aid}/averbar")
    tela = c.get(f"/rcpn/{aid}/averbar").get_data(as_text=True)
    assert "AVERBAÇÃO 01/13.706 – RETIFICAÇÃO" in tela
    assert 'value="retificacao" selected' in tela
    assert "Art. 110 da Lei 6.015/1973 - erro na data do registro" in tela
    # o preenchimento e de uma vez so
    assert "AVERBAÇÃO 01/13.706" not in c.get(f"/rcpn/{aid}/averbar").get_data(as_text=True)
    # nada gravado: nenhum ato, nenhum selo
    con = sqlite3.connect(casa["banco"])
    assert con.execute("SELECT COUNT(*) FROM rc_atos WHERE assento_id=?", (aid,)).fetchone()[0] == 0
    con.close()


def test_especie_ou_assento_inexistente(casa):
    c = casa["cliente"]
    assert c.get("/rcpn/999999/averbar/modelo/" + SLUG).status_code in (302, 303)
    assert c.get(f"/rcpn/{casa['aid']}/averbar/modelo/nao-existe").status_code in (302, 303)
