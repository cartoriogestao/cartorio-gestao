"""A TELA DO MAPA DO ONR no menu do Registro de Imóveis — `/registro-imoveis/mapa`.

    Registro de Imóveis → Mapa do ONR — polígonos

O QUE A TELA FAZ (a conta e a regra são de `ri_geo.py`)
    - IMPORTA um arquivo (GeoPackage, Shapefile em `.zip`, GeoJSON ou a parcela baixada do SIGEF) e guarda os
      polígonos como PENDENTES, com a origem;
    - ADOTA cada polígono para uma matrícula (ou em lote, as sugestões do atributo do arquivo);
    - MOSTRA a área geodésica ao lado da registrada, o fechamento, os cruzamentos e as sobreposições, e desenha o
      mosaico;
    - GERA o `.gpkg` e o Shapefile com os atributos do Mapa — só o ADMIN baixa, porque o arquivo leva o nome de
      cada proprietário (LGPD) e a baixa fica na auditoria.

O QUE A TELA NÃO FAZ
    Não envia nada ao ONR, não entra no Mapa nem em portal: o arquivo é baixado, e quem o leva à intranet do ONR
    é o oficial. Também não decide a área do arquivo: a escolha entre a registrada e a geodésica é do oficial, e
    sem ela o arquivo não se gera.

POR QUE NÃO HÁ MAPA DE FUNDO
    O desenho é só o mosaico dos perímetros guardados, em SVG, sem imagem de satélite nem serviço externo: nenhum
    dado do cartório sai da máquina para desenhar a tela.
"""
from __future__ import annotations

import html
import json
import math
from typing import Any

import geo_formatos as FORM
import geo_geodesia as GEO
import ri_geo as RG

QUEM_LE = ("ADMIN", "MANAGER", "USER", "AUDITOR")
QUEM_GRAVA = ("ADMIN", "MANAGER", "USER")
#: O arquivo leva o nome de cada proprietário (dado pessoal): é do oficial, com rastro na auditoria.
QUEM_GERA = ("ADMIN",)

MAX_POLIGONOS_NO_DESENHO = 400


def svg_do_mosaico(itens: list[dict], *, largura: int = 760, altura: int = 460) -> str:
    """O SVG dos polígonos: `itens = [{geometria, rotulo, cor, href}]`. Só calcula; texto escapado.

    Projeção simples (longitude × cos da latitude média): serve para olhar, e não para medir — a medida é de
    `geo_geodesia`. Devolve `""` sem polígonos.
    """
    itens = [i for i in itens if i["geometria"]][:MAX_POLIGONOS_NO_DESENHO]
    pontos = [p for i in itens for poligono in i["geometria"] for anel in poligono for p in anel]
    if not pontos:
        return ""
    lat_media = sum(p[1] for p in pontos) / len(pontos)
    escala_x = math.cos(math.radians(lat_media))
    xs = [p[0] * escala_x for p in pontos]
    ys = [p[1] for p in pontos]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    folga = 14
    escala = min((largura - 2 * folga) / max(x1 - x0, 1e-12), (altura - 2 * folga) / max(y1 - y0, 1e-12))

    def tela(p) -> str:
        return f"{folga + (p[0] * escala_x - x0) * escala:.1f},{altura - folga - (p[1] - y0) * escala:.1f}"

    partes = [f'<svg viewBox="0 0 {largura} {altura}" role="img" aria-label="Mosaico dos polígonos guardados" '
              f'style="width:100%;max-width:{largura}px;background:var(--fundo-suave,#f6f7f9);'
              f'border:1px solid var(--linha,#ccd);border-radius:6px">']
    for item in itens:
        cor = item.get("cor") or "#2f6fb5"
        caminho = " ".join("M" + " L".join(tela(p) for p in anel) + " Z"
                           for poligono in item["geometria"] for anel in poligono)
        rotulo = html.escape(str(item.get("rotulo") or ""))
        desenho = (f'<path d="{caminho}" fill="{cor}" fill-opacity="0.28" stroke="{cor}" stroke-width="1.4" '
                   f'fill-rule="evenodd"><title>{rotulo}</title></path>')
        if item.get("href"):
            desenho = f'<a href="{html.escape(item["href"], quote=True)}">{desenho}</a>'
        partes.append(desenho)
    partes.append("</svg>")
    return "".join(partes)


