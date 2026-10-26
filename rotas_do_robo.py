# -*- coding: utf-8 -*-
"""AS ROTAS QUE O ROBÔ ALCANÇA — e só elas (revisão de segurança, 26/10/2026).

POR QUE EXISTE
    Até aqui a guarda do robô era uma lista de VEDADAS por prefixo de rota
    (`selo_robo.ROTAS_VEDADAS_AO_ROBO`, A6 de 22/10/2026). Ela não cobria rota
    nova por padrão: cinco PRs abertos em 26/10 (#11, #13, #21, #22, #30)
    traziam rotas novas que o robô alcançaria sem ninguém ter decidido isso. A
    revisão de segurança mandou inverter: **o robô só entra no que está nesta
    lista; fora dela, 403.** A lista das vedadas continua valendo, como segunda
    trava: vedada vence permitida.

DE ONDE SAIU CADA ENTRADA — medido, e não suposto
    Não há registro de acesso por rota nesta casa (o `waitress` não guarda, e
    `audit_logs` guarda ação, e não endereço). Por isso a medição foi no
    CÓDIGO do `main` (commit b89252d): os robôs da casa (o «Grok Bot», o «Robo
    Nascimento RCPN», papel USER ou AUDITOR — `database.create_user` recusa
    outro) operam pelo NAVEGADOR, como o balcão, e não por cliente HTTP próprio
    — não há um único cliente HTTP no repositório que entre no sistema com
    login. O que prova onde eles trabalham é o código que JÁ OS TRATA: os
    módulos em que `selo_robo.pode_selar_automatico()` ou
    `exige_humano_para_selar()` aparecem são os módulos em que o robô lavra. As
    rotas desses módulos foram listadas por `ast` sobre os decoradores
    `@app.route` (nome da função = nome da rota), e cada grupo abaixo diz o
    arquivo e as linhas da prova.

O QUE FICOU DE FORA DE PROPÓSITO, E É DECISÃO DO OFICIAL
    Tudo o que não tem prova de uso pelo robô: a ajuda e o agente (falam com
    provedor de IA), as centrais (ONR, CENPROT, CRA, CENSEC, SIRC), a leitura
    de documentos por IA do RCPN, os protocolos do caixa (já vedados), tarefas,
    expedientes, processos, relatórios, produtividade, o gestor e a automação.
    Se um robô precisar de uma dessas telas, ela entra AQUI, com o motivo — e
    não por prefixo: rota nova nasce fechada.

    Dentro dos módulos listados entraram TODAS as rotas de hoje, para não
    quebrar o que o robô já faz; quais delas ele não deveria alcançar (as que
    falam com central externa, por exemplo) é a poda que o oficial decide.

COMO SE MEXE
    Rota nova que o robô precise: acrescente o nome no grupo certo, com a
    razão no comentário. `tests/test_rotas_do_robo.py` fica vermelho quando um
    nome daqui deixa de existir no `url_map`, quando um nome daqui cai numa
    vedada, e prova que toda rota fora daqui responde 403 ao robô.
"""
from __future__ import annotations

# O QUE TODA SESSÃO PRECISA, e nada mais. `dashboard` é a «Visão geral»
# para onde o login leva (e o teste `test_o_robo_nao_entra_nas_rotas_de_gente`
# já exige «/» abrindo para o robô); `login`/`logout` são a porta;
# `static` é o CSS e o JS de toda tela (o `before_request` já o deixa passar
# antes de olhar a sessão, e ele fica aqui para a lista dizer a verdade);
# `health` é o «/saude». `attachment_view`/`attachment_download` são o
# anexo aberto DE DENTRO das fichas que o robô trabalha
# (templates/atrib_rcpn_ficha.html, atrib_registro_ficha.html, notas_ato.html).
DA_SESSAO: tuple[str, ...] = (
    "dashboard", "login", "logout", "static", "health", "attachment_view",
    "attachment_download",
)


