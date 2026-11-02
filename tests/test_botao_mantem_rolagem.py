"""O botão continua embaixo do mouse depois de gravar (oficial, 02/11/2026).

«cada vez que clica num botão no sistema ele volta pra parte de cima da tela»: o formulário grava, o
servidor redireciona para a mesma tela, e ela abria no topo. `static/manter_rolagem.js` devolve a página
à posição em que o botão estava. A ligação (toda tela carrega o script) se confere no servidor; a rolagem,
só num navegador de verdade — e por isso a segunda parte usa o Chrome, numa página mínima, sem banco.
"""
from __future__ import annotations

import re
import threading
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = re.compile(r'<script defer src="[^"]*/manter_rolagem\.js\?v=([^"]*)"></script>')


@pytest.mark.parametrize("molde", ["base.html", "base_novo.html"])
def test_os_dois_moldes_carregam_o_script(molde):
    texto = (RAIZ / "templates" / molde).read_text(encoding="utf-8-sig")
    assert "filename='manter_rolagem.js') }}?v={{ VERSION }}" in texto


def test_a_tela_de_verdade_traz_o_script_uma_vez(cg_casa_logada):
    html = cg_casa_logada["c"].get("/").get_data(as_text=True)
    achados = SCRIPT.findall(html)
    assert len(achados) == 1 and re.fullmatch(r"\d+\.\d+\.\d+", achados[0]), achados


# ------------------------------------------------------------------ no navegador

def _pagina(aviso: bool) -> str:
    js = (RAIZ / "static" / "manter_rolagem.js").read_text(encoding="utf-8")
    linhas = "".join(f"<p>linha {i}</p>" for i in range(120))
    topo = '<div style="height:90px;background:#dfd">Gravado.</div>' if aviso else ""
    return (f"<!doctype html><html><head><meta charset='utf-8'></head><body>{topo}{linhas}"
            "<form method='post' action='/tela'><button id='gravar' type='submit'>Gravar</button></form>"
            f"{linhas}<script>{js}</script></body></html>")


@pytest.fixture(scope="module")
def servidor():
    from flask import Flask, redirect, request
    from werkzeug.serving import make_server

    app = Flask(__name__)
    estado = {"gravou": False}

    @app.route("/tela", methods=["GET", "POST"])
    def tela():
        if request.method == "POST":
            estado["gravou"] = True
            return redirect("/tela")
        return _pagina(estado["gravou"])

    @app.route("/outra", methods=["GET"])
    def outra():
        return _pagina(False)

    srv = make_server("127.0.0.1", 0, app, threaded=True)
    linha = threading.Thread(target=srv.serve_forever, daemon=True)
    linha.start()
    yield f"http://127.0.0.1:{srv.server_port}", estado
    srv.shutdown()


@pytest.fixture(scope="module")
def navegador():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        nav, erros = None, []
        for pedido in ({"channel": "chrome"}, {}):
            try:
                nav = p.chromium.launch(headless=True, **pedido)
                break
            except Exception as erro:  # noqa: BLE001
                erros.append(str(erro)[:160])
        if nav is None:
            pytest.skip(f"sem navegador nesta máquina: {erros}")
        yield nav
        nav.close()


def _altura_do_botao(tela) -> float:
    return tela.evaluate("document.getElementById('gravar').getBoundingClientRect().top")


def test_depois_de_gravar_o_botao_volta_a_mesma_altura(servidor, navegador):
    endereco, estado = servidor
    estado["gravou"] = False
    tela = navegador.new_page(viewport={"width": 1366, "height": 768})
    tela.goto(endereco + "/tela")
    tela.locator("#gravar").scroll_into_view_if_needed()
    tela.evaluate("window.scrollBy(0, -200)")
    antes = _altura_do_botao(tela)
    assert antes > 0, "o botão deveria estar à vista antes de clicar"
    with tela.expect_navigation():
        tela.locator("#gravar").click()
    tela.wait_for_load_state("load")
    tela.wait_for_timeout(200)
    depois = _altura_do_botao(tela)
    # O aviso de 90 px no alto não pode empurrar o botão para longe do mouse.
    assert abs(depois - antes) <= 2, (antes, depois)
    assert tela.evaluate("window.scrollY") > 0
    tela.close()


def test_outra_tela_abre_no_topo(servidor, navegador):
    endereco, estado = servidor
    tela = navegador.new_page(viewport={"width": 1366, "height": 768})
    tela.goto(endereco + "/tela")
    tela.locator("#gravar").scroll_into_view_if_needed()
    tela.evaluate("""() => sessionStorage.setItem('cg-botao-rolagem', JSON.stringify(
        {caminho: '/tela', em: Date.now(), tela: 900, alvo: 'x', ordem: 0, altura: 10}))""")
    tela.goto(endereco + "/outra")
    tela.wait_for_load_state("load")
    assert tela.evaluate("window.scrollY") == 0
    tela.close()
