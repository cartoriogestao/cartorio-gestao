# -*- coding: utf-8 -*-
"""As telas da Intimação Digital — escolher, mandar e acompanhar.

**UM PASSO DE CADA VEZ, e a decisão é de quem clica.** A lista mostra os
títulos que poderiam ir e **por que cada um não pode**; o envio manda só os
marcados; e o acompanhamento pergunta à Central sem mudar ato nenhum desta
casa.

**MANDAR NÃO É DO BALCÃO.** A intimação chega na casa do devedor e tem custo —
é a mesma separação da ajuda do Claude e do envio da CENPROT: consultar abre,
mandar não.
"""
from __future__ import annotations

import json
import sqlite3

from flask import flash, redirect, render_template, request, url_for

import centrais_cred as CENTCRED
import resolve_api as API
import resolve_intimacao as RI

QUEM_OPERA = ("ADMIN", "MANAGER", "USER")
QUEM_ENVIA = ("ADMIN", "MANAGER")

# O QUE VOLTA COMO FRASE, E NÃO COMO HTTP 500. São três de propósito, e a
# terceira é a que me pegou na CENPROT: falta de credencial estoura
# `CredencialError`, que não é nem erro de regra nem de transporte.
RECUSAS_DO_BALCAO = (RI.IntimacaoDigitalError, API.ResolveError,
                     CENTCRED.CredencialError)


