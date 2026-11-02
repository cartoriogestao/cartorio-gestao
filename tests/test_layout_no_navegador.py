"""O LAYOUT NOVO NUM NAVEGADOR DE VERDADE: o que o servidor sozinho não prova.

POR QUE ESTE TESTE EXISTE
    As fases, os passos e os quadros recolhidos são script e CSS. O HTML pode estar perfeito e o
    balcão ver uma aba em branco, um botão que não faz nada, ou o campo cortado na coluna. Foi
    uma varredura destas, em 30/10/2026, que achou 97 caixas de marcar esticadas em 34 telas, e
    nenhum teste de servidor as enxergaria.

O QUE ELE COBRE
    - Toda tela, em 1920x1080 (os monitores do balcão) e em 1366x768: nenhum erro de script,
      nenhum estouro para o lado, nenhum campo cortado, nenhuma caixa de marcar esticada, e a
      coluna de apoio à vista.
    - Toda ficha em fases: cada aba mostra os quadros dela e só eles, o endereço diz a fase,
      recarregar não perde, e sem script a página sai inteira.
    - Todo formulário em passos: cada porta mostra o bloco dela, e o campo obrigatório vazio em
      outro passo abre esse passo em vez de travar o botão.
    - Todo quadro recolhido: abre pelo endereço, e o campo inválido abre o quadro dele.
    - A moldura: Ctrl+K, o Novo com N, P, Enter, o sino, as gavetas, F1, a troca de layout.

SEM NAVEGADOR, ELE PULA, E DIZ POR QUÊ. `requirements-test.txt` traz o playwright, e ele usa o
Chrome da máquina ou o Chromium do `playwright install chromium`.

A TRAVA FICA LIGADA para o servidor. Só a linha de execução do teste é poupada, porque é ela que
abre o navegador.
"""
from __future__ import annotations

import os
import re
import threading

import pytest

import layout_ensaio as E
from layout_casa import AREAS, areas_pedidas, casa  # noqa: F401

sync_api = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.lento

PISOS = {"todas": 400, "fases": 20, "passos": 8, "quadros": 18}
_FOLGA_DE_LARGURA = 2


@pytest.fixture(scope="module")
def servidor(casa):  # noqa: F811
    from werkzeug.serving import make_server

    E.poupar_esta_linha()
    srv = make_server("127.0.0.1", 0, casa.app, threaded=True)
    linha = threading.Thread(target=srv.serve_forever, daemon=True)
    linha.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()
    E.poupar_esta_linha(False)


@pytest.fixture(scope="module")
def navegador(servidor):
    with sync_api.sync_playwright() as p:
        nav = None
        erros = []
        for pedido in ({"channel": "chrome"}, {}):
            try:
                nav = p.chromium.launch(headless=True, **pedido)
                break
            except Exception as erro:                              # noqa: BLE001
                erros.append(str(erro)[:160])
        if nav is None:
            pytest.skip(f"sem navegador nesta máquina: {erros}")
        yield nav
        nav.close()


def _contexto(casa, navegador, servidor, papel="ADMIN", layout="novo", largura=1920, altura=1080, script=True):  # noqa: F811
    ctx = navegador.new_context(viewport={"width": largura, "height": altura}, locale="pt-BR", java_script_enabled=script)
    casa.preparar_sessao(papel, layout)
    ctx.add_cookies([{"name": "session", "value": casa._sessoes[(papel, layout)], "url": servidor}])
    return ctx


@pytest.fixture(scope="module")
def telas(casa):  # noqa: F811
    """As telas de verdade: resposta em HTML, com moldura, e o que cada uma tem de especial."""
    c = casa.cliente("ADMIN", "novo")
    saida = {"todas": [], "fases": [], "passos": [], "quadros": []}
    for _endpoint, endereco in casa.enderecos(areas_pedidas()):
        r = c.get(endereco)
        if r.status_code != 200 or r.mimetype != "text/html":
            continue
        p = E.ler_pagina(r.get_data(as_text=True))
        if not p.marcas["cg-app"]:
            continue
        saida["todas"].append(endereco)
        if p.regua:
            saida["fases"].append(endereco)
        if p.passos_nav:
            saida["passos"].append(endereco)
        if p.quadros:
            saida["quadros"].append(endereco)
    return saida


