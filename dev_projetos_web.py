"""Rotas web — Projetos de desenvolvimento (ADMIN e MANAGER).

O QUE NÃO CABE À GESTÃO (25/11/2026, T019)
    «permitir que retiremos [...] dos projetos itens que nao cabem a gestao ou
    admin» — o oficial. «Retirar dos projetos da gestão», na ficha do projeto,
    pede o motivo e tira o projeto da lista principal (`gestao_retirados`, chave
    = id do projeto); «Ver os retirados» lista quem retirou, quando e por quê,
    com «Devolver à lista». Não apaga o projeto, a etapa nem o histórico, e a
    ficha continua abrindo. Retirar e devolver gravam na auditoria.

FASES, COMPROVANTES E LINHA DO TEMPO (26/11/2026, S006)
    Ver `dev_projetos`. A lista mostra o progresso («n de m fases»), a próxima
    fase, o responsável, o prazo e a área, com filtro por área e situação. A
    ficha abre com «O que falta para o resultado pleno» (as fases abertas, com
    critério, prazo e responsável; as atrasadas em destaque), depois as fases
    (cada uma com os comprovantes e os botões de mudar a situação e anexar), a
    linha do tempo (do mais novo ao mais antigo) e os formulários. «Novo
    projeto» e a carga em lote (JSON, a porta do agente 11) ficam na lista.

    Toda escrita grava na auditoria: DEV_PROJETO_CRIADO, DEV_PROJETO_ALTERADO,
    DEV_PROJETO_ANDAMENTO, DEV_PROJETO_FASE_CRIADA, DEV_PROJETO_FASE_ALTERADA,
    DEV_PROJETO_FASE_CONCLUIDA, DEV_PROJETO_COMPROVANTE, DEV_PROJETO_RETIRADO e
    DEV_PROJETO_DEVOLVIDO. A carga grava uma linha por projeto que mudou
    (CRIADO ou ALTERADO, com `via: importar` e os ids do que criou).
"""
from __future__ import annotations

from typing import Callable

import dev_projetos as DP
import gestao_retirados as GR

#: Quem abre e grava os projetos (o TI passa como ADMIN).
QUEM_USA = ("ADMIN", "MANAGER")
#: O tamanho máximo do JSON da carga em lote.
CARGA_MAXIMA_EM_BYTES = 2 * 1024 * 1024


