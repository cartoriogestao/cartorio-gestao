"""Catálogo de papéis por atribuição — ver módulos irmãos por atribuição.

O TEXTO E A FICHA DE CADA PAPEL MORAM EM `modelos_padrao/` desde o LF06A
(19/10/2026): `<pasta>/<CHAVE>.txt` é o corpo, `<CHAVE>.json` é o nome, o
formato e a explicação. Aqui fica só o que é do código — a ORDEM da tela, o
nome antigo da constante (`padrao`), o marcador do miolo — e `pasta.completar`
junta os dois. Ver `docs/MODELOS_PADRAO.md`.
"""
from __future__ import annotations
from modelos_papeis import (caixa, notas, protesto, rcpj_rtd, rcpn, retificacao,
                            ri, usucapiao)
from modelos_papeis.pasta import completar


def _de(modulo, papeis) -> tuple[dict, ...]:
    return tuple(completar(modulo.PASTA, c, modulo.ATRIBUICAO) for c in papeis)


# A RETIFICAÇÃO E A USUCAPIÃO VÊM LOGO DEPOIS DO RI, e não no fim: são papéis
# do Registro de Imóveis (LF06G), e a tela agrupa o catálogo pela ordem — no
# fim, o Registro de Imóveis apareceria duas vezes na lista.
CATALOGO: tuple[dict, ...] = (
    _de(ri, ri.PAPEIS) + _de(retificacao, retificacao.PAPEIS)
    + _de(usucapiao, usucapiao.PAPEIS)
    + _de(caixa, caixa.PAPEIS) + _de(notas, notas.PAPEIS)
    + _de(rcpj_rtd, rcpj_rtd.PAPEIS)
    + _de(rcpn, rcpn.PAPEIS[:2]) + _de(protesto, protesto.PAPEIS)
    + _de(rcpn, rcpn.PAPEIS[2:])
)
