"""Só o essencial nos atos já lavrados (06/10/2026).

Ordem do oficial: «reduza a quantidade de erros para corrigir. deixe apenas os
fundamentais e atos efetivamente lavrados e selados. o que não for essencial e
muito importante, tire e segue a vida» — e «isso para os atos já lavrados, os que
estão para revisão, segue normal». O que se guarda aqui: as quatro regras que
saem, o GRAVE em ato SELADO que fica, e a minuta que passa inteira.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import gestor_conferencia as GC                                  # noqa: E402
import gestor_erros as GER                                       # noqa: E402
import revisao_previa                                            # noqa: E402

AGORA = "2026-10-06T08:00:00"
_ABERTAS: list = []


def _con(cg_casa):
    c = sqlite3.connect(cg_casa["banco"])
    c.row_factory = sqlite3.Row
    revisao_previa.init_schema(c)
    _ABERTAS.append(c)
    return c


@pytest.fixture(autouse=True)
def _fecha_as_conexoes():
    yield
    while _ABERTAS:
        c = _ABERTAS.pop()
        c.commit()
        c.close()


def _a(chave, regra, grav="ATENCAO"):
    return {"chave": chave, "regra": regra, "gravidade": grav, "setor": "RI_QUALIFICACAO",
            "titulo": "t", "detalhe": "", "prazo": None, "fundamento": ""}


def _ato_do_ri(con, numero, selo=None):
    mid = con.execute("INSERT INTO ri_matriculas (numero, teor, criado_em) VALUES (?, 'F', ?)",
                      (numero, AGORA)).lastrowid
    aid = con.execute("""INSERT INTO ri_atos (matricula_id, tipo, numero, teor, lavrado_em,
                             hash_ato, selo_texto) VALUES (?, 'AV', 6, 'AV-6', ?, 'h', ?)""",
                      (mid, AGORA, selo)).lastrowid
    return mid, aid


def _revisao(con, mid, graves):
    return con.execute(
        """INSERT INTO rv_revisoes (atribuicao, alvo_id, hash_texto, rotulo, dossie, situacao,
               pedido_em, resultado_json, graves, origem)
           VALUES ('RI', ?, 'h', 'AV-6 da matrícula 9', 'd', 'PRONTA', ?, ?, ?, 'AGENTE')""",
        (mid, AGORA, json.dumps({"achados": [{"o_que": "x"}]}), graves)).lastrowid


def test_as_quatro_regras_nao_essenciais_saem(cg_casa):
    con = _con(cg_casa)
    entra = [_a("POR_FORA:ri_atos:1", "ATO_POR_FORA"), _a("SEM_PRENOT:1", "REGISTRO_SEM_PRENOTACAO"),
             _a("ORFAO:1", "SELO_ORFAO"), _a("SELO_LOCAL:X", "SELO_CANCELADO_LOCAL"),
             _a("SEM_SELO:ri_atos:1", "ATO_SEM_SELO"), _a("SIRC:1", "SIRC", "VENCIDO")]
    sai = {a["regra"] for a in GC.so_o_essencial(con, entra)}
    # ATO_SEM_SELO saiu também, na mesma noite: «não existe ato lavrado sem selo».
    assert sai == {"SIRC"}


def test_da_revisao_em_lote_fica_so_o_grave_em_ato_selado(cg_casa):
    con = _con(cg_casa)
    m_sel, _ = _ato_do_ri(con, "9001", selo="MATRIC000000XXXXXXXXXXXXXXXX")
    m_sem, _ = _ato_do_ri(con, "9002", selo=None)
    grave_selado = _revisao(con, m_sel, 1)
    leve_selado = _revisao(con, m_sel, 0)
    grave_sem_selo = _revisao(con, m_sem, 1)
    entra = [_a(f"REV_AGENTE:{grave_selado}", "REVISAO_DO_AGENTE", "CRITICO"),
             _a(f"REV_AGENTE:{leve_selado}", "REVISAO_DO_AGENTE", "ATENCAO"),
             _a(f"REV_AGENTE:{grave_sem_selo}", "REVISAO_DO_AGENTE", "CRITICO")]
    fica = [a["chave"] for a in GC.so_o_essencial(con, entra)]
    assert fica == [f"REV_AGENTE:{grave_selado}"]


def test_o_que_esta_em_revisao_passa_inteiro(cg_casa):
    """Minuta não é ato lavrado: o marcador esquecido nela continua apontado."""
    con = _con(cg_casa)
    entra = [_a("MARCADOR:ri_minutas:20", "MODELO_NAO_PREENCHIDO", "CRITICO"),
             _a("TEXTO:ri_minutas:14", "TEXTO_CONTRA_CADASTRO")]
    assert len(GC.so_o_essencial(con, entra)) == 2


def test_o_cnib_fica_so_no_registro_selado(cg_casa):
    con = _con(cg_casa)
    _, selado = _ato_do_ri(con, "9003", selo="MATRIC000000YYYYYYYYYYYYYYYY")
    _, sem = _ato_do_ri(con, "9004")
    entra = [_a(f"CNIB_ATO:{selado}", "REGISTRO_SEM_CNIB"), _a(f"CNIB_ATO:{sem}", "REGISTRO_SEM_CNIB")]
    assert [a["chave"] for a in GC.so_o_essencial(con, entra)] == [f"CNIB_ATO:{selado}"]


def test_o_relatorio_de_erros_nao_mostra_as_regras_retiradas():
    for regra in GC.RETIRADAS_DO_ATO_LAVRADO:
        assert regra not in GER.CATEGORIAS


# ---- 06/10/2026, noite: «mantenha apenas tarefas para os problemas que possa gerar
# problemas que culminem em responsabilidade civil»

import gestor_rotina as GR                                       # noqa: E402
from datetime import date as _date                               # noqa: E402


def test_so_vira_tarefa_o_que_pode_gerar_responsabilidade_civil(cg_casa):
    con = _con(cg_casa)
    from gestor_schema import init_gestor_schema
    init_gestor_schema(con)
    # 13/10/2026: o SIRC deixou de ser o exemplo do que vira tarefa — as Centrais e
    # as cargas saíram das tarefas por ordem do oficial (ver o teste seguinte). O
    # exemplo do que fica é o CPF errado no assento, que vai errado às Centrais.
    achados = [dict(_a("SIRC:1", "SIRC", "VENCIDO"), setor="RCPN"),
               dict(_a("DOC:1", "DOCUMENTO_INVALIDO", "CRITICO"), setor="RCPN"),
               dict(_a("FUNAI:1", "FUNAI", "VENCIDO"), setor="RCPN"),
               dict(_a("CAIXA_HOJE:1", "CAIXA_DO_DIA_ABERTO", "CRITICO"), setor="PESSOA:1")]
    GR.sincronizar_tarefas(con, achados, {}, _date(2026, 10, 6))
    refs = {r[0] for r in con.execute("SELECT source_ref FROM tasks WHERE source_type='GESTOR'")}
    assert refs == {"GESTOR:DOCUMENTO_INVALIDO:RCPN"}


def test_as_centrais_e_as_cargas_nao_viram_tarefa_e_a_aberta_fecha(cg_casa):
    """13/10/2026, o oficial: «as centrais e cargas automático, não crie mais
    tarefas para os escreventes (...) retire essas tarefas automáticas» e «quero
    aviso pra mim apenas, consolidado, não um por tarefa»."""
    con = _con(cg_casa)
    from gestor_schema import init_gestor_schema
    init_gestor_schema(con)
    for regra in ("SIRC", "SIRC_CANCELAMENTO", "CENSEC", "CENSEC_AUTOMATICO",
                  "ONR_INDICADOR_INCOMPLETO", "CARGAS_RCPN_PRONTA"):
        assert regra in GR.REGRAS_DAS_CENTRAIS and regra in GR.REGRAS_SEM_TAREFA, regra
    tid = con.execute("""INSERT INTO tasks (source_type, source_ref, title, status, created_at,
                             updated_at) VALUES ('GESTOR', 'GESTOR:SIRC:RCPN', 'SIRC', 'ABERTA', ?, ?)""",
                      (AGORA, AGORA)).lastrowid
    GR.sincronizar_tarefas(con, [dict(_a("SIRC:1", "SIRC", "VENCIDO"), setor="RCPN")], {},
                           _date(2026, 10, 13))
    assert con.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()[0] == "CONCLUIDA"
    nota = con.execute("SELECT note FROM task_history WHERE task_id=? ORDER BY id DESC",
                       (tid,)).fetchone()[0]
    assert "envio automático pelos agentes" in nota and "aviso" in nota
    # o aviso consolidado é a seção das Centrais do despacho do oficial
    assert set(GR._REGRAS_DE_CENTRAL) == set(GR.REGRAS_DAS_CENTRAIS)


def test_a_tarefa_que_ja_existia_fecha_dizendo_o_motivo_verdadeiro(cg_casa):
    con = _con(cg_casa)
    from gestor_schema import init_gestor_schema
    init_gestor_schema(con)
    tid = con.execute("""INSERT INTO tasks (source_type, source_ref, title, status, created_at,
                             updated_at) VALUES ('GESTOR', 'GESTOR:DIGITALIZACAO_DA_FICHA:RI', 'Digitalizacao', 'ABERTA', ?, ?)""",
                      (AGORA, AGORA)).lastrowid
    # 13/10/2026: era o IBGE, que passou a ser Central (nota própria, no teste acima).
    GR.sincronizar_tarefas(con, [dict(_a("DIGI:1", "DIGITALIZACAO_DA_FICHA", "PRAZO"), setor="RI")], {},
                           _date(2026, 10, 6))
    assert con.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()[0] == "CONCLUIDA"
    nota = con.execute("SELECT note FROM task_history WHERE task_id=? ORDER BY id DESC",
                       (tid,)).fetchone()[0]
    assert "responsabilidade civil" in nota and "não há mais pendência" not in nota


# ---- 06/10/2026: «coisa da cnib já temos a base atualizada, só verificar se tem ordem»

def _ordem(con, nome, documento, ativa=1):
    oid = con.execute("""INSERT INTO ri_cnib_ordens (protocolo_cnib, data_pedido, processo,
                             instituicao, ativa) VALUES (?, '2026-09-01', 'P-1', 'TRT', ?)""",
                      (f"PROT-{nome}-{documento}", ativa)).lastrowid
    import ri_schema
    con.execute("""INSERT INTO ri_cnib_pessoas (ordem_id, nome, documento, nome_norm)
                   VALUES (?, ?, ?, ?)""", (oid, nome, documento, ri_schema.normalizar_busca(nome)))


def _registro_com_parte(con, numero, nome, doc):
    mid, aid = _ato_do_ri(con, numero, selo="MATRIC000000ZZZZZZZZZZZZZZZZ")
    con.execute("UPDATE ri_atos SET tipo='R', numero=1 WHERE id=?", (aid,))
    con.execute("""INSERT INTO ri_partes (matricula_id, ato_id, nome, documento_numero)
                   VALUES (?, ?, ?, ?)""", (mid, aid, nome, doc))
    return aid


def test_o_cnib_so_aponta_registro_com_ordem_contra_a_parte(cg_casa):
    con = _con(cg_casa)
    _registro_com_parte(con, "9101", "FULANO SEM ORDEM NENHUMA", "11122233344")
    com = _registro_com_parte(con, "9102", "BELTRANO COM ORDEM ATIVA", "55566677788")
    _ordem(con, "BELTRANO COM ORDEM ATIVA", "55566677788")
    achados = GC.regra_registro_sem_cnib(con, _date(2026, 10, 6))
    assert [a["chave"] for a in achados] == [f"CNIB_ATO:{com}"]
    assert achados[0]["gravidade"] == "CRITICO"


def test_ordem_cancelada_nao_aponta(cg_casa):
    con = _con(cg_casa)
    _registro_com_parte(con, "9103", "CICRANO DE ORDEM CANCELADA", "99988877766")
    _ordem(con, "CICRANO DE ORDEM CANCELADA", "99988877766", ativa=0)
    assert GC.regra_registro_sem_cnib(con, _date(2026, 10, 6)) == []


def test_a_base_parada_e_medida_pela_ultima_leitura_e_nao_pelo_pedido(cg_casa):
    con = _con(cg_casa)
    con.execute("""INSERT INTO ri_cnib_leituras (de, ate, pedida_em, terminada_em, situacao)
                   VALUES ('2026-09-28', '2026-10-06', '2026-10-06T07:46', '2026-10-06T07:46', 'VAZIA')""")
    assert GC.regra_cnib_parado(con, _date(2026, 10, 6)) == []
    assert GC.regra_cnib_parado(con, _date(2026, 10, 20))[0]["regra"] == "CNIB_PARADO"
