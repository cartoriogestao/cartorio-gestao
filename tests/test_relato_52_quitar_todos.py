"""RELATO #52 — quitar todos os itens do protocolo com um botão só.

A frase do oficial, de 11/09/2026:

    «Caixa, permitir que um botão quite todos os itens — permitir quitar tudo
     com um botão só.»

MEDIDO ANTES DE CONSTRUIR, na produção de 15/09/2026: há protocolo em `A_PAGAR`
com **37 itens** — 3.964 protocolos em `A_PAGAR` naquele dia —, e cada item
custava um clique, um POST e uma volta de página. O balcão pagava esse preço em
cada pedido do mesmo cliente.

O QUE ESTES TESTES PROVAM, E A ORDEM IMPORTA:

1. o botão existe, diz quantos itens faltam e quanto é o total;
2. ele **some quando não há o que quitar** — botão que não faz nada faz o
   operador procurar defeito onde não há;
3. um clique quita todos e **lança cada um no caixa**, com os quatro fundos
   separados;
4. **o lote usa a mesma função do botão de um item** — não é um INSERT em lote.
   Um caminho só para o dinheiro: dois divergiriam no primeiro conserto;
5. **cada item na sua própria transação**: um que falhe não desfaz os outros, e
   a resposta diz qual falhou e por quê;
6. sem caixa aberto o lote **recusa antes de tentar**, e não N vezes com o mesmo
   aviso — o que resolve é abrir o caixa, e isso se diz uma vez;
7. rodar de novo não cobra de novo.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

OPERADOR = "MARIO EXEMPLO DOS SANTOS"

# Os três itens do protocolo de ensaio: valores diferentes, para a soma do
# rótulo dizer alguma coisa.
ITENS = (("Autenticação de cópia", "13.18", "61,70", "55,00"),
         ("Certidão de inteiro teor", "16.24.4", "100,73", "89,79"),
         ("Reconhecimento de firma", "13.17.2", "11,96", "10,68"))


# ------------------------------------------------------------- ferramentas

def _token(c, rota: str) -> str:
    html = c.get(rota).get_data(as_text=True)
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, f"a tela {rota} não trouxe csrf_token"
    return achado.group(1)


def _abrir_caixa(banco) -> None:
    con = sqlite3.connect(str(banco))
    con.execute("""INSERT INTO cx_caixas (data, operador_nome, situacao,
                                          saldo_inicial, aberto_em)
                   VALUES (?, ?, 'ABERTO', '0,00', ?)""",
                (date.today().isoformat(), OPERADOR, "2026-09-15T09:00:00"))
    con.commit()
    con.close()


def _protocolo(banco, quantos: int = 3) -> int:
    """O protocolo de ensaio, com itens pendentes. Devolve o id."""
    con = sqlite3.connect(str(banco))
    try:
        cur = con.execute(
            """INSERT INTO cx_protocolos (numero, data_abertura, interessado,
                                          interessado_documento, situacao, criado_em)
               VALUES ('2026.09.900', ?, 'CONSTRUTORA ALFA LTDA',
                       '52998224725', 'A_PAGAR', ?)""",
            (date.today().isoformat(), "2026-09-15T09:00:00"))
        protocolo_id = int(cur.lastrowid)
        for descricao, codigo, total, emol in ITENS[:quantos]:
            con.execute(
                """INSERT INTO cx_protocolo_atos
                       (protocolo_id, descricao, codigo_ato, quantidade,
                        valor_total, emolumentos, quitado)
                   VALUES (?,?,?,1,?,?,0)""",
                (protocolo_id, descricao, codigo, total, emol))
        con.commit()
        return protocolo_id
    finally:
        con.close()


def _itens(banco, protocolo_id: int) -> list[dict]:
    con = sqlite3.connect(str(banco))
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(
            "SELECT * FROM cx_protocolo_atos WHERE protocolo_id=? ORDER BY id",
            (protocolo_id,))]
    finally:
        con.close()


def _lancamentos(banco) -> list[dict]:
    con = sqlite3.connect(str(banco))
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(
            "SELECT * FROM cx_lancamentos WHERE origem='PROTOCOLO' ORDER BY id")]
    finally:
        con.close()


def _situacao(banco, protocolo_id: int) -> str:
    con = sqlite3.connect(str(banco))
    try:
        return con.execute("SELECT situacao FROM cx_protocolos WHERE id=?",
                           (protocolo_id,)).fetchone()[0]
    finally:
        con.close()


def _quitar_tudo(c, protocolo_id: int, **campos):
    corpo = {"csrf_token": _token(c, f"/caixa/protocolos/{protocolo_id}"),
             "acao": "quitar_todos"}
    corpo.update(campos)
    return c.post(f"/caixa/protocolos/{protocolo_id}/itens", data=corpo,
                  follow_redirects=True)


# ------------------------------------------------------------------ a tela

def test_a_tela_tem_o_botao_e_ele_diz_quantos_faltam(cg_casa_logada):
    """O rótulo conta porque quem está no balcão precisa saber o que vai sair
    da gaveta antes de clicar — e um rótulo que conta errado é pior que rótulo
    nenhum."""
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo(banco, 3)
    html = cg_casa_logada["c"].get(
        f"/caixa/protocolos/{protocolo_id}").get_data(as_text=True)
    assert 'value="quitar_todos"' in html, "a tela não tem o botão de quitar tudo"
    assert "Quitar os 3 que faltam" in html, "o botão não diz quantos faltam"


def test_o_botao_some_quando_nao_ha_o_que_quitar(cg_casa_logada):
    """Botão que não faz nada faz o operador procurar defeito onde não há."""
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo(banco, 3)
    _abrir_caixa(banco)
    _quitar_tudo(cg_casa_logada["c"], protocolo_id)
    html = cg_casa_logada["c"].get(
        f"/caixa/protocolos/{protocolo_id}").get_data(as_text=True)
    assert 'value="quitar_todos"' not in html, \
        "o botão continua na tela depois de quitar tudo"
    assert _situacao(banco, protocolo_id) == "PAGO"


def test_a_forma_de_pagamento_do_lote_e_escolhida_uma_vez(cg_casa_logada):
    """O pagamento é um só: a forma vale para o lote, e chega a cada
    lançamento."""
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo(banco, 3)
    _abrir_caixa(banco)
    _quitar_tudo(cg_casa_logada["c"], protocolo_id, forma_pagamento="PIX")
    formas = {l["forma_pagamento"] for l in _lancamentos(banco)}
    assert formas == {"PIX"}, f"a forma do lote não chegou aos lançamentos: {formas}"


def test_em_branco_grava_em_branco(cg_casa_logada):
    """Não se adivinha como o cliente pagou — é a mesma regra do item sozinho."""
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo(banco, 2)
    _abrir_caixa(banco)
    _quitar_tudo(cg_casa_logada["c"], protocolo_id)
    assert {l["forma_pagamento"] for l in _lancamentos(banco)} == {None}


# --------------------------------------------------------------- o dinheiro

def test_um_clique_quita_todos_e_lanca_cada_um_no_caixa(cg_casa_logada):
    """A metade que importa: o item não vira só uma bandeira — vira
    lançamento, com os quatro fundos separados."""
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo(banco, 3)
    _abrir_caixa(banco)
    _quitar_tudo(cg_casa_logada["c"], protocolo_id)

    itens = _itens(banco, protocolo_id)
    assert [i["quitado"] for i in itens] == [1, 1, 1], "sobrou item sem quitar"
    assert all(i["lancamento_id"] for i in itens), \
        "item quitado sem lançamento é a bandeira que este módulo consertou"

    lanc = _lancamentos(banco)
    assert len(lanc) == 3, f"esperava um lançamento por item, veio {len(lanc)}"
    # UM LANCAMENTO POR ITEM, e nao um pelo protocolo: e o item que tem o valor
    # da tabela e os fundos. Somar tudo faria a conferencia deixar de fechar.
    assert {l["valor"] for l in lanc} == {"61,70", "100,73", "11,96"}
    assert all(l["caixa_id"] for l in lanc)
    assert _situacao(banco, protocolo_id) == "PAGO"


def test_o_lote_nao_monta_lancamento_por_conta_propria():
    """**O guarda que impede a segunda régua do dinheiro.**

    Se o lote montasse os lançamentos por conta própria, os dois caminhos
    divergiriam no primeiro conserto — e a conferência dos quatro fundos
    deixaria de fechar sem ninguém saber qual dos dois estava certo.
    """
    codigo = (RAIZ / "caixa_web.py").read_text(encoding="utf-8")
    inicio = codigo.index('acao == "quitar_todos"')
    fim = codigo.index('if acao == "desquitar"')
    bloco = codigo[inicio:fim]
    assert "cobrar_item_do_protocolo(" in bloco, \
        "o lote deixou de usar a função do botão de um item"
    assert "INSERT INTO cx_lancamentos" not in bloco, \
        "o lote voltou a montar lançamento por fora do domínio"


def test_cada_item_na_sua_transacao(cg_casa_logada):
    """**Um item que falha não derruba os outros.**

    O terceiro item já tem lançamento pela chave de origem — é o estado que a
    carga repetida do E-Ofício deixa —, e nem por isso o primeiro e o segundo
    deixam de ser quitados. Quem atende não pode ouvir «não deu» e não saber o
    que entrou.
    """
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo(banco, 3)
    _abrir_caixa(banco)
    terceiro = _itens(banco, protocolo_id)[2]["id"]

    con = sqlite3.connect(str(banco))
    con.execute(
        """INSERT INTO cx_lancamentos (caixa_id, protocolo_id, data, hora,
               natureza, sentido, descricao, valor, origem, origem_chave, criado_em)
           VALUES (1, ?, ?, '09:00', 'RECEBIMENTO', 'ENTRADA',
                   'lançamento anterior', '11,96', 'PROTOCOLO', ?, ?)""",
        (protocolo_id, date.today().isoformat(),
         f"cx_protocolo_atos:{terceiro}", "2026-09-15T09:00:00"))
    con.commit()
    con.close()

    r = _quitar_tudo(cg_casa_logada["c"], protocolo_id)
    html = r.get_data(as_text=True)

    itens = _itens(banco, protocolo_id)
    quitados = [i["quitado"] for i in itens]
    assert quitados == [1, 1, 0], f"a falha de um derrubou o lote: {quitados}"
    assert "já entrou no caixa" in html, \
        "a tela não diz por que o item não foi quitado"
    assert "2 itens quitados" in html, "a resposta não diz o que entrou"


def test_sem_caixa_aberto_o_lote_recusa_antes_de_tentar(cg_casa_logada):
    """A recusa vem antes, e não N vezes com o mesmo aviso: o que resolve é
    abrir o caixa, e isso se diz uma vez."""
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo(banco, 3)
    r = _quitar_tudo(cg_casa_logada["c"], protocolo_id)
    html = r.get_data(as_text=True)

    assert _lancamentos(banco) == [], "lançou no caixa sem caixa aberto"
    assert [i["quitado"] for i in _itens(banco, protocolo_id)] == [0, 0, 0]
    assert "caixa aberto" in html, "a recusa não diz o que fazer"
    # Uma vez só: repetir o mesmo aviso três vezes esconde a única coisa que
    # resolve — abrir o caixa.
    assert html.count("Abra o caixa") == 1, \
        "a recusa repetiu o mesmo aviso uma vez por item"


def test_rodar_de_novo_nao_cobra_de_novo(cg_casa_logada):
    """Quem clica duas vezes por dúvida precisa saber que nada foi cobrado a
    mais — e a frase diz isso, em vez de repetir 3 recusas iguais."""
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo(banco, 3)
    _abrir_caixa(banco)
    _quitar_tudo(cg_casa_logada["c"], protocolo_id)
    r = _quitar_tudo(cg_casa_logada["c"], protocolo_id)
    html = r.get_data(as_text=True)

    assert len(_lancamentos(banco)) == 3, "o segundo clique cobrou de novo"
    assert "já foram quitados" in html, \
        "a segunda vez não diz que não há o que quitar"


# ------------------------------------------------------------- a auditoria

def test_o_rastro_diz_que_o_item_entrou_num_lote(cg_casa_logada):
    """Quem for ler a auditoria depois precisa achar cada item quitado pelo
    caminho de sempre **e** saber por que ele entrou sem clique próprio."""
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo(banco, 3)
    _abrir_caixa(banco)
    _quitar_tudo(cg_casa_logada["c"], protocolo_id)

    con = sqlite3.connect(str(banco))
    con.row_factory = sqlite3.Row
    try:
        linhas = [dict(r) for r in con.execute(
            """SELECT * FROM audit_logs
                WHERE action='PROTOCOLO_ITEM_QUITADO' AND entity_id=?""",
            (protocolo_id,))]
    finally:
        con.close()
    assert len(linhas) == 3, "faltou auditoria em item do lote"
    assert all("em_lote" in (l["details"] or "") for l in linhas), \
        "a auditoria do lote não se distingue da do clique único"
