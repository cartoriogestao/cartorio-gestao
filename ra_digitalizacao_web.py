"""OS PAPÉIS E OS ARQUIVOS DO REGISTRO DO LIVRO 3.

A digitalização (subir, ver, baixar), a conferência da ficha contra o papel, e
**a própria ficha impressa** — as três coisas são o registro visto de fora.

    «digitalizacao de imagens deve ter igual ao livro 2»
                                        — o oficial, 21/09/2026

As regras de arquivo moram em `ra_digitalizacao.py`, e elas são **lidas** das
do Livro 2. Aqui só se ligam os fios.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

from flask import Response, abort, flash, redirect, render_template, request, url_for

from bd_nativo import banco
import modelos_da_casa as MODELOS
import ra_correcoes as CORR
import ra_digitalizacao as DIGI
import ra_ficha_odt as FICHA
from serventia import dados as dados_serventia


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """A ASSINATURA É A DA CASA — ver `ajuda_web.registrar_rotas`."""

    usuario_nome = app.extensions["usuario_nome"]

    def _registro(registro_id: int) -> dict:
        with db.connect() as con:
            linha = banco(con).um("SELECT * FROM ra_registros WHERE id=%s",
                          (registro_id,))
        if not linha:
            abort(404)
        return dict(linha)

    @app.route("/livro3/<int:registro_id>/digitalizacao", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def livro3_upload_digitalizacao(registro_id: int):
        """Sobe a varredura do registro. **O arquivo anterior vai ao histórico.**"""
        r = _registro(registro_id)
        try:
            info = DIGI.gravar_upload(db, registro_id=registro_id,
                                      arquivo=request.files.get("arquivo"),
                                      usuario=usuario_nome())
        except DIGI.DigitalizacaoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("livro3_registro", registro_id=registro_id))
        audit("RA_DIGITALIZACAO_ATUALIZADA", "ra_registros", registro_id,
              {"numero": r["numero"], "nome": info["nome"],
               "sha256": info["sha256"]})
        flash(f"Digitalização do registro {r['numero']} atualizada "
              f"({info['nome']}). A anterior ficou no histórico.", "success")
        return redirect(url_for("livro3_registro", registro_id=registro_id))

    @app.route("/livro3/<int:registro_id>/digitalizacao/retirar",
               methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def livro3_remover_digitalizacao(registro_id: int):
        _registro(registro_id)
        try:
            info = DIGI.retirar_upload(
                db, registro_id=registro_id,
                motivo=request.form.get("motivo"), usuario=usuario_nome())
        except DIGI.DigitalizacaoError as erro:
            flash(str(erro), "danger")
        else:
            audit("RA_DIGITALIZACAO_RETIRADA", "ra_registros", registro_id, info)
            flash("Arquivo retirado da ficha. A cópia ficou no histórico; "
                  "agora envie o arquivo correto.", "success")
        return redirect(url_for("livro3_registro", registro_id=registro_id))

    @app.route("/livro3/<int:registro_id>/digitalizacao/arquivo")
    @login_required
    def livro3_baixar_digitalizacao(registro_id: int):
        """Entrega o arquivo. `?visualizar=1` abre na tela em vez de baixar.

        **A mesma rota serve ao botão de baixar e à tela de conferência** — o
        parâmetro só muda a apresentação HTTP; ele não copia nem altera o
        arquivo.
        """
        with db.connect() as con:
            digi = DIGI.atual(con, registro_id)
        if not digi:
            abort(404)
        caminho = Path(digi["digi_path"])
        if not caminho.is_file():
            abort(404)
        nome = str(digi["digi_nome"] or caminho.name)
        nome = nome.replace('"', "").replace("\r", "").replace("\n", "")
        tipo = mimetypes.guess_type(nome)[0] or "application/octet-stream"
        visualizar = request.args.get("visualizar") == "1"
        return Response(
            caminho.read_bytes(), mimetype=tipo,
            headers={
                "Content-Disposition":
                    f'{"inline" if visualizar else "attachment"}; '
                    f'filename="{nome}"',
                # O ARQUIVO VEM DE FORA, e servi-lo em linha o roda na origem
                # do sistema: `nosniff` é o que impede o navegador adivinhar
                # um tipo mais perigoso que o declarado.
                "X-Content-Type-Options": "nosniff",
            })

    @app.route("/livro3/<int:registro_id>/digitalizacao/miniatura")
    @login_required
    def livro3_miniatura_digitalizacao(registro_id: int):
        """A primeira página, para a ficha. Só lê."""
        with db.connect() as con:
            digi = DIGI.atual(con, registro_id)
        if not digi:
            abort(404)
        caminho = Path(digi["digi_path"])
        if not caminho.is_file():
            abort(404)
        # A LARGURA VEM DA TELA, como no Livro 2 — a ficha pede 420. Sem
        # ler o `w` a miniatura saía sempre no padrão, e o endereço que a
        # ficha monta prometia um tamanho que esta rota não entregava.
        # `miniatura_png` já limita o intervalo; aqui só se lê o número.
        try:
            largura = int(request.args.get("w") or 420)
        except ValueError:
            largura = 420
        try:
            imagem = DIGI.miniatura_png(caminho, largura=largura)
        except Exception:  # noqa: BLE001 — miniatura é conforto, não ato
            abort(404)
        return Response(imagem, mimetype="image/png",
                        headers={"Cache-Control": "private, max-age=3600",
                                 "X-Content-Type-Options": "nosniff"})

    @app.route("/livro3/<int:registro_id>/conferir", methods=["GET", "POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def livro3_conferir(registro_id: int):
        """Conferir a ficha contra a digitalização — o que está escrito de um
        lado, o papel varrido do outro.

        **Aqui ela vale mais que no Livro 2**: dos registros deste livro uns
        vieram da carga do acervo e outros da importação dos documentos, e um
        deles carrega uma divergência que o **próprio importador declarou**.
        """
        r = _registro(registro_id)
        if request.method == "POST":
            conferido = request.form.get("conferido") == "1"
            nota = (request.form.get("nota") or "").strip()
            try:
                with db.transaction() as con:
                    CORR.conferir(con, registro_id, conferido=conferido,
                                  agora=db.now(), usuario=usuario_nome(),
                                  nota=nota)
            except CORR.CorrecaoError as erro:
                flash(str(erro), "danger")
            else:
                audit("RA_REGISTRO_CONFERIDO", "ra_registros", registro_id,
                      {"conferido": conferido, "nota": nota[:400]})
                flash("Registro marcado como conferido." if conferido
                      else "A marca de conferido saiu — o carimbo de quem "
                           "conferiu antes fica, porque é fato do passado.",
                      "success")
            return redirect(url_for("livro3_conferir",
                                    registro_id=registro_id))

        with db.connect() as con:
            digi = DIGI.atual(con, registro_id)
            atos = banco(con).ler(
                "SELECT * FROM ra_atos WHERE registro_id=%s ORDER BY numero, id",
                (registro_id,))
            partes = banco(con).ler(
                "SELECT * FROM ra_partes WHERE registro_id=%s ORDER BY id",
                (registro_id,))
        arquivo = Path(digi["digi_path"]) if digi else None
        return render_template(
            "livro3_conferir.html", registro=r, atos=atos, partes=partes,
            digi=digi, fmt_date=fmt_date,
            digi_existe=bool(arquivo and arquivo.is_file()),
            digi_pdf=bool(arquivo and arquivo.suffix.lower() == ".pdf"),
            digi_imagem=bool(arquivo and arquivo.suffix.lower()
                             in {".png", ".jpg", ".jpeg"}))

    @app.route("/livro3/conferir")
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def livro3_por_conferir():
        """A fila do que ninguém leu contra o papel ainda."""
        with db.connect() as con:
            registros = CORR.por_conferir(con)
        return render_template("livro3_por_conferir.html",
                               registros=registros)

    # ------------------------------------------------------ a ficha em papel

    @app.route("/livro3/<int:registro_id>/ficha.odt")
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def livro3_ficha_odt(registro_id: int):
        """A ficha do registro impressa — **e ela não é certidão**.

        O Livro 2 imprime a própria ficha desde sempre; o Livro 3 só emitia
        certidão. São papéis diferentes e a diferença importa: a certidão vai
        para fora e **afirma**; a ficha é o livro, e serve para ler, levar à
        estante e conferir.

        **O TEXTO SAI DO CATÁLOGO DA CASA** (`RI_LIVRO3_FICHA`) — sem linha
        gravada vale o padrão do código, e ajustado sai como o oficial
        escreveu. É o relato #28.

        **NÃO HÁ FECHO DE CERTIDÃO, NEM «CONFERE COM O ORIGINAL», NEM
        ASSINATURA DE OFICIAL**: um papel que se pareça com certidão sem ser
        uma é o pior tipo de papel que esta casa pode pôr no mundo. O rodapé
        diz isso com todas as letras.

        **CADA ATO, PORÉM, DIZ QUEM O PRATICOU** — LH13, 21/10/2026 («15 a»):
        como na ficha do Livro 2, «Cidade/UF, data. Dou fé. A Escrevente
        Autorizada (NOME).», com o nome e a função gravados no ato na
        lavratura (CN-MA art. 458). É o que o livro diz do ato, e não uma
        afirmação da certidão; o ato antigo, sem o nome gravado, sai sem ele.
        """
        r = _registro(registro_id)
        with db.connect() as con:
            atos = banco(con).ler(
                "SELECT * FROM ra_atos WHERE registro_id=%s ORDER BY numero, id",
                (registro_id,))
            partes = banco(con).ler(
                "SELECT * FROM ra_partes WHERE registro_id=%s ORDER BY id",
                (registro_id,))
            corpo = MODELOS.corpo_de(con, "RI_LIVRO3_FICHA")
            sv = dados_serventia(db.get_settings)
            # A etiqueta do selo vem DESTE banco (LT03): sem `con`, o carimbo
            # procurava na pasta padrão da instalação e saía sem os valores.
            claros = FICHA.contexto(
                registro=r, atos=atos, partes=partes,
                serventia=sv, impresso_em=db.now(), con=con)
        try:
            texto = corpo.format(**claros)
        except KeyError as erro:
            # CLARO QUE O MODELO PEDE E A CASA NAO TEM — a recusa e aqui, com
            # o nome do claro, e nao um papel saindo com `{coisa}` impresso
            # dentro dele.
            flash(f"O modelo da ficha do Livro 3 pede um claro que este "
                  f"sistema não preenche: {erro}. Ajuste em Administrativo → "
                  f"Modelos.", "danger")
            return redirect(url_for("livro3_registro",
                                    registro_id=registro_id))

        arquivo = FICHA.montar_odt(
            texto_corpo=texto, sv=sv, claros=claros,
            usuario=usuario_nome(),
            titulo=f"Livro 3 — registro {r['numero']}")
        audit("RA_FICHA_IMPRESSA", "ra_registros", registro_id,
              {"numero": r["numero"], "atos": len(atos)})
        return Response(
            arquivo,
            mimetype="application/vnd.oasis.opendocument.text",
            headers={"Content-Disposition":
                     f'attachment; filename="livro3-{r["numero"]}.odt"'})

    # ---------------------------------------------- a digitalização do termo

    @app.route("/livro3/ato/<int:ato_id>/digitalizacao", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def livro3_upload_digitalizacao_do_ato(ato_id: int):
        """Guarda o papel daquele termo. **Não é a varredura da ficha.**

        Ordem do oficial em 21/09/2026: *«precisa ter digitalização do
        termo»*. A do registro é a ficha inteira; esta é o papel do ato — o
        instrumento de baixa que o credor expediu, a procuração que o
        representou, o aditivo que a averbação registrou.
        """
        with db.connect() as con:
            a = banco(con).um("SELECT registro_id, tipo, numero FROM ra_atos "
                          "WHERE id=%s", (ato_id,))
        if not a:
            abort(404)
        voltar = redirect(url_for("livro3_registro",
                                  registro_id=a["registro_id"]))
        try:
            info = DIGI.gravar_upload_do_ato(
                db, ato_id=ato_id, arquivo=request.files.get("arquivo"),
                usuario=usuario_nome())
        except DIGI.DigitalizacaoError as erro:
            flash(str(erro), "danger")
            return voltar
        audit("RA_TERMO_DIGITALIZADO", "ra_atos", ato_id,
              {"nome": info["nome"], "sha256": info["sha256"]})
        flash(f"Papel do termo {a['tipo']}-{a['numero']} guardado "
              f"({info['nome']}).", "success")
        return voltar

    @app.route("/livro3/ato/<int:ato_id>/digitalizacao/retirar",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def livro3_remover_digitalizacao_do_ato(ato_id: int):
        with db.connect() as con:
            ato = banco(con).um("SELECT registro_id FROM ra_atos WHERE id=%s",
                          (ato_id,))
        if not ato:
            abort(404)
        try:
            info = DIGI.retirar_upload(
                db, ato_id=ato_id, motivo=request.form.get("motivo"),
                usuario=usuario_nome())
        except DIGI.DigitalizacaoError as erro:
            flash(str(erro), "danger")
        else:
            audit("RA_TERMO_DIGITALIZACAO_RETIRADA", "ra_atos", ato_id, info)
            flash("Arquivo retirado do ato; a cópia ficou no histórico. "
                  "Envie o documento correto.", "success")
        return redirect(url_for("livro3_registro", registro_id=ato["registro_id"]))

    @app.route("/livro3/ato/<int:ato_id>/digitalizacao/arquivo")
    @login_required
    def livro3_baixar_digitalizacao_do_ato(ato_id: int):
        """Entrega o papel do termo. `?visualizar=1` abre na tela."""
        with db.connect() as con:
            digi = DIGI.atual_do_ato(con, ato_id)
        if not digi:
            abort(404)
        caminho = Path(digi["digi_path"])
        if not caminho.is_file():
            abort(404)
        nome = str(digi["digi_nome"] or caminho.name)
        nome = nome.replace('"', "").replace("\r", "").replace("\n", "")
        tipo = mimetypes.guess_type(nome)[0] or "application/octet-stream"
        visualizar = request.args.get("visualizar") == "1"
        return Response(
            caminho.read_bytes(), mimetype=tipo,
            headers={
                "Content-Disposition":
                    f'{"inline" if visualizar else "attachment"}; '
                    f'filename="{nome}"',
                "X-Content-Type-Options": "nosniff",
            })
