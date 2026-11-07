"""Atendimentos e escola de operação nas rotas autenticadas da instalação."""
from __future__ import annotations

from flask import abort, flash, redirect, render_template, request, session, url_for
from werkzeug.routing import BuildError

import atendimento_fluxo as FL
import treinamento as TR
from bd_nativo import banco
from seguranca_web import numero_digitado

PRATICA = ("ADMIN", "MANAGER", "USER")
LEITURA = (*PRATICA, "AUDITOR")


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date):
    # Migração pelo servidor nativo durante a construção do app; GET só lê.
    with db.transaction() as con:
        FL.init_schema(con)
        TR.init_schema(con)

    def papel():
        return app.extensions["usuario_papel"]()

    def uid():
        return int(app.extensions["usuario_id"]())

    def aula_corrente(chave):
        with db.connect() as con:
            return TR.aula_corrente(con,chave,papel())

    def link(endpoint, **args):
        if endpoint not in app.view_functions:
            return None
        try:
            return url_for(endpoint, **args)
        except BuildError:
            return None

    @app.context_processor
    def contexto_operacional():
        if not session.get("user_id"):
            return {}
        aula = TR.aula_da_tela(request.endpoint or "", papel())
        pid = None
        args = request.view_args or {}
        if request.endpoint == "caixa_protocolo":
            pid = args.get("protocolo_id")
        elif request.endpoint in ("ri_protocolo_ver", "ri_nota_devolutiva"):
            with db.connect() as con:
                pid = banco(con).valor("SELECT id FROM cx_protocolos WHERE ri_protocolo_id=%s ORDER BY id LIMIT 1",
                                       (args.get("protocolo_id"),))
        return {"operacao_disponivel": True, "aula_da_operacao": aula, "atendimento_da_operacao": pid}

    def moeda(centavos):
        if centavos is None:
            return "A apurar"
        return f"R$ {centavos/100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    @app.route("/atendimentos")
    @roles_required(*LEITURA)
    def at_lista():
        vista = request.args.get("vista", "todos")
        with db.connect() as con:
            dados = FL.listar(con, busca=request.args.get("busca", ""),
                usuario_id=uid() if vista == "meus" else None,
                sem_responsavel=vista == "sem-responsavel",
                pagina=numero_digitado(request.args.get("pagina"),maximo=1000000) or 1,
                historico=request.args.get("historico")=="1", atribuicao=request.args.get("atribuicao", ""))
        return render_template("at_lista.html", **dados, vista=vista)

    @app.route("/meu-trabalho")
    @roles_required(*LEITURA)
    def at_meu_trabalho():
        return redirect(url_for("at_lista",vista="meus"))

    @app.route("/atendimentos/<int:protocolo_id>")
    @roles_required(*LEITURA)
    def at_ficha(protocolo_id):
        aba = request.args.get("aba", "resumo")
        if aba not in ("resumo","documentos","analise","atos","financeiro","historico"):
            abort(404)
        try:
            with db.connect() as con:
                dados = FL.ficha(con, protocolo_id)
                users = banco(con).ler("SELECT id,full_name FROM users WHERE active=1 AND role IN ('ADMIN','MANAGER','USER') ORDER BY full_name") if papel() in ("ADMIN","MANAGER") else []
                eventos = banco(con).ler("""SELECT ts,action,username_snapshot FROM audit_logs
                    WHERE (entity_type IN ('ATENDIMENTO','CX_PROTOCOLO','PROTOCOLO') AND entity_id=%s)
                       OR (entity_type='RI_PROTOCOLO' AND entity_id=%s)
                       OR (entity_type='RI_NOTA' AND entity_id IN
                           (SELECT id FROM ri_notas_devolutivas WHERE protocolo_id=%s))
                    ORDER BY id DESC LIMIT 80""",(protocolo_id,dados["ri"]["id"] if dados["ri"] else -1,
                                                dados["ri"]["id"] if dados["ri"] else -1))
        except FL.FluxoError:
            abort(404)
        p, ri, e = dados["p"], dados["ri"], dados["etapa"]
        if e in ("A_QUALIFICAR","A_REQUALIFICAR"):
            proxima = ("Registrar resultado da qualificação",url_for("at_ficha",protocolo_id=protocolo_id,aba="analise"),"qualificacao")
        elif e == "EM_EXIGENCIA":
            proxima = ("Conferir cumprimento de exigências",url_for("at_ficha",protocolo_id=protocolo_id,aba="analise"),"reingresso")
        elif e == "VENCIDA":
            proxima = ("Examinar situação da prenotação",link("ri_protocolo_ver",protocolo_id=ri["id"])+"#prazo","prenotacao")
        elif e == "APTO":
            proxima = ("Preparar o ato",link("ri_ficha",matricula_id=ri.get("matricula_id")) if ri.get("matricula_id") else link("ri_minutas"),"ri_ato")
        elif e == "REGISTRADO":
            proxima = ("Conferir arquivamento e entrega",url_for("at_ficha",protocolo_id=protocolo_id,aba="atos"),"entrega")
        elif e == "ENTREGUE":
            proxima = ("Consultar o histórico da entrega",url_for("at_ficha",protocolo_id=protocolo_id,aba="historico"),"entrega")
        elif e == "ORCAMENTO":
            proxima = ("Conferir orçamento / transformar em serviço",link("caixa_protocolo",protocolo_id=protocolo_id)+"#virar-servico","atendimento")
        elif not ri and p["atribuicao"] == "RI" and e not in ("ENTREGUE","CANCELADO"):
            proxima = ("Prenotar este título, quando aplicável",link("ri_protocolo",cx_protocolo_id=protocolo_id),"prenotacao")
        else:
            proxima = ("Abrir rotina do serviço",link("caixa_protocolo",protocolo_id=protocolo_id),"atendimento")
        guia = TR.aula("roteiro-"+proxima[2],papel())
        import protocolo_documentos as DOC
        rotulos={'ATENDIMENTO_ENTREGUE':'Entrega registrada','RI_NOTA_DEVOLUTIVA':'Nota devolutiva emitida',
                 'RI_REINGRESSO':'Reingresso registrado','ATENDIMENTO_ITEM_CONFERIDO':'Conferência de exigência',
                 'ATENDIMENTO_RESPONSAVEL':'Responsável designado','RI_QUALIFICACAO':'Qualificação registrada',
                 'RI_QUALIFICACAO_POSITIVA':'Qualificação positiva registrada','RI_PRENOTACAO':'Título prenotado',
                 'RI_PROTOCOLO_ENCERRADO':'Prenotação encerrada','PROTOCOLO_ABERTO':'Atendimento aberto',
                 'PROTOCOLO_ITEM_ACRESCENTADO':'Item de serviço acrescentado',
                 'PROTOCOLO_ITEM_QUITADO':'Pagamento de item confirmado','RI_NOTA_IMPRESSA':'Documento da nota emitido',
                 'PROTOCOLO_DOCUMENTO_ANEXADO':'Documento recebido',
                 'SELO_PROTOCOLO_EM_ATENDIMENTO':'Protocolo selecionado para o serviço'}
        return render_template("at_ficha.html", **dados, aba=aba, proxima=proxima, guia=guia,
            usuarios=users,eventos=eventos,moeda=moeda,pratica=papel() in PRATICA,
            tipos_documento=DOC.ROTULO_DO_TIPO,
            rotulo_evento=lambda acao:rotulos.get(acao,str(acao).replace('_',' ').capitalize()))

    @app.route("/atendimentos/<int:protocolo_id>/entrega",methods=["POST"])
    @roles_required(*PRATICA)
    def at_entregar(protocolo_id):
        try:
            with db.transaction() as con:
                feito=FL.entregar(con,protocolo_id,recebido_por=request.form.get('recebido_por'),
                    observacao=request.form.get('observacao'),
                    conferencias={k:request.form.get(k)=='1' for k in ('documentos_conferidos','assinaturas_selos','arquivamento_conferido')},
                    quem=app.extensions['usuario_nome'](),agora=db.now())
                import identidade_do_robo as IDR
                usuario=banco(con).um('SELECT username FROM users WHERE id=%s',(uid(),))
                IDR.registrar(con,ts=db.now(),user_id=uid(),username=usuario['username'],
                    action='ATENDIMENTO_ENTREGUE',entity_type='ATENDIMENTO',entity_id=protocolo_id,
                    details=feito,ip_address=request.remote_addr)
            flash("Entrega registrada. Os pagamentos, recibos e documentos foram preservados.","success")
        except FL.FluxoError as e:
            flash(str(e),'danger')
        return redirect(url_for('at_ficha',protocolo_id=protocolo_id,aba='atos'))

    @app.route("/atendimentos/<int:protocolo_id>/responsavel",methods=["POST"])
    @roles_required(*PRATICA)
    def at_responsavel(protocolo_id):
        destino = numero_digitado(request.form.get("usuario_id")) or uid()
        try:
            with db.transaction() as con:
                alteracao = FL.assumir(con,protocolo_id,usuario_id=destino,autor_id=uid(),
                                      agora=db.now(),gerencia=papel() in ("ADMIN","MANAGER"))
            audit("ATENDIMENTO_RESPONSAVEL","ATENDIMENTO",protocolo_id,alteracao)
            flash("Responsável registrado. O pedido aparece no Meu trabalho dessa pessoa.","success")
        except FL.FluxoError as e:
            flash(str(e),"danger")
        return redirect(url_for("at_ficha",protocolo_id=protocolo_id))

    @app.route("/atendimentos/<int:protocolo_id>/exigencia",methods=["POST"])
    @roles_required(*PRATICA)
    def at_exigencia(protocolo_id):
        try:
            with db.transaction() as con:
                feito = FL.conferir_item(con,protocolo_id,origem=request.form.get("origem", ""),
                    nota_id=numero_digitado(request.form.get("nota_id")) or 0,
                    ordem=numero_digitado(request.form.get("ordem")) or 0,
                    estado=request.form.get("estado", ""),anexo_id=numero_digitado(request.form.get("anexo_id")),
                    observacao=request.form.get("observacao", ""),usuario_id=uid(),agora=db.now(),
                    versao_esperada=request.form.get("versao_item", ""))
            audit("ATENDIMENTO_ITEM_CONFERIDO","ATENDIMENTO",protocolo_id,feito)
            flash("Item atualizado. A decisão e o reingresso formal continuam na rotina da nota.","success")
        except FL.FluxoError as e:
            flash(str(e),"danger")
        return redirect(url_for("at_ficha",protocolo_id=protocolo_id,aba="analise"))

    @app.route("/treinamento")
    @roles_required(*LEITURA)
    def tr_inicio():
        busca=request.args.get("busca", "")
        grupo=request.args.get("grupo", "")
        tipo=request.args.get("tipo", "" if busca or grupo else "roteiro")
        todas=TR.aulas(papel())
        filtradas=TR.aulas(papel(),busca,grupo,tipo)
        pagina=numero_digitado(request.args.get("pagina"),maximo=1000000) or 1
        paginas=max(1,(len(filtradas)+23)//24);pagina=min(pagina,paginas)
        with db.connect() as con:
            progresso=TR.progresso(con,uid())
        return render_template("tr_inicio.html",aulas=filtradas[(pagina-1)*24:pagina*24],
            total=len(filtradas),grupos=sorted({x["grupo"] for x in todas}),
            pagina=pagina,paginas=paginas,progresso=progresso,
            total_geral=len(todas),busca=busca,grupo=grupo,tipo=tipo)

    def render_aula(a, resultado=None):
        with db.connect() as con:
            progresso=TR.progresso(con,uid()).get(a["id"])
        return render_template("tr_aula.html",a=a,resultado=resultado,progresso=progresso,
            rotina=link(a["endpoint"],**a.get("args",{})) if a.get("endpoint") else None,
            pratica=papel() in PRATICA)

    @app.route("/treinamento/aula/<chave>")
    @roles_required(*LEITURA)
    def tr_aula(chave):
        a=aula_corrente(chave)
        if not a: abort(404)
        return render_aula(a)

    @app.route("/treinamento/aula/<chave>/pratica",methods=["POST"])
    @roles_required(*PRATICA)
    def tr_pratica(chave):
        try:
            with db.transaction() as con:
                a=TR.aula_corrente(con,chave,papel())
                if not a: abort(404)
                respostas=[numero_digitado(request.form.get(f"resposta_{i}"),maximo=10) for i in range(len(a["questoes"]))]
                resultado=TR.avaliar(con,a,respostas,usuario_id=uid(),agora=db.now(),versao=request.form.get("versao", ""))
            audit("TREINAMENTO_PRATICA","TREINAMENTO",None,{"aula":chave,"versao":a["versao"],
                  "acertos":resultado["acertos"],"total":resultado["total"],"aprovado":resultado["aprovado"]})
        except ValueError as e:
            flash(str(e),"danger");return redirect(url_for("tr_aula",chave=chave))
        return render_aula(a,resultado)

    @app.route("/treinamento/equipe")
    @roles_required("ADMIN","MANAGER")
    def tr_equipe():
        with db.connect() as con:
            linhas=banco(con).ler("""SELECT u.id,u.full_name,u.role,t.aula,t.versao,t.aprovado,t.feito_em
                FROM users u LEFT JOIN (SELECT *,row_number() OVER
                  (PARTITION BY usuario_id,aula ORDER BY id DESC) AS rn FROM tr_tentativas) t
                  ON t.usuario_id=u.id AND t.rn=1 WHERE u.active=1 ORDER BY u.full_name,t.aula""")
        pessoas={}
        with db.connect() as con:
            for r in linhas:
                p=pessoas.setdefault(r["id"],{"nome":r["full_name"],"concluidas":0,"rever":0,"ultima":""})
                if r["aula"]:
                    a=TR.aula_corrente(con,r["aula"],r["role"])
                    if a and r["aprovado"] and r["versao"]==a["versao"]: p["concluidas"]+=1
                    else: p["rever"]+=1
                    p["ultima"]=max(p["ultima"],r["feito_em"] or "")
        return render_template("tr_equipe.html",pessoas=list(pessoas.values()))

    @app.route("/treinamento/trilha/<trilha>")
    @roles_required(*LEITURA)
    def tr_trilha(trilha):
        trilhas={
            "primeiro-dia":("Primeiro dia no cartório",["atendimento","prenotacao","qualificacao","nota","reingresso","caixa","ri_ato","certidao","entrega"]),
            "notas":("Tabelionato de Notas",["atendimento","firma","autenticacao","procuracao","notas_ato","ata","certidao","caixa","entrega"]),
            "civil":("Registro Civil",["atendimento","nascimento","casamento","obito","rcpn","certidao","caixa","entrega"]),
            "imoveis":("Registro de Imóveis",["prenotacao","qualificacao","nota","reingresso","ri_ato","livro3","especial_ri","certidao"]),
            "protesto":("Protesto",["atendimento","protesto","nota","caixa","certidao"]),
            "rtd-rpj":("RTD e RCPJ",["atendimento","rtd_rpj","qualificacao","nota","reingresso","certidao","caixa","entrega"])}
        if trilha not in trilhas:abort(404)
        titulo,ids=trilhas[trilha]
        if 'entrega' not in ids:
            ids=[*ids,'entrega']
        with db.connect() as con:
            aulas=[TR.aula_corrente(con,"roteiro-"+i,papel()) for i in ids]
            prog=TR.progresso(con,uid())
        for a in aulas:
            p=prog.get(a["id"])
            a["concluida"]=bool(p and p["aprovado"] and p["versao"]==a["versao"])
        return render_template("tr_trilha.html",titulo=titulo,aulas=aulas,
            feitas=sum(a["concluida"] for a in aulas))

    @app.route("/treinamento/aula/<chave>/orientacao",methods=["GET","POST"])
    @roles_required("ADMIN")
    def tr_orientacao(chave):
        a=aula_corrente(chave)
        if not a:abort(404)
        dados={k:request.form.get(k,"") for k in ("conteudo","fontes","motivo")}
        if request.method=="POST" and request.form.get("acao")=="publicar":
            try:
                with db.transaction() as con:
                    oid=TR.publicar_orientacao(con,chave,**dados,usuario_id=uid(),
                        nome=app.extensions["usuario_nome"](),agora=db.now())
                audit("TREINAMENTO_ORIENTACAO_PUBLICADA","TREINAMENTO",oid,{"aula":chave,"motivo":dados["motivo"]})
                flash("Orientação publicada com nova versão. O histórico de aprendizagem foi preservado.","success")
                return redirect(url_for("tr_aula",chave=chave))
            except ValueError as e:flash(str(e),"danger")
        return render_template("tr_orientacao.html",a=a,dados=dados,previa=request.method=="POST")

    @app.route("/treinamento/normas")
    @roles_required(*LEITURA)
    def tr_normas():
        import normativa as N
        termo=request.args.get("busca", "").strip()[:180]
        resultados=[]
        if termo:
            try: resultados=N.buscar(termo,limite=8)
            except N.NormaError as e: flash(str(e),"danger")
        return render_template("tr_normas.html",busca=termo,resultados=resultados)
