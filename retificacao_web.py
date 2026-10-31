"""As telas da retificação de área e do georreferenciamento.

    «vamos criar o módulo de processos de retificação de área e
     georreferenciamento» — o oficial, 29/08/2026

AS ROTAS SE CHAMAM `ri_retificacao_*`, E ISSO NÃO É ENFEITE
    O nome da rota é o que põe a tela no grupo certo do menu: o módulo sai do
    PREFIXO. Chamando-as `retificacao_*`, elas cairiam no Administrativo — longe
    do Registro de Imóveis, que é onde a matrícula está e onde a averbação sai.

    É a mesma decisão de `papel_web`, que se chama `rcpn_papel_*` pelo mesmo
    motivo.

A TELA NÃO REPETE A REGRA DO DOMÍNIO
    Ela só *oferece* o que cabe na fase; quem *recusa* é `retificacao.py`, e há
    teste que manda um ato que não cabe direto para a rota, sem passar pela
    tela. Repetir a regra nos dois lugares é como os dois divergem: a tela
    esconde o botão por educação, o domínio recusa por dever.

O PRAZO NÃO SE CALCULA AQUI
    Contar dia útil é do núcleo, que conhece os feriados desta comarca. A tela
    pede a data-limite ao mesmo lugar que a prenotação e o edital do usucapião
    pedem — uma segunda contagem divergiria, e num prazo divergir por um dia é
    recomeçar o prazo.
"""
from __future__ import annotations

from datetime import date

from flask import abort, flash, redirect, render_template, request, url_for

from bd_nativo import banco
import impressao_web as IMPW
import rascunho_de_tela as RASC
import retificacao as RT
import rt_tjma as NORMA
from storage import safe_component, save_upload
from seguranca_web import PRATICA  # M2 (LX11): o AUDITOR vê e não grava

#  O QUE A TELA DIZ AO JUNTAR UMA PEÇA — e por que a frase é uma só.
#
#  **A SEGUNDA PARTE É A QUE IMPORTA**: `retificacao.juntar_peca` marca
#  sozinho o item da conferência do art. 592 que aquela peça cumpre, e quem
#  acabou de anexar o arquivo precisa saber disso — senão vai marcar de novo à
#  mão, ou ficar em dúvida se marcou.
#
#  **ELA SUMIU DO CAMINHO MAIS USADO EM 21/09/2026**, quando o envio de vários
#  arquivos nasceu (medido: a 3.6.155 não tem o ramo, a 3.6.156 tem). O ramo
#  novo passou a dizer só «planta.pdf juntado ao processo» — o nome do arquivo,
#  que é informação boa, no lugar do aviso do checklist, que é a que se perde.
#  O teste que cobrava a frase ficou vermelho no mesmo dia, e ele estava certo.
#
#  Agora as duas coisas saem juntas, e a frase do checklist mora aqui: escrita
#  duas vezes, ela diverge no primeiro conserto e a tela passa a dizer uma
#  coisa num caminho e outra no outro.
ITEM_DA_CONFERENCIA_MARCADO = (
    "Se ele corresponder a um item da conferência, o item já foi marcado "
    "como atendido.")