# O MODAL DE AVISOS E TAREFAS SAI EM TODA TELA, PARA QUALQUER USUÁRIO
# (`nu_avisos_web._nu_avisos_contexto` + static/nu_avisos_modal.js no
# base.html). Sem poder fechá-lo ou dispensá-lo, o robô que opera pelo
# navegador ficaria preso atrás dele. Só as rotas de quem LÊ o aviso —
# as do administrador (`nu_avisos_admin_*`) e as que mexem em dinheiro
# (`nu_avisos_marcar_pago`, `nu_avisos_avisei`) ficam de fora.
DOS_AVISOS: tuple[str, ...] = (
    "nu_avisos_fechar_modal", "nu_avisos_dispensar_normais_faixa",
    "nu_avisos_dispensar_importantes_faixa", "nu_avisos_pendentes_json",
    "nu_avisos_lista", "nu_avisos_detalhe", "nu_avisos_dispensar",
)


# RCPN, RCPJ/RTD, Livro 3 e Protesto. PROVA de que o robô lavra aqui: o
# código já o trata — `SR.pode_selar_automatico()` em atribuicoes_web.py
# (linhas 969, 1545, 1648, 1744, 1937, 2815, 8223, 11846) e
# `SR.exige_humano_para_selar()` (linha 4258). O «Robo Nascimento RCPN» do
# teste de segurança é deste módulo.
# 177 rotas — TODAS as de atribuicoes_web.py no main de 26/10/2026.
DAS_ATRIBUICOES: tuple[str, ...] = (
    "atribuicoes_certidao", "atribuicoes_certidao_cancelar",
    "atribuicoes_certidao_emitir", "atribuicoes_certidao_imprimir",
    "atribuicoes_certidao_negativa", "atribuicoes_certidao_odt",
    "atribuicoes_certidoes", "atribuicoes_importar", "importar_padrao_manual",
    "importar_padrao_preencher", "importar_padrao_tela", "inacabados_ajustar",
    "inacabados_anotar", "inacabados_lista", "livro3_importar_acervo",
    "livro3_lancar", "livro3_registro", "livro3_registro_novo",
    "livro3_registros", "notas_certidao", "notas_certidao_cancelar",
    "notas_certidao_emitir", "notas_certidao_odt", "notas_certidoes",
    "protesto_a_protestar", "protesto_a_protestar_lavrar",
    "protesto_aviso_base_cadastrar", "protesto_aviso_base_consultar",
    "protesto_aviso_comprovante", "protesto_aviso_digital",
    "protesto_aviso_edital", "protesto_aviso_emitir", "protesto_aviso_entrega",
    "protesto_aviso_odt", "protesto_aviso_resolve", "protesto_avisos",
    "protesto_avisos_lote", "protesto_avisos_lote_folhas",
    "protesto_avisos_lote_registrar", "protesto_cenprot",
    "protesto_cenprot_edital", "protesto_cenprot_emolumentos",
    "protesto_cenprot_xml", "protesto_cenprot_xml_apresentante",
    "protesto_cenprot_xml_apresentantes_do_acervo",
    "protesto_cenprot_xml_baixar", "protesto_cenprot_xml_gerar",
    "protesto_certidao", "protesto_certidao_cancelar",
    "protesto_certidao_emitir", "protesto_certidao_odt", "protesto_certidoes",
    "protesto_desistencia", "protesto_desistencia_aplicar",
    "protesto_desistencia_arquivo", "protesto_desistencia_conferir",
    "protesto_desistencias", "protesto_editais_do_dia_odt",
    "protesto_edital_odt", "protesto_imagem", "protesto_imagens",
    "protesto_importar_eoficio", "protesto_instrumento_assinar",
    "protesto_instrumento_emitir", "protesto_instrumento_odt",
    "protesto_instrumentos", "protesto_lancar", "protesto_livro",
    "protesto_ordem_marcar", "protesto_painel", "protesto_quitacao_odt",
    "protesto_remessa", "protesto_remessa_arquivo",
    "protesto_remessa_conferir", "protesto_remessa_da_cra",
    "protesto_remessa_receber", "protesto_remessa_salva",
    "protesto_remessa_salva_conferir", "protesto_remessas",
    "protesto_retorno_arquivo", "protesto_retorno_enviar",
    "protesto_retorno_gerar", "protesto_retornos", "protesto_titulo",
    "protesto_titulo_novo", "protesto_titulos", "protesto_titulos_legacy",
    "rascunho_apagar", "rascunho_salvar", "rascunhos", "rcpj_rtd_ato_teor",
    "rcpj_rtd_certidao_previa", "rcpj_rtd_corrigir_requerente",
    "rcpj_rtd_dados_pj", "rcpj_rtd_lancar", "rcpj_rtd_registro",
    "rcpj_rtd_registro_arquivo", "rcpj_rtd_registro_novo",
    "rcpj_rtd_registros", "rcpj_rtd_teor_averbacao_previa",
    "rcpj_rtd_ultimos_atos", "rcpn_anotacao_crc", "rcpn_anotacao_oficio",
    "rcpn_anotacao_resolver", "rcpn_anotacoes", "rcpn_anotar", "rcpn_assento",
    "rcpn_assento_editar", "rcpn_assento_novo", "rcpn_assentos",
    "rcpn_ato_etiqueta", "rcpn_ato_selar", "rcpn_averbacao_selar_novamente",
    "rcpn_averbacoes", "rcpn_averbar", "rcpn_averbar_cpf", "rcpn_certidao",
    "rcpn_certidao_cancelar", "rcpn_certidao_eletronica_selo",
    "rcpn_certidao_emitir", "rcpn_certidao_imprimir", "rcpn_certidao_odt",
    "rcpn_certidao_previa", "rcpn_certidoes", "rcpn_checklist",
    "rcpn_checklist_pendente", "rcpn_comunicacao", "rcpn_comunicacao_resolver",
    "rcpn_comunicacoes", "rcpn_comunicacoes_abrir", "rcpn_confirmar_livro",
    "rcpn_cpf", "rcpn_crc", "rcpn_crc_arquivo", "rcpn_crc_enviar",
    "rcpn_crc_historico", "rcpn_crc_marcar_enviado", "rcpn_dados_cadastrais",
    "rcpn_etiqueta_averbacao_ajuste", "rcpn_filiacao", "rcpn_folha",
    "rcpn_folha_papel", "rcpn_formulario", "rcpn_funai", "rcpn_funai_oficio",
    "rcpn_gemeos", "rcpn_ibge", "rcpn_importar", "rcpn_importar_acervo",
    "rcpn_importar_manual", "rcpn_importar_modelo",
    "rcpn_informacoes_importadas", "rcpn_lancar", "rcpn_marcas_do_obito",
    "rcpn_matriculas", "rcpn_painel", "rcpn_registro_tardio",
    "rcpn_retificacao", "rcpn_retificacao_nova", "rcpn_retificacoes",
    "rcpn_retificar", "rcpn_sirc", "rcpn_sirc_arquivo",
    "rcpn_sirc_arquivo_enviar", "rcpn_sirc_arquivo_mrc",
    "rcpn_sirc_arquivo_validar", "rcpn_sirc_cancelamento_arquivo",
    "rcpn_sirc_cancelamento_enviar", "rcpn_sirc_cancelamento_validar",
    "rcpn_sirc_carga_arquivo", "rcpn_sirc_inexistencia",
    "rcpn_sirc_inexistencia_enviar", "rcpn_termo", "rcpn_termo_escrever",
    "rcpn_termo_odt", "rcpn_termo_pdf", "rcpn_termos_a_escrever",
)


