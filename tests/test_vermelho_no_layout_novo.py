"""`.danger` nunca pintou o texto. No layout novo, o que avisa sai em vermelho, e o layout antigo fica como está.

Mais de duzentos lugares das telas marcam aviso, atraso e recusa com essa classe, e o `app.css` só a pinta no
botão, no aviso do alto e no cartão de número. Estes testes leem o que a casca traz para os outros casos.
"""
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
CASCA = (RAIZ / "static" / "casca.css").read_text(encoding="utf-8")
APP = (RAIZ / "static" / "app.css").read_text(encoding="utf-8")


def _regra_que_tem(trecho: str) -> str:
    achadas = [r for r in re.findall(r"[^{}]+\{[^{}]*\}", CASCA) if trecho in r.split("{")[0]]
    assert achadas, f"nenhuma regra de {trecho} na casca"
    return achadas[0]


@pytest.mark.parametrize("trecho", ["strong,small", "tr.danger>td", ".notice.danger", ".alerta.danger", ".alert-danger",
                                    ".badge.danger"])
def test_a_casca_pinta_cada_forma_que_as_telas_usam(trecho):
    assert "color:" in _regra_que_tem(trecho)


def test_so_vale_na_moldura_nova():
    regras = [r for r in re.findall(r"[^{}]+\{[^{}]*\}", CASCA) if "danger" in r.split("{")[0]]
    assert regras
    for regra in regras:
        assert ".cg-corpo" in regra.split("{")[0], regra


def test_o_layout_antigo_nao_ganhou_a_regra_solta():
    assert not re.search(r"(^|[},])\s*\.danger\s*[,{]", APP)


def test_o_que_ja_tem_cor_propria_nao_entra_na_regra_do_texto():
    seletor = _regra_que_tem("strong,small").split("{")[0]
    for classe in (".badge", ".stat", ".flash", ".notice", ".alerta", ".alert", ".card"):
        assert classe in seletor.split(":not(")[1]


def test_o_cartao_de_numero_nao_vira_alarme_com_zero():
    """«Vencidos: 0» continua com a borda de sempre: pintar o cartão inteiro seria alarme sem nada para fazer."""
    assert ".card.danger:not(.stat)" in CASCA


def test_a_caixa_de_marcar_nao_estica_e_fica_abaixo_de_quem_cuida_da_propria():
    """O `app.css` dá a todo `input` a largura da linha. A regra usa `:where`, para ficar só acima da de fábrica."""
    regra = re.search(r":where\(\.cg-corpo\) input:where\(\[type=checkbox\],\[type=radio\]\)\{([^}]*)\}", CASCA)
    assert regra, "a regra da caixa de marcar saiu da casca"
    assert "width:16px" in regra.group(1) and "min-height:0" in regra.group(1)
    assert ":where(.cg-corpo) label:has(>input:where([type=checkbox],[type=radio])){display:block}" in CASCA


def test_o_app_css_continua_esticando_e_o_layout_antigo_nao_muda():
    assert "input,select,textarea{font:inherit;width:100%" in APP
