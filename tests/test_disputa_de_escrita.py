"""
O aviso de disputa de escrita — o gatilho medido para a conversa sobre migrar.

O QUE ELE É
    `db.transaction()` é `BEGIN IMMEDIATE`: um escritor por vez. Quando dois
    balcões gravam ao mesmo tempo e a espera estoura o `busy_timeout`, o SQLite
    devolve "database is locked". **Nada se perde** — a transação volta atrás
    inteira —, mas quem estava atendendo leva o erro.

    Uma vez ou outra é normal. Virar rotina é o único sinal MEDIDO de que o
    SQLite deixou de bastar para esta casa. Conferido em 25/08/2026: **zero**
    ocorrências em um ano de uso, com 6 usuários e 111 MB.

O QUE ESTES TESTES CONFEREM
    Que a disputa é DETECTADA de verdade — com duas conexões disputando a
    mesma trava, e não com um erro fabricado.

    Que o registro vai para ARQUIVO e não para o banco: gravar a disputa
    dentro do banco que acabou de travar seria disputar a mesma trava.

    E que o aviso não muda o que acontece: o erro sobe igual, a transação
    volta atrás igual.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from database import Database


@pytest.fixture()
def db(tmp_path):
    banco = Database(tmp_path / "b.sqlite3")
    # A casa espera dez segundos antes de desistir. Aqui a espera e curta: o
    # que se prova e que a disputa e DETECTADA, e nao quanto tempo ela dura —
    # e dez segundos por teste sairiam do orcamento da suite.
    banco.BUSY_TIMEOUT_MS = 150
    return banco


def _travar(db) -> sqlite3.OperationalError | None:
    """Duas conexões, uma trava de verdade. Devolve o erro que o balcão leva."""
    fora = db.connect()
    fora.execute("BEGIN IMMEDIATE")
    try:
        with db.transaction() as con:
            con.execute("INSERT INTO settings(key, value) VALUES ('x','1')")
    except sqlite3.OperationalError as erro:
        return erro
    finally:
        fora.rollback()
        fora.close()
    return None


def test_casa_sem_disputa_nao_tem_arquivo_nem_aviso(db):
    # É o caso conferido na produção em 25/08/2026: um ano de uso, zero.
    d = db.disputas_de_escrita()
    assert d == {"total": 0, "recentes": 0, "primeira": None, "ultima": None,
                 "arquivo": str(db.registro_de_disputas)}
    assert not db.registro_de_disputas.exists()
    assert db.dashboard_stats()["disputas_de_escrita"] == 0


def test_a_disputa_e_detectada_e_anotada(db):
    erro = _travar(db)
    assert erro is not None, "a trava tinha de acontecer"
    assert "locked" in str(erro).lower()

    d = db.disputas_de_escrita()
    assert d["total"] == 1 and d["recentes"] == 1
    assert d["primeira"] == d["ultima"]
    linha = db.registro_de_disputas.read_text(encoding="utf-8").strip()
    quando, motivo = linha.split("\t")
    assert len(quando) == 19 and quando[4] == "-"      # a hora da casa, ISO
    assert "locked" in motivo


def test_o_registro_vai_para_arquivo_e_nao_para_o_banco(db):
    # Gravar a disputa dentro do banco que acabou de travar seria disputar a
    # mesma trava, e no pior caso perder o registro que interessa.
    _travar(db)
    assert db.registro_de_disputas.exists()
    assert db.registro_de_disputas.parent == db.db_path.parent
    with db.connect() as con:
        tabelas = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert not any("disputa" in t for t in tabelas)


def test_o_aviso_nao_muda_o_que_acontece(db):
    # O erro sobe igual e a transacao volta atras igual: a anotacao so deixa
    # o rastro para depois.
    _travar(db)
    with db.connect() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM settings WHERE key='x'").fetchone()[0] == 0


def test_cada_disputa_e_uma_linha(db):
    for _ in range(3):
        _travar(db)
    assert db.disputas_de_escrita()["total"] == 3
    assert len(db.registro_de_disputas.read_text(
        encoding="utf-8").strip().splitlines()) == 3


def test_erro_que_nao_e_disputa_nao_entra(db):
    # Regra que estoura por outro motivo nao vira estatistica de trava — senao
    # o gatilho da migracao dispara por engano.
    with pytest.raises(sqlite3.IntegrityError), db.transaction() as con:
        con.execute("INSERT INTO settings(key, value) VALUES ('a','1')")
        con.execute("INSERT INTO settings(key, value) VALUES ('a','2')")
    assert db.disputas_de_escrita()["total"] == 0


def test_o_numero_viaja_com_o_resto_dos_avisos(db):
    # Aviso raro que mora numa tela so e aviso que ninguem ve.
    _travar(db)
    stats = db.dashboard_stats()
    assert stats["disputas_de_escrita"] == 1
    assert stats["disputas_recentes"] == 1
    assert stats["disputas_desde"]


def test_disputa_antiga_conta_no_total_e_nao_nas_recentes(db):
    db.registro_de_disputas.write_text(
        "2020-01-05T09:00:00\tdatabase is locked\n"
        "2020-01-06T09:00:00\tdatabase is locked\n", encoding="utf-8")
    d = db.disputas_de_escrita()
    assert d["total"] == 2
    assert d["recentes"] == 0            # o que importa é o que é recente
    assert d["primeira"].startswith("2020-01-05")
    assert d["ultima"].startswith("2020-01-06")


def test_registro_ilegivel_nao_derruba_a_tela(db):
    # Aviso que quebra a tela e pior que aviso nenhum.
    db.registro_de_disputas.write_bytes(b"\xff\xfe lixo sem tabula\n")
    assert db.disputas_de_escrita()["total"] == 1
    assert db.dashboard_stats()["disputas_de_escrita"] == 1


# ---------------------------------------------------------- aviso na tela

SENHA = "Senha#12345"
AVISO_DISPUTA = "O banco travou"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _sessao(cg_casa, papel: str = "ADMIN"):
    from tests.conftest import cg_login

    cg_casa["db"].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, papel)
    c = cg_casa["c"]
    cg_login(c, "tabeliao", SENHA)
    return cg_casa


def _semear_disputa(cg_casa, linhas: str = "2026-08-26T10:00:00\tdatabase is locked\n"):
    registro = Path(cg_casa["banco"]).parent / Database.NOME_DO_REGISTRO_DE_DISPUTAS
    registro.write_text(linhas, encoding="utf-8")


def test_o_aviso_de_disputa_aparece_em_qualquer_tela(cg_casa):
    s = _sessao(cg_casa)
    _semear_disputa(s)
    for caminho in ("/", "/protesto/titulos", "/nucleo/livros"):
        html = s["c"].get(caminho, follow_redirects=True).get_data(as_text=True)
        assert AVISO_DISPUTA in html, caminho


def test_o_aviso_de_disputa_e_de_quem_responde_pela_serventia(cg_casa):
    s = _sessao(cg_casa, papel="AUDITOR")
    _semear_disputa(s)
    html = s["c"].get("/").get_data(as_text=True)
    assert AVISO_DISPUTA not in html


def test_o_aviso_de_disputa_compacto_expande_os_detalhes(cg_casa):
    s = _sessao(cg_casa)
    _semear_disputa(s)
    html = s["c"].get("/").get_data(as_text=True)
    assert "flash-compact" in html
    assert 'data-aviso-expand' in html
    assert 'aria-expanded="false"' in html
    assert 'id="aviso-disputa-detalhe"' in html
    assert "flash-compact-detalhe" in html
    assert "MIGRAR_DE_BANCO.md" in html
    assert re.search(r"dois balcões gravam", html)
    linha = re.search(
        r'<div class="flash-compact-linha">.*?</div>', html, re.DOTALL)
    assert linha, "a linha compacta do aviso sumiu"
    trecho = linha.group(0)
    assert "MIGRAR_DE_BANCO.md" not in trecho
    assert not re.search(r"dois balcões gravam", trecho)
