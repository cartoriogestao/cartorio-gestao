"""A TELA DO PAINEL DE CONFORMIDADE DO ONR — RI010, 23/11/2026.

    Ver `onr_conformidade` para o desenho. Aqui só se mostra, se recebe o que a
    pessoa digitou e se imprime o quadro.

O PAINEL NÃO ENVIA NADA. Não entra no ONR, não chama a API e não altera ficha:
as rotas de escrita gravam só `onr_declaracoes`, `onr_provas_informadas`,
`onr_pendencias` e o comprovante (anexo `ONR_PENDENCIA`). Ver e imprimir é do
oficial, do gerente e do auditor; lançar é do oficial e do gerente (a mesma
régua da checklist de gestão).
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from flask import Response, flash, redirect, render_template, request, url_for

import onr_conformidade as OC
from bd_nativo import banco

QUEM_VE = ("ADMIN", "MANAGER", "AUDITOR")
QUEM_LANCA = ("ADMIN", "MANAGER")


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_nome = app.extensions["usuario_nome"]
    usuario_id = app.extensions["usuario_id"]
    archive_root = app.extensions["archive_root"]

    def _contexto() -> dict:
        with db.connect() as con:
            painel = OC.medir(con)
            historico = OC.historico_de_declaracoes(con)
            provas = OC.historico_de_provas(con)
            encerradas = [p for p in OC.pendencias(con, todas=True) if p["situacao"] != OC.ABERTA][:20]
        return {"p": painel, "historico": historico, "provas": provas, "encerradas": encerradas,
                "colunas": OC.COLUNAS, "obrigacoes": OC.OBRIGACOES, "situacoes_da_prova": OC.SITUACOES_DA_PROVA,
                "com_prova": OC.COM_PROVA_INFORMADA, "nomes": OC.NOME_DA_OBRIGACAO,
                "pode_lancar": _pode_lancar()}

    def _pode_lancar() -> bool:
        return app.extensions["usuario_papel"]() in QUEM_LANCA

    def _voltar(ancora: str = ""):
        return redirect(url_for("ri_onr_conformidade") + (f"#{ancora}" if ancora else ""))

    def _gravar(fazer, mensagem: str, acao: str, ancora: str = ""):
        """Roda `fazer(con)` numa transação; a recusa volta com o motivo, sem gravar nada."""
        try:
            with db.transaction() as con:
                detalhe = fazer(con)
        except OC.PainelOnrError as erro:
            flash(str(erro), "danger")
            return _voltar(ancora)
        audit(acao, "onr_conformidade", None, detalhe if isinstance(detalhe, dict) else {})
        flash(mensagem, "success")
        return _voltar(ancora)

    @app.route("/ri/onr/conformidade")
    @login_required
    @roles_required(*QUEM_VE)
    def ri_onr_conformidade():
        """O declarado, o que existe, o entregue com prova e o que falta. SÓ LÊ."""
        return render_template("onr_conformidade.html", **_contexto())

    @app.route("/ri/onr/conformidade/declaracao", methods=["POST"])
    @login_required
    @roles_required(*QUEM_LANCA)
    def ri_onr_conformidade_declarar():
        f = request.form

        def fazer(con):
            n = OC.lancar_declaracao(con, coluna=f.get("coluna"), valor=f.get("valor"),
                                     lido_em=f.get("lido_em"), origem=f.get("origem"),
                                     observacao=f.get("observacao"), por=usuario_nome())
            return {"id": n, "coluna": (f.get("coluna") or "").upper()}
        return _gravar(fazer, "Número lançado. Ele aparece ao lado do que existe e do que foi entregue; "
                              "não vira «cumprido» por ter sido declarado.",
                       "ONR_CONFORMIDADE_DECLARACAO", "declarado")

    @app.route("/ri/onr/conformidade/declaracao/<int:declaracao_id>/anular", methods=["POST"])
    @login_required
    @roles_required(*QUEM_LANCA)
    def ri_onr_conformidade_anular_declaracao(declaracao_id: int):
        def fazer(con):
            OC.anular_declaracao(con, declaracao_id, motivo=request.form.get("motivo"), por=usuario_nome())
            return {"id": declaracao_id}
        return _gravar(fazer, "Lançamento anulado; vale o anterior, se houver.",
                       "ONR_CONFORMIDADE_DECLARACAO_ANULADA", "declarado")

    @app.route("/ri/onr/conformidade/prova", methods=["POST"])
    @login_required
    @roles_required(*QUEM_LANCA)
    def ri_onr_conformidade_prova():
        f = request.form

        def fazer(con):
            n = OC.lancar_prova(con, coluna=f.get("coluna"), quantos=f.get("quantos"),
                                situacao=f.get("situacao"), visto_em=f.get("visto_em"),
                                protocolo_onr=f.get("protocolo_onr"), descricao=f.get("descricao"),
                                por=usuario_nome())
            return {"id": n, "coluna": (f.get("coluna") or "").upper()}
        return _gravar(fazer, "Importação informada. Só «Importado» conta como entregue com prova.",
                       "ONR_CONFORMIDADE_PROVA", "provas")

    @app.route("/ri/onr/conformidade/prova/<int:prova_id>/anular", methods=["POST"])
    @login_required
    @roles_required(*QUEM_LANCA)
    def ri_onr_conformidade_anular_prova(prova_id: int):
        def fazer(con):
            OC.anular_prova(con, prova_id, motivo=request.form.get("motivo"), por=usuario_nome())
            return {"id": prova_id}
        return _gravar(fazer, "Importação anulada.", "ONR_CONFORMIDADE_PROVA_ANULADA", "provas")

    @app.route("/ri/onr/conformidade/pendencia", methods=["POST"])
    @login_required
    @roles_required(*QUEM_LANCA)
    def ri_onr_conformidade_pendencia():
        f = request.form

        def fazer(con):
            n = OC.abrir_pendencia(con, obrigacao=f.get("obrigacao"), coluna=f.get("coluna"),
                                   titulo=f.get("titulo"), responsavel=f.get("responsavel"),
                                   prazo=f.get("prazo"), protocolo_onr=f.get("protocolo_onr"),
                                   observacao=f.get("observacao"), por=usuario_nome())
            return {"id": n}
        return _gravar(fazer, "Pendência aberta.", "ONR_CONFORMIDADE_PENDENCIA", "pendencias")

    @app.route("/ri/onr/conformidade/pendencia/<int:pendencia_id>", methods=["POST"])
    @login_required
    @roles_required(*QUEM_LANCA)
    def ri_onr_conformidade_pendencia_atualizar(pendencia_id: int):
        f = request.form

        def fazer(con):
            OC.atualizar_pendencia(con, pendencia_id, responsavel=f.get("responsavel"), prazo=f.get("prazo"),
                                   protocolo_onr=f.get("protocolo_onr"), observacao=f.get("observacao"))
            return {"id": pendencia_id}
        return _gravar(fazer, "Pendência atualizada.", "ONR_CONFORMIDADE_PENDENCIA_ATUALIZADA", "pendencias")

    @app.route("/ri/onr/conformidade/pendencia/<int:pendencia_id>/encerrar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_LANCA)
    def ri_onr_conformidade_pendencia_encerrar(pendencia_id: int):
        def fazer(con):
            OC.encerrar_pendencia(con, pendencia_id, situacao=request.form.get("situacao"),
                                  motivo=request.form.get("motivo"), por=usuario_nome())
            return {"id": pendencia_id, "situacao": (request.form.get("situacao") or "").upper()}
        return _gravar(fazer, "Pendência encerrada. Se o número ainda está sem lastro, a divergência "
                              "continua aparecendo.", "ONR_CONFORMIDADE_PENDENCIA_ENCERRADA", "pendencias")

    @app.route("/ri/onr/conformidade/pendencia/<int:pendencia_id>/comprovante", methods=["POST"])
    @login_required
    @roles_required(*QUEM_LANCA)
    def ri_onr_conformidade_comprovante(pendencia_id: int):
        arquivos = [a for a in request.files.getlist("arquivo") if a and a.filename]
        if not arquivos:
            flash("Escolha o arquivo do comprovante.", "danger")
            return _voltar("pendencias")
        try:
            with db.transaction() as con:
                ids = [OC.guardar_comprovante(con, pendencia_id, nome_arquivo=a.filename,
                                              conteudo=a.read(), pasta=archive_root() / "onr_conformidade",
                                              usuario_id=usuario_id()) for a in arquivos]
        except OC.PainelOnrError as erro:
            flash(f"{erro} Nenhum arquivo deste envio foi guardado.", "danger")
            return _voltar("pendencias")
        audit("ONR_CONFORMIDADE_COMPROVANTE", "onr_pendencias", pendencia_id, {"anexos": ids})
        flash(f"{len(ids)} comprovante(s) guardado(s).", "success")
        return _voltar("pendencias")

    def _quadro(papel: bool) -> str:
        with db.connect() as con:
            painel = OC.medir(con)
            serventia = {k: db.get_setting(k, "") for k in ("unit_name", "ri_cns", "serventia_cns")}
        return render_template("onr_conformidade_quadro.html", p=painel, papel=papel,
                               serventia=serventia, emitido_por=usuario_nome(),
                               emitido_em=datetime.now().strftime("%d/%m/%Y %H:%M"),
                               nomes=OC.NOME_DA_OBRIGACAO, colunas=OC.COLUNAS,
                               rotulo_da_prova=OC.SITUACOES_DA_PROVA)

    @app.route("/ri/onr/conformidade/quadro")
    @login_required
    @roles_required(*QUEM_VE)
    def ri_onr_conformidade_quadro():
        """O quadro para anexar à resposta da Corregedoria: a página pronta para imprimir."""
        audit("ONR_CONFORMIDADE_QUADRO_VISTO", "onr_conformidade", None, {})
        return _quadro(papel=False)

    @app.route("/ri/onr/conformidade/quadro/papel")
    @login_required
    @roles_required(*QUEM_VE)
    def ri_onr_conformidade_quadro_papel():
        """O mesmo quadro em PDF, pelo caminho de impressão da casa (Chrome)."""
        import impressao_pdf as PDFIMP
        try:
            conteudo, tipo, arquivo, entrega = PDFIMP.arquivo_de_html(
                _quadro(papel=True), nome=f"quadro-onr-{date.today().isoformat()}",
                formato=request.args.get("formato"), get_setting=db.get_setting)
        except PDFIMP.PdfError as erro:
            flash(f"{erro} Use «Imprimir» na página do quadro.", "warning")
            return redirect(url_for("ri_onr_conformidade_quadro"))
        audit("ONR_CONFORMIDADE_QUADRO_PDF", "onr_conformidade", None, {})
        return Response(conteudo, mimetype=tipo,
                        headers={"Content-Disposition": f'{entrega}; filename="{arquivo}"'})
