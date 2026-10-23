"""As telas dos modelos do escrevente — a lista, o editor e o documento montado.

A TELA NÃO REPETE A REGRA DO DOMÍNIO. Ela só *oferece*; quem *recusa* é
`rc_modelos_livres.py`, e há teste que manda a ação errada direto para a função.

**ESCREVER MODELO E IMPRIMIR DOCUMENTO SÃO DUAS PERMISSÕES.** Emitir é do
balcão — é o trabalho do dia. **Escrever o modelo não é**: uma vírgula fora do
lugar aqui sai em todo documento daquele tipo até alguém reparar, e é a mesma
razão pela qual a tela dos papéis da casa (`modelos_web`) é de ADMIN e gerente.

**CONFERIR E IMPRIMIR SÃO DOIS BOTÕES.** A tela do documento mostra o texto
montado **e a lista dos claros que saíram vazios** antes de qualquer impressão.
No E-Ofício o claro sem dado virava espaço em branco no papel, e quem descobria
era quem lia o documento depois de assinado.

**A LISTA VAZIA DIZ POR QUÊ.** Assento de espécie que não tem modelo cadastrado
mostra a faixa que explica, e o caminho para cadastrar — lista vazia calada faz
o escrevente concluir que a tela está quebrada.
"""
from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for

import rc_modelos_livres as MOD
from bd_nativo import banco
from rc_modelos_livres_schema import ESPECIES, NOME_DA_ESPECIE

