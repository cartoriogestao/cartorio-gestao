"""A tela de aprovação das certidões do ONR que o robô preparou (25/10/2026).

O CLIQUE «APROVAR» É A EMISSÃO — no servidor vivo, pela MESMA rota do balcão
    O selo é gasto na aprovação (decisão do oficial). A rota de emissão da
    casa (`ri_emitir_certidao`, `ri_emitir_certidao_negativa`) é chamada por
    um DESPACHO ANINHADO (`_despachar`): um contexto de aplicação NOVO (o `g`
    da requisição de fora não vaza para a de dentro), a sessão de quem clicou
    copiada, e `full_dispatch_request` — que roda o `before_request` (usuário
    ativo, carimbo da senha, token, alcance do módulo), a rota e o
    `after_request`. É quem clicou que emite, e a auditoria diz a verdade.

A SEQUÊNCIA, COM AS TRAVAS NO LUGAR CERTO (revisão do Agente RI, 25/10/2026)
    1. o status do pedido no ONR, ao vivo (rede, fora de transação);
    2. transação CURTA: trava do pedido, «já tem certidão?», EMITINDO com data
       e hora — e COMMIT antes do despacho (a rota trava o número noutra
       conexão; segurar a nossa trava ali seria esperar a si mesmo);
    3. o despacho; os recados da rota de dentro voltam para a tela de fora;
    4. transação curta: a certidão se acha PELO BANCO (`amarrar`), e nunca
       pelo texto do recado;
    5. o papel em PDF, por outro despacho (GET), guardado para o robô assinar.
"""
from __future__ import annotations

import json
from pathlib import Path

from flask import abort, flash, redirect, render_template, request, session, url_for

import onr_certidoes as OC
import onr_certidoes_auto as AUTO
import onr_wsoficio as WS
import ri_onus_ia as RONIA
from bd_nativo import banco

QUEM = ("ADMIN", "MANAGER", "USER")
RECUSAS = (OC.CertidaoOnrError, WS.WSOficioError, AUTO.AutoError)


