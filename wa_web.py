"""Telas e webhook do Balcao WhatsApp.

GET/POST /whatsapp/webhook — teste local e reenvio da caixa-postal.
  Sem login. CSRF isento. Em producao o inbound NAO chega direto aqui:
  o SERVIDOR do Cartorio Gestao nao expoe 8765 e nao roda tunel.

GET /whatsapp e as demais — mesmo login do resto do app.

UM RELOGIO SO PARA A CASA INTEIRA: as rotas passam `db.now()`, o mesmo que
grava o resto do sistema.
"""
from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, url_for

import serventia as SERV
import wa_balcao as WA
import wa_puxar as PUXAR


def registrar_rotas(app, db, login_required, roles_required, audit):
    """Pendura a fila do WhatsApp no app ja construido."""

    def _serventia() -> dict:
        return SERV.dados(db.get_settings)

    def _con():
        return db.connect()

    @app.route("/whatsapp/webhook", methods=["GET", "POST"])
    def whatsapp_webhook():
        """Callback da Cloud API. Sem login. CSRF isento neste endpoint.

        Producao: a Meta aponta para o worker na VPS (equipetextual.com.br), nao para aqui.
        Este POST so vale com X-Wa-Test (dev) ou HMAC se app_secret gravado.
        """
        if request.method == "GET":
            modo = (request.args.get("hub.mode") or "").strip()
            token = (request.args.get("hub.verify_token") or "").strip()
            challenge = request.args.get("hub.challenge") or ""
            with _con() as con:
                esperado = WA.verify_token_salvo(con)
            if modo == "subscribe" and token and token == esperado:
                return challenge, 200, {"Content-Type": "text/plain; charset=utf-8"}
            abort(403)

        header_teste = request.headers.get("X-Wa-Test", "")
        sig = request.headers.get("X-Hub-Signature-256", "")
        bruto = request.get_data(cache=True) or b""
        payload = request.get_json(silent=True)
        if payload is None:
            payload = {}
        with db.transaction() as con:
            if not WA.post_permitido(con, header_teste, bruto, sig):
                abort(403)
            resultado = WA.aplicar_entrada(con, payload,
                                           serventia=_serventia(),
                                           agora=db.now())
        try:
            audit("wa_entrada", "wa_conversa",
                  (resultado.get("conversa_ids") or [None])[0],
                  {"criadas": resultado.get("criadas"),
                   "repetidas": resultado.get("repetidas")})
        except Exception:                       # noqa: BLE001
            app.logger.exception(
                "a entrada do WhatsApp foi gravada, e a auditoria dela falhou")
        return ("", 200)

    @app.route("/whatsapp")
    @login_required
    def whatsapp_lista():
        with _con() as con:
            linhas = WA.listar_conversas(con)
            cfg = WA.config_para_tela(con)
        return render_template("whatsapp_lista.html", linhas=linhas, cfg=cfg)

    @app.route("/whatsapp/config", methods=["GET", "POST"])
    @login_required
    def whatsapp_config():
        if request.method == "POST":
            with db.transaction() as con:
                WA.gravar_tela_config(con, request.form)
            audit("wa_config", "wa_config", None, {"ok": True})
            flash("Configuracao do WhatsApp guardada. O token nao aparece no log.",
                  "success")
            return redirect(url_for("whatsapp_config"))
        with _con() as con:
            cfg = WA.config_para_tela(con)
        return render_template("whatsapp_config.html", cfg=cfg)

    @app.route("/whatsapp/puxar", methods=["POST"])
    @login_required
    def whatsapp_puxar():
        with db.transaction() as con:
            r = PUXAR.puxar_pendentes(
                con, serventia=_serventia(), agora=db.now())
        audit("wa_puxar", "wa_conversa", None,
              {"ok": r.get("ok"), "aplicadas": r.get("aplicadas")})
        if r.get("ok"):
            flash(
                f"Caixa-postal: {r.get('aplicadas') or 0} nova(s), "
                f"{r.get('repetidas') or 0} ja vista(s).",
                "success")
        else:
            flash(
                "Nao puxei a caixa-postal: "
                f"{r.get('motivo') or 'falhou'}. "
                "Cole https://equipetextual.com.br/pendentes em Configuracao.",
                "danger")
        return redirect(url_for("whatsapp_lista"))

    @app.route("/whatsapp/<int:conversa_id>")
    @login_required
    def whatsapp_conversa(conversa_id: int):
        with _con() as con:
            d = WA.conversa(con, conversa_id)
            pode = WA.pode_enviar_meta(con)
        if not d:
            abort(404)
        return render_template("whatsapp_conversa.html", c=d, pode_enviar=pode)

    @app.route("/whatsapp/<int:conversa_id>/rascunho", methods=["POST"])
    @login_required
    def whatsapp_salvar_rascunho(conversa_id: int):
        texto = (request.form.get("rascunho") or "").strip()
        with db.transaction() as con:
            if not WA.conversa(con, conversa_id):
                abort(404)
            WA.salvar_rascunho(con, conversa_id, texto, agora=db.now())
        audit("wa_rascunho", "wa_conversa", conversa_id, None)
        flash("Rascunho guardado. Nao foi enviado ao WhatsApp.", "success")
        return redirect(url_for("whatsapp_conversa", conversa_id=conversa_id))

    @app.route("/whatsapp/<int:conversa_id>/enviar", methods=["POST"])
    @login_required
    def whatsapp_enviar(conversa_id: int):
        try:
            with db.transaction() as con:
                if not WA.conversa(con, conversa_id):
                    abort(404)
                WA.enviar_rascunho(con, conversa_id, agora=db.now())
        except WA.EnvioErro as e:
            flash(str(e), "danger")
            return redirect(url_for("whatsapp_conversa", conversa_id=conversa_id)), 400
        audit("wa_enviar", "wa_conversa", conversa_id, {"ok": True})
        flash("Mensagem enviada no WhatsApp. Autoenvio continua desligado.",
              "success")
        return redirect(url_for("whatsapp_conversa", conversa_id=conversa_id))

    @app.route("/whatsapp/<int:conversa_id>/resolver", methods=["POST"])
    @login_required
    def whatsapp_resolver(conversa_id: int):
        with db.transaction() as con:
            if not WA.conversa(con, conversa_id):
                abort(404)
            WA.resolver(con, conversa_id, agora=db.now())
        audit("wa_resolver", "wa_conversa", conversa_id, None)
        flash("Conversa marcada como resolvida.", "success")
        return redirect(url_for("whatsapp_lista"))
