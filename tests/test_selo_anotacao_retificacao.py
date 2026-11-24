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


# ---------------------------------------------------------------- P006
# Retificação de 19/11/2026: sem item marcado, o selo levava o protocolo
# inteiro (14.5.1, 14.4.1, 14.10, 14.12×5) pelo caminho `/retificacao`; a
# anotação de 23/11 levava 14.10 e 13.30. E a averbação de CPF caía no
# Tribunal com «dadosSelo.folha deve estar entre 1 e 3» — a folha «137v».


def test_retificacao_sela_so_o_item_14_10_do_protocolo():
    itens = ["14.5.1", "14.4.1", "14.10"] + ["14.12"] * 5
    assert AS.itens_selo_do_lancamento_rcpn("RETIFICACAO", itens) == ["14.10"]
    assert AS.itens_selo_do_lancamento_rcpn(
        "retificacao", ["14.10.1", "14.100"]) == ["14.10.1"]


def test_anotacao_sela_so_o_item_14_7_do_protocolo():
    itens = ["14.10", "13.30", "13.30", "13.30"]
    assert AS.itens_selo_do_lancamento_rcpn("ANOTACAO", itens) == []
    assert AS.itens_selo_do_lancamento_rcpn(
        "ANOTACAO", ["14.5.1", "14.7", "14.7"]) == ["14.7", "14.7"]


def test_outros_tipos_passam_sem_filtro():
    itens = ["14.5.1", "14.4.1"]
    assert AS.itens_selo_do_lancamento_rcpn("REGISTRO", itens) == itens
    assert AS.itens_selo_do_lancamento_rcpn(None, None) == []


@pytest.mark.parametrize("escrita, esperado", [
    ("137v", "137"), ("082v", "82"), (" 100 V ", "100"), ("82v e 83", "82"),
    ("001", "1"), (13, "13"), ("9v", "9"),
    ("", ""), (None, ""), ("v", ""), ("0", ""), ("1234", ""),
])
def test_folha_do_selo_tira_o_verso_e_os_zeros(escrita, esperado):
    assert AS.folha_do_selo(escrita) == esperado


def _envelopes(folha):
    comum = dict(escrevente="MARIO", livro="A-11", folha=folha, termo="10427",
                 versao_tabela="0120260101")
    return {
        "averbacao": AS.envelope_da_averbacao_civil(
            **comum, alteracao="Averbo o CPF de teste.",
            tipo_averbacao=AS.TIPO_AVERBACAO_CPF_ART_347, isento=True,
            motivo_isencao="ART. 347"),
        "anotacao": AS.envelope_da_anotacao_civil(
            **comum, anotacao="Anoto neste assento de teste."),
        "retificacao": AS.envelope_da_retificacao_civil(
            **comum, retificacao="Retifico neste assento de teste."),
        "generico": AS.envelope_do_civil(
            especie="NASCIMENTO", tipo="REGISTRO", nome_parte="PEDRO EXEMPLO",
            codigo_tj="14.5.1", **comum),
    }


def test_a_folha_com_verso_vai_ao_selo_so_com_o_numero():
    for nome, env in _envelopes("137v").items():
        assert env["dadosSelo"]["folha"] == "137", nome


def test_a_folha_que_nao_vira_numero_e_recusada_antes_do_tribunal():
    with pytest.raises(AS.AtoError, match="1 a 3 algarismos"):
        _envelopes("1234")
