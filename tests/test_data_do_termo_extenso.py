# -*- coding: utf-8 -*-
"""Estilo «extenso» de `rc_modelos_do_livro.data_do_termo` (05/10/2026).

Dia e ano por extenso COM algarismo entre parênteses; mês SÓ por extenso,
sem «(N)». Arquivo isolado - roda com `--noconftest`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rc_modelos_do_livro as M  # noqa: E402


def test_mes_sai_so_por_extenso_sem_numero():
    assert M.data_do_termo("2026-08-19") == \
        "dezenove (19) de agosto de dois mil e vinte e seis (2026)"


def test_dia_com_dois_digitos_e_com_numeros():
    assert M.data_do_termo("2026-09-08", com_numeros=True) == \
        "oito (08) de setembro de dois mil e vinte e seis (2026) - 08/09/2026"


def test_nenhum_mes_leva_numero_entre_parenteses():
    for mes in range(1, 13):
        fora = M.data_do_termo(f"2026-{mes:02d}-10")
        assert f"{M.MESES[mes - 1]} ({mes})" not in fora
        assert f"de {M.MESES[mes - 1]} de " in fora


def test_data_invalida_volta_crua():
    assert M.data_do_termo("") == ""
    assert M.data_do_termo("2026-13-01") == "2026-13-01"
