"""As telas da e-Intimação do RI pelo ONR — ver `onr_intimacoes.py`.

    /ri/onr/intimacoes              a lista lida, a tabela de status e o que conta como parado
    /ri/onr/intimacoes/<id>         a ficha de um pedido (o que a lista trouxe)
    /ri/onr/intimacoes/ler          a MESMA leitura do processo, na hora (só lê o ONR)
    /ri/onr/intimacoes/regra        quais status contam como parados (só o ADMIN)

A rede acontece fora de `db.transaction()`, em `onr_intimacoes.ler`.
"""
from __future__ import annotations

from datetime import datetime

from flask import abort, flash, redirect, render_template, request, url_for

import onr_intimacoes as IN
import onr_wsoficio as WS

QUEM = ("ADMIN", "MANAGER", "USER", "AUDITOR")
QUEM_LE = ("ADMIN", "MANAGER", "USER")


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    with db.connect() as con:
        IN.init_schema(con)

    def amb() -> str:
        return IN.ambiente(db.get_setting)

    @app.route("/ri/onr/intimacoes")
    @login_required
    @roles_required(*QUEM)
    def onr_intimacoes():
        a = amb()
        with db.connect() as con:
            q = IN.quadro(con, a, db.get_setting)
        return render_template("onr_intimacoes.html", q=q, ambiente=a, processo=IN.CATALOGO[0],
                               credencial=WS.situacao(a))

    @app.route("/ri/onr/intimacoes/<int:pedido_id>")
    @login_required
    @roles_required(*QUEM)
    def onr_intimacao_ficha(pedido_id: int):
        a = amb()
        with db.connect() as con:
            try:
                p = IN.pedido(con, pedido_id)
            except IN.IntimacaoOnrError:
                abort(404)
            regra = IN.regra_dos_parados(con, a, db.get_setting)
        nomes = {int(s["id_status"]): s["nome"] for s in regra["status"]}
        return render_template("onr_intimacao_ficha.html", p=p,
                               nome_status=nomes.get(p["id_status"], f"status {p['id_status']}"),
                               parado=p["id_status"] in regra["ids"], regra=regra)

    @app.route("/ri/onr/intimacoes/ler", methods=["POST"])
    @login_required
    @roles_required(*QUEM_LE)
    def onr_intimacoes_ler():
        """A MESMA leitura do processo. Só GET no ONR (List*); nada se responde."""
        a = amb()

        def agora() -> str:
            return datetime.now().replace(microsecond=0).isoformat()

        r = IN.ler(db, a, hoje=datetime.now().date(), agora=agora, origem=IN.ORIGEM_TELA)
        audit("ONR_INTIMACOES_LIDAS", "ONR_INTIMACOES", r.get("leitura_id"),
              {k: r.get(k) for k in ("situacao", "listados", "novos", "mudaram")})
        if r["situacao"] == "ERRO":
            flash(f"A leitura da e-Intimação não terminou: {r['erro']}", "danger")
        else:
            flash(f"e-Intimação lida: {r['listados']} pedido(s) na lista, {r['novos']} novo(s), "
                  f"{r['mudaram']} mudaram de status.", "ok")
        return redirect(url_for("onr_intimacoes"))

    @app.route("/ri/onr/intimacoes/regra", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def onr_intimacoes_regra():
        """Quais status contam como parados. ESCREVE só esta chave."""
        a = amb()
        if request.form.get("acao") == "sugestao":
            valor = ""
        else:
            with db.connect() as con:
                status = IN.status_lidos(con, a)
            try:
                valor = IN.guardar_regra(request.form.getlist("status"), status)
            except IN.IntimacaoOnrError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("onr_intimacoes") + "#regra")
        antes = str(db.get_setting(IN.CHAVE_STATUS_PARADOS, "") or "")
        db.set_settings({IN.CHAVE_STATUS_PARADOS: valor})
        audit("SETTINGS_CHANGED", "SETTINGS", None,
              {IN.CHAVE_STATUS_PARADOS: valor, "antes": antes})
        flash("Status que contam como parados gravados." if valor else
              "Os status parados voltaram à sugestão pelo nome.", "success")
        return redirect(url_for("onr_intimacoes") + "#regra")
