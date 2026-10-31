"""A tela dos modelos dos papéis da casa — Administrativo → Modelos.

O RELATO #28 DO OFICIAL:

    «preciso ter controle geral sobre os modelos, em especial os cabeçalhos
     padrão de cada atribuição e ato, corpo, encerramento, eventual notas de
     rodapé»

UMA TELA SÓ, COM AS ATRIBUIÇÕES DENTRO
    «Controle geral» é a palavra dele. Havia dois lugares para editar modelo —
    ambos dentro do Registro de Imóveis — e cinco papéis que não tinham lugar
    nenhum. Espalhar por atribuição daria seis telas e a pergunta «onde eu mudo
    o cabeçalho?» continuaria sem resposta.

    Por isso as rotas se chamam `modelos_*`: o nome da rota é o que põe a tela
    no grupo do menu, e este assunto é do Administrativo — é onde mora o que se
    mexe uma vez e vale para a casa inteira.

O QUE ESTA TELA NÃO FAZ
    Ela não apaga o padrão, porque o padrão não mora junto do ajuste: mora na
    pasta `modelos_padrao/`, que a subida carrega na base de padrões (LF06A,
    19/10/2026). «Voltar ao padrão» apaga o ajuste, e o papel volta a sair de
    fábrica — não há como uma edição ruim deixar a casa sem modelo nenhum.
"""
from __future__ import annotations

from flask import Response, abort, flash, jsonify, redirect, render_template, request, url_for

import modelos_da_casa as MODELOS
import modelos_elementos as ELEM
import modelos_moldes as MOLDES
import seguranca_web as SEGWEB  # B2 (LX11): exceção inesperada não vai para a tela
import modelos_previa as PREVIA

# QUEM GRAVA O MODELO É ADMIN OU GERENTE (LX12, 19/10/2026 — achado M6 do LS02).
#
#   A docstring de `/modelos` sempre disse «SÓ ADMIN E GERENTE», e o decorador
#   deixava o USER: o escrevente trocava o molde da certidão do RCPN e os
#   `RC_TERMO_*`, que vão ao LibreOffice do servidor e saem em todo papel da
#   espécie. VER continua aberto ao balcão — é por esta tela que ele confere
#   com que forma o papel sai; só a gravação (salvar, restaurar, enviar o
#   `.odt`) se fecha. A prévia é POST, mas não grava: segue aberta.
QUEM_GRAVA: tuple[str, ...] = ("ADMIN", "MANAGER")


