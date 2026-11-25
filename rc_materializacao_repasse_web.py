"""As telas do valor de terceiro da materialização — F010, 25/11/2026.

O domínio mora em `rc_materializacao_repasse`; aqui só o pedido, a resposta, o
papel de quem pede e o rastro em `audit_logs`.

QUEM FAZ O QUÊ (o molde do repasse ao apresentante, `protesto_repasse_web`)
    Receber o valor do outro cartório é do balcão (ADMIN, MANAGER, USER): é
    quem atende o cliente e tem o caixa aberto. Registrar o repasse, conciliar
    e encerrar sem repasse é de quem responde pelo caixa (ADMIN, MANAGER).

O RASTRO NÃO LEVA DADO DE PESSOA
    O `audit` guarda o id, o pedido, o valor e a situação — e não o nome nem o
    documento de quem pagou.
"""
from __future__ import annotations

from datetime import datetime

from flask import flash, redirect, render_template, request, url_for

import rc_materializacao_repasse as RMR
from bd_nativo import banco
from caixa_schema import FORMAS_PAGAMENTO, reais

QUEM_RECEBE = ("ADMIN", "MANAGER", "USER")
QUEM_VE = ("ADMIN", "MANAGER", "USER", "AUDITOR")
QUEM_MEXE_NO_DINHEIRO = ("ADMIN", "MANAGER")

#: As formas do balcão que servem para valor de terceiro: dinheiro que o
#: cliente entrega agora (`RMR.conferir` recusa as outras, com a razão).
FORMAS_DO_TERCEIRO = {k: v for k, v in FORMAS_PAGAMENTO.items()
                      if k not in ("GRATUITO", "DEPOSITO_PREVIO", "PG_CRC", "PG_ONR")}


