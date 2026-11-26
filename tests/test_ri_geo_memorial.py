"""O memorial da matrícula vira polígono PENDENTE — `geo_formatos.ler_memorial` e `ri_geo.extrair_memorial`.

O QUE ESTES TESTES PROTEGEM

    ler o texto          vértices na ordem do texto, com nome, sinal, vírgula ou ponto, com e sem entidades HTML,
                         hemisfério em letra ou por extenso, rodapé de página no meio da coordenada
    SIRGAS 2000          texto que diz SAD 69 ou Córrego Alegre é RECUSADO, com o motivo, e nada é gravado
    guardar com origem   PENDENTE, «memorial da matrícula N», texto-fonte e vértices como vieram; a matrícula só SUGERIDA
    uma gleba, um anel   várias glebas no texto = um polígono por gleba, marcado «conferir»; vértices de glebas
                         diferentes NUNCA entram no mesmo anel
    não some em silêncio coordenada que não se lê e hemisfério que falta viram ERRO (não se adota)
    adoção é da pessoa   o lote só leva o memorial SEM nenhum aviso; o lote antigo (sugestão de arquivo) não o leva

O texto é INVENTADO (o prefixo dos vértices, os números, o lugar perto de uma latitude do Nordeste); nenhum dado de
matrícula real. Nada aqui fala com o SIGEF nem com o ONR.
"""
from __future__ import annotations

import json
import re
import sys
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
AGORA = "2026-11-26T10:00:00"
QUEM = {"quem": "Maria Exemplo", "quem_id": 7, "agora": AGORA}
SIRGAS = "As coordenadas estão referenciadas ao Sistema Geodésico Brasileiro, SIRGAS 2000."


# ------------------------------------------------------------------ o texto de mentira

def _dms(graus: float, *, eh_lat: bool = False, escapar: bool = True, virgula: bool = True, sinal: bool = True,
         letra: str | None = None) -> str:
    """`-45°30'00,000"` a partir de graus decimais (múltiplos exatos de 1/3600 de grau)."""
    segundos = round(abs(graus) * 3600, 3)
    g, resto = divmod(segundos, 3600)
    m, s = divmod(resto, 60)
    numero = f"{s:06.3f}".replace(".", ",") if virgula else f"{s:06.3f}"
    aspas = "&quot;" if escapar else '"'
    minuto = "&#x27;" if escapar else "'"
    texto = f"{'-' if sinal and graus < 0 else ''}{int(g):02d}°{int(m):02d}{minuto}{numero}{aspas}"
    return texto + (f" {letra}" if letra else "")


def _vertice(nome, lon, lat, **opcoes) -> str:
    return (f"{nome}, de coordenadas (Longitude: {_dms(lon, **opcoes)}, "
            f"Latitude {_dms(lat, eh_lat=True, **opcoes)} e Altitude: 112,30 m)")


def _memorial(pontos, prefixo="AAAA", *, fechar=True, inicio=True, **opcoes) -> str:
    """O memorial de UM perímetro: `Inicia-se ... no vértice P-M-0001 ... até o vértice P-M-0002 ...`."""
    partes = []
    for i, (lon, lat) in enumerate(pontos, start=1):
        nome = f"{prefixo}-M-{i:04d}"
        if i == 1:
            partes.append(("Inicia-se a descrição deste perímetro no vértice " if inicio else "no vértice ")
                          + _vertice(nome, lon, lat, **opcoes))
        else:
            partes.append(f"deste, segue por cerca, com azimute de 090°00&#x27; e 100,00 m até o vértice "
                          + _vertice(nome, lon, lat, **opcoes))
    if fechar:
        partes.append(f"deste, segue com azimute de 180°00&#x27; e 100,00 m até o vértice {prefixo}-M-0001, "
                      f"ponto inicial da descrição deste perímetro")
    return "; ".join(partes) + "."


def _quadrado(lon, lat, lado=0.01):
    return [(lon, lat), (lon + lado, lat), (lon + lado, lat - lado), (lon, lat - lado)]


def _plano(pontos) -> list:
    return [c for p in pontos for c in p]


def _html(*trechos: str) -> str:
    return "".join(f"<p>{t}</p>\n" for t in trechos)


def _area_ha(pontos) -> float:
    return G.hectares(G.area_perimetro_do_anel(pontos + [pontos[0]])[0])


def _ha(valor: float) -> str:
    return f"{valor:.4f}".replace(".", ",")


# ------------------------------------------------------------------ o banco

@pytest.fixture()
def db(cg_casa):
    cg_casa["db"].set_settings({"ri_cns": "000000"})
    return cg_casa["db"]


