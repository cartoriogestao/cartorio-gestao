"""Rotas do editor unificado de modelos — Marco 1 (RCPN).

Telas: /modelos/editor e /modelos/editor/<area>/<template_id>
APIs JSON do editor (rascunho/publicar/histórico/prévia via cliente do motor).

NÃO cria as rotas /modelos/api/previa|campos|trechos-bloqueados —
essas são do Robô Fidelidade (modelos_motor*).
"""
from __future__ import annotations

from flask import (
    Response, abort, flash, jsonify, redirect, render_template,
    request, session, url_for,
)

import modelos_editor as ED
import modelos_editor_motor as MOTOR
from modelos_editor_schema import (
    AREA_RCPN,
    PARTE_CORPO,
    PARTE_MOLDE,
    PARTES_TEXTO,
)
from modelos_elementos_schema import CABECALHO_FICOU_DE_FORA, NOME_DA_PARTE

QUEM_VE: tuple[str, ...] = ("ADMIN", "MANAGER", "USER")
QUEM_PUBLICA: tuple[str, ...] = ("ADMIN", "MANAGER")


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """Pendura o editor de modelos no app já construído."""
    usuario_nome = app.extensions["usuario_nome"]

    def _papel() -> str:
        user = None
        try:
            uid = session.get("user_id")
            if uid:
                with db.connect() as con:
                    row = con.execute(
                        "SELECT role FROM users WHERE id=?", (uid,)).fetchone()
                    if row:
                        return (row["role"] if hasattr(row, "keys")
                                else row[0]) or ""
        except Exception:
            pass
        return (session.get("role") or "").upper()

    def _agora() -> str:
        return db.now()

    def _settings():
        return db.get_settings

    @app.route("/modelos/editor")
    @login_required
    @roles_required(*QUEM_VE)
    def modelos_editor_lista():
        with db.connect() as con:
            ED.garantir_schema(con)
            modelos = ED.listar_modelos_rcpn(con)
            ligada = ED.chave_ligada(con, AREA_RCPN)
        return render_template(
            "modelos_editor.html",
            modo="lista",
            area=AREA_RCPN,
            modelos=modelos,
            modelo=None,
            chave_ligada=ligada,
            pode_publicar=ED.pode_publicar(_papel()),
            cabecalho_de_fora=CABECALHO_FICOU_DE_FORA,
            nome_da_parte=NOME_DA_PARTE,
        )

    @app.route("/modelos/editor/<area>/<template_id>")
    @login_required
    @roles_required(*QUEM_VE)
    def modelos_editor_editar(area, template_id):
        try:
            a = ED._area_ok(area)
            t = ED._tpl_ok(template_id)
        except ED.EditorError as err:
            flash(str(err), "danger")
            return redirect(url_for("modelos_editor_lista"))

        with db.connect() as con:
            ED.garantir_schema(con)
            modelos = ED.listar_modelos_rcpn(con)
            partes_ids = ([PARTE_MOLDE] if ED._eh_molde(t) else list(PARTES_TEXTO))
            partes = []
            for p in partes_ids:
                c = ED.carregar(con, area=a, template_id=t, parte=p, qual="auto",
                                marcar_para_edicao=True)
                partes.append({
                    "parte": p,
                    "nome": ("Molde ODT" if p == PARTE_MOLDE
                             else NOME_DA_PARTE.get(p, p)),
                    "conteudo": c.get("conteudo") or "",
                    "sha256": c.get("sha256"),
                    "origem": c.get("origem"),
                    "status": c.get("status"),
                    "id": c.get("id"),
                    "binario": bool(c.get("binario")),
                    "marcado_so_exibicao": bool(c.get("marcado_so_exibicao")),
                    "avisos_marcacao": c.get("avisos_marcacao") or [],
                })
            ligada = ED.chave_ligada(con, AREA_RCPN)
            info = next((m for m in modelos if m["template_id"] == t), None)

        return render_template(
            "modelos_editor.html",
            modo="editar",
            area=a,
            modelos=modelos,
            modelo={
                "template_id": t,
                "nome": (info or {}).get("nome") or t,
                "explica": (info or {}).get("explica") or "",
                "tipo": (info or {}).get("tipo") or "termo",
                "partes": partes,
            },
            chave_ligada=ligada,
            pode_publicar=ED.pode_publicar(_papel()),
            cabecalho_de_fora=CABECALHO_FICOU_DE_FORA,
            nome_da_parte=NOME_DA_PARTE,
        )

    # ----------------------- APIs JSON do editor -----------------------

    @app.route("/modelos/editor/api/salvar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_VE)
    def modelos_editor_api_salvar():
        dados = request.get_json(silent=True) or {}
        area = dados.get("area") or request.form.get("area") or AREA_RCPN
        template_id = (dados.get("template_id")
                       or request.form.get("template_id") or "")
        parte = dados.get("parte") or request.form.get("parte") or PARTE_CORPO
        conteudo = dados.get("conteudo")
        if conteudo is None:
            conteudo = request.form.get("conteudo")
        nota = dados.get("nota") or request.form.get("nota") or ""
        blob = None
        if "arquivo" in request.files:
            f = request.files["arquivo"]
            blob = f.read()
        try:
            with db.transaction() as con:
                # Trechos do motor para recusar bloco adulterado já no rascunho
                blk = MOTOR.trechos_bloqueados(area=area, tipo=template_id)
                row = ED.salvar_rascunho(
                    con, area=area, template_id=template_id, parte=parte,
                    conteudo=conteudo if blob is None else None,
                    conteudo_blob=blob,
                    autor=usuario_nome(), agora=_agora(), nota=nota,
                    get_settings=_settings(),
                    trechos_bloqueados=blk.get("trechos") or [])
            audit("MODELO_RASCUNHO", "mo_versoes", row.get("id"),
                  {"template_id": template_id, "parte": parte})
            return jsonify(ok=True, versao=row)
        except ED.EditorError as err:
            return jsonify(ok=False, erro=str(err)), 400
        except Exception as err:  # noqa: BLE001
            return jsonify(ok=False, erro=str(err)), 500

    @app.route("/modelos/editor/api/publicar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_VE)  # USER chega aqui e é recusado na regra
    def modelos_editor_api_publicar():
        dados = request.get_json(silent=True) or {}
        area = dados.get("area") or AREA_RCPN
        template_id = dados.get("template_id") or ""
        parte = dados.get("parte") or PARTE_CORPO
        nota = dados.get("nota") or ""
        try:
            with db.transaction() as con:
                blk = MOTOR.trechos_bloqueados(area=area, tipo=template_id)
                row = ED.publicar(
                    con, area=area, template_id=template_id, parte=parte,
                    autor=usuario_nome(), agora=_agora(), nota=nota,
                    papel_usuario=_papel(),
                    get_settings=_settings(),
                    trechos_bloqueados=blk.get("trechos") or [],
                    conteudo=dados.get("conteudo"),
                    conteudo_blob=None)
            audit("MODELO_PUBLICADO", "mo_versoes", row.get("id"),
                  {"template_id": template_id, "parte": parte})
            return jsonify(ok=True, versao=row)
        except ED.EditorError as err:
            return jsonify(ok=False, erro=str(err)), 403
        except Exception as err:  # noqa: BLE001
            return jsonify(ok=False, erro=str(err)), 500

    @app.route("/modelos/editor/api/historico")
    @login_required
    @roles_required(*QUEM_VE)
    def modelos_editor_api_historico():
        area = request.args.get("area") or AREA_RCPN
        template_id = request.args.get("template_id") or ""
        parte = request.args.get("parte") or PARTE_CORPO
        try:
            with db.connect() as con:
                if not template_id:
                    # Sem modelo: o historico geral da area, e nao 400.
                    return jsonify(ok=True, geral=True,
                                   historico=ED.historico_geral(con, area=area))
                hist = ED.historico(
                    con, area=area, template_id=template_id, parte=parte)
            return jsonify(ok=True, historico=hist)
        except ED.EditorError as err:
            return jsonify(ok=False, erro=str(err)), 400

    def _id_da_versao(nome: str) -> int:
        try:
            return max(int(request.args.get(nome) or 0), 0)
        except ValueError:
            return 0  # `a=xyz` dava 500; vale como «nao informado»

    @app.route("/modelos/editor/api/diff")
    @login_required
    @roles_required(*QUEM_VE)
    def modelos_editor_api_diff():
        try:
            with db.connect() as con:
                par = ED.par_para_diff(
                    con, id_a=_id_da_versao("a"), id_b=_id_da_versao("b"),
                    area=request.args.get("area") or AREA_RCPN,
                    template_id=request.args.get("template_id") or "",
                    parte=request.args.get("parte") or "")
                if par is None:
                    return jsonify(
                        ok=True, iguais=True, diff="", id_a=None, id_b=None,
                        aviso="Ainda não há duas versões deste modelo para comparar.")
                d = ED.diff_versoes(con, *par)
            return jsonify(ok=True, **d)
        except ED.VersaoNaoEncontrada as err:
            return jsonify(ok=False, erro=str(err)), 404
        except ED.EditorError as err:
            return jsonify(ok=False, erro=str(err)), 400

    @app.route("/modelos/editor/api/restaurar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_VE)
    def modelos_editor_api_restaurar():
        dados = request.get_json(silent=True) or {}
        try:
            vid = int(dados.get("versao_id") or 0)
            with db.transaction() as con:
                row = ED.restaurar_como_rascunho(
                    con, vid, autor=usuario_nome(), agora=_agora())
            audit("MODELO_RESTAURADO", "mo_versoes", row.get("id"),
                  {"de": vid})
            return jsonify(ok=True, versao=row)
        except ED.EditorError as err:
            return jsonify(ok=False, erro=str(err)), 400

    @app.route("/modelos/editor/api/previa", methods=["POST"])
    @login_required
    @roles_required(*QUEM_VE)
    def modelos_editor_api_previa():
        """Prévia do editor — delega ao cliente do motor (com fallback)."""
        dados = request.get_json(silent=True) or {}
        area = dados.get("area") or AREA_RCPN
        template_id = (dados.get("template_id") or "").strip().upper()
        papel = dados.get("papel") or "a4"
        formato = dados.get("formato") or "html"
        conteudo = dados.get("conteudo")
        form = {}
        if isinstance(conteudo, dict):
            for k, v in conteudo.items():
                form[f"parte_{str(k).lower()}"] = v if isinstance(v, str) else ""
        elif isinstance(conteudo, str):
            form["parte_corpo"] = conteudo
        try:
            with db.connect() as con:
                # Sem app_url → fallback local (motor ainda não no ar)
                resp = MOTOR.previa(
                    con, area=area, template_id=template_id,
                    conteudo=conteudo if isinstance(conteudo, dict) else None,
                    dados=dados.get("dados"),
                    assento_id=dados.get("assento_id"),
                    papel=papel, formato=formato,
                    form_fallback=form)
            codigo = resp.pop("_http", 200)
            return jsonify(resp), codigo
        except Exception as err:  # noqa: BLE001
            return jsonify(ok=False, erro=str(err), avisos=[], erros=[]), 200

    @app.route("/modelos/editor/api/campos")
    @login_required
    @roles_required(*QUEM_VE)
    def modelos_editor_api_campos():
        area = request.args.get("area") or AREA_RCPN
        tipo = request.args.get("tipo") or request.args.get("template_id") or ""
        return jsonify(MOTOR.campos(area=area, tipo=tipo))

    @app.route("/modelos/editor/api/trechos-bloqueados")
    @login_required
    @roles_required(*QUEM_VE)
    def modelos_editor_api_trechos_bloqueados():
        area = request.args.get("area") or AREA_RCPN
        tipo = request.args.get("tipo") or request.args.get("template_id") or ""
        return jsonify(MOTOR.trechos_bloqueados(area=area, tipo=tipo))

    @app.route("/modelos/editor/api/molde/<template_id>/baixar")
    @login_required
    @roles_required(*QUEM_VE)
    def modelos_editor_api_molde_baixar(template_id):
        with db.connect() as con:
            c = ED.carregar(con, area=AREA_RCPN, template_id=template_id,
                            parte=PARTE_MOLDE, qual="auto")
            if not c.get("conteudo_blob"):
                abort(404)
            nome = f"{template_id.lower()}.odt"
            return Response(
                c["conteudo_blob"],
                mimetype="application/vnd.oasis.opendocument.text",
                headers={
                    "Content-Disposition": f'attachment; filename="{nome}"',
                })

    @app.route("/modelos/editor/api/semear", methods=["POST"])
    @login_required
    @roles_required(*QUEM_PUBLICA)
    def modelos_editor_api_semear():
        dados = request.get_json(silent=True) or {}
        try:
            with db.transaction() as con:
                feitos = ED.semear_v1(
                    con, area=dados.get("area") or AREA_RCPN,
                    template_id=dados.get("template_id"),
                    autor=usuario_nome(), agora=_agora(),
                    forcar=bool(dados.get("forcar")))
            audit("MODELO_SEMENTE", "mo_versoes", None,
                  {"qtd": len(feitos)})
            return jsonify(ok=True, feitos=feitos)
        except ED.EditorError as err:
            return jsonify(ok=False, erro=str(err)), 400
