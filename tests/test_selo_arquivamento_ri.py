# -*- coding: utf-8 -*-
"""Selo de arquivamento RI (16.39) — opcional na lavratura."""
from __future__ import annotations

from pathlib import Path

import pytest

ATO = Path(__file__).resolve().parent.parent / "ato_selado.py"


def _load():
    src = ATO.read_text(encoding="utf-8")
    start = src.index("CODIGO_ARQUIVAMENTO_RI")
    # ate a proxima def de abertura (depois do envelope)
    fn = src.index("def envelope_do_arquivamento_do_ri", start)
    end = src.index("\ndef envelope_da_abertura_da_matricula", fn)
    chunk = src[start:end]
    pre = (
        "class AtoError(Exception): pass\n"
        "from typing import Any\n"
    )
    ns: dict = {}
    exec(pre + chunk, ns)
    return ns


@pytest.fixture(scope="module")
def fns():
    return _load()


def test_codigo_e_caminho(fns):
    assert fns["CODIGO_ARQUIVAMENTO_RI"] == "16.39"
    assert fns["CAMINHO_ARQUIVAMENTO_RI"] == "/selo/imovel/atos-em-geral"


def test_envelope_quantidade(fns):
    env = fns["envelope_do_arquivamento_do_ri"](
        escrevente="TESTE", versao_tabela="0220260101", quantidade=12)
    assert env["quantidade"] == 12
    assert env["ato"]["codigo"] == "16.39"
    assert env["ato"]["codigoTabelaCusta"] == "0220260101"
    assert env["escrevente"] == "TESTE"


def test_envelope_recusa_folha_invalida(fns):
    with pytest.raises(fns["AtoError"]):
        fns["envelope_do_arquivamento_do_ri"](
            escrevente="TESTE", versao_tabela="0220260101", quantidade=0)
    with pytest.raises(fns["AtoError"]):
        fns["envelope_do_arquivamento_do_ri"](
            escrevente="TESTE", versao_tabela="0220260101", quantidade="x")


def test_envelope_exige_escrevente(fns):
    with pytest.raises(fns["AtoError"]):
        fns["envelope_do_arquivamento_do_ri"](
            escrevente="", versao_tabela="0220260101", quantidade=1)

def test_envelope_isento_herda(fns):
    env = fns["envelope_do_arquivamento_do_ri"](
        escrevente="TESTE", versao_tabela="0220260101", quantidade=3,
        isento=True, motivo_isencao="art. 290-A reforma agraria")
    assert env["isento"]["value"] is True
    assert "290-A" in env["isento"]["motivo"]
    assert env["quantidade"] == 3


def test_envelope_isento_exige_motivo(fns):
    with pytest.raises(fns["AtoError"]):
        fns["envelope_do_arquivamento_do_ri"](
            escrevente="TESTE", versao_tabela="0220260101", quantidade=1,
            isento=True, motivo_isencao="")


def test_envelope_sem_isento_nao_leva_campo(fns):
    env = fns["envelope_do_arquivamento_do_ri"](
        escrevente="TESTE", versao_tabela="0220260101", quantidade=1)
    assert "isento" not in env

