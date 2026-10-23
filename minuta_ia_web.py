"""As rotas do agente de minutas — ver `minuta_ia.py`.

O quadro mora DENTRO das duas telas onde o ato se escreve — a ficha da
matrícula (RI) e a tela do ato em lavratura (Notas) —, como a leitura dos
anexos mora na tela do assento do RCPN: um lugar só para pedir, acompanhar e
revisar. Nenhuma rota daqui lavra, numera, sela ou cobra.
"""
from __future__ import annotations

from pathlib import Path

from flask import abort, flash, jsonify, redirect, render_template, request, url_for

import agente_provedores as AP
import minuta_ia as MI
import protocolo_documentos as PDOC
import ri_documentos as RDOC
from bd_nativo import banco
from storage import save_upload

#: As telas que mostram o quadro, e de onde sai o id do alvo.
TELAS = {"ri_ficha": (MI.RI, "matricula_id"), "notas_ato": (MI.NOTAS, "ato_id")}

PAPEIS_QUE_PEDEM = ("ADMIN", "MANAGER", "USER")


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_nome = app.extensions["usuario_nome"]

    def pasta() -> Path:
        return Path(app.config["DATA_DIR"])

    def raiz_dos_arquivos() -> Path:
        return Path(db.get_setting("archive_root", "").strip()
                    or (Path(db.db_path).parent / "arquivos"))

    def volta(atribuicao: str, alvo_id: int):
        if atribuicao == MI.RI:
            return redirect(url_for("ri_ficha", matricula_id=alvo_id) + "#agente-minutas")
        return redirect(url_for("notas_ato", ato_id=alvo_id) + "#agente-minutas")

    @app.context_processor
    def _agente_de_minutas_na_tela() -> dict:
        """O que o quadro precisa, só nas duas telas que o mostram. Só LÊ."""
        try:
            onde = request.endpoint or ""
            args = request.view_args or {}
        except RuntimeError:
            return {}
        if onde not in TELAS:
            return {}
        atribuicao, chave = TELAS[onde]
        alvo_id = args.get(chave)
        if alvo_id is None:
            return {}
        try:
            with db.connect() as con:
                try:
                    MI.alvo(con, atribuicao, alvo_id)
                except MI.MinutaIAError as motivo:
                    return {"agente_minutas": {"cabe": False, "motivo": str(motivo),
                                               "atribuicao": atribuicao}}
                return {"agente_minutas": {
                    "cabe": True, "atribuicao": atribuicao, "alvo_id": alvo_id,
                    "ligado": AP.tem_chave(pasta(), MI.PROVEDOR),
                    "disponiveis": MI.documentos_disponiveis(con, atribuicao, alvo_id),
                    "prenotacoes": (MI.prenotacoes_da_matricula(con, alvo_id)
                                    if atribuicao == MI.RI else []),
                    "andamento": MI.em_andamento(con, atribuicao, alvo_id),
                    "historico": MI.historico(con, atribuicao, alvo_id),
                    "modelo": MI.MODELO, "esforco": MI.ESFORCO,
                    "maximo": MI.MAXIMO_DE_DOCUMENTOS,
                    "limite_mb": MI.LIMITE_DOS_DOCUMENTOS // 1048576}}
        except Exception as erro:                      # noqa: BLE001 — o quadro some, a tela abre
            app.logger.error("Quadro do agente de minutas não montou.", exc_info=erro)
            return {}

    def _guardar_os_juntados(atribuicao: str, alvo_id: int) -> list[int]:
        """Grava os arquivos juntados no pedido ONDE O ATO OS ARQUIVA. ESCREVE.

        RI: na prenotação escolhida, que é onde o título apresentado mora e de
        onde a tela de lavrar os mostra. Notas: no próprio ato, que é o
        arquivamento dele. Todos se conferem ANTES de o primeiro chegar ao disco
        (PDF, JPG ou PNG de verdade, até 25 MB) — a régua do Protocolo Geral.
        """
        enviados = [f for f in request.files.getlist("arquivos") if f and f.filename]
        if not enviados:
            return []
        for f in enviados:
            PDOC.conferir_arquivo(*PDOC.medir_envio(f))
        uid = int(app.extensions["usuario_id"]() or 0)
        descricao = "Juntado ao pedir a minuta ao agente"
        ids = []
        if atribuicao == MI.RI:
            pid = request.form.get("prenotacao_destino") or ""
            with db.connect() as con:
                p = banco(con).um(
                    "SELECT id, numero FROM ri_protocolos WHERE id = %s AND matricula_id = %s",
                    (int(pid) if pid.isdigit() else -1, int(alvo_id)))
            if not p:
                raise MI.MinutaIAError(
                    "Escolha a prenotação em que os documentos juntados ficam guardados — "
                    "é dela que a tela de lavrar os mostra.")
            nome = "".join(c if (c.isalnum() or c in "-_.") else "_"
                           for c in str(p["numero"]))[:60] or "sem-numero"
            destino = raiz_dos_arquivos() / "ri" / "prenotacoes" / nome
            for f in enviados:
                info = save_upload(f, destino)
                ids.append(db.add_attachment(RDOC.ENTIDADE_RI, int(p["id"]), info, uid,
                                             descricao))
            audit("RI_PRENOTACAO_DOCUMENTO", "RI_PROTOCOLO", int(p["id"]),
                  {"anexos": ids, "qtd": len(ids), "pelo": "agente de minutas"})
        else:
            destino = (raiz_dos_arquivos() / "notas" / "atos"
                       / f"ato-{int(alvo_id):05d}" / "evidencias")
            for f in enviados:
                info = save_upload(f, destino)
                anexo_id = db.add_attachment("NT_ATO", int(alvo_id), info, uid, descricao)
                ids.append(anexo_id)
                audit("NT_ATO_ANEXO", "NT_ATO", int(alvo_id),
                      {"attachment_id": anexo_id, "sha256": info["sha256"],
                       "descricao": descricao})
        return ids

    def _comecar(pedido_id: int, atribuicao: str, alvo_id: int, revisao: bool):
        audit("MINUTA_IA_REVISAO_PEDIDA" if revisao else "MINUTA_IA_PEDIDA",
              "mi_pedidos", pedido_id, {"atribuicao": atribuicao, "alvo": alvo_id})
        MI.preparar_em_segundo_plano(db.db_path, pasta(), pedido_id)
        flash("O agente começou a preparar a minuta. Leva alguns minutos — o quadro "
              "abaixo se atualiza sozinho quando ela ficar pronta.", "success")

    @app.route("/agente-minutas/<atribuicao>/<int:alvo_id>/pedir", methods=["POST"])
    @roles_required(*PAPEIS_QUE_PEDEM)
    def minuta_ia_pedir(atribuicao: str, alvo_id: int):
        atribuicao = atribuicao.upper()
        if atribuicao not in MI.ATRIBUICOES:
            abort(404)
        if not AP.tem_chave(pasta(), MI.PROVEDOR):
            flash("Esta instalação não tem a chave do Claude: o agente de minutas não "
                  "funciona sem ela (Administrativo → Agente do sistema).", "danger")
            return volta(atribuicao, alvo_id)
        try:
            with db.connect() as con:
                MI.alvo(con, atribuicao, alvo_id)
            juntados = _guardar_os_juntados(atribuicao, alvo_id)
            marcados = [int(x) for x in request.form.getlist("anexo") if x.isdigit()]
            with db.transaction() as con:
                pid = MI.pedir(con, atribuicao, alvo_id, anexos_ids=marcados + juntados,
                               tipo_ato=request.form.get("tipo_ato") or "",
                               instrucao=request.form.get("instrucao") or "",
                               usuario=usuario_nome())
        except ValueError as erro:
            flash(str(erro), "danger")
            return volta(atribuicao, alvo_id)
        _comecar(pid, atribuicao, alvo_id, revisao=False)
        return volta(atribuicao, alvo_id)

    @app.route("/agente-minutas/pedido/<int:pedido_id>/revisar", methods=["POST"])
    @roles_required(*PAPEIS_QUE_PEDEM)
    def minuta_ia_revisar(pedido_id: int):
        with db.connect() as con:
            p = MI.mostrar(con, pedido_id)
        if not p:
            abort(404)
        try:
            juntados = _guardar_os_juntados(p["atribuicao"], p["alvo_id"])
            anteriores = [d["anexo_id"] for d in p["documentos"]]
            with db.transaction() as con:
                pid = MI.pedir(con, p["atribuicao"], p["alvo_id"],
                               anexos_ids=anteriores + juntados, anterior_id=pedido_id,
                               revisao=request.form.get("revisao") or "",
                               usuario=usuario_nome())
        except ValueError as erro:
            flash(str(erro), "danger")
            return volta(p["atribuicao"], p["alvo_id"])
        _comecar(pid, p["atribuicao"], p["alvo_id"], revisao=True)
        return volta(p["atribuicao"], p["alvo_id"])

    @app.route("/agente-minutas/pedido/<int:pedido_id>/usar", methods=["POST"])
    @roles_required(*PAPEIS_QUE_PEDEM)
    def minuta_ia_usar(pedido_id: int):
        """Põe a versão do agente no lugar do texto atual — com a pessoa decidindo."""
        with db.connect() as con:
            p = MI.mostrar(con, pedido_id)
        if not p:
            abort(404)
        try:
            with db.transaction() as con:
                frase = MI.pousar(con, pedido_id, usuario=usuario_nome(), forcar=True)
        except ValueError as erro:
            flash(str(erro), "danger")
            return volta(p["atribuicao"], p["alvo_id"])
        audit("MINUTA_IA_USADA", "mi_pedidos", pedido_id,
              {"atribuicao": p["atribuicao"], "alvo": p["alvo_id"]})
        flash(frase + " Confira com os documentos originais antes de lavrar.", "success")
        return volta(p["atribuicao"], p["alvo_id"])

    @app.route("/agente-minutas/pedido/<int:pedido_id>")
    @login_required
    def minuta_ia_pedido(pedido_id: int):
        """A versão inteira: o texto, as partes, as pendências e de onde saiu cada dado.

        Com `?andamento=1` responde só a situação, para o quadro perguntar de
        tempos em tempos sem baixar a minuta inteira.
        """
        with db.connect() as con:
            p = MI.mostrar(con, pedido_id)
        if not p:
            abort(404)
        if request.args.get("andamento"):
            return jsonify({"id": p["id"], "situacao": p["situacao"]})
        return render_template("minuta_ia_pedido.html", p=p)
