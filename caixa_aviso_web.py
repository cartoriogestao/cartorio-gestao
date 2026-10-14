"""Pendura o aviso do caixa em TODA tela — ver `caixa_aviso.py`.

Mora no `base.html` pela mesma razão da janela da ajuda: ligado tela a tela, a
primeira tela que alguém criasse amanhã nasceria sem o aviso. Só LÊ: um GET
que escrevesse disputaria a trava com o balcão.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from flask import request, session

import caixa_aviso as CA


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    usuario_nome = app.extensions["usuario_nome"]

    @app.context_processor
    def _caixa_aviso() -> dict:
        vazio = {"caixa_aviso": None}
        try:
            onde = request.endpoint or ""
        except RuntimeError:
            return vazio
        if not session.get("user_id") or onde in ("static", "login", "logout"):
            return vazio
        try:
            nome = usuario_nome()
            with db.connect() as con:
                papel = con.execute("SELECT role FROM users WHERE id = ?",
                                    (session.get("user_id"),)).fetchone()
                e_admin = bool(papel and papel[0] == "ADMIN")
                fim = db.get_setting(CA.CHAVE_FIM, CA.FIM_PADRAO)
                aviso = CA.situacao(con, nome, datetime.now(), fim, e_admin=e_admin)
        except (sqlite3.Error, RuntimeError, KeyError):
            return vazio
        if aviso:
            # A TELA DO CAIXA FICA LIVRE: é nela que se fecha. Bloquear também
            # ali seria trancar a porta de saída junto com as outras.
            aviso["na_tela_do_caixa"] = onde == "caixa"
        return {"caixa_aviso": aviso}
