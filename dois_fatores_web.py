"""AS TELAS DA VERIFICAÇÃO EM DUAS ETAPAS — lote LG02, 19/10/2026.

São três lugares, e cada um é de uma pessoa diferente:

    /login/dois-fatores           o segundo passo da entrada: quem acertou a
                                  senha e ainda não está dentro
    /conta/dois-fatores           o próprio usuário: ativa, troca os códigos,
                                  desativa (com senha E código)
    /administrativo/gestor/...    o Gestor (ADMIN): exige por papel, desbloqueia
                                  e zera a de quem perdeu o celular

A MEIA-SESSÃO
    Quem acertou a senha de uma conta com verificação NÃO ganha `user_id` na
    sessão: ganha `df_uid`, que nenhuma rota com `login_required` reconhece.
    É por isso que a guarda não precisou mudar em rota nenhuma — a tela que não
    vê `user_id` manda para o login, como sempre mandou. A meia-sessão morre
    em cinco minutos (`PRAZO_DO_SEGUNDO_PASSO`).

O RASTRO
    Tudo vai para `audit_logs`, pelo mesmo `db.log` do login — e NUNCA o código,
    a chave ou o código de recuperação: o rastro diz o que aconteceu, não dá o
    meio de repetir.
"""
from __future__ import annotations

from datetime import datetime

from flask import (abort, flash, make_response, redirect, render_template,
                   request, session, url_for)

import dois_fatores as DF
from security import new_csrf_token

# OS PAPÉIS DA CASA — os mesmos de `app.ROLES` e de `database.create_user`. Não
# se importa de `app` porque `app` importa este módulo; há teste que compara.
PAPEIS = ("ADMIN", "MANAGER", "USER", "AUDITOR", "PAINEL")

_CHAVES_DA_MEIA_SESSAO = ("df_uid", "df_desde", "df_next", "df_cadastro")


def destino_seguro(proximo: str | None, padrao: str) -> str:
    """Só caminho DESTE sistema: `/algo`, e não `//outro-site` nem `http://`."""
    proximo = str(proximo or "")
    if proximo.startswith("/") and not proximo.startswith("//") and "\\" not in proximo:
        return proximo
    return padrao


def _sem_cache(resposta):
    """Tela com a chave ou com os códigos não fica no cache do navegador."""
    resposta = make_response(resposta)
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


