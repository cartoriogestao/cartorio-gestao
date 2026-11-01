"""A ficha do protocolo do caixa, estado por estado, no layout novo.

O QUE ELES DEFENDEM
    A ficha do protocolo geral (`caixa_abas`) não tem fases em ordem: tem abas, e abre em «Itens e
    quitação». O que muda de um estado para outro é quais abas existem, o que cada uma conta e
    avisa, o que espera ação e quais formulários estão na página. O risco é a ficha dizer uma coisa
    e o protocolo estar noutra: pendência que não aparece (ou aparece onde a ficha diz que não deve),
    aba sem quadro, quadro sem aba, formulário que sumiu, ou a moldura antiga oferecendo o que a nova
    não oferece.

COMO
    A semente (`layout_semente_gestao`) abre um protocolo em cada estado, pelas telas. Aqui cada um é
    aberto com o sistema de pé, como o ADMIN no layout novo, e a ficha é lida pelo que o servidor
    entrega. A tabela é o que cada estado promete escrito à mão, e não a saída de `abas_do_protocolo`:
    se a função e a tabela discordarem, o teste acusa.
"""
from __future__ import annotations

import re

import pytest

import caixa_abas as CA
import caixa_web as CW
from layout_casa import casa  # noqa: F401
import layout_ensaio as E
from layout_semente_gestao import ESTADOS_DO_PROTOCOLO

pytestmark = pytest.mark.lento

BASE = [CA.ITENS, CA.DADOS, CA.DOCUMENTOS, CA.EXIGENCIAS, CA.TAREFAS]
#: Os formulários que mexem em item e em dinheiro, e só eles.
ITENS_E_DINHEIRO = {"acrescentar", "quitar", "quitar_todos", "desquitar", "remover"}


def estado(**campos) -> dict:
    return {"documentos": 0, "tarefas": 0, "movimento": None, "espera": 0, **campos}


#: Por estado: a situação gravada, as abas na ordem, (quantos itens, quantos a quitar), quantas
#: exigências avisam na aba delas, quantos documentos e tarefas a ficha conta, quantos lançamentos a aba
#: do movimento conta (None: sem aba), quantos quadros de «o que espera ação», e as ações do formulário
#: que têm de estar na página e as que não podem estar.
TABELA = {
    "aberto": estado(
        situacao="ABERTO", abas=BASE + [CA.ACOMPANHAMENTO], itens=(0, 0), exigencias=0,
        tem={"acrescentar", "encerrar", "contato", "acompanhamento_gerar"},
        nao_tem={"quitar", "quitar_todos", "desquitar", "remover", "reabrir"}),
    "a_pagar": estado(
        situacao="A_PAGAR", abas=BASE + [CA.ACOMPANHAMENTO], itens=(2, 2), exigencias=0,
        tem={"acrescentar", "encerrar", "quitar", "quitar_todos", "remover"}, nao_tem={"desquitar", "reabrir"}),
    "pago": estado(
        situacao="PAGO", abas=BASE + [CA.ACOMPANHAMENTO, CA.MOVIMENTO], itens=(2, 0), exigencias=0, movimento=2,
        tem={"acrescentar", "desquitar", "acompanhamento_trocar"},
        nao_tem={"quitar", "quitar_todos", "remover", "encerrar", "reabrir", "acompanhamento_gerar"}),
    "encerrado": estado(
        situacao="ENTREGUE", abas=BASE + [CA.ACOMPANHAMENTO], itens=(1, 0), exigencias=0,
        tem={"reabrir", "contato"}, nao_tem={"encerrar"}),
    "com_exigencia": estado(
        situacao="A_PAGAR", abas=BASE + [CA.ACOMPANHAMENTO], itens=(1, 1), exigencias=1, documentos=1, tarefas=1,
        espera=1, tem={"acrescentar", "encerrar", "quitar", "quitar_todos"}, nao_tem={"reabrir", "desquitar"}),
    "orcamento": estado(
        situacao="A_PAGAR", abas=BASE, itens=(1, 0), exigencias=0,
        tem={"acrescentar", "encerrar"}, nao_tem={"reabrir", "acompanhamento_gerar", "acompanhamento_trocar"}),
    "ri": estado(
        situacao="A_PAGAR", abas=BASE + [CA.VINCULOS, CA.ACOMPANHAMENTO], itens=(1, 1), exigencias=0,
        tem={"acrescentar", "encerrar", "vincular_ri"}, nao_tem={"reabrir", "desvincular_ri"}),
}

