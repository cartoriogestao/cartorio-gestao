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
"""
from __future__ import annotations

from datetime import date

from flask import request, session

import conformidade as CF

#: Quem vê o semáforo no painel geral.
QUEM_VE = ("ADMIN", "MANAGER", "AUDITOR")


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
