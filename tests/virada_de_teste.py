"""A virada num banco de FIXTURE, pelas ferramentas de verdade — lote LH10, 21/10/2026.

O roteiro da virada (`docs/ROTEIRO_DA_VIRADA.md`) roda três coisas que moram
fora do Python do sistema: `tools/migrar_para_postgres.py` (B3, a carga), e o
`psql` com `tools/ajuste_pos_migracao.sql` (B4) e com
`tools/ajuste_criado_por_matriculas.sql` (LX09). Os testes rodam as três do
mesmo jeito — o script em outro processo, o SQL pelo `psql` —, porque é assim
que elas vão rodar no servidor, e um `\\if` do psql ou um `sys.exit` da carga não
se provam chamando função.

O ARQUIVO SQLite tem a FORMA da produção só no que a virada mexe, e nenhum dado
de pessoa: os nomes são os fictícios da casa (`docs/AGENTES.md`), o documento é
da lista do anti-vazamento, e logins e teores são inventados. Ele traz o que o
ensaio com o banco real de 21/10 encontrou, em miniatura:
    - texto em coluna que o código declara INTEGER (`ri_matriculas.criado_por`
      com nome de exibição, `ri_atos.lavrado_por` com login,
      `nt_atos.filhos_maiores`, `nt_ato_partes.conjuge_tipo`) e chave de texto
      em `audit_logs.entity_id`;
    - inteiro em coluna que o código quer TEXT (`cx_depositos.criado_por`...);
    - nome de exibição que casa com um usuário, com nenhum e com dois;
    - a corrente de hash do RI (`ri_schema.hash_ato`);
    - `ri_cnib_decisoes` em cinco formas (`CNIB`): com o UNIQUE do código, sem
      ele, sem ele e com linhas repetidas, com a chave num índice único à parte,
      e com o UNIQUE mas com uma linha que só é repetida depois da carga (texto
      × bytes no SQLite).

Cada teste usa um schema só dele (`virada`), apagado no fim.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import banco_pg  # noqa: E402
from ri_schema import hash_ato  # noqa: E402

CARGA = RAIZ / "tools" / "migrar_para_postgres.py"
AJUSTE = RAIZ / "tools" / "ajuste_pos_migracao.sql"
LX09 = RAIZ / "tools" / "ajuste_criado_por_matriculas.sql"

UNIQUE_DO_CODIGO = "ri_cnib_decisoes_matricula_id_protocolo_cnib_pessoa_documen_key"

ESQUEMA_DA_PRODUCAO = """
CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
    full_name TEXT, role TEXT NOT NULL DEFAULT 'USER', active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE ri_matriculas (id INTEGER PRIMARY KEY, numero TEXT NOT NULL,
    criado_por INTEGER REFERENCES users(id), conferido_por INTEGER, atualizado_por TEXT);
CREATE TABLE ri_atos (id INTEGER PRIMARY KEY,
    matricula_id INTEGER NOT NULL REFERENCES ri_matriculas(id), tipo TEXT NOT NULL,
    numero INTEGER NOT NULL, data_ato TEXT, teor TEXT, hash_ato TEXT, hash_anterior TEXT,
    lavrado_por INTEGER REFERENCES users(id));
CREATE TABLE ri_ctp_itens (id INTEGER PRIMARY KEY, atualizado_por INTEGER);
CREATE TABLE nt_atos (id INTEGER PRIMARY KEY, filhos_maiores INTEGER);
CREATE TABLE nt_ato_partes (id INTEGER PRIMARY KEY, ato_id INTEGER REFERENCES nt_atos(id),
    conjuge_tipo INTEGER);
CREATE TABLE nt_autenticacoes (id INTEGER PRIMARY KEY, criado_por INTEGER);
CREATE TABLE nt_cartoes (id INTEGER PRIMARY KEY, criado_por INTEGER);
CREATE TABLE nt_reconhecimentos (id INTEGER PRIMARY KEY, criado_por INTEGER);
CREATE TABLE cx_depositos (id INTEGER PRIMARY KEY, criado_por INTEGER);
CREATE TABLE cx_recibos (id INTEGER PRIMARY KEY, cancelado_por INTEGER);
CREATE TABLE rg_encaminhamentos (id INTEGER PRIMARY KEY, criado_por INTEGER);
CREATE TABLE audit_logs (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, user_id INTEGER,
    action TEXT NOT NULL, entity TEXT, entity_id TEXT, details TEXT);
