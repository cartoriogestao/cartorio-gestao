"""A tela dos lotes do Indicador Real. SÓ O ADMIN entra.

CONFERIR NÃO GRAVA. Gerar grava o lote e o arquivo. Nenhuma rota fala com o ONR: quem importa é o
oficial, no portal, e quem diz o resultado é ele, aqui. Quem mora em `onr_ir_lotes` é a regra.
"""
from __future__ import annotations

from flask import Response, flash, redirect, render_template, request, url_for

import onr_ir_json as J
import onr_ir_lotes as LOTES
from bd_nativo import banco

QUEM_ENTRA = ("ADMIN",)
LINHAS_NA_TELA = 300


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_nome = app.extensions["usuario_nome"]

    with db.connect() as con:
        LOTES.init_schema(con)

    def _settings(con) -> dict:
        return {x["key"]: x["value"] for x in banco(con).ler("SELECT key, value FROM settings")}

    def _filtros() -> dict:
        return LOTES.filtros_de(request.form, request.form.getlist("classes"))

    def _tela(resultado=None, filtros=None):
        with db.connect() as con:
            s = _settings(con)
            historico = LOTES.lotes(con)
            eventos = LOTES.eventos(con, [x["id"] for x in historico])
            entregues = LOTES.entregues(con)
        _casa, faltam = J.serventia_de(s)
        return render_template(
            "onr_ir_lotes.html", r=resultado, f=filtros or {"classes": [LOTES.PRONTA], "limite": LOTES.LOTE_PADRAO},
            historico=historico, eventos=eventos, entregues=entregues, faltam=faltam,
            nome_classe=LOTES.NOME_DA_CLASSE, nome_situacao=LOTES.NOME_DA_SITUACAO, transicoes=LOTES.TRANSICOES,
            lote_maximo=LOTES.LOTE_MAXIMO, limite_tela=LINHAS_NA_TELA, DESCARTADO=LOTES.DESCARTADO,
            situacoes_externo=LOTES.SITUACOES_DO_EXTERNO)

    @app.route("/registro-imoveis/onr/indicador-real/lotes")
    @login_required
    @roles_required(*QUEM_ENTRA)
    def onr_ir_lotes():
        return _tela()

    @app.route("/registro-imoveis/onr/indicador-real/lotes/conferir", methods=["POST"])
    @login_required
    @roles_required(*QUEM_ENTRA)
    def onr_ir_lotes_conferir():
        """Mostra o que sairia. Não grava nada."""
        try:
            filtros = _filtros()
            with db.connect() as con:
                resultado = LOTES.conferir(con, settings=_settings(con), filtros=filtros)
        except LOTES.LoteError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("onr_ir_lotes"))
        return _tela(resultado, filtros)

    @app.route("/registro-imoveis/onr/indicador-real/lotes/gerar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_ENTRA)
    def onr_ir_lotes_gerar():
        try:
            filtros = _filtros()
            with db.transaction() as con:
                feito = LOTES.gerar(con, settings=_settings(con), filtros=filtros, por=usuario_nome(), agora=db.now())
        except (LOTES.LoteError, J.ArquivoInvalido) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("onr_ir_lotes"))
        audit("RI_ONR_LOTE_GERADO", "RI_ONR", feito["id"], {
            "arquivo": feito["arquivo"], "sha256": feito["sha256"], "registros": feito["registros"],
            "recusadas": feito["recusadas"], "filtros": {k: filtros[k] for k in filtros}})
        flash(f"Lote {feito['id']} gerado com {feito['registros']} matrícula(s). Nada foi enviado: baixe o "
              "arquivo e importe no Ofício Eletrônico.", "ok")
        return redirect(url_for("onr_ir_lotes"))

    @app.route("/registro-imoveis/onr/indicador-real/lotes/registrar-arquivo", methods=["POST"])
    @login_required
    @roles_required(*QUEM_ENTRA)
    def onr_ir_lotes_registrar_arquivo():
        """Um arquivo JÁ IMPORTADO no portal, gerado fora desta tela, entra no histórico."""
        enviado = request.files.get("arquivo")
        conteudo = enviado.read(LOTES.MAIOR_ARQUIVO_EXTERNO + 1) if enviado else b""
        situacao = (request.form.get("situacao") or "").strip()
        try:
            with db.transaction() as con:
                feito = LOTES.registrar_arquivo_externo(
                    con, conteudo=conteudo, nome=enviado.filename if enviado else "", situacao=situacao,
                    visto_em=request.form.get("visto_em"), observacao=request.form.get("observacao"),
                    settings=_settings(con), por=usuario_nome(), agora=db.now())
        except LOTES.LoteError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("onr_ir_lotes"))
        audit("RI_ONR_LOTE_EXTERNO", "RI_ONR", feito["id"], {
            "arquivo": feito["arquivo"], "sha256": feito["sha256"], "registros": feito["registros"],
            "situacao": situacao, "visto_em": request.form.get("visto_em")})
        flash(f"Lote {feito['id']}: o arquivo com {feito['registros']} matrícula(s) entrou no histórico como "
              f"«{LOTES.NOME_DA_SITUACAO[situacao]}». Nada foi enviado.", "ok")
        return redirect(url_for("onr_ir_lotes"))

    @app.route("/registro-imoveis/onr/indicador-real/lotes/<int:lote_id>/arquivo")
    @login_required
    @roles_required(*QUEM_ENTRA)
    def onr_ir_lote_arquivo(lote_id: int):
        try:
            with db.connect() as con:
                achado = LOTES.arquivo_do_lote(con, lote_id)
        except LOTES.LoteError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("onr_ir_lotes"))
        if not achado:
            flash("Lote não encontrado.", "danger")
            return redirect(url_for("onr_ir_lotes"))
        nome, conteudo = achado
        audit("RI_ONR_LOTE_BAIXADO", "RI_ONR", lote_id, {"arquivo": nome})
        return Response(conteudo, mimetype="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{nome}"'})

    @app.route("/registro-imoveis/onr/indicador-real/lotes/<int:lote_id>/recusadas.csv")
    @login_required
    @roles_required(*QUEM_ENTRA)
    def onr_ir_lote_recusadas(lote_id: int):
        with db.connect() as con:
            achado = LOTES.recusadas_csv(con, lote_id)
        if not achado:
            flash("Lote não encontrado.", "danger")
            return redirect(url_for("onr_ir_lotes"))
        nome, conteudo = achado
        return Response(conteudo, mimetype="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{nome}"'})

    @app.route("/registro-imoveis/onr/indicador-real/lotes/<int:lote_id>/resultado", methods=["POST"])
    @login_required
    @roles_required(*QUEM_ENTRA)
    def onr_ir_lote_resultado(lote_id: int):
        """O que o portal mostrou. Só «Importado» conta como entregue."""
        para = (request.form.get("situacao") or "").strip()
        try:
            with db.transaction() as con:
                LOTES.registrar_resultado(con, lote_id, para, visto_em=request.form.get("visto_em"),
                                          observacao=request.form.get("observacao"), por=usuario_nome(),
                                          agora=db.now())
        except LOTES.LoteError as erro:
            flash(str(erro), "danger")
        else:
            audit("RI_ONR_LOTE_RESULTADO", "RI_ONR", lote_id, {
                "situacao": para, "visto_em": request.form.get("visto_em")})
            flash(f"Lote {lote_id}: registrado como «{LOTES.NOME_DA_SITUACAO[para]}».", "ok")
        return redirect(url_for("onr_ir_lotes"))
