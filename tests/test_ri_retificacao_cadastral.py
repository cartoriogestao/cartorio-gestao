"""Usuário pode corrigir cadastro da matrícula com motivo e trilha atômica."""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
SENHA = "Senha#12345"


def _token(html):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


@pytest.fixture()
def casa(cg_casa):
    cg_casa["db"].create_user("balcao_ri", "Usuária do RI", SENHA, "USER")
    con = sqlite3.connect(cg_casa["banco"])
    with con:
        mid = con.execute(
            """INSERT INTO ri_matriculas
               (numero, livro, livro_norm, situacao, tipo_ficha, origem,
                logradouro, descricao_perimetro, teor, atualizado_em, criado_em)
               VALUES ('990021', '2', '2', 'ATIVO', 'ESTRUTURADA', 'MANUAL',
                       'Rua preservada', 'Descrição original.',
                       'Descrição original. Ato lavrado.',
                       '2026-09-28T09:00:00', '2026-09-28T08:00:00')""").lastrowid
    con.close()
    cliente = cg_casa["app"].test_client()
    tela = cliente.get("/login").get_data(as_text=True)
    cliente.post("/login", data={"username": "balcao_ri", "password": SENHA,
                                "csrf_token": _token(tela)}, follow_redirects=True)
    return {**cg_casa, "cliente": cliente, "mid": mid}


def _editar(casa, motivo, descricao, versao=None):
    c, mid = casa["cliente"], casa["mid"]
    html = c.get(f"/registro-imoveis/{mid}/editar").get_data(as_text=True)
    if versao is None:
        versao = re.search(r'name="versao_edicao" value="([^"]*)"', html).group(1)
    return c.post(f"/registro-imoveis/{mid}/editar",
                  data={"csrf_token": _token(html), "versao_edicao": versao,
                        "descricao_perimetro": descricao, "motivo": motivo},
                  follow_redirects=True)


def _dados(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    m = con.execute("SELECT * FROM ri_matriculas WHERE id=?", (casa["mid"],)).fetchone()
    logs = con.execute("""SELECT * FROM audit_logs
                           WHERE action='RI_MATRICULA_EDITADA' AND entity_id=?""",
                       (casa["mid"],)).fetchall()
    con.close()
    return m, logs


def test_usuario_ve_botao_e_motivo_e_retifica_so_o_cadastro(casa):
    c, mid = casa["cliente"], casa["mid"]
    ficha = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Retificar dados cadastrais" in ficha
    tela = c.get(f"/registro-imoveis/{mid}/editar").get_data(as_text=True)
    assert "Motivo da retificação cadastral" in tela
    resposta = _editar(casa, "Conferência com a descrição no título", "Descrição original. Complemento.")
    assert resposta.status_code == 200
    m, logs = _dados(casa)
    assert m["descricao_perimetro"] == "Descrição original. Complemento."
    assert m["logradouro"] == "Rua preservada"  # campo ausente não se apaga
    assert m["teor"] == "Descrição original. Ato lavrado."
    assert len(logs) == 1
    detalhes = json.loads(logs[0]["details"])
    assert detalhes["motivo"] == "Conferência com a descrição no título"
    assert detalhes["mudancas"]["descricao_perimetro"] == {
        "de": "Descrição original.", "para": "Descrição original. Complemento."}
    assert logs[0]["username_snapshot"] == "balcao_ri"


def test_motivo_curto_nao_muda_a_matricula(casa):
    resposta = _editar(casa, "erro", "Texto indevido")
    assert "pelo menos 10 caracteres" in resposta.get_data(as_text=True)
    m, logs = _dados(casa)
    assert m["descricao_perimetro"] == "Descrição original."
    assert not logs


def test_formulario_antigo_nao_sobrescreve_correcao_recente(casa):
    tela_antiga = casa["cliente"].get(
        f"/registro-imoveis/{casa['mid']}/editar").get_data(as_text=True)
    token_antigo = re.search(
        r'name="versao_edicao" value="([^"]*)"', tela_antiga).group(1)
    _editar(casa, "Conferência da primeira correção", "Texto novo")
    resposta = _editar(casa, "Conferência da segunda correção", "Texto obsoleto",
                      versao=token_antigo)
    assert "foi alterada por outra pessoa" in resposta.get_data(as_text=True)
    m, logs = _dados(casa)
    assert m["descricao_perimetro"] == "Texto novo"
    assert len(logs) == 1
