"""O valor que a tela da pendência CENPROT manda à Central — 26/11/2026 (PR009).

O DEFEITO: a tela preenche «Valor da retirada» e «Valor das custas» com a
sugestão de `cenprot_pendencias.retirada_sugerida`, que vem com PONTO
(«566.19»), e `cenprot_web._numero` apagava todo ponto antes de ler. A
sugestão aceita sem mexer subia CEM VEZES maior: «566.19» virava 56619.0. O
pedido 3925045 (título 9633) subiu assim em 18/11, com `vl_retirada` 10073.0.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cenprot_web as W  # noqa: E402


@pytest.mark.parametrize("digitado, lido", [
    ("566.19", 566.19),      # a sugestão da própria tela
    ("100.73", 100.73),      # o caso do 9633 — subiu como 10073.0
    ("566.1", 566.1),
    ("566,19", 566.19),      # o balcão digita com vírgula
    ("82,64", 82.64),
    ("1.234,56", 1234.56),
    ("1,234.56", 1234.56),
    ("1.234", 1234.0),       # ponto com três casas é milhar
    ("1.234.567", 1234567.0),
    ("10073", 10073.0),
    ("R$ 566,19", 566.19),
    ("0", 0.0),              # zero é afirmação, e o domínio o recusa
    ("0,00", 0.0),
])
def test_o_valor_se_le_com_ponto_ou_virgula(digitado, lido):
    assert W._numero(digitado) == pytest.approx(lido)


@pytest.mark.parametrize("digitado", [
    None, "", "   ", "abc", "1,2,3", "12.3456", "1.23.4", "1.234,5.6",
])
def test_o_que_nao_se_le_com_seguranca_e_none_e_nao_numero(digitado):
    """Branco não é zero, e número ambíguo não se adivinha: o domínio recusa o
    None e a tela pede de novo."""
    assert W._numero(digitado) is None


@pytest.mark.parametrize("centavos", [1, 99, 8264, 10073, 56619, 123456, 999999])
def test_a_sugestao_da_tela_volta_como_saiu(centavos):
    """O formato que `retirada_sugerida` põe no campo, lido de volta, é o mesmo
    valor — a sugestão aceita sem mexer não pode mudar de tamanho."""
    reais = f"{centavos // 100}.{centavos % 100:02d}"
    assert round(W._numero(reais) * 100) == centavos
