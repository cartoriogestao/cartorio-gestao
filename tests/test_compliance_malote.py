"""O verificador interno sobre o malote — 11/10/2026.

Ordem do oficial (via sessão 12): «vamos integrar o verificador interno para
revisar e cobrir falhas» do agente do malote. O que se guarda: o arquivo baixado
que ninguém cadastrou aparece; o expediente que a triagem não leu aparece; o
anexo que sumiu ou mudou aparece; e o compliance não importa o agente.
"""
from __future__ import annotations

import ast
import hashlib
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import compliance as CP                                          # noqa: E402
import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

AGORA = datetime(2026, 10, 14, 9, 0)          # uma quarta-feira


@pytest.fixture()
def con():
    c = conexao_de_teste()
    c.executescript("""
        CREATE TABLE expedientes (id INTEGER PRIMARY KEY, internal_protocol TEXT, source TEXT,
            subject TEXT, stage TEXT, created_at TEXT);
        CREATE TABLE attachments (id INTEGER PRIMARY KEY, entity_type TEXT, entity_id INTEGER,
            original_name TEXT, stored_path TEXT, sha256 TEXT);
        CREATE TABLE tasks (id INTEGER PRIMARY KEY, linked_expediente_id INTEGER, status TEXT);
        CREATE TABLE ge_triagens (id INTEGER PRIMARY KEY, expediente_id INTEGER, erro TEXT,
            lido_em TEXT);
    """)
    yield c
    c.close()


def _ctx(con, **kw):
    return CP.Contexto(con=con, agora=AGORA, agendador=[], saude=lambda: {"ok": True}, **kw)


def _arquivo(p: Path, conteudo: bytes, dia: datetime) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(conteudo)
    t = time.mktime(dia.timetuple())
    os.utime(p, (t, t))
    return p


def test_o_compliance_nao_importa_o_agente_do_malote():
    arvore = ast.parse((RAIZ / "compliance.py").read_text(encoding="utf-8"))
    importados = {a.name for no in ast.walk(arvore) if isinstance(no, ast.Import) for a in no.names}
    importados |= {no.module for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom) and no.module}
    assert not any(m.startswith("malote") for m in importados)


def test_arquivo_parado_aparece_e_o_cadastrado_nao(con, tmp_path):
    pasta_malote = tmp_path / "MALOTE"
    parado = _arquivo(pasta_malote / "PARA CADASTRAR" / "divorcio.pdf", b"a", datetime(2026, 9, 23))
    feito = _arquivo(pasta_malote / "PARA CADASTRAR" / "circular.pdf", b"b", datetime(2026, 9, 23))
    _arquivo(pasta_malote / "PARA CADASTRAR" / "certidao-rcpn-81-2026.pdf", b"c", datetime(2026, 9, 23))
    _arquivo(pasta_malote / "PARA CADASTRAR" / "hoje.pdf", b"d", AGORA)
    con.execute("INSERT INTO attachments VALUES (1,'EXPEDIENTE',1,'circular.pdf','x',?)",
                (hashlib.sha256(feito.read_bytes()).hexdigest(),))
    achados = CP.regra_malote_parado(_ctx(con, pasta_malote=pasta_malote))
    assert [a["evidencia"] for a in achados] == [str(parado)]
    assert achados[0]["gravidade"] == "CRITICO"


def test_sem_pasta_de_dados_nao_le_o_disco_real(con):
    assert CP._pastas_de_entrada_do_malote(_ctx(con)) == []


