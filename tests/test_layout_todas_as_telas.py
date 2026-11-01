"""TODAS AS TELAS, NAS DUAS MOLDURAS E COM OS QUATRO PAPÉIS.

POR QUE ESTE TESTE EXISTE
    Ordem do oficial, 31/10/2026: «antes de terminar tudo, precisamos elaborar testes para
    todas as telas e funcoes do novo layout». A suíte fica na moldura antiga (`conftest`), e o
    que conferia as telas novas morava em scripts soltos. Aqui a lista não se escreve: sai da
    tabela de rotas do próprio sistema, e tela nova entra sozinha.

COMO FUNCIONA
    A varredura abre tudo uma vez, olha cada página na hora (`E.conferir_pagina`) e guarda só o
    resumo: são milhares de páginas, e o HTML não cabe na memória. Cada teste abaixo cobra um
    guarda do que ela achou, e a mensagem diz a tela e o que está errado.

O QUE NÃO COBRE
    Aparência, estouro de largura e script: isso é `test_layout_no_navegador`. E não manda
    formulário: isso é `test_layout_todos_os_formularios`.

`CG_LAYOUT_AREAS=ri` e `CG_LAYOUT_PAPEIS=ADMIN` encurtam a rodada de quem está mexendo numa área.
"""
from __future__ import annotations

import os
import re
from collections import Counter

import flask
import pytest

import layout_ensaio as E
from layout_casa import AREAS, area_da_regra, areas_pedidas, casa  # noqa: F401

pytestmark = pytest.mark.lento

COMBINACOES = (("ADMIN", "antigo"), ("ADMIN", "novo"), ("USER", "antigo"), ("USER", "novo"),
               ("MANAGER", "novo"), ("AUDITOR", "novo"))

# Medido em 31/10/2026, com todas as áreas. Fica abaixo do medido de propósito: existe para pegar a
# semente que parou de semear e o leitor que parou de achar, e não para congelar o número.
PISOS = {"telas": 400, "reguas": 20, "passos": 8, "quadros": 18, "formularios": 900}

POR_ROTA_NOS_OUTROS_PAPEIS = 2

# Rota que escreve na resposta aos poucos: abrir não é ler até o fim.
_EM_PEDACOS = "text/event-stream"


class Varredura:
    def __init__(self):
        self.achados: dict[str, list[str]] = {}
        self.respostas: dict[tuple[str, str, str], dict] = {}
        self.contagem: Counter = Counter()
        self.links_da_tela: dict[str, dict[str, str]] = {}

    def anota(self, guarda: str, oque: str) -> None:
        self.achados.setdefault(guarda, []).append(oque)


def _assinatura(p: E.Pagina, endereco: str) -> Counter:
    """O que o servidor recebe do conteúdo da tela. A casca tem os formulários dela."""
    assinatura: Counter = Counter()
    caminho = endereco.split("?")[0]
    for f in p.formularios:
        if not f["no_conteudo"]:
            continue
        campos = tuple(sorted(c["nome"] for c in f["campos"] if c["nome"]))
        botoes = tuple(sorted((b["nome"], b["valor"]) for b in f["botoes"] if b["nome"]))
        # Formulário sem endereço manda para a própria tela: é a mesma coisa que dizer qual é.
        acao = (f["action"] or caminho).split("?")[0]
        assinatura[(acao, f["method"], campos, botoes)] += 1
    return assinatura


def _de_trava(excecao: BaseException) -> bool:
    """Foi a própria trava que caiu sem ninguém tratar: é o limite do teste, e não defeito."""
    return isinstance(excecao, (E.AcaoBloqueada, FileNotFoundError)) and "barrado pela trava" in str(excecao)


