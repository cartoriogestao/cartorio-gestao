"""O INDICADOR REAL EM XML — o arquivo que o ONR recebe por `POST /v1/indicador/real/upload`.

    «consigo exportar todo o indicador real num xml enquanto nao temos a api»
                                                      — o oficial, 10/10/2026

DE ONDE VEM O FORMATO
    «Manual de Integração com a API do Indicador Real», V.1, 20/07/2023, seção
    [RFI-02], lido em 10/10/2026 (cópia em
    `FONTES_EXTERNAS/onr_indicador_real/`). Até 10.000 indicadores por arquivo.

    **O MANUAL SE CONTRADIZ NOS NOMES, e vale o MODELO.** A tabela de campos diz
    `Logradouro`, `Nirf`, `SncrCcir` e, no ato, `Numero`; o «Modelo do XML»
    logo abaixo escreve `NomeLogradouro`, `NIRF`, `SNCR_CCIR` e `NumeroAto`. O
    modelo é a forma literal do arquivo, e é ele que se segue aqui — A CONFERIR
    na primeira resposta do ONR.

O CORPO É O MESMO DA API
    Este módulo não monta o indicador: recebe o `corpo` de
    `ri_onr_central.montar_indicador` e só muda a roupa (JSON → XML). Duas
    montagens divergiriam no primeiro conserto.

O QUE ELE RECUSA
    **Ato sem `DataInstrumento` ou `ValorDeclarado` não entra** — os dois são
    obrigatórios no manual, e esta casa não guarda a data do título. A lista de
    atos é opcional, e o E-Ofício mandou o indicador sem ato nenhum.

ENVIAR ESTE ARQUIVO TAMBÉM PEDE A CREDENCIAL. O manual só prevê o upload pela
API, com o mesmo token. Este módulo NÃO MANDA nada: só escreve o arquivo.
"""
from __future__ import annotations

import re
from typing import Any
from xml.sax.saxutils import escape

LIMITE_POR_ARQUIVO = 10_000

# corpo (JSON da API) → etiqueta do «Modelo do XML», na ordem do modelo.
CAMPOS = (
    ("cns", "CNS"), ("cnm", "CNM"), ("numeroRegistro", "NumeroRegistro"),
    ("letraRegistro", "LetraRegistro"), ("dataAbertura", "DataAbertura"),
    ("tipoRegistro", "TipoRegistro"), ("folhaTranscricao", "FolhaTranscricao"),
    ("livroTranscricao", "LivroTranscricao"), ("cep", "CEP"),
    ("tipoLogradouro", "TipoLogradouro"), ("logradouro", "NomeLogradouro"),
    ("numero", "Numero"), ("tipoImovel", "TipoImovel"), ("unidade", "Unidade"),
    ("bloco", "Bloco"), ("fracaoAreaComum", "FracaoAreaComum"),
    ("fracaoTempo", "FracaoTempo"), ("vagas", "Vagas"),
    ("nomeCondominio", "NomeCondominio"), ("complemento", "Complemento"),
    ("bairro", "Bairro"), ("quadra", "Quadra"), ("setor", "Setor"), ("lote", "Lote"),
    ("loteamento", "Loteamento"), ("cidade", "Cidade"), ("uf", "UF"),
    ("inscricaoMunicipal", "InscricaoMunicipal"), ("nirf", "NIRF"),
    ("sncrCcir", "SNCR_CCIR"), ("car", "CAR"), ("denominacaoRural", "DenominacaoRural"),
    ("cib", "CIB"), ("area", "Area"), ("situacaoConstrucao", "SituacaoConstrucao"),
    ("localizacao", "Localizacao"), ("vigenciaRegistro", "VigenciaRegistro"),
)
CAMPOS_DO_ATO = (
    ("tipo", "Tipo"), ("descricao", "Descricao"), ("dataInstrumento", "DataInstrumento"),
    ("valorDeclarado", "ValorDeclarado"), ("valorFiscal", "ValorFiscal"),
    ("dataRegistro", "DataRegistro"), ("numero", "NumeroAto"),
)