"""

# Os nomes de exibição guardados em `ri_matriculas.criado_por`: um casa com um
# usuário (o 2), um com nenhum e um com dois (os homônimos 4 e 5).
CASA_COM_UM = "Beatriz Exemplo de Souza"
NAO_CASA = "Mario Exemplo dos Santos"
CASA_COM_DOIS = "Carla Exemplo"
FILHOS_EM_TEXTO = "dois filhos maiores, conforme declaração"

DADOS = f"""
INSERT INTO users VALUES (1, 'admin', 'Administração de Exemplo', 'ADMIN', 1),
    (2, 'escrevente.um', '{CASA_COM_UM}', 'USER', 1),
    (3, 'oficial.exemplo', 'Oficial de Exemplo', 'MANAGER', 1),
    (4, 'carla.a', '{CASA_COM_DOIS}', 'USER', 1),
    (5, 'carla.b', '{CASA_COM_DOIS}', 'USER', 1);
INSERT INTO ri_matriculas VALUES (1, '1001', 1, 2, NULL),
    (2, '1002', '{CASA_COM_UM}', NULL, NULL), (3, '1003', '{CASA_COM_UM}', NULL, NULL),
    (4, '1004', '{CASA_COM_UM}', NULL, NULL), (5, '1005', '{NAO_CASA}', NULL, NULL),
    (6, '1006', '{NAO_CASA}', NULL, NULL), (7, '1007', '{CASA_COM_DOIS}', NULL, NULL),
    (8, '1008', NULL, NULL, NULL);
INSERT INTO ri_ctp_itens VALUES (1, 2);
INSERT INTO nt_atos VALUES (1, 2), (2, '{FILHOS_EM_TEXTO}');
INSERT INTO nt_ato_partes VALUES (1, 1, 1), (2, 1, 'CONJUGE');
INSERT INTO nt_autenticacoes VALUES (1, 2);
INSERT INTO nt_cartoes VALUES (1, 2);
INSERT INTO nt_reconhecimentos VALUES (1, NULL);
INSERT INTO cx_depositos VALUES (1, 2);
INSERT INTO cx_recibos VALUES (1, 3);
INSERT INTO rg_encaminhamentos VALUES (1, 3);
INSERT INTO audit_logs VALUES (1, '2026-10-01T10:00:00', 1, 'LOGIN', 'users', '1', NULL),
    (2, '2026-10-01T10:05:00', 1, 'ELEMENTO_AJUSTADO', 'mo_elementos', 'RI/ato/parte', NULL),
    (3, '2026-10-01T10:06:00', 1, 'SETTINGS', 'settings', '42', NULL);
"""

# O que o modo guardar do ajuste tem de guardar: (tabela, coluna) -> {id: valor}
GUARDAVEIS = {
    ("ri_matriculas", "criado_por"): {2: CASA_COM_UM, 3: CASA_COM_UM, 4: CASA_COM_UM,
                                      5: NAO_CASA, 6: NAO_CASA, 7: CASA_COM_DOIS},
    ("ri_atos", "lavrado_por"): {2: "oficial.exemplo"},
    ("nt_atos", "filhos_maiores"): {2: FILHOS_EM_TEXTO},
    ("nt_ato_partes", "conjuge_tipo"): {2: "CONJUGE"},
    ("audit_logs", "entity_id"): {2: "RI/ato/parte"},
}

# Os atos do RI: (id, matrícula, número da matrícula, tipo, número, data, teor, lavrado_por)
ATOS = [
    (1, 1, "1001", "R", 1, "2026-01-10", "Teor de exemplo do registro 1.", 3),
    (2, 1, "1001", "AV", 2, "2026-02-10", "Teor de exemplo da averbação 2.", "oficial.exemplo"),
    (3, 2, "1002", "R", 1, "2026-03-10", "Teor de exemplo do registro 1 da 1002.", None),
]

_CNIB_COLUNAS = """id INTEGER PRIMARY KEY,
    matricula_id INTEGER NOT NULL REFERENCES ri_matriculas(id), protocolo_cnib TEXT NOT NULL,
    pessoa_nome TEXT, pessoa_documento TEXT, criterio TEXT, decisao TEXT NOT NULL,
    motivo TEXT, ato_id INTEGER, decidido_por TEXT, decidido_em TEXT NOT NULL"""
_CNIB_DUAS = """
INSERT INTO ri_cnib_decisoes VALUES
    (1, 1, 'CNIB-0001', 'PEDRO EXEMPLO DOS SANTOS', '00000000191', 'documento', 'NAO_E_A_PESSOA',
     'Documento conferido não é o da parte.', NULL, 'admin', '2026-09-01T10:00:00'),
    (2, 2, 'CNIB-0002', 'CARLA EXEMPLO', '', 'nome', 'AVERBADA',
     NULL, NULL, 'admin', '2026-09-02T10:00:00');
