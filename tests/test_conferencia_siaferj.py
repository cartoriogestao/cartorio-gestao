"""A conferência «Sistema × SIAFERJ» quebra a diferença entre a receita do selo e a do caixa.

Pedido do oficial (03/11/2026): outubro de 2026 dava cerca de R$ 51 mil no sistema e cerca de R$ 49
mil no SIAFERJ, «já abatido o FERJ». Os dados reais estão no servidor; aqui o mês é FICTÍCIO, montado
para ter uma parcela de cada espécie, e a conta tem de fechar com resíduo zero.

Pessoas, protocolos e selos fictícios.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import conferencia_siaferj as CS  # noqa: E402
from bd_nativo import banco  # noqa: E402

AGORA = "2026-11-03T10:00:00"


@pytest.fixture
def casa(cg_casa_logada):
    return cg_casa_logada


def _selo(db, n: int, usado_em: str, emol: str, *, ato_id: int, marca: str = "") -> None:
    total = emol
    texto = (f"Selo: TESTE{n:024d} {usado_em[8:10]}/{usado_em[5:7]}/{usado_em[:4]} 10:00:00, Ato: 14.5.1, "
             f"Parte(s): FULANA DE TESTE,{marca} Total R$ {total} Emol R$ {emol} "
             "Consulte em https://selo.exemplo.invalid")
    with db.transaction() as con:
        banco(con).escrever(
            """INSERT INTO sd_selos (numero, texto, atribuicao, referencia, tabela, ato_id, ambiente,
                   obtido_em, usado_em) VALUES (%s, %s, 'NOTAS', %s, 'nt_atos', %s, 'PRODUCAO', %s, %s)""",
            (f"TESTE{n:024d}", texto, f"ato {ato_id}", ato_id, f"{usado_em}T10:00:00", f"{usado_em}T10:00:00"))


def _pago(db, dia: str, emol: str | None, valor: str, *, ato_id: int | None) -> int:
    """Um item de protocolo pago no caixa em `dia`, usado pelo ato `ato_id` (None: por ato nenhum)."""
    with db.transaction() as con:
        bd = banco(con)
        lan = bd.escrever(
            """INSERT INTO cx_lancamentos (data, natureza, sentido, forma_pagamento, descricao, valor,
                   emolumentos, criado_em) VALUES (%s, 'RECEBIMENTO', 'ENTRADA', 'PIX', 'Certidão', %s, %s, %s)
               RETURNING id""", (dia, valor, emol, AGORA))[0]["id"]
        pid = bd.escrever(
            """INSERT INTO cx_protocolos (numero, interessado, data_abertura, situacao, criado_em)
               VALUES (%s, 'FULANA DE TESTE', %s, 'PAGO', %s) RETURNING id""",
            (f"2026.10.{lan}", dia, AGORA))[0]["id"]
        bd.escrever(
            """INSERT INTO cx_protocolo_atos (protocolo_id, descricao, codigo_ato, quantidade, valor_total,
                   emolumentos, quitado, lancamento_id, usado_por_tabela, usado_por_ato_id)
               VALUES (%s, 'Certidão', '14.5.1', 1, %s, %s, 1, %s, %s, %s)""",
            (pid, valor, emol, lan, "nt_atos" if ato_id else None, ato_id))
        return int(lan)


def _outubro(db) -> dict:
    # A: selado e pago em outubro — está nas duas receitas
    _selo(db, 1, "2026-10-05", "100,00", ato_id=1)
    _pago(db, "2026-10-05", "100,00", "100,00", ato_id=1)
    # B: selado em outubro, pago em setembro
    _selo(db, 2, "2026-10-10", "50,00", ato_id=2)
    _pago(db, "2026-09-28", "50,00", "50,00", ato_id=2)
    # C: pago em outubro, selado em novembro
    _pago(db, "2026-10-20", "30,00", "30,00", ato_id=3)
    _selo(db, 3, "2026-11-02", "30,00", ato_id=3)
    # D: selado em outubro, sem pagamento no caixa (o depósito, o acervo, a gratuidade marcada…)
    _selo(db, 4, "2026-10-12", "20,00", ato_id=4)
    # E: entrou em outubro sem discriminar os fundos, e sem ato
    _pago(db, "2026-10-15", None, "25,00", ato_id=None)
    with db.connect() as con:
        return CS.conferir(con, "2026-10")


def _parcela(c: dict, comeco: str) -> int:
    return next(p["valor"] for p in c["parcelas"] if p["o_que"].startswith(comeco))


def test_as_tres_receitas_do_mes(casa):
    c = _outubro(casa["db"])
    assert c["selo"]["bruto"] == 17000                       # A + B + D
    assert c["selo"]["ferj"] == 2040                         # 12% do emolumento (o padrão da casa)
    assert c["selo"]["liquido"] == 14960                     # o comparável do SIAFERJ


def test_a_ponte_do_selo_ao_caixa_fecha_sem_residuo(casa):
    c = _outubro(casa["db"])
    assert _parcela(c, "Selado no mês e pago no caixa noutro mês") == -5000      # B
    assert _parcela(c, "Selado no mês sem pagamento no caixa") == -2000           # D
    assert _parcela(c, "Pago no mês e selado noutro mês") == 3000                 # C
    assert _parcela(c, "Pago no mês e ainda sem selo") > 0                        # E, sem os fundos estimados
    assert _parcela(c, "Diferença de valor nos atos pagos e selados no mês") == 0  # A bate
    assert c["residuo"] == 0, c
    assert c["caixa"]["fundos_estimados"] > 0                                     # os de E


def test_o_texto_para_o_servidor_diz_cada_parcela(casa):
    texto = CS.em_texto(_outubro(casa["db"]))
    assert "o comparável do SIAFERJ" in texto and "Pago no mês e selado noutro mês" in texto
    assert "resíduo não explicado: R$ 0,00" in texto
