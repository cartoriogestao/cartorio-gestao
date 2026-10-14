"""As telas do e-Proclamas — a fila, a conferência e o envio.

A TELA NÃO REPETE A REGRA DO DOMÍNIO. Ela só *oferece*; quem *recusa* é
`proclamas.py`, e há teste que manda o envio fora de ordem direto para a
função.

**CONFERIR E ENVIAR SÃO DOIS BOTÕES**, e é a forma de conferir/receber da
remessa da CRA — pela mesma razão: o que sobe **publica edital e é cobrado**.
Quem clica em «Enviar» já viu, na tela anterior, exatamente o que vai.

**E ENVIAR NÃO É DO BALCÃO.** Conferir é de quem atende; mandar à Central é do
oficial e do gerente — a mesma separação da ajuda do Claude (consultar abre,
configurar não) e da CENPROT.

O TESTE DE LIGAÇÃO NÃO PRECISA DE CREDENCIAL, e isso é medido: o
`GET /api/proclama/health` respondeu HTTP 200 **sem cabeçalho de autenticação
nenhum**. É a única coisa que esta casa pode conferir antes do cadastro no
IdRC — e a tela diz, com todas as letras, que ele **não** prova o token.
"""
from __future__ import annotations

import sqlite3

from flask import flash, redirect, render_template, request, url_for

import centrais_cred as CRED
import habilitacao as HAB
import onrcpn_api as API
import proclamas as PROC

# QUEM VÊ E QUEM MANDA. Ver o cabeçalho — enviar não é do balcão.
QUEM_CONFERE = ("ADMIN", "MANAGER", "USER")
QUEM_ENVIA = ("ADMIN", "MANAGER")

# AS RECUSAS QUE VIRAM AVISO NA TELA, e não HTTP 500.
#
#   `CredencialError` está aqui porque a sua falta é o caso mais comum numa
#   integração nova — e foi exatamente o que o teste de tela pegou na CENPROT,
#   em cinco rotas de uma vez.
RECUSAS_DO_BALCAO = (PROC.ProclamaError, API.OnrcpnError,
                     HAB.HabilitacaoError, CRED.CredencialError)


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """Pendura as telas do e-Proclamas no app já construído."""

    usuario_nome = app.extensions["usuario_nome"]

    def agora() -> str:
        return db.now()

    def _cns() -> str:
        return str(db.get_setting("serventia_cns", "") or "").strip() \
            or str(db.get_setting("ri_cns", "") or "").strip()

    def _marcado(nome: str, padrao: bool = True) -> bool:
        if request.method != "POST":
            return padrao
        return bool(request.form.get(nome))

    # -------------------------------------------------------------- a fila

    @app.route("/rcpn/proclamas")
    @roles_required(*QUEM_CONFERE)
    def rcpn_proclamas():
        """As habilitações com edital publicado e que a Central ainda não tem."""
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            fila = PROC.pendentes(con)
        return render_template(
            "rcpn_proclamas.html", fila=fila, cns=_cns(),
            ambiente=PROC.ambiente(),
            tem_credencial=API.tem_credencial(),
            arquivo_da_credencial=str(CRED.caminho(CRED.ONRCPN)),
            base=API.BASE)

    @app.route("/rcpn/proclamas/testar", methods=["POST"])
    @roles_required(*QUEM_CONFERE)
    def rcpn_proclamas_testar():
        """Pergunta à Central se ela está no ar. **Não prova o token.**

        `health` não leva autenticação — medido. Quem confundir as duas coisas
        conclui que a credencial está boa porque a Central respondeu, e é
        justamente por isso que a tela separa as duas frases.
        """
        try:
            r = API.esta_no_ar()
        except RECUSAS_DO_BALCAO as erro:
            flash(str(erro), "danger")
        else:
            if r["no_ar"]:
                flash(f"O e-Proclamas respondeu: {r['resposta']} "
                      f"(HTTP {r['status']}). Isto prova a ligação — **não** "
                      f"prova o token, porque esta chamada não o usa.", "ok")
            else:
                flash(f"O e-Proclamas respondeu HTTP {r['status']}: "
                      f"{r['resposta']}", "warning")
        return redirect(url_for("rcpn_proclamas"))

    # ------------------------------------------------------- a conferência

    @app.route("/rcpn/proclamas/<int:habilitacao_id>", methods=["GET", "POST"])
    @roles_required(*QUEM_CONFERE)
    def rcpn_proclama(habilitacao_id: int):
        """O que iria para a Central, antes de ir. NÃO GRAVA E NÃO ENVIA."""
        publicacao = _marcado("publicacao")
        livro = _marcado("livro_eletronico")
        cpf_fatura = (request.values.get("cpf_fatura") or "").strip()
        nome_fatura = (request.values.get("nome_fatura") or "").strip()
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            h = con.execute("SELECT * FROM hc_habilitacoes WHERE id=?",
                            (habilitacao_id,)).fetchone()
            if h is None:
                flash("Habilitação não encontrada.", "danger")
                return redirect(url_for("rcpn_proclamas"))
            try:
                conferido = PROC.conferir(
                    con, habilitacao_id, cns=_cns(), publicacao=publicacao,
                    livro_eletronico=livro, cpf_fatura=cpf_fatura or None,
                    nome_fatura=nome_fatura or None)
            except RECUSAS_DO_BALCAO as erro:
                flash(str(erro), "danger")
                return redirect(url_for("rcpn_proclamas"))
            enviados = PROC.enviados_de(con, habilitacao_id)
        return render_template(
            "rcpn_proclama.html", h=dict(h), c=conferido, enviados=enviados,
            publicacao=publicacao, livro_eletronico=livro,
            cpf_fatura=cpf_fatura, nome_fatura=nome_fatura,
            tem_credencial=API.tem_credencial(), base=API.BASE,
            arquivo_da_credencial=str(CRED.caminho(CRED.ONRCPN)))

    # ------------------------------------------------------------- o envio

    @app.route("/rcpn/proclamas/<int:habilitacao_id>/enviar", methods=["POST"])
    @roles_required(*QUEM_ENVIA)
    def rcpn_proclama_enviar(habilitacao_id: int):
        """Manda o proclama à Central. **É a única rota que publica.**

        `proclamas.enviar` recebe `db` e não `con`: a chamada de rede acontece
        FORA de transação, e a gravação é uma transação curta depois.
        """
        publicacao = bool(request.form.get("publicacao"))
        livro = bool(request.form.get("livro_eletronico"))
        try:
            feito = PROC.enviar(
                db, habilitacao_id, cns=_cns(), agora=agora(),
                publicacao=publicacao, livro_eletronico=livro,
                cpf_fatura=(request.form.get("cpf_fatura") or "").strip() or None,
                nome_fatura=(request.form.get("nome_fatura") or "").strip() or None,
                usuario=usuario_nome())
        except RECUSAS_DO_BALCAO as erro:
            # **A RECUSA DA CENTRAL NÃO É ERRO DE PROGRAMA**, e o envio pode ter
            # ficado gravado: `proclamas.enviar` grava antes de levantar, para
            # a chamada que aconteceu não sumir do rastro.
            flash(str(erro), "danger")
            return redirect(url_for("rcpn_proclama",
                                    habilitacao_id=habilitacao_id))
        audit("rcpn_proclama_enviado",
              f"habilitação {habilitacao_id} · lote {feito['lote']} · "
              f"{feito['ambiente']}")
        flash(f"O proclama subiu ao e-Proclamas. Número do lote que a Central "
              f"devolveu: {feito['lote']}.", "ok")
        return redirect(url_for("rcpn_proclama",
                                habilitacao_id=habilitacao_id))
