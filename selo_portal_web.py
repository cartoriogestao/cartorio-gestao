"""As telas do que a casa deve ao Portal do Selo (LG07, 19/10/2026).

Duas telas e uma de remessa:

- `/selos/cancelamentos` — os selos cancelados do período, o ofício de pedido
  de cancelamento ao TJMA e o «comunicado em». O aviso do topo (gestor e
  oficial) conta os cancelados que ainda não foram comunicados.
- `/selos/gratuidades-portal` — a fila do ressarcimento: por selo gratuito, o
  comprovante e a cópia da certidão do ato; o pacote com um PDF por selo.
- `/selos/portal/remessa/<id>` — o ofício (cancelamento) ou o pacote
  (gratuidade), com «mandei» e «descartar».

QUEM: o pedido e o pacote são do gestor e do oficial (ADMIN, MANAGER); o
AUDITOR vê. O escrevente (USER) vê a fila só com os selos dele e guarda as
peças — é ele quem tem o papel na mão. GET não grava; baixar o pacote é POST
porque fica no rastro (leva declaração de pobreza, dado pessoal).
"""
from __future__ import annotations

import sqlite3
from datetime import date

from flask import (Response, abort, flash, redirect, render_template, request, session,
                   url_for)

import selo_portal as SP
import serventia

