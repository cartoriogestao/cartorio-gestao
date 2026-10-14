"""Os cargos deixaram de ser fixos no código — pedido do oficial em 08/09/2026,
logo depois de a tela Usuários passar a deixar corrigir nome e usuário.

    «permitir editar nome dos cargos»

ONDE ELES MORAVAM
    `caixa_schema.FUNCOES`, uma tupla fixa com a nomenclatura da Lei 8.935/94
    (arts. 20 e 21): Tabelião e Oficial de Registro, Substituto, Escrevente
    Autorizado, Escrevente, Auxiliar. Uma serventia com um cargo que a Lei não
    nomeia nunca teria como cadastrá-lo.

POR QUE É SEGURO DEIXAR EDITAR
    `users.funcao` já era campo de texto livre — nenhum código decide nada
    pelo TEXTO do cargo, só o imprime embaixo da assinatura (Lei 8.935/94,
    arts. 20 e 21). `FUNCOES` continua sendo o de fábrica, semeado uma vez em
    `funcoes_cargos` (settings) — o mesmo padrão de categorias, fontes e
    setores, que já são editados assim em Configurações.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import caixa_schema as CX                                        # noqa: E402

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); usuario+login por teste."""
    cg_casa["db"].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = cg_casa["c"]
    c.post("/login", data={"username": "tabeliao", "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa


def salvar_cargos(c, texto: str):
    html = c.get("/usuarios").get_data(as_text=True)
    return c.post("/usuarios", data={"csrf_token": _token(html), "action": "cargos",
                                     "funcoes_cargos": texto},
                  follow_redirects=True)


def cargos_gravados(banco) -> list[str]:
    con = sqlite3.connect(banco)
    valor = con.execute(
        "SELECT value FROM settings WHERE key='funcoes_cargos'").fetchone()[0]
    con.close()
    return json.loads(valor)


def test_DE_FABRICA_OS_CARGOS_SAO_OS_DA_LEI_8_935(casa):
    assert cargos_gravados(casa["banco"]) == list(CX.FUNCOES)


def test_a_tela_mostra_os_cargos_atuais_para_editar(casa):
    html = casa["c"].get("/usuarios").get_data(as_text=True)
    for cargo in CX.FUNCOES:
        assert cargo in html


def test_RENOMEAR_UM_CARGO_MUDA_A_LISTA(casa):
    novos = ["Tabelião e Oficial de Registro", "Escrevente Substituto",
            "Escrevente", "Auxiliar"]
    salvar_cargos(casa["c"], "\n".join(novos))
    assert cargos_gravados(casa["banco"]) == novos
    html = casa["c"].get("/usuarios").get_data(as_text=True)
    assert "Escrevente Substituto" in html
    assert "Escrevente Autorizado" not in html


def test_ACRESCENTAR_UM_CARGO_QUE_A_LEI_NAO_NOMEIA(casa):
    novos = list(CX.FUNCOES) + ["Escrevente Digital"]
    salvar_cargos(casa["c"], "\n".join(novos))
    assert "Escrevente Digital" in cargos_gravados(casa["banco"])


def test_lista_vazia_e_recusada(casa):
    antes = cargos_gravados(casa["banco"])
    r = salvar_cargos(casa["c"], "   \n  \n")
    assert "não pode ficar vazia" in r.get_data(as_text=True)
    assert cargos_gravados(casa["banco"]) == antes


def test_renomear_cargo_nao_apaga_quem_ja_o_tinha(casa):
    """A pessoa que já tinha o cargo antigo mantém o texto: renomear a
    lista não reescreve o que já foi gravado em cada usuário."""
    from database import Database
    d = Database(casa["banco"])
    uid = d.create_user("escrevente", "MARIA DA SILVA", SENHA, "USER")
    con = sqlite3.connect(casa["banco"])
    con.execute("UPDATE users SET funcao='Escrevente Autorizado' WHERE id=?", (uid,))
    con.commit()
    con.close()

    salvar_cargos(casa["c"], "Tabelião e Oficial de Registro\nEscrevente Substituto")

    assert d.get_user(uid)["funcao"] == "Escrevente Autorizado"


def test_a_edicao_dos_cargos_fica_na_auditoria(casa):
    salvar_cargos(casa["c"], "Tabelião e Oficial de Registro\nEscrevente")
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    linha = con.execute(
        "SELECT * FROM audit_logs WHERE action='CARGOS_ALTERADOS' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    assert linha is not None
    assert "Escrevente" in (linha["details"] or "")
