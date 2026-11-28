"""QUEM ESTÁ RESOLVENDO NA TELA — 26/11/2026 (`quem_resolve`).

    «marcar quem está resolvendo cada problema na Checklist do dia e nos
    Projetos, para duas pessoas não fazerem o mesmo trabalho» — o titular

ONDE APARECE
    Na Checklist do dia (o bloco da rotina e os achados abertos), em «Minha
    rotina» e em cada fase da ficha do projeto: a marca «Fulano está
    resolvendo desde 14:40» (ou «desde 25/11, há 2 dias», para ver o parado),
    com a nota. O cabeçalho de cada área soma quantos estão em resolução; a
    lista dos projetos diz quem está na próxima fase.

OS BOTÕES, E QUEM OS VÊ
    «Eu resolvo» (ou «Eu cuido desta fase»), com nota opcional, no problema
    livre, para quem pode agir nele; «Largar», para quem está resolvendo;
    «Assumir no lugar», com confirmação, para o oficial e o gerente quando é de
    outra pessoa. As rotas conferem de novo: a tela esconde por educação, a
    rota recusa por dever. O auditor e a conta de robô nunca assumem.

AUDITORIA
    QUEM_RESOLVE_ASSUMIU, QUEM_RESOLVE_LARGOU e QUEM_RESOLVE_TOMOU aqui;
    QUEM_RESOLVE_CONCLUIU onde o problema acaba (o «Feito» da rotina, a fase
    concluída ou dispensada, a carga dos projetos). Sempre com o tipo, a chave
    e o título do item. `audit()` vai depois do `with db.transaction()`.
"""
from __future__ import annotations

from datetime import date

from flask import abort, flash, redirect, request, url_for

import quem_resolve as QR


def e_robo(usuario) -> bool:
    """A conta é de robô? (a linha de `current_user`). Só lê a linha."""
    try:
        return bool(int(usuario["eh_robo"] or 0))
    except (KeyError, IndexError, TypeError, ValueError):
        return False


def preparar_rotina(db, itens: list[dict], *, papel: str, usuario_id: int | None,
                    eh_robo: bool = False) -> int:
    """Marca os itens da rotina do dia (a ocorrência de cada um). Devolve quantos
    estão em resolução. Só lê."""
    import rotina_da_casa as RT
    if not itens:
        return 0

    def chave(x):
        return QR.chave_da_rotina(x["id"], x.get("referencia") or "")

    with db.connect() as con:
        quem = QR.ativos(con, QR.ROTINA, [chave(x) for x in itens])

    def pode(x):
        return (x.get("situacao") != RT.FEITO and bool(x.get("referencia"))
                and QR.pode_assumir(QR.ROTINA, papel, eh_robo=eh_robo,
                                    pode_marcar_a_rotina=RT.pode_marcar(x, papel, usuario_id)))

    return QR.marcar(itens, quem, chave, papel=papel, usuario_id=usuario_id,
                     pode_assumir_item=pode, eh_robo=eh_robo)


def preparar_achados(db, por_area: dict[str, list[dict]], *, papel: str,
                     usuario_id: int | None, eh_robo: bool = False) -> dict[str, int]:
    """Marca os achados abertos da lista. Devolve {área: quantos em resolução}. Só lê."""
    todos = [x for lista in por_area.values() for x in lista]
    if not todos:
        return {}
    with db.connect() as con:
        quem = QR.ativos(con, QR.ACHADO, [str(x["chave"]) for x in todos])
    pode = QR.pode_assumir(QR.ACHADO, papel, eh_robo=eh_robo)
    return {area: QR.marcar(lista, quem, lambda x: str(x["chave"]), papel=papel,
                            usuario_id=usuario_id, pode_assumir_item=lambda _x: pode,
                            eh_robo=eh_robo)
            for area, lista in por_area.items()}


def preparar_fases(db, fases: list[dict], *, papel: str, usuario_id: int | None,
                   eh_robo: bool = False, outras: list[dict] | None = None) -> int:
    """Marca as fases da ficha do projeto (e `outras` listas das mesmas fases,
    como «o que falta»). Devolve quantas estão em resolução. Só lê."""
    import dev_projetos as DP
    if not fases:
        return 0
    with db.connect() as con:
        quem = QR.ativos(con, QR.FASE, [str(int(f["id"])) for f in fases])

    def pode(f):
        return (f.get("situacao") not in DP.FASE_FEITA
                and QR.pode_assumir(QR.FASE, papel, eh_robo=eh_robo))

    n = QR.marcar(fases, quem, lambda f: str(int(f["id"])), papel=papel, usuario_id=usuario_id,
                  pode_assumir_item=pode, eh_robo=eh_robo)
    if outras:
        QR.marcar(outras, quem, lambda f: str(int(f["id"])), papel=papel,
                  usuario_id=usuario_id, pode_assumir_item=pode, eh_robo=eh_robo)
    return n


