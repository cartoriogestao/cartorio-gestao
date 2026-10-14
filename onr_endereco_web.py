"""As telas da conferência do endereço — o que vai ao índice real do ONR.

O MÓDULO DE DOMÍNIO EXISTIA SEM TELA, e essa é a família de defeito que este
projeto mais repete: `onr_endereco_do_teor` propõe, confirma e descarta desde
15/09/2026, e as **1.443 fichas** da fila não tinham por onde ser conferidas. O
balcão não podia despachar a primeira.

**A TELA NÃO REPETE A REGRA DO DOMÍNIO.** Ela só *oferece*; quem *recusa* é
`onr_endereco_do_teor.py` — a mesma separação de `ri_onr_web` e de
`atribuicoes_web`.

**O QUE A TELA MOSTRA, E ISTO É O DESENHO INTEIRO:** as **duas versões**, lado
a lado — o que a ficha tem hoje e o que o teor diz —, e a **frase de onde cada
campo saiu**. Sem isso a conferência vira «confiar na máquina», e a decisão que
o oficial reservou para si (as divergentes não sobem até ele conferir) não teria
como ser tomada.

**CONFERIR E MANDAR SÃO COISAS DIFERENTES, E SÓ A PRIMEIRA MORA AQUI.** Este
módulo **grava o endereço na ficha** e não fala com o ONR: quem publica o
índice é `ri_onr_web`, com perfil de oficial. É a mesma separação da remessa da
CRA (conferir/receber) e das pendências da CENPROT (decidir/enviar).

**E SÃO DUAS PORTAS PARA O MESMO EXTRATOR — 16/09/2026.** A **fila**
(`/ri/onr/enderecos`) roda o extrator sobre as 1.443 de uma vez, e é o trabalho
de um dia; a **ficha do imóvel** ganhou o botão «o que o teor diz», que lê
**uma** matrícula e leva à conferência dela. As duas escrevem no mesmo lugar e
pela mesma função: a fila não tem régua própria, e nenhuma delas grava na
matrícula — quem grava é a conferência.
"""
from __future__ import annotations

import sqlite3

from flask import flash, redirect, render_template, request, url_for

import onr_endereco_do_teor as END

