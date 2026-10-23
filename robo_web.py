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
from seguranca_web import PRATICA  # M2 (LX11): o AUDITOR vê e não grava
from seguranca_web import MAIOR_INTEGER, numero_digitado  # LD13: o número que a tela mandou


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
            # GRAVAR A CHAVE É SÓ DO ADMIN (LS01, 19/10/2026); ver a tela
            # (mascarada) segue de todos. Aberta a qualquer login, quem
            # estivesse no balcão punha a chave da própria conta no provedor,
            # e o que os robôs mandam passava a cair no histórico dele — ou
            # apagava o uso de todos com uma chave qualquer. É a regra da chave
            # do Claude e das Centrais: credencial, só ADMIN.
            if app.extensions["usuario_papel"]() != "ADMIN":
                abort(403)
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
    @roles_required(*PRATICA, metodos=("POST",))
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
    @roles_required(*PRATICA, metodos=("POST",))
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
    @roles_required(*PRATICA)
    def robos_exemplo_add(robo_id: int):
        entrada = (request.form.get("entrada") or "").strip()
        saida = (request.form.get("saida_esperada") or "").strip()
        # `robo_exemplo.peso` é `integer`: o que não é número, ou não cabe
        # nele, vale o padrão da tela (LD13) — o número grande derrubava o INSERT.
        peso = numero_digitado(request.form.get("peso") or "1", maximo=MAIOR_INTEGER)
        if peso is None:
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
    @roles_required(*PRATICA)
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
    @roles_required(*PRATICA)
    def robos_testar(robo_id: int):
        pedido = (request.form.get("pedido") or "").strip()
        if not pedido:
            flash("Informe o pedido para testar.", "danger")
            return redirect(url_for("robos_editar", robo_id=robo_id))
        # A REDE FICA FORA DA TRANSAÇÃO (LF01, 19/10/2026). O rascunho era
        # pedido dentro do `db.transaction()`, com a trava única do banco presa
        # durante a chamada ao provedor — o balcão esperava o provedor para
        # gravar, e o registro do uso de IA (`ia_uso`, conexão própria) nunca
        # entraria. Agora: lê, chama, e só então grava o teste.
        with db.connect() as con:
            robo = SCH.obter_robo(con, robo_id)
            if not robo:
                abort(404)
            exemplos_rows = SCH.exemplos_do_robo(con, robo_id)
            api_key = SCH.api_key_do_provedor(con, robo["provedor"])
        # O PEDIDO SOBE MASCARADO (M5 do LS03; LX13, 19/10/2026). Ia em claro,
        # e o balcão digita aqui o caso real — nome, CPF, telefone de quem
        # pediu. Passa pela MESMA barreira da triagem do malote
        # (`gestor_expedientes.mascarar`), que guarda o caminho de volta: o
        # rascunho volta com marcas, e só a TELA de quem testou o vê com os
        # nomes. Os exemplos do robô também sobem mascarados; o prompt não,
        # porque é configuração escrita pela casa, e não dado de pessoa.
        import gestor_expedientes as GE
        from ajuda_privacidade import PrivacidadeError, sanitizar_para_modelo
        try:
            seguro, originais = GE.mascarar(pedido)
            exemplos = [
                {"entrada": sanitizar_para_modelo(r["entrada"]),
                 "saida_esperada": sanitizar_para_modelo(r["saida_esperada"]),
                 "peso": r["peso"]}
                for r in exemplos_rows
            ]
            recusa = ""
        except PrivacidadeError:
            seguro, originais, exemplos = "", {}, []
            recusa = ("O pedido ou um exemplo do robô tem dado de pessoa que a "
                      "máscara não sabe tirar — nada foi enviado ao provedor. "
                      "Reescreva sem o dado e teste de novo.")
        # O TETO DO DIA (B5 do LS03): o teste do robô não é atendimento, e um
        # clique repetido não pode virar conta.
        import ia_uso as USO
        with db.connect() as con:
            recusa = recusa or USO.passou_do_teto(con, "robo_rascunho") or ""
        if recusa:
            resultado = {"texto": "", "modo": SCH.MODO_LOCAL, "aviso": recusa}
        else:
            resultado = LLM.rascunhar(
                robo, seguro, exemplos, api_key=api_key,
                pasta_de_dados=app.config.get("DATA_DIR"), modulo="robo_web",
                finalidade="robo_rascunho", usuario=_usuario(),
                referencia=f"robo:{robo_id}", mascarado=True)
        with db.transaction() as con:
            if not SCH.obter_robo(con, robo_id):
                abort(404)
            # O REGISTRO GUARDA A FORMA MASCARADA, que é a que saiu; o pedido
            # recusado não se guarda — é justamente o que tinha o dado.
            SCH.registrar_teste(
                con,
                robo_id=robo_id,
                usuario=_usuario(),
                pedido=seguro if not recusa else "(não enviado: recusado antes da rede)",
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
                "rascunho": GE.desmascarar(resultado["texto"], originais),
                "modo": resultado["modo"],
                "aviso": resultado.get("aviso") or "",
            },
        )
