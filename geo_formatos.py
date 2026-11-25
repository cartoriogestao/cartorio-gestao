"""OS FORMATOS DO MAPA — GeoPackage, Shapefile e GeoJSON, só com a biblioteca padrão do Python.

    «a importação de memorial descritivo digitado ou digital, inclusive do Sistema de Gestão Fundiária do
     INCRA (Sigef), do Acervo Fundiário do Incra e de outros portais que disponibilizem coordenadas
     geodésicas de imóveis»  (CNN, art. 343-E, VIII, incluído pelo Provimento CN n. 195/2025)

O QUE ESTE MÓDULO FAZ
    LÊ: `.gpkg`, Shapefile (`.shp` + `.dbf` + `.prj`, avulsos ou num `.zip`) e GeoJSON — as formas em que o
    QGIS, o SIGEF e o Acervo Fundiário entregam um polígono. ESCREVE: o `.gpkg` e o Shapefile (`.zip` com
    `.shp .shx .dbf .prj .cpg`) com os atributos do Mapa do ONR (`docs/MAPA_ONR.md`).

POR QUE À MÃO, E NÃO COM GDAL / FIONA / PYSHP
    O pedido da tarefa RI011 era o MÍNIMO de dependências, e a casa instala por `pip` num Windows e num Mac. GDAL
    e Fiona trazem dezenas de MB de binários nativos, e o servidor Windows não compila. O Shapefile e o
    GeoPackage são formatos pequenos e **públicos** (ESRI Shapefile Technical Description, 1998; OGC
    GeoPackage 1.2/1.3, que é um SQLite com tabelas de nome fixo), e o GeoPackage lê-se com o `sqlite3` que já
    vem no Python. O que se escreveu aqui foi **conferido contra o GDAL na bancada do desenvolvedor** (leitura
    e escrita em duas vias), e os testes do repositório trazem arquivos pequenos feitos pelo GDAL para que a
    leitura continue sendo conferida contra um escritor que não é este.

O QUE ESTE MÓDULO NÃO FAZ
    Não converte de sistema de coordenadas (isso é de `geo_geodesia`), não valida geometria e não fala com o
    banco. Lê o que o arquivo diz, no sistema do arquivo, e diz qual é.

ARQUIVO DE FORA É DADO, NÃO CONFIANÇA
    Tudo o que vem do arquivo passa por limite de tamanho, de contagem e de bordas: um `.zip` bomba, um
    Shapefile que anuncia dois bilhões de pontos ou um GeoPackage com um índice malicioso viram `GeoErro`,
    e não memória esgotada. O SQLite do GeoPackage abre **em memória**, com um autorizador que só deixa
    passar `SELECT`, e só as consultas fixas daqui rodam nele; o nome da tabela vem do próprio arquivo e é
    conferido contra `gpkg_contents` e contra o catálogo antes de entrar no SQL (entre aspas).
"""
from __future__ import annotations

import io
import json
import re
import sqlite3
import struct
import zipfile
from typing import Any, Iterable, Sequence

import tetos_de_entrada as TETOS
from geo_geodesia import GeoErro

# ------------------------------------------------------------------ limites (arquivo de fora)

MAX_BYTES_DO_ARQUIVO = 200 * 1024 * 1024        # o que o navegador pode mandar
MAX_FEICOES = 50_000
MAX_PONTOS_POR_FEICAO = 2_000_000
MAX_ANEIS_POR_FEICAO = 100_000

#: A forma dos dados que o resto do sistema vê.
#:   Camada  = {"nome", "epsg", "origem", "feicoes": [Feicao], "avisos": [str]}
#:   Feicao  = {"indice", "atributos": {str: Any}, "geometria": [[[(x, y), ...], ...], ...], "tipo": str,
#:              "avisos": [str]}      # `geometria` é lista de polígonos; polígono = lista de anéis
Camada = dict
Feicao = dict


# ------------------------------------------------------------------ o sistema de coordenadas do arquivo

_EPSG_NO_WKT = re.compile(r'(?:AUTHORITY\s*\[\s*"EPSG"\s*,\s*"?(\d+)"?\s*\]|ID\s*\[\s*"EPSG"\s*,\s*(\d+)\s*\])',
                          re.IGNORECASE)
_UTM_SIRGAS = re.compile(r'SIRGAS[_ ]?2000[_ /]*UTM[_ ]*zone[_ ]*(\d{1,2})\s*([NS])', re.IGNORECASE)


def epsg_do_wkt(wkt: str | None) -> int | None:
    """O código EPSG que o `.prj` (ou a definição do GeoPackage) declara, ou `None` se não se sabe.

    Procura o código EPSG escrito (o do sistema inteiro é o último que aparece no WKT) e, não o achando, o NOME —
    o ESRI escreve `GCS_SIRGAS_2000` e `SIRGAS_2000_UTM_Zone_23S` sem código. Nome que não se reconhece dá
    `None`: quem chama recusa e pede ao usuário que diga o sistema, e não se adivinha.
    """
    if not wkt:
        return None
    achados = _EPSG_NO_WKT.findall(wkt)
    if achados:
        ultimo = achados[-1]
        return int(ultimo[0] or ultimo[1])
    utm = _UTM_SIRGAS.search(wkt)
    if utm:
        fuso, hemisferio = int(utm.group(1)), utm.group(2).upper()
        base = 31965 if hemisferio == "N" else 31977
        epsg = base + (fuso - (11 if hemisferio == "N" else 17))
        return epsg if (31965 <= epsg <= 31976 if hemisferio == "N" else 31977 <= epsg <= 31985) else None
    nome = wkt.upper()
    if "SIRGAS" in nome and "UTM" not in nome and "PROJCS" not in nome and "PROJCRS" not in nome:
        return 4674
    if re.search(r"WGS[_ ]?(19)?84", nome) and "UTM" not in nome and "PROJCS" not in nome:
        return 4326
    if ("SAD" in nome and "69" in nome) or "SOUTH_AMERICAN_1969" in nome.replace(" ", "_"):
        return 4618
    if "CORREGO" in nome or "CÓRREGO" in nome:
        return 4225
    return None


