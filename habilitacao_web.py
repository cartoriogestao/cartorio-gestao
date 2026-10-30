"""As telas da habilitação de casamento.

A TELA NÃO REPETE A REGRA DO DOMÍNIO. Ela só *oferece* o que cabe na situação —
quem *recusa* é `habilitacao.py`, e há teste que manda o ato fora de ordem
direto para a função. Repetir a regra nos dois lugares é como os dois divergem:
a tela esconde o botão por educação, o domínio recusa por dever.

O TEXTO DOS PAPÉIS NÃO MORA AQUI (LF06C, 19/10/2026). O teor sugerido do
edital, a folha do edital e a certidão de habilitação são papéis do catálogo,
com o texto em `modelos_padrao/rcpn/` e o ajuste da casa na tela de Modelos.
Aqui ficou o que é do sistema: o que preenche cada claro, a regra que escolhe
a linha do prazo e o cabeçalho da serventia (a linha de conferência saiu em
22/10/2026).
"""
from __future__ import annotations

import sqlite3
from datetime import date

from flask import Response, abort, flash, redirect, render_template, request, url_for

import ato_selado as AS
import habilitacao as HAB
import habilitacao_fases as HABFASES
from bd_nativo import banco
import hc_schema as HC
import rc_textos as TEXTOS
from seguranca_web import numero_digitado  # LD13: o número que a tela mandou
from pathlib import Path

from ri_odt import carimbo_compacto_odf, gerar_odt, html_para_odf


# ------------------------------------------------------------ os papéis
#
# O TEXTO É DA CASA, A REGRA É DO SISTEMA. Os três papéis da habilitação eram
# f-strings dentro das rotas até o LF06C; o texto foi para a pasta dos padrões
# com os mesmos bytes (o ouro `tests/fixtures/modelos_ouro/LF06C_habilitacao`
# confere), e quem tem a conexão o lê pela busca única — o ajuste da casa, e
# na falta dele o padrão. Os montadores abaixo só calculam: sem `modelo`,
# valem o padrão da base.

CHAVE_DO_EDITAL = "RC_EDITAL_PROCLAMAS"
CHAVE_DA_FOLHA_DO_EDITAL = "RC_EDITAL_PROCLAMAS_FOLHA"
CHAVE_DA_CERTIDAO = "RC_CERTIDAO_HABILITACAO"

# A LINHA DO PRAZO DA CERTIDÃO, uma peça por situação: (o prazo já estava
# encerrado no dia da expedição?, sem oposição?) -> a peça. Quem escolhe é
# `peca_da_linha_do_prazo`; o texto de cada uma é ajustável.
PECA_DA_LINHA_DO_PRAZO: dict[tuple[bool, bool], str] = {
    (True, True): "RC_CERTIDAO_HABILITACAO__prazo_encerrado_sem_oposicao",
    (True, False): "RC_CERTIDAO_HABILITACAO__prazo_encerrado",
    (False, True): "RC_CERTIDAO_HABILITACAO__prazo_em_curso_sem_oposicao",
    (False, False): "RC_CERTIDAO_HABILITACAO__prazo_em_curso",
}


def _cabecalho_da_serventia(sv: dict) -> str:
    """O timbre da serventia, em três linhas, no alto do edital e da certidão.

    FICA NO CÓDIGO, fora do texto dos papéis: é o cabeçalho das folhas da
    casa, e o oficial decidiu em 07/09/2026 mantê-lo à parte dos modelos.
    """
    return (f'<p align="center"><b>{sv["unit_name"]}</b></p>'
            f'<p align="center">{sv["serventia_titulo"]}: '
            f'{sv["serventia_titular"]}</p>'
            f'<p align="center">CNS {sv["ri_cns"]} — {sv["endereco_completo"]}</p>')


# A LINHA «Conferência: <hash>…» SAIU DO EDITAL E DA CERTIDÃO — ordem do
# oficial em 22/10/2026 («4 confirmo»). Ela imprimia o começo do hash gravado
# (`edital_hash`, `certidao_hash`), e nenhum outro papel da casa faz isso, o
# E-Ofício não fazia e o público não tem onde conferir o número: no papel ele
# parecia código de validação. O hash continua gravado no banco, que é onde
# ele prova alguma coisa. A função foi apagada, e não desligada.


