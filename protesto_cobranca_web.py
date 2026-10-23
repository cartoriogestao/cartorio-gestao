# -*- coding: utf-8 -*-
"""As telas do LG06 — o AR digital, o boleto, o painel do devedor e o
interruptor das duas integrações no Gestor.

**QUEM FAZ O QUÊ, e a régua é a da Resolve** (`resolve_web`): o que SAI DA CASA
e tem custo — a carta pelos Correios, o boleto registrado no banco — é de
ADMIN e gerente; perguntar o que voltou e dar baixa no que bate é do balcão; o
interruptor é só do ADMIN, como a credencial das Centrais.

**TODA RECUSA VOLTA COMO FRASE**, e não como erro 500: a integração desligada,
o aviso que não pode ir, o banco que não respondeu. É o que o balcão lê.

**O RASTRO VAI PARA `audit_logs`, SEM SEGREDO E SEM CPF.** A configuração
registra o modo e o provedor, nunca a credencial; a busca do devedor registra
QUEM foi aberto (o número interno), e não o número que se digitou.
"""
from __future__ import annotations

from datetime import date

from flask import abort, flash, redirect, render_template, request, url_for

import boleto_api as BAPI
import centrais_cred as CRED
import correios_api as CAPI
import protesto as PT
import protesto_ar as AR
import protesto_aviso as AV
import protesto_boleto as BOL
import protesto_devedor as DEV
import protesto_integracoes as INTEG
from ri_web import data_por_extenso
from serventia import dados as dados_serventia

QUEM_OPERA = ("ADMIN", "MANAGER", "USER")
QUEM_ENVIA = ("ADMIN", "MANAGER")

RECUSAS_DO_BALCAO = (INTEG.IntegracaoError, AR.ArError, BOL.BoletoDominioError,
                     CAPI.CorreiosError, BAPI.BoletoError, CRED.CredencialError,
                     AV.AvisoError, PT.ProtestoError)


