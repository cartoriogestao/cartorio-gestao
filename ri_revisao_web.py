"""As telas das notas de revisão do RI.

O domínio — o que é uma nota, o que a baixa exige, por que ela não trava —
mora em `ri_revisao.py`; aqui só se ligam os fios.

MÓDULO PRÓPRIO, E NÃO DENTRO DE `ri_web.py`, por um motivo prático: aquele
arquivo está sendo escrito por outra passada ao mesmo tempo, e duas mãos no
mesmo arquivo se atropelam. As rotas ficam aqui e o `app.py` as registra
como registra as outras.
"""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for

import ri_revisao as RV
from bd_nativo import banco
from seguranca_web import destino_interno  # M1/B3 (LX11): o «volte para» só leva a caminho desta casa
from seguranca_web import numero_digitado  # LD13: o número que a tela mandou


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """A ASSINATURA É A DA CASA — ver `ajuda_web.registrar_rotas`."""

    usuario_id = app.extensions["usuario_id"]

    @app.route("/registro-imoveis/revisoes")
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_revisoes():
        """O que falta conferir, da casa inteira."""
        with db.connect() as con:
            notas = RV.abertas(con)
            # O que já foi respondido continua à vista, e de propósito: a
            # decisão escrita é o que a correição lê, e uma tela que só
            # mostra o que falta esconde justamente a resposta.
            baixadas = banco(con).ler(
                """SELECT r.*, m.numero AS matricula_numero,
                          a.tipo AS ato_tipo, a.numero AS ato_numero
                   FROM ri_revisoes r
                   JOIN ri_matriculas m ON m.id = r.matricula_id
                   LEFT JOIN ri_atos a ON a.id = r.ato_id
                   WHERE r.situacao=%s
                   ORDER BY r.baixada_em DESC, r.id DESC LIMIT 30""",
                (RV.BAIXADA,))
        return render_template("ri_revisoes.html", notas=notas,
                               baixadas=baixadas, fmt_date=fmt_date)

    # A baixa e decisao escrita que a correicao le: e do oficial/substituto.
    # O balcao ve e anota (rota abaixo), mas nao baixa a nota que outro abriu.
    @app.route("/registro-imoveis/revisoes/<int:revisao_id>/baixar",
               methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER")
    def ri_revisao_baixar(revisao_id):
        decisao = request.form.get("decisao") or ""
        try:
            with db.transaction() as con:
                RV.baixar(con, revisao_id, decisao=decisao, agora=db.now(),
                          usuario=usuario_id())
        except RV.RevisaoError as erro:
            flash(str(erro), "danger")
        else:
            # `audit` abre transação própria — por isso fica FORA do `with`.
            #
            # A ASSINATURA É `(acao, tipo_da_entidade, id_da_entidade,
            # detalhes)`, e esta chamada estava com os quatro argumentos
            # desencontrados — o id da nota no lugar do TIPO, e o texto da
            # decisão no lugar do ID. Não estourava (nenhum deles é conferido),
            # e por isso durou: a linha de auditoria é que ficava dizendo que a
            # entidade se chama «7». Corrigido em 19/09/2026.
            audit("RI_REVISAO_BAIXAR", "RI_REVISAO", revisao_id,
                  {"decisao": decisao[:200]})
            flash("Nota de revisão baixada, com o que você decidiu escrito "
                  "nela.", "success")
        return redirect(destino_interno(request.form.get("voltar"),
                                        url_for("ri_revisoes")))

    @app.route("/registro-imoveis/<int:matricula_id>/revisoes",
               methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_revisao_anotar(matricula_id):
        ato_bruto = request.form.get("ato_id") or None
        ato_id = numero_digitado(ato_bruto) if ato_bruto else None
        try:
            # O ato que não é número é o mesmo «não encontrado» de `anotar`
            # (LD13): o `int()` aqui dentro derrubava a tela.
            if ato_bruto and ato_id is None:
                raise RV.RevisaoError(f"Ato {ato_bruto[:20]} não encontrado.")
            with db.transaction() as con:
                RV.anotar(con, matricula_id=matricula_id,
                          ato_id=ato_id,
                          assunto=request.form.get("assunto") or "",
                          nota=request.form.get("nota") or "",
                          agora=db.now(), origem="MANUAL",
                          usuario=usuario_id())
        except RV.RevisaoError as erro:
            flash(str(erro), "danger")
        else:
            audit("RI_REVISAO_ANOTAR", "RI_MATRICULA", matricula_id,
                  {"assunto": (request.form.get("assunto") or "")[:200]})
            flash("Anotado. A nota fica na ficha até alguém conferir.",
                  "success")
        return redirect(url_for("ri_ficha", matricula_id=matricula_id))