# ------------------------------------------------------------------ WKB

_TIPOS_WKB = {1: "Point", 2: "LineString", 3: "Polygon", 4: "MultiPoint", 5: "MultiLineString",
              6: "MultiPolygon", 7: "GeometryCollection"}


class _Leitor:
    """Lê `bytes` com bordas conferidas: ler além do fim é `GeoErro`, e não `struct.error`."""

    def __init__(self, dados: bytes, posicao: int = 0) -> None:
        self.dados, self.pos = dados, posicao

    def pegar(self, formato: str):
        tamanho = struct.calcsize(formato)
        if self.pos + tamanho > len(self.dados):
            raise GeoErro("Geometria truncada: o arquivo termina antes do esperado.")
        valor = struct.unpack_from(formato, self.dados, self.pos)
        self.pos += tamanho
        return valor


def _wkb(leitor: _Leitor) -> tuple[str, list]:
    """`(tipo, partes)`: Point `[(x, y)]`; LineString `[[pts]]`; Polygon `[[anel...]]`; Multi* e coleção, achatado.

    Devolve **`partes` como lista de linhas/anéis**, e o tipo diz como lê-las. Z e M são descartados.
    """
    (ordem,) = leitor.pegar("B")
    fim = "<" if ordem == 1 else ">"
    (codigo,) = leitor.pegar(fim + "I")
    tem_srid = bool(codigo & 0x20000000)
    tem_z = bool(codigo & 0x80000000)
    tem_m = bool(codigo & 0x40000000)
    codigo &= 0x0FFFFFFF
    if codigo >= 1000:           # ISO: 1000 Z, 2000 M, 3000 ZM
        faixa, codigo = divmod(codigo, 1000)
        tem_z, tem_m = faixa in (1, 3), faixa in (2, 3)
    if tem_srid:
        leitor.pegar(fim + "I")
    tipo = _TIPOS_WKB.get(codigo)
    if tipo is None:
        raise GeoErro(f"Tipo de geometria desconhecido no arquivo ({codigo}).")
    ndim = 2 + (1 if tem_z else 0) + (1 if tem_m else 0)

    def pontos(n: int) -> list[tuple[float, float]]:
        if n < 0 or n > MAX_PONTOS_POR_FEICAO or leitor.pos + n * 8 * ndim > len(leitor.dados):
            raise GeoErro("Geometria com contagem de pontos impossível: arquivo corrompido ou truncado.")
        saida = []
        for _ in range(n):
            v = leitor.pegar(fim + "d" * ndim)
            saida.append((v[0], v[1]))
        return saida

    if tipo == "Point":
        return tipo, [pontos(1)]
    if tipo == "LineString":
        (n,) = leitor.pegar(fim + "I")
        return tipo, [pontos(n)]
    if tipo == "Polygon":
        (n,) = leitor.pegar(fim + "I")
        if n > MAX_ANEIS_POR_FEICAO:
            raise GeoErro("Polígono com anéis demais: arquivo corrompido.")
        aneis = []
        for _ in range(n):
            (m,) = leitor.pegar(fim + "I")
            aneis.append(pontos(m))
        return tipo, aneis
    # Multi* e coleção: lê os filhos, cada um com o seu cabeçalho
    (n,) = leitor.pegar(fim + "I")
    if n > MAX_ANEIS_POR_FEICAO:
        raise GeoErro("Geometria com partes demais: arquivo corrompido.")
    filhos = [_wkb(leitor) for _ in range(n)]
    return tipo, filhos  # type: ignore[return-value]


def geometria_de_wkb(dados: bytes) -> tuple[list, str]:
    """`(geometria, tipo)` do WKB. Polígono e MultiPolígono viram polígonos; linha vira anel (a tela o confere).

    `tipo` é o que o arquivo trazia: Polygon, MultiPolygon, LineString, MultiLineString. Ponto e coleção
    levantam `GeoErro` dizendo que não é polígono.
    """
    tipo, partes = _wkb(_Leitor(dados))
    if tipo == "Polygon":
        return [partes], tipo
    if tipo == "MultiPolygon":
        saida = []
        for t, aneis in partes:
            if t != "Polygon":
                raise GeoErro("MultiPolygon com parte que não é polígono.")
            saida.append(aneis)
        return saida, tipo
    if tipo == "LineString":
        return [[partes[0]]], tipo
    if tipo == "MultiLineString":
        return [[linha[0]] for t, linha in partes if t == "LineString"], tipo
    raise GeoErro(f"A geometria é do tipo {tipo}, e não polígono: o Mapa guarda o perímetro do imóvel.")


def wkb_de_geometria(geometria: Sequence, *, multi: bool = True) -> bytes:
    """O WKB (little endian, 2D) da geometria. `multi=True` sempre MultiPolygon; senão Polygon se for um só."""
    def anel(pontos) -> bytes:
        pontos = list(pontos)
        if pontos and pontos[0] != pontos[-1]:
            pontos.append(pontos[0])
        return struct.pack("<I", len(pontos)) + b"".join(struct.pack("<dd", x, y) for x, y in pontos)

    def poligono(aneis) -> bytes:
        return b"\x01" + struct.pack("<II", 3, len(aneis)) + b"".join(anel(a) for a in aneis)

    if not multi and len(geometria) == 1:
        return poligono(geometria[0])
    return b"\x01" + struct.pack("<II", 6, len(geometria)) + b"".join(poligono(p) for p in geometria)


