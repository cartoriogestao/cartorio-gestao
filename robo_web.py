"""Telas do gerenciador de robos (fatia 1).

GET/POST /robos* — mesmo login do resto do app.
Nunca grava no livro. Nunca autoenvia WhatsApp. Nunca loga API key.
UM RELOGIO SO: rotas passam `db.now()`.
"""
from __future__ import annotations

from flask import (abort, flash, redirect, render_template, request,
                   session, url_for)

import robo_llm as LLM
import robo_schema as SCH


def registrar_rotas(app, db, login_required, roles_required, audit):
    """Pendura o modulo de robos no app ja construido."""

    def _con():
        return db.connect()

    def _usuario() -> str:
        uid = session.get("user_id")
        if not uid:
            return ""
        user = db.get_user(int(uid))
        if not user:
            return ""
        return (user["username"] or user["full_name"] or "").strip()

    def _form_robo(form) -> dict:
        provedor = (form.get("provedor") or "grok").strip().lower()
        if provedor not in SCH.PROVEDORES:
            provedor = "grok"
        ativo = 1 if (form.get("ativo") in ("1", "on", "true", "True")) else 0
        return {
            "nome": (form.get("nome") or "").strip(),
            "ato": (form.get("ato") or "").strip(),
            "provedor": provedor,
            "prompt": (form.get("prompt") or "").strip(),
            "ativo": ativo,
        }

    @app.route("/robos")
    @login_required
    def robos_lista():
        with _con() as con:
            linhas = SCH.listar_robos(con)
        return render_template("robos_lista.html", linhas=linhas)

    @app.route("/robos/config", methods=["GET", "POST"])
    @login_required
    def robos_config():
        if request.method == "POST":
            with db.transaction() as con:
                SCH.gravar_tela_config(con, request.form)
            audit("robo_config", "robo_config", None, {"ok": True})
            flash("Configuracao dos robos guardada. A chave nao aparece no log.",
                  "success")
            return redirect(url_for("robos_config"))
        with _con() as con:
            cfg = SCH.config_para_tela(con)
        return render_template("robos_config.html", cfg=cfg)

    @app.route("/robos/novo", methods=["GET", "POST"])
    @login_required
    def robos_novo():
        if request.method == "POST":
            dados = _form_robo(request.form)
            if not dados["nome"] or not dados["ato"]:
                flash("Nome e ato sao obrigatorios.", "danger")
                return render_template(
                    "robos_form.html", robo=dados, novo=True,
                    exemplos=[], provedores=SCH.PROVEDORES), 400
            with db.transaction() as con:
                rid = SCH.criar_robo(con, agora=db.now(), **dados)
            audit("robo_criar", "robo", rid, {"nome": dados["nome"]})
            flash("Robo criado. Ainda nao grava no livro nem envia WhatsApp.",
                  "success")
            return redirect(url_for("robos_editar", robo_id=rid))
        vazio = {
            "nome": "", "ato": "", "provedor": "grok",
            "prompt": "", "ativo": 1,
        }
        return render_template(
            "robos_form.html", robo=vazio, novo=True,
            exemplos=[], provedores=SCH.PROVEDORES)

    @app.route("/robos/<int:robo_id>", methods=["GET", "POST"])
    @login_required
    def robos_editar(robo_id: int):
        if request.method == "POST":
            dados = _form_robo(request.form)
            if not dados["nome"] or not dados["ato"]:
                flash("Nome e ato sao obrigatorios.", "danger")
                with _con() as con:
                    exemplos = SCH.exemplos_do_robo(con, robo_id)
                return render_template(
                    "robos_form.html", robo={**dados, "id": robo_id},
                    novo=False, exemplos=exemplos,
                    provedores=SCH.PROVEDORES,
                    ultimo_teste=None), 400
            with db.transaction() as con:
                if not SCH.obter_robo(con, robo_id):
                    abort(404)
                SCH.atualizar_robo(con, robo_id, agora=db.now(), **dados)
            audit("robo_editar", "robo", robo_id, {"nome": dados["nome"]})
            flash("Robo atualizado.", "success")
            return redirect(url_for("robos_editar", robo_id=robo_id))

        with _con() as con:
            robo = SCH.obter_robo(con, robo_id)
            if not robo:
                abort(404)
            exemplos = SCH.exemplos_do_robo(con, robo_id)
        return render_template(
            "robos_form.html", robo=robo, novo=False,
            exemplos=exemplos, provedores=SCH.PROVEDORES,
            ultimo_teste=None)

    @app.route("/robos/<int:robo_id>/exemplos", methods=["POST"])
    @login_required
    def robos_exemplo_add(robo_id: int):
        entrada = (request.form.get("entrada") or "").strip()
        saida = (request.form.get("saida_esperada") or "").strip()
        try:
            peso = int(request.form.get("peso") or "1")
        except ValueError:
            peso = 1
        if not entrada or not saida:
            flash("Entrada e saida esperada sao obrigatorias.", "danger")
            return redirect(url_for("robos_editar", robo_id=robo_id))
        with db.transaction() as con:
            if not SCH.obter_robo(con, robo_id):
                abort(404)
            eid = SCH.adicionar_exemplo(con, robo_id, entrada, saida, peso)
        audit("robo_exemplo", "robo_exemplo", eid, {"robo_id": robo_id})
        flash("Exemplo adicionado.", "success")
        return redirect(url_for("robos_editar", robo_id=robo_id))

    @app.route("/robos/<int:robo_id>/exemplos/<int:exemplo_id>/apagar",
               methods=["POST"])
    @login_required
    def robos_exemplo_apagar(robo_id: int, exemplo_id: int):
        with db.transaction() as con:
            if not SCH.obter_robo(con, robo_id):
                abort(404)
            SCH.apagar_exemplo(con, robo_id, exemplo_id)
        audit("robo_exemplo_apagar", "robo_exemplo", exemplo_id,
              {"robo_id": robo_id})
        flash("Exemplo apagado.", "success")
        return redirect(url_for("robos_editar", robo_id=robo_id))

    @app.route("/robos/<int:robo_id>/testar", methods=["POST"])
    @login_required
    def robos_testar(robo_id: int):
        pedido = (request.form.get("pedido") or "").strip()
        if not pedido:
            flash("Informe o pedido para testar.", "danger")
            return redirect(url_for("robos_editar", robo_id=robo_id))
        with db.transaction() as con:
            robo = SCH.obter_robo(con, robo_id)
            if not robo:
                abort(404)
            exemplos_rows = SCH.exemplos_do_robo(con, robo_id)
            exemplos = [
                {"entrada": r["entrada"], "saida_esperada": r["saida_esperada"],
                 "peso": r["peso"]}
                for r in exemplos_rows
            ]
            api_key = SCH.api_key_do_provedor(con, robo["provedor"])
            resultado = LLM.rascunhar(
                robo, pedido, exemplos, api_key=api_key)
            SCH.registrar_teste(
                con,
                robo_id=robo_id,
                usuario=_usuario(),
                pedido=pedido,
                rascunho=resultado["texto"],
                modo=resultado["modo"],
                agora=db.now(),
            )
            exemplos_out = exemplos_rows
            robo_out = dict(robo)
        audit("robo_testar", "robo", robo_id,
              {"modo": resultado["modo"], "usuario": _usuario()})
        if resultado.get("aviso"):
            flash(resultado["aviso"], "warning")
        else:
            flash("Rascunho gerado via API (nao gravado no livro).", "success")
        return render_template(
            "robos_form.html",
            robo=robo_out,
            novo=False,
            exemplos=exemplos_out,
            provedores=SCH.PROVEDORES,
            ultimo_teste={
                "pedido": pedido,
                "rascunho": resultado["texto"],
                "modo": resultado["modo"],
                "aviso": resultado.get("aviso") or "",
            },
        )