def _matricula(db, numero, teor=None, **campos) -> int:
    base = {"numero": str(numero), "livro": "2", "livro_norm": "2", "tipo_ficha": "ESTRUTURADA",
            "criado_em": AGORA, "teor": teor, "teor_formato": "html"}
    base.update(campos)
    with db.transaction() as con:
        return banco(con).escrever(
            f"INSERT INTO ri_matriculas ({', '.join(base)}) VALUES ({', '.join(['%s'] * len(base))}) RETURNING id",
            tuple(base.values()))[0]["id"]


def _extrair(db, mid, **extra):
    with db.transaction() as con:
        return RG.extrair_memorial(con, mid, **{**QUEM, **extra})


def _linha(db, gid):
    with db.connect() as con:
        return dict(banco(con).um("SELECT * FROM ri_geometrias WHERE id = %s", (gid,)))


def _codigos(linha) -> set:
    return {a["codigo"] for a in RG.achados_da_linha(linha)}


def _cfg(db):
    return RG.configuracao(db)


def _limpa(db, numero, pontos=None, *, ponto=(-45.5, -7.2), **campos) -> tuple[int, list]:
    """Uma matrícula cujo memorial não tem aviso nenhum: SIRGAS dito, anel que volta ao 1º vértice, área que bate."""
    pontos = pontos or _quadrado(*ponto)
    teor = _html(f"IMÓVEL rural. {SIRGAS}", _memorial(pontos))
    campos.setdefault("area_valor", _ha(_area_ha(pontos)))
    campos.setdefault("area_unidade", "ha")
    return _matricula(db, numero, teor, **campos), pontos


# ------------------------------------------------------------------ ler o texto (sem banco)

def test_o_teor_html_e_desescapado_ate_duas_vezes_e_perde_a_marcacao():
    bruto = "<p>Longitude: -45°30&#x27;00,000&quot;</p><p>R&amp;R &amp;quot;x&amp;quot;</p>"
    assert F.texto_do_memorial(bruto, "html") == 'Longitude: -45°30\'00,000" R&R "x"'
    assert F.texto_do_memorial("Longitude: -45°30&#x27;00,000&quot;", "texto") == "Longitude: -45°30'00,000\""
    assert F.texto_do_memorial(None) == ""


def test_os_vertices_saem_na_ordem_do_texto_com_nome_e_o_anel_fecha():
    pontos = _quadrado(-45.5, -7.2)
    texto = F.texto_do_memorial(_html(_memorial(pontos)), "html")
    leitura = F.ler_memorial(texto)
    assert len(leitura["glebas"]) == 1
    gleba = leitura["glebas"][0]
    assert [v["nome"] for v in gleba["vertices"]] == [f"AAAA-M-{i:04d}" for i in range(1, 5)]
    assert _plano((v["lon"], v["lat"]) for v in gleba["vertices"]) == pytest.approx(_plano(pontos))
    assert gleba["anel"][0] == gleba["anel"][-1] and len(gleba["anel"]) == 5
    assert not gleba["fechado_pelo_sistema"] or gleba["volta_ao_primeiro"]
    assert gleba["vertices"][0]["lon_txt"] == 'Longitude: -45°30\'00,000"'      # como veio


@pytest.mark.parametrize("escapar,virgula", [(True, True), (False, True), (True, False), (False, False)])
def test_com_e_sem_entidades_e_com_virgula_ou_ponto_o_mesmo_poligono(escapar, virgula):
    pontos = _quadrado(-45.5, -7.2)
    texto = F.texto_do_memorial(_html(_memorial(pontos, escapar=escapar, virgula=virgula)), "html")
    anel = F.ler_memorial(texto)["glebas"][0]["anel"]
    assert _plano(anel[:4]) == pytest.approx(_plano(pontos))


def test_hemisferio_por_letra_ou_por_extenso_vale_como_sinal():
    por_letra = _memorial(_quadrado(-45.5, -7.2), sinal=False, letra="W")
    # a letra do hemisfério da latitude é S: monta à mão
    texto = ("Inicia-se a descrição deste perímetro no vértice AAAA-M-0001, de coordenadas (Longitude: 45°30'00,000\" W, "
             "Latitude 07°12'00,000\" S); até o vértice AAAA-M-0002, de coordenadas (Longitude: 45°29'00,000\" Oeste, "
             "Latitude 07°12'00,000\" Sul); até o vértice AAAA-M-0003, de coordenadas (Longitude: 45°29'00,000\" O, "
             "Latitude 07°13'00,000\" S); até o vértice AAAA-M-0001.")
    gleba = F.ler_memorial(F.texto_do_memorial(texto))["glebas"][0]
    assert gleba["anel"][0] == pytest.approx((-45.5, -7.2)) and gleba["anel"][1] == pytest.approx((-45.4833333, -7.2))
    assert not gleba["sem_hemisferio"] and por_letra       # `por_letra` só prova que o gerador aceita a opção