QUEM_VE: tuple[str, ...] = ("ADMIN", "MANAGER", "USER")
QUEM_ESCREVE: tuple[str, ...] = ("ADMIN", "MANAGER")


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """Pendura as telas dos modelos do escrevente no app já construído."""

    usuario_nome = app.extensions["usuario_nome"]
    papel_do_usuario = app.extensions["usuario_papel"]

    def _serventia() -> dict:
        """A serventia como os claros a leem.

        **AS DUAS GRAFIAS DE PROPÓSITO.** `serventia.dados` devolve
        `serventia_titular`/`ri_cidade`; quem assina sai da regra viva — a
        substituta se houver, senão o titular —, que é a mesma de
        `atribuicoes_web._servent`. Juntar as duas num dicionário só evita que
        o papel avulso e o termo do mesmo assento discordem sobre quem
        responde pela casa.
        """
        from serventia import dados as dados_serventia
        s = dict(dados_serventia(db.get_settings))
        substituta = (db.get_setting("ri_substituta", "") or "").strip()
        s["registrador"] = substituta or s.get("serventia_titular", "")
        s["titulo"] = ("Tabeliã Registradora Substituta" if substituta
                       else s.get("serventia_titulo", ""))
        return s

    # ==================================================== a lista e o cadastro

    @app.route("/rcpn/modelos", methods=["GET", "POST"])
    @login_required
    @roles_required(*QUEM_VE)
    def rcpn_modelos():
        """Os modelos cadastrados, e o cadastro de um novo."""
        if request.method == "POST":
            if not _pode_escrever():
                flash("Só o oficial e o gerente cadastram modelo.", "danger")
                return redirect(url_for("rcpn_modelos"))
            especie = (request.form.get("especie") or "").strip().upper()
            nome = request.form.get("nome") or ""
            corpo = request.form.get("corpo") or ""
            try:
                with db.transaction() as con:
                    novo = MOD.criar(con, especie=especie, nome=nome,
                                     corpo=corpo, quem=usuario_nome(),
                                     agora=db.now())
                audit("MODELO_LIVRE_CRIADO", "rc_modelos_livres", str(novo),
                      {"especie": especie, "nome": nome.strip()})
                flash("Modelo cadastrado.", "success")
                return redirect(url_for("rcpn_modelo", modelo_id=novo))
            except MOD.ModeloLivreError as erro:
                flash(str(erro), "danger")
            return redirect(url_for("rcpn_modelos", especie=especie))

        especie = (request.args.get("especie") or "").strip().upper()
        if especie and especie not in ESPECIES:
            especie = ""
        with db.connect() as con:
            modelos = MOD.listar(con, especie=especie)
            quantos = MOD.quantos_por_especie(con)
        return render_template(
            "rcpn_modelos.html", modelos=modelos, especie=especie,
            especies=[{"chave": e, "nome": NOME_DA_ESPECIE[e]}
                      for e in ESPECIES],
            quantos=quantos, pode_escrever=_pode_escrever(),
            nome_da_especie=NOME_DA_ESPECIE)

    def _pode_escrever() -> bool:
        """Se quem está logado pode mexer no texto dos modelos.

        **A GUARDA DE VERDADE É O `roles_required` DA ROTA QUE ESCREVE.** Este
        aqui só decide se a tela *mostra* o botão: esconder link não protege
        rota, e é a regra que `modulos_ligados` já escreve.
        """
        return str(papel_do_usuario() or "").upper() in QUEM_ESCREVE

    # ============================================================== o editor

    @app.route("/rcpn/modelos/<int:modelo_id>", methods=["GET", "POST"])
    @login_required
    @roles_required(*QUEM_VE)
    def rcpn_modelo(modelo_id: int):
        """Um modelo: o texto, a lista de claros e a conversão do E-Ofício."""
        if request.method == "POST":
            if not _pode_escrever():
                flash("Só o oficial e o gerente mexem no modelo.", "danger")
                return redirect(url_for("rcpn_modelo", modelo_id=modelo_id))
            acao = (request.form.get("acao") or "salvar").strip()
            corpo = request.form.get("corpo") or ""
            nome = request.form.get("nome") or ""
            try:
                if acao in ("ativar", "desativar"):
                    with db.transaction() as con:
                        MOD.ativar(con, modelo_id, ativo=(acao == "ativar"),
                                   quem=usuario_nome(), agora=db.now())
                    audit("MODELO_LIVRE_" + acao.upper(), "rc_modelos_livres",
                          str(modelo_id), {})
                    flash("Modelo ativado." if acao == "ativar"
                          else "Modelo desativado — ele sai da lista de quem "
                               "emite e continua guardado.", "success")
                else:
                    with db.transaction() as con:
                        MOD.salvar(con, modelo_id, nome=nome, corpo=corpo,
                                   quem=usuario_nome(), agora=db.now())
                    audit("MODELO_LIVRE_AJUSTADO", "rc_modelos_livres",
                          str(modelo_id), {"tamanho": len(corpo.strip())})
                    flash("Modelo gravado. Ele vale no próximo documento.",
                          "success")
            except MOD.ModeloLivreError as erro:
                flash(str(erro), "danger")
            return redirect(url_for("rcpn_modelo", modelo_id=modelo_id))

        with db.connect() as con:
            try:
                m = MOD.ler(con, modelo_id)
            except MOD.ModeloLivreError as erro:
                flash(str(erro), "warning")
                return redirect(url_for("rcpn_modelos"))
        return render_template(
            "rcpn_modelo.html", m=m,
            nome_da_especie=NOME_DA_ESPECIE[m["especie"]],
            vocabulario=MOD.vocabulario(m["especie"]),
            escritos=MOD.claros_do_texto(m["corpo"]),
            erro=MOD.conferir_corpo(m["especie"], m["corpo"]),
            pode_escrever=_pode_escrever(), convertido=None)

    @app.route("/rcpn/modelos/<int:modelo_id>/converter", methods=["POST"])
    @login_required
    @roles_required(*QUEM_ESCREVE)
    def rcpn_modelo_converter(modelo_id: int):
        """Traduz um texto colado do E-Ofício. NÃO GRAVA.

        **CONVERTER E GRAVAR SÃO DOIS PASSOS**, e a razão é o que a conversão
        não sabe fazer: os claros sem de-para **continuam escritos no texto** e
        aparecem numa lista. Gravar direto esconderia essa lista atrás de uma
        recusa genérica, e o oficial não saberia o que perdeu.
        """
        with db.connect() as con:
            try:
                m = MOD.ler(con, modelo_id)
            except MOD.ModeloLivreError as erro:
                flash(str(erro), "warning")
                return redirect(url_for("rcpn_modelos"))

        bruto = request.form.get("do_eoficio") or ""
        r = MOD.traduzir_do_eoficio(bruto, m["especie"])
        if r["nao_convertidos"]:
            flash("Não soube converter, e deixei escrito no texto: "
                  + ", ".join("@" + c for c in r["nao_convertidos"])
                  + ". Troque à mão pelo claro certo, ou apague.", "warning")
        else:
            flash(f"Converti {len(r['convertidos'])} claros. "
                  "Confira o texto e grave.", "success")
        return render_template(
            "rcpn_modelo.html", m=m,
            nome_da_especie=NOME_DA_ESPECIE[m["especie"]],
            vocabulario=MOD.vocabulario(m["especie"]),
            escritos=MOD.claros_do_texto(r["texto"]),
            erro=MOD.conferir_corpo(m["especie"], r["texto"]),
            pode_escrever=True, convertido=r)

    # ================================================ o documento de um assento

    @app.route("/rcpn/assentos/<int:assento_id>/modelos")
    @login_required
    @roles_required(*QUEM_VE)
    def rcpn_modelos_do_assento(assento_id: int):
        """Quais modelos servem a este assento."""
        with db.connect() as con:
            try:
                modelos = MOD.para_o_assento(con, assento_id)
            except MOD.ModeloLivreError as erro:
                flash(str(erro), "warning")
                return redirect(url_for("rcpn_assentos"))
            a = banco(con).um(
                "SELECT id, especie, nome, numero FROM rc_assentos "
                "WHERE id = %s", (assento_id,))
        return render_template(
            "rcpn_modelos.html", modelos=modelos, especie=a["especie"],
            especies=[{"chave": e, "nome": NOME_DA_ESPECIE[e]}
                      for e in ESPECIES],
            quantos={}, pode_escrever=_pode_escrever(),
            nome_da_especie=NOME_DA_ESPECIE, assento=a)

    @app.route("/rcpn/assentos/<int:assento_id>/modelos/<int:modelo_id>")
    @login_required
    @roles_required(*QUEM_VE)
    def rcpn_modelo_emitir(assento_id: int, modelo_id: int):
        """O documento montado — para conferir, e só depois imprimir. Só lê."""
        with db.connect() as con:
            try:
                r = MOD.montar(con, modelo_id, assento_id,
                               serventia=_serventia(), hoje=db.now())
            except MOD.ModeloLivreError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("rcpn_modelos_do_assento",
                                        assento_id=assento_id))
            rotulos = {c["nome"]: c["rotulo"]
                       for c in MOD.vocabulario(r["modelo"]["especie"])}
        return render_template(
            "rcpn_modelo_documento.html", r=r, assento_id=assento_id,
            rotulos=rotulos, fmt_date=fmt_date)
