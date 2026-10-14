"""
As telas do nucleo — os livros, os termos, as inutilizacoes e os encerramentos.

POR QUE UM MODULO PROPRIO, E NAO DENTRO DE `atribuicoes_web`
    Aquele e o das QUATRO atribuicoes novas: titulo, assento, registro. Este e
    o do LIVRO, que serve as seis. Sao assuntos diferentes, e o livro nao e de
    ninguem em particular — e por isso que o nucleo existe.

O QUE FALTAVA, E POR QUE ISSO IMPORTA
    Ate 25/08/2026 `escrituracao.py` — 41 KB, os 24 livros — nao tinha uma
    unica rota. Abrir livro, encerrar livro, inutilizar folha e ENCERRAR O DIA
    eram funcoes de dominio prontas e testadas que nenhuma tela chamava.

    O termo de abertura e o de encerramento nao sao formalidade: sao o que diz
    o que o livro e, quantas folhas tem, quais foram usadas e quais ficaram
    inutilizadas. E o primeiro papel que a inspecao pede.

O TERMO SAI EM .ODT, PARA COLAR NO LIVRO DE PAPEL
    Termo que so existe dentro do banco nao serve: o livro fisico e que precisa
    dele na primeira e na ultima folha. A forma e a mesma de
    `/notas/livros/<id>/termo/<qual>`, que ja roda nesta casa ha versoes —
    cabecalho da serventia, o teor, e a linha de assinatura.

A TELA NAO REPETE A REGRA DO DOMINIO
    Quem recusa abrir o segundo livro aberto, inutilizar folha escriturada,
    encerrar livro ja encerrado ou encerrar o mesmo dia duas vezes e
    `escrituracao`, com frase de balcao. A tela esconde o botao por educacao;
    o dominio recusa por dever.

FUNDAMENTO
    Lei 8.935/1994, art. 30, I. Lei 6.015/1973, arts. 3o a 6o.
    Lei 9.492/1997, arts. 33 e 34.
    Codigo de Normas do Foro Extrajudicial do Maranhao — Prov. TJMA 28/2026,
        "Dos Livros e da sua Escrituracao".
"""
from __future__ import annotations

import sqlite3
from datetime import date

from flask import Response, abort, flash, redirect, render_template, request, url_for

import acervo_carga as AC
import atribuicoes as AT
import escrituracao as ESC
import implantacao as IMP
import livro_nucleo as LN
from ri_odt import gerar_odt, html_para_odf
from ri_web import data_por_extenso
from serventia import dados as dados_serventia

