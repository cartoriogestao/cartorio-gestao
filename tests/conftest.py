# -*- coding: utf-8 -*-
"""Fixtures compartilhadas de DB/app para a suite pytest.

POR QUE EXISTEM
    create_app + Database() custam ~0,8-1,5 s e ~2 MB por chamada (schema
    inteiro). Muitos arquivos montavam isso por funcao. Aqui o schema sobe
    uma vez por modulo; entre testes o isolamento e barato (DELETE/INSERT
    so das tabelas com dados, a partir de um seed), sem dropar schema e sem
    tocar o SQLite de producao.

API (use nos testes novos ou ao migrar um arquivo)
    cg_data_dir  - Path do DATA_DIR do modulo (scope=module)
    cg_app       - Flask app ja montado (scope=module)
    cg_db_path   - Path do cartorio_gestao.sqlite3 do modulo
    cg_db        - Database() com DB restaurado ao seed (scope=function)
    cg_client    - app.test_client() fresco; depende de cg_db (reset incluso)
    cg_casa      - dict {app, cliente, c, banco, db, dados, acervo} limpo
    cg_casa_logada - cg_casa + admin mario logado (nao usar em testes de auth)
    cg_login(client, user, senha) - helper de login com CSRF

QUANDO NAO USAR
    - Teste que precisa de DB virgem absoluto diferente do seed de fabrica
      (ex.: schema parcial em :memory: proprio) -- continue local.
    - Teste que aponta para producao / CARTORIO_GESTAO_DATA real -- nunca use
      estas fixtures para isso; o seed e sempre sob tmp do pytest.
    - Teste que deixa conexoes sqlite abertas e precisa substituir o arquivo
      no mesmo path: o restore e SQL (ATTACH), nao shutil.copy.

COMO MIGRAR UM ARQUIVO
    1. Remova o create_app/tmp_path da fixture local.
    2. Depend de cg_casa (ou cg_app + cg_db) e faca so o setup do dominio
       (create_user, login, INSERT de fixture).
    3. Rode so aquele arquivo: pytest --durations=10 tests/test_X.py
    4. Compare setup time: antes ~2 s/teste; depois dezenas de ms
       (custo amortizado no setup de modulo).

Producao (ProgramData/CartorioGestao/cartorio_gestao.sqlite3) nunca e usada:
DATA_DIR vem de tmp_path_factory. Ver tambem DOCUMENTACAO/FIXTURES_DE_TESTE.md.
"""
from __future__ import annotations

import re
import shutil
import sqlite3
import sys
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import os  # noqa: E402

# MIGRAÇÃO PARA O POSTGRESQL (cópia MIGRACAO_PG, 15/10/2026): com
# CG_TEST_BACKEND=pg e CG_PG_DSN, o banco de cada teste vai para um schema
# próprio no PostgreSQL de teste, e o schema é apagado quando o teste acaba.
# Sem a variável, a suíte roda no SQLite como sempre.
BACKEND_PG = os.environ.get("CG_TEST_BACKEND", "").strip().lower() == "pg"
if BACKEND_PG:
    if not os.environ.get("CG_PG_DSN", "").strip():
        raise RuntimeError("CG_TEST_BACKEND=pg exige CG_PG_DSN")
    import banco_pg  # noqa: E402

    banco_pg.instalar_desvio()
# Os agentes da migração rodam pedaços da suíte em paralelo nesta cópia.
SEM_TRAVA = os.environ.get("CG_SEM_TRAVA_DA_SUITE", "").strip() == "1"

