"""CPF averbado pela tela comum (natureza cpf_347) precisa sair na certidão.

A tela `/rcpn/<id>/averbar` grava só o teor em `rc_atos` e não preenche
`rc_assentos.cpf_registrado` nem `rc_pessoas.documento_numero`. Sem ler o
teor da averbação, nascimento/óbito saíam com CPF em branco mesmo com a
margem correta. O quadro (`rc_certidao_quadro`) chama a mesma função.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import rc_certidao as CE  # noqa: E402
import rc_cpf as CPF  # noqa: E402

SV = {
    "unit_name": "SERVENTIA EXTRAJUDICIAL DO OFÍCIO ÚNICO DE CIDADE EXEMPLO",
    "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
    "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
}
MATRICULA = "000000015519971000111270010385 01"
TEOR_CPF = CPF.texto_averbacao("00000004502")
HOJE = "2026-11-19"
EXTENSO = "dezenove dias do mês de novembro do ano de dois mil e vinte e seis"


def test_cpf_da_averbacao_pega_o_mais_recente():
    atos = [
        {"tipo": "AVERBACAO", "teor": "Averbado o casamento."},
        {"tipo": "AVERBACAO", "teor": CPF.texto_averbacao("00000000191")},
        {"tipo": "ANOTACAO", "teor": TEOR_CPF},
        {"tipo": "AVERBACAO", "teor": TEOR_CPF},
    ]
    assert CE._cpf_da_averbacao(atos, "NASCIMENTO") == "000.000.045-02"


@pytest.mark.parametrize("especie", ["NASCIMENTO", "NATIMORTO", "OBITO"])
def test_cpf_da_averbacao_nas_especies_com_principal_unico(especie):
    assert CE._cpf_da_averbacao(
        [{"tipo": "AVERBACAO", "teor": TEOR_CPF}], especie) == "000.000.045-02"


def test_cpf_da_averbacao_nao_adivinha_no_casamento():
    assert CE._cpf_da_averbacao(
        [{"tipo": "AVERBACAO", "teor": TEOR_CPF}], "CASAMENTO") == ""


def test_cpf_da_averbacao_ignora_teor_que_nao_e_de_cpf():
    assert CE._cpf_da_averbacao(
        [{"tipo": "AVERBACAO", "teor": "Retificado o nome do pai."}],
        "NASCIMENTO") == ""


def test_montar_teor_usa_cpf_da_averbacao_quando_campos_estao_vazios():
    teor = CE.montar_teor(
        assento={"especie": "NASCIMENTO", "nome": "JOÃO DA SILVA",
                 "matricula": MATRICULA},
        pessoas_do_assento=[{"papel": "REGISTRADO", "nome": "JOÃO DA SILVA"}],
        atos=[{"tipo": "AVERBACAO", "teor": TEOR_CPF, "natureza": "cpf_347"}],
        sv=SV, hoje=HOJE, data_extenso=EXTENSO)
    linhas = teor.splitlines()
    assert linhas[linhas.index("CPF") + 1] == "000.000.045-02"


def test_montar_teor_obito_tambem_le_a_averbacao():
    teor = CE.montar_teor(
        assento={"especie": "OBITO", "nome": "JOÃO DA SILVA",
                 "matricula": MATRICULA},
        pessoas_do_assento=[{"papel": "FALECIDO", "nome": "JOÃO DA SILVA"}],
        atos=[{"tipo": "AVERBACAO", "teor": TEOR_CPF, "natureza": "cpf_347"}],
        sv=SV, hoje=HOJE, data_extenso=EXTENSO)
    linhas = teor.splitlines()
    assert linhas[linhas.index("CPF") + 1] == "000.000.045-02"


def test_pessoa_com_cpf_prevalece_sobre_averbacao():
    teor = CE.montar_teor(
        assento={"especie": "NASCIMENTO", "nome": "JOÃO DA SILVA",
                 "matricula": MATRICULA},
        pessoas_do_assento=[{
            "papel": "REGISTRADO", "nome": "JOÃO DA SILVA",
            "documento_tipo": "CPF", "documento_numero": "00000000191",
        }],
        atos=[{"tipo": "AVERBACAO", "teor": TEOR_CPF}],
        sv=SV, hoje=HOJE, data_extenso=EXTENSO)
    linhas = teor.splitlines()
    assert linhas[linhas.index("CPF") + 1] == "000.000.001-91"
