# -*- coding: utf-8 -*-
"""AS TELAS DO PAINEL DE SENHAS (26/10/2026) — a TV da recepção, o papel da
senha, o guichê, a ligação ao protocolo, o relatório do período e o quadro do
painel do gestor. O domínio mora em `senhas.py`; aqui só se ligam os fios.

A TV NÃO ENTRA COM LOGIN, E POR QUÊ
    A sessão da casa cai por inatividade e tem prazo absoluto
    (`prazo_absoluto_horas`): a TV da recepção pediria senha todo dia, e um
    computador de recepção logado com usuário de verdade deixaria o sistema
    inteiro aberto a quem passa. Um papel novo «só-leitura» teria de entrar nas
    réguas de papel da casa inteira, e continuaria sujeito ao prazo.
    A saída é a CHAVE DO PAINEL: um endereço com 256 bits aleatórios, gerado
    pelo ADMIN, guardado no cofre (`senhas.cred`, fora do banco) e trocado
    quando ele quiser — trocar desliga a TV antiga na hora. O que a chave abre
    é só senha e guichê (`senhas.estado_do_painel` nem lê outra coluna); chave
    errada responde 404, como endereço que não existe.
"""
from __future__ import annotations

import csv
import io
from datetime import date, timedelta

from flask import Response, abort, flash, jsonify, redirect, render_template, request, url_for

import cofre_cred as COFRE
import senhas as SEN
from seguranca_web import PRATICA, numero_digitado

#: O nome do segredo dentro de `senhas.cred`.
CHAVE_DA_TV = "chave_tv"

#: Quem vê o relatório do período: os nomes de quem atendeu estão nele.
QUEM_VE_O_RELATORIO = ("ADMIN", "MANAGER", "AUDITOR")

#: Teto do período do relatório, em dias — a conta é em Python, linha a linha.
PERIODO_MAIS_LONGO = 366


