"""
O selo de fiscalizacao do TJMA — pedido, guarda, texto, cancelamento.

DE ONDE VEM O DESENHO DESTE MODULO
    Nao de manual: de 26.130 selos reais desta serventia, entre 19/03/2020 e
    17/08/2026, com o pedido guardado em `tbSeloIndividual.memJson`, o endereco
    chamado em `strURLAto` e o texto devolvido em `strTextoSelo`.

    Foram esses 26 mil usos que responderam a pergunta que o levantamento tinha
    deixado aberta: o selo NAO vem de um talao consumido localmente. Ele e
    PEDIDO ao selador no momento do ato, e a resposta volta com o codigo, o
    valor e o texto pronto para imprimir. As colunas de "fila de envio ao
    Tribunal" existem no acervo e estao FALSAS nos 26.130 — nunca foram usadas.

O QUE ESTE MODULO FAZ, E O QUE ELE DEIXA PARA DEPOIS
    Faz tudo o que se pode fazer SEM tocar no Tribunal:

      - monta o pedido no formato que o selador espera, que e um por tipo de ato;
      - guarda o selo devolvido, amarrado ao ato, ao livro e a folha;
      - le o texto do selo e separa total, emolumentos e cada fundo;
      - controla o papel de seguranca, que vai declarado dentro do pedido;
      - aponta o selo obtido e nao usado — 1.304 no acervo, 5% do total, dos
        quais so 5 foram cancelados;
      - registra cancelamento COM MOTIVO, que o acervo nao tinha em nenhum dos
        79 selos cancelados.

    Nao faz a chamada de rede. Ela e o ultimo elo, depende de credencial que
    ainda nao temos, e e a parte mais facil de acrescentar depois: `pedir()`
    monta o corpo e devolve o pedido; quem tiver a credencial o despacha.

POR QUE UM MODULO SO PARA AS SEIS ATRIBUICOES
    Porque o selador e um so. Mesmo endereco-base, mesma tabela de custas,
    mesmo formato de resposta, mesmos cinco fundos. O que muda de uma
    atribuicao para outra e o CAMINHO e o CORPO do pedido — e isso e dado,
    declarado abaixo, nao codigo repetido seis vezes.

FUNDAMENTO
    Lei 8.935/1994, art. 30, VIII (fiscalizacao do recolhimento dos
        emolumentos) e art. 37 e ss. (fiscalizacao pelo Poder Judiciario).
    Codigo de Normas do Foro Extrajudicial do Maranhao — Provimento TJMA n. 28,
        de 23/04/2026 — do selo de fiscalizacao.

    Como no resto do sistema: cita-se a secao onde o artigo nao foi lido em
    fonte primaria. Nenhum numero foi inventado.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import atribuicoes as ATR


class SeloError(ValueError):
    """Impedimento de regra, com mensagem pronta para a tela."""


# ------------------------------------------------- os caminhos observados
#
# Tirados de `strURLAto` (26.123 chamadas) e de `tbServico.strURL_Selador`.
# O espaco de nome e /selo/{atribuicao}/{ato}, com quatro atribuicoes
# observadas: notas, civil, imovel e rtdpj.
#
# PROTESTO NAO APARECE. Os selos de protesto existem no acervo — PROTIT,
# LIQTIT, DILIGE, ARQUIV — mas o caminho chamado nao ficou gravado. Fica
# declarado como LACUNA, e nao inventado: pedir selo de protesto levanta erro
# dizendo o que falta, em vez de chutar um endereco.

# Os caminhos que ESTA serventia usou de fato, entre 2020 e 2026. Nao e o
# catalogo — o catalogo oficial, com 181 endpoints, esta em `selador.ENDPOINTS`.
# Isto aqui serve para saber o que ja foi exercitado em producao, que e uma
# informacao diferente e igualmente util: endpoint nunca usado merece um
# primeiro uso com conferencia.
CAMINHOS: dict[str, str] = {
    # Notas — 20.846 chamadas observadas
    "NT_RECONHECIMENTO_FIRMA": "/selo/notas/reconhecimento-firma",
    "NT_AUTENTICACAO": "/selo/notas/autenticacao",
    "NT_CARTAO_ASSINATURA": "/selo/notas/cartao-assinatura",
    "NT_ATOS_EM_GERAL": "/selo/notas/atos-em-geral",
    # Registro Civil — 1.238
    "RC_ATOS_EM_GERAL": "/selo/civil/atos-em-geral",
    # Registro de Imoveis — 829
    "RI_PRENOTACAO": "/selo/imovel/prenotacao",
    # RTD e RCPJ — do cadastro de servicos
    "TDPJ_ATOS_EM_GERAL": "/selo/rtdpj/atos-em-geral",
    "TDPJ_DECLARADO_INTEGRAL_COM_VALOR": "/selo/rtdpj/ato-declarado/integral/com-valor",
    "TDPJ_DECLARADO_INTEGRAL_SEM_VALOR": "/selo/rtdpj/ato-declarado/integral/sem-valor",
    "TDPJ_DECLARADO_RESUMIDO_SEM_VALOR": "/selo/rtdpj/ato-declarado/resumido/sem-valor",
    "TDPJ_BUSCA_ATE_DEZ_ANOS": "/selo/rtdpj/busca-ate-dez-anos",
    "TDPJ_ACIMA_TRES_DILIGENCIAS": "/selo/rtdpj/acima-tres-diligencias",
    "TDPJ_APOSTILA_HAIA": "/selo/rtdpj/apostila-haia",
    "TDPJ_DILIGENCIA_ZONA_URBANA": "/selo/rtdpj/diligencia/zona-urbana",
    "TDPJ_MATRICULA": "/selo/rtdpj/matricula",
    "TDPJ_PJ_AVERBACAO": "/selo/rtdpj/pessoa-juridica/averbacao",
    "TDPJ_PJ_CERTIDAO": "/selo/rtdpj/pessoa-juridica/certidao",
    "TDPJ_TD_CERTIDAO_POR_PECA": "/selo/rtdpj/titulo-documento/certidao/por-peca",
}

# NAO HA MAIS LACUNA DE CAMINHO.
#
# Ontem o caminho do selo de PROTESTO era desconhecido: os selos existiam no
# acervo — PROTIT, LIQTIT, DILIGE, ARQUIV — mas o endereco chamado nao ficara
# gravado. A documentacao oficial do Selador, achada em
# arquivos\\eoficio\\Selo Eletronico\\selador-doc, tem os dez caminhos do protesto e
# mais 171. Estao todos em `selador.ENDPOINTS`, que passa a ser a fonte.
#
# Este dicionario fica, vazio, porque a proxima lacuna vai aparecer — e e melhor
# ela ter lugar do que ser resolvida por chute.
LACUNAS: dict[int, str] = {}


# ------------------------------------------------------- o codigo do selo
#
# 28 caracteres: seis letras do tipo de ato, o CNS de seis digitos, e dezesseis
# de identificacao. Ha 488 selos antigos, de 2020, com 32 digitos hexadecimais.

CODIGO_SELO = re.compile(r"^(?P<tipo>[A-Z]{5,7})(?P<cns>\d{6})(?P<id>[A-Z0-9]{14,20})$")
CODIGO_ANTIGO = re.compile(r"^[0-9A-F]{32}$")

# Os prefixos observados, e quantas vezes cada um foi usado no acervo. Serve de
# vocabulario e de conferencia: prefixo que ninguem nunca usou nesta serventia
# merece um segundo olhar antes de entrar no livro de selos.
PREFIXOS: dict[str, str] = {
    "RECFIR": "Reconhecimento de firma",
    "AUTENT": "Autenticação de cópia",
    "CERTID": "Certidão",
    "ARQUIV": "Arquivamento",
    "PRENOT": "Prenotação",
    "CERINT": "Certidão de inteiro teor",
    "PROTIT": "Protesto de título",
    "CERELE": "Certidão eletrônica",
    "CERIMV": "Certidão de imóvel",
    "DILIGE": "Diligência",
    "LIQTIT": "Liquidação de título",
    "PROCUR": "Procuração",
    "AVESVD": "Averbação sem valor declarado",
    "BUSCAS": "Buscas",
    "MATRIC": "Matrícula",
    "ESCPUB": "Escritura pública",
    "REGTER": "Registro de terreno",
    "REGAVD": "Registro com valor declarado",
    "LOTDES": "Loteamento ou desmembramento",
    "REGNAS": "Registro de nascimento",
    "REGOBT": "Registro de óbito",
    "REGCON": "Registro de condomínio",
    "AVEGEO": "Averbação de georreferenciamento",
    "REGTOR": "Registro de título ou outros",
    "REGBEM": "Registro de bem",
    "REGGAR": "Registro de garantia",
    "RETCAN": "Retificação ou cancelamento",
    "RETFIC": "Retificação de ficha",
    "TRANSC": "Transcrição",
    "REGTIT": "Registro de título",
    # Nove prefixos de BUSCA que aparecem no acervo e cujo significado exato
    # nao esta documentado em lugar nenhum. O que se pode afirmar com seguranca
    # e o miolo do prefixo: RI e Registro de Imoveis, RC e Registro Civil. O
    # resto — a variacao do sufixo, provavelmente a faixa de anos pesquisada —
    # e INFERENCIA, e esta dito que e.
    "BUSRIL": "Busca no Registro de Imóveis (variante do acervo)",
    "BUSRIV": "Busca no Registro de Imóveis (variante do acervo)",
    "BUSRIX": "Busca no Registro de Imóveis (variante do acervo)",
    "BURIXX": "Busca no Registro de Imóveis (variante do acervo)",
    "BURIXV": "Busca no Registro de Imóveis (variante do acervo)",
    "BRIXXX": "Busca no Registro de Imóveis (variante do acervo)",
    "BUSRCL": "Busca no Registro Civil (variante do acervo)",
    "BURCII": "Busca no Registro Civil (variante do acervo)",
    "BRCXXX": "Busca no Registro Civil (variante do acervo)",
}


@dataclass(frozen=True)
class Codigo:
    """Um codigo de selo, decomposto."""

    inteiro: str
    prefixo: str | None
    cns: str | None
    identificacao: str | None
    antigo: bool = False

    @property
    def descricao(self) -> str:
        if self.antigo:
            return "selo em formato antigo (32 dígitos)"
        return PREFIXOS.get(self.prefixo or "", "prefixo não observado nesta serventia")


def ler_codigo(texto: Any) -> Codigo:
    """Decompoe o codigo do selo. Recusa o que nao tem forma de selo."""
    bruto = str(texto or "").strip().upper()
    if not bruto:
        raise SeloError("O código do selo não pode ficar em branco.")
    if CODIGO_ANTIGO.match(bruto):
        return Codigo(inteiro=bruto, prefixo=None, cns=None, identificacao=None, antigo=True)
    m = CODIGO_SELO.match(bruto)
    if not m:
        raise SeloError(
            f"«{bruto}» não tem forma de selo do TJMA. O selo eletrônico tem 28 "
            f"caracteres: seis letras do tipo de ato, seis dígitos do CNS e o "
            f"restante da identificação — por exemplo PRENOT000000ZEZSIN46Y2QXQM16.")
    return Codigo(inteiro=bruto, prefixo=m.group("tipo"),
                  cns=m.group("cns"), identificacao=m.group("id"))


def do_nosso_cns(codigo: Any, cns: Any) -> bool:
    """Se o selo e desta serventia. Selo de outra casa no nosso livro e erro."""
    try:
        lido = ler_codigo(codigo)
    except SeloError:
        return False
    if lido.antigo or not lido.cns:
        return False
    return lido.cns == "".join(c for c in str(cns or "") if c.isdigit()).zfill(6)[-6:]


# ------------------------------------------- o texto devolvido pelo selador
#
# O selador devolve o texto PRONTO, e e este texto que sai impresso no ato:
#
#   Poder Judiciario - TJMA. Selo: PRENOT000000ZEZSIN46Y2QXQM16,
#   17/08/2026 08:50:12, Ato: 16.1, Parte(s): NOME,
#   Total R$ 43,37 Emol R$ 38,72 FERC R$ 1,16 FADEP R$ 1,55 FEMP R$ 1,55
#   FERRFIS R$ 0,39 Consulte em https://selo.tjma.jus.br
#
# Ler este texto e o que permite conferir o Livro de Selos sem digitar valor
# nenhum a mao. E foi digitando a mao, em 18/08/2026, que a certidao saiu com
# "172,86" sem rotulo e a tela marcou a linha como "sem rotulo".

_MOEDA = r"R\$\s*([\d.]+,\d{2})"


def _numero(bruto: str) -> float:
    try:
        return float(str(bruto).replace(".", "").replace(",", "."))
    except (ValueError, AttributeError):
        return 0.0


# AS MARCAS DO SELO — as duas que esta casa recebeu, medidas em 17/09/2026
# no razao inteiro (25.839 selos com texto): `Selo Isento` em 172 e `Diferido`
# em 53, e nenhuma outra. Escritas na forma em que o aparelho as manda, porque
# e essa a forma que vai impressa.
MARCAS_DO_SELO: tuple[str, ...] = ("Selo Isento", "Diferido")


def ler_texto(texto: Any) -> dict[str, Any]:
    """Separa do texto do selo tudo o que ele afirma.

    Devolve o que achou e diz o que NAO achou, em `faltando`. Nao chuta: campo
    ausente vem como None, e nao como zero — zero e uma afirmacao, e afirmar
    zero emolumento sobre ato oneroso e pior do que dizer "nao sei".
    """
    bruto = " ".join(str(texto or "").split())
    achado: dict[str, Any] = {"texto": bruto, "faltando": []}

    m = re.search(r"Selo:\s*([A-Z0-9]{20,40})", bruto, re.I)
    achado["codigo"] = m.group(1).upper() if m else None
    # HOTFIX-2026-10-09-06: o segundo e opcional. A consulta publica do TJMA
    # informa a hora como HH:MM; o texto oficial gravado dela (selos antigos
    # do acervo, 09/10/2026) nao inventa segundos, e sem isto o carimbo
    # perdia a data inteira.
    m = re.search(r"(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2}(?::\d{2})?)\b", bruto)
    achado["data"] = m.group(1) if m else None
    achado["hora"] = m.group(2) if m else None
    m = re.search(r"\bAto:\s*([\d.]+[\dA-Za-z.]*)", bruto)
    achado["ato"] = m.group(1).rstrip(".,") if m else None
    m = re.search(r"Parte\(s\):\s*(.+?)(?=,\s*(?:Total|Emol)\b|$)", bruto, re.I)
    achado["partes"] = m.group(1).strip().rstrip(",") if m else None

    # **O ENDEREÇO DE CONSULTA — pedido do oficial em 11/09/2026: «precisa
    # incluir o site do tj para consulta do selo na etiqueta do selo».**
    # É o que o próprio aparelho já escreve no fim do texto, em 25.634 de
    # 25.634 selos medidos (`selo_no_papel.py`); só não estava sendo lido.
    # Não entra em `faltando` — a etiqueta pode sair sem ele sem afirmar
    # nada de errado, ao contrário de valor ou data.
    # **DUAS FORMAS, E A ANTIGA ESTAVA SENDO PERDIDA** — medido em
    # 17/09/2026 nos 25.839 selos com texto: 25.828 escrevem «Consulte em
    # https://…» e **11 escrevem «Consulte A VALIDADE DESTE SELO em https://…»**,
    # todos de marco a maio de 2020 — 8 reconhecimentos de firma e **3
    # certidoes do Registro de Imoveis**. Com o padrao literal, nesses onze o
    # papel saia sem endereco de consulta nenhum.
    m = re.search(r"Consulte\b[^:]{0,40}?\bem\s+(\S+)", bruto, re.I)
    achado["consulta"] = m.group(1).rstrip(".,") if m else None

    # AS MARCAS QUE O APARELHO ESCREVE DEPOIS DOS VALORES. Medido no razao
    # inteiro: `Selo Isento` em 172 e `Diferido` em 53 — e mais nada. Elas vem
    # entre o ultimo valor e o «Consulte em».
    #
    # **NAO SE DEDUZEM DO VALOR**: o selo isento desta casa traz os
    # emolumentos escritos (`Total R$ 115,44 … Selo Isento`), e um carimbo que
    # imprima so os numeros afirma que se cobrou. A marca e o que desmente o
    # numero ao lado dela.
    achado["marcas"] = [
        nome for nome in MARCAS_DO_SELO
        if re.search(rf"\b{re.escape(nome)}\b", bruto, re.I)]

    m = re.search(r"total\D{0,12}" + _MOEDA, bruto, re.I)
    achado["total"] = _numero(m.group(1)) if m else None
    m = re.search(r"emol\w*\D{0,12}" + _MOEDA, bruto, re.I)
    achado["emolumentos"] = _numero(m.group(1)) if m else None

    fundos: dict[str, float] = {}
    for f in ATR.FUNDOS:
        for sigla in (f["sigla"], *ATR.SINONIMOS_DE_FUNDO.get(f["sigla"], ())):
            m = re.search(rf"\b{re.escape(sigla)}\b\D{{0,12}}" + _MOEDA, bruto, re.I)
            if m:
                fundos[f["sigla"]] = _numero(m.group(1))
                break
    achado["fundos"] = fundos

    for campo in ("codigo", "data", "ato", "total", "emolumentos"):
        if achado.get(campo) is None:
            achado["faltando"].append(campo)
    if not fundos:
        achado["faltando"].append("fundos")
    achado["rotulado"] = "total" not in achado["faltando"]
    return achado


def conferir_texto(texto: Any, cns: Any = None) -> list[str]:
    """O que esta errado no texto do selo, em portugues de balcao.

    Lista vazia quer dizer que o texto se sustenta sozinho.
    """
    lido = ler_texto(texto)
    problemas: list[str] = []

    if lido["codigo"] is None:
        problemas.append("O texto não traz o código do selo.")
    else:
        try:
            ler_codigo(lido["codigo"])
        except SeloError as erro:
            problemas.append(str(erro))
        if cns and not do_nosso_cns(lido["codigo"], cns):
            problemas.append(
                f"O selo {lido['codigo']} não é desta serventia — o CNS no código não "
                f"é {cns}. Confira se não foi colado o selo de outro ato.")

    if lido["ato"] is None:
        problemas.append("O texto não diz qual é o ato da tabela de custas.")
    if lido["total"] is None:
        problemas.append(
            "O texto não traz o Total. Sem rótulo, o Livro de Selos usa o primeiro "
            "número que encontrar para tudo.")
    if lido["emolumentos"] is None:
        problemas.append("O texto não traz os emolumentos.")

    total, emol = lido["total"], lido["emolumentos"]
    soma_fundos = sum(lido["fundos"].values())
    if total is not None and emol is not None:
        if emol > total + 0.005:
            problemas.append(
                f"Os emolumentos (R$ {emol:.2f}) são maiores que o total "
                f"(R$ {total:.2f}) — um dos dois está errado.")
        elif lido["fundos"] and abs((emol + soma_fundos) - total) > 0.05:
            problemas.append(
                f"A conta não fecha: emolumentos R$ {emol:.2f} mais os fundos "
                f"R$ {soma_fundos:.2f} dão R$ {emol + soma_fundos:.2f}, e o total "
                f"declarado é R$ {total:.2f}.")
    return problemas


# --------------------------------------------------- a tabela de custas
#
# `codigoTabelaCusta` e `versaoTabelaDeCustas` vem como TTAAAAMMDD:
# "0520260101" = tabela 05, vigencia 01/01/2026. Tabelas observadas no acervo:
# 01, 02, 03 e 05 — e batem com a atribuicao do ato.

CODIGO_TABELA = re.compile(r"^(?P<tabela>\d{2})(?P<ano>\d{4})(?P<mes>\d{2})(?P<dia>\d{2})$")


def ler_tabela_de_custas(codigo: Any) -> dict[str, Any]:
    """Decompoe o codigo da tabela de custas em tabela e vigencia."""
    bruto = str(codigo or "").strip()
    m = CODIGO_TABELA.match(bruto)
    if not m:
        raise SeloError(
            f"«{bruto}» não tem forma de código de tabela de custas. O formato é "
            f"dois dígitos da tabela e a data de vigência — por exemplo 0520260101, "
            f"que é a tabela 05 com vigência em 1º de janeiro de 2026.")
    return {
        "codigo": bruto,
        "tabela": m.group("tabela"),
        "vigencia": f"{m.group('ano')}-{m.group('mes')}-{m.group('dia')}",
    }


def codigo_da_tabela(tabela: Any, vigencia: str) -> str:
    """Monta o codigo, a partir da tabela e da vigencia em AAAA-MM-DD."""
    t = str(tabela or "").strip().zfill(2)
    if len(t) != 2 or not t.isdigit():
        raise SeloError(f"A tabela de custas é de dois dígitos, e veio «{tabela}».")
    partes = str(vigencia or "").split("-")
    if len(partes) != 3 or not all(p.isdigit() for p in partes):
        raise SeloError(
            f"A vigência vem em AAAA-MM-DD, e veio «{vigencia}».")
    ano, mes, dia = partes
    return f"{t}{ano.zfill(4)}{mes.zfill(2)}{dia.zfill(2)}"
