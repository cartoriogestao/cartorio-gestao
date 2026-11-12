"""O TJ conhece o item 13.1; as faixas 13.1.N sao so do caixa (12/11/2026).

A escritura 813 (duas areas, 13.1.8 e 13.1.15) teve o selo recusado pelo TJ
(«Nao foi encontrado um ato para o codigo informado») porque o envelope levava o
item da FAIXA do caixa. Medido no razao: os 21 selos de
`/selo/notas/ato-declarado/com-valor` sao todos «Ato: 13.1». So o que vai ao
aparelho troca de codigo; a cobertura segue lendo o item pago (13.1.N).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ato_selado as AS  # noqa: E402


def _envelope(item: str, valor: float):
    return AS.envelope_do_ato_de_livro_das_notas(
        tipo="ESCRITURA", codigo_tj=item, escrevente="Escrevente Teste",
        versao_tabela="2026", livro="30", folha="194", termo="5723",
        partes=[{"nome": "Parte Teste"}], valor_declarado=valor)


@pytest.mark.parametrize("item,valor", [("13.1.8", 38815.53),
                                        ("13.1.15", 205863.95),
                                        ("13.1.34", 9999999.0)])
def test_faixa_do_13_1_vai_ao_aparelho_como_13_1(item, valor):
    envelope, caminho = _envelope(item, valor)
    assert caminho == AS.CAMINHO_DA_ESCRITURA_COM_VALOR
    assert envelope["ato"]["codigo"] == item           # o que a cobertura le
    enviado = AS.dados_para_o_aparelho(envelope)
    assert enviado["ato"]["codigo"] == "13.1"          # o que o TJ conhece
    assert enviado["ato"]["codigoTabelaCusta"] == "2026"
    assert enviado["valorDeclarado"]["valorDeclarado"] == valor
    # o envelope original nao foi alterado (a cobertura continua no 13.1.N)
    assert envelope["ato"]["codigo"] == item
    assert AS.codigo_do_envelope(envelope) == item
    assert AS.codigo_do_envelope(enviado) == "13.1"


@pytest.mark.parametrize("codigo", ["13.1", "13.2", "13.9.3", "13.10.3",
                                    "13.30", "16.24.4.1", "17.4.5", "13.1.8.1",
                                    "13.11", ""])
def test_outros_itens_seguem_como_estao(codigo):
    dados = {"ato": {"codigo": codigo, "codigoTabelaCusta": "2026"}}
    assert AS.dados_para_o_aparelho(dados) == dados


def test_sem_ato_nao_quebra():
    assert AS.dados_para_o_aparelho({"x": 1}) == {"x": 1}
    assert AS.dados_para_o_aparelho(None) is None