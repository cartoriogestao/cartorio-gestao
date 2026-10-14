"""
CTP — Comunicacao de Transacoes as Prefeituras.

O QUE E
    Arquivo mensal que o cartorio transmite a CENSEC, e por meio dela aos
    municipios, com todas as transacoes imobiliarias do mes. E o cumprimento do
    dever de comunicar ao Municipio as transacoes imobiliarias (Lei 8.935/1994,
    art. 30, XI), canalizado pelo modulo CTP da CENSEC por forca do Provimento
    CNJ 174/2024.

DE ONDE VEIO O LAYOUT
    Da especificacao publicada pelo CNB-CF ("CTP - Especificacao dos campos de
    carga", versao 1.3, de 24/10/2025), que por sua vez segue o Manual da DOI
    v1.1 de 30/04/2025. Os codigos das tabelas de dominio abaixo sao os de la.

DUAS RESSALVAS QUE PRECISAM SER LIDAS ANTES DE USAR
    1. Na especificacao publicada, a tabela de dominio de `tipoServico` traz
       uma unica opcao — "1 - Notarial" — e a de `tipoAto` traz "Escritura" e
       "Procuracao". O texto do proprio documento fala em "tres tipos de
       servico" e ha campos claramente registrais (CNM, transcricao, data de
       lavratura/registro/averbacao), mas os codigos registrais nao estao
       publicados. Por isso `tipoServico` e `tipoAto` saem configuraveis, com
       o valor notarial como padrao. CONFERIR COM A CENSEC ANTES DA PRIMEIRA
       REMESSA.
    2. Nada aqui transmite. Gera o arquivo JSON para conferencia e envio pela
       tela da CENSEC. Transmissao por API exigiria credencial da serventia.

O QUE O SISTEMA NAO TEM E PRECISA SER DIGITADO
    Valor do negocio, base de calculo do ITBI/ITCMD, forma de pagamento, data
    do negocio juridico e percentual transacionado nao estao na matricula.
    Sao digitados na tela da CTP e guardados em ri_ctp_itens — nunca no teor
    do ato, que e imutavel.
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from ri_naturezas import operacao_ctp as operacao_sauin

# ---------------------------------------------------------------- dominios

TIPO_DECLARACAO_ORIGINAL = "0"

# O CODIGO IBGE DO MUNICIPIO que vai na CTP/DOI. Fica configuravel
# (`ri_codigo_ibge`), e nao fixo no codigo, porque o imovel pode estar em
# municipio limitrofe. Ate 11/10/2026 o padrao era o municipio desta casa
# escrito aqui; agora, sem `ri_codigo_ibge`, vale a configuracao do IBGE que a
# casa ja tem (`ibge_uf` + `ibge_municipio`) — o mesmo codigo, sem o literal
# (sanitizacao B2).
CODIGO_IBGE_PADRAO = ""


def codigo_ibge_da_casa(get_setting) -> str:
    """`ri_codigo_ibge`, ou `ibge_uf` (2) + `ibge_municipio` (5). Vazio se
    nenhum dos dois estiver configurado."""
    explicito = str(get_setting("ri_codigo_ibge", "") or "").strip()
    if explicito:
        return explicito
    uf = str(get_setting("ibge_uf", "") or "").strip()
    mun = str(get_setting("ibge_municipio", "") or "").strip()
    if uf and mun:
        return uf.zfill(2) + mun.zfill(5)
    return CODIGO_IBGE_PADRAO

TIPO_SERVICO = {"1": "Notarial"}
TIPO_ATO = {"1": "Escritura", "2": "Procuração"}

# tipoOperacaoImobiliaria. Os desativados na DOI v1.1 ficam de fora de
# proposito: oferecer na tela um codigo que a CENSEC recusa so gera retrabalho.
TIPO_OPERACAO = {
    "11": "Compra e venda",
    "13": "Permuta",
    "15": "Adjudicação",
    "19": "Dação em pagamento",
    "21": "Distrato de negócio",
    "31": "Procuração em causa própria",
    "33": "Promessa de compra e venda",
    "35": "Promessa de cessão de direitos",
    "37": "Cessão de direitos",
    "39": "Outras operações imobiliárias",
    "41": "Alienação por iniciativa particular ou leilão judicial",
    "45": "Incorporação e loteamento",
    "47": "Integralização / subscrição de capital",
    "55": "Doação em adiantamento da legítima",
    "56": "Aforamento",
    "57": "Casamento em comunhão universal de bens",
    "58": "Cisão total ou parcial",
    "59": "Compra e venda de imóvel gravado por enfiteuse",
    "60": "Concessão de direito real de uso (CDRU)",
    "61": "Concessão de uso especial para fins de moradia (CUEM)",
    "62": "Consolidação da propriedade em nome do fiduciário",
    "63": "Desapropriação para fins de reforma agrária",
    "64": "Desapropriação, exceto para reforma agrária",
    "65": "Direito de laje",
    "66": "Direito de superfície",
    "67": "Doação, exceto em adiantamento de legítima",
    "68": "Incorporação",
    "69": "Inventário",
    "70": "Partilha — separação, divórcio ou união estável",
    "71": "Retorno de capital próprio na extinção de pessoa jurídica",
    "72": "Retorno de capital próprio, exceto na extinção de pessoa jurídica",
    "73": "Título de domínio — TD",
    "74": "Usucapião",
}

FORMA_PAGAMENTO = {
    "5": "Quitado à vista",
    "7": "A prazo",
    "9": "Não se aplica",
    "10": "Quitado a prazo",
    "11": "Quitado sem informação da forma de pagamento",
}

TIPO_PARTE_TRANSACIONADA = {"1": "Percentual (%)", "2": "Área (ha/m²)"}

DESTINACAO = {"1": "Urbano", "3": "Rural"}

MOTIVO_SEM_NI = {"1": "Sem CPF/CNPJ — decisão judicial", "2": "Não consta no documento"}

REGIME_BENS = {
    "1": "Separação de bens",
    "2": "Comunhão parcial de bens",
    "3": "Comunhão universal de bens",
    "4": "Participação final nos aquestos",
    "5": "Separação obrigatória",
}

# tipoImovel. Fora os desativados na DOI v1.1.
TIPO_IMOVEL = {
    "15": "Loja", "31": "Galpão", "65": "Apartamento", "67": "Casa",
    "69": "Fazenda / sítio / chácara", "71": "Terreno / fração",
    "73": "Sala ou loja", "89": "Outros", "90": "Sala", "91": "Conjunto de salas",
    "92": "Sobreloja", "93": "Vaga de garagem", "94": "Laje",
    "95": "Estacionamento", "96": "Barraco",
}

TIPO_IMOVEL_PADRAO_RURAL = "69"
TIPO_IMOVEL_PADRAO_URBANO = "71"


# ------------------------------------------------- de que ato sai a CTP

# Modelo do sistema -> operacao imobiliaria da CTP. Modelo que nao esta aqui
# NAO gera comunicacao: hipoteca, penhora, indisponibilidade, clausulas,
# georreferenciamento e afins nao sao transacao imobiliaria.
OPERACAO_POR_MODELO = {
    "R-COMPRA-VENDA": "11",
    "R-PERMUTA": "13",
    "R-ADJUDICACAO": "15",
    "R-DOACAO": "67",
    "R-ARREMATACAO": "41",
    "R-PARTILHA": "70",
    "R-INTEGRALIZACAO": "47",
    "R-TITULO-DOMINIO": "73",
    "R-USUCAPIAO": "74",
}

# Quando o ato nao guarda o codigo do modelo — todo o acervo herdado esta
# assim — resta ler a natureza em texto livre. E palpite, e a tela diz que e.
PISTAS_NATUREZA = (
    ("compra e venda", "11"), ("compra/venda", "11"), ("permuta", "13"),
    ("adjudica", "15"), ("dacao", "19"), ("dação", "19"), ("distrato", "21"),
    ("promessa de compra", "33"), ("promessa de cess", "35"),
    ("cessao de direitos", "37"), ("cessão de direitos", "37"),
    ("arremata", "41"), ("leilao", "41"), ("leilão", "41"),
    ("loteamento", "45"), ("integraliza", "47"), ("subscri", "47"),
    ("adiantamento da legitima", "55"), ("adiantamento da legítima", "55"),
    ("enfiteuse", "59"), ("aforamento", "56"),
    ("direito real de uso", "60"), ("uso especial", "61"),
    ("consolida", "62"), ("desapropria", "64"),
    ("laje", "65"), ("superficie", "66"), ("superfície", "66"),
    ("doacao", "67"), ("doação", "67"),
    ("inventario", "69"), ("inventário", "69"),
    ("partilha", "70"), ("divorcio", "70"), ("divórcio", "70"),
    ("titulo de dominio", "73"), ("título de domínio", "73"),
    ("usucapi", "74"),
)


def _sem_acento(texto: Any) -> str:
    s = "" if texto is None else str(texto)
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def operacao_sugerida(ato: dict) -> tuple[str, str]:
    """Devolve (codigo, origem_do_palpite). Codigo vazio = nao e transacao.

    Tres caminhos, do mais confiavel para o menos:
      1. o modelo usado na lavratura — certeza;
      2. a natureza batendo exatamente com o vocabulario do SAUIN — certeza;
      3. pista no texto livre — palpite, e a tela diz que e.
    """
    codigo = (ato.get("modelo_codigo") or "").strip().upper()
    if codigo in OPERACAO_POR_MODELO:
        return OPERACAO_POR_MODELO[codigo], "modelo"

    natureza = (ato.get("natureza_titulo") or "").strip()
    if natureza:
        op = operacao_sauin(natureza)
        if op:
            return op, "sauin"
        texto = _sem_acento(natureza)
        for pista, alvo in PISTAS_NATUREZA:
            if _sem_acento(pista) in texto:
                return alvo, "natureza"
    return "", ""


# ------------------------------------------------------------- utilitarios

def so_digitos(valor: Any) -> str:
    return "".join(c for c in ("" if valor is None else str(valor)) if c.isdigit())


def _decimal(valor: Any) -> float | None:
    """Le valor monetario digitado a brasileira: 1.234,56 e 1234.56."""
    s = ("" if valor is None else str(valor)).strip()
    if not s:
        return None
    s = re.sub(r"[^\d,.\-]", "", s)
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _area(valor: Any) -> float | None:
    v = _decimal(valor)
    return v if v and v > 0 else None


def _bool(valor: Any) -> bool:
    return str(valor).strip().lower() in ("1", "true", "on", "sim", "s")


# ------------------------------------------------------------ conferencia

def conferir(ato: dict, m: dict, partes: list[dict], dados: dict) -> list[str]:
    """Lista o que impede a inclusao do ato na carga.

    Devolve texto de gente, nao nome de campo: quem le a tela e o escrevente,
    nao o programador.
    """
    faltas: list[str] = []

    if not (dados.get("operacao") or "").strip():
        faltas.append("tipo de operação imobiliária não definido")
    if not (ato.get("data_ato") or "").strip():
        faltas.append("ato sem data")
    if not (dados.get("data_negocio") or "").strip():
        faltas.append("data do negócio jurídico não informada")

    if _decimal(dados.get("valor_operacao")) is None and not _bool(dados.get("valor_operacao_nao_consta")):
        faltas.append("valor da operação não informado (ou marque «não consta»)")
    if _decimal(dados.get("valor_base_itbi")) is None and not _bool(dados.get("valor_base_itbi_nao_consta")):
        faltas.append("base de cálculo do ITBI/ITCMD não informada (ou marque «não consta»)")
    if (dados.get("forma_pagamento") or "") not in FORMA_PAGAMENTO:
        faltas.append("forma de pagamento não informada")

    if not so_digitos(m.get("numero")):
        faltas.append("matrícula sem número utilizável")
    if not (m.get("cidade") or "").strip() and not so_digitos(dados.get("codigo_ibge")):
        faltas.append("município do imóvel não identificado")

    rural = (m.get("rural_urbano") or "").upper().startswith("R")
    if rural:
        if not (m.get("incra") or m.get("ccir") or dados.get("codigo_incra")):
            faltas.append("imóvel rural sem código do INCRA")
        if not (m.get("descricao_perimetro") or m.get("logradouro") or dados.get("localizacao")):
            faltas.append("imóvel rural sem dados de localização")
    else:
        if not (m.get("logradouro") or "").strip():
            faltas.append("imóvel urbano sem logradouro")
        if not (m.get("bairro") or "").strip():
            faltas.append("imóvel urbano sem bairro")
        if not so_digitos(m.get("cep")):
            faltas.append("imóvel urbano sem CEP")

    if _area(m.get("area_valor")) is None and not _bool(dados.get("area_nao_consta")):
        faltas.append("área do imóvel não informada (ou marque «não consta»)")

    alienantes = [p for p in partes if _papel(p) == "ALIENANTE"]
    adquirentes = [p for p in partes if _papel(p) == "ADQUIRENTE"]
    if not alienantes:
        faltas.append("nenhuma parte marcada como transmitente")
    if not adquirentes:
        faltas.append("nenhuma parte marcada como adquirente")
    for p in alienantes + adquirentes:
        if not so_digitos(p.get("documento_numero")) and not (dados.get("motivo_sem_ni") or ""):
            faltas.append(f"{p.get('nome')} sem CPF/CNPJ — informe o motivo")
            break
    return faltas


def _papel(parte: dict) -> str:
    """Traduz o papel gravado na parte para o vocabulario da CTP.

    ESTA E DO REGISTRO DE IMOVEIS, E LE `ri_partes.papel` — vocabulario
    CONTROLADO, medido em 28/08/2026: `proprietario` em 3.894 das 3.992
    linhas, `adquirente` em 1, vazio em 96. Ali `proprietario` quer dizer
    «dono de registro», ao lado de `proprietario_ativo`.

    A DAS NOTAS E OUTRA — `notas_doi.lado_da_parte` —, e le a `qualificacao`
    de `nt_ato_partes`, que e CAMPO LIVRE: 24 formas em 88 linhas, com
    procurador, testemunha e representante no meio.

    AS DUAS RESPONDEM A MESMA PERGUNTA E FICAM SEPARADAS DE PROPOSITO, porque
    a mesma palavra nao quer dizer a mesma coisa nas duas tabelas: juntá-las
    faria os 3.894 donos de registro virarem alienantes de uma hora para
    outra. Ha teste que guarda a separacao — se um dia as duas tabelas
    passarem a falar a mesma lingua, junte, e apague os dois avisos juntos.
    """
    p = _sem_acento(parte.get("papel"))
    if any(t in p for t in ("transmitente", "alienante", "vendedor", "outorgante",
                            "doador", "cedente", "executado", "fiduciante")):
        return "ALIENANTE"
    if any(t in p for t in ("adquirente", "comprador", "outorgado", "donatario",
                            "cessionario", "arrematante", "adjudicat", "herdeiro",
                            "usucapiente", "fiduciario", "beneficiario")):
        return "ADQUIRENTE"
    return ""


# ------------------------------------------------------------ montagem

def _pessoa(parte: dict, dados: dict) -> dict:
    ni = so_digitos(parte.get("documento_numero"))
    reg: dict[str, Any] = {"indicadorNiIdentificado": bool(ni)}
    if ni:
        reg["ni"] = ni
    else:
        reg["motivoNaoIdentificacaoNi"] = (dados.get("motivo_sem_ni") or "2")

    participacao = _decimal(parte.get("participacao"))
    if participacao:
        reg["participacao"] = participacao
        reg["indicadorNaoConstaParticipacaoOperacao"] = False
    else:
        reg["indicadorNaoConstaParticipacaoOperacao"] = True

    # Estes quatro eram False fixo. Na CTP passava, porque a tela nao coletava
    # nenhum deles; na DOI nao passa — o manual exige que digam a verdade, e o
    # conjuge tem campo proprio de CPF e regime de bens. Agora saem do que a
    # parte trouxer, e continuam False quando ela nao trouxer nada, que e o
    # comportamento antigo.
    reg["indicadorEstrangeiro"] = _bool(parte.get("estrangeiro"))
    reg["indicadorEspolio"] = _bool(parte.get("espolio"))

    conjuge_ni = so_digitos(parte.get("conjuge_documento"))
    reg["indicadorConjuge"] = bool(conjuge_ni or parte.get("conjuge_nome"))
    if reg["indicadorConjuge"]:
        if conjuge_ni:
            reg["niConjuge"] = conjuge_ni
        if parte.get("regime_bens"):
            reg["regimeBens"] = str(parte["regime_bens"])
        reg["indicadorConjugeParticipante"] = _bool(parte.get("conjuge_participante"))

    reg["indicadorRepresentante"] = _bool(parte.get("por_representante"))
    return reg


def montar_registro(ato: dict, m: dict, partes: list[dict], dados: dict,
                    cns: str, codigo_ibge: str,
                    tipo_servico: str = "1", tipo_ato: str = "1") -> dict:
    """Monta um registro da carga CTP para um ato."""
    rural = (m.get("rural_urbano") or "").upper().startswith("R")
    numero = so_digitos(m.get("numero"))

    reg: dict[str, Any] = {
        "tipoDeclaracao": TIPO_DECLARACAO_ORIGINAL,
        "tipoServico": tipo_servico,
        "dataLavraturaRegistroAverbacao": (ato.get("data_ato") or ""),
        "tipoAto": tipo_ato,
        "numeroLivro": (m.get("livro") or "2"),
        "folha": (m.get("folha") or ""),
        "matricula": numero.rjust(7, "0")[:15],
    }
    cnm = so_digitos(m.get("cnm"))
    if len(cnm) == 16:
        reg["codigoNacionalMatricula"] = cnm

    # Operacao
    reg["dataNegocioJuridico"] = (dados.get("data_negocio") or "")
    reg["tipoOperacaoImobiliaria"] = (dados.get("operacao") or "")
    if reg["tipoOperacaoImobiliaria"] == "39" and (dados.get("descricao_outras") or "").strip():
        reg["descricaoOutrasOperacoesImobiliarias"] = dados["descricao_outras"][:30]

    valor = _decimal(dados.get("valor_operacao"))
    if valor is not None:
        reg["valorOperacaoImobiliaria"] = valor
    else:
        reg["indicadorNaoConstaValorOperacaoImobiliaria"] = True

    base = _decimal(dados.get("valor_base_itbi"))
    if base is not None:
        reg["valorBaseCalculoItbiItcmd"] = base
    else:
        reg["IndicadorNaoConstaValorBaseCalculoItbiItcmd"] = True

    forma = dados.get("forma_pagamento") or "11"
    reg["formaPagamento"] = forma
    if forma == "7":
        reg["indicadorAlienacaoFiduciaria"] = _bool(dados.get("alienacao_fiduciaria"))
        if dados.get("ultima_parcela"):
            reg["mesAnoUltimaParcela"] = dados["ultima_parcela"]
        pago = _decimal(dados.get("valor_pago_ate_ato"))
        if pago is not None:
            reg["valorPagoAteDataAto"] = pago

    reg["indicadorPermutaBens"] = _bool(dados.get("permuta"))
    dinheiro = _bool(dados.get("pagamento_dinheiro"))
    reg["indicadorPagamentoDinheiro"] = dinheiro
    if dinheiro:
        especie = _decimal(dados.get("valor_especie"))
        if especie is not None:
            reg["valorPagoMoedaCorrenteDataAto"] = especie

    reg["tipoParteTransacionada"] = dados.get("tipo_parte") or "1"
    reg["valorParteTransacionada"] = _decimal(dados.get("valor_parte")) or 100.0

    # Imovel
    ibge = so_digitos(dados.get("codigo_ibge")) or so_digitos(codigo_ibge)
    reg["destinacao"] = "3" if rural else "1"
    reg["indicadorImovelPublicoUniao"] = False
    reg["codigoIbge"] = ibge

    area = _area(m.get("area_valor")) or _area(dados.get("area"))
    if area is not None:
        reg["areaImovel"] = area
    if so_digitos(m.get("nirf")):
        reg["cib"] = so_digitos(m.get("nirf"))[:8]

    if rural:
        reg["codigoIncra"] = (so_digitos(m.get("incra")) or so_digitos(m.get("ccir")) or
                              so_digitos(dados.get("codigo_incra")))[:13]
        reg["denominacao"] = (m.get("logradouro") or dados.get("denominacao") or "")[:200]
        reg["localizacao"] = (dados.get("localizacao") or m.get("bairro") or
                              m.get("descricao_perimetro") or "")[:200]
        # DOI-Web / sample Livro 30 fls 184-192: rural leva tipoImovel (69 = fazenda/sitio/chacara).
        reg["tipoImovel"] = dados.get("tipo_imovel") or TIPO_IMOVEL_PADRAO_RURAL
    else:
        if (m.get("inscricao_municipal") or "").strip():
            reg["inscricaoMunicipal"] = m["inscricao_municipal"][:45]
        reg["indicadorAreaLoteNaoConsta"] = area is None
        construida = _area(dados.get("area_construida"))
        if construida is not None:
            reg["areaConstruida"] = construida
        reg["indicadorAreaConstruidaNaoConsta"] = construida is None
        reg["tipoImovel"] = dados.get("tipo_imovel") or TIPO_IMOVEL_PADRAO_URBANO
        reg["tipoLogradouro"] = (dados.get("tipo_logradouro") or "Rua")[:30]
        reg["nomeLogradouro"] = (m.get("logradouro") or "n/c")[:255]
        reg["numeroImovel"] = (m.get("numero_predial") or "S/N")[:10]
        if (m.get("complemento_endereco") or "").strip():
            reg["complementoEndereco"] = m["complemento_endereco"][:100]
        reg["bairro"] = (m.get("bairro") or "")[:150]
        reg["cep"] = so_digitos(m.get("cep"))[:8]

    reg["alienantes"] = [_pessoa(p, dados) for p in partes if _papel(p) == "ALIENANTE"]
    reg["adquirentes"] = [_pessoa(p, dados) for p in partes if _papel(p) == "ADQUIRENTE"]
    return reg


def gerar_carga(registros: list[dict], cns: str, competencia: str) -> str:
    """Serializa a carga. JSON identado de proposito: alguem vai conferir isto
    com os olhos antes de subir na CENSEC."""
    corpo = {
        "cns": so_digitos(cns).rjust(6, "0")[:6],
        "competencia": competencia,
        "quantidade": len(registros),
        "registros": registros,
    }
    return json.dumps(corpo, ensure_ascii=False, indent=2)


def nome_arquivo(cns: str, competencia: str) -> str:
    return f"CTP_{so_digitos(cns)}_{competencia.replace('-', '')}.json"