def _abrir(pg, servidor, endereco):
    """Os scripts da casa são `defer`, e o CSS está no `head`: no fim do parse, a tela já está de pé."""
    return pg.goto(servidor + endereco, wait_until="domcontentloaded", timeout=60000)


MEDIR = """() => {
  const area = document.querySelector('#conteudo');
  const visivel = e => e.offsetParent !== null;
  const grades = [...document.querySelectorAll('#conteudo .grid2, #conteudo .form-grid')].filter(visivel);
  const cortados = [];
  for (const g of grades) for (const f of g.children) {
    if (visivel(f) && f.scrollWidth > f.clientWidth + 3)
      cortados.push((f.textContent || '').trim().slice(0, 40));
  }
  const marcas = [...document.querySelectorAll('#conteudo input[type=checkbox], #conteudo input[type=radio]')]
    .filter(e => visivel(e) && (e.offsetWidth > 24 || e.offsetHeight > 24));
  const apoio = document.querySelector('.cg-apoio');
  const caixaApoio = apoio ? apoio.getBoundingClientRect() : null;
  const rolagem = document.querySelector('.cg-rolagem') || document.scrollingElement;
  return {estouro: area ? area.scrollWidth - area.clientWidth : 0,
          altura: rolagem.scrollHeight,
          corpo: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          cortados: cortados.slice(0, 3), marcas: marcas.length,
          apoio: caixaApoio ? caixaApoio.right <= innerWidth + 1 && caixaApoio.width > 0 : false,
          esperando: !!document.querySelector('.cg-esperando')};
}"""


def _varrer_a_largura(casa, navegador, servidor, telas, largura, altura):  # noqa: F811
    ctx = _contexto(casa, navegador, servidor, largura=largura, altura=altura)
    # São centenas de telas: o brasão e as fotos só custariam tempo, e não mudam a largura da página.
    ctx.route(re.compile(r"\.(png|jpe?g|gif|webp)(\?|$)", re.I), lambda rota: rota.abort())
    pg = ctx.new_page()
    erros: list[str] = []
    atual = [""]
    pg.on("pageerror", lambda e: erros.append(f"{atual[0]}: erro de script: {str(e)[:200]}"))
    pg.on("response", lambda r: erros.append(f"{atual[0]}: {r.status} em {r.url[-60:]}")
          if "/static/" in r.url and r.status >= 400 else None)
    ruins = []
    alturas = []
    for endereco in telas["todas"]:
        atual[0] = endereco
        try:
            _abrir(pg, servidor, endereco)
            m = pg.evaluate(MEDIR)
        except Exception as erro:                                  # noqa: BLE001
            ruins.append(f"{endereco}: não abriu: {str(erro)[:160]}")
            continue
        alturas.append((m["altura"], endereco))
        if m["estouro"] > _FOLGA_DE_LARGURA or m["corpo"] > _FOLGA_DE_LARGURA:
            ruins.append(f"{endereco}: estoura {m['estouro']} px para o lado (página {m['corpo']})")
        if m["cortados"]:
            ruins.append(f"{endereco}: campo cortado: {m['cortados']}")
        if m["marcas"]:
            ruins.append(f"{endereco}: {m['marcas']} caixa(s) de marcar esticada(s)")
        if not m["apoio"]:
            ruins.append(f"{endereco}: a coluna de apoio não aparece")
        if m["esperando"]:
            ruins.append(f"{endereco}: a ficha ficou esperando o script")
    ctx.close()
    # Só informa: a altura depende do dado, e o que é alto demais quem decide é quem usa a tela.
    if os.environ.get("CG_LAYOUT_ALTURAS"):
        with open(f"{os.environ['CG_LAYOUT_ALTURAS']}_{largura}.txt", "w", encoding="utf-8") as saida:
            saida.write("\n".join(f"{a}\t{e}" for a, e in sorted(alturas, reverse=True)))
    return ruins + erros


