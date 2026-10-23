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

from datetime import datetime
from pathlib import Path

from flask import abort, flash, jsonify, redirect, render_template, request, send_file, url_for

from bd_nativo import banco
import ccn_consulta as CQ
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
            if not CE.tem_tabelas(con):
                abort(404)
            bd = banco(con)
            lote = bd.um("SELECT * FROM nt_ccn_lotes WHERE id = %s", (lote_id,))
            if lote is None:
                abort(404)
            itens = bd.ler(
                """SELECT i.*, c.nome, c.numero FROM nt_ccn_itens i
                     LEFT JOIN nt_cartoes c ON c.id = i.cartao_id
                    WHERE i.lote_id = %s ORDER BY i.posicao, i.id""", (lote_id,))
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
            lote = banco(con).um("SELECT arquivo_nome, caminho FROM nt_ccn_lotes WHERE id = %s",
                                 (lote_id,)) if CE.tem_tabelas(con) else None
        if lote is None or not Path(lote["caminho"]).is_file():
            abort(404)
        return send_file(lote["caminho"], mimetype="text/xml", as_attachment=True,
                         download_name=lote["arquivo_nome"])

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

    # ------------------------------------------------- a consulta (exportação)
    # «crie a integracao do ccn para receber e consultar na base nacional» —
    # o oficial, 15/10/2026. O domínio mora em `ccn_consulta.py`.

    @app.route("/notas/ccn/consultas", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_ccn_consultas():
        """Pedir uma consulta pelo CPF, e a lista das últimas. O POST ESCREVE o pedido."""
        if request.method == "POST":
            ambiente = request.form.get("ambiente") or "PRODUCAO"
            try:
                with db.transaction() as con:
                    cid = CQ.pedir(con, request.form.get("cpf"), ambiente,
                                   usuario=usuario_nome(), agora=_agora())
            except CQ.ConsultaError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("notas_ccn_consultas"))
            audit("NT_CCN_CONSULTA_PEDIDA", "nt_ccn_consultas", cid, {"ambiente": ambiente})
            return redirect(url_for("notas_ccn_consulta", consulta_id=cid))
        with db.connect() as con:
            lista = CQ.consultas(con)
        return render_template("notas_ccn_consultas.html", consultas=lista,
                               ambientes=CE.AMBIENTES)

    @app.route("/notas/ccn/consultas/<int:consulta_id>")
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_ccn_consulta(consulta_id: int):
        """A consulta: o código para a extensão, as fichas e o que completaria o cartão. Só LÊ."""
        try:
            indice = max(0, int(request.args.get("ficha") or 0))
        except ValueError:
            indice = 0
        with db.connect() as con:
            c = CQ.carregar(con, consulta_id)
            if c is None:
                abort(404)
            proposta = CQ.proposta(con, c, indice) if c["registros"] else None
        fichas = [CQ.ficha_para_a_tela(f) for f in c["registros"]]
        return render_template("notas_ccn_consulta.html", c=c, fichas=fichas, indice=indice,
                               proposta=proposta, host=CE.AMBIENTES[c["ambiente"]],
                               codigo=CQ.codigo_da_consulta(app.secret_key, consulta_id))

    @app.route("/notas/ccn/consultas/<int:consulta_id>/aplicar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def notas_ccn_consulta_aplicar(consulta_id: int):
        """Completa o cartão de firma com o que ele não tem. ESCREVE — só campo vazio."""
        try:
            indice = max(0, int(request.form.get("ficha") or 0))
        except ValueError:
            indice = 0
        try:
            with db.transaction() as con:
                c = CQ.carregar(con, consulta_id)
                if c is None:
                    abort(404)
                r = CQ.aplicar(con, c, indice=indice, usuario=usuario_nome(), agora=_agora())
        except CQ.ConsultaError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("notas_ccn_consulta", consulta_id=consulta_id, ficha=indice))
        audit("NT_CCN_CONSULTA_APLICADA", "nt_cartoes", r["cartao_id"],
              {"consulta": consulta_id, "campos": sorted(r["campos"])})
        if r["campos"]:
            flash(f"Cartão completado com {len(r['campos'])} campo(s) do CCN: "
                  + ", ".join(CQ.ROTULOS[k] for k in r["campos"]) + ".", "success")
        else:
            flash("Nada entrou: os campos foram preenchidos por outra pessoa enquanto a tela "
                  "estava aberta.", "warning")
        return redirect(url_for("notas_ccn_consulta", consulta_id=consulta_id, ficha=indice))

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

    @app.route("/ccn/ponte/consulta")
    def ccn_ponte_consulta():
        """O CPF que o código da consulta abre, para a extensão consultar. Só LÊ."""
        _so_desta_maquina()
        codigo = request.args.get("codigo") or ""
        try:
            with db.connect() as con:
                c = CQ.consulta_pelo_codigo(con, app.secret_key, codigo)
            return jsonify({"ok": True, **CQ.para_a_extensao(c, codigo.strip())})
        except CQ.ConsultaError as erro:
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
        # A MESMA PORTA SERVE A CONSULTA (15/10/2026): o código dela começa com
        # «C». Uma porta só, e não duas, porque é ela que está isenta do token
        # de formulário — e isenção se dá ao menor número de rotas possível.
        if CQ.e_codigo_de_consulta(codigo):
            try:
                with db.transaction() as con:
                    c = CQ.consulta_pelo_codigo(con, app.secret_key, codigo)
                    r = CQ.registrar_resposta(con, c, dados, _agora())
            except CQ.ConsultaError as erro:
                return jsonify({"ok": False, "erro": str(erro)}), 400
            audit("NT_CCN_CONSULTA_RESPONDIDA", "nt_ccn_consultas", c["id"], r)
            return jsonify({"ok": True, **r})
        try:
            with db.transaction() as con:
                lote = CE.lote_pelo_codigo(con, app.secret_key, codigo)
                r = CE.registrar_resultado(con, lote, dados, _agora())
        except CE.CcnError as erro:
            return jsonify({"ok": False, "erro": str(erro)}), 400
        audit("NT_CCN_RESULTADO", "nt_ccn_lotes", lote["id"],
              {k: r[k] for k in ("situacao", "status", "aceitos", "recusados", "duplicados")})
        return jsonify({"ok": True, **r})
