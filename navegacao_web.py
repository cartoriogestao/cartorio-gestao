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
import titular_privado as TITULAR
from seguranca_web import destino_interno

LAYOUTS = ("antigo", "novo")
PADRAO_DE_FABRICA = "novo"
CHAVE_PADRAO = "layout_padrao"


def chave_do_usuario(usuario_id) -> str:
    return f"layout_usuario_{int(usuario_id)}"


# O TAMANHO DA LETRA E AS COLUNAS DA ESQUERDA — pedidos do oficial, 02/11/2026: «alguém que não enxerga
# tão bem poder aumentar as fontes e logos do sistema» e «recolher as colunas da esquerda para deixar mais
# campo pra tela». São da pessoa, como o layout, e moram em `settings` pelo mesmo motivo. O tamanho é um
# `zoom` da página inteira — o CSS da casa é todo em pixels, e só o zoom aumenta letra, ícone e logo juntos.
ESCALAS = {"100": "1", "115": "1.15", "130": "1.3", "150": "1.5"}
COLUNAS = ("abertas", "recolhidas")


def chave_da_escala(usuario_id) -> str:
    return f"escala_usuario_{int(usuario_id)}"


def chave_das_colunas(usuario_id) -> str:
    return f"colunas_usuario_{int(usuario_id)}"


def escala_de(db, usuario_id) -> str:
    """O tamanho que a pessoa escolheu, «100» a «150». Só lê."""
    escolha = db.get_setting(chave_da_escala(usuario_id), "100")
    return escolha if escolha in ESCALAS else "100"


def colunas_recolhidas(db, usuario_id) -> bool:
    return db.get_setting(chave_das_colunas(usuario_id), "abertas") == "recolhidas"


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

    @app.route("/preferencias/aparencia", methods=["POST"])
    @login_required
    def preferencia_aparencia():
        """O tamanho da letra e as colunas da esquerda, da pessoa. Vale nas duas molduras.

        O botão de recolher manda pelo `fetch` e não recarrega a tela: a resposta é vazia. Sem script, é
        um formulário como os outros, e volta para a tela de onde veio."""
        uid = session.get("user_id")
        escala = (request.form.get("escala") or "").strip()
        colunas = (request.form.get("colunas") or "").strip()
        if (escala and escala not in ESCALAS) or (colunas and colunas not in COLUNAS) or not (escala or colunas):
            flash("Essa preferência não existe.", "danger")
            return redirect(_destino())
        if escala:
            db.set_settings({chave_da_escala(uid): escala})
        if colunas:
            db.set_settings({chave_das_colunas(uid): colunas})
        audit("APARENCIA_ESCOLHIDA", "users", uid, {"escala": escala, "colunas": colunas})
        if request.headers.get("X-Requested-With") == "fetch":
            return "", 204
        return redirect(_destino())

    def _em_atendimento():
        """O protocolo que esta pessoa está atendendo, para o alto da tela. Só lê."""
        with db.connect() as con:
            return CXP.em_atendimento(con, usuario_nome())

    def _e_o_titular() -> bool:
        """A rota do titular recusa os outros ADMIN: o menu não oferece o que vai ser recusado."""
        if "cg_titular" not in g:
            g.cg_titular = TITULAR.e_o_titular(db, usuario_nome(), app.extensions["usuario_papel"]())
        return g.cg_titular

    def _abre(endpoint: str, papel: str) -> bool:
        """A rota deixa esta pessoa abrir? O menu pergunta a ela, e não mantém uma segunda lista.

        Havia 46 opções no menu do auditor que levavam à recusa: cada lista de papéis tinha envelhecido
        por conta própria. Quem manda é `roles_required`, e ela deixa a resposta à vista na função.
        """
        funcao = app.view_functions.get(endpoint)
        exigidos = getattr(funcao, "papeis_exigidos", None)
        metodos = getattr(funcao, "metodos_exigidos", None)
        return exigidos is None or (metodos is not None and "GET" not in metodos) or papel in exigidos

    def nav_da_tela(*, papel="", escondidos=(), ajuda_liberada=False,
                    agente_no_menu=False, tipo_do_ato=""):
        args = dict(request.args.to_dict())
        args.update(request.view_args or {})
        return NAV.montar(request.endpoint or "", args, papel, url_for,
                          escondidos=escondidos, ajuda_liberada=ajuda_liberada,
                          agente_no_menu=agente_no_menu, tipo_do_ato=tipo_do_ato,
                          e_o_titular=_e_o_titular(), abre=_abre)

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
        escala = escala_de(db, uid)
        return {"layout_novo": g.cg_layout == "novo",
                "cg_escala": escala, "cg_zoom": ESCALAS[escala], "cg_escalas": tuple(ESCALAS),
                "cg_colunas_recolhidas": colunas_recolhidas(db, uid),
                "timbre_na_tela": g.cg_layout != "novo" or request.endpoint in NAV.TELAS_COM_TIMBRE,
                "layout_padrao_da_casa": db.get_setting(CHAVE_PADRAO, PADRAO_DE_FABRICA),
                "layout_sem_escolha": db.get_setting(chave_do_usuario(uid), "") not in LAYOUTS,
                "e_o_titular": _e_o_titular(),
                "nav_da_tela": nav_da_tela, "portas_de_lavrar": portas_de_lavrar,
                "protocolo_em_atendimento": _em_atendimento}
