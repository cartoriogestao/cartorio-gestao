"""
Teor RTDPJ (RCPJ/RTD) — PDF no modelo da casa (atos futuros).

ENSINO DO OFICIAL (modelo genérico para TODOS os atos RCPJ/RTD):
  1) Cabeçalho em TODAS as folhas: «OFÍCIO ÚNICO DE CIDADE EXEMPLO / MA — CNS {cns}»
     + nome da atribuição (SEM livro/folha/série/ficha id).
  2) Atribuição pela série:
       PJ_* → «Registro Civil das Pessoas Jurídicas» (com DAS)
       TD_* → «Registro de Títulos e Documentos»
  3) Intro SEM a palavra «hoje»: «CERTIFICO que me foi apresentado para ser
     {AVERBADO|REGISTRADO} no Registro nº {numero} o documento digitalizado abaixo:»
     (não: «apresentado, hoje, para»). Em averbação a intro também leva a
     natureza do título averbado + data da assinatura (elementos para
     diferenciar averbações — ensino Gentil/oficial 11/09/2026):
     «Tipo do ato: {natureza_ato}.» / «Data da assinatura: {data_assinatura}.»
  4) Faixa reservada no RODAPÉ da ÚLTIMA folha para colar a(s) etiqueta(s)
     do selo (100×30 mm @ ~150 dpi) — após o encerramento; imagem acima,
     sem sobrepor. `com_arquivamento=True` (1ª averbação do pacote) reserva
     duas áreas: «selo averbação» + «selo arquivamento» (TJ 15.22).
  5) 1 imagem por folha; cada digitalização cabe na área útil da própria
     página (escala individual). Multi = cabeçalho em todas; encerramento +
     faixa do selo só na última (rodapé).
  6) Encerramento: «Eu, {full_name}, {funcao}, o subscrevo e assino.»
     + «{cidade}/{uf}, {data_extenso}.» — lavrante da sessão (users).

MODELO EDITÁVEL (relato #28 / modelos da casa)
  O texto mora no catálogo `modelos_da_casa` sob as chaves:
    RCPJ_TEOR_AVERBACAO, RCPJ_TEOR_REGISTRO,
    RTD_TEOR_AVERBACAO,  RTD_TEOR_REGISTRO.
  Código = piso; `mo_modelos` = ajuste; «voltar ao padrão» = apagar a linha.
  Formato CHAVES (`{numero}`). Partes marcadas no corpo:
    ===CABECALHO=== / ===INTRO=== / ===ENCERRAMENTO=== / ===DATA===
  Desde o LF06F (19/10/2026) o texto de cada parte só existe no papel: a
  intro curta do livro (`intro`), o encerramento e o cabeçalho de quando o
  ajuste perdeu a parte saem do padrão. A linha de assinatura e os rótulos
  do selo são do papel RCPJ_RTD_PDF_MOLDURA (`moldura`).

O QUE O TERMO DECLARA ALÉM DO TEOR (LD09, 21/10/2026)
  O termo do registro diz, antes da trasladação, o protocolo do título — a
  data, o número e o apresentante (LRP arts. 136 e 143; art. 120, caput e VI)
  —; o do Livro C, o extrato (art. 143); o da inscrição da pessoa jurídica, as
  indicações do art. 120; o da matrícula do periódico, as do art. 123, I; o
  do Livro F, o total de páginas registradas (art. 127-A, § 3º); e o da
  averbação, no alto da folha, o número de ordem dela (arts. 149 e 153). Cada
  uma é uma linha do padrão com o seu claro, e a linha cujo claro veio vazio
  SAI DO MOLDE (`_sem_declaracao_vazia`): o Livro B não ganha linha do Livro C,
  e o teor que vai ao livro (`intro`) continua byte a byte o de antes.

O QUE ESTE MÓDULO NÃO FAZ
  Não grava ato, não emite selo, não chama ATUALIZAR. Só monta o PDF.
"""
from __future__ import annotations

import re
import sqlite3
import string
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, Sequence

from PIL import Image, ImageDraw, ImageFont

from bd_nativo import banco
from rg_registro import CLAROS_DAS_DECLARACOES

# ------------------------------------------------------------------ nomes
ATRIBUICAO_RCPJ = "Registro Civil das Pessoas Jurídicas"
ATRIBUICAO_RTD = "Registro de Títulos e Documentos"

TIPO_AVERBACAO = "AVERBACAO"
TIPO_REGISTRO = "REGISTRO"
# O TERMO DO CANCELAMENTO (LD05, 21/10/2026). LRP art. 165 e CN-MA art. 994,
# § 1º: o oficial certifica o cancelamento e a causa dele, mencionando o
# documento que o autorizou, «datando e assinando». O ato guardava só o motivo,
# e a rota do termo recusava — o cancelamento era o único ato do livro sem
# termo datado e assinado.
TIPO_CANCELAMENTO = "CANCELAMENTO"
TIPOS_ATO = (TIPO_AVERBACAO, TIPO_REGISTRO, TIPO_CANCELAMENTO)

VERBOS = {
    TIPO_AVERBACAO: "AVERBADO",
    TIPO_REGISTRO: "REGISTRADO",
    TIPO_CANCELAMENTO: "CANCELADO",
}

# Chaves do catálogo modelos_da_casa (formato CHAVES).
CHAVES_MODELO = {
    ("RCPJ", TIPO_AVERBACAO): "RCPJ_TEOR_AVERBACAO",
    ("RCPJ", TIPO_REGISTRO): "RCPJ_TEOR_REGISTRO",
    ("RTD", TIPO_AVERBACAO): "RTD_TEOR_AVERBACAO",
    ("RTD", TIPO_REGISTRO): "RTD_TEOR_REGISTRO",
    ("RCPJ", TIPO_CANCELAMENTO): "RCPJ_TEOR_CANCELAMENTO",
    ("RTD", TIPO_CANCELAMENTO): "RTD_TEOR_CANCELAMENTO",
}

# A4 em ~150 dpi (mesma escala do rascunho aprovado em Santa Isabel).
A4_W, A4_H = 1240, 1754
HEADER_H = 220
FOOTER_H = 175
SIDE = 48
# Faixa no RODAPÉ da ÚLTIMA folha para colar a(s) etiqueta(s) do selo (100×30 mm).
# 30 mm @ 150 dpi ≈ 177 px; + margem interna ≈ 200. Só na última página.
# Com arquivamento (1ª averbação do pacote): duas áreas lado a lado.
SELO_FAIXA_H = 200
# Os rótulos das duas áreas («selo averbação» / «selo arquivamento») saíram
# daqui no LF06F (19/10/2026): são partes do papel RCPJ_RTD_PDF_MOLDURA (ver
# `moldura`). Os nomes antigos continuam respondendo pelo `__getattr__`.

MESES = (
    "", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)

EXTENSOES_IMAGEM = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp")
EXTENSOES_PDF = (".pdf",)

MARCA_CABECALHO = "===CABECALHO==="
MARCA_INTRO = "===INTRO==="
MARCA_ENCERRAMENTO = "===ENCERRAMENTO==="
MARCA_DATA = "===DATA==="

PLACEHOLDERS = (
    "{cns}", "{atribuicao}", "{unit_short}", "{numero}", "{tipo_ato}",
    "{verbo}", "{natureza_ato}", "{data_assinatura}",
    "{full_name}", "{funcao}", "{cidade}", "{uf}",
    "{data_extenso}",
    # a causa do cancelamento e o documento que o autorizou (LD05) — só o
    # termo do cancelamento o preenche; nos outros ele sai vazio
    "{motivo}",
)

# O QUE O TERMO DECLARA ALÉM DO TEOR (LD09, 21/10/2026) — ver o cabeçalho do
# módulo. O protocolo do título, no registro (LRP arts. 136 e 143; art. 120);
# o total de páginas, no Livro F (art. 127-A, § 3º); o número de ordem da
# averbação (arts. 149 e 153); e as declarações de cada livro, que a lavratura
# grava no ato (`rg_registro.DECLARACOES_POR_SERIE`).
CLAROS_DO_PROTOCOLO = ("protocolo", "data_protocolo", "apresentante")
CLARO_DAS_PAGINAS = "paginas"
CLARO_DA_AVERBACAO = "numero_averbacao"
CLAROS_OPCIONAIS = frozenset(
    (*CLAROS_DO_PROTOCOLO, CLARO_DAS_PAGINAS, CLARO_DA_AVERBACAO,
     *CLAROS_DAS_DECLARACOES))
PLACEHOLDERS = PLACEHOLDERS + tuple(
    "{" + c + "}" for c in (*CLAROS_DO_PROTOCOLO, CLARO_DAS_PAGINAS,
                            CLARO_DA_AVERBACAO, *CLAROS_DAS_DECLARACOES))

