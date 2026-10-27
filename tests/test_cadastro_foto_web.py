"""Fotografia do cadastro pela tela do cartao — POST JPEG, arquivo no disco.

O QUE ESTES TESTES GUARDAM
    Que o POST /notas/cartoes/<id>/foto grava o JPEG em disco (a mesma pasta
    das assinaturas) e o SQLite nao recebe o blob. Que corpo vazio recusa em
    portugues, com a mensagem do dominio. Que o GET nao grava nada — nem
    arquivo, nem linha.
"""
from __future__ import annotations

import io
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"
MARCA = b"FOTO-WEB-CARTAO-TESTE-39"


def _jpeg(marca: bytes = MARCA) -> bytes:
    """JPEG minimo com comentario unico — o dominio nao decodifica, so guarda."""
    return b"\xff\xd8\xff\xfe" + bytes([0, 2 + len(marca)]) + marca + b"\xff\xd9"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); cartao+login por teste."""
    d = cg_casa["db"]
    d.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    d.set_settings({"archive_root": str(cg_casa["acervo"])})

    con = sqlite3.connect(cg_casa["banco"])
    con.execute(
        """INSERT INTO nt_cartoes (nome, nome_norm, documento, origem, ativo,
                                   abertura, criado_em)
           VALUES ('MARIA DAS DORES DA SILVA','MARIA DAS DORES DA SILVA',
                   '00000001082','MANUAL',1,'2026-08-31','2026-08-31T19:10:00')""")
    con.commit()
    cartao = con.execute("SELECT id FROM nt_cartoes").fetchone()[0]
    con.close()

    c = cg_casa["cliente"]
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    token = _token(c.get(f"/notas/cartoes/{cartao}").get_data(as_text=True))
    return {**cg_casa, "cartao": cartao, "token": token}


def _post(casa, dados_jpeg: bytes | None, filename="foto.jpg"):
    campos = {"csrf_token": casa["token"]}
    if dados_jpeg is not None:
        campos["foto"] = (io.BytesIO(dados_jpeg), filename)
    return casa["cliente"].post(
        f"/notas/cartoes/{casa['cartao']}/foto",
        data=campos, content_type="multipart/form-data",
        follow_redirects=True)


def _linhas(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    r = list(con.execute(
        "SELECT * FROM nt_cadastro_imagens WHERE cartao_id=? AND especie='FOTO'",
        (casa["cartao"],)))
    con.close()
    return r


def _arquivo(casa) -> Path:
    return (casa["acervo"] / "notas" / "firmas" / str(casa["cartao"]) / "foto.jpg")


# --------------------------------------------------------------- o caminho


def test_o_post_grava_jpeg_no_disco_e_nao_no_sqlite(casa):
    jpeg = _jpeg()
    r = _post(casa, jpeg)
    assert r.status_code == 200
    assert "Fotografia colhida" in r.get_data(as_text=True)

    arquivo = _arquivo(casa)
    assert arquivo.is_file()
    assert arquivo.read_bytes() == jpeg

    linhas = _linhas(casa)
    assert len(linhas) == 1
    assert linhas[0]["nome_arquivo"] == "foto.jpg"
    assert linhas[0]["caminho"] == str(arquivo)
    assert jpeg not in casa["banco"].read_bytes()


def test_a_foto_colhida_e_servida_no_get(casa):
    jpeg = _jpeg()
    _post(casa, jpeg)
    r = casa["cliente"].get(f"/notas/cartoes/{casa['cartao']}/foto")
    assert r.status_code == 200
    assert r.mimetype == "image/jpeg"
    assert r.get_data() == jpeg


def test_a_tela_mostra_a_fotografia_depois_de_colher(casa):
    _post(casa, _jpeg())
    html = casa["cliente"].get(
        f"/notas/cartoes/{casa['cartao']}").get_data(as_text=True)
    assert f"/notas/cartoes/{casa['cartao']}/foto" in html
    assert "Ainda sem fotografia" not in html
    assert "Fotografia" in html
    assert "Colher" in html


def test_a_tela_oferece_colher_e_avisa_a_digitalpersona(casa):
    html = casa["cliente"].get(
        f"/notas/cartoes/{casa['cartao']}").get_data(as_text=True)
    assert "Fotografia" in html
    assert "Colher" in html
    assert 'data-captura-foto' in html
    assert "cadastro_captura.js" in html
    assert "DigitalPersona" in html
    # O leitor deixou de ser «a próxima etapa» em 26/10/2026: a tela tem o
    # quadro dele, com o botão do SDK do fabricante.
    assert "data-leitor-digital" in html
    assert "leitor_digital.js" in html


# ------------------------------------------------------------- o que recusa


def test_corpo_vazio_recusa_em_portugues_e_nao_grava(casa):
    r = _post(casa, None)
    texto = r.get_data(as_text=True).lower()
    assert r.status_code == 200
    assert "vazia" in texto
    assert "webcam" in texto
    assert not _arquivo(casa).exists()
    assert _linhas(casa) == []
    assert MARCA not in casa["banco"].read_bytes()


def test_arquivo_vazio_recusa_em_portugues(casa):
    r = _post(casa, b"")
    texto = r.get_data(as_text=True).lower()
    assert "vazia" in texto
    assert "webcam" in texto
    assert not _arquivo(casa).exists()
    assert _linhas(casa) == []


def test_cartao_que_nao_existe_da_404(casa):
    r = casa["cliente"].post(
        "/notas/cartoes/99999/foto",
        data={"csrf_token": casa["token"],
              "foto": (io.BytesIO(_jpeg()), "foto.jpg")},
        content_type="multipart/form-data")
    assert r.status_code == 404
    assert not (casa["acervo"] / "notas" / "firmas" / "99999" / "foto.jpg").exists()


# ------------------------------------------------------------- GET nao grava


def test_get_nao_grava_foto_nem_linha(casa):
    """Abrir o cartao ou pedir a foto inexistente nao colhe nada."""
    cid = casa["cartao"]
    r = casa["cliente"].get(f"/notas/cartoes/{cid}")
    assert r.status_code == 200
    r2 = casa["cliente"].get(f"/notas/cartoes/{cid}/foto")
    assert r2.status_code == 404
    assert not _arquivo(casa).exists()
    assert _linhas(casa) == []
    assert MARCA not in casa["banco"].read_bytes()


def test_get_depois_de_colher_nao_reescreve_o_arquivo(casa):
    jpeg = _jpeg()
    _post(casa, jpeg)
    arquivo = _arquivo(casa)
    antes = arquivo.read_bytes()
    r = casa["cliente"].get(f"/notas/cartoes/{casa['cartao']}/foto")
    assert r.status_code == 200
    assert arquivo.read_bytes() == antes == jpeg
    r2 = casa["cliente"].get(f"/notas/cartoes/{casa['cartao']}")
    assert r2.status_code == 200
    assert arquivo.read_bytes() == jpeg
    assert jpeg not in casa["banco"].read_bytes()
