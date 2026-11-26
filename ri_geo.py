"""OS POLÍGONOS DO MAPA — guardar a geometria ligada à matrícula, conferir e gerar o arquivo do ONR.

    «O Sistema de Informações Geográficas do Registro de Imóveis (SIG-RI) destina-se a servir de base de
     dados geográficos relativos às informações imobiliárias mantidas pelos cartórios de registro de imóveis.»
    (CNN, art. 343-D, incluído pelo Provimento CN n. 195/2025; ver `docs/MAPA_ONR.md`)

ONDE ISTO SE ENCAIXA
    `ri_mapa_onr.py` dá os quatro atributos do Mapa (MATRICULA, CNS, PROPRIETAR, AREA_HA) e **não guardava
    geometria**: quem tinha o polígono era o QGIS. Este módulo guarda o polígono, com a ORIGEM de cada um, mede a
    área no elipsoide, confere (fechamento, cruzamento próprio, sobreposição, matrícula aberta) e gera o
    `.gpkg` e o Shapefile que o plugin de referência geraria. A conta é de `geo_geodesia`; os formatos, de
    `geo_formatos`; a tela, de `ri_geo_web`.

    **Nada vai ao ONR daqui.** O arquivo é gerado e baixado por quem tem papel de ADMIN; quem o envia ao Mapa,
    pela intranet do ONR, é o oficial. O sistema não entra no Mapa nem em portal.

O QUE FICA GUARDADO, E DE ONDE VEIO
    `ri_geo_importacoes`  um arquivo que entrou: nome, SHA-256, formato, camada, sistema de coordenadas, de que
                          levantamento é, quem o desenhou (responsável técnico), e quem o importou, quando.
    `ri_geometrias`       cada polígono do arquivo, **no SIRGAS 2000 (lon, lat)** — WKB em hexadecimal —, com a
                          origem (arquivo, feição, atributos como vieram), as medidas (área geodésica,
                          perímetro, vértices), os achados da conferência e a situação:

                          PENDENTE     entrou, e ainda não foi adotado para uma matrícula (pode ter uma
                                       matrícula SUGERIDA pelo atributo do arquivo)
                          VIGENTE      é o polígono desta matrícula (no máximo um por matrícula)
                          SUBSTITUIDA  foi o vigente e saiu para outro entrar — fica, com quem o trocou
                          DESCARTADA   alguém disse que não serve — fica, com o motivo

    **A importação NUNCA adota sozinha.** Atributo de arquivo de terceiro é sugestão: quem adota é a pessoa, na
    tela (ou em lote, para as sugestões sem erro). Substituir o vigente de uma matrícula também é ato da pessoa.

O MEMORIAL DA MATRÍCULA (`extrair_memorial`)
    O teor da matrícula traz, em muitas fichas, o memorial no formato do SIGEF: vértices com nome e
    Longitude/Latitude em graus, minutos e segundos. `extrair_memorial` LÊ esse texto (a leitura é de `geo_formatos`)
    e guarda cada gleba como polígono PENDENTE, com origem «memorial da matrícula N», o texto-fonte e os vértices
    como vieram. Regras: SIRGAS 2000 (o texto que diz SAD 69 ou Córrego Alegre é **recusado**, com o motivo); a
    matrícula com mais de uma gleba no texto vira **um polígono por gleba** (nunca vértices de glebas diferentes
    num anel só) e leva o aviso «várias glebas», com a soma das áreas ao lado da registrada; nada é adotado:
    adoção é ato da pessoa — um a um, ou em lote só para o memorial **sem nenhum aviso**
    (`adotar_memoriais_sem_aviso`: área que bate, sem sobreposição, sem gleba irmã, matrícula aberta e sem vigente).

A ÁREA DO ARQUIVO É DECISÃO DO OFICIAL (`ri_mapa_area_regra`)
    O plugin de referência manda a área REGISTRADA quando o banco a tem, e a geodésica só no vazio; o ONR fala
    da geodésica. A casa não escolheu: o ajuste fica em Configurações do sistema e **a geração do arquivo exige
    que alguém tenha escolhido** (a tela pergunta, com as três respostas). Valores:
    REGISTRADA_SENAO_GEODESICA (a regra do plugin), GEODESICA, REGISTRADA.

O QUE «CONFERIR» QUER DIZER AQUI
    ERRO    o polígono não é um polígono (não fecha, se cruza, não tem vértices) ou a matrícula não existe/não
            está aberta — **fica fora do arquivo**, e a tela diz por quê
    AVISO   o que a pessoa lê e decide: sobreposição com outro polígono, área que não bate com a registrada,
            coordenadas fora do Brasil, dono ou CNS em branco — **vai no arquivo**
    As tolerâncias são valores de trabalho desta casa (`geo_geodesia`), e não as do ONR.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any, Iterable, Sequence

import geo_formatos as FORM
import geo_geodesia as GEO
import ri_mapa_onr as MAPA
from bd_nativo import banco

# --------------------------------------------------------------- vocabulário

PENDENTE, VIGENTE, SUBSTITUIDA, DESCARTADA = "PENDENTE", "VIGENTE", "SUBSTITUIDA", "DESCARTADA"
SITUACOES = (PENDENTE, VIGENTE, SUBSTITUIDA, DESCARTADA)

ORIGENS = ("GPKG", "SHP", "GEOJSON", "SIGEF", "MEMORIAL")
ROTULO_DA_ORIGEM = {"GPKG": "GeoPackage", "SHP": "Shapefile", "GEOJSON": "GeoJSON",
                    "SIGEF": "Parcela do SIGEF", "MEMORIAL": "Memorial da matrícula"}

CHAVE_REGRA_DA_AREA = "ri_mapa_area_regra"
CHAVE_TOLERANCIA_FECHAMENTO = "ri_geo_tolerancia_fechamento_m"
CHAVE_TOLERANCIA_SOBREPOSICAO = "ri_geo_tolerancia_sobreposicao_m2"
CHAVE_DIVERGENCIA_DA_AREA = "ri_geo_divergencia_area_pct"

REGRA_PLUGIN = "REGISTRADA_SENAO_GEODESICA"
REGRA_GEODESICA = "GEODESICA"
REGRA_REGISTRADA = "REGISTRADA"
REGRAS_DA_AREA = {
    REGRA_PLUGIN: "A registrada, quando a ficha a tem; a geodésica só quando não tem (a regra do plugin de referência)",
    REGRA_GEODESICA: "Sempre a geodésica, calculada no SIRGAS 2000 (o que o ONR descreve)",
    REGRA_REGISTRADA: "Sempre a registrada na ficha (vazia, quando a ficha não tem)",
}

#: Da área registrada, o quanto a geodésica pode diferir antes de a tela marcar «não bate». Valor de trabalho.
DIVERGENCIA_PADRAO_PCT = 1.0

#: Nomes de atributo em que o arquivo costuma trazer a matrícula (sem acento, minúsculo). **Sugestão**: o que
#: casa vira proposta de vínculo, que a pessoa adota.
_ATRIBUTOS_DA_MATRICULA = ("matricula", "matric", "mat", "num_matric", "numero_matricula", "n_matricula",
                           "registro_m", "nr_matricula")
#: Nomes em que o SIGEF, ou quem o baixou, costuma pôr o código da parcela. **NÃO CONFIRMADO em fonte oficial**
#: (a descrição das camadas do Acervo Fundiário não foi achada em fonte pública): só se usa para PREENCHER o campo,
#: que a pessoa confere e corrige na tela.
_ATRIBUTOS_DO_SIGEF = ("parcela_co", "cod_parcela", "codigo_parcela", "parcela_codigo", "sigef", "cod_sigef")

_SO_ALGARISMOS_E_LETRAS = re.compile(r"[^0-9A-Za-z]+")


class GeoImportError(ValueError):
    """O arquivo, ou o pedido, não cabe — a frase diz o que fazer. Nada foi gravado."""


# --------------------------------------------------------------- esquema

SCHEMA = (
    """
