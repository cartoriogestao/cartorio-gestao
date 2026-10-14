"""Papéis do catálogo — Tabelionato de Notas."""
from __future__ import annotations

PAPEIS: tuple[dict, ...] = (
    {'chave': 'NOTAS_TRASLADO', 'atribuicao': 'Tabelionato de Notas', 'nome': 'Traslado', 'padrao': ('notas_web', 'MODELO_TRASLADO'), 'explica': 'A via da escritura que se entrega à parte.'},
    {'chave': 'NOTAS_TERMO_LIVRO', 'atribuicao': 'Tabelionato de Notas', 'nome': 'Termo do livro', 'padrao': ('notas_web', 'MODELO_TERMO_LIVRO'), 'explica': 'O instrumento que vai para o livro de notas — mesmo cabeçalho do traslado (brasão e serventia), teor, assinaturas dos comparecentes e carimbo compacto do selo (sem QR). Distinto do traslado entregue à parte.'},
    {'chave': 'NOTAS_CARTAO_FICHA', 'atribuicao': 'Tabelionato de Notas', 'nome': 'Cartão de autógrafo', 'padrao': ('notas_web', 'MODELO_CARTAO_FICHA'), 'explica': 'A ficha de firma impressa para o cliente assinar e a serventia arquivar — qualificação, autógrafos, foto e digital. Cabeçalho da serventia fica fora (em código); selo/QR e linhas de assinatura também.'},
)
