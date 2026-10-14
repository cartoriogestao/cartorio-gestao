"""Catálogo de papéis por atribuição — ver módulos irmãos por atribuição."""
from __future__ import annotations
from modelos_papeis import caixa, notas, protesto, rcpj_rtd, rcpn, ri
CATALOGO: tuple[dict, ...] = (
    ri.PAPEIS + caixa.PAPEIS + notas.PAPEIS + rcpj_rtd.PAPEIS
    + rcpn.PAPEIS[:2] + protesto.PAPEIS + rcpn.PAPEIS[2:]
)