GESTAO = ("ADMIN", "MANAGER")
VER = ("ADMIN", "MANAGER", "AUDITOR")
QUEM_GUARDA = ("ADMIN", "MANAGER", "USER")
FILA = ("ADMIN", "MANAGER", "USER", "AUDITOR")


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_id = app.extensions["usuario_id"]
    usuario_nome = app.extensions["usuario_nome"]
    usuario_papel = app.extensions["usuario_papel"]
    archive_root = app.extensions["archive_root"]
    current_user = app.extensions["current_user"]

    def _hoje() -> str:
        return date.today().isoformat()

    @app.context_processor
    def _selo_cancelamento_aviso() -> dict:
        """O aviso do topo, só para quem pede o cancelamento. Só LÊ."""
        vazio = {"selo_cancelamento_aviso": None}
        try:
            onde = request.endpoint or ""
        except RuntimeError:
            return vazio
        if not session.get("user_id") or onde in ("static", "login", "logout"):
            return vazio
        try:
            if usuario_papel() not in GESTAO:
                return vazio
            with db.connect() as con:
                conta = SP.nao_comunicados(con)
        except (sqlite3.Error, RuntimeError, KeyError, TypeError):
            return vazio
        return {"selo_cancelamento_aviso": conta if conta["n"] else None}

    # ------------------------------------------------------ cancelamentos

    @app.route("/selos/cancelamentos")
    @roles_required(*VER)
    def selo_cancelamentos():
        with db.connect() as con:
            desde = SP.desde_cancelamento(con)
            inicio = (request.args.get("inicio") or desde).strip()
            fim = (request.args.get("fim") or _hoje()).strip()
            try:
                lista = SP.cancelados(con, inicio=inicio, fim=fim)
            except SP.PortalError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("selo_cancelamentos"))
            conta = SP.nao_comunicados(con)
            feitas = SP.remessas(con, SP.CANCELAMENTO)
        return render_template("selo_cancelamentos.html", lista=lista, inicio=inicio, fim=fim,
                               desde=desde, conta=conta, remessas=feitas,
                               pode=usuario_papel() in GESTAO,
                               e_admin=usuario_papel() == "ADMIN")

    @app.route("/selos/cancelamentos/oficio", methods=["POST"])
    @roles_required(*GESTAO)
    def selo_cancelamento_oficio_gerar():
        inicio, fim = request.form.get("inicio"), request.form.get("fim")
        try:
            with db.transaction() as con:
                novo = SP.gerar_oficio(con, inicio=inicio, fim=fim, agora=db.now(),
                                       usuario=usuario_nome())
                n = len(SP.remessa(con, novo)["itens"])
        except SP.PortalError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("selo_cancelamentos", inicio=inicio, fim=fim))
        audit("SELO_CANCELAMENTO_OFICIO_GERADO", "sd_portal_remessas", novo,
              {"inicio": inicio, "fim": fim, "selos": n})
        flash(f"Ofício com {n} selo(s) gerado. Imprima ou baixe a lista, mande ao TJMA e "
              f"volte aqui para marcar «comunicado».", "ok")
        return redirect(url_for("selo_portal_remessa", remessa_id=novo))

    @app.route("/selos/cancelamentos/desde", methods=["POST"])
    @roles_required("ADMIN")
    def selo_cancelamento_desde():
        valor = (request.form.get("desde") or "").strip()
        if not SP._DATA.match(valor):
            flash("Informe a data (dia, mês e ano).", "danger")
            return redirect(url_for("selo_cancelamentos"))
        db.set_settings({SP.CHAVE_DO_DESDE: valor})
        audit("SELO_CANCELAMENTO_DESDE_ALTERADO", "settings", None, {"desde": valor})
        flash("Data de início do aviso gravada.", "ok")
        return redirect(url_for("selo_cancelamentos"))

    # ------------------------------------------------- gratuidades e Portal

    @app.route("/selos/gratuidades-portal")
    @roles_required(*FILA)
    def selo_gratuidades_portal():
        situacao = (request.args.get("situacao") or "FALTANDO").strip().upper()
        if situacao not in SP.SITUACOES_DA_GRATUIDADE and situacao not in ("FALTANDO", "TODAS"):
            situacao = "FALTANDO"
        inicio = (request.args.get("inicio") or "").strip() or None
        fim = (request.args.get("fim") or "").strip() or None
        quem = {}
        if usuario_papel() == "USER":
            u = current_user()
            quem = {"nome": (u["full_name"] or "") if u else "",
                    "username": (u["username"] or "") if u else ""}
        with db.connect() as con:
            try:
                lista = SP.gratuitos(con, inicio=inicio, fim=fim,
                                     situacao="" if situacao == "TODAS" else situacao, **quem)
            except SP.PortalError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("selo_gratuidades_portal"))
            for item in lista:
                item["pecas"] = SP.pecas(con, item["id"])
            feitas = SP.remessas(con, SP.GRATUIDADE) if usuario_papel() in VER else []
            desde = SP.GC.desde(con)
        return render_template("selo_gratuidades_portal.html", lista=lista, situacao=situacao,
                               inicio=inicio or desde, fim=fim or _hoje(), remessas=feitas,
                               SP=SP, pode=usuario_papel() in GESTAO,
                               guarda=usuario_papel() in QUEM_GUARDA)

    def _voltar_fila():
        # Volta sempre para a fila, e não para um endereço vindo do formulário:
        # «voltar» livre seria redirecionamento aberto.
        situacao = (request.form.get("situacao") or "").strip().upper()
        return redirect(url_for("selo_gratuidades_portal", situacao=situacao or None))

    @app.route("/selos/gratuidades-portal/<int:selo_id>/peca", methods=["POST"])
    @roles_required(*QUEM_GUARDA)
    def selo_gratuidade_peca(selo_id: int):
        arquivos = [a for a in request.files.getlist("arquivo") if a and a.filename]
        if not arquivos:
            flash("Escolha o arquivo.", "danger")
            return _voltar_fila()
        peca = request.form.get("peca") or ""
        ids = []
        try:
            with db.transaction() as con:
                for arquivo in arquivos:
                    ids.append(SP.guardar_peca(
                        con, selo_id, peca=peca, tipo_comprovante=request.form.get("tipo") or "",
                        nome_arquivo=arquivo.filename, conteudo=arquivo.read(),
                        pasta=archive_root() / "gratuidades", usuario_id=usuario_id(),
                        usuario=usuario_nome(), agora=db.now()))
        except SP.PortalError as erro:
            flash(f"{erro} Nenhum arquivo deste envio foi guardado.", "danger")
            return _voltar_fila()
        audit("SELO_GRATUIDADE_PECA_GUARDADA", "sd_selos", selo_id,
              {"anexos": ids, "peca": peca.upper()})
        flash(f"{len(ids)} arquivo(s) guardado(s).", "ok")
        return _voltar_fila()

    @app.route("/selos/gratuidades-portal/anexo/<int:attachment_id>", methods=["POST"])
    @roles_required(*QUEM_GUARDA)
    def selo_gratuidade_classificar(attachment_id: int):
        try:
            with db.transaction() as con:
                selo_id = SP.classificar(con, attachment_id, peca=request.form.get("peca") or "",
                                         tipo_comprovante=request.form.get("tipo") or "",
                                         agora=db.now(), usuario=usuario_nome())
        except SP.PortalError as erro:
            flash(str(erro), "danger")
            return _voltar_fila()
        audit("SELO_GRATUIDADE_PECA_CLASSIFICADA", "sd_selos", selo_id,
              {"anexo": attachment_id, "peca": (request.form.get("peca") or "").upper()})
        flash("Arquivo marcado.", "ok")
        return _voltar_fila()

    @app.route("/selos/gratuidades-portal/pacote", methods=["POST"])
    @roles_required(*GESTAO)
    def selo_gratuidade_pacote_gerar():
        inicio, fim = request.form.get("inicio"), request.form.get("fim")
        try:
            with db.transaction() as con:
                novo = SP.gerar_pacote(con, inicio=inicio, fim=fim, agora=db.now(),
                                       usuario=usuario_nome())
                n = len(SP.remessa(con, novo)["itens"])
        except SP.PortalError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("selo_gratuidades_portal", inicio=inicio, fim=fim))
        audit("SELO_GRATUIDADE_PACOTE_GERADO", "sd_portal_remessas", novo,
              {"inicio": inicio, "fim": fim, "selos": n})
        flash(f"Pacote com {n} selo(s) gerado. Baixe, suba no Portal do Selo e volte aqui "
              f"para marcar «enviado».", "ok")
        return redirect(url_for("selo_portal_remessa", remessa_id=novo))

    # ------------------------------------------------------------ a remessa

    @app.route("/selos/portal/remessa/<int:remessa_id>")
    @roles_required(*VER)
    def selo_portal_remessa(remessa_id: int):
        with db.connect() as con:
            try:
                r = SP.remessa(con, remessa_id)
            except SP.PortalError:
                abort(404)
        return render_template("selo_portal_remessa.html", r=r, SP=SP,
                               sv=serventia.dados(db.get_settings),
                               pode=usuario_papel() in GESTAO, hoje=_hoje())

    @app.route("/selos/portal/remessa/<int:remessa_id>/lista.csv")
    @roles_required(*VER)
    def selo_portal_remessa_csv(remessa_id: int):
        with db.connect() as con:
            try:
                corpo = SP.lista_csv(con, remessa_id)
            except SP.PortalError:
                abort(404)
        return Response(corpo, mimetype="text/csv; charset=utf-8", headers={
            "Content-Disposition": f'attachment; filename="selos_remessa_{remessa_id}.csv"'})

    @app.route("/selos/portal/remessa/<int:remessa_id>/pacote", methods=["POST"])
    @roles_required(*GESTAO)
    def selo_portal_remessa_pacote(remessa_id: int):
        try:
            with db.connect() as con:
                corpo = SP.montar_pacote(con, remessa_id)
        except SP.PortalError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("selo_portal_remessa", remessa_id=remessa_id))
        audit("SELO_GRATUIDADE_PACOTE_BAIXADO", "sd_portal_remessas", remessa_id,
              {"bytes": len(corpo)})
        return Response(corpo, mimetype="application/zip", headers={
            "Content-Disposition": f'attachment; filename="portal_do_selo_{remessa_id}.zip"',
            "Cache-Control": "no-store"})

    @app.route("/selos/portal/remessa/<int:remessa_id>/comunicado", methods=["POST"])
    @roles_required(*GESTAO)
    def selo_portal_remessa_comunicado(remessa_id: int):
        protocolo = (request.form.get("protocolo") or "").strip()
        try:
            with db.transaction() as con:
                SP.marcar_comunicado(con, remessa_id, agora=db.now(), usuario=usuario_nome(),
                                     protocolo=protocolo)
        except SP.PortalError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("selo_portal_remessa", remessa_id=remessa_id))
        audit("SELO_PORTAL_REMESSA_COMUNICADA", "sd_portal_remessas", remessa_id,
              {"protocolo": protocolo})
        flash("Marcado como enviado ao Tribunal.", "ok")
        return redirect(url_for("selo_portal_remessa", remessa_id=remessa_id))

    @app.route("/selos/portal/remessa/<int:remessa_id>/descartar", methods=["POST"])
    @roles_required(*GESTAO)
    def selo_portal_remessa_descartar(remessa_id: int):
        try:
            with db.transaction() as con:
                tipo = SP.descartar(con, remessa_id)
        except SP.PortalError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("selo_portal_remessa", remessa_id=remessa_id))
        audit("SELO_PORTAL_REMESSA_DESCARTADA", "sd_portal_remessas", remessa_id, {"tipo": tipo})
        flash("Rascunho descartado: os selos voltaram a faltar.", "ok")
        return redirect(url_for("selo_cancelamentos" if tipo == SP.CANCELAMENTO
                                else "selo_gratuidades_portal"))
