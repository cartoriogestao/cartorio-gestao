# -*- coding: utf-8 -*-
"""Tachado vermelho e destaques no teor HTML → ODT."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ri_odt

def test_tachado_e_destaques_viram_estilos_odt():
    html = (
        "<p>Antes <s style=\"color:#c62828\">riscado</s> "
        "<mark style=\"background:#fff59d\">amarelo</mark> "
        "<mark style=\"background:#ffcdd2\">vermelho</mark> depois.</p>"
    )
    odf = ri_odt.html_para_odf(html)
    assert "T-tachado-vermelho" in odf
    assert "T-destaque-amarelo" in odf
    assert "T-destaque-vermelho" in odf
    assert "riscado" in odf and "amarelo" in odf and "vermelho" in odf

def test_teor_marcas_js_tem_novos_botoes():
    js = (Path(__file__).resolve().parents[1] / "static" / "teor-marcas.js").read_text(encoding="utf-8")
    assert "Tachado vermelho" in js
    assert "Destaque amarelo" in js
    assert "Destaque vermelho" in js
    assert "marca.abre" in js or "m.abre" in js or "abre:" in js
