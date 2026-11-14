"""A TELA DO SUPERUSUÁRIO — a porta de dentro do sistema.

POR QUE EXISTE — 12/11/2026, o oficial: «não quero que esse superusuário seja
acessível só pelo Telegram, quero acessar também pelo sistema», e, sobre o
agente antigo (`agente_web`, fora da tela desde 06/10/2026): «pode substituir
e usar o que for interessante do agente, é um projeto abandonado; seria bom
atualizar ele como o superusuário». Esta tela ocupa o lugar dele no menu e na
rota (`/agente/...`).

O QUE ELA É: UMA PORTA, E SÓ. O superusuário não roda aqui dentro — ele é o
Claude Code no posto do servidor (`operador/posto.py`). A tela:

    - deixa o pedido (texto e anexos) na BANDEJA (`operador/bandeja.py`), de
      onde a ponte o colhe: é a mesma fila do Telegram;
    - mostra o que a ponte está fazendo (`bandeja/estado.json`);
    - mostra o DIÁRIO — todo pedido, de qualquer porta —, a memória e os
      relatórios do que mudou no código e no banco.

NADA AQUI GRAVA NO BANCO, e por isso a tela funciona no servidor reserva, que
só lê (`modo_reserva.FORMULARIOS_LIBERADOS`). A linha de auditoria do pedido
sai no principal; no reserva, o registro é o diário.

QUEM ENTRA: só o oficial que responde pela conta `superusuario` (o
`robo_responsavel_id` dela), com perfil ADMIN, e nunca um robô. Outro ADMIN
recebe 403; sem a conta criada, a tela só explica como criá-la. Com
`OPERADOR_FRASE` no `operador.cred`, a tela pede a frase antes — a mesma do
Telegram, com a mesma contagem de erros.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from flask import (abort, flash, jsonify, redirect, render_template, request,
                   send_file, session, url_for)

import modo_reserva as MRES
import selo_robo as SR
from bd_nativo import ERROS_DO_BANCO, banco
from operador import bandeja as BANDEJA

LOGIN = "superusuario"
ENTRADAS_NA_TELA = 30
RELATORIOS_NA_TELA = 15
ANEXOS_POR_PEDIDO = 10
HORAS_DA_FRASE = 12
#: De quanto em quanto tempo o menu confere de novo quem é o oficial (a rota
#: confere sempre; isto é só o link). O «não» vale menos tempo que o «sim»: a
#: conta acabou de ser criada, e o link não pode demorar a aparecer.
MINUTOS_DO_MENU = 10
MINUTOS_DO_MENU_SEM_LINK = 2
COMANDOS = ("novo", "parar", "lembrar", "confirmo")


def _ler_jsonl(arquivo: Path) -> list[dict]:
    lidas = []
    try:
        linhas = arquivo.read_text(encoding="utf-8").splitlines()
    except OSError:
        return lidas
    for linha in linhas:
        try:
            dados = json.loads(linha)
        except ValueError:
            continue
        if isinstance(dados, dict):
            lidas.append(dados)
    return lidas


#: O que a tela espera de cada linha do diário. A linha que vier sem um campo
#: (escrita à mão, ou por versão antiga) não derruba a página.
_ENTRADA_VAZIA = {"quando": "", "servidor": "", "porta": "", "numero": "", "pedido": "",
                  "resposta": "", "relatorio": None, "comandos": 0, "custo_usd": None,
                  "arquivos": []}


def diario(base: Path, limite: int = ENTRADAS_NA_TELA) -> list[dict]:
    """Os últimos pedidos, do mais novo ao mais antigo. Só LÊ os arquivos que
    `operador/conhecimento.py` escreve."""
    lidas: list[dict] = []
    for arquivo in sorted((base / "conhecimento" / "diario").glob("*.jsonl"), reverse=True):
        lidas = _ler_jsonl(arquivo) + lidas
        if len(lidas) >= limite:
            break
    entradas = []
    for lida in reversed(lidas[-limite:]):
        entrada = {**_ENTRADA_VAZIA, **lida}
        entrada["quando"] = str(entrada["quando"] or "")
        if not isinstance(entrada["relatorio"], dict) or not entrada["relatorio"].get("id"):
            entrada["relatorio"] = None
        if not isinstance(entrada["arquivos"], list):
            entrada["arquivos"] = []
        entradas.append(entrada)
    return entradas


def relatorios(base: Path, limite: int = RELATORIOS_NA_TELA) -> list[dict]:
    """As últimas intervenções fechadas (o que mudou no código e no banco)."""
    lidos = []
    for pasta in sorted((base / "intervencoes").glob("*/"), reverse=True):
        try:
            dados = json.loads((pasta / "intervencao.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(dados, dict) and dados.get("fechada_em"):
            lidos.append({"id": pasta.name, "pedido": str(dados.get("pedido") or ""),
                          "exportada_em": dados.get("exportada_em")})
        if len(lidos) >= limite:
            break
    return lidos


def filho(pasta: Path, nome: str) -> Path | None:
    """O item de `pasta` que tem exatamente aquele nome — achado na LISTA da
    pasta, e não montado com o que veio do navegador. Assim o endereço não tem
    como apontar para fora dela (`..`, caminho inteiro): o que não está na
    lista não existe."""
    try:
        for item in pasta.iterdir():
            if item.name == nome:
                return item
    except OSError:
        pass
    return None


def na_bandeja(base: Path) -> list[dict]:
    """Os pedidos que a tela deixou e a ponte ainda não colheu. Só LÊ."""
    esperando = []
    for arquivo in sorted((BANDEJA.pasta(base) / "entrada").glob("*.json")):
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(dados, dict) and dados.get("tipo") == "pedido":
            esperando.append({"quando": str(dados.get("quando") or ""),
                              "texto": str(dados.get("texto") or "")})
    return esperando


def registrar_rotas(app, db, login_required, roles_required, audit):
    """Pendura a tela do superusuário no app já construído."""
    usuario_id = app.extensions["usuario_id"]

    def base() -> Path:
        return Path(app.config["DATA_DIR"]) / "operador"

    def _eu():
        uid = usuario_id()
        return db.get_user(uid) if uid else None

    def _responsavel_id() -> int | None:
        """Quem responde pela conta do superusuário, lido do banco AGORA."""
        try:
            with db.connect() as con:
                linha = banco(con).um(
                    "SELECT robo_responsavel_id FROM users WHERE username=%s "
                    "AND active=1 AND COALESCE(eh_robo,0)=1", (LOGIN,))
        except ERROS_DO_BANCO:
            return None
        if not linha or not linha["robo_responsavel_id"]:
            return None
        return int(linha["robo_responsavel_id"])

    def _acesso(eu) -> str:
        """`oficial`, `sem_conta` ou `outro` — para a pessoa logada."""
        if not eu or str(eu["role"]).upper() != "ADMIN" or SR.usuario_e_robo(eu):
            return "outro"
        responsavel = _responsavel_id()
        if responsavel is None:
            return "sem_conta"
        return "oficial" if int(eu["id"]) == responsavel else "outro"

    def _frase() -> str:
        return (BANDEJA.ler_configuracao(base() / "operador.cred").get("OPERADOR_FRASE")
                or "").strip()

    def _aberta() -> bool:
        return not _frase() or time.time() < float(session.get("superusuario_aberto_ate") or 0)

    def _o_oficial(com_a_frase: bool = True):
        """A pessoa logada, se for o oficial (e já tiver dito a frase)."""
        eu = _eu()
        if _acesso(eu) != "oficial":
            abort(403, description="O superusuário só atende o oficial que responde por ele.")
        if com_a_frase and not _aberta():
            abort(403, description="Diga a frase na tela do superusuário antes.")
        return eu

    def _de_volta():
        return redirect(url_for("superusuario_console"))

    # ------------------------------------------------------------ o menu

    @app.context_processor
    def _o_superusuario_no_menu() -> dict:
        """O link só aparece para o oficial. A conta vem do banco, e o menu
        está em toda tela: a resposta fica na sessão por alguns minutos, para
        não custar uma consulta a cada página. A ROTA confere sempre."""
        try:
            if not session.get("user_id") or app.extensions["usuario_papel"]() != "ADMIN":
                return {"superusuario_no_menu": False}       # sem abrir o banco
            visto = session.get("superusuario_menu")
            vale = MINUTOS_DO_MENU if isinstance(visto, list) and visto and visto[0] \
                else MINUTOS_DO_MENU_SEM_LINK
            if not isinstance(visto, list) or len(visto) != 2 or \
                    time.time() - float(visto[1]) > vale * 60:
                visto = [_acesso(_eu()) == "oficial", time.time()]
                session["superusuario_menu"] = visto
            return {"superusuario_no_menu": bool(visto[0])}
        except Exception:  # noqa: BLE001 — o menu não derruba tela nenhuma
            return {"superusuario_no_menu": False}

    # ----------------------------------------------------------- a tela

    @app.route("/agente/superusuario")
    @login_required
    @roles_required("ADMIN")
    def superusuario_console():
        """O que ele está fazendo, a caixa do pedido e o diário. SÓ LÊ."""
        eu = _eu()
        acesso = _acesso(eu)
        if acesso == "outro":
            abort(403, description="O superusuário só atende o oficial que responde por ele.")
        # quem chegou aqui acabou de ser conferido no banco: o menu já sabe
        session["superusuario_menu"] = [acesso == "oficial", time.time()]
        # A TELA DE ONDE ELE VEIO vai junto com o pedido: o pedido nasce no meio
        # de outro trabalho. Só caminho DESTE sistema, e nunca o da própria tela.
        de = str(request.args.get("de") or "")
        if not de and request.referrer:
            veio = urlsplit(request.referrer)
            de = veio.path if veio.netloc == request.host else ""
        de = de[:200]
        if not de.startswith("/") or de.startswith("//") or de.startswith("/agente/superusuario"):
            de = ""
        if acesso == "sem_conta":
            return render_template("superusuario.html", acesso=acesso, trancada=False,
                                   reserva=MRES.ativo())
        if not _aberta():
            return render_template("superusuario.html", acesso=acesso, trancada=True,
                                   reserva=MRES.ativo())
        pasta = base()
        return render_template(
            "superusuario.html", acesso=acesso, trancada=False, reserva=MRES.ativo(),
            estado=BANDEJA.ler_estado(pasta), entradas=diario(pasta),
            relatorios=relatorios(pasta), de=de, esperando=na_bandeja(pasta),
            memoria=_texto(pasta / "conhecimento" / "MEMORIA.md"))

    def _texto(arquivo: Path) -> str:
        try:
            return arquivo.read_text(encoding="utf-8")
        except OSError:
            return ""

    @app.route("/agente/superusuario/andamento")
    @login_required
    @roles_required("ADMIN")
    def superusuario_andamento():
        """O que a tela pergunta sozinha, a cada poucos segundos. SÓ LÊ, e não
        renova a sessão (`ENDPOINTS_QUE_NAO_RENOVAM_A_SESSAO`)."""
        if _acesso(_eu()) != "oficial" or not _aberta():
            return jsonify({"acesso": False})
        pasta = base()
        estado = BANDEJA.ler_estado(pasta)
        ultimas = diario(pasta, 1)
        return jsonify({
            "acesso": True, "viva": bool(estado.get("viva")),
            "rodando": estado.get("rodando"), "fila": len(estado.get("fila") or []),
            "ultima": (ultimas[0].get("quando") if ultimas else "")})

    # ------------------------------------------------------- os formulários

    @app.route("/agente/superusuario/abrir", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def superusuario_abrir():
        """Confere a frase. Não grava no banco: a contagem de erros fica na
        pasta do operador, a mesma do Telegram."""
        _o_oficial(com_a_frase=False)
        confere, recado = BANDEJA.frase_confere(base(), request.form.get("frase") or "",
                                                _frase())
        if not confere:
            flash(recado or "Não há frase configurada.", "danger")
            return _de_volta()
        session["superusuario_aberto_ate"] = time.time() + HORAS_DA_FRASE * 3600
        return _de_volta()

    @app.route("/agente/superusuario/pedir", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def superusuario_pedir():
        """Deixa o pedido na bandeja. ESCREVE ARQUIVO na pasta do operador, e
        só no principal grava a linha da auditoria."""
        eu = _o_oficial()
        texto = str(request.form.get("texto") or "").strip()
        arquivos = [a for a in request.files.getlist("anexos") if a and a.filename]
        if not texto and not arquivos:
            flash("Escreva o pedido ou anexe um arquivo.", "warning")
            return _de_volta()
        agora = datetime.now()  # noqa: DTZ005 — hora local, como o resto da casa
        pasta = base() / "entrada" / agora.strftime("%Y-%m-%d")
        pasta.mkdir(parents=True, exist_ok=True)
        anexos = []
        for arquivo in arquivos[:ANEXOS_POR_PEDIDO]:
            destino = pasta / (f"{agora.strftime('%H%M%S')}_{uuid.uuid4().hex[:6]}_"
                               f"{BANDEJA.nome_seguro(arquivo.filename)}")
            arquivo.save(destino)
            anexos.append(str(destino))
        tela = str(request.form.get("tela") or "")[:200]
        numero = BANDEJA.pedir(base(), texto, anexos, de=str(eu["username"]),
                               tela=tela if tela.startswith("/") else "")
        if not MRES.ativo():
            audit("SUPERUSUARIO_PEDIDO", "SUPERUSUARIO", None,
                  {"numero": numero, "porta": "sistema", "letras": len(texto),
                   "anexos": len(anexos)})
        flash("Pedido entregue ao superusuário.", "success")
        return _de_volta()

    @app.route("/agente/superusuario/comando", methods=["POST"])
    @login_required
    @roles_required("ADMIN")
    def superusuario_comando():
        """Conversa nova, parar, lembrar e o CONFIRMO. ESCREVE ARQUIVO."""
        eu = _o_oficial()
        comando = str(request.form.get("comando") or "").strip().lower()
        texto = str(request.form.get("texto") or "").strip()
        if comando not in COMANDOS:
            abort(400, description="Comando desconhecido.")
        if comando == "confirmo":
            # o CONFIRMO vai como pedido: a ponte grava a confirmação e o
            # operador segue de onde parou — como no Telegram
            BANDEJA.pedir(base(), ("CONFIRMO " + texto).strip(), de=str(eu["username"]))
            flash("Confirmado: vale por 10 minutos para o que não tem volta.", "warning")
        elif comando == "lembrar" and not texto:
            flash("Escreva o fato a guardar na memória.", "warning")
            return _de_volta()
        else:
            BANDEJA.comandar(base(), comando, texto, de=str(eu["username"]))
            flash({"novo": "Conversa nova: o que importa continua na memória e no diário.",
                   "parar": "Pedi para interromper o pedido em andamento.",
                   "lembrar": "Guardado na memória do superusuário."}[comando], "success")
        if not MRES.ativo():
            audit("SUPERUSUARIO_COMANDO", "SUPERUSUARIO", None, {"comando": comando})
        return _de_volta()

    # ------------------------------------------------- o que ele devolveu

    @app.route("/agente/superusuario/arquivo")
    @login_required
    @roles_required("ADMIN")
    def superusuario_arquivo():
        """Um arquivo que o superusuário devolveu com a resposta. SÓ LÊ."""
        _o_oficial()
        pasta = filho(base() / "saida", str(request.args.get("pedido") or ""))
        arquivo = filho(pasta, str(request.args.get("nome") or "")) if pasta else None
        if arquivo is None or not arquivo.is_file():
            abort(404)
        return send_file(arquivo, as_attachment=True, download_name=arquivo.name)

    @app.route("/agente/superusuario/relatorio")
    @login_required
    @roles_required("ADMIN")
    def superusuario_relatorio():
        """O relatório de uma intervenção, como texto. SÓ LÊ."""
        _o_oficial()
        pasta = filho(base() / "intervencoes", str(request.args.get("id") or ""))
        texto = _texto(pasta / "RELATORIO.md") if pasta is not None else ""
        if not texto:
            abort(404)
        return app.response_class(texto, mimetype="text/plain")
