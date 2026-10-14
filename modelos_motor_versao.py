# -*- coding: utf-8 -*-
"""Hook da versão PUBLICADA do Editor de modelos — Etapa 2c (SANDBOX).

Ponto único, no motor, que pergunta ao Editor se há versão publicada para
um modelo e se a chave da área está ligada. **Flag desligada por padrão**:
com `USAR_CONTEUDO_PUBLICADO_EDITOR = False` o motor nem consulta o Editor
e tudo segue pelo caminho atual (`modelos_da_casa.corpo_de` para termo,
`modelos_moldes.arquivo_que_vale` / `.odt` do pacote para molde).

Ordem quando a flag estiver ligada:
  1. `modelos_editor.chave_ligada(con, area)` — False → caminho atual;
  2. `modelos_editor.conteudo_publicado_se_ligado(con, area=, template_id=,
     parte=)` — None → caminho atual;
  3. dict → `conteudo` (termo, texto) ou `conteudo_blob` (molde, ODT).

NÃO edita `atribuicoes_web.py`, `modelos_da_casa.py` nem `corpo_de`; a
emissão real só passa a usar isto quando for plugada (fase de fechamento).
Qualquer erro do Editor → caminho atual (a emissão nunca quebra por ele).
"""
from __future__ import annotations

import sqlite3
from typing import Any

# Desligada até o OK do oficial + reinício. Ligar = trocar para True (uma linha)
# E ligar a chave da área no Editor (settings). As duas precisam estar ligadas.
USAR_CONTEUDO_PUBLICADO_EDITOR = False

ORIGEM_EDITOR = "editor_publicada"
ORIGEM_ATUAL = "vigente"


def _editor():
    import modelos_editor as ED  # import tardio: o motor não depende do editor
    return ED


def conteudo_publicado_editor(con: sqlite3.Connection | Any, *, area: str = "RCPN",
                              template_id: str, parte: str = "CORPO",
                              usar: bool | None = None,
                              editor: Any = None) -> dict | None:
    """Versão publicada do Editor ou None (→ caminho atual). Só lê.

    `usar` sobrepõe a flag (testes); `editor` permite injetar um módulo
    falso (mock) com `chave_ligada` e `conteudo_publicado_se_ligado`.
    """
    ligado = USAR_CONTEUDO_PUBLICADO_EDITOR if usar is None else bool(usar)
    if not ligado or con is None:
        return None
    try:
        ed = editor or _editor()
        if not ed.chave_ligada(con, area):
            return None
        pub = ed.conteudo_publicado_se_ligado(
            con, area=area, template_id=template_id, parte=parte)
    except Exception:  # noqa: BLE001 — editor ausente/quebrado: emissão segue
        return None
    if not pub:
        return None
    return dict(pub)


def corpo_do_termo(con: sqlite3.Connection | Any, chave: str, *, area: str = "RCPN",
                   usar: bool | None = None, editor: Any = None
                   ) -> tuple[str | None, str]:
    """Corpo do termo: publicada do Editor (se ligado) ou `corpo_de`.

    Devolve `(corpo_no_formato_do_catalogo, origem)`. A publicada pode vir
    em `{{campo}}`/`@campo`/com marcadores de bloqueado — sai convertida
    para `{campo}` (formato que `rc_modelos_do_livro` monta).
    """
    pub = conteudo_publicado_editor(con, area=area, template_id=chave,
                                    parte="CORPO", usar=usar, editor=editor)
    if pub and str(pub.get("conteudo") or "").strip():
        from modelos_motor_placeholders import (
            normalizar_placeholders, para_formato_do_catalogo)
        canon, _ = normalizar_placeholders(pub["conteudo"])
        return para_formato_do_catalogo(canon), ORIGEM_EDITOR
    try:
        import modelos_da_casa as MODELOS
        return (MODELOS.corpo_de(con, chave) if chave else None), ORIGEM_ATUAL
    except Exception:  # noqa: BLE001 — sem catálogo, vale o padrão do código
        return None, ORIGEM_ATUAL


def molde_da_certidao(con: sqlite3.Connection | Any, chave: str, *,
                      area: str = "RCPN", usar: bool | None = None,
                      editor: Any = None) -> tuple[bytes | None, str]:
    """Molde ODT: publicada do Editor (se ligado) ou None (→ caminho atual,
    que é `molde_bytes=None` = `.odt` do pacote, como hoje na prévia)."""
    pub = conteudo_publicado_editor(con, area=area, template_id=chave,
                                    parte="MOLDE", usar=usar, editor=editor)
    if pub and pub.get("conteudo_blob"):
        return bytes(pub["conteudo_blob"]), ORIGEM_EDITOR
    return None, ORIGEM_ATUAL
