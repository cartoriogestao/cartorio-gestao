"""As telas do PIX do Protesto — registrar, conferir e confirmar (29/10/2026).

O domínio mora em `protesto_pix` (e o extrato em `pix_credito`); aqui só o
pedido, a resposta, o papel de quem pede e o rastro em `audit_logs`, FORA da
transação, como no resto da casa.

QUEM FAZ O QUÊ
    - Registrar o PIX (com o comprovante) e pedir a conferência no banco:
      o balcão (ADMIN, MANAGER, USER). Robô não registra pagamento.
    - Confirmar o crédito à mão e dar o PIX por não confirmado: o oficial e o
      gerente (ADMIN, MANAGER) — quem confere o caixa —, e o domínio recusa
      quem lançou o PIX.

A CONCILIAÇÃO AO CONTRÁRIO (29/10/2026)
    O dinheiro que entrou e ninguém lançou — o PIX e a TED que batem com um
    título em aberto — aparece na lista e na ficha; o oficial ou o gerente
    descarta o que não for de título nenhum, com o motivo.

QUEM FALA COM O BANCO
    Com o cofre da automação instalado (a casa hoje), a tela NÃO lê a
    credencial do Inter: pede a rodada do processo PROTESTO_PIX_CREDITO, que
    roda no minuto seguinte. Sem o cofre, a tela lê o extrato na hora — só
    leitura, fora de transação.
"""
from __future__ import annotations

from datetime import datetime

from flask import abort, flash, redirect, render_template, request, url_for

import pix_credito as PC
import protesto as PT
import protesto_pix as PIX
from caixa_schema import reais
from seguranca_web import MAIOR_INTEGER, numero_digitado

QUEM_LANCA = ("ADMIN", "MANAGER", "USER")


