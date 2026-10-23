"""Rotas web — Controle de produtividade (ADMIN, MANAGER, USER)."""
from __future__ import annotations

from typing import Any, Callable

from flask import Response, jsonify

import produtividade as PR
from bd_nativo import banco


def _usuario_sessao(raw: Any) -> dict[str, Any]:
    """Normaliza linha do banco ou dict retornado por `current_user()`."""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    if hasattr(raw, "keys"):
        return {k: raw[k] for k in raw.keys()}
    return {}


def _parse_filtro_responsavel(
    raw: str | None,
    *,
    role: str,
    user_id: int | None,
) -> tuple[int | None, str]:
    """Devolve (user_id para SQL ou None=todos) e valor do select ('Todos' ou id str)."""
    if role not in ("ADMIN", "MANAGER"):
        uid = int(user_id) if user_id else None
        return uid, str(uid) if uid else ""
    val = (raw or "Todos").strip()
    if val in ("", "Todos", "todos"):
        return None, "Todos"
    try:
        return int(val), val
    except (TypeError, ValueError):
        return None, "Todos"


def _json_erro(msg: str, codigo: int = 400):
    return jsonify({"ok": False, "erro": msg}), codigo


def register_produtividade_routes(
    app,
    *,
    login_required,
    roles_required,
    get_db,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    current_user_fn: Callable[[], dict[str, Any] | None],
) -> None:
    @app.route("/administrativo/produtividade", methods=["GET", "POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def produtividade_lista():
        user = _usuario_sessao(current_user_fn())
        role = (user.get("role") or "USER").upper()
        user_id = user.get("id")
        username = user.get("username") or ""
        full_name = (user.get("full_name") or username or "").strip()

        if request.method == "POST":
            acao = (request.form.get("acao") or "criar").strip()
            with get_db() as con:
                try:
                    if acao == "excluir":
                        if role not in ("ADMIN", "MANAGER"):
                            raise ValueError("Só administrador ou gerente pode excluir.")
                        rid = int(request.form.get("registro_id") or "0")
                        PR.excluir_registro(con, rid)
                        con.commit()
                        flash("Registro removido.", "success")
                    else:
                        esc_id = request.form.get("responsavel_user_id")
                        if role in ("ADMIN", "MANAGER") and esc_id:
                            responsavel_user_id = int(esc_id)
                            resp_nome = (request.form.get("responsavel_nome") or "").strip()
                        else:
                            responsavel_user_id = int(user_id) if user_id else None
                            resp_nome = full_name or username
                        planejado_raw = request.form.get("tempo_planejado_min")
                        planejado = None
                        if planejado_raw is not None and str(planejado_raw).strip() != "":
                            planejado = float(planejado_raw)
                        PR.registrar_registro(
                            con,
                            responsavel_user_id=responsavel_user_id,
                            responsavel_nome=resp_nome or full_name or username,
                            categoria=request.form.get("categoria") or "",
                            tarefa=request.form.get("tarefa") or "",
                            prioridade=request.form.get("prioridade") or "Média",
                            status=request.form.get("status") or PR.STATUS_CONCLUIDA,
                            data_registro=request.form.get("data_registro")
                            or PR.data_hoje_iso(),
                            hora_inicio=request.form.get("hora_inicio"),
                            hora_fim=request.form.get("hora_fim"),
                            pausas_min=request.form.get("pausas_min") or 0,
                            tempo_planejado_min=planejado,
                            observacoes=request.form.get("observacoes"),
                            criado_por=username,
                        )
                        con.commit()
                        flash("Registro salvo.", "success")
                except (ValueError, LookupError) as erro:
                    flash(str(erro), "warning")
            q_data = request.form.get("filtro_data") or request.form.get("data_registro")
            q_resp = request.form.get("filtro_responsavel") or "Todos"
            return redirect(
                url_for(
                    "produtividade_lista",
                    data=q_data,
                    responsavel=q_resp,
                )
            )

        data_filtro = (request.args.get("data") or PR.data_hoje_iso()).strip()[:10]
        # OS FILTROS E A ORDEM DA LISTA — pedido do oficial em 13/10/2026:
        # «também quero esses filtros e ordenar na produtividade». O PERÍODO
        # (de/até) vale só para a lista; o painel continua sendo o do dia.
        lista = {k: (request.args.get(k) or "").strip() for k in
                 ("data_de", "data_ate", "categoria", "prioridade", "status", "q",
                  "ordem", "inverter")}
        periodo = bool(lista["data_de"] or lista["data_ate"])
        resp_sql, resp_ui = _parse_filtro_responsavel(
            request.args.get("responsavel"),
            role=role,
            user_id=int(user_id) if user_id else None,
        )

        with get_db() as con:
            escreventes = PR.listar_escreventes_ativos(con)
            categorias = PR.listar_categorias(con)
            status_list = PR.listar_status(con)
            prioridades = PR.listar_prioridades(con)
            painel = PR.painel_kpis(
                con,
                data_filtro=data_filtro,
                responsavel_user_id=resp_sql,
            )
            registros = PR.listar_registros(
                con,
                limite=2000 if (periodo or lista["ordem"]) else 120,
                responsavel_user_id=resp_sql,
                data_exata=None if periodo else data_filtro,
                data_de=lista["data_de"] or None,
                data_ate=lista["data_ate"] or None,
                categoria=lista["categoria"] or None,
                prioridade=lista["prioridade"] or None,
                status=lista["status"] or None,
                texto=lista["q"] or None,
                ordem=lista["ordem"] or None,
                inverter=lista["inverter"],
            )
            recentes = []
            if user_id:
                recentes = PR.tarefas_recentes(
                    con, responsavel_user_id=int(user_id), limite=40
                )

        return render_template(
            "produtividade_lista.html",
            registros=registros,
            categorias=categorias,
            status_list=status_list,
            prioridades=prioridades,
            painel=painel,
            escreventes=escreventes,
            tarefas_recentes=recentes,
            user_role=role,
            hoje=PR.data_hoje_iso(),
            filtro_data=data_filtro,
            filtro_responsavel=resp_ui,
            lista=lista,
            periodo=periodo,
            ORDENS=PR.ORDENS_DO_REGISTRO,
            ordem_atual=(lista["ordem"].upper() if lista["ordem"].upper() in PR.ORDENS_DO_REGISTRO
                         else ""),
            defaults={
                "responsavel_user_id": user_id,
                "responsavel_nome": full_name,
                "data_registro": data_filtro,
                "status": PR.STATUS_CONCLUIDA,
                "prioridade": "Média",
                "categoria": PR.CATEGORIA_PADRAO,
            },
        )

    @app.route("/administrativo/produtividade/exportar.csv")
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def produtividade_exportar_csv():
        user = _usuario_sessao(current_user_fn())
        role = (user.get("role") or "USER").upper()
        user_id = user.get("id")
        data_filtro = (request.args.get("data") or PR.data_hoje_iso()).strip()[:10]
        resp_sql, _ = _parse_filtro_responsavel(
            request.args.get("responsavel"),
            role=role,
            user_id=int(user_id) if user_id else None,
        )
        with get_db() as con:
            conteudo = PR.exportar_csv(
                con, data_filtro=data_filtro, responsavel_user_id=resp_sql
            )
        nome = f"produtividade_{data_filtro}.csv"
        return Response(
            "\ufeff" + conteudo,
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{nome}"'},
        )


    @app.route("/administrativo/produtividade/exportar.xlsx")
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def produtividade_exportar_xlsx():
        user = _usuario_sessao(current_user_fn())
        role = (user.get("role") or "USER").upper()
        user_id = user.get("id")
        data_filtro = (request.args.get("data") or PR.data_hoje_iso()).strip()[:10]
        resp_sql, _ = _parse_filtro_responsavel(
            request.args.get("responsavel"),
            role=role,
            user_id=int(user_id) if user_id else None,
        )
        with get_db() as con:
            conteudo = PR.exportar_xlsx(
                con, data_filtro=data_filtro, responsavel_user_id=resp_sql
            )
        nome = f"produtividade_{data_filtro}.xlsx"
        return Response(
            conteudo,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{nome}"'},
        )

    # ----- API rápida (AJAX) -------------------------------------------------

    def _identidade():
        user = _usuario_sessao(current_user_fn())
        if not user or not user.get("id"):
            return None, None, None, None
        uid = int(user["id"])
        username = user.get("username") or ""
        nome = (user.get("full_name") or username or "").strip()
        # Nunca gravar nome de robô como responsável
        if nome.lower().startswith("robo") or username.lower().startswith("robo"):
            nome = username if not username.lower().startswith("robo") else nome
        return uid, nome, username, (user.get("role") or "USER").upper()

    @app.route("/administrativo/produtividade/api/contexto")
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def produtividade_api_contexto():
        uid, nome, username, _role = _identidade()
        if uid is None:
            return _json_erro("Sessão inválida.", 401)
        with get_db() as con:
            cats = PR.listar_categorias(con)
            recentes = PR.tarefas_recentes(con, responsavel_user_id=uid, limite=40)
            ultimo = PR.ultimo_fim_hoje(con, responsavel_user_id=uid)
            crono = PR.cronometro_em_andamento(con, responsavel_user_id=uid)
        return jsonify(
            {
                "ok": True,
                "categorias": cats,
                "tarefas_recentes": recentes,
                "ultimo_fim_hoje": ultimo,
                "agora": PR.hora_agora_hhmm(),
                "responsavel": nome,
                "cronometro": crono,
            }
        )

    @app.route("/administrativo/produtividade/api/lancar", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def produtividade_api_lancar():
        uid, nome, username, _role = _identidade()
        if uid is None:
            return _json_erro("Sessão inválida.", 401)
        categoria = (request.form.get("categoria") or "").strip()
        tarefa = (request.form.get("tarefa") or "").strip()
        dur_raw = request.form.get("duracao_min")
        duracao = None
        if dur_raw is not None and str(dur_raw).strip() != "":
            try:
                duracao = int(dur_raw)
            except (TypeError, ValueError):
                return _json_erro("Duração inválida.")
        hora_inicio = (request.form.get("hora_inicio") or "").strip() or None
        hora_fim = (request.form.get("hora_fim") or "").strip() or None
        with get_db() as con:
            try:
                rid = PR.lancar_rapido(
                    con,
                    responsavel_user_id=uid,
                    responsavel_nome=nome or username,
                    categoria=categoria,
                    tarefa=tarefa,
                    duracao_min=duracao,
                    hora_inicio=hora_inicio,
                    hora_fim=hora_fim,
                    criado_por=username,
                )
                con.commit()
                regs = PR.listar_registros(con, limite=1)
                reg = next((r for r in regs if r["id"] == rid), None)
                if reg is None:
                    rows = banco(con).ler(
                        "SELECT * FROM prod_registros WHERE id = %s", (rid,)
                    )
                    reg = PR._enriquecer_registro(dict(rows[0])) if rows else {"id": rid}
            except ValueError as erro:
                return _json_erro(str(erro))
        return jsonify({"ok": True, "id": rid, "registro": reg})

    @app.route("/administrativo/produtividade/api/cronometro/iniciar", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def produtividade_api_crono_iniciar():
        uid, nome, username, _role = _identidade()
        if uid is None:
            return _json_erro("Sessão inválida.", 401)
        with get_db() as con:
            try:
                rid = PR.iniciar_cronometro(
                    con,
                    responsavel_user_id=uid,
                    responsavel_nome=nome or username,
                    categoria=(request.form.get("categoria") or "").strip(),
                    tarefa=(request.form.get("tarefa") or "").strip(),
                    criado_por=username,
                )
                con.commit()
                crono = PR.cronometro_em_andamento(con, responsavel_user_id=uid)
            except ValueError as erro:
                return _json_erro(str(erro))
        return jsonify({"ok": True, "id": rid, "cronometro": crono})

    @app.route("/administrativo/produtividade/api/cronometro/pausar", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def produtividade_api_crono_pausar():
        uid, nome, username, _role = _identidade()
        if uid is None:
            return _json_erro("Sessão inválida.", 401)
        with get_db() as con:
            try:
                crono = PR.pausar_cronometro(con, responsavel_user_id=uid)
                con.commit()
            except (ValueError, LookupError) as erro:
                return _json_erro(str(erro))
        return jsonify({"ok": True, "cronometro": crono})

    @app.route("/administrativo/produtividade/api/cronometro/retomar", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def produtividade_api_crono_retomar():
        uid, nome, username, _role = _identidade()
        if uid is None:
            return _json_erro("Sessão inválida.", 401)
        with get_db() as con:
            try:
                crono = PR.retomar_cronometro(con, responsavel_user_id=uid)
                con.commit()
            except (ValueError, LookupError) as erro:
                return _json_erro(str(erro))
        return jsonify({"ok": True, "cronometro": crono})

    @app.route("/administrativo/produtividade/api/cronometro/parar", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def produtividade_api_crono_parar():
        uid, nome, username, _role = _identidade()
        if uid is None:
            return _json_erro("Sessão inválida.", 401)
        with get_db() as con:
            try:
                reg = PR.parar_cronometro(con, responsavel_user_id=uid)
                con.commit()
            except (ValueError, LookupError) as erro:
                return _json_erro(str(erro))
        return jsonify({"ok": True, "registro": reg, "cronometro": None,
                        "aviso": reg.get("encerrado_automaticamente")})

    @app.route("/administrativo/produtividade/api/cronometro/status")
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def produtividade_api_crono_status():
        uid, nome, username, _role = _identidade()
        if uid is None:
            return _json_erro("Sessão inválida.", 401)
        with get_db() as con:
            crono = PR.cronometro_em_andamento(con, responsavel_user_id=uid)
            avisos = PR.encerrados_sem_ciencia(con, responsavel_user_id=uid)
        return jsonify({"ok": True, "cronometro": crono, "encerrados_sem_ciencia": avisos})

    @app.route("/administrativo/produtividade/api/cronometro/ciencia", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def produtividade_api_crono_ciencia():
        uid, nome, username, _role = _identidade()
        if uid is None:
            return _json_erro("Sessão inválida.", 401)
        with get_db() as con:
            n = PR.dar_ciencia(con, responsavel_user_id=uid)
            con.commit()
        return jsonify({"ok": True, "ciencia": n})

    # O aviso das 14h15 e o encerramento das 14h30 (ordem do oficial,
    # 11/10/2026). O status acima só LÊ («GET não abre transação de escrita»);
    # quem fecha é o POST abaixo, que a tela chama quando o status diz ENCERRAR.
    @app.route("/administrativo/produtividade/api/cronometro/confirmar", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def produtividade_api_crono_confirmar():
        uid, nome, username, _role = _identidade()
        if uid is None:
            return _json_erro("Sessão inválida.", 401)
        with get_db() as con:
            try:
                crono = PR.confirmar_cronometro(con, responsavel_user_id=uid)
                con.commit()
            except (ValueError, LookupError) as erro:
                con.commit()  # o encerramento automático que ela fez fica gravado
                return _json_erro(str(erro))
        return jsonify({"ok": True, "cronometro": crono})

    @app.route("/administrativo/produtividade/api/cronometro/encerrar-esquecidos",
               methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def produtividade_api_crono_encerrar_esquecidos():
        uid, nome, username, _role = _identidade()
        if uid is None:
            return _json_erro("Sessão inválida.", 401)
        with get_db() as con:
            fechados = PR.encerrar_esquecidos(con, responsavel_user_id=uid)
            con.commit()
            crono = PR.cronometro_em_andamento(con, responsavel_user_id=uid)
            avisos = PR.encerrados_sem_ciencia(con, responsavel_user_id=uid)
        return jsonify({"ok": True, "fechados": fechados, "cronometro": crono,
                        "encerrados_sem_ciencia": avisos})