def test_toda_tela_em_1920(casa, navegador, servidor, telas):  # noqa: F811
    ruins = _varrer_a_largura(casa, navegador, servidor, telas, 1920, 1080)
    assert not ruins, f"{len(ruins)} achado(s):\n  " + "\n  ".join(ruins[:60])


def test_toda_tela_em_1366(casa, navegador, servidor, telas):  # noqa: F811
    ruins = _varrer_a_largura(casa, navegador, servidor, telas, 1366, 768)
    assert not ruins, f"{len(ruins)} achado(s):\n  " + "\n  ".join(ruins[:60])


def test_a_varredura_viu_as_telas(telas):
    if set(areas_pedidas()) != set(AREAS):
        pytest.skip("rodada de uma área só: o piso é da casa inteira")
    baixos = {k: (len(telas[k]), piso) for k, piso in PISOS.items() if len(telas[k]) < piso}
    assert not baixos, baixos


# ------------------------------------------------------------------- as fases

ESTADO_DAS_FASES = """() => {
  const abas = [...document.querySelectorAll('[data-cg-regua] [data-cg-fase]')].map(a => ({
    chave: a.getAttribute('data-cg-fase'), travada: a.hasAttribute('data-travada'),
    atual: a.getAttribute('aria-current') === 'step'}));
  const quadros = [...document.querySelectorAll('[data-fase]')].filter(q =>
    !q.hasAttribute('data-cg-barra') && !q.hasAttribute('data-cg-so-trava'));
  const vis = quadros.filter(q => !q.hidden && !q.closest('[hidden]'));
  const trava = [...document.querySelectorAll('[data-cg-so-trava]')].filter(q => !q.hidden);
  return {abas, visiveis: vis.map(q => q.getAttribute('data-fase')), trava: trava.map(q => q.getAttribute('data-fase')),
          total: quadros.length};
}"""


def test_cada_aba_mostra_os_quadros_dela_e_so_eles(casa, navegador, servidor, telas):  # noqa: F811
    ctx = _contexto(casa, navegador, servidor)
    pg = ctx.new_page()
    erros: list[str] = []
    atual = [""]
    pg.on("pageerror", lambda e: erros.append(f"{atual[0]}: erro de script: {str(e)[:200]}"))
    ruins = []
    for endereco in telas["fases"]:
        atual[0] = endereco
        _abrir(pg, servidor, endereco)
        inicial = pg.evaluate(ESTADO_DAS_FASES)
        if sum(a["atual"] for a in inicial["abas"]) != 1:
            ruins.append(f"{endereco}: ao abrir, {sum(a['atual'] for a in inicial['abas'])} abas marcadas")
        for aba in inicial["abas"]:
            pg.evaluate("(c) => { location.hash = c; }", aba["chave"])
            pg.wait_for_function("(c) => document.querySelector(`[data-cg-regua] [data-cg-fase=\"${c}\"]`).getAttribute('aria-current') === 'step'",
                                 arg=aba["chave"], timeout=5000)
            e = pg.evaluate(ESTADO_DAS_FASES)
            alheios = sorted(set(e["visiveis"]) - {aba["chave"]})
            if alheios:
                ruins.append(f"{endereco}#{aba['chave']}: mostra quadro de outra fase: {alheios}")
            if aba["travada"]:
                if e["visiveis"]:
                    ruins.append(f"{endereco}#{aba['chave']}: fase travada mostrando quadro")
                if aba["chave"] not in e["trava"]:
                    ruins.append(f"{endereco}#{aba['chave']}: fase travada sem dizer por quê")
            elif aba["chave"] not in e["visiveis"]:
                ruins.append(f"{endereco}#{aba['chave']}: aba em branco")
    ctx.close()
    ruins += erros
    assert not ruins, f"{len(ruins)} achado(s):\n  " + "\n  ".join(ruins[:60])