@pytest.fixture(scope="module")
def varredura(casa):  # noqa: F811
    v = Varredura()
    excecoes: list[BaseException] = []

    def anota_excecao(_remetente, exception, **_):
        excecoes.append(exception)

    flask.got_request_exception.connect(anota_excecao, casa.app, weak=False)
    papeis = [p.strip() for p in os.environ.get("CG_LAYOUT_PAPEIS", "").split(",") if p.strip()]
    enderecos = casa.enderecos(areas_pedidas())
    # OS OUTROS PAPÉIS VEEM AMOSTRAS DA MESMA FICHA: quem decide o que cada um vê é a rota e o molde, e os
    # estados de cada ficha já passam pelo ADMIN. Sem a amostra, a rodada passa de uma hora.
    amostra: list[tuple[str, str]] = []
    vistas: Counter = Counter()
    for endpoint, endereco in enderecos:
        vistas[endpoint] += 1
        if vistas[endpoint] <= POR_ROTA_NOS_OUTROS_PAPEIS:
            amostra.append((endpoint, endereco))
    for papel, layout in COMBINACOES:
        if papeis and papel not in papeis:
            continue
        c = casa.cliente(papel, layout)
        for endpoint, endereco in (enderecos if papel == "ADMIN" else amostra):
            excecoes.clear()
            quem = f"{papel}/{layout} {endereco}"
            resposta = c.get(endereco)
            corpo = "" if resposta.mimetype == _EM_PEDACOS else resposta.get_data(as_text=resposta.mimetype == "text/html")
            resumo = {"status": resposta.status_code, "local": resposta.headers.get("Location", ""),
                      "tipo": resposta.mimetype, "endpoint": endpoint}
            defeitos = [e for e in excecoes if not _de_trava(e)]
            if defeitos or (resposta.status_code == 500 and not excecoes):
                v.anota("erro", f"{quem}: {[f'{type(e).__name__}: {str(e)[:200]}' for e in defeitos]}")
            if resposta.status_code == 200 and resposta.mimetype == "text/html":
                p = E.ler_pagina(corpo)
                for guarda, oques in E.conferir_pagina(casa.app, p, corpo, layout, endereco, papel).items():
                    for oque in oques:
                        v.anota(guarda, f"{quem}: {oque}")
                resumo["assinatura"] = _assinatura(p, endereco)
                resumo["repetidos"] = {k for k, n in p.ids.items() if n > 1}
                resumo["casca"] = p.marcas["cg-app"] > 0
                resumo["velha"] = p.marcas["app-sidebar"] > 0
                resumo["cabecalho"] = bool(p.cabecalho)
                resumo["menu"] = sorted({l["href"] for l in p.links if not l["no_conteudo"] and l["href"].startswith("/")})
                if layout == "novo":
                    for l in p.links:
                        if l["no_conteudo"] and l["href"].startswith("/") and not l["href"].startswith("/static/"):
                            v.links_da_tela.setdefault(papel, {}).setdefault(l["href"], endereco)
                if layout == "novo":
                    v.contagem["telas"] += papel == "ADMIN"
                    v.contagem["reguas"] += (papel == "ADMIN" and bool(p.regua))
                    v.contagem["passos"] += (papel == "ADMIN" and bool(p.passos_nav))
                    v.contagem["quadros"] += (papel == "ADMIN" and bool(p.quadros))
                    v.contagem["formularios"] += (papel == "ADMIN") * sum(1 for f in p.formularios if f["no_conteudo"])
            v.respostas[(papel, layout, endereco)] = resumo
    flask.got_request_exception.disconnect(anota_excecao, casa.app)
    return v


def _cobrar(v: Varredura, guarda: str, conselho: str = "") -> None:
    achados = v.achados.get(guarda, [])
    assert not achados, f"{conselho}\n{len(achados)} achado(s):\n  " + "\n  ".join(achados[:60])


def test_nenhuma_tela_da_erro(varredura):
    _cobrar(varredura, "erro", "Tela que estoura. Erro de regra é aviso ao balcão, e não HTTP 500.")


def test_as_duas_molduras_respondem_o_mesmo(varredura):
    """A moldura não pode decidir quem entra, nem para onde a tela manda."""
    ruins = []
    for (papel, layout, endereco), novo in varredura.respostas.items():
        if layout != "novo" or (papel, "antigo", endereco) not in varredura.respostas:
            continue
        antigo = varredura.respostas[(papel, "antigo", endereco)]
        if (antigo["status"], antigo["local"], antigo["tipo"]) != (novo["status"], novo["local"], novo["tipo"]):
            ruins.append(f"{papel} {endereco}: antigo {antigo['status']} {antigo['local']} novo {novo['status']} {novo['local']}")
    assert not ruins, "\n  ".join(ruins)


