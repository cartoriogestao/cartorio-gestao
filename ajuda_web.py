"""
AS TELAS DA AJUDA DO SISTEMA — a janela de toda tela, e os problemas.

QUEM PODE ENTRAR NÃO ESTÁ ESCRITO AQUI, e isso é o ponto
    O oficial pediu, em 26/08/2026, "apenas para o administrador, **com opção
    de expandir**". Um `@roles_required("ADMIN")` cumpriria a primeira metade e
    impediria a segunda: expandir viraria mexer no código.

    Então a rota pergunta ao domínio (`ajuda.pode_usar`), e o domínio lê a
    resposta do banco. O dia de abrir para o balcão é uma escolha na tela, feita
    pelo oficial, sem programador no meio.

    **Configurar quem pode continua sendo só do ADMIN** — quem muda a regra não
    pode ser quem a regra alcança.

A JANELA VAI EM `base.html`, E NÃO TELA A TELA
    A ajuda tinha uma tela só, no menu Administrativo, e quem estava com dúvida
    no meio de um ato precisava sair do que estava fazendo para chegar até ela —
    perdendo o que tinha digitado. Ajuda que cobra o abandono da tarefa é ajuda
    que ninguém usa na hora em que precisa.

    A janela mora em `templates/_ajuda.html`, incluída uma vez no `base.html`.
    É a mesma decisão da lupa das assinaturas, e pelo mesmo motivo escrito lá:
    **ligada tela a tela, a primeira que alguém criasse amanhã nasceria sem
    ajuda — e sem aviso nenhum de que nasceu.**

    A tela de onde a pergunta saiu não se digita: sai do `request.endpoint`, e
    o nome dela sai do mapa medido. Campo que o operador tem de preencher para
    a resposta ficar boa é campo que fica vazio.

SEM JAVASCRIPT ELA CONTINUA FUNCIONANDO
    O que se vê é um link para a tela inteira, já com a tela de origem no
    endereço. O script só o transforma em gaveta. É a regra do menu — «o
    sistema roda em rede local e menu que precisa de script é menu que some» —
    aplicada à ajuda.

AVISAR PROBLEMA NÃO PASSA PELA LISTA DE PERFIS
    Consultar a API gasta e manda dado para fora; por isso tem perfil e teto.
    Avisar um problema não faz nem uma coisa nem outra — é escrita local. Quem
    topa com o defeito é o balcão, e o balcão não pode ficar sem poder avisar.

A TELA MOSTRA O QUE VAI SAIR, ANTES DE SAIR
    Quem manda dado para fora tem direito de ver o que está mandando. O quadro
    de pré-visualização usa as mesmas funções da consulta — `montar_envio`,
    `montar_instrucao` e `o_que_sai` —, e não uma cópia parecida, que
    divergiria no primeiro conserto.

NADA AQUI LAVRA NADA
    Não há rota que escreva em livro, número, selo ou custa. A ajuda responde;
    quem lavra é o escrevente, na tela do ato, como sempre.

O ANEXO DE ARQUIVO À PERGUNTA SAIU EM 08/09/2026
    Pedido do oficial: "não está servindo pra nada". O módulo `ajuda_arquivos`
    (leitura local, sanitização e extração de texto de PDF) foi removido junto
    com o campo `arquivo` das duas telas (`ajuda.html` e a gaveta `_ajuda.html`)
    e das duas rotas que o liam. As colunas `anexo_*` de `aj_consultas` FICAM —
    são histórico de consultas já feitas, e `AJ.consultar` continua aceitando
    `anexo` por assinatura (default `None`) para quem um dia precisar chamá-la
    de outro lugar; só não há mais tela que produza um.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from flask import flash, jsonify, redirect, render_template, request, send_file, url_for

# O SELETOR É O TRANSPORTE DA AJUDA DESDE 14/09/2026. Havia um cliente só da
# Anthropic aqui, e ele foi aposentado quando o transporte virou um só na casa.
import agente_provedores as PROV
import ajuda as AJ
import ajuda_base as BASE
import ajuda_mapa as MAPA
import ajuda_projeto as PROJ
import ajuda_problemas as AP
from serventia import dados as dados_da_serventia


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """Pendura as telas da ajuda no app já construído.

    A ASSINATURA É A DA CASA, e não uma minha. Os seis módulos de tela deste
    sistema recebem os mesmos cinco argumentos e pegam o resto de
    `app.extensions` — que existe para isso. Uma sétima forma de ligar a mesma
    coisa é um módulo que ninguém liga sem abrir o arquivo.
    """

    # O RELÓGIO É O MESMO DO RESTO DA CASA — hora local, sem fuso.
    #
    # O `ruff` pede `datetime.now(tz=...)`, e aqui a regra dele está errada
    # para este sistema: todo carimbo deste banco — `pt_atos.criado_em`,
    # `sd_selos.usado_em`, `cx_lancamentos` — é hora local ingênua, e sempre
    # foi. Gravar `aj_consultas.perguntada_em` com fuso poria um formato
    # diferente numa tabela só, e a comparação com o resto passaria a mentir.
    #
    # `selador_web.py` faz igual, pelo mesmo motivo. Consistência aqui vale
    # mais que a regra, e por isso o silêncio é explícito e não por omissão.
    def agora() -> str:
        return datetime.now().isoformat(timespec="seconds")   # noqa: DTZ005

    def hoje() -> str:
        return datetime.now().date().isoformat()              # noqa: DTZ005

    def pasta_de_dados() -> Path:
        return Path(app.config["DATA_DIR"])

    usuario_nome = app.extensions["usuario_nome"]
    papel_do_usuario = app.extensions["usuario_papel"]

    def login_do_usuario() -> str:
        """O LOGIN de quem está logado — relato #87. O nome muda (o mesmo
        Mario já foi «Mario Santos» e «Mario Exemplo dos Santos»); o login não,
        e é por ele que «os meus problemas» se reconhecem."""
        user = app.extensions["current_user"]()
        return str(user["username"]) if user else ""

    def gere_a_lista() -> bool:
        return str(papel_do_usuario() or "") in AP.PAPEIS_QUE_GEREM
    versao = app.config.get("VERSION") or ""

    def _campo(nome: str, padrao: str = "") -> str:
        return (request.form.get(nome) or padrao).strip()

    def _de_volta() -> str:
        """A tela de onde o formulário saiu, sem sair da casa.

        VEM DO CAMPO `caminho`, QUE É NOSSO, e não do `Referer` do navegador:
        aquele é cabeçalho que qualquer página de fora escreve, e redirecionar
        para o que ele disser é abrir uma porta para levar o operador
        autenticado a um endereço estranho. Um caminho que não comece com uma
        barra só cai no painel.
        """
        caminho = _campo("caminho")
        if caminho.startswith("/") and not caminho.startswith("//"):
            return caminho
        return url_for("dashboard")

    def _volta_para_a_lista(problema_id: int = 0):
        """Volta para a lista de problemas NA MESMA VISTA em que ela estava.

        A vista viaja no formulário, e não fica guardada na sessão: quem abre
        duas abas — uma nos abertos e outra nos resolvidos — tem de ser
        devolvido para a aba de onde clicou, e a sessão é uma só por pessoa.

        O ENDEREÇO DA LINHA VAI JUNTO quando se sabe de qual problema se
        trata: quem grava uma nota e é largado no alto de oitenta linhas perde
        o lugar onde estava — e a âncora é o que a tela já usava antes da
        vista existir.
        """
        # «Só os meus» viaja junto, pela mesma razão da vista (relato #87).
        so_meus = _campo("meus") == "1"
        vista_volta = AP.vista_escolhida(_campo("vista"))
        ambiente_volta = AP.ambiente_filtro_escolhido(_campo("ambiente"))
        url = url_for(
            "ajuda_problemas",
            **AP.params_url_lista_problemas(
                vista=vista_volta, so_meus=so_meus, gere=gere_a_lista(),
                ambiente=ambiente_volta, exibir_filtro_ambiente=True,
            ))
        return redirect(url + (f"#problema-{int(problema_id)}"
                               if problema_id else ""))

    def _mapa(con: sqlite3.Connection) -> dict:
        """O mapa desta instalação, medido uma vez por processo.

        Nunca derruba tela: um mapa que não se mede é uma resposta mais pobre,
        e não uma tela quebrada.
        """
        try:
            return MAPA.do_processo(app, con, versao=versao)
        except Exception:                                      # noqa: BLE001
            return {}

    def conhecimento_da_tela(onde, *, com_projeto: bool = False,
                             documento: str = "") -> str:
        """O que a ajuda vai saber: a tela de onde a pergunta saiu, e — quando
        se pede — o estado do PROJETO.

        O ESTADO DO PROJETO NÃO VAI EM TODA PERGUNTA, e isso é o relato #26
        atendido sem virar conta alta: são cerca de 15 mil caracteres a mais,
        e a API cobra por uso. Vai quando alguém pede, e vai sempre na tela dos
        problemas — que é a tela onde o oficial pediu isto.

        E O TEXTO DE UM DOCUMENTO SÓ VAI SE FOR PEDIDO PELO NOME. São 80
        documentos e mais de um milhão de caracteres; o que vai sempre é o
        **índice**, para quem responde saber o que existe e poder pedir. É a
        regra da fatia, que o mapa já segue com as telas.

        **E A BASE PRÉ-CARREGADA VAI SEMPRE — são três linhas.** Não é o
        conteúdo dela: é o aviso de que ela existe, com o tamanho do que está
        indexado e o nome da ferramenta que a consulta. Sem essas três linhas o
        modelo não sabe que a base está de pé e volta a procurar de um em um —
        que é exatamente o que o oficial pediu para acabar. Medido: **~330
        caracteres**, contra as três rodadas que elas evitam.
        """
        try:
            with db.connect() as con:
                con.row_factory = sqlite3.Row
                texto = MAPA.resumo(_mapa(con), onde)
                texto = (texto + "\n\n" + BASE.para_o_contexto(con))
                if com_projeto or documento:
                    texto = (texto + "\n\n"
                             + PROJ.para_a_consulta(
                                 con, versao=versao,
                                 documento_pedido=documento))
                return texto
        except sqlite3.Error:
            return ""

    # -------------------------------------------------- a janela de toda tela

    @app.context_processor
    def _ajuda_em_toda_tela() -> dict:
        """O que a janela precisa saber, em qualquer tela. Só LÊ.

        Fica aqui, e não dentro do template, porque template desta casa não
        abre banco. E é `try/except`: um banco antigo, sem `aj_config`, não
        pode derrubar TODAS as telas do sistema por causa de um item de menu.

        SÃO DUAS CONSULTAS SOBRE ÍNDICE, e nenhuma abre transação de escrita.
        A segunda é o que faz a janela avisar «isto já deu errado aqui antes» —
        e quem topa hoje com o defeito que outro topou ontem merece saber que
        não é ele que está fazendo errado.
        """
        vazio = {"ajuda_liberada": False, "ajuda_problemas_aqui": [],
                 "ajuda_tela": ""}
        try:
            onde = request.endpoint or ""
        except RuntimeError:
            return vazio
        if not onde or onde == "static":
            return vazio
        # SEM NINGUÉM NA TELA, NÃO SE PERGUNTA NADA AO BANCO. A tela de login e
        # a de instalação não têm janela — e duas consultas por visita a uma
        # tela que não vai usá-las é trabalho que ninguém pediu.
        if not papel_do_usuario():
            return vazio
        try:
            with db.connect() as con:
                con.row_factory = sqlite3.Row
                return {
                    "ajuda_liberada": AJ.pode_usar(con, papel_do_usuario()),
                    "ajuda_problemas_aqui": AP.da_tela(con, onde),
                    "ajuda_tela": onde,
                }
        except sqlite3.Error:
            return vazio

    # ------------------------------------------------------ a consulta

    @app.route("/ajuda", methods=["GET", "POST"])
    @login_required
    def ajuda_consultar():
        """Perguntar à ajuda, e ver o que saiu.

        GET NÃO ABRE TRANSAÇÃO DE ESCRITA — nem para contar o dia. Tela de
        leitura que grava fica presa no `busy_timeout` enquanto outro balcão
        lavra.
        """
        # DE ONDE VEIO A DÚVIDA, quando a pessoa chegou aqui pela janela de
        # outra tela. Sem isto, quem clica na ajuda no meio de um ato chega
        # numa tela que não sabe de onde ele veio — e a resposta fica genérica
        # justamente para quem estava no meio do trabalho.
        onde_de_origem = (request.args.get("onde") or "").strip()

        with db.connect() as con:
            con.row_factory = sqlite3.Row
            liberado = AJ.pode_usar(con, papel_do_usuario())
            acesso = AJ.situacao_do_acesso(con)
            quadro = AJ.contagem(con, hoje())
            recentes = AJ.listar(con, limite=15) if liberado else []
            # QUEM RESPONDE, lido na conexão que já estava aberta: a tela diz
            # qual é o provedor e o modelo em vigor, e é por ELE que a chave é
            # conferida. Sem isto, a tela diria «há chave» com a chave de outro
            # provedor na mão e ofereceria uma caixa que só sabe falhar.
            escolha = AJ.escolha_para_tela(con)

        tem_chave = PROV.tem_chave(pasta_de_dados(), escolha["provedor"])

        resposta = None
        pergunta = previa = ""
        assunto = "USO"
        onde = onde_de_origem
        if request.method == "POST":
            pergunta = _campo("pergunta")
            assunto = _campo("assunto", "USO") or "USO"
            contexto = _campo("contexto")
            onde = _campo("onde") or None
            # VAZIO QUER DIZER «O CONFIGURADO», e é o que vem marcado na tela:
            # quem não escolhe modelo não pode ser obrigado a escolher — a
            # configuração já decidiu por ele. Quem escolhe vale só para esta
            # pergunta.
            modelo = _campo("modelo") or None
            conhecimento = conhecimento_da_tela(onde)
            try:
                # A PRÉVIA USA AS MESMAS FUNÇÕES DA CONSULTA. Uma segunda
                # montagem "parecida" divergiria no primeiro conserto, e a
                # tela passaria a mostrar uma coisa e mandar outra.
                pacote = AJ.preparar_saida(
                    pergunta=pergunta, assunto=assunto, onde=onde,
                    contexto=contexto, conhecimento=conhecimento,
                    serventia=AJ.descricao_da_serventia(db.get_settings))
                previa = pacote.auditavel
                if _campo("acao") == "prever":
                    flash("Isto é o que sairia da serventia. Nada foi enviado.",
                          "info")
                else:
                    r = AJ.consultar(
                        db, pergunta=pergunta, assunto=assunto, onde=onde,
                        referencia=_campo("referencia") or None,
                        contexto=contexto, modelo=modelo,
                        pasta_de_dados=pasta_de_dados(), agora=agora(),
                        papel=papel_do_usuario(), usuario=usuario_nome(),
                        conhecimento=conhecimento,
                        # A RAIZ E O `app` VÃO JUNTO porque as ferramentas de
                        # leitura precisam deles: ler o código da casa parte da
                        # raiz do programa, e o mapa das telas sai do `app`.
                        # Sem eles, a ajuda leria e não saberia ONDE.
                        raiz=Path(app.root_path), app=app, versao=versao)
                    resposta = r
                    # `audit` abre transação própria: FORA de qualquer `with`.
                    audit("AJUDA_CONSULTA", "aj_consultas", r["consulta_id"],
                          {"assunto": assunto, "sanitizacao":
                           r.get("sanitizacao_versao"),
                           "sha256": r.get("sanitizacao_sha256"),
                           "modelo": r.get("modelo")})
            except (AJ.AjudaError, PROV.AgenteError) as erro:
                flash(str(erro), "danger")
            except Exception:
                flash(
                    "A ajuda nao conseguiu falar com o provedor de IA agora. "
                    "Confira a chave em Ajuda → Configurar, a rede e o credito "
                    "da conta. Nada do pedido foi perdido.",
                    "danger",
                )
                try:
                    import logging
                    logging.getLogger("ajuda").exception(
                        "falha ao chamar provedor (detalhe so no log)")
                except Exception:
                    pass
            with db.connect() as con:
                con.row_factory = sqlite3.Row
                quadro = AJ.contagem(con, hoje())
                recentes = AJ.listar(con, limite=15) if liberado else []

        return render_template(
            "ajuda.html", liberado=liberado, acesso=acesso, quadro=quadro,
            recentes=recentes, tem_chave=tem_chave, resposta=resposta,
            previa=previa, pergunta=pergunta, assunto=assunto, onde=onde or "",
            assuntos=AJ.ASSUNTOS, escolha=escolha,
            # AS DUAS ESCOLHAS SÃO DO PROVEDOR EM USO, e não uma lista fixa: o
            # rótulo «mais forte» quer dizer coisa diferente em cada provedor,
            # e é o seletor que sabe qual é qual.
            modelos=AJ.modelos_do_provedor(escolha["provedor"]))

    @app.route("/ajuda/janela", methods=["POST"])
    @login_required
    def ajuda_janela():
        """A pergunta feita de dentro de outra tela, sem sair dela.

        Devolve JSON porque a tela de trás não pode ser recarregada: a pessoa
        está no meio de um ato, com campos preenchidos que se perderiam.

        A REGRA É A MESMA DA TELA INTEIRA — `AJ.consultar` confere o perfil e o
        teto no domínio. Esta rota não tem regra própria; se tivesse, seriam
        duas regras para a mesma coisa, e um dia divergiriam.
        """
        onde = _campo("onde") or None
        try:
            contexto = _campo("contexto") or None
            r = AJ.consultar(
                db, pergunta=_campo("pergunta"),
                assunto=_campo("assunto", "USO") or "USO", onde=onde,
                referencia=_campo("referencia") or None,
                contexto=contexto,
                modelo=_campo("modelo") or None,
                pasta_de_dados=pasta_de_dados(), agora=agora(),
                papel=papel_do_usuario(), usuario=usuario_nome(),
                conhecimento=conhecimento_da_tela(onde),
                raiz=Path(app.root_path), app=app, versao=versao)
        except (AJ.AjudaError, PROV.AgenteError) as erro:
            return jsonify({"ok": False, "erro": str(erro)}), 200
        except Exception:
            return jsonify({
                "ok": False,
                "erro": ("A ajuda nao conseguiu falar com o provedor de IA agora. "
                         "Confira a chave em Ajuda → Configurar."),
            }), 200
        audit("AJUDA_CONSULTA", "aj_consultas", r["consulta_id"],
              {"onde": onde, "pela_janela": True, "modelo": r.get("modelo")})
        return jsonify({"ok": True, "resposta": r["resposta"],
                        "consulta_id": r["consulta_id"],
                        "endereco": url_for("ajuda_consulta",
                                            consulta_id=r["consulta_id"])})

    @app.route("/ajuda/<int:consulta_id>")
    @login_required
    def ajuda_consulta(consulta_id: int):
        """Uma consulta como ela foi — o que saiu e o que voltou."""
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            if not AJ.pode_usar(con, papel_do_usuario()):
                flash("A ajuda do sistema não está liberada para o seu perfil.",
                      "danger")
                # `dashboard`, E NAO `index`: nao existe rota chamada `index`
                # neste sistema, e o `url_for` estourava — a recusa virava
                # HTTP 500 justamente para quem ela recusava. Nenhum teste
                # passava por aqui porque nenhum abria uma consulta com o
                # perfil errado; agora ha um.
                return redirect(url_for("dashboard"))
            linha = AJ.ler(con, consulta_id)
        if not linha:
            flash("Consulta não encontrada.", "danger")
            return redirect(url_for("ajuda_consultar"))
        return render_template(
            "ajuda_consulta.html", consulta=dict(linha),
            sanitizacao=AJ.detalhes_sanitizacao(linha),
            # O RASTRO DAS LEITURAS VAI PARA A TELA, e não só para o banco:
            # quem lê a resposta precisa poder conferir em que ela se apoiou.
            passos=AJ.passos_da_consulta(linha))

    @app.route("/ajuda/<int:consulta_id>/avaliar", methods=["POST"])
    @login_required
    def ajuda_avaliar(consulta_id: int):
        """Diz se a resposta prestou. ESCREVE.

        Módulo que ninguém avalia é módulo que ninguém melhora — e resposta
        marcada como ruim é por onde se descobre que a instrução do sistema
        está incompleta.
        """
        try:
            with db.transaction() as con:
                AJ.exigir_permissao(con, papel_do_usuario())
                AJ.avaliar(con, consulta_id, util=_campo("util") == "1",
                           observacao=_campo("observacao") or None)
        except AJ.AjudaError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ajuda_consulta", consulta_id=consulta_id))
        flash("Obrigado — isso é o que faz a ajuda melhorar.", "success")
        return redirect(url_for("ajuda_consulta", consulta_id=consulta_id))

    # -------------------------------------------------------- os problemas

    @app.route("/ajuda/problema", methods=["POST"])
    @login_required
    def ajuda_problema():
        """Alguém do balcão conta que algo deu errado. ESCREVE.

        NÃO PASSA PELA LISTA DE PERFIS, e não é esquecimento: anotar problema
        não gasta e não manda nada para fora. Quem topa com o defeito é o
        balcão, e o balcão não pode ficar sem poder avisar por causa de uma
        regra que existe para outra coisa.

        E defeito que NÃO estoura o programa — o botão que não faz nada, o
        número que sai errado — é justamente o que máquina nenhuma percebe
        sozinha.

        RESPONDE DOS DOIS JEITOS, e por isso o campo `formato`. Com script, a
        janela manda `json` e a pessoa não sai da tela em que está. Sem script,
        o mesmo formulário manda a mesma coisa e volta para a tela de onde
        saiu, com o recado — que é o que a casa faz em toda parte.
        """
        de_onde = _campo("onde")
        try:
            with db.transaction() as con:
                r = AP.anotar(
                    con, origem="RELATADO", titulo=_campo("titulo"),
                    detalhe=_campo("detalhe") or None, onde=de_onde or None,
                    caminho=_campo("caminho") or None, versao=versao,
                    usuario=usuario_nome(), agora=agora(),
                    criado_por=login_do_usuario())
        except AP.ProblemaError as erro:
            if _campo("formato") == "json":
                return jsonify({"ok": False, "erro": str(erro)}), 200
            flash(str(erro), "danger")
            return redirect(_de_volta())
        audit("AJUDA_PROBLEMA_RELATADO", "aj_problemas", r["id"],
              {"onde": de_onde, "vezes": r["vezes"]})
        recado = ("Anotado. Obrigado — é assim que o defeito chega a quem "
                  "conserta." if r["nova"] else
                  f"Anotado. Isto já tinha acontecido antes: é a "
                  f"{r['vezes']}ª vez.")
        if _campo("formato") == "json":
            return jsonify({"ok": True, "id": r["id"], "vezes": r["vezes"],
                            "recado": recado})
        flash(recado, "success")
        return redirect(_de_volta())

    @app.route("/ajuda/problemas")
    @login_required
    def ajuda_problemas():
        """O que quebrou, o que a casa mediu, e o relatório para o conserto.

        ADMIN E GERENTE, e não só o ADMIN: é a mesma régua do aviso de disputa
        de escrita, que já aparece para os dois. Saber o que está quebrado na
        serventia é de quem responde por ela.

        A LISTA ABRE NO QUE AINDA PEDE ALGUMA COISA — relato #82, de
        17/09/2026. Ela mostrava os **83** problemas numa tabela só, e os
        resolvidos afogavam os abertos: medido hoje (17/09/2026, 19h04), são
        **65** resolvidos, **17** em aberto e **1** com uma palavra que o
        sistema não conhece. Quem abria a tela para saber o que havia para
        fazer lia primeiro o que já estava feito. A vista é da TELA, e a régua
        é do módulo (`AP.vista_escolhida`, `AP.listar`): a mesma pergunta é
        feita pela janela da ajuda e pelo relatório.

        O FILTRO É POR ENDEREÇO, GET, como o de todas as listas da casa — o
        operador guarda «os abertos» nos favoritos e o botão de voltar do
        navegador funciona.

        O BALCÃO VÊ OS SEUS — relato #87, decisão do oficial em 23/09/2026.
        Até ali a tela era só de ADMIN e gerente, e quem relatou não tinha
        como saber se o seu foi resolvido. Agora todo usuário logado a abre:
        quem gere a lista vê todos, com o botão «Só os meus»; o balcão vê
        APENAS o que ele mesmo relatou ou onde a tela dele estourou — o relato
        de um colega não é assunto de outro. E o que é de gestão (conferir a
        casa, o relatório, a nota do desenvolvimento, fechar) continua só de
        quem gere.
        """
        vista = AP.vista_escolhida(request.args.get("vista"))
        ambiente_filtro = AP.ambiente_filtro_escolhido(
            request.args.get("ambiente"))
        gere = gere_a_lista()
        so_meus = (not gere) or request.args.get("meus") == "1"
        dono = login_do_usuario() if so_meus else None
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            AP.init_problemas_schema(con)
            exibir_badge_ambiente = AP.banco_e_sandbox(con)
            problemas = AP.listar(
                con, situacao=AP.VISTAS[vista]["situacoes"],
                criado_por=dono, ambiente_filtro=ambiente_filtro)
            quadro = AP.contagem(con, criado_por=dono)
            relatorios = ([dict(r) for r in con.execute(
                """SELECT * FROM aj_relatorios ORDER BY id DESC LIMIT 10""")]
                if gere else [])
            liberado = gere and AJ.pode_usar(con, papel_do_usuario())
            escolha = AJ.escolha_para_tela(con)
        for p in problemas:
            p["pode_reabrir"] = AP.pode_reabrir(
                p, papel=papel_do_usuario(), login=login_do_usuario())
        return render_template(
            "ajuda_problemas.html", problemas=problemas, quadro=quadro,
            relatorios=relatorios, origens=AP.ORIGENS, liberado=liberado,
            vista=vista, vistas=AP.VISTAS, gere=gere, so_meus=so_meus,
            # OS ESTADOS DO RETORNO DO DESENVOLVIMENTO — relato #35. Saem do
            # módulo, e não escritos na tela: duas listas divergem no primeiro
            # conserto, e a tela passaria a oferecer estado que o módulo recusa.
            estados_dev=AP.ESTADOS_DO_DEV,
            rotulo_curto_dev=AP.ROTULO_CURTO_DEV,
            exibir_badge_ambiente=exibir_badge_ambiente,
            exibir_filtro_ambiente=exibir_badge_ambiente,
            ambiente_filtro=ambiente_filtro,
            ambientes_filtro=AP.AMBIENTES_FILTRO,
            params_url_lista_problemas=AP.params_url_lista_problemas,
            tem_chave=PROV.tem_chave(pasta_de_dados(), escolha["provedor"]))

    @app.route("/ajuda/problemas/conferir", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def ajuda_conferir():
        """Roda a conferência da casa e anota o que achou. ESCREVE.

        A CONFERÊNCIA É PEDIDA, e não automática em toda tela: ela lê o banco
        inteiro (`quick_check`) e as chaves estrangeiras, e isso leva segundos
        num banco de 111 MB. Rodar isso ao abrir tela poria o balcão esperando
        por uma coisa que ninguém pediu.
        """
        quando = agora()
        disputas = db.disputas_de_escrita()
        banco = db.conferencia_do_banco()
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            achados = AP.conferir_a_casa(con, agora=quando,
                                         disputas=disputas, banco=banco)
        with db.transaction() as con:
            r = AP.anotar_achados(con, achados, agora=quando, versao=versao,
                                  usuario=usuario_nome())
        audit("AJUDA_CONFERENCIA", "aj_problemas", None, r)
        if not achados:
            flash("A conferência não achou nada: o que a casa sabe medir está "
                  "em ordem.", "success")
        else:
            flash(f"A conferência achou {r['achados']} coisa(s) — "
                  f"{r['novos']} nova(s) e {r['repetidos']} que já estavam na "
                  f"lista.", "warning")
        return redirect(url_for("ajuda_problemas"))

    @app.route("/ajuda/problemas/<int:problema_id>/situacao", methods=["POST"])
    @login_required
    def ajuda_problema_situacao(problema_id: int):
        """Fecha ou reabre um problema. ESCREVE.

        A VOLTA É PARA A MESMA VISTA DE ONDE O CLIQUE SAIU — relato #82. Quem
        está percorrendo os resolvidos e reabre um voltava para «em aberto», e
        tinha de filtrar de novo a cada item: trabalhar em lista é ir de um ao
        seguinte, e não recomeçar a cada clique.

        QUEM RELATOU REABRE O SEU, E NÃO FECHA — relato #87, decisão do oficial
        em 23/09/2026. A guarda é AQUI, e não só na tela: esconder o botão
        não tranca a rota. Quem não gere a lista só reabre, só o próprio, só o
        resolvido, e sempre dizendo por quê.
        """
        acao = _campo("acao")
        gere = gere_a_lista()
        if not gere:
            with db.connect() as con:
                con.row_factory = sqlite3.Row
                alvo = AP.ler(con, problema_id)
            if acao != "reabrir" or not alvo or not AP.pode_reabrir(
                    alvo, papel=papel_do_usuario(), login=login_do_usuario()):
                flash("Você pode reabrir um problema que você mesmo relatou, "
                      "depois de resolvido. Marcar como resolvido é de quem "
                      "administra o sistema.", "danger")
                return _volta_para_a_lista(problema_id)
        try:
            with db.transaction() as con:
                if acao == "reabrir":
                    AP.reabrir(con, problema_id, agora=agora(),
                               usuario=usuario_nome(),
                               motivo=_campo("motivo") or None,
                               exige_motivo=not gere)
                else:
                    AP.fechar(con, problema_id, agora=agora(),
                              usuario=usuario_nome(),
                              nota=_campo("nota") or None)
        except AP.ProblemaError as erro:
            flash(str(erro), "danger")
            # NA RECUSA, A LINHA CONTINUA ONDE ESTAVA — e a frase vermelha
            # precisa aparecer ao lado dela, não no alto de oitenta.
            return _volta_para_a_lista(problema_id)
        audit("AJUDA_PROBLEMA_SITUACAO", "aj_problemas", problema_id,
              {"acao": acao or "fechar", "nota": _campo("nota"),
               "motivo": _campo("motivo")})
        flash("Problema reaberto." if acao == "reabrir"
              else "Problema marcado como resolvido.", "success")
        # NO ACERTO, A LINHA MUDOU DE VISTA — quem foi resolvido saiu dos
        # abertos, quem foi reaberto saiu dos resolvidos. Ancorar num lugar
        # que a linha deixou seria rolar para o vazio.
        return _volta_para_a_lista()

    @app.route("/ajuda/projeto")
    @roles_required("ADMIN", "MANAGER")
    def ajuda_projeto():
        """O que a ajuda sabe do PROJETO — relato #26.

        SÓ LÊ, E NÃO GASTA CONSULTA. Ver o que a ajuda sabe não pode custar
        uma pergunta à API: é a mesma regra da pré-visualização — quem manda
        dado para fora tem direito de ver o que está mandando, de graça.

        E O TEXTO É O MESMO QUE VAI NA CONSULTA, pela MESMA função. Montar
        aqui uma versão «parecida» faria a tela mostrar uma coisa e a consulta
        mandar outra, e a divergência apareceria no primeiro conserto.
        """
        pedido = (request.args.get("documento") or "").strip()
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            resumo = PROJ.resumo(con, versao=versao)
            texto = PROJ.para_a_consulta(con, versao=versao,
                                         documento_pedido=pedido)
            doc = PROJ.documento(pedido) if pedido else None
        if pedido and not doc:
            flash("Esse documento não existe nesta instalação.", "warning")
        return render_template("ajuda_projeto.html", r=resumo, doc=doc,
                               texto=texto, versao=versao)

    @app.route("/ajuda/base")
    @roles_required("ADMIN", "MANAGER")
    def ajuda_base():
        """A base de conhecimento da ajuda: o que está indexado e o que você escreve.

        **SÓ LÊ, E NÃO GASTA CONSULTA** — é a mesma régua de `/ajuda/projeto`:
        ver o que a ajuda sabe não pode custar uma pergunta à API. O quadro sai
        da própria base, que já está carregada; a tela não refaz a medição.

        **E ELA DIZ A VERDADE QUANDO A BASE NÃO TEM O QUE SE ESPERA.** Se os
        documentos não chegaram nesta instalação, o número aparece abaixo do
        piso e a tela diz que é isso — ausência com cara de medição é o defeito
        que este módulo existe para não repetir.
        """
        pedido = request.args.get("editar") or ""
        procura = (request.args.get("procurar") or "").strip()
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            quadro = BASE.para_a_tela(con)
            em_edicao = BASE.verbete(con, int(pedido)) if pedido.isdigit() else None
            achado = (BASE.buscar_em_tudo(procura, con=con) if procura else "")
            # AS LINHAS QUE VÃO EM TODA PERGUNTA, medidas aqui dentro — a
            # conexão morre ao sair do `with`, e a tela não pode montá-las
            # por conta própria: duas montagens do mesmo texto divergiriam no
            # primeiro conserto, e a tela mostraria uma coisa e a ajuda mandaria
            # outra.
            contexto = BASE.para_o_contexto(con)
        return render_template("ajuda_base.html", r=quadro, em_edicao=em_edicao,
                               versao=versao, achado=achado, procura=procura,
                               contexto=contexto,
                               piso=BASE.PISO_DE_DOCUMENTOS,
                               limite=BASE.LIMITE_DE_VERBETES_NO_CONTEXTO)

    @app.route("/ajuda/base/gravar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def ajuda_base_gravar():
        """Grava um verbete da base. **ESCREVE** — na tabela da ajuda, e só nela.

        **A PORTA É DO OFICIAL, E É DELIBERADO.** O que ele escrever aqui a
        ajuda lê como leem os documentos: com a mesma convicção. Um verbete
        errado não fica no caderno de quem o escreveu — fica na resposta que o
        balcão vai receber como «a casa decidiu assim».
        """
        id_ = int(_campo("id") or 0)
        try:
            with db.transaction() as con:
                con.row_factory = sqlite3.Row
                alvo = BASE.gravar_verbete(
                    con, titulo=_campo("titulo"), texto=request.form.get("texto") or "",
                    assunto=_campo("assunto"), onde=_campo("onde"),
                    por=usuario_nome(), agora=agora(), id_=id_ or None)
            audit("AJUDA_BASE_VERBETE_GRAVADO", "aj_verbetes", alvo,
                  {"titulo": _campo("titulo"), "edicao": bool(id_)})
            flash("Gravado: a ajuda já lê isto na próxima pergunta.", "success")
        except BASE.BaseError as erro:
            flash(str(erro), "danger")
        return redirect(url_for("ajuda_base"))

    @app.route("/ajuda/base/<int:verbete_id>/apagar", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def ajuda_base_apagar(verbete_id: int):
        """Tira um verbete da base. **ESCREVE** — e não é ato de cartório.

        O que estava escrito estava errado, e deixar a linha velha seria pior:
        a ajuda a leria com a mesma convicção das outras. Apagar aqui é apagar
        o caderno da ajuda; nada do que a serventia lavrou passa por esta
        tabela.
        """
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            antes = BASE.verbete(con, verbete_id)
        if not antes:
            flash("Esse verbete não existe mais — ele pode ter sido apagado "
                  "noutra aba.", "warning")
            return redirect(url_for("ajuda_base"))
        with db.transaction() as con:
            BASE.apagar_verbete(con, id_=verbete_id)
        audit("AJUDA_BASE_VERBETE_APAGADO", "aj_verbetes", verbete_id,
              {"titulo": antes["titulo"]})
        flash(f"«{antes['titulo']}» saiu da base.", "success")
        return redirect(url_for("ajuda_base"))

    @app.route("/ajuda/problemas/importar-notas", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def ajuda_importar_notas():
        """Sobe um documento de texto com as notas do desenvolvimento. ESCREVE.

        Pedido do oficial em 30/08/2026, depois que o Windows recusou a
        gravação direta: o banco de produção dá leitura ao usuário que
        desenvolve e escrita só ao SISTEMA, que roda o servidor. **A permissão
        está certa** — quem escreve passa a ser a aplicação, e quem manda
        escrever é o oficial, subindo o arquivo.

        UM ERRO NÃO DERRUBA OS OUTROS: o que der certo entra, o que não der
        volta na tela com o motivo, bloco a bloco.
        """
        arquivo = request.files.get("documento")
        texto = (request.form.get("texto") or "")
        if arquivo and arquivo.filename:
            try:
                texto = arquivo.read().decode("utf-8")
            except UnicodeDecodeError:
                flash("Não consegui ler o arquivo: ele precisa estar em UTF-8. "
                      "Salve como «texto sem formatação, UTF-8».", "danger")
                return redirect(url_for("ajuda_problemas"))
        if not texto.strip():
            flash("Nem arquivo nem texto — não havia o que importar.", "warning")
            return redirect(url_for("ajuda_problemas"))
        with db.transaction() as con:
            con.row_factory = sqlite3.Row
            r = AP.importar_notas(con, texto, agora=agora(),
                                  por=usuario_nome())
        if r["quantas"]:
            flash(f"{r['quantas']} "
                  f"{'nota gravada' if r['quantas'] == 1 else 'notas gravadas'}. "
                  f"**Nenhum problema foi fechado** — isso continua sendo o seu "
                  f"clique.", "success")
        for x in r["recusadas"]:
            flash(f"#{x['id']} não entrou: {x['porque']}", "warning")
        return redirect(url_for("ajuda_problemas"))

    @app.route("/ajuda/problemas/<int:problema_id>/nota-dev", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def ajuda_problema_nota_dev(problema_id: int):
        """Grava o retorno do desenvolvimento no problema. ESCREVE.

        Relato #35 do oficial: «criar um campo para completar com notas do
        desenvolvimento sobre a eventual solução ou pendência (…) os que forem
        resolvidos a IA ou desenvolvedor já coloca **a prova do cumprimento**».

        **NÃO FECHA O PROBLEMA.** Nenhum estado mexe na situação: marcar como
        resolvido continua sendo o clique do oficial. O máximo que a nota diz é
        «atendido, confira pela prova» — quem decide se o que ele relatou foi
        resolvido é quem relatou.
        """
        try:
            with db.transaction() as con:
                r = AP.anotar_desenvolvimento(
                    con, problema_id,
                    nota=request.form.get("nota_dev", ""),
                    estado=request.form.get("estado", ""),
                    prova=request.form.get("prova", ""),
                    agora=agora(), por=usuario_nome())
        except ValueError as erro:
            flash(str(erro), "danger")
            return _volta_para_a_lista(problema_id)
        flash(f"Nota do desenvolvimento gravada: {r['nome_do_estado']}. "
              f"O problema **continua aberto** — marcar como resolvido é seu.",
              "success")
        return _volta_para_a_lista(problema_id)

    @app.route("/ajuda/problemas/<int:problema_id>/ler", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def ajuda_problema_diagnosticar(problema_id: int):
        """Pede à ajuda uma leitura do problema. FALA COM A REDE.

        É CONSELHO, e fica marcado como conselho na tela e no relatório. O
        Lote 2 também entrega um trecho local do código, sem executá-lo ou
        alterá-lo. Quem conserta ainda precisa conferir e testar.
        """
        try:
            with db.connect() as con:
                con.row_factory = sqlite3.Row
                mapa = _mapa(con)
            resultado = AP.diagnosticar(
                db, problema_id, pasta_de_dados=pasta_de_dados(),
                agora=agora(), papel=papel_do_usuario(),
                usuario=usuario_nome(),
                raiz=Path(app.root_path), app=app, versao=versao,
                # O ESTADO DO PROJETO VAI SEMPRE AQUI — relato #26:
                # «acesso ao projeto do sistema para saber o que ja foi feito,
                #  o que falta». Esta e a tela onde ele pediu isso, e e a
                # pergunta que mais precisa: ler um defeito sem saber em que
                # versao a casa esta, o que ja foi consertado e o que espera
                # decisao do oficial e ler no escuro.
                conhecimento=conhecimento_da_tela(
                    _campo("onde") or None, com_projeto=True,
                    documento=_campo("documento")), mapa=mapa)
        except (AP.ProblemaError, AJ.AjudaError, PROV.AgenteError) as erro:
            flash(str(erro), "danger")
            return _volta_para_a_lista(problema_id)
        audit("AJUDA_PROBLEMA_LIDO", "aj_problemas", problema_id,
              {"codigo": resultado.get("codigo")})
        flash("A ajuda leu o problema. A leitura é conselho — confira antes "
              "de mexer.", "success")
        return _volta_para_a_lista(problema_id)

    @app.route("/ajuda/problemas/relatorio", methods=["POST"])
    @roles_required("ADMIN", "MANAGER")
    def ajuda_relatorio():
        """Gera o relatório para quem for consertar, e o baixa. ESCREVE.

        O ARQUIVO FICA NA MÁQUINA, ALÉM DE BAIXAR. Baixar é o caminho comum;
        ficar em disco é o que salva o dia em que o navegador perde o arquivo
        ou em que quem baixou não é quem vai mandar.
        """
        # UMA HORA SÓ PARA TUDO. Chamar o relógio quatro vezes poria a folha de
        # rosto, o nome do arquivo e o registro no banco com horas diferentes
        # por um segundo — e é justamente por esses três que se confere depois
        # qual relatório é qual.
        quando = agora()
        disputas = db.disputas_de_escrita()
        banco = db.conferencia_do_banco()
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            # A RÉGUA DE «EM ABERTO» É A MESMA DA LISTA — `em_aberto`, e não
            # um `!= 'RESOLVIDO'` escrito aqui. Escrita de dois jeitos, as
            # duas concordavam em quase tudo e discordavam exatamente no caso
            # do relato #82: a situação fora do vocabulário. O relatório sai
            # da serventia, e carregar nele um problema que a lista já não
            # mostra — ou calar o que ela mostra — é o defeito da
            # `normalizar_nome` na forma de lista.
            problemas = AP.em_aberto(con)
            achados = AP.conferir_a_casa(con, agora=quando,
                                         disputas=disputas, banco=banco)
            mapa = _mapa(con)
        texto = AP.montar_relatorio(
            problemas=problemas, achados=achados, mapa=mapa, versao=versao,
            agora=quando, serventia=dados_da_serventia(db.get_settings),
            gerado_por=usuario_nome())
        caminho = AP.guardar_relatorio(pasta_de_dados(), texto, agora=quando)
        digital = AP.digital_do_arquivo(caminho)
        ids = [int(p["id"]) for p in problemas[:AP.LIMITE_DO_RELATORIO]]
        with db.transaction() as con:
            AP.anotar_relatorio(con, arquivo=str(caminho), ids=ids,
                                agora=quando, versao=versao, sha256=digital,
                                usuario=usuario_nome())
        audit("AJUDA_RELATORIO", "aj_relatorios", None,
              {"arquivo": str(caminho), "quantos": len(ids),
               "sha256": digital})
        return send_file(caminho, as_attachment=True,
                         download_name=caminho.name)

    # ------------------------------------------- a chave e quem pode usar
    #
    # SÓ DO ADMIN, e sempre — mesmo quando a consulta estiver aberta para
    # todos. Quem muda a regra não pode ser quem a regra alcança.

    @app.route("/ajuda/configurar", methods=["GET", "POST"])
    @roles_required("ADMIN")
    def ajuda_configurar():
        """A chave da API e quem pode consultar."""
        if request.method == "POST":
            acao = _campo("acao")
            try:
                if acao == "chave":
                    _grava_chave()
                elif acao == "apagar_chave":
                    _apaga_chave()
                elif acao == "provedor":
                    _grava_provedor()
                elif acao == "perfis":
                    perfis = request.form.getlist("perfis")
                    with db.transaction() as con:
                        r = AJ.liberar_para(con, perfis, agora=agora(),
                                            motivo=_campo("motivo") or None,
                                            usuario=usuario_nome())
                    audit("AJUDA_ACESSO_ALTERADO", "aj_config", 1,
                          {"perfis": r["perfis"], "motivo": _campo("motivo")})
                    flash(f"A ajuda passa a valer para: "
                          f"{', '.join(r['perfis'])}.", "success")
            except (AJ.AjudaError, PROV.AgenteError) as erro:
                flash(str(erro), "danger")
            return redirect(url_for("ajuda_configurar"))

        with db.connect() as con:
            con.row_factory = sqlite3.Row
            acesso = AJ.situacao_do_acesso(con)
            quadro = AJ.contagem(con, hoje())
            historicas = AJ.historicas_sem_protecao(con, limite=20)
            mapa = _mapa(con)
            escolha = AJ.escolha_para_tela(con)
        return render_template(
            "ajuda_configurar.html", acesso=acesso, quadro=quadro,
            historicas=historicas, escolha=escolha,
            # O CATÁLOGO INTEIRO, e não só o provedor em uso: esta é a tela
            # onde se TROCA de provedor, e uma lista que mostrasse só o atual
            # não teria como oferecer o outro. É a mesma lista do Agente do
            # sistema — um lugar só, para as duas telas não divergirem.
            provedores=PROV.catalogo_para_tela(pasta_de_dados()),
            tem_chave=PROV.tem_chave(pasta_de_dados(), escolha["provedor"]),
            caminho_da_chave=PROV.caminho_da_credencial(pasta_de_dados()),
            teto=AJ.TETO_DE_CONSULTAS_POR_DIA,
            teto_de_tokens=AJ.TETO_DE_TOKENS_POR_DIA, mapa=mapa)

    def _grava_chave() -> None:
        """A chave de um provedor. **ESCREVE EM DISCO.**

        **CAMPO VAZIO NÃO GRAVA E NÃO APAGA.** `gravar_chave` recebe vazio como
        ordem de apagar — é assim que se desliga um provedor sem deixar
        credencial viva no disco —, e um formulário que gravasse o que estiver
        em branco apagaria a chave do provedor que ninguém estava olhando.
        """
        with db.connect() as con:
            padrao = AJ.provedor_em_uso(con)
        provedor = PROV.normalizar_provedor(_campo("provedor") or padrao)
        chave = request.form.get("api_key") or ""
        if not chave.strip():
            flash("O campo da chave estava vazio: nada foi gravado e nada foi "
                  "apagado. Para desligar um provedor, use o botão que apaga.",
                  "info")
            return
        caminho = PROV.gravar_chave(pasta_de_dados(), provedor, chave)
        audit("AJUDA_CHAVE_GRAVADA", "aj_config", 1,
              {"provedor": provedor, "arquivo": str(caminho)})
        flash(f"Chave do {PROV.PROVEDORES[provedor]['nome']} gravada em "
              f"{caminho}, fora do banco — o Agente do sistema usa a mesma.",
              "success")

    def _apaga_chave() -> None:
        """Apaga a chave de um provedor. **ESCREVE EM DISCO.**

        **APAGA PARA OS DOIS.** O arquivo é um só desde 14/09/2026: a ajuda e
        o agente leem as chaves do mesmo lugar, e o recado diz isso em voz alta
        — quem apaga aqui tira o provedor do agente também, e descobrir isso
        depois, com o console parado, seria descobrir na hora errada.
        """
        provedor = PROV.normalizar_provedor(
            _campo("provedor") or PROV.PADRAO)
        PROV.gravar_chave(pasta_de_dados(), provedor, "")
        audit("AJUDA_CHAVE_APAGADA", "aj_config", 1, {"provedor": provedor})
        flash(f"A chave do {PROV.PROVEDORES[provedor]['nome']} foi apagada do "
              f"disco. Nem a ajuda nem o agente respondem por esse provedor "
              f"até alguém informar outra.", "warning")

    def _grava_provedor() -> None:
        """Quem responde pela ajuda. **ESCREVE.**

        O modelo só vai junto quando a tela manda; mandando vazio, o domínio
        limpa o que valia — o nome do modelo antigo quase nunca existe no
        provedor novo, e guardá-lo faria a primeira pergunta depois da troca
        falhar com um erro que ninguém liga a esta tela.
        """
        with db.transaction() as con:
            r = AJ.salvar_escolha(con, provedor=_campo("provedor"),
                                  modelo=_campo("modelo") or None,
                                  agora=agora(), usuario=usuario_nome())
        audit("AJUDA_PROVEDOR_ALTERADO", "aj_config", 1,
              {"provedor": r["provedor"], "modelo": r["modelo"]})
        flash(f"A ajuda passa a responder pelo {r['provedor_nome']}, no modelo "
              f"{r['modelo']}.", "success")
