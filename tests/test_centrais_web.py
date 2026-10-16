"""O painel `/centrais/status` — pelo `test_client`, sem subir servidor."""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import centrais_fila as FILA  # noqa: E402
import centrais_schema as SCH  # noqa: E402

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _falhou(db, central="CRA") -> int:
    with db.transaction() as con:
        novo = FILA.enfileirar(con, central, "remessa", "arquivo:teste")
        FILA.pegar_proximo(con, central=central)
        FILA.marcar_falha(con, novo, "Central recusou (teste)", definitiva=True)
    return novo


def test_o_banco_do_sistema_ja_nasce_com_a_fila(cg_casa):
    with cg_casa["db"].connect() as con:
        nomes = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"centrais_fila", "centrais_log"} <= nomes


def test_painel_vazio_abre(cg_casa_logada):
    r = cg_casa_logada["c"].get("/centrais/status")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    for secao in ("centrais-resumo", "centrais-falhas", "centrais-erros",
                  "centrais-credenciais", "centrais-cliente-http"):
        assert secao in html
    assert "ainda está vazia" in html


def test_painel_lista_falha_e_reprocessa_localmente(cg_casa_logada):
    casa = cg_casa_logada
    novo = _falhou(casa["db"])
    html = casa["c"].get("/centrais/status?central=CRA").get_data(as_text=True)
    assert "Central recusou (teste)" in html
    assert f"/centrais/status/{novo}/reprocessar" in html
    r = casa["c"].post(f"/centrais/status/{novo}/reprocessar",
                       data={"csrf_token": _token(html), "central": "CRA"},
                       follow_redirects=True)
    assert r.status_code == 200
    assert "devolvido à fila" in r.get_data(as_text=True)
    with casa["db"].connect() as con:
        assert FILA.item(con, novo)["status"] == SCH.PENDENTE
        auditado = con.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE action = ?",
            ("CENTRAIS_REPROCESSO",)).fetchone()[0]
    assert auditado == 1


def test_reprocessar_sem_csrf_e_recusado(cg_casa_logada):
    novo = _falhou(cg_casa_logada["db"])
    r = cg_casa_logada["c"].post(f"/centrais/status/{novo}/reprocessar")
    assert r.status_code == 400
    with cg_casa_logada["db"].connect() as con:
        assert FILA.item(con, novo)["status"] == SCH.FALHOU


def test_reprocessar_o_que_nao_falhou_vira_aviso(cg_casa_logada):
    c = cg_casa_logada["c"]
    html = c.get("/centrais/status").get_data(as_text=True)
    r = c.post("/centrais/status/999/reprocessar",
               data={"csrf_token": _token(html)}, follow_redirects=True)
    assert r.status_code == 200
    assert "não está na fila" in r.get_data(as_text=True)


def test_balcao_nao_entra_no_painel(cg_casa):
    cg_casa["db"].create_user("maria", "MARIA DO BALCAO", SENHA, "USER")
    c = cg_casa["c"]
    c.post("/login", data={"username": "maria", "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    assert cg_casa["c"].get("/centrais/status").status_code in (302, 403)


def test_anonimo_vai_para_o_login(cg_casa):
    cg_casa["db"].create_user("mario", "ADMIN DE TESTE", SENHA, "ADMIN")
    r = cg_casa["c"].get("/centrais/status")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_configuracoes_aponta_para_o_painel(cg_casa_logada):
    html = cg_casa_logada["c"].get("/configuracoes").get_data(as_text=True)
    assert "/centrais/status" in html


def test_painel_nao_mostra_segredo(cg_casa_logada):
    html = cg_casa_logada["c"].get("/centrais/status").get_data(as_text=True)
    # Só «informada/não informada»: nenhum campo de segredo nesta tela.
    assert 'type="password"' not in html and 'name="senha"' not in html
    assert 'name="token"' not in html
