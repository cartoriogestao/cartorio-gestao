"""O SEMÁFORO DA CONFORMIDADE NO PAINEL GERAL — 18/11/2026.

    «Quer que eu comece o painel de conformidade (semáforo por área)?»
    «Sim, comece» — o oficial, 18/11/2026

SEM ROTA PRÓPRIA
    É um quadro da primeira tela, como o da ouvidoria: o contexto chega só ao
    painel geral (`dashboard`) e só a quem cuida da casa — o oficial, o
    gerente e o auditor (o gestor de compliance entra por um destes papéis).
    Para os demais o contexto vem vazio e o quadro não aparece.

TELA NÃO CAI POR CAUSA DE QUADRO
    A medição que quebra não vira «tudo verde»: o quadro aparece com o aviso
    de que não deu para medir, e o resto do painel abre normalmente.

A CHECKLIST DE GESTÃO DO DIA — 19/11/2026
    «não consigo clicar nos itens e não vejo checklist» — o oficial

    Cada cartão do semáforo leva a `/administrativo/gestor/checklist?area=…`,
    a tela que lista os achados abertos daquela área e as conferências do dia
    (`gestor_checklist`). Mora aqui porque é a mesma pergunta do quadro —
    «o que está fora da conformidade?» — e é vista pelos mesmos papéis.
    O «conferido hoje» grava quem olhou, com auditoria, e não fecha achado.

O QUE NÃO CABE À GESTÃO — 25/11/2026 (T019)
    «Retirar» e «Devolver à lista» moram aqui pela mesma razão: o oficial e o
    gerente marcam o achado que não cabe à gestão (`gestao_retirados`), com
    motivo e auditoria. O cartão do painel continua com a COR OFICIAL — a que
    vai ao retrato e que ninguém pinta à mão — e mostra, quando há retirados,
    quantos são e a cor «sem os retirados».

A ROTINA DO DIA — 26/11/2026
    A checklist abre com o bloco «Rotina do dia» de cada área (`rotina_da_casa`):
    o «Como fazer» e o «Feito» de cada item. O «Feito» mora em
    `rotina_da_casa_web` (é o mesmo de «Minha rotina»); aqui a tela só põe em
    cada item o link da tela onde se faz e se esta pessoa o marca.
"""
from __future__ import annotations

from datetime import date

from flask import (abort, flash, redirect, render_template, request, session,
                   url_for)

import conformidade as CF
import gestao_retirados as GR
import gestor_checklist as CK
import papeis as PAP
import quem_resolve_web as QRW
import rotina_da_casa as RT
import rotina_da_casa_web as RTW
from bd_nativo import banco

#: Quem vê o semáforo no painel geral — e abre a checklist que ele leva.
QUEM_VE = CK.QUEM_VE