# ------------------------------------------------------------------ anéis: furo ou externo?

def _area_assinada(anel: Sequence) -> float:
    """Fórmula do cadarço: positiva se o anel é anti-horário (com y para cima)."""
    soma = 0.0
    for (x1, y1), (x2, y2) in zip(anel, list(anel[1:]) + [anel[0]]):
        soma += x1 * y2 - x2 * y1
    return soma / 2.0


def _ponto_no_anel(ponto, anel) -> bool:
    x, y = ponto
    dentro = False
    n = len(anel)
    j = n - 1
    for i in range(n):
        xi, yi = anel[i]
        xj, yj = anel[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            dentro = not dentro
        j = i
    return dentro


def montar_poligonos(aneis: Sequence[Sequence]) -> list:
    """Agrupa anéis soltos em polígonos (externo + furos) **pelo aninhamento**, e não pela orientação.

    O Shapefile manda o externo no sentido horário e o furo no anti-horário, mas há quem escreva ao contrário.
    O aninhamento não mente: o anel dentro de um número ímpar de maiores é furo do menor que o contém.
    """
    validos = [list(a) for a in aneis if len(a) >= 3]
    ordem = sorted(range(len(validos)), key=lambda i: -abs(_area_assinada(validos[i])))
    poligonos: list[list] = []
    dono: dict[int, int] = {}          # índice do anel externo -> posição do polígono
    for i in ordem:
        anel = validos[i]
        continentes = [j for j in ordem if j != i and abs(_area_assinada(validos[j])) > abs(_area_assinada(anel))
                       and _ponto_no_anel(anel[0], validos[j])]
        if len(continentes) % 2 == 0:
            dono[i] = len(poligonos)
            poligonos.append([anel])
        else:
            externos = [j for j in continentes if j in dono]
            if externos:
                menor = min(externos, key=lambda j: abs(_area_assinada(validos[j])))
                poligonos[dono[menor]].append(anel)
            else:
                dono[i] = len(poligonos)
                poligonos.append([anel])
    return poligonos


# ------------------------------------------------------------------ GeoPackage (leitura)

_ID_SIMPLES = re.compile(r"^[A-Za-z0-9_ .\-]{1,128}$")


def _so_select(acao, *_):
    return sqlite3.SQLITE_OK if acao in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION) \
        else sqlite3.SQLITE_DENY


def _abrir_gpkg(dados: bytes) -> sqlite3.Connection:
    if not dados.startswith(b"SQLite format 3\x00"):
        raise GeoErro("O arquivo não é um GeoPackage (não tem o cabeçalho do SQLite).")
    con = sqlite3.connect(":memory:")
    try:
        con.deserialize(dados)
        con.set_authorizer(_so_select)
        con.row_factory = sqlite3.Row
        con.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchall()
    except (sqlite3.DatabaseError, sqlite3.OperationalError, AttributeError) as erro:
        con.close()
        raise GeoErro(f"Não foi possível abrir o GeoPackage: {erro}") from erro
    return con


def _blob_gpkg(blob: bytes) -> tuple[bytes | None, int | None]:
    """`(WKB, srs_id)` do cabeçalho binário do GeoPackage (OGC 12-128r18, §2.1.3). WKB `None` se vazio."""
    if blob is None or len(blob) < 8 or blob[:2] != b"GP":
        raise GeoErro("Geometria do GeoPackage com cabeçalho inválido.")
    flags = blob[3]
    fim = "<" if flags & 1 else ">"
    (srs,) = struct.unpack_from(fim + "i", blob, 4)
    codigo_do_envelope = (flags >> 1) & 0b111
    envelope = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}.get(codigo_do_envelope)
    if envelope is None:
        raise GeoErro("Geometria do GeoPackage com envelope desconhecido.")
    if flags & 0b00010000:        # vazia
        return None, srs
    return bytes(blob[8 + envelope:]), srs


def ler_gpkg(dados: bytes, nome: str = "") -> list[Camada]:
    """As camadas de feições do GeoPackage, uma por tabela (`gpkg_contents.data_type = 'features'`)."""
    con = _abrir_gpkg(dados)
    camadas: list[Camada] = []
    try:
        try:
            contents = con.execute(
                "SELECT table_name, identifier, srs_id FROM gpkg_contents WHERE data_type = 'features'").fetchall()
        except sqlite3.Error as erro:
            raise GeoErro("O arquivo é um SQLite, mas não um GeoPackage de feições (falta `gpkg_contents`).") \
                from erro
        for linha in contents:
            tabela = linha["table_name"]
            catalogo = con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                                   (tabela,)).fetchone()
            col = con.execute("SELECT column_name, srs_id FROM gpkg_geometry_columns WHERE table_name = ?",
                              (tabela,)).fetchone()
            if not catalogo or not col or not _ID_SIMPLES.match(str(tabela)) \
                    or not _ID_SIMPLES.match(str(col["column_name"])):
                continue
            srs_id = col["srs_id"] if col["srs_id"] is not None else linha["srs_id"]
            epsg = None
            if srs_id is not None:
                srs = con.execute(
                    "SELECT organization, organization_coordsys_id, definition FROM gpkg_spatial_ref_sys "
                    "WHERE srs_id = ?", (srs_id,)).fetchone()
                if srs and str(srs["organization"]).upper() == "EPSG" and int(srs["organization_coordsys_id"]) > 0:
                    epsg = int(srs["organization_coordsys_id"])
                elif srs:
                    epsg = epsg_do_wkt(srs["definition"])
            coluna_geom = col["column_name"]
            q = lambda s: '"' + str(s).replace('"', '""') + '"'
            feicoes: list[Feicao] = []
            avisos: list[str] = []
            for i, registro in enumerate(con.execute(f"SELECT * FROM {q(tabela)} LIMIT {MAX_FEICOES + 1}")):
                if i >= MAX_FEICOES:
                    avisos.append(f"A camada tem mais de {MAX_FEICOES} feições: só as primeiras foram lidas.")
                    break
                atributos = {k: registro[k] for k in registro.keys() if k != coluna_geom}
                feicao: Feicao = {"indice": i, "atributos": atributos, "geometria": [], "tipo": "", "avisos": []}
                try:
                    wkb, _ = _blob_gpkg(registro[coluna_geom])
                    if wkb is None:
                        feicao["avisos"].append("Geometria vazia.")
                    else:
                        feicao["geometria"], feicao["tipo"] = geometria_de_wkb(wkb)
                except GeoErro as erro:
                    feicao["avisos"].append(str(erro))
                feicoes.append(feicao)
            camadas.append({"nome": str(linha["identifier"] or tabela), "epsg": epsg, "origem": "GPKG",
                            "feicoes": feicoes, "avisos": avisos})
    finally:
        con.close()
    if not camadas:
        raise GeoErro("O GeoPackage não tem nenhuma camada de feições (polígonos).")
    return camadas


