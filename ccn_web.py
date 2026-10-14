"""As telas do envio ao CCN, e a ponte com a extensão — ver `ccn_envio.py`.

Duas portas, para duas pessoas:
    - as telas (`/notas/ccn…`), do oficial e do gerente: quem falta mandar,
      gerar o lote, o código de envio, o que o CCN respondeu, e o arquivo
      para quem preferir subir pela tela de importação do portal;
    - a ponte (`/ccn/ponte/…`), da extensão «CG CCN Assistente»: busca o lote
      pelo código e devolve o resultado. **Sem a sessão do Cartório Gestão, e
      só para quem está NESTA máquina** — o navegador do envio é o do
      servidor, onde também fica o token A3.

A ponte não chama o CCN, e nenhuma tela daqui chama: quem fala com o CCN é a
extensão, de dentro da aba do portal (a Cloudflare só deixa passar navegador).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from flask import abort, flash, jsonify, redirect, render_template, request, send_file, url_for

import ccn_envio as CE

#: Quem pode falar com a ponte: o próprio servidor.
LOCAIS = {"127.0.0.1", "::1"}


def registrar_rotas(app, db, login_required, roles_required, audit):
    usuario_nome = app.extensions["usuario_nome"]

    def _pasta() -> Path:
        return Path(app.config["DATA_DIR"])

    def _agora() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _montar():
        import ccn_xml                                       # o formato do XSD v4
        return ccn_xml.montar

    @app.route("/notas/ccn")
    @roles_required("ADMIN", "MANAGER")
    def notas_ccn():
        """O painel: quantos faltam, os lotes e o código de cada um. Só LÊ."""
        ambiente = request.args.get("ambiente") or "HOMOLOGACAO"
        if ambiente not in CE.AMBIENTES:
            ambiente = "HOMOLOGACAO"
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            resumo = CE.resumo(con, ambiente)
            lotes = CE.lotes(con)
        for l in lotes:
            l["codigo"] = (CE.codigo_do_lote(app.secret_key, l["id"])
                           if l["situacao"] in ("GERADO", "ENVIADO", "FALHOU", "COM_ERROS") else None)
        try:
            import ccn_xml
            formato = ccn_xml.situacao_do_formato()
        except ImportError:
            formato = {"pronto": False, "motivo": "o módulo do formato (ccn_xml) não está instalado"}
        return render_template("notas_ccn.html", resumo=resumo, lotes=lotes, ambiente=ambiente,
                               ambientes=CE.AMBIENTES, formato=formato,
                               prazo=CE.PRAZO_DO_PROVIMENTO_DIAS)

    @app.route("/notas/ccn/lotes", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def notas_ccn_gerar():
        ambiente = request.form.get("ambiente") or "HOMOLOGACAO"
        # «Quantas pessoas» (13/10/2026): o primeiro envio à produção se faz
        # com uma pessoa só — a chave que o oficial conseguiu é de produção.
        try:
            maximo = max(1, min(500, int(request.form.get("maximo") or 500)))
        except ValueError:
            maximo = 500
        try:
            montar = _montar()
            with db.transaction() as con:
                con.row_factory = sqlite3.Row
                r = CE.gerar_lote(con, _pasta(), ambiente=ambiente, usuario=usuario_nome(),
                                  agora=_agora(), montar=montar, maximo=maximo)
        except (CE.CcnError, ValueError) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("notas_ccn", ambiente=ambiente))
        except ImportError:
            flash("O formato do arquivo do CCN (XSD v4) ainda não está nesta instalação.", "danger")
            return redirect(url_for("notas_ccn", ambiente=ambiente))
        audit("NT_CCN_LOTE_GERADO", "nt_ccn_lotes", r["lote_id"],
              {"quantidade": r["quantidade"], "bytes": r["bytes"], "ambiente": ambiente})
        aviso = (f" Ficaram {r['ficaram_para_o_proximo']} para o próximo lote (teto de tamanho)."
                 if r["ficaram_para_o_proximo"] else "")
        flash(f"Lote {r['lote_id']} gerado: {r['quantidade']} pessoas, "
              f"{r['bytes'] / 1_000_000:.1f} MB.{aviso}", "success")
        return redirect(url_for("notas_ccn_lote", lote_id=r["lote_id"]))

    @app.route("/notas/ccn/lotes/<int:lote_id>")
    @roles_required("ADMIN", "MANAGER")
    def notas_ccn_lote(lote_id: int):
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            if not CE.tem_tabelas(con):
                abort(404)
            lote = con.execute("SELECT * FROM nt_ccn_lotes WHERE id=?", (lote_id,)).fetchone()
            if lote is None:
                abort(404)
            itens = [dict(r) for r in con.execute(
                """SELECT i.*, c.nome, c.numero FROM nt_ccn_itens i
                     LEFT JOIN nt_cartoes c ON c.id = i.cartao_id
                    WHERE i.lote_id=? ORDER BY i.posicao""", (lote_id,))]
        lote = dict(lote)
        codigo = (CE.codigo_do_lote(app.secret_key, lote_id)
                  if lote["situacao"] in ("GERADO", "ENVIADO", "FALHOU", "COM_ERROS") else None)
        return render_template("notas_ccn_lote.html", lote=lote, itens=itens, codigo=codigo,
                               host=CE.AMBIENTES[lote["ambiente"]])

    @app.route("/notas/ccn/lotes/<int:lote_id>/arquivo")
    @roles_required("ADMIN", "MANAGER")
    def notas_ccn_arquivo(lote_id: int):
        """O XML, para quem preferir subir pela tela de importação do portal."""
        with db.connect() as con:
            lote = con.execute("SELECT arquivo_nome, caminho FROM nt_ccn_lotes WHERE id=?",
                               (lote_id,)).fetchone() if CE.tem_tabelas(con) else None
        if lote is None or not Path(lote[1]).is_file():
            abort(404)
        return send_file(lote[1], mimetype="text/xml", as_attachment=True,
                         download_name=lote[0])

    @app.route("/notas/ccn/lotes/<int:lote_id>/descartar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def notas_ccn_descartar(lote_id: int):
        motivo = request.form.get("motivo") or ""
        try:
            with db.transaction() as con:
                CE.descartar(con, lote_id, motivo, _agora())
        except CE.CcnError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("notas_ccn_lote", lote_id=lote_id))
        audit("NT_CCN_LOTE_DESCARTADO", "nt_ccn_lotes", lote_id, {"motivo": motivo})
        flash(f"Lote {lote_id} descartado. As pessoas dele voltam a estar pendentes.", "success")
        return redirect(url_for("notas_ccn"))

    # ------------------------------------------------------------- a ponte

    def _so_desta_maquina():
        if request.remote_addr not in LOCAIS:
            abort(403, "a ponte do CCN só atende o navegador do próprio servidor")

    @app.route("/ccn/ponte/lote")
    def ccn_ponte_lote():
        """O lote que o código abre, para a extensão enviar. Só LÊ."""
        _so_desta_maquina()
        codigo = request.args.get("codigo") or ""
        try:
            with db.connect() as con:
                lote = CE.lote_pelo_codigo(con, app.secret_key, codigo)
            return jsonify({"ok": True, **CE.para_a_extensao(lote, codigo.strip())})
        except CE.CcnError as erro:
            return jsonify({"ok": False, "erro": str(erro)}), 400

    @app.route("/ccn/ponte/resultado", methods=["POST"])
    def ccn_ponte_resultado():
        """O que o CCN respondeu, trazido pela extensão. ESCREVE.

        Isenta do token de formulário (CSRF) como o webhook do WhatsApp, e
        pelo mesmo motivo: quem chama não tem a sessão; o que autentica é o
        código do lote — e a rota só responde a esta máquina.
        """
        _so_desta_maquina()
        dados = request.get_json(silent=True) or {}
        codigo = str(dados.get("codigo") or "")
        try:
            with db.transaction() as con:
                lote = CE.lote_pelo_codigo(con, app.secret_key, codigo)
                r = CE.registrar_resultado(con, lote, dados, _agora())
        except CE.CcnError as erro:
            return jsonify({"ok": False, "erro": str(erro)}), 400
        audit("NT_CCN_RESULTADO", "nt_ccn_lotes", lote["id"],
              {k: r[k] for k in ("situacao", "status", "aceitos", "recusados", "duplicados")})
        return jsonify({"ok": True, **r})
