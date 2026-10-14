"""As telas do ONR — o indicador real, o edital e a fila.

A TELA NÃO REPETE A REGRA DO DOMÍNIO. Ela só *oferece*; quem *recusa* é
`ri_onr_central.py`.

**CONFERIR E ENVIAR SÃO DOIS BOTÕES**, como em todas as Centrais desta casa: o
indicador real **publica o dono do imóvel no índice nacional**, e o edital
**faz o prazo correr**.

**E ENVIAR NÃO É DO BALCÃO.** Conferir e olhar a fila são de quem atende;
enviar, publicar e cancelar são do oficial e do gerente.

**A FILA SE CONFERE, e não se supõe.** O ONR recebe e processa depois — por
isso há um botão que pergunta a ele o que aconteceu, e a lista separa
«enviado» de «aceito».
"""
from __future__ import annotations

import sqlite3

from flask import flash, redirect, render_template, request, url_for

import centrais_cred as CRED
import onr_api as API
import ri_onr_central as ONR
import ri_onr_central_schema as ESQ

QUEM_CONFERE = ("ADMIN", "MANAGER", "USER")
QUEM_ENVIA = ("ADMIN", "MANAGER")

RECUSAS_DO_BALCAO = (ONR.OnrRIError, API.OnrError, CRED.CredencialError)


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """Pendura as telas do ONR no app já construído."""

    usuario_nome = app.extensions["usuario_nome"]

    def agora() -> str:
        return db.now()

    def _cns() -> str:
        return str(db.get_setting("ri_cns", "") or "").strip() \
            or str(db.get_setting("serventia_cns", "") or "").strip()

    def _sv() -> dict:
        return dict(db.get_settings())

    # ----------------------------------------------------------- o painel

    @app.route("/ri/onr")
    @roles_required(*QUEM_CONFERE)
    def ri_onr_painel():
        """O que já subiu, o que falta e o estado da ligação."""
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            lista = ONR.envios(con)
            faltam = ONR.a_enviar(con, limite=100)
        return render_template(
            "ri_onr_central.html", envios=lista, faltam=faltam, cns=_cns(),
            ambiente=ONR.ambiente(), base=API.base_do_ambiente(),
            situacoes=ESQ.SITUACOES, especies=ESQ.ESPECIES,
            nome_da_especie=ESQ.NOME_DA_ESPECIE,
            tem_credencial=API.tem_credencial(),
            arquivo_da_credencial=str(CRED.caminho(CRED.ONR)))

    @app.route("/ri/onr/testar", methods=["POST"])
    @roles_required(*QUEM_CONFERE)
    def ri_onr_testar():
        """Pergunta ao ONR se a credencial vale. **Não afirma nada além.**

        Usa `/v1/auth/validacao`, que é a única operação que prova o token sem
        mexer em indicador, protocolo ou edital.
        """
        try:
            r = API.esta_no_ar()
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            if r["no_ar"]:
                flash(f"O ONR aceitou a credencial da serventia "
                      f"(HTTP {r['status']}).", "ok")
            else:
                flash(f"O ONR respondeu HTTP {r['status']}: {r['resposta']}",
                      "warning")
        return redirect(url_for("ri_onr_painel"))

    @app.route("/ri/onr/fila", methods=["POST"])
    @roles_required(*QUEM_CONFERE)
    def ri_onr_fila():
        """Pergunta ao ONR o que aconteceu com o que subiu.

        **Enviar não é ser aceito**, e é esta chamada que separa as duas.
        """
        try:
            r = ONR.conferir_a_fila(db, agora=agora())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            flash(f"A fila do ONR devolveu {r['conferidos']} linhas, e "
                  f"{r['mudaram']} envios desta casa mudaram de situação.",
                  "ok")
        return redirect(url_for("ri_onr_painel"))

    # -------------------------------------------------- o indicador real

    @app.route("/ri/onr/indicador/<int:matricula_id>", methods=["GET", "POST"])
    @roles_required(*QUEM_CONFERE)
    def ri_onr_indicador(matricula_id: int):
        """O que iria para o índice real. **NÃO GRAVA E NÃO ENVIA.**"""
        situacao = (request.values.get("situacao_construcao") or "").strip()
        tipo = (request.values.get("tipo_imovel") or "").strip()
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            try:
                montado = ONR.montar_indicador(
                    con, matricula_id, cns=_cns(),
                    situacao_construcao=situacao or None,
                    tipo_imovel=tipo or None)
            except RECUSAS_DO_BALCAO as erro:
                flash(str(erro), "danger")
                return redirect(url_for("ri_onr_painel"))
            ja = ONR.envios_da_matricula(con, matricula_id)
        return render_template(
            "ri_onr_indicador.html", c=montado, ja=ja,
            matricula_id=matricula_id, situacao_escolhida=situacao,
            tipo_escolhido=tipo, base=API.base_do_ambiente(),
            ambiente=ONR.ambiente(),
            situacoes_de_construcao=API.SITUACOES_DE_CONSTRUCAO,
            tipos_de_imovel=API.TIPOS_DE_IMOVEL,
            tem_credencial=API.tem_credencial())

    @app.route("/ri/onr/indicador/<int:matricula_id>/enviar",
               methods=["POST"])
    @roles_required(*QUEM_ENVIA)
    def ri_onr_indicador_enviar(matricula_id: int):
        """Manda o indicador real ao ONR. **É a única rota que publica o
        índice.**"""
        try:
            feito = ONR.enviar_indicador(
                db, matricula_id, cns=_cns(), agora=agora(),
                usuario=usuario_nome(),
                situacao_construcao=(
                    request.form.get("situacao_construcao") or None),
                tipo_imovel=(request.form.get("tipo_imovel") or None))
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            audit("ri_onr_indicador_enviado",
                  f"matrícula {matricula_id} · {feito['identificador']}")
            flash(f"O indicador real subiu ao ONR. Identificador: "
                  f"{feito['identificador'] or '—'}. **Enviado não é aceito** "
                  f"— confira a fila daqui a pouco.", "ok")
        return redirect(url_for("ri_onr_indicador",
                                matricula_id=matricula_id))

    @app.route("/ri/onr/envio/<int:envio_id>/atualizar", methods=["POST"])
    @roles_required(*QUEM_ENVIA)
    def ri_onr_indicador_atualizar(envio_id: int):
        """Corrige no ONR o que ja subiu, **sem queimar o identificador**."""
        try:
            ONR.atualizar_indicador(
                db, envio_id, cns=_cns(), agora=agora(),
                usuario=usuario_nome(),
                situacao_construcao=(
                    request.form.get("situacao_construcao") or None),
                tipo_imovel=(request.form.get("tipo_imovel") or None))
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            audit("ri_onr_indicador_atualizado", f"envio {envio_id}")
            flash("O ONR atualizou o indicador com os dados de agora. O "
                  "identificador continua o mesmo.", "ok")
        return redirect(url_for("ri_onr_painel"))

    @app.route("/ri/onr/envio/<int:envio_id>/porque", methods=["POST"])
    @roles_required(*QUEM_CONFERE)
    def ri_onr_porque(envio_id: int):
        """Pergunta ao ONR **por que** ele recusou aquela linha."""
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            envio = ONR.ler_envio(con, envio_id)
        if not envio:
            flash("Envio não encontrado.", "danger")
            return redirect(url_for("ri_onr_painel"))
        try:
            detalhe = ONR.porque_a_fila_recusou(envio)
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            flash(f"O ONR respondeu sobre este envio: {detalhe}", "ok")
        return redirect(url_for("ri_onr_painel"))

    @app.route("/ri/onr/la", methods=["POST"])
    @roles_required(*QUEM_CONFERE)
    def ri_onr_la():
        """O que o ONR tem, do lado dele. **Se divergir, quem manda é lá.**"""
        try:
            lista = ONR.o_que_o_onr_tem()
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            quantos = len(lista) if isinstance(lista, list) else "?"
            flash(f"O ONR tem {quantos} indicadores desta serventia.", "ok")
        return redirect(url_for("ri_onr_painel"))

    # -------------------------------------------------------- o edital

    @app.route("/ri/onr/edital/<int:processo_id>", methods=["GET", "POST"])
    @roles_required(*QUEM_CONFERE)
    def ri_onr_edital(processo_id: int):
        """O edital do usucapião, como ele iria à Central."""
        tipo = (request.values.get("tipo_edital") or "").strip()
        texto = (request.values.get("texto") or "").strip()
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            try:
                montado = ONR.montar_edital(
                    con, processo_id, sv=_sv(), tipo_edital=tipo,
                    texto=texto or None)
            except RECUSAS_DO_BALCAO as erro:
                flash(str(erro), "danger")
                return redirect(url_for("ri_onr_painel"))
            ja = [e for e in ONR.envios(con, especie=ESQ.EDITAL)
                  if e.get("processo_id") == processo_id]
        return render_template(
            "ri_onr_edital.html", c=montado, ja=ja, processo_id=processo_id,
            tipo_escolhido=tipo, texto=texto, base=API.base_do_ambiente(),
            ambiente=ONR.ambiente(), tem_credencial=API.tem_credencial())

    @app.route("/ri/onr/edital/<int:processo_id>/tipos", methods=["POST"])
    @roles_required(*QUEM_CONFERE)
    def ri_onr_edital_tipos(processo_id: int):
        """Traz da Central a lista dos tipos de edital.

        **A casa não escreve esta lista.** Ela vem do ONR, e escrevê-la no
        código seria a lista à mão que envelhece na tarde em que se escreve.
        """
        try:
            tipos = API.tipos_de_edital()
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            flash(f"O ONR devolveu os tipos de edital: {tipos}", "ok")
        return redirect(url_for("ri_onr_edital", processo_id=processo_id))

    @app.route("/ri/onr/edital/<int:processo_id>/publicar", methods=["POST"])
    @roles_required(*QUEM_ENVIA)
    def ri_onr_edital_publicar(processo_id: int):
        """Publica o edital na Central. **É a chamada que faz o prazo correr.**"""
        try:
            feito = ONR.publicar_edital(
                db, processo_id, sv=_sv(),
                tipo_edital=(request.form.get("tipo_edital") or ""),
                texto=(request.form.get("texto") or None),
                agora=agora(), usuario=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            audit("ri_onr_edital_publicado",
                  f"usucapião {processo_id} · edital {feito['numero']}")
            flash(f"O edital foi disponibilizado na Central. Número: "
                  f"{feito['numero'] or '—'}. **O prazo conta do primeiro dia "
                  f"útil depois da disponibilização** — art. 755, § 1º.", "ok")
        return redirect(url_for("ri_onr_edital", processo_id=processo_id))

    @app.route("/ri/onr/envio/<int:envio_id>/cancelar", methods=["POST"])
    @roles_required(*QUEM_ENVIA)
    def ri_onr_edital_cancelar(envio_id: int):
        """Cancela o edital **na Central**. Não desfaz o usucapião."""
        try:
            ONR.cancelar_edital(db, envio_id,
                                motivo=(request.form.get("motivo") or ""),
                                agora=agora(), usuario=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            audit("ri_onr_edital_cancelado", f"envio {envio_id}")
            flash("O edital foi cancelado na Central. **O processo de "
                  "usucapião não foi tocado.**", "ok")
        return redirect(url_for("ri_onr_painel"))
