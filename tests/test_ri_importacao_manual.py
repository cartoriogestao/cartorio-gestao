"""A importação manual do RI — pedido do oficial em 14/09/2026, mesmo dia da
importação da matrícula 3110 e dos registros 1198/1243 do Livro 3.

O QUE ESTES TESTES GUARDAM

    **Que é o MESMO caminho de `importar_padrao.py`**, e não uma cópia: o que
    entra por aqui vira acervo (sem número novo, sem folha, sem selo), com a
    mesma chave de origem que impede duplicar.

    **Que só as duas espécies do RI se abrem aqui** — as outras quatro
    continuam em `/importar-padrao`.

    **Que o dinheiro do Livro 3 se digita em reais**, e a conversão para
    centavos é da tela — quem digita não escreve JSON nem centavos à mão.
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


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return achado.group(1) if achado else ""


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    banco = cg_casa["banco"]
    c = cg_casa["c"]
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA,
                                "ADMIN")
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    con = sqlite3.connect(banco)
    con.row_factory = sqlite3.Row
    return {**cg_casa, "con": con}

def _get(casa, especie):
    return casa["c"].get(
        f"/registro-imoveis/importacoes/manual/{especie}"
    ).get_data(as_text=True)


def test_so_as_duas_especies_do_ri_abrem_aqui(casa):
    r = casa["c"].get("/registro-imoveis/importacoes/manual/RCPN_ASSENTO",
                      follow_redirects=True)
    assert "Esta tela só importa matrícula ou registro do Livro 3" in \
        r.get_data(as_text=True)


def test_a_tela_da_matricula_pede_os_campos_medidos(casa):
    html = _get(casa, "RI_MATRICULA")
    assert "campo_numero" in html
    assert "campo_livro" in html
    assert "campo_teor" in html
    assert "campo_valor_reais" not in html, \
        "RI_MATRICULA não tem valor_centavos"


def test_a_tela_do_livro3_oferece_o_valor_em_reais(casa):
    html = _get(casa, "LIVRO3_REGISTRO")
    assert "campo_valor_reais" in html
    assert "campo_natureza" in html
    assert "CEDULA_CREDITO_RURAL" in html, \
        "o vocabulário de natureza não veio do módulo de domínio"


def test_confere_e_depois_importa_a_matricula(casa):
    token = _token(_get(casa, "RI_MATRICULA"))
    r1 = casa["c"].post(
        "/registro-imoveis/importacoes/manual/RI_MATRICULA",
        data={"csrf_token": token, "acao": "conferir",
             "campo_numero": "9001", "campo_livro": "2-Q",
             "campo_folha": "10"})
    html1 = r1.get_data(as_text=True)
    assert "O registro passou na conferência" in html1
    assert 'name="acao" value="importar"' in html1

    token2 = _token(html1)
    m = re.search(r'name="texto_pronto" value="([^"]*)"', html1)
    assert m, "o texto pronto para importar não veio na tela"
    texto_pronto = (m.group(1).replace("&quot;", '"').replace("&#34;", '"')
                   .replace("&amp;", "&"))
    r2 = casa["c"].post(
        "/registro-imoveis/importacoes/manual/RI_MATRICULA",
        data={"csrf_token": token2, "acao": "importar",
             "texto_pronto": texto_pronto},
        follow_redirects=True)
    linha = casa["con"].execute(
        "SELECT numero, origem, criado_por FROM ri_matriculas "
        "WHERE numero='9001'").fetchone()
    assert tuple(linha) == ("9001", "IMPORTACAO", None), \
        "a matrícula não entrou, ou criado_por quebrou a FK de users"


def test_confere_e_importa_o_livro3_com_o_valor_convertido(casa):
    token = _token(_get(casa, "LIVRO3_REGISTRO"))
    r1 = casa["c"].post(
        "/registro-imoveis/importacoes/manual/LIVRO3_REGISTRO",
        data={"csrf_token": token, "acao": "conferir",
             "campo_numero": "5001", "campo_natureza": "CEDULA_CREDITO_RURAL",
             "campo_valor_reais": "23.999,99"})
    html1 = r1.get_data(as_text=True)
    assert "O registro passou na conferência" in html1

    token2 = _token(html1)
    m = re.search(r'name="texto_pronto" value="([^"]*)"', html1)
    texto_pronto = (m.group(1).replace("&quot;", '"').replace("&#34;", '"')
                   .replace("&amp;", "&"))
    casa["c"].post(
        "/registro-imoveis/importacoes/manual/LIVRO3_REGISTRO",
        data={"csrf_token": token2, "acao": "importar",
             "texto_pronto": texto_pronto},
        follow_redirects=True)
    linha = casa["con"].execute(
        "SELECT valor_centavos FROM ra_registros WHERE numero=5001"
    ).fetchone()
    assert linha is not None and linha[0] == 2399999


def test_nao_importa_duas_vezes_o_mesmo_numero(casa):
    for _ in range(2):
        html = _get(casa, "RI_MATRICULA")
        token = _token(html)
        r = casa["c"].post(
            "/registro-imoveis/importacoes/manual/RI_MATRICULA",
            data={"csrf_token": token, "acao": "conferir",
                 "campo_numero": "9002"})
        html = r.get_data(as_text=True)
        token2 = _token(html)
        m = re.search(r'name="texto_pronto" value="([^"]*)"', html)
        if m:
            texto = (m.group(1).replace("&quot;", '"').replace("&#34;", '"')
                     .replace("&amp;", "&"))
            casa["c"].post(
                "/registro-imoveis/importacoes/manual/RI_MATRICULA",
                data={"csrf_token": token2, "acao": "importar",
                     "texto_pronto": texto},
                follow_redirects=True)
    n = casa["con"].execute(
        "SELECT COUNT(*) FROM ri_matriculas WHERE numero='9002'"
    ).fetchone()[0]
    assert n == 1