def test_quem_tem_a_barra_antiga_tem_a_casca_na_nova(varredura):
    """Tela que extende `base.html` tem moldura nas duas. Papel de imprimir não tem em nenhuma."""
    ruins = []
    for (papel, layout, endereco), novo in varredura.respostas.items():
        antigo = varredura.respostas.get((papel, "antigo", endereco))
        if layout == "novo" and antigo and "casca" in novo and "velha" in antigo and novo["casca"] != antigo["velha"]:
            ruins.append(f"{papel} {endereco}: barra antiga {antigo['velha']}, casca {novo['casca']}")
    assert not ruins, "\n  ".join(ruins)


def test_a_moldura_e_a_que_a_pessoa_escolheu(varredura):
    _cobrar(varredura, "moldura")


def test_a_barra_diz_onde_a_pessoa_esta(varredura):
    _cobrar(varredura, "lugar", "Tela sem módulo marcado abre com a barra fechada: ponha em `navegacao.PAI`.")


def test_as_ferramentas_de_apoio_acompanham_toda_tela(varredura):
    _cobrar(varredura, "apoio")


def test_as_caixas_fecham_na_ordem(varredura):
    _cobrar(varredura, "caixas", "Caixa torta: no layout novo ela leva junto o que vem depois para outra fase.")


def test_toda_fase_tem_porta_e_toda_porta_tem_quadro(varredura):
    _cobrar(varredura, "fases", "Quadro de fase sem porta fica escondido para sempre, e aba sem quadro abre em branco.")


def test_todo_passo_tem_porta_e_todo_campo_tem_passo(varredura):
    _cobrar(varredura, "passos", "Campo fora dos passos aparece em todos, e bloco sem porta nunca aparece.")


def test_os_quadros_recolhidos_abrem_pelo_endereco_e_pelo_campo_invalido(varredura):
    _cobrar(varredura, "quadros")


def test_todo_formulario_leva_a_uma_rota_e_manda_o_token(varredura):
    _cobrar(varredura, "formularios", "É o defeito de 27/08/2026: tela que não manda o que a rota exige.")


def test_todo_link_leva_a_uma_rota(varredura):
    _cobrar(varredura, "links")


def test_toda_ancora_tem_para_onde_ir(varredura):
    _cobrar(varredura, "ancoras", "Link para um # que não existe na página: o clique não faz nada.")


def test_todo_recurso_existe(varredura):
    _cobrar(varredura, "recursos")


def test_nao_sobra_texto_de_molde_nem_o_nada_do_python_na_tela(varredura):
    _cobrar(varredura, "texto_cru", "«None» num campo é o que o balcão vê, e o que vai no próximo envio.")


# Diferença de propósito entre as molduras: endereço -> o formulário que só existe no novo, e por quê.
SO_NO_NOVO = {
    # O painel de Notas leva as portas de lavrar: é o «clique fácil» do pedido do oficial.
    "/notas": {"/notas/atos/novo"},
}
# O contrário, pelo botão: fora da escritura, o layout novo tira o papel na DOI de propósito. É o exemplo do
# pedido do oficial, «campo da DOI à vista onde não há DOI nenhuma», e `test_notas_fases` cobra.
SO_NO_ANTIGO = {("acao", "papel_doi")}


def test_as_duas_molduras_oferecem_os_mesmos_formularios(varredura):
    """NENHUMA FUNÇÃO SE PERDE: o pedido do oficial, conferido no que o servidor recebe."""
    ruins = []
    for (papel, layout, endereco), novo in varredura.respostas.items():
        antigo = varredura.respostas.get((papel, "antigo", endereco))
        if layout != "novo" or not antigo or "assinatura" not in novo or "assinatura" not in antigo:
            continue
        perdidos = Counter({k: n for k, n in (antigo["assinatura"] - novo["assinatura"]).items()
                            if not SO_NO_ANTIGO & set(k[3])})
        sobrando = Counter({k: n for k, n in (novo["assinatura"] - antigo["assinatura"]).items()
                            if k[0] not in SO_NO_NOVO.get(endereco.split("?")[0], ())})
        if perdidos or sobrando:
            ruins.append(f"{papel} {endereco}: só no antigo {[k[:2] for k in perdidos]} só no novo {[k[:2] for k in sobrando]}")
    assert not ruins, "\n  ".join(ruins[:60])


