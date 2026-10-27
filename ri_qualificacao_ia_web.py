"""As rotas da qualificação assistida do RI — ver `ri_qualificacao_ia.py`.

O QUADRO MORA NA TELA DA NOTA DEVOLUTIVA (`ri_web.ri_nota_devolutiva`), que é
onde a prenotação recebe a qualificação negativa: pedir, acompanhar, ver o
rascunho e levar as exigências escolhidas para o formulário da nota — tudo no
mesmo lugar onde a nota se emite. Nenhuma rota daqui emite nota, grava
qualificação ou muda a situação da prenotação.
"""
from __future__ import annotations

from pathlib import Path

from flask import abort, flash, jsonify, redirect, render_template, request, url_for

import ri_qualificacao_ia as QIA
import seguranca_web as SEGWEB
from bd_nativo import banco

#: Quem pode pedir e levar à nota — DECISÃO DO OFICIAL EM 26/10/2026, «todos
#: podem»: todo usuário humano que pratica ato (ADMIN, MANAGER e USER), os
#: mesmos papéis da rota da nota devolutiva. Fora ficam o AUDITOR, que só lê
#: (vê o rascunho, não pede nem leva), e o robô, cuja conta é recusada antes
#: de chegar aqui (`selo_robo.ROTAS_VEDADAS_AO_ROBO`, prefixo
#: `ri_qualificacao_ia`). A régua é a da casa (`seguranca_web.PRATICA`), e não
#: uma lista escrita de novo: as duas divergiriam no primeiro conserto. As
#: telas leem esta mesma tupla para mostrar ou esconder os botões.
PAPEIS_QUE_PEDEM = tuple(SEGWEB.PRATICA)

