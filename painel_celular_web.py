"""AS TELAS DO PAINEL NO CELULAR — só do oficial titular (26/10/2026).

    «painel do gestor no celular, só com números agregados» — pedido de 26/10/2026
    «apenas eu» — decisão do oficial, 26/10/2026

DUAS TELAS
    /painel            os números do dia, da semana e do mês, numa coluna só,
                       para tela de celular. Sem nome, sem CPF, sem teor: é o
                       dicionário de `painel_numeros`, e nada além dele.
    /painel/retrato    o titular do painel, o endereço da VPS, a chave que
                       assina, a prévia do que sairia e o botão «enviar agora».

SÓ O TITULAR — E NÃO UM PAPEL
    A primeira versão deste PR criou um quinto papel, «PAINEL», para quem só
    devia ver agregados, e deixava o painel aberto a ADMIN, MANAGER e AUDITOR.
    O oficial respondeu «apenas eu». Um papel é coisa que se distribui; o que
    ele pediu é UM nome. Por isso o papel saiu (app.ROLES, `database` e
    `dois_fatores_web` voltaram aos quatro papéis do `main`) e no lugar dele
    entrou o TITULAR do painel (`painel_retrato.titular`): um único usuário
    ADMIN, guardado em configuração, escolhido na tela com auditoria. Só ele
    abre /painel, só ele configura e envia o retrato. Outro ADMIN, o gerente
    e o auditor recebem 403 — e o papel PAINEL, que deixou de existir, é
    recusado por `database.create_user` como «Perfil inválido».

    Sem titular escolhido, o ADMIN que abre o painel cai na tela do retrato,
    onde o escolhe. Escolhido, só o próprio titular passa o painel a outro
    ADMIN (a regra está em `painel_retrato.definir_titular`).
"""
from __future__ import annotations

import json

from flask import (abort, flash, make_response, redirect, render_template,
                   request, url_for)

import painel_numeros as PN
import painel_retrato as PR

#: Quem passa pela porta da rota. A trava fina — só o titular — é a de
#: `painel_retrato.e_o_titular`, conferida dentro de cada rota.
QUEM_VE = ("ADMIN",)

#: Quem age pela tela (os dois campos que `db.log` não tem coluna própria
#: vão no detalhe da auditoria, como no backup automático).
AGENTE_DA_TELA = "pessoa — tela /painel/retrato"


def registrar_rotas(app, db, login_required, roles_required, audit):
    pasta = app.config["DATA_DIR"]

    def _sem_cache(resposta):
        resposta = make_response(resposta)
        resposta.headers["Cache-Control"] = "no-store"
        return resposta

    def _quem():
        uid = app.extensions["usuario_id"]()
        return db.get_user(uid) if uid else None

    def _auditar(acao, detalhes, quem):
        audit(acao, "PAINEL", None,
              {**detalhes, "agente": AGENTE_DA_TELA,
               "a_mando_de": (quem["username"] if quem else None)})

    @app.route("/painel")
    @login_required
    @roles_required(*QUEM_VE)
    def painel_celular():
        quem = _quem()
        if not PR.e_o_titular(db, quem):
            if PR.titular(db) is None:
                flash("O painel ainda não tem titular. Escolha quem é o "
                      "titular do painel.", "warning")
                return redirect(url_for("painel_retrato_tela"))
            abort(403)
        periodo = request.args.get("p", "dia")
        if periodo not in PN.PERIODOS:
            periodo = "dia"
        numeros = PN.montar(db)
        return _sem_cache(render_template(
            "painel_celular.html", n=numeros, periodo=periodo,
            p=numeros["periodos"][periodo], periodos=PN.PERIODOS,
            rotulos=PN.ROTULO_DO_PERIODO, atribuicoes=PN.ATRIBUICOES,
            outras=PN.OUTRAS, reais=PN.reais))

    @app.route("/painel/retrato", methods=["GET", "POST"])
    @login_required
    @roles_required(*QUEM_VE)
    def painel_retrato_tela():
        quem = _quem()
        dono = PR.titular(db)
        sou_eu = PR.e_o_titular(db, quem)
        if request.method == "POST":
            acao = request.form.get("acao", "")
            # Escolher o titular: qualquer ADMIN enquanto não há titular; o
            # próprio titular depois. Toda outra ação é só do titular.
            if acao != "titular" and not sou_eu:
                abort(403)
            try:
                if acao == "titular":
                    antes = dono
                    novo = PR.definir_titular(
                        db, novo_id=int(request.form.get("usuario_id") or 0),
                        quem=quem)
                    _auditar("PAINEL_TITULAR_ESCOLHIDO",
                             {"antes": (antes["username"] if antes else None),
                              "titular": novo["username"]}, quem)
                    flash(f"Titular do painel: {novo['full_name']}.", "success")
                elif acao == "salvar":
                    PR.salvar_configuracao(
                        db, url=request.form.get("url", ""),
                        ligado=request.form.get("ligado") == "1")
                    _auditar("PAINEL_RETRATO_CONFIGURADO",
                             {"url": request.form.get("url", "").strip()[:200],
                              "ligado": request.form.get("ligado") == "1"}, quem)
                    flash("Configuração do retrato guardada.", "success")
                elif acao == "gerar_chave":
                    publica = PR.gerar_chave(pasta, trocar=request.form.get("trocar") == "1")
                    _auditar("PAINEL_RETRATO_CHAVE_GERADA",
                             {"impressao": PR.impressao(publica)}, quem)
                    flash("Chave gerada. Cole a chave pública na VPS antes de "
                          "enviar o primeiro retrato.", "success")
                elif acao == "enviar":
                    feito = PR.empurrar(db, pasta, forcar=True)
                    _auditar("PAINEL_RETRATO_ENVIADO",
                             {k: feito.get(k) for k in ("ok", "status", "bytes")}, quem)
                    if feito.get("ok"):
                        flash("Retrato enviado à VPS.", "success")
                    else:
                        flash("O retrato não foi aceito: "
                              + str(feito.get("motivo") or ""), "danger")
                else:
                    abort(400)
            except (PR.RetratoError, ValueError) as erro:
                flash(str(erro), "danger")
            return redirect(url_for("painel_retrato_tela"))
        previa = None
        publica = None
        if sou_eu:
            if request.args.get("ver") == "previa":
                numeros = PN.montar(db)
                try:
                    PR.conferir_que_e_so_agregado(numeros)
                    previa = json.dumps(numeros, ensure_ascii=False, indent=2,
                                        sort_keys=True)
                except PR.RetratoError as erro:
                    flash(str(erro), "danger")
            publica = PR.chave_publica(pasta)
        return _sem_cache(render_template(
            "painel_retrato.html", titular=dono, sou_eu=sou_eu,
            pode_escolher=(dono is None or sou_eu),
            candidatos=PR.candidatos_a_titular(db),
            conf=PR.configuracao(db) if sou_eu else None, publica=publica,
            impressao=PR.impressao(publica), previa=previa))
