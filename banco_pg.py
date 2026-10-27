"""A ponte do sistema com o PostgreSQL — uma conexão que se comporta como
`sqlite3.Connection`.

POR QUE ASSIM — 15/10/2026, ordem do oficial: migrar o sistema para PostgreSQL.
O código tem ~3 mil chamadas SQL em 268 arquivos, todas escritas para o
`sqlite3`. Reescrevê-las uma a uma seria meses de trabalho e mil chances de
errar uma. Esta camada faz o caminho inverso: **o código continua falando
«sqlite3»**, e ela traduz para o PostgreSQL — parâmetros, linhas, número do
registro novo, `INSERT OR IGNORE`, `PRAGMA`, `sqlite_master`, transações e as
mensagens de erro que o código lê. Quem conserta à mão é só o que ela não
cobre (ver `MIGRACAO_PG/inventario.md`).

COMO SE LIGA: variável `CG_PG_DSN` (ex.: ``host=127.0.0.1 port=5433 user=cg
dbname=cartorio``). Sem ela, `conectar()` devolve um `sqlite3.connect` comum e
NADA muda. Com ela, cada arquivo de banco vira um *schema* (o nome sai do
caminho — `schema_do_caminho`), e é isso que mantém cada teste isolado no seu
`tmp_path`. A produção fixa o schema com `CG_PG_SCHEMA`.

O QUE ELA NÃO TENTA: adivinhar semântica. Onde o SQLite e o PostgreSQL
divergem de um jeito que o texto do SQL não revela (divisão inteira, GROUP BY
frouxo, comparação de tipos misturados), o erro sobe com a mensagem do
PostgreSQL — e o conserto é no módulo, à vista.
"""
from __future__ import annotations

import datetime as _dt
import decimal
import hashlib
import os
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:  # o sistema roda sem o driver enquanto o PostgreSQL não estiver ligado
    import psycopg
    from psycopg import errors as _pgerr
except ImportError:  # pragma: no cover
    psycopg = None
    _pgerr = None

# ----------------------------------------------------------------- a escolha

def dsn() -> str:
    return (os.environ.get("CG_PG_DSN") or "").strip()


def ativo() -> bool:
    """O sistema está ligado ao PostgreSQL? Só lê a variável."""
    return bool(dsn())


def _caminho_e_modo(db_path: Any) -> tuple[str, bool]:
    """O caminho do arquivo e se é só-leitura, aceitando também o URI do
    sqlite3 (`file:C:/x.sqlite3?mode=ro`, `file:///C:/x.sqlite3`). Sem isto o
    mesmo banco aberto por URI caía noutro schema, vazio (achado do lote L7)."""
    texto = str(db_path)
    so_leitura = False
    if texto.startswith("file:"):
        from urllib.parse import parse_qs, unquote, urlsplit
        partes = urlsplit(texto)
        consulta = parse_qs(partes.query)
        so_leitura = consulta.get("mode", [""])[0] == "ro" or consulta.get("immutable", [""])[0] == "1"
        caminho = unquote(partes.path or texto[5:].split("?", 1)[0])
        if partes.netloc and partes.netloc not in ("", "localhost"):
            caminho = partes.netloc + caminho
        if len(caminho) > 2 and caminho[0] == "/" and caminho[2] == ":":
            caminho = caminho[1:]          # /C:/pasta → C:/pasta
        texto = caminho
    return texto, so_leitura


def _chave(db_path: Any) -> str:
    texto, _ = _caminho_e_modo(db_path)
    try:
        return str(Path(texto).resolve()).lower()
    except (OSError, ValueError, TypeError):
        return texto.lower()


def schema_do_caminho(db_path: Any) -> str:
    """O schema daquele arquivo de banco. `CG_PG_SCHEMA` ganha de tudo."""
    fixo = (os.environ.get("CG_PG_SCHEMA") or "").strip()
    if fixo:
        return fixo
    return "cg_" + hashlib.sha1(_chave(db_path).encode("utf-8")).hexdigest()[:12]


_CONNECT_ORIGINAL = sqlite3.connect
_BANCOS_DA_CASA: set[str] = set()
NOME_DO_BANCO_PRINCIPAL = "cartorio_gestao.sqlite3"


def registrar_banco(db_path: Any) -> None:
    """`Database(db_path)` avisa aqui que aquele caminho é o banco da casa —
    é o que faz um `sqlite3.connect(caminho)` escrito à mão noutro módulo
    também cair no PostgreSQL (ver `instalar_desvio`)."""
    _BANCOS_DA_CASA.add(_chave(db_path))


def e_banco_da_casa(db_path: Any) -> bool:
    if db_path in (":memory:", "") or db_path is None:
        return False
    chave = _chave(db_path)
    return chave in _BANCOS_DA_CASA or chave.endswith(NOME_DO_BANCO_PRINCIPAL)


def conectar(db_path: Any, *, fechar_no_with: bool = False,
             linhas_com_nome: bool = False, **kw):
    """A porta única: SQLite como sempre, ou a conexão do PostgreSQL.

    `fechar_no_with` reproduz o `ClosingConnection` de `database.py` (o `with`
    fecha a conexão além de confirmar). O `sqlite3.connect` puro não fecha.
    `linhas_com_nome` é o `row_factory = sqlite3.Row` de `database.connect`
    (lote L072): as linhas saem com nome (`row["coluna"]`) desde a abertura.
    """
    if not ativo():
        con = _CONNECT_ORIGINAL(db_path, **kw)
        if linhas_com_nome:
            con.row_factory = sqlite3.Row
        return con
    # A MESMA RÉGUA DO DESVIO: só o banco da casa vai ao PostgreSQL. O L7
    # trocou 48 `sqlite3.connect` de tools/ por esta porta (15/10, 22h), e
    # sem isto o acervo do E-Ofício ou uma cópia aberta por ela virariam um
    # schema vazio no PostgreSQL, calados.
    if not e_banco_da_casa(db_path):
        con = _sqlite_comum(db_path, **kw)
        if linhas_com_nome:
            con.row_factory = sqlite3.Row
        return con
    return Conexao(db_path, fechar_no_with=fechar_no_with,
                   linhas_com_nome=linhas_com_nome)


def conectar_sqlite(caminho: Any, *, so_leitura: bool = True, **kw) -> sqlite3.Connection:
    """Um arquivo SQLite DE VERDADE, sem passar pelo desvio — lote LH09, 21/10/2026.

    É a porta do acervo do E-Ofício (`acervo_eoficio.sqlite3`, 229 tabelas
    `tb*`, estático), que NÃO vai para o PostgreSQL. O desvio do
    `sqlite3.connect` e o `conectar` decidem pelo NOME do arquivo
    (`e_banco_da_casa`): um acervo enviado com o nome do banco da casa, ou um
    caminho registrado por engano, cairia no PostgreSQL — num schema vazio, ou
    no próprio banco da casa. Aqui o nome não decide nada.

    `so_leitura` (o padrão) abre com `mode=ro`: quem só lê não grava, e o
    arquivo que falta não nasce vazio. Só quem MONTA o acervo (a carga do
    E-Ofício, `acervo_eoficio.carregar`, e a atualização ao vivo do Protesto,
    `acervo_eo_vivo`) abre para escrever."""
    texto, _ = _caminho_e_modo(caminho)
    if so_leitura:
        return _CONNECT_ORIGINAL(Path(texto).resolve().as_uri() + "?mode=ro", uri=True, **kw)
    return _CONNECT_ORIGINAL(texto, **kw)


class _ConexaoSqlite(sqlite3.Connection):
    """A conexão SQLite de sempre (acervo, cópias, bancos soltos) enquanto o
    PostgreSQL está ligado. Só muda o `.backup()`: o destino pode ter caído no
    PostgreSQL pelo nome (`cartorio_gestao.sqlite3`) e o `.backup()` do
    sqlite3 recusa o que não é `sqlite3.Connection` — era o TypeError de
    test_backup (P04)."""

    def backup(self, target, *args, **kw):
        if isinstance(target, Conexao):
            return target._receber_de_sqlite(self, *args, **kw)
        return super().backup(target, *args, **kw)


def _sqlite_comum(database, *args, **kw):
    # `factory` posicional é o 6º argumento do sqlite3.connect
    if "factory" not in kw and len(args) < 5:
        kw["factory"] = _ConexaoSqlite
    return _CONNECT_ORIGINAL(database, *args, **kw)


def _connect_desviado(database, *args, **kw):
    """Substitui `sqlite3.connect` quando o PostgreSQL está ligado: o banco da
    casa vai para o PostgreSQL; qualquer outro arquivo (o acervo do E-Ofício,
    cópias, bancos de teste soltos) continua no SQLite, como sempre.

    POR QUE DESVIAR EM VEZ DE TROCAR AS CHAMADAS: há ~150 `sqlite3.connect`
    espalhados (módulos, ferramentas e testes). Trocar um por um é o trabalho
    certo a médio prazo e o inventário os lista; até lá, esta porta garante que
    nenhum deles abra um arquivo SQLite vazio achando que é o banco da casa."""
    if ativo() and e_banco_da_casa(database):
        fabrica = kw.get("factory")
        fecha = bool(fabrica is not None and fabrica is not sqlite3.Connection
                     and getattr(fabrica, "__name__", "") == "ClosingConnection")
        return Conexao(database, fechar_no_with=fecha)
    if ativo():
        return _sqlite_comum(database, *args, **kw)
    return _CONNECT_ORIGINAL(database, *args, **kw)


def instalar_desvio() -> None:
    if sqlite3.connect is not _connect_desviado:
        sqlite3.connect = _connect_desviado


# ------------------------------------------------------------- os erros
# SUBCLASSES DAS DO sqlite3: o código apanha `sqlite3.IntegrityError` em
# dezenas de lugares, e assim continua apanhando.

class IntegrityError(sqlite3.IntegrityError):
    pass


class OperationalError(sqlite3.OperationalError):
    pass


class ProgrammingError(sqlite3.ProgrammingError):
    pass


class DatabaseError(sqlite3.DatabaseError):
    pass


_RE_CHAVE = re.compile(r"Key \((?P<cols>[^)]*)\)=")
_RE_COLUNA = re.compile(r'column "(?P<col>[^"]+)"')
_RE_RELACAO = re.compile(r'relation "(?P<rel>[^"]+)"')


def _traduzir_erro(erro: BaseException) -> BaseException:
    """Exceção do psycopg → a do sqlite3, com a frase que o código lê."""
    if psycopg is None or not isinstance(erro, psycopg.Error):
        return erro
    texto = str(erro).strip()
    diag = getattr(erro, "diag", None)
    tabela = getattr(diag, "table_name", None) or ""
    detalhe = getattr(diag, "message_detail", None) or ""
    if isinstance(erro, _pgerr.UniqueViolation):
        m = _RE_CHAVE.search(detalhe)
        cols = [c.strip().strip('"') for c in (m.group("cols").split(",") if m else [])]
        alvo = ", ".join(f"{tabela}.{c}" for c in cols) if cols else tabela
        return IntegrityError(f"UNIQUE constraint failed: {alvo}")
    if isinstance(erro, _pgerr.NotNullViolation):
        col = getattr(diag, "column_name", None) or ""
        return IntegrityError(f"NOT NULL constraint failed: {tabela}.{col}")
    if isinstance(erro, _pgerr.ForeignKeyViolation):
        return IntegrityError("FOREIGN KEY constraint failed")
    if isinstance(erro, _pgerr.CheckViolation):
        nome = getattr(diag, "constraint_name", None) or ""
        return IntegrityError(f"CHECK constraint failed: {nome}")
    if isinstance(erro, _pgerr.IntegrityError):
        return IntegrityError(texto)
    if isinstance(erro, _pgerr.UndefinedTable):
        m = _RE_RELACAO.search(texto)
        return OperationalError(f"no such table: {m.group('rel') if m else texto}")
    if isinstance(erro, _pgerr.UndefinedColumn):
        m = _RE_COLUNA.search(texto)
        return OperationalError(f"no such column: {m.group('col') if m else texto}")
    if isinstance(erro, _pgerr.DuplicateColumn):
        m = _RE_COLUNA.search(texto)
        return OperationalError(f"duplicate column name: {m.group('col') if m else texto}")
    if isinstance(erro, _pgerr.DuplicateTable):
        m = _RE_RELACAO.search(texto)
        return OperationalError(f"table {m.group('rel') if m else ''} already exists")
    if isinstance(erro, (_pgerr.LockNotAvailable, _pgerr.DeadlockDetected,
                         _pgerr.QueryCanceled)):
        return OperationalError("database is locked")
    if isinstance(erro, _pgerr.ReadOnlySqlTransaction):
        return OperationalError("attempt to write a readonly database")
    if isinstance(erro, _pgerr.SyntaxError):
        return OperationalError(f"syntax error: {texto}")
    if isinstance(erro, _pgerr.UndefinedFunction):
        return OperationalError(f"no such function: {texto}")
    if isinstance(erro, (psycopg.OperationalError, _pgerr.DataError,
                         psycopg.ProgrammingError)):
        return OperationalError(texto)
    return DatabaseError(texto)


# ------------------------------------------------------------- as linhas

class Linha:
    """Comporta-se como `sqlite3.Row`: índice inteiro e por nome (sem caixa),
    `keys()`, `len`, iteração pelos valores e igualdade."""

    __slots__ = ("_v", "_n", "_i")

    def __init__(self, nomes: Sequence[str], valores: Sequence[Any],
                 indice: dict[str, int] | None = None):
        self._v = tuple(valores)
        self._n = tuple(nomes)
        self._i = indice if indice is not None else {
            n.lower(): k for k, n in reversed(list(enumerate(nomes)))}

    def keys(self) -> list[str]:
        return list(self._n)

    def __getitem__(self, chave):
        if isinstance(chave, (int, slice)):
            return self._v[chave]
        try:
            return self._v[self._i[str(chave).lower()]]
        except KeyError:
            raise IndexError("No item with that key") from None

    def __len__(self) -> int:
        return len(self._v)

    def __iter__(self):
        return iter(self._v)

    def __eq__(self, outra) -> bool:
        if isinstance(outra, Linha):
            return self._n == outra._n and self._v == outra._v
        if isinstance(outra, sqlite3.Row):
            return list(self._v) == list(outra) and list(self._n) == outra.keys()
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self._n, self._v))

    def __repr__(self) -> str:
        return f"<Linha {dict(zip(self._n, self._v))!r}>"


def _valor_do_banco(v: Any) -> Any:
    """O que o sqlite3 devolveria: Decimal vira int/float; memoryview, bytes;
    booleano vira 0/1 — o SQLite nunca devolve bool, e `{{ f }}` sairia
    «True» na tela e no JSON (achado do L2, 15/10 23h40)."""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, decimal.Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, memoryview):
        return bytes(v)
    return v


def _valor_para_o_banco(v: Any) -> Any:
    """Parâmetro → literal sem tipo. Número vira texto de propósito: o
    psycopg manda `str` como tipo desconhecido, e o PostgreSQL o converte
    pelo tipo da coluna — `'11'` compara com inteiro, como no SQLite."""
    if v is None or isinstance(v, (bytes, bytearray, memoryview)):
        return bytes(v) if isinstance(v, (bytearray, memoryview)) else v
    if isinstance(v, bool):
        return str(int(v))
    if isinstance(v, (int, float, decimal.Decimal)):
        return repr(v) if isinstance(v, float) else str(v)
    if isinstance(v, _dt.datetime):
        return v.isoformat(" ")
    if isinstance(v, _dt.date):
        return v.isoformat()
    return v


# --------------------------------------------------------- o tradutor de SQL

_PALAVRAS_DE_ESCRITA = ("INSERT", "UPDATE", "DELETE", "REPLACE")
_TIPO_DE_SQLITE = {
    "integer": "INTEGER", "bigint": "INTEGER", "smallint": "INTEGER",
    "text": "TEXT", "character varying": "TEXT", "character": "TEXT",
    "double precision": "REAL", "real": "REAL", "numeric": "NUMERIC",
    "bytea": "BLOB", "boolean": "INTEGER",
}


