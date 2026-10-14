"""A tela «Processos» — fase 3 do módulo único (12/10/2026).

Uma lista só para o que a casa tem a cumprir (as antigas tarefas) e, no alto, o
que chegou pelo malote e ainda espera decisão: virar processo ou receber «só
ciência». As telas antigas de tarefas e expedientes continuam abrindo — são
vistas da mesma coisa, e há link para elas.
"""
from __future__ import annotations

from datetime import date

from flask import flash, redirect, render_template, request, url_for

import processo_especies as ESP
import processos as PR
import tarefa_processo as TP

QUEM = ("ADMIN", "MANAGER", "USER")


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_id = app.extensions["usuario_id"]

    @app.route("/processos")
    @roles_required(*QUEM, "AUDITOR")
    def processos_lista():
        vista = request.args.get("vista") or "ABERTOS"
        if vista not in PR.VISTAS:
            vista = "ABERTOS"
        origem = (request.args.get("origem") or "").strip()
        q = (request.args.get("q") or "").strip()
        setor = (request.args.get("setor") or "").strip()
        filtros = {k: (request.args.get(k) or "").strip() for k in PR.FILTROS
                   if k not in ("origem", "q", "setor")}
        uid = usuario_id()
        # O CONTROLE E A FISCALIZAÇÃO (12/10/2026): o quadro por responsável e por
        # setor é do oficial e do gerente; os filtros servem a todos.
        u = app.extensions["current_user"]()
        fiscaliza = bool(u and u["role"] in ("ADMIN", "MANAGER"))
        with db.connect() as con:
            linhas = PR.listar(con, vista=vista, usuario_id=uid, origem=origem, q=q, setor=setor, **filtros)
            contagem = PR.contagem(con, uid)
            entradas = PR.entradas_sem_processo(con)
            fora = TP.tarefas_fora_do_vocabulario(con)
            quadro = PR.quadro_de_fiscalizacao(con) if fiscaliza else None
        return render_template("processos.html", linhas=linhas, vista=vista, vistas=PR.VISTAS,
                               contagem=contagem, entradas=entradas, origem=origem, origens=PR.ORIGENS,
                               q=q, catalogo=ESP.CATALOGO, hoje=date.today().isoformat(),
                               fora_do_vocabulario=fora, quadro=quadro, fiscaliza=fiscaliza,
                               filtros=filtros, PRAZOS=PR.PRAZOS, PARADOS=PR.PARADOS, ORDENS=PR.ORDENS,
                               ordem_atual=_ordem_atual(filtros.get("ordem")),
                               SEM_RESPONSAVEL=PR.SEM_RESPONSAVEL, TIPOS_ANDAMENTO=TP.TIPOS_ANDAMENTO,
                               setor=setor,
                               setores=_lista("sectors", []), vias=_lista("sources", ["Outro"]),
                               categorias=_lista("categories", ["Outros"]),
                               usuarios=db.list_users(active_only=True))

    def _ordem_atual(ordem: str | None) -> str:
        """A ordem que a lista está usando, com os apelidos antigos resolvidos —
        é ela que acende a seta no cabeçalho."""
        import tarefa_ordem as TO
        chave = TO.APELIDOS.get((ordem or "").upper(), (ordem or "").upper())
        return chave if chave in PR.ORDENS else TO.PADRAO

    def _lista(chave: str, padrao: list[str]) -> list[str]:
        """As listas da Configuração (setores, vias de entrada, classificações) —
        as mesmas que as telas antigas de tarefas e expedientes usavam."""
        import json
        try:
            return json.loads(db.get_setting(chave, "[]") or "[]") or padrao
        except ValueError:
            return padrao

    @app.route("/processos.csv")
    @roles_required("ADMIN", "MANAGER")
    def processos_planilha():
        """A lista com os mesmos filtros da tela, em planilha. Só lê."""
        import csv
        import io
        from flask import Response
        vista = request.args.get("vista") or "ABERTOS"
        filtros = {k: (request.args.get(k) or "").strip() for k in PR.FILTROS}
        with db.connect() as con:
            linhas = PR.listar(con, vista=vista if vista in PR.VISTAS else "ABERTOS", usuario_id=usuario_id(),
                               limite=100000, **filtros)
        saida = io.StringIO()
        w = csv.writer(saida, delimiter=";")
        w.writerow(["processo", "assunto", "origem", "tipo", "setor", "responsável", "substituto", "prioridade",
                    "prazo", "vencido", "situação", "último andamento", "dias parado"])
        for p in linhas:
            w.writerow([p["numero"], p["title"], p["origem"], p["especie_nome"] or "", p["sector"] or "",
                        p["responsavel"] or "", p["substituto"] or "", p["priority"] or "", p["due_date"] or "",
                        "sim" if p["vencido"] else "", p["status"] or "", (p["ultimo_andamento"] or "")[:16],
                        p["dias_parado"] if p["dias_parado"] is not None else ""])
        audit("PROCESSOS_PLANILHA", "TASK", None, {"vista": vista, **{k: v for k, v in filtros.items() if v}})
        return Response("\ufeff" + saida.getvalue(), mimetype="text/csv; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=processos.csv"})

    @app.route("/processos/entrada/<int:expediente_id>/abrir", methods=["POST"])
    @roles_required(*QUEM)
    def processos_abrir_da_entrada(expediente_id: int):
        exp = db.get_expediente(expediente_id)
        if not exp:
            flash("Não achei essa entrada do malote.", "danger")
            return redirect(url_for("processos_lista"))
        uid = usuario_id()
        dados = PR.dados_do_processo_do_expediente(dict(exp))
        if not dados["assigned_user_id"]:
            dados["assigned_user_id"] = uid
        tid = db.create_task(dados, user_id=uid)
        especie = (request.form.get("especie") or "").strip()
        if especie in ESP.CATALOGO:
            with db.transaction() as con:
                ESP.definir(con, tid, especie, agora=db.now(), por=uid)
        audit("PROCESSO_ABERTO_DA_ENTRADA", "TASK", tid, {"expediente_id": expediente_id, "especie": especie})
        flash(f"Processo {PR.numero(db.now(), tid)} aberto a partir de {exp['internal_protocol']}.", "success")
        return redirect(url_for("task_detail", task_id=tid))

    @app.route("/processos/entrada/<int:expediente_id>/ciencia", methods=["POST"])
    @roles_required(*QUEM)
    def processos_so_ciencia(expediente_id: int):
        exp = db.get_expediente(expediente_id)
        if not exp:
            flash("Não achei essa entrada do malote.", "danger")
            return redirect(url_for("processos_lista"))
        nota = (request.form.get("nota") or "").strip()
        db.update_expediente_stage(expediente_id, "ARQUIVADO", usuario_id(),
                                   response_reference=("Só ciência" + (f" — {nota}" if nota else "")))
        audit("EXPEDIENTE_SO_CIENCIA", "EXPEDIENTE", expediente_id, {"nota": nota})
        flash(f"{exp['internal_protocol']}: ciência registrada; não vira processo.", "info")
        return redirect(url_for("processos_lista"))