def test_expediente_sem_triagem_e_sem_tarefa_aparece(con):
    con.executemany("INSERT INTO expedientes VALUES (?,?,?,?,?,?)", [
        (1, "EXP-2026-000032", "Malote Digital", "Divórcio", "RECEBIDO", "2026-10-11T17:40:00"),
        (2, "EXP-2026-000033", "Malote Digital", "Lido", "RECEBIDO", "2026-10-11T17:40:00"),
        (3, "EXP-2026-000034", "Malote Digital", "Com tarefa", "RECEBIDO", "2026-10-11T17:40:00"),
        (4, "EXP-2026-000035", "Malote Digital", "Antigo", "RECEBIDO", "2026-08-01T10:00:00"),
        (5, "EXP-2026-000036", "Malote Digital", "De hoje", "RECEBIDO", "2026-10-14T08:00:00"),
    ])
    con.execute("INSERT INTO ge_triagens VALUES (1, 2, NULL, '2026-10-12T07:30:00')")
    con.execute("INSERT INTO ge_triagens VALUES (2, 1, 'AgenteError: modelo', '2026-10-12T07:30:00')")
    con.execute("INSERT INTO tasks VALUES (1, 3, 'ABERTA')")
    achados = CP.regra_malote_sem_triagem(_ctx(con))
    assert [a["chave"] for a in achados] == ["MALOTE_SEM_TRIAGEM:1"]
    assert "AgenteError" in achados[0]["detalhe"]


def test_anexo_sumido_ou_trocado_e_critico(con, tmp_path):
    bom = _arquivo(tmp_path / "bom.pdf", b"ok", AGORA)
    trocado = _arquivo(tmp_path / "trocado.pdf", b"outro", AGORA)
    con.executemany("INSERT INTO expedientes VALUES (?,?,?,?,?,?)", [
        (1, "EXP-1", "Malote Digital", "a", "RECEBIDO", "2026-10-11T17:40:00"),
        (2, "EXP-2", "Malote Digital", "b", "RECEBIDO", "2026-10-11T17:40:00"),
    ])
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()           # noqa: E731
    con.executemany("INSERT INTO attachments VALUES (?,?,?,?,?,?)", [
        (1, "EXPEDIENTE", 1, "bom.pdf", str(bom), sha(bom)),
        (2, "EXPEDIENTE", 1, "trocado.pdf", str(trocado), "0" * 64),
        (3, "EXPEDIENTE", 1, "sumido.pdf", str(tmp_path / "nao.pdf"), "1" * 64),
    ])
    achados = CP.regra_malote_anexo_confere(_ctx(con))
    chaves = sorted(a["chave"] for a in achados)
    assert chaves == ["MALOTE_ANEXO:2", "MALOTE_ANEXO:3", "MALOTE_SEM_ANEXO:2"]
    assert {a["gravidade"] for a in achados if a["chave"].startswith("MALOTE_ANEXO:")} == {"CRITICO"}


def test_as_tres_regras_estao_no_catalogo():
    nomes = {n for n, _ in CP.REGRAS}
    assert {"MALOTE_PARADO", "MALOTE_SEM_TRIAGEM", "MALOTE_ANEXO_CONFERE"} <= nomes
    assert all(CP.AREA_DA_REGRA[n] == "AGENTES" for n in
               ("MALOTE_PARADO", "MALOTE_SEM_TRIAGEM", "MALOTE_ANEXO_CONFERE"))


def test_aviso_de_fraude_lido_pela_ia_nao_e_malote_parado(con, tmp_path):
    # ordem de 13/10/2026: aviso de fraude não vira expediente; levado à lista de
    # fraudes (linha FRAUDE do agente), ele está resolvido — e não acusa parado
    pasta_malote = tmp_path / "MALOTE"
    aviso = _arquivo(pasta_malote / "PARA CADASTRAR" / "fraude.pdf", b"f", datetime(2026, 9, 23))
    pendente = _arquivo(pasta_malote / "PARA CADASTRAR" / "golpe.pdf", b"g", datetime(2026, 9, 23))
    con.execute("CREATE TABLE mt_arquivos (sha256 TEXT, situacao TEXT)")
    con.execute("INSERT INTO mt_arquivos VALUES (?, 'FRAUDE')", (hashlib.sha256(b"f").hexdigest(),))
    con.execute("INSERT INTO mt_arquivos VALUES (?, 'FRAUDE_PENDENTE')", (hashlib.sha256(b"g").hexdigest(),))
    achados = CP.regra_malote_parado(_ctx(con, pasta_malote=pasta_malote))
    assert [a["evidencia"] for a in achados] == [str(pendente)]
    assert str(aviso) not in str(achados)