ITENS_DA_CONFERENCIA_MARCADOS = (
    "Os itens da conferência correspondentes já foram marcados como "
    "atendidos.")


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """Pendura as telas da retificação no app já construído."""

    usuario_nome = app.extensions["usuario_nome"]
    usuario_id = app.extensions["usuario_id"]
    archive_root = app.extensions["archive_root"]

    # A NOTIFICAÇÃO É EDITÁVEL NA TELA DE MODELOS DESDE O LF06G, e a tela
    # confere o ajuste com a régua de quem monta (`rt_notificacao.
    # conferir_modelo`): o claro que o papel não tem é recusado ao gravar, e não
    # na hora de notificar, com o confrontante esperando.
    import rt_notificacao as _NOTIF
    app.extensions.setdefault("conferidores_de_modelo", {})[_NOTIF.PAPEL] = (
        _NOTIF.conferir_modelo)

    def agora() -> str:
        return db.now()

    def hoje() -> str:
        return db.now()[:10]

    def _serventia_do_papel() -> dict:
        """Quem assina a notificação — da regra viva, e num lugar só.

        A montagem mora em `serventia.quem_assina_o_papel`, que a usucapião
        também usa: duas cópias divergiriam no primeiro conserto, e o papel de
        um módulo passaria a dizer quem o do outro não diz.
        """
        from serventia import dados as dados_serventia
        from serventia import quem_assina_o_papel
        return quem_assina_o_papel(dados_serventia(db.get_settings))

    def _hoje_extenso() -> str:
        """«Cidade Exemplo-MA, 21 de setembro de 2026».

        A MESMA FUNÇÃO DO RESTO DA CASA — `ri_web.data_por_extenso` —, e não
        uma segunda montagem: duas formas de escrever a data divergiriam, e a
        notificação passaria a discordar da certidão.
        """
        from datetime import date as _date

        from ri_web import data_por_extenso
        from serventia import dados as dados_serventia
        s = dados_serventia(db.get_settings)
        lugar = s.get("cidade_uf") or s.get("ri_cidade") or ""
        # UM RELOGIO SO NA CASA: `db.now()`, o mesmo que grava os atos — e nao
        # `date.today()`, que e um segundo relogio e discorda dele na virada
        # do dia.
        quando = data_por_extenso(_date.fromisoformat(db.now()[:10]))
        return f"{lugar}, {quando}" if lugar else quando

    def _campo(nome: str, padrao: str = "") -> str:
        return (request.form.get(nome) or padrao).strip()

    def _pasta_pecas_retificacao(p: dict):
        numero = (p["numero"] if p else "") or "sem-numero"
        return (archive_root() / "Registro de Imoveis" / "Retificacoes" /
                safe_component(str(numero), f"Processo-{p['id']}"))

    def _dias_uteis_ate(dias: int) -> str:
        """A data-limite SUGERIDA, contada pelo mesmo lugar que a casa conta.

        `ri_schema.soma_dias_uteis` é a função que a prenotação já usa, e é ela
        que conhece os feriados desta comarca. Uma segunda contagem aqui
        divergiria da do comprovante de prenotação e da do edital do usucapião —
        e num prazo, divergir por um dia é recomeçar o prazo.

        (Eu escrevi `import feriados` na primeira versão, achando que havia um
         módulo com esse nome. Não há — a função mora no `ri_schema`, ao lado da
         numeração. **Não achar o arquivo que procurei não prova que a função
         não existe**, e este projeto já aprendeu isso cinco vezes.)

        É SUGESTÃO, e a tela deixa editar: quem sabe a data de recebimento é
        quem tem o AR na mão, e o prazo conta do recebimento (art. 599, § 2º).
        """
        from ri_schema import soma_dias_uteis
        return soma_dias_uteis(date.today(), dias).isoformat()

    # ------------------------------------------------------------- a lista

    @app.route("/registro-imoveis/retificacoes")
    @login_required
    def ri_retificacoes():
        """Os processos abertos, e o prazo do SIGEF em destaque.

        O SIGEF VEM PRIMEIRO NA TELA, e é deliberado: é o único prazo deste
        rito que é **da serventia** (art. 620, § 2º), nasce depois do ato — com
        o cliente já fora do balcão — e é por isso que se perde. Os outros
        prazos têm alguém de fora cobrando; este não tem ninguém.
        """
        with db.connect() as con:
            processos = RT.abertos(con)
            sigef = RT.sigef_a_vencer(con)
        return render_template("ri_retificacoes.html", processos=processos,
                               sigef=sigef, fases=RT.NOME_DA_FASE,
                               especies=NORMA.NOME_DA_ESPECIE)

    @app.route("/registro-imoveis/retificacoes/nova", methods=["GET", "POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER", "REGISTRADOR", "ESCREVENTE")
    def ri_retificacao_nova():
        form, rascunho_id = RASC.para_a_tela(
            db, "ri_retificacao_nova", "Este rascunho não é de uma retificação de área.")

        def tela():
            with db.connect() as con:
                matriculas = banco(con).ler(
                    """SELECT id, numero, livro FROM ri_matriculas
                        WHERE COALESCE(situacao,'ATIVA') <> 'ENCERRADA'
                     ORDER BY coalesce(substring(numero FROM '^[0-9]+')::bigint, 0) DESC, id
                     LIMIT 500""")
            return render_template("ri_retificacao_nova.html",
                                   matriculas=matriculas,
                                   especies=NORMA.NOME_DA_ESPECIE,
                                   fundamentos=NORMA.NOME_DO_FUNDAMENTO,
                                   form=form, rascunho_id=rascunho_id)

        if request.method == "POST":
            try:
                with db.transaction() as con:
                    novo = RT.autuar(
                        con,
                        numero=_campo("numero"),
                        especie=_campo("especie"),
                        fundamento=_campo("fundamento"),
                        matricula_id=int(_campo("matricula_id") or 0),
                        rural=_campo("rural") == "1",
                        agora=agora(), usuario=usuario_nome(),
                        ano=int(hoje()[:4]),
                        requerente_nome=_campo("requerente_nome"),
                        requerente_documento=_campo("requerente_documento"),
                        profissional_nome=_campo("profissional_nome"),
                        profissional_conselho=_campo("profissional_conselho"),
                        profissional_registro=_campo("profissional_registro"),
                        art_numero=_campo("art_numero"),
                        area_na_matricula=_campo("area_na_matricula"),
                        area_pretendida=_campo("area_pretendida"),
                        certificacao_incra=_campo("certificacao_incra"),
                        sigef_codigo=_campo("sigef_codigo"))
            except (RT.RetificacaoError, ValueError) as erro:
                flash(str(erro), "danger")
                return tela()
            audit("RT_AUTUADO", "rt_processos", novo,
                  {"numero": _campo("numero")})
            flash("Processo autuado. O checklist do art. 592 já está na ficha.",
                  "success")
            RASC.saiu_com_o_ato(db, audit, "ri_retificacao_nova",
                                url_for("ri_retificacao", processo_id=novo), usuario_nome())
            return redirect(url_for("ri_retificacao", processo_id=novo))

        return tela()

    # -------------------------------------------------------------- a ficha

    @app.route("/registro-imoveis/retificacoes/<int:processo_id>")
    @login_required
    def ri_retificacao(processo_id: int):
        with db.connect() as con:
            p = RT.processo(con, processo_id)
            if not p:
                flash("Não achei esse processo de retificação.", "warning")
                return redirect(url_for("ri_retificacoes"))
            pecas = RT.pecas(con, processo_id)
            dados = {
                "p": dict(p),
                "passos": RT.proximos_passos(con, processo_id, hoje=hoje()),
                "pecas": pecas,
                "anexos_pecas": {
                    x["id"]: [dict(a) for a in db.get_attachments(
                        "RT_PECA", x["id"])]
                    for x in pecas
                },
                "conferencia": RT.conferencia(con, processo_id),
                "confrontantes": RT.confrontantes(con, processo_id),
                "dispensados": RT.dispensados_de_notificacao(con, processo_id),
                "faltam_notificar": RT.quem_precisa_ser_notificado(
                    con, processo_id),
                "prazos": RT.situacao_dos_prazos(con, processo_id, hoje=hoje()),
                "andamento": RT.andamento(con, processo_id),
                "falta_decidir": RT.o_que_falta_para_decidir(
                    con, processo_id, hoje=hoje()),
            }
        return render_template(
            "ri_retificacao.html", **dados, norma=NORMA, RT=RT,
            prazo_sugerido=_dias_uteis_ate(15),
            fases=RT.NOME_DA_FASE, especies=NORMA.NOME_DA_ESPECIE,
            fundamentos=NORMA.NOME_DO_FUNDAMENTO,
            respostas=RT.NOME_DA_RESPOSTA, papeis=RT.NOME_DO_PAPEL)

    # ------------------------------------------------------------- as ações

    def _voltar(processo_id: int):
        return redirect(url_for("ri_retificacao", processo_id=processo_id))

    @app.route("/registro-imoveis/retificacoes/<int:processo_id>/peca",
               methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER", "REGISTRADOR", "ESCREVENTE")
    def ri_retificacao_peca(processo_id: int):
        arquivos = [f for f in request.files.getlist("documento") if f and f.filename]
        # Sem arquivo: junta so o registro da peca (comportamento antigo).
        if not arquivos:
            info = None
            try:
                with db.transaction() as con:
                    peca_id = RT.juntar_peca(
                        con, processo_id, tipo=_campo("tipo"), agora=agora(),
                        descricao=_campo("descricao"),
                        arquivo=_campo("arquivo"),
                        sha256="",
                        entregue_em=_campo("entregue_em") or hoje(),
                        usuario=usuario_nome())
            except RT.RetificacaoError as erro:
                flash(str(erro), "danger")
                return _voltar(processo_id)
            audit("RT_PECA", "rt_pecas", peca_id, {"processo": processo_id})
            flash("Documento juntado ao processo. "
                  + ITEM_DA_CONFERENCIA_MARCADO, "success")
            return _voltar(processo_id)

        with db.connect() as con:
            p = RT.processo(con, processo_id)
            if not p:
                flash("Nao achei esse processo de retificacao.", "danger")
                return _voltar(processo_id)
            pasta = _pasta_pecas_retificacao(p)

        nomes = []
        for upload in arquivos:
            try:
                info = save_upload(upload, pasta)
                with db.transaction() as con:
                    peca_id = RT.juntar_peca(
                        con, processo_id, tipo=_campo("tipo"), agora=agora(),
                        descricao=_campo("descricao"),
                        arquivo=info["stored_path"],
                        sha256=info["sha256"],
                        entregue_em=_campo("entregue_em") or hoje(),
                        usuario=usuario_nome())
                att = db.add_attachment(
                    "RT_PECA", peca_id, info, int(usuario_id() or 0),
                    _campo("descricao") or _campo("tipo"))
                audit("RT_PECA_ARQUIVO", "attachments", att,
                      {"peca": peca_id, "processo": processo_id})
                audit("RT_PECA", "rt_pecas", peca_id, {"processo": processo_id})
                nomes.append(info.get("original_name") or upload.filename)
            except RT.RetificacaoError as erro:
                flash(str(erro), "danger")
                return _voltar(processo_id)
        #  O NOME DO ARQUIVO **E** O AVISO DO CHECKLIST — 21/09/2026. O nome
        #  é o que prova ao balcão que subiu o arquivo certo; o aviso é o que
        #  evita marcar à mão o que o sistema já marcou.
        if len(nomes) == 1:
            flash(f"{nomes[0]} juntado ao processo. "
                  + ITEM_DA_CONFERENCIA_MARCADO, "success")
        else:
            flash(f"{len(nomes)} documentos juntados ao processo. "
                  + ITENS_DA_CONFERENCIA_MARCADOS, "success")
        return _voltar(processo_id)


    @app.route("/registro-imoveis/retificacoes/<int:processo_id>/item",
               methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def ri_retificacao_item(processo_id: int):
        try:
            with db.transaction() as con:
                RT.marcar_item(con, processo_id, _campo("item"),
                               situacao=_campo("situacao"), agora=agora(),
                               usuario=usuario_nome(), nota=_campo("nota"))
        except RT.RetificacaoError as erro:
            flash(str(erro), "danger")
            return _voltar(processo_id)
        audit("RT_ITEM", "rt_conferencia", processo_id,
              {"item": _campo("item"), "situacao": _campo("situacao")})
        return _voltar(processo_id)

    @app.route("/registro-imoveis/retificacoes/<int:processo_id>/confrontante",
               methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def ri_retificacao_confrontante(processo_id: int):
        try:
            with db.transaction() as con:
                RT.anotar_confrontante(
                    con, processo_id, nome=_campo("nome"), agora=agora(),
                    papel=_campo("papel", RT.CONFRONTANTE),
                    documento=_campo("documento"),
                    endereco=_campo("endereco"),
                    matricula_contigua=_campo("matricula_contigua"),
                    serventia_contigua=_campo("serventia_contigua"),
                    divisa_afetada=_campo("divisa_afetada") == "1",
                    assinou_planta=_campo("assinou_planta") == "1",
                    carta_anuencia=_campo("carta_anuencia") == "1",
                    usuario=usuario_nome())
        except RT.RetificacaoError as erro:
            flash(str(erro), "danger")
            return _voltar(processo_id)
        audit("RT_CONFRONTANTE", "rt_confrontantes", processo_id,
              {"nome": _campo("nome")})
        flash("Confrontante anotado.", "success")
        return _voltar(processo_id)

    @app.route("/registro-imoveis/retificacoes/<int:processo_id>/notificar",
               methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def ri_retificacao_notificar(processo_id: int):
        try:
            with db.transaction() as con:
                RT.notificar(con, int(_campo("confrontante_id") or 0),
                             forma=_campo("forma"), quando=_campo("quando"),
                             prazo_ate=_campo("prazo_ate"),
                             recebido_em=_campo("recebido_em"),
                             agora=agora(), usuario=usuario_nome(),
                             # QUEM ASSINA SAI DA REGRA VIVA, e nunca de um
                             # texto escrito no modelo: o cabeçalho do
                             # E-Ofício traz a oficial ANTERIOR.
                             serventia=_serventia_do_papel(),
                             hoje_extenso=_hoje_extenso())
        except (RT.RetificacaoError, ValueError) as erro:
            flash(str(erro), "danger")
            return _voltar(processo_id)
        audit("RT_NOTIFICADO", "rt_confrontantes",
              int(_campo("confrontante_id") or 0), {"forma": _campo("forma")})
        flash("Notificação registrada — e o papel dela está pronto: use "
              "«Imprimir a notificação» na linha do confrontante.", "success")
        return _voltar(processo_id)

    @app.route("/registro-imoveis/retificacoes/<int:processo_id>"
               "/notificacao/<int:confrontante_id>")
    @login_required
    def ri_retificacao_notificacao_papel(processo_id: int,
                                         confrontante_id: int):
        """A notificação do confrontante em PDF (ou .odt). SÓ LÊ.

            «faça ser possível imprimir as notificações da usucapião e da
             georreferenciamento em pdf»        — o oficial, 21/09/2026

        **AQUI NÃO HAVIA PAPEL NENHUM** — ao contrário da usucapião, que tinha
        a tela. Este módulo registrava que notificou e o texto era escrito
        fora do sistema. Ver `rt_notificacao.py`, que o monta da norma.

        O teor sai **como foi congelado** ao notificar; quem foi notificado
        antes desta versão não tem papel, e a tela diz isso em vez de
        remontar um texto que ninguém leu.
        """
        with db.connect() as con:
            linha = banco(con).um(
                """SELECT c.*, p.numero AS processo_numero
                     FROM rt_confrontantes c
                     JOIN rt_processos p ON p.id = c.processo_id
                    WHERE c.id = %s AND c.processo_id = %s""",
                (confrontante_id, processo_id))
        if linha is None:
            abort(404)
        voltar = url_for("ri_retificacao", processo_id=processo_id)
        teor = (linha["teor_expedido"] or "").strip()
        if not teor:
            flash("Esta notificação não guardou o teor — ela foi registrada "
                  "antes da versão que passou a montar o papel, ou por um "
                  "caminho que não o monta. O papel não se remonta: o que "
                  "sairia agora não é o que foi entregue.", "danger")
            return redirect(voltar)
        from ri_odt import gerar_odt, texto_para_odf
        arquivo = gerar_odt(
            texto_para_odf(teor),
            titulo=f"Notificação — retificação {linha['processo_numero']}")
        audit("RT_NOTIFICACAO_IMPRESSA", "rt_confrontantes", confrontante_id,
              {"processo": processo_id, "nome": linha["nome"]})
        nome = safe_component(
            f"notificacao-{linha['processo_numero']}-{linha['nome']}")
        return IMPW.resposta_do_papel(arquivo, nome=nome,
                                      get_setting=db.get_setting,
                                      voltar_para=voltar)

    @app.route("/registro-imoveis/retificacoes/<int:processo_id>/resposta",
               methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def ri_retificacao_resposta(processo_id: int):
        try:
            with db.transaction() as con:
                RT.responder(con, int(_campo("confrontante_id") or 0),
                             resposta=_campo("resposta"), agora=agora(),
                             impugnacao=_campo("impugnacao"),
                             usuario=usuario_nome())
        except (RT.RetificacaoError, ValueError) as erro:
            flash(str(erro), "danger")
            return _voltar(processo_id)
        audit("RT_RESPOSTA", "rt_confrontantes",
              int(_campo("confrontante_id") or 0),
              {"resposta": _campo("resposta")})
        return _voltar(processo_id)

    @app.route("/registro-imoveis/retificacoes/<int:processo_id>/decidir",
               methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER", "REGISTRADOR", "ESCREVENTE")
    def ri_retificacao_decidir(processo_id: int):
        """A DECISÃO É DO DELEGATÁRIO, e o perfil aqui diz isso.

        O art. 604 fala em «decisão fundamentada» do oficial — não é despacho de
        expediente. Quem qualifica e notifica é o balcão; quem decide, não.
        """
        try:
            with db.transaction() as con:
                RT.decidir(con, processo_id, sentido=_campo("sentido"),
                           fundamento=_campo("fundamento"), agora=agora(),
                           hoje=hoje(), usuario=usuario_nome())
        except RT.RetificacaoError as erro:
            flash(str(erro), "danger")
            return _voltar(processo_id)
        audit("RT_DECIDIDO", "rt_processos", processo_id,
              {"sentido": _campo("sentido")})
        flash("Decisão registrada.", "success")
        return _voltar(processo_id)

    @app.route("/registro-imoveis/retificacoes/<int:processo_id>/averbacao",
               methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER", "REGISTRADOR", "ESCREVENTE")
    def ri_retificacao_averbacao(processo_id: int):
        """Amarra o processo à averbação que a TELA DO RI lavrou.

        Esta rota **não lavra nada**. Ela guarda qual foi o ato — e é assim
        porque o desfecho encerra uma matrícula e abre outra, com corrente de
        hash, selo, emolumentos e o nome de quem assina. Um atalho aqui pularia
        os quatro.
        """
        try:
            with db.transaction() as con:
                RT.registrar_averbacao(
                    con, processo_id, ato_id=int(_campo("ato_id") or 0),
                    matricula_nova_id=(int(_campo("matricula_nova_id"))
                                       if _campo("matricula_nova_id") else None),
                    agora=agora(), usuario=usuario_nome())
        except (RT.RetificacaoError, ValueError) as erro:
            flash(str(erro), "danger")
            return _voltar(processo_id)
        audit("RT_AVERBADO", "rt_processos", processo_id,
              {"ato_id": _campo("ato_id")})
        flash("Averbação amarrada ao processo. Se for georreferenciada, a "
              "serventia tem 30 dias para requerer o registro no SIGEF "
              "(art. 620, § 2º).", "success")
        return _voltar(processo_id)

    @app.route("/registro-imoveis/retificacoes/<int:processo_id>/sigef",
               methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER", "REGISTRADOR", "ESCREVENTE")
    def ri_retificacao_sigef(processo_id: int):
        try:
            with db.transaction() as con:
                RT.registrar_sigef(con, processo_id,
                                   protocolo=_campo("protocolo"),
                                   quando=_campo("quando") or hoje(),
                                   agora=agora(), usuario=usuario_nome())
        except RT.RetificacaoError as erro:
            flash(str(erro), "danger")
            return _voltar(processo_id)
        audit("RT_SIGEF", "rt_processos", processo_id,
              {"protocolo": _campo("protocolo")})
        flash("Registro no SIGEF anotado. Processo concluído.", "success")
        return _voltar(processo_id)

    # ------------------------------------------------- a norma, para conferir

    @app.route("/registro-imoveis/retificacoes/codigo-de-normas")
    @login_required
    def ri_retificacao_normas():
        """O que o Código de Normas do TJMA exige, com o artigo ao lado.

        É A TELA QUE O OFICIAL PEDIU NO USUCAPIÃO, e pelo mesmo motivo: **regra
        sem endereço é regra que ninguém confere** — e numa correição quem
        confere é o juiz.
        """
        return render_template("ri_retificacao_normas.html", norma=NORMA,
                               fora=NORMA.fora_das_secoes())
