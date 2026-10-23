# -*- coding: utf-8 -*-
"""Nome que pode sair no ato e no selo — nunca rótulo de máquina/robô.

Achado em 21/09/2026: três selos de nascimento (REGNAS…) saíram com
`obtido_por` / escrevente = "Robô Nascimento RCPN". O selador do TJMA recebe
esse campo como quem praticou o ato. Máquina não assina ato de serventia.

Uma função só, usada por `usuario_nome`, pela emissão do selo e pelo cadastro
de usuários — três cópias da mesma regra divergiriam de novo.

OS ACENTOS DESTE ARQUIVO TINHAM VIRADO «?» desde a primeira versão guardada
(3.6.160), e foram restaurados em 23/10/2026. O estrago que importava estava
no código, e não na prosa: a expressão do prefixo dizia `rob[o?]` — «Robô»,
com acento, não casava ali, e só era pego pela conferência de baixo, que tira
o acento antes de comparar.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable

# Placeholders e nomes de ferramenta que já apareceram no razão (Codex) ou
# no teor (operador/sistema). Comparação em forma ASCII minúscula.
_EXATOS = frozenset({
    "operador", "none", "null", "sistema", "robot", "robo", "bot",
    "cartoriogestao", "servidor", "codex", "grok", "chatgpt", "claude",
    "cursor", "copilot", "gpt", "assistente",
})

#: O QUE SAI NO LUGAR DO NOME QUANDO QUEM ESTÁ NA TELA É MÁQUINA — 23/10/2026,
#: ordem do oficial («solução 1»). Até aqui `usuario_nome` trocava o robô pela
#: substituta, e o ato saía dizendo que ela o praticou: a mesma troca que a
#: revisão de segurança de 22/10 (A6) tirou do selo e tinha deixado no ato.
#: Agora o campo fica PENDENTE, e quem selar assina —
#: `ato_selado.vincular_ao_ato` troca esta marca pelo nome de quem obteve o
#: selo. E a marca CONTA COMO MÁQUINA, de propósito: o selo recusa sair com
#: ela no lugar do escrevente.
MARCA_PENDENTE = "PENDENTE — assina quem selar"

# "Robô Nascimento RCPN", "Robo Certidão", … — NÃO casa "Robson".
_RE_PREFIXO_ROBO = re.compile(r"^rob[oô]\b", re.IGNORECASE)


def _forma(nome: Any) -> str:
    bruto = ("" if nome is None else str(nome)).strip()
    if not bruto:
        return ""
    # casefold + tira acento só para comparar; a forma devolvida ao ato
    # continua sendo a original quando humana.
    nfd = unicodedata.normalize("NFD", bruto.casefold())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def eh_rotulo_de_maquina(nome: Any) -> bool:
    """True se o texto NÃO pode assinar ato nem ir ao selador."""
    bruto = ("" if nome is None else str(nome)).strip()
    if not bruto:
        return True
    if bruto == MARCA_PENDENTE:
        return True
    forma = _forma(bruto)
    if forma in _EXATOS:
        return True
    # Prefixo "robô"/"robo" como palavra (Robô X). "Robson" não casa.
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
    """Substituta e oficial cadastrados, nesta ordem. Só lê.

    Desde 23/10/2026 `usuario_nome` NÃO os usa: sessão de máquina sai como
    `MARCA_PENDENTE`, e não no nome deles. Quem ainda chama é a emissão do
    selo (`ato_selado.obter_selo`), e ali eles só decidem a frase da recusa:
    usuário máquina não sela de jeito nenhum.
    """
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
