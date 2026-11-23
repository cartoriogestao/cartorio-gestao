"""Os formatos do mapa — `geo_formatos.py` (RI011, S9).

O QUE ESTES TESTES PROTEGEM
    ler o que o GDAL escreve   `tests/dados_geo/gdal_*` foram feitos pelo GDAL 3.12 (o escritor do QGIS) com geometria
                               FICTÍCIA: um GeoPackage, dois Shapefiles (SIRGAS e UTM 23S, com o `.prj` do ESRI), um
                               GeoJSON em WGS 84 e uma linha aberta. O leitor daqui lê os cinco sem o GDAL
    escrever o que o GDAL lê   o `.gpkg` e o Shapefile gerados têm as tabelas e os campos que o ONR descreve; na
                               bancada foram abertos pelo GDAL e pelo pyshp (aqui, lidos de volta pelo leitor próprio e
                               conferidos byte a byte nos cabeçalhos)
    arquivo hostil             `.zip` bomba, contagem impossível, `.shp` truncado, SQLite que não é GeoPackage, JSON
                               torto: tudo vira `GeoErro` com frase — e nada cai com `struct.error`

Geometria fictícia, perto de uma latitude do Nordeste: não representa imóvel nenhum.
"""
from __future__ import annotations

import io
import json
import sqlite3
import struct
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

pytest.importorskip("geographiclib")

import geo_formatos as F
import geo_geodesia as G

DADOS = Path(__file__).resolve().parent / "dados_geo"


def _ler(nome: str):
    return F.ler_arquivo(nome, (DADOS / nome).read_bytes())


# ------------------------------------------------------------------ ler o que o GDAL escreve

def test_le_o_geopackage_do_gdal_com_furo_e_multipoligono():
    (camada,) = _ler("gdal_geo.gpkg")
    assert camada["epsg"] == 4674 and camada["origem"] == "GPKG"
    primeira, segunda = camada["feicoes"]
    assert primeira["atributos"]["MATRICULA"] == "4015"
    assert primeira["atributos"]["PROPRIETAR"] == "JOSÉ EXEMPLO; MARIA AÇÃO"        # os acentos voltam inteiros
    assert primeira["atributos"]["AREA_HA"] == pytest.approx(1.2345)
    assert [len(p) for p in primeira["geometria"]] == [2]                              # um polígono: externo + furo
    assert len(segunda["geometria"]) == 2                                              # multipolígono: dois
    assert primeira["tipo"] in ("Polygon", "MultiPolygon") and segunda["tipo"] == "MultiPolygon"   # o GDAL promove a camada


def test_le_o_shapefile_do_gdal_e_o_sistema_do_prj():
    (camada,) = _ler("gdal_sirgas.zip")
    assert camada["epsg"] == 4674 and camada["origem"] == "SHP" and camada["nome"] == "gdal_geo"
    primeira, segunda = camada["feicoes"]
    assert primeira["atributos"]["PROPRIETAR"] == "JOSÉ EXEMPLO; MARIA AÇÃO"
    assert [len(p) for p in primeira["geometria"]] == [2] and len(segunda["geometria"]) == 2


def test_o_shapefile_e_o_geopackage_do_mesmo_desenho_dao_a_mesma_area():
    gpkg = _ler("gdal_geo.gpkg")[0]["feicoes"][0]["geometria"]
    shp = _ler("gdal_sirgas.zip")[0]["feicoes"][0]["geometria"]
    assert G.area_perimetro(gpkg)[0] == pytest.approx(G.area_perimetro(shp)[0], rel=1e-9)
    # 0,01° × 0,01° menos o furo de 0,002° × 0,002°, a ~7° de latitude; 117,2612 ha pelo PROJ (Geod, GRS 1980)
    assert G.hectares(G.area_perimetro(gpkg)[0]) == pytest.approx(117.2612, abs=0.001)


