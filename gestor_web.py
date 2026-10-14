"""A TELA DOS ENVIOS ÀS CENTRAIS — Administrativo → Envios às Centrais.

O QUE ELA RESOLVE
    O gestor confere a casa todo dia às 07:30 e cobra o que não foi mandado ao
    SIRC, à FUNAI, ao IBGE, à CENSEC, à DOI e as cinco comunicações de óbito.
    A cobrança só some quando há REGISTRO do envio com o protocolo — e até aqui
    o único jeito de registrar era por fora do sistema. Esta tela mostra o que
    está sendo cobrado e deixa quem mandou marcar e dar o protocolo.

O QUE ELA NÃO FAZ
    Não envia nada a Central nenhuma: quem envia é a pessoa, pelo portal ou
    pela tela da própria Central. Aqui se registra que foi enviado. E não fecha
    o achado na hora: quem fecha é a conferência seguinte, que procura o
    registro — a tela marca «registrado, sai na próxima conferência» para
    ninguém registrar duas vezes.

É DE TODOS, e não só do oficial: quem manda a carga é o pessoal da atribuição
(ordem do oficial em 06/10/2026), e é quem a manda que tem o protocolo na mão.
"""
from __future__ import annotations

import sqlite3

from flask import flash, redirect, render_template, request, url_for

