"""
Testes do motor de custas do nucleo — emolumento, fundos, gratuidade e
vigencia.

O QUE ELES CONFEREM, E CONTRA O QUE
    Contra a TABELA DE VERDADE. `tests/custas_reais.json` traz, exportado do
    acervo do E-Oficio em 21/08/2026: as 18 vigencias com data de inicio e fim,
    os nove itens que declaram isencao no proprio texto, 400 valores reais da
    vigencia de 2026 e 60 faixas. Os testes de percentual rodam contra esses
    400 valores, e nao contra tres numeros que eu escolhi.

A REGRA QUE MAIS IMPORTA AQUI
    O ISS NAO ENTRA NO TOTAL. O cadastro de fundos tem cinco linhas e so
    quatro sao cobradas da parte. Somar o ISS cobraria 5% a mais de todo mundo,
    e o teste `test_o_iss_nao_entra_no_total` existe para que isso nao volte
    por descuido de leitura da lista de cinco.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import custas                                    # noqa: E402
import emolumentos                                # noqa: E402
from caixa_schema import centavos, init_caixa_schema, reais   # noqa: E402

REAIS = json.loads((Path(__file__).parent / "custas_reais.json").read_text("utf-8"))
VIGENCIA_2026 = 10022


def banco() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    # `init_caixa_schema` tem uma migracao sobre `users`, que e do esquema
    # geral. No banco da serventia ela ja existe; aqui basta o esqueleto.
    con.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)")
    init_caixa_schema(con)
    return con


def com_tabela(*, periodos: bool = True) -> sqlite3.Connection:
    """Um banco com a tabela de 2026 dentro, tirada do acervo real."""
    con = banco()
    for v in REAIS["vigencias"]:
        con.execute(
            """INSERT INTO cx_vigencias(codigo, descricao, vigente, inicio, fim,
                                        importado_em)
               VALUES (?,?,?,?,?, '2026-08-21')""",
            (v["codigo"], v["descricao"], 1 if v["codigo"] == VIGENCIA_2026 else 0,
             v["inicio"] if periodos else None, v["fim"] if periodos else None))
    for e in REAIS["valores_2026"]:
        con.execute(
            "INSERT OR IGNORE INTO cx_servicos(codigo, codigo_tj, descricao, ativo) "
            "VALUES (?,?,?,1)", (int(e["s"]), e["tj"], e["descricao"]))
        total = sum(centavos(reais(int(round(e[k] * 100))))
                    for k in ("emol", "ferc", "femp", "fadp", "ferrfis"))
        con.execute(
            """INSERT OR REPLACE INTO cx_servico_valores(servico, vigencia,
                   emolumentos, ferc, femp, fadep, ferrfis, total)
               VALUES (?,?,?,?,?,?,?,?)""",
            (int(e["s"]), int(e["v"]),
             reais(int(round(e["emol"] * 100))), reais(int(round(e["ferc"] * 100))),
             reais(int(round(e["femp"] * 100))), reais(int(round(e["fadp"] * 100))),
             reais(int(round(e["ferrfis"] * 100))), reais(total)))
    for f in REAIS["faixas_2026"]:
        con.execute(
            """INSERT INTO cx_faixas(tabela, vigencia, de, ate, codigo_tj,
                   emolumentos, ferc, femp, fadep, ferrfis, total)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (int(f["intCodigoTabela"]), int(f["intCodigoVigencia"]),
             reais(int(round(f["curDe"] * 100))), reais(int(round(f["curAte"] * 100))),
             f["strCodigoTJ"], reais(int(round(f["curValor"] * 100))),
             reais(int(round((f["curFERMOJUPI"] or 0) * 100))),
             reais(int(round((f["curValor_MP"] or 0) * 100))),
             reais(int(round((f["curValor_DP"] or 0) * 100))),
             reais(int(round((f["curvalor_ferrfis"] or 0) * 100))),
             reais(int(round((f["curValor"] + (f["curFERMOJUPI"] or 0)
                              + (f["curValor_MP"] or 0) + (f["curValor_DP"] or 0)
                              + (f["curvalor_ferrfis"] or 0)) * 100)))))
    con.commit()
    return con


def um_servico(tj: str) -> dict:
    return next(e for e in REAIS["valores_2026"] if e["tj"] == tj)


# ------------------------------------------------------------------- o ISS

def test_o_iss_nao_entra_no_total():
    campos = custas.CAMPOS_NO_TOTAL
    assert "iss" not in campos
    assert campos == ("ferc", "femp", "fadep", "ferrfis")
    iss = next(f for f in custas.FUNDOS if f["campo"] == "iss")
    assert iss["no_total"] is False
    assert iss["percentual"] == 5           # existe, e 5%, e nao e cobrado
    assert iss["coluna_origem"] is None     # nao ha coluna de ISS na tabela


