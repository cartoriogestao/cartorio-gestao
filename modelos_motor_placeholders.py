# -*- coding: utf-8 -*-
"""Placeholders `{{campo}}` e trechos bloqueados — Etapa 2c (SANDBOX).

INGESTÃO DE RASCUNHO (prévia com `conteudo` não salvo):

  - O formato canônico do motor/editor é `{{campo}}` (contrato aprovado).
  - Na VALIDAÇÃO, `@campo` (marcador dos moldes ODT) e `{campo}` (formato
    `str.format` do catálogo `rc_modelos_do_livro`) são aceitos e convertidos
    para `{{campo}}`. A lista de conversões volta na resposta.
  - Para MONTAR o termo, o texto canônico é convertido de volta para o
    formato do catálogo (`{campo}`), porque `rc_modelos_do_livro.conferir_corpo`
    recusa `{{` (formato Jinja antigo). Nada é gravado.

TRECHOS BLOQUEADOS — marcador `{{#bloqueado id}}…{{/bloqueado}}` (o mesmo
`RE_BLOQUEADO` do editor):

  - `marcar_bloqueados(area, template_id, conteudo)` envolve os trechos
    normativos conhecidos SEM mudar um byte do texto: tirar os marcadores
    (`remover_marcadores_bloqueados`) devolve exatamente a entrada.
  - Na emissão/prévia os marcadores nunca aparecem — saem antes de montar.

Sem dado de serventia aqui: só nomes de campos.
"""
from __future__ import annotations

import base64
import binascii
import re
from typing import Any

# Mesmas expressões do editor (`modelos_editor.RE_*`) — copiadas, não
# importadas, para o motor não depender do editor para validar.
# Sem `\s*` dos dois lados desde 28/10/2026 (CodeQL py/polynomial-redos): a
# forma antiga era cúbica num `{{` sem fecho seguido de brancos. Casa os
# mesmos trechos; o grupo traz os brancos das pontas, e os três leitores
# daqui fazem `.strip()`. A razão inteira está em `modelos_editor`.
RE_DUPLO = re.compile(r"\{\{(?=[^{}#/])([^{}]*)\}\}")
RE_SIMPLES = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_.]*)\}(?!\})")
# `@campo` só quando o @ não está colado em palavra/ponto (e-mail fica).
RE_ARROBA = re.compile(r"(?<![\w.@])@([A-Za-z_][A-Za-z0-9_]*)")
RE_BLOQUEADO = re.compile(
    r"\{\{#bloqueado\s+([A-Za-z0-9_\-]+)\}\}(.*?)\{\{/bloqueado\}\}",
    re.DOTALL,
)
RE_MARCADOR_BLOQUEADO = re.compile(
    r"\{\{#bloqueado\s+[A-Za-z0-9_\-]+\}\}|\{\{/bloqueado\}\}")

MIME_ODT = "application/vnd.oasis.opendocument.text"


# ------------------------------------------------------------ conteúdo cru

def eh_molde(template_id: str) -> bool:
    return str(template_id or "").upper().startswith("RC_MOLDE_")


def conteudo_de_partes(conteudo: Any, *, parte: str = "CORPO") -> Any:
    """O editor pode mandar `{"CORPO": ..., "ENCERRAMENTO": ...}`.

    Para termo vale a parte pedida (CORPO por padrão); para molde, `MOLDE`.
    String/bytes passam direto.
    """
    if not isinstance(conteudo, dict):
        return conteudo
    chaves = {str(k).upper(): v for k, v in conteudo.items()}
    for k in (parte.upper(), "MOLDE", "CORPO", "CONTEUDO"):
        v = chaves.get(k)
        if isinstance(v, (str, bytes)) and str(v).strip():
            return v
    partes = [v for v in chaves.values() if isinstance(v, str) and v.strip()]
    return "\n\n".join(partes) if partes else None