# **O TOTAL DE PÁGINAS É DO LIVRO F** — LRP art. 127-A, § 3º: «a certificação
# do registro [para conservação] será feita por termo, com indicação do número
# total de páginas registradas». A lei não o pede no B nem no C, e o termo
# deles não muda; quem quiser em todos, é uma série a mais aqui.
SERIES_COM_TOTAL_DE_PAGINAS = frozenset({"TD_F"})


class TeorRtdpjError(ValueError):
    """Impedimento de montagem do teor, com mensagem pronta para a tela."""


# Nome antigo — API compatível com quem já importa TeorAverbacaoError.
TeorAverbacaoError = TeorRtdpjError


# ------------------------------------------------------ piso (texto fábrica)
#
# O TEXTO DE FÁBRICA SAIU DAQUI NO LF06A (19/10/2026). Ele era montado por
# `_corpo_piso`, com as marcas de seção acima e o verbo/finalidade de cada um
# dos quatro papéis — aprovado nos PDFs de Santa Isabel —, e agora mora em
# `modelos_padrao/rcpj_rtd/<CHAVE>.txt`, com os MESMOS bytes (o teste-ouro
# confere), e chega pela base dos padrões. As marcas continuam aqui porque é
# este módulo que parte o texto nelas; quem mudar uma marca muda o `.txt`
# junto. Os nomes antigos (`MODELO_RCPJ_TEOR_AVERBACAO`, `PADROES_POR_CHAVE`)
# continuam respondendo — ver `__getattr__` no fim deste módulo.


def piso(chave: str) -> str:
    """O padrão da base para aquela chave — o de AVERBAÇÃO do RCPJ se a chave
    não for uma das quatro, como o `PADROES_POR_CHAVE.get(chave) or ...` fazia."""
    import modelos_da_casa as CASA
    alvo = chave if chave in CHAVES_MODELO.values() else "RCPJ_TEOR_AVERBACAO"
    return CASA.padrao_de(alvo)


def secoes_do_padrao(chave: str) -> dict[str, str]:
    """As partes (===CABECALHO===, ===INTRO===…) do padrão da base. Só lê.

    **É DAQUI QUE SAI O TEXTO QUANDO O AJUSTE DA CASA PERDEU UMA PARTE** — até
    o LF06F (19/10/2026) esse texto estava escrito uma segunda vez neste módulo
    (`intro`, `encerramento`, `linhas_cabecalho`, `linha_data`), e as duas cópias
    divergiriam no primeiro conserto do padrão.
    """
    return partir_modelo(piso(chave))


# ---------------------------------------------- as frases do desenho do PDF
#
# **O QUE O DESENHO ESCREVE NA FOLHA, E NÃO ESTÁ NO TEXTO DO TEOR**: a linha de
# assinatura, os rótulos das áreas do selo, o «Consulte em» do carimbo — e, na
# certidão em PDF (`rg_certidao_pdf`), «Página», o nome do livro e o objeto
# certificado. Até o LF06F (19/10/2026) eram literais no desenho; agora são as
# partes do papel RCPJ_RTD_PDF_MOLDURA, um só para os dois PDFs, editável na
# tela de Modelos. A REGRA que escolhe a parte (a 2ª caixa só com o selo de
# arquivamento 15.22, «Averbação» ou «Averbações») continua no código.
CHAVE_MOLDURA = "RCPJ_RTD_PDF_MOLDURA"

# Cada parte e os claros que ela recebe. A linha de assinatura recebe os do
# teor (`contexto_do_teor`), porque é desenhada junto com ele.
CLAROS_DA_MOLDURA: dict[str, tuple[str, ...]] = {
    "ASSINATURA": tuple(p.strip("{}") for p in PLACEHOLDERS),
    "SELO_AVERBACAO": (),
    "SELO_ARQUIVAMENTO": (),
    "SELO_CONSULTE": ("endereco",),
    "SELO_CERTIDAO": (),
    "SELO_VAZIO": (),
    "QR_VAZIO": (),
    "PAGINA": (),
    "LIVRO_RCPJ": (),
    "LIVRO_RTD": (),
    "OBJETO": ("natureza",),
    "OBJETO_SEM_NATUREZA": (),
    "IDENTIFICACAO": ("numero",),
    "OBJETO_AVERBACOES": ("averbacoes",),
    "AVERBACAO_COM_NATUREZA": ("ordem", "natureza"),
    "AVERBACAO_SEM_NATUREZA": ("ordem",),
    "IDENTIFICACAO_AVERBACAO": ("ordens",),
    "IDENTIFICACAO_AVERBACOES": ("ordens",),
}


def partir_secoes(corpo: str, nomes) -> dict[str, str]:
    """`===NOME===` → texto, só dos nomes pedidos. Parte que falta fica de fora."""
    texto = corpo or ""
    marca = re.compile(r"===(" + "|".join(re.escape(n) for n in nomes) + r")===\s*",
                       re.IGNORECASE)
    pedacos = marca.split(texto)
    partes: dict[str, str] = {}
    for nome, valor in zip(pedacos[1::2], pedacos[2::2]):
        partes[nome.upper()] = re.split(r"\n===", valor, maxsplit=1)[0].strip("\n")
    return partes


def moldura(con=None, *, erro=None) -> dict[str, str]:
    """As frases do desenho dos PDFs do RCPJ/RTD, parte por parte. Só lê.

    Com `con`, vale o ajuste da casa; **a parte que o ajuste apagou volta ao
    padrão**, como o teor faz com a intro e o encerramento. O ajuste que usa um
    claro que aquela parte não recebe é recusado AQUI, com `erro` (a exceção do
    módulo que pede), e não no meio do desenho.
    """
    import modelos_da_casa as CASA
    padrao = partir_secoes(CASA.padrao_de(CHAVE_MOLDURA), CLAROS_DA_MOLDURA)
    ajuste: dict[str, str] = {}
    if con is not None:
        try:
            ajuste = partir_secoes(CASA.corpo_de(con, CHAVE_MOLDURA), CLAROS_DA_MOLDURA)
        except Exception:  # noqa: BLE001 — piso seguro, como `corpo_do_modelo`
            ajuste = {}
    partes = {nome: ajuste.get(nome) or padrao.get(nome, "")
              for nome in CLAROS_DA_MOLDURA}
    for nome in partes:
        preencher_moldura(partes, nome, dict.fromkeys(CLAROS_DA_MOLDURA[nome], ""),
                          erro=erro)
    return partes


def conferir_moldura(corpo: str) -> str:
    """A moldura que a tela vai gravar serve? Devolve o erro, ou ``""``.

    A mesma conferência de `moldura`, na tela de Modelos: o boneco geral não
    conhece os claros de cada parte, e aprovaria um `{inventado}` que só
    estouraria ao desenhar o PDF."""
    partes = partir_secoes(corpo, CLAROS_DA_MOLDURA)
    try:
        for nome in partes:
            preencher_moldura(partes, nome,
                              dict.fromkeys(CLAROS_DA_MOLDURA[nome], ""))
    except TeorRtdpjError as erro:
        return str(erro)
    return ""


def conferir_teor(corpo: str) -> str:
    """O teor que a tela vai gravar monta? Devolve o erro, ou ``""``. Só calcula.

    A mesma montagem de `textos_prontos` (LD05, 21/10/2026): cada parte com os
    claros que o termo preenche, e o cabeçalho sem livro nem folha. Sem isto a
    tela aprovaria um `{inventado}` que só estouraria ao imprimir o termo.
    """
    secoes = partir_modelo(corpo)
    if not secoes:
        return ("O termo precisa das partes ===CABECALHO=== e ===INTRO=== — sem "
                "elas o papel volta inteiro ao padrão.")
    ctx = {p.strip("{}"): "exemplo" for p in PLACEHOLDERS}
    try:
        for texto in secoes.values():
            aplicar_chaves(texto, ctx)
    except TeorRtdpjError as erro:
        return str(erro)
    if cabecalho_tem_livro_ou_folha(secoes.get("CABECALHO", "").splitlines()):
        return "Cabeçalho do teor não pode citar livro/folha/série/ficha."
    return ""


def preencher_moldura(partes: dict[str, str], nome: str,
                      claros: dict | None = None, *, erro=None) -> str:
    """A parte `nome` da moldura com os claros dela. Só calcula."""
    try:
        return (partes.get(nome) or "").format(**(claros or {}))
    except (KeyError, ValueError, IndexError) as e:
        conhecidos = ", ".join("{" + c + "}" for c in CLAROS_DA_MOLDURA.get(nome, ()))
        raise (erro or TeorRtdpjError)(
            f"A parte ==={nome}=== do modelo {CHAVE_MOLDURA} usa um claro que o "
            f"sistema não preenche ali ({e}). Claros desta parte: "
            f"{conhecidos or 'nenhum'}.") from e