def test_o_endereco_diz_a_fase_e_recarregar_nao_perde(casa, navegador, servidor, telas):  # noqa: F811
    ctx = _contexto(casa, navegador, servidor)
    pg = ctx.new_page()
    ruins = []
    for endereco in telas["fases"]:
        _abrir(pg, servidor, endereco)
        abas = [a for a in pg.evaluate(ESTADO_DAS_FASES)["abas"]]
        fechadas = [a["chave"] for a in abas if not a["atual"]]
        if not fechadas:
            continue
        alvo = fechadas[-1]
        _abrir(pg, servidor, f"{endereco.split('#')[0]}#{alvo}")
        e = pg.evaluate(ESTADO_DAS_FASES)
        if next(a["chave"] for a in e["abas"] if a["atual"]) != alvo:
            ruins.append(f"{endereco}#{alvo}: colar o link não abre a fase")
        pg.reload(wait_until="load")
        e = pg.evaluate(ESTADO_DAS_FASES)
        if next(a["chave"] for a in e["abas"] if a["atual"]) != alvo:
            ruins.append(f"{endereco}#{alvo}: recarregar perde a fase")
    ctx.close()
    assert not ruins, "\n  ".join(ruins[:60])


def test_sem_script_a_ficha_sai_inteira(casa, navegador, servidor, telas):  # noqa: F811
    """A régua vira lista de âncoras: nada pode ficar de fora por falta de script."""
    ctx = _contexto(casa, navegador, servidor, script=False)
    pg = ctx.new_page()
    ruins = []
    for endereco in telas["fases"] + telas["passos"]:
        _abrir(pg, servidor, endereco)
        escondidos = pg.locator("#conteudo [data-fase][hidden]:not([data-cg-so-trava]):not([data-cg-barra]), #conteudo [data-passo][hidden]").count()
        if escondidos:
            ruins.append(f"{endereco}: {escondidos} quadro(s) escondido(s) sem script")
    ctx.close()
    assert not ruins, "\n  ".join(ruins[:60])


# ------------------------------------------------------------------- os passos

ABRIR_A_FASE_DOS_PASSOS = """() => {
  const nav = document.querySelector('[data-cg-passos]');
  const quadro = nav && nav.closest('[data-fase]');
  if (quadro) location.hash = quadro.getAttribute('data-fase');
  const recolhido = nav && nav.closest('details');
  if (recolhido) recolhido.open = true;
}"""

ESTADO_DOS_PASSOS = """() => {
  const nav = document.querySelector('[data-cg-passos]');
  const form = document.getElementById(nav.getAttribute('data-cg-passos'));
  const portas = [...nav.querySelectorAll('[data-passo-ir]')].map(b => ({chave: b.getAttribute('data-passo-ir'), atual: b.getAttribute('aria-current') === 'step'}));
  const vis = [...form.querySelectorAll('[data-passo]')].filter(b => !b.hidden).map(b => b.getAttribute('data-passo'));
  const avancar = form.querySelector('[data-passo-avancar]');
  const voltar = form.querySelector('[data-passo-voltar]');
  const barra = form.querySelector('.cg-gravar');
  const caixa = barra ? barra.getBoundingClientRect() : null;
  return {portas, visiveis: [...new Set(vis)], avancar: avancar ? !avancar.hidden : null, voltar: voltar ? !voltar.hidden : null,
          barra: caixa ? caixa.height > 0 && caixa.bottom <= innerHeight + 1 : null, form: form.id};
}"""


