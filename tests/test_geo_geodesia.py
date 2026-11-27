"""A geodésia do mapa — `geo_geodesia.py` (RI011, S9).

O QUE ESTES TESTES PROTEGEM
    a área geodésica        a conta do elipsoide GRS 1980: os valores esperados vieram do PROJ e do GeographicLib de
                            referência, rodados na bancada do desenvolvedor (nenhum deles é dependência)
    o UTM                   a inversa da Transversa de Mercator escrita aqui, conferida contra o PROJ em quatro
                            fusos, nos dois hemisférios, a menos de um milímetro
    o fechamento e o laço   o erro de fechamento e o cruzamento próprio viram ERRO; o polígono bom, não
    a sobreposição          por faixas, no plano equivalente: casos em que a resposta é conhecida de cabeça
                            (retângulos, aresta em comum, contido, furo), e a área do plano igual à do elipsoide
    o que se recusa         SAD 69 e Córrego Alegre não se tratam «de cabeça»; WGS 84 entra com aviso

Geometrias FICTÍCIAS, perto de uma latitude qualquer do Nordeste: não representam imóvel nenhum.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

pytest.importorskip("geographiclib")

import geo_geodesia as G

LON, LAT = -45.5, -7.2


def retangulo(dx: float, dy: float, lon: float = LON, lat: float = LAT) -> list:
    return [(lon, lat), (lon + dx, lat), (lon + dx, lat + dy), (lon, lat + dy), (lon, lat)]


# ------------------------------------------------------------------ a área geodésica

def test_a_area_do_retangulo_confere_com_o_valor_de_referencia():
    """0,03° × 0,02° em (-45,5; -7,2): 7.328.905,44 m², do PROJ (Geod, GRS 1980) e do GeographicLib."""
    area, perimetro = G.area_perimetro_do_anel(retangulo(0.03, 0.02))
    assert area == pytest.approx(7328905.4403, abs=0.01)
    assert perimetro == pytest.approx(11050.6625, abs=0.01)


def test_a_area_nao_depende_do_sentido_nem_do_fecho():
    anel = retangulo(0.03, 0.02)
    a1, _ = G.area_perimetro_do_anel(anel)
    a2, _ = G.area_perimetro_do_anel(anel[::-1])
    a3, _ = G.area_perimetro_do_anel(anel[:-1])           # sem repetir o primeiro vértice
    assert a1 == pytest.approx(a2) == pytest.approx(a3)
    assert a1 > 0


def test_o_furo_se_subtrai():
    externo = retangulo(0.01, 0.01)
    furo = retangulo(0.002, 0.002, LON + 0.004, LAT + 0.004)
    cheia, _ = G.area_perimetro([[externo]])
    com_furo, _ = G.area_perimetro([[externo, furo]])
    do_furo, _ = G.area_perimetro_do_anel(furo)
    assert com_furo == pytest.approx(cheia - do_furo)


def test_o_hectare_tem_quatro_casas():
    assert G.hectares(7_328_905.4403) == 732.8905
    assert G.hectares(1.0) == 0.0001           # um metro quadrado é a menor casa do Mapa
    assert G.hectares(0.4) == 0.0


def test_o_plano_equivalente_preserva_a_area_do_elipsoide():
    """A projeção de Lambert sobre o elipsoide é equivalente: a área do plano é a do elipsoide (arestas
    retas vs. geodésicas diferem só na casa de 1e-8)."""
    anel = retangulo(0.03, 0.02)
    plano = G.projetar_aneis([anel])[0]
    soma = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(plano, plano[1:])) / 2
    area, _ = G.area_perimetro_do_anel(anel)
    assert abs(soma) == pytest.approx(area, rel=1e-6)


# ------------------------------------------------------------------ os sistemas de coordenadas

# Pares (EPSG, E, N) -> (lon, lat) calculados pelo PROJ (pyproj 3.8) na bancada; tolerância de 1 mm.
_UTM_DO_PROJ = [
    (31983, 300000.0, 8000000.0),
    (31982, 500000.0, 9000000.0),
    (31976, 700000.0, 500000.0),
    (31984, 250000.0, 9700000.0),
]


@pytest.mark.parametrize("epsg, leste, norte", _UTM_DO_PROJ)
def test_o_utm_cai_onde_o_proj_diz(epsg, leste, norte):
    """A posição que o PROJ calcula para o mesmo ponto, a menos de 1 mm (1e-8 grau)."""
    sistema = G.sistema_do_epsg(epsg)
    (lon, lat), = G.para_sirgas([(leste, norte)], sistema)
    assert -80 < lon < -30 and -35 < lat < 6
    referencia = _REFERENCIA[(epsg, leste, norte)]
    # 1e-8 grau ≈ 1 mm
    assert lon == pytest.approx(referencia[0], abs=1e-8)
    assert lat == pytest.approx(referencia[1], abs=1e-8)


_REFERENCIA = {
    (31983, 300000.0, 8000000.0): (-46.88981066705159, -18.07945474952073),
    (31982, 500000.0, 9000000.0): (-51.00000000000001, -9.046562464063586),
    (31976, 700000.0, 500000.0): (-49.19737305395313, 4.521318308241404),
    (31984, 250000.0, 9700000.0): (-41.24861056639642, -2.7120728681995225),
}


def test_o_epsg_do_sirgas_e_do_utm_sao_reconhecidos():
    assert G.sistema_do_epsg(4674)["tipo"] == "GEOGRAFICO" and G.sistema_do_epsg(4674)["aviso"] is None
    utm = G.sistema_do_epsg(31983)
    assert (utm["tipo"], utm["fuso"], utm["hemisferio"]) == ("UTM", 23, "S")
    assert (G.sistema_do_epsg(31976)["fuso"], G.sistema_do_epsg(31976)["hemisferio"]) == (22, "N")
    assert (G.sistema_do_epsg(31977)["fuso"], G.sistema_do_epsg(31977)["hemisferio"]) == (17, "S")


def test_wgs84_entra_com_aviso():
    assert "WGS 84" in G.sistema_do_epsg(4326)["aviso"]


@pytest.mark.parametrize("epsg", [4618, 4291, 4225, 29193, 22523])
def test_os_datuns_antigos_sao_recusados_e_a_frase_diz_o_que_fazer(epsg):
    with pytest.raises(G.GeoErro) as erro:
        G.sistema_do_epsg(epsg)
    assert "SIRGAS 2000" in str(erro.value) and "QGIS" in str(erro.value)


def test_sem_sistema_ou_desconhecido_e_recusado():
    with pytest.raises(G.GeoErro):
        G.sistema_do_epsg(None)
    with pytest.raises(G.GeoErro):
        G.sistema_do_epsg(99999)


# ------------------------------------------------------------------ fechamento e cruzamento

def test_anel_fechado_tem_fechamento_zero():
    assert G.fechamento_m(retangulo(0.01, 0.01)) == 0.0


def test_o_ultimo_vertice_longe_do_primeiro_e_erro_de_fechamento():
    anel = retangulo(0.01, 0.01)[:-1]          # a linha aberta: o último vértice é o 4º, a ~1,1 km do 1º
    assert G.fechamento_m(anel) > 1000
    achados = G.analisar([[anel]])["achados"]
    assert [a["codigo"] for a in achados if a["nivel"] == G.ERRO] == ["FECHAMENTO"]


def test_o_fechamento_dentro_da_tolerancia_passa_e_fora_nao():
    anel = retangulo(0.01, 0.01)
    anel[-1] = (LON, LAT + 0.0000002)          # ~2 cm
    assert not any(a["codigo"] == "FECHAMENTO" for a in G.analisar([[anel]])["achados"])
    anel[-1] = (LON, LAT + 0.000002)           # ~22 cm
    assert any(a["codigo"] == "FECHAMENTO" for a in G.analisar([[anel]])["achados"])
    assert not any(a["codigo"] == "FECHAMENTO"
                   for a in G.analisar([[anel]], tolerancia_fechamento_m=1.0)["achados"])


def test_o_laco_em_oito_se_cruza():
    laco = [(LON, LAT), (LON + 0.001, LAT + 0.001), (LON + 0.001, LAT), (LON, LAT + 0.001), (LON, LAT)]
    assert G.tem_autointerseccao(laco) == 1
    assert "AUTOINTERSECCAO" in [a["codigo"] for a in G.analisar([[laco]])["achados"]]


def test_o_poligono_bom_nao_se_cruza_nem_tem_erro():
    achados = G.analisar([[retangulo(0.01, 0.01)]])["achados"]
    assert [a for a in achados if a["nivel"] == G.ERRO] == []
    # o L, côncavo, também é bom
    ele = [(0, 0), (3, 0), (3, 1), (1, 1), (1, 3), (0, 3), (0, 0)]
    ele = [(LON + x * 0.001, LAT + y * 0.001) for x, y in ele]
    assert G.tem_autointerseccao(ele) == 0


def test_poucos_vertices_e_geometria_vazia():
    assert G.analisar([[[(LON, LAT), (LON + 1e-4, LAT), (LON, LAT)]]])["achados"][0]["codigo"] == "POUCOS_VERTICES"
    assert G.analisar([])["achados"][0]["codigo"] == "VAZIA"


def test_coordenada_fora_do_brasil_avisa_e_nao_e_erro():
    """Latitude e longitude trocadas é o erro mais comum de quem monta o arquivo à mão."""
    trocado = [(y, x) for x, y in retangulo(0.01, 0.01)]
    achados = G.analisar([[trocado]])["achados"]
    fora = [a for a in achados if a["codigo"] == "FORA_DO_BRASIL"]
    assert fora and fora[0]["nivel"] == G.AVISO


# ------------------------------------------------------------------ a sobreposição

def inter(a, b):
    return G.area_da_interseccao_m2([[a]], [[b]])


def test_dois_retangulos_que_se_cobrem_pela_metade():
    a = retangulo(0.02, 0.01)
    b = retangulo(0.02, 0.01, LON + 0.01)
    esperado, _ = G.area_perimetro_do_anel(retangulo(0.01, 0.01, LON + 0.01))
    assert inter(a, b) == pytest.approx(esperado, rel=1e-6)


def test_vizinhos_com_aresta_em_comum_nao_se_sobrepoem():
    assert inter(retangulo(0.01, 0.01), retangulo(0.01, 0.01, LON + 0.01)) == pytest.approx(0.0, abs=1e-6)


def test_vizinhos_que_so_se_tocam_no_vertice_nao_se_sobrepoem():
    assert inter(retangulo(0.01, 0.01), retangulo(0.01, 0.01, LON + 0.01, LAT + 0.01)) == pytest.approx(0.0, abs=1e-6)


def test_o_contido_sobrepoe_a_area_inteira_dele():
    grande, pequeno = retangulo(0.01, 0.01), retangulo(0.002, 0.002, LON + 0.004, LAT + 0.004)
    esperado, _ = G.area_perimetro_do_anel(pequeno)
    assert inter(grande, pequeno) == pytest.approx(esperado, rel=1e-6)
    assert inter(pequeno, grande) == pytest.approx(esperado, rel=1e-6)      # e a ordem não importa


def test_o_que_cai_dentro_do_furo_nao_se_sobrepoe():
    externo = retangulo(0.01, 0.01)
    furo = retangulo(0.004, 0.004, LON + 0.003, LAT + 0.003)
    dentro = retangulo(0.001, 0.001, LON + 0.0045, LAT + 0.0045)
    assert G.area_da_interseccao_m2([[externo, furo]], [[dentro]]) == pytest.approx(0.0, abs=1e-6)
    assert G.area_da_interseccao_m2([[externo, furo]], [[retangulo(0.01, 0.01)]]) > 0


def test_poligonos_longe_um_do_outro():
    assert inter(retangulo(0.01, 0.01), retangulo(0.01, 0.01, LON + 1, LAT + 1)) == 0.0


def test_o_triangulo_e_o_quadrado_em_diagonal():
    """O quadrado de lado L cortado ao meio pela diagonal: metade da área."""
    quadrado = retangulo(0.01, 0.01)
    triangulo = [(LON, LAT), (LON + 0.01, LAT), (LON, LAT + 0.01), (LON, LAT)]
    a_quadrado, _ = G.area_perimetro_do_anel(quadrado)
    # no plano equivalente a «metade» é a do plano: a diferença para a geodésica é da ordem de 1e-8
    assert inter(quadrado, triangulo) == pytest.approx(a_quadrado / 2, rel=1e-4)


def test_par_grande_demais_devolve_none_e_nao_trava(monkeypatch):
    monkeypatch.setattr(G, "TETO_DE_ARESTAS_NA_SOBREPOSICAO", 3)
    assert inter(retangulo(0.01, 0.01), retangulo(0.01, 0.01)) is None


def test_a_caixa_da_geometria():
    assert G.caixa([[retangulo(0.01, 0.01)]]) == (LON, LAT, LON + 0.01, LAT + 0.01)
    with pytest.raises(G.GeoErro):
        G.caixa([])


def test_sem_a_biblioteca_a_frase_diz_o_que_instalar(monkeypatch):
    import builtins
    real = builtins.__import__

    def sem_geographiclib(nome, *a, **k):
        if nome.startswith("geographiclib"):
            raise ImportError(nome)
        return real(nome, *a, **k)

    monkeypatch.setattr(builtins, "__import__", sem_geographiclib)
    assert G.biblioteca_disponivel() is False
    with pytest.raises(G.GeographicLibFaltando) as erro:
        G.area_perimetro_do_anel(retangulo(0.01, 0.01))
    assert "requirements.txt" in str(erro.value)
