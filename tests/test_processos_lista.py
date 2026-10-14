# -*- coding: utf-8 -*-
"""A lista única de Processos — fase 3 (12/10/2026).

    «precisamos unir o modulo de tarefas e de expedientes para ser um unico
     modulo de Processos»                            — o oficial, 12/10/2026
"""
from __future__ import annotations

import re

import processos as PR


def _um(db, sql, args=()):
    with db.connect() as con:
        return con.execute(sql, args).fetchone()


def _token(c, url):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', c.get(url).get_data(as_text=True)).group(1)


def _uid(db):
    return _um(db, "SELECT id FROM users WHERE username='jean'")[0]


def test_numero_do_processo():
    assert PR.numero("2026-10-12T10:00:00", 318) == "PROC-2026-000318"


def test_a_lista_mostra_processos_e_deixa_o_despacho_de_fora(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    uid = _uid(db)
    db.create_task({"source_type": "MANUAL", "title": "Plano de continuidade de exemplo",
                    "assigned_user_id": uid, "due_date": "2026-01-02"}, user_id=uid)
    db.create_task({"source_type": "DESPACHO", "title": "[Despacho] o dia de exemplo",
                    "assigned_user_id": uid}, user_id=uid)
    html = c.get("/processos").get_data(as_text=True)
    assert "Plano de continuidade de exemplo" in html and "[Despacho] o dia de exemplo" not in html
    assert re.search(r"PROC-\d{4}-\d{6}", html)
    vencidos = c.get("/processos?vista=VENCIDOS").get_data(as_text=True)
    assert "Plano de continuidade de exemplo" in vencidos and "vencido" in vencidos


def test_a_entrada_do_malote_vira_processo_com_o_tipo_escolhido(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    uid = _uid(db)
    exp = db.create_expediente({"source": "Malote Digital", "subject": "Mandado de averbação de divórcio",
                                "sender": "Vara de Exemplo", "category": "Para Cumprimento",
                                "received_at": "2026-08-19"}, uid)
    html = c.get("/processos").get_data(as_text=True)
    assert "espera decisão" in html and "Mandado de averbação de divórcio" in html
    r = c.post(f"/processos/entrada/{exp}/abrir",
               data={"csrf_token": _token(c, "/processos"), "especie": "ORDEM_JUDICIAL"})
    tid = int(re.search(r"/tarefas/(\d+)", r.headers["Location"]).group(1))
    assert _um(db, "SELECT linked_expediente_id FROM tasks WHERE id=?", (tid,))[0] == exp
    assert _um(db, "SELECT especie FROM pr_especie_do_processo WHERE task_id=?", (tid,))[0] \
        == "ORDEM_JUDICIAL"
    assert "espera decisão" not in c.get("/processos").get_data(as_text=True)
    ficha = c.get(f"/tarefas/{tid}").get_data(as_text=True)
    # 12/10/2026: o roteiro saiu («não precisa de roteiro»); a ficha mostra o tipo.
    assert "Processo PROC-" in ficha and "Tipo do processo" in ficha and "Ordem judicial" in ficha


def test_so_ciencia_arquiva_a_entrada_sem_abrir_processo(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    uid = _uid(db)
    exp = db.create_expediente({"source": "Malote Digital", "subject": "Circular para conhecimento de exemplo",
                                "category": "Circulares", "received_at": "2026-08-19"}, uid)
    c.post(f"/processos/entrada/{exp}/ciencia", data={"csrf_token": _token(c, "/processos"), "nota": "lida"})
    assert _um(db, "SELECT stage FROM expedientes WHERE id=?", (exp,))[0] == "ARQUIVADO"
    assert _um(db, "SELECT COUNT(*) FROM tasks WHERE linked_expediente_id=?", (exp,))[0] == 0
    assert "Circular para conhecimento de exemplo" not in c.get("/processos").get_data(as_text=True)


def test_ler_a_lista_nao_grava_nada(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    antes = _um(db, "SELECT COUNT(*) FROM tasks")[0]
    c.get("/processos")
    c.get("/processos?vista=COMIGO")
    assert _um(db, "SELECT COUNT(*) FROM tasks")[0] == antes


# ------------------------------- fase 4: balcão, atribuições e Centrais

import sqlite3  # noqa: E402

import processo_pasta as PASTA  # noqa: E402


def test_a_etapa_do_ri_vem_da_regua_do_agente_do_ri():
    con = sqlite3.connect(":memory:")
    con.executescript("""
        CREATE TABLE ri_protocolos (id INTEGER PRIMARY KEY, numero INTEGER, natureza_titulo TEXT, ato_id INTEGER,
            situacao TEXT, data_limite TEXT, prazo_suspenso_desde TEXT);
        CREATE TABLE ri_qualificacoes (id INTEGER PRIMARY KEY, protocolo_id INTEGER, ordem INTEGER, resultado TEXT);
    """)
    con.execute("INSERT INTO ri_protocolos VALUES (1, 11600, 'Escritura', NULL, 'ABERTO', '2099-01-01', NULL)")
    assert PASTA.etapa_do_ri(con, 1) == "A qualificar"
    con.execute("UPDATE ri_protocolos SET ato_id=5 WHERE id=1")
    assert PASTA.etapa_do_ri(con, 1).startswith("Registrado")


def test_rascunho_lavrado_conclui_o_processo(cg_casa_logada):
    import rascunho_de_tela as RASC
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    with db.transaction() as con:
        RASC.init_rascunho_schema(con)
        rid = RASC.salvar(con, tela="rascunhos", dados={"nome": "Beatriz Exemplo de Souza"},
                          titulo="Óbito — Beatriz Exemplo de Souza", agora="2026-10-12T10:00:00", por="jean")["id"]
    r = c.post(f"/rascunhos/{rid}/processo", data={"csrf_token": _token(c, "/rascunhos")})
    tid = int(re.search(r"/tarefas/(\d+)", r.headers["Location"]).group(1))
    vid = _um(db, "SELECT id FROM pr_vinculos WHERE task_id=?", (tid,))[0]
    html = c.get(f"/tarefas/{tid}").get_data(as_text=True)
    assert "O ato foi lavrado: concluir o processo" in html
    c.post(f"/tarefas/{tid}/pasta/{vid}/ato-lavrado",
           data={"csrf_token": _token(c, f"/tarefas/{tid}"), "apagar_rascunho": "1"})
    assert _um(db, "SELECT status FROM tasks WHERE id=?", (tid,))[0] == "CONCLUIDA"
    assert _um(db, "SELECT COUNT(*) FROM rascunhos_de_tela WHERE id=?", (rid,))[0] == 0


# --------------------------------- fase 5: Processos substitui as telas antigas

def test_o_menu_tem_processos_e_nao_tem_mais_tarefas_nem_expedientes(cg_casa_logada):
    html = cg_casa_logada["c"].get("/processos").get_data(as_text=True)
    assert "Tarefas e pendências" not in html and "Expedientes / Malote" not in html
    assert "Abrir processo interno" in html and "Registrar entrada do malote" in html
    assert "Passou por mim" in html
    antiga = cg_casa_logada["c"].get("/tarefas").get_data(as_text=True)
    assert "Esta lista agora faz parte de" in antiga


def test_abrir_processo_interno_com_tipo(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    uid = _uid(db)
    # o «Abrir processo interno» usa o mesmo cadastro da tela de tarefas (12/10/2026)
    r = c.post("/tarefas", data={"csrf_token": _token(c, "/processos"), "title": "Renovar alvará de exemplo",
                                 "especie": "TAREFA_ADMINISTRATIVA", "assigned_user_id": str(uid),
                                 "backup_user_id": str(uid), "priority": "ALTA", "evidence_required": "1"})
    tid = int(re.search(r"/tarefas/(\d+)", r.headers["Location"]).group(1))
    assert _um(db, "SELECT title, assigned_user_id FROM tasks WHERE id=?", (tid,))[:] == ("Renovar alvará de exemplo", uid)
    assert _um(db, "SELECT especie FROM pr_especie_do_processo WHERE task_id=?", (tid,))[0] == "TAREFA_ADMINISTRATIVA"
    ficha = c.get(f"/tarefas/{tid}").get_data(as_text=True)
    assert "Concluir processo" in ficha and "&larr; Processos" in ficha


def test_a_entrada_do_malote_registrada_em_processos_volta_para_la(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    uid = _uid(db)
    comum = {"csrf_token": _token(c, "/processos"), "voltar": "processos", "source": "Malote Digital",
             "received_at": "2026-10-12", "assigned_user_id": str(uid), "backup_user_id": str(uid)}
    r = c.post("/expedientes", data={**comum, "subject": "Mandado de exemplo para cumprir",
                                     "category": "Para Cumprimento"})
    assert "/tarefas/" in r.headers["Location"]                    # já nasceu processo
    r = c.post("/expedientes", data={**comum, "subject": "Circular de exemplo", "category": "Circulares"})
    assert r.headers["Location"].endswith("/processos")             # espera a decisão no alto da lista


# ------------------------------- controle e fiscalização do administrador

def test_os_filtros_de_fiscalizacao(cg_casa_logada):
    db = cg_casa_logada["db"]
    uid = _uid(db)
    ids = {}
    for titulo, dados in {
        "Vencido de exemplo": {"assigned_user_id": uid, "due_date": "2026-01-02", "sector": "Notas"},
        "Sem prazo de exemplo": {"assigned_user_id": uid, "sector": "RI"},
        "Sem responsável de exemplo": {"due_date": "2099-01-01", "priority": "CRITICA"},
    }.items():
        ids[titulo] = db.create_task({"source_type": "MANUAL", "title": titulo, **dados}, user_id=uid)
    with db.connect() as con:
        def titulos(**f):
            return {p["title"] for p in PR.listar(con, vista="ABERTOS", usuario_id=uid, **f)}
        assert titulos(prazo="VENCIDO") == {"Vencido de exemplo"}
        assert "Sem prazo de exemplo" in titulos(prazo="SEM_PRAZO")
        assert titulos(responsavel=PR.SEM_RESPONSAVEL) >= {"Sem responsável de exemplo"}
        assert "Sem responsável de exemplo" not in titulos(responsavel=str(uid))
        assert titulos(setor="Notas") == {"Vencido de exemplo"}
        assert titulos(prioridade="CRITICA") >= {"Sem responsável de exemplo"}
        assert titulos(prazo_de="2098-12-31", prazo_ate="2099-01-02") == {"Sem responsável de exemplo"}
        assert titulos(parado="7") == set()                       # tudo criado agora
        quadro = PR.quadro_de_fiscalizacao(con)
    assert quadro["sem_responsavel"] >= 1 and quadro["vencidos"] >= 1
    assert any(p["nome"] == "sem responsável" for p in quadro["por_pessoa"])


def test_o_administrador_ve_o_controle_e_baixa_a_planilha(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    uid = _uid(db)
    db.create_task({"source_type": "MANUAL", "title": "Processo de exemplo da planilha", "assigned_user_id": uid,
                    "due_date": "2026-01-02"}, user_id=uid)
    html = c.get("/processos").get_data(as_text=True)
    assert "Controle e fiscalização" in html and "Mais filtros" in html
    assert "Balcão, atribuições e Centrais" not in html               # o quadro saiu (12/10/2026)
    r = c.get(f"/processos.csv?vista=ABERTOS&responsavel={uid}&prazo=VENCIDO")
    texto = r.get_data(as_text=True)
    assert r.status_code == 200 and "processo;assunto" in texto and "Processo de exemplo da planilha" in texto
