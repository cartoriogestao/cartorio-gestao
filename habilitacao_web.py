"""As telas da habilitação de casamento.

A TELA NÃO REPETE A REGRA DO DOMÍNIO. Ela só *oferece* o que cabe na situação —
quem *recusa* é `habilitacao.py`, e há teste que manda o ato fora de ordem
direto para a função. Repetir a regra nos dois lugares é como os dois divergem:
a tela esconde o botão por educação, o domínio recusa por dever.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from flask import Response, abort, flash, redirect, render_template, request, url_for

import ato_selado as AS
import habilitacao as HAB
import hc_schema as HC
from pathlib import Path

from ri_odt import carimbo_compacto_odf, gerar_odt, html_para_odf


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """Pendura as telas da habilitação no app já construído."""

    usuario_nome = app.extensions["usuario_nome"]
    usuario_funcao = app.extensions["usuario_funcao"]

    def agora() -> str:
        return db.now()

    def hoje() -> str:
        return date.today().isoformat()

    def _campo(nome: str) -> str:
        return (request.form.get(nome) or "").strip()

    def _motivo_da_falha_do_selo(recado: str) -> str | None:
        """Extrai o motivo que impediu a expedição. Só LÊ."""
        texto = str(recado or "").strip()
        if not texto:
            return None
        if not AS.suspende_o_ato(recado):
            return None
        if "SEM SELO:" in texto:
            return texto.split("SEM SELO:", 1)[1].strip() or "falha sem detalhe"
        baixo = texto.lower()
        if "sem selo:" in baixo:
            return texto.split(":", 1)[1].strip() or "falha sem detalhe"
        if "sem selo" in baixo:
            return texto or "falha sem detalhe"
        return None

    def _valor(linha, nome: str):
        """Uma coluna da linha, ou None se ela ainda não existe no banco.

        COLUNA DE MIGRAÇÃO PODE NÃO ESTAR LÁ, e um `sqlite3.Row` estoura com
        `IndexError` quando o nome não existe — o que viraria HTTP 500 no
        momento mais caro, logo depois de a habilitação ser expedida. Aqui vale
        a mesma regra do selo: nunca derrubar ato que já existe.
        """
        try:
            return linha[nome]
        except (IndexError, KeyError):
            return None

    def _sv():
        from serventia import dados as dados_serventia
        return dados_serventia(db.get_settings)

    # ------------------------------------------------------------ a lista

    @app.route("/rcpn/habilitacoes")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def rcpn_habilitacoes():
        """As habilitações em curso, e as que terminaram."""
        situacao = (request.args.get("situacao") or "").strip().upper()
        busca = (request.args.get("busca") or "").strip()
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            linhas = HAB.listar(con, situacao=situacao or None,
                                busca=busca or None)
            # O QUE FAZER AGORA, JÁ NA LISTA — num rito de semanas, a pergunta
            # não é «quais existem», é «qual delas espera por mim».
            for h in linhas:
                h["passos"] = HAB.proximos_passos(con, h["id"], hoje())
            resumo = {s: con.execute(
                "SELECT COUNT(*) n FROM hc_habilitacoes WHERE situacao=?",
                (s,)).fetchone()["n"] for s in HC.SITUACOES}
        return render_template("rcpn_habilitacoes.html", linhas=linhas,
                               resumo=resumo, situacao=situacao, busca=busca,
                               SITUACOES=HC.SITUACOES, TIPOS=HC.TIPOS,
                               REGIMES=HC.REGIMES,
                               PRAZO_EDITAL=HC.PRAZO_DO_EDITAL)

    # ------------------------------------------------------------- abrir

    @app.route("/rcpn/habilitacoes/nova", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_habilitacao_nova():
        if request.method == "POST":
            dados = {k: v for k, v in request.form.items()
                     if k != "csrf_token"}
            try:
                with db.transaction() as con:
                    novo = HAB.abrir(con, dados, agora=agora(),
                                     usuario=usuario_nome())
            except HAB.HabilitacaoError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("rcpn_habilitacao_nova"))
            audit("HC_ABERTA", "HC_HABILITACAO", novo,
                  {"nubentes": f"{dados.get('nubente1_nome')} e "
                               f"{dados.get('nubente2_nome')}"})
            # OS ANEXOS DA LEITURA ACOMPANHAM A HABILITAÇÃO (12/10/2026).
            if str(dados.get("leitura_id") or "").isdigit():
                import rc_leitura_documentos as LEIT
                with db.transaction() as con:
                    LEIT.ligar_documentos(con, int(dados["leitura_id"]), "HC_HABILITACAO", int(novo),
                                          agora=agora(), por_id=app.extensions["usuario_id"]())
            flash("Habilitação aberta. O checklist do art. 1.525 do Código "
                  "Civil já está montado — receba os documentos e publique o "
                  "edital.", "success")
            return redirect(url_for("rcpn_habilitacao",
                                    habilitacao_id=novo))
        # O RASCUNHO REABRE AQUI (12/10/2026). A tela SALVAVA rascunho desde
        # 07/09 e não sabia reabri-lo — a lista de rascunhos levava a uma tela
        # em branco. E é por aqui que chega a leitura dos documentos do
        # casamento. Só no GET, como na tela do assento.
        import rascunho_de_tela as RASC
        v: dict = {}
        rascunho_id = request.args.get("rascunho_id", type=int)
        if rascunho_id:
            with db.connect() as con:
                try:
                    r = RASC.ler(con, rascunho_id)
                except RASC.RascunhoError as erro:
                    flash(str(erro), "danger")
                    r = None
            if r and r["tela"] != "rcpn_habilitacao_nova":
                flash("Este rascunho não é de uma habilitação.", "danger")
                r = None
            if r:
                v = r.get("dados") or {}
            else:
                rascunho_id = None
        leitura_origem = None
        if rascunho_id:
            import rc_leitura_documentos as LEIT
            with db.connect() as con:
                leitura_origem = LEIT.leitura_do_rascunho(con, rascunho_id)
        return render_template("rcpn_habilitacao_nova.html",
                               TIPOS=HC.TIPOS, REGIMES=HC.REGIMES,
                               hoje=hoje(), v=v, rascunho_id=rascunho_id,
                               leitura_origem=leitura_origem)

    # -------------------------------------------------------------- ficha

    @app.route("/rcpn/habilitacoes/<int:habilitacao_id>", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def rcpn_habilitacao(habilitacao_id):
        if request.method == "POST":
            acao = _campo("acao")
            try:
                with db.transaction() as con:
                    con.row_factory = sqlite3.Row
                    recado = _fazer(con, habilitacao_id, acao)
            except HAB.HabilitacaoError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("rcpn_habilitacao",
                                        habilitacao_id=habilitacao_id))
            # O SELO É PEDIDO FORA DA TRANSAÇÃO DO ATO, e por isso aqui:
            # a chamada ao aparelho tem prazo de vinte segundos, e segurar o
            # `BEGIN IMMEDIATE` da casa por vinte segundos poria todo outro
            # balcão no `busy_timeout`. É a regra de sempre.
            sem_selo = False
            if "{selo}" in recado:
                recado_selo = _selar_a_habilitacao(habilitacao_id)
                sem_selo = isinstance(recado_selo, AS.RecadoDoSelo)
                if sem_selo:
                    motivo = (_motivo_da_falha_do_selo(recado_selo)
                              or str(recado_selo).strip()
                              or "falha sem detalhe")
                    with db.transaction() as con:
                        HAB.cancelar_expedicao_sem_selo(
                            con, habilitacao_id, agora=agora(),
                            usuario=usuario_nome(), motivo=motivo)
                    audit("HC_HABILITACAO_NAO_EXPEDIDA_SELO_FALHOU",
                          "HC_HABILITACAO", habilitacao_id,
                          {"acao": acao, "motivo": motivo})
                    flash(
                        "Habilitação NÃO expedida: o selo não foi emitido. "
                        f"Motivo: {motivo} Corrija o problema e use "
                        "Habilitar novamente; documentos, edital e prazo "
                        "foram preservados.", "danger")
                    return redirect(url_for(
                        "rcpn_habilitacao", habilitacao_id=habilitacao_id))
                recado = recado.replace("{selo}", recado_selo)
            audit(f"HC_{acao.upper()}", "HC_HABILITACAO", habilitacao_id,
                  {"acao": acao})
            flash(recado, "warning" if sem_selo else "success")
            return redirect(url_for("rcpn_habilitacao",
                                    habilitacao_id=habilitacao_id))

        with db.connect() as con:
            con.row_factory = sqlite3.Row
            h = con.execute("SELECT * FROM hc_habilitacoes WHERE id=?",
                            (habilitacao_id,)).fetchone()
            if not h:
                abort(404)
            h = dict(h)
            documentos = HAB.documentos_de(con, habilitacao_id)
            andamento = HAB.andamento_de(con, habilitacao_id)
            passos = HAB.proximos_passos(con, habilitacao_id, hoje())
            falta = HAB.o_que_falta(con, habilitacao_id)
            prazo_venceu = HAB.prazo_vencido(h, hoje())
            vencida = HAB.habilitacao_vencida(h, hoje())
            casamentos = HAB.casamentos_da_habilitacao(con, habilitacao_id)
        anexos_leitura = [dict(r) for r in db.get_attachments("HC_HABILITACAO", habilitacao_id)]
        return render_template(
            "rcpn_habilitacao.html", h=h, documentos=documentos,
            andamento=andamento, passos=passos, falta=falta,
            prazo_venceu=prazo_venceu, vencida=vencida,
            SITUACOES=HC.SITUACOES, TIPOS=HC.TIPOS, REGIMES=HC.REGIMES,
            PRAZO=HC.PRAZO_DO_EDITAL, VALIDADE=HC.VALIDADE_DA_HABILITACAO,
            ONDE_SE_PUBLICA=HC.ONDE_SE_PUBLICA,
            AVISO_REVISAO_JURIDICA=HC.AVISO_REVISAO_JURIDICA_HC,
            uniao_estavel=_valor(h, "uniao_estavel_processo"),
            modelo_edital=_modelo_do_edital(h), casamentos=casamentos,
            anexos_leitura=anexos_leitura)

    def _fazer(con: sqlite3.Connection, habilitacao_id: int, acao: str) -> str:
        """Cada botão da ficha. ESCREVE, dentro da transação de quem chama."""
        if acao == "documento":
            HAB.marcar_documento(
                con, int(_campo("documento_id")),
                apresentado=_campo("apresentado") == "1",
                agora=agora(), usuario=usuario_nome())
            return "Documento anotado."
        if acao == "dispensar":
            HAB.dispensar_documento(
                con, int(_campo("documento_id")), motivo=_campo("motivo"),
                agora=agora(), usuario=usuario_nome())
            return "Documento dispensado, com o motivo registrado."
        if acao == "edital":
            r = HAB.publicar_edital(
                con, habilitacao_id, teor=_campo("teor"), agora=agora(),
                hoje=hoje(), usuario=usuario_nome())
            return (f"Edital publicado. O prazo de {HC.PRAZO_DO_EDITAL} dias "
                    f"vai até {r['prazo_ate']}.")
        if acao == "uniao_estavel":
            HAB.registrar_uniao_estavel(
                con, habilitacao_id, processo=_campo("processo"),
                agora=agora(), usuario=usuario_nome())
            return "União estável anotada."
        if acao == "eproclamas":
            HAB.registrar_publicacao(
                con, habilitacao_id, protocolo=_campo("protocolo"),
                agora=agora(), usuario=usuario_nome())
            return "Publicação no e-Proclamas anotada, com o protocolo."
        if acao == "oposicao":
            HAB.registrar_oposicao(
                con, habilitacao_id, quem=_campo("quem"), teor=_campo("teor"),
                agora=agora(), usuario=usuario_nome())
            return ("Impedimento registrado. O processo fica parado até a sua "
                    "decisão.")
        if acao == "decidir":
            HAB.decidir_oposicao(
                con, habilitacao_id, decisao=_campo("decisao"),
                fundamento=_campo("fundamento"), agora=agora(),
                usuario=usuario_nome())
            return "Decisão registrada, com o fundamento."
        if acao == "habilitar":
            r = HAB.habilitar(
                con, habilitacao_id, agora=agora(), hoje=hoje(),
                usuario=usuario_nome(), teor=_campo("teor") or None)
            # O SELO SAI DEPOIS, FORA DESTA TRANSAÇÃO — quem chama guarda o
            # pedido para o fim. Ver `_selar_a_habilitacao`.
            return (f"Habilitação {r['numero']}/{r['ano']} expedida. Vale até "
                    f"{r['vale_ate']} — noventa dias, CC art. 1.532."
                    f"{{selo}}")
        if acao == "celebrado":
            HAB.registrar_celebracao(
                con, habilitacao_id, assento_id=int(_campo("assento_id") or 0),
                agora=agora(), hoje=hoje(), usuario=usuario_nome())
            return "Casamento amarrado à habilitação."
        if acao == "arquivar":
            HAB.arquivar(con, habilitacao_id, motivo=_campo("motivo"),
                         agora=agora(), usuario=usuario_nome())
            return "Processo arquivado, com o motivo registrado."
        raise HAB.HabilitacaoError(f"Ação desconhecida: {acao!r}.")

    @app.route("/rcpn/habilitacoes/<int:habilitacao_id>/selar",
               methods=["POST"])
    @roles_required("ADMIN", "MANAGER", "USER")
    def rcpn_habilitacao_selar(habilitacao_id):
        """Pede o selo de uma habilitação JÁ EXPEDIDA. FALA COM A REDE.

        **É A SAÍDA QUE FICA quando o aparelho estava fora do ar.** Sem ela, a
        habilitação expedida naquele dia ficaria sem selo para sempre — e o
        selo dela é o do casamento inteiro (item 14.1.1, «habilitação **e**
        registro»), reaproveitado no assento.

        É o mesmo botão que o RI ganhou em 15/09 e a escritura em 17/09, pela
        terceira vez e pela mesma razão: o ato existe, e o que falta é o selo.
        """
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            h = con.execute("SELECT * FROM hc_habilitacoes WHERE id=?",
                            (habilitacao_id,)).fetchone()
        if not h:
            abort(404)
        voltar = redirect(url_for("rcpn_habilitacao",
                                  habilitacao_id=habilitacao_id))
        if str(h["selo"] or "").strip():
            flash(f"Esta habilitação já tem o selo {h['selo']} — dois selos "
                  f"para o mesmo ato é o dinheiro da serventia saindo duas "
                  f"vezes.", "warning")
            return voltar
        recado = _selar_a_habilitacao(habilitacao_id)
        sem_selo = isinstance(recado, AS.RecadoDoSelo)
        audit("HC_HABILITACAO_SELADA", "HC_HABILITACAO", habilitacao_id,
              {"recado": str(recado).strip(), "saiu": not sem_selo})
        flash(str(recado).strip() or "O selo não foi pedido.",
              "warning" if sem_selo else "success")
        return voltar

    def _selar_a_habilitacao(habilitacao_id: int) -> str:
        """Pede o selo da habilitação DEPOIS de ela ser expedida. FALA COM A REDE.

        DOIS SELOS, UM AQUI E OUTRO NO ASSENTO — decisão do oficial em
        28/08/2026. Perguntei porque não havia o que imitar: o contrato tem os
        dois caminhos e **esta casa nunca selou por nenhum deles**.

        E o contrato confirma o desenho: o selo do ASSENTO tem o campo
        `seloReferencia`, que existe para citar **o selo do ato de
        habilitação**. Um selo só não teria o que referenciar.

        Se o selo falhar durante a expedição, quem chama cancela somente a
        certidão e conserva documentos, edital e prazo para nova tentativa.
        """
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            h = con.execute("SELECT * FROM hc_habilitacoes WHERE id=?",
                            (habilitacao_id,)).fetchone()
        if not h:
            return ""
        # O CAMINHO SAI DO TIPO, e não de uma constante escrita aqui: a
        # conversão de união estável tem endpoint próprio no contrato. Escrito
        # à mão, o caminho da conversão nunca seria usado — e o defeito só
        # apareceria no primeiro casal que convertesse.
        caminho = AS.caminho_do_ato("hc_habilitacoes", h["tipo"],
                                    especie=h["tipo"])
        versao = AS.versao_da_tabela_de_custas(
            caminho, db.get_setting("selo_tabela_custas_em", ""))
        if not versao:
            return AS.recado_de_falta(
                " A habilitação saiu SEM SELO: falta dizer de que data é a "
                "tabela de custas em vigor, em Administrativo → "
                "Configurações.")
        # NA CONVERSÃO O PROCESSO É O DA UNIÃO ESTÁVEL, e não o desta
        # habilitação — é o que o contrato pede, com esse nome.
        processo = f"{h['numero']}/{h['ano']}"
        if str(h["tipo"] or "").strip().upper() == "CONVERSAO":
            processo = (_valor(h, "uniao_estavel_processo") or "").strip()
        # HOTFIX-2026-10-07-05: o Tribunal exige dadosSelo.livro/folha/termo
        # no caminho /selo/civil/casamento/habilitacao. Na casa esses campos
        # saem do assento de proclamas (Livro D) ligado em
        # proclamas_assento_id — o mesmo vínculo que atribuicoes_web já usa
        # ao selar PROCLAMAS. Sem eles o aparelho recusa e a expedição é
        # desfeita (HC_HABILITACAO_NAO_EXPEDIDA_SELO_FALHOU).
        livro = folha = termo = ""
        aid = h["proclamas_assento_id"]
        if aid:
            with db.connect() as con2:
                con2.row_factory = sqlite3.Row
                ass = con2.execute(
                    "SELECT numero, livro_volume, matricula, dados_json "
                    "FROM rc_assentos WHERE id=?",
                    (int(aid),)).fetchone()
            if ass:
                livro = str(ass["livro_volume"] or "").strip()
                termo = str(ass["numero"] or "").strip()
                try:
                    import json as _json
                    dj = _json.loads(ass["dados_json"] or "{}") or {}
                except Exception:
                    dj = {}
                folha = str(dj.get("folha") or "").strip()
                if not livro and dj.get("livro"):
                    livro = str(dj.get("livro")).strip()
                if not termo and dj.get("termo"):
                    termo = str(dj.get("termo")).strip()
                if (not livro or not folha or not termo) and ass["matricula"]:
                    try:
                        import rc_matricula as _MAT
                        p = _MAT.partes(ass["matricula"])
                        num = str(int(p["livro"])) if str(p.get("livro") or "").strip() else ""
                        letra = str(p.get("livro_nome") or "").strip()
                        if not livro:
                            livro = f"{letra}-{num}" if letra and num else num
                        if not folha and str(p.get("folha") or "").strip():
                            folha = str(int(p["folha"]))
                        if not termo and str(p.get("termo") or "").strip():
                            termo = str(int(p["termo"]))
                    except Exception:
                        pass
        if not (livro and folha and termo):
            return AS.recado_de_falta(
                " A habilitação saiu SEM SELO: faltam livro/folha/termo do "
                "assento de proclamas (Livro D) vinculados à habilitação. "
                "Confira o proclamas_assento_id e o L/F/T do assento.")
        try:
            envelope = AS.envelope_da_habilitacao(
                escrevente=usuario_nome(), versao_tabela=versao,
                tipo=h["tipo"], numero_processo=processo,
                livro=livro, folha=folha, termo=termo,
                nubente1={"nome": h["nubente1_nome"],
                          "documento": h["nubente1_documento"]},
                nubente2={"nome": h["nubente2_nome"],
                          "documento": h["nubente2_documento"]})
        except AS.AtoError as erro:
            # O ENVELOPE NAO SE MONTOU: falta dado que a tela pergunta.
            return AS.recado_de_falta(
                f" A habilitação saiu SEM SELO: {erro}")
        r = AS.selar_o_ato_lavrado(
            db, Path(app.config["DATA_DIR"]), tabela="hc_habilitacoes",
            ato_id=habilitacao_id, tipo="HABILITACAO", atribuicao="RCPN",
            agora=agora(), cns=db.get_setting("ri_cns", ""),
            usuario=usuario_nome(), dados=envelope,
            referencia=f"hc_habilitacoes:{int(habilitacao_id)}")
        if not r["selado"]:
            # **O APARELHO RECUSOU**: e esta a metade da regra que suspende.
            return AS.recado_de_recusa(
                f" A habilitação saiu SEM SELO: {r['motivo']}")
        # SE O CASAMENTO JÁ FOI CELEBRADO, o assento recebe agora o selo que
        # acabou de sair. É a ordem incomum — aparelho fora do ar no dia em que
        # a habilitação foi expedida —, e sem isto o assento ficaria sem selo
        # com o selo dele já comprado.
        try:
            with db.transaction() as con:
                espelhado = HAB.espelhar_o_selo_no_assento(con, habilitacao_id)
        except sqlite3.Error:
            espelhado = None
        if espelhado:
            return (f" Selo {r['numero']}, anotado também no assento de "
                    f"casamento — é um selo só.")
        return f" Selo {r['numero']}."

    # ------------------------------------------------------- os papéis

    def _modelo_do_edital(h: dict) -> str:
        """O teor que a tela oferece pronto, para o escrevente ajustar.

        MODELO PREENCHIDO, E NÃO CAMPO EM BRANCO: campo em branco num edital é
        o que produz edital genérico, e o edital é o que chama terceiro a opor
        impedimento — ele precisa dizer QUEM vai casar.

        E é oferecido, não imposto: quem publica é quem assina.
        """
        sv = _sv()
        return (
            f"Faço saber que pretendem casar-se "
            f"{h['nubente1_nome']} e {h['nubente2_nome']}, "
            f"e que apresentaram os documentos exigidos pelo artigo 1.525 do "
            f"Código Civil. Se alguém souber de algum impedimento, oponha-o na "
            # O CANAL É O DESTA CASA, e não o do CC art. 1.527: o edital vai
            # ao e-Proclamas da CRC (`HC.ONDE_SE_PUBLICA`, informação do
            # oficial em 28/08/2026). Até 08/10/2026 este texto dizia
            # «afixado no lugar de costume… e publicado pela imprensa local»
            # — o que a casa não faz, num papel que ela assina.
            f"forma da lei. Lavro o presente para ser publicado em meio "
            f"eletrônico, no {HC.ONDE_SE_PUBLICA}. {sv.get('cidade_uf', '')}, "
            f"{fmt_date(date.today().isoformat())}.")

    @app.route("/rcpn/habilitacoes/<int:habilitacao_id>/edital")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def rcpn_habilitacao_edital(habilitacao_id):
        """O edital em `.odt`, para afixar. SÓ LÊ.

        O TEOR QUE SAI É O QUE FOI GRAVADO, e não o modelo remontado agora: o
        edital foi publicado num dia, com aquelas palavras, e é sobre ELE que
        alguém pode ter oposto impedimento. Remontar faria o papel afixado e o
        papel reimpresso divergirem.
        """
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            h = con.execute("SELECT * FROM hc_habilitacoes WHERE id=?",
                            (habilitacao_id,)).fetchone()
        if not h:
            abort(404)
        if not h["edital_em"]:
            flash("O edital ainda não foi publicado.", "danger")
            return redirect(url_for("rcpn_habilitacao",
                                    habilitacao_id=habilitacao_id))
        sv = _sv()
        html = (
            f'<p align="center"><b>{sv["unit_name"]}</b></p>'
            f'<p align="center">{sv["serventia_titulo"]}: '
            f'{sv["serventia_titular"]}</p>'
            f'<p align="center">CNS {sv["ri_cns"]} — {sv["endereco_completo"]}</p>'
            f'<p></p><p align="center"><b>EDITAL DE PROCLAMAS</b></p>'
            f'<p align="center"><b>Habilitação nº {h["numero"]}/{h["ano"]}</b></p>'
            f'<p></p><p>{h["edital_teor"]}</p><p></p>'
            f'<p>Publicado em {fmt_date(h["edital_em"])}. As oposições podem '
            f'ser apresentadas até {fmt_date(h["edital_prazo_ate"])}.</p>'
            f'<p></p><p></p>'
            f'<p align="center">_________________________________</p>'
            f'<p align="center">{sv["serventia_titular"]}</p>'
            f'<p align="center">{sv["serventia_titulo"]}</p>'
            f'<p></p><p class="small">{HC.AVISO_REVISAO_JURIDICA_HC}</p>'
            f'<p></p><p class="small">Conferência: {h["edital_hash"][:32]}…</p>')
        arquivo = gerar_odt(html_para_odf(html),
                            titulo=f"Edital de proclamas {h['numero']}/{h['ano']}")
        audit("HC_EDITAL_IMPRESSO", "HC_HABILITACAO", habilitacao_id, {})
        nome = f"edital-proclamas-{h['numero']}-{h['ano']}.odt"
        return Response(arquivo,
                        mimetype="application/vnd.oasis.opendocument.text",
                        headers={"Content-Disposition":
                                 f'attachment; filename="{nome}"'})

    @app.route("/rcpn/habilitacoes/<int:habilitacao_id>/certidao")
    @roles_required("ADMIN", "MANAGER", "USER", "AUDITOR")
    def rcpn_habilitacao_certidao(habilitacao_id):
        """A certidão de habilitação — CC art. 1.531. SÓ LÊ.

        É o papel que autoriza o casamento, e ele diz **até quando** vale: sem
        a data-limite impressa, quem celebra não tem como saber se ainda pode.
        """
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            h = con.execute("SELECT * FROM hc_habilitacoes WHERE id=?",
                            (habilitacao_id,)).fetchone()
        if not h:
            abort(404)
        if h["situacao"] not in ("HABILITADO", "CELEBRADO"):
            flash("A habilitação ainda não foi expedida.", "danger")
            return redirect(url_for("rcpn_habilitacao",
                                    habilitacao_id=habilitacao_id))
        sv = _sv()
        regime = HC.REGIMES.get(h["regime"] or "", "—")
        html = (
            f'<p align="center"><b>{sv["unit_name"]}</b></p>'
            f'<p align="center">{sv["serventia_titulo"]}: '
            f'{sv["serventia_titular"]}</p>'
            f'<p align="center">CNS {sv["ri_cns"]} — {sv["endereco_completo"]}</p>'
            f'<p></p>'
            f'<p align="center"><b>CERTIDÃO DE HABILITAÇÃO PARA CASAMENTO</b></p>'
            f'<p align="center"><b>Nº {h["certidao_numero"]}/{h["certidao_ano"]}'
            f' — Habilitação {h["numero"]}/{h["ano"]}</b></p><p></p>'
            f'<p>CERTIFICO que, cumpridas as formalidades legais e verificada a '
            f'inexistência de fato obstativo, estão <b>HABILITADOS</b> a casar-se, '
            f'na forma do artigo 1.531 do Código Civil:</p>'
            f'<table border="1" cols="4.6cm,11.4cm">'
            f'<tr><td><b>Nubente</b></td><td>{h["nubente1_nome"]}</td></tr>'
            f'<tr><td><b>Nubente</b></td><td>{h["nubente2_nome"]}</td></tr>'
            f'<tr><td><b>Regime de bens</b></td><td>{regime}</td></tr>'
            f'<tr><td><b>Edital publicado em</b></td>'
            f'<td>{fmt_date(h["edital_em"])}</td></tr>'
            # O PRAZO SÓ SE DIZ ENCERRADO SE JÁ ESTAVA, NO DIA DA EXPEDIÇÃO.
            # Desde o HOTFIX-2026-10-07-04 se habilita com o edital publicado
            # e o prazo ainda correndo; a certidão 1/2026 saiu em 07/10
            # afirmando «Prazo encerrado em 12/10/2026 — sem oposição». A régua
            # é a data da expedição (e não a de hoje), para a reimpressão
            # dizer o mesmo que o papel original.
            + (f'<tr><td><b>Prazo encerrado em</b></td>'
               f'<td>{fmt_date(h["edital_prazo_ate"])}'
               f'{" — sem oposição" if not h["oposicao_em"] else ""}</td></tr>'
               if str(h["habilitado_em"] or "")[:10]
               >= str(h["edital_prazo_ate"] or "")[:10] else
               f'<tr><td><b>Prazo de oposição</b></td>'
               f'<td>até {fmt_date(h["edital_prazo_ate"])} — ainda em curso '
               f'na data desta certidão'
               f'{"; sem oposição até então" if not h["oposicao_em"] else ""}'
               f'</td></tr>')
            + f'</table><p></p>'
            f'<p><b>Esta habilitação é válida até '
            f'{fmt_date(h["habilitacao_vale_ate"])}</b> — noventa dias contados '
            f'da data em que foi extraída (Código Civil, artigo 1.532). '
            f'Decorrido esse prazo sem que o casamento se realize, a '
            f'habilitação perde a eficácia e o processo se refaz.</p>'
            f'<p></p><p>{sv["cidade_uf"]}, {fmt_date(h["habilitado_em"])}.</p>'
            f'<p></p><p></p>'
            f'<p align="center">_________________________________</p>'
            f'<p align="center">{h["habilitado_por"] or sv["serventia_titular"]}</p>')
        # HOTFIX: O SELO SAI EM CARIMBO, como no resto da casa (número,
        # emolumentos, link e QR) — antes a certidão não imprimia o selo de
        # jeito nenhum, embora `hc_habilitacoes.selo` e o razão o tivessem.
        # A etiqueta inteira vem de `sd_selos.texto` (tabela + ato_id, com o
        # número como segunda porta). SÓ LÊ: não pede nem grava selo.
        imagens: dict = {}
        carimbo = ""
        numero_selo = str(h["selo"] or "").strip()
        if numero_selo:
            with db.connect() as con:
                etiqueta = AS.etiqueta_do_ato(
                    con, "hc_habilitacoes", habilitacao_id, numero_selo)
            carimbo = carimbo_compacto_odf(
                etiqueta or numero_selo, rotulo="SELO DIGITAL DO TJMA",
                imagens=imagens, prefixo_qr="qr-hab")
        conferencia = (f'<p></p><p class="small">Conferência: '
                       f'{h["certidao_hash"][:32]}…</p>')
        arquivo = gerar_odt(
            html_para_odf(html) + carimbo + html_para_odf(conferencia),
            titulo=f"Certidão de habilitação {h['certidao_numero']}/{h['certidao_ano']}",
            imagens=imagens or None)
        audit("HC_CERTIDAO_IMPRESSA", "HC_HABILITACAO", habilitacao_id, {})
        nome = (f"habilitacao-{h['certidao_numero']}-{h['certidao_ano']}.odt")
        return Response(arquivo,
                        mimetype="application/vnd.oasis.opendocument.text",
                        headers={"Content-Disposition":
                                 f'attachment; filename="{nome}"'})