def registrar_rotas(app, db, login_required, roles_required, audit):
    usuario_nome = app.extensions["usuario_nome"]
    usuario_id = app.extensions["usuario_id"]
    usuario_papel = app.extensions["usuario_papel"]
    archive_root = app.extensions["archive_root"]

    with db.connect() as con:
        OC.init_schema(con)
        AUTO.init_schema(con)

    def agora() -> str:
        return db.now()

    def ambiente() -> str:
        valor = str(db.get_setting("onr_certidoes_ambiente", WS.PRODUCAO) or WS.PRODUCAO)
        return valor if valor in WS.BASE else WS.PRODUCAO

    def status_ao_vivo(protocolo: str) -> str:
        """O status do pedido no ONR AGORA (rede; fora de transação)."""
        r = WS.Sessao(ambiente=ambiente()).certidoes_a_emitir(protocolo=protocolo)
        for p in OC.ler_pedidos(r.get("XML") or ""):
            if p["protocolo"] == protocolo:
                return str(p["status_onr"] or "")
        raise AUTO.AutoError(f"O ONR não devolveu o pedido {protocolo} agora — "
                             "confira no portal. Nada foi emitido.")

    def _despachar(metodo: str, caminho: str, dados: dict | None = None) -> dict:
        """A rota da casa como se quem clicou a chamasse. Ver o cabeçalho."""
        copia = {k: v for k, v in session.items() if k != "_flashes"}
        if dados is not None:
            dados = {**dados, "csrf_token": copia.get("csrf_token", "")}
        with app.app_context():
            with app.test_request_context(caminho, method=metodo, data=dados):
                from flask import session as sessao_de_dentro
                sessao_de_dentro.update(copia)
                resposta = app.full_dispatch_request()
                recados = list(sessao_de_dentro.get("_flashes") or [])
                resposta.direct_passthrough = False
                saida = {"status": resposta.status_code,
                         "location": resposta.headers.get("Location"),
                         "mimetype": resposta.mimetype, "dados": resposta.get_data(),
                         "recados": recados}
        for categoria, texto in recados:
            flash(texto, categoria)
        return saida

    def _pedido_e_preparo(con, pedido_id: int):
        p = OC.pedido(con, pedido_id)
        a = AUTO.preparo(con, pedido_id)
        if not a:
            raise AUTO.AutoError("Este pedido ainda não passou pela automação — rode a busca "
                                 "(ou espere a próxima rodada).")
        return p, a

    def _gerar_pdf(pedido_id: int, certidao_id: int) -> bool:
        """O papel da certidão em PDF, para o robô assinar. Devolve se guardou."""
        saida = _despachar("GET", url_for("ri_certidao_odt", certidao_id=certidao_id,
                                          formato="pdf"))
        try:
            if saida["status"] != 200:
                raise AUTO.AutoError("a tela do papel não devolveu a certidão "
                                     f"(HTTP {saida['status']}).")
            with db.transaction() as con:
                sha = AUTO.guardar_pdf(con, pedido_id, saida["dados"],
                                       pasta=archive_root() / "ri" / "onr" / "certidoes" / "pdf",
                                       usuario_id=usuario_id(), agora=agora())
        except AUTO.AutoError as erro:
            with db.transaction() as con:
                AUTO._gravar(banco(con), pedido_id, agora(),
                             erro=f"PDF: {erro}")
            flash(f"A certidão foi emitida, mas o PDF não: {erro}", "warning")
            return False
        # A PROVA DO PAPEL FICA FORA DA LINHA DO PEDIDO (26/10/2026, M2): o robô
        # só assina o PDF cujo sha está AQUI, com o número da certidão.
        audit(AUTO.ACAO_PDF_GERADO, "onr_cert_pedidos", pedido_id,
              {"certidao_id": int(certidao_id), "sha256": sha})
        return True

    def _voltar(pedido_id: int):
        return redirect(url_for("onr_auto_pedido", pedido_id=pedido_id))

    # ------------------------------------------------------------ as telas

    @app.route("/ri/onr/certidoes/automacao")
    @roles_required(*QUEM)
    def onr_auto_fila():
        import ato_selado as AS
        with db.connect() as con:
            AUTO.init_schema(con)
            lista = AUTO.fila(con)
            contas = AUTO.contar(con)
            selo_pago_ligado = AS.selo_pago_no_onr_ligado(con)
        abertas = [a for a in lista if a["etapa"] not in (AUTO.RESPONDIDO, AUTO.FECHADO)]
        return render_template("onr_auto_fila.html", lista=abertas, contas=contas,
                               selo_pago_ligado=selo_pago_ligado,
                               e_admin=str(usuario_papel() or "").upper() == "ADMIN",
                               nome_da_etapa=AUTO.NOME_DA_ETAPA,
                               esperam_gente=AUTO.ESPERAM_GENTE,
                               rotulo_do_tipo=OC.rotulo_do_tipo,
                               rotulo_do_status=OC.rotulo_do_status)

    @app.route("/ri/onr/certidoes/<int:pedido_id>/automacao")
    @roles_required(*QUEM)
    def onr_auto_pedido(pedido_id: int):
        import ato_selado as AS
        import ri_certidao_emissao as EMISSAO
        import ri_certidao_negativa as RINEG
        from ri_web import teor_seguro
        with db.connect() as con:
            try:
                p, a = _pedido_e_preparo(con, pedido_id)
            except RECUSAS as erro:
                flash(str(erro), "danger")
                return redirect(url_for("onr_certidao_ficha", pedido_id=pedido_id))
            selo_pago_ligado = AS.selo_pago_no_onr_ligado(con)
            dados = json.loads(p.get("dados_json") or "{}")
            certidao = None
            if a.get("certidao_id"):
                certidao = banco(con).um(
                    "SELECT id, numero, ano, tipo, cancelada FROM ri_certidoes WHERE id=%s",
                    (a["certidao_id"],))
            pessoas = []
            if a.get("via") == "PESSOA":
                for g in AUTO.grupos_do_pedido(con, dados):
                    pessoas.append({"grupo": g,
                                    "imoveis": RINEG.candidatas_da_positiva(con, g["chave"])})
        tipo_ri = request.args.get("tipo_ri") or a.get("tipo_ri")
        previa, previa_erro, onus_painel, matricula = "", "", None, None
        if (a["etapa"] == AUTO.A_REVISAR and tipo_ri == "ONUS" and p.get("matricula_id")):
            # O MESMO QUADRO DA FICHA (`_onus_decisao.html`): a leitura da IA, o
            # proprietário conferido, o que se transcreve. A prévia não se monta
            # antes da decisão — o teor da certidão de ônus É a decisão.
            try:
                onus_painel = EMISSAO.painel_do_onus_no_app_vivo(
                    p["matricula_id"], app.config["DATA_DIR"])
                matricula = {"id": p["matricula_id"]}
            except Exception as erro:                       # noqa: BLE001 — a tela não cai
                app.logger.warning("Quadro do ônus do pedido %s falhou.", pedido_id,
                                   exc_info=True)
                previa_erro = type(erro).__name__
        elif (a["etapa"] == AUTO.A_REVISAR and a.get("via") == "MATRICULA"
                and p.get("matricula_id") and tipo_ri in AUTO.TIPOS_RI_DA_APROVACAO):
            try:
                previa = teor_seguro(EMISSAO.previa_no_app_vivo(p["matricula_id"], tipo_ri), "html")
            except Exception as erro:                       # noqa: BLE001 — a tela não cai
                app.logger.warning("Prévia da certidão do pedido %s falhou.", pedido_id,
                                   exc_info=True)
                previa_erro = type(erro).__name__
        return render_template("onr_auto_pedido.html", p=p, a=a, dados=dados,
                               certidao=certidao, pessoas=pessoas, tipo_ri=tipo_ri,
                               selo_pago_ligado=selo_pago_ligado,
                               pode_gerar_pdf=AUTO.pode_gerar_o_pdf(a, usuario_papel()),
                               previa=previa, previa_erro=previa_erro,
                               onus_painel=onus_painel, m=matricula,
                               RESULTADOS_ONUS=RONIA.RESULTADOS,
                               tipos=AUTO.TIPOS_RI_DA_APROVACAO,
                               nome_da_etapa=AUTO.NOME_DA_ETAPA,
                               rotulo_do_tipo=OC.rotulo_do_tipo,
                               rotulo_do_status=OC.rotulo_do_status,
                               tipo_positiva=RINEG.TIPO_POSITIVA, tipo_negativa=RINEG.TIPO)

    # ------------------------------------------------------------ as ações

    @app.route("/ri/onr/certidoes/<int:pedido_id>/automacao/custas", methods=["POST"])
    @roles_required(*QUEM)
    def onr_auto_custas(pedido_id: int):
        try:
            with db.transaction() as con:
                valor = AUTO.aprovar_custas(con, pedido_id, request.form.get("valor"),
                                            usuario=usuario_nome(), agora=agora())
        except RECUSAS as erro:
            flash(str(erro), "danger")
            return _voltar(pedido_id)
        audit("ONR_CERTIDAO_CUSTAS_APROVADAS", "onr_cert_pedidos", pedido_id, {"valor": valor})
        flash(f"Custas de R$ {valor} aprovadas. O robô as informa ao ONR na próxima rodada.", "ok")
        return _voltar(pedido_id)

    @app.route("/ri/onr/certidoes/<int:pedido_id>/automacao/aprovar", methods=["POST"])
    @roles_required(*QUEM)
    def onr_auto_aprovar(pedido_id: int):
        import ri_certidao_negativa as RINEG
        f = request.form
        try:
            with db.connect() as con:
                p, a = _pedido_e_preparo(con, pedido_id)
            if a.get("via") == "MATRICULA":
                tipo_ri = (f.get("tipo_ri") or a.get("tipo_ri") or "").strip().upper()
                if tipo_ri not in AUTO.TIPOS_RI_DA_APROVACAO:
                    raise AUTO.AutoError("Escolha o tipo da certidão.")
            elif a.get("via") == "PESSOA":
                tipo_ri = (f.get("tipo_ri") or a.get("tipo_ri") or "").strip().upper()
                if tipo_ri not in (RINEG.TIPO, RINEG.TIPO_POSITIVA):
                    raise AUTO.AutoError("Escolha entre a certidão negativa e a positiva.")
                if tipo_ri == RINEG.TIPO:
                    with db.connect() as con:
                        AUTO.conferir_negativa_do_pedido(
                            con, json.loads(p.get("dados_json") or "{}"))
            else:
                raise AUTO.AutoError("Este pedido não tem caminho automático: faça à mão.")
            # A emissão que caiu antes de amarrar (27/10/2026): amarra primeiro o
            # que ela gravou, para a nova aprovação não gastar outro selo.
            with db.transaction() as con:
                retomado = AUTO.retomar_emitindo_vencido(con, pedido_id, agora=agora())
            if retomado and retomado.get("certidao_id"):
                flash("A emissão anterior deste pedido já tinha gravado a certidão; ela "
                      "foi amarrada ao pedido, e nenhuma outra foi emitida.", "warning")
                return _voltar(pedido_id)
            if retomado and retomado.get("etapa") == AUTO.ERRO:
                flash("A emissão anterior gravou mais de uma certidão para este pedido; "
                      "nenhuma foi amarrada. O oficial decide qual cancelar.", "danger")
                return _voltar(pedido_id)
            status = status_ao_vivo(p["protocolo"])            # rede, fora de transação
            onus = {}
            if tipo_ri == "ONUS":
                onus = {c: (f.get(c) or "").strip() for c in AUTO.CAMPOS_DO_ONUS if f.get(c)}
                onus["onus_formulario"] = "1"
                onus["onus_item"] = f.getlist("onus_item")
            formulario = {"tipo_ri": tipo_ri, "onus": onus,
                          "pessoa_chave": (f.get("pessoa_chave") or "").strip(),
                          "matriculas_marcadas": f.getlist("matricula_marcada"),
                          "transcricao_justificativa": (f.get("transcricao_justificativa") or "").strip(),
                          "anos": (f.get("anos") or "").strip(),
                          "origens": (f.get("origens") or "").strip()}
            with db.transaction() as con:                       # curta, e COMMIT antes do despacho
                marca = AUTO.marcar_emitindo(con, pedido_id, user_id=usuario_id(),
                                             nome=usuario_nome(), status_onr=status,
                                             formulario=formulario, agora=agora())
        except RECUSAS as erro:
            flash(str(erro), "danger")
            return _voltar(pedido_id)
        comum = {"requerente": p.get("solicitante") or "", "finalidade": marca["marca"],
                 "protocolo": p["protocolo"]}
        if a.get("via") == "MATRICULA":
            dados = {**comum, "tipo": tipo_ri, **formulario["onus"]}
            for campo in ("transcricao_justificativa", "anos", "origens"):
                if formulario[campo]:
                    dados[campo] = formulario[campo]
            alvo = url_for("ri_emitir_certidao", matricula_id=p["matricula_id"])
        else:
            dados = {**comum, "modo": "PESSOA", "busca": a.get("pessoa_busca") or ""}
            if tipo_ri == RINEG.TIPO_POSITIVA:
                dados.update(resultado="POSITIVA", pessoa_chave=formulario["pessoa_chave"],
                             matricula_marcada=formulario["matriculas_marcadas"])
            alvo = url_for("ri_emitir_certidao_negativa")
        _despachar("POST", alvo, dados)
        with db.transaction() as con:
            feito = AUTO.amarrar(con, pedido_id, agora=agora())
        audit("ONR_CERTIDAO_APROVADA", "onr_cert_pedidos", pedido_id,
              {"protocolo": p["protocolo"], "tipo": tipo_ri, "status_onr": status,
               "certidao_id": feito["certidao_id"], "etapa": feito["etapa"]})
        if feito["etapa"] == AUTO.A_ASSINAR:
            if _gerar_pdf(pedido_id, feito["certidao_id"]):
                flash("Certidão emitida e aprovada. O robô a assina com o A3 do oficial e a "
                      "envia ao ONR na próxima rodada.", "ok")
        elif feito["etapa"] == AUTO.SEM_SELO:
            flash("A certidão foi gravada, mas o selo não saiu. Use «Selar» nesta tela.", "warning")
        elif feito["etapa"] == AUTO.A_REVISAR:
            flash("A certidão não foi emitida — o motivo está no recado acima. Corrija e "
                  "aprove de novo.", "danger")
        return _voltar(pedido_id)

    @app.route("/ri/onr/certidoes/<int:pedido_id>/automacao/selar", methods=["POST"])
    @roles_required(*QUEM)
    def onr_auto_selar(pedido_id: int):
        try:
            with db.connect() as con:
                p, a = _pedido_e_preparo(con, pedido_id)
            if a["etapa"] != AUTO.SEM_SELO or not a.get("certidao_id"):
                raise AUTO.AutoError("Este pedido não tem certidão esperando selo.")
            status = status_ao_vivo(p["protocolo"])
            with db.transaction() as con:
                AUTO.reconferir_status(con, pedido_id, status_onr=status, agora=agora())
        except RECUSAS as erro:
            flash(str(erro), "danger")
            return _voltar(pedido_id)
        _despachar("POST", url_for("ri_certidao_selar", certidao_id=a["certidao_id"]), {})
        with db.transaction() as con:
            etapa = AUTO.voltar_a_assinar_depois_do_selo(con, pedido_id, agora=agora())
        audit("ONR_CERTIDAO_SELAR", "onr_cert_pedidos", pedido_id,
              {"certidao_id": a["certidao_id"], "status_onr": status, "etapa": etapa})
        if etapa == AUTO.A_ASSINAR:
            _gerar_pdf(pedido_id, a["certidao_id"])
        return _voltar(pedido_id)

    @app.route("/ri/onr/certidoes/<int:pedido_id>/automacao/pdf", methods=["POST"])
    @roles_required(*QUEM)
    def onr_auto_pdf(pedido_id: int):
        with db.connect() as con:
            a = AUTO.preparo(con, pedido_id)
        if not AUTO.pode_gerar_o_pdf(a, usuario_papel()):
            flash("Só a certidão emitida e esperando o envio tem PDF a gerar (com o pedido em "
                  "erro, só o oficial).", "danger")
            return _voltar(pedido_id)
        if _gerar_pdf(pedido_id, a["certidao_id"]):
            if a["etapa"] == AUTO.ERRO:
                # O oficial conferiu e gerou de novo: o pedido volta a esperar o robô.
                with db.transaction() as con:
                    AUTO._gravar(banco(con), pedido_id, agora(), etapa=AUTO.A_ASSINAR, erro=None)
            flash("PDF gerado. O robô assina e envia na próxima rodada.", "ok")
        return _voltar(pedido_id)

    @app.route("/ri/onr/certidoes/automacao/selo-pago", methods=["POST"])
    @roles_required("ADMIN")
    def onr_auto_selo_pago():
        """Liga ou desliga a forma CENTRAL_ONR (26/10/2026, M5). Só o oficial;
        ligar pede a frase da medição, e os dois ficam na auditoria."""
        import ato_selado as AS
        ligar = request.form.get("acao") == "ligar"
        try:
            with db.transaction() as con:
                AS.ligar_selo_pago_no_onr(con, ligado=ligar, papel=usuario_papel(),
                                          usuario=usuario_nome(), usuario_id=usuario_id(),
                                          justificativa=request.form.get("justificativa"),
                                          agora=agora())
        except AS.AtoError as erro:
            flash(str(erro), "danger")
        else:
            flash("Selo pago no ONR LIGADO." if ligar else
                  "Selo pago no ONR desligado: as certidões pedidas pelo ONR seguem a trava "
                  "normal do selo pago.", "ok")
        return redirect(url_for("onr_auto_fila"))

    @app.route("/ri/onr/certidoes/<int:pedido_id>/automacao/a-mao", methods=["POST"])
    @roles_required(*QUEM)
    def onr_auto_a_mao(pedido_id: int):
        try:
            with db.transaction() as con:
                a = AUTO.preparo(con, pedido_id)
                if not a or a["etapa"] in AUTO.EM_ANDAMENTO:
                    raise AUTO.AutoError("Este pedido já foi emitido pela automação.")
                AUTO.marcar_a_mao(con, pedido_id, request.form.get("motivo"),
                                  usuario=usuario_nome(), agora=agora())
        except RECUSAS as erro:
            flash(str(erro), "danger")
            return _voltar(pedido_id)
        audit("ONR_CERTIDAO_A_MAO", "onr_cert_pedidos", pedido_id,
              {"motivo": (request.form.get("motivo") or "")[:300]})
        flash("Pedido marcado para fazer à mão. Use a ficha do pedido, como antes.", "ok")
        return redirect(url_for("onr_certidao_ficha", pedido_id=pedido_id))
