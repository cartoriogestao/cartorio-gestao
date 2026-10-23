"""As telas da leitura de documentos do Registro Civil — `rc_leitura_documentos`.

O balcão anexa os documentos do registro (DNV ou DO, documentos de identidade,
residência), a IA lê, e a tela mostra o que foi lido AO LADO do que não fecha.
O botão final não lavra: cria o rascunho da tela de assento novo, preenchido,
e é ali que o escrevente confere com o original e lavra, como sempre.
"""
from __future__ import annotations

from pathlib import Path

from flask import flash, redirect, render_template, request, url_for

import rc_leitura_documentos as LEIT
import tetos_de_entrada as TETO
from storage import save_upload

#: QUEM LÊ DOCUMENTOS DO REGISTRO CIVIL (M6 do LS03; LX13, 19/10/2026). As
#: rotas exigiam só login: o AUDITOR, que não lavra, abria qualquer leitura pelo
#: número e via DNV e DO inteiras — causa da morte, CPF, filiação. Lê quem
#: lavra o assento; o AUDITOR confere o assento lavrado, na tela dele.
QUEM_LE = ("ADMIN", "MANAGER", "USER")
#: Quem vê a leitura de OUTRA pessoa: quem responde pela casa. O balcão vê as
#: que ele mesmo abriu (`LEIT.e_de`).
QUEM_VE_TODAS = ("ADMIN", "MANAGER")


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    """Pendura as telas da leitura de documentos no app já construído."""

    usuario_nome = app.extensions["usuario_nome"]
    usuario_papel = app.extensions["usuario_papel"]

    def pasta_de_dados() -> Path:
        return Path(app.config["DATA_DIR"])

    def usuario_id() -> int:
        from flask import session
        return int(session.get("user_id") or 0)

    def _pode_ver(con, leitura: dict) -> bool:
        """A leitura de outra pessoa só para ADMIN e MANAGER. SÓ LÊ."""
        if usuario_papel() in QUEM_VE_TODAS:
            return True
        return LEIT.e_de(con, leitura, nome=usuario_nome(), user_id=usuario_id())

    def _ler_e_guardar(especie: str, arquivos_enviados: list,
                       tardio: bool = False) -> tuple[int | None, str]:
        """Guarda os anexos na leitura e manda ler. Devolve (leitura, erro).
        É o mesmo caminho para as duas portas: a tela do assento (12/10/2026,
        «vamos deixar tudo na página de preenchimento do assento») e a antiga."""
        import agente_provedores as AP
        if not arquivos_enviados:
            return None, ("Anexe pelo menos um arquivo — o PDF digitalizado ou as fotos "
                          "dos documentos.")
        if not AP.tem_chave(pasta_de_dados(), LEIT.PROVEDOR):
            return None, ("A chave da API da Claude não está configurada — a leitura não "
                          "tem com quem falar. Ela se configura em Ajuda → configurar.")
        # O TETO DO DIA (B5 do LS03), conferido antes de guardar e de ler: a
        # leitura que passou dele não abre linha nem sobe página.
        import ia_uso as USO
        with db.connect() as con:
            passou = USO.passou_do_teto(con, "rc_leitura")
        if passou:
            return None, passou
        por = usuario_nome()
        try:
            with db.transaction() as con:
                leitura_id = LEIT.abrir(con, especie=especie, agora=LEIT.agora(), por=por)
        except LEIT.LeituraError as recusa:
            return None, str(recusa)
        return _ler_e_concluir(especie, leitura_id, arquivos_enviados, tardio)

    def _ler_e_concluir(especie: str, leitura_id: int, arquivos_enviados: list,
                        tardio: bool = False) -> tuple[int, str]:
        import agente_provedores as AP
        pasta_arquivos = (app.extensions["archive_root"]() / "rcpn" / "leituras"
                          / f"leitura_{leitura_id}")
        arquivos = []
        for f in arquivos_enviados:
            info = save_upload(f, pasta_arquivos)
            anexo_id = db.add_attachment("RC_LEITURA", leitura_id, info, usuario_id(),
                                         "documento anexado para a leitura")
            arquivos.append({"caminho": info["stored_path"], "nome": info["original_name"],
                             "attachment_id": anexo_id, "sha256": info["sha256"]})
        with db.connect() as con:
            em_uso = LEIT.modelos(con)
        lido, erro = None, ""
        try:
            # A REDE, FORA DE TRANSAÇÃO: um minuto de leitura segurando o
            # `BEGIN IMMEDIATE` poria todo outro balcão no `busy_timeout`.
            import functools

            import agente_provedores as AP2
            # O REGISTRO DO USO DE IA (LF01) vai preso ao transporte: a leitura
            # chama a IA em várias linhas de execução, e todas levam a mesma
            # finalidade e a mesma leitura. As imagens sobem sem máscara.
            conversar = functools.partial(
                AP2.conversar, modulo="rc_leitura_web", finalidade="rc_leitura",
                usuario=usuario_nome(), atribuicao="RCPN",
                referencia=f"rc_leituras:{leitura_id}", mascarado=False)
            lido = LEIT.ler(conversar, pasta_de_dados(), em_uso, arquivos,
                           especie=especie)
        except LEIT.LeituraError as recusa:
            erro = str(recusa)
        except AP.AgenteError as falha:
            erro = f"A IA não respondeu: {falha}"
        with db.transaction() as con:
            LEIT.concluir(con, leitura_id, arquivos=arquivos, lido=lido, erro=erro,
                          tardio=tardio)
        audit("RC_LEITURA_DE_DOCUMENTOS", "rc_leituras", leitura_id,
              {"especie": especie, "arquivos": [a["nome"] for a in arquivos],
               "registro_tardio": tardio or None, "erro": erro or None})
        return leitura_id, erro

    @app.route("/rcpn/leitura", methods=["GET", "POST"])
    @login_required
    @roles_required(*QUEM_LE)
    def rcpn_leitura():
        """O histórico das leituras. Desde 12/10/2026 a leitura se pede NA TELA
        DO ASSENTO (e na da habilitação); o POST daqui continua respondendo
        para quem tiver o endereço guardado."""
        import agente_provedores as AP
        if request.method == "POST":
            especie = (request.form.get("especie") or "").upper()
            leitura_id, erro = _ler_e_guardar(
                especie, [f for f in request.files.getlist("arquivos") if f and f.filename])
            if leitura_id is None:
                flash(erro, "danger")
                return redirect(url_for("rcpn_leitura"))
            if erro:
                flash(f"A leitura não terminou: {erro}", "danger")
            return redirect(url_for("rcpn_leitura_ficha", leitura_id=leitura_id))

        with db.connect() as con:
            leituras = LEIT.lista(con, so_de=None if usuario_papel() in QUEM_VE_TODAS
                                  else (usuario_nome(), usuario_id()))
            em_uso = LEIT.modelos(con)
        return render_template("rc_leitura.html", leituras=leituras, modelos=em_uso,
                               especies=LEIT.ESPECIES_LIDAS, tipos=LEIT.TIPOS,
                               rotulos=LEIT.ROTULO_DA_ESPECIE,
                               base_legal=LEIT.BASE_LEGAL, o_que_sai=LEIT.O_QUE_SAI,
                               zdr=LEIT.ZERO_DATA_RETENTION,
                               teto_paginas=TETO.valor("ia_paginas"),
                               tem_chave=AP.tem_chave(pasta_de_dados(), LEIT.PROVEDOR))

    def _tela_vazia_da_especie(especie: str) -> str:
        if especie == "HABILITACAO":
            return url_for("rcpn_habilitacao_nova")
        slug = {"NASCIMENTO": "nascimento", "OBITO": "obito", "CASAMENTO": "casamento"}.get(especie)
        return url_for("rcpn_assento_novo", especie_url=slug) if slug else url_for("rcpn_assento_novo")

    @app.route("/rcpn/leitura/preencher", methods=["POST"])
    @login_required
    @roles_required(*QUEM_LE)
    def rcpn_leitura_preencher():
        """O botão da tela do assento: junta os anexos, lê, e devolve A MESMA
        TELA preenchida (pelo rascunho), com o que não fecha à vista.
        12/10/2026, o oficial: «não tem pq ter dois lugares para importar
        assentos pela leitura».  ESCREVE só a leitura, os anexos e o rascunho —
        não lavra nada."""
        especie = (request.form.get("especie") or "").upper()
        if especie not in LEIT.ESPECIES_LIDAS:
            flash("A leitura de documentos atende nascimento, óbito, casamento e habilitação de casamento.", "danger")
            return redirect(url_for("rcpn_assento_novo"))
        # A MARCA DO REGISTRO TARDIO (21/10/2026): sem ela a leitura exige a
        # DNV; com ela, monta o nascimento pelos documentos de identidade.
        tardio = (especie == "NASCIMENTO"
                  and (request.form.get("registro_tardio") or "") in ("1", "on", "SIM"))
        leitura_id, erro = _ler_e_guardar(
            especie, [f for f in request.files.getlist("arquivos") if f and f.filename],
            tardio)
        if leitura_id is None:
            flash(erro, "danger")
            return redirect(_tela_vazia_da_especie(especie))
        if erro:
            flash(f"A leitura não terminou: {erro} Os anexos ficaram guardados na leitura nº {leitura_id}.",
                  "danger")
            return redirect(_tela_vazia_da_especie(especie))
        try:
            with db.transaction() as con:
                rascunho_id = LEIT.para_rascunho(con, leitura_id, agora=LEIT.agora(), por=usuario_nome())
        except LEIT.LeituraError as recusa:
            flash(str(recusa), "danger")
            return redirect(_tela_vazia_da_especie(especie))
        audit("RC_LEITURA_PARA_RASCUNHO", "rc_leituras", leitura_id, {"rascunho_id": rascunho_id,
                                                                       "porta": "tela do assento"})
        flash("Os campos foram preenchidos pela leitura dos anexos. Confira cada um com os "
              "documentos originais antes de lavrar — a leitura adiantou a digitação, e não decidiu "
              "nada.", "warning")
        return redirect(_url_do_rascunho(especie, rascunho_id))

    @app.route("/rcpn/requerimento-tardio/imprimir", methods=["POST"])
    @login_required
    @roles_required(*QUEM_LE)
    def rcpn_requerimento_tardio_imprimir():
        """O requerimento do registro tardio, preenchido com o que está NA
        TELA de preencher, para imprimir e os comparecentes assinarem — antes
        de conferir e de lavrar. 21/10/2026, o oficial: «receber a
        documentação e preencher o requerimento para imprimirmos para os
        comparecentes assinarem». SÓ LÊ o formulário; não grava nada."""
        import datetime as _dt

        import rc_assento as RC
        form = {k: v for k, v in request.form.items() if k != "csrf_token"}
        hoje = _dt.date.today()
        regra = RC.regra_das_testemunhas_do_tardio(
            {"data_fato": form.get("data_fato"), "dnv": form.get("dnv"),
             "data_ato": hoje.isoformat()},
            [{"papel": "REGISTRADO",
              "data_nascimento": form.get("pessoa_data_nascimento")}])
        return render_template("rcpn_requerimento_tardio_imprimir.html", form=form,
                               regra=regra, hoje_br=hoje.strftime("%d/%m/%Y"))

    def _url_do_rascunho(especie: str, rascunho_id: int) -> str:
        """A tela que o rascunho abre: o assento novo da espécie, ou a
        habilitação — o casamento desta casa começa por ela."""
        if especie == "HABILITACAO":
            return url_for("rcpn_habilitacao_nova", rascunho_id=rascunho_id)
        slug = {"NASCIMENTO": "nascimento", "OBITO": "obito", "CASAMENTO": "casamento"}.get(especie)
        return url_for("rcpn_assento_novo", especie_url=slug, rascunho_id=rascunho_id)

    @app.route("/rcpn/leitura/<int:leitura_id>")
    @login_required
    @roles_required(*QUEM_LE)
    def rcpn_leitura_ficha(leitura_id: int):
        """O que foi lido, documento por documento, e o que não fecha.

        O NÚMERO É SEQUENCIAL, e por isso não basta como chave: o balcão abre a
        que é dele (M6 do LS03). A de outra pessoa responde como a que não
        existe — dizer «existe, mas não é sua» já conta que houve um registro."""
        with db.connect() as con:
            leitura = LEIT.uma(con, leitura_id)
            if leitura is not None and not _pode_ver(con, leitura):
                leitura = None
        if leitura is None:
            flash(f"Não há leitura nº {leitura_id}.", "danger")
            return redirect(url_for("rcpn_leitura"))
        abrir_url = (_url_do_rascunho(leitura["especie"], leitura["rascunho_id"])
                     if leitura.get("rascunho_id") else None)
        return render_template("rc_leitura_ficha.html", leitura=leitura, tipos=LEIT.TIPOS,
                               base_legal=LEIT.BASE_LEGAL, zdr=LEIT.ZERO_DATA_RETENTION,
                               rotulos=LEIT.ROTULO_DA_ESPECIE, abrir_url=abrir_url)

    @app.route("/rcpn/leitura/<int:leitura_id>/rascunho", methods=["POST"])
    @login_required
    @roles_required(*QUEM_LE)
    def rcpn_leitura_rascunho(leitura_id: int):
        """A leitura vira rascunho do assento novo, e a tela de lavrar abre.
        Só a de quem pode vê-la: o rascunho mostra o que a leitura leu."""
        with db.connect() as con:
            leitura = LEIT.uma(con, leitura_id)
            if leitura is not None and not _pode_ver(con, leitura):
                leitura = None
        if leitura is None:
            flash(f"Não há leitura nº {leitura_id}.", "danger")
            return redirect(url_for("rcpn_leitura"))
        try:
            with db.transaction() as con:
                rascunho_id = LEIT.para_rascunho(con, leitura_id, agora=LEIT.agora(),
                                                 por=usuario_nome())
                especie = LEIT.uma(con, leitura_id)["especie"]
        except LEIT.LeituraError as recusa:
            flash(str(recusa), "danger")
            return redirect(url_for("rcpn_leitura_ficha", leitura_id=leitura_id))
        audit("RC_LEITURA_PARA_RASCUNHO", "rc_leituras", leitura_id,
              {"rascunho_id": rascunho_id})
        flash("O rascunho está aberto abaixo. Confira cada campo com os documentos "
              "originais antes de lavrar — a leitura adiantou a digitação, e não decidiu "
              "nada.", "warning")
        return redirect(_url_do_rascunho(especie, rascunho_id))
