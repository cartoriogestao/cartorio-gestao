"""As telas e as rotas da comunicação (T028). A regra mora em `comunicacao` e
`comunicacao_avisos`; aqui só se lê a sessão, se abre a transação e se desenha.

UMA TELA, DUAS MOLDURAS
    A gaveta da coluna da direita abre `/comunicacao/painel` num quadro da
    própria casa (`iframe`, permitido pelo `X-Frame-Options: SAMEORIGIN`), e a
    tela cheia `/comunicacao` desenha o MESMO pedaço (`_comunicacao_app.html`)
    dentro da moldura. Uma implementação só — duas seriam duas listas de defeitos.

O SERVIDOR DESENHA, O SCRIPT SÓ PEDE
    As mensagens novas chegam como HTML já escapado pelo Jinja (a ideia do
    htmx: o servidor devolve o pedaço de tela). O script não monta texto de
    mensagem: não há onde o HTML de alguém virar código na tela de outro.
    Sem script, tudo funciona por formulário comum, com recarga.

GET NÃO GRAVA (regra da casa, `nu_avisos_web`)
    Ler a conversa não marca nada. O «li até aqui» e o «vi o aviso» são POST
    que o script manda depois de mostrar.
"""
from __future__ import annotations

import re
import sqlite3

from flask import (abort, flash, jsonify, redirect, render_template, request,
                   send_file, session, url_for)
from markupsafe import Markup, escape

import comunicacao as CM
import comunicacao_avisos as CA
from seguranca_web import destino_interno

#: Endpoints que não desenham a insistência (não há tela de trabalho nelas).
_SEM_INSISTENCIA = frozenset({"login", "logout", "setup", "comunicacao_painel", "static"})

_URL = re.compile(r"(https?://[^\s<>\"']+)")


def _texto_html(texto: str, host: str) -> Markup:
    """O texto da mensagem: escapado, com quebras de linha e links clicáveis.

    Link da própria casa abre na janela de trabalho (`_top`, saindo da gaveta);
    link de fora abre em outra aba, sem levar a página junto (`noopener`).
    """
    seguro = str(escape(texto or ""))

    def ligar(m: re.Match) -> str:
        url = m.group(1)
        final = ""
        while url and url[-1] in ".,;:!?)":
            final = url[-1] + final
            url = url[:-1]
        de_casa = re.match(r"https?://" + re.escape(host) + r"(/|$)", url) is not None
        alvo = ' target="_top"' if de_casa else ' target="_blank" rel="noopener noreferrer"'
        return f'<a href="{url}"{alvo}>{url}</a>{final}'

    seguro = _URL.sub(ligar, seguro)
    return Markup(seguro.replace("\n", "<br>"))


def _hora(texto: str | None) -> str:
    return str(texto or "")[11:16]