# O ESTADO CIVIL NO EDITAL, concordando com o sexo do nubente. A tela grava o
# código (`SOLTEIRO`, `VIUVO`, `DIVORCIADO`); o que não for código passa como
# veio, em maiúsculas — é o que o balcão escreveu.
_ESTADO_CIVIL_NO_EDITAL: dict[str, tuple[str, str]] = {
    "SOLTEIRO": ("SOLTEIRO", "SOLTEIRA"),
    "VIUVO": ("VIÚVO", "VIÚVA"),
    "DIVORCIADO": ("DIVORCIADO", "DIVORCIADA"),
}


def _txt(v) -> str:
    return "" if v is None else str(v).strip()


def _do_nubente(h, lado: str, campo: str) -> str:
    """Uma coluna do nubente, vazia quando a linha não a tem. Só calcula."""
    chave = f"{lado}_{campo}"
    try:
        return _txt(h[chave])
    except (KeyError, IndexError):
        return ""


def estado_civil_no_edital(codigo, sexo) -> str:
    """«DIVORCIADA», «SOLTEIRO(A)» — o estado civil como o edital o escreve."""
    bruto = _txt(codigo).upper()
    formas = _ESTADO_CIVIL_NO_EDITAL.get(bruto)
    if not formas:
        return bruto
    s = _txt(sexo).upper()[:1]
    if s == "M":
        return formas[0]
    if s == "F":
        return formas[1]
    return formas[0] + "(A)" if formas[1] == formas[0][:-1] + "A" else formas[0]


def cidade_do_endereco(endereco) -> str:
    """«Cidade Exemplo/MA», tirada do fim do endereço — ou nada. Só calcula.

    **SÓ QUANDO O ENDEREÇO TERMINA EM «MUNICÍPIO/UF».** A habilitação guarda
    o endereço num campo de texto livre, e partir esse texto às cegas poria
    «Centro» no lugar da cidade (a lição de `proclamas.py`). O que vem depois
    da última vírgula só vale como município quando é «nome/UF» ou
    «nome-UF», com a UF de duas letras e sem número; senão o edital não
    afirma cidade nenhuma — campo vazio não afirma, campo errado afirma.
    """
    import re
    ultimo = _txt(endereco).rsplit(",", 1)[-1].strip(" .")
    achado = re.fullmatch(r"([^\d/,]+?)\s*[/-]\s*([A-Za-z]{2})", ultimo)
    if not achado or " - " in achado.group(1):
        return ""
    return f"{achado.group(1).strip()}/{achado.group(2).upper()}"


def _a_mesma_cidade(a: str, b: str) -> bool:
    import unicodedata

    def norm(x: str) -> str:
        return "".join(c for c in unicodedata.normalize("NFD", x.upper())
                       if unicodedata.category(c) != "Mn").strip()
    return bool(a) and norm(a) == norm(b)


