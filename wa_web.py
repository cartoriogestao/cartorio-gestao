"""Telas e webhook do Balcao WhatsApp.

GET/POST /whatsapp/webhook — teste local e reenvio da caixa-postal.
  Sem login. CSRF isento. Em producao o inbound NAO chega direto aqui:
  o SERVIDOR do Cartorio Gestao nao expoe 8765 e nao roda tunel.

GET /whatsapp e as demais — mesmo login do resto do app.

UM RELOGIO SO PARA A CASA INTEIRA: as rotas passam `db.now()`, o mesmo que
grava o resto do sistema.

O ATENDENTE COM IA, AS ETIQUETAS, O SETOR E O PAINEL (26/10/2026)
    /whatsapp/atendente — a configuracao do atendente (so o ADMIN grava) e o
    registro das respostas automaticas; /whatsapp/painel — o prazo por setor;
    na conversa, etiquetas, transferencia, assumir, passar para pessoa e
    devolver a IA. NENHUMA rota fala com a rede dentro de `db.transaction()`:
    o puxar busca fora e aplica dentro; o enviar monta, posta e grava.
"""
from __future__ import annotations

from pathlib import Path

from flask import abort, flash, redirect, render_template, request, url_for

import agente_provedores as PROV
import serventia as SERV
import tetos_de_entrada as TETO
import wa_atendente as ATENDENTE
import wa_balcao as WA
import wa_fila as FILA
import wa_modelos as MODELOS
import wa_puxar as PUXAR
import wa_schema as SCH
from seguranca_web import PRATICA  # M2 (LX11): o AUDITOR vê e não grava


