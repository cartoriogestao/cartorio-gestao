"""A tela de corrigir dado do acervo importado — pedido do oficial em
08/09/2026. O domínio (a lista de tabelas e campos liberados, a guarda de
proveniência) mora em `acervo_correcao.py`; aqui só se ligam os fios.
"""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for

import acervo_correcao as AC


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """A ASSINATURA É A DA CASA — ver `ajuda_web.registrar_rotas`."""

    @app.route("/administrativo/acervo/corrigir", methods=["GET", "POST"])
    @login_required
    @roles_required("ADMIN")
    def acervo_corrigir():
        tabela = (request.values.get("tabela") or "").strip()
        termo = (request.values.get("termo") or "").strip()
        row_id = request.values.get("id")
        row_id = int(row_id) if row_id and row_id.isdigit() else None

        if request.method == "POST" and request.form.get("acao") == "salvar":
            motivo = request.form.get("motivo", "")
            try:
                campos_da_tabela = AC.campos_de(tabela)
                valores = {c: request.form[f"campo_{c}"] for c in campos_da_tabela
                          if f"campo_{c}" in request.form}
                with db.transaction() as con:
                    resultado = AC.corrigir(con, tabela, row_id, valores, motivo)
                audit("ACERVO_CORRIGIDO", resultado["tabela"].upper(),
                     resultado["id"], resultado)
                flash(f"Corrigido: {', '.join(resultado['mudancas'])}.", "success")
            except AC.CorrecaoError as exc:
                flash(str(exc), "danger")
            return redirect(url_for("acervo_corrigir", tabela=tabela, id=row_id))

        achados = []
        linha = None
        if tabela and termo:
            with db.connect() as con:
                achados = AC.buscar(con, tabela, termo)
        if tabela and row_id:
            with db.connect() as con:
                try:
                    linha = AC.obter(con, tabela, row_id)
                except AC.CorrecaoError as exc:
                    flash(str(exc), "danger")
                    row_id = None

        return render_template(
            "acervo_corrigir.html", tabelas=AC.tabelas_disponiveis(),
            tabela=tabela, termo=termo, achados=achados, linha=linha,
            row_id=row_id,
            campos=AC.campos_de(tabela) if (tabela and linha) else [])
