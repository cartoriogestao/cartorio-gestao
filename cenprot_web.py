"""As telas do que a CENPROT manda — a fila do balcão.

Ordem do oficial em 02/09/2026: *«pode seguir na construção»*.

**MÓDULO PRÓPRIO, e não mais um pedaço de `atribuicoes_web`.** Aquele arquivo
já passa de quatro mil e quinhentas linhas e serve as telas das quatro
atribuições; este serve **uma integração**, com a sua fila e a sua
configuração. É a razão pela qual `nucleo_web` também nasceu à parte.

**UMA PORTA NO MENU, E AS ESPÉCIES EM ABAS.** São cinco coisas que chegam da
Central — anuência, pedido de certidão, pedido de cancelamento, decisão
judicial e pedido de protesto —, e cinco itens de menu fariam o Protesto
passar de seis para onze numa coluna. É a lição das firmas: *«reconhecimento e
reconhecer firma estão injustificadamente separados»*.

**O NOME DAS ROTAS COMEÇA COM `protesto`, E ISSO NÃO É ESTILO.** A guarda de
módulo do sistema inteiro pergunta a `modulos.modulo_da_tela(request.endpoint)`
de que módulo é a tela, e ela decide pelo prefixo. Rota que fugisse do prefixo
**ficaria de fora do alcance do Protesto** — aberta a todos no dia em que o
oficial fechasse o módulo, sem ninguém ver.

**DECIDIR E ENVIAR SÃO DOIS BOTÕES**, e o domínio é quem recusa. A tela só
oferece o que cabe; quem recusa por dever é `cenprot_pendencias`.
"""
from __future__ import annotations

import base64
import json
import sqlite3

from flask import Response, flash, redirect, render_template, request, url_for

import cenprot_api as API
import cenprot_pendencias as PEND
import centrais_cred as CENTCRED
import cn_schema as CN
import protesto_cenprot as PCEN

# QUEM ENTRA. É o mesmo trio das outras telas do Protesto — a guarda de
# alcance do módulo vem antes, no `before_request`, e é ela que decide se o
# Protesto abre para o balcão ou só para o oficial.
QUEM_OPERA = ("ADMIN", "MANAGER", "USER")

# QUEM CONFIGURA E QUEM MANDA. **Enviar muda coisa na Central** — aprova
# anuência, orça certidão, cancela protesto —, e por isso não é do balcão.
# É a mesma separação da ajuda do Claude: consultar abre, configurar não.
#
# 21/10/2026 — ORDEM DO OFICIAL: «dar acesso às escreventes operarem todo o
# protesto, em especial operar as API, CRA etc.». Era ("ADMIN", "MANAGER"); o
# balcão passou a enviar. Quem decide se o Protesto é do balcão continua sendo
# o alcance do módulo (`modulos_ligados`), que vem antes desta guarda.
QUEM_ENVIA = ("ADMIN", "MANAGER", "USER")

# O QUE VOLTA COMO FRASE, E NAO COMO HTTP 500 — e **o teste de tela me pegou
# sem a terceira**. A falta de credencial estoura `centrais_cred.
# CredencialError`, que nao e nem `PendenciaError` nem `CenprotError`: a rota
# nao a apanhava, e o escrevente levava um 500 por nao ter configurado a
# senha. **Erro de regra nao e HTTP 500** — a regra da casa, quebrada por mim
# em cinco rotas de uma vez.
#
# **E HA DUAS CLASSES COM O MESMO NOME NESTA CASA**, o que torna a lista mais
# necessaria ainda: `cenprot_api.CenprotError` e `RuntimeError` (falha de
# transporte) e `protesto_cenprot.CenprotError` e `ValueError` (regra do
# arquivo). Quem apanhar uma achando que apanha a outra deixa passar a que
# importa — «a mesma palavra em dois lugares nao quer dizer a mesma coisa»,
# pela quinta vez.
RECUSAS_DO_BALCAO = (PEND.PendenciaError, API.CenprotError,
                     CENTCRED.CredencialError)


