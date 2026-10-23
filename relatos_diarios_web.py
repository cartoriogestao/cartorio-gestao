"""A janela «Relatos do dia» no painel, e a página com o histórico.

Ordem do oficial em 12/10/2026: os relatos diários num lugar próprio, e não em
tarefa. O painel mostra os do dia de quem está olhando (o oficial e o gerente
veem também os da Gestão, e a carga da equipe); a página guarda os dias
anteriores. Ler não grava nada; «marcar como lido» é um POST.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from flask import redirect, render_template, request, session, url_for

import carga_da_equipe as CARGA
import relatos_diarios as RD
from seguranca_web import destino_interno  # M1/B3 (LX11): o «volte para» só leva a caminho desta casa

QUEM = ("ADMIN", "MANAGER", "USER")
VEEM_A_GESTAO = ("ADMIN", "MANAGER")


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    current_user = app.extensions["current_user"]

    def _quem() -> tuple[int | None, bool]:
        u = current_user()
        if not u:
            return None, False
        return int(u["id"]), (u["role"] in VEEM_A_GESTAO)

    with db.connect() as con:
        RD.init_schema(con)

    @app.context_processor
    def _relatos_no_painel() -> dict:
        vazio = {"relatos_do_dia": None}
        try:
            if request.endpoint != "dashboard" or not session.get("user_id"):
                return vazio
            uid, gestao = _quem()
            if uid is None:
                return vazio
            with db.connect() as con:
                relatos = RD.do_dia(con, dia=date.today(), usuario_id=uid, ve_a_gestao=gestao)
                carga = CARGA.carga(con) if gestao else None
        except (sqlite3.Error, RuntimeError, KeyError, TypeError):
            return vazio
        return {"relatos_do_dia": relatos, "carga_da_equipe": carga}

    @app.route("/relatos")
    @roles_required(*QUEM)
    def relatos_diarios():
        uid, gestao = _quem()
        dia = (request.args.get("dia") or date.today().isoformat())[:10]
        with db.connect() as con:
            relatos = RD.do_dia(con, dia=dia, usuario_id=uid, ve_a_gestao=gestao)
            dias = RD.dias_com_relato(con, usuario_id=uid, ve_a_gestao=gestao)
            carga = CARGA.carga(con) if gestao else None
            sugestoes = CARGA.sugestoes_de_passagem(con) if gestao else []
            grupos = CARGA.agrupaveis(con) if gestao else []
            inflada = CARGA.prioridade_inflada(con) if gestao else None
        return render_template("relatos_diarios.html", relatos=relatos, dia=dia, dias=dias,
                               carga=carga, sugestoes=sugestoes, grupos=grupos, inflada=inflada)

    @app.route("/relatos/<int:relato_id>/lido", methods=["POST"])
    @roles_required(*QUEM)
    def relato_lido(relato_id: int):
        uid, gestao = _quem()
        with db.transaction() as con:
            RD.marcar_lido(con, relato_id, usuario_id=uid, ve_a_gestao=gestao)
        return redirect(destino_interno(request.form.get("voltar"), url_for("relatos_diarios")))
