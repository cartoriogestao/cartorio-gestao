"""Regressões da folha nova do RCPN relatadas em 09/09/2026."""
from __future__ import annotations

from io import BytesIO
import re
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import impressao_pdf as PDF
import ri_odt as ODT


def _pagina(arquivo: bytes) -> str:
    """O bloco `<style:page-layout-properties …>` do .odt — e só ele.

    A medida da PÁGINA tem de ser lida na página. Procurar `fo:margin-top`
    no styles.xml inteiro acha o de um parágrafo, que é o que este arquivo
    guarda desde 09/09/2026.
    """
    with zipfile.ZipFile(BytesIO(arquivo)) as pacote:
        estilos = pacote.read("styles.xml").decode("utf-8")
    achado = re.search(r"<style:page-layout-properties\b[^>]*>", estilos)
    assert achado, "styles.xml sem <style:page-layout-properties>"
    return achado.group(0)


def test_odt_carta_sem_cabecalho_define_estilos_antes_do_tamanho():
    arquivo = ODT.gerar_odt(
        "<text:p>TERMO HIPOTÉTICO</text:p>",
        pagina_largura_cm=21.5, pagina_altura_cm=27.9, margem_cm=1.2,
    )
    pagina = _pagina(arquivo)
    assert 'fo:page-width="21.5cm"' in pagina
    assert 'fo:page-height="27.9cm"' in pagina
    assert 'fo:margin-left="1.2cm"' in pagina


def test_a_margem_pedida_vai_NA_PAGINA_e_nao_num_paragrafo():
    """**O DEFEITO DA FOLHA DO LIVRO, MEDIDO EM 09/09/2026.**

    `margem_cm=0` trocava a margem com `count=1` no styles.xml inteiro — e
    antes da página há **4** `fo:margin-top` e **9** `fo:margin-bottom` de
    estilos de parágrafo. O que mudava era o parágrafo; a PÁGINA ficava com
    os 1,5 cm / 2 cm de fábrica, e a imagem de 27,91 cm da folha entrava
    numa área útil de 24,41 cm: no .odt que o oficial baixou (termo 19567),
    a folha saía encolhida, empurrada para baixo e com uma faixa branca no
    pé — enquanto o PDF do Chrome, do mesmo HTML, saía certo.

    `left` e `right` passavam por acaso: só existem na página. Era esse o
    lado que o teste acima olhava.
    """
    pagina = _pagina(ODT.gerar_odt("<text:p>x</text:p>", margem_cm=0.0))
    for lado in ("top", "bottom", "left", "right"):
        assert f'fo:margin-{lado}="0cm"' in pagina, (
            f"a margem {lado} da PÁGINA não foi para 0 — provavelmente a "
            "troca pegou um estilo de parágrafo antes da página")


def test_exportacao_preserva_pauta_e_todas_as_anotacoes_do_html():
    entrada = ('<html><head></head><body><div class="campo-notas pautado">'
               + '<br>'.join(f'linha {n}' for n in range(40))
               + '</div></body></html>')
    saida = PDF._html_com_pauta_para_chrome(entrada)
    assert saida == entrada
    assert 'linha 39' in saida


def test_chrome_nao_forca_largura_total_dentro_da_area_com_margens():
    """A página tem 215 mm; a área útil, depois das margens, tem 191 mm.

    Forçar ``body=215mm`` dentro dos 191 mm fazia o Chrome reduzir tudo outra
    vez e deixava PDF/ODT com proporção diferente da prévia HTML.
    """
    saida = PDF._html_com_pauta_para_chrome("<html><head></head><body>x</body></html>")
    assert "width: 215mm !important" not in saida
    assert saida == "<html><head></head><body>x</body></html>"


def test_brasao_e_embutido_na_frente_e_no_verso(tmp_path):
    brasao = tmp_path / "brasao.jpg"
    brasao.write_bytes(b"imagem-falsa")
    entrada = ('<img src="/static/brasao.jpg"><p>frente</p>'
               '<img src="http://servidor/static/brasao.jpg"><p>verso</p>')

    saida = PDF.incorporar_imagem_local(entrada, brasao)

    assert "brasao.jpg" not in saida
    assert saida.count('src="data:image/jpeg;base64,') == 2


def test_previa_html_conta_a_largura_da_folha_com_as_margens_dentro():
    modelo = (RAIZ / "templates" / "rcpn_folha_impressa.html").read_text(
        encoding="utf-8")
    assert "* { box-sizing: border-box; }" in modelo