# QUEM CONFERE é quem atende — a mesma lista de `ri_onr_web`. **Conferir aqui
# escreve na ficha**, e escrever endereço na ficha é operação de balcão, como
# corrigir o bairro à mão; o que continua sendo do oficial é **publicar**, e
# isso não tem botão neste módulo.
QUEM_CONFERE = ("ADMIN", "MANAGER", "USER")


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """Pendura as telas do endereço no app já construído."""

    usuario_nome = app.extensions["usuario_nome"]

    def agora() -> str:
        return db.now()

    def _settings() -> dict:
        return dict(db.get_settings())

    # ─────────────────────────────────────────────── a fila da conferência

    @app.route("/ri/onr/enderecos")
    @roles_required(*QUEM_CONFERE)
    def ri_onr_enderecos():
        """A fila, na ordem da confiança: o que está pronto primeiro."""
        situacao = (request.values.get("situacao") or END.A_CONFERIR).strip()
        so_prontas = request.values.get("prontas") == "1"
        so_divergentes = request.values.get("divergentes") == "1"
        confianca = (request.values.get("confianca") or "").strip() or None
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            fila = END.listar(con, situacao=situacao or None,
                              somente_prontas=so_prontas,
                              somente_divergentes=so_divergentes,
                              confianca=confianca)
            contagem = END.contar(con)
        return render_template(
            "onr_enderecos.html", fila=fila, contagem=contagem,
            situacao=situacao, so_prontas=so_prontas,
            so_divergentes=so_divergentes, confianca=confianca or "",
            situacoes=END.SITUACOES, nome_da_situacao=END.NOME_DA_SITUACAO,
            rotulo_do_campo=END.ROTULO_DO_CAMPO)

    @app.route("/ri/onr/enderecos/gerar", methods=["POST"])
    @roles_required(*QUEM_CONFERE)
    def ri_onr_enderecos_gerar():
        """Roda o extrator sobre as fichas que não conseguem ir ao índice.

        **Só do OCR, ou o acervo inteiro** — decisão do oficial em 15/09/2026,
        e a caixa existe porque as duas coisas são úteis em horas diferentes:
        tudo nas 1.443 (o acervo ainda não conferido) e só o OCR depois de uma
        importação nova.
        """
        so_do_ocr = request.form.get("so_do_ocr") == "1"
        with db.transaction() as con:
            con.row_factory = sqlite3.Row
            feito = END.gerar(con, agora=agora(), settings=_settings(),
                              so_do_ocr=so_do_ocr)
        audit("ONR_ENDERECO_GERADO",
              f"lidas {feito['lidas']} · prontas {feito['prontas']} · "
              f"divergentes {feito['divergentes']} · "
              f"escopo {'só OCR' if so_do_ocr else 'todas as fichas'}")
        flash(
            f"O extrator leu {feito['lidas']} fichas: **{feito['prontas']}** "
            f"prontas para conferir, {feito['com_buraco']} com algum campo "
            f"faltando e {feito['divergentes']} em que o teor discorda da "
            f"ficha. **Nada foi gravado nas matrículas** — o que ele fez foi "
            f"proposta, e quem confirma é você.", "ok")
        return redirect(url_for("ri_onr_enderecos"))

    # ────────────────────────────────── o extrator, a partir de UMA ficha
    #
    # **A PORTA DA FILA NÃO BASTAVA, e isto é o defeito mais repetido desta
    # casa pelo lado de dentro.** A fila se abre de propósito e roda o extrator
    # sobre **1.443 fichas**; quem está na ficha de uma matrícula do OCR quer a
    # leitura **daquela** ficha, agora. O caminho já existia desde 15/09/2026 —
    # `onr_endereco_do_teor.propor_do_banco` — e **nenhuma tela o chamava**:
    # peça pronta que ninguém usa, que é a forma da `obter_selo`, da remessa da
    # CRA e de mais cinco neste projeto.
    #
    # **E O BOTÃO MORA NA FICHA**, em cima da linha do endereço, que é onde a
    # falta dele aparece: a ficha mostra «Endereço — —» e não oferecia nada.

    @app.route("/ri/onr/endereco/da-matricula/<int:matricula_id>",
               methods=["POST"])
    @roles_required(*QUEM_CONFERE)
    def ri_onr_endereco_da_matricula(matricula_id: int):
        """Lê o teor **de uma ficha** e leva direto à conferência dela.

        **É POST, E NÃO GET, PORQUE ESCREVE.** Criar a proposta é escrita no
        banco, e nesta casa um GET não abre transação de escrita — é a mesma
        razão de o botão de gravar o CNM ser formulário, ali ao lado na ficha.

        **E A FICHA SEM TEOR É RECUSADA COM FRASE, não com linha vazia na
        fila.** Quem recusa é o domínio (`propor_do_banco`); aqui só se leva a
        resposta de volta para a ficha, que é onde quem clicou estava.
        """
        # **A FICHA QUE JÁ TEVE PROPOSTA DECIDIDA NÃO GANHA OUTRA — e o botão
        # diz isso em vez de ler e jogar fora.** O `guardar` já garante que a
        # decisão não se perde (`UNIQUE(matricula_id)` mais o
        # `WHERE situacao=A_CONFERIR`), e é por isso que ele devolve o `id` da
        # proposta que já existe. O que faltava era **dizer**: sem esta
        # conferência, a rota leria o teor, o resultado sumiria em silêncio, e a
        # tela mostraria a proposta VELHA como se fosse a leitura que o operador
        # acabou de pedir — que é o carimbo que mente na sua forma mais direta.
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            ja = con.execute(
                "SELECT id, situacao, decidido_por, decidido_em, motivo "
                "FROM ri_onr_enderecos WHERE matricula_id=?",
                (int(matricula_id),)).fetchone()
        if ja and ja["situacao"] != END.A_CONFERIR:
            quando = str(ja["decidido_em"] or "")[:16]
            quem = ja["decidido_por"] or "alguém"
            flash(
                f"Esta ficha já teve a proposta de endereço "
                f"{END.NOME_DA_SITUACAO.get(ja['situacao'], ja['situacao']).lower()}"
                f" por {quem}{' em ' + quando if quando else ''}. "
                f"**Uma proposta por matrícula, e a decisão de quem conferiu "
                f"vale mais que uma segunda leitura** — nada foi refeito aqui. "
                f"A proposta está em tela, com o motivo.", "warning")
            return redirect(url_for("ri_onr_endereco", proposta_id=ja["id"]))
        try:
            with db.transaction() as con:
                con.row_factory = sqlite3.Row
                proposta = END.propor_do_banco(con, matricula_id,
                                               settings=_settings())
                proposta_id = END.guardar(con, proposta, agora=agora())
        except END.EnderecoError as erro:
            # A recusa volta para a FICHA, e não para a fila: quem clicou estava
            # na ficha, e mandá-lo para outra tela depois de uma recusa é
            # tirar-lhe o lugar onde ele estava.
            flash(str(erro), "danger")
            return redirect(url_for("ri_ficha", matricula_id=matricula_id))
        audit("ONR_ENDERECO_PROPOSITO",
              f"matrícula {matricula_id} · proposta {proposta_id} · "
              + ("pronta para conferir" if proposta["pode_enviar"]
                 else "faltam " + ", ".join(proposta["faltam"])))
        return redirect(url_for("ri_onr_endereco", proposta_id=proposta_id))

    # ─────────────────────────────────────────────── a ficha da proposta

    @app.route("/ri/onr/endereco/<int:proposta_id>")
    @roles_required(*QUEM_CONFERE)
    def ri_onr_endereco(proposta_id: int):
        """Uma proposta: as duas versões à vista, e a frase de onde saiu."""
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            p = END.ler(con, proposta_id)
            atual = None
            if p:
                atual = con.execute(
                    "SELECT id, numero, livro, tipo_ficha, origem, teor, "
                    "       logradouro, numero_predial, bairro, cidade, uf, "
                    "       cep, rural_urbano, area_valor, area_unidade, "
                    "       tipo_imovel "
                    "  FROM ri_matriculas WHERE id=?",
                    (int(p["matricula_id"]),)).fetchone()
        if not p:
            flash("Esta proposta de endereço não existe.", "danger")
            return redirect(url_for("ri_onr_enderecos"))
        return render_template(
            "onr_endereco.html", p=p, atual=dict(atual) if atual else {},
            campos=END.CAMPOS, rotulo_do_campo=END.ROTULO_DO_CAMPO,
            nome_da_situacao=END.NOME_DA_SITUACAO,
            texto_do_teor=END.texto_do_teor(
                dict(atual).get("teor") if atual else None))

    @app.route("/ri/onr/endereco/<int:proposta_id>/confirmar",
               methods=["POST"])
    @roles_required(*QUEM_CONFERE)
    def ri_onr_endereco_confirmar(proposta_id: int):
        """Grava na ficha o que foi conferido. **Na mesma transação da marca.**

        Os **ajustes** são o que a pessoa corrigiu na tela: só os campos que
        vieram no formulário, e só os que o domínio decide se cabe gravar. O
        que a ficha já tinha **não é sobrescrito** — quem digitou vale mais que
        a proposta —, e o que ficou de fora volta na resposta para a tela
        dizer qual foi.
        """
        ajustes = {campo: request.form.get(campo)
                   for campo in END.CAMPOS_QUE_A_CONFERENCIA_GRAVA
                   if request.form.get(campo) is not None}
        try:
            with db.transaction() as con:
                con.row_factory = sqlite3.Row
                feito = END.confirmar(con, proposta_id, agora=agora(),
                                      usuario=usuario_nome(),
                                      ajustes=ajustes)
        except END.EnderecoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ri_onr_endereco", proposta_id=proposta_id))
        audit("ONR_ENDERECO_CONFIRMADO",
              f"matrícula {feito['matricula_numero']} · "
              f"{len(feito['gravados'])} campos")
        if feito["gravados"]:
            gravados = ", ".join(
                END.ROTULO_DO_CAMPO.get(c, c) for c in feito["gravados"])
            flash(f"Gravado na matrícula {feito['matricula_numero']}: "
                  f"{gravados}.", "ok")
        else:
            flash(f"A matrícula {feito['matricula_numero']} já tinha todos "
                  f"estes campos preenchidos — nada foi sobrescrito.", "ok")
        if feito["preservados"]:
            # **O CAMPO QUE FICOU DE FORA NÃO SOME CALADO.** Ele é a diferença
            # entre o que a máquina leu e o que uma pessoa escreveu, e é
            # justamente onde a proposta poderia estar errada.
            ficaram = ", ".join(
                END.ROTULO_DO_CAMPO.get(c, c) for c in feito["preservados"])
            flash(f"Não foram tocados, porque a ficha já tinha outro valor: "
                  f"{ficaram}. Se o certo for o que o teor diz, corrija na "
                  f"própria ficha.", "warning")
        return redirect(url_for("ri_onr_enderecos"))

    @app.route("/ri/onr/endereco/<int:proposta_id>/descartar",
               methods=["POST"])
    @roles_required(*QUEM_CONFERE)
    def ri_onr_endereco_descartar(proposta_id: int):
        """Tira a proposta da fila. **Exige motivo escrito.**"""
        try:
            with db.transaction() as con:
                END.descartar(con, proposta_id,
                              motivo=(request.form.get("motivo") or ""),
                              agora=agora(), usuario=usuario_nome())
        except END.EnderecoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ri_onr_endereco", proposta_id=proposta_id))
        audit("ONR_ENDERECO_DESCARTADO", f"proposta {proposta_id}")
        flash("Proposta descartada, com o motivo registrado. **A ficha não "
              "foi tocada** — ela continua como estava.", "ok")
        return redirect(url_for("ri_onr_enderecos"))
