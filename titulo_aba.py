from __future__ import annotations

import functools
from pathlib import Path

import ajuda_mapa as _mapa

_RAIZ = Path(__file__).resolve().parent


@functools.lru_cache(maxsize=1)
def _nomes_do_menu() -> dict[str, str]:
    return _mapa._nomes_do_menu(_RAIZ)


def _rotulo_atribuicao(atribuicao: str) -> str:
    chave = (atribuicao or "").strip()
    if not chave:
        return ""
    try:
        import atrib_certidao as CE

        painel = CE.PAINEIS.get(chave)
        if painel:
            return str(painel.get("nome") or chave)
    except Exception:
        pass
    return chave


def sugerir(
    endpoint: str | None,
    *,
    atribuicao: str = "",
    modulo_nome: str = "",
) -> str:
    if not endpoint:
        return ""
    bruto = _nomes_do_menu().get(endpoint, "")
    if not bruto:
        return (modulo_nome or "").strip()

    seta = "\u2192"
    if f" {seta} " in bruto:
        _, rotulo = bruto.split(f" {seta} ", 1)
    elif " \u00b7 " in bruto:
        rotulo = bruto.split(" \u00b7 ", 1)[0].strip()
        if f" {seta} " in rotulo:
            _, rotulo = rotulo.split(f" {seta} ", 1)
    else:
        rotulo = bruto

    rotulo = rotulo.strip()
    if not rotulo:
        return (modulo_nome or "").strip()

    extra = _rotulo_atribuicao(atribuicao)
    if not extra and modulo_nome:
        extra = modulo_nome.strip()
    if extra and extra.lower() not in rotulo.lower():
        return f"{rotulo} \u2014 {extra}"
    return rotulo