# ------------------------------------------------------------------ GeoPackage (escrita)

# As definições do registro EPSG, no WKT 1 do GDAL (as que o próprio GDAL grava no GeoPackage).
_WKT_4674 = ('GEOGCS["SIRGAS 2000",DATUM["Sistema_de_Referencia_Geocentrico_para_las_AmericaS_2000",'
             'SPHEROID["GRS 1980",6378137,298.257222101,AUTHORITY["EPSG","7019"]],AUTHORITY["EPSG","6674"]],'
             'PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,'
             'AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4674"]]')
_WKT_4326 = ('GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,'
             'AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,'
             'AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],'
             'AUTHORITY["EPSG","4326"]]')
# O WKT do ESRI, para o `.prj` do Shapefile (é o que o QGIS e o ArcGIS leem sem perguntar).
_PRJ_4674 = ('GEOGCS["GCS_SIRGAS_2000",DATUM["D_SIRGAS_2000",SPHEROID["GRS_1980",6378137.0,298.257222101]],'
             'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]')

#: Os atributos do Mapa do ONR, na ordem do plugin de referência (`docs/MAPA_ONR.md`). Nome de coluna do
#: Shapefile tem no máximo dez letras: por isso `PROPRIETAR`.
COLUNAS_DO_MAPA = ("MATRICULA", "CNS", "PROPRIETAR", "AREA_HA")
NOME_DA_CAMADA = "mapa_onr"


def escrever_gpkg(feicoes: Iterable[dict], *, camada: str = NOME_DA_CAMADA) -> bytes:
    """O GeoPackage com os atributos do Mapa. Cada feição: `{geometria, MATRICULA, CNS, PROPRIETAR, AREA_HA}`.

    Geometria em SIRGAS 2000 (lon, lat), sempre MultiPolygon. Sem índice espacial (é extensão opcional): o QGIS
    abre e o GDAL lê do mesmo jeito. Conferido na bancada com o GDAL (`pyogrio`) e nos testes por leitura própria.
    """
    if not re.match(r"^[A-Za-z][A-Za-z0-9_]{0,62}$", camada):
        raise GeoErro("Nome de camada inválido.")
    con = sqlite3.connect(":memory:")
    try:
        for comando in (
                "PRAGMA application_id = 1196444487",
                "PRAGMA user_version = 10200",
                """CREATE TABLE gpkg_spatial_ref_sys (
  srs_name TEXT NOT NULL, srs_id INTEGER PRIMARY KEY, organization TEXT NOT NULL,
  organization_coordsys_id INTEGER NOT NULL, definition TEXT NOT NULL, description TEXT)""",
                """CREATE TABLE gpkg_contents (
  table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT NULL, identifier TEXT UNIQUE,
  description TEXT DEFAULT '', last_change DATETIME NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE, srs_id INTEGER,
  CONSTRAINT fk_gc_r_srs_id FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id))""",
                """CREATE TABLE gpkg_geometry_columns (
  table_name TEXT NOT NULL, column_name TEXT NOT NULL, geometry_type_name TEXT NOT NULL,
  srs_id INTEGER NOT NULL, z TINYINT NOT NULL, m TINYINT NOT NULL,
  CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name),
  CONSTRAINT fk_gc_tn FOREIGN KEY (table_name) REFERENCES gpkg_contents(table_name),
  CONSTRAINT fk_gc_srs FOREIGN KEY (srs_id) REFERENCES gpkg_spatial_ref_sys(srs_id))""",
                f"""CREATE TABLE "{camada}" (
  fid INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, geom MULTIPOLYGON,
  MATRICULA TEXT, CNS TEXT, PROPRIETAR TEXT, AREA_HA REAL)"""):
            con.execute(comando)

        con.executemany(
            "INSERT INTO gpkg_spatial_ref_sys VALUES (?,?,?,?,?,?)",
            [("Undefined Cartesian SRS", -1, "NONE", -1, "undefined", "undefined Cartesian coordinate reference system"),
             ("Undefined geographic SRS", 0, "NONE", 0, "undefined", "undefined geographic coordinate reference system"),
             ("WGS 84", 4326, "EPSG", 4326, _WKT_4326, "WGS 84"),
             ("SIRGAS 2000", 4674, "EPSG", 4674, _WKT_4674, "SIRGAS 2000")])
        caixa = [None, None, None, None]
        for f in feicoes:
            geometria = f["geometria"]
            pontos = [p for poligono in geometria for anel in poligono for p in anel]
            if not pontos:
                continue
            envelope = (min(p[0] for p in pontos), max(p[0] for p in pontos),
                        min(p[1] for p in pontos), max(p[1] for p in pontos))
            caixa = [envelope[0] if caixa[0] is None else min(caixa[0], envelope[0]),
                     envelope[2] if caixa[1] is None else min(caixa[1], envelope[2]),
                     envelope[1] if caixa[2] is None else max(caixa[2], envelope[1]),
                     envelope[3] if caixa[3] is None else max(caixa[3], envelope[3])]
            blob = b"GP\x00\x03" + struct.pack("<i", 4674) + struct.pack("<dddd", *envelope) \
                + wkb_de_geometria(_orientar(geometria, externo_anti_horario=True))
            con.execute(f'INSERT INTO "{camada}" (geom, MATRICULA, CNS, PROPRIETAR, AREA_HA) VALUES (?,?,?,?,?)',
                        (blob, f.get("MATRICULA"), f.get("CNS"), f.get("PROPRIETAR"), f.get("AREA_HA")))
        con.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier, description, min_x, min_y, "
                    "max_x, max_y, srs_id) VALUES (?, 'features', ?, 'Mapa do RI para o ONR', ?, ?, ?, ?, 4674)",
                    (camada, camada, *caixa))
        con.execute("INSERT INTO gpkg_geometry_columns VALUES (?, 'geom', 'MULTIPOLYGON', 4674, 0, 0)", (camada,))
        con.commit()
        return bytes(con.serialize())
    finally:
        con.close()


