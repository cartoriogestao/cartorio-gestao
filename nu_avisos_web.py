"""Rotas e contexto do módulo de avisos gerenciáveis."""
from __future__ import annotations

import sqlite3

from flask import flash, jsonify, redirect, render_template, request, session, url_for

import nu_avisos_gestao as NAV
import tarefa_processo as TP


_MODAL_SUPRIMIDO = frozenset({
    "nu_avisos_lista",
    "nu_avisos_detalhe",
    "nu_avisos_admin_lista",
    "nu_avisos_admin_novo",
    "nu_avisos_admin_editar",
    "tasks",
    "task_detail",
})

def _dispensados_sessao() -> set[int]:
    raw = session.get("nu_avisos_dispensados") or []
    return {int(x) for x in raw}


def _marcar_dispensado_sessao(aviso_id: int) -> None:
    ids = _dispensados_sessao()
    ids.add(int(aviso_id))
    session["nu_avisos_dispensados"] = sorted(ids)


def _overlay_fechado(modo_teste: bool, hoje: str) -> bool:
    if modo_teste:
        return bool(session.get("nu_avisos_overlay_fechado"))
    return session.get("nu_avisos_overlay_data") == hoje


def _marcar_overlay_fechado(modo_teste: bool, hoje: str) -> None:
    if modo_teste:
        session["nu_avisos_overlay_fechado"] = True
    else:
        session["nu_avisos_overlay_data"] = hoje


def _dispensados_efetivos(con: sqlite3.Connection, uid: int, hoje: str) -> set[int]:
    if NAV.modal_modo_teste(con):
        return _dispensados_sessao()
    return NAV.ids_dispensados_hoje(con, uid, hoje=hoje)


def _prioridade_do_form(form) -> int:
    if form.get("critico") == "1":
        return 2
    if form.get("importante") == "1":
        return 1
    return 0


def _vigencia_do_form(form):
    ini = (form.get("vigencia_inicio") or "").strip() or None
    fim = (form.get("vigencia_fim") or "").strip() or None
    return ini, fim