# ----------------------------------------------------------- normalização

def normalizar_tipo_ato(tipo_ato: str | None) -> str:
    t = (tipo_ato or TIPO_AVERBACAO).strip().upper()
    aliases = {
        "AVERBACAO": TIPO_AVERBACAO, "AVERBAÇÃO": TIPO_AVERBACAO,
        "AV": TIPO_AVERBACAO, "AVERBADO": TIPO_AVERBACAO,
        "REGISTRO": TIPO_REGISTRO, "REGISTRADO": TIPO_REGISTRO,
        "R": TIPO_REGISTRO, "LAVRATURA": TIPO_REGISTRO,
        "CANCELAMENTO": TIPO_CANCELAMENTO, "CANCELADO": TIPO_CANCELAMENTO,
    }
    if t not in aliases:
        raise TeorRtdpjError(
            f"Tipo de ato «{tipo_ato}» não é AVERBACAO, REGISTRO nem "
            f"CANCELAMENTO.")
    return aliases[t]


def codigo_atribuicao(*, serie: str | None = None,
                      atribuicao: str | int | None = None) -> str:
    """Devolve 'RCPJ' ou 'RTD' a partir da série ou do código/nome."""
    if serie:
        s = str(serie).strip().upper()
        if s.startswith("PJ"):
            return "RCPJ"
        if s.startswith("TD"):
            return "RTD"
    if atribuicao is not None:
        raw = str(atribuicao).strip().upper()
        if raw in ("3", "RCPJ", "PJ"):
            return "RCPJ"
        if raw in ("4", "RTD", "TD"):
            return "RTD"
        if "JURÍDIC" in raw or "JURIDIC" in raw or "PESSOAS JUR" in raw:
            return "RCPJ"
        if "TÍTULO" in raw or "TITULO" in raw or "DOCUMENTO" in raw:
            return "RTD"
    # Default histórico: averbação Santa Isabel era RCPJ.
    return "RCPJ"


def nome_da_atribuicao(codigo: str) -> str:
    return ATRIBUICAO_RTD if codigo == "RTD" else ATRIBUICAO_RCPJ


def chave_do_modelo(*, serie: str | None = None,
                    atribuicao: str | int | None = None,
                    tipo_ato: str | None = None) -> str:
    atr = codigo_atribuicao(serie=serie, atribuicao=atribuicao)
    tipo = normalizar_tipo_ato(tipo_ato)
    return CHAVES_MODELO[(atr, tipo)]


# ------------------------------------------------------------------ textos

def intro(numero_registro, *, tipo_ato: str | None = None,
          natureza_ato: str | None = None,
          data_assinatura: str | None = None) -> str:
    """Frase CERTIFICO… apresentado para ser {AVERBADO|REGISTRADO}…

    SEM a palavra «hoje» — pedido do oficial em 11/09/2026: não
    «apresentado, hoje, para»; sim «apresentado para ser …».

    Em averbação, `natureza_ato` + `data_assinatura` diferenciam o título
    averbado (ensino Gentil/oficial 11/09/2026). Se ambos vazios, mantém a
    intro de uma linha (compatível com atos/registros sem esses campos).

    **O TEXTO É O DA PARTE ===INTRO=== DO PADRÃO** desde o LF06F (19/10/2026) —
    até ali esta função o escrevia de novo numa f-string, uma segunda cópia
    da intro do papel que divergiria no primeiro conserto do padrão.

    **O PADRÃO, E NÃO O AJUSTE DA CASA, DE PROPÓSITO.** Esta frase é o teor
    que `atribuicoes_web.rcpj_rtd_lancar` grava no livro (`rg_atos.teor`), e
    o livro nunca seguiu o modelo que a casa edita — só o PDF segue. Fazer o
    lançamento seguir o ajuste muda o que se lavra, e é regra da casa, não da
    migração do texto (revisão do LF06F): fica como pergunta ao oficial.

    A linha de natureza ou de data sem valor sai do MOLDE antes de preencher,
    e não do texto depois: assim o teor é byte a byte o da f-string de antes,
    qualquer que seja o valor digitado.
    """
    n = str(numero_registro).strip()
    if not n:
        raise TeorRtdpjError(
            "O teor precisa do número do registro.")
    tipo = normalizar_tipo_ato(tipo_ato)
    nat = (natureza_ato or "").strip()
    data = (data_assinatura or "").strip()
    linhas = secoes_do_padrao(chave_do_modelo(tipo_ato=tipo)).get(
        "INTRO", "").split("\n")
    if not nat:
        linhas = [ln for ln in linhas if "{natureza_ato}" not in ln]
    if not data:
        linhas = [ln for ln in linhas if "{data_assinatura}" not in ln]
    # Os claros do teor que a intro curta não tem (quem lavra, a data, a
    # serventia) saem vazios: ela vai ao livro, e não ao PDF. As linhas das
    # declarações do LD09 (protocolo, extrato, art. 120…) saem inteiras — o
    # livro grava o que gravava antes delas.
    ctx = {p.strip("{}"): "" for p in PLACEHOLDERS}
    ctx.update(numero=n, tipo_ato=tipo, verbo=VERBOS[tipo],
               natureza_ato=nat, data_assinatura=data,
               atribuicao=nome_da_atribuicao(codigo_atribuicao()))
    return aplicar_chaves(_sem_declaracao_vazia("\n".join(linhas), ctx), ctx)


def _sem_declaracao_vazia(molde: str, ctx: dict) -> str:
    """Tira do MOLDE a linha de declaração cujo claro veio vazio. Só calcula.

    **A LINHA DE DECLARAÇÃO É A QUE SÓ TEM CLAROS DO LD09** (`CLAROS_OPCIONAIS`
    — o protocolo, as páginas, o número da averbação, as declarações de cada
    livro): «Valor: {valor}.», «Apresentante: {apresentante}.». Faltando um
    deles, ela sai inteira, e não pela metade — «Protocolizado em , sob o nº
    .» seria rótulo sem valor no papel assinado. A linha que tem também um
    claro de sempre (`{numero}`, `{natureza_ato}`…) ou nenhum claro fica como
    está: assim o ajuste da casa que escreveu «CERTIFICO, apresentado por
    {apresentante}, que …» não perde a frase do CERTIFICO no ato sem título.

    Linha que não se lê (chave torta) fica, para `aplicar_chaves` dizer o
    erro com o nome do claro.
    """
    fica = []
    for linha in str(molde or "").split("\n"):
        try:
            claros = {nome for _, nome, _, _ in string.Formatter().parse(linha)
                      if nome}
        except ValueError:
            fica.append(linha)
            continue
        if (claros and claros <= CLAROS_OPCIONAIS
                and any(not str(ctx.get(c) or "").strip() for c in claros)):
            continue
        fica.append(linha)
    return "\n".join(fica)


def paginas_por_extenso(quantas: int | None) -> str:
    """«1 página», «3 páginas» — o claro `{paginas}`; sem contagem, ``""``."""
    if not quantas:
        return ""
    n = int(quantas)
    return f"{n} página" if n == 1 else f"{n} páginas"


def _sem_linha_sem_valor(intro_txt: str) -> str:
    """Tira «Tipo do ato: .» e «Data da assinatura: .» quando o claro veio vazio.

    Compat: o padrão traz as duas linhas com os claros; sem valor elas virariam
    «Tipo do ato: .». Só essas — não apaga linha nenhuma do ajuste da casa.
    """
    limpas = []
    for ln in intro_txt.splitlines():
        s = ln.strip()
        if s in ("Tipo do ato: .", "Tipo do ato:",
                 "Data da assinatura: .", "Data da assinatura:"):
            continue
        limpas.append(ln)
    return "\n".join(limpas).rstrip()


def parse_campos_do_teor(teor: str | None) -> tuple[str, str]:
    """Extrai natureza_ato e data_assinatura das linhas do teor.

    Procura linhas no formato oficial:
      Tipo do ato: {natureza}.
      Data da assinatura: {data}.
    Devolve (natureza_ato, data_assinatura); string vazia se ausente.
    """
    nat = ""
    data = ""
    for linha in (teor or "").splitlines():
        m = re.match(r"(?i)^\s*Tipo do ato:\s*(.+?)\.?\s*$", linha)
        if m:
            nat = m.group(1).strip().rstrip(".")
            continue
        m = re.match(r"(?i)^\s*Data da assinatura:\s*(.+?)\.?\s*$", linha)
        if m:
            data = m.group(1).strip().rstrip(".")
    return nat, data


