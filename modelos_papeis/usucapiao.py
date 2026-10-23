"""Papéis do catálogo — a usucapião extrajudicial.

**PASTA PRÓPRIA, ATRIBUIÇÃO DO REGISTRO DE IMÓVEIS** (LF06G, 19/10/2026), pelo
mesmo motivo da retificação (`modelos_papeis/retificacao.py`): a usucapião
extrajudicial (Lei 6.015/1973, art. 216-A) corre perante o oficial de registro
de imóveis. Os papéis ficam na tela do Registro de Imóveis; o arquivo, em
`modelos_padrao/usucapiao/`.

**AS DECISÕES E O PEDIDO DO DOSSIÊ NÃO TINHAM CONSTANTE** — eram f-strings de
`usucapiao.modelos_de_decisao` e de `usucapiao.montar_dossie`. O par `padrao`
deles é o nome por que o texto passou a responder no módulo
(`usucapiao.MODELO_DECISAO_PROCEDENTE`…), que é o que o `__getattr__` serve.

**`elementos_comuns: False`**, como na retificação: o texto é `{claro}` do
`str.format`, e os papéis do Registro de Imóveis são Jinja.
"""
from __future__ import annotations

PASTA = "usucapiao"
ATRIBUICAO = "Registro de Imóveis"

PAPEIS: tuple[dict, ...] = (
    {'chave': 'US_NOTIFICACAO', 'padrao': ('us_notificacao', 'CORPO'), 'elementos_comuns': False},
    {'chave': 'US_EDITAL', 'padrao': ('us_notificacao', 'EDITAL'), 'elementos_comuns': False},
    {'chave': 'US_OFICIO_AO_ENTE', 'padrao': ('us_notificacao', 'OFICIO_AO_ENTE'), 'elementos_comuns': False},
    {'chave': 'US_DECISAO_PROCEDENTE', 'padrao': ('usucapiao', 'MODELO_DECISAO_PROCEDENTE'), 'elementos_comuns': False},
    {'chave': 'US_DECISAO_IMPROCEDENTE', 'padrao': ('usucapiao', 'MODELO_DECISAO_IMPROCEDENTE'), 'elementos_comuns': False},
    {'chave': 'US_DECISAO_EXIGENCIA', 'padrao': ('usucapiao', 'MODELO_DECISAO_EXIGENCIA'), 'elementos_comuns': False},
    {'chave': 'US_DECISAO_REMESSA_JUIZO', 'padrao': ('usucapiao', 'MODELO_DECISAO_REMESSA_JUIZO'), 'elementos_comuns': False},
    {'chave': 'US_DOSSIE_PEDIDO', 'padrao': ('usucapiao', 'MODELO_PEDIDO_DO_DOSSIE'), 'elementos_comuns': False},
)