def register_dev_projetos_routes(
    app,
    *,
    login_required,
    roles_required,
    get_db,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    abort,
    is_sandbox: Callable,
    current_user_login: Callable[[], str | None],
    audit: Callable | None = None,
) -> None:
    # Quem retira: o nome e o id, como o «conferido hoje» da checklist grava.
    _quem = app.extensions.get("usuario_nome") or (lambda: current_user_login() or "?")
    _uid = app.extensions.get("usuario_id") or (lambda: None)

    def _por() -> str:
        """Quem grava fase, comprovante e cadastro: o login, como o andamento."""
        return current_user_login() or _quem()

    def _pasta_dos_comprovantes():
        raiz = app.extensions.get("archive_root")
        if raiz is None:
            raise DP.ProjetoError("A pasta dos arquivos da casa não está configurada.")
        return raiz() / "dev_projetos"

    def _auditar(acao: str, projeto_id: int, detalhes: dict) -> None:
        if audit is not None:
            audit(acao, "dev_projetos", projeto_id, detalhes)

    def _formulario(campos) -> dict:
        """Só os campos que o formulário mandou: o que não veio não muda."""
        return {c: request.form.get(c) for c in campos if c in request.form}

    def _voltar(projeto_id: int, ancora: str = ""):
        if ancora:
            return redirect(url_for("dev_projetos_detalhe", projeto_id=projeto_id, _anchor=ancora))
        return redirect(url_for("dev_projetos_detalhe", projeto_id=projeto_id))

    def _fase_do_projeto(con, projeto_id: int, fase_id: int) -> dict:
        fase = DP.obter_fase(con, fase_id)
        if not fase or int(fase["projeto_id"]) != int(projeto_id):
            abort(404)
        return fase

    @app.route("/desenvolvimento/projetos")
    @login_required
    @roles_required(*QUEM_USA)
    def dev_projetos_lista():
        area = (request.args.get("area") or "").strip()
        situacao = (request.args.get("situacao") or "").strip().upper()
        with get_db() as con:
            if is_sandbox(con):
                DP.seed_sandbox_exemplo(con)
                DP.aplicar_atualizacao_pendencias_20261001(con)
                con.commit()
            todos = DP.listar_projetos(con)
            retiradas = GR.ativas(con, GR.PROJETOS)
        na_lista = [p for p in todos if str(p["id"]) not in retiradas]
        retirados = [{**p, "retirada": retiradas[str(p["id"])]}
                     for p in todos if str(p["id"]) in retiradas]
        return render_template(
            "dev_projetos_lista.html",
            projetos=DP.filtrar_projetos(na_lista, area=area, situacao=situacao),
            total_na_lista=len(na_lista),
            areas=DP.areas_em_uso(na_lista),
            filtro_area=area,
            filtro_situacao=situacao,
            filtros_situacao=DP.FILTROS_DE_SITUACAO,
            retirados=retirados,
            ver_retirados=request.args.get("ver") == "retirados",
            status_rotulo=DP.STATUS_ROTULO,
            situacao_da_fase=DP.SITUACAO_DA_FASE_ROTULO,
            carga_maxima=DP.CARGA_MAXIMA_DE_PROJETOS,
        )

    @app.route("/desenvolvimento/projetos/<int:projeto_id>")
    @login_required
    @roles_required(*QUEM_USA)
    def dev_projetos_detalhe(projeto_id: int):
        with get_db() as con:
            if is_sandbox(con):
                DP.seed_sandbox_exemplo(con)
                DP.aplicar_atualizacao_pendencias_20261001(con)
                con.commit()
            dados = DP.ficha(con, projeto_id)
            if not dados:
                abort(404)
            retirada = GR.ativas(con, GR.PROJETOS).get(str(projeto_id))
        return render_template(
            "dev_projeto_detalhe.html",
            projeto=dados["projeto"],
            fases=dados["fases"],
            falta=dados["falta"],
            comprovantes_do_projeto=dados["comprovantes_do_projeto"],
            linha_do_tempo=list(reversed(dados["linha_do_tempo"])),
            retirada=retirada,
            motivos_prontos=GR.MOTIVOS_PRONTOS,
            motivo_maximo=GR.MOTIVO_MAXIMO,
            status_rotulo=DP.STATUS_ROTULO,
            status_validos=sorted(DP.STATUS_VALIDOS),
            situacao_da_fase=DP.SITUACAO_DA_FASE_ROTULO,
            tipos_de_comprovante=DP.TIPOS_DE_COMPROVANTE,
            extensoes=",".join(DP.EXTENSOES_DO_ARQUIVO),
        )

    @app.route("/desenvolvimento/projetos/novo", methods=["POST"])
    @login_required
    @roles_required(*QUEM_USA)
    def dev_projetos_novo():
        dados = _formulario(DP.CAMPOS_DO_PROJETO)
        try:
            with get_db() as con:
                projeto_id = DP.criar_projeto(con, dados, por=_por())
                projeto = DP.obter_projeto(con, projeto_id)
        except DP.ProjetoError as erro:
            flash(f"{erro} O projeto não foi cadastrado.", "warning")
            return redirect(url_for("dev_projetos_lista", _anchor="novo-projeto"))
        _auditar("DEV_PROJETO_CRIADO", projeto_id,
                 {c: projeto.get(c) for c in DP.CAMPOS_DO_PROJETO if projeto.get(c)})
        flash(f"Projeto «{projeto['titulo']}» cadastrado. Cadastre agora as fases até o "
              "resultado pleno.", "success")
        return _voltar(projeto_id, "nova-fase")

    @app.route("/desenvolvimento/projetos/importar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_USA)
    def dev_projetos_importar():
        """A carga em lote (JSON): um projeto ou uma lista. Tudo ou nada."""
        texto = request.form.get("carga") or ""
        arquivo = request.files.get("arquivo")
        if arquivo and arquivo.filename:
            bruto = arquivo.read(CARGA_MAXIMA_EM_BYTES + 1)
            texto = bruto.decode("utf-8-sig", errors="replace")
        else:
            bruto = texto.encode("utf-8")
        # o mesmo limite para o arquivo e para o JSON colado
        if len(bruto) > CARGA_MAXIMA_EM_BYTES:
            flash("A carga passa de 2 MB: divida em cargas menores. Nada foi gravado.", "warning")
            return redirect(url_for("dev_projetos_lista", _anchor="carga-em-lote"))
        resultados = []
        try:
            specs = DP.ler_carga(texto)
            with get_db() as con:
                for n, spec in enumerate(specs, 1):
                    try:
                        resultados.append(DP.importar(con, spec, por=_por()))
                    except (ValueError, LookupError) as erro:
                        nome = spec.get("codigo") or spec.get("titulo") or f"nº {n}"
                        raise DP.ProjetoError(f"Projeto {nome} da carga: {erro}") from erro
                con.commit()
        except DP.ProjetoError as erro:
            flash(f"{erro} Nada desta carga foi gravado.", "warning")
            return redirect(url_for("dev_projetos_lista", _anchor="carga-em-lote"))
        for r in resultados:
            if r["mudou"]:
                _auditar("DEV_PROJETO_CRIADO" if r["projeto"] == "CRIADO" else "DEV_PROJETO_ALTERADO",
                         r["projeto_id"], {"via": "importar", **r})
        criados = sum(1 for r in resultados if r["projeto"] == "CRIADO")
        mudaram = sum(1 for r in resultados if r["mudou"] and r["projeto"] != "CRIADO")
        flash(f"Carga lida: {len(resultados)} projeto(s) — {criados} cadastrado(s), "
              f"{mudaram} atualizado(s), {len(resultados) - criados - mudaram} sem mudança.",
              "success")
        fora = [(r["titulo"], f["titulo"]) for r in resultados for f in r["fases_fora_da_carga"]]
        if fora:
            mostra = "; ".join(f"«{fase}» ({projeto})" for projeto, fase in fora[:10])
            resto = f" e mais {len(fora) - 10}" if len(fora) > 10 else ""
            flash(f"{len(fora)} fase(s) do sistema não vieram na carga e ficaram como estavam, no fim "
                  f"da lista: {mostra}{resto}. Confira se foram renomeadas no arquivo.", "warning")
        return redirect(url_for("dev_projetos_lista"))

    @app.route("/desenvolvimento/projetos/<int:projeto_id>/editar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_USA)
    def dev_projetos_editar(projeto_id: int):
        dados = _formulario(DP.CAMPOS_DO_PROJETO)
        try:
            with get_db() as con:
                if not DP.obter_projeto(con, projeto_id):
                    abort(404)
                mudou = DP.atualizar_projeto(con, projeto_id, dados, por=_por())
        except DP.ProjetoError as erro:
            flash(f"{erro} Nada foi gravado.", "warning")
            return _voltar(projeto_id, "editar-projeto")
        if not mudou:
            flash("Nada mudou no projeto.", "info")
            return _voltar(projeto_id)
        _auditar("DEV_PROJETO_ALTERADO", projeto_id, {"mudou": mudou})
        flash("Projeto atualizado.", "success")
        return _voltar(projeto_id)

    @app.route("/desenvolvimento/projetos/<int:projeto_id>/status", methods=["POST"])
    @login_required
    @roles_required(*QUEM_USA)
    def dev_projetos_alterar_status(projeto_id: int):
        status = (request.form.get("status_geral") or "").strip()
        with get_db() as con:
            antes = DP.obter_projeto(con, projeto_id)
            try:
                DP.alterar_status(con, projeto_id, status)
                con.commit()
            except (LookupError, ValueError) as erro:
                flash(str(erro), "warning")
                return redirect(url_for("dev_projetos_detalhe", projeto_id=projeto_id))
        _auditar("DEV_PROJETO_ALTERADO", projeto_id,
                 {"mudou": {"status_geral": [antes["status_geral"], status.upper()]}})
        flash("Status atualizado.", "success")
        return redirect(url_for("dev_projetos_detalhe", projeto_id=projeto_id))

    @app.route(
        "/desenvolvimento/projetos/<int:projeto_id>/proximo-passo",
        methods=["POST"],
    )
    @login_required
    @roles_required(*QUEM_USA)
    def dev_projetos_alterar_proximo_passo(projeto_id: int):
        texto = request.form.get("proximo_passo")
        with get_db() as con:
            antes = DP.obter_projeto(con, projeto_id)
            try:
                DP.alterar_proximo_passo(con, projeto_id, texto)
                con.commit()
            except LookupError as erro:
                flash(str(erro), "warning")
                return redirect(url_for("dev_projetos_detalhe", projeto_id=projeto_id))
        _auditar("DEV_PROJETO_ALTERADO", projeto_id,
                 {"mudou": {"proximo_passo": [antes["proximo_passo"], (texto or "").strip() or None]}})
        flash("Próximo passo / pendência salvo.", "success")
        return redirect(url_for("dev_projetos_detalhe", projeto_id=projeto_id))

    @app.route("/desenvolvimento/projetos/<int:projeto_id>/andamento", methods=["POST"])
    @login_required
    @roles_required(*QUEM_USA)
    def dev_projetos_novo_andamento(projeto_id: int):
        texto = request.form.get("texto") or ""
        autor = current_user_login()
        with get_db() as con:
            if not DP.obter_projeto(con, projeto_id):
                abort(404)
            try:
                andamento_id = DP.registrar_andamento(con, projeto_id, texto, autor=autor)
                con.commit()
            except (LookupError, ValueError) as erro:
                flash(str(erro), "warning")
                return redirect(url_for("dev_projetos_detalhe", projeto_id=projeto_id))
        _auditar("DEV_PROJETO_ANDAMENTO", projeto_id, {"andamento_id": andamento_id})
        flash("Andamento registrado.", "success")
        return redirect(url_for("dev_projetos_detalhe", projeto_id=projeto_id))

    @app.route("/desenvolvimento/projetos/<int:projeto_id>/fases/nova", methods=["POST"])
    @login_required
    @roles_required(*QUEM_USA)
    def dev_projetos_fase_nova(projeto_id: int):
        dados = _formulario(DP.CAMPOS_DA_FASE)
        try:
            with get_db() as con:
                if not DP.obter_projeto(con, projeto_id):
                    abort(404)
                fase_id = DP.adicionar_fase(con, projeto_id, dados, por=_por())
                fase = DP.obter_fase(con, fase_id)
        except DP.ProjetoError as erro:
            flash(f"{erro} A fase não foi cadastrada.", "warning")
            return _voltar(projeto_id, "nova-fase")
        _auditar("DEV_PROJETO_FASE_CRIADA", projeto_id,
                 {"fase_id": fase_id, "titulo": fase["titulo"], "ordem": fase["ordem"]})
        flash(f"Fase «{fase['titulo']}» cadastrada.", "success")
        return _voltar(projeto_id, f"fase-{fase_id}")

    @app.route("/desenvolvimento/projetos/<int:projeto_id>/fases/<int:fase_id>/alterar",
               methods=["POST"])
    @login_required
    @roles_required(*QUEM_USA)
    def dev_projetos_fase_alterar(projeto_id: int, fase_id: int):
        """A situação (com aguardando e observação) ou os campos da fase."""
        dados = _formulario(DP.CAMPOS_DA_FASE + ("situacao",))
        # No «Mudar a situação», a observação é a DESTA mudança e vem em branco:
        # em branco, não apaga a que está gravada.
        if request.form.get("formulario") == "situacao" and not (dados.get("observacao") or "").strip():
            dados.pop("observacao", None)
        try:
            with get_db() as con:
                fase = _fase_do_projeto(con, projeto_id, fase_id)
                feito = DP.alterar_fase(con, fase_id, dados, por=_por())
        except DP.ProjetoError as erro:
            flash(f"{erro} Nada foi gravado.", "warning")
            return _voltar(projeto_id, f"fase-{fase_id}")
        if not feito["mudou"]:
            flash("Nada mudou na fase.", "info")
            return _voltar(projeto_id, f"fase-{fase_id}")
        acao = "DEV_PROJETO_FASE_CONCLUIDA" if feito["concluida"] else "DEV_PROJETO_FASE_ALTERADA"
        _auditar(acao, projeto_id, {"fase_id": fase_id, "titulo": fase["titulo"],
                                    "mudou": feito["mudou"]})
        flash("Fase concluída." if feito["concluida"] else "Fase atualizada.", "success")
        return _voltar(projeto_id, f"fase-{fase_id}")

    @app.route("/desenvolvimento/projetos/<int:projeto_id>/fases/<int:fase_id>/mover",
               methods=["POST"])
    @login_required
    @roles_required(*QUEM_USA)
    def dev_projetos_fase_mover(projeto_id: int, fase_id: int):
        try:
            with get_db() as con:
                _fase_do_projeto(con, projeto_id, fase_id)
                ordem = DP.mover_fase(con, projeto_id, fase_id, request.form.get("direcao") or "",
                                      por=_por())
        except DP.ProjetoError as erro:
            flash(str(erro), "warning")
            return _voltar(projeto_id, "fases")
        if ordem:
            _auditar("DEV_PROJETO_FASE_ALTERADA", projeto_id, {"fase_id": fase_id, "ordem": ordem})
        return _voltar(projeto_id, f"fase-{fase_id}")

    @app.route("/desenvolvimento/projetos/<int:projeto_id>/comprovantes", methods=["POST"])
    @login_required
    @roles_required(*QUEM_USA)
    def dev_projetos_comprovante(projeto_id: int):
        """O comprovante de uma fase (ou do projeto): arquivo, link, PR, relatório,
        tarefa ou texto. O arquivo vai para `attachments` na mesma transação."""
        fase_id = (request.form.get("fase_id") or "").strip() or None
        ancora = f"fase-{fase_id}" if fase_id and fase_id.isdigit() else "comprovantes-do-projeto"
        arquivo = request.files.get("arquivo")
        tem_arquivo = bool(arquivo and arquivo.filename)
        tipo = (request.form.get("tipo") or "").strip().upper()
        # A RECUSA SAI DO `with`: a conexão da ponte confirma ao sair sem erro, e o
        # anexo gravado antes da recusa do comprovante ficaria órfão no banco.
        try:
            with get_db() as con:
                if not DP.obter_projeto(con, projeto_id):
                    abort(404)
                anexo_id = None
                comum = {"fase_id": fase_id, "tipo": tipo,
                         "descricao": request.form.get("descricao") or "",
                         "referencia": request.form.get("referencia") or "", "por": _por()}
                if tem_arquivo:
                    # confere antes de escrever: o recusado não deixa arquivo no disco
                    comprovante_id, anexo_id = DP.registrar_comprovante_com_arquivo(
                        con, projeto_id, nome_arquivo=arquivo.filename,
                        conteudo=arquivo.read(DP.TAMANHO_MAXIMO_DO_ARQUIVO + 1),
                        pasta=_pasta_dos_comprovantes(), usuario_id=_uid(), **comum)
                else:
                    comprovante_id = DP.registrar_comprovante(con, projeto_id, **comum)
        except DP.ProjetoError as erro:
            flash(f"{erro} O comprovante não foi registrado.", "warning")
            return _voltar(projeto_id, ancora)
        _auditar("DEV_PROJETO_COMPROVANTE", projeto_id,
                 {"comprovante_id": comprovante_id, "fase_id": int(fase_id) if fase_id else None,
                  "tipo": tipo, "attachment_id": anexo_id})
        flash("Comprovante registrado.", "success")
        return _voltar(projeto_id, ancora)

    @app.route("/desenvolvimento/projetos/<int:projeto_id>/retirar", methods=["POST"])
    @login_required
    @roles_required(*GR.QUEM_RETIRA)
    def dev_projetos_retirar(projeto_id: int):
        """Retira o projeto da lista: não cabe à gestão. Não apaga nada."""
        with get_db() as con:
            projeto = DP.obter_projeto(con, projeto_id)
            if not projeto:
                abort(404)
            try:
                r = GR.retirar(con, GR.PROJETOS, str(projeto_id),
                               motivo=request.form.get("motivo"),
                               motivo_codigo=request.form.get("motivo_codigo"),
                               por=_quem(), usuario_id=_uid())
                con.commit()
            except GR.RetiradaError as erro:
                flash(str(erro), "warning")
                return redirect(url_for("dev_projetos_detalhe", projeto_id=projeto_id))
        if not r["gravou"]:
            flash(f"O projeto já tinha sido retirado por {r['retirada']['por']}.", "info")
            return redirect(url_for("dev_projetos_detalhe", projeto_id=projeto_id))
        _auditar("DEV_PROJETO_RETIRADO", projeto_id,
                 {"titulo": projeto["titulo"], "motivo_codigo": r["retirada"]["motivo_codigo"],
                  "motivo": r["retirada"]["motivo"]})
        flash(f"«{projeto['titulo']}» saiu dos projetos da gestão. Nada foi apagado: "
              "está em «Ver os retirados».", "success")
        return redirect(url_for("dev_projetos_lista"))

    @app.route("/desenvolvimento/projetos/<int:projeto_id>/devolver", methods=["POST"])
    @login_required
    @roles_required(*GR.QUEM_RETIRA)
    def dev_projetos_devolver(projeto_id: int):
        """Devolve o projeto retirado à lista principal."""
        with get_db() as con:
            projeto = DP.obter_projeto(con, projeto_id)
            if not projeto:
                abort(404)
            r = GR.devolver(con, GR.PROJETOS, str(projeto_id),
                            por=_quem(), usuario_id=_uid())
            con.commit()
        if r:
            _auditar("DEV_PROJETO_DEVOLVIDO", projeto_id,
                     {"titulo": projeto["titulo"], "retirado_por": r["por"],
                      "retirado_em": r["em"]})
            flash(f"«{projeto['titulo']}» voltou aos projetos da gestão.", "success")
        else:
            flash("Este projeto não estava retirado.", "info")
        return redirect(url_for("dev_projetos_lista", ver="retirados"))
