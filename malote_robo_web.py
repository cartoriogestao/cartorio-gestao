"""A tela do código de dois fatores do robô do malote (29/10/2026).

O malote pede o código só quando quer (o oficial: «so me peca a autenticacao a
primeira vez»). Quando pede, a rodada MALOTE_CIENCIA_DIARIA termina em AVISO e
espera; aqui o oficial digita o código que recebeu, a tela o GRAVA NO COFRE
(`malote_tjma_codigo`) e pede uma rodada. Quem entra no malote é o despachante,
fora do servidor — a tela não fala com o malote e não lê o cofre de volta
(`automacao_cofre.ler` recusa dentro de requisição web).

O código não vai à auditoria nem ao log: a auditoria diz que um código foi
informado, e por quem. O robô apaga o código do cofre assim que o usa, e não
usa código com mais de 15 minutos.

O LOGIN E A SENHA TÊM FORMULÁRIO PRÓPRIO — 30/10/2026, relato do oficial: «sistema
nao aceita meu cpf como login do cadastro do malote». A tela geral do cofre pede
o NOME de cada campo à esquerda e o valor à direita, e o CPF posto na caixa do
nome é recusado (nome de campo começa com letra). Aqui há duas caixas com o nome
do que pedem, e quem monta a credencial é a rota.
"""
from __future__ import annotations

import re
import json
import secrets

from flask import flash, redirect, render_template, request, url_for, jsonify

import automacao as AU
import automacao_cofre as COFRE
import malote_robo as MR
import malote_agente as MA
import malote_documentos as MD
import malote_fluxo as FL
from bd_nativo import banco

PROCESSO = MR.CATALOGO[0]["codigo"]
_CODIGO_VALIDO = re.compile(r"^[A-Za-z0-9]{4,12}$")
_SO_NUMERO_E_MASCARA = re.compile(r"^[0-9.\-/ ]+$")


def login_limpo(texto) -> str:
    """O login como o malote o quer: o CPF com máscara vira só os números; outro
    login fica como foi digitado. Só calcula."""
    login = str(texto or "").strip()
    return re.sub(r"[^0-9]", "", login) if _SO_NUMERO_E_MASCARA.match(login) else login