#: A tela que mostra o quadro (e recebe o preenchimento).
TELA_DA_NOTA = "ri_nota_devolutiva"


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_nome = app.extensions["usuario_nome"]

    def pasta() -> Path:
        return Path(app.config["DATA_DIR"])

    def volta(protocolo_id: int, ancora: str = "qualificacao-ia", **args):
        return redirect(url_for(TELA_DA_NOTA, protocolo_id=protocolo_id, **args)
                        + f"#{ancora}")

    @app.context_processor
    def _qualificacao_ia_na_tela() -> dict:
        """O que o quadro e o formulário da nota precisam. Só LÊ, e só na tela
        da nota devolutiva."""
        try:
            if (request.endpoint or "") != TELA_DA_NOTA:
                return {}
            protocolo_id = (request.view_args or {}).get("protocolo_id")
        except RuntimeError:
            return {}
        if protocolo_id is None:
            return {}
        try:
            with db.connect() as con:
                saida = {"protocolo_id": protocolo_id,
                         "historico": QIA.historico(con, protocolo_id),
                         "preenche": QIA.preenchimento(
                             con, request.args.get("qualificacao"), protocolo_id),
                         "papeis": PAPEIS_QUE_PEDEM,
                         "teto": QIA.teto_do_dia(con),
                         "modelo": QIA.MODELO, "esforco": QIA.ESFORCO,
                         "maximo": QIA.MAXIMO_DE_DOCUMENTOS,
                         "limite_mb": QIA.LIMITE_DOS_DOCUMENTOS // 1048576}
                try:
                    p = QIA.prenotacao(con, protocolo_id)
                except QIA.QualificacaoIAError as motivo:
                    return {"qualificacao_ia": saida | {"cabe": False,
                                                        "motivo": str(motivo)}}
                bloqueio = QIA.por_que_nao(con, pasta())
                matricula = None
                try:
                    matricula = QIA.matricula_da_prenotacao(con, p)
                except QIA.QualificacaoIAError:
                    matricula = None
                return {"qualificacao_ia": saida | {
                    "cabe": True, "bloqueio": bloqueio, "matricula": matricula,
                    "disponiveis": QIA.documentos(con, p),
                    "especies": QIA.especies(),
                    "sugerida": QIA.sugerir_especie(p.get("natureza_titulo") or ""),
                    "andamento": QIA.em_andamento(con, protocolo_id)}}
        except Exception as erro:                      # noqa: BLE001 — o quadro some, a nota abre
            app.logger.error("Quadro da qualificação assistida não montou.", exc_info=erro)
            return {}

    @app.route("/registro-imoveis/protocolo/<int:protocolo_id>/qualificacao-ia/pedir",
               methods=["POST"])
    @roles_required(*PAPEIS_QUE_PEDEM)
    def ri_qualificacao_ia_pedir(protocolo_id: int):
        try:
            with db.connect() as con:
                bloqueio = QIA.por_que_nao(con, pasta())
            if bloqueio:
                flash(bloqueio, "danger")
                return volta(protocolo_id)
            marcados = [int(x) for x in request.form.getlist("anexo") if x.isdigit()]
            with db.transaction() as con:
                pid = QIA.pedir(con, protocolo_id, anexos_ids=marcados,
                                especie=request.form.get("especie") or "",
                                matricula_numero=request.form.get("matricula_numero") or "",
                                instrucao=request.form.get("instrucao") or "",
                                usuario=usuario_nome())
        except ValueError as erro:
            flash(str(erro), "danger")
            return volta(protocolo_id)
        audit("RI_QUALIFICACAO_IA_PEDIDA", "ri_qualificacao_ia", pid,
              {"protocolo_id": protocolo_id, "documentos": len(marcados)})
        QIA.preparar_em_segundo_plano(db.db_path, pasta(), pid)
        flash("A IA começou a ler o título. Leva alguns minutos — o quadro se atualiza "
              "sozinho quando o rascunho ficar pronto.", "success")
        return volta(protocolo_id)

    @app.route("/registro-imoveis/qualificacao-ia/<int:pedido_id>")
    @login_required
    def ri_qualificacao_ia_ver(pedido_id: int):
        """O rascunho inteiro: exigências com fundamento e trecho, o que foi
        conferido, as dúvidas e o que não se leu. Com `?andamento=1` responde só
        a situação, para o quadro perguntar de tempos em tempos."""
        with db.connect() as con:
            p = QIA.mostrar(con, pedido_id)
            if not p:
                abort(404)
            if request.args.get("andamento"):
                return jsonify({"id": p["id"], "situacao": p["situacao"]})
            prenot = banco(con).valor("SELECT numero FROM ri_protocolos WHERE id = %s",
                                      (int(p["protocolo_id"]),))
        linhas = [QIA.linha_da_exigencia(x)
                  for x in (p["resultado"] or {}).get("exigencias") or []]
        return render_template("ri_qualificacao_ia.html", p=p, linhas=linhas,
                               prenotacao_numero=prenot or "",
                               papeis_que_pedem=PAPEIS_QUE_PEDEM)

    @app.route("/registro-imoveis/qualificacao-ia/<int:pedido_id>/levar", methods=["POST"])
    @roles_required(*PAPEIS_QUE_PEDEM)
    def ri_qualificacao_ia_levar(pedido_id: int):
        """Leva as exigências marcadas (como a pessoa as editou) ao formulário da
        nota. Não emite: a nota sai pelo botão de sempre, depois de conferida."""
        with db.connect() as con:
            p = QIA.mostrar(con, pedido_id)
        if not p:
            abort(404)
        escolhidas = [(int(i), request.form.get(f"texto_{i}") or "")
                      for i in request.form.getlist("escolhida") if i.isdigit()]
        try:
            with db.transaction() as con:
                linhas = QIA.levar(con, pedido_id, escolhidas, usuario=usuario_nome())
        except ValueError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ri_qualificacao_ia_ver", pedido_id=pedido_id))
        audit("RI_QUALIFICACAO_IA_LEVADA", "ri_qualificacao_ia", pedido_id,
              {"protocolo_id": p["protocolo_id"], "exigencias": len(linhas)})
        flash(f"{len(linhas)} exigência(s) no formulário da nota. Confira, edite o que "
              "precisar e emita — a nota só existe depois do botão «Emitir».", "success")
        return volta(p["protocolo_id"], ancora="emitir-nota", qualificacao=pedido_id)

    @app.route("/registro-imoveis/qualificacao-ia/configuracao", methods=["GET", "POST"])
    @roles_required("ADMIN")
    def ri_qualificacao_ia_configuracao():
        """O TETO DIÁRIO — decisão do oficial em 26/10/2026: 20 leituras por dia
        de fábrica, e o ADMIN o muda aqui. Cada mudança fica na auditoria
        (`RI_QUALIFICACAO_IA_TETO`, com o antes e o depois). Vazio volta ao
        padrão do catálogo de IA."""
        if request.method == "POST":
            try:
                novo = QIA.validar_teto(request.form.get("teto"))
            except QIA.QualificacaoIAError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("ri_qualificacao_ia_configuracao"))
            with db.connect() as con:
                antes = QIA.teto_do_dia(con)
            db.set_settings({QIA.CHAVE_DO_TETO: "" if novo is None else str(novo)})
            with db.connect() as con:
                depois = QIA.teto_do_dia(con)
            audit("RI_QUALIFICACAO_IA_TETO", "settings", None,
                  {"antes": antes, "depois": depois, "padrao": novo is None})
            flash(f"Teto da qualificação assistida: {depois} leitura(s) por dia"
                  + (" (o padrão de fábrica)." if novo is None else "."), "success")
            return redirect(url_for("ri_qualificacao_ia_configuracao"))
        import ia_uso as USO
        with db.connect() as con:
            teto = QIA.teto_do_dia(con)
            feitas = USO.usos_do_dia(banco(con), QIA.FINALIDADE, db.now()[:10])
        return render_template("ri_qualificacao_ia_config.html", teto=teto,
                               padrao=QIA.teto_padrao(), feitas=feitas,
                               gravado=db.get_setting(QIA.CHAVE_DO_TETO, "") or "",
                               minimo=QIA.TETO_MINIMO, maximo=QIA.TETO_MAXIMO)