def quem_nas_proximas(db, projetos: list[dict]) -> None:
    """Na lista dos projetos: quem está na próxima fase de cada um. Só lê."""
    proximas = [p["progresso"]["proxima"] for p in projetos
                if (p.get("progresso") or {}).get("proxima")]
    if not proximas:
        return
    with db.connect() as con:
        quem = QR.ativos(con, QR.FASE, [str(int(f["id"])) for f in proximas])
    for f in proximas:
        f["quem"] = quem.get(str(int(f["id"])))


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    current_user = app.extensions["current_user"]
    usuario_nome = app.extensions["usuario_nome"]
    usuario_id = app.extensions["usuario_id"]

    def _alvo(tipo: str, papel: str, uid: int | None) -> dict:
        """O problema do formulário: {chave, titulo, pode, voltar_padrao, ...} — ou 400/404."""
        if tipo == QR.ROTINA:
            import rotina_da_casa as RT
            try:
                rotina_id = int(request.form.get("rotina_id") or "")
            except ValueError:
                abort(400)
            referencia = (request.form.get("referencia") or "").strip()[:10]
            try:
                dia = date.fromisoformat(referencia)
            except ValueError:
                abort(400)
            if dia > date.today():
                abort(400)
            with db.connect() as con:
                item = RT.uma(con, rotina_id)
            if not item or not int(item["ativo"] or 0):
                abort(404)
            return {"chave": QR.chave_da_rotina(rotina_id, referencia), "titulo": item["titulo"],
                    "pode": RT.pode_marcar(item, papel, uid), "rotina_id": rotina_id,
                    "area": item["area"]}
        if tipo == QR.ACHADO:
            import gestor_checklist as CK
            import gestor_didatica as GD
            try:
                achado_id = int(request.form.get("achado_id") or "")
            except ValueError:
                abort(400)
            from bd_nativo import banco
            with db.connect() as con:
                linha = banco(con).um(
                    "SELECT id, chave, regra, titulo FROM ge_achados "
                    "WHERE id = %s AND resolvido_em IS NULL", (achado_id,))
            if not linha:
                abort(404)
            sigiloso = str(linha["regra"] or "").upper() in CK.REGRAS_SIGILOSAS
            return {"chave": str(linha["chave"]),
                    "titulo": CK.TITULO_SIGILOSO if sigiloso else GD.limpar(linha["titulo"]),
                    "pode": papel in QR.QUEM_ASSUME_ACHADO_E_FASE, "achado_id": achado_id}
        if tipo == QR.FASE:
            import dev_projetos as DP
            try:
                fase_id = int(request.form.get("fase_id") or "")
            except ValueError:
                abort(400)
            with db.connect() as con:
                fase = DP.obter_fase(con, fase_id)
                projeto = DP.obter_projeto(con, fase["projeto_id"]) if fase else None
            if not fase or not projeto:
                abort(404)
            return {"chave": str(fase_id), "titulo": f"{projeto['titulo']} — {fase['titulo']}",
                    "pode": papel in QR.QUEM_ASSUME_ACHADO_E_FASE, "fase_id": fase_id,
                    "projeto_id": int(fase["projeto_id"]),
                    "feita": fase["situacao"] in DP.FASE_FEITA}
        abort(400)

    def _voltar(tipo: str, alvo: dict):
        destino = request.form.get("voltar") or ""
        area = (request.form.get("area") or "").strip().upper()
        if tipo == QR.FASE:
            return redirect(url_for("dev_projetos_detalhe", projeto_id=alvo["projeto_id"])
                            + f"#fase-{alvo['fase_id']}")
        if tipo == QR.ROTINA and destino == "minha":
            return redirect(url_for("rotina_minha") + f"#rotina-{alvo['rotina_id']}")
        import rotina_da_casa as RT
        area = area if area in RT.ROTULO_DA_AREA or area == "OUTROS" else None
        ancora = "#rotina" if tipo == QR.ROTINA else "#achados"
        return redirect(url_for("gestor_checklist", area=area) + ancora)

    def _quem_age(tipo: str):
        u = current_user()
        papel, uid = u["role"], usuario_id()
        if e_robo(u) or papel in QR.QUEM_NUNCA:
            abort(403)
        alvo = _alvo(tipo, papel, uid)
        if not QR.pode_assumir(tipo, papel, pode_marcar_a_rotina=alvo["pode"]):
            abort(403)
        return u, papel, uid, alvo

    def _detalhes(tipo: str, alvo: dict, **mais) -> dict:
        return {"tipo": tipo, "chave": alvo["chave"], "titulo": alvo["titulo"], **mais}

    @app.route("/administrativo/quem-resolve/assumir", methods=["POST"])
    @login_required
    def quem_resolve_assumir():
        """«Eu resolvo» — ou, para o oficial e o gerente, «Assumir no lugar»."""
        tipo = (request.form.get("tipo") or "").strip().upper()
        if tipo not in QR.TIPOS:
            abort(400)
        u, papel, uid, alvo = _quem_age(tipo)
        tomar = request.form.get("tomar") == "1"
        if tomar and not QR.pode_tomar(papel, eh_robo=e_robo(u)):
            abort(403)
        if tomar and request.form.get("confirmo") != "1":
            flash("Para assumir no lugar de outra pessoa, marque a confirmação.", "warning")
            return _voltar(tipo, alvo)
        if alvo.get("feita"):
            flash("Esta fase já está concluída ou dispensada: não há o que assumir.", "info")
            return _voltar(tipo, alvo)
        try:
            with db.transaction() as con:
                r = QR.assumir(con, tipo, alvo["chave"], usuario_id=uid, por=usuario_nome(),
                               nota=request.form.get("nota") or "", tomar=tomar)
        except QR.QuemResolveError as recusa:
            flash(str(recusa), "warning")
            return _voltar(tipo, alvo)
        if not r["gravou"]:
            flash("Você já está resolvendo isto.", "info")
        elif r["tomado_de"]:
            audit("QUEM_RESOLVE_TOMOU", "ge_quem_resolve", r["id"],
                  _detalhes(tipo, alvo, de=r["tomado_de"]["por"],
                            nota=request.form.get("nota") or ""))
            flash(f"Você assumiu no lugar de {r['tomado_de']['por']}.", "success")
        else:
            audit("QUEM_RESOLVE_ASSUMIU", "ge_quem_resolve", r["id"],
                  _detalhes(tipo, alvo, nota=request.form.get("nota") or ""))
            flash("Marcado: você está resolvendo. Os outros veem o seu nome.", "success")
        return _voltar(tipo, alvo)

    @app.route("/administrativo/quem-resolve/largar", methods=["POST"])
    @login_required
    def quem_resolve_largar():
        """«Largar»: quem estava resolvendo deixa o problema livre."""
        tipo = (request.form.get("tipo") or "").strip().upper()
        if tipo not in QR.TIPOS:
            abort(400)
        u = current_user()
        if e_robo(u) or u["role"] in QR.QUEM_NUNCA:
            abort(403)
        alvo = _alvo(tipo, u["role"], usuario_id())
        try:
            with db.transaction() as con:
                r = QR.largar(con, tipo, alvo["chave"], usuario_id=usuario_id(),
                              por=usuario_nome())
        except QR.QuemResolveError as recusa:
            flash(str(recusa), "warning")
            return _voltar(tipo, alvo)
        if r:
            audit("QUEM_RESOLVE_LARGOU", "ge_quem_resolve", r["id"], _detalhes(tipo, alvo))
            flash("Largado: o problema está livre para outra pessoa.", "success")
        else:
            flash("Ninguém estava resolvendo isto.", "info")
        return _voltar(tipo, alvo)


def auditar_conclusao(audit, tipo: str, chave: str, titulo: str, fechado: dict | None) -> None:
    """QUEM_RESOLVE_CONCLUIU: a marca que o fim do problema fechou."""
    if fechado and audit is not None:
        audit("QUEM_RESOLVE_CONCLUIU", "ge_quem_resolve", int(fechado["id"]),
              {"tipo": tipo, "chave": chave, "titulo": titulo, "de": fechado.get("por")})
