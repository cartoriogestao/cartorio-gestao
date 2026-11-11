"""O SQL das travas, num banco descartável.

O arquivo oficial tem `ALTER SYSTEM` e gatilho de evento. Gatilho de evento
pede superusuário. Na suíte, o usuário do PostgreSQL descartável é superusuário.
Neste servidor da casa, o papel não é: o teste não roda, e não mexe no cluster.

O que vale para o CLUSTER inteiro fica de fora do ensaio: `ALTER SYSTEM`,
`pg_reload_conf()` e `ALTER ROLE`. O banco descartável é só um banco; papel e
configuração são do servidor. Rodado contra um cluster que tenha o papel `cg`,
o ensaio tiraria dele o superusuário — o acidente que este arquivo quer evitar.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO = RAIZ / "installer" / "sql" / "travas_da_producao.sql"

# O que muda o servidor, e não o banco do ensaio. Pulado, e conferido que existe.
DO_CLUSTER = ("ALTER SYSTEM", "PG_RELOAD_CONF", "ALTER ROLE")


def _comandos(texto: str):
    """Separa o script em comandos. Ignora linha de psql (`\\set`). Respeita $$."""
    buf: list[str] = []
    dentro = False
    for linha in texto.splitlines():
        if linha.startswith("\\"):
            continue
        buf.append(linha)
        if linha.count("$$") % 2 == 1:
            dentro = not dentro
        if not dentro and linha.rstrip().endswith(";"):
            comando = "\n".join(buf).strip()
            buf = []
            if comando:
                yield comando
    resto = "\n".join(buf).strip()
    if resto:
        yield resto


def test_o_sql_das_travas_recusa_apagar_e_esvaziar():
    dsn = (os.environ.get("CG_PG_DSN") or "").strip()
    if not dsn or "password=" in dsn.lower():
        pytest.skip("sem CG_PG_DSN utilizável")
    from tools.trava_producao import porta_da_producao
    if porta_da_producao(dsn):
        pytest.skip("não roda na porta 5434 da produção")
    with psycopg.connect(dsn, autocommit=True, connect_timeout=8) as pg:
        superuser = pg.execute(
            "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
        ).fetchone()[0]
    if not superuser:
        pytest.skip("gatilho de evento pede superusuário; este papel não é")

    nome = "cg_trava_" + os.urandom(4).hex()
    criado = False
    try:
        with psycopg.connect(dsn, autocommit=True) as pg:
            pg.execute(psycopg.sql.SQL("CREATE DATABASE {}").format(psycopg.sql.Identifier(nome)))
        criado = True
        alvo = psycopg.conninfo.make_conninfo(dsn, dbname=nome)
        with psycopg.connect(alvo, autocommit=True) as pg, pg.cursor() as c:
            c.execute("CREATE SCHEMA producao")
            c.execute("CREATE TABLE producao.t (id int)")
            c.execute("INSERT INTO producao.t VALUES (1)")
            pulados: set[str] = set()
            for comando in _comandos(ARQUIVO.read_text(encoding="utf-8")):
                do_cluster = {m for m in DO_CLUSTER if m in comando.upper()}
                if do_cluster:
                    pulados |= do_cluster
                    continue
                c.execute(comando)
            assert pulados == set(DO_CLUSTER), "o arquivo mudou: confira o que vale para o cluster"
            with pytest.raises(psycopg.Error, match="recusado"):
                c.execute("TRUNCATE producao.t")
            assert c.execute("SELECT count(*) FROM producao.t").fetchone()[0] == 1
            with pytest.raises(psycopg.Error, match="recusado"):
                c.execute("DROP TABLE producao.t")
            c.execute("ALTER TABLE producao.t ADD COLUMN extra text")
            c.execute("ALTER TABLE producao.t DROP COLUMN extra")
            c.execute("CREATE TABLE producao.nova (id int)")
            c.execute("INSERT INTO producao.nova VALUES (2)")
            with pytest.raises(psycopg.Error, match="recusado"):
                c.execute("TRUNCATE producao.nova")
            assert c.execute("SELECT count(*) FROM producao.nova").fetchone()[0] == 1
            with pytest.raises(psycopg.Error, match="recusado"):
                c.execute("DROP SCHEMA producao CASCADE")
    finally:
        if criado:
            with psycopg.connect(dsn, autocommit=True) as pg:
                pg.execute(
                    psycopg.sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                        psycopg.sql.Identifier(nome)))