def tem_selo_arquivamento(con: sqlite3.Connection, ato_id: int) -> bool:
    """True se o ato tem selo TJ 15.22 (arquivamento) em sd_selos."""
    try:
        row = banco(con).um(
            """SELECT 1 AS tem FROM sd_selos
                WHERE tabela='rg_atos' AND ato_id=%s
                  AND (referencia ILIKE '%%:15.22:%%'
                       OR texto ILIKE '%%Ato: 15.22%%'
                       OR numero ILIKE 'ARQUIV%%')
                LIMIT 1""",
            (ato_id,))
    except sqlite3.Error:
        return False
    return bool(row)


def com_arquivamento_para_ato(con: sqlite3.Connection, registro_id: int,
                              ato_id: int) -> bool:
    """Reserva a faixa do selo de arquivamento SE este ato tem o selo 15.22.

    **NÃO HÁ REGRA QUE LIGUE ARQUIVAMENTO À "1ª AVERBAÇÃO DO PACOTE"** —
    correção do oficial em 11/09/2026: «não tem nada que ligue 1 averbação a
    arquivamento, foi algo que o projeto entendeu errado». A versão anterior
    também considerava `com_arquivamento=True` para a averbação de menor id do
    registro, mesmo sem selo 15.22 nenhum — um palpite sem base na tabela de
    emolumentos nem no contrato do selador. Cada averbação leva a faixa de
    arquivamento SE E SOMENTE SE ela mesma tiver o selo 15.22 — o que agora é
    decidido pelo operador, item por item, ao lançar (ver
    `atribuicoes_web._itens_para_selar`), e não deduzido da ordem dos atos.
    `registro_id` fica no parâmetro só para não quebrar quem já chama esta
    função com ele.
    """
    return tem_selo_arquivamento(con, ato_id)


def linhas_cabecalho(*, cns: str = "",
                     unit_short: str = "",
                     atribuicao: str | None = None,
                     serie: str | None = None,
                     ) -> list[str]:
    """Cabeçalho curto — SEM livro/folha/série/ficha.

    O texto é a parte ===CABECALHO=== do padrão do papel (LF06F, 19/10/2026),
    linha por linha como está — é o que vale quando o ajuste da casa deixou o
    cabeçalho vazio.
    """
    cns = (cns or "").strip() or ""
    codigo = codigo_atribuicao(serie=serie, atribuicao=atribuicao)
    chave = chave_do_modelo(serie=serie, atribuicao=atribuicao)
    ctx = {p.strip("{}"): "" for p in PLACEHOLDERS}
    ctx.update(cns=cns, unit_short=unit_short,
               atribuicao=nome_da_atribuicao(codigo))
    # sem ato, não há número de averbação a dizer (LD09): a linha sai
    return aplicar_chaves(_sem_declaracao_vazia(
        secoes_do_padrao(chave).get("CABECALHO", ""), ctx), ctx).split("\n")


def cabecalho_tem_livro_ou_folha(linhas: Sequence[str]) -> bool:
    junto = " ".join(linhas).lower()
    for palavra in ("livro", "folha", "fl.", "fls", "série", "serie",
                    "ficha id"):
        if palavra in junto:
            return True
    return False


def data_por_extenso(dia: date | None = None) -> str:
    d = dia or date.today()
    return f"{d.day} de {MESES[d.month]} de {d.year}"


def encerramento(*, lavrante_nome: str, lavrante_funcao: str,
                 tipo_ato: str | None = None,
                 serie: str | None = None,
                 atribuicao: str | int | None = None) -> str:
    """O encerramento do teor — a parte ===ENCERRAMENTO=== do padrão do papel
    daquele tipo (LF06F, 19/10/2026: «averbação» ou «registro» está no texto
    de cada um dos quatro papéis, e não mais numa f-string aqui)."""
    nome = (lavrante_nome or "").strip()
    funcao = (lavrante_funcao or "").strip()
    if not nome:
        raise TeorRtdpjError(
            "O teor precisa do nome de quem lavra (sessão).")
    if not funcao:
        raise TeorRtdpjError(
            "O teor precisa da função de quem lavra (sessão).")
    tipo = normalizar_tipo_ato(tipo_ato)
    chave = chave_do_modelo(serie=serie, atribuicao=atribuicao, tipo_ato=tipo)
    ctx = {p.strip("{}"): "" for p in PLACEHOLDERS}
    ctx.update(full_name=nome, funcao=funcao, tipo_ato=tipo, verbo=VERBOS[tipo])
    return aplicar_chaves(_sem_declaracao_vazia(
        secoes_do_padrao(chave).get("ENCERRAMENTO", ""), ctx), ctx)


def linha_data(*, cidade: str = "", uf: str = "MA",
               dia: date | None = None) -> str:
    """«Cidade/UF, 8 de setembro de 2026.» — a parte ===DATA=== do padrão."""
    ctx = {p.strip("{}"): "" for p in PLACEHOLDERS}
    ctx.update(cidade=cidade, uf=uf, data_extenso=data_por_extenso(dia))
    # sem série nem tipo, o papel de sempre deste módulo: a averbação do RCPJ
    chave = CHAVES_MODELO[("RCPJ", TIPO_AVERBACAO)]
    return aplicar_chaves(_sem_declaracao_vazia(
        secoes_do_padrao(chave).get("DATA", ""), ctx), ctx)


def flags_das_paginas(n: int) -> list[tuple[bool, bool]]:
    """Para cada página: (com_cabecalho, com_encerramento)."""
    if n < 1:
        raise TeorRtdpjError(
            "O teor precisa de ao menos uma imagem digitalizada.")
    return [(True, i == n - 1) for i in range(n)]


# ---------------------------------------------- ler / partir o modelo

def contexto_do_teor(*, numero_registro, lavrante_nome: str,
                     lavrante_funcao: str, cns: str = "",
                     unit_short: str = "",
                     cidade: str = "", uf: str = "MA",
                     dia: date | None = None,
                     serie: str | None = None,
                     atribuicao: str | int | None = None,
                     tipo_ato: str | None = None,
                     natureza_ato: str | None = None,
                     data_assinatura: str | None = None,
                     motivo: str | None = None,
                     protocolo: str | None = None,
                     data_protocolo: str | None = None,
                     apresentante: str | None = None,
                     numero_averbacao: str | int | None = None,
                     paginas: int | None = None,
                     declaracoes: dict | None = None) -> dict[str, str]:
    """Os claros do termo, preenchidos. Só calcula.

    Os do LD09 (o protocolo, as páginas, o número da averbação e as
    declarações do livro) vêm vazios quando o ato não os tem — e a linha deles
    sai do termo (`_sem_declaracao_vazia`). Declaração com nome que o termo
    não conhece não entra: quem confere o nome é a lavratura
    (`rg_registro.declaracoes_do_livro`)."""
    tipo = normalizar_tipo_ato(tipo_ato)
    atr = codigo_atribuicao(serie=serie, atribuicao=atribuicao)
    declarado = {c: " ".join(str((declaracoes or {}).get(c) or "").split())
                 for c in CLAROS_DAS_DECLARACOES}
    return {
        **declarado,
        "protocolo": str(protocolo if protocolo is not None else "").strip(),
        "data_protocolo": (data_protocolo or "").strip(),
        "apresentante": (apresentante or "").strip(),
        "numero_averbacao": str(numero_averbacao
                                if numero_averbacao is not None else "").strip(),
        "paginas": paginas_por_extenso(paginas),
        "cns": (cns or "").strip() or "",
        "unit_short": unit_short or "",
        "atribuicao": nome_da_atribuicao(atr),
        "numero": str(numero_registro).strip(),
        "tipo_ato": tipo,
        "verbo": VERBOS[tipo],
        "natureza_ato": (natureza_ato or "").strip(),
        "data_assinatura": (data_assinatura or "").strip(),
        "full_name": (lavrante_nome or "").strip(),
        "funcao": (lavrante_funcao or "").strip(),
        "cidade": cidade or "",
        "uf": uf or "MA",
        "data_extenso": data_por_extenso(dia),
        "motivo": (motivo or "").strip(),
    }


def aplicar_chaves(texto: str, ctx: dict[str, str]) -> str:
    """str.format_map com claros faltantes → mensagem clara."""
    class _Ctx(dict):
        def __missing__(self, key: str) -> str:
            raise TeorRtdpjError(
                f"O modelo do teor usa o claro {{{key}}}, que o sistema "
                f"não preenche. Claros conhecidos: "
                + ", ".join(PLACEHOLDERS) + ".")
    try:
        return (texto or "").format_map(_Ctx(ctx))
    except ValueError as erro:
        raise TeorRtdpjError(
            f"Modelo do teor com chave malformada: {erro}") from erro


