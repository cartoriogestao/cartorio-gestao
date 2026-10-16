"""O relatório de erros, por quem praticou (06/10/2026).

Pedido do oficial: «crie um relatorio de erros, com detalhes e quem praticou,
disponivel para o administrador no painel». O que se guarda aqui: o autor sai da
coluna do ato e, vazia, da AUDITORIA (24 dos 25 atos do RI desde 10/09 têm
`lavrado_por` vazio); pendência da casa não entra; e só o ADMIN vê.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import gestor_erros as GER                                       # noqa: E402
from gestor_schema import init_gestor_schema                     # noqa: E402

AGORA = "2026-10-06T08:00:00"
SENHA = "Senha#12345"


_ABERTAS: list = []


def _con(cg_casa):
    c = sqlite3.connect(cg_casa["banco"])
    c.row_factory = sqlite3.Row
    init_gestor_schema(c)
    _ABERTAS.append(c)
    return c


@pytest.fixture(autouse=True)
def _fecha_as_conexoes():
    """Conexão aberta trava o restauro do banco no teste seguinte."""
    yield
    while _ABERTAS:
        c = _ABERTAS.pop()
        c.commit()
        c.close()


def _achado(con, chave, regra, grav="CRITICO", resolvido=None):
    con.execute("""INSERT INTO ge_achados (chave, regra, gravidade, setor, titulo, detalhe,
                       primeiro_visto_em, ultimo_visto_em, resolvido_em)
                   VALUES (?, ?, ?, 'RI_QUALIFICACAO', 'T', 'o detalhe', ?, ?, ?)""",
                (chave, regra, grav, AGORA, AGORA, resolvido))


def _ato_do_ri(con, numero="4300", lavrado_por=None):
    mid = con.execute("INSERT INTO ri_matriculas (numero, teor, criado_em) VALUES (?, 'F', ?)",
                      (numero, AGORA)).lastrowid
    aid = con.execute("""INSERT INTO ri_atos (matricula_id, tipo, numero, teor, lavrado_em,
                             hash_ato, lavrado_por) VALUES (?, 'R', 1, 'R-1', ?, 'h', ?)""",
                      (mid, AGORA, lavrado_por)).lastrowid
    return mid, aid


def test_o_autor_vem_da_auditoria_quando_a_coluna_esta_vazia(cg_casa):
    cg_casa["db"].create_user("carla", "Carla Exemplo Lima", SENHA, "USER")
    con = _con(cg_casa)
    uid = con.execute("SELECT id FROM users WHERE username='carla'").fetchone()[0]
    _, aid = _ato_do_ri(con)
    con.execute("""INSERT INTO audit_logs (ts, user_id, username_snapshot, action, entity_type,
                       entity_id, details) VALUES (?, ?, 'carla', 'RI_ATO_LAVRADO', 'RI_ATO', ?, '{}')""",
                (AGORA, uid, str(aid)))
    _achado(con, f"CNIB_ATO:{aid}", "REGISTRO_SEM_CNIB")
    r = GER.relatorio(con)
    (l,) = r["linhas"]
    assert l["quem"] == "Carla Exemplo Lima" and "auditoria" in l["como"]
    assert l["ato"] == "R-1 da matrícula 4300" and l["link"].startswith("/registro-imoveis/")


def test_a_coluna_do_ato_ganha_e_o_login_vira_nome(cg_casa):
    cg_casa["db"].create_user("beatriz", "Beatriz Exemplo de Souza", SENHA, "USER")
    con = _con(cg_casa)
    _, aid = _ato_do_ri(con, lavrado_por="BEATRIZ")
    # Era ATO_SEM_SELO, que saiu em 06/10/2026 («não existe ato lavrado sem selo»).
    _achado(con, f"CNIB_ATO:{aid}", "REGISTRO_SEM_CNIB")
    (l,) = GER.relatorio(con)["linhas"]
    assert l["quem"] == "Beatriz Exemplo de Souza" and l["como"] == "lavrou"


def test_sem_fonte_nao_se_adivinha(cg_casa):
    con = _con(cg_casa)
    _, aid = _ato_do_ri(con)
    # Era REGISTRO_SEM_PRENOTACAO, que saiu do relatório em 06/10/2026 (só o essencial).
    _achado(con, f"CNIB_ATO:{aid}", "REGISTRO_SEM_CNIB")
    assert GER.relatorio(con)["linhas"][0]["quem"] == GER.NAO_IDENTIFICADO


def test_pendencia_da_casa_nao_entra_e_o_filtro_de_situacao_vale(cg_casa):
    cg_casa["db"].create_user("debora", "Debora Exemplo Reis", SENHA, "USER")
    con = _con(cg_casa)
    cx = con.execute("""INSERT INTO cx_caixas (data, operador_nome, saldo_inicial, aberto_em,
                            situacao) VALUES ('2026-09-20', 'Debora', '0,00', ?, 'ABERTO')""",
                     (AGORA,)).lastrowid
    _achado(con, f"CAIXA_ABERTO:{cx}", "CAIXA_ABERTO")
    _achado(con, "BACKUP:completo", "BACKUP")
    _achado(con, f"CAIXA_CONF:{cx}", "CAIXA_PRONTO_PARA_VISTO")
    _achado(con, f"CAIXA_HOJE:{cx}", "CAIXA_DO_DIA_ABERTO", resolvido=AGORA)
    abertos = GER.relatorio(con, situacao="abertos")["linhas"]
    assert [l["regra"] for l in abertos] == ["CAIXA_ABERTO"]
    assert abertos[0]["quem"] == "Debora Exemplo Reis"
    todos = GER.relatorio(con, situacao="todos")
    assert {l["regra"] for l in todos["linhas"]} == {"CAIXA_ABERTO", "CAIXA_DO_DIA_ABERTO"}
    assert todos["por_pessoa"][0] == {"quem": "Debora Exemplo Reis", "total": 2, "abertos": 1,
                                      "criticos": 1, "categorias": {"Caixa": 2}}


def test_so_o_administrador_ve_a_tela_e_o_painel(cg_casa_logada):
    con = _con(cg_casa_logada)
    _, aid = _ato_do_ri(con, lavrado_por="mario")
    _achado(con, f"CNIB_ATO:{aid}", "REGISTRO_SEM_CNIB")
    con.commit()
    c = cg_casa_logada["c"]
    pagina = c.get("/administrativo/gestor/erros").get_data(as_text=True)
    assert "Relatório de erros" in pagina and "R-1 da matrícula 4300" in pagina
    assert "MARIO EXEMPLO DOS SANTOS" in pagina
    painel = c.get("/").get_data(as_text=True)
    assert "Erros abertos de quem praticou (1)" in painel
    csv = c.get("/administrativo/gestor/erros.csv")
    assert csv.status_code == 200 and "R-1 da matrícula 4300" in csv.get_data(as_text=True)


def test_o_escrevente_nao_ve(cg_casa):
    from conftest import cg_login
    cg_casa["db"].create_user("elisa", "Elisa Exemplo Lima", SENHA, "USER")
    c = cg_casa["c"]
    cg_login(c, "elisa", SENHA)
    assert c.get("/administrativo/gestor/erros").status_code == 403
    assert "Erros abertos de quem praticou" not in c.get("/").get_data(as_text=True)


def test_o_arquivo_do_dia_sai(cg_casa, tmp_path):
    from datetime import date
    con = _con(cg_casa)
    _, aid = _ato_do_ri(con)
    _achado(con, f"CNIB_ATO:{aid}", "REGISTRO_SEM_CNIB")
    p = GER.escrever_html(con, date(2026, 10, 6), tmp_path)
    assert p.name == "erros_2026-10-06.html" and "R-1 da matrícula 4300" in p.read_text("utf-8")