def odt_do_conteudo(conteudo: Any) -> bytes:
    """`conteudo` de molde → bytes do ODT (aceita base64, data-URL ou bytes).

    Levanta ValueError com mensagem pronta quando não é um .odt.
    """
    import io
    import zipfile
    if isinstance(conteudo, (bytes, bytearray)):
        bruto = bytes(conteudo)
    else:
        s = str(conteudo or "").strip()
        if s.startswith("data:") and "," in s:
            s = s.split(",", 1)[1]
        try:
            bruto = base64.b64decode(s, validate=False)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"conteudo do molde não é base64 válido: {exc}") from exc
    try:
        with zipfile.ZipFile(io.BytesIO(bruto)) as z:
            if "content.xml" not in z.namelist():
                raise ValueError("conteudo do molde sem content.xml — não é .odt")
    except zipfile.BadZipFile as exc:
        raise ValueError("conteudo do molde não é um .odt (zip inválido)") from exc
    return bruto


def texto_do_odt(odt: bytes) -> str:
    """Texto visível do content.xml (para listar placeholders do molde)."""
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(odt)) as z:
        x = z.read("content.xml").decode("utf-8", errors="replace")
    x = x[x.find("<office:body"):] if "<office:body" in x else x
    x = re.sub(r"<text:(?:tab|line-break|s)[^>]*/>", " ", x)
    x = re.sub(r"</text:(?:p|h)>", "\n", x)
    x = re.sub(r"<[^>]+>", "", x)
    import html
    return html.unescape(x)


# ------------------------------------------------------------ placeholders

def nome_canonico(ph: str) -> str:
    """`@x` / `{x}` / `{{ x }}` → `x`."""
    s = str(ph or "").strip()
    s = s.strip("{}").strip()
    return s.lstrip("@")


def normalizar_placeholders(texto: str, *, conhecidos: set[str] | None = None,
                            converter_arroba: bool = True
                            ) -> tuple[str, list[dict[str, str]]]:
    """Converte `@campo` e `{campo}` em `{{campo}}`. Só calcula.

    `@campo` só é convertido quando o nome é conhecido (se `conhecidos` for
    dado) — evita mexer em «@» que não é marcador. Marcadores de bloqueado
    (`{{#bloqueado id}}`) e `{{campo}}` já canônicos ficam como estão.
    Devolve `(texto_canonico, conversoes)`.
    """
    conversoes: list[dict[str, str]] = []
    s = str(texto or "")

    def _simples(m: re.Match) -> str:
        nome = m.group(1)
        novo = "{{" + nome + "}}"
        conversoes.append({"de": m.group(0), "para": novo})
        return novo

    s = RE_SIMPLES.sub(_simples, s)
    if converter_arroba:
        def _arroba(m: re.Match) -> str:
            nome = m.group(1)
            if conhecidos is not None and nome not in conhecidos \
                    and ("@" + nome) not in conhecidos:
                return m.group(0)
            novo = "{{" + nome + "}}"
            conversoes.append({"de": m.group(0), "para": novo})
            return novo
        s = RE_ARROBA.sub(_arroba, s)
    # `{{ x }}` → `{{x}}` (forma única)
    def _duplo(m: re.Match) -> str:
        novo = "{{" + m.group(1).strip() + "}}"
        if novo != m.group(0):
            conversoes.append({"de": m.group(0), "para": novo})
        return novo
    s = RE_DUPLO.sub(_duplo, s)
    return s, conversoes


def placeholders_do_texto(texto: str) -> list[str]:
    """Nomes canônicos (sem chaves/@) na ordem em que aparecem."""
    vistos: list[str] = []
    s = RE_MARCADOR_BLOQUEADO.sub("", str(texto or ""))
    for rx in (RE_DUPLO, RE_SIMPLES, RE_ARROBA):
        for m in rx.finditer(s):
            nome = m.group(1).strip()
            if nome and nome not in vistos:
                vistos.append(nome)
    return vistos


def para_formato_do_catalogo(texto: str) -> str:
    """Canônico `{{campo}}` (ou `@campo`) → `{campo}` do `rc_modelos_do_livro`.

    Tira antes os marcadores de bloqueado (não podem ir ao papel).
    """
    s = remover_marcadores_bloqueados(texto)
    s = RE_DUPLO.sub(lambda m: "{" + m.group(1).strip() + "}", s)
    return s


