"""
As telas da LISTA DE ATENÇÃO PARA FRAUDES.

DUAS TELAS, E ELAS SERVEM A DUAS PESSOAS DIFERENTES

    **A lista** (`/fraudes`) é de quem recebe as comunicações — o oficial e o
    gerente. É ali que a comunicação que chegou pelo malote vira nome
    procurável.

    **A consulta** (`/fraudes/consultar`) é do balcão, e é de TODOS. Quem está
    atendendo digita o nome que o cliente deu e vê na hora. Deixar a consulta
    só para ADMIN seria pôr a informação longe de quem precisa dela.

E O ALERTA NÃO MORA AQUI
    Ele aparece **onde o ato acontece** — na ficha do título, na tela de abrir
    registro novo. Aviso que mora numa aba é aviso que ninguém vê, e esta casa
    já aprendeu isso três vezes.
"""
from __future__ import annotations

import sqlite3

from flask import flash, redirect, render_template, request, url_for

import fraude as FR


def registrar_rotas(app, db, login_required, roles_required, audit):
    """Pendura as telas da lista de atenção no app já construído."""

    def agora() -> str:
        return db.now()

    usuario_nome = app.extensions["usuario_nome"]

    def _campo(nome: str) -> str:
        return (request.form.get(nome) or "").strip()

    def _ler():
        con = db.connect()
        con.row_factory = sqlite3.Row
        return con

    # ------------------------------------------------------------ a lista

    @app.route("/fraudes")
    @roles_required("ADMIN", "MANAGER", "USER")
    def fraudes():
        """A lista de atenção — incluir, procurar, inativar. Só LÊ aqui.

        É de quem recebe as comunicações. O oficial escreveu que elas chegam
        **continuamente pelo malote**: o que esta tela faz é transformar papel
        que vira pasta em nome que o sistema reconhece no balcão.
        """
        busca = (request.args.get("q") or "").strip()
        situacao = (request.args.get("situacao") or "ATIVO").upper()
        if situacao not in FR.SITUACOES:
            situacao = "ATIVO"
        with _ler() as con:
            linhas = FR.listar(con, situacao=situacao, busca=busca or None)
            contas = FR.contagem(con)
            rastro = FR.conferencias(con, limite=30)
        return render_template("fraudes.html", linhas=linhas, contas=contas,
                               rastro=rastro, busca=busca, situacao=situacao,
                               papeis=FR.PAPEIS)

    @app.route("/fraudes/incluir", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def fraude_incluir():
        """Põe um nome ou documento na lista. ESCREVE."""
        try:
            with db.transaction() as con:
                con.row_factory = sqlite3.Row
                r = FR.incluir(
                    con, papel=_campo("papel"), origem=_campo("origem"),
                    agora=agora(), nome=_campo("nome") or None,
                    documento=_campo("documento") or None,
                    origem_data=_campo("origem_data") or None,
                    origem_orgao=_campo("origem_orgao") or None,
                    observacao=_campo("observacao") or None,
                    usuario=usuario_nome())
        except FR.FraudeError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("fraudes"))
        # `audit` abre transação própria: FORA do `with`, como no resto da casa.
        audit("FRAUDE_INCLUIR", "fr_alertas", r["alerta_id"],
              {"papel": r["papel"], "nome": r["nome"],
               "documento": r["documento"]})
        flash(f"{r['nome'] or r['documento']} entrou na lista de atenção. "
              f"O sistema passa a avisar quando esse nome aparecer num ato.",
              "success")
        return redirect(url_for("fraudes"))

    @app.route("/fraudes/<int:alerta_id>/situacao", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def fraude_situacao(alerta_id: int):
        """Tira da lista, ou devolve a ela. ESCREVE.

        TIRAR EXIGE MOTIVO ESCRITO — comunicação de fraude é documento, e o
        que ela gerou não se apaga sem explicação. Quem recusa sem motivo é o
        domínio, e não esta rota.
        """
        try:
            with db.transaction() as con:
                con.row_factory = sqlite3.Row
                if _campo("acao") == "reativar":
                    FR.reativar(con, alerta_id, agora=agora(),
                                usuario=usuario_nome())
                    recado = "Nome devolvido à lista de atenção."
                else:
                    FR.inativar(con, alerta_id, motivo=_campo("motivo"),
                                agora=agora(), usuario=usuario_nome())
                    recado = ("Nome tirado da lista, com o motivo registrado. "
                              "A comunicação continua guardada.")
        except FR.FraudeError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("fraudes"))
        audit("FRAUDE_SITUACAO", "fr_alertas", alerta_id,
              {"acao": _campo("acao") or "inativar"})
        flash(recado, "success")
        return redirect(url_for("fraudes"))

    # ---------------------------------------------------------- a consulta

    @app.route("/fraudes/consultar")
    @login_required
    def fraude_consultar():
        """A consulta do balcão. Só LÊ — e é de TODOS, não só do ADMIN.

        Quem atende digita o nome que o cliente deu e vê na hora. Pôr esta
        tela atrás de perfil seria deixar a informação longe de quem precisa
        dela no momento em que ela serve.

        Ela mostra também **o que a casa já tem daquela pessoa** — a
        comunicação chega depois do fato, e saber que há três atos no nome
        transforma um aviso numa diligência.
        """
        nome = (request.args.get("nome") or "").strip()
        documento = (request.args.get("documento") or "").strip()
        achados, atos = [], []
        if nome or documento:
            with _ler() as con:
                achados = FR.conferir(con, nome=nome, documento=documento)
                atos = FR.atos_da_pessoa(con, nome=nome, documento=documento)
        return render_template("fraude_consultar.html", nome=nome,
                               documento=documento, achados=achados,
                               atos=atos, procurou=bool(nome or documento))

    @app.route("/fraudes/<int:alerta_id>/conferir", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def fraude_conferir(alerta_id: int):
        """Registra que o alerta foi visto, e o que se decidiu. ESCREVE.

        É ISTO QUE PROTEGE A CASA, e não o alerta. Se um ato fraudado passar
        apesar do aviso, a pergunta que vem é "o sistema avisou?" — e esta
        linha é a resposta escrita.
        """
        volta = request.form.get("volta") or url_for("fraude_consultar")
        try:
            with db.transaction() as con:
                con.row_factory = sqlite3.Row
                r = FR.registrar_conferencia(
                    con, alerta_id, decisao=_campo("decisao") or "ANOTOU",
                    agora=agora(), onde=_campo("onde") or None,
                    referencia=_campo("referencia") or None,
                    nome=_campo("nome") or None,
                    documento=_campo("documento") or None,
                    observacao=_campo("observacao") or None,
                    usuario=usuario_nome())
        except FR.FraudeError as erro:
            flash(str(erro), "danger")
            return redirect(volta)
        audit("FRAUDE_CONFERENCIA", "fr_conferencias", r["conferencia_id"],
              {"alerta_id": alerta_id, "decisao": r["decisao"],
               "onde": _campo("onde") or None})
        flash("Conferência registrada.", "success")
        return redirect(volta)
