"""As telas das notas de revisão do Livro 3.

A regra mora em `ra_revisao.py`; aqui só se ligam os fios. `audit` fica **fora**
do `with db.transaction()`.
"""
from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, url_for

import ra_revisao as RV


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """A ASSINATURA É A DA CASA — ver `ajuda_web.registrar_rotas`."""

    usuario_nome = app.extensions["usuario_nome"]

    def _campo(nome: str) -> str:
        return (request.form.get(nome) or "").strip()

    def _numero(nome: str):
        bruto = "".join(c for c in _campo(nome) if c.isdigit())
        return int(bruto) if bruto else None

    @app.route("/livro3/revisoes")
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def livro3_revisoes():
        """O que falta conferir no Livro 3, da casa inteira."""
        with db.connect() as con:
            notas = RV.abertas(con)
        return render_template("livro3_revisoes.html", notas=notas,
                               fmt_date=fmt_date)

    @app.route("/livro3/<int:registro_id>/revisoes", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def livro3_revisao_anotar(registro_id: int):
        """Anota o que precisa ser conferido antes de selar.

        **A nota não trava nada** — quem decide se o ato sai é quem assina.
        """
        try:
            with db.transaction() as con:
                nota_id = RV.anotar(
                    con, registro_id=registro_id, assunto=_campo("assunto"),
                    nota=_campo("nota"), agora=db.now(),
                    ato_id=_numero("ato_id"), minuta_id=_numero("minuta_id"),
                    usuario=usuario_nome())
        except RV.RevisaoError as erro:
            flash(str(erro), "danger")
        else:
            audit("RA_REVISAO_ANOTAR", "ra_revisoes", nota_id,
                  {"registro_id": registro_id, "assunto": _campo("assunto")[:200]})
            flash("Anotado. A nota fica na ficha até alguém conferir — ela não "
                  "impede lavrar nem selar.", "success")
        return redirect(url_for("livro3_registro", registro_id=registro_id))

    @app.route("/livro3/revisao/<int:revisao_id>/baixar", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def livro3_revisao_baixar(revisao_id: int):
        """Fecha a nota, com o que se decidiu escrito dentro."""
        with db.connect() as con:
            linha = con.execute(
                "SELECT registro_id FROM ra_revisoes WHERE id=?",
                (revisao_id,)).fetchone()
        if not linha:
            abort(404)
        decisao = _campo("decisao")
        try:
            with db.transaction() as con:
                RV.baixar(con, revisao_id, decisao=decisao, agora=db.now(),
                          usuario=usuario_nome())
        except RV.RevisaoError as erro:
            flash(str(erro), "danger")
        else:
            audit("RA_REVISAO_BAIXAR", "ra_revisoes", revisao_id,
                  {"decisao": decisao[:200]})
            flash("Nota baixada, com o que você decidiu escrito nela.",
                  "success")
        return redirect(request.form.get("voltar")
                        or url_for("livro3_registro",
                                   registro_id=linha["registro_id"]))
