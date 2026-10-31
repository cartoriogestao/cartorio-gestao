"""Dois consertos pequenos que a revisão de telas achou. Estes testes não abrem banco.

O valor do título que não é número era lido como zero, e o título nascia de R$ 0,00. E as configurações que
cobram a equipe apareciam em «Cobrança por boleto», só porque as duas têm a palavra cobrança.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import navegacao
import protesto as PT
import protesto_cra as CRA


@pytest.mark.parametrize("valor", ["100,00", "1.234,56", "R$ 1.234,56", "1234.56", " 10 ", "0,00", 1500, 12.5])
def test_o_que_e_valor_passa(valor):
    assert PT.valor_legivel(valor)


@pytest.mark.parametrize("valor", ["abc", "", None, "R$", "12a", "cem reais", "1,00 reais"])
def test_o_que_nao_e_valor_nao_passa(valor):
    assert not PT.valor_legivel(valor)


def _dados(**mais):
    dados = {"especie": next(iter(CRA.ESPECIES)), "numero_titulo": "ENSAIO/1", "data_emissao": "2026-10-01",
             "valor": "100,00", "saldo": "100,00", "praca_protesto": "Cidade Exemplo",
             "devedores": [{"nome": "Ana Exemplo", "CPF": "00000000191", "enderecos": ["Rua Exemplo, 1"]}]}
    dados.update(mais)
    return dados


@pytest.mark.parametrize("campo, rotulo", [("valor", "O valor"), ("saldo", "O saldo")])
def test_o_titulo_com_letra_no_valor_e_recusado_antes_do_banco(campo, rotulo):
    assert not CRA.conferir_titulo(_dados()), "os dados de ensaio têm de passar no contrato"
    with pytest.raises(PT.ProtestoError, match=rotulo):
        PT.cadastrar_titulo(None, _dados(**{campo: "abc"}), origem="MANUAL", agora="2026-10-31T10:00:00")


def test_as_chaves_que_cobram_a_equipe_nao_moram_em_cobranca_por_boleto():
    assert navegacao.PAI["configuracoes_cobranca"] == ("GESTAO", "Configurações")
