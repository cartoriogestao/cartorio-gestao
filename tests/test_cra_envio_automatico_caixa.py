"""A caixa do envio automático à CRA salva — relato do oficial, 15/10/2026.

«não consegui salvar o check de mandar automaticamente para a CRA»: a caixa
morava fora de qualquer formulário da tela de Configurações, e cada «Salvar»
do formulário principal gravava «0» por cima. Agora ela tem formulário e rota
próprios, e o salvar geral não mexe nela.
"""
from __future__ import annotations

import inspect
import re

from test_protesto_aviso_web import _token, s  # noqa: F401


def test_a_caixa_esta_dentro_do_proprio_formulario(s):
    html = s["c"].get("/configuracoes").get_data(as_text=True)
    form = re.search(
        r'<form[^>]*action="/configuracoes/cra-envio"[^>]*>(.*?)</form>',
        html, re.S)
    assert form, "o formulário do envio à CRA sumiu da tela"
    assert 'name="cra_auto_enviar_producao"' in form.group(1)
    assert 'name="csrf_token"' in form.group(1)


def test_marcar_e_desmarcar_grava(s):
    from database import Database
    db = Database(s["banco"])
    tela = s["c"].get("/configuracoes").get_data(as_text=True)
    html = s["c"].post("/configuracoes/cra-envio",
                       data={"csrf_token": _token(tela),
                             "cra_auto_enviar_producao": "on"},
                       follow_redirects=True).get_data(as_text=True)
    assert "LIGADO" in html
    assert db.get_setting("cra_auto_enviar_producao") == "1"

    tela = s["c"].get("/configuracoes").get_data(as_text=True)
    s["c"].post("/configuracoes/cra-envio",
                data={"csrf_token": _token(tela)}, follow_redirects=True)
    assert db.get_setting("cra_auto_enviar_producao") == "0"


def test_o_salvar_geral_nao_escreve_mais_a_caixa():
    import app as APP
    fonte = inspect.getsource(APP)
    corpo = fonte[fonte.index("    def settings():"):
                  fonte.index("    def configuracoes_cra_envio():")]
    assert '"cra_auto_enviar_producao":' not in corpo
