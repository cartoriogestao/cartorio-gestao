# -*- coding: utf-8 -*-
"""As telas da fila de conferência das fichas (Livros 4 e 5).

A tela só oferece; quem recusa é `ri_fila_fichas`. Isso vale também para a regra
da casa: esconder o valor aqui não bastaria, e o domínio recusa o aceite dele.

`AUDITOR` lê a fila e o rastro, e não decide. Ligar a regra da casa é só do
titular.
"""
from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, url_for

import ri_fila_fichas as FILA
import titular_privado as TITULAR

QUEM_CONFERE = ("ADMIN", "MANAGER", "USER")
QUEM_VE = (*QUEM_CONFERE, "AUDITOR")
QUEM_LIBERA_LOTE = ("ADMIN", "MANAGER")
POR_PAGINA = 100


def registrar_rotas(app, db, login_required, roles_required, audit) -> None:
    usuario_nome = app.extensions["usuario_nome"]
    _, e_o_titular = TITULAR.guarda(app, db)

    def _settings() -> dict:
        return dict(db.get_settings())

    def _depois(item, item_id):
        """Depois de decidir, vai para a próxima da mesma classe."""
        with db.connect() as con:
            seguinte = FILA.proximo(con, item)
        if seguinte:
            return redirect(url_for("ri_fila_ficha", item_id=seguinte))
        return redirect(url_for("ri_fila_fichas", livro=item["livro"]))

    @app.route("/ri/fila-fichas")
    @login_required
    @roles_required(*QUEM_VE)
    def ri_fila_fichas():
        livro = request.args.get("livro") or FILA.LIVRO_REAL
        if livro not in (FILA.LIVRO_REAL, FILA.LIVRO_PESSOAL):
            livro = FILA.LIVRO_REAL
        classe = (request.args.get("classe") or "").strip() or None
        situacao = request.args.get("situacao", FILA.A_CONFERIR).strip() or None
        confianca = (request.args.get("confianca") or "").strip() or None
        prioridade = request.args.get("prioridade", type=int)
        amostra_id = request.args.get("amostra", type=int)
        pagina = max(request.args.get("pagina", 1, type=int), 1)
        s = _settings()
        ligada = FILA.regra_ligada(s)
        with db.connect() as con:
            fila = FILA.listar(con, livro=livro, classe=classe, situacao=situacao,
                               confianca=confianca, prioridade=prioridade,
                               amostra_id=amostra_id, limite=POR_PAGINA,
                               deslocamento=(pagina - 1) * POR_PAGINA)
            contagem = FILA.contar(con)
            fatias = FILA.fatias_de_lote(con, ligada) if livro == FILA.LIVRO_REAL else []
        return render_template(
            "ri_fila_fichas.html", fila=fila, contagem=contagem, fatias=fatias, livro=livro,
            classe=classe or "", situacao=situacao or "", confianca=confianca or "",
            prioridade=prioridade or "", amostra_id=amostra_id or "", pagina=pagina,
            por_pagina=POR_PAGINA, ligada=ligada, e_titular=e_o_titular(),
            nome_da_classe=FILA.NOME_DA_CLASSE, nome_da_situacao=FILA.NOME_DA_SITUACAO,
            nome_da_prioridade=FILA.NOME_DA_PRIORIDADE)

    @app.route("/ri/fila-fichas/gerar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_CONFERE)
    def ri_fila_fichas_gerar():
        try:
            with db.transaction() as con:
                feito = FILA.gerar(con, agora=db.now(), settings=_settings())
        except FILA.FilaError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ri_fila_fichas"))
        audit("RI_FILA_GERADA", "ri_ff_itens", None,
              f"fichas {feito['fichas']} · partes {feito['partes']} · novos {feito['novos']} · "
              f"atualizados {feito['atualizados']} · decisões preservadas {feito['preservados']}")
        flash(f"Fila atualizada: {feito['fichas']} fichas e {feito['partes']} partes lidas. "
              "Nenhuma matrícula foi alterada.", "ok")
        return redirect(url_for("ri_fila_fichas"))

    @app.route("/ri/fila-fichas/<int:item_id>")
    @login_required
    @roles_required(*QUEM_VE)
    def ri_fila_ficha(item_id: int):
        ligada = FILA.regra_ligada(_settings())
        with db.connect() as con:
            item = FILA.ler(con, item_id)
            rastro = FILA.alteracoes(con, item_id=item_id) if item else []
        if not item:
            flash("Este item da fila não existe.", "danger")
            return redirect(url_for("ri_fila_fichas"))
        return render_template(
            "ri_fila_ficha.html", item=item, campos=FILA.campos_visiveis(item, ligada),
            avisos=FILA.avisos_visiveis(item, ligada),
            rastro=rastro, ligada=ligada, nome_da_classe=FILA.NOME_DA_CLASSE,
            nome_da_situacao=FILA.NOME_DA_SITUACAO,
            nome_da_prioridade=FILA.NOME_DA_PRIORIDADE,
            abertas=FILA.ABERTAS, decididas=FILA.DECIDIDAS,
            pode_decidir=app.extensions["usuario_papel"]() in QUEM_CONFERE)

    def _decisao(item_id: int, acao: str, funcao):
        try:
            with db.transaction() as con:
                feito = funcao(con)
        except FILA.FilaError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ri_fila_ficha", item_id=item_id))
        item = feito["item"]
        campos = feito.get("gravados") or feito.get("campos") or []
        audit(acao, "ri_ff_itens", item_id,
              f"matrícula id {item['matricula_id']} · parte {item['parte_id']} · "
              f"campos: {', '.join(campos) or 'nenhum'}")
        return item

    @app.route("/ri/fila-fichas/<int:item_id>/aceitar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_CONFERE)
    def ri_fila_ficha_aceitar(item_id: int):
        s = _settings()
        r = _decisao(item_id, "RI_FILA_ACEITE", lambda con: FILA.aceitar(
            con, item_id, campos=request.form.getlist("campo"), agora=db.now(),
            usuario=usuario_nome(), ligada=FILA.regra_ligada(s), cns=FILA.cns_da_casa(s),
            motivo=request.form.get("motivo") or "",
            mesma_pessoa=request.form.get("mesma_pessoa") == "1"))
        if not isinstance(r, dict):
            return r
        flash("Gravado na ficha, com o rastro. Dá para desfazer.", "ok")
        return _depois(r, item_id)

    @app.route("/ri/fila-fichas/<int:item_id>/corrigir", methods=["POST"])
    @login_required
    @roles_required(*QUEM_CONFERE)
    def ri_fila_ficha_corrigir(item_id: int):
        s = _settings()
        valores = {k[len("valor_"):]: v for k, v in request.form.items()
                   if k.startswith("valor_")}
        r = _decisao(item_id, "RI_FILA_CORRECAO", lambda con: FILA.corrigir(
            con, item_id, valores=valores, agora=db.now(), usuario=usuario_nome(),
            cns=FILA.cns_da_casa(s), motivo=request.form.get("motivo") or "",
            mesma_pessoa=request.form.get("mesma_pessoa") == "1"))
        if not isinstance(r, dict):
            return r
        flash("Correção gravada na ficha, com o rastro. Dá para desfazer.", "ok")
        return _depois(r, item_id)

    @app.route("/ri/fila-fichas/<int:item_id>/pular", methods=["POST"])
    @login_required
    @roles_required(*QUEM_CONFERE)
    def ri_fila_ficha_pular(item_id: int):
        r = _decisao(item_id, "RI_FILA_PULO", lambda con: FILA.pular(
            con, item_id, agora=db.now(), usuario=usuario_nome()))
        if not isinstance(r, dict):
            return r
        return _depois(r, item_id)

    @app.route("/ri/fila-fichas/<int:item_id>/desfazer", methods=["POST"])
    @login_required
    @roles_required(*QUEM_CONFERE)
    def ri_fila_ficha_desfazer(item_id: int):
        s = _settings()
        r = _decisao(item_id, "RI_FILA_DESFEITO", lambda con: FILA.desfazer(
            con, item_id, motivo=request.form.get("motivo") or "", agora=db.now(),
            usuario=usuario_nome(), cns=FILA.cns_da_casa(s)))
        if not isinstance(r, dict):
            return r
        flash("Desfeito: a ficha voltou ao valor anterior e o item voltou à fila.", "ok")
        return redirect(url_for("ri_fila_ficha", item_id=item_id))

    @app.route("/ri/fila-fichas/amostra", methods=["POST"])
    @login_required
    @roles_required(*QUEM_LIBERA_LOTE)
    def ri_fila_amostra():
        fatia = request.form.get("fatia") or ""
        try:
            with db.transaction() as con:
                feito = FILA.sortear_amostra(con, fatia, agora=db.now(), usuario=usuario_nome(),
                                             ligada=FILA.regra_ligada(_settings()))
        except FILA.FilaError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ri_fila_fichas"))
        audit("RI_FILA_AMOSTRA", "ri_ff_amostras", feito["amostra_id"],
              f"{fatia} · {feito['tamanho']} fichas")
        flash(f"Amostra de {feito['tamanho']} fichas sorteada. Confira uma a uma: "
              "uma correção que seja mantém o lote fechado.", "ok")
        return redirect(url_for("ri_fila_fichas", amostra=feito["amostra_id"]))

    @app.route("/ri/fila-fichas/lote/<int:amostra_id>", methods=["POST"])
    @login_required
    @roles_required(*QUEM_LIBERA_LOTE)
    def ri_fila_lote(amostra_id: int):
        s = _settings()
        try:
            with db.transaction() as con:
                feito = FILA.aceitar_lote(con, amostra_id,
                                          quantidade=request.form.get("quantidade"),
                                          agora=db.now(), usuario=usuario_nome(),
                                          ligada=FILA.regra_ligada(s), cns=FILA.cns_da_casa(s))
        except FILA.FilaError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ri_fila_fichas"))
        audit("RI_FILA_LOTE", "ri_ff_amostras", amostra_id,
              f"gravadas {feito['gravados']} · sem campo {feito['sem_campo']} · "
              f"mudaram {feito['mudaram']}")
        flash(f"Lote gravado em {feito['gravados']} fichas. {feito['sem_campo']} não tinham "
              f"campo a preencher e {feito['mudaram']} mudaram e ficaram na fila.", "ok")
        return redirect(url_for("ri_fila_fichas"))

    @app.route("/ri/fila-fichas/lote/<int:amostra_id>/desfazer", methods=["POST"])
    @login_required
    @roles_required(*QUEM_LIBERA_LOTE)
    def ri_fila_lote_desfazer(amostra_id: int):
        s = _settings()
        try:
            with db.transaction() as con:
                feito = FILA.desfazer_lote(con, amostra_id,
                                           motivo=request.form.get("motivo") or "",
                                           agora=db.now(), usuario=usuario_nome(),
                                           cns=FILA.cns_da_casa(s))
        except FILA.FilaError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ri_fila_fichas"))
        audit("RI_FILA_LOTE_DESFEITO", "ri_ff_amostras", amostra_id,
              f"desfeitas {feito['desfeitos']} · ficaram {feito['ficaram']}")
        flash(f"Lote desfeito em {feito['desfeitos']} fichas. {feito['ficaram']} foram editadas "
              "depois e ficaram como estão.", "ok")
        return redirect(url_for("ri_fila_fichas"))

    @app.route("/ri/fila-fichas/regra-da-casa", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def ri_fila_regra_casa():
        if not e_o_titular():
            abort(403)
        ligar = request.form.get("ligar") == "1"
        db.set_settings({FILA.CHAVE_REGRA_CASA: "1" if ligar else "0"})
        audit("RI_FILA_REGRA_CASA", "settings", None, "ligada" if ligar else "desligada")
        flash("Regra da casa ligada: os valores-padrão aparecem como opção, marcados como tal."
              if ligar else "Regra da casa desligada: os valores-padrão não aparecem mais.", "ok")
        return redirect(url_for("ri_fila_fichas"))

    @app.route("/ri/fila-fichas/auditoria")
    @login_required
    @roles_required(*QUEM_VE)
    def ri_fila_auditoria():
        with db.connect() as con:
            linhas = FILA.alteracoes(con)
        return render_template("ri_fila_auditoria.html", linhas=linhas,
                               rotulo=FILA.ROTULO_DO_CAMPO)
