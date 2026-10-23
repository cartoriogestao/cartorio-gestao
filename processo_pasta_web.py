"""As rotas da pasta do processo e do rascunho que vira processo (12/10/2026).

    «no caso, por exemplo, de salvar um rascunho pra continuar depois em um ato
     de rcpn, acho que vale ter a opcao de virar processo se nao for pra
     terminar no mesmo dia»                          — o oficial, 12/10/2026

O que se resolve na hora (firma, autenticação, nascimento, certidão) NÃO vira
processo — decisão dele no mesmo dia. O rascunho que fica para outro dia pode
virar: ele ganha responsável, prazo e lugar na lista, em vez de ficar esquecido
na tela de rascunhos.
"""
from __future__ import annotations

from datetime import date, timedelta

from flask import flash, redirect, request, url_for

from bd_nativo import banco
import processo_pasta as PASTA
import rascunho_de_tela as RASC
from seguranca_web import destino_interno  # M1/B3 (LX11): o «volte para» só leva a caminho desta casa

QUEM = ("ADMIN", "MANAGER", "USER")


def proximo_dia_util(hoje: date) -> date:
    """O prazo padrão do rascunho que não termina hoje: o próximo dia útil
    (sábado e domingo pulam; feriado o escrevente ajusta na tarefa)."""
    d = hoje + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_id = app.extensions["usuario_id"]
    usuario_nome = app.extensions["usuario_nome"]

    with db.connect() as con:
        PASTA.init_schema(con)

    @app.route("/tarefas/<int:task_id>/pasta/vincular", methods=["POST"])
    @roles_required(*QUEM)
    def processo_pasta_vincular(task_id: int):
        tabela = (request.form.get("tabela") or "").strip()
        try:
            with db.transaction() as con:
                PASTA.vincular(con, task_id, tabela, request.form.get("referencia") or "",
                               agora=db.now(), por=usuario_id())
        except ValueError as erro:
            flash(str(erro), "danger")
        else:
            audit("PROCESSO_PASTA_VINCULOU", "TASK", task_id, {"tabela": tabela})
            flash("A peça entrou na pasta do processo.", "success")
        return redirect(url_for("task_detail", task_id=task_id) + "#pasta")

    @app.route("/tarefas/<int:task_id>/pasta/<int:vinculo_id>/tirar", methods=["POST"])
    @roles_required(*QUEM)
    def processo_pasta_tirar(task_id: int, vinculo_id: int):
        try:
            with db.transaction() as con:
                PASTA.desvincular(con, task_id, vinculo_id, agora=db.now(), por=usuario_id())
        except ValueError as erro:
            flash(str(erro), "danger")
        else:
            audit("PROCESSO_PASTA_TIROU", "TASK", task_id, {"vinculo_id": vinculo_id})
            flash("A peça saiu da pasta. Ela continua onde sempre esteve.", "info")
        return redirect(url_for("task_detail", task_id=task_id) + "#pasta")

    @app.route("/tarefas/<int:task_id>/pasta/<int:vinculo_id>/ato-lavrado", methods=["POST"])
    @roles_required(*QUEM)
    def processo_rascunho_ato_lavrado(task_id: int, vinculo_id: int):
        try:
            with db.transaction() as con:
                PASTA.ato_lavrado_do_rascunho(con, task_id, vinculo_id,
                                              apagar_rascunho=bool(request.form.get("apagar_rascunho")),
                                              agora=db.now(), por=usuario_id())
        except ValueError as erro:
            flash(str(erro), "danger")
        else:
            audit("PROCESSO_RASCUNHO_LAVRADO", "TASK", task_id, {"vinculo_id": vinculo_id})
            flash("Processo concluído: o ato do rascunho foi lavrado.", "success")
        return redirect(url_for("task_detail", task_id=task_id))

    def _abrir_processo_do_rascunho(rascunho_id: int, prazo: date) -> int:
        with db.connect() as con:
            r = RASC.ler(con, rascunho_id)
        uid = usuario_id()
        tid = db.create_task({
            "source_type": "RASCUNHO", "source_ref": f"RASCUNHO:{rascunho_id}",
            "title": f"Continuar o ato: {r['titulo']}",
            "description": (f"Rascunho #{rascunho_id} salvo por {r.get('criado_por') or usuario_nome()} "
                            "para terminar depois — ele não é ato: não tomou número nem selo. "
                            "Abra o rascunho pela pasta do processo, termine e lavre; ao lavrar, "
                            "conclua este processo com o ato como prova."),
            "priority": "MEDIA", "assigned_user_id": uid, "start_date": db.now()[:10],
            "due_date": prazo.isoformat(),
        }, user_id=uid)
        with db.transaction() as con:
            if not banco(con).um("SELECT 1 FROM pr_vinculos WHERE task_id = %s AND tabela = 'rascunhos_de_tela' "
                                 "AND item_id = %s", (tid, rascunho_id)):
                PASTA.vincular(con, tid, "rascunhos_de_tela", str(rascunho_id), agora=db.now(), por=uid)
        audit("PROCESSO_DO_RASCUNHO", "TASK", tid, {"rascunho_id": rascunho_id})
        return tid

    def _prazo_do_form() -> date:
        bruto = (request.form.get("_prazo") or "").strip()
        try:
            return date.fromisoformat(bruto) if bruto else proximo_dia_util(date.today())
        except ValueError:
            return proximo_dia_util(date.today())

    @app.route("/rascunhos/<int:rascunho_id>/processo", methods=["POST"])
    @roles_required(*QUEM)
    def rascunho_virar_processo(rascunho_id: int):
        try:
            tid = _abrir_processo_do_rascunho(rascunho_id, _prazo_do_form())
        except ValueError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rascunhos"))
        flash("O rascunho virou processo, com você de responsável e prazo marcado. "
              "Ele continua não sendo ato.", "success")
        return redirect(url_for("task_detail", task_id=tid))

    @app.route("/rascunhos/salvar-e-abrir-processo", methods=["POST"])
    @roles_required(*QUEM)
    def rascunho_salvar_e_abrir_processo():
        """O botão «não termina hoje» da tela do ato: guarda o rascunho (como o
        botão de sempre) e abre o processo dele, numa ação só."""
        tela = (request.form.get("_tela") or "").strip()
        volta = destino_interno((request.form.get("_volta") or "").strip(), "")
        rid = request.form.get("_rascunho_id")
        dados = {k: v for k, v in request.form.items() if not k.startswith("_")}
        try:
            with db.transaction() as con:
                r = RASC.salvar(con, tela=tela, dados=dados,
                                titulo=(request.form.get("_titulo") or "").strip() or (dados.get("nome") or tela),
                                chave=(request.form.get("_chave") or "").strip(), agora=db.now(),
                                por=usuario_nome(), rascunho_id=int(rid) if rid else None)
            tid = _abrir_processo_do_rascunho(r["id"], _prazo_do_form())
        except ValueError as erro:
            flash(str(erro), "danger")
            return redirect(volta if volta.startswith("/") else url_for("rascunhos"))
        flash("Rascunho guardado e processo aberto: o ato fica para terminar no prazo marcado. "
              "Ele não é ato — não tomou número nem selo.", "success")
        return redirect(url_for("task_detail", task_id=tid))

    # ------------------------------------------------ o tipo do processo
    # O roteiro (lista de documentos, passos, marcação e aprovação) saiu em
    # 12/10/2026, por ordem do oficial: «não precisa de roteiro». Ficou o tipo.
    import processo_especies as ESP

    with db.connect() as con:
        ESP.init_schema(con)

    @app.route("/tarefas/<int:task_id>/especie", methods=["POST"])
    @roles_required(*QUEM)
    def processo_definir_especie(task_id: int):
        especie = (request.form.get("especie") or "").strip()
        try:
            with db.transaction() as con:
                ESP.definir(con, task_id, especie, agora=db.now(), por=usuario_id())
        except ValueError as erro:
            flash(str(erro), "danger")
        else:
            audit("PROCESSO_ESPECIE", "TASK", task_id, {"especie": especie})
        return redirect(url_for("task_detail", task_id=task_id) + "#tipo")
