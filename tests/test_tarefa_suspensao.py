"""Relato #132 — suspender a tarefa (e o processo) por prazo ou por condição.

    «criar opção de suspensão de tarefas e expedientes por prazo ou por
     condição — permitir suspender a exigência da tarefa ou expediente por
     tempo, ou condicionar ao retorno de algo, como no caso de emissao de nota
     devolutiva e espera do retorno do cliente» — o oficial, 14/10/2026

O que se prova aqui: a suspensa sai da COBRANÇA (painel, sino, escalonamento,
cobrança do gestor, carga, pauta) e continua na LISTA, com o selo; o prazo para
de correr; a volta por prazo é automática na leitura; e tudo fica no rastro.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import carga_da_equipe as CARGA
import gestor_rotina as GR
import oficial_pauta as PAUTA
import processos as PR
import tarefa_processo as TP
import tarefa_suspensao as TS

SENHA = "Senha#12345"
HOJE = date(2026, 10, 15)
AGORA = "2026-10-15T09:00:00"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa_logada):
    casa = cg_casa_logada
    casa["db"].create_user("beatriz", "BEATRIZ EXEMPLO DE SOUZA", SENHA, "USER")
    return casa


def _uid(db, login: str) -> int:
    with db.connect() as con:
        return int(con.execute("SELECT id FROM users WHERE username=?", (login,)).fetchone()[0])


def _tarefa(db, titulo="Nota devolutiva — matrícula 4020", **campos) -> int:
    mario = _uid(db, "mario")
    dados = {"title": titulo, "sector": "RI", "evidence_required": 0,
             "assigned_user_id": mario, "backup_user_id": _uid(db, "beatriz"),
             "due_date": "2026-10-01"}
    dados.update(campos)
    return db.create_task(dados, mario)


def _suspender(db, tid, **kw):
    kw.setdefault("modo", TS.MODO_CONDICAO)
    kw.setdefault("motivo", "Emitida nota devolutiva ao cliente")
    kw.setdefault("condicao", "Aguardando o retorno do cliente com o documento")
    with db.transaction() as con:
        return TS.suspender(con, tid, usuario_id=_uid(db, "mario"), agora=AGORA,
                            hoje=kw.pop("hoje", HOJE), **kw)


def _linha(db, tid):
    with db.connect() as con:
        return con.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()


def _historico(db, tid):
    with db.connect() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM task_history WHERE task_id=? ORDER BY id", (tid,))]


# ------------------------------------------------------------ o esquema
def test_as_colunas_entram_so_por_acrescimo_e_a_migracao_e_idempotente(casa):
    db = casa["db"]
    with db.connect() as con:
        assert TS.tem_as_colunas(con)
        TS.init_suspensao_schema(con)          # segunda vez: não estoura
    for _tabela, _coluna, tipo in TS.MIGRACOES:
        assert "NOT NULL" not in tipo.upper()


def test_a_regua_tolera_tabela_montada_a_mao():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, status TEXT, due_date TEXT)")
    assert TS.condicao_nao_suspensa(None, HOJE, con=con) == ("1=1", [])
    assert TS.condicao_suspensa(None, HOJE, con=con) == ("0=1", [])


def test_as_frases_da_linha_do_tempo_sao_as_mesmas_nos_dois_modulos():
    for acao, frase in TS.ACOES.items():
        assert TP.ACOES[acao] == frase
        assert TP.rotulo_da_acao(acao) == frase


# --------------------------------------------- suspender por condição
def test_por_condicao_sai_da_cobranca_e_fica_na_lista_com_o_selo(casa):
    db = casa["db"]
    tid = _tarefa(db)
    antes = db.dashboard_stats()
    _suspender(db, tid, hoje=date.today())
    depois = db.dashboard_stats()
    assert depois["overdue"] == antes["overdue"] - 1
    assert depois["open_tasks"] == antes["open_tasks"] - 1
    assert depois["tarefas_suspensas"] == antes.get("tarefas_suspensas", 0) + 1
    # o prazo não andou ainda (por condição, os dias só se sabem na volta)
    assert _linha(db, tid)["due_date"] == "2026-10-01"
    # a lista continua mostrando, com o selo
    assert tid in [r["id"] for r in db.list_tasks("ABERTAS")]
    assert tid not in [r["id"] for r in db.list_tasks("ABERTAS", filtros={"suspensas": "OCULTAR"})]
    assert [r["id"] for r in db.list_tasks("", filtros={"suspensas": "SO"})] == [tid]
    assert tid not in [r["id"] for r in db.list_tasks("", filtros={"prazo": "VENCIDO"})]
    sit = TS.situacao(_linha(db, tid))
    assert sit["modo"] == TS.MODO_CONDICAO and "retorno do cliente" in sit["rotulo"]


def test_a_suspensa_nao_escalona_nem_toca_o_sino(casa):
    db = casa["db"]
    mario = _uid(db, "mario")
    tid = _tarefa(db)
    with db.connect() as con:
        criticas_antes = TP.contagem_tier_critico_tarefas(con, mario)
    _suspender(db, tid, hoje=date.today())
    assert db.ensure_overdue_escalations() == 0
    assert not [h for h in _historico(db, tid) if h["action"] == "ESCALONAMENTO_AUTOMATICO"]
    with db.connect() as con:
        assert TP.contagem_tier_critico_tarefas(con, mario) == criticas_antes - 1
        assert TP.contagem_pendentes_notificacao(con, mario) == 0


def test_a_suspensa_sai_da_carga_da_pauta_e_da_cobranca_do_gestor(casa):
    db = casa["db"]
    mario = _uid(db, "mario")
    tid = _tarefa(db)
    with db.connect() as con:
        assert any(d["vencidas"] for d in CARGA.carga(con, date.today()))
        assert PAUTA.tarefas(con, date.today(), mario)["VENCIDAS"]
    # a cobrança diária do gestor não cobra o escrevente pela tarefa suspensa
    da_beatriz = _tarefa(db, "Exigência do RTD — aguardando o cliente",
                         assigned_user_id=_uid(db, "beatriz"), backup_user_id=mario)
    with db.transaction() as con:
        assert GR.cobrar_vencidas(con, date.today()) == 1
    _suspender(db, tid, hoje=date.today())
    _suspender(db, da_beatriz, hoje=date.today())
    with db.connect() as con:
        assert not any(d["vencidas"] for d in CARGA.carga(con, date.today()))
        assert not PAUTA.tarefas(con, date.today(), mario)["VENCIDAS"]
    with db.transaction() as con:
        assert GR.cobrar_vencidas(con, date.today()) == 0
    assert _linha(db, da_beatriz)["priority"] == "MEDIA"


def test_retomar_por_condicao_anda_o_vencimento_os_dias_suspensos(casa):
    db = casa["db"]
    tid = _tarefa(db)
    _suspender(db, tid)                                      # em 15/10
    with db.transaction() as con:
        feito = TS.retomar(con, tid, motivo="O cliente voltou com a certidão pedida",
                           usuario_id=_uid(db, "beatriz"), agora="2026-10-25T10:00:00",
                           hoje=date(2026, 10, 25))
    assert feito["dias"] == 10
    linha = _linha(db, tid)
    assert linha["due_date"] == "2026-10-11"                 # 01/10 + 10 dias
    assert all(linha[c] is None for c in TS.COLUNAS)
    acoes = [h["action"] for h in _historico(db, tid)]
    assert acoes[-2:] == ["SUSPENSA", "RETOMADA"]
    retomada = _historico(db, tid)[-1]
    assert retomada["old_value"] == "2026-10-01" and retomada["new_value"] == "2026-10-11"
    assert "voltou com a certidão" in retomada["note"]


# ------------------------------------------------- suspender por prazo
def test_por_prazo_anda_o_vencimento_na_hora_e_volta_sozinha_na_data(casa):
    db = casa["db"]
    tid = _tarefa(db)
    feito = _suspender(db, tid, modo=TS.MODO_PRAZO, ate="2026-10-25", condicao=None)
    assert feito["vencimento_depois"] == "2026-10-11"         # 01/10 + 10 dias
    linha = _linha(db, tid)
    assert TS.esta_suspensa(linha, date(2026, 10, 24))
    assert not TS.esta_suspensa(linha, date(2026, 10, 25))   # no dia, volta — sem rotina
    assert TS.situacao(linha, HOJE)["rotulo"] == "SUSPENSA até 25/10/2026"
    # a manutenção diária só deixa o rastro, e só uma vez
    with db.transaction() as con:
        assert TS.encerrar_as_vencidas(con, agora="2026-10-25T07:00:00", hoje=date(2026, 10, 24)) == 0
        assert TS.encerrar_as_vencidas(con, agora="2026-10-25T07:00:00", hoje=date(2026, 10, 25)) == 1
        assert TS.encerrar_as_vencidas(con, agora="2026-10-26T07:00:00", hoje=date(2026, 10, 26)) == 0
    linha = _linha(db, tid)
    assert linha["due_date"] == "2026-10-11" and linha["suspensa_desde"] is None
    ultima = _historico(db, tid)[-1]
    assert ultima["action"] == "RETOMADA" and ultima["user_id"] is None
    assert "automática" in ultima["note"]


def test_retomar_antes_da_data_devolve_os_dias_que_sobraram(casa):
    db = casa["db"]
    tid = _tarefa(db)
    _suspender(db, tid, modo=TS.MODO_PRAZO, ate="2026-10-25", condicao=None)
    with db.transaction() as con:
        feito = TS.retomar(con, tid, motivo="O cliente voltou antes do previsto",
                           usuario_id=_uid(db, "mario"), agora="2026-10-18T10:00:00",
                           hoje=date(2026, 10, 18))
    assert feito["dias"] == 3
    assert _linha(db, tid)["due_date"] == "2026-10-04"       # 01/10 + 3, e não + 10


def test_vencimento_editado_durante_a_suspensao_nao_se_perde_na_volta(casa):
    db = casa["db"]
    tid = _tarefa(db)
    _suspender(db, tid)
    db.update_task(tid, {"due_date": "2026-10-05"}, _uid(db, "mario"))
    with db.transaction() as con:
        TS.retomar(con, tid, motivo="Retorno do cliente registrado", usuario_id=None,
                   agora="2026-10-20T10:00:00", hoje=date(2026, 10, 20))
    assert _linha(db, tid)["due_date"] == "2026-10-10"       # 05/10 + 5 dias


# ------------------------------------------------------ as recusas
@pytest.mark.parametrize("kw, frase", [
    ({"motivo": "curto"}, "pelo menos"),
    ({"modo": "QUALQUER"}, "Escolha como suspender"),
    ({"modo": TS.MODO_PRAZO, "ate": "2026-10-15", "condicao": None}, "depois de hoje"),
    ({"modo": TS.MODO_PRAZO, "ate": None, "condicao": None}, "até que data"),
    ({"condicao": ""}, "Descreva a condição"),
])
def test_o_que_se_recusa_diz_o_que_fazer(casa, kw, frase):
    db = casa["db"]
    tid = _tarefa(db)
    with pytest.raises(TS.SuspensaoError, match=frase):
        _suspender(db, tid, **kw)
    assert _linha(db, tid)["suspensa_desde"] is None


def test_nao_se_suspende_duas_vezes_nem_o_que_terminou(casa):
    db = casa["db"]
    tid = _tarefa(db)
    _suspender(db, tid)
    with pytest.raises(TS.SuspensaoError, match="já está suspensa"):
        _suspender(db, tid)
    feita = _tarefa(db, "Tarefa concluída", status="CONCLUIDA")
    with pytest.raises(TS.SuspensaoError, match="só se suspende"):
        _suspender(db, feita)
    with pytest.raises(TS.SuspensaoError, match="não está suspensa"):
        with db.transaction() as con:
            TS.retomar(con, feita, motivo="Retomar o que não parou", usuario_id=None, agora=AGORA)


def test_concluir_a_suspensa_encerra_a_suspensao_junto(casa):
    db = casa["db"]
    tid = _tarefa(db)
    _suspender(db, tid)
    db.update_task(tid, {"status": "CONCLUIDA"}, _uid(db, "mario"))
    linha = _linha(db, tid)
    assert linha["suspensa_desde"] is None
    with db.transaction() as con:
        TP.reabrir(con, tid, "Reaberta para conferir o registro", _uid(db, "mario"), AGORA)
    assert not TS.esta_suspensa(_linha(db, tid))


# ------------------------------------------------------- Processos
def test_processos_mostra_o_selo_e_nao_conta_como_vencido(casa):
    db = casa["db"]
    tid = _tarefa(db)
    _suspender(db, tid, hoje=date.today())
    with db.connect() as con:
        linha = [p for p in PR.listar(con, vista="ABERTOS") if p["id"] == tid][0]
        assert linha["suspensao"] and not linha["vencido"]
        assert tid not in [p["id"] for p in PR.listar(con, vista="VENCIDOS")]
        assert PR.quadro_de_fiscalizacao(con)["suspensas"] == 1
        assert [p["id"] for p in PR.listar(con, vista="ABERTOS", suspensas="SO")] == [tid]
    html = casa["c"].get("/processos?vista=ABERTOS").get_data(as_text=True)
    assert "SUSPENSA até: Aguardando o retorno do cliente" in html


# ------------------------------------------------------- a tela
def test_a_ficha_suspende_e_retoma_com_rastro_e_auditoria(casa):
    db, c = casa["db"], casa["c"]
    tid = _tarefa(db)
    html = c.get(f"/tarefas/{tid}").get_data(as_text=True)
    assert "Suspender a cobrança" in html
    ate = (date.today() + timedelta(days=7)).isoformat()
    r = c.post(f"/tarefas/{tid}", data={
        "csrf_token": _token(html), "action": "suspender", "modo": "PRAZO", "ate": ate,
        "motivo": "Aguardando o cliente pagar a diferença"}, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Tarefa suspensa" in html
    assert f"SUSPENSA até {ate[8:10]}/{ate[5:7]}/{ate[:4]}" in html
    assert "Retomar agora" in html and "Suspensa — a cobrança parou" in html
    lista = c.get("/tarefas?status=ABERTAS").get_data(as_text=True)
    assert "SUSPENSA até" in lista
    r = c.post(f"/tarefas/{tid}", data={
        "csrf_token": _token(html), "action": "retomar",
        "motivo": "O cliente pagou a diferença hoje"}, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "Tarefa retomada" in html and not TS.esta_suspensa(_linha(db, tid))
    with db.connect() as con:
        acoes = [x[0] for x in con.execute(
            "SELECT action FROM audit_logs WHERE entity_type='TASK' AND entity_id=? "
            "ORDER BY id", (tid,))]
    assert "TASK_SUSPENSA" in acoes and "TASK_RETOMADA" in acoes


def test_a_tela_recusa_sem_derrubar(casa):
    db, c = casa["db"], casa["c"]
    tid = _tarefa(db)
    html = c.get(f"/tarefas/{tid}").get_data(as_text=True)
    r = c.post(f"/tarefas/{tid}", data={
        "csrf_token": _token(html), "action": "suspender", "modo": "CONDICAO",
        "condicao": "", "motivo": "Aguardando retorno do cliente"}, follow_redirects=True)
    assert r.status_code == 200 and "Descreva a condição" in r.get_data(as_text=True)
    assert _linha(db, tid)["suspensa_desde"] is None


def test_o_auditor_ve_mas_nao_suspende_nem_retoma(casa):
    """Decisão do oficial em 15/10/2026: «o AUDITOR não suspende nem retoma;
    só vê»."""
    from conftest import cg_login
    db = casa["db"]
    db.create_user("carla", "CARLA EXEMPLO LIMA", SENHA, "AUDITOR")
    auditor = casa["app"].test_client()
    cg_login(auditor, "carla", SENHA)
    tid = _tarefa(db)
    html = auditor.get(f"/tarefas/{tid}").get_data(as_text=True)
    assert "Nota devolutiva" in html and "Suspender a cobrança" not in html
    r = auditor.post(f"/tarefas/{tid}", data={
        "csrf_token": _token(html), "action": "suspender", "modo": "CONDICAO",
        "condicao": "Aguardando o retorno do cliente", "motivo": "Nota devolutiva emitida"},
        follow_redirects=True)
    assert "auditor só consulta" in r.get_data(as_text=True)
    assert _linha(db, tid)["suspensa_desde"] is None
    _suspender(db, tid, hoje=date.today())
    html = auditor.get(f"/tarefas/{tid}").get_data(as_text=True)
    assert "SUSPENSA até:" in html and "Retomar agora" not in html
    r = auditor.post(f"/tarefas/{tid}", data={
        "csrf_token": _token(html), "action": "retomar",
        "motivo": "Tentativa de retomar pelo auditor"}, follow_redirects=True)
    assert "auditor só consulta" in r.get_data(as_text=True)
    assert TS.esta_suspensa(_linha(db, tid))


def test_o_boletim_do_rcpn_nao_cobra_a_suspensa_como_vencida(casa):
    import gestor_rcpn as GRCPN
    db = casa["db"]
    tid = _tarefa(db, "Averbação do RCPN à espera do mandado", sector="RCPN")
    with db.connect() as con:
        linha = [x for x in GRCPN.boletim_texto(con, date.today()).splitlines()
                 if f"#{tid} " in x][0]
    assert "VENCIDA" in linha
    _suspender(db, tid, hoje=date.today())
    with db.connect() as con:
        linha = [x for x in GRCPN.boletim_texto(con, date.today()).splitlines()
                 if f"#{tid} " in x][0]
    assert "VENCIDA" not in linha and "SUSPENSA" in linha


def test_a_critica_da_produtividade_nao_conta_a_suspensa(casa):
    import produtividade_agente as PA
    db = casa["db"]
    _tarefa(db, "Exigência do RTD — retorno do cliente", assigned_user_id=_uid(db, "beatriz"))
    with db.connect() as con:
        antes = PA.medir(con, "2026-01-01")["por"]["beatriz"]["tarefas"]
    assert antes["abertas"] == 1 and antes["vencidas"] == 1
    with db.connect() as con:
        tid = con.execute("SELECT id FROM tasks WHERE title LIKE 'Exigência do RTD%'").fetchone()[0]
    _suspender(db, tid, hoje=date.today())
    with db.connect() as con:
        depois = PA.medir(con, "2026-01-01")["por"]["beatriz"]["tarefas"]
    assert depois["abertas"] == 0 and depois["vencidas"] == 0


def test_o_painel_conta_os_suspensos_a_parte(casa):
    db, c = casa["db"], casa["c"]
    tid = _tarefa(db)
    _suspender(db, tid, hoje=date.today())
    html = c.get("/").get_data(as_text=True)
    assert "Suspensos" in html