# As tres series de livro diario — os protocolos. Sao as unicas em que
# "encerrar o dia" quer dizer alguma coisa; as outras encerram quando enchem.
SERIES_DIARIAS = tuple(c for c, s in LN.SERIES.items() if s.diario)


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """Pendura as telas do nucleo no app ja construido."""

    # UM RELOGIO SO PARA O MODULO INTEIRO. `db.now()` e o mesmo que grava o
    # resto da casa; ler a hora de dois lugares faria o termo do livro e o
    # registro do banco discordarem por um segundo, e termo e o papel que a
    # inspecao le.
    def agora() -> str:
        return db.now()

    def hoje() -> str:
        return agora()[:10]

    def sv() -> dict:
        return dados_serventia(db.get_settings)

    def extenso(dia: str | None = None) -> str:
        return data_por_extenso(date.fromisoformat(dia or hoje()))

    usuario_nome = app.extensions["usuario_nome"]

    def _campo(nome: str) -> str:
        return (request.form.get(nome) or "").strip()

    def _inteiro(valor: str) -> int | None:
        """Número inteiro de um campo do formulário, ou None. Nunca levanta."""
        try:
            return int(str(valor).strip())
        except (TypeError, ValueError):
            return None

    def _ler():
        con = db.connect()
        con.row_factory = sqlite3.Row
        return con

    # ------------------------------------------------------- o panorama

    @app.route("/nucleo/livros")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def nucleo_livros():
        """Os 24 livros do núcleo, um por série, com o que está aberto.

        É a tela de onde se vê as seis atribuições de uma vez: qual série tem
        livro aberto, em que folha ele está, e qual o próximo número de ordem.
        """
        with _ler() as con:
            linhas = ESC.panorama(con)
            atrasados = {s: ESC.dias_sem_encerrar(con, s)
                         for s in SERIES_DIARIAS}
            fechados = [dict(r) for r in con.execute(
                """SELECT l.*, COUNT(g.id) atos
                     FROM nu_livros l
                     LEFT JOIN nu_lugares g ON g.livro_id = l.id AND g.inicio = 1
                    WHERE l.encerrado = 1
                    GROUP BY l.id ORDER BY l.encerramento DESC LIMIT 40""")]
        atrasados = {s: d for s, d in atrasados.items() if d}
        return render_template("nucleo_livros.html", linhas=linhas,
                               atribuicoes=AT.ATRIBUICOES, fechados=fechados,
                               atrasados=atrasados, series=LN.SERIES)

    @app.route("/nucleo/livros/abrir", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def nucleo_livro_abrir():
        """Abre livro novo da série, com termo de abertura. ESCREVE.

        O NÚMERO DO LIVRO NÃO SE DIGITA: sai de
        `escrituracao.numero_do_proximo_livro`, que é o maior já usado mais um.
        Digitar abriria a porta para dois Livros 3 na mesma série.

        Quem recusa o segundo livro aberto é o domínio — dois livros abertos na
        mesma série fazem o mesmo número de ordem sair em dois lugares.
        """
        serie = _campo("serie")
        dia = _campo("dia") or None
        try:
            with db.transaction() as con:
                livro_id = ESC.abrir_livro(
                    con, serie, sv=sv(), agora=agora(),
                    data_extenso=extenso(dia), dia=dia,
                    folhas=_inteiro(_campo("folhas")),
                    descricao=_campo("descricao") or None,
                    usuario=usuario_nome())
        except LN.LivroError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("nucleo_livros"))
        # `audit` abre transação própria: FORA do `with`, como no resto da casa.
        audit("NUCLEO_LIVRO_ABERTO", "nu_livros", livro_id,
              {"serie": serie, "dia": dia})
        flash("Livro aberto, com termo de abertura. Imprima o termo e cole na "
              "primeira folha.", "success")
        return redirect(url_for("nucleo_livro", livro_id=livro_id))

    # --------------------------------------------------- a ficha do livro

    @app.route("/nucleo/livros/<int:livro_id>")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def nucleo_livro(livro_id: int):
        """A ficha do livro: o termo, o que está escriturado e o que falta.

        A CONFERÊNCIA VEM JUNTO. `escrituracao.conferir_livro` diz, em frases
        de balcão, o que a inspeção acharia — folha em branco no meio sem termo
        de inutilização, verso pulado, número de ordem repetido, dia sem
        encerramento. Deixar isso numa tela separada seria deixar para depois.
        """
        with _ler() as con:
            livro = con.execute("SELECT * FROM nu_livros WHERE id=?",
                                (livro_id,)).fetchone()
            if not livro:
                flash("Livro não encontrado.", "danger")
                return redirect(url_for("nucleo_livros"))
            conferencia = ESC.conferir_livro(con, livro_id)
            lugares = [dict(r) for r in con.execute(
                """SELECT * FROM nu_lugares WHERE livro_id=? AND inicio=1
                    ORDER BY folha, verso, ordem LIMIT 400""", (livro_id,))]
            inutilizadas = [dict(r) for r in con.execute(
                """SELECT * FROM nu_inutilizacoes WHERE livro_id=?
                    ORDER BY folha, verso""", (livro_id,))]
            livre = ESC.folha_livre(con, livro)
        s = ESC.serie_de(livro["serie"])
        return render_template(
            "nucleo_livro.html", livro=dict(livro), serie=s,
            conferencia=conferencia, lugares=lugares,
            inutilizadas=inutilizadas, folha_livre=livre,
            ultima=ESC.ultima_folha(livro))

    @app.route("/nucleo/livros/<int:livro_id>/inutilizar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def nucleo_livro_inutilizar(livro_id: int):
        """Inutiliza uma face em branco, com motivo e termo. ESCREVE.

        FOLHA ESCRITURADA NÃO SE INUTILIZA — o ato nela é que se cancela. São
        coisas diferentes, e confundi-las apaga ato bom; quem recusa é o
        domínio.
        """
        rotulo = _campo("rotulo")
        try:
            with db.transaction() as con:
                ESC.inutilizar(con, livro_id, rotulo, motivo=_campo("motivo"),
                               sv=sv(), agora=agora(), data_extenso=extenso(),
                               usuario=usuario_nome())
        except LN.LivroError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("nucleo_livro", livro_id=livro_id))
        audit("NUCLEO_FOLHA_INUTILIZADA", "nu_livros", livro_id,
              {"rotulo": rotulo, "motivo": _campo("motivo")})
        flash(f"Folha {rotulo} inutilizada, com termo.", "success")
        return redirect(url_for("nucleo_livro", livro_id=livro_id))

    @app.route("/nucleo/livros/<int:livro_id>/encerrar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def nucleo_livro_encerrar(livro_id: int):
        """Encerra o livro com termo. ESCREVE.

        O termo diz a faixa de números que o livro recebeu, a última folha
        usada e quantas ficaram inutilizadas — é o que a inspeção lê para saber
        que nada sumiu entre um livro e o seguinte.
        """
        try:
            with db.transaction() as con:
                ESC.encerrar_livro(con, livro_id, sv=sv(), agora=agora(),
                                   data_extenso=extenso(),
                                   motivo=_campo("motivo") or None,
                                   usuario=usuario_nome())
        except LN.LivroError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("nucleo_livro", livro_id=livro_id))
        audit("NUCLEO_LIVRO_ENCERRADO", "nu_livros", livro_id,
              {"motivo": _campo("motivo") or None})
        flash("Livro encerrado, com termo. Imprima o termo e cole na última "
              "folha.", "success")
        return redirect(url_for("nucleo_livro", livro_id=livro_id))

    # ------------------------------------------------------- os termos

    @app.route("/nucleo/livros/<int:livro_id>/termo/<qual>")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def nucleo_livro_termo(livro_id: int, qual: str):
        """O termo de abertura ou de encerramento em .odt, para colar no livro.

        Termo que só existe dentro do banco não serve: o livro de papel é que
        precisa dele na primeira e na última folha. A forma é a mesma de
        `/notas/livros/<id>/termo/<qual>`, que já roda nesta casa.
        """
        if qual not in ("abertura", "encerramento"):
            abort(404)
        with _ler() as con:
            livro = con.execute("SELECT * FROM nu_livros WHERE id=?",
                                (livro_id,)).fetchone()
        if not livro:
            abort(404)
        texto = (livro[f"termo_{qual}"] or "").strip()
        if not texto:
            flash(f"Este livro ainda não tem termo de {qual}.", "warning")
            return redirect(url_for("nucleo_livro", livro_id=livro_id))
        s = sv()
        html = (f'<p align="center"><b>{s["unit_name"]}</b></p>'
                f'<p align="center">{s["serventia_titulo"]}: '
                f'{s["serventia_titular"]}</p>'
                f'<p align="center">CNS {s["ri_cns"]} — {s["endereco_completo"]}</p>'
                f'<p></p><p>{texto}</p><p></p><p></p>'
                f'<p align="center">_________________________________</p>'
                f'<p align="center">{s["serventia_titular"]}</p>'
                f'<p align="center">{s["serventia_titulo"]}</p>')
        arquivo = gerar_odt(html_para_odf(html),
                            titulo=f"Termo de {qual} — livro {livro['numero']}")
        audit("NUCLEO_LIVRO_TERMO", "nu_livros", livro_id, {"qual": qual})
        nome = (f"termo-{qual}-{livro['serie'].lower()}-"
                f"livro-{livro['numero']}.odt")
        return Response(arquivo,
                        mimetype="application/vnd.oasis.opendocument.text",
                        headers={"Content-Disposition":
                                 f'attachment; filename="{nome}"'})

    # ------------------------------------------------ encerramento diário

    @app.route("/nucleo/encerramento-diario", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def nucleo_encerramento_diario():
        """Encerrar o dia nos livros de protocolo — Protesto, RCPJ e RTD.

        DIA SEM MOVIMENTO TAMBÉM SE ENCERRA, e o termo diz "não houve
        movimento". É isso que distingue dia parado de dia não escriturado — e
        é a diferença que a inspeção procura.

        `dias_sem_encerrar` é a outra metade: não basta encerrar hoje, tem de
        dar para provar que não ficou dia aberto atrás.
        """
        if request.method == "POST":
            if app.extensions["usuario_papel"]() == "AUDITOR":
                flash("Perfil de auditoria não encerra o dia.", "danger")
                return redirect(url_for("nucleo_encerramento_diario"))
            serie, dia = _campo("serie"), _campo("dia") or hoje()
            try:
                with db.transaction() as con:
                    r = ESC.encerrar_o_dia(con, serie, dia, sv=sv(),
                                           agora=agora(),
                                           dia_extenso=extenso(dia),
                                           usuario=usuario_nome())
            except (LN.LivroError, ValueError) as erro:
                flash(str(erro), "danger")
                return redirect(url_for("nucleo_encerramento_diario"))
            audit("NUCLEO_DIA_ENCERRADO", "nu_encerramentos_diarios", None,
                  {"serie": serie, "dia": dia, "quantidade": r["quantidade"]})
            movimento = (f"{r['quantidade']} lançamento(s), do nº "
                         f"{r['primeiro']} ao {r['ultimo']}"
                         if r["quantidade"] else "sem movimento")
            flash(f"Dia {dia} encerrado em {LN.serie(serie).nome} — "
                  f"{movimento}.", "success")
            return redirect(url_for("nucleo_encerramento_diario"))

        with _ler() as con:
            painel = []
            for codigo in SERIES_DIARIAS:
                painel.append({
                    "serie": codigo,
                    "nome": LN.serie(codigo).nome,
                    "atrasados": ESC.dias_sem_encerrar(con, codigo),
                    "encerrado_hoje": bool(con.execute(
                        """SELECT 1 FROM nu_encerramentos_diarios
                            WHERE serie=? AND dia=?""",
                        (codigo, hoje())).fetchone()),
                })
            feitos = [dict(r) for r in con.execute(
                """SELECT * FROM nu_encerramentos_diarios
                    ORDER BY dia DESC, id DESC LIMIT 60""")]
        return render_template("nucleo_encerramento_diario.html",
                               painel=painel, feitos=feitos, hoje=hoje())

    # ---------------------------------------------------- a numeração

    # ------------------------------------- o que só o oficial pode informar

    @app.route("/implantacao")
    @login_required
    def implantacao():
        """A aba do que espera você — nas seis atribuições. Só LÊ.

        O SISTEMA ESTEVE SUSPENSO E VAI VOLTAR. Quando voltar, há coisas que o
        acervo não sabe dizer e que só quem conhece o livro físico responde.
        Até 26/08/2026 elas moravam numa lista dentro da documentação, e o
        balcão não as via — **documentação não avisa ninguém**.

        A LISTA NÃO É ADIVINHADA: cada pendência foi declarada por quem a
        descobriu, com o motivo medido. Num sistema novo, sem carga nenhuma,
        ela é vazia — e começar do número 1 nele está certo.
        """
        with _ler() as con:
            abertas = IMP.abertas(con)
            fechadas = IMP.fechadas(con)
            # O próximo número de cada série, para a pendência mostrar de onde
            # o contador está partindo. `consumir=False`: GET não consome.
            numeros = {}
            for x in abertas:
                if x["tipo"] == "NUMERO" and x["serie"]:
                    linha = con.execute(
                        "SELECT * FROM nu_numeracao WHERE serie=?",
                        (x["serie"],)).fetchone()
                    numeros[x["chave"]] = dict(linha) if linha else None
        return render_template("implantacao.html", abertas=abertas,
                               fechadas=fechadas, numeros=numeros,
                               nomes=IMP.NOME_DA_ATRIBUICAO)

    @app.route("/implantacao/<path:chave>/informar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def implantacao_informar(chave: str):
        """Informa o número, ou registra a decisão. ESCREVE.

        QUEM RECUSA BAIXAR O CONTADOR é `escrituracao.fixar_numeracao`, e não
        esta rota — número igual ou menor que o maior já usado repetiria número
        de ordem.
        """
        acao = _campo("acao") or "informar"
        try:
            with db.transaction() as con:
                con.row_factory = sqlite3.Row
                if acao == "dispensar":
                    r = IMP.dispensar(con, chave, motivo=_campo("motivo"),
                                      agora=agora(), usuario=usuario_nome())
                    recado = "Pendência dispensada, com o motivo registrado."
                elif acao == "reabrir":
                    r = IMP.reabrir(con, chave, agora=agora(),
                                    usuario=usuario_nome())
                    recado = "Pendência reaberta."
                elif _campo("proximo"):
                    r = IMP.resolver_numero(
                        con, chave, _campo("proximo"), agora=agora(),
                        usuario=usuario_nome(),
                        observacao=_campo("observacao") or None)
                    recado = (f"O próximo número de "
                              f"{LN.serie(r['serie']).nome} passa a ser "
                              f"{r['proximo']}.")
                else:
                    r = IMP.resolver_decisao(
                        con, chave, observacao=_campo("observacao"),
                        agora=agora(), usuario=usuario_nome())
                    recado = "Decisão registrada."
        except (IMP.ImplantacaoError, LN.LivroError) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("implantacao"))
        # `audit` abre transação própria: FORA do `with`, como no resto da casa.
        audit("IMPLANTACAO", "nu_implantacao", None, {"chave": chave, **r})
        flash(recado, "success")
        return redirect(url_for("implantacao"))

    @app.route("/nucleo/numeracao", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER")
    def nucleo_numeracao():
        """O contador de ordem de cada livro do núcleo — ver e corrigir.

        ESTA TELA FALTAVA, e sem ela o passo 5 do roteiro não tinha onde
        acontecer. A carga semeia sozinha sete séries do acervo e declara duas
        que o acervo **não sabe informar** — o Registro de Protestos e o de
        Pagamentos. Essas duas só saem do livro físico, e informá-las é
        decisão do oficial. Sem informar, o primeiro ato de cada uma nasce com
        o **número 1** sobre acervo que já passou disso: o defeito de
        18/08/2026 outra vez.

        GET NÃO CONSOME NÚMERO. `proximo_numero(..., consumir=False)` não
        escreve nada — tela de conferência que consome contador fica presa no
        `busy_timeout` enquanto outro balcão lavra, e devolve 500 na cara do
        escrevente.

        QUEM RECUSA BAIXAR O CONTADOR é `escrituracao.fixar_numeracao`, e não
        esta rota: número igual ou menor que o maior já usado repetiria número
        de ordem, e é exatamente isso que o núcleo existe para impedir.
        """
        if request.method == "POST":
            serie = _campo("serie")
            try:
                with db.transaction() as con:
                    novo = ESC.fixar_numeracao(
                        con, serie, _campo("proximo"), usuario=usuario_nome(),
                        motivo=_campo("motivo"), agora=agora())
            except LN.LivroError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("nucleo_numeracao"))
            # `audit` abre transação própria: FORA do `with`, como no resto
            # da casa.
            audit("NUCLEO_NUMERACAO", "nu_numeracao", None,
                  {"serie": serie, "proximo": novo,
                   "motivo": _campo("motivo") or None})
            flash(f"O próximo número de {LN.serie(serie).nome} passa a ser "
                  f"{novo}.", "success")
            return redirect(url_for("nucleo_numeracao"))

        with _ler() as con:
            fixados = {r["serie"]: dict(r)
                       for r in con.execute("SELECT * FROM nu_numeracao")}
            series = []
            for codigo, s in LN.SERIES.items():
                # As chaves de `nu_numeracao` entram SEMPRE, mesmo vazias:
                # série sem linha no contador deixaria o template com chave
                # que não existe, e Jinja imprime isso como espaço em branco
                # em vez do travessão que diz "não há".
                linha = {"codigo": codigo, "nome": s.nome,
                         "atribuicao": s.atribuicao,
                         "diaria": bool(s.numeracao_diaria),
                         "pendente": AC.SEM_CONTADOR_NO_ACERVO.get(codigo),
                         "maior_em_uso": None, "semeado_de": None,
                         "fixado_em": None, "fixado_por": None,
                         "observacao": None,
                         **fixados.get(codigo, {})}
                # Série de numeração diária não tem contador a corrigir: ela
                # reinicia sozinha a cada dia, e o número sai do livro do dia.
                linha["proximo"] = (
                    None if s.numeracao_diaria
                    else ESC.proximo_numero(con, codigo, consumir=False))
                series.append(linha)
        return render_template("nucleo_numeracao.html", series=series,
                               atribuicoes=AT.ATRIBUICOES)