def test_o_utm_23s_com_prj_do_esri_vira_epsg_31983_e_volta_ao_mesmo_lugar():
    (utm,) = _ler("gdal_utm23s.zip")
    assert utm["epsg"] == 31983, "o .prj do ESRI não traz o código: o nome «SIRGAS_2000_UTM_Zone_23S» decide"
    sistema = G.sistema_do_epsg(utm["epsg"])
    em_utm = utm["feicoes"][0]["geometria"]
    em_graus = [[G.para_sirgas(anel, sistema) for anel in poligono] for poligono in em_utm]
    esperado = _ler("gdal_sirgas.zip")[0]["feicoes"][0]["geometria"]
    for anel_utm, anel_ref in zip(em_graus[0], esperado[0]):
        for (lon, lat), (rlon, rlat) in zip(anel_utm, anel_ref):
            assert lon == pytest.approx(rlon, abs=2e-8) and lat == pytest.approx(rlat, abs=2e-8)
    assert G.area_perimetro(em_graus)[0] == pytest.approx(G.area_perimetro(esperado)[0], rel=1e-7)


def test_o_geojson_e_wgs84_por_padrao_da_rfc():
    (camada,) = _ler("gdal_wgs84.geojson")
    assert camada["epsg"] == 4326 and camada["origem"] == "GEOJSON" and len(camada["feicoes"]) == 2
    assert G.sistema_do_epsg(camada["epsg"])["aviso"]


def test_a_linha_aberta_vem_como_linha_e_a_conferencia_acusa_o_fechamento():
    (camada,) = _ler("gdal_linha_aberta.zip")
    feicao = camada["feicoes"][0]
    assert feicao["tipo"] == "LineString"
    achados = G.analisar(feicao["geometria"])["achados"]
    assert "FECHAMENTO" in [a["codigo"] for a in achados]


def test_o_arquivo_e_reconhecido_pelo_conteudo_e_nao_pelo_nome():
    dados = (DADOS / "gdal_geo.gpkg").read_bytes()
    assert F.ler_arquivo("qualquer_coisa.dat", dados)[0]["origem"] == "GPKG"
    assert F.ler_arquivo("x.bin", (DADOS / "gdal_wgs84.geojson").read_bytes())[0]["origem"] == "GEOJSON"


# ------------------------------------------------------------------ escrever

def _feicoes():
    quadrado = [(-45.5, -7.2), (-45.49, -7.2), (-45.49, -7.19), (-45.5, -7.19), (-45.5, -7.2)]
    furo = [(-45.498, -7.198), (-45.496, -7.198), (-45.496, -7.196), (-45.498, -7.196), (-45.498, -7.198)]
    outro = [(-45.4, -7.2), (-45.39, -7.2), (-45.39, -7.19), (-45.4, -7.2)]
    return [
        {"geometria": [[quadrado, furo]], "MATRICULA": "4015", "CNS": "000000",
         "PROPRIETAR": "JOSÉ EXEMPLO; MARIA AÇÃO", "AREA_HA": 1.2345},
        {"geometria": [[outro]], "MATRICULA": "4016-A", "CNS": "000000", "PROPRIETAR": "", "AREA_HA": None},
    ]


def test_o_geopackage_gerado_tem_as_tabelas_e_os_campos_do_mapa():
    dados = F.escrever_gpkg(_feicoes())
    con = sqlite3.connect(":memory:")
    con.deserialize(dados)
    assert con.execute("PRAGMA application_id").fetchone()[0] == 0x47504B47
    assert {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")} >= {
        "gpkg_spatial_ref_sys", "gpkg_contents", "gpkg_geometry_columns", "mapa_onr"}
    colunas = [r[1] for r in con.execute("PRAGMA table_info(mapa_onr)")]
    assert colunas == ["fid", "geom", "MATRICULA", "CNS", "PROPRIETAR", "AREA_HA"]
    assert con.execute("SELECT srs_id, geometry_type_name FROM gpkg_geometry_columns").fetchone() == (4674, "MULTIPOLYGON")
    assert con.execute("SELECT organization_coordsys_id FROM gpkg_spatial_ref_sys WHERE srs_id=4674").fetchone()[0] == 4674
    linha = con.execute("SELECT MATRICULA, CNS, PROPRIETAR, AREA_HA FROM mapa_onr ORDER BY fid").fetchall()
    assert linha == [("4015", "000000", "JOSÉ EXEMPLO; MARIA AÇÃO", 1.2345), ("4016-A", "000000", "", None)]


