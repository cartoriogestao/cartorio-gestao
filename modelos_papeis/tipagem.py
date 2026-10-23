"""Tipagem ABCM dos papéis."""
from __future__ import annotations

TIPOS_POR_CHAVE: dict[str, tuple[str, str | None]] = {'RI_CABECALHO': ('TEXTO', None), 'RI_FICHA': ('MOLDE_ODT', 'Ficha da matrícula em XML/ODT (ri_odt)'), 'RI_CERTIDAO': ('MOLDE_ODT', 'Molde comum das certidões RI (ri_odt)'), 'RI_CERTIDAO_INTEIRO_TEOR': ('TEXTO', 'Miolo — não é o molde inteiro'), 'RI_CERTIDAO_ONUS': ('TEXTO', 'Miolo — não é o molde inteiro'), 'RI_CERTIDAO_PROPRIEDADE': ('TEXTO', 'Miolo — não é o molde inteiro'), 'RI_CERTIDAO_DOMINIAL': ('TEXTO', 'Miolo — não é o molde inteiro'), 'RI_CERTIDAO_VINTENARIA': ('TEXTO', 'Miolo — não é o molde inteiro'), 'RI_CERTIDAO_NEGATIVA_IMOVEL':('TEXTO', 'Molde inteiro da negativa de imóvel'), 'RI_NOTA': ('TEXTO', None), 'RI_PRENOTACAO': ('TEXTO', None), 'RI_LIVRO3_CERTIDAO': ('TEXTO', None), 'RI_LIVRO3_FICHA': ('TEXTO', None), 'CAIXA_RECIBO': ('TEXTO', None), 'CAIXA_ORCAMENTO': ('TEXTO', None), 'CAIXA_RECEPCAO': ('TEXTO', None), 'NOTAS_TRASLADO': ('TEXTO', None), 'NOTAS_TERMO_LIVRO': ('TEXTO', None), 'NOTAS_CARTAO_FICHA': ('TEXTO', None), 'RCPJ_CERTIDAO': ('TEXTO', 'Texto congelado em at_certidoes na emissão'), 'RTD_CERTIDAO': ('TEXTO', 'Texto congelado em at_certidoes na emissão'), 'RCPJ_TEOR_AVERBACAO': ('TEXTO', None), 'RCPJ_TEOR_REGISTRO': ('TEXTO', None), 'RTD_TEOR_AVERBACAO': ('TEXTO', None), 'RTD_TEOR_REGISTRO': ('TEXTO', None), 'RCPJ_CERTIDAO_CAPA': ('TEXTO', 'Fragmento de capa PDF'), 'RTD_CERTIDAO_CAPA': ('TEXTO', 'Fragmento de capa PDF'), 'RCPJ_CERTIDAO_FAIXA': ('TEXTO', 'Fragmento de faixa PDF'), 'RTD_CERTIDAO_FAIXA': ('TEXTO', 'Fragmento de faixa PDF'), 'RC_TERMO_NASCIMENTO': ('TEXTO', 'Marcadores {chave} do livro'), 'RC_TERMO_CASAMENTO': ('TEXTO', 'Marcadores {chave} do livro'), 'RC_TERMO_OBITO': ('TEXTO', 'Marcadores {chave} do livro'), 'RC_TERMO_LIVRO_E': ('TEXTO', 'Marcadores {chave} do livro'), 'PT_TERMO_PROTESTO': ('TEXTO', None), 'PT_INSTRUMENTO_PROTESTO': ('TEXTO', None), 'PT_CERTIDAO_NEGATIVA': ('TEXTO', None), 'NOTAS_CERTIDAO_INTEIRO_TEOR': ('TEXTO', None), 'NOTAS_CERTIDAO_POSITIVA': ('TEXTO', None), 'NOTAS_CERTIDAO_NEGATIVA': ('TEXTO', None), 'PT_CERTIDAO_POSITIVA': ('TEXTO', None), 'PT_CERTIDAO_CANCELAMENTO': ('TEXTO', None)}