def _recorrencia_do_form(form):
    rec = form.get("recorrente") == "1"
    hora = form.get("recorrencia_hora")
    raw = form.getlist("recorrencia_dias")
    dias: list[int] = []
    for x in raw:
        if x in (None, ""):
            continue
        dias.append(int(x))
    if not dias:
        leg = form.get("recorrencia_dia_semana")
        if leg not in (None, ""):
            dias = [int(leg)]
    mask = NAV.dias_bitmask(dias) if dias else None
    return rec, mask, (hora or None)


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_id = app.extensions["usuario_id"]
    usuario_nome = app.extensions["usuario_nome"]
    usuario_papel = app.extensions["usuario_papel"]

    def _lista_avisos_url():
        return url_for("nu_avisos_lista")

    def agora() -> str:
        return db.now()

    def _hoje() -> str:
        return NAV.data_local(agora())

    @app.context_processor
    def _nu_avisos_contexto():
        vazio = {
            "nu_avisos_pendentes": 0,
            "nu_avisos_modal": None,
            "nu_avisos_modal_teste": False,
            "nu_avisos_banner": False,
            "nu_avisos_itens": [],
            "nu_avisos_faixa_critica": None,
            "nu_avisos_faixa_vermelha": None,
            "nu_avisos_faixa_verde": None,
            "nu_avisos_ux_compacta": False,
            "nu_tarefas_faixa": None,
            "nu_tarefas_faixa_sem_responsavel": None,
        }
        try:
            request.endpoint
        except RuntimeError:
            return vazio
        uid = usuario_id()
        if not uid:
            return vazio
        try:
            # GET NÃO ABRE TRANSAÇÃO DE ESCRITA — regra da casa, guardada por
            # `tests/test_manutencao_diaria.py`. Este bloco roda em TODA tela, e
            # `db.transaction()` é `BEGIN IMMEDIATE`: com outro balcão gravando,
            # qualquer tela esperava o `busy_timeout` (medido em 14/10/2026: 83 s
            # para abrir cinco telas das Notas). Na conexão comum o SELECT não
            # trava nada; a trava só é pedida no UPDATE, quando há aviso
            # recorrente para reativar — e o `with` faz o commit.
            with db.connect() as con:
                con.row_factory = sqlite3.Row
                NAV.processar_recorrencias(con, agora=agora())
            with db.connect() as con:
                con.row_factory = sqlite3.Row
                dispensados = _dispensados_efetivos(con, uid, _hoje())
                pendentes = NAV.pendentes_para_usuario(
                    con, uid, hoje=_hoje(), dispensados=dispensados
                )
                modo_teste = NAV.modal_modo_teste(con)
                ux_compacta = NAV.banco_e_sandbox(con)
                overlay_fechado = _overlay_fechado(modo_teste, _hoje())
                papel = usuario_papel()
                tarefas_crit = TP.contagem_tier_critico_tarefas(con, uid)
                tarefas_alta = TP.contagem_tier_alta_tarefas(con, uid)
                tarefas_media, tarefas_baixa = TP.contagem_media_baixa_notificacao(con, uid)
                tarefas_media_baixa = int(tarefas_media or 0) + int(tarefas_baixa or 0)
                tarefas_sem_resp = (
                    TP.contagem_sem_responsavel_abertas(con)
                    if papel == "ADMIN"
                    else 0
                )
            crit = NAV.pendentes_criticos(pendentes)
            imp = NAV.pendentes_importantes(pendentes)
            nor = NAV.pendentes_normais(pendentes)
            tem_avisos = bool(pendentes)
            tem_tarefas = (tarefas_crit > 0 or tarefas_alta > 0 or tarefas_media_baixa > 0 or tarefas_sem_resp > 0)
            modal = None
            if (
                not overlay_fechado
                and (request.endpoint or "") not in _MODAL_SUPRIMIDO
                and (tem_avisos or tem_tarefas)
            ):
                bloco_tarefas_crit = None
                if tarefas_crit:
                    bloco_tarefas_crit = {
                        "texto": TP.texto_tarefas_criticas(tarefas_crit),
                        "url": url_for("tasks"),
                    }
                bloco_tarefas_alta = None
                if tarefas_alta:
                    bloco_tarefas_alta = {
                        "intro": TP.texto_tarefas_media_baixa_intro(tarefas_alta, 0),
                        "alta": tarefas_alta,
                        "url": url_for("tasks"),
                    }
                bloco_tarefas = None
                if tarefas_media_baixa:
                    bloco_tarefas = {
                        "intro": TP.texto_tarefas_media_baixa_intro(tarefas_media, tarefas_baixa),
                        "media": tarefas_media,
                        "baixa": tarefas_baixa,
                        "url": url_for("tasks"),
                    }
                bloco_sem_resp = None
                if tarefas_sem_resp:
                    bloco_sem_resp = {
                        "texto": TP.texto_sem_responsavel(tarefas_sem_resp),
                        "url": url_for("tasks"),
                    }
                modal = {
                    "criticos": crit,
                    "importantes": imp,
                    "normais": nor,
                    "url_fechar": url_for("nu_avisos_fechar_modal"),
                    "tarefas_criticas": bloco_tarefas_crit,
                    "tarefas_alta": bloco_tarefas_alta,
                    "tarefas": bloco_tarefas,
                    "sem_responsavel": bloco_sem_resp,
                }
            banner = bool(
                ux_compacta
                and overlay_fechado
                and (crit or imp or nor or tarefas_crit or tarefas_alta or tarefas_media_baixa)
            )
            faixa_critica = None
            faixa_vermelha = None
            faixa_verde = None
            if ux_compacta and (crit or tarefas_crit):
                faixa_critica = {
                    "avisos": crit,
                    "count_avisos": len(crit),
                    "tarefas_texto": TP.texto_tarefas_criticas(tarefas_crit)
                    if tarefas_crit
                    else None,
                    "tarefas_url": url_for("tasks"),
                }
            if ux_compacta and (imp or tarefas_alta):
                faixa_vermelha = {
                    "count": len(imp),
                    "itens": imp,
                    "tarefas_texto": TP.texto_tarefas_alta(tarefas_alta)
                    if tarefas_alta
                    else None,
                    "tarefas_url": url_for("tasks"),
                }
            if ux_compacta and nor:
                faixa_verde = {"count": len(nor), "itens": nor}
            nu_tarefas_faixa = None
            nu_tarefas_faixa_sem_resp = None
            if ux_compacta and tarefas_media_baixa:
                nu_tarefas_faixa = {
                    "intro": TP.texto_tarefas_media_baixa_intro(tarefas_media, tarefas_baixa),
                    "media": tarefas_media,
                    "baixa": tarefas_baixa,
                    "url": url_for("tasks"),
                }
            if ux_compacta and tarefas_sem_resp:
                nu_tarefas_faixa_sem_resp = {
                    "texto": TP.texto_sem_responsavel(tarefas_sem_resp),
                    "url": url_for("tasks"),
                }
            return {
                "nu_avisos_pendentes": len(pendentes),
                "nu_avisos_modal": modal,
                "nu_avisos_modal_teste": modo_teste,
                "nu_avisos_banner": banner,
                "nu_avisos_itens": pendentes if banner else [],
                "nu_avisos_faixa_critica": faixa_critica,
                "nu_avisos_faixa_vermelha": faixa_vermelha,
                "nu_avisos_faixa_verde": faixa_verde,
                "nu_avisos_ux_compacta": ux_compacta,
                "nu_tarefas_faixa": nu_tarefas_faixa,
                "nu_tarefas_faixa_sem_responsavel": nu_tarefas_faixa_sem_resp,
            }
        except sqlite3.Error:
            return vazio

    @app.route("/avisos")
    @login_required
    def nu_avisos_lista():
        if usuario_papel() == "ADMIN":
            with db.connect() as con:
                con.row_factory = sqlite3.Row
                linhas = NAV.listar_admin(con)
            return render_template("avisos_admin_lista.html", linhas=linhas)
        uid = usuario_id()
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            ativos = NAV.listar_ativos_vigentes(con, hoje=_hoje())
            dispensados = _dispensados_efetivos(con, uid, _hoje())
        return render_template(
            "avisos_lista.html",
            avisos=ativos,
            dispensados_hoje=dispensados,
            hoje=_hoje(),
        )

    @app.route("/avisos/<int:aviso_id>")
    @login_required
    def nu_avisos_detalhe(aviso_id: int):
        uid = usuario_id()
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            aviso = NAV.obter(con, aviso_id)
            if not aviso or not int(aviso["ativo"]):
                flash("Aviso não encontrado ou inativo.", "danger")
                return redirect(url_for("nu_avisos_lista"))
            dispensados = _dispensados_efetivos(con, uid, _hoje())
            aviso_view = dict(aviso)
        return render_template(
            "avisos_detalhe.html",
            aviso_item=aviso_view,
            aviso_id=aviso_id,
            dispensado_hoje=int(aviso_id) in dispensados,
            hoje=_hoje(),
        )

    @app.route("/avisos/<int:aviso_id>/dispensar", methods=["POST"])
    @login_required
    def nu_avisos_dispensar(aviso_id: int):
        uid = usuario_id()
        try:
            with db.connect() as con:
                modo_teste = NAV.modal_modo_teste(con)
                if not NAV.obter(con, aviso_id):
                    raise NAV.AvisoGestaoError("Aviso não encontrado.")
            with db.connect() as con:
                con.row_factory = sqlite3.Row
                aviso_row = NAV.obter(con, aviso_id)
                eh_prior = aviso_row and NAV.eh_prioritario(aviso_row)
            if modo_teste and not (eh_prior and usuario_papel() == "ADMIN"):
                _marcar_dispensado_sessao(aviso_id)
            else:
                with db.transaction() as con:
                    NAV.dispensar(
                        con,
                        user_id=uid,
                        aviso_id=aviso_id,
                        agora=agora(),
                        hoje=_hoje(),
                        papel=usuario_papel(),
                    )
        except NAV.AvisoGestaoError as erro:
            flash(str(erro), "danger")
            return redirect(request.referrer or url_for("nu_avisos_lista"))
        audit("NU_AVISO_DISPENSA", "nu_aviso_dispensa", aviso_id, {"user_id": uid})
        dest = request.form.get("next") or request.referrer or url_for("dashboard")
        return redirect(dest)


    @app.route("/avisos/fechar-modal", methods=["POST"])
    @login_required
    def nu_avisos_fechar_modal():
        uid = usuario_id()
        hoje = _hoje()
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            modo_teste = NAV.modal_modo_teste(con)
            ux_compacta = NAV.banco_e_sandbox(con)
            dispensados = _dispensados_efetivos(con, uid, hoje)
            pendentes = NAV.pendentes_para_usuario(
                con, uid, hoje=hoje, dispensados=dispensados
            )
        if ux_compacta and modo_teste:
            _marcar_overlay_fechado(True, hoje)
        else:
            if modo_teste:
                for av in pendentes:
                    _marcar_dispensado_sessao(int(av["id"]))
            else:
                with db.transaction() as con:
                    NAV.dispensar_todos_pendentes(
                        con,
                        user_id=uid,
                        agora=agora(),
                        hoje=hoje,
                        apenas_normais=True,
                        papel=usuario_papel(),
                    )
            _marcar_overlay_fechado(modo_teste, hoje)
        audit("NU_AVISO_FECHAR_MODAL", "nu_avisos", None, {"user_id": uid})
        dest = request.form.get("next") or request.referrer or url_for("dashboard")
        return redirect(dest)

    @app.route("/avisos/dispensar-normais-faixa", methods=["POST"])
    @login_required
    def nu_avisos_dispensar_normais_faixa():
        uid = usuario_id()
        try:
            with db.connect() as con:
                modo_teste = NAV.modal_modo_teste(con)
                dispensados = _dispensados_efetivos(con, uid, _hoje())
                nor = NAV.pendentes_normais(
                    NAV.pendentes_para_usuario(
                        con, uid, hoje=_hoje(), dispensados=dispensados
                    )
                )
            if modo_teste:
                for av in nor:
                    _marcar_dispensado_sessao(int(av["id"]))
                n = len(nor)
            else:
                with db.transaction() as con:
                    n = NAV.dispensar_todos_pendentes(
                        con,
                        user_id=uid,
                        agora=agora(),
                        hoje=_hoje(),
                        apenas_normais=True,
                        papel=usuario_papel(),
                    )
        except NAV.AvisoGestaoError as erro:
            flash(str(erro), "danger")
            return redirect(request.referrer or url_for("dashboard"))
        audit("NU_AVISO_DISPENSA_FAIXA_VERDE", "nu_aviso_dispensa", None, {"n": n})
        dest = request.form.get("next") or request.referrer or url_for("dashboard")
        return redirect(dest)

    @app.route("/avisos/dispensar-importantes-faixa", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def nu_avisos_dispensar_importantes_faixa():
        uid = usuario_id()
        try:
            with db.connect() as con:
                modo_teste = NAV.modal_modo_teste(con)
                dispensados = _dispensados_efetivos(con, uid, _hoje())
                imp = NAV.pendentes_importantes(
                    NAV.pendentes_para_usuario(
                        con, uid, hoje=_hoje(), dispensados=dispensados
                    )
                )
            if modo_teste:
                with db.transaction() as con:
                    for av in imp:
                        NAV.dispensar(
                            con,
                            user_id=uid,
                            aviso_id=int(av["id"]),
                            agora=agora(),
                            hoje=_hoje(),
                            papel=usuario_papel(),
                        )
                n = len(imp)
            else:
                with db.transaction() as con:
                    n = NAV.dispensar_todos_pendentes(
                        con,
                        user_id=uid,
                        agora=agora(),
                        hoje=_hoje(),
                        apenas_importantes=True,
                        papel=usuario_papel(),
                    )
        except NAV.AvisoGestaoError as erro:
            flash(str(erro), "danger")
            return redirect(request.referrer or url_for("dashboard"))
        audit("NU_AVISO_DISPENSA_FAIXA_VERMELHA", "nu_aviso_dispensa", None, {"n": n})
        dest = request.form.get("next") or request.referrer or url_for("dashboard")
        return redirect(dest)

    @app.route("/avisos/pendentes.json")
    @login_required
    def nu_avisos_pendentes_json():
        uid = usuario_id()
        with db.connect() as con:
            dispensados = _dispensados_efetivos(con, uid, _hoje())
            n = NAV.contar_pendentes(
                con, uid, hoje=_hoje(), dispensados=dispensados
            )
            modo_teste = NAV.modal_modo_teste(con)
        return jsonify({"pendentes": n, "hoje": _hoje(), "modo_teste": modo_teste})

    @app.route("/admin/avisos")
    @login_required
    @roles_required("ADMIN")
    def nu_avisos_admin_lista():
        return redirect(_lista_avisos_url())

    @app.route("/admin/avisos/novo", methods=["GET", "POST"])
    @login_required
    @roles_required("ADMIN")
    def nu_avisos_admin_novo():
        if request.method == "GET":
            return render_template("avisos_admin_form.html", aviso_item=None)
        try:
            with db.transaction() as con:
                rec, dias_mask, hh = _recorrencia_do_form(request.form)
                v_ini, v_fim = _vigencia_do_form(request.form)
                aid = NAV.criar(
                    con,
                    titulo=request.form.get("titulo") or "",
                    corpo=request.form.get("corpo") or "",
                    ativo=True,
                    prioridade=_prioridade_do_form(request.form),
                    vigencia_inicio=v_ini,
                    vigencia_fim=v_fim,
                    agora=agora(),
                    criado_por=usuario_nome(),
                    recorrente=rec,
                    recorrencia_dias=dias_mask,
                    recorrencia_hora=hh,
                )
        except NAV.AvisoGestaoError as erro:
            flash(str(erro), "danger")
            return render_template("avisos_admin_form.html", aviso_item=None)
        audit("NU_AVISO_CRIAR", "nu_avisos", aid, {})
        flash("Aviso criado.", "success")
        return redirect(_lista_avisos_url())

    @app.route("/admin/avisos/<int:aviso_id>/editar", methods=["GET", "POST"])
    @login_required
    @roles_required("ADMIN")
    def nu_avisos_admin_editar(aviso_id: int):
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            aviso = NAV.obter(con, aviso_id)
        if not aviso:
            flash("Aviso não encontrado.", "danger")
            return redirect(_lista_avisos_url())
        if request.method == "GET":
            return render_template("avisos_admin_form.html", aviso_item=aviso)
        try:
            with db.transaction() as con:
                rec, dias_mask, hh = _recorrencia_do_form(request.form)
                v_ini, v_fim = _vigencia_do_form(request.form)
                NAV.atualizar(
                    con,
                    aviso_id,
                    titulo=request.form.get("titulo") or "",
                    corpo=request.form.get("corpo") or "",
                    ativo=bool(int(aviso["ativo"])),
                    prioridade=_prioridade_do_form(request.form),
                    vigencia_inicio=v_ini,
                    vigencia_fim=v_fim,
                    agora=agora(),
                    recorrente=rec,
                    recorrencia_dias=dias_mask,
                    recorrencia_hora=hh,
                )
        except NAV.AvisoGestaoError as erro:
            flash(str(erro), "danger")
            return render_template("avisos_admin_form.html", aviso_item=aviso)
        audit("NU_AVISO_EDITAR", "nu_avisos", aviso_id, {})
        flash("Aviso atualizado.", "success")
        return redirect(_lista_avisos_url())

    @app.route("/admin/avisos/<int:aviso_id>/desativar", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def nu_avisos_admin_desativar(aviso_id: int):
        try:
            with db.transaction() as con:
                ativo = NAV.alternar_ativo(con, aviso_id, agora=agora())
        except NAV.AvisoGestaoError as erro:
            flash(str(erro), "danger")
            return redirect(_lista_avisos_url())
        audit(
            "NU_AVISO_ATIVAR" if ativo else "NU_AVISO_DESATIVAR",
            "nu_avisos",
            aviso_id,
            {},
        )
        flash("Aviso ativado." if ativo else "Aviso desativado.", "success")
        return redirect(_lista_avisos_url())

    @app.route("/admin/avisos/<int:aviso_id>/remover", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def nu_avisos_admin_remover(aviso_id: int):
        try:
            with db.transaction() as con:
                NAV.remover(con, aviso_id)
        except NAV.AvisoGestaoError as erro:
            flash(str(erro), "danger")
            return redirect(_lista_avisos_url())
        audit("NU_AVISO_REMOVER", "nu_avisos", aviso_id, {})
        flash("Aviso removido.", "success")
        return redirect(_lista_avisos_url())
