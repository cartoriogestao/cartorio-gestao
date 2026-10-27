"""Papéis do catálogo — Caixa e protocolo."""
from __future__ import annotations

PASTA = "caixa"
ATRIBUICAO = "Caixa e protocolo"

PAPEIS: tuple[dict, ...] = (
    {'chave': 'CAIXA_RECIBO', 'padrao': ('caixa_web', 'MODELO_RECIBO')},
    {'chave': 'CAIXA_ORCAMENTO', 'padrao': ('caixa_web', 'MODELO_ORCAMENTO')},
    {'chave': 'CAIXA_RECEPCAO', 'padrao': ('caixa_web', 'MODELO_RECEPCAO')},
    # LF06F (19/10/2026): os rascunhos do WhatsApp ao cliente, que eram
    # f-strings em `wa_textos`. Em chaves, e por isso fora do encerramento
    # comum do caixa (que é Jinja).
    {'chave': 'CAIXA_WHATSAPP', 'padrao': ('wa_textos', 'MODELO_WHATSAPP'), 'elementos_comuns': False},
    # 26/10/2026: a nota de exigência GERAL do protocolo do balcão — a das
    # atribuições que não têm nota própria (Notas, Registro Civil, Protesto).
    # O texto nasceu na pasta; o nome responde por `caixa_exigencia.__getattr__`.
    {'chave': 'CAIXA_EXIGENCIA', 'padrao': ('caixa_exigencia', 'MODELO_NOTA_DE_EXIGENCIA')},
)