# A SERVENTIA DOS TESTES É FICTÍCIA — sanitização B3, 10/10/2026. As sementes
# de `database.DEFAULT_SETTINGS` nascem vazias desde a B2b (a identidade vem
# do perfil local), e os testes precisam de uma serventia preenchida: esta,
# com o CNS 000000 que o varredor anti-vazamento reconhece como fictício.
# Quem monta banco por `Database()` em qualquer teste a recebe.
SERVENTIA_DE_TESTE = {
    "unit_name": "Ofício Único de Cidade Exemplo/MA",
    "ri_cns": "000000",
    "ri_cidade": "Cidade Exemplo",
    "ri_uf": "MA",
    "ri_registrador": "Mario Exemplo dos Santos",
    "ri_substituta": "Beatriz Exemplo de Souza",
    "ri_feriados_locais": ("2026-07-28  # Adesao do Maranhao\n"
                           "2026-09-08  # Padroeira de Cidade Exemplo"),
    # A distribuição da equipe pelo gestor (desde 11/10/2026 em `settings`, e
    # não mais em `gestor_rotina.py`): a mesma forma da que o oficial ditou,
    # com a equipe fictícia dos testes.
    "gestor_distribuicao": (
        '[["RCPN", "elisa", "debora", 1],'
        ' ["RI", "carla", "beatriz", 0],'
        ' ["NOTAS", "carla", "beatriz", 0],'
        ' ["RCPJ_RTD", "carla", "beatriz", 0],'
        ' ["RI_QUALIFICACAO", "beatriz", "mario", 0],'
        ' ["NOTAS_QUALIFICACAO", "beatriz", "mario", 0],'
        ' ["RCPJ_RTD_QUALIFICACAO", "beatriz", "mario", 0],'
        ' ["PROTESTO", "elisa", "mario", 0],'
        ' ["GESTAO", "mario", null, 0],'
        ' ["TI", "alberto", "mario", 0]]'),
}
import database as _database  # noqa: E402

_database.DEFAULT_SETTINGS.update(SERVENTIA_DE_TESTE)

_SEED_NAME = "_cg_seed_schema.sqlite3"
_DB_NAME = "cartorio_gestao.sqlite3"
_TRAVA_SUITE = None
_ARVORE_INICIAL = None
_PROXIMA_CONFERENCIA = 0.0
_SESSAO_CONTROLADORA = None
_ARVORE_INVALIDADA = False


def _estado_da_suite():
    """Fonte do app mais os dois arquivos externos que os testes consultam."""
    from tools.pytest_guard import estado_da_arvore

    estado = estado_da_arvore(RAIZ)
    for rotulo, caminho in (
        ("../ATUALIZAR_SISTEMA.cmd", RAIZ.parent / "ATUALIZAR_SISTEMA.cmd"),
        ("../../CLAUDE.md", RAIZ.parent.parent / "CLAUDE.md"),
    ):
        try:
            stat = caminho.stat()
            estado[rotulo] = (stat.st_size, stat.st_mtime_ns)
        except OSError:
            estado[rotulo] = (-1, -1)
    return estado


def pytest_sessionstart(session) -> None:
    """Uma arvore, uma suite, uma versao durante toda a medicao.

    Os workers do xdist pertencem a execucao que ja adquiriu a trava no
    controlador. Eles so vigiam alteracoes da arvore.
    """
    global _TRAVA_SUITE, _ARVORE_INICIAL, _PROXIMA_CONFERENCIA
    global _SESSAO_CONTROLADORA, _ARVORE_INVALIDADA
    _ARVORE_INVALIDADA = False
    from tools.pytest_guard import TravaDaSuite

    if SEM_TRAVA:
        return
    if not hasattr(session.config, "workerinput"):
        _SESSAO_CONTROLADORA = session
        _TRAVA_SUITE = TravaDaSuite(RAIZ)
        try:
            _TRAVA_SUITE.adquirir()
        except RuntimeError as erro:
            raise pytest.UsageError(str(erro)) from erro
    _ARVORE_INICIAL = _estado_da_suite()
    # Uma varredura de metadados custa ~1 s nesta arvore. Fazê-la em cada
    # worker, antes de quase todo teste, multiplicava esse custo milhares de
    # vezes. O controlador recebe relatórios continuamente e confere sozinho,
    # a cada 15 s: mesma garantia, sem quatro varreduras concorrentes.
    _PROXIMA_CONFERENCIA = time.monotonic() + 15.0


def pytest_runtest_logreport(report) -> None:
    """O controlador para em ate ~15 s se a arvore mudar durante a suite."""
    global _PROXIMA_CONFERENCIA, _ARVORE_INVALIDADA
    # Workers nao adquirem a trava; so o controlador vigia a arvore.
    if _TRAVA_SUITE is None:
        return
    agora = time.monotonic()
    if agora < _PROXIMA_CONFERENCIA:
        return
    _PROXIMA_CONFERENCIA = agora + 15.0
    from tools.pytest_guard import diferencas

    mudaram = diferencas(_ARVORE_INICIAL, _estado_da_suite())
    if mudaram:
        _ARVORE_INVALIDADA = True
        amostra = ", ".join(mudaram[:5])
        if len(mudaram) > 5:
            amostra += f" e mais {len(mudaram) - 5}"
        # Nao levante pytest.exit dentro do hook de relatorio do xdist: isso
        # fecha os canais dos workers durante o teardown e pode esconder a
        # mensagem principal sob avisos "cannot send (already closed?)".
        # shouldstop deixa o controlador encerrar os workers ordenadamente e
        # preserva o diagnostico no resumo final.
        if _SESSAO_CONTROLADORA is not None:
            _SESSAO_CONTROLADORA.shouldstop = (
                "ARVORE ALTERADA DURANTE A SUITE: " + amostra
                + ". Resultado invalidado; aguarde as edicoes terminarem "
                "e rode novamente."
            )


