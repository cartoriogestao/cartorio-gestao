"""A tela do arquivo inteiro do Indicador Real.

    «as outras serventias que baixarem o programa precisam do botao»
                                                      — o oficial, 30/10/2026

CONFERIR E BAIXAR SÃO DE QUEM JÁ EXPORTA PARA O ONR (ADMIN e MANAGER), e nada vai à rede. As decisões
que mudam o que sai no índice, como a ficha que fica de fora e o dono informado, são do ADMIN.

O CÁLCULO SÓ RODA NO CLIQUE: ele passa por todas as matrículas ativas, e abrir a tela não pode custar
isso. Quem mora em `onr_ir_inteiro` é a regra.
"""
from __future__ import annotations

from flask import Response, flash, redirect, render_template, request, url_for

import onr_ir_inteiro as IR
from bd_nativo import banco
from seguranca_web import numero_digitado

QUEM_EXPORTA = ("ADMIN", "MANAGER")
QUEM_DECIDE = ("ADMIN",)
#: Quantas linhas de cada lista saem na tela. O relatório completo vai no .zip.
LINHAS_NA_TELA = 300


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_nome = app.extensions["usuario_nome"]

    with db.connect() as con:
        IR.init_schema(con)

    def _settings(con) -> dict:
        return {x["key"]: x["value"] for x in banco(con).ler("SELECT key, value FROM settings")}

    def _tela(resultado=None):
        with db.connect() as con:
            s = _settings(con)
            fora = IR.fichas_fora(con)
            donos = IR.donos_informados(con)
        padrao = IR.padrao_do_arquivo(s)
        return render_template("onr_ir_inteiro.html", regras=IR.regras_na_tela(s), fora=fora, donos=donos,
                               padrao=padrao, cns=s.get("ri_cns") or "", tipos=IR.tipos_do_onr(), r=resultado,
                               limite=LINHAS_NA_TELA)

    def _calcular() -> dict:
        with db.connect() as con:
            s = _settings(con)
            return IR.calcular(con, settings=s, cns=s.get("ri_cns") or "")

    @app.route("/registro-imoveis/onr/indicador-inteiro")
    @login_required
    @roles_required(*QUEM_EXPORTA)
    def onr_ir():
        return _tela()

    @app.route("/registro-imoveis/onr/indicador-inteiro/conferir", methods=["POST"])
    @login_required
    @roles_required(*QUEM_EXPORTA)
    def onr_ir_conferir():
        """Mostra o que sairia. Não grava nada."""
        return _tela(_calcular())

    @app.route("/registro-imoveis/onr/indicador-inteiro/baixar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_EXPORTA)
    def onr_ir_baixar():
        r = _calcular()
        if not r["corpos"]:
            flash("Nenhuma ficha está pronta para o arquivo. Clique em «Conferir» para ver o que falta.", "warning")
            return redirect(url_for("onr_ir"))
        data = db.now()[:10]
        conteudo, nomes = IR.pacote(r, data=data)
        audit("RI_ONR_INDICADOR_INTEIRO", "RI_ONR", None, {
            "no_arquivo": len(r["corpos"]), "fora": len(r["fora"]), "sem_dono": len(r["sem_dono"]),
            "repetidas": len(r["repetidas"]), "arquivos": nomes})
        return Response(conteudo, mimetype="application/zip", headers={
            "Content-Disposition": f'attachment; filename="IndicadorReal_COMPLETO_{data}.zip"'})

    # ------------------------------------------------------------ o que a serventia decide

    @app.route("/registro-imoveis/onr/indicador-inteiro/regras", methods=["POST"])
    @login_required
    @roles_required(*QUEM_DECIDE)
    def onr_ir_regras():
        try:
            novas = IR.conferir_regras(request.form)
        except IR.RegraError as e:
            flash(str(e), "danger")
            return redirect(url_for("onr_ir"))
        db.set_settings(novas)
        audit("RI_ONR_INDICADOR_REGRAS", "RI_ONR", None, novas)
        flash("Regras gravadas. Valem para o próximo arquivo, e nenhuma ficha mudou.", "ok")
        return redirect(url_for("onr_ir"))

    def _decidir(acao, rastro: str, **dados):
        try:
            with db.transaction() as con:
                acao(con)
        except IR.RegraError as e:
            flash(str(e), "danger")
        else:
            audit(rastro, "RI_ONR", None, dados)
            flash("Gravado. Vale para o próximo arquivo, e a ficha não mudou.", "ok")
        return redirect(url_for("onr_ir"))

    @app.route("/registro-imoveis/onr/indicador-inteiro/fora", methods=["POST"])
    @login_required
    @roles_required(*QUEM_DECIDE)
    def onr_ir_fora():
        numero, motivo = request.form.get("numero"), request.form.get("motivo")
        return _decidir(lambda con: IR.por_fora(con, numero, motivo, por=usuario_nome(), agora=db.now()),
                        "RI_ONR_INDICADOR_FICHA_FORA", numero=numero, motivo=motivo)

    @app.route("/registro-imoveis/onr/indicador-inteiro/fora/<numero>/voltar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_DECIDE)
    def onr_ir_fora_voltar(numero: str):
        return _decidir(lambda con: IR.trazer_de_volta(con, numero), "RI_ONR_INDICADOR_FICHA_VOLTOU", numero=numero)

    @app.route("/registro-imoveis/onr/indicador-inteiro/dono", methods=["POST"])
    @login_required
    @roles_required(*QUEM_DECIDE)
    def onr_ir_dono():
        f = request.form
        return _decidir(
            lambda con: IR.informar_dono(con, f.get("numero"), f.get("nome"), f.get("documento"), f.get("de_onde"),
                                         por=usuario_nome(), agora=db.now()),
            "RI_ONR_INDICADOR_DONO", numero=f.get("numero"), nome=f.get("nome"), de_onde=f.get("de_onde"))

    @app.route("/registro-imoveis/onr/indicador-inteiro/dono/<int:dono_id>/tirar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_DECIDE)
    def onr_ir_dono_tirar(dono_id: int):
        return _decidir(lambda con: IR.tirar_dono(con, dono_id), "RI_ONR_INDICADOR_DONO_TIRADO", dono=dono_id)
