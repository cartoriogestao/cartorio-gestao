"""A data digitada errada volta à tela com aviso — of-0144.

Um ano de 5 dígitos no campo da tarefa estourava `ValueError` em `parse_date`,
e a tela virava erro 500. Devolver `None` seria pior: a data sumiria em
silêncio, e o prazo seria calculado sem ela.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app import DataInvalida, parse_date                         # noqa: E402

SENHA = "Senha#12345"
DATA_DO_RELATO = "26202-10-26"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def s(cg_casa):
    bd = cg_casa["db"]
    bd.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = cg_casa["app"].test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"c": c, "banco": cg_casa["banco"], "db": bd}


def _contar(s, tabela: str) -> int:
    con = sqlite3.connect(s["banco"])
    try:
        return int(con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0])
    finally:
        con.close()


def _postar(s, endereco: str, **campos):
    token = _token(s["c"].get("/tarefas").get_data(as_text=True))
    return s["c"].post(endereco, data={**campos, "csrf_token": token})


# ------------------------------------------------------------- a função


@pytest.mark.parametrize("digitado, esperado", [
    ("2026-10-26", "2026-10-26"),
    (" 2026-10-26 ", "2026-10-26"),
    ("20261026", "2026-10-26"),
    ("1900-01-01", "1900-01-01"),
    ("2100-12-31", "2100-12-31"),
    ("", None),
    ("   ", None),
    (None, None),
])
def test_a_data_boa_sai_normalizada_e_a_vazia_e_none(digitado, esperado):
    assert parse_date(digitado) == esperado


@pytest.mark.parametrize("digitado", [
    DATA_DO_RELATO, "0026-10-26", "1899-12-31", "2101-01-01",
    "2026-02-30", "amanhã",
])
def test_a_data_errada_levanta_e_nao_vira_none(digitado):
    with pytest.raises(DataInvalida) as erro:
        parse_date(digitado)
    assert erro.value.digitado == digitado


# --------------------------------------------------------------- as rotas


def test_a_tarefa_com_a_data_do_relato_volta_com_aviso(s):
    tarefas = _contar(s, "tasks")
    falhas = _contar(s, "aj_problemas")

    r = _postar(s, "/tarefas", title="Tarefa do teste",
                start_date=DATA_DO_RELATO)

    assert r.status_code == 302
    assert r.headers["Location"].endswith("/tarefas")
    html = s["c"].get("/tarefas").get_data(as_text=True)
    assert DATA_DO_RELATO in html and "Nada foi gravado" in html
    assert _contar(s, "tasks") == tarefas
    assert _contar(s, "aj_problemas") == falhas


def test_o_voltar_de_fora_nao_e_seguido(s):
    r = _postar(s, "/tarefas", title="Tarefa do teste",
                start_date=DATA_DO_RELATO, voltar="//fora.exemplo/x")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/tarefas")


def test_a_edicao_com_data_errada_deixa_a_tarefa_como_estava(s):
    bd = s["db"]
    task_id = bd.create_task({"title": "Original", "start_date": "2026-10-01",
                              "due_date": "2026-10-10"}, None)
    antes = dict(bd.get_task(task_id))

    r = _postar(s, f"/tarefas/{task_id}", action="update", title="Trocado",
                start_date=DATA_DO_RELATO)

    assert r.status_code == 302
    assert r.headers["Location"].endswith(f"/tarefas/{task_id}")
    assert dict(bd.get_task(task_id)) == antes
