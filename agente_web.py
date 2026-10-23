"""AS TELAS DO AGENTE — o console de quem responde pela serventia.

SÓ O ADMIN, E SEM OPÇÃO DE EXPANDIR — e a diferença com a ajuda é o ponto
    A ajuda nasceu fechada **com opção de expandir** porque responder dúvida de
    balcão é para o balcão. Isto aqui não é dúvida: é gente com permissão de
    mudar o sistema, lendo o código da casa e mexendo no alcance dos módulos.
    Quem responde pela serventia é o oficial, e é ele quem clica aqui. Se um dia
    isso precisar mudar, muda no código, com quem decidir sabendo o que decidiu.

    A ROTA E O DOMÍNIO CONFEREM A MESMA COISA. O menu esconde por educação; a
    rota recusa por dever. `roles_required` fecha a porta inteira, e as funções
    de domínio não têm regra própria de perfil: duas réguas divergiriam, e a
    que ficasse frouxa não avisaria ninguém.

A TELA NÃO ESCONDE O QUE GASTA
    Sessão que consome dinheiro de verdade mostra quanto gastou, quantos turnos
    deu e onde parou. **Oficial que não vê o preço não pode decidir sobre ele**,
    e a conta chega no fim do mês de qualquer jeito.

O QUE A TELA MOSTRA É O QUE O MODELO VIU
    A conversa desenhada aqui sai de `agente.conversa`, que é a **mesma**
    tradução que vai ao provedor. Montar na tela uma versão «parecida» faria a
    tela mostrar uma coisa e a consulta mandar outra, e a divergência apareceria
    no primeiro conserto — é a mesma decisão da pré-visualização da ajuda.

A CHAVE NÃO PASSA PELO BANCO
    Ela vai direto para `agente.cred`, ao lado de `claude.cred`. E **campo
    vazio não apaga nada**: quem apaga é o botão que diz que apaga. Um
    formulário que gravasse o que estiver em branco apagaria a chave do
    provedor que ninguém estava olhando.

A RODADA CORRE ATRÁS, E A TELA NÃO FICA PARADA
    O console chamava o agente e esperava: um turno leva dezenas de segundos, e
    a página ficava travada sem saber se ele estava pensando ou se o sistema
    tinha morrido. Agora a rota abre a sessão, devolve o id e a rodada corre em
    segundo plano — a tela pergunta «como está?» em `/agente/andamento/<id>`,
    que **só lê** e devolve apenas o que ainda não foi desenhado.

    **A GAVETA EM TODA TELA É A MESMA RODADA, COM O MESMO MODELO DE CONVERSA.**
    Ela opera de qualquer tela, como a janela da ajuda — e o HTML dos passos
    sai de `_agente_passos.html`, que é o mesmo que desenha a sessão inteira.
    Montar a conversa duas vezes faria a gaveta mostrar uma coisa e a tela da
    sessão outra, e a divergência apareceria no primeiro conserto.

    ELA CONTINUA SENDO DO ADMIN, e a régua da ajuda não se aplica: a ajuda
    responde dúvida e pode ser liberada ao balcão com um clique; isto aqui mexe
    no sistema.

NADA AQUI LAVRA NADA
    Não há rota que escreva em livro, matrícula, escritura, título, selo,
    cobrança ou caixa. O agente apura, diagnostica e resolve o que é pequeno:
    anota no problema, registra o achado da conferência e abre ou fecha um
    módulo. Ato continua sendo do delegatário, com gente no meio.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from flask import (flash, jsonify, redirect, render_template, request,
                   url_for)

import agente as AGT
import agente_ferramentas as FER
import agente_provedores as PROV
import agente_schema as AGS

# AS DUAS TELAS QUE DESENHAM A CONVERSA INTEIRA — e por isso não levam a gaveta.
#
# **A GAVETA EXISTE PARA AS OUTRAS TELAS.** Quem está no console ou numa sessão
# já tem a conversa na frente, e desenhá-la outra vez na mesma página daria duas
# listas de ferramenta com o mesmo conteúdo, cada uma atualizando no seu ritmo —
# e quem comparasse as duas veria números diferentes por um instante. É a mesma
# decisão de «não se põe um atalho para onde já se está».
#
# A lista é curta de propósito: são as telas que MOSTRAM a conversa, e não as
# rotas que a movem (`pedir`, `responder`, `desfazer`), que não desenham nada.
TELAS_DO_AGENTE = ("agente_console", "agente_sessao")

#: O AGENTE SAIU DA TELA EM 06/10/2026 — ordem do oficial: «desativar o modulo
#: de agente do sistema. apenas nao aparecer mais, desenvolvimento fica pro
#: futuro». NADA SE APAGOU: as rotas (ADMIN), as tabelas `ag_*`, as sessões e a
#: chave ficam; some o que se vê — o item «Agente do sistema», o «Agente —
#: configurar» e a gaveta de toda tela. Voltar é trocar para True.
AGENTE_VISIVEL = False


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """Pendura o console do agente no app já construído.

    A ASSINATURA É A DA CASA, e não uma minha: os módulos de tela deste sistema
    recebem os mesmos argumentos e pegam o resto de `app.extensions`.
    """

    # O RELÓGIO É O MESMO DO RESTO DA CASA — hora local, sem fuso. O
    # `ruff` pede `datetime.now(tz=...)`, e aqui a regra dele está errada para
    # este sistema: todo carimbo deste banco é hora local ingênua, e um formato
    # diferente numa tabela só faria a comparação com o resto mentir.
    #
    # E VAI COMO FUNÇÃO, e não como instante: uma sessão do agente atravessa
    # minutos, e um instante fixo carimbaria todos os passos com a hora do
    # começo — a tela mentiria sobre a ordem em que as coisas aconteceram.
    def agora() -> str:
        return datetime.now().isoformat(timespec="seconds")   # noqa: DTZ005

    def hoje() -> str:
        return datetime.now().date().isoformat()              # noqa: DTZ005

    def pasta_de_dados() -> Path:
        return Path(app.config["DATA_DIR"])

    usuario_nome = app.extensions["usuario_nome"]
    papel_do_usuario = app.extensions["usuario_papel"]
    versao = app.config.get("VERSION") or ""

    # --------------------------------------------------------- o texto miúdo

    def _campo(nome: str, padrao: str = "") -> str:
        return (request.form.get(nome) or padrao).strip()

    def _marcado(nome: str) -> bool:
        return request.form.get(nome) is not None

    def _de_volta() -> str:
        """A tela de onde o formulário saiu, sem sair da casa.

        VEM DO CAMPO `sessao_id`, QUE É NOSSO, e não do `Referer`: aquele é
        cabeçalho que qualquer página de fora escreve. Sem ele, volta ao
        console — de onde se vê a lista inteira de mudanças, que é o lugar certo
        para quem acabou de desfazer uma.
        """
        try:
            de_sessao = int(_campo("sessao_id") or 0)
        except ValueError:
            de_sessao = 0
        if de_sessao:
            return url_for("agente_sessao", sessao_id=de_sessao)
        return url_for("agente_console")

    def _quer_json() -> bool:
        """A tela pediu a resposta para ela mesma desenhar?

        **O MESMO FORMULÁRIO SERVE AOS DOIS**, como na janela da ajuda: com
        `formato=json` quem pediu não sai da tela em que está; sem script, o
        formulário faz o caminho antigo e volta com o recado. Duas telas para a
        mesma coisa divergiriam no primeiro conserto — e uma delas é a que
        opera de dentro de outra tela.
        """
        return (request.values.get("formato") or "").strip() == "json"

    def _inteiro(nome: str, padrao: int = 0) -> int:
        """Um cursor de leitura. Zero no que não for número.

        **NÃO ESTOURA DE PROPÓSITO:** o cursor vem da tela e volta igual, e um
        `?desde=abc` digitado na barra de endereço viraria HTTP 500 numa tela
        que só estava perguntando «como está?». Cursor inválido não perde nada
        — zero quer dizer «me mande tudo», que é o que a tela desenha na
        primeira pergunta.
        """
        try:
            return int(request.values.get(nome) or padrao)
        except (TypeError, ValueError):
            return padrao

    def _onde_da_tela() -> str:
        """A tela de onde o pedido saiu, com os argumentos dela. Só calcula.

        **SAI DO `request.endpoint`, E NÃO DE CAMPO DIGITADO** — a mesma régua
        da janela da ajuda: campo que o operador tem de preencher para a
        resposta ficar boa é campo que fica vazio. É isto que faz a gaveta
        saber que a pergunta nasceu na ficha da matrícula 3.110, e não «no
        sistema»; o agente responde sobre a ficha que está aberta em vez de
        perguntar qual era.
        """
        pedacos = [str(request.endpoint or "")]
        for chave, valor in sorted((request.view_args or {}).items()):
            pedacos.append(f"{chave}={valor}")
        return " ".join(p for p in pedacos if p)

    def _recusa_de_rodada(mensagem: str, destino: str):
        """O pedido recusado ANTES de gastar turno. Responde dos dois jeitos."""
        if _quer_json():
            return jsonify({"ok": False, "erro": mensagem}), 200
        flash(mensagem, "danger")
        return redirect(destino)

    def _anotar_na_auditoria(acao: str, sessao_id: int) -> None:
        """O rastro de que a rodada começou. **GRAVA O QUE SE SABE AGORA.**

        Antes desta mudança a rota esperava a rodada e anotava turnos e tokens
        junto — porque era o único instante em que ela sabia. Agora a rodada
        segue atrás e o fim se lê em `ag_sessoes`, que é onde a tela o lê: o
        que mudou de lugar foi a **duplicata**, e não o rastro. O que se anota
        aqui é o que só existe no começo — com quem, por qual provedor, e de
        que tela o pedido saiu.
        """
        try:
            with db.connect() as con:
                s = AGS.ler_sessao(con, int(sessao_id))
        except sqlite3.Error:            # a auditoria não derruba o pedido
            s = None
        audit(acao, "ag_sessoes", sessao_id, {
            "provedor": (s["provedor"] if s else ""),
            "modelo": (s["modelo"] if s else ""),
            "onde": _onde_da_tela(),
        })

    def _recado_da_config(config: dict) -> str:
        """Diz o que PASSOU A VALER, e não o que foi digitado.

        O teto que a tela oferece é preso no limite duro, e um recado que
        repetisse o número digitado diria «guardado 900» sobre um teto de 24. É
        o mesmo cuidado do `gravar_config`, que recusa em vez de ignorar calado.
        """
        sozinho = config["escrita_ligada"] and config.get("escrita_sem_confirmacao")
        return (f"Guardado. Vale agora: provedor {config['provedor_padrao']}, "
                f"modelo {config['modelo_padrao'] or '(o padrão do provedor)'}, "
                f"até {config['teto_de_turnos']} turnos por rodada, "
                f"{config['teto_de_sessoes']} sessões por dia, escrita "
                f"{'LIGADA' if config['escrita_ligada'] else 'desligada'}"
                f"{' (aplica sem confirmação)' if sozinho else ''}.")

    # ------------------------------------------------------------- o console

    @app.route("/agente")
    @roles_required("ADMIN")
    def agente_console():
        """O painel: como está, o que já foi feito, e a caixa do pedido. SÓ LÊ.

        GET NÃO ABRE TRANSAÇÃO DE ESCRITA. Tela de leitura que grava fica presa
        no `busy_timeout` enquanto outro balcão lavra — e a regra aqui é a
        mesma da ajuda, pela mesma razão.
        """
        painel = AGT.painel(db, pasta_de_dados=pasta_de_dados(), hoje=hoje())
        return render_template(
            "agente.html", p=painel, versao=versao,
            catalogo_leitura=[f for f in painel["catalogo"]
                              if f["tipo"] == FER.LEITURA],
            catalogo_escrita=[f for f in painel["catalogo"]
                              if f["tipo"] == FER.ESCRITA])

    @app.route("/agente/pedir", methods=["POST"])
    @roles_required("ADMIN")
    def agente_pedir():
        """O oficial escreve o que quer que o agente apure. FALA COM A REDE.

        **A ROTA NÃO ESPERA.** Ela abre a sessão, devolve o id e a rodada corre
        em segundo plano — quem desenha pergunta «como está?» a cada segundo em
        `/agente/andamento/<id>`. Esperar aqui deixaria a página parada por
        minutos, e da gaveta, no meio de outro trabalho, isso é pior: quem
        pediu não sabe se ele está pensando ou se o sistema morreu.

        **A SESSÃO JÁ ESTÁ GRAVADA QUANDO ISTO RESPONDE**, e está ABERTA: se o
        programa cair no meio, ela volta como interrompida quando o banco abre.
        O que se pode perder é a rodada, nunca a sessão.

        **VAI O RELÓGIO, E NÃO A HORA DO CLIQUE** — e isso é conserto de
        18/09/2026, com o problema #74 na mão. `agora=agora()` congelava o
        instante de abertura e `_relogio` o obedecia: **todos os passos da rodada
        saíam com a hora do primeiro**, de modo que a tela não tinha como dizer
        quanto tempo a rodada levou — e «trava e não responde» era exatamente a
        pergunta que não se podia responder com o que estava gravado. O módulo
        já dizia isso no docstring do próprio `_relogio`.

        RESPONDE DOS DOIS JEITOS, como a janela da ajuda: com `formato=json` a
        gaveta recebe o id e não sai da tela em que está; sem script, o mesmo
        formulário volta para a sessão com o recado.
        """
        try:
            sessao_id = AGT.iniciar(
                db, pedido=_campo("pedido"), pasta_de_dados=pasta_de_dados(),
                raiz=Path(app.root_path), agora=agora,
                usuario=usuario_nome(), versao=versao, app=app,
                provedor=_campo("provedor") or None,
                modelo=_campo("modelo") or None, onde=_onde_da_tela())
        except (AGT.AgenteRecusado, PROV.AgenteError) as recusa:
            return _recusa_de_rodada(str(recusa), url_for("agente_console"))

        _anotar_na_auditoria("AGENTE_SESSAO", sessao_id)
        if _quer_json():
            return jsonify({"ok": True, "sessao_id": sessao_id,
                            "url": url_for("agente_sessao",
                                           sessao_id=sessao_id)})
        return redirect(url_for("agente_sessao", sessao_id=sessao_id))

    @app.route("/agente/sessao/<int:sessao_id>")
    @roles_required("ADMIN")
    def agente_sessao(sessao_id: int):
        """Uma sessão inteira, como ela foi: o que se disse e o que se fez."""
        try:
            retrato = AGT.retrato(db, sessao_id)
        except AGT.AgenteRecusado as recusa:
            flash(str(recusa), "danger")
            return redirect(url_for("agente_console"))
        return render_template("agente_sessao.html", r=retrato, versao=versao)

    @app.route("/agente/sessao/<int:sessao_id>/responder", methods=["POST"])
    @roles_required("ADMIN")
    def agente_responder(sessao_id: int):
        """Continua a conversa. FALA COM A REDE.

        **É o que faz o console ser um console:** o agente para no teto, ou
        termina e faz uma pergunta, e o oficial escreve de volta na MESMA
        conversa — com tudo o que já foi lido ali dentro. Sem isto, continuar um
        diagnóstico custaria repetir o diagnóstico.

        **E NÃO ESPERA, pela mesma razão do pedido novo:** o que já foi lido
        continua guardado, e quem continua não precisa ficar olhando a página
        parada para não perder o fio.
        """
        try:
            AGT.continuar(
                db, sessao_id, pedido=_campo("pedido"),
                pasta_de_dados=pasta_de_dados(), raiz=Path(app.root_path),
                agora=agora, usuario=usuario_nome(), versao=versao, app=app,
                onde=_onde_da_tela())
        except (AGT.AgenteRecusado, PROV.AgenteError) as recusa:
            return _recusa_de_rodada(
                str(recusa), url_for("agente_sessao", sessao_id=sessao_id))

        _anotar_na_auditoria("AGENTE_SESSAO_CONTINUADA", sessao_id)
        if _quer_json():
            return jsonify({"ok": True, "sessao_id": sessao_id,
                            "url": url_for("agente_sessao",
                                           sessao_id=sessao_id)})
        return redirect(url_for("agente_sessao", sessao_id=sessao_id))

    @app.route("/agente/andamento/<int:sessao_id>")
    @roles_required("ADMIN")
    def agente_andamento(sessao_id: int):
        """O que a sessão tem de novo desde o último desenho. **SÓ LÊ.**

        **É ESTA ROTA QUE FAZ A GAVETA SER RESPONSIVA.** Quem desenha guarda até
        onde leu — `desde` é a `ordem` do último passo, `mudanca_desde` é o `id`
        da última mudança — e recebe só o que veio depois. Sem os cursores, a
        cada segundo a tela releria a conversa inteira, e o resultado de uma
        ferramenta pode ter dezenas de linhas.

        **O HTML VEM MONTADO PELO MESMO MODELO DA SESSÃO INTEIRA**
        (`_agente_passos.html`): dois desenhos da conversa divergiriam no
        primeiro conserto, e a gaveta mostraria uma coisa e a tela da sessão
        outra — a lição da pré-visualização da ajuda.

        **NÃO GRAVA NADA**, e é por isso que pode ser chamada de segundo em
        segundo: uma tela de leitura que consome contador fica presa no
        `busy_timeout` enquanto o balcão lavra, e esta roda justamente enquanto
        o agente escreve.
        """
        try:
            d = AGT.andamento(
                db, sessao_id, desde=_inteiro("desde"),
                mudanca_desde=_inteiro("mudanca_desde"))
        except AGT.AgenteRecusado as recusa:
            return jsonify({"ok": False, "erro": str(recusa)}), 200

        sessao = d["sessao"]
        gastos = (int(sessao.get("tokens_de_entrada") or 0)
                  + int(sessao.get("tokens_de_saida") or 0))
        return jsonify({
            "ok": True,
            "rodando": bool(d["rodando"]),
            "estado": sessao["estado"],
            "selo": d["selo"],
            "recado": d["recado"],
            "turnos": int(sessao.get("turnos") or 0),
            "tokens": gastos,
            # OS CURSORES VÃO DE VOLTA, e não são calculados na tela: quem sabe
            # até onde se leu é quem tem a lista na mão, e o banco é quem manda
            # na ordem (`ordem` e `id`, e não a contagem).
            "proximo": int(d["proximo"]),
            "mudanca_proxima": int(d["mudanca_proxima"]),
            "html": render_template("_agente_passos.html",
                                    passos=d["passos"]),
            # A GAVETA CONTA AS MUDANÇAS E NÃO AS DESENHA. Desfazer é ato com
            # consequência, e a gaveta é estreita: o que ela precisa dizer é que
            # ele mexeu em alguma coisa, e levar à sessão, onde está o antes e o
            # depois com o botão. Desenhar a mesma tabela duas vezes faria a
            # gaveta mostrar uma coisa e a sessão outra no primeiro conserto.
            "mudancas_novas": len(d["mudancas"]),
            # E AS LINHAS VÃO PRONTAS PARA QUEM AS DESENHA: a tela da sessão é
            # onde o botão de desfazer mora, e ali a mudança que chega com a
            # sessão rodando tem de aparecer — com o MESMO desenho da que já
            # estava, porque é o mesmo `_agente_mudancas.html`. A gaveta recebe
            # isto e não usa; mandar de qualquer jeito custa uma renderização
            # vazia, e só quando há mudança nova.
            "mudancas_html": (render_template("_agente_mudancas.html",
                                              mudancas=d["mudancas"],
                                              sessao_id=sessao_id)
                              if d["mudancas"] else ""),
            "passos_novos": len(d["passos"]),
            "total_de_passos": int(d["total_de_passos"]),
        })

    # ------------------------------------------------- a gaveta de toda tela

    @app.context_processor
    def _o_agente_em_toda_tela() -> dict:
        """A gaveta do agente existe em TODA tela — para quem pode usá-la.

        **AQUI NÃO SE ABRE BANCO NEM SE LÊ CREDENCIAL.** É só a pergunta «esta
        pessoa pode?», que já está respondida na sessão do Flask. A tentação era
        mandar junto o resumo (provedor, gasto do dia, última sessão) — e isso
        seriam três consultas e a leitura dos arquivos de chave em CADA tela
        que o oficial abrir, para desenhar um botão que ele pode nem clicar.
        Quem busca o resumo é a gaveta, quando abre: `/agente/gaveta`.

        **É A MESMA DECISÃO DA AJUDA, COM UMA DIFERENÇA.** A ajuda também mora
        no `base.html`, e lá o contexto é barato porque a janela avisa «isto já
        deu errado aqui». Aqui o aviso não vale o preço: quem abre a gaveta é
        quem já quer falar com ele.

        E ELA NÃO APARECE NA TELA DE LOGIN: sem papel, sem botão — e sem
        `agente_cred` sendo lido por quem não entrou.

        **E NEM NAS PRÓPRIAS TELAS DO AGENTE.** A gaveta existe para as OUTRAS
        telas: quem está no console ou numa sessão já tem a conversa inteira na
        frente, e a mesma conversa desenhada duas vezes na mesma página faria
        duas listas de ferramenta com o mesmo conteúdo rolando lado a lado —
        uma delas com números que andam em ritmo diferente da outra. Um botão
        que abre a cópia do que já está à vista não é atalho: é enfeite.
        """
        menu = AGENTE_VISIVEL
        if not AGENTE_VISIVEL:
            return {"agente_na_tela": False, "agente_no_menu": False}
        try:
            onde = request.endpoint or ""
        except RuntimeError:                    # fora de contexto de requisição
            return {"agente_na_tela": False, "agente_no_menu": menu}
        if not onde or onde == "static":
            return {"agente_na_tela": False, "agente_no_menu": menu}
        if onde in TELAS_DO_AGENTE:
            return {"agente_na_tela": False, "agente_no_menu": menu}
        return {"agente_na_tela": papel_do_usuario() == "ADMIN", "agente_no_menu": menu}

    @app.route("/agente/gaveta")
    @roles_required("ADMIN")
    def agente_gaveta():
        """O que a gaveta desenha quando abre. **SÓ LÊ.**

        **É UMA LEITURA SÓ, E É O QUE FAZ A GAVETA ABRIR RÁPIDO.** Ela precisa
        de quatro coisas que moram em quatro lugares: a configuração, o gasto do
        dia, a última sessão e a conversa dela. Buscadas em rotas separadas
        seriam quatro idas ao servidor para desenhar uma caixa — e a gaveta
        abriria em pedaços.

        **A SESSÃO ANTIGA VEM INTEIRA, E SÓ UMA VEZ.** O cursor volta junto
        (`proximo` e `mudanca_proxima`), e daí em diante quem responde é
        `/agente/andamento/<id>`, que devolve só o que veio depois. Sem isso, a
        gaveta releria a conversa toda a cada segundo — e o resultado de uma
        ferramenta pode ter dezenas de linhas.

        **SEM SESSÃO NENHUMA ELA NÃO INVENTA UMA:** devolve `sessao: None` e o
        formulário vazio, que é o começo de uma.
        """
        r = AGT.resumo_para_a_gaveta(db, pasta_de_dados=pasta_de_dados(),
                                     hoje=hoje())
        sessao = r["sessao"]
        conversa = {"passos": [], "mudancas": [],
                    "proximo": 0, "mudanca_proxima": 0, "total_de_passos": 0}
        if sessao:
            try:
                conversa = AGT.andamento(db, int(sessao["id"]))
            except AGT.AgenteRecusado:
                # A SESSÃO MORREU ENTRE A LISTA E A LEITURA — acontece quando
                # alguém apaga o histórico noutra janela. Não é erro de quem
                # clicou, e a gaveta abre vazia em vez de mostrar um vermelho.
                sessao = None
        gastos = 0
        if sessao:
            gastos = (int(sessao.get("tokens_de_entrada") or 0)
                      + int(sessao.get("tokens_de_saida") or 0))
        return jsonify({
            "ok": True,
            "config": r["config"],
            "avisos": r["avisos"],
            "do_dia": r["do_dia"],
            "rodando": bool(r["rodando"]),
            "recado": r["recado"],
            "sessao": ({"id": int(sessao["id"]), "titulo": sessao["titulo"],
                        "estado": sessao["estado"],
                        "turnos": int(sessao.get("turnos") or 0),
                        "tokens": gastos,
                        "url": url_for("agente_sessao",
                                       sessao_id=int(sessao["id"]))}
                       if sessao else None),
            "html": render_template("_agente_passos.html",
                                    passos=conversa["passos"]),
            "proximo": int(conversa["proximo"]),
            "mudanca_proxima": int(conversa["mudanca_proxima"]),
            "total_de_passos": int(conversa["total_de_passos"]),
        })

    # ------------------------------------------------------------ o desfazer

    @app.route("/agente/mudanca/<int:mudanca_id>/desfazer", methods=["POST"])
    @roles_required("ADMIN")
    def agente_desfazer(mudanca_id: int):
        """Volta atrás uma mudança que o agente fez. ESCREVE.

        **É esta rota que faz a permissão de escrever ser defensável**: quem
        pode desfazer com um clique pode ousar mais. E ela recusa em vez de
        fingir — mudança já desfeita, mudança de ferramenta que não sabe voltar
        e mudança que é só acréscimo. **Uma volta que não volta é pior que um
        botão que não existe**, porque dá a quem clica a impressão de ter
        consertado.
        """
        try:
            r = AGT.desfazer(db, mudanca_id, agora=agora(),
                             usuario=usuario_nome())
        except FER.FerramentaError as recusa:
            flash(str(recusa), "danger")
            return redirect(_de_volta())
        audit("AGENTE_DESFEZ", "ag_mudancas", mudanca_id, r)
        if r.get("descartada"):
            flash(f"Proposta descartada: {r['alvo']} continua como estava.",
                  "success")
        else:
            flash(f"Desfeito: {r['ferramenta']} voltou para "
                  f"«{r['voltei_para']}».", "success")
        return redirect(_de_volta())

    @app.route("/agente/mudanca/<int:mudanca_id>/aplicar", methods=["POST"])
    @roles_required("ADMIN")
    def agente_aplicar(mudanca_id: int):
        """Aplica a mudança que o agente deixou PROPOSTA. ESCREVE.

        **É O CLIQUE QUE O LS03 (M4) PÔS ENTRE O MODELO E O SISTEMA.** Com a
        confirmação ligada (o padrão), o agente não abre nem fecha módulo: ele
        propõe, e quem muda é o oficial, aqui, com o antes e o depois à vista.
        Depois de aplicada, a mudança volta com o mesmo «desfazer» de sempre.
        """
        try:
            r = AGT.aplicar(db, mudanca_id, agora=agora(),
                            usuario=usuario_nome())
        except FER.FerramentaError as recusa:
            flash(str(recusa), "danger")
            return redirect(_de_volta())
        audit("AGENTE_APLICOU", "ag_mudancas", mudanca_id, r)
        flash(f"Aplicado: {r['alvo']} passou de «{r['antes']}» para "
              f"«{r['apliquei']}».", "success")
        return redirect(_de_volta())

    # -------------------------------------------------------- a configuração

    @app.route("/agente/configurar", methods=["GET", "POST"])
    @roles_required("ADMIN")
    def agente_configurar():
        """O provedor, o modelo, os tetos, a escrita e as chaves.

        **LIGAR A ESCRITA É UM CLIQUE CONSCIENTE**, com o aviso ao lado — e não
        um padrão que veio ligado. É a mesma regra da ajuda, que também depende
        de alguém liberar: uma capacidade nasce desligada.
        """
        if request.method == "POST":
            acao = _campo("acao")
            try:
                if acao == "chave":
                    _grava_chave()
                elif acao == "apagar_chave":
                    _apaga_chave()
                else:
                    _grava_config()
            except (AGT.AgenteRecusado, PROV.AgenteError,
                    ValueError) as recusa:
                flash(str(recusa), "danger")
            return redirect(url_for("agente_configurar"))

        # A CONFIGURAÇÃO VEM PELO DOMÍNIO, e não por uma leitura minha: este
        # módulo não abre banco. Duas leituras da mesma tabela divergiriam no
        # primeiro campo novo, e a tela passaria a mostrar o que o agente não
        # obedece — que é o pior jeito de errar numa tela de permissão.
        config = AGT.config_para_tela(db)
        return render_template(
            "agente_configurar.html", config=config,
            provedores=PROV.catalogo_para_tela(pasta_de_dados()),
            caminho_da_chave=PROV.caminho_da_credencial(pasta_de_dados()),
            arquivo_da_ajuda=str(Path(app.config["DATA_DIR"])
                                 / PROV.ARQUIVO_DA_AJUDA),
            teto_de_tokens=AGT.TETO_DE_TOKENS,
            teto_maximo_de_saida=AGT.MAXIMO_DE_SAIDA,
            quantas_leitura=len([f for f in FER.FERRAMENTAS
                                 if f.tipo == FER.LEITURA]),
            quantas_escrita=len([f for f in FER.FERRAMENTAS
                                 if f.tipo == FER.ESCRITA]))

    def _grava_config() -> None:
        """Os campos da configuração. **ESCREVE.**"""
        r = AGT.salvar_config(
            db, provedor=_campo("provedor_padrao") or None,
            modelo=_campo("modelo_padrao"),
            teto_de_turnos=_campo("teto_de_turnos") or None,
            teto_de_sessoes=_campo("teto_de_sessoes") or None,
            escrita_ligada=_marcado("escrita_ligada"),
            escrita_sem_confirmacao=_marcado("escrita_sem_confirmacao"))
        audit("AGENTE_CONFIGURADA", "ag_config", 1, r)
        flash(_recado_da_config(r), "success")

    def _grava_chave() -> None:
        """A chave de um provedor. **ESCREVE EM DISCO.**

        **CAMPO VAZIO NÃO GRAVA E NÃO APAGA.** É o cuidado que o formulário de
        robôs já toma, e aqui ele vale mais: `gravar_chave` recebe vazio como
        ordem de apagar — é assim que se desliga um provedor sem deixar
        credencial viva no disco —, e um campo em branco que chegasse até lá
        apagaria a chave de um provedor que ninguém estava olhando.
        """
        provedor = _campo("provedor")
        chave = request.form.get("api_key") or ""
        if not chave.strip():
            flash("O campo da chave estava vazio: nada foi gravado e nada foi "
                  "apagado. Para desligar um provedor, use o botão que apaga.",
                  "info")
            return
        r = AGT.gravar_chave(pasta_de_dados(), provedor, chave)
        audit("AGENTE_CHAVE_GRAVADA", "ag_config", 1,
              {"provedor": r["provedor"], "arquivo": r["caminho"]})
        flash(f"Chave do {r['provedor']} gravada em {r['caminho']}, fora do "
              f"banco.", "success")

    def _apaga_chave() -> None:
        """Apaga a chave de um provedor. **ESCREVE EM DISCO.**

        Só por clique explícito, e com o recado dizendo o que aquilo custa: sem
        chave, o agente não responde por aquele provedor.
        """
        r = AGT.gravar_chave(pasta_de_dados(), _campo("provedor"), "")
        audit("AGENTE_CHAVE_APAGADA", "ag_config", 1,
              {"provedor": r["provedor"]})
        flash(f"A chave do {r['provedor']} foi apagada do disco. O agente não "
              f"responde mais por esse provedor até alguém informar outra.",
              "warning")
