# -*- coding: utf-8 -*-
"""A tela das configurações que cobram a equipe — ver `config_de_cobranca`.

UMA TELA PARA AS DUAS COISAS: alterar (só o oficial, com afirmação expressa)
e conferir o histórico de cada chave — quem, quando, de quê para quê e a
mando de quem. Fica em Configurações, e não na tela das afirmações do
Protesto: estas chaves são da casa inteira (caixa, produtividade, RI, RCPN,
gratuidade), e a afirmação expressa de cada alteração aparece lá também,
regra `CONFIG_DE_COBRANCA`, pelo contrato comum.

QUEM ENTRA
    - a tela (GET): ADMIN e MANAGER. O MANAGER vê os valores e a frase «peça
      ao oficial»; o histórico é só do ADMIN.
    - a alteração (POST): qualquer login chega — e é o domínio quem recusa,
      com a frase e com a TENTATIVA gravada. Um `roles_required` aqui
      devolveria um 403 calado, e a tentativa de quem é cobrado é justamente
      o que o oficial quer ver.
    - o robô não chega a nenhuma das duas (fora de `rotas_do_robo`); o
      `before_request` chama `robo_barrado` antes do 403, e a tentativa dele
      também fica gravada.
"""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for

import config_de_cobranca as CC
from bd_nativo import ERROS_DO_BANCO

ENDPOINT_DA_ALTERACAO = "configuracoes_cobranca_alterar"
PAPEIS_DA_TELA = ("ADMIN", "MANAGER")


def robo_barrado(db, quem, pedido) -> str | None:
    """O robô bateu na rota que altera: grava a TENTATIVA e devolve a frase
    do 403. Para qualquer outra rota, None (o 403 de sempre). ESCREVE.

    Gravar não pode virar erro de outro tipo: se a auditoria falhar, o 403
    sai do mesmo jeito — a recusa é o que importa."""
    if pedido.endpoint != ENDPOINT_DA_ALTERACAO or pedido.method != "POST":
        return None
    try:
        with db.transaction() as con:
            CC.registrar_recusa(con, chave=pedido.form.get("chave"),
                                valor=pedido.form.get("valor"),
                                usuario_id=quem["id"], motivo=CC.MOTIVO_ROBO,
                                mensagem=CC.MENSAGEM_DO_ROBO, agora=db.now(),
                                ip=pedido.remote_addr, via="robô, pela rota")
    except (ValueError, *ERROS_DO_BANCO):
        pass
    return CC.MENSAGEM_DO_ROBO


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_id = app.extensions["usuario_id"]
    usuario_papel = app.extensions["usuario_papel"]

    @app.route("/configuracoes/cobranca")
    @login_required
    @roles_required(*PAPEIS_DA_TELA)
    def configuracoes_cobranca():
        """O quadro, as duas formas de alterar e o histórico. SÓ LÊ."""
        e_admin = usuario_papel() == "ADMIN"
        with db.connect() as con:
            quadro = CC.quadro(con)
            historico = (CC.historico(con, hoje=db.now(), dias=request.args.get("dias"))
                         if e_admin else None)
        return render_template("config_de_cobranca.html", q=quadro, hist=historico,
                               e_admin=e_admin)

    @app.route("/configuracoes/cobranca/alterar", methods=["POST"])
    @login_required
    def configuracoes_cobranca_alterar():
        """Altera uma chave de cobrança. ESCREVE — ou recusa e grava a tentativa."""
        chave = request.form.get("chave") or ""
        valor = request.form.get("valor")
        uid = usuario_id()
        agora = db.now()
        voltar = redirect(url_for("configuracoes_cobranca")
                          if usuario_papel() in PAPEIS_DA_TELA else url_for("dashboard"))
        try:
            with db.transaction() as con:
                feito = CC.alterar(con, chave=chave, valor=valor, usuario_id=uid,
                                   afirmo=request.form.get("afirmo") == "1",
                                   afirmacao=request.form.get("afirmacao"),
                                   agora=agora, ip=request.remote_addr)
        except CC.Recusa as recusa:
            with db.transaction() as con:
                CC.registrar_recusa(con, chave=chave, valor=valor, usuario_id=uid,
                                    motivo=recusa.motivo, mensagem=str(recusa),
                                    agora=agora, ip=request.remote_addr)
            flash(str(recusa), "danger")
            return voltar
        except CC.ValorInvalido as erro:
            flash(str(erro), "danger")
            return voltar
        if not feito["mudou"]:
            flash("Nada mudou: o valor informado já é o que está gravado.", "info")
        else:
            flash(f"Gravado: {feito['chave']} passou de "
                  f"{feito['de'] if feito['de'] is not None else 'o padrão'} para "
                  f"{feito['para'] or 'vazio'}. A afirmação ficou na auditoria e o "
                  f"oficial recebeu a tarefa.", "success")
        return voltar
