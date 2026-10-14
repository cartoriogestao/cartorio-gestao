# -*- coding: utf-8 -*-
"""A pasta do processo e o rascunho que vira processo — fase 1 do módulo único.

    «ainda que bem explicada a tarefa eh insuficiente. nao tem os docs
     necessarios e nao tem onde procurar»            — o oficial, 12/10/2026
    «salvar um rascunho pra continuar depois em um ato de rcpn, acho que vale
     ter a opcao de virar processo se nao for pra terminar no mesmo dia»
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date

import pytest

import processo_pasta as PASTA
from processo_pasta_web import proximo_dia_util

MATRICULA = "99999901552022200003154000092990"


def _con():
    con = sqlite3.connect(":memory:")
    con.executescript("""
        CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT, linked_expediente_id INTEGER);
        CREATE TABLE task_history (id INTEGER PRIMARY KEY, task_id INTEGER, ts TEXT, user_id INTEGER,
            action TEXT, old_value TEXT, new_value TEXT, note TEXT);
        CREATE TABLE expedientes (id INTEGER PRIMARY KEY, internal_protocol TEXT, subject TEXT);
        CREATE TABLE rc_assentos (id INTEGER PRIMARY KEY, especie TEXT, numero INTEGER, matricula TEXT,
            livro_volume TEXT, nome TEXT);
        CREATE TABLE attachments (id INTEGER PRIMARY KEY, entity_type TEXT, entity_id INTEGER,
            original_name TEXT, size_bytes INTEGER, uploaded_at TEXT);
    """)
    con.execute("INSERT INTO expedientes VALUES (12, 'EXP-2026-000012', 'Mandado de averbação')")
    con.execute("INSERT INTO tasks VALUES (318, 'Cumprir o mandado', 12)")
    con.execute("INSERT INTO rc_assentos VALUES (1689, 'CASAMENTO', 929, ?, 'B-3', "
                "'Mario Exemplo dos Santos e Beatriz Exemplo de Souza')", (MATRICULA,))
    con.executemany("INSERT INTO attachments(entity_type, entity_id, original_name) VALUES (?,?,?)",
                    [("EXPEDIENTE", 12, "mandado.pdf"), ("rc_assento", 1689, "termo.pdf"),
                     ("TASK", 318, "rascunho do oficio.pdf"), ("EXPEDIENTE", 99, "de outro.pdf")])
    return con


def test_a_origem_ja_esta_na_pasta_e_os_documentos_se_juntam():
    con = _con()
    assert [(v["tabela"], v["origem"]) for v in PASTA.vinculos(con, 318)] == [("expedientes", True)]
    PASTA.vincular(con, 318, "rc_assentos", "999999 01 55 2022 2 00003 154 0000929 90", agora="t", por=1)
    nomes = [d["nome"] for d in PASTA.documentos(con, 318)]
    assert nomes == ["rascunho do oficio.pdf", "mandado.pdf", "termo.pdf"]     # e não «de outro.pdf»
    assert "casamento nº 929, livro B-3" in PASTA.vinculos(con, 318)[1]["rotulo"]
    assert "Na pasta do processo" in con.execute("SELECT note FROM task_history").fetchone()[0]


def test_recusa_o_que_nao_acha_o_repetido_e_a_origem_de_novo():
    con = _con()
    with pytest.raises(PASTA.PastaError, match="Não achei"):
        PASTA.vincular(con, 318, "rc_assentos", "9999990155", agora="t", por=1)   # a matrícula cortada
    PASTA.vincular(con, 318, "rc_assentos", MATRICULA, agora="t", por=1)
    with pytest.raises(PASTA.PastaError, match="já está na pasta"):
        PASTA.vincular(con, 318, "rc_assentos", "1689", agora="t", por=1)
    with pytest.raises(PASTA.PastaError, match="já é a origem"):
        PASTA.vincular(con, 318, "expedientes", "EXP-2026-000012", agora="t", por=1)
    with pytest.raises(PASTA.PastaError, match="não pode entrar"):
        PASTA.vincular(con, 318, "users", "1", agora="t", por=1)


def test_tirar_da_pasta_nao_mexe_na_peca():
    con = _con()
    PASTA.vincular(con, 318, "rc_assentos", MATRICULA, agora="t", por=1)
    vid = PASTA.vinculos(con, 318)[1]["id"]
    PASTA.desvincular(con, 318, vid, agora="t", por=1)
    assert len(PASTA.vinculos(con, 318)) == 1
    assert con.execute("SELECT COUNT(*) FROM rc_assentos").fetchone()[0] == 1


def test_o_prazo_padrao_do_rascunho_pula_o_fim_de_semana():
    assert proximo_dia_util(date(2026, 10, 9)) == date(2026, 10, 12)    # sexta → segunda
    assert proximo_dia_util(date(2026, 10, 12)) == date(2026, 10, 13)


def _um(db, sql, args=()):
    with db.connect() as con:
        return con.execute(sql, args).fetchone()


def _token(c, url):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', c.get(url).get_data(as_text=True)).group(1)


def test_a_tela_mostra_a_pasta_e_poe_peca_nela(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    uid = _um(db, "SELECT id FROM users WHERE username='jean'")[0]
    exp = db.create_expediente({"source": "Malote Digital", "subject": "Mandado de exemplo",
                                "category": "Para Cumprimento", "received_at": "2026-08-19"}, uid)
    db.add_attachment("EXPEDIENTE", exp, {"original_name": "Mandado de Exemplo.pdf", "stored_name": "m.pdf",
                                          "stored_path": "m.pdf", "sha256": "0" * 64, "size_bytes": 10}, uid)
    outro = db.create_expediente({"source": "Malote Digital", "subject": "Ofício complementar",
                                  "category": "Para Cumprimento", "received_at": "2026-08-20"}, uid)
    tid = db.create_task({"source_type": "EXPEDIENTE", "title": "Cumprir o mandado de exemplo",
                          "assigned_user_id": uid, "linked_expediente_id": exp}, user_id=uid)
    html = c.get(f"/tarefas/{tid}").get_data(as_text=True)
    assert "Pasta do processo" in html and "Mandado de Exemplo.pdf" in html
    protocolo = _um(db, "SELECT internal_protocol FROM expedientes WHERE id=?", (outro,))[0]
    c.post(f"/tarefas/{tid}/pasta/vincular",
           data={"csrf_token": _token(c, f"/tarefas/{tid}"), "tabela": "expedientes", "referencia": protocolo})
    assert "Ofício complementar" in c.get(f"/tarefas/{tid}").get_data(as_text=True)


def test_o_rascunho_vira_processo_com_responsavel_e_prazo(cg_casa_logada):
    import rascunho_de_tela as RASC
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    with db.transaction() as con:
        RASC.init_rascunho_schema(con)
        rid = RASC.salvar(con, tela="rascunhos", dados={"nome": "Mario Exemplo dos Santos"},
                          titulo="Nascimento — Mario Exemplo dos Santos", agora="2026-10-12T10:00:00",
                          por="jean")["id"]
    r = c.post(f"/rascunhos/{rid}/processo", data={"csrf_token": _token(c, "/rascunhos")})
    tid = int(re.search(r"/tarefas/(\d+)", r.headers["Location"]).group(1))
    t = _um(db, "SELECT title, due_date, assigned_user_id, source_ref FROM tasks WHERE id=?", (tid,))
    assert t[0] == "Continuar o ato: Nascimento — Mario Exemplo dos Santos" and t[1] and t[2]
    assert t[3] == f"RASCUNHO:{rid}"
    assert _um(db, "SELECT COUNT(*) FROM pr_vinculos WHERE task_id=? AND tabela='rascunhos_de_tela'",
               (tid,))[0] == 1
    # pedir de novo não abre outro processo (a guarda contra tarefa repetida)
    c.post(f"/rascunhos/{rid}/processo", data={"csrf_token": _token(c, "/rascunhos")})
    assert _um(db, "SELECT COUNT(*) FROM tasks WHERE source_ref=?", (f"RASCUNHO:{rid}",))[0] == 1


# ------------------------------------------------ o tipo do processo
# 12/10/2026: o roteiro (documentos, passos, marcação, aprovação) saiu por ordem
# do oficial — «não precisa de roteiro». Ficaram quatro tipos, para filtrar.

import processo_especies as ESP  # noqa: E402


def test_sao_so_os_quatro_tipos_que_o_oficial_pediu():
    assert {k: e["nome"] for k, e in ESP.CATALOGO.items()} == {
        "TAREFA_ADMINISTRATIVA": "Tarefa administrativa",
        "ORDEM_JUDICIAL": "Ordem judicial",
        "CORREGEDORIA": "Processo da Corregedoria",
        "ATO_PENDENTE": "Ato do cartório pendente",
    }
    proibidos = ("bloque", "impedir", "recusar", "travar", "exigir", "marcar", "aprovar", "roteiro")
    assert not [n for n in dir(ESP) if not n.startswith("_") and any(p in n.lower() for p in proibidos)]


def test_sugere_o_tipo_pela_origem_e_pelo_texto():
    assert ESP.sugerir({"source_type": "EXPEDIENTE", "title": "Mandado",
                        "description": "averbar a sentença de divórcio no assento de casamento"}) == "ORDEM_JUDICIAL"
    assert ESP.sugerir({"source_type": "EXPEDIENTE", "title": "penhora na matrícula 1234"}) == "ORDEM_JUDICIAL"
    assert ESP.sugerir({"source_type": "EXPEDIENTE", "title": "Ofício circular da COGEX"}) == "CORREGEDORIA"
    assert ESP.sugerir({"source_type": "INSPECAO", "title": "item 12"}) == "CORREGEDORIA"
    assert ESP.sugerir({"source_type": "RASCUNHO"}) == "ATO_PENDENTE"
    assert ESP.sugerir({"source_type": "MANUAL", "title": "qualquer"}) == "TAREFA_ADMINISTRATIVA"
    assert ESP.sugerir({"source_type": "EXPEDIENTE", "title": "pedido de informação"}) is None


def test_definir_e_trocar_o_tipo():
    con = _con()
    assert ESP.tipo_do_processo(con, {"id": 318, "source_type": "RASCUNHO"})["sugerida"] == "ATO_PENDENTE"
    ESP.definir(con, 318, "ORDEM_JUDICIAL", agora="t", por=1)
    ESP.definir(con, 318, "CORREGEDORIA", agora="t", por=1)
    t = ESP.tipo_do_processo(con, {"id": 318})
    assert (t["especie"], t["nome"], t["sugerida"]) == ("CORREGEDORIA", "Processo da Corregedoria", None)
    try:
        ESP.definir(con, 318, "RCPN_AVERBACAO_JUDICIAL", agora="t", por=1)
    except ESP.EspecieError:
        pass
    else:
        raise AssertionError("tipo fora dos quatro foi aceito")


def test_tipo_antigo_gravado_aparece_como_sem_tipo():
    con = _con()
    ESP.init_schema(con)
    con.execute("INSERT INTO pr_especie_do_processo VALUES (319, 'RCPN_AVERBACAO_JUDICIAL', 't', 1)")
    t = ESP.tipo_do_processo(con, {"id": 319, "source_type": "MANUAL"})
    assert t["especie"] is None and t["sugerida"] == "TAREFA_ADMINISTRATIVA"


def test_a_tela_mostra_o_tipo_sugerido_e_depois_o_gravado(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    uid = _um(db, "SELECT id FROM users WHERE username='jean'")[0]
    tid = db.create_task({"source_type": "EXPEDIENTE", "title": "Mandado de averbação",
                          "description": "averbar o divórcio no assento de casamento", "assigned_user_id": uid},
                         user_id=uid)
    html = c.get(f"/tarefas/{tid}").get_data(as_text=True)
    assert "Tipo do processo" in html and "Ainda sem tipo" in html and "Roteiro" not in html
    c.post(f"/tarefas/{tid}/especie", data={"csrf_token": _token(c, f"/tarefas/{tid}"),
                                            "especie": "ORDEM_JUDICIAL"})
    html = c.get(f"/tarefas/{tid}").get_data(as_text=True)
    assert "Ainda sem tipo" not in html and "Trocar" in html and "mandado de averbação ou de registro" in html