# AS NOTAS (LF06D, 19/10/2026). Linha à parte, como as do LF06G e do
# LF06B: cada lote acrescenta os seus papéis sem tocar na linha do vizinho.
TIPOS_POR_CHAVE.update({
    'NOTAS_RECONHECIMENTO_SEMELHANCA': ('TEXTO', 'Fórmula da etiqueta (notas_schema)'),
    'NOTAS_RECONHECIMENTO_AUTENTICIDADE': ('TEXTO', 'Fórmula da etiqueta (notas_schema)'),
    'NOTAS_RECONHECIMENTO_SINAL': ('TEXTO', 'Fórmula do sinal público (notas_schema)'),
    'NOTAS_AUTENTICACAO': ('TEXTO', 'Texto congelado em nt_autenticacoes'),
    'NOTAS_AUTENTICACAO_INTERNET': ('TEXTO', 'Texto congelado em nt_autenticacoes'),
    'NOTAS_ETIQUETA_FECHO': ('TEXTO', 'Fecho acrescido na impressão da etiqueta'),
    'NOTAS_TERMO_COMPARECIMENTO': ('TEXTO', 'Gravado em nt_presencas.conteudo'),
    'NOTAS_LIVRO_ABERTURA': ('TEXTO', 'Texto congelado em nt_livros.termo_abertura'),
    'NOTAS_LIVRO_ENCERRAMENTO': ('TEXTO', 'Texto congelado em nt_livros.termo_encerramento'),
    'NOTAS_INUTILIZACAO': ('TEXTO', 'Dizer da face inutilizada'),
    'NOTAS_INUTILIZACAO_FACE': ('TEXTO', 'Folha impressa da face inutilizada'),
    'NOTAS_ANOTACAO_MARGEM': ('TEXTO', 'Texto congelado em nt_ato_anotacoes'),
    'NOTAS_ABERTURA_ESCRITURA': ('TEXTO', 'Pedaço do teor (notas_teor.montar)'),
    'NOTAS_ABERTURA_PROCURACAO': ('TEXTO', 'Pedaço do teor (notas_teor.montar)'),
    'NOTAS_ABERTURA_SUBSTABELECIMENTO': ('TEXTO', 'Pedaço do teor (notas_teor.montar)'),
    'NOTAS_ABERTURA_REVOGACAO': ('TEXTO', 'Pedaço do teor (notas_teor.montar)'),
    'NOTAS_ABERTURA_ATA': ('TEXTO', 'Pedaço do teor (notas_teor.montar)'),
    'NOTAS_FECHO_ESCRITURA': ('TEXTO', 'Pedaço do teor (notas_teor.montar)'),
    'NOTAS_FECHO_PROCURACAO': ('TEXTO', 'Pedaço do teor (notas_teor.montar)'),
    'NOTAS_FECHO_SUBSTABELECIMENTO': ('TEXTO', 'Pedaço do teor (notas_teor.montar)'),
    'NOTAS_FECHO_REVOGACAO': ('TEXTO', 'Pedaço do teor (notas_teor.montar)'),
    'NOTAS_FECHO_ATA': ('TEXTO', 'Pedaço do teor (notas_teor.montar)'),
    'NOTAS_QUALIFICACAO_PF': ('MONTADO_POR_CAMPO', 'Qualificação da parte (notas_teor.qualificar)'),
    'NOTAS_QUALIFICACAO_PJ': ('MONTADO_POR_CAMPO', 'Qualificação da parte (notas_teor.qualificar)'),
    'NOTAS_TRASLADO_CABECALHO': ('TEXTO', 'Cabeçalho das páginas 2+ do traslado'),
})

# A RETIFICAÇÃO E A USUCAPIÃO (LF06G, 19/10/2026). Linha à parte, e não dentro
# do dicionário de cima: cada lote do LF06 acrescenta os seus papéis, e uma
# linha só de quarenta chaves faria cada acréscimo colidir com o do vizinho.
TIPOS_POR_CHAVE.update({
    'RT_NOTIFICACAO_CONFRONTANTE': ('TEXTO', 'Texto congelado em rt_confrontantes ao notificar'),
    'US_NOTIFICACAO': ('TEXTO', 'Texto congelado em us_movimentos ao expedir'),
    'US_EDITAL': ('TEXTO', 'Texto congelado em us_movimentos ao montar'),
    'US_OFICIO_AO_ENTE': ('TEXTO', 'Texto congelado em us_movimentos ao montar'),
    'US_DECISAO_PROCEDENTE': ('TEXTO', 'Sugestão: o oficial completa, e o teor congela em us_decisoes'),
    'US_DECISAO_IMPROCEDENTE': ('TEXTO', 'Sugestão: o oficial completa, e o teor congela em us_decisoes'),
    'US_DECISAO_EXIGENCIA': ('TEXTO', 'Sugestão: o oficial completa, e o teor congela em us_decisoes'),
    'US_DECISAO_REMESSA_JUIZO': ('TEXTO', 'Sugestão: o oficial completa, e o teor congela em us_decisoes'),
    'US_DOSSIE_PEDIDO': ('TEXTO', 'Trecho do dossiê que vai a quem analisa; o resto é o processo listado'),
})

