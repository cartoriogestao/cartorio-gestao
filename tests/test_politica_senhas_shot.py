import os
from pathlib import Path

import pytest
# Sem o playwright o modulo PULA, em vez de quebrar a coleta (23/10/2026).
sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright

pytestmark = pytest.mark.skipif(
    os.environ.get("CG_SHOT_POLITICA_SENHAS") != "1",
    reason="shot env",
)


def test_politica_senhas_fieldset_screenshot(cg_casa_logada):
    client = cg_casa_logada["cliente"]
    html = client.get("/configuracoes").get_data(as_text=True)
    assert "Política de senhas" in html
    static = Path(__file__).resolve().parent.parent / "static"
    html = html.replace('href="/static/', f'href="file:///{static.as_posix()}/')
    out = Path(r"C:\cursor\stores\self\media\configuracoes-politica-senhas-20261001.png")
    alt = Path.home() / "Downloads" / "CartorioGestao" / "internal" / "media" / "configuracoes-politica-senhas-20261001.png"
    for p in (out, alt):
        p.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.set_content(html, wait_until="load")
        loc = page.locator("fieldset.cfg-bloco").filter(
            has=page.locator("legend", has_text="Política de senhas")
        )
        loc.first.screenshot(path=str(out))
        loc.first.screenshot(path=str(alt))
        browser.close()
