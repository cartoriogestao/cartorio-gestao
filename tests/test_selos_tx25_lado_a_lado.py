# -*- coding: utf-8 -*-
"""HOTFIX-2026-09-29-08: etiquetas TX25 empilhadas → carimbo lado a lado."""
from __future__ import annotations

import re

from ri_odt import carimbos_do_html_para_odf, html_para_odf


TABELA_TX25 = """
<p>Dou fé. A Tabeliã.</p>
<table cellspacing="0" style="width:509.7pt;border-collapse:collapse;">
<colgroup><col width="329" /><col width="351" /></colgroup>
<tr>
<td style="border:1pt solid #000;">
<table><tr><td>
<p><span style="font-size:6pt;">Poder Judiciário — TJMA<br /></span>
<span style="font-size:6pt;font-weight:bold;">Selo: MATRIC000000GXVCAWUO3HPU0793</span>
<span style="font-size:6pt;"><br />08/11/2023 16:21:51, Ato: 16.2</span></p>
</td><td><p></p></td></tr></table>
</td>
<td style="border:1pt solid #000;">
<table><tr><td>
<p><span style="font-size:6pt;">Poder Judiciário — TJMA<br /></span>
<span style="font-size:6pt;font-weight:bold;">Selo: PRENOT00000026GWXVCCGXE93F76</span>
<span style="font-size:6pt;"><br />08/11/2023 16:02:29, Ato: 16.1</span></p>
</td><td><p></p></td></tr></table>
</td>
</tr>
</table>
<p>R-01 segue.</p>
"""


def test_tabela_tx25_vira_carimbo_lado_a_lado():
    html, frags, imgs = carimbos_do_html_para_odf(TABELA_TX25)
    assert "@@CARIMBO_CERT_1@@" in html
    assert "Selo: MATRIC" not in html  # tabela sumiu
    assert len(frags) == 1
    frag = next(iter(frags.values()))
    assert "CarimboDoSelo" in frag
    assert frag.count("Col-selo-compacto") == 2  # lado a lado
    assert "MATRIC000000GXVCAWUO3HPU0793" in frag
    assert "PRENOT00000026GWXVCCGXE93F76" in frag
    odf = html_para_odf(html, fragmentos=frags)
    assert "CarimboDoSelo" in odf
    assert "Tab1" not in odf  # não empilha Tab1/Tab2 de etiquetas
    assert odf.count("Col-selo-compacto") == 2


def test_html_sem_etiqueta_intacta():
    html_in = "<p>Só texto sem selo.</p>"
    html, frags, imgs = carimbos_do_html_para_odf(html_in)
    assert html == html_in
    assert frags == {}
    assert imgs == {}
