"""As rotas da sugestão de ônus por IA — ver `ri_onus_ia.py`.

O botão «Sugerir com IA» fica no quadro da certidão de ônus, na ficha da
matrícula. A leitura roda em segundo plano; a ficha mostra o andamento e, pronta
a leitura, já vem com a escolha e os trechos marcados. Nenhuma das duas rotas
emite certidão: quem emite é `ri_emitir_certidao`, chamando `ri_onus_ia.decidir`.
"""
from __future__ import annotations

from pathlib import Path

from flask import flash, jsonify, redirect, url_for

import ri_onus_ia as RONIA


def registrar_rotas(app, db, login_required, roles_required, audit):
    usuario_nome = app.extensions["usuario_nome"]

    def pasta() -> Path:
        return Path(app.config["DATA_DIR"])

    @app.route("/registro-imoveis/<int:matricula_id>/onus/sugerir", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_onus_sugerir(matricula_id: int):
        volta = url_for("ri_ficha", matricula_id=matricula_id) + "#certidao-onus"
        with db.connect() as con:
            if RONIA.no_sandbox(con):
                flash("No sistema de teste (SANDBOX) a sugestão por IA não existe — ordem "
                      "do oficial. Escolha positiva ou negativa lendo a ficha.", "warning")
                return redirect(volta)
            if not RONIA.ligada(con, pasta()):
                flash("A sugestão por IA não está ligada nesta instalação (falta a chave "
                      "do provedor, ou ela foi desligada). Escolha positiva ou negativa "
                      "lendo a ficha.", "warning")
                return redirect(volta)
        try:
            with db.transaction() as con:
                sid, nova = RONIA.pedir(con, matricula_id, usuario=usuario_nome())
        except RONIA.OnusError as erro:
            flash(str(erro), "danger")
            return redirect(volta)
        if nova:
            audit("RI_ONUS_SUGESTAO_PEDIDA", "ri_onus_sugestoes", sid,
                  {"matricula_id": matricula_id})
            RONIA.ler_em_segundo_plano(db.db_path, pasta(), sid)
            flash("A IA está lendo a ficha. Em um ou dois minutos atualize a página: a "
                  "sugestão aparece no quadro da certidão de ônus.", "info")
        else:
            flash("Esta ficha já foi lida (ou está sendo lida) do jeito que está.", "info")
        return redirect(volta)

    @app.route("/registro-imoveis/<int:matricula_id>/onus/sugestao")
    @login_required
    def ri_onus_sugestao(matricula_id: int):
        with db.connect() as con:
            s = RONIA.ultima(con, matricula_id)
        if s is None:
            return jsonify({"situacao": None})
        return jsonify({"id": s["id"], "situacao": s["situacao"], "vale": s["vale"]})
