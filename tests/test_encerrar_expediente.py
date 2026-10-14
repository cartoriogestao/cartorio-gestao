"""O expediente e a tarefa — o relato #24 do oficial.

A FRASE DELE:

    «nao tem botao para encerrar expediente. encerrei a tarefa e o expediente
     segue ativo. Melhorar a integração da tarefa e do expediente, permitir
     encerrar o segundo (…). Acho que os expedientes podem ficar restritos aos
     procedimentos abertos, como escrituras em rascunho, procedimentos de
     georreferenciamento, usucapiao e etc.»

O QUE SE MEDIU EM 29/08/2026
    **13 expedientes, todos em `RECEBIDO`, nenhum com data de conclusão.** Das
    84 tarefas, **5 apontam para expediente** — uma para cada —, e o expediente
    **6** está com a tarefa dele **CONCLUÍDA** e ele ainda aberto. É exatamente
    o caso descrito.

    E encerrar já era possível: `update_expediente_stage` grava `completed_at`
    quando a etapa vira `RESPONDIDO` ou `ARQUIVADO`. **O que não havia era
    botão** — a tela oferecia uma caixa com sete nomes de etapa e um «Atualizar
    etapa». Quem procura «encerrar» não acha «ARQUIVADO» numa lista.

POR QUE O EXPEDIENTE NÃO FECHA SOZINHO
    Hoje é uma tarefa por expediente, e seria fácil fechá-lo quando a tarefa
    fecha. Mas `linked_expediente_id` não é único, e «uma regularidade forte
    dentro de uma casa parece lei até alguém contar as exceções» — esta casa já
    pagou por isso na letra da posição 566 do Protesto.

A TERCEIRA PARTE DO RELATO NÃO VIROU CÓDIGO
    «os expedientes podem ficar restritos aos procedimentos abertos» muda o que
    o módulo é, e isso é desenho e não defeito. Ficou como pergunta ao oficial.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import expediente_tarefa as EXPT

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    c = cg_casa["cliente"]
    db.create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login",
           data={"username": "jean", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _expediente(con, *, protocolo="2026/001", stage="RECEBIDO"):
    cur = con.execute(
        """INSERT INTO expedientes (internal_protocol, source, subject,
               category, received_at, stage, created_by, created_at, updated_at)
           VALUES (?, 'MALOTE', 'ofício da corregedoria', 'CORREGEDORIA',
                   '2026-08-01', ?, 1, '2026-08-01T09:00', '2026-08-01T09:00')""",
        (protocolo, stage))
    return int(cur.lastrowid)


def _tarefa(con, *, expediente_id=None, titulo="responder o ofício",
            status="ABERTA"):
    cur = con.execute(
        """INSERT INTO tasks (title, status, linked_expediente_id,
               created_by, created_at, updated_at)
           VALUES (?,?,?, 1, '2026-08-01T09:00', '2026-08-01T09:00')""",
        (titulo, status, expediente_id))
    return int(cur.lastrowid)


# ------------------------------------------- o que falta para encerrar


def test_com_tarefa_aberta_a_tela_diz_o_que_falta(casa):
    """É aviso, e não trava: quem decide encerrar com tarefa pendente é o
    oficial. Mas ele decide sabendo."""
    con = _con(casa)
    with con:
        eid = _expediente(con)
        _tarefa(con, expediente_id=eid, titulo="juntar a certidão")
    estado = EXPT.o_que_falta_para_encerrar(_con(casa), eid)
    assert estado["pode"] is True          # não impede
    assert estado["tarefas"]["abertas"] == 1
    assert "juntar a certidão" in estado["recado"]
    assert "sem quem cobre" in estado["recado"]


def test_com_tudo_concluido_a_tela_diz_que_pode(casa):
    con = _con(casa)
    with con:
        eid = _expediente(con)
        _tarefa(con, expediente_id=eid, status="CONCLUIDA")
    estado = EXPT.o_que_falta_para_encerrar(_con(casa), eid)
    assert "pode ser encerrado" in estado["recado"]


def test_tarefa_cancelada_nao_segura_o_expediente(casa):
    """Tarefa cancelada é trabalho que se decidiu não fazer. Contá-la como
    aberta deixaria o expediente preso a uma coisa que ninguém vai fazer."""
    con = _con(casa)
    with con:
        eid = _expediente(con)
        _tarefa(con, expediente_id=eid, status="CANCELADA")
        _tarefa(con, expediente_id=eid, status="CONCLUIDA")
    t = EXPT.tarefas_do_expediente(_con(casa), eid)
    assert t["abertas"] == 0
    assert t["total"] == 2


def test_expediente_ja_encerrado_diz_que_esta(casa):
    con = _con(casa)
    with con:
        eid = _expediente(con, stage="ARQUIVADO")
    estado = EXPT.o_que_falta_para_encerrar(_con(casa), eid)
    assert estado["ja_encerrado"] is True
    assert estado["pode"] is False


# ------------------------------------------- «encerrei a tarefa e ele segue ativo»


def test_concluir_a_tarefa_avisa_sobre_o_expediente(casa):
    """O caso do relato, e o do expediente 6 desta casa: a tarefa fechou e o
    expediente ficou aberto, calado."""
    con = _con(casa)
    with con:
        eid = _expediente(con, protocolo="2026/006")
        tid = _tarefa(con, expediente_id=eid, status="CONCLUIDA")
    recado = EXPT.recado_da_tarefa_concluida(_con(casa), tid)
    assert recado is not None
    assert recado["protocolo"] == "2026/006"
    assert recado["abertas"] == 0
    assert recado["ja_encerrado"] is False


def test_tarefa_sem_expediente_nao_fala_de_expediente(casa):
    """79 das 84 tarefas desta casa não pertencem a expediente nenhum. A tela
    não pode falar de expediente para elas — recado que não se aplica é ruído,
    e ruído é o que faz ninguém ler os que se aplicam."""
    con = _con(casa)
    with con:
        tid = _tarefa(con, expediente_id=None)
    assert EXPT.recado_da_tarefa_concluida(_con(casa), tid) is None


def test_o_expediente_nao_fecha_sozinho(casa):
    """O esquema permite várias tarefas por expediente, e fechar na primeira
    deixaria trabalho sem quem cobre. Hoje é uma para cada — e este teste é o
    que impede alguém construir sobre essa regularidade."""
    con = _con(casa)
    with con:
        eid = _expediente(con)
        tid = _tarefa(con, expediente_id=eid, status="CONCLUIDA")
        _tarefa(con, expediente_id=eid, titulo="a segunda, ainda aberta")
    EXPT.recado_da_tarefa_concluida(_con(casa), tid)
    stage = _con(casa).execute(
        "SELECT stage FROM expedientes WHERE id=?", (eid,)).fetchone()["stage"]
    assert stage == "RECEBIDO", "o expediente foi encerrado sozinho"


def test_o_modulo_nao_encerra_nada():
    """Ele só lê e diz. Quem encerra é a rota, pelo caminho que já existia —
    `update_expediente_stage`, que grava a data e quem foi."""
    codigo = (RAIZ / "expediente_tarefa.py").read_text(encoding="utf-8")
    assert "UPDATE " not in codigo
    assert "INSERT " not in codigo
    publicos = [n for n in dir(EXPT) if not n.startswith("_")]
    for proibido in ("encerrar", "arquivar", "fechar", "concluir"):
        assert not [n for n in publicos
                    if n.lower().startswith(proibido)], proibido


# ------------------------------------------- o botão que faltava


def test_a_ficha_tem_botao_de_encerrar_com_esse_nome(casa):
    """«não tem botão para encerrar expediente». Encerrar já era possível:
    bastava achar «ARQUIVADO» numa caixa de sete etapas. Quem procura
    «encerrar» não acha «ARQUIVADO» numa lista."""
    con = _con(casa)
    with con:
        eid = _expediente(con)
    html = casa["cliente"].get(f"/expedientes/{eid}").get_data(as_text=True)
    assert "Encerrar expediente" in html
    assert "Respondido — saiu resposta" in html
    assert "Arquivado — encerrado sem resposta" in html


def test_encerrado_a_ficha_nao_oferece_encerrar_de_novo(casa):
    con = _con(casa)
    with con:
        eid = _expediente(con, stage="ARQUIVADO")
    html = casa["cliente"].get(f"/expedientes/{eid}").get_data(as_text=True)
    assert "Encerrar expediente" not in html
    assert "está arquivado" in html


def test_a_lista_dos_prontos_para_encerrar(casa):
    """O trabalho que acabou e ninguém fechou. Sem esta lista, cada um só
    apareceria a quem abrisse aquele expediente por acaso."""
    con = _con(casa)
    with con:
        pronto = _expediente(con, protocolo="2026/006")
        _tarefa(con, expediente_id=pronto, status="CONCLUIDA")
        andando = _expediente(con, protocolo="2026/007")
        _tarefa(con, expediente_id=andando)
        _expediente(con, protocolo="2026/008")          # sem tarefa nenhuma
    lista = EXPT.expedientes_com_tudo_concluido(_con(casa))
    assert [x["internal_protocol"] for x in lista] == ["2026/006"]
    html = casa["cliente"].get(
        "/expedientes/prontos-para-encerrar").get_data(as_text=True)
    assert "2026/006" in html
    assert "2026/007" not in html


def test_encerrar_pela_tela_grava_a_data_e_quem_foi(casa):
    con = _con(casa)
    with con:
        eid = _expediente(con)
    html = casa["cliente"].get(f"/expedientes/{eid}").get_data(as_text=True)
    casa["cliente"].post(f"/expedientes/{eid}/stage", data={
        "csrf_token": _token(html), "stage": "ARQUIVADO",
        "response_reference": ""}, follow_redirects=True)
    r = _con(casa).execute(
        "SELECT stage, completed_at, completed_by FROM expedientes WHERE id=?",
        (eid,)).fetchone()
    assert r["stage"] == "ARQUIVADO"
    assert r["completed_at"], "o expediente foi marcado sem data de conclusão"
    assert r["completed_by"]