"""
CNIB = {
    # a forma de hoje: o UNIQUE do código já estava no CREATE TABLE da produção
    "unico": f"CREATE TABLE ri_cnib_decisoes ({_CNIB_COLUNAS},\n"
             "    UNIQUE(matricula_id, protocolo_cnib, pessoa_documento, pessoa_nome));\n"
             + _CNIB_DUAS,
    # a tabela de antes do UNIQUE, sem repetição
    "sem_unico": f"CREATE TABLE ri_cnib_decisoes ({_CNIB_COLUNAS});\n" + _CNIB_DUAS,
    # sem o UNIQUE e com a decisão 1 três vezes (3 e 4 repetem); 5 e 6 têm o
    # documento NULL, e NULL não repete nada (nem no SQLite, nem no PostgreSQL)
    "repetida": f"CREATE TABLE ri_cnib_decisoes ({_CNIB_COLUNAS});\n" + _CNIB_DUAS + """
INSERT INTO ri_cnib_decisoes VALUES
    (3, 1, 'CNIB-0001', 'PEDRO EXEMPLO DOS SANTOS', '00000000191', 'documento', 'AVERBADA',
     NULL, NULL, 'oficial.exemplo', '2026-09-03T10:00:00'),
    (4, 1, 'CNIB-0001', 'PEDRO EXEMPLO DOS SANTOS', '00000000191', 'documento', 'NAO_E_A_PESSOA',
     'Segunda conferência do mesmo documento.', NULL, 'admin', '2026-09-04T10:00:00'),
    (5, 2, 'CNIB-0003', 'MARIO EXEMPLO DOS SANTOS', NULL, 'nome', 'NAO_E_A_PESSOA',
     'Nome igual, pessoa diferente.', NULL, 'admin', '2026-09-05T10:00:00'),
    (6, 2, 'CNIB-0003', 'MARIO EXEMPLO DOS SANTOS', NULL, 'nome', 'NAO_E_A_PESSOA',
     'Nome igual, pessoa diferente.', NULL, 'admin', '2026-09-06T10:00:00');
""",
    # a chave única num CREATE UNIQUE INDEX à parte, e não no CREATE TABLE: a
    # carga faz índice único com o nome do SQLite, sem restrição
    "indice_unico": f"CREATE TABLE ri_cnib_decisoes ({_CNIB_COLUNAS});\n"
                    "CREATE UNIQUE INDEX ux_cnib_decisao ON ri_cnib_decisoes"
                    "(matricula_id, protocolo_cnib, pessoa_documento, pessoa_nome);\n" + _CNIB_DUAS,
    # com o UNIQUE, e a decisão 3 com o nome em BYTES: para o SQLite, bytes e
    # texto nunca são iguais, e a linha entra; a carga grava os bytes como o
    # texto que eles são, a 3 vira repetição da 1 e o UNIQUE não entra — a
    # carga põe um índice comum de mesmo nome no lugar
    "bytes": f"CREATE TABLE ri_cnib_decisoes ({_CNIB_COLUNAS},\n"
             "    UNIQUE(matricula_id, protocolo_cnib, pessoa_documento, pessoa_nome));\n"
             + _CNIB_DUAS + """
