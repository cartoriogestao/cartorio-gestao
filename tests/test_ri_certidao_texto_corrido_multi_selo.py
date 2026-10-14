# -*- coding: utf-8 -*-
"""Certidão RI: texto corrido + multi-selo + risca full-width (3.6.197)."""
from __future__ import annotations

from ri_odt import (
    SEPARADOR_DE_ATO,
    SEPARADOR_DE_ATO_HTML,
    html_em_texto_corrido,
    miolo_html_do_documento,
    html_para_odf,
    MIOLO_CERTIDAO_INTEIRO_TEOR,
    separar_atos,
)


def test_html_em_texto_corrido_junta_paragrafos():
    out = html_em_texto_corrido("<p>um</p>\n<p>dois</p>\n<p>tres</p>", "4001")
    assert out == "<p>um dois tres</p>"


def test_html_em_texto_corrido_linha_entre_atos():
    html = (
        "<p>abertura da ficha</p><p>continua descricao</p>"
        "<p>AV-01/4.001 - DESMEMBRAMENTO</p><p>resto do ato</p>"
    )
    out = html_em_texto_corrido(html, "4001")
    assert "abertura da ficha continua descricao" in out
    assert SEPARADOR_DE_ATO_HTML in out
    assert "AV-01/4.001 - DESMEMBRAMENTO resto do ato" in out


def test_html_em_texto_corrido_ignora_ato_de_outra_matricula():
    html = "<p>texto</p><p>AV-01/3.110 - outro imovel</p><p>mais</p>"
    out = html_em_texto_corrido(html, "4001")
    assert SEPARADOR_DE_ATO_HTML not in out
    assert "separa-ato" not in out
    assert out.count("<p>") == 1


def test_miolo_inteiro_teor_tem_separador_entre_atos():
    assert "separa-ato" in MIOLO_CERTIDAO_INTEIRO_TEOR
    assert "Era o que nela continha." in MIOLO_CERTIDAO_INTEIRO_TEOR


def test_tracinhos_viram_borda_full_width_no_odf():
    """Beatriz 24/09/2026: a risca tem de ir até o fim da coluna."""
    html = (
        "<p>R-1/4.001. um</p>"
        "<p>----------------------------------------</p>"
        "<p>AV-2/4.001. dois</p>"
    )
    odf = html_para_odf(html)
    assert SEPARADOR_DE_ATO in odf
    assert "----------------------------------------" not in odf
    depois = separar_atos(odf, "4001")
    assert depois.count(SEPARADOR_DE_ATO) == 1


def test_separa_ato_html_vira_borda_odf():
    odf = html_para_odf("<p>antes</p>" + SEPARADOR_DE_ATO_HTML + "<p>depois</p>")
    assert SEPARADOR_DE_ATO in odf
    assert odf.count(SEPARADOR_DE_ATO) == 1

def test_html_em_texto_corrido_descasca_envelope_tx25():
    """Beatriz 29/09/2026 mat. 2005: envelope e-Oficio nao vai ao papel."""
    html = (
        '<?xml version="1.0" ?>'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title></title></head>'
        '<body style="font-family:Arial">'
        '<p><span style="font-weight:bold">IMOVEL:-</span> gleba Firmeza.</p>'
        '</body></html>'
    )
    out = html_em_texto_corrido(html, "2005")
    assert "<?xml" not in out
    assert "<html" not in out.lower()
    assert "<body" not in out.lower()
    assert "<head" not in out.lower()
    assert "IMOVEL:-" in out and "Firmeza" in out
    assert out.startswith("<p>")


def test_html_em_texto_corrido_envelope_ato_sem_risca_sola():
    """Rotulo R-1 sozinho no documento nao gera risca (nada antes para separar)."""
    html = (
        '<?xml version="1.0"?><html><body>'
        '<p>R-1/2.005:- compra e venda.</p>'
        '</body></html>'
    )
    out = html_em_texto_corrido(html, "2005")
    assert "<?xml" not in out
    assert SEPARADOR_DE_ATO_HTML not in out
    assert "R-1/2.005" in out


def test_miolo_html_do_documento_sem_body_mantem():
    assert miolo_html_do_documento("<p>so miolo</p>") == "<p>so miolo</p>"

