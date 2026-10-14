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

O QUE ESTE MÓDULO NÃO FAZ
  Não grava ato, não emite selo, não chama ATUALIZAR. Só monta o PDF.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, Sequence

from PIL import Image, ImageDraw, ImageFont

# ------------------------------------------------------------------ nomes
ATRIBUICAO_RCPJ = "Registro Civil das Pessoas Jurídicas"
ATRIBUICAO_RTD = "Registro de Títulos e Documentos"

TIPO_AVERBACAO = "AVERBACAO"
TIPO_REGISTRO = "REGISTRO"
TIPOS_ATO = (TIPO_AVERBACAO, TIPO_REGISTRO)

VERBOS = {
    TIPO_AVERBACAO: "AVERBADO",
    TIPO_REGISTRO: "REGISTRADO",
}

# Chaves do catálogo modelos_da_casa (formato CHAVES).
CHAVES_MODELO = {
    ("RCPJ", TIPO_AVERBACAO): "RCPJ_TEOR_AVERBACAO",
    ("RCPJ", TIPO_REGISTRO): "RCPJ_TEOR_REGISTRO",
    ("RTD", TIPO_AVERBACAO): "RTD_TEOR_AVERBACAO",
    ("RTD", TIPO_REGISTRO): "RTD_TEOR_REGISTRO",
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
SELO_FAIXA_ROTULO = "selo averbação"
SELO_FAIXA_ROTULO_ARQUIVAMENTO = "selo arquivamento"

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
)


class TeorRtdpjError(ValueError):
    """Impedimento de montagem do teor, com mensagem pronta para a tela."""


# Nome antigo — API compatível com quem já importa TeorAverbacaoError.
TeorAverbacaoError = TeorRtdpjError


# ------------------------------------------------------ piso (texto fábrica)

def _corpo_piso(*, atribuicao_nome: str, verbo: str, finalidade: str) -> str:
    """Texto de fábrica com marcas de seção — aprovado nos PDFs Santa Isabel."""
    return (
        f"{MARCA_CABECALHO}\n"
        f"{{unit_short}} — CNS {{cns}}\n"
        f"{{atribuicao}}\n"
        f"{MARCA_INTRO}\n"
        f"CERTIFICO que me foi apresentado para ser {verbo} no "
        f"Registro nº {{numero}} o documento digitalizado abaixo:\n"
        f"Tipo do ato: {{natureza_ato}}.\n"
        f"Data da assinatura: {{data_assinatura}}.\n"
        f"{MARCA_ENCERRAMENTO}\n"
        f"Era o que continha o documento apresentado para {finalidade}, "
        f"arquivado em sua íntegra mediante digitalização. "
        f"Eu, {{full_name}}, {{funcao}}, o subscrevo e assino.\n"
        f"{MARCA_DATA}\n"
        f"{{cidade}}/{{uf}}, {{data_extenso}}.\n"
    )


MODELO_RCPJ_TEOR_AVERBACAO = _corpo_piso(
    atribuicao_nome=ATRIBUICAO_RCPJ, verbo="AVERBADO",
    finalidade="averbação")
MODELO_RCPJ_TEOR_REGISTRO = _corpo_piso(
    atribuicao_nome=ATRIBUICAO_RCPJ, verbo="REGISTRADO",
    finalidade="registro")
MODELO_RTD_TEOR_AVERBACAO = _corpo_piso(
    atribuicao_nome=ATRIBUICAO_RTD, verbo="AVERBADO",
    finalidade="averbação")
MODELO_RTD_TEOR_REGISTRO = _corpo_piso(
    atribuicao_nome=ATRIBUICAO_RTD, verbo="REGISTRADO",
    finalidade="registro")

PADROES_POR_CHAVE = {
    "RCPJ_TEOR_AVERBACAO": MODELO_RCPJ_TEOR_AVERBACAO,
    "RCPJ_TEOR_REGISTRO": MODELO_RCPJ_TEOR_REGISTRO,
    "RTD_TEOR_AVERBACAO": MODELO_RTD_TEOR_AVERBACAO,
    "RTD_TEOR_REGISTRO": MODELO_RTD_TEOR_REGISTRO,
}


# ----------------------------------------------------------- normalização

