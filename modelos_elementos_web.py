"""Os submódulos de modelos — um por atribuição, com as partes editáveis.

    «preciso que haja um submodulo de modelos para cada atribuicao e nesse
     submodulo quero poder editar cada parte dos modelos, especialmente
     gerenciando cada elemento do modelo» — o oficial, 07/09/2026.

SEIS PORTAS, UMA FUNÇÃO SÓ
    **O nome da rota é o que põe a tela no grupo do menu** (`modulos.
    modulo_da_tela`), e por isso são seis endpoints — `ri_modelos_papeis`,
    `notas_modelos_papeis`, `rcpn_modelos_papeis`, `rcpj_rtd_modelos_papeis`,
    `protesto_modelos_papeis` e `caixa_modelos_papeis`. **A tela é a mesma**:
    seis cópias dela divergiriam no primeiro conserto, e o oficial veria a
    correção num submódulo e não no seguinte.

    Quem está no Registro de Imóveis abre os modelos do Registro de Imóveis.
    Era o relato #32 — «a lista filtrada» — levado até o fim: agora não há
    filtro a esquecer, porque a porta já é da atribuição.

**A TELA GERAL CONTINUA EXISTINDO**, em Administrativo → Modelos, e as duas
gravam **no mesmo lugar**. Ela responde «onde eu mudo o cabeçalho?» quando não
se sabe de qual atribuição é o papel; estas respondem quando se sabe.

O QUE ESTA TELA NÃO FAZ
    **Não edita o cabeçalho.** Decisão do oficial em 07/09/2026 — «cabecalho
    dos atos vamos deixar num ajuste separado para manter a forma e diminuir o
    risco de ir errado». Ela **diz** isso, em vez de omitir: campo que some sem
    explicação faz procurar defeito onde há decisão.

    **Não apaga o padrão**, porque o padrão não mora no banco. «Voltar ao
    herdado» apaga a linha, e o texto volta ao degrau de cima.
"""
from __future__ import annotations

from flask import flash, jsonify, redirect, render_template, request, url_for

import modelos_elementos as ELEM
import modelos_previa as PREVIA
from modelos_elementos_schema import (
    ATRIBUICOES,
    CABECALHO_FICOU_DE_FORA,
    NOME_DA_ATRIBUICAO,
)

# SÓ ADMIN E GERENTE, e o motivo não é hierarquia: o elemento é a forma de um
# documento que a serventia assina, e uma vírgula fora do lugar num elemento
# **da atribuição** sai em todo papel dela até alguém reparar.
# Mesmas roles de `/modelos` (`modelos_web`): quem ajusta papel assinado inclui
# USER — escrevente autorizado; negar só aqui dava 403 com link visível no menu.
QUEM_EDITA: tuple[str, ...] = ("ADMIN", "MANAGER", "USER")

# O endpoint de cada atribuição. O sufixo `_papeis` está em todos de propósito:
# `ri_modelos` e `rcpn_modelos` já existiam com outro sentido — a tabela velha
# do RI e os modelos livres do Registro Civil —, e reusar o nome poria duas
# telas diferentes atrás da mesma palavra.
ROTA_DA_ATRIBUICAO: dict[str, str] = {
    "RI": "ri_modelos_papeis",
    "NOTAS": "notas_modelos_papeis",
    "RCPN": "rcpn_modelos_papeis",
    "RCPJ_RTD": "rcpj_rtd_modelos_papeis",
    "PROTESTO": "protesto_modelos_papeis",
    "CAIXA": "caixa_modelos_papeis",
}