def _varrer(sql: str):
    """Percorre o SQL devolvendo (trecho, eh_codigo) — separa o que está em
    aspas e comentários do código de verdade, para as trocas não tocarem
    em literais."""
    i, n, ini = 0, len(sql), 0
    while i < n:
        c = sql[i]
        if c in ("'", '"', "`", "["):
            fecha = {"'": "'", '"': '"', "`": "`", "[": "]"}[c]
            if i > ini:
                yield sql[ini:i], True
            j = i + 1
            while j < n:
                if sql[j] == fecha:
                    if fecha in ("'", '"') and j + 1 < n and sql[j + 1] == fecha:
                        j += 2
                        continue
                    break
                j += 1
            yield sql[i:j + 1], False
            i = ini = j + 1
            continue
        if c == "-" and sql.startswith("--", i):
            if i > ini:
                yield sql[ini:i], True
            j = sql.find("\n", i)
            j = n if j < 0 else j
            yield sql[i:j], False
            i = ini = j
            continue
        if c == "/" and sql.startswith("/*", i):
            if i > ini:
                yield sql[ini:i], True
            j = sql.find("*/", i + 2)
            j = n if j < 0 else j + 2
            yield sql[i:j], False
            i = ini = j
            continue
        i += 1
    if ini < n:
        yield sql[ini:], True


def _sem_comentario_na_frente(sql: str) -> str:
    """Tira os comentários e brancos do começo — o `executescript` traz o
    comando com o comentário que o explica colado à frente, e a decisão de que
    comando é (CREATE TABLE, PRAGMA…) olha a primeira palavra."""
    texto = sql.strip()
    while True:
        if texto.startswith("--"):
            fim = texto.find("\n")
            texto = "" if fim < 0 else texto[fim + 1:].lstrip()
        elif texto.startswith("/*"):
            fim = texto.find("*/")
            texto = "" if fim < 0 else texto[fim + 2:].lstrip()
        else:
            return texto


def dividir_comandos(script: str) -> list[str]:
    """Separa um `executescript` em comandos (o `;` fora de aspas)."""
    comandos, atual = [], []
    for trecho, codigo in _varrer(script):
        if not codigo:
            atual.append(trecho)
            continue
        partes = trecho.split(";")
        for k, p in enumerate(partes):
            atual.append(p)
            if k < len(partes) - 1:
                cmd = "".join(atual).strip()
                if cmd:
                    comandos.append(cmd)
                atual = []
    resto = "".join(atual).strip()
    if resto and not all(not c for _, c in _varrer(resto) if _.strip()):
        comandos.append(resto)
    elif resto and any(c and t.strip() for t, c in _varrer(resto)):
        comandos.append(resto)
    return comandos


_RE_TROCAS_DE_CODIGO = [
    (re.compile(r"\bINSERT\s+OR\s+(?:ABORT|FAIL|ROLLBACK)\s+INTO\b", re.I), "INSERT INTO"),
    (re.compile(r"\bLIMIT\s+-1\b", re.I), "LIMIT ALL"),
    # `date(x)` com um argumento vira CONVERSÃO para o tipo date do
    # PostgreSQL, e `time(` nem é chamada de função na gramática dele: as duas
    # vão para os nomes próprios da casa (banco_pg_funcoes.sql).
    (re.compile(r"(?<![\w.\"])date\s*\(", re.I), "cg_date("),
    (re.compile(r"(?<![\w.\"])time\s*\(", re.I), "cg_time("),
    (re.compile(r"\bCURRENT_TIMESTAMP\b", re.I), "cg_agora_texto()"),
    (re.compile(r"\bCURRENT_DATE\b", re.I), "cg_hoje_texto()"),
    (re.compile(r"\bCURRENT_TIME\b", re.I), "cg_hora_texto()"),
    (re.compile(r"(?<![\w.])(NOT\s+)?LIKE\b", re.I), lambda m: (m.group(1) or "") + "ILIKE"),
    # NOCASE vira uma comparação sem caixa do próprio PostgreSQL (ICU, não
    # determinística): `username = 'MARIO'` acha 'mario', e o UNIQUE também.
    (re.compile(r"\bCOLLATE\s+NOCASE\b", re.I), "COLLATE public.cg_nocase"),
    (re.compile(r"\bCOLLATE\s+BINARY\b", re.I), 'COLLATE "C"'),
    (re.compile(r"\bCOLLATE\s+RTRIM\b", re.I), ""),
    # REAL no PostgreSQL é float4 (seis dígitos): soma de dinheiro erraria
    (re.compile(r"\bAS\s+REAL\b", re.I), "AS DOUBLE PRECISION"),
    (re.compile(r"\blast_insert_rowid\s*\(\s*\)", re.I), "lastval()"),
    # `x IS ?` só existe no SQLite; o equivalente é IS [NOT] DISTINCT FROM
    (re.compile(r"\bIS\s+NOT\s+(?=[?:@$])", re.I), "IS DISTINCT FROM "),
    (re.compile(r"\bIS\s+(?=[?:@$])", re.I), "IS NOT DISTINCT FROM "),
    (re.compile(r"(?<![\w.])TRUE(?![\w(])", re.I), "1"),
    (re.compile(r"(?<![\w.])FALSE(?![\w(])", re.I), "0"),
    (re.compile(r"\bsqlite_schema\b", re.I), "sqlite_master"),
]

# Só em consulta e escrita: no DDL, `CHAR(10)` é tipo de coluna.
_RE_TROCAS_SO_DML = [
    (re.compile(r"(?<![\w.\"])char\s*\(", re.I), "chr("),
]

_RE_TIPOS_DDL = [
    (re.compile(r"\bINTEGER\s+PRIMARY\s+KEY(\s+AUTOINCREMENT)?\b", re.I),
     "BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY"),
    (re.compile(r"\bAUTOINCREMENT\b", re.I), ""),
    (re.compile(r"\bUNSIGNED\s+BIG\s+INT\b|\bBIG\s+INT\b|\bINTEGER\b|\bINT\b|\bTINYINT\b|\bSMALLINT\b|\bMEDIUMINT\b|\bINT8\b|\bINT2\b", re.I), "BIGINT"),
    (re.compile(r"\bDOUBLE\s+PRECISION\b|\bDOUBLE\b|\bFLOAT\b|\bREAL\b", re.I), "DOUBLE PRECISION"),
    (re.compile(r"\bBLOB\b", re.I), "BYTEA"),
    (re.compile(r"\bDATETIME\b|\bTIMESTAMP\b|\bDATE\b(?!\s*\()|\bTIME\b(?!\s*\()", re.I), "TEXT"),
    (re.compile(r"\bBOOLEAN\b|\bBOOL\b", re.I), "BIGINT"),
    (re.compile(r"\bWITHOUT\s+ROWID\b|\bSTRICT\b\s*$", re.I), ""),
    (re.compile(r"\bON\s+CONFLICT\s+(?:REPLACE|IGNORE|ABORT|FAIL|ROLLBACK)\b", re.I), ""),
]


def _trocar_no_codigo(sql: str, trocas) -> str:
    saida = []
    for trecho, codigo in _varrer(sql):
        if codigo:
            for padrao, novo in trocas:
                trecho = padrao.sub(novo, trecho)
        elif trecho.startswith("`") or trecho.startswith("["):
            trecho = '"' + trecho[1:-1].replace('"', '""') + '"'
        elif trecho == '""':
            # `""` no SQLite é o texto vazio (identificador que não existe vira
            # literal); no PostgreSQL é erro de sintaxe — identificador vazio
            # não existe lá. `COALESCE(x, "") = ""` (importar_padrao, P04).
            trecho = "''"
        saida.append(trecho)
    return "".join(saida)


def _glob_para_regex(p: str) -> str:
    """O padrão do GLOB do SQLite como expressão regular ancorada (o GLOB
    distingue caixa e casa o texto inteiro). A mesma regra de
    `cg_glob_regex` em banco_pg_funcoes.sql, que serve o padrão em parâmetro."""
    saida, i = ["^"], 0
    while i < len(p):
        c = p[i]
        if c == "*":
            saida.append(".*")
        elif c == "?":
            saida.append(".")
        elif c == "[":
            fim = p.find("]", i + 2)
            if fim < 0:
                saida.append(r"\[")
            else:
                saida.append(p[i:fim + 1].replace("\\", "\\\\"))
                i = fim
        else:
            saida.append(re.escape(c))
        i += 1
    return "".join(saida) + "$"


_RE_GLOB_NO_FIM = re.compile(r"\b(NOT\s+)?GLOB\s*$", re.I)
_RE_GLOB_PARAMETRO = re.compile(r"\b(NOT\s+)?GLOB\s+(\?\d*|:[A-Za-z_]\w*)", re.I)


def _glob_como_regex(sql: str) -> str:
    """`x GLOB 'p'` → `x ~ '^..$'`; `x GLOB ?` → `x ~ cg_glob_regex(?)`.
    A tradução antiga (SIMILAR TO) mudava o sentido: `'[0-9]*'` virava «só
    dígitos» e `'*X*'` era expressão inválida (achado do lote L2)."""
    if not re.search(r"\bGLOB\b", sql, re.I):
        return sql
    trechos = list(_varrer(sql))
    for k, (trecho, codigo) in enumerate(trechos):
        if not codigo:
            continue
        m = _RE_GLOB_NO_FIM.search(trecho)
        if m and k + 1 < len(trechos) and trechos[k + 1][0].startswith("'"):
            literal = trechos[k + 1][0][1:-1].replace("''", "'")
            regex = _glob_para_regex(literal).replace("'", "''")
            op = "!~ " if m.group(1) else "~ "
            trechos[k] = (trecho[:m.start()] + op, True)
            trechos[k + 1] = ("'" + regex + "'", False)
            continue
        trechos[k] = (_RE_GLOB_PARAMETRO.sub(
            lambda g: ("!~ " if g.group(1) else "~ ") + "cg_glob_regex(" + g.group(2) + ")",
            trecho), True)
    return "".join(t for t, _ in trechos)


_RE_CAST_ABRE = re.compile(r"\bCAST\s*\(", re.I)
_RE_AS_INTEIRO = re.compile(r"\bAS\s+(?:INTEGER|INT|BIGINT)\s*$", re.I)


def _cast_inteiro_como_sqlite(sql: str) -> str:
    """`CAST(x AS INTEGER)` → `cg_inteiro(x)`: o SQLite lê o prefixo numérico
    ('12A' → 12, '' → 0) e o PostgreSQL estouraria. Só quando o AS INTEGER
    é do próprio CAST (o nível de parênteses dele)."""
    if not _RE_CAST_ABRE.search(sql):
        return sql
    guardados, partes = [], []
    for trecho, codigo in _varrer(sql):
        if codigo:
            partes.append(trecho)
        else:
            guardados.append(trecho)
            partes.append(f"\x00{len(guardados) - 1}\x00")
    texto = "".join(partes)
    while True:
        mudou = False
        for m in _RE_CAST_ABRE.finditer(texto):
            i, nivel, fim = m.end(), 0, None
            while i < len(texto):
                if texto[i] == "(":
                    nivel += 1
                elif texto[i] == ")":
                    if nivel == 0:
                        fim = i
                        break
                    nivel -= 1
                i += 1
            if fim is None:
                break
            dentro = texto[m.end():fim]
            a = _RE_AS_INTEIRO.search(dentro)
            if a and dentro[:a.start()].count("(") == dentro[:a.start()].count(")"):
                texto = (texto[:m.start()] + "cg_inteiro(" + dentro[:a.start()].rstrip()
                         + ")" + texto[fim + 1:])
                mudou = True
                break
        if not mudou:
            break
    return re.sub("\x00(\\d+)\x00", lambda k: guardados[int(k.group(1))], texto)


_RE_ORDER_BY = re.compile(r"\bORDER\s+BY\b", re.I)
_RE_FIM_DO_ORDER = re.compile(
    r"\b(LIMIT|OFFSET|UNION|EXCEPT|INTERSECT|FETCH|FOR|WINDOW|RETURNING|ON\s+CONFLICT)\b", re.I)


def _nulos_como_sqlite(sql: str) -> str:
    """No SQLite o NULL vem PRIMEIRO no ASC e por último no DESC; no
    PostgreSQL é o contrário. Cada item de ORDER BY ganha o NULLS que o
    SQLite usaria — sem isso, toda lista com campo vazio mudaria de ordem."""
    if not _RE_ORDER_BY.search(sql):
        return sql
    trechos = list(_varrer(sql))
    guardados, partes = [], []
    for trecho, codigo in trechos:
        if codigo:
            partes.append(trecho)
        else:
            guardados.append(trecho)
            partes.append(f"\x00{len(guardados) - 1}\x00")
    texto = "".join(partes)
    saida, pos = [], 0
    for m in _RE_ORDER_BY.finditer(texto):
        if m.start() < pos:
            continue
        saida.append(texto[pos:m.end()])
        i, nivel, itens, ini = m.end(), 0, [], m.end()
        while i < len(texto):
            ch = texto[i]
            if ch == "(":
                nivel += 1
            elif ch == ")":
                if nivel == 0:
                    break
                nivel -= 1
            elif ch == ";" and nivel == 0:
                break
            elif ch == "," and nivel == 0:
                itens.append(texto[ini:i])
                ini = i + 1
            elif nivel == 0 and (i == 0 or not (texto[i - 1].isalnum() or texto[i - 1] == "_")):
                if _RE_FIM_DO_ORDER.match(texto, i):
                    break
            i += 1
        itens.append(texto[ini:i])
        novos = []
        for item in itens:
            corpo = item.rstrip()
            fim = item[len(corpo):]
            if not corpo.strip() or re.search(r"\bNULLS\s+(FIRST|LAST)\b", corpo, re.I):
                novos.append(item)
            elif re.search(r"\bDESC\s*$", corpo, re.I):
                novos.append(corpo + " NULLS LAST" + fim)
            else:
                novos.append(corpo + " NULLS FIRST" + fim)
        saida.append(",".join(novos))
        pos = i
    saida.append(texto[pos:])
    resultado = "".join(saida)
    return re.sub("\x00(\\d+)\x00", lambda k: guardados[int(k.group(1))], resultado)


def _parametros(sql: str, nomeados: bool) -> str:
    """`?` → `%s`, `:nome` → `%(nome)s`, `%` → `%%` (fora e dentro de aspas,
    porque o psycopg formata o texto inteiro quando há parâmetros)."""
    saida = []
    for trecho, codigo in _varrer(sql):
        trecho = trecho.replace("%", "%%")
        if codigo:
            if nomeados:
                trecho = re.sub(r"(?<![:\w]):([A-Za-z_]\w*)", r"%(\1)s", trecho)
                trecho = re.sub(r"[@$]([A-Za-z_]\w*)", r"%(\1)s", trecho)
            trecho = re.sub(r"\?\d*", "%s", trecho)
        saida.append(trecho)
    return "".join(saida)


_RE_CREATE_TABLE = re.compile(
    r"^\s*CREATE\s+(?:TEMP(?:ORARY)?\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?P<nome>\"[^\"]+\"|\w+)", re.I)
_RE_ALTER_ADD = re.compile(
    r"^\s*ALTER\s+TABLE\s+(?P<nome>\"[^\"]+\"|\w+)\s+ADD\s+(?:COLUMN\s+)?(?P<def>.+)$",
    re.I | re.S)
_RE_CREATE_INDEX = re.compile(r"^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\b", re.I)
_RE_DROP_TABLE = re.compile(
    r"^\s*DROP\s+TABLE\s+(?P<se>IF\s+EXISTS\s+)?(?:main\.)?(?P<nome>\"[^\"]+\"|`[^`]+`|\w+)\s*;?\s*$",
    re.I)
_RE_INSERT = re.compile(
    r"^\s*(?P<verbo>INSERT\s+OR\s+IGNORE|INSERT\s+OR\s+REPLACE|REPLACE|INSERT)\s+INTO\s+"
    r"(?P<nome>\"[^\"]+\"|\w+)\s*(?P<cols>\([^)]*\))?", re.I | re.S)
_RE_PRAGMA = re.compile(
    r"^\s*PRAGMA\s+(?:\w+\.)?(?P<nome>\w+)\s*(?:(?:=\s*(?P<valor>.+))|(?:\(\s*(?P<arg>[^)]*)\s*\)))?\s*;?\s*$",
    re.I | re.S)
_RE_BEGIN = re.compile(
    r"^\s*BEGIN(?:\s+(?P<modo>DEFERRED|IMMEDIATE|EXCLUSIVE))?(?:\s+TRANSACTION)?\s*;?\s*$", re.I)
_RE_FIM = re.compile(r"^\s*(?P<acao>COMMIT|END|ROLLBACK)(?:\s+TRANSACTION)?\s*;?\s*$", re.I)
_RE_FK_INLINE = re.compile(
    r"\bREFERENCES\s+(?P<alvo>\"[^\"]+\"|\w+)\s*(?:\((?P<cols>[^)]*)\))?"
    r"(?P<resto>(?:\s+ON\s+(?:DELETE|UPDATE)\s+(?:SET\s+NULL|SET\s+DEFAULT|CASCADE|RESTRICT|NO\s+ACTION))*"
    r"(?:\s+(?:NOT\s+)?DEFERRABLE(?:\s+INITIALLY\s+(?:DEFERRED|IMMEDIATE))?)?)", re.I)