def test_sinal_e_hemisferio_que_se_contradizem_nao_viram_coordenada():
    texto = ("no vértice AAAA-M-0001, de coordenadas (Longitude: -45°30'00,000\" L, Latitude -07°12'00,000\" S); "
             "até o vértice AAAA-M-0002 (Longitude: -45°29'00,000\", Latitude -07°12'00,000\"); "
             "até o vértice AAAA-M-0003 (Longitude: -45°29'00,000\", Latitude -07°13'00,000\").")
    gleba = F.ler_memorial(F.texto_do_memorial(texto))["glebas"][0]
    assert gleba["ilegiveis"] == 1                        # o primeiro vértice: «-» com «L»


def test_rodape_de_pagina_no_meio_da_coordenada_e_lido_e_marcado():
    texto = ("no vértice AAAA-M-0001, de coordenadas (Longitude: -45°30'00,000\", Latitude – [Registro de Imóveis · "
             "Livro 2 · Matrícula N° 9 · Folha 3 de 12] [continua] 07°12'00,000\" e Altitude: 1 m); "
             "até o vértice AAAA-M-0002 (Longitude: -45°29'00,000\", Latitude -07°12'00,000\"); "
             "até o vértice AAAA-M-0003 (Longitude: -45°29'00,000\", Latitude -07°13'00,000\"); até o vértice AAAA-M-0001.")
    gleba = F.ler_memorial(F.texto_do_memorial(texto))["glebas"][0]
    assert gleba["anel"][0] == pytest.approx((-45.5, -7.2))     # o sinal ficou antes do rodapé
    assert gleba["com_ruido"] == 1 and gleba["ilegiveis"] == 0


def test_coordenada_inexistente_nao_some_em_silencio():
    texto = ("no vértice AAAA-M-0001, de coordenadas (Longitude: -45°61'00,000\", Latitude -07°12'00,000\"); "
             "até o vértice AAAA-M-0002 (Longitude: -45°29'00,000\", Latitude -07°12'00,000\"); "
             "até o vértice AAAA-M-0003 (Longitude: -45°29'00,000\", Latitude -07°13'00,000\"); "
             "até o vértice AAAA-M-0004 (Longitude: -45°30'00,000\", Latitude -07°13'00,000\").")
    gleba = F.ler_memorial(F.texto_do_memorial(texto))["glebas"][0]
    assert gleba["ilegiveis"] == 1 and len(gleba["vertices"]) == 4      # o minuto 61 não existe


def test_o_sistema_do_texto_recusa_sad69_e_corrego_alegre():
    assert F.sistema_do_texto("Datum SAD-69, zona 23")["recusa"] and "SAD 69" in F.sistema_do_texto("SAD 69")["recusa"]
    assert "Córrego Alegre" in F.sistema_do_texto("referido ao Córrego Alegre")["recusa"]
    ambos = F.sistema_do_texto("convertido do SAD 69 para SIRGAS 2000")
    assert ambos["recusa"] and "não dá para saber" in ambos["recusa"]
    assert F.sistema_do_texto("SIRGAS 2000") == {"sistema": "SIRGAS2000", "aviso": None, "recusa": None}
    wgs = F.sistema_do_texto("datum WGS 84")
    assert wgs["sistema"] == "WGS84" and wgs["aviso"] and not wgs["recusa"]
    nada = F.sistema_do_texto("sem datum nenhum")
    assert nada["sistema"] is None and nada["aviso"] and not nada["recusa"]


def test_varios_perimetros_com_inicia_se_viram_glebas_separadas():
    a, b = _quadrado(-45.5, -7.2), _quadrado(-45.3, -7.2)
    texto = F.texto_do_memorial(_html("GLEBA 1: " + _memorial(a, "AAAA"), "GLEBA 2: " + _memorial(b, "BBBB")))
    glebas = F.ler_memorial(texto)["glebas"]
    assert [g["indice"] for g in glebas] == [1, 2]
    assert all(v["nome"].startswith("AAAA") for v in glebas[0]["vertices"])
    assert all(v["nome"].startswith("BBBB") for v in glebas[1]["vertices"])
    assert glebas[0]["rotulo_no_texto"] == "gleba 1" and glebas[1]["rotulo_no_texto"] == "gleba 2"
    assert [len(g["anel"]) for g in glebas] == [5, 5]


