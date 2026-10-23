"""O selo digitado à mão passa pela trava do selo pago — revisão de segurança
da 3.7.0, 22/10/2026, achado A9.

O QUE A REVISÃO MEDIU: a trava do selo pago (3.7.0) vivia num ponto só,
`obter_selo` — e `registrar_selo_obtido_a_mao`, que grava o número que o
escrevente tirou no portal, não passava por ela. Nas sete telas que a chamam
(RI, Notas, Livro 3, RCPJ/RTD, as quatro atribuições), digitar um selo
gravava o ato como selado sem protocolo, sem pagamento e sem liberação do
ADMIN: a porta ao lado da trava.

O CONSERTO: `registrar_selo_obtido_a_mao` chama `cobrir_o_selo` com a
MESMA régua do selo automático e confirma a reserva na mesma transação. O
que a cobertura lê sai do TEXTO do selo — «Selo Isento» é gratuito, e o
item (`Ato 16.1`) escolhe o item do protocolo. Os fixtures são os de
`test_selo_e_caixa.py`, porque a trava tem de ser a mesma nos dois caminhos.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ato_selado as AS                       # noqa: E402
from test_selo_e_caixa import (               # noqa: E402,F401 — fixtures da trava
    _casa, _protocolo, _item, _ligar, _fechar_as_conexoes, AGORA, CNS,
    ESCREVENTE,
)
from test_ato_selado import SELO_BOM, SELO_OUTRO   # noqa: E402

TEXTO_PAGO = ("Selo Digital AVESVD000000NARRKWVNJCRSVO21 Ato: 16.1 "
              "Total R$ 80,00 Emol R$ 60,00 FERC R$ 2,00 "
              "Consulte em https://selo.tjma.jus.br")
TEXTO_ISENTO = ("Selo Digital REGAVD000000OD1Q8BV5TOOZE492 Ato: 16.1 "
                "Total R$ 0,00 Emol R$ 0,00 Selo Isento "
                "Consulte em https://selo.tjma.jus.br")


def _registrar(con, numero=SELO_BOM, *, ato_id=1, texto=TEXTO_PAGO):
    return AS.registrar_selo_obtido_a_mao(
        con, numero, tabela="pt_atos", ato_id=ato_id, atribuicao="PROTESTO",
        agora=AGORA, cns=CNS, usuario=ESCREVENTE, texto=texto)


def _selos(con):
    return AS.banco(con).ler(
        "SELECT numero, tabela, ato_id FROM sd_selos ORDER BY numero")


def _cobertura(con, ato_id=1):
    return AS.banco(con).um(
        "SELECT forma, situacao FROM cx_selo_coberturas WHERE referencia = %s",
        (f"pt_atos:{ato_id}",))


def test_sem_protocolo_nem_pagamento_o_selo_a_mao_nao_entra():
    con = _casa()
    with pytest.raises(AS.SeloSemCobertura) as erro:
        _registrar(con)
    con.rollback()
    assert "não foi pedido" in str(erro.value) or "protocolo" in str(erro.value).lower()
    assert erro.value.quadro.get("itens"), "a recusa tem de trazer o quadro"
    assert _selos(con) == [], "nada pode ficar no razão sem cobertura"
    assert _cobertura(con) is None


def test_a_recusa_e_a_mesma_do_selo_automatico():
    """`SeloSemCobertura` é `AtoError`: as sete telas, que já apanham
    `AtoError`, mostram a recusa em vez de HTTP 500."""
    assert issubclass(AS.SeloSemCobertura, AS.AtoError)


def test_item_ligado_e_quitado_cobre_o_selo_a_mao_e_confirma_a_reserva():
    con = _casa()
    p = _protocolo(con)
    item = _item(con, p["protocolo_id"], quitado=1)
    _ligar(con, item, ato_id=1)
    _registrar(con)
    con.commit()
    assert [dict(s) for s in _selos(con)] == [
        {"numero": SELO_BOM, "tabela": "pt_atos", "ato_id": 1}]
    cob = _cobertura(con)
    assert cob is not None
    assert cob["situacao"] == AS.CONFIRMADA, "o selo já saiu: a reserva confirma"


def test_o_texto_com_selo_isento_passa_sem_protocolo():
    """A gratuidade NÃO trava (regra do oficial, 19/10/2026) — e aqui quem
    diz que é isento é o texto que o aparelho imprimiu."""
    con = _casa()
    _registrar(con, SELO_OUTRO, ato_id=2, texto=TEXTO_ISENTO)
    con.commit()
    assert [s["numero"] for s in _selos(con)] == [SELO_OUTRO]


def test_o_item_do_texto_escolhe_o_item_do_protocolo():
    lido = AS._dados_do_selo_a_mao(TEXTO_PAGO)
    assert lido == {"codigoAto": "16.1"}
    assert AS._dados_do_selo_a_mao(TEXTO_ISENTO) == {"isento": True,
                                                     "codigoAto": "16.1"}
    assert AS._dados_do_selo_a_mao(None) == {}


def test_a_liberacao_do_admin_cobre_o_selo_a_mao():
    con = _casa()
    AS.liberar_selo(con, tabela="pt_atos", ato_id=3, papel="ADMIN",
                    usuario="OFICIAL DE EXEMPLO", usuario_id=1,
                    justificativa="Cliente pagou no balcão e o caixa ainda não lançou.",
                    agora=AGORA)
    _registrar(con, SELO_OUTRO, ato_id=3)
    con.commit()
    cob = _cobertura(con, 3)
    assert cob["forma"] == AS.FORMA_LIBERADO
    assert cob["situacao"] == AS.CONFIRMADA
    usada = AS.banco(con).um(
        "SELECT usado_em FROM cx_selo_liberacoes WHERE tabela='pt_atos' AND ato_id=3")
    assert usada["usado_em"], "a liberação fica marcada como usada"


def test_com_a_trava_desligada_o_selo_a_mao_entra_como_antes():
    con = _casa()
    AS.ligar_trava(con, ligada=False, papel="ADMIN", usuario="OFICIAL DE EXEMPLO",
                   usuario_id=1,
                   justificativa="Selador fora do ar; a casa sela pelo portal hoje.",
                   agora=AGORA)
    _registrar(con)
    con.commit()
    assert _cobertura(con)["forma"] == AS.FORMA_TRAVA_DESLIGADA


def test_o_mesmo_selo_reenviado_nao_e_recusa_nem_cobre_duas_vezes():
    con = _casa()
    p = _protocolo(con)
    item = _item(con, p["protocolo_id"], quitado=1)
    _ligar(con, item, ato_id=1)
    _registrar(con)
    con.commit()
    _registrar(con)          # o formulário enviado duas vezes (LD14)
    con.commit()
    assert len(_selos(con)) == 1
    assert AS.banco(con).valor(
        "SELECT count(*) FROM cx_selo_coberturas WHERE referencia = 'pt_atos:1'") == 1
