"""As telas da FILA DE CORREÇÕES DE OFÍCIO — propor, ver, aprovar e recusar.

Decisão do oficial, 29/10/2026: a leitura do banco é livre para os robôs e
os agentes; a ESCRITA é do sistema, com usuário. A correção de ofício que se
fazia por script direto no banco vira uma proposta nesta fila: o agente (pela
conta de robô) ou a escrevente PROPÕE; o oficial APROVA, com a afirmação
expressa; o SERVIDOR executa, numa transação. O domínio mora em
`correcoes_de_oficio`; aqui a rota só liga os fios.

MÓDULO PRÓPRIO, com as rotas registradas à parte (a forma de
`cra21_web.registrar_rotas`), para não disputar `atribuicoes_web.py`.

O ROBÔ ALCANÇA TRÊS ROTAS, e só elas (`rotas_do_robo.DA_FILA_DE_CORRECOES`):
o formulário, a proposta (formulário ou JSON) e a ficha. Aprovar, recusar e
anexar ficam fora da lista — o `before_request` já devolve 403 — e aprovar e
recusar recusam o robô POR DENTRO também, e o domínio uma terceira vez.
"""
from __future__ import annotations

from flask import abort, flash, jsonify, redirect, render_template, request, url_for

import correcoes_de_oficio as CDO
import protesto_selo_previo as PSELO
import selo_robo as SR
from bd_nativo import ERROS_DO_BANCO
from storage import save_upload