def partir_modelo(corpo: str) -> dict[str, str]:
    """Extrai seções marcadas; se faltarem marcas, devolve vazio (cai no piso)."""
    texto = corpo or ""
    if MARCA_CABECALHO not in texto or MARCA_INTRO not in texto:
        return {}
    partes: dict[str, str] = {}
    padrao = re.compile(
        r"===(CABECALHO|INTRO|ENCERRAMENTO|DATA)===\s*", re.IGNORECASE)
    pedacos = padrao.split(texto)
    # pedacos: [preamble, nome1, corpo1, nome2, corpo2, ...]
    i = 1
    while i + 1 < len(pedacos):
        nome = pedacos[i].upper()
        valor = pedacos[i + 1]
        # Corta na próxima marca residual se houver
        valor = re.split(r"\n===", valor, maxsplit=1)[0]
        partes[nome] = valor.strip("\n")
        i += 2
    return partes


def corpo_do_modelo(chave: str,
                    con: sqlite3.Connection | None = None) -> str:
    """Lê o ajuste em mo_modelos (via modelos_da_casa) ou o piso do código."""
    if con is not None:
        try:
            import modelos_da_casa as CASA
            return CASA.corpo_de(con, chave)
        except Exception:  # noqa: BLE001 — piso seguro
            pass
    return piso(chave)


def textos_prontos(*, numero_registro, lavrante_nome: str,
                   lavrante_funcao: str, cns: str = "",
                   unit_short: str = "",
                   cidade: str = "", uf: str = "MA",
                   dia: date | None = None,
                   serie: str | None = None,
                   atribuicao: str | int | None = None,
                   tipo_ato: str | None = None,
                   natureza_ato: str | None = None,
                   data_assinatura: str | None = None,
                   con: sqlite3.Connection | None = None,
                   motivo: str | None = None,
                   protocolo: str | None = None,
                   data_protocolo: str | None = None,
                   apresentante: str | None = None,
                   numero_averbacao: str | int | None = None,
                   paginas: int | None = None,
                   declaracoes: dict | None = None,
                   ) -> dict[str, Any]:
    """Monta cabeçalho/intro/encerramento/data a partir do modelo (DB ou piso).

    Os claros do LD09 (`protocolo`, `data_protocolo`, `apresentante`,
    `numero_averbacao`, `paginas` e as `declaracoes` do livro) são o que o
    termo declara além do teor; a rota os lê do ato e do título
    (`rg_registro.dados_do_termo`). A linha de cada um sai do molde quando ele
    vem vazio — em toda parte, e não só na intro: o ajuste da casa pode
    tê-la posto no encerramento."""
    tipo = normalizar_tipo_ato(tipo_ato)
    chave = chave_do_modelo(serie=serie, atribuicao=atribuicao, tipo_ato=tipo)
    ctx = contexto_do_teor(
        numero_registro=numero_registro, lavrante_nome=lavrante_nome,
        lavrante_funcao=lavrante_funcao, cns=cns, unit_short=unit_short,
        cidade=cidade, uf=uf, dia=dia, serie=serie, atribuicao=atribuicao,
        tipo_ato=tipo, natureza_ato=natureza_ato,
        data_assinatura=data_assinatura, motivo=motivo, protocolo=protocolo,
        data_protocolo=data_protocolo, apresentante=apresentante,
        numero_averbacao=numero_averbacao, paginas=paginas,
        declaracoes=declaracoes)
    if not ctx["numero"]:
        raise TeorRtdpjError("O teor precisa do número do registro.")
    if tipo == TIPO_CANCELAMENTO and not ctx["motivo"]:
        # O termo do cancelamento sem a causa não certifica nada (LRP 165).
        raise TeorRtdpjError(
            "O termo do cancelamento precisa da causa e do documento que o "
            "autorizou (o motivo gravado no ato).")
    if not ctx["full_name"]:
        raise TeorRtdpjError(
            "O teor precisa do nome de quem lavra (sessão).")
    if not ctx["funcao"]:
        raise TeorRtdpjError(
            "O teor precisa da função de quem lavra (sessão).")

    bruto = corpo_do_modelo(chave, con=con)
    padrao = secoes_do_padrao(chave)
    # Piso estruturado, se o ajuste no banco removeu as marcas.
    secoes = partir_modelo(bruto) or padrao

    def montar(molde: str) -> str:
        return aplicar_chaves(_sem_declaracao_vazia(molde, ctx), ctx)

    def linhas_de(molde: str) -> list[str]:
        return [ln.strip() for ln in montar(molde).splitlines() if ln.strip()]

    linhas = linhas_de(secoes.get("CABECALHO", ""))
    if not linhas:
        # o cabeçalho do padrão DESTE papel, com os claros do ato — o número
        # da averbação (LD09) mora nele —, e só sem ele o curto de sempre
        linhas = linhas_de(padrao.get("CABECALHO", "")) or linhas_cabecalho(
            cns=ctx["cns"], unit_short=ctx["unit_short"],
            atribuicao=atribuicao, serie=serie)
    if cabecalho_tem_livro_ou_folha(linhas):
        raise TeorRtdpjError(
            "Cabeçalho do teor não pode citar livro/folha/série/ficha.")

    # A PARTE QUE O AJUSTE DEIXOU VAZIA VOLTA AO PADRÃO DO PAPEL — e não a uma
    # segunda cópia do texto escrita aqui, como era até o LF06F (19/10/2026).
    intro_bruto = secoes.get("INTRO") or ""
    if not intro_bruto.strip():
        intro_bruto = padrao.get("INTRO", "")
    intro_txt = _sem_linha_sem_valor(montar(intro_bruto))
    enc_txt = montar(secoes.get("ENCERRAMENTO") or padrao.get("ENCERRAMENTO", ""))
    data_txt = montar(secoes.get("DATA") or padrao.get("DATA", ""))
    # AS DECLARAÇÕES SAEM NA PRIMEIRA FOLHA, E NÃO EM TODAS (LD09): a intro se
    # repete no alto de cada folha, com o cabeçalho, e o extrato ou as vinte
    # linhas do art. 120 repetidas em cada página do estatuto encolheriam a
    # imagem de todas. Da segunda em diante, a intro de antes delas.
    sem_declaracao = {**ctx, **dict.fromkeys(CLAROS_OPCIONAIS - {CLARO_DA_AVERBACAO}, "")}
    intro_das_seguintes = _sem_linha_sem_valor(aplicar_chaves(
        _sem_declaracao_vazia(intro_bruto, sem_declaracao), sem_declaracao))

    return {
        "chave": chave,
        "linhas_cabecalho": linhas,
        "intro": intro_txt,
        "encerramento": enc_txt,
        "data": data_txt,
        "ctx": ctx,
        # as frases do desenho (assinatura, rótulos do selo) — ver `moldura`
        "moldura": moldura(con),
        # o que muda da segunda folha em diante (LD09)
        "folhas_seguintes": {"intro": intro_das_seguintes},
    }