def registrar_rotas(app, db, login_required, roles_required, audit) -> None:
    """Pendura as telas do mapa no app já construído."""
    from flask import Response, abort, flash, redirect, render_template, request, url_for

    def quem() -> tuple[str | None, int | None]:
        nome = app.extensions["usuario_nome"]()
        return nome, app.extensions["usuario_id"]()

    def _numero(texto) -> int | None:
        texto = str(texto or "").strip()
        return int(texto) if texto.isdigit() and len(texto) < 10 else None

    @app.route("/registro-imoveis/mapa")
    @login_required
    @roles_required(*QUEM_LE)
    def ri_geo():
        """A tela: o mosaico, o que importar, o que adotar, a área ao lado da registrada e o arquivo do ONR."""
        from bd_nativo import banco
        cfg = RG.configuracao(db)
        with db.connect() as con:
            todas = RG.lista(con)
            vigentes = [l for l in todas if l["situacao"] == RG.VIGENTE]
            pendentes = [l for l in todas if l["situacao"] == RG.PENDENTE]
            historico = [l for l in todas if l["situacao"] in (RG.SUBSTITUIDA, RG.DESCARTADA)]
            conferencia = RG.conferir_para_o_mapa(con, cfg) if vigentes and GEO.biblioteca_disponivel() else None
            geos = {r["id"]: r for r in banco(con).ler(
                "SELECT id, geom_wkb_hex FROM ri_geometrias WHERE situacao = 'VIGENTE'")}
        desenho = svg_do_mosaico([
            {"geometria": RG._geometria_do_wkb_hex(geos[v["id"]]["geom_wkb_hex"]), "rotulo": v["rotulo"],
             "href": url_for("ri_geo_ver", geometria_id=v["id"])} for v in vigentes if v["id"] in geos])
        for linha in vigentes + pendentes + historico:
            linha["areas"] = RG.comparar_areas(linha, cfg["divergencia_area_pct"])
            linha["lista_de_achados"] = RG.achados_da_linha(linha)
            linha["com_erro"] = RG.tem_erro(linha["lista_de_achados"])
        return render_template(
            "ri_geo.html", vigentes=vigentes, pendentes=pendentes, historico=historico, cfg=cfg,
            conferencia=conferencia, desenho=desenho, regras=RG.REGRAS_DA_AREA, RG=RG,
            biblioteca=GEO.biblioteca_disponivel(), pode_gravar=_papel_grava(), pode_gerar=_papel_gera(),
            rotulo_da_origem=RG.ROTULO_DA_ORIGEM)

    def _papel(*papeis) -> bool:
        return app.extensions["usuario_papel"]() in papeis

    def _papel_grava() -> bool:
        return _papel(*QUEM_GRAVA)

    def _papel_gera() -> bool:
        return _papel(*QUEM_GERA)

    @app.route("/registro-imoveis/mapa/importar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_GRAVA)
    def ri_geo_importar():
        """Guarda as feições do arquivo como PENDENTES. Não adota nenhuma."""
        enviado = request.files.get("arquivo")
        if not enviado or not enviado.filename:
            flash("Escolha o arquivo do polígono (.gpkg, .zip com o Shapefile, ou .geojson).", "danger")
            return redirect(url_for("ri_geo"))
        import tetos_de_entrada as TETOS
        teto = TETOS.valor("zip_bytes")
        dados = enviado.stream.read(teto + 1)
        if len(dados) > teto:
            flash("O arquivo passa do limite de tamanho aceito.", "danger")
            return redirect(url_for("ri_geo"))
        cfg = RG.configuracao(db)
        nome, nome_id = quem()
        try:
            with db.transaction() as con:
                resumo = RG.importar(
                    con, nome=enviado.filename, dados=dados, quem=nome, quem_id=nome_id, agora=db.now(),
                    camada=(request.form.get("camada") or "").strip() or None,
                    epsg=_numero(request.form.get("epsg")),
                    origem_declarada="SIGEF" if request.form.get("e_sigef") == "1" else None,
                    levantamento=request.form.get("levantamento"),
                    responsavel_tecnico=request.form.get("responsavel_tecnico"),
                    tolerancia_fechamento_m=cfg["tolerancia_fechamento_m"])
        except (RG.GeoImportError, GEO.GeoErro) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ri_geo"))
        audit("RI_GEO_IMPORTADO", "RI_GEO_IMPORTACAO", resumo["importacao_id"],
              {"arquivo": enviado.filename, "sha256": resumo["sha256"], "formato": resumo["formato"],
               "origem": resumo["origem"], "epsg": resumo["epsg"], "poligonos": len(resumo["geometrias"]),
               "sugeridas": resumo["sugeridas"], "com_erro": resumo["com_erro"]})
        flash(f"{len(resumo['geometrias'])} polígono(s) guardado(s) como PENDENTES "
              f"({resumo['sugeridas']} com matrícula sugerida pelo arquivo, {resumo['com_erro']} com erro). "
              f"Nenhum foi adotado: confira e adote.", "success")
        for aviso in resumo["avisos"][:10]:
            flash(aviso, "warning")
        return redirect(url_for("ri_geo"))

    @app.route("/registro-imoveis/mapa/<int:geometria_id>")
    @login_required
    @roles_required(*QUEM_LE)
    def ri_geo_ver(geometria_id):
        """Um polígono: de onde veio, as medidas, o que a conferência achou e o desenho com os vizinhos."""
        from bd_nativo import banco
        cfg = RG.configuracao(db)
        with db.connect() as con:
            geo = banco(con).um(
                f"""SELECT g.*, i.arquivo_nome, i.arquivo_sha256, i.formato, i.camada, i.epsg, i.importado_por,
                           i.importado_em, m.area_valor, m.area_unidade, {RG.MAPA._MATRICULA} AS rotulo
                      FROM ri_geometrias g JOIN ri_geo_importacoes i ON i.id = g.importacao_id
                      LEFT JOIN ri_matriculas m ON m.id = g.matricula_id WHERE g.id = %s""", (geometria_id,))
            if not geo:
                abort(404)
            geo = dict(geo)
            geometria = RG.geometria_da_linha(geo)
            sobrepostas = RG.sobreposicoes(con, geometria_id, tolerancia_m2=cfg["tolerancia_sobreposicao_m2"]) \
                if GEO.biblioteca_disponivel() and geo["situacao"] == RG.VIGENTE else []
            vizinhas = banco(con).ler("SELECT id, geom_wkb_hex FROM ri_geometrias WHERE id = ANY(%s)",
                                      ([s["id"] for s in sobrepostas] or [0],))
            historico = RG.da_matricula(con, geo["matricula_id"])["historico"] if geo["matricula_id"] else []
        itens = [{"geometria": geometria, "rotulo": geo["rotulo"] or "este polígono", "cor": "#c0392b"}]
        nomes = {s["id"]: s["matricula"] for s in sobrepostas}
        itens += [{"geometria": RG._geometria_do_wkb_hex(v["geom_wkb_hex"]), "rotulo": f"matrícula {nomes[v['id']]}",
                   "cor": "#2f6fb5", "href": url_for("ri_geo_ver", geometria_id=v["id"])} for v in vizinhas]
        return render_template(
            "ri_geo_ver.html", g=geo, achados=RG.achados_da_linha(geo), areas=RG.comparar_areas(
                geo, cfg["divergencia_area_pct"]), sobrepostas=sobrepostas, desenho=svg_do_mosaico(itens),
            atributos=json.loads(geo["origem_atributos"] or "{}"), historico=historico, RG=RG, cfg=cfg,
            pode_gravar=_papel_grava(), rotulo_da_origem=RG.ROTULO_DA_ORIGEM,
            biblioteca=GEO.biblioteca_disponivel())

    @app.route("/registro-imoveis/mapa/<int:geometria_id>/adotar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_GRAVA)
    def ri_geo_adotar(geometria_id):
        """Faz do polígono o vigente da matrícula digitada. O vigente anterior vira SUBSTITUIDA e fica."""
        nome, nome_id = quem()
        try:
            with db.transaction() as con:
                fichas = RG.achar_matriculas(con, request.form.get("matricula"))
                if not fichas:
                    raise RG.GeoImportError(f"Não achei a matrícula «{request.form.get('matricula', '').strip()}».")
                if len(fichas) > 1:
                    livros = ", ".join(str(f["livro"]) for f in fichas)
                    raise RG.GeoImportError("Há mais de uma ficha com este número (livros "
                                            f"{livros}): o sistema não escolhe por você. Peça ao oficial para "
                                            "conferir a numeração.")
                resultado = RG.adotar(con, geometria_id, fichas[0]["id"], quem=nome, quem_id=nome_id,
                                      agora=db.now())
        except RG.GeoImportError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ri_geo_ver", geometria_id=geometria_id))
        audit("RI_GEO_ADOTADO", "RI_GEOMETRIA", geometria_id,
              {"matricula": resultado["matricula"], "substituiu": resultado["substituiu"]})
        flash(f"Polígono adotado para a matrícula {resultado['matricula']}."
              + (" O que era vigente ficou como SUBSTITUÍDO, no histórico." if resultado["substituiu"] else ""),
              "success")
        for aviso in resultado["avisos"]:
            flash(aviso, "warning")
        return redirect(url_for("ri_geo_ver", geometria_id=geometria_id))

    @app.route("/registro-imoveis/mapa/adotar-sugestoes", methods=["POST"])
    @login_required
    @roles_required(*QUEM_GRAVA)
    def ri_geo_adotar_sugestoes():
        """Adota as PENDENTES sem erro cuja matrícula sugerida ainda não tem polígono. Não troca nenhum vigente."""
        nome, nome_id = quem()
        with db.transaction() as con:
            saida = RG.adotar_sugestoes(con, quem=nome, quem_id=nome_id, agora=db.now())
        audit("RI_GEO_ADOTADO_EM_LOTE", "RI_GEOMETRIA", None,
              {"adotadas": saida["adotadas"], "deixadas": saida["deixadas"]})
        flash(f"{len(saida['adotadas'])} polígono(s) adotado(s); {len(saida['deixadas'])} ficaram "
              f"({'; '.join(sorted({d['motivo'] for d in saida['deixadas']})) or 'nenhum'}).", "success")
        return redirect(url_for("ri_geo"))

    @app.route("/registro-imoveis/mapa/<int:geometria_id>/descartar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_GRAVA)
    def ri_geo_descartar(geometria_id):
        nome, _ = quem()
        try:
            with db.transaction() as con:
                RG.descartar(con, geometria_id, request.form.get("motivo"), quem=nome, agora=db.now())
        except RG.GeoImportError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ri_geo_ver", geometria_id=geometria_id))
        audit("RI_GEO_DESCARTADO", "RI_GEOMETRIA", geometria_id, {"motivo": request.form.get("motivo")})
        flash("Polígono descartado. Ele continua guardado, com o motivo.", "success")
        return redirect(url_for("ri_geo"))

    @app.route("/registro-imoveis/mapa/regra-da-area", methods=["POST"])
    @login_required
    @roles_required(*QUEM_GERA)
    def ri_geo_regra_da_area():
        """A escolha do oficial: qual área vai em AREA_HA. Guarda também as tolerâncias de trabalho."""
        regra = (request.form.get("regra") or "").strip().upper()
        if regra not in RG.REGRAS_DA_AREA:
            flash("Escolha uma das três respostas.", "danger")
            return redirect(url_for("ri_geo"))

        def numero(chave: str, padrao: float) -> str:
            try:
                valor = float(str(request.form.get(chave) or "").replace(",", "."))
                return str(valor) if 0 <= valor <= 1_000_000 else str(padrao)
            except ValueError:
                return str(padrao)

        antes = RG.configuracao(db)
        db.set_settings({RG.CHAVE_REGRA_DA_AREA: regra,
                         RG.CHAVE_TOLERANCIA_FECHAMENTO: numero("tolerancia_fechamento_m",
                                                                antes["tolerancia_fechamento_m"]),
                         RG.CHAVE_TOLERANCIA_SOBREPOSICAO: numero("tolerancia_sobreposicao_m2",
                                                                  antes["tolerancia_sobreposicao_m2"]),
                         RG.CHAVE_DIVERGENCIA_DA_AREA: numero("divergencia_area_pct",
                                                              antes["divergencia_area_pct"])})
        audit("RI_GEO_REGRA_DA_AREA", "RI_MAPA_ONR", None, {"antes": antes["regra_da_area"] or None, "depois": regra})
        flash("Regra da área do arquivo gravada.", "success")
        return redirect(url_for("ri_geo"))

    def _baixar(formato: str):
        cfg = RG.configuracao(db)
        try:
            with db.connect() as con:
                if formato == "gpkg":
                    conteudo, conferencia = RG.gerar_gpkg(con, cfg)
                    avisos: list[str] = []
                else:
                    conteudo, conferencia, avisos = RG.gerar_shapefile(con, cfg)
        except (RG.GeoImportError, GEO.GeoErro) as erro:
            flash(str(erro), "danger")
            return redirect(url_for("ri_geo"))
        audit("RI_GEO_EXPORTADO", "RI_MAPA_ONR", None,
              {"formato": formato, "poligonos": conferencia["vao"], "de_fora": conferencia["ficam"],
               "regra_da_area": cfg["regra_da_area"], "cortes": len(avisos)})
        if formato == "gpkg":
            return Response(conteudo, mimetype="application/geopackage+sqlite3",
                            headers={"Content-Disposition": "attachment; filename=mapa_onr.gpkg"})
        return Response(conteudo, mimetype="application/zip",
                        headers={"Content-Disposition": "attachment; filename=mapa_onr_shapefile.zip"})

    @app.route("/registro-imoveis/mapa/mapa_onr.gpkg")
    @login_required
    @roles_required(*QUEM_GERA)
    def ri_geo_baixar_gpkg():
        """O GeoPackage para a intranet do ONR. Só o ADMIN; a baixa fica na auditoria."""
        return _baixar("gpkg")

    @app.route("/registro-imoveis/mapa/mapa_onr_shapefile.zip")
    @login_required
    @roles_required(*QUEM_GERA)
    def ri_geo_baixar_shapefile():
        """O Shapefile (`.zip` com `.shp .shx .dbf .prj .cpg`). Só o ADMIN; a baixa fica na auditoria."""
        return _baixar("shapefile")
