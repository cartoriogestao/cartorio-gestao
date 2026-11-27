"""A ROTINA DA SERVENTIA NA TELA — 26/11/2026 (`rotina_da_casa`).

    «cadastre nossa rotina lá, como se fosse para eu, oficial, delegar tarefas
    de manutenção do cartório para quem não faz ideia do que o cartório faz.»
                                                    — o oficial, 26/11/2026

TRÊS LUGARES, UMA ROTINA SÓ
    1. A CHECKLIST DO DIA (`gestor_checklist`, em `conformidade_web`): o bloco
       «Rotina do dia» vem no alto de cada área, antes dos achados do gestor,
       com o «Como fazer» de cada item e o botão «Feito».
    2. MINHA ROTINA (`rotina_minha`, em Trabalho): para qualquer pessoa
       logada, também o escrevente, o que ela tem para hoje e o atrasado, como
       responsável ou suplente, com o mesmo «Como fazer» e o mesmo «Feito».
    3. O CADASTRO «ROTINA DA SERVENTIA» (`rotina_cadastro`, em Gestão): o
       oficial e o gerente cadastram, editam, desativam (com motivo) e
       reativam; o auditor lê e não grava. O TI entra como o ADMIN (`papeis`).
    O item de destino ESCREVENTE (A011, 27/11/2026) não vai ao lugar 1: fica
    só em «Minha rotina» do responsável e do suplente. O destino se escolhe e
    se troca no formulário, e o cadastro o mostra em cada linha.

O «FEITO» NÃO MEXE NO SEMÁFORO
    Ele grava quem fez, quando, o resultado e a observação (e a prova, se
    houver) — e só. A cor oficial da área (`conformidade.medir`) continua
    sendo a dos achados do gestor.

AUDITORIA EM TODA ESCRITA
    ROTINA_CRIADA, ROTINA_ALTERADA, ROTINA_DESATIVADA, ROTINA_REATIVADA e
    ROTINA_FEITA, sempre com o código do item. `audit()` abre a transação
    dele: chama-se depois do `with db.transaction()`. O «feito» vai à
    auditoria LOGO depois do COMMIT, antes de guardar o arquivo da prova: o
    arquivo que falha (disco cheio, pasta sem permissão) não deixa feito sem
    trilha nem a tela em erro — vira aviso e ROTINA_PROVA_FALHOU; o que entra
    vira ROTINA_PROVA_ANEXADA.
"""
from __future__ import annotations

from datetime import date
from typing import Callable

from flask import abort, flash, redirect, render_template, request, url_for

import navegacao as NAV
import papeis as PAP
import quem_resolve_web as QRW
import rotina_da_casa as RT
from storage import save_upload

#: Os campos do formulário que vão como vieram (as listas de caixa vão à parte).
_CAMPOS_DO_FORMULARIO = ("codigo", "area", "titulo", "para_que", "como_fazer", "pronto_quando",
                         "se_der_errado", "prova", "onde_endpoint", "onde_url", "base_legal",
                         "periodicidade", "dias_mes", "dia_util", "horario", "destino",
                         "responsavel_id", "suplente_id", "prioridade", "ordem")


def contexto() -> dict:
    """O que os moldes da rotina usam, além dos itens."""
    return {"rotina_resultados": RT.RESULTADOS, "rotina_areas": RT.ROTULO_DA_AREA,
            "rotina_ok": RT.OK, "hoje_da_rotina": date.today().isoformat()}


def telas_do_menu() -> list[tuple[str, str]]:
    """As telas do menu que abrem sem número: (endpoint, «Módulo › Seção › Tela»)."""
    curto = {m["chave"]: m["curto"] for m in NAV.MODULOS_DA_BARRA}
    vistas, saida = set(), []
    for e in NAV.entradas("ADMIN"):
        if e["args"] or e.get("atalho") or e["endpoint"] in vistas:
            continue
        vistas.add(e["endpoint"])
        caminho = " › ".join(x for x in (curto.get(e["modulo"], e["modulo"]), e["secao"],
                                         e["rotulo"]) if x and not x.startswith("·"))
        saida.append((e["endpoint"], caminho))
    return saida


