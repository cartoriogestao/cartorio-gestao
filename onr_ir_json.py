"""O JSON DO INDICADOR REAL (LIVRO 4) que o oficial importa no Ofício Eletrônico.

DE ONDE VEM O FORMATO
    «Manual de Importação de Dados do Indicador Real (Livro 4)», versão 2.0, de 05/03/2026, e o
    exemplo oficial `indicadorReal.JSON`, os dois públicos no site do RI Digital. As tabelas de
    código do manual são imagem: foram lidas página a página e conferidas por OCR.

O QUE ESTE MÓDULO CORRIGE EM `ri_onr.gerar_indicador_real`
    O gerador antigo copiava o único arquivo que o sistema anterior deixou, e esse arquivo não
    prova nada: leva `UF`, `CIDADE` e `TIPO_LOGRADOURO` iguais a zero, e os três são obrigatórios.

    `LOCALIZACAO` é 0 urbano e 1 rural (manual, p. 8 e 11; exemplo). O antigo escrevia 1 urbano e
    2 rural, por leitura errada daquele arquivo: as fichas dele são rurais e estavam com 1.

    `TIPO_DE_IMOVEL` vai de 1 a 13 (manual, p. 17). A tabela antiga ia de 0 a 9, e por ela
    «Fazenda» sairia como 8, que no manual é «prédio residencial».

O QUE FICA COMO PERGUNTA AO ONR, E COMO O CÓDIGO SE COMPORTA ATÉ A RESPOSTA
    * `CONTRIBUINTE`: a tabela e a p. 10 do manual dizem texto, e o exemplo baixável traz número.
      Vai como texto, que são duas fontes contra uma.
    * `TIPO_DE_IMOVEL` é opcional, mas o manual não diz como representar a ausência. A ficha sem
      tipo é recusada, em vez de arriscar o arquivo inteiro com `null`.
    * `CAR`: o manual diz «39 caracteres» e descreve 2 + 7 + 32 mais dois hífens, que dão 43.
      Vale a estrutura descrita, que é a do exemplo dele.
    * O manual não fixa limite de registros por arquivo. O teto daqui é da casa.

SÓ CALCULA. Não lê banco, não grava e não transmite nada.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Mapping

TIPOENVIO_ATUAL = 0
REGISTRO_MATRICULA = 1
LOCALIZACAO_URBANO = 0
LOCALIZACAO_RURAL = 1
TIPO_LOGRADOURO_LOTEAMENTO = 162

#: Manual, seção 10.
UF_IBGE: dict[str, int] = {
    "RO": 11, "AC": 12, "AM": 13, "RR": 14, "PA": 15, "AP": 16, "TO": 17, "MA": 21, "PI": 22,
    "CE": 23, "RN": 24, "PB": 25, "PE": 26, "AL": 27, "SE": 28, "BA": 29, "MG": 31, "ES": 32,
    "RJ": 33, "SP": 35, "PR": 41, "SC": 42, "RS": 43, "MS": 50, "MT": 51, "GO": 52, "DF": 53,
}

#: Manual, seção 11. NÃO é a tabela da API (64 = Casa) nem a do sistema anterior (0 = Casa).
TIPOS_DE_IMOVEL: dict[int, str] = {
    1: "casa", 2: "apartamento", 3: "loja", 4: "sala/conjunto", 5: "terreno/fracao", 6: "galpao",
    7: "predio comercial", 8: "predio residencial", 9: "fazenda/sitio/chacara", 10: "vaga",
    11: "deposito", 12: "publicos", 13: "outros",
}
#: Os nomes que a casa grava e o manual escreve de outro jeito.
_APELIDOS_DO_IMOVEL = {"apto": 2, "sala": 4}

#: Manual, seção 9. NÃO é o catálogo da API (lá, 8 = Avenida; aqui, 26).
TIPOS_DE_LOGRADOURO: dict[int, str] = dict(enumerate((
    "Acampamento", "Acesso", "Açude", "Adro", "Aeroporto", "Afluente", "Aglomerado", "Agrovila",
    "Alagado", "Alameda", "Aldeia", "Aleia", "Alto", "Anel", "Antiga", "Antigo", "Área", "Areal",
    "Arraial", "Arroio", "Artéria", "Assentamento", "Atalho", "Aterro", "Autódromo", "Avenida",
    "Baia", "Bairro", "Baixa", "Baixada", "Baixadão", "Baixão", "Baixo", "Balão", "Balneário",
    "Barra", "Barragem", "Barranca", "Barranco", "Barreiro", "Barro", "Beco", "Beira", "Beirada",
    "Belvedere", "Bloco", "Bocaina", "Boqueirão", "Bosque", "Boulevard", "Brejo", "Buraco",
    "Cabeceira", "Cachoeira", "Cachoeirinha", "Cais", "Calcada", "Calçadão", "Caminho", "Campo",
    "Canal", "Canteiro", "Capão", "Capoeira", "Cartódromo", "Central", "Centro", "Cerca",
    "Cerrado", "Cerro", "Chácara", "Chapada", "Chapadão", "Charco", "Cidade", "Circular", "Cohab",
    "Colina", "Colônia", "Comunidade", "Condomínio", "Conjunto", "Continuação", "Contorno",
    "Corredor", "Córrego", "Costa", "Coxilha", "Cruzamento", "Descida", "Desvio", "Dique",
    "Distrito", "Divisa", "Divisão", "Divisor", "Edifício", "Eixo", "Elevado", "Encosta",
    "Engenho", "Enseada", "Entrada", "Entreposto", "Entroncamento", "Escada", "Escadão",
    "Escadaria", "Escadinha", "Espigão", "Esplanada", "Esquina", "Estação", "Estacionamento",
    "Estádio", "Estância", "Estrada", "Extensão", "Faixa", "Favela", "Fazenda", "Feira",
    "Ferrovia", "Final", "Floresta", "Folha", "Fonte", "Fortaleza", "Freguesia", "Fundos", "Furo",
    "Galeria", "Gameleira", "Garimpo", "Gleba", "Granja", "Grota", "Habitacional", "Haras",
    "Hipódromo", "Horto", "Igarapé", "Ilha", "Inaplicável", "Invasão", "Jardim", "Jardinete",
    "Ladeira", "Lado", "Lago", "Lagoa", "Lagoinha", "Largo", "Lateral", "Leito", "Ligação",
    "Limeira", "Limite", "Limites", "Linha", "Lote", "Loteamento", "Lugarejo", "Maloca",
    "Manancial", "Mangue", "Margem", "Margens", "Marginal", "Marina", "Mata", "Mato", "Módulo",
    "Monte", "Morro", "Muro", "Não Especificado", "Núcleo", "Oca", "Oleoduto", "Olho", "Olhos",
    "Orla", "Outros", "Paco", "Palafita", "Pântano", "Parada", "Paradouro", "Paralela", "Parque",
    "Particular", "Passagem", "Passarela", "Passeio", "Passo", "Pasto", "Pátio", "Pavilhão",
    "Pedra", "Pedras", "Pedreira", "Penhasco", "Perimetral", "Perímetro", "Perto", "Planalto",
    "Plataforma", "Ponta", "Ponte", "Ponto", "Porto", "Posto", "Povoado", "Praça", "Praia",
    "Projeção", "Projetada", "Projeto", "Prolongamento", "Propriedade", "Próximo", "Quadra",
    "Quarteirão", "Quilombo", "Quilometro", "Quinta", "Quintas", "Rachão", "Ramal", "Rampa",
    "Rancho", "Recanto", "Região", "Represa", "Residencial", "Reta", "Retiro", "Retorno", "Riacho",
    "Ribanceira", "Ribeirão", "Rincão", "Rio", "Rocha", "Rochedo", "Rodovia", "Rotatória", "Rotula",
    "Rua", "Ruela", "Saco", "Saída", "Sanga", "Sede", "Sem", "Seringal", "Serra", "Sertão",
    "Servidão", "Seta", "Setor", "Sitio", "Sopé", "Subida", "Superquadra", "Tapera", "Terminal",
    "Terra", "Terreno", "Terrenos", "Transversal", "Travessa", "Travessão", "Travessia", "Trecho",
    "Trevo", "Trilha", "Trilho", "Trilhos", "Trincheira", "Túnel", "Unidade", "Usina", "Vala",
    "Valão", "Vale", "Vargem", "Variante", "Várzea", "Velódromo", "Vereda", "Vertente", "Via",
    "Viaduto", "Vicinal", "Viela", "Vila", "Vilarejo", "Volta", "Zona", "1a Travessa da Avenida",
    "1a Travessa da Rua", "2a Travessa da Avenida", "2a Travessa da Rua", "3a Travessa da Avenida",
    "3a Travessa da Rua", "4a Travessa da Avenida", "4a Travessa da Rua", "5a Travessa da Avenida",
    "5a Travessa da Rua",
), start=1))

#: Estão no catálogo, mas não dizem o tipo da via: «Sem Denominação» não é uma via do tipo «Sem».
_TIPOS_QUE_NAO_NOMEIAM = frozenset({144, 177, 184, 256})

CHAVES_DO_REGISTRO = (
    "TIPOENVIO", "NUMERO_REGISTRO", "REGISTRO_TIPO", "TIPO_DE_IMOVEL", "LOCALIZACAO",
    "TIPO_LOGRADOURO", "NOME_LOGRADOURO", "NUMERO_LOGRADOURO", "UF", "CIDADE", "BAIRRO", "CEP",
    "COMPLEMENTO", "QUADRA", "CONJUNTO", "SETOR", "LOTE", "LOTEAMENTO", "CONTRIBUINTE", "RURAL",
    "CONDOMINIO",
)
CHAVES_RURAL = ("CAR", "NIRF", "CCIR", "NUMERO_INCRA", "SIGEF", "DENOMINACAORURAL", "ACIDENTEGEOGRAFICO")
CHAVES_CONDOMINIO = ("NOME_CONDOMINIO", "BLOCO", "CONJUNTO", "TORRE", "APTO", "VAGA")
_TEXTOS_DO_REGISTRO = ("NUMERO_REGISTRO", "NOME_LOGRADOURO", "NUMERO_LOGRADOURO", "BAIRRO", "CEP",
                       "COMPLEMENTO", "QUADRA", "CONJUNTO", "SETOR", "LOTE", "LOTEAMENTO")

_CAR = re.compile(r"^[A-Z]{2}-\d{7}-[A-Za-z0-9]{32}$")
_SIGEF = re.compile(r"^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$")
_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")


class ArquivoInvalido(ValueError):
    """O arquivo não sai: algum registro contraria o manual."""


def _texto(v: Any) -> str:
    return "" if v is None else re.sub(r"\s+", " ", str(v)).strip()


def _digitos(v: Any) -> str:
    return re.sub(r"\D", "", _texto(v))


def chave(v: Any) -> str:
    """Sem acento, sem caixa e com um espaço só: é assim que se casa com as tabelas."""
    decomposto = unicodedata.normalize("NFKD", _texto(v).replace("º", "o"))
    return " ".join("".join(c for c in decomposto if not unicodedata.combining(c)).lower().split())


_CODIGO_DO_LOGRADOURO = {chave(n): c for c, n in TIPOS_DE_LOGRADOURO.items()}
_MAIOR_TIPO = max(len(k.split()) for k in _CODIGO_DO_LOGRADOURO)
_CODIGO_DO_IMOVEL = {**{chave(n): c for c, n in TIPOS_DE_IMOVEL.items()}, **_APELIDOS_DO_IMOVEL}


def partir_logradouro(texto: Any) -> tuple[int | None, str]:
    """`Rua João da Silva` vira `(250, "João da Silva")`, como no manual.

    Tenta do nome maior para o menor, porque «1a Travessa da Rua X» não é uma via do tipo «1a».
    Sem nome depois do tipo, ou com um tipo que não nomeia nada, devolve `None`.
    """
    palavras = _texto(texto).split()
    for quantas in range(min(_MAIOR_TIPO, len(palavras) - 1), 0, -1):
        codigo = _CODIGO_DO_LOGRADOURO.get(chave(" ".join(palavras[:quantas])))
        if codigo is not None:
            if codigo in _TIPOS_QUE_NAO_NOMEIAM:
                return None, _texto(texto)
            return codigo, " ".join(palavras[quantas:])
    return None, _texto(texto)


def codigo_do_imovel(texto: Any) -> int | None:
    """Pelo NOME, e só o nome exato. Número solto na ficha é da tabela antiga e não se aproveita."""
    return _CODIGO_DO_IMOVEL.get(chave(texto))


# ------------------------------------------------------------ a serventia


@dataclass(frozen=True)
class Serventia:
    """O que o arquivo precisa da configuração da casa."""
    cns: str
    uf: str
    uf_codigo: int
    municipios: Mapping[str, int] = field(default_factory=dict)


def serventia_de(settings: Mapping[str, Any]) -> tuple[Serventia | None, list[str]]:
    """Lê a configuração. Sem CNS, UF ou município do IBGE, não há arquivo, e a tela diz o que falta."""
    faltam: list[str] = []
    cns = _digitos(settings.get("ri_cns") or settings.get("serventia_cns"))
    if len(cns) != 6:
        faltam.append("o CNS da serventia, com 6 dígitos")
    uf = _texto(settings.get("ri_uf") or settings.get("serventia_uf")).upper()
    uf_codigo = UF_IBGE.get(uf)
    if uf_codigo is None:
        faltam.append("a UF da serventia")
    cidade = chave(settings.get("ri_cidade") or settings.get("serventia_cidade"))
    parte_uf, parte_mun = _digitos(settings.get("ibge_uf")), _digitos(settings.get("ibge_municipio"))
    codigo = parte_uf + parte_mun if len(parte_uf) == 2 and len(parte_mun) == 5 else \
        _digitos(settings.get("nfse_municipio"))
    if not cidade:
        faltam.append("o nome do município da serventia")
    if len(codigo) != 7 or (uf_codigo is not None and not codigo.startswith(str(uf_codigo))):
        faltam.append("o código IBGE do município da serventia, com 7 dígitos e da mesma UF")
    outros, erros_outros = _outros_municipios(settings.get("ri_municipios_ibge"), uf_codigo)
    faltam.extend(erros_outros)
    if faltam:
        return None, faltam
    return Serventia(cns=cns, uf=uf, uf_codigo=uf_codigo, municipios={**outros, cidade: int(codigo)}), []


def _outros_municipios(bruto: Any, uf_codigo: int | None) -> tuple[dict[str, int], list[str]]:
    """Os outros municípios da circunscrição: `ri_municipios_ibge` = {"Nome": código IBGE}.

    A CIRCUNSCRIÇÃO PODE TER MAIS DE UM MUNICÍPIO, e a ficha do segundo era recusada porque só a
    sede tinha código. O código vem da configuração, e não daqui: é o oficial quem diz o que a
    circunscrição abrange. Configuração torta recusa o arquivo inteiro, em vez de sumir com as fichas.
    """
    if bruto is None or not _texto(bruto):
        return {}, []
    try:
        lido = json.loads(bruto) if isinstance(bruto, str) else bruto
    except ValueError:
        lido = None
    if not isinstance(lido, Mapping):
        return {}, ['«ri_municipios_ibge» tem de ser {"Nome do município": código IBGE}']
    saida: dict[str, int] = {}
    erros: list[str] = []
    for nome, codigo in lido.items():
        digitos = _digitos(codigo)
        if not chave(nome) or len(digitos) != 7 or (uf_codigo is not None and not digitos.startswith(str(uf_codigo))):
            erros.append(f"o código IBGE de «{_texto(nome)}» em «ri_municipios_ibge», com 7 dígitos e da mesma UF")
        else:
            saida[chave(nome)] = int(digitos)
    return saida, erros


# ------------------------------------------------------------ o registro


def _bloco_rural(m: Mapping[str, Any], motivos: list[tuple[str, str]]) -> dict[str, str]:
    car = _texto(m.get("car")).upper()
    if car and not _CAR.match(car):
        motivos.append(("car", "O CAR da ficha não tem o formato do manual (UF-7 dígitos-32 caracteres)."))
    ccir = _digitos(m.get("ccir"))
    if ccir and len(ccir) != 13:
        motivos.append(("ccir", "O CCIR da ficha não tem os 13 dígitos do manual."))
    sigef = _texto(m.get("sigef")).lower()
    if sigef and not _SIGEF.match(sigef):
        motivos.append(("sigef", "O SIGEF da ficha não tem os 32 caracteres do manual."))
    # O manual diz que o CIB é o NIRF com outro nome, e o exemplo do campo traz os dois formatos.
    nirf = _texto(m.get("nirf")) or _texto(m.get("cib"))
    if nirf and not 7 <= len(re.sub(r"[^0-9A-Za-z]", "", nirf)) <= 8:
        motivos.append(("nirf", "O NIRF/CIB da ficha não tem o tamanho do manual."))
    return {"CAR": car, "NIRF": nirf, "CCIR": ccir, "NUMERO_INCRA": _texto(m.get("incra")),
            "SIGEF": sigef, "DENOMINACAORURAL": _texto(m.get("logradouro")), "ACIDENTEGEOGRAFICO": ""}


def montar_registro(m: Mapping[str, Any], casa: Serventia) -> tuple[dict | None, list[str]]:
    """O registro do manual, ou a lista do que impede. Não preenche nada que a ficha não diga."""
    registro, por_campo = montar_registro_por_campo(m, casa)
    return registro, [motivo for _campo, motivo in por_campo]


def montar_registro_por_campo(m: Mapping[str, Any], casa: Serventia) -> tuple[dict | None, list[tuple[str, str]]]:
    """O mesmo `montar_registro`, com cada impedimento ligado à coluna da ficha que o causa.

    É a régua da abertura da matrícula (`ri_requisitos_ir`): a tela mostra o que falta campo por
    campo, e a régua é esta, a do arquivo, para que a ficha que abre seja a ficha que sobe.
    """
    motivos: list[tuple[str, str]] = []
    numero = _texto(m.get("numero"))
    if not numero.isdigit():
        motivos.append(("numero", f"O número da matrícula («{numero}») não é só de dígitos."))
    if not _texto(m.get("livro_norm")).startswith("2"):
        motivos.append(("livro_norm", "A ficha não está no Livro 2. Confira se é matrícula antes de enviar."))

    letra = chave(m.get("rural_urbano"))
    if letra in ("u", "urbano", "urbana"):
        localizacao = LOCALIZACAO_URBANO
    elif letra in ("r", "rural"):
        localizacao = LOCALIZACAO_RURAL
    else:
        localizacao = None
        motivos.append(("rural_urbano", "A ficha não diz se o imóvel é urbano ou rural."))

    tipo = codigo_do_imovel(m.get("tipo_imovel"))
    if tipo is None:
        motivos.append(("tipo_imovel", f"O tipo do imóvel («{_texto(m.get('tipo_imovel')) or 'vazio'}») não é um dos 13 do manual."))
    tipo_via, nome_via = partir_logradouro(m.get("logradouro"))
    if tipo_via is None:
        motivos.append(("logradouro", f"O logradouro («{_texto(m.get('logradouro')) or 'vazio'}») não começa por um tipo "
                       "do manual seguido do nome."))

    cidade = casa.municipios.get(chave(m.get("cidade")))
    # O MUNICÍPIO JÁ DIZ A UF: o código IBGE de 7 dígitos começa pelo da UF. Ficha sem UF e com um
    # município da circunscrição não fica de fora por isso. UF escrita e diferente continua recusada.
    uf = _texto(m.get("uf")).upper() or (casa.uf if cidade is not None else "")
    if uf != casa.uf:
        motivos.append(("uf", f"A UF da ficha («{uf or 'vazia'}») não é a da serventia."))
    if cidade is None:
        motivos.append(("cidade", f"O município da ficha («{_texto(m.get('cidade')) or 'vazio'}») não tem código IBGE "
                       "configurado nesta serventia."))
    cep = _digitos(m.get("cep"))
    if cep and len(cep) != 8:
        motivos.append(("cep", "O CEP da ficha não tem 8 dígitos."))

    vazio_rural = {c: "" for c in CHAVES_RURAL}
    if localizacao == LOCALIZACAO_RURAL:
        rural = _bloco_rural(m, motivos)
    else:
        rural = vazio_rural
        if localizacao == LOCALIZACAO_URBANO and any(_texto(m.get(c)) for c in ("car", "ccir", "sigef", "incra", "nirf")):
            motivos.append(("rural_urbano", "A ficha está como urbana e traz cadastro rural (CAR, CCIR, SIGEF, INCRA ou NIRF). Confira."))
    if motivos:
        return None, motivos

    contribuinte = _texto(m.get("inscricao_municipal")) or _texto(m.get("iptu"))
    return {
        "TIPOENVIO": TIPOENVIO_ATUAL,
        "NUMERO_REGISTRO": numero,
        "REGISTRO_TIPO": REGISTRO_MATRICULA,
        "TIPO_DE_IMOVEL": tipo,
        "LOCALIZACAO": localizacao,
        "TIPO_LOGRADOURO": tipo_via,
        "NOME_LOGRADOURO": nome_via,
        "NUMERO_LOGRADOURO": _texto(m.get("numero_predial")),
        "UF": casa.uf_codigo,
        "CIDADE": cidade,
        "BAIRRO": _texto(m.get("bairro")),
        "CEP": cep,
        # «000» na coluna de complemento é sobra do sistema anterior, e não informação.
        "COMPLEMENTO": "" if re.fullmatch(r"0*", _texto(m.get("complemento_endereco"))) else _texto(m.get("complemento_endereco")),
        "QUADRA": "",
        "CONJUNTO": "",
        "SETOR": "",
        "LOTE": "",
        # Manual, p. 8: obrigatório quando o tipo é Loteamento, e aí o nome da via é o dele.
        "LOTEAMENTO": nome_via if tipo_via == TIPO_LOGRADOURO_LOTEAMENTO else "",
        "CONTRIBUINTE": [contribuinte] if contribuinte else [],
        "RURAL": rural,
        "CONDOMINIO": {c: "" for c in CHAVES_CONDOMINIO},
    }, []


def validar_registro(r: Mapping[str, Any], casa: Serventia) -> list[str]:
    """Confere o registro PRONTO contra o manual, sem confiar em quem o montou."""
    erros: list[str] = []
    if tuple(r.keys()) != CHAVES_DO_REGISTRO:
        return ["As chaves do registro não são as do manual."]
    if tuple(r["RURAL"].keys()) != CHAVES_RURAL or tuple(r["CONDOMINIO"].keys()) != CHAVES_CONDOMINIO:
        return ["Os blocos RURAL e CONDOMINIO não têm as chaves do manual."]
    for campo, permitido in (("TIPOENVIO", {0, 1, 2}), ("REGISTRO_TIPO", {1, 2, 4}), ("LOCALIZACAO", {0, 1}),
                             ("TIPO_DE_IMOVEL", set(TIPOS_DE_IMOVEL)), ("TIPO_LOGRADOURO", set(TIPOS_DE_LOGRADOURO)),
                             ("UF", {casa.uf_codigo}), ("CIDADE", set(casa.municipios.values()))):
        if type(r[campo]) is not int or r[campo] not in permitido:
            erros.append(f"{campo} fora da tabela do manual: {r[campo]!r}.")
    for campo in _TEXTOS_DO_REGISTRO:
        if not isinstance(r[campo], str) or _CONTROLE.search(r[campo]):
            erros.append(f"{campo} tem de ser texto, sem caractere de controle.")
    if not str(r["NUMERO_REGISTRO"]).isdigit():
        erros.append("NUMERO_REGISTRO tem de ser só de dígitos.")
    if not r["NOME_LOGRADOURO"]:
        erros.append("NOME_LOGRADOURO é obrigatório.")
    if r["CEP"] and not re.fullmatch(r"\d{8}", str(r["CEP"])):
        erros.append("CEP tem de ter 8 dígitos.")
    if r["TIPO_LOGRADOURO"] == TIPO_LOGRADOURO_LOTEAMENTO and not r["LOTEAMENTO"]:
        erros.append("LOTEAMENTO é obrigatório quando o tipo do logradouro é Loteamento.")
    if not isinstance(r["CONTRIBUINTE"], list) or not all(isinstance(x, str) for x in r["CONTRIBUINTE"]):
        erros.append("CONTRIBUINTE tem de ser uma lista de textos.")
    if not all(isinstance(v, str) for v in (*r["RURAL"].values(), *r["CONDOMINIO"].values())):
        erros.append("Os blocos RURAL e CONDOMINIO têm de ser de textos.")
    if r["LOCALIZACAO"] == LOCALIZACAO_URBANO and any(r["RURAL"][c] for c in CHAVES_RURAL):
        erros.append("Imóvel urbano com o bloco RURAL preenchido.")
    return erros


def arquivo_json(registros: list[dict], casa: Serventia) -> bytes:
    """O arquivo, em UTF-8 sem BOM. Recusa o arquivo inteiro se algum registro contrariar o manual."""
    if not registros:
        raise ArquivoInvalido("Não há registro para o arquivo.")
    numeros = [r.get("NUMERO_REGISTRO") for r in registros]
    if len(set(numeros)) != len(numeros):
        raise ArquivoInvalido("O mesmo número de matrícula aparece duas vezes no arquivo.")
    for r in registros:
        erros = validar_registro(r, casa)
        if erros:
            raise ArquivoInvalido(f"Matrícula {r.get('NUMERO_REGISTRO')}: " + " ".join(erros))
    corpo = {"INDICADOR_REAL": {"CNS": casa.cns, "REAL": registros}}
    return (json.dumps(corpo, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def sha256(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()
