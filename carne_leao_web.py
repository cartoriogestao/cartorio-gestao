"""As telas do carnê-leão e do livro-caixa do titular.

SÓ O ADMIN (26/10/2026). É o imposto de renda PESSOAL do delegatário: a renda
dele não é assunto do gerente nem do auditor da casa. Toda rota é
`roles_required("ADMIN")`, e o menu só mostra o link ao ADMIN.

O mês que a tela abre é o ANTERIOR: o carnê-leão de um mês se apura e se
paga no mês seguinte, e o mês corrente ainda está andando.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from flask import flash, redirect, render_template, request, url_for

import carne_leao as CL
import csv_seguro as CSVS
import oficial_obrigacoes as OO
from caixa_schema import reais


def _mes_anterior(hoje: date) -> str:
    return (hoje.replace(day=1) - timedelta(days=1)).isoformat()[:7]


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_nome = app.extensions["usuario_nome"]

    def _agora() -> str:
        return datetime.now().replace(microsecond=0).isoformat(timespec="seconds")

    def _mes() -> str:
        bruto = request.values.get("mes") or _mes_anterior(date.today())
        try:
            return CL.competencia(bruto)
        except CL.CarneLeaoError:
            return _mes_anterior(date.today())

    def _volta(mes: str, ancora: str = ""):
        return redirect(url_for("carne_leao", mes=mes) + (f"#{ancora}" if ancora else ""))

    @app.route("/administrativo/carne-leao")
    @login_required
    @roles_required("ADMIN")
    def carne_leao():
        mes = _mes()
        hoje = date.today()
        with db.connect() as con:
            a, ano = CL.apurar_com_o_ano(con, mes, ate=hoje.isoformat()[:7])
            cfg = CL.configuracao(con)
            ob = CL.obrigacao_da_agenda(con)
        prazo = OO.proximo_vencimento(ob, hoje) if ob else None
        return render_template(
            "carne_leao.html", a=a, mes=mes, ano=ano, cfg=cfg, prazo=prazo,
            categorias=CL.CATEGORIAS_FISCAIS, modos=CL.MODOS_DO_DEPOSITO,
            formas_fundos=CL.FORMAS_DOS_FUNDOS,
            aviso_lista=CL.AVISO_DA_LISTA, aviso_leiaute=CL.AVISO_DO_LEIAUTE,
            reais=reais, percentual=CL.percentual, hoje=hoje.isoformat())

    @app.route("/administrativo/carne-leao/outra-entrada/<int:lancamento_id>",
               methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def carne_leao_outra_entrada(lancamento_id: int):
        mes, resposta = _mes(), request.form.get("receita")
        try:
            with db.transaction() as con:
                CL.marcar_outra_entrada(con, lancamento_id, receita=resposta)
        except CL.CarneLeaoError as erro:
            flash(str(erro), "danger")
            return _volta(mes, "receitas")
        audit("CARNE_LEAO_OUTRA_ENTRADA_RESPONDIDA", "cx_lancamentos", lancamento_id,
              {"receita_do_titular": resposta})
        flash("Resposta gravada.", "success")
        return _volta(mes, "receitas")

    @app.route("/administrativo/carne-leao/despesa/<int:ld_despesa_id>/marcar",
               methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def carne_leao_marcar(ld_despesa_id: int):
        f, mes = request.form, _mes()
        try:
            with db.transaction() as con:
                CL.marcar_despesa(con, ld_despesa_id, categoria_fiscal=f.get("categoria_fiscal") or "",
                                  dedutivel=f.get("dedutivel"), por=usuario_nome(),
                                  agora=_agora(), observacao=f.get("observacao"))
        except CL.CarneLeaoError as erro:
            flash(str(erro), "danger")
            return _volta(mes, "despesas")
        audit("CARNE_LEAO_DESPESA_MARCADA", "ld_despesas", ld_despesa_id,
              {"categoria_fiscal": f.get("categoria_fiscal"), "dedutivel": f.get("dedutivel")})
        flash("Marcação gravada.", "success")
        return _volta(mes, "despesas")

    @app.route("/administrativo/carne-leao/lancamentos", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def carne_leao_lancar():
        f, mes = request.form, _mes()
        try:
            with db.transaction() as con:
                novo = CL.lancar_avulso(
                    con, tipo=f.get("tipo") or "", data=f.get("data"),
                    descricao=f.get("descricao"), valor=f.get("valor"),
                    documento=f.get("documento"), categoria_fiscal=f.get("categoria_fiscal") or "",
                    dedutivel=f.get("dedutivel") or "0", hoje=date.today().isoformat(),
                    agora=_agora(), por=usuario_nome())
        except CL.CarneLeaoError as erro:
            flash(str(erro), "danger")
            return _volta(mes, "avulso")
        audit("CARNE_LEAO_LANCAMENTO_AVULSO", "cl_lancamentos", novo,
              {"tipo": f.get("tipo"), "valor": f.get("valor")})
        flash("Lançamento gravado no livro-caixa.", "success")
        return _volta(mes, "avulso")

    @app.route("/administrativo/carne-leao/lancamentos/<int:lancamento_id>/anular",
               methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def carne_leao_anular(lancamento_id: int):
        mes = _mes()
        try:
            with db.transaction() as con:
                CL.anular_avulso(con, lancamento_id, motivo=request.form.get("motivo"),
                                 por=usuario_nome(), agora=_agora())
        except CL.CarneLeaoError as erro:
            flash(str(erro), "danger")
            return _volta(mes)
        audit("CARNE_LEAO_LANCAMENTO_ANULADO", "cl_lancamentos", lancamento_id,
              {"motivo": request.form.get("motivo")})
        flash("Lançamento anulado. A linha fica no histórico.", "success")
        return _volta(mes)

    @app.route("/administrativo/carne-leao/exportar")
    @login_required
    @roles_required("ADMIN")
    def carne_leao_exportar():
        mes = _mes()
        with db.connect() as con:
            a = CL.apurar(con, mes)
        audit("CARNE_LEAO_LIVRO_CAIXA_EXPORTADO", "cl_lancamentos", None, {"mes": mes})
        # pelo `csv_seguro`: tudo entre aspas e fórmula desarmada
        return CSVS.resposta(f"livro-caixa-{mes}.csv", None, CL.livro_caixa_linhas(a))

    @app.route("/administrativo/carne-leao/configuracao", methods=["GET", "POST"])
    @login_required
    @roles_required("ADMIN")
    def carne_leao_configuracao():
        if request.method == "POST":
            f, acao = request.form, request.form.get("acao")
            try:
                with db.transaction() as con:
                    if acao == "tabela":
                        novo = CL.cadastrar_tabela(
                            con, vigencia_inicio=f.get("vigencia_inicio"),
                            descricao=f.get("descricao"), fonte=f.get("fonte"),
                            faixas_texto=f.get("faixas"), por=usuario_nome(), agora=_agora())
                        detalhe = {"tabela": novo, "vigencia": f.get("vigencia_inicio")}
                        recado = "Tabela cadastrada."
                    elif acao == "tabelas_nacionais":
                        feito = CL.cadastrar_tabelas_nacionais(con, por=usuario_nome(),
                                                               agora=_agora())
                        detalhe, recado = {"feito": feito}, " ".join(feito)
                    elif acao == "anular_tabela":
                        CL.anular_tabela(con, int(f.get("tabela_id") or 0), motivo=f.get("motivo"),
                                         por=usuario_nome(), agora=_agora())
                        detalhe = {"tabela": f.get("tabela_id"), "motivo": f.get("motivo")}
                        recado = "Tabela anulada. A linha fica no histórico."
                    elif acao == "lista_conferida":
                        texto = CL.registrar_lista_conferida(
                            con, por=usuario_nome(), quando=_agora(), contador=f.get("contador"))
                        detalhe, recado = {"registro": texto}, "Registrado."
                    else:
                        mudou = CL.gravar_configuracao(con, f)
                        detalhe = {k: {"de": de, "para": para} for k, (de, para) in mudou.items()}
                        recado = "Configuração gravada." if mudou else "Nada mudou."
            except (CL.CarneLeaoError, ValueError) as erro:
                flash(str(erro), "danger")
                return redirect(url_for("carne_leao_configuracao"))
            audit(f"CARNE_LEAO_CONFIGURACAO_{str(acao or 'geral').upper()}", "settings", None,
                  detalhe)
            flash(recado, "success")
            return redirect(url_for("carne_leao_configuracao"))
        with db.connect() as con:
            cfg = CL.configuracao(con)
            lista = CL.tabelas(con)
        return render_template(
            "carne_leao_configuracao.html", cfg=cfg, tabelas=lista,
            modos=CL.MODOS_DO_DEPOSITO, regras=CL.REGRAS_DO_PRAZO,
            formas_fundos=CL.FORMAS_DOS_FUNDOS, nacionais=CL.TABELAS_NACIONAIS,
            categorias=CL.CATEGORIAS_FISCAIS, aviso_lista=CL.AVISO_DA_LISTA,
            reais=reais, percentual=CL.percentual)