def registrar_rotas(app, db, login_required, roles_required, audit):
    usuario_nome = app.extensions["usuario_nome"]

    def _pasta():
        from centrais_cred import pasta_de_dados
        return pasta_de_dados()

    @app.route("/automacao/malote/agente", methods=["GET", "POST"])
    @roles_required("ADMIN")
    def malote_agente_local():
        if request.method == "POST":
            try:
                valor = {r: {"principal": request.form.get(r), "substituto": request.form.get(r + "_sub")}
                         for r in FL.ROTAS}
                with db.transaction() as con:
                    distribuicao = FL.conferir_distribuicao(con, valor)
                    bd = banco(con)
                    bd.escrever("INSERT INTO settings (key,value) VALUES (%s,%s) "
                                "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
                                (FL.CONFIG, json.dumps(distribuicao)))
                    p = AU.por_codigo(con, PROCESSO)
                    if not p:
                        raise FL.FluxoMaloteError("O processo do Malote não está cadastrado.")
                    parametros = dict(p["parametros"], triar_recebidos=request.form.get("triar") == "1")
                    bd.escrever("UPDATE au_processos SET parametros=%s WHERE id=%s",
                                (json.dumps(parametros), p["id"]))
            except FL.FluxoMaloteError as erro:
                flash(str(erro), "danger")
            else:
                audit("MALOTE_FLUXO_CONFIGURADO", "au_processos", p["id"],
                      {"triar_recebidos": parametros["triar_recebidos"], "distribuicao": distribuicao})
                flash("Triagem e responsáveis guardados. Ligar e autorizar a ciência continuam na tela do processo.", "success")
            return redirect(url_for("malote_agente_local"))
        with db.connect() as con:
            estado = FL.estado(con)
            distribuicao = FL.distribuicao(con)
        if request.accept_mimetypes.best == "application/json":
            return jsonify(estado)
        return render_template("malote_agente_local.html", estado=estado, distribuicao=distribuicao,
                               rotas=FL.ROTAS, usuarios=db.list_users(active_only=True), chave_manual=secrets.token_hex(16))

    @app.route("/automacao/malote/agente/rodada", methods=["POST"])
    @roles_required("ADMIN")
    def malote_agente_pedir():
        try:
            with db.transaction() as con:
                resultado = FL.pedir(con, chave=request.form.get("chave") or "",
                                     modo=request.form.get("modo") or "",
                                     usuario_id=int(app.extensions["usuario_id"]()), usuario=usuario_nome())
        except FL.FluxoMaloteError as erro:
            if request.accept_mimetypes.best == "application/json":
                return jsonify(erro="Pedido recusado. Confira a configuração e as rodadas pendentes na tela do Malote."), 409
            flash(str(erro), "danger")
            return redirect(url_for("malote_agente_local"))
        audit("MALOTE_PEDIDO_LOCAL", "au_processos", None, resultado)
        if request.accept_mimetypes.best == "application/json":
            return jsonify(resultado), 202
        flash("Rodada solicitada. Acompanhe o resultado no processo do Malote.", "success")
        return redirect(url_for("malote_agente_local"))

    @app.route("/automacao/malote/documentos", methods=["GET", "POST"])
    @roles_required("ADMIN")
    def malote_documentos():
        grupo = (request.values.get("grupo") or "").strip()
        if request.method == "GET":
            return render_template("malote_documentos.html", grupo=grupo)
        enviado = request.files.get("documento")
        try:
            if not enviado:
                raise MD.DocumentoMaloteError("Selecione o PDF recebido do Malote.")
            conteudo = enviado.stream.read(MD.LIMITE + 1)
            if request.form.get("conferir") == "1":
                with db.connect() as con:
                    info = MD.examinar(con, conteudo, grupo)
                return jsonify(codigo=info["codigo"], grupo=grupo, sha256=info["sha256"],
                               alertas=len(info["alertas"]), conferir=True)
            with db.connect() as con:
                raiz = MA.archive_root_de(db.db_path.parent, con)
            uid = int(app.extensions["usuario_id"]())
            with db.transaction() as con:
                resultado = MD.receber(con, conteudo, grupo, raiz=raiz, usuario_id=uid, agora=db.now())
        except MD.DocumentoMaloteError as erro:
            if request.accept_mimetypes.best == "application/json":
                return jsonify(erro="PDF recusado. Confira a capa do Malote, os códigos da comunicação e a validade do arquivo."), 400
            flash(str(erro), "danger")
            return redirect(url_for("malote_documentos", grupo=grupo))
        audit("MALOTE_FRAUDE_DOCUMENTO", "attachments", None,
              {"codigo": resultado["codigo"], "sha256": resultado["sha256"], "anexos": resultado["anexos"]})
        if request.accept_mimetypes.best == "application/json":
            return jsonify(resultado)
        flash("PDF guardado e vinculado aos alertas da comunicação.", "success")
        return redirect(url_for("fraudes"))

    @app.route("/automacao/malote/responsavel", methods=["POST"])
    @roles_required("ADMIN")
    def malote_robo_responsavel():
        login = (request.form.get("responsavel_malote") or "").strip()
        try:
            with db.transaction() as con:
                MA.configurar_responsavel(con, login)
        except MA.MaloteError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("malote_robo_codigo"))
        audit("MALOTE_ROBO_RESPONSAVEL", "settings", None, {"em_nome_de": login})
        flash("Responsável pelo cadastro do malote guardado.", "success")
        return redirect(url_for("malote_robo_codigo"))

    @app.route("/automacao/malote/credencial", methods=["POST"])
    @roles_required("ADMIN")
    def malote_robo_credencial():
        usuario = login_limpo(request.form.get("login_malote"))
        senha = request.form.get("senha_malote") or ""
        if not usuario or not senha:
            flash("Preencha o usuário (o CPF, só os números) e a senha do malote.", "danger")
            return redirect(url_for("malote_robo_codigo"))
        try:
            COFRE.gravar(MR.CREDENCIAL, {"usuario": usuario, "senha": senha}, tipo=COFRE.SENHA,
                         por=usuario_nome(), caminho=COFRE.caminho_do_cofre(_pasta()))
        except COFRE.CofreError as erro:
            flash(f"O login do malote não foi guardado: {erro}", "danger")
            return redirect(url_for("malote_robo_codigo"))
        audit("AUTOMACAO_COFRE_GRAVADO", "automacao_cofre", None,
              {"nome": MR.CREDENCIAL, "tipo": COFRE.SENHA, "campos": ["senha", "usuario"], "validade": None})
        flash("Login do malote guardado no cofre.", "success")
        return redirect(url_for("malote_robo_codigo"))

    @app.route("/automacao/malote/codigo", methods=["GET", "POST"])
    @roles_required("ADMIN")
    def malote_robo_codigo():
        caminho = COFRE.caminho_do_cofre(_pasta())
        with db.connect() as con:
            processo = AU.por_codigo(con, PROCESSO)
            ultima = (AU.execucoes(con, processo["id"], limite=1) or [None])[0] if processo else None
        if request.method == "POST":
            codigo = (request.form.get("codigo") or "").strip().replace(" ", "")
            if not _CODIGO_VALIDO.match(codigo):
                flash("O código tem de ter de 4 a 12 letras ou números, como chegou do malote.", "danger")
                return redirect(url_for("malote_robo_codigo"))
            if processo is None:
                flash("O processo do robô do malote ainda não está no cadastro da automação.", "danger")
                return redirect(url_for("malote_robo_codigo"))
            try:
                COFRE.gravar(MR.CODIGO, {"codigo": codigo}, tipo=COFRE.TOKEN, por=usuario_nome(),
                             caminho=caminho)
            except COFRE.CofreError as erro:
                flash(f"O código não foi guardado: {erro}", "danger")
                return redirect(url_for("malote_robo_codigo"))
            with db.transaction() as con:
                AU.pedir_rodada(con, processo["id"], usuario=usuario_nome())
            audit("MALOTE_ROBO_CODIGO_INFORMADO", "au_processos", processo["id"],
                  {"codigo_do_processo": PROCESSO})
            flash("Código guardado no cofre. O robô do malote roda no próximo minuto e usa o código "
                  "(ele vale 15 minutos). Recarregue o processo para ver o resultado.", "success")
            return redirect(url_for("automacao_processo", processo_id=processo["id"]))
        esperando = bool(ultima and "código de dois fatores" in (ultima.get("erro") or "")
                         + (ultima.get("relato") or ""))
        return render_template("malote_robo_codigo.html", processo=processo, ultima=ultima,
                               esperando=esperando, cofre=COFRE.estado(caminho=caminho),
                               credencial=COFRE.tem(MR.CREDENCIAL, caminho=caminho),
                               nome_da_credencial=MR.CREDENCIAL,
                               responsavel=db.get_setting("malote_cadastra_em_nome_de", ""),
                               usuarios=db.list_users(active_only=True))
