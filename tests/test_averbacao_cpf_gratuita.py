"""Averbação de CPF gratuita (art. 347) e selo isentoGratuito no civil."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ato_selado as AS                                          # noqa: E402
import custas as CU                                              # noqa: E402


def test_art_347_cpf_existe_nas_gratuidades():
    assert CU.gratuidade_por_pessoa("ART_347_CPF")
    assert "347" in CU.gratuidade_por_pessoa("ART_347_CPF")["fundamento"]


def test_envelope_do_civil_aceita_selo_gratuito():
    env = AS.envelope_do_civil(
        especie="NASCIMENTO", tipo="AVERBACAO",
        escrevente="JEAN", livro="A-1", folha="10", termo="1",
        nome_parte="MARIA", versao_tabela="0120260101",
        isento=True,
        motivo_isencao="ART. 347 DO CODIGO DE NORMAS DO TJMA")
    ds = env["dadosSelo"]
    assert ds["isentoGratuito"] == "GRATUITO"
    assert "347" in ds["motivoIsentoGratuito"]


def test_envelope_do_civil_gratuito_exige_motivo():
    with pytest.raises(AS.AtoError):
        AS.envelope_do_civil(
            especie="NASCIMENTO", tipo="AVERBACAO",
            escrevente="JEAN", livro="A-1", folha="10", termo="1",
            nome_parte="MARIA", versao_tabela="0120260101",
            isento=True, motivo_isencao="")


def test_envelope_da_averbacao_civil_campos_obrigatorios():
    env = AS.envelope_da_averbacao_civil(
        escrevente="JEAN SANTOS", livro="A-1", folha="10", termo="1222",
        versao_tabela="0120260101",
        alteracao="Averbo neste assento o CPF n.º 000.000.000-00, art. 347.",
        tipo_averbacao=AS.TIPO_AVERBACAO_CPF_ART_347,
        codigo_tj="14.4.1", isento=True,
        motivo_isencao="ART. 347 DO CODIGO DE NORMAS DO TJMA")
    assert env["codigoAto"] == "14.4.1"
    assert env["tipoAverbacao"] == AS.TIPO_AVERBACAO_CPF_ART_347
    assert "CPF" in env["alteracao"].upper()
    assert "codigoTipoAtoRegistro" not in env
    assert env["dadosSelo"]["isentoGratuito"] == "GRATUITO"
    # Tribunal /averbacao exige dadosSelo.isento Boolean (Jackson DadosSelo),
    # alem de dadosSelo.isentoGratuito (forma medida do civil registro).
    assert env["dadosSelo"]["isento"] is True
    assert "isento" not in env or not isinstance(env.get("isento"), dict)


def test_envelope_da_averbacao_civil_exige_tipo():
    with pytest.raises(AS.AtoError):
        AS.envelope_da_averbacao_civil(
            escrevente="JEAN", livro="A-1", folha="10", termo="1",
            versao_tabela="0120260101", alteracao="texto",
            tipo_averbacao="", codigo_tj="14.4.1")


def test_envelope_da_averbacao_civil_default_codigo_14_4_1():
    """Sem codigo_tj, monta 14.4.1 + alteracao + tipo obrigatorio."""
    env = AS.envelope_da_averbacao_civil(
        escrevente="JEAN", livro="A-1", folha="10", termo="1",
        versao_tabela="0120260101",
        alteracao="Averbo o CPF, art. 347.",
        tipo_averbacao=AS.TIPO_AVERBACAO_CPF_ART_347)
    assert env["codigoAto"] == "14.4.1"
    assert env["alteracao"].startswith("Averbo")
    assert env["tipoAverbacao"] == 0
    assert AS.TIPO_AVERBACAO_CPF_ART_347 == 0


def test_envelope_da_averbacao_civil_isento_false_quando_pago():
    """Sem gratuidade, ainda manda dadosSelo.isento=False (Tribunal exige o campo)."""
    env = AS.envelope_da_averbacao_civil(
        escrevente="JEAN", livro="A-1", folha="10", termo="1",
        versao_tabela="0120260101",
        alteracao="Averbo retificacao de grafia.",
        tipo_averbacao=1, codigo_tj="14.4.1", isento=False)
    assert env["dadosSelo"]["isento"] is False
    assert "isentoGratuito" not in env["dadosSelo"]