def registrar_rotas(app, db, login_required, roles_required, audit):
    """Pendura as três telas e publica o desvio que o `/login` consulta."""

    pasta = app.config["DATA_DIR"]

    def _log(user, acao, detalhes=None):
        db.log(int(user["id"]), user["username"], acao, "USER", int(user["id"]),
               detalhes, request.remote_addr)

    def _limpar_meia_sessao():
        for chave in _CHAVES_DA_MEIA_SESSAO:
            session.pop(chave, None)

    def _meia_sessao():
        """O usuário que acertou a senha e falta o código — ou None.

        Confere o prazo e confere de novo que o cadastro continua ativo: a
        desativação vale na hora (LS01), inclusive no meio da entrada.
        """
        uid = session.get("df_uid")
        if not uid:
            return None
        try:
            desde = datetime.fromisoformat(session.get("df_desde") or "")
        except ValueError:
            desde = None
        agora = datetime.fromtimestamp(DF.relogio())
        if desde is None or (agora - desde).total_seconds() > DF.PRAZO_DO_SEGUNDO_PASSO:
            _limpar_meia_sessao()
            flash("O prazo para digitar o código acabou. Entre de novo.", "warning")
            return None
        user = db.get_user(int(uid))
        if not user or not user["active"]:
            _limpar_meia_sessao()
            return None
        return user

    def depois_da_senha(row, proximo):
        """O `/login` pergunta aqui, com a senha já conferida. Devolve a
        resposta do desvio, ou None quando a entrada segue como sempre foi.
        """
        with db.connect() as con:
            estado = DF.situacao(con, int(row["id"]))["estado"]
        exige = DF.exigido(db.get_setting, row["role"])
        if estado != DF.ATIVO and not exige:
            return None
        session.clear()
        session["csrf_token"] = new_csrf_token()
        session["df_uid"] = int(row["id"])
        session["df_desde"] = DF.agora_iso()
        session["df_next"] = destino_seguro(proximo, "")
        if estado == DF.ATIVO:
            _log(row, "LOGIN_DOIS_FATORES_PEDIDO")
            return redirect(url_for("login_dois_fatores"))
        session["df_cadastro"] = True
        _log(row, "LOGIN_DOIS_FATORES_CADASTRO_EXIGIDO", {"papel": row["role"]})
        return redirect(url_for("login_dois_fatores_cadastrar"))

    app.extensions["dois_fatores_depois_da_senha"] = depois_da_senha

    def _entrar(user, detalhes):
        destino = destino_seguro(session.get("df_next"), url_for("dashboard"))
        app.extensions["abrir_sessao"](user, detalhes)
        return destino

    def _contexto_da_chave(user, segredo):
        from markupsafe import Markup
        endereco = DF.endereco_do_aplicativo(segredo, user["username"])
        # O SVG É DA CASA (o `segno` desenha o endereço que montamos), e por
        # isso vai como `Markup` daqui — e não com `|safe` na tela.
        return {"qr_svg": Markup(DF.qr_em_svg(endereco)),
                "chave_digitavel": DF.chave_agrupada(segredo)}

    def _aviso_da_falha(resultado):
        if resultado["motivo"] == "bloqueado":
            return (f"Muitas tentativas erradas. A verificação desta conta está "
                    f"travada até {resultado['bloqueado_ate'][11:16]}.")
        if resultado["cofre_ilegivel"]:
            return ("O código não confere — e a chave guardada desta conta não "
                    "abre nesta instalação. Use um código de recuperação, ou "
                    "peça ao Gestor para zerar a verificação.")
        return "O código não confere."

    def _conferir_e_registrar(user, codigo, acao_da_falha):
        """Confere o código, grava a contagem e deixa o rastro da falha.

        O código de recuperação é procurado ANTES da transação (os PBKDF2 não
        seguram a trava de escrita da casa — LX20); a transação só grava.
        """
        with db.connect() as con:
            achado = DF.achar_codigo(con, int(user["id"]), codigo)
        with db.transaction() as con:
            resultado = DF.conferir(con, int(user["id"]), codigo, pasta=pasta,
                                    achado=achado)
        if not resultado["ok"]:
            _log(user, acao_da_falha, {"motivo": resultado["motivo"]})
            if resultado["bloqueou_agora"]:
                _log(user, "DOIS_FATORES_BLOQUEADO",
                     {"ate": resultado["bloqueado_ate"], "tentativas": DF.MAX_FALHAS})
        elif resultado["meio"] == DF.RECUPERACAO:
            _log(user, "DOIS_FATORES_RECUPERACAO_USADA",
                 {"restantes": resultado["restantes"]})
        return resultado

    def _codigos_se_o_primeiro_confere(uid, codigo):
        """Os dez códigos prontos — mas SÓ se o primeiro código confere. Só LÊ.

        `preparar_codigos` são dez PBKDF2 de 60 mil iterações, e ele rodava
        antes de saber se o código estava certo (LX20 #1): quem tem a sessão,
        ou a meia-sessão do login, gastava a CPU do servidor sem limite com
        POST de código errado. Conferir o TOTP é barato (decifrar a chave e
        três HMAC); por isso vem primeiro.

        Errado, devolve None, e o `confirmar` da transação recusa com a frase
        de sempre ANTES de chegar aos códigos — nenhum PBKDF2. A conferência de
        verdade continua a da transação, com a linha presa: esta é só o filtro
        do custo (se o passo virar entre as duas e o código valer lá dentro, os
        códigos se calculam na transação — raro, e certo). A ativação pendente não conta tentativas (a chave é a que a
        própria pessoa tem na tela); a troca de códigos confere o código pelo
        `conferir`, que conta e respeita o bloqueio, antes de chegar aqui.
        """
        with db.connect() as con:
            segredo = DF.segredo_pendente(con, uid, pasta)
        if segredo is None or DF.passo_aceito(segredo, codigo, DF.relogio()) is None:
            return None
        return DF.preparar_codigos()  # fora da transação: são dez PBKDF2

    # ------------------------------------------------ o segundo passo da entrada

    @app.route("/login/dois-fatores", methods=["GET", "POST"])
    def login_dois_fatores():
        """O código do aplicativo (ou um de recuperação), depois da senha."""
        user = _meia_sessao()
        if user is None or session.get("df_cadastro"):
            return redirect(url_for("login"))
        if request.method == "POST":
            resultado = _conferir_e_registrar(
                user, request.form.get("codigo", ""), "LOGIN_DOIS_FATORES_FALHA")
            if resultado["ok"]:
                destino = _entrar(user, {"segundo_fator": resultado["meio"]})
                if resultado["meio"] == DF.RECUPERACAO:
                    flash(f"Você entrou com um código de recuperação. Restam "
                          f"{resultado['restantes']}. Se o celular se perdeu, "
                          f"desative e ative de novo em «Verificação em duas "
                          f"etapas».", "warning")
                return redirect(destino)
            if resultado["motivo"] == "sem_dois_fatores":
                # O Gestor zerou a verificação enquanto a pessoa digitava:
                # recomeça pela senha, e a entrada segue a regra de agora.
                _limpar_meia_sessao()
                flash("A verificação desta conta mudou. Entre de novo.", "warning")
                return redirect(url_for("login"))
            flash(_aviso_da_falha(resultado), "danger")
            return redirect(url_for("login_dois_fatores"))
        return render_template("login_dois_fatores.html", conta=user["username"],
                               tentativas=DF.MAX_FALHAS, bloqueio=DF.BLOQUEIO_MINUTOS)

    @app.route("/login/dois-fatores/cadastrar", methods=["GET", "POST"])
    def login_dois_fatores_cadastrar():
        """A ativação OBRIGATÓRIA, na entrada de quem o Gestor exigiu.

        O GET não grava: a chave nasce no POST «gerar a chave». O código
        certo ativa, abre a sessão e mostra os códigos de recuperação — uma vez.
        """
        user = _meia_sessao()
        if user is None or not session.get("df_cadastro"):
            return redirect(url_for("login"))
        uid = int(user["id"])
        if request.method == "POST":
            if request.form.get("acao") == "iniciar":
                try:
                    with db.transaction() as con:
                        DF.iniciar(con, uid, pasta=pasta)
                except DF.DoisFatoresError as erro:
                    flash(str(erro), "danger")
                else:
                    _log(user, "DOIS_FATORES_INICIADO", {"na_entrada": True})
                return redirect(url_for("login_dois_fatores_cadastrar"))
            codigo = request.form.get("codigo", "")
            prontos = _codigos_se_o_primeiro_confere(uid, codigo)
            try:
                with db.transaction() as con:
                    codigos = DF.confirmar(con, uid, codigo, pasta=pasta,
                                           prontos=prontos)
            except DF.DoisFatoresError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("login_dois_fatores_cadastrar"))
            _log(user, "DOIS_FATORES_ATIVADO", {"na_entrada": True})
            destino = _entrar(user, {"segundo_fator": DF.TOTP, "ativado_agora": True})
            return _sem_cache(render_template("dois_fatores_codigos.html",
                                              codigos=codigos, seguir=destino))
        with db.connect() as con:
            segredo = DF.segredo_pendente(con, uid, pasta)
        contexto = _contexto_da_chave(user, segredo) if segredo else {}
        return _sem_cache(render_template("login_dois_fatores_cadastrar.html",
                                          conta=user["username"], pendente=bool(segredo),
                                          **contexto))

    # ------------------------------------------------------- a conta do usuário

    def _eu():
        return app.extensions["current_user"]()

    @app.route("/conta/dois-fatores")
    @login_required
    def dois_fatores():
        """A verificação de quem está logado. Só LÊ."""
        user = _eu()
        uid = int(user["id"])
        with db.connect() as con:
            sit = DF.situacao(con, uid)
            segredo = DF.segredo_pendente(con, uid, pasta) if sit["estado"] == DF.PENDENTE else None
        contexto = _contexto_da_chave(user, segredo) if segredo else {}
        return _sem_cache(render_template(
            "dois_fatores.html", sit=sit, exigido=DF.exigido(db.get_setting, user["role"]),
            pendente=bool(segredo), **contexto))

    @app.route("/conta/dois-fatores/iniciar", methods=["POST"])
    @login_required
    def dois_fatores_iniciar():
        user = _eu()
        try:
            with db.transaction() as con:
                DF.iniciar(con, int(user["id"]), pasta=pasta)
        except DF.DoisFatoresError as erro:
            flash(str(erro), "danger")
        else:
            audit("DOIS_FATORES_INICIADO", "USER", int(user["id"]))
        return redirect(url_for("dois_fatores"))

    @app.route("/conta/dois-fatores/cancelar", methods=["POST"])
    @login_required
    def dois_fatores_cancelar():
        user = _eu()
        with db.transaction() as con:
            cancelou = DF.cancelar(con, int(user["id"]))
        if cancelou:
            audit("DOIS_FATORES_CANCELADO", "USER", int(user["id"]))
        return redirect(url_for("dois_fatores"))

    @app.route("/conta/dois-fatores/confirmar", methods=["POST"])
    @login_required
    def dois_fatores_confirmar():
        """O primeiro código ativa; a resposta mostra os códigos, uma vez."""
        user = _eu()
        codigo = request.form.get("codigo", "")
        prontos = _codigos_se_o_primeiro_confere(int(user["id"]), codigo)
        try:
            with db.transaction() as con:
                codigos = DF.confirmar(con, int(user["id"]), codigo, pasta=pasta,
                                       prontos=prontos)
        except DF.DoisFatoresError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("dois_fatores"))
        audit("DOIS_FATORES_ATIVADO", "USER", int(user["id"]))
        return _sem_cache(render_template("dois_fatores_codigos.html", codigos=codigos,
                                          seguir=url_for("dois_fatores")))

    def _senha_e_codigo(user, acao_da_falha):
        """A senha E o código, os dois — é o que a especificação pede para
        desativar. Só a senha não basta: é justamente o que vazou quando o
        segundo fator faz falta."""
        if not db.authenticate(user["username"], request.form.get("senha", "")):
            audit(acao_da_falha, "USER", int(user["id"]), {"motivo": "senha"})
            flash("A senha não confere.", "danger")
            return False
        resultado = _conferir_e_registrar(user, request.form.get("codigo", ""),
                                          acao_da_falha)
        if not resultado["ok"]:
            flash(_aviso_da_falha(resultado), "danger")
        return resultado["ok"]

    @app.route("/conta/dois-fatores/desativar", methods=["POST"])
    @login_required
    def dois_fatores_desativar():
        user = _eu()
        if _senha_e_codigo(user, "DOIS_FATORES_DESATIVAR_RECUSADO"):
            with db.transaction() as con:
                DF.desativar(con, int(user["id"]))
            audit("DOIS_FATORES_DESATIVADO", "USER", int(user["id"]))
            flash("Verificação em duas etapas desativada.", "success")
        return redirect(url_for("dois_fatores"))

    @app.route("/conta/dois-fatores/codigos", methods=["POST"])
    @login_required
    def dois_fatores_codigos():
        user = _eu()
        if not _senha_e_codigo(user, "DOIS_FATORES_CODIGOS_RECUSADO"):
            return redirect(url_for("dois_fatores"))
        # Só depois da senha E do código (que conta tentativas e respeita o
        # bloqueio): código errado não chega aos dez PBKDF2 (LX20 #1).
        prontos = DF.preparar_codigos()  # fora da transação: são dez PBKDF2
        try:
            with db.transaction() as con:
                codigos = DF.trocar_codigos(con, int(user["id"]), prontos=prontos)
        except DF.DoisFatoresError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("dois_fatores"))
        audit("DOIS_FATORES_CODIGOS_NOVOS", "USER", int(user["id"]))
        return _sem_cache(render_template("dois_fatores_codigos.html", codigos=codigos,
                                          seguir=url_for("dois_fatores")))

    # ------------------------------------------------------------ o Gestor

    @app.route("/administrativo/gestor/dois-fatores")
    @login_required
    @roles_required("ADMIN")
    def gestor_dois_fatores():
        """Quem tem a verificação, quem está travado e o que se exige. Só LÊ."""
        with db.connect() as con:
            linhas = DF.resumo_da_casa(con)
        return render_template("gestor_dois_fatores.html", linhas=linhas, papeis=PAPEIS,
                               exigidos=DF.papeis_exigidos(db.get_setting))

    @app.route("/administrativo/gestor/dois-fatores/exigir", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def gestor_dois_fatores_exigir():
        """Grava para que papéis o segundo fator é obrigatório.

        Vale na PRÓXIMA entrada de cada um: quem já está dentro não é posto
        para fora no meio do ato.
        """
        import json
        papeis = [p for p in PAPEIS if request.form.get(f"papel_{p}") == "1"]
        db.set_settings({DF.CHAVE_DA_EXIGENCIA: json.dumps(papeis)})
        audit("DOIS_FATORES_EXIGENCIA_ALTERADA", "SETTINGS", None, {"papeis": papeis})
        flash("Exigência gravada. Vale na próxima entrada de cada usuário.", "success")
        return redirect(url_for("gestor_dois_fatores"))

    def _alvo_do_gestor():
        try:
            uid = int(request.form.get("user_id") or 0)
        except ValueError:
            uid = 0
        alvo = db.get_user(uid) if uid else None
        if not alvo:
            abort(404)
        return alvo

    @app.route("/administrativo/gestor/dois-fatores/desbloquear", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def gestor_dois_fatores_desbloquear():
        alvo = _alvo_do_gestor()
        with db.transaction() as con:
            DF.desbloquear(con, int(alvo["id"]))
        audit("DOIS_FATORES_DESBLOQUEADO", "USER", int(alvo["id"]))
        flash(f"Tentativas zeradas para {alvo['username']}.", "success")
        return redirect(url_for("gestor_dois_fatores"))

    @app.route("/administrativo/gestor/dois-fatores/zerar", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def gestor_dois_fatores_zerar():
        """Apaga a verificação de quem perdeu o celular E os códigos.

        Pede a senha do PRÓPRIO Gestor e o motivo: é a porta que contorna o
        segundo fator de outra pessoa, e por isso ela não abre com uma sessão
        esquecida aberta no balcão. A própria conta não se zera por aqui — o
        dono desativa na tela dele, com senha e código.
        """
        alvo = _alvo_do_gestor()
        eu = _eu()
        motivo = " ".join((request.form.get("motivo") or "").split())[:200]
        if int(alvo["id"]) == int(eu["id"]):
            flash("A própria verificação se desativa em «Verificação em duas etapas», "
                  "com senha e código.", "danger")
        elif not motivo:
            flash("Diga o motivo — ele fica no rastro.", "danger")
        elif not db.authenticate(eu["username"], request.form.get("senha", "")):
            audit("DOIS_FATORES_ZERAR_RECUSADO", "USER", int(alvo["id"]), {"motivo": "senha"})
            flash("A sua senha não confere.", "danger")
        else:
            with db.transaction() as con:
                DF.desativar(con, int(alvo["id"]))
            audit("DOIS_FATORES_ZERADO_PELO_GESTOR", "USER", int(alvo["id"]),
                  {"usuario": alvo["username"], "motivo": motivo})
            flash(f"Verificação de {alvo['username']} zerada. Se o papel dele "
                  f"exige, ele cadastra o celular de novo na próxima entrada.", "success")
        return redirect(url_for("gestor_dois_fatores"))