def pytest_sessionfinish(session, exitstatus) -> None:
    global _TRAVA_SUITE, _SESSAO_CONTROLADORA, _ARVORE_INVALIDADA
    from tools.pytest_guard import codigo_de_saida

    if BACKEND_PG:
        for esquema in banco_pg.schemas_criados():
            try:
                banco_pg.devolver_schema(esquema)
            except Exception:  # noqa: BLE001 - limpeza não derruba o resultado
                pass
    session.exitstatus = codigo_de_saida(exitstatus, _ARVORE_INVALIDADA)
    if _TRAVA_SUITE is not None:
        _TRAVA_SUITE.liberar()
        _TRAVA_SUITE = None
    _SESSAO_CONTROLADORA = None
    _ARVORE_INVALIDADA = False


def _db_file(data_dir: Path) -> Path:
    return data_dir / _DB_NAME


def _seed_file(data_dir: Path) -> Path:
    return data_dir / _SEED_NAME


def _nomes_de_tabela(con, schema: str = "main") -> list[str]:
    return [
        r[0]
        for r in con.execute(
            f"SELECT name FROM {schema}.sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]


def _tabelas_com_linha(con, tables, schema: str = "main") -> list[str]:
    cheias = []
    for t in tables:
        if con.execute(f'SELECT 1 FROM {schema}."{t}" LIMIT 1').fetchone():
            cheias.append(t)
    return cheias


def _pg_cru():
    import psycopg

    return psycopg.connect(os.environ["CG_PG_DSN"], autocommit=True)


_FORA_DO_SEED = ("cg_meta", "cg_ddl", "cg_fk_pendentes")


def _pg_tabelas(c, esquema: str) -> list[str]:
    c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=%s "
              "AND table_type='BASE TABLE' ORDER BY table_name", (esquema,))
    return [r[0] for r in c.fetchall() if r[0] not in _FORA_DO_SEED]


def _pg_com_linha(c, esquema: str, tabelas: list[str]) -> list[str]:
    if not tabelas:
        return []
    partes = [f"(SELECT %s::text FROM \"{esquema}\".\"{t}\" LIMIT 1)" for t in tabelas]
    c.execute(" UNION ALL ".join(partes), tabelas)
    return [r[0] for r in c.fetchall()]


def _pg_semear(db_path: Path, seed_path: Path) -> list[str]:
    esquema = banco_pg.schema_do_caminho(db_path)
    semente = banco_pg.schema_do_caminho(seed_path)
    with _pg_cru() as pg, pg.cursor() as c:
        c.execute(f'DROP SCHEMA IF EXISTS "{semente}" CASCADE')
        c.execute(f'CREATE SCHEMA "{semente}"')
        cheias = _pg_com_linha(c, esquema, _pg_tabelas(c, esquema))
        for t in cheias:
            c.execute(f'CREATE TABLE "{semente}"."{t}" AS SELECT * FROM "{esquema}"."{t}"')
    banco_pg._SCHEMAS_CRIADOS.append(semente)
    return cheias


def _pg_restaurar(db_path: Path, seed_path: Path, seed_tables: list[str]) -> None:
    esquema = banco_pg.schema_do_caminho(db_path)
    semente = banco_pg.schema_do_caminho(seed_path)
    with _pg_cru() as pg, pg.cursor() as c:
        # conexão esquecida no meio de uma transação seguraria o TRUNCATE
        c.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE "
                  "application_name=%s AND state LIKE 'idle in transaction%%' "
                  "AND pid<>pg_backend_pid()", (esquema[:60],))
        sujas = _pg_com_linha(c, esquema, _pg_tabelas(c, esquema))
        alvo = sorted(set(sujas) | set(seed_tables))
        # DELETE e não TRUNCATE: o TRUNCATE troca os arquivos da tabela, e no
        # Windows arquivo novo custa caro
        c.execute("SET session_replication_role = replica")
        for t in alvo:
            c.execute(f'DELETE FROM "{esquema}"."{t}"')
        for t in seed_tables:
            c.execute(f'INSERT INTO "{esquema}"."{t}" SELECT * FROM "{semente}"."{t}"')
        # a numeração automática volta ao maior id (ou ao 1) em toda tabela
        # mexida — é o que o SQLite faz ao recolocar o sqlite_sequence do seed
        c.execute(
            "SELECT k.relname, a.attname FROM pg_attribute a JOIN pg_class k ON k.oid=a.attrelid "
            "JOIN pg_namespace n ON n.oid=k.relnamespace WHERE n.nspname=%s AND "
            "a.attidentity IN ('a','d') AND k.relname = ANY(%s)", (esquema, alvo))
        for t, coluna in c.fetchall():
            c.execute(
                f"SELECT setval(pg_get_serial_sequence(%s, %s), "
                f'COALESCE((SELECT MAX("{coluna}") FROM "{esquema}"."{t}"), 0) + 1, false)',
                (f'"{esquema}"."{t}"', coluna))
        c.execute("SET session_replication_role = origin")