def registrar_rotas(app, db, login_required, roles_required, audit):
    """Pendura as telas da CENPROT no app já construído."""

    usuario_nome = app.extensions["usuario_nome"]

    def ambiente_pedido() -> str:
        """Qual ambiente a tela usa: **sempre PRODUÇÃO, desde 14/10/2026**.

        Ordem do oficial no primeiro dia do protesto no sistema: «tire a
        opção de funcionar na homologação, agora é tudo produção». Até 13/10
        a tela lia `ambiente` de `request.values` e caía na homologação por
        padrão; agora **o que vier no endereço ou no formulário não muda
        nada** — um favorito antigo com `?ambiente=HOMOLOGACAO` abre a
        produção, e não o ambiente de teste.
        """
        return CENTCRED.PRODUCAO

    def especie_pedida(padrao: str = CN.ANUENCIA) -> str:
        pedida = str(request.values.get("especie") or "").strip().upper()
        return pedida if pedida in CN.ESPECIES else padrao

    # ------------------------------------------------------------- a fila

    @app.route("/protesto/pendencias")
    @roles_required(*QUEM_OPERA)
    def protesto_pendencias_atalho():
        """Bookmark antigo — a tela mora em `/protesto/cenprot/pendencias`."""
        return redirect(url_for("protesto_pendencias", **request.args))

    @app.route("/protesto/cenprot/pendencias")
    @roles_required(*QUEM_OPERA)
    def protesto_pendencias():
        """O que a CENPROT mandou e ainda espera resposta.

        **A LISTA NÃO JULGA PRAZO**, e isso é a regra do módulo do Protesto
        inteiro: um zero aqui pode ser «nada chegou hoje» ou «ainda não
        baixei», e o sistema não tem como saber qual. Ela mostra o número **e
        a última baixa**, que é o que responde a diferença.
        """
        especie = especie_pedida()
        ambiente = ambiente_pedido()
        with db.connect() as con:
            fila = PEND.abertas(con, especie=especie, ambiente=ambiente)
            quadro = PEND.painel(con)
            decididas = PEND.decididas(con, especie, ambiente)
        return render_template(
            "protesto_pendencias.html",
            fila=fila, quadro=quadro, especie=especie, ambiente=ambiente,
            decididas=len(decididas),
            especies=[{"chave": e, "nome": CN.NOME_DA_ESPECIE[e]}
                      for e in CN.ESPECIES],
            so_baixa=(especie in PEND.ESPECIES_QUE_SO_SE_BAIXAM),
            tem_credencial=CENTCRED.tem(CENTCRED.CENPROT, ambiente),
            fora_de_uso=CENTCRED.fora_de_uso(CENTCRED.CENPROT),
            a_conferir=PEND.CODIGO_DO_CANCELAMENTO_A_CONFERIR)

    @app.route("/protesto/cenprot/pendencias/baixar", methods=["POST"])
    @roles_required(*QUEM_OPERA)
    def protesto_pendencias_baixar():
        """Traz da Central o que está pendente. **Não responde nada.**"""
        especie = especie_pedida()
        ambiente = ambiente_pedido()
        filtros: dict = {}
        inicio = str(request.values.get("inicio") or "").strip()
        fim = str(request.values.get("fim") or "").strip()
        # **CADA ESPÉCIE FILTRA COM O NOME DELA**, e os nomes são três
        # convenções diferentes na mesma API — quem monta o parâmetro é
        # `cenprot_api`, e não esta tela.
        if especie in (CN.ANUENCIA, CN.CERTIDAO, CN.CANCELAMENTO):
            filtros = {"inicio": inicio, "fim": fim}
        elif especie == CN.DECISAO_JUDICIAL:
            filtros = {"de": inicio, "ate": fim}
        elif especie == CN.PEDIDO_PROTESTO:
            filtros = {"data": inicio}
        try:
            r = PEND.baixar(db, especie, ambiente=ambiente,
                            quem=usuario_nome(), **filtros)
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_pendencias",
                                    especie=especie, ambiente=ambiente))
        audit("cenprot_baixar", "cn_pendencias", None,
              {"especie": especie, "ambiente": ambiente, **r})
        # **TRÊS NÚMEROS, E NÃO UM.** Dizer «entraram 50» numa baixa em que 48
        # já estavam faria o balcão procurar 50 linhas novas.
        recado = (f"Vieram {r['vieram']}: {r['entraram']} nova(s) e "
                  f"{r['repetidas']} que já estavam.")
        if r["sem_titulo"]:
            recado += (f" {r['sem_titulo']} não casaram com título desta casa "
                       f"— olhe essas primeiro.")
        if r["sem_codigo"]:
            recado += (f" {r['sem_codigo']} vieram sem código e não entraram: "
                       f"sem ele não há como responder à Central.")
        flash(recado, "success" if r["entraram"] else "info")
        return redirect(url_for("protesto_pendencias",
                                especie=especie, ambiente=ambiente))

    # ------------------------------------------------------- uma pendência

    @app.route("/protesto/cenprot/pendencias/<int:pendencia_id>")
    @roles_required(*QUEM_OPERA)
    def protesto_pendencia(pendencia_id: int):
        """A ficha: o teor que a Central mandou, e o que se pode responder."""
        with db.connect() as con:
            p = PEND.uma(con, pendencia_id)
        if p is None:
            flash("Essa pendência não existe.", "warning")
            return redirect(url_for("protesto_pendencias"))
        # **O VALOR DA RETIRADA NÃO SE DIGITA: A CASA JÁ O CALCULA.** É
        # sugestão, e a tela diz de onde ela veio — a mesma regra da receita
        # de custas e da participação das partes na DOI.
        sugerida = {"centavos": None, "reais": "", "motivo": ""}
        if p["especie"] == CN.PEDIDO_PROTESTO:
            with db.connect() as con:
                sugerida = PEND.retirada_sugerida(con, p, hoje=db.now())
        elif p["especie"] in (CN.RENEGOCIACAO, CN.ANUENCIA):
            # A ANUÊNCIA TAMBÉM COTA PELA CUSTA DE CANCELAMENTO — ordem do
            # oficial em 13/10/2026: «são respondidas conforme tabela de
            # emolumentos, cota cada uma». O título está protestado e o credor
            # consentiu em cancelar; o `vl_custas` é o que custa cancelar.
            # Até aqui o campo vinha em branco, com «82,64» de exemplo.
            # **AQUI É A CUSTA DE CANCELAMENTO, E NÃO A RETIRADA.** São dois
            # números diferentes que a mesma função da casa devolve, e trocá-los
            # mandaria à Central um valor que o devedor paga.
            with db.connect() as con:
                sugerida = PEND.custa_de_cancelamento_sugerida(
                    con, p, hoje=db.now())
        pedido = None
        if p["especie"] == CN.CANCELAMENTO:
            # O PEDIDO CHEGA COM A ANUÊNCIA APROVADA E O VALOR DOS EMOLUMENTOS
            # (contrato, `/cancelamento/pedidos`): a tela os mostra ao lado da
            # cotação da tabela da casa, para quem vai lavrar conferir que é o
            # mesmo número que a casa informou — e leva à ficha já preparada.
            with db.connect() as con:
                sugerida = PEND.custa_de_cancelamento_sugerida(
                    con, p, hoje=db.now())
            teor = p.get("teor_aberto") or {}
            pedido = {
                "nr_anuencia": PEND._procurar(teor, "nr_anuencia"),
                "status": PEND._procurar(teor, "status"),
                "emolumentos": PEND._procurar(teor, "vl_emolumentos_cancelamento"),
            }
            fundamento = (
                f"Pedido de cancelamento nº {p['codigo']} recebido pela CENPROT"
                + (f", com a anuência nº {pedido['nr_anuencia']} do credor"
                   if pedido["nr_anuencia"] else "")
                + (f" ({pedido['status']})" if pedido["status"] else "")
                + (f"; emolumentos de R$ {pedido['emolumentos']}"
                   if pedido["emolumentos"] not in (None, "") else "")
                + ".")
            pedido["ficha"] = (url_for("protesto_titulo",
                                       titulo_id=p["titulo_id"],
                                       hipotese="ANUENCIA_CREDOR",
                                       fundamento=fundamento)
                               if p.get("titulo_id") else None)
        return render_template(
            "protesto_pendencia.html", p=p,
            nome_da_especie=CN.NOME_DA_ESPECIE.get(p["especie"], p["especie"]),
            so_baixa=(p["especie"] in PEND.ESPECIES_QUE_SO_SE_BAIXAM),
            teor_bonito=json.dumps(p["teor_aberto"], ensure_ascii=False,
                                   indent=2) if p["teor_aberto"] else p["teor"],
            retirada=sugerida, pedido=pedido,
            a_conferir=PEND.CODIGO_DO_CANCELAMENTO_A_CONFERIR)

    @app.route("/protesto/cenprot/pendencias/<int:pendencia_id>/decidir",
               methods=["POST"])
    @roles_required(*QUEM_ENVIA)
    def protesto_pendencia_decidir(pendencia_id: int):
        """Guarda a decisão do oficial. **NÃO MANDA NADA À CENTRAL.**"""
        with db.connect() as con:
            p = PEND.uma(con, pendencia_id)
        if p is None:
            flash("Essa pendência não existe.", "warning")
            return redirect(url_for("protesto_pendencias"))
        try:
            decisao = _decisao_do_formulario(p)
            with db.transaction() as con:
                PEND.decidir(con, pendencia_id, decisao=decisao,
                             quem=usuario_nome(), agora=db.now())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_pendencia",
                                    pendencia_id=pendencia_id))
        audit("cenprot_decidir", "cn_pendencias", pendencia_id,
              {"especie": p["especie"]})
        flash("Decisão gravada. Ela **ainda não subiu** — use «Enviar as "
              "decididas» na lista quando quiser mandar.", "success")
        return redirect(url_for("protesto_pendencia",
                                pendencia_id=pendencia_id))

    @app.route("/protesto/cenprot/pendencias/<int:pendencia_id>/dispensar",
               methods=["POST"])
    @roles_required(*QUEM_ENVIA)
    def protesto_pendencia_dispensar(pendencia_id: int):
        """Tira da fila, com motivo escrito."""
        try:
            with db.transaction() as con:
                PEND.dispensar(con, pendencia_id,
                               motivo=str(request.values.get("motivo") or ""),
                               quem=usuario_nome(), agora=db.now())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_pendencia",
                                    pendencia_id=pendencia_id))
        audit("cenprot_dispensar", "cn_pendencias", pendencia_id, None)
        flash("Pendência dispensada, com o motivo registrado.", "success")
        return redirect(url_for("protesto_pendencias"))

    # ------------------------------------------------------------- enviar

    @app.route("/protesto/cenprot/pendencias/enviar", methods=["POST"])
    @roles_required(*QUEM_ENVIA)
    def protesto_pendencias_enviar():
        """Sobe à Central o que foi decidido. **ESCREVE NA CENTRAL.**"""
        especie = especie_pedida()
        ambiente = ambiente_pedido()
        try:
            r = PEND.enviar(db, especie, ambiente=ambiente,
                            quem=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_pendencias",
                                    especie=especie, ambiente=ambiente))
        audit("cenprot_enviar", "cn_pendencias", None,
              {"especie": especie, "ambiente": ambiente,
               "enviadas": r["enviadas"]})
        flash(f"Subiram {r['enviadas']} à CENPROT ({ambiente.lower()}). A "
              f"resposta dela ficou gravada em cada uma.", "success")
        return redirect(url_for("protesto_pendencias",
                                especie=especie, ambiente=ambiente))

    # ------------------------------------- os PDFs assinados da anuência

    @app.route("/protesto/cenprot/pendencias/<int:pendencia_id>/arquivos")
    @roles_required(*QUEM_OPERA)
    def protesto_pendencia_arquivos(pendencia_id: int):
        """Baixa da Central os PDFs daquela anuência. SÓ LÊ.

        **A ANUÊNCIA VEM ASSINADA COM e-CPF DA ICP-BRASIL**, no mesmo formato
        PKCS#7 que `assinatura_digital` já lê dos instrumentos desta casa — e é
        ela que prova que o credor consentiu. Sem este botão o oficial teria de
        ir ao site da Central buscar o papel que fundamenta o cancelamento.

        **PEDE-SE PELO `cd_anuencia`, e não pela chave do protesto** — está
        medido no contrato, e eu havia escrito `nm_chave` na primeira versão.
        """
        with db.connect() as con:
            p = PEND.uma(con, pendencia_id)
        if p is None or p["especie"] != CN.ANUENCIA:
            flash("Os arquivos assinados existem só para a anuência.",
                  "warning")
            return redirect(url_for("protesto_pendencias"))
        try:
            # A PENDÊNCIA DIZ DE QUE AMBIENTE ELA É, e a de homologação não se
            # consulta mais (14/10/2026) — a recusa vem com a frase.
            r = API.arquivos_da_anuencia(
                p["codigo"],
                CENTCRED.ambiente_de_uso(CENTCRED.CENPROT, p["ambiente"]))
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_pendencia",
                                    pendencia_id=pendencia_id))
        audit("cenprot_arquivos_anuencia", "cn_pendencias", pendencia_id, None)
        # **O QUE VOLTA É JSON com base64 dentro**, e não o PDF. Entregar isto
        # como `.pdf` faria o navegador abrir um arquivo quebrado; entregar
        # como texto diz a verdade sobre o que a Central mandou.
        return Response(
            json.dumps(r, ensure_ascii=False, indent=2).encode("utf-8"),
            mimetype="application/json; charset=utf-8",
            headers={"Content-Disposition":
                     f'attachment; filename="anuencia-{p["codigo"]}.json"'})

    # ------------------------- o arquivo de emolumentos, pela API em vez do site

    @app.route("/protesto/cenprot/emolumentos/enviar", methods=["POST"])
    @roles_required(*QUEM_ENVIA)
    def protesto_cenprot_emolumentos_enviar():
        """Sobe o arquivo de emolumentos pela API. **ESCREVE NA CENTRAL.**

        É o **passo 8 do roteiro das Centrais**, que até aqui se fazia à mão no
        site. E ele pesa mais do que parece: o roteiro diz que a aprovação da
        anuência é **automática por meio do arquivo de emolumentos** — mandá-lo
        em dia é o que faz a anuência andar sozinha.

        **O ARQUIVO É O MESMO QUE BAIXA, E PELA MESMA FUNÇÃO.** Uma segunda
        montagem «parecida» divergiria no primeiro conserto, e a casa passaria
        a mandar à Central um arquivo diferente do que ela confere na tela —
        é a lição da prévia da ajuda, que usa a mesma função da consulta.

        **E O NOME BATE POR DUAS FONTES**: a forma medida no arquivo que o
        oficial gerou pelo E-Ofício (`MA-2198765-01-E-20260831-01.txt`) é
        exatamente a que o contrato descreve
        (`UF-CODIGOIBGE-NUMEROCARTORIO-E-YYYYMMDD-SS.txt`).
        """
        ambiente = ambiente_pedido()
        config = db.get_settings()
        try:
            casa = PCEN.identidade_da_casa(config)
            with db.connect() as con:
                con.row_factory = sqlite3.Row
                arquivo = PCEN.gerar_emolumentos(
                    con, uf=str(config.get("ri_uf") or "MA").strip(),
                    data=db.now()[:10], **casa)
        except PCEN.CenprotError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_cenprot"))
        if not arquivo["linhas"]:
            # ARQUIVO VAZIO NÃO SE MANDA — a mesma recusa da tela que o baixa.
            flash("Nenhum título entra no arquivo, e cabeçalho sozinho subiria "
                  "dizendo «nenhum protesto tem preço», que é diferente de "
                  "«não há protesto vivo».", "warning")
            return redirect(url_for("protesto_cenprot"))
        try:
            r = API.enviar_custas(
                arquivo["nome"],
                base64.b64encode(arquivo["conteudo"].encode("utf-8")).decode(),
                ambiente)
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_cenprot"))
        audit("cenprot_custas_enviadas", "pt_titulos", None,
              {"arquivo": arquivo["nome"], "linhas": arquivo["linhas"],
               "ambiente": ambiente, "resposta": str(r)[:300]})
        flash(f"Arquivo {arquivo['nome']} subiu à CENPROT "
              f"({ambiente.lower()}) com {arquivo['linhas']} título(s).",
              "success")
        return redirect(url_for("protesto_cenprot"))

    @app.route("/protesto/cenprot/testar", methods=["POST"])
    @roles_required(*QUEM_ENVIA)
    def protesto_cenprot_testar():
        """O botão «testar a conexão». **Não baixa nem envia nada.**

        Sem ele, a primeira notícia de credencial errada seria no meio de um
        download — com o escrevente achando que a Central está vazia.
        """
        ambiente = ambiente_pedido()
        try:
            # SÓ PRODUÇÃO, E DIRETO (14/10/2026). Até 13/10 a homologação
            # passava pela fila comum das Centrais (marco b, 05/10/2026), que
            # não fala com produção; com a homologação fora da tela, o teste
            # é o de produção, direto, como já era.
            d = API.diagnostico(ambiente)
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("protesto_pendencias", ambiente=ambiente))
        nota = ""
        if d.get("fila_id"):
            nota = (f" (teste nº {d['fila_id']} da fila das Centrais — veja "
                    f"em Configurações → Centrais → status.)")
        flash(d["motivo"] + nota, "success" if d["ok"] else "danger")
        return redirect(url_for("protesto_pendencias", ambiente=ambiente))