import gestor_envios as GE


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """Pendura a tela dos envios no app já construído."""

    usuario_nome = app.extensions["usuario_nome"]

    # O TEXTO DIDÁTICO DA TAREFA COM LINK (06/10/2026): o gestor escreve
    # «Onde abrir: … — /registro-imoveis/5381», e a tela da tarefa transforma o
    # endereço em link. Só endereços DESTE sistema (começam com «/» e um dos
    # módulos da casa) viram link; o texto é escapado antes.
    import re as _re

    from markupsafe import Markup, escape

    _ENDERECO = _re.compile(
        r"(?<![\w/])(/(?:registro-imoveis|notas|rcpn|caixa|relatorios|administrativo"
        r"|livro3|protesto|rcpj|rtd)[\w\-/?=&.%]*)")

    @app.template_filter("com_links")
    def _com_links(texto):
        seguro = str(escape(texto or ""))
        return Markup(_ENDERECO.sub(r'<a href="\1">\1</a>', seguro))

    @app.route("/administrativo/gestor/envios")
    @login_required
    def gestor_envios():
        """O que a conferência cobra das Centrais, e o que já se registrou. Só LÊ."""
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            itens = GE.pendentes(con)
            feitos = GE.recentes(con, limite=40)
        grupos: dict[str, list[dict]] = {}
        for item in itens:
            grupos.setdefault(item["central"], []).append(item)
        return render_template(
            "gestor_envios.html", grupos=grupos, feitos=feitos, canais=GE.CANAIS,
            nomes=GE.NOME_DA_CENTRAL)

    @app.route("/administrativo/gestor/envios/registrar", methods=["POST"])
    @login_required
    def gestor_envios_registrar():
        """Grava o envio dos itens marcados, com o protocolo."""
        chaves = [c for c in request.form.getlist("chave") if c.strip()]
        protocolo = (request.form.get("protocolo") or "").strip()
        canal = (request.form.get("canal") or "PORTAL").strip().upper()
        mensagem = (request.form.get("mensagem") or "").strip()
        try:
            with db.transaction() as con:
                n = GE.registrar_pelas_chaves(
                    con, chaves, protocolo=protocolo, registrado_por=usuario_nome(),
                    canal=canal, mensagem=mensagem)
        except GE.EnvioError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("gestor_envios"))
        audit("GESTOR_ENVIO_REGISTRADO", "ge_envios", None,
              {"chaves": chaves, "protocolo": protocolo, "canal": canal})
        flash(f"{n} envio(s) registrado(s) com o protocolo {protocolo}. A cobrança "
              "sai na próxima conferência (todo dia às 07:30).", "success")
        return redirect(url_for("gestor_envios"))

    # ------------------------------------------------ o visto nos caixas
    #
    # O agente refaz a conta de cada caixa fechado (`gestor_caixa.parecer`); o
    # que fecha espera o VISTO de quem confere, e aqui ele se dá em lote. O
    # visto grava o id de quem clicou — a mesma coluna e a mesma regra da tela
    # do caixa: ninguém dá visto no próprio caixa.

    usuario_id = app.extensions["usuario_id"]

    def _caixas_para_o_visto(con):
        import gestor_caixa as GX
        prontos, com_pontos = [], []
        for r in con.execute(
                """SELECT * FROM cx_caixas WHERE situacao = 'FECHADO'
                      AND fechado_em IS NOT NULL AND conferido_em IS NULL
                      AND data >= '2026-08-01' ORDER BY data, id"""):
            pontos = GX.parecer(con, r)
            item = {"id": r["id"], "data": r["data"], "operador": r["operador_nome"],
                    "pontos": pontos}
            (com_pontos if pontos else prontos).append(item)
        return prontos, com_pontos

    @app.route("/administrativo/gestor/caixas")
    @roles_required("ADMIN", "MANAGER")
    def gestor_caixas():
        """Os caixas fechados, com o parecer do agente. Só LÊ."""
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            prontos, com_pontos = _caixas_para_o_visto(con)
        return render_template("gestor_caixas.html", prontos=prontos,
                               com_pontos=com_pontos, eu=usuario_nome())

    @app.route("/administrativo/gestor/caixas/visto", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def gestor_caixas_visto():
        """Dá o visto nos marcados — só nos que continuam fechando agora."""
        pedidos = {int(x) for x in request.form.getlist("caixa_id") if x.isdigit()}
        if not pedidos:
            flash("Marque os caixas que você conferiu.", "danger")
            return redirect(url_for("gestor_caixas"))
        eu, quem = usuario_nome(), usuario_id()
        with db.transaction() as con:
            con.row_factory = sqlite3.Row
            prontos, _ = _caixas_para_o_visto(con)
            # A CONTA SE REFAZ NA HORA DO CLIQUE: um lançamento mexido entre a
            # tela e o botão tira o caixa do lote, em vez de levar visto calado.
            dados = [p for p in prontos if p["id"] in pedidos and p["operador"] != eu]
            for p in dados:
                con.execute("""UPDATE cx_caixas SET conferido_por=?, conferido_em=?
                                WHERE id=? AND conferido_em IS NULL""",
                            (quem, db.now(), p["id"]))
        for p in dados:
            audit("CAIXA_CONFERIDO", "CAIXA", p["id"],
                  {"data": p["data"], "operador": p["operador"],
                   "como": "visto em lote, sobre o parecer do agente gestor"})
        recusados = len(pedidos) - len(dados)
        flash(f"Visto dado em {len(dados)} caixa(s)."
              + (f" {recusados} ficaram de fora: o seu próprio caixa, ou um que deixou de "
                 "fechar entre a tela e o clique." if recusados else ""), "success")
        return redirect(url_for("gestor_caixas"))

    # ----------------------------------------- o que a leitura pela IA apontou
    #
    # A IA lê o texto mascarado das minutas, R e escrituras e aponta; ela NÃO
    # decide. Quem decide é quem qualifica, aqui: «conferi» tira o apontamento
    # da lista e da tarefa na próxima conferência. Texto que mudar depois volta
    # a ser lido — o «conferi» vale para aquela versão do texto, e só para ela.

    @app.route("/administrativo/gestor/leituras")
    @login_required
    def gestor_leituras():
        """Os apontamentos da leitura que ninguém conferiu ainda. Só LÊ."""
        import gestor_leitura as GL
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            # NUM BANCO EM QUE A LEITURA NUNCA RODOU a tabela não existe, e
            # `achados_vigentes` a criaria — GET não escreve.
            tem = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                              "AND name='ge_leituras'").fetchone()
            itens = GL.achados_vigentes(con) if tem else []
            revisoes = []
            if con.execute("SELECT 1 FROM sqlite_master WHERE name='rv_revisoes'").fetchone():
                import json as _json
                for r in con.execute(
                        """SELECT id, rotulo, resultado_json, graves FROM rv_revisoes
                            WHERE origem = 'AGENTE' AND situacao = 'PRONTA'
                              AND justificado_em IS NULL ORDER BY graves DESC, id"""):
                    achados = _json.loads(r["resultado_json"] or "{}").get("achados") or []
                    if achados:
                        revisoes.append({"id": r["id"], "rotulo": r["rotulo"],
                                         "graves": r["graves"], "achados": achados})
        return render_template("gestor_leituras.html", itens=itens, revisoes=revisoes)

    @app.route("/administrativo/gestor/revisoes/<int:revisao_id>/conferi", methods=["POST"])
    @login_required
    def gestor_revisao_conferida(revisao_id: int):
        """A revisão em lote de um ato passado, conferida por quem qualifica."""
        nota = (request.form.get("nota") or "").strip() or "conferido"
        with db.transaction() as con:
            con.execute("""UPDATE rv_revisoes SET justificativa=?, justificado_por=?,
                               justificado_em=? WHERE id=? AND origem='AGENTE'""",
                        (nota, usuario_nome(), db.now(), revisao_id))
        audit("GESTOR_REVISAO_CONFERIDA", "rv_revisoes", revisao_id, {"nota": nota})
        flash("Revisão conferida. A tarefa sai na próxima conferência.", "success")
        return redirect(url_for("gestor_leituras"))

    @app.route("/administrativo/gestor/leituras/<int:leitura_id>/conferi", methods=["POST"])
    @login_required
    def gestor_leitura_conferida(leitura_id: int):
        """Quem qualifica conferiu o apontamento e o dá por resolvido."""
        import gestor_leitura as GL
        with db.transaction() as con:
            GL.marcar_revisado(con, leitura_id, usuario_nome())
        audit("GESTOR_LEITURA_CONFERIDA", "ge_leituras", leitura_id, {})
        flash("Apontamento conferido. A tarefa sai na próxima conferência.", "success")
        return redirect(url_for("gestor_leituras"))

    # ----------------------------------------- o relatório de erros, por pessoa
    #
    # Pedido do oficial em 06/10/2026: «crie um relatorio de erros, com detalhes
    # e quem praticou, disponivel para o administrador no painel». É SÓ DO ADMIN
    # — diz quem errou, e isso não é tela de balcão. Só lê; a regra e o autor
    # moram em `gestor_erros`.

    def _filtros_dos_erros():
        a = request.args
        return {"desde": (a.get("desde") or "2026-09-10")[:10],
                "ate": (a.get("ate") or "")[:10] or None,
                "pessoa": a.get("pessoa") or None,
                "categoria": a.get("categoria") or None,
                "situacao": a.get("situacao") if a.get("situacao") in
                ("abertos", "resolvidos", "todos") else "abertos"}

    @app.route("/administrativo/gestor/erros")
    @roles_required("ADMIN")
    def gestor_erros():
        import gestor_erros as GER
        filtros = _filtros_dos_erros()
        with db.connect() as con:
            r = GER.relatorio(con, **filtros)
        return render_template("gestor_erros.html", r=r, f=filtros,
                               nao_identificado=GER.NAO_IDENTIFICADO)

    @app.route("/administrativo/gestor/erros.csv")
    @roles_required("ADMIN")
    def gestor_erros_csv():
        import csv
        import io

        from flask import Response

        import gestor_erros as GER
        filtros = _filtros_dos_erros()
        with db.connect() as con:
            r = GER.relatorio(con, **filtros)
        saida = io.StringIO()
        w = csv.writer(saida, delimiter=";")
        w.writerow(["visto em", "gravidade", "tipo", "quem praticou", "como se soube",
                    "ato", "o que é", "detalhe", "situação"])
        for l in r["linhas"]:
            w.writerow([l["visto_em"][:10], l["gravidade"], l["categoria"], l["quem"],
                        l["como"], l["ato"], l["titulo"], l["detalhe"],
                        f"resolvido em {str(l['resolvido_em'])[:10]}" if l["resolvido_em"]
                        else "aberto"])
        audit("GESTOR_ERROS_EXPORTADOS", "ge_achados", None, filtros)
        # O «﻿» é para o Excel abrir os acentos certos.
        return Response("﻿" + saida.getvalue(), mimetype="text/csv; charset=utf-8",
                        headers={"Content-Disposition":
                                 "attachment; filename=relatorio_de_erros.csv"})

    @app.context_processor
    def _erros_no_painel() -> dict:
        """O quadro do painel: quantos erros abertos, por pessoa — só para o ADMIN
        e só no painel geral, para não ler o relatório em toda tela."""
        from flask import session
        try:
            if (request.endpoint or "") != "dashboard" or not session.get("user_id"):
                return {"erros_no_painel": None}
        except RuntimeError:
            return {"erros_no_painel": None}
        try:
            import gestor_erros as GER
            with db.connect() as con:
                papel = con.execute("SELECT role FROM users WHERE id = ?",
                                    (session.get("user_id"),)).fetchone()
                if not papel or papel[0] != "ADMIN":
                    return {"erros_no_painel": None}
                r = GER.relatorio(con, situacao="abertos")
            return {"erros_no_painel": {"abertos": r["abertos"],
                                        "por_pessoa": r["por_pessoa"][:6]}}
        except sqlite3.Error:
            return {"erros_no_painel": None}
