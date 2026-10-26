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

A LISTA É DO QUE O ROBÔ FAZ, MEDIDA NO CÓDIGO — E NÃO NO USO
    Não há registro de acesso por rota nesta casa (o `waitress` não guarda, e
    `audit_logs` guarda ação, e não endereço), e não há no repositório cliente
    HTTP de robô que entre com login: os robôs da casa (papel USER ou AUDITOR —
    `database.create_user` recusa outro) operam pelo NAVEGADOR, como o balcão.

    O que o robô faz, o código diz: ele LAVRA, e o selo fica pendente. As rotas
    abaixo são as que chegam a `selo_robo.pode_selar_automatico()` — medido
    por grafo de chamadas (`ast`) a partir de cada `@app.route` de
    atribuicoes_web, notas_web, ri_web, ra_selo_web, rg_notificacao,
    nt_publica_forma e nt_veiculo_detran, no `main` b89252d. Cada entrada diz
    o ajudante de selo que ela alcança.

    FICARAM DE FORA, mesmo chegando ao selo:
      - os botões «Selar» que já recusam o robô por dentro
        (`SR.exige_humano_para_selar()`): rcpn_ato_selar, notas_cartao_selar,
        notas_reconhecimento_selar, notas_autenticacao_selar, ri_selar_ato,
        ri_selar_prenotacao, ri_selar_arquivamento, livro3_selar_ato,
        livro3_selar_arquivamento, notas_publica_forma_selar;
      - `ri_cancelar_ato` — cancelar é decisão de gente (revisão de 26/10).

    E A PRIMEIRA VERSÃO DESTA LISTA (bd6c0b49) ESTAVA LARGA DEMAIS: ela trazia
    TODAS as rotas daqueles módulos (357), porque um módulo que cita o robô
    «tem o robô». Não tem: o robô é citado ali para ser RECUSADO ao selar, e
    isso não prova que ele opere no resto. `ri_cancelar_ato` e
    `ri_expurgar_ato` estavam dentro e não recusam o robô por dentro.

    MEDIR PELO USO É O PASSO DO OFICIAL antes do merge: a consulta somente de
    leitura aos `audit_logs` das contas de robô está no corpo do PR. Rota que o
    robô use e não esteja aqui entra no grupo certo, com o motivo.

O QUE A LISTA NÃO PODE TER
    Nome com `cancel`, `expurg`, `apagar`, `excluir`, `enviar`, `importar`,
    `configuracao` ou `modelo` só entra com exceção declarada e justificada em
    `tests/test_rotas_do_robo.py` (`EXCECOES_DA_LISTA_NEGRA`) — e com teste que
    prove a recusa por dentro. Hoje não há nenhuma.

    E dentro das rotas de lançar que o robô alcança, os lançamentos que
    desfazem ou suspendem (CANCELAMENTO e as ordens judiciais do Protesto)
    recusam o robô POR DENTRO: `selo_robo.lancamento_vedado_ao_robo`.

COMO SE MEXE
    Rota nova que o robô precise: acrescente o nome no grupo certo, com a
    razão no comentário. `tests/test_rotas_do_robo.py` fica vermelho quando um
    nome daqui deixa de existir no `url_map`, quando cai numa vedada ou na
    lista negra, e prova que toda rota fora daqui responde 403 ao robô.
