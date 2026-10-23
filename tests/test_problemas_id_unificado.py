"""Ids unificados oficial/sandbox — import e sequence."""
import sqlite3

import pytest

import ajuda_problemas as AP
import banco_pg
import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402


def _con() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    AP.init_problemas_schema(con)
    return con


def test_insert_com_id_oficial_e_sequence():
    con = _con()
    cols = [r[1] for r in con.execute("PRAGMA table_info(aj_problemas)")
            if r[1] != "id"]
    vals = {
        "impressao": "abc",
        "origem": "RELATADO",
        "titulo": "t",
        "vezes": 1,
        "primeira_em": "2026-01-01",
        "ultima_em": "2026-01-01",
        "situacao": "ABERTO",
        "ambiente_abertura": "OFICIAL",
    }
    row = [vals.get(c) for c in cols]
    con.execute(
        f"INSERT INTO aj_problemas (id, {', '.join(cols)}) "
        f"VALUES (93, {', '.join('?' * len(cols))})",
        row,
    )
    AP.atualizar_sqlite_sequence(con)
    r = AP.anotar(
        con, origem="RELATADO", titulo="outro", agora="2026-01-02T12:00:00")
    assert r["id"] > 93
    assert con.execute("SELECT id FROM aj_problemas WHERE impressao='abc'"
                       ).fetchone()["id"] == 93


def test_realinhar_id_por_impressao():
    con = _con()
    con.execute(
        """INSERT INTO aj_problemas(id, impressao, origem, titulo, vezes,
           primeira_em, ultima_em, situacao, nota_dev)
           VALUES (13, 'x', 'RELATADO', 't', 1, 'a', 'a', 'ABERTO',
           'origem_id_oficial=93\\nREPLICADO_SBX')""")
    AP.realinhar_id_problema(
        con, id_atual=13, id_desejado=93, impressao="x")
    assert con.execute(
        "SELECT id FROM aj_problemas WHERE impressao='x'").fetchone()["id"] == 93


def _insere_amb(con, impressao: str, ambiente: str) -> None:
    con.execute(
        """INSERT INTO aj_problemas(impressao, origem, titulo, vezes,
           primeira_em, ultima_em, situacao, ambiente_abertura)
           VALUES (?, 'RELATADO', 't', 1, 'a', 'a', 'ABERTO', ?)""",
        (impressao, ambiente),
    )


def test_listar_filtro_ambiente_no_sandbox(monkeypatch):
    monkeypatch.setenv(
        "CARTORIO_GESTAO_DATA",
        r"C:\Users\fulano\Downloads\CartorioGestao\SANDBOX\dados",
    )
    con = _con()
    _insere_amb(con, "of", "OFICIAL")
    _insere_amb(con, "sb", "SANDBOX")
    assert len(AP.listar(con, ambiente_filtro="todas")) == 2
    of = AP.listar(con, ambiente_filtro="oficial")
    assert len(of) == 1 and of[0]["ambiente_abertura"] == "OFICIAL"
    sb = AP.listar(con, ambiente_filtro="sandbox")
    assert len(sb) == 1 and sb[0]["ambiente_abertura"] == "SANDBOX"
    assert len(
        AP.listar(con, situacao=("ABERTO",), ambiente_filtro="oficial")
    ) == 1


def test_listar_filtro_ambiente_ignorado_fora_sandbox(monkeypatch):
    monkeypatch.delenv("CARTORIO_GESTAO_DATA", raising=False)
    con = _con()
    _insere_amb(con, "of", "OFICIAL")
    _insere_amb(con, "sb", "SANDBOX")
    assert len(AP.listar(con, ambiente_filtro="oficial")) == 2


# ------------------------------------------------- a trava de quem numera
#
# RESSALVA DA REVISAO DO L055, consertada no L055R. `atualizar_sqlite_sequence`
# lia MAX(id) e fazia `setval` sem trava; `realinhar_id_problema` trocava a PK
# sem ela; e `anotar`, que pega o numero da identidade e soma `vezes`, lia fora
# dela. Enquanto a ponte existe a trava unica do banco serializa tudo; estes
# testes guardam o dia em que ela sair.

com_pg = pytest.mark.skipif(
    not banco_pg.ativo(),
    reason="trava do PostgreSQL: só roda com o PostgreSQL ligado (CG_PG_DSN)")


def _assunto_livre(chave: str) -> bool:
    """Outra conexao consegue a trava do assunto agora? Nao espera por ela."""
    import psycopg
    with psycopg.connect(banco_pg.dsn(), autocommit=True) as outra:
        return bool(outra.execute(
            "SELECT pg_try_advisory_xact_lock(hashtext(%s))", (chave,)).fetchone()[0])


@com_pg
def test_o_contador_da_identidade_se_acerta_dentro_da_trava():
    con = _con()
    _insere_amb(con, "of", "OFICIAL")
    con.commit()
    assert _assunto_livre("aj_problemas.id")
    AP.atualizar_sqlite_sequence(con)
    assert not _assunto_livre("aj_problemas.id")
    con.rollback()
    assert _assunto_livre("aj_problemas.id")


@com_pg
def test_realinhar_a_pk_trava_o_assunto():
    con = _con()
    con.execute(
        """INSERT INTO aj_problemas(id, impressao, origem, titulo, vezes,
           primeira_em, ultima_em, situacao)
           VALUES (13, 'x', 'RELATADO', 't', 1, 'a', 'a', 'ABERTO')""")
    con.commit()
    AP.realinhar_id_problema(con, id_atual=13, id_desejado=93, impressao="x")
    assert not _assunto_livre("aj_problemas.id")
    con.rollback()


@com_pg
def test_o_plano_do_realinhamento_e_lido_dentro_da_trava(monkeypatch):
    con = _con()
    con.execute(
        """INSERT INTO aj_problemas(id, impressao, origem, titulo, vezes,
           primeira_em, ultima_em, situacao, nota_dev)
           VALUES (13, 'x', 'RELATADO', 't', 1, 'a', 'a', 'ABERTO',
           'origem_id_oficial=93\\nREPLICADO_SBX')""")
    con.commit()
    livre_no_plano = []
    original = AP.id_oficial_da_nota

    def espiao(nota):
        livre_no_plano.append(_assunto_livre("aj_problemas.id"))
        return original(nota)

    monkeypatch.setattr(AP, "id_oficial_da_nota", espiao)
    stats = AP.realinhar_ids_replicados(con, dry_run=False)
    assert stats["realinhados"] == 1
    assert livre_no_plano == [False]
    con.rollback()


@com_pg
def test_anotar_le_e_numera_dentro_da_trava(monkeypatch):
    con = _con()
    con.commit()
    livre_antes_do_insert = []
    original = AP.ambiente_abertura_padrao

    def espiao(c):
        livre_antes_do_insert.append(_assunto_livre("aj_problemas.id"))
        return original(c)

    monkeypatch.setattr(AP, "ambiente_abertura_padrao", espiao)
    r = AP.anotar(con, origem="RELATADO", titulo="novo",
                  agora="2026-01-02T12:00:00")
    assert r["nova"] and livre_antes_do_insert == [False]
    con.commit()
    r = AP.anotar(con, origem="RELATADO", titulo="novo",
                  agora="2026-01-02T12:05:00")
    assert r["vezes"] == 2
    assert not _assunto_livre("aj_problemas.id")
    con.rollback()
