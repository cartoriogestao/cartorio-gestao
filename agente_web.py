"""A CONFIGURAÇÃO DOS PROVEDORES DE IA — o que sobrou das telas do agente.

O CONSOLE DO AGENTE SAIU EM 14/11/2026 — ordem do oficial: «pode substituir e
usar o que for interessante do agente, é um projeto abandonado». Quem faz esse
papel agora é o superusuário (`operador_web`, `docs/SUPERUSUARIO.md`). Ele já
estava fora da tela desde 06/10; em produção eram duas sessões, a última de
22/09, e nenhuma rotina de IA na automação.

O QUE FICOU, E POR QUÊ
    - esta tela (`/agente/configurar`): as chaves dos provedores de IA, que a
      Ajuda, o WhatsApp, as revisões e a automação usam, e a configuração do
      laço do agente;
    - o laço (`agente.py`): a automação ainda o roda nas rotinas do tipo
      «agente de IA» (`automacao_processos.rodar_agente`), e `desfazer` e
      `aplicar` voltam atrás o que uma delas fizer;
    - as ferramentas (`agente_ferramentas.py`): são as da Ajuda do sistema.

SÓ O ADMIN. A rota recusa por dever; o menu esconde por educação.

A CHAVE NÃO PASSA PELO BANCO
    Ela vai direto para `agente.cred`, ao lado de `claude.cred`. E **campo
    vazio não apaga nada**: quem apaga é o botão que diz que apaga. Um
    formulário que gravasse o que estiver em branco apagaria a chave do
    provedor que ninguém estava olhando.
"""
from __future__ import annotations

from pathlib import Path

from flask import flash, redirect, render_template, request, url_for

import agente as AGT
import agente_ferramentas as FER
import agente_provedores as PROV

#: O AGENTE SAIU DA TELA EM 06/10/2026 («apenas não aparecer mais») e o console
#: foi apagado em 14/11/2026. Isto agora só decide se «Agente: configurar»
#: aparece no menu; a rota existe sempre, para o ADMIN.
AGENTE_VISIVEL = False


