"""Os polígonos do mapa — `ri_geo.py` e `ri_geo_web.py` (RI011, S9).

O QUE ESTES TESTES PROTEGEM

    guardar com a origem     arquivo, SHA-256, camada, sistema, quem desenhou e quem importou; os atributos como vieram
    nunca adotar sozinho     a importação só SUGERE a matrícula; quem adota é a pessoa; um vigente por matrícula, e o
                             banco recusa o segundo
    trocar sem apagar        o vigente que sai vira SUBSTITUÍDO e fica; o descartado fica, com o motivo
    medir e comparar         área geodésica ao lado da registrada; a que «não bate» é marcada
    conferir                 fechamento, cruzamento, sobreposição, matrícula aberta — e o que tem ERRO fica fora do arquivo
    a decisão do oficial     sem escolher a regra da área, o arquivo não se gera; com ela, AREA_HA sai pela regra
    só ADMIN baixa           o arquivo leva o nome de cada proprietário; a baixa fica na auditoria

Geometria FICTÍCIA (`tests/dados_geo`), perto de uma latitude do Nordeste; nenhum dado de imóvel real.
Nenhum teste fala com o ONR nem com o Mapa.
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

pytest.importorskip("geographiclib")

import geo_formatos as F
import geo_geodesia as G
import ri_geo as RG
from bd_nativo import banco
from conftest import cg_login

SENHA = "Senha#12345"
AGORA = "2026-11-23T10:00:00"
DADOS = Path(__file__).resolve().parent / "dados_geo"
QUEM = {"quem": "Maria Exemplo", "quem_id": 7, "agora": AGORA}


@pytest.fixture()
def db(cg_casa):
    cg_casa["db"].set_settings({"ri_cns": "000000"})
    return cg_casa["db"]


def _matricula(db, numero, **campos) -> int:
    base = {"numero": str(numero), "livro": "2", "livro_norm": "2", "tipo_ficha": "ESTRUTURADA",
            "criado_em": AGORA}
    base.update(campos)
    with db.transaction() as con:
        return banco(con).escrever(
            f"INSERT INTO ri_matriculas ({', '.join(base)}) VALUES ({', '.join(['%s'] * len(base))}) RETURNING id",
            tuple(base.values()))[0]["id"]


def _dono(db, matricula_id, nome="FULANO EXEMPLO") -> None:
    with db.transaction() as con:
        banco(con).escrever("INSERT INTO ri_partes (matricula_id, nome, proprietario, proprietario_ativo) "
                            "VALUES (%s,%s,1,1)", (matricula_id, nome))


def _importar(db, nome, dados=None, **extra):
    dados = dados if dados is not None else (DADOS / nome).read_bytes()
    with db.transaction() as con:
        return RG.importar(con, nome=nome, dados=dados, **{**QUEM, **extra})


def _linha(db, gid):
    with db.connect() as con:
        return dict(banco(con).um("SELECT * FROM ri_geometrias WHERE id = %s", (gid,)))


def _quadrado(lon, lat, lado=0.01) -> list:
    return [(lon, lat), (lon + lado, lat), (lon + lado, lat + lado), (lon, lat + lado), (lon, lat)]


def _geojson(feicoes: list[dict]) -> bytes:
    return json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": p, "geometry": {"type": "Polygon", "coordinates": [anel]}}
        for p, anel in feicoes]}).encode()


# ------------------------------------------------------------------ importar

def test_importar_geopackage_guarda_a_origem_e_nao_adota_nada(db):
    _matricula(db, 4015)
    resumo = _importar(db, "gdal_geo.gpkg", levantamento="ART 0000000 — exemplo", responsavel_tecnico="Técnica Exemplo")
    assert resumo["formato"] == "GPKG" and resumo["origem"] == "GPKG" and resumo["epsg"] == 4674
    assert len(resumo["geometrias"]) == 2 and resumo["sugeridas"] == 1 and resumo["com_erro"] == 0
    with db.connect() as con:
        imp = dict(banco(con).um("SELECT * FROM ri_geo_importacoes WHERE id = %s", (resumo["importacao_id"],)))
    assert imp["arquivo_nome"] == "gdal_geo.gpkg" and len(imp["arquivo_sha256"]) == 64
    assert imp["importado_por"] == "Maria Exemplo" and imp["levantamento"].startswith("ART")
    primeira = _linha(db, resumo["geometrias"][0])
    assert primeira["situacao"] == RG.PENDENTE, "a importação nunca adota sozinha"
    assert primeira["matricula_declarada"] == "4015" and primeira["matricula_id"] is not None   # só a sugestão
    assert primeira["responsavel_tecnico"] == "Técnica Exemplo"
    assert json.loads(primeira["origem_atributos"])["PROPRIETAR"] == "JOSÉ EXEMPLO; MARIA AÇÃO"
    assert primeira["area_geodesica_m2"] / 10_000 == pytest.approx(117.2612, abs=0.001)
    assert _linha(db, resumo["geometrias"][1])["matricula_id"] is None      # 4016-A não existe: sem sugestão


def test_a_sugestao_entende_complemento_e_ponto_de_milhar(db):
    mid = _matricula(db, 4016, complemento="A")
    with db.connect() as con:
        assert [f["id"] for f in RG.achar_matriculas(con, "4.016 a")] == [mid]
        assert [f["id"] for f in RG.achar_matriculas(con, "4016-A")] == [mid]
        assert RG.achar_matriculas(con, "4016") == []        # a ficha 4016-A não é a 4016
        assert RG.achar_matriculas(con, "") == []


def test_mesma_matricula_em_dois_livros_nao_e_sugerida(db):
    _matricula(db, 4015, livro="2", livro_norm="2")
    _matricula(db, 4015, livro="2-F", livro_norm="2F")
    resumo = _importar(db, "gdal_geo.gpkg")
    assert _linha(db, resumo["geometrias"][0])["matricula_id"] is None, "o sistema não escolhe entre duas fichas"


def test_shapefile_em_utm_23s_chega_ao_mesmo_lugar_e_com_a_mesma_area(db):
    sirgas = _importar(db, "gdal_sirgas.zip")
    utm = _importar(db, "gdal_utm23s.zip")
    assert utm["epsg"] == 31983 and utm["formato"] == "SHP"
    a, b = _linha(db, sirgas["geometrias"][0]), _linha(db, utm["geometrias"][0])
    assert b["area_geodesica_m2"] == pytest.approx(a["area_geodesica_m2"], rel=1e-7)
    assert (b["min_lon"], b["min_lat"]) == pytest.approx((a["min_lon"], a["min_lat"]), abs=1e-7)


def test_geojson_entra_com_aviso_de_wgs84(db):
    resumo = _importar(db, "gdal_wgs84.geojson")
    assert resumo["epsg"] == 4326 and any("WGS 84" in a for a in resumo["avisos"])


def test_parcela_do_sigef_guarda_a_origem_e_o_codigo_do_atributo(db):
    corpo = _geojson([({"parcela_co": "00000000-0000-0000-0000-000000000000", "matricula": "4015"},
                       _quadrado(-45.5, -7.2))])
    resumo = _importar(db, "parcela.geojson", corpo, origem_declarada="SIGEF", levantamento="certificada em 2026")
    assert resumo["origem"] == "SIGEF" and resumo["formato"] == "GEOJSON"
    linha = _linha(db, resumo["geometrias"][0])
    assert linha["origem"] == "SIGEF" and linha["sigef_codigo"] == "00000000-0000-0000-0000-000000000000"
    assert linha["matricula_declarada"] == "4015"
    # sem declarar que é do SIGEF, o código não é inventado
    de_novo = _importar(db, "parcela.geojson", corpo)
    assert _linha(db, de_novo["geometrias"][0])["sigef_codigo"] is None and de_novo["origem"] == "GEOJSON"


def test_linha_aberta_vira_poligono_com_erro_de_fechamento_e_nao_se_adota(db):
    mid = _matricula(db, 4020)
    resumo = _importar(db, "gdal_linha_aberta.zip")
    linha = _linha(db, resumo["geometrias"][0])
    codigos = {a["codigo"]: a["nivel"] for a in RG.achados_da_linha(linha)}
    assert codigos["FECHAMENTO"] == G.ERRO and codigos["LINHA"] == G.AVISO and resumo["com_erro"] == 1
    with pytest.raises(RG.GeoImportError) as erro:
        with db.transaction() as con:
            RG.adotar(con, linha["id"], mid, **QUEM)
    assert "erro" in str(erro.value)


def test_arquivo_sem_prj_pede_o_sistema_e_com_ele_importa(db):
    z = zipfile.ZipFile(DADOS / "gdal_sirgas.zip")
    sem_prj = io.BytesIO()
    with zipfile.ZipFile(sem_prj, "w") as novo:
        for nome in z.namelist():
            if not nome.endswith(".prj"):
                novo.writestr(nome, z.read(nome))
    with pytest.raises(RG.GeoImportError) as erro:
        _importar(db, "sem_prj.zip", sem_prj.getvalue())
    assert "sistema de coordenadas" in str(erro.value)
    assert _importar(db, "sem_prj.zip", sem_prj.getvalue(), epsg=4674)["epsg"] == 4674
    with db.connect() as con:
        assert banco(con).um("SELECT count(*) AS n FROM ri_geo_importacoes")["n"] == 1, "a recusa não grava nada"


def test_datum_antigo_e_recusado_sem_gravar(db):
    with pytest.raises(RG.GeoImportError) as erro:
        _importar(db, "gdal_sirgas.zip", epsg=4618)
    assert "SIRGAS 2000" in str(erro.value)
    with db.connect() as con:
        assert banco(con).um("SELECT count(*) AS n FROM ri_geometrias")["n"] == 0


def test_arquivo_com_mais_de_uma_camada_pergunta_qual(db):
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as novo:
        for pacote in ("gdal_sirgas.zip", "gdal_linha_aberta.zip"):
            for nome in zipfile.ZipFile(DADOS / pacote).namelist():
                novo.writestr(nome, zipfile.ZipFile(DADOS / pacote).read(nome))
    with pytest.raises(RG.GeoImportError) as erro:
        _importar(db, "duas.zip", z.getvalue())
    assert "mais de uma camada" in str(erro.value) and "gdal_geo" in str(erro.value)
    assert _importar(db, "duas.zip", z.getvalue(), camada="gdal_linha")["camada"] == "gdal_linha"


def test_arquivo_de_ponto_nao_importa_nada(db):
    corpo = json.dumps({"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [-45.5, -7.2]}})
    with pytest.raises(RG.GeoImportError) as erro:
        _importar(db, "ponto.geojson", corpo.encode())
    assert "Nenhuma feição" in str(erro.value)


# ------------------------------------------------------------------ adotar, substituir, descartar

def test_adotar_faz_o_vigente_e_so_um_por_matricula(db):
    mid = _matricula(db, 4015)
    a, b = _importar(db, "gdal_geo.gpkg")["geometrias"], _importar(db, "gdal_sirgas.zip")["geometrias"]
    with db.transaction() as con:
        saida = RG.adotar(con, a[0], mid, **QUEM)
    assert saida["matricula"] == "4015" and saida["substituiu"] is None
    linha = _linha(db, a[0])
    assert linha["situacao"] == RG.VIGENTE and linha["adotada_por"] == "Maria Exemplo" and linha["adotada_em"] == AGORA
    with db.transaction() as con:
        saida = RG.adotar(con, b[0], mid, **{**QUEM, "agora": "2026-11-24T08:00:00"})
    assert saida["substituiu"] == a[0]
    assert _linha(db, a[0])["situacao"] == RG.SUBSTITUIDA and _linha(db, a[0])["substituida_por"] == b[0]
    assert _linha(db, b[0])["situacao"] == RG.VIGENTE
    with db.connect() as con:
        ficha = RG.da_matricula(con, mid)
    assert ficha["vigente"]["id"] == b[0] and [h["id"] for h in ficha["historico"]] == [a[0]]


def test_o_banco_recusa_dois_vigentes_na_mesma_matricula(db):
    mid = _matricula(db, 4015)
    a, b = _importar(db, "gdal_geo.gpkg")["geometrias"][:1], _importar(db, "gdal_sirgas.zip")["geometrias"][:1]
    with db.transaction() as con:
        RG.adotar(con, a[0], mid, **QUEM)
    with pytest.raises(Exception) as erro:
        with db.transaction() as con:
            banco(con).escrever("UPDATE ri_geometrias SET matricula_id = %s, situacao = 'VIGENTE' WHERE id = %s",
                                (mid, b[0]))
    # a ponte do banco traduz a violação de unicidade no texto do SQLite; o índice parcial é quem a levantou
    assert "UNIQUE" in str(erro.value).upper() or "ux_ri_geometrias_vigente" in str(erro.value)


def test_adotar_em_matricula_encerrada_adota_com_aviso(db):
    mid = _matricula(db, 4015, encerrada=1, situacao="ENCERRADA")
    gid = _importar(db, "gdal_geo.gpkg")["geometrias"][0]
    with db.transaction() as con:
        saida = RG.adotar(con, gid, mid, **QUEM)
    assert saida["avisos"] and "não vai ao arquivo" in saida["avisos"][0]


def test_adotar_em_matricula_que_nao_existe_ou_polígono_que_nao_existe(db):
    gid = _importar(db, "gdal_geo.gpkg")["geometrias"][0]
    with pytest.raises(RG.GeoImportError):
        with db.transaction() as con:
            RG.adotar(con, gid, 999999, **QUEM)
    with pytest.raises(RG.GeoImportError):
        with db.transaction() as con:
            RG.adotar(con, 999999, 1, **QUEM)


def test_adotar_em_lote_so_as_sugestoes_sem_erro_e_sem_trocar_vigente(db):
    livre, ocupada = _matricula(db, 4015), _matricula(db, 4020)
    corpo = _geojson([({"matricula": "4015"}, _quadrado(-45.5, -7.2)),
                      ({"matricula": "4020"}, _quadrado(-45.4, -7.2)),
                      ({"matricula": "4999"}, _quadrado(-45.3, -7.2))])
    primeiro = _importar(db, "um.geojson", corpo)
    with db.transaction() as con:
        RG.adotar(con, primeiro["geometrias"][1], ocupada, **QUEM)       # a 4020 já tem polígono
    segundo = _importar(db, "dois.geojson", corpo)
    with db.transaction() as con:
        resultado = RG.adotar_sugestoes(con, **QUEM)
    adotadas = set(resultado["adotadas"])
    # das duas sugestões para a 4015 só a primeira (a mais antiga) entra: a segunda já encontra vigente
    assert adotadas == {primeiro["geometrias"][0]}
    assert _linha(db, segundo["geometrias"][0])["situacao"] == RG.PENDENTE
    # a 4020 já tinha polígono: o lote não o troca
    assert _linha(db, segundo["geometrias"][1])["situacao"] == RG.PENDENTE
    assert _linha(db, primeiro["geometrias"][1])["situacao"] == RG.VIGENTE
    assert {d["motivo"] for d in resultado["deixadas"]} == {"a matrícula já tem polígono vigente"}
    assert _linha(db, segundo["geometrias"][2])["situacao"] == RG.PENDENTE and livre   # 4999 não existe: sem sugestão


def test_descartar_exige_motivo_e_o_vigente_nao_se_descarta(db):
    mid = _matricula(db, 4015)
    a, b = _importar(db, "gdal_geo.gpkg")["geometrias"][:2]
    with pytest.raises(RG.GeoImportError):
        with db.transaction() as con:
            RG.descartar(con, a, "  ", quem="Maria Exemplo", agora=AGORA)
    with db.transaction() as con:
        RG.descartar(con, b, "Desenho de outra gleba, não é do imóvel", quem="Maria Exemplo", agora=AGORA)
    linha = _linha(db, b)
    assert linha["situacao"] == RG.DESCARTADA and "outra gleba" in linha["descartada_motivo"]
    with db.transaction() as con:
        RG.adotar(con, a, mid, **QUEM)
    with pytest.raises(RG.GeoImportError):
        with db.transaction() as con:
            RG.descartar(con, a, "Não serve mais para nada", quem="Maria Exemplo", agora=AGORA)
    with pytest.raises(RG.GeoImportError):
        with db.transaction() as con:
            RG.adotar(con, b, mid, **QUEM)             # o descartado não se adota


# ------------------------------------------------------------------ medir e comparar

def test_a_area_geodesica_fica_ao_lado_da_registrada(db):
    mid = _matricula(db, 4015, area_valor="117,2612", area_unidade="ha")
    gid = _importar(db, "gdal_geo.gpkg")["geometrias"][0]
    with db.transaction() as con:
        RG.adotar(con, gid, mid, **QUEM)
    linha = [l for l in RG.lista(db.connect().__enter__()) if l["id"] == gid][0]
    comparacao = RG.comparar_areas(linha)
    assert comparacao["geodesica_ha"] == pytest.approx(117.2612, abs=1e-4)
    assert comparacao["registrada_ha"] == pytest.approx(117.2612, abs=1e-4) and comparacao["bate"] is True
    assert RG.comparar_areas({**linha, "area_valor": "100", "area_unidade": "ha"})["bate"] is False
    assert RG.comparar_areas({**linha, "area_valor": "100", "area_unidade": "ha"})["diferenca_pct"] == pytest.approx(17.261, abs=0.01)
    sem = RG.comparar_areas({**linha, "area_valor": None, "area_unidade": None})
    assert sem["registrada_ha"] is None and sem["bate"] is None


def test_a_divergencia_aceita_e_configuravel():
    linha = {"area_geodesica_m2": 1_050_000.0, "area_valor": "100", "area_unidade": "ha"}
    assert RG.comparar_areas(linha, 1.0)["bate"] is False
    assert RG.comparar_areas(linha, 5.0)["bate"] is True


# ------------------------------------------------------------------ sobreposição

def _vigente(db, numero, anel, **campos):
    mid = _matricula(db, numero, **campos)
    gid = _importar(db, f"m{numero}.geojson", _geojson([({"matricula": str(numero)}, anel)]))["geometrias"][0]
    with db.transaction() as con:
        RG.adotar(con, gid, mid, **QUEM)
    return mid, gid


def test_sobreposicao_mede_a_area_comum_e_o_vizinho_de_aresta_em_comum_nao_conta(db):
    _, a = _vigente(db, 4015, _quadrado(-45.5, -7.2))               # lon -45,500 a -45,490
    _, b = _vigente(db, 4016, _quadrado(-45.495, -7.2))             # lon -45,495 a -45,485: cobre metade da 4015
    _, c = _vigente(db, 4017, _quadrado(-45.485, -7.2))             # lon -45,485 a -45,475: só toca a 4016, na aresta
    with db.connect() as con:
        sobre_a, sobre_b, sobre_c = (RG.sobreposicoes(con, g) for g in (a, b, c))
    assert [s["matricula"] for s in sobre_a] == ["4016"] and [s["matricula"] for s in sobre_b] == ["4015"]
    comum = [(-45.495, -7.2), (-45.49, -7.2), (-45.49, -7.19), (-45.495, -7.19)]
    assert sobre_a[0]["area_m2"] == pytest.approx(G.area_perimetro_do_anel(comum)[0], rel=1e-6)
    assert sobre_a[0]["pct_deste"] == pytest.approx(50.0, abs=0.1) and sobre_a[0]["pct_do_outro"] == pytest.approx(50.0, abs=0.1)
    assert sobre_c == [], "aresta em comum não é sobreposição"


def test_a_tolerancia_de_sobreposicao_e_a_da_casa(db):
    _, a = _vigente(db, 4015, _quadrado(-45.5, -7.2))
    _vigente(db, 4016, _quadrado(-45.4999, -7.2))                   # ~1,1 km de lado: a faixa comum é grande
    with db.connect() as con:
        assert RG.sobreposicoes(con, a)
        assert RG.sobreposicoes(con, a, tolerancia_m2=10**12) == []


def test_vizinhos_com_aresta_em_comum_nao_sao_sobreposicao(db):
    _, a = _vigente(db, 4015, _quadrado(-45.5, -7.2))
    _, b = _vigente(db, 4016, _quadrado(-45.49, -7.2))
    with db.connect() as con:
        assert RG.sobreposicoes(con, a) == [] and RG.sobreposicoes(con, b) == []


# ------------------------------------------------------------------ a conferência antes do arquivo

def _cfg(db, **mudancas):
    cfg = RG.configuracao(db)
    cfg.update(mudancas)
    return cfg


def test_conferencia_deixa_de_fora_a_matricula_encerrada_e_avisa_o_resto(db):
    viva, gv = _vigente(db, 4015, _quadrado(-45.5, -7.2), area_valor="100", area_unidade="ha")
    morta, gm = _vigente(db, 4016, _quadrado(-45.3, -7.2))
    with db.transaction() as con:
        banco(con).escrever("UPDATE ri_matriculas SET encerrada = 1, situacao = 'ENCERRADA' WHERE id = %s", (morta,))
    with db.connect() as con:
        conf = RG.conferir_para_o_mapa(con, _cfg(db))
    por = {i["matricula"]: i for i in conf["itens"]}
    assert por["4015"]["vai"] is True and por["4016"]["vai"] is False
    assert "MATRICULA_FECHADA" in [a["codigo"] for a in por["4016"]["achados"]]
    codigos = {a["codigo"] for a in por["4015"]["achados"]}
    assert {"SEM_DONO", "AREA_NAO_BATE"} <= codigos and "SEM_CNS" not in codigos
    assert conf["vao"] == 1 and conf["ficam"] == 1


def test_conferencia_avisa_sobreposicao_mas_nao_tira_do_arquivo(db):
    _vigente(db, 4015, _quadrado(-45.5, -7.2))
    _vigente(db, 4016, _quadrado(-45.495, -7.2))
    with db.connect() as con:
        conf = RG.conferir_para_o_mapa(con, _cfg(db))
    for item in conf["itens"]:
        assert item["vai"] is True and "SOBREPOSICAO" in [a["codigo"] for a in item["achados"]]


# ------------------------------------------------------------------ o arquivo e a decisão do oficial

def test_sem_a_regra_da_area_escolhida_o_arquivo_nao_se_gera(db):
    _vigente(db, 4015, _quadrado(-45.5, -7.2))
    assert RG.configuracao(db)["regra_da_area"] == ""
    with pytest.raises(RG.GeoImportError) as erro:
        with db.connect() as con:
            RG.gerar_gpkg(con, RG.configuracao(db))
    assert "escolher" in str(erro.value)


@pytest.mark.parametrize("regra, esperado", [
    (RG.REGRA_GEODESICA, 117.2612), (RG.REGRA_REGISTRADA, 99.0), (RG.REGRA_PLUGIN, 99.0)])
def test_area_ha_sai_pela_regra_que_o_oficial_escolheu(db, regra, esperado):
    mid = _matricula(db, 4015, area_valor="99", area_unidade="ha")
    _dono(db, mid)
    gid = _importar(db, "gdal_geo.gpkg")["geometrias"][0]
    with db.transaction() as con:
        RG.adotar(con, gid, mid, **QUEM)
    with db.connect() as con:
        conteudo, conf = RG.gerar_gpkg(con, _cfg(db, regra_da_area=regra))
    (camada,) = F.ler_arquivo("m.gpkg", conteudo)
    (feicao,) = camada["feicoes"]
    assert feicao["atributos"]["AREA_HA"] == pytest.approx(esperado, abs=1e-4)
    assert feicao["atributos"]["MATRICULA"] == "4015" and feicao["atributos"]["PROPRIETAR"] == "FULANO EXEMPLO"
    assert feicao["atributos"]["CNS"] == "000000"


def test_regra_do_plugin_cai_na_geodesica_quando_a_ficha_nao_tem_area(db):
    mid = _matricula(db, 4015)
    gid = _importar(db, "gdal_geo.gpkg")["geometrias"][0]
    with db.transaction() as con:
        RG.adotar(con, gid, mid, **QUEM)
    with db.connect() as con:
        conteudo, _ = RG.gerar_gpkg(con, _cfg(db, regra_da_area=RG.REGRA_PLUGIN))
    assert F.ler_arquivo("m.gpkg", conteudo)[0]["feicoes"][0]["atributos"]["AREA_HA"] == pytest.approx(117.2612, abs=1e-4)
    with db.connect() as con:
        conteudo, _ = RG.gerar_gpkg(con, _cfg(db, regra_da_area=RG.REGRA_REGISTRADA))
    assert F.ler_arquivo("m.gpkg", conteudo)[0]["feicoes"][0]["atributos"]["AREA_HA"] is None


def test_o_shapefile_gerado_leva_os_mesmos_atributos(db):
    mid = _matricula(db, 4015, area_valor="99", area_unidade="ha")
    _dono(db, mid, "JOSÉ EXEMPLO")
    gid = _importar(db, "gdal_geo.gpkg")["geometrias"][0]
    with db.transaction() as con:
        RG.adotar(con, gid, mid, **QUEM)
    with db.connect() as con:
        conteudo, conf, avisos = RG.gerar_shapefile(con, _cfg(db, regra_da_area=RG.REGRA_GEODESICA))
    (camada,) = F.ler_arquivo("m.zip", conteudo)
    assert camada["feicoes"][0]["atributos"] == {"MATRICULA": "4015", "CNS": "000000", "PROPRIETAR": "JOSÉ EXEMPLO",
                                                  "AREA_HA": 117.2612}
    assert avisos == []


def test_so_o_que_vai_entra_no_arquivo_e_sem_nenhum_ele_nao_se_gera(db):
    morta, gid = _vigente(db, 4016, _quadrado(-45.3, -7.2))
    with db.transaction() as con:
        banco(con).escrever("UPDATE ri_matriculas SET encerrada = 1 WHERE id = %s", (morta,))
    with pytest.raises(RG.GeoImportError) as erro:
        with db.connect() as con:
            RG.gerar_gpkg(con, _cfg(db, regra_da_area=RG.REGRA_GEODESICA))
    assert "Nenhum polígono vigente" in str(erro.value)


# ------------------------------------------------------------------ as telas

@pytest.fixture()
def usuarios(cg_casa):
    db = cg_casa["db"]
    db.set_settings({"ri_cns": "000000"})
    for login, papel in (("oficial", "ADMIN"), ("gerente", "MANAGER"), ("balcao", "USER"), ("auditor", "AUDITOR")):
        db.create_user(login, login.upper() + " EXEMPLO", SENHA, papel)
    cliente = {}
    for login in ("oficial", "gerente", "balcao", "auditor"):
        c = cg_casa["app"].test_client()
        cg_login(c, login, SENHA)
        cliente[login] = c
    cg_casa["clientes"] = cliente
    return cg_casa


def _token(c) -> str:
    import re
    html = c.get("/registro-imoveis/mapa").get_data(as_text=True)
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def test_todo_papel_do_ri_ve_a_tela_e_o_anonimo_nao(usuarios):
    assert usuarios["app"].test_client().get("/registro-imoveis/mapa").status_code == 302
    for login, c in usuarios["clientes"].items():
        r = c.get("/registro-imoveis/mapa")
        assert r.status_code == 200, login
        assert "Mapa do ONR — polígonos" in r.get_data(as_text=True)


def test_importar_pela_tela_guarda_pendente_e_a_tela_lista(usuarios):
    c = usuarios["clientes"]["balcao"]
    _matricula(usuarios["db"], 4015)
    r = c.post("/registro-imoveis/mapa/importar", follow_redirects=True, data={
        "csrf_token": _token(c), "levantamento": "ART exemplo", "responsavel_tecnico": "Técnica Exemplo",
        "arquivo": (io.BytesIO((DADOS / "gdal_geo.gpkg").read_bytes()), "gdal_geo.gpkg")},
        content_type="multipart/form-data")
    html = r.get_data(as_text=True)
    assert "polígono(s) guardado(s) como PENDENTES" in html and "Nenhum foi adotado" in html
    assert "Pendentes de adoção" in html and "gdal_geo.gpkg" in html
    with usuarios["db"].connect() as con:
        assert banco(con).um("SELECT count(*) AS n FROM ri_geometrias WHERE situacao='PENDENTE'")["n"] == 2
    log = [l for l in usuarios["db"].list_logs(10) if l["action"] == "RI_GEO_IMPORTADO"]
    assert log and '"poligonos": 2' in log[0]["details"]


def test_importar_arquivo_ruim_diz_o_que_fazer_e_nao_grava(usuarios):
    c = usuarios["clientes"]["balcao"]
    r = c.post("/registro-imoveis/mapa/importar", follow_redirects=True, data={
        "csrf_token": _token(c), "arquivo": (io.BytesIO(b"nada de mapa"), "x.txt")},
        content_type="multipart/form-data")
    assert "Formato não reconhecido" in r.get_data(as_text=True)
    r = c.post("/registro-imoveis/mapa/importar", follow_redirects=True,
               data={"csrf_token": _token(c)}, content_type="multipart/form-data")
    assert "Escolha o arquivo" in r.get_data(as_text=True)


def test_adotar_pela_tela_e_ver_o_poligono(usuarios):
    c = usuarios["clientes"]["gerente"]
    mid = _matricula(usuarios["db"], 4015, area_valor="117,2612", area_unidade="ha")
    gid = _importar(usuarios["db"], "gdal_geo.gpkg")["geometrias"][0]
    r = c.post(f"/registro-imoveis/mapa/{gid}/adotar", follow_redirects=True,
               data={"csrf_token": _token(c), "matricula": "4015"})
    html = r.get_data(as_text=True)
    assert "Polígono adotado para a matrícula 4015" in html and "VIGENTE" in html
    assert "117.2612 ha" in html and "SIRGAS 2000" in html and "<svg" in html
    assert _linha(usuarios["db"], gid)["matricula_id"] == mid
    inexistente = c.post(f"/registro-imoveis/mapa/{gid}/adotar", follow_redirects=True,
                         data={"csrf_token": _token(c), "matricula": "9999"})
    assert "Não achei a matrícula" in inexistente.get_data(as_text=True)
    assert c.get("/registro-imoveis/mapa/999999").status_code == 404


def test_o_auditor_ve_e_nao_grava(usuarios):
    c = usuarios["clientes"]["auditor"]
    r = c.post("/registro-imoveis/mapa/importar", data={"csrf_token": _token(c)}, content_type="multipart/form-data")
    assert r.status_code == 403


def test_so_o_admin_gera_o_arquivo_e_a_baixa_fica_na_auditoria(usuarios):
    db = usuarios["db"]
    mid = _matricula(db, 4015, area_valor="99", area_unidade="ha")
    _dono(db, mid)
    gid = _importar(db, "gdal_geo.gpkg")["geometrias"][0]
    with db.transaction() as con:
        RG.adotar(con, gid, mid, **QUEM)
    for login in ("gerente", "balcao", "auditor"):
        assert usuarios["clientes"][login].get("/registro-imoveis/mapa/mapa_onr.gpkg").status_code == 403, login
        assert usuarios["clientes"][login].get("/registro-imoveis/mapa/mapa_onr_shapefile.zip").status_code == 403
    oficial = usuarios["clientes"]["oficial"]
    # sem a regra escolhida: não gera, e diz por quê
    r = oficial.get("/registro-imoveis/mapa/mapa_onr.gpkg", follow_redirects=True)
    assert "escolher" in r.get_data(as_text=True)
    sem_regra = oficial.post("/registro-imoveis/mapa/regra-da-area", follow_redirects=True,
                             data={"csrf_token": _token(oficial), "regra": "TALVEZ"})
    assert "Escolha uma das três respostas" in sem_regra.get_data(as_text=True)
    oficial.post("/registro-imoveis/mapa/regra-da-area", follow_redirects=True, data={
        "csrf_token": _token(oficial), "regra": "GEODESICA", "tolerancia_fechamento_m": "0,1",
        "tolerancia_sobreposicao_m2": "2", "divergencia_area_pct": "3"})
    cfg = RG.configuracao(db)
    assert cfg["regra_da_area"] == "GEODESICA" and cfg["tolerancia_fechamento_m"] == 0.1
    assert cfg["tolerancia_sobreposicao_m2"] == 2.0 and cfg["divergencia_area_pct"] == 3.0
    gpkg = oficial.get("/registro-imoveis/mapa/mapa_onr.gpkg")
    assert gpkg.status_code == 200 and "attachment" in gpkg.headers["Content-Disposition"]
    (camada,) = F.ler_arquivo("m.gpkg", gpkg.data)
    assert camada["feicoes"][0]["atributos"]["AREA_HA"] == pytest.approx(117.2612, abs=1e-4)
    shp = oficial.get("/registro-imoveis/mapa/mapa_onr_shapefile.zip")
    assert shp.status_code == 200 and shp.mimetype == "application/zip"
    acoes = [l["action"] for l in db.list_logs(20)]
    assert "RI_GEO_EXPORTADO" in acoes and "RI_GEO_REGRA_DA_AREA" in acoes


def test_a_tela_pergunta_a_regra_enquanto_o_oficial_nao_escolhe(usuarios):
    html = usuarios["clientes"]["oficial"].get("/registro-imoveis/mapa").get_data(as_text=True)
    assert "Qual área vai em AREA_HA?" in html and "Ainda não foi escolhida" in html
    assert "valores de trabalho desta casa" in html


def test_descartar_pela_tela(usuarios):
    c = usuarios["clientes"]["balcao"]
    gid = _importar(usuarios["db"], "gdal_geo.gpkg")["geometrias"][0]
    r = c.post(f"/registro-imoveis/mapa/{gid}/descartar", follow_redirects=True,
               data={"csrf_token": _token(c), "motivo": ""})
    assert "motivo do descarte" in r.get_data(as_text=True)
    c.post(f"/registro-imoveis/mapa/{gid}/descartar", follow_redirects=True,
           data={"csrf_token": _token(c), "motivo": "Não é o imóvel da matrícula"})
    assert _linha(usuarios["db"], gid)["situacao"] == RG.DESCARTADA


def test_o_svg_do_mosaico_escapa_o_texto_e_nao_quebra_sem_poligono():
    import ri_geo_web as W
    assert W.svg_do_mosaico([]) == ""
    svg = W.svg_do_mosaico([{"geometria": [[_quadrado(-45.5, -7.2)]], "rotulo": '<script>alert(1)</script>',
                             "href": '/x?a="b"'}])
    assert "<script>" not in svg and "&lt;script&gt;" in svg and svg.startswith("<svg") and svg.endswith("</svg>")
    assert "&quot;" in svg
