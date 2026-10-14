"""Modelos da ficha e da certidão do Livro 3 — editor com prévia ao vivo.

O catálogo continua em Administrativo → Modelos e em Registro de Imóveis →
Modelos; **esta tela é a porta do módulo Livro 3**, para quem está na ficha e
precisa ajustar o papel sem sair do contexto.
"""
from __future__ import annotations

from flask import flash, jsonify, redirect, render_template, request, url_for

import livro3_modelos_ensaio as L3_ENSAIO
import modelos_da_casa as MODELOS
import modelos_elementos as ELEM
import modelos_previa as PREVIA

QUEM_EDITA: tuple[str, ...] = ("ADMIN", "MANAGER", "USER")


def _conferir(chave: str, corpo: str) -> str | None:
    atrib = ELEM.atribuicao_do_ato(chave)
    erro = ELEM.conferir(atrib, chave, ELEM.CORPO, corpo or "")
    if erro:
        return erro
    try:
        (corpo or "").format(**L3_ENSAIO.claros_de(chave))
    except KeyError as exc:
        return (
            f"O modelo pede um claro que o ensaio não conhece: {exc}. "
            "Confira a legenda ou use «Voltar ao padrão»."
        )
    except ValueError as exc:
        return str(exc)
    return None


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    usuario_nome = app.extensions["usuario_nome"]

    conferidores = app.extensions.setdefault("conferidores_de_modelo", {})
    for chave in L3_ENSAIO.CHAVES_LIVRO3:
        conferidores[chave] = lambda c, k=chave: _conferir(k, c) or ""

    def _itens(con):
        linhas = []
        for chave in L3_ENSAIO.CHAVES_LIVRO3:
            meta = MODELOS.POR_CHAVE[chave]
            linhas.append({
                **meta,
                "chave": chave,
                "ajustado": ELEM.esta_ajustado(con, chave),
                "corpo": ELEM.corpo_do_ato(con, chave),
            })
        return linhas

    @app.route("/livro3/modelos", methods=["GET", "POST"])
    @login_required
    @roles_required(*QUEM_EDITA)
    def livro3_modelos():
        chave = (request.values.get("editar") or "").strip().upper()
        if chave and chave not in L3_ENSAIO.CHAVES_LIVRO3:
            flash("Esse modelo não pertence ao Livro 3.", "warning")
            chave = ""

        if request.method == "POST":
            chave = (request.form.get("chave") or "").strip().upper()
            corpo = request.form.get("corpo") or ""
            acao = (request.form.get("acao") or "salvar").strip()
            if chave not in L3_ENSAIO.CHAVES_LIVRO3:
                flash("Modelo inválido.", "danger")
                return redirect(url_for("livro3_modelos"))
            try:
                if acao == "restaurar":
                    with db.transaction() as con:
                        havia = ELEM.restaurar(
                            con, atribuicao=ELEM.atribuicao_do_ato(chave),
                            ato=chave, parte=ELEM.CORPO)
                        havia = MODELOS.restaurar(con, chave) or havia
                    audit("MODELO_RESTAURADO", "mo_elementos", chave,
                          {"havia_ajuste": havia, "modulo": "livro3"})
                    flash("Voltou ao padrão do sistema." if havia
                          else "Este modelo já estava no padrão.",
                          "success" if havia else "info")
                else:
                    erro = _conferir(chave, corpo)
                    if erro and corpo.strip():
                        flash(f"O modelo tem um erro e não foi gravado: {erro}",
                              "danger")
                        return redirect(url_for("livro3_modelos", editar=chave))
                    with db.transaction() as con:
                        ELEM.salvar(
                            con, atribuicao=ELEM.atribuicao_do_ato(chave),
                            ato=chave, parte=ELEM.CORPO, corpo=corpo,
                            quem=usuario_nome(), agora=db.now())
                    audit("MODELO_AJUSTADO", "mo_elementos", chave,
                          {"tamanho": len(corpo.strip()), "modulo": "livro3"})
                    flash("Modelo gravado. Vale no próximo documento deste "
                          "tipo.", "success")
            except (MODELOS.ModeloError, ELEM.ElementoError) as erro:
                flash(str(erro), "danger")
            except Exception as erro:  # noqa: BLE001
                flash(f"Não deu para gravar: {erro}", "danger")
            return redirect(url_for("livro3_modelos", editar=chave))

        if not chave:
            chave = L3_ENSAIO.CHAVES_LIVRO3[0]

        with db.connect() as con:
            itens = _itens(con)
            editando = next((i for i in itens if i["chave"] == chave), itens[0])
            editando = {
                **editando,
                "erro": _conferir(editando["chave"], editando["corpo"]),
                "legenda": ELEM.legenda_do_ato(
                    editando["chave"], editando["corpo"]),
                "formato": MODELOS.formato_de(editando["chave"]),
                "onde": "{}.{}".format(*editando["padrao"]),
            }

        return render_template(
            "livro3_modelos.html",
            itens=itens,
            editando=editando,
            quantos_ajustados=sum(1 for i in itens if i["ajustado"]),
        )

    @app.route("/livro3/modelos/previa", methods=["POST"])
    @login_required
    @roles_required(*QUEM_EDITA)
    def livro3_modelos_previa():
        ato = (request.form.get("ato") or "").strip().upper()
        if ato not in L3_ENSAIO.CHAVES_LIVRO3:
            return jsonify(ok=False, erro="Modelo desconhecido."), 400
        with db.connect() as con:
            corpo, codigo = PREVIA.resposta_previa(con, ato, request.form)
        return jsonify(**corpo), codigo
