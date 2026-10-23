"""As rotas da revisão das transcrições — ver `revisao_transcricao.py` (a
revisão de uma ficha e a regra da certidão) e `revisao_transcricao_lote.py`
(os livros antigos em lote).

O BOTÃO SÓ LÊ QUANDO ALGUÉM CLICA. Ele mora no quadro da certidão, na ficha da
matrícula — cada leitura custa, e quem decide gastar é quem está emitindo (a
régua da sugestão de ônus, 15/10/2026). Nenhuma rota daqui emite certidão nem
muda o teor: quem emite é `ri_emitir_certidao`, chamando `conferir_para_
emitir`, e quem corrige o texto é o caminho de correção de sempre.

A AUDITORIA LEVA SÓ IDS, CONTAGENS E A GRAVIDADE — nunca o texto da ficha nem o
que a IA leu (o pedido do LH11).
"""
from __future__ import annotations

from pathlib import Path

from flask import abort, flash, jsonify, redirect, render_template, request, url_for

import revisao_transcricao as RT
import revisao_transcricao_lote as RTL
import ri_digitalizacao as RDIGI
from bd_nativo import banco
from seguranca_web import numero_digitado

#: O teto de custo que a tela aceita — acima disto é engano de digitação.
CUSTO_MAIS_ALTO = 1000.0


