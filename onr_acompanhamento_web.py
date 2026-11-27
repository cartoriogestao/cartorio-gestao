"""A tela do andamento dos títulos do RI no Acompanhamento de Títulos do ONR.

    Pedido de 26/10/2026 — ver o cabeçalho de `onr_acompanhamento`.

O QUE ELA FAZ
    Mostra a fila (o que espera subir, com o motivo de quem espera), o que já
    subiu e o que foi anulado ou descartado; e tem três botões:

    - **Enviar pendentes** (ADMIN e MANAGER): manda a fila ao ONR. Só com o
      envio LIGADO — sem isso, recusa e diz onde ligar.
    - **Ligar / desligar o envio** (ADMIN): a chave `onr_acompanhamento_ligado`.
      Desligado de fábrica: andamento na Central é publicidade, e quem decide
      quando começa é quem responde pela serventia.
    - **Descartar** um pendente, com motivo (ADMIN): o que não deve ir.

O ENCAIXE NA AUTOMAÇÃO (A008, 26/11/2026)
    O processo `RI_ONR_ACOMPANHAMENTO` da central chama `ACOMP.enviar_pendentes`
    por dentro — a mesma função deste botão —, e a chave
    `onr_acompanhamento_ligado` continua sendo a trava. O que a A008 pôs nesta
    tela, todo auditado:

    - **Liberar os atrasados** (ADMIN), em lote ou por título: o que estava na
      fila quando a rotina começou a mandar só sai depois disto.
    - **Marcar a exigência como revisada** (ADMIN e MANAGER): o texto inteiro
      só sobe revisado. A bloqueada (sem exigência no texto, rascunho) não se
      marca: corrige-se a nota.
    - **Chamada de prova de 1 título** (ADMIN): escolhe o protocolo, vê os
      campos e o envelope que vão subir, digita o número e confirma. É UM
      evento, e o ONR avisa o apresentante de verdade.
    - **As duas opções que o titular ainda não decidiu** (ADMIN): o texto curto
      da exigência e o evento retroativo de prenotação. Nascem desligadas.

A REDE ACONTECE FORA DE `db.transaction()` — `enviar_pendentes` abre as suas
transações curtas DEPOIS de cada resposta do ONR.
"""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for

import onr_acompanhamento as ACOMP
import onr_wsoficio as WS
from bd_nativo import banco
from seguranca_web import numero_digitado


