"""As telas da minuta do Livro 3.

A regra mora em `ra_minuta.py`; aqui só se ligam os fios. **`audit` fica fora
do `with db.transaction()`** — ele abre transação própria.

MÓDULO PRÓPRIO, e não dentro de `atribuicoes_web.py`: aquele arquivo tem nove
mil linhas e é escrito por outra passada. O que precisou ser tocado lá foi a
rota que lavra, para ela marcar a minuta como lavrada **na mesma transação do
ato**.
"""
from __future__ import annotations

import json

from flask import Response, abort, flash, redirect, render_template, request, url_for

from bd_nativo import banco
import ra_expurgo as EXP
import ra_minuta as MIN
import ra_selo as RS
from seguranca_web import destino_interno  # M1/B3 (LX11): o «volte para» só leva a caminho desta casa


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """A ASSINATURA É A DA CASA — ver `ajuda_web.registrar_rotas`."""

    usuario_nome = app.extensions["usuario_nome"]

    def _campo(nome: str) -> str:
        return (request.form.get(nome) or "").strip()

    def _numero(nome: str):
        bruto = "".join(c for c in _campo(nome) if c.isdigit())
        return int(bruto) if bruto else None

    # ------------------------------------------------------------- a fila

    @app.route("/livro3/minutas")
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def livro3_minutas():
        """O que espera revisão no Livro 3, da casa inteira.

        Ela existe pelo mesmo motivo da lista de rascunhos do Livro 2: **uma
        minuta esquecida num registro que ninguém abre não aparece em lugar
        nenhum**, e quem a escreveu lembra dela por uma semana.
        """
        with db.connect() as con:
            minutas = MIN.a_revisar(con)
        return render_template("livro3_minutas.html", minutas=minutas,
                               situacoes=MIN.SITUACOES, fmt_date=fmt_date)

    # ------------------------------------------------------------ escrever

    @app.route("/livro3/<int:registro_id>/minuta", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def livro3_minuta_criar(registro_id: int):
        """Põe na fila um ato escrito que **ainda não vai ao livro**."""
        try:
            with db.transaction() as con:
                minuta_id = MIN.criar(
                    con, registro_id=registro_id, tipo=_campo("tipo") or "AV",
                    teor=_campo("teor"), agora=db.now(),
                    numero_pretendido=_numero("numero_pretendido"),
                    natureza_titulo=_campo("natureza_titulo"),
                    codigo_tj=_campo("codigo_tj"),
                    base_calculo_centavos=RS.centavos_do_valor(
                        _campo("base_calculo")),
                    protocolo=_campo("protocolo"),
                    usuario=usuario_nome())
        except MIN.MinutaError as erro:
            flash(str(erro), "danger")
        else:
            audit("RA_MINUTA_CRIADA", "ra_minutas", minuta_id,
                  {"registro_id": registro_id, "tipo": _campo("tipo")})
            flash("Minuta guardada. Ela não tomou número, não entrou no livro "
                  "e não pediu selo — está esperando revisão.", "success")
        return redirect(url_for("livro3_registro", registro_id=registro_id))

    @app.route("/livro3/minuta/<int:minuta_id>/guardar", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def livro3_minuta_guardar(minuta_id: int):
        """Guarda a revisão **sem lavrar**."""
        with db.connect() as con:
            m = MIN.uma(con, minuta_id)
        if not m:
            abort(404)
        try:
            with db.transaction() as con:
                MIN.atualizar(
                    con, minuta_id, teor=_campo("teor"), agora=db.now(),
                    tipo=_campo("tipo") or None,
                    numero_pretendido=_numero("numero_pretendido"),
                    natureza_titulo=_campo("natureza_titulo"),
                    codigo_tj=_campo("codigo_tj"),
                    base_calculo_centavos=RS.centavos_do_valor(
                        _campo("base_calculo")),
                    protocolo=_campo("protocolo"), usuario=usuario_nome())
        except MIN.MinutaError as erro:
            flash(str(erro), "danger")
        else:
            audit("RA_MINUTA_GUARDADA", "ra_minutas", minuta_id, None)
            flash("Revisão guardada. Nada foi ao livro.", "success")
        return redirect(url_for("livro3_registro",
                                registro_id=m["registro_id"]))

    @app.route("/livro3/minuta/<int:minuta_id>/descartar", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def livro3_minuta_descartar(minuta_id: int):
        """Tira da fila, **com motivo escrito**. Não apaga nada."""
        with db.connect() as con:
            m = MIN.uma(con, minuta_id)
        if not m:
            abort(404)
        motivo = _campo("motivo")
        try:
            with db.transaction() as con:
                MIN.descartar(con, minuta_id, motivo=motivo, agora=db.now(),
                              usuario=usuario_nome())
        except MIN.MinutaError as erro:
            flash(str(erro), "danger")
        else:
            audit("RA_MINUTA_DESCARTADA", "ra_minutas", minuta_id,
                  {"motivo": motivo[:200]})
            flash("Minuta descartada, com o motivo escrito nela. Ela continua "
                  "na ficha — descartada não some.", "success")
        return redirect(destino_interno(request.form.get("voltar"),
                                        url_for("livro3_registro",
                                                registro_id=m["registro_id"])))

    @app.route("/livro3/ato/<int:ato_id>/devolver-a-minuta", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def livro3_ato_para_minuta(ato_id: int):
        """Devolve um ato lavrado à condição de minuta. ESCREVE.

        Ordem do oficial em 21/09/2026, sobre a AV-01 do registro 1.243, que
        ficou lavrada e sem selo.

        **ELA NÃO É O CAMINHO DE TODO DIA, e a tela diz isso:** ato sem selo
        **se sela onde está**, pelo botão «selar este ato» — não precisa ser
        desfeito para isso. Esta rota é para quando o próprio ato tem de ser
        reescrito antes de voltar ao livro.

        É do ADMIN e do gerente: desfazer ato é decisão de quem assina.
        """
        with db.connect() as con:
            a = banco(con).um("SELECT registro_id FROM ra_atos WHERE id=%s",
                              (ato_id,))
        if not a:
            abort(404)
        registro_id = a["registro_id"]
        try:
            with db.transaction() as con:
                r = MIN.voltar_do_ato(con, ato_id, agora=db.now(),
                                      usuario=usuario_nome(),
                                      motivo=_campo("motivo"))
        except MIN.MinutaError as erro:
            flash(str(erro), "danger")
        else:
            audit("RA_ATO_PARA_MINUTA", "ra_atos", ato_id,
                  {"minuta_id": r["minuta_id"], "rotulo": r["rotulo"],
                   "descancelou": r["descancelou"],
                   "expurgo_id": r["expurgo_id"]})
            recado = (f"O ato {r['rotulo']} voltou a ser minuta, com o teor e "
                      f"os campos do selo dentro. A ata de ocorrência nº "
                      f"{r['expurgo_id']} ficou guardada.")
            if r["descancelou"]:
                recado += (" E o registro voltou a ATIVO: o cancelamento era "
                           "desse ato, que não existe mais.")
            flash(recado, "success")
        return redirect(url_for("livro3_registro", registro_id=registro_id))

    @app.route("/livro3/<int:registro_id>/como-ficara/<int:minuta_id>")
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def livro3_como_ficara(registro_id: int, minuta_id: int):
        """O registro com a minuta no fim — **montado em memória**.

        A pergunta que ela responde é «como esta ficha vai ler depois deste
        ato», e por isso a minuta aparece no fim, que é onde ela entraria.

        **A MARCA DE QUE NÃO É ATO APARECE EM TRÊS LUGARES, e nenhum deles é
        um botão**: ela continua na impressão, porque quem imprime pode
        entregar — e um papel que afirma um ato que não existe é pior que
        papel nenhum.
        """
        try:
            with db.connect() as con:
                visao = MIN.como_ficara(con, registro_id, minuta_id)
        except MIN.MinutaError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("livro3_registro",
                                    registro_id=registro_id))
        return render_template("livro3_como_ficara.html", **visao,
                               MARCA=MIN.MARCA, fmt_date=fmt_date)

    @app.route("/livro3/expurgo/<int:expurgo_id>/ata.odt")
    @login_required
    @roles_required("ADMIN", "MANAGER", "AUDITOR")
    def livro3_expurgo_ata(expurgo_id: int):
        """A ata de ocorrência, em `.odt` — o papel que a correição lê."""
        with db.connect() as con:
            e = EXP.um(con, expurgo_id)
        if not e:
            abort(404)
        from ri_odt import gerar_odt, texto_para_odf
        arquivo = gerar_odt(texto_para_odf(e["ata"]),
                            titulo=f"Ata de ocorrência {expurgo_id} — Livro 3")
        audit("RA_EXPURGO_ATA_IMPRESSA", "ra_expurgos", expurgo_id,
              {"ato": e["ato_rotulo"]})
        return Response(
            arquivo,
            mimetype="application/vnd.oasis.opendocument.text",
            headers={"Content-Disposition":
                     f'attachment; filename="ata-livro3-{expurgo_id}.odt"'})

    # ------------------------------------------- a ponte com o que já existia

    @app.route("/livro3/<int:registro_id>/minuta/do-rascunho/<int:rascunho_id>",
               methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def livro3_minuta_do_rascunho(registro_id: int, rascunho_id: int):
        """Traz para as minutas o que estava guardado em `rascunhos_de_tela`.

        POR QUE ISTO EXISTE, E É UM BOTÃO E NÃO UMA MIGRAÇÃO CALADA. Até hoje
        as duas minutas de cancelamento do Livro 3 — dos registros **1.198** e
        **1.243** — moravam na gaveta de rascunho de tela, que não tem
        situação nem descarte: a do 1.243 virou a AV-01 e **continuou lá**,
        como se ainda esperasse alguém.

        Mover isso sozinho, na abertura do banco, seria o sistema decidindo
        que aquele rascunho é uma minuta. **Quem decide é quem escreveu o
        texto**, e o rascunho fica onde está até alguém clicar — e continua lá
        depois, porque apagar o que outra tela guardou não é desta rota.
        """
        with db.connect() as con:
            r = banco(con).um(
                "SELECT * FROM rascunhos_de_tela WHERE id=%s",
                (rascunho_id,))
        if not r:
            abort(404)
        try:
            dados = json.loads(r["dados_json"] or "{}")
        except json.JSONDecodeError:
            dados = {}
        # O RASCUNHO DIZ `AVERBACAO`; a minuta fala a língua do livro, que é
        # `AV`. Traduzir aqui é o que evita um terceiro vocabulário.
        tipo = "AV" if str(dados.get("tipo") or "").upper().startswith("AVERB") \
            else str(dados.get("tipo") or "AV").upper()
        try:
            with db.transaction() as con:
                minuta_id = MIN.criar(
                    con, registro_id=registro_id, tipo=tipo,
                    teor=str(dados.get("teor") or ""), agora=db.now(),
                    origem=MIN.RASCUNHO_DE_TELA,
                    origem_chave=f"rascunhos_de_tela:{rascunho_id}",
                    observacao=r["titulo"], usuario=usuario_nome())
        except MIN.MinutaError as erro:
            flash(str(erro), "danger")
        else:
            audit("RA_MINUTA_CRIADA", "ra_minutas", minuta_id,
                  {"registro_id": registro_id, "origem": MIN.RASCUNHO_DE_TELA,
                   "rascunho_id": rascunho_id})
            flash("O rascunho virou minuta: agora ela tem situação, número "
                  "pretendido e descarte com motivo. O rascunho antigo ficou "
                  "onde estava.", "success")
        return redirect(url_for("livro3_registro", registro_id=registro_id))