def test_cada_porta_mostra_o_bloco_dela(casa, navegador, servidor, telas):  # noqa: F811
    ctx = _contexto(casa, navegador, servidor)
    pg = ctx.new_page()
    erros: list[str] = []
    atual = [""]
    pg.on("pageerror", lambda e: erros.append(f"{atual[0]}: erro de script: {str(e)[:200]}"))
    ruins = []
    for endereco in telas["passos"]:
        atual[0] = endereco
        _abrir(pg, servidor, endereco)
        pg.evaluate("sessionStorage.clear()")
        pg.reload(wait_until="load")
        pg.evaluate(ABRIR_A_FASE_DOS_PASSOS)
        inicio = pg.evaluate(ESTADO_DOS_PASSOS)
        portas = [p["chave"] for p in inicio["portas"]]
        for i, chave in enumerate(portas):
            pg.locator(f'[data-cg-passos] [data-passo-ir="{chave}"]').click()
            e = pg.evaluate(ESTADO_DOS_PASSOS)
            if e["visiveis"] != [chave]:
                ruins.append(f"{endereco}, passo {chave}: mostra {e['visiveis']}")
            if [p["chave"] for p in e["portas"] if p["atual"]] != [chave]:
                ruins.append(f"{endereco}, passo {chave}: a régua não marca")
            if e["avancar"] is not None and e["avancar"] != (i < len(portas) - 1):
                ruins.append(f"{endereco}, passo {chave}: «Avançar» {'à vista' if e['avancar'] else 'sumiu'}")
            if e["voltar"] is not None and e["voltar"] != (i > 0):
                ruins.append(f"{endereco}, passo {chave}: «Voltar» {'à vista' if e['voltar'] else 'sumiu'}")
            if e["barra"] is False:
                ruins.append(f"{endereco}, passo {chave}: a barra de gravar saiu da tela")
    ctx.close()
    ruins += erros
    assert not ruins, f"{len(ruins)} achado(s):\n  " + "\n  ".join(ruins[:60])


def test_o_campo_obrigatorio_vazio_abre_o_passo_dele(casa, navegador, servidor, telas):  # noqa: F811
    """A armadilha dos passos: o navegador recusa o envio e não tem onde pôr o foco."""
    ctx = _contexto(casa, navegador, servidor)
    pg = ctx.new_page()
    ruins = []
    testadas = 0
    for endereco in telas["passos"]:
        _abrir(pg, servidor, endereco)
        pg.evaluate("sessionStorage.clear()")
        pg.reload(wait_until="load")
        pg.evaluate(ABRIR_A_FASE_DOS_PASSOS)
        # O botão de gravar mora na barra ou no último passo: é de onde a pessoa clica nele.
        alvo = pg.evaluate("""() => {
          const nav = document.querySelector('[data-cg-passos]');
          const form = document.getElementById(nav.getAttribute('data-cg-passos'));
          const portas = [...nav.querySelectorAll('[data-passo-ir]')].map(b => b.getAttribute('data-passo-ir'));
          const botao = [...form.querySelectorAll('button:not([type=button]):not([formtarget]):not([formnovalidate])')].pop();
          if (!botao) return null;
          botao.dataset.cgTeste = '1';
          const moradia = botao.closest('[data-passo]');
          const fica = moradia ? moradia.getAttribute('data-passo') : null;
          const campo = [...form.querySelectorAll('[data-passo] [required]')].find(c => !c.disabled && !c.value
            && c.closest('[data-passo]').getAttribute('data-passo') !== fica);
          if (!campo) return null;
          const dele = campo.closest('[data-passo]').getAttribute('data-passo');
          const outro = fica || portas.find(p => p !== dele);
          return outro ? {dele, outro, nome: campo.name} : null; }""")
        if not alvo:
            continue
        testadas += 1
        pg.locator(f'[data-cg-passos] [data-passo-ir="{alvo["outro"]}"]').click()
        url = pg.url
        pg.evaluate("() => document.querySelector('button[data-cg-teste]').click()")
        pg.wait_for_timeout(120)
        e = pg.evaluate(ESTADO_DOS_PASSOS)
        if pg.url != url:
            ruins.append(f"{endereco}: o formulário foi com {alvo['nome']} vazio")
        elif e["visiveis"] != [alvo["dele"]]:
            ruins.append(f"{endereco}: {alvo['nome']} vazio não abriu o passo {alvo['dele']}: mostra {e['visiveis']}")
    ctx.close()
    assert not ruins, "\n  ".join(ruins[:60])
    if set(areas_pedidas()) == set(AREAS):
        assert testadas >= 3, f"só {testadas} tela(s) com campo obrigatório nos passos: o teste deixou de achar"