def _orientar(geometria: Sequence, *, externo_anti_horario: bool) -> list:
    """Anéis no sentido que o formato pede: GeoPackage/OGC, externo anti-horário; Shapefile, externo horário."""
    saida = []
    for poligono in geometria:
        aneis = []
        for i, anel in enumerate(poligono):
            pontos = list(anel)
            if pontos and pontos[0] == pontos[-1]:
                pontos = pontos[:-1]
            anti = _area_assinada(pontos) > 0
            quer_anti = externo_anti_horario if i == 0 else not externo_anti_horario
            if anti != quer_anti:
                pontos.reverse()
            aneis.append(pontos + pontos[:1])
        saida.append(aneis)
    return saida


# ------------------------------------------------------------------ Shapefile (leitura)

_TIPOS_POLIGONO = {5, 15, 25}
_TIPOS_LINHA = {3, 13, 23}
_TIPOS_PONTO = {1, 11, 21, 8, 18, 28}


def _ler_shp(dados: bytes) -> list[tuple[str, list]]:
    """As formas do `.shp`, em ordem: `("poligono"|"linha"|"nula"|"outra", anéis/partes)`."""
    if len(dados) < 100:
        raise GeoErro("O .shp é pequeno demais para ser um Shapefile.")
    (codigo,) = struct.unpack_from(">i", dados, 0)
    if codigo != 9994:
        raise GeoErro("O arquivo .shp não tem o código 9994 de um Shapefile.")
    (tipo_do_arquivo,) = struct.unpack_from("<i", dados, 32)
    if tipo_do_arquivo not in _TIPOS_POLIGONO | _TIPOS_LINHA:
        raise GeoErro(f"O Shapefile é do tipo de forma {tipo_do_arquivo}, e não polígono nem linha: o Mapa "
                      f"guarda o perímetro do imóvel.")
    formas: list[tuple[str, list]] = []
    pos = 100
    while pos + 8 <= len(dados):
        (_, palavras) = struct.unpack_from(">ii", dados, pos)
        tamanho = palavras * 2
        inicio = pos + 8
        if palavras < 2 or inicio + tamanho > len(dados):
            raise GeoErro("Shapefile truncado: um registro passa do fim do .shp.")
        if len(formas) >= MAX_FEICOES:
            raise GeoErro(f"O Shapefile tem mais de {MAX_FEICOES} feições.")
        (tipo,) = struct.unpack_from("<i", dados, inicio)
        corpo = dados[inicio:inicio + tamanho]
        pos = inicio + tamanho
        if tipo == 0:
            formas.append(("nula", []))
            continue
        if tipo not in _TIPOS_POLIGONO | _TIPOS_LINHA:
            formas.append(("outra", []))
            continue
        if len(corpo) < 44:
            raise GeoErro("Registro do Shapefile curto demais.")
        n_partes, n_pontos = struct.unpack_from("<ii", corpo, 36)
        if n_partes < 0 or n_pontos < 0 or n_pontos > MAX_PONTOS_POR_FEICAO or n_partes > MAX_ANEIS_POR_FEICAO \
                or 44 + 4 * n_partes + 16 * n_pontos > len(corpo):
            raise GeoErro("Registro do Shapefile com contagens impossíveis: arquivo corrompido.")
        partes = list(struct.unpack_from(f"<{n_partes}i", corpo, 44))
        base = 44 + 4 * n_partes
        pontos = [struct.unpack_from("<dd", corpo, base + 16 * i) for i in range(n_pontos)]
        limites = partes + [n_pontos]
        if any(b < a or b > n_pontos for a, b in zip(limites, limites[1:])) or (partes and partes[0] < 0):
            raise GeoErro("Registro do Shapefile com índices de partes inválidos.")
        aneis = [pontos[a:b] for a, b in zip(limites, limites[1:])]
        formas.append(("poligono" if tipo in _TIPOS_POLIGONO else "linha", aneis))
    return formas