#: O que cada formulário tem de mandar, além do token.
CAMPOS = {
    "acrescentar": {"tabela", "base_calculo", "quantidade"},
    "quitar_todos": {"forma_pagamento"},
    "quitar": {"item_id", "forma_pagamento"},
    "encerrar": {"encerramento", "motivo"},
    "reabrir": {"motivo"},
    "contato": {"telefone", "email"},
    "vincular_ri": {"ri_protocolo_id"},
}


def _selo(html: str, chave: str) -> tuple[int, int]:
    """O que a régua escreve na aba: quantos (`cg-fase-q`) e quantos avisam (`cg-fase-c`)."""
    aba = re.search(rf'<a [^>]*data-cg-fase="{chave}"[^>]*>(.*?)</a>', html, re.S)
    assert aba, f"a régua não tem a aba {chave}"
    conta = re.search(r'cg-fase-q">(\d+)<', aba.group(1))
    avisa = re.search(r'cg-fase-c"[^>]*>(\d+)<', aba.group(1))
    return int(conta.group(1)) if conta else 0, int(avisa.group(1)) if avisa else 0


def _acoes(p) -> set[str]:
    return {b["valor"] for f in p.formularios for b in f["botoes"] if b["nome"] == "acao"}


def _formulario(p, acao: str) -> dict:
    return next(f for f in p.formularios if any(b["nome"] == "acao" and b["valor"] == acao for b in f["botoes"]))


def _ficha(casa, chave: str, layout: str = "novo"):
    pid = casa.ids[f"gestao_protocolo_{chave}"]
    resposta = casa.cliente("ADMIN", layout).get(f"/caixa/protocolos/{pid}")
    assert resposta.status_code == 200, resposta.status_code
    return pid, resposta.get_data(as_text=True)


def test_todo_estado_semeado_tem_a_sua_linha_na_tabela():
    assert set(TABELA) == set(ESTADOS_DO_PROTOCOLO)


@pytest.mark.parametrize("chave", list(TABELA))
def test_a_ficha_de_cada_estado(casa, chave):  # noqa: F811
    esperado = TABELA[chave]
    pid, html = _ficha(casa, chave)
    protocolo = casa.um("SELECT situacao, interessado FROM cx_protocolos WHERE id = %s", (pid,))
    # Sem isto o resto mediria outro protocolo: a semente tem de ter deixado este no estado.
    assert protocolo["situacao"] == esperado["situacao"], (chave, protocolo)
    p = E.ler_pagina(html)
    assert p.html_layout == "novo"
    # Quem é e como está ficam no título, e não somem ao trocar de aba.
    assert protocolo["interessado"] in p.cabecalho and CW.SITUACOES[esperado["situacao"]] in p.cabecalho, p.cabecalho

    # A régua abre em «Itens e quitação», com as abas deste estado, nenhuma travada: não há fases em ordem.
    assert [(r["chave"], r["inicial"]) for r in p.regua] == [(f"protocolo-{pid}", CA.ITENS)]
    assert [a["fase"] for a in p.abas] == esperado["abas"]
    assert not [a["fase"] for a in p.abas if a["travada"]]
    assert not [f for f in p.fases if f["so_trava"] or f["barra"]]
    # Toda aba tem para onde ir e um quadro, e todo quadro mora numa aba: quadro sem aba some da tela.
    assert all(p.ids[a["fase"]] == 1 for a in p.abas), [a["fase"] for a in p.abas if p.ids[a["fase"]] != 1]
    assert {f["fase"] for f in p.fases if f["fase"]} == set(esperado["abas"])
    assert not p.tortas and not [nome for nome, n in p.ids.items() if n > 1]

    # O que cada aba conta e avisa.
    assert _selo(html, CA.ITENS) == esperado["itens"]
    assert _selo(html, CA.EXIGENCIAS) == (0, esperado["exigencias"])
    assert _selo(html, CA.DOCUMENTOS) == (esperado["documentos"], 0)
    assert _selo(html, CA.TAREFAS) == (esperado["tarefas"], 0)
    assert _selo(html, CA.DADOS) == (0, 0)
    if esperado["movimento"] is not None:
        assert _selo(html, CA.MOVIMENTO) == (esperado["movimento"], 0)
    # O documento anexado abre e baixa pelas rotas do anexo.
    anexos = [l["href"] for l in p.links if l["href"].startswith("/arquivo/")]
    assert len(anexos) == 2 * esperado["documentos"], anexos

    # O que espera ação vem no alto, só quando há, e leva à aba onde se resolve.
    espera = [f for f in p.fases if "cg-falta" in f["classes"]]
    assert len(espera) == esperado["espera"]
    if esperado["espera"]:
        painel = re.search(r'<section class="panel cg-falta".*?</section>', html, re.S).group(0)
        abertas = casa.um("SELECT count(*) AS n FROM cx_exigencias WHERE protocolo_id = %s AND situacao = 'ABERTA'",
                          (pid,))["n"]
        assert f"{abertas} nota(s) de exigência aguardando o interessado" in painel
        assert 'href="#exigencias"' in painel

    # Os formulários: o que o estado oferece, o que ele recusa, e o que cada um manda.
    acoes = _acoes(p)
    assert esperado["tem"] <= acoes, sorted(esperado["tem"] - acoes)
    assert not (esperado["nao_tem"] & acoes), sorted(esperado["nao_tem"] & acoes)
    for acao in acoes & set(CAMPOS):
        f = _formulario(p, acao)
        nomes = {c["nome"] for c in f["campos"]}
        assert f["method"] == "post" and "csrf_token" in nomes and CAMPOS[acao] <= nomes, (acao, nomes)