# ------------------------------------------------------------------- os quadros recolhidos

def test_o_endereco_abre_o_quadro_e_o_clique_fecha(casa, navegador, servidor, telas):  # noqa: F811
    ctx = _contexto(casa, navegador, servidor)
    pg = ctx.new_page()
    ruins = []
    for endereco in telas["quadros"]:
        _abrir(pg, servidor, endereco)
        fechado = pg.evaluate("() => { const d = [...document.querySelectorAll('details.cg-quadro[id]')].find(x => !x.open); return d ? d.id : null; }")
        if not fechado:
            continue
        _abrir(pg, servidor, f"{endereco.split('#')[0]}#{fechado}")
        if not pg.evaluate("(i) => document.getElementById(i).open", fechado):
            ruins.append(f"{endereco}#{fechado}: o endereço não abre o quadro")
        pg.evaluate("(i) => document.querySelector(`[id=\"${i}\"] > summary`).click()", fechado)
        if pg.evaluate("(i) => document.getElementById(i).open", fechado):
            ruins.append(f"{endereco}#{fechado}: o clique não fecha o quadro")
    ctx.close()
    assert not ruins, "\n  ".join(ruins[:60])


def test_o_campo_invalido_abre_o_quadro_dele(casa, navegador, servidor, telas):  # noqa: F811
    ctx = _contexto(casa, navegador, servidor)
    pg = ctx.new_page()
    ruins = []
    for endereco in telas["quadros"]:
        _abrir(pg, servidor, endereco)
        achou = pg.evaluate("""() => {
          for (const d of document.querySelectorAll('details.cg-quadro:not([open])')) {
            const c = d.querySelector('input[required]:not([type=hidden]), textarea[required], select[required]');
            if (!c || c.disabled || !c.form) continue;
            c.value = ''; c.dataset.cgTeste = '1'; c.form.dataset.cgTeste = '1'; return d.id || '?';
          } return null; }""")
        if not achou:
            continue
        pg.evaluate("() => document.querySelector('form[data-cg-teste]').reportValidity()")
        pg.wait_for_timeout(50)
        if not pg.evaluate("() => { const c = document.querySelector('[data-cg-teste]:not(form)'); return !!c.closest('details').open; }"):
            ruins.append(f"{endereco}: o campo inválido não abriu o quadro {achou}")
    ctx.close()
    assert not ruins, "\n  ".join(ruins[:60])


# ------------------------------------------------------------------- a moldura

@pytest.fixture
def tela(casa, navegador, servidor):  # noqa: F811
    casa.restaurar()
    ctx = _contexto(casa, navegador, servidor)
    pg = ctx.new_page()
    erros: list[str] = []
    pg.on("pageerror", lambda e: erros.append(str(e)[:200]))
    _abrir(pg, servidor, "/")
    yield pg
    ctx.close()
    assert not erros, erros