def test_sem_inicia_se_o_anel_que_volta_ao_primeiro_vertice_fecha_a_gleba():
    a, b = _quadrado(-45.5, -7.2), _quadrado(-45.3, -7.2)
    corpo = _memorial(a, "AAAA", inicio=False) + " " + _memorial(b, "BBBB", inicio=False)
    corpo = corpo.replace("ponto inicial da descrição deste perímetro", "ponto inicial")
    # a volta ao primeiro vértice é só o NOME (sem coordenada): fecha-se pelo que há de coordenadas
    glebas = F.ler_memorial(F.texto_do_memorial(_html(corpo)))["glebas"]
    # sem repetir a coordenada, nada separa as duas: UMA gleba, e o sistema a marca como suspeita
    assert len(glebas) == 1 and len(glebas[0]["vertices"]) == 8
    com_volta = _memorial(a, "AAAA", inicio=False).replace(
        f"até o vértice AAAA-M-0001, ponto inicial da descrição deste perímetro",
        "até o vértice " + _vertice("AAAA-M-0001", *a[0]))
    glebas = F.ler_memorial(F.texto_do_memorial(_html(com_volta + " " + _memorial(b, "BBBB", inicio=False))))["glebas"]
    assert len(glebas) == 2, "a coordenada que volta ao primeiro vértice fecha a gleba"
    assert all(v["nome"].startswith("AAAA") for v in glebas[0]["vertices"])
    assert all(v["nome"].startswith("BBBB") for v in glebas[1]["vertices"])


# ------------------------------------------------------------------ guardar

def test_extrair_guarda_pendente_com_a_origem_o_texto_e_os_vertices_como_vieram(db):
    mid, pontos = _limpa(db, 4015)
    resumo = _extrair(db, mid)
    assert resumo["glebas"] == 1 and resumo["matricula"] == "4015" and len(resumo["geometrias"]) == 1
    linha = _linha(db, resumo["geometrias"][0])
    assert linha["situacao"] == RG.PENDENTE, "extrair nunca adota"
    assert linha["origem"] == "MEMORIAL" and linha["matricula_declarada"] == "4015" and linha["matricula_id"] == mid
    assert linha["adotada_por"] is None and linha["vertices"] == 4
    guardado = json.loads(linha["origem_atributos"])
    assert guardado["campo_da_ficha"] == "teor" and guardado["sistema_no_texto"] == "SIRGAS2000"
    assert guardado["vertices"][0] == {"nome": "AAAA-M-0001", "lon": pytest.approx(-45.5), "lat": pytest.approx(-7.2),
                                       "lon_txt": 'Longitude: -45°30\'00,000"', "lat_txt": 'Latitude -07°12\'00,000"'}
    assert "Inicia-se a descrição deste perímetro" in guardado["texto_fonte"] and "&#x27;" not in guardado["texto_fonte"]
    with db.connect() as con:
        imp = dict(banco(con).um("SELECT * FROM ri_geo_importacoes WHERE id = %s", (resumo["importacao_id"],)))
    assert imp["arquivo_nome"] == "memorial da matrícula 4015" and imp["formato"] == "MEMORIAL" and imp["epsg"] == 4674
    assert len(imp["arquivo_sha256"]) == 64 and imp["importado_por"] == "Maria Exemplo"
    assert RG.ROTULO_DA_ORIGEM["MEMORIAL"] == "Memorial da matrícula"
    assert _codigos(linha) == set(), "memorial limpo: sem achado"


def test_a_area_medida_fica_ao_lado_da_registrada(db):
    mid, pontos = _limpa(db, 4015)
    gid = _extrair(db, mid)["geometrias"][0]
    with db.connect() as con:
        linha = [l for l in RG.lista(con) if l["id"] == gid][0]
    comparacao = RG.comparar_areas(linha)
    assert comparacao["geodesica_ha"] == pytest.approx(_area_ha(pontos), abs=1e-4)
    assert comparacao["registrada_ha"] == pytest.approx(_area_ha(pontos), abs=1e-4) and comparacao["bate"] is True
    mid2 = _matricula(db, 4016, _html(SIRGAS, _memorial(_quadrado(-45.3, -7.2))), area_valor="100", area_unidade="ha")
    gid2 = _extrair(db, mid2)["geometrias"][0]
    with db.connect() as con:
        linha2 = [l for l in RG.lista(con) if l["id"] == gid2][0]
    assert RG.comparar_areas(linha2)["bate"] is False


def test_o_texto_em_sad69_e_recusado_com_o_motivo_e_nada_e_gravado(db):
    teor = _html("Coordenadas referidas ao datum SAD 69.", _memorial(_quadrado(-45.5, -7.2)))
    mid = _matricula(db, 4015, teor)
    with pytest.raises(RG.GeoImportError) as erro:
        _extrair(db, mid)
    assert "SAD 69" in str(erro.value) and "4015" in str(erro.value) and "QGIS" in str(erro.value)
    mid2 = _matricula(db, 4016, _html("Datum Córrego Alegre.", _memorial(_quadrado(-45.5, -7.2))))
    with pytest.raises(RG.GeoImportError) as erro:
        _extrair(db, mid2)
    assert "Córrego Alegre" in str(erro.value)
    with db.connect() as con:
        assert banco(con).um("SELECT count(*) AS n FROM ri_geometrias")["n"] == 0
        assert banco(con).um("SELECT count(*) AS n FROM ri_geo_importacoes")["n"] == 0


