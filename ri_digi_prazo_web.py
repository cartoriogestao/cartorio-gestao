"""O aviso vermelho da ficha sem imagem nova — ver `ri_digi_prazo.py`.

Aparece no alto das telas do RI (para todos) e, para o ADMIN, em qualquer tela
enquanto houver ficha com o prazo de 7 dias vencido. Na ficha da própria
matrícula, diz qual ato está fora da imagem. Só LÊ.
"""
from __future__ import annotations

import sqlite3

from flask import request, session

import ri_digi_prazo as DP
from bd_nativo import banco


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):

    @app.context_processor
    def _digi_aviso() -> dict:
        vazio = {"digi_aviso": None}
        try:
            onde = request.endpoint or ""
        except RuntimeError:
            return vazio
        if not session.get("user_id") or onde in ("static", "login", "logout"):
            return vazio
        try:
            with db.connect() as con:
                papel = banco(con).um("SELECT role FROM users WHERE id = %s",
                                      (session.get("user_id"),))
                e_admin = bool(papel and papel["role"] == "ADMIN")
                if not (onde.startswith("ri_") or e_admin):
                    return vazio
                todas = DP.pendentes(con)
        except (sqlite3.Error, OSError):
            return vazio
        vencidas = [p for p in todas if p["vencida"]]
        desta = None
        mid = (request.view_args or {}).get("matricula_id")
        if onde.startswith("ri_") and mid:
            desta = next((p for p in todas if p["matricula_id"] == mid), None)
        if not (vencidas and (onde.startswith("ri_") or e_admin)) and not desta:
            return vazio
        return {"digi_aviso": {"vencidas": vencidas, "desta": desta}}