"""
from __future__ import annotations

# O QUE TODA SESSÃO PRECISA. `dashboard` é a «Visão geral» para onde o login
# leva (o teste `test_o_robo_nao_entra_nas_rotas_de_gente` exige «/» abrindo
# para o robô); `login`/`logout` são a porta; `static` é o CSS e o JS de toda
# tela (o `before_request` já o deixa passar antes de olhar a sessão); `health`
# é o «/saude». `attachment_view`/`attachment_download` são o anexo aberto DE
# DENTRO das fichas que o robô trabalha (templates/atrib_rcpn_ficha.html,
# atrib_registro_ficha.html, notas_ato.html).
DA_SESSAO: tuple[str, ...] = (
    "dashboard", "login", "logout", "static", "health", "attachment_view",
    "attachment_download",
)

# O MODAL DE AVISOS E TAREFAS SAI EM TODA TELA, PARA QUALQUER USUÁRIO
# (`nu_avisos_web._nu_avisos_contexto` + static/nu_avisos_modal.js). Sem poder
# fechá-lo, o robô que opera pelo navegador ficaria preso atrás dele. Ficam de
# fora as do administrador (`nu_avisos_admin_*`), as que mexem em dinheiro
# (`nu_avisos_marcar_pago`, `nu_avisos_avisei`) e a dispensa em lote dos
# avisos IMPORTANTES (`nu_avisos_dispensar_importantes_faixa`): aviso
# importante quem dispensa é gente.
DOS_AVISOS: tuple[str, ...] = (
    "nu_avisos_fechar_modal", "nu_avisos_dispensar_normais_faixa",
    "nu_avisos_pendentes_json", "nu_avisos_lista", "nu_avisos_detalhe",
    "nu_avisos_dispensar",
)

# RCPN, RCPJ/RTD, LIVRO 3 E PROTESTO (atribuicoes_web.py) — as rotas que
# LAVRAM com selo automático. Entre parênteses, o ajudante que chama
# `SR.pode_selar_automatico()`.
DO_SELO_AUTOMATICO_ATRIBUICOES: tuple[str, ...] = (
    "rcpn_assento_novo",               # (_selar_o_ato)
    "rcpn_lancar",                     # (_selar_o_ato) — averba, anota, retifica
    "rcpn_averbar_cpf",                # (_selar_o_ato) — o mutirão do art. 347
    "rcpn_averbacao_selar_novamente",  # (_selar_o_ato)
    "rcpn_certidao_emitir",            # (_selar_o_ato)
    "rcpn_certidao_eletronica_selo",   # (rcpn_certidao_eletronica_selo)
    "rcpj_rtd_registro_novo",          # (_selar_o_ato)
    "rcpj_rtd_lancar",                 # (_selar_o_ato) — CANCELAMENTO recusa o robô
    "livro3_registro_novo",            # (arquivar_o_ato_do_livro3)
    "livro3_lancar",                   # (arquivar_o_ato_do_livro3) — idem
    "protesto_lancar",                 # (_selar_o_protesto) — idem, e as ordens judiciais
    "protesto_certidao_emitir",        # (_selar_o_protesto)
    "atribuicoes_certidao_emitir",     # (_selar_a_certidao_do_livro3 / _rtdpj)
    "atribuicoes_certidao_negativa",   # (_selar_a_certidao_negativa)
    "notas_certidao_emitir",           # (_selar_a_certidao_das_notas)
)

# TABELIONATO (notas_web.py e nt_publica_forma.py). Os quatro primeiros são o
# que tests/test_selo_travado_para_robos.py faz entrando como robô.
DO_SELO_AUTOMATICO_NOTAS: tuple[str, ...] = (
    "notas_cartoes",                   # (selar_simples) — abrir cartão
    "notas_reconhecimento",            # (selar_reconhecimento)
    "notas_autenticacao",              # (selar_simples)
    "notas_sinal_reconhecimento",      # (selar_reconhecimento_sinal)
    "notas_ato",                       # (_selar_arquivamento_das_notas) — ato de livro
    "notas_selar_arquivamento",        # (_selar_arquivamento_das_notas)
    "notas_publica_forma_emitir",      # (_selar, nt_publica_forma)
)

# NOTIFICAÇÃO DO RTD (rg_notificacao.py), pelo `_selar` de lá.
DO_SELO_AUTOMATICO_NOTIFICACAO: tuple[str, ...] = (
    "rcpj_rtd_notificacao_certidao", "rcpj_rtd_notificacao_diligencia",
    "rcpj_rtd_notificacao_selar",
)

# REGISTRO DE IMÓVEIS (ri_web.py).
DO_SELO_AUTOMATICO_RI: tuple[str, ...] = (
    "ri_lavrar_ato",                   # (_selar_arquivamento_do_ri / _selar_o_ato_do_ri)
    "ri_protocolo",                    # (_selar_a_prenotacao)
)

# AS FICHAS ONDE ESTÃO OS FORMULÁRIOS DE CIMA — só GET. Medido nos modelos de
# tela: cada uma desenha um modelo que tem `url_for` de uma rota de selo
# automático acima (rota → modelo → ficha), e nenhuma aceita POST.
DAS_FICHAS: tuple[str, ...] = (
    "rcpn_assento",            # atrib_rcpn_ficha.html → rcpn_lancar, rcpn_certidao_emitir…
    "rcpj_rtd_registro",       # atrib_registro_ficha.html → rcpj_rtd_lancar
    "livro3_registro",         # atrib_livro3_ficha.html → livro3_lancar
    "protesto_titulo",         # atrib_protesto_ficha.html → protesto_lancar
    "protesto_certidoes",      # protesto_certidoes.html → protesto_certidao_emitir
    "notas_certidoes",         # notas_certidoes.html → notas_certidao_emitir
    "atribuicoes_certidoes",   # atrib_certidoes.html → atribuicoes_certidao_negativa
    "notas_publica_forma",     # notas_publica_forma.html → notas_publica_forma_emitir
    "rcpj_rtd_notificacao",    # rcpj_rtd_notificacao.html → as três da notificação
    "ri_ficha",                # ri_ficha.html → ri_lavrar_ato
)

#: A LISTA FECHADA. `selo_robo.rota_permitida_ao_robo` a consulta; vedada
#: (`selo_robo.ROTAS_VEDADAS_AO_ROBO`) vence permitida.
ROTAS_PERMITIDAS_AO_ROBO: frozenset[str] = frozenset(
    DA_SESSAO + DOS_AVISOS + DO_SELO_AUTOMATICO_ATRIBUICOES
    + DO_SELO_AUTOMATICO_NOTAS + DO_SELO_AUTOMATICO_NOTIFICACAO
    + DO_SELO_AUTOMATICO_RI + DAS_FICHAS)