# O CONTEXTO DE ENSAIO DA CONFERENCIA.
#
# Ele nao e um ato de verdade: e um boneco, e por isso os valores dizem que sao
# de ensaio. Conferir com dado real exigiria escolher um ato — e a escolha do
# ato mudaria o resultado da conferencia, de modo que um modelo aprovado numa
# escritura reprovaria na seguinte.
#
# O QUE ELE PEGA e o que importa: chave que nao existe, `for` sem fechar, filtro
# escrito errado. O que ele NAO pega e campo que so aparece em ato de um tipo —
# e por isso a tela diz, em letra pequena, que a conferencia e da FORMA.
ENSAIO = {
    "hoje": "29 de agosto de 2026",
    "agora": "2026-08-29T09:00",
    "sv": {"nome": "SERVENTIA EXTRAJUDICIAL DE EXEMPLO",
           "cns": "000000", "cidade": "Cidade Exemplo", "uf": "UF",
           "endereco": "(endereço de ensaio)", "telefone": "(99) 0000-0000",
           "registrador": "(nome de ensaio)", "titulo": "Tabelião e Oficial"},
}


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """Pendura a tela dos modelos no app já construído."""

    usuario_nome = app.extensions["usuario_nome"]

    def _so_quem_grava() -> None:
        """403 para quem não grava modelo — ver `QUEM_GRAVA`."""
        if app.extensions["usuario_papel"]() not in QUEM_GRAVA:
            abort(403)

    def _redirect_modelos(chave: str, atribuicao_filtro: str = ""):
        """Volta ao editor preservando o filtro por atribuição, se houver."""
        args = {"editar": chave}
        if atribuicao_filtro:
            args["atribuicao"] = atribuicao_filtro
        return redirect(url_for("modelos", **args))

    def _conferir(chave: str, corpo: str) -> str | None:
        """Confere o modelo — com o conferidor do modulo, se houver um.

        O REGISTRO DE IMOVEIS CONFERE CONTRA UMA MATRICULA DE VERDADE, e isso
        e melhor que o boneco: o boneco pega erro de FORMA, e a matricula real
        pega campo que so aparece em ficha com ato, com onus, com parte. Era o
        que a tela antiga do RI ja fazia, e teria se perdido ao juntar tudo.

        `""` do conferidor quer dizer «conferi e esta bom»; `None` quer dizer
        «nao tinha com que conferir» — e ai vale o boneco. Sao coisas
        diferentes, e trata-las como a mesma faria a instalacao nova, sem
        matricula nenhuma, passar sem conferencia alguma.
        """
        proprio = app.extensions.get("conferidores_de_modelo", {}).get(chave)
        if proprio:
            resposta = proprio(corpo)
            if resposta is not None:
                return resposta or None
        # A MESMA RÉGUA DE QUEM GRAVA (`ELEM.salvar`): duas diriam coisas diferentes do mesmo texto.
        if chave in MODELOS.POR_CHAVE:
            return ELEM.conferir(ELEM.atribuicao_do_ato(chave), chave, ELEM.CORPO, corpo) or None
        return MODELOS.conferir(corpo, ENSAIO)

    @app.route("/modelos/previa", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def modelos_previa():
        """Prévia ao vivo enquanto edita — mesmo pipeline da emissão, dados de ensaio."""
        ato = (request.form.get("ato") or request.form.get("chave") or "").strip().upper()
        with db.connect() as con:
            corpo, codigo = PREVIA.resposta_previa(con, ato, request.form)
        return jsonify(**corpo), codigo

    @app.route("/modelos", methods=["GET", "POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def modelos():
        """A lista dos papéis, e o editor de um deles.

        SÓ ADMIN E GERENTE, e o motivo não é hierarquia: o modelo é a forma de
        um documento que a serventia assina, e uma vírgula fora do lugar aqui
        sai em todo papel daquele tipo até alguém reparar.
        """
        chave = (request.args.get("editar") or "").strip().upper()
        # O FILTRO POR ATRIBUICAO — relato #32. O catalogo ja sabia de qual
        # atribuicao e cada modelo, e nenhuma tela usava: quem estava no
        # Registro de Imoveis via os papeis das seis e procurava o seu.
        atribuicao = (request.args.get("atribuicao") or "").strip()
        # DEEP LINK `?editar=RI_CABECALHO` — relato 26/09/2026. Sem filtro a
        # tela lista as seis atribuicoes inteiras e o editor fica la embaixo:
        # parece que «nao abriu», embora o HTTP seja 200. Com `?editar=` e
        # chave valida, resolve a atribuicao pelo catalogo — o mesmo efeito de
        # `?atribuicao=Registro de Imoveis&editar=…`.
        if chave in MODELOS.POR_CHAVE and not atribuicao:
            atribuicao = MODELOS.POR_CHAVE[chave]["atribuicao"]

        if request.method == "POST":
            _so_quem_grava()
            chave = (request.form.get("chave") or "").strip().upper()
            corpo = request.form.get("corpo") or ""
            acao = (request.form.get("acao") or "salvar").strip()
            atribuicao_post = (
                (request.form.get("atribuicao") or atribuicao or "").strip())
            # O PAPEL QUE VAI SOZINHO AO CLIENTE (revisão de segurança de
            # 26/10/2026, PR #26 M1): a regra mora em
            # `MODELOS.PAPEIS_SO_DO_GESTOR`, e vale mesmo que `QUEM_GRAVA`
            # um dia volte a abrir ao escrevente.
            recusa = MODELOS.recusa_ao_gravar(app.extensions["usuario_papel"](),
                                              [chave])
            if recusa:
                return render_template("error.html", code=403, message=recusa), 403
            try:
                if acao == "restaurar":
                    with db.transaction() as con:
                        # **O MESMO ARMAZEM DOS SUBMODULOS.** Ate 07/09/2026
                        # esta tela gravava em `mo_modelos` e o submodulo da
                        # atribuicao gravaria em `mo_elementos`: duas fontes
                        # para o mesmo texto, para divergirem no primeiro
                        # conserto. `MODELOS.restaurar` continua existindo e
                        # limpa o legado.
                        havia = ELEM.restaurar(
                            con, atribuicao=ELEM.atribuicao_do_ato(chave),
                            ato=chave, parte=ELEM.CORPO)
                        havia = MODELOS.restaurar(con, chave) or havia
                    audit("MODELO_RESTAURADO", "mo_elementos", chave,
                          {"havia_ajuste": havia})
                    flash("O modelo voltou ao padrão do sistema."
                          if havia else
                          "Este modelo já estava no padrão do sistema.",
                          "success" if havia else "info")
                else:
                    # A CONFERENCIA VEM ANTES DE GRAVAR, e recusa.
                    #
                    # Gravar primeiro e avisar depois deixaria o modelo
                    # quebrado valendo ate alguem voltar na tela — e quem
                    # descobre e o escrevente com o cliente na frente, na hora
                    # de emitir. Aqui o erro aparece para quem edita, que e
                    # quem sabe conserta-lo.
                    erro = _conferir(chave, corpo)
                    if erro and corpo.strip():
                        flash(f"O modelo tem um erro e não foi gravado: {erro}",
                              "danger")
                        return _redirect_modelos(chave, atribuicao_post)
                    with db.transaction() as con:
                        ELEM.salvar(
                            con, atribuicao=ELEM.atribuicao_do_ato(chave),
                            ato=chave, parte=ELEM.CORPO, corpo=corpo,
                            quem=usuario_nome(), agora=db.now())
                    audit("MODELO_AJUSTADO", "mo_elementos", chave,
                          {"tamanho": len(corpo.strip())})
                    flash("Modelo gravado. Ele passa a valer no próximo "
                          "documento deste tipo.", "success")
            # **AS DUAS RECUSAS DE REGRA**, e nao so a antiga: desde
            # 07/09/2026 quem grava e `modelos_elementos`, e ele levanta o
            # `ElementoError`. Sem esta linha a recusa limpa cairia no
            # `except Exception` abaixo e sairia como «Nao deu para gravar o
            # modelo: ...» — a mensagem generica escondendo a explicada.
            except (MODELOS.ModeloError, ELEM.ElementoError) as erro:
                flash(str(erro), "danger")
            except Exception as erro:                      # noqa: BLE001
                flash(SEGWEB.recado_de_erro(erro, "modelos_gravar",
                                            "Não deu para gravar o modelo; o detalhe "
                                            "ficou no registro do servidor."), "danger")
            return _redirect_modelos(chave, atribuicao_post)

        # --------------------------------------------------------- a lista
        with db.connect() as con:
            grupos = []
            for atribuicao_do_grupo, itens in MODELOS.por_atribuicao():
                # O FILTRO — relato #32. Ele esconde os grupos das outras
                # atribuicoes; **nao esconde nada de dentro do grupo**, para
                # que ninguem conclua que a casa tem menos modelos do que tem.
                if atribuicao and atribuicao_do_grupo != atribuicao:
                    continue
                atribuicao_do_grupo_ = atribuicao_do_grupo
                linhas = []
                for c in itens:
                    linhas.append({**c,
                                   "ajustado": ELEM.esta_ajustado(
                                       con, c["chave"])})
                grupos.append({"atribuicao": atribuicao_do_grupo_,
                               "itens": linhas})

            editando = None
            if chave in MODELOS.POR_CHAVE:
                # **SO O CORPO**, e nao o documento composto: mostrar o fecho
                # dentro da caixa de edicao faria o escrevente grava-lo DENTRO
                # do corpo, e ele sairia duas vezes no papel seguinte.
                corpo = ELEM.corpo_do_ato(con, chave)
                editando = {
                    **MODELOS.POR_CHAVE[chave],
                    "corpo": corpo,
                    "ajustado": ELEM.esta_ajustado(con, chave),
                    "erro": _conferir(chave, corpo),
                    # DE ONDE O PADRÃO SAI: o arquivo da pasta dos padrões
                    # (LF06A). Era o nome da constante no código.
                    "onde": MODELOS.arquivo_do_padrao(chave),
                    # O PADRÃO MUDOU DEPOIS DO AJUSTE? — ver o aviso na tela.
                    "mudou": MODELOS.padrao_mudou_depois_do_ajuste(con, chave),
                    # **QUEM ESCREVE O MODELO PRECISA SABER COM QUE MARCADOR.**
                    #
                    #   Sao dois nesta casa: `{{ a.numero }}` do Jinja, que a
                    #   maioria usa, e `{numero}` do `str.format`, que e o dos
                    #   tres termos do Registro Civil. Escrever no formato
                    #   errado e o engano mais facil de cometer aqui — e sem
                    #   esta linha a tela nao dava pista nenhuma de qual e
                    #   qual: a pessoa descobriria pela recusa, e nao antes
                    #   dela.
                    "formato": MODELOS.formato_de(chave),
                }
            elif chave:
                flash("Esse modelo não existe nesta casa.", "warning")

            # OS PAPÉIS QUE SÃO FORMULÁRIO — os `.odt` das certidões do RCPN.
            # Eles seguem o filtro por atribuição como os outros; o que muda
            # é o que se faz com eles (baixar e enviar, e não editar texto).
            moldes = []
            if not atribuicao or atribuicao == MOLDES.MOLDES[0]["atribuicao"]:
                moldes = [MOLDES.como_esta(con, m["chave"])
                          for m in MOLDES.MOLDES]

        return render_template("modelos.html", grupos=grupos,
                               atribuicao=atribuicao,
                               atribuicoes=[a for a, _ in
                                            MODELOS.por_atribuicao()],
                               editando=editando, moldes=moldes,
                               base=MODELOS.situacao_da_base(),
                               quantos_ajustados=sum(
                                   1 for g in grupos for i in g["itens"]
                                   if i["ajustado"]))

    # ------------------------------------------------- os papéis em .odt
    #
    # **DUAS ROTAS, E NÃO UMA COM `if`**: uma BAIXA (GET, não muda nada) e a
    # outra GRAVA (POST). Juntá-las poria uma escrita atrás de um GET, que é
    # a regra da casa que mais custou aqui — «GET não abre transação de
    # escrita».

    @app.route("/modelos/molde/<chave>/baixar")
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def modelos_molde_baixar(chave: str):
        """O papel que vale hoje, para abrir no LibreOffice. SÓ LÊ."""
        try:
            with db.connect() as con:
                arquivo = MOLDES.arquivo_que_vale(con, chave)
                nome = MOLDES.como_esta(con, chave)["nome_arquivo"]
        except MOLDES.PapelError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("modelos"))
        return Response(
            arquivo,
            mimetype="application/vnd.oasis.opendocument.text",
            headers={"Content-Disposition":
                     f'attachment; filename="{nome}"'})

    @app.route("/modelos/molde", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def modelos_molde():
        """Grava o papel ajustado, ou volta ao do pacote. SÓ ADMIN E GERENTE."""
        _so_quem_grava()
        chave = (request.form.get("chave") or "").strip().upper()
        acao = (request.form.get("acao") or "enviar").strip()
        try:
            if acao == "restaurar":
                with db.transaction() as con:
                    havia = MOLDES.restaurar(con, chave)
                audit("MOLDE_RESTAURADO", "mo_moldes", chave,
                      {"havia_ajuste": havia})
                flash("O papel voltou ao que vem no pacote do sistema."
                      if havia else
                      "Este papel já era o do pacote.",
                      "success" if havia else "info")
                return redirect(url_for("modelos"))

            enviado = request.files.get("arquivo")
            bruto = enviado.read() if enviado else b""
            if not bruto:
                flash("Escolha o arquivo .odt antes de enviar.", "warning")
                return redirect(url_for("modelos"))
            # A CONFERÊNCIA VEM ANTES DE GRAVAR, e recusa — `MOLDES.salvar`
            # a faz e levanta a frase pronta.
            with db.transaction() as con:
                resumo = MOLDES.salvar(
                    con, chave, arquivo=bruto,
                    nome_arquivo=(enviado.filename or ""),
                    quem=usuario_nome(), agora=db.now())
            audit("MOLDE_AJUSTADO", "mo_moldes", chave,
                  {"tamanho": len(bruto), "sha256": resumo})
            flash("Papel gravado. Ele passa a valer na próxima certidão desta "
                  "espécie — e a atualização do sistema não o apaga.",
                  "success")
        except MOLDES.PapelError as erro:
            flash(str(erro), "danger")
        except Exception as erro:                          # noqa: BLE001
            flash(SEGWEB.recado_de_erro(erro, "modelos_papel",
                                        "Não deu para gravar o papel; o detalhe "
                                        "ficou no registro do servidor."), "danger")
        return redirect(url_for("modelos"))