def test_a_moldura_nova_nao_repete_identificador(varredura):
    """O script acha o quadro pelo id: repetido, ele acha o primeiro, e pode ser o da casca."""
    ruins = []
    for (papel, layout, endereco), novo in varredura.respostas.items():
        antigo = varredura.respostas.get((papel, "antigo", endereco))
        if layout == "novo" and antigo and "repetidos" in novo:
            so = novo["repetidos"] - antigo.get("repetidos", set())
            if so:
                ruins.append(f"{endereco}: {sorted(so)[:6]}")
    assert not ruins, "\n  ".join(ruins[:60])


def test_o_menu_de_cada_papel_nao_leva_a_recusa(varredura, casa):  # noqa: F811
    """Opção que leva à recusa é clique perdido, e no layout novo o menu é o caminho."""
    ruins = []
    for papel in E.PAPEIS:
        resumos = [r for (p, l, _), r in varredura.respostas.items() if p == papel and l == "novo" and "menu" in r]
        if not resumos:
            continue
        c = casa.cliente(papel, "novo")
        vistos = {e: r for (p, l, e), r in varredura.respostas.items() if p == papel and l == "novo"}
        for href in sorted({h for r in resumos for h in r["menu"]}):
            if re.match(r"/(logout|static)\b", href):
                continue
            r = vistos.get(href)
            status = r["status"] if r else c.get(href).status_code
            if status == 403:
                ruins.append(f"{papel}: {href}")
    assert not ruins, "\n  ".join(ruins[:60])


def test_nenhum_link_da_tela_leva_a_recusa(varredura, casa):  # noqa: F811
    """O mesmo clique perdido, dentro da ficha. A recusa é da rota, e vale por rota: basta abrir uma de cada.

    O AUDITOR FICA DE FORA: ele lê as telas do balcão, e elas citam o que só o balcão faz (medido em
    31/10/2026: 208 links). A casa não tem auditor hoje. O menu dele é cobrado no teste acima.
    """
    ruins = []
    for papel, links in varredura.links_da_tela.items():
        if papel == "AUDITOR":
            continue
        c = casa.cliente(papel, "novo")
        por_rota: dict[str, int] = {}
        for (p, l, endereco), r in varredura.respostas.items():
            if p == papel and l == "novo" and r["status"] != 404:
                por_rota.setdefault(r["endpoint"], r["status"])
        for href, onde in sorted(links.items()):
            regra = E.casar(casa.app, href, "GET")
            if regra in (None, "redireciona"):
                continue
            if regra.endpoint not in por_rota:
                resposta = c.get(href)
                if resposta.mimetype != "text/event-stream":
                    resposta.get_data()
                por_rota[regra.endpoint] = resposta.status_code
            if por_rota[regra.endpoint] == 403:
                ruins.append(f"{papel}: em {onde}, o link {href}")
    assert not ruins, f"{len(ruins)} link(s) que levam à recusa:\n  " + "\n  ".join(ruins[:60])


def test_o_admin_que_nao_e_o_titular_nao_ve_o_que_e_do_titular(casa):  # noqa: F811
    """Ordem do oficial, 31/10/2026: a casa tem mais de uma conta de administrador."""
    c = E.entrar(casa.app, "ensaio_outro_admin", "ADMIN", "novo", "Beatriz Exemplo de Souza")
    p = E.ler_pagina(c.get("/").get_data(as_text=True))
    assert "/administrativo/carne-leao" not in {l["href"] for l in p.links}
    assert c.get("/administrativo/carne-leao").status_code == 403
    titular = E.ler_pagina(casa.cliente("ADMIN", "novo").get("/").get_data(as_text=True))
    assert "/administrativo/carne-leao" in {l["href"] for l in titular.links}


def test_a_varredura_viu_o_que_devia(varredura):
    """Varredor que deixa de achar passa calado: o piso o deixa vermelho."""
    if set(areas_pedidas()) != set(AREAS) or os.environ.get("CG_LAYOUT_PAPEIS"):
        pytest.skip("rodada de uma área só: o piso é da casa inteira")
    baixos = {k: (varredura.contagem[k], piso) for k, piso in PISOS.items() if varredura.contagem[k] < piso}
    assert not baixos, f"medido, piso: {baixos}"