def test_o_geopackage_gerado_e_lido_de_volta_com_a_mesma_geometria():
    (camada,) = F.ler_arquivo("mapa.gpkg", F.escrever_gpkg(_feicoes()))
    assert camada["epsg"] == 4674 and camada["nome"] == "mapa_onr"
    primeira = camada["feicoes"][0]
    assert primeira["atributos"]["MATRICULA"] == "4015" and [len(p) for p in primeira["geometria"]] == [2]
    original = G.area_perimetro(_feicoes()[0]["geometria"])[0]
    assert G.area_perimetro(primeira["geometria"])[0] == pytest.approx(original, rel=1e-9)


def test_o_shapefile_gerado_traz_os_cinco_arquivos_e_os_nomes_de_ate_dez_letras():
    conteudo, avisos = F.escrever_shapefile(_feicoes())
    assert avisos == []
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        assert sorted(z.namelist()) == ["mapa_onr.cpg", "mapa_onr.dbf", "mapa_onr.prj", "mapa_onr.shp", "mapa_onr.shx"]
        dbf = z.read("mapa_onr.dbf")
        assert z.read("mapa_onr.cpg") == b"UTF-8" and b"GCS_SIRGAS_2000" in z.read("mapa_onr.prj")
        shp, shx = z.read("mapa_onr.shp"), z.read("mapa_onr.shx")
    nomes = [dbf[32 + 32 * i:32 + 32 * i + 11].split(b"\x00")[0].decode() for i in range(4)]
    assert nomes == ["MATRICULA", "CNS", "PROPRIETAR", "AREA_HA"] and all(len(n) <= 10 for n in nomes)
    assert struct.unpack(">i", shp[:4])[0] == 9994 and struct.unpack(">i", shp[24:28])[0] * 2 == len(shp)
    assert struct.unpack(">i", shx[24:28])[0] * 2 == len(shx) == 100 + 8 * 2


def test_o_shapefile_gerado_e_lido_de_volta():
    conteudo, _ = F.escrever_shapefile(_feicoes())
    (camada,) = F.ler_arquivo("mapa.zip", conteudo)
    assert camada["epsg"] == 4674 and len(camada["feicoes"]) == 2
    primeira = camada["feicoes"][0]
    assert primeira["atributos"] == {"MATRICULA": "4015", "CNS": "000000", "PROPRIETAR": "JOSÉ EXEMPLO; MARIA AÇÃO",
                                     "AREA_HA": 1.2345}
    assert [len(p) for p in primeira["geometria"]] == [2]


def test_o_proprietario_comprido_e_cortado_no_shapefile_e_o_corte_e_dito():
    longo = _feicoes()
    longo[0]["PROPRIETAR"] = "ÇÃO " * 100
    conteudo, avisos = F.escrever_shapefile(longo)
    assert len(avisos) == 1 and "4015" in avisos[0] and "254" in avisos[0]
    (camada,) = F.ler_arquivo("m.zip", conteudo)
    texto = camada["feicoes"][0]["atributos"]["PROPRIETAR"]
    assert len(texto.encode("utf-8")) <= 254 and texto.startswith("ÇÃO ÇÃO")     # cortou sem partir caractere
    # o GeoPackage não tem o limite
    (gpkg,) = F.ler_arquivo("m.gpkg", F.escrever_gpkg(longo))
    assert gpkg["feicoes"][0]["atributos"]["PROPRIETAR"] == "ÇÃO " * 100


def test_o_externo_sai_no_sentido_de_cada_formato():
    anti = [(0, 0), (4, 0), (4, 4), (0, 4)]
    assert F._area_assinada(anti) > 0
    horario = F._orientar([[anti]], externo_anti_horario=False)[0][0][:-1]
    assert F._area_assinada(horario) < 0
    assert F._area_assinada(F._orientar([[anti[::-1]]], externo_anti_horario=True)[0][0][:-1]) > 0


# ------------------------------------------------------------------ montar polígonos pelo aninhamento

