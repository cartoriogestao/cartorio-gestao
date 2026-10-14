# -*- coding: utf-8 -*-
"""Contagem de folhas da certidão ANTES de emitir / selar.

Pedido 22/09/2026: o sistema contabiliza sozinho quantas folhas a certidão
terá, em vez de depender do campo digitado (padrão 1), que selava errado
quando a via tinha mais páginas.

- Reprodução da digitalização: páginas do arquivo.
- Certidão por texto: PDF do teor (Chrome/LibreOffice) e conta páginas;
  se o conversor falhar, estima pelo tamanho do teor (piso 1).
"""
from __future__ import annotations

import re
from pathlib import Path

CHARS_POR_FOLHA_TEXTO = 3200


def _texto_plano(html_ou_texto: str | None) -> str:
    t = str(html_ou_texto or "")
    t = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", t)
    t = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def contar_paginas_pdf(pdf: bytes | None) -> int:
    if not pdf:
        return 1
    n = len(re.findall(rb"/Type\s*/Page\b(?![sS])", pdf))
    return max(1, n)


def folhas_por_estimativa_de_texto(html_ou_texto: str | None) -> int:
    plain = _texto_plano(html_ou_texto)
    if not plain:
        return 1
    return max(1, (len(plain) + CHARS_POR_FOLHA_TEXTO - 1) // CHARS_POR_FOLHA_TEXTO)


def folhas_da_digitalizacao(caminho: str | Path | None = None,
                            *, paginas_ja: int | None = None) -> int:
    if paginas_ja is not None:
        try:
            return max(1, int(paginas_ja))
        except (TypeError, ValueError):
            pass
    p = Path(caminho) if caminho else None
    if not p or not p.is_file():
        return 1
    try:
        import ri_digitalizacao as RDIGI  # type: ignore
        return max(1, len(RDIGI.paginas_png(p)))
    except Exception:
        return 1


def _pdf_do_html(html: str, *, get_setting=None) -> bytes | None:
    try:
        import impressao_pdf as IP  # type: ignore
    except Exception:
        return None
    # 1) Chrome/Edge — fiel ao HTML e em geral mais rápido no balcão.
    try:
        if hasattr(IP, "pdf_de_html_chrome"):
            return IP.pdf_de_html_chrome(html, nome="previa-certidao",
                                         get_setting=get_setting)
    except Exception:
        pass
    # 2) LibreOffice via ODT mínimo.
    try:
        from ri_odt import (  # type: ignore
            html_para_odf, gerar_odt, cabecalho_certidao_compacto_odf,
        )
        cab_odf, _imgs = cabecalho_certidao_compacto_odf(None)
        odt = gerar_odt(html_para_odf(html or ""), titulo="Certidão",
                        cabecalho_odf=cab_odf or "")
        return IP.pdf_de_odt(odt, nome="previa-certidao",
                             get_setting=get_setting)
    except Exception:
        return None


def folhas_do_html_como_certidao(html: str | None, *,
                                 get_setting=None) -> int:
    plain_est = folhas_por_estimativa_de_texto(html)
    pdf = _pdf_do_html(html or "", get_setting=get_setting)
    if pdf:
        n = contar_paginas_pdf(pdf)
        if n <= 1 and plain_est > 1:
            return plain_est
        return n
    return plain_est


def decidir_folhas_antes_de_emitir(
    *,
    fonte: str,
    caminho_digi: str | Path | None = None,
    paginas_digi: int | None = None,
    corpo_html: str | None = None,
    folhas_informadas: int | None = None,
    get_setting=None,
) -> int:
    """Folhas para o selo na emissão.

    Digitalização → páginas do arquivo.
    Texto → contagem pelo papel (PDF) / estimativa.
    Se o balcão informar um número MAIOR que o calculado, respeita
    (capa/anexo). Número menor que o calculado é ignorado — era o
    defeito do campo nascendo em 1.
    """
    fonte_u = (fonte or "").strip().upper()
    if fonte_u in ("DIGITALIZACAO", "DIGITALIZAÇÃO", "REPRO", "REPRODUCAO"):
        calc = folhas_da_digitalizacao(caminho_digi, paginas_ja=paginas_digi)
    else:
        calc = folhas_do_html_como_certidao(corpo_html, get_setting=get_setting)

    try:
        informada = int(folhas_informadas) if folhas_informadas is not None else None
    except (TypeError, ValueError):
        informada = None
    if informada is not None and informada > calc:
        return informada
    return max(1, calc)
