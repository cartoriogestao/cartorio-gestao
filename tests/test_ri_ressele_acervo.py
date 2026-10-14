"""HOTFIX-2026-10-09-08 — nao oferecer selo como pendencia para ato que ja tem selo.

Razao (sd_selos ligado), codigo de selo citado no teor, ou ato de acervo anterior
ao sistema: etiqueta no lugar do botao; ADMIN/MANAGER so por «Selar mesmo assim»
com confirmacao. Ato novo sem selo continua com o botao normal. Nada e selado aqui.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
SENHA = "Senha#12345"


def _token(html):
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert m
    return m.group(1)


def _entrar(app, usuario):
    c = app.test_client()
    c.post("/login", data={"username": usuario, "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    db.create_user("jean", "JEAN ADMIN", SENHA, "ADMIN")
    db.create_user("balcao", "QUEM ATENDE", SENHA, "USER")
    return {**cg_casa, "admin": _entrar(cg_casa["app"], "jean"),
            "balcao": _entrar(cg_casa["app"], "balcao")}


def _con(casa):
    con = sqlite3.connect(casa["banco"]); con.row_factory = sqlite3.Row
    return con


def _ficha(casa, atos, encerrada=1):
    """atos: lista de (numero, teor, acervo, origem, selo_no_razao)."""
    from ri_schema import hash_ato
    con = _con(casa); ids = []
    with con:
        mid = int(con.execute(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao, tipo_ficha,
                   criado_em, encerrada, data_encerramento)
               VALUES ('3769','2-S','2-S',?, 'ACERVO','2026-10-01T14:00',?,?)""",
            ("ENCERRADA" if encerrada else "ATIVA", encerrada,
             "2026-10-01" if encerrada else None)).lastrowid)
        ant = None
        for numero, teor, acervo, origem, razao in atos:
            h = hash_ato("3769", "AV", numero, "2024-07-29", teor, ant); ant = h
            aid = int(con.execute(
                """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, teor, teor_formato,
                       cancelado, acervo, origem, hash_ato, lavrado_em)
                   VALUES (?, 'AV', ?, '2024-07-29', ?, 'texto', 0, ?, ?, ?, '2026-10-01T14:16')""",
                (mid, numero, teor, acervo, origem, h)).lastrowid)
            if razao:
                con.execute("""INSERT INTO sd_selos (numero, texto, tabela, ato_id, atribuicao, obtido_em)
                               VALUES (?, ?, 'ri_atos', ?, 'IMOVEL', '2024-04-29T18:23:32')""",
                            (razao, "Selo: " + razao, aid))
            ids.append(aid)
    con.close()
    return mid, ids


COD = "AVEGEO000000VYIUK3L8V63CFP15"


def _bloco(html, aid):
    i = html.index(f'id="selar-ato-{aid}"')
    return html[i:html.index("</details>", i)]


def test_acervo_e_selados_viram_etiqueta_e_novo_continua(casa):
    mid, (a_raz, a_teor, a_acv, a_novo) = _ficha(casa, [
        (1, "AV-1 acervo", 1, "MANUAL", COD),
        (2, "AV-2. Selo Geral 27417124.", 0, "MANUAL", None),
        (3, "AV-3 do acervo antigo", 1, "MANUAL", None),
        (4, "AV-4 lavrado hoje", 0, "MANUAL", None)])
    html = casa["balcao"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    for aid in (a_raz, a_teor, a_acv):
        assert f'id="selar-ato-{aid}"' not in html
    assert "Já selado (acervo)" in html and "Selo citado no teor" in html
    assert "Selar este ato" in _bloco(html, a_novo)
    # aviso da ficha encerrada so aponta o ato novo
    assert f'href="#selar-ato-{a_novo}"' in html
    for aid in (a_raz, a_teor, a_acv):
        assert f'href="#selar-ato-{aid}"' not in html
    # gerente/admin: «Selar mesmo assim» com confirmacao obrigatoria
    h2 = casa["admin"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    b = _bloco(h2, a_acv)
    assert "Selar mesmo assim" in b and 'name="confirmar_ressele"' in b and "duplicidade" in b


def test_lista_nao_mostra_atalho_para_acervo(casa):
    mid, _ = _ficha(casa, [(1, "AV-1 acervo", 1, "MANUAL", None)])
    html = casa["admin"].get("/registro-imoveis?busca=3769").get_data(as_text=True)
    assert "#selar-ato-" not in html


def test_post_sem_confirmacao_ou_por_escrevente_recusa(casa):
    mid, (aid,) = _ficha(casa, [(1, "AV-1 acervo", 1, "MANUAL", COD)])
    for cli, extra in ((casa["balcao"], {"confirmar_ressele": "1"}), (casa["admin"], {})):
        h = cli.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
        r = cli.post(f"/registro-imoveis/ato/{aid}/selar",
                     data={"csrf_token": _token(h), "natureza_titulo": "x",
                           "codigo_tj_selo": "16.22.2", "qtd_selo": "1", **extra},
                     follow_redirects=True).get_data(as_text=True)
        assert "duplicidade" in r
    con = _con(casa)
    assert con.execute("SELECT COUNT(*) FROM sd_selos").fetchone()[0] == 1
    con.close()
