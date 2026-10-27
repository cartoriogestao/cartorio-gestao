# -*- coding: utf-8 -*-
"""A tarefa a partir do protocolo, e o protocolo ligado a tarefa nova ou antiga.

    «precisamos poder criar uma tarefa a partir do protocolo e precisamos poder
     linkar um protocolo a uma tarefa nova ou preexistente» — o oficial, 26/10/2026

O vínculo é o da pasta do processo (`pr_vinculos`): uma ligação só, que a
tarefa mostra na pasta dela e o protocolo mostra na seção «Tarefas».
"""
from __future__ import annotations

import re

import processo_pasta as PASTA
from bd_nativo import banco

NUMERO = "2099.01.7"


def _protocolo(db) -> int:
    with db.transaction() as con:
        return int(banco(con).escrever(
            """INSERT INTO cx_protocolos (numero, data_abertura, hora, atribuicao, interessado,
                   assunto, situacao, tipo, criado_em)
               VALUES (%s,'2099-01-01','10:00','RI','MARIO EXEMPLO DOS SANTOS',
                       'BAIXA DE HIPOTECA','A_PAGAR','SERVICO','2099-01-01T10:00:00')
               RETURNING id""", (NUMERO,))[0]["id"])


def _token(c, url):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                     c.get(url).get_data(as_text=True)).group(1)


def _vinculos(db, pid):
    with db.connect() as con:
        return PASTA.processos_da_peca(con, "cx_protocolos", pid)


def test_cria_a_tarefa_a_partir_do_protocolo_e_volta_para_ele(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    pid = _protocolo(db)
    tela = f"/caixa/protocolos/{pid}"
    html = c.get(tela).get_data(as_text=True)
    assert "Tarefas deste protocolo" in html and "Criar tarefa ligada a este protocolo" in html
    r = c.post("/tarefas", data={
        "csrf_token": _token(c, tela), "title": f"Protocolo {NUMERO} — qualificar",
        "vincular_tabela": "cx_protocolos", "vincular_referencia": NUMERO,
        "voltar": f"{tela}#tarefas"})
    assert r.status_code == 302 and r.headers["Location"].endswith(f"{tela}#tarefas")
    ligadas = _vinculos(db, pid)
    assert len(ligadas) == 1 and ligadas[0]["title"] == f"Protocolo {NUMERO} — qualificar"
    # a tarefa mostra o protocolo na pasta dela, e o protocolo mostra a tarefa
    tid = ligadas[0]["id"]
    assert NUMERO in c.get(f"/tarefas/{tid}").get_data(as_text=True)
    assert f"#{tid}" in c.get(tela).get_data(as_text=True)


def test_a_recusa_da_criacao_volta_para_o_protocolo(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    pid = _protocolo(db)
    tela = f"/caixa/protocolos/{pid}"
    r = c.post("/tarefas", data={"csrf_token": _token(c, tela), "title": "  ",
                                 "vincular_tabela": "cx_protocolos",
                                 "vincular_referencia": NUMERO, "voltar": tela})
    assert r.status_code == 302 and r.headers["Location"].endswith(tela)
    assert _vinculos(db, pid) == []


def test_liga_o_protocolo_a_uma_tarefa_que_ja_existe_e_desliga(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    pid = _protocolo(db)
    with db.connect() as con:
        uid = banco(con).valor("SELECT id FROM users WHERE username='mario'")
    tid = db.create_task({"title": "Tarefa que já existia", "assigned_user_id": uid}, user_id=uid)
    tela = f"/caixa/protocolos/{pid}"
    assert f"#{tid} — Tarefa que já existia" in c.get(tela).get_data(as_text=True)  # na lista
    c.post(f"{tela}/tarefas/vincular", data={"csrf_token": _token(c, tela), "task_id": f"#{tid}"})
    ligadas = _vinculos(db, pid)
    assert [t["id"] for t in ligadas] == [tid]
    # ligar de novo recusa, e não duplica
    c.post(f"{tela}/tarefas/vincular", data={"csrf_token": _token(c, tela), "task_id": str(tid)})
    assert len(_vinculos(db, pid)) == 1
    # tarefa que não existe recusa
    c.post(f"{tela}/tarefas/vincular", data={"csrf_token": _token(c, tela), "task_id": "999999"})
    assert len(_vinculos(db, pid)) == 1
    # desligar pelo protocolo volta para o protocolo, e os dois continuam existindo
    r = c.post(f"/tarefas/{tid}/pasta/{ligadas[0]['vinculo_id']}/tirar",
               data={"csrf_token": _token(c, tela), "voltar": f"{tela}#tarefas"})
    assert r.headers["Location"].endswith(f"{tela}#tarefas")
    assert _vinculos(db, pid) == []
    with db.connect() as con:
        assert banco(con).valor("SELECT COUNT(*) FROM tasks WHERE id=%s", (tid,)) == 1


def test_a_tarefa_nova_da_tela_de_tarefas_nasce_ligada_ao_protocolo(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    pid = _protocolo(db)
    assert "Protocolo geral (opcional)" in c.get("/tarefas").get_data(as_text=True)
    r = c.post("/tarefas", data={"csrf_token": _token(c, "/tarefas"), "title": "Nova com protocolo",
                                 "vincular_tabela": "cx_protocolos",
                                 "vincular_referencia": NUMERO})
    assert "/tarefas/" in r.headers["Location"]
    assert [t["title"] for t in _vinculos(db, pid)] == ["Nova com protocolo"]
    # protocolo que não existe: a tarefa nasce, e o aviso diz que a ligação não pegou
    c.post("/tarefas", data={"csrf_token": _token(c, "/tarefas"), "title": "Com protocolo errado",
                             "vincular_tabela": "cx_protocolos", "vincular_referencia": "1900.01.1"})
    with db.connect() as con:
        assert banco(con).valor("SELECT COUNT(*) FROM tasks WHERE title='Com protocolo errado'") == 1


def test_o_voltar_so_aceita_caminho_desta_casa(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    r = c.post("/tarefas", data={"csrf_token": _token(c, "/tarefas"), "title": "Fora",
                                 "voltar": "//fora.exemplo/x"})
    assert "fora.exemplo" not in r.headers["Location"]