# TABELIONATO. PROVA: `SR.pode_selar_automatico()` em notas_web.py (linhas
# 1593, 1676, 1765, 1877, 6652) e `SR.exige_humano_para_selar()` (2847,
# 2871, 2933); e tests/test_selo_travado_para_robos.py, que entra como robô
# em /notas/cartoes, /notas/reconhecimento e /notas/autenticacao.
# 65 rotas — TODAS as de notas_web.py no main de 26/10/2026.
DAS_NOTAS: tuple[str, ...] = (
    "notas_anotacoes_pendentes", "notas_assinaturas", "notas_atas",
    "notas_ato", "notas_ato_anexo", "notas_ato_anexo_retirar",
    "notas_ato_apagar_rascunho", "notas_ato_comunicacao_origem",
    "notas_ato_inutilizacao", "notas_ato_montar", "notas_ato_novo",
    "notas_ato_pdf_assinado", "notas_ato_preencher",
    "notas_ato_protocolo_geral", "notas_ato_teor_importar",
    "notas_ato_teor_odt", "notas_ato_termo_livro", "notas_ato_traslado",
    "notas_atos", "notas_autenticacao", "notas_autenticacao_etiqueta",
    "notas_autenticacao_selar", "notas_autenticacao_selo", "notas_cartao",
    "notas_cartao_digital", "notas_cartao_digital_colher",
    "notas_cartao_ficha", "notas_cartao_ficha_enviar", "notas_cartao_foto",
    "notas_cartao_foto_colher", "notas_cartao_imagem",
    "notas_cartao_imagem_gerir", "notas_cartao_imagem_original",
    "notas_cartao_selar", "notas_cartoes", "notas_escritura_partes_ambiguas",
    "notas_escritura_valor", "notas_escrituras", "notas_escrituras_natureza",
    "notas_escrituras_pendentes", "notas_etiqueta_ajuste", "notas_importar",
    "notas_livro_conferir", "notas_livro_inutilizacao", "notas_livro_termo",
    "notas_livros", "notas_painel", "notas_reconhecimento",
    "notas_reconhecimento_etiqueta", "notas_reconhecimento_selar",
    "notas_reconhecimento_termo_comparecimento", "notas_reconhecimento_ver",
    "notas_reconhecimentos", "notas_remessa_enviar_api", "notas_remessa_gerar",
    "notas_remessa_pendencias", "notas_remessa_situacao", "notas_remessas",
    "notas_selar_arquivamento", "notas_sinais", "notas_sinal",
    "notas_sinal_pdf", "notas_sinal_reconhecimento",
    "notas_sinal_reconhecimento_etiqueta", "notas_sinal_reconhecimento_ver",
)