def test_o_anel_dentro_de_outro_e_furo_qualquer_que_seja_o_sentido():
    externo = [(0, 0), (10, 0), (10, 10), (0, 10)]
    dentro_mesmo_sentido = [(2, 2), (4, 2), (4, 4), (2, 4)]          # o arquivo não seguiu a convenção
    outro_lugar = [(20, 0), (30, 0), (30, 10), (20, 10)]
    polis = F.montar_poligonos([dentro_mesmo_sentido, externo, outro_lugar])
    assert sorted(len(p) for p in polis) == [1, 2]
    com_furo = next(p for p in polis if len(p) == 2)
    assert com_furo[0] == externo and com_furo[1] == dentro_mesmo_sentido


def test_a_ilha_dentro_do_furo_e_outro_poligono():
    grande = [(0, 0), (20, 0), (20, 20), (0, 20)]
    furo = [(2, 2), (18, 2), (18, 18), (2, 18)]
    ilha = [(8, 8), (12, 8), (12, 12), (8, 12)]
    polis = F.montar_poligonos([grande, furo, ilha])
    assert sorted(len(p) for p in polis) == [1, 2]


# ------------------------------------------------------------------ o sistema no .prj

@pytest.mark.parametrize("wkt, epsg", [
    ('GEOGCS["SIRGAS 2000",DATUM["x",SPHEROID["GRS 1980",6378137,298.257222101,AUTHORITY["EPSG","7019"]],'
     'AUTHORITY["EPSG","6674"]],AUTHORITY["EPSG","4674"]]', 4674),
    ('GEOGCS["GCS_SIRGAS_2000",DATUM["D_SIRGAS_2000",SPHEROID["GRS_1980",6378137.0,298.257222101]]]', 4674),
    ('PROJCS["SIRGAS_2000_UTM_Zone_22S",GEOGCS["GCS_SIRGAS_2000"]]', 31982),
    ('PROJCS["SIRGAS 2000 / UTM zone 23S",GEOGCS["SIRGAS 2000"],AUTHORITY["EPSG","31983"]]', 31983),
    ('GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984"]]', 4326),
    ('GEOGCS["GCS_South_American_1969",DATUM["D_South_American_1969"]]', 4618),
    ('GEOGCS["GCS_Corrego_Alegre",DATUM["D_Corrego_Alegre"]]', 4225),
    ('PROJCRS["SIRGAS 2000 / UTM zone 21S",ID["EPSG",31981]]', 31981),
    ("", None), (None, None), ('LOCAL_CS["qualquer coisa"]', None),
])
def test_o_sistema_que_o_prj_declara(wkt, epsg):
    assert F.epsg_do_wkt(wkt) == epsg


# ------------------------------------------------------------------ arquivo hostil

def test_arquivo_vazio_ou_de_formato_desconhecido():
    with pytest.raises(G.GeoErro):
        F.ler_arquivo("x", b"")
    with pytest.raises(G.GeoErro) as erro:
        F.ler_arquivo("x.txt", b"isto nao e mapa")
    assert "GeoPackage" in str(erro.value) and "Shapefile" in str(erro.value)


def test_shp_solto_pede_o_zip():
    shp = zipfile.ZipFile(DADOS / "gdal_sirgas.zip").read("gdal_geo.shp")
    with pytest.raises(G.GeoErro) as erro:
        F.ler_arquivo("x.shp", shp)
    assert ".zip" in str(erro.value)


def test_sqlite_que_nao_e_geopackage():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE t (a)")
    with pytest.raises(G.GeoErro) as erro:
        F.ler_arquivo("x.gpkg", bytes(con.serialize()))
    assert "GeoPackage" in str(erro.value)


def test_geopackage_cujo_nome_de_tabela_e_malicioso_nao_vira_sql():
    """O nome da tabela vem do arquivo: aqui vem com aspas e ponto e vírgula. Não entra no SQL."""
    base = F.escrever_gpkg(_feicoes())
    con = sqlite3.connect(":memory:")
    con.deserialize(base)
    con.execute("UPDATE gpkg_contents SET table_name = 'mapa_onr\"; DROP TABLE mapa_onr; --'")
    con.execute("UPDATE gpkg_geometry_columns SET table_name = 'mapa_onr\"; DROP TABLE mapa_onr; --'")
    con.commit()
    with pytest.raises(G.GeoErro):
        F.ler_arquivo("x.gpkg", bytes(con.serialize()))


