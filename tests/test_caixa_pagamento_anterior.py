"""Quitar o item do protocolo com o pagamento feito em data anterior.

Pedido do oficial, 03/11/2026: o cliente pagou dias antes (o PIX de anteontem), e o item precisa estar
quitado para o selo sair. É recebimento de cliente, não despesa. As decisões: o lançamento continua com
a data de hoje (`cx_lancamentos.data`), e a do pagamento vai ao lado (`data_pagamento`), com o
comprovante e a justificativa; só PIX, TED, depósito e cartão; de ano anterior, com a aprovação de
outra pessoa; data futura, nunca. O carnê-leão e o caixa fechado não mudam.

Os nomes são fictícios, como em todo teste desta casa.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

import pytest

import carne_leao as CL
import caixa_protocolo as CXP
import test_fluxo_notas as F
from bd_nativo import banco
from test_fluxo_notas import balcao  # noqa: F401 — a bancada (fixture) das Notas

HOJE = date.today()


def _protocolo_com_item(b) -> dict:
    """Protocolo aberto pela tela, com um item da tabela e o caixa do escrevente aberto."""
    r = F._postar(b, "/caixa/protocolos", {"acao": "novo", "interessado": "MARIO EXEMPLO DOS SANTOS",
                                           "telefone": "(99) 90000-0000", "atribuicao": "NOTAS"},
                  seguir=False)
    pid = int(re.search(r"/caixa/protocolos/(\d+)", r.headers["Location"]).group(1))
    ficha = f"/caixa/protocolos/{pid}"
    F._postar(b, f"{ficha}/itens", {"acao": "acrescentar", "quantidade": "1",
                                    "servico": str(F._servico("13.12.1"))}, de=ficha)
    F._postar(b, "/caixa", {"acao": "abrir", "saldo_inicial": "0,00"})
    item = F._um(b, "SELECT id FROM cx_protocolo_atos WHERE protocolo_id=%s", (pid,))
    return {"id": pid, "ficha": ficha, "item_id": int(item["id"])}


def _quitar(b, p: dict, **campos) -> str:
    dados = {"acao": "quitar", "item_id": str(p["item_id"]), "forma_pagamento": "PIX", **campos}
    html = F._postar(b, f"{p['ficha']}/itens", dados, de=p["ficha"]).get_data(as_text=True)
    return " · ".join(F._flashes(html))


def _anterior(dias: int = 3, **mais) -> dict:
    return {"pago_antes": "1", "data_pagamento": (HOJE - timedelta(days=dias)).isoformat(),
            "comprovante": "E2E00000000000000000000000000000", "justificativa": "PIX feito antes da vinda ao balcão",
            **mais}


def _lancamento(b, p: dict) -> dict | None:
    return F._um(b, "SELECT l.* FROM cx_lancamentos l JOIN cx_protocolo_atos a ON a.lancamento_id = l.id "
                    "WHERE a.id=%s", (p["item_id"],))


def test_quitar_com_data_anterior_registra_hoje_e_libera_o_selo(balcao):  # noqa: F811
    p = _protocolo_com_item(balcao)
    recado = _quitar(balcao, p, **_anterior(3))
    assert "Item quitado" in recado and "Pago em" in recado, recado
    lan = _lancamento(balcao, p)
    assert str(lan["data"])[:10] == HOJE.isoformat()                       # o caixa de hoje o conta
    assert lan["data_pagamento"] == (HOJE - timedelta(days=3)).isoformat()  # a data do pagamento, ao lado
    assert lan["comprovante_pagamento"].startswith("E2E") and lan["justificativa_pagamento"]
    # A TRAVA DO SELO lê o item quitado: com o pagamento de antes, ele pode pagar o selo
    con = banco_pg_con(balcao)
    try:
        itens = CXP.itens_para_o_selo(con, p["id"], "13.12.1")
    finally:
        con.close()
    assert itens and CXP.item_pago(itens[0])
    # e a ficha do protocolo diz as duas datas
    ficha = F._tela(balcao, p["ficha"])
    assert "Pago em" in ficha and "registrado em" in ficha


def banco_pg_con(b):
    import banco_pg
    return banco_pg.conectar(b["banco"])


@pytest.mark.parametrize("forma", ["DINHEIRO", "BOLETO"])
def test_especie_e_boleto_sao_recusados(balcao, forma):  # noqa: F811
    p = _protocolo_com_item(balcao)
    recado = _quitar(balcao, p, forma_pagamento=forma, **_anterior(3))
    assert "só por PIX, TED, depósito ou cartão" in recado, recado
    assert _lancamento(balcao, p) is None


def test_data_futura_e_recusada(balcao):  # noqa: F811
    p = _protocolo_com_item(balcao)
    recado = _quitar(balcao, p, **_anterior(-1))
    assert "não pode ser futura" in recado, recado
    assert _lancamento(balcao, p) is None


def test_sem_comprovante_e_recusado(balcao):  # noqa: F811
    p = _protocolo_com_item(balcao)
    recado = _quitar(balcao, p, **_anterior(3, comprovante=""))
    assert "comprovante" in recado and _lancamento(balcao, p) is None


def test_ano_anterior_sem_aprovacao_e_recusado_e_com_aprovacao_passa(balcao):  # noqa: F811
    p = _protocolo_com_item(balcao)
    ano_passado = {"data_pagamento": date(HOJE.year - 1, 12, 30).isoformat()}
    recado = _quitar(balcao, p, **_anterior(**ano_passado))
    assert "aprovação de OUTRA pessoa" in recado, recado
    assert _lancamento(balcao, p) is None
    # quem quita não aprova a si mesmo
    recado = _quitar(balcao, p, **_anterior(**ano_passado, aprovador="escrevente", senha_aprovador=F.SENHA))
    assert _lancamento(balcao, p) is None, recado
    # outra pessoa, oficial, com a senha dela
    recado = _quitar(balcao, p, **_anterior(**ano_passado, aprovador="oficial", senha_aprovador=F.SENHA))
    lan = _lancamento(balcao, p)
    assert lan is not None, recado
    assert lan["pagamento_aprovado_por"] == F.OFICIAL and str(lan["data"])[:10] == HOJE.isoformat()


def test_o_carne_leao_e_o_caixa_fechado_nao_mudam(balcao):  # noqa: F811
    """O carnê-leão lê `cx_lancamentos.data` (decisão do oficial: a data do pagamento não entra no
    livro-caixa), e o caixa de outro dia — fechado — não ganha lançamento nenhum."""
    p = _protocolo_com_item(balcao)
    con = banco_pg_con(balcao)
    try:
        caixas_antes = banco(con).ler("SELECT * FROM cx_caixas WHERE id <> "
                                      "(SELECT max(id) FROM cx_caixas) ORDER BY id")
    finally:
        con.close()
    pago = HOJE.replace(day=1) - timedelta(days=1)          # o último dia do mês passado
    _quitar(balcao, p, **_anterior(**{"data_pagamento": pago.isoformat()}))
    lan = _lancamento(balcao, p)
    assert lan["data_pagamento"] == pago.isoformat()
    con = banco_pg_con(balcao)
    try:
        bd = banco(con)
        forma = next(iter(CL.FORMAS_DOS_FUNDOS))
        # O CRITÉRIO DE ANTES (pelo registro no caixa) e o do selo (#274/#278, 03/11/2026): pelos
        # dois, a data do pagamento não leva a receita para o mês passado. Sem selo, pelo critério
        # do selo o item fica nos «pagos sem selo» (31/12); pelo de antes, conta hoje.
        do_mes_passado = CL._recebido_no_caixa(bd, f"{pago:%Y-%m}", forma, 0, CL.PAGAMENTO)[0]
        do_mes_passado += CL._recebido_no_caixa(bd, f"{pago:%Y-%m}", forma, 0, CL.SELO)[0]
        deste_mes = CL._recebido_no_caixa(bd, f"{HOJE:%Y-%m}", forma, 0, CL.PAGAMENTO)[0]
        caixas_depois = bd.ler("SELECT * FROM cx_caixas WHERE id <> (SELECT max(id) FROM cx_caixas) "
                               "ORDER BY id")
    finally:
        con.close()
    # o recebimento conta no dia em que se registrou, e não no do pagamento
    assert not [r for r in do_mes_passado if r["dia"] == pago.isoformat()]
    assert [r for r in deste_mes if r["dia"] == HOJE.isoformat()]
    assert caixas_depois == caixas_antes


def test_o_recibo_e_a_conferencia_do_dia_mostram_as_duas_datas(balcao):  # noqa: F811
    p = _protocolo_com_item(balcao)
    _quitar(balcao, p, **_anterior(2))
    pago = (HOJE - timedelta(days=2)).strftime("%d/%m/%Y")
    caixa = F._tela(balcao, "/caixa")
    assert "Recebimentos de dias anteriores lançados hoje" in caixa and "E2E0000" in caixa
    F._postar(balcao, f"{p['ficha']}/recibo", {}, de=p["ficha"])
    recibo = F._um(balcao, "SELECT observacao FROM cx_recibos WHERE protocolo_id=%s", (p["id"],))
    assert recibo and f"Pago em {pago}, registrado em {HOJE:%d/%m/%Y}." in (recibo["observacao"] or ""), recibo