def test_ctrl_k_abre_a_busca_e_esc_fecha(tela):
    assert tela.locator("[data-cg-paleta]").is_hidden()
    tela.keyboard.press("Control+k")
    assert tela.locator("[data-cg-paleta]").is_visible()
    assert tela.evaluate("document.activeElement.hasAttribute('data-cg-paleta-q')")
    tela.keyboard.press("Escape")
    assert tela.locator("[data-cg-paleta]").is_hidden()


def test_a_busca_acha_sem_acento_e_no_plural_e_leva_a_tela(tela):
    tela.keyboard.press("Control+k")
    tela.keyboard.type("matriculas")
    achados = tela.locator("[data-cg-paleta-l] .cg-pi")
    assert achados.count() >= 2, "a busca não achou «matriculas»"
    assert "matr" in achados.first.inner_text().lower()
    with tela.expect_navigation(wait_until="load"):
        tela.keyboard.press("Enter")
    assert tela.locator(".cg-app").count() == 1
    assert "/registro-imoveis" in tela.url


def test_a_busca_procura_o_nome_nas_listas(tela):
    tela.keyboard.press("Control+k")
    tela.keyboard.type("MARCADOR9")
    rotulos = tela.locator("[data-cg-paleta-l] .cg-pi").all_inner_texts()
    assert len(rotulos) >= 3, rotulos
    with tela.expect_navigation(wait_until="load"):
        tela.locator("[data-cg-paleta-l] .cg-pi").first.click()
    assert "MARCADOR9" in tela.url


def test_n_abre_o_novo_e_a_letra_e_o_enter_abrem_a_procuracao(tela):
    """O clique fácil do pedido do oficial: N, P, Enter, e a ficha da procuração aberta."""
    tela.keyboard.press("n")
    assert tela.locator("#cg-novo").evaluate("d => d.open")
    assert tela.evaluate("document.activeElement.hasAttribute('data-cg-novo-filtro')")
    tela.keyboard.type("p")
    with tela.expect_navigation(wait_until="load"):
        tela.keyboard.press("Enter")
    assert re.search(r"/notas/atos/\d+", tela.url), tela.url
    assert tela.locator("[data-cg-regua]").count() == 1


def test_n_nao_abre_o_novo_de_quem_esta_digitando(tela, servidor):
    _abrir(tela, servidor, "/registro-imoveis/protocolo")
    campo = tela.locator("#conteudo input:not([type=hidden],[type=checkbox],[type=radio],[type=file]):visible").first
    campo.click()
    tela.keyboard.type("n")
    assert not tela.locator("#cg-novo").evaluate("d => d.open")


def test_o_filtro_do_novo_esconde_o_que_nao_casa(tela):
    tela.keyboard.press("n")
    # O Novo põe o cursor no filtro ao abrir. Numa máquina ocupada isso leva um instante, e a letra de antes se perde.
    tela.wait_for_selector("[data-cg-novo-filtro]:focus")
    tela.keyboard.type("procur")
    tela.wait_for_function("[...document.querySelectorAll('[data-cg-novo-item]')].some(e => e.offsetParent === null)")
    visiveis = tela.locator("[data-cg-novo-item]:visible")
    assert 1 <= visiveis.count() < tela.locator("[data-cg-novo-item]").count()
    for i in range(visiveis.count()):
        assert "rocura" in (visiveis.nth(i).get_attribute("data-rotulo") or "")


def test_o_que_abre_por_cima_fecha_com_esc_e_com_clique_fora(tela):
    tela.locator(".cg-botao-sino").click()
    assert tela.locator("#cg-sino").evaluate("d => d.open")
    tela.keyboard.press("Escape")
    assert not tela.locator("#cg-sino").evaluate("d => d.open")
    tela.locator(".cg-botao-sino").click()
    tela.locator("#conteudo").click(position={"x": 5, "y": 5})
    assert not tela.locator("#cg-sino").evaluate("d => d.open")