# LF06F (19/10/2026): RCPJ/RTD e Caixa. Bloco à parte, pelo mesmo motivo dos
# de cima — os lotes do LF06 acrescentam juntos.
TIPOS_POR_CHAVE.update({
    'RCPJ_RTD_CERTIDAO_SO_AVERBACOES': ('TEXTO', 'Texto congelado em at_certidoes na emissão'),
    'RCPJ_RTD_CERTIDAO_ODT': ('MOLDE_ODT', 'Papel da certidão por texto (HTML que vira .odt)'),
    'RCPJ_RTD_NOTA': ('TEXTO', None),
    'RCPJ_RTD_ETIQUETA': ('TEXTO', 'Tira térmica 100×30 mm (HTML)'),
    'RCPJ_RTD_ETIQUETA_SELO_EXTERNO': ('TEXTO', 'Tira térmica 100×30 mm (HTML)'),
    'RCPJ_RTD_PDF_MOLDURA': ('TEXTO', 'Frases curtas do desenho dos PDFs, por ===PARTE==='),
    'CAIXA_WHATSAPP': ('TEXTO', 'Rascunho por assunto (===PARTE===), conferido antes de enviar'),
})

# LG04 (19/10/2026): os papéis dos atos novos — a certidão da notificação do
# RTD, os termos e a certidão da autenticação de livro do RCPJ e a pública
# forma das Notas. Bloco à parte, pelo motivo dos de cima.
TIPOS_POR_CHAVE.update({
    'RTD_CERTIDAO_NOTIFICACAO_POSITIVA': ('TEXTO', 'Teor congelado em rg_notificacao_certidoes na emissão'),
    'RTD_CERTIDAO_NOTIFICACAO_NEGATIVA': ('TEXTO', 'Teor congelado em rg_notificacao_certidoes na emissão'),
    'RCPJ_LIVRO_CONTABIL_TERMO_ABERTURA': ('TEXTO', 'Congelado em rg_livros_contabeis na autenticação'),
    'RCPJ_LIVRO_CONTABIL_TERMO_ENCERRAMENTO': ('TEXTO', 'Congelado em rg_livros_contabeis na autenticação'),
    'RCPJ_LIVRO_CONTABIL_CERTIDAO': ('TEXTO', 'Montada do que a autenticação congelou'),
    'NOTAS_PUBLICA_FORMA': ('TEXTO', 'Teor congelado em nt_publicas_formas na emissão'),
})

# LD05 (21/10/2026): o termo do cancelamento do RCPJ/RTD. Bloco à parte, pelo
# motivo dos de cima.
TIPOS_POR_CHAVE.update({
    'RCPJ_TEOR_CANCELAMENTO': ('TEXTO', None),
    'RTD_TEOR_CANCELAMENTO': ('TEXTO', None),
    'RCPJ_RTD_CERTIDAO_NEGATIVA': ('TEXTO', 'Texto congelado em at_certidoes na emissão'),
    'RCPJ_CERTIDAO_BREVE_RELATO': ('TEXTO', 'Texto congelado em at_certidoes na emissão'),
})

