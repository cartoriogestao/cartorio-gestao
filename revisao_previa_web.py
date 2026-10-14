"""As rotas da revisão antes da lavratura — ver `revisao_previa.py`.

O botão «Revisar com IA» manda o texto que está NA TELA (no RI, o formulário
ainda não lavrado; nas Notas, o teor guardado), a leitura roda em segundo
plano, e a tela pergunta o andamento a cada poucos segundos. Nenhuma das três
rotas lavra nada: quem trava ou libera é a rota de lavrar, chamando
`exigir_para_lavrar`.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import abort, jsonify, request

import revisao_previa as RV

#: As telas em que o painel aparece (as que lavram ato do RI e das Notas).
TELAS_COM_REVISAO = ("ri_ficha", "ri_preencher_modelo", "notas_ato")


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    usuario_nome = app.extensions["usuario_nome"]

    def pasta() -> Path:
        return Path(app.config["DATA_DIR"])

    @app.context_processor
    def _revisao_na_tela() -> dict:
        try:
            onde = request.endpoint or ""
        except RuntimeError:
            return {"revisao_ligada": False}
        if onde not in TELAS_COM_REVISAO:
            return {"revisao_ligada": False}
        try:
            with db.connect() as con:
                return {"revisao_ligada": RV.ligada(con, pasta())}
        except sqlite3.Error:
            return {"revisao_ligada": False}

    def _comecar(atribuicao: str, alvo_id: int, hash_texto: str, dossie: str,
                 rotulo: str, anexos_origem: dict | None = None):
        with db.transaction() as con:
            rid, nova = RV.pedir(con, atribuicao, alvo_id, hash_texto, dossie,
                                 rotulo=rotulo, usuario=usuario_nome(),
                                 anexos_origem=anexos_origem)
        if nova:
            audit("REVISAO_PREVIA_PEDIDA", "rv_revisoes", rid,
                  {"atribuicao": atribuicao, "alvo": alvo_id})
            RV.ler_em_segundo_plano(db.db_path, pasta(), rid)
        return jsonify({"id": rid, "nova": nova})

    @app.route("/revisao-previa/ri/<int:matricula_id>", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def revisao_previa_ri(matricula_id: int):
        tipo = (request.form.get("tipo") or "").strip().upper()
        teor = request.form.get("teor") or ""
        if tipo not in ("R", "AV") or not RV.normalizar(teor):
            return jsonify({"erro": "Escolha o tipo e escreva o teor antes de revisar."}), 400
        with db.connect() as con:
            if not RV.ligada(con, pasta()):
                return jsonify({"desligada": True})
            try:
                dossie = RV.dossie_ri(con, matricula_id, tipo, teor,
                                      request.form.get("natureza_titulo"))
            except RV.RevisaoPendente as erro:
                return jsonify({"erro": str(erro)}), 404
        # OS ANEXOS DO RI SÃO OS DA PRENOTAÇÃO escolhida no formulário — é ali que
        # o título apresentado mora (`ri_documentos`). Sem prenotação, sem anexos.
        prenotacao = (request.form.get("prenotacao_id_ui") or "").strip()
        origem = ({"entidade": "RI_PROTOCOLO", "id": int(prenotacao)}
                  if prenotacao.isdigit() else None)
        return _comecar("RI", matricula_id, RV.hash_do_ato(tipo, teor), dossie,
                        f"{tipo} na matrícula id {matricula_id}", origem)

    @app.route("/revisao-previa/notas/<int:ato_id>", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def revisao_previa_notas(ato_id: int):
        with db.connect() as con:
            if not RV.ligada(con, pasta()):
                return jsonify({"desligada": True})
            a = con.execute("SELECT tipo, teor FROM nt_atos WHERE id = ?", (ato_id,)).fetchone()
            if a is None or not RV.normalizar(a[1]):
                return jsonify({"erro": "Guarde o teor antes de revisar."}), 400
            dossie = RV.dossie_notas(con, ato_id)
        return _comecar("NOTAS", ato_id, RV.hash_do_ato(a[0], a[1]), dossie,
                        f"{a[0]} das Notas id {ato_id}",
                        {"entidade": "NT_ATO", "id": ato_id})

    # A ÚLTIMA REVISÃO, PARA A TELA MOSTRAR AO ABRIR (07/10/2026): recarregar a
    # página não pode sumir com uma resposta que está gravada.
    @app.route("/revisao-previa/notas/<int:ato_id>/ultima")
    @login_required
    def revisao_previa_notas_ultima(ato_id: int):
        with db.connect() as con:
            a = con.execute("SELECT tipo, teor FROM nt_atos WHERE id = ?", (ato_id,)).fetchone()
            if a is None:
                abort(404)
            r = RV.ultima(con, "NOTAS", ato_id, RV.hash_do_ato(a[0], a[1]))
            r = RV.anotar_supridos(con, r) if r else r
        return jsonify(r or {})

    @app.route("/revisao-previa/ri/<int:matricula_id>/ultima")
    @login_required
    def revisao_previa_ri_ultima(matricula_id: int):
        with db.connect() as con:
            lavrado = con.execute("SELECT MAX(lavrado_em) FROM ri_atos WHERE matricula_id = ?",
                                  (matricula_id,)).fetchone()[0]
            r = RV.ultima(con, "RI", matricula_id, None, depois_de=lavrado)
            r = RV.anotar_supridos(con, r) if r else r
        return jsonify(r or {})

    @app.route("/revisao-previa/<int:revisao_id>")
    @login_required
    def revisao_previa_andamento(revisao_id: int):
        with db.connect() as con:
            r = RV.mostrar(con, revisao_id)
            r = RV.anotar_supridos(con, r) if r else r
        if r is None:
            abort(404)
        return jsonify(r)

    # «JÁ VERIFICADO/SUPRIDO» - HOTFIX-2026-10-08-07, pedido da Beatriz
    # (08/10/2026, AV-8/1196). Marca apontamentos da revisão; GRAVE só o
    # gerente/administrador, com observação. Cada marca vai para a auditoria.
    @app.route("/revisao-previa/<int:revisao_id>/suprir", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def revisao_previa_suprir(revisao_id: int):
        papel = app.extensions["usuario_papel"]()
        itens = []
        for bruto in request.form.getlist("indice"):
            if str(bruto).strip().isdigit():
                i = int(bruto)
                itens.append((i, request.form.get(f"obs_{i}") or ""))
        if not itens:
            return jsonify({"erro": "Marque ao menos um apontamento."}), 400
        try:
            with db.transaction() as con:
                alvo = con.execute("SELECT atribuicao, alvo_id FROM rv_revisoes WHERE id=?",
                                   (revisao_id,)).fetchone()
                feitos = RV.suprir(con, revisao_id, itens, usuario=usuario_nome(),
                                   papel=papel)
        except RV.RevisaoPendente as erro:
            return jsonify({"erro": str(erro)}), 400
        for f in feitos:
            audit("REVISAO_PREVIA_SUPRIDO", "rv_revisoes", revisao_id,
                  {"atribuicao": alvo[0], "alvo": alvo[1], "papel": papel, **f})
        with db.connect() as con:
            r = RV.mostrar(con, revisao_id)
            r = RV.anotar_supridos(con, r) if r else r
        return jsonify(r or {})
