"""As ferramentas do malote e das tarefas (`tools/`) no PostgreSQL — LH03.

Vieram do sandbox (20/10/2026), escritas para o SQLite: `mode=ro`, `VACUUM
INTO`, `BEGIN IMMEDIATE` e `lastrowid`. Aqui se prova, para cada uma:

  * sem `--confirmar` ela SÓ MEDE: o banco abre só para ler (o servidor recusa
    a escrita), nada muda e nenhuma cópia é tirada;
  * com `--confirmar` tira a cópia da casa (`banco_pg.copiar_para_arquivo`)
    antes de gravar, e grava com histórico e auditoria;
  * a conferência se refaz DENTRO da transação que grava: entre a medição e a
    escrita há a cópia, e o que outra mesa fez nesse meio não é atropelado.

Rodam como a linha de comando roda: ninguém montou `Database()`, e o
`sqlite3.connect` é o de fábrica. A cópia é de mentira (não há pg_dump aqui; o
teste é da ferramenta, e não da cópia). Os nomes são fictícios.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import banco_pg  # noqa: E402
from bd_nativo import banco  # noqa: E402
from tools import malote_ciencia as CIENCIA  # noqa: E402
from tools import malote_tarefas as TAREFAS  # noqa: E402
from tools import tarefa_trocar_responsavel as TROCAR  # noqa: E402

pytestmark = pytest.mark.skipif(
    not banco_pg.ativo(),
    reason="ferramenta nativa: só roda com o PostgreSQL ligado (CG_PG_DSN)")

SENHA = "Senha#12345"


@pytest.fixture()
def casa(cg_casa_logada, monkeypatch, tmp_path):
    casa = cg_casa_logada
    db = casa["db"]
    db.create_user("beatriz", "BEATRIZ EXEMPLO DE SOUZA", SENHA, "USER")
    db.create_user("carla", "CARLA TESTE RIBEIRO", SENHA, "USER")
    db.set_settings({"malote_cadastra_em_nome_de": "mario",
                     "archive_root": str(tmp_path / "arquivos")})
    # a linha de comando: ninguém instalou o desvio do `sqlite3.connect`
    monkeypatch.setattr(sqlite3, "connect", banco_pg._CONNECT_ORIGINAL)
    monkeypatch.setenv("CARTORIO_GESTAO_COPIAS", str(tmp_path / "copias"))
    casa["copias"] = []

    def copia_de_mentira(db_path, destino):
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(b"copia de teste")
        casa["copias"].append(destino)
        if casa.get("durante_a_copia"):
            casa["durante_a_copia"]()
        return destino

    monkeypatch.setattr(banco_pg, "copiar_para_arquivo", copia_de_mentira)
    casa["arquivos"] = tmp_path / "arquivos"
    return casa


def _uid(db, login: str) -> int:
    with db.connect() as con:
        return int(banco(con).valor("SELECT id FROM users WHERE username=%s", (login,)))


def _um(db, sql: str, params=()):
    with db.connect() as con:
        return banco(con).um(sql, params)


def _contar(db, sql: str, params=()) -> int:
    with db.connect() as con:
        return int(banco(con).valor(sql, params))


def _expediente(db, assunto="Ofício circular de exemplo") -> int:
    return db.create_expediente({"source": "Malote Digital", "subject": assunto,
                                 "category": "Ofício", "sector": "RCPN",
                                 "notes": "Recebido pelo malote."}, _uid(db, "mario"))


def _tarefa(db, titulo="Conferir o ofício de exemplo", **campos) -> int:
    dados = {"title": titulo, "sector": "RCPN", "evidence_required": 0,
             "assigned_user_id": _uid(db, "beatriz")}
    dados.update(campos)
    return db.create_task(dados, _uid(db, "mario"))


@pytest.fixture()
def conexoes(monkeypatch):
    """Espia a porta do banco: guarda cada conexão aberta, e com que caminho.
    O teste limpa a lista logo antes de chamar a ferramenta (as do próprio
    teste, pelo `db`, também passam pela porta)."""
    abertas = []
    original = banco_pg.conectar

    def espiao(caminho, *a, **kw):
        con = original(caminho, *a, **kw)
        abertas.append((str(caminho), con))
        return con

    monkeypatch.setattr(banco_pg, "conectar", espiao)
    return abertas


def _so_para_ler(abertas, db_path) -> None:
    """Toda conexão que a medição abriu é `mode=ro`, e o servidor recusa escrever
    por ela (reaberta pelo mesmo caminho, pela porta)."""
    assert abertas, "a ferramenta não abriu o banco"
    for caminho, _con in abertas:
        assert caminho.startswith("file:") and caminho.endswith("?mode=ro"), caminho
    ro = banco_pg.conectar(abertas[0][0], uri=True)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            banco(ro).escrever("INSERT INTO settings (key, value) VALUES (%s, %s)",
                               ("chave_de_teste_lh03", "x"))
    finally:
        ro.close()


# ------------------------------------------------------ malote_ciencia

def test_a_ciencia_sem_confirmar_so_mede_com_o_banco_aberto_so_para_ler(
        casa, conexoes, capsys):
    db = casa["db"]
    eid = _expediente(db)
    conexoes.clear()
    assert CIENCIA.main(["--banco", str(casa["banco"]), "--arquivar", str(eid)]) == 0
    saida = capsys.readouterr().out
    assert "arquivar (ciência):" in saida and "Só medi. Nada foi gravado." in saida
    _so_para_ler(conexoes, casa["banco"])
    assert _um(db, "SELECT stage FROM expedientes WHERE id=%s", (eid,))["stage"] == "RECEBIDO"
    assert _contar(db, "SELECT count(*) AS n FROM audit_logs WHERE action='EXPEDIENTE_STAGE'") == 0
    assert casa["copias"] == []


def test_a_ciencia_confirmada_arquiva_com_a_nota_liga_a_tarefa_e_audita(casa, capsys):
    db = casa["db"]
    arquivar, outro = _expediente(db), _expediente(db, "Ofício que pediu tarefa")
    tid = _tarefa(db)
    assert CIENCIA.main(["--banco", str(casa["banco"]), "--arquivar", str(arquivar),
                         "--ligar", f"{outro}:{tid}", "--confirmar"]) == 0
    assert "feito." in capsys.readouterr().out
    assert len(casa["copias"]) == 1 and casa["copias"][0].name.startswith("antes_malote_ciencia_")
    e = _um(db, "SELECT stage, completed_at, completed_by, notes FROM expedientes WHERE id=%s",
            (arquivar,))
    assert e["stage"] == "ARQUIVADO" and e["completed_at"]
    assert e["completed_by"] == _uid(db, "mario")
    assert e["notes"].startswith("Recebido pelo malote. Ciência do oficial em ")
    trilha = _um(db, "SELECT user_id, username_snapshot, entity_type, entity_id, details "
                     "FROM audit_logs WHERE action='EXPEDIENTE_STAGE' ORDER BY id")
    assert (trilha["username_snapshot"], trilha["entity_type"], str(trilha["entity_id"])) \
        == ("mario", "EXPEDIENTE", str(arquivar))
    assert json.loads(trilha["details"])["origem"] == "AGENTE MALOTE"
    assert _um(db, "SELECT stage FROM expedientes WHERE id=%s", (outro,))["stage"] == "RECEBIDO"
    assert _um(db, "SELECT linked_expediente_id FROM tasks WHERE id=%s", (tid,))[
        "linked_expediente_id"] == outro
    nota = _um(db, "SELECT action, note FROM task_history WHERE task_id=%s AND action='NOTA' "
                   "ORDER BY id DESC", (tid,))
    assert nota["note"] == f"Ligada ao expediente {outro} (malote)."


def test_a_ciencia_recusa_o_expediente_fora_de_recebido_sem_copia_nem_escrita(casa):
    db = casa["db"]
    eid = _expediente(db)
    db.update_expediente_stage(eid, "ARQUIVADO", _uid(db, "beatriz"))
    with pytest.raises(SystemExit, match="não está em RECEBIDO"):
        CIENCIA.main(["--banco", str(casa["banco"]), "--arquivar", str(eid), "--confirmar"])
    assert casa["copias"] == []
    assert _contar(db, "SELECT count(*) AS n FROM audit_logs WHERE action='EXPEDIENTE_STAGE'") == 0


def test_o_expediente_que_outra_mesa_arquivou_durante_a_copia_nao_se_arquiva_por_cima(casa):
    db = casa["db"]
    eid = _expediente(db)
    beatriz = _uid(db, "beatriz")
    casa["durante_a_copia"] = lambda: db.update_expediente_stage(eid, "ARQUIVADO", beatriz)
    with pytest.raises(SystemExit, match="não está em RECEBIDO"):
        CIENCIA.main(["--banco", str(casa["banco"]), "--arquivar", str(eid), "--confirmar"])
    e = _um(db, "SELECT completed_by, notes FROM expedientes WHERE id=%s", (eid,))
    assert e["completed_by"] == beatriz, "o arquivamento da outra mesa foi atropelado"
    assert "Ciência do oficial" not in (e["notes"] or "")
    assert _contar(db, "SELECT count(*) AS n FROM audit_logs WHERE action='EXPEDIENTE_STAGE'") == 0


# ------------------------------------------------------ malote_tarefas

def _json_das_tarefas(tmp_path, *tarefas) -> Path:
    caminho = tmp_path / "tarefas.json"
    caminho.write_text(json.dumps(list(tarefas), ensure_ascii=False), encoding="utf-8")
    return caminho


def _pedido(tmp_path, titulo="Conferir a averbação do malote de exemplo", **campos) -> dict:
    anexo = tmp_path / "MALOTE_123_oficio_exemplo.pdf"
    anexo.write_bytes(b"%PDF-1.4\n% oficio de exemplo\n%%EOF\n")
    t = {"titulo": titulo, "descricao": "Ofício do malote para conferir no RCPN.",
         "setor": "RCPN", "responsavel": "beatriz", "substituto": "carla",
         "prazo_dias": 5, "prazo": "2026-10-27", "referencia": "Malote nº 0001",
         "arquivos": [str(anexo)]}
    t.update(campos)
    return t


def test_as_tarefas_sem_confirmar_so_medem_com_o_banco_aberto_so_para_ler(
        casa, conexoes, tmp_path, capsys):
    db = casa["db"]
    antes = _contar(db, "SELECT count(*) AS n FROM tasks")
    lista = _json_das_tarefas(tmp_path, _pedido(tmp_path))
    conexoes.clear()
    assert TAREFAS.main(["--banco", str(casa["banco"]), "--tarefas", str(lista)]) == 0
    saida = capsys.readouterr().out
    assert "a criar: Conferir a averbação do malote de exemplo" in saida
    assert "Só medi. Nada foi gravado." in saida
    _so_para_ler(conexoes, casa["banco"])
    assert _contar(db, "SELECT count(*) AS n FROM tasks") == antes
    assert casa["copias"] == [] and not casa["arquivos"].exists()


def test_as_tarefas_confirmadas_nascem_com_historico_anexo_e_auditoria_e_nao_repetem(
        casa, tmp_path, capsys):
    db = casa["db"]
    pedido = _pedido(tmp_path)
    lista = _json_das_tarefas(tmp_path, pedido)
    assert TAREFAS.main(["--banco", str(casa["banco"]), "--tarefas", str(lista), "--confirmar"]) == 0
    assert "criadas: 1" in capsys.readouterr().out
    assert len(casa["copias"]) == 1 and casa["copias"][0].name.startswith("antes_malote_tarefas_")
    t = _um(db, "SELECT * FROM tasks WHERE title=%s", (pedido["titulo"],))
    assert (t["status"], t["source_type"], t["source_ref"], t["sector"], t["priority"]) \
        == ("ABERTA", "MANUAL", "Malote nº 0001", "RCPN", "ALTA")
    assert (t["assigned_user_id"], t["backup_user_id"], t["created_by"]) \
        == (_uid(db, "beatriz"), _uid(db, "carla"), _uid(db, "mario"))
    assert (t["due_days"], t["due_date"], t["evidence_required"]) == (5, "2026-10-27", 0)
    h = _um(db, "SELECT action, new_value, note FROM task_history WHERE task_id=%s ORDER BY id",
            (t["id"],))
    assert (h["action"], h["new_value"], h["note"]) == ("CRIADA", "ABERTA", pedido["descricao"])
    anexo = _um(db, "SELECT * FROM attachments WHERE entity_type='TASK' AND entity_id=%s",
                (t["id"],))
    guardado = casa["arquivos"] / "Evidencias" / "RCPN" / f"Tarefa-{t['id']:05d}" / "oficio_exemplo.pdf"
    assert anexo["stored_path"] == str(guardado) and guardado.is_file()
    assert anexo["sha256"] == hashlib.sha256(guardado.read_bytes()).hexdigest()
    assert anexo["uploaded_by"] == _uid(db, "mario")
    trilha = _um(db, "SELECT username_snapshot, entity_id, details FROM audit_logs "
                     "WHERE action='TASK_CREATED' ORDER BY id")
    assert trilha["username_snapshot"] == "mario" and str(trilha["entity_id"]) == str(t["id"])
    assert json.loads(trilha["details"])["origem"] == "AGENTE MALOTE"
    # a segunda rodada acha a mesma tarefa aberta e não cria outra
    assert TAREFAS.main(["--banco", str(casa["banco"]), "--tarefas", str(lista), "--confirmar"]) == 0
    saida = capsys.readouterr().out
    assert f"JÁ EXISTE (tarefa {t['id']})" in saida and "criadas: 0" in saida
    assert _contar(db, "SELECT count(*) AS n FROM tasks WHERE title=%s", (pedido["titulo"],)) == 1


def test_a_tarefa_que_a_tela_criou_durante_a_copia_nao_nasce_duas_vezes(casa, tmp_path, capsys):
    db = casa["db"]
    pedido = _pedido(tmp_path)
    lista = _json_das_tarefas(tmp_path, pedido)
    casa["durante_a_copia"] = lambda: _tarefa(db, pedido["titulo"])
    assert TAREFAS.main(["--banco", str(casa["banco"]), "--tarefas", str(lista), "--confirmar"]) == 0
    assert "criadas: 0" in capsys.readouterr().out
    assert _contar(db, "SELECT count(*) AS n FROM tasks WHERE title=%s", (pedido["titulo"],)) == 1
    assert _contar(db, "SELECT count(*) AS n FROM audit_logs WHERE action='TASK_CREATED'") == 0


def test_a_pergunta_ja_existe_e_feita_com_a_trava_do_assunto(casa, tmp_path, monkeypatch):
    import psycopg
    db = casa["db"]
    lista = _json_das_tarefas(tmp_path, _pedido(tmp_path))
    # A trava vale para o banco inteiro, e sob o xdist outro processo roda o
    # mesmo arquivo noutro schema do mesmo banco: a chave do teste é só dele.
    with db.connect() as con:
        trava = f"{TAREFAS.TRAVA}:{con.schema}"
    monkeypatch.setattr(TAREFAS, "TRAVA", trava)
    livre_na_pergunta = []
    original = TAREFAS._igual

    def espiao(bd, titulo, responsavel):
        with psycopg.connect(banco_pg.dsn(), autocommit=True) as outra:
            livre_na_pergunta.append(bool(outra.execute(
                "SELECT pg_try_advisory_xact_lock(hashtext(%s))", (trava,)).fetchone()[0]))
        return original(bd, titulo, responsavel)

    monkeypatch.setattr(TAREFAS, "_igual", espiao)
    assert TAREFAS.main(["--banco", str(casa["banco"]), "--tarefas", str(lista), "--confirmar"]) == 0
    assert livre_na_pergunta == [True, False], (
        "a medição não trava; a pergunta de dentro da escrita, sim: " f"{livre_na_pergunta}")
    assert _contar(db, "SELECT count(*) AS n FROM tasks WHERE source_ref='Malote nº 0001'") == 1


def test_a_falha_no_meio_desfaz_tudo_e_apaga_o_anexo_ja_copiado(casa, tmp_path):
    db = casa["db"]
    primeira = _pedido(tmp_path, "Primeira tarefa de exemplo")
    some = tmp_path / "some_durante_a_copia.pdf"
    some.write_bytes(b"%PDF-1.4\n%%EOF\n")
    segunda = _pedido(tmp_path, "Segunda tarefa de exemplo", arquivos=[str(some)])
    lista = _json_das_tarefas(tmp_path, primeira, segunda)
    antes = _contar(db, "SELECT count(*) AS n FROM tasks")
    casa["durante_a_copia"] = some.unlink
    with pytest.raises(FileNotFoundError):
        TAREFAS.main(["--banco", str(casa["banco"]), "--tarefas", str(lista), "--confirmar"])
    assert _contar(db, "SELECT count(*) AS n FROM tasks") == antes
    assert _contar(db, "SELECT count(*) AS n FROM attachments WHERE entity_type='TASK'") == 0
    assert _contar(db, "SELECT count(*) AS n FROM audit_logs WHERE action='TASK_CREATED'") == 0
    assert not list(casa["arquivos"].rglob("*.pdf")), "anexo sem tarefa ficou no acervo"


# ------------------------------------------------- tarefa_trocar_responsavel

def test_trocar_sem_confirmar_so_mede_com_o_banco_aberto_so_para_ler(casa, conexoes, capsys):
    db = casa["db"]
    tid = _tarefa(db)
    conexoes.clear()
    assert TROCAR.main(["--banco", str(casa["banco"]), "--tarefa", f"{tid}:carla"]) == 0
    assert "Só medi. Nada foi gravado." in capsys.readouterr().out
    _so_para_ler(conexoes, casa["banco"])
    assert _um(db, "SELECT assigned_user_id FROM tasks WHERE id=%s", (tid,))[
        "assigned_user_id"] == _uid(db, "beatriz")
    assert casa["copias"] == []


def test_trocar_confirmado_grava_o_historico_de_cada_mudanca_e_a_auditoria(casa, capsys):
    db = casa["db"]
    beatriz, carla, mario = _uid(db, "beatriz"), _uid(db, "carla"), _uid(db, "mario")
    tid = _tarefa(db, backup_user_id=mario)
    assert TROCAR.main(["--banco", str(casa["banco"]), "--tarefa", f"{tid}:carla:beatriz",
                        "--motivo", "Férias de exemplo", "--confirmar"]) == 0
    assert "feito." in capsys.readouterr().out
    assert len(casa["copias"]) == 1 and casa["copias"][0].name.startswith("antes_trocar_responsavel_")
    t = _um(db, "SELECT assigned_user_id, backup_user_id FROM tasks WHERE id=%s", (tid,))
    assert (t["assigned_user_id"], t["backup_user_id"]) == (carla, beatriz)
    with db.connect() as con:
        historico = banco(con).ler(
            "SELECT action, old_value, new_value, note, user_id FROM task_history "
            "WHERE task_id=%s AND action LIKE 'ALTEROU_%%' ORDER BY id", (tid,))
    assert [(h["action"], h["old_value"], h["new_value"]) for h in historico] == [
        ("ALTEROU_ASSIGNED_USER_ID", str(beatriz), str(carla)),
        ("ALTEROU_BACKUP_USER_ID", str(mario), str(beatriz))]
    assert {(h["note"], h["user_id"]) for h in historico} == {("Férias de exemplo", mario)}
    trilha = _um(db, "SELECT username_snapshot, entity_id, details FROM audit_logs "
                     "WHERE action='TASK_UPDATED' ORDER BY id")
    assert trilha["username_snapshot"] == "mario" and str(trilha["entity_id"]) == str(tid)
    assert json.loads(trilha["details"]) == {"responsavel": carla, "substituto": beatriz,
                                             "motivo": "Férias de exemplo"}


def test_trocar_grava_como_antigo_o_que_estava_no_banco_na_hora_de_gravar(casa):
    # A tela trocou o responsável durante a cópia: o histórico não pode dizer
    # que a tarefa saiu da beatriz, porque ela já estava com o mario.
    db = casa["db"]
    carla, mario = _uid(db, "carla"), _uid(db, "mario")
    tid = _tarefa(db)
    casa["durante_a_copia"] = lambda: db.update_task(tid, {"assigned_user_id": mario}, mario)
    assert TROCAR.main(["--banco", str(casa["banco"]), "--tarefa", f"{tid}:carla", "--confirmar"]) == 0
    h = _um(db, "SELECT old_value, new_value FROM task_history WHERE task_id=%s "
                "AND action='ALTEROU_ASSIGNED_USER_ID' AND user_id=%s ORDER BY id DESC",
            (tid, mario))
    assert (h["old_value"], h["new_value"]) == (str(mario), str(carla))


def test_trocar_prende_a_tarefa_antes_de_gravar(casa, monkeypatch):
    # Sem a ponte, é o FOR UPDATE que segura a tarefa entre a releitura e o
    # UPDATE (a tela faz o mesmo em `database.update_task`).
    import psycopg
    db = casa["db"]
    tid = _tarefa(db)
    with db.connect() as con:
        schema = con.schema
    presa_na_releitura = []
    original = TROCAR._tarefa

    def espiao(bd, tarefa_id, *, prender=False):
        t = original(bd, tarefa_id, prender=prender)
        if prender:
            with psycopg.connect(banco_pg.dsn(), autocommit=True) as outra:
                outra.execute(f'SET search_path TO "{schema}", public')
                try:
                    outra.execute("SELECT id FROM tasks WHERE id=%s FOR UPDATE NOWAIT", (tarefa_id,))
                    presa_na_releitura.append(False)
                except psycopg.errors.LockNotAvailable:
                    presa_na_releitura.append(True)
        return t

    monkeypatch.setattr(TROCAR, "_tarefa", espiao)
    assert TROCAR.main(["--banco", str(casa["banco"]), "--tarefa", f"{tid}:carla", "--confirmar"]) == 0
    assert presa_na_releitura == [True]
