"""Toda tela abre numa instalação nova — e não havia varredor para isto.

    «instalação nova nasce funcionando» é regra escrita deste projeto, e até
    07/09/2026 nada a guardava.

O DEFEITO QUE FEZ ESTE ARQUIVO NASCER
    Varrendo as rotas para outra coisa, `/registro-imoveis/delegatarios`
    respondeu **HTTP 500**:

        TypeError: unsupported operand type(s) for -: 'int' and 'NoneType'

    A causa é a que este projeto já conhece por outro nome: **`SUM()` sobre
    zero linhas devolve NULL**, e a tela fazia `acervo.total -
    acervo.com_fecho`. Na produção não aparece — há 1.245 atos com teor —,
    **e aparece exatamente onde ninguém está olhando**: na casa que acabou de
    instalar o sistema.

POR QUE ISTO É UM VARREDOR, E NÃO O CONSERTO DE UMA TELA
    A família é conhecida: `SUM` sem `COALESCE`, `MIN`/`MAX` de tabela vazia,
    divisão por contagem zero, `[0]` de lista vazia. **Todas passam na
    produção e falham na instalação limpa**, e nenhum teste de tela as pega,
    porque os testes de tela montam o dado de que precisam.

    Consertar só o `ri_delegatarios` deixaria a próxima igual — é a decisão de
    `test_debitos_do_balcao.py` («toda rota que grava tem de ter tela») e a do
    varredor das rotas de volta.

O QUE ELE NÃO VARRE, E FICA DITO
    Só as rotas **GET sem parâmetro**: são as 149 que se pode abrir sem
    inventar um `id`. Uma ficha de matrícula pede um número, e um número
    inventado responderia 404 — o que é comportamento certo, e não defeito.
    Cobrir aquelas exigiria semear um ato de cada espécie, que é outro teste.
"""
from __future__ import annotations

import glob
import logging
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"

# **O PISO EXISTE PORQUE VARREDOR QUE DEIXA DE ACHAR PASSA CALADO.** Se uma
# mudança fizer o `url_map` encolher — um blueprint que não carrega, por
# exemplo —, o varredor varreria dez telas e diria «tudo certo».
PISO_DE_TELAS = 140


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    c = cg_casa["c"]
    cg_casa["app"].config["PROPAGATE_EXCEPTIONS"] = False
    cg_casa["db"].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                                SENHA, "ADMIN")
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                      c.get("/login").get_data(as_text=True)).group(1)
    c.post("/login", data={"username": "tabeliao", "password": SENHA,
                           "csrf_token": token}, follow_redirects=True)
    return cg_casa

def _telas(app):
    for r in sorted(app.url_map.iter_rules(), key=lambda x: x.rule):
        if "GET" in r.methods and not r.arguments and r.endpoint != "static":
            yield r


def test_toda_tela_abre_sem_estourar(casa):
    """**O banco está vazio, e é esse o ponto.** Nenhum ato, nenhuma
    matrícula, nenhum lançamento — a casa que acabou de instalar."""
    logging.disable(logging.CRITICAL)
    try:
        quebradas = []
        for r in _telas(casa["app"]):
            try:
                resp = casa["c"].get(r.rule)
                if resp.status_code >= 500:
                    quebradas.append(f"{r.rule} ({r.endpoint}) → "
                                     f"{resp.status_code}")
            except Exception as erro:            # noqa: BLE001
                quebradas.append(f"{r.rule} ({r.endpoint}) → "
                                 f"{type(erro).__name__}: {erro}")
    finally:
        logging.disable(logging.NOTSET)

    assert not quebradas, (
        "estas telas estouram numa instalação nova:\n  "
        + "\n  ".join(quebradas))


def test_o_varredor_nao_deixou_de_achar(casa):
    """**Varredor que deixa de achar passa calado** — e este passaria verde
    varrendo dez telas."""
    quantas = len(list(_telas(casa["app"])))
    assert quantas >= PISO_DE_TELAS, (
        f"o varredor achou {quantas} telas, e o piso é {PISO_DE_TELAS} — "
        f"ou o piso está velho, ou alguma coisa deixou de registrar rotas")


def test_a_tela_dos_delegatarios_e_o_caso_que_fez_este_arquivo(casa):
    """O defeito concreto, guardado pelo nome — como
    `test_problemas_relatados_27_08.py` guarda a frase de cada relato.

    `SUM()` sobre zero linhas devolve NULL, e a tela subtraía dele.
    """
    r = casa["c"].get("/registro-imoveis/delegatarios")
    assert r.status_code == 200
    # e o número que a conta produzia aparece, em vez de estourar
    assert "atos sem fecho no teor" in r.get_data(as_text=True)