# O PREENCHIMENTO PARA A EXPORTAÇÃO — ordem do oficial, 10/10/2026: «vamos
# aumentar para todos. gerado do texto nao precisa conferir. vamos criar uma
# regra da casa, sem numero, zona rural, cep geral da cidade».
#
# A ORDEM É: o que a FICHA diz → o que o TEXTO da ficha diz → a REGRA DA CASA.
# A ficha nunca é sobrescrita (quem a preencheu leu o livro); o texto só entra
# onde ela está em branco; a regra só onde os dois calaram. E NADA DISTO É
# GRAVADO NA FICHA: vale para o arquivo que sai.
CAMPOS_DO_ENDERECO = ("logradouro", "numero_predial", "bairro", "cidade", "uf", "cep",
                      "rural_urbano", "area_valor", "area_unidade", "tipo_imovel")

#: As regras da casa que ainda não estavam escritas — as de 15/09/2026 (CEP único,
#: «Zona Rural», número «0») moram em `onr_endereco_do_teor.padrao_da_casa`.
LOGRADOURO_RURAL_SEM_NOME = "Fazenda Sem Denominação"
BAIRRO_URBANO_SEM_NOME = "Centro"
TIPO_RURAL = "Fazenda/Sítio/Chácara"
TIPO_URBANO = "Terreno/fração"


def _em_branco(v: Any) -> bool:
    return v is None or not str(v).strip()


def completar_ficha(m: dict, proposta: dict | None, padrao: dict) -> tuple[dict, dict]:
    """A ficha com os brancos preenchidos, e de onde veio cada um. SÓ CALCULA."""
    saida = dict(m)
    origem: dict[str, str] = {}
    campos_do_texto = dict((proposta or {}).get("campos") or {})
    # «ÁREA MAIOR» É A DA GLEBA DE ONDE O LOTE SAIU, e não a dele (matrículas
    # 2552 e 2556, 11/10/2026: «área maior de 3.108,08,06 ha»). Sem área o
    # indicador sobe — o campo é opcional —; com a da gleba-mãe, mente.
    leitura_da_area = ((proposta or {}).get("area") or {}).get("de_onde") or ""
    if "maior" in leitura_da_area.lower():
        campos_do_texto.pop("area_valor", None)
        campos_do_texto.pop("area_unidade", None)
        origem["area_valor"] = "fora: o texto dá a área maior (da gleba de origem)"
    for c in CAMPOS_DO_ENDERECO:
        if _em_branco(saida.get(c)) and not _em_branco(campos_do_texto.get(c)):
            saida[c] = campos_do_texto[c]
            origem[c] = "texto"
    rural = str(saida.get("rural_urbano") or "").strip().upper()[:1]
    if rural not in ("R", "U"):
        # Sem a palavra do livro, a casa é rural: é o que o acervo desta
        # serventia é (o tipo «Fazenda/Sítio/Chácara» domina as fichas).
        rural = "R"
        saida["rural_urbano"] = "Rural"
        origem["rural_urbano"] = "regra"
    regra = {
        "numero_predial": padrao.get("numero") or "0",
        "bairro": (padrao.get("bairro_rural") or "Zona Rural") if rural == "R"
        else BAIRRO_URBANO_SEM_NOME,
        "cidade": padrao.get("cidade"),
        "uf": padrao.get("uf"),
        "logradouro": LOGRADOURO_RURAL_SEM_NOME if rural == "R" else None,
        "tipo_imovel": TIPO_RURAL if rural == "R" else TIPO_URBANO,
    }
    for c, v in regra.items():
        if _em_branco(saida.get(c)) and not _em_branco(v):
            saida[c] = v
            origem[c] = "regra"
    # A área com o número por extenso ao lado (matrícula 4011, 11/10/2026): só o
    # primeiro número vale — os dígitos do texto inteiro davam dez mil vezes a
    # área. O conserto definitivo está em `onr_api.area_em_metros`; este cobre a
    # instalação que ainda não o tem.
    area = str(saida.get("area_valor") or "")
    num = re.search(r"\d(?:[\d.,]*\d)?", area)
    if num and re.search(r"[A-Za-zÀ-ÿ(]", area[num.end():]):
        saida["area_valor"] = area[:num.end()].strip()
        origem["area_valor"] = "limpo"
    _endireitar_logradouro(saida, origem, rural)
    _endireitar_tipo(saida, origem, rural)
    if _em_branco(saida.get("cep")):
        ceps = padrao.get("ceps") or {}
        cidade = str(saida.get("cidade") or "").strip().lower()
        import unicodedata
        cidade = "".join(ch for ch in unicodedata.normalize("NFKD", cidade)
                         if not unicodedata.combining(ch))
        cep = ceps.get(cidade) or padrao.get("cep")
        if cep:
            saida["cep"] = cep
            origem["cep"] = "regra"
    return saida, origem


