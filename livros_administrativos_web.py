"""As telas dos livros obrigatórios (LG08, 19/10/2026).

    - «Livros obrigatórios»: o que o Código de Normas do MA manda ter, e onde
      cada livro está no sistema (`livros_obrigatorios`);
    - o Livro de Visitas e Correições (`livro_visitas`, art. 189);
    - o Livro Diário Auxiliar da Receita e da Despesa (`livro_diario`, arts.
      190 a 207);
    - o Livro de Controle de Depósito Prévio (`livro_deposito_previo`, art. 198).

QUEM VÊ E QUEM ESCREVE
    São livros do DELEGATÁRIO: ficam «sob a guarda e responsabilidade» dele
    (art. 189), e o Diário leva receita e despesa da serventia. Veem o oficial
    (ADMIN), o gerente (MANAGER) e o auditor (AUDITOR, que vê e não pratica).
    Lançam o oficial e o gerente. GERAR o Diário do mês — a fotografia que vai
    assinada e rubricada (art. 205) — é só do oficial. O balcão (USER) não
    entra: nada aqui é ato de atendimento.

Toda escrita é POST, passa pelo token de formulário do app e deixa rastro em
`audit_logs` — sem o texto do termo nem a descrição da despesa, que ficam no
próprio livro.
"""
from __future__ import annotations

from datetime import date

from flask import abort, flash, redirect, render_template, request, url_for

import livro_deposito_previo as LDP
import livro_diario as LD
import livro_visitas as LV
import livros_obrigatorios as LO
from ri_schema import ler_feriados_locais
from serventia import dados as dados_serventia

VEEM = ("ADMIN", "MANAGER", "AUDITOR")
LANCAM = ("ADMIN", "MANAGER")
GERA = ("ADMIN",)