_CODIGOS_CPG = {"UTF-8": "utf-8", "UTF8": "utf-8", "65001": "utf-8", "1252": "cp1252", "WINDOWS-1252": "cp1252",
                "CP1252": "cp1252", "ISO-8859-1": "latin-1", "ISO8859-1": "latin-1", "LATIN1": "latin-1",
                "850": "cp850", "437": "cp437"}


def _ler_dbf(dados: bytes, cpg: str | None) -> list[dict | None]:
    """Os registros do `.dbf` como dicionários (`None` no registro apagado, para não perder o alinhamento)."""
    if len(dados) < 33:
        raise GeoErro("O .dbf é pequeno demais.")
    n_registros, tam_cabecalho, tam_registro = struct.unpack_from("<IHH", dados, 4)
    if n_registros > MAX_FEICOES * 4 or tam_cabecalho < 33 or tam_registro < 1 or tam_cabecalho > len(dados):
        raise GeoErro("O .dbf tem cabeçalho inválido.")
    campos = []
    pos = 32
    deslocamento = 1
    while pos + 32 <= tam_cabecalho and dados[pos] != 0x0D:
        nome = dados[pos:pos + 11].split(b"\x00")[0].decode("ascii", "replace").strip()
        tipo = chr(dados[pos + 11])
        tamanho = dados[pos + 16]
        campos.append((nome, tipo, tamanho, dados[pos + 17], deslocamento))
        deslocamento += tamanho
        pos += 32
    codificacao = _CODIGOS_CPG.get((cpg or "").strip().upper())
    registros: list[dict | None] = []
    for i in range(n_registros):
        ini = tam_cabecalho + i * tam_registro
        if ini + tam_registro > len(dados):
            break
        bruto = dados[ini:ini + tam_registro]
        if bruto[:1] == b"*":
            registros.append(None)
            continue
        linha: dict[str, Any] = {}
        for nome, tipo, tamanho, decimais, desloc in campos:
            cru = bruto[desloc:desloc + tamanho]
            texto = _decodificar(cru, codificacao).strip()
            if tipo in "NF":
                if not texto or set(texto) <= {"*"}:
                    linha[nome] = None
                else:
                    try:
                        linha[nome] = int(texto) if decimais == 0 and "." not in texto else float(texto)
                    except ValueError:
                        linha[nome] = None
            elif tipo == "L":
                linha[nome] = {"T": True, "Y": True, "F": False, "N": False}.get(texto.upper()[:1])
            else:
                linha[nome] = texto or None
        registros.append(linha)
    return registros


def _decodificar(cru: bytes, codificacao: str | None) -> str:
    if codificacao:
        return cru.decode(codificacao, "replace").replace("\x00", "")
    try:
        return cru.decode("utf-8").replace("\x00", "")
    except UnicodeDecodeError:
        return cru.decode("cp1252", "replace").replace("\x00", "")


def ler_shapefile(partes: dict[str, bytes], nome: str = "") -> Camada:
    """O Shapefile a partir dos bytes de `.shp`, `.dbf`, `.prj` e `.cpg` (as chaves, sem o ponto, em minúsculas)."""
    if "shp" not in partes:
        raise GeoErro("Faltou o arquivo .shp do Shapefile.")
    formas = _ler_shp(partes["shp"])
    registros = _ler_dbf(partes["dbf"], (partes.get("cpg") or b"").decode("ascii", "ignore")) \
        if "dbf" in partes else []
    avisos: list[str] = []
    if "dbf" not in partes:
        avisos.append("Faltou o arquivo .dbf: as feições vieram sem atributos.")
    wkt = partes["prj"].decode("utf-8", "replace") if "prj" in partes else None
    epsg = epsg_do_wkt(wkt)
    if "prj" not in partes:
        avisos.append("Faltou o arquivo .prj: o arquivo não diz o sistema de coordenadas.")
    feicoes: list[Feicao] = []
    for i, (tipo, aneis) in enumerate(formas):
        atributos = registros[i] if i < len(registros) else {}
        if atributos is None:        # registro apagado no .dbf
            continue
        feicao: Feicao = {"indice": i, "atributos": atributos or {}, "geometria": [], "tipo": "", "avisos": []}
        if tipo == "poligono":
            feicao["geometria"], feicao["tipo"] = montar_poligonos(aneis), "Polygon"
        elif tipo == "linha":
            feicao["geometria"], feicao["tipo"] = [[a] for a in aneis if a], "LineString"
        else:
            feicao["avisos"].append("Forma vazia ou que não é polígono: ignorada.")
        feicoes.append(feicao)
    return {"nome": nome or "shapefile", "epsg": epsg, "origem": "SHP", "feicoes": feicoes, "avisos": avisos,
            "wkt": wkt}


# ------------------------------------------------------------------ Shapefile (escrita)

_TAMANHO_DOS_CAMPOS = {"MATRICULA": 40, "CNS": 20, "PROPRIETAR": 254}


def _texto_dbf(valor: Any, tamanho: int) -> tuple[bytes, bool]:
    """O texto em UTF-8, preenchido com espaço até `tamanho` bytes; corta sem partir caractere. `(bytes, cortou)`."""
    bruto = ("" if valor is None else str(valor)).encode("utf-8")
    cortou = len(bruto) > tamanho
    if cortou:
        bruto = bruto[:tamanho]
        while bruto:
            try:
                bruto.decode("utf-8")
                break
            except UnicodeDecodeError:
                bruto = bruto[:-1]
    return bruto.ljust(tamanho, b" "), cortou


