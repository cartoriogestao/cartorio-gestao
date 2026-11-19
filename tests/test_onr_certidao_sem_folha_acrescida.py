"""CGJ-TJMA (18/11/2026): certidão da ONR não cobra folha acrescida; selo
base já emitido não cancela a certidão se o item extra falhar."""
from __future__ import annotations

from pathlib import Path

import ato_selado as AS

RAIZ = Path(__file__).resolve().parent.parent


def test_balcao_continua_cobrando_folha_acrescida():
    assert AS.itens_da_certidao_do_ri("INTEIRO_TEOR", 4) == [
        ("16.24.4", 1), ("16.24.4.1", 3)]
    # A de ônus são dois 16.24.4 (ônus reais e ações), e a folha
    # acrescida vai uma vez, pelo papel — decisão de 19/11/2026.
    assert AS.itens_da_certidao_do_ri("ONUS", 2) == [
        ("16.24.4", 1), ("16.24.4", 1), ("16.24.4.1", 1)]
    assert AS.itens_da_certidao_do_ri("PROPRIEDADE", 3) == [
        ("16.24.1", 1), ("16.24.2", 2)]
    assert AS.itens_da_certidao_do_ri("NEGATIVA_IMOVEL", 3) == [
        ("16.24.1", 1), ("16.24.2", 2)]


def test_onr_16_24_4_e_16_24_1_sem_folha_acrescida():
    for tipo in ("INTEIRO_TEOR", "ONUS", "DOMINIAL", "VINTENARIA",
                 "PROPRIEDADE", "NEGATIVA_IMOVEL", "POSITIVA_PESSOA"):
        itens = AS.itens_da_certidao_do_ri(tipo, 9, digital=True)
        assert len(itens) == 1, tipo
        assert itens[0][1] == 1, tipo
        assert itens[0][0] in {"16.24.4", "16.24.1"}, tipo


def test_recado_parcial_nao_e_sem_selo_total():
    """«item(ns) sem cobertura» não dispara o cancelamento por «SEM SELO»."""
    fonte = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    assert "item(ns) sem cobertura:" in fonte
    assert "RI_CERTIDAO_SELO_PARCIAL" in fonte
    # O cancelamento só quando NÃO saiu selo base.
    assert 'if motivo_selo and pedido.get("saiu"):' in fonte
    inicio = fonte.index("def _motivo_da_falha_do_selo")
    fim = fonte.index("\n    def ", inicio + 1)
    auxiliar = fonte[inicio:fim]
    # Só o padrão com dois-pontos; «sem selo» solto (parcial) não cancela.
    assert 'if "sem selo" in baixo:' not in auxiliar
    assert 'if "sem selo:" in baixo:' in auxiliar


def test_telas_do_ri_oferecem_a_caixa_onr():
    for nome in ("ri_ficha.html", "ri_indicador_pessoal.html",
                 "ri_indicador_real.html"):
        html = (RAIZ / "templates" / nome).read_text(encoding="utf-8")
        assert "_certidao_digital_onr.html" in html, nome
