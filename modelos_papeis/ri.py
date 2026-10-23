"""Papéis do catálogo — Registro de Imóveis."""
from __future__ import annotations

PASTA = "ri"
ATRIBUICAO = "Registro de Imóveis"

PAPEIS: tuple[dict, ...] = (
    {'chave': 'RI_CABECALHO', 'padrao': ('ri_odt', 'MODELO_CABECALHO_PADRAO')},
    {'chave': 'RI_FICHA', 'padrao': ('ri_odt', 'MODELO_FICHA_PADRAO')},
    {'chave': 'RI_CERTIDAO', 'padrao': ('ri_odt', 'MODELO_CERTIDAO_PADRAO'), 'miolo': ('ri_odt', 'MARCADOR_DO_MIOLO')},
    {'chave': 'RI_CERTIDAO_INTEIRO_TEOR', 'padrao': ('ri_odt', 'MIOLO_CERTIDAO_INTEIRO_TEOR')},
    {'chave': 'RI_CERTIDAO_ONUS', 'padrao': ('ri_odt', 'MIOLO_CERTIDAO_ONUS')},
    {'chave': 'RI_CERTIDAO_PROPRIEDADE', 'padrao': ('ri_odt', 'MIOLO_CERTIDAO_PROPRIEDADE')},
    {'chave': 'RI_CERTIDAO_DOMINIAL', 'padrao': ('ri_odt', 'MIOLO_CERTIDAO_DOMINIAL')},
    {'chave': 'RI_CERTIDAO_VINTENARIA', 'padrao': ('ri_odt', 'MIOLO_CERTIDAO_VINTENARIA')},
    {'chave': 'RI_CERTIDAO_NEGATIVA_IMOVEL', 'padrao': ('ri_certidao_negativa', 'MODELO_PADRAO')},
    {'chave': 'RI_NOTA', 'padrao': ('ri_odt', 'MODELO_NOTA_PADRAO')},
    {'chave': 'RI_PRENOTACAO', 'padrao': ('ri_web', 'MODELO_PRENOTACAO')},
    {'chave': 'RI_LIVRO3_FICHA', 'padrao': ('ra_ficha_odt', 'MODELO_FICHA_LIVRO3_PADRAO'), 'elementos_comuns': False},
    {'chave': 'RI_LIVRO3_CERTIDAO', 'padrao': ('atrib_certidao', 'MODELO_CERTIDAO_LIVRO3'), 'elementos_comuns': False},
    # LF06B (19/10/2026): as FRASES que os módulos do RI montavam em f-string.
    # A regra que escolhe a frase ficou no módulo; o texto, na pasta (ver
    # `ri_frases.py`). Sem elementos comuns: a frase entra DENTRO de um papel,
    # e o fecho e o rodapé da atribuição sairiam no meio dele. O par
    # `padrao` é `ri_frases.<CHAVE>`: não havia constante antes.
    # -- LF06B grupo A (ri_web, ri_certidao_negativa)
    {'chave': 'RI_PRENOTACOES_ABERTAS_NAO_HA', 'padrao': ('ri_frases', 'RI_PRENOTACOES_ABERTAS_NAO_HA'), 'elementos_comuns': False},
    {'chave': 'RI_PRENOTACOES_ABERTAS_HA_UMA', 'padrao': ('ri_frases', 'RI_PRENOTACOES_ABERTAS_HA_UMA'), 'elementos_comuns': False},
    {'chave': 'RI_PRENOTACOES_ABERTAS_HA_VARIAS', 'padrao': ('ri_frases', 'RI_PRENOTACOES_ABERTAS_HA_VARIAS'), 'elementos_comuns': False},
    {'chave': 'RI_PRENOTACOES_ABERTAS_ITEM_PROTOCOLO', 'padrao': ('ri_frases', 'RI_PRENOTACOES_ABERTAS_ITEM_PROTOCOLO'), 'elementos_comuns': False},
    {'chave': 'RI_PRENOTACOES_ABERTAS_ITEM_DATA', 'padrao': ('ri_frases', 'RI_PRENOTACOES_ABERTAS_ITEM_DATA'), 'elementos_comuns': False},
    {'chave': 'RI_PRENOTACOES_ABERTAS_ITEM_NATUREZA', 'padrao': ('ri_frases', 'RI_PRENOTACOES_ABERTAS_ITEM_NATUREZA'), 'elementos_comuns': False},
    {'chave': 'RI_PRENOTACOES_ABERTAS_ITEM_OBJETO', 'padrao': ('ri_frases', 'RI_PRENOTACOES_ABERTAS_ITEM_OBJETO'), 'elementos_comuns': False},
    {'chave': 'RI_ENCERRAMENTO_TECNICA', 'padrao': ('ri_frases', 'RI_ENCERRAMENTO_TECNICA'), 'elementos_comuns': False},
    {'chave': 'RI_ENCERRAMENTO_DESMEMBRAMENTO', 'padrao': ('ri_frases', 'RI_ENCERRAMENTO_DESMEMBRAMENTO'), 'elementos_comuns': False},
    {'chave': 'RI_ENCERRAMENTO_UNIFICACAO', 'padrao': ('ri_frases', 'RI_ENCERRAMENTO_UNIFICACAO'), 'elementos_comuns': False},
    {'chave': 'RI_ENCERRAMENTO_CIRCUNSCRICAO', 'padrao': ('ri_frases', 'RI_ENCERRAMENTO_CIRCUNSCRICAO'), 'elementos_comuns': False},
    {'chave': 'RI_ENCERRAMENTO_LIVRE', 'padrao': ('ri_frases', 'RI_ENCERRAMENTO_LIVRE'), 'elementos_comuns': False},
    {'chave': 'RI_ENCERRAMENTO_FECHO', 'padrao': ('ri_frases', 'RI_ENCERRAMENTO_FECHO'), 'elementos_comuns': False},
    {'chave': 'RI_ENCERRAMENTO_FECHO_SEM_TITULO', 'padrao': ('ri_frases', 'RI_ENCERRAMENTO_FECHO_SEM_TITULO'), 'elementos_comuns': False},
    {'chave': 'RI_ENCERRAMENTO_FECHO_SEM_NOME', 'padrao': ('ri_frases', 'RI_ENCERRAMENTO_FECHO_SEM_NOME'), 'elementos_comuns': False},
    {'chave': 'RI_NEGATIVA_CRITERIO_DOCUMENTO', 'padrao': ('ri_frases', 'RI_NEGATIVA_CRITERIO_DOCUMENTO'), 'elementos_comuns': False},
    {'chave': 'RI_NEGATIVA_CRITERIO_NOME', 'padrao': ('ri_frases', 'RI_NEGATIVA_CRITERIO_NOME'), 'elementos_comuns': False},
    {'chave': 'RI_NEGATIVA_CRITERIO_IMOVEL', 'padrao': ('ri_frases', 'RI_NEGATIVA_CRITERIO_IMOVEL'), 'elementos_comuns': False},
    # -- LF06B grupo B (ri_digitalizacao, atrib_certidao, atribuicoes_web, ri_onus_ia)
    {'chave': 'RI_REPROGRAFICA_FECHO', 'padrao': ('ri_frases', 'RI_REPROGRAFICA_FECHO'), 'elementos_comuns': False},
    {'chave': 'RI_REPROGRAFICA_CAPA', 'padrao': ('ri_frases', 'RI_REPROGRAFICA_CAPA'), 'elementos_comuns': False},
    # LH02 (21/10/2026): o fecho impresso do modelo da casa da reprográfica.
    {'chave': 'RI_REPROGRAFICA_FECHO_DO_PAPEL', 'padrao': ('ri_frases', 'RI_REPROGRAFICA_FECHO_DO_PAPEL'), 'elementos_comuns': False},
    {'chave': 'RI_LIVRO3_REPRODUCAO', 'padrao': ('ri_frases', 'RI_LIVRO3_REPRODUCAO'), 'elementos_comuns': False},
    {'chave': 'RI_LIVRO3_SEM_ATOS', 'padrao': ('ri_frases', 'RI_LIVRO3_SEM_ATOS'), 'elementos_comuns': False},
    {'chave': 'RI_ONUS_TITULO', 'padrao': ('ri_frases', 'RI_ONUS_TITULO'), 'elementos_comuns': False},
    # -- LF06B grupo C (atos que vão ao livro)
    {'chave': 'RI_CANCELAMENTO_INDICADOR_REAL', 'padrao': ('ri_frases', 'RI_CANCELAMENTO_INDICADOR_REAL'), 'elementos_comuns': False},
    {'chave': 'RI_CANCELAMENTO_INDICADOR_PESSOAL', 'padrao': ('ri_frases', 'RI_CANCELAMENTO_INDICADOR_PESSOAL'), 'elementos_comuns': False},
    {'chave': 'RI_CANCELAMENTO_INDICADOR_PESSOAL_SEM_PARTES', 'padrao': ('ri_frases', 'RI_CANCELAMENTO_INDICADOR_PESSOAL_SEM_PARTES'), 'elementos_comuns': False},
    {'chave': 'RI_LIVRO3_CANCELAMENTO_INDICADOR_REAL', 'padrao': ('ri_frases', 'RI_LIVRO3_CANCELAMENTO_INDICADOR_REAL'), 'elementos_comuns': False},
    {'chave': 'RI_LIVRO3_CANCELAMENTO_INDICADOR_PESSOAL', 'padrao': ('ri_frases', 'RI_LIVRO3_CANCELAMENTO_INDICADOR_PESSOAL'), 'elementos_comuns': False},
    {'chave': 'RI_LIVRO3_CANCELAMENTO_INDICADOR_PESSOAL_SEM_PARTES', 'padrao': ('ri_frases', 'RI_LIVRO3_CANCELAMENTO_INDICADOR_PESSOAL_SEM_PARTES'), 'elementos_comuns': False},
    {'chave': 'RI_LIVRO3_CANCELAMENTO', 'padrao': ('ri_frases', 'RI_LIVRO3_CANCELAMENTO'), 'elementos_comuns': False},
    {'chave': 'RI_ATA_EXPURGO', 'padrao': ('ri_frases', 'RI_ATA_EXPURGO'), 'elementos_comuns': False},
    {'chave': 'RI_LIVRO3_ATA_EXPURGO', 'padrao': ('ri_frases', 'RI_LIVRO3_ATA_EXPURGO'), 'elementos_comuns': False},
    {'chave': 'RI_MINUTA_PROTOCOLO', 'padrao': ('ri_frases', 'RI_MINUTA_PROTOCOLO'), 'elementos_comuns': False},
    # -- LF06B grupo D (ri_odt, ra_ficha_odt, ri_schema)
    {'chave': 'RI_MINUTA_IMOVEL', 'padrao': ('ri_frases', 'RI_MINUTA_IMOVEL'), 'elementos_comuns': False},
    {'chave': 'RI_MINUTA_IMOVEL_AREA', 'padrao': ('ri_frases', 'RI_MINUTA_IMOVEL_AREA'), 'elementos_comuns': False},
    {'chave': 'RI_LIVRO3_CERTIDAO_TITULO', 'padrao': ('ri_frases', 'RI_LIVRO3_CERTIDAO_TITULO'), 'elementos_comuns': False},
    {'chave': 'RI_LIVRO3_CERTIDAO_CANCELADA', 'padrao': ('ri_frases', 'RI_LIVRO3_CERTIDAO_CANCELADA'), 'elementos_comuns': False},
    {'chave': 'RI_LIVRO3_CERTIDAO_FECHO', 'padrao': ('ri_frases', 'RI_LIVRO3_CERTIDAO_FECHO'), 'elementos_comuns': False},
    {'chave': 'RI_NEGATIVA_CRITERIO_BAIRRO', 'padrao': ('ri_frases', 'RI_NEGATIVA_CRITERIO_BAIRRO'), 'elementos_comuns': False},
    {'chave': 'RI_PRENOTACAO_PRAZO_SUSPENSO', 'padrao': ('ri_frases', 'RI_PRENOTACAO_PRAZO_SUSPENSO'), 'elementos_comuns': False},
    {'chave': 'RI_ENCERRAMENTO_DIRETO', 'padrao': ('ri_frases', 'RI_ENCERRAMENTO_DIRETO'), 'elementos_comuns': False},
    {'chave': 'RI_ENCERRAMENTO_DIRETO_DESTINO', 'padrao': ('ri_frases', 'RI_ENCERRAMENTO_DIRETO_DESTINO'), 'elementos_comuns': False},
    {'chave': 'RI_CANCELAMENTO_DO_ATO', 'padrao': ('ri_frases', 'RI_CANCELAMENTO_DO_ATO'), 'elementos_comuns': False},
    {'chave': 'RI_REPROGRAFICA_VALIDADE', 'padrao': ('ri_frases', 'RI_REPROGRAFICA_VALIDADE'), 'elementos_comuns': False},
    {'chave': 'RI_FECHO_DO_ATO', 'padrao': ('ri_frases', 'RI_FECHO_DO_ATO'), 'elementos_comuns': False},
    {'chave': 'RI_FECHO_DO_ATO_SEM_TITULO', 'padrao': ('ri_frases', 'RI_FECHO_DO_ATO_SEM_TITULO'), 'elementos_comuns': False},
    {'chave': 'RI_FECHO_DA_ABERTURA', 'padrao': ('ri_frases', 'RI_FECHO_DA_ABERTURA'), 'elementos_comuns': False},
)
