"""O timbre da serventia na tela: só onde ele tem função, e o papel não muda.

O QUE ELES DEFENDEM
    Decisão do oficial, 30/10/2026: no layout novo o quadro fica nas telas de origem. O risco é tela
    que se imprime pelo navegador ficar sem timbre no papel, sem erro nenhum. A parte de baixo usa o
    sistema de pé, e roda na outra máquina.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import navegacao as NAV  # noqa: E402

TELAS = RAIZ / "templates"
# As telas que têm o quadro e se imprimem pelo navegador, e a rota de cada uma.
IMPRIMEM = {"rcpj_rtd_notificacao_certidao.html": "rcpj_rtd_notificacao_certidao_ver"}


def _texto(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8-sig")


def test_o_quadro_obedece_a_regra():
    corpo = _texto(TELAS / "_serventia.html")
    assert "{% if timbre_na_tela is not defined or timbre_na_tela %}" in corpo
    assert corpo.rstrip().endswith("{% endif %}")


def test_as_telas_de_origem_continuam_com_o_quadro():
    for tela in ("caixa.html", "caixa_protocolos.html", "caixa_protocolo.html", "ri_protocolo.html"):
        assert "_serventia.html" in _texto(TELAS / tela), tela
    assert {"caixa", "caixa_protocolos", "caixa_protocolo", "ri_protocolo"} <= NAV.TELAS_COM_TIMBRE


def test_quem_se_imprime_pelo_navegador_nao_perde_o_timbre():
    """Tela nova que imprime e tem o quadro entra na lista: sem isso, o papel sai sem timbre."""
    achadas = {t.name for t in TELAS.glob("*.html")
               if "_serventia.html" in _texto(t) and re.search(r"window\.print|\bprint\(\)", _texto(t))}
    assert achadas == set(IMPRIMEM), "tela que imprime pelo navegador: ponha em TELAS_COM_TIMBRE"
    assert set(IMPRIMEM.values()) <= NAV.TELAS_COM_TIMBRE


def test_toda_tela_da_lista_existe():
    fontes = "".join(_texto(a) for a in RAIZ.glob("*.py"))
    for rota in NAV.TELAS_COM_TIMBRE:
        assert re.search(rf"def {rota}\(", fontes), rota


# ------------------------------------------------------------- com o sistema de pé

def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _entrar(app, usuario: str):
    d = app.extensions["db"]
    try:
        d.create_user(usuario, "Operador Exemplo", "Senha#12345", "ADMIN")
    except Exception:                                              # noqa: BLE001
        pass
    c = app.test_client()
    c.post("/login", data={"username": usuario, "password": "Senha#12345",
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


def _layout(c, qual: str) -> None:
    c.post("/preferencias/layout", data={
        "layout": qual, "next": "/", "csrf_token": _token(c.get("/").get_data(as_text=True))})


def test_o_quadro_some_so_no_layout_novo_e_fora_das_telas_de_origem(cg_app):
    c = _entrar(cg_app, "timbre_a")
    marca = "line-height:1.45"
    _layout(c, "antigo")
    assert marca in c.get("/usucapiao").get_data(as_text=True)
    assert marca in c.get("/caixa/protocolos").get_data(as_text=True)
    _layout(c, "novo")
    assert marca not in c.get("/usucapiao").get_data(as_text=True)
    assert marca in c.get("/caixa/protocolos").get_data(as_text=True)
