"""Rotas web — Projetos de desenvolvimento (ADMIN)."""
from __future__ import annotations

from typing import Callable

import dev_projetos as DP


def register_dev_projetos_routes(
    app,
    *,
    login_required,
    roles_required,
    get_db,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    abort,
    is_sandbox: Callable,
    current_user_login: Callable[[], str | None],
) -> None:
    @app.route("/desenvolvimento/projetos")
    @login_required
    @roles_required("ADMIN")
    def dev_projetos_lista():
        with get_db() as con:
            if is_sandbox(con):
                DP.seed_sandbox_exemplo(con)
                DP.aplicar_atualizacao_pendencias_20261001(con)
                con.commit()
            projetos = DP.listar_projetos(con)
        return render_template(
            "dev_projetos_lista.html",
            projetos=projetos,
            status_rotulo=DP.STATUS_ROTULO,
        )

    @app.route("/desenvolvimento/projetos/<int:projeto_id>")
    @login_required
    @roles_required("ADMIN")
    def dev_projetos_detalhe(projeto_id: int):
        with get_db() as con:
            if is_sandbox(con):
                DP.seed_sandbox_exemplo(con)
                DP.aplicar_atualizacao_pendencias_20261001(con)
                con.commit()
            projeto = DP.obter_projeto(con, projeto_id)
            if not projeto:
                abort(404)
            andamentos = DP.listar_andamento(con, projeto_id)
        return render_template(
            "dev_projeto_detalhe.html",
            projeto=projeto,
            andamentos=andamentos,
            status_rotulo=DP.STATUS_ROTULO,
            status_validos=sorted(DP.STATUS_VALIDOS),
        )

    @app.route("/desenvolvimento/projetos/<int:projeto_id>/status", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def dev_projetos_alterar_status(projeto_id: int):
        status = (request.form.get("status_geral") or "").strip()
        with get_db() as con:
            try:
                DP.alterar_status(con, projeto_id, status)
                con.commit()
                flash("Status atualizado.", "success")
            except (LookupError, ValueError) as erro:
                flash(str(erro), "warning")
        return redirect(url_for("dev_projetos_detalhe", projeto_id=projeto_id))

    @app.route(
        "/desenvolvimento/projetos/<int:projeto_id>/proximo-passo",
        methods=["POST"],
    )
    @login_required
    @roles_required("ADMIN")
    def dev_projetos_alterar_proximo_passo(projeto_id: int):
        texto = request.form.get("proximo_passo")
        with get_db() as con:
            try:
                DP.alterar_proximo_passo(con, projeto_id, texto)
                con.commit()
                flash("Próximo passo / pendência salvo.", "success")
            except LookupError as erro:
                flash(str(erro), "warning")
        return redirect(url_for("dev_projetos_detalhe", projeto_id=projeto_id))

    @app.route("/desenvolvimento/projetos/<int:projeto_id>/andamento", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def dev_projetos_novo_andamento(projeto_id: int):
        texto = request.form.get("texto") or ""
        autor = current_user_login()
        with get_db() as con:
            try:
                DP.registrar_andamento(con, projeto_id, texto, autor=autor)
                con.commit()
                flash("Andamento registrado.", "success")
            except (LookupError, ValueError) as erro:
                flash(str(erro), "warning")
        return redirect(url_for("dev_projetos_detalhe", projeto_id=projeto_id))