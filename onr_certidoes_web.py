"""As telas das certidões pedidas pelo ONR (Ofício Eletrônico, «Certidões a Emitir»).

    «faça a da onr certidões»                       — o oficial, 11/10/2026

QUATRO BOTÕES MUDAM COISA NO ONR — custas, enviar, finalizar, devolver — e
cada um é um clique sobre UM pedido: nada aqui responde em lote. Buscar só lê.

A REDE ACONTECE FORA DE `db.transaction()`: primeiro a chamada ao ONR, depois
a transação curta que registra o que ele respondeu. Se o ONR recusar, nada se
grava aqui, e a tela diz o código e a frase dele.

É DO BALCÃO (ADMIN, MANAGER e USER): responder pedido de certidão é rotina do
RI operacional — feito à mão no portal, era o maior bloco de tempo de quem cuida
do RI operacional (medido de 06 a 09/10/2026).
"""
from __future__ import annotations

from datetime import date, timedelta

from flask import flash, redirect, render_template, request, url_for

import onr_certidoes as OC
import onr_wsoficio as WS

QUEM = ("ADMIN", "MANAGER", "USER")
RECUSAS = (OC.CertidaoOnrError, WS.WSOficioError)


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_nome = app.extensions["usuario_nome"]
    usuario_id = app.extensions["usuario_id"]
    archive_root = app.extensions["archive_root"]

    def agora() -> str:
        return db.now()

    def ambiente() -> str:
        valor = str(db.get_setting("onr_certidoes_ambiente", WS.PRODUCAO) or WS.PRODUCAO)
        return valor if valor in WS.BASE else WS.PRODUCAO

    def sessao() -> WS.Sessao:
        return WS.Sessao(ambiente=ambiente())

    with db.connect() as con:
        OC.init_schema(con)

    @app.route("/ri/onr/certidoes")
    @roles_required(*QUEM)
    def onr_certidoes():
        todos = request.args.get("todos") == "1"
        with db.connect() as con:
            lista = OC.fila(con, todos=todos)
        return render_template("onr_certidoes.html", lista=lista, todos=todos,
                               ambiente=ambiente(), credencial=WS.situacao(ambiente()),
                               rotulo_do_tipo=OC.rotulo_do_tipo,
                               rotulo_do_status=OC.rotulo_do_status)

    @app.route("/ri/onr/certidoes/buscar", methods=["POST"])
    @roles_required(*QUEM)
    def onr_certidoes_buscar():
        """Traz do ONR os pedidos dos últimos dias. SÓ LÊ do lado de lá."""
        dias = max(1, min(90, int(request.form.get("dias") or 30)))
        de = (date.today() - timedelta(days=dias)).isoformat()
        try:
            r = sessao().certidoes_a_emitir(de=de, ate=date.today().isoformat())
        except RECUSAS as erro:
            flash(str(erro), "danger")
            return redirect(url_for("onr_certidoes"))
        try:
            with db.transaction() as con:
                res = OC.guardar_pedidos(con, ambiente(), r.get("XML") or "", agora())
        except OC.CertidaoOnrError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("onr_certidoes"))
        audit("ONR_CERTIDOES_BUSCADAS", "onr_cert_pedidos", None,
              {"desde": de, **res, "vazio": bool(r.get("vazio"))})
        flash(f"ONR consultado desde {de}: {res['novos']} pedido(s) novo(s), "
              f"{res['atualizados']} atualizado(s).", "ok")
        return redirect(url_for("onr_certidoes"))

    @app.route("/ri/onr/certidoes/<int:pedido_id>")
    @roles_required(*QUEM)
    def onr_certidao_ficha(pedido_id: int):
        with db.connect() as con:
            try:
                p = OC.pedido(con, pedido_id)
            except OC.CertidaoOnrError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("onr_certidoes"))
            anexos = OC.anexos(con, pedido_id)
        return render_template("onr_certidao_ficha.html", p=p, anexos=anexos,
                               rotulo_do_tipo=OC.rotulo_do_tipo,
                               rotulo_do_status=OC.rotulo_do_status,
                               pesquisa=WS.PESQUISA_POR)

    def _voltar(pedido_id: int):
        return redirect(url_for("onr_certidao_ficha", pedido_id=pedido_id))

    @app.route("/ri/onr/certidoes/<int:pedido_id>/anexo", methods=["POST"])
    @roles_required(*QUEM)
    def onr_certidao_anexo(pedido_id: int):
        """Guarda AQUI o arquivo assinado. Não manda nada ao ONR."""
        arquivo = request.files.get("arquivo")
        if not arquivo or not arquivo.filename:
            flash("Escolha o arquivo assinado da certidão (PDF ou P7S).", "danger")
            return _voltar(pedido_id)
        try:
            with db.transaction() as con:
                aid = OC.guardar_anexo(con, pedido_id, nome=arquivo.filename,
                                       conteudo=arquivo.read(),
                                       pasta=archive_root() / "ri" / "onr" / "certidoes",
                                       usuario_id=usuario_id(), agora=agora())
        except OC.CertidaoOnrError as erro:
            flash(str(erro), "danger")
            return _voltar(pedido_id)
        audit("ONR_CERTIDAO_ANEXO_GUARDADO", "onr_cert_pedidos", pedido_id, {"anexo": aid})
        flash("Arquivo guardado. Confira e clique em «Enviar ao ONR».", "ok")
        return _voltar(pedido_id)

    @app.route("/ri/onr/certidoes/<int:pedido_id>/custas", methods=["POST"])
    @roles_required(*QUEM)
    def onr_certidao_custas(pedido_id: int):
        try:
            valor = OC.conferir_custas(request.form.get("valor"))
            with db.connect() as con:
                p = OC.pedido(con, pedido_id)
            if p["custas_informadas"]:
                raise OC.CertidaoOnrError("As custas deste pedido já foram informadas ao ONR.")
            sessao().informar_custas_da_certidao(p["protocolo"], valor)
        except RECUSAS as erro:
            flash(str(erro), "danger")
            return _voltar(pedido_id)
        with db.transaction() as con:
            OC.registrar_custas(con, pedido_id, valor, usuario_nome(), agora())
        audit("ONR_CERTIDAO_CUSTAS", "onr_cert_pedidos", pedido_id, {"valor": valor})
        flash(f"Custas de R$ {valor} informadas ao ONR.", "ok")
        return _voltar(pedido_id)

    @app.route("/ri/onr/certidoes/<int:pedido_id>/enviar", methods=["POST"])
    @roles_required(*QUEM)
    def onr_certidao_enviar(pedido_id: int):
        try:
            with db.connect() as con:
                p = OC.pedido(con, pedido_id)
                lista = OC.anexos_para_enviar(con, pedido_id)
            sessao().enviar_anexos_da_certidao(p["protocolo"], lista)
        except RECUSAS as erro:
            flash(str(erro), "danger")
            return _voltar(pedido_id)
        nomes = [a["NomeArquivo"] for a in lista]
        with db.transaction() as con:
            OC.registrar_envio(con, pedido_id, nomes, usuario_nome(), agora())
        audit("ONR_CERTIDAO_ENVIADA", "onr_cert_pedidos", pedido_id, {"anexos": nomes})
        flash("Arquivo enviado ao ONR. Agora finalize o pedido.", "ok")
        return _voltar(pedido_id)

    @app.route("/ri/onr/certidoes/<int:pedido_id>/finalizar", methods=["POST"])
    @roles_required(*QUEM)
    def onr_certidao_finalizar(pedido_id: int):
        social = request.form.get("interesse_social") == "1"
        try:
            with db.connect() as con:
                p = OC.conferir_finalizacao(con, pedido_id)
            sessao().finalizar_certidao(p["protocolo"], interesse_social=social)
        except RECUSAS as erro:
            flash(str(erro), "danger")
            return _voltar(pedido_id)
        with db.transaction() as con:
            OC.registrar_finalizacao(con, pedido_id, social, usuario_nome(), agora())
        audit("ONR_CERTIDAO_FINALIZADA", "onr_cert_pedidos", pedido_id,
              {"interesse_social": social})
        flash("Pedido finalizado no ONR: o solicitante já recebe a certidão.", "ok")
        return _voltar(pedido_id)

    @app.route("/ri/onr/certidoes/<int:pedido_id>/devolver", methods=["POST"])
    @roles_required(*QUEM)
    def onr_certidao_devolver(pedido_id: int):
        motivo = (request.form.get("motivo") or "").strip()
        try:
            with db.connect() as con:
                p = OC.conferir_devolucao(con, pedido_id, motivo)
            sessao().devolver_certidao(p["protocolo"], motivo)
        except RECUSAS as erro:
            flash(str(erro), "danger")
            return _voltar(pedido_id)
        with db.transaction() as con:
            OC.registrar_devolucao(con, pedido_id, motivo, usuario_nome(), agora())
        audit("ONR_CERTIDAO_DEVOLVIDA", "onr_cert_pedidos", pedido_id, {"motivo": motivo})
        flash("Pedido devolvido no ONR, com o motivo.", "ok")
        return _voltar(pedido_id)
