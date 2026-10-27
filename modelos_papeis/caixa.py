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
    # 27/10/2026: o convite da pesquisa de satisfação ao cliente
    # (`satisfacao_envio`) — o e-mail que sai sozinho, por isso em chaves e
    # sem o encerramento comum do caixa. «quero poder editar o texto do
    # e-mail» (o oficial, 27/10/2026).
    {'chave': 'OUVIDORIA_CONVITE_PESQUISA',
     'padrao': ('satisfacao_envio', 'MODELO_CONVITE_PESQUISA'),
     'elementos_comuns': False},
)