def registrar_rotas(app, db, login_required, roles_required, audit):
    """Pendura a fila do WhatsApp no app ja construido."""

    def _serventia() -> dict:
        return SERV.dados(db.get_settings)

    # Os rascunhos são o papel CAIXA_WHATSAPP do catálogo desde o LF06F; a
    # tela de Modelos os confere com os claros deles, e não com o boneco geral.
    app.extensions.setdefault("conferidores_de_modelo", {})[
        WA.TEXTOS.MODELO] = WA.TEXTOS.conferir
    import modelos_elementos as ELEM
    ELEM.CONFERIDORES[WA.TEXTOS.MODELO] = WA.TEXTOS.conferir

    def _con():
        return db.connect()

    def _quem() -> str:
        try:
            return app.extensions["usuario_nome"]() or ""
        except Exception:                               # noqa: BLE001
            return ""

    def _pasta() -> Path:
        return Path(app.config["DATA_DIR"])

    @app.route("/whatsapp/webhook", methods=["GET", "POST"])
    def whatsapp_webhook():
        """Callback da Cloud API. Sem login. CSRF isento neste endpoint.

        Producao: a Meta aponta para o worker na VPS (equipetextual.com.br), nao para aqui.
        Este POST so vale com X-Wa-Test (dev, e so da propria maquina) ou HMAC
        se app_secret gravado.
        """
        if request.method == "GET":
            modo = (request.args.get("hub.mode") or "").strip()
            token = (request.args.get("hub.verify_token") or "").strip()
            challenge = request.args.get("hub.challenge") or ""
            with _con() as con:
                esperado = WA.verify_token_salvo(con)
            if modo == "subscribe" and token and token == esperado:
                return challenge, 200, {"Content-Type": "text/plain; charset=utf-8"}
            abort(403)

        # O POST DE TESTE SÓ VALE DA PRÓPRIA MÁQUINA (LS02, 19/10/2026).
        #
        #   Sem `app_secret` gravado — e a casa não o grava, porque a entrada
        #   de verdade vem pela caixa-postal (`/whatsapp/puxar`) —, bastava o
        #   cabeçalho `X-Wa-Test: 1` para qualquer máquina da rede, SEM LOGIN,
        #   pôr na fila do balcão a conversa que quisesse, com o número e o
        #   nome que quisesse: a resposta do escrevente iria para o número de
        #   quem forjou. O teste de desenvolvimento roda no próprio servidor;
        #   é a mesma régua da ponte do CCN (`ccn_web.LOCAIS`).
        # O CORPO TEM TETO, E A RECUSA VEM ANTES DE LER (LX12, LS02 M5,
        # 19/10/2026). Esta rota não tem login, e o teto geral do app é de
        # 200 MB: qualquer máquina mandava 200 MB que o servidor lia inteiros
        # para a memória antes de o HMAC dizer não. A entrada da Meta é JSON
        # de poucos KB; 2 MB (`corpo_anonimo_bytes`) é folga de sobra. O
        # `Content-Length` declarado se recusa já; o corpo sem ele (chunked)
        # é cortado na leitura pelo `max_content_length` desta requisição.
        teto = TETO.valor("corpo_anonimo_bytes")
        if (request.content_length or 0) > teto:
            abort(413)
        request.max_content_length = teto
        header_teste = (request.headers.get("X-Wa-Test", "")
                        if request.remote_addr in ("127.0.0.1", "::1") else "")
        sig = request.headers.get("X-Hub-Signature-256", "")
        bruto = request.get_data(cache=True) or b""
        payload = request.get_json(silent=True)
        if payload is None:
            payload = {}
        with db.transaction() as con:
            if not WA.post_permitido(con, header_teste, bruto, sig):
                abort(403)
            resultado = WA.aplicar_entrada(con, payload,
                                           serventia=_serventia(),
                                           agora=db.now())
        try:
            audit("wa_entrada", "wa_conversa",
                  (resultado.get("conversa_ids") or [None])[0],
                  {"criadas": resultado.get("criadas"),
                   "repetidas": resultado.get("repetidas")})
        except Exception:                       # noqa: BLE001
            app.logger.exception(
                "a entrada do WhatsApp foi gravada, e a auditoria dela falhou")
        return ("", 200)

    @app.route("/whatsapp")
    @login_required
    def whatsapp_lista():
        setor = request.args.get("setor", "")
        etiqueta = request.args.get("etiqueta", "")
        so = request.args.get("so", "")
        with _con() as con:
            linhas = FILA.listar(con, agora=db.now(), setor=setor,
                                 etiqueta=etiqueta, so_abertas=(so == "abertas"),
                                 so_vencidas=(so == "vencidas"))
            cfg = WA.config_para_tela(con)
            ia = ATENDENTE.configuracao(con)
            etiquetas = FILA.etiquetas_em_uso(con)
        return render_template("whatsapp_lista.html", linhas=linhas, cfg=cfg,
                               ia=ia, setores=SCH.SETORES, etiquetas=etiquetas,
                               filtro={"setor": setor, "etiqueta": etiqueta,
                                       "so": so})

    @app.route("/whatsapp/painel")
    @login_required
    def whatsapp_painel():
        with _con() as con:
            p = FILA.painel(con, agora=db.now())
            hoje = ATENDENTE.resumo_do_dia(con, agora=db.now())
            ia = ATENDENTE.configuracao(con)
        return render_template("whatsapp_painel.html", p=p, hoje=hoje, ia=ia)

    @app.route("/whatsapp/atendente", methods=["GET", "POST"])
    @login_required
    def whatsapp_atendente():
        """O atendente com IA: ver é de todos; gravar é só do ADMIN — é ele que
        liga a resposta automática e aprova o texto-base (26/10/2026)."""
        if request.method == "POST":
            if app.extensions["usuario_papel"]() != "ADMIN":
                abort(403)
            try:
                with db.transaction() as con:
                    avisos = ATENDENTE.gravar_configuracao(
                        con, request.form, por=_quem(), agora=db.now())
            except ATENDENTE.AtendenteErro as erro:
                flash(str(erro), "danger")
                return redirect(url_for("whatsapp_atendente"))
            audit("wa_atendente_config", "wa_config", None,
                  {"ia_ligada": request.form.get("ia_ligada") == "1",
                   "audio_ligado": request.form.get("audio_ligado") == "1"})
            for aviso in avisos:
                flash(aviso, "warning")
            flash("Configuração do atendente guardada.", "success")
            return redirect(url_for("whatsapp_atendente"))
        with _con() as con:
            ia = ATENDENTE.configuracao(con)
            linhas = ATENDENTE.registros(con, limite=100)
            hoje = ATENDENTE.resumo_do_dia(con, agora=db.now())
            pode_enviar = WA.pode_enviar_meta(con)
        return render_template(
            "whatsapp_atendente.html", ia=ia, linhas=linhas, hoje=hoje,
            pode_enviar=pode_enviar,
            # SÓ O NOME E SE HÁ CHAVE: nenhum pedaço da chave chega ao HTML
            # desta tela, que todo login vê.
            provedores=[{"id": p["id"], "nome": p["nome"], "tem_chave": p["tem_chave"]}
                        for p in PROV.catalogo_para_tela(_pasta())],
            rotulos=ATENDENTE.ROTULO_DO_CASO, exemplo=ATENDENTE.TEXTO_BASE_EXEMPLO,
            tentativas=ATENDENTE.TENTATIVAS_POR_DIA,
            e_admin=app.extensions["usuario_papel"]() == "ADMIN")

    @app.route("/whatsapp/atendente/rodar", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def whatsapp_atendente_rodar():
        r = ATENDENTE.rodada(db, pasta_de_dados=_pasta(),
                             limite=ATENDENTE.CONVERSAS_NA_TELA)
        audit("wa_atendente_rodada", "wa_conversa", None,
              {"audios": r.get("audios"), "conversas": len(r.get("conversas") or [])})
        if r.get("desligado"):
            flash("O atendente e a transcrição estão desligados. Nada foi feito.",
                  "warning")
        else:
            flash(f"Atendente: {len(r.get('conversas') or [])} conversa(s) "
                  f"atendida(s), {r.get('audios') or 0} áudio(s) transcrito(s).",
                  "success")
        return redirect(url_for("whatsapp_lista"))

    @app.route("/whatsapp/config", methods=["GET", "POST"])
    @login_required
    def whatsapp_config():
        if request.method == "POST":
            # GRAVAR É SÓ DO ADMIN (LS01, 19/10/2026); ver a tela segue de todos.
            # Esta tela grava o token da Meta e a `caixa_url` — e o «puxar»
            # manda o segredo da caixa-postal, como `Bearer`, para a URL que
            # estiver gravada. Aberta a qualquer login, o balcão trocava a URL
            # pela de fora e o próximo «puxar» entregava o segredo; trocava o
            # token e as respostas aos clientes saíam pela conta de outro. É a
            # regra de `configuracoes_central`: credencial de central, só ADMIN.
            if app.extensions["usuario_papel"]() != "ADMIN":
                abort(403)
            try:
                with db.transaction() as con:
                    # OS MODELOS DA META PRIMEIRO (27/10/2026): eles conferem
                    # tudo antes de gravar, e a recusa desfaz a transação antes
                    # de o token ir ao cofre.
                    MODELOS.gravar_tela(con, request.form)
                    WA.gravar_tela_config(con, request.form)
            except MODELOS.ModeloRecusado as erro:
                flash(f"Nada foi guardado: {erro}", "danger")
                return redirect(url_for("whatsapp_config"))
            audit("wa_config", "wa_config", None,
                  {"ok": True,
                   "modelos_aprovados": request.form.get(SCH.CHAVE_MODELOS_APROVADOS) == "1"})
            flash("Configuracao do WhatsApp guardada. O token nao aparece no log.",
                  "success")
            return redirect(url_for("whatsapp_config"))
        with _con() as con:
            cfg = WA.config_para_tela(con)
            modelos = MODELOS.config_para_tela(con, _serventia())
        return render_template("whatsapp_config.html", cfg=cfg, modelos=modelos,
                               SCH=SCH,
                               e_admin=app.extensions["usuario_papel"]() == "ADMIN")

    @app.route("/whatsapp/puxar", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def whatsapp_puxar():
        # A REDE FORA DA TRANSAÇÃO (26/10/2026): busca com a conexão de
        # leitura, e só a aplicação abre a transação de escrita.
        with _con() as con:
            achado = PUXAR.buscar_pendentes(con)
        if achado.get("ok"):
            with db.transaction() as con:
                r = PUXAR.aplicar_itens(con, achado["itens"],
                                        serventia=_serventia(), agora=db.now())
            # A CONFIRMAÇÃO À CAIXA-POSTAL (27/10/2026) depois de aplicar e fora
            # da transação: o ack também é rede.
            with _con() as con:
                PUXAR.confirmar(con, r.get("ids"))
        else:
            r = achado
        audit("wa_puxar", "wa_conversa", None,
              {"ok": r.get("ok"), "aplicadas": r.get("aplicadas")})
        if r.get("ok"):
            flash(
                f"Caixa-postal: {r.get('aplicadas') or 0} nova(s), "
                f"{r.get('repetidas') or 0} ja vista(s).",
                "success")
            # O ATENDENTE RODA DEPOIS, FORA DA TRANSAÇÃO, e com poucas
            # conversas: quem clicou espera a tela, e o resto fica para a
            # rodada seguinte. Desligado, não faz nada.
            atendeu = ATENDENTE.rodada(db, pasta_de_dados=_pasta(),
                                       limite=ATENDENTE.CONVERSAS_NA_TELA)
            if not atendeu.get("desligado") and (
                    atendeu.get("conversas") or atendeu.get("audios")):
                flash(f"Atendente: {len(atendeu.get('conversas') or [])} "
                      f"conversa(s) atendida(s), {atendeu.get('audios') or 0} "
                      "áudio(s) transcrito(s).", "success")
        else:
            flash(
                "Nao puxei a caixa-postal: "
                f"{r.get('motivo') or 'falhou'}. "
                "Cole https://equipetextual.com.br/pendentes em Configuracao.",
                "danger")
        return redirect(url_for("whatsapp_lista"))

    @app.route("/whatsapp/<int:conversa_id>")
    @login_required
    def whatsapp_conversa(conversa_id: int):
        with _con() as con:
            d = WA.conversa(con, conversa_id)
            pode = WA.pode_enviar_meta(con)
            if d:
                d["etiquetas"] = FILA.etiquetas(con, conversa_id)
                d["eventos"] = FILA.eventos(con, conversa_id)
                d["setor"] = FILA.setor_valido(d.get("setor")) or SCH.SETOR_PADRAO
                d["modo"] = d.get("modo") or SCH.MODO_IA
                d["registros"] = ATENDENTE.registros(con, conversa_id=conversa_id,
                                                     limite=20)
                usuarios = FILA.usuarios_ativos(con)
                sugeridas = FILA.etiquetas_em_uso(con)
                ia = ATENDENTE.configuracao(con)
                # A JANELA DE 24 H (27/10/2026): passada ela, a Meta recusa o
                # texto livre, e o caminho é o modelo de retomar.
                janela = {"fora": MODELOS.fora_da_janela(d["mensagens"], db.now()),
                          "ligado": MODELOS.ligado(con),
                          "falta": MODELOS.falta_para_enviar(con, _serventia()),
                          "modelo": MODELOS.nome_do_modelo(con, MODELOS.RETOMAR)}
        if not d:
            abort(404)
        return render_template("whatsapp_conversa.html", c=d, pode_enviar=pode,
                               setores=SCH.SETORES, usuarios=usuarios,
                               sugeridas=sugeridas, ia=ia, janela=janela,
                               rotulos_evento=FILA.ROTULO_DO_EVENTO,
                               rotulos_caso=ATENDENTE.ROTULO_DO_CASO)

    def _na_conversa(conversa_id: int, acao, auditoria: str, detalhe=None):
        """Faz `acao(con)` na transação; ValueError vira aviso na tela."""
        try:
            with db.transaction() as con:
                if not WA.conversa(con, conversa_id):
                    abort(404)
                acao(con)
        except ValueError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("whatsapp_conversa", conversa_id=conversa_id))
        audit(auditoria, "wa_conversa", conversa_id, detalhe)
        return None

    @app.route("/whatsapp/<int:conversa_id>/etiqueta", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def whatsapp_etiqueta(conversa_id: int):
        etiqueta = request.form.get("etiqueta", "")
        tirar = request.form.get("acao") == "tirar"
        if not FILA.normalizar_etiqueta(etiqueta):
            flash("Escreva a etiqueta.", "warning")
            return redirect(url_for("whatsapp_conversa", conversa_id=conversa_id))

        def acao(con):
            if tirar:
                FILA.tirar_etiqueta(con, conversa_id, etiqueta, por=_quem(),
                                    quando=db.now())
            else:
                FILA.por_etiqueta(con, conversa_id, etiqueta, por=_quem(),
                                  quando=db.now())
        volta = _na_conversa(conversa_id, acao, "wa_etiqueta",
                             {"etiqueta": FILA.normalizar_etiqueta(etiqueta),
                              "tirar": tirar})
        return volta or redirect(url_for("whatsapp_conversa",
                                         conversa_id=conversa_id))

    @app.route("/whatsapp/<int:conversa_id>/transferir", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def whatsapp_transferir(conversa_id: int):
        bruto = (request.form.get("responsavel_id") or "").strip()
        responsavel = int(bruto) if bruto.isdigit() else None
        setor = request.form.get("setor", "")

        def acao(con):
            FILA.transferir(con, conversa_id, setor, responsavel_id=responsavel,
                            por=_quem(), nota=request.form.get("nota", ""),
                            quando=db.now())
        volta = _na_conversa(conversa_id, acao, "wa_transferir",
                             {"setor": setor, "responsavel_id": responsavel})
        if volta:
            return volta
        flash(f"Conversa transferida para {FILA.nome_do_setor(setor)}.", "success")
        return redirect(url_for("whatsapp_conversa", conversa_id=conversa_id))

    @app.route("/whatsapp/<int:conversa_id>/assumir", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def whatsapp_assumir(conversa_id: int):
        uid = app.extensions["usuario_id"]()
        volta = _na_conversa(
            conversa_id, lambda con: FILA.assumir(con, conversa_id, uid,
                                                  por=_quem(), quando=db.now()),
            "wa_assumir", None)
        return volta or redirect(url_for("whatsapp_conversa",
                                         conversa_id=conversa_id))

    @app.route("/whatsapp/<int:conversa_id>/passar", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def whatsapp_passar(conversa_id: int):
        volta = _na_conversa(
            conversa_id, lambda con: FILA.passar_para_pessoa(
                con, conversa_id, setor=request.form.get("setor", ""),
                motivo=request.form.get("motivo", "") or "passada pela tela",
                por=_quem(), quando=db.now()),
            "wa_passar", None)
        if volta:
            return volta
        flash("A IA não responde mais nesta conversa até alguém a devolver.",
              "success")
        return redirect(url_for("whatsapp_conversa", conversa_id=conversa_id))

    @app.route("/whatsapp/<int:conversa_id>/devolver", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def whatsapp_devolver(conversa_id: int):
        volta = _na_conversa(
            conversa_id, lambda con: FILA.devolver_a_ia(
                con, conversa_id, por=_quem(), quando=db.now()),
            "wa_devolver", None)
        if volta:
            return volta
        flash("Conversa devolvida ao atendente com IA (se ele estiver ligado).",
              "success")
        return redirect(url_for("whatsapp_conversa", conversa_id=conversa_id))

    @app.route("/whatsapp/<int:conversa_id>/rascunho", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def whatsapp_salvar_rascunho(conversa_id: int):
        texto = (request.form.get("rascunho") or "").strip()
        with db.transaction() as con:
            if not WA.conversa(con, conversa_id):
                abort(404)
            WA.salvar_rascunho(con, conversa_id, texto, agora=db.now())
        audit("wa_rascunho", "wa_conversa", conversa_id, None)
        flash("Rascunho guardado. Nao foi enviado ao WhatsApp.", "success")
        return redirect(url_for("whatsapp_conversa", conversa_id=conversa_id))

    @app.route("/whatsapp/<int:conversa_id>/enviar", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def whatsapp_enviar(conversa_id: int):
        # MONTAR, POSTAR E GRAVAR (26/10/2026): o POST na Graph ficava dentro
        # da transação, com a trava de escrita da casa presa até oito segundos.
        try:
            with _con() as con:
                d = WA.conversa(con, conversa_id)
                if not d:
                    abort(404)
                texto = (d.get("rascunho") or "").strip()
                if not texto:
                    raise WA.EnvioErro("Nao ha rascunho para enviar.")
                pedido = WA.montar_envio(con, d["wa_id"], texto)
            meta_id = WA.postar_envio(pedido)
            with db.transaction() as con:
                WA.gravar_saida(con, conversa_id, texto, meta_id, autor=_quem(),
                                agora=db.now())
        except WA.EnvioErro as e:
            flash(str(e), "danger")
            if "131047" in str(e):
                # A Meta recusou por janela de 24 h vencida: o caminho é o modelo.
                flash("Passaram as 24 horas da última mensagem do cliente: a Meta só "
                      "aceita um modelo aprovado. Use «Reabrir com o modelo» e, quando o "
                      "cliente responder, envie o rascunho.", "warning")
            # Sem o `, 400`: redirecionamento com status 400 o navegador não
            # segue, e o balcão via a página «Redirecting…» (27/10/2026).
            return redirect(url_for("whatsapp_conversa", conversa_id=conversa_id))
        audit("wa_enviar", "wa_conversa", conversa_id, {"ok": True})
        flash("Mensagem enviada no WhatsApp.", "success")
        return redirect(url_for("whatsapp_conversa", conversa_id=conversa_id))

    @app.route("/whatsapp/<int:conversa_id>/reabrir", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def whatsapp_reabrir(conversa_id: int):
        """REABRIR COM O MODELO (27/10/2026): fora da janela de 24 h, manda o
        `cartorio_retomar_atendimento` — só o nome do cartório. A resposta de
        verdade (o rascunho) vai em texto livre depois que o cliente responder,
        porque é a resposta dele que reabre a janela. Montar (lê), postar (rede,
        FORA da transação) e gravar."""
        try:
            with _con() as con:
                d = WA.conversa(con, conversa_id)
                if not d:
                    abort(404)
                falta = MODELOS.falta_para_enviar(con, _serventia())
                if falta:
                    raise MODELOS.ModeloRecusado(f"Não dá para reabrir: {falta}.")
                pedido = MODELOS.montar_envio_modelo(
                    con, d["wa_id"], MODELOS.RETOMAR,
                    [MODELOS.nome_no_modelo(con, _serventia())])
            meta_id = WA.postar_envio(pedido)
            with db.transaction() as con:
                WA.gravar_saida(con, conversa_id, pedido["texto"], meta_id,
                                autor=_quem(), agora=db.now(), tipo="modelo")
        except WA.EnvioErro as e:
            flash(str(e), "danger")
            # Sem o `, 400`, pelo mesmo motivo do envio: o navegador não segue.
            return redirect(url_for("whatsapp_conversa", conversa_id=conversa_id))
        audit("wa_reabrir_modelo", "wa_conversa", conversa_id,
              {"ok": True, "modelo": pedido["modelo"]})
        flash("Modelo de retomar enviado. Quando o cliente responder, a janela de 24 h "
              "reabre e o rascunho pode ser enviado.", "success")
        return redirect(url_for("whatsapp_conversa", conversa_id=conversa_id))

    @app.route("/whatsapp/<int:conversa_id>/resolver", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def whatsapp_resolver(conversa_id: int):
        with db.transaction() as con:
            if not WA.conversa(con, conversa_id):
                abort(404)
            WA.resolver(con, conversa_id, agora=db.now())
        audit("wa_resolver", "wa_conversa", conversa_id, None)
        flash("Conversa marcada como resolvida.", "success")
        return redirect(url_for("whatsapp_lista"))
