"""As telas do valor de terceiro da materialização — F010, 25/11/2026.

O domínio mora em `rc_materializacao_repasse`; aqui só o pedido, a resposta, o
papel de quem pede e o rastro em `audit_logs`.

QUEM FAZ O QUÊ (o molde do repasse ao apresentante, `protesto_repasse_web`)
    Receber o valor do outro cartório é do balcão (ADMIN, MANAGER, USER): é
    quem atende o cliente e tem o caixa aberto. Enviar o saldo à CRC e tirar do
    saldo o pedido que não vale é de quem responde pelo caixa (ADMIN, MANAGER).
    Transformar o saldo em caixa é do oficial (ADMIN — e o TI, que passa onde o
    ADMIN passa).

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
#: O saldo que deixa de ser de repasse e fica na casa: decisão do oficial.
QUEM_TRANSFORMA_EM_CAIXA = ("ADMIN",)

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
                "DESTINOS_DO_SALDO_CRC": RMR.DESTINOS}

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
              f"Diário, e entra no saldo de repasse da CRC.", "success")
        return redirect(url_for("rcpn_materializacoes"))

    @app.route("/rcpn/materializacoes/repasses")
    @roles_required(*QUEM_VE)
    def rcpn_materializacao_repasses():
        """O saldo de repasse da CRC, de onde veio e para onde foi. Só LÊ."""
        with db.connect() as con:
            pend = RMR.pendentes(con)
            todos = RMR.listar(con, limite=200)
            destinos = RMR.destinacoes(con, limite=200)
        return render_template("rc_materializacao_repasses.html", pend=pend,
                               todos=todos, destinos=destinos, reais=reais,
                               SITUACOES=RMR.SITUACOES, hoje=hoje(),
                               QUEM_TRANSFORMA_EM_CAIXA=QUEM_TRANSFORMA_EM_CAIXA)

    def _destinar(destino: str):
        try:
            with db.transaction() as con:
                res = RMR.destinar(
                    con, destino=destino, valor=_campo("valor"), dia=_campo("dia"),
                    hoje=hoje(), agora=agora(), despesa_id=_campo("despesa_id"),
                    comprovante=_campo("comprovante"), observacao=_campo("observacao"),
                    usuario=usuario_nome())
        except RMR.RepasseTerceiroError as erro:
            flash(f"{erro} Nada foi registrado.", "danger")
            return _volta()
        audit("RCPN_SALDO_CRC_DESTINADO", RMR.TABELA_DESTINOS, res["destinacao_id"],
              {"destino": res["destino"], "valor": reais(res["valor_centavos"]),
               "despesa_id": res["despesa_id"]})
        flash(f"R$ {reais(res['valor_centavos'])} "
              f"{RMR.DESTINOS[res['destino']]['curto']}. Saldo de repasse da CRC: "
              f"R$ {reais(max(res['saldo_centavos'], 0))}.", "success")
        return _volta()

    @app.route("/rcpn/materializacoes/repasses/enviar-crc", methods=["POST"])
    @roles_required(*QUEM_MEXE_NO_DINHEIRO)
    def rcpn_materializacao_enviar_crc():
        """Envia parte do saldo à CRC, pela despesa paga. ESCREVE."""
        return _destinar(RMR.ENVIO_CRC)

    @app.route("/rcpn/materializacoes/repasses/virar-caixa", methods=["POST"])
    @roles_required(*QUEM_TRANSFORMA_EM_CAIXA)
    def rcpn_materializacao_virar_caixa():
        """Transforma parte do saldo em caixa da casa. ESCREVE (só o registro)."""
        return _destinar(RMR.CAIXA)

    @app.route("/rcpn/materializacoes/repasses/<int:repasse_id>/encerrar",
               methods=["POST"])
    @roles_required(*QUEM_MEXE_NO_DINHEIRO)
    def rcpn_materializacao_encerrar(repasse_id):
        """Tira do saldo o pedido que não vale (devolvido ou cancelado). ESCREVE."""
        try:
            with db.transaction() as con:
                res = RMR.encerrar_sem_repasse(
                    con, repasse_id, motivo=_campo("motivo"), agora=agora(),
                    devolucao=_campo("devolucao"), usuario=usuario_nome())
        except RMR.RepasseTerceiroError as erro:
            flash(str(erro), "danger")
            return _volta()
        audit("RCPN_VALOR_DE_TERCEIRO_ENCERRADO", RMR.TABELA, repasse_id, res)
        flash(f"Registro encerrado: {RMR.SITUACOES[res['situacao']].lower()}.", "success")
        return _volta()
