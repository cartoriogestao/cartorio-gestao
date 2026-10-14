"""As telas do PLD/COAF — ver `pld_coaf.py`.

TODAS SÃO DO ADMIN, e não por gosto: o CNN, art. 154, e o TJMA, art. 954,
parágrafo único, mandam guardar sigilo das comunicações, inclusive dentro da
casa. O oficial de cumprimento é o titular enquanto não houver outro nomeado
(CNN, art. 144, § 1º). A auditoria grava o número do caso, e nunca o nome.

ESTAS TELAS NÃO ENVIAM NADA AO COAF: selecionam, preparam e registram. O porquê
está no módulo de domínio.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from flask import abort, flash, redirect, render_template, request, url_for

import pld_coaf as PLD
from storage import save_upload

ENDERECO_DO_SISCOAF = "https://siscoaf.coaf.gov.br/siscoaf-internet/"
ENTIDADE_DO_RECIBO = "PLD_CASO"


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_nome = app.extensions["usuario_nome"]

    def _sv() -> dict:
        from serventia import dados as dados_serventia
        return dados_serventia(db.get_settings)

    @app.route("/administrativo/pld")
    @roles_required("ADMIN")
    def pld_painel():
        """A fila do COAF. SÓ LÊ — a seleção é botão, porque escreve."""
        situacao = (request.args.get("situacao") or "").strip() or None
        with db.connect() as con:
            PLD.init_schema(con)
            lista = PLD.casos(con, situacao)
            resumo = PLD.resumo(con)
            ano = date.today().year
            anos = [PLD.nao_ocorrencia(con, a, _sv()) for a in (ano - 1, ano)]
        return render_template("pld.html", casos=lista, resumo=resumo, anos=anos,
                               situacao=situacao, SITUACOES=PLD.SITUACOES,
                               reais=PLD.reais, corte=PLD.CORTE_PADRAO,
                               siscoaf=ENDERECO_DO_SISCOAF)

    @app.route("/administrativo/pld/selecionar", methods=["POST"])
    @roles_required("ADMIN")
    def pld_selecionar():
        desde = (request.form.get("desde") or PLD.CORTE_PADRAO).strip()
        with db.transaction() as con:
            r = PLD.selecionar(con, desde=desde)
        audit("PLD_SELECAO", "pld_casos", None, r)
        flash(f"Li {r['atos_lidos']} ato(s) lavrados desde {desde}: "
              f"{r['novos']} caso(s) novo(s) na fila.", "success")
        return redirect(url_for("pld_painel"))

    @app.route("/administrativo/pld/abrir", methods=["POST"])
    @roles_required("ADMIN")
    def pld_abrir():
        valor = (request.form.get("valor") or "").strip()
        try:
            centavos = PLD.centavos(valor) if valor and "," in valor else (
                int(valor) * 100 if valor.isdigit() else None)
            with db.transaction() as con:
                cid = PLD.abrir_para_analise(
                    con, referencia=request.form.get("referencia") or "",
                    data_operacao=request.form.get("data") or "",
                    motivo=request.form.get("motivo") or "", valor_centavos=centavos,
                    atribuicao=(request.form.get("atribuicao") or "NOTAS").upper())
        except (PLD.PldError, ValueError) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("pld_painel"))
        audit("PLD_CASO_ABERTO", "pld_casos", cid, {})
        return redirect(url_for("pld_caso", caso_id=cid))

    @app.route("/administrativo/pld/caso/<int:caso_id>")
    @roles_required("ADMIN")
    def pld_caso(caso_id: int):
        with db.connect() as con:
            try:
                c = PLD.caso(con, caso_id)
            except PLD.PldError:
                abort(404)
            texto = c["texto_comunicacao"] or PLD.montar_comunicacao(con, caso_id)
            recibos = con.execute(
                """SELECT id, original_name, uploaded_at FROM attachments
                    WHERE entity_type=? AND entity_id=? ORDER BY id""",
                (ENTIDADE_DO_RECIBO, caso_id)).fetchall()
        return render_template("pld_caso.html", c=c, texto=texto, recibos=recibos,
                               SITUACOES=PLD.SITUACOES, reais=PLD.reais,
                               siscoaf=ENDERECO_DO_SISCOAF, hoje=date.today().isoformat(),
                               minimo=PLD.MINIMO_DA_FUNDAMENTACAO)

    def _acao(caso_id: int, fazer, evento: str, sucesso: str):
        try:
            with db.transaction() as con:
                fazer(con)
        except PLD.PldError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("pld_caso", caso_id=caso_id))
        audit(evento, "pld_casos", caso_id, {})
        flash(sucesso, "success")
        return redirect(url_for("pld_caso", caso_id=caso_id))

    @app.route("/administrativo/pld/caso/<int:caso_id>/analise", methods=["POST"])
    @roles_required("ADMIN")
    def pld_analise(caso_id: int):
        comunicar = request.form.get("conclusao") == "COMUNICAR"
        return _acao(caso_id, lambda con: PLD.concluir_analise(
            con, caso_id, comunicar=comunicar,
            fundamentacao=request.form.get("fundamentacao") or "",
            usuario=usuario_nome()), "PLD_ANALISE",
            "Análise gravada." + (" O caso passou a «a comunicar»." if comunicar else
                                  " Fica documentada, sem comunicação."))

    @app.route("/administrativo/pld/caso/<int:caso_id>/descartar", methods=["POST"])
    @roles_required("ADMIN")
    def pld_descartar(caso_id: int):
        return _acao(caso_id, lambda con: PLD.descartar(
            con, caso_id, motivo=request.form.get("motivo") or "",
            usuario=usuario_nome()), "PLD_DESCARTE", "Seleção descartada, com o motivo.")

    @app.route("/administrativo/pld/caso/<int:caso_id>/texto", methods=["POST"])
    @roles_required("ADMIN")
    def pld_texto(caso_id: int):
        return _acao(caso_id, lambda con: PLD.guardar_texto(
            con, caso_id, request.form.get("texto") or ""), "PLD_TEXTO",
            "Texto da comunicação guardado.")

    @app.route("/administrativo/pld/caso/<int:caso_id>/enviado", methods=["POST"])
    @roles_required("ADMIN")
    def pld_enviado(caso_id: int):
        recibo = request.files.get("recibo")
        resposta = _acao(caso_id, lambda con: PLD.registrar_envio(
            con, caso_id, numero_coaf=request.form.get("numero_coaf") or "",
            data_envio=request.form.get("data_envio") or "", usuario=usuario_nome()),
            "PLD_COMUNICADA", "Envio registrado com o número do COAF.")
        # O RECIBO SE GUARDA (TJMA, art. 434, § 4º, «h»), e numa pasta própria:
        # quem abre a pasta do ato não deve achar a comunicação ao lado dele.
        if recibo and recibo.filename:
            with db.connect() as con:
                situacao = PLD.caso(con, caso_id)["situacao"]
            if situacao == "COMUNICADA":
                raiz = Path(db.get_setting("archive_root", "").strip()
                            or (Path(db.db_path).parent / "arquivos"))
                info = save_upload(recibo, raiz / "pld_sigiloso" / f"caso-{caso_id:05d}")
                db.add_attachment(ENTIDADE_DO_RECIBO, caso_id, info,
                                  int(app.extensions["usuario_id"]() or 0),
                                  "Recibo da comunicação ao COAF")
        return resposta

    @app.route("/administrativo/pld/nao-ocorrencia/<int:ano>")
    @roles_required("ADMIN")
    def pld_nao_ocorrencia(ano: int):
        with db.connect() as con:
            r = PLD.nao_ocorrencia(con, ano, _sv())
        if not r["cabe"]:
            flash(f"{ano} não pede a comunicação de não ocorrência: "
                  f"{r['comunicadas']} comunicada(s) e {r['pendentes']} caso(s) "
                  f"ainda pendente(s) no ano.", "warning")
            return redirect(url_for("pld_painel"))
        return render_template("pld_nao_ocorrencia.html", r=r)
