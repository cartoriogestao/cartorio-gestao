"""AS TELAS DO PAINEL NO CELULAR — e o papel que só entra nelas (26/10/2026).

    «painel do gestor no celular, só com números agregados» — pedido de 26/10/2026

DUAS TELAS
    /painel            os números do dia, da semana e do mês, numa coluna só,
                       para tela de celular. Sem nome, sem CPF, sem teor: é o
                       dicionário de `painel_numeros`, e nada além dele.
    /painel/retrato    só do ADMIN: o endereço da VPS, a chave que assina, a
                       prévia do que sairia e o botão «enviar agora».

O PAPEL «PAINEL» — SÓ AGREGADOS
    É o quinto papel da casa, ao lado de ADMIN, MANAGER, USER e AUDITOR, e o
    único que é definido pelo que NÃO vê. A trava não é rota a rota: metade
    das telas do sistema é só `login_required`, e um papel novo passaria por
    todas elas. Ela mora no `before_request` do app e FECHA POR PADRÃO: quem
    tem o papel PAINEL só alcança os endereços de `ROTAS_DO_PAINEL` — esta
    tela, sair, trocar a própria senha e a verificação em duas etapas. Tela
    nova que alguém crie amanhã nasce fechada para ele, sem ninguém lembrar.

    Fora da lista, o GET volta para o painel (quem digitou um endereço velho
    não fica numa página de erro) e o POST recebe 403 (nada se grava).

POR QUE NÃO UMA «PERMISSÃO» DENTRO DO AUDITOR
    O AUDITOR vê o caixa, os atos, os selos com o nome de quem selou — é o
    papel de quem confere. «Só agregados» é o contrário: quem o tem não deve
    ver nem um nome. Uma marca dentro do AUDITOR obrigaria cada tela que ele
    vê a perguntar pela marca; um papel próprio é trancado num lugar só.
"""
from __future__ import annotations

import json

from flask import (abort, flash, make_response, redirect, render_template,
                   request, url_for)

import painel_numeros as PN
import painel_retrato as PR

#: O papel que só vê os números agregados.
PAPEL_SO_AGREGADOS = "PAINEL"

#: Quem abre o painel. O USER (balcão) fica de fora: a receita da casa não é
#: número do balcão — é do oficial, do gerente e de quem confere.
QUEM_VE = ("ADMIN", "MANAGER", "AUDITOR", PAPEL_SO_AGREGADOS)

#: Os endereços que o papel PAINEL alcança — e mais nenhum. Os da verificação
#: em duas etapas estão aqui porque o Gestor pode exigi-la deste papel, e quem
#: não alcança a tela de cadastrar o código fica trancado do lado de fora.
ROTAS_DO_PAINEL = frozenset({
    "painel_celular", "logout", "login", "static", "minha_senha",
    "login_dois_fatores", "login_dois_fatores_cadastrar",
    "dois_fatores", "dois_fatores_iniciar", "dois_fatores_cancelar",
    "dois_fatores_confirmar", "dois_fatores_desativar", "dois_fatores_codigos",
})


def so_agregados(papel) -> bool:
    return str(papel or "").upper() == PAPEL_SO_AGREGADOS


def destino_do_papel_painel(papel, endpoint, metodo) -> str | None:
    """O que a guarda do app faz com este pedido. Só calcula.

    None = segue; "painel" = volta para o painel; "recusa" = 403.
    """
    if not so_agregados(papel) or endpoint in ROTAS_DO_PAINEL:
        return None
    return "painel" if metodo in ("GET", "HEAD") else "recusa"


def registrar_rotas(app, db, login_required, roles_required, audit):
    pasta = app.config["DATA_DIR"]

    def _sem_cache(resposta):
        resposta = make_response(resposta)
        resposta.headers["Cache-Control"] = "no-store"
        return resposta

    @app.route("/painel")
    @login_required
    @roles_required(*QUEM_VE)
    def painel_celular():
        periodo = request.args.get("p", "dia")
        if periodo not in PN.PERIODOS:
            periodo = "dia"
        numeros = PN.montar(db)
        return _sem_cache(render_template(
            "painel_celular.html", n=numeros, periodo=periodo,
            p=numeros["periodos"][periodo], periodos=PN.PERIODOS,
            rotulos=PN.ROTULO_DO_PERIODO, atribuicoes=PN.ATRIBUICOES,
            outras=PN.OUTRAS, reais=PN.reais,
            so_agregados=so_agregados(app.extensions["usuario_papel"]())))

    @app.route("/painel/retrato", methods=["GET", "POST"])
    @login_required
    @roles_required("ADMIN")
    def painel_retrato_tela():
        if request.method == "POST":
            acao = request.form.get("acao", "")
            try:
                if acao == "salvar":
                    PR.salvar_configuracao(
                        db, url=request.form.get("url", ""),
                        ligado=request.form.get("ligado") == "1")
                    audit("PAINEL_RETRATO_CONFIGURADO", "PAINEL", None,
                          {"url": request.form.get("url", "").strip()[:200],
                           "ligado": request.form.get("ligado") == "1"})
                    flash("Configuração do retrato guardada.", "success")
                elif acao == "gerar_chave":
                    publica = PR.gerar_chave(pasta, trocar=request.form.get("trocar") == "1")
                    audit("PAINEL_RETRATO_CHAVE_GERADA", "PAINEL", None,
                          {"impressao": PR.impressao(publica)})
                    flash("Chave gerada. Cole a chave pública na VPS antes de "
                          "enviar o primeiro retrato.", "success")
                elif acao == "enviar":
                    feito = PR.empurrar(db, pasta, forcar=True)
                    audit("PAINEL_RETRATO_ENVIADO", "PAINEL", None,
                          {k: feito.get(k) for k in ("ok", "status", "bytes")})
                    if feito.get("ok"):
                        flash("Retrato enviado à VPS.", "success")
                    else:
                        flash("O retrato não foi aceito: "
                              + str(feito.get("motivo") or ""), "danger")
                else:
                    abort(400)
            except PR.RetratoError as erro:
                flash(str(erro), "danger")
            return redirect(url_for("painel_retrato_tela"))
        previa = None
        if request.args.get("ver") == "previa":
            numeros = PN.montar(db)
            try:
                PR.conferir_que_e_so_agregado(numeros)
                previa = json.dumps(numeros, ensure_ascii=False, indent=2,
                                    sort_keys=True)
            except PR.RetratoError as erro:
                flash(str(erro), "danger")
        publica = PR.chave_publica(pasta)
        return _sem_cache(render_template(
            "painel_retrato.html", conf=PR.configuracao(db), publica=publica,
            impressao=PR.impressao(publica), previa=previa))
