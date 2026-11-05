"""AS TELAS DOS LIVROS DO RCPJ E DO RTD: uma aba por livro, como a lei os nomeia.

    «Não temos aba do livro de protocolo, nem nos demais livros obrigatórios.»
                                                       — o oficial, 01/11/2026

O domínio mora em `rg_livros` e em `rg_normas`; aqui a rota só liga os fios. Livro é
leitura: lavrar continua nas telas de sempre, e o que estas rotas gravam é o cadastro em
volta do registro (as partes do indicador e os bens do Livro E).

O NOME DAS ROTAS COMEÇA COM `rcpj_rtd` porque é o prefixo que diz de que módulo é a tela.
"""
from __future__ import annotations

from datetime import date
from html import escape

from flask import Response, flash, redirect, render_template, request, url_for

import ri_odt as RODT
import rg_livros as RGL
import rg_normas as NORMAS
import rg_registro as RG
import rg_titulo as TIT
from ri_odt import gerar_odt, html_para_odf
from rg_web import QUEM_OPERA, QUEM_QUALIFICA
from ri_web import data_por_extenso
from serventia import dados as dados_serventia

# As colunas de cada tipo de livro: a mesma lista desenha a tela e o papel.
COLUNAS = {
    RGL.PROTOCOLO: (("numero", "N. de ordem"), ("data_br", "Apresentação"), ("natureza", "Natureza"),
                    ("especie_rotulo", "Espécie de lançamento"), ("apresentante", "Apresentante"),
                    ("lancamento", "Lançamento (art. 968)"), ("pendencia", "Pendência")),
    RGL.ATOS: (("registro_numero", "Registro"), ("tipo", "Ato"), ("numero_ordem", "N. de ordem"),
               ("data_br", "Data"), ("volume", "Volume"), ("folha_rotulo", "Folha"),
               ("requerente_nome", "Requerente"), ("natureza", "Natureza"), ("selo", "Selo")),
    RGL.INDICE: (("nome", "Nome"), ("documento_formatado", "CPF ou CNPJ"), ("papel", "Papel"),
                 ("serie_nome", "Livro"), ("numero", "Registro"), ("data_br", "Data")),
    RGL.INDICADOR_REAL: (("descricao", "Bem"), ("especie", "Espécie"), ("identificacao", "Identificação"),
                         ("onus", "Direitos e ônus"), ("serie_nome", "Livro"), ("numero", "N. de ordem"),
                         ("baixa", "Baixa")),
    RGL.AUXILIAR: (("registro_numero", "Registro"), ("volume", "Volume"), ("data_br", "Data"),
                   ("requerente_nome", "Requerente"), ("copias", "Cópias")),
    RGL.INDICADOR_F: (("numero", "Registro"), ("nome", "Apresentante"),
                      ("documento_formatado", "CPF ou CNPJ"), ("data_br", "Data")),
}


def _data_br(valor) -> str:
    dia = str(valor or "")[:10]
    return f"{dia[8:10]}/{dia[5:7]}/{dia[:4]}" if len(dia) == 10 else ""


