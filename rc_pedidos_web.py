"""As telas da Central de Certidões — a fila, a ficha e a certidão eletrônica.

A TELA NÃO REPETE A REGRA DO DOMÍNIO. Ela só *oferece*; quem *recusa* é
`rc_pedidos.py`, e há teste que manda a ação fora de ordem direto para a
função.

**CONFERIR E ENVIAR SÃO DOIS BOTÕES**, como na remessa da CRA e no e-Proclamas:
o que sobe **entrega documento e é cobrado**.

**E ENVIAR NÃO É DO BALCÃO.** Conferir e baixar a fila são de quem atende;
cumprir, rejeitar, assinar e cancelar são do oficial e do gerente — a mesma
separação da CENPROT e da ajuda do Claude.

**A FILA VAZIA DIZ POR QUÊ.** Lista vazia sem a faixa da credencial faz o
operador achar que não há trabalho quando o que há é falta de token — é a lição
da tela de assinaturas, que custou três respostas.
"""
from __future__ import annotations

import json

from flask import Response, flash, redirect, render_template, request, url_for

import arquivo_visivel as VIS
from bd_nativo import banco
import centrais_cred as CRED
import onrcpn_certidao_api as API
import rc_certidao as RCE
import rc_pedidos as PED
import rc_pedidos_schema as ESQ
from seguranca_web import MAIOR_INTEGER, numero_digitado  # LD13: o número que a tela mandou

# QUEM VÊ E QUEM RESPONDE. Ver o cabeçalho.
QUEM_CONFERE = ("ADMIN", "MANAGER", "USER")
QUEM_RESPONDE = ("ADMIN", "MANAGER")

