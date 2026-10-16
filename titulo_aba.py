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
    # RCPJ (3) e RTD (4) chegam como CÓDIGO no endereço (`?atribuicao=4`), e o
    # nome deles mora em `rg_titulo` — a sigla é a primeira palavra dele.
    if chave.isdigit():
        try:
            import rg_titulo as TIT

            nome = TIT.NOME_DA_ATRIBUICAO.get(int(chave))
            if nome:
                return nome.split()[0]
        except Exception:
            pass
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
    # A MESMA TELA EM DOIS ITENS DO MENU — 14/10/2026. Desde que o RCPJ e o
    # RTD ganharam cada um o seu item (`rcpj_rtd_titulos`, com
    # `atribuicao=3` e `=4`), o mapa junta os dois rótulos com « · ». A aba
    # fica com o item DAQUELA atribuição; sem atribuição, com o primeiro.
    if " · " in rotulo:
        opcoes = [o.strip() for o in rotulo.split(" · ") if o.strip()]
        escolhida = next((o for o in opcoes
                          if extra and o.lower().startswith(extra.lower())),
                         opcoes[0] if opcoes else rotulo)
        rotulo = escolhida
    if not extra and modulo_nome:
        extra = modulo_nome.strip()
    if extra and extra.lower() not in rotulo.lower():
        return f"{rotulo} \u2014 {extra}"
    return rotulo