def _nome(bruto: str) -> str:
    return bruto.strip().strip('"').lower()


def _partir_colunas(corpo: str) -> list[str]:
    """Separa as definições de um CREATE TABLE pelas vírgulas do nível de cima."""
    partes, nivel, atual = [], 0, []
    for trecho, codigo in _varrer(corpo):
        if not codigo:
            # comentário sai (no fim da última coluna ele comeria o «)» que
            # fecha a tabela); literal fica
            if not (trecho.startswith("--") or trecho.startswith("/*")):
                atual.append(trecho)
            else:
                atual.append(" ")
            continue
        for ch in trecho:
            if ch == "(":
                nivel += 1
            elif ch == ")":
                nivel -= 1
            if ch == "," and nivel == 0:
                partes.append("".join(atual).strip())
                atual = []
            else:
                atual.append(ch)
    if "".join(atual).strip():
        partes.append("".join(atual).strip())
    return partes


def _padrao_como_sqlite(padrao):
    """O DEFAULT como o PRAGMA do SQLite o mostra: `'ABERTO'::text` volta a
    ser `'ABERTO'`, e `cg_agora_texto()` volta a ser `CURRENT_TIMESTAMP`."""
    if padrao is None:
        return None
    texto = re.sub(r"::[a-z ]+(\[\])?$", "", str(padrao).strip())
    if texto.startswith("cg_agora_texto("):
        return "CURRENT_TIMESTAMP"
    return texto


# ------------------------------------------------------------- o cursor

class Cursor:
    """O cursor do `sqlite3`, sobre o do psycopg."""

    arraysize = 1

    def __init__(self, conexao: "Conexao"):
        self.connection = conexao
        self._linhas: list[tuple] = []
        self._pos = 0
        self._nomes: tuple[str, ...] = ()
        self._indice: dict[str, int] = {}
        self.description = None
        self.rowcount = -1
        self.lastrowid = None
        self.row_factory = None

    # -- leitura
    def _fazer(self, valores: tuple):
        fabrica = self.row_factory or self.connection.row_factory
        valores = tuple(_valor_do_banco(v) for v in valores)
        if fabrica is None:
            return valores
        if fabrica is sqlite3.Row or fabrica is Linha:
            return Linha(self._nomes, valores, self._indice)
        return fabrica(self, valores)

    def fetchone(self):
        if self._pos >= len(self._linhas):
            return None
        self._pos += 1
        return self._fazer(self._linhas[self._pos - 1])

    def fetchmany(self, size: int | None = None):
        size = size or self.arraysize
        fim = min(self._pos + size, len(self._linhas))
        saida = [self._fazer(t) for t in self._linhas[self._pos:fim]]
        self._pos = fim
        return saida

    def fetchall(self):
        saida = [self._fazer(t) for t in self._linhas[self._pos:]]
        self._pos = len(self._linhas)
        return saida

    def __iter__(self):
        while True:
            linha = self.fetchone()
            if linha is None:
                return
            yield linha

    def close(self) -> None:
        self._linhas = []

    def setinputsizes(self, *a) -> None:  # pragma: no cover
        pass

    def setoutputsize(self, *a) -> None:  # pragma: no cover
        pass

    # -- escrita
    def _carregar(self, nomes: Sequence[str], linhas: list[tuple], rowcount: int) -> None:
        self._nomes = tuple(nomes)
        self._indice = {n.lower(): k for k, n in reversed(list(enumerate(self._nomes)))}
        self._linhas = linhas
        self._pos = 0
        self.description = (tuple((n, None, None, None, None, None, None)
                                  for n in self._nomes) or None)
        self.rowcount = rowcount

    def execute(self, sql: str, parametros: Any = ()):
        self.connection._executar(self, sql, parametros)
        return self

    def executemany(self, sql: str, sequencia: Iterable[Any]):
        total = 0
        ultimo = None
        for p in sequencia:
            self.connection._executar(self, sql, p, em_lote=True)
            if self.rowcount and self.rowcount > 0:
                total += self.rowcount
            ultimo = self.lastrowid or ultimo
        self.rowcount = total
        self.lastrowid = ultimo
        self._linhas = []
        return self

    def executescript(self, script: str):
        self.connection.executescript(script)
        return self


# ------------------------------------------------------------- a conexão

_DDL_ARQUIVO_FUNCOES = Path(__file__).with_name("banco_pg_funcoes.sql")
_SCHEMAS_PRONTOS: set[tuple[str, str]] = set()
_TRAVA_SCHEMAS = threading.Lock()
_SCHEMAS_CRIADOS: list[str] = []
_CHAVE_DO_PREPARO = 7_100_715_202_610_150
_FUNCOES_PRONTAS: set[str] = set()

# O QUE O SCHEMA DA CASA PEDE EMPRESTADO DO `public` (26/10/2026). As tabelas
# usam a collation `public.cg_nocase`, os índices do imóvel usam o pg_trgm, e as
# funções do SQLite moram em `public`. **O `pg_dump -n <schema>` do backup NÃO
# leva nada disso** — e por isso o pacote, sozinho, não restaura num banco
# vazio. Quem prepara o banco vazio antes do `pg_restore` (o teste de
# restauração, e quem restaurar num servidor novo) usa os MESMOS comandos, daqui:
# duas cópias deles divergiriam no primeiro conserto, e a restauração do dia do
# desastre descobriria isso.
_SQL_COLLATION_NOCASE = ("CREATE COLLATION IF NOT EXISTS public.cg_nocase "
                         "(provider = icu, locale = 'und-u-ks-level2', deterministic = false)")
_SQL_PG_TRGM = "CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA public"
_SQL_UNACCENT = "CREATE EXTENSION IF NOT EXISTS unaccent SCHEMA public"


def preparar_banco_vazio(c) -> None:
    """Põe no `public` de um banco VAZIO o que o schema da casa pede: a collation,
    as duas extensões e as funções de `banco_pg_funcoes.sql`. Sem cache e sem a
    marca de `public.cg_funcoes` — é para um banco que acabou de nascer.

    `c` é um cursor de psycopg ligado ao banco descartável. NUNCA chame isto no
    banco da casa: lá quem prepara é `_instalar_funcoes`, com a trava do preparo.
    """
    texto = _DDL_ARQUIVO_FUNCOES.read_text(encoding="utf-8") if _DDL_ARQUIVO_FUNCOES.exists() else ""
    c.execute(_SQL_COLLATION_NOCASE)
    c.execute(_SQL_PG_TRGM)
    c.execute(_SQL_UNACCENT)
    if texto:
        c.execute("SET search_path TO public")
        c.execute(texto)


def _instalar_funcoes(c, schema: str) -> None:
    """As funções do SQLite (strftime, date, group_concat, nome_da_casa…),
    uma vez por banco, em `public` — e de novo se o arquivo mudar."""
    if dsn() in _FUNCOES_PRONTAS:
        return
    texto = _DDL_ARQUIVO_FUNCOES.read_text(encoding="utf-8") if _DDL_ARQUIVO_FUNCOES.exists() else ""
    marca = hashlib.sha1(texto.encode("utf-8")).hexdigest()
    c.execute(_SQL_COLLATION_NOCASE)
    # O pg_trgm (indice do imovel, ri_schema) nasce AQUI, sob a trava do preparo:
    # criado so no ri_schema, quatro processos subindo juntos num banco novo
    # batiam no `pg_extension_name_index` (medido na suite com -n 4, 18/10/2026).
    c.execute(_SQL_PG_TRGM)
    c.execute("CREATE TABLE IF NOT EXISTS public.cg_funcoes (marca TEXT PRIMARY KEY)")
    c.execute("SELECT 1 FROM public.cg_funcoes WHERE marca=%s", (marca,))
    if c.fetchone() is None:
        c.execute(_SQL_UNACCENT)
        if texto:
            c.execute("SET search_path TO public")
            try:
                c.execute(texto)
            finally:
                c.execute(f'SET search_path TO "{schema}", public')
            c.execute("DELETE FROM public.cg_funcoes")
            c.execute("INSERT INTO public.cg_funcoes(marca) VALUES (%s)", (marca,))
    _FUNCOES_PRONTAS.add(dsn())


def descartar_schema(schema: str) -> None:
    """Apaga um schema inteiro (os testes chamam ao terminar). Derruba antes
    as conexões que ficaram abertas nele — uma conexão esquecida no meio de
    uma transação seguraria o DROP para sempre."""
    if not ativo() or not schema.startswith("cg_"):
        return
    esvaziar_reservatorio(schema)
    with psycopg.connect(dsn(), autocommit=True) as pg, pg.cursor() as c:
        c.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                  "WHERE application_name=%s AND pid<>pg_backend_pid()", (schema[:60],))
        c.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    for marca in [m for m in _SCHEMAS_PRONTOS if m[1] == schema]:
        _SCHEMAS_PRONTOS.discard(marca)
    if schema in _SCHEMAS_CRIADOS:
        _SCHEMAS_CRIADOS.remove(schema)


def schemas_criados() -> list[str]:
    return list(_SCHEMAS_CRIADOS)


# ------------------------------------------------ o reservatório de conexões
#
# O CÓDIGO ABRE UMA CONEXÃO POR CONSULTA (`q`, `q1`, `db.connect()` em toda
# rota): no SQLite isso custa microssegundos; no PostgreSQL, dezenas de
# milissegundos — medido em 15/10/2026, dois testes de tela abriram 1.129
# conexões. `close()` devolve a conexão aqui, sem transação aberta e com o
# `lock_timeout` de volta ao padrão, e a próxima `Conexao` do mesmo banco a
# reaproveita.

_RESERVATORIO: dict[str, list] = {}
_TRAVA_RESERVATORIO = threading.Lock()
_MAXIMO_POR_BANCO = 8
# Teto do processo inteiro: a suíte passa por centenas de bancos, e 8 por
# banco sem teto geral esgotou o `max_connections` do servidor (16/10/2026,
# 6 trabalhadores, 2.800 erros «too many clients»). Passou do teto, fecha-se
# a guardada do banco usado há mais tempo.
_MAXIMO_NO_TOTAL = 8


def _tomar_do_reservatorio(schema: str):
    with _TRAVA_RESERVATORIO:
        fila = _RESERVATORIO.get(dsn() + "|" + schema)
        while fila:
            pg = fila.pop()
            if not pg.closed and pg.info.transaction_status == psycopg.pq.TransactionStatus.IDLE:
                return pg
            try:
                pg.close()
            except Exception:  # noqa: BLE001
                pass
    return None


def _devolver_ao_reservatorio(schema: str, pg) -> None:
    try:
        if pg.closed or pg.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
            pg.close()
            return
        with pg.cursor() as c:
            c.execute("SET lock_timeout = '15s'")
            c.execute("SET default_transaction_read_only = off")
    except Exception:  # noqa: BLE001
        try:
            pg.close()
        except Exception:  # noqa: BLE001
            pass
        return
    sobra = []
    with _TRAVA_RESERVATORIO:
        chave = dsn() + "|" + schema
        fila = _RESERVATORIO.pop(chave, [])
        _RESERVATORIO[chave] = fila  # o mais recente vai para o fim
        if len(fila) < _MAXIMO_POR_BANCO:
            fila.append(pg)
            pg = None
            total = sum(len(f) for f in _RESERVATORIO.values())
            for outra in list(_RESERVATORIO):
                if total <= _MAXIMO_NO_TOTAL:
                    break
                velhas = _RESERVATORIO[outra]
                while velhas and total > _MAXIMO_NO_TOTAL:
                    sobra.append(velhas.pop(0))
                    total -= 1
                if not velhas:
                    del _RESERVATORIO[outra]
    if pg is not None:
        sobra.append(pg)
    for velha in sobra:
        try:
            velha.close()
        except Exception:  # noqa: BLE001
            pass


def esvaziar_reservatorio(schema: str | None = None) -> None:
    """Fecha as conexões guardadas (de um banco, ou de todos)."""
    with _TRAVA_RESERVATORIO:
        chaves = [k for k in _RESERVATORIO if schema is None or k.endswith("|" + schema)]
        filas = [_RESERVATORIO.pop(k) for k in chaves]
    for fila in filas:
        for pg in fila:
            try:
                pg.close()
            except Exception:  # noqa: BLE001
                pass


# ------------------------------------------------ banco de teste reaproveitado
#
# POR QUE EXISTE: no Windows, criar um banco novo são ~2.200 arquivos e apagar
# outros tantos — medido em 15/10/2026, 12 s para criar (já reproduzindo a
# gravação) e até 158 s para apagar. A suíte cria milhares. Então o banco que
# um teste largou é ESVAZIADO (só as tabelas com linha, e as sementes voltam)
# e guardado; o próximo `Database()` novo o recebe com um RENAME, que é
# instantâneo. Só se reaproveita banco cuja forma não mudou: se o teste criou
# tabela, coluna ou índice, a impressão digital da forma não bate e ele vai
# para o lixo.

_RESERVA: list[str] = []
_SEMENTE: dict[str, Any] = {"schema": None, "tabelas": None, "forma": None, "nomes": None}
_TABELA_DOS_NOMES = "cg__nomes_da_forma"


def _nomes_da_semente(c, semente: str):
    """Os nomes das relações do banco recém-criado, guardados na semente
    (None em semente antiga, que não os guardou)."""
    c.execute("SELECT to_regclass(%s)", (f'"{semente}"."{_TABELA_DOS_NOMES}"',))
    if c.fetchone()[0] is None:
        return None
    c.execute(f'SELECT nome FROM "{semente}"."{_TABELA_DOS_NOMES}"')
    return frozenset(r[0] for r in c.fetchall())


def _tirar_o_que_o_teste_criou(c, schema: str) -> None:
    """O TESTE CRIA TABELA PELO CAMINHO (módulo que monta o esquema na primeira
    chamada), e a forma deixava de bater: todo banco usado ia para o lixo e o
    teste seguinte recriava tudo — ~90 s por teste, medido pelo L5 às 21h58,
    com zero reservas no servidor. Tira as relações que não estavam no banco
    recém-criado; se FALTA alguma, não mexe (vai para o lixo)."""
    nomes = _SEMENTE.get("nomes")
    if not nomes:
        return
    c.execute("SELECT k.relname, k.relkind FROM pg_class k JOIN pg_namespace n ON n.oid=k.relnamespace "
              "WHERE n.nspname=%s", (schema,))
    atuais = {r[0]: r[1] for r in c.fetchall()}
    if not nomes <= set(atuais):
        return
    sobra = [n for n in atuais if n not in nomes]
    if not sobra:
        return
    for nome in sobra:
        tipo = atuais[nome]
        if tipo in ("v", "m"):
            c.execute(f'DROP {"MATERIALIZED " if tipo == "m" else ""}VIEW IF EXISTS "{schema}"."{nome}" CASCADE')
    for nome in sobra:
        if atuais[nome] in ("r", "p"):
            c.execute(f'DROP TABLE IF EXISTS "{schema}"."{nome}" CASCADE')
    for nome in sobra:
        if atuais[nome] == "i":
            c.execute(f'DROP INDEX IF EXISTS "{schema}"."{nome}"')
        elif atuais[nome] == "S":
            c.execute(f'DROP SEQUENCE IF EXISTS "{schema}"."{nome}" CASCADE')
    c.execute(f'DELETE FROM "{schema}".cg_ddl WHERE nome = ANY(%s)', (sobra,))
    c.execute(f'DELETE FROM "{schema}".cg_fk_pendentes WHERE tabela = ANY(%s)', (sobra,))
_NAO_ESVAZIA = ("cg_ddl", "cg_fk_pendentes")


def _nome_de_reserva() -> str:
    return "cg_reserva_" + hashlib.sha1(os.urandom(16)).hexdigest()[:12]


def _forma(c, schema: str):
    """Impressão digital da FORMA do banco: relações, colunas, padrões,
    restrições e índices. Teste que mexe no esquema muda algum destes."""
    c.execute(
        "WITH k AS (SELECT k.oid FROM pg_class k JOIN pg_namespace n ON n.oid=k.relnamespace "
        "WHERE n.nspname=%s) SELECT (SELECT count(*) FROM k), "
        "(SELECT count(*) FROM pg_attribute a WHERE a.attrelid IN (SELECT oid FROM k) "
        " AND a.attnum>0 AND NOT a.attisdropped), "
        "(SELECT count(*) FROM pg_attrdef d WHERE d.adrelid IN (SELECT oid FROM k)), "
        "(SELECT count(*) FROM pg_constraint r WHERE r.conrelid IN (SELECT oid FROM k)), "
        "(SELECT count(*) FROM pg_index x WHERE x.indrelid IN (SELECT oid FROM k))", (schema,))
    return tuple(c.fetchone())


