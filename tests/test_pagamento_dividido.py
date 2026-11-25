# -*- coding: utf-8 -*-
"""Um item do protocolo pago em mais de uma forma — F005, 24/11/2026.

O PROBLEMA, NO BALCÃO
    O cliente quer pagar o registro em duas partes: uma em dinheiro ou Pix e a
    outra no cartão parcelado, pelo link da Parcela Express. O caixa dividia o
    pagamento por item, nunca dentro de um item: dois depósitos do mesmo
    protocolo, um em dinheiro e outro da Parcela, não quitavam o item juntos,
    e o selo ficava travado.

A DECISÃO DO OFICIAL: OPÇÃO B
    Vários depósitos do MESMO protocolo somam para quitar um item, com um
    `cx_deposito_usos` por depósito. O item só fica quitado quando a soma
    fecha ao centavo; enquanto não fecha, segue a pagar e o selo travado.

Dados fictícios: «Pessoa Exemplo», documento de teste, protocolo inventado.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

import pytest

import ato_selado as AS
import caixa_depositos as DEP
import caixa_protocolo as CXP
import cobranca as CB
from bd_nativo import banco
from caixa_schema import CaixaError, cobrar_item_do_protocolo, resumo_caixa

AGORA = datetime(2026, 11, 5, 15, 0, tzinfo=timezone(timedelta(hours=-3)))
HOJE = date(2026, 11, 5)
CARIMBO = "2026-11-05T15:00:00"
GAVETA = "ESCREVENTE EXEMPLO"
PAGADOR = {"nome": "PESSOA EXEMPLO", "documento": "000.000.001-91", "email": "",
           "logradouro": "Rua Um", "numero": "10", "complemento": "", "bairro": "Centro",
           "cidade": "Cidade Exemplo", "uf": "MA", "cep": "65000-000"}


# ------------------------------------------------------------------ o preparo

@pytest.fixture
def casa(cg_casa_logada):
    db = cg_casa_logada["db"]
    with db.transaction() as con:
        bd = banco(con)
        p = bd.escrever(
            """INSERT INTO cx_protocolos (numero, data_abertura, interessado,
                   interessado_documento, criado_em)
               VALUES ('2026.11.901', '2026-11-05', 'PESSOA EXEMPLO', '00000000191',
                       '2026-11-05T09:00:00') RETURNING id""", ())
        pid = int(p[0]["id"])
        item = int(bd.escrever(
            """INSERT INTO cx_protocolo_atos (protocolo_id, descricao, codigo_ato,
                   valor_total, emolumentos, ferc, fadep, femp, ferrfis)
               VALUES (%s, 'Registro de exemplo', '16.1', '1000,00', '800,00',
                       '100,00', '40,00', '40,00', '20,00') RETURNING id""",
            (pid,))[0]["id"])
        gaveta = int(bd.escrever(
            """INSERT INTO cx_caixas (data, operador_nome, aberto_em, situacao)
               VALUES (%s, %s, %s, 'ABERTO') RETURNING id""",
            (HOJE.isoformat(), GAVETA, CARIMBO))[0]["id"])
    return {**cg_casa_logada, "pid": pid, "item": item, "gaveta": gaveta}


def _deposito(db, pid, valor_centavos, *, forma="DINHEIRO", caixa_id=None) -> dict:
    with db.transaction() as con:
        return DEP.criar(con, valor_centavos=valor_centavos, depositante="Pessoa Exemplo",
                         documento="00000000191", agora=CARIMBO, forma_pagamento=forma,
                         caixa_id=caixa_id, protocolo_id=pid, hoje=HOJE)


def _parcela_paga(db, pid, valor_centavos, *, ref="tok-dividido") -> int:
    """A cobrança da Parcela Express paga no cartão — e o caixa a recebe."""
    with db.transaction() as con:
        i = CB.cadastrar(
            con, agora=AGORA, por="balcao", banco_codigo=CB.PARCELA, ambiente="sandbox",
            protocolo_id=pid, valor_centavos=valor_centavos, vencimento="2026-11-20",
            pagador=PAGADOR, mensagem="Emolumentos do protocolo.")
        CB.gravar_resposta(con, i, {
            "situacao": CB.RECEBIDA, "banco_id": ref, "valor_recebido": valor_centavos,
            "data_pagamento": "2026-11-05", "forma_recebida": "CARTAO",
            "banco_status": "paid"}, por="automação", agora=AGORA)
    return i


def _item(db, item_id) -> dict:
    with db.connect() as con:
        return banco(con).um("SELECT * FROM cx_protocolo_atos WHERE id = %s", (item_id,))


def _ler(db, sql, params=()):
    with db.connect() as con:
        return banco(con).ler(sql, params)


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe o csrf_token"
    return achado.group(1)


def _texto(html: str) -> str:
    import html as _html
    return " ".join(_html.unescape(re.sub(r"<[^>]+>", " ", html)).split())


def _ficha(casa) -> str:
    r = casa["c"].get(f"/caixa/protocolos/{casa['pid']}")
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _emitir_recibo(casa):
    tok = _token(_ficha(casa))
    return casa["c"].post(f"/caixa/protocolos/{casa['pid']}/recibo",
                          data={"csrf_token": tok}, follow_redirects=True)


def _recibos(db, pid):
    return _ler(db, "SELECT * FROM cx_recibos WHERE protocolo_id = %s ORDER BY id", (pid,))


def _dividido(casa) -> tuple[dict, int]:
    """O caso do balcão: R$ 400 em dinheiro na gaveta, R$ 600 pela Parcela."""
    d1 = _deposito(casa["db"], casa["pid"], 40000, caixa_id=casa["gaveta"])
    cobranca = _parcela_paga(casa["db"], casa["pid"], 60000)
    return d1, cobranca


# ------------------------------------------------------------ o caso do balcão

def test_dinheiro_mais_parcela_quita_o_item_libera_o_selo_e_o_recibo_diz_as_duas_formas(casa):
    db, pid, item = casa["db"], casa["pid"], casa["item"]
    d1 = _deposito(db, pid, 40000, caixa_id=casa["gaveta"])

    # ANTES DA PARCELA: R$ 400 não pagam um item de R$ 1.000. Nada se debita,
    # o item segue a pagar e o selo continua travado.
    with db.transaction() as con:
        assert DEP.pagar_item(con, item, agora=CARIMBO, quem="balcao",
                              tabela="rg_atos", ato_id=1) is None
    assert _item(db, item)["quitado"] == 0
    assert not CXP.item_pago(_item(db, item))
    assert _ler(db, "SELECT id FROM cx_deposito_usos WHERE item_id = %s", (item,)) == []
    assert "parcial: falta R$ 600,00" in _texto(_ficha(casa))

    i = _parcela_paga(db, pid, 60000)
    with db.connect() as con:
        c = CB.cobranca(con, i)
    assert c["situacao"] == CB.LANCADA and c["deposito_id"]

    # DEPOIS: os dois depósitos somam o item, um uso por depósito.
    linha = _item(db, item)
    assert linha["quitado"] == 1
    assert linha["quitado_por"].startswith("DEPÓSITO PRÉVIO")
    assert CXP.item_pago(linha)
    usos = _ler(db, """SELECT deposito_id, valor_centavos FROM cx_deposito_usos
                        WHERE item_id = %s ORDER BY id""", (item,))
    assert sorted((int(u["deposito_id"]), int(u["valor_centavos"])) for u in usos) == sorted(
        [(int(d1["id"]), 40000), (int(c["deposito_id"]), 60000)])
    assert _ler(db, "SELECT situacao FROM cx_protocolos WHERE id = %s",
                (pid,))[0]["situacao"] == "PAGO"
    # O selo agora acha o item pago — sem debitar de novo.
    with db.transaction() as con:
        assert DEP.pagar_item(con, item, agora=CARIMBO, tabela="rg_atos",
                              ato_id=1) == {"ja_quitado": True}
    assert len(_ler(db, "SELECT id FROM cx_deposito_usos WHERE item_id = %s", (item,))) == 2

    # O RECIBO DO PROTOCOLO: o item pago por depósito entra, com as duas formas.
    _emitir_recibo(casa)
    recibos = _recibos(db, pid)
    assert len(recibos) == 1
    assert recibos[0]["forma_pagamento"] == (
        "Dinheiro R$ 400,00; Cartão (Parcela Express) R$ 600,00")
    assert recibos[0]["valor_total"] == "1.000,00"
    assert _item(db, item)["recibo_id"] == recibos[0]["id"]
    # E o mesmo dinheiro não sai em segundo recibo.
    t = _texto(_emitir_recibo(casa).get_data(as_text=True))
    assert "já estão num recibo" in t
    assert len(_recibos(db, pid)) == 1


def test_o_caixa_por_forma_fecha_e_a_gaveta_conta_so_a_especie(casa):
    db = casa["db"]
    _d1, i = _dividido(casa)
    with db.connect() as con:
        c = CB.cobranca(con, i)
        bd = banco(con)
        gaveta = bd.ler("SELECT * FROM cx_lancamentos WHERE caixa_id = %s ORDER BY id",
                        (casa["gaveta"],))
        dep = bd.um("SELECT * FROM cx_depositos WHERE id = %s", (c["deposito_id"],))
        bancario_id = bd.valor("SELECT caixa_id FROM cx_lancamentos WHERE id = %s",
                               (dep["lancamento_id"],))
        bancario = bd.ler("SELECT * FROM cx_lancamentos WHERE caixa_id = %s ORDER BY id",
                          (bancario_id,))
    assert bancario_id != casa["gaveta"]
    na_gaveta = resumo_caixa(gaveta)
    assert na_gaveta["por_forma"] == {"DINHEIRO": 40000}
    assert na_gaveta["em_especie"] == 40000
    no_banco = resumo_caixa(bancario)
    assert no_banco["por_forma"] == {"CARTAO": 60000}
    assert no_banco["em_especie"] == 0
    # Quitar o item com os depósitos não é entrada nova: nenhum lançamento a mais.
    assert len(gaveta) == 1 and len(bancario) == 1


def test_quitar_duas_vezes_e_recusado(casa):
    db, item = casa["db"], casa["item"]
    _dividido(casa)
    assert _item(db, item)["quitado"] == 1
    with db.transaction() as con, pytest.raises(CaixaError, match="já está quitado"):
        cobrar_item_do_protocolo(con, item, caixa_id=casa["gaveta"], agora=CARIMBO,
                                 hoje="2026-11-05", hora="15:00",
                                 forma_pagamento="DINHEIRO", usuario="balcao")
    with db.transaction() as con:
        assert DEP.pagar_item(con, item, agora=CARIMBO) == {"ja_quitado": True}
        assert DEP.quitar_itens_com_o_deposito(
            con, 1, DEP.prender_itens_a_pagar(con, casa["pid"]), 100000,
            agora=CARIMBO) == []
    assert len(_ler(db, "SELECT id FROM cx_deposito_usos WHERE item_id = %s", (item,))) == 2


def test_o_estorno_de_uma_parte_reabre_o_item(casa):
    db, pid, item = casa["db"], casa["pid"], casa["item"]
    d1, _i = _dividido(casa)
    _emitir_recibo(casa)
    with db.transaction() as con:
        feito = DEP.estornar_parte(con, item, int(d1["id"]), agora=CARIMBO, quem="oficial",
                                   motivo="dinheiro devolvido ao cliente no balcão")
    assert feito["reaberto"] is True and feito["valor_centavos"] == 40000
    assert feito["falta_centavos"] == 40000 and feito["pago_centavos"] == 60000
    linha = _item(db, item)
    assert linha["quitado"] == 0 and linha["quitado_por"] is None
    assert linha["recibo_id"] is None
    assert not CXP.item_pago(linha)
    assert _ler(db, "SELECT situacao FROM cx_protocolos WHERE id = %s",
                (pid,))[0]["situacao"] == "A_PAGAR"
    # O dinheiro voltou ao depósito, com o rastro negativo.
    assert _ler(db, "SELECT saldo FROM cx_depositos WHERE id = %s",
                (d1["id"],))[0]["saldo"] == "400,00"
    assert [int(u["valor_centavos"]) for u in _ler(
        db, "SELECT valor_centavos FROM cx_deposito_usos WHERE deposito_id = %s ORDER BY id",
        (d1["id"],))] == [40000, -40000]
    # A parte da Parcela continua paga: o que falta é só a parte estornada.
    with db.connect() as con:
        assert DEP.pago_do_item(con, item) == 60000
        conta = CB.a_pagar_do_protocolo(con, pid)
    assert conta["devido"] == 40000
    t = _texto(_ficha(casa))
    assert "parcial: R$ 600,00 pagos pelo depósito, falta R$ 400,00" in t
    # O item com parte paga não se cobra inteiro em dinheiro, nem se remove.
    with db.transaction() as con, pytest.raises(CaixaError, match="pagos pelo depósito"):
        cobrar_item_do_protocolo(con, item, caixa_id=casa["gaveta"], agora=CARIMBO,
                                 hoje="2026-11-05", hora="15:00",
                                 forma_pagamento="DINHEIRO", usuario="balcao")
    tok = _token(_ficha(casa))
    t = _texto(casa["c"].post(f"/caixa/protocolos/{pid}/itens",
                              data={"csrf_token": tok, "acao": "remover",
                                    "item_id": str(item)},
                              follow_redirects=True).get_data(as_text=True))
    assert "não se remove" in t and _item(db, item) is not None
    # O depósito que voltou a ter saldo fecha a soma de novo: o selo só
    # debita o que falta.
    with db.transaction() as con:
        feito = DEP.pagar_item(con, item, agora=CARIMBO, tabela="rg_atos", ato_id=2)
    assert feito["valor_centavos"] == 40000
    assert _item(db, item)["quitado"] == 1


def test_a_ficha_do_protocolo_estorna_uma_parte_pelo_botao_do_oficial(casa):
    db, pid, item = casa["db"], casa["pid"], casa["item"]
    d1, _i = _dividido(casa)
    html = _ficha(casa)
    assert "estornar esta parte" in html
    assert "Dinheiro R$ 400,00" in _texto(html)
    tok = _token(html)
    curto = _texto(casa["c"].post(f"/caixa/protocolos/{pid}/itens", data={
        "csrf_token": tok, "acao": "estornar_parte", "item_id": str(item),
        "deposito_id": str(d1["id"]), "motivo": "curto"},
        follow_redirects=True).get_data(as_text=True))
    assert "pelo menos dez letras" in curto and _item(db, item)["quitado"] == 1
    t = _texto(casa["c"].post(f"/caixa/protocolos/{pid}/itens", data={
        "csrf_token": tok, "acao": "estornar_parte", "item_id": str(item),
        "deposito_id": str(d1["id"]), "motivo": "cliente desistiu da parte em dinheiro"},
        follow_redirects=True).get_data(as_text=True))
    assert "R$ 400,00 voltaram ao depósito" in t and "falta R$ 400,00" in t
    assert _item(db, item)["quitado"] == 0
    assert _ler(db, "SELECT count(*) AS n FROM audit_logs WHERE action = %s",
                ("DEPOSITO_PREVIO_PARTE_ESTORNADA",))[0]["n"] == 1


def test_o_estorno_da_reserva_do_selo_devolve_cada_parte_ao_seu_deposito(casa):
    """O selo que não saiu desfaz a quitação somada: cada depósito recebe de
    volta o que saiu dele (`ato_selado._devolver_ao_deposito`)."""
    db, pid, item = casa["db"], casa["pid"], casa["item"]
    d1 = _deposito(db, pid, 40000, caixa_id=casa["gaveta"])
    d2 = _deposito(db, pid, 70000, forma="PIX", caixa_id=casa["gaveta"])
    with db.transaction() as con:
        feito = DEP.pagar_item(con, item, agora=CARIMBO, quem="balcao",
                               tabela="rg_atos", ato_id=9)
    assert feito["valor_centavos"] == 100000 and len(feito["partes"]) == 2
    assert [p["valor_centavos"] for p in feito["partes"]] == [40000, 60000]
    assert _item(db, item)["quitado"] == 1
    with db.transaction() as con:
        AS._devolver_ao_deposito(banco(con), {
            "referencia": "REF-EXEMPLO-1", "valor_centavos": feito["valor_centavos"],
            "deposito_id": feito["deposito_id"], "item_id": item, "tabela": "rg_atos",
            "ato_id": 9, "protocolo_id": pid, "usuario": "balcao"},
            agora=CARIMBO, motivo="o selo não saiu")
    saldos = {int(r["id"]): r["saldo"] for r in _ler(
        db, "SELECT id, saldo FROM cx_depositos WHERE id = ANY(%s)",
        ([int(d1["id"]), int(d2["id"])],))}
    assert saldos == {int(d1["id"]): "400,00", int(d2["id"]): "700,00"}
    assert _item(db, item)["quitado"] == 0
    with db.connect() as con:
        assert DEP.pago_do_item(con, item) == 0


# --------------------------------------------------------------- a regressão

def test_item_pago_inteiro_por_um_deposito_so_continua_como_antes(casa):
    db, pid, item = casa["db"], casa["pid"], casa["item"]
    menor = _deposito(db, pid, 30000, caixa_id=casa["gaveta"])
    inteiro = _deposito(db, pid, 150000, caixa_id=casa["gaveta"])
    with db.transaction() as con:
        feito = DEP.pagar_item(con, item, agora=CARIMBO, tabela="rg_atos", ato_id=3)
    # O depósito que cobre sozinho paga sozinho: um débito, sem partes — e o
    # menor, que não cobria, nem é tocado.
    assert "partes" not in feito
    assert feito["deposito_id"] == int(inteiro["id"]) and feito["valor_centavos"] == 100000
    assert _item(db, item)["quitado_por"] == f"DEPÓSITO PRÉVIO {inteiro['numero']}"
    usos = _ler(db, "SELECT deposito_id FROM cx_deposito_usos WHERE item_id = %s", (item,))
    assert [int(u["deposito_id"]) for u in usos] == [int(inteiro["id"])]
    assert _ler(db, "SELECT saldo FROM cx_depositos WHERE id = %s",
                (menor["id"],))[0]["saldo"] == "300,00"
    # O recibo de item quitado por depósito aparece, com a forma do depósito.
    _emitir_recibo(casa)
    recibos = _recibos(db, pid)
    assert len(recibos) == 1 and recibos[0]["forma_pagamento"] == "Dinheiro"
    assert "Registro de exemplo" in recibos[0]["corpo"]


def test_a_parcela_que_paga_o_item_inteiro_continua_como_antes(casa):
    db, item = casa["db"], casa["item"]
    i = _parcela_paga(db, casa["pid"], 100000)
    with db.connect() as con:
        c = CB.cobranca(con, i)
    assert _item(db, item)["quitado"] == 1
    usos = _ler(db, "SELECT deposito_id, valor_centavos FROM cx_deposito_usos "
                    "WHERE item_id = %s", (item,))
    assert [(int(u["deposito_id"]), int(u["valor_centavos"])) for u in usos] == [
        (int(c["deposito_id"]), 100000)]
    _emitir_recibo(casa)
    assert _recibos(db, casa["pid"])[0]["forma_pagamento"] == "Cartão (Parcela Express)"


def test_o_recibo_ainda_junta_os_itens_pagos_no_caixa(casa):
    """Item quitado no caixa e item pago pelo depósito no mesmo recibo, cada
    forma com o seu valor."""
    db, pid = casa["db"], casa["pid"]
    with db.transaction() as con:
        outro = int(banco(con).escrever(
            """INSERT INTO cx_protocolo_atos (protocolo_id, descricao, codigo_ato,
                   valor_total) VALUES (%s, 'Certidão de exemplo', '16.9', '50,00')
               RETURNING id""", (pid,))[0]["id"])
        cobrar_item_do_protocolo(con, outro, caixa_id=casa["gaveta"], agora=CARIMBO,
                                 hoje="2026-11-05", hora="15:00",
                                 forma_pagamento="PIX", usuario="balcao")
    _parcela_paga(db, pid, 100000)
    _emitir_recibo(casa)
    r = _recibos(db, pid)[0]
    assert r["valor_total"] == "1.050,00"
    assert r["forma_pagamento"] == "Cartão (Parcela Express) R$ 1.000,00; PIX R$ 50,00"


# -------------------------------------------------------------- os avisos

def test_a_parcela_que_nao_fecha_mostra_o_parcial_na_cobranca_e_no_protocolo(casa):
    db, pid, item = casa["db"], casa["pid"], casa["item"]
    _deposito(db, pid, 40000, caixa_id=casa["gaveta"])
    i = _parcela_paga(db, pid, 50000)
    assert _item(db, item)["quitado"] == 0
    with db.connect() as con:
        c = CB.cobranca(con, i)
        rastro = CB.eventos(con, i)
        assert CB.falta_do_protocolo(con, c) == 10000
    assert c["situacao"] == CB.LANCADA
    assert any("parcial: falta R$ 100,00" in str(e.get("detalhe") or e.get("mensagem") or e)
               for e in rastro)
    # O recebimento ficou inteiro no depósito, sem debitar nada do item.
    assert _ler(db, "SELECT saldo FROM cx_depositos WHERE id = %s",
                (c["deposito_id"],))[0]["saldo"] == "500,00"
    ficha = _texto(casa["c"].get(f"/caixa/cobranca/{i}").get_data(as_text=True))
    assert "parcial: falta R$ 100,00" in ficha
    assert "parcial: falta R$ 100,00" in _texto(_ficha(casa))


def test_o_quitar_todos_avisa_que_grava_uma_forma_so(casa):
    t = _texto(_ficha(casa))
    assert "O lote grava uma forma só para todos os itens" in t
    assert "quite item a item" in t