# AS RECUSAS QUE VIRAM AVISO NA TELA, e não HTTP 500.
#
#   `CredencialError` está aqui porque a sua falta é o caso mais comum numa
#   integração nova — foi o que o teste de tela pegou na CENPROT, em cinco
#   rotas de uma vez.
RECUSAS_DO_BALCAO = (PED.PedidoError, API.CertidaoError, CRED.CredencialError)


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """Pendura as telas da Central de Certidões no app já construído."""

    usuario_nome = app.extensions["usuario_nome"]

    def agora() -> str:
        return db.now()

    def _cns() -> str:
        return str(db.get_setting("serventia_cns", "") or "").strip() \
            or str(db.get_setting("ri_cns", "") or "").strip()

    def _uf() -> str:
        return str(db.get_setting("ri_uf", "") or "").strip().upper()

    def _valores_da_certidao() -> dict:
        """O que a tela de conferência oferece mandar junto do registro."""
        return {
            "selo": (request.values.get("selo") or "").strip(),
            "cod_selo": (request.values.get("cod_selo") or "").strip(),
            "cota_emolumentos":
                (request.values.get("cota_emolumentos") or "").strip(),
            "cota_isento": bool(request.values.get("cota_isento")),
            "tipo_registro":
                (request.values.get("tipo_registro") or "").strip() or None,
            "tipo_certidao":
                (request.values.get("tipo_certidao") or "").strip() or None,
        }

    # -------------------------------------------------------------- a fila

    @app.route("/rcpn/pedidos")
    @roles_required(*QUEM_CONFERE)
    def rcpn_pedidos():
        """A fila dos sete módulos, com o que cada um tem esperando."""
        modulo = (request.args.get("modulo") or "").strip().upper() or None
        situacao = (request.args.get("situacao") or ESQ.PENDENTE).strip().upper()
        with db.connect() as con:
            try:
                fila = PED.pendentes(con, modulo=modulo,
                                     situacao=situacao or None)
            except API.CertidaoError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("rcpn_pedidos"))
            contagem = PED.quantos_por_modulo(con)
        return render_template(
            "rcpn_pedidos.html", fila=fila, contagem=contagem,
            modulo=modulo, situacao=situacao, cns=_cns(),
            ambiente=PED.ambiente(), base=API.BASE,
            modulos=API.MODULOS, nome_do_modulo=API.NOME_DO_MODULO,
            modulos_de_registro=API.MODULOS_DE_REGISTRO,
            situacoes=ESQ.SITUACOES,
            tem_credencial=API.tem_credencial(),
            arquivo_da_credencial=str(CRED.caminho(CRED.ONRCPN)))

    @app.route("/rcpn/pedidos/baixar", methods=["POST"])
    @roles_required(*QUEM_CONFERE)
    def rcpn_pedidos_baixar():
        """Traz os pedidos pendentes de um módulo. **Não responde a nenhum.**"""
        modulo = (request.form.get("modulo") or "").strip().upper()
        try:
            r = PED.baixar(db, modulo, cns=_cns(), agora=agora(),
                           usuario=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_pedidos"))
        audit("rcpn_pedidos_baixados",
              f"{r['modulo']} · {r['novos']} novos de {r['vieram']}")
        flash(f"Módulo {r['modulo']}: vieram {r['vieram']}, entraram "
              f"{r['novos']} e {r['repetidos']} já estavam na fila.", "ok")
        if not r["contagem_bate"]:
            # **DIVERGÊNCIA NÃO SE CORRIGE EM SILÊNCIO.**
            flash(f"A Central disse que havia "
                  f"{r['quantos_a_central_disse']} pedidos e mandou "
                  f"{r['vieram']}. Baixe de novo e confira.", "warning")
        return redirect(url_for("rcpn_pedidos", modulo=r["modulo"]))

    # ------------------------------------------------------------- a ficha

    @app.route("/rcpn/pedidos/<int:pedido_id>", methods=["GET", "POST"])
    @roles_required(*QUEM_CONFERE)
    def rcpn_pedido(pedido_id: int):
        """O pedido, o assento que casou e o que iria para a Central.

        **NÃO GRAVA E NÃO ENVIA.**
        """
        campos = _valores_da_certidao()
        with db.connect() as con:
            p = PED.pedido(con, pedido_id)
            if p is None:
                flash("Pedido não encontrado.", "danger")
                return redirect(url_for("rcpn_pedidos"))
            conferido, erro_da_conferencia = None, ""
            if p.get("assento_id"):
                try:
                    conferido = PED.conferir(
                        con, p["assento_id"], cns=_cns(),
                        selo=campos["selo"] or None,
                        cod_selo=campos["cod_selo"] or None,
                        cota_emolumentos=campos["cota_emolumentos"] or None,
                        cota_isento=campos["cota_isento"],
                        tipo_registro=campos["tipo_registro"],
                        tipo_certidao=campos["tipo_certidao"])
                except RECUSAS_DO_BALCAO as erro:
                    erro_da_conferencia = str(erro)
            sugestao = PED.sugerir_valor_adicional(
                p, request.values.get("valor_emolumentos") or 0)
        return render_template(
            "rcpn_pedido.html", p=p, c=conferido,
            erro_da_conferencia=erro_da_conferencia, campos=campos,
            sugestao=sugestao, base=API.BASE, ambiente=PED.ambiente(),
            uf=_uf(), uf_que_conta=API.UF_QUE_CONTA_AVERBACAO,
            tipos=API.TIPOS_DE_REGISTRO,
            tem_credencial=API.tem_credencial(),
            arquivo_da_credencial=str(CRED.caminho(CRED.ONRCPN)))

    @app.route("/rcpn/pedidos/<int:pedido_id>/amarrar", methods=["POST"])
    @roles_required(*QUEM_CONFERE)
    def rcpn_pedido_amarrar(pedido_id: int):
        """Amarra à mão o assento que a matrícula não achou."""
        try:
            assento_id = int(request.form.get("assento_id") or 0)
        except ValueError:
            assento_id = 0
        if not assento_id:
            flash("Informe o número do assento.", "danger")
            return redirect(url_for("rcpn_pedido", pedido_id=pedido_id))
        try:
            with db.transaction() as con:
                PED.amarrar_assento(
                    con, pedido_id, assento_id,
                    motivo=(request.form.get("motivo") or "").strip())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            audit("rcpn_pedido_amarrado",
                  f"pedido {pedido_id} · assento {assento_id}")
            flash("Assento amarrado ao pedido.", "ok")
        return redirect(url_for("rcpn_pedido", pedido_id=pedido_id))

    @app.route("/rcpn/pedidos/<int:pedido_id>/dispensar", methods=["POST"])
    @roles_required(*QUEM_RESPONDE)
    def rcpn_pedido_dispensar(pedido_id: int):
        """Tira da fila **sem responder à Central**, com motivo escrito."""
        try:
            with db.transaction() as con:
                PED.dispensar(con, pedido_id,
                              motivo=(request.form.get("motivo") or ""),
                              agora=agora(), usuario=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            audit("rcpn_pedido_dispensado", f"pedido {pedido_id}")
            flash("O pedido saiu da fila. **A Central continua com ele em "
                  "aberto** — se ela cobrar, é aqui que se explica.", "warning")
        return redirect(url_for("rcpn_pedido", pedido_id=pedido_id))

    @app.route("/rcpn/pedidos/<int:pedido_id>/registrado", methods=["POST"])
    @roles_required(*QUEM_RESPONDE)
    def rcpn_pedido_registrado(pedido_id: int):
        """Marca que o registro pedido por P13/EOB **já foi lavrado**.

        **Não lavra nada** — quem lavrou foi a tela do assento.
        """
        # `rc_pedidos.assento_id` é `integer`, e aqui ninguém confere antes de
        # gravar: o número que não cabe derrubava o UPDATE (LD13).
        assento_id = numero_digitado(request.form.get("assento_id"),
                                     maximo=MAIOR_INTEGER)
        if not assento_id:
            flash("Informe o assento que foi lavrado.", "danger")
            return redirect(url_for("rcpn_pedido", pedido_id=pedido_id))
        try:
            with db.transaction() as con:
                PED.marcar_registrado(con, pedido_id, assento_id=assento_id,
                                      agora=agora(), usuario=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            audit("rcpn_pedido_registrado",
                  f"pedido {pedido_id} · assento {assento_id}")
            flash("Pedido marcado como registrado.", "ok")
        return redirect(url_for("rcpn_pedido", pedido_id=pedido_id))

    @app.route("/rcpn/pedidos/<int:pedido_id>/rejeitar", methods=["POST"])
    @roles_required(*QUEM_RESPONDE)
    def rcpn_pedido_rejeitar(pedido_id: int):
        """Recusa o pedido **na Central**, com o motivo que o requerente lê."""
        try:
            feito = PED.rejeitar(db, pedido_id,
                                 motivo=(request.form.get("motivo") or ""),
                                 agora=agora(), usuario=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            audit("rcpn_pedido_rejeitado", f"pedido {pedido_id}")
            flash(f"O pedido foi rejeitado na Central. Motivo enviado: "
                  f"{feito['motivo']}", "ok")
        return redirect(url_for("rcpn_pedido", pedido_id=pedido_id))

    # ----------------------------------------------- a certidão eletrônica

    @app.route("/rcpn/pedidos/<int:pedido_id>/emitir", methods=["POST"])
    @roles_required(*QUEM_RESPONDE)
    def rcpn_pedido_emitir(pedido_id: int):
        """Cria a certidão eletrônica na Central. **Ainda não a entrega.**"""
        campos = _valores_da_certidao()
        with db.connect() as con:
            p = PED.pedido(con, pedido_id)
        if p is None or not p.get("assento_id"):
            flash("Este pedido ainda não está amarrado a um assento.", "danger")
            return redirect(url_for("rcpn_pedido", pedido_id=pedido_id))
        try:
            feito = PED.emitir(
                db, p["assento_id"], cns=_cns(), agora=agora(),
                pedido_id=pedido_id, usuario=usuario_nome(),
                selo=campos["selo"] or None,
                cod_selo=campos["cod_selo"] or None,
                cota_emolumentos=campos["cota_emolumentos"] or None,
                cota_isento=campos["cota_isento"],
                tipo_registro=campos["tipo_registro"],
                tipo_certidao=campos["tipo_certidao"])
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            audit("rcpn_certidao_eletronica_criada",
                  f"pedido {pedido_id} · certidão {feito['certidao_id']}")
            flash(f"A certidão eletrônica foi criada na Central. "
                  f"Identificador: {feito['certidao_id']}. Assine-a antes de "
                  f"entregar.", "ok")
        return redirect(url_for("rcpn_pedido", pedido_id=pedido_id))

    # ------------------------------- a certidão eletrônica SEM pedido da CRC
    #
    # **O DOMÍNIO ESTAVA PRONTO E UMA TELA SÓ O CHAMAVA** — pedido do oficial
    # em 10/09/2026: «precisamos colocar o botao de emissao do json (...) para
    # emitir certidao pela CRC».
    #
    #   Medido antes de construir: `rc_pedidos.emitir` recebe
    #   `pedido_id: int | None = None` desde que nasceu, e
    #   `rc_certidoes_eletronicas.pedido_id` aceita NULO — a certidão
    #   eletrônica de um registro DESTA CASA sempre foi possível. O que havia
    #   era **um único botão, na ficha de um pedido que veio da Central**
    #   (`templates/rcpn_pedido.html`), de modo que emitir pela CRC dependia
    #   de alguém do outro lado pedir primeiro. Quem chega ao balcão pedindo
    #   certidão eletrônica não passa por aquela fila.
    #
    #   É o defeito que mais se repetiu neste projeto, **pelo lado do rascunho
    #   de tela**: não «função sem chamador», mas peça que UMA tela chama e as
    #   outras não — e nenhum varredor o vê, porque a função tem chamador.
    #
    # **CONFERIR E CRIAR CONTINUAM DOIS BOTÕES**, como na fila: o que sobe
    # entrega documento e é cobrado.

    def _conferencia_da_eletronica(assento_id: int):
        """O que iria para a Central, e o que impede. SÓ LÊ."""
        campos = _valores_da_certidao()
        with db.connect() as con:
            # **O SELO DO REGISTRO VEM PREENCHIDO** — «acho que selado já»,
            # o oficial no mesmo pedido. O sistema **não compra** selo por
            # aqui (esta casa nunca selou certidão eletrônica, e escolher um
            # caminho por semelhança seria assinar por quem selou); o que ele
            # faz é trazer o selo que o ATO DE REGISTRO já tem, para não
            # obrigar a digitar um número que o banco conhece. Continua
            # editável, e vazio quando o registro não tem selo.
            if not campos["selo"]:
                campos["selo"] = RCE.selo_do_registro(con, assento_id) or ""
            conferido = PED.conferir(con, assento_id, cns=_cns(), **campos)
            ja_saiu = PED.eletronicas_do_assento(con, assento_id)
            assento = banco(con).um(
                "SELECT id, especie, numero, nome, matricula FROM rc_assentos "
                "WHERE id=%s", (int(assento_id),))
        return campos, conferido, ja_saiu, (dict(assento) if assento else None)

    @app.route("/rcpn/<int:assento_id>/certidao-eletronica",
               methods=["GET", "POST"])
    @roles_required(*QUEM_CONFERE)
    def rcpn_certidao_eletronica_nova(assento_id: int):
        """A conferência da certidão eletrônica de um registro desta casa.

        **NÃO MANDA NADA** — nem no POST, que é o botão «refazer a
        conferência» com os campos mudados. Quem manda é
        `rcpn_certidao_eletronica_criar`.
        """
        # **ERRO DE REGRA NÃO É HTTP 500**, e quem me pegou foi o teste de
        # tela: `PED.montar` recusa o assento que não existe **antes** de eu
        # ter a linha dele na mão, de modo que a conferência da minha
        # primeira versão estourava em vez de avisar. A recusa do domínio é a
        # que vale; o que faltava era apanhá-la.
        try:
            campos, conferido, ja_saiu, assento = _conferencia_da_eletronica(
                assento_id)
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_assentos"))
        if assento is None:
            flash("Este assento não existe.", "danger")
            return redirect(url_for("rcpn_assentos"))
        return render_template(
            "rcpn_certidao_eletronica_nova.html",
            assento=assento, c=conferido, campos=campos, ja_saiu=ja_saiu,
            tipos=API.TIPOS_DE_REGISTRO, cns=_cns(),
            ambiente=PED.ambiente(), base=API.BASE,
            tem_credencial=API.tem_credencial(),
            arquivo_da_credencial=str(CRED.caminho(CRED.ONRCPN)))

    @app.route("/rcpn/<int:assento_id>/certidao-eletronica/criar",
               methods=["POST"])
    @roles_required(*QUEM_RESPONDE)
    def rcpn_certidao_eletronica_criar(assento_id: int):
        """Cria na Central a certidão eletrônica deste registro.

        **SEM `pedido_id`**: não há pedido da Central por trás — é a casa
        emitindo. O resto é igual ao caminho da fila, e de propósito: uma
        segunda montagem do corpo divergiria da primeira no primeiro
        conserto, e o que a Central recebesse deixaria de ser o que a tela
        conferiu.
        """
        campos = _valores_da_certidao()
        if not campos["selo"]:
            with db.connect() as con:
                campos["selo"] = RCE.selo_do_registro(con, assento_id) or ""
        volta = url_for("rcpn_certidao_eletronica_nova", assento_id=assento_id)
        try:
            feito = PED.emitir(
                db, assento_id, cns=_cns(), agora=agora(),
                pedido_id=None, usuario=usuario_nome(),
                selo=campos["selo"] or None,
                cod_selo=campos["cod_selo"] or None,
                cota_emolumentos=campos["cota_emolumentos"] or None,
                cota_isento=campos["cota_isento"],
                tipo_registro=campos["tipo_registro"],
                tipo_certidao=campos["tipo_certidao"])
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(volta)
        audit("rcpn_certidao_eletronica_criada",
              f"assento {assento_id} · certidão {feito['certidao_id']}")
        flash(f"A certidão eletrônica foi criada na Central. Identificador: "
              f"{feito['certidao_id']}. Assine-a antes de entregar.", "ok")
        return redirect(volta)

    @app.route("/rcpn/pedidos/<int:pedido_id>/atender", methods=["POST"])
    @roles_required(*QUEM_RESPONDE)
    def rcpn_pedido_atender(pedido_id: int):
        """Entrega a certidão ao requerente. **É a chamada que fecha o
        pedido.**"""
        try:
            eletronica_id = int(request.form.get("eletronica_id") or 0)
        except ValueError:
            eletronica_id = 0
        if not eletronica_id:
            flash("Escolha qual certidão eletrônica entregar.", "danger")
            return redirect(url_for("rcpn_pedido", pedido_id=pedido_id))
        try:
            PED.atender(
                db, pedido_id, eletronica_id=eletronica_id,
                valor_emolumentos=(request.form.get("valor_emolumentos") or 0),
                valor_adicional=request.form.get("valor_adicional"),
                observacoes=(request.form.get("observacoes") or ""),
                quantidade_averbacao=request.form.get("quantidade_averbacao"),
                uf_da_serventia=_uf(), agora=agora(), usuario=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            audit("rcpn_pedido_atendido",
                  f"pedido {pedido_id} · certidão local {eletronica_id}")
            flash("O pedido foi cumprido na Central.", "ok")
        return redirect(url_for("rcpn_pedido", pedido_id=pedido_id))

    @app.route("/rcpn/certidao-eletronica/<int:eletronica_id>/assinar",
               methods=["POST"])
    @roles_required(*QUEM_RESPONDE)
    def rcpn_certidao_eletronica_assinar(eletronica_id: int):
        """Manda a Central assinar. **A assinatura acontece do lado de lá.**"""
        volta = request.form.get("volta_para") or ""
        try:
            feito = PED.assinar(db, eletronica_id, agora=agora(),
                                usuario=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            audit("rcpn_certidao_eletronica_assinada",
                  f"certidão local {eletronica_id}")
            flash(f"A Central assinou. Link: {feito['link'] or '—'}", "ok")
        return _voltar(volta, eletronica_id)

    @app.route("/rcpn/certidao-eletronica/<int:eletronica_id>/atualizar",
               methods=["POST"])
    @roles_required(*QUEM_RESPONDE)
    def rcpn_certidao_eletronica_atualizar(eletronica_id: int):
        """Corrige na Central o que ja subiu, **sem queimar o identificador**.

        Cancelar e criar de novo daria um `certidao_id` novo — e o pedido pode
        ja ter recebido o antigo como `id_verificador`.
        """
        volta = request.form.get("volta_para") or ""
        campos = _valores_da_certidao()
        try:
            PED.atualizar_eletronica(
                db, eletronica_id, cns=_cns(), agora=agora(),
                usuario=usuario_nome(),
                selo=campos["selo"] or None,
                cod_selo=campos["cod_selo"] or None,
                cota_emolumentos=campos["cota_emolumentos"] or None,
                cota_isento=campos["cota_isento"])
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            audit("rcpn_certidao_eletronica_atualizada",
                  f"certidao local {eletronica_id}")
            flash("A Central atualizou a certidao com os dados de agora. "
                  "O identificador continua o mesmo.", "ok")
        return _voltar(volta, eletronica_id)

    @app.route("/rcpn/certidao-eletronica/<int:eletronica_id>/cancelar",
               methods=["POST"])
    @roles_required(*QUEM_RESPONDE)
    def rcpn_certidao_eletronica_cancelar(eletronica_id: int):
        """Cancela a certidão **eletrônica**. Não cancela a de papel."""
        volta = request.form.get("volta_para") or ""
        try:
            PED.cancelar_eletronica(db, eletronica_id, agora=agora(),
                                    usuario=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            audit("rcpn_certidao_eletronica_cancelada",
                  f"certidão local {eletronica_id}")
            flash("A certidão eletrônica foi cancelada na Central. **A "
                  "certidão de papel não foi tocada** — aquele é outro ato, na "
                  "ficha do assento.", "ok")
        return _voltar(volta, eletronica_id)


    @app.route("/rcpn/<int:assento_id>/certidao-eletronica/json")
    @roles_required(*QUEM_CONFERE)
    def rcpn_certidao_eletronica_json(assento_id: int):
        """Baixa o JSON CRC/ON-RCPN deste assento. **Não chama a Central.**

        Opção local enquanto a API CRC não está em uso operacional: monta o
        mesmo corpo de emitir (montar → {certidao, registro}) e devolve
        como anexo .json, mesmo sem token / mesmo se a API falharia.
        """
        campos = _valores_da_certidao()
        try:
            with db.connect() as con:
                if not campos["selo"]:
                    campos["selo"] = RCE.selo_do_registro(con, assento_id) or ""
                corpo = PED.corpo_crc(con, assento_id, cns=_cns(), **campos)
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_certidao_eletronica_nova",
                                    assento_id=assento_id))
        bruto = json.dumps(corpo, ensure_ascii=False, indent=2).encode("utf-8")
        nome = f"certidao-crc-assento-{assento_id}.json"
        return Response(
            bruto, mimetype="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{nome}"'})

    @app.route("/rcpn/certidao-eletronica/<int:eletronica_id>/json")
    @roles_required(*QUEM_CONFERE)
    def rcpn_certidao_eletronica_json_gravado(eletronica_id: int):
        """Baixa o JSON da eletrônica: corpo_enviado se houver, senão remonta.

        Opção local enquanto a API CRC não está em uso operacional — **sem
        rede**.
        """
        try:
            with db.connect() as con:
                corpo = PED.corpo_crc_da_eletronica(
                    con, eletronica_id, cns=_cns())
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_pedidos"))
        bruto = json.dumps(corpo, ensure_ascii=False, indent=2).encode("utf-8")
        nome = f"certidao-crc-{eletronica_id}.json"
        return Response(
            bruto, mimetype="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{nome}"'})

    @app.route("/rcpn/certidao-eletronica/<int:eletronica_id>/pdf")
    @roles_required(*QUEM_CONFERE)
    def rcpn_certidao_eletronica_pdf(eletronica_id: int):
        """Busca o PDF **na Central** e o mostra. Não guarda nada.

        O arquivo é dela e se busca nela — ver o cabeçalho de
        `rc_pedidos_schema`: binário não entra num banco que viaja no backup.
        """
        with db.connect() as con:
            linha = PED.eletronica(con, eletronica_id)
        if not linha:
            flash("Certidão eletrônica não encontrada.", "danger")
            return redirect(url_for("rcpn_pedidos"))
        try:
            achado = PED.buscar_na_central(linha)
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_pedidos"))
        if not achado["pdf"]:
            flash("A Central não devolveu arquivo para esta certidão "
                  f"(situação: {achado['situacao'] or 'não informada'}).",
                  "warning")
            return redirect(url_for("rcpn_pedidos"))
        cabecas = dict(VIS.cabecalhos_para_mostrar())
        cabecas["Content-Disposition"] = (
            f'inline; filename="certidao-{eletronica_id}.pdf"')
        return Response(achado["pdf"], mimetype="application/pdf",
                        headers=cabecas)

    def _voltar(volta: str, eletronica_id: int):
        """Volta para a tela de onde se veio, quando ela se identificou.

        **AGORA HÁ DUAS PORTAS PARA A MESMA CERTIDÃO** — a ficha do pedido da
        Central e a conferência do registro desta casa (10/09/2026). Assinar
        e cair na fila mandaria o operador de volta para uma lista em que ele
        não estava; é o defeito da rota que ignora o próprio
        redirecionamento, que este projeto pagou duas vezes numa noite.
        """
        # O «²» e os 5.000 dígitos passavam pelo `isdigit()` e caíam no
        # `int()` — DEPOIS de a Central já ter respondido (LD13).
        pedido = numero_digitado(volta)
        if pedido is not None:
            return redirect(url_for("rcpn_pedido", pedido_id=pedido))
        assento = numero_digitado(volta[8:]) if volta.startswith("assento:") else None
        if assento is not None:
            return redirect(url_for("rcpn_certidao_eletronica_nova",
                                    assento_id=assento))
        return redirect(url_for("rcpn_pedidos"))
