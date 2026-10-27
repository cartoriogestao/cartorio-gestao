"""NFS-e dos emolumentos — as telas: a fila do caixa, o recibo e a configuração.

Registrado a partir de `create_app()`, no padrão dos outros módulos de rota:
recebe os decoradores e a auditoria que já existem. A regra mora em `nfse`;
aqui só se lê o formulário, chama-se a regra e diz-se o que houve.

QUEM PODE O QUÊ (LG01, 19/10/2026)
    Emitir e completar o tomador: quem opera o caixa (ADMIN, MANAGER, USER) —
    é no balcão que a nota nasce. Emitir o lote do dia e cancelar: ADMIN e
    MANAGER, porque cancelar nota é ato perante o fisco. Configurar e gravar o
    certificado: só o ADMIN. O AUDITOR vê a fila e baixa o DANFSe e o XML, e
    não grava nada.

O QUE VAI AO RASTRO
    Cada emissão, recusa, reenvio, cancelamento, DANFSe e mudança de
    configuração entra em `audit_logs` — com o CPF do tomador mascarado e
    **sem a senha nem o conteúdo do certificado**, que não passam por aqui
    depois de gravados (`nfse.gravar_certificado`).
"""
from __future__ import annotations

import json
from datetime import date

from flask import Response, abort, flash, redirect, render_template, request, url_for

import csv_seguro as CSVS
import nfse as NFSE
import nfse_dps as DPS

QUEM_OPERA = ("ADMIN", "MANAGER", "USER")
QUEM_VE = ("ADMIN", "MANAGER", "USER", "AUDITOR")
QUEM_CANCELA = ("ADMIN", "MANAGER")