def _tabelas_do(c, schema: str) -> list[str]:
    c.execute("SELECT k.relname FROM pg_class k JOIN pg_namespace n ON n.oid=k.relnamespace "
              "WHERE n.nspname=%s AND k.relkind='r' ORDER BY 1", (schema,))
    return [r[0] for r in c.fetchall()]


def _cheias(c, schema: str, tabelas: list[str]) -> list[str]:
    if not tabelas:
        return []
    partes = [f'(SELECT %s::text FROM "{schema}"."{t}" LIMIT 1)' for t in tabelas]
    c.execute(" UNION ALL ".join(partes), tabelas)
    return [r[0] for r in c.fetchall()]


def guardar_semente(db_path: Any) -> None:
    """Fotografa o banco recém-criado (forma e linhas das sementes): é o
    estado a que um banco reaproveitado volta. A semente tem o nome da MARCA
    do código de esquema, e fica para os outros processos (ver
    `_carregar_gravacao_compartilhada`)."""
    if _SEMENTE["schema"]:
        return
    origem = schema_do_caminho(db_path)
    semente = "cg_semente_" + marca_do_codigo()[:16]
    with psycopg.connect(dsn(), autocommit=True) as pg, pg.cursor() as c:
        c.execute("SELECT pg_advisory_lock(%s)", (_CHAVE_DA_SEMENTE,))
        try:
            c.execute("SELECT to_regnamespace(%s)", (semente,))
            if c.fetchone()[0] is None:
                c.execute(f'CREATE SCHEMA "{semente}"')
                cheias = [t for t in _cheias(c, origem, _tabelas_do(c, origem)) if t not in _NAO_ESVAZIA]
                for t in cheias:
                    c.execute(f'CREATE TABLE "{semente}"."{t}" AS SELECT * FROM "{origem}"."{t}"')
                c.execute(f'CREATE TABLE "{semente}"."{_TABELA_DOS_NOMES}" AS '
                          "SELECT k.relname AS nome FROM pg_class k JOIN pg_namespace n "
                          "ON n.oid=k.relnamespace WHERE n.nspname=%s", (origem,))
            else:
                cheias = [t for t in _tabelas_do(c, semente) if t != _TABELA_DOS_NOMES]
            forma = _forma(c, origem)
            _SEMENTE.update(schema=semente, tabelas=cheias, forma=forma, nomes=_nomes_da_semente(c, semente))
            if _CRIACAO_GRAVADA["linhas"]:
                c.execute(
                    "CREATE TABLE IF NOT EXISTS public.cg_gravacao (marca TEXT PRIMARY KEY, "
                    "origem TEXT, linhas TEXT[], semente TEXT, tabelas TEXT[], forma TEXT, "
                    "criada_em TIMESTAMPTZ DEFAULT now())")
                c.execute(
                    "INSERT INTO public.cg_gravacao(marca, origem, linhas, semente, tabelas, forma) "
                    "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (marca) DO NOTHING",
                    (marca_do_codigo(), _CRIACAO_GRAVADA["schema"], _CRIACAO_GRAVADA["linhas"],
                     semente, cheias, ",".join(str(x) for x in forma)))
        finally:
            c.execute("SELECT pg_advisory_unlock(%s)", (_CHAVE_DA_SEMENTE,))


_CHAVE_DA_SEMENTE = 7_100_715_202_610_151
_CHAVE_DA_REPRODUCAO = 7_100_715_202_610_152
_MARCA: dict[str, str] = {}


def marca_do_codigo() -> str:
    """Impressão digital do código que DESENHA o banco: todo .py da pasta que
    escreve CREATE/ALTER TABLE, a camada, as funções e o conftest dos testes
    (que mexe nas sementes). Mudou um deles, a gravação compartilhada não
    serve mais e se grava de novo — os agentes mexem no código a noite toda."""
    if "m" in _MARCA:
        return _MARCA["m"]
    raiz = Path(__file__).resolve().parent
    h = hashlib.sha1()
    candidatos = sorted(raiz.glob("*.py")) + [raiz / "banco_pg_funcoes.sql", raiz / "tests" / "conftest.py"]
    for arq in candidatos:
        try:
            st = arq.stat()
            if arq.suffix == ".py" and arq.name not in ("banco_pg.py", "bd_nativo.py") and arq.parent == raiz:
                texto = arq.read_bytes()
                if b"CREATE TABLE" not in texto and b"ALTER TABLE" not in texto:
                    continue
            h.update(f"{arq.name}|{st.st_size}|{st.st_mtime_ns}\n".encode())
        except OSError:
            continue
    # sob pytest o conftest troca as sementes (serventia fictícia): marca própria
    import sys as _sys
    h.update(b"pytest" if "pytest" in _sys.modules else b"programa")
    _MARCA["m"] = h.hexdigest()
    return _MARCA["m"]


def _carregar_gravacao_compartilhada() -> bool:
    """Outro processo já gravou a criação deste mesmo código? Então este
    reproduz a dele e usa a semente dele, sem gravar de novo."""
    if _CRIACAO_GRAVADA["linhas"] and _SEMENTE["schema"]:
        return True
    try:
        with psycopg.connect(dsn(), autocommit=True) as pg, pg.cursor() as c:
            c.execute("SELECT to_regclass('public.cg_gravacao')")
            if c.fetchone()[0] is None:
                return False
            c.execute("SELECT origem, linhas, semente, tabelas, forma FROM public.cg_gravacao "
                      "WHERE marca=%s", (marca_do_codigo(),))
            linha = c.fetchone()
            if not linha:
                return False
            c.execute("SELECT to_regnamespace(%s)", (linha[2],))
            if c.fetchone()[0] is None:
                return False
    except psycopg.Error:
        return False
    _CRIACAO_GRAVADA.update(schema=linha[0], linhas=list(linha[1]))
    _SEMENTE.update(schema=linha[2], tabelas=[t for t in linha[3] if t != _TABELA_DOS_NOMES],
                    forma=tuple(int(x) for x in linha[4].split(",")))
    try:
        with psycopg.connect(dsn(), autocommit=True) as pg, pg.cursor() as c:
            _SEMENTE["nomes"] = _nomes_da_semente(c, linha[2])
    except psycopg.Error:
        _SEMENTE["nomes"] = None
    return True


def _esvaziar(c, schema: str) -> None:
    semente = _SEMENTE["schema"]
    c.execute("SET session_replication_role = replica")   # sem gatilho de FK
    try:
        sujas = [t for t in _cheias(c, schema, _tabelas_do(c, schema)) if t not in _NAO_ESVAZIA]
        for t in sorted(set(sujas) | set(_SEMENTE["tabelas"])):
            c.execute(f'DELETE FROM "{schema}"."{t}"')
        for t in _SEMENTE["tabelas"]:
            c.execute(f'INSERT INTO "{schema}"."{t}" SELECT * FROM "{semente}"."{t}"')
        # as sequências voltam ao maior id de cada tabela (ou ao começo)
        c.execute(
            "SELECT k.relname, a.attname, pg_get_serial_sequence(format('%%I.%%I', n.nspname, k.relname), a.attname) "
            "FROM pg_attribute a JOIN pg_class k ON k.oid=a.attrelid JOIN pg_namespace n ON n.oid=k.relnamespace "
            "WHERE n.nspname=%s AND a.attidentity IN ('a','d')", (schema,))
        for tabela, coluna, seq in c.fetchall():
            if seq:
                c.execute(f'SELECT setval(%s, COALESCE((SELECT MAX("{coluna}") FROM "{schema}"."{tabela}"), 0) + 1, false)',
                          (seq,))
    finally:
        c.execute("SET session_replication_role = origin")


def devolver_schema(schema: str) -> None:
    """O teste acabou: esvazia e guarda o banco, ou apaga se a forma mudou."""
    if not ativo() or not schema.startswith("cg_"):
        return
    for marca in [m for m in _SCHEMAS_PRONTOS if m[1] == schema]:
        _SCHEMAS_PRONTOS.discard(marca)
    if schema in _SCHEMAS_CRIADOS:
        _SCHEMAS_CRIADOS.remove(schema)
    esvaziar_reservatorio(schema)
    with psycopg.connect(dsn(), autocommit=True) as pg, pg.cursor() as c:
        c.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                  "WHERE application_name=%s AND pid<>pg_backend_pid()", (schema[:60],))
        if _SEMENTE["schema"]:
            try:
                _tirar_o_que_o_teste_criou(c, schema)
            except psycopg.Error:
                pass
        if _SEMENTE["schema"] and _forma(c, schema) == _SEMENTE["forma"]:
            try:
                _esvaziar(c, schema)
                reserva = _nome_de_reserva()
                c.execute(f'ALTER SCHEMA "{schema}" RENAME TO "{reserva}"')
                _RESERVA.append(reserva)
                return
            except psycopg.Error:
                pass
        # NÃO APAGA AGORA: o DROP CASCADE de ~400 tabelas é o comando mais
        # pesado do catálogo, e com sete agentes ele chegou a 13 minutos
        # (medido pelo L1, 19h15). Renomear é instantâneo; o lixo
        # (`cg_lixo_*`) se apaga de uma vez com `apagar_lixo()`, com a máquina
        # livre.
        c.execute(f'ALTER SCHEMA "{schema}" RENAME TO "cg_lixo_{hashlib.sha1(os.urandom(16)).hexdigest()[:12]}"')


def apagar_lixo() -> int:
    """Apaga os schemas renomeados para lixo. Devolve quantos."""
    with psycopg.connect(dsn(), autocommit=True) as pg, pg.cursor() as c:
        c.execute(r"SELECT nspname FROM pg_namespace WHERE nspname LIKE 'cg\_lixo\_%'")
        nomes = [r[0] for r in c.fetchall()]
        for nome in nomes:
            c.execute(f'DROP SCHEMA IF EXISTS "{nome}" CASCADE')
    return len(nomes)


def tomar_da_reserva(db_path: Any) -> bool:
    """Banco novo a partir de um esvaziado (de qualquer processo, desta ou de
    outra rodada): confere a forma contra a semente DESTE processo, repõe as
    sementes DESTE código e renomeia. False se não há reserva que sirva."""
    if os.environ.get("CG_PG_SEM_REPRODUCAO", "").strip() == "1":
        return False
    if not _SEMENTE["schema"] and not _carregar_gravacao_compartilhada():
        return False
    destino = schema_do_caminho(db_path)
    with psycopg.connect(dsn(), autocommit=True) as pg, pg.cursor() as c:
        c.execute(r"SELECT nspname FROM pg_namespace WHERE nspname LIKE 'cg\_reserva\_%' "
                  "ORDER BY random() LIMIT 20")
        for (reserva,) in c.fetchall():
            try:
                c.execute("BEGIN")
                c.execute("SELECT pg_try_advisory_xact_lock(hashtext(%s))", (reserva,))
                if not c.fetchone()[0]:
                    c.execute("ROLLBACK")
                    continue
                c.execute("SELECT to_regnamespace(%s)", (reserva,))
                if c.fetchone()[0] is None or _forma(c, reserva) != _SEMENTE["forma"]:
                    c.execute("ROLLBACK")
                    continue
                c.execute(f'ALTER SCHEMA "{reserva}" RENAME TO "{destino}"')
                c.execute("COMMIT")
            except psycopg.Error:
                try:
                    c.execute("ROLLBACK")
                except psycopg.Error:
                    pass
                continue
            _esvaziar(c, destino)
            _SCHEMAS_CRIADOS.append(destino)
            return True
    return False


_PREPARO_DO_SCHEMA = """
CREATE TABLE IF NOT EXISTS cg_meta (chave TEXT PRIMARY KEY, valor TEXT);
CREATE TABLE IF NOT EXISTS cg_ddl (nome TEXT PRIMARY KEY, tipo TEXT, tabela TEXT, sql TEXT);
CREATE TABLE IF NOT EXISTS cg_fk_pendentes (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tabela TEXT, comando TEXT, erro TEXT);
CREATE OR REPLACE VIEW sqlite_master AS
  SELECT 'table'::text AS type, c.relname::text AS name, c.relname::text AS tbl_name,
         0 AS rootpage, d.sql AS sql
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN cg_ddl d ON d.nome = c.relname
   WHERE n.nspname = current_schema() AND c.relkind IN ('r', 'p')
     AND c.relname NOT IN ('cg_meta', 'cg_ddl', 'cg_fk_pendentes')
  UNION ALL
  SELECT 'index', i.relname::text, t.relname::text, 0,
         COALESCE(d.sql, pg_get_indexdef(i.oid))
    FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid
    JOIN pg_class t ON t.oid = x.indrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    LEFT JOIN cg_ddl d ON d.nome = i.relname
   WHERE n.nspname = current_schema() AND NOT x.indisprimary
     AND t.relname NOT IN ('cg_meta', 'cg_ddl', 'cg_fk_pendentes')
     AND d.sql IS NOT NULL
  UNION ALL
  SELECT 'view', c.relname::text, c.relname::text, 0, d.sql
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN cg_ddl d ON d.nome = c.relname
   WHERE n.nspname = current_schema() AND c.relkind = 'v'
     AND c.relname NOT IN ('sqlite_master', 'sqlite_sequence');
CREATE OR REPLACE VIEW sqlite_sequence AS
  SELECT tc.relname::text AS name, ps.last_value AS seq
    FROM pg_class sc JOIN pg_namespace n ON n.oid = sc.relnamespace
    JOIN pg_depend d ON d.objid = sc.oid AND d.deptype IN ('a', 'i')
    JOIN pg_class tc ON tc.oid = d.refobjid
    JOIN pg_sequences ps ON ps.schemaname = n.nspname AND ps.sequencename = sc.relname
   WHERE sc.relkind = 'S' AND n.nspname = current_schema() AND ps.last_value IS NOT NULL;
"""