@pytest.mark.parametrize("chave", list(TABELA))
def test_a_moldura_antiga_oferece_o_mesmo(casa, chave):  # noqa: F811
    """A régua só existe no layout novo, e nada se perde por causa dela."""
    _, novo = _ficha(casa, chave, "novo")
    _, antigo = _ficha(casa, chave, "antigo")
    assert not E.ler_pagina(antigo).regua
    assert _acoes(E.ler_pagina(antigo)) == _acoes(E.ler_pagina(novo))


def test_o_encerrado_nao_oferece_item_nem_quitacao(casa):  # noqa: F811
    """Achado por esta semente: o dinheiro entrava no caixa com a situação ainda em ENTREGUE."""
    pid, html = _ficha(casa, "encerrado")
    assert not (ITENS_E_DINHEIRO & _acoes(E.ler_pagina(html)))
    casa.restaurar()
    try:
        casa.postar(f"/caixa/protocolos/{pid}/itens", acao="quitar_todos", forma_pagamento="PIX")
        assert casa.um("SELECT count(*) AS n FROM cx_lancamentos WHERE protocolo_id = %s", (pid,))["n"] == 0
    finally:
        casa.restaurar()


# ------------------------------------------------------------------- os dois protocolos

def test_abrir_protocolo_diz_o_efeito_de_cada_tipo(casa):  # noqa: F811
    """Ordem do oficial, 01/11/2026: serviços de verdade entravam como «mero cálculo», por não estar claro."""
    html = casa.cliente().get("/caixa/protocolos").get_data(as_text=True)
    form = next(f for f in E.ler_pagina(html).formularios if any(c["nome"] == "tipo" and c["tipo"] == "radio" for c in f["campos"]))
    tipos = [c for c in form["campos"] if c["nome"] == "tipo"]
    assert [(c["tipo"], c["valor"], c["marcado"]) for c in tipos] == [("radio", "SERVICO", True), ("radio", "ORCAMENTO", False)]
    for frase in ("emite recepção, orçamento e recibo", "Só exame e cálculo", "não gera prenotação nem reserva valor"):
        assert frase in html, frase
    assert 'id="novo"' in html, "o Novo manda para /caixa/protocolos#novo, e a tela tem de ir ao formulário"


@pytest.mark.parametrize("tipo", ["SERVICO", "ORCAMENTO"])
def test_o_tipo_escolhido_e_o_que_fica_gravado(casa, tipo):  # noqa: F811
    casa.restaurar()
    try:
        r = casa.postar("/caixa/protocolos", acao="novo", tipo=tipo, interessado="Ana Exemplo", telefone="(00) 90000-0000",
                        atribuicao="NOTAS")
        assert r.status_code == 302, r.status_code
        assert casa.um("SELECT tipo FROM cx_protocolos ORDER BY id DESC LIMIT 1")["tipo"] == tipo
    finally:
        casa.restaurar()


def test_a_ficha_de_cada_tipo_diz_o_que_ele_e(casa):  # noqa: F811
    _pid, so_calculo = _ficha(casa, "orcamento")
    assert "Só exame e cálculo" in so_calculo and "só cálculo" in so_calculo
    assert "/caixa/protocolos/novo" in {l["href"] for l in E.ler_pagina(so_calculo).links}
    assert "Protocolo de recepção" not in so_calculo
    _pid, servico = _ficha(casa, "a_pagar")
    assert "Só exame e cálculo" not in servico and "só cálculo" not in servico
    assert "Emitir orçamento" in servico and "Protocolo de recepção" in servico
