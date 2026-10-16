"""ABRIR UM RASCUNHO JÁ SALVO — relato do oficial em 09/09/2026.

    «Salvei um rascunho, mas não tenho como abrir ele no sistema»

O mecanismo salvava, listava e apagava desde 31/08/2026 (relato #36) — e
nunca devolvia o que foi digitado para dentro da tela de onde saiu.
`rascunhos.html` não tinha um único link de abrir, e `rcpn_assento_novo`
(a única tela que já salva) não tinha uma linha sequer que lesse
`?rascunho_id=`.

Ver `rascunho_de_tela.py` (o mecanismo) e `test_rascunho_em_todo_ato.py`
(o «salva» das 13 telas). Este arquivo guarda o «abre» que faltava.
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

import rascunho_de_tela as RASC                                # noqa: E402

SENHA = "Senha#12345"


@pytest.fixture()
def casa(tmp_path):
    from app import create_app
    from database import Database

    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    Database(banco).create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                                SENHA, "ADMIN")
    c = app.test_client()
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                      c.get("/login").get_data(as_text=True)).group(1)
    c.post("/login", data={"username": "tabeliao", "password": SENHA,
                           "csrf_token": token}, follow_redirects=True)
    return {"app": app, "c": c, "banco": banco}


def _salvar_rascunho(casa, **dados) -> int:
    con = sqlite3.connect(casa["banco"])
    RASC.init_rascunho_schema(con)
    r = RASC.salvar(con, tela="rcpn_assento_novo", titulo="Nascimento — ÁUREA",
                     dados=dados, agora="2026-09-09T14:19:45",
                     por="Robô Nascimento RCPN")
    con.commit()
    con.close()
    return r["id"]


def test_a_lista_de_rascunhos_oferece_abrir(casa):
    """O achado do relato: a lista tinha «apagar» e não tinha «abrir»."""
    rid = _salvar_rascunho(casa, especie="NASCIMENTO", pessoa_nome="ÁUREA")
    html = casa["c"].get("/rascunhos").get_data(as_text=True)
    assert f"rascunho_id={rid}" in html, (
        "a lista de rascunhos não oferece um jeito de reabrir o que foi salvo")


def test_abrir_o_rascunho_leva_direto_para_a_especie_certa(casa):
    """Sem espécie na URL, `/rcpn/novo` abre o SELETOR. O rascunho sabe a
    espécie (ele mesmo a guardou) — por isso o redirecionamento tem de levar
    direto ao formulário de nascimento, e não ao seletor."""
    rid = _salvar_rascunho(
        casa, especie="NASCIMENTO", pessoa_nome="ÁUREA EXEMPLO LEÃO",
        filiacao1_nome="DIOGO BITENCOURT BARROS", cor_raca="PARDA")
    r = casa["c"].get(f"/rcpn/novo?rascunho_id={rid}", follow_redirects=False)
    assert r.status_code in (301, 302, 303, 307, 308), (
        f"esperava um redirecionamento para a espécie certa, veio {r.status_code}")
    assert "/nascimento" in r.headers["Location"]
    assert f"rascunho_id={rid}" in r.headers["Location"], (
        "o redirecionamento perdeu o rascunho_id pelo caminho")


def test_abrir_o_rascunho_preenche_o_formulario(casa):
    """**O teste que prova o relato resolvido**: o nome que o robô digitou
    tem de aparecer no campo da tela, não só existir no banco."""
    rid = _salvar_rascunho(
        casa, especie="NASCIMENTO", pessoa_nome="ÁUREA EXEMPLO LEÃO",
        filiacao1_nome="DIOGO BITENCOURT BARROS", cor_raca="PARDA")
    html = casa["c"].get(
        f"/rcpn/novo/nascimento?rascunho_id={rid}",
        follow_redirects=True).get_data(as_text=True)
    assert "ÁUREA EXEMPLO LEÃO" in html, (
        "o rascunho abriu, mas o nome da pessoa não veio para o campo")
    assert "DIOGO BITENCOURT BARROS" in html
    assert "Continuando o rascunho" in html


def test_rascunho_de_outra_tela_nao_abre_aqui(casa):
    """Trocar tela por engano (ou na mão, na URL) não pode vazar o rascunho
    de uma tela para dentro do formulário de outra."""
    con = sqlite3.connect(casa["banco"])
    RASC.init_rascunho_schema(con)
    r = RASC.salvar(con, tela="notas_ato_novo", titulo="Escritura",
                     dados={"nome": "FULANO"}, agora="2026-09-09T14:00:00",
                     por="tabeliao")
    con.commit()
    con.close()
    html = casa["c"].get(
        f"/rcpn/novo?rascunho_id={r['id']}",
        follow_redirects=True).get_data(as_text=True)
    assert "não é de um assento do Registro Civil" in html
    assert "FULANO" not in html


def test_salvar_de_novo_atualiza_em_vez_de_duplicar(casa):
    """Sem `_rascunho_id` no botão de salvar, reabrir e salvar de novo criava
    um SEGUNDO rascunho — o escrevente veria a mesma certidão duplicada."""
    rid = _salvar_rascunho(casa, especie="NASCIMENTO", pessoa_nome="ÁUREA")
    html = casa["c"].get(
        f"/rcpn/novo/nascimento?rascunho_id={rid}").get_data(as_text=True)
    assert f'name="_rascunho_id" value="{rid}"' in html, (
        "o botão de salvar rascunho não carrega o id do rascunho aberto — "
        "salvar de novo criaria um segundo, em vez de atualizar este")
