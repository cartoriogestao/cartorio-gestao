# -*- coding: utf-8 -*-
"""Helpers HTML do motor de fidelidade (Etapa 2a → 2b).

F01 (Beatriz 2026-10-05): certidões RI / Livro 3 / ficha imprimem tags HTML
literais no PDF quando o teor do acervo está guardado em HTML e passa por
escape duplo. O fix na rota RI fica para 2c (`ri_web`/`atribuicoes_web` não
são tocados aqui); o motor expõe `html_para_texto_impressao(html) -> str`
para a rota chamar quando for plugada.

2b: `strip_tags` passou a
  - aceitar HTML com **escape duplo** (`&lt;strong&gt;` → some, não vira
    `<strong>` literal no papel);
  - descartar `<script>`/`<style>` inteiros;
  - não comer `<` que não abre tag (ex.: «a < b»);
  - remover caracteres invisíveis (zero-width, NBSP) que o editor deixa.
"""
from __future__ import annotations

import html
import re
from typing import Any


# Só é tag o que começa com letra, `/` ou `!` logo após o `<` — «a < b» fica.
_TAG = re.compile(r"<(?:/?[A-Za-z][^<>]*|![^<>]*)>", re.DOTALL)
_COMENTARIO = re.compile(r"<!--.*?-->", re.DOTALL)
_SCRIPT_STYLE = re.compile(r"(?is)<(script|style)\b[^>]*>.*?</\1\s*>")
_ESPACO = re.compile(r"[ \t\f\v]+")
_QUEBRAS = re.compile(r"\n{3,}")
_INVISIVEIS = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
# entidade de tag ainda escapada depois de um unescape (escape duplo)
_TAG_ESCAPADA = re.compile(
    r"&(?:amp;)*lt;\s*(?:/?[A-Za-z]|!--)", re.IGNORECASE)


def _uma_passada(s: str) -> str:
    s = _COMENTARIO.sub(" ", s)
    s = _SCRIPT_STYLE.sub(" ", s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</(?:p|div|tr|li|h[1-6]|table|ul|ol)\s*>", "\n", s)
    s = _TAG.sub("", s)
    return s


def strip_tags(texto: Any) -> str:
    """Remove tags HTML/XML, preservando o texto visível.

    Comentários HTML somem. Entidades (`&amp;`, `&nbsp;`, …) são
    decodificadas. Escape duplo (`&lt;p&gt;` guardado no acervo) é desfeito
    em até 3 passadas, e a tag resultante também some. Não interpreta
    JavaScript nem CSS (o conteúdo de `<script>`/`<style>` é descartado).
    """
    s = str(texto or "")
    if not s:
        return ""
    s = _uma_passada(s)
    s = html.unescape(s)
    # escape duplo/triplo: depois do unescape ainda há tag (ou entidade de tag)
    for _ in range(3):
        if _TAG.search(s) or _COMENTARIO.search(s) or _TAG_ESCAPADA.search(s):
            s = _uma_passada(s)
            s = html.unescape(s)
        else:
            break
    s = s.replace("\xa0", " ")
    s = _INVISIVEIS.sub("", s)
    s = _ESPACO.sub(" ", s)
    s = "\n".join(linha.strip() for linha in s.splitlines())
    s = _QUEBRAS.sub("\n\n", s)
    return s.strip()


def html_para_texto(texto: Any) -> str:
    """Alias canônico: HTML (ou misto) → texto plano para papel/PDF.

    Use antes de embutir teor de acervo/ato em certidão ou ficha, para não
    repetir o F01 (tags literais no PDF de fé pública).
    """
    return strip_tags(texto)


def html_para_texto_impressao(html_ou_texto: Any) -> str:
    """Função pública para a emissão (RI/Livro 3/ficha/termo) — F01.

    Garante que nada com cara de marcação chegue ao papel:
      - tags reais e escapadas (uma ou mais vezes) somem;
      - parágrafos viram linhas; linhas vazias repetidas colapsam;
      - texto que já é plano volta igual (exceto espaços nas bordas).

    É idempotente: `f(f(x)) == f(x)`. A rota RI (`ri_web`/`atribuicoes_web`)
    ainda NÃO chama esta função — 2c deixou o patch de 1 linha documentado
    (`corrigir_teor_f01`), sem aplicar, porque `ri_web` está em uso.
    """
    s = str(html_ou_texto or "")
    if not s.strip():
        return ""
    if not (parece_html(s) or _TAG_ESCAPADA.search(s) or "&" in s):
        return s.strip()
    return strip_tags(s)


def tem_tag_escapada(texto: Any) -> bool:
    """True se há tag HTML escapada (`&lt;p&gt;`, `&amp;lt;p&amp;gt;`…).

    É o sintoma do F01: o teor foi escapado antes de ir ao papel e a tag
    sairia literal.
    """
    return bool(_TAG_ESCAPADA.search(str(texto or "")))


def corrigir_teor_f01(texto: Any, formato: Any = "html") -> tuple[str, str]:
    """F01 — decide como o teor vai ao papel do RI/ficha/certidão. Só calcula.

    Devolve `(texto, formato)` para a rota usar no lugar dos originais:
      - tag escapada (uma ou mais vezes) → texto plano, formato `"texto"`;
      - HTML real com formato diferente de `"html"` (seria escapado e sairia
        literal) → texto plano, formato `"texto"`;
      - HTML real com formato `"html"` ou texto plano → volta igual.
    Patch proposto (1 linha, NÃO aplicado) em
    `SANDBOX\\tmp\\motor_fidelidade_2c_f01_ri.patch`.
    """
    s = str(texto or "")
    fmt = str(formato or "").strip().lower()
    if tem_tag_escapada(s) or (fmt != "html" and parece_html(s)):
        return html_para_texto_impressao(s), "texto"
    return s, (fmt or "texto")


def parece_html(texto: Any) -> bool:
    """Heurística barata: há tags de marcação conhecidas no corpo
    (também quando vieram escapadas uma vez: `&lt;p&gt;`)."""
    s = str(texto or "")
    if "&lt;" in s.lower():
        s = html.unescape(s)
    if "<" not in s or ">" not in s:
        return False
    return bool(re.search(
        r"(?i)</?(?:p|div|span|br|strong|b|em|i|u|table|tr|td|th|ul|ol|li|"
        r"h[1-6]|font|center)\b",
        s,
    ))


def escapar(texto: Any) -> str:
    return html.escape(str(texto or ""), quote=True)
