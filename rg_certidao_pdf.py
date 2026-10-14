"""
Certidão de registro RCPJ/RTD — PDF visual (capa + folhas internas).

ENSINO DO OFICIAL (modelo SP adaptado — 11/09/2026):
  1) CAPA: cabeçalho da serventia (Cidade Exemplo / CNS), atribuição
     «Registro Civil das Pessoas Jurídicas» (com DAS) ou RTD, nº do
     registro + data, texto «Certifico e dou fé que o documento…
     contendo N páginas… foi apresentado… protocolado sob nº … tendo
     sido registrado…», Denominação, Natureza, data/local, assinatura
     do escrevente, quadro de emolumentos (pode ser zeros), espaço
     selo/QR (SEM inventar número de selo na prévia).
  2) FOLHAS INTERNAS: faixa no topo (~120–160 px) com mini-emolumentos
     + Registro Nº + data + texto curto de certificação + Página X/Y;
     abaixo a imagem da página do documento anexado.
  3) NÃO copia branding/telefones de SP. Casa = Ofício Único de
     Cidade Exemplo/MA — CNS 000000.

MODELO EDITÁVEL (relato #28 / modelos da casa)
  RCPJ_CERTIDAO_CAPA / RTD_CERTIDAO_CAPA
  RCPJ_CERTIDAO_FAIXA / RTD_CERTIDAO_FAIXA
  Código = piso; mo_modelos = ajuste; «voltar ao padrão» = apagar.

O QUE ESTE MÓDULO NÃO FAZ
  Não grava ato, não emite selo, não chama ATUALIZAR. Só monta o PDF.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Sequence

from PIL import Image, ImageDraw, ImageFont

# Reaproveita escala A4 / fontes / PDF JPEG do teor RTDPJ.
import rg_teor_rtdpj as TEOR

ATRIBUICAO_RCPJ = TEOR.ATRIBUICAO_RCPJ
ATRIBUICAO_RTD = TEOR.ATRIBUICAO_RTD

A4_W, A4_H = TEOR.A4_W, TEOR.A4_H
SIDE = TEOR.SIDE
FAIXA_H = 150  # banda no topo das folhas internas (~120–160 px)

EXTENSOES_IMAGEM = TEOR.EXTENSOES_IMAGEM
EXTENSOES_PDF = TEOR.EXTENSOES_PDF

MARCA_CABECALHO = "===CABECALHO==="
MARCA_TITULO = "===TITULO==="
MARCA_CORPO = "===CORPO==="
MARCA_DENOMINACAO = "===DENOMINACAO==="
MARCA_FECHO = "===FECHO==="
MARCA_FAIXA = "===FAIXA==="

PLACEHOLDERS = (
    "{unit_short}", "{cns}", "{atribuicao}", "{oficial}", "{endereco}",
    "{numero}", "{data_registro}", "{protocolo}", "{data_apresentacao}",
    "{paginas}", "{paginas_extenso}", "{denominacao}", "{natureza}",
    "{cidade}", "{uf}", "{data_extenso}", "{full_name}", "{funcao}",
    "{pagina}", "{total_paginas}", "{certidao_numero}", "{certidao_ano}",
    "{livro}", "{telefone}", "{email}", "{objeto_certificado}",
)

# Nomes de arquivos/descrições a NÃO pré-marcar na UI (pacotes grandes).
ANEXOS_PADRAO_EXCLUIR = (
    "DOCUMENTOS", "registro_originario", "pacote", "PARA AVERBA",
)

MESES = TEOR.MESES

NUMEROS_EXTENSO = {
    0: "zero", 1: "uma", 2: "duas", 3: "três", 4: "quatro", 5: "cinco",
    6: "seis", 7: "sete", 8: "oito", 9: "nove", 10: "dez",
    11: "onze", 12: "doze", 13: "treze", 14: "quatorze", 15: "quinze",
    16: "dezesseis", 17: "dezessete", 18: "dezoito", 19: "dezenove",
    20: "vinte",
}


class CertidaoPdfError(ValueError):
    """Impedimento de montagem da certidão PDF, com mensagem para a tela."""


# ------------------------------------------------------ piso (texto fábrica)

def _capa_piso() -> str:
    """Capa adaptada do modelo SP — sem telefones/branding de SP."""
    return (
        f"{MARCA_CABECALHO}\n"
        f"{{unit_short}} — CNS {{cns}}\n"
        f"Oficial: {{oficial}}\n"
        f"{{endereco}}\n"
        f"{MARCA_TITULO}\n"
        f"{{atribuicao}}\n"
        f"Nº {{numero}} de {{data_registro}}\n"
        f"{MARCA_CORPO}\n"
        # **`{{objeto_certificado}}` DIZ O QUE ESTÁ SENDO CERTIFICADO** —
        # correção do oficial em 12/09/2026: «no PDF precisa arrumar a
        # parte introdutória, não está com os dados do serviço efetivo de
        # certidão de averbações». Antes, esta frase sempre falava do
        # REGISTRO original, mesmo quando a certidão era só sobre
        # averbações posteriores — quem monta o texto (a rota) decide o
        # que entra aqui: "o registro de {natureza}" ou "a(s) averbação(ões)
        # nº X, Y".
        #
        # **E A FRASE EM SI AINDA AFIRMAVA "REGISTRADO... NA PRESENTE
        # DATA"** — mesmo achado, mesmo dia: dizia que o documento "foi
        # apresentado... tendo sido registrado sob nº {numero}... na
        # presente data", frase que só faz sentido quando o que se
        # certifica É o próprio registro, lavrado hoje. Numa certidão de
        # averbação, o registro nº {numero} é de {data_registro} — não de
        # hoje —, e o que se apresentou/registrou agora foi a averbação, já
        # nomeada em {objeto_certificado}. A frase passa a REFERENCIAR o
        # registro (nº e data dele) em vez de afirmar que ele aconteceu na
        # data da certidão.
        f"Certifico e dou fé que o documento, contendo {{paginas}} "
        f"({{paginas_extenso}}) página(s) (arquivo anexo), foi apresentado "
        f"em {{data_apresentacao}}, protocolado sob nº {{protocolo}}, "
        f"referente ao registro nº {{numero}} de {{data_registro}}, no "
        f"{{livro}} desta serventia. A presente certidão tem por objeto "
        f"{{objeto_certificado}}.\n"
        f"{MARCA_DENOMINACAO}\n"
        f"Denominação\n"
        f"{{denominacao}}\n"
        f"Natureza:\n"
        f"{{natureza}}\n"
        f"{MARCA_FECHO}\n"
        f"{{cidade}}, {{data_extenso}}.\n"
        f"Eu, {{full_name}}, {{funcao}}, o subscrevo e assino.\n"
        # Frase «parte integrante…» removida a pedido do oficial (11/09/2026).
    )


def _faixa_piso() -> str:
    """Texto curto da faixa de cada folha interna.

    **TAMBÉM PRECISA DIZER O OBJETO** — mesma correção de 12/09/2026: a
    faixa fica no topo de TODA folha interna, e falava só do registro
    original mesmo quando a certidão é de averbação — quem lê uma folha
    solta (fotocópia, por exemplo) via só a história do registro, nunca a
    do que de fato foi certificado.
    """
    return (
        f"{MARCA_FAIXA}\n"
        f"Protocolo nº {{protocolo}} de {{data_apresentacao}}: certidão de "
        f"{{objeto_certificado}}, sob nº {{numero}} em {{data_registro}} "
        f"neste {{unit_short}} — {{atribuicao}}. Assinado por "
        f"{{full_name}} — {{funcao}}.\n"
    )


MODELO_RCPJ_CERTIDAO_CAPA = _capa_piso()
MODELO_RTD_CERTIDAO_CAPA = _capa_piso()
MODELO_RCPJ_CERTIDAO_FAIXA = _faixa_piso()
MODELO_RTD_CERTIDAO_FAIXA = _faixa_piso()

PADROES_POR_CHAVE = {
    "RCPJ_CERTIDAO_CAPA": MODELO_RCPJ_CERTIDAO_CAPA,
    "RTD_CERTIDAO_CAPA": MODELO_RTD_CERTIDAO_CAPA,
    "RCPJ_CERTIDAO_FAIXA": MODELO_RCPJ_CERTIDAO_FAIXA,
    "RTD_CERTIDAO_FAIXA": MODELO_RTD_CERTIDAO_FAIXA,
}

CHAVES_CAPA = {"RCPJ": "RCPJ_CERTIDAO_CAPA", "RTD": "RTD_CERTIDAO_CAPA"}
CHAVES_FAIXA = {"RCPJ": "RCPJ_CERTIDAO_FAIXA", "RTD": "RTD_CERTIDAO_FAIXA"}


# ----------------------------------------------------------- utilidades

def paginas_por_extenso(n: int) -> str:
    n = int(n)
    if n in NUMEROS_EXTENSO:
        return NUMEROS_EXTENSO[n]
    if n < 100:
        dezena, unidade = divmod(n, 10)
        base = {
            2: "vinte", 3: "trinta", 4: "quarenta", 5: "cinquenta",
            6: "sessenta", 7: "setenta", 8: "oitenta", 9: "noventa",
        }.get(dezena, str(n))
        if unidade == 0:
            return base
        return f"{base} e {NUMEROS_EXTENSO.get(unidade, str(unidade))}"
    return str(n)


def _data_br(valor: str | date | datetime | None) -> str:
    if valor is None or valor == "":
        return ""
    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    s = str(valor).strip()
    if len(s) >= 10 and s[4] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[:4]}"
    return s


def _font(size: int, bold: bool = False):
    return TEOR._font(size, bold)


def _wrap(draw, text, font, max_w):
    return TEOR._wrap(draw, text, font, max_w)


def codigo_atribuicao(*, serie=None, atribuicao=None) -> str:
    return TEOR.codigo_atribuicao(serie=serie, atribuicao=atribuicao)


def nome_da_atribuicao(codigo: str) -> str:
    return TEOR.nome_da_atribuicao(codigo)


def chave_capa(*, serie=None, atribuicao=None) -> str:
    return CHAVES_CAPA[codigo_atribuicao(serie=serie, atribuicao=atribuicao)]


def chave_faixa(*, serie=None, atribuicao=None) -> str:
    return CHAVES_FAIXA[codigo_atribuicao(serie=serie, atribuicao=atribuicao)]


def aplicar_chaves(texto: str, ctx: dict[str, str]) -> str:
    class _Ctx(dict):
        def __missing__(self, key: str) -> str:
            raise CertidaoPdfError(
                f"O modelo da certidão usa o claro {{{key}}}, que o sistema "
                f"não preenche. Claros conhecidos: "
                + ", ".join(PLACEHOLDERS) + ".")
    try:
        return (texto or "").format_map(_Ctx(ctx))
    except ValueError as erro:
        raise CertidaoPdfError(
            f"Modelo da certidão com chave malformada: {erro}") from erro


def partir_modelo(corpo: str, marcas: Sequence[str]) -> dict[str, str]:
    texto = corpo or ""
    nomes = "|".join(re.escape(m.strip("=")) for m in marcas)
    padrao = re.compile(rf"===({nomes})===\s*", re.IGNORECASE)
    pedacos = padrao.split(texto)
    partes: dict[str, str] = {}
    i = 1
    while i + 1 < len(pedacos):
        nome = pedacos[i].upper()
        valor = re.split(r"\n===", pedacos[i + 1], maxsplit=1)[0]
        partes[nome] = valor.strip("\n")
        i += 2
    return partes


def corpo_do_modelo(chave: str, con: sqlite3.Connection | None = None) -> str:
    if con is not None:
        try:
            import modelos_da_casa as CASA
            return CASA.corpo_de(con, chave)
        except Exception:  # noqa: BLE001 — piso seguro
            pass
    return PADROES_POR_CHAVE.get(chave) or MODELO_RCPJ_CERTIDAO_CAPA


def livro_impresso(serie: str | None, volume: str | None) -> str:
    letra = (serie or "").split("_")[-1] or "A"
    v = str(volume or "").strip().lstrip("0")
    atr = codigo_atribuicao(serie=serie)
    if atr == "RTD":
        base = "Livro de Registro de Títulos e Documentos"
    else:
        base = "Livro de Registro Civil das Pessoas Jurídicas"
    sufixo = f" {letra}" + (f"-{v}" if v else "")
    return base + sufixo


# ----------------------------------------------------------- contexto

def contexto_certidao(
    *,
    numero,
    data_registro: str | date | None = None,
    protocolo: str = "",
    data_apresentacao: str | date | None = None,
    paginas: int = 1,
    denominacao: str = "",
    natureza: str = "",
    objeto_certificado: str = "",
    identificacao_curta: str = "",
    identificacao_data: str | date | None = None,
    lavrante_nome: str = "",
    lavrante_funcao: str = "",
    cns: str = "",
    unit_short: str = "",
    oficial: str = "",
    endereco: str = "",
    telefone: str = "",
    email: str = "",
    cidade: str = "",
    uf: str = "MA",
    serie: str | None = None,
    atribuicao: str | int | None = None,
    volume: str | None = None,
    dia: date | None = None,
    certidao_numero: str = "",
    certidao_ano: str = "",
    pagina: int = 1,
    total_paginas: int = 1,
) -> dict[str, str]:
    atr = codigo_atribuicao(serie=serie, atribuicao=atribuicao)
    n_pag = max(1, int(paginas or 1))
    d_reg = _data_br(data_registro) or _data_br(dia or date.today())
    d_apr = _data_br(data_apresentacao) or d_reg
    return {
        "cns": (cns or "").strip() or "",
        "unit_short": unit_short or "",
        "atribuicao": nome_da_atribuicao(atr),
        "oficial": (oficial or "").strip() or "",
        "endereco": (endereco or "").strip(),
        "telefone": (telefone or "").strip(),
        "email": (email or "").strip(),
        "numero": str(numero).strip(),
        "data_registro": d_reg,
        "protocolo": (protocolo or "").strip() or "—",
        "data_apresentacao": d_apr,
        "paginas": str(n_pag),
        "paginas_extenso": paginas_por_extenso(n_pag),
        "denominacao": (denominacao or "").strip() or "—",
        "natureza": (natureza or "").strip() or "—",
        # Sem que a rota mande nada, o padrão continua descrevendo o
        # REGISTRO — o mesmo texto de sempre, e não uma frase vazia.
        "objeto_certificado": (objeto_certificado or "").strip() or (
            f"o registro de {natureza.strip()}" if (natureza or "").strip()
            else "o registro"),
        # **A CAIXA "Página/Registro Nº.../data" DE TODA FOLHA INTERNA** —
        # achado do oficial em 12/09/2026: «segue o registro 148 na parte
        # esquerda superior do cabeçalho». Aquela caixa (desenhada em
        # `montar_folha_interna`) sempre dizia "Registro Nº {numero}" com a
        # data do REGISTRO, mesmo numa certidão só de averbação — e ali,
        # sozinha, sem a frase da faixa ao lado para dar contexto, ela lia
        # como se a certidão fosse do registro. Quando a rota manda
        # `identificacao_curta` (o rótulo do que está sendo certificado, ex.
        # "Averbação nº 378, 379"), a caixa mostra ELE — com a data de
        # `data_apresentacao` (a da própria averbação) — em vez do registro.
        "identificacao_curta": (
            (identificacao_curta or "").strip() or f"Registro Nº {numero}"),
        "identificacao_data": _data_br(identificacao_data) or d_reg,
        "cidade": cidade or "",
        "uf": uf or "MA",
        "data_extenso": TEOR.data_por_extenso(dia or date.today()),
        "full_name": (lavrante_nome or "").strip(),
        "funcao": (lavrante_funcao or "").strip(),
        "pagina": f"{int(pagina):06d}",
        "total_paginas": f"{int(total_paginas):06d}",
        "certidao_numero": str(certidao_numero or ""),
        "certidao_ano": str(certidao_ano or ""),
        "livro": livro_impresso(serie, volume),
    }


def textos_prontos(
    *,
    numero,
    lavrante_nome: str,
    lavrante_funcao: str,
    con: sqlite3.Connection | None = None,
    serie: str | None = None,
    atribuicao: str | int | None = None,
    **kwargs,
) -> dict[str, Any]:
    if not str(numero or "").strip():
        raise CertidaoPdfError("A certidão precisa do número do registro.")
    if not (lavrante_nome or "").strip():
        raise CertidaoPdfError(
            "A certidão precisa do nome de quem assina (sessão).")
    if not (lavrante_funcao or "").strip():
        raise CertidaoPdfError(
            "A certidão precisa da função de quem assina (sessão).")

    atr = codigo_atribuicao(serie=serie, atribuicao=atribuicao)
    chave_c = CHAVES_CAPA[atr]
    chave_f = CHAVES_FAIXA[atr]
    ctx = contexto_certidao(
        numero=numero, lavrante_nome=lavrante_nome,
        lavrante_funcao=lavrante_funcao, serie=serie, atribuicao=atribuicao,
        **kwargs)

    bruto_capa = corpo_do_modelo(chave_c, con=con)
    secoes = partir_modelo(
        bruto_capa,
        (MARCA_CABECALHO, MARCA_TITULO, MARCA_CORPO, MARCA_DENOMINACAO,
         MARCA_FECHO))
    if not secoes:
        secoes = partir_modelo(
            PADROES_POR_CHAVE[chave_c],
            (MARCA_CABECALHO, MARCA_TITULO, MARCA_CORPO, MARCA_DENOMINACAO,
             MARCA_FECHO))

    bruto_faixa = corpo_do_modelo(chave_f, con=con)
    faixa_sec = partir_modelo(bruto_faixa, (MARCA_FAIXA,))
    if not faixa_sec:
        faixa_sec = partir_modelo(
            PADROES_POR_CHAVE[chave_f], (MARCA_FAIXA,))

    return {
        "chave_capa": chave_c,
        "chave_faixa": chave_f,
        "cabecalho": aplicar_chaves(secoes.get("CABECALHO", ""), ctx),
        "titulo": aplicar_chaves(secoes.get("TITULO", ""), ctx),
        "corpo": aplicar_chaves(secoes.get("CORPO", ""), ctx),
        "denominacao": aplicar_chaves(secoes.get("DENOMINACAO", ""), ctx),
        "fecho": aplicar_chaves(secoes.get("FECHO", ""), ctx),
        "faixa": aplicar_chaves(faixa_sec.get("FAIXA", ""), ctx),
        "ctx": ctx,
    }


# ------------------------------------------------------ emolumentos (quadro)

# **OS FUNDOS SÃO OS DO MARANHÃO, E NÃO OS DE SÃO PAULO** — correção do
# oficial em 11/09/2026: «a tabela que está na certidão também não faz
# sentido pra o Maranhão, de emolumentos». O quadro nasceu copiando as
# categorias do modelo de SP que serviu de referência para o LAYOUT
# («Estado», «Secretaria da Fazenda», «Registro Civil», «Tribunal de
# Justiça», «Ministério Público») — só que aquilo é a repartição de SP, e
# esta casa não recolhe para nenhum desses. Os fundos que o resto do
# sistema já usa em toda custa desta serventia são FERC, FADEP, FEMP e
# FERRFIS (`atribuicoes.FUNDOS`, `custas.CAMPOS_NO_TOTAL`) — e o ISS não
# entra no total (regra medida e já escrita em `custas.py`).
CAMPOS_EMOL = (
    ("emolumentos", "Emolumentos"),
    ("ferc", "FERC"),
    ("fadep", "FADEP"),
    ("femp", "FEMP"),
    ("ferrfis", "FERRFIS"),
    ("total", "Total"),
)

CAMPOS_EMOL_FAIXA = (
    ("emolumentos", "Emolumentos"),
    ("ferc", "FERC"),
    ("fadep", "FADEP"),
    ("femp", "FEMP"),
    ("ferrfis", "FERRFIS"),
    ("total", "Total"),
)


def _emol_zeros() -> dict[str, str]:
    return {k: "R$ 0,00" for k, _ in CAMPOS_EMOL}


def _fmt_emol(valor) -> str:
    if valor is None or valor == "":
        return "R$ 0,00"
    if isinstance(valor, (int, float)):
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace(
            "X", ".")
    s = str(valor).strip()
    if s.upper().startswith("R$"):
        return s
    return f"R$ {s}"


def normalizar_emolumentos(emolumentos: dict | None) -> dict[str, str]:
    base = _emol_zeros()
    if not emolumentos:
        return base
    for k, _ in CAMPOS_EMOL:
        if k in emolumentos:
            base[k] = _fmt_emol(emolumentos[k])
    return base


# ----------------------------------------------------------- desenho capa

def _desenhar_quadro_emol(im: Image.Image, emol: dict[str, str],
                         y0: int) -> int:
    """Quadro de emolumentos, com os FUNDOS DO MARANHÃO. Devolve Y abaixo.

    3 colunas × 2 linhas — os 6 campos de `CAMPOS_EMOL` cabem exatos, sem
    célula vazia sobrando (o quadro antigo, de SP, tinha 10 campos em 2×5).
    """
    d = ImageDraw.Draw(im)
    fn = _font(12)
    fb = _font(12, True)
    x0, x1 = SIDE, A4_W - SIDE
    pares = list(CAMPOS_EMOL)
    cols = min(len(pares), 3)
    linhas = -(-len(pares) // cols)  # divisão arredondada para cima
    cell_w = (x1 - x0) // cols
    row_h = 42
    for row in range(linhas):
        for col in range(cols):
            idx = row * cols + col
            if idx >= len(pares):
                break
            chave, rotulo = pares[idx]
            cx = x0 + col * cell_w
            cy = y0 + row * row_h
            d.rectangle([cx, cy, cx + cell_w, cy + row_h], outline="black",
                        width=1)
            d.text((cx + 4, cy + 3), rotulo, fill="black", font=fb)
            d.text((cx + 4, cy + 20), emol.get(chave, "R$ 0,00"),
                   fill="black", font=fn)
    return y0 + linhas * row_h + 12


def _desenhar_area_selo(im: Image.Image, y0: int,
                       selo: dict[str, Any] | None = None) -> int:
    """A área do selo/QR na capa. Reservada (sem inventar número) — ou

    **COM O CARIMBO DE VERDADE**, quando a certidão já foi selada — achado
    do oficial em 12/09/2026: «segue sem selo a certidão que emiti». O
    selo saía certinho no banco (`at_certidoes.selo`, `sd_selos`), mas
    esta função NUNCA tinha um jeito de recebê-lo: sempre desenhava só a
    moldura tracejada com os rótulos "selo / verificação" e "QR /
    autenticação" — mesmo para uma certidão já selada. Reaproveita
    `TEOR._carimbo_do_selo` (o mesmo carimbo do teor da averbação), e não
    desenha um segundo do zero.
    """
    if selo and str(selo.get("numero") or "").strip():
        d = ImageDraw.Draw(im)
        faixa_w = min(A4_W - 2 * SIDE, 600)
        x0 = (A4_W - faixa_w) // 2
        h = 160
        TEOR._carimbo_do_selo(d, im, x0=x0, y0=y0, x1=x0 + faixa_w,
                              y1=y0 + h, rotulo="selo da certidão", selo=selo)
        return y0 + h + 8
    d = ImageDraw.Draw(im)
    fn = _font(12)
    h = 160
    meio = A4_W // 2
    gap = 12
    for i, rotulo in enumerate(("selo / verificação", "QR / autenticação")):
        x0 = SIDE if i == 0 else meio + gap // 2
        x1 = meio - gap // 2 if i == 0 else A4_W - SIDE
        d.rectangle([x0, y0, x1, y0 + h], outline=(160, 160, 160), width=1)
        # tracejado interno leve
        tw = d.textlength(rotulo, font=fn)
        d.text((x0 + (x1 - x0 - tw) / 2, y0 + h / 2 - 8), rotulo,
               fill=(160, 160, 160), font=fn)
    return y0 + h + 8


def montar_capa(textos: dict[str, Any], *,
                emolumentos: dict[str, str] | None = None,
                com_emolumentos: bool = True,
                primeira_folha: Image.Image | None = None,
                selo: dict[str, Any] | None = None
                ) -> tuple[Image.Image, bool]:
    im = Image.new("RGB", (A4_W, A4_H), "white")
    d = ImageDraw.Draw(im)
    fb, fn, ft = _font(22, True), _font(16), _font(20, True)
    y = 28
    max_w = A4_W - 2 * SIDE

    for i, ln in enumerate(
            [x.strip() for x in textos["cabecalho"].splitlines() if x.strip()]):
        font = fb if i == 0 else fn
        for wrap in _wrap(d, ln, font, max_w):
            tw = d.textlength(wrap, font=font)
            d.text(((A4_W - tw) / 2, y), wrap, fill="black", font=font)
            y += 26 if i == 0 else 22
    y += 10
    d.line([(SIDE, y), (A4_W - SIDE, y)], fill="black", width=1)
    y += 16

    for i, ln in enumerate(
            [x.strip() for x in textos["titulo"].splitlines() if x.strip()]):
        font = ft if i == 0 else fb
        for wrap in _wrap(d, ln, font, max_w):
            tw = d.textlength(wrap, font=font)
            d.text(((A4_W - tw) / 2, y), wrap, fill="black", font=font)
            y += 30 if i == 0 else 26
    y += 14

    for ln in textos["corpo"].splitlines():
        s = ln.strip()
        if not s:
            y += 8
            continue
        for wrap in _wrap(d, s, fn, max_w):
            d.text((SIDE, y), wrap, fill="black", font=fn)
            y += 22
    y += 16

    den_lines = [x for x in textos["denominacao"].splitlines() if x.strip()]
    for i, ln in enumerate(den_lines):
        font = fb if i in (0, 2) else _font(18, True) if i in (1, 3) else fn
        # rótulos (Denominação / Natureza) em bold menor; valores maiores
        if ln.strip().lower().startswith("denom") or ln.strip().lower().startswith("natur"):
            font = fb
        elif i in (1, 3) or (i > 0 and not den_lines[i - 1].lower().startswith(
                ("denom", "natur"))):
            font = _font(18, True)
        d.text((SIDE, y), ln.strip(), fill="black", font=font)
        y += 26
    y += 20

    for ln in textos["fecho"].splitlines():
        s = ln.strip()
        if not s:
            y += 8
            continue
        for wrap in _wrap(d, s, fn, max_w):
            d.text((SIDE, y), wrap, fill="black", font=fn)
            y += 22
    y += 24

    if com_emolumentos:
        emol = normalizar_emolumentos(emolumentos)
        y = _desenhar_quadro_emol(im, emol, y)
        y += 8

    # **A PRIMEIRA FOLHA DO DOCUMENTO CABE NA CAPA** — pedido do oficial em
    # 11/09/2026: a capa é só cabeçalho/texto/emolumentos, e a primeira
    # imagem do documento sempre nascia numa folha à parte — uma página
    # inteira gasta com quase nada, quando sobrava espaço em branco embaixo
    # do quadro de emolumentos. Cola aqui SE sobrar altura que valha a pena
    # (120 px é pouco menos que uma linha de texto de sobra); senão, a
    # imagem cai para a primeira folha interna, como sempre foi — nunca
    # força um encaixe que cortaria a imagem.
    colou_primeira_folha = False
    espaco_do_selo = 170
    if primeira_folha is not None:
        limite_inferior = A4_H - 20 - espaco_do_selo
        if limite_inferior - y > 120:
            TEOR._colar_imagem(im, primeira_folha.convert("RGB"), y,
                               limite_inferior)
            y = limite_inferior
            colou_primeira_folha = True

    # Área do selo — sempre reservada na capa; vazia na prévia, ou com o
    # carimbo de verdade quando a certidão já foi selada.
    if y + 170 < A4_H - 20:
        _desenhar_area_selo(im, max(y, A4_H - 190), selo=selo)
    else:
        _desenhar_area_selo(im, y, selo=selo)
    return im, colou_primeira_folha


# ------------------------------------------------------ folhas internas

def _desenhar_mini_emol(d: ImageDraw.ImageDraw, emol: dict[str, str],
                       y: int) -> int:
    fn = _font(10)
    fb = _font(10, True)
    x = SIDE
    max_x = A4_W - SIDE
    for chave, rotulo in CAMPOS_EMOL_FAIXA:
        cell = 108
        if x + cell > max_x:
            break
        d.rectangle([x, y, x + cell - 2, y + 28], outline=(120, 120, 120),
                    width=1)
        d.text((x + 2, y + 1), rotulo, fill="black", font=fb)
        d.text((x + 2, y + 13), emol.get(chave, "R$ 0,00"), fill="black",
               font=fn)
        x += cell
    return y + 32


def montar_folha_interna(
    src: Image.Image,
    *,
    textos: dict[str, Any],
    pagina: int,
    total_paginas: int,
    emolumentos: dict[str, str] | None = None,
    com_emolumentos: bool = True,
) -> Image.Image:
    im = Image.new("RGB", (A4_W, A4_H), "white")
    d = ImageDraw.Draw(im)
    fn, fb = _font(13), _font(13, True)
    ctx = dict(textos["ctx"])
    ctx["pagina"] = f"{pagina:06d}"
    ctx["total_paginas"] = f"{total_paginas:06d}"
    # Reaplica faixa com página atual
    chave_f = textos["chave_faixa"]
    bruto = PADROES_POR_CHAVE.get(chave_f, MODELO_RCPJ_CERTIDAO_FAIXA)
    # Usa o texto já resolvido trocando só a página via re-format se preciso
    faixa_txt = textos["faixa"]

    y = 10
    # Caixa Página / Registro Nº / data (esquerda)
    box_w = 160
    d.rectangle([SIDE, y, SIDE + box_w, y + 70], outline="black", width=1)
    d.text((SIDE + 6, y + 4), "Página", fill="black", font=fb)
    d.text((SIDE + 6, y + 22),
           f"{ctx['pagina']}/{ctx['total_paginas']}", fill="black", font=fn)
    # **NÃO É SEMPRE "Registro Nº X"** — achado do oficial em 12/09/2026:
    # «segue o registro 148 na parte esquerda superior do cabeçalho». Numa
    # certidão de averbação, `identificacao_curta`/`identificacao_data` (de
    # `contexto_certidao`) já trazem o rótulo e a data do que de fato está
    # sendo certificado; só caem no registro quando a rota não manda nada
    # de diferente (certidão do próprio registro).
    rotulo_curto = ctx.get("identificacao_curta") or f"Registro Nº {ctx['numero']}"
    fb_rotulo = fb if len(rotulo_curto) <= 18 else _font(11, True)
    d.text((SIDE + 6, y + 40), rotulo_curto, fill="black", font=fb_rotulo)
    d.text((SIDE + 6, y + 54),
           ctx.get("identificacao_data") or ctx["data_registro"],
           fill="black", font=fn)

    # Texto da faixa à direita
    tx = SIDE + box_w + 12
    max_w = A4_W - SIDE - tx
    ty = y
    for wrap in _wrap(d, faixa_txt, fn, max_w):
        d.text((tx, ty), wrap, fill="black", font=fn)
        ty += 16
    y = max(y + 74, ty + 4)

    if com_emolumentos:
        y = _desenhar_mini_emol(d, normalizar_emolumentos(emolumentos), y)

    y = max(y + 4, FAIXA_H)
    d.line([(SIDE - 4, y), (A4_W - SIDE + 4, y)], fill="black", width=1)
    top = y + 8
    bottom = A4_H - 28
    TEOR._colar_imagem(im, src.convert("RGB"), top, bottom)
    return im


# ------------------------------------------------------ carregar folhas

def carregar_folhas(caminhos: Sequence[str | Path]) -> list[Image.Image]:
    return TEOR.carregar_folhas(caminhos)


def anexo_padrao_marcado(nome: str | None, descricao: str | None = None) -> bool:
    """Default sensato: marca peças úteis; pula pacotes mistos grandes."""
    junto = f"{nome or ''} {descricao or ''}".upper()
    for proibido in ANEXOS_PADRAO_EXCLUIR:
        if proibido.upper() in junto:
            return False
    return True



# Fallback legado (Santa Isabel / registro 148): ato_id → attachment_id do
# RG_REGISTRO, só quando ainda não há vínculo attachments RG_ATO.
FALLBACK_ATO_PARA_ANEXO: dict[int, int] = {
    75: 37,  # AVERBACAO 374 → 01_edital_ata_lista.pdf
    76: 38,  # AVERBACAO 375 → 02_estatuto_consolidado.pdf
    73: 33,  # REGISTRO 148 → 0148_folha_067.png
}


def rotulo_ato_para_certidao(ato: dict) -> str:
    """Rótulo curto: tipo + número_ordem + natureza (se houver no teor)."""
    tipo = str(ato.get("tipo") or "").strip().upper() or "ATO"
    ordem = ato.get("numero_ordem") or ato.get("rotulo") or ""
    nat = ""
    try:
        nat, _ = TEOR.parse_campos_do_teor(ato.get("teor"))
    except Exception:
        nat = ""
    if not nat:
        trecho = " ".join(str(ato.get("teor") or "").split())[:50]
        nat = trecho
    base = f"{tipo} n. {ordem}" if ordem != "" else tipo
    return f"{base} — {nat}" if nat else base


def atos_padrao_marcados(atos: Sequence[dict]) -> list[dict]:
    """Default da prévia/emissão: REGISTRO + todas as AVERBAÇÕES."""
    out = []
    for a in atos or []:
        tipo = str(a.get("tipo") or "").strip().upper()
        if tipo == "REGISTRO" or tipo.startswith("AVERB"):
            out.append(a)
    return out


def filtrar_atos_por_ids(atos: Sequence[dict], ato_ids: Sequence[int] | None
                        ) -> list[dict]:
    """Se ato_ids é None, devolve o default; senão só os ids pedidos (ordem)."""
    base = list(atos or [])
    if ato_ids is None:
        return atos_padrao_marcados(base)
    ids = {int(x) for x in ato_ids}
    return [a for a in base if int(a["id"]) in ids]


def _caminhos_uteis_de_anexos(anexos: Sequence[dict]) -> list[Path]:
    caminhos: list[Path] = []
    vistos: set[str] = set()
    for a in anexos or []:
        caminho = Path(str(a.get("stored_path") or ""))
        if not caminho.is_file():
            continue
        ext = caminho.suffix.lower()
        if ext not in EXTENSOES_IMAGEM and ext not in EXTENSOES_PDF:
            continue
        chave = str(caminho.resolve())
        if chave in vistos:
            continue
        vistos.add(chave)
        caminhos.append(caminho)
    return caminhos


def imagens_dos_atos(
    atos_escolhidos: Sequence[dict],
    *,
    anexos_por_ato: dict[int, Sequence[dict]],
    anexos_registro: Sequence[dict],
    anexo_ids_override: Sequence[int] | None = None,
) -> list[Path]:
    """Atos mandam na inclusão. Preferir RG_ATO; fallback mapeado; senão anexos.

    - Para cada ato (na ordem): usa attachments entity_type RG_ATO.
    - Se faltar RG_ATO, tenta FALLBACK_ATO_PARA_ANEXO (Santa Isabel).
    - Se NENHUM ato tiver RG_ATO nem fallback útil, cai nos anexo_id do
      formulário (ou nos anexos-padrão do registro).
    """
    caminhos: list[Path] = []
    usou_vinculo = False
    reg_por_id = {int(a["id"]): a for a in (anexos_registro or [])}

    for ato in atos_escolhidos or []:
        aid = int(ato["id"])
        atts = list(anexos_por_ato.get(aid) or [])
        imgs = _caminhos_uteis_de_anexos(atts)
        if imgs:
            usou_vinculo = True
            caminhos.extend(imgs)
            continue
        fid = FALLBACK_ATO_PARA_ANEXO.get(aid)
        if fid and fid in reg_por_id:
            imgs = _caminhos_uteis_de_anexos([reg_por_id[fid]])
            if imgs:
                usou_vinculo = True
                caminhos.extend(imgs)

    if caminhos:
        return caminhos

    # Sem vínculos RG_ATO / fallback: anexos do formulário (comportamento antigo).
    if anexo_ids_override:
        ids = {int(x) for x in anexo_ids_override}
        escolhidos = [a for a in (anexos_registro or []) if int(a["id"]) in ids]
    else:
        escolhidos = [
            a for a in (anexos_registro or [])
            if anexo_padrao_marcado(a.get("original_name"), a.get("description"))
        ] or list(anexos_registro or [])
    return _caminhos_uteis_de_anexos(escolhidos)


# -------------------------------------------------------------- API pública

def gerar_pdf(
    *,
    numero,
    imagens: Sequence[str | Path | Image.Image],
    lavrante_nome: str,
    lavrante_funcao: str,
    denominacao: str = "",
    natureza: str = "",
    objeto_certificado: str = "",
    identificacao_curta: str = "",
    identificacao_data: str | date | None = None,
    data_registro: str | date | None = None,
    protocolo: str = "",
    data_apresentacao: str | date | None = None,
    cns: str = "",
    unit_short: str = "",
    oficial: str = "",
    endereco: str = "",
    telefone: str = "",
    email: str = "",
    cidade: str = "",
    uf: str = "MA",
    serie: str | None = None,
    atribuicao: str | int | None = None,
    volume: str | None = None,
    dia: date | None = None,
    certidao_numero: str = "",
    certidao_ano: str = "",
    emolumentos: dict | None = None,
    com_emolumentos: bool = True,
    selo: dict[str, Any] | None = None,
    con: sqlite3.Connection | None = None,
) -> bytes:
    """Monta o PDF da certidão (capa + folhas). Não grava nada."""
    folhas: list[Image.Image] = []
    caminhos: list[str | Path] = []
    for item in imagens:
        if isinstance(item, Image.Image):
            folhas.append(item.convert("RGB"))
        else:
            caminhos.append(item)
    if caminhos:
        folhas.extend(carregar_folhas(caminhos))
    if not folhas:
        raise CertidaoPdfError(
            "Anexe ao menos uma imagem ou PDF do documento para a certidão.")

    textos = textos_prontos(
        numero=numero, lavrante_nome=lavrante_nome,
        lavrante_funcao=lavrante_funcao, denominacao=denominacao,
        natureza=natureza, objeto_certificado=objeto_certificado,
        identificacao_curta=identificacao_curta,
        identificacao_data=identificacao_data,
        data_registro=data_registro, protocolo=protocolo,
        data_apresentacao=data_apresentacao, paginas=len(folhas),
        cns=cns, unit_short=unit_short, oficial=oficial, endereco=endereco,
        telefone=telefone, email=email, cidade=cidade, uf=uf, serie=serie,
        atribuicao=atribuicao, volume=volume, dia=dia,
        certidao_numero=certidao_numero, certidao_ano=certidao_ano,
        total_paginas=len(folhas), con=con)

    # Telefones de SP não podem vazar no PDF.
    junto = "\n".join([
        textos["cabecalho"], textos["titulo"], textos["corpo"],
        textos["denominacao"], textos["fecho"], textos["faixa"],
    ]).lower()
    for proibido in ("3107-0111", "3777-8680", "8rtd", "cdtsp", "tjsp.jus"):
        if proibido in junto:
            raise CertidaoPdfError(
                "O modelo da certidão ainda cita branding/telefone de SP — "
                "ajuste o texto em Modelos da casa.")

    n = len(folhas)
    capa, colou_primeira = montar_capa(
        textos, emolumentos=emolumentos, com_emolumentos=com_emolumentos,
        primeira_folha=folhas[0], selo=selo)
    pages = [capa]
    # Se a 1ª folha já entrou na capa, as internas começam da 2ª — mas o
    # NÚMERO da página impressa na faixa continua sendo o da folha real do
    # documento (a 2ª folha do papel é "página 2/N", nunca "1/N-1").
    restantes = folhas[1:] if colou_primeira else folhas
    deslocamento = 1 if colou_primeira else 0
    for i, src in enumerate(restantes):
        pages.append(montar_folha_interna(
            src, textos=textos, pagina=i + 1 + deslocamento, total_paginas=n,
            emolumentos=emolumentos, com_emolumentos=com_emolumentos))
    return TEOR._images_to_pdf_bytes(pages)
