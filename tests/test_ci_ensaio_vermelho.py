"""ENSAIO DA CI — este arquivo existe só no PR de ensaio vermelho e não vai para o main.

Três falhas com a mesma causa e uma com outra, para conferir que o comentário
as agrupa em duas causas e que a fila não mescla o PR.
"""
import pytest


@pytest.mark.parametrize("valor", [1, 2, 3])
def test_ensaio_mesma_causa(valor):
    assert valor == 0, f"ensaio da CI: o valor {valor} deveria ser zero"


def test_ensaio_outra_causa():
    raise RuntimeError("ensaio da CI: uma falha de outra natureza")
