"""A tela Usuários só sabia CRIAR — pedido do oficial em 08/09/2026.

    «acrescente a possibilidade do administrador alterar qualquer campo do
     sistema, em especial editar nome e usuario dos usuarios do sistema»

O QUE JÁ EXISTIA
    Criar, trocar senha, ativar/desativar e mudar a função (o rótulo que sai
    embaixo da assinatura). Nome, usuário e perfil nunca podiam ser
    corrigidos depois de gravados — um erro de digitação no cadastro ficava
    para sempre, do mesmo jeito que o nome do delegatário ficou errado em
    `ri_registrador` até hoje, sem tela para corrigir (achado na mesma
    passada).

O QUE ESTE ARQUIVO PROTEGE
    Que o ADMIN corrija nome, usuário e perfil de qualquer um — inclusive o
    próprio nome e usuário —, sem poder se trancar do lado de fora rebaixando
    o próprio perfil durante a sessão. É a mesma regra do botão "Desativar",
    que já recusa desativar quem está logado.
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

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    d = cg_casa["db"]
    c = cg_casa["c"]
    admin_id = d.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    escrevente_id = d.create_user("escrevente", "MARIA DA SILVA", SENHA, "USER")
    c.post("/login", data={"username": "tabeliao", "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {**cg_casa, "admin_id": admin_id, "escrevente_id": escrevente_id}

def editar(c, uid, **campos):
    html = c.get("/usuarios").get_data(as_text=True)
    dados = {"csrf_token": _token(html), "action": "editar", "user_id": uid}
    dados.update(campos)
    return c.post("/usuarios", data=dados, follow_redirects=True)


def usuario(banco, uid):
    con = sqlite3.connect(banco)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    con.close()
    return row


def test_O_NOME_ERRADO_DE_OUTRO_USUARIO_SE_CORRIGE(casa):
    """O caso que motivou o pedido: `EXEMPLO` sem o T."""
    r = editar(casa["c"], casa["admin_id"],
               full_name="MARIO EXEMPLO DOS SANTOS", username="tabeliao", role="ADMIN")
    assert r.status_code == 200
    assert "Usuário atualizado" in r.get_data(as_text=True)
    assert usuario(casa["banco"], casa["admin_id"])["full_name"] == "MARIO EXEMPLO DOS SANTOS"


def test_username_tambem_se_corrige(casa):
    editar(casa["c"], casa["escrevente_id"], full_name="MARIA DA SILVA",
          username="maria.silva", role="USER")
    assert usuario(casa["banco"], casa["escrevente_id"])["username"] == "maria.silva"


def test_o_perfil_de_outro_usuario_pode_subir_ou_descer(casa):
    editar(casa["c"], casa["escrevente_id"], full_name="MARIA DA SILVA",
          username="escrevente", role="MANAGER")
    assert usuario(casa["banco"], casa["escrevente_id"])["role"] == "MANAGER"


def test_NAO_DEIXA_REBAIXAR_O_PROPRIO_PERFIL_NA_SESSAO(casa):
    """A mesma regra do botão Desativar, agora para o perfil: o ADMIN nunca
    se tranca do lado de fora durante a própria sessão."""
    r = editar(casa["c"], casa["admin_id"], full_name="MARIO EXEMPLO DOS SANTOS",
              username="tabeliao", role="USER")
    assert "rebaixar o próprio perfil" in r.get_data(as_text=True)
    assert usuario(casa["banco"], casa["admin_id"])["role"] == "ADMIN"


def test_o_proprio_nome_e_usuario_continuam_editaveis(casa):
    """A guarda é só contra rebaixar o PRÓPRIO PERFIL — nome e usuário do
    próprio administrador continuam livres, é o caso do pedido."""
    r = editar(casa["c"], casa["admin_id"], full_name="MARIO EXEMPLO DOS SANTOS",
              username="jean.exemplo", role="ADMIN")
    assert "Usuário atualizado" in r.get_data(as_text=True)
    row = usuario(casa["banco"], casa["admin_id"])
    assert row["full_name"] == "MARIO EXEMPLO DOS SANTOS"
    assert row["username"] == "jean.exemplo"


def test_username_duplicado_e_recusado_sem_derrubar_a_tela(casa):
    r = editar(casa["c"], casa["escrevente_id"], full_name="MARIA DA SILVA",
              username="tabeliao", role="USER")
    assert r.status_code == 200
    assert "Já existe outro usuário" in r.get_data(as_text=True)
    assert usuario(casa["banco"], casa["escrevente_id"])["username"] == "escrevente"


def test_nome_vazio_e_recusado(casa):
    r = editar(casa["c"], casa["escrevente_id"], full_name="", username="escrevente",
              role="USER")
    assert "Informe o nome" in r.get_data(as_text=True)


def test_usuario_vazio_e_recusado(casa):
    r = editar(casa["c"], casa["escrevente_id"], full_name="MARIA DA SILVA",
              username="", role="USER")
    assert "Informe o usuário" in r.get_data(as_text=True)


def test_a_tela_mostra_os_campos_ja_preenchidos_para_editar(casa):
    html = casa["c"].get("/usuarios").get_data(as_text=True)
    assert 'value="MARIO EXEMPLO DOS SANTOS"' in html
    assert 'value="tabeliao"' in html
    assert 'value="MARIA DA SILVA"' in html
    assert 'value="escrevente"' in html


def test_a_edicao_fica_na_auditoria(casa):
    editar(casa["c"], casa["escrevente_id"], full_name="MARIA DA SILVA SOUSA",
          username="escrevente", role="USER")
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    linha = con.execute(
        "SELECT * FROM audit_logs WHERE action='USER_EDITED' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    con.close()
    assert linha is not None
    assert "MARIA DA SILVA SOUSA" in (linha["details"] or "")


def test_usuario_inexistente_nao_derruba_a_tela(casa):
    r = editar(casa["c"], 999999, full_name="X", username="y", role="USER")
    assert r.status_code == 200
    assert "Usuário inválido" in r.get_data(as_text=True)