def _atribuicao(valor) -> int:
    try:
        codigo = int(valor)
    except (TypeError, ValueError):
        return TIT.RTD
    return codigo if codigo in TIT.ATRIBUICOES else TIT.RTD


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    """Pendura as telas dos livros no app já construído."""

    usuario_nome = app.extensions["usuario_nome"]

    def sv() -> dict:
        return dados_serventia(db.get_settings)

    def _campo(nome: str) -> str:
        return (request.form.get(nome) or "").strip()

    def _linhas(con, livro: dict, atribuicao: int, *, de: str, ate: str, busca: str,
                ordem: str, pagina: int) -> dict:
        """As linhas da aba, já prontas para as colunas dela. Só LÊ."""
        total = paginas = None
        if livro["tipo"] == RGL.PROTOCOLO:
            linhas = RGL.linhas_do_protocolo(con, atribuicao, de=de, ate=ate, busca=busca)
            for x in linhas:
                x["data_br"] = _data_br(x["data_apresentacao"])
        elif livro["tipo"] == RGL.ATOS:
            pedido = RGL.atos_do_livro(con, livro["serie"], de=de, ate=ate, busca=busca, pagina=pagina)
            linhas, total, paginas = pedido["linhas"], pedido["total"], pedido["paginas"]
            for x in linhas:
                x["data_br"] = _data_br(x["data_ato"])
                x["folha_rotulo"] = x["rotulo"] or x["folha"]
        elif livro["tipo"] == RGL.AUXILIAR:
            pedido = RGL.copias_do_livro_b(con, busca=busca, pagina=pagina)
            linhas, total, paginas = pedido["linhas"], pedido["total"], pedido["paginas"]
            for x in linhas:
                x["data_br"] = _data_br(x["data_ato"])
        elif livro["tipo"] == RGL.INDICE:
            # O Livro F não dá publicidade (CN-MA art. 957, § 5º): quem o procura é o Livro G.
            series = ("TD_B", "TD_C") if atribuicao == TIT.RTD else ()
            linhas = RGL.indicador_pessoal(con, atribuicao=atribuicao, series=series, busca=busca, ordem=ordem)
            for x in linhas:
                x["data_br"] = _data_br(x["data_ato"])
        elif livro["tipo"] == RGL.INDICADOR_F:
            linhas = RGL.indicador_pessoal(con, series=("TD_F",), busca=busca, ordem=ordem)
            for x in linhas:
                x["data_br"] = _data_br(x["data_ato"])
        else:
            linhas = RGL.indicador_real(con, busca=busca)
            for x in linhas:
                x["baixa"] = f"{_data_br(x['baixado_em'])}: {x['baixa_motivo']}" if x["baixado_em"] else ""
        return {"linhas": linhas, "total": len(linhas) if total is None else total,
                "paginas": paginas or 1}

    def _papel_do_livro(livro: dict, atribuicao: int, linhas: list[dict], *, de: str, ate: str) -> bytes:
        s = sv()
        cabeca = "".join(f"<th>{escape(r)}</th>" for _, r in COLUNAS[livro["tipo"]])
        corpo = "".join(
            "<tr>" + "".join(
                f"<td>{escape(str(x.get(c) if x.get(c) is not None else ''))}</td>"
                for c, _ in COLUNAS[livro["tipo"]]) + "</tr>"
            for x in linhas)
        periodo = (f"<p align=\"center\">De {_data_br(de) or 'o início'} a {_data_br(ate) or 'hoje'}</p>"
                   if de or ate else "")
        html = (f'<p align="center"><b>{escape(livro["nome"]).upper()}</b></p>'
                f'<p align="center">{escape(TIT.NOME_DA_ATRIBUICAO[atribuicao])} — '
                f'{escape(livro["fonte"])}</p>{periodo}'
                f'<table border="1"><tr>{cabeca}</tr>{corpo}</table>')
        assinatura = (f'<p></p><p align="center">_________________________________</p>'
                      f'<p align="center">{escape(s["serventia_titular"])}</p>'
                      f'<p align="center">{escape(s["serventia_titulo"])}</p>')
        cab_odf, cab_imgs = RODT.cabecalho_certidao_completo_odf(s)
        return gerar_odt(html_para_odf(html + assinatura), titulo=livro["nome"],
                         cabecalho_odf=cab_odf, imagens=dict(cab_imgs or {}) or None,
                         cabecalho_altura_min="2.0cm", cabecalho_margem_baixo="0.25cm",
                         cabecalho_borda=False)

    @app.route("/rcpj-rtd/livros")
    @login_required
    def rcpj_rtd_livros():
        """Os livros de uma atribuição, um por aba. Com `?formato=odt` sai o papel. Só LÊ."""
        atribuicao = _atribuicao(request.args.get("atribuicao"))
        livro = RGL.livro_pedido(atribuicao, request.args.get("livro"))
        de = (request.args.get("de") or "")[:10]
        ate = (request.args.get("ate") or "")[:10]
        busca = (request.args.get("busca") or "").strip()
        ordem = "cronologica" if request.args.get("ordem") == "cronologica" else "alfabetica"
        try:
            pagina = max(1, int(request.args.get("pagina") or 1))
        except ValueError:
            pagina = 1
        hoje = db.now()[:10]
        with db.connect() as con:
            if request.args.get("formato") == "odt":
                dados = _linhas(con, livro, atribuicao, de=de, ate=ate, busca=busca, ordem=ordem, pagina=1)
                linhas = dados["linhas"]
                for p in range(2, dados["paginas"] + 1):
                    linhas += _linhas(con, livro, atribuicao, de=de, ate=ate, busca=busca,
                                      ordem=ordem, pagina=p)["linhas"]
                papel = _papel_do_livro(livro, atribuicao, linhas, de=de, ate=ate)
                audit("RG_LIVRO_ODT", "rg_registros", 0,
                      {"atribuicao": atribuicao, "livro": livro["chave"], "linhas": len(linhas)})
                return Response(
                    papel, mimetype="application/vnd.oasis.opendocument.text",
                    headers={"Content-Disposition":
                             f'attachment; filename="livro-{atribuicao}-{livro["chave"]}.odt"'})
            dados = _linhas(con, livro, atribuicao, de=de, ate=ate, busca=busca, ordem=ordem, pagina=pagina)
            abas = [{**x, "quantos": RGL.quantos_no_livro(con, x, atribuicao)} for x in RGL.livros_de(atribuicao)]
            lugar = RGL.lugar_do_livro(con, livro["serie"])
            pendentes = dias_abertos = None
            if livro["tipo"] == RGL.PROTOCOLO:
                pendentes = RGL.pendentes_ao_fim_do_dia(con, atribuicao, hoje)
                dias_abertos = [_data_br(d) for d in RGL.dias_sem_termo(con, livro["serie"])]
        return render_template(
            "rcpj_rtd_livros.html", atribuicao=atribuicao, livro=livro, abas=abas,
            linhas=dados["linhas"], total=dados["total"], paginas=dados["paginas"], pagina=pagina,
            colunas=COLUNAS[livro["tipo"]], de=de, ate=ate, busca=busca, ordem=ordem, lugar=lugar,
            pendentes=pendentes, dias_abertos=dias_abertos,
            atribuicoes=[{"codigo": c, "nome": TIT.NOME_DA_ATRIBUICAO[c]} for c in TIT.ATRIBUICOES],
            nome_da_atribuicao=TIT.NOME_DA_ATRIBUICAO[atribuicao])

    @app.route("/rcpj-rtd/o-que-conferir")
    @login_required
    def rcpj_rtd_normas():
        """A lista de conferência, e a conferência de um nome de pessoa jurídica. Só LÊ."""
        atribuicao = _atribuicao(request.args.get("atribuicao"))
        nome = (request.args.get("nome") or "").strip()
        reservadas = parecidos = None
        if nome:
            reservadas = NORMAS.avisos_do_nome(nome)
            with db.connect() as con:
                parecidos = NORMAS.nomes_parecidos(con, nome)
        return render_template(
            "rcpj_rtd_normas.html", atribuicao=atribuicao, nome=nome, reservadas=reservadas,
            parecidos=parecidos, gerais=NORMAS.regras_gerais(atribuicao),
            por_natureza=[r for _, a, r in NORMAS.POR_NATUREZA if a == atribuicao],
            atribuicoes=[{"codigo": c, "nome": TIT.NOME_DA_ATRIBUICAO[c]} for c in TIT.ATRIBUICOES],
            nome_da_atribuicao=TIT.NOME_DA_ATRIBUICAO[atribuicao])

    @app.route("/rcpj-rtd/titulo/<int:titulo_id>/recibo")
    @login_required
    def rcpj_rtd_titulo_recibo(titulo_id: int):
        """O recibo do art. 974, § 1º, com a anotação do art. 966, § 2º. Só LÊ."""
        with db.connect() as con:
            titulo = TIT.um(con, titulo_id)
        if not titulo:
            flash("Título não encontrado.", "danger")
            return redirect(url_for("rcpj_rtd_titulos"))
        s = sv()
        return render_template(
            "rcpj_rtd_recibo.html", t=titulo, sv=s, data_br=_data_br,
            nome_da_atribuicao=TIT.NOME_DA_ATRIBUICAO[int(titulo["atribuicao"])],
            anotacao=RGL.anotacao_no_titulo(titulo),
            data_extenso=data_por_extenso(date.fromisoformat(db.now()[:10])))

    # ------------------------------------------- as partes e os bens do registro

    def _de_volta(registro_id: int):
        return redirect(url_for("rcpj_rtd_registro", registro_id=registro_id))

    @app.route("/rcpj-rtd/<int:registro_id>/partes", methods=["POST"])
    @roles_required(*QUEM_OPERA)
    def rcpj_rtd_parte_incluir(registro_id: int):
        """Põe uma pessoa no indicador daquele registro. ESCREVE."""
        try:
            with db.transaction() as con:
                feito = RGL.incluir_parte(
                    con, registro_id, nome=_campo("nome"), documento=_campo("documento"),
                    papel=_campo("papel"), participacao=_campo("participacao"),
                    doi_lado=_campo("doi_lado"), agora=db.now(), usuario=usuario_nome(),
                    domicilio_cidade=_campo("domicilio_cidade"),
                    domicilio_uf=_campo("domicilio_uf"))
        except (RGL.LivroDoRegistroError, RG.RgError) as erro:
            flash(str(erro), "danger")
            return _de_volta(registro_id)
        audit("RG_PARTE_INCLUIDA", "rg_partes", feito["parte_id"],
              {"registro_id": registro_id, "papel": _campo("papel")})
        flash(f"{feito['nome']} entrou no indicador deste registro.", "success")
        return _de_volta(registro_id)

    @app.route("/rcpj-rtd/<int:registro_id>/partes/<int:parte_id>/retirar", methods=["POST"])
    @roles_required(*QUEM_QUALIFICA)
    def rcpj_rtd_parte_retirar(registro_id: int, parte_id: int):
        """Tira a pessoa do indicador, com o motivo escrito. ESCREVE. A linha fica."""
        try:
            with db.transaction() as con:
                feito = RGL.retirar_parte(con, registro_id, parte_id, motivo=_campo("motivo"),
                                          agora=db.now(), usuario=usuario_nome())
        except RGL.LivroDoRegistroError as erro:
            flash(str(erro), "danger")
            return _de_volta(registro_id)
        audit("RG_PARTE_RETIRADA", "rg_partes", parte_id,
              {"registro_id": registro_id, "motivo": feito["motivo"]})
        flash(f"{feito['nome']} saiu do indicador; o motivo ficou gravado.", "success")
        return _de_volta(registro_id)

    @app.route("/rcpj-rtd/<int:registro_id>/bens", methods=["POST"])
    @roles_required(*QUEM_OPERA)
    def rcpj_rtd_bem_incluir(registro_id: int):
        """Lança um bem móvel no Livro E. ESCREVE."""
        try:
            with db.transaction() as con:
                feito = RGL.incluir_bem(
                    con, registro_id, descricao=_campo("descricao"), identificacao=_campo("identificacao"),
                    especie=_campo("especie"), onus=_campo("onus"), agora=db.now(), usuario=usuario_nome())
        except RGL.LivroDoRegistroError as erro:
            flash(str(erro), "danger")
            return _de_volta(registro_id)
        audit("RG_BEM_INCLUIDO", "rg_bens", feito["bem_id"], {"registro_id": registro_id})
        flash("Bem lançado no Livro E.", "success")
        return _de_volta(registro_id)

    @app.route("/rcpj-rtd/<int:registro_id>/bens/<int:bem_id>/baixar", methods=["POST"])
    @roles_required(*QUEM_QUALIFICA)
    def rcpj_rtd_bem_baixar(registro_id: int, bem_id: int):
        """Dá baixa no bem, com o motivo escrito. ESCREVE. A linha fica no Livro E."""
        try:
            with db.transaction() as con:
                feito = RGL.baixar_bem(con, registro_id, bem_id, motivo=_campo("motivo"),
                                       agora=db.now(), usuario=usuario_nome())
        except RGL.LivroDoRegistroError as erro:
            flash(str(erro), "danger")
            return _de_volta(registro_id)
        audit("RG_BEM_BAIXADO", "rg_bens", bem_id,
              {"registro_id": registro_id, "motivo": feito["motivo"]})
        flash("Baixa gravada no Livro E.", "success")
        return _de_volta(registro_id)
