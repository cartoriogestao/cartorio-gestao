"""As rotas da sugestão de ônus por IA — ver `ri_onus_ia.py`.

A leitura fica no quadro da certidão de ônus, na ficha da matrícula, e SÓ
COMEÇA QUANDO ALGUÉM CLICA no botão — ordem do oficial em 15/10/2026: «a IA so
vai ler se clicar no botao na emissao de certidao de onus. para cada
matricula». A leitura roda em segundo plano e confere também o PROPRIETÁRIO.
Nenhuma das rotas emite certidão: quem emite é `ri_emitir_certidao`, chamando
`ri_onus_ia.decidir`.
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
                flash("A sugestão por IA não está ligada nesta instalação (falta a chave do "
                      "provedor, ou ela foi desligada). Escolha positiva ou negativa lendo a "
                      "ficha.", "warning")
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
            flash("A IA está lendo a ficha (ônus, ações e proprietário). Em um ou dois "
                  "minutos a leitura aparece no quadro da certidão de ônus.", "info")
        else:
            flash("Esta ficha já foi lida (ou está sendo lida) do jeito que está.", "info")
        return redirect(volta)

    @app.route("/registro-imoveis/<int:matricula_id>/onus/acatar-proprietario",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_onus_acatar_proprietario(matricula_id: int):
        """«sendo acatada a sugestao, sistema tbm retifique no cadastro da
        matricula» — o oficial, 15/10/2026. Corrige o cadastro de partes pelo que
        a IA leu no teor; quem decide acatar é quem clica."""
        volta = url_for("ri_ficha", matricula_id=matricula_id) + "#certidao-onus"
        try:
            with db.transaction() as con:
                feito = RONIA.acatar_proprietarios(
                    con, matricula_id, agora=db.now(), usuario=usuario_nome())
        except (RONIA.OnusError, ValueError) as erro:
            flash(str(erro), "danger")
            return redirect(volta)
        for s in feito["desligados"] + feito["religados"]:
            audit("RI_PARTE_CORRIGIDA", "RI_PARTE", s["parte_id"],
                  {"matricula_id": s["matricula_id"], "ato_id": s["ato_id"],
                   "nome": s["nome"], "motivo": s["motivo"], "mudancas": s["mudancas"],
                   "origem": "leitura da IA acatada", "sugestao_id": feito["sugestao_id"]})
        for p in feito["incluidos"]:
            audit("RI_PARTE_INCLUIDA", "RI_PARTE", p["parte_id"],
                  {"matricula_id": matricula_id, "ato_id": p["ato_id"], "nome": p["nome"],
                   "documento": p["documento"], "motivo": feito["motivo"],
                   "origem": "leitura da IA acatada", "sugestao_id": feito["sugestao_id"]})
        partes = []
        if feito["incluidos"]:
            partes.append("incluído(s): " + ", ".join(p["nome"] for p in feito["incluidos"]))
        if feito["religados"]:
            partes.append("de novo titular(es): " + ", ".join(s["nome"] for s in feito["religados"]))
        if feito["desligados"]:
            partes.append("deixou(aram) de ser titular: "
                          + ", ".join(s["nome"] for s in feito["desligados"]))
        flash("Cadastro da matrícula corrigido pela leitura da IA — " + "; ".join(partes)
              + ". O valor anterior de cada linha ficou na auditoria; o teor não foi tocado.",
              "success")
        return redirect(volta)

    @app.route("/registro-imoveis/<int:matricula_id>/onus/sugestao")
    @login_required
    def ri_onus_sugestao(matricula_id: int):
        with db.connect() as con:
            s = RONIA.ultima(con, matricula_id)
        if s is None:
            return jsonify({"situacao": None})
        return jsonify({"id": s["id"], "situacao": s["situacao"], "vale": s["vale"]})
