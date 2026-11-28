"""Pendura o aviso dos pedidos do ONR parados em TODA tela da responsável — ver
`onr_pedidos_avisos.py` (A005).

Mora no `base.html` (e no `base_novo.html`) pela razão da faixa da gratuidade:
ligado tela a tela, a próxima tela nasceria sem ele. O aviso só LÊ: quem grava é
a verificação (o processo da central, ou o botão «Verificar agora»).

TRÊS PORTAS
    - o aviso no alto da tela (`_onr_pedidos_aviso.html`): simples no 1º dia
      útil, faixa vermelha que não fecha a partir do 2º;
    - a tela dos avisos (`/ri/onr/pedidos-parados`): todos os abertos, quem
      recebe, a última verificação e os encerrados — a medição que saiu da
      checklist continua à vista do admin e do gestor;
    - a configuração do responsável, em Administrativo → Configurações.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from flask import flash, g, redirect, render_template, request, session, url_for
from werkzeug.routing import BuildError

import onr_pedidos_avisos as AV

QUEM_VE = ("ADMIN", "MANAGER", "USER", "AUDITOR")
QUEM_VERIFICA = ("ADMIN", "MANAGER", "USER")
#: O nome do argumento de cada tela de pedido.
ARGUMENTO = {"onr_auto_pedido": "pedido_id", "onr_certidao_ficha": "pedido_id",
             "onr_eprotocolo_ficha": "pedido_id", "onr_saec_ficha": "atendimento_id",
             "onr_intimacao_ficha": "pedido_id"}
#: Quantos pedidos a faixa lista; o resto vai na tela dos avisos.
NA_FAIXA = 5


def _dd_mm(iso: str | None) -> str:
    t = str(iso or "")
    return f"{t[8:10]}/{t[5:7]}/{t[:4]}" if len(t) >= 10 else t


def para_a_tela(a: dict) -> dict:
    """O aviso como a tela o mostra: o link do pedido e «parado desde»."""
    arg = ARGUMENTO.get(a.get("endpoint") or "")
    try:
        href = url_for(a["endpoint"], **{arg: int(a["ref_id"])}) if arg else None
    except BuildError:
        href = None                     # a tela do pedido não está neste pacote
    return {**a, "href": href, "desde_br": _dd_mm(a.get("desde")),
            "fonte_rotulo": AV.ROTULO_DA_FONTE.get(a.get("fonte"), a.get("fonte"))}


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_id = app.extensions["usuario_id"]

    with db.connect() as con:
        AV.init_schema(con)

    @app.context_processor
    def _onr_pedidos_aviso() -> dict:
        vazio = {"onr_pedidos_aviso": None}
        try:
            onde = request.endpoint or ""
        except RuntimeError:
            return vazio
        if not session.get("user_id") or onde in ("static", "login", "logout"):
            return vazio

        def contar():
            try:
                with db.connect() as con:
                    avisos = AV.avisos_de(con, session.get("user_id"))
            except (sqlite3.Error, RuntimeError, KeyError, TypeError):
                return vazio
            if not (avisos["faixa"] or avisos["simples"]):
                return vazio
            faixa = [para_a_tela(a) for a in avisos["faixa"]]
            simples = [para_a_tela(a) for a in avisos["simples"]]
            return {"onr_pedidos_aviso": {
                "faixa": faixa[:NA_FAIXA], "faixa_mais": max(0, len(faixa) - NA_FAIXA),
                "simples": simples[:NA_FAIXA], "simples_mais": max(0, len(simples) - NA_FAIXA),
                "total": len(faixa) + len(simples)}}

        if "_cg_onr_pedidos_aviso" not in g:
            g._cg_onr_pedidos_aviso = contar()
        return g._cg_onr_pedidos_aviso

    @app.context_processor
    def _onr_pedidos_na_configuracao() -> dict:
        """O quadro do responsável na tela de Configurações. SÓ LÊ."""
        try:
            if (request.endpoint or "") != "settings":
                return {}
        except RuntimeError:
            return {}
        try:
            with db.connect() as con:
                return {"onr_pedidos_cfg": {
                    "usuarios": AV.usuarios_que_podem_receber(con),
                    "atual": str(db.get_setting(AV.CHAVE_RESPONSAVEL, "") or ""),
                    "efetivo": AV.responsavel(con, db.get_setting)}}
        except Exception:                               # noqa: BLE001 — o quadro some, a tela abre
            app.logger.warning("O quadro do responsável do ONR não abriu.", exc_info=True)
            return {}

    @app.route("/ri/onr/pedidos-parados")
    @login_required
    @roles_required(*QUEM_VE)
    def onr_pedidos_avisos():
        with db.connect() as con:
            q = AV.quadro(con, db.get_setting)
        return render_template(
            "onr_pedidos_avisos.html", abertos=[para_a_tela(a) for a in q["abertos"]],
            encerrados=[para_a_tela(a) for a in q["encerrados"]], ultima=q["ultima"],
            responsavel=q["responsavel"], processo=AV.CATALOGO[0], fontes=AV.FONTES,
            dd_mm=_dd_mm)

    @app.route("/ri/onr/pedidos-parados/verificar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_VERIFICA)
    def onr_pedidos_avisos_verificar():
        """A MESMA verificação do processo, na hora. Lê o ONR (SAEC) só com GET."""
        try:
            r = AV.verificar_os_pedidos(db, agora=datetime.now(), origem=AV.ORIGEM_TELA)
        except Exception as erro:                       # noqa: BLE001
            flash(f"A verificação não terminou: {erro}", "danger")
            return redirect(url_for("onr_pedidos_avisos"))
        audit("ONR_PEDIDOS_AVISOS_VERIFICADOS", "ONR_PEDIDOS_AVISOS", None,
              {k: r[k] for k in ("abertos", "faixas", "novos", "encerrados", "medidas")})
        flash(AV.relato(r), "warning" if r["nao_medidas"] else "ok")
        return redirect(url_for("onr_pedidos_avisos"))

    @app.route("/configuracoes/onr-pedidos-responsavel", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def configuracoes_onr_pedidos_responsavel():
        """Quem recebe os avisos. ESCREVE só esta chave.

        Rota própria, como a da revisão das transcrições: o formulário geral
        grava tudo o que manda."""
        try:
            with db.connect() as con:
                valor = AV.guardar_responsavel(con, request.form.get("user_id"))
        except AV.AvisosOnrError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("settings") + "#cfg-onr-pedidos")
        antes = str(db.get_setting(AV.CHAVE_RESPONSAVEL, "") or "")
        db.set_settings({AV.CHAVE_RESPONSAVEL: valor})
        # Os avisos abertos mudam de dono agora, e não só na próxima verificação.
        with db.transaction() as con:
            AV.repassar(con, AV.responsavel(con, db.get_setting)["user_id"])
        audit("SETTINGS_CHANGED", "SETTINGS", None,
              {AV.CHAVE_RESPONSAVEL: valor, "antes": antes, "por": usuario_id()})
        flash("Responsável pelos pedidos do ONR gravado. Os avisos abertos passaram a "
              "essa pessoa." if valor else
              "Responsável pelos pedidos do ONR em branco: os avisos vão para o ADMIN.", "success")
        return redirect(url_for("settings") + "#cfg-onr-pedidos")