def vocabulario(area: str = "", template_id: str = "") -> set[str]:
    """Nomes de campo que o motor conhece para aquele modelo. Só lê código.

    Junta: `GET /modelos/api/campos` (mesma função), os campos do catálogo
    do termo (`rc_modelos_do_livro.campos_do`), os marcadores do molde
    (`rc_certidao_odt.valores`) e os aliases `serventia.*` do editor.
    """
    from modelos_motor_campos import campos
    nomes = {c["nome"] for c in campos(area=area, tipo=template_id)}
    for c in campos(area=area, tipo=template_id):
        for a in c.get("aliases") or ():
            nomes.add(nome_canonico(a))
    t = str(template_id or "").upper()
    if t.startswith("RC_TERMO_"):
        try:
            import rc_modelos_do_livro as LIVRO
            base = t.replace("RC_TERMO_", "")
            nomes |= {c["nome"] for c in LIVRO.campos_do(base)}
            nomes |= set(LIVRO.claros_do_texto(LIVRO.modelo(base)["texto"]))
        except Exception:  # noqa: BLE001 — sem catálogo, fica o da API
            pass
    if eh_molde(t) or not t:
        try:
            import rc_certidao_odt as ODT
            nomes |= {k.lstrip("@") for k in ODT.valores({}, {}, {})}
        except Exception:  # noqa: BLE001
            pass
    try:
        from modelos_editor_serventia import mapa_aliases
        nomes |= {f"serventia.{a}" for a in mapa_aliases()}
    except Exception:  # noqa: BLE001
        pass
    return {n for n in nomes if n}


def analisar_placeholders(texto: str, *, area: str = "", template_id: str = ""
                          ) -> dict[str, Any]:
    """Validação de ingestão: converte e separa usados × desconhecidos."""
    conhecidos = vocabulario(area, template_id)
    canonico, conversoes = normalizar_placeholders(
        texto, conhecidos=conhecidos | {"@" + n for n in conhecidos})
    usados = placeholders_do_texto(canonico)
    desconhecidos = [u for u in usados if u not in conhecidos]
    return {
        "texto_canonico": canonico,
        "conversoes": conversoes,
        "placeholders_usados": usados,
        "placeholders_desconhecidos": desconhecidos,
    }


# ------------------------------------------------------------ bloqueados

def remover_marcadores_bloqueados(texto: str) -> str:
    """Tira `{{#bloqueado id}}` e `{{/bloqueado}}` — o miolo fica intacto."""
    return RE_MARCADOR_BLOQUEADO.sub("", str(texto or ""))


def _rx_do_literal(literal: str) -> re.Pattern | None:
    """Regex tolerante para achar o literal no rascunho.

    Claros casam em qualquer grafia (`{x}`, `{{x}}`, `{{ x }}`, `@x`) e
    espaços casam com qualquer espaço — o trecho achado é envolvido como
    está (byte a byte).
    """
    lit = str(literal or "")
    if not lit.strip():
        return None
    partes: list[str] = []
    pos = 0
    rx_claro = re.compile(r"\{\{\s*([A-Za-z_][\w.]*)\s*\}\}|\{([A-Za-z_][\w.]*)\}"
                          r"|(?<![\w.@])@([A-Za-z_]\w*)")
    for m in rx_claro.finditer(lit):
        partes.append(_rx_texto(lit[pos:m.start()]))
        nome = re.escape(m.group(1) or m.group(2) or m.group(3))
        partes.append(rf"(?:\{{\{{\s*{nome}\s*\}}\}}|\{{{nome}\}}|@{nome}\b)")
        pos = m.end()
    partes.append(_rx_texto(lit[pos:]))
    return re.compile("".join(partes))


def _rx_texto(pedaco: str) -> str:
    out = []
    for token in re.split(r"(\s+)", pedaco):
        if not token:
            continue
        out.append(r"\s+" if token.isspace() else re.escape(token))
    return "".join(out)


