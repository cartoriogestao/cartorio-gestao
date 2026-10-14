"""Papéis do catálogo — Caixa e protocolo."""
from __future__ import annotations

PAPEIS: tuple[dict, ...] = (
    {'chave': 'CAIXA_RECIBO', 'atribuicao': 'Caixa e protocolo', 'nome': 'Recibo', 'padrao': ('caixa_web', 'MODELO_RECIBO'), 'explica': 'A prova de pagamento do atendimento inteiro.'},
    {'chave': 'CAIXA_ORCAMENTO', 'atribuicao': 'Caixa e protocolo', 'nome': 'Orçamento', 'padrao': ('caixa_web', 'MODELO_ORCAMENTO'), 'explica': 'O que o ato vai custar, com os fundos separados.'},
    {'chave': 'CAIXA_RECEPCAO', 'atribuicao': 'Caixa e protocolo', 'nome': 'Comprovante de recepção', 'padrao': ('caixa_web', 'MODELO_RECEPCAO'), 'explica': 'O que o cliente entregou no balcão, e quando.'},
)