# LF06B (19/10/2026): as frases do Registro de Imóveis que saíram do código
# (`ri_frases.py`). Uma linha por papel, para o diff mostrar qual entrou.
TIPOS_POR_CHAVE.update({
    # -- LF06B grupo A
    'RI_PRENOTACOES_ABERTAS_NAO_HA': ('TEXTO', 'Frase de clausula_html_prenotacoes_abertas (LF06B)'),
    'RI_PRENOTACOES_ABERTAS_HA_UMA': ('TEXTO', 'Frase de clausula_html_prenotacoes_abertas (LF06B)'),
    'RI_PRENOTACOES_ABERTAS_HA_VARIAS': ('TEXTO', 'Frase de clausula_html_prenotacoes_abertas (LF06B)'),
    'RI_PRENOTACOES_ABERTAS_ITEM_PROTOCOLO': ('TEXTO', 'Frase de clausula_html_prenotacoes_abertas (LF06B)'),
    'RI_PRENOTACOES_ABERTAS_ITEM_DATA': ('TEXTO', 'Frase de clausula_html_prenotacoes_abertas (LF06B)'),
    'RI_PRENOTACOES_ABERTAS_ITEM_NATUREZA': ('TEXTO', 'Frase de clausula_html_prenotacoes_abertas (LF06B)'),
    'RI_PRENOTACOES_ABERTAS_ITEM_OBJETO': ('TEXTO', 'Frase de clausula_html_prenotacoes_abertas (LF06B)'),
    'RI_ENCERRAMENTO_TECNICA': ('TEXTO', 'Frase de modelos_de_encerramento (LF06B)'),
    'RI_ENCERRAMENTO_DESMEMBRAMENTO': ('TEXTO', 'Frase de modelos_de_encerramento (LF06B)'),
    'RI_ENCERRAMENTO_UNIFICACAO': ('TEXTO', 'Frase de modelos_de_encerramento (LF06B)'),
    'RI_ENCERRAMENTO_CIRCUNSCRICAO': ('TEXTO', 'Frase de modelos_de_encerramento (LF06B)'),
    'RI_ENCERRAMENTO_LIVRE': ('TEXTO', 'Frase de modelos_de_encerramento (LF06B)'),
    'RI_ENCERRAMENTO_FECHO': ('TEXTO', 'Frase de modelos_de_encerramento (LF06B)'),
    'RI_ENCERRAMENTO_FECHO_SEM_TITULO': ('TEXTO', 'Frase de modelos_de_encerramento (LF06B)'),
    'RI_ENCERRAMENTO_FECHO_SEM_NOME': ('TEXTO', 'Frase de modelos_de_encerramento (LF06B)'),
    'RI_NEGATIVA_CRITERIO_DOCUMENTO': ('TEXTO', 'Frase de montar_identificacao (LF06B)'),
    'RI_NEGATIVA_CRITERIO_NOME': ('TEXTO', 'Frase de montar_identificacao (LF06B)'),
    'RI_NEGATIVA_CRITERIO_IMOVEL': ('TEXTO', 'Frase de montar_identificacao (LF06B)'),
    # -- LF06B grupo B
    'RI_REPROGRAFICA_FECHO': ('TEXTO', 'Frase de ri_digitalizacao.corpo_resumo_digitalizacao (LF06B)'),
    'RI_REPROGRAFICA_CAPA': ('TEXTO', 'Frase de ri_digitalizacao.odt_da_digitalizacao (LF06B)'),
    'RI_LIVRO3_REPRODUCAO': ('TEXTO', 'Frase de atrib_certidao.corpo_por_reproducao (LF06B)'),
    'RI_LIVRO3_SEM_ATOS': ('TEXTO', 'Frase de atrib_certidao._bloco_atos_certidao_livro3 (LF06B)'),
    'RI_ONUS_TITULO': ('TEXTO', 'Frase de ri_onus_ia.titulo (LF06B)'),
    # -- LF06B grupo C
    'RI_CANCELAMENTO_INDICADOR_REAL': ('TEXTO', 'Frase de Indicador Real, cancelamento de ato do Livro 2 (ri_indicador_lancamentos), congelada no livro (LF06B)'),
    'RI_CANCELAMENTO_INDICADOR_PESSOAL': ('TEXTO', 'Frase de Indicador Pessoal, cancelamento de ato do Livro 2 (ri_indicador_lancamentos), congelada no livro (LF06B)'),
    'RI_CANCELAMENTO_INDICADOR_PESSOAL_SEM_PARTES': ('TEXTO', 'Frase de Indicador Pessoal sem partes, Livro 2 (ri_indicador_lancamentos), congelada no livro (LF06B)'),
    'RI_LIVRO3_CANCELAMENTO_INDICADOR_REAL': ('TEXTO', 'Frase de Indicador Real, cancelamento do Livro 3 (ri_indicador_lancamentos), congelada no livro (LF06B)'),
    'RI_LIVRO3_CANCELAMENTO_INDICADOR_PESSOAL': ('TEXTO', 'Frase de Indicador Pessoal, cancelamento do Livro 3 (ri_indicador_lancamentos), congelada no livro (LF06B)'),
    'RI_LIVRO3_CANCELAMENTO_INDICADOR_PESSOAL_SEM_PARTES': ('TEXTO', 'Frase de Indicador Pessoal sem partes, Livro 3 (ri_indicador_lancamentos), congelada no livro (LF06B)'),
    'RI_LIVRO3_CANCELAMENTO': ('TEXTO', 'Frase de averbação de cancelamento do Livro 3 (ra_registro), congelada no livro (LF06B)'),
    'RI_ATA_EXPURGO': ('TEXTO', 'Frase de ata do expurgo do Livro 2 (ri_expurgo), congelada no livro (LF06B)'),
    'RI_LIVRO3_ATA_EXPURGO': ('TEXTO', 'Frase de ata do expurgo do Livro 3 (ra_expurgo), congelada no livro (LF06B)'),
    'RI_MINUTA_PROTOCOLO': ('TEXTO', 'Frase do protocolo na parte fixa das minutas e da averbação da CNIB, congelada no livro (LF06B)'),
    # -- LF06B grupo D
    'RI_MINUTA_IMOVEL': ('TEXTO', 'Frase da parte fixa das minutas de ato (LF06B)'),
    'RI_MINUTA_IMOVEL_AREA': ('TEXTO', 'Frase da parte fixa das minutas de ato (LF06B)'),
    'RI_LIVRO3_CERTIDAO_TITULO': ('TEXTO', 'Frase da certidão do Livro 3 impressa (LF06B)'),
    'RI_LIVRO3_CERTIDAO_CANCELADA': ('TEXTO', 'Frase da certidão do Livro 3 impressa (LF06B)'),
    'RI_LIVRO3_CERTIDAO_FECHO': ('TEXTO', 'Fecho da certidão do Livro 3 impressa (LF06B)'),
    'RI_NEGATIVA_CRITERIO_BAIRRO': ('TEXTO', 'Frase da rota da negativa de imóvel (LF06B)'),
    'RI_PRENOTACAO_PRAZO_SUSPENSO': ('TEXTO', 'Frase do comprovante de prenotação (LF06B)'),
    'RI_ENCERRAMENTO_DIRETO': ('TEXTO', 'Frase do encerramento direto, congelada no livro (LF06B)'),
    'RI_ENCERRAMENTO_DIRETO_DESTINO': ('TEXTO', 'Frase do encerramento direto, congelada no livro (LF06B)'),
    'RI_CANCELAMENTO_DO_ATO': ('TEXTO', 'Frase do cancelamento de ato, congelada no livro (LF06B)'),
    'RI_REPROGRAFICA_VALIDADE': ('TEXTO', 'Frase da certidão reprográfica, congelada no hash (LF06B)'),
    'RI_FECHO_DO_ATO': ('TEXTO', 'Frase do fecho de cada ato, na ficha e na certidão (LF06B)'),
    'RI_FECHO_DO_ATO_SEM_TITULO': ('TEXTO', 'Frase do fecho do ato sem a função (LF06B)'),
    'RI_FECHO_DA_ABERTURA': ('TEXTO', 'Frase do fecho da abertura da matrícula (LF06B)'),
})