def test_texto_sem_sistema_entra_como_sirgas_com_aviso_e_wgs84_tambem(db):
    sem = _matricula(db, 4015, _html(_memorial(_quadrado(-45.5, -7.2))))
    resumo = _extrair(db, sem)
    assert "SISTEMA_DO_TEXTO" in _codigos(_linha(db, resumo["geometrias"][0]))
    assert any("não diz o sistema" in a for a in resumo["avisos"])
    wgs = _matricula(db, 4016, _html("Datum WGS 84.", _memorial(_quadrado(-45.3, -7.2))))
    codigos = _codigos(_linha(db, _extrair(db, wgs)["geometrias"][0]))
    assert "SISTEMA_DO_TEXTO" in codigos


def test_extrair_duas_vezes_o_mesmo_texto_e_recusado_e_texto_novo_extrai(db):
    mid, _ = _limpa(db, 4015)
    primeiro = _extrair(db, mid)["geometrias"][0]
    with pytest.raises(RG.GeoImportError) as erro:
        _extrair(db, mid)
    assert "já foi extraído" in str(erro.value) and str(primeiro) in str(erro.value)
    with db.transaction() as con:
        RG.descartar(con, primeiro, "texto da ficha vai mudar", quem="Maria Exemplo", agora=AGORA)
    with pytest.raises(RG.GeoImportError):                  # descartado também conta: o mesmo texto, a mesma resposta
        _extrair(db, mid)
    novo = _html(f"IMÓVEL. {SIRGAS}", _memorial(_quadrado(-45.5, -7.2, 0.02)))
    with db.transaction() as con:
        banco(con).escrever("UPDATE ri_matriculas SET teor = %s WHERE id = %s", (novo, mid))
    assert len(_extrair(db, mid)["geometrias"]) == 1


def test_matricula_encerrada_ou_sem_memorial_e_recusada_com_a_frase(db):
    morta = _matricula(db, 4015, _html(SIRGAS, _memorial(_quadrado(-45.5, -7.2))), encerrada=1)
    with pytest.raises(RG.GeoImportError) as erro:
        _extrair(db, morta)
    assert "encerrada" in str(erro.value)
    vazia = _matricula(db, 4016, _html("IMÓVEL sem coordenadas, só com confrontações."))
    with pytest.raises(RG.GeoImportError) as erro:
        _extrair(db, vazia)
    assert "graus, minutos e segundos" in str(erro.value)
    decimal = _matricula(db, 4017, _html("Longitude: -45,500000, Latitude -7,200000."))
    with pytest.raises(RG.GeoImportError):
        _extrair(db, decimal)
    with pytest.raises(RG.GeoImportError) as erro:
        _extrair(db, 999999)
    assert "não existe" in str(erro.value)


def test_se_o_teor_nao_tem_o_memorial_le_a_descricao_do_perimetro(db):
    pontos = _quadrado(-45.5, -7.2)
    mid = _matricula(db, 4015, _html("Teor sem coordenadas."), descricao_perimetro=_html(SIRGAS, _memorial(pontos)))
    guardado = json.loads(_linha(db, _extrair(db, mid)["geometrias"][0])["origem_atributos"])
    assert guardado["campo_da_ficha"] == "descricao_perimetro"


# ------------------------------------------------------------------ gleba

def test_matricula_com_duas_glebas_vira_dois_poligonos_e_nunca_um_anel_so(db):
    a, b = _quadrado(-45.5, -7.2), _quadrado(-45.3, -7.2)
    teor = _html(SIRGAS, "GLEBA 1: " + _memorial(a, "AAAA"), "GLEBA 2: " + _memorial(b, "BBBB"))
    mid = _matricula(db, 4015, teor, area_valor=_ha(_area_ha(a) + _area_ha(b)), area_unidade="ha")
    resumo = _extrair(db, mid)
    assert resumo["glebas"] == 2 and len(resumo["geometrias"]) == 2
    linhas = [_linha(db, g) for g in resumo["geometrias"]]
    for linha, pontos, prefixo in zip(linhas, (a, b), ("AAAA", "BBBB")):
        assert linha["vertices"] == 4 and linha["situacao"] == RG.PENDENTE
        assert linha["min_lon"] == pytest.approx(min(p[0] for p in pontos))
        assert linha["max_lon"] == pytest.approx(max(p[0] for p in pontos))      # a caixa é da gleba, e não das duas
        guardado = json.loads(linha["origem_atributos"])
        assert guardado["de_n_glebas"] == 2 and all(v["nome"].startswith(prefixo) for v in guardado["vertices"])
        assert "VARIAS_GLEBAS" in _codigos(linha)
    aviso = [a for a in RG.achados_da_linha(linhas[0]) if a["codigo"] == "VARIAS_GLEBAS"][0]["texto"]
    assert "CONFERIR" in aviso and "soma das 2 glebas" in aviso and "0,00%" in aviso
    assert json.loads(linhas[0]["origem_atributos"])["rotulo_no_texto"] == "gleba 1"