def registrar_rotas(app, db, login_required, roles_required, audit):
    """Pendura a fila no app já construído."""

    # O ANEXO (a prova) ABRE PARA QUEM ABRE A FICHA — a regra de
    # `TELA_DO_ANEXO`, lida da própria tela. A forma é a de `despesas_web`.
    app.extensions.setdefault("tela_do_anexo", {})[CDO.ENTIDADE_DO_ANEXO] = (
        "correcoes_de_oficio_ficha",)
    archive_root = app.extensions.get("archive_root")

    def _quem():
        uid = app.extensions["usuario_id"]()
        return db.get_user(uid) if uid else None

    def _anexar(correcao_id: int, arquivos, quem) -> int:
        """Guarda os arquivos da prova na pasta da casa. ESCREVE."""
        if archive_root is None:
            return 0
        pasta = archive_root() / "correcoes_de_oficio" / str(int(correcao_id))
        feitos = 0
        for arquivo in arquivos or []:
            if not arquivo or not arquivo.filename:
                continue
            info = save_upload(arquivo, pasta)
            db.add_attachment(CDO.ENTIDADE_DO_ANEXO, int(correcao_id), info,
                              int(quem["id"]), "Prova da correção de ofício")
            feitos += 1
        return feitos

    def _contexto_do_formulario(tipo: str, resultado=None, valores=None) -> dict:
        tipos = CDO.tipos_disponiveis()
        escolhido = next((t for t in tipos if t["chave"] == tipo), None)
        return {"tipos": tipos, "escolhido": escolhido,
                "campos_do_cadastro": CDO.campos_do_cadastro(),
                "resultado": resultado, "valores": valores or {},
                "minimo_do_motivo": CDO.MINIMO_DE_LETRAS_DO_MOTIVO}

    # ------------------------------------------------------------- a lista

    @app.route("/administrativo/correcoes-de-oficio")
    @login_required
    @roles_required(*CDO.QUEM_VE)
    def correcoes_de_oficio_lista():
        """As quatro abas — Propostas, Executadas, Recusadas e Falhas. Só LÊ.

        Na aba das propostas vai também a lista que o roteiro do Protesto lê
        (`pendentes`): os títulos que esperam a decisão do oficial."""
        aba = str(request.args.get("aba") or CDO.PROPOSTA)
        if aba not in CDO.SITUACOES:
            aba = CDO.PROPOSTA
        # O FILTRO DA ATRIBUIÇÃO é o que separa a porta do Protesto («Do
        # oficial») da do Administrativo: a mesma fila, só a parte dele.
        atribuicao = CDO.atribuicao_do_filtro(request.args.get("atribuicao"))
        with db.connect() as con:
            lista = CDO.listar(con, situacao=aba, atribuicao=atribuicao)
            contagem = CDO.contar_por_situacao(con, atribuicao=atribuicao)
            pendencias = (CDO.pendentes(con)
                          if aba == CDO.PROPOSTA and atribuicao in (None, CDO.ATRIBUICAO_PROTESTO)
                          else [])
        quem = _quem()
        return render_template(
            "correcoes_de_oficio.html", lista=lista, contagem=contagem, aba=aba,
            abas=CDO.ROTULO_DA_SITUACAO, pendencias=pendencias,
            atribuicao=atribuicao,
            nome_da_atribuicao=CDO.NOME_DA_ATRIBUICAO.get(atribuicao or "", ""),
            limite=CDO.LIMITE_DA_LISTA,
            pode_propor=bool(quem and quem["role"] in CDO.QUEM_PROPOE))

    # ------------------------------------------------------------- propor

    @app.route("/administrativo/correcoes-de-oficio/nova")
    @login_required
    @roles_required(*CDO.QUEM_PROPOE)
    def correcoes_de_oficio_nova():
        """O formulário da proposta. Só mostra."""
        tipo = str(request.args.get("tipo") or "")
        return render_template("correcoes_de_oficio_nova.html",
                               **_contexto_do_formulario(tipo))

    @app.route("/administrativo/correcoes-de-oficio/propor", methods=["POST"])
    @login_required
    @roles_required(*CDO.QUEM_PROPOE)
    def correcoes_de_oficio_propor():
        """Prévia ou proposta. PROPOR NÃO ALTERA NADA fora da fila.

        Aceita o formulário da tela ou um JSON — o caminho do agente pela conta
        de robô: `{"tipo", "parametros", "motivo", "agente"?, "previa"?}`,
        com o token no cabeçalho `X-CSRF-Token`. No JSON a resposta é JSON:
        `ok`, `id`, `recusas`, `avisos`, `antes`, `depois`, `linhas`, `resumo`.
        """
        quem = _quem()
        dados = request.get_json(silent=True) if request.is_json else None
        como_json = request.is_json
        if como_json:
            if not isinstance(dados, dict):
                return jsonify({"ok": False, "recusas": [
                    "O corpo é um objeto JSON com tipo, parametros e motivo."]}), 400
            tipo = str(dados.get("tipo") or "")
            parametros = dados.get("parametros")
            motivo, agente = dados.get("motivo"), dados.get("agente")
            previa = bool(dados.get("previa"))
        else:
            tipo = str(request.form.get("tipo") or "")
            parametros = CDO.parametros_do_formulario(tipo, request.form)
            motivo, agente = request.form.get("motivo"), request.form.get("agente")
            previa = request.form.get("acao") == "previa"
        argumentos = {"tipo": tipo, "parametros": parametros, "motivo": motivo,
                      "quem": quem, "agora": db.now(), "agente": agente,
                      "ip": request.remote_addr}
        if previa:
            # A PRÉVIA SÓ LÊ: conexão sem transação de escrita.
            with db.connect() as con:
                r = CDO.propor(con, previa=True, **argumentos)
        else:
            with db.transaction() as con:
                r = CDO.propor(con, previa=False, **argumentos)
        if r["ok"] and not previa and not como_json:
            anexos = _anexar(r["id"], request.files.getlist("anexos"), quem)
            if anexos:
                audit(CDO.ACAO_ANEXO, CDO.ENTIDADE, r["id"], {"arquivos": anexos})
        if como_json:
            return jsonify(r), (200 if r["ok"] else 400)
        if r["ok"] and not previa:
            flash(f"Proposta nº {r['id']} gravada. Nada foi alterado: ela espera a "
                  "decisão do oficial, e virou tarefa dele.", "success")
            return redirect(url_for("correcoes_de_oficio_ficha", correcao_id=r["id"]))
        return render_template("correcoes_de_oficio_nova.html",
                               **_contexto_do_formulario(tipo, r, request.form))

    # ------------------------------------------------------------- a ficha

    @app.route("/administrativo/correcoes-de-oficio/<int:correcao_id>")
    @login_required
    @roles_required(*CDO.QUEM_VE)
    def correcoes_de_oficio_ficha(correcao_id: int):
        """A proposta inteira: o antes, o depois, a prova e a decisão. Só LÊ."""
        with db.connect() as con:
            c = CDO.uma(con, correcao_id)
        if c is None:
            abort(404)
        quem = _quem()
        robo = SR.usuario_e_robo(quem)
        aberta = c["situacao"] == CDO.PROPOSTA
        return render_template(
            "correcoes_de_oficio_ficha.html", c=c,
            anexos=db.get_attachments(CDO.ENTIDADE_DO_ANEXO, correcao_id),
            pode_decidir=bool(aberta and quem and not robo
                              and quem["role"] in CDO.QUEM_APROVA),
            pode_anexar=bool(aberta and quem and not robo
                             and quem["role"] in CDO.QUEM_PROPOE),
            minimo_da_afirmacao=PSELO.MINIMO_DE_LETRAS_DA_AFIRMACAO,
            modelo_da_afirmacao=PSELO.MODELO_DA_AFIRMACAO,
            minimo_da_recusa=CDO.MINIMO_DE_LETRAS_DA_RECUSA)

    @app.route("/administrativo/correcoes-de-oficio/<int:correcao_id>/anexar",
               methods=["POST"])
    @login_required
    @roles_required(*CDO.QUEM_PROPOE)
    def correcoes_de_oficio_anexar(correcao_id: int):
        """Junta prova a uma proposta que ainda espera decisão. ESCREVE."""
        quem = _quem()
        with db.connect() as con:
            c = CDO.uma(con, correcao_id)
        if c is None:
            abort(404)
        if c["situacao"] != CDO.PROPOSTA:
            flash("A proposta já foi decidida: a prova dela é a que estava junta "
                  "quando se decidiu.", "danger")
            return redirect(url_for("correcoes_de_oficio_ficha", correcao_id=correcao_id))
        anexos = _anexar(correcao_id, request.files.getlist("anexos"), quem)
        if anexos:
            audit(CDO.ACAO_ANEXO, CDO.ENTIDADE, correcao_id, {"arquivos": anexos})
            flash(f"{anexos} arquivo(s) juntado(s) à proposta.", "success")
        else:
            flash("Escolha pelo menos um arquivo.", "danger")
        return redirect(url_for("correcoes_de_oficio_ficha", correcao_id=correcao_id))

    # ------------------------------------------------------------- decidir

    @app.route("/administrativo/correcoes-de-oficio/<int:correcao_id>/aprovar",
               methods=["POST"])
    @login_required
    @roles_required(*CDO.QUEM_APROVA)
    def correcoes_de_oficio_aprovar(correcao_id: int):
        """O oficial aprova e o SERVIDOR executa, na transação desta rota.

        A falha (o «antes» que mudou, a conferência que não fechou) fica
        GRAVADA como FALHOU — por isso a transação é confirmada também nela.
        """
        quem = _quem()
        if SR.usuario_e_robo(quem):
            abort(403)
        with db.transaction() as con:
            r = CDO.aprovar(con, correcao_id, aprovador=quem,
                            afirmo=request.form.get("afirmo") == "1",
                            afirmacao=request.form.get("afirmacao"),
                            agora=db.now(), ip=request.remote_addr)
        if r["ok"]:
            flash(f"Correção de ofício nº {correcao_id} aprovada e executada pelo "
                  "servidor. A auditoria e a sua afirmação expressa ficaram "
                  "gravadas.", "success")
        elif r.get("situacao") == CDO.FALHOU:
            flash(f"A correção nº {correcao_id} NÃO foi executada: ficou como "
                  "FALHOU, e o motivo está nesta ficha.", "danger")
        else:
            flash(r["recusa"], "danger")
        return redirect(url_for("correcoes_de_oficio_ficha", correcao_id=correcao_id))

    @app.route("/administrativo/correcoes-de-oficio/<int:correcao_id>/recusar",
               methods=["POST"])
    @login_required
    @roles_required(*CDO.QUEM_APROVA)
    def correcoes_de_oficio_recusar(correcao_id: int):
        """O oficial recusa, com o motivo; a proposta fica no histórico."""
        quem = _quem()
        if SR.usuario_e_robo(quem):
            abort(403)
        with db.transaction() as con:
            r = CDO.recusar(con, correcao_id, aprovador=quem,
                            motivo=request.form.get("motivo_da_recusa"),
                            agora=db.now(), ip=request.remote_addr)
        if r["ok"]:
            flash(f"Proposta nº {correcao_id} recusada. Ela fica no histórico, na "
                  "aba das recusadas.", "success")
        else:
            flash(r["recusa"], "danger")
        return redirect(url_for("correcoes_de_oficio_ficha", correcao_id=correcao_id))

    # ------------------------------------------------- o contador do painel

    @app.context_processor
    def _correcoes_de_oficio_no_painel() -> dict:
        """Quantas propostas esperam o oficial — só para o ADMIN de gente, e só
        no painel geral, para não contar em toda tela (a forma de
        `gestor_web._erros_no_painel`)."""
        try:
            if (request.endpoint or "") != "dashboard":
                return {"correcoes_de_oficio_no_painel": None}
        except RuntimeError:
            return {"correcoes_de_oficio_no_painel": None}
        quem = _quem()
        if not quem or quem["role"] not in CDO.QUEM_APROVA or SR.usuario_e_robo(quem):
            return {"correcoes_de_oficio_no_painel": None}
        try:
            with db.connect() as con:
                n = CDO.contar(con)
        except ERROS_DO_BANCO:
            # O painel não cai por causa de um quadro; e não mostra zero que
            # não mediu — some, como os outros quadros do painel.
            return {"correcoes_de_oficio_no_painel": None}
        return {"correcoes_de_oficio_no_painel": ({"pendentes": n} if n else None)}
