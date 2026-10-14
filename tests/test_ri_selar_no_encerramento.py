"""HOTFIX-2026-10-09-07 — selar o ato onde há encerramento (Beatriz, 09/10/2026 13:55).

«Verifique na matrícula 1130, 1196, e não só na matrícula, mas no campo de
matrículas onde tem encerramento, insira o campo de selar o ato, tanto pra
selar o item quanto o de arquivamento e a opção de gratuito, caso necessário,
inclusive a informação de gratuito pelo REURB.»

O «Selar este ato» (ato lavrado sem selo, inclusive o encerramento, com a
ficha fechada) ganha REURB-S/E/misto e o arquivamento opcional com folhas; a
ficha encerrada e a lista de matrículas levam direto a ele. Nesta instalação
de ensaio não há selador: nada é selado — o caminho provado é o da tela e o
do que fica gravado antes da rede.
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


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


def _entrar(app, usuario: str):
    c = app.test_client()
    c.post("/login",
           data={"username": usuario, "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    db.create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("balcao", "QUEM ATENDE", SENHA, "USER")
    return {**cg_casa, "cliente": _entrar(cg_casa["app"], "jean")}


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


TEOR = "AV-06/3.110 — Fica encerrada a escrituracao desta matricula."


def _ficha_com_ato(casa, *, numero=6, selo=None, cancelado=0, encerrada=0):
    """A 3.110 como a producao a deixou: encerrada, e o ato sem selo."""
    from ri_schema import hash_ato
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
                   tipo_ficha, criado_em, encerrada, data_encerramento)
               VALUES ('3110', '2-Q', '2-Q', ?, 'ACERVO', '2026-09-14T10:27',
                       ?, ?)""",
            ("ENCERRADA" if encerrada else "ATIVO", encerrada,
             "2026-09-14" if encerrada else None))
        mid = int(cur.lastrowid)
        h = hash_ato("3110", "AV", numero, "2026-09-14", TEOR, None)
        cur = con.execute(
            """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, teor,
                   teor_formato, cancelado, acervo, origem, hash_ato,
                   lavrado_em, selo_texto)
               VALUES (?, 'AV', ?, '2026-09-14', ?, 'texto', ?, 0, 'MANUAL', ?,
                       '2026-09-14T22:00', ?)""",
            (mid, numero, TEOR, cancelado, h, selo))
        ato_id = int(cur.lastrowid)
    con.close()
    return mid, ato_id


def _selar(casa, mid, ato_id, cliente=None, **campos):
    c = cliente or casa["cliente"]
    html = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    dados = {"csrf_token": _token(html)}
    dados.update(campos)
    return c.post(f"/registro-imoveis/ato/{ato_id}/selar", data=dados,
                  follow_redirects=True)


def _ato(casa, ato_id):
    con = _con(casa)
    r = con.execute("SELECT * FROM ri_atos WHERE id=?", (ato_id,)).fetchone()
    con.close()
    return r


# ------------------------------------------------------------------ o botao



def _so_o_selar(html, ato_id):
    i = html.index(f'id="selar-ato-{ato_id}"')
    return html[i:html.index("</details>", i)]


def test_selar_no_encerramento_tem_item_arquivamento_gratuito_e_reurb(casa):
    mid, ato_id = _ficha_com_ato(casa, encerrada=1)
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    f = _so_o_selar(html, ato_id)
    assert 'name="codigo_tj_selo"' in f                       # item da tabela
    assert 'name="gerar_arquivamento"' in f and 'name="folhas_arquivamento"' in f
    assert 'name="isento"' in f and 'name="motivo_isencao"' in f
    assert 'name="reurb_tipo"' in f
    for op in ('value="S"', 'value="E"', 'value="MISTO"', "REURB-S", "REURB-E", "Misto"):
        assert op in f
    # o aviso da ficha encerrada leva direto ao selar do ato sem selo
    assert f'href="#selar-ato-{ato_id}"' in html and "Selar AV-06" in html


def test_escrevente_humano_tambem_ve(casa):
    mid, ato_id = _ficha_com_ato(casa, encerrada=1)
    c = _entrar(casa["app"], "balcao")
    html = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    f = _so_o_selar(html, ato_id)
    assert 'name="reurb_tipo"' in f and 'name="gerar_arquivamento"' in f


def test_lista_de_matriculas_mostra_encerrada_e_o_atalho(casa):
    mid, ato_id = _ficha_com_ato(casa, encerrada=1)
    html = casa["cliente"].get("/registro-imoveis?busca=3110").get_data(as_text=True)
    assert "Encerrada" in html
    assert f"#selar-ato-{ato_id}" in html and "Selar AV-06" in html


def test_reurb_s_grava_isento_com_motivo_e_arquivamento_espera_o_selo(casa):
    mid, ato_id = _ficha_com_ato(casa, encerrada=1)
    html = _selar(casa, mid, ato_id, natureza_titulo="Encerramento de matrícula",
                  codigo_tj_selo="16.22.2", qtd_selo="1", reurb_tipo="S",
                  gerar_arquivamento="1", folhas_arquivamento="3").get_data(as_text=True)
    a = _ato(casa, ato_id)
    assert a["isento"] == 1
    assert "13.465" in (a["motivo_isencao"] or "")
    assert not a["selo_texto"], "sem selador de ensaio, nada sai"
    assert not a["selo_arquivamento"]
    assert "O selo NÃO saiu" in html
    assert "arquivamento não foi pedido" in html


def test_encerramento_sem_item_sugere_16_22_2(casa):
    mid, ato_id = _ficha_com_ato(casa, encerrada=1)
    con = _con(casa)
    with con:
        con.execute("UPDATE ri_atos SET natureza_titulo='Encerramento de matrícula', "
                    "codigo_tj=NULL WHERE id=?", (ato_id,))
    con.close()
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    f = _so_o_selar(html, ato_id)
    assert 'name="codigo_tj_selo" value="16.22.2"' in f
