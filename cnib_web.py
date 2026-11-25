"""As telas do atualizador do CNIB — **a cópia local e a ida à Central.**

O que é uma leitura, o que ela grava e por que a janela volta atrás mora em
`cnib_atualizador.py`; quem fala com a Central é `cnib_api.py`. Aqui só se
ligam os fios, na ordem que as duas regras da casa pedem: a rede **antes** da
transação, e a auditoria **fora** dela.

MÓDULO PRÓPRIO, e não dentro de `ri_web.py`: aquele arquivo é escrito por
outra passada ao mesmo tempo, e duas mãos no mesmo arquivo se atropelam.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import date

from flask import flash, redirect, render_template, request, url_for

import banco_pg
import centrais_cred as CRED
import cnib_api as API
import cnib_atualizador as ATZ
import cpf_cnpj as CC
import identidade_do_robo as IDR

# O MAIOR PEDAÇO QUE UMA IDA PODE PEDIR. Não é zelo: a fila desta serventia
# tinha 341.697 ordens, e uma janela de anos numa tacada varreria o país num
# pedido só — o freio do `cnib_api` pararia no meio e o pedaço ficaria pela
# metade sem ninguém saber onde. A posta em dia anda **mês a mês**, e este
# teto é o que impede alguém de digitar 2012 no campo e esperar sentado.
MAIOR_JANELA_EM_DIAS = 400


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """A ASSINATURA É A DA CASA — ver `ajuda_web.registrar_rotas`."""

    usuario_id = app.extensions["usuario_id"]

    def _acervo():
        """Onde mora o acervo do E-Ofício. É de onde o par do CNIB veio."""
        return db.db_path.parent / "acervo_eoficio.sqlite3"

    def _uma_ida(*, de: str, ate: str, automatica: bool, usuario, registrar):
        """Uma leitura inteira: rede, gravação e registro — nessa ordem.

        **ELA NÃO USA NADA DO PEDIDO WEB**, e isso não é capricho: a rotina
        diária a chama de uma linha de fundo, onde não há sessão, não há
        `request` e portanto não há `audit()` — que lê o usuário logado. Por
        isso quem registra entra por `registrar`: da tela é a auditoria; da
        rotina é o registro do sistema. A primeira versão disto chamava
        `audit` direto e teria estourado na primeira noite, dentro de uma
        linha de fundo onde ninguém veria o erro.

        Devolve a frase que a tela mostra e a categoria do `flash`.
        """
        with db.connect() as con:
            cpf = ATZ.cpf_de_quem_consulta(con)
        try:
            leitura = ATZ.ler_da_central(de, ate, cpf_usuario=cpf)
        except (ATZ.CnibAtualizadorError, API.CnibError) as erro:
            # A TENTATIVA QUE NÃO CHEGOU TAMBÉM FICA ESCRITA. Sem isto, amanhã
            # ninguém distingue «não há ordem nova» de «faz uma semana que não
            # se fala com a Central».
            with db.transaction() as con:
                ATZ.anotar(con, de=de, ate=ate, situacao=ATZ.ERRO,
                           agora=db.now(), usuario=usuario,
                           automatica=automatica, mensagem=str(erro))
            registrar({"de": de, "ate": ate, "situacao": ATZ.ERRO,
                       "erro": str(erro)[:400]})
            return str(erro), "danger"

        with db.transaction() as con:
            resumo = ATZ.gravar(con, de=de, ate=ate, leitura=leitura,
                                agora=db.now(), usuario=usuario,
                                automatica=automatica)
        registrar(dict(resumo, de=de, ate=ate))

        if resumo["situacao"] == ATZ.RECUSADA:
            return ("A Central respondeu numa forma que este sistema não "
                    "conhece. Nada foi gravado — e a janela não andou, de "
                    "propósito."), "danger"
        if resumo["situacao"] == ATZ.VAZIA:
            return (f"A Central não devolveu ordem nenhuma de {fmt_date(de)} a "
                    f"{fmt_date(ate)}. Isso não prova que não há: a mesma "
                    "resposta já veio para dias que tinham ordens. A próxima "
                    "busca relê esta janela."), "warning"
        frase = (f"{resumo['lidas']} ordens lidas: {resumo['novas']} novas, "
                 f"{resumo['atualizadas']} atualizadas e "
                 f"{resumo['canceladas']} que passaram a cancelada.")
        if resumo.get("parou_no_teto"):
            return (frase + " A varredura parou no teto de páginas: há mais "
                    "ordens nesta janela do que coube. Peça um pedaço "
                    "menor."), "warning"
        return frase, "success"

    # A rotina de fundo diz quem é e a mando de quem age (26/10/2026).
    identidade = {"agente": "atualizador automático do CNIB",
                  "a_mando_de": IDR.PELO_RESPONSAVEL}

    def _registrar_do_sistema(detalhes):
        db.log(None, "SISTEMA", "CNIB_LEITURA", "CNIB", None, detalhes,
               **identidade)

    def _pasta_da_fila():
        """Onde a página da fila espera entre a Central e o banco."""
        return db.db_path.parent / ATZ.PASTA_DA_GUARDA

    def _rodada_da_fila(*, automatica: bool, usuario, registrar):
        """Uma rodada da fila, com o mesmo registro da leitura por janela."""
        try:
            resumo = ATZ.ler_a_fila(db, hoje=date.today(),  # noqa: DTZ011 — relógio da casa
                                    pasta=_pasta_da_fila(), usuario=usuario,
                                    automatica=automatica)
        except ATZ.CnibAtualizadorError as erro:
            registrar({"fila": True, "situacao": ATZ.ERRO, "erro": str(erro)[:400]})
            return
        registrar(dict(resumo, fila=True))

    def _rodada_em_fundo(*, automatica: bool, usuario, registrar) -> None:
        def trabalhar():
            try:
                _rodada_da_fila(automatica=automatica, usuario=usuario,
                                registrar=registrar)
            except Exception as erro:  # noqa: BLE001 — linha de fundo não derruba nada
                try:
                    registrar({"fila": True, "situacao": ATZ.ERRO,
                               "erro": str(erro)[:400]})
                except Exception:   # noqa: BLE001,S110
                    pass
        threading.Thread(target=trabalhar, name="cnib-fila", daemon=True).start()

    # --------------------------------------------------------------- a tela

    @app.route("/registro-imoveis/cnib/central")
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def cnib_central():
        """De quando é a cópia local, e o que falta para ela ficar em dia."""
        hoje = date.today()   # noqa: DTZ011 — relógio da casa
        with db.connect() as con:
            pronto = ATZ.esta_pronto(con)
            espelho = ATZ.resumo_do_espelho(con)
            ultima = ATZ.ultima_leitura(con)
            historico = ATZ.leituras(con, 30)
            de, ate = ATZ.janela_do_dia(con, hoje=hoje)
            pedacos = ATZ.janelas_da_posta_em_dia(con, hoje=hoje)
            leu_hoje = ATZ.ja_leu_hoje(con, hoje=hoje)
            rotina = ATZ.rotina_ligada(con)
            cpf = ATZ.cpf_de_quem_consulta(con)
            fila = ATZ.fila_autorizada(con)
            data_base = ATZ.data_da_base(con, hoje=hoje)

        faltam = [p for p in pedacos if not p["feita"]]
        return render_template(
            "cnib_central.html", pronto=pronto, espelho=espelho,
            ultima=ultima, historico=historico, de=de, ate=ate,
            pedacos=pedacos, faltam=faltam, leu_hoje=leu_hoje,
            rotina=rotina, cpf=cpf, hoje=hoje.isoformat(),
            fila=fila, data_base=data_base,
            guardadas=len(ATZ.paginas_guardadas(_pasta_da_fila())),
            tem_acervo=_acervo().exists(),
            tem_credencial=API.tem_credencial(), fmt_date=fmt_date)

    # ------------------------------------------------------------ a ida

    @app.route("/registro-imoveis/cnib/central/buscar", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def cnib_buscar():
        """Uma ida à Central, na janela que o formulário mandou.

        **O BOTÃO É UM SÓ PARA A ROTINA E PARA A POSTA EM DIA.** A diferença
        entre elas é a janela, e mais nada — dois caminhos de gravação seriam
        duas chances de divergir.
        """
        de = (request.form.get("de") or "").strip()
        ate = (request.form.get("ate") or "").strip()
        try:
            inicio, fim = date.fromisoformat(de), date.fromisoformat(ate)
        except ValueError:
            flash("Informe as duas datas da janela, no formato do calendário.",
                  "danger")
            return redirect(url_for("cnib_central"))
        if inicio > fim:
            flash("A janela começa depois de terminar.", "danger")
            return redirect(url_for("cnib_central"))
        if (fim - inicio).days > MAIOR_JANELA_EM_DIAS:
            flash(f"Janela grande demais para uma ida só (mais de "
                  f"{MAIOR_JANELA_EM_DIAS} dias). A posta em dia anda mês a "
                  f"mês, logo abaixo.", "danger")
            return redirect(url_for("cnib_central"))

        with db.connect() as con:
            pronto = ATZ.esta_pronto(con)
        if not pronto["pronto"]:
            for frase in pronto["falta"]:
                flash(frase, "danger")
            return redirect(url_for("cnib_central"))

        frase, tom = _uma_ida(
            de=de, ate=ate, automatica=False, usuario=usuario_id(),
            registrar=lambda d: audit("CNIB_LEITURA", "CNIB", None, d))
        flash(frase, tom)
        return redirect(url_for("cnib_central"))

    # ------------------------------------------------------------- a fila

    @app.route("/registro-imoveis/cnib/central/fila/autorizacao", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def cnib_fila_autorizacao():
        """Liga ou desliga a leitura da fila. **Só o ADMIN, e com o «ciente».**

        Ligar exige marcar a frase que diz o que acontece: o que vier sai da
        fila da serventia na Central, e não volta. Desligar não exige nada.
        """
        ligar = request.form.get("ligar") == "1"
        if ligar and request.form.get("ciente") != "1":
            flash("Para ligar, marque que está ciente de que a leitura tira "
                  "as ordens da fila da serventia na Central.", "danger")
            return redirect(url_for("cnib_central"))
        db.set_settings({ATZ.CHAVE_DA_FILA: "1" if ligar else "0"})
        audit("CNIB_FILA_AUTORIZACAO", "CNIB", None, {"ligada": ligar})
        flash("Leitura da fila ligada. A rotina diária passa a ler a fila."
              if ligar else "Leitura da fila desligada. A rotina volta a ler "
              "por janela, sem consumir.", "success" if ligar else "info")
        return redirect(url_for("cnib_central"))

    @app.route("/registro-imoveis/cnib/central/fila/ler", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def cnib_fila_ler():
        """Uma rodada da fila agora, em segundo plano. O resultado vai para a lista."""
        with db.connect() as con:
            pronto = ATZ.esta_pronto(con)
            fila = ATZ.fila_autorizada(con)
        if not fila:
            flash("A leitura da fila está desligada.", "danger")
            return redirect(url_for("cnib_central"))
        if not pronto["pronto"]:
            for frase in pronto["falta"]:
                flash(frase, "danger")
            return redirect(url_for("cnib_central"))
        # O PEDIDO VAI NA AUDITORIA AGORA; O RESULTADO, NO REGISTRO DO SISTEMA.
        # A rodada roda numa linha de fundo, sem `request`, e `audit()` lê o
        # usuário logado (ver `_uma_ida`).
        audit("CNIB_FILA_RODADA", "CNIB", None, {"pedida": True})
        _rodada_em_fundo(automatica=False, usuario=usuario_id(),
                         registrar=_registrar_do_sistema)
        flash("A rodada da fila começou em segundo plano. Ela leva alguns "
              "minutos; o resultado aparece em «As últimas leituras».", "info")
        return redirect(url_for("cnib_central"))

    # --------------------------------------------- a consulta por documento

    @app.route("/registro-imoveis/cnib/consulta", methods=["GET", "POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER", "USER")
    def cnib_consulta():
        """O que pesa sobre este CPF ou CNPJ, agora, direto na Central. Só lê.

        Pedido do oficial em 30/10/2026. A outra tela do CNIB consulta a cópia
        local; esta pergunta à Central, com o cliente na frente. O documento vai
        por POST para não ficar no endereço, e cada consulta fica na auditoria.
        """
        with db.connect() as con:
            pronto = ATZ.esta_pronto(con)
            cpf = ATZ.cpf_de_quem_consulta(con)
        documento, resposta, erro, protocolos = "", None, "", []
        if request.method == "POST":
            documento = (request.form.get("documento") or "").strip()
            if CC.documento_valido(documento) is not True:
                flash(CC.mensagem_documento_invalido(documento), "danger")
            elif pronto["pronto"]:
                documento = CC.formatar_documento(documento)
                try:
                    resposta = API.consultar_por_documento(documento, cpf_usuario=cpf)
                except (API.CnibError, CRED.CredencialError) as e:
                    erro = str(e)
                else:
                    protocolos = [
                        API.protocolo_da_ordem(p) if isinstance(p, dict) else str(p)
                        for p in resposta["protocolos"]]
                audit("CNIB_CONSULTA_DOCUMENTO", "CNIB", None, {
                    "documento": documento, "erro": erro[:400],
                    "indisponivel": resposta["indisponivel"] if resposta else None,
                    "respondeu": resposta["respondeu"] if resposta else False})
        return render_template(
            "cnib_consulta.html", pronto=pronto, documento=documento, r=resposta,
            erro=erro, protocolos=protocolos, quando=db.now()[:16].replace("T", " "))

    # ------------------------------------------------- o par que está no acervo

    @app.route("/registro-imoveis/cnib/central/credencial", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def cnib_credencial_do_acervo():
        """Traz o par do CNIB **do acervo do E-Ofício** para o `%PROGRAMDATA%`.

        POR QUE ISTO EXISTE, e não é atalho de preguiça: o par desta serventia
        **não veio de papel nenhum** — ele estava dentro do banco do sistema
        antigo, em `tbCNIB_Propriedades`, duas colunas e uma linha. Sem este
        botão, informá-lo quer dizer abrir um arquivo de 382 MB com ferramenta
        de programador e copiar uma senha à mão, que é exatamente a operação em
        que uma senha vaza para um bloco de notas.

        **O SEGREDO NÃO PASSA PELA TELA E NÃO ENTRA NO BANCO.** Ele é lido do
        acervo e escrito no arquivo do `centrais_cred` no mesmo passo, dentro
        do servidor; o navegador recebe só a frase de que deu certo. E a
        auditoria registra QUE se trouxe, nunca o quê.

        **É SÓ DO ADMIN**, como a própria tela de credenciais.
        """
        caminho = _acervo()
        if not caminho.exists():
            flash("O acervo do E-Ofício não está nesta máquina — não há de "
                  "onde trazer o par. Grave-o em Configurações.", "danger")
            return redirect(url_for("cnib_central"))
        try:
            # o acervo e SQLite de verdade, so leitura, pela porta que nao
            # decide pelo nome do arquivo (LH09)
            con = banco_pg.conectar_sqlite(caminho)
            try:
                linha = con.execute(
                    "SELECT Cliente_ID, Secret_Code FROM tbCNIB_Propriedades "
                    "LIMIT 1").fetchone()
            finally:
                con.close()
        except sqlite3.DatabaseError as erro:
            flash(f"Não deu para ler o acervo: {erro}", "danger")
            return redirect(url_for("cnib_central"))

        if not linha or not (linha[0] or "").strip() or not (linha[1] or "").strip():
            flash("O acervo não tem o par do CNIB guardado.", "danger")
            return redirect(url_for("cnib_central"))

        try:
            CRED.gravar(CRED.CNIB, ambiente=CRED.PRODUCAO,
                        usuario=str(linha[0]).strip(), senha=str(linha[1]).strip())
        except CRED.CredencialError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("cnib_central"))

        # **TROCAR A CREDENCIAL TEM DE JOGAR FORA O TOKEN GUARDADO** — ele dura
        # uma hora, e sem esta linha quem corrigisse o par continuaria falando
        # pelo token velho e concluiria que a correção não pegou. É a mesma
        # armadilha medida no ONR.
        API.esquecer_o_token()
        audit("CENTRAL_CREDENCIAL", "CENTRAIS", None,
              {"central": CRED.CNIB, "ambiente": CRED.PRODUCAO,
               "acao": "trazida_do_acervo"})
        flash("O par do CNIB foi trazido do acervo e guardado fora do banco. "
              "A senha não passou pela tela.", "success")
        return redirect(url_for("cnib_central"))

    # ------------------------------------------------------ o CPF e a rotina

    @app.route("/registro-imoveis/cnib/central/ajustes", methods=["POST"])
    @login_required
    @roles_required("ADMIN", "MANAGER")
    def cnib_ajustes():
        """O CPF de quem consulta e o interruptor da rotina diária.

        O CPF fica em `settings` porque **não é segredo**: é o identificador
        que a Central exige para registrar quem pediu a lista, e ele já está
        no cadastro de gente desta casa. O que não pode entrar no banco é o
        `client_secret` — esse mora no `%PROGRAMDATA%`.
        """
        cpf = "".join(c for c in (request.form.get("cpf") or "") if c.isdigit())
        if cpf and len(cpf) != 11:
            flash("O CPF de quem consulta tem 11 dígitos.", "danger")
            return redirect(url_for("cnib_central"))
        db.set_settings({
            ATZ.CHAVE_DO_CPF: cpf,
            ATZ.CHAVE_DA_ROTINA: "1" if request.form.get("rotina") else "0",
        })
        audit("CNIB_AJUSTES", "CNIB", None,
              {"cpf_informado": bool(cpf),
               "rotina": bool(request.form.get("rotina"))})
        flash("Guardado.", "success")
        return redirect(url_for("cnib_central"))

    # ------------------------------------------------------- a rotina diária

    def atualizacao_do_cnib_uma_vez_por_dia() -> None:
        """A leitura do dia, **na forma do backup automático**.

        Ela imita `automatic_backup_once` de propósito — trava numa marca do
        processo, consulta o interruptor, só faz o que ainda não foi feito
        hoje e **não derruba a tela quando falha**. É o único padrão de
        trabalho diário que esta casa já tem rodando.

        **E ELA NÃO SEGURA A TELA.** O backup é trabalho de disco e demora o
        que demora; esta aqui sai para a rede, com prazo de 60 s por página, e
        prendê-la no `before_request` faria a primeira tela do dia ficar
        girando enquanto a Central responde. Por isso vai numa linha de fundo,
        como a descoberta de rede — e cada linha dessas abre a **sua própria**
        conexão, que é como o `Database` desta casa funciona.

        O QUE ELA NÃO FAZ: a posta em dia. A janela do dia tem uma semana; o
        atraso de 2023 é outro trabalho, deliberado, que anda mês a mês com
        alguém olhando. Rotina que sozinha varresse três anos de fila seria a
        máquina decidindo o tamanho do que pede à Central.

        **COM A FILA AUTORIZADA PELO OFICIAL (23/11/2026)**, ela lê uma rodada
        da fila em vez da janela. A rodada tem teto próprio
        (`cnib_api.MAXIMO_DE_PAGINAS_DA_FILA`), e quem decidiu consumir a fila
        foi gente, na tela.
        """
        hoje = date.today()   # noqa: DTZ011 — relógio da casa
        verificado = app.extensions.get("cnib_verificado")
        if verificado is True or verificado == hoje.isoformat():
            return
        app.extensions["cnib_verificado"] = hoje.isoformat()
        try:
            with db.connect() as con:
                if not ATZ.rotina_ligada(con):
                    return
                if ATZ.ja_leu_hoje(con, hoje=hoje):
                    return
                if not ATZ.esta_pronto(con)["pronto"]:
                    return
                fila = ATZ.fila_autorizada(con) is True
                de, ate = ATZ.janela_do_dia(con, hoje=hoje)
        except Exception:   # noqa: BLE001 — ver abaixo
            # Tela não cai por causa de rotina de fundo. Se o banco não
            # responde, quem tem de gritar é a tela que o usuário abriu.
            return

        # COM A FILA AUTORIZADA, A ROTINA LÊ A FILA, uma rodada por dia, e não
        # a janela. As duas no mesmo dia seriam duas idas para o mesmo fim, e a
        # janela com `True` é justamente a que parou de trazer ordem nova.
        if fila:
            _rodada_em_fundo(automatica=True, usuario=None,
                             registrar=_registrar_do_sistema)
            return

        registrar = _registrar_do_sistema

        def trabalhar():
            try:
                _uma_ida(de=de, ate=ate, automatica=True, usuario=None,
                         registrar=registrar)
            except Exception as erro:  # noqa: BLE001 — ver acima
                try:
                    db.log(None, "SISTEMA", "CNIB_LEITURA_FALHOU", "CNIB",
                           None, {"erro": str(erro)[:400]}, **identidade)
                except Exception:   # noqa: BLE001,S110 — ver acima
                    pass

        threading.Thread(target=trabalhar, name="cnib-atualizador",
                         daemon=True).start()

    app.extensions["cnib_uma_vez_por_dia"] = atualizacao_do_cnib_uma_vez_por_dia