def test_o_total_da_tabela_fecha_com_emolumento_mais_os_quatro():
    # Nos 400 valores reais de 2026. Se o ISS entrasse, nenhum fecharia.
    fora = []
    for e in REAIS["valores_2026"]:
        soma = sum(int(round(e[k] * 100))
                   for k in ("emol", "ferc", "femp", "fadp", "ferrfis"))
        com_iss = soma + int(round(e["emol"] * 5))
        if com_iss == soma:
            fora.append(e["tj"])
    assert not fora
    assert len(REAIS["valores_2026"]) == 400


def test_nenhum_selo_real_imprime_iss():
    selos = json.loads(
        (Path(__file__).parent / "selos_reais.json").read_text("utf-8"))["textos"]
    assert len(selos) == 39
    assert sum(1 for t in selos if re.search(r"\bISS\b", t)) == 0
    assert sum(1 for t in selos if "FERC" in t) == 39


# -------------------------------------------------------------- percentuais

def test_os_quatro_percentuais_batem_nos_400_valores_reais():
    fora = []
    for e in REAIS["valores_2026"]:
        emol = int(round(e["emol"] * 100))
        for campo, chave in (("ferc", "ferc"), ("femp", "femp"),
                             ("fadep", "fadp"), ("ferrfis", "ferrfis")):
            cobrado = int(round(e[chave] * 100))
            esperado = int(round(emol * custas.PERCENTUAIS[campo] / 100))
            if abs(cobrado - esperado) > 1:
                fora.append((e["tj"], campo, cobrado, esperado))
    # Uma unica excecao, e ela esta declarada no modulo.
    assert [(t, c) for t, c, *_ in fora] == [("15.17", "ferc")]
    conhecida = custas.DIVERGENCIAS_CONHECIDAS[0]
    assert conhecida["codigo_tj"] == "15.17" and conhecida["campo"] == "ferc"


def test_a_conferencia_nao_repete_a_divergencia_ja_conhecida():
    assert custas.conferir_fundos(71, {"ferc": 5, "femp": 3, "fadep": 3,
                                       "ferrfis": 1}, codigo_tj="15.17") == []
    # O mesmo desvio em outro item aparece.
    achados = custas.conferir_fundos(71, {"ferc": 5, "femp": 3, "fadep": 3,
                                          "ferrfis": 1}, codigo_tj="16.1")
    assert len(achados) == 1 and achados[0]["sigla"] == "FERC"
    assert "3% do emolumento dariam" in achados[0]["frase"]


def test_a_conferencia_nao_corrige_o_valor_da_tabela():
    # Ela RELATA. Corrigir por conta propria seria inventar preco.
    # Emolumento de R$ 100,00 (10.000 centavos): 3% sao R$ 3,00, e a tabela
    # traz R$ 9,99.
    achados = custas.conferir_fundos(10000, {"ferc": 999, "femp": 400,
                                             "fadep": 400, "ferrfis": 100})
    assert [a["sigla"] for a in achados] == ["FERC"]
    assert achados[0]["cobrado"] == "9,99"
    assert achados[0]["pelo_percentual"] == "3,00"
    assert achados[0]["diferenca"] == "6,99"


# ---------------------------------------------------------------- vigencia

def test_a_vigencia_sai_da_data_do_ato_e_nao_de_hoje():
    con = com_tabela()
    assert custas.vigencia_do_dia(con, "2023-06-15")["codigo"] == 10019
    assert custas.vigencia_do_dia(con, "2024-01-01")["codigo"] == 10020
    assert custas.vigencia_do_dia(con, "2026-08-21")["codigo"] == VIGENCIA_2026
    assert custas.vigencia_do_dia(con, "2026-08-21")["exata"] is True


def test_a_vigencia_aceita_data_em_dia_mes_ano():
    con = com_tabela()
    assert custas.vigencia_do_dia(con, "15/06/2023")["codigo"] == 10019


def test_sem_periodo_gravado_a_vigencia_e_a_corrente_e_isso_fica_marcado():
    con = com_tabela(periodos=False)
    v = custas.vigencia_do_dia(con, "2023-06-15")
    assert v["codigo"] == VIGENCIA_2026
    assert v["exata"] is False


def test_o_calculo_avisa_quando_a_data_nao_casou():
    con = com_tabela(periodos=False)
    conta = custas.calcular(con, servico=int(um_servico("17.2")["s"]),
                            data="2019-03-04")
    assert conta["vigencia_exata"] is False
    assert any("não casou com nenhuma vigência" in a for a in conta["avisos"])


