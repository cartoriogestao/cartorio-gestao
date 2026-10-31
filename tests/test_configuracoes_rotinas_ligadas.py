"""As duas rotinas que escrevem sem clique: a caixa da tela diz o mesmo que a rotina faz.

SEM LINHA GRAVADA, A ROTINA RODA. A caixa saía desmarcada nesse caso, e o próximo «Salvar configurações»
gravava DESLIGADO nas duas sem ninguém pedir. Medido na produção em 30/10/2026: nenhuma das duas tem linha.

Estes testes montam a própria caixa do molde, e por isso não dependem de banco.
"""
import re
from pathlib import Path

import jinja2
import pytest

import censec_automatico

RAIZ = Path(__file__).resolve().parents[1]
MOLDE = (RAIZ / "templates" / "settings.html").read_text(encoding="utf-8")
CHAVES = ("censec_envio_automatico", "rtdpj_corrigir_automatico")


def _caixa(chave: str, s: dict) -> str:
    achado = re.search(rf'<input type="checkbox" name="{chave}"[^>]*>', MOLDE)
    assert achado, f"a caixa {chave} saiu da tela"
    return jinja2.Environment(autoescape=True).from_string(achado.group(0)).render(s=s)


@pytest.mark.parametrize("chave", CHAVES)
def test_sem_linha_gravada_a_caixa_vem_marcada(chave):
    assert "checked" in _caixa(chave, {})


@pytest.mark.parametrize("chave", CHAVES)
@pytest.mark.parametrize("valor, marcada", [("LIGADO", True), ("", True), (None, True), ("DESLIGADO", False)])
def test_a_caixa_respeita_o_que_esta_gravado(chave, valor, marcada):
    assert ("checked" in _caixa(chave, {chave: valor})) is marcada


class _Banco:
    """Responde como `get_setting`: sem linha gravada, devolve o padrão pedido."""

    def __init__(self, gravadas: dict):
        self.gravadas = gravadas

    def get_setting(self, chave, padrao=""):
        return self.gravadas.get(chave, padrao)


@pytest.mark.parametrize("gravadas", [{}, {"censec_envio_automatico": "LIGADO"},
                                      {"censec_envio_automatico": "DESLIGADO"}])
def test_a_caixa_da_censec_e_a_rotina_dizem_a_mesma_coisa(gravadas):
    assert censec_automatico.envio_ligado(_Banco(gravadas)) is ("checked" in _caixa("censec_envio_automatico", gravadas))
