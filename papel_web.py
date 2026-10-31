"""
A TELA DO PAPEL DE SEGURANÇA — Registro Civil → Folhas de segurança.

POR QUE AS ROTAS SE CHAMAM `rcpn_papel_*`
    O nome da rota é o que põe a tela no grupo certo do menu: o módulo sai do
    PREFIXO, e não de uma lista. Chamando-as `papel_*`, elas cairiam no
    Administrativo — longe do balcão que gasta a folha.

    O arquivo é próprio porque o estoque é assunto próprio; o lugar dele na
    tela é o Registro Civil, porque é lá que a folha é gasta.

O QUE ESTA TELA NÃO FAZ
    Ela não gasta folha. Quem gasta é o ato — a certidão, o registro —, e a
    baixa acontece junto do selo, no mesmo momento. Uma tela que deixasse
    marcar folha como usada à mão seria a porta para a numeração andar sem ato
    nenhum do outro lado.

    O que ela faz é o que só uma pessoa pode fazer: dizer que a caixa chegou, e
    dizer que uma folha estragou.
"""
from __future__ import annotations

import sqlite3

from flask import flash, redirect, render_template, request, url_for

import papel_seguranca as PP
from seguranca_web import PRATICA  # M2 (LX11): o AUDITOR vê e não grava


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """Pendura a tela do papel no app já construído."""

    def agora() -> str:
        return db.now()

    usuario_nome = app.extensions["usuario_nome"]

    def _campo(nome: str, padrao: str = "") -> str:
        return (request.form.get(nome) or padrao).strip()

    @app.context_processor
    def _papel_no_aviso() -> dict:
        """O estoque acabando aparece em QUALQUER tela do civil. Só LÊ.

        Papel de segurança se compra de fornecedor e demora a chegar; acabar no
        meio do expediente é o balcão sem poder entregar certidão. O aviso é
        raro, e aviso raro que mora num canto é aviso que ninguém vê.

        SÓ NAS TELAS DO CIVIL, e não em todas: quem está no Protesto não gasta
        folha, e alarme que soa onde não interessa é alarme que se aprende a
        ignorar.
        """
        vazio = {"papel_acabando": None}
        try:
            onde = request.endpoint or ""
        except RuntimeError:
            return vazio
        if not onde.startswith("rcpn"):
            return vazio
        try:
            with db.connect() as con:
                quadro = PP.estoque(con)
        except sqlite3.Error:
            return vazio
        return {"papel_acabando": quadro if quadro["acabando"] else None}

    @app.route("/rcpn/papel")
    @login_required
    def rcpn_papel():
        """O estoque das folhas de segurança, e o caminho de uma folha."""
        # O CAMINHO DE UMA FOLHA (revisão de telas, 30/10/2026). O número vem como
        # está impresso, com ou sem a série; o NUL no endereço o banco recusaria.
        procurada = (request.args.get("folha") or "").replace("\x00", "").strip()
        with db.connect() as con:
            quadro = PP.estoque(con)
            caixas = PP.remessas(con)
            # FICHA_FOLHA_SEGURANCA_20261009: as usadas com o assento (nome e
            # link para a ficha), da mais recente, com busca e paginas - antes
            # eram so as 60 primeiras pela numeracao e diziam «rc_atos nº 428».
            pagina_usadas = PP.usadas_com_assento(
                con, busca=request.args.get("q", ""),
                pagina=request.args.get("pagina", 1, type=int) or 1)
            usadas = pagina_usadas["linhas"]
            inutilizadas = PP.listar(con, situacao="INUTILIZADA", limite=60)
            # `ler` acha a folha com ou sem a série, e os movimentos se perguntam
            # pelo código como ele está gravado.
            folha = PP.ler(con, procurada) if procurada else None
            caminho = PP.movimentos_da_folha(con, folha["codigo"]) if folha else []
        return render_template("rcpn_papel.html", quadro=quadro, caixas=caixas,
                               usadas=usadas, inutilizadas=inutilizadas,
                               pagina_usadas=pagina_usadas, procurada=procurada,
                               folha=folha, caminho=caminho)

    @app.route("/rcpn/papel/receber", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_papel_receber():
        """A caixa chegou do fornecedor. ESCREVE.

        DE QUEM RESPONDE PELA SERVENTIA, e não do balcão: dar entrada em papel
        de segurança é o mesmo tipo de ato que dar entrada em livro — o que
        entra aqui é o que a inspeção vai contar depois.
        """
        try:
            with db.transaction() as con:
                r = PP.receber_remessa(
                    con, fornecedor=_campo("fornecedor"),
                    serie=_campo("serie") or None,
                    tipo=_campo("tipo") or None,
                    codigo_de=_campo("codigo_de"),
                    codigo_ate=_campo("codigo_ate"),
                    nota_fiscal=_campo("nota_fiscal") or None,
                    observacao=_campo("observacao") or None,
                    agora=agora(), usuario=usuario_nome())
        except PP.PapelError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_papel"))
        audit("PAPEL_REMESSA", "pp_remessas", r["remessa_id"], r)
        flash(f"Entraram {r['quantas']} folhas, da {r['de']} à {r['ate']}.",
              "success")
        return redirect(url_for("rcpn_papel"))

    @app.route("/rcpn/papel/estornar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def rcpn_papel_estornar():
        """Desfaz uma remessa recebida por engano. ESCREVE.

        De quem responde pela serventia, e não do balcão: desfazer a entrada
        do papel de segurança INUTILIZA folhas em branco em lote.

        O PERFIL USER VOLTOU A SER RECUSADO AQUI EM 14/10/2026. A 3.6.160
        (21/09/2026) abriu esta rota ao USER na mesma leva de ~50 rotas, sem
        ordem registrada (`DOCUMENTACAO/SANITIZACAO_PARA_O_GITHUB.md`), e a
        tela continuou escondendo o botão de quem não é ADMIN/MANAGER — a porta
        escondida e destrancada. `tests/test_papel_web.py` guarda a recusa.
        (`receber`, acima, ficou aberta ao USER na mesma leva; decidir se fica
        é do oficial.)
        """
        try:
            with db.transaction() as con:
                r = PP.estornar_remessa(
                    con, _campo("remessa_id"), motivo=_campo("motivo"),
                    agora=agora(), usuario=usuario_nome())
        except PP.PapelError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_papel"))
        audit("PAPEL_REMESSA_ESTORNADA", "pp_remessas", r["remessa_id"],
              {"inutilizadas": r["inutilizadas"], "ja_usadas": r["ja_usadas"],
               "motivo": _campo("motivo")})
        recado = (f"{r['inutilizadas']} folha(s) inutilizada(s) desta remessa.")
        if r["ja_usadas"]:
            recado += (f" {r['ja_usadas']} já estavam gastas em ato — essas "
                      f"continuam como estavam.")
        flash(recado, "success")
        return redirect(url_for("rcpn_papel"))

    @app.route("/rcpn/papel/inutilizar", methods=["POST"])
    @login_required
    @roles_required(*PRATICA)
    def rcpn_papel_inutilizar():
        """A folha estragou. ESCREVE.

        DO BALCÃO, e não só do gerente: quem vê o papel sair borrado da
        impressora é quem está imprimindo. Exigir o gerente faria a folha ficar
        «em branco» no sistema e no lixo na vida real — e é assim que a
        numeração deixa de fechar.
        """
        try:
            with db.transaction() as con:
                r = PP.inutilizar(con, _campo("codigo"),
                                  motivo=_campo("motivo"), agora=agora(),
                                  usuario=usuario_nome())
        except PP.PapelError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_papel"))
        audit("PAPEL_INUTILIZADA", "pp_folhas", None,
              {"codigo": r["codigo"], "motivo": _campo("motivo")})
        flash(f"A folha {r['codigo']} saiu do estoque, com o motivo escrito.",
              "success")
        return redirect(url_for("rcpn_papel"))
