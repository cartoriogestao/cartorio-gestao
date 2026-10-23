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
from bd_nativo import banco
from seguranca_web import PRATICA  # M2 (LX11): o AUDITOR vê e não grava
from seguranca_web import numero_digitado  # LD13: o número que a tela mandou


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
    @roles_required(*PRATICA)
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
        for r in banco(con).ler(
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
            prontos, com_pontos = _caixas_para_o_visto(con)
        return render_template("gestor_caixas.html", prontos=prontos,
                               com_pontos=com_pontos, eu=usuario_nome())

    @app.route("/administrativo/gestor/caixas/visto", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def gestor_caixas_visto():
        """Dá o visto nos marcados — só nos que continuam fechando agora."""
        # Marcado que não é número («²», dígitos demais) é como não marcado.
        pedidos = {n for n in map(numero_digitado, request.form.getlist("caixa_id"))
                   if n is not None}
        if not pedidos:
            flash("Marque os caixas que você conferiu.", "danger")
            return redirect(url_for("gestor_caixas"))
        eu, quem = usuario_nome(), usuario_id()
        with db.transaction() as con:
            prontos, _ = _caixas_para_o_visto(con)
            # A CONTA SE REFAZ NA HORA DO CLIQUE: um lançamento mexido entre a
            # tela e o botão tira o caixa do lote, em vez de levar visto calado.
            dados = [p for p in prontos if p["id"] in pedidos and p["operador"] != eu]
            for p in dados:
                banco(con).escrever("""UPDATE cx_caixas SET conferido_por=%s, conferido_em=%s
                                WHERE id=%s AND conferido_em IS NULL""",
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
            # NUM BANCO EM QUE A LEITURA NUNCA RODOU a tabela não existe, e
            # `achados_vigentes` a criaria — GET não escreve.
            tem = banco(con).tem_tabela("ge_leituras")
            itens = GL.achados_vigentes(con) if tem else []
            revisoes = []
            if banco(con).tem_tabela("rv_revisoes"):
                import json as _json
                for r in banco(con).ler(
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
    @roles_required(*PRATICA)
    def gestor_revisao_conferida(revisao_id: int):
        """A revisão em lote de um ato passado, conferida por quem qualifica."""
        nota = (request.form.get("nota") or "").strip() or "conferido"
        with db.transaction() as con:
            banco(con).escrever("""UPDATE rv_revisoes SET justificativa=%s, justificado_por=%s,
                               justificado_em=%s WHERE id=%s AND origem='AGENTE'""",
                                (nota, usuario_nome(), db.now(), revisao_id))
        audit("GESTOR_REVISAO_CONFERIDA", "rv_revisoes", revisao_id, {"nota": nota})
        flash("Revisão conferida. A tarefa sai na próxima conferência.", "success")
        return redirect(url_for("gestor_leituras"))

    @app.route("/administrativo/gestor/leituras/<int:leitura_id>/conferi", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
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
                papel = banco(con).um("SELECT role FROM users WHERE id = %s",
                                      (session.get("user_id"),))
                if not papel or papel["role"] != "ADMIN":
                    return {"erros_no_painel": None}
                r = GER.relatorio(con, situacao="abertos")
            return {"erros_no_painel": {"abertos": r["abertos"],
                                        "por_pessoa": r["por_pessoa"][:6]}}
        except sqlite3.Error:
            return {"erros_no_painel": None}

    # --------------------------------------- o relatório anual do uso de IA
    #
    # LF01 (19/10/2026): o Código de Normas do MA (art. 170, § 4º) pede um
    # relatório anual à COGEX. É SÓ DO ADMIN — leva os dados dos fornecedores e
    # os incidentes, e quem o assina é o oficial. A montagem mora em
    # `ia_relatorio`; o registro, em `ia_uso`; o catálogo, em `ia_catalogo`.
    # O endereço da especificação (`/gestor/relatorio-ia`) e o da casa
    # (`/administrativo/gestor/...`) levam à mesma tela.

    def _contexto_da_ia() -> dict:
        import ia_catalogo as CAT
        import ia_uso as USO
        return {"aviso": CAT.AVISO_DO_TEXTO_OFICIAL, "requisito": CAT.REQUISITO_DO_FORNECEDOR,
                "nome_da_finalidade": CAT.nome_da_finalidade, "catalogo": CAT.CATALOGO,
                "respostas": USO.RESPOSTAS, "retencoes": USO.RETENCOES}

    def _relatorio_ia(papel: bool):
        import ia_relatorio as IAR
        ano = IAR.ano_pedido(request.args.get("ano"), IAR.hoje())
        with db.connect() as con:
            r = IAR.montar(con, ano, pasta_de_dados=app.config.get("DATA_DIR"),
                           serventia=IAR.serventia_de(con))
        return ano, render_template("gestor_relatorio_ia.html", r=r, papel=papel,
                                    **_contexto_da_ia())

    @app.route("/gestor/relatorio-ia")
    @app.route("/administrativo/gestor/relatorio-ia")
    @roles_required("ADMIN")
    def gestor_relatorio_ia():
        """A página do relatório, pronta para imprimir. Só LÊ."""
        return _relatorio_ia(papel=False)[1]

    @app.route("/administrativo/gestor/relatorio-ia/papel")
    @roles_required("ADMIN")
    def gestor_relatorio_ia_papel():
        """O mesmo HTML em PDF, pelo caminho de impressão da casa (Chrome)."""
        from flask import Response

        import impressao_pdf as PDFIMP
        ano, html = _relatorio_ia(papel=True)
        try:
            conteudo, tipo, arquivo, entrega = PDFIMP.arquivo_de_html(
                html, nome=f"relatorio-ia-{ano}", formato=request.args.get("formato"),
                get_setting=db.get_setting)
        except PDFIMP.PdfError as erro:
            flash(f"{erro} Use «Imprimir» na página do relatório.", "warning")
            return redirect(url_for("gestor_relatorio_ia", ano=ano))
        audit("GESTOR_RELATORIO_IA_PAPEL", None, None, {"ano": ano})
        return Response(conteudo, mimetype=tipo,
                        headers={"Content-Disposition": f'{entrega}; filename="{arquivo}"'})

    @app.route("/administrativo/gestor/ia")
    @roles_required("ADMIN")
    def gestor_ia():
        """Os incidentes e os dados dos fornecedores. Só LÊ."""
        import agente_provedores as AP
        import ia_uso as USO
        with db.connect() as con:
            incidentes = USO.incidentes(con)
            fornecedores = USO.fornecedores(con)
        provedores = [{"id": p, "nome": d["nome"]} for p, d in AP.PROVEDORES.items()]
        return render_template("gestor_ia.html", incidentes=incidentes,
                               fornecedores=fornecedores, provedores=provedores,
                               reserva_sem_mascara=db.get_setting(
                                   _CHAVE_RESERVA_SEM_MASCARA, "0") == "1",
                               **_contexto_da_ia())

    # A CAUTELA DA LEITURA DIÁRIA (LX13, A6). O «sem máscara» de 06/10/2026 foi
    # decidido com o Claude como provedor; quando a leitura cai noutro, vai
    # mascarada até o oficial dizer o contrário AQUI — e a mudança fica na
    # auditoria, com quem mudou. A chave mora em `gestor_leitura`, que a lê.
    from gestor_leitura import CHAVE_RESERVA_SEM_MASCARA as _CHAVE_RESERVA_SEM_MASCARA

    @app.route("/administrativo/gestor/ia/cautelas", methods=["POST"])
    @roles_required("ADMIN")
    def gestor_ia_cautelas():
        """Grava «permitir sem máscara no provedor reserva» (padrão: desligado)."""
        valor = "1" if request.form.get("reserva_sem_mascara") == "1" else "0"
        db.set_settings({_CHAVE_RESERVA_SEM_MASCARA: valor})
        audit("GESTOR_IA_CAUTELA", "settings", None,
              {"chave": _CHAVE_RESERVA_SEM_MASCARA, "valor": valor})
        flash("Provedor reserva liberado a ler SEM máscara." if valor == "1" else
              "Provedor reserva lê com máscara (o padrão).", "success")
        return redirect(url_for("gestor_ia"))

    @app.route("/administrativo/gestor/ia/incidente", methods=["POST"])
    @roles_required("ADMIN")
    def gestor_ia_incidente():
        """Grava um incidente ou falha do uso de IA."""
        import ia_uso as USO
        campos = {c: request.form.get(c) or "" for c in USO.CAMPOS_DO_INCIDENTE}
        try:
            with db.transaction() as con:
                novo = USO.registrar_incidente(con, registrado_por=usuario_nome(),
                                               agora=db.now(), **campos)
        except USO.IncidenteError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("gestor_ia"))
        audit("GESTOR_IA_INCIDENTE", "ia_incidentes", novo, {"sistema": campos["sistema"]})
        flash("Incidente registrado. Ele entra no relatório anual do uso de IA.", "success")
        return redirect(url_for("gestor_ia"))

    @app.route("/administrativo/gestor/ia/fornecedor", methods=["POST"])
    @roles_required("ADMIN")
    def gestor_ia_fornecedor():
        """Grava os dados de um fornecedor, como o oficial os conferiu."""
        import agente_provedores as AP
        import ia_uso as USO
        provedor = (request.form.get("provedor") or "").strip().lower()
        if provedor not in AP.PROVEDORES:
            flash("Provedor desconhecido.", "danger")
            return redirect(url_for("gestor_ia"))
        with db.transaction() as con:
            USO.gravar_fornecedor(con, provedor, request.form, por=usuario_nome(),
                                  agora=db.now())
        audit("GESTOR_IA_FORNECEDOR", "ia_fornecedores", None, {"provedor": provedor})
        flash("Dados do fornecedor gravados.", "success")
        return redirect(url_for("gestor_ia"))

    @app.context_processor
    def _relatorio_ia_no_painel() -> dict:
        """Em janeiro, o painel do ADMIN lembra o relatório de IA do ano anterior."""
        from flask import session
        try:
            if (request.endpoint or "") != "dashboard" or not session.get("user_id"):
                return {"relatorio_ia_no_painel": None}
        except RuntimeError:
            return {"relatorio_ia_no_painel": None}
        import ia_relatorio as IAR
        aviso = IAR.aviso_do_painel(IAR.hoje())
        if aviso is None:
            return {"relatorio_ia_no_painel": None}
        try:
            with db.connect() as con:
                papel = banco(con).um("SELECT role FROM users WHERE id = %s",
                                      (session.get("user_id"),))
        except sqlite3.Error:
            return {"relatorio_ia_no_painel": None}
        if not papel or papel["role"] != "ADMIN":
            return {"relatorio_ia_no_painel": None}
        return {"relatorio_ia_no_painel": aviso}
