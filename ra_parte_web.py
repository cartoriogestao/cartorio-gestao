"""As telas das partes do registro do Livro 3.

A regra e as medições moram em `ra_parte.py`; aqui só se ligam os fios.
`audit` fica **fora** do `with db.transaction()`.
"""
from __future__ import annotations

from flask import abort, flash, redirect, request, url_for

import ra_parte as PT


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """A ASSINATURA É A DA CASA — ver `ajuda_web.registrar_rotas`."""

    def _campo(nome: str) -> str:
        return (request.form.get(nome) or "").strip()

    @app.route("/livro3/<int:registro_id>/partes", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def livro3_parte_acrescentar(registro_id: int):
        """Põe uma parte no registro — **sem elas o selo não sai**.

        Relato do oficial em 21/09/2026: *«não tem campo para partes»*. A
        tabela existia desde que o Livro 3 nasceu e **nenhuma tela escrevia
        nela** — vazia nos 14 registros.
        """
        try:
            with db.transaction() as con:
                parte_id = PT.acrescentar(
                    con, registro_id=registro_id, nome=_campo("nome"),
                    papel=_campo("papel"), documento=_campo("documento"))
        except PT.ParteError as erro:
            flash(str(erro), "danger")
        else:
            audit("RA_PARTE", "ra_partes", parte_id,
                  {"registro_id": registro_id, "papel": _campo("papel")})
            flash(f"{_campo('nome')} entrou como parte deste registro.",
                  "success")
        return redirect(url_for("livro3_registro", registro_id=registro_id))

    @app.route("/livro3/parte/<int:parte_id>/remover", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def livro3_parte_remover(parte_id: int):
        """Tira uma parte. Quem errou o nome tira e põe de novo."""
        try:
            with db.transaction() as con:
                registro_id = PT.remover(con, parte_id)
        except PT.ParteError as erro:
            flash(str(erro), "danger")
            abort(404)
        audit("RA_PARTE_REMOVIDA", "ra_partes", parte_id,
              {"registro_id": registro_id})
        flash("Parte retirada do registro.", "success")
        return redirect(url_for("livro3_registro", registro_id=registro_id))