def registrar_rotas(app, db, login_required, roles_required, audit):
    """Pendura as telas da Intimação Digital no app já construído."""

    usuario_nome = app.extensions["usuario_nome"]

    def ambiente_pedido() -> str:
        """Qual ambiente a tela usa: **sempre PRODUÇÃO, desde 14/10/2026**.

        Ordem do oficial no primeiro dia do protesto no sistema: «tire a
        opção de funcionar na homologação, agora é tudo produção». Até 13/10
        a tela lia `ambiente` do pedido, com homologação por padrão e `TESTES`
        quando vinha no endereço; agora o que vier no endereço ou no
        formulário não muda nada.
        """
        return CENTCRED.PRODUCAO

    # ---------------------------------------------------------- a lista

    @app.route("/protesto/resolve")
    @roles_required(*QUEM_OPERA)
    def protesto_resolve():
        """Os títulos que podem ir, e o que já foi. SÓ LÊ."""
        ambiente = ambiente_pedido()
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            titulos = RI.candidatos(con)
            quadro = RI.quantos_podem_ir(con)
            enviadas = RI.abertas(con, ambiente=ambiente)
        return render_template(
            "protesto_resolve.html",
            titulos=titulos, quadro=quadro, enviadas=enviadas,
            ambiente=ambiente,
            tem_credencial=CENTCRED.tem(CENTCRED.RESOLVE, ambiente),
            fora_de_uso=CENTCRED.fora_de_uso(CENTCRED.RESOLVE),
            estados=API.ESTADOS, maximo=API.MAXIMO_DO_LOTE)

    # ---------------------------------------------------------- o envio

    @app.route("/protesto/resolve/enviar", methods=["POST"])
    @roles_required(*QUEM_ENVIA)
    def protesto_resolve_enviar():
        """Manda os títulos marcados. **ESCREVE NA CENTRAL.**"""
        ambiente = ambiente_pedido()
        marcados = request.form.getlist("titulo_id")
        try:
            r = RI.enviar(db, marcados, ambiente=ambiente,
                          quem=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_resolve", ambiente=ambiente))
        audit("resolve_enviar",
              f"{r['mandadas']} intimações, lote {r['lote_id'] or '-'}, "
              f"ambiente {ambiente}")
        flash(f"Foram mandadas {r['mandadas']} intimações "
              f"({r['gravadas']} novas nesta casa). Lote "
              f"{r['lote_id'] or 'sem número'}.", "success")
        return redirect(url_for("protesto_resolve", ambiente=ambiente))

    # --------------------------------------------------- o acompanhamento

    @app.route("/protesto/resolve/atualizar", methods=["POST"])
    @roles_required(*QUEM_OPERA)
    def protesto_resolve_atualizar():
        """Pergunta à Central o estado de cada uma. **Não muda ato nenhum.**"""
        ambiente = ambiente_pedido()
        try:
            r = RI.atualizar_estados(db, ambiente=ambiente,
                                     quem=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_resolve", ambiente=ambiente))
        recado = (f"Perguntei por {r['olhadas']} intimações; "
                  f"{r['mudaram']} mudaram de estado.")
        if r["falhas"]:
            # **A FALHA APARECE, E NÃO VIRA ZERO.** Um dia em que a Central não
            # respondeu não pode parecer um dia em que nada mudou.
            recado += f" {len(r['falhas'])} não deu para consultar."
        flash(recado, "success" if not r["falhas"] else "warning")
        return redirect(url_for("protesto_resolve", ambiente=ambiente))

    # ------------------------------------------------------------ a ficha

    @app.route("/protesto/resolve/<int:intimacao_id>")
    @roles_required(*QUEM_OPERA)
    def protesto_resolve_ficha(intimacao_id: int):
        """O que subiu, o que a Central respondeu, e o histórico. SÓ LÊ."""
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            item = RI.uma(con, intimacao_id)
        if item is None:
            flash("Essa intimação não existe.", "warning")
            return redirect(url_for("protesto_resolve"))
        return render_template(
            "protesto_resolve_ficha.html", i=item,
            teor_bonito=json.dumps(item["teor_aberto"], ensure_ascii=False,
                                   indent=2) if item["teor_aberto"] else "",
            avisos=RI.AVISOS_A_CENTRAL,
            tem_credencial=CENTCRED.tem(CENTCRED.RESOLVE, item["ambiente"]))

    @app.route("/protesto/resolve/<int:intimacao_id>/historico", methods=["POST"])
    @roles_required(*QUEM_OPERA)
    def protesto_resolve_historico(intimacao_id: int):
        """Traz o histórico de tentativas da Central. SÓ LÊ lá.

        **É a prova de que se tentou** — a Central devolve, por tentativa, o
        canal, o destinatário, a data e uma assinatura HMAC. É o que se lê
        quando alguém perguntar por que o título foi a edital.
        """
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            item = RI.uma(con, intimacao_id)
        if item is None or not (item.get("intimacao_id") or "").strip():
            flash("Essa intimação não tem número na Central.", "warning")
            return redirect(url_for("protesto_resolve"))
        try:
            # A INTIMAÇÃO DE HOMOLOGAÇÃO OU TESTES NÃO SE CONSULTA MAIS
            # (14/10/2026) — `ambiente_de_uso` recusa com a frase.
            historico = API.historico_de(
                item["intimacao_id"],
                CENTCRED.ambiente_de_uso(CENTCRED.RESOLVE, item["ambiente"]))
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_resolve_ficha",
                                    intimacao_id=intimacao_id))
        with db.transaction() as con:
            con.execute(
                "UPDATE rs_intimacoes SET historico = ? WHERE id = ?",
                (json.dumps(historico, ensure_ascii=False)[:4000],
                 intimacao_id))
        flash("Histórico atualizado.", "success")
        return redirect(url_for("protesto_resolve_ficha",
                                intimacao_id=intimacao_id))

    @app.route("/protesto/resolve/<int:intimacao_id>/pdf", methods=["POST"])
    @roles_required(*QUEM_OPERA)
    def protesto_resolve_pdf(intimacao_id: int):
        """O link do PDF da intimação — **o comprovante**. SÓ LÊ lá.

        **O arquivo não se guarda no banco**: a Central devolve uma URL, e o
        banco viaja no backup. Guardar o PDF aqui seria pôr no backup o que já
        está lá.
        """
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            item = RI.uma(con, intimacao_id)
        if item is None or not (item.get("intimacao_id") or "").strip():
            flash("Essa intimação não tem número na Central.", "warning")
            return redirect(url_for("protesto_resolve"))
        try:
            r = API.pdf_da_intimacao(
                item["intimacao_id"],
                CENTCRED.ambiente_de_uso(CENTCRED.RESOLVE, item["ambiente"]))
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_resolve_ficha",
                                    intimacao_id=intimacao_id))
        link = ""
        if isinstance(r, dict):
            link = str(r.get("link") or r.get("url") or "").strip()
        if link:
            flash(f"O comprovante está em: {link}", "success")
        else:
            flash("A Central respondeu, e não veio link no formato esperado: "
                  f"{str(r)[:200]}", "warning")
        return redirect(url_for("protesto_resolve_ficha",
                                intimacao_id=intimacao_id))

    @app.route("/protesto/resolve/<int:intimacao_id>/avisar", methods=["POST"])
    @roles_required(*QUEM_ENVIA)
    def protesto_resolve_avisar(intimacao_id: int):
        """Diz à Central o que aconteceu aqui. **ESCREVE NA CENTRAL.**"""
        qual = str(request.form.get("qual") or "").strip().lower()
        try:
            r = RI.avisar(db, intimacao_id, qual, quem=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_resolve_ficha",
                                    intimacao_id=intimacao_id))
        audit("resolve_avisar", f"intimação {intimacao_id}: {r['estado']}")
        flash(f"A Central foi avisada {r['o_que']}.", "success")
        return redirect(url_for("protesto_resolve_ficha",
                                intimacao_id=intimacao_id))

    @app.route("/protesto/resolve/lote/<lote_id>/pdfs", methods=["POST"])
    @roles_required(*QUEM_OPERA)
    def protesto_resolve_pdfs_do_lote(lote_id: str):
        """Os comprovantes de um lote inteiro, de uma vez. SÓ LÊ lá."""
        ambiente = ambiente_pedido()
        try:
            r = API.pdfs_do_lote(lote_id, ambiente)
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_resolve", ambiente=ambiente))
        links = (r or {}).get("links") or []
        flash(f"O lote tem {len(links)} comprovante(s): "
              + " · ".join(str(x) for x in links[:5])
              + (" …" if len(links) > 5 else ""), "success")
        return redirect(url_for("protesto_resolve", ambiente=ambiente))

    # ------------------------------------------------------ o diagnóstico

    @app.route("/protesto/resolve/testar", methods=["POST"])
    @roles_required(*QUEM_ENVIA)
    def protesto_resolve_testar():
        """Testa a ligação. **Não manda nem baixa intimação nenhuma.**"""
        ambiente = ambiente_pedido()
        de_pe = API.status(ambiente)
        if not de_pe["ok"]:
            flash(f"A Resolve não respondeu em {de_pe['base']}: "
                  f"{de_pe['motivo']}.", "danger")
            return redirect(url_for("protesto_resolve", ambiente=ambiente))
        r = API.diagnostico(ambiente)
        flash(("Ligação boa: " if r["ok"] else "Não deu: ") + r["motivo"],
              "success" if r["ok"] else "danger")
        return redirect(url_for("protesto_resolve", ambiente=ambiente))
