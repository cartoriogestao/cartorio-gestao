"""O PROJETOS MORA EM TRABALHO E ABRE PARA O ADMINISTRADOR E O GERENTE (24/11/2026).

POR QUE ESTE TESTE EXISTE
    O oficial mandou o Projetos sair de Gestão › Configurações para a área
    Trabalho, numa seção própria, sem mudar o funcionamento nem o endereço. No
    mesmo dia, abriu a tela para o gerente. Aqui se prova:
    - o item está em Trabalho › Projetos e não está mais em Gestão › Configurações;
    - a ficha de um projeto abre com Trabalho › Projetos aberto no menu;
    - ADMIN e MANAGER veem o item (nos dois layouts) e gravam;
    - USER e AUDITOR não veem o item e recebem 403 em todas as rotas;
    - o endereço `/desenvolvimento/projetos` continua o mesmo.

Usuários fictícios. Nada de dado real de pessoa.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import dev_projetos as DP  # noqa: E402
import navegacao as NAV    # noqa: E402

SENHA = "Senha#12345"
ENTRAM = ("ADMIN", "MANAGER")
NAO_ENTRAM = ("USER", "AUDITOR")


def _secoes_com(endpoint: str) -> list[tuple[str, str]]:
    return [(m["chave"], nome) for m in NAV.MODULOS_DA_BARRA
            for nome, itens in m["secoes"] for e in itens if e["endpoint"] == endpoint]


def test_projetos_esta_em_trabalho_e_nao_em_gestao():
    assert _secoes_com("dev_projetos_lista") == [("TRABALHO", "Projetos")]


def test_a_ficha_do_projeto_abre_trabalho_projetos():
    assert NAV.PAI["dev_projetos_detalhe"] == ("TRABALHO", "Projetos")


@pytest.mark.parametrize("papel", ENTRAM + NAO_ENTRAM)
def test_quem_ve_o_item_no_menu_novo(papel):
    achados = [(e["modulo"], e["secao"]) for e in NAV.entradas(papel)
               if e["endpoint"] == "dev_projetos_lista"]
    assert achados == ([("TRABALHO", "Projetos")] if papel in ENTRAM else [])


@pytest.mark.parametrize("papel", ENTRAM + NAO_ENTRAM)
def test_quem_ve_o_item_no_menu_antigo(papel):
    from test_navegacao_registro import menu_antigo
    assert (("dev_projetos_lista", ()) in menu_antigo(papel)) == (papel in ENTRAM)


def _entrar(casa, usuario: str, papel: str):
    casa["db"].create_user(usuario, f"OPERADOR {papel} DE TESTE", SENHA, papel)
    c = casa["app"].test_client()
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                      c.get("/login").get_data(as_text=True)).group(1)
    c.post("/login", data={"username": usuario, "password": SENHA, "csrf_token": token},
           follow_redirects=True)
    return c


def _post(c, url: str, **dados):
    with c.session_transaction() as s:
        token = s.get("csrf_token")
    if not token:
        token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                          c.get("/login").get_data(as_text=True)).group(1)
    return c.post(url, data={"csrf_token": token, **dados})


def _um_projeto(casa) -> int:
    with casa["db"].transaction() as con:
        DP.seed_sandbox_exemplo(con)
        return int(DP.listar_projetos(con)[0]["id"])


def _rotas(pid: int) -> list[tuple[str, str, dict]]:
    base = "/desenvolvimento/projetos"
    return [("GET", base, {}),
            ("GET", f"{base}/{pid}", {}),
            ("POST", f"{base}/{pid}/status", {"status_geral": DP.STATUS_PAUSADO}),
            ("POST", f"{base}/{pid}/proximo-passo", {"proximo_passo": "Conferir com o oficial"}),
            ("POST", f"{base}/{pid}/andamento", {"texto": "Andamento de teste"})]


@pytest.mark.parametrize("papel", ENTRAM)
def test_admin_e_gerente_abrem_e_gravam(cg_casa, papel):
    pid = _um_projeto(cg_casa)
    c = _entrar(cg_casa, f"pessoa_{papel.lower()}", papel)
    for metodo, url, dados in _rotas(pid):
        r = c.get(url) if metodo == "GET" else _post(c, url, **dados)
        assert r.status_code in (200, 302), (papel, url, r.status_code)
    with cg_casa["db"].transaction() as con:
        projeto = DP.obter_projeto(con, pid)
        andamentos = DP.listar_andamento(con, pid)
    assert projeto["status_geral"] == DP.STATUS_PAUSADO
    assert projeto["proximo_passo"] == "Conferir com o oficial"
    assert any(a["texto"] == "Andamento de teste" for a in andamentos)


@pytest.mark.parametrize("papel", NAO_ENTRAM)
def test_balcao_e_auditor_recebem_403(cg_casa, papel):
    pid = _um_projeto(cg_casa)
    c = _entrar(cg_casa, f"pessoa_{papel.lower()}", papel)
    for metodo, url, dados in _rotas(pid):
        r = c.get(url) if metodo == "GET" else _post(c, url, **dados)
        assert r.status_code == 403, (papel, url, r.status_code)
    with cg_casa["db"].transaction() as con:
        assert not any(a["texto"] == "Andamento de teste" for a in DP.listar_andamento(con, pid))
