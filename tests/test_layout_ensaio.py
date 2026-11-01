"""Quem vigia o vigia: a trava barra mesmo, o leitor lê certo, e cada guarda acusa o defeito dele.

POR QUE EXISTE
    A varredura de todas as telas passa verde de dois jeitos: com o sistema certo, ou com o guarda
    cego. O segundo é o pior que há neste projeto, e já aconteceu mais de uma vez: varredor que
    parou de achar e passou calado. Aqui cada guarda recebe uma página com o defeito que ele
    existe para pegar, e tem de acusar.

    E a trava é o que permite mandar todo formulário numa máquina que pode ser a da produção:
    se ela deixar de barrar, o teste seguinte reinicia o serviço de verdade.

SÓ LÊ E MONTA NA MEMÓRIA: não abre banco, e roda em qualquer máquina.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from flask import Flask

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout_ensaio as E  # noqa: E402


# ------------------------------------------------------------------- a trava

@pytest.fixture
def trava(tmp_path):
    E.ligar_trava(tmp_path)
    yield tmp_path
    E.desligar_trava()


def test_a_trava_barra_programa(trava):
    with pytest.raises(E.AcaoBloqueada):
        subprocess.run(["whoami"], check=False)
    with pytest.raises(E.AcaoBloqueada):
        os.system("whoami")


def test_a_trava_barra_a_rede_e_o_dns(trava):
    with socket.socket() as s, pytest.raises(E.AcaoBloqueada):
        s.connect(("192.0.2.1", 9))
    with pytest.raises(E.AcaoBloqueada):
        socket.getaddrinfo("exemplo.invalid", 443)


def test_a_trava_barra_tambem_a_propria_maquina(trava):
    """O servidor de produção escuta em 127.0.0.1, e o banco fala em C, por fora do gancho."""
    with socket.socket() as s, pytest.raises(E.AcaoBloqueada):
        s.connect(("127.0.0.1", 8765))


def test_a_trava_deixa_gravar_na_pasta_do_teste(trava):
    alvo = trava / "pode.txt"
    alvo.write_text("sim", encoding="utf-8")
    assert alvo.read_text(encoding="utf-8") == "sim"
    alvo.unlink()


def test_a_trava_barra_gravar_fora_da_pasta_do_teste(trava):
    fora = Path(tempfile.gettempdir()).parent / "cg_teste_nao_pode.txt"
    with pytest.raises(E.AcaoBloqueada):
        fora.write_text("não", encoding="utf-8")
    assert not fora.exists()


def test_a_trava_barra_apagar_fora_da_pasta_do_teste(trava):
    fora = Path(tempfile.gettempdir()).parent / "cg_teste_nao_existe.txt"
    with pytest.raises(E.AcaoBloqueada):
        os.remove(fora)


def test_a_trava_conhece_a_pasta_de_uma_instalacao_real():
    assert E._normal(r"C:\ProgramData\CartorioGestao") in E.pastas_de_instalacao_real()


def test_a_trava_esconde_a_pasta_de_uma_instalacao_real(trava, monkeypatch):
    pasta = trava / "instalacao"
    pasta.mkdir()
    (pasta / "credencial.txt").write_text("segredo", encoding="utf-8")
    monkeypatch.setitem(E._trava, "reais", E._trava["reais"] + [E._normal(pasta)])
    with pytest.raises(FileNotFoundError):
        (pasta / "credencial.txt").read_text(encoding="utf-8")


def test_a_trava_anota_o_que_barrou(trava):
    antes = len(E.tentativas())
    with pytest.raises(E.AcaoBloqueada):
        os.system("whoami")
    assert len(E.tentativas()) == antes + 1
    assert "programa" in E.tentativas()[-1]


def test_a_trava_desligada_nao_atrapalha(tmp_path):
    E.ligar_trava(tmp_path)
    E.desligar_trava()
    assert subprocess.run([sys.executable, "-c", "pass"], check=False).returncode == 0


def test_a_linha_poupada_passa_e_as_outras_nao(trava):
    import threading

    E.poupar_esta_linha()
    try:
        assert subprocess.run([sys.executable, "-c", "pass"], check=False).returncode == 0
        barrou = []

        def outra():
            try:
                os.system("whoami")
            except E.AcaoBloqueada:
                barrou.append(True)

        linha = threading.Thread(target=outra)
        linha.start()
        linha.join()
        assert barrou, "a outra linha passou pela trava"
    finally:
        E.poupar_esta_linha(False)


# ------------------------------------------------------------------- o banco de teste

@pytest.mark.parametrize("dsn", ["host=127.0.0.1 port=5434 user=cg dbname=cartorio",
                                 "host=127.0.0.1 port=5432 user=cg dbname=producao"])
def test_recusa_o_banco_que_nao_e_de_teste(monkeypatch, dsn):
    monkeypatch.setenv("CG_PG_DSN", dsn)
    monkeypatch.setenv("CG_TEST_BACKEND", "pg")
    with pytest.raises(AssertionError, match="não é de teste"):
        E.conferir_que_e_banco_de_teste(object())


@pytest.mark.parametrize("dsn", ["host=127.0.0.1 port=5435 user=cg dbname=cartorio",
                                 "host=127.0.0.1 port=5491 user=cg dbname=cartorio_teste",
                                 "host=127.0.0.1 port=5433 user=cg dbname=cartorio_teste_gw3"])
def test_aceita_o_banco_de_teste(monkeypatch, dsn):
    monkeypatch.setenv("CG_PG_DSN", dsn)
    monkeypatch.setenv("CG_TEST_BACKEND", "pg")
    E.conferir_que_e_banco_de_teste(object())


# ------------------------------------------------------------------- o leitor

def test_o_leitor_manda_o_que_o_navegador_manda():
    p = E.ler_pagina("""<form method="post" action="/x">
      <input type="hidden" name="csrf_token" value="t">
      <input name="vazio"><input name="cheio" value="a">
      <input type="checkbox" name="sim" value="1" checked><input type="checkbox" name="nao" value="1">
      <input type="radio" name="r" value="um"><input type="radio" name="r" value="dois" checked>
      <select name="s"><option value="">--<option value="b" selected>B</select>
      <select name="primeiro"><option value="c">C<option value="d">D</select>
      <select name="m" multiple><option value="e" selected>E<option value="f">F<option value="g" selected>G</select>
      <textarea name="t">linha</textarea>
      <input name="desligado" value="z" disabled>
      <fieldset disabled><input name="tambem" value="z"></fieldset>
      <input type="file" name="arquivo">
      <input type="text" value="sem nome">
      <button name="acao" value="gravar">Gravar</button><button type="button" name="so_tela">Só tela</button>
    </form>""")
    f = p.formularios[0]
    pares = E.como_o_navegador_manda(f, f["botoes"][0])
    assert ("vazio", "") in pares and ("cheio", "a") in pares
    assert ("csrf_token", "t") in pares and ("sim", "1") in pares and ("r", "dois") in pares
    assert ("s", "b") in pares and ("primeiro", "c") in pares and ("t", "linha") in pares and ("acao", "gravar") in pares
    assert ("m", "e") in pares and ("m", "g") in pares and ("m", "f") not in pares
    assert not {"nao", "desligado", "tambem", "arquivo", "so_tela"} & {k for k, _ in pares}


def test_o_campo_com_form_entra_no_formulario_que_ele_aponta():
    p = E.ler_pagina('<form id="a" method="post" action="/x"></form><input name="fora" value="1" form="a"><button form="a" name="b" value="2">B</button>')
    assert [c["nome"] for c in p.formularios[0]["campos"]] == ["fora"]
    assert [b["nome"] for b in p.formularios[0]["botoes"]] == ["b"]


def test_o_campo_de_template_nao_vai():
    p = E.ler_pagina('<form method="post" action="/x"><template><input name="modelo"></template><input name="real"></form>')
    assert [c["nome"] for c in p.formularios[0]["campos"]] == ["real"]


def test_o_leitor_sabe_o_que_esta_no_conteudo_e_o_que_e_da_casca():
    p = E.ler_pagina('<form action="/casca"></form><div class="content"><form action="/tela"></form></div><form action="/depois"></form>')
    assert [(f["action"], f["no_conteudo"]) for f in p.formularios] == [("/casca", False), ("/tela", True), ("/depois", False)]


def test_o_recado_da_tela_e_lido():
    p = E.ler_pagina('<div class="flash danger" data-aviso>Falta o <b>nome</b>.<button>x</button></div>')
    assert p.flashes == [("danger", "Falta o nome.x")]


# ------------------------------------------------------------------- cada guarda acusa o defeito dele

@pytest.fixture(scope="module")
def app():
    a = Flask("guardas")
    for regra, metodos in (("/", ["GET"]), ("/tela", ["GET", "POST"]), ("/so-grava", ["POST"])):
        a.add_url_rule(regra, regra, lambda: "", methods=metodos)
    return a


CASCA = ('<!doctype html><html data-layout="novo"><body class="cg-corpo"><div class="cg-app">'
         '<a class="cg-mod atual" href="/">m</a><div class="content">{}</div>'
         '<aside class="cg-apoio"><button data-prod-rapida></button></aside></div></body></html>')
SCRIPT = '<script src="/static/fases.js"></script>'
REGUA = ('<div class="cg-ficha"><nav data-cg-regua data-chave="k" data-inicial="um" data-foco="">'
         '<a href="#um" data-cg-fase="um">1</a><a href="#dois" data-cg-fase="dois" data-travada>2</a></nav></div>')
PASSOS = ('<nav data-cg-passos="f" data-inicial="a"><button type="button" data-passo-ir="a">1</button>'
          '<button type="button" data-passo-ir="b">2</button></nav>')


def _achados(app, conteudo, layout="novo"):
    html = CASCA.format(conteudo) if layout == "novo" else conteudo
    return E.conferir_pagina(app, E.ler_pagina(html), html, layout, "/tela")


def test_a_pagina_certa_nao_tem_achado(app):
    conteudo = (SCRIPT + REGUA + '<section data-fase="um">q</section><section data-fase="dois" data-cg-so-trava hidden>t</section>'
                + PASSOS + '<form id="f" method="post" action="/tela"><input type="hidden" name="csrf_token" value="t">'
                '<div data-passo="a"><input name="x"></div><div data-passo="b"><input name="y"></div>'
                '<div class="cg-gravar"><button>Gravar</button></div></form>'
                '<a href="/tela">ok</a><a href="#um">fase</a><details class="panel cg-quadro" id="q"><summary>s</summary></details>'
                '<script>var g = "cg-quadros:";</script>')
    assert _achados(app, conteudo) == {}


@pytest.mark.parametrize("guarda,conteudo", [
    ("caixas", "<section><div></section></div>"),
    ("caixas", "<div>"),
    ("caixas", '<form action="/tela"><form action="/tela"></form></form>'),
    ("fases", '<section data-fase="um">quadro sem régua</section>'),
    ("fases", SCRIPT + REGUA.replace('data-inicial="um"', 'data-inicial="tres"') + '<section data-fase="um">q</section>'),
    ("fases", SCRIPT + REGUA + '<section data-fase="tres">sem porta</section><section data-fase="um">q</section>'),
    ("fases", SCRIPT + REGUA.replace(" data-travada", "") + '<section data-fase="um">a dois fica em branco</section>'),
    ("fases", REGUA + '<section data-fase="um">sem o script</section>'),
    ("passos", SCRIPT + PASSOS + '<form id="f" method="post" action="/tela"><div data-passo="a"></div></form>'),
    ("passos", SCRIPT + PASSOS.replace('data-cg-passos="f"', 'data-cg-passos="outro"')
     + '<form id="f" action="/tela"><div data-passo="a"></div><div data-passo="b"></div></form>'),
    ("passos", SCRIPT + PASSOS + '<form id="f" action="/tela"><div data-passo="a"></div><div data-passo="b"></div>'
     '<input name="fora_dos_passos"></form>'),
    ("passos", SCRIPT + PASSOS + '<form id="f" action="/tela"><div data-passo="a"><button>Gravar</button></div><div data-passo="b"></div></form>'),
    ("passos", SCRIPT + '<form id="f" action="/tela"><div data-passo="a"></div></form>'),
    ("quadros", '<details class="panel cg-quadro"><summary>sem id</summary></details><script>var g="cg-quadros:";</script>'),
    ("quadros", '<details class="panel cg-quadro" id="q"><summary>sem as ferramentas</summary></details>'),
    ("formularios", '<form method="post" action="/tela"><button>sem token</button></form>'),
    ("formularios", '<form method="post" action="/nao-existe"><input name="csrf_token"></form>'),
    ("formularios", '<form method="get" action="/so-grava"></form>'),
    ("formularios", '<form method="post" action="/tela"><input name="csrf_token"><button formaction="/nao-existe">b</button></form>'),
    ("formularios", '<form method="post" action="/tela"><input name="csrf_token"><input type="file" name="a"></form>'),
    ("formularios", '<input name="solto" form="nao-existe">'),
    ("links", '<a href="/nao-existe">morto</a>'),
    ("links", '<a href="/static/nao-existe.js">morto</a>'),
    ("recursos", '<script src="/static/nao-existe.js"></script>'),
    ("ancoras", '<a href="#nao-existe">morto</a>'),
    ("texto_cru", '<input name="a" value="None">'),
    ("texto_cru", "<td>None</td>"),
    ("texto_cru", "<p>{{ campo }}</p>"),
    ("texto_cru", "<p>Undefined</p>"),
])
def test_cada_guarda_acusa_o_defeito_dele(app, guarda, conteudo):
    assert guarda in _achados(app, conteudo), _achados(app, conteudo)


def test_a_tela_que_ensina_modelo_pode_citar_as_chaves_mas_nao_o_nada(app):
    html = '<!doctype html><html><body><div id="app-sidebar"></div><p>Use {{ serventia.cidade }}</p></body></html>'
    assert "texto_cru" not in E.conferir_pagina(app, E.ler_pagina(html), html, "antigo", "/ri/modelos")
    assert "texto_cru" in E.conferir_pagina(app, E.ler_pagina(html), html, "antigo", "/tela")
    html = html.replace("{{ serventia.cidade }}", '<input name="a" value="None">')
    assert "texto_cru" in E.conferir_pagina(app, E.ler_pagina(html), html, "antigo", "/ri/modelos")


def test_a_marca_bom_de_um_molde_nao_conta_como_algo_antes_do_doctype(app):
    html = "\ufeff\n\n" + CASCA.format("")
    assert E.conferir_pagina(app, E.ler_pagina(html), html, "novo", "/tela") == {}


def test_o_campo_de_texto_livre_pode_conter_chaves(app):
    """Teor e modelo moram em `textarea`: a chave ali é do usuário, e não sobra de molde."""
    assert "texto_cru" not in _achados(app, '<form action="/tela"><textarea name="t">{{ campo }}</textarea></form>')


@pytest.mark.parametrize("html,layout", [
    ('<!doctype html><html data-layout="novo"><body><div class="cg-app"><div id="app-sidebar"></div></div></body></html>', "novo"),
    ('<!doctype html><html><body><div class="cg-app"></div></body></html>', "antigo"),
    ('<!doctype html><html><body><div id="app-sidebar"></div></body></html>', "novo"),
    ('sobra<!doctype html><html data-layout="novo"><body class="cg-corpo"><div class="cg-app"><aside class="cg-apoio"></aside></div></body></html>', "novo"),
    ('<!doctype html><html><body class="cg-corpo"><div class="cg-app"><aside class="cg-apoio"></aside></div></body></html>', "novo"),
])
def test_a_moldura_errada_e_acusada(app, html, layout):
    assert "moldura" in E.conferir_pagina(app, E.ler_pagina(html), html, layout, "/tela")


def test_a_barra_sem_modulo_marcado_e_acusada(app):
    html = CASCA.format("").replace(' atual"', '"')
    assert "lugar" in E.conferir_pagina(app, E.ler_pagina(html), html, "novo", "/tela")


def test_a_casca_sem_a_produtividade_e_acusada(app):
    html = CASCA.format("").replace("<button data-prod-rapida></button>", "")
    assert "apoio" in E.conferir_pagina(app, E.ler_pagina(html), html, "novo", "/tela")
    assert "apoio" not in E.conferir_pagina(app, E.ler_pagina(html), html, "novo", "/tela", "AUDITOR")


def test_o_botao_de_gravar_no_ultimo_passo_e_o_campo_obrigatorio_a_vista_passam(app):
    conteudo = (SCRIPT + PASSOS + '<form id="f" method="post" action="/tela"><input type="hidden" name="csrf_token">'
                '<input name="motivo" required><div data-passo="a"><button formtarget="_blank">Imprimir</button></div>'
                '<div data-passo="b"><button>Gravar</button></div></form>')
    assert "passos" not in _achados(app, conteudo)


def test_as_marcas_do_layout_novo_nao_valem_no_antigo(app):
    html = '<!doctype html><html><body><div id="app-sidebar"></div><div class="content"><section data-fase="um"></section><div data-passo="a"></div></div></body></html>'
    assert E.conferir_pagina(app, E.ler_pagina(html), html, "antigo", "/tela") == {}


def test_o_formulario_sem_endereco_manda_para_a_propria_tela(app):
    html = '<!doctype html><html><body><div id="app-sidebar"></div><form method="post"><input name="csrf_token"></form></body></html>'
    assert E.conferir_pagina(app, E.ler_pagina(html), html, "antigo", "/tela") == {}
    assert "formularios" in E.conferir_pagina(app, E.ler_pagina(html), html, "antigo", "/nao-existe")
