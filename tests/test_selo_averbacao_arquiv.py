"""Averbação RCPN: só 14.4.1 + um ARQUIV com quantidade (oficial 15/09/2026)."""
from __future__ import annotations

from pathlib import Path

import pytest

ATO = Path(__file__).resolve().parent.parent / "ato_selado.py"


def _load_fns():
    src = ATO.read_text(encoding="utf-8")
    start = src.index("CODIGO_AVERBACAO_RCPN")
    fn_end = src.index(
        "\ndef envelope_da_habilitacao",
        src.index("def envelope_da_averbacao_civil"),
    )
    chunk = src[start:fn_end]
    pre = (
        "class AtoError(Exception): pass\n"
        "MOTIVO_DA_ISENCAO = {}\n"
        "CODIGO_DO_ATO_DO_CIVIL = {'AVERBACAO': ('14.4.1', 'TABELA')}\n"
        "from typing import Any\n"
    )
    ns: dict = {}
    exec(pre + chunk, ns)
    return ns


@pytest.fixture(scope="module")
def fns():
    return _load_fns()


def test_sem_protocolo_so_averbacao(fns):
    assert fns["itens_selo_averbacao_rcpn"](None) == [("14.4.1", 1)]
    assert fns["itens_selo_averbacao_rcpn"]([]) == [("14.4.1", 1)]


def test_protocolo_guilhermy_nao_expande_arquiv_nem_outros(fns):
    # Medido no ato 298: CERTID, BURCXX, AVERBA, RETIFI, ARQUIV×5
    proto = [
        ("14.5.1", 1), ("14.6.5", 1), ("14.4.1", 1),
        ("14.10", 1), ("14.12", 5),
    ]
    got = fns["itens_selo_averbacao_rcpn"](proto)
    assert got == [("14.4.1", 1), ("14.12", 5)]
    assert all(c != "14.5.1" for c, _ in got)
    assert all(c != "14.10" for c, _ in got)


def test_arquiv_agrega_linhas(fns):
    got = fns["itens_selo_averbacao_rcpn"]([("14.12", 2), ("14.12", 3)])
    assert got == [("14.4.1", 1), ("14.12", 5)]


def test_envelope_arquiv_leva_quantidade(fns):
    env = fns["envelope_da_averbacao_civil"](
        escrevente="TESTE", livro="A-14", folha="1", termo="1",
        versao_tabela="20260101", alteracao="alteracao de prenome",
        tipo_averbacao=0, codigo_tj="14.12", quantidade=5)
    assert env["codigoAto"] == "14.12"
    assert env["quantidade"] == 5


def test_envelope_averba_sem_quantidade_unitaria(fns):
    env = fns["envelope_da_averbacao_civil"](
        escrevente="TESTE", livro="A-14", folha="1", termo="1",
        versao_tabela="20260101", alteracao="alteracao de prenome",
        tipo_averbacao=0, codigo_tj="14.4.1", quantidade=1)
    assert env["codigoAto"] == "14.4.1"
    assert "quantidade" not in env
