# -*- coding: utf-8 -*-
"""Tela dos modelos de averbacao com formulario proprio (HOTFIX-2026-10-09-04).

So LE o banco. O POST "Gerar texto" mostra a previa numa caixa EDITAVEL (relato
#127, 15/10/2026); "Levar para a averbacao" guarda o texto da caixa, como o
escrevente o deixou, na sessao e abre /rcpn/<id>/averbar ja preenchido - o
lancamento (e o selo) continuam sendo o botao da tela padrao, pelo escrevente.
As rotas se chamam `rcpn_*` para cair no modulo RCPN do menu/permissoes.
"""
from __future__ import annotations

import sqlite3

from flask import flash, redirect, render_template, request, session, url_for

import rc_averbacao_modelos as RAM

QUEM_USA = ("ADMIN", "MANAGER", "USER")


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=None):

    @app.context_processor
    def _modelos_de_averbacao():
        return {"modelos_de_averbacao": RAM.listar}

    def _usuario(con) -> dict:
        uid = session.get("user_id")
        if not uid:
            return {}
        try:
            import sqlite_esquema
            cols = sqlite_esquema.colunas(con, "users")
            sel = "full_name, username" + (", funcao" if "funcao" in cols else "")
            r = con.execute(f"SELECT {sel} FROM users WHERE id=?", (uid,)).fetchone()
        except sqlite3.Error:
            return {}
        if not r:
            return {}
        return {"nome": (r["full_name"] or r["username"] or "").strip(),
                "funcao": (r["funcao"] if "funcao" in r.keys() else "") or ""}

    @app.route("/rcpn/<int:assento_id>/averbar/modelo/<slug>", methods=["GET", "POST"])
    @login_required
    @roles_required(*QUEM_USA)
    def rcpn_averbacao_modelo(assento_id: int, slug: str):
        try:
            m = RAM.modelo(slug)
        except RAM.ModeloErro as e:
            flash(str(e), "danger")
            return redirect(url_for("rcpn_averbar", assento_id=assento_id))
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            linha = con.execute("SELECT * FROM rc_assentos WHERE id=?",
                                (assento_id,)).fetchone()
            if not linha:
                flash("Assento não encontrado.", "danger")
                return redirect(url_for("rcpn_assentos"))
            assento = dict(linha)
            if assento.get("situacao") != "ATIVO":
                flash("Só é possível averbar em assento ativo.", "danger")
                return redirect(url_for("rcpn_assento", assento_id=assento_id))
            if str(assento.get("especie") or "").upper() not in m["especies"]:
                flash("Este modelo não serve para a espécie deste assento.", "danger")
                return redirect(url_for("rcpn_averbar", assento_id=assento_id))
            if request.method == "GET":
                valores = RAM.sugestoes(con, slug, assento, _usuario(con))
            else:
                valores = RAM.valores_do_formulario(slug, request.form)
        previa = None
        if request.method == "POST":
            acao = request.form.get("acao")
            # O texto da prévia é editável (relato #127, 15/10/2026: «tela não tem
            # edição de texto»). Em «Levar» vai o que o escrevente deixou na caixa,
            # e NÃO o texto remontado — senão a correção dele se perderia calada.
            # Em «Gerar texto» o modelo remonta, e a tela avisa disso.
            teor_editado = str(request.form.get("teor") or "").strip()
            fund_editado = str(request.form.get("fundamento_ato") or "").strip()
            try:
                previa = RAM.montar(slug, valores, assento)
            except RAM.ModeloErro as e:
                flash(str(e), "danger")
                if acao == "levar" and teor_editado:
                    # Recusa não apaga o que foi editado: a caixa volta com o texto.
                    previa = {"teor": teor_editado, "fundamento": fund_editado,
                              "natureza": "retificacao", "recusado": True}
            if previa and not previa.get("recusado") and acao == "levar":
                editou = bool(teor_editado) and teor_editado != previa["teor"]
                session[RAM.CHAVE_DA_SESSAO] = {
                    "assento_id": assento_id,
                    "teor": teor_editado or previa["teor"],
                    "fundamento": fund_editado or previa["fundamento"],
                    "natureza": previa["natureza"], "modelo": slug, "editado": editou}
                flash("Texto do modelo levado para a averbação"
                      + (", com as suas alterações" if editou else "")
                      + ". Confira antes de lançar.", "info")
                return redirect(url_for("rcpn_averbar", assento_id=assento_id))
        return render_template("atrib_rcpn_averbacao_modelo.html", assento=assento,
                               modelo=m, valores=valores, previa=previa)
