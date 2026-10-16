"""Prévia de anotação a partir do HTML da CRC — offline, sem escrever na margem.

O QUE ESTES TESTES GUARDAM
    Que o HTML de exemplo da CRC rende casamento e óbito com código, nome,
    livro, folha e termo — sem inventar número que o arquivo não trouxe.

    Que os três modelos geram texto com o código e o nome do óbito.

    Que a tela só mostra prévia: POST com o fixture devolve o texto, e o
    módulo não importa urllib/requests (não chama a internet).
"""
from __future__ import annotations

import glob
import io
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rc_anotacao_crc as CRC  # noqa: E402

SENHA = "Senha#12345"
FIXTURE = RAIZ / "tests" / "fixtures" / "crc_comunicacoes_exemplo.html"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    c = cg_casa["cliente"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _html():
    return FIXTURE.read_text(encoding="utf-8")


# ------------------------------------------------ parse


def test_fixture_existe():
    assert FIXTURE.is_file()


def test_ler_arquivo_acha_casamento_e_obito():
    comuns = CRC.ler_arquivo(_html())
    tipos = {c["tipo"] for c in comuns}
    assert "CASAMENTO" in tipos
    assert "OBITO" in tipos
    assert len(comuns) >= 2


def test_obito_traz_codigo_nome_livro_folha_termo():
    comuns = CRC.ler_arquivo(_html())
    ob = next(c for c in comuns if c["codigo"] == "90000049")
    assert ob["tipo"] == "OBITO"
    assert "JOÃO MODELO SANTOS" in ob["nome_principal"]
    assert ob["livro"] == "C 002"
    assert ob["folhas"] == "011"
    assert ob["termo"] == "0003001"
    assert ob["data_fato"] == "01/04/2026"
    assert "Serventia Modelo" in ob["origem_serventia"]


def test_casamento_traz_conjuges_e_rename():
    comuns = CRC.ler_arquivo(_html())
    cas = next(c for c in comuns if c["codigo"] == "90000001")
    assert cas["tipo"] == "CASAMENTO"
    assert cas["livro"] == "B 001"
    assert cas["folhas"] == "010"
    assert cas["termo"] == "0001001"
    assert "MARIA EXEMPLO DA SILVA" in cas["conjuges"]
    assert any("passou a assinar" in x for x in cas["rename_frases"])


def test_html_vazio_erra():
    with pytest.raises(CRC.AnotacaoCrcError):
        CRC.ler_arquivo("")
    with pytest.raises(CRC.AnotacaoCrcError):
        CRC.ler_arquivo("<html><body>sem comunicação</body></html>")


# ------------------------------------------------ modelos


def test_tres_modelos_geram_texto_com_codigo_e_nome():
    comuns = CRC.ler_arquivo(_html())
    ob = next(c for c in comuns if c["codigo"] == "90000049")
    for mid in ("compacto", "completo", "fe_publica"):
        r = CRC.gerar([ob], mid, hoje="2026-09-07",
                      cidade_destino="Cidade Exemplo",
                      assinatura="Fulano, Escrevente")
        assert r["ok"]
        assert r["texto"].strip()
        assert "90000049" in r["texto"]
        assert "JOÃO MODELO SANTOS" in r["texto"]


def test_filtro_especie_obito():
    comuns = CRC.ler_arquivo(_html())
    r = CRC.gerar(comuns, "compacto", hoje="2026-09-07", especie="OBITO")
    assert all(i["tipo"] == "OBITO" for i in r["itens"])
    assert any(i["codigo"] == "90000049" for i in r["itens"])


def test_modelo_desconhecido_erra():
    with pytest.raises(CRC.AnotacaoCrcError):
        CRC.gerar([{"tipo": "OBITO", "codigo": "1"}], "xyz")


# ------------------------------------------------ sem internet


def test_modulo_nao_chama_a_rede():
    """O docstring pode citar urllib; o que não pode é importar ou usar."""
    codigo = (RAIZ / "rc_anotacao_crc.py").read_text(encoding="utf-8")
    for proibido in ("urllib", "requests", "http.client", "httpx", "aiohttp"):
        assert f"import {proibido}" not in codigo, f"importou {proibido}"
        assert f"from {proibido}" not in codigo, f"from {proibido}"
    assert "INSERT INTO rc_assentos" not in codigo
    assert "UPDATE rc_assentos" not in codigo


# ------------------------------------------------ HTTP


def test_get_tela_200(casa):
    r = casa["cliente"].get("/rcpn/anotacoes/crc")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Anotação da CRC" in html
    assert "não anota sozinho" in html.lower() or "não anota sozinho" in html
    assert "csrf_token" in html


def test_post_fixture_devolve_previa(casa):
    token = _token(casa["cliente"].get("/rcpn/anotacoes/crc").get_data(as_text=True))
    dados = {
        "csrf_token": token,
        "modelo": "compacto",
        "especie": "OBITO",
        "cidade_destino": "Cidade Exemplo",
        "assinatura": "Escrevente",
        "arquivo": (io.BytesIO(_html().encode("utf-8")), "crc.html"),
    }
    r = casa["cliente"].post("/rcpn/anotacoes/crc", data=dados,
                             content_type="multipart/form-data",
                             follow_redirects=True)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "90000049" in html
    assert "JOÃO MODELO SANTOS" in html
