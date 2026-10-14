"""A CÓPIA DA DIGITALIZAÇÃO PARA O ONR, VISTA DA FICHA DA MATRÍCULA.

    «nao existe outra forma que o sistema processe e crie a copia em tiff?»
                                                      — o oficial, 10/10/2026

A conversão mora em `gestor_cargas_ri` (seção «NA HORA DO ENVIO»); aqui só se
ligam os fios: a situação que a ficha mostra e o botão «converter agora», que
serve para quando a conversão falhou ou ainda não aconteceu. A rota que recebe
a varredura (`ri_web.ri_upload_digitalizacao`) dispara a mesma conversão.
"""
from __future__ import annotations

from contextlib import closing

from flask import abort, flash, redirect, url_for

import gestor_cargas_ri as GCR


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    """A ASSINATURA É A DA CASA — ver `ajuda_web.registrar_rotas`."""

    def situacao_da_imagem_onr(matricula_id) -> dict:
        """Para a ficha: em que pé está a cópia ao ONR. Nunca derruba a ficha."""
        try:
            with closing(db.connect()) as con:
                return GCR.situacao_da_imagem(con, int(matricula_id), db.db_path)
        except Exception as erro:                       # noqa: BLE001
            return {"estado": "DESCONHECIDO", "motivo": f"{type(erro).__name__}: {erro}"}

    app.add_template_global(situacao_da_imagem_onr, "situacao_da_imagem_onr")

    @app.route("/registro-imoveis/<int:matricula_id>/digitalizacao/onr",
               methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_onr_imagem_converter(matricula_id: int):
        """Converte agora a digitalização desta ficha para a pasta do CSL2."""
        with closing(db.connect()) as con:
            r = con.execute("SELECT numero, digi_path FROM ri_matriculas WHERE id=?",
                            (matricula_id,)).fetchone()
        if not r:
            abort(404)
        if not (r[1] or "").strip():
            flash("Esta matrícula não tem digitalização oficial para converter.", "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))
        linha = GCR.converter_em_segundo_plano(db, matricula_id)
        audit("RI_DIGITALIZACAO_ONR_CONVERTER", "RI_MATRICULA", matricula_id,
              {"numero": r[0], "comecou": linha is not None})
        if linha is None:
            flash("A conversão não pôde começar (a ficha não vai ao ONR, ou a pasta do "
                  "CSL2 está inacessível). A rodada das 07:30 tenta de novo.", "warning")
        else:
            flash("Conversão para o ONR começada. Atualize a ficha em alguns segundos "
                  "para ver o resultado.", "success")
        return redirect(url_for("ri_ficha", matricula_id=matricula_id))
