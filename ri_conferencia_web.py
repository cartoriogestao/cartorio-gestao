"""As rotas da conferência de documento eletrônico do RI — ver `ri_conferencia.py`.

O QUADRO MORA NA FICHA DO PROTOCOLO DO BALCÃO (`caixa_web.caixa_protocolo`),
que é de onde o oficial pediu que o selo saísse (28/10/2026): «a emissao do
selo pode ser feita a partir do protocolo, gerando uma etiqueta para colar na
folha fisica (tipo etiqueta de reconhecimento de firma) ou comprovante anexado
ao arquivamento digital (pdf)».

    emitir   — grava a conferência, gasta as unidades do 16.42 e pede o selo;
    etiqueta — uma tira por documento, na bobina de 100 × 30 mm da firma;
    PDF      — o comprovante, para ver ou baixar;
    anexar   — o mesmo PDF entra nos documentos do protocolo, que a prenotação
               ligada a ele já mostra (`protocolo_documentos.da_prenotacao`).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from flask import (Response, abort, flash, redirect, render_template, request,
                   url_for)

import ato_selado as AS
import ri_conferencia as RC
import seguranca_web as SEGWEB
from bd_nativo import banco

#: Quem emite, imprime e anexa: todo humano que pratica ato (a régua da casa).
#: O AUDITOR vê o quadro e o PDF; o robô não chega aqui (lista fechada).
PAPEIS_QUE_EMITEM = tuple(SEGWEB.PRATICA)

#: A tela que mostra o quadro.
TELA_DO_QUADRO = "caixa_protocolo"


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_nome = app.extensions["usuario_nome"]

    def agora() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def volta(protocolo_id) -> str:
        return url_for(TELA_DO_QUADRO, protocolo_id=protocolo_id) + "#conferencia-digital"

    def serventia() -> dict:
        from serventia import dados
        return dados(db.get_settings)

    def texto_do_selo(selo) -> str:
        """O que o aparelho escreveu no selo, do razão. Só LÊ."""
        if not str(selo or "").strip():
            return ""
        with db.connect() as con:
            t = banco(con).um("SELECT texto FROM sd_selos WHERE numero = %s",
                              (str(selo).strip(),))
        return (t["texto"] if t else "") or ""

    def conferencia_ou_404(conferencia_id) -> tuple[dict, dict]:
        with db.connect() as con:
            c = RC.uma(con, conferencia_id)
            if not c:
                abort(404)
            p = banco(con).um("SELECT * FROM cx_protocolos WHERE id = %s",
                              (int(c["protocolo_id"]),))
        return c, dict(p or {})

    def recusa_sem_selo(c: dict) -> str | None:
        if c.get("cancelada_em"):
            return ("Esta conferência está cancelada — não sai etiqueta nem "
                    "comprovante de ato que não vale.")
        if not str(c.get("selo") or "").strip():
            return ("Esta conferência está sem selo: emita o selo antes de "
                    "imprimir a etiqueta ou gerar o comprovante.")
        return None

    @app.context_processor
    def _conferencia_digital_na_tela() -> dict:
        """O que o quadro precisa, só na ficha do protocolo. Só LÊ."""
        try:
            if (request.endpoint or "") != TELA_DO_QUADRO:
                return {}
            protocolo_id = (request.view_args or {}).get("protocolo_id")
        except RuntimeError:
            return {}
        if protocolo_id is None:
            return {}
        try:
            with db.connect() as con:
                p = banco(con).um("SELECT atribuicao FROM cx_protocolos WHERE id = %s",
                                  (int(protocolo_id),))
                itens = RC.itens_do_protocolo(con, protocolo_id)
                feitas = RC.do_protocolo(con, protocolo_id)
            e_do_ri = str((p or {}).get("atribuicao") or "").strip().upper() == RC.ATRIBUICAO
            if not (e_do_ri or itens or feitas):
                return {}
            return {"conferencia_digital": {
                "protocolo_id": protocolo_id, "e_do_ri": e_do_ri, "itens": itens,
                "feitas": feitas, "papeis": PAPEIS_QUE_EMITEM,
                "codigo": RC.CODIGO_ATO, "maximo": RC.MAXIMO_DE_DOCUMENTOS}}
        except Exception as erro:                      # noqa: BLE001 — o quadro some, a ficha abre
            app.logger.error("Quadro da conferência digital não montou.", exc_info=erro)
            return {}

    @app.route("/caixa/protocolos/<int:protocolo_id>/conferencia-digital",
               methods=["POST"])
    @roles_required(*PAPEIS_QUE_EMITEM)
    def ri_conferencia_emitir(protocolo_id: int):
        """Grava a conferência, gasta as unidades do 16.42 e pede o selo.
        ESCREVE (a conferência e o selo) e FALA COM A REDE, fora da transação."""
        import selo_robo as SR
        if not SR.pode_selar_automatico():
            flash(SR.recado_pendente_selo(), "danger")
            return redirect(volta(protocolo_id))
        dados = {k: request.form.get(k) or "" for k in ("item_id", "quantidade",
                                                       "documentos")}
        # O PEDIDO SE MONTA ANTES DE GRAVAR: o que falta no formulário, no
        # protocolo ou no cadastro (a versão da tabela) recusa aqui, sem deixar
        # conferência cancelada nem unidade gasta para trás.
        try:
            with db.connect() as con:
                conferido = RC.conferir(con, protocolo_id, dados)
            pedido = RC.envelope(
                conferido, escrevente=usuario_nome(),
                versao_tabela=AS.versao_da_tabela_de_custas(
                    RC.CAMINHO, db.get_setting("selo_tabela_custas_em", "")))
            with db.transaction() as con:
                cid = RC.registrar(con, conferido, agora=agora(),
                                   usuario=usuario_nome())
        except RC.ConferenciaError as erro:
            flash(str(erro), "danger")
            return redirect(volta(protocolo_id))
        try:
            res = AS.selar_o_ato_lavrado(
                db, Path(app.config["DATA_DIR"]), tabela=RC.TABELA, ato_id=cid,
                tipo="CONFERENCIA", atribuicao="IMOVEL", agora=agora(),
                cns=db.get_setting("ri_cns", ""), usuario=usuario_nome(),
                dados=pedido, caminho=RC.CAMINHO,
                referencia=f"{RC.TABELA}:{cid}:{RC.CODIGO_ATO}:1")
        except AS.AtoError as erro:
            res = {"selado": False, "motivo": str(erro)}
        if not res.get("selado") or not res.get("numero"):
            motivo = str(res.get("motivo") or "o selador não devolveu número").strip()
            # O SELO NÃO SAIU: a conferência fica cancelada, com o motivo, e as
            # unidades voltam ao item — o cliente pagou o serviço, e ele ainda
            # vai ser selado. Nada se apaga.
            with db.transaction() as con:
                RC.cancelar(con, cid, motivo=f"Selo não emitido: {motivo}",
                            agora=agora(), usuario=usuario_nome())
            audit("RI_CONFERENCIA_SELO_FALHOU", RC.TABELA, cid,
                  {"protocolo_id": protocolo_id, "motivo": motivo,
                   "quantidade": conferido["quantidade"]})
            flash(f"O selo da conferência NÃO saiu: {motivo} As unidades do "
                  f"16.42 voltaram ao protocolo.", "danger")
            return redirect(volta(protocolo_id))
        audit("RI_CONFERENCIA_SELADA", RC.TABELA, cid,
              {"protocolo_id": protocolo_id, "selo": res["numero"],
               "codigo": RC.CODIGO_ATO, "quantidade": conferido["quantidade"],
               "item_id": conferido["item"]["id"]})
        import selo_no_papel as SNP
        valores = SNP.linha_de_valores(texto_do_selo(res["numero"]))
        flash(f"Selo da conferência: {res['numero']} ({conferido['quantidade']} "
              f"documento(s)). " + (f"Valores: {valores}. " if valores else "")
              + "Imprima a etiqueta ou anexe o comprovante em PDF.", "success")
        return redirect(volta(protocolo_id))

    @app.route("/registro-imoveis/conferencias/<int:conferencia_id>/etiqueta",
               methods=["POST"])
    @roles_required(*PAPEIS_QUE_EMITEM)
    def ri_conferencia_etiqueta(conferencia_id: int):
        """As tiras, uma por documento, prontas para a janela de impressão.

        POR POST COM O TOKEN, como a etiqueta da firma: a contagem de
        impressões sobe aqui, e GET que grava não passa pelo CSRF."""
        import etiqueta as ETQ
        import notas_selo as NSELO
        import selo_no_papel as SNP
        c, p = conferencia_ou_404(conferencia_id)
        recusa = recusa_sem_selo(c)
        if recusa:
            flash(recusa, "danger")
            return redirect(volta(c["protocolo_id"]))
        with db.transaction() as con:
            banco(con).escrever(
                """UPDATE ri_conferencias
                      SET etiqueta_impressa_em = %s,
                          etiqueta_impressoes = COALESCE(etiqueta_impressoes, 0) + 1
                    WHERE id = %s""", (agora(), int(conferencia_id)))
        vez = int(c.get("etiqueta_impressoes") or 0) + 1
        audit("RI_CONFERENCIA_ETIQUETA_IMPRESSA", RC.TABELA, conferencia_id,
              {"vez": vez, "selo": c["selo"], "tiras": len(c["lista"])})
        m = ETQ.medidas_registro_rtdpj(db.get_settings)
        texto = texto_do_selo(c["selo"])
        marca = NSELO.marca_do_selo(c["selo"], tamanho_mm=m["etiqueta_qr_mm"])
        tiras = [t | {"selo": c["selo"], "valores": SNP.linha_de_valores(texto),
                      "qr": marca["qr"], "qr_possivel": marca["qr_possivel"]}
                 for t in RC.tiras(c, p.get("numero"), serventia())]
        return render_template("ri_conferencia_etiqueta.html", c=c, tiras=tiras,
                               m=m, vez=vez, voltar=volta(c["protocolo_id"]))

    @app.route("/registro-imoveis/conferencias/<int:conferencia_id>/comprovante.pdf")
    @login_required
    def ri_conferencia_comprovante(conferencia_id: int):
        """O comprovante em PDF, para ver na tela ou baixar. Só LÊ."""
        c, p = conferencia_ou_404(conferencia_id)
        recusa = recusa_sem_selo(c)
        if recusa:
            flash(recusa, "danger")
            return redirect(volta(c["protocolo_id"]))
        pdf = RC.comprovante_pdf(c, protocolo_numero=p.get("numero"),
                                 serventia=serventia(),
                                 texto_do_selo=texto_do_selo(c["selo"]))
        nome = f"conferencia-{int(conferencia_id)}-{c['selo']}.pdf"
        entrega = "attachment" if request.args.get("baixar") else "inline"
        return Response(pdf, mimetype="application/pdf",
                        headers={"Content-Disposition": f'{entrega}; filename="{nome}"'})

    @app.route("/registro-imoveis/conferencias/<int:conferencia_id>/anexar",
               methods=["POST"])
    @roles_required(*PAPEIS_QUE_EMITEM)
    def ri_conferencia_anexar(conferencia_id: int):
        """O comprovante entra nos documentos do protocolo. ESCREVE (o arquivo,
        o anexo e a ligação). A prenotação ligada ao protocolo já o mostra."""
        import protocolo_documentos as PDOC
        from storage import hash_file, unique_path
        c, p = conferencia_ou_404(conferencia_id)
        recusa = recusa_sem_selo(c)
        if recusa:
            flash(recusa, "danger")
            return redirect(volta(c["protocolo_id"]))
        if c.get("comprovante_anexo_id"):
            flash("O comprovante desta conferência já está nos documentos do "
                  "protocolo.", "warning")
            return redirect(volta(c["protocolo_id"]))
        pdf = RC.comprovante_pdf(c, protocolo_numero=p.get("numero"),
                                 serventia=serventia(),
                                 texto_do_selo=texto_do_selo(c["selo"]))
        raiz = Path(db.get_setting("archive_root", "").strip()
                    or (Path(db.db_path).parent / "arquivos"))
        pasta = PDOC.pasta_de_qualificacao(raiz, p.get("numero"))
        pasta.mkdir(parents=True, exist_ok=True)
        nome = f"conferencia-{int(conferencia_id)}-{c['selo']}.pdf"
        caminho = unique_path(pasta, nome)
        caminho.write_bytes(pdf)
        info = {"original_name": nome, "stored_name": caminho.name,
                "stored_path": str(caminho.resolve()), "sha256": hash_file(caminho),
                "size_bytes": caminho.stat().st_size}
        try:
            with db.transaction() as con:
                anexo = PDOC.registrar(
                    con, c["protocolo_id"], info, tipo="CONFERENCIA",
                    descricao=(f"Conferência nº {int(conferencia_id)} — selo "
                               f"{c['selo']} — {len(c['lista'])} documento(s)"),
                    usuario_id=app.extensions["usuario_id"](), agora=agora())
                banco(con).escrever(
                    """UPDATE ri_conferencias SET comprovante_anexo_id = %s
                        WHERE id = %s AND comprovante_anexo_id IS NULL""",
                    (int(anexo), int(conferencia_id)))
        except PDOC.DocumentoError as erro:
            # A transação voltou: o arquivo gravado há pouco sai do disco,
            # senão ficaria órfão sem linha que o cite.
            try:
                caminho.unlink()
            except OSError:
                pass
            flash(str(erro), "danger")
            return redirect(volta(c["protocolo_id"]))
        audit("RI_CONFERENCIA_COMPROVANTE_ANEXADO", RC.TABELA, conferencia_id,
              {"protocolo_id": c["protocolo_id"], "anexo": anexo,
               "sha256": info["sha256"], "selo": c["selo"]})
        flash(f"Comprovante da conferência nº {int(conferencia_id)} anexado aos "
              f"documentos do protocolo {p.get('numero')}.", "success")
        return redirect(volta(c["protocolo_id"]))