def registrar_rotas(app, db, login_required, roles_required, audit,
                    fmt_date=str):
    """Pendura a configuração dos provedores no app já construído.

    A ASSINATURA É A DA CASA, e não uma minha: os módulos de tela deste sistema
    recebem os mesmos argumentos e pegam o resto de `app.extensions`.
    """

    def pasta_de_dados() -> Path:
        return Path(app.config["DATA_DIR"])

    def _campo(nome: str, padrao: str = "") -> str:
        return (request.form.get(nome) or padrao).strip()

    def _marcado(nome: str) -> bool:
        return request.form.get(nome) is not None

    def _recado_da_config(config: dict) -> str:
        """Diz o que PASSOU A VALER, e não o que foi digitado.

        O teto que a tela oferece é preso no limite duro, e um recado que
        repetisse o número digitado diria «guardado 900» sobre um teto de 24. É
        o mesmo cuidado do `gravar_config`, que recusa em vez de ignorar calado.
        """
        sozinho = config["escrita_ligada"] and config.get("escrita_sem_confirmacao")
        return (f"Guardado. Vale agora: provedor {config['provedor_padrao']}, "
                f"modelo {config['modelo_padrao'] or '(o padrão do provedor)'}, "
                f"até {config['teto_de_turnos']} turnos por rodada, "
                f"{config['teto_de_sessoes']} sessões por dia, escrita "
                f"{'LIGADA' if config['escrita_ligada'] else 'desligada'}"
                f"{' (aplica sem confirmação)' if sozinho else ''}.")

    @app.context_processor
    def _o_agente_no_menu() -> dict:
        """Só o item «Agente: configurar» do menu. Sem banco, sem credencial."""
        return {"agente_no_menu": AGENTE_VISIVEL}

    # -------------------------------------------------------- a configuração

    @app.route("/agente/configurar", methods=["GET", "POST"])
    @roles_required("ADMIN")
    def agente_configurar():
        """O provedor, o modelo, os tetos, a escrita e as chaves.

        **LIGAR A ESCRITA É UM CLIQUE CONSCIENTE**, com o aviso ao lado — e não
        um padrão que veio ligado. É a mesma regra da ajuda, que também depende
        de alguém liberar: uma capacidade nasce desligada.
        """
        if request.method == "POST":
            acao = _campo("acao")
            try:
                if acao == "chave":
                    _grava_chave()
                elif acao == "apagar_chave":
                    _apaga_chave()
                else:
                    _grava_config()
            except (AGT.AgenteRecusado, PROV.AgenteError,
                    ValueError) as recusa:
                flash(str(recusa), "danger")
            return redirect(url_for("agente_configurar"))

        # A CONFIGURAÇÃO VEM PELO DOMÍNIO, e não por uma leitura minha: este
        # módulo não abre banco. Duas leituras da mesma tabela divergiriam no
        # primeiro campo novo, e a tela passaria a mostrar o que o agente não
        # obedece — que é o pior jeito de errar numa tela de permissão.
        config = AGT.config_para_tela(db)
        return render_template(
            "agente_configurar.html", config=config,
            provedores=PROV.catalogo_para_tela(pasta_de_dados()),
            caminho_da_chave=PROV.caminho_da_credencial(pasta_de_dados()),
            arquivo_da_ajuda=str(Path(app.config["DATA_DIR"])
                                 / PROV.ARQUIVO_DA_AJUDA),
            teto_de_tokens=AGT.TETO_DE_TOKENS,
            teto_maximo_de_saida=AGT.MAXIMO_DE_SAIDA,
            quantas_leitura=len([f for f in FER.FERRAMENTAS
                                 if f.tipo == FER.LEITURA]),
            quantas_escrita=len([f for f in FER.FERRAMENTAS
                                 if f.tipo == FER.ESCRITA]))

    def _grava_config() -> None:
        """Os campos da configuração. **ESCREVE.**"""
        r = AGT.salvar_config(
            db, provedor=_campo("provedor_padrao") or None,
            modelo=_campo("modelo_padrao"),
            teto_de_turnos=_campo("teto_de_turnos") or None,
            teto_de_sessoes=_campo("teto_de_sessoes") or None,
            escrita_ligada=_marcado("escrita_ligada"),
            escrita_sem_confirmacao=_marcado("escrita_sem_confirmacao"))
        audit("AGENTE_CONFIGURADA", "ag_config", 1, r)
        flash(_recado_da_config(r), "success")

    def _grava_chave() -> None:
        """A chave de um provedor. **ESCREVE EM DISCO.**

        **CAMPO VAZIO NÃO GRAVA E NÃO APAGA.** É o cuidado que o formulário de
        robôs já toma, e aqui ele vale mais: `gravar_chave` recebe vazio como
        ordem de apagar — é assim que se desliga um provedor sem deixar
        credencial viva no disco —, e um campo em branco que chegasse até lá
        apagaria a chave de um provedor que ninguém estava olhando.
        """
        provedor = _campo("provedor")
        chave = request.form.get("api_key") or ""
        if not chave.strip():
            flash("O campo da chave estava vazio: nada foi gravado e nada foi "
                  "apagado. Para desligar um provedor, use o botão que apaga.",
                  "info")
            return
        r = AGT.gravar_chave(pasta_de_dados(), provedor, chave)
        audit("AGENTE_CHAVE_GRAVADA", "ag_config", 1,
              {"provedor": r["provedor"], "arquivo": r["caminho"]})
        flash(f"Chave do {r['provedor']} gravada em {r['caminho']}, fora do "
              f"banco.", "success")

    def _apaga_chave() -> None:
        """Apaga a chave de um provedor. **ESCREVE EM DISCO.**

        Só por clique explícito, e com o recado dizendo o que aquilo custa: sem
        chave, o agente não responde por aquele provedor.
        """
        r = AGT.gravar_chave(pasta_de_dados(), _campo("provedor"), "")
        audit("AGENTE_CHAVE_APAGADA", "ag_config", 1,
              {"provedor": r["provedor"]})
        flash(f"A chave do {r['provedor']} foi apagada do disco. O agente não "
              f"responde mais por esse provedor até alguém informar outra.",
              "warning")
