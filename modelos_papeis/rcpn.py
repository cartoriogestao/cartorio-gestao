"""Papéis do catálogo — Registro Civil das Pessoas Naturais."""
from __future__ import annotations

PASTA = "rcpn"
ATRIBUICAO = "Registro Civil das Pessoas Naturais"

PAPEIS: tuple[dict, ...] = (
    {'chave': 'RC_TERMO_NASCIMENTO', 'padrao': ('rc_modelos_do_livro', 'TERMO_NASCIMENTO')},
    {'chave': 'RC_TERMO_CASAMENTO', 'padrao': ('rc_modelos_do_livro', 'TERMO_CASAMENTO')},
    {'chave': 'RC_TERMO_OBITO', 'padrao': ('rc_modelos_do_livro', 'TERMO_OBITO')},
    {'chave': 'RC_TERMO_LIVRO_E', 'padrao': ('rc_modelos_do_livro', 'TERMO_LIVRO_E')},
    # LF06C (19/10/2026): os papéis do civil que eram montados no código. Não
    # herdam o encerramento e o rodapé comuns da atribuição — esses são os dos
    # termos, e um rodapé de termo no meio de um edital ou de uma certidão
    # sairia no papel errado. O nome em `padrao` é o que responde pelo
    # `__getattr__` do módulo que monta o papel (nenhum deles era constante).
    {'chave': 'RC_QUALIFICACAO', 'padrao': ('rc_modelos_do_livro', 'QUALIFICACAO'), 'elementos_comuns': False},
    {'chave': 'RC_CERTIDAO_RESUMO', 'padrao': ('rc_certidao', 'FECHO_DO_TEOR'), 'elementos_comuns': False},
    {'chave': 'RC_CERTIDAO_INTEIRO_TEOR', 'padrao': ('rc_certidao_inteiro_teor', 'INTRODUCAO'), 'elementos_comuns': False},
    {'chave': 'RC_ANOTACAO_CRC_COMPACTA', 'padrao': ('rc_anotacao_crc', 'ANOTACAO_COMPACTA'), 'elementos_comuns': False},
    {'chave': 'RC_ANOTACAO_CRC_COMPLETA', 'padrao': ('rc_anotacao_crc', 'ANOTACAO_COMPLETA'), 'elementos_comuns': False},
    {'chave': 'RC_ANOTACAO_CRC_FE_PUBLICA', 'padrao': ('rc_anotacao_crc', 'ANOTACAO_FE_PUBLICA'), 'elementos_comuns': False},
    {'chave': 'RC_AVERBACAO_RETIFICACAO', 'padrao': ('rc_averbacao_modelos', 'TEOR_DA_RETIFICACAO'), 'elementos_comuns': False},
    {'chave': 'RC_COMUNICACAO_OBITOS', 'padrao': ('rc_comunicacoes', 'COMUNICACAO_MENSAL'), 'elementos_comuns': False},
    {'chave': 'RC_OFICIO_FUNAI', 'padrao': ('rc_funai', 'OFICIO_A_FUNAI'), 'elementos_comuns': False},
    {'chave': 'RC_EDITAL_PROCLAMAS', 'padrao': ('habilitacao_web', 'EDITAL_DE_PROCLAMAS'), 'elementos_comuns': False},
    {'chave': 'RC_EDITAL_PROCLAMAS_FOLHA', 'padrao': ('habilitacao_web', 'FOLHA_DO_EDITAL'), 'elementos_comuns': False},
    {'chave': 'RC_CERTIDAO_HABILITACAO', 'padrao': ('habilitacao_web', 'CERTIDAO_DE_HABILITACAO'), 'elementos_comuns': False},
)
