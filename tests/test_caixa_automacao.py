"""Fechamento por data dos caixas compartilhados, sem contar gavetas humanas."""
import json
from datetime import datetime
from types import SimpleNamespace

import pytest

import automacao as AU
import caixa_automacao as M
import cobranca as CB
from bd_nativo import banco

AGORA = datetime(2026, 11, 16, 0, 5)


def _abrir(db, nome=CB.OPERADOR_DO_CAIXA_BANCARIO, dia="2026-11-15", inicial="0", situacao="ABERTO"):
    with db.transaction() as con:
        return banco(con).escrever("""INSERT INTO cx_caixas
            (data,operador_nome,saldo_inicial,aberto_em,situacao)
            VALUES (%s,%s,%s,%s,%s) RETURNING id""",
            (dia, nome, inicial, dia + "T09:00:00", situacao))[0]["id"]


def _lancar(db, cid, forma="BOLETO", sentido="ENTRADA", **campos):
    with db.transaction() as con:
        bd = banco(con)
        lid = bd.escrever("""INSERT INTO cx_lancamentos
            (caixa_id,data,natureza,sentido,forma_pagamento,valor,criado_em)
            VALUES (%s,'2026-11-15','RECEBIMENTO',%s,%s,'10,00','2026-11-15T10:00:00') RETURNING id""",
            (cid, sentido, forma))[0]["id"]
        if campos:
            assert set(campos) <= {"excluido", "estornado"}
            for campo, valor in campos.items():
                bd.escrever(f"UPDATE cx_lancamentos SET {campo}=%s WHERE id=%s", (valor, lid))


def _rodar(db, agir=True, agora=AGORA):
    return M.fechar_compartilhados(SimpleNamespace(db=db, agora=agora,
        processo={"pode_agir": agir, "alterado_por": "mario"}))


def _um(db, cid):
    with db.connect() as con:
        return banco(con).um("SELECT * FROM cx_caixas WHERE id=%s", (cid,))


def test_encerra_geral_e_bancario_sem_inventar_contagem_e_audita_uma_vez(cg_casa):
    db = cg_casa["db"]
    ids = [_abrir(db, nome) for nome in (CB.OPERADOR_DO_CAIXA_GERAL, CB.OPERADOR_DO_CAIXA_BANCARIO)]
    _lancar(db, ids[1])
    r = _rodar(db)
    assert r["situacao"] == "OK" and len(r["acoes"]) == 2
    for cid in ids:
        c = _um(db, cid)
        assert c["situacao"] == "FECHADO" and c["valor_esperado"] == "0,00"
        assert c["valor_contado"] is None and c["diferenca"] is None
        assert c["conferido_em"] is None and c["conferido_por"] is None
        assert c["fechado_por"] is None and "mario" in c["justificativa"]
    assert _rodar(db)["acoes"] == []
    with db.connect() as con:
        logs = banco(con).ler("SELECT * FROM audit_logs WHERE action='CAIXA_FECHADO_AUTOMATICAMENTE'")
    assert {l["entity_id"] for l in logs} == set(ids) and len(logs) == 2
    assert all(l["agente"] and l["a_mando_de"] == "mario" for l in logs)
    assert any(json.loads(l["details"])["entradas"] == "10,00" for l in logs)


def test_preserva_hoje_futuro_gaveta_humana_acervo_e_caixa_ja_fechado(cg_casa):
    db = cg_casa["db"]
    ids = [_abrir(db, dia="2026-11-16"), _abrir(db, dia="2026-11-17"),
           _abrir(db, nome="Carla Exemplo"), _abrir(db, dia="2022-01-01"),
           _abrir(db, nome=CB.OPERADOR_DO_CAIXA_GERAL, situacao="FECHADO")]
    antes = [_um(db, cid) for cid in ids]
    assert _rodar(db)["acoes"] == []
    assert [_um(db, cid) for cid in ids] == antes


@pytest.mark.parametrize("forma,sentido,inicial", [
    ("DINHEIRO", "ENTRADA", "0"), ("PIX", "SAIDA", "0"),
    ("OUTROS", "ENTRADA", "0"), ("PIX", "ENTRADA", "1,00"),
])
def test_contagem_fica_para_o_humano(cg_casa, forma, sentido, inicial):
    db = cg_casa["db"]
    cid = _abrir(db, inicial=inicial)
    _lancar(db, cid, forma, sentido)
    r = _rodar(db)
    assert r["situacao"] == "AVISO" and r["achados"][0]["tipo"] == "CONTAGEM_NECESSARIA"
    assert _um(db, cid)["situacao"] == "ABERTO"


def test_modo_leitura_nao_fecha_e_movimento_desfeito_nao_entra_na_contagem(cg_casa):
    db = cg_casa["db"]
    cid = _abrir(db)
    _lancar(db, cid, "DINHEIRO", excluido=1)
    _lancar(db, cid, "DINHEIRO", estornado=1)
    assert _rodar(db, agir=False)["achados"][0]["tipo"] == "FECHAMENTO_PENDENTE"
    assert _um(db, cid)["situacao"] == "ABERTO"
    assert len(_rodar(db)["acoes"]) == 1


def test_pagamento_tardio_usa_novo_dia_sem_reabrir_o_anterior(cg_casa):
    db = cg_casa["db"]
    cid = _abrir(db)
    _rodar(db)
    with db.transaction() as con:
        novo = CB.caixa_bancario(con, agora=AGORA)
    assert novo["id"] != cid and novo["data"] == "2026-11-16" and novo["situacao"] == "ABERTO"
    assert _um(db, cid)["situacao"] == "FECHADO"


def test_catalogo_semeia_desligado_e_mantem_a_configuracao_do_oficial(cg_casa):
    db = cg_casa["db"]
    with db.transaction() as con:
        AU.semear(con, AGORA)
        p = AU.por_codigo(con, M.CODIGO)
    assert not p["ativo"] and not p["pode_agir"]
    assert p["robo_oficial"] == "FINANCEIRO" and p["alvo"] == "caixa_automacao:fechar_compartilhados"
    assert p["agenda"]["dias"] == list(range(7))
    with db.transaction() as con:
        AU.definir_pode_agir(con, p["id"], True, papel="ADMIN", usuario="mario")
        AU.semear(con, AGORA)
        assert AU.por_codigo(con, M.CODIGO)["pode_agir"]