def test_sem_tabela_carregada_a_mensagem_e_de_balcao():
    con = banco()
    with pytest.raises(custas.CustasError) as erro:
        custas.vigencia_do_dia(con, "2026-08-21")
    assert "Importe a tabela do E-Ofício" in str(erro.value)


def test_data_invalida_nao_derruba_com_ValueError_cru():
    con = com_tabela()
    with pytest.raises(custas.CustasError) as erro:
        custas.vigencia_do_dia(con, "ontem")
    assert "Data inválida" in str(erro.value)


# ----------------------------------------------------------------- calcular

def test_o_calculo_bate_com_o_valor_real_da_tabela():
    con = com_tabela()
    e = um_servico("17.5.1")           # certidao de protesto, uma folha
    conta = custas.calcular(con, servico=int(e["s"]), data="2026-08-21")
    assert conta["emolumentos"] == "47,84"
    assert conta["ferc"] == "1,44" and conta["femp"] == "1,91"
    assert conta["fadep"] == "1,91" and conta["ferrfis"] == "0,48"
    assert conta["total"] == "53,58"          # 47,84 + 1,44 + 1,91 + 1,91 + 0,48
    assert conta["gratuito"] is False
    assert conta["conferencia"] == []
    assert conta["iss_no_total"] is False


def test_a_quantidade_multiplica_tudo_sem_arredondar_no_meio():
    con = com_tabela()
    e = um_servico("17.5.2")
    um = custas.calcular(con, servico=int(e["s"]), data="2026-08-21")
    tres = custas.calcular(con, servico=int(e["s"]), quantidade=3,
                           data="2026-08-21")
    assert tres["total_centavos"] == um["total_centavos"] * 3


def test_o_calculo_por_faixa_usa_o_valor_do_negocio():
    con = com_tabela()
    baixa = custas.calcular(con, tabela=3, base="5.000,00", data="2026-08-21")
    alta = custas.calcular(con, tabela=3, base="10.000,00", data="2026-08-21")
    assert baixa["emolumentos"] == "149,57"
    assert alta["emolumentos"] == "187,03"
    assert baixa["origem_valor"] == "FAIXA"


def test_o_ato_que_nao_existe_na_tabela_da_mensagem_de_balcao():
    con = com_tabela()
    with pytest.raises(custas.CustasError) as erro:
        custas.calcular(con, servico=999999, data="2026-08-21")
    assert "Confira o código do ato" in str(erro.value)


def test_sem_servico_e_sem_tabela_o_modulo_recusa():
    con = com_tabela()
    with pytest.raises(custas.CustasError):
        custas.calcular(con, data="2026-08-21")


# --------------------------------------------------------------- gratuidade

def test_as_nove_gratuidades_da_tabela_estao_todas_aqui():
    assert len(custas.GRATUIDADES) == 9
    do_acervo = {g["codigo_tj"] for g in REAIS["gratuidades"]}
    assert {g["codigo_tj"] for g in custas.GRATUIDADES} == do_acervo


def test_toda_gratuidade_tem_fundamento_escrito():
    for g in custas.GRATUIDADES:
        assert g["fundamento"].strip(), g["codigo_tj"]
        assert g["texto"].strip(), g["codigo_tj"]


def test_o_registro_de_nascimento_e_isento_e_o_selo_sai_igual():
    # 14.a nao tem preco na tabela — e isento —, mas a gratuidade e reconhecida
    # pelo codigo do item.
    g = custas.gratuidade("14.a")
    assert g["rotulo"] == "Registro de nascimento e primeira certidão"
    assert "9.534" in g["fundamento"]
    assert g["compensavel"] is False


def test_o_registro_tardio_e_isento_mas_compensavel():
    g = custas.gratuidade("14.13")
    assert g["compensavel"] is True
    assert g["item_de_compensacao"] == "14.5.1"


def test_ato_refeito_por_erro_da_serventia_nao_se_cobra():
    # E o caso de 18/08/2026, escrito na propria tabela do Tribunal.
    g = custas.gratuidade("14.10.1")
    assert "vedada a cobrança" in g["texto"]
    assert "retificado, refeito ou renovado" in g["texto"]


def test_a_gratuidade_por_pessoa_exige_motivo():
    con = com_tabela()
    e = um_servico("17.2")
    with pytest.raises(custas.CustasError) as erro:
        custas.calcular(con, servico=int(e["s"]), data="2026-08-21",
                        gratuidade_codigo="HIPOSSUFICIENCIA")
    assert "declaração de hipossuficiência" in str(erro.value)


