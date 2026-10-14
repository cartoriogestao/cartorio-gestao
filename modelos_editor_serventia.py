"""Leitura isolada dos dados da serventia para o editor de modelos.

Ponto ÚNICO. Ordem de fonte do mapa `{{serventia.*}}`:
  1) B0 oficial — `serventia.ALIASES_MODELOS` + `serventia.namespace_modelos`
     (Sanitização — Migração), se já estiver no pacote;
  2) mapa no motor (`modelos_motor*`), se expuser aliases;
  3) cópia local de contingência (mesmo contrato), marcada em `fonte_mapa`.

Nunca grava literais da casa neste módulo. Não edita `serventia.py`.
"""
from __future__ import annotations

from typing import Any, Callable

# Cópia local de contingência — idêntica ao contrato B0/Fidelidade.
# Usada SÓ se B0 e motor ainda não expuserem o mapa.
_ALIAS_LOCAL: dict[str, str] = {
    "nome": "unit_name",
    "cns": "ri_cns",
    "cnpj": "serventia_cnpj",
    "cidade": "ri_cidade",
    "uf": "ri_uf",
    "cidade_uf": "cidade_uf",
    "endereco": "serventia_endereco",
    "endereco_completo": "endereco_completo",
    "cep": "serventia_cep",
    "telefone": "serventia_telefone",
    "email": "serventia_email",
    "titular": "serventia_titular",
    "titulo": "serventia_titulo",
    "substituta": "ri_substituta",
    "brasao": "serventia_brasao",
}

_FONTE_MAPA = "local"


def _resolver_aliases() -> tuple[dict[str, str], str]:
    """Devolve (mapa alias→chave, fonte)."""
    try:
        import serventia as SV
        oficial = getattr(SV, "ALIASES_MODELOS", None)
        if oficial:
            return dict(oficial), "b0_serventia"
    except Exception:
        pass
    try:
        import modelos_motor as MOTOR  # noqa: F401
        # Se o motor expuser o mapa no futuro
        for attr in ("ALIASES_SERVENTIA", "ALIASES_MODELOS", "MAPA_SERVENTIA"):
            oficial = getattr(MOTOR, attr, None)
            if oficial:
                return dict(oficial), "motor"
        ctx = getattr(MOTOR, "contexto", None)
        if ctx is not None and hasattr(ctx, "ALIASES_MODELOS"):
            return dict(ctx.ALIASES_MODELOS), "motor"
    except Exception:
        pass
    return dict(_ALIAS_LOCAL), "local"


def mapa_aliases() -> dict[str, str]:
    m, _fonte = _resolver_aliases()
    return m


def fonte_mapa() -> str:
    _m, fonte = _resolver_aliases()
    return fonte


# Compat: nome usado no Marco 1
ALIAS_SERVENTIA: dict[str, str] = mapa_aliases()


def PLACEHOLDERS_SERVENTIA_dyn() -> tuple[str, ...]:
    return tuple(f"serventia.{a}" for a in mapa_aliases())


def placeholders_serventia() -> tuple[str, ...]:
    return PLACEHOLDERS_SERVENTIA_dyn()


# Compat Marco 1: tupla inicial; preferir placeholders_serventia() / mapa_aliases()
PLACEHOLDERS_SERVENTIA = tuple(f"serventia.{a}" for a in _ALIAS_LOCAL)


def ler_dados(get_settings: Callable | dict | None) -> dict[str, Any]:
    """Devolve o dict de serventia.dados."""
    import serventia as SV
    return SV.dados(get_settings)


def namespace_serventia(get_settings: Callable | dict | None) -> dict[str, Any]:
    """Dict `{nome: valor, cns: valor, ...}` pronto para {{serventia.*}}."""
    bruto = ler_dados(get_settings)
    try:
        import serventia as SV
        if hasattr(SV, "namespace_modelos"):
            return dict(SV.namespace_modelos(bruto))
    except Exception:
        pass
    saida: dict[str, Any] = {}
    for alias, chave in mapa_aliases().items():
        saida[alias] = bruto.get(chave, "")
    return saida


def literais_proibidos(get_settings: Callable | dict | None) -> list[dict[str, str]]:
    """Valores reais da serventia que NÃO podem aparecer como literal no modelo.

    O teste do validador monta o literal a partir da fixture — nunca hardcoded.
    """
    ns = namespace_serventia(get_settings)
    pular = {"brasao", "titulo"}
    achados: list[dict[str, str]] = []
    for alias, valor in ns.items():
        if alias in pular:
            continue
        texto = str(valor or "").strip()
        if len(texto) < 4:
            continue
        achados.append({
            "alias": alias,
            "placeholder": f"{{{{serventia.{alias}}}}}",
            "literal": texto,
        })
    return achados
