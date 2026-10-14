"""Fatia 1 dos robos do cartorio — schema, CRUD, local, mascara, login.

Nao fala com provedor de verdade. Nao grava no livro. Nao envia WhatsApp.
"""
from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import robo_llm as LLM
import robo_schema as SCH

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


def _sessao(cg_casa):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    bd = cg_casa['db']
    bd.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco, "bd": bd}


@pytest.fixture()
def s(cg_casa):
    return _sessao(cg_casa)


def test_schema_cria_tabelas(s):
    import sqlite3
    con = sqlite3.connect(s["banco"])
    nomes = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ("robo", "robo_exemplo", "robo_config", "robo_teste_log"):
        assert t in nomes, f"faltou tabela {t}"
    chaves = {r[0] for r in con.execute("SELECT chave FROM robo_config")}
    assert "api_key_grok" in chaves
    assert "provedor_padrao" in chaves
    con.close()


def test_criar_robo_e_exemplo(s):
    import sqlite3
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    SCH.init_robo_schema(con)
    rid = SCH.criar_robo(
        con, nome="Certidao nascimento", ato="certidao",
        provedor="grok", prompt="Redija certidao curta.",
        ativo=1, agora="2026-09-07T12:00:00")
    eid = SCH.adicionar_exemplo(
        con, rid, "preciso de certidao", "Segue rascunho de certidao.", 2)
    con.commit()
    robo = SCH.obter_robo(con, rid)
    exs = SCH.exemplos_do_robo(con, rid)
    assert robo["nome"] == "Certidao nascimento"
    assert robo["ato"] == "certidao"
    assert len(exs) == 1
    assert exs[0]["peso"] == 2
    assert eid > 0
    con.close()


def test_rascunhar_modo_local_sem_chave():
    robo = {"prompt": "Voce e o cartorio.", "provedor": "grok"}
    exemplos = [{"entrada": "horario?", "saida_esperada": "Confirme no balcao.",
                 "peso": 1}]
    r = LLM.rascunhar(robo, "Qual o horario?", exemplos, api_key="")
    assert r["modo"] == "local"
    assert "sem chave" in r["aviso"]
    assert "PROMPT:" in r["texto"]
    assert "Voce e o cartorio." in r["texto"]
    assert "Qual o horario?" in r["texto"]
    assert "horario?" in r["texto"]


def test_config_nao_vaza_chave_no_html(s):
    chave_secreta = "sk-test-CHAVE-COMPLETA-NUNCA-VAZAR-xyz987"
    with s["bd"].transaction() as con:
        SCH.gravar_config(con, SCH.CHAVE_GROK, chave_secreta)
    r = s["c"].get("/robos/config")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert chave_secreta not in html
    assert "sk-test-CHAVE-COMPLETA" not in html
    assert "z987" in html  # ultimos 4 (mascarado)
    assert "••••" in html or "****" in html or "gravado" in html.lower()


def test_testar_rota_exige_login(tmp_path):
    """Sem sessao, POST /robos/<id>/testar nao executa o teste.

    Precisa existir usuario: sem nenhum, o redirect e /setup e nao prova login.
    CSRF vem da tela de login (sessao anonima); sem user_id cai no login.
    """
    import glob
    from pathlib import Path

    from app import create_app
    from database import Database

    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    Database(Path(glob.glob(str(dados / "*.sqlite3"))[0])).create_user(
        "tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = app.test_client()
    csrf = _token(c.get("/login").get_data(as_text=True))
    r = c.post(
        "/robos/1/testar",
        data={"csrf_token": csrf, "pedido": "oi"},
        follow_redirects=False,
    )
    assert r.status_code in (301, 302, 303, 307, 308)
    assert "login" in (r.headers.get("Location") or "").lower()


def test_testar_grava_log_local(s):
    csrf = _token(s["c"].get("/robos/novo").get_data(as_text=True))
    s["c"].post("/robos/novo", data={
        "csrf_token": csrf,
        "nome": "Firma",
        "ato": "firma",
        "provedor": "gpt",
        "prompt": "Reconheca firma.",
        "ativo": "1",
    }, follow_redirects=True)
    import sqlite3
    con = sqlite3.connect(s["banco"])
    rid = con.execute("SELECT id FROM robo WHERE nome='Firma'").fetchone()[0]
    con.close()
    csrf2 = _token(s["c"].get(f"/robos/{rid}").get_data(as_text=True))
    r = s["c"].post(f"/robos/{rid}/testar", data={
        "csrf_token": csrf2,
        "pedido": "quero reconhecer firma",
    })
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "modo local" in html.lower() or "sem chave" in html.lower()
    assert "quero reconhecer firma" in html.lower() or "rascunho" in html.lower()
    con = sqlite3.connect(s["banco"])
    logs = list(con.execute(
        "SELECT usuario, modo, pedido FROM robo_teste_log WHERE robo_id=?",
        (rid,)))
    con.close()
    assert len(logs) == 1
    assert logs[0][1] == "local"
    assert "firma" in (logs[0][2] or "").lower()
    assert logs[0][0]  # usuario preenchido