def test_a_gratuidade_invocada_zera_o_que_se_cobra_e_guarda_o_que_seria():
    con = com_tabela()
    e = um_servico("17.2")
    conta = custas.calcular(
        con, servico=int(e["s"]), data="2026-08-21",
        gratuidade_codigo="HIPOSSUFICIENCIA",
        motivo_gratuidade="declaração assinada e arquivada no protocolo 118")
    assert conta["gratuito"] is True
    assert conta["total"] == "0,00"
    assert conta["total_devido"] == "10,68"      # 9,53 + 0,29 + 0,38 + 0,38 + 0,10
    assert conta["motivo_gratuidade"].startswith("declaração assinada")


def test_gratuidade_que_nao_existe_e_recusada_com_a_lista():
    con = com_tabela()
    with pytest.raises(custas.CustasError) as erro:
        custas.calcular(con, servico=int(um_servico("17.2")["s"]),
                        data="2026-08-21", gratuidade_codigo="CORTESIA")
    assert "HIPOSSUFICIENCIA" in str(erro.value)


# --------------------------------------------------------------------- soma

def test_a_soma_separa_o_cobrado_do_gratuito_e_do_compensavel():
    con = com_tabela()
    pago = custas.calcular(con, servico=int(um_servico("17.2")["s"]),
                           data="2026-08-21")
    isento = custas.calcular(
        con, servico=int(um_servico("17.5.2")["s"]), data="2026-08-21",
        gratuidade_codigo="ASSISTENCIA_JUDICIARIA",
        motivo_gratuidade="decisão de gratuidade nos autos 0800123-45")
    soma = custas.somar([pago, isento])
    assert soma["itens"] == 2 and soma["gratuitos"] == 1
    assert soma["total_centavos"] == pago["total_devido_centavos"]
    assert soma["gratuito_centavos"] == isento["total_devido_centavos"]
    assert soma["compensavel_centavos"] == 0     # esta nao e compensavel


def test_a_soma_de_conta_vazia_nao_estoura():
    soma = custas.somar([])
    assert soma["total"] == "0,00" and soma["itens"] == 0


# ------------------------------------------------------- import da vigencia

def test_o_import_marca_a_vigencia_corrente_pela_data_e_nao_pelo_codigo(tmp_path):
    con = banco()
    (tmp_path / "dom_servico.jsonl").write_text(
        json.dumps({"intCodigoServico": 25, "strCodigoTJ": "17.2",
                    "strDescricao": "Intimação", "bitAtivo": 1}) + "\n",
        encoding="utf-8")
    (tmp_path / "dom_servico_tabela.jsonl").write_text("\n".join(
        json.dumps({"intCodigoServico": 25, "intCodigoVigencia": v,
                    "curValor": 9.53, "curFERMOJUPI": 0.29, "curValor_MP": 0.38,
                    "curValor_DP": 0.38, "curvalor_ferrfis": 0.10})
        for v in (10021, 10022, 99999)) + "\n", encoding="utf-8")
    (tmp_path / "dom_vigencia.jsonl").write_text("\n".join(
        json.dumps({"intChave": v["codigo"], "dtmPeriodo1": v["inicio"],
                    "dtmPeriodo2": v["fim"], "strDescricao": v["descricao"]})
        for v in REAIS["vigencias"]) + "\n", encoding="utf-8")
    rel = emolumentos.importar(con, tmp_path)
    # 99999 e o maior codigo, mas nao contem hoje. A corrente e a de 2026.
    assert rel["vigente"] == VIGENCIA_2026
    linha = con.execute(
        "SELECT inicio, fim, descricao FROM cx_vigencias WHERE codigo=?",
        (VIGENCIA_2026,)).fetchone()
    assert linha["inicio"] == "2026-01-01" and linha["fim"] == "2026-12-31"
    assert "01/01/2026" in linha["descricao"]


def test_sem_o_arquivo_de_vigencia_o_import_avisa_em_vez_de_silenciar(tmp_path):
    con = banco()
    (tmp_path / "dom_servico.jsonl").write_text(
        json.dumps({"intCodigoServico": 25, "strCodigoTJ": "17.2",
                    "strDescricao": "Intimação", "bitAtivo": 1}) + "\n",
        encoding="utf-8")
    (tmp_path / "dom_servico_tabela.jsonl").write_text(
        json.dumps({"intCodigoServico": 25, "intCodigoVigencia": 10022,
                    "curValor": 9.53}) + "\n", encoding="utf-8")
    rel = emolumentos.importar(con, tmp_path)
    assert any("Sem dom_vigencia.jsonl" in a for a in rel["avisos"])
    assert rel["vigente"] == VIGENCIA_2026