def test_adotar_uma_gleba_avisa_que_a_matricula_tem_outras(db):
    a, b = _quadrado(-45.5, -7.2), _quadrado(-45.3, -7.2)
    mid = _matricula(db, 4015, _html(SIRGAS, _memorial(a, "AAAA"), _memorial(b, "BBBB")))
    primeira = _extrair(db, mid)["geometrias"][0]
    with db.transaction() as con:
        saida = RG.adotar(con, primeira, mid, **QUEM)
    assert any("várias glebas" in a for a in saida["avisos"])


# ------------------------------------------------------------------ o que não se adota

def test_coordenada_ilegivel_vira_erro_e_nao_se_adota(db):
    teor = _html(SIRGAS, _memorial(_quadrado(-45.5, -7.2)).replace("-45°30&#x27;00,000&quot;", "-45°61&#x27;00,000&quot;", 1))
    mid = _matricula(db, 4015, teor)
    resumo = _extrair(db, mid)
    linha = _linha(db, resumo["geometrias"][0])
    assert resumo["com_erro"] == 1 and linha["situacao"] == RG.PENDENTE
    assert "COORDENADA_ILEGIVEL" in _codigos(linha)
    with pytest.raises(RG.GeoImportError) as erro:
        with db.transaction() as con:
            RG.adotar(con, linha["id"], mid, **QUEM)
    assert "erro" in str(erro.value)


def test_coordenada_sem_sinal_e_sem_hemisferio_vira_erro(db):
    mid = _matricula(db, 4015, _html(SIRGAS, _memorial(_quadrado(-45.5, -7.2), sinal=False)))
    linha = _linha(db, _extrair(db, mid)["geometrias"][0])
    assert "SEM_HEMISFERIO" in _codigos(linha)
    assert RG.tem_erro(RG.achados_da_linha(linha))


def test_memorial_cortado_que_nao_volta_ao_primeiro_vertice_e_aviso(db):
    mid = _matricula(db, 4015, _html(SIRGAS, _memorial(_quadrado(-45.5, -7.2), fechar=False)))
    linha = _linha(db, _extrair(db, mid)["geometrias"][0])
    assert "ANEL_FECHADO_PELO_SISTEMA" in _codigos(linha) and not RG.tem_erro(RG.achados_da_linha(linha))


def test_anel_que_se_cruza_e_erro_do_conferidor_que_ja_existia(db):
    gravata = [(-45.5, -7.2), (-45.49, -7.21), (-45.49, -7.2), (-45.5, -7.21)]
    mid = _matricula(db, 4015, _html(SIRGAS, _memorial(gravata)))
    assert "AUTOINTERSECCAO" in _codigos(_linha(db, _extrair(db, mid)["geometrias"][0]))


def test_ato_com_coordenadas_no_teor_e_aviso(db):
    mid, _ = _limpa(db, 4015)
    with db.transaction() as con:
        banco(con).escrever(
            "INSERT INTO ri_atos (matricula_id, tipo, numero, teor, hash_ato, lavrado_em) "
            "VALUES (%s,'AVERBACAO',1,%s,'x',%s)",
            (mid, "Nova descrição: (Longitude: -45°30'00\", Latitude -07°12'00\")", AGORA))
    assert "ATO_COM_COORDENADAS" in _codigos(_linha(db, _extrair(db, mid)["geometrias"][0]))


# ------------------------------------------------------------------ o lote de adoção

