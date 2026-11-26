"""«NEGATIVA» NÃO LEVA AS CAIXAS QUE SUMIRAM DA TELA — 26/11/2026.

O CASO
    Cinco recusas seguidas na mesma ficha, numa manhã de balcão: a IA leu
    NEGATIVA (a hipoteca e a alienação fiduciária já canceladas por averbação),
    o quadro veio com «Negativa» escolhida, e a rota recusava todas com «Marcou
    ônus para transcrever e escolheu NEGATIVA». Os dois atos, lavrados no
    sistema sem a marca de cancelados, entram como «confira» e vêm MARCADOS na
    lista de transcrição. Com «Negativa», a lista some da tela — mas as caixas
    marcadas iam no formulário mesmo assim, e quem emitia não tinha o que ver.

O QUE O TESTE PROVA, NUM NAVEGADOR DE VERDADE
    O quadro é o `_onus_decisao.html` de verdade, com o script dele. Com
    «Negativa», nada da lista escondida vai no formulário; voltando a
    «Positiva», a marca está lá e vai. A rota (`ri_onus_ia.decidir`) continua
    recusando NEGATIVA com ato marcado: a guarda fica, quem não manda mais o
    escondido é a tela.

SEM NAVEGADOR, ELE PULA, como os outros testes de navegador.
"""
from __future__ import annotations

from pathlib import Path

import jinja2
import pytest

MODELOS = Path(__file__).resolve().parent.parent / "templates"


def _item(chave, rotulo, *, origem="SISTEMA", literal=True, conferir=True):
    return {"chave": chave, "origem": origem, "categoria": "ONUS", "rotulo": rotulo,
            "natureza": "HIPOTECA", "texto": f"texto do {rotulo}", "conferir": conferir,
            "literal": literal}


def _quadro(sugerido_onus="NEGATIVA") -> str:
    amb = jinja2.Environment(loader=jinja2.FileSystemLoader(str(MODELOS)), autoescape=True)
    amb.globals["url_for"] = lambda *a, **k: "/andamento"
    painel = {
        "ia_ligada": True, "no_sandbox": False,
        "sugestao": {"situacao": "PRONTA", "vale": True, "onus": sugerido_onus,
                     "acoes": "NEGATIVA", "parecer": "", "cancelados": []},
        "proprietarios": {"situacao": "CONFERE", "cadastro": [{"nome": "FULANO"}],
                          "ato": "R-4", "ia": []},
        "sistema": [_item("ATO:1", "R-2"), _item("ATO:2", "R-6")],
        "ia": [_item("IA:0", "R-9", origem="IA", literal=False, conferir=False)],
        "sugerido": {"onus": sugerido_onus, "acoes": "NEGATIVA", "por": "IA"},
    }
    quadro = amb.get_template("_onus_decisao.html").render(
        onus_painel=painel, m={"id": 1}, RESULTADOS_ONUS=("POSITIVA", "NEGATIVA"))
    return ("<!doctype html><meta charset=utf-8><form id=f method=post>"
            "<select name=tipo><option value=ONUS selected>Ônus</option></select>"
            f"{quadro}<button class=primary type=submit>Emitir</button></form>")


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


ENVIADO = """() => { const d = new FormData(document.getElementById('f'));
  return {itens: d.getAll('onus_item'), onus: d.get('resultado_onus'),
          transcricao: d.has('onus_transcricao')}; }"""


def test_negativa_nao_envia_a_lista_escondida(navegador):
    tela = navegador.new_page()
    tela.set_content(_quadro("NEGATIVA"))
    assert not tela.is_visible("[data-so-positiva=resultado_onus]")
    enviado = tela.evaluate(ENVIADO)
    assert enviado["onus"] == "negativa"
    assert enviado["itens"] == [], "a caixa escondida ia no formulário"
    assert enviado["transcricao"] is False
    tela.close()


def test_voltar_a_positiva_devolve_a_marca(navegador):
    tela = navegador.new_page()
    tela.set_content(_quadro("NEGATIVA"))
    tela.check("input[name=resultado_onus][value=positiva]")
    enviado = tela.evaluate(ENVIADO)
    assert enviado["itens"] == ["ATO:1", "ATO:2"]
    # o trecho da IA que não está escrito na ficha continua fora, em qualquer caso
    assert tela.is_disabled("input[name=onus_item][value='IA:0']")
    tela.check("input[name=resultado_onus][value=negativa]")
    assert tela.evaluate(ENVIADO)["itens"] == []
    tela.close()


def test_positiva_sugerida_envia_o_que_vem_marcado(navegador):
    tela = navegador.new_page()
    tela.set_content(_quadro("POSITIVA"))
    assert tela.evaluate(ENVIADO)["itens"] == ["ATO:1", "ATO:2"]
    tela.close()


def test_a_rota_ainda_recusa_negativa_com_ato_marcado():
    """A guarda do servidor não saiu: só a tela deixou de mandar o escondido."""
    import ri_onus_ia as R

    with pytest.raises(R.OnusError, match="escolheu NEGATIVA"):
        R.decidir(texto_da_ficha_="R-2 texto", onus_vigentes=[
                      {"id": 1, "rotulo": "R-2", "natureza_titulo": "HIPOTECA",
                       "teor": "R-2 texto", "conferir": True}],
                  sugestao=None, resultado_onus="negativa", resultado_acoes="negativa",
                  marcados=["ATO:1"], proprietario_conferido=True)
