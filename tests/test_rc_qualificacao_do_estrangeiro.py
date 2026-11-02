"""O estrangeiro sai identificado no termo — o ensaio de atos, 01/11/2026.

O PEDIDO do oficial: «antecipar esses problemas e processar antes de encontrar na prática». O ensaio
de atos (`tests/ensaio_de_atos_rcpn.py`) lavrou pela tela o casamento de um nubente italiano com
passaporte, e o termo o qualificou «italiano, lavrador, natural de Roma, nascido no dia …»: sem o
país e sem documento nenhum — a qualificação só tinha frase para o RG e o CPF. E a opção de
nacionalidade de quem nasceu em Portugal saiu «natural de Cidade Exemplo/MA».

Os nomes são fictícios, como em todo teste desta casa.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import rc_modelos_do_livro as ML                 # noqa: E402

BASE = {"nome": "MARIO EXEMPLO DOS SANTOS", "sexo": "M", "nacionalidade": "italiano",
        "profissao": "lavrador", "naturalidade_cidade": "Roma", "naturalidade_pais": "Itália",
        "data_nascimento": "1994-02-11", "endereco": "Rua Exemplo, 10", "bairro": "Centro",
        "cidade": "Cidade Exemplo", "uf": "MA"}


@pytest.mark.parametrize("tipo, frase", [("PASSAPORTE", "portador do passaporte n.º YA0000000"),
                                          ("CNH", "portador da CNH n.º YA0000000"),
                                          ("OUTRO", "portador do documento n.º YA0000000")])
def test_o_documento_que_nao_e_rg_nem_cpf_entra_na_qualificacao(tipo, frase):
    q = ML.qualificacao_inteira(BASE | {"documento_tipo": tipo, "documento_numero": "YA0000000"})
    assert frase in q, q


def test_a_frase_do_documento_concorda_com_o_sexo():
    q = ML.qualificacao_inteira(BASE | {"sexo": "F", "documento_tipo": "PASSAPORTE",
                                        "documento_numero": "YA0000000"})
    assert "portadora do passaporte n.º YA0000000" in q


def test_quem_nasceu_fora_e_natural_da_cidade_e_do_pais_sem_a_uf():
    q = ML.qualificacao_inteira(BASE | {"naturalidade_uf": "MA"})
    assert "natural de Roma, Itália, nascido" in q, q


def test_so_o_pais_quando_a_cidade_nao_veio():
    q = ML.qualificacao_inteira(BASE | {"naturalidade_cidade": ""})
    assert "natural de Itália" in q, q


@pytest.mark.parametrize("pais", ["", "Brasil", "BRASIL", "brasil"])
def test_o_brasileiro_continua_como_era(pais):
    p = BASE | {"nacionalidade": "brasileiro", "naturalidade_cidade": "Cidade Exemplo",
                "naturalidade_uf": "MA", "naturalidade_pais": pais, "documento_tipo": "CPF",
                "documento_numero": "000.000.011-63"}
    q = ML.qualificacao_inteira(p)
    assert "natural de Cidade Exemplo/MA, nascido" in q and "inscrito no CPF n.º 000.000.011-63" in q, q
    assert "portador do" not in q
