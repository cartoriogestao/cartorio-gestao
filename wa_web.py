"""Telas e webhook do Balcao WhatsApp.

GET/POST /whatsapp/webhook — teste local e reenvio da caixa-postal.
  Sem login. CSRF isento. Em producao o inbound NAO chega direto aqui:
  o SERVIDOR do Cartorio Gestao nao expoe 8765 e nao roda tunel.

GET /whatsapp e as demais — mesmo login do resto do app.

A TELA DE CONVERSA (27/10/2026): `/whatsapp` e `/whatsapp/<id>` são a MESMA
tela, como num aplicativo — a lista à esquerda e a conversa em balões à
direita (`whatsapp_chat.html`). O `/novas` e o `/lista-parcial` só leem o
banco e devolvem o mesmo parcial da primeira carga: a tela mostra o que a
caixa-postal já trouxe, e nenhuma das duas fala com a Meta.

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

import re
import threading
from datetime import date, timedelta
from pathlib import Path

from flask import (abort, flash, jsonify, make_response, redirect, render_template, request,
                   send_file, url_for)

import agente_provedores as PROV
import serventia as SERV
import tetos_de_entrada as TETO
import wa_atendente as ATENDENTE
import wa_balcao as WA
import wa_contato as CONTATO
import wa_fila as FILA
import wa_midia as MIDIA
import wa_modelos as MODELOS
import wa_puxar as PUXAR
import wa_rotina as ROTINA
import wa_schema as SCH
import wa_vigia as VIGIA
from seguranca_web import PRATICA  # M2 (LX11): o AUDITOR vê e não grava


#: Quantas enviadas o `/novas` devolve com o estado da entrega (29/10/2026).
ENTREGAS_NO_NOVAS = 30

#: O cabeçalho que marca a resposta do `/whatsapp/lista-parcial` (o JS confere).
CABECALHO_DO_PARCIAL = "X-Wa-Parcial"

#: O token que o navegador gera para cada envio (`whatsapp_chat.js`).
ENVIO_TOKEN_VALIDO = re.compile(r"[A-Za-z0-9-]{1,64}")


def registrar_rotas(app, db, login_required, roles_required, audit):
    """Pendura a fila do WhatsApp no app ja construido."""
    # O texto da entrega no balão sai da mesma regra do `/novas`.
    app.jinja_env.globals["wa_rotulo_da_entrega"] = WA.rotulo_da_entrega

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

    def _filtro() -> dict:
        """A aba e os filtros pedidos. A aba que abre é «Sem responsável»."""
        aba = request.args.get("aba", "")
        # SEM O FILTRO «ETIQUETA» (segunda revisão do #73): as etiquetas saíram
        # da tela; os dados de `wa_etiqueta` ficam.
        return {"aba": aba if aba in dict(FILA.ABAS) else FILA.ABA_PADRAO,
                "setor": request.args.get("setor", ""),
                "vencidas": "1" if request.args.get("vencidas") == "1" else ""}

    def _lista(con, filtro: dict) -> tuple[list[dict], bool]:
        """As conversas da aba, filtradas NO BANCO, e se sobrou alguma além do
        limite das resolvidas. Cada linha leva a cor do setor e as iniciais."""
        linhas = FILA.listar(con, agora=db.now(), setor=filtro["setor"],
                             so_vencidas=bool(filtro["vencidas"]), aba=filtro["aba"],
                             usuario_id=app.extensions["usuario_id"]())
        ha_mais = len(linhas) > FILA.LIMITE_DAS_RESOLVIDAS
        linhas = linhas[:FILA.LIMITE_DAS_RESOLVIDAS]
        for r in linhas:
            r["cor_setor"] = FILA.cor_do_setor(r["setor"])
            r["iniciais"] = FILA.iniciais(r.get("nome"), r.get("wa_id"))
            r["iniciais_resp"] = (FILA.iniciais(r.get("responsavel_nome"))
                                  if r.get("responsavel_id") else "")
        return linhas, ha_mais

    def _contagens(con, filtro: dict) -> dict:
        return FILA.contar_por_aba(con, agora=db.now(),
                                   usuario_id=app.extensions["usuario_id"](),
                                   setor=filtro["setor"],
                                   so_vencidas=bool(filtro["vencidas"]))

    def _com_dias(mensagens: list[dict], dia_anterior: str = "") -> list[dict]:
        """Põe o separador de dia («hoje», «ontem», `dd/mm`) na mensagem em
        que o dia muda. `dia_anterior` é o da última que a tela já tem: o
        `/novas` não repete o separador do dia que já está na tela."""
        hoje = str(db.now())[:10]
        try:
            ontem = (date.fromisoformat(hoje) - timedelta(days=1)).isoformat()
        except ValueError:
            ontem = ""
        anterior = dia_anterior
        for m in mensagens:
            dia = str(m.get("criado_em") or "")[:10]
            m["separador"] = ""
            if dia and dia != anterior:
                m["separador"] = ("hoje" if dia == hoje else "ontem" if dia == ontem
                                  else f"{dia[8:10]}/{dia[5:7]}")
            anterior = dia or anterior
        return mensagens

    def _da_lista(filtro: dict) -> dict:
        """O que o parcial da lista precisa além das linhas: o filtro só com o
        que foi escolhido (para os endereços não levarem `?setor=&vencidas=`),
        quantos filtros estão ligados e o dia de hoje (a hora sem a data)."""
        escolhido = {k: v for k, v in filtro.items() if v and k != "aba"}
        manter = dict(escolhido)
        if filtro["aba"] != FILA.ABA_PADRAO:
            manter["aba"] = filtro["aba"]
        return {"filtro": filtro, "hoje": str(db.now())[:10], "abas": FILA.ABAS,
                "filtros_ligados": len(escolhido), "filtros_url": escolhido,
                "filtro_url": manter, "limite_resolvidas": FILA.LIMITE_DAS_RESOLVIDAS}

    @app.route("/whatsapp")
    @login_required
    def whatsapp_lista():
        return _tela(None)

    # O ATALHO COM O ALERTA (27/10/2026): o botão flutuante de toda tela logada
    # (`_whatsapp_atalho.html`) mostra quantas conversas esperam resposta.
    # Fica fora da própria tela do WhatsApp, onde seria redundante e cobriria
    # a caixa de escrever, e só para quem pode abrir o `/whatsapp`.
    TELAS_SEM_ATALHO = frozenset({"whatsapp_lista", "whatsapp_conversa"})

    def _pode_abrir_o_whatsapp() -> bool:
        """A mesma régua da guarda do `before_request` (o módulo da tela, o
        papel e a função cadastrada de quem está logado)."""
        import modulos as MOD
        import modulos_ligados as MODLIG
        u = app.extensions["current_user"]()
        if not u:
            return False
        funcao = u["funcao"] if "funcao" in u.keys() else None
        return MODLIG.pode_entrar(db.get_setting, MOD.modulo_da_tela("whatsapp_lista"),
                                  u["role"], funcao)

    @app.context_processor
    def _atalho_do_whatsapp():
        """Devolve uma FUNÇÃO, e não a contagem (revisão do #74): o
        `_whatsapp_atalho.html` a chama, e a contagem só roda quando o
        `base.html` desenha o atalho — nunca nos parciais, no `/novas` nem na
        lista que a tela pede a cada poucos segundos."""
        def wa_atalho():
            try:
                if (not app.extensions["usuario_id"]()
                        or not _pode_abrir_o_whatsapp()):
                    return None
                if request.endpoint in TELAS_SEM_ATALHO:
                    # O AVISO DE MENSAGEM NOVA VALE AQUI TAMBÉM (29/10/2026):
                    # sem o atalho, e sem contar — o JS pergunta sozinho.
                    return {"escondido": True}
                with _con() as con:
                    n = FILA.nao_respondidas(con, usuario_id=app.extensions["usuario_id"]())
                return FILA.rotulo_do_atalho(n)
            except Exception:                           # noqa: BLE001
                # uma contagem nunca derruba a tela: o atalho some, e o log diz
                app.logger.exception("o atalho do WhatsApp não conseguiu contar")
                return None
        return {"wa_atalho": wa_atalho}

    @app.route("/whatsapp/nao-respondidas")
    @login_required
    def whatsapp_nao_respondidas():
        """O número do alerta do atalho. SÓ LÊ, e nunca fala com a Meta. É
        pergunta automática: não renova a sessão (`app.py`)."""
        with _con() as con:
            n = FILA.nao_respondidas(con, usuario_id=app.extensions["usuario_id"]())
            ultima = FILA.ultima_entrada(con, usuario_id=app.extensions["usuario_id"]())
        resposta = FILA.rotulo_do_atalho(n)
        # A ÚLTIMA MENSAGEM DE CLIENTE (29/10/2026): é por ela que o navegador
        # sabe que chegou coisa nova e avisa pelo Windows (`whatsapp_atalho.js`).
        resposta["ultima"] = ultima
        return jsonify(resposta)

    @app.route("/whatsapp/lista-parcial")
    @login_required
    def whatsapp_lista_parcial():
        """A lista desenhada de novo, com os mesmos filtros. SÓ LÊ.

        O cabeçalho `X-Wa-Parcial` diz ao JS que veio a lista, e não outra
        página: a do login também é HTML, e não pode ir parar dentro da lista
        (revisão do #72)."""
        VIGIA.marcar_tela_aberta()
        bruto = (request.args.get("aberta") or "").strip()
        with _con() as con:
            linhas, ha_mais = _lista(con, _filtro())
        resposta = make_response(render_template(
            "_whatsapp_lista.html", linhas=linhas, ha_mais=ha_mais,
            aberta=int(bruto) if bruto.isdigit() else None, **_da_lista(_filtro())))
        resposta.headers[CABECALHO_DO_PARCIAL] = "lista"
        return resposta

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
            rotina = ROTINA.config(con)
        return render_template(
            "whatsapp_atendente.html", ia=ia, linhas=linhas, hoje=hoje,
            pode_enviar=pode_enviar,
            # SÓ O NOME E SE HÁ CHAVE: nenhum pedaço da chave chega ao HTML
            # desta tela, que todo login vê.
            provedores=[{"id": p["id"], "nome": p["nome"], "tem_chave": p["tem_chave"]}
                        for p in PROV.catalogo_para_tela(_pasta())],
            rotina=rotina, texto_fora_padrao=ROTINA.TEXTO_FORA_PADRAO,
            vigia_padrao=ROTINA.VIGIA_PADRAO_S, encerrar_padrao=ROTINA.ENCERRAR_PADRAO_DIAS,
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

    @app.route("/whatsapp/balcao", methods=["POST"])
    @login_required
    def whatsapp_balcao_config():
        """A ROTINA DO BALCÃO (29/10/2026): a busca do vigia, o horário, o aviso de
        fora do horário, as respostas prontas e o encerramento da conversa
        parada. Gravar é só do ADMIN, como o resto da configuração do WhatsApp."""
        if app.extensions["usuario_papel"]() != "ADMIN":
            abort(403)
        try:
            with db.transaction() as con:
                avisos = ROTINA.gravar(con, request.form)
        except ROTINA.RotinaErro as erro:
            flash(f"Nada foi guardado: {erro}", "danger")
            return redirect(url_for("whatsapp_atendente") + "#balcao")
        audit("wa_balcao_config", "wa_config", None,
              {"vigia_segundos": request.form.get("vigia_segundos", ""),
               "fora_ligado": request.form.get("fora_ligado") == "1",
               "encerrar_dias": request.form.get("encerrar_dias", "")})
        for aviso in avisos:
            flash(aviso, "warning")
        flash("Rotina do balcão guardada.", "success")
        return redirect(url_for("whatsapp_atendente") + "#balcao")

    def _mensagem(mensagem_id: int) -> dict:
        with _con() as con:
            from bd_nativo import banco
            m = banco(con).um("SELECT * FROM wa_mensagem WHERE id=%s", (int(mensagem_id),))
        if not m:
            abort(404)
        return dict(m)

    @app.route("/whatsapp/midia/<int:mensagem_id>")
    @login_required
    def whatsapp_midia(mensagem_id: int):
        """O ARQUIVO DA CONVERSA (29/10/2026): a foto, o PDF, o áudio e o vídeo
        abrem na tela; o resto baixa (`wa_midia.MOSTRA_NA_TELA`, a razão de
        `arquivo_visivel`). `?baixar=1` baixa sempre. A guarda é a do módulo:
        quem não abre o WhatsApp recebe 404, pelo `before_request`."""
        if not _pode_abrir_o_whatsapp():
            abort(404)
        m = _mensagem(mensagem_id)
        caminho = Path(m.get("arquivo_caminho") or "")
        if not m.get("arquivo_caminho") or not caminho.is_file():
            abort(404)
        mime, em_linha = MIDIA.tipo_para_servir(m)
        baixar = request.args.get("baixar") == "1" or not em_linha
        audit("wa_midia_aberta", "wa_mensagem", int(mensagem_id),
              {"conversa_id": m.get("conversa_id"), "baixou": baixar})
        resposta = send_file(caminho, mimetype=mime, as_attachment=baixar,
                             download_name=m.get("arquivo_nome") or caminho.name,
                             max_age=0)
        # Os MESMOS cabeçalhos de quem mostra anexo (`arquivo_visivel`): nada de
        # adivinhar o tipo, e nenhum script na página servida.
        import arquivo_visivel as ARQVIS
        for chave, valor in ARQVIS.cabecalhos_para_mostrar().items():
            resposta.headers[chave] = valor
        return resposta

    @app.route("/whatsapp/midia/<int:mensagem_id>/tentar", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def whatsapp_midia_tentar(mensagem_id: int):
        """O arquivo que não baixou volta à fila do vigia."""
        m = _mensagem(mensagem_id)
        with db.transaction() as con:
            voltou = MIDIA.tentar_de_novo(con, mensagem_id)
        flash("O arquivo volta a ser baixado em alguns segundos." if voltou
              else "Este arquivo não estava com erro.", "success" if voltou else "info")
        return redirect(url_for("whatsapp_conversa", conversa_id=int(m["conversa_id"])))

    @app.route("/whatsapp/<int:conversa_id>/arquivo", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def whatsapp_enviar_arquivo(conversa_id: int):
        """MANDAR UM ARQUIVO AO CLIENTE (29/10/2026): foto, PDF, documento,
        planilha, áudio ou vídeo, com legenda. Guardar (a casa fica com a cópia
        do que mandou), subir à Meta e mandar — a rede fora da transação — e
        gravar a saída com o arquivo, para o balão mostrá-lo."""
        enviado = request.files.get("arquivo")
        legenda = (request.form.get("legenda") or "").strip()
        if not enviado or not enviado.filename:
            flash("Escolha o arquivo.", "warning")
            return redirect(url_for("whatsapp_conversa", conversa_id=conversa_id))
        dados = enviado.read(MIDIA.TETO_DE_BYTES + 1)
        nome = Path(enviado.filename).name
        salvo = None
        try:
            if len(dados) > MIDIA.TETO_DE_BYTES:
                raise MIDIA.MidiaErro("O arquivo passa de 25 MB.")
            tipo, mime = MIDIA.conferir_envio(nome, len(dados))
            with _con() as con:
                d = WA.conversa(con, conversa_id)
                if not d:
                    abort(404)
                token = WA.ler_config(con, SCH.CHAVE_TOKEN)
                phone = WA.ler_config(con, SCH.CHAVE_PHONE)
            salvo = MIDIA.guardar(MIDIA.pasta_do_mes(app.extensions["archive_root"](),
                                                     db.now()), nome, dados)
            midia_id = MIDIA.subir(token, phone, dados, mime, salvo["nome"])
            with _con() as con:
                pedido = MIDIA.montar_envio(con, d["wa_id"], tipo, midia_id,
                                            legenda=legenda, nome=salvo["nome"])
            meta_id = WA.postar_envio(pedido)
            with db.transaction() as con:
                WA.gravar_saida(con, conversa_id, legenda, meta_id, autor=_quem(),
                                agora=db.now(), tipo=tipo,
                                arquivo={**salvo, "mime": mime})
        except (MIDIA.MidiaErro, WA.EnvioErro) as erro:
            # O que não saiu não fica guardado como se tivesse saído.
            if salvo and salvo.get("novo"):
                Path(salvo["caminho"]).unlink(missing_ok=True)
            flash(str(erro), "danger")
            if "131047" in str(erro):
                flash("Passaram as 24 horas da última mensagem do cliente: a Meta só "
                      "aceita um modelo aprovado. Use «Reabrir com o modelo».", "warning")
            return redirect(url_for("whatsapp_conversa", conversa_id=conversa_id))
        audit("wa_enviar_arquivo", "wa_conversa", conversa_id,
              {"tipo": tipo, "bytes": salvo["bytes"], "sha256": salvo["sha256"]})
        flash(f"Arquivo «{salvo['nome']}» enviado no WhatsApp.", "success")
        return redirect(url_for("whatsapp_conversa", conversa_id=conversa_id))

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

    def _vista(d: dict, historico: bool) -> dict:
        """A VISTA DA CONVERSA RETOMADA (27/10/2026). Com `atendimento_desde_id`,
        a vista curta mostra só o atendimento atual e conta o que ficou oculto;
        com `historico`, mostra tudo e marca onde o atendimento foi retomado.
        Sem `atendimento_desde_id`, mostra tudo, como antes. Nada se apaga."""
        todas = d["mensagens"]
        desde = int(d.get("atendimento_desde_id") or 0)
        retomadas = [e for e in d.get("eventos") or []
                     if e.get("tipo") == FILA.EV_RETOMADA]
        quando = str((retomadas[-1].get("quando") if retomadas else "") or "")
        vista = {"desde": desde, "historico": historico, "ocultas": 0,
                 "retomada_em": f"{quando[8:10]}/{quando[5:7]}" if quando else "",
                 # o /novas parte do maior id da conversa, MESMO OCULTO: depois
                 # de um «Reativar», a tela vazia não puxa o histórico de volta
                 "ultimo": max([int(m["id"]) for m in todas] or [0]),
                 "todas": todas}
        if not desde:
            return vista
        vista["ocultas"] = sum(1 for m in todas if int(m["id"]) < desde)
        if historico:
            primeira = next((m for m in todas if int(m["id"]) >= desde), None)
            if primeira:
                primeira["retomada"], primeira["retomada_em"] = True, vista["retomada_em"]
        else:
            d["mensagens"] = [m for m in todas if int(m["id"]) >= desde]
        return vista

    def _tela(conversa_id: int | None):
        """A tela única: a lista e, se houver, a conversa aberta."""
        filtro = _filtro()
        d = janela = vista = None
        usuarios: list = []
        with _con() as con:
            linhas, ha_mais = _lista(con, filtro)
            contagens = _contagens(con, filtro)
            busca_automatica = PUXAR.busca_automatica_ligada(con)
            cfg = WA.config_para_tela(con)
            ia = ATENDENTE.configuracao(con)
            pode = WA.pode_enviar_meta(con)
            rotina = ROTINA.config(con)
            if conversa_id is not None:
                d = WA.conversa(con, conversa_id)
                if not d:
                    abort(404)
                d["eventos"] = FILA.eventos(con, conversa_id)
                d["setor"] = FILA.setor_valido(d.get("setor")) or SCH.SETOR_PADRAO
                d["modo"] = d.get("modo") or SCH.MODO_IA
                d["registros"] = ATENDENTE.registros(con, conversa_id=conversa_id,
                                                     limite=20)
                d["cor_setor"] = FILA.cor_do_setor(d["setor"])
                # QUEM É (29/10/2026): a Meta não manda a foto do cliente; o
                # que a casa tem é o cartão de firma e o protocolo com o
                # mesmo telefone (`wa_contato`).
                d["contato"] = CONTATO.quem_e(con, d.get("wa_id"))
                d["iniciais"] = FILA.iniciais(d.get("nome"), d.get("wa_id"))
                vista = _vista(d, request.args.get("historico") == "1")
                d["sugestao_na_caixa"] = WA.sugestao_visivel(con, conversa_id, d.get("sugestao"))
                _com_dias(d["mensagens"])
                usuarios = FILA.usuarios_ativos(con)
                # A JANELA DE 24 H (27/10/2026): passada ela, a Meta recusa o
                # texto livre, e o caminho é o modelo de retomar.
                # a janela conta a última mensagem do cliente, MESMO OCULTA
                janela = {"fora": MODELOS.fora_da_janela(vista["todas"], db.now()),
                          "ligado": MODELOS.ligado(con),
                          "falta": MODELOS.falta_para_enviar(con, _serventia()),
                          "modelo": MODELOS.nome_do_modelo(con, MODELOS.RETOMAR)}
        return render_template("whatsapp_chat.html", linhas=linhas, cfg=cfg, ia=ia,
                               setores=SCH.SETORES,
                               ha_mais=ha_mais, contagens=contagens,
                               busca_automatica=busca_automatica, vista=vista,
                               **_da_lista(filtro), aberta=conversa_id, c=d,
                               pode_enviar=pode, usuarios=usuarios,
                               janela=janela, rotina=rotina,
                               usuario_id=app.extensions["usuario_id"](),
                               respostas=rotina["respostas"],
                               aceitos_no_envio=", ".join(sorted(MIDIA.ENVIO_POR_EXTENSAO)),
                               como_mostrar=MIDIA.como_mostrar,
                               rotulos_evento=FILA.ROTULO_DO_EVENTO,
                               rotulos_caso=ATENDENTE.ROTULO_DO_CASO)

    @app.route("/whatsapp/<int:conversa_id>")
    @login_required
    def whatsapp_conversa(conversa_id: int):
        return _tela(conversa_id)

    @app.route("/whatsapp/<int:conversa_id>/novas")
    @login_required
    def whatsapp_novas(conversa_id: int):
        """SÓ AS MENSAGENS NOVAS, desenhadas pelo mesmo parcial da primeira
        carga, e o estado da conversa. SÓ LÊ O BANCO: nunca fala com a Meta nem
        com a caixa-postal — quem traz a mensagem é o «puxar» ou a automação."""
        # A TELA ESTÁ ABERTA (30/10/2026): a busca do vigia fica mais atenta.
        VIGIA.marcar_tela_aberta()
        bruto = (request.args.get("depois") or "").strip()
        depois = int(bruto) if bruto.isdigit() else 0
        # UMA CONEXÃO SÓ, E SEM LER A CONVERSA INTEIRA (30/10/2026).
        with _con() as con:
            d = WA.cabecalho_da_conversa(con, conversa_id)
            if not d:
                abort(404)
            # O ATENDIMENTO ATUAL É O PISO (27/10/2026): fora da vista do histórico,
            # nada de antes de `atendimento_desde_id` volta à tela — nem com
            # `depois=0`, nem depois de um «Reativar».
            desde = int(d.get("atendimento_desde_id") or 0)
            piso = depois
            if desde and request.args.get("historico") != "1":
                piso = max(depois, desde - 1)
            novas = WA.mensagens_depois(con, conversa_id, piso)
            # o dia da última mensagem que a tela tem; com o piso subido, ela não
            # tem nenhuma do atendimento atual, e o primeiro balão leva o seu dia
            dia_anterior = (WA.dia_da_mensagem(con, conversa_id, depois)
                            if novas and piso == depois else "")
            enviadas = WA.ultimas_enviadas(con, conversa_id, ENTREGAS_NO_NOVAS)
            ultima = WA.ultima_do_cliente(con, conversa_id)
            sugestao = WA.sugestao_visivel(con, conversa_id, d.get("sugestao"))
        novas = _com_dias(novas, dia_anterior)
        html = (render_template("_whatsapp_baloes.html", mensagens=novas,
                                como_mostrar=MIDIA.como_mostrar) if novas else "")
        # A ENTREGA AO VIVO (29/10/2026): o estado das últimas enviadas, pronto
        # pelo `rotulo_da_entrega`, para o JS atualizar os balões que já estão
        # na tela.
        entregas = [{"id": int(m["id"]), "token": m.get("envio_token") or "",
                     **WA.rotulo_da_entrega(m.get("entrega"), m.get("entrega_erro"))}
                    for m in enviadas]
        return jsonify({"html": html, "entregas": entregas,
                        "ultimo": max([depois] + [int(m["id"]) for m in novas]),
                        "status": d.get("status") or "",
                        "modo": d.get("modo") or SCH.MODO_IA,
                        "sugestao": sugestao,
                        "janela_fora": MODELOS.fora_da_janela(ultima, db.now())})

    @app.route("/whatsapp/<int:conversa_id>/reativar", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def whatsapp_reativar(conversa_id: int):
        """«REATIVAR CONVERSA» (27/10/2026): a resolvida volta aberta sem esperar o
        cliente. A mesma regra da entrada (`FILA.retomar`): os 7 dias do
        responsável e o histórico oculto, que começa no próximo id — a tela abre
        vazia, com o «Ver histórico», e a próxima mensagem já aparece. Não é o
        «Reabrir com o modelo», que é a janela de 24 h da Meta."""
        with db.transaction() as con:
            d = WA.conversa(con, conversa_id)
            if not d:
                abort(404)
            if d.get("status") != SCH.RESOLVIDA:
                flash("Esta conversa não está resolvida: não há o que reativar.",
                      "warning")
                return redirect(url_for("whatsapp_conversa", conversa_id=conversa_id))
            proximo = max([int(m["id"]) for m in d["mensagens"]] or [0]) + 1
            r = FILA.retomar(con, d, desde_id=proximo, quando=db.now(), por=_quem(),
                             motivo="reativada pela tela")
        audit("wa_reativar", "wa_conversa", conversa_id,
              {"saiu_o_responsavel": r["saiu_o_responsavel"]})
        flash("Conversa reativada. O atendimento anterior está em «Ver histórico».",
              "success")
        if r["saiu_o_responsavel"]:
            flash(f"Ela voltou sem responsável: estava resolvida havia mais de "
                  f"{FILA.DIAS_COM_O_MESMO_RESPONSAVEL} dias.", "warning")
        return redirect(url_for("whatsapp_conversa", conversa_id=conversa_id))

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

    @app.route("/whatsapp/<int:conversa_id>/detalhes", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def whatsapp_detalhes(conversa_id: int):
        """O «OK» DA JANELINHA DE DETALHES (segunda revisão do #73, 27/10/2026):
        setor, responsável e «Usa IA» de uma vez. Compara com o BANCO e aplica
        só o que mudou, pelas funções de sempre — `FILA.transferir` (sem nota),
        `FILA.passar_para_pessoa` e `FILA.devolver_a_ia` —, com a auditoria
        com os nomes de sempre. Nada mudou: volta sem gravar."""
        setor = FILA.setor_valido(request.form.get("setor", ""))
        bruto = (request.form.get("responsavel_id") or "").strip()
        responsavel = int(bruto) if bruto.isdigit() else None
        usa_ia = request.form.get("usa_ia") == "1"
        feitas: list[tuple[str, dict | None]] = []
        try:
            with db.transaction() as con:
                c = WA.conversa(con, conversa_id)
                if not c:
                    abort(404)
                setor_antes = FILA.setor_valido(c.get("setor")) or SCH.SETOR_PADRAO
                setor = setor or setor_antes
                resp_antes = c.get("responsavel_id")
                resp_antes = int(resp_antes) if resp_antes else None
                ia_antes = (c.get("modo") or SCH.MODO_IA) != SCH.MODO_PESSOA
                if setor != setor_antes or responsavel != resp_antes:
                    FILA.transferir(con, conversa_id, setor, responsavel_id=responsavel,
                                    por=_quem(), nota="", quando=db.now())
                    feitas.append(("wa_transferir",
                                   {"setor": setor, "responsavel_id": responsavel}))
                if usa_ia != ia_antes:
                    if usa_ia:
                        FILA.devolver_a_ia(con, conversa_id, por=_quem(), quando=db.now())
                        feitas.append(("wa_devolver", None))
                    else:
                        FILA.passar_para_pessoa(con, conversa_id, setor=setor,
                                                motivo="passada pela tela",
                                                por=_quem(), quando=db.now())
                        feitas.append(("wa_passar", None))
        except ValueError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("whatsapp_conversa", conversa_id=conversa_id))
        if not feitas:
            flash("Nada mudou.", "info")
            return redirect(url_for("whatsapp_conversa", conversa_id=conversa_id))
        for acao, detalhe in feitas:
            audit(acao, "wa_conversa", conversa_id, detalhe)
        flash("Detalhes da conversa atualizados.", "success")
        return redirect(url_for("whatsapp_conversa", conversa_id=conversa_id))

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

    # O TOKEN EM CURSO (30/10/2026): o «tentar de novo» de uma resposta perdida
    # pode chegar com o primeiro POST ainda falando com a Graph. Nada está gravado,
    # e sem esta trava a mensagem sairia duas vezes. O servidor é um processo só.
    tokens_em_curso: set[tuple[int, str]] = set()
    trava_dos_tokens = threading.Lock()

    def _enviar_em_json(conversa_id: int):
        """O ENVIO DA FILA DA TELA (30/10/2026): o mesmo caminho, montar lendo,
        postar fora da transação e gravar, com JSON no lugar do `flash`. Não
        guarda rascunho: a fila manda uma mensagem atrás da outra, e o texto vem
        do pedido."""
        token = request.form.get("envio_token") or ""
        if not ENVIO_TOKEN_VALIDO.fullmatch(token):
            return jsonify({"ok": False, "motivo": "Envio recusado: identificador inválido."}), 400
        texto = (request.form.get("rascunho") or "").strip()
        if not texto:
            return jsonify({"ok": False, "token": token, "motivo": "Escreva a mensagem."}), 400
        chave = (conversa_id, token)
        with trava_dos_tokens:
            if chave in tokens_em_curso:
                return jsonify({"ok": False, "token": token, "em_curso": True,
                                "motivo": "A mensagem ainda está indo."}), 409
            tokens_em_curso.add(chave)
        try:
            with _con() as con:
                d = WA.cabecalho_da_conversa(con, conversa_id)
                if not d:
                    abort(404)
                gravada = WA.mensagem_por_token(con, conversa_id, token)
                pedido = None if gravada else WA.montar_envio(con, d["wa_id"], texto)
            if gravada:
                return jsonify({"ok": True, "id": int(gravada["id"]), "token": token,
                                **WA.rotulo_da_entrega(gravada.get("entrega"),
                                                       gravada.get("entrega_erro"))})
            meta_id = WA.postar_envio(pedido)
            with db.transaction() as con:
                mid = WA.gravar_saida(con, conversa_id, texto, meta_id, autor=_quem(),
                                      agora=db.now(), envio_token=token)
        except WA.EnvioErro as e:
            return jsonify({"ok": False, "token": token, "erro": str(e),
                            **WA.recusa_do_envio(e)}), 422
        finally:
            with trava_dos_tokens:
                tokens_em_curso.discard(chave)
        audit("wa_enviar", "wa_conversa", conversa_id, {"ok": True})
        return jsonify({"ok": True, "id": mid, "token": token, **WA.rotulo_da_entrega("", "")})

    @app.route("/whatsapp/<int:conversa_id>/enviar", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def whatsapp_enviar(conversa_id: int):
        if "application/json" in (request.headers.get("Accept") or ""):
            return _enviar_em_json(conversa_id)
        # MONTAR, POSTAR E GRAVAR (26/10/2026): o POST na Graph ficava dentro
        # da transação, com a trava de escrita da casa presa até oito segundos.
        #
        # O TEXTO DA CAIXA (27/10/2026): a tela de conversa manda o que está
        # escrito, no campo `rascunho` (o mesmo do «guardar rascunho», que
        # usa o mesmo formulário). Ele é guardado como rascunho, numa transação
        # só dele, e daí em diante o caminho é o de sempre. Sem o campo, envia
        # o rascunho guardado, como antes.
        if "rascunho" in request.form:
            escrito = (request.form.get("rascunho") or "").strip()
            if not escrito:
                flash("Escreva a mensagem.", "warning")
                return redirect(url_for("whatsapp_conversa", conversa_id=conversa_id))
            with db.transaction() as con:
                if not WA.conversa(con, conversa_id):
                    abort(404)
                WA.salvar_rascunho(con, conversa_id, escrito, agora=db.now())
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
