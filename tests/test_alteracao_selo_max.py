"""Padrão da casa: alteracao do selo civil ≤ 500 (TJMA)."""
from ato_selado import (
    ALTERACAO_SELO_MAX,
    envelope_da_averbacao_civil,
    recortar_alteracao_do_selo,
)


def test_recortar_alteracao_respeita_teto():
    assert ALTERACAO_SELO_MAX == 500
    curto = "Averbo o CPF 000.000.000-00."
    assert recortar_alteracao_do_selo(curto) == curto
    longo = ("A" * 480) + (" B" * 40)
    out = recortar_alteracao_do_selo(longo)
    assert len(out) <= ALTERACAO_SELO_MAX
    assert out.endswith("...")
    assert len(out) == ALTERACAO_SELO_MAX or len(out) < ALTERACAO_SELO_MAX


def test_envelope_averbacao_civil_nao_manda_alteracao_acima_de_500():
    teor = (
        "Averbo neste assento que o registrado passa a chamar-se "
        + ("Nome Completo Extenso Com Muitos Detalhes Do Requerimento " * 20)
        + " conforme protocolo e decisão do oficial."
    )
    assert len(teor) > ALTERACAO_SELO_MAX
    env = envelope_da_averbacao_civil(
        escrevente="Teste",
        livro="17",
        folha="161",
        termo="16919",
        versao_tabela="0320260101",
        alteracao=teor,
        tipo_averbacao=0,
    )
    assert 1 <= len(env["alteracao"]) <= ALTERACAO_SELO_MAX
    assert env["tipoAverbacao"] == 0
    # teor original não é responsabilidade do envelope
    assert len(teor) > len(env["alteracao"])