def registrar_rotas(app, db, login_required, roles_required, audit):
    """Pendura as telas do valor de terceiro no app já construído."""

    usuario_nome = app.extensions["usuario_nome"]
    usuario_id = app.extensions["usuario_id"]

    def agora() -> str:
        return db.now()

    def hoje() -> str:
        return agora()[:10]

    def _campo(nome: str) -> str:
        return (request.form.get(nome) or "").strip()

    def _volta():
        destino = _campo("volta")
        if destino == "materializacoes":
            return redirect(url_for("rcpn_materializacoes"))
        return redirect(url_for("rcpn_materializacao_repasses"))

    @app.context_processor
    def _formas_do_terceiro():
        return {"FORMAS_DO_TERCEIRO": FORMAS_DO_TERCEIRO,
                "FORMAS_DE_REPASSE_TERCEIRO": RMR.FORMAS_DE_REPASSE}

    @app.route("/rcpn/materializacoes/terceiros", methods=["POST"])
    @roles_required(*QUEM_RECEBE)
    def rcpn_materializacao_receber_terceiro():
        """Recebe no caixa o valor do outro cartório. ESCREVE."""
        numero = _campo("protocolo")
        with db.connect() as con:
            bd = banco(con)
            prot = bd.um("SELECT id FROM cx_protocolos WHERE numero=%s", (numero,)) \
                if numero else None
            caixa = bd.um(
                """SELECT id FROM cx_caixas WHERE operador_nome=%s AND situacao='ABERTO'
                    ORDER BY data DESC LIMIT 1""", (usuario_nome(),))
        if not prot:
            flash(f"Informe o protocolo da materialização (o «{numero or '—'}» não "
                  f"existe). Nada foi lançado.", "danger")
            return redirect(url_for("rcpn_materializacoes"))
        dados = {k: _campo(k) for k in (
            "pedido_crc", "cartorio_nome", "cartorio_cidade", "cartorio_uf",
            "emolumentos_origem", "fundos_origem", "taxa_crc", "forma_pagamento",
            "pagador", "pagador_documento")}
        try:
            with db.transaction() as con:
                res = RMR.receber(
                    con, int(prot["id"]), dados,
                    caixa_id=int(caixa["id"]) if caixa else 0, hoje=hoje(),
                    hora=datetime.now().strftime("%H:%M"), agora=agora(),
                    usuario=usuario_nome(), usuario_id=usuario_id())
        except RMR.RepasseTerceiroError as erro:
            flash(f"{erro} Nada foi lançado.", "danger")
            return redirect(url_for("rcpn_materializacoes"))
        audit("RCPN_VALOR_DE_TERCEIRO_RECEBIDO", RMR.TABELA, res["repasse_id"],
              {"pedido_crc": res["pedido_crc"], "protocolo": res["protocolo"],
               "lancamento": res["lancamento"], "valor": reais(res["valor_centavos"])})
        flash(f"Valor de terceiro recebido: R$ {reais(res['valor_centavos'])}, "
              f"lançamento nº {res['lancamento']} no protocolo {res['protocolo']}. "
              f"Não é emolumento desta casa: fica fora da receita, do ISS e do Livro "
              f"Diário. Repasse ao cartório de origem até "
              f"{res['prazo'][8:10]}/{res['prazo'][5:7]}/{res['prazo'][:4]}.",
              "success")
        return redirect(url_for("rcpn_materializacoes"))

    @app.route("/rcpn/materializacoes/repasses")
    @roles_required(*QUEM_VE)
    def rcpn_materializacao_repasses():
        """O que foi recebido para outro cartório e o que falta fazer. Só LÊ."""
        with db.connect() as con:
            pend = RMR.pendentes(con, hoje=hoje())
            todos = RMR.listar(con, limite=200)
            prazo = RMR.prazo_em_dias_uteis(con)
        return render_template("rc_materializacao_repasses.html", pend=pend,
                               todos=todos, prazo_dias=prazo, reais=reais,
                               SITUACOES=RMR.SITUACOES, hoje=hoje(),
                               categoria=RMR.CATEGORIA_DA_DESPESA)

    def _acao(nome_audit: str, fazer):
        rid = request.view_args["repasse_id"]
        try:
            with db.transaction() as con:
                res = fazer(con, rid)
        except RMR.RepasseTerceiroError as erro:
            flash(str(erro), "danger")
            return None
        audit(nome_audit, RMR.TABELA, rid, {k: v for k, v in res.items()
                                             if k not in ("favorecido",)})
        return res

    @app.route("/rcpn/materializacoes/repasses/<int:repasse_id>/repassar",
               methods=["POST"])
    @roles_required(*QUEM_MEXE_NO_DINHEIRO)
    def rcpn_materializacao_repassar(repasse_id):
        """Registra o repasse ao outro cartório, com o comprovante. ESCREVE."""
        res = _acao("RCPN_VALOR_DE_TERCEIRO_REPASSADO", lambda con, rid: RMR.registrar_repasse(
            con, rid, forma=_campo("forma"), comprovante=_campo("comprovante"),
            repassado_em=_campo("repassado_em"), hoje=hoje(), agora=agora(),
            despesa_id=_campo("despesa_id"), favorecido=_campo("favorecido"),
            usuario=usuario_nome()))
        if res:
            flash(f"Repasse do pedido CRC nº {res['pedido_crc']} registrado"
                  + ("" if res["no_prazo"] else " — FORA do prazo da casa") + ".",
                  "success" if res["no_prazo"] else "warning")
        return _volta()

    @app.route("/rcpn/materializacoes/repasses/<int:repasse_id>/conciliar",
               methods=["POST"])
    @roles_required(*QUEM_MEXE_NO_DINHEIRO)
    def rcpn_materializacao_conciliar(repasse_id):
        """Confere o repasse com o que o outro lado confirmou. ESCREVE."""
        res = _acao("RCPN_VALOR_DE_TERCEIRO_CONCILIADO", lambda con, rid: RMR.conciliar(
            con, rid, valor_confirmado=_campo("valor_confirmado"),
            referencia=_campo("referencia"), agora=agora(), usuario=usuario_nome()))
        if res:
            flash(f"Repasse do pedido CRC nº {res['pedido_crc']} conciliado.", "success")
        return _volta()

    @app.route("/rcpn/materializacoes/repasses/<int:repasse_id>/encerrar",
               methods=["POST"])
    @roles_required(*QUEM_MEXE_NO_DINHEIRO)
    def rcpn_materializacao_encerrar(repasse_id):
        """Encerra o valor que não vai ser repassado. ESCREVE."""
        res = _acao("RCPN_VALOR_DE_TERCEIRO_ENCERRADO", lambda con, rid: RMR.encerrar_sem_repasse(
            con, rid, motivo=_campo("motivo"), agora=agora(),
            devolucao=_campo("devolucao"), usuario=usuario_nome()))
        if res:
            flash(f"Registro encerrado: {RMR.SITUACOES[res['situacao']].lower()}.",
                  "success")
        return _volta()
