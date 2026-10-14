# -*- coding: utf-8 -*-
"""A folha de seguranca na ficha e o /rcpn/papel com o assento - 09/10/2026
(FICHA_FOLHA_SEGURANCA_20261009), pedido da escrevente Elisa.

    - o bloco do REGISTRO da ficha mostra «Folha de seguranca: IA 0000000»
      (a linha «Folha» do quadro do assento e a folha do LIVRO);
    - a tabela das usadas em /rcpn/papel mostra o registrado e o assento com
      link para a ficha, da mais recente, com busca e paginas.
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
sys.path.insert(0, str(Path(__file__).resolve().parent))

import papel_seguranca as PP                                     # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-10-09T10:00:00"
FOLHAS = ("9300001", "9300002", "9300003")


def _token(html):
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado
    return achado.group(1)


@pytest.fixture()
def casa(tmp_path):
    from app import create_app
    from database import Database
    from selador_de_bancada import ligar_o_selador

    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    db = Database(banco)
    db.create_user("elisa", "ELISA TESTE", SENHA, "ADMIN")
    con = sqlite3.connect(banco)
    with con:
        PP.receber_remessa(con, fornecedor="ARPENBRASIL", serie="IA",
                           codigo_de=FOLHAS[0], codigo_ate=FOLHAS[-1],
                           agora=AGORA, nota_fiscal="NF", usuario="T")
    con.close()
    bancada = {"app": app, "banco": banco, "dados": dados, "db": db}
    with ligar_o_selador(bancada):
        c = app.test_client()
        html = c.get("/login").get_data(as_text=True)
        c.post("/login", data={"username": "elisa", "password": SENHA,
                               "csrf_token": _token(html)},
               follow_redirects=True)
        bancada["c"] = c
        yield bancada


def _lavrar(casa, folha, nome="CRIANCA DA FICHA"):
    c = casa["c"]
    html = c.get("/rcpn/novo/nascimento").get_data(as_text=True)
    dados = {"csrf_token": _token(html), "especie": "NASCIMENTO",
             "acao": "lavrar", "folha_seguranca": folha, "nome": nome,
             "pessoa_nome": nome, "pessoa_sexo": "F",
             "data_fato": "2026-10-01", "local_fato_nome": "Hospital",
             "filiacao1_nome": "MAE DA FICHA", "filiacao2_nome": "IGNORADO",
             "declarante_nome": "MAE DA FICHA"}
    c.post("/rcpn/novo/nascimento", data=dados, follow_redirects=True)
    con = sqlite3.connect(casa["banco"])
    aid = con.execute("SELECT MAX(id) FROM rc_assentos").fetchone()[0]
    con.close()
    return int(aid)


def _texto(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def test_ficha_mostra_a_folha_de_seguranca_no_bloco_do_registro(casa):
    aid = _lavrar(casa, FOLHAS[1])
    html = casa["c"].get(f"/rcpn/{aid}").get_data(as_text=True)
    assert "data-folha-seguranca" in html
    assert f"Folha de segurança: IA {FOLHAS[1]}" in _texto(html)


def test_papel_mostra_o_registrado_com_link_e_busca(casa):
    aid = _lavrar(casa, FOLHAS[2], nome="ZULMIRA BUSCAVEL")
    c = casa["c"]
    html = c.get("/rcpn/papel").get_data(as_text=True)
    assert f'href="/rcpn/{aid}"' in html
    assert "ZULMIRA BUSCAVEL" in html
    assert "rc_atos nº" not in html
    for q in ("ZULMIRA", FOLHAS[2], f"IA {FOLHAS[2]}", str(aid)):
        achou = c.get("/rcpn/papel", query_string={"q": q}).get_data(as_text=True)
        assert "ZULMIRA BUSCAVEL" in achou, q
    nada = c.get("/rcpn/papel", query_string={"q": "NINGUEM-ASSIM"}).get_data(as_text=True)
    assert "ZULMIRA BUSCAVEL" not in nada and "Nenhuma folha gasta" in nada


def test_papel_pagina_alem_das_60(casa):
    con = sqlite3.connect(casa["banco"])
    with con:
        PP.receber_remessa(con, fornecedor="ARPENBRASIL", serie="ZZ",
                           codigo_de="8000001", codigo_ate="8000130",
                           agora=AGORA, nota_fiscal="NF2", usuario="T")
        # folhas antigas gastas (fixture de teste, sem ato): a mais antiga
        # e a 8000001
        for i in range(130):
            con.execute("UPDATE pp_folhas SET situacao='USADA', usada_em=? "
                        "WHERE codigo=?",
                        (f"2026-01-01T00:{i // 60:02d}:{i % 60:02d}",
                         str(8000001 + i)))
    con.close()
    c = casa["c"]
    p1 = c.get("/rcpn/papel").get_data(as_text=True)
    assert "página 1 de 3" in p1 and "<td>ZZ 8000130</td>" in p1 and "<td>ZZ 8000001</td>" not in p1
    p3 = c.get("/rcpn/papel", query_string={"pagina": 3}).get_data(as_text=True)
    assert "página 3 de 3" in p3 and "<td>ZZ 8000001</td>" in p3
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    r = PP.usadas_com_assento(con, pagina=2)
    con.close()
    assert r["total"] == 130 and len(r["linhas"]) == 60 and r["paginas"] == 3
