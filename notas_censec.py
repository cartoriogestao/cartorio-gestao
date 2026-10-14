"""
Remessa as centrais da CENSEC — CEP, CESDI e RCTO.

O QUE ESTE MODULO FAZ
    Separa os atos da quinzena, confere cada um contra o layout oficial do
    CNB-CF e monta a carga. O que nao passa na conferencia NAO vai no arquivo:
    fica na lista de impedidos, com o motivo escrito, para o registrador
    resolver. O sistema separa, mede e mostra — quem decide e ele.

DE ONDE VEIO O LAYOUT
    Da documentacao do Colegio Notarial do Brasil, lida em 15/08/2026:
      CEP    https://suporte.notariado.org.br/a/solutions/articles/43000536374  (v4.0, 04/03/2026)
      CESDI  https://suporte.notariado.org.br/a/solutions/articles/43000536375  (v3.9, 04/08/2025)
      RCTO   https://suporte.notariado.org.br/a/solutions/articles/43000536373  (v3.1, 04/09/2024)
      JSON   https://suporte.notariado.org.br/a/solutions/articles/43000708963  (v3.1, 08/07/2025)
      Regras https://suporte.notariado.org.br/a/solutions/articles/43000731919  (v1,   02/08/2024)

    NAO foi copiado do E-Oficio. Os dominios que vieram do E-Oficio estao
    velhos — faltam 17 naturezas de escritura que a CENSEC ja aceita — e por
    isso as tabelas abaixo sao as oficiais, nao as importadas. A carga do
    E-Oficio continua servindo para o que o ato ja trazia gravado.

O QUE AINDA NAO FOI CONFERIDO CONTRA FONTE PRIMARIA
    Os nomes das listas dentro do envelope (ENVELOPE_CHAVES, la embaixo).
    O cabecalho esta conferido; o nome de cada lista so aparece no Postman e
    no Swagger da CENSEC, que exigem login do cartorio. Esta marcado no lugar
    onde alguem iria "consertar", e a tela avisa enquanto nao for confirmado.

DINHEIRO
    Entra em centavos inteiros, como no resto do sistema, e so vira decimal na
    hora de escrever o JSON. Ponto flutuante nao encosta em valor de ato.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import sqlite3
from typing import Any

from notas_partes import documento_valido, so_digitos

# ------------------------------------------------------------- quinzena

# O cabecalho da CENSEC pede o mes por extenso ("Junho"), nao o numero.
MESES = ("", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
         "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro")


def quinzena_de(data_iso: str) -> tuple[int, int, int]:
    """Devolve (ano, mes, quinzena) da data do ato.

    1a quinzena: dia 01 ao 15. 2a: dia 16 ao fim do mes. E a regra do
    Provimento CNJ 149/2023, art. 267, e nao uma escolha nossa.
    """
    ano, mes, dia = int(data_iso[0:4]), int(data_iso[5:7]), int(data_iso[8:10])
    return ano, mes, 1 if dia <= 15 else 2


def periodo_da_quinzena(ano: int, mes: int, quinzena: int) -> tuple[str, str]:
    """Primeiro e ultimo dia da quinzena, em AAAA-MM-DD."""
    if quinzena == 1:
        return f"{ano:04d}-{mes:02d}-01", f"{ano:04d}-{mes:02d}-15"
    ultimo = calendar.monthrange(ano, mes)[1]   # fevereiro bissexto incluido
    return f"{ano:04d}-{mes:02d}-16", f"{ano:04d}-{mes:02d}-{ultimo:02d}"


def prazo_de_fechamento(ano: int, mes: int, quinzena: int) -> str:
    """Ate quando a quinzena tem de estar fechada.

    Ate o dia 5 do mes seguinte para a 2a quinzena; ate o dia 20 do proprio
    mes para a 1a. Caindo em dia nao util, o cartorio usa o proximo dia util —
    isso o sistema nao calcula, porque nao conhece o feriado municipal.
    """
    if quinzena == 1:
        return f"{ano:04d}-{mes:02d}-20"
    ano_s, mes_s = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return f"{ano_s:04d}-{mes_s:02d}-05"


# --------------------------------------------------------- tabelas dominio

# TipoAtoCep. O layout aceita o codigo numerico OU o codigo JSON; mandamos o
# numerico, que nao tem ambiguidade de grafia.
TIPO_ATO_CEP = {
    1: "Escritura",
    2: "Procuracao",
    3: "ProcuracaoParaFinsPrevidenciarios",
    5: "RenunciaDeProcuracao",
    6: "RevogacaoDeProcuracao",
    7: "Substabelecimento",
    8: "AtaNotarial",
    9: "AtaNotarialDeUsucapiao",
    10: "ProcuracaoPrivada",   # so em "referentes", nunca como ato proprio
}

# NaturezaEscritura, tabela oficial completa. A carga do E-Oficio trouxe 38
# destas; as 17 marcadas com # novo nao existiam la e por isso nenhum ato do
# acervo pode estar classificado nelas hoje.
NATUREZA_ESCRITURA = {
    1: "ACORDO EXTRAJUDICIAL",
    4: "ALIENAÇÃO FIDUCIÁRIA",
    5: "CESSÃO",
    6: "COMPRA E VENDA",
    10: "CONFISSÃO DE DÍVIDA OU DAÇÃO EM PAGAMENTO",
    14: "DECLARAÇÃO",
    15: "DECLARATÓRIA DE UNIÃO ESTÁVEL",
    16: "DECLARATÓRIA DE UNIÃO ESTÁVEL HOMOAFETIVA",
    17: "DESAPROPRIAÇÃO",
    20: "DISSOLUÇÃO DE UNIÃO ESTÁVEL",
    21: "DISTRATO",
    22: "DOAÇÃO",
    23: "EMANCIPAÇÃO",
    24: "HIPOTECA",
    25: "INCORPORAÇÃO",
    26: "BEM DE FAMÍLIA",
    28: "LOCAÇÃO",
    30: "PACTO ANTENUPCIAL",
    31: "PENHOR",
    33: "PROMESSA DE CESSÃO DE DIREITOS AQUISITIVOS",
    34: "QUITAÇÃO",
    35: "RERRATIFICAÇÃO",                              # novo
    36: "RECONHECIMENTO DE PATERNIDADE",
    38: "REGISTRO DE CHANCELA MECÂNICA",
    39: "REMISSÃO DE FORO E LAUDÊMIOS",
    43: "SEM VALOR DECLARADO",                         # novo
    45: "SERVIDÃO",                                    # novo
    46: "USUFRUTO (RESERVA, INSTITUIÇÃO E RENÚNCIA)",  # novo
    48: "CONDOMÍNIO",
    49: "PARCELAMENTO",
    50: "SOCIEDADE E FUNDAÇÕES",                       # novo
    51: "TRANSAÇÃO",                                   # novo
    52: "DIREITO DE USO OU SUPERFÍCIE",
    53: "DIVISÃO",
    54: "FIANÇA",                                      # novo
    55: "DIRETIVAS ANTECIPADAS DE VONTADE",            # novo
    56: "CONFERÊNCIA DE BENS",
    57: "NOVAÇÃO",
    58: "CRÉDITO COM GARANTIA",
    59: "EMISSÃO DE CÉDULA",
    60: "EMISSÃO DE DEBENTURES",
    61: "REVOGAÇÃO",
    62: "RENÚNCIA DE DIREITOS HEREDITÁRIOS",
    63: "COMODATO OU MÚTUO",
    70: "PRESTAÇÃO DE SERVIÇOS",                       # novo
    71: "ARRENDAMENTO MERCANTIL (LEASING)",            # novo
    72: "CONCESSÃO DE DOMÍNIO",                        # novo
    74: "CONTRATO DE NAMORO",
    75: "CONCILIAÇÃO",                                 # novo
    76: "MEDIAÇÃO",                                    # novo
    77: "AFETAÇÃO",                                    # novo
    78: "AUTOCURATELA",                                # novo
    79: "DECLATÓRIA COM DIRETIVAS DE CURATELA",        # novo (grafia do CNB)
    80: "PROMESSA DE COMPRA E VENDA",                  # novo
}

# NaturezaAtaNotarialDeUsucapiao. Mandamos o codigo numerico de proposito: a
# tabela do CNB grafa o codigo 5 como "EspecialFamilar" (sem o segundo i) e o
# E-Oficio grafa "EspecialFamiliar". Com o numero, a divergencia nao importa.
NATUREZA_ATA_USUCAPIAO = {
    1: "Ordinária", 2: "Extraordinária", 3: "Especial Rural",
    4: "Especial Urbana", 5: "Especial Familiar",
}

TIPO_ATO_CESDI = {
    1: "Separação", 2: "Reconciliação", 3: "Conversão de Separação em Divórcio",
    4: "Divórcio Direto", 5: "Inventário", 6: "Sobrepartilha", 7: "Retificação",
    8: "Nomeação de Inventariante", 9: "Partilha",
    10: "Inventário com menor ou incapaz", 11: "Retificação de ato não notarial",
}

TIPO_TESTAMENTO = {
    1: "Aditamento", 2: "Cerrado", 3: "Revogacao", 4: "Testamento",
    5: "TestamentoComRevogacao", 6: "TestamentoSemConteudoPatrimonial",
}

# ParteQualidade da CEP. Valem para qualquer tipo de ato, exceto as quatro
# ultimas, que so existem em conciliacao e mediacao.
QUALIDADE_CEP = ("Outorgado", "Outorgante", "Interveniente", "Usufrutuário",
                 "Requerente", "Requerido", "Conciliador", "Mediador")

# Qualidade da CESDI, no codigo JSON. Cada tipo de ato aceita um subconjunto —
# QUALIDADE_CESDI_POR_ATO abaixo.
QUALIDADE_CESDI = ("Separando", "Reconciliando", "Divorciando", "Falecido",
                   "Viuvo", "Herdeiro", "Inventariante", "Advogado",
                   "CessionarioAdjudicatarios", "Cedente", "Interveniente",
                   "Anuente")

_COMUNS_CESDI = ("CessionarioAdjudicatarios", "Cedente", "Interveniente",
                 "Anuente", "Advogado")
QUALIDADE_CESDI_POR_ATO = {
    1: ("Separando",) + _COMUNS_CESDI,
    2: ("Reconciliando",) + _COMUNS_CESDI,
    3: ("Divorciando",) + _COMUNS_CESDI,
    4: ("Divorciando",) + _COMUNS_CESDI,
    5: ("Falecido", "Viuvo", "Herdeiro", "Inventariante") + _COMUNS_CESDI,
    6: ("Falecido", "Viuvo", "Herdeiro", "Divorciando") + _COMUNS_CESDI,
    7: ("Divorciando", "Separando", "Falecido", "Viuvo", "Herdeiro") + _COMUNS_CESDI,
    8: ("Falecido", "Viuvo", "Inventariante", "Herdeiro") + _COMUNS_CESDI,
    9: ("Falecido", "Viuvo", "Herdeiro", "Divorciando") + _COMUNS_CESDI,
    10: ("Falecido", "Viuvo", "Herdeiro", "Inventariante") + _COMUNS_CESDI,
    11: ("Divorciando", "Separando", "Falecido", "Viuvo", "Herdeiro") + _COMUNS_CESDI,
}

# Minimo de partes por tipo de ato da CESDI, conforme o item 10 do layout.
# (quantidade minima, qualidades que precisam estar presentes)
MINIMO_PARTES_CESDI = {
    1: (3, ("Advogado", "Separando")),
    2: (3, ("Advogado", "Reconciliando")),
    3: (3, ("Advogado", "Divorciando")),
    4: (3, ("Advogado", "Divorciando")),
    5: (2, ("Advogado", "Falecido")),
    6: (2, ("Advogado",)),
    7: (1, ()),
    8: (2, ("Inventariante", "Falecido")),
    9: (2, ("Advogado",)),
    10: (2, ("Advogado", "Falecido")),
    11: (1, ()),
}

REGIME_BENS = {
    "COMUNHAO PARCIAL": "ComunhaoParcial",
    "COMUNHAO UNIVERSAL": "ComunhaoUniversal",
    "PARTICIPACAO FINAL NOS AQUESTOS": "ParticipacaoFinalNosAquestos",
    "SEPARACAO TOTAL": "SeparacaoTotal",
    "SEPARACAO OBRIGATORIA": "SeparacaoObrigatoria",
    "PACTO ANTENUPCIAL": "RegimeEspecificoAtribuidoEmPactoAntenupcial",
}

TIPO_DOCUMENTO_CEP = ("CPF", "CNPJ", "RNM", "Desconhecido")
TIPO_DOCUMENTO_RCTO = ("Rg", "Rne", "Outros")

# Como a qualificacao gravada no ato vira qualidade da CEP.
#
# TESTEMUNHA vira Interveniente porque e o proprio layout que diz: a qualidade
# Interveniente "contempla assistentes, assina a rogo, representante, credor,
# anuente e testemunha". Nao e arredondamento nosso.
#
# A serventia nao grava "outorgante": grava o papel do ato — VENDEDOR(A),
# COMPRADOR(A), CEDENTE(S), DONATARIO(A). Sao os 22 rotulos encontrados nas
# 105 partes de escritura do acervo. O rotulo original fica gravado na parte;
# o de-para acontece so na hora da remessa.
#
# QUEM NAO ESTIVER AQUI NAO PASSA. A conferencia devolve o rotulo exato como
# impedimento, para o rotulo novo aparecer em vez de virar Outorgante calado.
QUALIFICACAO_PARA_CEP = {
    # quem transmite, aliena, declara ou outorga
    "OUTORGANTE": "Outorgante",
    "VENDEDOR": "Outorgante",
    "VENDEDOR(A)": "Outorgante",
    "VENDEDORA": "Outorgante",
    "PROPRIETARIO": "Outorgante",
    "PROPRIETARIO(A)": "Outorgante",
    "PROPRIETARIA": "Outorgante",
    "CEDENTE": "Outorgante",
    "CEDENTE(S)": "Outorgante",
    "HERDEIRO(A) CEDENTE": "Outorgante",
    "DOADOR": "Outorgante",
    "DOADOR(A)": "Outorgante",
    # O declarante da escritura declaratoria e quem pratica a declaracao: e o
    # outorgante do ato, nao um terceiro que intervem.
    "DECLARANTE": "Outorgante",
    # quem recebe
    "OUTORGADO": "Outorgado",
    "OUTORGADA": "Outorgado",
    "COMPRADOR": "Outorgado",
    "COMPRADOR(A)": "Outorgado",
    "COMPRADORA": "Outorgado",
    "CESSIONARIO": "Outorgado",
    "CESSIONARIO(A)": "Outorgado",
    "DONATARIO": "Outorgado",
    "DONATARIO(A)": "Outorgado",
    # quem intervem
    "TESTEMUNHA": "Interveniente",
    "INTERVENIENTE": "Interveniente",
    "ANUENTE": "Interveniente",
    "CREDOR": "Interveniente",
    "USUFRUTUARIO": "Usufrutuário",
    "REQUERENTE": "Requerente",
    # ata notarial: quem pede a ata e grava «Solicitante» (atas 780 e 792, 09/10/2026)
    "SOLICITANTE": "Requerente",
    "REQUERIDO": "Requerido",
    "CONCILIADOR": "Conciliador",
    "MEDIADOR": "Mediador",
}

# O procurador e o representante entram como Interveniente, e nao por analogia:
# o layout da CEP diz que a qualidade Interveniente "contempla assistentes,
# assina a rogo, REPRESENTANTE, credor, anuente e testemunha". Como regra e nao
# como lista, porque o acervo tem seis grafias — PROCURADOR DO VENDEDOR,
# PROCURADORA DA VENDEDORA, PROCURADOR DO PROPRIETARIO e por ai.
PREFIXOS_INTERVENIENTE = ("PROCURADOR", "PROCURADORA", "REPRESENTANTE",
                          "ASSISTENTE", "ASSINA A ROGO")

# Tipos de ato do sistema que a CEP recebe, e com que codigo.
#
# **AS CHAVES SÃO AS DE `notas_schema.TIPOS_ATO`, E NÃO NOMES PARECIDOS — 09/10/2026.**
# Este dicionário dizia «ATA_NOTARIAL», «RENUNCIA_PROCURACAO» e
# «REVOGACAO_PROCURACAO», e o sistema grava «ATA», «RENUNCIA» e «REVOGACAO»:
# atas, renúncias e revogações nunca entravam na conta da CEP, sem aviso. Medido
# na CENSEC: a 2ª quinzena de setembro foi fechada com 0 atos tendo a ata termo
# 9 (17/09), e a 1ª sem a ata termo 10 (10/09). Os nomes antigos ficam, inertes,
# para não recusar dado legado. Há teste que exige toda chave de `TIPOS_ATO`
# (menos os testamentos, que vão ao RCTO) aqui dentro.
TIPO_SISTEMA_PARA_CEP = {
    "ESCRITURA": 1,
    "PROCURACAO": 2,
    "PROCURACAO_PREVIDENCIARIA": 3,
    "RENUNCIA": 5,
    "REVOGACAO": 6,
    "SUBSTABELECIMENTO": 7,
    "ATA": 8,
    "ATA_USUCAPIAO": 9,
    "RENUNCIA_PROCURACAO": 5,
    "REVOGACAO_PROCURACAO": 6,
    "ATA_NOTARIAL": 8,
}

# Atos que exigem os dados do ato antecessor ("referentes").
EXIGEM_REFERENTE = (5, 6, 7)          # renuncia, revogacao, substabelecimento
NATUREZA_EXIGE_REFERENTE = 35         # escritura de rerratificacao

# Atos em que nao existe valor a declarar.
#
#     A CEP marca o campo `valor` como obrigatorio, mas o proprio layout
#     explica o que ele e: "o valor discriminado no ato, e nao o valor pago
#     pela lavratura". Procuracao, revogacao, renuncia, substabelecimento e
#     ata notarial nao discriminam valor nenhum — nesses o zero nao e chute,
#     e a informacao correta.
#
#     Escritura NAO entra nesta lista, e e o ponto todo da distincao: ali o
#     valor e o proprio conteudo economico do ato, e mandar zero seria
#     declaracao falsa a uma central nacional. Escritura sem valor fica
#     barrada e aparece na lista de pendencias.
#
#     Decisao do delegatario em 15/08/2026.
ATOS_SEM_VALOR_DECLARADO = (2, 3, 5, 6, 7, 8)


# --------------------------------------------------------------- envelope

# CONFERIDO CONTRA O CONTRATO EM 09/10/2026 — e os tres nomes estavam errados.
#
#     Ate esta data aqui estava escrito que os nomes das listas «aparecem so
#     no Postman e no Swagger da CENSEC, que pedem login», e os tres eram
#     palpite: `cep`, `cesdi`, `rcto`. **O Swagger nao pede login**:
#     `https://censec.org.br/swagger/api/swagger.json` («CENSEC API» 2.71.0),
#     schema `Cargas.UploadCargaRequest` — as listas sao `atosCep`, `atosCesdi`
#     e `testamentos` (e `declaracoes`, da CTP). Com os palpites a API
#     ignoraria os atos.
#
#     E o conteudo tambem muda: o contrato quer os vocabularios por NOME
#     (`Cpf`, `DivorcioDireto`, `Marco`). Quem traduz e `censec_api`, e
#     `gerar` passa a escrever o arquivo pela mesma traducao — o arquivo e a
#     API levam exatamente o mesmo corpo.
ENVELOPE_CHAVES = {"CEP": "atosCep", "CESDI": "atosCesdi", "RCTO": "testamentos"}
ENVELOPE_CONFERIDO = True


def cabecalho(cns: str, ano: int, mes: int, quinzena: int) -> dict:
    """O cabecalho da carga, igual para as tres centrais."""
    return {
        "Cns": int(so_digitos(cns) or 0),
        "quinzena": {
            "anoReferencia": ano,
            "quinzenaReferencia": quinzena,
            "mesReferencia": MESES[mes],
        },
    }


# ------------------------------------------------------------- formatacao

def valor_censec(centavos: int | None) -> str | None:
    """Centavos inteiros -> "1234.56", que e um dos formatos que a CENSEC aceita.

    Feito com divisao inteira de proposito: o valor nunca vira float, nem por
    um instante. O layout aceita virgula ou ponto; ponto evita confusao com o
    separador de milhar.
    """
    if centavos is None:
        return None
    sinal = "-" if centavos < 0 else ""
    n = abs(int(centavos))
    return f"{sinal}{n // 100}.{n % 100:02d}"


def _texto(v: Any, limite: int | None = None) -> str | None:
    """Texto limpo dos caracteres que a CENSEC recusa.

    O layout proibe aspa simples e (!@#$%¨&*); acento passa. Cortar no limite
    e melhor que ter o arquivo inteiro recusado por um nome comprido.
    """
    if v is None:
        return None
    s = " ".join(str(v).split())
    s = s.translate({ord(c): None for c in "'\"!@#$%¨&*"})
    if limite:
        s = s[:limite]
    return s or None


def _data(v: Any) -> str | None:
    """AAAA-MM-DD, que e o formato de data do JSON e do XML."""
    s = str(v or "").strip()
    return s[:10] if len(s) >= 10 else None


def _norm(texto: Any) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(texto or "").upper())
    return "".join(c for c in s if not unicodedata.combining(c)).strip()


# NA PROCURAÇÃO O PROCURADOR É O OUTORGADO — 09/10/2026. A regra do prefixo
# acima foi escrita olhando a ESCRITURA, onde o procurador representa uma
# parte e intervém; na procuração ele é quem RECEBE os poderes, e mandá-lo
# como Interveniente diria à CENSEC que a procuração não tem outorgado.
ATOS_EM_QUE_O_PROCURADOR_E_OUTORGADO = ("PROCURACAO", "PROCURACAO_PREVIDENCIARIA")


def qualidade_cep(qualificacao: Any, tipo_ato: Any = None) -> str | None:
    """O papel gravado no ato vira qualidade da CEP, ou nada.

    Devolver None e proposital: a conferencia transforma isso em impedimento
    com o rotulo exato, e o rotulo novo aparece na tela em vez de virar
    Outorgante por omissao.
    """
    rotulo = _norm(qualificacao)
    if not rotulo:
        return None
    if rotulo in QUALIFICACAO_PARA_CEP:
        return QUALIFICACAO_PARA_CEP[rotulo]
    if (rotulo.startswith(("PROCURADOR", "PROCURADORA"))
            and str(tipo_ato or "").upper() in ATOS_EM_QUE_O_PROCURADOR_E_OUTORGADO):
        return "Outorgado"
    if rotulo.startswith(PREFIXOS_INTERVENIENTE):
        return "Interveniente"
    return None


def regime_bens_censec(texto: Any) -> str | None:
    """O regime gravado no ato, no vocabulário da CESDI.

    13/10/2026: o divórcio 778 grava «COMUNHÃO PARCIAL DE BENS», que é como a
    escritura e a certidão escrevem — e a tabela só conhecia «COMUNHAO PARCIAL».
    O «DE BENS» no fim não muda o regime; tira-se antes de procurar.
    """
    rotulo = _norm(texto)
    if rotulo.endswith(" DE BENS"):
        rotulo = rotulo[: -len(" DE BENS")].strip()
    return REGIME_BENS.get(rotulo)


def tipo_documento(documento: Any, tipo_pessoa: Any = "F") -> str:
    """CPF, CNPJ ou Desconhecido, pelo que o numero e — nao pelo que se supoe."""
    n = so_digitos(documento)
    if len(n) == 11:
        return "CPF"
    if len(n) == 14:
        return "CNPJ"
    return "Desconhecido"


# ------------------------------------------------------------- conferencia

class Impedimento:
    """Um motivo pelo qual um ato nao pode ir na carga.

    Guardado assim, e nao como texto solto, porque a tela agrupa por motivo:
    "213 atos sem valor declarado" e uma pendencia so para o registrador
    resolver, e nao 213 avisos iguais.
    """

    __slots__ = ("campo", "motivo")

    def __init__(self, campo: str, motivo: str):
        self.campo, self.motivo = campo, motivo

    def __repr__(self) -> str:                                    # pragma: no cover
        return f"{self.campo}: {self.motivo}"

    def como_dict(self) -> dict:
        return {"campo": self.campo, "motivo": self.motivo}


def conferir_ato_cep(ato: dict, partes: list[dict]) -> list[Impedimento]:
    """Confere um ato contra o layout da CEP. Lista vazia = pode ir."""
    p: list[Impedimento] = []
    tipo = TIPO_SISTEMA_PARA_CEP.get(ato.get("tipo"))
    if tipo is None:
        p.append(Impedimento("tipo", f"tipo {ato.get('tipo')!r} não é ato da CEP"))
        return p

    if not _data(ato.get("data")):
        p.append(Impedimento("data", "sem data de lavratura"))
    if not _texto(ato.get("livro")):
        p.append(Impedimento("livro", "sem livro — a CENSEC exige"))
    if not _texto(ato.get("folha")):
        p.append(Impedimento("folha", "sem folha — a CENSEC exige"))
    if ato.get("valor_transacao") is None and tipo not in ATOS_SEM_VALOR_DECLARADO:
        p.append(Impedimento("valor",
                             "escritura sem valor declarado — a CEP exige, e o "
                             "valor é o conteúdo do ato"))

    if tipo == 1:      # escritura
        nat = ato.get("natureza_censec")
        if nat is None:
            p.append(Impedimento("naturezaEscritura",
                                 "escritura sem natureza da CENSEC"))
        elif int(nat) not in NATUREZA_ESCRITURA:
            p.append(Impedimento("naturezaEscritura",
                                 f"natureza {nat} não existe na tabela do CNB"))
        elif int(nat) == NATUREZA_EXIGE_REFERENTE and not ato.get("anterior_livro"):
            p.append(Impedimento("referentes",
                                 "rerratificação sem os dados do ato anterior"))

    if tipo == 9 and ato.get("natureza_ata_usucapiao") is None:
        p.append(Impedimento("naturezaAtaNotarialDeUsucapiao",
                             "ata de usucapião sem a natureza"))

    if tipo in EXIGEM_REFERENTE:
        if not ato.get("anterior_livro") or not ato.get("anterior_folha"):
            p.append(Impedimento("referentes",
                                 "ato subsequente sem livro e folha do ato anterior"))
        if not so_digitos(ato.get("anterior_cns")):
            p.append(Impedimento("referentes.cns",
                                 "ato subsequente sem o CNS do cartório de origem"))

    if not partes:
        p.append(Impedimento("partes", "ato sem nenhuma parte — a CEP exige ao menos uma"))
    for parte in partes:
        if not _texto(parte.get("nome")):
            p.append(Impedimento("partes.nome", "parte sem nome"))
        if qualidade_cep(parte.get("qualificacao"), ato.get("tipo")) is None:
            p.append(Impedimento("partes.qualidade",
                                 f"{parte.get('nome') or 'parte'}: qualificação "
                                 f"{parte.get('qualificacao') or '(em branco)'!r} "
                                 "não corresponde a nenhuma qualidade da CEP"))
        doc = so_digitos(parte.get("documento"))
        if doc and documento_valido(doc) is False:
            p.append(Impedimento("partes.numeroDocumento",
                                 f"documento de {parte.get('nome')} não passa no "
                                 "dígito verificador — a CENSEC recusa o arquivo inteiro"))
    return p


def conferir_ato_cesdi(ato: dict, partes: list[dict]) -> list[Impedimento]:
    """Confere um ato contra o layout da CESDI."""
    p: list[Impedimento] = []
    tipo = ato.get("tipo_cesdi")
    if tipo is None or int(tipo) not in TIPO_ATO_CESDI:
        p.append(Impedimento("tipoAtoCesdi", "sem o tipo de ato da CESDI"))
        return p
    tipo = int(tipo)

    if not _data(ato.get("data")):
        p.append(Impedimento("data", "sem data de lavratura"))
    if not _texto(ato.get("livro")):
        p.append(Impedimento("livro", "sem livro"))
    if not _texto(ato.get("folha")):
        p.append(Impedimento("folha", "sem folha"))

    if tipo in (1, 3, 4):    # separacao, conversao, divorcio direto
        if not _data(ato.get("casamento_data")):
            p.append(Impedimento("dataCasamento", "sem data do casamento"))
        if regime_bens_censec(ato.get("regime_bens")) is None:
            p.append(Impedimento("regimeBens",
                                 f"regime {ato.get('regime_bens')!r} não está na "
                                 "tabela da CENSEC"))
        if ato.get("responsavel_menores") is None:
            p.append(Impedimento("responsavel", "sem o responsável pelos filhos menores"))

    minimo, exigidas = MINIMO_PARTES_CESDI.get(tipo, (1, ()))
    aceitas = QUALIDADE_CESDI_POR_ATO.get(tipo, QUALIDADE_CESDI)
    presentes = {parte.get("qualidade_cesdi") for parte in partes}
    if len(partes) < minimo:
        p.append(Impedimento("partes",
                             f"{TIPO_ATO_CESDI[tipo]} exige ao menos {minimo} partes; "
                             f"o ato tem {len(partes)}"))
    for exigida in exigidas:
        if exigida not in presentes:
            p.append(Impedimento("partes.qualidade",
                                 f"{TIPO_ATO_CESDI[tipo]} exige uma parte {exigida}"))
    for parte in partes:
        q = parte.get("qualidade_cesdi")
        if q not in aceitas:
            p.append(Impedimento("partes.qualidade",
                                 f"qualidade {q!r} não vale para {TIPO_ATO_CESDI[tipo]}"))
        doc = so_digitos(parte.get("documento"))
        if doc and documento_valido(doc) is False:
            p.append(Impedimento("partes.documento",
                                 f"documento de {parte.get('nome')} não passa no "
                                 "dígito verificador"))
        if q != "Advogado" and tipo in (1, 3, 4):
            for campo, rotulo in (("nascimento", "dataNascimento"),
                                  ("sexo", "sexo"),
                                  ("municipio_ibge", "localResidenciaMunicipio")):
                if not parte.get(campo):
                    p.append(Impedimento(f"partes.{rotulo}",
                                         f"{parte.get('nome')}: falta {rotulo}"))
    return p


def conferir_ato_rcto(ato: dict, testador: dict | None) -> list[Impedimento]:
    """Confere um testamento contra o layout do RCTO."""
    p: list[Impedimento] = []
    tipo = ato.get("tipo_testamento")
    if tipo is None or int(tipo) not in TIPO_TESTAMENTO:
        p.append(Impedimento("tipoTestamento", "sem o tipo do testamento"))
        return p
    tipo = int(tipo)

    if not _data(ato.get("data")):
        p.append(Impedimento("dataTestamento", "sem data de lavratura"))
    if not _texto(ato.get("livro")):
        p.append(Impedimento("livro", "sem livro"))
    if not _texto(ato.get("folha")):
        p.append(Impedimento("folha", "sem folha"))

    if testador is None:
        p.append(Impedimento("testador", "testamento sem o testador cadastrado"))
    else:
        cpf = so_digitos(testador.get("documento"))
        if len(cpf) != 11:
            p.append(Impedimento("cpf", "o RCTO exige o CPF do testador"))
        elif documento_valido(cpf) is False:
            p.append(Impedimento("cpf", "CPF do testador não passa no dígito verificador"))
        if not _texto(testador.get("nome")):
            p.append(Impedimento("nome", "testador sem nome"))
        if not _data(testador.get("nascimento")):
            p.append(Impedimento("dataNascimento", "testador sem data de nascimento"))
        if not _texto(testador.get("mae")):
            p.append(Impedimento("nomeMae", "o RCTO exige o nome da mãe do testador"))

    if tipo == 3:    # revogacao
        if not so_digitos(ato.get("anterior_cns")):
            p.append(Impedimento("revogacaoCartorioCns",
                                 "revogação sem o CNS do cartório do testamento revogado"))
        if not _data(ato.get("anterior_data")):
            p.append(Impedimento("revogacaoDataTestamento",
                                 "revogação sem a data do testamento revogado"))
        if not _texto(ato.get("anterior_livro")) or not _texto(ato.get("anterior_folha")):
            p.append(Impedimento("revogacaoLivro",
                                 "revogação sem livro e folha do testamento revogado"))
    return p


# ----------------------------------------------------------------- montagem

def montar_cep(ato: dict, partes: list[dict]) -> dict:
    """O ato da CEP, no formato que a carga espera."""
    tipo = TIPO_SISTEMA_PARA_CEP[ato["tipo"]]
    valor = ato.get("valor_transacao")
    if valor is None and tipo in ATOS_SEM_VALOR_DECLARADO:
        valor = 0
    linha: dict[str, Any] = {
        "tipoAtoCep": tipo,
        "mne": _texto(ato.get("mne")),
        "data": _data(ato.get("data")),
        "livro": _texto(ato.get("livro"), 8),
        "livroComplemento": _texto(ato.get("livro_complemento"), 50),
        "folha": _texto(ato.get("folha"), 4),
        "folhaComplemento": _texto(ato.get("folha_complemento"), 50),
        "valor": valor_censec(valor),
    }
    if tipo == 1:
        linha["naturezaEscritura"] = int(ato["natureza_censec"])
    if tipo == 9:
        linha["naturezaAtaNotarialDeUsucapiao"] = int(ato["natureza_ata_usucapiao"])
    if ato.get("regime_bens"):
        linha["regimeBens"] = regime_bens_censec(ato.get("regime_bens"))
    if ato.get("data_validade"):
        linha["dataValidade"] = _data(ato.get("data_validade"))

    if tipo in EXIGEM_REFERENTE or \
            (tipo == 1 and int(ato.get("natureza_censec") or 0) == NATUREZA_EXIGE_REFERENTE):
        linha["referentes"] = [{
            "tipoAtoCep": int(ato.get("anterior_tipo_cep") or 2),
            "cns": so_digitos(ato.get("anterior_cns")),
            "livro": _texto(ato.get("anterior_livro"), 20),
            "livroComplemento": _texto(ato.get("anterior_livro_complemento"), 50),
            "folha": _texto(ato.get("anterior_folha"), 10),
            "folhaComplemento": _texto(ato.get("anterior_folha_complemento"), 50),
        }]

    # O filtro de vazios vale tambem DENTRO da parte, e nao so no ato.
    # Sem isso o arquivo saia com "identidade": null e "orgaoEmissor": null em
    # toda parte sem RG — passou nos testes e so apareceu quando eu abri o
    # arquivo e li. Campo nulo que o layout nao pede e sujeira no que a central
    # arquiva.
    linha["partes"] = [{k: v for k, v in {
        "nome": _texto(parte.get("nome"), 150),
        "tipoDocumento": tipo_documento(parte.get("documento"),
                                        parte.get("tipo_pessoa")),
        "numeroDocumento": so_digitos(parte.get("documento")) or None,
        "identidade": _texto(parte.get("rg"), 20),
        "orgaoEmissor": _texto(parte.get("rg_orgao"), 20),
        "qualidade": qualidade_cep(parte.get("qualificacao"), ato.get("tipo")),
        "estrangeiro": 1 if parte.get("estrangeiro") else 0,
    }.items() if v is not None} for parte in partes]
    return {k: v for k, v in linha.items() if v is not None}


def montar_cesdi(ato: dict, partes: list[dict]) -> dict:
    """O ato da CESDI.

    O advogado nunca e a primeira parte da lista: o layout diz, no item 5, que
    o registro do advogado nao deve ser o primeiro informado. E por isso que a
    ordenacao abaixo existe, e nao por estetica.
    """
    tipo = int(ato["tipo_cesdi"])
    linha: dict[str, Any] = {
        "tipoAtoCesdi": tipo,
        "mne": _texto(ato.get("mne")),
        "data": _data(ato.get("data")),
        "livro": _texto(ato.get("livro"), 8),
        "livroComplemento": _texto(ato.get("livro_complemento"), 50),
        "folha": _texto(ato.get("folha"), 4),
        "folhaComplemento": _texto(ato.get("folha_complemento"), 50),
    }
    if tipo in (1, 3, 4):
        linha.update({
            "dataCasamento": _data(ato.get("casamento_data")),
            "regimeBens": regime_bens_censec(ato.get("regime_bens")),
            "quantidadeFilhosMaiores": ato.get("filhos_maiores"),
            "quantidadeFilhosMenores": ato.get("filhos_menores"),
            "responsavel": ato.get("responsavel_menores"),
        })

    ordenadas = sorted(partes, key=lambda p: p.get("qualidade_cesdi") == "Advogado")
    linha["partes"] = []
    for parte in ordenadas:
        qualidade = parte.get("qualidade_cesdi")
        documentos = []
        doc = so_digitos(parte.get("documento"))
        if doc:
            documentos.append({
                "documentoTipo": tipo_documento(doc, parte.get("tipo_pessoa")),
                "prioridade": "Primario",       # o CPF vai sempre como primario
                "documento": doc,
            })
        if qualidade == "Advogado" and parte.get("oab_uf"):
            documentos.append({"documentoTipo": "OAB", "prioridade": "Secundario",
                               "documento": _texto(parte.get("rg"), 20),
                               "uf": _texto(parte.get("oab_uf"), 2)})
        elif parte.get("rg"):
            documentos.append({"documentoTipo": "RG", "prioridade": "Secundario",
                               "documento": _texto(parte.get("rg"), 20)})

        item: dict[str, Any] = {
            "qualidade": qualidade,
            "nome": _texto(parte.get("nome"), 150),
            "estrangeiro": bool(parte.get("estrangeiro")),
            "documentos": documentos,
        }
        # O advogado nao leva qualificacao pessoal: o layout manda deixar em
        # branco a data de nascimento e os campos seguintes.
        if qualidade != "Advogado":
            item.update({
                "conjugeTipo": parte.get("conjuge_tipo"),
                "dataNascimento": _data(parte.get("nascimento")),
                "localNascimentoPais": _texto(parte.get("pais_nascimento"), 150),
                "localNascimentoUF": _texto(parte.get("uf_nascimento"), 2),
                "localResidenciaPais": _texto(parte.get("pais_residencia"), 150),
                "localResidenciaMunicipio": so_digitos(parte.get("municipio_ibge")) or None,
                "localResidenciaUF": _texto(parte.get("uf_residencia"), 2),
                "sexo": _texto(parte.get("sexo"), 1),
            })
        linha["partes"].append({k: v for k, v in item.items() if v is not None})
    return {k: v for k, v in linha.items() if v is not None}


def montar_rcto(ato: dict, testador: dict) -> dict:
    """O testamento do RCTO. Testemunha nao entra: a central so quer o testador."""
    linha: dict[str, Any] = {
        "tipoTestamento": int(ato["tipo_testamento"]),
        "mne": _texto(ato.get("mne")),
        "cpf": so_digitos(testador.get("documento")),
        "nome": _texto(testador.get("nome"), 150),
        "dataNascimento": _data(testador.get("nascimento")),
        "nomeMae": _texto(testador.get("mae"), 150),
        "nomePai": _texto(testador.get("pai"), 150),
        "dataTestamento": _data(ato.get("data")),
        "livro": _texto(ato.get("livro"), 8),
        "livroComplemento": _texto(ato.get("livro_complemento"), 50),
        "folha": _texto(ato.get("folha"), 4),
        "folhaComplemento": _texto(ato.get("folha_complemento"), 50),
        "observacoes": _texto(ato.get("observacao"), 1000),
    }
    if int(ato["tipo_testamento"]) == 3:
        linha.update({
            "revogacaoCartorioCns": so_digitos(ato.get("anterior_cns")),
            "revogacaoDataTestamento": _data(ato.get("anterior_data")),
            "revogacaoLivro": _texto(ato.get("anterior_livro"), 8),
            "revogacaoFolha": _texto(ato.get("anterior_folha"), 4),
        })
    return {k: v for k, v in linha.items() if v is not None}


# ------------------------------------------------------------------ carga

CONFERENCIA = {"CEP": conferir_ato_cep, "CESDI": conferir_ato_cesdi}


# A TRAVA DA LAVRATURA — ordem do oficial em 09/10/2026: «cria travas na
# lavratura quando tivermos esses problemas e nao for possivel enviar pra
# censec». Os casos que a pediram, medidos na produção no mesmo dia:
#
#   - procuração do livro 28, fl. 47 (ato 791): lavrada, selada e trasladada
#     com «[OUTORGADO(S) — QUALIFIQUE A PARTE NO ATO]» no lugar do procurador.
#     A tela já AVISAVA o campo em branco ao montar o teor; avisar não bastou.
#   - procuração do livro 28, fl. 46 (ato 788): três das quatro partes sem
#     qualificação, e a CEP exige uma por parte — o ato ficou fora da quinzena.
#
# A conferência é A MESMA da remessa (`CONFERENCIA`), e não uma parecida: a
# trava e a carga dizendo coisas diferentes é como um ato passa por uma e
# para na outra. Ficam de fora só os campos que a própria lavratura
# preenche — livro, folha e data saem do lançamento, e antes dele faltam
# sempre.
PREENCHE_A_LAVRATURA = frozenset({"livro", "folha", "data", "dataTestamento"})

# E O QUE NÃO TEM ONDE SER CORRIGIDO ANTES DE LAVRAR TAMBÉM NÃO TRAVA — o
# mesmo raciocínio da CESDI, campo a campo. O ato anterior de OUTRA serventia
# (revogação, renúncia, substabelecimento) só se informa depois, na tela das
# anotações pendentes, que existe para isso; e a natureza da ata de usucapião
# não tem campo. Achado pelo teste `test_a_tela_de_pendentes_lista_e_esvazia`,
# que lavra a revogação antes de vinculá-la. A remessa continua acusando.
SEM_ONDE_CORRIGIR_ANTES = frozenset({"referentes", "referentes.cns",
                                     "naturezaAtaNotarialDeUsucapiao"})

# A CESDI e o RCTO NÃO TRAVAM, e não por esquecimento: os campos que elas
# exigem (data do casamento, regime, responsável pelos menores, qualidade da
# CESDI, tipo de testamento) não têm onde ser preenchidos na tela do ato —
# medido em 09/10/2026. Trava sem saída pararia todo divórcio e todo
# testamento; o aviso continua na tela da remessa, que é onde ele já aparece.
CENTRAIS_QUE_TRAVAM = ("CEP",)


def central_do_ato(ato: dict) -> str | None:
    """Para qual central da CENSEC o ato vai — a mesma regra de `separar`."""
    if ato.get("tipo_cesdi") is not None:
        return "CESDI"
    if (ato.get("tipo") or "") == "TESTAMENTO" or ato.get("tipo_testamento") is not None:
        return "RCTO"
    if ato.get("tipo") in TIPO_SISTEMA_PARA_CEP:
        return "CEP"
    return None


def impedimentos_para_lavrar(con: sqlite3.Connection, ato: dict) -> list[Impedimento]:
    """O que impediria este ato de ir à CENSEC, dito ANTES de lavrar.

    Lista vazia: pode lavrar. Não grava nada.
    """
    central = central_do_ato(ato)
    if central not in CENTRAIS_QUE_TRAVAM:
        return []
    problemas = CONFERENCIA[central](ato, _partes_do_ato(con, ato["id"]))
    return [p for p in problemas
            if p.campo not in PREENCHE_A_LAVRATURA | SEM_ONDE_CORRIGIR_ANTES]


def _partes_do_ato(con: sqlite3.Connection, ato_id: int) -> list[dict]:
    """As partes com o que a CENSEC pede — inclusive o que so o cartao tem.

    A data de nascimento, o sexo e o nome da mae nao ficam na parte do ato:
    ficam no cartao de autografo. A CESDI e o RCTO exigem esses tres, entao a
    parte sem cartao nao tem como ir — e a conferencia diz isso com todas as
    letras, em vez de mandar campo vazio e esperar a central recusar.
    """
    linhas = con.execute("""
        SELECT p.*, c.nascimento, c.sexo, c.mae, c.pai, c.rg, c.rg_orgao,
               c.cidade, c.uf, c.nacionalidade
          FROM nt_ato_partes p
          LEFT JOIN nt_cartoes c ON c.id = p.cartao_id
         WHERE p.ato_id = ?
         ORDER BY p.ordem, p.id""", (ato_id,)).fetchall()
    return [dict(linha) for linha in linhas]


def separar(con: sqlite3.Connection, central: str, ano: int, mes: int,
            quinzena: int) -> dict:
    """Separa os atos da quinzena em aptos e impedidos.

    Nao grava nada. Serve tanto para a tela de conferencia quanto para a
    geracao — a mesma conta, para nao existir a chance de a tela dizer uma
    coisa e o arquivo levar outra.
    """
    inicio, fim = periodo_da_quinzena(ano, mes, quinzena)
    tipos = tuple(TIPO_SISTEMA_PARA_CEP) if central == "CEP" else ()
    onde = "a.data BETWEEN ? AND ? AND a.situacao = 'LAVRADO'"
    args: list[Any] = [inicio, fim]
    if central == "CEP":
        # "Na CEP devem ser informadas todas as ESCRITURAS, PROCURACOES e ATAS
        # NOTARIAIS, EXCETO aquelas que se enquadram nos informes da RCTO e
        # CESDI, que devem ser informadas somente nestas centrais." O ato que
        # ja tem tipo da CESDI ou do RCTO nao entra aqui — mandar nas duas
        # produz o mesmo ato em duas centrais.
        onde += f" AND a.tipo IN ({','.join('?' * len(tipos))})"
        onde += " AND a.tipo_cesdi IS NULL AND a.tipo_testamento IS NULL"
        args += list(tipos)
    elif central == "CESDI":
        onde += " AND a.tipo_cesdi IS NOT NULL"
    elif central == "RCTO":
        onde += " AND a.tipo = 'TESTAMENTO'"

    # Ja enviado nao vai de novo: item confirmado em remessa anterior fica de
    # fora. Rejeitado volta, que e o ponto de poder reenviar.
    onde += """ AND NOT EXISTS (
                    SELECT 1 FROM nt_remessa_itens i
                      JOIN nt_remessas r ON r.id = i.remessa_id
                     WHERE i.ato_id = a.id AND r.central = ?
                       AND i.situacao IN ('ENVIADA', 'CONFIRMADA'))"""
    args.append(central)

    aptos, impedidos = [], []
    for linha in con.execute(f"SELECT a.* FROM nt_atos a WHERE {onde} "
                             "ORDER BY a.data, COALESCE(a.termo, a.numero_ordem), a.id", args):
        ato = dict(linha)
        partes = _partes_do_ato(con, ato["id"])
        if central == "RCTO":
            testador = next((p for p in partes if _norm(p.get("qualificacao")) in
                             ("TESTADOR", "OUTORGANTE")), None)
            problemas = conferir_ato_rcto(ato, testador)
            montado = montar_rcto(ato, testador) if not problemas else None
        else:
            problemas = CONFERENCIA[central](ato, partes)
            montado = None
            if not problemas:
                montado = (montar_cep if central == "CEP" else montar_cesdi)(ato, partes)
        if problemas:
            impedidos.append({"ato": ato, "problemas": [x.como_dict() for x in problemas]})
        else:
            aptos.append({"ato": ato, "linha": montado})

    return {
        "central": central, "ano": ano, "mes": mes, "quinzena": quinzena,
        "periodo_inicio": inicio, "periodo_fim": fim,
        "prazo": prazo_de_fechamento(ano, mes, quinzena),
        "aptos": aptos, "impedidos": impedidos,
    }


def gerar(con: sqlite3.Connection, central: str, ano: int, mes: int,
          quinzena: int, cns: str) -> dict:
    """Monta a carga da quinzena e devolve o texto do arquivo e o resumo.

    Nao grava o arquivo em disco e nao registra a remessa: quem faz isso e a
    tela, dentro da transacao, para que a contagem gravada seja a contagem do
    arquivo — e nao a que o gerador achou que ia escrever.
    """
    # O CORPO E O DA API, pela traducao de `censec_api` (importada aqui dentro
    # porque ela importa este modulo). Ate 09/10/2026 o arquivo levava os
    # codigos numericos e as listas com o nome errado — ver ENVELOPE_CHAVES.
    import censec_api as CA
    separado = separar(con, central, ano, mes, quinzena)
    carga = CA.cabecalho(cns, ano, mes, quinzena)
    chave, traduzir = CA.TRADUTOR[central]
    carga[chave] = [traduzir(x["linha"]) for x in separado["aptos"]]

    # UTF-8 sem BOM, como o layout exige. ensure_ascii=False para o acento sair
    # como acento, que a CENSEC aceita e prefere.
    texto = json.dumps(carga, ensure_ascii=False, indent=2)
    separado.update({
        "texto": texto,
        "sha256": hashlib.sha256(texto.encode("utf-8")).hexdigest(),
        "quantidade": len(separado["aptos"]),
        "arquivo_nome": f"{central.lower()}_{ano:04d}{mes:02d}_q{quinzena}.json",
        "envelope_conferido": ENVELOPE_CONFERIDO,
    })
    return separado


def resumo_impedimentos(impedidos: list[dict]) -> list[dict]:
    """Agrupa os motivos, do mais comum para o menos.

    Uma lista de 213 avisos iguais nao ajuda ninguem. "213 atos sem valor
    declarado" e uma pendencia so, e da para resolver de uma vez.
    """
    contas: dict[tuple[str, str], int] = {}
    for item in impedidos:
        for problema in item["problemas"]:
            chave = (problema["campo"], problema["motivo"])
            contas[chave] = contas.get(chave, 0) + 1
    return [{"campo": campo, "motivo": motivo, "atos": n}
            for (campo, motivo), n in sorted(contas.items(), key=lambda x: -x[1])]
