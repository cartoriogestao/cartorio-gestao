"""As telas das despesas — cadastrar, autorizar, pagar, conferir e o relatório do mês.

QUEM FAZ O QUÊ (decisões do oficial, 24/10/2026 e 28/10/2026)
    - Ver: ADMIN, MANAGER e AUDITOR.
    - Cadastrar: todos (28/10/2026, «libere o acesso para cadastramento de
      despesas para todos usuários»). O USER vê só as que ELE cadastrou — a
      lista inteira traz salários e honorários, e o pedido foi cadastrar, não
      ver. Ele também não abre as recorrentes nem o relatório do mês.
    - Cancelar e cuidar das recorrentes: ADMIN e MANAGER.
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

import logging
from datetime import date, datetime
from io import BytesIO

from flask import (
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

import cofre_do_titular as COT
import csv_seguro as CSVS
import despesas as DP
import despesas_comprovante as DC
import despesas_documento as DD
import despesas_fluxo as DF
import despesas_inter as INTER
import despesas_previsao as DV
import despesas_recorrentes as RC
import faturamento_portal as FP
import serventia as SERV
import titular_privado as TP

_LOG = logging.getLogger("cartorio.despesas_web")

# A frase da leitura recusada (ver `despesas_ler_codigo`).
CODIGO_NAO_LIDO = ("Não foi possível ler este código. Cole o código completo: a linha "
                   "digitável do boleto (44, 47 ou 48 dígitos), o Pix copia e cola ou a chave Pix.")
# A frase da leitura de documento ou anexo recusada (ver `despesas_ler_documento`).
DOCUMENTO_NAO_LIDO = ("Não foi possível ler o QR ou o código de barras deste documento. Use "
                      "PDF (até 12 páginas, sem senha), PNG ou JPG de até 15 MB, ou cole o código "
                      "à mão. O detalhe ficou no registro do servidor.")

QUEM_CADASTRA = ("ADMIN", "MANAGER", "USER")


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_nome = app.extensions["usuario_nome"]
    so_o_titular, e_o_titular = TP.guarda(app, db)
    # O ANEXO TAMBÉM (31/10/2026): a régua de `tela_do_anexo` só olha o papel, e o recibo da
    # folha abriria pelo número na barra para quem é ADMIN sem ser o titular.
    app.extensions["dono_do_anexo"]["DESPESA"] = lambda _anexo: e_o_titular()
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
    @roles_required(*QUEM_CADASTRA)
    def despesas_lista():
        # QUEM SÓ CADASTRA CAI NO FORMULÁRIO (31/10/2026): a lista é do titular.
        if not e_o_titular():
            return redirect(url_for("despesas_nova"))
        situacao = request.args.get("situacao") or None
        if situacao and situacao not in DP.SITUACOES:
            abort(400)
        with db.connect() as con:
            linhas = DP.listar(con, situacao=situacao)
            contagem = DP.contagem(con)
            cfg = DP.configuracao(con)
            do_mes = RC.do_mes(con, date.today())
            carregadas = len(
                [d for d in DP.listar(con, situacao=DP.AGUARDANDO) if d["origem"] == RC.ORIGEM])
            a_autorizar = DP.para_autorizar(con)
            em_duvida = DP.recebedor_em_duvida(con)
            quadro, quadro_falhou = None, False
            quadro_trancado = not TP.esta_aberto(db)
            # O quadro é conta de outros módulos: se ele quebrar, a tela de autorizar
            # e pagar continua de pé, e diz que a conta não saiu em vez de mostrar zero.
            try:
                quadro = None if quadro_trancado else DV.quadro_do_mes(con, date.today())
            except Exception:  # noqa: BLE001
                _LOG.exception("o quadro do mês não saiu")
                quadro_falhou = True
            balanco = DP.balanco(con, date.today().isoformat(), do_mes)
            cns=FP.cns_da_casa(con)
            conferencia_portal=FP.conferencia(con,DV._mes_anterior(_agora().date()),cns=cns) if len(cns)==6 else None
        return render_template("despesas_lista.html", linhas=linhas, contagem=contagem,
                               situacoes=DP.SITUACOES, situacao=situacao, cfg=cfg,
                               categorias=DP.CATEGORIAS, reais=DP.reais,
                               papel=usuario_papel(), do_mes=do_mes,
                               recorrentes_carregadas=carregadas, a_autorizar=a_autorizar,
                               balanco=balanco, em_duvida=em_duvida, quadro=quadro,
                               quadro_falhou=quadro_falhou, quadro_trancado=quadro_trancado,
                               formas=DP.FORMAS, revisao_pagamento=DF.revisao,
                               conferencia_portal=conferencia_portal)

    @app.route('/administrativo/despesas/faturamento-portal',methods=['POST'])
    @login_required
    @roles_required('ADMIN')
    @so_o_titular
    def despesas_importar_faturamento():
        arquivo=request.files.get('relatorio')
        try:
            if not arquivo: raise DP.DespesaError('Escolha o XLSX de faturamento exportado do Portal do Selo.')
            if not archive_root: raise DP.DespesaError('A pasta de documentos nao esta configurada.')
            with db.transaction() as con:
                feito=FP.registrar(con,arquivo.read(FP.MAX_BYTES+1),cns=FP.cns_da_casa(con),
                    pasta=archive_root()/'faturamento_portal',por=usuario_nome(),usuario_id=usuario_id(),agora=db.now())
        except (DP.DespesaError,ValueError) as erro:
            flash(str(erro),'danger')
        else:
            flash(f"Referencia de {feito['competencia']} importada: bruto R$ {DP.reais(feito['bruto'])}, "
                  f"FERJ R$ {DP.reais(feito['ferj'])}, liquido R$ {DP.reais(feito['liquido'])}. "
                  'Original e autoria preservados; nenhum selo ou lancamento de receita foi criado.','success')
        return redirect(url_for('despesas_lista')+'#faturamento-portal')

    @app.route("/administrativo/despesas/ler-codigo", methods=["POST"])
    @login_required
    @roles_required(*QUEM_CADASTRA)
    def despesas_ler_codigo():
        # So calcula o texto enviado; nao le despesas, credenciais ou o banco Inter.
        try:
            return jsonify(DF.ler_codigo(request.form.get('codigo'), hoje=_agora().date()))
        except DP.DespesaError as erro:
            # O TEXTO DA EXCEÇÃO NÃO VAI NO JSON (CodeQL py/stack-trace-exposure, alerta #301,
            # 04/11/2026): a frase da tela é fixa, e o detalhe fica no registro do servidor.
            _LOG.info("código de pagamento recusado: %s", erro)
            return jsonify(erro=CODIGO_NAO_LIDO), 400

    @app.route('/administrativo/despesas/ler-documento', methods=['POST'])
    @login_required
    @roles_required(*QUEM_CADASTRA)
    def despesas_ler_documento():
        arquivo = request.files.get('documento')
        if not arquivo:
            return jsonify(erro='Escolha o documento da despesa.'), 400
        try:
            return jsonify(DD.ler(arquivo.read(DD.MAX_BYTES+1),hoje=_agora().date()))
        except DP.DespesaError as erro:
            # Frase fixa na tela, detalhe no registro (CodeQL #302, como o #301).
            _LOG.info("documento de despesa não lido: %s", erro)
            return jsonify(erro=DOCUMENTO_NAO_LIDO), 400

    @app.route('/administrativo/despesas/<int:despesa_id>/ler-anexo/<int:anexo_id>',methods=['POST'])
    @login_required
    @roles_required('ADMIN')
    @so_o_titular
    def despesas_ler_anexo(despesa_id: int, anexo_id: int):
        import hashlib
        from pathlib import Path
        with db.connect() as con:
            anexo = next((a for a in DP.anexos(con,despesa_id) if int(a['id'])==anexo_id),None)
        if not anexo: abort(404)
        try:
            raiz = _pasta()
            caminho = Path(anexo['stored_path']).resolve()
            if not raiz or not caminho.is_relative_to(raiz.resolve()): abort(404)
            with caminho.open('rb') as arquivo: conteudo=arquivo.read(DD.MAX_BYTES+1)
            if anexo.get('sha256') and hashlib.sha256(conteudo).hexdigest()!=anexo['sha256']:
                raise DP.DespesaError('O arquivo difere do anexo registrado. Confira o documento antes de ler.')
            resposta=DD.ler(conteudo,hoje=_agora().date())
        except (OSError,DP.DespesaError) as erro:
            # Frase fixa na tela, detalhe no registro (CodeQL #303, como o #301).
            _LOG.info("anexo %s da despesa %s não lido: %s", anexo_id, despesa_id, erro)
            return jsonify(erro=DOCUMENTO_NAO_LIDO),400
        audit('DESPESA_ANEXO_LIDO','dp_despesas',despesa_id,
              {'anexo_id':anexo_id,'sha256':resposta['sha256'],'codigos':len(resposta['opcoes'])})
        return jsonify(resposta)

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
                    origem, chave = ("MANUAL", None) if not e_o_titular() else \
                        RC.origem_do_formulario(con, f.get("recorrente_id"), f.get("competencia"))
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
                        pasta_anexos=_pasta(), usuario_id=usuario_id(),
                        contato_email=f.get("contato_email"),
                        contato_whatsapp=f.get("contato_whatsapp"))
            except DP.DespesaError as erro:
                flash(str(erro), "danger")
                return render_template("despesas_nova.html", f=f, formas=DP.FORMAS,
                                       categorias=DP.CATEGORIAS, naturezas=DP.NATUREZAS)
            audit("DESPESA_CADASTRADA", "dp_despesas", novo,
                  {"valor": f.get("valor"), "categoria": f.get("categoria")})
            flash("Despesa cadastrada. Ela espera a autorização do oficial.", "success")
            # Quem só cadastra não abre a ficha, nem a que acabou de gravar.
            return _ficha(novo) if e_o_titular() else redirect(url_for("despesas_nova"))
        preenchido: dict = {}
        rid, comp = request.args.get("recorrente_id") or "", request.args.get("competencia") or ""
        darf = request.args.get("carne_leao") or ""
        if darf and e_o_titular():
            try:
                with db.connect() as con:
                    preenchido = DV.formulario_do_darf(con, darf)
            except DP.DespesaError as erro:
                flash(str(erro), "warning")
        elif request.args.get("iss") and e_o_titular():
            try:
                with db.connect() as con:
                    preenchido = DV.formulario_do_iss(
                        con, request.args["iss"],
                        municipio=SERV.dados(db.get_settings).get("ri_cidade") or "")
            except DP.DespesaError as erro:
                flash(str(erro), "warning")
        elif rid.isdigit() and comp and e_o_titular():
            with db.connect() as con:
                r = RC.recorrente(con, int(rid))
                feriados = RC.feriados_da_casa(con)
            if r:
                preenchido = RC.para_o_formulario(r, comp[:7], feriados)
        return render_template("despesas_nova.html", f=preenchido, formas=DP.FORMAS,
                               categorias=DP.CATEGORIAS, naturezas=DP.NATUREZAS)

    # ------------------------------------------------- as recorrentes (28/10/2026)

    @app.route("/administrativo/despesas/recorrentes")
    @login_required
    @roles_required("ADMIN")
    @so_o_titular
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
    @roles_required("ADMIN")
    @so_o_titular
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
    @roles_required("ADMIN")
    @so_o_titular
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
    @roles_required("ADMIN")
    @so_o_titular
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
    @roles_required("ADMIN")
    @so_o_titular
    def despesas_ficha(despesa_id: int):
        with db.connect() as con:
            d = DP.despesa(con, despesa_id)
            if not d:
                abort(404)
            rastro = DP.eventos(con, despesa_id)
            arquivos = DP.anexos(con, despesa_id)
            whatsapp = DC.whatsapp_na_ficha(con, d, db.now())
            cfg = DP.configuracao(con)
        return render_template("despesas_ficha.html", d=d, rastro=rastro, arquivos=arquivos,
                               situacoes=DP.SITUACOES, formas=DP.FORMAS,
                               categorias=DP.CATEGORIAS, naturezas=DP.NATUREZAS,
                               tetos=DP.tetos(cfg), cfg=cfg, reais=DP.reais,
                               papel=usuario_papel(), hoje=date.today().isoformat(),
                               foi_paga=DC.foi_paga(d), demonstrativo=DC.pode_gerar(d),
                               whatsapp=whatsapp, orientacao=DF.orientacao(d),
                               pode_corrigir=DF.pode_corrigir(d), revisao=DF.revisao(d))

    @app.route("/administrativo/despesas/<int:despesa_id>/corrigir-pagamento", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    @so_o_titular
    def despesas_corrigir_pagamento(despesa_id: int):
        try:
            with db.transaction() as con:
                DF.corrigir(con, despesa_id, dados=request.form,
                            motivo=request.form.get('motivo') or '',
                            versao=request.form.get('revisao') or '',
                            agora=_agora(), por=usuario_nome(), papel=usuario_papel(),
                            usuario_id=usuario_id())
        except (DP.DespesaError, ValueError) as erro:
            flash(str(erro), 'danger')
        else:
            flash('Dados corrigidos na mesma despesa. Historico preservado; '
                  'confira os novos dados e autorize novamente. Nenhum pagamento foi enviado.', 'success')
        return _ficha(despesa_id)

    @app.route("/administrativo/despesas/<int:despesa_id>/<acao>", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    @so_o_titular
    def despesas_acao(despesa_id: int, acao: str):
        f, papel = request.form, usuario_papel()
        try:
            if acao in ("autorizar", "devolver", "cancelar", "pago_fora", "documento",
                        "ajustar_valor"):
                with db.transaction() as con:
                    if acao == "ajustar_valor":
                        DP.ajustar_valor(con, despesa_id, agora=_agora(), por=usuario_nome(),
                                         papel=papel,
                                         valor_centavos=DP.centavos_da_tela(f.get("valor")))
                    elif acao == "autorizar":
                        DF.conferir_revisao(con, despesa_id, f.get('revisao') or '')
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

    @app.route("/administrativo/despesas/autorizar-marcadas", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    @so_o_titular
    def despesas_autorizar_marcadas():
        """Autoriza as marcadas na lista, sem abrir uma por uma.

        Cada uma na sua transação: a recusa de uma não segura as outras, e a
        tela diz qual ficou e por quê. O teto e a divergência continuam na ficha.
        """
        try:
            marcadas = dict(tuple(int(p) for p in m.split(":"))
                            for m in request.form.getlist("marcada"))
        except ValueError:
            abort(400)
        if not marcadas:
            flash("Marque ao menos uma despesa.", "warning")
            return redirect(url_for("despesas_lista"))
        autorizadas, total, recusadas = [], 0, []
        for despesa_id, valor in marcadas.items():
            try:
                with db.transaction() as con:
                    DF.conferir_revisao(con, despesa_id,
                                        request.form.get(f'revisao_{despesa_id}') or '')
                    DP.autorizar(con, despesa_id, agora=_agora(), por=usuario_nome(),
                                 papel=usuario_papel(), valor_visto=valor)
            except DP.DespesaError as erro:
                recusadas.append(f"#{despesa_id}: {erro}")
                continue
            autorizadas.append(despesa_id)
            total += valor
        for despesa_id in autorizadas:
            audit("DESPESA_AUTORIZAR", "dp_despesas", despesa_id,
                  {"papel": usuario_papel(), "em_lote": True})
        if autorizadas:
            flash(f"{len(autorizadas)} despesa(s) autorizada(s), R$ {DP.reais(total)}.", "success")
        for recusa in recusadas:
            flash(f"Não autorizei {recusa}", "danger")
        return redirect(url_for("despesas_lista"))

    @app.route("/administrativo/despesas/conciliar", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    @so_o_titular
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
    @so_o_titular
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

    @app.route("/administrativo/despesas/<int:despesa_id>/recebedor", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    @so_o_titular
    def despesas_recebedor(despesa_id: int):
        try:
            with db.transaction() as con:
                DP.aceitar_recebedor(con, despesa_id, agora=_agora(), por=usuario_nome(),
                                     papel=usuario_papel(), motivo=request.form.get("motivo"))
        except DP.DespesaError as erro:
            flash(str(erro), "danger")
            return _ficha(despesa_id)
        audit("DESPESA_RECEBEDOR_ACEITO", "dp_despesas", despesa_id, {})
        flash("Registrado. A despesa volta à conferência do extrato.", "success")
        return _ficha(despesa_id)

    @app.route("/administrativo/despesas/<int:despesa_id>/contato", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    @so_o_titular
    def despesas_contato(despesa_id: int):
        try:
            with db.transaction() as con:
                DC.gravar_contato(con, despesa_id, email=request.form.get("contato_email"),
                                  whatsapp=request.form.get("contato_whatsapp"),
                                  por=usuario_nome(), agora=_agora())
        except DP.DespesaError as erro:
            flash(str(erro), "danger")
            return _ficha(despesa_id)
        audit("DESPESA_CONTATO", "dp_despesas", despesa_id, {})
        flash("Contato gravado.", "success")
        return _ficha(despesa_id)

    @app.route("/administrativo/despesas/<int:despesa_id>/demonstrativo.pdf")
    @login_required
    @roles_required("ADMIN")
    @so_o_titular
    def despesas_demonstrativo(despesa_id: int):
        with db.connect() as con:
            d = DP.despesa(con, despesa_id)
        if not d:
            abort(404)
        try:
            pdf = DC.pdf_do_demonstrativo(d, SERV.dados(db.get_settings), _agora())
        except DP.DespesaError as erro:
            flash(str(erro), "danger")
            return _ficha(despesa_id)
        return send_file(BytesIO(pdf), mimetype="application/pdf", as_attachment=True,
                         download_name=DC.nome_do_demonstrativo(d))

    @app.route("/administrativo/despesas/<int:despesa_id>/comprovante", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    @so_o_titular
    def despesas_comprovante(despesa_id: int):
        """O clique que manda o comprovante. A rede fica fora da transação."""
        canal = request.form.get("canal")
        try:
            if canal == "email":
                DC.enviar_email(db, despesa_id, por=usuario_nome(), agora=_agora(),
                                anexo_id=request.form.get("anexo_id"))
            elif canal == "whatsapp":
                DC.enviar_whatsapp(db, despesa_id, por=usuario_nome(), agora=_agora(),
                                   agora_texto=db.now(), pasta_arquivos=archive_root())
            else:
                abort(400)
        except DP.DespesaError as erro:
            flash(str(erro), "danger")
            return _ficha(despesa_id)
        audit("DESPESA_COMPROVANTE", "dp_despesas", despesa_id, {"canal": canal})
        flash("Demonstrativo enviado.", "success")
        return _ficha(despesa_id)

    @app.route("/administrativo/despesas/relatorio")
    @login_required
    @roles_required("ADMIN")
    @so_o_titular
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
    @so_o_titular
    def despesas_configuracao():
        if request.method == "POST":
            f = request.form
            try:
                if f.get("acao") == "chave_do_titular":
                    # As senhas não ficam: não vão à auditoria, ao log nem à tela de volta.
                    marca = COT.criar_chave(db, f.get("senha") or "", f.get("confirmacao") or "",
                                            de_quem=usuario_nome(), agora=_agora(),
                                            senha_atual=f.get("senha_atual") or "")
                    audit("DESPESAS_CHAVE_DO_TITULAR", "settings", None, {"impressao": marca})
                    flash("Chave do titular criada. Guarde a senha: ninguém a recupera. "
                          "O próximo backup já sai com a sua parte fechada.", "success")
                elif f.get("acao") == "credencial":
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
            except (DP.DespesaError, COT.CofreDoTitularError) as erro:
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
                               ambientes=DP.AMBIENTES, credencial=INTER.resumo_da_credencial(),
                               chave_do_titular=COT.situacao_para_a_tela(db))
