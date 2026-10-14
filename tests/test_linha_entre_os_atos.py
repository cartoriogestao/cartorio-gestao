"""
A LINHA TRACADA ENTRE UM ATO E O SEGUINTE.

    «espaco nao e suficiente para separar um ato e outro, deve ter uma linha
     tracada entre eles»
                                    — o oficial, em 31/08/2026

EU TINHA PERGUNTADO A COISA ERRADA
    Perguntei se a certidao devia trazer de volta as linhas EM BRANCO que o
    E-Oficio guardou no teor, e ofereci duas escolhas. Ele respondeu com o
    requisito de verdade — SEPARAR — e disse que o meio que eu propus nao
    cumpre.

    E nao cumpre: branco some quando a folha vira, some no meio de um texto
    longo, e nao distingue «fim do ato» de «paragrafo novo dentro do mesmo
    ato».

E A CASA JA FAZIA ISSO — o achado que valida o pedido dele
    Medido nas 1.508 fichas com teor: **176 delas ja trazem 405 linhas de
    tracinhos**, desenhadas a mao pelo digitador entre um ato e o seguinte. O
    oficial nao pediu coisa nova; pediu de volta o que esta casa fazia, e que
    se perdeu quando o teor virou texto corrido. «Na duvida, imitar o
    E-Oficio» aqui nem e duvida: e o precedente literal.

O QUE ESTES TESTES GUARDAM
      - a linha entra ANTES de cada ato, **menos do primeiro** — separador
        serve para separar dois;
      - so conta o rotulo DESTA matricula, e so quando ele ABRE o paragrafo:
        o teor antigo cita atos de outras fichas o tempo todo, e uma linha ali
        cortaria a ficha no meio de uma frase;
      - a regua e IMPORTADA de `ri_numeros_do_teor`, e nao copiada;
      - onde o digitador ja desenhou a risca, a do sistema CEDE A VEZ — eram
        93 casos de linha dupla;
      - tabela e quadro do selo continuam onde estavam;
      - e o TEOR NAO MUDA: a linha e desenhada na impressao, e a certidao
        congela o corpo com sha256.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_numeros_do_teor
import ri_odt

MATRICULA = "3.231"


def odf_de(html: str) -> str:
    return ri_odt.html_para_odf(html)


def com_linha(html: str, numero=MATRICULA) -> str:
    return ri_odt.separar_atos(odf_de(html), numero)


def quantas(html: str, numero=MATRICULA) -> int:
    return com_linha(html, numero).count(ri_odt.SEPARADOR_DE_ATO)


# ------------------------------------------------------- onde ela entra


def test_entra_entre_um_ato_e_o_seguinte():
    html = ('<p>R-1/3.231. (COMPRA E VENDA).</p>'
            '<p>Pelo Título de Domínio nº 022181.</p>'
            '<p>AV-2/3.231. (CLÁUSULAS RESOLUTIVAS).</p>')
    assert quantas(html) == 1


def test_NAO_entra_antes_do_primeiro():
    """Separador serve para separar dois. Um traço antes do primeiro ato seria
    régua debaixo do cabeçalho."""
    saida = com_linha('<p>MATRÍCULA Nº 3.231</p><p>R-1/3.231. (COMPRA).</p>')
    assert saida.count(ri_odt.SEPARADOR_DE_ATO) == 0


def test_tres_atos_dao_duas_linhas():
    html = ('<p>R-1/3.231. um</p><p>AV-2/3.231. dois</p>'
            '<p>R-3/3.231. três</p>')
    assert quantas(html) == 2


def test_a_linha_e_um_paragrafo_com_borda_e_nao_tracinhos():
    """Traços digitados dependem da largura da letra e da margem; a borda de
    parágrafo acompanha a folha. E o estilo existe nos DOIS conjuntos — o do
    `content.xml` e o do `styles.xml` —, senão o LibreOffice não a desenha."""
    assert ri_odt.SEPARADOR_DE_ATO == '<text:p text:style-name="P-separa-ato"/>'
    # `ESTILOS_AUTO` vai no `content.xml` e `STYLES` no `styles.xml`. O
    # estilo precisa existir nos DOIS: o que estiver só num deles o
    # LibreOffice ignora conforme o lugar em que o parágrafo cai.
    assert ri_odt.ESTILOS_AUTO.count("P-separa-ato") == 1
    assert ri_odt.STYLES.count("P-separa-ato") == 1


# ------------------------------------------ e onde ela NÃO pode entrar


def test_ato_de_OUTRA_matricula_nao_abre_linha():
    """«Transcrita neste Registro no Lº 2-C, fls. 16 sob nº R-1/503» — o teor
    antigo cita atos de outras fichas o tempo todo. Uma linha ali cortaria a
    ficha no meio de uma frase."""
    html = ('<p>R-1/3.231. um</p>'
            '<p>R-1/503. de outro imóvel</p>'
            '<p>AV-2/3.231. dois</p>')
    assert quantas(html) == 1


def test_rotulo_no_MEIO_da_frase_nao_abre_linha():
    """O rótulo tem de ABRIR o parágrafo. É exatamente assim que o teor antigo
    cita os das outras fichas — no meio de uma frase."""
    html = ('<p>R-1/3.231. um</p>'
            '<p>Transcrita no Lº 2-C, fls. 16, sob nº AV-2/3.231.</p>')
    assert quantas(html) == 0


def test_sem_o_numero_da_matricula_nao_marca_nada():
    """Rótulo sem matrícula com que comparar pode ser de outra ficha — e o
    silêncio é o certo: melhor deixar de separar do que separar errado."""
    html = '<p>R-1/3.231. um</p><p>AV-2/3.231. dois</p>'
    assert quantas(html, numero="") == 0
    assert quantas(html, numero=None) == 0


def test_a_regua_e_a_MESMA_de_ri_numeros_do_teor():
    """Não é «parecida»: é a mesma. Copiar o padrão para cá seria a
    `normalizar_nome` pela quarta vez — duas cópias divergem no primeiro
    conserto, e aqui o preço é a linha cair no lugar errado.

    Este teste lê o código, e não a intenção.
    """
    fonte = (RAIZ / "ri_odt.py").read_text(encoding="utf-8")
    assert "from ri_numeros_do_teor import ROTULO" in fonte
    # E a régua importada é a que reconhece o rótulo desta casa.
    assert ri_numeros_do_teor.ROTULO.match("AV-2/3.231. algo")
    assert not ri_numeros_do_teor.ROTULO.match("AV-2. algo")


# ------------------------------------- a risca que o digitador já fez


def test_NAO_desenha_risca_em_cima_de_risca():
    """Tracinhos do digitador viram a borda full-width; separar_atos não
    empilha uma segunda. Resultado: exatamente UMA risca (P-separa-ato)."""
    html = ('<p>R-1/3.231. um</p>'
            '<p>--------------------------------------------</p>'
            '<p>AV-2/3.231. dois</p>')
    assert quantas(html) == 1
    # e o ODF intermediário já trouxe a borda — sem traçinhos pela metade
    assert ri_odt.SEPARADOR_DE_ATO in odf_de(html)
    assert "----" not in odf_de(html)


def test_risca_curta_nao_conta_como_risca():
    """Um traço solto não é separador — e tratá-lo como tal faria a linha
    sumir onde ela é necessária."""
    html = ('<p>R-1/3.231. um</p><p>-</p><p>AV-2/3.231. dois</p>')
    assert quantas(html) == 1


# ----------------------------------------------- e o que não se estraga


def test_a_tabela_continua_no_lugar():
    """`re.sub` substitui NO LUGAR: o que não é parágrafo — tabela, quadro do
    selo, fragmento — continua exatamente onde estava."""
    html = ('<p>R-1/3.231. um</p>'
            '<table border="1" cols="4cm,4cm"><tr><td>a</td><td>b</td></tr></table>'
            '<p>AV-2/3.231. dois</p>')
    saida = com_linha(html)
    assert "<table:table" in saida
    assert saida.index("<table:table") < saida.index(ri_odt.SEPARADOR_DE_ATO)


def test_corpo_vazio_nao_estoura():
    assert ri_odt.separar_atos("", MATRICULA) == ""
    assert ri_odt.separar_atos(None, MATRICULA) == ""


def test_o_TEOR_nao_muda_uma_letra():
    """A linha é desenhada na IMPRESSÃO, e não gravada no teor.

    A certidão congela o corpo com sha256, e o teor certificado tem de
    continuar sendo exatamente o que foi certificado. Tirados os separadores,
    o que sobra é idêntico ao que havia antes deles.
    """
    html = ('<p>R-1/3.231. um</p><p>AV-2/3.231. dois</p>'
            '<p>R-3/3.231. três</p>')
    antes = odf_de(html)
    depois = com_linha(html).replace(ri_odt.SEPARADOR_DE_ATO, "")
    assert depois == antes