LOGRADOURO_URBANO_SEM_NOME = "Rua Sem Denominação"

#: O que o texto da ficha põe na frente do nome da via («a AVENIDA…», «Na RUA…»).
_PREFIXOS_DA_FRASE = ("situada na ", "situado na ", "situada no ", "situado no ",
                      "sito na ", "sito no ", "na ", "no ", "a ", "à ", "em ")


def _endireitar_logradouro(saida: dict, origem: dict, rural: str) -> None:
    """O ONR exige o logradouro começando por um tipo do catálogo dele.

    Primeiro tira a preposição da frase do livro («a AVENIDA DEOCLIDES GOMES»);
    se ainda não casar, vale a regra da casa — a frase solta («situada na zona
    rural do Município…») não é nome de via, e ir ao índice como se fosse seria
    pior que «Sem Denominação».
    """
    import ri_onr_central as ONR
    atual = str(saida.get("logradouro") or "").strip()
    if atual and ONR.partir_logradouro(atual)["tipo_codigo"] is not None:
        return
    baixo = atual.lower()
    for p in _PREFIXOS_DA_FRASE:
        if baixo.startswith(p):
            resto = atual[len(p):].strip()
            if resto and ONR.partir_logradouro(resto)["tipo_codigo"] is not None:
                saida["logradouro"] = resto
                origem["logradouro"] = origem.get("logradouro", "texto") + "+limpo"
                return
    saida["logradouro"] = (LOGRADOURO_RURAL_SEM_NOME if rural == "R"
                           else LOGRADOURO_URBANO_SEM_NOME)
    origem["logradouro"] = "regra"


def _endireitar_tipo(saida: dict, origem: dict, rural: str) -> None:
    """O tipo do imóvel tem de ser um dos dez do ONR; a frase da ficha vira o mais próximo."""
    import onr_api as API
    atual = str(saida.get("tipo_imovel") or "").strip()
    chave = API.sem_acento(atual)
    if chave and chave in API.CODIGO_DO_IMOVEL:
        return
    if "casa" in chave:
        novo = "Casa"
    elif "sala" in chave:
        novo = "Sala"
    elif "apart" in chave:
        novo = "Apto"
    elif "galp" in chave:
        novo = "Galpão"
    elif "loja" in chave:
        novo = "Loja"
    else:
        novo = TIPO_RURAL if rural == "R" else TIPO_URBANO
    saida["tipo_imovel"] = novo
    origem["tipo_imovel"] = "regra"


# O DONO DE HOJE QUANDO A FICHA NÃO DIZ — ordem do oficial, 11/10/2026: «nao
# conseguimos resolver o problema das 283?». Medido: 275 das 283 TÊM as partes
# gravadas (a leitura do teor as trouxe, com o ato na `qualificacao`: «R-1 ·
# 10/10/1990 · …»), e nenhuma com `proprietario_ativo` aceso. A regra da casa:
# os ADQUIRENTES do último registro (R-n) que teve adquirente; sem registro de
# transmissão, quem consta como proprietário (abertura). Vale para o ARQUIVO
# que sai — a marca na ficha continua sendo de quem lê o livro.
_ATO_DA_QUALIFICACAO = re.compile(r"^\s*(R|AV|ABERTURA)\s*-?\s*(\d*)", re.I)


def _ato_da_parte(p: dict) -> tuple[str, int]:
    m = _ATO_DA_QUALIFICACAO.match(str(p.get("qualificacao") or ""))
    if not m:
        return ("", 0)
    return (m.group(1).upper(), int(m.group(2) or 0))