def normalizar_tipo_ato(tipo_ato: str | None) -> str:
    t = (tipo_ato or TIPO_AVERBACAO).strip().upper()
    aliases = {
        "AVERBACAO": TIPO_AVERBACAO, "AVERBAÇÃO": TIPO_AVERBACAO,
        "AV": TIPO_AVERBACAO, "AVERBADO": TIPO_AVERBACAO,
        "REGISTRO": TIPO_REGISTRO, "REGISTRADO": TIPO_REGISTRO,
        "R": TIPO_REGISTRO, "LAVRATURA": TIPO_REGISTRO,
    }
    if t not in aliases:
        raise TeorRtdpjError(
            f"Tipo de ato «{tipo_ato}» não é AVERBACAO nem REGISTRO.")
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
    """
    n = str(numero_registro).strip()
    if not n:
        raise TeorRtdpjError(
            "O teor precisa do número do registro.")
    tipo = normalizar_tipo_ato(tipo_ato)
    verbo = VERBOS[tipo]
    base = (
        f"CERTIFICO que me foi apresentado para ser {verbo} no "
        f"Registro nº {n} o documento digitalizado abaixo:"
    )
    nat = (natureza_ato or "").strip()
    data = (data_assinatura or "").strip()
    if not nat and not data:
        return base
    partes = [base]
    if nat:
        partes.append(f"Tipo do ato: {nat}.")
    if data:
        partes.append(f"Data da assinatura: {data}.")
    return "\n".join(partes)


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
        row = con.execute(
            """SELECT 1 FROM sd_selos
                WHERE tabela='rg_atos' AND ato_id=?
                  AND (referencia LIKE '%:15.22:%'
                       OR texto LIKE '%Ato: 15.22%'
                       OR numero LIKE 'ARQUIV%')
                LIMIT 1""",
            (ato_id,)).fetchone()
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
    """Cabeçalho curto — SEM livro/folha/série/ficha."""
    cns = (cns or "").strip() or ""
    atr = nome_da_atribuicao(
        codigo_atribuicao(serie=serie, atribuicao=atribuicao))
    linha1 = f"{unit_short} — CNS {cns}"
    return [linha1, atr]


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
                 tipo_ato: str | None = None) -> str:
    nome = (lavrante_nome or "").strip()
    funcao = (lavrante_funcao or "").strip()
    if not nome:
        raise TeorRtdpjError(
            "O teor precisa do nome de quem lavra (sessão).")
    if not funcao:
        raise TeorRtdpjError(
            "O teor precisa da função de quem lavra (sessão).")
    tipo = normalizar_tipo_ato(tipo_ato)
    finalidade = ("averbação" if tipo == TIPO_AVERBACAO else "registro")
    return (
        f"Era o que continha o documento apresentado para {finalidade}, "
        "arquivado em sua íntegra mediante digitalização. "
        f"Eu, {nome}, {funcao}, o subscrevo e assino."
    )


def linha_data(*, cidade: str = "", uf: str = "MA",
               dia: date | None = None) -> str:
    return f"{cidade}/{uf}, {data_por_extenso(dia)}."


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
                     data_assinatura: str | None = None) -> dict[str, str]:
    tipo = normalizar_tipo_ato(tipo_ato)
    atr = codigo_atribuicao(serie=serie, atribuicao=atribuicao)
    return {
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
    return PADROES_POR_CHAVE.get(chave) or MODELO_RCPJ_TEOR_AVERBACAO


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
                   ) -> dict[str, Any]:
    """Monta cabeçalho/intro/encerramento/data a partir do modelo (DB ou piso)."""
    tipo = normalizar_tipo_ato(tipo_ato)
    chave = chave_do_modelo(serie=serie, atribuicao=atribuicao, tipo_ato=tipo)
    ctx = contexto_do_teor(
        numero_registro=numero_registro, lavrante_nome=lavrante_nome,
        lavrante_funcao=lavrante_funcao, cns=cns, unit_short=unit_short,
        cidade=cidade, uf=uf, dia=dia, serie=serie, atribuicao=atribuicao,
        tipo_ato=tipo, natureza_ato=natureza_ato,
        data_assinatura=data_assinatura)
    if not ctx["numero"]:
        raise TeorRtdpjError("O teor precisa do número do registro.")
    if not ctx["full_name"]:
        raise TeorRtdpjError(
            "O teor precisa do nome de quem lavra (sessão).")
    if not ctx["funcao"]:
        raise TeorRtdpjError(
            "O teor precisa da função de quem lavra (sessão).")

    bruto = corpo_do_modelo(chave, con=con)
    secoes = partir_modelo(bruto)
    if not secoes:
        # Piso estruturado, se o ajuste no banco removeu as marcas.
        secoes = partir_modelo(PADROES_POR_CHAVE[chave])

    cab_txt = aplicar_chaves(secoes.get("CABECALHO", ""), ctx)
    linhas = [ln.strip() for ln in cab_txt.splitlines() if ln.strip()]
    if not linhas:
        linhas = linhas_cabecalho(
            cns=ctx["cns"], unit_short=ctx["unit_short"],
            atribuicao=atribuicao, serie=serie)
    if cabecalho_tem_livro_ou_folha(linhas):
        raise TeorRtdpjError(
            "Cabeçalho do teor não pode citar livro/folha/série/ficha.")

    intro_bruto = secoes.get("INTRO") or ""
    if not intro_bruto.strip():
        intro_txt = intro(
            ctx["numero"], tipo_ato=tipo,
            natureza_ato=ctx.get("natureza_ato"),
            data_assinatura=ctx.get("data_assinatura"))
    else:
        intro_txt = aplicar_chaves(intro_bruto, ctx)
        # Compat: piso traz «Tipo do ato: {natureza_ato}.» / data; sem valor
        # vira «Tipo do ato: .» — remove só essas linhas vazias (não apaga
        # ajuste customizado em mo_modelos).
        limpas = []
        for ln in intro_txt.splitlines():
            s = ln.strip()
            if s in ("Tipo do ato: .", "Tipo do ato:",
                     "Data da assinatura: .", "Data da assinatura:"):
                continue
            limpas.append(ln)
        intro_txt = "\n".join(limpas).rstrip()
    enc_txt = aplicar_chaves(
        secoes.get("ENCERRAMENTO")
        or encerramento(lavrante_nome=ctx["full_name"],
                        lavrante_funcao=ctx["funcao"], tipo_ato=tipo),
        ctx)
    data_txt = aplicar_chaves(
        secoes.get("DATA")
        or f"{{cidade}}/{{uf}}, {{data_extenso}}.",
        ctx)

    return {
        "chave": chave,
        "linhas_cabecalho": linhas,
        "intro": intro_txt,
        "encerramento": enc_txt,
        "data": data_txt,
        "ctx": ctx,
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
                     selo: dict[str, Any]) -> None:
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
    if endereco_consulta and y_corpo <= y1 - 12:
        y_corpo += 3
        fonte_consulta = _font(9)
        d.text((texto_x0, y_corpo), f"Consulte em {endereco_consulta}",
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

    def _caixa(x0: int, y0: int, y1: int, rotulo: str, faixa_w: int,
              selo: dict | None) -> None:
        if selo and str(selo.get("numero") or "").strip():
            _carimbo_do_selo(d, im, x0=x0, y0=y0, x1=x0 + faixa_w, y1=y1,
                             rotulo=rotulo, selo=selo)
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
        _caixa(x_start, y0_nomeada, y1, SELO_FAIXA_ROTULO, faixa_w,
              selo_averbacao)
        _caixa(x_start + faixa_w + gap, y0_nomeada, y1,
               SELO_FAIXA_ROTULO_ARQUIVAMENTO, faixa_w, selo_arquivamento)
    else:
        # Largura útil da tira (100 mm @ 150 dpi ≈ 591 px), centrada.
        faixa_w = min(A4_W - 2 * SIDE, 600)
        x0_nomeada = (A4_W - faixa_w) // 2
        _caixa(x0_nomeada, y0_nomeada, y1, SELO_FAIXA_ROTULO, faixa_w,
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
                           linhas_extra: int = 0) -> None:
    """Encerramento no rodapé; sobe SELO_FAIXA_H (e mais, com `linhas_extra`

    de selos que não couberam nas duas caixas nomeadas) quando a faixa vem
    abaixo.
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
    d.text((SIDE, y),
           f"{lavrante_funcao}: ________________________________",
           fill="black", font=fn)


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
            com_faixa_selo=com_faixa_selo, linhas_extra=linhas_extra)
    if com_faixa_selo:
        _desenhar_faixa_do_selo(im, com_arquivamento=com_arquivamento,
                                selo_averbacao=selo_averbacao,
                                selo_arquivamento=selo_arquivamento,
                                selos_extra=selos_extra)
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
              selos_extra: Sequence[dict] | None = None) -> bytes:
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
    """
    textos = textos_prontos(
        numero_registro=numero_registro, lavrante_nome=lavrante_nome,
        lavrante_funcao=lavrante_funcao, cns=cns, unit_short=unit_short,
        cidade=cidade, uf=uf, dia=dia, serie=serie, atribuicao=atribuicao,
        tipo_ato=tipo_ato, natureza_ato=natureza_ato,
        data_assinatura=data_assinatura, con=con)

    folhas: list[Image.Image] = []
    caminhos: list[str | Path] = []
    for item in imagens:
        if isinstance(item, Image.Image):
            folhas.append(item.convert("RGB"))
        else:
            caminhos.append(item)
    if caminhos:
        folhas.extend(carregar_folhas(caminhos))
    flags = flags_das_paginas(len(folhas))
    pages = []
    n = len(folhas)
    for i, (src, (com_cab, com_enc)) in enumerate(zip(folhas, flags)):
        ultima = i == n - 1
        pages.append(montar_pagina(
            src, textos=textos, with_header=com_cab, with_closing=com_enc,
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
