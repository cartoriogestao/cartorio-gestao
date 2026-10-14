"""
A tela de configuracao do selador.

O QUE ELA RESOLVE
    O selador desta serventia esta em `https://192.168.0.200:443` — uma maquina
    da rede local do escritorio. Isso nao cabe em constante no codigo: cada
    casa sela num lugar. A tela e o lugar onde o endereco, o usuario e a senha
    entram.

    E tem o botao que evita a pior parte: **importar do E-Oficio**. A
    configuracao ja esta na casa, em `tbSeladorConfiguracao`. Pedir para o
    escrevente abrir a tela do E-Oficio, ler a senha e redigitar aqui seria
    mais exposicao, nao menos.

O QUE ELA NUNCA MOSTRA
    A senha. Nem mascarada em campo `password` preenchido, nem na auditoria,
    nem na mensagem de sucesso. A tela diz *que existe* uma credencial e
    *quando* foi gravada; o resto e do arquivo.
"""
from __future__ import annotations

import selos_emitidos as SEM

import sqlite3
from datetime import datetime
from pathlib import Path

from flask import flash, redirect, render_template, request, url_for

import selador
import selador_cliente as CL
import selador_config as SC


def _legivel(sha256: str | None) -> str:
    """`AB:CD:…` — o jeito como impressão digital se confere a olho."""
    if not sha256:
        return ""
    return ":".join(sha256[i:i + 2] for i in range(0, len(sha256), 2)).upper()


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """Pendura a tela do selador no app ja construido."""

    def agora() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def pasta_de_dados() -> Path:
        return Path(app.config["DATA_DIR"])

    def acervo() -> Path:
        return pasta_de_dados() / "acervo_eoficio.sqlite3"

    usuario_nome = app.extensions["usuario_nome"]

    # -------------------------------------- o razao dos selos, pesquisavel
    #
    # **RELATO #33 do oficial**: «preciso que seja possivel pesquisar os selo
    # emitidos por data, especialidade, usuario». Os tres campos existem em
    # `sd_selos` — e o terceiro com outro nome, `obtido_por`, que foi o que me
    # fez procurar por `usuario` e nao achar.
    #
    # **NAO E A TELA DE SELOS DO RI.** Aquela reune o selo de dentro dos atos
    # do Registro de Imoveis; esta e o RAZAO, com as seis atribuicoes juntas —
    # 26.135 linhas. Sao perguntas diferentes, e cada tela diz a que veio.

    @app.route("/selos")
    @roles_required("ADMIN", "MANAGER", "AUDITOR")
    def selos_emitidos_lista():
        """O razão dos selos, pesquisável — relato #33. **SÓ LÊ.**

        **É A ÚNICA TELA DO RAZÃO DESDE 15/09/2026.** Havia duas com o mesmo
        nome, e elas discordavam em 7.762 selos sobre o que é «não usado». O que
        a antiga tinha de melhor — o tipo do ato, os agrupamentos por dia e mês,
        e a busca por pedaço — está aqui. `/relatorios/selos` continua
        respondendo, e aponta para cá.
        """
        f = {
            "inicio": (request.args.get("inicio") or "").strip(),
            "fim": (request.args.get("fim") or "").strip(),
            "atribuicao": (request.args.get("atribuicao") or "").strip(),
            "caminho": (request.args.get("caminho") or "").strip(),
            "quem": (request.args.get("quem") or "").strip(),
            "tipo": (request.args.get("tipo") or "").strip(),
            "numero": (request.args.get("numero") or "").strip(),
            "situacao": (request.args.get("situacao") or "").strip(),
        }
        agrupar = (request.args.get("agrupar") or "usuario").strip()
        try:
            pagina = int(request.args.get("pagina") or 1)
        except ValueError:
            pagina = 1
        with db.connect() as con:
            con.row_factory = sqlite3.Row
            try:
                lista = SEM.procurar(con, pagina=pagina, **f)
                conta = SEM.resumo(con, **f)
                grupos = SEM.por_grupo(con, agrupar, **f)
            except SEM.SeloEmitidoError as erro:
                flash(str(erro), "danger")
                return redirect(url_for("selos_emitidos_lista"))
            escolhas = SEM.opcoes(con)
        return render_template("selos_emitidos.html", f=f, lista=lista,
                               conta=conta, escolhas=escolhas,
                               grupos=grupos, agrupar=agrupar, norma=SEM)

    @app.route("/selador", methods=["GET", "POST"])
    @roles_required("ADMIN", "MANAGER")
    def selador_config():
        """Onde selamos, com que usuário, e se está tudo no lugar."""
        if request.method == "POST":
            acao = (request.form.get("acao") or "").strip()
            try:
                if acao == "importar":
                    with db.transaction() as con:
                        resumo = SC.importar_do_eoficio(
                            con, acervo(), pasta_de_dados(), agora=agora(),
                            usuario_do_sistema=usuario_nome())
                    audit("SELADOR_IMPORTADO", "SELADOR", None,
                          {k: v for k, v in resumo.items() if k != "senha"})
                    aviso = (" O endereço é da rede local: o sistema só vai "
                             "selar de dentro do escritório."
                             if resumo["na_rede_local"] else "")
                    flash(f"Configuração trazida do E-Ofício: "
                          f"{resumo['base_url']}, usuário {resumo['usuario']}. "
                          f"A senha foi guardada fora do banco.{aviso}",
                          "success")

                elif acao == "gravar":
                    with db.transaction() as con:
                        SC.gravar(
                            con,
                            base_url=request.form.get("base_url"),
                            base_homologacao=request.form.get("base_homologacao"),
                            auth_url=request.form.get("auth_url"),
                            ambiente=request.form.get("ambiente") or "PRODUCAO",
                            usuario=request.form.get("usuario"),
                            origem="MANUAL", agora=agora(),
                            usuario_do_sistema=usuario_nome())
                    senha = request.form.get("senha") or ""
                    if senha:
                        SC.gravar_credencial(
                            pasta_de_dados(),
                            request.form.get("usuario") or "", senha,
                            agora=agora(), usuario_do_sistema=usuario_nome())
                    audit("SELADOR_CONFIGURADO", "SELADOR", None,
                          {"ambiente": request.form.get("ambiente"),
                           "base_url": request.form.get("base_url"),
                           "senha_trocada": bool(senha)})
                    CL.esquecer_tokens()
                    flash("Configuração do selador gravada.", "success")

                elif acao == "ver_certificado":
                    with db.connect() as con:
                        con.row_factory = sqlite3.Row
                        base = SC.base_em_uso(con)
                    if not base:
                        flash("Informe primeiro o endereço do selador.", "danger")
                    else:
                        visto = CL.espiar_certificado(base)
                        flash(f"O selador em {base} apresenta o certificado "
                              f"{visto.legivel}"
                              + (f" — {visto.assunto}" if visto.assunto else "")
                              + ". Confira com quem instalou o selador antes de "
                                "confirmar.", "warning")
                        if visto.vencido:
                            flash(visto.aviso_de_validade(), "warning")

                elif acao == "fixar_certificado":
                    with db.transaction() as con:
                        base = SC.base_em_uso(con)
                        visto = CL.fixar_certificado(
                            con, base,
                            sha256=request.form.get("sha256") or "",
                            agora=agora(), usuario=usuario_nome())
                    CL.esquecer_tokens()
                    audit("SELADOR_CERTIFICADO_FIXADO", "SELADOR", None,
                          {"sha256": visto.sha256, "assunto": visto.assunto})
                    flash(f"Certificado conferido e fixado: {visto.legivel}. "
                          f"A partir de agora o sistema só fala com a máquina "
                          f"que apresentar exatamente este certificado.",
                          "success")
                    if visto.vencido:
                        flash(visto.aviso_de_validade(), "warning")

                elif acao == "testar":
                    with db.transaction() as con:
                        r = CL.testar(con, pasta_de_dados(), agora=agora())
                    audit("SELADOR_TESTADO", "SELADOR", None,
                          {"ok": r["ok"],
                           "passos": [{k: p[k] for k in ("passo", "ok")}
                                      for p in r["passos"]]})
                    if r["ok"]:
                        flash("Rede, certificado e credencial: tudo respondeu. "
                              "O sistema está pronto para selar.", "success")
                    else:
                        parou = next((p for p in r["passos"] if not p["ok"]),
                                     None)
                        flash(f"Parou em «{parou['passo']}»: {parou['detalhe']}"
                              if parou else "O teste falhou.", "danger")

                elif acao == "apagar_credencial":
                    apagou = SC.apagar_credencial(pasta_de_dados())
                    audit("SELADOR_CREDENCIAL_APAGADA", "SELADOR", None,
                          {"existia": apagou})
                    flash("Usuário e senha apagados. O sistema não vai selar "
                          "até que sejam informados de novo."
                          if apagou else "Não havia credencial gravada.",
                          "warning")
                else:
                    flash("Ação desconhecida.", "danger")
            except (SC.ConfigError, CL.SeladorIndisponivel) as erro:
                flash(str(erro), "danger")
            return redirect(url_for("selador_config"))

        with db.connect() as con:
            con.row_factory = sqlite3.Row
            estado = SC.situacao(con, pasta_de_dados())
            linha = con.execute(
                "SELECT * FROM sd_config WHERE id=1").fetchone()
            orfaos = CL.orfaos(con, limite=20)
        certificado = dict(
            sha256=(linha["certificado_sha256"] if linha else None),
            legivel=_legivel(linha["certificado_sha256"] if linha else None),
            assunto=(linha["certificado_assunto"] if linha else None),
            valido_ate=(linha["certificado_valido_ate"] if linha else None),
            fixado_em=(linha["certificado_fixado_em"] if linha else None),
            fixado_por=(linha["certificado_fixado_por"] if linha else None))
        return render_template(
            "selador_config.html", estado=estado, certificado=certificado,
            orfaos=orfaos,
            ambientes=SC.AMBIENTES,
            tem_acervo=acervo().is_file(),
            espacos=selador.ESPACOS,
            endpoints=len(selador.ENDPOINTS),
            padrao_de_fabrica=selador.BASE_PRODUCAO)