CREATE TABLE IF NOT EXISTS ri_geo_importacoes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    arquivo_nome TEXT,
    arquivo_sha256 TEXT NOT NULL,
    formato TEXT NOT NULL,
    camada TEXT,
    epsg INTEGER,
    origem TEXT NOT NULL,
    levantamento TEXT,
    responsavel_tecnico TEXT,
    n_feicoes INTEGER NOT NULL DEFAULT 0,
    avisos TEXT,
    importado_por TEXT,
    importado_por_id INTEGER,
    importado_em TEXT NOT NULL
)""",
    """
CREATE TABLE IF NOT EXISTS ri_geometrias (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    importacao_id INTEGER NOT NULL,
    matricula_id INTEGER,
    situacao TEXT NOT NULL,
    origem TEXT NOT NULL,
    origem_feicao INTEGER,
    origem_atributos TEXT,
    matricula_declarada TEXT,
    levantamento TEXT,
    responsavel_tecnico TEXT,
    sigef_codigo TEXT,
    geom_wkb_hex TEXT NOT NULL,
    min_lon DOUBLE PRECISION NOT NULL,
    min_lat DOUBLE PRECISION NOT NULL,
    max_lon DOUBLE PRECISION NOT NULL,
    max_lat DOUBLE PRECISION NOT NULL,
    area_geodesica_m2 DOUBLE PRECISION NOT NULL,
    perimetro_m DOUBLE PRECISION NOT NULL,
    vertices INTEGER NOT NULL,
    fechamento_m DOUBLE PRECISION NOT NULL DEFAULT 0,
    achados TEXT,
    substituida_por INTEGER,
    substituida_em TEXT,
    descartada_motivo TEXT,
    adotada_por TEXT,
    adotada_por_id INTEGER,
    adotada_em TEXT,
    criado_em TEXT NOT NULL,
    FOREIGN KEY(importacao_id) REFERENCES ri_geo_importacoes(id),
    FOREIGN KEY(matricula_id) REFERENCES ri_matriculas(id)
)""",
    "CREATE INDEX IF NOT EXISTS ix_ri_geometrias_mat ON ri_geometrias(matricula_id)",
    "CREATE INDEX IF NOT EXISTS ix_ri_geometrias_imp ON ri_geometrias(importacao_id)",
    # No máximo UM polígono vigente por matrícula — o banco recusa o segundo, e não só a tela.
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_ri_geometrias_vigente ON ri_geometrias(matricula_id) "
    "WHERE situacao = 'VIGENTE'",
)


def init_geo_schema(con) -> None:
    """As duas tabelas. Idempotente; roda a cada subida, depois de `init_ri_schema` (as chaves estrangeiras)."""
    bd = banco(con)
    for comando in SCHEMA:
        bd.escrever(comando)


# --------------------------------------------------------------- pequenas coisas

def _sem_acento(texto: Any) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(texto or "")) if unicodedata.category(c) != "Mn")


def _texto(valor: Any, limite: int = 500) -> str | None:
    texto = " ".join(str(valor or "").split())
    return texto[:limite] or None


def configuracao(db) -> dict:
    """As configurações do mapa lidas das `settings`, com o padrão de trabalho quando não há."""
    def numero(chave: str, padrao: float) -> float:
        try:
            valor = float(str(db.get_setting(chave, "") or "").replace(",", "."))
            return valor if valor >= 0 else padrao
        except ValueError:
            return padrao
    regra = (db.get_setting(CHAVE_REGRA_DA_AREA, "") or "").strip().upper()
    return {"regra_da_area": regra if regra in REGRAS_DA_AREA else "",
            "tolerancia_fechamento_m": numero(CHAVE_TOLERANCIA_FECHAMENTO, GEO.TOLERANCIA_FECHAMENTO_M),
            "tolerancia_sobreposicao_m2": numero(CHAVE_TOLERANCIA_SOBREPOSICAO, GEO.TOLERANCIA_SOBREPOSICAO_M2),
            "divergencia_area_pct": numero(CHAVE_DIVERGENCIA_DA_AREA, DIVERGENCIA_PADRAO_PCT)}


def _matricula_do_atributo(atributos: dict) -> str | None:
    for nome, valor in atributos.items():
        if _sem_acento(nome).strip().lower() in _ATRIBUTOS_DA_MATRICULA and valor not in (None, ""):
            if isinstance(valor, float) and valor.is_integer():
                valor = int(valor)
            return _texto(valor, 40)
    return None


def _sigef_do_atributo(atributos: dict) -> str | None:
    for nome, valor in atributos.items():
        if _sem_acento(nome).strip().lower() in _ATRIBUTOS_DO_SIGEF and valor not in (None, ""):
            return _texto(valor, 80)
    return None


def _atributos_para_guardar(atributos: dict) -> str:
    """Os atributos como vieram, em JSON — o que prova de onde o polígono saiu. Valor não serializável vira texto."""
    limpo = {}
    for chave, valor in list(atributos.items())[:80]:
        if isinstance(valor, (bytes, bytearray, memoryview)):
            valor = f"<{len(valor)} bytes>"
        elif not isinstance(valor, (str, int, float, bool, type(None))):
            valor = str(valor)
        limpo[str(chave)[:80]] = valor if not isinstance(valor, str) else valor[:300]
    return json.dumps(limpo, ensure_ascii=False)


def _geometria_do_wkb_hex(texto: str) -> list:
    return FORM.geometria_de_wkb(bytes.fromhex(texto))[0]


def achados_da_linha(linha: dict) -> list[dict]:
    try:
        return json.loads(linha.get("achados") or "[]")
    except ValueError:
        return []


def tem_erro(achados: Iterable[dict]) -> bool:
    return any(a.get("nivel") == GEO.ERRO for a in achados)


# --------------------------------------------------------------- achar a matrícula

def achar_matriculas(con, rotulo: Any) -> list[dict]:
    """As fichas cujo número, escrito como a ficha o escreve (`4015`, `4015-A`), é `rotulo`.

    Aceita `4.015` e `4015 a`; compara só pelos algarismos e letras, sem maiúscula. Mais de uma ficha (a mesma matrícula em dois
    livros) volta como lista de mais de um: quem chama decide — o sistema não escolhe por conta própria.
    """
    chave = _SO_ALGARISMOS_E_LETRAS.sub("", str(rotulo or "")).lower()
    if not chave:
        return []
    return banco(con).ler(
        f"""SELECT m.id, m.numero, m.complemento, m.livro, m.situacao, m.encerrada,
                   {MAPA._MATRICULA} AS rotulo, m.area_valor, m.area_unidade
              FROM ri_matriculas m
             WHERE lower(regexp_replace({MAPA._MATRICULA}, '[^0-9A-Za-z]+', '', 'g')) = %s
             ORDER BY m.id""", (chave,))


def esta_aberta(matricula: dict) -> bool:
    """A matrícula vale para o mapa? É a mesma regra de `ri_mapa_onr` (encerrada e anulada ficam de fora)."""
    return not (int(matricula.get("encerrada") or 0) or str(matricula.get("situacao") or "") in
                MAPA.SITUACOES_FORA_DO_MAPA)


# --------------------------------------------------------------- importar

def _camada_a_usar(camadas: list[dict], escolhida: str | None) -> dict:
    if escolhida:
        for camada in camadas:
            if camada["nome"] == escolhida:
                return camada
        raise GeoImportError(f"O arquivo não tem a camada «{escolhida}».")
    if len(camadas) == 1:
        return camadas[0]
    nomes = ", ".join(c["nome"] for c in camadas)
    raise GeoImportError(f"O arquivo tem mais de uma camada ({nomes}). Escolha qual importar.")


def _epsg_a_usar(camada: dict, forcado: int | None) -> int:
    if forcado:
        return int(forcado)
    if camada.get("epsg") is None:
        raise GeoImportError("O arquivo não diz o sistema de coordenadas (falta o .prj, ou ele não é conhecido). "
                             "Diga qual é no formulário, ou salve o arquivo no QGIS em SIRGAS 2000 (EPSG:4674).")
    return int(camada["epsg"])


def importar(con, *, nome: str, dados: bytes, quem: str | None, quem_id: int | None, agora: str,
             camada: str | None = None, epsg: int | None = None, origem_declarada: str | None = None,
             levantamento: str | None = None, responsavel_tecnico: str | None = None,
             tolerancia_fechamento_m: float = GEO.TOLERANCIA_FECHAMENTO_M) -> dict:
    """Guarda as feições do arquivo como polígonos PENDENTES. Devolve o resumo; nada é adotado.

    `origem_declarada` = `"SIGEF"` quando a pessoa diz que o arquivo é a parcela do SIGEF (o formato continua
    sendo o do arquivo, e fica em `ri_geo_importacoes.formato`). Uma feição que não é polígono, ou cujo
    sistema não se trata, **não entra** e vai nos `avisos` do resumo, com o motivo: nada some em silêncio. Se
    nenhuma feição entra, nada é gravado e a recusa diz por quê.
    """
    try:
        camadas = FORM.ler_arquivo(nome, dados)
        escolhida = _camada_a_usar(camadas, camada)
        sistema = GEO.sistema_do_epsg(_epsg_a_usar(escolhida, epsg))
    except GEO.GeoErro as erro:
        raise GeoImportError(str(erro)) from erro
    formato = escolhida["origem"]
    origem = "SIGEF" if (origem_declarada or "").upper() == "SIGEF" else formato
    avisos: list[str] = list(escolhida.get("avisos") or [])
    if sistema.get("aviso"):
        avisos.append(sistema["aviso"])
    prontas: list[dict] = []
    for feicao in escolhida["feicoes"]:
        rotulo = f"Feição {feicao['indice'] + 1}"
        if not feicao["geometria"]:
            avisos.append(f"{rotulo}: " + (" ".join(feicao["avisos"]) or "sem geometria") + " Não foi importada.")
            continue
        try:
            geometria = [[GEO.para_sirgas(anel, sistema) for anel in poligono] for poligono in feicao["geometria"]]
            medidas = GEO.analisar(geometria, tolerancia_fechamento_m=tolerancia_fechamento_m)
        except GEO.GeoErro as erro:
            avisos.append(f"{rotulo}: {erro}")
            continue
        achados = list(medidas["achados"])
        if feicao["tipo"] in ("LineString", "MultiLineString"):
            achados.append({"codigo": "LINHA", "nivel": GEO.AVISO,
                            "texto": "A feição era uma LINHA no arquivo, e o sistema a fechou como polígono "
                                     "(como faz o plugin do QGIS). Confira o desenho."})
        prontas.append({"feicao": feicao, "geometria": geometria, "medidas": medidas, "achados": achados})
    if not prontas:
        raise GeoImportError("Nenhuma feição do arquivo pôde ser importada: " + (" ".join(avisos) or "o arquivo "
                             "não tem polígonos") )
    bd = banco(con)
    sha = hashlib.sha256(dados).hexdigest()
    importacao_id = int(bd.escrever(
        """INSERT INTO ri_geo_importacoes
              (arquivo_nome, arquivo_sha256, formato, camada, epsg, origem, levantamento, responsavel_tecnico,
               n_feicoes, avisos, importado_por, importado_por_id, importado_em)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (_texto(nome, 200), sha, formato, _texto(escolhida["nome"], 200), sistema["epsg"], origem,
         _texto(levantamento), _texto(responsavel_tecnico, 200), len(prontas),
         json.dumps(avisos, ensure_ascii=False) if avisos else None, quem, quem_id, agora))[0]["id"])
    criadas: list[int] = []
    for p in prontas:
        feicao, geometria, medidas = p["feicao"], p["geometria"], p["medidas"]
        caixa = medidas["caixa"] or GEO.caixa(geometria)
        declarada = _matricula_do_atributo(feicao["atributos"])
        sigef = _sigef_do_atributo(feicao["atributos"]) if origem == "SIGEF" else None
        criadas.append(int(bd.escrever(
            """INSERT INTO ri_geometrias
                  (importacao_id, matricula_id, situacao, origem, origem_feicao, origem_atributos,
                   matricula_declarada, levantamento, responsavel_tecnico, sigef_codigo, geom_wkb_hex,
                   min_lon, min_lat, max_lon, max_lat, area_geodesica_m2, perimetro_m, vertices, fechamento_m,
                   achados, criado_em)
               VALUES (%s,NULL,'PENDENTE',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (importacao_id, origem, feicao["indice"], _atributos_para_guardar(feicao["atributos"]), declarada,
             _texto(levantamento), _texto(responsavel_tecnico, 200), sigef,
             FORM.wkb_de_geometria(geometria).hex(), caixa[0], caixa[1], caixa[2], caixa[3],
             medidas["area_m2"], medidas["perimetro_m"], medidas["vertices"], medidas["fechamento_m"],
             json.dumps(p["achados"], ensure_ascii=False), agora))[0]["id"]))
    sugeridas = 0
    for gid in criadas:
        sugestao = sugerir_matricula(con, gid)
        sugeridas += 1 if sugestao else 0
    return {"importacao_id": importacao_id, "geometrias": criadas, "sha256": sha, "formato": formato,
            "origem": origem, "epsg": sistema["epsg"], "camada": escolhida["nome"], "avisos": avisos,
            "sugeridas": sugeridas, "com_erro": sum(1 for p in prontas if tem_erro(p["achados"]))}


def sugerir_matricula(con, geometria_id: int) -> dict | None:
    """Põe a matrícula que o ATRIBUTO do arquivo cita como SUGESTÃO (`matricula_id`), se houver só uma ficha.

    Sugestão não adota: a geometria continua PENDENTE. Devolve a ficha sugerida, ou `None`.
    """
    bd = banco(con)
    linha = bd.um("SELECT id, matricula_declarada, matricula_id, situacao FROM ri_geometrias WHERE id = %s",
                  (int(geometria_id),))
    if not linha or linha["situacao"] != PENDENTE or linha["matricula_id"] or not linha["matricula_declarada"]:
        return None
    fichas = achar_matriculas(con, linha["matricula_declarada"])
    if len(fichas) != 1:
        return None
    bd.escrever("UPDATE ri_geometrias SET matricula_id = %s WHERE id = %s", (fichas[0]["id"], int(geometria_id)))
    return fichas[0]


# --------------------------------------------------------------- o memorial da matrícula

def _area_registrada_m2(ficha: dict) -> float | None:
    return MAPA._metros(ficha.get("area_valor"), ficha.get("area_unidade")) if ficha.get("area_valor") else None


def _ficha_do_memorial(con, matricula_id: int) -> dict:
    ficha = banco(con).um(
        f"""SELECT m.id, m.numero, m.livro, m.situacao, m.encerrada, m.teor, m.teor_formato, m.descricao_perimetro,
                   m.area_valor, m.area_unidade, {MAPA._MATRICULA} AS rotulo
              FROM ri_matriculas m WHERE m.id = %s""", (int(matricula_id),))
    if not ficha:
        raise GeoImportError("Esta matrícula não existe.")
    return dict(ficha)


def ler_memorial_da_matricula(con, matricula_id: int, *,
                              tolerancia_fechamento_m: float = GEO.TOLERANCIA_FECHAMENTO_M) -> dict:
    """Lê o memorial do teor da matrícula e mede cada gleba — **sem gravar nada**.

    Devolve `{matricula, rotulo, fonte, sha256, sistema, glebas, avisos, soma_ha, registrada_ha}`. Cada gleba:
    `{indice, rotulo_no_texto, geometria, medidas, achados, vertices, texto, area_ha, comparacao}` (`geometria` é
    a de `ri_geometrias`: lista de polígonos de anéis lon/lat). Recusa (`GeoImportError`) a matrícula encerrada,
    o texto em SAD 69 / Córrego Alegre e o que não tem vértices legíveis — sempre dizendo o motivo.
    """
    ficha = _ficha_do_memorial(con, matricula_id)
    if not esta_aberta(ficha):
        raise GeoImportError(f"A matrícula {ficha['rotulo']} está encerrada ou anulada: não vai ao Mapa.")
    leitura = fonte = texto = None
    for nome_da_fonte, bruto in (("teor", ficha.get("teor")), ("descricao_perimetro", ficha.get("descricao_perimetro"))):
        candidato = FORM.texto_do_memorial(bruto, ficha.get("teor_formato") if nome_da_fonte == "teor" else None)
        lido = FORM.ler_memorial(candidato) if candidato else None
        if lido and any(g["anel"] for g in lido["glebas"]):
            leitura, fonte, texto = lido, nome_da_fonte, candidato
            break
    if not leitura:
        raise GeoImportError(
            f"O texto da matrícula {ficha['rotulo']} não traz vértices com Longitude e Latitude em graus, minutos e "
            f"segundos (no teor nem na descrição do perímetro). Esta entrada só lê o memorial nesse formato.")
    sistema = FORM.sistema_do_texto(texto)
    if sistema["recusa"]:
        raise GeoImportError(f"Matrícula {ficha['rotulo']}: {sistema['recusa']}")
    avisos: list[str] = []
    if sistema["aviso"]:
        avisos.append(sistema["aviso"])
    if leitura["antes_da_primeira"]:
        avisos.append(f"{leitura['antes_da_primeira']} coordenada(s) estão no texto antes da primeira descrição de "
                      f"perímetro e não entraram em polígono nenhum: confira se não é outra gleba.")
    bd = banco(con)
    atos = bd.um("SELECT count(*) AS n FROM ri_atos WHERE matricula_id = %s AND cancelado = 0 "
                 "AND teor ILIKE %s", (int(matricula_id), "%Longitude%"))
    com_atos = bool(atos and int(atos["n"]))
    glebas: list[dict] = []
    for g in leitura["glebas"]:
        if not g["anel"]:
            avisos.append(f"A gleba {g['indice']} do texto tem menos de 3 vértices legíveis e não virou polígono.")
            continue
        geometria = [[g["anel"]]]
        try:
            medidas = GEO.analisar(geometria, tolerancia_fechamento_m=tolerancia_fechamento_m)
        except GEO.GeoErro as erro:
            avisos.append(f"A gleba {g['indice']} do texto não pôde ser medida: {erro}")
            continue
        achados = list(medidas["achados"])
        if g["ilegiveis"]:
            achados.append({"codigo": "COORDENADA_ILEGIVEL", "nivel": GEO.ERRO, "texto": (
                f"O texto desta gleba tem {g['ilegiveis']} coordenada(s) que não se leem em graus, minutos e "
                f"segundos: o polígono está incompleto e não se adota.")})
        if g["sem_hemisferio"]:
            achados.append({"codigo": "SEM_HEMISFERIO", "nivel": GEO.ERRO, "texto": (
                "Há coordenada sem sinal e sem N/S/L/O: não se sabe o hemisfério, e o sistema não adivinha.")})
        if g["com_ruido"]:
            achados.append({"codigo": "COORDENADA_COM_TEXTO_NO_MEIO", "nivel": GEO.AVISO, "texto": (
                f"{g['com_ruido']} coordenada(s) têm texto no meio, entre o rótulo e os graus (rodapé de página, "
                f"em geral): foram lidas assim mesmo, e o texto-fonte mostra o trecho. Confira os vértices.")})
        if g["fechado_pelo_sistema"] and not g["volta_ao_primeiro"]:
            achados.append({"codigo": "ANEL_FECHADO_PELO_SISTEMA", "nivel": GEO.AVISO, "texto": (
                "O texto desta gleba não volta ao primeiro vértice: o sistema fechou o anel. Confira se o memorial "
                "não está cortado.")})
        if leitura["antes_da_primeira"]:
            achados.append({"codigo": "COORDENADAS_FORA_DA_DESCRICAO", "nivel": GEO.AVISO, "texto": (
                "O texto tem coordenadas antes da primeira descrição de perímetro, que ficaram de fora.")})
        if sistema["aviso"]:
            achados.append({"codigo": "SISTEMA_DO_TEXTO", "nivel": GEO.AVISO, "texto": sistema["aviso"]})
        if com_atos:
            achados.append({"codigo": "ATO_COM_COORDENADAS", "nivel": GEO.AVISO, "texto": (
                "Há ato (registro ou averbação) desta matrícula com coordenadas no teor: confira qual descrição "
                "está em vigor — este polígono saiu do texto da ficha.")})
        comparacao = comparar_areas({"area_geodesica_m2": medidas["area_m2"], "area_valor": ficha.get("area_valor"),
                                     "area_unidade": ficha.get("area_unidade")})
        glebas.append({"indice": g["indice"], "rotulo_no_texto": g["rotulo_no_texto"], "geometria": geometria,
                       "medidas": medidas, "achados": achados, "vertices": g["vertices"], "texto": g["texto"],
                       "area_ha": GEO.hectares(medidas["area_m2"]), "comparacao": comparacao})
    if not glebas:
        raise GeoImportError(f"Matrícula {ficha['rotulo']}: nenhuma gleba do texto virou polígono. "
                             + " ".join(avisos))
    registrada = _area_registrada_m2(ficha)
    soma_m2 = sum(g["medidas"]["area_m2"] for g in glebas)
    if len(glebas) > 1:
        # `conferir`: a matrícula tem várias glebas; a área registrada pode ser da soma, de uma só, ou de outra coisa.
        def ha(m2: float) -> str:
            return f"{GEO.hectares(m2):.4f}".replace(".", ",")
        if registrada:
            dif = 100.0 * (soma_m2 - registrada) / registrada
            dif = f"{0.0 if abs(dif) < 0.005 else dif:+.2f}".replace(".", ",")
            frase_soma = (f"A soma das {len(glebas)} glebas é {ha(soma_m2)} ha, contra {ha(registrada)} ha "
                          f"registrados ({dif}%).")
        else:
            frase_soma = f"A soma das {len(glebas)} glebas é {ha(soma_m2)} ha; a ficha não tem área para comparar."
        for g in glebas:
            g["achados"].append({"codigo": "VARIAS_GLEBAS", "nivel": GEO.AVISO, "texto": (
                f"CONFERIR: o texto da matrícula tem {len(glebas)} glebas, e este é um polígono por gleba (os "
                f"vértices de glebas diferentes não se juntam). {frase_soma}")})
    return {"matricula": ficha, "rotulo": ficha["rotulo"], "fonte": fonte,
            "sha256": hashlib.sha256(texto.encode("utf-8")).hexdigest(), "sistema": sistema["sistema"],
            "glebas": glebas, "avisos": avisos, "soma_ha": GEO.hectares(soma_m2),
            "registrada_ha": GEO.hectares(registrada) if registrada else None}


def extrair_memorial(con, matricula_id: int, *, quem: str | None, quem_id: int | None, agora: str,
                     tolerancia_fechamento_m: float = GEO.TOLERANCIA_FECHAMENTO_M) -> dict:
    """Guarda as glebas do memorial da matrícula como polígonos PENDENTES, com a matrícula como SUGESTÃO.

    Nada é adotado. A origem é «memorial da matrícula N»: em `origem_atributos` ficam o texto-fonte da gleba, os
    vértices como vieram (nome e coordenadas escritas) e de qual campo da ficha saiu. Extrair de novo o **mesmo
    texto** é recusado (já está guardado — adotado, pendente ou descartado); texto que mudou extrai de novo.
    Devolve `{importacao_id, geometrias, glebas, avisos, matricula, sha256}`.
    """
    plano = ler_memorial_da_matricula(con, matricula_id, tolerancia_fechamento_m=tolerancia_fechamento_m)
    bd = banco(con)
    rotulo = plano["rotulo"]
    ja = bd.um("""SELECT g.id, g.situacao FROM ri_geo_importacoes i JOIN ri_geometrias g ON g.importacao_id = i.id
                   WHERE i.formato = 'MEMORIAL' AND i.arquivo_sha256 = %s AND g.matricula_declarada = %s
                   ORDER BY g.id LIMIT 1""", (plano["sha256"], rotulo))
    if ja:
        raise GeoImportError(f"O memorial da matrícula {rotulo} já foi extraído (polígono nº {ja['id']}, "
                             f"{str(ja['situacao']).lower()}). Se o texto da matrícula mudou, extraia de novo.")
    importacao_id = int(bd.escrever(
        """INSERT INTO ri_geo_importacoes
              (arquivo_nome, arquivo_sha256, formato, camada, epsg, origem, levantamento, responsavel_tecnico,
               n_feicoes, avisos, importado_por, importado_por_id, importado_em)
           VALUES (%s,%s,'MEMORIAL',NULL,4674,'MEMORIAL',NULL,NULL,%s,%s,%s,%s,%s) RETURNING id""",
        (_texto(f"memorial da matrícula {rotulo}", 200), plano["sha256"], len(plano["glebas"]),
         json.dumps(plano["avisos"], ensure_ascii=False) if plano["avisos"] else None, quem, quem_id, agora))[0]["id"])
    criadas: list[int] = []
    for g in plano["glebas"]:
        medidas = g["medidas"]
        caixa = medidas["caixa"] or GEO.caixa(g["geometria"])
        atributos = {"matricula": rotulo, "campo_da_ficha": plano["fonte"], "gleba": g["indice"],
                     "de_n_glebas": len(plano["glebas"]), "rotulo_no_texto": g["rotulo_no_texto"],
                     "sistema_no_texto": plano["sistema"] or "não diz", "vertices": g["vertices"],
                     "texto_fonte": g["texto"]}
        criadas.append(int(bd.escrever(
            """INSERT INTO ri_geometrias
                  (importacao_id, matricula_id, situacao, origem, origem_feicao, origem_atributos,
                   matricula_declarada, geom_wkb_hex, min_lon, min_lat, max_lon, max_lat, area_geodesica_m2,
                   perimetro_m, vertices, fechamento_m, achados, criado_em)
               VALUES (%s,%s,'PENDENTE','MEMORIAL',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (importacao_id, plano["matricula"]["id"], g["indice"] - 1, json.dumps(atributos, ensure_ascii=False),
             rotulo, FORM.wkb_de_geometria(g["geometria"]).hex(), caixa[0], caixa[1], caixa[2], caixa[3],
             medidas["area_m2"], medidas["perimetro_m"], medidas["vertices"], medidas["fechamento_m"],
             json.dumps(g["achados"], ensure_ascii=False), agora))[0]["id"]))
    return {"importacao_id": importacao_id, "geometrias": criadas, "glebas": len(plano["glebas"]),
            "avisos": plano["avisos"], "matricula": rotulo, "sha256": plano["sha256"],
            "com_erro": sum(1 for g in plano["glebas"] if tem_erro(g["achados"]))}


def matriculas_com_memorial(con) -> list[dict]:
    """As matrículas ABERTAS cujo teor ou descrição do perímetro cita «Longitude» — candidatas à extração."""
    linhas = banco(con).ler(
        f"""SELECT m.id, m.encerrada, m.situacao, {MAPA._MATRICULA} AS rotulo FROM ri_matriculas m
             WHERE (m.teor ILIKE %s OR m.descricao_perimetro ILIKE %s) ORDER BY m.id""", ("%Longitude%", "%Longitude%"))
    return [dict(l) for l in linhas if esta_aberta(l)]


def extrair_memoriais_em_lote(con, *, quem: str | None, quem_id: int | None, agora: str,
                              tolerancia_fechamento_m: float = GEO.TOLERANCIA_FECHAMENTO_M) -> dict:
    """Extrai de todas as matrículas abertas com memorial. Guarda PENDENTES; **não adota nenhuma**.

    Devolve `{extraidas: [rotulo], poligonos, recusadas: [{matricula, motivo}]}`: o que não deu certo vem com o motivo.
    """
    extraidas: list[str] = []
    recusadas: list[dict] = []
    poligonos = 0
    for ficha in matriculas_com_memorial(con):
        try:
            resumo = extrair_memorial(con, ficha["id"], quem=quem, quem_id=quem_id, agora=agora,
                                      tolerancia_fechamento_m=tolerancia_fechamento_m)
        except GeoImportError as erro:
            recusadas.append({"matricula": ficha["rotulo"], "motivo": str(erro)})
            continue
        extraidas.append(ficha["rotulo"])
        poligonos += len(resumo["geometrias"])
    return {"extraidas": extraidas, "poligonos": poligonos, "recusadas": recusadas}


def adotar_memoriais_sem_aviso(con, cfg: dict, *, quem: str | None, quem_id: int | None, agora: str) -> dict:
    """Adota, em lote, os polígonos PENDENTES de memorial que **não têm aviso nenhum**. Os outros ficam para a pessoa.

    Para ir, o polígono precisa: não ter achado (nem aviso) guardado; ter matrícula aberta e **sem vigente**; a
    área geodésica **bater** com a registrada (dentro da tolerância da casa); não se sobrepor a nenhum vigente;
    e não ser uma de várias glebas do mesmo memorial. Devolve `{adotadas, deixadas}`, `deixadas` com o motivo.
    """
    bd = banco(con)
    adotadas: list[int] = []
    deixadas: list[dict] = []
    for geo in bd.ler("SELECT * FROM ri_geometrias WHERE situacao = 'PENDENTE' AND origem = 'MEMORIAL' "
                      "AND matricula_id IS NOT NULL ORDER BY id"):
        def deixar(motivo: str) -> None:
            deixadas.append({"id": int(geo["id"]), "matricula": geo["matricula_declarada"], "motivo": motivo})

        achados = achados_da_linha(geo)
        ficha = bd.um("SELECT m.id, m.encerrada, m.situacao, m.area_valor, m.area_unidade FROM ri_matriculas m "
                      "WHERE m.id = %s", (geo["matricula_id"],))
        if achados:
            deixar("tem aviso ou erro")
        elif not ficha or not esta_aberta(ficha):
            deixar("matrícula encerrada ou inexistente")
        elif bd.um("SELECT 1 FROM ri_geometrias WHERE matricula_id = %s AND situacao = 'VIGENTE'",
                   (geo["matricula_id"],)):
            deixar("a matrícula já tem polígono vigente")
        elif bd.um("SELECT 1 FROM ri_geometrias WHERE importacao_id = %s AND id <> %s AND situacao <> 'DESCARTADA'",
                   (geo["importacao_id"], geo["id"])):
            deixar("o memorial tem mais de uma gleba")
        else:
            comparacao = comparar_areas({**geo, "area_valor": ficha["area_valor"],
                                         "area_unidade": ficha["area_unidade"]}, cfg["divergencia_area_pct"])
            if comparacao["bate"] is None:
                deixar("a ficha não tem área para comparar")
            elif comparacao["bate"] is False:
                deixar(f"a área não bate com a registrada ({comparacao['diferenca_pct']:+.2f}%)".replace(".", ","))
            elif sobreposicoes(con, geo["id"], tolerancia_m2=cfg["tolerancia_sobreposicao_m2"]):
                deixar("sobrepõe outro polígono vigente")
            else:
                adotar(con, geo["id"], geo["matricula_id"], quem=quem, quem_id=quem_id, agora=agora)
                adotadas.append(int(geo["id"]))
    return {"adotadas": adotadas, "deixadas": deixadas}


# --------------------------------------------------------------- adotar, descartar

def adotar(con, geometria_id: int, matricula_id: int, *, quem: str | None, quem_id: int | None,
           agora: str) -> dict:
    """Faz da geometria o polígono VIGENTE da matrícula. O vigente que havia passa a SUBSTITUIDA, e fica.

    Recusa (`GeoImportError`) a geometria com ERRO — não é um polígono que se possa levar ao Mapa —, a
    descartada e a matrícula que não existe. Matrícula encerrada **adota com aviso** (o polígono fica guardado,
    mas não vai ao arquivo). Devolve `{matricula, substituiu, avisos}`.
    """
    bd = banco(con)
    geo = bd.um("SELECT * FROM ri_geometrias WHERE id = %s", (int(geometria_id),))
    if not geo:
        raise GeoImportError("Este polígono não existe.")
    if geo["situacao"] in (DESCARTADA, SUBSTITUIDA):
        raise GeoImportError(f"Este polígono está {geo['situacao'].lower()}: importe o arquivo de novo para adotá-lo.")
    if tem_erro(achados_da_linha(geo)):
        raise GeoImportError("Este polígono tem erro (fechamento, cruzamento ou vértices): não se adota. "
                             "Corrija o desenho no QGIS e importe de novo.")
    ficha = bd.um(f"SELECT m.id, m.encerrada, m.situacao, {MAPA._MATRICULA} AS rotulo, m.numero "
                  f"FROM ri_matriculas m WHERE m.id = %s", (int(matricula_id),))
    if not ficha:
        raise GeoImportError("Esta matrícula não existe.")
    avisos: list[str] = []
    if not esta_aberta(ficha):
        avisos.append(f"A matrícula {ficha['rotulo']} está encerrada ou anulada: o polígono fica guardado, mas "
                      f"não vai ao arquivo do Mapa.")
    if geo["origem"] == "MEMORIAL":
        irmas = bd.um("SELECT count(*) AS n FROM ri_geometrias WHERE importacao_id = %s AND id <> %s "
                      "AND situacao <> 'DESCARTADA'", (geo["importacao_id"], int(geometria_id)))
        if irmas and int(irmas["n"]):
            avisos.append("Este polígono é uma de várias glebas do mesmo memorial, e o Mapa guarda um polígono por "
                          "matrícula: adotá-lo substitui o que já for o vigente desta matrícula.")
    vigente = bd.um("SELECT id FROM ri_geometrias WHERE matricula_id = %s AND situacao = 'VIGENTE' AND id <> %s",
                    (int(matricula_id), int(geometria_id)))
    if vigente:
        bd.escrever("UPDATE ri_geometrias SET situacao = 'SUBSTITUIDA', substituida_por = %s, substituida_em = %s "
                    "WHERE id = %s", (int(geometria_id), agora, vigente["id"]))
    bd.escrever("""UPDATE ri_geometrias SET matricula_id = %s, situacao = 'VIGENTE', adotada_por = %s,
                          adotada_por_id = %s, adotada_em = %s WHERE id = %s""",
                (int(matricula_id), quem, quem_id, agora, int(geometria_id)))
    return {"matricula": ficha["rotulo"], "substituiu": int(vigente["id"]) if vigente else None, "avisos": avisos}


def adotar_sugestoes(con, *, quem: str | None, quem_id: int | None, agora: str) -> dict:
    """Adota, em lote, as PENDENTES sem erro cuja matrícula sugerida ainda não tem polígono vigente.

    **Não substitui nenhum vigente**: trocar o polígono de uma matrícula é decisão por polígono. Devolve
    `{adotadas, deixadas}`, e `deixadas` diz por que cada uma ficou.
    """
    bd = banco(con)
    adotadas: list[int] = []
    deixadas: list[dict] = []
    # O memorial da matrícula tem o seu próprio lote (só o sem aviso): a sugestão dele nasce com aviso de propósito.
    for geo in bd.ler("SELECT * FROM ri_geometrias WHERE situacao = 'PENDENTE' AND matricula_id IS NOT NULL "
                      "AND origem <> 'MEMORIAL' ORDER BY id"):
        if tem_erro(achados_da_linha(geo)):
            deixadas.append({"id": geo["id"], "motivo": "tem erro"})
        elif bd.um("SELECT 1 FROM ri_geometrias WHERE matricula_id = %s AND situacao = 'VIGENTE'",
                   (geo["matricula_id"],)):
            deixadas.append({"id": geo["id"], "motivo": "a matrícula já tem polígono vigente"})
        else:
            adotar(con, geo["id"], geo["matricula_id"], quem=quem, quem_id=quem_id, agora=agora)
            adotadas.append(int(geo["id"]))
    return {"adotadas": adotadas, "deixadas": deixadas}


def descartar(con, geometria_id: int, motivo: str, *, quem: str | None, agora: str) -> None:
    """Marca como DESCARTADA, com o motivo. O polígono fica no banco. O vigente não se descarta: troca-se por outro."""
    motivo = _texto(motivo, 400) or ""
    if len(re.sub(r"[^A-Za-zÀ-ÿ]", "", motivo)) < 5:
        raise GeoImportError("Diga o motivo do descarte (pelo menos uma frase curta).")
    bd = banco(con)
    geo = bd.um("SELECT id, situacao FROM ri_geometrias WHERE id = %s", (int(geometria_id),))
    if not geo:
        raise GeoImportError("Este polígono não existe.")
    if geo["situacao"] == VIGENTE:
        raise GeoImportError("O polígono vigente de uma matrícula não se descarta: adote outro no lugar dele.")
    if geo["situacao"] == DESCARTADA:
        return
    bd.escrever("UPDATE ri_geometrias SET situacao = 'DESCARTADA', descartada_motivo = %s, adotada_por = %s, "
                "adotada_em = %s WHERE id = %s", (f"{motivo} (por {quem or 'sem nome'})", quem, agora,
                                                  int(geometria_id)))


# --------------------------------------------------------------- ler

def lista(con, *, situacoes: Sequence[str] | None = None) -> list[dict]:
    """Os polígonos com a matrícula (`rotulo`) e a área registrada, para a tela. Sem o WKB (é pesado)."""
    filtro, parametros = "", []
    if situacoes:
        filtro, parametros = "WHERE g.situacao = ANY(%s)", [list(situacoes)]
    linhas = banco(con).ler(
        f"""SELECT g.id, g.importacao_id, g.matricula_id, g.situacao, g.origem, g.origem_feicao,
                   g.matricula_declarada, g.levantamento, g.responsavel_tecnico, g.sigef_codigo,
                   g.area_geodesica_m2, g.perimetro_m, g.vertices, g.fechamento_m, g.achados, g.adotada_por,
                   g.adotada_em, g.criado_em, g.descartada_motivo, g.substituida_por, i.arquivo_nome,
                   i.importado_por, i.importado_em, m.area_valor, m.area_unidade, m.encerrada, m.situacao AS
                   situacao_da_matricula, {MAPA._MATRICULA} AS rotulo
              FROM ri_geometrias g
              JOIN ri_geo_importacoes i ON i.id = g.importacao_id
              LEFT JOIN ri_matriculas m ON m.id = g.matricula_id
              {filtro}
             ORDER BY g.id DESC""", parametros or None)
    return [dict(l) for l in linhas]


def comparar_areas(linha: dict, divergencia_pct: float = DIVERGENCIA_PADRAO_PCT) -> dict:
    """A área geodésica ao lado da registrada: `{geodesica_ha, registrada_ha, diferenca_ha, diferenca_pct, bate}`.

    A registrada vem da régua da casa (`ri_mapa_onr`), e fica `None` quando a ficha não a tem ou escreve de um jeito
    que a régua não decide. `bate` é `None` sem registrada; senão, vale quando a diferença não passa de
    `divergencia_pct` — valor de trabalho da casa, e não de norma.
    """
    geodesica_m2 = float(linha["area_geodesica_m2"])
    registrada_m2 = MAPA._metros(linha.get("area_valor"), linha.get("area_unidade")) \
        if linha.get("area_valor") else None
    saida = {"geodesica_ha": GEO.hectares(geodesica_m2), "registrada_ha": None, "diferenca_ha": None,
             "diferenca_pct": None, "bate": None}
    if registrada_m2:
        diferenca = geodesica_m2 - registrada_m2
        saida.update(registrada_ha=GEO.hectares(registrada_m2), diferenca_ha=GEO.hectares(diferenca),
                     diferenca_pct=round(100.0 * diferenca / registrada_m2, 3),
                     bate=abs(100.0 * diferenca / registrada_m2) <= divergencia_pct)
    return saida


def geometria_da_linha(linha: dict) -> list:
    """A geometria (lista de polígonos, lon/lat) de uma linha de `ri_geometrias` lida com `SELECT *`."""
    return _geometria_do_wkb_hex(linha["geom_wkb_hex"])


def da_matricula(con, matricula_id: int) -> dict:
    """`{vigente, historico}` de uma matrícula: o polígono de hoje e os que já foram."""
    linhas = banco(con).ler("SELECT * FROM ri_geometrias WHERE matricula_id = %s ORDER BY id DESC",
                            (int(matricula_id),))
    return {"vigente": next((l for l in linhas if l["situacao"] == VIGENTE), None),
            "historico": [l for l in linhas if l["situacao"] != VIGENTE]}


# --------------------------------------------------------------- sobreposição

def sobreposicoes(con, geometria_id: int, *, tolerancia_m2: float = GEO.TOLERANCIA_SOBREPOSICAO_M2) -> list[dict]:
    """Com quem este polígono se sobrepõe, entre os VIGENTES: `[{id, matricula, area_m2, pct_deste, pct_do_outro}]`.

    Só entram os que se sobrepõem em mais de `tolerancia_m2`. `area_m2` é `None` quando o par é grande demais
    para conferir aqui — a tela diz que não conferiu. Um polígono vigente não se compara com ele mesmo.
    """
    bd = banco(con)
    este = bd.um("SELECT * FROM ri_geometrias WHERE id = %s", (int(geometria_id),))
    if not este:
        return []
    geometria = geometria_da_linha(este)
    candidatos = bd.ler(
        f"""SELECT g.*, {MAPA._MATRICULA} AS rotulo FROM ri_geometrias g
              LEFT JOIN ri_matriculas m ON m.id = g.matricula_id
             WHERE g.situacao = 'VIGENTE' AND g.id <> %s
               AND g.min_lon <= %s AND g.max_lon >= %s AND g.min_lat <= %s AND g.max_lat >= %s""",
        (int(geometria_id), este["max_lon"], este["min_lon"], este["max_lat"], este["min_lat"]))
    achadas = []
    for outro in candidatos:
        area = GEO.area_da_interseccao_m2(geometria, geometria_da_linha(outro))
        if area is None:
            achadas.append({"id": outro["id"], "matricula": outro["rotulo"], "area_m2": None,
                            "pct_deste": None, "pct_do_outro": None})
        elif area > tolerancia_m2:
            achadas.append({"id": outro["id"], "matricula": outro["rotulo"], "area_m2": area,
                            "pct_deste": round(100.0 * area / float(este["area_geodesica_m2"]), 3),
                            "pct_do_outro": round(100.0 * area / float(outro["area_geodesica_m2"]), 3)})
    return sorted(achadas, key=lambda a: -(a["area_m2"] or 0.0))


# --------------------------------------------------------------- a conferência antes do arquivo

def conferir_para_o_mapa(con, cfg: dict) -> dict:
    """O que iria e o que ficaria de fora do arquivo, com o motivo de cada um.

    Devolve `{itens: [...], vao: n, ficam: n}`. Cada item: `{id, matricula, matricula_id, achados, vai}`, com
    `achados` já somados aos da conferência de hoje: matrícula inexistente ou fechada (ERRO), sobreposição,
    área que não bate, dono ou CNS em branco (AVISO). **Só os VIGENTES** entram.
    """
    bd = banco(con)
    vigentes = bd.ler("SELECT * FROM ri_geometrias WHERE situacao = 'VIGENTE' ORDER BY id")
    dados = {d["matricula"]: d for d in MAPA.dados_do_mapa(con)}
    itens: list[dict] = []
    for geo in vigentes:
        achados = [dict(a) for a in achados_da_linha(geo)]
        ficha = bd.um(f"SELECT m.id, m.encerrada, m.situacao, {MAPA._MATRICULA} AS rotulo, m.area_valor, "
                      f"m.area_unidade FROM ri_matriculas m WHERE m.id = %s", (geo["matricula_id"],))
        rotulo = ficha["rotulo"] if ficha else None
        if not ficha:
            achados.append({"codigo": "SEM_MATRICULA", "nivel": GEO.ERRO, "texto": "A matrícula deste polígono "
                            "não existe mais."})
        elif not esta_aberta(ficha) or rotulo not in dados:
            achados.append({"codigo": "MATRICULA_FECHADA", "nivel": GEO.ERRO,
                            "texto": f"A matrícula {rotulo} está encerrada ou anulada: não vai ao Mapa."})
        else:
            atributos = dados[rotulo]
            if not atributos["proprietario"]:
                achados.append({"codigo": "SEM_DONO", "nivel": GEO.AVISO,
                                "texto": "A matrícula não tem proprietário ativo: PROPRIETAR vai em branco."})
            if not atributos["cns"]:
                achados.append({"codigo": "SEM_CNS", "nivel": GEO.AVISO,
                                "texto": "O CNS da serventia não está nas Configurações: CNS vai em branco."})
            comparacao = comparar_areas({**geo, **{"area_valor": ficha["area_valor"],
                                                   "area_unidade": ficha["area_unidade"]}},
                                        cfg["divergencia_area_pct"])
            if comparacao["bate"] is False:
                achados.append({"codigo": "AREA_NAO_BATE", "nivel": GEO.AVISO,
                                "texto": f"A área geodésica ({comparacao['geodesica_ha']:.4f} ha) difere da "
                                         f"registrada ({comparacao['registrada_ha']:.4f} ha) em "
                                         f"{comparacao['diferenca_pct']:+.2f}%.".replace(".", ",")})
            elif comparacao["bate"] is None:
                achados.append({"codigo": "SEM_AREA_REGISTRADA", "nivel": GEO.AVISO,
                                "texto": "A ficha não tem área que a régua da casa decida: nada a comparar."})
        if not tem_erro(achados):
            for s in sobreposicoes(con, geo["id"], tolerancia_m2=cfg["tolerancia_sobreposicao_m2"]):
                achados.append({"codigo": "SOBREPOSICAO", "nivel": GEO.AVISO,
                                "texto": ("Sobrepõe a matrícula %s em %s m² (%s%% deste, %s%% da outra)." % (
                                    s["matricula"], f"{s['area_m2']:,.1f}".replace(",", "."),
                                    f"{s['pct_deste']:.2f}".replace(".", ","),
                                    f"{s['pct_do_outro']:.2f}".replace(".", ",")))
                                if s["area_m2"] is not None else
                                f"Não foi possível conferir a sobreposição com a matrícula {s['matricula']}: "
                                f"os dois polígonos são grandes demais para a conta feita aqui."})
        itens.append({"id": geo["id"], "matricula": rotulo, "matricula_id": geo["matricula_id"],
                      "achados": achados, "vai": not tem_erro(achados)})
    return {"itens": itens, "vao": sum(1 for i in itens if i["vai"]), "ficam": sum(1 for i in itens if not i["vai"])}


# --------------------------------------------------------------- o arquivo

def area_para_o_arquivo(regra: str, registrada_ha: float | None, geodesica_ha: float) -> float | None:
    """O `AREA_HA` do arquivo, pela regra que o oficial escolheu. `None` = vazio no arquivo."""
    if regra == REGRA_GEODESICA:
        return geodesica_ha
    if regra == REGRA_REGISTRADA:
        return registrada_ha
    if regra == REGRA_PLUGIN:
        return registrada_ha if registrada_ha is not None else geodesica_ha
    raise GeoImportError("A regra da área do arquivo ainda não foi escolhida.")


def montar_feicoes(con, cfg: dict) -> dict:
    """As feições do arquivo — `[{geometria, MATRICULA, CNS, PROPRIETAR, AREA_HA}]` — e o que ficou de fora.

    Exige a regra da área escolhida (`ri_mapa_area_regra`). Devolve `{feicoes, conferencia}`; `conferencia` é a
    de `conferir_para_o_mapa`, para a tela mostrar o que foi e o que não foi.
    """
    if cfg["regra_da_area"] not in REGRAS_DA_AREA:
        raise GeoImportError("Antes de gerar o arquivo, o oficial precisa escolher qual área vai em AREA_HA "
                             "(a registrada ou a geodésica).")
    conferencia = conferir_para_o_mapa(con, cfg)
    bd = banco(con)
    dados = {d["matricula"]: d for d in MAPA.dados_do_mapa(con)}
    feicoes: list[dict] = []
    for item in conferencia["itens"]:
        if not item["vai"]:
            continue
        geo = bd.um("SELECT * FROM ri_geometrias WHERE id = %s", (item["id"],))
        atributos = dados[item["matricula"]]
        area = area_para_o_arquivo(cfg["regra_da_area"], atributos["area_ha"],
                                   GEO.hectares(float(geo["area_geodesica_m2"])))
        feicoes.append({"geometria": geometria_da_linha(geo), "MATRICULA": atributos["matricula"],
                        "CNS": atributos["cns"], "PROPRIETAR": atributos["proprietario"], "AREA_HA": area})
    return {"feicoes": feicoes, "conferencia": conferencia}


def gerar_gpkg(con, cfg: dict) -> tuple[bytes, dict]:
    """`(arquivo .gpkg, conferência)`. Ver `montar_feicoes`."""
    pronto = montar_feicoes(con, cfg)
    if not pronto["feicoes"]:
        raise GeoImportError("Nenhum polígono vigente pode ir ao arquivo. Veja a conferência.")
    return FORM.escrever_gpkg(pronto["feicoes"]), pronto["conferencia"]


def gerar_shapefile(con, cfg: dict) -> tuple[bytes, dict, list[str]]:
    """`(.zip do Shapefile, conferência, avisos do corte dos campos)`."""
    pronto = montar_feicoes(con, cfg)
    if not pronto["feicoes"]:
        raise GeoImportError("Nenhum polígono vigente pode ir ao arquivo. Veja a conferência.")
    conteudo, avisos = FORM.escrever_shapefile(pronto["feicoes"])
    return conteudo, pronto["conferencia"], avisos
