"""AS TELAS DO PROCESSO FIDUCIÁRIO, DO SOBRESTAMENTO E DA DOI DO RTD. A rota só liga os fios.

O domínio mora em `rg_fiduciaria`, `rg_titulo` e `rg_doi`. O nome das rotas começa com
`rcpj_rtd` porque é o prefixo que diz de que módulo é a tela.
"""
from __future__ import annotations

from datetime import date

from flask import flash, redirect, render_template, request, url_for

import rg_doi as RDOI
import rg_fiduciaria as FID
import rg_livros as RGL
import rg_titulo as TIT
from rg_web import QUEM_OPERA, QUEM_QUALIFICA
from ri_schema import eh_dia_util, ler_feriados_locais
from ri_web import data_por_extenso
from serventia import dados as dados_serventia

# Quem decide no processo é quem qualifica o título: a mesma regra, num lugar só.
QUEM_DECIDE = QUEM_QUALIFICA

# As ações que decidem o processo são do oficial; o balcão lança o que aconteceu.
ACOES_DO_OFICIAL = {"qualificar", "conhecer", "decidir", "concluir", "extinguir", "desistir"}


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    """Pendura as telas no app já construído."""

    usuario_nome = app.extensions["usuario_nome"]
    usuario_papel = app.extensions["usuario_papel"]

    def _campo(nome: str) -> str:
        return (request.form.get(nome) or "").strip()

    def _e_util():
        locais = ler_feriados_locais(db.get_setting("ri_feriados_locais", ""))
        return lambda d: eh_dia_util(d, locais)

    def _hoje() -> str:
        return db.now()[:10]

    @app.route("/rcpj-rtd/fiduciaria")
    @login_required
    def rcpj_rtd_fiduciarias():
        """A fila: o prazo vencido primeiro. Só LÊ."""
        hoje = _hoje()
        with db.connect() as con:
            abertos = FID.fila(con, hoje=hoje)
            encerrados = FID.fila(con, hoje=hoje, abertos=False)
        return render_template("rcpj_rtd_fiduciarias.html", abertos=abertos, encerrados=encerrados, fmt_date=fmt_date)

    @app.route("/rcpj-rtd/fiduciaria/nova", methods=["GET", "POST"])
    @roles_required(*QUEM_OPERA)
    def rcpj_rtd_fiduciaria_nova():
        """Autua o requerimento, a partir do título protocolado. ESCREVE no POST."""
        if request.method == "POST":
            try:
                with db.transaction() as con:
                    feito = FID.autuar(
                        con, titulo_id=int(_campo("titulo_id") or 0), ano=int(db.now()[:4]), agora=db.now(),
                        usuario=usuario_nome(), **{c: _campo(c) for c in (
                            "credor_nome", "credor_documento", "credor_contato", "devedor_nome",
                            "devedor_documento", "devedor_email", "devedor_endereco", "contrato",
                            "bem_descricao", "bem_identificacao", "valor_divida", "registro_numero",
                            "protocolo_central")})
            except (FID.FiduciariaError, TIT.TituloError) as erro:
                flash(str(erro), "danger")
                return redirect(url_for("rcpj_rtd_fiduciaria_nova", titulo_id=_campo("titulo_id")))
            audit("RG_FIDUCIARIA_AUTUADA", "rg_fiduciarias", feito["id"], {"rotulo": feito["rotulo"]})
            flash(f"Processo autuado sob o n. {feito['rotulo']}.", "success")
            return redirect(url_for("rcpj_rtd_fiduciaria", proc_id=feito["id"]))
        with db.connect() as con:
            titulos = FID.titulos_para_autuar(con)
        return render_template("rcpj_rtd_fiduciaria_nova.html", titulos=titulos,
                               escolhido=(request.args.get("titulo_id") or ""))

    @app.route("/rcpj-rtd/fiduciaria/<int:proc_id>")
    @login_required
    def rcpj_rtd_fiduciaria(proc_id: int):
        """A ficha do processo, em fases no layout novo. Só LÊ."""
        hoje = _hoje()
        with db.connect() as con:
            p = FID.um(con, proc_id)
            if not p:
                flash("Processo não encontrado.", "danger")
                return redirect(url_for("rcpj_rtd_fiduciarias"))
            eventos = FID.eventos_de(con, proc_id)
            titulo = TIT.um(con, int(p["titulo_id"]))
            registro_id = p["registro_id"] or titulo.get("registro_id")
            atos = []
            if registro_id:
                from bd_nativo import banco
                atos = [dict(x) for x in banco(con).ler(
                    "SELECT id, tipo, numero_ordem, data_ato FROM rg_atos WHERE registro_id=%s ORDER BY id",
                    (int(registro_id),))]

        def abas_da_ficha(pode_decidir: bool = False) -> dict:
            return FID.fases(p, pode_decidir=pode_decidir, eventos=eventos)

        feitas = {e["tipo"].replace("PROVIDENCIA_", "") for e in eventos if e["tipo"].startswith("PROVIDENCIA_")}
        return render_template(
            "rcpj_rtd_fiduciaria.html", p=p, eventos=eventos, titulo=titulo, registro_id=registro_id, atos=atos,
            acoes=FID.acoes_possiveis(p, hoje=hoje), abas_da_ficha=abas_da_ficha, hoje=hoje,
            situacao=FID.SITUACOES.get(p["situacao"], p["situacao"]), requisitos=FID.REQUISITOS,
            providencias=FID.PROVIDENCIAS, providencias_feitas=feitas, formas=FID.FORMAS_DE_NOTIFICAR,
            resultados=FID.RESULTADOS_DA_DILIGENCIA, pecas=FID.pecas_disponiveis(p, eventos),
            pendentes=FID.averbacoes_pendentes(p, eventos), reais=FID.reais, fmt_date=fmt_date,
            documento_na_tela=RGL.documento_na_tela)

    @app.route("/rcpj-rtd/fiduciaria/<int:proc_id>/acao", methods=["POST"])
    @roles_required(*QUEM_OPERA)
    def rcpj_rtd_fiduciaria_acao(proc_id: int):
        """Lança um passo do rito. ESCREVE. O domínio recusa o que não cabe na situação."""
        voltar = redirect(url_for("rcpj_rtd_fiduciaria", proc_id=proc_id))
        acao = _campo("acao")
        if acao in ACOES_DO_OFICIAL and usuario_papel() not in QUEM_DECIDE:
            flash("Este passo é do oficial.", "danger")
            return voltar
        dia = _campo("dia") or _hoje()
        comum = {"agora": db.now(), "usuario": usuario_nome()}
        util = {"e_util": _e_util()}
        marca = lambda n: bool(request.form.get(n))  # noqa: E731
        passos = {
            "qualificar": lambda c: FID.qualificar(c, proc_id, resultado=_campo("resultado"), itens=request.form.getlist("itens"), motivo=_campo("motivo"), dia=dia, **comum),
            "notificar": lambda c: FID.notificar(c, proc_id, forma=_campo("forma"), dia=dia, **comum, **util),
            "ciencia": lambda c: FID.ciencia(c, proc_id, dia=dia, **comum, **util),
            "pagamento": lambda c: FID.pagamento(c, proc_id, dia=dia, valor=_campo("valor"), integral=marca("integral"), credor_aceitou=marca("credor_aceitou"), ao_oficial=marca("ao_oficial"), **comum, **util),
            "impugnar": lambda c: FID.impugnar(c, proc_id, dia=dia, texto=_campo("texto"), valor=_campo("valor"), **comum),
            "conhecer": lambda c: FID.conhecer(c, proc_id, conhece=_campo("conhece") == "1", fundamento=_campo("fundamento"), dia=dia, **comum, **util),
            "decidir": lambda c: FID.decidir(c, proc_id, procedente=_campo("procedente") == "1", fundamento=_campo("fundamento"), dia=dia, **comum),
            "entrega": lambda c: FID.entrega(c, proc_id, dia=dia, detalhe=_campo("detalhe"), **comum, **util),
            "requerer_busca": lambda c: FID.requerer_busca(c, proc_id, dia=dia, valor=_campo("valor"), tem_planilha=marca("planilha"), hoje=_hoje(), **comum),
            "providencia": lambda c: FID.providencia(c, proc_id, qual=_campo("qual"), dia=dia, **comum),
            "diligencia": lambda c: FID.diligencia(c, proc_id, dia=dia, hora=_campo("hora"), local=_campo("local"), resultado=_campo("resultado"), detalhe=_campo("detalhe"), **comum, **util),
            "cancelar_providencias": lambda c: FID.cancelar_providencias(c, proc_id, dia=dia, **comum),
            "reverter": lambda c: FID.reverter(c, proc_id, dia=dia, detalhe=_campo("detalhe"), **comum),
            "concluir": lambda c: FID.concluir(c, proc_id, dia=dia, valor_venda=_campo("valor"), detalhe=_campo("detalhe"), hoje=_hoje(), **comum),
            "desistir": lambda c: FID.desistir(c, proc_id, motivo=_campo("motivo"), dia=dia, **comum, **util),
            "extinguir": lambda c: FID.extinguir(c, proc_id, motivo=_campo("motivo"), dia=dia, **comum),
        }
        if acao not in passos:
            flash("Este passo não existe.", "danger")
            return voltar
        try:
            with db.transaction() as con:
                passos[acao](con)
        except FID.FiduciariaError as erro:
            flash(str(erro), "danger")
            return voltar
        audit("RG_FIDUCIARIA_PASSO", "rg_fiduciarias", proc_id, {"acao": acao, "dia": dia})
        flash("Lançado na linha do tempo do processo.", "success")
        return voltar

    @app.route("/rcpj-rtd/fiduciaria/<int:proc_id>/averbacao/<int:evento_id>", methods=["POST"])
    @roles_required(*QUEM_OPERA)
    def rcpj_rtd_fiduciaria_averbacao(proc_id: int, evento_id: int):
        """Amarra ao passo o ato lavrado na ficha do registro. ESCREVE. CN art. 397-M."""
        try:
            with db.transaction() as con:
                FID.amarrar_averbacao(con, proc_id, evento_id, ato_id=int(_campo("ato_id") or 0))
        except FID.FiduciariaError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpj_rtd_fiduciaria", proc_id=proc_id))
        audit("RG_FIDUCIARIA_AVERBACAO", "rg_fiduciarias", proc_id, {"evento": evento_id, "ato": _campo("ato_id")})
        flash("Ato amarrado ao passo do processo.", "success")
        return redirect(url_for("rcpj_rtd_fiduciaria", proc_id=proc_id))

    @app.route("/rcpj-rtd/fiduciaria/<int:proc_id>/peca/<qual>")
    @login_required
    def rcpj_rtd_fiduciaria_peca(proc_id: int, qual: str):
        """A peça em papel: montar e imprimir não grava nada. Só LÊ."""
        with db.connect() as con:
            p = FID.um(con, proc_id)
            eventos = FID.eventos_de(con, proc_id) if p else []
        disponiveis = FID.pecas_disponiveis(p, eventos) if p else {}
        if qual not in disponiveis:
            flash("Esta peça ainda não cabe neste processo.", "warning")
            return redirect(url_for("rcpj_rtd_fiduciarias") if not p else url_for("rcpj_rtd_fiduciaria", proc_id=proc_id))
        s = dados_serventia(db.get_settings)
        return render_template(
            "rcpj_rtd_fiduciaria_peca.html", p=p, sv=s, titulo=disponiveis[qual],
            paragrafos=FID.texto_da_peca(p, qual, eventos, sv=s),
            data_extenso=data_por_extenso(date.fromisoformat(_hoje())))

    # ---------------------------------------------------- o sobrestamento do título

    @app.route("/rcpj-rtd/titulo/<int:titulo_id>/sobrestar", methods=["POST"])
    @roles_required(*QUEM_DECIDE)
    def rcpj_rtd_titulo_sobrestar(titulo_id: int):
        """Suspende o lançamento, preservando número e data. ESCREVE. CN-MA arts. 971 e 975, § 1º."""
        try:
            with db.transaction() as con:
                TIT.sobrestar(con, titulo_id, tipo=_campo("tipo"), motivo=_campo("motivo"),
                              notificado_em=_campo("notificado_em"), agora=db.now(), usuario=usuario_nome())
        except TIT.TituloError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpj_rtd_titulo", titulo_id=titulo_id))
        audit("RG_TITULO_SOBRESTADO", "rg_titulos", titulo_id, {"tipo": _campo("tipo")})
        flash("Lançamento sobrestado. Os títulos seguintes podem seguir (art. 971, parágrafo único).", "success")
        return redirect(url_for("rcpj_rtd_titulo", titulo_id=titulo_id))

    @app.route("/rcpj-rtd/titulo/<int:titulo_id>/retomar", methods=["POST"])
    @roles_required(*QUEM_DECIDE)
    def rcpj_rtd_titulo_retomar(titulo_id: int):
        """Encerra o sobrestamento, retomando ou remetendo ao juízo. ESCREVE. CN-MA art. 975, §§ 2º e 3º."""
        try:
            with db.transaction() as con:
                TIT.retomar(con, titulo_id, forma=_campo("forma"), motivo=_campo("motivo"),
                            agora=db.now(), usuario=usuario_nome())
        except TIT.TituloError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpj_rtd_titulo", titulo_id=titulo_id))
        audit("RG_TITULO_RETOMADO", "rg_titulos", titulo_id, {"forma": _campo("forma")})
        flash("Sobrestamento encerrado; a ocorrência ficou anotada no título.", "success")
        return redirect(url_for("rcpj_rtd_titulo", titulo_id=titulo_id))

    # --------------------------------------------------------------- a DOI do RTD

    @app.route("/rcpj-rtd/<int:registro_id>/doi", methods=["POST"])
    @roles_required(*QUEM_DECIDE)
    def rcpj_rtd_doi_gravar(registro_id: int):
        """Grava ou retira os dados da DOI do registro. ESCREVE. CN-MA art. 962."""
        try:
            with db.transaction() as con:
                if _campo("acao") == "retirar":
                    RDOI.retirar(con, registro_id)
                else:
                    RDOI.gravar(con, registro_id, operacao=_campo("operacao"), matricula=_campo("matricula"),
                                valor=_campo("valor"), data=_campo("data"), tipo_imovel=_campo("tipo_imovel"),
                                endereco=_campo("endereco"), area=_campo("area"), torna=_campo("torna"),
                                folha=_campo("folha"), agora=db.now(), usuario=usuario_nome())
        except RDOI.DoiDoRegistroError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpj_rtd_registro", registro_id=registro_id))
        audit("RG_DOI_GRAVADA", "rg_doi", registro_id, {"acao": _campo("acao") or "gravar"})
        flash("Dados da DOI gravados: a linha aparece na tela da DOI, no mês do registro.", "success")
        return redirect(url_for("rcpj_rtd_registro", registro_id=registro_id))
