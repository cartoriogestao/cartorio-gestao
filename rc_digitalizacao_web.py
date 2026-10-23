"""As telas do termo assinado digitalizado do RCPN — problema #121.

A rota só liga os fios; a regra mora em `rc_digitalizacao`. O desenho é o das
rotas da digitalização do RI (`ri_web`, «digitalizacao oficial»): enviar,
abrir/baixar o arquivo, miniatura da primeira página — mais a lista dos
registros lavrados que ainda esperam o termo, e o aviso vermelho quando o
prazo de 7 dias venceu, como `ri_digi_prazo_web`.
"""
from __future__ import annotations

import mimetypes
import sqlite3
from pathlib import Path

from flask import (
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import rc_digitalizacao as RCDIGI
import ri_digitalizacao as RDIGI


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):

    def _usuario() -> str:
        quem = app.extensions.get("usuario_nome")
        return quem() if quem else (session.get("username") or "")

    @app.context_processor
    def _rc_digi() -> dict:
        """A ficha do assento recebe a situação do termo; as telas do Registro
        Civil recebem o aviso vermelho dos vencidos. Só LÊ, e nunca derruba a
        tela: aviso que falha não pode virar HTTP 500 no balcão."""
        vazio = {"rc_digi_ficha": None, "rc_digi_aviso": None}
        try:
            onde = request.endpoint or ""
        except RuntimeError:
            return vazio
        if not session.get("user_id") or not onde.startswith("rcpn"):
            return vazio
        saida = dict(vazio)
        try:
            with db.connect() as con:
                if onde == "rcpn_assento":
                    aid = (request.view_args or {}).get("assento_id")
                    if aid:
                        ficha = RCDIGI.situacao(con, int(aid))
                        if ficha is not None:
                            ficha["guardados"] = RCDIGI.guardados(
                                RCDIGI.raiz_arquivos(db), int(aid))
                        saida["rc_digi_ficha"] = ficha
                if onde != "rcpn_termos_a_digitalizar":
                    vencidas = [p for p in RCDIGI.pendentes(con) if p["vencida"]]
                    if vencidas:
                        saida["rc_digi_aviso"] = {"vencidas": vencidas}
        except (sqlite3.Error, OSError, ValueError):
            return vazio
        return saida

    @app.route("/rcpn/<int:assento_id>/digitalizacao", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_digitalizacao_enviar(assento_id: int):
        """O balcão envia o termo assinado (PDF ou imagem). ESCREVE."""
        volta = url_for("rcpn_assento", assento_id=assento_id)
        try:
            info = RCDIGI.gravar_upload(db, assento_id=assento_id,
                                        arquivo=request.files.get("arquivo"),
                                        usuario=_usuario())
        except RCDIGI.DigitalizacaoError as erro:
            flash(str(erro), "danger")
            return redirect(volta)
        # `audit` abre transação própria: FORA de `db.transaction()`.
        audit("RCPN_DIGITALIZACAO_ATUALIZADA", "rc_assentos", assento_id,
              {"nome": info["nome"], "sha256": info["sha256"],
               "origem": info["origem"], "substituiu": info["substituiu"]})
        flash(f"Termo digitalizado {'substituído' if info['substituiu'] else 'guardado'} "
              f"({info['nome']}). Já serve para a certidão reprográfica.",
              "success")
        return redirect(volta + "#termo-digitalizado")

    def _arquivo_oficial(assento_id: int) -> tuple[Path, dict]:
        with db.connect() as con:
            atual = RCDIGI.atual_do_assento(con, assento_id)
        if not atual or not atual["tem_arquivo"]:
            abort(404)
        return Path(atual["digi_path"]), atual

    @app.route("/rcpn/<int:assento_id>/digitalizacao/arquivo")
    @login_required
    def rcpn_digitalizacao_arquivo(assento_id: int):
        """O arquivo oficial: `?visualizar=1` abre na tela; sem ele, baixa. Só LÊ."""
        caminho, atual = _arquivo_oficial(assento_id)
        nome = str(atual.get("digi_nome") or caminho.name)
        nome = nome.replace('"', "").replace("\r", "").replace("\n", "")
        tipo = mimetypes.guess_type(nome)[0] or "application/octet-stream"
        modo = "inline" if request.args.get("visualizar") == "1" else "attachment"
        return Response(caminho.read_bytes(), mimetype=tipo, headers={
            "Content-Disposition": f'{modo}; filename="{nome}"',
            "X-Content-Type-Options": "nosniff"})

    @app.route("/rcpn/<int:assento_id>/digitalizacao/miniatura")
    @login_required
    def rcpn_digitalizacao_miniatura(assento_id: int):
        """A primeira página, em PNG, para a ficha. Só LÊ."""
        caminho, _ = _arquivo_oficial(assento_id)
        try:
            largura = int(request.args.get("w") or 420)
        except ValueError:
            largura = 420
        try:
            png = RDIGI.miniatura_png(caminho, largura=largura)
        except ValueError as erro:
            app.logger.warning("Miniatura do termo do assento %s: %s",
                               assento_id, erro)
            abort(404)
        return Response(png, mimetype="image/png", headers={
            "Cache-Control": "private, max-age=600",
            "X-Content-Type-Options": "nosniff"})

    @app.route("/rcpn/termos-a-digitalizar")
    @login_required
    def rcpn_termos_a_digitalizar():
        """Os registros lavrados aqui que ainda esperam o termo assinado. Só LÊ."""
        with db.connect() as con:
            linhas = RCDIGI.pendentes(con)
            desde = RCDIGI.obrigatoria_desde(con)
        return render_template("rc_termos_a_digitalizar.html", linhas=linhas,
                               desde=desde, prazo_dias=RCDIGI.PRAZO_DIAS)
