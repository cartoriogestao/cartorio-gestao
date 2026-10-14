"""Certidão de inteiro teor do RCPN - texto corrido ou cópia reprográfica.

O RESUMO (modelo CNJ em quadro) continua em `rc_certidao` / `rc_certidao_odt` /
`rc_certidao_quadro`. Este módulo é o outro papel: a certidão que **reproduz o
assento** - ou colando o teor entre aspas, ou colocando a imagem do livro.

NÃO SE INVENTA O TEOR DO REGISTRO. Os 244 assentos do acervo vieram sem texto
de livro; o que o balcão cola ou fotografa é o que está no papel. A prévia
mostra o que sairia **sem gravar**.

CABEÇALHO (pedido do oficial, 08/09/2026; ajuste papel de segurança): o
brasão da República **já vem impresso** na folha — **não** se desenha
`brasao.jpg` / `@@BRASAO@@`. Ficam ~5 linhas em branco no topo para não
bater nesse brasão; depois o bloco da serventia (unit_name + CNPJ/CNS/
telefone + endereço), no padrão Notas sem a imagem.

SELO: etiqueta completa com QR — o mesmo `ri_odt.bloco_selo_odf` das Notas e
dos demais atos (texto TJMA + QR para selo.tjma.jus.br).

ASSINATURA: nome completo de quem emitiu (`emitida_por` / usuário logado).
Sem linha de rubrica nem rótulo «Assinatura». Fecha com «Era o que cabia
certificar.» + nome + selo etiqueta (nada após o selo).

SELO DE ATO: `ato_selado.CODIGO_DA_CERTIDAO_INTEIRO_TEOR` (`14.5.6`), já medido.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from ri_odt import (
    bloco_selo_odf,
    carimbo_da_certidao_odf,
    carimbo_do_selo_odf,
    gerar_odt,
    html_para_odf,
)

# ------------------------------------------------------------ modalidades

RESUMO = "RESUMO"
INTEIRO_TEXTO = "INTEIRO_TEXTO"
INTEIRO_REPRO = "INTEIRO_REPRO"

MODALIDADES = frozenset({RESUMO, INTEIRO_TEXTO, INTEIRO_REPRO})
INTEIRO = frozenset({INTEIRO_TEXTO, INTEIRO_REPRO})

# Layout padrão da imagem na área imprimível (folha A4 útil ~17 cm).
LARGURA_CM_PADRAO = 16.0
MARGEM_ESQ_CM_PADRAO = 0.5
MARGEM_SUP_CM_PADRAO = 0.3

TITULOS: dict[str, str] = {
    "NASCIMENTO": "CERTIDÃO DE INTEIRO TEOR DE NASCIMENTO",
    "CASAMENTO": "CERTIDÃO DE INTEIRO TEOR DE CASAMENTO",
    "CASAMENTO_RELIGIOSO": "CERTIDÃO DE INTEIRO TEOR DE CASAMENTO",
    "OBITO": "CERTIDÃO DE INTEIRO TEOR DE ÓBITO",
    "NATIMORTO": "CERTIDÃO DE INTEIRO TEOR DE NATIMORTO",
    "OUTRO": "CERTIDÃO DE INTEIRO TEOR",
}

NOME_DA_ESPECIE: dict[str, str] = {
    "NASCIMENTO": "nascimento",
    "CASAMENTO": "casamento",
    "CASAMENTO_RELIGIOSO": "casamento religioso",
    "OBITO": "óbito",
    "NATIMORTO": "natimorto",
}

_BRASAO = Path(__file__).resolve().parent / "static" / "brasao.jpg"


class InteiroTeorError(ValueError):
    """Impedimento de regra, com mensagem pronta para o balcão."""


def normalizar_modalidade(valor: Any) -> str:
    """Aceita o que a ficha manda; o desconhecido vira RESUMO. Só calcula."""
    bruto = str(valor or "").strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "RESUMO": RESUMO,
        "CNJ": RESUMO,
        "QUADRO": RESUMO,
        "INTEIRO": INTEIRO_TEXTO,
        "INTEIRO_TEOR": INTEIRO_TEXTO,
        "INTEIRO_TEXTO": INTEIRO_TEXTO,
        "TEXTO": INTEIRO_TEXTO,
        "TEXTO_CORRIDO": INTEIRO_TEXTO,
        "INTEIRO_REPRO": INTEIRO_REPRO,
        "INTEIRO_REPROGRAFICA": INTEIRO_REPRO,
        "REPRO": INTEIRO_REPRO,
        "REPROGRAFICA": INTEIRO_REPRO,
        "REPROGRÁFICA": INTEIRO_REPRO,
        "IMAGEM": INTEIRO_REPRO,
        "FOTO": INTEIRO_REPRO,
    }
    return aliases.get(bruto, RESUMO)


def e_inteiro_teor(modalidade: Any) -> bool:
    return normalizar_modalidade(modalidade) in INTEIRO


def titulo(especie: Any) -> str:
    return TITULOS.get(str(especie or "").strip().upper(), TITULOS["OUTRO"])


def _especie_por_extenso(especie: Any) -> str:
    return NOME_DA_ESPECIE.get(
        str(especie or "").strip().upper(), "registro civil")


def _limpo(v: Any) -> str:
    return " ".join(str(v or "").split()).strip()


def introducao(*, especie: Any, nome: Any, matricula: Any = None,
               livro: Any = None, folha: Any = None, termo: Any = None,
               cns: Any = None, cidade: Any = None, uf: Any = None,
               modo: str = INTEIRO_TEXTO) -> str:
    """A introdução padrão da certidão de inteiro teor. Só calcula."""
    esp = str(especie or "").strip().upper()
    cabeca = titulo(esp)
    onde_partes = []
    if _limpo(livro):
        onde_partes.append(f"livro {_limpo(livro)}")
    if _limpo(folha):
        onde_partes.append(f"folha {_limpo(folha)}")
    if _limpo(termo):
        onde_partes.append(f"termo {_limpo(termo)}")
    onde = (", ".join(onde_partes) + ", ") if onde_partes else ""
    mat = f", matrícula {_limpo(matricula)}" if _limpo(matricula) else ""
    cns_txt = f" — CNS {_limpo(cns)}" if _limpo(cns) else ""
    lugar = ""
    if _limpo(cidade) and _limpo(uf):
        lugar = f" de {_limpo(cidade)}/{_limpo(uf)}"
    elif _limpo(cidade):
        lugar = f" de {_limpo(cidade)}"

    if normalizar_modalidade(modo) == INTEIRO_REPRO:
        corpo = (
            f"CERTIFICO E DOU FÉ que, a pedido de parte interessada, revendo "
            f"os livros próprios desta Serventia Extrajudicial do Ofício Único"
            f"{lugar}{cns_txt}, encontrei o assento de "
            f"{_especie_por_extenso(esp)} de {_limpo(nome) or '—'}{mat}, "
            f"{onde}e passo a reproduzir, por cópia reprográfica, o teor "
            f"constante do livro de papel, na imagem abaixo."
        )
    else:
        corpo = (
            f"CERTIFICO E DOU FÉ que, a pedido de parte interessada, revendo "
            f"os livros próprios desta Serventia Extrajudicial do Ofício Único"
            f"{lugar}{cns_txt}, encontrei o assento de "
            f"{_especie_por_extenso(esp)} de {_limpo(nome) or '—'}{mat}, "
            f"{onde}COM O SEGUINTE TEOR:"
        )
    return f"{cabeca}\n\n{corpo}"


def entre_aspas(teor_colado: Any) -> str:
    """O teor do livro entre aspas angulares — o oficial cola, a casa não inventa."""
    texto = str(teor_colado or "").strip()
    if not texto:
        raise InteiroTeorError(
            "Cole o teor completo do assento entre as aspas. A certidão de "
            "inteiro teor em texto corrido reproduz o que está no livro de "
            "papel — este sistema não inventa esse texto a partir dos campos "
            "(os assentos do acervo vieram sem ele)."
        )
    if ((texto.startswith("«") and texto.endswith("»"))
            or (texto.startswith('"') and texto.endswith('"'))
            or (texto.startswith("'") and texto.endswith("'"))):
        texto = texto[1:-1].strip()
    # Texto corrido: aspas coladas ao teor, sem linhas em branco.
    # Ponto final dentro do teor se faltar (pedido do oficial).
    if texto and texto[-1] not in ".!?…":
        texto = texto + "."
    return f"«{texto}»"


def _campo_ato(ato: Any, chave: str) -> Any:
    """Lê campo de dict ou sqlite3.Row sem impor tipo."""
    if ato is None:
        return None
    if isinstance(ato, dict):
        return ato.get(chave)
    try:
        return ato[chave]
    except (KeyError, IndexError, TypeError):
        return None


def _norm_para_conter(texto: Any) -> str:
    """Normaliza espaços para checar se um teor de ato já está no colado."""
    t = re.sub(r"\s+", " ", str(texto or "")).strip().casefold()
    return t


def ato_teor_ja_contido(teor_colado: Any, ato: Any) -> bool:
    """True se o colado já traz este ato (selo ou núcleo do teor)."""
    base = _norm_para_conter(teor_colado)
    if not base:
        return False
    selo = str(_campo_ato(ato, "selo") or "").strip()
    if selo and selo.casefold() in base:
        return True
    teor = str(_campo_ato(ato, "teor") or "").strip()
    if not teor:
        return True
    trecho = _norm_para_conter(teor)
    if trecho and trecho in base:
        return True
    # Núcleo: primeira sentença / primeiros ~80 chars — evita falso negativo
    # quando o colado tem o texto sem o selo/fecho que rc_atos acrescentou.
    nucleo = trecho.split(". ")[0].strip()
    if len(nucleo) >= 30 and nucleo in base:
        return True
    curto = trecho[:80].rstrip(" .")
    if len(curto) >= 30 and curto in base:
        return True
    return False


# Separador visual entre o livro colado e as averbações que o sistema acresce
# (mesmo estilo de traço longo que o balcão usa no inteiro teor).
SEPARADOR_ATOS_INTEIRO = (
    "\n"
    + ("-" * 170)
    + "\n"
)

TIPOS_ATOS_INTEIRO = frozenset({"AVERBACAO", "ANOTACAO", "RETIFICACAO"})


def completar_teor_colado_com_atos(teor_colado: Any,
                                   atos: list | None = None) -> str:
    """Acrescenta ao colado averbações/anotações/retificações que faltam.

    O balcão cola o teor do livro; o sistema **não inventa** o assento. Mas o
    que já está em `rc_atos` e ainda não aparece no colado precisa entrar —
    senão a certidão de inteiro teor omite CPF, casamento etc. lavrados na
    ficha. Só calcula; quem grava é `rc_certidao.emitir`.
    """
    texto = str(teor_colado or "").strip()
    faltando: list[str] = []
    for ato in atos or []:
        tipo = str(_campo_ato(ato, "tipo") or "").strip().upper()
        if tipo not in TIPOS_ATOS_INTEIRO:
            continue
        teor = str(_campo_ato(ato, "teor") or "").strip()
        if not teor:
            continue
        if ato_teor_ja_contido(texto, ato):
            continue
        faltando.append(teor)
    if not faltando:
        return texto
    bloco = SEPARADOR_ATOS_INTEIRO.join(faltando)
    if not texto:
        return bloco
    return texto.rstrip() + SEPARADOR_ATOS_INTEIRO + bloco


def montar_teor_texto(*, introducao_txt: str, teor_colado: Any,
                      atos: list | None = None) -> str:
    """Introdução + teor colado entre aspas (com atos faltantes). Só calcula."""
    colado = completar_teor_colado_com_atos(teor_colado, atos)
    return f"{introducao_txt.rstrip()}\n{entre_aspas(colado)}"


def montar_teor_repro(*, introducao_txt: str) -> str:
    """O teor congelado da via reprográfica (a imagem mora à parte)."""
    return (
        f"{introducao_txt.rstrip()}\n\n"
        f"[Cópia reprográfica do assento anexa a esta certidão.]"
    )


def escapar_xml(texto: Any) -> str:
    """Escapa o que vai para content.xml do ODT — &, <, >, aspas."""
    return escape(str(texto or ""), entities={'"': "&quot;", "'": "&apos;"})


def _ponto_no_teor_aspas(texto: str) -> str:
    """Garante ponto final dentro de «…» se o teor congelado ainda não tiver."""
    def _fix(m: re.Match) -> str:
        corpo = m.group(1).rstrip()
        if corpo and corpo[-1] not in ".!?…":
            corpo = corpo + "."
        return f"«{corpo}»"
    return re.sub(r"«(.*?)»", _fix, str(texto or ""), flags=re.DOTALL)


def _paragrafos_html(texto: str) -> str:
    """Parágrafos do teor: título da certidão centrado/negrito; resto corrido."""
    bruto = _ponto_no_teor_aspas(str(texto or "")).strip()
    if not bruto:
        return "<p></p>"
    linhas = bruto.split("\n")
    saida: list[str] = []
    resto_linhas = linhas
    primeira = linhas[0].strip()
    if primeira.upper().startswith("CERTIDÃO DE INTEIRO TEOR") or \
            primeira.upper().startswith("CERTIDAO DE INTEIRO TEOR"):
        saida.append(
            f'<p align="center"><b>{escape(primeira)}</b></p>')
        i = 1
        while i < len(linhas) and not linhas[i].strip():
            i += 1
        resto_linhas = linhas[i:]
    # Colapsa linhas em branco extras → texto corrido (sem <p> vazios).
    corpo = "\n".join(resto_linhas).strip()
    corpo = re.sub(r"\n{2,}", "\n", corpo)
    # Aspas do teor coladas ao fluxo (sem quebra antes/depois).
    corpo = re.sub(r"\n*«\n*", "«", corpo)
    corpo = re.sub(r"\n*»\n*", "»", corpo)
    if corpo:
        partes = [escape(L) for L in corpo.split("\n")]
        saida.append("<p>" + "<br/>".join(partes) + "</p>")
    return "".join(saida) if saida else "<p></p>"


def _cabecalho_notas_html(sv: dict, certidao: dict) -> str:
    """Bloco de identificação no padrão Notas, **sem** brasão digital.

    O papel de segurança já traz o brasão da República no topo. Por isso
    não entra `@@BRASAO@@` / `brasao.jpg`. Em vez disso, ~5 linhas em branco
    no início para o texto não bater nesse brasão impresso.
    Sem tabela LIVRO/FOLHA/TERMO no topo (pedido do oficial).
    """
    s = sv or {}
    unidade = escape(str(s.get("unit_name") or ""))
    titulo_sv = escape(str(s.get("serventia_titulo") or "Oficial"))
    titular = escape(str(s.get("serventia_titular") or ""))
    cnpj = escape(str(s.get("serventia_cnpj") or ""))
    cns = escape(str(s.get("ri_cns") or ""))
    fone = escape(str(s.get("serventia_telefone") or ""))
    end = escape(str(s.get("endereco_completo") or ""))
    # Cinco linhas em branco = folga sob o brasão da folha de segurança.
    folga = "".join("<p><br/></p>" for _ in range(5))
    return (
        f"{folga}"
        f'<p align="center"><b>{unidade}</b></p>'
        f'<p align="center">{titulo_sv}: {titular}</p>'
        f'<p align="center">CNPJ {cnpj} — CNS {cns} — Telefone {fone}</p>'
        f'<p align="center">{end}</p>'
    )


def _brasao_odf() -> tuple[str, dict[str, tuple[bytes, str]]]:
    """Frame ODF do brasão centrado + mapa de imagens (padrão Notas).

    Usa `P-centro` (não `ESTILO_PAGINA_1`): esse estilo só é declarado em
    `gerar_odt` quando `cabecalho_a_partir_da_pagina_2=True`. Sem a declaração
    o LibreOffice cai no Standard e o brasão sai à esquerda.
    """
    imagens: dict[str, tuple[bytes, str]] = {}
    if not _BRASAO.is_file():
        return "", imagens
    imagens["brasao.jpg"] = (_BRASAO.read_bytes(), "image/jpeg")
    odf = (
        '<text:p text:style-name="P-centro">'
        '<draw:frame draw:style-name="Fr-qr" text:anchor-type="as-char" '
        'svg:width="2.5cm" svg:height="2.5cm">'
        '<draw:image xlink:href="Pictures/brasao.jpg" '
        'xlink:type="simple" xlink:show="embed" '
        'xlink:actuate="onLoad"/></draw:frame></text:p>'
    )
    return odf, imagens


_SELO_CODIGO_RE = re.compile(
    r"(?<![A-Z0-9])([A-Z]{5,7}\d{6}[A-Z0-9]{10,25})\b"
)


def _codigo_do_selo(selo: str | None, texto: str | None = None) -> str:
    """Número curto do selo (28 chars). Extrai da etiqueta se vier o texto TJMA."""
    for bruto in (selo, texto):
        s = _limpo(bruto)
        if not s:
            continue
        # Já é só o código.
        if re.fullmatch(r"[A-Z]{5,7}\d{6}[A-Z0-9]{10,25}", s):
            return s
        m = _SELO_CODIGO_RE.search(s)
        if m:
            return m.group(1)
    return _limpo(selo) or ""


def _png_do_qr(selo: str) -> bytes | None:
    """PNG do QR do selo — mesma regra de Notas / `rc_certidao_odt._png_do_qr`.

    **O QR LEVA O ENDEREÇO DA CONSULTA DAQUELE SELO** — `#/resumo/<número>`,
    medido no portal em 24/09/2026. O `qr_token` do aparelho **saiu do
    caminho**: ele não é link (24 caracteres, sem `http`), e o portal procura
    pelo número. Ver `notas_selo`.
    """
    codigo = _codigo_do_selo(selo)
    if not codigo:
        return None
    try:
        import segno
        import notas_selo as NSELO
    except ImportError:
        return None
    texto = NSELO.conteudo(NSELO.MODELO_PADRAO, codigo)
    if not texto:
        return None
    try:
        qr = segno.make(texto, error="m")
        buf = io.BytesIO()
        # scale=8 + border=1: QR legível na prévia PDF (antes sumia se png=None).
        qr.save(buf, kind="png", scale=8, border=1)
        return buf.getvalue() or None
    except Exception:
        return None


def _selo_odf_e_imagens(certidao: dict) -> tuple[str, dict[str, tuple[bytes, str]]]:
    """Etiqueta completa do selo com QR (`bloco_selo_odf`), como nas Notas."""
    imagens: dict[str, tuple[bytes, str]] = {}
    texto = _limpo(certidao.get("selo_texto"))
    numero = _codigo_do_selo(certidao.get("selo"), texto)
    if not texto and numero:
        texto = numero
    if not texto:
        return "", imagens
    # O CARIMBO E O MESMO DAS OUTRAS ATRIBUICOES — ordem do oficial em
    # 15/09/2026. Numero, ato e data, linha de valores e QR, cada coisa na sua
    # linha; e nao a frase corrida de trezentos caracteres do aparelho.
    #
    # **E DESDE 17/09 ELE E O CARIMBO DA CERTIDAO**: largura inteira,
    # requerente, data e hora por extenso, as marcas do selo e o link da
    # consulta — `#/resumo/<selo>` desde 24/09/2026, porque `?selo=` abre a
    # tela de digitar, vazia. A montagem mora em
    # `ri_odt.carimbo_da_certidao_odf`, e serve as quatro certidoes da casa.
    #
    #   **E O `qr_token` SAIU DO CAMINHO EM 24/09/2026.** Até aqui, quando
    #   ele existisse, o QR seria o do token — e token cru não é link: a
    #   câmera lê vinte e quatro caracteres e não tem o que abrir. Medido no
    #   portal, quem abre a consulta é o NÚMERO.
    return carimbo_da_certidao_odf(texto, prefixo="qr_selo")


def _assinante(certidao: dict, sv: dict) -> tuple[str, str]:
    """Quem assina a via: emitente logado; fallback no titular da serventia."""
    s = sv or {}
    nome = _limpo(certidao.get("emitida_por")) or _limpo(
        s.get("serventia_titular"))
    funcao = (
        _limpo(certidao.get("emitida_funcao"))
        or _limpo(certidao.get("emitida_titulo"))
        or _limpo(s.get("serventia_titulo"))
        or "Escrevente"
    )
    return nome, funcao


def _rodape_html(certidao: dict, sv: dict, hoje_extenso: str) -> str:
    """Fecha a certidão: data + nome completo + selo.

    A frase «Era o que cabia certificar.» entra no fim do parágrafo do teor
    (`html_da_certidao_*`) — texto corrido, sem linha em branco após «…teor.».
    Ordem: teor+fecho → data → nome → selo etiqueta. Nada após o selo.
    Sem linha de rubrica nem rótulo «Assinatura».
    """
    s = sv or {}
    cidade = escape(str(s.get("ri_cidade") or ""))
    uf = escape(str(s.get("ri_uf") or ""))
    nome, funcao = _assinante(certidao, sv)
    return (
        f"<p>{cidade}-{uf}, {escape(hoje_extenso)}.</p>"
        "<p><br/></p>"
        f'<p align="center"><b>{escape(nome)}</b></p>'
        f'<p align="center">{escape(funcao)}</p>'
        "<p>@@SELO@@</p>"
    )


def _com_fecho_certificar(teor_html: str) -> str:
    """Cola «Era o que cabia certificar.» no fim do último <p> do teor."""
    fecho = " Era o que cabia certificar."
    html = str(teor_html or "")
    if not html:
        return f"<p>{escape(fecho.strip())}</p>"
    # Último </p> do teor — mesmo parágrafo, sem linha em branco.
    idx = html.rfind("</p>")
    if idx < 0:
        return html + f"<p>{escape(fecho.strip())}</p>"
    return html[:idx] + escape(fecho) + html[idx:]


def html_da_certidao_texto(certidao: dict, sv: dict, *,
                            hoje_extenso: str) -> str:
    """HTML da via em texto corrido — cabeçalho Notas + teor + selo/QR + emitente."""
    cancelada = ""
    if certidao.get("cancelada_em"):
        motivo = escape(str(certidao.get("cancelada_motivo") or ""))
        cancelada = (
            f'<p align="center"><b>CERTIDÃO CANCELADA — {motivo}</b></p>'
        )
    teor = str(certidao.get("teor") or "")
    return (
        f"{_cabecalho_notas_html(sv, certidao)}"
        f"{_com_fecho_certificar(_paragrafos_html(teor))}"
        f"{cancelada}"
        f"{_rodape_html(certidao, sv, hoje_extenso)}"
    )


def frame_da_imagem(*, nome_arquivo: str, largura_cm: float,
                    altura_cm: float | None,
                    margem_esq_cm: float,
                    margem_sup_cm: float) -> str:
    """Fragmento ODF com a imagem ajustável na área imprimível."""
    w = max(1.0, float(largura_cm or LARGURA_CM_PADRAO))
    if altura_cm and float(altura_cm) > 0:
        h = float(altura_cm)
    else:
        h = round(w * 1.35, 2)
    x = max(0.0, float(margem_esq_cm if margem_esq_cm is not None
                       else MARGEM_ESQ_CM_PADRAO))
    y = max(0.0, float(margem_sup_cm if margem_sup_cm is not None
                       else MARGEM_SUP_CM_PADRAO))
    return (
        f'<draw:frame draw:style-name="Fr-qr" text:anchor-type="paragraph" '
        f'text:anchor-page-number="1" svg:x="{x}cm" svg:y="{y}cm" '
        f'svg:width="{w}cm" svg:height="{h}cm" draw:z-index="0">'
        f'<draw:image xlink:href="Pictures/{nome_arquivo}" '
        f'xlink:type="simple" xlink:show="embed" '
        f'xlink:actuate="onLoad"/></draw:frame>'
    )


def mime_da_imagem(caminho: str | Path) -> str:
    ext = Path(caminho).suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
    }.get(ext, "image/jpeg")


def html_da_certidao_repro(certidao: dict, sv: dict, *,
                            hoje_extenso: str,
                            marca_imagem: str = "##IMG_REPRO##") -> str:
    """HTML com marca onde entra o frame ODF da imagem."""
    intro = str(certidao.get("teor") or "")
    intro = re.sub(
        r"\n*\[Cópia reprográfica do assento anexa a esta certidão\.\]\s*",
        "\n\n", intro).strip()
    cancelada = ""
    if certidao.get("cancelada_em"):
        motivo = escape(str(certidao.get("cancelada_motivo") or ""))
        cancelada = (
            f'<p align="center"><b>CERTIDÃO CANCELADA — {motivo}</b></p>'
        )
    return (
        f"{_cabecalho_notas_html(sv, certidao)}"
        f"{_com_fecho_certificar(_paragrafos_html(intro))}"
        f"<p>{marca_imagem}</p>"
        f"{cancelada}"
        f"{_rodape_html(certidao, sv, hoje_extenso)}"
    )


def _ext_de_caminho(caminho: Any) -> str:
    ext = Path(str(caminho or "")).suffix.lower()
    return ext if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
                          ".tif", ".tiff"} else ".jpg"


def arquivo_odt(certidao: dict, sv: dict, *, hoje_extenso: str,
                imagem_bytes: bytes | None = None) -> bytes:
    """ODT da certidão de inteiro teor (texto ou reprográfica).

    Inclui folga + cabeçalho da serventia (sem brasão digital), «Era o que
    cabia certificar.», nome do emitente e selo+QR (`bloco_selo_odf`).
    """
    imagens: dict[str, tuple[bytes, str]] = {}
    selo_odf, imgs_selo = _selo_odf_e_imagens(certidao)
    imagens.update(imgs_selo)
    fragmentos = {"@@SELO@@": selo_odf}

    mod = normalizar_modalidade(certidao.get("modalidade"))
    if mod == INTEIRO_REPRO:
        if not imagem_bytes:
            raise InteiroTeorError(
                "Esta certidão é de cópia reprográfica e a imagem do assento "
                "não foi encontrada no disco. Anexe de novo na emissão.")
        nome_img = "repro_assento" + _ext_de_caminho(
            certidao.get("imagem_caminho") or ".jpg")
        marca = "##IMG_REPRO##"
        html = html_da_certidao_repro(certidao, sv, hoje_extenso=hoje_extenso,
                                     marca_imagem=marca)
        frame = frame_da_imagem(
            nome_arquivo=nome_img,
            largura_cm=float(certidao.get("imagem_largura_cm")
                             or LARGURA_CM_PADRAO),
            altura_cm=(float(certidao["imagem_altura_cm"])
                       if certidao.get("imagem_altura_cm") not in (None, "")
                       else None),
            margem_esq_cm=float(certidao.get("imagem_margem_esq_cm")
                                if certidao.get("imagem_margem_esq_cm")
                                is not None else MARGEM_ESQ_CM_PADRAO),
            margem_sup_cm=float(certidao.get("imagem_margem_sup_cm")
                                if certidao.get("imagem_margem_sup_cm")
                                is not None else MARGEM_SUP_CM_PADRAO),
        )
        fragmentos[marca] = frame
        corpo = html_para_odf(html, fragmentos=fragmentos)
        imagens[nome_img] = (imagem_bytes, mime_da_imagem(nome_img))
        return gerar_odt(
            corpo,
            titulo=(f"Certidão inteiro teor {certidao.get('numero')}/"
                    f"{certidao.get('ano')}"),
            imagens=imagens,
            cabecalho_odf="",
        )
    html = html_da_certidao_texto(certidao, sv, hoje_extenso=hoje_extenso)
    return gerar_odt(
        html_para_odf(html, fragmentos=fragmentos),
        titulo=(f"Certidão inteiro teor {certidao.get('numero')}/"
                f"{certidao.get('ano')}"),
        imagens=imagens,
        cabecalho_odf="",
    )


def previa_html(*, modalidade: Any, introducao_txt: str,
                teor_colado: Any = None, tem_imagem: bool = False,
                atos: list | None = None) -> str:
    """Prévia do que sairia — não grava. Não inventa teor."""
    mod = normalizar_modalidade(modalidade)
    if mod == RESUMO:
        return ("<p><em>Modalidade resumo:</em> sai o quadro CNJ habitual "
                "(molde ODT da espécie), montado dos campos do assento.</p>")
    if mod == INTEIRO_TEXTO:
        try:
            corpo = montar_teor_texto(introducao_txt=introducao_txt,
                                     teor_colado=teor_colado, atos=atos)
        except InteiroTeorError as erro:
            return f'<p class="alert danger">{escape(str(erro))}</p>'
        return (
            '<div class="teor-previa" style="white-space:pre-wrap;'
            'font-family:serif;padding:14px;border:1px solid #ccc;'
            'background:#fff">'
            f"{escape(corpo)}</div>"
            "<p><small>Prévia — nada foi gravado. Conferir no livro antes de "
            "emitir. O PDF traz cabeçalho Notas (brasão/serventia), selo com "
            "QR e assinatura de quem emitiu.</small></p>"
        )
    bloco = escape(introducao_txt)
    img = ("<p><em>[imagem do assento — posição/tamanho ajustáveis na "
           "emissão]</em></p>" if tem_imagem else
           '<p class="alert danger">Escolha ou envie a imagem do '
           "assento para a cópia reprográfica.</p>")
    return (
        f'<div class="teor-previa" style="padding:14px;border:1px solid #ccc;'
        f'background:#fff"><div style="white-space:pre-wrap;font-family:serif">'
        f"{bloco}</div>{img}</div>"
        "<p><small>Prévia — nada foi gravado.</small></p>"
    )


# Colunas novas em rc_certidoes (aplicadas por init_rc_certidao_schema).
MIGRACOES_CERTIDAO: tuple[tuple[str, str], ...] = (
    ("modalidade", "TEXT NOT NULL DEFAULT 'RESUMO'"),
    ("teor_colado", "TEXT"),
    ("imagem_caminho", "TEXT"),
    ("imagem_largura_cm", "REAL"),
    ("imagem_altura_cm", "REAL"),
    ("imagem_margem_esq_cm", "REAL"),
    ("imagem_margem_sup_cm", "REAL"),
)
