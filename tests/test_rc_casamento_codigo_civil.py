"""O casamento que o Código Civil não admite não se lavra calado — o ensaio de atos, 01/11/2026.

O PEDIDO do oficial: «antecipar esses problemas e processar antes de encontrar na prática». O ensaio
de atos (`tests/ensaio_de_atos_rcpn.py`) lavrou pela tela, sem um aviso:

    - a comunhão universal SEM pacto antenupcial (CC art. 1.640, parágrafo único, e art. 1.653);
    - o nubente de 15 anos (CC art. 1.520, na redação da Lei 13.811/2019);
    - o nubente de 76 anos em comunhão parcial, sem pacto (CC art. 1.641, II).

Os dois primeiros não têm leitura em que estejam certos, e TRAVAM; o terceiro pode estar (a separação
se afasta por escritura, STF Tema 1.236), e AVISA, como o de 16 ou 17 anos, que casa com autorização.
A régua é da época do casamento: a casa ainda transporta casamento antigo.

Os nomes são fictícios, como em todo teste desta casa.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import rc_conferencia_dados as CD                # noqa: E402


def _casamento(*, regime="COMUNHAO_PARCIAL", fato="2026-10-28", pacto_data="", pacto_serventia="",
               nasc1="1994-02-11", nasc2="1997-08-30") -> dict:
    return {"especie": "CASAMENTO", "nome": "MARIO EXEMPLO DOS SANTOS e BEATRIZ EXEMPLO DE SOUZA",
            "data_fato": fato, "data_ato": "2026-11-02", "teor": "", "regime_bens": regime,
            "pacto_data": pacto_data, "pacto_serventia": pacto_serventia,
            "pessoas": [{"papel": "NUBENTE1", "nome": "MARIO EXEMPLO DOS SANTOS", "sexo": "M",
                         "data_nascimento": nasc1},
                        {"papel": "NUBENTE2", "nome": "BEATRIZ EXEMPLO DE SOUZA", "sexo": "F",
                         "data_nascimento": nasc2}]}


def _codigos(dados: dict, gravidade: str) -> set[str]:
    return {p["codigo"] for p in CD.conferir(dados) if p["gravidade"] == gravidade}


@pytest.mark.parametrize("regime", ["COMUNHAO_UNIVERSAL", "SEPARACAO_TOTAL", "PARTICIPACAO_FINAL",
                                    "Comunhão universal de bens"])
def test_o_regime_convencional_sem_pacto_trava(regime):
    assert "REGIME_SEM_PACTO" in _codigos(_casamento(regime=regime), CD.BLOQUEIA)


@pytest.mark.parametrize("pacto", [{"pacto_data": "2026-08-01"},
                                   {"pacto_serventia": "Tabelionato de Notas de Cidade Exemplo"}])
def test_o_regime_convencional_com_pacto_passa(pacto):
    assert not _codigos(_casamento(regime="COMUNHAO_UNIVERSAL", **pacto), CD.BLOQUEIA)


@pytest.mark.parametrize("regime", ["COMUNHAO_PARCIAL", "SEPARACAO_OBRIGATORIA",
                                    "Separação obrigatória de bens (CC art. 1.641)"])
def test_a_comunhao_parcial_e_a_separacao_obrigatoria_dispensam_o_pacto(regime):
    assert "REGIME_SEM_PACTO" not in _codigos(_casamento(regime=regime), CD.BLOQUEIA)


def test_antes_de_1977_a_comunhao_universal_era_o_regime_legal():
    """Lei 6.515/1977: até ela, a comunhão universal dispensava pacto. O casamento transportado de
    antes não trava."""
    assert not _codigos(_casamento(regime="COMUNHAO_UNIVERSAL", fato="1975-05-10",
                                   nasc1="1950-01-01", nasc2="1952-01-01"), CD.BLOQUEIA)


def test_o_nubente_de_15_anos_trava():
    problemas = CD.conferir(_casamento(nasc2="2011-06-01"))
    trava = [p for p in problemas if p["codigo"] == "SEM_IDADE_NUBIL"]
    assert trava and trava[0]["gravidade"] == CD.BLOQUEIA and trava[0]["campo"] == "NUBENTE2"
    assert "15 anos" in trava[0]["mensagem"] and "1.520" in trava[0]["mensagem"]


def test_o_nubente_sem_idade_nubil_pede_a_data_de_nascimento_para_arrumar():
    campos = [c["campo"] for c in CD.campos_para_corrigir(CD.conferir(_casamento(nasc2="2011-06-01")))]
    assert "nubente2_data_nascimento" in campos


def test_antes_da_lei_13811_o_menor_de_16_casava_com_suprimento():
    assert "SEM_IDADE_NUBIL" not in _codigos(_casamento(fato="2018-05-10", nasc2="2002-08-01"),
                                             CD.BLOQUEIA)


@pytest.mark.parametrize("nasc2", ["2010-03-01", "2009-01-01"])
def test_o_nubente_de_16_ou_17_anos_avisa_e_nao_trava(nasc2):
    dados = _casamento(nasc2=nasc2)
    assert "NUBENTE_MENOR" in _codigos(dados, CD.AVISA)
    assert not _codigos(dados, CD.BLOQUEIA)


def test_o_maior_de_70_sem_separacao_nem_pacto_avisa():
    dados = _casamento(nasc1="1950-01-10")
    assert "REGIME_DO_MAIOR_DE_70" in _codigos(dados, CD.AVISA)
    assert not _codigos(dados, CD.BLOQUEIA)


@pytest.mark.parametrize("trocar", [{"regime": "SEPARACAO_OBRIGATORIA"},
                                    {"regime": "COMUNHAO_UNIVERSAL", "pacto_data": "2026-08-01"}])
def test_o_maior_de_70_na_separacao_ou_com_pacto_nao_avisa(trocar):
    assert "REGIME_DO_MAIOR_DE_70" not in _codigos(_casamento(nasc1="1950-01-10", **trocar), CD.AVISA)


def test_o_formulario_leva_o_regime_e_o_pacto_a_conferencia():
    """A conferência antes de lavrar lê a tela (`dados_do_formulario`): sem o regime e o pacto nela, a
    trava só apareceria na recusa da lavratura."""
    d = CD.dados_do_formulario({"especie": "CASAMENTO", "regime_bens": "COMUNHAO_UNIVERSAL",
                                "pacto_data": "", "pacto_serventia": "", "data_fato": "2026-10-28",
                                "nubente1_nome": "MARIO EXEMPLO DOS SANTOS"})
    assert "REGIME_SEM_PACTO" in {p["codigo"] for p in CD.bloqueios(CD.conferir(d))}
