"""As telas da automação — a central única das rotinas da casa (Administrativo → Automação).

A TELA NÃO RODA NADA
    «Rodar agora» só marca o pedido; quem roda é o despachante, no tique do
    minuto seguinte, fora do servidor. Uma verificação que fala com Central
    dentro de uma requisição do waitress seguraria o balcão.

QUEM VÊ E QUEM MEXE
    O ADMIN vê e mexe; o MANAGER vê (a lista, o processo e o relatório). Ligar,
    editar, «pode agir sozinho», a configuração e o cofre são do ADMIN — e o
    «pode agir sozinho» vai à auditoria, porque é o oficial liberando a IA a
    escrever sem esperar o clique dele.

O COFRE NÃO SAI DAQUI
    A tela grava e remove o segredo (pelo guardião, com o cofre aberto); ela
    NUNCA o lê de volta — `automacao_cofre.ler` recusa dentro de requisição
    web. A senha do SMTP NÃO vai para este cofre: vai para `avisos.cred`
    (`cofre_cred`), que abre sem a senha-mestra — senão o e-mail que avisa «o
    cofre está trancado» não sairia. O campo da tela fica vazio sempre, e campo
    vazio não apaga nada.

DESBLOQUEAR PELA TELA SÓ NA PRÓPRIA MÁQUINA
    `/automacao/cofre/desbloquear` é do ADMIN e só atende quem chega de
    127.0.0.1: a senha-mestra não atravessa a rede da serventia. Ela é
    repassada ao guardião e não é gravada (nem na auditoria, nem no log).
"""
from __future__ import annotations

import base64
import json
import sqlite3
from datetime import datetime

from flask import abort, flash, redirect, render_template, request, session, url_for

import automacao as AU
import automacao_avisos as AV
import automacao_cofre as COFRE
import cofre_cred as CRED
import automacao_processos as PROC
import automacao_schema as SCH
from bd_nativo import banco

