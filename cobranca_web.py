"""As telas da cobrança — o boleto do protocolo, pelo Inter ou pela Unicred.

QUEM FAZ O QUÊ
    - Ver, cadastrar e lançar no caixa: quem opera o caixa (ADMIN, MANAGER e
      USER) — é o balcão que manda o boleto ao cliente e recebe o dinheiro.
    - Cancelar no banco, conceder abatimento e mexer no protesto automático:
      ADMIN e MANAGER. É dinheiro que deixa de entrar, e protesto é ato
      contra o cliente.
    - Configurar e cadastrar a credencial da Unicred: só o ADMIN. A do Inter
      é a mesma das despesas, e mora na configuração delas.

QUEM FALA COM O BANCO
    Com o cofre da automação instalado, a tela NÃO lê a credencial: grava o
    pedido e chama a rodada do despachante (`cobranca_automacao`), que roda
    no minuto seguinte. Sem o cofre, a tela fala com o banco na hora, pelo
    mesmo caminho (`cobranca_banco`). Nos dois casos nenhuma transação do
    banco de dados fica aberta durante a rede.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from flask import abort, flash, redirect, render_template, request, send_file, url_for

import cobranca as CB
import cobranca_banco as CBB
import cobranca_unicred as UNICRED
import despesas as DP
from bd_nativo import banco

QUEM_OPERA = ("ADMIN", "MANAGER", "USER")
QUEM_DECIDE = ("ADMIN", "MANAGER")
PROCESSO = "COBRANCA_ACOMPANHAR"


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_nome = app.extensions["usuario_nome"]
    usuario_papel = app.extensions["usuario_papel"]

    def _agora() -> datetime:
        return datetime.now().astimezone().replace(microsecond=0)

    def _ficha(cobranca_id: int):
        return redirect(url_for("cobranca_ficha", cobranca_id=cobranca_id))

    def _pasta():
        import centrais_cred
        return centrais_cred.pasta_de_dados()

    def _com_cofre() -> bool:
        return UNICRED._cofre() is not None

    def _pedir_rodada() -> None:
        """Com o cofre instalado: o despachante fala com o banco no próximo minuto."""
        import automacao  # type: ignore
        with db.transaction() as con:
            processo = automacao.por_codigo(con, PROCESSO)
            if not processo:
                raise CB.CobrancaError(f"O processo {PROCESSO} não está cadastrado na automação. "
                                       f"Cadastre-o lá (Automação → processos).")
            automacao.pedir_rodada(con, int(processo["id"]), usuario=usuario_nome())
        flash("Pedido ao despachante da automação: o banco é consultado no próximo minuto.",
              "info")

    def _cliente(c: dict | None = None):
        with db.connect() as con:
            cfg = CB.configuracao(con)
        return CBB.cliente_da_casa(cfg, banco_codigo=(c or {}).get("banco"))

    # ---------------------------------------------------------------- lista

    @app.route("/caixa/cobranca")
    @login_required
    @roles_required(*QUEM_OPERA)
    def cobranca_lista():
        situacao = request.args.get("situacao") or ""
        if situacao and situacao not in CB.SITUACOES:
            abort(400)
        with db.connect() as con:
            linhas = CB.lista(con, situacao=situacao)
            contagem = CB.contagem(con)
            cfg = CB.configuracao(con)
        return render_template("cobranca_lista.html", linhas=linhas, contagem=contagem,
                               situacoes=CB.SITUACOES, situacao=situacao, cfg=cfg,
                               bancos=CB.BANCOS, reais=DP.reais, papel=usuario_papel())

    # ----------------------------------------------------------------- nova

    @app.route("/caixa/cobranca/nova", methods=["GET", "POST"])
    @login_required
    @roles_required(*QUEM_OPERA)
    def cobranca_nova():
        f = request.form if request.method == "POST" else request.args
        protocolo_id = f.get("protocolo_id") or ""
        with db.connect() as con:
            cfg = CB.configuracao(con)
            a_pagar = None
            if protocolo_id.isdigit():
                try:
                    a_pagar = CB.a_pagar_do_protocolo(con, int(protocolo_id))
                except CB.CobrancaError as erro:
                    flash(str(erro), "danger")
        if request.method == "POST":
            try:
                with db.transaction() as con:
                    novo = CB.cadastrar(
                        con, agora=_agora(), por=usuario_nome(), banco_codigo=cfg["cobranca_banco"],
                        ambiente=cfg["cobranca_ambiente"],
                        protocolo_id=int(protocolo_id) if protocolo_id.isdigit() else None,
                        valor_centavos=DP.centavos_da_tela(f.get("valor")),
                        vencimento=f.get("vencimento"),
                        pagador={k: f.get(k) for k in ("nome", "documento", "email", "logradouro",
                                                       "numero", "complemento", "bairro",
                                                       "cidade", "uf", "cep")},
                        mensagem=f.get("mensagem") or "",
                        dias_apos_vencimento=int(cfg["cobranca_dias_apos_vencimento"] or 0))
            except (CB.CobrancaError, ValueError) as erro:
                flash(str(erro), "danger")
                return render_template("cobranca_nova.html", f=f, cfg=cfg, a_pagar=a_pagar,
                                       bancos=CB.BANCOS, reais=DP.reais, ufs=CB.UFS)
            audit("COBRANCA_CADASTRADA", "cb_cobrancas", novo,
                  {"valor": f.get("valor"), "protocolo_id": protocolo_id or None})
            if cfg["cobranca_ligada"] != "1":
                flash("Cobrança cadastrada. A emissão está desligada na configuração: ela "
                      "espera o oficial ligar.", "warning")
                return _ficha(novo)
            return _emitir(novo)
        p = (a_pagar or {}).get("protocolo") or {}
        sugestao = {
            "nome": p.get("interessado") or "", "documento": p.get("interessado_documento") or "",
            "email": p.get("email") or "",
            "valor": DP.reais(a_pagar["sugerido"]) if a_pagar and a_pagar["sugerido"] else "",
            "vencimento": (date.today() + timedelta(
                days=int(cfg["cobranca_dias_vencimento"] or 0))).isoformat(),
            "mensagem": cfg["cobranca_mensagem"].replace("{protocolo}", p.get("numero") or ""),
            "uf": "MA", "protocolo_id": protocolo_id,
        }
        return render_template("cobranca_nova.html", f=sugestao, cfg=cfg, a_pagar=a_pagar,
                               bancos=CB.BANCOS, reais=DP.reais, ufs=CB.UFS)

    def _emitir(cobranca_id: int):
        if _com_cofre():
            try:
                _pedir_rodada()
            except CB.CobrancaError as erro:
                flash(str(erro), "danger")
            return _ficha(cobranca_id)
        try:
            with db.connect() as con:
                c = CB.cobranca(con, cobranca_id)
            nova = CBB.emitir(db, cobranca_id, cliente=_cliente(c), por=usuario_nome(),
                              agora=_agora())
        except (CBB.BancoError, CB.CobrancaError) as erro:
            flash(f"A cobrança não foi emitida agora: {erro}", "danger")
            return _ficha(cobranca_id)
        audit("COBRANCA_EMITIDA", "cb_cobrancas", cobranca_id, {"situacao": nova})
        flash(f"Enviada ao banco: {CB.SITUACOES[nova]}.",
              "success" if nova in CB.EM_ABERTO else "danger")
        return _ficha(cobranca_id)

    # ---------------------------------------------------------------- ficha

    @app.route("/caixa/cobranca/<int:cobranca_id>")
    @login_required
    @roles_required(*QUEM_OPERA)
    def cobranca_ficha(cobranca_id: int):
        with db.connect() as con:
            c = CB.cobranca(con, cobranca_id)
            if not c:
                abort(404)
            rastro = CB.eventos(con, cobranca_id)
            cfg = CB.configuracao(con)
            protocolo = None
            if c["protocolo_id"]:
                protocolo = banco(con).um("SELECT id, numero FROM cx_protocolos WHERE id = %s",
                                          (int(c["protocolo_id"]),))
            caixa = CB.caixa_aberto(con, usuario_nome())
        return render_template("cobranca_ficha.html", c=c, rastro=rastro, cfg=cfg,
                               protocolo=protocolo, caixa=caixa, endereco=CB.endereco(c),
                               pedido=CB.pedido(c), pedidos=CB.PEDIDOS,
                               recursos=CB.RECURSOS[c["banco"]], situacoes=CB.SITUACOES,
                               bancos=CB.BANCOS, reais=DP.reais, papel=usuario_papel(),
                               com_cofre=_com_cofre())

    @app.route("/caixa/cobranca/<int:cobranca_id>/boleto.pdf")
    @login_required
    @roles_required(*QUEM_OPERA)
    def cobranca_boleto_pdf(cobranca_id: int):
        with db.connect() as con:
            c = CB.cobranca(con, cobranca_id)
        if not c:
            abort(404)
        alvo = CB.caminho_do_pdf(_pasta(), cobranca_id)
        if not c["pdf_guardado"] or not alvo.is_file():
            flash("O PDF deste boleto ainda não foi baixado do banco.", "warning")
            return _ficha(cobranca_id)
        audit("COBRANCA_PDF_ABERTO", "cb_cobrancas", cobranca_id, {})
        return send_file(alvo, mimetype="application/pdf", as_attachment=False,
                         download_name=f"boleto_{c['seu_numero']}.pdf")

    @app.route("/caixa/cobranca/<int:cobranca_id>/<acao>", methods=["POST"])
    @login_required
    @roles_required(*QUEM_OPERA)
    def cobranca_acao(cobranca_id: int, acao: str):
        f, papel, agora, por = request.form, usuario_papel(), _agora(), usuario_nome()
        with db.connect() as con:
            c = CB.cobranca(con, cobranca_id)
        if not c:
            abort(404)
        try:
            if acao == "emitir":
                with db.connect() as con:
                    if CB.configuracao(con)["cobranca_ligada"] != "1":
                        raise CB.CobrancaError("A emissão está desligada na configuração.")
                return _emitir(cobranca_id)
            if acao == "lancar":
                with db.transaction() as con:
                    caixa = CB.caixa_aberto(con, por)
                    feito = CB.lancar_no_caixa(con, cobranca_id, por=por, agora=agora,
                                               caixa_id=int(caixa["id"]) if caixa else None)
                audit("COBRANCA_LANCADA_NO_CAIXA", "cb_cobrancas", cobranca_id,
                      {"deposito": feito["numero"]})
                flash(f"Lançada no caixa como depósito prévio nº {feito['numero']}. Use o saldo "
                      f"dele para quitar os itens do protocolo.", "success")
                return _ficha(cobranca_id)
            if acao == "descartar":
                with db.transaction() as con:
                    CB.cancelar_local(con, cobranca_id, por=por, agora=agora,
                                      motivo=f.get("motivo") or "")
                audit("COBRANCA_DESCARTADA", "cb_cobrancas", cobranca_id,
                      {"motivo": f.get("motivo")})
                flash("Cobrança cancelada (ela não chegou ao banco).", "success")
                return _ficha(cobranca_id)
            if acao in ("atualizar", "baixar_pdf"):
                return _falar_com_banco(c, acao)
            if acao in ("cancelar", "abatimento", "cancelar_abatimento", "protesto"):
                if papel not in QUEM_DECIDE:
                    abort(403)
                dados = _dados_do_pedido(acao, f)
                with db.transaction() as con:
                    CB.pedir(con, cobranca_id, acao.upper(), dados, por=por, agora=agora)
                audit("COBRANCA_PEDIDO", "cb_cobrancas", cobranca_id, {"acao": acao, **dados})
                return _falar_com_banco(c, "pedido")
        except (CB.CobrancaError, CBB.BancoError) as erro:
            flash(str(erro), "danger")
            return _ficha(cobranca_id)
        abort(404)

    def _dados_do_pedido(acao: str, f) -> dict:
        if acao == "cancelar":
            return {"motivo": f.get("motivo") or ""}
        if acao == "abatimento":
            return {"valor": DP.centavos_da_tela(f.get("valor")),
                    "justificativa": f.get("justificativa") or ""}
        if acao == "cancelar_abatimento":
            return {"justificativa": f.get("justificativa") or ""}
        dias = str(f.get("dias") or "0").strip()
        if not dias.isdigit():
            raise CB.CobrancaError("Os dias do protesto são um número.")
        return {"ligado": f.get("ligado") in ("1", "on"), "dias": int(dias),
                "dias_uteis": f.get("dias_uteis") in ("1", "on")}

    def _falar_com_banco(c: dict, acao: str):
        """Consulta, executa o pedido ou baixa o PDF — agora, ou pela automação."""
        if _com_cofre():
            _pedir_rodada()
            return _ficha(c["id"])
        cliente = _cliente(c)
        agora, por = _agora(), usuario_nome()
        if acao == "pedido":
            frase = CBB.executar_pedido(db, c["id"], cliente=cliente, por=por, agora=agora,
                                        pasta=_pasta())
            flash(frase, "danger" if frase.startswith("O banco recusou") else "success")
        elif acao == "baixar_pdf":
            CBB.guardar_pdf(db, c["id"], cliente=cliente, pasta=_pasta())
            flash("PDF do boleto baixado do banco.", "success")
        else:
            nova = CBB.atualizar(db, c["id"], cliente=cliente, por=por, agora=agora)
            flash(f"Consultado no banco: {CB.SITUACOES[nova]}.", "info")
        return _ficha(c["id"])

    # -------------------------------------------------------- configuração

    @app.route("/caixa/cobranca/configuracao", methods=["GET", "POST"])
    @login_required
    @roles_required("ADMIN")
    def cobranca_configuracao():
        if request.method == "POST":
            f = request.form
            try:
                if f.get("parte") == "unicred":
                    onde = UNICRED.gravar_credencial(
                        {k: f.get(k) for k in UNICRED.CAMPOS_DA_CREDENCIAL})["onde"]
                    audit("COBRANCA_CREDENCIAL_UNICRED", "settings", None, {"onde": onde})
                    flash(f"Credencial da Unicred gravada ({onde}).", "success")
                else:
                    with db.transaction() as con:
                        mudou = CB.gravar_configuracao(con, f)
                    audit("COBRANCA_CONFIGURADA", "settings", None,
                          {k: v[1] for k, v in mudou.items()})
                    flash("Configuração gravada.", "success")
            except (CB.CobrancaError, CBB.BancoError) as erro:
                flash(str(erro), "danger")
            return redirect(url_for("cobranca_configuracao"))
        with db.connect() as con:
            cfg = CB.configuracao(con)
        return render_template("cobranca_configuracao.html", cfg=cfg, rotulos=CB.ROTULOS,
                               bancos=CB.BANCOS, ambientes=CB.AMBIENTES,
                               unicred=UNICRED.resumo_da_credencial(),
                               rotulos_unicred=UNICRED.ROTULOS_DA_CREDENCIAL,
                               procedencia_token=UNICRED.PROCEDENCIA_DO_TOKEN)
