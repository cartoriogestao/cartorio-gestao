# -*- coding: utf-8 -*-
"""Tipos de andamento na tarefa — código em task_history.new_value (NOTA)."""
from __future__ import annotations

import tarefa_processo as TP


def test_vocabulario_tipos_uteis():
    codigos = {c for c, _ in TP.TIPOS_ANDAMENTO}
    for esperado in (
        "OBSERVACAO",
        "EMITIDA_NOTA_EXIGENCIA",
        "AGUARDANDO_CLIENTE",
        "CUMPRIR_EXIGENCIAS",
        "CUMPRIDO",
        "EM_ANALISE",
        "DOCUMENTO_PENDENTE",
    ):
        assert esperado in codigos


def test_normalizar_desconhecido_vira_observacao():
    assert TP.normalizar_tipo_andamento(None) == "OBSERVACAO"
    assert TP.normalizar_tipo_andamento("") == "OBSERVACAO"
    assert TP.normalizar_tipo_andamento("xyz") == "OBSERVACAO"
    assert TP.normalizar_tipo_andamento("aguardando_cliente") == "AGUARDANDO_CLIENTE"


def test_rotulo_e_prefixo():
    assert TP.rotulo_do_tipo_andamento(None) == "Observação"
    assert "exigência" in TP.rotulo_do_tipo_andamento("EMITIDA_NOTA_EXIGENCIA").lower()
    plain = TP.texto_andamento_com_tipo("OBSERVACAO", "só texto")
    assert plain == "só texto"
    pref = TP.texto_andamento_com_tipo("AGUARDANDO_CLIENTE", "telefone sem resposta")
    assert pref.startswith("[Aguardando o cliente]")
    assert "telefone" in pref

def test_cumprido_rotulo_e_normaliza():
    assert TP.normalizar_tipo_andamento("cumprido") == "CUMPRIDO"
    assert TP.rotulo_do_tipo_andamento("CUMPRIDO") == "Cumprido"
    pref = TP.texto_andamento_com_tipo("CUMPRIDO", "protocolo anexado")
    assert pref.startswith("[Cumprido]")
    assert "protocolo" in pref
