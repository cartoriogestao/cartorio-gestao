"""As telas dos avisos de andamento ao cliente — o sim do cliente, o pronto, a fila.

    «para saber do andamento do protocolo, caso deseje» — o oficial, 25/10/2026

A TELA NÃO MANDA NADA
    Ela grava o consentimento, a marca de pronto para retirar e mostra a fila.
    Quem manda é o despachante da automação (`andamento_avisos.rodar`), fora do
    servidor: um e-mail dentro da requisição seguraria o balcão até o prazo do
    SMTP (20 s).

QUEM MEXE
    Marcar e desmarcar o aviso, e o pronto para retirar, é de quem pratica ato
    (ADMIN, MANAGER, USER); o AUDITOR vê. A fila geral é do ADMIN e do gerente.
    Tudo o que grava vai à auditoria, com o endereço mascarado.
"""
from __future__ import annotations

from datetime import datetime

from flask import abort, flash, redirect, render_template, request, url_for

import andamento_avisos as AA
import andamento_schema as AS
from bd_nativo import banco
from serventia import mascarar_email, mascarar_telefone

VEEM = ("ADMIN", "MANAGER", "USER", "AUDITOR")
GRAVAM = ("ADMIN", "MANAGER", "USER")
ENTIDADE = {AS.PROTOCOLO_GERAL: "PROTOCOLO", AS.PRENOTACAO: "RI_PROTOCOLO"}


