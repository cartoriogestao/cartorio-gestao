"""
Testes da PESQUISA AMPLA dos assentos do RCPN (`rc_busca`, 04/11/2026).

O QUE ELES CONFEREM
    - o CAMPO ÚNICO entende o que o balcão digita: `A-3/45`, `livro 3 folha
      45`, `C-5`, `nº 812`, a matrícula com espaços, e nome no meio disso;
    - o LIVRO se compara pela letra e pelo número: `C5`, `C-05` e o `5` que o
      acervo guarda no óbito são o mesmo livro;
    - a folha `45` acha o verso `45v`, e `45v` não acha a frente;
    - acha pelo nome da MÃE, do PAI e do DECLARANTE, sem acento;
    - a RELAÇÃO DO LIVRO vem em ordem de folha e termo;
    - o livro e a folha são os MESMOS que a certidão imprime
      (`rc_certidao.lugar_do_assento`);
    - formulário vazio não lista a casa inteira.

Os testes de banco são do PostgreSQL (CG_TEST_BACKEND=pg), como os da
certidão: `rc_busca` é módulo nativo.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import rc_busca as B

AGORA = "2026-08-26T09:00:00"
EXTENSO = "vinte e seis dias do mês de agosto do ano de dois mil e vinte e seis"
SV = {
    "unit_name": "SERVENTIA EXTRAJUDICIAL DO OFÍCIO ÚNICO DE CIDADE EXEMPLO",
    "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
    "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
}


# ------------------------------------------------- o campo único (puro)


@pytest.mark.parametrize("digitado, esperado", [
    ("A-3/45", {"livro": "A-3", "folha": "45"}),
    ("a-3 / 45 / 120", {"livro": "A-3", "folha": "45", "termo": "120"}),
    ("livro 3 folha 45", {"livro": "3", "folha": "45"}),
    ("Livro A 3 fl. 45 termo 1200", {"livro": "A-3", "folha": "45", "termo": "1200"}),
    ("C-5", {"livro": "C-5"}),
    ("fls:45v", {"folha": "45v"}),
    ("nº 812", {"termo": "812"}),
    ("livro c", {"livro": "C"}),
])
def test_o_campo_unico_entende_livro_folha_e_termo(digitado, esperado):
    r = B.interpretar(digitado)
    for chave in ("livro", "folha", "termo"):
        assert r[chave] == esperado.get(chave), chave
    assert r["palavras"] == []


def test_a_matricula_com_espacos_e_um_numero_so():
    r = B.interpretar("000000 01 55 1997 1 00011 127 0010385 01")
    assert r["matricula"] == "00000001551997100011127001038501"
    assert r["palavras"] == [] and r["numeros"] == []


def test_nome_sai_sem_acento_e_sem_as_palavras_vazias():
    r = B.interpretar("Maria das Graças")
    assert r["palavras"] == ["maria", "gracas"]


def test_nome_e_livro_juntos():
    r = B.interpretar("maria A-3")
    assert r["livro"] == "A-3" and r["palavras"] == ["maria"]


def test_o_e_solto_e_conjuncao_e_nao_o_livro_e():
    r = B.interpretar("joão e maria")
    assert r["livro"] is None
    assert r["palavras"] == ["joao", "maria"]


def test_numero_solto_fica_em_aberto():
    r = B.interpretar("1985")
    assert r["numeros"] == [1985]
    assert "termo, folha, livro ou ano" in r["entendido"][0]


def test_o_livro_se_compara_pela_letra_e_pelo_numero():
    assert B.livro_casa("C5", "5", "C")           # o óbito do acervo: só «5»
    assert B.livro_casa("c-05", "C-5")
    assert B.livro_casa("3", "B-3")               # sem letra, qualquer letra
    assert not B.livro_casa("A-3", "B-3")
    assert not B.livro_casa("A-3", "A-33")
    assert B.livro_casa("A", "A-22")              # só a letra: o livro A todo


def test_a_folha_acha_o_verso_e_o_verso_nao_acha_a_frente():
    assert B.folha_casa("45", "45v")
    assert B.folha_casa("045", "45")
    assert not B.folha_casa("45v", "45")
    assert not B.folha_casa("45", "145")


def test_a_letra_vem_da_serie_e_na_falta_da_especie():
    assert B.letra_da_serie("RC_C") == "C"
    assert B.letra_da_serie(None, "OBITO") == "C"
    assert B.letra_da_serie("", "NASCIMENTO") == "A"


def test_filtros_estranhos_nao_passam():
    f = B.ler_filtros({"especie": "DROP TABLE", "situacao": "x", "ordem": "y",
                       "q": "  maria  "})
    assert f["especie"] == "" and f["situacao"] == "" and f["ordem"] == ""
    assert f["q"] == "maria"


# ------------------------------------------------------- no banco (PG)


def _banco():
    from banco_de_teste import conexao_de_teste

    import rc_certidao as CE
    from nucleo_schema import init_nucleo_schema
    from rc_schema import init_rc_schema
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    init_rc_schema(con)
    CE.init_rc_certidao_schema(con)
    return con


@pytest.fixture
def con():
    import os
    if os.environ.get("CG_TEST_BACKEND", "").strip().lower() != "pg":
        pytest.skip("rc_busca é PostgreSQL nativo: rode com CG_TEST_BACKEND=pg")
    return _banco()


def _pessoa(con, assento_id, papel, nome, ordem=1):
    con.execute(
        """INSERT INTO rc_pessoas(assento_id, papel, nome, ordem, criado_em)
           VALUES (?,?,?,?,?)""", (assento_id, papel, nome, ordem, AGORA))


def _acervo(con, nome, *, especie="NASCIMENTO", serie="RC_A", livro="A-3",
            numero=100, matricula=None, data_fato="1997-03-11", pais=(),
            declarante=None):
    """Assento do ACERVO: sem ato REGISTRO, com volume e (ou) matrícula."""
    cur = con.execute(
        """INSERT INTO rc_assentos(serie, especie, numero, matricula, nome,
                                   data_ato, data_fato, livro_volume, origem,
                                   criado_em)
           VALUES (?,?,?,?,?,?,?,?, 'ARQUIVO', ?) RETURNING id""",
        (serie, especie, numero, matricula, nome, data_fato, data_fato, livro,
         AGORA))
    aid = int(cur.fetchone()[0])
    for i, (papel, quem) in enumerate(pais, start=1):
        _pessoa(con, aid, papel, quem, i)
    if declarante:
        _pessoa(con, aid, "DECLARANTE", declarante, 9)
    return aid


def _ids(resultado):
    return [r["id"] for r in resultado["linhas"]]


def test_acha_pelo_nome_da_mae_sem_acento(con):
    alvo = _acervo(con, "JOÃO PEDRO SOUSA",
                   pais=[("MAE", "MARIA DAS GRAÇAS SOUSA"), ("PAI", "JOSÉ SOUSA")])
    _acervo(con, "OUTRA PESSOA", numero=101, pais=[("MAE", "ANA LIMA")])
    r = B.pesquisar(con, B.ler_filtros({"pais": "maria das gracas"}))
    assert _ids(r) == [alvo]
    linha = r["linhas"][0]
    assert any("MARIA DAS GRAÇAS" in p for p in linha["pais"])
    assert any(a.startswith("Mãe") for a in linha["achado_em"])


def test_acha_pelo_declarante(con):
    alvo = _acervo(con, "CRIANÇA UM", declarante="RAIMUNDO NONATO")
    _acervo(con, "CRIANÇA DOIS", numero=101, declarante="FRANCISCO ALVES")
    r = B.pesquisar(con, B.ler_filtros({"declarante": "raimundo"}))
    assert _ids(r) == [alvo]
    assert r["linhas"][0]["declarante"] == "RAIMUNDO NONATO"


def test_o_pai_nao_casa_no_campo_do_declarante(con):
    _acervo(con, "CRIANÇA", pais=[("PAI", "RAIMUNDO NONATO")])
    assert B.pesquisar(con, B.ler_filtros({"declarante": "raimundo"}))["total"] == 0


def test_o_campo_unico_acha_qualquer_pessoa_do_assento(con):
    alvo = _acervo(con, "JOÃO", pais=[("MAE", "MARIA BONITA")],
                   declarante="TIO PATINHAS")
    r = B.pesquisar(con, B.ler_filtros({"q": "joao bonita"}))
    assert _ids(r) == [alvo]
    r = B.pesquisar(con, B.ler_filtros({"q": "patinhas"}))
    assert _ids(r) == [alvo]


def test_livro_e_folha_pela_matricula_do_acervo(con):
    # livro 9, folha 141, termo 8842 — a mesma matrícula do teste da certidão.
    alvo = _acervo(con, "GUSTAVO", livro="A-9", numero=8842,
                   matricula="00000001551994100009141000884223")
    _acervo(con, "OUTRO", livro="A-9", numero=8843)
    r = B.pesquisar(con, B.ler_filtros({"q": "A-9/141"}))
    assert _ids(r) == [alvo]
    linha = r["linhas"][0]
    assert (linha["livro"], str(linha["folha"]), str(linha["termo"])) == (
        "A-9", "141", "8842")


def test_o_livro_do_obito_sem_letra_acha_por_c5(con):
    alvo = _acervo(con, "FALECIDO", especie="OBITO", serie="RC_C", livro="5")
    _acervo(con, "NASCIDO", livro="5", numero=101)        # A-5, não C-5
    assert _ids(B.pesquisar(con, B.ler_filtros({"livro": "C-05"}))) == [alvo]


def test_a_relacao_do_livro_vem_em_ordem_de_termo(con):
    tres = _acervo(con, "TERCEIRO", numero=3)
    um = _acervo(con, "PRIMEIRO", numero=1)
    dois = _acervo(con, "SEGUNDO", numero=2)
    _acervo(con, "DE OUTRO LIVRO", livro="A-4", numero=1)
    r = B.pesquisar(con, B.ler_filtros({"q": "A-3"}))
    assert r["ordem"] == "livro"
    assert _ids(r) == [um, dois, tres]


def test_o_lugar_e_o_mesmo_da_certidao(con):
    import rc_certidao as CE
    aid = _acervo(con, "GUSTAVO", livro="A-9", numero=8842,
                  matricula="00000001551994100009141000884223")
    lugar = CE.lugar_do_assento(con, aid)
    linha = B.pesquisar(con, B.ler_filtros({"nome": "gustavo"}))["linhas"][0]
    assert linha["livro"] == lugar["livro"]
    assert str(linha["folha"]) == str(lugar["folha"])
    assert str(linha["termo"]) == str(lugar["termo"])


def test_o_registrado_vem_antes_de_quem_so_tem_mae_com_o_nome(con):
    so_mae = _acervo(con, "PEDRO", pais=[("MAE", "MARIA SANTOS")])
    registrada = _acervo(con, "MARIA SANTOS", numero=101)
    r = B.pesquisar(con, B.ler_filtros({"q": "maria santos"}))
    assert _ids(r) == [registrada, so_mae]


def test_numero_solto_acha_termo_e_ano(con):
    termo = _acervo(con, "TERMO 1985", numero=1985, data_fato="2001-01-01")
    ano = _acervo(con, "NASCIDO EM 85", numero=7, data_fato="1985-05-05")
    _acervo(con, "NADA", numero=8, data_fato="1990-01-01")
    r = B.pesquisar(con, B.ler_filtros({"q": "1985"}))
    assert _ids(r) == [termo, ano]       # termo pesa mais que ano


def test_formulario_vazio_nao_lista_a_casa(con):
    _acervo(con, "ALGUEM")
    r = B.pesquisar(con, B.ler_filtros({}))
    assert r["vazio"] and r["linhas"] == []


def test_ano_torto_e_recusado_com_frase(con):
    with pytest.raises(B.BuscaError):
        B.pesquisar(con, B.ler_filtros({"ano": "85"}))


# ------------------------------------------------------------- a tela


@pytest.fixture
def tela(request):
    """O app logado — só no PostgreSQL: sem ele, `create_app` não sobe."""
    import os
    if os.environ.get("CG_TEST_BACKEND", "").strip().lower() != "pg":
        pytest.skip("o app é PostgreSQL nativo: rode com CG_TEST_BACKEND=pg")
    return request.getfixturevalue("cg_casa_logada")


def test_a_tela_abre_vazia_e_explica(tela):
    r = tela["c"].get("/rcpn/pesquisa")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Pesquisa ampla de assentos" in html
    assert 'name="pais"' in html and 'name="declarante"' in html
    assert 'name="livro"' in html and 'name="folha"' in html
    assert "só consulta" in html


def test_a_lista_de_assentos_e_o_menu_levam_a_pesquisa(tela):
    html = tela["c"].get("/rcpn?q=maria").get_data(as_text=True)
    assert "/rcpn/pesquisa?q=maria" in html
    assert "Pesquisa ampla" in html


def test_a_tela_mostra_o_achado(tela):
    db = tela["db"]
    with db.transaction() as con:
        _acervo(con, "JOÃO PEDRO SOUSA", livro="A-3", numero=45,
                pais=[("MAE", "MARIA DAS GRAÇAS SOUSA")],
                declarante="RAIMUNDO NONATO")
    c = tela["c"]
    html = c.get("/rcpn/pesquisa?q=gracas").get_data(as_text=True)
    assert "JOÃO PEDRO SOUSA" in html and "Mãe: MARIA DAS GRAÇAS SOUSA" in html
    html = c.get("/rcpn/pesquisa?livro=A-3").get_data(as_text=True)
    assert "JOÃO PEDRO SOUSA" in html and "RAIMUNDO NONATO" in html
    r = c.get("/rcpn/pesquisa?ano=85")
    assert r.status_code == 200 and "quatro dígitos" in r.get_data(as_text=True)