INSERT INTO ri_cnib_decisoes VALUES
    (3, 1, 'CNIB-0001', CAST('PEDRO EXEMPLO DOS SANTOS' AS BLOB), '00000000191', 'documento', 'AVERBADA',
     NULL, NULL, 'oficial.exemplo', '2026-09-03T10:00:00');
""",
}

# Para a fixture «limpa»: os valores de texto que o ajuste no modo padrão recusa
# viram NULL, e sobram só as diferenças que convertem sozinhas.
_LIMPAR = """
UPDATE ri_matriculas SET criado_por = NULL WHERE typeof(criado_por) = 'text';
UPDATE ri_atos SET lavrado_por = NULL WHERE typeof(lavrado_por) = 'text';
UPDATE nt_atos SET filhos_maiores = NULL WHERE typeof(filhos_maiores) = 'text';
UPDATE nt_ato_partes SET conjuge_tipo = NULL WHERE typeof(conjuge_tipo) = 'text';
UPDATE audit_logs SET entity_id = NULL WHERE entity_id GLOB '*[^0-9]*';
"""


TABELAS = tuple(re.findall(r"CREATE TABLE (\w+)", ESQUEMA_DA_PRODUCAO)) + ("ri_cnib_decisoes",)


def montar_sqlite(pasta: Path, cnib: str = "unico", *, limpo: bool = False) -> Path:
    """A cópia da produção em miniatura (ver o cabeçalho). `limpo` tira os
    valores de texto que não convertem: o ajuste no modo padrão passa."""
    arquivo = pasta / "copia_da_producao.sqlite3"
    sq = banco_pg._CONNECT_ORIGINAL(str(arquivo))
    try:
        sq.executescript(ESQUEMA_DA_PRODUCAO + DADOS)
        anterior: dict[int, str] = {}
        for id_, mid, numero_m, tipo, numero, data, teor, lavrado in ATOS:
            h = hash_ato(numero_m, tipo, numero, data, teor, anterior.get(mid))
            sq.execute("INSERT INTO ri_atos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (id_, mid, tipo, numero, data, teor, h, anterior.get(mid), lavrado))
            anterior[mid] = h
        sq.executescript(CNIB[cnib])
        if limpo:
            sq.executescript(_LIMPAR)
        sq.commit()
    finally:
        sq.close()
    return arquivo


def ler_sqlite(arquivo: Path, comando: str) -> list[tuple]:
    sq = banco_pg._CONNECT_ORIGINAL(str(arquivo))
    try:
        return sq.execute(comando).fetchall()
    finally:
        sq.close()


def _rodar(comando: list[str]) -> subprocess.CompletedProcess:
    feito = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=600, cwd=str(RAIZ),
                           env={**os.environ, "PGCLIENTENCODING": "UTF8"})
    feito.saida = (feito.stdout or "") + (feito.stderr or "")
    return feito


def carregar(arquivo: Path, schema: str, *extra: str) -> subprocess.CompletedProcess:
    """`python tools/migrar_para_postgres.py`, como o passo B3 a roda. O
    relatório vai para `relatorio_carga.md`, ao lado do arquivo."""
    return _rodar([sys.executable, str(CARGA), "--sqlite", str(arquivo),
                   "--dsn", banco_pg.dsn(), "--schema", schema,
                   "--relatorio", str(arquivo.with_name("relatorio_carga.md")), *extra])


def psql() -> str | None:
    """O psql da mesma pasta do pg_dump (`CG_PG_BIN`), ou o do PATH."""
    nome = "psql.exe" if os.name == "nt" else "psql"
    pasta = (os.environ.get("CG_PG_BIN") or "").strip()
    if pasta and (Path(pasta) / nome).exists():
        return str(Path(pasta) / nome)
    return shutil.which(nome)


def rodar_sql(script: Path, schema: str, **variaveis: str) -> subprocess.CompletedProcess:
    """`psql -X -q -v schema=... -f script`, como o roteiro manda rodar."""
    exe = psql()
    if exe is None:
        pytest.skip("psql não encontrado (CG_PG_BIN ou PATH): o ajuste roda pelo psql")
    comando = [exe, banco_pg.dsn(), "-X", "-q", "-v", f"schema={schema}"]
    for nome, valor in variaveis.items():
        comando += ["-v", f"{nome}={valor}"]
    return _rodar(comando + ["-f", str(script)])


def sql(schema: str, comando: str, parametros: tuple = ()) -> list[dict]:
    """Um comando no schema da virada, fora da ponte (o schema não é dela)."""
    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(banco_pg.dsn(), autocommit=True) as pg:
        pg.execute(f'SET search_path TO "{schema}", public')
        with pg.cursor(row_factory=dict_row) as c:
            c.execute(comando, parametros)
            return c.fetchall() if c.description else []


def tipo_da_coluna(schema: str, tabela: str, coluna: str) -> str | None:
    linhas = sql(schema, "SELECT format_type(a.atttypid, a.atttypmod) AS tipo FROM pg_attribute a "
                         "WHERE a.attrelid = to_regclass(%s) AND a.attname = %s "
                         "AND NOT a.attisdropped", (tabela, coluna))
    return linhas[0]["tipo"] if linhas else None


def tem_tabela(schema: str, tabela: str) -> bool:
    return sql(schema, "SELECT to_regclass(%s) IS NOT NULL AS tem", (tabela,))[0]["tem"]


def guardados(schema: str) -> dict:
    """`cg_ajuste_guardados` como {(tabela, coluna): {linha_id: valor_original}}."""
    if not tem_tabela(schema, "cg_ajuste_guardados"):
        return {}
    saida: dict = {}
    for r in sql(schema, "SELECT tabela, coluna, linha_id, valor_original FROM cg_ajuste_guardados "
                         "ORDER BY tabela, coluna, linha_id"):
        saida.setdefault((r["tabela"], r["coluna"]), {})[r["linha_id"]] = r["valor_original"]
    return saida


def restricoes(schema: str, tabela: str) -> dict:
    """{nome: definição} das restrições da tabela."""
    return {r["conname"]: r["def"] for r in sql(
        schema, "SELECT conname, pg_get_constraintdef(oid) AS def FROM pg_constraint "
                "WHERE conrelid = to_regclass(%s) ORDER BY conname", (tabela,))}


def indices(schema: str, tabela: str) -> dict:
    """{nome: (único?, definição)} dos índices da tabela."""
    return {r["nome"]: (r["unico"], r["def"]) for r in sql(
        schema, "SELECT c.relname AS nome, i.indisunique AS unico, "
                "pg_get_indexdef(i.indexrelid) AS def FROM pg_index i "
                "JOIN pg_class c ON c.oid = i.indexrelid WHERE i.indrelid = to_regclass(%s) "
                "ORDER BY c.relname", (tabela,))}


@pytest.fixture
def virada(tmp_path):
    """Um schema só desta virada, com o caminho que o aponta (para a
    conferência da carga), apagado no fim. A ponte abre uma conexão antes:
    é ela que põe em `public` a collation `cg_nocase` e as funções, que o
    ajuste espera achar prontas."""
    conexao_de_teste().close()
    caminho = tmp_path / "virada.sqlite3"
    schema = banco_pg.schema_do_caminho(caminho)
    banco_pg.descartar_schema(schema)
    yield SimpleNamespace(pasta=tmp_path, caminho=caminho, schema=schema)
    banco_pg.descartar_schema(schema)


def ate_o_ajuste(v, cnib: str = "unico", *, limpo: bool = False, **variaveis: str):
    """A carga (exigida: saída 0) e o ajuste com as variáveis dadas. Devolve
    (arquivo SQLite, resultado do psql)."""
    arquivo = montar_sqlite(v.pasta, cnib, limpo=limpo)
    feito = carregar(arquivo, v.schema, "--recriar")
    assert feito.returncode == 0, feito.saida[-4000:]
    return arquivo, rodar_sql(AJUSTE, v.schema, **variaveis)