def _data(texto, padrao: str) -> str:
    try:
        return date.fromisoformat(str(texto or "").strip()).isoformat()
    except ValueError:
        return padrao


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    """Pendura as telas do painel de senhas no app já construído."""

    usuario_id = app.extensions["usuario_id"]

    def _hoje() -> str:
        return date.today().isoformat()

    def _chave_guardada() -> str:
        with db.connect() as con:
            return COFRE.ler_segredo(con, COFRE.SENHAS, CHAVE_DA_TV)

    # ------------------------------------------------------------ o balcão

    @app.route("/atendimento/guiche", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def senhas_guiche():
        """Grava o guichê (ou a mesa) de quem está chamando."""
        try:
            with db.transaction() as con:
                guiche = SEN.gravar_guiche(con, usuario_id(), request.form.get("guiche"),
                                           agora=db.now())
        except SEN.SenhaError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("service_queue"))
        audit("SENHA_GUICHE", "USER", usuario_id(), {"guiche": guiche})
        flash(f"Seu guichê agora é «{guiche}». É ele que aparece na TV ao chamar.", "success")
        return redirect(url_for("service_queue"))

    @app.route("/atendimento/chamar-proxima", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def senhas_chamar_proxima():
        """Chama a próxima da fila (preferencial e normal alternadas)."""
        try:
            with db.transaction() as con:
                feito = SEN.chamar_proxima(con, user_id=usuario_id(), agora=db.now(),
                                           dia=_hoje())
        except SEN.SenhaError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("service_queue"))
        if not feito:
            flash("Não há senha aguardando.", "info")
            return redirect(url_for("service_queue"))
        audit("SERVICE_TICKET_ACTION", "TICKET", feito["id"], {"action": "call_next"})
        flash(f"Senha {feito['senha']} chamada para o guichê {feito['guiche']}.", "success")
        return redirect(url_for("service_queue"))

    @app.route("/atendimento/<int:ticket_id>/imprimir")
    @login_required
    def senhas_imprimir(ticket_id: int):
        """O papel da senha, para impressora térmica de 80 mm pelo navegador."""
        with db.connect() as con:
            t = SEN.senha(con, ticket_id)
            if not t:
                abort(404)
            frente = SEN.a_frente(con, t)
        return render_template("senhas_impressao.html", t=t, frente=frente,
                               nome_da_casa=db.get_setting("unit_name", "") or "")

    @app.route("/atendimento/<int:ticket_id>/protocolo", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def senhas_protocolo(ticket_id: int):
        """Liga (ou desliga) a senha ao protocolo geral do balcão."""
        acao = (request.form.get("acao") or "ligar").strip()
        try:
            with db.transaction() as con:
                if acao == "desligar":
                    SEN.desligar_protocolo(con, ticket_id)
                    feito = None
                else:
                    feito = SEN.ligar_protocolo(con, ticket_id, request.form.get("protocolo"),
                                                user_id=usuario_id(), agora=db.now())
        except SEN.SenhaError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("service_queue"))
        audit("SENHA_PROTOCOLO", "TICKET", ticket_id,
              {"acao": acao, "protocolo": feito["numero"] if feito else None})
        flash("Ligação ao protocolo desfeita." if feito is None else
              f"Senha ligada ao protocolo {feito['numero']}.", "success")
        return redirect(url_for("service_queue"))

    # ------------------------------------------------------------ o relatório

    def _periodo():
        hoje = _hoje()
        inicio = _data(request.args.get("de"), (date.today() - timedelta(days=29)).isoformat())
        fim = _data(request.args.get("ate"), hoje)
        if fim < inicio:
            inicio, fim = fim, inicio
        if (date.fromisoformat(fim) - date.fromisoformat(inicio)).days > PERIODO_MAIS_LONGO:
            inicio = (date.fromisoformat(fim) - timedelta(days=PERIODO_MAIS_LONGO)).isoformat()
            flash(f"O período foi limitado a {PERIODO_MAIS_LONGO} dias.", "warning")
        atendente = numero_digitado(request.args.get("atendente"))
        return inicio, fim, atendente

    @app.route("/atendimento/relatorio")
    @login_required
    @roles_required(*QUEM_VE_O_RELATORIO)
    def senhas_relatorio():
        """Espera, atendimento e desistências do período. Só LÊ."""
        inicio, fim, atendente = _periodo()
        with db.connect() as con:
            m = SEN.metricas(con, inicio, fim, hoje=_hoje(), atendente_id=atendente)
            linhas = SEN.historico(con, inicio, fim, atendente_id=atendente)
        return render_template("senhas_relatorio.html", m=m, linhas=linhas[-300:],
                               total_de_linhas=len(linhas), atendente=atendente,
                               atendentes=db.list_users(active_only=False),
                               minutos=SEN.minutos)

    @app.route("/atendimento/relatorio.csv")
    @login_required
    @roles_required(*QUEM_VE_O_RELATORIO)
    def senhas_relatorio_csv():
        """O histórico do período em CSV (separador «;», como os outros da casa)."""
        inicio, fim, atendente = _periodo()
        with db.connect() as con:
            linhas = SEN.historico(con, inicio, fim, atendente_id=atendente)
        saida = io.StringIO()
        w = csv.writer(saida, delimiter=";")
        w.writerow(["Data", "Senha", "Tipo", "Prioridade", "Situação", "Chegada", "Chamada",
                    "Chamadas", "Guichê", "Início", "Fim", "Espera (min)",
                    "Atendimento (min)", "Atendente", "Protocolo"])
        for r in linhas:
            w.writerow([r["ticket_date"], r["senha"], r.get("service_type") or "Geral",
                        "Preferencial" if r.get("priority") else "Normal", r["situacao"],
                        r.get("created_at") or "", r.get("called_at") or "",
                        r.get("chamadas") or 0, r.get("guiche") or "",
                        r.get("started_at") or "", r.get("finished_at") or "",
                        "" if r["espera_seg"] is None else f"{r['espera_seg'] / 60:.1f}".replace(".", ","),
                        "" if r["atendimento_seg"] is None else f"{r['atendimento_seg'] / 60:.1f}".replace(".", ","),
                        r.get("attendant_name") or "", r.get("protocolo_numero") or ""])
        audit("SENHAS_RELATORIO_EXPORTADO", "TICKET", None, {"de": inicio, "ate": fim})
        return Response("﻿" + saida.getvalue(), mimetype="text/csv; charset=utf-8",
                        headers={"Content-Disposition":
                                 f"attachment; filename=atendimento_{inicio}_{fim}.csv"})

    # ------------------------------------------------------------ a TV

    @app.route("/atendimento/painel-da-tv", methods=["GET", "POST"])
    @login_required
    @roles_required("ADMIN")
    def senhas_painel_config():
        """O endereço da TV (gerar, trocar, desligar) e os tipos de atendimento."""
        if request.method == "POST":
            acao = (request.form.get("acao") or "").strip()
            if acao == "gerar":
                with db.connect() as con:
                    COFRE.gravar_segredo(con, COFRE.SENHAS, CHAVE_DA_TV, SEN.gerar_chave())
                audit("SENHAS_TV_CHAVE_TROCADA", "SETTINGS", None)
                flash("Endereço novo gerado. A TV que usava o endereço anterior parou: "
                      "abra o endereço novo nela.", "success")
            elif acao == "desligar":
                with db.connect() as con:
                    COFRE.gravar_segredo(con, COFRE.SENHAS, CHAVE_DA_TV, "")
                audit("SENHAS_TV_DESLIGADA", "SETTINGS", None)
                flash("Painel da TV desligado. Nenhum endereço abre o painel agora.", "success")
            elif acao == "tipos":
                linhas = [" ".join(l.split())[:60] for l in
                          (request.form.get("tipos") or "").splitlines() if l.strip()]
                db.set_settings({SEN.CHAVE_DOS_TIPOS: "\n".join(linhas)})
                audit("SENHAS_TIPOS", "SETTINGS", None, {"tipos": linhas})
                flash("Tipos de atendimento gravados." if linhas else
                      "Lista vazia: voltaram os tipos de fábrica.", "success")
            return redirect(url_for("senhas_painel_config"))
        chave = _chave_guardada()
        endereco = (request.host_url.rstrip("/") + url_for("senhas_tv", chave=chave)) if chave else ""
        return render_template("senhas_painel_config.html", endereco=endereco,
                               tipos=SEN.tipos_de_atendimento(db.get_setting),
                               tipos_gravados=db.get_setting(SEN.CHAVE_DOS_TIPOS, "") or "",
                               fabrica=SEN.TIPOS_DE_FABRICA)

    def _conferir_chave(chave: str) -> None:
        if not SEN.chave_confere(_chave_guardada(), chave):
            abort(404)

    @app.route("/senhas/tv/<chave>")
    def senhas_tv(chave: str):
        """A TV da recepção — tela cheia, sem login, só senha e guichê."""
        _conferir_chave(chave)
        resposta = app.make_response(render_template(
            "senhas_tv.html", endereco_estado=url_for("senhas_tv_estado", chave=chave)))
        resposta.headers["Cache-Control"] = "no-store"
        resposta.headers["Referrer-Policy"] = "no-referrer"
        return resposta

    @app.route("/senhas/tv/<chave>/estado")
    def senhas_tv_estado(chave: str):
        """O que a TV mostra agora, em JSON. Só senha e guichê."""
        _conferir_chave(chave)
        with db.connect() as con:
            estado = SEN.estado_do_painel(con, _hoje())
        resposta = jsonify(estado)
        resposta.headers["Cache-Control"] = "no-store"
        resposta.headers["Referrer-Policy"] = "no-referrer"
        return resposta

    # ------------------------------------------------------------ o painel do gestor

    @app.context_processor
    def _senhas_no_painel() -> dict:
        """O quadro «Atendimento de hoje» no painel geral — só ADMIN e MANAGER,
        e só no painel, para não ler a fila em toda tela."""
        from flask import session
        try:
            if (request.endpoint or "") != "dashboard" or not session.get("user_id"):
                return {"senhas_no_painel": None}
        except RuntimeError:
            return {"senhas_no_painel": None}
        try:
            with db.connect() as con:
                from bd_nativo import banco
                papel = banco(con).um("SELECT role FROM users WHERE id = %s",
                                      (session.get("user_id"),))
                if not papel or papel["role"] not in ("ADMIN", "MANAGER"):
                    return {"senhas_no_painel": None}
                hoje = _hoje()
                m = SEN.metricas(con, hoje, hoje, hoje=hoje)
        except Exception:  # noqa: BLE001 — quadro do painel não derruba o painel
            return {"senhas_no_painel": None}
        if not m["resumo"]["total"]:
            return {"senhas_no_painel": None}
        return {"senhas_no_painel": {"r": m["resumo"], "minutos": SEN.minutos}}
