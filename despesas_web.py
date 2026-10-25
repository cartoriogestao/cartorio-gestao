"""As telas das despesas — cadastrar, autorizar, pagar, conferir e o relatório do mês.

QUEM FAZ O QUÊ (decisões do oficial, 24/10/2026)
    - Ver: ADMIN, MANAGER e AUDITOR.
    - Cadastrar e cancelar: ADMIN e MANAGER.
    - Autorizar, devolver à autorização, registrar pago fora do banco,
      configurar e cadastrar a credencial do Inter: só o ADMIN.

«PAGAR AGORA» E «CONFERIR O EXTRATO»
    Quando o hub da automação está instalado, quem paga é o despachante
    (`despesas_automacao`, processo DESPESAS_PAGAR). O botão da tela existe
    para não esperar a próxima rodada, e faz a mesma coisa pelo mesmo
    caminho (`despesas_inter.pagar`) — sem segurar transação do banco durante
    a conversa com o Inter.
"""
from __future__ import annotations

from datetime import date, datetime

from flask import Response, abort, flash, redirect, render_template, request, url_for

import despesas as DP
import despesas_inter as INTER

QUEM_VE = ("ADMIN", "MANAGER", "AUDITOR")
QUEM_CADASTRA = ("ADMIN", "MANAGER")


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_nome = app.extensions["usuario_nome"]
    usuario_papel = app.extensions["usuario_papel"]
    usuario_id = app.extensions.get("usuario_id", lambda: None)
    archive_root = app.extensions.get("archive_root")
    app.extensions.setdefault("tela_do_anexo", {})["DESPESA"] = ("despesas_ficha",)

    def _agora() -> datetime:
        return datetime.now().astimezone().replace(microsecond=0)

    def _ficha(despesa_id: int):
        return redirect(url_for("despesas_ficha", despesa_id=despesa_id))

    def _pasta():
        return (archive_root() / "despesas") if archive_root else None

    def _pela_automacao(codigo: str) -> bool:
        """Com o cofre da automação instalado, a tela não lê o segredo: pede a rodada.

        O cofre recusa `ler` dentro de requisição web (sessão 10, 24/10/2026).
        Então «pagar agora» e «conferir agora» viram um pedido ao despachante,
        que roda no próximo minuto, fora do servidor web. Sem o cofre, a tela
        fala com o Inter direto (credencial no arquivo provisório).
        """
        if INTER._cofre() is None:
            return False
        import automacao  # type: ignore
        with db.transaction() as con:
            processo = automacao.por_codigo(con, codigo)
            if not processo:
                raise DP.DespesaError(f"O processo {codigo} não está cadastrado na automação. "
                                      f"Cadastre-o lá (Automação → processos).")
            automacao.pedir_rodada(con, int(processo["id"]), usuario=usuario_nome())
        flash("Pedido ao despachante da automação: roda no próximo minuto.", "info")
        return True

    @app.route("/administrativo/despesas")
    @login_required
    @roles_required(*QUEM_VE)
    def despesas_lista():
        situacao = request.args.get("situacao") or None
        if situacao and situacao not in DP.SITUACOES:
            abort(400)
        with db.connect() as con:
            linhas = DP.listar(con, situacao=situacao)
            contagem = DP.contagem(con)
            cfg = DP.configuracao(con)
        return render_template("despesas_lista.html", linhas=linhas, contagem=contagem,
                               situacoes=DP.SITUACOES, situacao=situacao, cfg=cfg,
                               categorias=DP.CATEGORIAS, reais=DP.reais,
                               papel=usuario_papel())

    @app.route("/administrativo/despesas/nova", methods=["GET", "POST"])
    @login_required
    @roles_required(*QUEM_CADASTRA)
    def despesas_nova():
        f = request.form
        if request.method == "POST":
            arquivo = request.files.get("documento")
            anexo = (arquivo.filename, arquivo.read()) if arquivo and arquivo.filename else None
            try:
                with db.transaction() as con:
                    novo = DP.cadastrar(
                        con, agora=_agora(), por=usuario_nome(), origem="MANUAL",
                        chave_origem=None, beneficiario_nome=f.get("beneficiario_nome"),
                        beneficiario_documento=f.get("beneficiario_documento"),
                        valor_centavos=DP.centavos_da_tela(f.get("valor")),
                        vencimento=f.get("vencimento"), forma=f.get("forma") or "",
                        codigo=f.get("codigo"), descricao=f.get("descricao"),
                        categoria=f.get("categoria") or "",
                        documento_especie=f.get("documento_especie"),
                        documento_numero=f.get("documento_numero"), anexo=anexo,
                        pasta_anexos=_pasta(), usuario_id=usuario_id())
            except DP.DespesaError as erro:
                flash(str(erro), "danger")
                return render_template("despesas_nova.html", f=f, formas=DP.FORMAS,
                                       categorias=DP.CATEGORIAS, naturezas=DP.NATUREZAS)
            audit("DESPESA_CADASTRADA", "dp_despesas", novo,
                  {"valor": f.get("valor"), "categoria": f.get("categoria")})
            flash("Despesa cadastrada. Ela espera a autorização do oficial.", "success")
            return _ficha(novo)
        return render_template("despesas_nova.html", f={}, formas=DP.FORMAS,
                               categorias=DP.CATEGORIAS, naturezas=DP.NATUREZAS)

    @app.route("/administrativo/despesas/<int:despesa_id>")
    @login_required
    @roles_required(*QUEM_VE)
    def despesas_ficha(despesa_id: int):
        with db.connect() as con:
            d = DP.despesa(con, despesa_id)
            if not d:
                abort(404)
            rastro = DP.eventos(con, despesa_id)
            arquivos = DP.anexos(con, despesa_id)
            cfg = DP.configuracao(con)
        return render_template("despesas_ficha.html", d=d, rastro=rastro, arquivos=arquivos,
                               situacoes=DP.SITUACOES, formas=DP.FORMAS,
                               categorias=DP.CATEGORIAS, naturezas=DP.NATUREZAS,
                               tetos=DP.tetos(cfg), cfg=cfg, reais=DP.reais,
                               papel=usuario_papel(), hoje=date.today().isoformat())

    @app.route("/administrativo/despesas/<int:despesa_id>/<acao>", methods=["POST"])
    @login_required
    @roles_required(*QUEM_CADASTRA)
    def despesas_acao(despesa_id: int, acao: str):
        f, papel = request.form, usuario_papel()
        try:
            if acao in ("autorizar", "devolver", "cancelar", "pago_fora", "documento"):
                with db.transaction() as con:
                    if acao == "autorizar":
                        DP.autorizar(con, despesa_id, agora=_agora(), por=usuario_nome(),
                                     papel=papel, acima_do_teto=f.get("acima_do_teto") == "1",
                                     motivo_divergencia=f.get("motivo"))
                    elif acao == "devolver":
                        DP.devolver(con, despesa_id, agora=_agora(), por=usuario_nome(),
                                    papel=papel, motivo=f.get("motivo"))
                    elif acao == "cancelar":
                        DP.cancelar(con, despesa_id, agora=_agora(), por=usuario_nome(),
                                    papel=papel, motivo=f.get("motivo"))
                    elif acao == "pago_fora":
                        DP.registrar_pago_fora(con, despesa_id, agora=_agora(),
                                               hoje=date.today().isoformat(),
                                               por=usuario_nome(), papel=papel,
                                               data_pagamento=f.get("data_pagamento"))
                    else:
                        arquivo = request.files.get("documento")
                        if not arquivo or not arquivo.filename:
                            raise DP.DespesaError("Escolha o arquivo.")
                        DP.guardar_anexo(con, despesa_id, nome_arquivo=arquivo.filename,
                                         conteudo=arquivo.read(), pasta=_pasta(),
                                         usuario_id=usuario_id(), agora=db.now())
            elif acao in ("pagar", "atualizar"):
                if papel != "ADMIN":
                    raise DP.DespesaError("Só o oficial manda pagar ou consulta o banco.")
                if _pela_automacao("DESPESAS_PAGAR"):
                    return _ficha(despesa_id)
                with db.connect() as con:
                    cfg = DP.configuracao(con)
                cliente = INTER.cliente_da_casa(cfg)
                funcao = INTER.pagar if acao == "pagar" else INTER.atualizar
                r = funcao(db, despesa_id, cliente=cliente, por=usuario_nome())
                flash(r.get("mensagem") or DP.SITUACOES.get(r.get("situacao"), ""), "info")
            else:
                abort(404)
        except (DP.DespesaError, INTER.InterError) as erro:
            flash(str(erro), "danger")
            return _ficha(despesa_id)
        audit(f"DESPESA_{acao.upper()}", "dp_despesas", despesa_id, {"papel": papel})
        if acao not in ("pagar", "atualizar"):
            flash("Feito.", "success")
        return _ficha(despesa_id)

    @app.route("/administrativo/despesas/conciliar", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def despesas_conciliar():
        try:
            if _pela_automacao("DESPESAS_CONCILIAR"):
                return redirect(url_for("despesas_lista"))
            with db.connect() as con:
                cfg = DP.configuracao(con)
            r = INTER.conciliar(db, cliente=INTER.cliente_da_casa(cfg), por=usuario_nome())
        except (INTER.InterError, DP.DespesaError) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("despesas_lista"))
        audit("DESPESAS_CONCILIADAS", "dp_despesas", None,
              {"conciliadas": len(r["conciliadas"]), "sem_despesa": len(r["sem_despesa"])})
        flash(f"{len(r['conciliadas'])} despesa(s) conferida(s) no extrato; "
              f"{len(r['sem_despesa'])} débito(s) sem despesa cadastrada.", "info")
        return redirect(url_for("despesas_lista"))

    @app.route("/administrativo/despesas/pagar-autorizadas", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def despesas_pagar_autorizadas():
        """A rodada do despachante, pedida pela tela — para não esperar o próximo tique."""
        try:
            if _pela_automacao("DESPESAS_PAGAR"):
                return redirect(url_for("despesas_lista"))
            with db.connect() as con:
                cfg = DP.configuracao(con)
            r = INTER.pagar_autorizadas(db, cliente=INTER.cliente_da_casa(cfg),
                                        por=usuario_nome())
        except (INTER.InterError, DP.DespesaError) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("despesas_lista"))
        audit("DESPESAS_PAGAMENTO_EM_LOTE", "dp_despesas", None,
              {k: len(v) for k, v in r.items()})
        flash(f"{len(r['pagas'])} enviada(s) ao Inter, {len(r['esperam'])} esperando "
              f"(teto ou configuração), {len(r['falharam'])} recusada(s).", "info")
        return redirect(url_for("despesas_lista"))

    @app.route("/administrativo/despesas/relatorio")
    @login_required
    @roles_required(*QUEM_VE)
    def despesas_relatorio():
        mes = (request.args.get("mes") or date.today().isoformat()[:7]).strip()
        try:
            with db.connect() as con:
                rel = DP.relatorio_do_mes(con, mes)
        except DP.DespesaError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("despesas_relatorio"))
        if request.args.get("formato") == "csv":
            audit("DESPESAS_RELATORIO_EXPORTADO", "dp_despesas", None, {"mes": mes})
            return Response(DP.relatorio_csv(rel).encode("utf-8-sig"), mimetype="text/csv",
                            headers={"Content-Disposition":
                                     f'attachment; filename="despesas-{mes}.csv"'})
        return render_template("despesas_relatorio.html", rel=rel, mes=mes,
                               siaferj=DP.lancamentos_para_o_siaferj(rel),
                               categorias=DP.CATEGORIAS, naturezas=DP.NATUREZAS,
                               situacoes=DP.SITUACOES, reais=DP.reais)

    @app.route("/administrativo/despesas/configuracao", methods=["GET", "POST"])
    @login_required
    @roles_required("ADMIN")
    def despesas_configuracao():
        if request.method == "POST":
            f = request.form
            try:
                if f.get("acao") == "credencial":
                    def _ler(nome: str) -> str:
                        arq = request.files.get(nome)
                        return arq.read().decode("utf-8", "replace") if arq and arq.filename else ""
                    resumo = INTER.gravar_credencial({
                        "client_id": f.get("client_id"), "client_secret": f.get("client_secret"),
                        "crt_pem": _ler("crt"), "key_pem": _ler("key"),
                        "conta_corrente": f.get("conta_corrente")})
                    audit("DESPESAS_CREDENCIAL_INTER_GRAVADA", "settings", None,
                          {"valido_ate": resumo["valido_ate"], "onde": resumo["onde"]})
                    flash(f"Credencial do Inter gravada ({resumo['onde']}), certificado "
                          f"válido até {resumo['valido_ate']}.", "success")
                else:
                    with db.transaction() as con:
                        mudou = DP.gravar_configuracao(con, f)
                    audit("DESPESAS_CONFIGURACAO_ALTERADA", "settings", None,
                          {k: {"de": de, "para": para} for k, (de, para) in mudou.items()})
                    flash("Configuração gravada." if mudou else "Nada mudou.", "success")
            except DP.DespesaError as erro:
                flash(str(erro), "danger")
            return redirect(url_for("despesas_configuracao"))
        with db.connect() as con:
            cfg = DP.configuracao(con)
        return render_template("despesas_configuracao.html", cfg=cfg, rotulos=DP.ROTULOS,
                               ambientes=DP.AMBIENTES, credencial=INTER.resumo_da_credencial())
