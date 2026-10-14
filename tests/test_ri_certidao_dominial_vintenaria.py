# -*- coding: utf-8 -*-
"""Certidão dominial / vintenária — mapas e filtro de atos."""
from __future__ import annotations

import ato_selado as AS
import ri_dominial as RIDOM
import ri_odt as ODT
from ri_schema import TIPOS_CERTIDAO


def test_tipos_miolo_e_selo_alinhados():
    assert set(TIPOS_CERTIDAO) == set(ODT.MIOLO_DA_CERTIDAO)
    assert set(TIPOS_CERTIDAO) == set(AS.CODIGO_DA_CERTIDAO_DO_RI)
    assert "DOMINIAL" in TIPOS_CERTIDAO
    assert "VINTENARIA" in TIPOS_CERTIDAO
    assert AS.CODIGO_DA_CERTIDAO_DO_RI["DOMINIAL"] == "16.24.4"
    assert AS.CODIGO_DA_CERTIDAO_DO_RI["VINTENARIA"] == "16.24.4"
    assert ODT.MIOLO_DA_CERTIDAO["DOMINIAL"] == "RI_CERTIDAO_DOMINIAL"
    assert ODT.MIOLO_DA_CERTIDAO["VINTENARIA"] == "RI_CERTIDAO_VINTENARIA"


def test_cadeia_dominial_por_natureza():
    atos = [
        {"tipo": "R", "numero": 1, "natureza_titulo": "Compra e Venda",
         "teor": "R-1/1 - COMPRA E VENDA. Fulano...", "data_ato": "2010-01-10",
         "cancelado": 0},
        {"tipo": "R", "numero": 2, "natureza_titulo": "Hipoteca",
         "teor": "R-2/1 - HIPOTECA...", "data_ato": "2015-03-01",
         "cancelado": 0},
        {"tipo": "R", "numero": 3, "natureza_titulo": "Doação",
         "teor": "R-3/1 - DOAÇÃO...", "data_ato": "2020-05-05",
         "cancelado": 0},
    ]
    cadeia = RIDOM.cadeia_dominial(atos, rotulo=lambda a: f"R-{a['numero']}")
    assert [a["numero"] for a in cadeia] == [1, 3]
    assert all(not a["conferir"] for a in cadeia)


def test_vintenaria_janela_e_onus():
    from datetime import date
    hoje = date(2026, 9, 28)
    atos = [
        {"tipo": "R", "numero": 1, "natureza_titulo": "Compra e Venda",
         "teor": "x", "data_ato": "2000-01-01", "cancelado": 0},
        {"tipo": "R", "numero": 2, "natureza_titulo": "Compra e Venda",
         "teor": "x", "data_ato": "2018-06-01", "cancelado": 0},
        {"tipo": "R", "numero": 3, "natureza_titulo": "Hipoteca",
         "teor": "R-3 - HIPOTECA", "data_ato": "2019-01-01", "cancelado": 0},
    ]
    pack = RIDOM.conteudo_vintenaria(atos, anos=20, rotulo=lambda a: f"R-{a['numero']}", hoje=hoje)
    assert pack["anos"] == 20
    assert [a["numero"] for a in pack["dominio"]] == [2]
    assert [a["numero"] for a in pack["onus"]] == [3]


def test_itens_selo_dominial():
    itens = AS.itens_da_certidao_do_ri("DOMINIAL", folhas=1)
    assert itens == [("16.24.4", 1)]
    itens2 = AS.itens_da_certidao_do_ri("VINTENARIA", folhas=3)
    assert itens2 == [("16.24.4", 1), ("16.24.4.1", 2)]


def test_extrai_numeros_registro_anterior():
    texto = ("Desmembrada da Matricula nº 3307, LIVRO: 2-R; "
             "unificação Matrícula 2558 e Matriculas 2557")
    nums = RIDOM.extrair_numeros_registro_anterior(texto)
    assert "3307" in nums
    assert "2558" in nums
    assert "2557" in nums
    # 2.765 -> 2765
    assert RIDOM.extrair_numeros_registro_anterior("MATRICULA 2.765, Livro 2-P") == ["2765"]
    assert RIDOM.normalizar_numero_matricula("0293") == "293"
    assert RIDOM.sugerir_numeros_origem(
        "MATRICULA 3236 DO LIVRO 2-R", numero_atual="3359") == ["3236"]
    # nao sugere a propria
    assert RIDOM.sugerir_numeros_origem(
        "Matrícula 3359", numero_atual="3359") == []


def test_parsear_numeros_digitados():
    assert RIDOM.parsear_numeros_digitados("2040, 1.990 e 3020") == ["2040", "1990", "3020"]