def _checkpoint(db_path: Path) -> None:
    if BACKEND_PG:
        return
    con = sqlite3.connect(str(db_path), timeout=30)
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        con.close()
    for suffix in ("-wal", "-shm"):
        extra = Path(str(db_path) + suffix)
        if extra.exists():
            try:
                extra.unlink()
            except OSError:
                pass


def _limpar_acervo(data_dir: Path) -> None:
    """Remove arquivos gerados pelos testes; mantem a pasta arquivos/ e o DB/seed."""
    acervo = data_dir / "arquivos"
    if not acervo.is_dir():
        acervo.mkdir(parents=True, exist_ok=True)
    else:
        for filho in list(acervo.iterdir()):
            if filho.is_dir():
                shutil.rmtree(filho, ignore_errors=True)
            else:
                try:
                    filho.unlink()
                except OSError:
                    pass
    # Sidecars no DATA_DIR (credenciais, caches) — o restore SQL nao os apaga.
    manter = {_DB_NAME, _SEED_NAME, "arquivos"}
    manter |= {_DB_NAME + "-wal", _DB_NAME + "-shm", _DB_NAME + "-journal"}
    for filho in list(data_dir.iterdir()):
        if filho.name in manter:
            continue
        if filho.is_dir():
            shutil.rmtree(filho, ignore_errors=True)
        else:
            try:
                filho.unlink()
            except OSError:
                pass


def _restaurar_do_seed(db_path: Path, seed_path: Path, seed_tables: list[str]) -> None:
    """Isolamento barato: apaga so tabelas com dados e recoloca o seed.

    Preferido a substituir o arquivo: no Windows conexoes sqlite vazadas do
    teste anterior travam shutil.copy; ATTACH+DELETE/INSERT convive com isso.
    """
    if BACKEND_PG:
        return _pg_restaurar(db_path, seed_path, seed_tables)
    con = sqlite3.connect(str(db_path), timeout=30)
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("PRAGMA busy_timeout=30000")
        tables = _nomes_de_tabela(con)
        sujas = _tabelas_com_linha(con, tables)
        con.execute("ATTACH DATABASE ? AS cg_seed", (str(seed_path.resolve()),))
        con.execute("BEGIN IMMEDIATE")
        for t in sujas:
            con.execute(f'DELETE FROM "{t}"')
        try:
            con.execute("DELETE FROM sqlite_sequence")
        except sqlite3.OperationalError:
            pass
        for t in seed_tables:
            con.execute(f'INSERT INTO main."{t}" SELECT * FROM cg_seed."{t}"')
        try:
            con.execute("DELETE FROM main.sqlite_sequence")
            con.execute(
                "INSERT INTO main.sqlite_sequence SELECT * FROM cg_seed.sqlite_sequence"
            )
        except sqlite3.OperationalError:
            pass
        con.commit()
        con.execute("DETACH DATABASE cg_seed")
    except Exception:
        try:
            con.rollback()
        except sqlite3.Error:
            pass
        try:
            con.execute("DETACH DATABASE cg_seed")
        except sqlite3.Error:
            pass
        raise
    finally:
        con.close()


