"""O carnê-leão reconhece a receita do item de protocolo na emissão do selo do ato.

Decisão do oficial, 03/11/2026 («Sim, no selo»), como o depósito prévio já era (`NO_USO`, 26/10/2026).
O dia do selo é o que já mora no item: `cx_protocolo_atos.usado_em`. A receita conta no mais tarde
entre o pagamento e o selo. Os meses já apurados mudam de valor, e a tela avisa quanto.

Pessoas, protocolos e valores fictícios.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import carne_leao as CL  # noqa: E402
from bd_nativo import banco  # noqa: E402

AGORA = "2026-11-03T10:00:00"


@pytest.fixture
def casa(cg_casa_logada):
    return cg_casa_logada


def _item_pago(db, pago_em: str, emol: str, *, selado_em: str | None, estornado: int = 0) -> int:
    """Um item do protocolo pago no caixa em `pago_em`, consumido pelo selo em `selado_em` (ou não)."""
    with db.transaction() as con:
        bd = banco(con)
        lan = bd.escrever(
            """INSERT INTO cx_lancamentos (data, natureza, sentido, forma_pagamento, descricao, valor,
                   emolumentos, estornado, criado_em)
               VALUES (%s, 'RECEBIMENTO', 'ENTRADA', 'PIX', 'Certidão', %s, %s, %s, %s) RETURNING id""",
            (pago_em, emol, emol, estornado, AGORA))[0]["id"]
        pid = bd.escrever(
            """INSERT INTO cx_protocolos (numero, interessado, data_abertura, situacao, criado_em)
               VALUES (%s, 'FULANA DE TESTE', %s, 'PAGO', %s) RETURNING id""",
            (f"2026.10.{lan}", pago_em, AGORA))[0]["id"]
        bd.escrever(
            """INSERT INTO cx_protocolo_atos (protocolo_id, descricao, codigo_ato, quantidade, valor_total,
                   emolumentos, quitado, lancamento_id, quantidade_usada, usado_em,
                   usado_por_tabela, usado_por_ato_id)
               VALUES (%s, 'Certidão', '14.5.1', 1, %s, %s, 1, %s, %s, %s, %s, %s)""",
            (pid, emol, emol, lan, 1 if selado_em else 0,
             f"{selado_em}T10:00:00" if selado_em else None,
             "nt_atos" if selado_em else None, lan if selado_em else None))
        return int(lan)


def _apurar(db, comp):
    with db.connect() as con:
        return CL.apurar(con, comp)


def test_pago_em_outubro_e_selado_em_novembro_conta_em_novembro(casa):
    db = casa["db"]
    _item_pago(db, "2026-10-28", "100,00", selado_em="2026-11-02")
    outubro, novembro = _apurar(db, "2026-10"), _apurar(db, "2026-11")
    assert outubro["caixa"] == 0 and novembro["caixa"] == 10000
    # e o aviso da diferença em relação ao critério de antes, nos dois meses
    assert outubro["mudanca_do_criterio"] == {"antes": 10000, "agora": 0, "diferenca": -10000}
    assert novembro["mudanca_do_criterio"]["diferenca"] == 10000
    assert any("critério de 03/11/2026" in x for x in outubro["avisos"])


def test_pago_e_selado_no_mesmo_dia_nada_muda(casa):
    db = casa["db"]
    _item_pago(db, "2026-10-10", "80,00", selado_em="2026-10-10")
    outubro = _apurar(db, "2026-10")
    assert outubro["caixa"] == 8000 and outubro["mudanca_do_criterio"]["diferenca"] == 0
    assert not any("critério de 03/11/2026" in x for x in outubro["avisos"])


def test_o_selado_antes_e_pago_depois_conta_no_pagamento(casa):
    """O diferido: não há receita antes do dinheiro (caso A, a confirmar com o oficial)."""
    db = casa["db"]
    _item_pago(db, "2026-11-05", "60,00", selado_em="2026-10-20")
    assert _apurar(db, "2026-10")["caixa"] == 0 and _apurar(db, "2026-11")["caixa"] == 6000


def test_o_estornado_antes_do_selo_nao_conta(casa):
    db = casa["db"]
    _item_pago(db, "2026-10-15", "70,00", selado_em=None, estornado=1)
    assert _apurar(db, "2026-10")["caixa"] == 0 and _apurar(db, "2026-11")["caixa"] == 0


def test_o_pago_ainda_sem_selo_conta_no_pagamento_e_e_avisado(casa):
    """Caso B, com o oficial: por ora no pagamento, e na lista dos pagos sem selo."""
    db = casa["db"]
    _item_pago(db, "2026-10-15", "40,00", selado_em=None)
    outubro = _apurar(db, "2026-10")
    assert outubro["caixa"] == 4000 and outubro["pagos_sem_selo"] == {"n": 1, "valor": 4000}
    assert any("ainda sem selo" in x for x in outubro["avisos"])


def test_o_deposito_previo_continua_como_esta(casa):
    """O uso do depósito não é receita do caixa (o livro do depósito conta, no ato): não muda."""
    db = casa["db"]
    with db.transaction() as con:
        banco(con).escrever(
            """INSERT INTO cx_lancamentos (data, natureza, sentido, forma_pagamento, descricao, valor,
                   emolumentos, criado_em)
               VALUES ('2026-10-12', 'RECEBIMENTO', 'ENTRADA', 'DEPOSITO_PREVIO',
                       'Uso do depósito prévio nº 1', '50,00', '50,00', %s)""", (AGORA,))
    outubro = _apurar(db, "2026-10")
    assert outubro["caixa"] == 0 and outubro["mudanca_do_criterio"]["diferenca"] == 0


def test_o_livro_caixa_exportado_diz_o_criterio(casa):
    linhas = CL.livro_caixa_linhas(_apurar(casa["db"], "2026-10"))
    assert any("receita reconhecida na emissão do selo" in c for linha in linhas[:4] for c in linha)


def test_o_resumo_do_ano_mostra_a_mudanca_de_cada_mes(casa):
    db = casa["db"]
    _item_pago(db, "2026-10-28", "100,00", selado_em="2026-11-02")
    with db.connect() as con:
        ano = CL.apurar_com_o_ano(con, "2026-11", ate="2026-11")[1]
    por_mes = {m["competencia"]: m["mudanca_do_criterio"] for m in ano}
    assert por_mes["2026-10"] == -10000 and por_mes["2026-11"] == 10000