def escrever_shapefile(feicoes: Iterable[dict], *, nome: str = NOME_DA_CAMADA) -> tuple[bytes, list[str]]:
    """O `.zip` com `.shp .shx .dbf .prj .cpg`. Devolve `(zip, avisos)`; aviso diz o que foi cortado.

    Os quatro atributos do Mapa, com os nomes de até dez letras. `PROPRIETAR` tem 254 bytes (o teto do dBase): o
    que passar disso é cortado **e dito** no aviso, com a matrícula. Anéis no sentido do Shapefile (externo
    horário, furo anti-horário).
    """
    if not re.match(r"^[A-Za-z][A-Za-z0-9_]{0,62}$", nome):
        raise GeoErro("Nome de arquivo inválido.")
    lista = [f for f in feicoes if f["geometria"]]
    avisos: list[str] = []
    registros_shp: list[bytes] = []
    todos_x: list[float] = []
    todos_y: list[float] = []
    for f in lista:
        aneis = [a for p in _orientar(f["geometria"], externo_anti_horario=False) for a in p]
        pontos = [p for a in aneis for p in a]
        xs, ys = [p[0] for p in pontos], [p[1] for p in pontos]
        todos_x += xs
        todos_y += ys
        partes, acumulado = [], 0
        for a in aneis:
            partes.append(acumulado)
            acumulado += len(a)
        conteudo = (struct.pack("<i", 5) + struct.pack("<dddd", min(xs), min(ys), max(xs), max(ys))
                    + struct.pack("<ii", len(aneis), len(pontos)) + struct.pack(f"<{len(partes)}i", *partes)
                    + b"".join(struct.pack("<dd", x, y) for x, y in pontos))
        registros_shp.append(conteudo)
    caixa = (min(todos_x), min(todos_y), max(todos_x), max(todos_y)) if todos_x else (0.0, 0.0, 0.0, 0.0)

    def cabecalho(tamanho_em_bytes: int) -> bytes:
        return (struct.pack(">i", 9994) + b"\x00" * 20 + struct.pack(">i", tamanho_em_bytes // 2)
                + struct.pack("<ii", 1000, 5) + struct.pack("<dddd", *caixa) + struct.pack("<dddd", 0, 0, 0, 0))

    corpo_shp = b""
    corpo_shx = b""
    for numero, conteudo in enumerate(registros_shp, start=1):
        corpo_shx += struct.pack(">ii", (100 + len(corpo_shp)) // 2, len(conteudo) // 2)
        corpo_shp += struct.pack(">ii", numero, len(conteudo) // 2) + conteudo
    shp = cabecalho(100 + len(corpo_shp)) + corpo_shp
    shx = cabecalho(100 + len(corpo_shx)) + corpo_shx

    campos = [("MATRICULA", "C", _TAMANHO_DOS_CAMPOS["MATRICULA"], 0), ("CNS", "C", _TAMANHO_DOS_CAMPOS["CNS"], 0),
              ("PROPRIETAR", "C", _TAMANHO_DOS_CAMPOS["PROPRIETAR"], 0), ("AREA_HA", "N", 18, 4)]
    tam_registro = 1 + sum(c[2] for c in campos)
    tam_cabecalho = 32 + 32 * len(campos) + 1
    dbf = struct.pack("<BBBBIHH", 3, 126, 11, 23, len(lista), tam_cabecalho, tam_registro) + b"\x00" * 20
    for nome_do_campo, tipo, tamanho, decimais in campos:
        dbf += nome_do_campo.encode("ascii").ljust(11, b"\x00") + tipo.encode() + b"\x00" * 4 \
            + bytes([tamanho, decimais]) + b"\x00" * 14
    dbf += b"\x0D"
    for f in lista:
        linha = b" "
        for nome_do_campo, tipo, tamanho, decimais in campos:
            valor = f.get(nome_do_campo)
            if tipo == "N":
                texto = "" if valor is None else f"{float(valor):.{decimais}f}"
                linha += texto.rjust(tamanho).encode("ascii")[-tamanho:]
            else:
                bruto, cortou = _texto_dbf(valor, tamanho)
                if cortou:
                    avisos.append(f"{nome_do_campo} da matrícula {f.get('MATRICULA')} passou de {tamanho} bytes "
                                  f"e foi cortado no Shapefile (o GeoPackage não tem esse limite).")
                linha += bruto
        dbf += linha
    dbf += b"\x1A"

    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as pacote:
        pacote.writestr(f"{nome}.shp", shp)
        pacote.writestr(f"{nome}.shx", shx)
        pacote.writestr(f"{nome}.dbf", dbf)
        pacote.writestr(f"{nome}.prj", _PRJ_4674)
        pacote.writestr(f"{nome}.cpg", "UTF-8")
    return saida.getvalue(), avisos


# ------------------------------------------------------------------ GeoJSON

def ler_geojson(dados: bytes, nome: str = "") -> Camada:
    """O GeoJSON (FeatureCollection, Feature ou geometria solta). Sem `crs`, é WGS 84, como manda a RFC 7946."""
    try:
        documento = json.loads(dados.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as erro:
        raise GeoErro("O arquivo não é um JSON válido.") from erro
    if not isinstance(documento, dict) or "type" not in documento:
        raise GeoErro("O JSON não é um GeoJSON (falta `type`).")
    epsg = 4326
    crs = documento.get("crs")
    if isinstance(crs, dict):
        nome_do_crs = str((crs.get("properties") or {}).get("name") or "")
        achado = re.search(r"EPSG[:/]+(\d+)$", nome_do_crs)
        # `OGC:1.3:CRS84` é o WGS 84 em longitude/latitude: o que o GDAL escreve no GeoJSON
        epsg = int(achado.group(1)) if achado else (4326 if "CRS84" in nome_do_crs.upper() else None)
    if documento["type"] == "FeatureCollection":
        itens = documento.get("features") or []
    elif documento["type"] == "Feature":
        itens = [documento]
    else:
        itens = [{"type": "Feature", "geometry": documento, "properties": {}}]
    if len(itens) > MAX_FEICOES:
        raise GeoErro(f"O GeoJSON tem mais de {MAX_FEICOES} feições.")

    def pontos(seq) -> list:
        if not isinstance(seq, list) or len(seq) > MAX_PONTOS_POR_FEICAO:
            raise GeoErro("Coordenadas inválidas no GeoJSON.")
        try:
            return [(float(p[0]), float(p[1])) for p in seq]
        except (TypeError, ValueError, IndexError) as erro:
            raise GeoErro("Coordenada inválida no GeoJSON.") from erro

    feicoes: list[Feicao] = []
    for i, item in enumerate(itens):
        feicao: Feicao = {"indice": i, "atributos": dict((item or {}).get("properties") or {}), "geometria": [],
                          "tipo": "", "avisos": []}
        geometria = (item or {}).get("geometry") or {}
        tipo, coords = geometria.get("type"), geometria.get("coordinates")
        try:
            if tipo == "Polygon":
                feicao["geometria"] = [[pontos(a) for a in coords]]
            elif tipo == "MultiPolygon":
                feicao["geometria"] = [[pontos(a) for a in poligono] for poligono in coords]
            elif tipo == "LineString":
                feicao["geometria"] = [[pontos(coords)]]
            elif tipo == "MultiLineString":
                feicao["geometria"] = [[pontos(linha)] for linha in coords]
            else:
                feicao["avisos"].append(f"Geometria do tipo {tipo or 'vazio'}, e não polígono: ignorada.")
            feicao["tipo"] = tipo or ""
        except (GeoErro, TypeError) as erro:
            feicao["avisos"].append(str(erro))
        feicoes.append(feicao)
    return {"nome": nome or "geojson", "epsg": epsg, "origem": "GEOJSON", "feicoes": feicoes, "avisos": []}


# ------------------------------------------------------------------ o arquivo que o usuário mandou

def _ler_zip(dados: bytes) -> list[Camada]:
    """O `.zip`: Shapefiles (`.shp` + `.dbf` + `.prj` + `.cpg` de mesmo nome), GeoPackages e GeoJSON dentro dele.

    Os tetos são os da casa (`tetos_de_entrada`: entradas, bytes que o pacote declara e bytes que de fato saem
    de cada membro — o índice do `.zip` pode mentir).
    """
    try:
        pacote = zipfile.ZipFile(io.BytesIO(dados))
    except zipfile.BadZipFile as erro:
        raise GeoErro("O arquivo .zip está corrompido.") from erro
    with pacote:
        try:
            TETOS.conferir_pacote(pacote)
            camadas: list[Camada] = []
            grupos: dict[str, dict[str, bytes]] = {}
            for info in pacote.infolist():
                nome_do_membro = info.filename.replace("\\", "/")
                if info.is_dir() or "__MACOSX" in nome_do_membro or nome_do_membro.rsplit("/", 1)[-1].startswith("."):
                    continue
                base, _, extensao = nome_do_membro.rpartition(".")
                extensao = extensao.lower()
                if extensao in ("shp", "dbf", "prj", "cpg", "shx"):
                    grupo = grupos.setdefault(base.lower(), {})
                    if extensao != "shx":          # o índice não se usa: lemos o .shp em sequência
                        grupo[extensao] = TETOS.ler_membro(pacote, info)
                    grupo.setdefault("_nome", nome_do_membro.rsplit("/", 1)[-1].encode())
                elif extensao == "gpkg":
                    camadas += ler_gpkg(TETOS.ler_membro(pacote, info), nome_do_membro)
                elif extensao in ("geojson", "json"):
                    camadas.append(ler_geojson(TETOS.ler_membro(pacote, info), nome_do_membro.rsplit("/", 1)[-1]))
        except TETOS.TetoExcedido as erro:
            raise GeoErro(str(erro)) from erro
        for partes in grupos.values():
            if "shp" in partes:
                nome = partes.pop("_nome").decode("utf-8", "replace").rsplit(".", 1)[0]
                camadas.append(ler_shapefile(partes, nome))
    if not camadas:
        raise GeoErro("O .zip não tem nenhum Shapefile (.shp), GeoPackage (.gpkg) ou GeoJSON.")
    return camadas


def ler_arquivo(nome: str, dados: bytes) -> list[Camada]:
    """As camadas do arquivo, reconhecido pelo CONTEÚDO (e não pela extensão): `.zip`, `.gpkg` ou GeoJSON.

    Um `.shp` solto não basta (faltam `.dbf` e `.prj`): a tela pede o `.zip`.
    """
    if not dados:
        raise GeoErro("O arquivo está vazio.")
    if len(dados) > MAX_BYTES_DO_ARQUIVO:
        raise GeoErro("O arquivo passa do limite de tamanho.")
    if dados[:2] == b"PK":
        return _ler_zip(dados)
    if dados.startswith(b"SQLite format 3\x00"):
        return ler_gpkg(dados, nome)
    if dados[:4] == b"\x00\x00\x27\x0a":      # o .shp solto: código 9994 big-endian
        raise GeoErro("Isto é um .shp solto. Mande um .zip com o .shp, o .dbf e o .prj juntos.")
    if dados.lstrip()[:1] in (b"{", b"["):
        return [ler_geojson(dados, nome)]
    raise GeoErro("Formato não reconhecido. Aceitam-se GeoPackage (.gpkg), Shapefile (.zip com .shp, .dbf e "
                  ".prj) e GeoJSON (.geojson).")
