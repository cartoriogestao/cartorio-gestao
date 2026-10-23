"""Papéis do catálogo — a retificação de área e o georreferenciamento.

**PASTA PRÓPRIA, ATRIBUIÇÃO DO REGISTRO DE IMÓVEIS** (LF06G, 19/10/2026). A
retificação de área (Lei 6.015/1973, art. 213) é procedimento DO oficial de
registro de imóveis, e não uma atribuição da serventia: posta como sétima
atribuição, ela ganharia submódulo, rota e menu próprios para um papel só, e a
casa procuraria a notificação fora do Registro de Imóveis, onde ela não mora.
A pasta separada é só para o arquivo: `modelos_padrao/retificacao/`.

**`elementos_comuns: False`**: o texto é `{claro}` do `str.format`, e os papéis
do Registro de Imóveis são Jinja — um encerramento comum da atribuição, em
Jinja, sairia escrito no papel. É o mesmo caso das duas fichas do Livro 3.
"""
from __future__ import annotations

PASTA = "retificacao"
ATRIBUICAO = "Registro de Imóveis"

PAPEIS: tuple[dict, ...] = (
    {'chave': 'RT_NOTIFICACAO_CONFRONTANTE', 'padrao': ('rt_notificacao', 'MODELO'), 'elementos_comuns': False},
)