def cg_login(client, username: str, password: str):
    """Login via test_client com CSRF da tela /login."""
    html = client.get("/login").get_data(as_text=True)
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    if not achado:
        raise AssertionError("a tela /login nao trouxe csrf_token")
    return client.post(
        "/login",
        data={
            "username": username,
            "password": password,
            "csrf_token": achado.group(1),
        },
        follow_redirects=True,
    )


@pytest.fixture(scope="module")
def cg_data_dir(tmp_path_factory) -> Path:
    """DATA_DIR unico por modulo de teste (nunca producao)."""
    return tmp_path_factory.mktemp("cg_dados")


@pytest.fixture(scope="module")
def _cg_boot(cg_data_dir: Path) -> dict:
    """Sobe create_app 1x no modulo e grava seed schema-only."""
    from app import create_app

    app = create_app({"DATA_DIR": str(cg_data_dir)})
    db_path = _db_file(cg_data_dir)
    seed_path = _seed_file(cg_data_dir)
    if BACKEND_PG:
        seed_tables = _pg_semear(db_path, seed_path)
    else:
        _checkpoint(db_path)
        shutil.copy2(db_path, seed_path)
        con = sqlite3.connect(str(seed_path))
        try:
            seed_tables = _tabelas_com_linha(con, _nomes_de_tabela(con))
        finally:
            con.close()
    return {
        "app": app,
        "data_dir": cg_data_dir,
        "db_path": db_path,
        "seed_path": seed_path,
        "seed_tables": seed_tables,
        "db": app.extensions["db"],
    }


@pytest.fixture(scope="module")
def cg_app(_cg_boot) -> object:
    """Flask app compartilhado do modulo."""
    return _cg_boot["app"]


@pytest.fixture(scope="module")
def cg_db_path(_cg_boot) -> Path:
    return _cg_boot["db_path"]


@pytest.fixture
def cg_db(_cg_boot):
    """Database com dados restaurados ao seed (por teste). Reusa a instancia do modulo."""
    _restaurar_do_seed(
        _cg_boot["db_path"], _cg_boot["seed_path"], _cg_boot["seed_tables"]
    )
    _limpar_acervo(_cg_boot["data_dir"])
    return _cg_boot["db"]


@pytest.fixture
def cg_client(cg_app, cg_db):
    """test_client fresco; o DB ja foi resetado via dependencia cg_db."""
    return cg_app.test_client()


@pytest.fixture
def cg_casa(cg_app, cg_db, _cg_boot) -> dict:
    """Pacote no padrao dos testes legados: app + client + paths + Database.

    O client NAO vem logado -- chame cg_login ou faca o POST /login no teste.
    Aliases: cliente e c apontam para o mesmo test_client.
    """
    client = cg_app.test_client()
    return {
        "app": cg_app,
        "cliente": client,
        "c": client,
        "banco": _cg_boot["db_path"],
        "db": cg_db,
        "dados": _cg_boot["data_dir"],
        "acervo": _cg_boot["data_dir"] / "arquivos",
    }


@pytest.fixture
def cg_casa_logada(cg_casa):
    """cg_casa com admin padrao ja logado (mario / Senha#12345).

    Use quando o arquivo so precisa de um ADMIN logado e nao testa auth/login.
    NAO use em testes de login, CSRF anonimo, /setup ou troca de papel — esses
    precisam de client fresco sem sessao (cg_casa / cg_client).

    Escopo function: restore do seed + create_user + login a cada teste.
    O ganho e de boilerplate (e ~0,1-0,3 s vs repetir o POST), nao de schema.
    """
    SENHA = "Senha#12345"
    cg_casa["db"].create_user(
        "mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN"
    )
    c = cg_casa["c"]
    cg_login(c, "mario", SENHA)
    return cg_casa


@pytest.fixture(autouse=True)
def _cg_pg_apaga_schemas_do_teste():
    """No PostgreSQL, cada `Database(tmp_path)` cria um schema com centenas de
    tabelas; sem apagar, a suíte enche o disco. O que nasceu durante o teste
    morre com ele (os de módulo morrem no fim da sessão)."""
    if not BACKEND_PG:
        yield
        return
    antes = set(banco_pg.schemas_criados())
    yield
    for esquema in banco_pg.schemas_criados():
        if esquema not in antes:
            try:
                banco_pg.devolver_schema(esquema)
            except Exception:  # noqa: BLE001
                pass


def pytest_configure(config):
    # A marca existia só no pytest.ini da instalação (fora do GitHub).
    config.addinivalue_line("markers", "lento: teste demorado; o gate rápido usa -m 'not lento'")
