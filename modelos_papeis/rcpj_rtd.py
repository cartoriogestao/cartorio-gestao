"""Papéis do catálogo — RCPJ e RTD."""
from __future__ import annotations

PASTA = "rcpj_rtd"
ATRIBUICAO = "RCPJ e RTD"

PAPEIS: tuple[dict, ...] = (
    {'chave': 'RCPJ_CERTIDAO', 'padrao': ('atrib_certidao', 'MODELO_CERTIDAO_RCPJ_RTD')},
    {'chave': 'RTD_CERTIDAO', 'padrao': ('atrib_certidao', 'MODELO_CERTIDAO_RCPJ_RTD')},
    {'chave': 'RCPJ_TEOR_AVERBACAO', 'padrao': ('rg_teor_rtdpj', 'MODELO_RCPJ_TEOR_AVERBACAO')},
    {'chave': 'RCPJ_TEOR_REGISTRO', 'padrao': ('rg_teor_rtdpj', 'MODELO_RCPJ_TEOR_REGISTRO')},
    {'chave': 'RTD_TEOR_AVERBACAO', 'padrao': ('rg_teor_rtdpj', 'MODELO_RTD_TEOR_AVERBACAO')},
    {'chave': 'RTD_TEOR_REGISTRO', 'padrao': ('rg_teor_rtdpj', 'MODELO_RTD_TEOR_REGISTRO')},
    {'chave': 'RCPJ_CERTIDAO_CAPA', 'padrao': ('rg_certidao_pdf', 'MODELO_RCPJ_CERTIDAO_CAPA')},
    {'chave': 'RTD_CERTIDAO_CAPA', 'padrao': ('rg_certidao_pdf', 'MODELO_RTD_CERTIDAO_CAPA')},
    {'chave': 'RCPJ_CERTIDAO_FAIXA', 'padrao': ('rg_certidao_pdf', 'MODELO_RCPJ_CERTIDAO_FAIXA')},
    {'chave': 'RTD_CERTIDAO_FAIXA', 'padrao': ('rg_certidao_pdf', 'MODELO_RTD_CERTIDAO_FAIXA')},
    # LF06F (19/10/2026): os papéis do RCPJ/RTD que ainda moravam no código —
    # a certidão só de averbações (que não tinha chave), o papel por texto, a
    # nota devolutiva e as etiquetas (que eram templates) e as frases do
    # desenho dos PDFs. Os quatro em Jinja/HTML não herdam o encerramento da
    # atribuição: ela é toda em chaves, e o fecho comum não cabe numa etiqueta.
    {'chave': 'RCPJ_RTD_CERTIDAO_SO_AVERBACOES', 'padrao': ('atrib_certidao', 'MODELO_CERTIDAO_RCPJ_RTD_SO_AVERBACOES')},
    {'chave': 'RCPJ_RTD_CERTIDAO_ODT', 'padrao': ('atrib_certidao', 'MODELO_CERTIDAO_RCPJ_RTD_ODT'), 'elementos_comuns': False},
    {'chave': 'RCPJ_RTD_NOTA', 'padrao': ('rg_web', 'MODELO_NOTA_DEVOLUTIVA'), 'elementos_comuns': False},
    {'chave': 'RCPJ_RTD_ETIQUETA', 'padrao': ('rg_web', 'MODELO_ETIQUETA_DE_REGISTRO'), 'elementos_comuns': False},
    {'chave': 'RCPJ_RTD_ETIQUETA_SELO_EXTERNO', 'padrao': ('rg_web', 'MODELO_ETIQUETA_DE_SELO_EXTERNO'), 'elementos_comuns': False},
    {'chave': 'RCPJ_RTD_PDF_MOLDURA', 'padrao': ('rg_teor_rtdpj', 'MOLDURA_DOS_PDFS'), 'elementos_comuns': False},
    # LG04 (19/10/2026): a certidão da notificação extrajudicial do RTD
    # (positiva e negativa, CN-MA arts. 986 a 993) e os termos e a certidão da
    # autenticação de livro do RCPJ. Sem precedente de texto no E-Ofício, e
    # afirmação jurídica em papel assinado — o texto é do oficial.
    {'chave': 'RTD_CERTIDAO_NOTIFICACAO_POSITIVA', 'padrao': ('rg_notificacao', 'MODELO_CERTIDAO_NOTIFICACAO_POSITIVA')},
    {'chave': 'RTD_CERTIDAO_NOTIFICACAO_NEGATIVA', 'padrao': ('rg_notificacao', 'MODELO_CERTIDAO_NOTIFICACAO_NEGATIVA')},
    {'chave': 'RCPJ_LIVRO_CONTABIL_TERMO_ABERTURA', 'padrao': ('rg_livro_contabil', 'MODELO_RCPJ_LIVRO_CONTABIL_TERMO_ABERTURA')},
    {'chave': 'RCPJ_LIVRO_CONTABIL_TERMO_ENCERRAMENTO', 'padrao': ('rg_livro_contabil', 'MODELO_RCPJ_LIVRO_CONTABIL_TERMO_ENCERRAMENTO')},
    {'chave': 'RCPJ_LIVRO_CONTABIL_CERTIDAO', 'padrao': ('rg_livro_contabil', 'MODELO_RCPJ_LIVRO_CONTABIL_CERTIDAO')},
    # LD05 (21/10/2026): o termo do cancelamento — o único ato do livro sem
    # termo datado e assinado (LRP art. 165; CN-MA art. 994, § 1º). Afirmação
    # do oficial em papel assinado, sem precedente de texto no E-Ofício: vai ao
    # catálogo, como os outros quatro teores do RCPJ/RTD.
    {'chave': 'RCPJ_TEOR_CANCELAMENTO', 'padrao': ('rg_teor_rtdpj', 'MODELO_RCPJ_TEOR_CANCELAMENTO')},
    {'chave': 'RTD_TEOR_CANCELAMENTO', 'padrao': ('rg_teor_rtdpj', 'MODELO_RTD_TEOR_CANCELAMENTO')},
    # LD05: a certidão negativa do RTD e do RCPJ (serviços 314 e 315 da casa),
    # que não existia — a casa só certificava um registro que existe.
    {'chave': 'RCPJ_RTD_CERTIDAO_NEGATIVA', 'padrao': ('atrib_certidao', 'MODELO_CERTIDAO_NEGATIVA_RCPJ_RTD')},
    # LD05: a certidão do RCPJ em breve relato (CN-MA art. 420, II) — a casa só
    # emitia o inteiro teor.
    {'chave': 'RCPJ_CERTIDAO_BREVE_RELATO', 'padrao': ('atrib_certidao', 'MODELO_CERTIDAO_BREVE_RELATO_RCPJ')},
)
