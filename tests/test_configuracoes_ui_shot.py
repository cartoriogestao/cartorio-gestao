import os
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright

pytestmark = pytest.mark.skipif(
    os.environ.get("CG_SHOT_CONFIGURACOES") != "1",
    reason="shot env",
)

def test_configuracoes_ui_screenshot(cg_casa_logada):
    client = cg_casa_logada["cliente"]
    html = client.get("/configuracoes").get_data(as_text=True)
    assert "cfg-centrais" in html
    assert "pagina-configuracoes" in html
    html = html.replace("<head>", '<head><base href="http://127.0.0.1:8899/">', 1)
    out = Path(r"C:\cursor\stores\self\media\configuracoes-ui-20261001.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    alt = Path.home() / "Downloads" / "CartorioGestao" / "internal" / "media" / "configuracoes-ui-20261001.png"
    alt.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1200})
        page.set_content(html, wait_until="networkidle")
        page.locator("#cfg-centrais").scroll_into_view_if_needed()
        page.wait_for_timeout(600)
        page.screenshot(path=str(out), full_page=True)
        page.screenshot(path=str(alt), full_page=True)
        browser.close()
