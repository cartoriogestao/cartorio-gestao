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