def frases_dos_nubentes_no_edital(h, *, sv: dict) -> dict[str, str]:
    """O estado civil, a filiação e o domicílio dos noivos, para o edital. Só
    calcula.

    **O EDITAL TRAZIA SÓ OS NOMES** — LD01, 21/10/2026. O CNN (art. 122) manda
    o edital conter «tão somente o nome, o estado civil, a filiação, a cidade
    e a circunscrição do domicílio dos noivos» (e a LRP, art. 67, § 1º, que se
    publique). O «tão somente» vale dos dois lados: a rua não entra — só a
    cidade e, quando é a da serventia, «nesta circunscrição».

    Os dois nubentes vão «respectivamente», na ordem dos nomes. O que a
    habilitação não tem de nenhum dos dois não vira frase; o que falta de um
    só sai como «não declarado», para não emprestar ao outro.
    """
    lados = ("nubente1", "nubente2")
    estados = [estado_civil_no_edital(_do_nubente(h, l, "estado_civil"),
                                      _do_nubente(h, l, "sexo")) for l in lados]
    pais = [" e ".join(x for x in (_do_nubente(h, l, "mae"),
                                   _do_nubente(h, l, "pai")) if x)
            for l in lados]
    cidade_da_casa = _txt((sv or {}).get("ri_cidade"))
    domicilios = []
    for lado in lados:
        cidade = cidade_do_endereco(_do_nubente(h, lado, "endereco"))
        if cidade and _a_mesma_cidade(cidade.rsplit("/", 1)[0], cidade_da_casa):
            cidade += ", nesta circunscrição"
        domicilios.append(cidade)

    def par(valores: list[str], falta: str) -> list[str]:
        return [v or falta for v in valores]

    frases = {"estado_civil": "", "filiacao": "", "domicilio": ""}
    if any(estados):
        e1, e2 = par(estados, "NÃO DECLARADO")
        frases["estado_civil"] = ", " + TEXTOS.peca(
            "RC_EDITAL_PROCLAMAS__estado_civil", estados=f"{e1} e {e2}")
    if any(pais):
        p1, p2 = par(pais, "pais não declarados")
        frases["filiacao"] = ", " + TEXTOS.peca(
            "RC_EDITAL_PROCLAMAS__filiacao", pais1=p1, pais2=p2)
    if any(domicilios):
        if domicilios[0] == domicilios[1]:
            frases["domicilio"] = ", " + TEXTOS.peca(
                "RC_EDITAL_PROCLAMAS__domicilio_comum", domicilio=domicilios[0])
        else:
            d1, d2 = par(domicilios, "domicílio não declarado")
            frases["domicilio"] = ", " + TEXTOS.peca(
                "RC_EDITAL_PROCLAMAS__domicilio", domicilio1=d1, domicilio2=d2)
    return frases


def teor_sugerido_do_edital(h, *, sv: dict, hoje_iso: str, fmt_date,
                            modelo: str | None = None) -> str:
    """O teor que a tela oferece pronto, para o escrevente ajustar. Só calcula.

    MODELO PREENCHIDO, E NÃO CAMPO EM BRANCO: campo em branco num edital é
    o que produz edital genérico, e o edital é o que chama terceiro a opor
    impedimento — ele precisa dizer QUEM vai casar.

    E é oferecido, não imposto: quem publica é quem assina. O que vale é o
    teor PUBLICADO, que congela em `hc_habilitacoes.edital_teor` com o hash;
    por isso um ajuste deste texto não muda edital já publicado.

    `modelo` é o texto lido pela busca única por quem tem a conexão; sem ele,
    vale o padrão da base.
    """
    corpo = modelo or TEXTOS.texto(CHAVE_DO_EDITAL)
    return corpo.format(
        nubente1_nome=h["nubente1_nome"], nubente2_nome=h["nubente2_nome"],
        # O estado civil, a filiação e o domicílio (CNN art. 122 — LD01).
        **frases_dos_nubentes_no_edital(h, sv=sv),
        # O CANAL É O DESTA CASA, e não o do CC art. 1.527: o edital vai
        # ao e-Proclamas da CRC (`HC.ONDE_SE_PUBLICA`, informação do
        # oficial em 28/08/2026). Até 08/10/2026 este texto dizia
        # «afixado no lugar de costume… e publicado pela imprensa local»
        # — o que a casa não faz, num papel que ela assina.
        onde_se_publica=HC.ONDE_SE_PUBLICA,
        cidade_uf=sv.get("cidade_uf", ""), data=fmt_date(hoje_iso))


def html_do_edital(h, *, sv: dict, fmt_date, modelo: str | None = None) -> str:
    """A folha do edital em HTML: cabeçalho e o papel. Só calcula.

    `{teor}` é o teor GRAVADO na publicação, e não o sugerido remontado agora
    (ver a rota). `modelo` é a folha lida pela busca única; sem ele, vale o
    padrão da base.

    O AVISO INTERNO SAI NA FOLHA PÚBLICA, como saía antes do LF06C:
    `{aviso_de_revisao_juridica}` é o `HC.AVISO_REVISAO_JURIDICA_HC`, o aviso
    da ficha para o escrevente. Ficou claro, e não texto, para acompanhar a
    constante; a casa pode tirá-lo da folha na tela de Modelos.
    """
    folha = modelo or TEXTOS.texto(CHAVE_DA_FOLHA_DO_EDITAL)
    return (_cabecalho_da_serventia(sv)
            + folha.format(
                numero=h["numero"], ano=h["ano"], teor=h["edital_teor"],
                publicado_em=fmt_date(h["edital_em"]),
                prazo_ate=fmt_date(h["edital_prazo_ate"]),
                serventia_titular=sv["serventia_titular"],
                serventia_titulo=sv["serventia_titulo"],
                aviso_de_revisao_juridica=HC.AVISO_REVISAO_JURIDICA_HC))