def test_o_lote_so_adota_o_memorial_sem_nenhum_aviso_e_diz_por_que_deixou_os_outros(db):
    limpa, _ = _limpa(db, 4015, ponto=(-45.5, -7.2))
    sem_sistema = _matricula(db, 4016, _html(_memorial(_quadrado(-45.3, -7.2))),
                             area_valor=_ha(_area_ha(_quadrado(-45.3, -7.2))), area_unidade="ha")
    nao_bate = _matricula(db, 4017, _html(SIRGAS, _memorial(_quadrado(-45.1, -7.2))), area_valor="10", area_unidade="ha")
    sem_area = _matricula(db, 4018, _html(SIRGAS, _memorial(_quadrado(-44.9, -7.2))))
    duas = _matricula(db, 4019, _html(SIRGAS, _memorial(_quadrado(-44.7, -7.2), "AAAA"),
                                      _memorial(_quadrado(-44.5, -7.2), "BBBB")))
    ids = {n: _extrair(db, m)["geometrias"] for n, m in
           ((4015, limpa), (4016, sem_sistema), (4017, nao_bate), (4018, sem_area), (4019, duas))}
    with db.transaction() as con:
        saida = RG.adotar_memoriais_sem_aviso(con, _cfg(db), **QUEM)
    assert saida["adotadas"] == ids[4015]
    assert _linha(db, ids[4015][0])["situacao"] == RG.VIGENTE and _linha(db, ids[4015][0])["adotada_por"] == "Maria Exemplo"
    motivos = {d["matricula"]: d["motivo"] for d in saida["deixadas"]}
    assert motivos["4016"] == "tem aviso ou erro" and motivos["4019"] == "tem aviso ou erro"
    assert motivos["4017"].startswith("a área não bate com a registrada (") and motivos["4017"].endswith("%)")
    assert motivos["4018"] == "a ficha não tem área para comparar"
    for numero in (4016, 4017, 4018):
        assert _linha(db, ids[numero][0])["situacao"] == RG.PENDENTE


def test_o_lote_nao_troca_vigente_nem_adota_o_que_se_sobrepoe(db):
    pontos = _quadrado(-45.5, -7.2)
    ocupada, _ = _limpa(db, 4015, pontos)
    primeira = _extrair(db, ocupada)["geometrias"][0]
    with db.transaction() as con:
        mesma = RG.adotar(con, primeira, ocupada, **QUEM)
    assert mesma["substituiu"] is None
    # a mesma matrícula, texto novo: já tem vigente
    novo = _html(f"IMÓVEL. {SIRGAS}", _memorial(pontos, "ZZZZ"))
    with db.transaction() as con:
        banco(con).escrever("UPDATE ri_matriculas SET teor = %s WHERE id = %s", (novo, ocupada))
    reextraida = _extrair(db, ocupada)["geometrias"][0]
    vizinha, _ = _limpa(db, 4016, [(pontos[0][0] + 0.005, pontos[0][1] - 0.002)] + [
        (pontos[1][0] + 0.005, pontos[1][1] - 0.002), (pontos[2][0] + 0.005, pontos[2][1] - 0.002),
        (pontos[3][0] + 0.005, pontos[3][1] - 0.002)])
    sobreposta = _extrair(db, vizinha)["geometrias"][0]
    with db.transaction() as con:
        saida = RG.adotar_memoriais_sem_aviso(con, _cfg(db), **QUEM)
    motivos = {d["id"]: d["motivo"] for d in saida["deixadas"]}
    assert motivos[reextraida] == "a matrícula já tem polígono vigente"
    assert motivos[sobreposta] == "sobrepõe outro polígono vigente"
    assert saida["adotadas"] == []


def test_o_lote_antigo_das_sugestoes_de_arquivo_nao_leva_memorial(db):
    mid, _ = _limpa(db, 4015)
    gid = _extrair(db, mid)["geometrias"][0]
    with db.transaction() as con:
        saida = RG.adotar_sugestoes(con, **QUEM)
    assert saida == {"adotadas": [], "deixadas": []} and _linha(db, gid)["situacao"] == RG.PENDENTE


def test_extrair_em_lote_guarda_pendentes_diz_o_que_recusou_e_nao_adota(db):
    _limpa(db, 4015)
    _matricula(db, 4016, _html("Datum SAD 69.", _memorial(_quadrado(-45.3, -7.2))))
    _matricula(db, 4017, _html("Só texto, sem coordenada nenhuma."))
    _matricula(db, 4018, _html(SIRGAS, _memorial(_quadrado(-45.1, -7.2))), encerrada=1)
    with db.transaction() as con:
        saida = RG.extrair_memoriais_em_lote(con, **QUEM)
    assert saida["extraidas"] == ["4015"] and saida["poligonos"] == 1
    assert [r["matricula"] for r in saida["recusadas"]] == ["4016"] and "SAD 69" in saida["recusadas"][0]["motivo"]
    with db.connect() as con:
        assert [l["situacao"] for l in RG.lista(con)] == [RG.PENDENTE]
        assert RG.matriculas_com_memorial(con) and [m["rotulo"] for m in RG.matriculas_com_memorial(con)] == ["4015", "4016"]
    with db.transaction() as con:
        again = RG.extrair_memoriais_em_lote(con, **QUEM)
    assert again["extraidas"] == [] and {r["matricula"] for r in again["recusadas"]} == {"4015", "4016"}


# ------------------------------------------------------------------ a tela

