"""As telas do e-Protocolo do RI pelo ONR — a entrada dos títulos (RI013, P1).

    «pode abrir a P1 do e-Protocolo também»          — o oficial, 24/11/2026

DUAS TELAS E UM BOTÃO, E NENHUM ESCREVE NO ONR
    A fila (na ordem da remessa, com os avisos), a ficha de cada título (o que
    chegou, os imóveis ligados ao acervo, os anexos com a URL e o XML congelado)
    e «Ler agora no ONR», só do ADMIN, que faz a MESMA leitura da rodada da
    central. Prenotar continua sendo na tela da prenotação, como hoje.

O AVISO NO PAINEL
    Quantos títulos esperam prenotação, quantos têm possível contraditório e o
    horário da última leitura bem-sucedida — vermelho quando, com o processo
    ligado e no expediente, passa de uma hora sem leitura (CNN 325). Antes de a
    casa ligar o processo ou fazer a primeira leitura, o painel não mostra nada.

A REDE ACONTECE FORA DE `db.transaction()` — ver `onr_eprotocolo.ler`.
"""
from __future__ import annotations

from datetime import date, datetime

from flask import flash, redirect, render_template, request, url_for

import onr_eprotocolo as EP
import onr_wsoficio as WS
from bd_nativo import ERROS_DO_BANCO
from seguranca_web import numero_digitado

QUEM = ("ADMIN", "MANAGER", "USER", "AUDITOR")
NO_PAINEL = ("ADMIN", "MANAGER", "USER")
ERROS_DO_PAINEL = (*ERROS_DO_BANCO, EP.EProtocoloRIError, ValueError, KeyError,
                   RuntimeError, OSError)


def no_expediente(agora: datetime) -> bool:
    """A janela do processo: dia útil, das 8h às 18h (o `CATALOGO`)."""
    janela = EP.CATALOGO[0]["agenda"]
    inicio, fim = janela["janela"]
    hhmm = agora.strftime("%H:%M")
    return agora.weekday() in janela["dias"] and inicio <= hhmm <= fim


def registrar_rotas(app, db, login_required, roles_required, audit, fmt_date=str):
    current_user = app.extensions["current_user"]

    with db.connect() as con:
        EP.init_schema(con)

    def amb() -> str:
        return EP.ambiente(db.get_setting)

    @app.route("/ri/onr/eprotocolo")
    @roles_required(*QUEM)
    def onr_eprotocolo():
        todos = request.args.get("todos") == "1"
        a = amb()
        with db.connect() as con:
            lista = EP.fila_com_alertas(con, todos=todos, amb=a)
            resumo = EP.resumo_do_painel(con, agora=datetime.now(), amb=a,
                                         processo_ligado=EP.processo_ligado(con),
                                         no_expediente=no_expediente(datetime.now()))
        return render_template("onr_eprotocolo.html", lista=lista, todos=todos, ambiente=a,
                               endereco=WS.BASE[a], credencial=WS.situacao(a), resumo=resumo,
                               processo=EP.CATALOGO[0],
                               rotulo_do_status=EP.rotulo_do_status,
                               rotulo_do_tipo_servico=EP.rotulo_do_tipo_servico)

    @app.route("/ri/onr/eprotocolo/<int:pedido_id>")
    @roles_required(*QUEM)
    def onr_eprotocolo_ficha(pedido_id: int):
        with db.connect() as con:
            try:
                p = EP.pedido(con, pedido_id)
            except EP.EProtocoloRIError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("onr_eprotocolo"))
            avisos = EP.alertas(con, p, p["imoveis"])
        return render_template("onr_eprotocolo_ficha.html", p=p, alertas=avisos,
                               rotulo_do_status=EP.rotulo_do_status,
                               rotulo_do_tipo_servico=EP.rotulo_do_tipo_servico,
                               tipos_de_cobranca=WS.TIPO_COBRANCA_EPROTOCOLO,
                               tipos_de_isencao=WS.TIPO_ISENCAO_EPROTOCOLO)

    @app.route("/ri/onr/eprotocolo/ler", methods=["POST"])
    @roles_required("ADMIN")
    def onr_eprotocolo_ler():
        """A mesma leitura da rodada. SÓ LÊ do lado de lá."""
        digitado = numero_digitado(request.form.get("dias"))
        dias = max(1, min(180, 30 if digitado is None else digitado))
        a = amb()
        try:
            r = EP.ler(db, a, hoje=date.today(), agora=db.now, origem=EP.ORIGEM_TELA, dias=dias)
        except WS.WSOficioError as erro:          # credencial faltando: antes da rede
            flash(str(erro), "danger")
            return redirect(url_for("onr_eprotocolo"))
        audit("ONR_EPROTOCOLO_LIDO", "onr_ep_leituras", r.get("leitura_id"),
              {k: r.get(k) for k in ("situacao", "listados", "novos", "atualizados",
                                     "fichas", "sobraram")} | {"dias": dias})
        if r["situacao"] == "ERRO":
            flash(f"O ONR não respondeu a leitura: {r['erro']}", "danger")
        else:
            msg = (f"e-Protocolo lido ({dias} dias): {r['listados']} na lista, "
                   f"{r['novos']} novo(s), {r['fichas']} ficha(s).")
            if r["sobraram"]:
                msg += f" {r['sobraram']} ficha(s) ficam para a próxima leitura."
            if r["falhas"]:
                msg += " Falhas: " + " | ".join(r["falhas"])
            flash(msg, "warning" if r["falhas"] else "ok")
        return redirect(url_for("onr_eprotocolo"))

    @app.context_processor
    def _onr_eprotocolo_no_painel() -> dict:
        """O aviso no painel — só no painel, só para o balcão e a gerência."""
        from flask import session
        vazio = {"onr_eprotocolo_no_painel": None}
        try:
            if (request.endpoint or "") != "dashboard" or not session.get("user_id"):
                return vazio
        except RuntimeError:
            return vazio
        u = current_user()
        if not u or u["role"] not in NO_PAINEL:
            return vazio
        try:
            agora = datetime.now()
            with db.connect() as con:
                ligado = EP.processo_ligado(con)
                r = EP.resumo_do_painel(con, agora=agora, amb=amb(), processo_ligado=ligado,
                                        no_expediente=no_expediente(agora))
        except ERROS_DO_PAINEL:
            return vazio          # tela não cai por causa de quadro do painel
        if not (ligado or r["ultima"] or r["abertos"]):
            return vazio
        return {"onr_eprotocolo_no_painel": r}
