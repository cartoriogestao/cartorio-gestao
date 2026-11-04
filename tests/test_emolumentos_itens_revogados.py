"""ITENS REVOGADOS DA TABELA DO TJMA - aviso no lugar do 0,00 e sem entrar no protocolo.

Caso real (03/11/2026): no calculo de emolumentos, o balcao procurou o 16.30
achando que era o arquivamento do Registro de Imoveis e viu so «0,00». O 16.30
foi revogado (Lei 9.490/2011) e esta na tabela oficial de 2026 (Resolucao-GP
143/2025) com a descricao «Revogado pela Lei ...» e valores zerados; o
arquivamento por folha e' o 16.39 (R$ 6,92).

O revogado e' reconhecido pela DESCRICAO que ja esta na tabela, e
«Revogacao de testamento» (um ato com preco) nao pode ser confundida com ele.
"""
from __future__ import annotations

import sys
from pathlib import Path

import jinja2

import emolumentos as EMOL

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tests"))
from banco_de_teste import conexao_de_teste  # noqa: E402

ZERO = "0,00"
LINHAS = [
    # codigo, codigo_tj, descricao, emolumentos, total
    (1472, "16.30", "Revogado pela Lei nº 9.490, de 04/11/11, pub. D.O.04/11/11", ZERO, ZERO),
    (1500, "16.32", "REVOGADO", ZERO, ZERO),
    (633, "16.39", "Arquivamento, por folha do documento, os emolumentos serão:", "6,17", "6,92"),
    (690, "13.10.4", "Testamento: Revogação de testamento.", "155,90", "174,60"),
]


def _tabela():
    con = conexao_de_teste()
    con.execute("CREATE TABLE cx_vigencias (codigo INTEGER PRIMARY KEY, vigente INTEGER NOT NULL DEFAULT 0)")
    con.execute("""CREATE TABLE cx_servicos (codigo INTEGER PRIMARY KEY, codigo_tj TEXT,
                   descricao TEXT, descricao_norm TEXT, ativo INTEGER NOT NULL DEFAULT 1)""")
    con.execute("""CREATE TABLE cx_servico_valores (servico INTEGER, vigencia INTEGER,
                   emolumentos TEXT, ferc TEXT, femp TEXT, fadep TEXT, ferrfis TEXT, total TEXT)""")
    con.execute("INSERT INTO cx_vigencias (codigo, vigente) VALUES (10022, 1)")
    for codigo, tj, desc, emol, total in LINHAS:
        con.execute("INSERT INTO cx_servicos (codigo, codigo_tj, descricao, descricao_norm, ativo) VALUES (?,?,?,?,1)",
                    (codigo, tj, desc, EMOL._norm(desc)))
        con.execute("INSERT INTO cx_servico_valores VALUES (?,?,?,?,?,?,?,?)",
                    (codigo, 10022, emol, ZERO, ZERO, ZERO, ZERO, total))
    con.commit()
    return con


def test_revogado_vem_da_descricao_e_nao_pega_revogacao():
    assert EMOL.revogado("Revogado pela Lei nº 9.490, de 04/11/11")
    assert EMOL.revogado("  REVOGADO")
    assert not EMOL.revogado("Testamento: Revogação de testamento.")
    assert not EMOL.revogado("Revogação de procuração e de substabelecimento")
    assert not EMOL.revogado("Arquivamento, por folha do documento")
    assert not EMOL.revogado(None)


def test_aviso_do_16_30_aponta_o_16_39_e_os_outros_nao_adivinham():
    a = EMOL.aviso_do_revogado("16.30", "Revogado pela Lei nº 9.490")
    assert a.startswith("REVOGADO \u2013 sem valor") and "16.39" in a and "arquivamento" in a
    assert EMOL.aviso_do_revogado("16.32", "REVOGADO") == "REVOGADO \u2013 sem valor"
    assert EMOL.aviso_do_revogado("16.39", "Arquivamento, por folha") is None


def test_busca_marca_o_revogado_e_nao_marca_o_resto():
    con = _tabela()
    por = {r["codigo_tj"]: r for r in EMOL.buscar(con, "16.3")}
    assert por["16.30"]["revogado"] is True
    assert "16.39" in por["16.30"]["aviso_revogado"]
    assert por["16.39"]["revogado"] is False and por["16.39"]["aviso_revogado"] is None
    tes = EMOL.buscar(con, "testamento")
    assert tes and tes[0]["revogado"] is False


def test_busca_por_arquivamento_acha_o_16_39_com_preco():
    con = _tabela()
    achados = EMOL.buscar(con, "arquivamento")
    assert [r["codigo_tj"] for r in achados] == ["16.39"]
    assert achados[0]["total"] == "6,92"


def test_calcular_item_do_revogado_traz_a_descricao_para_a_rota_barrar():
    con = _tabela()
    item = EMOL.calcular_item(con, servico=1472)
    assert item["origem_valor"] == "TABELA"
    assert EMOL.aviso_do_revogado(item["codigo_tj"], item["descricao"])


def _env():
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(RAIZ / "templates")))
    env.globals["url_for"] = lambda *a, **k: "/x"
    env.globals["csrf_token"] = "t"
    return env


def test_lista_do_protocolo_nao_oferece_acrescentar_no_revogado():
    con = _tabela()
    achados = EMOL.buscar(con, "16.30")
    html = _env().from_string(
        '{% import "_atos_da_tabela.html" as T with context %}{{ T.lista(achados, 1, "16.30") }}'
    ).render(achados=achados)
    assert "data-revogado" in html and "16.39" in html
    assert "acrescentar</button>" not in html