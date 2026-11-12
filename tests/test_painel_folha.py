"""A folha do dia (12/11/2026) — a conta do termo de abertura e da régua.

Só função pura: nem banco, nem tela. O que se guarda aqui é o que faria o
painel mentir — a data escrita errada, o vencido que some da régua, a casa do
dia fora do lugar.
"""
from datetime import date

import painel_folha as FOLHA

HOJE = date(2026, 11, 12)          # uma quinta-feira


def test_a_data_sai_na_formula_do_assento():
    assert FOLHA.data_do_termo(HOJE) == (
        "Aos doze dias do mês de novembro de dois mil e vinte e seis")
    assert FOLHA.data_do_termo(date(2027, 1, 1)) == (
        "Ao primeiro dia do mês de janeiro de dois mil e vinte e sete")
    assert FOLHA.data_do_termo(date(2026, 3, 31)).startswith("Aos trinta e um dias")


def test_o_numero_por_extenso():
    assert FOLHA.por_extenso(21) == "vinte e um"
    assert FOLHA.por_extenso(100) == "cem"
    assert FOLHA.por_extenso(1998) == "mil novecentos e noventa e oito"
    assert FOLHA.por_extenso(2000) == "dois mil"
    assert FOLHA.por_extenso(2100) == "dois mil e cem"


def test_a_folha_e_o_dia_do_ano():
    assert FOLHA.cabecalho(HOJE)["folha"] == 316
    assert FOLHA.cabecalho(HOJE)["semana"] == "quinta-feira"


def test_o_aperto_fala_em_dias():
    assert FOLHA.aperto("2026-11-06", HOJE) == "há 6 dias"
    assert FOLHA.aperto("2026-11-11", HOJE) == "ontem"
    assert FOLHA.aperto("2026-11-12", HOJE) == "hoje"
    assert FOLHA.aperto("2026-11-13", HOJE) == "amanhã"
    assert FOLHA.aperto("2026-11-16", HOJE) == "em 4 dias"
    assert FOLHA.aperto(None, HOJE) == ""
    assert FOLHA.aperto("sem data", HOJE) == ""


def test_a_regua_vai_de_seis_dias_atras_ao_fim_do_alerta():
    r = FOLHA.regua({}, HOJE, 5)
    assert (r["desde"], r["ate"]) == ("2026-11-06", "2026-11-17")
    assert len(r["casas"]) == 12
    assert [c["semana"] for c in r["casas"] if c["hoje"]] == ["hoje"]
    assert [c["dia"] for c in r["casas"] if c["folga"]] == ["07", "08", "14", "15"]


def test_o_vencido_que_nao_cabe_na_regua_sai_contado():
    por_dia = {"2026-11-06": 1, "2026-11-10": 1, "2026-11-12": 1, "2026-11-13": 2}
    r = FOLHA.regua(por_dia, HOJE, 5, vencidos_ao_todo=5)
    # Dois na janela (dias 6 e 10); os outros três venceram antes do dia 6.
    assert r["antes"] == 3
    assert {c["dia"]: c["quantos"] for c in r["casas"] if c["quantos"]} == {
        "06": 1, "10": 1, "12": 1, "13": 2}
    # O de hoje não é vencido: vence hoje.
    assert [c["vencido"] for c in r["casas"] if c["dia"] == "12"] == [False]


def test_a_regua_nunca_conta_vencido_negativo():
    assert FOLHA.regua({"2026-11-10": 4}, HOJE, 5, vencidos_ao_todo=1)["antes"] == 0