def _decisao_do_formulario(p: dict) -> dict:
    """O corpo que vai subir, montado do que o oficial marcou na tela.

    **A CONFERÊNCIA DE VERDADE É NO DOMÍNIO E NO TRANSPORTE**, e não aqui: é
    `cenprot_api` que sabe quais campos a Central exige, e ele os confere
    **antes de mandar**. Esta função só traduz o formulário — repetir a regra
    nos dois lugares é como eles divergem.
    """
    teor = p.get("teor_aberto") or {}
    especie = p["especie"]

    # **O TEOR VEM ANINHADO, e a busca tem de ser em qualquer profundidade.**
    # Medido na produção em 13/10/2026: cada anuência chega como
    # `{"dados_anuencia": {cd_anuencia, nm_chave, …, "dados_cartorio": {…}}}`.
    # Esta função lia `teor.get(campo)` — só o primeiro nível —, e com a
    # resposta real o corpo saía sem nenhum dos onze campos que a Central
    # exige de volta: o próprio transporte recusaria, e nenhuma anuência se
    # responderia pela tela. `_procurar` é a mesma régua que a baixa já usa.
    def do_teor(campo: str, padrao=None):
        achado = PEND._procurar(teor, campo)
        return padrao if achado is None else achado

    if especie == CN.ANUENCIA:
        aprovado = str(request.values.get("decisao") or "") == "aprovar"
        # **O CORPO REPETE OS DADOS QUE A CENTRAL MANDOU**, porque ela os
        # exige de volta — são doze campos, e eles vêm do teor congelado, e
        # não de um formulário que alguém redigitaria.
        corpo = {campo: do_teor(campo)
                 for campo, _ in API.CAMPOS_OBRIGATORIOS_DA_ANUENCIA
                 if do_teor(campo) is not None}
        corpo["cd_anuencia"] = do_teor("cd_anuencia", p["codigo"])
        corpo["ic_aprovado"] = aprovado
        if aprovado:
            corpo["vl_custas"] = _numero(request.values.get("vl_custas"))
        else:
            corpo["motivo_recusa"] = str(
                request.values.get("motivo_recusa") or "").strip()
        return corpo

    if especie == CN.CERTIDAO:
        corpo = {"cd_pedido": do_teor("cd_pedido", p["codigo"]),
                 "vl_orcamento": _numero(request.values.get("vl_orcamento"))}
        arquivo = str(request.values.get("arquivo_certidao") or "").strip()
        if arquivo:
            corpo["arquivo_certidao"] = arquivo
        return corpo

    if especie == CN.CANCELAMENTO:
        # **O NÚMERO QUE SOBE É O `nr_pedido` QUE A CENTRAL DEVOLVEU**, e a
        # escolha está declarada em `CODIGO_DO_CANCELAMENTO_A_CONFERIR`: o
        # contrato o chama de `cd_pedido` no envio e de `nr_pedido` aqui.
        corpo = {"cd_pedido": p["codigo"]}
        certidao = str(
            request.values.get("certidao_cancelamento_b64") or "").strip()
        if certidao:
            corpo["certidao_cancelamento_b64"] = certidao
        return corpo

    if especie == CN.PEDIDO_PROTESTO:
        return {"cd_pedido_protesto": do_teor("cd_pedido_protesto",
                                               p["codigo"]),
                "cd_chave_unica": str(
                    request.values.get("cd_chave_unica")
                    or p.get("chave") or "").strip(),
                "nm_nr_protocolo": str(
                    request.values.get("nm_nr_protocolo")
                    or p.get("titulo_protocolo") or "").strip(),
                "dt_protocolo": str(
                    request.values.get("dt_protocolo") or "").strip(),
                "vl_retirada": _numero(request.values.get("vl_retirada"))}

    if especie == CN.RENEGOCIACAO:
        # **SÃO DOIS CAMPOS SÓ, e o contrato os declara `required`.** O que se
        # decide aqui é o VALOR DA CUSTA DE CANCELAMENTO — a proposta em si é
        # do devedor, e esta casa não a aceita nem a recusa: ela diz quanto
        # custa cancelar. É a regra do CNIB outra vez — preparar, e não
        # decidir pelo outro.
        return {"cd_renegociacao_divida": _numero(
                    do_teor("cd_renegociacao_divida", p["codigo"])),
                "vl_custa": _numero(request.values.get("vl_custa"))}

    raise PEND.PendenciaError(
        f"{CN.NOME_DA_ESPECIE.get(especie, especie)} não se responde por esta "
        f"tela — quem registra a ordem do juiz é o oficial, na ficha do "
        f"título.")


def _numero(valor):
    """Lê o valor do formulário. **`None` quando veio em branco, e não zero.**

    Zero é gratuidade, e branco é campo não preenchido — tratá-los como a mesma
    coisa faria o sistema mandar «custou zero» onde ninguém informou nada, e é
    o domínio que tem de recusar o branco.
    """
    texto = str(valor or "").strip().replace(".", "").replace(",", ".")
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None
