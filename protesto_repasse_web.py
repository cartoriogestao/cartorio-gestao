"""As telas do LG05 — repasse ao apresentante, certidão em relação e o regime.

Lote LG05 (19/10/2026). O domínio mora em `protesto_repasse`,
`protesto_relacao` e `protesto_posteriori`; aqui só o pedido, a resposta, o
papel de quem pede e o rastro em `audit_logs`.

QUEM FAZ O QUÊ
    Ver as pendências, gerar a relação do dia e registrar a entrega é do
    balcão (ADMIN, MANAGER, USER): é quem atende o apresentante e a entidade.
    Mexer no dinheiro — gerar, registrar, pagar e conciliar a guia, registrar
    o repasse direto — é de quem responde pelo caixa (ADMIN, MANAGER).
    Cancelar guia, suspender entidade e ligar o envio externo é do ADMIN: são
    os três que mudam o que a casa diz para fora.

O RASTRO NÃO LEVA DADO DE PESSOA
    O `audit` guarda número, id, valor e situação — e não o nome nem o CPF do
    devedor que vai na relação. A relação inteira já fica no banco, congelada;
    copiá-la no rastro seria espalhar o dado reservado por mais uma tabela.
"""
from __future__ import annotations

from datetime import date, timedelta

from flask import (Response, flash, redirect, render_template, request,
                   url_for)

import protesto_posteriori as POST
import protesto_relacao as REL
import protesto_repasse as REP
from caixa_schema import reais
from seguranca_web import numero_digitado  # LD13: o número que a tela mandou
from serventia import dados as dados_serventia

QUEM_VE = ("ADMIN", "MANAGER", "USER")
QUEM_MEXE_NO_DINHEIRO = ("ADMIN", "MANAGER")
SO_O_ADMIN = ("ADMIN",)

# O que volta como frase, e não como HTTP 500. `ValueError` cobre o valor em
# reais que não se lê (`caixa_schema.centavos`).
RECUSAS = (REP.RepasseError, REL.RelacaoError, POST.PosterioriError, ValueError)