VEEM = ("ADMIN", "MANAGER")


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    current_user = app.extensions["current_user"]
    usuario_nome = app.extensions["usuario_nome"]

    def pasta() -> str:
        return str(db.db_path.parent)

    def cofre():
        """O arquivo do cofre desta instalação (a pasta de dados do servidor)."""
        return COFRE.caminho_do_cofre(pasta())

    def _local() -> bool:
        return (request.remote_addr or "") in ("127.0.0.1", "::1")

    with db.transaction() as con:
        SCH.init_automacao_schema(con)
        AU.semear(con)

    @app.context_processor
    def _automacao_no_painel() -> dict:
        vazio = {"automacao_no_painel": None}
        try:
            if request.endpoint != "dashboard" or not session.get("user_id"):
                return vazio
            u = current_user()
            if not u or u["role"] not in VEEM:
                return vazio
            with db.connect() as con:
                processos = AU.listar(con)
                painel = {"problemas": AU.contar_problemas(con),
                          "despachante": AU.batida_do_despachante(con),
                          "ativos": sum(1 for p in processos if p["ativo"]),
                          "precisam_do_cofre": sum(1 for p in processos if p["ativo"] and p.get("usa_credencial"))}
            painel["cofre"] = COFRE.estado(caminho=cofre()) if painel["precisam_do_cofre"] else None
            return {"automacao_no_painel": painel}
        except (sqlite3.Error, RuntimeError, KeyError, TypeError):
            return vazio

    def _usuarios():
        return [u for u in db.list_users(active_only=True)]

    # ------------------------------------------------------------ a lista

    @app.route("/automacao")
    @roles_required(*VEEM)
    def automacao_lista():
        with db.connect() as con:
            linhas = AU.painel(con)
            problemas = AU.problemas_atuais(con)
            batida = AU.batida_do_despachante(con)
        return render_template("automacao_lista.html", linhas=linhas, problemas=problemas,
                               batida=batida, selo=SCH.selo, cofre=COFRE.estado(caminho=cofre()))

    @app.route("/automacao/<int:processo_id>/ligar", methods=["POST"])
    @roles_required("ADMIN")
    def automacao_ligar(processo_id: int):
        ligar = request.form.get("ativo") == "1"
        try:
            with db.transaction() as con:
                p = AU.definir_ativo(con, processo_id, ligar, usuario=usuario_nome())
        except AU.AutomacaoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("automacao_lista"))
        audit("AUTOMACAO_LIGADO" if ligar else "AUTOMACAO_DESLIGADO", "au_processos", processo_id,
              {"codigo": p["codigo"]})
        flash(f"«{p['nome']}» {'ligado: roda no próximo horário da agenda' if ligar else 'desligado'}.",
              "success")
        if request.form.get("voltar") == "processo":
            return redirect(url_for("automacao_processo", processo_id=processo_id))
        return redirect(url_for("automacao_lista"))

    # ------------------------------------------------------------ o processo

    @app.route("/automacao/<int:processo_id>")
    @roles_required(*VEEM)
    def automacao_processo(processo_id: int):
        with db.connect() as con:
            p = AU.obter(con, processo_id)
            if not p:
                abort(404)
            historico = AU.execucoes(con, processo_id)
            batida = AU.batida_do_despachante(con)
        return render_template("automacao_processo.html", p=p, historico=historico, batida=batida,
                               agenda_texto=AU.descrever_agenda(p["agenda"]),
                               catalogo=sorted(AU.funcoes_permitidas()), tipos=SCH.TIPOS,
                               nome_do_tipo=SCH.NOME_DO_TIPO, canais=SCH.CANAIS,
                               nome_do_canal=SCH.NOME_DO_CANAL, dias=AU.DIAS,
                               usuarios=_usuarios(), credenciais=COFRE.listar(caminho=cofre()),
                               parametros_json=json.dumps(p["parametros"], ensure_ascii=False, indent=1),
                               selo=SCH.selo)

    @app.route("/automacao/<int:processo_id>/salvar", methods=["POST"])
    @roles_required("ADMIN")
    def automacao_salvar(processo_id: int):
        f = request.form
        agenda = {"dias": f.getlist("dias")}
        if f.get("forma") == "intervalo":
            agenda["intervalo_min"] = f.get("intervalo_min") or ""
        else:
            agenda["horarios"] = f.get("horarios") or ""
        if (f.get("janela_inicio") or "").strip() or (f.get("janela_fim") or "").strip():
            agenda["janela"] = [f.get("janela_inicio") or "", f.get("janela_fim") or ""]
        try:
            parametros = json.loads(f.get("parametros") or "{}")
        except ValueError:
            flash("Os parâmetros não são um JSON válido (ex.: {\"dias\": 7}).", "danger")
            return redirect(url_for("automacao_processo", processo_id=processo_id))
        campos = {"nome": f.get("nome"), "descricao": f.get("descricao"), "setor": f.get("setor"),
                  "tipo": f.get("tipo"), "alvo": f.get("alvo"), "parametros": parametros,
                  "agenda": agenda, "usa_credencial": f.get("usa_credencial"),
                  "timeout_s": f.get("timeout_s"), "max_tentativas": f.get("max_tentativas"),
                  "responsavel_user_id": f.get("responsavel_user_id"),
                  "canais": {c: f.get(f"canal_{c}") == "1" for c in SCH.CANAIS},
                  "lembrar_a_cada_h": f.get("lembrar_a_cada_h"), "robo_oficial": f.get("robo_oficial")}
        try:
            with db.transaction() as con:
                p = AU.salvar(con, processo_id, campos, usuario=usuario_nome())
        except AU.AutomacaoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("automacao_processo", processo_id=processo_id))
        # O rastro leva os PARÂMETROS inteiros (revisão de segurança de 26/10/2026,
        # PR #11, M2): era só o `alvo`, e os `argumentos` do script ficavam de fora.
        audit("AUTOMACAO_ALTERADO", "au_processos", processo_id,
              {"codigo": p["codigo"], "agenda": p["agenda"], "tipo": p["tipo"], "alvo": p["alvo"][:200],
               "parametros": json.dumps(p.get("parametros") or {}, ensure_ascii=False, sort_keys=True)[:4000]})
        flash("Processo gravado.", "success")
        return redirect(url_for("automacao_processo", processo_id=processo_id))

    @app.route("/automacao/<int:processo_id>/pode-agir", methods=["POST"])
    @roles_required("ADMIN")
    def automacao_pode_agir(processo_id: int):
        valor = request.form.get("pode_agir") == "1"
        u = current_user()
        try:
            with db.transaction() as con:
                p = AU.definir_pode_agir(con, processo_id, valor, papel=u["role"], usuario=usuario_nome())
        except AU.AutomacaoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("automacao_processo", processo_id=processo_id))
        # FORA da transação: `audit` abre a dela (regra da casa).
        audit("AUTOMACAO_PODE_AGIR", "au_processos", processo_id,
              {"codigo": p["codigo"], "pode_agir": valor})
        flash("Liberado: o agente deste processo passa a AGIR SOZINHO, e tudo o que ele fizer vai "
              "para o relatório da rodada." if valor else
              "Desligado: o agente deste processo volta a só ler e propor.", "success")
        return redirect(url_for("automacao_processo", processo_id=processo_id))

    @app.route("/automacao/<int:processo_id>/rodar", methods=["POST"])
    @roles_required("ADMIN")
    def automacao_rodar(processo_id: int):
        try:
            with db.transaction() as con:
                p = AU.pedir_rodada(con, processo_id, usuario=usuario_nome())
        except AU.AutomacaoError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("automacao_lista"))
        audit("AUTOMACAO_RODAR_AGORA", "au_processos", processo_id, {"codigo": p["codigo"]})
        flash(f"«{p['nome']}» vai rodar no próximo minuto, pelo despachante. Recarregue esta "
              "página daqui a pouco para ver o resultado.", "success")
        return redirect(url_for("automacao_processo", processo_id=processo_id))

    # ------------------------------------------------------------ o relatório

    @app.route("/automacao/execucoes/<int:execucao_id>")
    @roles_required(*VEEM)
    def automacao_execucao(execucao_id: int):
        with db.connect() as con:
            e = AU.execucao(con, execucao_id)
            if not e:
                abort(404)
            p = AU.obter(con, e["processo_id"])
            avisos = AU.avisos_da_execucao(con, execucao_id)
        return render_template("automacao_execucao.html", e=e, p=p, avisos=avisos,
                               nome_do_canal=SCH.NOME_DO_CANAL,
                               achados_json=json.dumps(e["achados"], ensure_ascii=False, indent=1, default=str),
                               acoes_json=json.dumps(e["acoes"], ensure_ascii=False, indent=1, default=str))

    # ------------------------------------------------------------ a configuração

    @app.route("/automacao/configuracao")
    @roles_required("ADMIN")
    def automacao_configuracao():
        with db.connect() as con:
            cfg = {c: SCH.ler_config(con, c) for c in SCH.CHAVES_CONFIG}
            batida = AU.batida_do_despachante(con)
            ultimos = banco(con).ler("SELECT * FROM au_avisos ORDER BY id DESC LIMIT 20")
        return render_template("automacao_configuracao.html", cfg=cfg, batida=batida,
                               seguranca=SCH.SEGURANCAS_SMTP, ultimos=ultimos,
                               senha_guardada=AV.tem_senha_do_smtp(pasta()),
                               nome_do_canal=SCH.NOME_DO_CANAL)

    @app.route("/automacao/configuracao", methods=["POST"])
    @roles_required("ADMIN")
    def automacao_configuracao_salvar():
        f = request.form
        campos = (SCH.CHAVE_SMTP_HOST, SCH.CHAVE_SMTP_PORTA, SCH.CHAVE_SMTP_USUARIO,
                  SCH.CHAVE_SMTP_REMETENTE, SCH.CHAVE_SMTP_SEGURANCA, SCH.CHAVE_EMAIL_DESTINO,
                  SCH.CHAVE_WHATSAPP_DESTINO, SCH.CHAVE_LEMBRAR, SCH.CHAVE_BACKUP_ESTADO,
                  SCH.CHAVE_CNIB_LOG)
        if (f.get(SCH.CHAVE_SMTP_SEGURANCA) or "STARTTLS") not in SCH.SEGURANCAS_SMTP:
            flash("Escolha a segurança do SMTP: STARTTLS, SSL ou nenhuma.", "danger")
            return redirect(url_for("automacao_configuracao"))
        with db.transaction() as con:
            for c in campos:
                if c in f:
                    SCH.gravar_config(con, c, (f.get(c) or "").strip())
        senha = f.get("smtp_senha") or ""
        if senha:
            try:
                AV.gravar_senha_do_smtp(pasta(), senha)
            except (CRED.CofreError, OSError) as erro:
                flash(f"A senha do SMTP não foi gravada: {erro}", "danger")
                return redirect(url_for("automacao_configuracao"))
        audit("AUTOMACAO_CONFIGURADO", "au_config", None,
              {"campos": [c for c in campos if c in f], "senha_smtp_trocada": bool(senha)})
        flash("Configuração gravada." + (" A senha do SMTP foi guardada." if senha else ""), "success")
        return redirect(url_for("automacao_configuracao"))

    @app.route("/automacao/configuracao/testar-email", methods=["POST"])
    @roles_required("ADMIN")
    def automacao_testar_email():
        with db.transaction() as con:
            SCH.gravar_config(con, SCH.CHAVE_TESTE_EMAIL, datetime.now().isoformat(timespec="seconds"))
            SCH.gravar_config(con, SCH.CHAVE_TESTE_EMAIL_POR, usuario_nome())
        flash("O e-mail de teste sai pelo despachante no próximo minuto. O resultado aparece na "
              "lista «últimos avisos», abaixo.", "success")
        return redirect(url_for("automacao_configuracao"))

    # ------------------------------------------------------------ o cofre

    @app.route("/automacao/cofre")
    @roles_required("ADMIN")
    def automacao_cofre():
        return render_template("automacao_cofre.html", itens=COFRE.listar(caminho=cofre()),
                               estado=COFRE.estado(caminho=cofre()), local=_local(),
                               tipos=COFRE.TIPOS, nome_do_tipo=COFRE.NOME_DO_TIPO)

    #: Os arquivos que a tela aceita, e o campo em que cada um vira texto.
    ARQUIVOS = (("arquivo_crt", "crt_pem", False), ("arquivo_key", "key_pem", False),
                ("arquivo_pfx", "pfx_base64", True))

    @app.route("/automacao/cofre", methods=["POST"])
    @roles_required("ADMIN")
    def automacao_cofre_gravar():
        f = request.form
        campos: dict[str, str] = {}
        for n in range(1, 6):
            chave = (f.get(f"campo_nome_{n}") or "").strip().lower()
            if chave:
                campos[chave] = f.get(f"campo_valor_{n}") or ""
        for entrada, campo, binario in ARQUIVOS:
            arquivo = request.files.get(entrada)
            if arquivo and arquivo.filename:
                bruto = arquivo.read(COFRE.TETO_DO_CAMPO + 1)
                campos[campo] = (base64.b64encode(bruto).decode("ascii") if binario
                                 else bruto.decode("utf-8", "replace"))
        try:
            meta = COFRE.gravar(f.get("nome"), campos, tipo=f.get("tipo"), validade=f.get("validade"),
                                por=usuario_nome(), caminho=cofre())
        except COFRE.CofreError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("automacao_cofre"))
        audit("AUTOMACAO_COFRE_GRAVADO", "automacao_cofre", None,
              {"nome": meta["nome"], "tipo": meta["tipo"], "campos": meta["campos_presentes"],
               "validade": meta["validade"]})
        flash(f"Credencial «{meta['nome']}» guardada no cofre ({len(meta['campos_presentes'])} campo(s)).",
              "success")
        return redirect(url_for("automacao_cofre"))

    @app.route("/automacao/cofre/remover", methods=["POST"])
    @roles_required("ADMIN")
    def automacao_cofre_remover():
        nome = request.form.get("nome")
        try:
            removido = COFRE.remover(nome, por=usuario_nome(), caminho=cofre())
        except COFRE.CofreError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("automacao_cofre"))
        if removido:
            audit("AUTOMACAO_COFRE_REMOVIDO", "automacao_cofre", None, {"nome": nome})
            flash(f"Credencial «{nome}» removida do cofre.", "success")
        else:
            flash("Essa credencial não estava no cofre.", "danger")
        return redirect(url_for("automacao_cofre"))

    @app.route("/automacao/cofre/desbloquear", methods=["GET", "POST"])
    @roles_required("ADMIN")
    def automacao_cofre_desbloquear():
        """Repassa a senha-mestra ao guardião. Só ADMIN, só de 127.0.0.1, e não grava a senha."""
        if not _local():
            abort(403)
        estado = COFRE.estado(caminho=cofre())
        if request.method == "POST":
            confirmacao = request.form.get("confirmacao") if not estado["existe"] else None
            try:
                COFRE.desbloquear(request.form.get("senha") or "", confirmacao=confirmacao, caminho=cofre())
            except COFRE.CofreError as erro:
                audit("AUTOMACAO_COFRE_SENHA_RECUSADA", "automacao_cofre", None, {})
                flash(str(erro), "danger")
                return redirect(url_for("automacao_cofre_desbloquear"))
            audit("AUTOMACAO_COFRE_DESBLOQUEADO", "automacao_cofre", None, {})
            flash("Cofre aberto. A chave ficou só na memória do guardião.", "success")
            return redirect(url_for("automacao_cofre"))
        return render_template("automacao_cofre_desbloquear.html", estado=estado)

    @app.route("/automacao/cofre/trancar", methods=["POST"])
    @roles_required("ADMIN")
    def automacao_cofre_trancar():
        try:
            COFRE.trancar(caminho=cofre())
        except COFRE.CofreError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("automacao_cofre"))
        audit("AUTOMACAO_COFRE_TRANCADO", "automacao_cofre", None, {})
        flash("Cofre trancado: a chave saiu da memória do guardião.", "success")
        return redirect(url_for("automacao_cofre"))
