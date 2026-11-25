"""AS TELAS DA INTIMAÇÃO FIDUCIÁRIA DO RI (RI013-I1, 24/11/2026). A rota só liga os fios.

O domínio mora em `ri_intimacao_fiduciaria`. Nada aqui fala com o ONR nem com os Correios, e
nada sela: as peças saem com a tarja «SEM SELO — NÃO ENTREGAR» enquanto o selo não estiver ligado.

Quem decide é o oficial (ADMIN e MANAGER): qualificar, promover o edital, certificar e encerrar.
O balcão lança o que aconteceu: intimandos, endereços, diligências, e-mail, purga e repasse.
"""
from __future__ import annotations

import json
from datetime import date

from flask import flash, redirect, render_template, request, url_for

import ri_intimacao_fiduciaria as INT
from ri_schema import eh_dia_util, ler_feriados_locais
from serventia import dados as dados_serventia

QUEM_OPERA = ("ADMIN", "MANAGER", "USER")
QUEM_DECIDE = ("ADMIN", "MANAGER")
ACOES_DO_OFICIAL = {"qualificar", "edital", "certidao_purgacao", "certidao_nao_purgacao", "encerrar"}


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    """Pendura as telas no app já construído."""

    usuario_nome = app.extensions["usuario_nome"]
    usuario_papel = app.extensions["usuario_papel"]

    def _campo(nome: str) -> str:
        return (request.form.get(nome) or "").strip()

    def _e_util():
        locais = ler_feriados_locais(db.get_setting("ri_feriados_locais", ""))
        return lambda d: eh_dia_util(d, locais)

    def _hoje() -> str:
        return db.now()[:10]

    def _config() -> dict:
        return INT.configuracao(db.get_setting)

    def _do_protocolo(protocolo_id: int) -> dict | None:
        """Para a ficha da prenotação: o procedimento dela, se houver. Só LÊ."""
        try:
            with db.connect() as con:
                i = INT.do_protocolo(con, int(protocolo_id))
        except Exception:  # noqa: BLE001 — a ficha da prenotação não cai por causa deste quadro
            return None
        return (i | {"terminais": INT.TERMINAIS}) if i else None

    app.jinja_env.globals["intimacao_fiduciaria_do_protocolo"] = _do_protocolo

    @app.route("/registro-imoveis/intimacoes")
    @login_required
    def ri_intimacoes():
        """O painel: os prazos, o vencido primeiro; repasses e consolidações a acompanhar. Só LÊ."""
        hoje = _hoje()
        with db.connect() as con:
            dados = INT.painel(con, hoje=hoje, e_util=_e_util())
            atos = INT.atos_e_emolumentos(con)
        return render_template(
            "ri_intimacoes.html", hoje=hoje, atos=atos, config=_config(), MEIOS=INT.MEIOS,
            CONTAGENS=INT.CONTAGENS, FORMAS_DO_REPASSE=INT.FORMAS_DO_REPASSE, reais=INT.reais,
            fmt_date=fmt_date, **dados)

    @app.route("/registro-imoveis/intimacoes/configuracao", methods=["POST"])
    @roles_required("ADMIN")
    def ri_intimacoes_configuracao():
        """As decisões do titular: meio padrão, conta da purga, repasse e contagem. ESCREVE settings."""
        try:
            valores = INT.conferir_configuracao(request.form)
        except INT.IntimacaoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ri_intimacoes"))
        db.set_settings(valores)
        audit("RI_INTIMACAO_CONFIGURACAO", "settings", None,
              {k: v for k, v in valores.items() if k != "ri_intimacao_conta_purga"})
        flash("Configuração da intimação fiduciária gravada.", "success")
        return redirect(url_for("ri_intimacoes"))

    @app.route("/registro-imoveis/intimacoes/nova", methods=["GET", "POST"])
    @roles_required(*QUEM_OPERA)
    def ri_intimacao_nova():
        """Autua o requerimento sobre uma prenotação aberta. ESCREVE no POST."""
        if request.method == "POST" and _campo("pedido_central"):
            # O PEDIDO DA CENTRAL, COLADO: a forma do `GetDetalhesIN_V3` em JSON. Serve à
            # homologação da I2 e a quem tem o pedido em mãos; nada aqui fala com a Central.
            try:
                pedido = json.loads(_campo("pedido_central"))
                if not isinstance(pedido, dict):
                    raise ValueError("o pedido não é um objeto")
                with db.transaction() as con:
                    feito = INT.autuar_da_central(
                        con, protocolo_id=int(_campo("protocolo_id") or 0), resp=pedido, ano=int(db.now()[:4]),
                        agora=db.now(), hoje=date.fromisoformat(_hoje()), usuario=usuario_nome())
            except (INT.IntimacaoError, ValueError) as erro:
                flash(f"Pedido da Central não autuado: {erro}", "danger")
                return redirect(url_for("ri_intimacao_nova", protocolo_id=_campo("protocolo_id")))
            audit("RI_INTIMACAO_AUTUADA", "ri_intimacoes", feito["id"], {"rotulo": feito["rotulo"], "origem": "CENTRAL_ONR"})
            flash(f"Pedido da Central autuado sob o n. {feito['rotulo']}, com os devedores na lista.", "success")
            return redirect(url_for("ri_intimacao", intimacao_id=feito["id"]))
        if request.method == "POST":
            try:
                with db.transaction() as con:
                    feito = INT.autuar(
                        con, protocolo_id=int(_campo("protocolo_id") or 0), ano=int(db.now()[:4]),
                        agora=db.now(), hoje=date.fromisoformat(_hoje()), usuario=usuario_nome(),
                        matricula_numero=_campo("matricula_numero"),
                        ato_garantia_id=_campo("ato_garantia_id") or None,
                        habitacional=bool(request.form.get("habitacional")),
                        avalistas_a_pedido=bool(request.form.get("avalistas_a_pedido")),
                        prestacoes=_campo("prestacoes"), projecao=_campo("projecao"),
                        demonstrativo_valor=_campo("demonstrativo_valor"),
                        **{c: _campo(c) for c in (
                            "origem", "protocolo_central", "data_remessa", "contrato", "credor_nome",
                            "credor_documento", "credor_contato", "solicitante_nome", "solicitante_documento",
                            "representante_nome", "demonstrativo_data")})
            except INT.IntimacaoError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("ri_intimacao_nova", protocolo_id=_campo("protocolo_id")))
            audit("RI_INTIMACAO_AUTUADA", "ri_intimacoes", feito["id"], {"rotulo": feito["rotulo"]})
            flash(f"Requerimento autuado sob o n. {feito['rotulo']}. O prazo da prenotação está suspenso "
                  "(TJMA 723). Agora ponha na lista quem será intimado.", "success")
            return redirect(url_for("ri_intimacao", intimacao_id=feito["id"]))
        with db.connect() as con:
            prenotacoes = INT.prenotacoes_para_autuar(con)
        return render_template("ri_intimacao_nova.html", prenotacoes=prenotacoes, ORIGENS=INT.ORIGENS,
                               escolhido=(request.args.get("protocolo_id") or ""), fmt_date=fmt_date)

    @app.route("/registro-imoveis/intimacoes/<int:intimacao_id>")
    @login_required
    def ri_intimacao(intimacao_id: int):
        """A ficha do procedimento, em fases no layout novo. Só LÊ."""
        hoje = _hoje()
        with db.connect() as con:
            i = INT.um(con, intimacao_id)
            if not i:
                flash("Procedimento não encontrado.", "danger")
                return redirect(url_for("ri_intimacoes"))
            intimandos = INT.intimandos_de(con, intimacao_id)
            eventos = INT.eventos_de(con, intimacao_id)
            sugeridos = INT.sugerir_proprietarios(con, intimacao_id)
        for x in intimandos:
            x["faltas_edital"] = INT.faltas_para_o_edital(x)
        cfg = _config()
        return render_template(
            "ri_intimacao.html", i=i, intimandos=intimandos, eventos=eventos, sugeridos=sugeridos, hoje=hoje,
            acoes=INT.acoes_possiveis(i, hoje=hoje), abas=INT.fases(i, intimandos=intimandos, eventos=eventos),
            requisitos=INT.REQUISITOS, nao_se_qualifica=INT.NAO_SE_QUALIFICA, PAPEIS=INT.PAPEIS,
            ORIGENS=INT.ORIGENS, ORIGENS_DO_ENDERECO=INT.ORIGENS_DO_ENDERECO, MEIOS=INT.MEIOS,
            RESULTADOS=INT.RESULTADOS, FORMAS_DA_PURGA=INT.FORMAS_DA_PURGA,
            FORMAS_DO_REPASSE=INT.FORMAS_DO_REPASSE, JA_INTIMADO=INT.JA_INTIMADO,
            pecas=INT.pecas_disponiveis(i, intimandos), marcos=INT.depois_da_nao_purgacao(i, e_util=_e_util()),
            config=cfg, reais=INT.reais, fmt_date=fmt_date)

    @app.route("/registro-imoveis/intimacoes/<int:intimacao_id>/acao", methods=["POST"])
    @roles_required(*QUEM_OPERA)
    def ri_intimacao_acao(intimacao_id: int):
        """Lança um passo. ESCREVE. O domínio recusa o que não cabe na situação."""
        voltar = redirect(url_for("ri_intimacao", intimacao_id=intimacao_id))
        acao = _campo("acao")
        if acao in ACOES_DO_OFICIAL and usuario_papel() not in QUEM_DECIDE:
            flash("Este passo é do oficial.", "danger")
            return voltar
        dia = _campo("dia") or _hoje()
        cfg = _config()
        comum = {"agora": db.now(), "usuario": usuario_nome()}
        prazo = {"contagem": cfg["ri_intimacao_purga_contagem"], "e_util": _e_util()}
        quem = lambda: int(_campo("intimando_id") or 0)  # noqa: E731
        passos = {
            "qualificar": lambda c: INT.qualificar(c, intimacao_id, resultado=_campo("resultado"),
                                                   itens=request.form.getlist("itens"), motivo=_campo("motivo"),
                                                   dia=dia, **comum),
            "intimando": lambda c: INT.adicionar_intimando(
                c, intimacao_id, nome=_campo("nome"), papel=_campo("papel"), documento=_campo("documento"),
                participacao=_campo("participacao"), email=_campo("email"),
                pessoa_juridica=bool(request.form.get("pessoa_juridica")), representante=_campo("representante"),
                enderecos=_campo("enderecos"), **comum, **prazo),
            "corrigir": lambda c: INT.corrigir_intimando(
                c, intimacao_id, quem(), representante=request.form.get("representante"),
                email=request.form.get("email"), documento=request.form.get("documento"), **comum),
            "endereco": lambda c: INT.adicionar_endereco(c, intimacao_id, quem(), origem=_campo("origem"),
                                                         endereco=_campo("endereco"), **comum),
            "acervo_sem_endereco": lambda c: INT.acervo_sem_endereco(c, intimacao_id, quem(),
                                                                     motivo=_campo("motivo"), **comum),
            "retirar": lambda c: INT.retirar_intimando(c, intimacao_id, quem(), motivo=_campo("motivo"),
                                                       **comum, **prazo),
            "diligencia": lambda c: INT.diligencia(
                c, intimacao_id, quem(), meio=_campo("meio"), dia=dia, resultado=_campo("resultado"),
                endereco_id=_campo("endereco_id") or None, hora=_campo("hora"),
                tentativas_carteiro=_campo("tentativas_carteiro") or None, quem_recebeu=_campo("quem_recebeu"),
                detalhe=_campo("detalhe"), rastreio=_campo("rastreio"), **comum, **prazo),
            "email": lambda c: INT.email_enviado(c, intimacao_id, quem(), dia=dia, **comum),
            "edital": lambda c: INT.publicar_edital(c, intimacao_id, quem(), dia=dia, veiculo=_campo("veiculo"),
                                                    **comum, **prazo),
            "purgar": lambda c: INT.purgar(c, intimacao_id, dia=dia, valor=_campo("valor"), forma=_campo("forma"),
                                           conta=cfg["ri_intimacao_conta_purga"], comprovante=_campo("comprovante"),
                                           e_util=_e_util(), **comum),
            "avisar_credor": lambda c: INT.avisar_credor(c, intimacao_id, dia=dia, **comum),
            "repassar": lambda c: INT.repassar(c, intimacao_id, dia=dia, forma=_campo("forma"), valor=_campo("valor"),
                                               despesas=_campo("despesas"), comprovante=_campo("comprovante"), **comum),
            "certidao_purgacao": lambda c: INT.certificar(c, intimacao_id, tipo="PURGACAO", dia=dia, hoje=_hoje(),
                                                          sv=dados_serventia(db.get_settings), **comum),
            "certidao_nao_purgacao": lambda c: INT.certificar(c, intimacao_id, tipo="NAO_PURGACAO", dia=dia,
                                                              hoje=_hoje(), sv=dados_serventia(db.get_settings),
                                                              **comum),
            "encerrar": lambda c: INT.encerrar_sem_certidao(c, intimacao_id, motivo=_campo("motivo"),
                                                            texto=_campo("texto"), dia=dia, **comum),
        }
        if acao not in passos:
            flash("Este passo não existe.", "danger")
            return voltar
        try:
            with db.transaction() as con:
                passos[acao](con)
        except (INT.IntimacaoError, ValueError) as erro:
            flash(str(erro), "danger")
            return voltar
        audit("RI_INTIMACAO_PASSO", "ri_intimacoes", intimacao_id, {"acao": acao, "dia": dia})
        flash("Lançado na linha do tempo do procedimento.", "success")
        return voltar

    @app.route("/registro-imoveis/intimacoes/<int:intimacao_id>/peca/<qual>")
    @login_required
    def ri_intimacao_peca(intimacao_id: int, qual: str):
        """A peça em papel: montar e imprimir não grava nada. Só LÊ. Sem selo, leva a tarja."""
        with db.connect() as con:
            i = INT.um(con, intimacao_id)
            intimandos = INT.intimandos_de(con, intimacao_id) if i else []
        disponiveis = INT.pecas_disponiveis(i, intimandos) if i else {}
        if qual not in disponiveis:
            flash("Esta peça ainda não cabe neste procedimento.", "warning")
            return redirect(url_for("ri_intimacoes") if not i else url_for("ri_intimacao", intimacao_id=intimacao_id))
        intimando = None
        if qual in INT.PECAS_DO_INTIMANDO:
            escolhido = request.args.get("intimando", type=int)
            intimando = next((x for x in intimandos if int(x["id"]) == (escolhido or 0)), None)
            if not intimando:
                flash("Escolha de quem é a peça.", "warning")
                return redirect(url_for("ri_intimacao", intimacao_id=intimacao_id))
        sv = dados_serventia(db.get_settings)
        from ri_web import data_por_extenso
        return render_template(
            "ri_intimacao_peca.html", i=i, sv=sv, titulo=disponiveis[qual], aviso=INT.AVISO_SEM_SELO,
            selado=bool(intimando and intimando.get("selo")),
            paragrafos=INT.texto_da_peca(i, qual, intimandos, sv=sv, intimando=intimando,
                                         conta=_config()["ri_intimacao_conta_purga"]),
            data_extenso=data_por_extenso(date.fromisoformat(_hoje())))
