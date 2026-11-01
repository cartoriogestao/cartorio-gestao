"""As telas do Serviço de Pendências do e-Protocolo: a fila, a ficha e o cumprimento.

A TELA SÓ OFERECE; quem recusa é `eprotocolo.py`. Ver e levar ao rascunho são de quem
atende. Cumprir, dispensar e trazer a fila à mão são do oficial e do gerente: o
cumprimento altera o protocolo na Central, com o token do cartorário.

**A FILA VAZIA DIZ POR QUÊ.** Sem a faixa do ambiente e da credencial, lista vazia faz
achar que não há trabalho quando o que há é falta de senha.

**OS ANEXOS PASSAM, E NÃO FICAM.** Buscam-se na Central a cada abertura, e só os que o
detalhe do protocolo declara: o número do anexo vem da URL, e a rota não pode virar
porta para baixar arquivo de outro protocolo.
"""
from __future__ import annotations

import re

from flask import Response, flash, redirect, render_template, request, url_for

import centrais_cred as CRED
import eprotocolo as EP
import eprotocolo_api as API
from seguranca_web import MAIOR_INTEGER, numero_digitado

QUEM_VE = ("ADMIN", "MANAGER", "USER")
QUEM_RESPONDE = ("ADMIN", "MANAGER")
RECUSAS_DO_BALCAO = (EP.EProtocoloRegra, API.EProtocoloError, CRED.CredencialError)
TELA_DA_ESPECIE = {"NASCIMENTO": "nascimento", "OBITO": "obito"}
TETO_DO_RECIBO = 15 * 1024 * 1024


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    """Pendura as telas do e-Protocolo no app já construído."""

    usuario_nome = app.extensions["usuario_nome"]

    def agora() -> str:
        return db.now()

    def _ambiente() -> str:
        return EP.ambiente_em_uso(db.get_setting)

    def _cns() -> str:
        return str(db.get_setting("serventia_cns", "") or "").strip() \
            or str(db.get_setting("ri_cns", "") or "").strip()

    def _sessao() -> API.Sessao:
        return API.Sessao(_ambiente())

    @app.route("/rcpn/eprotocolo")
    @roles_required(*QUEM_VE)
    def rcpn_eprotocolo():
        """A lista: o que espera a casa vem primeiro. SÓ LÊ."""
        ambiente = _ambiente()
        with db.connect() as con:
            protocolos = EP.lista(con, ambiente)
            conta = EP.contar(con, ambiente)
        return render_template(
            "rcpn_eprotocolo.html", protocolos=protocolos, conta=conta, ambiente=ambiente,
            tem_credencial=CRED.tem(CRED.EPROTOCOLO, ambiente),
            ambientes=(API.HOMOLOGACAO, API.PRODUCAO), fmt_date=fmt_date)

    @app.route("/rcpn/eprotocolo/ambiente", methods=["POST"])
    @roles_required("ADMIN")
    def rcpn_eprotocolo_ambiente():
        """Homologação ou produção. A casa fica numa só; a outra guarda o que trouxe."""
        escolhido = (request.form.get("ambiente") or "").strip().upper()
        if escolhido not in (API.HOMOLOGACAO, API.PRODUCAO):
            flash("Escolha homologação ou produção.", "danger")
        else:
            db.set_settings({EP.CHAVE_DO_AMBIENTE: escolhido})
            audit("EPROTOCOLO_AMBIENTE", "settings", None, {"ambiente": escolhido})
            flash(f"O e-Protocolo agora fala com {escolhido.lower()}.", "ok")
        return redirect(url_for("rcpn_eprotocolo"))

    @app.route("/rcpn/eprotocolo/testar", methods=["POST"])
    @roles_required(*QUEM_RESPONDE)
    def rcpn_eprotocolo_testar():
        """Confere se o usuário e a senha autenticam. Não mexe na fila."""
        try:
            valeu = _sessao().conferir()
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            flash("O e-Protocolo aceitou a credencial." if valeu
                  else "O e-Protocolo autenticou, mas não validou o token.",
                  "ok" if valeu else "warning")
        return redirect(url_for("rcpn_eprotocolo"))

    @app.route("/rcpn/eprotocolo/trazer", methods=["POST"])
    @roles_required(*QUEM_RESPONDE)
    def rcpn_eprotocolo_trazer():
        """Traz a fila agora, sem esperar o robô. Mesmas funções da rodada."""
        ambiente = _ambiente()
        try:
            sessao = API.Sessao(ambiente)
            fila = EP.esvaziar_a_fila(db, sessao, ambiente, agora=agora())
            with db.connect() as con:
                pendentes = EP.a_consultar(con, ambiente, limite=30)
            for p in pendentes:
                EP.consultar(db, sessao, p["id"], agora=agora())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            audit("EPROTOCOLO_FILA_TRAZIDA", "ep_notificacoes", None,
                  {"novas": fila["novas"], "ambiente": ambiente})
            flash(f"{fila['novas']} notificação(ões) nova(s); {len(pendentes)} protocolo(s) "
                  "consultado(s).", "ok")
        return redirect(url_for("rcpn_eprotocolo"))

    def _protocolo_da_casa(protocolo_id: int):
        with db.connect() as con:
            p = EP.um(con, protocolo_id)
        return p if p and p["ambiente"] == _ambiente() else None

    @app.route("/rcpn/eprotocolo/<int:protocolo_id>")
    @roles_required(*QUEM_VE)
    def rcpn_eprotocolo_ficha(protocolo_id: int):
        """A ficha do protocolo. SÓ LÊ, e por isso o histórico da Central é por botão."""
        p = _protocolo_da_casa(protocolo_id)
        if p is None:
            flash("Esse protocolo não existe neste ambiente.", "danger")
            return redirect(url_for("rcpn_eprotocolo"))
        with db.connect() as con:
            eventos = EP.eventos_do_protocolo(con, p["ambiente"], p["hash"])
            titulares = EP.titulares_do_assento(con, p["assento_id"])
        previa, avisos, erro_previa = None, [], ""
        if p["estruturado"]:
            try:
                previa, avisos = EP.montar_registro(p["estruturado"], cns_da_casa=_cns())
            except EP.EProtocoloRegra as recusa:
                erro_previa = str(recusa)
        historico = None
        if request.args.get("historico") == "1":
            try:
                historico = _sessao().historico(p["hash"])
            except RECUSAS_DO_BALCAO as erro:
                flash(str(erro), "danger")
        return render_template(
            "rcpn_eprotocolo_ficha.html", p=p, d=p["detalhe"] or {}, eventos=eventos,
            previa=previa, avisos=avisos, erro_previa=erro_previa, titulares=titulares,
            historico=historico, cns=_cns(), nome_de_quem=usuario_nome(),
            fmt_date=fmt_date, TELA_DA_ESPECIE=TELA_DA_ESPECIE)

    @app.route("/rcpn/eprotocolo/<int:protocolo_id>/consultar", methods=["POST"])
    @roles_required(*QUEM_VE)
    def rcpn_eprotocolo_consultar(protocolo_id: int):
        """Atualiza o detalhe agora. Só lê na Central."""
        if _protocolo_da_casa(protocolo_id) is None:
            flash("Esse protocolo não existe neste ambiente.", "danger")
            return redirect(url_for("rcpn_eprotocolo"))
        try:
            EP.consultar(db, _sessao(), protocolo_id, agora=agora())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            flash("Protocolo atualizado.", "ok")
        return redirect(url_for("rcpn_eprotocolo_ficha", protocolo_id=protocolo_id))

    @app.route("/rcpn/eprotocolo/<int:protocolo_id>/anexo/<int:anexo_id>")
    @roles_required(*QUEM_VE)
    def rcpn_eprotocolo_anexo(protocolo_id: int, anexo_id: int):
        """Um anexo, direto da Central. Só os que este protocolo declara."""
        p = _protocolo_da_casa(protocolo_id)
        anexos = ((p or {}).get("detalhe") or {}).get("attachments") or []
        item = next((a for a in anexos if str(a.get("id")) == str(anexo_id)), None)
        if item is None:
            flash("Esse anexo não é deste protocolo.", "danger")
            return redirect(url_for("rcpn_eprotocolo"))
        try:
            arquivo = _sessao().anexo(anexo_id)
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_eprotocolo_ficha", protocolo_id=protocolo_id))
        audit("EPROTOCOLO_ANEXO_ABERTO", "ep_protocolos", protocolo_id, {"anexo": anexo_id})
        # O NOME VEM DE FORA: só o que não quebra o cabeçalho.
        nome = re.sub(r"[^\w.-]", "_", f"{item.get('name') or 'anexo'}.{item.get('extension') or 'bin'}")
        return Response(arquivo["bytes"], mimetype="application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="{nome}"',
                                 "X-Content-Type-Options": "nosniff"})

    @app.route("/rcpn/eprotocolo/<int:protocolo_id>/rascunho", methods=["POST"])
    @roles_required(*QUEM_VE)
    def rcpn_eprotocolo_rascunho(protocolo_id: int):
        """O arquivo estruturado vira rascunho do assento. Não lavra nada."""
        if _protocolo_da_casa(protocolo_id) is None:
            flash("Esse protocolo não existe neste ambiente.", "danger")
            return redirect(url_for("rcpn_eprotocolo"))
        try:
            with db.transaction() as con:
                feito = EP.para_rascunho(con, protocolo_id, cns_da_casa=_cns(), agora=agora(),
                                         por=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_eprotocolo_ficha", protocolo_id=protocolo_id))
        audit("EPROTOCOLO_PARA_RASCUNHO", "ep_protocolos", protocolo_id,
              {"rascunho_id": feito["rascunho_id"]})
        flash("Os campos foram preenchidos pelo arquivo do e-Protocolo. Confira cada um com os "
              "documentos anexados antes de lavrar.", "warning")
        return redirect(url_for("rcpn_assento_novo", especie_url=TELA_DA_ESPECIE[feito["especie"]],
                                rascunho_id=feito["rascunho_id"]))

    @app.route("/rcpn/eprotocolo/<int:protocolo_id>/assento", methods=["POST"])
    @roles_required(*QUEM_RESPONDE)
    def rcpn_eprotocolo_assento(protocolo_id: int):
        """Liga o assento já lavrado ao protocolo. Não lavra nada."""
        assento_id = numero_digitado(request.form.get("assento_id"), maximo=MAIOR_INTEGER)
        if not assento_id:
            flash("Informe o número interno do assento lavrado.", "danger")
            return redirect(url_for("rcpn_eprotocolo_ficha", protocolo_id=protocolo_id))
        try:
            with db.transaction() as con:
                EP.ligar_assento(con, protocolo_id, assento_id, agora=agora(), por=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            audit("EPROTOCOLO_ASSENTO_LIGADO", "ep_protocolos", protocolo_id, {"assento": assento_id})
            flash("Assento ligado ao protocolo.", "ok")
        return redirect(url_for("rcpn_eprotocolo_ficha", protocolo_id=protocolo_id))

    @app.route("/rcpn/eprotocolo/<int:protocolo_id>/dispensar", methods=["POST"])
    @roles_required(*QUEM_RESPONDE)
    def rcpn_eprotocolo_dispensar(protocolo_id: int):
        """Tira da lista da casa, com motivo. Na Central nada muda."""
        try:
            with db.transaction() as con:
                EP.dispensar(con, protocolo_id, motivo=request.form.get("motivo") or "",
                             agora=agora(), por=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            audit("EPROTOCOLO_DISPENSADO", "ep_protocolos", protocolo_id, {})
            flash("Protocolo dispensado da lista da casa. Na Central ele continua como está.", "ok")
        return redirect(url_for("rcpn_eprotocolo_ficha", protocolo_id=protocolo_id))

    @app.route("/rcpn/eprotocolo/<int:protocolo_id>/cumprir", methods=["POST"])
    @roles_required(*QUEM_RESPONDE)
    def rcpn_eprotocolo_cumprir(protocolo_id: int):
        """Cumpre na Central. ESCREVE LÁ. O token do IdRC passa e não se guarda."""
        if _protocolo_da_casa(protocolo_id) is None:
            flash("Esse protocolo não existe neste ambiente.", "danger")
            return redirect(url_for("rcpn_eprotocolo"))
        certidao = {"type": (request.form.get("tipo_certidao") or "").strip()}
        link = (request.form.get("link_certidao") or "").strip()
        if link:
            certidao["url"] = link
        responsavel = {"cpf": request.form.get("cpf"), "cns": _cns(),
                       "name": request.form.get("nome"), "email": request.form.get("email")}
        recibo = None
        enviado = request.files.get("recibo")
        if enviado and enviado.filename:
            dados = enviado.read(TETO_DO_RECIBO + 1)
            if len(dados) > TETO_DO_RECIBO:
                flash("O recibo passa de 15 MB.", "danger")
                return redirect(url_for("rcpn_eprotocolo_ficha", protocolo_id=protocolo_id))
            recibo = {"nome": enviado.filename, "bytes": dados}
        try:
            feito = EP.cumprir(db, _sessao(), protocolo_id, certidao=certidao,
                               responsavel=responsavel, recibo=recibo, agora=agora(),
                               por=usuario_nome(),
                               token_idrc=request.form.get("token_idrc") or "")
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            audit("EPROTOCOLO_CUMPRIDO", "ep_protocolos", protocolo_id,
                  {"tipo": certidao["type"], "ja_estava": feito["ja_estava"]})
            flash("O protocolo já estava cumprido na Central; a casa só anotou." if feito["ja_estava"]
                  else "Cumprimento registrado no e-Protocolo.", "ok")
        return redirect(url_for("rcpn_eprotocolo_ficha", protocolo_id=protocolo_id))
