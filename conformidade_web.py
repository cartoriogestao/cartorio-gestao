"""O SEMÁFORO DA CONFORMIDADE NO PAINEL GERAL — 18/11/2026.

    «Quer que eu comece o painel de conformidade (semáforo por área)?»
    «Sim, comece» — o oficial, 18/11/2026

SEM ROTA PRÓPRIA
    É um quadro da primeira tela, como o da ouvidoria: o contexto chega só ao
    painel geral (`dashboard`) e só a quem cuida da casa — o oficial, o
    gerente e o auditor (o gestor de compliance entra por um destes papéis).
    Para os demais o contexto vem vazio e o quadro não aparece.

TELA NÃO CAI POR CAUSA DE QUADRO
    A medição que quebra não vira «tudo verde»: o quadro aparece com o aviso
    de que não deu para medir, e o resto do painel abre normalmente.

A CHECKLIST DE GESTÃO DO DIA — 19/11/2026
    «não consigo clicar nos itens e não vejo checklist» — o oficial

    Cada cartão do semáforo leva a `/administrativo/gestor/checklist?area=…`,
    a tela que lista os achados abertos daquela área e as conferências do dia
    (`gestor_checklist`). Mora aqui porque é a mesma pergunta do quadro —
    «o que está fora da conformidade?» — e é vista pelos mesmos papéis.
    O «conferido hoje» grava quem olhou, com auditoria, e não fecha achado.
"""
from __future__ import annotations

from datetime import date

from flask import (abort, flash, redirect, render_template, request, session,
                   url_for)

import conformidade as CF
import gestor_checklist as CK

#: Quem vê o semáforo no painel geral — e abre a checklist que ele leva.
QUEM_VE = CK.QUEM_VE


def quadro(db, hoje: date | None = None) -> dict:
    """O que o quadro mostra: a medição, ou o erro dela. Só lê."""
    try:
        with db.connect() as con:
            return {"medicao": CF.medir(con, hoje), "erro": ""}
    except Exception as erro:                              # noqa: BLE001
        # ZERO MEDIDO E ZERO POR ENGANO SÃO COISAS DIFERENTES: o quadro diz
        # que não mediu, em vez de mostrar sete áreas verdes.
        return {"medicao": None, "erro": f"não deu para medir: {erro}"}


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    current_user = app.extensions["current_user"]
    usuario_nome = app.extensions["usuario_nome"]
    usuario_id = app.extensions["usuario_id"]

    def _abre(endpoint: str, papel: str) -> bool:
        """A rota do item deixa esta pessoa entrar? Pergunta à própria rota.

        A mesma pergunta do menu (`navegacao_web`): os papéis ficam à vista
        na função (`roles_required`), e copiar a lista para cá envelheceria.
        """
        funcao = app.view_functions.get(endpoint)
        if funcao is None:
            return False
        exigidos = getattr(funcao, "papeis_exigidos", None)
        metodos = getattr(funcao, "metodos_exigidos", None)
        return exigidos is None or (metodos is not None and "GET" not in metodos) or papel in exigidos

    @app.route("/administrativo/gestor/checklist")
    @login_required
    @roles_required(*CK.QUEM_VE)
    def gestor_checklist():
        """Os achados abertos por área e as conferências do dia. SÓ LÊ."""
        papel = current_user()["role"]
        dados = CK.montar(db, papel=papel, area=(request.args.get("area") or "").upper() or None,
                          abre=lambda endpoint: _abre(endpoint, papel))
        return render_template(
            "gestor_checklist.html", ck=dados, areas=CF.ROTULO_DA_AREA, ordem_areas=CF.AREAS,
            outros=CF.OUTROS, cores=CF.ROTULO_DA_COR, motivos=CF.ROTULO_DO_MOTIVO,
            gravidades=CK.ROTULO_DA_GRAVIDADE, nao_mede=CF.NAO_MEDE)

    @app.route("/administrativo/gestor/checklist/conferido", methods=["POST"])
    @login_required
    @roles_required(*CK.QUEM_CONFERE)
    def gestor_checklist_conferido():
        """«Conferido hoje» num item. Grava quem e quando; não resolve achado."""
        item = (request.form.get("item") or "").strip().upper()
        area = (request.form.get("area") or "").strip().upper()
        voltar = url_for("gestor_checklist", area=area or None)
        if area and area not in CF.ROTULO_DA_AREA:
            voltar = url_for("gestor_checklist")
        if item not in CK.CODIGOS:
            abort(400)
        with db.transaction() as con:
            r = CK.marcar_conferido(con, item, date.today(), por=usuario_nome(),
                                    usuario_id=usuario_id())
        rotulo = next(rot for cod, rot, *_ in CK.CONFERENCIAS if cod == item)
        if r["gravou"]:
            audit("GESTOR_CHECKLIST_CONFERIDO", "ge_conferencias_do_dia", None,
                  {"item": item, "dia": date.today().isoformat()})
            flash(f"«{rotulo}» conferido hoje. Os achados continuam abertos até a "
                  "conferência seguinte do gestor ver que foram resolvidos.", "success")
        else:
            flash(f"«{rotulo}» já tinha sido conferido hoje por {r['por']}"
                  f" ({str(r['em'])[11:16]}).", "info")
        return redirect(voltar)

    @app.context_processor
    def _conformidade_no_painel() -> dict:
        vazio = {"conformidade_no_painel": None}
        try:
            if (request.endpoint or "") != "dashboard" or not session.get("user_id"):
                return vazio
        except RuntimeError:
            return vazio
        u = current_user()
        if not u or u["role"] not in QUEM_VE:
            return vazio
        return {"conformidade_no_painel": {
            **quadro(db),
            "areas": CF.ROTULO_DA_AREA, "cores": CF.ROTULO_DA_COR,
            "motivos": CF.ROTULO_DO_MOTIVO, "nao_mede": CF.NAO_MEDE}}