CAMINHO_DA_ATRIBUICAO: dict[str, str] = {
    "RI": "/ri/modelos",
    "NOTAS": "/notas/modelos",
    "RCPN": "/rcpn/modelos-dos-papeis",
    "RCPJ_RTD": "/rcpj-rtd/modelos",
    "PROTESTO": "/protesto/modelos",
    "CAIXA": "/caixa/modelos",
}


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """Pendura os seis submódulos de modelos no app já construído."""

    usuario_nome = app.extensions["usuario_nome"]

    def _tela(atribuicao: str):
        """A tela de uma atribuição. É a mesma para as seis."""
        atrib = ELEM.atribuicao_valida(atribuicao)

        if request.method == "POST":
            ato = (request.form.get("ato") or "").strip().upper()
            parte = (request.form.get("parte") or "").strip().upper()
            corpo = request.form.get("corpo") or ""
            acao = (request.form.get("acao") or "salvar").strip()
            alvo = ato or "(toda a atribuição)"
            try:
                if acao == "restaurar":
                    with db.transaction() as con:
                        havia = ELEM.restaurar(con, atribuicao=atrib, ato=ato,
                                               parte=parte)
                    audit("ELEMENTO_RESTAURADO", "mo_elementos",
                          f"{atrib}/{ato}/{parte}", {"havia_ajuste": havia})
                    flash("Voltou ao que ele herda." if havia
                          else "Este já era o herdado — não havia ajuste.",
                          "success" if havia else "info")
                else:
                    with db.transaction() as con:
                        ELEM.salvar(con, atribuicao=atrib, ato=ato,
                                    parte=parte, corpo=corpo,
                                    quem=usuario_nome(), agora=db.now())
                    audit("ELEMENTO_AJUSTADO", "mo_elementos",
                          f"{atrib}/{ato}/{parte}",
                          {"tamanho": len(corpo.strip())})
                    flash(f"Gravado em {alvo}. Passa a valer no próximo "
                          "documento.", "success")
            except ELEM.ElementoError as erro:
                flash(str(erro), "danger")
            except Exception as erro:                        # noqa: BLE001
                flash(f"Não deu para gravar: {erro}", "danger")
            return redirect(url_for(ROTA_DA_ATRIBUICAO[atrib], editar=ato))

        with db.connect() as con:
            q = ELEM.quadro(con, atrib)
        escolhida = (request.args.get("editar") or "").strip().upper()
        if escolhida not in {a["chave"] for a in q["atos"]}:
            escolhida = q["atos"][0]["chave"] if q["atos"] else ""
        q["editando"] = next((a for a in q["atos"]
                              if a["chave"] == escolhida), None)
        return render_template(
            "modelos_atribuicao.html", q=q,
            cabecalho_de_fora=CABECALHO_FICOU_DE_FORA,
            rota=ROTA_DA_ATRIBUICAO[atrib],
            outras=[{"chave": a, "nome": NOME_DA_ATRIBUICAO[a],
                     "rota": ROTA_DA_ATRIBUICAO[a]}
                    for a in ATRIBUICOES if a != atrib])

    # AS SEIS PORTAS. `add_url_rule` em vez de seis funções decoradas: o corpo
    # é o mesmo, e seis cópias dele divergiriam no primeiro conserto.
    for atribuicao in ATRIBUICOES:
        endpoint = ROTA_DA_ATRIBUICAO[atribuicao]

        def _porta(_a=atribuicao):
            return _tela(_a)

        _porta.__name__ = endpoint
        protegida = login_required(roles_required(*QUEM_EDITA)(_porta))
        app.add_url_rule(CAMINHO_DA_ATRIBUICAO[atribuicao], endpoint,
                         protegida, methods=["GET", "POST"])

        def _previa(_a=atribuicao):
            atrib = ELEM.atribuicao_valida(_a)
            ato = (request.form.get("ato") or "").strip().upper()
            if ELEM.atribuicao_do_ato(ato) != atrib:
                return jsonify(ok=False, erro="O modelo não pertence a esta atribuição."), 400
            with db.connect() as con:
                corpo, codigo = PREVIA.resposta_previa(con, ato, request.form)
            return jsonify(**corpo), codigo

        _previa.__name__ = endpoint + "_previa"
        protegida_previa = login_required(roles_required(*QUEM_EDITA)(_previa))
        app.add_url_rule(CAMINHO_DA_ATRIBUICAO[atribuicao] + "/previa",
                         endpoint + "_previa", protegida_previa,
                         methods=["POST"])

    @app.route("/notas/modelos/atos", methods=["GET", "POST"])
    @login_required
    @roles_required(*QUEM_EDITA)
    def notas_modelos_de_atos():
        """A biblioteca inteira das minutas notariais, agora editável."""
        codigo = (request.values.get("codigo") or "").strip()
        if request.method == "POST":
            nome = (request.form.get("nome") or "").strip()
            corpo = request.form.get("corpo") or ""
            fundamento = (request.form.get("fundamento") or "").strip()
            if not nome or not corpo.strip():
                flash("O modelo precisa de nome e texto.", "danger")
            else:
                import unicodedata
                nome_norm = " ".join("".join(
                    c for c in unicodedata.normalize("NFKD", nome.upper())
                    if not unicodedata.combining(c)).split())
                with db.transaction() as con:
                    existe = con.execute("SELECT id FROM nt_modelos WHERE codigo=?",
                                         (codigo,)).fetchone()
                    if not existe:
                        flash("Modelo notarial não encontrado.", "danger")
                        return redirect(url_for("notas_modelos_de_atos"))
                    con.execute("""UPDATE nt_modelos SET nome=?, nome_norm=?,
                                   corpo=?, fundamento=?, atualizado_em=?
                                   WHERE codigo=?""",
                                (nome, nome_norm, corpo.strip(), fundamento or None,
                                 db.now(), codigo))
                audit("NT_MODELO_AJUSTADO", "nt_modelos", codigo,
                      {"tamanho": len(corpo.strip())})
                flash("Modelo do ato gravado. Ele vale para o próximo ato aberto.",
                      "success")
            return redirect(url_for("notas_modelos_de_atos", codigo=codigo))

        busca = (request.args.get("busca") or "").strip()
        with db.connect() as con:
            con.row_factory = __import__("sqlite3").Row
            params: list = []
            filtro = "WHERE ativo=1"
            if busca:
                filtro += " AND (nome LIKE ? OR codigo LIKE ? OR tipo LIKE ?)"
                params.extend([f"%{busca}%"] * 3)
            modelos = [dict(r) for r in con.execute(
                f"SELECT * FROM nt_modelos {filtro} ORDER BY tipo,nome_norm", params)]
            if codigo:
                atual = con.execute("SELECT * FROM nt_modelos WHERE codigo=?",
                                    (codigo,)).fetchone()
            else:
                atual = modelos[0] if modelos else None
        atual = dict(atual) if atual else None
        return render_template("notas_modelos_de_atos.html", modelos=modelos,
                               atual=atual, busca=busca)