def _fuso_local() -> str:
    """O deslocamento do relógio do Windows, para o 'localtime' das datas."""
    desl = _dt.datetime.now().astimezone().utcoffset() or _dt.timedelta(0)
    minutos = int(desl.total_seconds() // 60)
    sinal = "+" if minutos >= 0 else "-"
    minutos = abs(minutos)
    return f"{sinal}{minutos // 60:02d}:{minutos % 60:02d}"


class Conexao:
    """`sqlite3.Connection`, falando com o PostgreSQL."""

    def __init__(self, db_path: Any, *, fechar_no_with: bool = False,
                 linhas_com_nome: bool = False):
        if psycopg is None:
            raise OperationalError(
                "O sistema está configurado para o PostgreSQL (CG_PG_DSN), mas o "
                "driver psycopg não está instalado neste Python.")
        self.db_path = db_path
        self.schema = schema_do_caminho(db_path)
        self._so_leitura = _caminho_e_modo(db_path)[1]
        self._fechar_no_with = fechar_no_with
        # `linhas_com_nome`: a `sqlite3.Row` da ponte desde a abertura (L072).
        self.row_factory = Linha if linhas_com_nome else None
        self.isolation_level = ""
        self.total_changes = 0
        self._em_transacao = False
        self._travada = False
        self._ultimo_id = None
        self._chave_trava = int(hashlib.sha1(self.schema.encode()).hexdigest()[:15], 16)
        self._cache_identidade: dict[str, str | None] = {}
        self._cache_chaves: dict[str, list[list[str]]] = {}
        self._cache_colunas: dict[str, list[str]] = {}
        self._fechada = False
        self._pg = _tomar_do_reservatorio(self.schema)
        if self._pg is None:
            try:
                self._pg = psycopg.connect(dsn(), autocommit=True, application_name=self.schema[:60],
                                           cursor_factory=psycopg.ClientCursor)
            except psycopg.Error as erro:
                raise _traduzir_erro(erro) from erro
            with self._pg.cursor() as c:
                c.execute(f'SET search_path TO "{self.schema}", public')
                c.execute("SET lock_timeout = '15s'")
                c.execute(f"SET TIME ZONE INTERVAL '{_fuso_local()}' HOUR TO MINUTE")
        self._preparar_schema()
        if self._so_leitura:
            # `mode=ro` do sqlite3: aqui o próprio servidor recusa a escrita
            with self._pg.cursor() as c:
                c.execute("SET default_transaction_read_only = on")

    # -- as funções do SQLite moram em `public`, uma vez por banco; o schema
    #    nasce com a visão sqlite_master e as tabelas de apoio
    def _preparar_schema(self) -> None:
        marca = (dsn(), self.schema)
        if marca in _SCHEMAS_PRONTOS:
            return
        with _TRAVA_SCHEMAS:
            if marca in _SCHEMAS_PRONTOS:
                return
            with self._pg.cursor() as c:
                # A FILA DO PREPARO NÃO TEM PRAZO: com o lock_timeout de 15 s
                # da conexão, esperar a vez virava «database is locked» (137
                # ERROR de setup medidos pelo L5 com xdist, 15/10 20h).
                # E A FILA GLOBAL SÓ SERVE ÀS FUNÇÕES, que moram em `public`
                # e são de todos — uma vez por processo. O schema de cada
                # banco tem trava própria: com uma só, todos os processos de
                # todos os lotes esperavam um atrás do outro (L2, 20h07: ~30
                # testes em 65 min, a maioria ERROR de setup).
                chave_do_schema = int(hashlib.sha1(("preparo:" + self.schema).encode()).hexdigest()[:15], 16)
                c.execute("SET lock_timeout = 0")
                try:
                    if dsn() not in _FUNCOES_PRONTAS:
                        c.execute("SELECT pg_advisory_lock(%s)", (_CHAVE_DO_PREPARO,))
                        try:
                            _instalar_funcoes(c, self.schema)
                        finally:
                            c.execute("SELECT pg_advisory_unlock(%s)", (_CHAVE_DO_PREPARO,))
                    c.execute("SELECT pg_advisory_lock(%s)", (chave_do_schema,))
                    try:
                        c.execute("SELECT 1 FROM pg_class k JOIN pg_namespace n ON n.oid=k.relnamespace "
                                  "WHERE n.nspname=%s AND k.relname='cg_meta'", (self.schema,))
                        if c.fetchone() is None:
                            c.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"')
                            c.execute(_PREPARO_DO_SCHEMA)
                            _SCHEMAS_CRIADOS.append(self.schema)
                    finally:
                        c.execute("SELECT pg_advisory_unlock(%s)", (chave_do_schema,))
                finally:
                    c.execute("SET lock_timeout = '15s'")
            _SCHEMAS_PRONTOS.add(marca)

    # -- o que o sqlite3 oferece
    @property
    def in_transaction(self) -> bool:
        return self._em_transacao

    def cursor(self, factory=None) -> Cursor:
        cur = (factory or Cursor)(self)
        return cur

    def execute(self, sql: str, parametros: Any = ()) -> Cursor:
        cur = Cursor(self)
        self._executar(cur, sql, parametros)
        return cur

    def executemany(self, sql: str, sequencia: Iterable[Any]) -> Cursor:
        return Cursor(self).executemany(sql, sequencia)

    def executescript(self, script: str) -> Cursor:
        """Como o sqlite3: confirma o que estiver aberto e roda comando a
        comando (sem transação implícita)."""
        if self._em_transacao:
            self.commit()
        cur = Cursor(self)
        comandos = dividir_comandos(script)
        # UMA TRANSAÇÃO PARA O SCRIPT INTEIRO, com ponto de retorno por comando:
        # confirmar CREATE TABLE por CREATE TABLE custava ~40 s por banco novo.
        # O efeito visível é o do SQLite — o que rodou antes de um comando que
        # falha fica gravado, e o erro sobe. Script que traz o próprio BEGIN ou
        # COMMIT roda do jeito antigo, comando a comando.
        controla = any(_RE_BEGIN.match(_sem_comentario_na_frente(c))
                       or _RE_FIM.match(_sem_comentario_na_frente(c)) for c in comandos)
        if not controla:
            self._comecar(False)
        try:
            for comando in comandos:
                self._executar(cur, comando, (), de_script=True)
            self._tentar_fks_pendentes()
        finally:
            if not controla and self._em_transacao:
                self.commit()
        return cur

    def commit(self) -> None:
        if self._em_transacao:
            self._cru("COMMIT")
        self._em_transacao = False
        self._travada = False

    def rollback(self) -> None:
        if self._em_transacao:
            self._cru("ROLLBACK")
        self._em_transacao = False
        self._travada = False

    def close(self) -> None:
        if self._fechada:
            return
        self._fechada = True
        pg, self._pg = self._pg, None
        try:
            if self._em_transacao:
                self._em_transacao = False
                self._travada = False
                with pg.cursor() as c:
                    c.execute("ROLLBACK")
        except Exception:  # noqa: BLE001
            try:
                pg.close()
            except Exception:  # noqa: BLE001
                pass
            return
        _devolver_ao_reservatorio(self.schema, pg)

    def __del__(self):  # conexão esquecida também volta ao reservatório
        try:
            if not getattr(self, "_fechada", True):
                self.close()
        except Exception:  # noqa: BLE001
            pass

    def create_function(self, nome: str, *_a, **_k) -> None:
        """As funções da casa já estão instaladas no schema (banco_pg_funcoes.sql)."""
        return None

    def create_aggregate(self, nome: str, *_a, **_k) -> None:
        return None

    def create_collation(self, nome: str, *_a, **_k) -> None:
        return None

    def set_trace_callback(self, *_a) -> None:  # pragma: no cover
        return None

    def interrupt(self) -> None:  # pragma: no cover
        return None

    def backup(self, destino, **_k) -> None:
        """O `.backup()` do sqlite3: o destino fica uma cópia deste banco.

        Destino SQLite (a cópia «antes da carga» do ri_web e do caixa_web) →
        exportação: as tabelas com o DDL original do SQLite (`cg_ddl`), as
        linhas, os índices e as visões. Destino PostgreSQL (outra `Conexao`) →
        cópia de schema a schema, dentro do servidor. Em ambos, o que havia
        no destino sai antes, como no SQLite."""
        if isinstance(destino, Conexao):
            self._copiar_para_schema(destino)
        elif isinstance(destino, sqlite3.Connection):
            self._exportar_para_sqlite(destino)
        else:
            raise TypeError("backup() argument 'target' must be sqlite3.Connection, "
                            f"not {type(destino).__name__}")

    def _exportar_para_sqlite(self, alvo: sqlite3.Connection) -> None:
        objetos = self._cru("SELECT type, name, sql FROM sqlite_master") or []
        tabelas = sorted((n, s) for t, n, s in objetos if t == "table")
        indices = [s for t, _n, s in objetos if t == "index" and s]
        visoes = [s for t, _n, s in objetos if t == "view" and s]
        if alvo.in_transaction:
            alvo.commit()
        fk = alvo.execute("PRAGMA foreign_keys").fetchone()[0]
        alvo.execute("PRAGMA foreign_keys=OFF")
        try:
            alvo.execute("BEGIN")
            try:
                velhos = alvo.execute("SELECT type, name FROM sqlite_master "
                                      "WHERE type IN ('view', 'table') AND name NOT LIKE 'sqlite_%' "
                                      "ORDER BY type DESC").fetchall()
                for tipo, nome in velhos:
                    alvo.execute(f'DROP {tipo.upper()} IF EXISTS "{nome}"')
                for nome, ddl in tabelas:
                    colunas = self._colunas(nome)
                    lista = ", ".join('"' + c.replace('"', '""') + '"' for c in colunas)
                    if ddl and not re.search(r"\bAS\s+SELECT\b", ddl, re.I):
                        alvo.execute(ddl)
                    else:
                        alvo.execute(f'CREATE TABLE "{nome}" ({lista})')
                    linhas = self._cru(f'SELECT {lista} FROM {self._qual(nome)}') or []
                    if linhas:
                        alvo.executemany(
                            f'INSERT INTO "{nome}" ({lista}) VALUES ({", ".join("?" * len(colunas))})',
                            [tuple(_valor_do_banco(v) for v in x) for x in linhas])
                for ddl in indices + visoes:
                    alvo.execute(ddl)
                versao = self._cru("SELECT valor FROM cg_meta WHERE chave='user_version'")
                if versao:
                    alvo.execute(f"PRAGMA user_version={int(versao[0][0])}")
                alvo.commit()
            except BaseException:
                alvo.rollback()
                raise
        except psycopg.Error as erro:
            raise _traduzir_erro(erro) from erro
        finally:
            alvo.execute(f"PRAGMA foreign_keys={int(fk)}")

    def _copiar_para_schema(self, destino: "Conexao") -> None:
        origem, alvo = self.schema, destino.schema
        if origem == alvo:
            return
        de, para = f'"{origem}".', f'"{alvo}".'
        apoio = ("cg_meta", "cg_ddl", "cg_fk_pendentes")

        def trocar(texto: str) -> str:  # o catálogo qualifica o schema de origem
            return texto.replace(de, para).replace(f"{origem}.", para)

        if destino._em_transacao:
            destino.commit()
        destino._comecar(True)
        try:
            cru = destino._cru
            for nome, tipo in cru(
                    "SELECT c.relname, c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = %s AND c.relkind IN ('r', 'p', 'v', 'm') AND c.relname <> ALL(%s) "
                    "ORDER BY c.relkind DESC", (alvo, list(apoio) + ["sqlite_master", "sqlite_sequence"])) or []:
                tipo_sql = {"v": "VIEW", "m": "MATERIALIZED VIEW"}.get(tipo, "TABLE")
                cru(f'DROP {tipo_sql} IF EXISTS {para}"{nome}" CASCADE')
            tabelas = [x[0] for x in cru(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = %s AND c.relkind IN ('r', 'p') AND c.relname <> ALL(%s) "
                "ORDER BY c.relname", (origem, list(apoio))) or []]
            for t in tabelas:
                cru(f'CREATE TABLE {para}"{t}" (LIKE {de}"{t}" INCLUDING DEFAULTS INCLUDING IDENTITY '
                    f'INCLUDING GENERATED INCLUDING CONSTRAINTS)')
                lista = ", ".join('"' + c[0].replace('"', '""') + '"' for c in cru(
                    "SELECT attname FROM pg_attribute WHERE attrelid = to_regclass(%s) "
                    "AND attnum > 0 AND NOT attisdropped AND attgenerated = '' ORDER BY attnum",
                    (f'{de}"{t}"',)) or [])
                cru(f'INSERT INTO {para}"{t}" ({lista}) OVERRIDING SYSTEM VALUE SELECT {lista} FROM {de}"{t}"')
            for t in apoio:
                cru(f'DELETE FROM {para}"{t}"')
                cru(f'INSERT INTO {para}"{t}" OVERRIDING SYSTEM VALUE SELECT * FROM {de}"{t}"')
            # índices e chaves com o MESMO nome (o sqlite_master os acha pelo nome)
            for t, indice, chave, definicao in cru(
                    "SELECT t.relname, pg_get_indexdef(x.indexrelid), k.conname, pg_get_constraintdef(k.oid) "
                    "FROM pg_index x JOIN pg_class t ON t.oid = x.indrelid "
                    "JOIN pg_namespace n ON n.oid = t.relnamespace "
                    "LEFT JOIN pg_constraint k ON k.conindid = x.indexrelid AND k.conrelid = t.oid "
                    " AND k.contype IN ('p', 'u', 'x') "
                    "WHERE n.nspname = %s AND t.relkind IN ('r', 'p') AND t.relname <> ALL(%s) "
                    "ORDER BY x.indisprimary DESC, x.indexrelid", (origem, list(apoio))) or []:
                if chave:
                    cru(f'ALTER TABLE {para}"{t}" ADD CONSTRAINT "{chave}" {trocar(definicao)}')
                else:
                    cru(trocar(indice))
            for t, chave, definicao in cru(
                    "SELECT c.relname, k.conname, pg_get_constraintdef(k.oid) FROM pg_constraint k "
                    "JOIN pg_class c ON c.oid = k.conrelid JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = %s AND k.contype = 'f' ORDER BY k.oid", (origem,)) or []:
                cru(f'ALTER TABLE {para}"{t}" ADD CONSTRAINT "{chave}" {trocar(definicao)}')
            for t, coluna in cru(
                    "SELECT c.relname, a.attname FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = %s "
                    "AND a.attidentity IN ('a', 'd') AND NOT a.attisdropped", (alvo,)) or []:
                cru(f"SELECT setval(pg_get_serial_sequence(%s, %s), "
                    f'COALESCE((SELECT MAX("{coluna}") FROM {para}"{t}"), 0) + 1, false)',
                    (f'{para}"{t}"', coluna))
            for v, corpo in cru(
                    "SELECT c.relname, pg_get_viewdef(c.oid) FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = %s "
                    "AND c.relkind = 'v' AND c.relname NOT IN ('sqlite_master', 'sqlite_sequence') "
                    "ORDER BY c.oid", (origem,)) or []:
                cru(f'CREATE VIEW {para}"{v}" AS {trocar(corpo)}')
        except psycopg.Error as erro:
            destino.rollback()
            raise _traduzir_erro(erro) from erro
        except BaseException:
            destino.rollback()
            raise
        destino.commit()
        destino._esquecer()

    def _receber_de_sqlite(self, origem: sqlite3.Connection, **kw) -> None:
        """`sqlite3.connect(x).backup(sqlite3.connect(y))` com `y` caindo aqui
        porque o NOME é o do banco da casa (o instantâneo do backup.py se chama
        `cartorio_gestao.sqlite3`). Cópia é ARQUIVO — a mesma regra do
        `VACUUM INTO` e do `backup_database`, que viram pg_dump em disco —, e
        o schema deste caminho está vazio: grava o arquivo SQLite. Se o schema
        tem tabelas, isto seria restaurar uma cópia SQLite por cima do banco
        da casa no PostgreSQL: recusa à vista, nunca calado."""
        if self._cru("SELECT 1 FROM sqlite_master WHERE type = 'table' LIMIT 1"):
            raise OperationalError(
                "Restaurar uma cópia SQLite por cima do banco no PostgreSQL não é "
                "feito pelo .backup(): use a importação do banco.")
        arquivo = _CONNECT_ORIGINAL(_caminho_e_modo(self.db_path)[0])
        try:
            sqlite3.Connection.backup(origem, arquivo, **kw)
        finally:
            arquivo.close()

    def iterdump(self):  # pragma: no cover
        raise OperationalError("iterdump não existe no PostgreSQL: use o pg_dump.")

    def __enter__(self):
        return self

    def __exit__(self, tipo, valor, tb):
        try:
            if tipo is None:
                self.commit()
            else:
                self.rollback()
        finally:
            if self._fechar_no_with:
                self.close()
        return False

    # -- por dentro
    def _cru(self, sql: str, parametros: Any = None):
        if self._fechada:
            raise ProgrammingError("Cannot operate on a closed database.")
        with self._pg.cursor() as c:
            c.execute(sql, parametros)
            self._anotar(c, sql, parametros)
            return c.fetchall() if c.description else None

    def _anotar(self, c, sql: str, parametros: Any) -> None:
        """Durante a gravação da criação de um banco novo, guarda o comando que
        deu certo, já com os valores dentro (ver `criar_por_reproducao`)."""
        if _GRAVACAO["schema"] != self.schema:
            return
        if _RE_NAO_GRAVA.match(sql):
            return
        # cursor à parte: o mogrify no cursor do comando apaga o resultado dele
        texto = (psycopg.ClientCursor(self._pg).mogrify(sql, parametros)
                 if parametros not in (None, (), []) else sql)
        _GRAVACAO["linhas"].append(texto)

    def _comecar(self, imediata: bool) -> None:
        nova = not self._em_transacao
        if nova:
            self._cru("BEGIN")
            self._em_transacao = True
            self._travada = False
        if imediata and not self._travada:
            # A TRAVA QUE NÃO VEM (lock_timeout do busy_timeout) é o «database
            # is locked» do SQLite: sobe traduzida — o LockNotAvailable cru
            # ninguém apanha como sqlite3.OperationalError (achado do P04 em
            # test_disputa_de_escrita). Transação aberta aqui volta atrás, como
            # o BEGIN IMMEDIATE que não abre; a que já vinha aberta continua
            # viva (o SAVEPOINT impede o PostgreSQL de condená-la inteira).
            try:
                if not nova:
                    self._cru("SAVEPOINT cg_trava")
                self._cru("SELECT pg_advisory_xact_lock(%s)", (self._chave_trava,))
                if not nova:
                    self._cru("RELEASE SAVEPOINT cg_trava")
            except psycopg.Error as erro:
                try:
                    self._cru("ROLLBACK" if nova else "ROLLBACK TO SAVEPOINT cg_trava")
                    if not nova:
                        self._cru("RELEASE SAVEPOINT cg_trava")
                except psycopg.Error:
                    pass
                if nova:
                    self._em_transacao = False
                raise _traduzir_erro(erro) from erro
            self._travada = True

    def _ponto_de_retorno(self, texto: str) -> None:
        """SAVEPOINT, RELEASE ou ROLLBACK TO de quem chama — fora do `cg_sp`.

        O SAVEPOINT DE QUEM CHAMA MORRIA NA HORA (LX01, 19/10/2026). Ele ia pelo
        `_rodar`, que põe cada comando dentro do `cg_sp` e o solta no fim — e o
        RELEASE de um savepoint leva junto todo savepoint aberto depois dele. O
        ROLLBACK TO seguinte estourava com «savepoint "x" does not exist», e
        quem desfazia por savepoint a recusa da lavratura do RCPN não desfazia
        nada. O L056R tinha contornado isso só no termo pelo modelo
        (`atribuicoes_web._ponto_de_retorno`); aqui é a raiz.

        RELEASE E ROLLBACK TO CONTINUAM PROTEGIDOS: nome que não existe é erro
        que, no SQLite, não derruba a transação. O `cg_sp` abre ANTES do
        comando; quando o comando dá certo, o próprio PostgreSQL apaga o `cg_sp`
        junto (foi aberto depois do savepoint de quem chama), e só no erro se
        volta a ele. O SAVEPOINT vai cru: não há o que proteger.

        A TRAVA ÚNICA SE PEDE DE NOVO depois do ROLLBACK TO: a trava de
        transação pega depois do savepoint é solta pelo PostgreSQL junto com o
        resto (medido em 19/10/2026), e a escrita seguinte não pode contar com
        ela. Pedir outra vez a que ainda se tem não custa nada.
        """
        verbo = texto.split(None, 1)[0].upper()
        try:
            with self._pg.cursor() as c:
                if verbo == "SAVEPOINT":
                    c.execute(texto)
                    return
                c.execute("SAVEPOINT cg_sp")
                try:
                    c.execute(texto)
                except psycopg.Error:
                    c.execute("ROLLBACK TO SAVEPOINT cg_sp")
                    c.execute("RELEASE SAVEPOINT cg_sp")
                    raise
        except psycopg.Error as erro:
            raise _traduzir_erro(erro) from erro
        if verbo == "ROLLBACK":
            self._travada = False

    def _executar(self, cur: Cursor, sql: str, parametros: Any, *,
                  em_lote: bool = False, de_script: bool = False) -> None:
        if self._fechada:
            raise ProgrammingError("Cannot operate on a closed database.")
        if not isinstance(sql, str):
            raise ProgrammingError("O comando SQL tem de ser texto.")
        texto = _sem_comentario_na_frente(sql)
        if not texto:
            cur._carregar((), [], -1)
            return
        # comandos de transação
        m = _RE_BEGIN.match(texto)
        if m:
            if self._em_transacao:
                raise OperationalError("cannot start a transaction within a transaction")
            self._comecar((m.group("modo") or "").upper() in ("IMMEDIATE", "EXCLUSIVE"))
            cur._carregar((), [], -1)
            return
        m = _RE_FIM.match(texto)
        if m:
            if m.group("acao").upper() == "ROLLBACK":
                self.rollback()
            else:
                self.commit()
            cur._carregar((), [], -1)
            return
        if re.match(r"^\s*(SAVEPOINT|RELEASE|ROLLBACK\s+TO)\b", texto, re.I):
            if not self._em_transacao:
                self._comecar(False)
            self._ponto_de_retorno(texto)
            cur._carregar((), [], -1)
            return
        m = _RE_PRAGMA.match(texto)
        if m:
            self._pragma(cur, m.group("nome").lower(), m.group("valor"), m.group("arg"))
            return
        m = re.match(r"^\s*VACUUM\s+(?:main\s+)?INTO\s+\?\s*;?\s*$", texto, re.I)
        if m:
            # A CÓPIA ANTES DE GRAVAR não pode virar nada calado: o script
            # seguiria achando que tem cópia. Vira um pg_dump do schema.
            # SÓ A FORMA COM `?` (27/10/2026): a forma com o caminho escrito no
            # SQL (`VACUUM INTO 'x'`) tirava o destino do pg_dump do texto do
            # comando, e ninguém a usa (alerta do CodeQL).
            destino = parametros[0] if isinstance(parametros, (list, tuple)) else None
            if not destino:
                raise OperationalError("VACUUM INTO sem destino")
            copiar_para_arquivo(self.db_path, destino)
            cur._carregar((), [], -1)
            return
        if (texto.lstrip()[:6].upper() == "VACUUM"
                and "INTO" in texto.upper().split()):
            # A cópia com o caminho no texto não cai no «não faz nada» abaixo.
            raise OperationalError("VACUUM INTO só com o destino em parâmetro: "
                                   "con.execute(\"VACUUM INTO ?\", (destino,))")
        if re.match(r"^\s*(VACUUM|ANALYZE|REINDEX|ATTACH|DETACH)\b", texto, re.I):
            cur._carregar((), [], -1)
            return
        if _RE_CREATE_TABLE.match(texto):
            self._criar_tabela(cur, texto)
            return
        m = _RE_DROP_TABLE.match(texto)
        if m:
            self._apagar_tabela(cur, m.group("nome"), bool(m.group("se")))
            return
        m = _RE_ALTER_ADD.match(texto)
        if m and not re.match(r"^\s*(CONSTRAINT|PRIMARY|UNIQUE|FOREIGN|CHECK)\b",
                              m.group("def"), re.I):
            self._adicionar_coluna(cur, m.group("nome"), m.group("def"), texto)
            return
        if _RE_CREATE_INDEX.match(texto):
            self._criar_indice(cur, texto)
            return
        if re.match(r"^\s*CREATE\s+(?:TEMP(?:ORARY)?\s+)?VIEW\b", texto, re.I):
            self._criar_visao(cur, texto)
            return
        if re.match(r"^\s*CREATE\s+TRIGGER\b", texto, re.I):
            raise OperationalError("gatilho (TRIGGER) do SQLite não é traduzido: "
                                   "reescreva-o para o PostgreSQL.")
        # escrita: transação implícita, como o sqlite3 legado
        verbo = texto.split(None, 1)[0].upper()
        escrita = verbo in _PALAVRAS_DE_ESCRITA or (
            verbo == "WITH" and re.search(r"\b(INSERT|UPDATE|DELETE)\b", texto, re.I))
        if escrita and not de_script:
            self._comecar(True)
        elif escrita and de_script:
            pass  # executescript roda em modo automático, como no sqlite3
        nomeados = isinstance(parametros, Mapping)
        traduzido, extra = self._traduzir_dml(texto) if verbo in (
            "INSERT", "REPLACE") else (texto, None)
        traduzido = _trocar_no_codigo(traduzido, _RE_TROCAS_DE_CODIGO + _RE_TROCAS_SO_DML)
        traduzido = _nulos_como_sqlite(traduzido)
        traduzido = _glob_como_regex(traduzido)
        traduzido = _cast_inteiro_como_sqlite(traduzido)
        valores = None
        if parametros not in (None, (), []) or nomeados:
            traduzido = _parametros(traduzido, nomeados)
            if nomeados:
                valores = {k: _valor_para_o_banco(v) for k, v in parametros.items()}
            else:
                valores = [_valor_para_o_banco(v) for v in parametros]
        self._rodar(cur, traduzido, valores, insercao=extra)

    def _rodar(self, cur: Cursor, sql: str, valores: Any, *, insercao: dict | None = None) -> None:
        """Roda um comando. Dentro de transação, cada comando vai num
        SAVEPOINT: no SQLite um comando que falha NÃO derruba a transação, e o
        código conta com isso (try/except em volta de um INSERT)."""
        protege = self._em_transacao
        try:
            with self._pg.cursor() as c:
                if protege:
                    c.execute("SAVEPOINT cg_sp")
                try:
                    c.execute(sql, valores)
                except psycopg.Error as erro:
                    if protege:
                        c.execute("ROLLBACK TO SAVEPOINT cg_sp")
                    # A NUMERAÇÃO AUTOMÁTICA FICOU ATRÁS: no SQLite o próximo id
                    # é sempre o maior + 1; no PostgreSQL a sequência não anda
                    # quando alguém grava o id à mão (cargas, testes). Na
                    # primeira colisão da chave, ela é posta no maior id e o
                    # comando roda de novo — uma vez só.
                    if not self._acertar_sequencia(c, erro, insercao):
                        if protege:
                            c.execute("RELEASE SAVEPOINT cg_sp")
                        raise
                    try:
                        c.execute(sql, valores)
                    except psycopg.Error:
                        if protege:
                            c.execute("ROLLBACK TO SAVEPOINT cg_sp")
                            c.execute("RELEASE SAVEPOINT cg_sp")
                        raise
                self._anotar(c, sql, valores)
                linhas = c.fetchall() if c.description else []
                nomes = [d.name for d in c.description] if c.description else []
                afetadas = c.rowcount
                if protege:
                    c.execute("RELEASE SAVEPOINT cg_sp")
        except psycopg.Error as erro:
            raise _traduzir_erro(erro) from erro
        if insercao is not None:
            # a inserção pediu RETURNING da identidade: o resultado é o lastrowid
            if insercao.get("retorno") and linhas:
                self._ultimo_id = linhas[-1][0]
            cur.lastrowid = self._ultimo_id if afetadas else cur.lastrowid or self._ultimo_id
            if insercao.get("retorno"):
                linhas, nomes = [], []
            if afetadas and afetadas > 0:
                self.total_changes += afetadas
            cur._carregar(nomes, linhas, afetadas)
            return
        primeira = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ""
        if primeira in ("UPDATE", "DELETE") and afetadas and afetadas > 0:
            self.total_changes += afetadas
        cur._carregar(nomes, linhas, afetadas if primeira in ("UPDATE", "DELETE", "INSERT") else -1)

    def _acertar_sequencia(self, c, erro, insercao: dict | None) -> bool:
        if not insercao or not insercao.get("identidade") or insercao.get("id_explicito"):
            return False
        if not isinstance(erro, _pgerr.UniqueViolation):
            return False
        tabela, coluna = insercao["tabela"], insercao["identidade"]
        nome = getattr(getattr(erro, "diag", None), "constraint_name", "") or ""
        if nome and not nome.endswith("_pkey"):
            return False
        c.execute(
            f"SELECT setval(pg_get_serial_sequence(%s, %s), "
            f'COALESCE((SELECT MAX("{coluna}") FROM "{tabela}"), 0) + 1, false)',
            (f'"{self.schema}"."{tabela}"', coluna))
        return True

    # -- INSERT/REPLACE: OR IGNORE, OR REPLACE e o lastrowid
    def _identidade(self, tabela: str) -> str | None:
        if tabela not in self._cache_identidade:
            r = self._cru(
                "SELECT a.attname FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema() "
                "AND c.relname=%s AND a.attidentity IN ('a','d') AND NOT a.attisdropped",
                (tabela,))
            self._cache_identidade[tabela] = r[0][0] if r else None
        return self._cache_identidade[tabela]

    def _chaves_unicas(self, tabela: str) -> list[list[str]]:
        if tabela not in self._cache_chaves:
            r = self._cru(
                "SELECT i.indisprimary, array_agg(a.attname ORDER BY k.ord) "
                "FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY k(attnum, ord) "
                "JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum "
                "WHERE n.nspname=current_schema() AND c.relname=%s AND i.indisunique "
                "AND i.indpred IS NULL GROUP BY i.indexrelid, i.indisprimary "
                "ORDER BY i.indisprimary DESC", (tabela,))
            self._cache_chaves[tabela] = [list(x[1]) for x in (r or [])]
        return self._cache_chaves[tabela]

    def _qual(self, tabela: str) -> str:
        return '"' + self.schema + '"."' + tabela.replace('"', '""') + '"'

    def _colunas(self, tabela: str) -> list[str]:
        if tabela not in self._cache_colunas:
            r = self._cru(
                "SELECT a.attname FROM pg_attribute a WHERE a.attrelid = to_regclass(%s) "
                "AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum",
                (self._qual(tabela),))
            self._cache_colunas[tabela] = [x[0] for x in (r or [])]
        return self._cache_colunas[tabela]

    def _esquecer(self, tabela: str | None = None) -> None:
        for cache in (self._cache_identidade, self._cache_chaves, self._cache_colunas):
            if tabela is None:
                cache.clear()
            else:
                cache.pop(tabela, None)

    def _traduzir_dml(self, texto: str) -> tuple[str, dict]:
        m = _RE_INSERT.match(texto)
        if not m:
            return texto, {}
        verbo = re.sub(r"\s+", " ", m.group("verbo").upper())
        tabela = _nome(m.group("nome"))
        cols = ([_nome(c) for c in m.group("cols")[1:-1].split(",")]
                if m.group("cols") else self._colunas(tabela))
        corpo = "INSERT INTO" + texto[m.end("verbo") + len(texto[m.end("verbo"):]) - len(texto[m.end("verbo"):]):]
        # tira o verbo antigo e põe INSERT INTO
        resto = texto[m.end("verbo"):]
        resto = re.sub(r"^\s+INTO\b", "", resto, count=1, flags=re.I)
        corpo = "INSERT INTO" + resto
        tem_conflito = bool(re.search(r"\bON\s+CONFLICT\b", texto, re.I))
        tem_retorno = bool(re.search(r"\bRETURNING\b", texto, re.I))
        sufixo = ""
        if verbo == "INSERT OR IGNORE" and not tem_conflito:
            sufixo = " ON CONFLICT DO NOTHING"
        elif verbo in ("INSERT OR REPLACE", "REPLACE") and not tem_conflito:
            chave = None
            for k in self._chaves_unicas(tabela):
                if set(k) <= set(cols):
                    chave = k
                    break
            if chave:
                outras = [c for c in cols if c not in chave]
                # O REPLACE do SQLite APAGA a linha e insere de novo: a coluna
                # que o comando não lista volta ao padrão. Sem isto, o erro novo
                # ficaria ao lado do resultado velho (achado do lote L6 em
                # gestor_leitura/gestor_expedientes). O id fica — muda menos.
                identidade = self._identidade(tabela)
                omitidas = [c for c in self._colunas(tabela)
                            if c not in cols and c not in chave and c != identidade]
                if outras or omitidas:
                    sufixo = (f" ON CONFLICT ({', '.join(chave)}) DO UPDATE SET "
                              + ", ".join([f'"{c}" = EXCLUDED."{c}"' for c in outras]
                                          + [f'"{c}" = DEFAULT' for c in omitidas]))
                else:
                    sufixo = f" ON CONFLICT ({', '.join(chave)}) DO NOTHING"
            else:
                sufixo = " ON CONFLICT DO NOTHING"
        retorno = None
        if not tem_retorno:
            retorno = self._identidade(tabela)
        if sufixo or retorno:
            corpo = corpo.rstrip().rstrip(";")
            if sufixo:
                corpo += sufixo
            if retorno:
                corpo += f' RETURNING "{retorno}"'
        identidade = self._identidade(tabela)
        return corpo, {"retorno": bool(retorno), "tabela": tabela, "identidade": identidade,
                       "id_explicito": bool(identidade and identidade in cols)}

    # -- DDL
    def _registrar_ddl(self, nome: str, tipo: str, tabela: str, sql: str) -> None:
        self._cru("INSERT INTO cg_ddl(nome, tipo, tabela, sql) VALUES (%s, %s, %s, %s) "
                  "ON CONFLICT (nome) DO UPDATE SET sql = EXCLUDED.sql, tipo = EXCLUDED.tipo, "
                  "tabela = EXCLUDED.tabela", (nome, tipo, tabela, sql))

    def _criar_tabela(self, cur: Cursor, texto: str) -> None:
        m = _RE_CREATE_TABLE.match(texto)
        tabela = _nome(m.group("nome"))
        if re.search(r"\bAS\s+SELECT\b", texto, re.I) and "(" not in texto[m.end():m.end() + 3]:
            self._rodar(cur, _trocar_no_codigo(texto, _RE_TROCAS_DE_CODIGO), None)
            self._registrar_ddl(tabela, "table", tabela, texto)
            self._esquecer(tabela)
            return
        abre = texto.index("(", m.end())
        fecha = texto.rindex(")")
        corpo, cauda = texto[abre + 1:fecha], texto[fecha + 1:]
        definicoes, fks = [], []
        for parte in _partir_colunas(corpo):
            if re.match(r"^\s*(CONSTRAINT\s+\w+\s+)?FOREIGN\s+KEY\b", parte, re.I):
                fks.append(parte)
                continue
            fk = _RE_FK_INLINE.search(parte)
            if fk and not re.match(r"^\s*(CONSTRAINT|PRIMARY|UNIQUE|CHECK)\b", parte, re.I):
                coluna = parte.split(None, 1)[0]
                alvo_cols = f"({fk.group('cols')})" if fk.group("cols") else ""
                fks.append(f"FOREIGN KEY ({coluna}) REFERENCES {fk.group('alvo')}{alvo_cols}"
                           f"{fk.group('resto') or ''}")
                parte = parte[:fk.start()] + parte[fk.end():]
            definicoes.append(self._definicao_de_coluna(parte))
        cauda = re.sub(r"\bWITHOUT\s+ROWID\b|\bSTRICT\b", "", cauda, flags=re.I)
        novo = texto[:abre + 1] + ",\n  ".join(definicoes) + ")" + cauda
        novo = re.sub(r"^\s*CREATE\s+TEMP(?:ORARY)?\s+TABLE", "CREATE TEMP TABLE", novo, flags=re.I)
        existia = self._cru("SELECT to_regclass(%s)", (self._qual(tabela),))[0][0]
        self._rodar(cur, novo, None)
        self._esquecer(tabela)
        if not existia:
            self._registrar_ddl(tabela, "table", tabela, texto)
            for fk in fks:
                nome_fk = "fk_" + hashlib.sha1((tabela + fk).encode()).hexdigest()[:10]
                comando = f'ALTER TABLE "{tabela}" ADD CONSTRAINT {nome_fk} {fk} NOT VALID'
                self._cru("INSERT INTO cg_fk_pendentes(tabela, comando) VALUES (%s, %s)",
                          (tabela, comando))
            if fks:
                self._tentar_fks_pendentes()

    def _apagar_tabela(self, cur: Cursor, nome_tab: str, se_existir: bool) -> None:
        """`DROP TABLE` como o do SQLite, que apaga a tabela mesmo com outra
        apontando para ela (a FK da outra fica lá, à espera). O PostgreSQL
        recusa sem CASCADE — e o CASCADE leva a FK da outra tabela junto. Por
        isso ela vai, antes, para `cg_fk_pendentes`: quando a tabela voltar a
        existir, a FK volta com ela (`_tentar_fks_pendentes`). Visão que
        dependa da tabela também cai — no SQLite ela ficaria, quebrada."""
        tabela = _nome(nome_tab.strip("`"))
        fks = self._cru(
            "SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid) "
            "FROM pg_constraint WHERE contype = 'f' AND confrelid = to_regclass(%s) "
            "AND conrelid <> confrelid ORDER BY oid", (self._qual(tabela),)) or []
        comando = f'DROP TABLE {"IF EXISTS " if se_existir else ""}"{tabela}" CASCADE'
        propria = bool(fks) and not self._em_transacao
        if propria:
            self._comecar(False)
        try:
            self._rodar(cur, comando, None)
            for filha, nome_fk, definicao in fks:
                if "NOT VALID" not in definicao.upper():
                    definicao += " NOT VALID"
                self._cru("INSERT INTO cg_fk_pendentes(tabela, comando, erro) VALUES (%s, %s, %s)",
                          (filha, f'ALTER TABLE {filha} ADD CONSTRAINT "{nome_fk}" {definicao}',
                           f"falta: {tabela} (DROP TABLE)"))
        except BaseException:
            if propria:
                self.rollback()
            raise
        if propria:
            self.commit()
        self._esquecer()

    def _definicao_de_coluna(self, parte: str) -> str:
        if re.match(r"^\s*(CONSTRAINT|PRIMARY|UNIQUE|CHECK)\b", parte, re.I):
            return _trocar_no_codigo(parte, _RE_TROCAS_DE_CODIGO)
        nome, _, resto = parte.strip().partition(" ")
        resto = resto.strip()
        if not resto or re.match(r"^(NOT\s+NULL|NULL|DEFAULT|PRIMARY|UNIQUE|CHECK|REFERENCES|COLLATE)\b",
                                 resto, re.I):
            resto = "TEXT " + resto  # coluna sem tipo no SQLite
        resto = _trocar_no_codigo(resto, _RE_TIPOS_DDL)
        resto = self._defaults(resto)
        resto = _trocar_no_codigo(resto, _RE_TROCAS_DE_CODIGO)
        return f"{nome} {resto}"

    @staticmethod
    def _defaults(resto: str) -> str:
        """`DEFAULT CURRENT_TIMESTAMP` → texto no formato do SQLite; default
        entre parênteses com função do SQLite fica (as funções existem no PG)."""
        resto = re.sub(r"\bDEFAULT\s+CURRENT_TIMESTAMP\b", "DEFAULT cg_agora_texto()", resto, flags=re.I)
        resto = re.sub(r"\bDEFAULT\s+CURRENT_DATE\b", "DEFAULT cg_hoje_texto()", resto, flags=re.I)
        resto = re.sub(r"\bDEFAULT\s+CURRENT_TIME\b", "DEFAULT cg_hora_texto()", resto, flags=re.I)
        return resto

    def _adicionar_coluna(self, cur: Cursor, nome_tab: str, definicao: str, original: str) -> None:
        tabela = _nome(nome_tab)
        fk = _RE_FK_INLINE.search(definicao)
        fk_txt = None
        if fk:
            coluna = definicao.split(None, 1)[0]
            alvo_cols = f"({fk.group('cols')})" if fk.group("cols") else ""
            fk_txt = (f"FOREIGN KEY ({coluna}) REFERENCES {fk.group('alvo')}{alvo_cols}"
                      f"{fk.group('resto') or ''}")
            definicao = definicao[:fk.start()] + definicao[fk.end():]
        nova = self._definicao_de_coluna(definicao)
        self._rodar(cur, f'ALTER TABLE "{tabela}" ADD COLUMN {nova}', None)
        self._esquecer(tabela)
        linha = self._cru("SELECT sql FROM cg_ddl WHERE nome=%s", (tabela,))
        if linha and linha[0][0]:
            antigo = linha[0][0]
            k = antigo.rstrip().rstrip(";").rstrip()
            if k.endswith(")"):
                self._registrar_ddl(tabela, "table", tabela, k[:-1].rstrip() + ", " + definicao.strip() + ")")
        if fk_txt:
            nome_fk = "fk_" + hashlib.sha1((tabela + fk_txt).encode()).hexdigest()[:10]
            self._cru("INSERT INTO cg_fk_pendentes(tabela, comando) VALUES (%s, %s)",
                      (tabela, f'ALTER TABLE "{tabela}" ADD CONSTRAINT {nome_fk} {fk_txt} NOT VALID'))
            self._tentar_fks_pendentes()

    def _criar_indice(self, cur: Cursor, texto: str) -> None:
        novo = _trocar_no_codigo(texto, _RE_TROCAS_DE_CODIGO)
        # ILIKE não existe em índice; e o LIKE não deveria estar num índice
        self._rodar(cur, novo, None)
        m = re.search(r"\bINDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(\"[^\"]+\"|\w+)\s+ON\s+(\"[^\"]+\"|\w+)",
                      texto, re.I)
        if m:
            self._registrar_ddl(_nome(m.group(1)), "index", _nome(m.group(2)), texto)
            self._esquecer(_nome(m.group(2)))

    def _criar_visao(self, cur: Cursor, texto: str) -> None:
        novo = _trocar_no_codigo(texto, _RE_TROCAS_DE_CODIGO)
        novo = re.sub(r"^\s*CREATE\s+(?:TEMP(?:ORARY)?\s+)?VIEW\s+IF\s+NOT\s+EXISTS\s+",
                      "CREATE OR REPLACE VIEW ", novo, flags=re.I)
        self._rodar(cur, novo, None)
        m = re.search(r"\bVIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(\"[^\"]+\"|\w+)", texto, re.I)
        if m:
            self._registrar_ddl(_nome(m.group(1)), "view", _nome(m.group(1)), texto)

    def _tentar_fks_pendentes(self) -> None:
        """As FKs entram quando a tabela de destino existe (o SQLite aceita
        referência adiante; o PostgreSQL não). Entram NOT VALID: dado antigo
        órfão não impede a criação, e o dado novo é conferido."""
        try:
            pendentes = self._cru("SELECT id, comando FROM cg_fk_pendentes WHERE erro IS NULL OR erro LIKE 'falta:%%' ORDER BY id") or []
        except psycopg.Error:
            return
        protege = self._em_transacao
        for ident, comando in pendentes:
            try:
                if protege:
                    self._cru("SAVEPOINT cg_fk")
                try:
                    self._cru(comando)
                except psycopg.Error:
                    if protege:
                        self._cru("ROLLBACK TO SAVEPOINT cg_fk")
                    raise
                finally:
                    if protege:
                        self._cru("RELEASE SAVEPOINT cg_fk")
                self._cru("DELETE FROM cg_fk_pendentes WHERE id=%s", (ident,))
            except psycopg.errors.UndefinedTable as erro:
                self._cru("UPDATE cg_fk_pendentes SET erro=%s WHERE id=%s", ("falta: " + str(erro)[:200], ident))
            except psycopg.errors.DuplicateObject:
                self._cru("DELETE FROM cg_fk_pendentes WHERE id=%s", (ident,))
            except psycopg.Error as erro:
                self._cru("UPDATE cg_fk_pendentes SET erro=%s WHERE id=%s", (str(erro)[:300], ident))

    # -- PRAGMA
    def _pragma(self, cur: Cursor, nome: str, valor: str | None, arg: str | None) -> None:
        alvo = _nome(arg) if arg else ""
        if nome in ("table_info", "table_xinfo"):
            r = self._cru(
                "SELECT (row_number() OVER (ORDER BY a.attnum)) - 1, a.attname, "
                "format_type(a.atttypid, a.atttypmod), CASE WHEN a.attnotnull THEN 1 ELSE 0 END, "
                "pg_get_expr(d.adbin, d.adrelid), "
                "COALESCE(array_position(p.indkey::int2[], a.attnum), 0) "
                "FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum "
                "LEFT JOIN pg_index p ON p.indrelid = a.attrelid AND p.indisprimary "
                "WHERE a.attrelid = to_regclass(%s) AND a.attnum > 0 AND NOT a.attisdropped "
                "ORDER BY a.attnum", (self._qual(alvo),)) or []
            linhas = []
            for cid, col, tipo, notnull, dflt, pk in r:
                padrao = dflt
                if padrao and "nextval(" in padrao:
                    padrao = None
                base = tipo.split("(")[0].strip()
                linhas.append((cid, col, _TIPO_DE_SQLITE.get(base, base.upper()), notnull,
                               _padrao_como_sqlite(padrao), int(pk)))
            nomes = ["cid", "name", "type", "notnull", "dflt_value", "pk"]
            if nome == "table_xinfo":
                nomes.append("hidden")
                linhas = [x + (0,) for x in linhas]
            cur._carregar(nomes, linhas, -1)
            return
        if nome == "index_list":
            r = self._cru(
                "SELECT row_number() OVER () - 1, i.relname, CASE WHEN x.indisunique THEN 1 ELSE 0 END, "
                "CASE WHEN x.indisprimary THEN 'pk' ELSE 'c' END, CASE WHEN x.indpred IS NULL THEN 0 ELSE 1 END "
                "FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid JOIN pg_class t ON t.oid = x.indrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace WHERE n.nspname = current_schema() "
                "AND t.relname = %s", (alvo,)) or []
            cur._carregar(["seq", "name", "unique", "origin", "partial"], r, -1)
            return
        if nome in ("index_info", "index_xinfo"):
            r = self._cru(
                "SELECT k.ord - 1, a.attnum - 1, a.attname FROM pg_class i "
                "JOIN pg_namespace n ON n.oid = i.relnamespace JOIN pg_index x ON x.indexrelid = i.oid "
                "CROSS JOIN LATERAL unnest(x.indkey) WITH ORDINALITY k(attnum, ord) "
                "JOIN pg_attribute a ON a.attrelid = x.indrelid AND a.attnum = k.attnum "
                "WHERE n.nspname = current_schema() AND i.relname = %s ORDER BY k.ord", (alvo,)) or []
            cur._carregar(["seqno", "cid", "name"], r, -1)
            return
        if nome == "foreign_key_list":
            r = self._cru(
                "SELECT row_number() OVER () - 1, 0, ccu.table_name, kcu.column_name, ccu.column_name, "
                "rc.update_rule, rc.delete_rule, 'NONE' "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name "
                " AND kcu.table_schema = tc.table_schema "
                "JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name "
                " AND ccu.table_schema = tc.table_schema "
                "JOIN information_schema.referential_constraints rc ON rc.constraint_name = tc.constraint_name "
                " AND rc.constraint_schema = tc.table_schema "
                "WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = current_schema() "
                "AND tc.table_name = %s", (alvo,)) or []
            cur._carregar(["id", "seq", "table", "from", "to", "on_update", "on_delete", "match"], r, -1)
            return
        if nome == "user_version":
            if valor is not None:
                self._cru("INSERT INTO cg_meta(chave, valor) VALUES ('user_version', %s) "
                          "ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor", (valor.strip(),))
                cur._carregar((), [], -1)
            else:
                r = self._cru("SELECT valor FROM cg_meta WHERE chave='user_version'")
                cur._carregar(["user_version"], [(int(r[0][0]) if r else 0,)], -1)
            return
        if nome in ("quick_check", "integrity_check"):
            cur._carregar([nome], [("ok",)], -1)
            return
        if nome == "foreign_key_check":
            cur._carregar(["table", "rowid", "parent", "fkid"], [], -1)
            return
        if nome == "database_list":
            cur._carregar(["seq", "name", "file"], [(0, "main", str(self.db_path))], -1)
            return
        if nome == "journal_mode":
            cur._carregar(["journal_mode"], [("wal",)], -1)
            return
        if nome == "foreign_keys" and valor is None:
            cur._carregar(["foreign_keys"], [(1,)], -1)
            return
        if nome == "busy_timeout":
            if valor is not None:
                try:
                    ms = int(str(valor).strip())
                    self._cru(f"SET lock_timeout = '{max(ms, 1)}ms'")
                except ValueError:
                    pass
            cur._carregar(["timeout"], [(15000,)], -1)
            return
        # foreign_keys=ON, synchronous, cache_size, temp_store, mmap_size,
        # wal_checkpoint, optimize, compile_options, recursive_triggers...
        cur._carregar((), [], -1)


# ---------------------------------------------- criar banco novo por reprodução
#
# POR QUE EXISTE: criar o esquema inteiro (≈400 tabelas e índices, mais as
# sementes) comando a comando leva ~25 s no PostgreSQL, contra ~1 s no SQLite;
# a suíte cria milhares de bancos novos. O primeiro banco novo de cada processo
# é GRAVADO (os comandos que deram certo, com os valores dentro), e os
# seguintes são criados REPRODUZINDO a gravação numa ida só ao servidor. Só
# vale para banco que ainda não existe — banco existente passa pelo
# `init_schema` de sempre, que é quem migra. `CG_PG_SEM_REPRODUCAO=1` desliga.

_GRAVACAO: dict[str, Any] = {"schema": None, "linhas": None}
_CRIACAO_GRAVADA: dict[str, Any] = {"schema": None, "linhas": None}
_RE_NAO_GRAVA = re.compile(
    r"^\s*(SAVEPOINT|RELEASE|ROLLBACK|BEGIN|COMMIT|SET\s+lock_timeout|"
    r"SELECT\s+pg_advisory|SELECT\s+pg_terminate)", re.I)


def schema_existe(db_path: Any) -> bool:
    schema = schema_do_caminho(db_path)
    with psycopg.connect(dsn(), autocommit=True) as pg, pg.cursor() as c:
        c.execute("SELECT to_regclass(%s)", (f'"{schema}"."cg_meta"',))
        return c.fetchone()[0] is not None


def comecar_gravacao(db_path: Any) -> None:
    if os.environ.get("CG_PG_SEM_REPRODUCAO", "").strip() == "1":
        return
    if _CRIACAO_GRAVADA["linhas"] is None and not _carregar_gravacao_compartilhada():
        _GRAVACAO["schema"] = schema_do_caminho(db_path)
        _GRAVACAO["linhas"] = []


def terminar_gravacao(deu_certo: bool) -> None:
    if _GRAVACAO["schema"] and deu_certo:
        _CRIACAO_GRAVADA["schema"] = _GRAVACAO["schema"]
        _CRIACAO_GRAVADA["linhas"] = list(_GRAVACAO["linhas"])
    _GRAVACAO["schema"] = None
    _GRAVACAO["linhas"] = None


def criar_por_reproducao(db_path: Any) -> bool:
    """Cria o banco novo reproduzindo a gravação. Devolve False quando não há
    gravação (aí quem chama roda o `init_schema` e grava)."""
    if os.environ.get("CG_PG_SEM_REPRODUCAO", "").strip() == "1":
        return False
    if not _CRIACAO_GRAVADA["linhas"]:
        _carregar_gravacao_compartilhada()
    linhas, origem = _CRIACAO_GRAVADA["linhas"], _CRIACAO_GRAVADA["schema"]
    if not linhas:
        return False
    con = Conexao(db_path)          # cria o schema e a sqlite_master
    try:
        destino = con.schema
        corpo = ";\n".join(x.replace(origem, destino) for x in linhas)
        with con._pg.cursor() as c:
            # UMA REPRODUÇÃO DE CADA VEZ: oito ao mesmo tempo disputavam o
            # catálogo e levavam até 27 minutos cada (medido pelo L6, 18h56).
            # E a fila não tem prazo (o lock_timeout de 15 s fazia quem
            # esperava a vez morrer com «database is locked» — L5, 20h).
            c.execute("SET lock_timeout = 0")
            c.execute("SELECT pg_advisory_lock(%s)", (_CHAVE_DA_REPRODUCAO,))
            try:
                c.execute("BEGIN;\n" + corpo + ";\nCOMMIT")
            finally:
                c.execute("SELECT pg_advisory_unlock(%s)", (_CHAVE_DA_REPRODUCAO,))
                c.execute("SET lock_timeout = '15s'")
    finally:
        con.close()
    return True


# ------------------------------------------------------------- a cópia

def binario_do_postgres(nome: str) -> Path:
    """O caminho de `pg_dump`, `pg_restore`… — em `CG_PG_BIN` ou no PATH."""
    import shutil
    pasta = (os.environ.get("CG_PG_BIN") or "").strip()
    exe = (Path(pasta) / (f"{nome}.exe" if os.name == "nt" else nome)) if pasta else None
    if not exe or not exe.exists():
        achado = shutil.which(nome)
        exe = Path(achado) if achado else None
    if not exe:
        raise OperationalError(f"{nome} não encontrado: defina CG_PG_BIN com a pasta bin do PostgreSQL.")
    return exe


def contar_linhas(c, schema: str) -> dict[str, int]:
    """Quantas linhas tem cada tabela do schema, pelo cursor recebido (e no
    instantâneo da transação dele). Só LÊ."""
    c.execute("SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
              "WHERE n.nspname = %s AND c.relkind IN ('r', 'p') ORDER BY c.relname", (schema,))
    tabelas = [linha[0] for linha in c.fetchall()]
    saida: dict[str, int] = {}
    for tabela in tabelas:
        c.execute(f"SELECT count(*) FROM {_nome_sql(schema)}.{_nome_sql(tabela)}")
        saida[tabela] = int(c.fetchone()[0])
    return saida


def copiar_para_arquivo(db_path: Any, destino: Any,
                        contagens: dict | None = None) -> Path:
    """O equivalente do `VACUUM INTO`/`.backup()`: um pg_dump do schema daquele
    banco, em formato próprio (-Fc). Procura o pg_dump em `CG_PG_BIN` ou no
    PATH.

    COM `contagens` (um dicionário), ele é preenchido com as linhas de cada
    tabela **no MESMO instantâneo do pg_dump** (26/10/2026): uma transação
    REPEATABLE READ exporta o instantâneo, conta, e o pg_dump o importa com
    `--snapshot`. Contar antes ou depois numa transação à parte daria números
    que o balcão já mudou — e o teste de restauração, que compara a contagem
    restaurada com a do manifesto, acusaria divergência que não existe.
    """
    exe = binario_do_postgres("pg_dump")
    destino = Path(destino)
    # O DESTINO NÃO VAI NA LINHA DE COMANDO (27/10/2026, alerta do CodeQL): o
    # pg_dump escreve na saída padrão, e quem abre o arquivo é este código.
    destino.parent.mkdir(parents=True, exist_ok=True)
    schema = schema_do_caminho(db_path)
    comando = [str(exe), "-d", dsn(), "-n", schema, "-Fc"]
    with open(destino, "wb") as arquivo:
        proc = _pg_dump_em(arquivo, comando, schema, contagens)
    if proc.returncode != 0:
        # Cópia pela metade não é cópia: o arquivo sai, e o erro sobe.
        destino.unlink(missing_ok=True)
        raise OperationalError("pg_dump falhou: " + (proc.stderr or "")[-500:])
    return destino


def _pg_dump_em(arquivo, comando: list[str], schema: str, contagens: dict | None):
    """Roda o pg_dump com a saída no arquivo já aberto. Ver `copiar_para_arquivo`."""
    import subprocess
    if contagens is None:
        return subprocess.run(comando, stdout=arquivo, stderr=subprocess.PIPE, text=True)
    with psycopg.connect(dsn(), autocommit=True) as pg, pg.cursor() as c:
        c.execute("BEGIN ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        try:
            c.execute("SELECT pg_export_snapshot()")
            instantaneo = c.fetchone()[0]
            contagens.clear()
            contagens.update(contar_linhas(c, schema))
            return subprocess.run(comando[:1] + ["--snapshot", instantaneo] + comando[1:],
                                  stdout=arquivo, stderr=subprocess.PIPE, text=True)
        finally:
            c.execute("COMMIT")


# ------------------------------------------------- a conferência da carga
# A CARGA DA VIRADA NÃO MORA AQUI, E POR ISSO ELA SE CONFERE AQUI — lote LH07,
# 21/10/2026. Quem leva os dados do SQLite da produção para o PostgreSQL é o
# `tools/migrar_para_postgres.py` (roteiro da virada, passo B3; na branch desde
# o LH10, a mesma versão da entrega de 17/10); o
# `_receber_de_sqlite` acima não carrega nada no PostgreSQL (grava o arquivo,
# ou recusa). E o banco da produção tem colunas que o código dela não conhecia:
# `pt_avisos.origem`/`origem_chave` (1.676 avisos do E-Ofício),
# `pt_editais.origem`/`origem_chave`, `rc_assentos.tardio_requerimento`. Coluna
# que não chega ao PostgreSQL some CALADA — a tela não a lê, e ninguém a
# procura. Esta conferência compara o arquivo com o schema DEPOIS da carga e
# diz o nome de cada tabela, coluna e contagem que não bate.

def _nome_sql(nome: str) -> str:
    return '"' + str(nome).replace('"', '""') + '"'


# TABELA DO ARQUIVO QUE NÃO É DO SISTEMA não se cobra da carga — lote LH09,
# 21/10/2026. `_ping` (uma coluna `x` sem tipo, 0 linhas) está no banco da
# produção e nenhum código a cria: não há `_ping` no código, nas ferramentas
# nem na história do repositório. É sobra de um teste de escrita feito à mão no
# servidor. O código não a cria; a carga pode deixá-la para trás, e a
# conferência a lista em `tabelas_ignoradas` (o aviso) em vez de dar a carga
# por incompleta. Se a carga a trouxer, também não é defeito.
TABELAS_FORA_DA_CARGA = {
    "_ping": "não é do sistema: nenhum código a cria (sobra de teste de escrita "
             "feito à mão no servidor, 0 linhas); a carga a ignora",
}


# O QUE O AJUSTE TIROU DE PROPÓSITO não é perda — lote LH10, 21/10/2026. O
# roteiro confere a carga DEPOIS do `tools/ajuste_pos_migracao.sql` (e antes de
# subir o código). No modo guardar, o ajuste põe NULL no valor que não converte
# (2.015 em `ri_matriculas.criado_por` no ensaio de 21/10) e apaga a linha
# repetida na chave de um UNIQUE do código, e antes guarda cada um em
# `cg_ajuste_guardados` (coluna '*' = a linha inteira, em JSON). Sem descontar
# isso, a conferência sairia com 1 por causa da própria decisão do oficial, e a
# perda de verdade ficaria no meio do esperado. Desconta-se EXATAMENTE o que
# está guardado e continua fora (valor ainda NULL, linha ainda ausente): a
# diferença que sobra além disso continua sendo perda.

def _tirado_pelo_ajuste(c, schema: str, no_pg: dict) -> tuple[dict, dict]:
    """({tabela: linhas apagadas}, {(tabela, coluna): valores a menos}) que
    `cg_ajuste_guardados` explica, como estão AGORA no schema."""
    import json
    linhas: dict[str, int] = {}
    valores: dict[tuple[str, str], int] = {}
    if "cg_ajuste_guardados" not in no_pg:
        return linhas, valores
    guardados = f"{_nome_sql(schema)}.cg_ajuste_guardados"
    c.execute(f"SELECT tabela, coluna FROM {guardados} GROUP BY tabela, coluna "
              f"ORDER BY tabela, coluna")
    for tabela, coluna in c.fetchall():
        colunas = no_pg.get(str(tabela).lower())
        if not colunas or "id" not in colunas:
            continue
        alvo = f"{_nome_sql(schema)}.{_nome_sql(tabela)}"
        if coluna == "*":
            c.execute(f"SELECT g.valor_original FROM {guardados} g WHERE g.tabela = %s "
                      f"AND g.coluna = '*' AND NOT EXISTS (SELECT 1 FROM {alvo} t "
                      f"WHERE t.id = g.linha_id) ORDER BY g.linha_id", (tabela,))
            for (original,) in c.fetchall():
                linhas[tabela.lower()] = linhas.get(tabela.lower(), 0) + 1
                for nome, valor in json.loads(original or "{}").items():
                    if valor is not None:
                        chave = (tabela.lower(), str(nome).lower())
                        valores[chave] = valores.get(chave, 0) + 1
        elif str(coluna).lower() in colunas:
            c.execute(f"SELECT count(*) FROM {guardados} g JOIN {alvo} t ON t.id = g.linha_id "
                      f"WHERE g.tabela = %s AND g.coluna = %s AND t.{_nome_sql(coluna)} IS NULL",
                      (tabela, coluna))
            chave = (tabela.lower(), str(coluna).lower())
            valores[chave] = valores.get(chave, 0) + int(c.fetchone()[0])
    return linhas, valores


def conferir_carga_de_sqlite(origem: Any, db_path: Any) -> dict:
    """O arquivo SQLite `origem` contra o schema PostgreSQL de `db_path`. Só LÊ.

    Para cada tabela do arquivo: se ela existe no PostgreSQL, que colunas do
    arquivo NÃO existem lá (a lista do aviso), se o número de linhas bate e,
    coluna a coluna, se o número de valores preenchidos bate (uma coluna que
    existe nos dois lados e veio vazia também é dado perdido). Nome de tabela
    e de coluna se compara sem caixa: o PostgreSQL guarda em minúscula.

    Devolve `ok` e as quatro listas — `tabelas_que_nao_vieram`,
    `colunas_que_nao_vieram` ({tabela: [colunas]}), `linhas_diferentes` e
    `valores_diferentes` ({tabela: {coluna: {"sqlite": n, "pg": m}}}) —, mais
    o aviso `tabelas_ignoradas` ({tabela: por quê}): as do arquivo que não são
    do sistema (`TABELAS_FORA_DA_CARGA`), que não pesam no `ok`.

    Depois do `tools/ajuste_pos_migracao.sql` no modo guardar, a diferença que
    é EXATAMENTE o que ele guardou em `cg_ajuste_guardados` e ainda está fora
    sai das duas listas e vai para `linhas_guardadas_pelo_ajuste` e
    `valores_guardados_pelo_ajuste` (mesma forma), que também não pesam no
    `ok`: é a decisão do oficial, e não perda (ver `_tirado_pelo_ajuste`).
    """
    if psycopg is None or not ativo():
        raise OperationalError("A conferência da carga precisa do PostgreSQL ligado (CG_PG_DSN).")
    arquivo = Path(_caminho_e_modo(origem)[0]).resolve()
    if not arquivo.is_file():
        raise OperationalError(f"O arquivo SQLite da carga não existe: {arquivo}")
    schema = schema_do_caminho(db_path)
    saida: dict[str, Any] = {"schema": schema, "tabelas_que_nao_vieram": [],
                             "colunas_que_nao_vieram": {}, "linhas_diferentes": {},
                             "valores_diferentes": {}, "tabelas_ignoradas": {},
                             "linhas_guardadas_pelo_ajuste": {},
                             "valores_guardados_pelo_ajuste": {}}
    sq = _CONNECT_ORIGINAL(arquivo.as_uri() + "?mode=ro", uri=True)
    try:
        with psycopg.connect(dsn(), autocommit=True) as pg, pg.cursor() as c:
            c.execute("SELECT table_name, column_name FROM information_schema.columns "
                      "WHERE table_schema = %s ORDER BY table_name, ordinal_position",
                      (schema,))
            no_pg: dict[str, dict[str, str]] = {}
            for tabela, coluna in c.fetchall():
                no_pg.setdefault(tabela.lower(), {})[coluna.lower()] = coluna
            linhas_tiradas, valores_tirados = _tirado_pelo_ajuste(c, schema, no_pg)
            tabelas = [t for (t,) in sq.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite%' ORDER BY name")]
            for tabela in tabelas:
                if tabela.lower() in TABELAS_FORA_DA_CARGA:
                    saida["tabelas_ignoradas"][tabela] = TABELAS_FORA_DA_CARGA[tabela.lower()]
                    continue
                colunas = [d[0] for d in sq.execute(
                    f"SELECT * FROM {_nome_sql(tabela)} LIMIT 0").description]
                destino = no_pg.get(tabela.lower())
                if destino is None:
                    saida["tabelas_que_nao_vieram"].append(tabela)
                    continue
                faltam = [x for x in colunas if x.lower() not in destino]
                if faltam:
                    saida["colunas_que_nao_vieram"][tabela] = faltam
                comuns = [x for x in colunas if x.lower() in destino]
                lista = "".join(f", count({_nome_sql(x)})" for x in comuns)
                de_la = sq.execute(f"SELECT count(*){lista} FROM {_nome_sql(tabela)}").fetchone()
                lista_pg = "".join(f", count({_nome_sql(destino[x.lower()])})" for x in comuns)
                c.execute(f"SELECT count(*){lista_pg} FROM {_nome_sql(schema)}."
                          f"{_nome_sql(tabela.lower())}")
                de_ca = c.fetchone()
                if de_la[0] != de_ca[0]:
                    par = {"sqlite": de_la[0], "pg": de_ca[0]}
                    if de_la[0] - de_ca[0] == linhas_tiradas.get(tabela.lower(), 0):
                        saida["linhas_guardadas_pelo_ajuste"][tabela] = par
                    else:
                        saida["linhas_diferentes"][tabela] = par
                diferentes: dict[str, dict] = {}
                guardados: dict[str, dict] = {}
                for x, a, b in zip(comuns, de_la[1:], de_ca[1:]):
                    if a == b:
                        continue
                    tirados = valores_tirados.get((tabela.lower(), x.lower()), 0)
                    (guardados if tirados and a - b == tirados else diferentes)[x] = {"sqlite": a, "pg": b}
                if diferentes:
                    saida["valores_diferentes"][tabela] = diferentes
                if guardados:
                    saida["valores_guardados_pelo_ajuste"][tabela] = guardados
    finally:
        sq.close()
    saida["ok"] = not (saida["tabelas_que_nao_vieram"] or saida["colunas_que_nao_vieram"]
                       or saida["linhas_diferentes"] or saida["valores_diferentes"])
    return saida


def main(argv: Sequence[str] | None = None) -> int:
    """`python banco_pg.py conferir-carga <copia.sqlite3> [<caminho do banco>]`

    Para o roteiro da virada (`docs/ROTEIRO_DA_VIRADA.md`), depois da carga
    (B3) e do ajuste (B4), e antes de subir o código: imprime a conferência e
    sai com 1 se alguma coisa não veio. O que o ajuste guardou sai em AVISO,
    sem pesar. Sem o caminho do banco vale o `CG_PG_SCHEMA` (é o que a
    produção usa)."""
    import json
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) not in (2, 3) or args[0] != "conferir-carga":
        print(main.__doc__)
        return 2
    feito = conferir_carga_de_sqlite(args[1], args[2] if len(args) == 3 else NOME_DO_BANCO_PRINCIPAL)
    print(json.dumps(feito, ensure_ascii=False, indent=1))
    for tabela, motivo in feito["tabelas_ignoradas"].items():
        print(f"AVISO: a tabela {tabela} do arquivo ficou fora da conferência — {motivo}.",
              file=sys.stderr)
    for tabela, par in feito["linhas_guardadas_pelo_ajuste"].items():
        print(f"AVISO: {tabela}: {par['sqlite'] - par['pg']} linha(s) a menos no PostgreSQL — "
              f"guardadas inteiras pelo ajuste em cg_ajuste_guardados (não é perda).",
              file=sys.stderr)
    for tabela, colunas in feito["valores_guardados_pelo_ajuste"].items():
        for coluna, par in colunas.items():
            print(f"AVISO: {tabela}.{coluna}: {par['sqlite'] - par['pg']} valor(es) a menos no "
                  f"PostgreSQL — guardados pelo ajuste em cg_ajuste_guardados (não é perda).",
                  file=sys.stderr)
    return 0 if feito["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
