"""As telas da OUVIDORIA e da PESQUISA DE SATISFAÇÃO (26/10/2026).

A regra mora em `ouvidoria` e em `satisfacao`; aqui só se ligam os fios.

QUEM VÊ O QUÊ
    - Ouvidoria: o balcão (USER), o gerente e o oficial registram; o AUDITOR
      vê a lista e o relatório e não grava. A identificação de quem se
      manifestou só abre na ficha, para o oficial, o gerente e o responsável
      — e cada abertura fica na auditoria (`OUVIDORIA_IDENTIFICACAO_VISTA`).
    - Pesquisa: o convite (o QR) é de quem atende; o relatório é do oficial,
      do gerente e do auditor; abrir a página sem login é SÓ do oficial.

A PÁGINA SEM LOGIN
    `/satisfacao` é a única rota deste módulo que não pede login, e por isso
    tem três guardas próprias: nasce FECHADA (o oficial abre), tem teto de
    avaliações por aparelho em dez minutos (contado na memória do servidor, e
    não no banco — o banco não guarda nada do aparelho), e o corpo do POST
    anônimo já tem o teto geral do `before_request`. O token de formulário
    vale aqui como em toda tela.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from datetime import date

from flask import abort, flash, redirect, render_template, request, url_for
from markupsafe import Markup

import ouvidoria as OU
import satisfacao as SAT
from bd_nativo import ERROS_DO_BANCO, banco
from seguranca_web import PRATICA  # o AUDITOR vê e não grava

VEEM = PRATICA + ("AUDITOR",)
RELATORIO = ("ADMIN", "MANAGER", "AUDITOR")

#: Avaliações por aparelho a cada dez minutos, na página sem login. Um
#: tablet de balcão com fila cheia não passa de uma por minuto.
TETO_POR_APARELHO = 20
JANELA_SEGUNDOS = 600


def _qr_em_svg(endereco: str) -> str:
    """O QR do convite. Sem o `segno`, vazio — o link continua na tela."""
    try:
        import segno
    except ImportError:
        return ""
    return segno.make(endereco, error="m").svg_inline(scale=5)


def _periodo() -> tuple[str, str]:
    """O período do relatório: o mês corrente, se a tela não disser outro."""
    hoje = date.today()
    de = (request.args.get("de") or "").strip()[:10] or hoje.replace(day=1).isoformat()
    ate = (request.args.get("ate") or "").strip()[:10] or hoje.isoformat()
    try:
        date.fromisoformat(de)
        date.fromisoformat(ate)
    except ValueError:
        de, ate = hoje.replace(day=1).isoformat(), hoje.isoformat()
    return de, ate


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    current_user = app.extensions["current_user"]
    usuario_id = app.extensions["usuario_id"]
    segredo = app.config["SECRET_KEY"]

    # As tabelas nascem na subida do banco (`database`, `init_ouvidoria_schema`).

    def _usuarios():
        return [u for u in db.list_users(active_only=True) if not u.get("eh_robo")]

    def _responsavel_padrao() -> int | None:
        try:
            escolhido = int(db.get_setting(OU.CHAVE_RESPONSAVEL, "") or 0)
        except ValueError:
            escolhido = 0
        ativos = _usuarios()
        if escolhido and any(int(u["id"]) == escolhido for u in ativos):
            return escolhido
        admins = [u for u in ativos if u["role"] == "ADMIN"]
        return int(admins[0]["id"]) if admins else None

    def _tarefa_aberta(tarefa_id) -> bool:
        if not tarefa_id:
            return False
        with db.connect() as con:
            t = banco(con).um("SELECT status FROM tasks WHERE id = %s", (int(tarefa_id),))
        return bool(t) and t["status"] not in ("CONCLUIDA", "CANCELADA")

    def _concluir_tarefa(m: dict, nota: str) -> None:
        """A manifestação respondida (ou encerrada) fecha a tarefa dela."""
        if not _tarefa_aberta(m.get("tarefa_id")):
            return
        uid = usuario_id()
        db.add_task_note(int(m["tarefa_id"]), uid, nota)
        db.update_task(int(m["tarefa_id"]), {"status": "CONCLUIDA"}, uid)

    # ------------------------------------------------------------ ouvidoria

    @app.route("/administrativo/ouvidoria")
    @roles_required(*VEEM)
    def ouvidoria_lista():
        f = {"situacao": (request.args.get("situacao") or "EM_ABERTO")[:20],
             "tipo": (request.args.get("tipo") or "")[:20],
             "de": (request.args.get("de") or "")[:10],
             "ate": (request.args.get("ate") or "")[:10]}
        u = current_user()
        with db.connect() as con:
            linhas = OU.listar(con, **f)
        for x in linhas:
            x["assunto"] = OU.assunto_na_lista(x, u)
        return render_template(
            "ouvidoria.html", linhas=linhas, f=f, tipos=OU.TIPOS, canais=OU.CANAIS,
            setores=OU.SETORES, situacoes=OU.SITUACOES, usuarios=_usuarios(),
            responsavel_padrao=_responsavel_padrao(), hoje=date.today().isoformat(),
            prazo_dias=OU.prazo_em_dias(db.get_setting),
            pode_registrar=u["role"] in PRATICA, e_admin=u["role"] == "ADMIN",
            prazo_padrao=OU.PRAZO_PADRAO_DIAS)

    @app.route("/administrativo/ouvidoria", methods=["POST"])
    @roles_required(*PRATICA)
    def ouvidoria_registrar():
        uid = usuario_id()
        try:
            with db.transaction() as con:
                novo = OU.registrar(con, request.form, por=uid, agora=db.now(),
                                    prazo_dias=OU.prazo_em_dias(db.get_setting))
        except OU.OuvidoriaError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ouvidoria_lista"))
        # A TAREFA DEPOIS DO COMMIT: `create_task` abre a transação dela, e a
        # casa já não deixa nascer duas iguais (`source_ref` é a manifestação).
        with db.connect() as con:
            m = OU.ler(con, novo["id"])
        tid = db.create_task(OU.dados_da_tarefa(m), user_id=uid)
        with db.transaction() as con:
            OU.amarrar_tarefa(con, novo["id"], tid)
        audit("OUVIDORIA_REGISTRADA", "ou_manifestacoes", novo["id"],
              {"numero": novo["numero"], "tipo": m["tipo"], "canal": m["canal"],
               "anonima": bool(m["anonima"]), "tarefa_id": tid})
        flash(f"Manifestação {novo['numero']} registrada. Prazo de resposta: "
              f"{date.fromisoformat(novo['prazo']).strftime('%d/%m/%Y')}. "
              f"A tarefa #{tid} foi aberta para o responsável.", "success")
        return redirect(url_for("ouvidoria_ficha", manifestacao_id=novo["id"]))

    @app.route("/administrativo/ouvidoria/<int:manifestacao_id>")
    @roles_required(*VEEM)
    def ouvidoria_ficha(manifestacao_id: int):
        u = current_user()
        with db.connect() as con:
            m = OU.ler(con, manifestacao_id)
            if not m:
                abort(404)
            historico = OU.andamentos(con, manifestacao_id)
        pediu = request.args.get("identificacao") == "1"
        tela = OU.para_a_tela(m, u, mostrar_identificacao=pediu)
        if tela["identificacao_aberta"]:
            audit("OUVIDORIA_IDENTIFICACAO_VISTA", "ou_manifestacoes", manifestacao_id,
                  {"numero": m["numero"]})
        return render_template("ouvidoria_ficha.html", m=tela, historico=historico,
                               usuarios=_usuarios(), hoje=date.today())

    def _acao(manifestacao_id: int, faz, sucesso: str, acao_audit: str, depois=None):
        u = current_user()
        with db.connect() as con:
            m = OU.ler(con, manifestacao_id)
        if not m:
            abort(404)
        if not OU.pode_tratar(m, u):
            abort(403)
        try:
            with db.transaction() as con:
                faz(con)
        except OU.OuvidoriaError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ouvidoria_ficha", manifestacao_id=manifestacao_id))
        if depois:
            depois(m)
        audit(acao_audit, "ou_manifestacoes", manifestacao_id, {"numero": m["numero"]})
        flash(sucesso, "success")
        return redirect(url_for("ouvidoria_ficha", manifestacao_id=manifestacao_id))

    @app.route("/administrativo/ouvidoria/<int:manifestacao_id>/analise", methods=["POST"])
    @roles_required(*PRATICA)
    def ouvidoria_em_analise(manifestacao_id: int):
        return _acao(manifestacao_id,
                     lambda con: OU.em_analise(con, manifestacao_id, por=usuario_id(),
                                               agora=db.now()),
                     "Manifestação marcada como em análise.", "OUVIDORIA_EM_ANALISE")

    @app.route("/administrativo/ouvidoria/<int:manifestacao_id>/encaminhar", methods=["POST"])
    @roles_required(*PRATICA)
    def ouvidoria_encaminhar(manifestacao_id: int):
        try:
            novo = int(request.form.get("responsavel_id") or 0)
        except ValueError:
            novo = 0
        if novo and not any(int(x["id"]) == novo for x in _usuarios()):
            novo = 0

        def _tarefa_junto(m):
            # A TAREFA VAI JUNTO com a manifestação: senão a lista de quem a
            # recebeu não mostra o que agora é dele.
            if _tarefa_aberta(m.get("tarefa_id")):
                db.update_task(int(m["tarefa_id"]), {"assigned_user_id": novo}, usuario_id())

        return _acao(manifestacao_id,
                     lambda con: OU.encaminhar(con, manifestacao_id, novo,
                                               motivo=request.form.get("motivo", ""),
                                               por=usuario_id(), agora=db.now()),
                     "Manifestação encaminhada. A tarefa foi junto.", "OUVIDORIA_ENCAMINHADA",
                     depois=_tarefa_junto)

    @app.route("/administrativo/ouvidoria/<int:manifestacao_id>/responder", methods=["POST"])
    @roles_required(*PRATICA)
    def ouvidoria_responder(manifestacao_id: int):
        return _acao(manifestacao_id,
                     lambda con: OU.responder(con, manifestacao_id,
                                              resposta=request.form.get("resposta", ""),
                                              por=usuario_id(), agora=db.now()),
                     "Resposta registrada. A tarefa da manifestação foi concluída.",
                     "OUVIDORIA_RESPONDIDA",
                     depois=lambda m: _concluir_tarefa(
                         m, f"Manifestação {m['numero']} respondida na ouvidoria."))

    @app.route("/administrativo/ouvidoria/<int:manifestacao_id>/encerrar", methods=["POST"])
    @roles_required(*PRATICA)
    def ouvidoria_encerrar(manifestacao_id: int):
        return _acao(manifestacao_id,
                     lambda con: OU.encerrar(con, manifestacao_id,
                                             motivo=request.form.get("motivo", ""),
                                             por=usuario_id(), agora=db.now()),
                     "Manifestação encerrada.", "OUVIDORIA_ENCERRADA",
                     depois=lambda m: _concluir_tarefa(
                         m, f"Manifestação {m['numero']} encerrada na ouvidoria."))

    @app.route("/administrativo/ouvidoria/relatorio")
    @roles_required(*RELATORIO)
    def ouvidoria_relatorio():
        de, ate = _periodo()
        with db.connect() as con:
            r = OU.relatorio(con, de=de, ate=ate)
        return render_template("ouvidoria_relatorio.html", r=r)

    @app.route("/administrativo/ouvidoria/configuracao", methods=["POST"])
    @roles_required("ADMIN")
    def ouvidoria_configurar():
        try:
            dias = OU.validar_prazo(request.form.get("prazo_dias"))
        except OU.OuvidoriaError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ouvidoria_lista"))
        try:
            resp = int(request.form.get("responsavel_padrao") or 0)
        except ValueError:
            resp = 0
        if resp and not any(int(x["id"]) == resp for x in _usuarios()):
            resp = 0
        db.set_settings({OU.CHAVE_PRAZO: str(dias), OU.CHAVE_RESPONSAVEL: str(resp or "")})
        audit("OUVIDORIA_CONFIGURADA", "settings", None,
              {"prazo_dias": dias, "responsavel_padrao": resp or None})
        flash(f"Prazo de resposta: {dias} dias corridos. Vale para as manifestações "
              "registradas daqui em diante.", "success")
        return redirect(url_for("ouvidoria_lista"))

    # ------------------------------------------------------------- pesquisa

    @app.route("/administrativo/satisfacao")
    @roles_required(*RELATORIO)
    def satisfacao_relatorio():
        de, ate = _periodo()
        with db.connect() as con:
            r = SAT.relatorio(con, de=de, ate=ate)
        return render_template("satisfacao_relatorio.html", r=r,
                               aberta=SAT.pagina_aberta(db.get_setting),
                               e_admin=current_user()["role"] == "ADMIN")

    @app.route("/administrativo/satisfacao/pagina", methods=["POST"])
    @roles_required("ADMIN")
    def satisfacao_abrir_pagina():
        abrir = request.form.get("aberta") == "1"
        db.set_settings({SAT.CHAVE_PAGINA_ABERTA: "1" if abrir else "0"})
        audit("SATISFACAO_PAGINA", "settings", None, {"aberta": abrir})
        flash("A página da pesquisa está ABERTA na rede da casa." if abrir
              else "A página da pesquisa está FECHADA.", "success")
        return redirect(url_for("satisfacao_relatorio"))

    @app.route("/administrativo/satisfacao/convite")
    @roles_required(*PRATICA)
    def satisfacao_convite():
        """O QR do convite: do protocolo (uma avaliação por ida ao balcão), ou
        do tablet do balcão, com quem está atendendo."""
        numero = (request.args.get("protocolo") or "").strip()[:40]
        balcao = request.args.get("balcao") == "1"
        token = endereco = qr = ""
        protocolo = None
        if numero:
            with db.connect() as con:
                protocolo = SAT.protocolo_por_numero(con, numero)
            if not protocolo:
                flash(f"Não achei o protocolo «{numero}». Confira o número no caixa.", "danger")
            else:
                token = SAT.assinar_convite(segredo, atendente_id=usuario_id(),
                                            protocolo_id=protocolo["id"],
                                            atribuicao=protocolo["atribuicao"] or "")
        elif balcao:
            token = SAT.assinar_convite(segredo, atendente_id=usuario_id())
        if token:
            endereco = url_for("satisfacao_pagina", t=token, _external=True)
            qr = Markup(_qr_em_svg(endereco))
        # QR com «localhost» só abre na própria máquina do servidor.
        local = request.host.split(":")[0] in ("localhost", "127.0.0.1", "[::1]")
        return render_template("satisfacao_convite.html", numero=numero, protocolo=protocolo,
                               balcao=balcao, endereco=endereco, qr=qr, local=local,
                               aberta=SAT.pagina_aberta(db.get_setting),
                               dias=SAT.DIAS_DO_CONVITE)

    # -------------------------------------------- a página sem login

    _aparelhos: dict[str, deque] = {}
    _trava = threading.Lock()

    def _passou_do_teto() -> bool:
        agora = time.monotonic()
        quem = request.remote_addr or "?"
        with _trava:
            fila = _aparelhos.setdefault(quem, deque())
            while fila and agora - fila[0] > JANELA_SEGUNDOS:
                fila.popleft()
            if len(fila) >= TETO_POR_APARELHO:
                return True
            fila.append(agora)
            # A memória não cresce sem fim: aparelho calado sai da conta.
            for chave in [k for k, v in _aparelhos.items() if not v]:
                _aparelhos.pop(chave, None)
        return False

    @app.route("/satisfacao", methods=["GET", "POST"])
    def satisfacao_pagina():
        if not SAT.pagina_aberta(db.get_setting):
            return render_template("satisfacao_pagina.html", fechada=True, notas=SAT.NOTAS), 404
        token = (request.values.get("t") or "")[:500]
        convite = SAT.ler_convite(segredo, token)
        chave = (SAT.chave_do_protocolo(segredo, convite["protocolo_id"])
                 if convite and convite.get("protocolo_id") else None)
        # O tablet do balcão volta ao formulário depois do «obrigado»; o
        # convite de um protocolo, não — ele já foi usado.
        volta = (url_for("satisfacao_pagina", t=token) if token and not chave
                 else url_for("satisfacao_pagina"))
        if request.method == "GET":
            with db.connect() as con:
                usado = SAT.ja_avaliado(con, chave)
            return render_template("satisfacao_pagina.html", notas=SAT.NOTAS, token=token,
                                   usado=usado)
        if _passou_do_teto():
            return render_template("satisfacao_pagina.html", notas=SAT.NOTAS, token=token,
                                   erro="Muitas avaliações seguidas deste aparelho. "
                                        "Tente de novo em alguns minutos."), 429
        try:
            with db.transaction() as con:
                SAT.registrar(con, nota=request.form.get("nota"),
                              comentario=request.form.get("comentario", ""),
                              dia=date.today(), convite=convite, protocolo_chave=chave)
        except SAT.SatisfacaoError as erro:
            return render_template("satisfacao_pagina.html", notas=SAT.NOTAS, token=token,
                                   erro=str(erro)), 400
        return render_template("satisfacao_pagina.html", notas=SAT.NOTAS, obrigado=True,
                               volta=volta, repetir=not chave)

    # --------------------------------------------------- o painel

    @app.context_processor
    def _ouvidoria_no_painel() -> dict:
        """O quadro da ouvidoria e da pesquisa no painel e nos relatórios —
        só para o oficial e o gerente, e só nessas duas telas."""
        from flask import session
        vazio = {"ouvidoria_no_painel": None}
        try:
            if (request.endpoint or "") not in ("dashboard", "reports") \
                    or not session.get("user_id"):
                return vazio
        except RuntimeError:
            return vazio
        u = current_user()
        if not u or u["role"] not in ("ADMIN", "MANAGER"):
            return vazio
        try:
            with db.connect() as con:
                return {"ouvidoria_no_painel": {
                    "ouvidoria": OU.numeros_do_painel(con),
                    "satisfacao": SAT.numeros_do_painel(con)}}
        except (*ERROS_DO_BANCO, RuntimeError, KeyError):
            # Tela não cai por causa de quadro do painel.
            return vazio