def test_shapefile_truncado_ou_com_contagem_impossivel():
    z = zipfile.ZipFile(DADOS / "gdal_sirgas.zip")
    shp = z.read("gdal_geo.shp")
    partes = {"shp": shp[:-20], "dbf": z.read("gdal_geo.dbf"), "prj": z.read("gdal_geo.prj")}
    with pytest.raises(G.GeoErro):
        F.ler_shapefile(partes)
    # número de pontos de dois bilhões no primeiro registro (offset 100 + 8 + 4 + 32 + 4 = 148)
    ruim = bytearray(shp)
    struct.pack_into("<i", ruim, 100 + 8 + 4 + 32 + 4, 2_000_000_000)
    with pytest.raises(G.GeoErro):
        F.ler_shapefile({"shp": bytes(ruim), "dbf": partes["dbf"]})
    with pytest.raises(G.GeoErro):
        F.ler_shapefile({"dbf": partes["dbf"]})


def test_shapefile_de_pontos_nao_e_poligono():
    z = zipfile.ZipFile(DADOS / "gdal_sirgas.zip")
    shp = bytearray(z.read("gdal_geo.shp"))
    struct.pack_into("<i", shp, 32, 1)
    with pytest.raises(G.GeoErro) as erro:
        F.ler_shapefile({"shp": bytes(shp)})
    assert "polígono" in str(erro.value)


def test_zip_bomba_e_recusado_pelos_tetos_da_casa(monkeypatch):
    monkeypatch.setenv("CG_TETO_ZIP_BYTES", "1000")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("grande.geojson", b"0" * 50_000)
    with pytest.raises(G.GeoErro) as erro:
        F.ler_arquivo("x.zip", buffer.getvalue())
    assert "teto" in str(erro.value)


def test_zip_sem_nada_de_mapa_e_zip_corrompido():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("leia-me.txt", "nada")
    with pytest.raises(G.GeoErro):
        F.ler_arquivo("x.zip", buffer.getvalue())
    with pytest.raises(G.GeoErro):
        F.ler_arquivo("x.zip", b"PK\x03\x04lixo")


@pytest.mark.parametrize("texto", ['{"nada": 1}', "[1, 2", '{"type": "FeatureCollection", "features": 5}'])
def test_geojson_torto(texto):
    with pytest.raises((G.GeoErro, TypeError)):
        F.ler_arquivo("x.geojson", texto.encode())


def test_geojson_com_ponto_nao_entra_e_diz_por_que():
    corpo = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"a": 1}, "geometry": {"type": "Point", "coordinates": [-45.5, -7.2]}}]}
    (camada,) = F.ler_arquivo("x.geojson", json.dumps(corpo).encode())
    assert camada["feicoes"][0]["geometria"] == [] and "não polígono" in " ".join(camada["feicoes"][0]["avisos"])


def test_wkb_truncado_e_tipo_que_nao_e_poligono():
    wkb = F.wkb_de_geometria([[[(0, 0), (1, 0), (1, 1), (0, 0)]]])
    with pytest.raises(G.GeoErro):
        F.geometria_de_wkb(wkb[:-8])
    ponto = b"\x01" + struct.pack("<I", 1) + struct.pack("<dd", 1.0, 2.0)
    with pytest.raises(G.GeoErro):
        F.geometria_de_wkb(ponto)


def test_wkb_com_z_e_srid_perde_so_a_altura():
    z = (b"\x01" + struct.pack("<I", 3 | 0x80000000 | 0x20000000) + struct.pack("<I", 4674)
         + struct.pack("<II", 1, 4) + b"".join(struct.pack("<ddd", x, y, 100.0)
                                                for x, y in [(0, 0), (1, 0), (1, 1), (0, 0)]))
    geometria, tipo = F.geometria_de_wkb(z)
    assert tipo == "Polygon" and geometria == [[[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0)]]]
