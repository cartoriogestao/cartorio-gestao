"""Papéis do catálogo — Tabelionato de Notas."""
from __future__ import annotations

PAPEIS: tuple[dict, ...] = (
    {'chave': 'NOTAS_TRASLADO', 'atribuicao': 'Tabelionato de Notas', 'nome': 'Traslado', 'padrao': ('notas_web', 'MODELO_TRASLADO'), 'explica': 'A via da escritura que se entrega à parte.'},
    {'chave': 'NOTAS_TERMO_LIVRO', 'atribuicao': 'Tabelionato de Notas', 'nome': 'Termo do livro', 'padrao': ('notas_web', 'MODELO_TERMO_LIVRO'), 'explica': 'O instrumento que vai para o livro de notas — mesmo cabeçalho do traslado (brasão e serventia), teor, assinaturas dos comparecentes e carimbo compacto do selo (sem QR). Distinto do traslado entregue à parte.'},
    # A CERTIDÃO DAS NOTAS (15/10/2026): sem precedente de texto no E-Ofício,
    # e afirmação jurídica num papel assinado — o texto é do oficial.
    {'chave': 'NOTAS_CERTIDAO_INTEIRO_TEOR', 'atribuicao': 'Tabelionato de Notas', 'nome': 'Certidão de inteiro teor', 'padrao': ('notas_certidao', 'MODELO_INTEIRO_TEOR'), 'explica': 'Certidão do ato identificado por livro e folha: reproduz o teor do livro e as anotações à margem.'},
    {'chave': 'NOTAS_CERTIDAO_POSITIVA', 'atribuicao': 'Tabelionato de Notas', 'nome': 'Certidão positiva de atos', 'padrao': ('notas_certidao', 'MODELO_POSITIVA'), 'explica': 'Busca pela parte (nome ou documento) que achou atos: relaciona livro, folha, data e qualificação.'},
    {'chave': 'NOTAS_CERTIDAO_NEGATIVA', 'atribuicao': 'Tabelionato de Notas', 'nome': 'Certidão negativa de atos', 'padrao': ('notas_certidao', 'MODELO_NEGATIVA'), 'explica': 'Busca pela parte que não achou ato nenhum no período.'},
    {'chave': 'NOTAS_CARTAO_FICHA', 'atribuicao': 'Tabelionato de Notas', 'nome': 'Cartão de autógrafo', 'padrao': ('notas_web', 'MODELO_CARTAO_FICHA'), 'explica': 'A ficha de firma impressa para o cliente assinar e a serventia arquivar — qualificação, autógrafos, foto e digital. Cabeçalho da serventia fica fora (em código); selo/QR e linhas de assinatura também.'},
)