# REGISTRO DE IMÓVEIS. PROVA: `SR.pode_selar_automatico()` em ri_web.py
# (linhas 2341, 2611, 2777, 2850) e `SR.exige_humano_para_selar()` (5140,
# 5296, 5353, 5592).
# 78 rotas — TODAS as de ri_web.py no main de 26/10/2026.
DO_RI: tuple[str, ...] = (
    "ri_aplicar_modelo", "ri_baixar_digitalizacao", "ri_cancelar_ato",
    "ri_cancelar_certidao", "ri_certidao_odt", "ri_certidao_selar",
    "ri_certidoes", "ri_cnib", "ri_cnib_pendentes", "ri_cnib_resolver",
    "ri_conferir", "ri_conferir_ficha", "ri_copiar_imagens",
    "ri_corrigir_parte", "ri_ctp", "ri_ctp_arquivo", "ri_delegatarios",
    "ri_descartar_minuta", "ri_doi", "ri_doi_arquivo", "ri_editar_matricula",
    "ri_emitir_certidao", "ri_emitir_certidao_negativa",
    "ri_encerrar_matricula", "ri_expurgar_ato", "ri_expurgo_ata",
    "ri_expurgos", "ri_ficha", "ri_ficha_odt", "ri_fichas_do_disco",
    "ri_fichas_do_disco_escolher", "ri_fichas_do_disco_trazer",
    "ri_gravar_cnm", "ri_imagem", "ri_importacao_manual", "ri_importacoes",
    "ri_importar", "ri_incluir_parte_abertura", "ri_indicador_pessoal",
    "ri_indicador_real", "ri_lavrar_ato", "ri_matriculas", "ri_matriculas_doc",
    "ri_miniatura_digitalizacao", "ri_minuta_criar", "ri_minuta_guardar",
    "ri_modelos", "ri_modelos_atos", "ri_nota_devolutiva", "ri_nota_odt",
    "ri_nova_matricula", "ri_numeracao", "ri_numeracao_no_teor", "ri_onr",
    "ri_onr_next_cloud", "ri_onr_next_cloud_ips", "ri_organizar_imagens",
    "ri_pedidos", "ri_preencher_modelo", "ri_prenotacao_comprovante",
    "ri_prenotacao_documento", "ri_protocolo", "ri_protocolo_prazo",
    "ri_protocolo_ver", "ri_qualificar", "ri_rascunho_guardar",
    "ri_rascunho_ver", "ri_rascunhos", "ri_reabrir_matricula", "ri_reingresso",
    "ri_renumerar_matricula", "ri_resolver_imagens", "ri_selar_abertura",
    "ri_selar_arquivamento", "ri_selar_ato", "ri_selar_prenotacao", "ri_selos",
    "ri_upload_digitalizacao",
)


