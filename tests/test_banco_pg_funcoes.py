"""As funções do SQLite emuladas no PostgreSQL (`banco_pg_funcoes.sql`),
comparadas com o `sqlite3` do Python — entrada por entrada.

A régua é o SQLite da PRODUÇÃO (3.45.1, o do Python 3.11.9 do Windows): para
cada função, uma grade grande de entradas (datas nos formatos que o SQLite
aceita e nos que ele recusa, números, modificadores, formatos, nulos, vazios,
nomes com acento, caixa e espaço) é calculada NOS DOIS, e o teste exige o
mesmo resultado — o mesmo texto, o mesmo número, o mesmo NULL.

ONDE O PYTHON NÃO RODA A 3.45.1, A RÉGUA É A MEDIÇÃO GRAVADA DELA
(`tests/fixtures/regua_sqlite_3_45_1.json`). Achado em 19/10/2026: o Mac da
migração roda o SQLite 3.53.4, que da 3.46 em diante aceita 'floor'/'ceiling'
e %G %g %U %V, ignora 'localtime'/'utc' repetidos e 'utc' depois de 'now',
corta a fração abaixo do milissegundo em vez de arredondar, arredonda o
printf('%.0f') de outro jeito e escreve o real com 17 dígitos. Comparado com
ele, o teste dava 1.775 divergências — a distância entre duas versões do
SQLite, não a do PostgreSQL até a produção (com a 3.45.1, zero). Onde o Python
roda a 3.45.1, a comparação continua ao vivo e confere também que a medição
gravada ainda é a dela.

Pula sem `CG_PG_DSN`. Cria um schema temporário, instala o .sql nele (o
`search_path` fica «schema, public», como na instalação de verdade) e apaga
o schema no fim.

Também roda como script avulso, e então imprime o resumo da comparação:
    venv\\Scripts\\python.exe sistema\\tests\\test_banco_pg_funcoes.py
e, com um Python que rode o SQLite 3.45.1, regrava a medição:
    python tests/test_banco_pg_funcoes.py --gravar-regua
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import sqlite3
import sys
import time as _time
import uuid
from pathlib import Path

try:
    import pytest
except ImportError:  # script avulso sem pytest
    pytest = None

try:
    import psycopg
except ImportError:
    psycopg = None

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
ARQUIVO_SQL = RAIZ / "banco_pg_funcoes.sql"
DSN = os.environ.get("CG_PG_DSN", "").strip()

# O SQLite que a produção roda, e o que ele respondeu às grades (ver o topo).
REGUA_DA_PRODUCAO = "3.45.1"
ARQUIVO_REGUA = RAIZ / "tests" / "fixtures" / "regua_sqlite_3_45_1.json"
COMO_GRAVAR = ("com CG_PG_DSN e um Python que rode o SQLite 3.45.1: "
               "python tests/test_banco_pg_funcoes.py --gravar-regua")

if pytest is not None:
    pytestmark = pytest.mark.skipif(
        not DSN or psycopg is None,
        reason="sem CG_PG_DSN (ou sem psycopg): a comparação precisa do PostgreSQL")


# ============================================================ o ambiente

def _impressao(consultas) -> str:
    """O que identifica uma grade: o texto exato de cada consulta ao SQLite.
    Se a grade muda, a medição gravada deixa de valer para ela."""
    bruto = json.dumps([[sql, list(params)] for sql, params in consultas], ensure_ascii=False)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def _ler_regua():
    if not ARQUIVO_REGUA.exists():
        return None
    return json.loads(ARQUIVO_REGUA.read_text(encoding="utf-8"))


class Ambiente:
    """Um schema temporário com as funções instaladas, um SQLite em memória
    e a régua (o SQLite da produção, ao vivo ou medido)."""

    def __init__(self, gravando: bool = False) -> None:
        self.ao_vivo = sqlite3.sqlite_version == REGUA_DA_PRODUCAO
        self.gravada = None if gravando else _ler_regua()
        self.medidas: dict = {}
        # 'localtime' do SQLite usa o fuso do Windows; o do PostgreSQL é o
        # da sessão. Para comparar, a sessão recebe o deslocamento daqui — ou,
        # nas datas medidas, o da máquina em que a régua foi medida.
        desloc = _dt.datetime.now().astimezone().utcoffset()
        self.fuso_daqui = int(desloc.total_seconds() // 60)
        self.fuso_da_regua = (self.gravada["fuso_minutos"]
                              if self.gravada and not self.ao_vivo else self.fuso_daqui)
        self.pg = psycopg.connect(DSN, autocommit=True)
        self.schema = "cg_teste_funcoes_" + uuid.uuid4().hex[:10]
        with self.pg.cursor() as cur:
            cur.execute(f'CREATE SCHEMA "{self.schema}"')
            cur.execute(f'SET search_path TO "{self.schema}"')
            cur.execute(ARQUIVO_SQL.read_text(encoding="utf-8"))
            cur.execute(f'SET search_path TO "{self.schema}", public')
        self.no_fuso(self.fuso_daqui)
        # A RÉGUA é o sqlite3 de verdade, em memória — de propósito: não trocar
        # por conexao_de_teste(), que no backend pg compararia o PostgreSQL com ele mesmo.
        self.sqlite = sqlite3.connect(":memory:")

    def no_fuso(self, minutos: int) -> None:
        sinal = "-" if minutos < 0 else "+"
        with self.pg.cursor() as cur:
            cur.execute(f"SET TIME ZONE INTERVAL '{sinal}{abs(minutos) // 60:02d}:"
                        f"{abs(minutos) % 60:02d}' HOUR TO MINUTE")

    def esperados(self, grade: str, consultas: list) -> list:
        """A resposta do SQLite da PRODUÇÃO a cada consulta `(sql, params)`.

        Ao vivo onde o Python daqui roda a 3.45.1 — e aí confere também que a
        medição gravada continua sendo a dele, para ela não apodrecer calada.
        Nas outras máquinas, a medição gravada; se a grade mudou depois dela,
        o teste falha pedindo a regravação, em vez de comparar com o SQLite
        daqui (que mediria a distância entre duas versões do SQLite)."""
        impressao = _impressao(consultas)
        gravada = ((self.gravada or {}).get("grades") or {}).get(grade)
        if gravada is not None and gravada.get("impressao") != impressao:
            gravada = None
        if not self.ao_vivo:
            assert gravada is not None, (
                f"a grade «{grade}» não está medida no SQLite {REGUA_DA_PRODUCAO} (o daqui é o "
                f"{sqlite3.sqlite_version}): regrave {ARQUIVO_REGUA.name} {COMO_GRAVAR}")
            return list(gravada["valores"])
        valores = [self.lite(sql, params) for sql, params in consultas]
        self.medidas[grade] = {"impressao": impressao, "valores": valores}
        if gravada is not None and self.fuso_daqui == self.gravada["fuso_minutos"]:
            difere = sum(1 for g, v in zip(gravada["valores"], valores) if g != v)
            assert not difere, (
                f"{difere} valores da grade «{grade}» em {ARQUIVO_REGUA.name} não são os do "
                f"SQLite {REGUA_DA_PRODUCAO} daqui: regrave {COMO_GRAVAR}")
        return valores

    def fechar(self) -> None:
        try:
            with self.pg.cursor() as cur:
                cur.execute(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE')
        finally:
            self.pg.close()
            self.sqlite.close()

    def lite(self, sql: str, params=()):
        try:
            return self.sqlite.execute(sql, params).fetchone()[0]
        except sqlite3.Error as erro:
            return f"<ERRO {type(erro).__name__}>"

    def pg1(self, sql: str, params=None):
        with self.pg.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()[0]


# ============================================================ as grades

VALORES_TEXTO = [
    "2024-01-01", "2024-02-29", "2023-02-29", "2023-02-31", "2024-04-31",
    "2024-12-31 23:59:59", "2024-01-01 10:00", "2024-01-01T10:00:00",
    "2024-01-01 10:00:00.123", "2024-01-01 10:00:00.9996", "2024-01-01 10:00:59.9996",
    "2024-01-01 10:00:00.1235", "2024-01-01 10:00:00.0005", "2024-01-01 10:00:00.",
    "2026-10-15T10:20:30.123456", "2026-10-15 10:20:30.123456+00:00",
    "2024-01-01 10:00:00Z", "2024-01-01 10:00:00z", "2024-01-01 10:00:00-03:00",
    "2024-01-01 10:00 +05:30", "2024-01-01 10:00+0300", "2024-01-01 10:00+15:00",
    "2024-01-01 24:00", "2024-01-01 24:00+01:00", "2024-01-01 24:00Z", "2024-01-01  T 10:00",
    "2024-01-01T", "2024-01-01 ", " 2024-01-01", "2024-1-01", "2024-13-01", "2024-00-10",
    "2024-01-32", "2024-01-01x", "0000-01-01", "-0001-06-15", "-4713-11-24 12:00:00",
    "9999-12-31 23:59:59", "9999-12-31 23:59:59.999", "1582-10-10", "1900-02-28",
    "2000-02-29", "1969-12-31 23:59:59", "2038-01-19 03:14:08",
    "10:00", "10:00:30", "10:00:30.5", "23:59:59.999", "24:00", "25:00", "10:60",
    "10:00:61", "1:00", "10:00 -03:00",
    # a forma canônica, que date()/datetime() recortam sem a máquina de estado
    "2026-10-15 10:20:30", "2026-10-15T10:20", "2024-02-28 23:59:59.999",
    "2024-02-28 23:59:59.9999", "2024-01-29 10:00", "2024-03-28 00:00:00.000001",
    "2024-03-28 23:59", "2024-03-28 23:60", "2024-03-28 23:59:60", "2024-03-28 1:00",
    "2024-01-31 10:00", "2024-04-30", "2024-04-31 10:00", "2024-02-29 10:00",
    "2023-02-29 10:00", "2000-02-29", "1900-02-29", "0000-02-29", "2024-12-31T23:59:59",
    "2024-01-31 24:00", "2024-06-30 23:59:59.5",
    "2460000.5", " 2460000.5 ", "2460000.5x", "1e5", ".5", "+2460000", "-1",
    "5373484.4", "5373484.5", "1700000000", "1e400", "", "abc", "nOw!",
]
# número = REAL ou INTEGER do SQLite (dia juliano; segundos com 'unixepoch')
VALORES_NUMERO = [2460000.5, 2460000, 0, -1, 0.5, 5373484.49, 5373484.5,
                  1700000000, 1700000000.5, -86400, 1e10, 2460310.916678240]

MODIFICADORES = [
    [], ["+1 day"], ["-1 days"], ["+1.5 days"], ["-365 days"], ["+0 days"],
    ["+1 hour"], ["+90 minutes"], ["-30 seconds"], ["+0.5 seconds"], ["-0.5 seconds"],
    ["+1 month"], ["-1 month"], ["+13 months"], ["-13 months"], ["+1.5 months"],
    ["-2.5 months"], ["+1 year"], ["-1.25 years"], ["+1 DAYS"], ["+1  day"],
    ["+1days"], ["+1 day "], [" +1 day"], ["1 day"], ["+1e1 days"], ["+.5 days"],
    ["+5. days"], ["+1 dayss"], ["+1 fortnight"], ["+6000000 days"],
    ["start of month"], ["start of year"], ["start of day"], ["START OF MONTH"],
    ["start of week"], ["weekday 0"], ["weekday 1"], ["weekday 6"], ["weekday 7"],
    ["weekday 1.5"], ["weekday  3 "], ["Weekday 2"], ["unixepoch"], ["auto"],
    ["julianday"], ["subsec"], ["subsecond"], ["+01:30"], ["-01:30"], ["10:00"],
    ["+24:00"], ["+1:30"], ["+01:30:15.5"], ["+0001-01-01"], ["-0001-02-03"],
    ["+0001-01-01 01:00"], ["-0000-00-01 12:00"], ["+0001-12-01"], ["+00001-01-01"],
    ["start of month", "+1 month", "-1 day"], ["+1 month", "-1 day"],
    ["weekday 0", "-6 days"], ["start of year", "+59 days"],
    ["+1 day", "unixepoch"], ["unixepoch", "+1 day"], ["auto", "+1 day"],
    ["start of day", "subsec"],
    ["localtime"], ["utc"], ["localtime", "start of day", "utc"],
    ["unixepoch", "localtime"], ["localtime", "localtime"], ["utc", "utc"],
    [None], [""], ["floor"], ["ceiling"], ["+"], ["-"], ["start of"],
]

FORMATOS = [
    "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%f", "%j", "%J", "%s", "%S", "%w", "%W",
    "%Y", "%m", "%d", "%H", "%M", "%%", "%Q", "%Y%", "texto %Y fim", "", "%e",
    "%F", "%T", "%H:%M", "%Y-%m-%dT%H:%M:%fZ", "%%Y", "sem formato",
    # os da 3.45.1 medidos um a um, e os quatro que ela NÃO tem (%G %g %U %V)
    "%I|%k|%l|%p|%P|%R|%u", "%G", "%g", "%U", "%V", "%E", "%c",
]

# Datas com 'localtime'/'utc' só no intervalo em que a regra de fuso do
# Windows e a da sessão coincidem com certeza (o SQLite troca o ano fora de
# 1970..2038, e o fuso do Brasil já teve horário de verão).
_COM_FUSO = {"localtime", "utc"}


def _usa_fuso(mods) -> bool:
    return any((m or "").lower() in _COM_FUSO for m in mods)


def _valor_seguro_para_fuso(v) -> bool:
    if isinstance(v, str):
        return v[:4].isdigit() and "2020" <= v[:4] <= "2030" and v[4:5] == "-"
    return isinstance(v, (int, float)) and 2458849.5 <= v <= 2462502.5


def _casos_de_data():
    casos = []
    valores = VALORES_TEXTO + VALORES_NUMERO
    for v in valores:
        for mods in MODIFICADORES:
            if _usa_fuso(mods) and not _valor_seguro_para_fuso(v):
                continue
            for fn in ("date", "time", "datetime", "julianday"):
                casos.append((fn, None, v, mods))
    # strftime: todos os formatos sobre uma fatia das entradas
    fatia_v = ["2024-01-01", "2024-12-31 23:59:59", "2024-01-01 10:00:00.9996",
               "2024-01-01 10:00:59.9996", "2024-01-01 10:00:00.1235", "2023-02-31",
               "2024-01-01 24:00", "-0001-06-15", "0000-01-01", "9999-12-31 23:59:59.999",
               "10:00:30.5", "2026-10-15T10:20:30.123456", "abc", "", 2460000.5,
               1700000000.5, 0, "2024-03-03", "2024-01-07", "2021-01-03",
               "2024-01-01 00:30", "2024-01-01 12:00", "2024-01-01 13:05:07"]
    fatia_m = [[], ["+1 day"], ["unixepoch"], ["subsec"], ["start of year"],
               ["weekday 0"], ["+1.5 months"], ["localtime"], [None]]
    for f in FORMATOS:
        for v in fatia_v:
            for mods in fatia_m:
                if _usa_fuso(mods) and not _valor_seguro_para_fuso(v):
                    continue
                casos.append(("strftime", f, v, mods))
    casos.append(("strftime", None, "2024-01-01", []))
    # todos os dias de 2023 e 2024 com %j %W %w (o calendário inteiro)
    d = _dt.date(2023, 1, 1)
    while d.year < 2025:
        casos.append(("strftime", "%Y-%m-%d %j %W %w", d.isoformat(), []))
        d += _dt.timedelta(days=1)
    return casos


def _sql_sqlite(fn, fmt, v, mods):
    args = ([fmt] if fn == "strftime" else []) + [v] + list(mods)
    return f"SELECT {fn}({', '.join('?' for _ in args)})", args


def comparar_datas(amb: Ambiente) -> tuple[int, list[str]]:
    casos = _casos_de_data()
    amb.no_fuso(amb.fuso_da_regua)
    esperado = amb.esperados("datas", [_sql_sqlite(*c) for c in casos])
    obtido = [None] * len(casos)
    # O PostgreSQL recebe as entradas em lote (jsonb), agrupadas pela forma
    # da chamada. "time" vai entre aspas: TIME é palavra da gramática.
    nomes_pg = {"date": "date", "time": '"time"', "datetime": "datetime",
                "julianday": "julianday", "strftime": "strftime"}
    grupos: dict[tuple, list] = {}
    for i, (fn, fmt, v, mods) in enumerate(casos):
        tipo = "t" if isinstance(v, str) else ("i" if isinstance(v, int) else "n")
        grupos.setdefault((fn, tipo, bool(mods)), []).append(
            {"id": i, "f": fmt, tipo: v, "m": list(mods)})
    for (fn, tipo, com_mods), linhas in grupos.items():
        args = (["c.f"] if fn == "strftime" else []) + [f"c.{tipo}"]
        if com_mods:
            args.append("VARIADIC c.m")
        sql = (f"SELECT c.id, {nomes_pg[fn]}({', '.join(args)}) FROM jsonb_to_recordset(%s::jsonb) "
               "AS c(id int, f text, t text, n float8, i bigint, m text[])")
        with amb.pg.cursor() as cur:
            cur.execute(sql, (json.dumps(linhas),))
            for i, r in cur.fetchall():
                obtido[i] = r
    diverg = []
    for c, e, o in zip(casos, esperado, obtido):
        if e != o:
            fn, fmt, v, mods = c
            args = ([fmt] if fn == "strftime" else []) + [v] + list(mods)
            diverg.append(f"{fn}{tuple(args)!r}: sqlite={e!r} pg={o!r}")
    return len(casos), diverg


# 'now' não se grava: a régua é o SQLite daqui, e onde ele não é a 3.45.1 a
# consulta que difere vai na forma que dá a conta da 3.45.1 em qualquer versão.
# 'utc' logo depois de 'now': a 3.45.1 converte, tratando 'now' como hora local
# (o manual do SQLite chama isso de indefinido); da 3.46 em diante, 'utc' sobre
# o que já é UTC não faz nada. 'now' passado como TEXTO não leva a marca de
# «já é UTC», e então toda versão converte, como a 3.45.1.
AGORA_NA_3_45_1 = {
    "SELECT datetime('now','utc')": "SELECT datetime(datetime('now'),'utc')",
}


def comparar_agora(amb: Ambiente) -> tuple[int, list[str]]:
    """'now' e CURRENT_*: o mesmo instante, a menos de um segundo virando."""
    amb.no_fuso(amb.fuso_daqui)
    pares = [
        ("SELECT date('now')", "SELECT cg_date('now')"),
        ("SELECT date()", "SELECT date()"),
        ("SELECT datetime('now')", "SELECT datetime('now')"),
        ("SELECT datetime()", "SELECT datetime()"),
        ("SELECT time('now')", "SELECT cg_time('now')"),
        ("SELECT strftime('%Y-%m-%d %H:%M:%S','now')", "SELECT strftime('%Y-%m-%d %H:%M:%S','now')"),
        ("SELECT strftime('%Y-%m-%d %H:%M:%S')", "SELECT strftime('%Y-%m-%d %H:%M:%S')"),
        ("SELECT datetime('now','localtime')", "SELECT datetime('now','localtime')"),
        ("SELECT date('now','start of month','-1 day')", "SELECT date('now','start of month','-1 day')"),
        ("SELECT datetime('NOW','-7 days')", "SELECT datetime('NOW','-7 days')"),
        ("SELECT datetime('now','utc')", "SELECT datetime('now','utc')"),
        ("SELECT datetime('now','localtime','utc')", "SELECT datetime('now','localtime','utc')"),
        ("SELECT strftime('%Y-%m-%d %H:%M','now','localtime','start of day')",
         "SELECT strftime('%Y-%m-%d %H:%M','now','localtime','start of day')"),
        ("SELECT CURRENT_TIMESTAMP", "SELECT cg_agora_texto()"),
        ("SELECT CURRENT_DATE", "SELECT cg_hoje_texto()"),
        ("SELECT CURRENT_TIME", "SELECT cg_hora_texto()"),
    ]
    if not amb.ao_vivo:
        pares = [(AGORA_NA_3_45_1.get(lite, lite), pg) for lite, pg in pares]
    diverg = []
    for lite, pg in pares:
        for _tentativa in range(3):
            antes = amb.lite(lite)
            obtido = amb.pg1(pg)
            depois = amb.lite(lite)
            if obtido in (antes, depois):
                break
            _time.sleep(0.2)
        else:
            diverg.append(f"{pg}: sqlite={antes!r}/{depois!r} pg={obtido!r}")
    return len(pares), diverg


# ------------------------------------------------------------ nome_da_casa

def _nomes():
    c = chr
    return [
        None, "", " ", "   ", "JOSÉ DA SILVA", "  josé   da  silva  ", "José\tda\nSilva",
        "MARIA" + c(0xA0) + "DAS" + c(0x2003) + "DORES", c(0x3000) + "ANA" + c(0x2028),
        "ÀÁÂÃÄÅ àáâãäå", "ÇÉÊËÈ çéêëè", "ÌÍÎÏ ìíîï", "ÑÒÓÔÕÖ ñòóôõö", "ÙÚÛÜ ùúûü ÝŸ ýÿ",
        "STRAßE", "ÆSIR æ", "ØRSTED ø", "ŁÓDŹ ł", "ŒUVRE œ", "ĐORĐE đ", "Þór ð",
        "İSTANBUL", "ıI", "ΟΔΥΣΣΕΥΣ", "Σίσυφος", "ΣΑΣ ΣΑΣ.", "ǅemal ǈ ǋ", "ﬁnal ﬂor",
        "Ⅻ Ⅻ", "Ẽ Ệ ỹ", "Ḑ ḑ", "e" + c(0x301) + c(0x323), c(0x301) + "acento solto",
        "a " + c(0x301) + " b", "ÁGUA" + c(0x20DD), "𝔄𝔅 𝐀", "Ａｂｃ", "日本 語", "Привет МИР",
        "ŞĞÜÖÇ şğüöç", "Ā ā Ē ē", "ŰŐ űő", "Å" + c(0x30A), "x" + c(0x200B) + "y",
        "linha1\r\nlinha2", c(0x1C) + "sep" + c(0x1F), "tab\x0bvt\x0cff", c(0x85) + "nel",
        "😀 Emoji", "123 456", "D'ÁVILA", "SÃO JOÃO DO CARÚ", "CONCEIÇÃO", "ÑANDÚ",
        "AÇAÍ", "Ü", "ÿ", "ǰ", "ﬀ", "İ̇", "ẞ", "ꝤꝥꞫ", "ᲐᲑ", "Ꭰꭰ",
    ]


def comparar_nome_da_casa(amb: Ambiente) -> tuple[int, list[str]]:
    from pt_schema import normalizar_nome
    nomes = _nomes()
    with amb.pg.cursor() as cur:
        cur.execute("SELECT x, nome_da_casa(x) FROM unnest(%s::text[]) WITH ORDINALITY AS u(x, o) "
                    "ORDER BY o", (nomes,))
        pg = [r[1] for r in cur.fetchall()]
    diverg = []
    for n, o in zip(nomes, pg):
        e = normalizar_nome(n) or ""
        if e != o:
            diverg.append(f"nome_da_casa({n!r}): python={e!r} pg={o!r}")
    # número: str(texto or "")
    for v, e in ((5, "5"), (0, ""), (-12, "-12")):
        o = amb.pg1("SELECT nome_da_casa(%s::bigint)", (v,))
        if o != (normalizar_nome(v) or ""):
            diverg.append(f"nome_da_casa({v}): python={normalizar_nome(v) or ''!r} pg={o!r}")
    return len(nomes) + 3, diverg


def comparar_digitos(amb: Ambiente) -> tuple[int, list[str]]:
    from protesto_cenprot import so_digitos
    c = chr
    textos = [None, "", "abc", "123", "12.345.678/0001-90", "  0 1 ", "2604170001",
              "nº 7" + c(0x661) + c(0x6F2) + c(0xFF13), "²³", "1e5", "-42", "0"]
    with amb.pg.cursor() as cur:
        cur.execute("SELECT digitos(x) FROM unnest(%s::text[]) WITH ORDINALITY AS u(x, o) ORDER BY o",
                    (textos,))
        pg = [r[0] for r in cur.fetchall()]
    diverg = [f"digitos({t!r}): python={so_digitos(t)!r} pg={o!r}"
              for t, o in zip(textos, pg) if so_digitos(t) != o]
    for v, tipo in ((0, "bigint"), (12, "bigint"), (-7, "integer"), (5.0, "float8"),
                    (12.5, "float8"), (3, "integer")):
        o = amb.pg1(f"SELECT digitos(%s::{tipo})", (v,))
        if o != so_digitos(v):
            diverg.append(f"digitos({v!r}::{tipo}): python={so_digitos(v)!r} pg={o!r}")
    return len(textos) + 6, diverg


# ------------------------------------------- as escalares e o agregado

def _lit_pg(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return f"'{v!r}'::float8"
    return "'" + v.replace("'", "''") + "'"


def _lit_lite(v):
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + v.replace("'", "''") + "'"


def comparar_escalares(amb: Ambiente) -> tuple[int, list[str]]:
    casos = [
        # (expressão com {0},{1}..., argumentos)
        ("ifnull({0},{1})", (None, "x")), ("ifnull({0},{1})", ("a", "x")),
        ("ifnull({0},{1})", (None, None)), ("ifnull({0},{1})", (None, 0)),
        ("ifnull({0},{1})", (5, 0)), ("ifnull({0},{1})", (None, 2.5)),
        ("ifnull({0},{1})", ("", "x")),
        ("instr({0},{1})", ("abc", "c")), ("instr({0},{1})", ("abc", "")),
        ("instr({0},{1})", ("abc", "z")), ("instr({0},{1})", (None, "a")),
        ("instr({0},{1})", ("a", None)), ("instr({0},{1})", ("ação", "ç")),
        ("instr({0},{1})", ("ABC", "b")),
        ("max({0},{1})", (1, 2)), ("max({0},{1})", (2, 1)), ("max({0},{1})", (1, None)),
        ("max({0},{1})", (None, None)), ("max({0},{1})", ("a", "b")), ("max({0},{1})", ("B", "a")),
        ("max({0},{1})", (2, 1.5)), ("max({0},{1})", (1.5, 2.5)), ("max({0},{1},{2})", (1, 7, 3)),
        ("max({0},{1},{2})", (1, None, 3)), ("max({0},{1},{2},{3})", (4, 1, 9, 2)),
        ("max({0},{1},{2},{3},{4})", (4, 1, 9, 2, 10)),
        ("min({0},{1})", (1, 2)), ("min({0},{1})", (1, None)), ("min({0},{1})", ("a", "B")),
        ("min({0},{1},{2})", (5, 7, 3)), ("min({0},{1},{2},{3},{4})", (4, 1, 9, 2, 10)),
        ("min({0},{1})", (-1.5, 2)),
        ("typeof({0})", (1,)), ("typeof({0})", (1.5,)), ("typeof({0})", ("a",)),
        ("typeof({0})", (None,)), ("typeof({0})", ("",)),
        ("printf({0},{1})", ("%05d", 42)), ("printf({0},{1})", ("%05d", -42)),
        ("printf({0},{1})", ("%d", -7)), ("printf({0},{1})", ("%.2f", 3.14159)),
        ("printf({0},{1})", ("%.2f", 2.675)), ("printf({0},{1})", ("%.3f", 0.1235)),
        ("printf({0},{1})", ("%.0f", 0.5)), ("printf({0},{1})", ("%.0f", 1.5)),
        ("printf({0},{1})", ("%.0f", 2.5)), ("printf({0},{1})", ("%f", 1 / 3)),
        ("printf({0},{1})", ("%.1f", 0.05)), ("printf({0},{1})", ("%.2f", 1e15 + 0.125)),
        ("printf({0},{1})", ("%s", "oi")), ("printf({0},{1})", ("%5s|", "ab")),
        ("printf({0},{1})", ("%-5s|", "ab")), ("printf({0},{1})", ("[%3d]", 7)),
        ("printf({0},{1})", ("%d", 12)), ("printf({0},{1})", ("%%%d%%", 5)),
        ("printf({0},{1})", ("%.10f", 0.1)), ("printf({0},{1})", ("%.2f", -0.004)),
        ("printf({0})", ("só texto %%",)), ("printf({0},{1},{2})", ("%s-%s", "a", "b")),
        ("printf({0},{1},{2})", ("%02d/%02d", "5", "9")),
    ]
    esperados = amb.esperados("escalares", [
        ("SELECT " + expr.format(*(_lit_lite(a) for a in args)), ()) for expr, args in casos])
    diverg = []
    for (expr, args), e in zip(casos, esperados):
        args_pg = args
        if expr.startswith("printf") and len(args) > 2:
            # vários argumentos chegam como texto (ver o comentário do printf)
            args_pg = (args[0],) + tuple(None if a is None else str(a) for a in args[1:])
        try:
            o = amb.pg1("SELECT " + expr.format(*(_lit_pg(a) for a in args_pg)))
        except Exception as erro:  # noqa: BLE001 — a divergência é o relatório
            o = f"<ERRO {type(erro).__name__}: {str(erro).splitlines()[0]}>"
            amb.pg.rollback() if not amb.pg.autocommit else None
        if isinstance(o, float) and isinstance(e, (int, float)):
            iguais = float(e) == o
        else:
            iguais = e == o or (o is not None and e is not None and str(e) == str(o))
        if not iguais:
            diverg.append(f"{expr.format(*(repr(a) for a in args))}: sqlite={e!r} pg={o!r}")
    return len(casos), diverg


GRUPOS = [
    ([], ","), ([None], ","), ([""], ","), (["", ""], ","), (["a", "b"], ","),
    (["a", None, "b"], " / "), (["a", "b", "c"], ""), (["a", "b"], None),
    ([None, "x"], ","), (["x", ""], ","), ([1, 2, 3], ","), ([1, None, 3], " · "),
    ([1.5, 2.0, 0.1 + 0.2, 1e20, 1e-5, 123456789012345678.0, -0.0, 1 / 3], ","),
    (["NOME Á", "NOME B"], " · "),
]


def comparar_group_concat(amb: Ambiente) -> tuple[int, list[str]]:
    itens = []      # (valores, sep, consulta ao SQLite, consulta ao PostgreSQL)
    for valores, sep in GRUPOS:
        for com_sep in (True, False):
            if not com_sep and sep != ",":
                continue
            linhas = ", ".join(f"({i}, {_lit_lite(v)})" for i, v in enumerate(valores))
            sub_lite = (f"SELECT x FROM (SELECT column1 o, column2 x FROM (VALUES {linhas})) ORDER BY o"
                        if valores else "SELECT NULL x WHERE 0")
            arg_lite = f"x, {_lit_lite(sep)}" if com_sep else "x"
            tipo = ("text" if all(isinstance(v, str) or v is None for v in valores) else
                    "bigint" if all(isinstance(v, int) or v is None for v in valores) else "float8")
            if valores:
                linhas_pg = ", ".join(f"({i}, {_lit_pg(v)}::{tipo})" for i, v in enumerate(valores))
                fonte = f"(VALUES {linhas_pg}) AS t(o, x)"
            else:
                fonte = f"(SELECT 0 o, NULL::{tipo} x WHERE false) AS t"
            sep_pg = f", {_lit_pg(sep)}::text" if com_sep else ""
            itens.append((valores, sep, f"SELECT group_concat({arg_lite}) FROM ({sub_lite})",
                          f"SELECT group_concat(x{sep_pg} ORDER BY o) FROM {fonte}"))
    esperados = amb.esperados("group_concat", [(lite, ()) for _v, _s, lite, _pg in itens])
    diverg = []
    for (valores, sep, _lite, pg), e in zip(itens, esperados):
        o = amb.pg1(pg)
        if e != o:
            diverg.append(f"group_concat({valores!r}, {sep!r}): sqlite={e!r} pg={o!r}")
    return len(itens), diverg


def comparacoes(amb: Ambiente) -> dict[str, tuple[int, list[str]]]:
    return {
        "datas (date/time/datetime/julianday/strftime)": comparar_datas(amb),
        "'now' e CURRENT_*": comparar_agora(amb),
        "nome_da_casa": comparar_nome_da_casa(amb),
        "digitos": comparar_digitos(amb),
        "ifnull/instr/max/min/typeof/printf": comparar_escalares(amb),
        "group_concat": comparar_group_concat(amb),
    }


# ============================================================ os testes

if pytest is not None:

    @pytest.fixture(scope="module")
    def amb():
        a = Ambiente()
        yield a
        a.fechar()

    def _sem_divergencia(resultado):
        n, diverg = resultado
        assert n > 0
        assert not diverg, f"{len(diverg)} de {n} divergem:\n" + "\n".join(diverg[:60])

    def test_datas_iguais_ao_sqlite(amb):
        n, diverg = comparar_datas(amb)
        assert n > 20000, n          # a grade é grande de propósito
        _sem_divergencia((n, diverg))

    def test_agora_igual_ao_sqlite(amb):
        _sem_divergencia(comparar_agora(amb))

    def test_nome_da_casa_igual_ao_python(amb):
        _sem_divergencia(comparar_nome_da_casa(amb))

    def test_digitos_igual_ao_python(amb):
        _sem_divergencia(comparar_digitos(amb))

    def test_escalares_iguais_ao_sqlite(amb):
        _sem_divergencia(comparar_escalares(amb))

    def test_group_concat_igual_ao_sqlite(amb):
        _sem_divergencia(comparar_group_concat(amb))

    # ---- a resolução de nomes: pg_catalog é procurado ANTES do schema

    def test_com_coluna_texto_ou_dois_argumentos_a_funcao_e_a_nossa(amb):
        assert amb.pg1("SELECT date('2026-01-31', '+1 day')") == "2026-02-01"
        assert amb.pg1("SELECT date(x) FROM (VALUES ('2026-02-31')) t(x)") == "2026-03-03"
        assert amb.pg1("SELECT datetime('2026-01-01')") == "2026-01-01 00:00:00"
        assert amb.pg1("SELECT julianday('2026-01-01')") == 2461041.5
        assert amb.pg1("SELECT cg_date('2026-02-31')") == "2026-03-03"
        assert amb.pg1("SELECT cg_time('10:00')") == "10:00:00"
        # parâmetro: psycopg manda str sem tipo; com ::text é a nossa
        assert amb.pg1("SELECT date(%s::text)", ("2026-02-31",)) == "2026-03-03"
        assert amb.pg1("SELECT date(%s, %s)", ("2026-01-01", "-365 days")) == "2025-01-01"

    def test_armadilha_date_com_um_literal_vira_conversao_de_tipo(amb):
        """O PostgreSQL lê `date('...')` de UM literal como cast para o tipo
        date — fica aqui medido, para o tradutor trocar por `cg_date(`."""
        assert amb.pg1("SELECT pg_typeof(date('2026-01-01'))::text") == "date"
        with amb.pg.cursor() as cur:
            with pytest.raises(psycopg.Error):
                cur.execute("SELECT date('2026-02-31')")   # o tipo date recusa o dia 31

    def test_armadilha_time_nao_e_nem_chamavel(amb):
        """TIME é palavra da gramática: `time('10:00')` é erro de sintaxe.
        Só `"time"(...)` entre aspas, ou `cg_time(...)`."""
        with pytest.raises(psycopg.errors.SyntaxError):
            amb.pg1("SELECT time('10:00'::text)")
        assert amb.pg1('SELECT "time"(\'10:00\'::text)') == "10:00:00"

    def test_max_e_min_de_dois_argumentos_sao_os_nossos(amb):
        assert amb.pg1("SELECT max(1, 2)") == 2
        assert amb.pg1("SELECT max(1, NULL::int)") is None      # greatest() daria 1
        assert amb.pg1("SELECT min(%s, %s)", (3, 1)) == 1
        assert amb.pg1("SELECT max(x) FROM (VALUES (1),(5),(3)) t(x)") == 5   # o agregado
        with amb.pg.cursor() as cur:
            cur.execute("CREATE TEMP TABLE t_num (serie text PRIMARY KEY, maior_em_uso bigint)")
            cur.execute("INSERT INTO t_num VALUES ('A', 7)")
            cur.execute("INSERT INTO t_num VALUES ('A', 3) ON CONFLICT (serie) DO UPDATE "
                        "SET maior_em_uso = MAX(COALESCE(t_num.maior_em_uso, 0), excluded.maior_em_uso)")
            cur.execute("SELECT maior_em_uso FROM t_num")
            assert cur.fetchone()[0] == 7
            cur.execute("DROP TABLE t_num")

    def test_ifnull_resolve_nas_formas_do_sistema(amb):
        assert amb.pg1("SELECT ifnull(NULL::text, '')") == ""
        assert amb.pg1("SELECT ifnull(x, '') <> '' FROM (VALUES ('selo')) t(x)") is True
        assert amb.pg1("SELECT ifnull(NULL::int, 0)") == 0
        assert amb.pg1("SELECT ifnull(NULL::bigint, '')") == ""

    def test_group_concat_numa_subconsulta_correlacionada(amb):
        assert amb.pg1(
            "SELECT (SELECT group_concat(p.nome, ' / ') FROM (VALUES (1,'ANA'),(1,'JOÃO'),(2,'X')) "
            "p(ato_id, nome) WHERE p.ato_id = a.id) FROM (VALUES (1)) a(id)") in ("ANA / JOÃO", "JOÃO / ANA")

    def test_nome_da_casa_serve_para_like(amb):
        assert amb.pg1("SELECT nome_da_casa('JOSÉ DA SILVA') LIKE %s", ("%jose%",)) is True

    def test_versoes_imutaveis_servem_a_indice_e_recusam_agora(amb):
        with amb.pg.cursor() as cur:
            cur.execute("CREATE TEMP TABLE t_dt (d text)")
            cur.execute("CREATE INDEX ON t_dt (cg_date_imutavel(d))")
            cur.execute("CREATE INDEX ON t_dt (nome_da_casa(d))")
            cur.execute("INSERT INTO t_dt VALUES ('2026-02-31 10:00'), ('lixo'), (NULL)")
            cur.execute("SELECT cg_date_imutavel(d) FROM t_dt ORDER BY 1")
            assert [r[0] for r in cur.fetchall()] == ["2026-03-03", None, None]
            assert amb.pg1("SELECT cg_datetime_imutavel('2026-01-01', '+1 day')") == "2026-01-02 00:00:00"
            with pytest.raises(psycopg.Error):
                cur.execute("SELECT cg_date_imutavel('now')")
            with pytest.raises(psycopg.Error):
                cur.execute("SELECT cg_date_imutavel('2026-01-01', 'localtime')")
            cur.execute("DROP TABLE t_dt")
        estab = amb.pg1("SELECT string_agg(DISTINCT provolatile::text, '') FROM pg_proc p "
                        "JOIN pg_namespace n ON n.oid = p.pronamespace "
                        "WHERE n.nspname = %s AND proname IN ('date','datetime','strftime','julianday')",
                        (amb.schema,))
        assert estab == "s"      # STABLE: dependem de 'now' e do fuso da sessão

    def test_o_arquivo_roda_duas_vezes_sem_erro(amb):
        with amb.pg.cursor() as cur:
            cur.execute(f'SET search_path TO "{amb.schema}"')
            cur.execute(ARQUIVO_SQL.read_text(encoding="utf-8"))
            cur.execute(f'SET search_path TO "{amb.schema}", public')
        assert amb.pg1("SELECT datetime('2026-01-01 24:00')") == "2026-01-01 24:00:00"


# ============================================================ script avulso

def gravar_regua(amb: Ambiente) -> None:
    """Grava o que o SQLite 3.45.1 daqui respondeu às grades que já rodaram
    (`amb.medidas`), com o fuso da máquina — as datas com 'localtime' são
    comparadas nele. Um valor por linha, para a regravação mostrar no diff
    exatamente o que mudou."""
    dados = {
        "sobre": ("O que o SQLite da produção respondeu a cada consulta das grades de "
                  "tests/test_banco_pg_funcoes.py. Regrave " + COMO_GRAVAR),
        "sqlite": sqlite3.sqlite_version,
        "python": sys.version.split()[0],
        "medido_em": _dt.date.today().isoformat(),
        "fuso_minutos": amb.fuso_daqui,
        "grades": amb.medidas,
    }
    ARQUIVO_REGUA.write_text(json.dumps(dados, ensure_ascii=False, indent=0) + "\n",
                             encoding="utf-8")


if __name__ == "__main__":
    if not DSN or psycopg is None:
        print("defina CG_PG_DSN (e instale psycopg) para comparar")
        sys.exit(2)
    gravar = "--gravar-regua" in sys.argv[1:]
    print("SQLite", sqlite3.sqlite_version, "| Python", sys.version.split()[0])
    if gravar and sqlite3.sqlite_version != REGUA_DA_PRODUCAO:
        print(f"a régua é o SQLite {REGUA_DA_PRODUCAO} da produção; este Python roda o "
              f"{sqlite3.sqlite_version} — use um que rode a {REGUA_DA_PRODUCAO}")
        sys.exit(2)
    a = Ambiente(gravando=gravar)
    try:
        print("PostgreSQL", a.pg1("SELECT current_setting('server_version')"),
              "| fuso da sessão", a.pg1("SELECT current_setting('TimeZone')"))
        if not a.ao_vivo:
            g = a.gravada or {}
            print(f"régua: a medição gravada (SQLite {g.get('sqlite')}, Python {g.get('python')}, "
                  f"{g.get('medido_em')}, fuso {g.get('fuso_minutos')} min)")
        total_div = 0
        t0 = _time.time()
        for nome, (n, diverg) in comparacoes(a).items():
            total_div += len(diverg)
            print(f"\n== {nome}: {n} casos, {len(diverg)} divergências")
            for d in diverg[:40]:
                print("   ", d)
        print(f"\n{total_div} divergência(s) no total ({_time.time() - t0:.1f} s)")
        if gravar:
            gravar_regua(a)
            print("régua gravada em", ARQUIVO_REGUA)
        sys.exit(1 if total_div else 0)
    finally:
        a.fechar()