def _mes_anterior(hoje: date) -> str:
    return (f"{hoje.year - 1:04d}-12" if hoje.month == 1
            else f"{hoje.year:04d}-{hoje.month - 1:02d}")


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_nome = app.extensions["usuario_nome"]
    usuario_papel = app.extensions["usuario_papel"]

    def _feriados() -> set[date]:
        return ler_feriados_locais(db.get_setting("ri_feriados_locais", ""))

    # ------------------------------------------------ o catálogo

    @app.route("/livros-obrigatorios")
    @roles_required(*VEEM)
    def livros_obrigatorios():
        return render_template("livros_obrigatorios.html", grupos=LO.grupos(),
                               contagem=LO.contagem(), situacoes=LO.SITUACOES,
                               fonte=LO.FONTE)

    # ------------------------------------------------ visitas e correições

    @app.route("/livros-obrigatorios/visitas")
    @roles_required(*VEEM)
    def livro_visitas():
        with db.connect() as con:
            linhas = LV.lancamentos(con)
            inspecoes = LV.inspecoes_do_plano(con)
        return render_template("livro_visitas.html", linhas=linhas, inspecoes=inspecoes,
                               naturezas=LV.NATUREZAS, hoje=date.today().isoformat(),
                               pode_lancar=usuario_papel() in LANCAM,
                               retificar=request.args.get("retificar", type=int))

    @app.route("/livros-obrigatorios/visitas", methods=["POST"])
    @roles_required(*LANCAM)
    def livro_visitas_lancar():
        f = request.form
        try:
            with db.transaction() as con:
                feito = LV.lancar(
                    con, hoje=date.today().isoformat(), agora=db.now(), por=usuario_nome(),
                    data=f.get("data"), natureza=f.get("natureza"),
                    autoridade=f.get("autoridade"), autoridade_nome=f.get("autoridade_nome"),
                    processo=f.get("processo"), termo=f.get("termo"),
                    determinacoes=f.get("determinacoes"), prazo=f.get("prazo"),
                    inspecao_id=f.get("inspecao_id"), retifica_id=f.get("retifica_id"),
                    motivo_retificacao=f.get("motivo_retificacao"))
        except LV.VisitaError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("livro_visitas", retificar=f.get("retifica_id") or None))
        audit("LIVRO_VISITAS_LANCADO", "LIVRO_VISITAS", feito["id"],
              {"numero": feito["numero"], "natureza": f.get("natureza"),
               "retifica_id": feito["retifica_id"]})
        flash(f"Lançamento nº {feito['numero']} escriturado no Livro de Visitas e Correições.",
              "success")
        return redirect(url_for("livro_visitas"))

    @app.route("/livros-obrigatorios/visitas/imprimir")
    @roles_required(*VEEM)
    def livro_visitas_imprimir():
        with db.connect() as con:
            linhas = LV.lancamentos(con)
        return render_template("livro_visitas_papel.html", linhas=linhas,
                               sv=dados_serventia(db.get_settings))

    # ------------------------------------------------ diário auxiliar

    @app.route("/livros-obrigatorios/diario")
    @roles_required(*VEEM)
    def livro_diario():
        hoje = date.today()
        try:
            comp = LD.competencia(request.args.get("mes") or _mes_anterior(hoje))
        except LD.DiarioError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("livro_diario"))
        with db.connect() as con:
            livro = LD.apurar(con, comp)
            despesas = LD.despesas_do_mes(con, comp, com_anuladas=True)
            versoes = LD.geracoes(con, comp)
            situacao = LD.situacao_do_mes(con, comp, hoje=hoje.isoformat(),
                                          feriados_locais=_feriados())
        return render_template("livro_diario.html", livro=livro, despesas=despesas,
                               versoes=versoes, situacao=situacao, comp=comp,
                               fundos=LD.FUNDOS, fora=LD.FORA_DO_SISTEMA,
                               em_reais=LD.em_reais, hoje=hoje.isoformat(),
                               pode_lancar=usuario_papel() in LANCAM,
                               pode_gerar=usuario_papel() in GERA)

    @app.route("/livros-obrigatorios/diario/despesas", methods=["POST"])
    @roles_required(*LANCAM)
    def livro_diario_despesa():
        f = request.form
        try:
            with db.transaction() as con:
                novo = LD.lancar_despesa(
                    con, hoje=date.today().isoformat(), agora=db.now(), por=usuario_nome(),
                    data=f.get("data"), descricao=f.get("descricao"),
                    documento_especie=f.get("documento_especie"),
                    documento_numero=f.get("documento_numero"), valor=f.get("valor"))
        except LD.DiarioError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("livro_diario", mes=(f.get("data") or "")[:7] or None))
        audit("LIVRO_DIARIO_DESPESA_LANCADA", "LIVRO_DIARIO_DESPESA", novo,
              {"data": (f.get("data") or "")[:10], "valor": f.get("valor")})
        flash("Despesa lançada no Livro Diário Auxiliar.", "success")
        return redirect(url_for("livro_diario", mes=(f.get("data") or "")[:7]))

    @app.route("/livros-obrigatorios/diario/despesas/<int:despesa_id>/anular", methods=["POST"])
    @roles_required(*LANCAM)
    def livro_diario_anular(despesa_id: int):
        try:
            with db.transaction() as con:
                feito = LD.anular_despesa(con, despesa_id, agora=db.now(), por=usuario_nome(),
                                          motivo=request.form.get("motivo"))
        except LD.DiarioError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("livro_diario", mes=request.form.get("mes") or None))
        audit("LIVRO_DIARIO_DESPESA_ANULADA", "LIVRO_DIARIO_DESPESA", despesa_id,
              {"data": feito["data"], "valor": feito["valor"]})
        flash("Despesa anulada. A linha continua no histórico do mês.", "success")
        return redirect(url_for("livro_diario", mes=str(feito["data"])[:7]))

    @app.route("/livros-obrigatorios/diario/gerar", methods=["POST"])
    @roles_required(*GERA)
    def livro_diario_gerar():
        comp = request.form.get("mes")
        try:
            with db.transaction() as con:
                feito = LD.gerar(con, comp, hoje=date.today().isoformat(), agora=db.now(),
                                 por=usuario_nome(), motivo=request.form.get("motivo"))
        except LD.DiarioError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("livro_diario", mes=comp or None))
        audit("LIVRO_DIARIO_GERADO", "LIVRO_DIARIO", feito["id"],
              {"competencia": feito["competencia"], "versao": feito["versao"],
               "retificacao": feito["versao"] > 1})
        flash(f"Livro Diário de {feito['competencia'][5:7]}/{feito['competencia'][:4]} "
              f"gerado (versão {feito['versao']}). Imprima, assine e rubrique (art. 205).",
              "success")
        return redirect(url_for("livro_diario_versao", geracao_id=feito["id"]))

    @app.route("/livros-obrigatorios/diario/versao/<int:geracao_id>")
    @roles_required(*VEEM)
    def livro_diario_versao(geracao_id: int):
        with db.connect() as con:
            g = LD.geracao(con, geracao_id)
        if not g:
            abort(404)
        return render_template("livro_diario_papel.html", g=g, livro=g["livro"],
                               fundos=LD.FUNDOS, fora=LD.FORA_DO_SISTEMA,
                               em_reais=LD.em_reais, sv=dados_serventia(db.get_settings))

    # ------------------------------------------------ depósito prévio

    @app.route("/livros-obrigatorios/deposito-previo")
    @roles_required(*VEEM)
    def livro_deposito_previo():
        ano = (request.args.get("ano") or "").strip()
        with db.connect() as con:
            livro = LDP.livro(con, ano=ano or None)
        return render_template("livro_deposito_previo.html", livro=livro, ano=ano,
                               reais=LD.em_reais, sv=dados_serventia(db.get_settings))