ACAO_DA_SITUACAO = {
    NFSE.EMITIDA: "NFSE_EMITIDA",
    NFSE.REJEITADA: "NFSE_RECUSADA",
    NFSE.ENVIANDO: "NFSE_NA_FILA",
}


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    """Pendura as telas da NFS-e no app já construído."""
    usuario_nome = app.extensions["usuario_nome"]
    usuario_papel = app.extensions["usuario_papel"]

    def _cfg() -> dict:
        with db.connect() as con:
            return NFSE.configuracao(con)

    def _abrir_o_emissor(cfg):
        """O certificado e o provedor. Erro de configuração vira `NfseError`."""
        faltas = NFSE.pendencias_da_configuracao(cfg)
        if faltas:
            raise NFSE.NfseError(" ".join(faltas))
        certificado = NFSE.ler_certificado()
        return NFSE.provedor_da_casa(cfg, certificado), certificado

    def _dizer(nota: dict) -> None:
        if nota["situacao"] == NFSE.EMITIDA:
            flash(f"NFS-e {nota['numero_nfse'] or ''} emitida (chave {nota['chave']}).",
                  "success")
        elif nota["situacao"] == NFSE.REJEITADA:
            flash(f"O emissor recusou a DPS: {nota['mensagem']}", "danger")
        else:
            flash(f"A DPS ficou na fila: {nota['mensagem'] or 'sem resposta do emissor'}. "
                  f"O reenvio é seguro — a mesma DPS não vira duas notas.", "warning")

    # -------------------------------------------------------------- a fila

    @app.route("/caixa/nfse")
    @login_required
    @roles_required(*QUEM_VE)
    def nfse_fila():
        """A fila do balcão: pendências, prontos, em envio, recusadas. Só LÊ."""
        cfg = _cfg()
        data = (request.args.get("data") or "").strip()
        with db.connect() as con:
            grupos = NFSE.fila(con, cfg, data=data or None)
        return render_template(
            "nfse_fila.html", cfg=cfg, grupos=grupos, data=data,
            hoje=date.today().isoformat(), ligada=NFSE.ligada(cfg),
            faltas=NFSE.pendencias_da_configuracao(cfg),
            ambiente=NFSE.AMBIENTES.get(cfg["nfse_ambiente"], cfg["nfse_ambiente"]),
            situacoes=NFSE.SITUACOES, reais=NFSE.reais, papel=usuario_papel(),
            quem_opera=QUEM_OPERA, quem_cancela=QUEM_CANCELA)

    @app.route("/caixa/nfse/lote", methods=["POST"])
    @login_required
    @roles_required(*QUEM_CANCELA)
    def nfse_lote():
        """Emite as notas do dia, uma por recibo. Um que falha não para os outros."""
        cfg = _cfg()
        data = (request.form.get("data") or "").strip() or date.today().isoformat()
        try:
            provedor, certificado = _abrir_o_emissor(cfg)
            contagem = NFSE.emitir_lote(db, data, provedor=provedor, certificado=certificado,
                                        cfg=cfg, usuario=usuario_nome())
        except NFSE.NfseError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("nfse_fila", data=data))
        audit("NFSE_LOTE", "nfse_notas", None, {"data": data, **contagem})
        flash(f"Lote de {data}: {contagem['emitidas']} emitida(s), "
              f"{contagem['recusadas']} recusada(s), {contagem['na_fila']} na fila, "
              f"{contagem['pendentes']} com pendência.",
              "success" if not (contagem["recusadas"] or contagem["na_fila"]) else "warning")
        return redirect(url_for("nfse_fila", data=data))

    # ------------------------------------------------------------ o recibo

    @app.route("/caixa/nfse/recibo/<int:recibo_id>", methods=["GET", "POST"])
    @login_required
    @roles_required(*QUEM_VE)
    def nfse_recibo(recibo_id):
        """O recibo diante da NFS-e: o que falta, o tomador, as notas e o rastro."""
        cfg = _cfg()
        if request.method == "POST":
            if usuario_papel() not in QUEM_OPERA:
                abort(403)
            try:
                with db.transaction() as con:
                    tomador = NFSE.gravar_tomador(con, recibo_id, request.form,
                                                  por=usuario_nome(), agora=db.now())
            except NFSE.NfseError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("nfse_recibo", recibo_id=recibo_id))
            audit("NFSE_TOMADOR_COMPLETADO", "cx_recibos", recibo_id,
                  {"tomador": NFSE.mascarar_documento(tomador.documento),
                   "com_endereco": tomador.tem_endereco})
            flash("Dados do tomador gravados.", "success")
            return redirect(url_for("nfse_recibo", recibo_id=recibo_id))
        with db.connect() as con:
            item = NFSE.avaliar_recibo(con, recibo_id, cfg)
            if item is None:
                abort(404)
            notas = NFSE.notas_do_recibo(con, recibo_id)
            rastro = {n["id"]: NFSE.eventos(con, n["id"]) for n in notas}
        return render_template(
            "nfse_recibo.html", item=item, notas=notas, rastro=rastro, cfg=cfg,
            ligada=NFSE.ligada(cfg), situacoes=NFSE.SITUACOES, reais=NFSE.reais,
            motivos=DPS.MOTIVOS_DE_CANCELAMENTO, papel=usuario_papel(),
            quem_opera=QUEM_OPERA, quem_cancela=QUEM_CANCELA,
            mascarar=NFSE.mascarar_documento, fmt_date=fmt_date)

    @app.route("/caixa/nfse/recibo/<int:recibo_id>/emitir", methods=["POST"])
    @login_required
    @roles_required(*QUEM_OPERA)
    def nfse_emitir(recibo_id):
        """«Emitir NFS-e» do recibo pago. Repetir o clique não emite duas."""
        cfg = _cfg()
        try:
            provedor, certificado = _abrir_o_emissor(cfg)
            nota = NFSE.emitir(db, recibo_id, provedor=provedor, certificado=certificado,
                               cfg=cfg, usuario=usuario_nome())
        except NFSE.Pendente as pendente:
            flash("A nota não sai ainda: " + " ".join(pendente.pendencias), "warning")
            return redirect(url_for("nfse_recibo", recibo_id=recibo_id))
        except NFSE.NfseError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("nfse_recibo", recibo_id=recibo_id))
        audit(ACAO_DA_SITUACAO.get(nota["situacao"], "NFSE_NA_FILA"), "nfse_notas",
              nota["id"], NFSE.para_o_rastro(nota))
        _dizer(nota)
        return redirect(url_for("nfse_recibo", recibo_id=recibo_id))

    # -------------------------------------------------------------- a nota

    def _nota_ou_404(nota_id: int) -> dict:
        with db.connect() as con:
            n = NFSE.nota(con, nota_id)
        if not n:
            abort(404)
        return n

    @app.route("/caixa/nfse/nota/<int:nota_id>/reenviar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_OPERA)
    def nfse_reenviar(nota_id):
        """Reenvia a DPS que ficou na fila ou foi recusada. Idempotente."""
        n = _nota_ou_404(nota_id)
        cfg = _cfg()
        try:
            provedor, certificado = _abrir_o_emissor(cfg)
            if n["situacao"] == NFSE.ENVIANDO:
                nota = NFSE.enviar(db, nota_id, provedor, usuario=usuario_nome())
            else:
                nota = NFSE.emitir(db, n["recibo_id"], provedor=provedor,
                                   certificado=certificado, cfg=cfg, usuario=usuario_nome())
        except NFSE.Pendente as pendente:
            flash("A nota não sai ainda: " + " ".join(pendente.pendencias), "warning")
            return redirect(url_for("nfse_recibo", recibo_id=n["recibo_id"]))
        except NFSE.NfseError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("nfse_recibo", recibo_id=n["recibo_id"]))
        audit("NFSE_REENVIADA", "nfse_notas", nota["id"], NFSE.para_o_rastro(nota))
        _dizer(nota)
        return redirect(url_for("nfse_recibo", recibo_id=n["recibo_id"]))

    @app.route("/caixa/nfse/nota/<int:nota_id>/cancelar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_CANCELA)
    def nfse_cancelar(nota_id):
        """Pede o cancelamento ao emissor. A nota só muda se ele aceitar."""
        n = _nota_ou_404(nota_id)
        cfg = _cfg()
        motivo = (request.form.get("motivo") or "").strip()
        justificativa = (request.form.get("justificativa") or "").strip()
        try:
            provedor, certificado = _abrir_o_emissor(cfg)
            nota = NFSE.cancelar(db, nota_id, provedor=provedor, certificado=certificado,
                                 cfg=cfg, motivo=motivo, justificativa=justificativa,
                                 usuario=usuario_nome())
        except NFSE.NfseError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("nfse_recibo", recibo_id=n["recibo_id"]))
        audit("NFSE_CANCELADA", "nfse_notas", nota_id,
              {**NFSE.para_o_rastro(nota), "motivo": DPS.MOTIVOS_DE_CANCELAMENTO.get(motivo)})
        flash("NFS-e cancelada.", "success")
        return redirect(url_for("nfse_recibo", recibo_id=n["recibo_id"]))

    @app.route("/caixa/nfse/nota/<int:nota_id>/danfse")
    @login_required
    @roles_required(*QUEM_VE)
    def nfse_danfse(nota_id):
        """O DANFSe v2.0 (NT 008/2026), montado do XML da nota. `?formato=html`
        mostra a folha para imprimir no navegador quando o PDF não sair."""
        n = _nota_ou_404(nota_id)
        formato = "html" if request.args.get("formato") == "html" else "pdf"
        try:
            provedor = None
            if not n.get("xml_nfse"):
                provedor, _certificado = _abrir_o_emissor(_cfg())
            saida = NFSE.danfse(db, nota_id, usuario=usuario_nome(), provedor=provedor,
                                formato=formato)
        except NFSE.NfseError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("nfse_recibo", recibo_id=n["recibo_id"]))
        audit("NFSE_DANFSE_BAIXADO", "nfse_notas", nota_id,
              {"chave": n["chave"], "formato": formato})
        if formato == "html":
            return Response(saida, mimetype="text/html")
        return Response(saida, mimetype="application/pdf", headers={
            "Content-Disposition": f'inline; filename="danfse-{n["numero_nfse"] or nota_id}.pdf"'})

    @app.route("/caixa/nfse/nota/<int:nota_id>/xml")
    @login_required
    @roles_required("ADMIN", "MANAGER", "AUDITOR")
    def nfse_xml(nota_id):
        """O XML da NFS-e (ou da DPS, se a nota ainda não saiu), para o contador."""
        n = _nota_ou_404(nota_id)
        conteudo = n["xml_nfse"] or n["xml_dps"]
        qual = "nfse" if n["xml_nfse"] else "dps"
        audit("NFSE_XML_BAIXADO", "nfse_notas", nota_id, {"qual": qual})
        return Response(conteudo, mimetype="application/xml", headers={
            "Content-Disposition": f'attachment; filename="{qual}-{n["id_dps"]}.xml"'})

    # ------------------------------------------------------ a configuração

    @app.route("/administrativo/gestor/nfse", methods=["GET", "POST"])
    @login_required
    @roles_required("ADMIN")
    def nfse_gestor():
        """Ligar, escolher o ambiente, dados fiscais e o certificado A1. Só ADMIN."""
        if request.method == "POST":
            acao = request.form.get("acao")
            try:
                if acao == "configuracao":
                    with db.transaction() as con:
                        mudou = NFSE.gravar_configuracao(con, request.form)
                    audit("NFSE_CONFIGURACAO_ALTERADA", "settings", None,
                          {k: {"de": de, "para": para} for k, (de, para) in mudou.items()})
                    flash("Configuração da NFS-e gravada." if mudou
                          else "Nada mudou na configuração.", "success")
                elif acao == "certificado":
                    arquivo = request.files.get("pfx")
                    resumo = NFSE.gravar_certificado(
                        arquivo.read() if arquivo else b"", request.form.get("senha") or "")
                    audit("NFSE_CERTIFICADO_GRAVADO", "settings", None,
                          {"titular": resumo["titular"], "valido_ate": resumo["valido_ate"]})
                    flash(f"Certificado de {resumo['titular']} gravado, válido até "
                          f"{resumo['valido_ate']}. Ele mora fora do banco.", "success")
                elif acao == "apagar_certificado":
                    NFSE.apagar_certificado()
                    audit("NFSE_CERTIFICADO_APAGADO", "settings", None, {})
                    flash("Certificado apagado desta máquina.", "success")
                elif acao == "parametros":
                    cfg = _cfg()
                    provedor, _certificado = _abrir_o_emissor(cfg)
                    consulta = NFSE.conferir_no_emissor(provedor, cfg)
                    with db.transaction() as con:
                        NFSE.gravar_parametros(con, consulta)
                    audit("NFSE_PARAMETROS_CONSULTADOS", "settings", None,
                          {"municipio": consulta["municipio"],
                           "ambiente": consulta["ambiente"]})
                    flash("Parâmetros do município consultados. Leia a resposta do "
                          "convênio abaixo e marque a situação dele.", "success")
                else:
                    abort(400)
            except NFSE.NfseError as erro:
                flash(str(erro), "danger")
            return redirect(url_for("nfse_gestor"))
        cfg = _cfg()
        with db.connect() as con:
            parametros = NFSE.parametros_gravados(con)
        return render_template(
            "nfse_gestor.html", cfg=cfg, rotulos=NFSE.ROTULOS,
            certificado=NFSE.resumo_do_certificado(),
            faltas=NFSE.pendencias_da_configuracao(cfg), ambientes=NFSE.AMBIENTES,
            avisos=NFSE.avisos_da_configuracao(cfg), convenios=NFSE.CONVENIO,
            parametros=parametros,
            parametros_texto=(json.dumps(parametros, ensure_ascii=False, indent=2)
                              if parametros else ""),
            regimes=NFSE.REGIMES_ESPECIAIS, opcoes_simples=NFSE.OPCOES_SIMPLES,
            provedores=sorted(NFSE.PROV.PROVEDORES))

    # ------------------------------------------------------ a apuração do mês

    @app.route("/caixa/nfse/apuracao")
    @login_required
    @roles_required("ADMIN", "MANAGER", "AUDITOR")
    def nfse_apuracao():
        """O ISS do mês, nota por nota — o número que a guia deve dar."""
        mes = (request.args.get("mes") or date.today().isoformat()[:7]).strip()
        cfg = _cfg()
        ambiente = request.args.get("ambiente") or cfg["nfse_ambiente"]
        if ambiente not in NFSE.AMBIENTES:
            abort(400)
        try:
            with db.connect() as con:
                apuracao = NFSE.apuracao_do_mes(con, mes, ambiente=ambiente)
        except NFSE.NfseError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("nfse_apuracao"))
        if request.args.get("formato") == "csv":
            audit("NFSE_APURACAO_EXPORTADA", "nfse_notas", None,
                  {"mes": mes, "ambiente": ambiente, "notas": apuracao["quantidade"]})
            # pelo `csv_seguro`: tudo entre aspas e fórmula desarmada no tomador
            return CSVS.resposta(f"apuracao-iss-{mes}.csv", NFSE.CABECALHO_DA_APURACAO,
                                 NFSE.linhas_da_apuracao(apuracao))
        return render_template("nfse_apuracao.html", a=apuracao, mes=mes,
                               ambientes=NFSE.AMBIENTES, reais=NFSE.reais)