def test_abrir_um_fecha_o_outro(tela):
    tela.locator(".cg-botao-sino").click()
    tela.locator(".cg-botao-novo").click()
    assert tela.locator("#cg-novo").evaluate("d => d.open")
    assert not tela.locator("#cg-sino").evaluate("d => d.open")


def test_o_sino_conta_o_que_tem(tela):
    quantos = tela.evaluate("document.querySelectorAll('[data-cg-sino-corpo] .barra-fixa, [data-cg-sino-corpo] .flash, [data-cg-sino-corpo] [data-cg-aviso]').length")
    conta = tela.locator("[data-cg-sino-conta]")
    if quantos:
        assert conta.inner_text() == str(quantos)
    else:
        assert conta.is_hidden()
        tela.locator(".cg-botao-sino").click()
        assert tela.locator("[data-cg-sino-vazio]").is_visible()


def test_uma_gaveta_de_cada_vez(tela):
    """Produtividade, ajuda e agente na coluna de apoio: abrir uma fecha a outra."""
    produtividade = tela.locator(".cg-apoio .prod-rapida-btn")
    ajuda = tela.locator(".cg-apoio .ajuda-chamar")
    assert produtividade.count() == 1
    produtividade.click()
    painel = tela.locator("[data-prod-painel]")
    assert painel.is_visible()
    if ajuda.count():
        ajuda.click()
        assert tela.locator("[data-ajuda-gaveta]").is_visible()
        assert painel.is_hidden()


def test_os_atalhos_de_teclado_abrem_as_gavetas(tela):
    tela.keyboard.press("Alt+p")
    assert tela.locator("[data-prod-painel]").is_visible()
    if tela.locator(".cg-apoio .ajuda-chamar").count():
        tela.keyboard.press("F1")
        assert tela.locator("[data-ajuda-gaveta]").is_visible()


def test_trocar_de_layout_e_voltar_mantem_a_tela(tela, servidor):
    _abrir(tela, servidor, "/registro-imoveis")
    tela.locator(".cg-eu > summary").click()
    with tela.expect_navigation(wait_until="load"):
        tela.locator(".cg-eu button", has_text="Voltar ao layout antigo").click()
    assert "/registro-imoveis" in tela.url
    assert tela.locator("#app-sidebar").count() == 1 and tela.locator(".cg-app").count() == 0
    # Na moldura antiga, o quadro de avisos pode estar por cima do rodapé da barra.
    with tela.expect_navigation(wait_until="load"):
        tela.locator("form[action$='/preferencias/layout'] button").first.evaluate("b => b.click()")
    assert "/registro-imoveis" in tela.url
    assert tela.locator(".cg-app").count() == 1 and tela.locator("#app-sidebar").count() == 0


def test_escolher_so_calculo_tira_o_que_e_do_servico(tela, servidor):
    """Ordem do oficial, 01/11/2026: as duas possibilidades claras, sem poluir a tela."""
    _abrir(tela, servidor, "/caixa/protocolos/novo")
    assert tela.evaluate("location.hash") == "#novo"
    so_do_servico = tela.locator("#bloco-prenotacao-ri")
    assert so_do_servico.is_visible()
    tela.locator(".cx-tipo input[value=ORCAMENTO]").check()
    assert so_do_servico.is_hidden()
    tela.locator(".cx-tipo input[value=SERVICO]").check()
    assert so_do_servico.is_visible()


def test_o_menu_marca_onde_a_pessoa_esta_e_leva_as_subabas(tela, servidor):
    _abrir(tela, servidor, "/registro-imoveis")
    assert tela.locator(".cg-mod.atual").count() == 1
    assert tela.locator(".cg-sec.atual").count() >= 1
    assert tela.locator(".cg-migalhas").count() == 1
    secoes = tela.locator(".cg-sec")
    assert secoes.count() >= 2
    with tela.expect_navigation(wait_until="load"):
        secoes.nth(1).click()
    assert tela.locator(".cg-sec.atual").count() >= 1
