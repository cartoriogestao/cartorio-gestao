"""Copia o banco SQLite do sistema para o PostgreSQL e CONFERE que nada se perdeu.

Ordem do oficial (15/10/2026): migrar o sistema para PostgreSQL numa cópia
separada e entregar um relatório MEDIDO. Esta ferramenta é a metade dos dados:
ela lê um arquivo SQLite (a cópia da produção — nunca a produção), cria um
schema no PostgreSQL, copia tabela por tabela e confere, linha por linha, que o
que chegou é o que saiu.

USO
    python tools/migrar_para_postgres.py --sqlite CAMINHO --dsn DSN --schema NOME
           [--recriar] [--so-conferir] [--so-tabela NOME] [--sem-corrente]
           [--relatorio ARQUIVO]

    --recriar      apaga o schema (DROP SCHEMA ... CASCADE) e o cria de novo.
                   Recusado para `public`: lá mora o que é de outros.
    --so-conferir  não cria nem copia nada: só confere um schema já copiado.
    --so-tabela    confere (ou copia) só a tabela indicada — útil após fix de NUL.
    --sem-corrente pula a etapa 6 (corrente de hash do RI); exit 0 não exige corrente.

O QUE ELA FAZ, NA ORDEM
    1. Lê o esquema do SQLite pelo catálogo (`pragma table_xinfo`,
       `index_list`, `foreign_key_list`) e não pelo texto do CREATE TABLE —
       o catálogo é estruturado; o texto só é lido para o que o catálogo não
       diz (CHECK, WITHOUT ROWID, ON CONFLICT, COLLATE, a cláusula WHERE do
       índice parcial).
    2. PERFILA cada coluna com `typeof()`: o SQLite aceita texto numa coluna
       declarada INTEGER, e o PostgreSQL não. Coluna com valor fora do tipo
       declarado nasce TEXT, e entra no relatório com quantos valores e quais
       — sem dado pessoal: só o vazio, números e datas aparecem por extenso;
       o resto aparece como «texto de N caracteres».
    3. Cria as tabelas SEM restrição, copia com COPY (NULL continua NULL e ''
       continua ''), e só DEPOIS liga NOT NULL, PK, UNIQUE e índices — assim um
       valor que o PostgreSQL recuse vira uma linha no relatório, e não uma
       tabela inteira que não entrou.
    4. FKs entram como NOT VALID, e as linhas órfãs que já existem são
       contadas por FK.
    5. As colunas identity seguem do maior id (ou do `sqlite_sequence`, se for
       maior — o AUTOINCREMENT do SQLite nunca reaproveita número).
    6. CONFERE: contagem de linhas e soma de verificação (sha256 do texto
       canônico de cada linha, na ordem da chave). A ordem é decidida em
       Python, e não pelo banco, para que colação de nenhum dos dois lados
       entre na conta.
    7. Recalcula a CORRENTE DE HASH dos atos do RI (`ri_schema.hash_ato`) lendo
       do PostgreSQL e do SQLite, e confere com a gravada.
    8. Escreve o relatório (`MIGRACAO_PG/relatorio_dados.md`).

O TEXTO CANÔNICO DE UMA LINHA
    Cada campo vira `\\N` (NULL), `i<inteiro>`, `r<repr do real>`,
    `t<texto como está>` ou `b<bytes em hex>`, separados por 0x1F. A forma é a
    do TIPO DE DESTINO: numa coluna que nasceu TEXT por ter texto misturado, o
    inteiro 7 do SQLite é comparado como `t7` — é exatamente o que o
    PostgreSQL guarda, e a mudança de tipo está declarada no relatório.

Esta ferramenta não depende de `banco_pg.py`: a tradução do esquema é dela,
para que a conferência não confira a camada contra ela mesma.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

try:
    import psycopg
    from psycopg import sql as S
except ImportError:  # pragma: no cover
    psycopg = None
    S = None

AQUI = Path(__file__).resolve()
SISTEMA = AQUI.parents[1]
RELATORIO_PADRAO = AQUI.parents[2] / "relatorio_dados.md"

SEP = "\x1f"
MAX_DIVERGENCIAS = 20
LOTE = 5000
# Tabela com chave inteira e mais linhas que isto é conferida em fluxo,
# ordenada pelo banco (a chave é inteira dos dois lados, a ordem é a mesma);
# as outras são lidas inteiras e ordenadas em Python.
FLUXO_A_PARTIR_DE = 200_000


def log(*partes: Any) -> None:
    print(time.strftime("%H:%M:%S"), *partes, flush=True)


# ===================================================================== esquema

@dataclass
class Coluna:
    nome: str
    tipo_decl: str
    notnull: bool
    default: str | None
    pk: int
    oculta: int
    afinidade: str = ""
    alvo: str = ""            # bigint | double | text | bytea
    identity: bool = False
    perfil: dict = field(default_factory=dict)


@dataclass
class Tabela:
    nome: str
    sql: str
    colunas: list[Coluna]
    sem_rowid: bool = False
    pk: list[str] = field(default_factory=list)
    uniques: list[list[str]] = field(default_factory=list)
    indices: list[dict] = field(default_factory=list)
    fks: list[dict] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    linhas: int = 0

    @property
    def identity(self) -> Coluna | None:
        for c in self.colunas:
            if c.identity:
                return c
        return None


def afinidade(tipo: str) -> str:
    """As cinco regras de afinidade do SQLite (seção 3.1 da documentação)."""
    t = (tipo or "").upper()
    if "INT" in t:
        return "INTEGER"
    if any(k in t for k in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if t == "" or "BLOB" in t:
        return "BLOB"
    if any(k in t for k in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"


def q(nome: str) -> str:
    """Identificador entre aspas duplas, para o SQL que vai ao SQLite."""
    return '"' + nome.replace('"', '""') + '"'


# --- um varredor de SQL mínimo: pula strings, identificadores e comentários.

def _fichas(sql: str) -> Iterator[tuple[str, int, int]]:
    """Devolve (tipo, inicio, fim): tipo é 'str', 'id', 'com', 'pal', 'sim'."""
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch in " \t\r\n":
            i += 1
            continue
        if sql.startswith("--", i):
            j = sql.find("\n", i)
            j = n if j < 0 else j
            yield "com", i, j
            i = j
            continue
        if sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            j = n if j < 0 else j + 2
            yield "com", i, j
            i = j
            continue
        if ch == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            yield "str", i, j + 1
            i = j + 1
            continue
        if ch in '"`[':
            fecho = {'"': '"', "`": "`", "[": "]"}[ch]
            j = sql.find(fecho, i + 1)
            j = n - 1 if j < 0 else j
            yield "id", i, j + 1
            i = j + 1
            continue
        if ch.isalnum() or ch == "_":
            j = i
            while j < n and (sql[j].isalnum() or sql[j] == "_"):
                j += 1
            yield "pal", i, j
            i = j
            continue
        yield "sim", i, i + 1
        i += 1


def _fecho_do_parentese(sql: str, abre: int) -> int:
    """Posição do ')' que fecha o '(' em `abre` (respeitando strings)."""
    nivel = 0
    for tipo, a, b in _fichas(sql[abre:]):
        if tipo != "sim":
            continue
        ch = sql[abre + a]
        if ch == "(":
            nivel += 1
        elif ch == ")":
            nivel -= 1
            if nivel == 0:
                return abre + a
    return -1


def extrair_checks(sql: str) -> list[str]:
    fichas = list(_fichas(sql))
    saida = []
    for k, (tipo, a, b) in enumerate(fichas):
        if tipo == "pal" and sql[a:b].upper() == "CHECK" and k + 1 < len(fichas):
            t2, a2, _ = fichas[k + 1]
            if t2 == "sim" and sql[a2] == "(":
                fim = _fecho_do_parentese(sql, a2)
                if fim > 0:
                    saida.append(sql[a2 + 1:fim].strip())
    return saida


def traduzir_expressao(expr: str) -> tuple[str, list[str]]:
    """Expressão SQLite → PG: identificadores [x] e `x` viram "x"; COLLATE sai."""
    avisos = []
    partes = []
    ultimo = 0
    fichas = list(_fichas(expr))
    pular_ate = -1
    for k, (tipo, a, b) in enumerate(fichas):
        if a < pular_ate:
            continue
        if tipo == "com":
            partes.append(expr[ultimo:a])
            ultimo = b
            continue
        if tipo == "id" and expr[a] in "`[":
            partes.append(expr[ultimo:a])
            partes.append(q(expr[a + 1:b - 1]))
            ultimo = b
            continue
        if tipo == "pal" and expr[a:b].upper() == "COLLATE" and k + 1 < len(fichas):
            _, a2, b2 = fichas[k + 1]
            avisos.append("COLLATE " + expr[a2:b2])
            partes.append(expr[ultimo:a])
            ultimo = b2
            pular_ate = b2
            continue
    partes.append(expr[ultimo:])
    return "".join(partes).strip(), avisos


def clausula_where(sql_indice: str) -> str | None:
    """A cláusula WHERE de um índice parcial, tirada do texto do CREATE INDEX."""
    for tipo, a, b in _fichas(sql_indice):
        if tipo == "pal" and sql_indice[a:b].upper() == "WHERE":
            return sql_indice[b:].strip().rstrip(";").strip()
    return None


def ler_esquema(sq: sqlite3.Connection) -> tuple[list[Tabela], dict]:
    extras = {"sem_rowid": [], "on_conflict": [], "collate": [], "geradas": [],
              "sqlite_sequence": {}, "objetos": {}}
    for tipo, n in sq.execute("SELECT type, count(*) FROM sqlite_master GROUP BY type"):
        extras["objetos"][tipo] = n
    try:
        extras["sqlite_sequence"] = {r[0]: r[1] for r in sq.execute(
            "SELECT name, seq FROM sqlite_sequence")}
    except sqlite3.Error:
        pass
    tabelas = []
    nomes = [r[0] for r in sq.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite\\_%' ESCAPE '\\' ORDER BY name")]
    for nome in nomes:
        sql = sq.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                         (nome,)).fetchone()[0] or ""
        cols = []
        for cid, cn, tp, nn, df, pk, hid in sq.execute(f"PRAGMA table_xinfo({q(nome)})"):
            c = Coluna(cn, tp or "", bool(nn), df, pk, hid)
            c.afinidade = afinidade(c.tipo_decl)
            if hid:
                extras["geradas"].append(f"{nome}.{cn}")
            cols.append(c)
        t = Tabela(nome, sql, [c for c in cols if not c.oculta])
        t.sem_rowid = bool(re.search(r"\)\s*WITHOUT\s+ROWID\s*;?\s*$", sql, re.I))
        if t.sem_rowid:
            extras["sem_rowid"].append(nome)
        for m in re.finditer(r"ON\s+CONFLICT\s+(\w+)", sql, re.I):
            extras["on_conflict"].append(f"{nome}: ON CONFLICT {m.group(1).upper()}")
        for m in re.finditer(r"(\w+|\"[^\"]+\")[^,(]*?COLLATE\s+(\w+)", sql, re.I):
            extras["collate"].append(f"{nome}: COLLATE {m.group(2).upper()} "
                                     f"(perto de «{m.group(1)}»)")
        pkcols = sorted([c for c in t.colunas if c.pk], key=lambda c: c.pk)
        t.pk = [c.nome for c in pkcols]
        if (len(pkcols) == 1 and pkcols[0].tipo_decl.strip().upper() == "INTEGER"
                and not t.sem_rowid):
            pkcols[0].identity = True
        t.checks = extrair_checks(sql)
        for seq, iname, unico, origem, parcial in sq.execute(
                f"PRAGMA index_list({q(nome)})"):
            info = sq.execute(f"PRAGMA index_xinfo({q(iname)})").fetchall()
            chaves = [r for r in info if r[5]]          # key=1
            isql = sq.execute("SELECT sql FROM sqlite_master WHERE type='index' "
                              "AND name=?", (iname,)).fetchone()
            isql = isql[0] if isql else None
            if origem == "pk":
                continue
            if origem == "u":
                t.uniques.append([r[2] for r in chaves])
                continue
            t.indices.append({
                "nome": iname, "unico": bool(unico), "parcial": bool(parcial),
                "colunas": [(r[2], bool(r[3]), r[4]) for r in chaves],  # nome, desc, coll
                "expressao": any(r[1] == -2 for r in chaves),
                "sql": isql,
            })
        grupos: dict[int, dict] = {}
        for fid, seq, pai, de, para, upd, dele, match in sq.execute(
                f"PRAGMA foreign_key_list({q(nome)})"):
            g = grupos.setdefault(fid, {"pai": pai, "de": [], "para": [],
                                        "on_update": upd, "on_delete": dele})
            g["de"].append(de)
            g["para"].append(para)
        t.fks = [grupos[k] for k in sorted(grupos)]
        tabelas.append(t)
    return tabelas, extras


# ===================================================================== perfil

def _amostra_segura(v: Any) -> str:
    """Mostra o valor só quando ele não pode ser dado pessoal."""
    if isinstance(v, bytes):
        return f"bytes({len(v)})"
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, int):
        return str(v)
    s = str(v)
    if s == "":
        return "«''» (vazio)"
    if s.strip() == "":
        return f"«{len(s)} espaço(s)»"
    if re.fullmatch(r"[\d\s.,:/+\-]{1,20}", s):
        return f"«{s}»"
    return f"texto de {len(s)} caracteres"


def perfilar(sq: sqlite3.Connection, t: Tabela) -> None:
    # Uma passada por tabela, com UMA conta por coluna: quantos valores fogem
    # do tipo que a afinidade espera. Só a coluna que tem algum ganha a conta
    # detalhada (a primeira versão fazia seis contas por coluna e levava
    # 290 s na cópia; a maior parte do tempo ia nas colunas sem problema).
    expr = ["count(*)"]
    for c in t.colunas:
        n = q(c.nome)
        if c.afinidade == "INTEGER":
            expr.append(f"sum(typeof({n}) NOT IN ('integer','null'))")
        elif c.afinidade == "REAL":
            expr.append(f"sum(typeof({n}) IN ('text','blob'))")
        elif c.afinidade == "TEXT":
            expr.append(f"sum(typeof({n}) IN ('integer','real','blob'))")
        else:
            expr.append("1")       # sem tipo / numérico: sempre detalha
    linha = sq.execute(f"SELECT {', '.join(expr)} FROM {q(t.nome)}").fetchone()
    t.linhas = int(linha[0] or 0)
    for i, c in enumerate(t.colunas):
        c.perfil = {"integer": 0, "real": 0, "text": 0, "blob": 0, "vazio": 0}
        if int(linha[i + 1] or 0):
            n = q(c.nome)
            d = sq.execute(
                f"SELECT sum(typeof({n})='integer'), sum(typeof({n})='real'), "
                f"sum(typeof({n})='text'), sum(typeof({n})='blob'), "
                f"sum(typeof({n})='text' AND {n}='') FROM {q(t.nome)}").fetchone()
            c.perfil.update(zip(("integer", "real", "text", "blob", "vazio"),
                                (int(x or 0) for x in d)))
        c.alvo, motivo = decidir_alvo(c)
        if motivo:
            c.perfil["motivo"] = motivo
            amostra = sq.execute(
                f"SELECT {q(c.nome)}, typeof({q(c.nome)}), count(*) FROM {q(t.nome)} "
                f"WHERE typeof({q(c.nome)}) NOT IN ('null', ?) "
                f"GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 8",
                (esperado(c),)).fetchall()
            c.perfil["exemplos"] = [(_amostra_segura(v), tp, n) for v, tp, n in amostra]


def esperado(c: Coluna) -> str:
    return {"INTEGER": "integer", "REAL": "real", "TEXT": "text",
            "BLOB": "blob", "NUMERIC": "integer"}[c.afinidade]


def decidir_alvo(c: Coluna) -> tuple[str, str | None]:
    """O tipo no PostgreSQL, e o motivo quando não é o que se declarou."""
    p = c.perfil
    ni, nr, nt, nb = p["integer"], p["real"], p["text"], p["blob"]
    if c.identity:
        return "bigint", None
    a = c.afinidade
    if a == "INTEGER":
        if nr or nt or nb:
            return "text", "coluna INTEGER com valor que não é inteiro"
        return "bigint", None
    if a == "REAL":
        if nt or nb:
            return "text", "coluna REAL com valor que não é número"
        return "double", None
    if a == "TEXT":
        if nb and not nt:
            return "bytea", "coluna TEXT que só guarda bytes"
        if nb:
            return "text", "coluna TEXT com bytes misturados (gravados em hex)"
        if ni or nr:
            return "text", "coluna TEXT com número guardado como número"
        return "text", None
    if a == "BLOB":       # BLOB declarado, ou coluna sem tipo
        decl = c.tipo_decl.strip()
        if nb and not (ni or nr or nt):
            return "bytea", None
        if not (ni or nr or nt or nb):
            return ("bytea" if decl else "text"), None
        if not decl:
            if ni and not (nr or nt or nb):
                return "bigint", None
            if not (nt or nb):
                return "double", None
            if nt and not (ni or nr or nb):
                return "text", None
            return "text", "coluna sem tipo com valores de tipos misturados"
        return "text", "coluna BLOB com valor que não é bytes"
    # NUMERIC: DATE, DATETIME, BOOLEAN, DECIMAL...
    if not (ni or nr or nt or nb):
        return ("bigint" if "BOOL" in c.tipo_decl.upper() else "text"), None
    if ni and not (nr or nt or nb):
        return "bigint", None
    if (ni or nr) and not (nt or nb):
        return "double", None
    if nt and not (ni or nr or nb):
        return "text", None
    return "text", f"coluna {c.tipo_decl} com valores de tipos misturados"


PG_TIPO = {"bigint": "BIGINT", "double": "DOUBLE PRECISION", "text": "TEXT",
           "bytea": "BYTEA"}


# ===================================================================== valores

PROBLEMAS_DE_VALOR: dict[str, dict[str, int]] = {}
# Só conta numa passada (a da cópia, ou a da conferência no --so-conferir):
# contar nas duas mostraria o dobro do que existe.
_TABELA_ATUAL = [""]


def _anotar(tipo: str) -> None:
    if not _TABELA_ATUAL[0]:
        return
    d = PROBLEMAS_DE_VALOR.setdefault(_TABELA_ATUAL[0], {})
    d[tipo] = d.get(tipo, 0) + 1


def _fabrica_de_texto(b: bytes) -> str:
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        _anotar("texto com UTF-8 inválido (lido com substituição)")
        return b.decode("utf-8", "replace")


def como_texto(v: Any) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, bool):
        return str(int(v))
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        b = bytes(v)
        try:
            return b.decode("utf-8")
        except UnicodeDecodeError:
            return "\\x" + b.hex()
    return str(v)


def _sanitizar_texto_pg(s: str) -> str:
    """Política de carga: TEXT no PG não aceita NUL; alinhar COPY e conferência."""
    if "\x00" in s:
        _anotar("texto com caractere NUL (0x00), trocado por U+FFFD")
        s = s.replace("\x00", "\ufffd")
    return s


def conversor(alvo: str) -> Callable[[Any], Any]:
    """O que vai ao COPY, a partir do valor cru do SQLite."""
    if alvo == "text":
        def f(v):
            if v is None:
                return None
            s = v if type(v) is str else como_texto(v)
            return _sanitizar_texto_pg(s)
        return f
    if alvo == "double":
        return lambda v: None if v is None else float(v)
    if alvo == "bytea":
        return lambda v: None if v is None else (
            bytes(v) if not isinstance(v, str) else v.encode("utf-8"))
    return lambda v: v


def canon(v: Any, alvo: str) -> str:
    if v is None:
        return "\\N"
    if alvo == "bigint":
        if isinstance(v, str):
            return "t" + _sanitizar_texto_pg(v)
        return "i" + str(int(v))
    if alvo == "double":
        return "r" + repr(float(v))
    if alvo == "bytea":
        if isinstance(v, str):
            return "b" + v.encode("utf-8").hex()
        return "b" + bytes(v).hex()
    s = v if type(v) is str else como_texto(v)
    if alvo == "text":
        s = _sanitizar_texto_pg(s)
    return "t" + s


# ===================================================================== PostgreSQL

def ident(*nomes: str):
    return S.SQL(".").join(S.Identifier(n) for n in nomes)


def nome_curto(base: str, usados: set) -> str:
    """Nome de objeto do PG (63 bytes), sem colidir com outro do schema."""
    nome = base
    if len(nome.encode()) > 63:
        h = hashlib.sha1(base.encode()).hexdigest()[:8]
        nome = base.encode()[:54].decode("utf-8", "ignore") + "_" + h
    k = 2
    raiz = nome
    while nome in usados:
        nome = f"{raiz[:58]}_{k}"
        k += 1
    usados.add(nome)
    return nome


def traduzir_default(d: str | None, alvo: str) -> tuple[str | None, str | None]:
    """(default no PG, aviso). Função do SQLite no default sai, e é listada."""
    if d is None:
        return None, None
    s = d.strip()
    while s.startswith("(") and s.endswith(")") and _fecho_do_parentese(s, 0) == len(s) - 1:
        s = s[1:-1].strip()
    if s.upper() == "NULL":
        return None, None
    if re.fullmatch(r"[+-]?\d+(\.\d+)?([eE][+-]?\d+)?", s):
        if alvo == "text":
            return "'" + s + "'", None
        if alvo == "bytea":
            return None, f"default {d} numa coluna de bytes"
        if alvo == "bigint" and not re.fullmatch(r"[+-]?\d+", s):
            return None, f"default {d} não é inteiro"
        return s, None
    m = re.fullmatch(r"'((?:[^']|'')*)'", s, re.S)
    if m:
        dentro = m.group(1).replace("''", "'")
        if alvo == "text":
            return s, None
        if alvo == "bigint" and re.fullmatch(r"\s*[+-]?\d+\s*", dentro):
            return dentro.strip(), None
        if alvo == "double" and re.fullmatch(r"\s*[+-]?\d+(\.\d+)?\s*", dentro):
            return dentro.strip(), None
        return None, f"default {d} não cabe na coluna {PG_TIPO[alvo]}"
    if s.upper() in ("TRUE", "FALSE"):
        v = "1" if s.upper() == "TRUE" else "0"
        return (("'" + v + "'") if alvo == "text" else v), None
    if re.fullmatch(r"[xX]'([0-9a-fA-F]*)'", s) and alvo == "bytea":
        return "'\\x" + s[2:-1] + "'::bytea", None
    return None, f"default {d} (função do SQLite) removido"


@dataclass
class Resultado:
    tempos: dict = field(default_factory=dict)
    defaults_removidos: list = field(default_factory=list)
    clausulas_removidas: list = field(default_factory=list)
    notnull_falhou: list = field(default_factory=list)
    pk_falhou: list = field(default_factory=list)
    unique_duplicatas: list = field(default_factory=list)
    indice_falhou: list = field(default_factory=list)
    check_falhou: list = field(default_factory=list)
    check_violado: list = field(default_factory=list)
    fk_criadas: int = 0
    fk_orfas: list = field(default_factory=list)
    fk_falhou: list = field(default_factory=list)
    sequencias: list = field(default_factory=list)
    copia: dict = field(default_factory=dict)        # tabela -> (linhas, segundos)
    conferencia: dict = field(default_factory=dict)
    corrente: dict = field(default_factory=dict)
    tamanho_pg: int = 0
    tamanho_sqlite: int = 0
    indices_criados: int = 0
    uniques_criados: int = 0
    pks_criadas: int = 0
    checks_criados: int = 0
    erro_copia: dict = field(default_factory=dict)


class Etapa:
    def __init__(self, res: Resultado, nome: str):
        self.res, self.nome = res, nome

    def __enter__(self):
        self.t0 = time.perf_counter()
        log(f"== {self.nome}")
        return self

    def __exit__(self, *exc):
        dt = time.perf_counter() - self.t0
        self.res.tempos[self.nome] = self.res.tempos.get(self.nome, 0) + dt
        log(f"   {self.nome}: {dt:.1f} s")
        return False


def executar_protegido(pg, comando, params=None) -> Exception | None:
    """Roda um comando num SAVEPOINT: se falhar, desfaz só ele e devolve o erro."""
    with pg.cursor() as cur:
        cur.execute("SAVEPOINT s")
        try:
            cur.execute(comando, params)
        except Exception as e:  # noqa: BLE001 — o erro vai para o relatório
            cur.execute("ROLLBACK TO SAVEPOINT s")
            cur.execute("RELEASE SAVEPOINT s")
            return e
        cur.execute("RELEASE SAVEPOINT s")
    return None


def consultar_protegido(pg, sql_texto: str):
    """Uma consulta num SAVEPOINT: (primeira linha, erro). Não desfaz o resto."""
    with pg.cursor() as cur:
        cur.execute("SAVEPOINT c")
        try:
            cur.execute(sql_texto)
            linha = cur.fetchone()
        except Exception as e:  # noqa: BLE001
            cur.execute("ROLLBACK TO SAVEPOINT c")
            cur.execute("RELEASE SAVEPOINT c")
            return None, e
        cur.execute("RELEASE SAVEPOINT c")
    return linha, None


def msg(e: Exception) -> str:
    texto = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
    return texto[:240]


def criar_tabelas(pg, schema: str, tabelas: list[Tabela], res: Resultado) -> None:
    with pg.cursor() as cur:
        for t in tabelas:
            partes = []
            for c in t.colunas:
                tipo = PG_TIPO[c.alvo]
                linha = S.SQL("{} {}").format(S.Identifier(c.nome), S.SQL(tipo))
                if c.identity:
                    linha = S.SQL("{} BIGINT GENERATED BY DEFAULT AS IDENTITY").format(
                        S.Identifier(c.nome))
                else:
                    dflt, aviso = traduzir_default(c.default, c.alvo)
                    if aviso:
                        res.defaults_removidos.append(f"{t.nome}.{c.nome}: {aviso}")
                    if dflt is not None:
                        linha = S.SQL("{} DEFAULT {}").format(linha, S.SQL(dflt))
                partes.append(linha)
            if not partes:
                partes.append(S.SQL('"_sem_coluna" TEXT'))
            cur.execute(S.SQL("CREATE TABLE {} ({})").format(
                ident(schema, t.nome), S.SQL(", ").join(partes)))
    pg.commit()


def copiar_tabela(sq, pg, schema: str, t: Tabela, res: Resultado) -> None:
    _TABELA_ATUAL[0] = t.nome
    if not t.colunas:
        return
    t0 = time.perf_counter()
    convs = [conversor(c.alvo) for c in t.colunas]
    precisa = [c.alvo != "bigint" for c in t.colunas]
    cols_pg = S.SQL(", ").join(S.Identifier(c.nome) for c in t.colunas)
    sel = f"SELECT {', '.join(q(c.nome) for c in t.colunas)} FROM {q(t.nome)}"
    n = 0
    try:
        with pg.cursor() as cur:
            with cur.copy(S.SQL("COPY {} ({}) FROM STDIN").format(
                    ident(schema, t.nome), cols_pg)) as cp:
                cs = sq.execute(sel)
                while True:
                    lote = cs.fetchmany(LOTE)
                    if not lote:
                        break
                    for linha in lote:
                        cp.write_row([f(v) if p else v
                                      for f, p, v in zip(convs, precisa, linha)])
                    n += len(lote)
        pg.commit()
    except Exception as e:  # noqa: BLE001
        pg.rollback()
        res.erro_copia[t.nome] = msg(e)
        log(f"   ERRO ao copiar {t.nome}: {msg(e)}")
        return
    res.copia[t.nome] = (n, time.perf_counter() - t0)
    if n >= 100_000:
        log(f"   {t.nome}: {n} linhas em {time.perf_counter() - t0:.1f} s")


def ligar_restricoes(pg, schema: str, tabelas: list[Tabela], res: Resultado,
                     extras: dict) -> None:
    usados: set = set()
    for t in tabelas:
        usados.add(t.nome)
        for i in t.indices:
            usados.add(i["nome"])
    por_nome = {t.nome: t for t in tabelas}
    with pg.cursor() as cur:
        cur.execute("SET maintenance_work_mem = '512MB'")
    # NOT NULL — uma passada por tabela; se falhar, coluna a coluna.
    for t in tabelas:
        alvos = [c for c in t.colunas if c.notnull and not c.identity]
        if not alvos or t.nome in res.erro_copia:
            continue
        cmd = S.SQL("ALTER TABLE {} {}").format(ident(schema, t.nome), S.SQL(", ").join(
            S.SQL("ALTER COLUMN {} SET NOT NULL").format(S.Identifier(c.nome)) for c in alvos))
        if executar_protegido(pg, cmd):
            for c in alvos:
                e = executar_protegido(pg, S.SQL("ALTER TABLE {} ALTER COLUMN {} SET NOT NULL")
                                       .format(ident(schema, t.nome), S.Identifier(c.nome)))
                if e:
                    res.notnull_falhou.append(f"{t.nome}.{c.nome}: {msg(e)}")
        pg.commit()
    # PK
    for t in tabelas:
        if not t.pk or t.nome in res.erro_copia:
            continue
        nome = nome_curto(f"{t.nome}_pkey", usados)
        e = executar_protegido(pg, S.SQL("ALTER TABLE {} ADD CONSTRAINT {} PRIMARY KEY ({})")
                               .format(ident(schema, t.nome), S.Identifier(nome),
                                       S.SQL(", ").join(S.Identifier(c) for c in t.pk)))
        if e:
            res.pk_falhou.append(f"{t.nome} ({', '.join(t.pk)}): {msg(e)}")
            _registrar_duplicatas(pg, schema, t.nome, t.pk, res, "PRIMARY KEY")
            executar_protegido(pg, S.SQL("CREATE INDEX {} ON {} ({})").format(
                S.Identifier(nome), ident(schema, t.nome),
                S.SQL(", ").join(S.Identifier(c) for c in t.pk)))
        else:
            res.pks_criadas += 1
        pg.commit()
    # UNIQUE (das restrições da tabela)
    for t in tabelas:
        if t.nome in res.erro_copia:
            continue
        for k, cols in enumerate(t.uniques, 1):
            nome = nome_curto(f"{t.nome}_{'_'.join(cols)}_key", usados)
            e = executar_protegido(pg, S.SQL("ALTER TABLE {} ADD CONSTRAINT {} UNIQUE ({})")
                                   .format(ident(schema, t.nome), S.Identifier(nome),
                                           S.SQL(", ").join(S.Identifier(c) for c in cols)))
            if e:
                _registrar_duplicatas(pg, schema, t.nome, cols, res, "UNIQUE", erro=msg(e))
                executar_protegido(pg, S.SQL("CREATE INDEX {} ON {} ({})").format(
                    S.Identifier(nome), ident(schema, t.nome),
                    S.SQL(", ").join(S.Identifier(c) for c in cols)))
            else:
                res.uniques_criados += 1
        pg.commit()
    # Índices explícitos
    for t in tabelas:
        if t.nome in res.erro_copia:
            continue
        for i in t.indices:
            criar_indice(pg, schema, t, i, res)
        pg.commit()
    # CHECK
    for t in tabelas:
        if t.nome in res.erro_copia:
            continue
        for k, expr in enumerate(t.checks, 1):
            traduzida, avisos = traduzir_expressao(expr)
            for a in avisos:
                res.clausulas_removidas.append(f"{t.nome}: {a} dentro de CHECK")
            nome = nome_curto(f"{t.nome}_check{k}", usados)
            e = executar_protegido(pg, S.SQL("ALTER TABLE {} ADD CONSTRAINT {} CHECK ({}) NOT VALID")
                                   .format(ident(schema, t.nome), S.Identifier(nome),
                                           S.SQL(traduzida)))
            if e:
                res.check_falhou.append(f"{t.nome}: CHECK ({expr}): {msg(e)}")
                continue
            res.checks_criados += 1
            e = executar_protegido(pg, S.SQL("ALTER TABLE {} VALIDATE CONSTRAINT {}")
                                   .format(ident(schema, t.nome), S.Identifier(nome)))
            if e:
                res.check_violado.append(f"{t.nome}: CHECK ({expr}) — há linhas que não "
                                         f"cumprem; fica NOT VALID")
        pg.commit()
    # FK (NOT VALID) e órfãs
    tipos = tipos_no_pg(pg, schema)
    for t in tabelas:
        if t.nome in res.erro_copia:
            continue
        for k, fk in enumerate(t.fks, 1):
            pai = por_nome.get(fk["pai"])
            rotulo = (f"{t.nome}({', '.join(fk['de'])}) → {fk['pai']}"
                      f"({', '.join(p or '?' for p in fk['para'])})")
            if pai is None:
                res.fk_falhou.append(f"{rotulo}: a tabela {fk['pai']} não existe no banco")
                continue
            para = [p if p else None for p in fk["para"]]
            if any(p is None for p in para):
                if len(pai.pk) != len(para):
                    res.fk_falhou.append(f"{rotulo}: aponta para a chave de {pai.nome}, "
                                         f"que não tem PK compatível")
                    continue
                para = list(pai.pk)
            rotulo = f"{t.nome}({', '.join(fk['de'])}) → {pai.nome}({', '.join(para)})"
            nome = nome_curto(f"{t.nome}_{'_'.join(fk['de'])}_fkey", usados)
            acoes = ""
            if (fk["on_delete"] or "NO ACTION").upper() != "NO ACTION":
                acoes += f" ON DELETE {fk['on_delete'].upper()}"
            if (fk["on_update"] or "NO ACTION").upper() != "NO ACTION":
                acoes += f" ON UPDATE {fk['on_update'].upper()}"
            e = executar_protegido(pg, S.SQL(
                "ALTER TABLE {} ADD CONSTRAINT {} FOREIGN KEY ({}) REFERENCES {} ({})"
                + acoes + " NOT VALID").format(
                    ident(schema, t.nome), S.Identifier(nome),
                    S.SQL(", ").join(S.Identifier(c) for c in fk["de"]),
                    ident(schema, pai.nome),
                    S.SQL(", ").join(S.Identifier(c) for c in para)))
            if e:
                res.fk_falhou.append(f"{rotulo}: {msg(e)}")
            else:
                res.fk_criadas += 1
            n = contar_orfas(pg, schema, t.nome, fk["de"], pai.nome, para, tipos)
            if n:
                res.fk_orfas.append((rotulo, n))
            pg.commit()


def criar_indice(pg, schema: str, t: Tabela, i: dict, res: Resultado) -> None:
    unico = "UNIQUE " if i["unico"] else ""
    if i["expressao"]:
        # índice sobre expressão: vai o texto do SQLite, traduzido.
        corpo = i["sql"] or ""
        abre = corpo.find("(")
        fecho = _fecho_do_parentese(corpo, abre) if abre >= 0 else -1
        lista, avisos = traduzir_expressao(corpo[abre + 1:fecho]) if fecho > 0 else ("", [])
        colunas = S.SQL(lista)
    else:
        avisos = []
        itens = []
        for nome_col, desc, coll in i["colunas"]:
            if coll and coll.upper() not in ("BINARY",):
                avisos.append(f"COLLATE {coll}")
            itens.append(S.SQL("{}{}").format(S.Identifier(nome_col),
                                             S.SQL(" DESC" if desc else "")))
        colunas = S.SQL(", ").join(itens)
    where = S.SQL("")
    if i["parcial"]:
        w = clausula_where(i["sql"] or "")
        if w:
            wt, av2 = traduzir_expressao(w)
            avisos += av2
            where = S.SQL(" WHERE ") + S.SQL(wt)
    for a in avisos:
        res.clausulas_removidas.append(f"índice {i['nome']} ({t.nome}): {a}")
    cmd = S.SQL("CREATE " + unico + "INDEX {} ON {} ({}){}").format(
        S.Identifier(i["nome"]), ident(schema, t.nome), colunas, where)
    e = executar_protegido(pg, cmd)
    if e is None:
        res.indices_criados += 1
        return
    if i["unico"] and getattr(e, "sqlstate", "") == "23505":
        cols = [c for c, _, _ in i["colunas"]]
        _registrar_duplicatas(pg, schema, t.nome, cols, res, f"índice único {i['nome']}",
                              erro=msg(e), where=(clausula_where(i["sql"] or "")
                                                  if i["parcial"] else None))
        e2 = executar_protegido(pg, S.SQL("CREATE INDEX {} ON {} ({}){}").format(
            S.Identifier(i["nome"]), ident(schema, t.nome), colunas, where))
        if e2 is None:
            res.indices_criados += 1
        return
    res.indice_falhou.append(f"{i['nome']} ({t.nome}): {msg(e)}")


def _registrar_duplicatas(pg, schema, tabela, cols, res, oque, erro="", where=None):
    filtro = " AND ".join(f"{q(c)} IS NOT NULL" for c in cols)
    if where:
        filtro += f" AND ({traduzir_expressao(where)[0]})"
    lista = ", ".join(q(c) for c in cols)
    linha, e = consultar_protegido(
        pg, f"SELECT count(*), coalesce(sum(n), 0) FROM (SELECT count(*) n "
            f"FROM {q(schema)}.{q(tabela)} WHERE {filtro} GROUP BY {lista} "
            f"HAVING count(*) > 1) x")
    grupos, linhas = linha if linha else (None, None)
    if e:
        erro = (erro + " / " if erro else "") + msg(e)
    res.unique_duplicatas.append({"tabela": tabela, "colunas": cols, "oque": oque,
                                  "grupos": grupos, "linhas": linhas, "erro": erro})


def tipos_no_pg(pg, schema: str) -> dict:
    with pg.cursor() as cur:
        cur.execute("SELECT table_name, column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = %s", (schema,))
        saida = {}
        for tb, col, dt in cur.fetchall():
            saida[(tb, col)] = {"bigint": "bigint", "integer": "bigint", "smallint": "bigint",
                                "double precision": "double", "real": "double",
                                "numeric": "double", "bytea": "bytea"}.get(dt, "text")
        return saida


def contar_orfas(pg, schema, filho, de, pai, para, tipos) -> int | None:
    conds = []
    for a, b in zip(de, para):
        ta, tb = tipos.get((filho, a)), tipos.get((pai, b))
        if ta == tb:
            conds.append(f"p.{q(b)} = c.{q(a)}")
        else:
            conds.append(f"p.{q(b)}::text = c.{q(a)}::text")
    naonulo = " AND ".join(f"c.{q(a)} IS NOT NULL" for a in de)
    sql = (f"SELECT count(*) FROM {q(schema)}.{q(filho)} c WHERE {naonulo} AND NOT EXISTS "
           f"(SELECT 1 FROM {q(schema)}.{q(pai)} p WHERE {' AND '.join(conds)})")
    linha, e = consultar_protegido(pg, sql)
    return linha[0] if linha else None


def ajustar_sequencias(pg, schema: str, tabelas: list[Tabela], extras: dict,
                       res: Resultado) -> None:
    seqs = extras.get("sqlite_sequence") or {}
    with pg.cursor() as cur:
        for t in tabelas:
            c = t.identity
            if not c or t.nome in res.erro_copia:
                continue
            cur.execute(S.SQL("SELECT max({}) FROM {}").format(
                S.Identifier(c.nome), ident(schema, t.nome)))
            mx = cur.fetchone()[0] or 0
            sq_seq = int(seqs.get(t.nome) or 0)
            alvo = max(mx, sq_seq)
            cur.execute("SELECT pg_get_serial_sequence(%s, %s)",
                        (f'{q(schema)}.{q(t.nome)}', c.nome))
            seq = cur.fetchone()[0]
            if alvo > 0:
                cur.execute("SELECT setval(%s, %s, true)", (seq, alvo))
            else:
                cur.execute("SELECT setval(%s, 1, false)", (seq,))
            res.sequencias.append((t.nome, mx, sq_seq if t.nome in seqs else None, alvo + 1))
    pg.commit()


# ===================================================================== conferência

def _linhas_sqlite(sq, t: Tabela, alvos: list[str], ordenar_pk: str | None):
    sel = f"SELECT {', '.join(q(c.nome) for c in t.colunas)} FROM {q(t.nome)}"
    if ordenar_pk:
        sel += f" ORDER BY {q(ordenar_pk)}"
    cs = sq.execute(sel)
    while True:
        lote = cs.fetchmany(LOTE)
        if not lote:
            return
        for linha in lote:
            yield [canon(v, a) for v, a in zip(linha, alvos)]


def _linhas_pg(pg, schema, t: Tabela, alvos: list[str], ordenar_pk: str | None, nome_cur):
    sel = S.SQL("SELECT {} FROM {}").format(
        S.SQL(", ").join(S.Identifier(c.nome) for c in t.colunas), ident(schema, t.nome))
    if ordenar_pk:
        sel = sel + S.SQL(" ORDER BY {}").format(S.Identifier(ordenar_pk))
    with pg.cursor(name=nome_cur) as cur:
        cur.itersize = 20000
        cur.execute(sel)
        for linha in cur:
            yield [canon(v, a) for v, a in zip(linha, alvos)]


def conferir_tabela(sq, pg, schema, t: Tabela, tipos_pg: dict) -> dict:
    alvos = [tipos_pg.get((t.nome, c.nome), c.alvo or "text") for c in t.colunas]
    faltam_no_pg = [c.nome for c in t.colunas if (t.nome, c.nome) not in tipos_pg]
    if faltam_no_pg:
        return {"ok": False, "erro": f"colunas ausentes no PG: {faltam_no_pg}"}
    pos_pk = [i for i, c in enumerate(t.colunas) if c.nome in t.pk]
    pos_pk.sort(key=lambda i: t.pk.index(t.colunas[i].nome))
    if not pos_pk:
        pos_pk = list(range(len(t.colunas)))
    em_fluxo = bool(t.identity) and t.linhas >= FLUXO_A_PARTIR_DE
    ordem = t.identity.nome if em_fluxo else None
    a_it = _linhas_sqlite(sq, t, alvos, ordem)
    b_it = _linhas_pg(pg, schema, t, alvos, ordem, f"conf_{abs(hash(t.nome))}")
    if not em_fluxo:
        def chave(r):
            return tuple(r[i] for i in pos_pk) + tuple(r)
        a_it = iter(sorted(a_it, key=chave))
        b_it = iter(sorted(b_it, key=chave))

    def chave_pk(r):
        if em_fluxo:
            return int(r[pos_pk[0]][1:])
        return tuple(r[i] for i in pos_pk) + (tuple(r) if len(pos_pk) == len(r) else ())

    ha, hb = hashlib.sha256(), hashlib.sha256()
    na = nb = 0
    divergentes = []
    ndiv = 0

    def texto(r):
        return (SEP.join(r) + "\n").encode("utf-8", "surrogatepass")

    def anotar(r, cols):
        if len(divergentes) < MAX_DIVERGENCIAS:
            divergentes.append({"pk": _pk_legivel(r, pos_pk, t), "colunas": cols})

    ra, rb = next(a_it, None), next(b_it, None)
    while ra is not None or rb is not None:
        ka = chave_pk(ra) if ra is not None else None
        kb = chave_pk(rb) if rb is not None else None
        if rb is None or (ra is not None and ka < kb):
            ha.update(texto(ra))
            na += 1
            ndiv += 1
            anotar(ra, ["(só no SQLite)"])
            ra = next(a_it, None)
        elif ra is None or kb < ka:
            hb.update(texto(rb))
            nb += 1
            ndiv += 1
            anotar(rb, ["(só no PG)"])
            rb = next(b_it, None)
        else:
            ha.update(texto(ra))
            hb.update(texto(rb))
            na += 1
            nb += 1
            if ra != rb:
                ndiv += 1
                anotar(ra, [t.colunas[i].nome for i, (x, y) in enumerate(zip(ra, rb)) if x != y])
            ra, rb = next(a_it, None), next(b_it, None)
    pg.commit()
    return {"ok": na == nb and ha.hexdigest() == hb.hexdigest(), "linhas_sqlite": na,
            "linhas_pg": nb, "sha_sqlite": ha.hexdigest(), "sha_pg": hb.hexdigest(),
            "divergentes": divergentes, "n_divergentes": ndiv}


def _pk_legivel(r, pos_pk, t: Tabela) -> str:
    if not t.pk:
        return "(tabela sem PK)"
    return ", ".join(f"{t.colunas[i].nome}={r[i][1:] if r[i] != chr(92) + 'N' else 'NULL'}"
                     for i in pos_pk)


# ===================================================================== corrente de hash

def _hash_ato_local(matricula_numero, tipo, numero, data_ato, teor, hash_anterior):
    """Cópia de `ri_schema.hash_ato`, usada só se o import falhar."""
    def norm(v):
        return "" if v is None else str(v).strip()
    payload = json.dumps({"matricula": norm(matricula_numero), "tipo": norm(tipo).upper(),
                          "numero": int(numero), "data": norm(data_ato),
                          "teor": teor or "", "anterior": hash_anterior or ""},
                         ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def obter_hash_ato():
    try:
        sys.path.insert(0, str(SISTEMA))
        from ri_schema import hash_ato  # type: ignore
        return hash_ato, "ri_schema.hash_ato (importada do sistema)"
    except Exception as e:  # noqa: BLE001
        return _hash_ato_local, f"cópia local (import falhou: {msg(e)})"


SQL_CORRENTE = ("SELECT a.id, a.matricula_id, m.numero, a.tipo, a.numero, a.data_ato, a.teor, "
                "a.hash_ato, a.hash_anterior FROM ri_atos a "
                "LEFT JOIN ri_matriculas m ON m.id = a.matricula_id "
                "ORDER BY a.matricula_id, a.id")


def avaliar_corrente(linhas: Iterable, hash_fn) -> dict:
    total = confere = nao_confere = elo_ok = elo_quebrado = sem_numero = 0
    recalc: dict = {}
    nao_conferem: list = []
    elos_quebrados: list = []
    por_matricula: dict = {}
    mid_ant, hash_ant = object(), None
    for (aid, mid, mnum, tipo, num, data, teor, h, hant) in linhas:
        total += 1
        if mid != mid_ant:
            mid_ant, hash_ant = mid, None
        por_matricula.setdefault(mid, []).append((aid, mnum, tipo, num, data, teor, h))
        try:
            r = hash_fn(mnum, tipo, int(num), data or "", teor or "", hant)
        except (TypeError, ValueError):
            r = None
            sem_numero += 1
        recalc[aid] = (r, h, hant)
        if r is not None and r == h:
            confere += 1
        else:
            nao_confere += 1
            nao_conferem.append(aid)
        if (hant or None) == (hash_ant or None):
            elo_ok += 1
        else:
            elo_quebrado += 1
            elos_quebrados.append(aid)
        hash_ant = h
    # como a tela de integridade confere (ri_web: ORDER BY numero, tipo; o anterior
    # é o hash GRAVADO do ato de antes na lista)
    quebras_tela = []
    for mid, atos in por_matricula.items():
        def k(a):
            n = a[3]
            return (0, int(n)) if isinstance(n, int) or (isinstance(n, str) and n.lstrip("-").isdigit()) else (1, str(n)), str(a[2] or "")
        anterior = None
        for (aid, mnum, tipo, num, data, teor, h) in sorted(atos, key=k):
            try:
                esperado = hash_fn(mnum, tipo, int(num), data or "", teor or "", anterior)
            except (TypeError, ValueError):
                esperado = None
            if esperado != h:
                quebras_tela.append(aid)
            anterior = h
    return {"total": total, "confere": confere, "nao_confere": nao_confere,
            "elo_ok": elo_ok, "elo_quebrado": elo_quebrado, "sem_numero": sem_numero,
            "matriculas": len(por_matricula), "nao_conferem": nao_conferem,
            "elos_quebrados": elos_quebrados, "quebras_tela": sorted(quebras_tela),
            "recalc": recalc}


def conferir_corrente(sq, pg, schema) -> dict:
    hash_fn, origem = obter_hash_ato()
    amostra = ("4011", "R", 1, "2026-08-18", "x", None)
    if hash_fn(*amostra) != _hash_ato_local(*amostra):
        origem += " — ATENÇÃO: difere da cópia local"
    a = avaliar_corrente(sq.execute(SQL_CORRENTE), hash_fn)
    with pg.cursor() as cur:
        cur.execute(S.SQL("SET LOCAL search_path TO {}").format(S.Identifier(schema)))
        cur.execute(SQL_CORRENTE)
        b = avaliar_corrente(cur.fetchall(), hash_fn)
    pg.commit()
    iguais = a["recalc"] == b["recalc"]
    difs = [k for k in set(a["recalc"]) | set(b["recalc"])
            if a["recalc"].get(k) != b["recalc"].get(k)]
    for x in (a, b):
        x.pop("recalc")
    return {"funcao": origem, "sqlite": a, "pg": b, "recalculo_identico": iguais,
            "atos_diferentes": sorted(difs)[:MAX_DIVERGENCIAS], "n_atos_diferentes": len(difs)}


# ===================================================================== relatório

def fmt(n) -> str:
    return "—" if n is None else f"{n:,}".replace(",", ".")


def fmt_t(s: float) -> str:
    return f"{s:.1f} s" if s < 120 else f"{int(s // 60)} min {int(s % 60)} s"


def escrever_relatorio(caminho: Path, args, tabelas: list[Tabela], extras: dict,
                       res: Resultado, inicio: datetime, total_s: float) -> None:
    conf = res.conferencia
    ok = [t for t in tabelas if conf.get(t.nome, {}).get("ok")]
    div = [t for t in tabelas if t.nome in conf and not conf[t.nome].get("ok")]
    linhas_sq = sum(t.linhas for t in tabelas)
    linhas_pg = sum(conf.get(t.nome, {}).get("linhas_pg", 0) or 0 for t in tabelas)
    L = []
    w = L.append
    w("# Migração dos dados SQLite → PostgreSQL — relatório medido")
    w("")
    w(f"Gerado por `sistema/tools/migrar_para_postgres.py` em "
      f"{inicio.strftime('%d/%m/%Y %H:%M')} (duração total {fmt_t(total_s)}).")
    w("")
    w(f"- Origem: `{args.sqlite}` (cópia da produção; {fmt(res.tamanho_sqlite)} bytes). "
      "A produção não foi aberta.")
    w(f"- Destino: PostgreSQL, schema `{args.schema}` "
      f"({'recriado' if args.recriar else 'só conferido' if args.so_conferir else 'existente'}).")
    w(f"- Objetos no `sqlite_master`: " + ", ".join(f"{k} {v}" for k, v in
                                               sorted(extras['objetos'].items()))
      + " (as tabelas incluem a interna `sqlite_sequence`, que não é copiada: "
        "ela vira o ponto de partida das colunas identity).")
    w("")
    w("## Resumo")
    w("")
    w("| | |")
    w("|---|---|")
    w(f"| Tabelas de usuário | **{len(tabelas)}** |")
    w(f"| Linhas no SQLite | **{fmt(linhas_sq)}** |")
    w(f"| Linhas no PostgreSQL | **{fmt(linhas_pg)}** |")
    w(f"| Tabelas conferidas OK (contagem **e** soma de verificação) | **{len(ok)}** |")
    w(f"| Tabelas divergentes | **{len(div)}** |")
    w(f"| Tabelas que não copiaram | **{len(res.erro_copia)}** |")
    w(f"| Colunas que viraram TEXT por dado fora do tipo | "
      f"**{sum(1 for t in tabelas for c in t.colunas if c.perfil.get('motivo'))}** |")
    w(f"| PK / UNIQUE / índices criados | {res.pks_criadas} / {res.uniques_criados} / "
      f"{res.indices_criados} |")
    w(f"| FKs criadas (NOT VALID) / com linhas órfãs | {res.fk_criadas} / {len(res.fk_orfas)} |")
    cr = res.corrente
    if cr:
        w(f"| Corrente de hash do RI | "
          f"{'**confere** dos dois lados' if cr.get('recalculo_identico') else '**DIVERGE**'}"
          f" — {fmt(cr['pg']['total'])} atos, {fmt(cr['pg']['confere'])} com o hash "
          f"gravado reproduzido |")
    w(f"| Tamanho no PostgreSQL (tabelas + índices + TOAST) | "
      f"**{res.tamanho_pg / 1024 / 1024:.1f} MB** (SQLite: "
      f"{res.tamanho_sqlite / 1024 / 1024:.1f} MB) |")
    w("")
    w("### Tempo de cada etapa")
    w("")
    w("| etapa | tempo |")
    w("|---|---|")
    for k, v in res.tempos.items():
        w(f"| {k} | {fmt_t(v)} |")
    w(f"| **total** | **{fmt_t(total_s)}** |")
    if res.copia:
        w("")
        w("As cinco tabelas mais pesadas na cópia:")
        w("")
        for nome, (n, s) in sorted(res.copia.items(), key=lambda x: -x[1][1])[:5]:
            w(f"- `{nome}`: {fmt(n)} linhas em {fmt_t(s)} "
              f"({n / s if s else 0:,.0f} linhas/s)".replace(",", "."))
    w("")
    w("## Conferência por tabela")
    w("")
    w("Contagem de linhas e sha256 do texto canônico de cada linha, na ordem da chave "
      "(a ordem é decidida em Python, igual dos dois lados). A tabela inteira, com as "
      "somas, está no fim deste relatório.")
    w("")
    if div:
        w("### Tabelas DIVERGENTES")
        w("")
        for t in div:
            c = conf[t.nome]
            if c.get("erro"):
                w(f"- `{t.nome}`: {c['erro']}")
                continue
            w(f"- `{t.nome}`: SQLite {fmt(c['linhas_sqlite'])} × PG {fmt(c['linhas_pg'])} "
              f"linhas; {fmt(c['n_divergentes'])} linha(s) diferente(s). Primeiras:")
            for d in c["divergentes"]:
                w(f"  - {d['pk']} — colunas: {', '.join(d['colunas'])}")
            if t.nome in PROBLEMAS_DE_VALOR:
                w("  - a diferença é o valor que o PostgreSQL não guarda como está (seção "
                  "seguinte): texto do PostgreSQL não aceita o caractere NUL, e ele foi "
                  "trocado por U+FFFD. A linha está lá; o caractere, não.")
        w("")
    else:
        w("**Nenhuma tabela divergente**: todas as tabelas têm a mesma contagem e a mesma "
          "soma de verificação nos dois bancos.")
        w("")
    if res.erro_copia:
        w("### Tabelas que não copiaram")
        w("")
        for k, v in res.erro_copia.items():
            w(f"- `{k}`: {v}")
        w("")
    if PROBLEMAS_DE_VALOR:
        w("### Valores que o PostgreSQL não guarda como estão")
        w("")
        for tb, d in PROBLEMAS_DE_VALOR.items():
            for tipo, n in d.items():
                w(f"- `{tb}`: {fmt(n)} × {tipo}")
        w("")
    w("## Colunas que viraram TEXT (ou mudaram de tipo) por dado fora do tipo declarado")
    w("")
    viradas = [(t, c) for t in tabelas for c in t.colunas if c.perfil.get("motivo")]
    if not viradas:
        w("Nenhuma: todo valor cabe no tipo declarado da sua coluna.")
    else:
        w("Os exemplos mostram por extenso só o vazio, números e datas; o resto aparece "
          "como «texto de N caracteres» (pode ser dado pessoal).")
        w("")
        w("| coluna | declarada | criada como | valores fora do tipo | exemplos (valor · tipo · vezes) |")
        w("|---|---|---|---|---|")
        for t, c in viradas:
            p = c.perfil
            fora = {k: p[k] for k in ("integer", "real", "text", "blob")
                    if p[k] and k != esperado(c)}
            fora_txt = ", ".join(f"{k} {fmt(v)}" for k, v in fora.items())
            if p.get("vazio"):
                fora_txt += f" (dos quais vazio '' {fmt(p['vazio'])})"
            ex = "; ".join(f"{a} · {tp} · {fmt(n)}" for a, tp, n in p.get("exemplos", []))
            w(f"| `{t.nome}.{c.nome}` | {c.tipo_decl or '(sem tipo)'} | "
              f"{PG_TIPO[c.alvo]} | {fora_txt} | {ex} |")
    sem_tipo = [(t, c) for t in tabelas for c in t.colunas
                if c.afinidade in ("BLOB", "NUMERIC") and not c.tipo_decl.upper().startswith("BLOB")]
    if sem_tipo:
        w("")
        w("Colunas sem tipo declarado ou de tipo «numérico» do SQLite (DATE, BOOLEAN…), "
          "decididas pelo dado:")
        w("")
        for t, c in sem_tipo:
            w(f"- `{t.nome}.{c.nome}` ({c.tipo_decl or 'sem tipo'}) → {PG_TIPO[c.alvo]}")
    w("")
    w("## Defaults e cláusulas removidos")
    w("")
    itens = (res.defaults_removidos + res.clausulas_removidas + extras["on_conflict"]
             + [f"{x} (WITHOUT ROWID removido)" for x in extras["sem_rowid"]]
             + [f"{x} (removido)" for x in extras["collate"]]
             + [f"{x}: coluna gerada/oculta não copiada" for x in extras["geradas"]])
    if itens:
        for x in dict.fromkeys(itens):
            w(f"- {x}")
    else:
        w("Nenhum.")
    if extras["collate"]:
        w("")
        w("> `COLLATE NOCASE` removido muda o que conta como repetido num UNIQUE: no SQLite "
          "«Ana» e «ana» colidiam; no PostgreSQL não. A camada de compatibilidade precisa "
          "decidir (índice único em `lower(...)`, por exemplo).")
    if res.notnull_falhou or res.pk_falhou or res.check_falhou or res.check_violado:
        w("")
        w("### Restrições que não entraram como no SQLite")
        w("")
        for x in res.notnull_falhou:
            w(f"- NOT NULL: {x}")
        for x in res.pk_falhou:
            w(f"- PRIMARY KEY: {x}")
        for x in res.check_falhou:
            w(f"- CHECK: {x}")
        for x in res.check_violado:
            w(f"- CHECK: {x}")
    w("")
    w("## FKs com linhas órfãs")
    w("")
    w(f"{res.fk_criadas} FKs criadas como `NOT VALID` (valem para o que entrar daqui em "
      "diante; o que já existe não foi reprovado). Linhas órfãs = valor preenchido na "
      "coluna da FK sem a linha correspondente na tabela-mãe.")
    w("")
    if res.fk_orfas:
        w("| FK | linhas órfãs |")
        w("|---|---|")
        for rot, n in sorted(res.fk_orfas, key=lambda x: -(x[1] or 0)):
            w(f"| `{rot}` | {fmt(n)} |")
    else:
        w("Nenhuma FK com linha órfã.")
    if res.fk_falhou:
        w("")
        w("FKs que não puderam ser criadas:")
        w("")
        for x in res.fk_falhou:
            w(f"- `{x}`")
    w("")
    w("## Problemas de UNIQUE (duplicatas que impediram o índice único)")
    w("")
    if res.unique_duplicatas:
        w("| tabela | colunas | restrição | grupos repetidos | linhas nesses grupos | erro |")
        w("|---|---|---|---|---|---|")
        for d in res.unique_duplicatas:
            w(f"| `{d['tabela']}` | {', '.join(d['colunas'])} | {d['oque']} | "
              f"{fmt(d['grupos'])} | {fmt(d['linhas'])} | {d['erro'][:120]} |")
        w("")
        w("Onde o único não entrou, foi criado um índice comum com o mesmo nome, para a "
          "consulta não ficar sem índice.")
    else:
        w("Nenhum: todas as PKs, UNIQUEs e índices únicos foram criados.")
    if res.indice_falhou:
        w("")
        w("Índices que não puderam ser criados:")
        w("")
        for x in res.indice_falhou:
            w(f"- {x}")
        if any("maximum size" in x for x in res.indice_falhou):
            w("")
            w("> O índice B-tree do PostgreSQL não aceita chave maior que ~8 KB (um terço "
              "da página); o SQLite aceita. A coluna precisa de outro índice (por exemplo "
              "sobre `md5(coluna)` ou `left(coluna, 200)`) — decisão da camada/esquema.")
    w("")
    w("## Sequências (colunas identity)")
    w("")
    dif = [s for s in res.sequencias if s[2] is not None and s[2] != s[1]]
    w(f"{len(res.sequencias)} colunas identity ajustadas para seguir de max(id)+1 — ou do "
      "`sqlite_sequence`, quando ele é maior (o AUTOINCREMENT do SQLite não reaproveita "
      "número de linha apagada).")
    if dif:
        w("")
        w("Tabelas em que o `sqlite_sequence` está à frente do maior id (houve linha "
          "apagada no fim):")
        w("")
        for nome, mx, sseq, prox in dif:
            w(f"- `{nome}`: max(id) {fmt(mx)}, sqlite_sequence {fmt(sseq)} → próximo {fmt(prox)}")
    w("")
    w("## Corrente de hash dos atos do Registro de Imóveis")
    w("")
    if not cr:
        w("Não conferida.")
    else:
        w(f"Função: {cr['funcao']}. Cada ato guarda `hash_ato` = sha256 de "
          "{matrícula, tipo, número, data, teor, anterior}, e `hash_anterior` = o hash do "
          "ato lavrado antes na mesma matrícula (`ri_web`: o último por `id`).")
        w("")
        w("| | SQLite | PostgreSQL |")
        w("|---|---|---|")
        for k, rot in (("total", "atos"), ("matriculas", "matrículas com ato"),
                       ("confere", "hash recalculado = gravado (com o `hash_anterior` gravado)"),
                       ("nao_confere", "hash recalculado ≠ gravado"),
                       ("elo_ok", "elo `hash_anterior` = hash do ato anterior (por id)"),
                       ("elo_quebrado", "elo quebrado"),
                       ("sem_numero", "ato sem número (não recalculável)")):
            w(f"| {rot} | {fmt(cr['sqlite'][k])} | {fmt(cr['pg'][k])} |")
        w(f"| quebras como a tela de integridade as vê (ordem número, tipo) | "
          f"{fmt(len(cr['sqlite']['quebras_tela']))} | {fmt(len(cr['pg']['quebras_tela']))} |")
        w("")
        if cr["recalculo_identico"]:
            w("**O recálculo lendo do PostgreSQL é idêntico, ato por ato, ao recálculo lendo "
              "do SQLite** (mesmo hash recalculado, mesmo gravado, mesmo anterior para os "
              f"{fmt(cr['pg']['total'])} atos): a migração não alterou nenhum byte que "
              "entra na corrente.")
        else:
            w(f"**DIVERGE**: {fmt(cr['n_atos_diferentes'])} atos com resultado diferente "
              f"entre os dois lados. Primeiros ids: {cr['atos_diferentes']}")
        if cr["pg"]["nao_confere"] or cr["pg"]["elo_quebrado"]:
            w("")
            w("Os atos que não conferem **já não conferiam no SQLite** (é dado da produção, "
              "e não efeito da migração) — ids: ")
            w("")
            w(f"- hash ≠ gravado: {cr['pg']['nao_conferem'][:60]}"
              + (" …" if len(cr['pg']['nao_conferem']) > 60 else ""))
            w(f"- elo quebrado: {cr['pg']['elos_quebrados'][:60]}"
              + (" …" if len(cr['pg']['elos_quebrados']) > 60 else ""))
    w("")
    w("## Anexo — conferência de todas as tabelas")
    w("")
    w("| tabela | linhas SQLite | linhas PG | sha256 (16 primeiros) | resultado |")
    w("|---|---|---|---|---|")
    for t in tabelas:
        c = conf.get(t.nome, {})
        res_txt = "OK" if c.get("ok") else ("não conferida" if not c else "**DIVERGE**")
        if c.get("ok") and t.nome in PROBLEMAS_DE_VALOR:
            res_txt = "OK, com ressalva (ver valores)"
        w(f"| `{t.nome}` | {fmt(c.get('linhas_sqlite', t.linhas))} | "
          f"{fmt(c.get('linhas_pg'))} | `{(c.get('sha_pg') or '')[:16]}` | {res_txt} |")
    w("")
    caminho.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")


# ===================================================================== principal

def principal(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sqlite", required=True)
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--schema", required=True)
    ap.add_argument("--recriar", action="store_true")
    ap.add_argument("--so-conferir", action="store_true")
    ap.add_argument("--so-tabela", default="", metavar="NOME",
                    help="limita cópia/conferência a uma tabela")
    ap.add_argument("--sem-corrente", action="store_true",
                    help="não recalcula a corrente de hash do RI (etapa 6)")
    ap.add_argument("--relatorio", default=str(RELATORIO_PADRAO))
    args = ap.parse_args(argv)
    if psycopg is None:
        print("psycopg (3) não está instalado neste Python.", file=sys.stderr)
        return 2
    caminho = Path(args.sqlite).resolve()
    if "programdata" in str(caminho).lower():
        print("Recuso: isto parece o banco da produção. Use uma cópia.", file=sys.stderr)
        return 2
    if args.recriar and args.schema.lower() == "public":
        print("Recuso recriar o schema public.", file=sys.stderr)
        return 2
    if args.recriar and args.so_conferir:
        print("--recriar e --so-conferir não andam juntos.", file=sys.stderr)
        return 2

    inicio = datetime.now()
    t_total = time.perf_counter()
    res = Resultado()
    res.tamanho_sqlite = caminho.stat().st_size
    sq = sqlite3.connect(f"file:{caminho.as_posix()}?mode=ro", uri=True)
    sq.text_factory = _fabrica_de_texto
    pg = psycopg.connect(args.dsn, autocommit=False)
    with pg.cursor() as cur:
        cur.execute("SET synchronous_commit = off")
    pg.commit()

    with Etapa(res, "1. ler o esquema do SQLite"):
        tabelas, extras = ler_esquema(sq)
        if args.so_tabela:
            nomes = {args.so_tabela.strip()}
            tabelas = [t for t in tabelas if t.nome in nomes]
            if not tabelas:
                print(f"Tabela {args.so_tabela!r} não encontrada no SQLite.", file=sys.stderr)
                return 2
            log(f"   filtro --so-tabela: {args.so_tabela}")
        log(f"   {len(tabelas)} tabelas")
    with Etapa(res, "2. perfilar as colunas"):
        _TABELA_ATUAL[0] = ""
        for t in tabelas:
            perfilar(sq, t)
        log(f"   {sum(t.linhas for t in tabelas)} linhas")

    if not args.so_conferir:
        with pg.cursor() as cur:
            cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema=%s",
                        (args.schema,))
            existentes = cur.fetchone()[0]
        if existentes and not args.recriar:
            print(f"O schema {args.schema} já tem {existentes} tabelas. Use --recriar "
                  f"(ou --so-conferir).", file=sys.stderr)
            return 2
        with Etapa(res, "3a. criar o schema e as tabelas"):
            with pg.cursor() as cur:
                if args.recriar:
                    cur.execute(S.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        S.Identifier(args.schema)))
                cur.execute(S.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                    S.Identifier(args.schema)))
            pg.commit()
            criar_tabelas(pg, args.schema, tabelas, res)
        with Etapa(res, "3b. copiar os dados (COPY)"):
            for t in tabelas:
                copiar_tabela(sq, pg, args.schema, t, res)
        with Etapa(res, "3c. NOT NULL, PK, UNIQUE, índices, CHECK e FKs"):
            ligar_restricoes(pg, args.schema, tabelas, res, extras)
        with Etapa(res, "4. ajustar as sequências"):
            ajustar_sequencias(pg, args.schema, tabelas, extras, res)
        with Etapa(res, "4b. ANALYZE"):
            pg.autocommit = True
            with pg.cursor() as cur:
                for t in tabelas:
                    cur.execute(S.SQL("ANALYZE {}").format(ident(args.schema, t.nome)))
            pg.autocommit = False

    with Etapa(res, "5. conferir contagem e soma de verificação"):
        tipos = tipos_no_pg(pg, args.schema)
        for t in tabelas:
            _TABELA_ATUAL[0] = t.nome if args.so_conferir else ""
            try:
                res.conferencia[t.nome] = conferir_tabela(sq, pg, args.schema, t, tipos)
            except Exception as e:  # noqa: BLE001
                pg.rollback()
                res.conferencia[t.nome] = {"ok": False, "erro": msg(e)}
            if not res.conferencia[t.nome]["ok"]:
                log(f"   DIVERGE: {t.nome}: {res.conferencia[t.nome].get('erro') or ''}")
        log(f"   {sum(1 for v in res.conferencia.values() if v['ok'])} de {len(tabelas)} OK")
    if not args.sem_corrente:
        with Etapa(res, "6. corrente de hash do RI"):
            _TABELA_ATUAL[0] = ""
            try:
                res.corrente = conferir_corrente(sq, pg, args.schema)
                log(f"   recálculo idêntico: {res.corrente['recalculo_identico']}; "
                    f"confere no PG {res.corrente['pg']['confere']} de {res.corrente['pg']['total']}")
            except Exception as e:  # noqa: BLE001
                pg.rollback()
                log(f"   corrente não conferida: {msg(e)}")
    else:
        log("   etapa 6 omitida (--sem-corrente)")
    with Etapa(res, "7. medir o tamanho no PostgreSQL"):
        with pg.cursor() as cur:
            cur.execute("SELECT coalesce(sum(pg_total_relation_size(c.oid)), 0) FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = %s AND c.relkind IN ('r', 'm', 'p')", (args.schema,))
            res.tamanho_pg = int(cur.fetchone()[0])
        pg.commit()

    total = time.perf_counter() - t_total
    escrever_relatorio(Path(args.relatorio), args, tabelas, extras, res, inicio, total)
    log(f"relatório: {args.relatorio}")
    pg.close()
    sq.close()
    corrente_ok = args.sem_corrente or (
        res.corrente and res.corrente.get("recalculo_identico"))
    tudo_ok = (all(v.get("ok") for v in res.conferencia.values()) and not res.erro_copia
               and corrente_ok)
    return 0 if tudo_ok else 1


if __name__ == "__main__":
    sys.exit(principal())
