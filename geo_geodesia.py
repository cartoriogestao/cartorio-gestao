"""A GEODÉSIA DO MAPA — área no elipsoide, fechamento, autointerseção e sobreposição. SÓ CALCULA.

    «III – o cálculo de fechamento de polígonos para verificação de possíveis erros em trabalhos
     técnicos; [...] VII – a análise e identificação de divergências [...] emitindo relatório de
     sobreposição ou de lacunas entre imóveis»
    (CNN, art. 343-E, III e VII, incluídos pelo Provimento CN n. 195/2025)

O QUE ESTE MÓDULO É
    As contas da tela do mapa (`ri_geo.py`), sem banco e sem Flask: quem chama passa coordenadas e recebe
    números. Por isso se testa contra um oráculo externo (PROJ e GEOS, na bancada do desenvolvedor — nunca
    em produção) e roda em qualquer máquina da casa.

UMA DEPENDÊNCIA SÓ: `geographiclib` (Charles Karney, licença MIT)
    Pura em Python, roda sem compilar em qualquer sistema (a roda é `py3-none-any`; 390 KB). É dela a conta que o QGIS
    faz (`QgsDistanceArea` usa o mesmo GeographicLib): a área de polígono de arestas geodésicas no
    elipsoide. Importada **na hora do uso**: sem ela a tela diz o que instalar, e o resto do sistema segue.
    O que NÃO se usou, e por quê: GDAL/Fiona/PyProj (rodas nativas de dezenas de MB, e o servidor Windows
    teria de compilar ou baixar binário), Shapely (GEOS nativo). A sobreposição é conta de plano e está
    escrita aqui, conferida contra o Shapely nos testes de bancada.

O DATUM É O SIRGAS 2000 (GRS 1980: a = 6.378.137 m, 1/f = 298,257222101)
    A área «geodésica» do ONR é a do elipsoide do projeto (docs/MAPA_ONR.md); o do projeto, no Brasil, é este.
    Aceitam-se coordenadas em SIRGAS 2000 geográficas (EPSG:4674) e em UTM SIRGAS 2000 (EPSG:31965 a 31985);
    WGS 84 (EPSG:4326, o GeoJSON) entra **com aviso** — a diferença para o SIRGAS 2000 é de ordem do
    decímetro ao metro, e quem a medir bem deve converter no QGIS. **SAD 69, Córrego Alegre e SIRGAS
    antigo NÃO entram**: a transformação precisa de parâmetros e grades que esta casa não tem, e
    transformar «de cabeça» é inventar posição. A recusa diz o que fazer.

SOBREPOSIÇÃO — POR FAIXAS, NO PLANO EQUIVALENTE
    As contas de intersecção se fazem na projeção cilíndrica equivalente de Lambert sobre o elipsoide
    (`x = a·λ`, `y = a·q/2`): ela **preserva área exatamente**, e por isso a área da sobreposição sai em
    m² certos, sem escolher fuso. As arestas viram retas no plano, e não geodésicas: para imóveis (arestas
    de metros a poucos quilômetros) a diferença é de milímetros e fica abaixo de qualquer tolerância
    prática. A conta é por faixas verticais entre as abscissas notáveis — dentro de cada faixa as arestas
    não se cruzam, o comprimento da seção é linear e a regra do ponto médio é **exata**. Aresta em comum,
    vértice tocando aresta e polígono dentro de furo dão área zero ou certa, sem caso especial.

TOLERÂNCIAS SÃO DESTA CASA
    Os limites de fechamento e de sobreposição abaixo são **valores de trabalho**, e não os do ONR: o
    art. 343-D, § 2º, V, remete as tolerâncias posicionais ao manual técnico do ONR (art. 320-O, § 1º), que
    a casa não tem. Quem chama pode trocá-los; a tela os mostra.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

# --------------------------------------------------------------- o elipsoide

#: GRS 1980, o elipsoide do SIRGAS 2000.
GRS80_A = 6378137.0
GRS80_F = 1.0 / 298.257222101
_E2 = GRS80_F * (2.0 - GRS80_F)
_E = math.sqrt(_E2)

#: Valores de trabalho (ver o cabeçalho): a ponta do anel que não fecha, e a sobreposição que importa.
TOLERANCIA_FECHAMENTO_M = 0.05
TOLERANCIA_SOBREPOSICAO_M2 = 1.0

#: Um polígono de poucos vértices ou arestas de zero metro não é imóvel.
MIN_VERTICES = 3

#: Quadro em que o Brasil cabe (com folga: ilhas oceânicas incluídas). Fora dele, o mais provável é
#: latitude e longitude trocadas, ou coordenada projetada lida como se fosse grau.
BRASIL = (-75.0, -34.5, -28.0, 6.0)  # lon_min, lat_min, lon_max, lat_max

#: Teto do produto de arestas para a sobreposição por faixas: acima, a tela diz que não conferiu.
TETO_DE_ARESTAS_NA_SOBREPOSICAO = 40_000_000

Ponto = tuple  # (lon, lat) em graus
Anel = list
Poligono = list  # [anel externo, furo, furo...]
Geometria = list  # [poligono, poligono...]


class GeoErro(ValueError):
    """Coordenada ou sistema que o sistema não sabe tratar — a frase diz o que fazer."""


class GeographicLibFaltando(GeoErro):
    """A biblioteca de geodésia não está instalada nesta máquina."""

    def __init__(self) -> None:
        super().__init__(
            "A biblioteca «geographiclib» não está instalada nesta máquina. Ela vem no pacote do sistema "
            "(requirements.txt); numa instalação antiga, rode «pip install -r requirements.txt» no Python do "
            "sistema, ou aplique a atualização completa.")


def _geodesic():
    try:
        from geographiclib.geodesic import Geodesic
    except ImportError as erro:  # pragma: no cover - depende da instalação
        raise GeographicLibFaltando() from erro
    return Geodesic(GRS80_A, GRS80_F)


def biblioteca_disponivel() -> bool:
    """A conta de área pode ser feita nesta máquina? Só tenta importar."""
    try:
        _geodesic()
    except GeographicLibFaltando:
        return False
    return True


# --------------------------------------------------------------- sistemas de coordenadas

#: EPSG → (hemisfério, fuso) do UTM SIRGAS 2000. 31965–31976: 11N a 22N; 31977–31985: 17S a 25S
#: (conferido contra o registro EPSG pelo PROJ na bancada).
_UTM = {**{31965 + i: ("N", 11 + i) for i in range(12)}, **{31977 + i: ("S", 17 + i) for i in range(9)}}

#: Datuns que o Brasil já usou e que **não** se tratam aqui.
_RECUSADOS = {
    4618: "SAD 69", 4291: "SAD 69 (1996 não: SAD 69 antigo)", 4225: "Córrego Alegre 1970-72",
    4224: "Chuá", 4189: "REGVEN", 29168: "SAD 69 / UTM 18N", 29169: "SAD 69 / UTM 19N",
    29170: "SAD 69 / UTM 20N", 29171: "SAD 69 / UTM 21N", 29172: "SAD 69 / UTM 22N",
    29173: "SAD 69 / UTM 23N", 29174: "SAD 69 / UTM 24N", 29175: "SAD 69 / UTM 25N",
    29188: "SAD 69 / UTM 18S", 29189: "SAD 69 / UTM 19S", 29190: "SAD 69 / UTM 20S",
    29191: "SAD 69 / UTM 21S", 29192: "SAD 69 / UTM 22S", 29193: "SAD 69 / UTM 23S",
    29194: "SAD 69 / UTM 24S", 29195: "SAD 69 / UTM 25S", 22521: "Córrego Alegre / UTM 21S",
    22522: "Córrego Alegre / UTM 22S", 22523: "Córrego Alegre / UTM 23S",
    22524: "Córrego Alegre / UTM 24S", 22525: "Córrego Alegre / UTM 25S",
}


def sistema_do_epsg(epsg: int | None) -> dict:
    """`{epsg, tipo, [hemisferio, fuso], aviso}` do sistema de coordenadas, ou `GeoErro` dizendo o que fazer.

    `tipo`: GEOGRAFICO (graus) ou UTM (metros). `aviso` só vem para o WGS 84.
    """
    if epsg is None:
        raise GeoErro("O arquivo não diz em que sistema de coordenadas está. Salve-o no QGIS com o sistema "
                      "«SIRGAS 2000» (EPSG:4674) e importe de novo.")
    epsg = int(epsg)
    if epsg == 4674:
        return {"epsg": 4674, "tipo": "GEOGRAFICO", "aviso": None}
    if epsg == 4326:
        return {"epsg": 4326, "tipo": "GEOGRAFICO",
                "aviso": "As coordenadas estão em WGS 84 (EPSG:4326) e foram tratadas como SIRGAS 2000: a "
                         "diferença entre os dois é da ordem do decímetro ao metro. Para a área do Mapa do ONR, "
                         "converta no QGIS para SIRGAS 2000 (EPSG:4674)."}
    if epsg in _UTM:
        hemisferio, fuso = _UTM[epsg]
        return {"epsg": epsg, "tipo": "UTM", "hemisferio": hemisferio, "fuso": fuso, "aviso": None}
    if epsg in _RECUSADOS:
        raise GeoErro(f"O arquivo está em {_RECUSADOS[epsg]} (EPSG:{epsg}), um sistema antigo: a passagem para "
                      f"SIRGAS 2000 depende de parâmetros que este sistema não tem, e não vamos adivinhar a "
                      f"posição do imóvel. Converta no QGIS para SIRGAS 2000 (EPSG:4674) e importe de novo.")
    raise GeoErro(f"Sistema de coordenadas EPSG:{epsg} não reconhecido. Aceitam-se SIRGAS 2000 (EPSG:4674), "
                  f"SIRGAS 2000 UTM (EPSG:31965 a 31985) e, com aviso, WGS 84 (EPSG:4326). Converta no QGIS e "
                  f"importe de novo.")


# Série de Krüger (Karney, 2011), até a sexta ordem em n = f/(2-f): a inversa da Transversa de Mercator,
# com erro de nanômetros dentro do fuso. Escrita aqui porque o `geographiclib` de Python não a traz.
_N = GRS80_F / (2.0 - GRS80_F)
_A_RETIFICADO = GRS80_A / (1.0 + _N) * (1.0 + _N**2 / 4.0 + _N**4 / 64.0 + _N**6 / 256.0)
_BETA = (
    _N / 2 - 2 * _N**2 / 3 + 37 * _N**3 / 96 - _N**4 / 360 - 81 * _N**5 / 512 + 96199 * _N**6 / 604800,
    _N**2 / 48 + _N**3 / 15 - 437 * _N**4 / 1440 + 46 * _N**5 / 105 - 1118711 * _N**6 / 3870720,
    17 * _N**3 / 480 - 37 * _N**4 / 840 - 209 * _N**5 / 4480 + 5569 * _N**6 / 90720,
    4397 * _N**4 / 161280 - 11 * _N**5 / 504 - 830251 * _N**6 / 7257600,
    4583 * _N**5 / 161280 - 108847 * _N**6 / 3991680,
    20648693 * _N**6 / 638668800,
)
_DELTA = (
    2 * _N - 2 * _N**2 / 3 - 2 * _N**3 + 116 * _N**4 / 45 + 26 * _N**5 / 45 - 2854 * _N**6 / 675,
    7 * _N**2 / 3 - 8 * _N**3 / 5 - 227 * _N**4 / 45 + 2704 * _N**5 / 315 + 2323 * _N**6 / 945,
    56 * _N**3 / 15 - 136 * _N**4 / 35 - 1262 * _N**5 / 105 + 73814 * _N**6 / 2835,
    4279 * _N**4 / 630 - 332 * _N**5 / 35 - 399572 * _N**6 / 14175,
    4174 * _N**5 / 315 - 144838 * _N**6 / 6237,
    601676 * _N**6 / 22275,
)
_K0_UTM = 0.9996


def _utm_para_geografico(leste: float, norte: float, fuso: int, hemisferio: str) -> Ponto:
    """UTM SIRGAS 2000 → `(lon, lat)` em graus."""
    x = leste - 500_000.0
    y = norte - (10_000_000.0 if hemisferio == "S" else 0.0)
    xi0, eta0 = y / (_K0_UTM * _A_RETIFICADO), x / (_K0_UTM * _A_RETIFICADO)
    xi, eta = xi0, eta0
    for j, beta in enumerate(_BETA, start=1):
        xi -= beta * math.sin(2 * j * xi0) * math.cosh(2 * j * eta0)
        eta -= beta * math.cos(2 * j * xi0) * math.sinh(2 * j * eta0)
    chi = math.asin(math.sin(xi) / math.cosh(eta))
    lat = chi + sum(d * math.sin(2 * j * chi) for j, d in enumerate(_DELTA, start=1))
    dlon = math.atan2(math.sinh(eta), math.cos(xi))
    return (-183.0 + 6.0 * fuso + math.degrees(dlon), math.degrees(lat))


def para_sirgas(pontos: Iterable[Sequence[float]], sistema: dict) -> list[Ponto]:
    """Leva `(x, y)` do sistema ao par `(lon, lat)` em graus."""
    if sistema["tipo"] == "GEOGRAFICO":
        return [(float(p[0]), float(p[1])) for p in pontos]
    return [_utm_para_geografico(float(p[0]), float(p[1]), sistema["fuso"], sistema["hemisferio"])
            for p in pontos]


# --------------------------------------------------------------- graus, minutos e segundos

def dms_para_graus(graus: float, minutos: float, segundos: float, *, negativo: bool = False) -> float:
    """Graus, minutos e segundos em graus decimais. `GeoErro` se minuto ou segundo passam de 59,999….

    O sinal vem à parte (`negativo`) porque «-00°30'00"» é meio grau ao sul, e o `-0` do número perderia o sinal.
    """
    if not (0 <= minutos < 60 and 0 <= segundos < 60 and graus >= 0):
        raise GeoErro(f"Coordenada que não existe: {graus:g}° {minutos:g}' {segundos:g}\".")
    valor = float(graus) + float(minutos) / 60.0 + float(segundos) / 3600.0
    return -valor if negativo else valor


# --------------------------------------------------------------- distância e área geodésicas

def distancia_m(a: Ponto, b: Ponto) -> float:
    """Distância geodésica no elipsoide, em metros."""
    return float(_geodesic().Inverse(a[1], a[0], b[1], b[0])["s12"])


def area_perimetro_do_anel(anel: Sequence[Ponto]) -> tuple[float, float]:
    """`(área em m², perímetro em m)` de UM anel, de arestas geodésicas. A área é sempre positiva.

    O anel pode vir fechado (último = primeiro) ou aberto — o GeographicLib fecha sozinho.
    """
    pontos = _sem_o_fecho(anel)
    if len(pontos) < 3:
        return 0.0, 0.0
    poligono = _geodesic().Polygon(False)
    for lon, lat in pontos:
        poligono.AddPoint(lat, lon)
    _, perimetro, area = poligono.Compute(False, True)
    return abs(float(area)), float(perimetro)


def area_perimetro(geometria: Geometria) -> tuple[float, float]:
    """`(área em m², perímetro em m)` da geometria: o externo menos os furos, somado por polígono."""
    area = perimetro = 0.0
    for poligono in geometria:
        for i, anel in enumerate(poligono):
            a, p = area_perimetro_do_anel(anel)
            area += a if i == 0 else -a
            perimetro += p
    return area, perimetro


def hectares(metros_quadrados: float) -> float:
    """Metros quadrados em hectares, com as quatro casas do Mapa (1 m² = 0,0001 ha)."""
    return round(metros_quadrados / 10_000.0, 4)


def _sem_o_fecho(anel: Sequence[Ponto]) -> list[Ponto]:
    pontos = [(float(p[0]), float(p[1])) for p in anel]
    if len(pontos) > 1 and pontos[0] == pontos[-1]:
        pontos.pop()
    return pontos


def fechamento_m(anel: Sequence[Ponto]) -> float:
    """A distância entre o primeiro e o último vértice, em metros: o erro de fechamento do anel.

    Anel que repete o primeiro vértice no fim fecha com 0. Anel de um ponto só, ou vazio, devolve 0 — o que
    há de errado nele é outra pergunta (`analisar`).
    """
    if len(anel) < 2:
        return 0.0
    return distancia_m((anel[0][0], anel[0][1]), (anel[-1][0], anel[-1][1]))


# --------------------------------------------------------------- o plano equivalente

def _q(seno: float) -> float:
    return (1.0 - _E2) * (seno / (1.0 - _E2 * seno * seno)
                          - (1.0 / (2.0 * _E)) * math.log((1.0 - _E * seno) / (1.0 + _E * seno)))


def projetar(ponto: Ponto) -> tuple[float, float]:
    """`(lon, lat)` em graus → `(x, y)` em metros na cilíndrica equivalente de Lambert sobre o GRS 1980."""
    return (GRS80_A * math.radians(ponto[0]), GRS80_A * _q(math.sin(math.radians(ponto[1]))) / 2.0)


def projetar_aneis(aneis: Iterable[Sequence[Ponto]]) -> list[list[tuple[float, float]]]:
    return [[projetar(p) for p in anel] for anel in aneis]


def _arestas(aneis: Iterable[Sequence[tuple[float, float]]]) -> list[tuple[float, float, float, float]]:
    """As arestas de cada anel, fechando-o. Aresta de comprimento zero fica de fora."""
    saida = []
    for anel in aneis:
        pontos = list(anel)
        if len(pontos) > 1 and pontos[0] == pontos[-1]:
            pontos.pop()
        n = len(pontos)
        for i in range(n):
            (x1, y1), (x2, y2) = pontos[i], pontos[(i + 1) % n]
            if x1 != x2 or y1 != y2:
                saida.append((x1, y1, x2, y2))
    return saida


def _cruza(a, b):
    """O ponto onde as arestas `a` e `b` se cruzam de verdade (nas duas, no interior ou na ponta), ou `None`.

    Paralelas e colineares não cruzam: a sobreposição colinear já é coberta pelos vértices como abscissas.
    """
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    dx1, dy1, dx2, dy2 = ax2 - ax1, ay2 - ay1, bx2 - bx1, by2 - by1
    den = dx1 * dy2 - dy1 * dx2
    if den == 0.0:
        return None
    t = ((bx1 - ax1) * dy2 - (by1 - ay1) * dx2) / den
    u = ((bx1 - ax1) * dy1 - (by1 - ay1) * dx1) / den
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return ax1 + t * dx1, ay1 + t * dy1, t, u
    return None


def tem_autointerseccao(anel: Sequence[Ponto]) -> int:
    """Quantos cruzamentos próprios o anel tem (arestas que não se encontram só na ponta comum). 0 é válido.

    Feito no plano equivalente, com varredura por abscissa: custa pouco mesmo com milhares de vértices.
    """
    plano = [(x, y) for x, y in (projetar(p) for p in _sem_o_fecho(anel))]
    n = len(plano)
    if n < 4:
        return 0
    arestas = []
    for i in range(n):
        (x1, y1), (x2, y2) = plano[i], plano[(i + 1) % n]
        arestas.append((min(x1, x2), max(x1, x2), i, (x1, y1, x2, y2)))
    arestas.sort(key=lambda e: e[0])
    cruzamentos = 0
    for i, (min_i, max_i, idx_i, seg_i) in enumerate(arestas):
        for min_j, max_j, idx_j, seg_j in arestas[i + 1:]:
            if min_j > max_i:
                break
            vizinhas = (abs(idx_i - idx_j) == 1) or (abs(idx_i - idx_j) == n - 1)
            achado = _cruza(seg_i, seg_j)
            if achado is None:
                continue
            _, _, t, u = achado
            if vizinhas:
                # as vizinhas se encontram na ponta comum; só conta se também se encontram em outro lugar
                # (colineares sobrepostas dão `den == 0` e já saíram acima)
                ponta_comum = (min(abs(t), abs(t - 1.0)) < 1e-9) and (min(abs(u), abs(u - 1.0)) < 1e-9)
                if ponta_comum:
                    continue
            cruzamentos += 1
    return cruzamentos


def _y_em(aresta, x):
    x1, y1, x2, y2 = aresta
    return y1 + (y2 - y1) * (x - x1) / (x2 - x1)


def _intervalos(arestas, x):
    """Os trechos de y dentro da figura na vertical `x`: regra par-ímpar (furos entram sozinhos)."""
    ys = sorted(_y_em(a, x) for a in arestas
                if a[0] != a[2] and min(a[0], a[2]) < x < max(a[0], a[2]))
    return [(ys[i], ys[i + 1]) for i in range(0, len(ys) - 1, 2)]


def area_da_interseccao_m2(geometria_a: Geometria, geometria_b: Geometria) -> float | None:
    """A área, em m², do que as duas geometrias têm em comum. `None` se o par é grande demais para conferir.

    Cada geometria é lida com a regra par-ímpar sobre TODOS os seus anéis (externo e furos de todos os
    polígonos). Pressupõe geometrias válidas (sem cruzamento próprio); a tela confere isso antes.
    """
    aneis_a = projetar_aneis(a for poligono in geometria_a for a in poligono)
    aneis_b = projetar_aneis(a for poligono in geometria_b for a in poligono)
    ea, eb = _arestas(aneis_a), _arestas(aneis_b)
    if not ea or not eb:
        return 0.0
    if len(ea) * len(eb) > TETO_DE_ARESTAS_NA_SOBREPOSICAO:
        return None
    xs_a = [x for e in ea for x in (e[0], e[2])]
    xs_b = [x for e in eb for x in (e[0], e[2])]
    esquerda, direita = max(min(xs_a), min(xs_b)), min(max(xs_a), max(xs_b))
    if esquerda >= direita:
        return 0.0
    ymin_a, ymax_a = min(y for e in ea for y in (e[1], e[3])), max(y for e in ea for y in (e[1], e[3]))
    ymin_b, ymax_b = min(y for e in eb for y in (e[1], e[3])), max(y for e in eb for y in (e[1], e[3]))
    if max(ymin_a, ymin_b) >= min(ymax_a, ymax_b):
        return 0.0
    abscissas = {x for x in xs_a + xs_b if esquerda <= x <= direita}
    abscissas.update((esquerda, direita))
    # os cruzamentos entre as bordas das duas figuras também quebram as faixas
    caixa_b = [(min(e[0], e[2]), max(e[0], e[2]), min(e[1], e[3]), max(e[1], e[3]), e) for e in eb]
    for a in ea:
        amin, amax = min(a[0], a[2]), max(a[0], a[2])
        if amax < esquerda or amin > direita:
            continue
        bmin_y, bmax_y = min(a[1], a[3]), max(a[1], a[3])
        for bmin, bmax, cmin, cmax, b in caixa_b:
            if bmax < amin or bmin > amax or cmax < bmin_y or cmin > bmax_y:
                continue
            achado = _cruza(a, b)
            if achado is not None and esquerda <= achado[0] <= direita:
                abscissas.add(achado[0])
    ordenadas = sorted(abscissas)
    total = 0.0
    for x0, x1 in zip(ordenadas, ordenadas[1:]):
        largura = x1 - x0
        if largura <= 1e-9:
            continue
        meio = (x0 + x1) / 2.0
        ia, ib = _intervalos(ea, meio), _intervalos(eb, meio)
        comprimento = 0.0
        for a0, a1 in ia:
            for b0, b1 in ib:
                comprimento += max(0.0, min(a1, b1) - max(a0, b0))
        total += comprimento * largura
    return total


def caixa(geometria: Geometria) -> tuple[float, float, float, float]:
    """`(lon_min, lat_min, lon_max, lat_max)` da geometria."""
    pontos = [p for poligono in geometria for anel in poligono for p in anel]
    if not pontos:
        raise GeoErro("Geometria sem vértices.")
    return (min(p[0] for p in pontos), min(p[1] for p in pontos),
            max(p[0] for p in pontos), max(p[1] for p in pontos))


# --------------------------------------------------------------- a análise de uma geometria

ERRO, AVISO = "ERRO", "AVISO"


def analisar(geometria: Geometria, *, tolerancia_fechamento_m: float = TOLERANCIA_FECHAMENTO_M) -> dict:
    """Tudo o que se mede de uma geometria, e os achados que o oficial lê.

    Devolve `{area_m2, area_ha, perimetro_m, vertices, aneis, fechamento_m, caixa, achados}`, com `achados`
    uma lista de `{codigo, nivel, texto}`. **ERRO** é o que impede o arquivo de ir ao Mapa (geometria que não
    é um polígono); **AVISO** é o que a pessoa lê e decide.
    """
    achados: list[dict] = []

    def achar(codigo: str, nivel: str, texto: str) -> None:
        achados.append({"codigo": codigo, "nivel": nivel, "texto": texto})

    if not geometria or not any(poligono for poligono in geometria):
        achar("VAZIA", ERRO, "A geometria não tem polígono.")
        return {"area_m2": 0.0, "area_ha": 0.0, "perimetro_m": 0.0, "vertices": 0, "aneis": 0,
                "fechamento_m": 0.0, "caixa": None, "achados": achados}
    vertices = aneis = 0
    pior_fechamento = 0.0
    for numero_do_poligono, poligono in enumerate(geometria, start=1):
        for numero_do_anel, anel in enumerate(poligono, start=1):
            aneis += 1
            onde = (f"polígono {numero_do_poligono}, " if len(geometria) > 1 else "") + \
                   ("anel externo" if numero_do_anel == 1 else f"furo {numero_do_anel - 1}")
            distintos = _sem_o_fecho(anel)
            vertices += len(distintos)
            if len(set(distintos)) < MIN_VERTICES:
                achar("POUCOS_VERTICES", ERRO, f"O {onde} tem menos de {MIN_VERTICES} vértices distintos.")
                continue
            if len(distintos) != len(set(distintos)):
                achar("VERTICE_REPETIDO", AVISO, f"O {onde} repete vértice (fora o que fecha o anel).")
            gap = fechamento_m(anel) if len(anel) > 1 else 0.0
            pior_fechamento = max(pior_fechamento, gap)
            if gap > tolerancia_fechamento_m:
                achar("FECHAMENTO", ERRO,
                      f"Erro de fechamento no {onde}: o último vértice fica a {gap:,.3f} m do primeiro "
                      f"(tolerância de trabalho: {tolerancia_fechamento_m:g} m).".replace(",", "."))
            cruzamentos = tem_autointerseccao(anel)
            if cruzamentos:
                achar("AUTOINTERSECCAO", ERRO,
                      f"O {onde} se cruza ({cruzamentos} cruzamento(s)): as arestas atravessam umas às outras.")
    area, perimetro = area_perimetro(geometria)
    if area <= 0.0 and not any(a["codigo"] == "POUCOS_VERTICES" for a in achados):
        achar("AREA_ZERO", ERRO, "A área do polígono é zero ou negativa.")
    limites = caixa(geometria)
    if (limites[0] < BRASIL[0] or limites[2] > BRASIL[2] or limites[1] < BRASIL[1] or limites[3] > BRASIL[3]):
        achar("FORA_DO_BRASIL", AVISO,
              "Há coordenadas fora do quadro do Brasil: confira se latitude e longitude não estão trocadas e "
              "se o sistema de coordenadas do arquivo é o declarado.")
    return {"area_m2": area, "area_ha": hectares(area), "perimetro_m": perimetro, "vertices": vertices,
            "aneis": aneis, "fechamento_m": pior_fechamento, "caixa": limites, "achados": achados}
