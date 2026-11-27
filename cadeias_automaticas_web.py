"""A faixa das cadeias automáticas no alto de toda tela (A006). Só LÊ.

Mora no `base.html` e no `base_novo.html` pela razão da faixa da gratuidade:
ligada tela a tela, a próxima tela nasceria sem ela. Quem calcula é
`cadeias_automaticas.aviso`; aqui só se decide QUEM vê e se guarda a conta por
um minuto — ela é a mesma para todos, e a TI abre dezenas de telas por hora.
"""
from __future__ import annotations

import time
from datetime import datetime

from flask import request, session

import cadeias_automaticas as CA
import papeis as PAP
from bd_nativo import banco
from gratuidade_comprovante_web import _uma_vez_por_requisicao

#: Por quantos segundos a conta vale. A faixa some até um minuto depois de a
#: cadeia voltar — e não a cada tela, que pagaria a conta toda vez.
GUARDA_S = 60
VAZIO = {"cadeias_aviso": None}


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    guardado: dict = {"em": 0.0, "aviso": None}

    def _conta() -> dict:
        if time.monotonic() - guardado["em"] < GUARDA_S and guardado["aviso"] is not None:
            return guardado["aviso"]
        aviso = CA.aviso(db.connect, datetime.now())   # noqa: DTZ005 — relógio da casa
        guardado.update(em=time.monotonic(), aviso=aviso)
        return aviso

    app.extensions["cadeias_automaticas_esquecer"] = lambda: guardado.update(em=0.0, aviso=None)

    @app.context_processor
    def _cadeias_aviso() -> dict:
        try:
            onde = request.endpoint or ""
        except RuntimeError:
            return VAZIO
        if not session.get("user_id") or onde in ("static", "login", "logout"):
            return VAZIO

        def calcular() -> dict:
            try:
                with db.connect() as con:
                    quem = banco(con).um("SELECT role FROM users WHERE id = %s",
                                         (session.get("user_id"),)) or {}
                if not PAP.equivale_a(quem, *CA.QUEM_VE):
                    return VAZIO
                aviso = _conta()
            except Exception:                           # noqa: BLE001 — tela não cai por aviso
                return VAZIO
            return {"cadeias_aviso": aviso if aviso["quantos"] else None}
        return _uma_vez_por_requisicao("_cg_cadeias_aviso", calcular)
