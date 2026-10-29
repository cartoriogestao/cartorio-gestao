"""Item gratuito não paga selo pago; ato isento não sela com item cobrado; o selo
cancelado no Portal não volta — 28/10/2026.

    «resolve o problema do selo pago. cancela e abre botao pra emitir outro selo
     gratuito [...] faz o PR para evitar que item gratuito pague selo pago e ato
     isento com item cobrado» — o oficial, sobre a AV-9/2 (mandado do INCRA,
     prenotação 11589): o protocolo foi quitado «em lote» com a forma «Ato
     gratuito», o item ficou com `gratuito = 0`, o ato foi lavrado sem marcar
     isento, e a trava aceitou o item como pagamento do selo cobrado.

O QUE ESTES TESTES GUARDAM
    1. `item_gratuito` lê as DUAS marcas: a do item e a forma do lançamento.
    2. Item gratuito não cobre selo pago — o selo não é pedido, e o quadro diz
       para marcar o ato isento.
    3. Ato isento com item COBRADO ligado a ele não sela; com item gratuito, ou
       sem item, sela.
    4. A tentativa do SID anda quando o selo do SID anterior foi cancelado.
    5. Registrar o cancelamento feito no Portal: o selo vira cancelado no
       razão, a cobertura sai e a unidade volta, o ato fica sem selo — e o
       selo isento novo sai depois.

Nomes fictícios, como em todo teste desta casa.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import ato_selado as AS                                              # noqa: E402
import caixa_protocolo as CXP                                        # noqa: E402
import selador                                                       # noqa: E402
from bd_nativo import banco as _banco                                # noqa: E402
from test_selo_e_caixa import (AGORA, CNS, ESCREVENTE, ISENTO, PAGO,  # noqa: E402,F401
                               _casa, _fechar_as_conexoes, _item, _ligar,
                               _protocolo, _selar, aparelho)


def _gratuito(con, item_id):
    _banco(con).escrever("UPDATE cx_protocolo_atos SET gratuito = 1 WHERE id = %s",
                         (item_id,))
    con.commit()


# ------------------------------------------------------------- as duas marcas


def test_item_gratuito_le_a_marca_do_item_e_a_forma_do_lancamento():
    assert CXP.item_gratuito({"gratuito": 1})
    assert CXP.item_gratuito({"quitado": 1, "lancamento_forma": "GRATUITO"})
    assert not CXP.item_gratuito({"quitado": 1, "lancamento_forma": "DINHEIRO"})
    assert CXP.item_cobrado({"quitado": 1, "lancamento_forma": "PIX"})
    assert not CXP.item_cobrado({"quitado": 1, "lancamento_forma": "GRATUITO"})
    assert not CXP.item_cobrado({"quitado": 0})
    # `item_pago` continua contando o gratuito: é a régua da ficha do protocolo.
    assert CXP.item_pago({"gratuito": 1})


# ------------------------------------------------------------- recusa 1


def test_item_gratuito_nao_paga_selo_pago(aparelho):
    con = _casa()
    p = _protocolo(con)
    item = _item(con, p["protocolo_id"], quitado=1)
    _gratuito(con, item)
    _ligar(con, item)
    r = _selar(con, dados=PAGO)
    assert r["selado"] is False and r.get("aguardando_cobertura") is True, r
    assert aparelho == [], "o selo cobrado foi pedido com item gratuito"
    assert "é gratuito" in r["motivo"] and "isento" in r["motivo"]


def test_item_cobrado_continua_pagando_selo_pago(aparelho):
    con = _casa()
    p = _protocolo(con)
    item = _item(con, p["protocolo_id"], quitado=1)
    _ligar(con, item)
    r = _selar(con, dados=PAGO)
    assert r["selado"] is True and len(aparelho) == 1


# ------------------------------------------------------------- recusa 2


def test_ato_isento_com_item_cobrado_ligado_nao_sela(aparelho):
    con = _casa()
    p = _protocolo(con)
    item = _item(con, p["protocolo_id"], quitado=1)
    _ligar(con, item)
    r = _selar(con, dados=ISENTO)
    assert r["selado"] is False, r
    assert aparelho == []
    assert "isento" in r["motivo"] and "cobrado" in r["motivo"]


def test_ato_isento_com_item_gratuito_ligado_sela(aparelho):
    con = _casa()
    p = _protocolo(con)
    item = _item(con, p["protocolo_id"], quitado=1)
    _gratuito(con, item)
    _ligar(con, item)
    r = _selar(con, dados=ISENTO)
    assert r["selado"] is True and len(aparelho) == 1


def test_ato_isento_sem_item_sela(aparelho):
    con = _casa()
    r = _selar(con, dados=ISENTO)
    assert r["selado"] is True and len(aparelho) == 1


def test_o_aviso_aponta_item_cobrado_no_protocolo_em_atendimento():
    con = _casa()
    p = _protocolo(con)
    _item(con, p["protocolo_id"], quitado=1)
    CXP.atender(con, usuario=ESCREVENTE, protocolo=p["numero"], agora=AGORA)
    con.commit()
    avisos = AS.avisos_do_ato_isento(con, usuario=ESCREVENTE, codigo="16.1")
    assert len(avisos) == 1 and "foi cobrado" in avisos[0]
    assert AS.avisos_do_ato_isento(con, usuario=ESCREVENTE, codigo="16.9") == []


# ------------------------------------------------------------- o SID


def _no_razao(con, numero, tentativa, *, cancelado=False):
    chave = selador.sid(CNS, "PROTESTO", "pt_atos:1", tentativa)
    _banco(con).escrever(
        """INSERT INTO sd_selos(numero, texto, sid, caminho, atribuicao, referencia,
               ambiente, obtido_em, cancelado_em)
           VALUES (%s,'x',%s,'/selo/x','PROTESTO','pt_atos:1','HOMOLOGACAO',%s,%s)""",
        (numero, chave, AGORA, AGORA if cancelado else None))
    con.commit()


def test_a_tentativa_anda_so_quando_o_selo_do_sid_foi_cancelado():
    con = _casa()

    def proxima():
        return AS.proxima_tentativa(con, cns=CNS, atribuicao="PROTESTO",
                                    referencia="pt_atos:1")
    assert proxima() == 1
    _no_razao(con, "SELOEXEMPLOA001", 1)
    assert proxima() == 1                   # selo vivo: o mesmo SID devolve ele
    _banco(con).escrever("UPDATE sd_selos SET cancelado_em = %s", (AGORA,))
    con.commit()
    assert proxima() == 2                   # cancelado: o SID seguinte
    _no_razao(con, "SELOEXEMPLOA002", 2)
    assert proxima() == 2


# ------------------------------------------------------------- o cancelamento


def test_cancelar_no_portal_desfaz_a_cobertura_e_o_isento_sai_depois(aparelho):
    con = _casa()
    p = _protocolo(con)
    item = _item(con, p["protocolo_id"], quitado=1)
    CXP.atender(con, usuario=ESCREVENTE, protocolo=p["numero"], agora=AGORA)
    con.commit()
    r = _selar(con, dados=PAGO)
    assert r["selado"] is True
    numero = r["numero"]
    bd = _banco(con)
    assert bd.valor("SELECT coalesce(quantidade_usada,0) FROM cx_protocolo_atos "
                    "WHERE id = %s", (item,)) == 1

    feito = AS.registrar_cancelamento_no_portal(
        con, numero=numero, motivo="selo saiu cobrado em ato gratuito",
        agora=AGORA, usuario=ESCREVENTE)
    con.commit()
    assert feito["cobertura"] and feito["cobertura"]["item_id"] == item
    assert bd.valor("SELECT cancelado_em FROM sd_selos WHERE numero = %s", (numero,))
    assert bd.valor("SELECT selo FROM pt_atos WHERE id = 1") is None
    assert bd.valor("SELECT coalesce(quantidade_usada,0) FROM cx_protocolo_atos "
                    "WHERE id = %s", (item,)) == 0
    assert not bd.valor("SELECT count(*) FROM cx_selo_coberturas WHERE ato_id = 1 "
                        "AND tabela = 'pt_atos'")

    # o mesmo selo não se cancela duas vezes
    with pytest.raises(AS.AtoError, match="já consta cancelado"):
        AS.registrar_cancelamento_no_portal(con, numero=numero, motivo="de novo, por engano",
                                            agora=AGORA, usuario=ESCREVENTE)

    # e o selo isento novo sai, pelo caminho de sempre
    r2 = _selar(con, dados=ISENTO)
    assert r2["selado"] is True and r2["numero"] != numero
    assert len(aparelho) == 2