def marcar_bloqueados(area: str, template_id: str, conteudo: Any) -> Any:
    """Envolve os trechos bloqueados conhecidos com `{{#bloqueado id}}…`.

    - Texto: cada trecho com literal (`trechos_bloqueados(...)[i]["texto"]`)
      achado no conteúdo é envolvido UMA vez; trecho já marcado não é
      marcado de novo. `remover_marcadores_bloqueados(saida) == entrada`.
    - Molde ODT (bytes/base64) volta inalterado: marcador dentro do XML
      sairia visível no papel.
    """
    if conteudo is None or isinstance(conteudo, (bytes, bytearray)):
        return conteudo
    if isinstance(conteudo, dict):
        return {k: marcar_bloqueados(area, template_id, v) for k, v in conteudo.items()}
    texto = str(conteudo)
    if eh_molde(template_id) and _parece_base64_odt(texto):
        return conteudo
    from modelos_motor_campos import trechos_bloqueados
    ja = {m.group(1) for m in RE_BLOQUEADO.finditer(texto)}
    for t in trechos_bloqueados(area=area, tipo=template_id):
        tid = t.get("id") or ""
        if not t.get("literal") or tid in ja:
            continue
        rx = _rx_do_literal(t.get("texto") or "")
        if rx is None:
            continue
        # não marcar dentro de bloco já marcado
        livres = _faixas_livres(texto)
        for m in rx.finditer(texto):
            if any(a <= m.start() and m.end() <= b for a, b in livres):
                texto = (texto[:m.start()] + "{{#bloqueado " + tid + "}}"
                         + m.group(0) + "{{/bloqueado}}" + texto[m.end():])
                ja.add(tid)
                break
    return texto


def _faixas_livres(texto: str) -> list[tuple[int, int]]:
    faixas = []
    pos = 0
    for m in RE_BLOQUEADO.finditer(texto):
        faixas.append((pos, m.start()))
        pos = m.end()
    faixas.append((pos, len(texto)))
    return faixas


def _parece_base64_odt(s: str) -> bool:
    s = s.strip()
    if s.startswith("data:"):
        return True
    return bool(re.fullmatch(r"[A-Za-z0-9+/=\s]{40,}", s)) and s.lstrip().startswith("UEsD")


def conferir_bloqueados(area: str, template_id: str, conteudo: str
                        ) -> tuple[list[dict], list[str], list[str]]:
    """Confere os blocos marcados no rascunho. Devolve (erros, avisos, ids).

    Miolo comparado com o literal do trecho com claros normalizados e
    espaços colapsados — `{x}` e `{{x}}` valem o mesmo.
    """
    from modelos_motor_campos import trechos_bloqueados
    erros: list[dict] = []
    avisos: list[str] = []
    por_id = {t["id"]: t for t in trechos_bloqueados(area=area, tipo=template_id)}
    ids: list[str] = []
    for m in RE_BLOQUEADO.finditer(str(conteudo or "")):
        bid, miolo = m.group(1), m.group(2)
        ids.append(bid)
        t = por_id.get(bid)
        if t is None:
            erros.append({"linha": _linha(conteudo, m.start()), "coluna": 0,
                          "codigo": "BLOQUEADO_DESCONHECIDO",
                          "msg": f"Trecho bloqueado «{bid}» não existe para "
                                 f"{template_id or area}."})
            continue
        if t.get("literal") and _comparavel(miolo) != _comparavel(t.get("texto")):
            erros.append({"linha": _linha(conteudo, m.start()), "coluna": 0,
                          "codigo": "BLOQUEADO_ADULTERADO",
                          "msg": f"Trecho bloqueado «{bid}» foi alterado — "
                                 f"volte ao texto normativo."})
    return erros, avisos, ids


def _comparavel(s: Any) -> str:
    c, _ = normalizar_placeholders(str(s or ""))
    return re.sub(r"\s+", " ", c).strip()


def _linha(texto: Any, pos: int) -> int:
    return str(texto or "")[:pos].count("\n") + 1