# O SELO DO LIVRO 3. PROVA: `SR.pode_selar_automatico()` (linhas 40, 114) e
# `SR.exige_humano_para_selar()` (193, 231) em ra_selo_web.py — o selar
# automático é chamado de atribuicoes_web.py (linhas 9612 e 9727).
# 2 rotas — TODAS as de ra_selo_web.py no main de 26/10/2026.
DO_LIVRO3_SELO: tuple[str, ...] = (
    "livro3_selar_arquivamento", "livro3_selar_ato",
)


# NOTIFICAÇÃO DO RTD. PROVA: `SR.pode_selar_automatico()` em
# rg_notificacao.py, linha 1027.
# 9 rotas — TODAS as de rg_notificacao.py no main de 26/10/2026.
DA_NOTIFICACAO_RTD: tuple[str, ...] = (
    "rcpj_rtd_notificacao", "rcpj_rtd_notificacao_averbar",
    "rcpj_rtd_notificacao_certidao", "rcpj_rtd_notificacao_certidao_ver",
    "rcpj_rtd_notificacao_diligencia", "rcpj_rtd_notificacao_negativa",
    "rcpj_rtd_notificacao_nova", "rcpj_rtd_notificacao_selar",
    "rcpj_rtd_notificacoes",
)


# PÚBLICA FORMA. PROVA: `SR.pode_selar_automatico()` (linha 508) e
# `SR.exige_humano_para_selar()` (656) em nt_publica_forma.py.
# 7 rotas — TODAS as de nt_publica_forma.py no main de 26/10/2026.
DA_PUBLICA_FORMA: tuple[str, ...] = (
    "notas_publica_forma", "notas_publica_forma_cancelar",
    "notas_publica_forma_configuracao", "notas_publica_forma_emitir",
    "notas_publica_forma_odt", "notas_publica_forma_selar",
    "notas_publica_forma_ver",
)


# COMUNICAÇÃO DE VENDA DE VEÍCULO. PROVA: `SR.exige_humano_para_selar()` em
# nt_veiculo_detran.py, linha 783.
# 5 rotas — TODAS as de nt_veiculo_detran.py no main de 26/10/2026.
DO_VEICULO_DETRAN: tuple[str, ...] = (
    "notas_veiculo", "notas_veiculo_comunicar", "notas_veiculo_configuracao",
    "notas_veiculo_nova", "notas_veiculos",
)

#: A LISTA FECHADA. `selo_robo.rota_permitida_ao_robo` a consulta; vedada
#: (`selo_robo.ROTAS_VEDADAS_AO_ROBO`) vence permitida.
ROTAS_PERMITIDAS_AO_ROBO: frozenset[str] = frozenset(
    DA_SESSAO + DOS_AVISOS + DAS_ATRIBUICOES + DAS_NOTAS + DO_RI
    + DO_LIVRO3_SELO + DA_NOTIFICACAO_RTD + DA_PUBLICA_FORMA + DO_VEICULO_DETRAN)
