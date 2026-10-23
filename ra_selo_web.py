"""A tela de selar o ato do Livro 3 — **o botão que o Livro 2 já tinha.**

A regra e as medições moram em `ra_selo.py`; aqui só se ligam os fios, na
ordem que a casa manda: a **rede fora da transação** e a **auditoria fora
dela** também.

MÓDULO PRÓPRIO, e não dentro de `atribuicoes_web.py`: aquele arquivo tem nove
mil linhas e está sendo escrito por outra passada — duas mãos no mesmo arquivo
se atropelam. O que precisou ser tocado lá foi **uma chamada** na rota que
averba, e mais nada.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from flask import abort, flash, redirect, request, url_for

import ato_selado as AS
from bd_nativo import banco
import ra_parte as PT
import ra_selo as RS


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """A ASSINATURA É A DA CASA — ver `ajuda_web.registrar_rotas`."""

    usuario_nome = app.extensions["usuario_nome"]

    def selar_o_ato_do_livro3(*, ato, registro, natureza, codigo_tj,
                              base_calculo, isento, motivo_isencao) -> dict:
        """Pede o selo do ato do Livro 3. **FALA COM A REDE.**

        Devolve `{"recado", "selado"}`. Ela não grava nada: quem grava é o
        `selar_o_ato_lavrado`, que abre a própria transação curta — é por isso
        que ele recebe `db`, e não `con`.
        """
        import selo_robo as SR
        if not SR.pode_selar_automatico():
            return {"recado": SR.recado_pendente_selo(),
                    "selado": False, "pendente_de_selo": True}
        caminho = RS.caminho_do_ato(base_calculo)
        versao = AS.versao_da_tabela_de_custas(
            caminho, db.get_setting("selo_tabela_custas_em", ""))

        # **A LISTA VAZIA IMPEDE O SELO, E EU HAVIA ESCRITO O CONTRÁRIO AQUI.**
        # Em 20/09/2026 este comentário dizia que «a lista vazia não impede o
        # selo, e o envelope do Livro 2 já manda `parteAto: []`». Ele manda —
        # e o aparelho recusa, com a frase «Os nomes das partes devem ser
        # informados», que o oficial recebeu no dia seguinte ao tentar selar a
        # AV-01 do registro 1.243. Dedução minha contra medição do balcão:
        # ganha o balcão, e a recusa passou a ser aqui, antes da viagem.
        with db.connect() as con:
            partes = PT.para_o_selo(con, registro["id"])
            disponiveis = {codigo for codigo, _ in RS.itens_disponiveis(con)}

        # 16.45 É O CÓDIGO QUE O TRIBUNAL ACEITA (medido 28/09/2026 no selo
        # REGGAR… da matrícula 3.247 / mesmo título CCB 030-26/5178-0): o
        # selador cobra a faixa pelo baseCalculo. Os 16.45.x são faixas da
        # tabela local de custas — mandar o subitem devolve «Não foi
        # encontrado um ato para o código informado».
        if str(codigo_tj or "").strip().startswith("16.45.") and str(codigo_tj).strip() != "16.45":
            return {"recado": " O ato ficou SEM SELO: para garantia de crédito "
                    "rural o Tribunal espera o código 16.45 (cabeçalho); a "
                    "faixa sai do valor declarado (base de cálculo). Troque "
                    "16.45.x por 16.45 na ficha.",
                    "selado": False}
        if disponiveis and str(codigo_tj or "").strip() not in disponiveis:
            return {"recado": " O ato ficou SEM SELO: o item escolhido não "
                    "tem preço ativo na tabela vigente; confira o subitem.",
                    "selado": False}

        falta = RS.falta_para_selar(
            natureza=natureza, codigo_tj=codigo_tj, versao_tabela=versao,
            partes=partes, isento=isento, motivo_isencao=motivo_isencao,
            protocolo=registro["prenotacao"])
        if falta:
            return {"recado": " O ato ficou SEM SELO: " + falta[0],
                    "selado": False}
        try:
            envelope = RS.envelope_do_ato(
                registro_numero=registro["numero"], tipo=ato["tipo"],
                numero=ato["numero"], escrevente=usuario_nome(),
                versao_tabela=versao, natureza=natureza, codigo_tj=codigo_tj,
                protocolo=registro["prenotacao"],
                base_calculo_centavos=base_calculo, partes=partes,
                isento=isento, motivo_isencao=motivo_isencao)
        except (AS.AtoError, RS.RaSeloError) as erro:
            # DADO QUE O ENVELOPE RECUSA, e não a rede: montar de novo com o
            # mesmo dado recusaria de novo.
            return {"recado": f" O ato ficou SEM SELO: {erro}", "selado": False}

        r = AS.selar_o_ato_lavrado(
            db, Path(app.config["DATA_DIR"]), tabela="ra_atos",
            ato_id=int(ato["id"]), tipo=str(ato["tipo"]), atribuicao="IMOVEL",
            agora=datetime.now().isoformat(timespec="seconds"),  # noqa: DTZ005
            cns=db.get_setting("ri_cns", ""), usuario=usuario_nome(),
            dados=envelope,
            # O CAMINHO VAI PRONTO: só quem tem o valor declarado na mão sabe
            # escolher entre `com-valor` e `sem-valor`.
            caminho=caminho,
            referencia=f"ra_atos:{int(ato['id'])}")
        if not r["selado"]:
            return {"recado": f" O ato ficou SEM SELO: {r['motivo']}",
                    "selado": False}
        return {"recado": f" Selo {r['numero']}.", "selado": True}

    app.extensions["selar_o_ato_do_livro3"] = selar_o_ato_do_livro3

    def arquivar_o_ato_do_livro3(*, ato_id: int, folhas: int) -> dict:
        """Selo 16.39 por folha; só depois de sucesso encerra a prenotação."""
        import selo_robo as SR
        if not SR.pode_selar_automatico():
            return {"ok": False, "recado": SR.recado_pendente_selo().strip(),
                    "pendente_de_selo": True}
        try:
            quantidade = int(folhas)
        except (TypeError, ValueError):
            quantidade = 0
        if quantidade < 1:
            return {"ok": False, "recado": "Informe as folhas do arquivamento (>= 1)."}
        with db.connect() as con:
            bd = banco(con)
            ato = bd.um("SELECT * FROM ra_atos WHERE id = %s", (ato_id,))
            reg = (bd.um("SELECT * FROM ra_registros WHERE id = %s",
                         (ato["registro_id"],)) if ato else None)
            partes = PT.para_o_selo(con, reg["id"]) if reg else []
        if not ato or not reg:
            return {"ok": False, "recado": "Ato do Livro 3 não encontrado."}
        if ato["selo_arquivamento"]:
            return {"ok": False, "recado": f"Arquivamento já selado: {ato['selo_arquivamento']}."}
        if not ato["selo"]:
            return {"ok": False, "recado": "Sele primeiro o ato principal; o arquivamento permanece pendente."}
        versao = AS.versao_da_tabela_de_custas(
            AS.CAMINHO_ARQUIVAMENTO_RI,
            db.get_setting("selo_tabela_custas_em", ""))
        if not versao:
            return {"ok": False, "recado": "Falta a data da tabela de custas em Configurações."}
        try:
            envelope = AS.envelope_do_arquivamento_do_ri(
                escrevente=usuario_nome(), versao_tabela=versao,
                quantidade=quantidade, partes=partes,
                isento=bool(ato["isento"]),
                motivo_isencao=ato["motivo_isencao"])
        except AS.AtoError as erro:
            return {"ok": False, "recado": str(erro)}
        with db.transaction() as con:
            banco(con).escrever(
                "UPDATE ra_atos SET folhas_arquivamento = %s WHERE id = %s",
                (quantidade, ato_id))
        r = AS.selar_o_ato_lavrado(
            db, Path(app.config["DATA_DIR"]), tabela="ra_atos", ato_id=ato_id,
            tipo="ARQUIV", atribuicao="IMOVEL",
            agora=datetime.now().isoformat(timespec="seconds"),
            cns=db.get_setting("ri_cns", ""), usuario=usuario_nome(),
            dados=envelope, caminho=AS.CAMINHO_ARQUIVAMENTO_RI,
            referencia=f"ra_atos:{ato_id}:{AS.CODIGO_ARQUIVAMENTO_RI}:1")
        if not r["selado"]:
            with db.transaction() as con:
                banco(con).escrever("UPDATE ra_atos SET selo = %s WHERE id = %s",
                                    (ato["selo"], ato_id))
            return {"ok": False, "recado": f"Arquivamento pendente: {r['motivo']}"}
        with db.transaction() as con:
            banco(con).escrever(
                """UPDATE ra_atos SET selo = %s, selo_arquivamento = %s,
                       folhas_arquivamento = %s WHERE id = %s""",
                (ato["selo"], r["numero"], quantidade, ato_id))
            encerramento = RS.encerrar_prenotacao_apos_arquivamento(
                con, int(reg["id"]))
        if encerramento and encerramento.get("encerrou"):
            audit("RI_PROTOCOLO_ENCERRADO", "RI_PROTOCOLO",
                  encerramento["protocolo_id"],
                  {"via": "livro3_arquivamento_16.39", "ato_id": ato_id,
                   "numero": encerramento["numero"]})
        recado = f"Arquivamento {r['numero']} ({quantidade} folha(s))."
        if encerramento and encerramento.get("encerrou"):
            recado += f" Prenotação {encerramento['numero']} encerrada."
        elif encerramento and encerramento.get("ambiguo"):
            recado += " Prenotação não encerrada: número ambíguo; confira manualmente."
        elif encerramento and encerramento.get("achou") is False:
            recado += " Prenotação não encontrada; confira o número na ficha."
        elif encerramento is None:
            recado += " Sem prenotação vinculada para encerrar."
        return {"ok": True, "recado": recado, "numero": r["numero"]}

    app.extensions["arquivar_o_ato_do_livro3"] = arquivar_o_ato_do_livro3

    @app.route("/livro3/ato/<int:ato_id>/selar-arquivamento", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def livro3_selar_arquivamento(ato_id: int):
        import selo_robo as SR
        if SR.exige_humano_para_selar():
            abort(403)
        with db.connect() as con:
            ato = banco(con).um("SELECT registro_id FROM ra_atos WHERE id = %s",
                                (ato_id,))
        if not ato:
            abort(404)
        voltar = redirect(url_for("livro3_registro", registro_id=ato["registro_id"]))
        resultado = arquivar_o_ato_do_livro3(
            ato_id=ato_id, folhas=request.form.get("folhas_arquivamento"))
        audit("RA_ARQUIVAMENTO", "ra_atos", ato_id,
              {"ok": resultado["ok"], "recado": resultado["recado"][:300]})
        flash(resultado["recado"], "success" if resultado["ok"] else "danger")
        return voltar

    @app.route("/livro3/ato/<int:ato_id>/selar", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def livro3_selar_ato(ato_id: int):
        """Sela um ato do Livro 3 **que já está lavrado**.

        O BURACO QUE ELA FECHA, relatado pelo oficial em 20/09/2026: *«fiz a
        averbação da 1243 e não emitiu selo»*. A rota que averba no Livro 3 só
        sabia **gravar o número que o escrevente digitasse** — ela nunca pediu
        selo ao aparelho —, e não havia por onde selar depois. É o mesmo
        buraco que o Livro 2 fechou em 15/09 com o botão «selar este ato», e a
        mesma saída.

        **ELA PERGUNTA TRÊS COISAS E NÃO ADIVINHA NENHUMA** — item da tabela de
        custas, natureza do título e valor declarado. O que for informado
        **fica gravado no ato antes de a rede ser chamada**: se o aparelho não
        responder, o que se digitou não se perde e a próxima tentativa já abre
        preenchida.

        **DOIS SELOS PARA O MESMO ATO É O DINHEIRO DA SERVENTIA SAINDO DUAS
        VEZES:** ato que já tem selo é recusado, dizendo qual é.
        """
        import selo_robo as SR
        if SR.exige_humano_para_selar():
            abort(403)
        with db.connect() as con:
            bd = banco(con)
            ato = bd.um("SELECT * FROM ra_atos WHERE id = %s", (ato_id,))
            if not ato:
                abort(404)
            registro = bd.um("SELECT * FROM ra_registros WHERE id = %s",
                             (ato["registro_id"],))
        if not registro:
            abort(404)
        voltar = redirect(url_for("livro3_registro",
                                  registro_id=ato["registro_id"]))
        rotulo = f"{ato['tipo']}-{ato['numero']}"

        if str(ato["selo"] or "").strip():
            flash(f"O ato {rotulo} já tem selo: {ato['selo']}. Dois selos para "
                  f"o mesmo ato é o dinheiro da serventia saindo duas vezes.",
                  "warning")
            return voltar

        natureza = (request.form.get("natureza_titulo") or "").strip()
        codigo_tj = (request.form.get("codigo_tj") or "").strip()
        base_calculo = RS.centavos_do_valor(request.form.get("base_calculo"))
        isento = request.form.get("isento") == "1"
        motivo_isencao = (request.form.get("motivo_isencao") or "").strip()
        selo_a_mao = (request.form.get("selo") or "").strip()

        # O QUE FOI INFORMADO FICA NO ATO, **ANTES DE QUALQUER RECUSA** — e
        # esta ordem foi corrigida em 21/09/2026. Ela estava ao contrário: a
        # tela recusava e voltava, e **o que o escrevente tinha acabado de
        # digitar ia junto**. Quem topa com a recusa é exatamente quem
        # preencheu alguma coisa; perder o que ele escreveu é cobrar duas
        # vezes pelo mesmo trabalho.
        with db.transaction() as con:
            banco(con).escrever(
                """UPDATE ra_atos
                      SET natureza_titulo=COALESCE(%s, natureza_titulo),
                          codigo_tj=COALESCE(%s, codigo_tj),
                          base_calculo_centavos=COALESCE(%s, base_calculo_centavos),
                          isento=%s, motivo_isencao=%s
                    WHERE id = %s""",
                (natureza or None, codigo_tj or None, base_calculo,
                 1 if isento else 0, motivo_isencao or None, ato_id))

        # A RECUSA VEM AGORA, COM O CLIENTE NA FRENTE — e o que ele digitou
        # já está guardado. O envelope também recusaria, mas lá a resposta
        # vem depois de uma viagem à rede.
        if not selo_a_mao:
            with db.connect() as con:
                partes = PT.para_o_selo(con, registro["id"])
            falta = RS.falta_para_selar(
                natureza=natureza, codigo_tj=codigo_tj, partes=partes,
                versao_tabela=AS.versao_da_tabela_de_custas(
                    RS.caminho_do_ato(base_calculo),
                    db.get_setting("selo_tabela_custas_em", "")),
                isento=isento, motivo_isencao=motivo_isencao,
                protocolo=registro["prenotacao"])
            if falta:
                flash(falta[0], "danger")
                return voltar

        if selo_a_mao:
            # O SELO DIGITADO À MÃO PASSA PELO RAZÃO, e não só pela coluna do
            # ato: `registrar_selo_obtido_a_mao` lê o código, confere o CNS
            # contra o da serventia e recusa selo repetido dizendo em que ato
            # ele já está — as três coisas que a coluna sozinha não faz.
            try:
                with db.transaction() as con:
                    AS.registrar_selo_obtido_a_mao(
                        con, selo_a_mao, tabela="ra_atos", ato_id=ato_id,
                        atribuicao="IMOVEL",
                        agora=datetime.now().isoformat(timespec="seconds"),  # noqa: DTZ005
                        cns=db.get_setting("ri_cns", ""),
                        usuario=usuario_nome())
            except AS.AtoError as erro:
                flash(str(erro), "danger")
                return voltar
            audit("RA_ATO_SELADO", "ra_atos", ato_id,
                  {"selo": selo_a_mao, "a_mao": True})
            flash(f"Selo do ato {rotulo} gravado: {selo_a_mao}.", "success")
            return voltar

        r = selar_o_ato_do_livro3(
            ato=ato, registro=registro, natureza=natureza,
            codigo_tj=codigo_tj, base_calculo=base_calculo, isento=isento,
            motivo_isencao=motivo_isencao)
        audit("RA_ATO_SELADO", "ra_atos", ato_id,
              {"selado": r["selado"], "recado": r["recado"][:200]})
        flash(f"Ato {rotulo}.{r['recado']}",
              "success" if r["selado"] else "danger")
        return voltar