def mascarar(canal: str, destino: str) -> str:
    return mascarar_email(destino) if canal == AS.EMAIL else mascarar_telefone(destino)


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    usuario_nome = app.extensions["usuario_nome"]

    # O papel CAIXA_AVISO_ANDAMENTO se confere com os claros dele, e não com o
    # boneco geral da tela de Modelos — a régua de `wa_textos`.
    app.extensions.setdefault("conferidores_de_modelo", {})[AA.MODELO] = AA.conferir
    import modelos_elementos as ELEM
    ELEM.CONFERIDORES[AA.MODELO] = AA.conferir

    def _avisos_do_registro(con, origem: str, origem_id: int) -> list[dict]:
        """O que saiu (ou não) por este registro, ou pelo sim dado nele."""
        return banco(con).ler(
            """SELECT a.* FROM av_avisos a
                LEFT JOIN av_consentimentos c ON c.id = a.consentimento_id
                WHERE (a.origem=%s AND a.origem_id=%s) OR (c.origem=%s AND c.origem_id=%s)
                ORDER BY a.id DESC LIMIT 100""",
            (origem, int(origem_id), origem, int(origem_id)))

    def _tela(origem: str, origem_id: int):
        endpoint = ("andamento_protocolo_geral" if origem == AS.PROTOCOLO_GERAL
                    else "andamento_prenotacao")
        if request.method == "POST":
            acao = (request.form.get("acao") or "").strip()
            canal = (request.form.get("canal") or "").strip().upper()
            agora = datetime.now()
            quem = (usuario_nome() or "").strip()
            try:
                with db.transaction() as con:
                    if acao == "consentir":
                        feito = AA.consentir(con, origem, origem_id, canal, quem=quem, agora=agora)
                        detalhe = {"canal": canal, "destino": mascarar(canal, feito["destino"])}
                    elif acao == "revogar":
                        feito = AA.revogar(con, origem, origem_id, canal, quem=quem, agora=agora)
                        detalhe = {"canal": canal}
                    elif acao in ("pronto", "desfazer_pronto") and origem == AS.PROTOCOLO_GERAL:
                        if acao == "pronto":
                            feito = AA.marcar_pronto(con, origem_id, quem=quem, agora=agora)
                        else:
                            feito = AA.desmarcar_pronto(con, origem_id)
                        detalhe = {"numero": feito.get("numero")}
                    else:
                        raise AA.AndamentoError("Ação desconhecida.")
            except AA.AndamentoError as erro:
                flash(str(erro), "danger")
                return redirect(url_for(endpoint, protocolo_id=origem_id))
            audit(f"ANDAMENTO_{acao.upper()}", ENTIDADE[origem], origem_id, detalhe)
            mensagens = {
                "consentir": f"Aviso por {AS.NOME_DO_CANAL.get(canal, canal)} marcado: o "
                             "consentimento do cliente ficou gravado com a data e o seu nome.",
                "revogar": (f"Aviso por {AS.NOME_DO_CANAL.get(canal, canal)} desmarcado. O que "
                            "estava na fila não sai mais." if feito else
                            "Este canal já não estava marcado."),
                "pronto": "Protocolo marcado como pronto para retirar. Se o cliente pediu o "
                          "aviso, ele sai na próxima rodada da automação.",
                "desfazer_pronto": "A marca de pronto para retirar foi retirada.",
            }
            flash(mensagens[acao], "success")
            return redirect(url_for(endpoint, protocolo_id=origem_id))

        with db.connect() as con:
            try:
                reg = AA.registro(con, origem, origem_id)
            except AA.AndamentoError:
                abort(404)
            todos = AA.consentimentos(con, origem, origem_id)
            ligados = []
            if origem == AS.PROTOCOLO_GERAL and reg.get("ri_protocolo_id"):
                ligados.append((AS.PRENOTACAO, int(reg["ri_protocolo_id"])))
            elif origem == AS.PRENOTACAO:
                ligados.extend((AS.PROTOCOLO_GERAL, int(c["id"])) for c in banco(con).ler(
                    "SELECT id FROM cx_protocolos WHERE ri_protocolo_id=%s", (int(origem_id),)))
            avisos = _avisos_do_registro(con, origem, origem_id)
        ativos = {c["canal"]: c for c in todos if c["ativo"]}
        return render_template(
            "andamento_registro.html", reg=reg, origem=origem, origem_id=origem_id,
            endpoint=endpoint, ativos=ativos, historico=todos, avisos=avisos, ligados=ligados,
            protesto=AA.e_protesto(reg), AS=AS, selo=AS.selo, mascarar=mascarar,
            SEM_MODELO_DA_META=AA.SEM_MODELO_DA_META)

    @app.route("/andamento/protocolo-geral/<int:protocolo_id>", methods=["GET", "POST"])
    @roles_required(*VEEM)
    @roles_required(*GRAVAM, metodos=("POST",))
    def andamento_protocolo_geral(protocolo_id: int):
        return _tela(AS.PROTOCOLO_GERAL, protocolo_id)

    @app.route("/andamento/prenotacao/<int:protocolo_id>", methods=["GET", "POST"])
    @roles_required(*VEEM)
    @roles_required(*GRAVAM, metodos=("POST",))
    def andamento_prenotacao(protocolo_id: int):
        return _tela(AS.PRENOTACAO, protocolo_id)

    @app.route("/andamento")
    @roles_required("ADMIN", "MANAGER")
    def andamento_fila():
        import automacao as AU
        import automacao_avisos as AV
        import serventia as SERV
        situacao = (request.args.get("situacao") or "").strip().upper()
        with db.connect() as con:
            bd = banco(con)
            filtro = "WHERE situacao=%s" if situacao in AS.SITUACOES else ""
            ultimos = bd.ler(f"SELECT * FROM av_avisos {filtro} ORDER BY id DESC LIMIT 200",
                             (situacao,) if filtro else None)
            contagem = {r["situacao"]: int(r["n"]) for r in bd.ler(
                "SELECT situacao, COUNT(*) AS n FROM av_avisos GROUP BY situacao")}
            consentidos = {r["canal"]: int(r["n"]) for r in bd.ler(
                "SELECT canal, COUNT(*) AS n FROM av_consentimentos WHERE ativo=1 GROUP BY canal")}
            processo = AU.por_codigo(con, "AVISOS_ANDAMENTO")
            cfg = AV.configuracao_de_email(con)
            serventia = SERV.dados(db.get_settings)
            exemplo = {"numero": "0000", "data_limite": "2026-12-31", "dias": 3}
            previas = {e: AA.textos(e, exemplo, serventia, con) for e in AS.EVENTOS}
        dias, _tent, eventos = AA._parametros((processo or {}).get("parametros") or {})
        return render_template(
            "andamento_fila.html", ultimos=ultimos, contagem=contagem, consentidos=consentidos,
            processo=processo, email_configurado=bool(cfg["host"]), dias_antes=dias,
            eventos=eventos, previas=previas, situacao=situacao, AS=AS, selo=AS.selo,
            mascarar=mascarar, SEM_MODELO_DA_META=AA.SEM_MODELO_DA_META)
