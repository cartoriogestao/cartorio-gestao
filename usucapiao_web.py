"""
As telas do usucapiao extrajudicial — os autos, como autos.

A FORMA E A DO PROCESSO ELETRONICO, e nao a de um cadastro
    Quem trabalha em cartorio ja leu autos eletronicos. A tela do processo tem
    o que aquela tem: capa, pecas, andamento, prazos, conferencia e decisao —
    nessa ordem, porque e a ordem em que se olha.

    O que ela acrescenta, e que os autos judiciais nao tem: **o que fazer
    agora**, calculado do estado do processo (`proximos_passos`). Num rito de
    meses, a pergunta que mais se repete e "e agora?", e ela merece resposta na
    tela e nao na cabeca de quem lembra.

O RELATORIO PARA QUALIFICACAO SAI DAQUI, E O PARECER VOLTA AQUI
    `/usucapiao/<id>/dossie` EXPORTA o processo inteiro em texto, para copiar
    ou baixar e mandar a quem vai opinar sobre a qualificacao. O parecer VOLTA
    por `/usucapiao/<id>/analise`, cola-se, e ele fica nos autos — com o sha256
    do relatorio que o gerou, para
    se saber depois sobre o que a maquina falou.

    O parecer entra POR CONFERIR. Enquanto o oficial nao o ler, a decisao
    apoiada nela e recusada pelo dominio — ver `usucapiao.decidir`.

FUNDAMENTO
    Lei 6.015/1973, art. 216-A. Codigo de Normas TJMA, arts. 747 a 761.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime

import us_tjma as TJMA

from flask import (Response, abort, flash, redirect, render_template,
                   request, url_for)

import impressao_web as IMPW
import us_notificacao as UN
import usucapiao as US
from serventia import dados as dados_serventia
from storage import safe_component, save_upload

POR_PAGINA = 50


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """Pendura as telas do usucapiao no app ja construido."""

    def agora() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def hoje() -> str:
        return date.today().isoformat()

    def sv() -> dict:
        return dados_serventia(db.get_settings)

    usuario_nome = app.extensions["usuario_nome"]
    usuario_id = app.extensions["usuario_id"]
    archive_root = app.extensions["archive_root"]

    def _campo(nome: str) -> str:
        return (request.form.get(nome) or "").strip()

    def _ler():
        con = db.connect()
        con.row_factory = sqlite3.Row
        return con

    def _pasta_pecas_usucapiao(p: sqlite3.Row | dict) -> object:
        """Pasta própria dos autos no arquivo do Cartório Gestão.

        A peça pode ter vindo do scanner, do balcão ou de um PDF já OCRizado,
        mas depois de juntada ela precisa morar no repositório do sistema — não
        em uma pasta solta do usuário nem no acervo de outro sistema.
        """
        numero = (p["numero"] if p else "") or "sem-numero"
        return (archive_root() / "Usucapiao" /
                safe_component(str(numero), f"Processo-{p['id']}"))

    # ------------------------------------------------------------ a lista

    @app.route("/usucapiao")
    @login_required
    def usucapiao_processos():
        """Os processos, com o que está vencido em destaque."""
        termo = (request.args.get("q") or "").strip()
        etapa = (request.args.get("etapa") or "").strip()
        situacao = (request.args.get("situacao") or "").strip()

        onde, params = [], []
        if termo:
            onde.append("(numero LIKE ? OR requerente_nome LIKE ? "
                        "OR imovel_descricao LIKE ?)")
            params += [f"%{termo}%"] * 3
        if etapa in US.ORDEM_DAS_ETAPAS:
            onde.append("etapa = ?")
            params.append(etapa)
        if situacao in US.SITUACOES:
            onde.append("situacao = ?")
            params.append(situacao)
        filtro = (" WHERE " + " AND ".join(onde)) if onde else ""

        with _ler() as con:
            linhas = [dict(r) for r in con.execute(
                f"SELECT * FROM us_processos{filtro} ORDER BY id DESC LIMIT ?",
                (*params, POR_PAGINA))]
            por_etapa = [dict(r) for r in con.execute(
                "SELECT etapa, COUNT(*) n FROM us_processos GROUP BY etapa")]
            # Quem tem prazo vencido aparece marcado na lista, e não só na
            # ficha: processo que espera resposta é o que se esquece.
            vencidos = {r["processo_id"] for r in con.execute(
                """SELECT DISTINCT processo_id FROM us_movimentos
                    WHERE prazo_fim IS NOT NULL AND respondido_em IS NULL
                      AND prazo_fim < ?""", (hoje(),))}
        return render_template("usucapiao_lista.html", linhas=linhas,
                               por_etapa=por_etapa, vencidos=vencidos,
                               termo=termo, etapa=etapa, situacao=situacao,
                               ETAPAS=US.ETAPAS, SITUACOES=US.SITUACOES,
                               NOME_DA_ETAPA=US.NOME_DA_ETAPA,
                               MODALIDADES=US.MODALIDADES)

    @app.route("/usucapiao/codigo-de-normas")
    @login_required
    def usucapiao_codigo_de_normas():
        """O que a Secao XIV do Codigo de Normas do TJMA manda, artigo por artigo.

        O oficial pediu referencias — «o cadastramento e muito simples e nao
        parece ser maduro para processar um usucapiao no RI com confianca» —, e
        decidiu que eu montasse do Codigo e da lei para ele CONFERIR. Esta tela
        e o lugar de conferir: cada regra com o artigo do lado, para abrir o
        PDF e ler.

        E ela nao decide nada. So le `us_tjma`, que so tem texto.
        """
        return render_template("usucapiao_codigo_de_normas.html", T=TJMA,
                               artigos=TJMA.artigos_citados())

    @app.route("/usucapiao/novo", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def usucapiao_novo():
        """Autua um processo. ESCREVE."""
        try:
            with db.transaction() as con:
                pid = US.autuar(
                    con, numero=_campo("numero"),
                    modalidade=_campo("modalidade"), agora=agora(),
                    requerente_nome=_campo("requerente_nome") or None,
                    requerente_documento=_campo("requerente_documento") or None,
                    imovel_descricao=_campo("imovel_descricao") or None,
                    imovel_municipio=_campo("imovel_municipio") or None,
                    imovel_area=_campo("imovel_area") or None,
                    prenotacao=_campo("prenotacao") or None,
                    posse_inicio=_campo("posse_inicio") or None,
                    usuario=usuario_nome())
        except US.UsucapiaoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("usucapiao_processos"))
        audit("USUCAPIAO_AUTUADO", "us_processos", pid, {})
        flash("Processo autuado. O checklist da modalidade já está montado — "
              "o que falta aparece na ficha.", "success")
        return redirect(url_for("usucapiao_processo", processo_id=pid))

    # ------------------------------------------------------------ a ficha

    @app.route("/usucapiao/<int:processo_id>")
    @login_required
    def usucapiao_processo(processo_id: int):
        """Os autos: capa, peças, andamento, conferência, decisão."""
        with _ler() as con:
            p = US.processo(con, processo_id)
            if not p:
                flash("Processo não encontrado.", "danger")
                return redirect(url_for("usucapiao_processos"))
            pecas = [dict(x) for x in US.pecas(con, processo_id)]
            dados = {
                "p": dict(p),
                "pecas": pecas,
                "anexos_pecas": {
                    x["id"]: [dict(a) for a in db.get_attachments(
                        "USUCAPIAO_PECA", x["id"])]
                    for x in pecas
                },
                "movimentos": [dict(x) for x in US.movimentos(con, processo_id)],
                "conferencia": US.conferir(con, processo_id),
                "passos": US.proximos_passos(con, processo_id, hoje()),
                "faltantes": US.etapas_faltantes(con, processo_id),
                "prazos": US.prazos_abertos(con, processo_id, hoje()),
                "decisoes": [dict(x) for x in US.decisoes(con, processo_id)],
                "analises": [dict(x) for x in US.analises(con, processo_id)],
                "modelos": US.modelos_de_decisao(p, sv()),
            }
        return render_template(
            "usucapiao_ficha.html", **dados, hoje=hoje(),
            ETAPAS=US.ETAPAS, NOME_DA_ETAPA=US.NOME_DA_ETAPA,
            MODALIDADES=US.MODALIDADES, TIPOS_DE_PECA=US.TIPOS_DE_PECA,
            TIPOS_DE_MOVIMENTO=US.TIPOS_DE_MOVIMENTO, RESPOSTAS=US.RESPOSTAS,
            SENTIDOS=US.SENTIDOS, ENTES=US.ENTES_PUBLICOS,
            ORDEM=US.ORDEM_DAS_ETAPAS,
            # AS LISTAS DA NORMA vao para a tela do modulo que as tem, e nao
            # escritas no template: escritas la, divergiriam do Codigo no
            # primeiro conserto — e a tela ofereceria uma forma de notificar
            # que a norma nao preve.
            FORMAS_DE_NOTIFICAR=UN.FORMAS, ONDE_NOTIFICAR=UN.ONDE,
            PRAZOS_DA_NOTIFICACAO=UN.PRAZOS,
            TENTATIVAS=_tentativas_por_destinatario(dados["movimentos"]))

    # ------------------------------------------------------ o que se lança

    @app.route("/usucapiao/<int:processo_id>/peca", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def usucapiao_juntar(processo_id: int):
        """Junta documento(s) aos autos. ESCREVE."""
        voltar = redirect(url_for("usucapiao_processo", processo_id=processo_id))
        arquivos = [f for f in request.files.getlist("documento") if f and f.filename]
        if not arquivos:
            info = None
            try:
                with db.transaction() as con:
                    peca_id = US.juntar_peca(
                        con, processo_id, tipo=_campo("tipo"), agora=agora(),
                        descricao=_campo("descricao") or None,
                        nome_arquivo=_campo("nome_arquivo") or None,
                        caminho=_campo("caminho") or None,
                        sha256=None,
                        bytes_=None,
                        teor=_campo("teor") or None, usuario=usuario_nome())
            except US.UsucapiaoError as erro:
                flash(str(erro), "danger")
                return voltar
            audit("USUCAPIAO_PECA", "us_pecas", peca_id, {"processo": processo_id})
            flash("Documento juntado. O que ele cumpre no checklist ja foi "
                  "marcado.", "success")
            return voltar

        with _ler() as con:
            p = US.processo(con, processo_id)
            if not p:
                flash("Processo nao encontrado.", "danger")
                return voltar
            pasta = _pasta_pecas_usucapiao(p)

        nomes = []
        for upload in arquivos:
            try:
                info = save_upload(upload, pasta)
                with db.transaction() as con:
                    peca_id = US.juntar_peca(
                        con, processo_id, tipo=_campo("tipo"), agora=agora(),
                        descricao=_campo("descricao") or None,
                        nome_arquivo=info["original_name"],
                        caminho=info["stored_path"],
                        sha256=info["sha256"],
                        bytes_=info["size_bytes"],
                        teor=_campo("teor") or None, usuario=usuario_nome())
                att = db.add_attachment(
                    "USUCAPIAO_PECA", peca_id, info, int(usuario_id() or 0),
                    _campo("descricao") or US.TIPOS_DE_PECA.get(_campo("tipo")))
                audit("USUCAPIAO_PECA_ARQUIVO", "attachments", att,
                      {"peca": peca_id, "processo": processo_id})
                audit("USUCAPIAO_PECA", "us_pecas", peca_id, {"processo": processo_id})
                nomes.append(info.get("original_name") or upload.filename)
            except US.UsucapiaoError as erro:
                flash(str(erro), "danger")
                return voltar
        if len(nomes) == 1:
            flash(f"{nomes[0]} juntado aos autos.", "success")
        else:
            flash(f"{len(nomes)} documentos juntados aos autos.", "success")
        return voltar


    def _tentativas_por_destinatario(movimentos) -> dict:
        """Quem já foi notificado, por quais formas, e **qual é a próxima**.

        Relato #30. **A ORDEM DAS FORMAS É DA NORMA** — art. 598 — e o edital
        só cabe «caso frustradas as tentativas anteriores». Quem vai expedir a
        segunda notificação precisa ver, na tela, o que já se tentou: sem isso
        ele repete a mesma forma, ou pula direto para o edital — que custa,
        demora, e sem a frustração registrada é nulo.
        """
        por_quem: dict[str, dict] = {}
        for m in movimentos:
            if m.get("tipo") != "NOTIFICACAO":
                continue
            quem = (m.get("destinatario") or "").strip()
            if not quem:
                continue
            registro = por_quem.setdefault(
                quem, {"formas": [], "papel": m.get("destinatario_papel") or "",
                       "endereco": m.get("endereco") or ""})
            forma = (m.get("forma") or "").strip().upper()
            if forma and forma not in registro["formas"]:
                registro["formas"].append(forma)
        for registro in por_quem.values():
            seguinte = UN.forma_seguinte(registro["formas"])
            registro["seguinte"] = seguinte
            registro["seguinte_rotulo"] = (
                UN.FORMA_POR_CHAVE.get(seguinte, {}).get("o_que", "")
                if seguinte else "")
        return por_quem

    def _serventia_do_papel() -> dict:
        """Quem assina o papel — da regra viva, e nunca escrito no modelo.

        **O cabeçalho do E-Ofício trazia a oficial ANTERIOR**, com endereço e
        CEP diferentes; copiá-lo para dentro de um modelo traria o oficial de
        ontem para o papel de hoje. Sai daqui, que é onde a casa se cadastra.
        """
        # A MONTAGEM MORA EM `serventia.quem_assina_o_papel`, e nao aqui:
        # a notificacao da retificacao monta o mesmo bloco, e duas copias
        # divergiriam no primeiro conserto (21/09/2026).
        from serventia import quem_assina_o_papel
        return quem_assina_o_papel(sv())

    def _hoje_extenso() -> str:
        # A MESMA FUNCAO DO RESTO DA CASA, e nao uma segunda montagem: duas
        # formas de escrever a data por extenso divergiriam no primeiro
        # conserto, e o papel da notificacao passaria a discordar da certidao.
        # Ela recebe um Sun Aug 30 21:30:44 HPBA 2026, e nao texto.
        from ri_web import data_por_extenso
        s = sv()
        lugar = s.get("cidade_uf") or s.get("ri_cidade") or ""
        data = data_por_extenso(date.today())
        return f"{lugar}, {data}" if lugar else data

    @app.route("/usucapiao/<int:processo_id>/edital", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def usucapiao_edital(processo_id: int):
        """Monta o edital para terceiros e lança o movimento. ESCREVE."""
        voltar = redirect(url_for("usucapiao_processo",
                                  processo_id=processo_id))
        try:
            with db.transaction() as con:
                r = US.publicar_edital(
                    con, processo_id, agora=agora(),
                    serventia=_serventia_do_papel(),
                    hoje_extenso=_hoje_extenso(),
                    imovel_sem_origem=bool(_campo("sem_origem")),
                    disponibilizado_em=_campo("disponibilizado_em") or None,
                    usuario=usuario_nome())
        except (US.UsucapiaoError, UN.NotificacaoError, ValueError) as erro:
            flash(str(erro), "danger")
            return voltar
        audit("USUCAPIAO_EDITAL", "us_movimentos", r["movimento_id"],
              {"processo": processo_id})
        flash("Edital montado. **Publique na Central** e anote o protocolo — "
              "o prazo não conta da disponibilização: são dois dias úteis "
              "encadeados (art. 755, § 1º).", "success")
        return redirect(url_for("usucapiao_notificacao_papel",
                                processo_id=processo_id,
                                movimento_id=r["movimento_id"]))

    @app.route("/usucapiao/<int:processo_id>/ciencia-aos-entes",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def usucapiao_ciencia_entes(processo_id: int):
        """Monta os TRÊS ofícios de ciência. ESCREVE.

        **Os três de uma vez** — deixar escolher qual abriria a porta para
        avisar dois, e o vício de faltar um só aparece depois do registro.
        """
        voltar = redirect(url_for("usucapiao_processo",
                                  processo_id=processo_id))
        try:
            with db.transaction() as con:
                r = US.dar_ciencia_aos_entes(
                    con, processo_id, agora=agora(),
                    serventia=_serventia_do_papel(),
                    hoje_extenso=_hoje_extenso(), usuario=usuario_nome())
        except (US.UsucapiaoError, UN.NotificacaoError, ValueError) as erro:
            flash(str(erro), "danger")
            return voltar
        audit("USUCAPIAO_CIENCIA_ENTES", "us_movimentos", processo_id,
              {"entes": [x["ente"] for x in r]})
        flash(f"Os {len(r)} ofícios foram montados — "
              + ", ".join(x["ente"] for x in r)
              + ". Use «Abrir para imprimir» em cada linha do andamento e "
                "junte os comprovantes aos autos.",
              "success")
        return redirect(url_for("usucapiao_processo", processo_id=processo_id)
                        + "#andamento")

    @app.route("/usucapiao/<int:processo_id>/notificar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def usucapiao_notificar(processo_id: int):
        """Expede notificação: confere, monta o papel e lança o movimento.

        Relato #30 do oficial. ESCREVE.

        **O PAPEL É CONFERIDO ANTES DE O MOVIMENTO EXISTIR.** Se faltar
        endereço, ou a forma não for uma das quatro da norma, nada é gravado:
        movimento de notificação sem papel que o sustente é uma linha dizendo
        que a serventia notificou alguém sem ter notificado.
        """
        voltar = redirect(url_for("usucapiao_processo",
                                  processo_id=processo_id))
        try:
            with db.transaction() as con:
                r = US.notificar(
                    con, processo_id,
                    destinatario=_campo("destinatario"),
                    destinatario_papel=_campo("destinatario_papel"),
                    endereco=_campo("endereco"),
                    forma=_campo("forma"),
                    prazo_chave=_campo("prazo_chave"),
                    tentativa=int(_campo("tentativa") or 0) or None,
                    agora=agora(), serventia=_serventia_do_papel(),
                    hoje_extenso=_hoje_extenso(), usuario=usuario_nome())
        except (US.UsucapiaoError, UN.NotificacaoError, ValueError) as erro:
            flash(str(erro), "danger")
            return voltar
        audit("USUCAPIAO_NOTIFICACAO", "us_movimentos", r["movimento_id"],
              {"processo": processo_id, "forma": _campo("forma")})
        flash("Notificação expedida. **Imprima o papel e entregue** — o que "
              "prova a notificação é o comprovante que volta assinado, e ele se "
              "junta ao processo como peça.", "success")
        return redirect(url_for("usucapiao_notificacao_papel",
                                processo_id=processo_id,
                                movimento_id=r["movimento_id"]))

    @app.route("/usucapiao/<int:processo_id>/notificacao/<int:movimento_id>")
    @roles_required("ADMIN", "MANAGER", "USER")
    def usucapiao_notificacao_papel(processo_id: int, movimento_id: int):
        """O papel da notificação, para imprimir. SÓ LÊ.

        **Sai o teor GUARDADO, e não um remontado agora.** Remontar traria o
        processo como ele está hoje, e não como estava quando o papel saiu — e
        o que o notificado leu é o de então. É a mesma regra do termo do
        Registro Civil e da certidão de protesto.
        """
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            mov = con.execute(
                "SELECT * FROM us_movimentos WHERE id=? AND processo_id=?",
                (movimento_id, processo_id)).fetchone()
            p = US.processo(con, processo_id)
        if mov is None or p is None:
            abort(404)
        teor = (mov["teor_expedido"] or "").strip()
        if not teor:
            flash("Este movimento não guardou o teor da notificação — ele é "
                  "anterior à versão que passou a guardá-lo. O papel não se "
                  "remonta: o que sairia agora não é o que foi entregue.",
                  "danger")
            return redirect(url_for("usucapiao_processo",
                                    processo_id=processo_id))
        return render_template("usucapiao_notificacao.html", p=p, mov=mov,
                               teor=teor)

    @app.route("/usucapiao/<int:processo_id>/notificacao/"
               "<int:movimento_id>/papel")
    @roles_required("ADMIN", "MANAGER", "USER")
    def usucapiao_notificacao_arquivo(processo_id: int, movimento_id: int):
        """O papel da notificação em PDF (ou .odt). SÓ LÊ.

            «faça ser possível imprimir as notificações da usucapião e da
             georreferenciamento em pdf»        — o oficial, 21/09/2026

        **A TELA JÁ EXISTIA, E ELA NÃO É UM ARQUIVO.** O papel saía como
        página do navegador, com o botão «Imprimir» chamando a caixa de
        impressão do navegador — e quem trabalha por acesso remoto clica ali e
        a caixa abre **na outra máquina**. Foi o relato #88, de hoje: «aparece
        que gerou porém não consigo acessar». Os três ofícios de ciência
        estavam gravados, com teor (682, 683 e 686 caracteres), e o que
        faltava era um arquivo para levar.

        **O TEOR É O CONGELADO**, e não um remontado agora — a mesma regra da
        tela. `?formato=odt` entrega o editável.
        """
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            mov = con.execute(
                "SELECT * FROM us_movimentos WHERE id=? AND processo_id=?",
                (movimento_id, processo_id)).fetchone()
            p = US.processo(con, processo_id)
        if mov is None or p is None:
            abort(404)
        voltar = url_for("usucapiao_processo", processo_id=processo_id)
        teor = (mov["teor_expedido"] or "").strip()
        if not teor:
            flash("Este movimento não guardou o teor da notificação — ele é "
                  "anterior à versão que passou a guardá-lo. O papel não se "
                  "remonta: o que sairia agora não é o que foi entregue.",
                  "danger")
            return redirect(voltar)
        from ri_odt import gerar_odt, texto_para_odf
        quem = (mov["destinatario"] or "").strip()
        arquivo = gerar_odt(
            texto_para_odf(teor),
            titulo=f"Notificação — usucapião {p['numero']}")
        audit("USUCAPIAO_NOTIFICACAO_IMPRESSA", "us_movimentos", movimento_id,
              {"processo": processo_id, "destinatario": quem})
        nome = safe_component(
            f"notificacao-{p['numero']}-{quem or movimento_id}")
        return IMPW.resposta_do_papel(arquivo, nome=nome,
                                      get_setting=db.get_setting,
                                      voltar_para=voltar)

    @app.route("/usucapiao/notificacao/manual")
    @roles_required("ADMIN", "MANAGER", "USER")
    def usucapiao_manual_notificacao():
        """O manual de como efetuar a notificação. SÓ LÊ."""
        return render_template("usucapiao_manual.html", manual=UN.MANUAL,
                               formas=UN.FORMAS, onde=UN.ONDE,
                               prazos=UN.PRAZOS, base=UN.BASE_DA_REMISSAO,
                               silencio=UN.SILENCIO_CONCORDA,
                               medido=UN.MEDIDO, citado=UN.CITADO)

    @app.route("/usucapiao/<int:processo_id>/movimento", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def usucapiao_movimentar(processo_id: int):
        """Lança movimento — notificação, ciência, edital, diligência. ESCREVE."""
        voltar = redirect(url_for("usucapiao_processo", processo_id=processo_id))
        try:
            with db.transaction() as con:
                mid = US.movimentar(
                    con, processo_id, tipo=_campo("tipo"),
                    descricao=_campo("descricao"), agora=agora(),
                    destinatario=_campo("destinatario") or None,
                    destinatario_papel=_campo("destinatario_papel") or None,
                    prazo_dias=int(_campo("prazo_dias") or 0) or None,
                    prazo_inicio=_campo("prazo_inicio") or None,
                    prazo_fim=_campo("prazo_fim") or None,
                    usuario=usuario_nome())
        except (US.UsucapiaoError, ValueError) as erro:
            flash(str(erro), "danger")
            return voltar
        audit("USUCAPIAO_MOVIMENTO", "us_movimentos", mid,
              {"processo": processo_id})
        flash("Movimento lançado.", "success")
        return voltar

    @app.route("/usucapiao/<int:processo_id>/responder/<int:movimento_id>",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def usucapiao_responder(processo_id: int, movimento_id: int):
        """Registra a resposta a uma notificação — inclusive o silêncio. ESCREVE.

        O SILÊNCIO É RESPOSTA. No rito do art. 216-A ele tem efeito, e por isso
        é um valor a gravar, e não a ausência de um.
        """
        voltar = redirect(url_for("usucapiao_processo", processo_id=processo_id))
        resposta = _campo("resposta")
        if resposta not in US.RESPOSTAS:
            flash(f"Resposta desconhecida: {resposta!r}.", "danger")
            return voltar
        with db.transaction() as con:
            con.execute(
                """UPDATE us_movimentos SET respondido_em=?, resposta=?,
                       resposta_teor=? WHERE id=? AND processo_id=?""",
                (agora(), resposta, _campo("resposta_teor") or None,
                 movimento_id, processo_id))
            US.movimentar(
                con, processo_id, tipo="RESPOSTA",
                descricao=(f"{US.RESPOSTAS[resposta]}"
                           + (f" — {_campo('resposta_teor')}"
                              if _campo("resposta_teor") else "")),
                agora=agora(), usuario=usuario_nome())
        audit("USUCAPIAO_RESPOSTA", "us_movimentos", movimento_id,
              {"resposta": resposta})
        flash(f"Registrado: {US.RESPOSTAS[resposta]}.", "success")
        return voltar

    @app.route("/usucapiao/<int:processo_id>/conferencia", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def usucapiao_conferencia(processo_id: int):
        """Marca item do checklist. ESCREVE."""
        voltar = redirect(url_for("usucapiao_processo", processo_id=processo_id))
        try:
            with db.transaction() as con:
                US.marcar_item(con, processo_id, _campo("item"),
                               estado=_campo("estado"), agora=agora(),
                               motivo=_campo("motivo") or None,
                               anotacao=_campo("anotacao") or None,
                               usuario=usuario_nome())
        except US.UsucapiaoError as erro:
            flash(str(erro), "danger")
            return voltar
        flash("Conferência atualizada.", "success")
        return voltar

    @app.route("/usucapiao/<int:processo_id>/etapa", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def usucapiao_etapa(processo_id: int):
        """Move o processo de etapa. ESCREVE."""
        voltar = redirect(url_for("usucapiao_processo", processo_id=processo_id))
        try:
            with db.transaction() as con:
                US.avancar(con, processo_id, etapa=_campo("etapa"),
                           agora=agora(), usuario=usuario_nome())
        except US.UsucapiaoError as erro:
            flash(str(erro), "danger")
            return voltar
        flash("Etapa alterada.", "success")
        return voltar

    # ------------------------------- o relatório para qualificação

    @app.route("/usucapiao/<int:processo_id>/dossie")
    @roles_required("ADMIN", "MANAGER", "USER")
    def usucapiao_dossie(processo_id: int):
        """O processo em texto, para mandar a quem vai opinar. Só LÊ.

        `?mascarar=nao` traz os documentos inteiros — e o próprio dossiê avisa
        disso no rodapé, para quem receber saber o que tem em mãos.
        `?formato=txt` baixa como arquivo.
        """
        mascarar = (request.args.get("mascarar") or "").lower() != "nao"
        with _ler() as con:
            p = US.processo(con, processo_id)
            if not p:
                flash("Processo não encontrado.", "danger")
                return redirect(url_for("usucapiao_processos"))
            d = US.montar_dossie(con, processo_id, hoje=hoje(),
                                 mascarar=mascarar)
        # Gerar dossiê é tirar dado da casa: fica na auditoria, com o sha256 do
        # que saiu e se foi mascarado.
        audit("USUCAPIAO_DOSSIE", "us_processos", processo_id,
              {"sha256": d["sha256"], "pecas": d["pecas"],
               "mascarado": d["mascarado"]})
        if (request.args.get("formato") or "").lower() == "txt":
            nome = f"usucapiao-{d['numero']}.md".replace("/", "-")
            return Response(
                d["texto"], mimetype="text/markdown; charset=utf-8",
                headers={"Content-Disposition":
                         f'attachment; filename="{nome}"'})
        return render_template("usucapiao_dossie.html", d=d, p=dict(p),
                               mascarar=mascarar)

    @app.route("/usucapiao/<int:processo_id>/analise", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def usucapiao_analise(processo_id: int):
        """Junta aos autos o parecer que voltou. ESCREVE.

        Entra POR CONFERIR: enquanto o oficial não a ler, a decisão apoiada
        nela é recusada pelo domínio.
        """
        voltar = redirect(url_for("usucapiao_processo", processo_id=processo_id))
        achados = None
        bruto = _campo("achados_json")
        if bruto:
            try:
                achados = json.loads(bruto)
            except ValueError:
                flash("Os achados não estão em JSON válido. O parecer em texto "
                      "basta — os achados são opcionais.", "danger")
                return voltar
        try:
            with db.transaction() as con:
                aid = US.registrar_analise(
                    con, processo_id, parecer=_campo("parecer"), agora=agora(),
                    ferramenta=_campo("ferramenta") or None,
                    dossie_sha256=_campo("dossie_sha256") or None,
                    achados=achados, usuario=usuario_nome(),
                    observacao=_campo("observacao") or None)
        except US.UsucapiaoError as erro:
            flash(str(erro), "danger")
            return voltar
        audit("USUCAPIAO_ANALISE", "us_analises", aid, {"processo": processo_id})
        flash("Análise juntada aos autos. Ela ainda precisa da sua conferência "
              "antes de servir de apoio à decisão.", "success")
        return voltar

    @app.route("/usucapiao/<int:processo_id>/analise/<int:analise_id>/conferir",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def usucapiao_conferir_analise(processo_id: int, analise_id: int):
        """O oficial diz que leu a análise. ESCREVE."""
        voltar = redirect(url_for("usucapiao_processo", processo_id=processo_id))
        try:
            with db.transaction() as con:
                US.conferir_analise(con, analise_id, agora=agora(),
                                    usuario=usuario_nome(),
                                    observacao=_campo("observacao") or None)
        except US.UsucapiaoError as erro:
            flash(str(erro), "danger")
            return voltar
        audit("USUCAPIAO_ANALISE_CONFERIDA", "us_analises", analise_id, {})
        flash("Análise conferida. Conferir não é concordar: é ter lido, e "
              "assumir o que se faz com aquilo.", "success")
        return voltar

    # ----------------------------------------------------------- a decisão

    @app.route("/usucapiao/<int:processo_id>/decidir", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def usucapiao_decidir(processo_id: int):
        """Lavra a decisão do oficial. ESCREVE."""
        voltar = redirect(url_for("usucapiao_processo", processo_id=processo_id))
        analise = _campo("analise_id")
        try:
            with db.transaction() as con:
                did = US.decidir(
                    con, processo_id, sentido=_campo("sentido"),
                    fundamento=_campo("fundamento"), teor=_campo("teor"),
                    modelo=_campo("modelo") or None,
                    analise_id=int(analise) if analise else None,
                    agora=agora(), usuario=usuario_nome())
        except (US.UsucapiaoError, ValueError) as erro:
            flash(str(erro), "danger")
            return voltar
        audit("USUCAPIAO_DECISAO", "us_decisoes", did,
              {"processo": processo_id, "sentido": _campo("sentido")})
        flash("Decisão lavrada.", "success")
        return voltar

    @app.route("/usucapiao/<int:processo_id>/registrar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def usucapiao_registrar(processo_id: int):
        """Amarra o registro feito à decisão que o determinou. ESCREVE."""
        voltar = redirect(url_for("usucapiao_processo", processo_id=processo_id))
        try:
            with db.transaction() as con:
                US.registrar_reconhecimento(
                    con, processo_id, ato_id=int(_campo("ato_id") or 0),
                    selo=_campo("selo") or None, agora=agora(),
                    usuario=usuario_nome())
        except (US.UsucapiaoError, ValueError) as erro:
            flash(str(erro), "danger")
            return voltar
        audit("USUCAPIAO_REGISTRADO", "us_processos", processo_id, {})
        flash("Processo registrado e encerrado.", "success")
        return voltar
