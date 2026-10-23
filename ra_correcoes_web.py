"""As telas de corrigir o registro do Livro 3 — editar, descancelar, renumerar.

A regra mora em `ra_correcoes.py`; aqui só se ligam os fios. `audit` fica
**fora** do `with db.transaction()` — e aqui ele é mais que rastro: é o que
responde, meses depois, **o que foi corrigido, de quê para quê e por quem**.
"""
from __future__ import annotations

from flask import abort, flash, redirect, request, url_for

from bd_nativo import banco
import ra_correcoes as CORR
import ra_selo as RS


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """A ASSINATURA É A DA CASA — ver `ajuda_web.registrar_rotas`."""

    usuario_nome = app.extensions["usuario_nome"]

    def _campo(nome: str) -> str:
        return (request.form.get(nome) or "").strip()

    @app.route("/livro3/<int:registro_id>/editar", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def livro3_editar_registro(registro_id: int):
        """Corrige o cadastro do registro. **Não mexe em ato nenhum.**

        É do ADMIN e do gerente: o que se corrige aqui é o que a ficha afirma
        sobre o título, e a ficha é o que a certidão reproduz.
        """
        campos = {}
        for campo in CORR.CAMPOS_EDITAVEIS:
            if campo not in request.form:
                continue
            valor = _campo(campo)
            # O VALOR VAI EM CENTAVOS, e a tela pergunta em reais — a mesma
            # leitura do selo, num lugar só.
            campos[campo] = (RS.centavos_do_valor(valor)
                             if campo == "valor_centavos" else valor)
        try:
            with db.transaction() as con:
                mudou = CORR.editar(con, registro_id, campos=campos,
                                    agora=db.now(), usuario=usuario_nome())
        except CORR.CorrecaoError as erro:
            flash(str(erro), "danger")
        else:
            if mudou:
                audit("RA_REGISTRO_CORRIGIDO", "ra_registros", registro_id,
                      mudou)
                quais = ", ".join(CORR.CAMPOS_EDITAVEIS[c] for c in mudou)
                flash(f"Corrigido: {quais}. O antes e o depois ficaram na "
                      f"auditoria.", "success")
            else:
                flash("Nada mudou — os campos vieram iguais aos que já "
                      "estavam lá.", "warning")
        return redirect(url_for("livro3_registro", registro_id=registro_id))

    @app.route("/livro3/<int:registro_id>/descancelar", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def livro3_descancelar(registro_id: int):
        """Devolve o registro a ATIVO, com o motivo escrito.

        **Ela não apaga a averbação que cancelou** — aquela está no livro e
        fica. O que se desfaz é a marca da ficha.
        """
        motivo = _campo("motivo")
        try:
            with db.transaction() as con:
                CORR.descancelar(con, registro_id, motivo=motivo,
                                 agora=db.now(), usuario=usuario_nome())
        except CORR.CorrecaoError as erro:
            flash(str(erro), "danger")
        else:
            audit("RA_REGISTRO_DESCANCELADO", "ra_registros", registro_id,
                  {"motivo": motivo[:400]})
            flash("O registro voltou a ATIVO. A averbação que o cancelou "
                  "continua no livro — o que mudou foi a marca da ficha.",
                  "success")
        return redirect(url_for("livro3_registro", registro_id=registro_id))

    @app.route("/livro3/<int:registro_id>/renumerar", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def livro3_renumerar(registro_id: int):
        """Põe os atos do registro na numeração contínua.

        **Ato com selo não se renumera**: o selo carrega o número do ato
        dentro dele, e o selo não se reescreve.
        """
        with db.connect() as con:
            if banco(con).um("SELECT 1 FROM ra_registros WHERE id=%s",
                             (registro_id,)) is None:
                abort(404)
        try:
            with db.transaction() as con:
                mudou = CORR.renumerar(con, registro_id, agora=db.now(),
                                       usuario=usuario_nome())
        except CORR.CorrecaoError as erro:
            flash(str(erro), "danger")
        else:
            audit("RA_ATOS_RENUMERADOS", "ra_registros", registro_id,
                  {"atos": [{"id": a["id"], "de": a["numero"],
                             "para": a["deveria_ser"]} for a in mudou]})
            flash(f"{len(mudou)} ato(s) renumerado(s), na ordem em que foram "
                  f"lavrados.", "success")
        return redirect(url_for("livro3_registro", registro_id=registro_id))
