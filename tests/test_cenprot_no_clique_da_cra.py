# -*- coding: utf-8 -*-
"""O clique da remessa baixa a CENPROT e não responde."""
from __future__ import annotations

import cn_schema as CN
import cenprot_pendencias as PEND


def _vazia(especie):
    return {"especie": especie, "ambiente": "PRODUCAO", "vieram": 0,
            "entraram": 0, "repetidas": 0, "sem_codigo": 0, "sem_titulo": 0}


def test_o_periodo_cobre_sete_dias_com_o_dia_do_clique():
    assert PEND.periodo_do_clique("2026-11-04T23:00:00") == (
        "2026-10-29", "2026-11-04")


def test_baixa_cada_especie_e_nao_responde(monkeypatch):
    chamadas = []

    def falso(db, especie, **kw):
        chamadas.append((especie, kw))
        return _vazia(especie)

    def responder(*_a, **_k):
        raise AssertionError("o clique respondeu à CENPROT")

    monkeypatch.setattr(PEND, "baixar", falso)
    monkeypatch.setattr(PEND, "enviar", responder)
    linhas = PEND.trazer_com_a_cra(object(), dia="2026-11-04",
                                   quem="Escrevente Exemplo")
    assert [linha["especie"] for linha in linhas] == list(
        PEND.ESPECIES_DO_CLIQUE_DA_CRA)
    assert all(linha["ok"] for linha in linhas)
    anuencia = dict(chamadas)[CN.ANUENCIA]
    assert anuencia["inicio"] == "2026-10-29"
    assert anuencia["fim"] == "2026-11-04"
    ordem = dict(chamadas)[CN.DECISAO_JUDICIAL]
    assert ordem == {"de": "2026-10-29", "ate": "2026-11-04",
                     "quem": "Escrevente Exemplo", "pasta": None}
    datas = [kw["data"] for especie, kw in chamadas
             if especie == CN.PEDIDO_PROTESTO]
    assert datas == ["2026-10-29", "2026-10-30", "2026-10-31", "2026-11-01",
                     "2026-11-02", "2026-11-03", "2026-11-04"]


def test_a_falha_de_uma_especie_nao_derruba_as_outras(monkeypatch):
    def falso(db, especie, **kw):
        if especie == CN.CANCELAMENTO:
            raise PEND.PendenciaError("a Central não respondeu o cancelamento")
        return _vazia(especie)

    monkeypatch.setattr(PEND, "baixar", falso)
    linhas = {linha["especie"]: linha for linha in PEND.trazer_com_a_cra(
        object(), dia="2026-11-04")}
    assert linhas[CN.CANCELAMENTO]["ok"] is False
    assert "cancelamento" in linhas[CN.CANCELAMENTO]["frase"]
    assert linhas[CN.CANCELAMENTO]["cor"] == "danger"
    assert linhas[CN.ANUENCIA]["ok"] is True
    assert linhas[CN.DECISAO_JUDICIAL]["ok"] is True
