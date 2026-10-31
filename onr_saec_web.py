"""As telas do atendimento eletrônico do ONR (SAEC) e das cobranças.

    «Lista de pedidos do SAEC», «Responder no SAEC e cobrar»    — o oficial, 30/10/2026

LER É DO BALCÃO; ESCREVER LÁ FORA É SÓ DO ADMIN
    Responder e gerar cobrança falam em nome da serventia, e a cobrança mexe com o dinheiro do cliente.
    Cada clique vale para um atendimento ou uma cobrança: nada aqui responde em lote.

A ORDEM DE CADA ENVIO
    1. confere o formulário, sem rede; 2. reserva a chave, em transação própria; 3. fala com o ONR,
    fora de transação; 4. anota o que ele disse; 5. audita, fora de transação. O CPF do pagador nunca
    vai no endereço: a tela da cobrança nova só recebe o número do atendimento.
"""
from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, url_for

import centrais_cred as CRED
import onr_api as API
import onr_saec as SAEC
from seguranca_web import numero_digitado

QUEM_LE = ("ADMIN", "MANAGER", "USER")
QUEM_VE_COBRANCA = ("ADMIN", "MANAGER")
QUEM_ESCREVE = ("ADMIN",)
RECUSAS = (API.OnrError, CRED.CredencialError)
POR_PAGINA = 100
PEDE_CONFERIR = ("O ONR não confirmou. Pode ter entrado mesmo assim: confira antes de repetir, "
                 "para não {o_que} duas vezes. O que aconteceu: {erro}")


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_nome = app.extensions["usuario_nome"]

    def agora() -> str:
        return db.now()

    def hoje() -> str:
        return agora()[:10]

    with db.connect() as con:
        SAEC.init_schema(con)

    def _anotar(chave: str, situacao: str, **dados) -> None:
        with db.transaction() as con:
            SAEC.anotar(con, chave=chave, situacao=situacao, agora=agora(), **dados)

    # ------------------------------------------------------------ o atendimento

    @app.route("/ri/onr/atendimentos")
    @login_required
    @roles_required(*QUEM_LE)
    def onr_saec():
        """A lista, direto do ONR. Só lê. Sem credencial, a tela diz isso e não vai à rede."""
        status = numero_digitado(request.args.get("status"))
        tipo = numero_digitado(request.args.get("tipo"))
        filtros = {
            "pagina": max(1, numero_digitado(request.args.get("pagina")) or 1),
            "status": status if status in SAEC.SITUACOES else None,
            "tipo": tipo if tipo in SAEC.TIPOS else None,
            "protocolo": (request.args.get("protocolo") or "").strip()[:150],
        }
        lista, erro = None, ""
        tem_credencial = API.tem_credencial()
        if tem_credencial:
            try:
                lista = SAEC.atendimentos_da_resposta(API.atendimentos(
                    pagina=filtros["pagina"], por_pagina=POR_PAGINA, tipo_atendimento=filtros["tipo"],
                    status=filtros["status"], protocolo=filtros["protocolo"] or None))
            except RECUSAS as e:
                erro = str(e)
        return render_template("onr_saec.html", lista=lista, erro=erro, filtros=filtros,
                               tem_credencial=tem_credencial, situacoes=SAEC.SITUACOES, tipos=SAEC.TIPOS)

    def _ficha(atendimento_id: int, *, mensagem: str = "", acao: str = "0", forma: str = ""):
        try:
            a = SAEC.atendimento_da_resposta(API.atendimento(atendimento_id))
        except RECUSAS as e:
            flash(str(e), "danger")
            return redirect(url_for("onr_saec"))
        with db.connect() as con:
            envios = SAEC.envios_do_atendimento(con, atendimento_id)
        return render_template("onr_saec_ficha.html", a=a, atendimento_id=atendimento_id, envios=envios,
                               acoes=SAEC.ACOES, formas=SAEC.FORMAS, chave=SAEC.chave_nova(),
                               mensagem=mensagem, acao=acao, forma=forma, reais=SAEC.reais)

    @app.route("/ri/onr/atendimentos/<int:atendimento_id>")
    @login_required
    @roles_required(*QUEM_LE)
    def onr_saec_ficha(atendimento_id: int):
        return _ficha(atendimento_id)

    @app.route("/ri/onr/atendimentos/<int:atendimento_id>/responder", methods=["POST"])
    @login_required
    @roles_required(*QUEM_ESCREVE)
    def onr_saec_responder(atendimento_id: int):
        """Uma resposta, em nome da serventia. Não emite certidão nem cobra nada."""
        chave = request.form.get("chave") or ""
        mensagem = request.form.get("mensagem") or ""
        acao = request.form.get("acao") or "0"
        forma = request.form.get("forma") or ""
        voltar = dict(mensagem=mensagem, acao=acao, forma=forma)
        try:
            corpo = SAEC.corpo_da_resposta(acao, mensagem, forma)
            with db.transaction() as con:
                nova = SAEC.reservar(con, chave=chave, tipo=SAEC.RESPOSTA, atendimento_id=atendimento_id,
                                     resumo=f"{SAEC.ACOES[corpo['acao']]}: {corpo['mensagem']}",
                                     valor_centavos=None, por=usuario_nome(), agora=agora())
        except SAEC.SaecError as e:
            flash(str(e), "danger")
            return _ficha(atendimento_id, **voltar)
        if not nova:
            flash("Este formulário já foi enviado. A resposta não foi repetida.", "warning")
            return redirect(url_for("onr_saec_ficha", atendimento_id=atendimento_id))
        rastro = {"acao": corpo["acao"], "mensagem": corpo["mensagem"][:2000]}
        try:
            API.interagir_no_atendimento(atendimento_id, corpo)
        except API.OnrRecusou as e:
            _anotar(chave, SAEC.RECUSADO, erro=str(e))
            audit("ONR_SAEC_RESPOSTA_RECUSADA", "onr_atendimento", atendimento_id, {**rastro, "erro": str(e)[:400]})
            flash(str(e), "danger")
            return _ficha(atendimento_id, **voltar)
        except RECUSAS as e:
            _anotar(chave, SAEC.SEM_RESPOSTA, erro=str(e))
            audit("ONR_SAEC_RESPOSTA_SEM_CONFIRMACAO", "onr_atendimento", atendimento_id,
                  {**rastro, "erro": str(e)[:400]})
            flash(PEDE_CONFERIR.format(o_que="responder", erro=e), "warning")
            return _ficha(atendimento_id, **voltar)
        _anotar(chave, SAEC.ACEITO)
        audit("ONR_SAEC_RESPONDIDO", "onr_atendimento", atendimento_id, rastro)
        flash("Resposta registrada no ONR.", "ok")
        return redirect(url_for("onr_saec_ficha", atendimento_id=atendimento_id))

    # ------------------------------------------------------------ a cobrança

    @app.route("/ri/onr/cobrancas")
    @login_required
    @roles_required(*QUEM_VE_COBRANCA)
    def onr_cobrancas():
        """O que o ONR tem, e as tentativas desta casa. Só lê."""
        pagina = max(1, numero_digitado(request.args.get("pagina")) or 1)
        lista, erro = None, ""
        tem_credencial = API.tem_credencial()
        if tem_credencial:
            try:
                lista = SAEC.cobrancas_da_resposta(API.cobrancas(pagina=pagina, por_pagina=POR_PAGINA))
            except RECUSAS as e:
                erro = str(e)
        with db.connect() as con:
            desta_casa = SAEC.cobrancas_desta_casa(con)
        return render_template("onr_cobrancas.html", lista=lista, erro=erro, pagina=pagina,
                               tem_credencial=tem_credencial, desta_casa=desta_casa, reais=SAEC.reais)

    def _nova(campos: dict, atendimento_id: int | None):
        tipos: list[dict] = []
        tem_credencial = API.tem_credencial()
        if tem_credencial:
            try:
                tipos = SAEC.tipos_de_pagamento_da_resposta(API.tipos_de_pagamento())
            except RECUSAS:
                # O campo é opcional no contrato: sem a lista, a cobrança sai sem ele.
                tipos = []
        return render_template("onr_cobranca_nova.html", campos=campos, atendimento_id=atendimento_id,
                               tipos=tipos, chave=SAEC.chave_nova(), hoje=hoje(),
                               tem_credencial=tem_credencial, quantos=range(1, SAEC.SERVICOS_NA_TELA + 1))

    @app.route("/ri/onr/cobrancas/nova")
    @login_required
    @roles_required(*QUEM_ESCREVE)
    def onr_cobranca_nova():
        """O formulário. Vindo de um atendimento, abre com o que ele sabe do pagador."""
        atendimento_id = numero_digitado(request.args.get("atendimento"))
        campos: dict = {}
        if atendimento_id and API.tem_credencial():
            try:
                campos = SAEC.campos_do_atendimento(SAEC.atendimento_da_resposta(API.atendimento(atendimento_id)))
            except RECUSAS as e:
                flash(f"Não consegui trazer os dados do atendimento: {e}", "warning")
        return _nova(campos, atendimento_id)

    @app.route("/ri/onr/cobrancas/gerar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_ESCREVE)
    def onr_cobranca_gerar():
        """Uma cobrança de verdade no ONR. Dois cliques no mesmo formulário valem um envio."""
        campos = request.form.to_dict()
        chave = campos.get("chave") or ""
        atendimento_id = numero_digitado(campos.get("atendimento_id"))
        try:
            corpo = SAEC.corpo_da_cobranca(campos, hoje=hoje())
            total = SAEC.total_em_centavos(corpo)
            with db.transaction() as con:
                nova = SAEC.reservar(con, chave=chave, tipo=SAEC.COBRANCA, atendimento_id=atendimento_id,
                                     resumo=f"{corpo['tipoCobranca']} para {corpo['dadosPagador']['nome']}, "
                                            f"vencimento {corpo['dataVencimento']}",
                                     valor_centavos=total, por=usuario_nome(), agora=agora())
        except SAEC.SaecError as e:
            flash(str(e), "danger")
            return _nova(campos, atendimento_id)
        if not nova:
            flash("Este formulário já foi enviado. A cobrança não foi repetida: confira a lista.", "warning")
            return redirect(url_for("onr_cobrancas"))
        rastro = {"atendimento": atendimento_id, "centavos": total, "tipo": corpo["tipoCobranca"],
                  "pagador": corpo["dadosPagador"]["nome"]}
        try:
            r = API.gerar_cobranca(corpo)
        except API.OnrRecusou as e:
            _anotar(chave, SAEC.RECUSADO, erro=str(e))
            audit("ONR_COBRANCA_RECUSADA", "onr_cobranca", None, {**rastro, "erro": str(e)[:400]})
            flash(str(e), "danger")
            return _nova(campos, atendimento_id)
        except RECUSAS as e:
            _anotar(chave, SAEC.SEM_RESPOSTA, erro=str(e))
            audit("ONR_COBRANCA_SEM_CONFIRMACAO", "onr_cobranca", None, {**rastro, "erro": str(e)[:400]})
            flash(PEDE_CONFERIR.format(o_que="cobrar", erro=e), "warning")
            return redirect(url_for("onr_cobrancas"))
        bruto = r.get("bruto") if isinstance(r.get("bruto"), dict) else {}
        dados = bruto.get("data") if isinstance(bruto.get("data"), dict) else bruto
        _anotar(chave, SAEC.ACEITO, hash_cobranca=r.get("hash") or "", url=SAEC.url_segura(r.get("url")),
                qrcode=SAEC.qrcode_seguro(dados.get("qrcode")))
        audit("ONR_COBRANCA_GERADA", "onr_cobranca", None, {**rastro, "hash": r.get("hash"), "url": r.get("url")})
        flash("Cobrança gerada no ONR.", "ok")
        if SAEC.hash_valido(r.get("hash")):
            return redirect(url_for("onr_cobranca_ficha", hash_cobranca=r["hash"]))
        return redirect(url_for("onr_cobrancas"))

    @app.route("/ri/onr/cobrancas/<hash_cobranca>")
    @login_required
    @roles_required(*QUEM_VE_COBRANCA)
    def onr_cobranca_ficha(hash_cobranca: str):
        if not SAEC.hash_valido(hash_cobranca):
            abort(404)
        try:
            c = SAEC.cobranca_da_resposta(API.cobranca(hash_cobranca))
        except RECUSAS as e:
            flash(str(e), "danger")
            return redirect(url_for("onr_cobrancas"))
        with db.connect() as con:
            envio = SAEC.envio_da_cobranca(con, hash_cobranca)
        return render_template("onr_cobranca_ficha.html", c=c, envio=envio, reais=SAEC.reais)