def registrar_rotas(app, db, login_required, roles_required, audit):
    """Pendura as telas do repasse e da relação no app já construído."""

    usuario_nome = app.extensions["usuario_nome"]

    def agora() -> str:
        return db.now()

    def hoje() -> str:
        return agora()[:10]

    def _campo(nome: str) -> str:
        return (request.form.get(nome) or "").strip()

    def _feriados(con):
        return REP.feriados_da_casa(con)

    # ------------------------------------------------------------ o repasse

    @app.route("/protesto/repasses")
    @login_required
    @roles_required(*QUEM_VE)
    def protesto_repasses():
        """As pendências de repasse e as guias. Só LÊ."""
        with db.connect() as con:
            rel = REP.relatorio(con, hoje=hoje(), feriados=_feriados(con))
            guias = REP.guias(con)
        return render_template(
            "protesto_repasses.html", rel=rel, guias=guias, hoje=hoje(),
            formas=REP.FORMAS_DE_REPASSE_DIRETO, reais=reais,
            fundamento=REP.FUNDAMENTO_DO_PRAZO,
            pode_mexer=QUEM_MEXE_NO_DINHEIRO)

    @app.route("/protesto/repasses/pendencias.csv")
    @login_required
    @roles_required(*QUEM_VE)
    def protesto_repasses_csv():
        """O relatório de pendências de repasse, em planilha. Só LÊ.

        Sai o mesmo que a tela mostra, pela mesma função — duas contas para a
        mesma pergunta divergiriam na primeira mudança.
        """
        with db.connect() as con:
            rel = REP.relatorio(con, hoje=hoje(), feriados=_feriados(con))
        linhas = ["CANAL;PROTOCOLO;TITULO;APRESENTANTE;PAGO_EM;PRAZO;"
                  "DIAS_DE_ATRASO;VALOR;VALOR_DE;OBSERVACAO"]
        for p in rel["pendentes"]:
            linhas.append(";".join(str(x) for x in (
                p["canal"], p["protocolo"] or "", p["numero_titulo"] or "",
                p["favorecido"], p["recebido_em"], p["prazo"],
                p["dias_de_atraso"], reais(p["valor_centavos"]), p["valor_de"],
                p["observacao"])))
        corpo = ("\n".join(linhas) + "\n").encode("utf-8-sig")
        return Response(corpo, mimetype="text/csv", headers={
            "Content-Disposition":
                f"attachment; filename=repasses_pendentes_{hoje()}.csv"})

    @app.route("/protesto/repasses/guias", methods=["POST"])
    @login_required
    @roles_required(*QUEM_MEXE_NO_DINHEIRO)
    def protesto_repasse_guia_gerar():
        """Gera a guia do IEPTB com os pagamentos marcados (ou todos). ESCREVE."""
        # O MARCADO COM CARA DE NÚMERO QUE NÃO É PAGAMENTO («²», dígitos
        # demais) recusa a guia inteira, como o pagamento que não está
        # pendente: tirá-lo da lista faria a guia sair com «todos» (LD13).
        brutos = [str(x).strip() for x in request.form.getlist("ato_id")]
        marcados = [numero_digitado(x) for x in brutos if x.isdigit()]
        if None in marcados:
            flash("Um dos pagamentos marcados não é pagamento lançado no "
                  "sistema. Nenhuma guia foi gerada.", "danger")
            return redirect(url_for("protesto_repasses"))
        try:
            with db.transaction() as con:
                g = REP.gerar_guia(con, hoje=hoje(), agora=agora(),
                                   usuario=usuario_nome(),
                                   ato_ids=marcados or None,
                                   feriados=_feriados(con))
        except RECUSAS as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_repasses"))
        audit("PROTESTO_REPASSE_GUIA_GERADA", "pt_repasse_guias", g["guia_id"],
              {"numero": g["numero"], "ano": g["ano"], "titulos": g["titulos"],
               "total_centavos": g["total_centavos"]})
        flash(f"Guia {g['numero']}/{g['ano']} gerada: {g['titulos']} título(s), "
              f"R$ {reais(g['total_centavos'])}. Emita a guia no IEPTB com esta "
              f"relação e registre-a aqui.", "success")
        return redirect(url_for("protesto_repasse_guia", guia_id=g["guia_id"]))

    @app.route("/protesto/repasses/guias/<int:guia_id>")
    @login_required
    @roles_required(*QUEM_VE)
    def protesto_repasse_guia(guia_id: int):
        """A ficha da guia: a relação congelada e os repasses dela. Só LÊ."""
        with db.connect() as con:
            g = REP.guia(con, guia_id)
        if not g:
            flash("Guia não encontrada.", "danger")
            return redirect(url_for("protesto_repasses"))
        return render_template("protesto_repasse_guia.html", g=g, hoje=hoje(),
                               reais=reais, pode_mexer=QUEM_MEXE_NO_DINHEIRO)

    @app.route("/protesto/repasses/guias/<int:guia_id>/relacao.txt")
    @login_required
    @roles_required(*QUEM_VE)
    def protesto_repasse_guia_relacao(guia_id: int):
        """A relação da guia, como foi congelada. Só LÊ."""
        with db.connect() as con:
            g = REP.guia(con, guia_id)
        if not g:
            flash("Guia não encontrada.", "danger")
            return redirect(url_for("protesto_repasses"))
        return Response(g["relacao"].encode("utf-8-sig"), mimetype="text/plain",
                        headers={"Content-Disposition":
                                 f"attachment; filename=guia_ieptb_"
                                 f"{g['numero']}_{g['ano']}.txt"})

    def _passo_da_guia(guia_id: int, acao: str, faz, recado):
        try:
            with db.transaction() as con:
                r = faz(con)
        except RECUSAS as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_repasse_guia", guia_id=guia_id))
        audit(acao, "pt_repasse_guias", guia_id,
              {k: v for k, v in r.items() if k != "guia_id"})
        flash(recado(r), "success")
        return redirect(url_for("protesto_repasse_guia", guia_id=guia_id))

    @app.route("/protesto/repasses/guias/<int:guia_id>/registrar",
               methods=["POST"])
    @login_required
    @roles_required(*QUEM_MEXE_NO_DINHEIRO)
    def protesto_repasse_guia_registrar(guia_id: int):
        """Registra a guia que o IEPTB emitiu. ESCREVE."""
        return _passo_da_guia(
            guia_id, "PROTESTO_REPASSE_GUIA_REGISTRADA",
            lambda con: REP.registrar_guia(
                con, guia_id, identificador=_campo("identificador"),
                vencimento=_campo("vencimento") or None, agora=agora(),
                usuario=usuario_nome()),
            lambda r: f"Guia {r['numero']} registrada: {r['identificador']}.")

    @app.route("/protesto/repasses/guias/<int:guia_id>/pagar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_MEXE_NO_DINHEIRO)
    def protesto_repasse_guia_pagar(guia_id: int):
        """Registra o pagamento da guia — o repasse se cumpre aqui. ESCREVE."""
        return _passo_da_guia(
            guia_id, "PROTESTO_REPASSE_GUIA_PAGA",
            lambda con: REP.pagar_guia(
                con, guia_id, paga_em=_campo("paga_em"),
                comprovante=_campo("comprovante"), agora=agora(),
                usuario=usuario_nome()),
            lambda r: (f"Guia {r['numero']} paga em {r['paga_em']}: "
                       f"R$ {reais(r['total_centavos'])} repassados. Falta "
                       f"conciliar com a confirmação do IEPTB."))

    @app.route("/protesto/repasses/guias/<int:guia_id>/conciliar",
               methods=["POST"])
    @login_required
    @roles_required(*QUEM_MEXE_NO_DINHEIRO)
    def protesto_repasse_guia_conciliar(guia_id: int):
        """Concilia a guia com o valor que o IEPTB confirmou. ESCREVE."""
        return _passo_da_guia(
            guia_id, "PROTESTO_REPASSE_GUIA_CONCILIADA",
            lambda con: REP.conciliar_guia(
                con, guia_id, valor_confirmado=_campo("valor_confirmado"),
                referencia=_campo("referencia"), agora=agora(),
                usuario=usuario_nome()),
            lambda r: f"Guia {r['numero']} conciliada.")

    @app.route("/protesto/repasses/guias/<int:guia_id>/cancelar",
               methods=["POST"])
    @login_required
    @roles_required(*SO_O_ADMIN)
    def protesto_repasse_guia_cancelar(guia_id: int):
        """Cancela a guia não paga; os pagamentos voltam à pendência. ESCREVE."""
        return _passo_da_guia(
            guia_id, "PROTESTO_REPASSE_GUIA_CANCELADA",
            lambda con: REP.cancelar_guia(
                con, guia_id, motivo=_campo("motivo"), agora=agora(),
                usuario=usuario_nome()),
            lambda r: (f"Guia {r['numero']} cancelada: os {r['titulos']} "
                       f"pagamento(s) voltaram à pendência."))

    @app.route("/protesto/repasses/direto", methods=["POST"])
    @login_required
    @roles_required(*QUEM_MEXE_NO_DINHEIRO)
    def protesto_repasse_direto():
        """Registra o repasse direto ao apresentante do título do balcão. ESCREVE."""
        ato = _campo("ato_id")
        try:
            if not ato.isdigit():
                raise REP.RepasseError("Escolha o pagamento a repassar.")
            with db.transaction() as con:
                r = REP.registrar_direto(
                    con, int(ato), forma=_campo("forma"),
                    comprovante=_campo("comprovante"),
                    repassado_em=_campo("repassado_em") or hoje(), hoje=hoje(),
                    agora=agora(), favorecido=_campo("favorecido") or None,
                    usuario=usuario_nome(), feriados=_feriados(con))
        except RECUSAS as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_repasses"))
        audit("PROTESTO_REPASSE_DIRETO", "pt_repasses", r["repasse_id"],
              {"ato_id": r["ato_id"], "titulo_id": r["titulo_id"],
               "valor_centavos": r["valor_centavos"], "forma": r["forma"],
               "no_prazo": r["no_prazo"]})
        flash(f"Repasse de R$ {reais(r['valor_centavos'])} registrado"
              + ("." if r["no_prazo"] else
                 " — FORA do prazo do primeiro dia útil."),
              "success" if r["no_prazo"] else "warning")
        return redirect(url_for("protesto_repasses"))

    # ------------------------------------------------- a certidão em relação

    @app.route("/protesto/relacao-diaria")
    @login_required
    @roles_required(*QUEM_VE)
    def protesto_relacao_diaria():
        """As entidades, o que falta gerar e entregar, e as últimas. Só LÊ."""
        with db.connect() as con:
            dados = {
                "entidades": REL.entidades(con),
                "a_entregar": REL.a_entregar(con),
                "faltam": REL.dias_sem_relacao(con, hoje=hoje(),
                                               feriados=_feriados(con)),
                "relacoes": REL.relacoes(con),
                "modo": REL.modo_de_envio(con),
            }
        ontem = (date.fromisoformat(hoje()) - timedelta(days=1)).isoformat()
        return render_template(
            "protesto_relacao_diaria.html", d=dados, hoje=hoje(), ontem=ontem,
            canais=REL.CANAIS, formas=REL.FORMAS_DE_ENTREGA,
            modos=REL.MODOS_DE_ENVIO, aviso=REL.AVISO_DE_RESERVA,
            fundamento=REL.FUNDAMENTO, quem_envia=QUEM_MEXE_NO_DINHEIRO)

    def _voltar_a_relacao():
        return redirect(url_for("protesto_relacao_diaria"))

    @app.route("/protesto/relacao-diaria/entidades", methods=["POST"])
    @login_required
    @roles_required(*QUEM_MEXE_NO_DINHEIRO)
    def protesto_relacao_entidade_habilitar():
        """Cadastra a entidade habilitada (CN-MA art. 949, § 1º). ESCREVE."""
        try:
            with db.transaction() as con:
                eid = REL.habilitar_entidade(
                    con, nome=_campo("nome"), documento=_campo("documento"),
                    canal=_campo("canal"), habilitacao=_campo("habilitacao"),
                    habilitada_em=_campo("habilitada_em"), agora=agora(),
                    contato=_campo("contato") or None, usuario=usuario_nome())
        except RECUSAS as erro:
            flash(str(erro), "danger")
            return _voltar_a_relacao()
        audit("PROTESTO_RELACAO_ENTIDADE_HABILITADA", "pt_relacao_entidades",
              eid, {"canal": _campo("canal").upper()})
        flash("Entidade habilitada.", "success")
        return _voltar_a_relacao()

    @app.route("/protesto/relacao-diaria/entidades/<int:entidade_id>/suspender",
               methods=["POST"])
    @login_required
    @roles_required(*SO_O_ADMIN)
    def protesto_relacao_entidade_suspender(entidade_id: int):
        """Suspende o fornecimento à entidade (§ 3º). ESCREVE."""
        try:
            with db.transaction() as con:
                r = REL.suspender_entidade(con, entidade_id,
                                           motivo=_campo("motivo"),
                                           agora=agora(), usuario=usuario_nome())
        except RECUSAS as erro:
            flash(str(erro), "danger")
            return _voltar_a_relacao()
        audit("PROTESTO_RELACAO_ENTIDADE_SUSPENSA", "pt_relacao_entidades",
              entidade_id, {"motivo": _campo("motivo")})
        flash(f"Fornecimento à {r['nome']} suspenso. O § 3º manda comunicar o "
              f"fato ao juiz corregedor permanente.", "warning")
        return _voltar_a_relacao()

    @app.route("/protesto/relacao-diaria/gerar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_VE)
    def protesto_relacao_gerar():
        """Gera a relação do dia para a entidade (ou devolve a que já há)."""
        try:
            entidade = _campo("entidade_id")
            if not entidade.isdigit():
                raise REL.RelacaoError("Escolha a entidade.")
            with db.transaction() as con:
                r = REL.gerar_relacao(
                    con, dia=_campo("dia"), entidade_id=int(entidade),
                    hoje=hoje(), agora=agora(),
                    sv=dados_serventia(db.get_settings), usuario=usuario_nome())
        except RECUSAS as erro:
            flash(str(erro), "danger")
            return _voltar_a_relacao()
        if r["ja_existia"]:
            flash(f"A relação {r['numero']}/{r['ano']} deste dia já existia — "
                  f"é a mesma, com o mesmo teor.", "info")
            return _voltar_a_relacao()
        audit("PROTESTO_RELACAO_GERADA", "pt_relacoes_diarias", r["relacao_id"],
              {"dia": r["dia"], "entidade_id": int(entidade),
               "registros": r["registros"], "negativa": r["negativa"]})
        flash(f"Relação {r['numero']}/{r['ano']} gerada: "
              + ("certidão negativa." if r["negativa"]
                 else f"{r['registros']} registro(s)."), "success")
        return _voltar_a_relacao()

    @app.route("/protesto/relacao-diaria/<int:relacao_id>/arquivo")
    @login_required
    @roles_required(*QUEM_VE)
    def protesto_relacao_arquivo(relacao_id: int):
        """O arquivo da relação, como congelou. Só LÊ."""
        with db.connect() as con:
            r = REL.relacao(con, relacao_id)
        if not r:
            flash("Relação não encontrada.", "danger")
            return _voltar_a_relacao()
        return Response(str(r["teor"]).encode("utf-8-sig"), mimetype="text/plain",
                        headers={"Content-Disposition":
                                 f"attachment; filename=relacao_{r['dia']}_"
                                 f"{r['entidade_documento']}.txt"})

    @app.route("/protesto/relacao-diaria/<int:relacao_id>/entregar",
               methods=["POST"])
    @login_required
    @roles_required(*QUEM_VE)
    def protesto_relacao_entregar(relacao_id: int):
        """Registra a entrega à entidade, com o comprovante. ESCREVE."""
        try:
            with db.transaction() as con:
                r = REL.registrar_entrega(
                    con, relacao_id, forma=_campo("forma"),
                    comprovante=_campo("comprovante"),
                    entregue_em=_campo("entregue_em") or hoje(), agora=agora(),
                    usuario=usuario_nome())
        except RECUSAS as erro:
            flash(str(erro), "danger")
            return _voltar_a_relacao()
        audit("PROTESTO_RELACAO_ENTREGUE", "pt_relacoes_diarias", relacao_id,
              {"forma": r["forma"]})
        flash(f"Entrega da relação {r['numero']} registrada.", "success")
        return _voltar_a_relacao()

    @app.route("/protesto/relacao-diaria/<int:relacao_id>/enviar",
               methods=["POST"])
    @login_required
    @roles_required(*QUEM_MEXE_NO_DINHEIRO)
    def protesto_relacao_enviar(relacao_id: int):
        """Manda pela CENPROT, se o envio estiver ligado. FALA COM A REDE.

        O transporte vem de `app.config["PROTESTO_RELACAO_TRANSPORTE"]` quando
        o teste o põe ali — o serviço falso, sem rede; senão é o de verdade,
        que hoje recusa (ver `protesto_relacao.TransporteCenprot`).
        """
        transporte = (app.config.get("PROTESTO_RELACAO_TRANSPORTE")
                      or REL.TransporteCenprot())
        try:
            with db.transaction() as con:
                r = REL.enviar(con, relacao_id, transporte=transporte,
                               agora=agora(), usuario=usuario_nome())
        except RECUSAS as erro:
            audit("PROTESTO_RELACAO_ENVIO_RECUSADO", "pt_relacoes_diarias",
                  relacao_id, {"motivo": str(erro)})
            flash(str(erro), "danger")
            return _voltar_a_relacao()
        audit("PROTESTO_RELACAO_ENVIADA", "pt_relacoes_diarias", relacao_id,
              {"ambiente": r["ambiente"], "entregue": r["entregue"],
               "protocolo": r["protocolo"]})
        flash(f"Relação enviada ({r['ambiente'].lower()}), protocolo "
              f"{r['protocolo'] or '—'}."
              + ("" if r["entregue"] else
                 " Homologação não conta como entrega."), "success")
        return _voltar_a_relacao()

    @app.route("/protesto/relacao-diaria/configuracao", methods=["POST"])
    @login_required
    @roles_required(*SO_O_ADMIN)
    def protesto_relacao_configuracao():
        """Liga, põe em homologação ou desliga o envio pela CENPROT. ESCREVE só
        esta chave — formulário próprio, como `configuracoes_cra_envio`, para
        o «salvar» de outra tela não gravar por cima."""
        modo = _campo("modo").upper()
        if modo not in REL.MODOS_DE_ENVIO:
            flash(f"Modo desconhecido: {modo or '(vazio)'}.", "danger")
            return _voltar_a_relacao()
        db.set_settings({REL.CHAVE_DO_ENVIO: modo})
        audit("SETTINGS_CHANGED", "SETTINGS", None, {REL.CHAVE_DO_ENVIO: modo})
        flash(f"Envio da relação pela CENPROT: {modo.lower()}.", "success")
        return _voltar_a_relacao()

    # ------------------------------------------- o regime dos emolumentos

    @app.route("/protesto/<int:titulo_id>/regime-emolumentos", methods=["POST"])
    @login_required
    @roles_required(*QUEM_MEXE_NO_DINHEIRO)
    def protesto_regime_emolumentos(titulo_id: int):
        """O balcão decide o regime dos emolumentos, antes do primeiro ato."""
        try:
            with db.transaction() as con:
                r = POST.definir_regime(con, titulo_id, _campo("regime") or None,
                                        motivo=_campo("motivo"))
        except RECUSAS as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_titulo", titulo_id=titulo_id))
        audit("PROTESTO_REGIME_EMOLUMENTOS", "pt_titulos", titulo_id,
              {"regime": r["regime"] or "pela regra", "motivo": r["motivo"]})
        flash("Regime dos emolumentos: "
              + (r["regime"].lower() if r["regime"] else "pela regra") + ".",
              "success")
        return redirect(url_for("protesto_titulo", titulo_id=titulo_id))
