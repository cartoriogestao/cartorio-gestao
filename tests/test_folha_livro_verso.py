# -*- coding: utf-8 -*-
"""Numeração da face do livro no cabeçalho (193, 193v, 194…)."""
import io, zipfile
import notas_livro as NL
import ri_odt


def test_rotulo_folha_da_pagina_frente_verso():
    assert NL.rotulo_folha_da_pagina(193, 1) == "193"
    assert NL.rotulo_folha_da_pagina(193, 2) == "193v"
    assert NL.rotulo_folha_da_pagina(193, 3) == "194"
    assert NL.rotulo_folha_da_pagina(193, 4) == "194v"


def test_campo_folha_do_livro_odf_tem_formula_e_verso():
    xml = ri_odt.campo_folha_do_livro_odf(193)
    assert "INT((PAGE-1)/2)+193" in xml
    assert 'text:string-value-if-true="v"' in xml
    assert "(PAGE rem 2)=0" in xml


def test_gerar_odt_com_folha_livro_inicio_no_cabecalho():
    cab = "<p>FOLHA #FOLHA_PAGINA#</p>"
    corpo = f'''<text:p text:style-name="{ri_odt.ESTILO_PAGINA_1}">p1</text:p>
<text:p>continua</text:p>'''
    odt = ri_odt.gerar_odt(
        corpo, titulo="t", cabecalho_odf=cab,
        cabecalho_a_partir_da_pagina_2=True,
        folha_livro_inicio=193,
        cabecalho_altura_min="0.6cm", cabecalho_borda=False,
    )
    with zipfile.ZipFile(io.BytesIO(odt)) as z:
        styles = z.read("styles.xml").decode("utf-8")
    assert "INT((PAGE-1)/2)+193" in styles
    assert "#FOLHA_PAGINA#" not in styles
    assert "text:page-adjust" not in styles or "folha_livro" # livro mode should not use page-adjust for FOLHA
    assert "text:page-adjust" not in styles

def test_gerar_odt_ficha_usa_frente_verso():
    """#FICHA# numera folha física (1, 1v, 2…), não página sequencial do PDF."""
    cab = "<p>FICHA Nº #FICHA#</p>"
    corpo = "<text:p>corpo</text:p>"
    odt = ri_odt.gerar_odt(corpo, titulo="t", cabecalho_odf=cab)
    with zipfile.ZipFile(io.BytesIO(odt)) as z:
        styles = z.read("styles.xml").decode("utf-8")
    assert "INT((PAGE-1)/2)+1" in styles
    assert 'text:string-value-if-true="v"' in styles
    assert "#FICHA#" not in styles
    # Não pode ser o page-number sequencial antigo.
    assert 'text:select-page="current">1</text:page-number>' not in styles