# LH02 (21/10/2026): o fecho impresso da certidão reprográfica no modelo da
# casa. A `RI_REPROGRAFICA_CAPA`, acima, virou o CERTIFICO e a ressalva dele.
TIPOS_POR_CHAVE.update({
    'RI_REPROGRAFICA_FECHO_DO_PAPEL': ('TEXTO', 'Frase de ri_digitalizacao.odt_da_digitalizacao, modelo da casa (LH02)'),
})

# LF06C (19/10/2026): os papéis do Registro Civil que eram montados no código.
TIPOS_POR_CHAVE.update({
    'RC_QUALIFICACAO': ('TEXTO', 'Ordem da qualificação nos termos; as frases são peças'),
    'RC_CERTIDAO_RESUMO': ('TEXTO', 'Fecho do teor congelado em rc_certidoes na emissão'),
    'RC_CERTIDAO_INTEIRO_TEOR': ('TEXTO', 'Introdução congelada em rc_certidoes na emissão'),
    'RC_ANOTACAO_CRC_COMPACTA': ('TEXTO', 'Sugestão de anotação a partir da comunicação da CRC'),
    'RC_ANOTACAO_CRC_COMPLETA': ('TEXTO', 'Sugestão de anotação a partir da comunicação da CRC'),
    'RC_ANOTACAO_CRC_FE_PUBLICA': ('TEXTO', 'Sugestão de anotação a partir da comunicação da CRC'),
    'RC_AVERBACAO_RETIFICACAO': ('TEXTO', 'Sugestão editável; vai a rc_atos.teor ao lançar'),
    'RC_COMUNICACAO_OBITOS': ('TEXTO', 'Congelado em rc_comunicacoes com hash no envio'),
    'RC_OFICIO_FUNAI': ('TEXTO', 'Congelado em rc_funai com hash no envio'),
    'RC_EDITAL_PROCLAMAS': ('TEXTO', 'Teor oferecido; o publicado congela em hc_habilitacoes'),
    'RC_EDITAL_PROCLAMAS_FOLHA': ('TEXTO', 'Folha do edital; remontada na impressão'),
    'RC_CERTIDAO_HABILITACAO': ('TEXTO', 'Remontada na impressão'),
})

# LD02 (21/10/2026): a certidão das Notas em breve relato — a cópia resumida
# do art. 851. Bloco à parte, pelo motivo dos de cima.
TIPOS_POR_CHAVE.update({
    'NOTAS_CERTIDAO_BREVE_RELATO': ('TEXTO', 'Texto congelado em nt_certidoes na emissão'),
})
