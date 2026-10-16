"""
A manutencao diaria deixou de rodar em toda requisicao.

O DEFEITO
    `before_request` chamava `ensure_recurring_tasks` e
    `ensure_overdue_escalations` em TODA requisicao, inclusive nos GET. As duas
    abrem `db.transaction()`, que e `BEGIN IMMEDIATE`: tomavam o lock de
    ESCRITA do banco inteiro para abrir qualquer tela.

    Com outro balcao dentro de uma transacao de escrita, um GET simples
    esperava os dez segundos do `busy_timeout` e devolvia HTTP 500 — e a tela
    que morria nao tinha nada a ver com o que estava sendo gravado.

POR QUE UMA VEZ POR DIA E EQUIVALENTE
    As duas trabalham por DATA. Rodar cem vezes no mesmo dia produz o mesmo
    resultado de rodar uma.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def serventia(cg_casa):
    app = cg_casa['app']
    caminho = cg_casa['banco']
    dados = cg_casa['dados']
    cg_casa['db'].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "cliente": c, "banco": caminho}


def test_a_manutencao_roda_uma_vez_e_deixa_a_marca(serventia):
    serventia["cliente"].get("/")
    con = sqlite3.connect(serventia["banco"])
    marca = con.execute("SELECT value FROM settings WHERE key='manutencao_diaria_em'"
                        ).fetchone()
    con.close()
    assert marca and marca[0] == date.today().isoformat()


def test_a_segunda_requisicao_nao_repete_a_manutencao(serventia):
    """Conta chamadas de verdade, trocando os métodos do banco por espiões."""
    db = serventia["app"].extensions["db"]
    chamadas = []
    original_r = db.ensure_recurring_tasks
    original_e = db.ensure_overdue_escalations
    db.ensure_recurring_tasks = lambda *a, **k: (chamadas.append("r"), original_r(*a, **k))[1]
    db.ensure_overdue_escalations = lambda *a, **k: (chamadas.append("e"), original_e(*a, **k))[1]
    try:
        serventia["app"].extensions.pop("manutencao_em", None)
        con = sqlite3.connect(serventia["banco"])
        con.execute("DELETE FROM settings WHERE key='manutencao_diaria_em'")
        con.commit()
        con.close()

        for _ in range(8):
            serventia["cliente"].get("/notas")
        assert chamadas == ["r", "e"], f"rodou {len(chamadas)//2} vez(es), devia ser 1"
    finally:
        db.ensure_recurring_tasks = original_r
        db.ensure_overdue_escalations = original_e


def test_a_manutencao_volta_no_dia_seguinte(serventia):
    con = sqlite3.connect(serventia["banco"])
    con.execute("""INSERT INTO settings(key, value) VALUES('manutencao_diaria_em','2020-01-01')
                   ON CONFLICT(key) DO UPDATE SET value='2020-01-01'""")
    con.commit()
    con.close()
    serventia["app"].extensions.pop("manutencao_em", None)
    serventia["cliente"].get("/notas")
    con = sqlite3.connect(serventia["banco"])
    marca = con.execute("SELECT value FROM settings WHERE key='manutencao_diaria_em'"
                        ).fetchone()[0]
    con.close()
    assert marca == date.today().isoformat()


def test_a_tela_de_leitura_nao_espera_o_lock_de_outro_balcao(serventia, monkeypatch):
    """Era 500 depois de dez segundos. Agora abre na hora.

    Segura o lock de escrita numa conexão à parte e abre telas de leitura.
    Voltando a haver escrita no GET, o teste falha — que é exatamente o que se
    quer detectar.

    A PROVA PASSOU A SER O COMANDO, E NÃO SÓ O RELÓGIO — 14/10/2026. O teto
    era 3 s para as cinco telas juntas, e com quatro suítes na mesma máquina
    as cinco levam 9 s SEM trava nenhuma (medido: a mesma tela, 2 a 10 s): o
    relógio passou a acusar a máquina. Agora o teste (1) registra todo
    comando de escrita que as telas mandam ao banco — `BEGIN IMMEDIATE`,
    `INSERT`, `UPDATE`, `DELETE` — e exige ZERO, que não depende de carga; e
    (2) mantém o relógio, por tela, abaixo do `busy_timeout`, que é a
    assinatura do defeito (quem espera a trava espera os dez segundos).
    O que este guarda pegou em 14/10/2026: `nu_avisos_web` abria
    `db.transaction()` em TODA tela para as recorrências dos avisos — 83 s.
    """
    import re
    from database import Database

    serventia["cliente"].get("/")          # gasta a manutenção do dia

    escritas: list[str] = []
    escreve = re.compile(r"^\s*(BEGIN\s+IMMEDIATE|INSERT|UPDATE|DELETE|REPLACE)\b", re.I)
    original = sqlite3.connect

    def conectar(*a, **k):
        con = original(*a, **k)
        con.set_trace_callback(
            lambda sql: escritas.append(sql[:120]) if escreve.match(sql or "") else None)
        return con

    outro = sqlite3.connect(serventia["banco"], timeout=30)
    outro.execute("PRAGMA busy_timeout=30000")
    outro.execute("BEGIN IMMEDIATE")
    outro.execute("UPDATE settings SET value=value")
    monkeypatch.setattr(sqlite3, "connect", conectar)
    teto = Database.BUSY_TIMEOUT_MS / 1000
    try:
        for caminho in ("/notas", "/notas/livros", "/notas/atos",
                        "/notas/anotacoes/pendentes", "/notas/atos/novo"):
            comeco = time.monotonic()
            resposta = serventia["cliente"].get(caminho)
            decorrido = time.monotonic() - comeco
            assert resposta.status_code == 200, (caminho, resposta.status_code)
            assert not escritas, f"{caminho} escreveu no banco num GET: {escritas}"
            assert decorrido < teto, (
                f"{caminho} esperou {decorrido:.1f}s — o tempo de quem espera a trava")
    finally:
        monkeypatch.setattr(sqlite3, "connect", original)
        outro.rollback()
        outro.close()


def test_a_manutencao_nao_derruba_a_tela_quando_o_banco_esta_travado(serventia):
    """Falhando a manutenção, a requisição segue. Manutenção não derruba tela."""
    db = serventia["app"].extensions["db"]
    serventia["app"].extensions.pop("manutencao_em", None)
    con = sqlite3.connect(serventia["banco"])
    con.execute("DELETE FROM settings WHERE key='manutencao_diaria_em'")
    con.commit()
    con.close()

    original = db.ensure_recurring_tasks

    def explode(*a, **k):
        raise sqlite3.OperationalError("database is locked")

    db.ensure_recurring_tasks = explode
    try:
        assert serventia["cliente"].get("/notas").status_code == 200
        con = sqlite3.connect(serventia["banco"])
        marca = con.execute(
            "SELECT value FROM settings WHERE key='manutencao_diaria_em'").fetchone()
        con.close()
        assert not marca or marca[0] != date.today().isoformat(), \
            "não pode marcar como feita o que falhou — o dia se perderia"
        # E a falha fica registrada, em vez de morrer só no log do servidor.
        con = sqlite3.connect(serventia["banco"])
        erro = con.execute(
            "SELECT value FROM settings WHERE key='manutencao_diaria_erro'").fetchone()
        con.close()
        assert erro and "OperationalError" in erro[0]
    finally:
        db.ensure_recurring_tasks = original


def test_a_obrigacao_diaria_nao_atrasa_quando_o_cartorio_fecha(serventia):
    """O defeito que a primeira versão desta trava criou.

    `ensure_recurring_tasks` avança UM vencimento por chamada. Rodando uma vez
    por dia e pronto, uma obrigação DIÁRIA nunca recuperava dia perdido: todo
    fim de semana atrasava dois dias, para sempre. Em oito semanas de uso a
    deriva medida foi de quinze dias.
    """
    from datetime import timedelta
    atras = (date.today() - timedelta(days=10)).isoformat()
    con = sqlite3.connect(serventia["banco"])
    con.execute(
        """INSERT INTO recurring_obligations(title, frequency, lead_days, active,
                                             next_due_date, created_at, updated_at)
           VALUES ('Conferência diária do protocolo','DAILY',0,1,?,?,?)""",
        (atras, "2026-08-17T09:00:00", "2026-08-17T09:00:00"))
    con.execute("DELETE FROM settings WHERE key='manutencao_diaria_em'")
    con.commit()
    con.close()
    serventia["app"].extensions.pop("manutencao_em", None)

    serventia["cliente"].get("/notas")

    con = sqlite3.connect(serventia["banco"])
    quantas = con.execute(
        "SELECT COUNT(*) FROM tasks WHERE source_type='RECORRENTE'").fetchone()[0]
    proxima = con.execute(
        "SELECT next_due_date FROM recurring_obligations").fetchone()[0]
    con.close()
    # Dez dias de atraso + hoje: onze tarefas, e a obrigação em dia.
    assert quantas >= 11, f"criou só {quantas} — a deriva continua"
    assert proxima > date.today().isoformat()


def test_dois_balcoes_na_mesma_manha_nao_duplicam_tarefa(serventia):
    """A marca sozinha era ler-e-depois-escrever. Agora quem altera a linha ganha."""
    import threading

    app = serventia["app"]
    con = sqlite3.connect(serventia["banco"])
    con.execute(
        """INSERT INTO recurring_obligations(title, frequency, lead_days, active,
                                             next_due_date, created_at, updated_at)
           VALUES ('Remessa quinzenal','DAILY',0,1,?,?,?)""",
        (date.today().isoformat(), "2026-08-17T09:00:00", "2026-08-17T09:00:00"))
    con.execute("DELETE FROM settings WHERE key='manutencao_diaria_em'")
    con.commit()
    con.close()
    app.extensions.pop("manutencao_em", None)

    def balcao():
        c = app.test_client()
        c.post("/login",
               data={"username": "tabeliao", "password": SENHA,
                     "csrf_token": _token(c.get("/login").get_data(as_text=True))},
               follow_redirects=True)
        app.extensions.pop("manutencao_em", None)
        c.get("/notas")

    fios = [threading.Thread(target=balcao) for _ in range(4)]
    for f in fios:
        f.start()
    for f in fios:
        f.join()

    con = sqlite3.connect(serventia["banco"])
    chaves = [r[0] for r in con.execute(
        "SELECT source_ref FROM tasks WHERE source_type='RECORRENTE'")]
    con.close()
    assert len(chaves) == len(set(chaves)), f"tarefa duplicada: {chaves}"


def test_sem_sessao_nao_ha_manutencao(serventia):
    """A tela de login não abre transação de escrita."""
    app = serventia["app"]
    app.extensions.pop("manutencao_em", None)
    con = sqlite3.connect(serventia["banco"])
    con.execute("DELETE FROM settings WHERE key='manutencao_diaria_em'")
    con.commit()
    con.close()

    anonimo = app.test_client()
    anonimo.get("/login")
    con = sqlite3.connect(serventia["banco"])
    marca = con.execute(
        "SELECT value FROM settings WHERE key='manutencao_diaria_em'").fetchone()
    con.close()
    assert marca is None


def test_as_rotinas_continuam_funcionando_quando_rodam(serventia):
    """Uma vez por dia é menos vezes, não menos efeito."""
    db = serventia["app"].extensions["db"]
    con = sqlite3.connect(serventia["banco"])
    con.execute(
        """INSERT INTO recurring_obligations(title, frequency, lead_days, active,
                                             next_due_date, created_at, updated_at)
           VALUES ('Remessa quinzenal à CENSEC','MONTHLY',0,1,?,?,?)""",
        (date.today().isoformat(), "2026-08-17T09:00:00", "2026-08-17T09:00:00"))
    con.execute("DELETE FROM settings WHERE key='manutencao_diaria_em'")
    con.commit()
    con.close()
    serventia["app"].extensions.pop("manutencao_em", None)

    serventia["cliente"].get("/notas")

    con = sqlite3.connect(serventia["banco"])
    quantas = con.execute(
        "SELECT COUNT(*) FROM tasks WHERE source_type='RECORRENTE'").fetchone()[0]
    con.close()
    assert quantas == 1
    assert db is not None


def test_o_traslado_tambem_abre_com_o_banco_travado_por_outro_balcao(serventia):
    """A última tela de leitura que ainda devolvia 500 depois de dez segundos.

    Não era a manutenção: era o `audit("NT_TRASLADO", ...)`, que abre
    `BEGIN IMMEDIATE` como qualquer escrita. `Database.log` passou a tolerar o
    lock — a linha de auditoria vai para o log do servidor, e o documento sai.
    """
    con = sqlite3.connect(serventia["banco"])
    con.execute("""INSERT INTO nt_atos(tipo, data, livro, folha, situacao, teor,
                                       criado_em)
                   VALUES ('PROCURACAO','2024-03-11','27','139','LAVRADO',
                           '<p>poderes</p>','2026-08-17T09:00:00')""")
    con.commit()
    ato_id = con.execute("SELECT MAX(id) FROM nt_atos").fetchone()[0]
    con.close()
    serventia["cliente"].get("/")          # gasta a manutenção do dia

    outro = sqlite3.connect(serventia["banco"], timeout=30)
    outro.execute("PRAGMA busy_timeout=30000")
    outro.execute("BEGIN IMMEDIATE")
    outro.execute("UPDATE settings SET value=value")
    try:
        comeco = time.monotonic()
        resposta = serventia["cliente"].get(f"/notas/atos/{ato_id}/traslado")
        decorrido = time.monotonic() - comeco
        assert resposta.status_code == 200
        assert resposta.mimetype == "application/vnd.oasis.opendocument.text"
        assert decorrido < 3, f"o traslado esperou {decorrido:.1f}s"
    finally:
        outro.rollback()
        outro.close()
