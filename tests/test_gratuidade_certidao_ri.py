# -*- coding: utf-8 -*-
"""Gratuidade na certidao do RI — 23/09/2026 (Beatriz, matricula 582)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ato_selado as AS


def _env(**extra):
    return AS.envelope_da_certidao_do_ri(
        tipo="INTEIRO_TEOR",
        escrevente="Beatriz",
        versao_tabela="20260101",
        quantidade=1,
        requerente="FULANO",
        requerente_documento="00000000000",
        matricula="582",
        **extra,
    )


def test_cobrada_continua_isento_false():
    d = _env()
    assert d["isento"] is False
    assert "motivoIsentoGratuito" not in d


def test_gratuita_manda_isento_e_motivo_maiusculo():
    d = _env(isento=True, motivo_isencao="Lei 13.465/2017")
    assert d["isento"] is True
    assert d["motivoIsentoGratuito"] == "LEI 13.465/2017"


def test_gratuita_sem_motivo_recusada_antes_da_rede():
    with pytest.raises(AS.AtoError) as erro:
        _env(isento=True, motivo_isencao="   ")
    assert "motivo" in str(erro.value).lower()


def test_motivo_acima_de_500_recusado():
    with pytest.raises(AS.AtoError) as erro:
        _env(isento=True, motivo_isencao="X" * 501)
    assert "500" in str(erro.value)


def test_schema_tem_colunas_de_isencao():
    txt = (RAIZ / "ri_schema.py").read_text(encoding="utf-8")
    assert '("ri_certidoes", "isento", "INTEGER")' in txt
    assert '("ri_certidoes", "motivo_isencao", "TEXT")' in txt


def test_tela_da_ficha_tem_bloco_de_gratuidade():
    html = (RAIZ / "templates" / "ri_ficha.html").read_text(encoding="utf-8")
    assert "Este selo será COBRADO" in html
    assert "Este selo é gratuito" in html
    assert 'name="isento"' in html
    assert 'name="motivo_isencao"' in html
    assert 'maxlength="500"' in html
