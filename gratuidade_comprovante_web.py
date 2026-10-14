"""O aviso insistente do comprovante da gratuidade, e a tela de subir.

Ordem do oficial em 11/10/2026: aviso ao USUÁRIO, não trava no ato. O ato se
pratica; quem obteve o selo isento vê, em TODA tela, a faixa vermelha até
guardar o comprovante. Mora no `base.html` pela razão do aviso do caixa: ligado
tela a tela, a próxima tela nasceria sem ele. O aviso só LÊ (GET não grava).
"""
from __future__ import annotations

import sqlite3

from flask import flash, redirect, render_template, request, session, url_for

import gratuidade_comprovante as GC

QUEM = ("ADMIN", "MANAGER", "USER")


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_id = app.extensions["usuario_id"]
    archive_root = app.extensions["archive_root"]
    current_user = app.extensions["current_user"]

    def _quem() -> tuple[str, str]:
        u = current_user()
        if not u:
            return "", ""
        return (u["full_name"] or ""), (u["username"] or "")

    def _pasta_proton():
        valor = str(db.get_setting("gratuidade_pasta_proton", "") or "").strip()
        return GC.Path(valor) if valor else GC.pasta_proton_padrao()

    @app.context_processor
    def _gratuidade_aviso() -> dict:
        vazio = {"gratuidade_aviso": 0}
        try:
            onde = request.endpoint or ""
        except RuntimeError:
            return vazio
        if not session.get("user_id") or onde in ("static", "login", "logout"):
            return vazio
        try:
            nome, username = _quem()
            with db.connect() as con:
                n = GC.quantos_pendentes(con, nome=nome, username=username)
        except (sqlite3.Error, RuntimeError, KeyError, TypeError):
            return vazio
        return {"gratuidade_aviso": n}

    @app.route("/gratuidades/comprovantes")
    @roles_required(*QUEM)
    def gratuidade_comprovantes():
        nome, username = _quem()
        with db.connect() as con:
            lista = GC.pendentes(con, nome=nome, username=username)
            inicio = GC.desde(con)
            feitos = GC.comprovados(con, nome=nome, username=username)  # HOTFIX-2026-10-13-07
        achados = GC.no_proton([p["numero"] for p in lista], _pasta_proton())
        return render_template("gratuidade_comprovantes.html", lista=lista, inicio=inicio, feitos=feitos,
                               achados={k: v.name for k, v in achados.items()})

    def _voltar():
        return redirect(url_for("gratuidade_comprovantes"))

    @app.route("/gratuidades/comprovantes/<int:selo_id>", methods=["POST"])
    @roles_required(*QUEM)
    def gratuidade_comprovante_subir(selo_id: int):
        # HOTFIX-2026-10-13-07: varios arquivos de uma vez; nunca apaga os que ja ha.
        arquivos = [a for a in request.files.getlist("arquivo") if a and a.filename]
        if not arquivos:
            flash("Escolha o arquivo do comprovante.", "danger")
            return _voltar()
        ids = []
        try:
            with db.transaction() as con:
                for arquivo in arquivos:
                    ids.append(GC.guardar(con, selo_id, nome_arquivo=arquivo.filename,
                                          conteudo=arquivo.read(),
                                          pasta=archive_root() / "gratuidades",
                                          usuario_id=usuario_id(), agora=db.now()))
        except GC.ComprovanteError as erro:
            flash(f"{erro} Nenhum arquivo deste envio foi guardado.", "danger")
            return _voltar()
        audit("GRATUIDADE_COMPROVANTE_GUARDADO", "sd_selos", selo_id, {"anexos": ids})
        flash(f"{len(ids)} comprovante(s) guardado(s).", "ok")
        return _voltar()

    @app.route("/gratuidades/comprovantes/<int:selo_id>/proton", methods=["POST"])
    @roles_required(*QUEM)
    def gratuidade_comprovante_do_proton(selo_id: int):
        """Traz o arquivo do Proton cujo nome tem o código deste selo."""
        with db.connect() as con:
            row = con.execute("SELECT numero FROM sd_selos WHERE id=?", (selo_id,)).fetchone()
        achado = GC.no_proton([row[0]], _pasta_proton()).get(row[0].upper()) if row else None
        if not achado:
            flash("Não achei no Proton um arquivo com o código deste selo no nome.", "danger")
            return _voltar()
        try:
            with db.transaction() as con:
                aid = GC.guardar(con, selo_id, nome_arquivo=achado.name,
                                 conteudo=achado.read_bytes(),
                                 pasta=archive_root() / "gratuidades", usuario_id=usuario_id(),
                                 agora=db.now(), origem="Proton")
        except GC.ComprovanteError as erro:
            flash(str(erro), "danger")
            return _voltar()
        audit("GRATUIDADE_COMPROVANTE_GUARDADO", "sd_selos", selo_id,
              {"anexo": aid, "origem": "Proton", "arquivo": achado.name})
        flash(f"Comprovante trazido do Proton ({achado.name}).", "ok")
        return _voltar()
