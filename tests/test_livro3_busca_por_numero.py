"""Busca do Livro 3 acha pelo numero do registro - nao so pelo titulo."""
from __future__ import annotations
import sqlite3
import sys
from pathlib import Path
import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
SENHA = "Senha#12345"

def _token(html: str):
    import re
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else ""

@pytest.fixture()
def casa(cg_casa):
    c = cg_casa["c"]
    cg_casa["db"].create_user("jean", "JEAN", SENHA, "ADMIN")
    c.post("/login", data={"username": "jean", "password": SENHA,
           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    con = sqlite3.connect(cg_casa["banco"])
    con.execute(
        "INSERT INTO ra_registros (numero, livro, natureza, titulo_numero, "
        "titulo_tipo, situacao, origem, origem_chave, criado_em) VALUES "
        "(1198, '3', 'CEDULA_CREDITO_RURAL', '40/TEST', 'Cedula teste', "
        "'CANCELADO', 'IMPORTACAO', 'L3-1198-test', '2026-09-14T10:00:00')")
    con.commit()
    return cg_casa

def test_busca_do_livro3_acha_pelo_numero(casa):
    html = casa["c"].get("/livro3?q=1198").get_data(as_text=True)
    assert "1198" in html
    assert "CANCELADO" in html
    assert "Nenhum registro" not in html and "nenhum registro" not in html.lower()
