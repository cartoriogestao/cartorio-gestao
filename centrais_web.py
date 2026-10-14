"""O PAINEL DE STATUS DAS CENTRAIS — filas, últimas falhas, e o cofre.

Construído em 05/10/2026, marco (a) da base comum das integrações.

**ESTA TELA SÓ LÊ — com UMA exceção, e ela é local.** Ela mostra o que está
na fila genérica (`centrais_fila`), as últimas falhas, os últimos erros do
log (`centrais_log`) e **se** cada credencial está informada (de
`centrais_cred.situacao()`, que nunca devolve segredo). A exceção é o botão
**Reprocessar**, que devolve à fila um item que falhou — e **não manda nada à
Central**: quem manda é o processador do domínio, na próxima passada.

**NÃO HÁ BOTÃO DE «TESTAR CONEXÃO» AQUI**, de propósito: cada Central tem o
seu teste seguro (a CRA usa `BuscarApresentante` porque pedir remessa MARCA
a remessa lá), e quem sabe qual é o seguro é a tela da própria Central. Um
botão genérico seria o primeiro a errar.

**ROTA PRÓPRIA, LIGADA A PARTIR DE CONFIGURAÇÕES.** A seção «Centrais» de
`/configuracoes` é só do ADMIN e grava credencial; o painel é de leitura e
serve também ao MANAGER e ao AUDITOR. Misturar os dois faria a tela de
credencial abrir para quem só precisa ver a fila.
"""
from __future__ import annotations

from flask import current_app, flash, redirect, render_template, request, url_for

import centrais_cred as CENTCRED
import centrais_fila as FILA
import centrais_http as HTTP
import centrais_log as LOG
import centrais_schema as SCH

QUEM_VE_O_PAINEL = ("ADMIN", "MANAGER", "AUDITOR")
QUEM_REPROCESSA = ("ADMIN", "MANAGER")


def _quem() -> str:
    usuario = current_app.extensions.get("current_user")
    try:
        u = usuario() if usuario else None
        # `current_user` devolve `sqlite3.Row`, que nao tem `.get`.
        return str(u["username"] or "") if u else ""
    except Exception:
        return ""


def registrar_rotas(app, db, login_required, roles_required, audit):
    """Pendura o painel das Centrais no app já construído."""

    # O BANCO DO LOG DAS CENTRAIS (marco b): as `*_api.py` nao recebem `con`,
    # e anotam cada chamada por `centrais_log.anotar_resposta` neste banco.
    LOG.ligar_banco(db)

    def central_pedida() -> str:
        pedido = str(request.values.get("central") or "").strip().upper()
        return pedido if pedido in CENTCRED.ARQUIVO_DA_CENTRAL else ""

    @app.route("/centrais/status")
    @login_required
    @roles_required(*QUEM_VE_O_PAINEL)
    def centrais_status():
        """Filas, falhas e credenciais — só leitura."""
        central = central_pedida()
        with db.connect() as con:
            resumo = FILA.resumo_por_central(con)
            falhas = FILA.ultimas_falhas(con, central=central or None)
            erros = LOG.ultimos(con, central=central or None,
                                nivel=SCH.ERRO, limite=20)
            fila = FILA.listar(con, central=central or None, limite=50)
        return render_template(
            "centrais_status.html",
            central=central,
            nomes=CENTCRED.NOME_DA_CENTRAL,
            centrais=list(CENTCRED.ARQUIVO_DA_CENTRAL),
            credenciais=CENTCRED.situacao(),
            resumo=resumo, falhas=falhas, erros=erros, fila=fila,
            situacoes=SCH.SITUACOES,
            reprocessaveis=SCH.SITUACOES_REPROCESSAVEIS,
            http=HTTP.configuracao())

    @app.route("/centrais/status/<int:item_id>/reprocessar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_REPROCESSA)
    def centrais_status_reprocessar(item_id: int):
        """Devolve à fila um item que falhou. LOCAL — não fala com a Central."""
        try:
            with db.transaction() as con:
                FILA.reprocessar(con, item_id, por=_quem() or None)
        except FILA.FilaError as erro:
            flash(str(erro), "warning")
        else:
            audit("CENTRAIS_REPROCESSO", "CENTRAIS_FILA", item_id,
                  {"item_id": item_id})
            flash(f"Item {item_id} devolvido à fila. Nada foi enviado agora — "
                  "ele sai na próxima passada do processador.", "success")
        destino = central_pedida()
        if destino:
            return redirect(url_for("centrais_status", central=destino))
        return redirect(url_for("centrais_status"))