def registrar_rotas(app, db, login_required, roles_required, audit):
    """Pendura as telas do LG06 no app já construído."""

    usuario_nome = app.extensions["usuario_nome"]
    usuario_id = app.extensions["usuario_id"]
    pasta_dos_arquivos = app.extensions["archive_root"]

    def hoje() -> str:
        return db.now()[:10]

    def hoje_extenso() -> str:
        return data_por_extenso(date.fromisoformat(hoje()))

    def sv() -> dict:
        return dados_serventia(db.get_settings)

    def _campo(nome: str) -> str:
        return (request.form.get(nome) or "").strip()

    def usuario_papel() -> str:
        return app.extensions["usuario_papel"]() or ""

    def _br(iso) -> str:
        s = str(iso or "")[:10]
        return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if len(s) == 10 else s

    # ------------------------------------------------------- o AR digital

    @app.route("/protesto/ar")
    @roles_required(*QUEM_OPERA)
    def protesto_ar():
        """Os avisos que podem ir pelo correio, o que foi e o que voltou. SÓ LÊ."""
        with db.connect() as con:
            cfg = INTEG.configuracao(con, INTEG.AR)
            ambiente = cfg["ambiente"] or INTEG.PRODUCAO
            postaveis = AR.postaveis(con, ambiente=ambiente)
            postagens = AR.postagens(con, ambiente=ambiente)
            contas = AR.contagens(con, ambiente=ambiente)
            atrasados = AR.sem_retorno(con, hoje=hoje())
        return render_template(
            "protesto_ar.html", cfg=cfg, ambiente=ambiente, postaveis=postaveis,
            postagens=postagens, contas=contas, atrasados=atrasados,
            motivos=CAPI.MOTIVOS, hoje=hoje(),
            pode_enviar=(usuario_papel() in QUEM_ENVIA))

    @app.route("/protesto/ar/<int:aviso_id>/postar", methods=["POST"])
    @roles_required(*QUEM_ENVIA)
    def protesto_ar_postar(aviso_id: int):
        """Manda o aviso pelos Correios, com AR digital. **ESCREVE NOS CORREIOS.**"""
        try:
            r = AR.solicitar_postagem(db, aviso_id, quem=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_ar"))
        audit("PROTESTO_AR_POSTAGEM", "pt_ar_postagens", r["postagem_id"],
              {"aviso_id": aviso_id, "codigo_objeto": r["codigo_objeto"],
               "ambiente": r["ambiente"], "prazo_limite": r["prazo_limite"]})
        flash(f"Aviso postado: objeto {r['codigo_objeto']}"
              + (" (HOMOLOGAÇÃO — nada saiu da casa)"
                 if r["ambiente"] != INTEG.PRODUCAO else "")
              + f". O AR tem de voltar até {_br(r['prazo_limite'])}.",
              "success")
        return redirect(url_for("protesto_ar"))

    @app.route("/protesto/ar/retornos", methods=["POST"])
    @roles_required(*QUEM_OPERA)
    def protesto_ar_retornos():
        """Pergunta pelos AR que saíram e assenta os que voltaram."""
        try:
            r = AR.buscar_retornos(db, quem=usuario_nome(),
                                   usuario_id=usuario_id(),
                                   pasta_de_arquivos=pasta_dos_arquivos())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_ar"))
        conferir = [x for x in r["voltaram"] if x["situacao"] == AR.CONFERIR]
        audit("PROTESTO_AR_RETORNOS", "pt_ar_postagens", None,
              {"ambiente": r["ambiente"], "olhadas": r["olhadas"],
               "voltaram": len(r["voltaram"]), "conferir": len(conferir),
               "falhas": len(r["falhas"])})
        recado = (f"Perguntei por {r['olhadas']} AR; {len(r['voltaram'])} "
                  f"voltaram.")
        if conferir:
            recado += f" {len(conferir)} ficaram para CONFERIR."
        if r["falhas"]:
            # A FALHA APARECE, E NÃO VIRA ZERO.
            recado += f" {len(r['falhas'])} não deu para consultar."
        flash(recado, "warning" if (conferir or r["falhas"]) else "success")
        return redirect(url_for("protesto_ar"))

    @app.route("/protesto/ar/<int:postagem_id>/simular", methods=["POST"])
    @roles_required(*QUEM_ENVIA)
    def protesto_ar_simular(postagem_id: int):
        """O carteiro da homologação: diz ao serviço falso como o AR voltou."""
        try:
            AR.simular_retorno(db, postagem_id,
                               entregue=_campo("entregue") == "1",
                               data=_campo("data") or hoje(),
                               recebedor=_campo("recebedor"),
                               motivo=_campo("motivo"))
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_ar"))
        audit("PROTESTO_AR_SIMULADO", "pt_ar_postagens", postagem_id,
              {"entregue": _campo("entregue") == "1",
               "motivo": _campo("motivo") or None})
        flash("Retorno simulado. Clique em «Buscar os AR que voltaram» para "
              "assentá-lo, como seria com os Correios.", "success")
        return redirect(url_for("protesto_ar"))

    # ------------------------------------------------------------ o boleto

    @app.route("/protesto/boletos")
    @roles_required(*QUEM_OPERA)
    def protesto_boletos():
        """Os títulos que podem ter boleto, os emitidos e as pendências. SÓ LÊ."""
        with db.connect() as con:
            cfg = INTEG.configuracao(con, INTEG.BOLETO)
            ambiente = cfg["ambiente"] or INTEG.PRODUCAO
            emitiveis = BOL.emitiveis(con, hoje=hoje(), ambiente=ambiente)
            lista = BOL.boletos(con, ambiente=ambiente)
            pendencias = BOL.pendencias(con)
            a_cancelar = BOL.vivos_de_titulo_encerrado(con)
        return render_template(
            "protesto_boletos.html", cfg=cfg, ambiente=ambiente,
            emitiveis=emitiveis, boletos=lista, pendencias=pendencias,
            a_cancelar=a_cancelar, hoje=hoje(),
            pode_enviar=(usuario_papel() in QUEM_ENVIA))

    @app.route("/protesto/boletos/<int:titulo_id>/emitir", methods=["POST"])
    @roles_required(*QUEM_ENVIA)
    def protesto_boleto_emitir(titulo_id: int):
        """Registra o boleto do título no banco. **ESCREVE NO BANCO.**"""
        try:
            r = BOL.emitir(db, titulo_id, emolumentos=request.form.get("emolumentos"),
                           hoje=hoje(), quem=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_boletos"))
        audit("PROTESTO_BOLETO_EMITIDO", "pt_boletos", r["boleto_id"],
              {"titulo_id": titulo_id, "ambiente": r["ambiente"],
               "valor_centavos": r["valor_centavos"],
               "vencimento": r["vencimento"]})
        flash(f"Boleto emitido — nosso número {r['nosso_numero'] or '?'}, "
              f"vencimento {_br(r['vencimento'])}"
              + (" (HOMOLOGAÇÃO — não se paga)"
                 if r["ambiente"] != INTEG.PRODUCAO else "") + ".", "success")
        return redirect(url_for("protesto_boletos"))

    @app.route("/protesto/boletos/<int:boleto_id>/cancelar", methods=["POST"])
    @roles_required(*QUEM_ENVIA)
    def protesto_boleto_cancelar(boleto_id: int):
        """Pede ao banco a baixa do boleto aberto. **ESCREVE NO BANCO.**"""
        try:
            BOL.cancelar(db, boleto_id, motivo=_campo("motivo"),
                         quem=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_boletos"))
        audit("PROTESTO_BOLETO_CANCELADO", "pt_boletos", boleto_id,
              {"motivo": _campo("motivo")})
        flash("Boleto cancelado no banco.", "success")
        return redirect(url_for("protesto_boletos"))

    @app.route("/protesto/boletos/<int:boleto_id>/conferir", methods=["POST"])
    @roles_required(*QUEM_OPERA)
    def protesto_boleto_conferir(boleto_id: int):
        """Pergunta ao banco pelo boleto que ficou sem resposta. LÊ LÁ."""
        try:
            r = BOL.conferir_no_banco(db, boleto_id)
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_boletos"))
        audit("PROTESTO_BOLETO_CONFERIDO", "pt_boletos", boleto_id,
              {"situacao": r["situacao"]})
        flash("O banco tem o boleto: ele está EMITIDO." if r["situacao"] == BOL.EMITIDO
              else "O banco não tem o boleto: ficou RECUSADO, e o título pode "
                   "ter outro.", "success")
        return redirect(url_for("protesto_boletos"))

    @app.route("/protesto/boletos/pagamentos", methods=["POST"])
    @roles_required(*QUEM_OPERA)
    def protesto_boletos_pagamentos():
        """Pergunta ao banco o que foi pago e dá baixa no que bate."""
        try:
            r = BOL.buscar_pagamentos(db, sv=sv(), data_extenso=hoje_extenso(),
                                      hoje=hoje(), quem=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_boletos"))
        audit("PROTESTO_BOLETO_PAGAMENTOS", "pt_boletos", None,
              {"ambiente": r["ambiente"], "vistas": r["vistas"],
               "baixadas": len(r["baixadas"]), "conferir": len(r["conferir"]),
               "atos": [x.get("ato_id") for x in r["baixadas"] if x.get("ato_id")]})
        if not r["perguntou"]:
            flash("Não há boleto em aberto — não havia o que perguntar ao banco.",
                  "info")
        else:
            flash(f"O banco devolveu {r['vistas']} pagamento(s): "
                  f"{len(r['baixadas'])} com baixa"
                  + (" (homologação: sem baixa no título)"
                     if r["ambiente"] != INTEG.PRODUCAO else "")
                  + f", {len(r['conferir'])} para conferir, "
                    f"{r['ja_vistas']} já vistos antes.",
                  "warning" if r["conferir"] else "success")
        return redirect(url_for("protesto_boletos"))

    @app.route("/protesto/boletos/<int:boleto_id>/simular", methods=["POST"])
    @roles_required(*QUEM_ENVIA)
    def protesto_boleto_simular(boleto_id: int):
        """O devedor da homologação pagando, no serviço falso."""
        try:
            BOL.simular_pagamento(db, boleto_id, pago_em=_campo("pago_em") or hoje(),
                                  valor=_campo("valor") or None)
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_boletos"))
        audit("PROTESTO_BOLETO_SIMULADO", "pt_boletos", boleto_id,
              {"valor": _campo("valor") or None})
        flash("Pagamento simulado. Clique em «Buscar pagamentos no banco» para "
              "conciliar, como seria com o banco.", "success")
        return redirect(url_for("protesto_boletos"))

    @app.route("/protesto/boletos/liquidacoes/<int:liquidacao_id>/resolver",
               methods=["POST"])
    @roles_required(*QUEM_ENVIA)
    def protesto_boleto_resolver(liquidacao_id: int):
        """Fecha a pendência com o que foi feito, escrito. Não lavra nada."""
        try:
            BOL.resolver_pendencia(db, liquidacao_id,
                                   conferencia=_campo("conferencia"),
                                   quem=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_boletos"))
        audit("PROTESTO_BOLETO_PENDENCIA", "pt_boletos_liquidacoes",
              liquidacao_id, {"conferencia": _campo("conferencia")})
        flash("Pendência resolvida.", "success")
        return redirect(url_for("protesto_boletos"))

    # ------------------------------------------------- o painel do devedor

    @app.route("/protesto/devedores")
    @roles_required(*QUEM_OPERA)
    def protesto_devedores():
        """Os devedores com título em andamento, os com alerta primeiro. SÓ LÊ."""
        with db.connect() as con:
            r = DEV.devedores_em_andamento(con, hoje=hoje())
        return render_template("protesto_devedores.html", r=r,
                               alertas=DEV.ALERTAS, hoje=hoje())

    @app.route("/protesto/devedores/buscar", methods=["POST"])
    @roles_required(*QUEM_OPERA)
    def protesto_devedores_buscar():
        """Acha o devedor pelo CPF/CNPJ. **O número não vai no endereço**: a
        busca é POST, e a ficha abre pelo número interno."""
        with db.connect() as con:
            achado = DEV.achar(con, _campo("documento"))
        # NO RASTRO, QUEM FOI ABERTO — e não o número digitado.
        audit("PROTESTO_DEVEDOR_BUSCA", "pt_devedores", achado,
              {"encontrado": bool(achado)})
        if not achado:
            flash("Nenhum devedor com esse CPF/CNPJ nos títulos do Protesto. "
                  "Confira os dígitos (11 do CPF, 14 do CNPJ).", "warning")
            return redirect(url_for("protesto_devedores"))
        return redirect(url_for("protesto_devedor", devedor_id=achado))

    @app.route("/protesto/devedores/<int:devedor_id>")
    @roles_required(*QUEM_OPERA)
    def protesto_devedor(devedor_id: int):
        """Tudo de um devedor: títulos, prazos, intimações, pagamentos e
        alertas. SÓ LÊ o Protesto; a consulta fica no rastro (LGPD)."""
        with db.connect() as con:
            p = DEV.painel(con, devedor_id, hoje=hoje())
        if p is None:
            abort(404)
        audit("PROTESTO_DEVEDOR_CONSULTA", "pt_devedores", devedor_id,
              {"titulos": p["resumo"]["titulos"]})
        return render_template("protesto_devedor.html", p=p, hoje=hoje(),
                               formas=PT.FORMAS_DE_PAGAMENTO)

    # ------------------------------------------------ o interruptor (Gestor)

    @app.route("/administrativo/gestor/protesto-integracoes")
    @roles_required("ADMIN")
    def gestor_protesto_integracoes():
        """O modo e o provedor do AR e do boleto. SÓ LÊ — e não mostra segredo."""
        with db.connect() as con:
            quadro = INTEG.quadro(con)
        return render_template("gestor_protesto_integracoes.html", quadro=quadro,
                               modos=INTEG.MODOS, rotulos=INTEG.ROTULO_DO_MODO)

    @app.route("/administrativo/gestor/protesto-integracoes/salvar",
               methods=["POST"])
    @roles_required("ADMIN")
    def gestor_protesto_integracoes_salvar():
        """Grava o modo e o provedor. **A credencial não passa por aqui.**"""
        qual = _campo("integracao").upper()
        try:
            with db.transaction() as con:
                cfg = INTEG.gravar_configuracao(
                    con, qual, modo=_campo("modo"), provedor=_campo("provedor"),
                    tarifa=request.form.get("tarifa"))
        except INTEG.IntegracaoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("gestor_protesto_integracoes"))
        audit("PROTESTO_INTEGRACAO_CONFIG", "settings", None,
              {"integracao": cfg["integracao"], "modo": cfg["modo"],
               "provedor": cfg["provedor"],
               "tarifa_centavos": cfg.get("tarifa_centavos")})
        flash(f"{cfg['nome']}: {cfg['rotulo_do_modo']}.", "success")
        return redirect(url_for("gestor_protesto_integracoes"))

    @app.route("/administrativo/gestor/protesto-integracoes/testar",
               methods=["POST"])
    @roles_required("ADMIN")
    def gestor_protesto_integracoes_testar():
        """Pergunta ao transporte ligado se ele responde. Não manda nada."""
        qual = _campo("integracao").upper()
        try:
            with db.connect() as con:
                _cfg, transporte = INTEG.transporte_em_uso(con, qual)
            r = transporte.diagnostico()
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("gestor_protesto_integracoes"))
        flash(("Responde: " if r.get("ok") else "Não responde: ")
              + str(r.get("motivo") or ""), "success" if r.get("ok") else "danger")
        return redirect(url_for("gestor_protesto_integracoes"))