def quadro(db, hoje: date | None = None) -> dict:
    """O que o quadro mostra: a medição, ou o erro dela. Só lê.

    `sem_retirados` é a segunda leitura (T019): a medição sem os achados que
    o oficial ou o gerente retirou por não caberem à gestão, com quantos são
    por área. A cor do cartão continua a oficial.
    """
    try:
        with db.connect() as con:
            medicao = CF.medir(con, hoje)
    except Exception as erro:                              # noqa: BLE001
        # ZERO MEDIDO E ZERO POR ENGANO SÃO COISAS DIFERENTES: o quadro diz
        # que não mediu, em vez de mostrar sete áreas verdes.
        return {"medicao": None, "erro": f"não deu para medir: {erro}", "sem_retirados": None}
    try:
        with db.connect() as con:
            chaves = frozenset(GR.ativas(con, GR.CHECKLIST))
            sem = CF.medir(con, hoje, excluir_chaves=chaves) if chaves else None
    except Exception:                                      # noqa: BLE001
        sem = None          # a segunda leitura que quebra não derruba a oficial
    return {"medicao": medicao, "erro": "", "sem_retirados": sem}


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    current_user = app.extensions["current_user"]
    usuario_nome = app.extensions["usuario_nome"]
    usuario_id = app.extensions["usuario_id"]

    def _abre(endpoint: str, papel: str) -> bool:
        """A rota do item deixa esta pessoa entrar? Pergunta à própria rota.

        A mesma pergunta do menu (`navegacao_web`): os papéis ficam à vista
        na função (`roles_required`), e copiar a lista para cá envelheceria.
        """
        funcao = app.view_functions.get(endpoint)
        if funcao is None:
            return False
        exigidos = getattr(funcao, "papeis_exigidos", None)
        metodos = getattr(funcao, "metodos_exigidos", None)
        return exigidos is None or (metodos is not None and "GET" not in metodos) or papel in exigidos

    @app.route("/administrativo/gestor/checklist")
    @login_required
    @roles_required(*CK.QUEM_VE)
    def gestor_checklist():
        """Os achados abertos por área e as conferências do dia. SÓ LÊ."""
        u = current_user()
        papel = u["role"]
        dados = CK.montar(db, papel=papel, area=(request.args.get("area") or "").upper() or None,
                          abre=lambda endpoint: _abre(endpoint, papel),
                          pode_retirar=PAP.equivale_a(u, GR.QUEM_RETIRA))
        RTW.preparar(dados["rotina_itens"], papel=papel, usuario_id=usuario_id(),
                     abre=lambda endpoint: _abre(endpoint, papel))
        # QUEM ESTÁ RESOLVENDO (26/11/2026): a marca em cada linha e quantos em
        # resolução por área. A leitura que quebra não derruba a checklist.
        dados["em_resolucao_rotina"], dados["em_resolucao_achados"] = {}, {}
        dados["erro_quem_resolve"] = ""
        try:
            for area, lista in dados["rotina"].items():
                dados["em_resolucao_rotina"][area] = QRW.preparar_rotina(
                    db, lista, papel=papel, usuario_id=usuario_id(), eh_robo=QRW.e_robo(u))
            dados["em_resolucao_achados"] = QRW.preparar_achados(
                db, dados["achados"], papel=papel, usuario_id=usuario_id(),
                eh_robo=QRW.e_robo(u))
        except Exception as falha:                         # noqa: BLE001
            dados["erro_quem_resolve"] = str(falha) or falha.__class__.__name__
        return render_template(
            "gestor_checklist.html", ck=dados, areas={**CF.ROTULO_DA_AREA, **RT.ROTULO_DA_AREA},
            ordem_areas=CF.AREAS, outros=CF.OUTROS, cores=CF.ROTULO_DA_COR,
            motivos=CF.ROTULO_DO_MOTIVO, gravidades=CK.ROTULO_DA_GRAVIDADE, nao_mede=CF.NAO_MEDE,
            ver_retirados=request.args.get("ver") == "retirados", area_ti=RT.TI,
            **RTW.contexto())

    def _achado_do_formulario():
        """O achado aberto do formulário: (id, chave, área, regra) — ou 400/404."""
        try:
            achado_id = int(request.form.get("achado_id") or "")
        except ValueError:
            abort(400)
        with db.connect() as con:
            linha = banco(con).um(
                "SELECT id, chave, regra FROM ge_achados WHERE id = %s", (achado_id,))
        if not linha:
            abort(404)
        return linha

    def _voltar(ver: str | None = None):
        area = (request.form.get("area") or "").strip().upper()
        if area not in CF.ROTULO_DA_AREA:
            area = None
        return redirect(url_for("gestor_checklist", area=area, ver=ver) + "#achados")

    @app.route("/administrativo/gestor/checklist/retirar", methods=["POST"])
    @login_required
    @roles_required(*GR.QUEM_RETIRA)
    def gestor_checklist_retirar():
        """Retira o achado da checklist: não cabe à gestão. Não o resolve."""
        achado = _achado_do_formulario()
        try:
            with db.transaction() as con:
                r = GR.retirar(con, GR.CHECKLIST, achado["chave"],
                               motivo=request.form.get("motivo"),
                               motivo_codigo=request.form.get("motivo_codigo"),
                               por=usuario_nome(), usuario_id=usuario_id())
        except GR.RetiradaError as erro:
            flash(str(erro), "warning")
            return _voltar()
        if r["gravou"]:
            audit("GESTOR_CHECKLIST_RETIRADO", "ge_achados", achado["id"],
                  {"chave": achado["chave"], "regra": achado["regra"],
                   "motivo_codigo": r["retirada"]["motivo_codigo"],
                   "motivo": r["retirada"]["motivo"]})
            flash("Achado retirado da checklist: não cabe à gestão. Ele continua aberto no "
                  "gestor e na cor oficial da área; está em «Ver os retirados».", "success")
        else:
            flash(f"O achado já tinha sido retirado por {r['retirada']['por']}.", "info")
        return _voltar()

    @app.route("/administrativo/gestor/checklist/devolver", methods=["POST"])
    @login_required
    @roles_required(*GR.QUEM_RETIRA)
    def gestor_checklist_devolver():
        """Devolve à checklist o achado retirado."""
        achado = _achado_do_formulario()
        with db.transaction() as con:
            r = GR.devolver(con, GR.CHECKLIST, achado["chave"], por=usuario_nome(),
                            usuario_id=usuario_id())
        if r:
            audit("GESTOR_CHECKLIST_DEVOLVIDO", "ge_achados", achado["id"],
                  {"chave": achado["chave"], "regra": achado["regra"],
                   "retirado_por": r["por"], "retirado_em": r["em"]})
            flash("Achado devolvido à checklist.", "success")
        else:
            flash("Este achado não estava retirado.", "info")
        return _voltar("retirados")

    @app.route("/administrativo/gestor/checklist/conferido", methods=["POST"])
    @login_required
    @roles_required(*CK.QUEM_CONFERE)
    def gestor_checklist_conferido():
        """«Conferido hoje» num item. Grava quem e quando; não resolve achado."""
        item = (request.form.get("item") or "").strip().upper()
        area = (request.form.get("area") or "").strip().upper()
        voltar = url_for("gestor_checklist", area=area or None)
        if area and area not in CF.ROTULO_DA_AREA and area != RT.TI:
            voltar = url_for("gestor_checklist")
        if item not in CK.CODIGOS:
            abort(400)
        with db.transaction() as con:
            r = CK.marcar_conferido(con, item, date.today(), por=usuario_nome(),
                                    usuario_id=usuario_id())
        rotulo = next(rot for cod, rot, *_ in CK.CONFERENCIAS if cod == item)
        if r["gravou"]:
            audit("GESTOR_CHECKLIST_CONFERIDO", "ge_conferencias_do_dia", None,
                  {"item": item, "dia": date.today().isoformat()})
            flash(f"«{rotulo}» conferido hoje. Os achados continuam abertos até a "
                  "conferência seguinte do gestor ver que foram resolvidos.", "success")
        else:
            flash(f"«{rotulo}» já tinha sido conferido hoje por {r['por']}"
                  f" ({str(r['em'])[11:16]}).", "info")
        return redirect(voltar)

    @app.context_processor
    def _conformidade_no_painel() -> dict:
        vazio = {"conformidade_no_painel": None}
        try:
            if (request.endpoint or "") != "dashboard" or not session.get("user_id"):
                return vazio
        except RuntimeError:
            return vazio
        u = current_user()
        if not u or u["role"] not in QUEM_VE:
            return vazio
        return {"conformidade_no_painel": {
            **quadro(db),
            "areas": CF.ROTULO_DA_AREA, "cores": CF.ROTULO_DA_COR,
            "motivos": CF.ROTULO_DO_MOTIVO, "nao_mede": CF.NAO_MEDE}}
