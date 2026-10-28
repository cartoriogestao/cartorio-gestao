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

from flask import abort, flash, redirect, render_template, request, url_for

import csv_seguro as CSVS
import despesas as DP
import despesas_inter as INTER
import despesas_recorrentes as RC

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
        # A TELA NÃO PROMETE O QUE O PROCESSO NÃO FAZ — 27/10/2026. Com «pode
        # agir» desligado (o padrão) o despachante só lê: nada é pago nem
        # conferido, e a tela dizia «roda no próximo minuto».
        if not int(processo.get("pode_agir") or 0):
            flash(f"Pedido registrado, mas o processo {codigo} está sem «pode agir»: "
                  f"o despachante só vai CONFERIR, sem pagar nem baixar nada. Ligue "
                  f"«pode agir» em Automação → {codigo} para ele agir.", "warning")
        elif not int(processo.get("ativo") or 0):
            flash(f"Pedido registrado: o processo {codigo} está desligado na "
                  f"automação, e o pedido roda uma vez no próximo minuto.", "info")
        else:
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
            do_mes = RC.do_mes(con, date.today())
            carregadas = len([d for d in DP.listar(con, situacao=DP.AGUARDANDO)
                              if d["origem"] == RC.ORIGEM])
        return render_template("despesas_lista.html", linhas=linhas, contagem=contagem,
                               situacoes=DP.SITUACOES, situacao=situacao, cfg=cfg,
                               categorias=DP.CATEGORIAS, reais=DP.reais,
                               papel=usuario_papel(), do_mes=do_mes,
                               recorrentes_carregadas=carregadas)

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
                    # Vinda do botão de uma recorrente, a despesa leva a chave do
                    # mês: é isso que tira o mês do aviso (`despesas_recorrentes`).
                    origem, chave = RC.origem_do_formulario(
                        con, f.get("recorrente_id"), f.get("competencia"))
                    novo = DP.cadastrar(
                        con, agora=_agora(), por=usuario_nome(), origem=origem,
                        chave_origem=chave, beneficiario_nome=f.get("beneficiario_nome"),
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
        preenchido: dict = {}
        rid, comp = request.args.get("recorrente_id") or "", request.args.get("competencia") or ""
        if rid.isdigit() and comp:
            with db.connect() as con:
                r = RC.recorrente(con, int(rid))
            if r:
                preenchido = RC.para_o_formulario(r, comp[:7])
        return render_template("despesas_nova.html", f=preenchido, formas=DP.FORMAS,
                               categorias=DP.CATEGORIAS, naturezas=DP.NATUREZAS)

    # ------------------------------------------------- as recorrentes (28/10/2026)

    @app.route("/administrativo/despesas/recorrentes")
    @login_required
    @roles_required(*QUEM_VE)
    def despesas_recorrentes():
        with db.connect() as con:
            linhas = RC.lista(con)
            do_mes = RC.do_mes(con, date.today())
        return render_template("despesas_recorrentes.html", linhas=linhas, do_mes=do_mes,
                               formas=DP.FORMAS, categorias=DP.CATEGORIAS, reais=DP.reais,
                               carrega_sozinho=RC.CARREGA_SOZINHO, papel=usuario_papel())

    def _dados_da_recorrente(f) -> dict:
        dados = {c: f.get(c) for c in RC.CAMPOS}
        dados["valor"] = DP.centavos_da_tela(f.get("valor")) if f.get("valor") else 0
        return dados

    @app.route("/administrativo/despesas/recorrentes/nova", methods=["GET", "POST"])
    @app.route("/administrativo/despesas/recorrentes/<int:recorrente_id>", methods=["GET", "POST"])
    @login_required
    @roles_required(*QUEM_CADASTRA)
    def despesas_recorrente(recorrente_id: int | None = None):
        r = None
        if recorrente_id is not None:
            with db.connect() as con:
                r = RC.recorrente(con, recorrente_id)
            if not r:
                abort(404)
        if request.method == "POST":
            f = request.form
            try:
                with db.transaction() as con:
                    if r:
                        RC.alterar(con, recorrente_id, _dados_da_recorrente(f),
                                   por=usuario_nome(), agora=_agora())
                        rid = recorrente_id
                    else:
                        rid = RC.cadastrar(con, _dados_da_recorrente(f), por=usuario_nome(),
                                           agora=_agora())
            except DP.DespesaError as erro:
                flash(str(erro), "danger")
                return render_template("despesas_recorrente_form.html", f=f, r=r,
                                       formas=DP.FORMAS, categorias=DP.CATEGORIAS)
            audit("DESPESA_RECORRENTE_ALTERADA" if r else "DESPESA_RECORRENTE_CADASTRADA",
                  "dp_recorrentes", rid, {"valor": f.get("valor"), "forma": f.get("forma")})
            flash("Recorrente gravada. Ela vale dos próximos meses em diante.", "success")
            return redirect(url_for("despesas_recorrentes"))
        if r:
            f = {**r, "valor": DP.reais(int(r["valor"])) if r["valor"] else ""}
        else:
            f = {"primeiro_mes": RC.mes(date.today()), "antecedencia_dias": RC.ANTECEDENCIA_PADRAO,
                 "forma": DP.PIX_CHAVE}
        return render_template("despesas_recorrente_form.html", f=f, r=r, formas=DP.FORMAS,
                               categorias=DP.CATEGORIAS)

    @app.route("/administrativo/despesas/recorrentes/<int:recorrente_id>/<acao>",
               methods=["POST"])
    @login_required
    @roles_required(*QUEM_CADASTRA)
    def despesas_recorrente_acao(recorrente_id: int, acao: str):
        if acao not in ("encerrar", "reativar"):
            abort(404)
        with db.transaction() as con:
            if not RC.recorrente(con, recorrente_id):
                abort(404)
            if acao == "encerrar":
                RC.encerrar(con, recorrente_id, por=usuario_nome(), agora=_agora())
            else:
                RC.reativar(con, recorrente_id)
        audit(f"DESPESA_RECORRENTE_{acao.upper()}", "dp_recorrentes", recorrente_id, {})
        flash("Recorrente encerrada: não avisa nem carrega mais." if acao == "encerrar"
              else "Recorrente reativada.", "success")
        return redirect(url_for("despesas_recorrentes"))

    @app.route("/administrativo/despesas/recorrentes/carregar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_CADASTRA)
    def despesas_recorrentes_carregar():
        """O mesmo que o processo DESPESAS_RECORRENTES faz de manhã, agora."""
        try:
            with db.transaction() as con:
                novas = RC.gerar(con, hoje=date.today(), agora=_agora(), por=usuario_nome())
        except DP.DespesaError as erro:
            flash(f"Não carreguei: {erro}", "danger")
            return redirect(url_for("despesas_recorrentes"))
        for i in novas:
            audit("DESPESA_RECORRENTE_CARREGADA", "dp_despesas", i, {})
        flash(f"{len(novas)} despesa(s) do mês carregada(s), esperando a autorização." if novas
              else "Nenhuma despesa por Pix a carregar agora.", "success" if novas else "info")
        return redirect(url_for("despesas_lista", situacao=DP.AGUARDANDO) if novas
                        else url_for("despesas_recorrentes"))

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
            # pelo `csv_seguro`: tudo entre aspas e fórmula desarmada (o nome do
            # favorecido e a descrição vêm de quem cadastrou)
            return CSVS.resposta(f"despesas-{mes}.csv", DP.CABECALHO_DO_CSV,
                                 DP.linhas_do_csv(rel))
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
            except RuntimeError as erro:
                # O cofre da automação trancado ou ainda não criado — 27/10/2026:
                # `CofreTrancado` é `RuntimeError` e virava HTTP 500 justamente
                # no passo «grave de novo a credencial» da instalação.
                import automacao_cofre as COFRE  # type: ignore
                if not isinstance(erro, COFRE.CofreError):
                    raise
                flash("A credencial NÃO foi gravada: o cofre da automação está "
                      "trancado ou ainda não foi criado. Abra o cofre (Automação → "
                      f"Cofre, na máquina do servidor) e grave de novo. ({erro})",
                      "danger")
            return redirect(url_for("despesas_configuracao"))
        with db.connect() as con:
            cfg = DP.configuracao(con)
        return render_template("despesas_configuracao.html", cfg=cfg, rotulos=DP.ROTULOS,
                               ambientes=DP.AMBIENTES, credencial=INTER.resumo_da_credencial())