# ------------------------------------------------------------------- fontes


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidatos = []
    if bold:
        candidatos += [
            r"C:\Windows\Fonts\arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
    else:
        candidatos += [
            r"C:\Windows\Fonts\arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    for p in candidatos:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: float) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


# ----------------------------------------------------------- desenho página


def _caixa_tracejada(d: ImageDraw.ImageDraw, x0: int, y0: int,
                     x1: int, y1: int) -> None:
    """Retângulo tracejado leve (guia para colar etiqueta)."""
    step = 10
    for x in range(x0, x1, step):
        d.line([(x, y0), (min(x + step // 2, x1), y0)],
               fill=(180, 180, 180), width=1)
        d.line([(x, y1), (min(x + step // 2, x1), y1)],
               fill=(180, 180, 180), width=1)
    for y in range(y0, y1, step):
        d.line([(x0, y), (x0, min(y + step // 2, y1))],
               fill=(180, 180, 180), width=1)
        d.line([(x1, y), (x1, min(y + step // 2, y1))],
               fill=(180, 180, 180), width=1)


def _carimbo_do_selo(d: ImageDraw.ImageDraw, im: Image.Image, *,
                     x0: int, y0: int, x1: int, y1: int, rotulo: str,
                     selo: dict[str, Any],
                     rotulos: dict[str, str] | None = None) -> None:
    """Desenha o carimbo de VERDADE — número, QR e valores. Só desenha.

    O QUE O SELO DECLARA VAI IMPRESSO, NO MODELO DO RI: lá o selo entra no
    corpo do próprio documento no momento da lavratura, e não numa etiqueta à
    parte que alguém precisa lembrar de colar depois. Aqui é a mesma decisão —
    o número, o QR e a linha de valores (a mesma régua de `selo_no_papel`, a
    da certidão do RCPN e da etiqueta de firma) entram DIRETO na folha que vai
    para o livro, assim que o ato tem selo.
    """
    numero = str(selo.get("numero") or "").strip()
    rotulo_font = _font(11)
    tw = d.textlength(rotulo, font=rotulo_font)
    d.text((x0 + (x1 - x0 - tw) / 2, y0 + 2),
           rotulo, fill=(120, 120, 120), font=rotulo_font)
    y_corpo = y0 + 20

    # **O QR NÃO PRECISA DE QUASE TODA A FAIXA** — relato do oficial em
    # 11/09/2026: «o modelo do selo pode diminuir bastante o tamanho do QR
    # code e ocupar menos espaço». 140 px (~23,7 mm a 150 dpi) tomava perto
    # de 80% da altura da faixa (`SELO_FAIXA_H` = 200 px), espremendo o
    # número e a linha de valores numa tira estreita ao lado. 90 px
    # (~15,2 mm) ainda lê tranquilo num leitor de celular a poucos
    # centímetros, e sobra altura para o texto.
    qr_lado = min(y1 - y_corpo - 4, 90)
    qr_bytes = b""
    try:
        import notas_selo as NSELO
        qr_texto = str(selo.get("qr_texto") or numero).strip()
        if qr_texto:
            qr_bytes = NSELO.png(qr_texto, tamanho_mm=qr_lado * 25.4 / 150)
    except Exception:                                        # noqa: BLE001
        qr_bytes = b""

    texto_x0 = x0 + 6
    if qr_bytes:
        try:
            from io import BytesIO as _BytesIO
            qr_img = Image.open(_BytesIO(qr_bytes)).convert("RGB")
            qr_img = qr_img.resize((qr_lado, qr_lado), Image.Resampling.NEAREST)
            im.paste(qr_img, (x0 + 6, y_corpo))
            texto_x0 = x0 + qr_lado + 16
        except Exception:                                    # noqa: BLE001
            pass

    texto_w = max(40, x1 - texto_x0 - 6)
    fonte_selo = _font(13, bold=True)
    for linha in _wrap(d, numero, fonte_selo, texto_w):
        d.text((texto_x0, y_corpo), linha, fill="black", font=fonte_selo)
        y_corpo += 17

    try:
        import selo_no_papel as SNPAPEL
        valores = SNPAPEL.linha_de_valores(selo.get("texto"))
        endereco_consulta = SNPAPEL.consulta(selo.get("texto"))
    except Exception:                                         # noqa: BLE001
        valores = ""
        endereco_consulta = ""
    if valores:
        y_corpo += 4
        fonte_valores = _font(10)
        for linha in _wrap(d, valores, fonte_valores, texto_w):
            if y_corpo > y1 - 12:
                break
            d.text((texto_x0, y_corpo), linha, fill=(70, 70, 70),
                   font=fonte_valores)
            y_corpo += 13

    # **O SITE DO TJ PARA CONSULTAR O SELO — pedido do oficial em
    # 11/09/2026: «precisa incluir o site do tj para consulta do selo na
    # etiqueta do selo».** É o próprio aparelho que o escreve no fim do
    # texto (`Consulte em https://selo.tjma.jus.br`), em 25.634 de 25.634
    # selos medidos — só faltava o carimbo imprimir.
    #
    # A frase («Consulte em …») é a parte ===SELO_CONSULTE=== da moldura desde
    # o LF06F; `rotulos` é a moldura já lida (ajuste da casa ou padrão).
    if endereco_consulta and y_corpo <= y1 - 12:
        y_corpo += 3
        fonte_consulta = _font(9)
        d.text((texto_x0, y_corpo),
               preencher_moldura(rotulos or moldura(), "SELO_CONSULTE",
                                 {"endereco": endereco_consulta}),
               fill=(100, 100, 100), font=fonte_consulta)


def _linhas_reservadas_extra(selos_extra: Sequence[dict] | None) -> int:
    """Quantas linhas A MAIS a faixa do selo precisa, para os selos extras.

    Duas caixas por linha, a mesma largura das dos dois nomeados.
    """
    n = len(selos_extra or [])
    return (n + 1) // 2


def _desenhar_faixa_do_selo(im: Image.Image, *, y0: int | None = None,
                           com_arquivamento: bool = False,
                           selo_averbacao: dict[str, Any] | None = None,
                           selo_arquivamento: dict[str, Any] | None = None,
                           selos_extra: Sequence[dict] | None = None,
                           rotulos: dict[str, str] | None = None,
                           ) -> int:
    """Reserva no RODAPÉ da ÚLTIMA folha a área da(s) etiqueta(s). Só desenha.

    **COM SELO, O CARIMBO JÁ SAI IMPRESSO** — número, QR e valores, no modelo
    do RI (`_carimbo_do_selo`). **SEM SELO** — a prévia, que nunca sela, ou um
    ato que ainda não tem número — a área continua sendo a moldura tracejada
    de sempre, «cole aqui», porque não se inventa selo que o aparelho não deu.

    Uma área («selo averbação») ou, com `com_arquivamento`, duas lado a lado
    («selo averbação» / «selo arquivamento»). Devolve o Y abaixo da faixa.
    `y0` default = rodapé (A4_H - SELO_FAIXA_H + 4).

    **`selos_extra`, achado do oficial em 11/09/2026** («preciso que todos os
    selos estejam no ato da averbação»): um ato pode ter mais de um selo do
    MESMO tipo (dois itens distintos de averbação, por exemplo — `15.1` e
    `15.9.1` no mesmo ato) — o que `selo_averbacao`/`selo_arquivamento`
    sozinhos não guardam, porque `rg_atos` só tem duas colunas. Cada item de
    `selos_extra` é `{"rotulo": ..., "numero", "texto", "qr_texto"}` — o
    resto do selado (`AS.selos_do_ato`), impresso em linhas extras abaixo,
    duas caixas por linha, para NENHUM selo comprado ficar de fora do papel.
    """
    # **O BLOCO INTEIRO PRECISA CABER NO QUE FOI RESERVADO** — correção de
    # 11/09/2026: `y0=None` sempre virava "uma linha acima do fim da
    # página", não importa quantas linhas extras existissem — e as linhas
    # extras eram desenhadas ABAIXO disso, ou seja, fora da folha,
    # invisíveis. Com `selos_extra`, a linha NOMEADA (averbação/
    # arquivamento) vira a ÚLTIMA do bloco — a mais perto da borda, como
    # sempre foi sem extras — e as extras sobem a partir daí.
    linhas_extra = _linhas_reservadas_extra(selos_extra)
    if y0 is None:
        y0 = A4_H - SELO_FAIXA_H * (1 + linhas_extra) + 4
    d = ImageDraw.Draw(im)
    y0_nomeada = y0 + linhas_extra * SELO_FAIXA_H
    y1 = y0_nomeada + SELO_FAIXA_H - 16
    rotulo_font = _font(12)

    # Os rótulos das áreas são da moldura (LF06F); a REGRA de qual área sai —
    # a do arquivamento só com o selo 15.22 — é de quem chama.
    rotulos = rotulos or moldura()

    def _caixa(x0: int, y0: int, y1: int, rotulo: str, faixa_w: int,
              selo: dict | None) -> None:
        if selo and str(selo.get("numero") or "").strip():
            _carimbo_do_selo(d, im, x0=x0, y0=y0, x1=x0 + faixa_w, y1=y1,
                             rotulo=rotulo, selo=selo, rotulos=rotulos)
            return
        _caixa_tracejada(d, x0, y0, x0 + faixa_w, y1)
        tw = d.textlength(rotulo, font=rotulo_font)
        d.text((x0 + (faixa_w - tw) / 2, y0 + (SELO_FAIXA_H - 28) / 2),
               rotulo, fill=(160, 160, 160), font=rotulo_font)

    if com_arquivamento:
        gap = 16
        faixa_w = min((A4_W - 2 * SIDE - gap) // 2, 600)
        total_w = 2 * faixa_w + gap
        x_start = (A4_W - total_w) // 2
        _caixa(x_start, y0_nomeada, y1, rotulos["SELO_AVERBACAO"], faixa_w,
              selo_averbacao)
        _caixa(x_start + faixa_w + gap, y0_nomeada, y1,
               rotulos["SELO_ARQUIVAMENTO"], faixa_w, selo_arquivamento)
    else:
        # Largura útil da tira (100 mm @ 150 dpi ≈ 591 px), centrada.
        faixa_w = min(A4_W - 2 * SIDE, 600)
        x0_nomeada = (A4_W - faixa_w) // 2
        _caixa(x0_nomeada, y0_nomeada, y1, rotulos["SELO_AVERBACAO"], faixa_w,
              selo_averbacao)

    y_fim = y1
    if selos_extra:
        # **CRESCE PARA CIMA, A PARTIR DA LINHA NOMEADA** — a linha de
        # `selo_averbacao`/`selo_arquivamento` fica embaixo (mais perto da
        # borda, como sempre foi); as extras vão ocupando o espaço reservado
        # ACIMA dela (é para isso que `y0` já foi empurrado para cima).
        gap = 16
        faixa_w = min((A4_W - 2 * SIDE - gap) // 2, 600)
        total_w = 2 * faixa_w + gap
        x_start = (A4_W - total_w) // 2
        for i, selo in enumerate(selos_extra):
            linha_de_baixo_para_cima = i // 2
            coluna = i % 2
            linha_da_pagina = linhas_extra - 1 - linha_de_baixo_para_cima
            yl0 = y0 + linha_da_pagina * SELO_FAIXA_H
            yl1 = yl0 + SELO_FAIXA_H - 16
            xl0 = x_start + coluna * (faixa_w + gap)
            rotulo = str(selo.get("rotulo") or "selo")
            _caixa(xl0, yl0, yl1, rotulo, faixa_w, selo)
            y_fim = yl1
    return y_fim + 14


def _desenhar_cabecalho(im: Image.Image, *, linhas: Sequence[str],
                        intro_txt: str) -> int:
    d = ImageDraw.Draw(im)
    fb, fn = _font(22, True), _font(17)
    # Faixa do selo ficou no rodapé da última folha — cabeçalho sempre no topo.
    y = 20
    fontes = (fb, fn) + (fn,) * max(0, len(linhas) - 2)
    for texto, font in zip(linhas, fontes):
        tw = d.textlength(texto, font=font)
        d.text(((A4_W - tw) / 2, y), texto, fill="black", font=font)
        y += 28
    y += 6
    for line in _wrap(d, intro_txt, fn, A4_W - 2 * SIDE):
        d.text((SIDE, y), line, fill="black", font=fn)
        y += 24
    y = max(y + 8, HEADER_H)
    d.line([(SIDE - 8, y - 10), (A4_W - SIDE + 8, y - 10)],
           fill="black", width=1)
    return y


def _desenhar_encerramento(im: Image.Image, *, enc_txt: str, data_txt: str,
                           lavrante_funcao: str,
                           com_faixa_selo: bool = False,
                           linhas_extra: int = 0,
                           assinatura: str | None = None) -> None:
    """Encerramento no rodapé; sobe SELO_FAIXA_H (e mais, com `linhas_extra`

    de selos que não couberam nas duas caixas nomeadas) quando a faixa vem
    abaixo.

    `assinatura` é a linha de quem lavra já montada — a parte ===ASSINATURA===
    da moldura (LF06F). Sem ela, a do padrão, com a função de quem lavra.
    """
    d = ImageDraw.Draw(im)
    fn = _font(16)
    reservado_abaixo = (SELO_FAIXA_H * (1 + linhas_extra)) if com_faixa_selo else 0
    y = A4_H - FOOTER_H - reservado_abaixo + 8
    d.line([(SIDE - 8, y), (A4_W - SIDE + 8, y)], fill="black", width=1)
    y += 12
    for line in _wrap(d, enc_txt, fn, A4_W - 2 * SIDE):
        d.text((SIDE, y), line, fill="black", font=fn)
        y += 22
    y += 8
    d.text((SIDE, y), data_txt, fill="black", font=fn)
    y += 36
    if assinatura is None:
        claros = dict.fromkeys(CLAROS_DA_MOLDURA["ASSINATURA"], "")
        claros["funcao"] = lavrante_funcao
        assinatura = preencher_moldura(moldura(), "ASSINATURA", claros)
    d.text((SIDE, y), assinatura, fill="black", font=fn)


def _rodape_reservado(*, with_closing: bool, com_faixa_selo: bool,
                      linhas_extra: int = 0) -> int:
    """Altura do rodapé (encerramento e/ou faixa do selo) a reservar da imagem."""
    h = 40
    if with_closing:
        h = FOOTER_H
    if com_faixa_selo:
        h += SELO_FAIXA_H + linhas_extra * SELO_FAIXA_H
    return h


def _colar_imagem(im: Image.Image, src: Image.Image, top: int,
                  bottom: int) -> None:
    max_w, max_h = A4_W - 2 * SIDE, max(80, bottom - top - 8)
    iw, ih = src.size
    scale = min(max_w / max(iw, 1), max_h / max(ih, 1)) * 0.96
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    resized = src.resize((nw, nh), Image.Resampling.LANCZOS)
    im.paste(resized, ((A4_W - nw) // 2, top + max(0, (max_h - nh) // 2)))


def montar_pagina(src: Image.Image, *, textos: dict[str, Any],
                  with_header: bool, with_closing: bool,
                  rotulo: str = "",
                  com_faixa_selo: bool = False,
                  com_arquivamento: bool = False,
                  selo_averbacao: dict[str, Any] | None = None,
                  selo_arquivamento: dict[str, Any] | None = None,
                  selos_extra: Sequence[dict] | None = None,
                  ) -> Image.Image:
    linhas_extra = _linhas_reservadas_extra(selos_extra)
    # As frases do desenho vêm com os textos (`textos_prontos` as lê da casa);
    # quem monta os textos à mão recebe as do padrão.
    rotulos = textos.get("moldura") or moldura()
    im = Image.new("RGB", (A4_W, A4_H), "white")
    if with_header:
        top = _desenhar_cabecalho(
            im, linhas=textos["linhas_cabecalho"],
            intro_txt=textos["intro"])
    else:
        top = 28
    bottom = A4_H - _rodape_reservado(
        with_closing=with_closing, com_faixa_selo=com_faixa_selo,
        linhas_extra=linhas_extra)
    _colar_imagem(im, src.convert("RGB"), top, bottom)
    if with_closing:
        _desenhar_encerramento(
            im, enc_txt=textos["encerramento"],
            data_txt=textos["data"],
            lavrante_funcao=textos["ctx"]["funcao"],
            com_faixa_selo=com_faixa_selo, linhas_extra=linhas_extra,
            assinatura=preencher_moldura(rotulos, "ASSINATURA", textos["ctx"]))
    if com_faixa_selo:
        _desenhar_faixa_do_selo(im, com_arquivamento=com_arquivamento,
                                selo_averbacao=selo_averbacao,
                                selo_arquivamento=selo_arquivamento,
                                selos_extra=selos_extra, rotulos=rotulos)
    if rotulo:
        # Rótulo acima da faixa do selo (e das linhas extras) quando ela
        # ocupa o rodapé final.
        y_rotulo = (A4_H - SELO_FAIXA_H * (1 + linhas_extra) - 18
                    if com_faixa_selo else A4_H - 22)
        ImageDraw.Draw(im).text(
            (SIDE, y_rotulo), rotulo, fill="gray", font=_font(13))
    return im


# --------------------------------------------------------------- PDF bytes


def _jpeg_bytes(im: Image.Image, quality: int = 78) -> bytes:
    buf = BytesIO()
    im.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _images_to_pdf_bytes(images: Sequence[Image.Image]) -> bytes:
    page_w, page_h = 595.27, 841.89
    n = len(images)
    if n < 1:
        raise TeorRtdpjError("Nenhuma página para o PDF do teor.")
    body, offsets = bytearray(), [0]

    def write_obj(num: int, data: bytes) -> None:
        offsets.append(len(body))
        body.extend(f"{num} 0 obj\n".encode("latin-1"))
        body.extend(data)
        if not data.endswith(b"\n"):
            body.extend(b"\n")
        body.extend(b"endobj\n")

    kids = " ".join(f"{3 + 3 * i} 0 R" for i in range(n))
    write_obj(1, b"<< /Type /Catalog /Pages 2 0 R >>")
    write_obj(2, f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode(
        "latin-1"))
    for i, im in enumerate(images):
        jpg = _jpeg_bytes(im)
        page_num, cont_num, img_num = 3 + 3 * i, 4 + 3 * i, 5 + 3 * i
        write_obj(
            page_num,
            (f"<< /Type /Page /Parent 2 0 R "
             f"/MediaBox [0 0 {page_w:.2f} {page_h:.2f}] "
             f"/Contents {cont_num} 0 R "
             f"/Resources << /XObject << /Im0 {img_num} 0 R >> >> >>"
             ).encode("latin-1"))
        content = (f"q\n{page_w:.2f} 0 0 {page_h:.2f} 0 0 cm\n/Im0 Do\nQ\n"
                   .encode("latin-1"))
        write_obj(
            cont_num,
            f"<< /Length {len(content)} >>\nstream\n".encode("latin-1")
            + content + b"\nendstream")
        write_obj(
            img_num,
            (f"<< /Type /XObject /Subtype /Image "
             f"/Width {im.width} /Height {im.height} "
             f"/ColorSpace /DeviceRGB /BitsPerComponent 8 "
             f"/Filter /DCTDecode /Length {len(jpg)} >>\nstream\n"
             ).encode("latin-1") + jpg + b"\nendstream")
    xref_pos = len(body)
    total = 2 + 3 * n
    xref = [f"xref\n0 {total + 1}\n", "0000000000 65535 f \n"]
    xref += [f"{o:010d} 00000 n \n" for o in offsets[1:]]
    trailer = (f"trailer\n<< /Size {total + 1} /Root 1 0 R >>\n"
               f"startxref\n{xref_pos}\n%%EOF\n")
    return (b"%PDF-1.4\n" + bytes(body)
            + "".join(xref).encode("latin-1")
            + trailer.encode("latin-1"))


# ------------------------------------------------------ carregar imagens


def _paginas_de_pdf(caminho: Path) -> list[Image.Image]:
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise TeorRtdpjError(
            "Para usar PDF como folha do teor, o pacote pypdfium2 precisa "
            "estar instalado (ele já vem no requirements da casa)."
        ) from exc
    doc = pdfium.PdfDocument(str(caminho))
    out: list[Image.Image] = []
    try:
        for i in range(len(doc)):
            page = doc[i]
            bitmap = page.render(scale=150 / 72)
            out.append(bitmap.to_pil().convert("RGB"))
    finally:
        doc.close()
    return out


def carregar_folhas(caminhos: Sequence[str | Path]) -> list[Image.Image]:
    folhas: list[Image.Image] = []
    for raw in caminhos:
        path = Path(raw)
        if not path.is_file():
            raise TeorRtdpjError(f"Arquivo não encontrado: {path.name}")
        ext = path.suffix.lower()
        if ext in EXTENSOES_IMAGEM:
            folhas.append(Image.open(path).convert("RGB"))
        elif ext in EXTENSOES_PDF:
            folhas.extend(_paginas_de_pdf(path))
        else:
            raise TeorRtdpjError(
                f"Formato não suportado no teor: {path.name}. "
                "Use imagem (PNG/JPG/TIFF) ou PDF.")
    if not folhas:
        raise TeorRtdpjError(
            "Nenhuma folha digitalizada para montar o teor.")
    return folhas


# -------------------------------------------------------------- API pública


def gerar_pdf(*, numero_registro, imagens: Sequence[str | Path | Image.Image],
              lavrante_nome: str, lavrante_funcao: str,
              cns: str = "",
              unit_short: str = "",
              cidade: str = "", uf: str = "MA",
              dia: date | None = None,
              serie: str | None = None,
              atribuicao: str | int | None = None,
              tipo_ato: str | None = None,
              natureza_ato: str | None = None,
              data_assinatura: str | None = None,
              con: sqlite3.Connection | None = None,
              com_arquivamento: bool = False,
              selo_averbacao: dict[str, Any] | None = None,
              selo_arquivamento: dict[str, Any] | None = None,
              selos_extra: Sequence[dict] | None = None,
              motivo: str | None = None,
              protocolo: str | None = None,
              data_protocolo: str | None = None,
              apresentante: str | None = None,
              numero_averbacao: str | int | None = None,
              declaracoes: dict | None = None) -> bytes:
    """Monta o PDF do teor. Não grava nada, não sela — só IMPRIME o que já saiu.

    Lê o modelo de `mo_modelos` (via modelos_da_casa) quando `con` é dado;
    sem linha no banco, usa o piso do código. API antiga (só averbação RCPJ)
    continua válida: tipo_ato/série omitidos → AVERBACAO + RCPJ.

    Faixa do selo só no RODAPÉ da ÚLTIMA página. `com_arquivamento=True`
    (1ª averbação do pacote) reserva duas áreas: selo averbação + selo
    arquivamento. Cada imagem escala na área útil da própria página.

    **`selo_averbacao`/`selo_arquivamento` SÃO O QUE JÁ FOI SELADO**
    (`{"numero", "texto", "qr_texto"}`, de `sd_selos`) — no modelo do RI, o
    carimbo entra automaticamente na área reservada assim que o ato tem selo.
    Sem eles (`None`), a área continua sendo a moldura tracejada de sempre —
    esta função não pede selo a ninguém, só desenha o que já existe.

    **O CANCELAMENTO NÃO PRECISA DE IMAGEM** (LD05, 21/10/2026): o termo dele
    é a certidão do oficial — a causa e o documento que o autorizou, `motivo`
    —, e não a trasladação de um documento. Com o documento digitalizado, ele
    vai na folha; sem ele, a folha leva só o termo. Os outros atos continuam
    exigindo a imagem: o termo deles É a trasladação.

    **O QUE O TERMO DECLARA ALÉM DO TEOR** (LD09, 21/10/2026): `protocolo`,
    `data_protocolo` e `apresentante` do título, `numero_averbacao` e as
    `declaracoes` do livro — o que a rota lê com `rg_registro.dados_do_termo`.
    O total de páginas do Livro F (LRP art. 127-A, § 3º) é a conta das folhas
    que este PDF traslada, e não um número que alguém digita.
    """
    declarado = dict(protocolo=protocolo, data_protocolo=data_protocolo,
                     apresentante=apresentante,
                     numero_averbacao=numero_averbacao, declaracoes=declaracoes)

    def _textos(paginas: int | None = None) -> dict[str, Any]:
        return textos_prontos(
            numero_registro=numero_registro, lavrante_nome=lavrante_nome,
            lavrante_funcao=lavrante_funcao, cns=cns, unit_short=unit_short,
            cidade=cidade, uf=uf, dia=dia, serie=serie, atribuicao=atribuicao,
            tipo_ato=tipo_ato, natureza_ato=natureza_ato,
            data_assinatura=data_assinatura, con=con, motivo=motivo,
            paginas=paginas, **declarado)

    # o texto se confere ANTES das folhas, como sempre: o termo sem quem lavra
    # é recusado por isso, e não pelo arquivo que falta
    textos = _textos()

    folhas: list[Image.Image] = []
    caminhos: list[str | Path] = []
    for item in imagens:
        if isinstance(item, Image.Image):
            folhas.append(item.convert("RGB"))
        else:
            caminhos.append(item)
    if caminhos:
        folhas.extend(carregar_folhas(caminhos))
    if not folhas and normalizar_tipo_ato(tipo_ato) == TIPO_CANCELAMENTO:
        folhas.append(Image.new("RGB", (A4_W, A4_H), "white"))
    flags = flags_das_paginas(len(folhas))
    if (str(serie or "").strip().upper() in SERIES_COM_TOTAL_DE_PAGINAS
            and normalizar_tipo_ato(tipo_ato) == TIPO_REGISTRO):
        textos = _textos(paginas=len(folhas))
    pages = []
    n = len(folhas)
    # as declarações do LD09 só na primeira folha — ver `textos_prontos`
    seguintes = {**textos, **textos.get("folhas_seguintes", {})}
    for i, (src, (com_cab, com_enc)) in enumerate(zip(folhas, flags)):
        ultima = i == n - 1
        pages.append(montar_pagina(
            src, textos=textos if i == 0 else seguintes,
            with_header=com_cab, with_closing=com_enc,
            rotulo=f"{i + 1}/{n}",
            com_faixa_selo=ultima,
            com_arquivamento=bool(com_arquivamento) and ultima,
            selo_averbacao=selo_averbacao if ultima else None,
            selo_arquivamento=selo_arquivamento if ultima else None,
            selos_extra=selos_extra if ultima else None))
    return _images_to_pdf_bytes(pages)


def teor_texto_curto(numero_registro, *, tipo_ato: str | None = None,
                     natureza_ato: str | None = None,
                     data_assinatura: str | None = None) -> str:
    """Frase curta para o campo `teor` do lançamento (não substitui o PDF)."""
    return intro(numero_registro, tipo_ato=tipo_ato,
                 natureza_ato=natureza_ato, data_assinatura=data_assinatura)


def __getattr__(nome: str):
    """Os nomes antigos do texto de fábrica, lidos da base dos padrões.

    O TEXTO SAIU DESTE MÓDULO NO LF06A (19/10/2026) e mora em `modelos_padrao/`.
    Quem ainda importa o nome antigo recebe o padrão da base — o MESMO que o
    papel imprime, e não uma cópia que ficou para trás. `PADROES_POR_CHAVE`
    devolve os quatro, na ordem de sempre. Nome que não é de papel continua
    sendo `AttributeError`.
    """
    if nome.startswith("__"):
        raise AttributeError(nome)
    if nome == "PADROES_POR_CHAVE":
        # os quatro de sempre: o termo do cancelamento (LD05) nasceu no
        # catálogo, e não teve constante antiga
        return {chave: piso(chave) for (_, tipo), chave in CHAVES_MODELO.items()
                if tipo != TIPO_CANCELAMENTO}
    # os rótulos das áreas do selo, que viraram partes da moldura (LF06F)
    if nome == "SELO_FAIXA_ROTULO":
        return moldura()["SELO_AVERBACAO"]
    if nome == "SELO_FAIXA_ROTULO_ARQUIVAMENTO":
        return moldura()["SELO_ARQUIVAMENTO"]
    import modelos_da_casa as _MODELOS
    return _MODELOS.constante_antiga(__name__, nome)
