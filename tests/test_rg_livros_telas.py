"""AS ABAS DOS LIVROS DO RCPJ E DO RTD, pela tela (01/11/2026).

A aba do Protocolo nasceu dando erro 500, por um filtro de molde, com todos os testes de
domínio passando: só a tela pegava. Por isso cada aba se abre aqui, com dado e sem dado.
Dados fictícios.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rg_livros as RGL
import rg_titulo as TIT


def _token(html: str) -> str:
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else ""


@pytest.fixture()
def casa(cg_casa_logada):
    return cg_casa_logada


def _registro(casa, serie="TD_B", atribuicao=4, numero=7) -> int:
    con = sqlite3.connect(casa["banco"])
    con.execute(
        """INSERT INTO rg_registros(atribuicao, serie, numero, requerente_nome, situacao, origem,
               origem_chave, criado_em)
           VALUES (?,?,?,'José Exemplo','ATIVO','TESTE',?,'2026-11-01T09:00:00')""",
        (atribuicao, serie, numero, f"t:{serie}:{numero}"))
    registro_id = con.execute("SELECT id FROM rg_registros WHERE origem_chave=?",
                              (f"t:{serie}:{numero}",)).fetchone()[0]
    con.commit()
    con.close()
    return int(registro_id)


@pytest.mark.parametrize("atribuicao", TIT.ATRIBUICOES)
def test_toda_aba_abre_vazia(casa, atribuicao):
    for livro in RGL.livros_de(atribuicao):
        r = casa["c"].get(f"/rcpj-rtd/livros?atribuicao={atribuicao}&livro={livro['chave']}")
        assert r.status_code == 200, livro["chave"]
        assert livro["fonte"] in r.get_data(as_text=True)


def test_o_protocolo_mostra_o_pendente_no_alto_e_o_recibo_abre(casa):
    c = casa["c"]
    html = c.get("/rcpj-rtd/titulos/novo?atribuicao=4").get_data(as_text=True)
    r = c.post("/rcpj-rtd/titulos/novo", data={
        "csrf_token": _token(html), "atribuicao": "4", "data_apresentacao": "2026-11-01",
        "apresentante": "Maria Exemplo", "natureza": "Contrato de locação",
        "especie_lancamento": "INTEGRAL", "previsao_entrega": "2026-11-10"})
    assert r.status_code == 302
    titulo = r.headers["Location"].rstrip("/").split("/")[-1]
    pagina = c.get("/rcpj-rtd/livros?atribuicao=4&livro=a").get_data(as_text=True)
    assert pagina.index("Esperando lançamento") < pagina.index("Maria Exemplo", pagina.index("lançamento(s)"))
    assert "Registro integral" in pagina
    recibo = c.get(f"/rcpj-rtd/titulo/{titulo}/recibo").get_data(as_text=True)
    assert "para registro integral" in recibo and "10/11/2026" in recibo
    assert "cg-regua" not in recibo


def test_a_parte_incluida_na_ficha_aparece_no_livro_d(casa):
    c = casa["c"]
    registro = _registro(casa)
    ficha = c.get(f"/rcpj-rtd/{registro}").get_data(as_text=True)
    assert f"/rcpj-rtd/{registro}/partes" in ficha and f"/rcpj-rtd/{registro}/bens" in ficha
    r = c.post(f"/rcpj-rtd/{registro}/partes", data={
        "csrf_token": _token(ficha), "nome": "Conceição Exemplo", "papel": "Cônjuge"})
    assert r.status_code == 302
    pagina = c.get("/rcpj-rtd/livros?atribuicao=4&livro=d&busca=conceicao").get_data(as_text=True)
    assert "Conceição Exemplo" in pagina and "Cônjuge" in pagina


def test_o_rcpj_nao_oferece_o_livro_e(casa):
    registro = _registro(casa, serie="PJ_A", atribuicao=3, numero=8)
    assert f"/rcpj-rtd/{registro}/bens" not in casa["c"].get(f"/rcpj-rtd/{registro}").get_data(as_text=True)


def test_o_papel_do_livro_sai_em_odt(casa):
    r = casa["c"].get("/rcpj-rtd/livros?atribuicao=4&livro=d&formato=odt")
    assert r.status_code == 200
    assert r.mimetype == "application/vnd.oasis.opendocument.text"


def test_a_lista_do_que_conferir_e_o_nome_reservado(casa):
    pagina = casa["c"].get("/rcpj-rtd/o-que-conferir?atribuicao=3&nome=Cart%C3%B3rio%20Exemplo").get_data(as_text=True)
    assert "CN-MA art. 407, IV" in pagina and "Palavra reservada" in pagina