@pytest.fixture()
def usuarios(cg_casa):
    db = cg_casa["db"]
    db.set_settings({"ri_cns": "000000"})
    for login, papel in (("oficial", "ADMIN"), ("balcao", "USER"), ("auditor", "AUDITOR")):
        db.create_user(login, login.upper() + " EXEMPLO", SENHA, papel)
    cg_casa["clientes"] = {}
    for login in ("oficial", "balcao", "auditor"):
        c = cg_casa["app"].test_client()
        cg_login(c, login, SENHA)
        cg_casa["clientes"][login] = c
    return cg_casa


def _token(c) -> str:
    html = c.get("/registro-imoveis/mapa").get_data(as_text=True)
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def test_extrair_pela_tela_guarda_pendente_mostra_vertices_e_diz_que_nao_adotou(usuarios):
    c, db = usuarios["clientes"]["balcao"], usuarios["db"]
    mid, pontos = _limpa(db, 4015)
    r = c.post("/registro-imoveis/mapa/memorial", follow_redirects=True,
               data={"csrf_token": _token(c), "matricula": "4.015"})
    html = r.get_data(as_text=True)
    assert "1 gleba(s) do memorial guardada(s) como PENDENTES" in html and "Nenhuma foi adotada" in html
    assert "Memorial da matrícula" in html and "Registrada na ficha" in html
    with db.connect() as con:
        (g,) = banco(con).ler("SELECT id, situacao FROM ri_geometrias")
    assert g["situacao"] == RG.PENDENTE
    ver = c.get(f"/registro-imoveis/mapa/{g['id']}").get_data(as_text=True)
    assert "O memorial de onde saiu" in ver and "AAAA-M-0001" in ver and "Texto-fonte desta gleba" in ver
    assert "SIRGAS 2000" in ver and "&#x27;" not in ver.replace("&#39;", "")
    auditoria = [l for l in db.list_logs(10) if l["action"] == "RI_GEO_MEMORIAL_EXTRAIDO"]
    assert auditoria and '"matricula": "4015"' in auditoria[0]["details"]
    de_novo = c.post("/registro-imoveis/mapa/memorial", follow_redirects=True,
                     data={"csrf_token": _token(c), "matricula": "4015"})
    assert "já foi extraído" in de_novo.get_data(as_text=True)
    nao_existe = c.post("/registro-imoveis/mapa/memorial", follow_redirects=True,
                        data={"csrf_token": _token(c), "matricula": "9999"})
    assert "Não achei a matrícula" in nao_existe.get_data(as_text=True)


def test_sad69_pela_tela_diz_por_que_recusou(usuarios):
    c, db = usuarios["clientes"]["balcao"], usuarios["db"]
    _matricula(db, 4015, _html("Datum SAD 69.", _memorial(_quadrado(-45.5, -7.2))))
    r = c.post("/registro-imoveis/mapa/memorial", follow_redirects=True,
               data={"csrf_token": _token(c), "matricula": "4015"})
    assert "SAD 69" in r.get_data(as_text=True) and "sistema antigo" in r.get_data(as_text=True)


def test_lote_pela_tela_extrai_e_adota_so_o_sem_aviso(usuarios):
    c, db = usuarios["clientes"]["balcao"], usuarios["db"]
    _limpa(db, 4015)
    _matricula(db, 4016, _html(_memorial(_quadrado(-45.3, -7.2))), area_valor="1", area_unidade="ha")
    r = c.post("/registro-imoveis/mapa/memorial-lote", follow_redirects=True, data={"csrf_token": _token(c)})
    assert "2 matrícula(s) com memorial extraída(s)" in r.get_data(as_text=True)
    r = c.post("/registro-imoveis/mapa/adotar-memoriais", follow_redirects=True, data={"csrf_token": _token(c)})
    html = r.get_data(as_text=True)
    assert "1 memorial(is) sem aviso adotado(s); 1 ficaram para a sua conferência" in html
    with db.connect() as con:
        situacoes = {l["rotulo"] or l["matricula_declarada"]: l["situacao"] for l in RG.lista(con)}
    assert situacoes == {"4015": RG.VIGENTE, "4016": RG.PENDENTE}
    acoes = [l["action"] for l in db.list_logs(20)]
    assert "RI_GEO_MEMORIAL_EM_LOTE" in acoes and "RI_GEO_ADOTADO_EM_LOTE" in acoes


def test_o_auditor_ve_e_nao_extrai_nem_adota_em_lote(usuarios):
    c = usuarios["clientes"]["auditor"]
    assert c.get("/registro-imoveis/mapa").status_code == 200
    for rota in ("memorial", "memorial-lote", "adotar-memoriais"):
        assert c.post(f"/registro-imoveis/mapa/{rota}", data={"csrf_token": _token(c)}).status_code == 403, rota
