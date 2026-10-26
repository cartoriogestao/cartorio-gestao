# -*- coding: utf-8 -*-
"""Trava de selo automatico para contas de robo (Grok Bot).

Regra permanente do oficial (05/10/2026): robos NUNCA aplicam selo
automaticamente. O ato fica pendente de selo; so o escrevente humano sela.
O balcao humano continua selando ao salvar, como sempre.

`eh_robo` e coluna em `users` (migracao em caixa_schema). Nome/login com
Robo/Robô/grok tambem indicam robo no preenchimento inicial.
"""
from __future__ import annotations

from typing import Any

import nome_humano as NOMEHUM

MSG_PENDENTE_SELO = " Pendente de selo — o escrevente deve selar."


def usuario_e_robo(user: Any = None) -> bool:
    """True se a conta logada (ou o row passado) e de robo."""
    if user is None:
        user = _usuario_da_sessao()
    if not user:
        return False
    try:
        if int(user["eh_robo"] or 0) == 1:
            return True
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    # Fallbacks por nome, para bancos/sessoes sem a coluna ainda.
    try:
        nome = (user["full_name"] or "").strip()
    except (KeyError, IndexError, TypeError):
        nome = ""
    try:
        login = (user["username"] or "").strip()
    except (KeyError, IndexError, TypeError):
        login = ""
    return NOMEHUM.eh_rotulo_de_maquina(nome) or NOMEHUM.eh_rotulo_de_maquina(login)


def pode_selar_automatico(user: Any = None) -> bool:
    """False para robo: nao chamar o selador no fluxo automatico."""
    return not usuario_e_robo(user)


def recado_pendente_selo() -> str:
    """Mensagem que NAO casa com motivo_da_falha_do_selo (sem 'SEM SELO')."""
    return MSG_PENDENTE_SELO


def reconhecimento_pendente() -> dict:
    """Resposta estruturada de selar_reconhecimento quando o usuario e robo.

    `ok=True` e `selos=[]` evitam o caminho que APAGA o reconhecimento
    quando o selo falha de verdade. O ato fica lavrado, sem numero de selo.
    """
    return {
        "ok": True,
        "selos": [],
        "mensagem": MSG_PENDENTE_SELO,
        "motivo": None,
        "pendente_de_selo": True,
    }


#: O que o robô NÃO alcança, pelo nome da rota (revisão de segurança da 3.7.0,
#: 22/10/2026, achado A6): usuários, atualizações, backup, configurações, caixa,
#: selador, modelos, agente, os próprios robôs, livros do núcleo e implantação.
#: O robô gera minuta e lavra o que o seu papel deixa; o que é de gente é de gente.
#:
#: DESDE 26/10/2026 ESTA É A SEGUNDA TRAVA, e não a única. A régua por prefixo
#: não cobria rota nova (revisão de segurança dos PRs abertos, achado
#: transversal 1): a primeira trava passou a ser a LISTA FECHADA de
#: `rotas_do_robo.ROTAS_PERMITIDAS_AO_ROBO` — fora dela, 403. Esta continua
#: valendo por cima: vedada vence permitida, e um nome que alguém ponha na
#: lista permitida por engano continua barrado aqui.
ROTAS_VEDADAS_AO_ROBO = ("users", "usuarios", "updates", "atualizacoes", "settings",
                         "configuracoes", "backup", "caixa_", "caixa", "selador",
                         "modelos", "agente", "robos", "dois_fatores", "permiss",
                         "nucleo_", "implantacao")


def rota_vedada_ao_robo(endpoint: Any) -> bool:
    """A rota é das que o robô não entra? Só calcula."""
    nome = str(endpoint or "").strip()
    return bool(nome) and nome.startswith(ROTAS_VEDADAS_AO_ROBO)


def rota_permitida_ao_robo(endpoint: Any) -> bool:
    """O robô pode entrar nesta rota? Só calcula.

    A RÉGUA É FECHADA (revisão de segurança de 26/10/2026, achado transversal
    1): entra só o que está em `rotas_do_robo.ROTAS_PERMITIDAS_AO_ROBO`, e a
    rota nova nasce fora — até alguém decidir, com o motivo escrito, que o robô
    precisa dela. Vedada vence permitida (`rota_vedada_ao_robo`). Rota sem
    nome (o 404, que não casa com regra nenhuma) também fica fora.
    """
    nome = str(endpoint or "").strip()
    if not nome or rota_vedada_ao_robo(nome):
        return False
    import rotas_do_robo as RR
    return nome in RR.ROTAS_PERMITIDAS_AO_ROBO


#: Os LANÇAMENTOS que o robô não faz, mesmo nas rotas de lançar que ele
#: alcança (`rotas_do_robo`): os que DESFAZEM ou SUSPENDEM ato — o
#: cancelamento (RCPJ/RTD, Livro 3, Protesto) e as ordens judiciais do
#: Protesto. Revisão de segurança de 26/10/2026: cancelar é decisão de gente.
#: E, por ordem do oficial no mesmo dia, a DESISTÊNCIA (encerra o título) e o
#: PAGAMENTO (é dinheiro) do Protesto também ficam com gente.
LANCAMENTOS_VEDADOS_AO_ROBO = ("CANCELAMENTO", "SUSTACAO", "EFEITO_SUSPENSIVO",
                               "REVOGACAO_EFEITO_SUSPENSIVO", "DESISTENCIA",
                               "PAGAMENTO")


def lancamento_vedado_ao_robo(tipo: Any, user: Any = None) -> bool:
    """True = a rota de lançar deve responder 403: é robô pedindo um dos
    `LANCAMENTOS_VEDADOS_AO_ROBO`. Só calcula."""
    if str(tipo or "").strip().upper() not in LANCAMENTOS_VEDADOS_AO_ROBO:
        return False
    return usuario_e_robo(user)


def exige_humano_para_selar(user: Any = None) -> bool:
    """True = a rota do botao Selar deve responder 403."""
    return usuario_e_robo(user)


def nome_ou_login_indica_robo(nome: Any = None, login: Any = None) -> bool:
    return (NOMEHUM.eh_rotulo_de_maquina(nome)
            or NOMEHUM.eh_rotulo_de_maquina(login))


def _usuario_da_sessao():
    try:
        from flask import current_app, has_app_context, has_request_context
        if not has_app_context():
            return None
        # Preferir current_user da extensao (mesmo row do get_user).
        cu = current_app.extensions.get("current_user")
        if cu:
            return cu()
        if not has_request_context():
            return None
    except Exception:
        return None
    return None
