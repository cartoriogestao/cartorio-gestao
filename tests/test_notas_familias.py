"""Integração compartilhada de Escrituras e Atas notariais."""

from __future__ import annotations

import re
import sqlite3
from io import BytesIO

import pytest

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado
    return achado.group(1)


@pytest.fixture()
def serventia(cg_casa):
    cg_casa["db"].create_user("tabeliao", "TABELIÃO TESTE", SENHA, "ADMIN")
    login = cg_casa["c"].get("/login").get_data(as_text=True)
    cg_casa["c"].post("/login", data={
        "username": "tabeliao", "password": SENHA,
        "csrf_token": _token(login),
    }, follow_redirects=True)
    return cg_casa


def _abrir_ata(s, modelo="NT-ATA-NOTARIAL", tipo="ATA") -> int:
    c = s["c"]
    html = c.get(f"/notas/atos/novo?familia=atas&modelo={modelo}").get_data(as_text=True)
    c.post("/notas/atos/novo", data={
        "csrf_token": _token(html), "familia": "atas", "tipo": tipo,
        "modelo_codigo": modelo, "interessado": "PARTE DA ATA",
    }, follow_redirects=True)
    with sqlite3.connect(s["banco"]) as con:
        return int(con.execute("SELECT MAX(id) FROM nt_atos").fetchone()[0])


def test_escrituras_e_atas_usam_o_mesmo_painel_de_familia(serventia):
    atas = serventia["c"].get("/notas/atas").get_data(as_text=True)
    escrituras = serventia["c"].get("/notas/escrituras").get_data(as_text=True)
    assert "Um único fluxo de instrumentos notariais" in atas
    assert "Um único fluxo de instrumentos notariais" in escrituras
    assert "NT-ATA-NOTARIAL" in atas and "NT-ATA-USUCAPIAO" in atas
    assert "NT-ESC-COMPRA-VENDA" in escrituras
    assert "Pendências específicas" in escrituras


def test_abertura_de_ata_filtra_modelos_e_obedece_ao_tipo_do_modelo(serventia):
    c = serventia["c"]
    html = c.get(
        "/notas/atos/novo?familia=atas&modelo=NT-ATA-USUCAPIAO"
    ).get_data(as_text=True)
    assert "NT-ATA-USUCAPIAO" in html
    assert "NT-ESC-COMPRA-VENDA" not in html
    assert 'value="NT-ATA-USUCAPIAO"' in html and "selected" in html

    # Mesmo adulterando o select para ESCRITURA, o modelo leva ao livro certo.
    c.post("/notas/atos/novo", data={
        "csrf_token": _token(html), "familia": "atas", "tipo": "ESCRITURA",
        "modelo_codigo": "NT-ATA-USUCAPIAO", "interessado": "USUCAPIENTE",
    }, follow_redirects=True)
    with sqlite3.connect(serventia["banco"]) as con:
        linha = con.execute(
            "SELECT tipo, serie FROM nt_atos ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert linha == ("ATA_USUCAPIAO", "ATA")


def test_lista_da_familia_reune_as_duas_especies_de_ata(serventia):
    _abrir_ata(serventia, "NT-ATA-NOTARIAL", "ATA")
    _abrir_ata(serventia, "NT-ATA-USUCAPIAO", "ATA_USUCAPIAO")
    html = serventia["c"].get("/notas/atos?familia=atas").get_data(as_text=True)
    assert "Ata notarial" in html
    assert "Ata notarial para usucapião extrajudicial" in html


def test_ata_exige_descricao_e_exibe_evidencia_com_hash(serventia):
    ato_id = _abrir_ata(serventia)
    c = serventia["c"]
    pagina = c.get(f"/notas/atos/{ato_id}").get_data(as_text=True)
    assert "Conferência jurídica do modelo" in pagina
    assert "Evidências da constatação" in pagina

    recusada = c.post(f"/notas/atos/{ato_id}/anexos", data={
        "csrf_token": _token(pagina),
        "arquivo": (BytesIO("imagem-probatória".encode()), "captura.txt"),
        "descricao": "",
    }, content_type="multipart/form-data", follow_redirects=True)
    assert "descreva o que o arquivo comprova" in recusada.get_data(as_text=True)

    pagina = c.get(f"/notas/atos/{ato_id}").get_data(as_text=True)
    aceita = c.post(f"/notas/atos/{ato_id}/anexos", data={
        "csrf_token": _token(pagina),
        "arquivo": (BytesIO("imagem-probatória".encode()), "captura.txt"),
        "descricao": "Tela consultada no balcão às 14h30",
    }, content_type="multipart/form-data", follow_redirects=True)
    html = aceita.get_data(as_text=True)
    assert "captura.txt" in html
    assert "Tela consultada no balcão às 14h30" in html
    assert "SHA-256" in html and "ver" in html and "baixar" in html