def donos_presumidos(partes: list[dict],
                     numero_do_ato: dict[int, tuple[str, int]] | None = None
                     ) -> tuple[list[dict], str]:
    """Quem é dono hoje, quando nenhuma parte está marcada como dona atual. SÓ CALCULA.

    O ÚLTIMO ATO (pelo número, R ou AV — nas fichas antigas a compra e venda e a
    partilha estão muitas vezes como AV) em que aparece adquirente ou
    proprietário decide: os adquirentes dele, ou, se não houver, os
    proprietários (divórcio, retificação, maioridade refazem o dono sem
    «adquirente»). A abertura é o ato zero. O ato sai da `qualificacao` («R-1 ·
    …»), ou do `ato_id` pelo mapa `numero_do_ato`, nas partes lavradas aqui.
    """
    if any(p.get("proprietario_ativo") for p in partes):
        return [p for p in partes if p.get("proprietario_ativo")], "ficha"
    por_ato: dict[tuple[str, int], list[dict]] = {}
    for p in partes:
        papel = str(p.get("papel") or "").strip().lower()
        if papel not in ("adquirente", "proprietario"):
            continue
        ato = _ato_da_parte(p)
        if ato == ("", 0) and p.get("ato_id") and numero_do_ato:
            ato = numero_do_ato.get(int(p["ato_id"]), ("", 0))
        if ato == ("", 0):
            continue
        por_ato.setdefault(ato, []).append(p)
    if not por_ato:
        # A carga do E-Ofício gravou só o nome e o papel, sem dizer de que ato:
        # se não há adquirente nenhum, quem está como proprietário é o dono.
        sem_ato = [p for p in partes
                   if str(p.get("papel") or "").strip().lower() == "proprietario"]
        if sem_ato and not any(str(p.get("papel") or "").strip().lower() == "adquirente"
                               for p in partes):
            return sem_ato, "proprietários da carga do E-Ofício (sem ato indicado)"
        return [], ""
    ultimo = max(por_ato, key=lambda a: a[1])
    gente = por_ato[ultimo]
    adq = [p for p in gente if str(p.get("papel")).strip().lower() == "adquirente"]
    rotulo = "abertura" if ultimo[0] == "ABERTURA" else f"{ultimo[0]}-{ultimo[1]}"
    if adq:
        return adq, f"adquirentes do {rotulo}"
    return gente, f"proprietários do {rotulo}"


def _valor(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.2f}"
    return escape(str(v))


def _linha(etiqueta: str, v: Any, recuo: str) -> str:
    texto = _valor(v)
    return f"{recuo}<{etiqueta}>{texto}</{etiqueta}>" if texto else f"{recuo}<{etiqueta} />"


def ato_entra(ato: dict) -> bool:
    """O manual exige data do título e valor declarado em cada ato."""
    return bool(ato.get("dataInstrumento")) and ato.get("valorDeclarado") is not None


def indicador_em_xml(corpo: dict, recuo: str = "  ") -> str:
    """Um `<IndicadorReal>` a partir do corpo da API. SÓ CALCULA."""
    r2, r3, r4 = recuo * 2, recuo * 3, recuo * 4
    partes = [f"{recuo}<IndicadorReal>"]
    for chave, etiqueta in CAMPOS:
        partes.append(_linha(etiqueta, corpo.get(chave), r2))
    donos = corpo.get("proprietarios") or []
    if donos:
        partes.append(f"{r2}<Proprietarios>")
        for p in donos:
            partes += [f"{r3}<Parte>", _linha("Nome", p.get("nome"), r4),
                       _linha("Documento", p.get("documento"), r4), f"{r3}</Parte>"]
        partes.append(f"{r2}</Proprietarios>")
    atos = [a for a in (corpo.get("atos") or []) if ato_entra(a)]
    if atos:
        partes.append(f"{r2}<Atos>")
        for a in atos:
            partes.append(f"{r3}<Ato>")
            partes += [_linha(et, a.get(ch), r4) for ch, et in CAMPOS_DO_ATO]
            partes.append(f"{r3}</Ato>")
        partes.append(f"{r2}</Atos>")
    partes.append(f"{recuo}</IndicadorReal>")
    return "\n".join(partes)


def arquivo_xml(corpos: list[dict]) -> str:
    """O arquivo inteiro. Recusa passar do limite do manual."""
    if len(corpos) > LIMITE_POR_ARQUIVO:
        raise ValueError(f"O ONR aceita até {LIMITE_POR_ARQUIVO} indicadores por "
                         f"arquivo; vieram {len(corpos)}.")
    corpo = "\n".join(indicador_em_xml(c) for c in corpos)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<Indicadores>\n'
            + corpo + ("\n" if corpo else "") + "</Indicadores>\n")
