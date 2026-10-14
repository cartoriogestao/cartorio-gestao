"""Obito nao misture texto/botoes de nascimento — problemas #100 e #101.

Parte A: asserts estaticos nos templates (sem subir o app).
Parte B: HTTP no fluxo /rcpn/novo/... espelhando o relato #46.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


# ----------------------------- A) templates -------------------------------


def test_template_conferencia_tem_ramos_por_especie():
    conf = (RAIZ / "templates" / "rcpn_conferencia.html").read_text(encoding="utf-8")
    assert "{% if especie == 'OBITO' %}" in conf
    assert "RASCUNHO DE REGISTRO DE ÓBITO" in conf
    assert "RASCUNHO DE REGISTRO DE NASCIMENTO" in conf
    assert "RASCUNHO DE REGISTRO DE CASAMENTO" in conf
    assert "<strong>DO:</strong>" in conf
    assert "<strong>DNV:</strong>" in conf
    assert "isento no óbito" in conf
    assert "isento no nascimento" in conf
    assert "CPF do falecido" in conf
    assert "Avós maternos" in conf


def test_template_conferencia_render_obito_nao_parece_nascimento():
    env = Environment(loader=FileSystemLoader(str(RAIZ / "templates")),
                      autoescape=select_autoescape(["html"]))
    conf = (RAIZ / "templates" / "rcpn_conferencia.html").read_text(encoding="utf-8")
    import re as _re
    m = _re.search(
        r'<div style="padding:14px; font-family: Georgia, serif" id="rascunho-declarante">(.*?)</div>',
        conf, _re.S)
    assert m, "bloco rascunho-declarante nao encontrado"
    tpl = env.from_string(m.group(0))
    form = {
        "pessoa_nome": "FULANO", "pessoa_sexo": "M", "data_fato": "2026-09-20",
        "hora_fato": "10:00", "cor_raca": "PARDA",
        "local_fato_nome": "Hospital", "local_fato_endereco": "Rua 1",
        "naturalidade_declarada": "Cidade Exemplo/MA",
        "numero_do": "123456789", "natureza_obito": "1",
        "causa_morte": "natural", "atestante": "Dr X",
        "atestante_documento": "CRM 1", "local_sepultamento": "Cemiterio",
        "filiacao1_nome": "MAE", "filiacao2_nome": "PAI",
        "declarante_nome": "SOBRINHO", "declarante_documento_numero": "111",
        "dnv": "NAO_DEVE_APARECER",
        "prog1f1_nome": "AVO1", "prog2f1_nome": "AVO2",
    }
    html = tpl.render(especie="OBITO", form=form)
    assert "RASCUNHO DE REGISTRO DE ÓBITO" in html
    assert "RASCUNHO DE REGISTRO DE NASCIMENTO" not in html
    assert "123456789" in html
    assert "DO:" in html
    assert "DNV:" not in html
    assert "Avós maternos" not in html
    assert "Falecido(a):" in html
    assert "Óbito:" in html
    assert "NAO_DEVE_APARECER" not in html


def test_template_conferencia_render_nascimento_preservado():
    env = Environment(loader=FileSystemLoader(str(RAIZ / "templates")),
                      autoescape=select_autoescape(["html"]))
    conf = (RAIZ / "templates" / "rcpn_conferencia.html").read_text(encoding="utf-8")
    import re as _re
    m = _re.search(
        r'<div style="padding:14px; font-family: Georgia, serif" id="rascunho-declarante">(.*?)</div>',
        conf, _re.S)
    tpl = env.from_string(m.group(0))
    form = {"pessoa_nome": "BEBE", "dnv": "DNV1",
            "filiacao1_nome": "MAE", "filiacao2_nome": "PAI",
            "prog1f1_nome": "AVO1", "prog2f1_nome": "AVO2",
            "prog1f2_nome": "AVO3", "prog2f2_nome": "AVO4",
            "declarante_nome": "MAE"}
    html = tpl.render(especie="NASCIMENTO", form=form)
    assert "RASCUNHO DE REGISTRO DE NASCIMENTO" in html
    assert "RASCUNHO DE REGISTRO DE ÓBITO" not in html
    assert "DNV:" in html
    assert "Avós maternos" in html


def test_template_novo_obito_sem_botoes_mae_pai_e_sem_parto():
    atrib = (RAIZ / "templates" / "atrib_rcpn_novo.html").read_text(encoding="utf-8")
    assert "Filiação do falecido" in atrib
    assert "problemas #100/#101" in atrib
    assert atrib.count("Mãe (filiação 1)") == 1
    # o unico Mãe (filiação 1) fica dentro do ramo nascimento
    trecho = atrib.split("pessoa('declarante'") 
    # apos o primeiro pessoa('declarante' do nascimento vem a lista; o do obito nao
    assert "[('filiacao1', 'Mãe (filiação 1)')" in atrib
    # ajuda de parto so no ramo nascimento
    assert "ocasião do parto" in atrib


# ----------------------------- B) HTTP (relato 46 style) --------------------


@pytest.fixture()
def c(cg_casa):
    app = cg_casa["app"]
    cg_casa["db"].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                              SENHA, "ADMIN")
    cliente = app.test_client()
    cliente.post("/login",
                 data={"username": "tabeliao", "password": SENHA,
                       "csrf_token": _token(
                           cliente.get("/login").get_data(as_text=True))},
                 follow_redirects=True)
    return cliente


def test_http_obito_nao_oferece_botoes_mae_pai(c):
    html = c.get("/rcpn/novo/obito").get_data(as_text=True)
    assert "Declarante" in html
    assert "copiarDadosDaPessoa('filiacao1', 'declarante')" not in html
    assert "copiarDadosDaPessoa('filiacao2', 'declarante')" not in html
    assert "Mãe (filiação 1)" not in html
    assert "ocasião do parto" not in html
    assert "Filiação do falecido" in html


def test_http_nascimento_ainda_oferece_botoes_mae_pai(c):
    html = c.get("/rcpn/novo/nascimento").get_data(as_text=True)
    assert "copiarDadosDaPessoa('filiacao1', 'declarante')" in html
    assert "Mãe (filiação 1)" in html
    assert "ocasião do parto" in html


def test_http_conferencia_obito(c):
    token = _token(c.get("/rcpn/novo/obito").get_data(as_text=True))
    r = c.post("/rcpn/novo/obito", data={
        "csrf_token": token, "especie": "OBITO", "acao": "conferir",
        "pessoa_nome": "FULANO DE TAL", "pessoa_sexo": "M",
        "data_fato": "2026-09-20", "numero_do": "123456789",
        "causa_morte": "natural", "atestante": "Dr Teste",
        "local_sepultamento": "Cemiterio",
        "filiacao1_nome": "MAE", "filiacao2_nome": "PAI",
        "declarante_nome": "SOBRINHO",
    }, follow_redirects=True)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "RASCUNHO DE REGISTRO DE ÓBITO" in html
    assert "RASCUNHO DE REGISTRO DE NASCIMENTO" not in html
    assert "<strong>DO:</strong>" in html
    assert "isento no óbito" in html
    assert "Avós maternos" not in html
