"""Rotas web — Projetos de desenvolvimento (ADMIN e MANAGER).

O QUE NÃO CABE À GESTÃO (25/11/2026, T019)
    «permitir que retiremos [...] dos projetos itens que nao cabem a gestao ou
    admin» — o oficial. «Retirar dos projetos da gestão», na ficha do projeto,
    pede o motivo e tira o projeto da lista principal (`gestao_retirados`, chave
    = id do projeto); «Ver os retirados» lista quem retirou, quando e por quê,
    com «Devolver à lista». Não apaga o projeto, a etapa nem o histórico, e a
    ficha continua abrindo. Retirar e devolver gravam na auditoria.
"""
from __future__ import annotations

from typing import Callable

import dev_projetos as DP
import gestao_retirados as GR


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
    audit: Callable | None = None,
) -> None:
    # Quem retira: o nome e o id, como o «conferido hoje» da checklist grava.
    _quem = app.extensions.get("usuario_nome") or (lambda: current_user_login() or "?")
    _uid = app.extensions.get("usuario_id") or (lambda: None)

    def _auditar(acao: str, projeto_id: int, detalhes: dict) -> None:
        if audit is not None:
            audit(acao, "dev_projetos", projeto_id, detalhes)

    @app.route("/desenvolvimento/projetos")
    @login_required
    @roles_required("ADMIN", "MANAGER")
    def dev_projetos_lista():
        with get_db() as con:
            if is_sandbox(con):
                DP.seed_sandbox_exemplo(con)
                DP.aplicar_atualizacao_pendencias_20261001(con)
                con.commit()
            todos = DP.listar_projetos(con)
            retiradas = GR.ativas(con, GR.PROJETOS)
        projetos = [p for p in todos if str(p["id"]) not in retiradas]
        retirados = [{**p, "retirada": retiradas[str(p["id"])]}
                     for p in todos if str(p["id"]) in retiradas]
        return render_template(
            "dev_projetos_lista.html",
            projetos=projetos,
            retirados=retirados,
            ver_retirados=request.args.get("ver") == "retirados",
            status_rotulo=DP.STATUS_ROTULO,
        )

    @app.route("/desenvolvimento/projetos/<int:projeto_id>")
    @login_required
    @roles_required("ADMIN", "MANAGER")
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
            retirada = GR.ativas(con, GR.PROJETOS).get(str(projeto_id))
        return render_template(
            "dev_projeto_detalhe.html",
            projeto=projeto,
            andamentos=andamentos,
            retirada=retirada,
            motivos_prontos=GR.MOTIVOS_PRONTOS,
            motivo_maximo=GR.MOTIVO_MAXIMO,
            status_rotulo=DP.STATUS_ROTULO,
            status_validos=sorted(DP.STATUS_VALIDOS),
        )

    @app.route("/desenvolvimento/projetos/<int:projeto_id>/status", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER")
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
    @roles_required("ADMIN", "MANAGER")
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
    @roles_required("ADMIN", "MANAGER")
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

    @app.route("/desenvolvimento/projetos/<int:projeto_id>/retirar", methods=["POST"])
    @login_required
    @roles_required(*GR.QUEM_RETIRA)
    def dev_projetos_retirar(projeto_id: int):
        """Retira o projeto da lista: não cabe à gestão. Não apaga nada."""
        with get_db() as con:
            projeto = DP.obter_projeto(con, projeto_id)
            if not projeto:
                abort(404)
            try:
                r = GR.retirar(con, GR.PROJETOS, str(projeto_id),
                               motivo=request.form.get("motivo"),
                               motivo_codigo=request.form.get("motivo_codigo"),
                               por=_quem(), usuario_id=_uid())
                con.commit()
            except GR.RetiradaError as erro:
                flash(str(erro), "warning")
                return redirect(url_for("dev_projetos_detalhe", projeto_id=projeto_id))
        if not r["gravou"]:
            flash(f"O projeto já tinha sido retirado por {r['retirada']['por']}.", "info")
            return redirect(url_for("dev_projetos_detalhe", projeto_id=projeto_id))
        _auditar("DEV_PROJETO_RETIRADO", projeto_id,
                 {"titulo": projeto["titulo"], "motivo_codigo": r["retirada"]["motivo_codigo"],
                  "motivo": r["retirada"]["motivo"]})
        flash(f"«{projeto['titulo']}» saiu dos projetos da gestão. Nada foi apagado: "
              "está em «Ver os retirados».", "success")
        return redirect(url_for("dev_projetos_lista"))

    @app.route("/desenvolvimento/projetos/<int:projeto_id>/devolver", methods=["POST"])
    @login_required
    @roles_required(*GR.QUEM_RETIRA)
    def dev_projetos_devolver(projeto_id: int):
        """Devolve o projeto retirado à lista principal."""
        with get_db() as con:
            projeto = DP.obter_projeto(con, projeto_id)
            if not projeto:
                abort(404)
            r = GR.devolver(con, GR.PROJETOS, str(projeto_id),
                            por=_quem(), usuario_id=_uid())
            con.commit()
        if r:
            _auditar("DEV_PROJETO_DEVOLVIDO", projeto_id,
                     {"titulo": projeto["titulo"], "retirado_por": r["por"],
                      "retirado_em": r["em"]})
            flash(f"«{projeto['titulo']}» voltou aos projetos da gestão.", "success")
        else:
            flash("Este projeto não estava retirado.", "info")
        return redirect(url_for("dev_projetos_lista", ver="retirados"))
