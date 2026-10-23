# -*- coding: utf-8 -*-
"""Nome que pode sair no ato e no selo ? nunca r?tulo de m?quina/rob?.

Achado em 21/09/2026: tr?s selos de nascimento (REGNAS?) sa?ram com
`obtido_por` / escrevente = "Rob? Nascimento RCPN". O selador do TJMA recebe
esse campo como quem praticou o ato. M?quina n?o assina ato de serventia.

Uma fun??o s?, usada por `usuario_nome`, pela emiss?o do selo e pelo cadastro
de usu?rios ? tr?s c?pias da mesma regra divergiriam de novo.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable

# Placeholders e nomes de ferramenta que j? apareceram no raz?o (Codex) ou
# no teor (operador/sistema). Compara??o em forma ASCII min?scula.
_EXATOS = frozenset({
    "operador", "none", "null", "sistema", "robot", "robo", "bot",
    "cartoriogestao", "servidor", "codex", "grok", "chatgpt", "claude",
    "cursor", "copilot", "gpt", "assistente",
})

# "Rob? Nascimento RCPN", "Robo Certid?o", ? ? N?O casa "Robson".
_RE_PREFIXO_ROBO = re.compile(r"^rob[o?]\b", re.IGNORECASE)


def _forma(nome: Any) -> str:
    bruto = ("" if nome is None else str(nome)).strip()
    if not bruto:
        return ""
    # casefold + tira acento s? para comparar; a forma devolvida ao ato
    # continua sendo a original quando humana.
    nfd = unicodedata.normalize("NFD", bruto.casefold())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def eh_rotulo_de_maquina(nome: Any) -> bool:
    """True se o texto N?O pode assinar ato nem ir ao selador."""
    bruto = ("" if nome is None else str(nome)).strip()
    if not bruto:
        return True
    forma = _forma(bruto)
    if forma in _EXATOS:
        return True
    # Prefixo "rob?"/"robo" como palavra (Rob? X). "Robson" n?o casa.
    if _RE_PREFIXO_ROBO.search(bruto):
        return True
    if forma.startswith("robo ") or forma == "robo":
        return True
    return False


def nome_humano_para_ato(nome: Any, *fallbacks: Any) -> str:
    """Devolve o primeiro nome humano da lista (candidato + fallbacks)."""
    for cand in (nome, *fallbacks):
        texto = ("" if cand is None else str(cand)).strip()
        if texto and not eh_rotulo_de_maquina(texto):
            return texto
    return ""


def fallbacks_da_casa(db) -> list[str]:
    """Ordem da casa quando a sess?o ? m?quina: substituta, depois gente do cadastro."""
    saida: list[str] = []
    for chave in ("ri_substituta", "serventia_oficial", "oficial_nome",
                  "ri_registrador"):
        try:
            v = (db.get_setting(chave, "") or "").strip()
        except Exception:
            v = ""
        if v:
            saida.append(v)
    # O PRIMEIRO USUÁRIO DO CADASTRO NÃO ASSINA ATO DE NINGUÉM (revisão de
    # segurança de 22/10/2026, A6): cair em `list_users` punha no selo o nome
    # de quem por acaso está no alto da lista. Sem a substituta e o oficial
    # cadastrados, a resposta é «não há humano», e quem pede o selo recusa.
    return saida
