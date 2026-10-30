"""A moldura nova, com o sistema de pé: a chave por pessoa e o que sai na página.

O QUE ELES DEFENDEM
    Que o layout novo é o padrão, que quem não escolheu recebe o aviso e volta com um
    clique, e que a troca não desenha as duas molduras na mesma página. A suíte fica na
    moldura antiga (`conftest`), e por isso estes testes pedem o padrão de verdade. Foi o
    primeiro defeito desta casca: o
    `include` de `base.html` não obedece ao `extends` dentro de `if`, e os avisos e os
    botões do layout antigo saíam antes do <!doctype> da nova.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from flask import url_for

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import navegacao as NAV  # noqa: E402


@pytest.fixture(scope="module")
def app(cg_app):
    return cg_app


def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _entrar(app, usuario: str, papel: str):
    d = app.extensions["db"]
    try:
        d.create_user(usuario, "Operador Exemplo", "Senha#12345", papel)
    except Exception:                                              # noqa: BLE001
        pass
    c = app.test_client()
    c.post("/login", data={"username": usuario, "password": "Senha#12345",
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


def _trocar(c, layout: str, proximo: str = "/"):
    pagina = c.get("/").get_data(as_text=True)
    return c.post("/preferencias/layout",
                  data={"layout": layout, "next": proximo, "csrf_token": _token(pagina)})


def test_quem_nao_escolheu_ve_a_moldura_antiga_e_o_convite(app):
    c = _entrar(app, "casca_a", "ADMIN")
    html = c.get("/").get_data(as_text=True)
    assert 'id="app-sidebar"' in html
    assert "cg-app" not in html
    assert "/preferencias/layout" in html


def test_a_escolha_troca_a_moldura_e_nao_desenha_as_duas(app):
    c = _entrar(app, "casca_b", "ADMIN")
    assert _trocar(c, "novo").status_code == 302
    html = c.get("/").get_data(as_text=True)
    assert html.lstrip().lower().startswith("<!doctype"), "algo saiu antes da moldura"
    assert "cg-app" in html
    assert 'id="app-sidebar"' not in html
    assert html.count("data-prod-rapida") == 1
    assert html.count("data-ajuda-gaveta") <= 1


def test_da_para_voltar_ao_layout_antigo(app):
    c = _entrar(app, "casca_c", "ADMIN")
    _trocar(c, "novo")
    _trocar(c, "antigo")
    assert 'id="app-sidebar"' in c.get("/").get_data(as_text=True)


def test_a_escolha_e_de_cada_pessoa(app):
    um = _entrar(app, "casca_d", "ADMIN")
    outro = _entrar(app, "casca_e", "USER")
    _trocar(um, "novo")
    assert 'id="app-sidebar"' in outro.get("/").get_data(as_text=True)


def test_layout_que_nao_existe_nao_grava(app):
    c = _entrar(app, "casca_f", "ADMIN")
    _trocar(c, "qualquer")
    assert 'id="app-sidebar"' in c.get("/").get_data(as_text=True)


def test_a_volta_nao_leva_para_outro_site(app):
    c = _entrar(app, "casca_g", "ADMIN")
    resposta = _trocar(c, "novo", "https://exemplo.invalid/fora")
    assert "exemplo.invalid" not in resposta.headers.get("Location", "")


def test_o_padrao_de_fabrica_e_o_layout_novo():
    """Lido do código: o `conftest` troca o valor em memória para os outros testes."""
    assert 'PADRAO_DE_FABRICA = "novo"' in (RAIZ / "navegacao_web.py").read_text(encoding="utf-8")


def test_quem_nao_escolheu_abre_no_novo_com_o_aviso(app, monkeypatch):
    import navegacao_web as NW
    monkeypatch.setattr(NW, "PADRAO_DE_FABRICA", "novo")
    c = _entrar(app, "casca_padrao_a", "USER")
    html = c.get("/").get_data(as_text=True)
    assert 'class="cg-corpo"' in html and "data-cg-troca" in html
    assert "Ficar neste" in html and "Voltar ao antigo" in html


def test_ficar_neste_faz_o_aviso_sumir(app, monkeypatch):
    import navegacao_web as NW
    monkeypatch.setattr(NW, "PADRAO_DE_FABRICA", "novo")
    c = _entrar(app, "casca_padrao_b", "USER")
    _trocar(c, "novo")
    html = c.get("/").get_data(as_text=True)
    assert 'class="cg-corpo"' in html and "data-cg-troca" not in html


def test_voltar_ao_antigo_vale_mesmo_com_o_padrao_novo(app, monkeypatch):
    import navegacao_web as NW
    monkeypatch.setattr(NW, "PADRAO_DE_FABRICA", "novo")
    c = _entrar(app, "casca_padrao_c", "USER")
    _trocar(c, "antigo")
    html = c.get("/").get_data(as_text=True)
    assert 'id="app-sidebar"' in html and "data-cg-troca" not in html


def test_o_oficial_ainda_pode_devolver_a_casa_ao_antigo(app, monkeypatch):
    import navegacao_web as NW
    monkeypatch.setattr(NW, "PADRAO_DE_FABRICA", "novo")
    d = app.extensions["db"]
    d.set_settings({"layout_padrao": "antigo"})
    try:
        c = _entrar(app, "casca_padrao_d", "USER")
        assert 'id="app-sidebar"' in c.get("/").get_data(as_text=True)
    finally:
        d.set_settings({"layout_padrao": ""})


def test_o_aviso_da_troca_so_sai_para_quem_nao_escolheu():
    molde = (RAIZ / "templates" / "base_novo.html").read_text(encoding="utf-8")
    assert "{% if layout_sem_escolha %}" in molde
    assert molde.count("data-cg-troca") == 1


def test_so_o_oficial_muda_o_padrao_da_casa(app):
    c = _entrar(app, "casca_h", "USER")
    pagina = c.get("/").get_data(as_text=True)
    resposta = c.post("/preferencias/layout/padrao",
                      data={"layout": "novo", "csrf_token": _token(pagina)})
    assert resposta.status_code == 403
    assert app.extensions["db"].get_setting("layout_padrao", "antigo") == "antigo"


def test_a_lista_das_procuracoes_marca_a_secao_e_a_subaba(app):
    """O filtro da lista diz onde a pessoa está: a barra não abre sem nada marcado."""
    c = _entrar(app, "casca_i", "ADMIN")
    _trocar(c, "novo")
    html = c.get("/notas/atos?tipo=PROCURACAO").get_data(as_text=True)
    assert 'class="cg-sec atual"' in html
    assert ">Procurações</a>" in html
    assert "cg-subaba atual" in html


def test_o_botao_novo_abre_a_procuracao_direto(app):
    """O clique fácil do pedido do oficial: sem tela de escolher no meio."""
    c = _entrar(app, "casca_j", "ADMIN")
    _trocar(c, "novo")
    html = c.get("/").get_data(as_text=True)
    assert 'name="modelo_codigo" value="NT-PROC-PUBLICA"' in html
    assert 'name="tipo" value="PROCURACAO"' in html


@pytest.mark.parametrize("onde", NAV.PROCURAR_EM, ids=lambda p: p["endpoint"])
def test_a_lista_le_o_campo_que_a_busca_manda(app, onde):
    """A lista devolve o termo no campo dela: é o que prova que leu.

    A primeira versão mandava `busca` a duas listas que leem `q`. A tela abria, sem
    erro nenhum, com a lista inteira, e a pessoa concluía que o nome não existia.
    """
    c = _entrar(app, "casca_l", "ADMIN")
    with app.test_request_context():
        endereco = url_for(onde["endpoint"])
    html = c.get(endereco, query_string={onde["campo"]: "MARCADOR9"}).get_data(as_text=True)
    assert 'value="MARCADOR9"' in html, f'{endereco} não leu ?{onde["campo"]}='


def test_o_auditor_nao_ve_o_que_nao_pode_fazer(app):
    c = _entrar(app, "casca_k", "AUDITOR")
    _trocar(c, "novo")
    html = c.get("/").get_data(as_text=True)
    assert 'value="NT-PROC-PUBLICA"' not in html
