"""Envelope do selo de anotação e retificação do Registro Civil.

O envelope genérico (`codigoTipoAtoRegistro`) é errado para `/anotacao` e
`/retificacao`: o Tribunal exige `codigoAto` + `anotacao` / `retificacao`
(DadosSeloAnotacaoRegistroCivil / DadosSeloRetificacaoRegistroCivil).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ato_selado as AS                                          # noqa: E402
import atribuicoes_web as AW                                     # noqa: E402

_AMOSTRA = Path(__file__).parent / "selador_reais.json"


def test_envelope_da_anotacao_civil_chaves_e_codigo_14_7():
    teor = "Anoto neste assento de teste o nascimento do filho."
    env = AS.envelope_da_anotacao_civil(
        escrevente="MARIO", livro="A-1", folha="10", termo="1",
        versao_tabela="0120260101", anotacao=teor)
    assert sorted(env.keys()) == ["anotacao", "codigoAto", "dadosSelo"]
    assert env["codigoAto"] == "14.7"
    assert env["anotacao"] == teor
    assert "codigoTipoAtoRegistro" not in env
    assert env["dadosSelo"]["escrevente"] == "MARIO"
    assert env["dadosSelo"]["livro"] == "A-1"
    assert env["dadosSelo"]["folha"] == "10"
    assert env["dadosSelo"]["termo"] == "1"
    assert env["dadosSelo"]["versaoTabelaDeCustas"] == "0120260101"


def test_envelope_da_anotacao_civil_nao_recorta_teor_longo():
    """Sem teto inventado: só a averbação mediu 1..500 em `alteracao`."""
    teor = "Anoto assento de teste. " + ("X" * 600)
    env = AS.envelope_da_anotacao_civil(
        escrevente="MARIO", livro="A-1", folha="10", termo="1",
        versao_tabela="0120260101", anotacao=teor)
    assert env["anotacao"] == teor.strip()
    assert len(env["anotacao"]) > AS.ALTERACAO_SELO_MAX


def test_envelope_da_anotacao_civil_exige_teor():
    with pytest.raises(AS.AtoError, match="anotação"):
        AS.envelope_da_anotacao_civil(
            escrevente="MARIO", livro="A-1", folha="10", termo="1",
            versao_tabela="0120260101", anotacao="")


def test_envelope_da_retificacao_civil_chaves_e_codigo_14_10():
    teor = "Retifico neste assento de teste a grafia do prenome."
    env = AS.envelope_da_retificacao_civil(
        escrevente="MARIO", livro="A-1", folha="10", termo="1",
        versao_tabela="0120260101", retificacao=teor)
    assert sorted(env.keys()) == ["codigoAto", "dadosSelo", "retificacao"]
    assert env["codigoAto"] == "14.10"
    assert env["retificacao"] == teor
    assert "codigoTipoAtoRegistro" not in env


def test_envelope_da_retificacao_civil_exige_teor():
    with pytest.raises(AS.AtoError, match="retificação"):
        AS.envelope_da_retificacao_civil(
            escrevente="MARIO", livro="A-1", folha="10", termo="1",
            versao_tabela="0120260101", retificacao="   ")


def test_envelope_anotacao_bate_schema_oficial_quando_ha_amostra():
    if not _AMOSTRA.is_file():
        pytest.skip("tests/selador_reais.json fica fora do repositório público")
    schemas = json.loads(_AMOSTRA.read_text(encoding="utf-8"))["schemas_oficiais"]
    schema = schemas["DadosSeloAnotacaoRegistroCivil"]
    required = set(schema.get("required") or [])
    assert {"anotacao", "codigoAto", "dadosSelo"} <= required
    env = AS.envelope_da_anotacao_civil(
        escrevente="MARIO", livro="A-1", folha="10", termo="1",
        versao_tabela="0120260101",
        anotacao="Anoto neste assento de teste.")
    assert required <= set(env.keys())
    assert "codigoTipoAtoRegistro" not in env


def test_envelope_retificacao_bate_schema_oficial_quando_ha_amostra():
    if not _AMOSTRA.is_file():
        pytest.skip("tests/selador_reais.json fica fora do repositório público")
    schemas = json.loads(_AMOSTRA.read_text(encoding="utf-8"))["schemas_oficiais"]
    schema = schemas["DadosSeloRetificacaoRegistroCivil"]
    required = set(schema.get("required") or [])
    assert {"retificacao", "codigoAto", "dadosSelo"} <= required
    env = AS.envelope_da_retificacao_civil(
        escrevente="MARIO", livro="A-1", folha="10", termo="1",
        versao_tabela="0120260101",
        retificacao="Retifico neste assento de teste.")
    assert required <= set(env.keys())
    assert "codigoTipoAtoRegistro" not in env


def test_atribuicoes_web_liga_anotacao_e_retificacao_ao_envelope_certo():
    """O ramo de `_envelope_do_civil` não pode cair no envelope genérico."""
    src = Path(AW.__file__).read_text(encoding="utf-8")
    assert "envelope_da_anotacao_civil" in src
    assert "envelope_da_retificacao_civil" in src
    # Ordem: averbação, anotação, retificação, genérico.
    i_av = src.index("envelope_da_averbacao_civil")
    i_an = src.index("envelope_da_anotacao_civil")
    i_re = src.index("envelope_da_retificacao_civil")
    i_gen = src.index("return AS.envelope_do_civil(", i_av)
    assert i_av < i_an < i_re < i_gen
