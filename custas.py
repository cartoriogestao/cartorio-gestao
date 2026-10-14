"""
O motor de custas do nucleo — emolumento, fundos, gratuidade e vigencia, para
as SEIS atribuicoes.

O QUE ESTE MODULO ACRESCENTA A `emolumentos.py`
    `emolumentos.py` importa a tabela do E-Oficio e sabe consultar valor de
    servico e faixa de valor. E bom e continua sendo a fonte. Faltavam quatro
    coisas, e sao elas que estao aqui:

      1. VIGENCIA POR DATA. `emolumentos` responde "quanto custa hoje". Quem
         relavra ato de marco de 2023, ou reimprime recibo de 2024, precisa de
         "quanto custava naquele dia". A tabela do E-Oficio tem as 18 vigencias
         com data de inicio e fim; o nosso banco guardava so a marca `vigente`.

      2. GRATUIDADE. Nove itens da tabela do Tribunal declaram isencao no
         PROPRIO TEXTO, com a lei citada. Estavam sendo lidos como valor
         qualquer. Um deles — 14.10.1 — e exatamente o caso de 18/08/2026:
         "e vedada a cobranca de emolumentos em decorrencia da pratica de ato
         retificado, refeito ou renovado em razao de erro imputavel" a
         serventia.

      3. CONFERENCIA DOS FUNDOS. Cada fundo tem percentual em lei; o valor que
         se cobra e o da tabela. Quando os dois divergem, o sistema mostra a
         divergencia em vez de escolher sozinho.

      4. O TOTAL, e o que NAO entra nele. Ver abaixo.

O ISS NAO ENTRA NA CONTA DO CLIENTE, E ISTO FOI CONFERIDO
    O cadastro de fundos do E-Oficio tem CINCO linhas: FERC 3%, FEMP 4%,
    FADP 4%, ISS 5% e FERRFIS 1%. Eu havia escrito, em `atribuicoes.py`, que
    "sao eles que aparecem na linha do selo". Nao sao. Conferindo:

      - nos 39 textos de selo reais, um por prefixo: FERC em 39, FADEP em 38,
        FEMP em 38, FERRFIS em 4 e **ISS em ZERO**;
      - na tabela de precos (`tbServico_Tabela`) existem quatro colunas de
        fundo — FERMOJUPI, MP, DP e ferrfis — e **nenhuma de ISS**;
      - em 400 valores reais da vigencia de 2026, o total fecha ao centavo com
        emolumento + os quatro. Somar 5% de ISS cobraria 5% a mais de todo
        mundo.

    O ISS e o imposto municipal sobre o servico, devido pelo delegatario ao
    Municipio — nao e repasse cobrado da parte no balcao. Fica registrado aqui
    como fundo conhecido e com `no_total=False`, para nunca mais ser somado por
    quem ler a lista de cinco e supor.

OS PERCENTUAIS BATEM, MENOS UM
    Em 400 valores da vigencia de 2026 e 60 faixas, os quatro percentuais
    fecham ao centavo. A unica excecao e o item 15.17 (registro de conjunto de
    documentos de arquivo, por folha): emolumento R$ 0,71 e FERC R$ 0,05, onde
    3% dariam R$ 0,02. Sobre setenta e um centavos, e arredondamento da origem.
    Esta em `DIVERGENCIAS_CONHECIDAS` para que a tela de conferencia nao o
    aponte todo dia como se fosse novidade.

FUNDAMENTO
    Lei 9.534/1997 e Lei estadual (MA) n. 9.490/2011 — gratuidade do registro
        de nascimento e obito e da primeira certidao.
    Lei 6.015/1973, art. 30.
    Lei 13.465/2017 — Reurb-S.
    Lei 9.492/1997 — protesto.
    Resolucao-GP TJMA n. 143/2025 — tabela de emolumentos, itens 13 a 17.
    Codigo de Normas do Foro Extrajudicial do Maranhao — Provimento TJMA n. 28,
        de 23/04/2026.

    Os textos de gratuidade abaixo sao TRANSCRITOS da tabela do Tribunal, e nao
    resumidos por mim. Onde a tabela cita a lei, a citacao vem com ela.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import Any

import emolumentos
from caixa_schema import centavos, reais


class CustasError(ValueError):
    """Impedimento de regra, com mensagem pronta para a tela."""


# ------------------------------------------------------------------ fundos
#
# `sigla` e o que sai no recibo. `no_total` diz se entra na conta da parte.

FUNDOS: tuple[dict, ...] = (
    {"campo": "ferc", "sigla": "FERC", "percentual": 3, "no_total": True,
     "nome": "Fundo Especial de Modernização e Reaparelhamento do Judiciário",
     "coluna_origem": "curFERMOJUPI"},
    {"campo": "femp", "sigla": "FEMP", "percentual": 4, "no_total": True,
     "nome": "Fundo Especial do Ministério Público Estadual",
     "coluna_origem": "curValor_MP"},
    {"campo": "fadep", "sigla": "FADEP", "percentual": 4, "no_total": True,
     "nome": "Fundo de Aparelhamento da Defensoria Pública do Maranhão",
     "coluna_origem": "curValor_DP"},
    {"campo": "ferrfis", "sigla": "FERRFIS", "percentual": 1, "no_total": True,
     "nome": "Fundo Especial Registral de Regularização Fundiária de Interesse Social",
     "coluna_origem": "curvalor_ferrfis"},
    {"campo": "iss", "sigla": "ISS", "percentual": 5, "no_total": False,
     "nome": "Imposto Sobre Serviços (municipal, devido pelo delegatário)",
     "coluna_origem": None},
)

CAMPOS_NO_TOTAL: tuple[str, ...] = tuple(
    f["campo"] for f in FUNDOS if f["no_total"])

PERCENTUAIS: dict[str, int] = {f["campo"]: f["percentual"] for f in FUNDOS}

# O que a origem arredondou e nao vale reportar como novidade todo dia.
DIVERGENCIAS_CONHECIDAS: tuple[dict, ...] = (
    {"codigo_tj": "15.17", "servico": 640, "campo": "ferc",
     "emolumento": "0,71", "na_tabela": "0,05", "pelo_percentual": "0,02",
     "observacao": "arredondamento da origem sobre valor de centavos"},
)


# -------------------------------------------------------------- gratuidade
#
# Os NOVE itens que a tabela do Tribunal declara isentos no proprio texto.
# Transcritos da origem em 21/08/2026, com a lei que ela cita.

GRATUIDADES: tuple[dict, ...] = (
    {"codigo_tj": "14.a", "servico": 861, "atribuicao": 6,
     "rotulo": "Registro de nascimento e primeira certidão",
     "texto": "Registro de nascimento, bem como pela primeira certidão "
              "respectiva. Isento.",
     "fundamento": "Lei n. 9.490, de 04/11/2011 (MA); Lei n. 9.534/1997",
     "compensavel": False, "item_de_compensacao": None},
    {"codigo_tj": "14.b", "servico": 862, "atribuicao": 6,
     "rotulo": "Registro de nascimento em Central ou Posto público",
     "texto": "Registro de nascimento realizado pelas Centrais ou Postos de "
              "Registro mantidos pelo poder público, bem como pela primeira "
              "certidão respectiva. Isento.",
     "fundamento": "Lei n. 9.490, de 04/11/2011 (MA)",
     "compensavel": False, "item_de_compensacao": None},
    {"codigo_tj": "14.c", "servico": 863, "atribuicao": 6,
     "rotulo": "Assento de óbito e primeira certidão",
     "texto": "Assento de óbito, bem como pela primeira certidão respectiva. "
              "Isento.",
     "fundamento": "Lei n. 9.490, de 04/11/2011 (MA); Lei n. 9.534/1997",
     "compensavel": False, "item_de_compensacao": None},
    {"codigo_tj": "14.d", "servico": 864, "atribuicao": 6,
     "rotulo": "Assento de natimorto e primeira certidão",
     "texto": "Assento de natimorto, bem como pela primeira certidão "
              "respectiva. Isento.",
     "fundamento": "Lei n. 9.490, de 04/11/2011 (MA)",
     "compensavel": False, "item_de_compensacao": None},
    {"codigo_tj": "14.13", "servico": 883, "atribuicao": 6,
     "rotulo": "Registro tardio",
     "texto": "Procedimento administrativo para o registro tardio — isento — "
              "para fins de compensação os emolumentos serão os do item 14.5.1.",
     "fundamento": "Tabela XIV, item 14.13",
     "compensavel": True, "item_de_compensacao": "14.5.1"},
    {"codigo_tj": "14.1.8", "servico": 850, "atribuicao": 6,
     "rotulo": "Casamento comunitário do Poder Judiciário",
     "texto": "Serão isentos de quaisquer emolumentos todos os atos "
              "necessários à realização do projeto Casamentos Comunitários "
              "organizado pelo Poder Judiciário.",
     "fundamento": "Tabela XIV, item 14.1.8",
     "compensavel": False, "item_de_compensacao": None},
    {"codigo_tj": "14.10.1", "servico": 1280, "atribuicao": 6,
     "rotulo": "Ato refeito por erro da serventia",
     "texto": "É vedada a cobrança de emolumentos em decorrência da prática "
              "de ato retificado, refeito ou renovado em razão de erro "
              "imputável ao serviço registral.",
     "fundamento": "Tabela XIV, item 14.10.1",
     "compensavel": False, "item_de_compensacao": None},
    {"codigo_tj": "16.38", "servico": 1478, "atribuicao": 5,
     "rotulo": "Reurb-S — regularização fundiária de interesse social",
     "texto": "Serão gratuitos os emolumentos dos atos registrais "
              "relacionados à Reurb de interesse social (Reurb-S).",
     "fundamento": "Lei n. 13.465/2017; Tabela XVI, item 16.38",
     "compensavel": False, "item_de_compensacao": None},
    {"codigo_tj": "17.8", "servico": 1580, "atribuicao": 2,
     "rotulo": "Protesto por mandado judicial a beneficiário de assistência",
     "texto": "Serão isentos de emolumentos os atos praticados em cumprimento "
              "de mandado judicial expedido em favor da parte beneficiária de "
              "assistência judiciária.",
     "fundamento": "Tabela XVII, item 17.8",
     "compensavel": False, "item_de_compensacao": None},
)

# Gratuidade que NAO esta na tabela de precos porque nao depende do ato, e sim
# de quem pede. Fica aqui com o que o balcao precisa exigir antes de dar.
GRATUIDADES_POR_PESSOA: tuple[dict, ...] = (
    {"codigo": "HIPOSSUFICIENCIA",
     "rotulo": "Hipossuficiência declarada",
     "texto": "Isenção a quem declara não ter condição de pagar sem prejuízo "
              "do próprio sustento ou do da família.",
     "fundamento": "CF, art. 5º, LXXVI; Lei n. 1.060/1950; CPC, art. 98",
     "exige": "declaração de hipossuficiência assinada, arquivada no ato"},
    {"codigo": "ASSISTENCIA_JUDICIARIA",
     "rotulo": "Beneficiário de assistência judiciária",
     "texto": "Isenção por deferimento judicial de gratuidade de justiça.",
     "fundamento": "CPC, art. 98; Tabela XVII, item 17.8",
     "exige": "cópia da decisão que deferiu a gratuidade"},
    {"codigo": "ART_347_CPF",
     "rotulo": "Averbação de CPF (art. 347)",
     "texto": "Averbação gratuita do CPF nos assentos anteriores ao "
              "Provimento nº 63/2017, na forma do art. 347 do Código de "
              "Normas do TJMA.",
     "fundamento": "art. 347 do Código de Normas do TJMA",
     "exige": "conferência do número do CPF antes de averbar"},
)

_POR_CODIGO_TJ = {g["codigo_tj"]: g for g in GRATUIDADES}
_POR_SERVICO = {g["servico"]: g for g in GRATUIDADES}


def gratuidade(codigo_tj: str | None = None,
               servico: int | None = None) -> dict | None:
    """A gratuidade declarada na tabela para este item, ou None."""
    if codigo_tj and str(codigo_tj).strip() in _POR_CODIGO_TJ:
        return dict(_POR_CODIGO_TJ[str(codigo_tj).strip()])
    if servico is not None and int(servico) in _POR_SERVICO:
        return dict(_POR_SERVICO[int(servico)])
    return None


def gratuidade_por_pessoa(codigo: str) -> dict | None:
    """A gratuidade que depende de quem pede, pelo codigo interno."""
    alvo = str(codigo or "").strip().upper()
    for g in GRATUIDADES_POR_PESSOA:
        if g["codigo"] == alvo:
            return dict(g)
    return None


# --------------------------------------------------------------- vigencia


def _dia(valor: Any) -> str:
    """Data em AAAA-MM-DD, aceitando date, datetime ou texto."""
    if valor is None:
        return date.today().isoformat()
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    texto = str(valor).strip()
    if len(texto) >= 10 and texto[4] == "-":
        return texto[:10]
    if len(texto) == 10 and texto[2] == "/":     # 21/08/2026
        d, m, a = texto.split("/")
        return f"{a}-{m}-{d}"
    raise CustasError(f"Data inválida: {valor!r}. Use AAAA-MM-DD.")


def vigencia_do_dia(con: sqlite3.Connection, data: Any = None) -> dict:
    """A vigencia que valia naquele dia. So LE.

    Devolve sempre um dicionario, com `exata=False` quando teve de recorrer a
    vigencia marcada como corrente. Marcar isso importa: cobrar por tabela de
    outro ano e devolucao de emolumento, e quem confere precisa ver que a data
    nao casou com nenhuma faixa.
    """
    dia = _dia(data)
    colunas = {linha[1] for linha in con.execute("PRAGMA table_info(cx_vigencias)")}
    if {"inicio", "fim"} <= colunas:
        linha = con.execute(
            """SELECT codigo, descricao, inicio, fim FROM cx_vigencias
                WHERE inicio IS NOT NULL AND inicio <= ?
                  AND (fim IS NULL OR fim >= ?)
                ORDER BY inicio DESC LIMIT 1""", (dia, dia)).fetchone()
        if linha:
            return {"codigo": int(linha["codigo"]), "descricao": linha["descricao"],
                    "inicio": linha["inicio"], "fim": linha["fim"],
                    "dia": dia, "exata": True}
    corrente = con.execute(
        "SELECT codigo, descricao FROM cx_vigencias WHERE vigente=1").fetchone()
    if not corrente:
        raise CustasError(
            "Não há tabela de emolumentos carregada. Importe a tabela do "
            "E-Ofício antes de cobrar.")
    return {"codigo": int(corrente["codigo"]), "descricao": corrente["descricao"],
            "inicio": None, "fim": None, "dia": dia, "exata": False}


# ---------------------------------------------------------------- conferir


def conferir_fundos(emolumento_centavos: int, valores: dict[str, int], *,
                    codigo_tj: str | None = None,
                    tolerancia: int = 1) -> list[dict]:
    """Compara cada fundo com o seu percentual em lei. So calcula.

    Devolve a lista de divergencias. Nao corrige nada: o valor que se cobra e
    o da tabela do Tribunal. Corrigir por conta propria seria inventar preco.
    """
    conhecidas = {(d["codigo_tj"], d["campo"]) for d in DIVERGENCIAS_CONHECIDAS}
    achados = []
    for f in FUNDOS:
        if not f["no_total"]:
            continue
        campo = f["campo"]
        cobrado = int(valores.get(campo) or 0)
        esperado = int(round(emolumento_centavos * f["percentual"] / 100))
        if abs(cobrado - esperado) <= tolerancia:
            continue
        if (str(codigo_tj), campo) in conhecidas:
            continue
        achados.append({
            "campo": campo, "sigla": f["sigla"], "percentual": f["percentual"],
            "cobrado": reais(cobrado), "pelo_percentual": reais(esperado),
            "diferenca": reais(cobrado - esperado),
            "frase": (f"{f['sigla']} está em {reais(cobrado)} e "
                      f"{f['percentual']}% do emolumento dariam "
                      f"{reais(esperado)}."),
        })
    return achados


# ----------------------------------------------------------------- calcular


def calcular(con: sqlite3.Connection, *, servico: int | None = None,
             tabela: int | None = None, base: Any = None,
             quantidade: int = 1, data: Any = None,
             gratuidade_codigo: str | None = None,
             motivo_gratuidade: str | None = None) -> dict:
    """Quanto custa um ato, pela tabela do dia dele.

    Dois caminhos, como em `emolumentos.calcular_item`:
      `servico`          ato de valor fixo;
      `tabela` + `base`  ato que depende do valor do negócio.

    E tres saidas que aquele nao tinha:
      `gratuidade`   se a tabela declara isencao, ou se o balcao invocou uma;
      `vigencia`     qual tabela foi usada, e se casou com a data;
      `conferencia`  as divergencias entre a tabela e os percentuais em lei.

    Ato gratuito devolve total zero E os valores que TERIA — o selo de ato
    isento e emitido do mesmo jeito, e o valor compensavel precisa aparecer.
    """
    if servico is None and tabela is None:
        raise CustasError("Informe o serviço ou a tabela de faixas.")
    vig = vigencia_do_dia(con, data)
    item = emolumentos.calcular_item(
        con, servico=servico, tabela=tabela, base=base,
        quantidade=max(1, int(quantidade or 1)), vigencia=vig["codigo"])
    if not item:
        onde = f"serviço {servico}" if servico is not None else f"tabela {tabela}"
        raise CustasError(
            f"Não achei o {onde} na tabela de {vig['descricao'] or vig['codigo']}. "
            f"Confira o código do ato ou reimporte a tabela.")

    valores = {c: centavos(item.get(c)) for c in CAMPOS_NO_TOTAL}
    emol = centavos(item.get("emolumentos"))
    total_devido = emol + sum(valores.values())

    isencao = gratuidade(item.get("codigo_tj"), servico)
    invocada = gratuidade_por_pessoa(gratuidade_codigo) if gratuidade_codigo else None
    if gratuidade_codigo and not invocada:
        raise CustasError(
            f"Gratuidade {gratuidade_codigo!r} não existe. As que existem são: "
            f"{', '.join(g['codigo'] for g in GRATUIDADES_POR_PESSOA)}.")
    if invocada and not (motivo_gratuidade or "").strip():
        raise CustasError(
            f"{invocada['rotulo']} exige registrar o motivo e "
            f"{invocada['exige']}.")

    gratuito = bool(isencao or invocada)
    a_cobrar = 0 if gratuito else total_devido

    saida = dict(item)
    saida.update({
        "vigencia": vig["codigo"],
        "vigencia_descricao": vig["descricao"],
        "vigencia_exata": vig["exata"],
        "data": vig["dia"],
        "gratuito": gratuito,
        "gratuidade": isencao or invocada,
        "motivo_gratuidade": (motivo_gratuidade or "").strip() or None,
        "compensavel": bool(isencao and isencao.get("compensavel")),
        "item_de_compensacao": (isencao or {}).get("item_de_compensacao"),
        "emolumento_centavos": emol,
        "total_devido": reais(total_devido),
        "total_devido_centavos": total_devido,
        "total": reais(a_cobrar),
        "total_centavos": a_cobrar,
        "iss_no_total": False,
        "conferencia": conferir_fundos(emol, valores,
                                       codigo_tj=item.get("codigo_tj")),
    })
    if not vig["exata"]:
        saida.setdefault("avisos", []).append(
            f"A data {vig['dia']} não casou com nenhuma vigência com período "
            f"gravado; foi usada a tabela marcada como corrente "
            f"({vig['descricao'] or vig['codigo']}). Confira antes de cobrar.")
    return saida


def somar(itens: list[dict]) -> dict:
    """Soma uma conta de varios itens, separando o que e gratuito.

    O gratuito entra com zero no que se cobra e com o valor cheio no que se
    compensa. Sao duas colunas diferentes do relatorio da COGEX, e somar tudo
    junto e o erro que faz a serventia pedir compensacao de ato pago.
    """
    campos = ("emolumentos",) + CAMPOS_NO_TOTAL
    soma = {c: 0 for c in campos}
    cobrado = devido = compensavel = 0
    for i in itens:
        gratis = bool(i.get("gratuito"))
        for c in campos:
            soma[c] += centavos(i.get(c))
        devido += centavos(i.get("total_devido") or i.get("total"))
        cobrado += 0 if gratis else centavos(i.get("total_devido") or i.get("total"))
        if gratis and i.get("compensavel"):
            compensavel += centavos(i.get("total_devido") or i.get("total"))
    return {
        **{c: reais(v) for c, v in soma.items()},
        "total_devido": reais(devido), "total_devido_centavos": devido,
        "total": reais(cobrado), "total_centavos": cobrado,
        "gratuito": reais(devido - cobrado),
        "gratuito_centavos": devido - cobrado,
        "compensavel": reais(compensavel),
        "compensavel_centavos": compensavel,
        "itens": len(itens),
        "gratuitos": sum(1 for i in itens if i.get("gratuito")),
    }
