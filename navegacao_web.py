"""A chave do layout novo e o contexto da casca. O registro mora em `navegacao.py`.

A TROCA É POR PESSOA, E VOLTA COM UM CLIQUE
    Até a etapa de limpeza, cada um escolhe o layout, e o oficial escolhe o padrão da
    casa. O padrão de fábrica é o novo, por decisão do oficial de 30/10/2026: quem ainda
    não escolheu abre nele, com um aviso, e volta ao antigo com um clique. As telas
    continuam as mesmas, nas mesmas rotas. O que muda é a moldura.

A ESCOLHA MORA EM `settings`, e não numa coluna nova: é preferência passageira, que
some com a etapa de limpeza, e coluna nova ficaria para sempre.
"""
from __future__ import annotations

from flask import flash, g, redirect, request, session, url_for

import caixa_protocolo as CXP
import navegacao as NAV
from seguranca_web import destino_interno

LAYOUTS = ("antigo", "novo")
PADRAO_DE_FABRICA = "novo"
CHAVE_PADRAO = "layout_padrao"


def chave_do_usuario(usuario_id) -> str:
    return f"layout_usuario_{int(usuario_id)}"


def layout_de(db, usuario_id) -> str:
    """O layout daquela pessoa: a escolha dela, ou o padrão da casa. Só lê."""
    escolha = db.get_setting(chave_do_usuario(usuario_id), "")
    if escolha in LAYOUTS:
        return escolha
    padrao = db.get_setting(CHAVE_PADRAO, PADRAO_DE_FABRICA)
    return padrao if padrao in LAYOUTS else PADRAO_DE_FABRICA


def registrar_rotas(app, db, login_required, roles_required, audit):
    """Pendura a chave e o contexto da casca no app já construído."""
    usuario_nome = app.extensions["usuario_nome"]

    def _destino() -> str:
        """Volta para a tela de onde veio. Só caminho interno: a régua é a da casa."""
        return destino_interno((request.form.get("next") or "").strip(), url_for("dashboard"))

    @app.route("/preferencias/layout", methods=["POST"])
    @login_required
    def preferencia_layout():
        """Cada pessoa escolhe o próprio layout, e pode voltar a qualquer momento."""
        layout = (request.form.get("layout") or "").strip()
        if layout not in LAYOUTS:
            flash("Esse layout não existe.", "danger")
            return redirect(_destino())
        uid = session.get("user_id")
        db.set_settings({chave_do_usuario(uid): layout})
        audit("LAYOUT_ESCOLHIDO", "users", uid, {"layout": layout})
        g.pop("cg_layout", None)
        return redirect(_destino())

    @app.route("/preferencias/layout/padrao", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def preferencia_layout_padrao():
        """O padrão da casa, para quem ainda não escolheu. É do oficial."""
        layout = (request.form.get("layout") or "").strip()
        if layout not in LAYOUTS:
            flash("Esse layout não existe.", "danger")
            return redirect(_destino())
        db.set_settings({CHAVE_PADRAO: layout})
        audit("LAYOUT_PADRAO", "settings", 0, {"layout": layout})
        flash(f"Quem não escolheu passa a ver o layout {layout}.", "success")
        return redirect(_destino())

    def _em_atendimento():
        """O protocolo que esta pessoa está atendendo, para o alto da tela. Só lê."""
        with db.connect() as con:
            return CXP.em_atendimento(con, usuario_nome())

    def nav_da_tela(*, papel="", escondidos=(), ajuda_liberada=False,
                    agente_no_menu=False, tipo_do_ato=""):
        args = dict(request.args.to_dict())
        args.update(request.view_args or {})
        return NAV.montar(request.endpoint or "", args, papel, url_for,
                          escondidos=escondidos, ajuda_liberada=ajuda_liberada,
                          agente_no_menu=agente_no_menu, tipo_do_ato=tipo_do_ato)

    def portas_de_lavrar(grupo: str) -> list[dict]:
        """As portas de um módulo, do mesmo registro do botão Novo: quem vê uma vê a outra."""
        nav = nav_da_tela(papel=app.extensions["usuario_papel"]())
        return next((g["itens"] for g in nav["novo"] if g["grupo"] == grupo), [])

    @app.context_processor
    def contexto_da_casca():
        uid = session.get("user_id")
        if not uid:
            return {"layout_novo": False}
        if "cg_layout" not in g:
            g.cg_layout = layout_de(db, uid)
        return {"layout_novo": g.cg_layout == "novo",
                "timbre_na_tela": g.cg_layout != "novo" or request.endpoint in NAV.TELAS_COM_TIMBRE,
                "layout_padrao_da_casa": db.get_setting(CHAVE_PADRAO, PADRAO_DE_FABRICA),
                "layout_sem_escolha": db.get_setting(chave_do_usuario(uid), "") not in LAYOUTS,
                "nav_da_tela": nav_da_tela, "portas_de_lavrar": portas_de_lavrar,
                "protocolo_em_atendimento": _em_atendimento}