def registrar_rotas(app, db, login_required, roles_required, audit):
    usuario_nome = app.extensions["usuario_nome"]

    with db.connect() as con:
        ACOMP.init_schema(con)

    def _amb() -> str:
        return ACOMP.ambiente(db.get_setting)

    @app.route("/ri/onr/acompanhamento")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def onr_acompanhamento():
        todos = request.args.get("todos") == "1"
        amb = _amb()
        with db.connect() as con:
            dados = ACOMP.painel(con, todos=todos, amb=amb)
        # 26/10/2026 — decisão do oficial: produção de fábrica. A tela diz o
        # ambiente E o endereço para onde o clique vai, porque «ligar» em
        # produção é publicar ao apresentante de verdade.
        return render_template("onr_acompanhamento.html", todos=todos,
                               ambiente=amb, producao=(amb == WS.PRODUCAO),
                               endereco=WS.BASE[amb],
                               de_fabrica=(amb == ACOMP.AMBIENTE_DE_FABRICA),
                               nota_sem_anexo=ACOMP.NOTA_SEM_ANEXO,
                               ligado=ACOMP.ligado(db.get_setting),
                               credencial=WS.situacao(amb), **dados)

    @app.route("/ri/onr/acompanhamento/enviar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def onr_acompanhamento_enviar():
        if not ACOMP.ligado(db.get_setting):
            flash("O envio do andamento ao ONR está desligado. Quem liga é o oficial, "
                  "nesta mesma tela — nada foi enviado.", "danger")
            return redirect(url_for("onr_acompanhamento"))
        amb = _amb()
        try:
            feito = ACOMP.enviar_pendentes(
                db, lambda: WS.Sessao(ambiente=amb), amb=amb,
                quem=(usuario_nome() or "").strip() or "?", agora=db.now)
        except (ACOMP.AcompanhamentoError, WS.WSOficioError) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("onr_acompanhamento"))
        audit("ONR_ACOMPANHAMENTO_ENVIADO", "onr_at_eventos", None,
              dict({k: v for k, v in feito.items() if k != "recusas"}, ambiente=amb,
                   recusas=len(feito["recusas"])))
        frase = (f"ONR ({amb.lower()}): {feito['enviados']} andamento(s) enviado(s), "
                 f"{feito['titulos_novos']} título(s) cadastrado(s), "
                 f"{feito['esperando']} esperando, {feito['recusados']} recusado(s), "
                 f"{feito['anulados']} anulado(s)"
                 + (f", {feito['atrasados']} atrasado(s) aguardando a liberação"
                    if feito["atrasados"] else "") + ".")
        if feito["parou"]:
            flash(frase + f" A rodada parou: {feito['parou']}", "danger")
        else:
            flash(frase, "ok" if not feito["recusados"] else "warning")
        return redirect(url_for("onr_acompanhamento"))

    @app.route("/ri/onr/acompanhamento/ligar", methods=["POST"])
    @roles_required("ADMIN")
    def onr_acompanhamento_ligar():
        valor = "1" if request.form.get("ligar") == "1" else "0"
        db.set_settings({ACOMP.CHAVE_LIGADO: valor})
        audit("ONR_ACOMPANHAMENTO_LIGADO" if valor == "1" else "ONR_ACOMPANHAMENTO_DESLIGADO",
              "settings", None, {"ambiente": _amb()})
        flash(f"Envio do andamento ao ONR LIGADO, no ambiente de "
              f"{'PRODUÇÃO — o apresentante passa a ver o andamento na Central' if _amb() == WS.PRODUCAO else _amb().lower()}."
              if valor == "1" else
              "Envio do andamento ao ONR desligado. A fila continua se anotando.", "ok")
        return redirect(url_for("onr_acompanhamento"))

    @app.route("/ri/onr/acompanhamento/<int:evento_id>/descartar", methods=["POST"])
    @roles_required("ADMIN")
    def onr_acompanhamento_descartar(evento_id: int):
        motivo = (request.form.get("motivo") or "").strip()
        try:
            with db.transaction() as con:
                ev = ACOMP.descartar(con, evento_id, motivo=motivo,
                                     quem=(usuario_nome() or "").strip(), agora=db.now())
        except ACOMP.AcompanhamentoError as erro:
            flash(str(erro), "danger")
        else:
            audit("ONR_ACOMPANHAMENTO_DESCARTADO", "RI_PROTOCOLO", ev["protocolo_id"],
                  {"evento": ev["chave"], "motivo": motivo})
            flash("Andamento descartado: não vai ao ONR.", "ok")
        volta = numero_digitado(request.form.get("protocolo_id"))
        if volta is not None:
            return redirect(url_for("ri_protocolo_ver", protocolo_id=volta))
        return redirect(url_for("onr_acompanhamento"))

    # ------------------------------------------------- A008, 26/11/2026

    def _quem() -> str:
        return (usuario_nome() or "").strip()

    @app.route("/ri/onr/acompanhamento/liberar", methods=["POST"])
    @roles_required("ADMIN")
    def onr_acompanhamento_liberar():
        """Libera os ATRASADOS — todos (`todos=1`) ou os de um título."""
        pid = numero_digitado(request.form.get("protocolo_id"))
        if pid is None and request.form.get("todos") != "1":
            flash("Diga se libera todos os atrasados ou os de um título. Nada foi liberado.",
                  "danger")
            return redirect(url_for("onr_acompanhamento"))
        with db.transaction() as con:
            n = ACOMP.liberar_atrasados(con, quem=_quem(), agora=db.now(), protocolo_id=pid)
        audit("ONR_ACOMPANHAMENTO_ATRASADOS_LIBERADOS", "RI_PROTOCOLO" if pid else "onr_at_eventos",
              pid, {"liberados": n, "todos": pid is None})
        flash(f"{n} andamento(s) atrasado(s) liberado(s). A rotina os leva na próxima rodada, "
              "com as outras travas (exigência revisada, cadastro, selo)." if n else
              "Nenhum atrasado a liberar.", "ok" if n else "warning")
        volta = numero_digitado(request.form.get("voltar_ficha"))
        if volta is not None:
            return redirect(url_for("ri_protocolo_ver", protocolo_id=volta))
        return redirect(url_for("onr_acompanhamento"))

    @app.route("/ri/onr/acompanhamento/<int:evento_id>/revisar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def onr_acompanhamento_revisar(evento_id: int):
        """«Revisada por … em …»: a exigência de texto inteiro pode subir."""
        try:
            with db.transaction() as con:
                ev = ACOMP.marcar_revisada(con, evento_id, quem=_quem(), agora=db.now())
        except ACOMP.AcompanhamentoError as erro:
            flash(str(erro), "danger")
        else:
            audit("ONR_ACOMPANHAMENTO_EXIGENCIA_REVISADA", "RI_PROTOCOLO", ev["protocolo_id"],
                  {"evento": ev["chave"]})
            flash("Exigência marcada como revisada: o texto inteiro sobe na próxima rodada.", "ok")
        volta = numero_digitado(request.form.get("protocolo_id"))
        if volta is not None:
            return redirect(url_for("ri_protocolo_ver", protocolo_id=volta))
        return redirect(url_for("onr_acompanhamento"))

    @app.route("/ri/onr/acompanhamento/opcao", methods=["POST"])
    @roles_required("ADMIN")
    def onr_acompanhamento_opcao():
        """O texto curto da exigência e o evento retroativo — decisões do titular."""
        chave = (request.form.get("chave") or "").strip()
        ligar = request.form.get("ligar") == "1"
        try:
            with db.transaction() as con:
                ACOMP.opcao(con, chave, ligar)
        except ACOMP.AcompanhamentoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("onr_acompanhamento"))
        audit("ONR_ACOMPANHAMENTO_OPCAO", "settings", None, {"chave": chave, "ligada": ligar})
        flash(f"Opção {'ligada' if ligar else 'desligada'}.", "ok")
        return redirect(url_for("onr_acompanhamento"))

    @app.route("/ri/onr/acompanhamento/<int:protocolo_id>/retroativo", methods=["POST"])
    @roles_required("ADMIN")
    def onr_acompanhamento_retroativo(protocolo_id: int):
        """Anota o «prenotado» do título anterior à fila (só com a opção ligada)."""
        try:
            with db.transaction() as con:
                anotou = ACOMP.anotar_prenotacao_retroativa(con, protocolo_id, agora=db.now())
        except ACOMP.AcompanhamentoError as erro:
            flash(str(erro), "danger")
        else:
            audit("ONR_ACOMPANHAMENTO_PRENOTACAO_RETROATIVA", "RI_PROTOCOLO", protocolo_id,
                  {"anotou": bool(anotou)})
            flash("«Prenotado» retroativo anotado na fila." if anotou
                  else "Não deu para anotar o «prenotado» deste título.", "ok" if anotou else "danger")
        return redirect(url_for("onr_acompanhamento"))

    @app.route("/ri/onr/acompanhamento/prova", methods=["GET", "POST"])
    @roles_required("ADMIN")
    def onr_acompanhamento_prova():
        """A CHAMADA DE PROVA DE 1 TÍTULO. GET mostra exatamente o que sobe;
        POST manda UM evento, com o número do protocolo digitado de novo."""
        amb = _amb()
        if request.method == "POST":
            pid = numero_digitado(request.form.get("protocolo_id"))
            evento_id = numero_digitado(request.form.get("evento_id"))
            if pid is None or evento_id is None:
                flash("Escolha o protocolo e confira o que vai subir antes de confirmar.", "danger")
                return redirect(url_for("onr_acompanhamento_prova"))
            if not ACOMP.ligado(db.get_setting):
                flash("O envio ao ONR está desligado: a prova não sai. Nada foi enviado.", "danger")
                return redirect(url_for("onr_acompanhamento_prova", protocolo_id=pid))
            with db.connect() as con:
                p = ACOMP._protocolo(banco(con), pid)
            digitado = (request.form.get("confirmacao") or "").strip()
            if not p or digitado != str(p.get("numero")):
                flash("Para confirmar, digite o número do protocolo exatamente como na tela. "
                      "Nada foi enviado.", "danger")
                return redirect(url_for("onr_acompanhamento_prova", protocolo_id=pid))
            try:
                feito = ACOMP.enviar_prova(db, lambda: WS.Sessao(ambiente=amb), amb=amb,
                                           quem=_quem() or "?", agora=db.now,
                                           protocolo_id=pid, evento_id=evento_id)
            except (ACOMP.AcompanhamentoError, WS.WSOficioError) as erro:
                flash(str(erro), "danger")
                return redirect(url_for("onr_acompanhamento_prova", protocolo_id=pid))
            audit("ONR_ACOMPANHAMENTO_PROVA", "RI_PROTOCOLO", pid,
                  {"evento_id": evento_id, "ambiente": amb, "enviados": feito["enviados"],
                   "recusados": feito["recusados"], "parou": feito["parou"],
                   "recusas": feito["recusas"]})
            if feito["enviados"]:
                flash(f"Prova enviada ao ONR ({amb.lower()}): 1 andamento. Confira na Central "
                      "antes de liberar o resto.", "ok")
            else:
                flash("A prova não subiu: " + (feito["parou"] or "; ".join(
                    f"código {r['codigo']} — {r['texto']}" for r in feito["recusas"])
                    or "o ONR não aceitou."), "danger")
            return redirect(url_for("onr_acompanhamento_prova", protocolo_id=pid))
        pid = numero_digitado(request.args.get("protocolo_id"))
        previa, erro = None, ""
        with db.connect() as con:
            candidatos = banco(con).ler(
                """SELECT e.protocolo_id, p.numero AS protocolo_numero, COUNT(*) AS pendentes
                     FROM onr_at_eventos e LEFT JOIN ri_protocolos p ON p.id = e.protocolo_id
                    WHERE e.situacao='PENDENTE'
                    GROUP BY e.protocolo_id, p.numero ORDER BY p.numero""")
            if pid is not None:
                try:
                    previa = ACOMP.previa_da_prova(con, pid, amb=amb)
                except ACOMP.AcompanhamentoError as e:
                    erro = str(e)
        return render_template("onr_acompanhamento_prova.html", candidatos=candidatos,
                               protocolo_id=pid, previa=previa, erro=erro, ambiente=amb,
                               producao=(amb == WS.PRODUCAO), endereco=WS.BASE[amb],
                               ligado=ACOMP.ligado(db.get_setting))
