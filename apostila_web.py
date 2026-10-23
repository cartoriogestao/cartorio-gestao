"""AS TELAS DA APOSTILA DE HAIA — Administrativo → Apostila de Haia (LG03).

QUEM FAZ O QUÊ
    - ver os pedidos, o controle e a certidão: todos, inclusive o AUDITOR, que
      confere e não pratica ato;
    - registrar pedido, documento, emissão, selo e recusa: o balcão;
    - CANCELAR apostila emitida: só o oficial e o gerente — é desfazer ato
      que já ocupa número no controle;
    - ligar o módulo e escolher o serviço da tabela: só o oficial.

A GUARDA DO ALCANCE É AQUI, NA ROTA, e não no menu. A regra é a do
`modulos_ligados` (de fábrica, `NINGUEM`). A tela de configuração fica FORA da
guarda, de propósito: com o módulo fechado é por ela que o oficial o abre — a
mesma razão de `NINGUEM` não trancar a tela de Configurações do Protesto.

Todo POST passa pelo token de formulário do `before_request` do app, e toda
escrita deixa linha em `audit_logs` — com números e códigos, nunca o nome de
quem pediu.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from functools import wraps

from flask import abort, flash, redirect, render_template, request, url_for

import apostila as AP
import modulos_ligados as MODLIG

VER = ("ADMIN", "MANAGER", "USER", "AUDITOR")
FAZER = ("ADMIN", "MANAGER", "USER")
CANCELAR = ("ADMIN", "MANAGER")
CONFIGURAR = ("ADMIN",)


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """Pendura as telas da apostila no app já construído."""

    usuario_nome = app.extensions["usuario_nome"]
    usuario_papel = app.extensions["usuario_papel"]

    def aberto(view):
        """Recusa a rota quando o alcance do módulo não deixa este papel entrar."""
        @wraps(view)
        def guardada(*args, **kwargs):
            papel = usuario_papel()
            if not MODLIG.pode_entrar(db.get_setting, AP.MODULO, papel):
                ate_onde = MODLIG.alcance(db.get_setting, AP.MODULO)
                flash(MODLIG.motivo(AP.MODULO, ate_onde), "warning")
                if papel in CONFIGURAR:
                    return redirect(url_for("apostila_configuracao"))
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return guardada

    def _hoje() -> str:
        return date.today().isoformat()

    def _volta_ao_pedido(pedido_id):
        return redirect(url_for("apostila_pedido", pedido_id=pedido_id))

    def _pedido_da_apostila(apostila_id: int) -> int:
        with db.connect() as con:
            linha = AP.apostila(con, apostila_id)
        if not linha:
            abort(404)
        return int(linha["pedido_id"])

    @app.route("/apostila")
    @login_required
    @roles_required(*VER)
    @aberto
    def apostila_lista():
        """Os pedidos e o que ainda falta. Só LÊ."""
        with db.connect() as con:
            lista = AP.pedidos(con)
            falta = AP.pendencias(con)
        return render_template(
            "apostila_lista.html", pedidos=lista, pendencias=falta,
            atribuicoes=[(s, AP.ATR.ATRIBUICOES[AP.ATOS_DE_APOSTILA[s]["atribuicao"]]["nome"])
                         for s in AP.ATRIBUICOES_LIBERADAS],
            hoje=_hoje(), pode_fazer=usuario_papel() in FAZER)

    @app.route("/apostila/pedido", methods=["POST"])
    @login_required
    @roles_required(*FAZER)
    @aberto
    def apostila_pedido_novo():
        """Registra o pedido de apostilamento."""
        f = request.form
        try:
            with db.transaction() as con:
                novo = AP.abrir_pedido(
                    con, agora=db.now(), por=usuario_nome(),
                    recebido_em=f.get("recebido_em"), atribuicao=f.get("atribuicao"),
                    requerente_nome=f.get("requerente_nome"),
                    requerente_documento=f.get("requerente_documento"),
                    requerente_contato=f.get("requerente_contato"),
                    pais_destino=f.get("pais_destino"), protocolo=f.get("protocolo"),
                    observacao=f.get("observacao"))
        except AP.ApostilaError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("apostila_lista"))
        audit("APOSTILA_PEDIDO", "ap_pedidos", novo,
              {"atribuicao": (f.get("atribuicao") or "").upper(),
               "protocolo": (f.get("protocolo") or "").strip()})
        flash("Pedido registrado. Inclua agora os documentos a apostilar.", "success")
        return _volta_ao_pedido(novo)

    @app.route("/apostila/pedido/<int:pedido_id>")
    @login_required
    @roles_required(*VER)
    @aberto
    def apostila_pedido(pedido_id: int):
        """A ficha do pedido, com as apostilas dele. Só LÊ."""
        with db.connect() as con:
            p = AP.pedido(con, pedido_id)
            if not p:
                abort(404)
            itens = AP.itens_para_cobrar(con, pedido_id, db.get_setting)
        papel = usuario_papel()
        return render_template(
            "apostila_pedido.html", p=p, itens=itens, hoje=_hoje(),
            tipos=AP.TIPOS_DE_DOCUMENTO, situacoes=AP.SITUACOES,
            pode_fazer=papel in FAZER, pode_cancelar=papel in CANCELAR)

    @app.route("/apostila/pedido/<int:pedido_id>/documento", methods=["POST"])
    @login_required
    @roles_required(*FAZER)
    @aberto
    def apostila_documento_novo(pedido_id: int):
        """Inclui um documento, com o valor da tabela do dia."""
        f = request.form
        try:
            with db.transaction() as con:
                novo = AP.incluir_documento(
                    con, pedido_id, agora=db.now(), por=usuario_nome(),
                    documento_tipo=f.get("documento_tipo"),
                    documento_descricao=f.get("documento_descricao"),
                    documento_data=f.get("documento_data"),
                    signatario_nome=f.get("signatario_nome"),
                    signatario_cargo=f.get("signatario_cargo"),
                    autoridade=f.get("autoridade"), get_setting=db.get_setting)
        except AP.ApostilaError as erro:
            flash(str(erro), "danger")
            return _volta_ao_pedido(pedido_id)
        audit("APOSTILA_DOCUMENTO", "ap_apostilas", novo, {"pedido": pedido_id})
        flash("Documento incluído. Depois de emitir no sistema do CNJ, registre "
              "aqui o código da apostila.", "success")
        return _volta_ao_pedido(pedido_id)

    def _acao(apostila_id: int, faz, mensagem: str, acao: str):
        """Uma ação sobre a apostila, com a frase do impedimento e o rastro."""
        pedido_id = _pedido_da_apostila(apostila_id)
        try:
            with db.transaction() as con:
                rastro = faz(con) or {}
        except AP.ApostilaError as erro:
            flash(str(erro), "danger")
            return _volta_ao_pedido(pedido_id)
        except sqlite3.IntegrityError:
            # Duas pessoas gravando o mesmo código ou selo ao mesmo tempo: o
            # índice único segurou a segunda.
            flash("Esse código ou selo acabou de ser gravado em outra apostila. "
                  "Confira o número.", "danger")
            return _volta_ao_pedido(pedido_id)
        audit(acao, "ap_apostilas", apostila_id,
              rastro if isinstance(rastro, dict) else {"valor": rastro})
        flash(mensagem, "success")
        return _volta_ao_pedido(pedido_id)

    @app.route("/apostila/<int:apostila_id>/emitir", methods=["POST"])
    @login_required
    @roles_required(*FAZER)
    @aberto
    def apostila_emitir(apostila_id: int):
        """Registra a apostila emitida no sistema do CNJ; dá o número de ordem."""
        f = request.form
        return _acao(apostila_id, lambda con: AP.emitir(
            con, apostila_id, agora=db.now(), por=usuario_nome(),
            codigo_cnj=f.get("codigo_cnj"), emitida_em=f.get("emitida_em"),
            selo=f.get("selo"), protocolo_item_id=f.get("protocolo_item_id"),
            get_setting=db.get_setting),
            "Apostila registrada no controle.", "APOSTILA_EMITIDA")

    @app.route("/apostila/<int:apostila_id>/selo", methods=["POST"])
    @login_required
    @roles_required(*FAZER)
    @aberto
    def apostila_selo(apostila_id: int):
        """Grava o selo que chegou depois da emissão."""
        return _acao(apostila_id, lambda con: {"selo": AP.registrar_selo(
            con, apostila_id, agora=db.now(), por=usuario_nome(),
            selo=request.form.get("selo"))},
            "Selo gravado.", "APOSTILA_SELO")

    @app.route("/apostila/<int:apostila_id>/recusar", methods=["POST"])
    @login_required
    @roles_required(*FAZER)
    @aberto
    def apostila_recusar(apostila_id: int):
        """Recusa o documento que não se apostila. Não ocupa número."""
        return _acao(apostila_id, lambda con: AP.recusar(
            con, apostila_id, agora=db.now(), por=usuario_nome(),
            motivo=request.form.get("motivo")),
            "Documento recusado. O motivo fica na ficha.", "APOSTILA_RECUSADA")

    @app.route("/apostila/<int:apostila_id>/cancelar", methods=["POST"])
    @login_required
    @roles_required(*CANCELAR)
    @aberto
    def apostila_cancelar(apostila_id: int):
        """Marca a apostila cancelada no CNJ. O número fica no controle."""
        return _acao(apostila_id, lambda con: AP.cancelar(
            con, apostila_id, agora=db.now(), por=usuario_nome(),
            motivo=request.form.get("motivo")),
            "Apostila cancelada. Ela continua no controle, marcada.",
            "APOSTILA_CANCELADA")

    @app.route("/apostila/controle")
    @login_required
    @roles_required(*VER)
    @aberto
    def apostila_controle():
        """O controle das apostilas emitidas no período, para imprimir. Só LÊ."""
        try:
            with db.connect() as con:
                r = AP.controle(con, de=request.args.get("de"),
                                ate=request.args.get("ate"))
        except AP.ApostilaError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("apostila_controle"))
        return render_template("apostila_controle.html", r=r,
                               situacoes=AP.SITUACOES)

    @app.route("/apostila/<int:apostila_id>/certidao")
    @login_required
    @roles_required(*VER)
    @aberto
    def apostila_certidao(apostila_id: int):
        """A certidão do que consta no controle sobre uma apostila. Só LÊ."""
        with db.connect() as con:
            a = AP.apostila(con, apostila_id)
        if not a:
            abort(404)
        if a["ordem"] is None:
            flash("Só a apostila emitida está no controle e tem certidão.", "warning")
            return _volta_ao_pedido(a["pedido_id"])
        audit("APOSTILA_CERTIDAO", "ap_apostilas", apostila_id, {"ordem": a["ordem"]})
        return render_template("apostila_certidao.html", a=a, situacoes=AP.SITUACOES,
                               emitida_por=usuario_nome(), hoje=_hoje())

    @app.route("/administrativo/gestor/apostila", methods=["GET", "POST"])
    @login_required
    @roles_required(*CONFIGURAR)
    def apostila_configuracao():
        """Liga o módulo (alcance) e escolhe o serviço da tabela. Só do oficial."""
        chave_alcance = MODLIG.CHAVE_DA_CONFIGURACAO[AP.MODULO]
        with db.connect() as con:
            servicos = AP.servicos_da_tabela(con)
        if request.method == "POST":
            alcance = (request.form.get("alcance") or "").strip().upper()
            if alcance not in MODLIG.ALCANCES:
                alcance = MODLIG.ALCANCE_DE_FABRICA[AP.MODULO]
            servico = (request.form.get("servico") or "").strip()
            if servico not in {str(s["codigo"]) for s in servicos}:
                servico = ""
            valores = {chave_alcance: alcance, AP.CHAVE_DO_SERVICO: servico}
            db.set_settings(valores)
            audit("APOSTILA_CONFIGURACAO", "SETTINGS", None, valores)
            flash("Configuração da Apostila de Haia gravada.", "success")
            return redirect(url_for("apostila_configuracao"))
        return render_template(
            "apostila_configuracao.html",
            alcance=MODLIG.alcance(db.get_setting, AP.MODULO),
            servico=str(db.get_setting(AP.CHAVE_DO_SERVICO, "") or ""),
            servicos=servicos, chave_alcance=chave_alcance)
