"""Ids unificados oficial/sandbox — import e sequence."""
import sqlite3

import ajuda_problemas as AP


def _con() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
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