def _dia(texto: str | None, hoje: str) -> str:
    d = str(texto or "")[:10]
    if not d:
        return ""
    if d == hoje[:10]:
        return "Hoje"
    try:
        from datetime import date, timedelta
        if date.fromisoformat(d) == date.fromisoformat(hoje[:10]) - timedelta(days=1):
            return "Ontem"
    except ValueError:
        pass
    return f"{d[8:10]}/{d[5:7]}/{d[:4]}"


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_id = app.extensions["usuario_id"]
    usuario_papel = app.extensions["usuario_papel"]
    raiz_dos_arquivos = app.extensions["archive_root"]

    def agora() -> str:
        return db.now()

    def _ip():
        return request.remote_addr

    def _quer_json() -> bool:
        return request.headers.get("X-Requested-With") == "fetch"

    def _embutido() -> bool:
        return (request.values.get("embutido") == "1"
                or request.endpoint == "comunicacao_painel")

    def _voltar(padrao: str):
        """Volta para a tela de onde veio — só caminho interno, pela régua da casa."""
        return redirect(destino_interno((request.values.get("next") or "").strip(), padrao))

    def _url_app(**args):
        if _embutido():
            return url_for("comunicacao_painel", **args)
        return url_for("comunicacao_inicio", **args)

    def _pedaco(nome: str, **contexto) -> str:
        """Um pedaço de tela para o script — direto do Jinja.

        `render_template` roda os processadores de contexto de TODA tela (avisos da
        serventia, navegação, a própria comunicação), e a conversa aberta pergunta a
        cada 4 s: seria a casa inteira recalculada por nada. O pedaço só precisa do
        token e da requisição.
        """
        return app.jinja_env.get_template(nome).render(
            csrf_token=session.get("csrf_token", ""), request=request, **contexto)

    @app.template_filter("cm_texto")
    def _filtro_texto(texto):
        return _texto_html(texto, request.host if request else "")

    app.jinja_env.globals.update(
        cm_hora=_hora, cm_tamanho=CM.tamanho_legivel, cm_primeiro_nome=CM.primeiro_nome,
        CM_URGENCIA=CA.NOME_DA_URGENCIA, CM_SITUACAO=CA.ROTULO_DA_SITUACAO,
        CM_GRAU=CA.NOME_DO_GRAU)

    # ------------------------------------------------ o que toda tela recebe

    def _estado(uid: int) -> dict:
        with db.connect() as con:
            ins = CA.insistencia(con, uid, agora=agora())
            nao_lidas = CM.total_nao_lidas(con, uid)
            ultima = CM.ultima_nao_lida(con, uid)
        return {"insistencia": ins, "nao_lidas": nao_lidas, "ultima": ultima,
                "pode_avisar": usuario_papel() in CA.CRIAM, "agora": agora()}

    @app.context_processor
    def _comunicacao_contexto():
        vazio = {"cm": None}
        try:
            endpoint = request.endpoint or ""
        except RuntimeError:
            return vazio
        uid = usuario_id()
        if not uid or endpoint in _SEM_INSISTENCIA:
            return vazio
        try:
            return {"cm": _estado(uid)}
        except (sqlite3.Error, ValueError):
            # A comunicação nunca derruba a tela de trabalho.
            return vazio

    # ------------------------------------------------ a conversa, nas duas molduras

    def _montar_app(uid: int, conversa_id: int | None, para: int | None, aba: str) -> dict:
        hoje = agora()
        papel = usuario_papel()
        with db.connect() as con:
            dados = {
                "conversas": CM.conversas_da_pessoa(con, uid),
                "pessoas": CM.pessoas(con, exceto=uid),
                "grupos_da_casa": CM.grupos(con),
                "avisos": CA.da_pessoa(con, uid, agora=hoje),
                "conversa": None, "mensagens": [], "recibo": None, "para": None,
                "primeira_nova": None, "tem_anteriores": False,
                "aba": aba, "agora": hoje, "embutido": _embutido(),
                "pode_avisar": papel in CA.CRIAM, "pode_acompanhar": papel in CA.ACOMPANHAM,
                "nomes_de_atribuicao": CM.nomes_de_atribuicao(),
                "papel": papel, "eu": uid,
            }
            if para and not conversa_id:
                existente = CM.direta_existente(con, uid, para)
                if existente:
                    conversa_id = int(existente)
                else:
                    alvo = CM.pessoa(con, para)
                    if alvo and int(alvo.get("active") or 0) and int(alvo["id"]) != uid:
                        dados["para"] = alvo
            if conversa_id:
                try:
                    c = CM.conversa_da_pessoa(con, conversa_id, uid)
                except CM.SemAcesso:
                    abort(404)
                msgs = CM.mensagens(con, c["id"], uid)
                lida = int(c.get("ultima_lida_id") or 0)
                dados.update(
                    conversa=c, mensagens=msgs, recibo=CM.recibo(con, c, uid),
                    primeira_nova=next((m["id"] for m in msgs if m["id"] > lida
                                        and int(m["autor_id"]) != uid), None),
                    tem_anteriores=len(msgs) >= CM.MENSAGENS_POR_PAGINA,
                    pode_gerir=CM.pode_gerir_grupo(c, uid, papel))
        dados["dia"] = lambda t: _dia(t, hoje)
        dados["pode_mudar"] = lambda m: CM.pode_mudar(m, uid, hoje)
        dados["url_app"] = _url_app
        return dados

    def _numero(nome: str) -> int | None:
        v = request.args.get(nome, "")
        return int(v) if v.isdigit() else None

    def _pagina_do_app(template: str):
        uid = usuario_id()
        aba = request.args.get("aba") or ("avisos" if request.args.get("aviso") else "conversas")
        dados = _montar_app(uid, _numero("c"), _numero("para"), aba)
        return render_template(template, **dados)

    @app.route("/comunicacao")
    @login_required
    def comunicacao_inicio():
        return _pagina_do_app("comunicacao.html")

    @app.route("/comunicacao/painel")
    @login_required
    def comunicacao_painel():
        return _pagina_do_app("comunicacao_painel.html")

    def _html_mensagens(con, conversa: dict, msgs: list[dict], uid: int) -> str:
        hoje = agora()
        return _pedaco(
            "_comunicacao_mensagens.html", mensagens=msgs, conversa=conversa, eu=uid,
            dia=lambda t: _dia(t, hoje), pode_mudar=lambda m: CM.pode_mudar(m, uid, hoje),
            primeira_nova=None, url_app=_url_app, embutido=_embutido())

    def _html_recibo(con, conversa: dict, uid: int) -> str:
        return _pedaco("_comunicacao_recibo.html", recibo=CM.recibo(con, conversa, uid))

    @app.route("/comunicacao/c/<int:conversa_id>/novas")
    @login_required
    def comunicacao_novas(conversa_id: int):
        """O que chegou depois da última que a tela tem (o script pergunta a cada 4 s)."""
        uid = usuario_id()
        depois = _numero("depois") or 0
        desde = request.args.get("desde") or agora()
        momento = agora()
        with db.connect() as con:
            try:
                c = CM.conversa_da_pessoa(con, conversa_id, uid)
                novas = CM.mensagens(con, conversa_id, uid, depois=depois)
                alteradas = CM.mensagens_alteradas(con, conversa_id, uid, desde=desde, ate_id=depois)
            except CM.SemAcesso:
                return jsonify(ok=False, erro="sem acesso"), 404
            return jsonify(
                ok=True, agora=momento,
                html=_html_mensagens(con, c, novas, uid) if novas else "",
                ultimo_id=max([m["id"] for m in novas], default=depois),
                alteradas={str(m["id"]): _html_mensagens(con, c, [m], uid) for m in alteradas},
                recibo=_html_recibo(con, c, uid))

    @app.route("/comunicacao/c/<int:conversa_id>/anteriores")
    @login_required
    def comunicacao_anteriores(conversa_id: int):
        uid = usuario_id()
        antes = _numero("antes") or 0
        with db.connect() as con:
            try:
                c = CM.conversa_da_pessoa(con, conversa_id, uid)
                msgs = CM.mensagens(con, conversa_id, uid, antes=antes)
            except CM.SemAcesso:
                return jsonify(ok=False), 404
            return jsonify(ok=True, html=_html_mensagens(con, c, msgs, uid),
                           primeiro_id=min([m["id"] for m in msgs], default=antes),
                           tem_mais=len(msgs) >= CM.MENSAGENS_POR_PAGINA)

    def _anexo_do_form(con, uid: int) -> int | None:
        arquivo = request.files.get("anexo")
        if not arquivo or not (arquivo.filename or "").strip():
            return None
        return CM.guardar_anexo(con, arquivo, raiz=raiz_dos_arquivos(), por=uid, agora=agora())

    def _resposta_do_envio(conversa_id: int, mid: int | None, erro: str | None = None):
        if _quer_json():
            if erro:
                return jsonify(ok=False, erro=erro), 400
            return jsonify(ok=True, conversa_id=conversa_id, mensagem_id=mid,
                           url=_url_app(c=conversa_id))
        if erro:
            flash(erro, "error")
        return redirect(_url_app(c=conversa_id) if conversa_id else _url_app())

    @app.route("/comunicacao/c/<int:conversa_id>/enviar", methods=["POST"])
    @login_required
    def comunicacao_enviar(conversa_id: int):
        uid = usuario_id()
        resposta = request.form.get("resposta_a", "")
        try:
            with db.transaction() as con:
                anexo = _anexo_do_form(con, uid)
                mid = CM.enviar(con, conversa_id, uid, texto=request.form.get("texto", ""),
                                agora=agora(), anexo_id=anexo,
                                resposta_a=int(resposta) if resposta.isdigit() else None,
                                token=request.form.get("token"))
        except CM.SemAcesso:
            abort(404)
        except CM.ComunicacaoErro as erro:
            return _resposta_do_envio(conversa_id, None, str(erro))
        return _resposta_do_envio(conversa_id, mid)

    @app.route("/comunicacao/para/<int:pessoa_id>/enviar", methods=["POST"])
    @login_required
    def comunicacao_enviar_para(pessoa_id: int):
        """A primeira mensagem para alguém: abre a conversa direta e manda."""
        uid = usuario_id()
        try:
            with db.transaction() as con:
                cid = CM.abrir_direta(con, uid, pessoa_id, agora=agora())
                anexo = _anexo_do_form(con, uid)
                mid = CM.enviar(con, cid, uid, texto=request.form.get("texto", ""),
                                agora=agora(), anexo_id=anexo, token=request.form.get("token"))
        except CM.ComunicacaoErro as erro:
            if _quer_json():
                return jsonify(ok=False, erro=str(erro)), 400
            flash(str(erro), "error")
            return redirect(_url_app(para=pessoa_id))
        return _resposta_do_envio(cid, mid)

    @app.route("/comunicacao/c/<int:conversa_id>/lida", methods=["POST"])
    @login_required
    def comunicacao_lida(conversa_id: int):
        uid = usuario_id()
        ate = request.form.get("ate", "")
        try:
            with db.transaction() as con:
                lida = CM.marcar_lida(con, conversa_id, uid, ate=int(ate) if ate.isdigit() else 0,
                                      agora=agora())
        except CM.SemAcesso:
            return jsonify(ok=False), 404
        return jsonify(ok=True, lida=lida)

    def _mudar_mensagem(mensagem_id: int, acao: str):
        uid = usuario_id()
        conversa_id = None
        try:
            with db.transaction() as con:
                conversa_id = int(CM.mensagem(con, mensagem_id, uid)["conversa_id"])
                if acao == "editar":
                    CM.editar(con, mensagem_id, uid, texto=request.form.get("texto", ""), agora=agora())
                else:
                    CM.apagar(con, mensagem_id, uid, agora=agora())
        except CM.SemAcesso:
            abort(404)
        except CM.ComunicacaoErro as erro:
            return _resposta_do_envio(conversa_id, None, str(erro))
        return _resposta_do_envio(conversa_id, mensagem_id)

    @app.route("/comunicacao/m/<int:mensagem_id>/editar", methods=["POST"])
    @login_required
    def comunicacao_editar(mensagem_id: int):
        return _mudar_mensagem(mensagem_id, "editar")

    @app.route("/comunicacao/m/<int:mensagem_id>/apagar", methods=["POST"])
    @login_required
    def comunicacao_apagar(mensagem_id: int):
        return _mudar_mensagem(mensagem_id, "apagar")

    @app.route("/comunicacao/anexo/<int:anexo_id>")
    @login_required
    def comunicacao_anexo(anexo_id: int):
        uid = usuario_id()
        with db.connect() as con:
            try:
                a = CM.anexo_para_baixar(con, anexo_id, uid, raiz=raiz_dos_arquivos())
            except CM.SemAcesso:
                abort(404)
        resposta = send_file(a["arquivo"], mimetype=a["tipo_mime"],
                             as_attachment=not a["imagem"], download_name=a["nome_original"])
        resposta.headers["Cache-Control"] = "private, max-age=3600"
        return resposta

    @app.route("/comunicacao/buscar")
    @login_required
    def comunicacao_buscar():
        uid = usuario_id()
        termo = request.args.get("q", "")
        with db.connect() as con:
            achados = CM.buscar(con, uid, termo)
        return render_template("comunicacao_buscar.html", termo=termo, achados=achados,
                               embutido=_embutido(), url_app=_url_app,
                               dia=lambda t: _dia(t, agora()))

    # ------------------------------------------------ grupos

    @app.route("/comunicacao/grupos/novo", methods=["GET", "POST"])
    @login_required
    def comunicacao_grupo_novo():
        uid = usuario_id()
        if request.method == "POST":
            try:
                with db.transaction() as con:
                    cid = CM.criar_grupo(con, nome=request.form.get("nome", ""),
                                         membros_ids=request.form.getlist("membros"),
                                         descricao=request.form.get("descricao", ""),
                                         criado_por=uid, agora=agora(), ip=_ip())
            except CM.ComunicacaoErro as erro:
                flash(str(erro), "error")
            else:
                flash("Grupo criado.", "success")
                return redirect(_url_app(c=cid))
        with db.connect() as con:
            pessoas = CM.pessoas(con, exceto=uid)
        return render_template("comunicacao_grupo.html", grupo=None, pessoas=pessoas,
                               membros_ids=set(), embutido=_embutido(), url_app=_url_app,
                               nomes_de_atribuicao=CM.nomes_de_atribuicao(), pode_gerir=True,
                               form=request.form)

    @app.route("/comunicacao/grupos/<int:conversa_id>", methods=["GET", "POST"])
    @login_required
    def comunicacao_grupo(conversa_id: int):
        uid = usuario_id()
        papel = usuario_papel()
        if request.method == "POST":
            acao = request.form.get("acao", "")
            try:
                with db.transaction() as con:
                    frase = CM.gerir_grupo(con, conversa_id, por=uid, papel=papel, acao=acao,
                                           agora=agora(), nome=request.form.get("nome", ""),
                                           membros_ids=request.form.getlist("membros"), ip=_ip())
            except CM.SemAcesso as erro:
                abort(404 if "não encontrado" in str(erro) else 403)
            except CM.ComunicacaoErro as erro:
                flash(str(erro), "error")
            else:
                flash(frase, "success")
                if acao in ("sair", "arquivar"):
                    return redirect(_url_app())
            return redirect(url_for("comunicacao_grupo", conversa_id=conversa_id,
                                    embutido="1" if _embutido() else None))
        with db.connect() as con:
            try:
                c = CM.conversa_da_pessoa(con, conversa_id, uid)
            except CM.SemAcesso:
                if papel not in CM.GEREM_TODOS_OS_GRUPOS:
                    abort(404)
                c = banco_grupo(con, conversa_id)
            pessoas = CM.pessoas(con)
        return render_template("comunicacao_grupo.html", grupo=c, pessoas=pessoas,
                               membros_ids={int(m["id"]) for m in c["membros"]},
                               embutido=_embutido(), url_app=_url_app,
                               nomes_de_atribuicao=CM.nomes_de_atribuicao(),
                               pode_gerir=CM.pode_gerir_grupo(c, uid, papel), form={})

    def banco_grupo(con, conversa_id: int) -> dict:
        """A gestão abre o grupo de que não participa (para gerir os da casa)."""
        from bd_nativo import banco
        c = banco(con).um("SELECT * FROM cm_conversas WHERE id=%s AND tipo='GRUPO' "
                          "AND arquivada_em IS NULL", (int(conversa_id),))
        if not c:
            abort(404)
        c = dict(c)
        c["titulo"] = c["nome"]
        c["membros"] = CM.membros(con, conversa_id)
        return c

    # ------------------------------------------------ avisos: quem recebe

    @app.route("/comunicacao/estado.json")
    @login_required
    def comunicacao_estado():
        """O que o script de toda tela pergunta a cada 30 s. Só lê."""
        uid = usuario_id()
        estado = _estado(uid)
        ins = estado["insistencia"]
        ultima = estado["ultima"]
        html = _pedaco("_comunicacao_insistencia.html", cm=estado)
        return jsonify(
            ok=True, nao_lidas=estado["nao_lidas"], esperando=ins["esperando"], grau=ins["grau"],
            ids=ins["ids"], html=html,
            versao=f"{ins['grau']}:{ins['ids']}:{(ins['cartao'] or {}).get('id')}:"
                   f"{(ins['faixa'] or {}).get('id')}:{ins['cartoes']}:{ins['faixas']}",
            ultima=None if not ultima else {
                "id": ultima["id"], "autor": ultima["autor"],
                "onde": ultima["nome"] if ultima["tipo"] == CM.GRUPO else "",
                "texto": (ultima["texto"] or ("Anexo" if ultima["anexo_id"] else ""))[:120],
                "url": url_for("comunicacao_painel", c=ultima["conversa_id"])})

    @app.route("/comunicacao/avisos/visto", methods=["POST"])
    @login_required
    def comunicacao_avisos_visto():
        uid = usuario_id()
        ids = request.form.getlist("ids") or (request.form.get("lista", "").split(","))
        with db.transaction() as con:
            n = CA.registrar_visto(con, uid, ids, agora=agora())
        return jsonify(ok=True, gravados=n)

    def _acao_do_aviso(aviso_id: int, faz):
        uid = usuario_id()
        try:
            with db.transaction() as con:
                faz(con, uid)
        except CM.SemAcesso:
            abort(404)
        except CM.ComunicacaoErro as erro:
            if _quer_json():
                return jsonify(ok=False, erro=str(erro)), 400
            flash(str(erro), "error")
        if _quer_json():
            return jsonify(ok=True)
        return _voltar(url_for("comunicacao_inicio", aba="avisos"))

    @app.route("/comunicacao/avisos/<int:aviso_id>/fazendo", methods=["POST"])
    @login_required
    def comunicacao_aviso_fazendo(aviso_id: int):
        return _acao_do_aviso(aviso_id, lambda con, uid: CA.marcar(
            con, aviso_id, uid, CA.FAZENDO, agora=agora(), ip=_ip()))

    @app.route("/comunicacao/avisos/<int:aviso_id>/feito", methods=["POST"])
    @login_required
    def comunicacao_aviso_feito(aviso_id: int):
        return _acao_do_aviso(aviso_id, lambda con, uid: CA.marcar(
            con, aviso_id, uid, CA.FEITO, agora=agora(), ip=_ip()))

    @app.route("/comunicacao/avisos/<int:aviso_id>/recolher", methods=["POST"])
    @login_required
    def comunicacao_aviso_recolher(aviso_id: int):
        return _acao_do_aviso(aviso_id, lambda con, uid: CA.recolher(con, aviso_id, uid, agora=agora()))

    @app.route("/comunicacao/avisos/<int:aviso_id>/abri", methods=["POST"])
    @login_required
    def comunicacao_aviso_abri(aviso_id: int):
        return _acao_do_aviso(aviso_id, lambda con, uid: CA.marcar_vista_aberta(
            con, aviso_id, uid, agora=agora()))

    # ------------------------------------------------ avisos: quem manda e confere

    @app.route("/comunicacao/avisos")
    @login_required
    @roles_required(*CA.ACOMPANHAM)
    def comunicacao_avisos():
        with db.connect() as con:
            avisos = CA.lista_da_gestao(con)
        return render_template("comunicacao_avisos.html", avisos=avisos,
                               pode_avisar=usuario_papel() in CA.CRIAM)

    @app.route("/comunicacao/avisos/<int:aviso_id>")
    @login_required
    @roles_required(*CA.ACOMPANHAM)
    def comunicacao_aviso_detalhe(aviso_id: int):
        with db.connect() as con:
            d = CA.detalhe(con, aviso_id, agora=agora())
        if not d:
            abort(404)
        papel = usuario_papel()
        pode_encerrar = (not d["aviso"]["encerrado_em"] and papel in CA.CRIAM
                         and (papel == "ADMIN" or int(d["aviso"]["criado_por"]) == int(usuario_id())))
        return render_template("comunicacao_aviso_detalhe.html", item=d["aviso"], destinos=d["destinos"],
                               eventos=d["eventos"], pode_encerrar=pode_encerrar)

    @app.route("/comunicacao/avisos/novo", methods=["GET", "POST"])
    @login_required
    @roles_required(*CA.CRIAM)
    def comunicacao_aviso_novo():
        uid = usuario_id()
        if request.method == "POST":
            destino_tipo = request.form.get("destino_tipo", "")
            ref = {CA.DESTINO_GRUPO: request.form.get("grupo_id"),
                   CA.DESTINO_PESSOA: request.form.get("pessoa_id")}.get(destino_tipo)
            try:
                with db.transaction() as con:
                    aid = CA.criar(con, titulo=request.form.get("titulo", ""),
                                   texto=request.form.get("texto", ""),
                                   urgencia=request.form.get("urgencia", CA.NORMAL),
                                   destino_tipo=destino_tipo, destino_ref=ref, por=uid,
                                   papel=usuario_papel(), agora=agora(), ip=_ip())
            except CM.ComunicacaoErro as erro:
                flash(str(erro), "error")
            except PermissionError:
                abort(403)
            else:
                flash("Aviso enviado. A insistência começa agora na tela de quem recebe.", "success")
                return redirect(url_for("comunicacao_aviso_detalhe", aviso_id=aid))
        with db.connect() as con:
            pessoas = CM.pessoas(con, exceto=uid)
            grupos = CM.grupos(con)
        return render_template("comunicacao_aviso_novo.html", pessoas=pessoas, grupos=grupos,
                               urgencias=CA.ROTULO_DA_URGENCIA, form=request.form,
                               nomes_de_atribuicao=CM.nomes_de_atribuicao())

    @app.route("/comunicacao/avisos/<int:aviso_id>/encerrar", methods=["POST"])
    @login_required
    @roles_required(*CA.CRIAM)
    def comunicacao_aviso_encerrar(aviso_id: int):
        try:
            with db.transaction() as con:
                CA.encerrar(con, aviso_id, por=usuario_id(), papel=usuario_papel(),
                            agora=agora(), ip=_ip())
        except CM.SemAcesso:
            abort(404)
        except PermissionError:
            abort(403)
        flash("Aviso encerrado. Ele sai da tela de todos; o histórico fica.", "success")
        return redirect(url_for("comunicacao_aviso_detalhe", aviso_id=aviso_id))

