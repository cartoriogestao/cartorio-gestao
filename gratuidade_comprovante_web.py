"""O aviso insistente do comprovante da gratuidade, e a tela de subir.

Ordem do oficial em 11/10/2026: aviso ao USUÁRIO, não trava no ato. O ato se
pratica; quem obteve o selo isento vê, em TODA tela, a faixa vermelha até
guardar o comprovante. Mora no `base.html` pela razão do aviso do caixa: ligado
tela a tela, a próxima tela nasceria sem ele. O aviso só LÊ (GET não grava).

SELO × CAIXA (LX16, 19/10/2026) mora aqui também: `registrar_rotas_do_selo_e_caixa`.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import date
from pathlib import Path

from flask import abort, flash, g, redirect, render_template, request, session, url_for

import ato_selado as AS
import caixa_depositos as DEP
import caixa_protocolo as CXP
import gratuidade_comprovante as GC
from bd_nativo import banco
from seguranca_web import numero_digitado  # LD13: o número que a tela mandou

QUEM = ("ADMIN", "MANAGER", "USER")
#: Quantos selos pagos sem cobertura a conferência mostra de uma vez.
LIMITE_DOS_PAGOS = 500


def _uma_vez_por_requisicao(chave: str, calcular):
    """As barras do topo, contadas UMA vez por requisição (LX21b).

    O context processor roda a cada `render_template` — a página, o pedaço
    que a rota monta antes, o recado de erro —, e cada volta abria conexão e
    refazia as contas. A requisição é a unidade certa do cache: o POST
    redireciona, então o que a rota gravou chega contado na tela seguinte, e
    nada passa de uma pessoa para outra.
    """
    if chave not in g:
        setattr(g, chave, calcular())
    return getattr(g, chave)


def quantos_a_pagar(con, *, nome, username="") -> int:
    """Quantos selos liberados pelo oficial esta pessoa ainda tem de pagar. Só LÊ.

    É o número de `ato_selado.pagamentos_pendentes`, em consultas que não
    crescem com a casa (LX21b, achado 6 da revisão do LX16): aquela percorre
    TODAS as liberações — três consultas de cobertura e uma de selo por
    liberação — e a barra a chamava em toda tela de todo mundo. Aqui UMA
    consulta traz as liberações com quem obteve o selo; a cobertura só se
    pergunta das liberações DESTA pessoa, que em dia normal são nenhuma, e
    pela régua de `ato_selado.cobertura_de_verdade` — que não se reescreve
    em SQL. O teste de equivalência segura as duas contas juntas.
    """
    bd = banco(con)
    if not bd.tem_tabela("cx_selo_liberacoes"):
        return 0
    # «Quem obteve» é o do primeiro selo vivo do ato e, sem selo, quem usou a
    # liberação — o mesmo `obtido_por` de `liberados_sem_cobertura`.
    liberacoes = bd.ler(
        """SELECT l.id, l.tabela, l.ato_id,
                  CASE WHEN s.id IS NULL THEN l.usado_por ELSE s.obtido_por END
                      AS obtido_por
             FROM cx_selo_liberacoes l
             LEFT JOIN LATERAL (
                  SELECT x.id, x.obtido_por FROM sd_selos x
                   WHERE x.tabela = l.tabela AND x.ato_id = l.ato_id
                     AND x.cancelado_em IS NULL
                   ORDER BY x.id LIMIT 1) s ON TRUE
            ORDER BY l.liberado_em, l.id""")
    alvos = {str(nome or ""), str(username or "")}
    return sum(1 for lib in liberacoes
               if AS._mesma_pessoa(lib["obtido_por"], alvos)
               and not AS.cobertura_de_verdade(bd, lib["tabela"], lib["ato_id"]))


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_id = app.extensions["usuario_id"]
    archive_root = app.extensions["archive_root"]
    current_user = app.extensions["current_user"]

    registrar_rotas_do_selo_e_caixa(app, db, login_required, roles_required, audit)

    def _quem() -> tuple[str, str]:
        u = current_user()
        if not u:
            return "", ""
        return (u["full_name"] or ""), (u["username"] or "")

    def _pasta_proton():
        valor = str(db.get_setting("gratuidade_pasta_proton", "") or "").strip()
        return GC.Path(valor) if valor else GC.pasta_proton_padrao()

    @app.context_processor
    def _gratuidade_aviso() -> dict:
        vazio = {"gratuidade_aviso": 0}
        try:
            onde = request.endpoint or ""
        except RuntimeError:
            return vazio
        if not session.get("user_id") or onde in ("static", "login", "logout"):
            return vazio

        def contar() -> dict:
            try:
                nome, username = _quem()
                with db.connect() as con:
                    # LX16: a barra diz também o selo mais antigo e fica vermelha
                    # depois de N dias — `GC.aviso` faz a conta.
                    barra = GC.aviso(con, nome=nome, username=username,
                                     hoje=str(db.now())[:10])
            except (sqlite3.Error, RuntimeError, KeyError, TypeError):
                return vazio
            return {"gratuidade_aviso": barra["quantos"], "gratuidade_barra": barra}
        return _uma_vez_por_requisicao("_cg_gratuidade_aviso", contar)

    @app.route("/gratuidades/comprovantes")
    @roles_required(*QUEM)
    def gratuidade_comprovantes():
        nome, username = _quem()
        with db.connect() as con:
            lista = GC.pendentes(con, nome=nome, username=username)
            inicio = GC.desde(con)
            feitos = GC.comprovados(con, nome=nome, username=username)  # HOTFIX-2026-10-13-07
        achados = GC.no_proton([p["numero"] for p in lista], _pasta_proton())
        return render_template("gratuidade_comprovantes.html", lista=lista, inicio=inicio, feitos=feitos,
                               achados={k: v.name for k, v in achados.items()},
                               fundamentos=GC.FUNDAMENTOS, o_que_vai=GC.O_QUE_VAI_NO_PDF,
                               por_que=GC.POR_QUE)

    def _voltar():
        return redirect(url_for("gratuidade_comprovantes"))

    def _certidoes_guardadas(con, selo_id: int) -> list[dict]:
        """A certidão do ato que o sistema já guardou para este selo (LG07)."""
        import selo_portal as SP
        if not banco(con).tem_tabela("sd_gratuidade_pecas"):
            return []
        return [p for p in SP.pecas(con, selo_id)
                if p["peca"] == SP.CERTIDAO and Path(p["stored_path"] or "").is_file()]

    @app.route("/gratuidades/comprovantes/<int:selo_id>", methods=["POST"])
    @roles_required(*QUEM)
    def gratuidade_comprovante_subir(selo_id: int):
        # HOTFIX-2026-10-13-07: varios arquivos de uma vez; nunca apaga os que ja ha.
        arquivos = [a for a in request.files.getlist("arquivo") if a and a.filename]
        if not arquivos:
            flash("Escolha o arquivo do comprovante.", "danger")
            return _voltar()
        # LX16: o fundamento vem da lista (`GC.FUNDAMENTOS`); «juntar» faz UM
        # PDF com o que a pessoa mandou e a certidão do ato que o sistema já
        # guardou para este selo (a peça CERTIDÃO do Portal, LG07).
        fundamento = request.form.get("fundamento") or None
        ids = []
        try:
            with db.transaction() as con:
                if request.form.get("juntar"):
                    certidoes = [(Path(p["stored_path"]).name, Path(p["stored_path"]).read_bytes())
                                 for p in _certidoes_guardadas(con, selo_id)]
                    ids.append(GC.guardar_junto(
                        con, selo_id,
                        arquivos=[(a.filename, a.read()) for a in arquivos] + certidoes,
                        pasta=archive_root() / "gratuidades", usuario_id=usuario_id(),
                        agora=db.now(), fundamento=fundamento))
                else:
                    for arquivo in arquivos:
                        ids.append(GC.guardar(con, selo_id, nome_arquivo=arquivo.filename,
                                              conteudo=arquivo.read(),
                                              pasta=archive_root() / "gratuidades",
                                              usuario_id=usuario_id(), agora=db.now(),
                                              fundamento=fundamento))
        except GC.ComprovanteError as erro:
            flash(f"{erro} Nenhum arquivo deste envio foi guardado.", "danger")
            return _voltar()
        audit("GRATUIDADE_COMPROVANTE_GUARDADO", "sd_selos", selo_id, {"anexos": ids})
        flash(f"{len(ids)} comprovante(s) guardado(s).", "ok")
        return _voltar()

    @app.route("/gratuidades/comprovantes/<int:selo_id>/proton", methods=["POST"])
    @roles_required(*QUEM)
    def gratuidade_comprovante_do_proton(selo_id: int):
        """Traz o arquivo do Proton cujo nome tem o código deste selo."""
        with db.connect() as con:
            row = banco(con).um("SELECT numero FROM sd_selos WHERE id=%s", (selo_id,))
        achado = (GC.no_proton([row["numero"]], _pasta_proton()).get(row["numero"].upper())
                  if row else None)
        if not achado:
            flash("Não achei no Proton um arquivo com o código deste selo no nome.", "danger")
            return _voltar()
        try:
            with db.transaction() as con:
                aid = GC.guardar(con, selo_id, nome_arquivo=achado.name,
                                 conteudo=achado.read_bytes(),
                                 pasta=archive_root() / "gratuidades", usuario_id=usuario_id(),
                                 agora=db.now(), origem="Proton")
        except GC.ComprovanteError as erro:
            flash(str(erro), "danger")
            return _voltar()
        audit("GRATUIDADE_COMPROVANTE_GUARDADO", "sd_selos", selo_id,
              {"anexo": aid, "origem": "Proton", "arquivo": achado.name})
        flash(f"Comprovante trazido do Proton ({achado.name}).", "ok")
        return _voltar()


def registrar_rotas_do_selo_e_caixa(app, db, login_required, roles_required, audit):
    """SELO × CAIXA (LX16) — o quadro «Para selar este ato falta», as ações
    que resolvem cada falta, a conferência do gestor e as barras de topo.

    A REGRA MORA EM `ato_selado` (`cobrir_o_selo`, chamada por `obter_selo`):
    aqui só se mostra o que falta e se resolve cada falta no próprio lugar.
    «Registrar pagamento» e «Abrir protocolo» levam à tela do caixa, que é
    onde o dinheiro entra — uma segunda tela de receber seria uma segunda
    conta. A válvula e o interruptor são do ADMIN: guarda na rota e, de
    novo, no domínio. Mora ao lado do comprovante da gratuidade porque é a
    mesma cobrança do selo, e porque um `*_web.py` a mais seria mais uma
    peça que o `app.py` precisa lembrar de chamar.
    """
    usuario_nome = app.extensions["usuario_nome"]
    usuario_papel = app.extensions["usuario_papel"]
    usuario_id = app.extensions["usuario_id"]
    current_user = app.extensions["current_user"]

    def agora() -> str:
        return db.now()

    # O PROTOCOLO PAGO ESCOLHIDO EM QUALQUER TELA (22/10/2026, ordem do
    # oficial: «todas as atribuições que selam»). Toda tela que põe a macro
    # `_protocolo_do_selo.html` dentro do formulário do ato manda o campo
    # `protocolo_selo`; aqui ele vira o «em atendimento» ANTES de a rota rodar,
    # e a cobertura do selo (`cobrir_o_selo`, passo 3) o acha. Assim nenhuma
    # rota de atribuição precisou mudar. As que já tratam o campo por conta
    # própria (Notas e RI, do HOTFIX_SELO_PROTOCOLO) ficam de fora, para a
    # auditoria não sair em dobro — e um teste confere a lista.
    JA_ESCOLHEM_O_PROTOCOLO = frozenset({
        "notas_reconhecimento", "notas_reconhecimento_selar",
        "ri_protocolo", "ri_selar_abertura", "ri_selar_prenotacao",
        "ri_selar_arquivamento", "ri_emitir_certidao_negativa",
        "ri_certidao_selar", "ri_emitir_certidao"})
    app.extensions["ja_escolhem_o_protocolo"] = JA_ESCOLHEM_O_PROTOCOLO

    @app.before_request
    def _protocolo_do_selo_escolhido():
        if request.method != "POST" or not session.get("user_id"):
            return None
        escolhido = (request.form.get("protocolo_selo") or "").strip()
        # O protocolo do quadro de cobrança (`_cobrar.html`) também vale: ele
        # já é a escolha do escrevente, e a marca garante que é um protocolo
        # do CAIXA — `protocolo_id` noutras telas pode ser a prenotação do RI.
        if not escolhido and request.form.get("protocolo_do_quadro"):
            escolhido = (request.form.get("protocolo_id") or "").strip()
        if not escolhido or request.endpoint in JA_ESCOLHEM_O_PROTOCOLO:
            return None
        try:
            with db.transaction() as con:
                feito = AS.escolher_protocolo_do_selo(
                    con, usuario=usuario_nome(), protocolo=escolhido, agora=agora())
        except CXP.ProtocoloError as erro:
            # Não barra o ato: sem o atendimento, a cobertura diz o que falta.
            flash(str(erro), "warning")
            return None
        if feito:
            audit("SELO_PROTOCOLO_EM_ATENDIMENTO", "CX_PROTOCOLO", feito["protocolo_id"],
                  {"numero": feito["numero"], "pela": request.endpoint or ""})
        return None

    def _seletor_do_selo(tabela, pedidos=None) -> dict:
        """Global de Jinja: o que a macro do protocolo pago precisa. Só LÊ."""
        try:
            with db.connect() as con:
                return AS.seletor_do_ato(con, tabela=tabela, usuario=usuario_nome(),
                                         pedidos=pedidos)
        except Exception:                                  # noqa: BLE001
            # A tela do ato não cai por causa da lista: sem ela, o escrevente
            # ainda pode atender pelo «Selo e caixa».
            logging.getLogger(__name__).exception("seletor do selo")
            return {"candidatos": [], "pedidos": pedidos or [], "atendendo": None}

    app.jinja_env.globals["seletor_do_selo"] = _seletor_do_selo

    @app.context_processor
    def _selo_barras() -> dict:
        vazio = {"selo_trava_barra": None, "selo_pagar_aviso": 0}
        try:
            onde = request.endpoint or ""
        except RuntimeError:
            return vazio
        if not session.get("user_id") or onde in ("static", "login", "logout"):
            return vazio

        def contar() -> dict:
            # O erro do PostgreSQL chega aqui como `sqlite3.Error`: o
            # `bd_nativo` o traduz (`banco_pg._traduzir_erro`), e a página
            # não cai por causa da barra.
            try:
                u = current_user()
                with db.connect() as con:
                    barra = AS.barra_da_trava(con)
                    pagar = quantos_a_pagar(
                        con, nome=(u["full_name"] if u else ""),
                        username=(u["username"] if u else ""))
            except (sqlite3.Error, RuntimeError, KeyError, TypeError):
                return vazio
            return {"selo_trava_barra": barra, "selo_pagar_aviso": pagar}
        return _uma_vez_por_requisicao("_cg_selo_barras", contar)

    def _ato_do_pedido() -> tuple[str | None, int | None]:
        tabela = (request.values.get("tabela") or "").strip()
        bruto = (request.values.get("ato_id") or "").strip()
        if tabela and tabela not in AS.TABELAS_DE_ATO:
            abort(404)
        return (tabela or None), numero_digitado(bruto)

    def _item_do_pedido() -> int:
        """O `item_id` do formulário. Texto que não é número é 400, e não 500.

        Também o «²» e o número de 5.000 dígitos, que passavam pelo
        `isdigit()` e caíam no `int()` (LD13)."""
        item_id = numero_digitado(request.form.get("item_id"))
        if not item_id:
            abort(400)
        return item_id

    def _recusa_do_item(con, item_id: int, tabela, ato_id) -> str | None:
        """Este escrevente pode mexer neste item, para este ato? None = pode.

        A REVISÃO DO LX16 ACHOU AS AÇÕES ABERTAS (LX20): `item_id`, `tabela` e
        `ato_id` vinham livres do formulário, e qualquer USER pagava com
        depósito, diferia ou gastava unidade de item de qualquer protocolo —
        até encerrado — e amarrava depósito a ato que nem existe. Aqui vale o
        que a tela oferece: item do protocolo que ESTE escrevente está
        atendendo, ou item já ligado a este ato; protocolo aberto; ato que
        existe. Lê dentro da transação da ação, mas não prende o protocolo:
        o selo prende item e depois protocolo, e prender na ordem inversa
        abriria o deadlock.
        """
        if (tabela is None) != (ato_id is None):
            return "Diga o ato inteiro (tabela e número), ou nenhum."
        bd = banco(con)
        if tabela is not None and not (bd.tem_tabela(tabela) and bd.um(
                f"SELECT id FROM {tabela} WHERE id = %s", (int(ato_id),))):
            return "Não achei este ato."
        item = CXP.item_do_protocolo(con, item_id)
        if not item:
            return "Não achei este item do protocolo."
        if CXP.esta_encerrado(item["protocolo_situacao"]):
            return (f"O protocolo {item['protocolo_numero']} já foi encerrado "
                    f"({item['protocolo_situacao']}): o item dele não se usa mais.")
        atendendo = CXP.em_atendimento(con, usuario_nome())
        if atendendo and int(atendendo["id"]) == int(item["protocolo_id"]):
            return None
        if tabela is not None and any(
                int(i["id"]) == item_id for i in CXP.itens_do_ato(con, tabela, ato_id)):
            return None
        return ("Este item não é do protocolo que você está atendendo. Marque o "
                "protocolo em «Protocolo que estou atendendo» e tente de novo.")

    def _protocolo_ainda_aberto(con, item_id: int) -> None:
        """Confere DE NOVO, com o protocolo preso, que ele não foi encerrado.

        `_recusa_do_item` lê a situação sem prender (LX20), e entre essa
        leitura e a gravação outro balcão podia encerrar o protocolo: o
        depósito ficava debitado, o item quitado ou a unidade gasta num
        protocolo CANCELADO — o que o próprio `encerrar` recusa (dinheiro que
        entrou não se esconde). Por isso, DEPOIS da ação e dentro da mesma
        transação, o protocolo é preso e relido; encerrado, a ação inteira
        volta (LX21b, achado 4 da revisão do LX16).

        Prende no fim, e não no começo, pela ordem das travas: o selo e o
        depósito prendem item, depósito e só então o protocolo
        (`caixa_depositos.pagar_item` → `atualizar_situacao`). Prender o
        protocolo antes do depósito inverteria a ordem e abriria o deadlock
        entre dois balcões do mesmo protocolo.
        """
        bd = banco(con)
        bd._escrita()
        p = bd.um("""SELECT p.numero, p.situacao FROM cx_protocolos p
                      WHERE p.id = (SELECT i.protocolo_id FROM cx_protocolo_atos i
                                     WHERE i.id = %s)
                        FOR UPDATE""", (int(item_id),))
        if p and CXP.esta_encerrado(p["situacao"]):
            raise CXP.ProtocoloError(
                f"O protocolo {p['numero']} foi encerrado ({p['situacao']}) "
                f"enquanto você usava o item dele. Nada foi gravado.")

    def _voltar(tabela, ato_id):
        if tabela and ato_id is not None:
            return redirect(url_for("selo_cobertura", tabela=tabela, ato_id=ato_id))
        return redirect(url_for("selo_cobertura"))

    @app.route("/selo/cobertura")
    @login_required
    def selo_cobertura():
        tabela, ato_id = _ato_do_pedido()
        with db.connect() as con:
            quadro = AS.quadro_para_selar(con, tabela=tabela, ato_id=ato_id,
                                          usuario=usuario_nome())
            atendendo = CXP.em_atendimento(con, usuario_nome())
            ligados = (CXP.itens_do_ato(con, tabela, ato_id)
                       if tabela and ato_id is not None else [])
            disponiveis = (CXP.itens_disponiveis(con, atendendo["id"])
                           if atendendo else [])
            saldo = (DEP.saldo_do_protocolo(con, atendendo["id"], tabela=tabela,
                                            ato_id=ato_id) if atendendo else 0)
            aguardando = AS.aguardando_cobertura(con, limite=50)
            # OS CANDIDATOS DA TELA QUE MANDOU PARA CÁ (22/10/2026): a tela do
            # ato monta o link com `pedido=código:quantidade` (um por selo) e
            # `selar=<rota que sela de novo>`. Com eles o quadro mostra os
            # protocolos pagos e o botão «Atender este protocolo e selar de
            # novo», que posta direto na tela do ato.
            pedidos = []
            for bruto in request.args.getlist("pedido"):
                codigo, _, qtd = str(bruto).partition(":")
                if codigo.strip():
                    pedidos.append((codigo.strip(), qtd.strip() or 1))
            pedidos = CXP.pedidos_do_selo(pedidos)
            candidatos = (AS.candidatos_do_ato(
                con, tabela=tabela, pedidos=pedidos,
                pre_marcar_protocolo_id=(atendendo or {}).get("id"))
                if pedidos else [])
        selar = str(request.args.get("selar") or "").strip()
        # Só caminho DESTA casa: «/algo», nunca «//outro-site» nem endereço.
        url_de_selar = selar if selar.startswith("/") and not selar.startswith("//") else None
        return render_template(
            "selo_cobertura.html", quadro=quadro, tabela=tabela, ato_id=ato_id,
            rotulo=AS.TABELAS_DE_ATO.get(tabela or "", ""), atendendo=atendendo,
            ligados=ligados, disponiveis=disponiveis, saldo=saldo,
            aguardando=aguardando, pode_diferir=tabela in CXP.TABELAS_QUE_DIFEREM,
            pedidos=pedidos, candidatos=candidatos, url_de_selar=url_de_selar,
            eh_admin=usuario_papel() == AS.PAPEL_QUE_LIBERA,
            o_que_vai=AS.O_QUE_VAI_NO_PDF, reais=DEP.reais)

    @app.route("/selo/cobertura/atender", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def selo_cobertura_atender():
        tabela, ato_id = _ato_do_pedido()
        try:
            with db.transaction() as con:
                if request.form.get("encerrar"):
                    CXP.encerrar_atendimento(con, usuario_nome())
                    feito = None
                else:
                    feito = CXP.atender(con, usuario=usuario_nome(),
                                        protocolo=request.form.get("protocolo"),
                                        agora=agora())
        except CXP.ProtocoloError as erro:
            flash(str(erro), "danger")
            return _voltar(tabela, ato_id)
        if feito:
            audit("SELO_PROTOCOLO_EM_ATENDIMENTO", "CX_PROTOCOLO", feito["protocolo_id"],
                  {"numero": feito["numero"]})
            flash(f"Você está atendendo o protocolo {feito['numero']}. Os selos "
                  f"pagos que você tirar procuram o item ali.", "success")
        else:
            flash("Atendimento encerrado.", "success")
        return _voltar(tabela, ato_id)

    @app.route("/selo/cobertura/vincular", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def selo_cobertura_vincular():
        tabela, ato_id = _ato_do_pedido()
        item_id = _item_do_pedido()
        if not tabela or ato_id is None:
            abort(400)
        try:
            with db.transaction() as con:
                recusa = _recusa_do_item(con, item_id, tabela, ato_id)
                if recusa:
                    raise CXP.ProtocoloError(recusa)
                gastou = CXP.consumir_item(
                    con, item_id, ato_id=ato_id, tabela=tabela, agora=agora(),
                    origem=CXP.ORIGEM_QUADRO, quem=usuario_nome())
                _protocolo_ainda_aberto(con, item_id)
        except CXP.ProtocoloError as erro:
            flash(str(erro), "danger")
            return _voltar(tabela, ato_id)
        if gastou:
            audit("SELO_ATO_LIGADO_AO_ITEM", "CX_PROTOCOLO_ATO", item_id,
                  {"tabela": tabela, "ato_id": ato_id})
            flash("O ato foi ligado ao item do protocolo.", "success")
        else:
            flash("Este item já foi todo usado. Escolha outro ou acrescente o "
                  "item no protocolo, no caixa.", "danger")
        return _voltar(tabela, ato_id)

    @app.route("/selo/cobertura/deposito", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def selo_cobertura_deposito():
        tabela, ato_id = _ato_do_pedido()
        item_id = _item_do_pedido()
        try:
            with db.transaction() as con:
                recusa = _recusa_do_item(con, item_id, tabela, ato_id)
                if recusa:
                    raise CXP.ProtocoloError(recusa)
                feito = DEP.pagar_item(
                    con, item_id, agora=agora(), quem=usuario_nome(),
                    tabela=tabela, ato_id=ato_id)
                _protocolo_ainda_aberto(con, item_id)
        except CXP.ProtocoloError as erro:
            flash(str(erro), "danger")
            return _voltar(tabela, ato_id)
        if feito and feito.get("ja_quitado"):
            flash("Este item já estava pago.", "success")
        elif feito:
            audit("DEPOSITO_PREVIO_PAGOU_ITEM", "DEPOSITO", feito["deposito_id"],
                  {"item_id": item_id, "valor": DEP.reais(feito["valor_centavos"])})
            flash(f"Item pago com o depósito {feito['numero']}: R$ "
                  f"{DEP.reais(feito['valor_centavos'])}. Saldo que sobrou: R$ "
                  f"{DEP.reais(feito['saldo_centavos'])}.", "success")
        else:
            flash("O depósito prévio deste protocolo não cobre o item. Registre "
                  "o pagamento da diferença no caixa.", "danger")
        return _voltar(tabela, ato_id)

    @app.route("/selo/cobertura/diferir", methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def selo_cobertura_diferir():
        tabela, ato_id = _ato_do_pedido()
        item_id = _item_do_pedido()
        try:
            with db.transaction() as con:
                recusa = _recusa_do_item(con, item_id, tabela, ato_id)
                if recusa:
                    raise CXP.ProtocoloError(recusa)
                feito = CXP.registrar_diferimento(
                    con, item_id, quem_paga=request.form.get("quem_paga"),
                    quando=request.form.get("quando"),
                    motivo=request.form.get("motivo"), por=usuario_nome(),
                    agora=agora())
                _protocolo_ainda_aberto(con, item_id)
        except CXP.ProtocoloError as erro:
            flash(str(erro), "danger")
            return _voltar(tabela, ato_id)
        audit("SELO_EMOLUMENTO_DIFERIDO", "CX_PROTOCOLO_ATO", item_id, feito)
        flash(f"Diferimento registrado: paga {feito['quem']} até {feito['quando']}.",
              "success")
        return _voltar(tabela, ato_id)

    @app.route("/selo/cobertura/liberar", methods=["POST"])
    @roles_required("ADMIN")
    def selo_cobertura_liberar():
        tabela, ato_id = _ato_do_pedido()
        if not tabela or ato_id is None:
            abort(400)
        try:
            with db.transaction() as con:
                AS.liberar_selo(con, tabela=tabela, ato_id=ato_id,
                                justificativa=request.form.get("justificativa"),
                                papel=usuario_papel(), usuario=usuario_nome(),
                                usuario_id=usuario_id(), agora=agora())
        except AS.AtoError as erro:
            flash(str(erro), "danger")
            return _voltar(tabela, ato_id)
        flash("Selo liberado. O pagamento continua pendente para quem obtiver o "
              "selo, e o ato aparece na lista «selos liberados sem cobertura».",
              "warning")
        return _voltar(tabela, ato_id)

    @app.route("/selo/conferencia", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER")
    def selo_conferencia():
        if request.method == "POST":
            acao = request.form.get("acao")
            try:
                with db.transaction() as con:
                    if acao in ("ligar", "desligar"):
                        AS.ligar_trava(con, ligada=(acao == "ligar"),
                                       papel=usuario_papel(), usuario=usuario_nome(),
                                       usuario_id=usuario_id(),
                                       justificativa=request.form.get("justificativa"),
                                       agora=agora())
                    elif acao == "desde" and usuario_papel() == "ADMIN":
                        desde = str(request.form.get("desde") or "").strip()[:10]
                        try:
                            date.fromisoformat(desde)
                        except ValueError:
                            raise AS.AtoError("Escolha uma data válida.") from None
                        banco(con).escrever(
                            """INSERT INTO settings (key, value) VALUES (%s, %s)
                               ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
                            (AS.CHAVE_DESDE_DA_CONFERENCIA, desde))
                    else:
                        abort(403)
            except AS.AtoError as erro:
                flash(str(erro), "danger")
            else:
                flash("Feito.", "success")
            return redirect(url_for("selo_conferencia"))
        # O relógio da casa (`db.now`), e não o do sistema: é o mesmo da
        # barra do topo, e o teste o fixa.
        hoje = str(agora())[:10]
        with db.connect() as con:
            dados = {
                "trava_ligada": AS.trava_ligada(con),
                "liberados": AS.liberados_sem_cobertura(con),
                "gratuitos": GC.sem_comprovante_por_escrevente(con, hoje=hoje),
                "prazo": GC.dias_para_ficar_vermelho(con),
                "aguardando": AS.aguardando_cobertura(con),
                "desde": AS.desde_da_conferencia(con),
            }
            # Um a mais que o limite: é assim que a tela sabe que ficou
            # selo sem cobertura de fora, e diz.
            pagos = AS.selos_pagos_sem_cobertura(con, dados["desde"],
                                                 limite=LIMITE_DOS_PAGOS + 1)
            dados["pagos_sem_cobertura"] = pagos[:LIMITE_DOS_PAGOS]
            dados["pagos_cortados"] = len(pagos) > LIMITE_DOS_PAGOS
            dados["pagos_limite"] = LIMITE_DOS_PAGOS
        return render_template("selo_conferencia.html",
                               eh_admin=usuario_papel() == "ADMIN", **dados)