def preparar(itens: list[dict], *, papel: str, usuario_id: int | None,
             abre: Callable[[str], bool], gerar_url: Callable[..., str] = url_for) -> list[dict]:
    """Põe em cada item o que depende de quem olha: se marca «feito», e o link
    da tela onde se faz (só para quem a abre; endereço que não se monta some)."""
    nomes = dict(telas_do_menu())
    for x in itens:
        x["pode_marcar"] = (RT.pode_marcar(x, papel, usuario_id) and x.get("ativo", True)
                            and bool(x.get("referencias_marcaveis")))
        x["onde_link"], x["onde_rotulo"] = None, None
        endpoint = x.get("onde_endpoint")
        if endpoint:
            x["onde_rotulo"] = nomes.get(endpoint, endpoint)
            try:
                if abre(endpoint):
                    x["onde_link"] = gerar_url(endpoint)
            except Exception:                              # noqa: BLE001 — link que falha some
                x["onde_link"] = None
    return itens


def _agrupar(itens: list[dict]) -> list[tuple[str, str, list[tuple[str, str, list[dict]]]]]:
    """[(área, rótulo, [(periodicidade, rótulo, itens)])], na ordem das áreas."""
    saida = []
    for area, rotulo in RT.AREAS:
        da_area = [x for x in itens if x["area"] == area]
        if not da_area:
            continue
        grupos = [(p, rp, [x for x in da_area if x["periodicidade"] == p])
                  for p, rp in RT.PERIODICIDADES]
        saida.append((area, rotulo, [g for g in grupos if g[2]]))
    return saida


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    current_user = app.extensions["current_user"]
    usuario_nome = app.extensions["usuario_nome"]
    usuario_id = app.extensions["usuario_id"]
    archive_root = app.extensions.get("archive_root")

    def _abre_para(papel: str) -> Callable[[str], bool]:
        """A tela «onde fazer» abre para esta pessoa? A régua do anexo e do menu."""
        abre_pela_tela = app.extensions.get("abre_pela_tela")
        funcao = app.extensions.get("funcao_de_quem_esta_logado")

        def abre(endpoint: str) -> bool:
            if endpoint not in app.view_functions:
                return False
            if abre_pela_tela is None:
                return True
            return bool(abre_pela_tela(endpoint, papel, funcao() if funcao else None))
        return abre

    def _conferir_tela(endpoint: str | None) -> str | None:
        """A tela «onde fazer» existe e abre sem número? Senão, a frase."""
        endpoint = (endpoint or "").strip()
        if not endpoint:
            return None
        if endpoint not in app.view_functions:
            return (f"A tela «{endpoint}» não existe no sistema: escolha uma da lista, ou deixe "
                    "em branco e use o endereço de fora.")
        try:
            url_for(endpoint)
        except Exception:                                  # noqa: BLE001
            return (f"A tela «{endpoint}» precisa de um número (é a ficha de alguma coisa): "
                    "escolha a lista de onde se chega nela.")
        return None

    def _dados_do_formulario() -> dict:
        f = request.form
        dados = {c: f.get(c, "") for c in _CAMPOS_DO_FORMULARIO}
        dados["dias_semana"] = ",".join(f.getlist("dias_semana"))
        dados["meses"] = ",".join(f.getlist("meses"))
        return dados

    def _formulario(item: dict | None, valores: dict, problemas: list[str]):
        with db.connect() as con:
            pessoas = RT.pessoas(con)
            # A PESSOA QUE O ITEM JÁ TEM e saiu da lista (inativa, auditor):
            # aparece marcada, para o servidor pedir outra em vez de apagá-la.
            ids = {int(p["id"]) for p in pessoas}
            fora = {}
            for campo in ("responsavel_id", "suplente_id"):
                extra = RT.pessoa_do_formulario(con, valores.get(campo))
                if extra and extra["id"] not in ids:
                    fora[extra["id"]] = extra
        return render_template(
            "rotina_form.html", item=item, v=valores, problemas=problemas, pessoas=pessoas,
            pessoas_fora=list(fora.values()),
            areas=RT.AREAS, periodicidades=RT.PERIODICIDADES, dias_semana=RT.DIAS_DA_SEMANA,
            destinos=RT.DESTINOS, destino_padrao=RT.TI_ADMIN,
            meses=RT.NOMES_DOS_MESES, prioridades=RT.PRIORIDADES, telas=telas_do_menu(),
            semana_marcada={int(x) for x in str(valores.get("dias_semana") or "").split(",") if x.strip().isdigit()},
            meses_marcados={int(x) for x in str(valores.get("meses") or "").split(",") if x.strip().isdigit()})

    def _detalhes(item: dict, **mais) -> dict:
        return {"codigo": item["codigo"], "titulo": item["titulo"], "area": item["area"],
                "periodicidade": item["periodicidade"], "destino": item.get("destino"), **mais}

    # ------------------------------------------------------------- o cadastro

    @app.route("/administrativo/rotina")
    @login_required
    @roles_required(*RT.QUEM_VE_O_CADASTRO)
    def rotina_cadastro():
        """A rotina da serventia: por área e periodicidade, com busca. SÓ LÊ."""
        u = current_user()
        area = (request.args.get("area") or "").strip().upper() or None
        if area not in RT.ROTULO_DA_AREA:
            area = None
        busca = (request.args.get("q") or "").strip()[:100]
        inativas = request.args.get("ver") == "inativas"
        with db.connect() as con:
            itens = RT.listar(con, date.today(), area=area, busca=busca, ativas=not inativas)
            total_inativas = RT.contar(con, ativas=False)
            total_ativas = RT.contar(con)
        papel = u["role"]
        preparar(itens, papel=papel, usuario_id=usuario_id(), abre=_abre_para(papel))
        return render_template(
            "rotina_cadastro.html", grupos=_agrupar(itens), total=len(itens), area=area,
            busca=busca, inativas=inativas, total_inativas=total_inativas,
            total_ativas=total_ativas, areas=RT.AREAS,
            pode=PAP.equivale_a(u, RT.QUEM_CADASTRA), motivo_maximo=RT.MOTIVO_MAXIMO,
            **contexto())

    @app.route("/administrativo/rotina/nova", methods=["GET", "POST"])
    @login_required
    @roles_required(*RT.QUEM_CADASTRA)
    def rotina_nova():
        """Cadastra um item da rotina."""
        if request.method == "GET":
            area = (request.args.get("area") or "").strip().upper()
            return _formulario(None, {**dict.fromkeys(RT.CAMPOS, ""),
                                      "area": area if area in RT.ROTULO_DA_AREA else "",
                                      "periodicidade": "DIARIA", "destino": RT.TI_ADMIN,
                                      "prioridade": 2, "ordem": 100}, [])
        valores = _dados_do_formulario()
        erro = _conferir_tela(valores["onde_endpoint"])
        if erro:
            return _formulario(None, valores, [erro])
        try:
            with db.transaction() as con:
                rotina_id = RT.criar(con, valores, por=usuario_nome())
                item = RT.uma(con, rotina_id)
                primeiro = RT.proximo_prazo(con, item)
        except RT.RotinaError as recusa:
            return _formulario(None, valores, recusa.problemas)
        audit("ROTINA_CRIADA", "ge_rotina", rotina_id, _detalhes(item))
        onde = ("só em «Minha rotina» do responsável e do suplente"
                if item.get("destino") == RT.ESCREVENTE
                else "na Checklist do dia e em «Minha rotina» de quem responde por ela")
        flash(f"Rotina «{item['titulo']}» cadastrada. Ela vale de hoje em diante: o que venceu "
              "antes não é cobrado." + (
                  f" O primeiro vencimento é {primeiro:%d/%m/%Y}; a partir dele ela aparece "
                  f"{onde}." if primeiro else ""), "success")
        return redirect(url_for("rotina_cadastro", area=item["area"]) + f"#rotina-{rotina_id}")

    @app.route("/administrativo/rotina/<int:rotina_id>/editar", methods=["GET", "POST"])
    @login_required
    @roles_required(*RT.QUEM_CADASTRA)
    def rotina_editar(rotina_id):
        """Edita um item da rotina. O código não muda."""
        with db.connect() as con:
            item = RT.uma(con, rotina_id)
        if not item:
            abort(404)
        if request.method == "GET":
            return _formulario(item, dict(item), [])
        valores = _dados_do_formulario()
        valores["codigo"] = item["codigo"]
        erro = _conferir_tela(valores["onde_endpoint"])
        if erro:
            return _formulario(item, valores, [erro])
        try:
            with db.transaction() as con:
                mudou = RT.atualizar(con, rotina_id, valores, por=usuario_nome())
                novo = RT.uma(con, rotina_id)
        except RT.RotinaError as recusa:
            return _formulario(item, valores, recusa.problemas)
        if mudou:
            audit("ROTINA_ALTERADA", "ge_rotina", rotina_id, _detalhes(novo, campos=mudou))
            flash(f"Rotina «{novo['titulo']}» alterada.", "success")
        else:
            flash("Nada mudou: a rotina já estava assim.", "info")
        return redirect(url_for("rotina_cadastro", area=novo["area"]) + f"#rotina-{rotina_id}")

    def _voltar_ao_cadastro():
        area = (request.form.get("area") or "").strip().upper()
        ver = "inativas" if request.form.get("ver") == "inativas" else None
        return redirect(url_for("rotina_cadastro", area=area if area in RT.ROTULO_DA_AREA else None,
                                ver=ver))

    @app.route("/administrativo/rotina/<int:rotina_id>/desativar", methods=["POST"])
    @login_required
    @roles_required(*RT.QUEM_CADASTRA)
    def rotina_desativar(rotina_id):
        """Tira o item da rotina, com motivo. Nada se apaga."""
        try:
            with db.transaction() as con:
                r = RT.desativar(con, rotina_id, por=usuario_nome(),
                                 motivo=request.form.get("motivo"))
        except RT.RotinaError as recusa:
            if str(recusa) == "Rotina não encontrada.":
                abort(404)
            flash(str(recusa), "warning")
            return _voltar_ao_cadastro()
        if r["gravou"]:
            audit("ROTINA_DESATIVADA", "ge_rotina", rotina_id,
                  {"codigo": r["codigo"], "motivo": r["motivo"]})
            flash(f"Rotina {r['codigo']} desativada: sai da Checklist do dia e de «Minha "
                  "rotina». Ela fica em «Ver as desativadas», com o motivo.", "success")
        else:
            flash(f"A rotina {r['codigo']} já estava desativada.", "info")
        return _voltar_ao_cadastro()

    @app.route("/administrativo/rotina/<int:rotina_id>/reativar", methods=["POST"])
    @login_required
    @roles_required(*RT.QUEM_CADASTRA)
    def rotina_reativar(rotina_id):
        """Devolve o item à rotina."""
        try:
            with db.transaction() as con:
                r = RT.reativar(con, rotina_id, por=usuario_nome())
        except RT.RotinaError:
            abort(404)
        if r["gravou"]:
            audit("ROTINA_REATIVADA", "ge_rotina", rotina_id,
                  {"codigo": r["codigo"], "motivo_anterior": r["motivo_anterior"],
                   "vale_desde": r["vale_desde"]})
            flash(f"Rotina {r['codigo']} reativada. Ela vale de hoje em diante: o tempo em que "
                  "esteve desativada não é cobrado.", "success")
        else:
            flash(f"A rotina {r['codigo']} já estava ativa.", "info")
        return _voltar_ao_cadastro()

    # ------------------------------------------------------------- o «feito»

    def _voltar_do_feito(rotina_id: int):
        area = (request.form.get("area") or "").strip().upper()
        area = area if area in RT.ROTULO_DA_AREA else None
        if request.form.get("voltar") == "checklist":
            return redirect(url_for("gestor_checklist", area=area) + "#rotina")
        return redirect(url_for("rotina_minha") + f"#rotina-{int(rotina_id)}")

    @app.route("/administrativo/rotina/<int:rotina_id>/feito", methods=["POST"])
    @login_required
    def rotina_feito(rotina_id):
        """«Feito» num vencimento: quem, quando, resultado, observação e a prova."""
        u = current_user()
        papel, uid = u["role"], usuario_id()
        with db.connect() as con:
            item = RT.uma(con, rotina_id)
        if not item:
            abort(404)
        if not RT.pode_marcar(item, papel, uid):
            abort(403)
        try:
            with db.transaction() as con:
                r = RT.marcar_feito(con, rotina_id, request.form.get("referencia") or "",
                                    resultado=request.form.get("resultado") or "",
                                    observacao=request.form.get("observacao") or "",
                                    por=usuario_nome(), usuario_id=uid, papel=papel)
        except RT.RotinaSemPermissao:
            abort(403)
        except RT.RotinaError as recusa:
            flash(str(recusa), "warning")
            return _voltar_do_feito(rotina_id)
        arquivo = request.files.get("prova_arquivo")
        tem_arquivo = bool(arquivo and arquivo.filename)
        if not r["gravou"]:
            flash(f"«{r['titulo']}» já tinha sido registrado por {r['por']} "
                  f"({str(r['em'])[8:10]}/{str(r['em'])[5:7]} às {str(r['em'])[11:16]})."
                  + (" O arquivo enviado não foi guardado." if tem_arquivo else ""), "info")
            return _voltar_do_feito(rotina_id)
        # A TRILHA PRIMEIRO: o feito já está gravado, e a auditoria não espera o arquivo.
        audit("ROTINA_FEITA", "ge_rotina", rotina_id,
              {"codigo": r["codigo"], "referencia": r["referencia"], "prazo": r["prazo"],
               "com_atraso": r["com_atraso"], "resultado": r["resultado"],
               "observacao": r["observacao"], "feito_id": r["id"], "com_prova": tem_arquivo})
        QRW.auditar_conclusao(audit, "ROTINA", f"{int(rotina_id)}:{r['referencia']}", r["titulo"],
                              r.get("quem_resolvia"))
        flash(f"«{r['titulo']}»: {RT.ROTULO_DO_RESULTADO[r['resultado']].lower()}, registrado"
              + (" com atraso" if r["com_atraso"] else "") + ".", "success")
        if tem_arquivo and archive_root is not None:
            try:
                pasta = archive_root() / "gestao" / "rotina" / f"feito_{int(r['id'])}"
                info = save_upload(arquivo, pasta)
                anexo_id = db.add_attachment(RT.TIPO_DO_ANEXO, int(r["id"]), info, uid,
                                             "Prova da rotina da serventia")
            except Exception as falha:                     # noqa: BLE001 — o feito fica, o arquivo não
                audit("ROTINA_PROVA_FALHOU", "ge_rotina", rotina_id,
                      {"codigo": r["codigo"], "feito_id": r["id"],
                       "erro": (str(falha) or falha.__class__.__name__)[:300]})
                flash("O «feito» ficou registrado, mas o arquivo da prova não foi guardado "
                      f"({str(falha) or falha.__class__.__name__}). Guarde a prova de outro jeito "
                      "e avise a TI.", "warning")
            else:
                audit("ROTINA_PROVA_ANEXADA", "ge_rotina", rotina_id,
                      {"codigo": r["codigo"], "feito_id": r["id"], "anexo_id": anexo_id,
                       "sha256": info.get("sha256")})
        return _voltar_do_feito(rotina_id)

    # ------------------------------------------------------------- minha rotina

    @app.route("/minha-rotina")
    @login_required
    def rotina_minha():
        """O que a pessoa tem para hoje e o atrasado, como responsável ou suplente. SÓ LÊ."""
        u = current_user()
        papel, uid = u["role"], usuario_id()
        itens, toda, erro = [], [], ""
        try:
            with db.connect() as con:
                itens = RT.do_dia(con, date.today(), usuario_id=uid)
                toda = RT.da_pessoa(con, uid)
        except Exception as falha:                         # noqa: BLE001 — zero por engano não é zero
            erro = str(falha) or falha.__class__.__name__
        preparar(itens, papel=papel, usuario_id=uid, abre=_abre_para(papel))
        preparar(toda, papel=papel, usuario_id=uid, abre=_abre_para(papel))
        em_resolucao, erro_quem = 0, ""
        try:
            em_resolucao = QRW.preparar_rotina(db, itens, papel=papel, usuario_id=uid,
                                               eh_robo=QRW.e_robo(u))
        except Exception as falha:                         # noqa: BLE001 — a marca não derruba a tela
            erro_quem = str(falha) or falha.__class__.__name__
        return render_template("rotina_minha.html", itens=itens, toda=toda, erro=erro,
                               em_resolucao=em_resolucao, erro_quem=erro_quem,
                               hoje=date.today().isoformat(), so_ve=papel in RT.QUEM_SO_VE,
                               **contexto())
