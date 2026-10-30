"""
Testes de PROTOCOLO E CAIXA COMO A MESMA COISA.

A DECISAO DO OFICIAL, EM 27/08/2026
    «Juntemos protocolo geral com o caixa. No caixa/protocolo geral colocamos
    os servicos prestados.»

O QUE HAVIA ANTES, E POR QUE ERA DEFEITO
    O protocolo guardava os servicos com os valores da tabela do tribunal, e
    quitar um item **so marcava uma bandeira**. O dinheiro entrava no caixa por
    OUTRO caminho — o botao «cobrar» da ficha do ato.

    Dois trilhos para o mesmo dinheiro e como eles divergem: o protocolo dizia
    que o cliente pagou, o caixa nao tinha o lancamento, e a conferencia do dia
    fechava com uma diferenca que ninguem sabia de onde vinha.

    Medido em 27/08/2026: `cx_protocolo_atos.lancamento_id` era NULL em
    **32.416 de 32.416**. Nenhum item de protocolo jamais virou dinheiro.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import caixa_schema as CX                            # noqa: E402

AGORA = "2026-08-27T14:30:00"
HOJE, HORA = "2026-08-27", "14:30"


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    # `cx_lancamentos` aponta para `users` em `criado_por`. Num banco de
    # memoria a tabela nao existe, e a chave estrangeira reclama antes de o
    # teste chegar ao que ele quer provar.
    con.execute("CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY)")
    # `cx_protocolos` aponta para a prenotacao e a matricula do RI: o
    # PostgreSQL cobra a FK, e o banco da casa cria as duas antes.
    con.execute("CREATE TABLE IF NOT EXISTS ri_protocolos (id INTEGER PRIMARY KEY)")
    con.execute("CREATE TABLE IF NOT EXISTS ri_matriculas (id INTEGER PRIMARY KEY)")
    CX.init_caixa_schema(con)
    con.execute(
        """INSERT INTO cx_caixas(id, data, operador_nome, situacao, aberto_em)
           VALUES (1, ?, 'ELISA', 'ABERTO', ?)""", (HOJE, AGORA))
    con.execute(
        """INSERT INTO cx_protocolos(id, numero, data_abertura, interessado,
               interessado_documento, situacao, criado_em)
           VALUES (1, '2026.08.103', ?, 'MARIA DAS DORES', '52998224725',
                   'ABERTO', ?)""", (HOJE, AGORA))
    con.execute(
        """INSERT INTO cx_protocolo_atos(id, protocolo_id, descricao,
               codigo_ato, quantidade, valor_total, emolumentos, ferc, fadep,
               femp, ferrfis, quitado)
           VALUES (1, 1, 'Autenticação de cópia', '13.18', 10, '61,70',
                   '55,00', '2,00', '1,50', '1,60', '1,60', 0)""")
    return con


def _quitar(con, item=1, caixa=1):
    return CX.cobrar_item_do_protocolo(
        con, item, caixa_id=caixa, agora=AGORA, hoje=HOJE, hora=HORA,
        usuario="ELISA")


def test_quitar_o_item_poe_dinheiro_no_caixa():
    """Era isto que faltava: a bandeira virava marca, e nao lancamento."""
    con = banco()
    r = _quitar(con)
    linha = con.execute("SELECT * FROM cx_lancamentos WHERE id=?",
                        (r["lancamento_id"],)).fetchone()
    assert linha["valor"] == "61,70"
    assert linha["caixa_id"] == 1
    assert linha["protocolo_id"] == 1
    assert linha["origem"] == "PROTOCOLO"
    assert linha["sentido"] == "ENTRADA"


def test_o_item_fica_amarrado_ao_lancamento():
    """`lancamento_id` era NULL em 32.416 de 32.416 — o elo nunca existiu."""
    con = banco()
    r = _quitar(con)
    item = con.execute("SELECT * FROM cx_protocolo_atos WHERE id=1").fetchone()
    assert item["lancamento_id"] == r["lancamento_id"]
    assert item["quitado"] == 1
    assert item["quitado_por"] == "ELISA"


def test_os_fundos_vao_separados_para_o_caixa():
    """Somar tudo num valor so faria a conferencia dos quatro fundos deixar de
    fechar — e e ela que a inspecao pede."""
    con = banco()
    _quitar(con)
    linha = con.execute("SELECT * FROM cx_lancamentos").fetchone()
    assert linha["emolumentos"] == "55,00"
    assert (linha["ferc"], linha["fadep"], linha["femp"], linha["ferrfis"]) \
        == ("2,00", "1,50", "1,60", "1,60")


def test_o_pagador_sai_do_protocolo_quando_ninguem_o_informa():
    """Quem abriu o protocolo e quem esta pagando, ate alguem dizer outra
    coisa."""
    con = banco()
    _quitar(con)
    linha = con.execute("SELECT * FROM cx_lancamentos").fetchone()
    assert linha["pagador"] == "MARIA DAS DORES"
    assert linha["pagador_documento"] == "52998224725"


def test_o_mesmo_item_nao_se_cobra_duas_vezes():
    """Cobrar duas vezes o mesmo servico e o erro que o cliente descobre no
    extrato."""
    con = banco()
    _quitar(con)
    with pytest.raises(CX.CaixaError, match="já entrou no caixa"):
        _quitar(con)


def _estornar_como_a_tela(con, lancamento_id):
    """O que o estorno do caixa (caixa_web, F13) faz com o lançamento e o item."""
    con.execute("UPDATE cx_lancamentos SET estornado=1, motivo_estorno='DUPLICADO' "
                "WHERE id=?", (lancamento_id,))
    con.execute("UPDATE cx_protocolo_atos SET quitado=0, quitado_em=NULL, "
                "quitado_por=NULL, lancamento_id=NULL WHERE lancamento_id=?",
                (lancamento_id,))


def test_depois_do_estorno_o_item_se_quita_de_novo():
    """Problema #137, 22/10/2026: o estorno devolvia o item ao aberto e a chave
    do lançamento estornado continuava presa — quitar de novo era HTTP 500."""
    con = banco()
    primeiro = _quitar(con)["lancamento_id"]
    _estornar_como_a_tela(con, primeiro)
    segundo = _quitar(con)["lancamento_id"]
    assert segundo != primeiro
    chaves = [r["origem_chave"] for r in con.execute(
        "SELECT origem_chave FROM cx_lancamentos ORDER BY id")]
    assert chaves == ["cx_protocolo_atos:1", "cx_protocolo_atos:1#2"]
    item = con.execute("SELECT * FROM cx_protocolo_atos WHERE id=1").fetchone()
    assert item["lancamento_id"] == segundo and item["quitado"] == 1
    # e a terceira vez também
    _estornar_como_a_tela(con, segundo)
    assert _quitar(con)["lancamento_id"]
    assert con.execute("SELECT origem_chave FROM cx_lancamentos ORDER BY id DESC"
                       ).fetchone()["origem_chave"] == "cx_protocolo_atos:1#3"


def test_lancamento_vivo_com_item_aberto_nao_se_cobra_de_novo():
    """Elo quebrado sem estorno não é licença para cobrar outra vez."""
    con = banco()
    _quitar(con)
    con.execute("UPDATE cx_protocolo_atos SET quitado=0, lancamento_id=NULL WHERE id=1")
    with pytest.raises(CX.CaixaError, match="não foi estornado"):  # «já entrou no caixa», relato #52
        _quitar(con)


def test_sem_caixa_aberto_nao_se_cobra():
    """Lancamento sem caixa nao aparece na conferencia do dia: o dinheiro entra
    no sistema e nao entra na gaveta."""
    con = banco()
    with pytest.raises(CX.CaixaError, match="caixa aberto"):
        _quitar(con, caixa=0)


def test_item_que_nao_existe_e_recusado():
    con = banco()
    with pytest.raises(CX.CaixaError, match="não está em protocolo"):
        _quitar(con, item=99)


def test_o_valor_NAO_se_recalcula_na_quitacao():
    """Ele foi calculado quando o item entrou, pela tabela vigente na data.

    Recalcular faria o cliente pagar um preco diferente do que lhe foi dito no
    balcao — e tabela nova entre uma coisa e outra e exatamente o caso.
    """
    con = banco()
    con.execute("UPDATE cx_protocolo_atos SET valor_total='99,99' WHERE id=1")
    r = _quitar(con)
    assert r["valor"] == "99,99"
    assert con.execute("SELECT valor FROM cx_lancamentos WHERE id=?",
                       (r["lancamento_id"],)).fetchone()[0] == "99,99"


def test_a_lista_do_protocolo_mostra_o_que_ja_entrou_no_caixa():
    con = banco()
    antes = CX.itens_do_protocolo(con, 1)
    assert antes[0]["lancamento"] is None
    _quitar(con)
    depois = CX.itens_do_protocolo(con, 1)
    assert depois[0]["lancamento"] is not None
    assert depois[0]["data_lancamento"] == HOJE


def test_a_descricao_do_lancamento_diz_de_que_protocolo_veio():
    """Quem olha o extrato do caixa precisa achar o atendimento."""
    con = banco()
    _quitar(con)
    linha = con.execute("SELECT descricao FROM cx_lancamentos").fetchone()
    assert "2026.08.103" in linha["descricao"]
    assert "Autenticação" in linha["descricao"]


# ---------------- o recibo do atendimento inteiro (27/08/2026)
#
# «Um recibo do protocolo» — decisao do oficial. Quem pede tres copias
# autenticadas e uma certidao na mesma ida ao balcao espera UM papel.


def _sessao(cg_casa):
    """Um sistema de verdade: o recibo mexe em numeracao e hash."""
    import glob
    import re as _re

    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    cg_casa['db'].create_user("t", "ELISA", "Senha#12345", "ADMIN")
    c = app.test_client()

    def tok(html):
        return _re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                          html).group(1)

    c.post("/login", data={"username": "t", "password": "Senha#12345",
                           "csrf_token": tok(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    h = c.get("/caixa").get_data(as_text=True)
    c.post("/caixa", data={"csrf_token": tok(h), "acao": "abrir",
                           "saldo_inicial": "0,00"}, follow_redirects=True)
    h = c.get("/caixa/protocolos").get_data(as_text=True)
    c.post("/caixa/protocolos",
           data={"csrf_token": tok(h), "acao": "novo",
                 "interessado": "MARIA DAS DORES",
                 # 10/10/2026: telefone OU e-mail obrigatório ao abrir
                 # protocolo (ordem do oficial; contato_do_cliente.py).
                 "telefone": "(99) 98888-7777",
                 "atribuicao": "OUTROS"}, follow_redirects=True)
    con = sqlite3.connect(banco)
    con.row_factory = sqlite3.Row
    pid = con.execute(
        "SELECT id FROM cx_protocolos ORDER BY id DESC LIMIT 1").fetchone()["id"]
    return {"c": c, "con": con, "pid": pid, "tok": tok}


def _item(s, valor="18,51"):
    with s["con"]:
        s["con"].execute(
            """INSERT INTO cx_protocolo_atos(protocolo_id, descricao,
                   codigo_ato, quantidade, valor_total, emolumentos, ferc,
                   fadep, femp, ferrfis, quitado)
               VALUES (?,'Autenticação de cópia','13.18',3,?,'16,50','0,60',
                       '0,45','0,48','0,48',0)""", (s["pid"], valor))
    return s["con"].execute(
        "SELECT id FROM cx_protocolo_atos ORDER BY id DESC LIMIT 1").fetchone()["id"]


def _quitar_na_tela(s, item):
    h = s["c"].get(f"/caixa/protocolos/{s['pid']}").get_data(as_text=True)
    return s["c"].post(f"/caixa/protocolos/{s['pid']}/itens",
                       data={"csrf_token": s["tok"](h), "acao": "quitar",
                             "item_id": item, "forma_pagamento": "DINHEIRO"},
                       follow_redirects=True)


def test_quitar_na_tela_lanca_no_caixa(cg_casa):
    s = _sessao(cg_casa)
    t = _quitar_na_tela(s, _item(s)).get_data(as_text=True)
    assert "lançado no caixa" in t
    assert s["con"].execute(
        "SELECT COUNT(*) c FROM cx_lancamentos").fetchone()["c"] == 1


def test_o_recibo_do_atendimento_soma_os_servicos(cg_casa):
    s = _sessao(cg_casa)
    _quitar_na_tela(s, _item(s, "18,51"))
    _quitar_na_tela(s, _item(s, "10,00"))
    h = s["c"].get(f"/caixa/protocolos/{s['pid']}").get_data(as_text=True)
    assert "Recibo do atendimento" in h
    s["c"].post(f"/caixa/protocolos/{s['pid']}/recibo",
                data={"csrf_token": s["tok"](h)}, follow_redirects=True)
    r = s["con"].execute("SELECT * FROM cx_recibos").fetchone()
    assert r["valor_total"] == "28,51"
    assert r["protocolo_numero"]
    assert r["hash_recibo"]
    # TODOS os lançamentos ficam marcados: sem isso o mesmo dinheiro sairia
    # num segundo recibo.
    assert s["con"].execute(
        "SELECT COUNT(*) c FROM cx_lancamentos WHERE recibo_id IS NULL"
    ).fetchone()["c"] == 0


def test_o_mesmo_dinheiro_nao_sai_em_dois_recibos(cg_casa):
    s = _sessao(cg_casa)
    _quitar_na_tela(s, _item(s))
    h = s["c"].get(f"/caixa/protocolos/{s['pid']}").get_data(as_text=True)
    s["c"].post(f"/caixa/protocolos/{s['pid']}/recibo",
                data={"csrf_token": s["tok"](h)}, follow_redirects=True)
    r = s["c"].post(f"/caixa/protocolos/{s['pid']}/recibo",
                    data={"csrf_token": s["tok"](h)}, follow_redirects=True)
    assert "já estão num recibo" in r.get_data(as_text=True)
    assert s["con"].execute(
        "SELECT COUNT(*) c FROM cx_recibos").fetchone()["c"] == 1


def test_sem_servico_quitado_nao_ha_recibo(cg_casa):
    """Recibo é prova de pagamento, e não de orçamento."""
    s = _sessao(cg_casa)
    _item(s)
    h = s["c"].get(f"/caixa/protocolos/{s['pid']}").get_data(as_text=True)
    assert "Recibo do atendimento" not in h
    r = s["c"].post(f"/caixa/protocolos/{s['pid']}/recibo",
                    data={"csrf_token": s["tok"](h)}, follow_redirects=True)
    assert "entrou no caixa ainda" in r.get_data(as_text=True)


def test_desquitar_nao_apaga_dinheiro_do_caixa(cg_casa):
    """Dinheiro que entrou sai por ESTORNO, que deixa rastro.

    Apagar a linha faria a conferência do dia fechar sem que ninguém soubesse
    por quê.
    """
    s = _sessao(cg_casa)
    item = _item(s)
    _quitar_na_tela(s, item)
    h = s["c"].get(f"/caixa/protocolos/{s['pid']}").get_data(as_text=True)
    r = s["c"].post(f"/caixa/protocolos/{s['pid']}/itens",
                    data={"csrf_token": s["tok"](h), "acao": "desquitar",
                          "item_id": item}, follow_redirects=True)
    assert "estorne o lançamento" in r.get_data(as_text=True)
    assert s["con"].execute(
        "SELECT COUNT(*) c FROM cx_lancamentos").fetchone()["c"] == 1