def registrar_rotas(app, db, login_required, roles_required, audit):
    """Pendura as telas do PIX no app já construído."""

    usuario_nome = app.extensions["usuario_nome"]
    usuario_papel = app.extensions["usuario_papel"]
    usuario_id = app.extensions["usuario_id"]
    pasta_dos_arquivos = app.extensions["archive_root"]

    def agora() -> str:
        return db.now()

    def _campo(nome: str) -> str:
        return (request.form.get(nome) or "").strip()

    def _volta(titulo_id: int | None = None):
        """Para a ficha do título ou para a lista — escolha, e não endereço:
        o destino se monta aqui, do número."""
        if request.form.get("volta") == "ficha" and titulo_id:
            return redirect(url_for("protesto_titulo", titulo_id=titulo_id) + "#pix")
        return redirect(url_for("protesto_pix_lista"))

    def _titulo_do_formulario() -> int | None:
        return numero_digitado(request.form.get("titulo_id"), maximo=MAIOR_INTEGER)

    # A FICHA DO TÍTULO LÊ O PIX DAQUI — a ficha é de `atribuicoes_web`, e o
    # bloco do PIX pede o que mostrar sem que a rota dela mude.
    @app.context_processor
    def _o_pix_na_ficha():
        def pix_do_titulo(titulo_id):
            with db.connect() as con:
                return PIX.para_a_ficha(con, int(titulo_id))
        return {"pix_do_titulo": pix_do_titulo,
                "modelo_da_afirmacao_pix": PIX.modelo_da_afirmacao,
                "minimo_da_afirmacao_pix": 30}

    # ------------------------------------------------------------ registrar

    @app.route("/protesto/<int:titulo_id>/pix", methods=["POST"])
    @login_required
    @roles_required(*QUEM_LANCA)
    def protesto_pix_registrar(titulo_id: int):
        """Registra o PIX declarado, AGUARDANDO O CRÉDITO. ESCREVE.

        Não é pagamento: nenhum ato nasce, e o título fica como está."""
        import selo_robo as SR
        if SR.usuario_e_robo():
            abort(403)
        voltar = redirect(url_for("protesto_titulo", titulo_id=titulo_id) + "#pix")
        enviado = request.files.get("comprovante")
        tem_arquivo = bool(enviado and enviado.filename)
        try:
            with db.transaction() as con:
                r = PIX.registrar(
                    con, titulo_id, valor=_campo("valor_pix"),
                    data_pix=_campo("data_pix"), e2eid=_campo("e2eid") or None,
                    nome=enviado.filename if tem_arquivo else "",
                    conteudo=enviado.read() if tem_arquivo else b"",
                    pasta_de_arquivos=pasta_dos_arquivos(), agora=agora(),
                    usuario=usuario_nome(), usuario_id=usuario_id())
        except PT.ProtestoError as erro:
            flash(str(erro), "danger")
            return voltar
        audit("PROTESTO_PIX_REGISTRADO", "pt_pix", r["pix_id"],
              {"titulo_id": titulo_id, "valor_centavos": r["valor_centavos"],
               "data_pix": r["data_pix"], "e2eid": r["e2eid"],
               "e2eid_lido_do_comprovante": r["e2eid_lido_do_comprovante"],
               "anexo_id": r["anexo_id"]})
        flash(f"PIX de R$ {reais(r['valor_centavos'])} registrado, AGUARDANDO O "
              f"CRÉDITO. O título NÃO está pago: o pagamento se lavra quando o "
              f"crédito for localizado no banco (ou confirmado pelo oficial ou "
              f"pelo gerente)."
              + (f" O identificador do PIX foi lido do comprovante: {r['e2eid']}."
                 if r["e2eid_lido_do_comprovante"] else ""), "warning")
        return voltar

    # ------------------------------------------------------------- a lista

    @app.route("/protesto/pix")
    @login_required
    @roles_required(*QUEM_LANCA)
    def protesto_pix_lista():
        """Os PIX que ainda não viraram pagamento, e as pendências. Só LÊ."""
        with db.connect() as con:
            dados = PIX.lista(con)
            pendencias = PIX.pendencias_do_pix(con)
            sem_pagamento = PIX.creditos_sem_pagamento(con)
        return render_template(
            "protesto_pix.html", dados=dados, pendencias=pendencias,
            sem_pagamento=sem_pagamento,
            modos=PIX.MODOS, com_cofre=PC.com_cofre(),
            processo=PIX.CODIGO_DO_PROCESSO,
            tolerancia=PIX.DIAS_UTEIS_DE_TOLERANCIA,
            pode_confirmar=usuario_papel() in PIX.QUEM_CONFIRMA_A_MAO)

    # ------------------------------------------------------- conferir no banco

    @app.route("/protesto/pix/conferir", methods=["POST"])
    @login_required
    @roles_required(*QUEM_LANCA)
    def protesto_pix_conferir():
        """Pede a conferência do extrato. Só LÊ o banco do Inter.

        Com o cofre: marca o pedido para o despachante da automação. Sem ele:
        lê o extrato agora, fora de transação, e confirma o que achar."""
        titulo_id = _titulo_do_formulario()
        import despesas_inter as INTER
        if PC.com_cofre():
            import automacao
            try:
                with db.transaction() as con:
                    processo = automacao.por_codigo(con, PIX.CODIGO_DO_PROCESSO)
                    if not processo:
                        raise PIX.PixError(
                            f"O processo {PIX.CODIGO_DO_PROCESSO} não está cadastrado na "
                            f"automação: ele nasce no próximo início do servidor.")
                    automacao.pedir_rodada(con, int(processo["id"]),
                                           usuario=usuario_nome())
            except (PIX.PixError, automacao.AutomacaoError) as erro:
                flash(str(erro), "danger")
                return _volta(titulo_id)
            audit("PROTESTO_PIX_CONFERENCIA_PEDIDA", "pt_pix", None,
                  {"processo": PIX.CODIGO_DO_PROCESSO})
            flash(f"Pedido ao despachante da automação: o extrato é consultado no "
                  f"próximo minuto. Para confirmar sozinho, o processo "
                  f"{PIX.CODIGO_DO_PROCESSO} precisa estar com «pode agir» ligado "
                  f"(Automação → processos).", "info")
            return _volta(titulo_id)
        import despesas as DP
        with db.connect() as con:
            cfg = DP.configuracao(con)
        try:
            cliente = PC.cliente_da_casa(cfg)
            r = PIX.conferir_no_banco(db, cliente=cliente,
                                      agora=datetime.now().astimezone(),
                                      por=usuario_nome())
        except INTER.InterError as erro:
            flash(f"O extrato não veio: {erro}", "danger")
            return _volta(titulo_id)
        for c in r["confirmados"]:
            audit("PROTESTO_PIX_CREDITO_CONFERIDO", "pt_pix", c["pix_id"],
                  {"titulo_id": c["titulo_id"], "credito_id": c["credito_id"],
                   "credito_data": c["credito_data"]})
        for n in r["sem_pagamento"]:
            audit("PROTESTO_CREDITO_SEM_PAGAMENTO", "pt_creditos_banco", n["id"],
                  {"titulo_id": n["titulo_id"], "dia": n["dia"], "tipo": n["tipo"]})
        flash(f"{len(r['confirmados'])} PIX com o crédito localizado no extrato; "
              f"{len(r['sem_credito'])} sem crédito localizado"
              + (f"; {len(r['fora_da_janela'])} além dos 90 dias do extrato"
                 if r["fora_da_janela"] else "")
              + f"; {len(r['sem_pagamento'])} crédito(s) novo(s) recebido(s) sem "
                f"pagamento lançado.",
              "success" if r["confirmados"] else "warning")
        return _volta(titulo_id)

    # ------------------------------------------------- confirmar à mão

    @app.route("/protesto/pix/<int:pix_id>/confirmar", methods=["POST"])
    @login_required
    @roles_required(*PIX.QUEM_CONFIRMA_A_MAO)
    def protesto_pix_confirmar(pix_id: int):
        """O oficial ou o gerente confirma o crédito que o sistema não achou,
        com afirmação expressa. ESCREVE."""
        import selo_robo as SR
        try:
            with db.transaction() as con:
                r = PIX.confirmar_a_mao(
                    con, pix_id, papel=usuario_papel(), usuario=usuario_nome(),
                    usuario_id=usuario_id(), por_robo=SR.usuario_e_robo(),
                    afirmo=bool(request.form.get("afirmo")),
                    afirmacao=_campo("afirmacao"),
                    credito_data=_campo("credito_data"), conta=_campo("conta"),
                    agora=agora())
        except PT.ProtestoError as erro:
            flash(str(erro), "danger")
            return _volta(_titulo_do_formulario())
        # O CONTRATO COMUM: a afirmação vai à auditoria FORA da transação.
        audit(PIX.ACAO_DA_AFIRMACAO, "pt_pix", pix_id,
              {k: r[k] for k in ("regra", "afirmacao", "o_que_faltava")})
        audit("PROTESTO_PIX_CONFIRMADO_A_MAO", "pt_pix", pix_id,
              {"titulo_id": r["titulo_id"]})
        flash("Crédito confirmado à mão — a afirmação ficou no PIX e na auditoria. "
              "Agora lance o PAGAMENTO no formulário da ficha: ele já leva o PIX.",
              "success")
        return redirect(url_for("protesto_titulo", titulo_id=r["titulo_id"])
                        + "#lancar-PAGAMENTO")

    @app.route("/protesto/pix/credito/<int:credito_id>/descartar", methods=["POST"])
    @login_required
    @roles_required(*PIX.QUEM_CONFIRMA_A_MAO)
    def protesto_pix_credito_descartar(credito_id: int):
        """O crédito do extrato não é de título nenhum (ou não é deste): sai da
        lista do dinheiro sem pagamento, com o motivo. ESCREVE."""
        try:
            with db.transaction() as con:
                r = PIX.descartar_credito(con, credito_id, papel=usuario_papel(),
                                          usuario=usuario_nome(),
                                          motivo=_campo("motivo"), agora=agora())
        except PT.ProtestoError as erro:
            flash(str(erro), "danger")
            return _volta(_titulo_do_formulario())
        audit("PROTESTO_CREDITO_DESCARTADO", "pt_creditos_banco", credito_id,
              {"titulo_id": r["titulo_id"], "motivo": r["motivo"]})
        flash("Crédito tirado da lista do dinheiro sem pagamento, com o motivo.",
              "success")
        return _volta(_titulo_do_formulario())

    @app.route("/protesto/pix/<int:pix_id>/nao-confirmado", methods=["POST"])
    @login_required
    @roles_required(*PIX.QUEM_CONFIRMA_A_MAO)
    def protesto_pix_nao_confirmado(pix_id: int):
        """O crédito não entrou: o PIX fica não confirmado. ESCREVE."""
        try:
            with db.transaction() as con:
                r = PIX.dar_por_nao_confirmado(
                    con, pix_id, papel=usuario_papel(), usuario=usuario_nome(),
                    motivo=_campo("motivo"), agora=agora())
        except PT.ProtestoError as erro:
            flash(str(erro), "danger")
            return _volta(_titulo_do_formulario())
        audit("PROTESTO_PIX_NAO_CONFIRMADO", "pt_pix", pix_id,
              {"titulo_id": r["titulo_id"], "situacao_antes": r["situacao_antes"],
               "motivo": r["motivo"]})
        flash("PIX dado por não confirmado. O título volta a andar — e, se o "
              "devedor pagar de outro jeito, o pagamento se lança na ficha.",
              "success")
        return _volta(r["titulo_id"])