def registrar_rotas(app, db, login_required, roles_required, audit):
    usuario_nome = app.extensions["usuario_nome"]

    def pasta() -> Path:
        return Path(app.config["DATA_DIR"])

    def raiz() -> Path:
        return RDIGI.raiz_arquivos(db)

    @app.context_processor
    def _revisao_da_transcricao_na_tela() -> dict:
        """O quadro da certidão na ficha, e a configuração na tela de
        Configurações. SÓ LÊ — a tela nunca cria a tabela."""
        try:
            onde = request.endpoint or ""
        except RuntimeError:
            return {}
        try:
            if onde == "ri_ficha":
                mid = (request.view_args or {}).get("matricula_id")
                if not isinstance(mid, int):
                    return {}
                with db.connect() as con:
                    return {"transcricao_painel": RT.painel(con, pasta(), raiz(), mid)}
            if onde == "settings":
                with db.connect() as con:
                    return {"revisao_transcricao_cfg": RT.configuracao(con)
                            | {"padrao_paginas": RT.TETO_DE_PAGINAS_POR_RODADA,
                               "padrao_custo": RT.TETO_DE_CUSTO_POR_RODADA}}
        except Exception:                           # noqa: BLE001 — o quadro some, a tela abre
            app.logger.warning("O quadro da revisão da transcrição não abriu em %s.", onde,
                               exc_info=True)
        return {}

    # ------------------------------------------------------- uma ficha

    @app.route("/registro-imoveis/<int:matricula_id>/transcricao/revisar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def ri_transcricao_revisar(matricula_id: int):
        volta = url_for("ri_ficha", matricula_id=matricula_id) + "#certidao-transcricao"
        with db.connect() as con:
            if RT.no_sandbox(con):
                flash("No sistema de teste (SANDBOX) a revisão por IA não existe — ordem "
                      "do oficial. Confira a transcrição contra a página à mão.", "warning")
                return redirect(volta)
            if not RT.ligada(con, pasta()):
                flash("A revisão por IA não está ligada nesta instalação (falta a chave do "
                      "provedor, ou ela foi desligada). Confira a transcrição contra a "
                      "página à mão.", "warning")
                return redirect(volta)
        try:
            with db.transaction() as con:
                rid, nova = RT.pedir(con, matricula_id, raiz=raiz(), usuario=usuario_nome())
        except RT.TranscricaoError as erro:
            flash(str(erro), "danger")
            return redirect(volta)
        if nova:
            audit("RI_TRANSCRICAO_REVISAO_PEDIDA", "ri_transcricao_revisoes", rid,
                  {"matricula_id": matricula_id})
            RT.ler_em_segundo_plano(db.db_path, pasta(), rid, raiz=raiz())
            flash("A IA está conferindo a transcrição contra as páginas escaneadas. Em um "
                  "ou dois minutos o resultado aparece no quadro da certidão.", "info")
        else:
            flash("Este texto, com estas páginas, já foi revisado (ou está sendo): o "
                  "resultado está no quadro da certidão, e não se paga de novo.", "info")
        return redirect(volta)

    @app.route("/registro-imoveis/<int:matricula_id>/transcricao/andamento")
    @login_required
    def ri_transcricao_andamento(matricula_id: int):
        """Para a tela saber quando recarregar. SÓ LÊ."""
        with db.connect() as con:
            try:
                r = RT.vigente(con, raiz(), matricula_id)["ultima"]
            except RT.TranscricaoError:
                abort(404)
        if r is None:
            return jsonify({"situacao": None})
        return jsonify({"id": r["id"], "situacao": r["situacao"]})

    @app.route("/registro-imoveis/transcricao/<int:revisao_id>/conferir", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def ri_transcricao_conferir(revisao_id: int):
        """Dá divergências por conferidas no livro. GRAVE pede observação."""
        with db.connect() as con:
            r = RT.mostrar(con, revisao_id)
        if r is None:
            abort(404)
        volta = url_for("ri_ficha", matricula_id=r["matricula_id"]) + "#certidao-transcricao"
        itens = []
        for bruto in request.form.getlist("indice"):
            i = numero_digitado(bruto)
            if i is not None:
                itens.append((i, request.form.get(f"obs_{i}") or ""))
        if not itens:
            flash("Marque ao menos uma divergência.", "warning")
            return redirect(volta)
        try:
            with db.transaction() as con:
                feitos = RT.conferir_divergencias(
                    con, revisao_id, itens, usuario=usuario_nome(),
                    papel=app.extensions["usuario_papel"]())
        except RT.TranscricaoError as erro:
            flash(str(erro), "danger")
            return redirect(volta)
        for f in feitos:
            audit("RI_TRANSCRICAO_DIVERGENCIA_CONFERIDA", "ri_transcricao_revisoes",
                  revisao_id, {"matricula_id": r["matricula_id"], **f})
        flash(f"{len(feitos)} divergência(s) dada(s) por conferida(s) no livro. O texto "
              "não foi tocado.", "success")
        return redirect(volta)

    # ------------------------------------------------------- o lote

    def _no_endereco(filtro: dict) -> dict:
        return {**filtro, "so_sem_revisao": "1" if filtro["so_sem_revisao"] else ""}

    def _filtro_da_tela() -> dict:
        dados = request.values
        primeira_vez = request.method == "GET" and not dados
        return {"livro": (dados.get("livro") or "").strip(),
                "de": (dados.get("de") or "").strip(),
                "ate": (dados.get("ate") or "").strip(),
                # A ESCOLHA QUE ABRE A TELA É «todos os transcritos sem revisão».
                "so_sem_revisao": primeira_vez or dados.get("so_sem_revisao") == "1"}

    @app.route("/registro-imoveis/transcricoes/lote", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER")
    def ri_transcricoes_lote():
        filtro = _filtro_da_tela()
        if request.method == "POST":
            with db.connect() as con:
                if not RT.ligada(con, pasta()):
                    flash("A revisão por IA não está ligada nesta instalação (falta a chave "
                          "do provedor, ela foi desligada, ou é o SANDBOX). Nada foi "
                          "criado.", "warning")
                    return redirect(url_for("ri_transcricoes_lote", **_no_endereco(filtro)))
            try:
                with db.transaction() as con:
                    lote_id = RTL.criar(con, filtro, usuario=usuario_nome())
                    RTL.comecar(con, lote_id)
                    conta = banco(con).um("""SELECT total_fichas, total_paginas
                                               FROM ri_transcricao_lotes WHERE id = %s""",
                                          (lote_id,))
            except (RTL.LoteError, RT.TranscricaoError) as erro:
                flash(str(erro), "danger")
                return redirect(url_for("ri_transcricoes_lote", **_no_endereco(filtro)))
            audit("RI_TRANSCRICAO_LOTE_CRIADO", "ri_transcricao_lotes", lote_id,
                  {"fichas": conta["total_fichas"], "paginas": conta["total_paginas"]})
            RTL.rodar_em_segundo_plano(db.db_path, pasta(), raiz(), lote_id)
            flash("O lote começou a rodar em segundo plano, do livro mais antigo para o "
                  "mais novo. Esta tela mostra o andamento.", "info")
            return redirect(url_for("ri_transcricoes_lote_ver", lote_id=lote_id))
        with db.connect() as con:
            contexto = {"filtro": filtro, "livros": RTL.livros(con),
                        "previa": RTL.previa(con, filtro), "lotes": RTL.lotes(con),
                        "cfg": RT.configuracao(con), "ligada": RT.ligada(con, pasta()),
                        "no_sandbox": RT.no_sandbox(con)}
        return render_template("ri_transcricoes_lote.html", **contexto)

    @app.route("/registro-imoveis/transcricoes/lote/<int:lote_id>")
    @roles_required("ADMIN", "MANAGER")
    def ri_transcricoes_lote_ver(lote_id: int):
        with db.connect() as con:
            lote = RTL.ver(con, lote_id)
        if lote is None:
            abort(404)
        return render_template("ri_transcricoes_lote_ver.html", lote=lote,
                               linhas_na_tela=RTL.LINHAS_NA_TELA)

    @app.route("/registro-imoveis/transcricoes/lote/<int:lote_id>/acao", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def ri_transcricoes_lote_acao(lote_id: int):
        acao = (request.form.get("acao") or "").strip().lower()
        volta = url_for("ri_transcricoes_lote_ver", lote_id=lote_id)
        try:
            if acao == "continuar":
                with db.connect() as con:
                    if not RT.ligada(con, pasta()):
                        flash("A revisão por IA não está ligada nesta instalação; o lote "
                              "continua pausado.", "warning")
                        return redirect(volta)
                with db.transaction() as con:
                    RTL.comecar(con, lote_id)
                audit("RI_TRANSCRICAO_LOTE_CONTINUADO", "ri_transcricao_lotes", lote_id, {})
                RTL.rodar_em_segundo_plano(db.db_path, pasta(), raiz(), lote_id)
                flash("Rodada nova começada, com o teto de hoje.", "info")
            elif acao == "pausar":
                with db.transaction() as con:
                    como = RTL.pausar(con, lote_id, usuario=usuario_nome())
                audit("RI_TRANSCRICAO_LOTE_PAUSADO", "ri_transcricao_lotes", lote_id, {})
                flash("Pausa pedida: a ficha em leitura termina e o lote para."
                      if como == RTL.PAUSANDO else "Lote pausado.", "info")
            else:
                flash("Não entendi o que fazer com o lote.", "danger")
        except RTL.LoteError as erro:
            flash(str(erro), "danger")
        return redirect(volta)

    # ------------------------------------------------------- a configuração

    @app.route("/configuracoes/revisao-transcricao", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def configuracoes_revisao_transcricao():
        """A imagem e os tetos da rodada. ESCREVE só estas três chaves.

        Rota própria, como a do envio à CRA: o formulário geral de
        Configurações grava tudo o que manda, e caixa fora dele gravaria «0»
        por cima a cada «salvar» (o relato de 15/10/2026)."""
        paginas = numero_digitado(request.form.get("teto_paginas"), maximo=100_000)
        try:
            custo = float((request.form.get("teto_custo") or "").replace(",", "."))
        except ValueError:
            custo = 0.0
        valores = {
            RT.CHAVE_IMAGEM: "1" if request.form.get("manda_imagem") else "0",
            RT.CHAVE_TETO_PAGINAS: str(paginas or RT.TETO_DE_PAGINAS_POR_RODADA),
            RT.CHAVE_TETO_CUSTO: (f"{custo:.2f}" if 0 < custo <= CUSTO_MAIS_ALTO
                                  else f"{RT.TETO_DE_CUSTO_POR_RODADA:.2f}"),
        }
        db.set_settings(valores)
        audit("SETTINGS_CHANGED", "SETTINGS", None, valores)
        flash("Revisão das transcrições: " + (
            "a imagem da página VAI ao provedor (decisão do oficial de 21/10/2026)."
            if valores[RT.CHAVE_IMAGEM] == "1" else
            "a imagem da página NÃO vai mais ao provedor; a revisão confere só o texto "
            "contra a ficha e diz que não viu a página.")
            + f" Teto da rodada do lote: {valores[RT.CHAVE_TETO_PAGINAS]} páginas e US$ "
              f"{valores[RT.CHAVE_TETO_CUSTO]}.", "success")
        return redirect(url_for("settings") + "#cfg-revisao-transcricao")
