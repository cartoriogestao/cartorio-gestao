"""A tela do andamento dos títulos do RI no Acompanhamento de Títulos do ONR.

    Pedido de 26/10/2026 — ver o cabeçalho de `onr_acompanhamento`.

O QUE ELA FAZ
    Mostra a fila (o que espera subir, com o motivo de quem espera), o que já
    subiu e o que foi anulado ou descartado; e tem três botões:

    - **Enviar pendentes** (ADMIN e MANAGER): manda a fila ao ONR. Só com o
      envio LIGADO — sem isso, recusa e diz onde ligar.
    - **Ligar / desligar o envio** (ADMIN): a chave `onr_acompanhamento_ligado`.
      Desligado de fábrica: andamento na Central é publicidade, e quem decide
      quando começa é quem responde pela serventia.
    - **Descartar** um pendente, com motivo (ADMIN): o que não deve ir.

O ENCAIXE NA AUTOMAÇÃO (declarado)
    A central de automação (PR #11) ainda não está no `main`. Quando estiver, a
    rotina dela chama exatamente `ACOMP.enviar_pendentes(db, sessao, amb=...,
    quem="automação", agora=db.now)` — a mesma função deste botão — e a chave
    `onr_acompanhamento_ligado` continua sendo a trava. Nada aqui precisa
    mudar para isso.

A REDE ACONTECE FORA DE `db.transaction()` — `enviar_pendentes` abre as suas
transações curtas DEPOIS de cada resposta do ONR.
"""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for

import onr_acompanhamento as ACOMP
import onr_wsoficio as WS
from seguranca_web import numero_digitado


def registrar_rotas(app, db, login_required, roles_required, audit):
    usuario_nome = app.extensions["usuario_nome"]

    with db.connect() as con:
        ACOMP.init_schema(con)

    def _amb() -> str:
        return ACOMP.ambiente(db.get_setting)

    @app.route("/ri/onr/acompanhamento")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def onr_acompanhamento():
        todos = request.args.get("todos") == "1"
        with db.connect() as con:
            dados = ACOMP.painel(con, todos=todos)
        return render_template("onr_acompanhamento.html", todos=todos,
                               ambiente=_amb(), ligado=ACOMP.ligado(db.get_setting),
                               credencial=WS.situacao(_amb()), **dados)

    @app.route("/ri/onr/acompanhamento/enviar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def onr_acompanhamento_enviar():
        if not ACOMP.ligado(db.get_setting):
            flash("O envio do andamento ao ONR está desligado. Quem liga é o oficial, "
                  "nesta mesma tela — nada foi enviado.", "danger")
            return redirect(url_for("onr_acompanhamento"))
        amb = _amb()
        try:
            feito = ACOMP.enviar_pendentes(
                db, lambda: WS.Sessao(ambiente=amb), amb=amb,
                quem=(usuario_nome() or "").strip() or "?", agora=db.now)
        except (ACOMP.AcompanhamentoError, WS.WSOficioError) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("onr_acompanhamento"))
        audit("ONR_ACOMPANHAMENTO_ENVIADO", "onr_at_eventos", None, dict(feito, ambiente=amb))
        frase = (f"ONR ({amb.lower()}): {feito['enviados']} andamento(s) enviado(s), "
                 f"{feito['titulos_novos']} título(s) cadastrado(s), "
                 f"{feito['esperando']} esperando, {feito['recusados']} recusado(s), "
                 f"{feito['anulados']} anulado(s).")
        if feito["parou"]:
            flash(frase + f" A rodada parou: {feito['parou']}", "danger")
        else:
            flash(frase, "ok" if not feito["recusados"] else "warning")
        return redirect(url_for("onr_acompanhamento"))

    @app.route("/ri/onr/acompanhamento/ligar", methods=["POST"])
    @roles_required("ADMIN")
    def onr_acompanhamento_ligar():
        valor = "1" if request.form.get("ligar") == "1" else "0"
        db.set_settings({ACOMP.CHAVE_LIGADO: valor})
        audit("ONR_ACOMPANHAMENTO_LIGADO" if valor == "1" else "ONR_ACOMPANHAMENTO_DESLIGADO",
              "settings", None, {"ambiente": _amb()})
        flash("Envio do andamento ao ONR LIGADO." if valor == "1" else
              "Envio do andamento ao ONR desligado. A fila continua se anotando.", "ok")
        return redirect(url_for("onr_acompanhamento"))

    @app.route("/ri/onr/acompanhamento/<int:evento_id>/descartar", methods=["POST"])
    @roles_required("ADMIN")
    def onr_acompanhamento_descartar(evento_id: int):
        motivo = (request.form.get("motivo") or "").strip()
        try:
            with db.transaction() as con:
                ev = ACOMP.descartar(con, evento_id, motivo=motivo,
                                     quem=(usuario_nome() or "").strip(), agora=db.now())
        except ACOMP.AcompanhamentoError as erro:
            flash(str(erro), "danger")
        else:
            audit("ONR_ACOMPANHAMENTO_DESCARTADO", "RI_PROTOCOLO", ev["protocolo_id"],
                  {"evento": ev["chave"], "motivo": motivo})
            flash("Andamento descartado: não vai ao ONR.", "ok")
        volta = numero_digitado(request.form.get("protocolo_id"))
        if volta is not None:
            return redirect(url_for("ri_protocolo_ver", protocolo_id=volta))
        return redirect(url_for("onr_acompanhamento"))
