"""A tela do código de dois fatores do robô do malote (29/10/2026).

O malote pede o código só quando quer (o oficial: «so me peca a autenticacao a
primeira vez»). Quando pede, a rodada MALOTE_CIENCIA_DIARIA termina em AVISO e
espera; aqui o oficial digita o código que recebeu, a tela o GRAVA NO COFRE
(`malote_tjma_codigo`) e pede uma rodada. Quem entra no malote é o despachante,
fora do servidor — a tela não fala com o malote e não lê o cofre de volta
(`automacao_cofre.ler` recusa dentro de requisição web).

O código não vai à auditoria nem ao log: a auditoria diz que um código foi
informado, e por quem. O robô apaga o código do cofre assim que o usa, e não
usa código com mais de 15 minutos.
"""
from __future__ import annotations

import re

from flask import flash, redirect, render_template, request, url_for

import automacao as AU
import automacao_cofre as COFRE
import malote_robo as MR

PROCESSO = MR.CATALOGO[0]["codigo"]
_CODIGO_VALIDO = re.compile(r"^[A-Za-z0-9]{4,12}$")


def registrar_rotas(app, db, login_required, roles_required, audit):
    usuario_nome = app.extensions["usuario_nome"]

    def _pasta():
        from centrais_cred import pasta_de_dados
        return pasta_de_dados()

    @app.route("/automacao/malote/codigo", methods=["GET", "POST"])
    @roles_required("ADMIN")
    def malote_robo_codigo():
        caminho = COFRE.caminho_do_cofre(_pasta())
        with db.connect() as con:
            processo = AU.por_codigo(con, PROCESSO)
            ultima = (AU.execucoes(con, processo["id"], limite=1) or [None])[0] if processo else None
        if request.method == "POST":
            codigo = (request.form.get("codigo") or "").strip().replace(" ", "")
            if not _CODIGO_VALIDO.match(codigo):
                flash("O código tem de ter de 4 a 12 letras ou números, como chegou do malote.", "danger")
                return redirect(url_for("malote_robo_codigo"))
            if processo is None:
                flash("O processo do robô do malote ainda não está no cadastro da automação.", "danger")
                return redirect(url_for("malote_robo_codigo"))
            try:
                COFRE.gravar(MR.CODIGO, {"codigo": codigo}, tipo=COFRE.TOKEN, por=usuario_nome(),
                             caminho=caminho)
            except COFRE.CofreError as erro:
                flash(f"O código não foi guardado: {erro}", "danger")
                return redirect(url_for("malote_robo_codigo"))
            with db.transaction() as con:
                AU.pedir_rodada(con, processo["id"], usuario=usuario_nome())
            audit("MALOTE_ROBO_CODIGO_INFORMADO", "au_processos", processo["id"],
                  {"codigo_do_processo": PROCESSO})
            flash("Código guardado no cofre. O robô do malote roda no próximo minuto e usa o código "
                  "(ele vale 15 minutos). Recarregue o processo para ver o resultado.", "success")
            return redirect(url_for("automacao_processo", processo_id=processo["id"]))
        esperando = bool(ultima and "código de dois fatores" in (ultima.get("erro") or "")
                         + (ultima.get("relato") or ""))
        return render_template("malote_robo_codigo.html", processo=processo, ultima=ultima,
                               esperando=esperando, cofre=COFRE.estado(caminho=caminho),
                               credencial=COFRE.tem(MR.CREDENCIAL, caminho=caminho),
                               nome_da_credencial=MR.CREDENCIAL)