def peca_da_linha_do_prazo(h) -> str:
    """Qual linha do prazo de oposição a certidão imprime. Só calcula.

    O PRAZO SÓ SE DIZ ENCERRADO SE JÁ ESTAVA, NO DIA DA EXPEDIÇÃO.
    Desde o HOTFIX-2026-10-07-04 se habilita com o edital publicado
    e o prazo ainda correndo; a certidão 1/2026 saiu em 07/10
    afirmando «Prazo encerrado em 12/10/2026 — sem oposição». A régua
    é a data da expedição (e não a de hoje), para a reimpressão
    dizer o mesmo que o papel original.
    """
    encerrado = (str(h["habilitado_em"] or "")[:10]
                 >= str(h["edital_prazo_ate"] or "")[:10])
    return PECA_DA_LINHA_DO_PRAZO[(encerrado, not h["oposicao_em"])]


def html_da_certidao(h, *, sv: dict, fmt_date, modelo: str | None = None,
                     linha_do_prazo: str | None = None) -> str:
    """A certidão de habilitação em HTML, sem o selo. Só calcula.

    `modelo` é o texto da certidão e `linha_do_prazo` a peça que
    `peca_da_linha_do_prazo` escolheu, os dois lidos pela busca única por quem
    tem a conexão; sem eles, vale o padrão da base.

    NÃO CONGELA: a certidão é remontada a cada impressão (`certidao_teor` fica
    nulo), e por isso um ajuste da casa muda também a reimpressão das
    certidões já expedidas.
    """
    corpo = modelo or TEXTOS.texto(CHAVE_DA_CERTIDAO)
    linha = linha_do_prazo or TEXTOS.texto(peca_da_linha_do_prazo(h))
    return (_cabecalho_da_serventia(sv)
            + corpo.format(
                certidao_numero=h["certidao_numero"],
                certidao_ano=h["certidao_ano"], numero=h["numero"], ano=h["ano"],
                nubente1_nome=h["nubente1_nome"], nubente2_nome=h["nubente2_nome"],
                regime=HC.REGIMES.get(h["regime"] or "", "—"),
                edital_em=fmt_date(h["edital_em"]),
                linha_do_prazo=linha.format(
                    prazo_ate=fmt_date(h["edital_prazo_ate"])),
                vale_ate=fmt_date(h["habilitacao_vale_ate"]),
                cidade_uf=sv["cidade_uf"],
                habilitado_em=fmt_date(h["habilitado_em"]),
                assinante=h["habilitado_por"] or sv["serventia_titular"]))


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

    def _registrar_no_livro_d(con, habilitacao_id: int) -> dict:
        """O registro do edital no Livro D (LD01) — o domínio lança; aqui só
        se dá a serventia e a data por extenso que o livro pede."""
        from ri_web import data_por_extenso
        return HAB.registrar_o_edital_no_livro_d(
            con, habilitacao_id, sv=_sv(), agora=agora(),
            data_extenso=data_por_extenso(date.fromisoformat(hoje())),
            usuario=usuario_nome())

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

        COLUNA DE MIGRAÇÃO PODE NÃO ESTAR LÁ, e uma linha do banco estoura com
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
            linhas = HAB.listar(con, situacao=situacao or None,
                                busca=busca or None)
            # O QUE FAZER AGORA, JÁ NA LISTA — num rito de semanas, a pergunta
            # não é «quais existem», é «qual delas espera por mim».
            for h in linhas:
                h["passos"] = HAB.proximos_passos(con, h["id"], hoje())
            resumo = {s: int(banco(con).valor(
                "SELECT COUNT(*) AS n FROM hc_habilitacoes WHERE situacao=%s",
                (s,))) for s in HC.SITUACOES}
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
            # O «²» passava pelo `isdigit()` e o `int()` caía com a habilitação
            # já aberta (LD13); leitura que não é número é como nenhuma.
            leitura_id = numero_digitado(dados.get("leitura_id"))
            if leitura_id is not None:
                import rc_leitura_documentos as LEIT
                with db.transaction() as con:
                    LEIT.ligar_documentos(con, leitura_id, "HC_HABILITACAO", int(novo),
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
    # O AUDITOR ve a tela; o que ela GRAVA (POST) exige papel que pratica ato.
    @roles_required("ADMIN", "MANAGER", "USER", metodos=("POST",))
    def rcpn_habilitacao(habilitacao_id):
        if request.method == "POST":
            acao = _campo("acao")
            try:
                with db.transaction() as con:
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
            h = banco(con).um("SELECT * FROM hc_habilitacoes WHERE id=%s",
                              (habilitacao_id,))
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
            # O TEOR SUGERIDO É O DA CASA (o ajuste, ou o padrão), lido pela
            # busca única enquanto a conexão está aberta — o papel e as peças
            # dele (o estado civil, a filiação, o domicílio). Só lê.
            with TEXTOS.lendo_da_casa(con):
                modelo_edital = teor_sugerido_do_edital(
                    h, sv=_sv(), hoje_iso=hoje(), fmt_date=fmt_date,
                    modelo=TEXTOS.texto(CHAVE_DO_EDITAL, con))
        anexos_leitura = [dict(r) for r in db.get_attachments("HC_HABILITACAO", habilitacao_id)]
        def fases_da_ficha() -> dict:
            """A régua do layout novo. Só ele chama."""
            return HABFASES.fases_da_habilitacao(
                h, falta=falta, andamento=andamento, vencida=vencida,
                uniao_estavel=_valor(h, "uniao_estavel_processo"))
        return render_template(
            "rcpn_habilitacao.html", h=h, documentos=documentos,
            andamento=andamento, passos=passos, falta=falta,
            prazo_venceu=prazo_venceu, vencida=vencida,
            SITUACOES=HC.SITUACOES, TIPOS=HC.TIPOS, REGIMES=HC.REGIMES,
            PRAZO=HC.PRAZO_DO_EDITAL, VALIDADE=HC.VALIDADE_DA_HABILITACAO,
            ONDE_SE_PUBLICA=HC.ONDE_SE_PUBLICA,
            AVISO_REVISAO_JURIDICA=HC.AVISO_REVISAO_JURIDICA_HC,
            uniao_estavel=_valor(h, "uniao_estavel_processo"),
            modelo_edital=modelo_edital,
            casamentos=casamentos,
            anexos_leitura=anexos_leitura,
            fases_da_ficha=fases_da_ficha)

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
            # O EDITAL SE REGISTRA NO LIVRO D AO SAIR (CN-MA art. 265) — LD01.
            # Na mesma transação: edital que não se registra não se publica.
            livro_d = _registrar_no_livro_d(con, habilitacao_id)
            return (f"Edital publicado. O prazo de {HC.PRAZO_DO_EDITAL} dias "
                    f"vai até {r['prazo_ate']}. Registrado no Livro D "
                    f"{livro_d.get('livro') or ''}, folha "
                    f"{livro_d.get('folha') or ''}, termo "
                    f"{livro_d.get('termo') or ''}.")
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
            # O EDITAL PUBLICADO ANTES DO LD01 NÃO TEM O REGISTRO NO LIVRO D,
            # e sem ele o selo não sai: registra-se agora (uma vez só; o
            # registrado continua o mesmo). Não registra edital que não houve.
            if banco(con).valor(
                    "SELECT edital_em FROM hc_habilitacoes WHERE id = %s",
                    (int(habilitacao_id),)):
                _registrar_no_livro_d(con, habilitacao_id)
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
            h = banco(con).um("SELECT * FROM hc_habilitacoes WHERE id=%s",
                              (habilitacao_id,))
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
            h = banco(con).um("SELECT * FROM hc_habilitacoes WHERE id=%s",
                              (habilitacao_id,))
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
            # O LUGAR DO ATO DE REGISTRO VEM PRIMEIRO (LD01): o registro que
            # `HAB.registrar_o_edital_no_livro_d` lavra tem livro, folha e
            # termo no ato, como todo assento; o volume, o blob e a matrícula
            # ficam para o vínculo antigo, feito à mão.
            import rc_certidao as RCE
            with db.connect() as con2:
                ass = banco(con2).um(
                    "SELECT numero, livro_volume, matricula, dados_json "
                    "FROM rc_assentos WHERE id=%s",
                    (int(aid),))
                lugar = RCE.lugar_do_assento(con2, int(aid)) if ass else {}
            livro = str(lugar.get("livro") or "").strip()
            folha = str(lugar.get("folha") or "").strip()
            termo = str(lugar.get("termo") or "").strip()
            if ass and not (livro and folha and termo):
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
                # O MESMO SELO NO REGISTRO DO EDITAL NO LIVRO D (LD01): o
                # envelope levou o livro, a folha e o termo dele.
                HAB.espelhar_o_selo_no_livro_d(con, habilitacao_id)
                espelhado = HAB.espelhar_o_selo_no_assento(con, habilitacao_id)
        except sqlite3.Error:
            espelhado = None
        if espelhado:
            return (f" Selo {r['numero']}, anotado também no assento de "
                    f"casamento — é um selo só.")
        return f" Selo {r['numero']}."

    # ------------------------------------------------------- os papéis
    #
    # O teor sugerido do edital é montado na ficha (acima), por
    # `teor_sugerido_do_edital`; os montadores dos três papéis estão no alto
    # deste módulo.

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
            h = banco(con).um("SELECT * FROM hc_habilitacoes WHERE id=%s",
                              (habilitacao_id,))
            if not h:
                abort(404)
            if not h["edital_em"]:
                flash("O edital ainda não foi publicado.", "danger")
                return redirect(url_for("rcpn_habilitacao",
                                        habilitacao_id=habilitacao_id))
            # A FOLHA É A DA CASA (o ajuste, ou o padrão), lida pela busca
            # única com a mesma conexão. O teor dentro dela é o gravado.
            folha = TEXTOS.texto(CHAVE_DA_FOLHA_DO_EDITAL, con)
        html = html_do_edital(h, sv=_sv(), fmt_date=fmt_date, modelo=folha)
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
            h = banco(con).um("SELECT * FROM hc_habilitacoes WHERE id=%s",
                              (habilitacao_id,))
            if not h:
                abort(404)
            if h["situacao"] not in ("HABILITADO", "CELEBRADO"):
                flash("A habilitação ainda não foi expedida.", "danger")
                return redirect(url_for("rcpn_habilitacao",
                                        habilitacao_id=habilitacao_id))
            # O TEXTO E A LINHA DO PRAZO SÃO OS DA CASA (o ajuste, ou o
            # padrão), lidos pela busca única com a mesma conexão.
            modelo = TEXTOS.texto(CHAVE_DA_CERTIDAO, con)
            linha_do_prazo = TEXTOS.texto(peca_da_linha_do_prazo(h), con)
        html = html_da_certidao(h, sv=_sv(), fmt_date=fmt_date, modelo=modelo,
                                linha_do_prazo=linha_do_prazo)
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
        arquivo = gerar_odt(
            html_para_odf(html) + carimbo,
            titulo=f"Certidão de habilitação {h['certidao_numero']}/{h['certidao_ano']}",
            imagens=imagens or None)
        audit("HC_CERTIDAO_IMPRESSA", "HC_HABILITACAO", habilitacao_id, {})
        nome = (f"habilitacao-{h['certidao_numero']}-{h['certidao_ano']}.odt")
        return Response(arquivo,
                        mimetype="application/vnd.oasis.opendocument.text",
                        headers={"Content-Disposition":
                                 f'attachment; filename="{nome}"'})


def __getattr__(nome: str):
    """Os nomes antigos dos três papéis, lidos da base dos padrões.

    O TEXTO SAIU DESTE MÓDULO NO LF06C (19/10/2026) e mora em
    `modelos_padrao/rcpn/`. Os papéis não eram constantes — eram f-strings
    dentro das rotas —, e o catálogo os registra com os nomes
    `EDITAL_DE_PROCLAMAS`, `FOLHA_DO_EDITAL` e `CERTIDAO_DE_HABILITACAO`: quem
    os pedir recebe o padrão da base, o MESMO que o papel imprime, e não uma
    cópia que ficou para trás. Nome que não é de papel continua sendo
    `AttributeError`.
    """
    if nome.startswith("__"):
        raise AttributeError(nome)
    import modelos_da_casa as _MODELOS
    return _MODELOS.constante_antiga(__name__, nome)
