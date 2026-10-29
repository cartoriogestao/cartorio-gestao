"""O robô do malote — a ciência diária das 8h, sem gente na frente do navegador.

    «configure o robo do malote pra fazer esse trabalho sozinho, so me peca a
     autenticacao a primeira vez e guarde o cookie pra sempre acessar»
    «usuario e senha eu cadastro no cofre do proprio sistema. eh pra dar
     ciencia mesmo e cadastrar no sistema, eh assim que deve ser, ciencia
     diaria, 8h»                                  — o oficial, 29/10/2026

ISTO DESFAZ UMA DECISÃO ESCRITA EM `malote_agente`, E A CORREÇÃO FICA VISÍVEL
    O docstring de `malote_agente` diz, desde 11/10/2026, que «o robô NÃO entra
    sozinho no Malote Digital», por duas razões: guardar o segundo fator na
    máquina é decisão de segurança do oficial, e abrir o documento conta prazo.
    As duas continuam verdadeiras — e as duas foram DECIDIDAS por ele em
    29/10/2026: a senha mora no cofre da automação (que só abre com a
    senha-mestra dele), e a ciência diária às 8h é o que ele quer. O que era
    «não pode» virou «só com o processo ligado e com `pode_agir`».

O QUE SE MEDIU NO MALOTE 26.08.0018 (29/10/2026, com a sessão do oficial)
    - O LOGIN é um formulário JSF comum (`inicial:formLogin`: `Login`, `Senha`,
      `csrf`, `javax.faces.ViewState` e o botão `inicial:formLogin:cmdLogin`),
      SEM captcha. A página avisa «Habilitado duplo fator de acesso (2FA)».
    - ABRIR o não lido é `prepararArquivoInterno(link, id)`: põe o id em
      `idDocumentoLeitura`, serializa o formulário da lista, acrescenta o botão
      cujo id termina em `:btnPrepararArquivoInterno` e faz POST na ação do
      formulário. A resposta diz o resultado num cabeçalho —
      `X-Malote-Resultado-Leitura: sucesso | corrompido`. **É ESTE POST QUE DÁ
      CIÊNCIA.** Depois, `documentoLer.jsf`, `documentoLerTopo.jsf` e
      `documentoLeitorPDF.jsf` (este devolve o PDF).
    - No navegador, o `window.open` dessa função cai num `alert` quando o
      pop-up é bloqueado, e o `alert` nativo CONGELAVA o Chrome controlado: foi
      o defeito de 25/10. Aqui não há navegador, e por isso não há alert.
    - A SESSÃO CAI EM CERCA DE UMA HORA SEM USO (lidos às 18h09, login pedido
      às 19h30). «Guardar o cookie pra sempre» não se sustenta para a sessão:
      o robô entra de novo a cada rodada, com a senha do cofre. O que se guarda
      é o POTE de cookies inteiro (`malote_tjma_sessao`, no cofre) — se o
      malote lembrar o aparelho depois do 2FA, é ali que a lembrança mora, e o
      código só é pedido de novo quando o malote quiser.
    - O FORMULÁRIO DO 2FA **NÃO FOI VISTO**: o oficial já tinha o navegador
      lembrado. `pagina()` o reconhece pelo que é provável (um formulário com um
      campo de texto que não é login nem senha, numa página que fala em código,
      token ou dois fatores) e, na primeira vez, o robô GUARDA A PÁGINA para
      conferência (`arquivos/malote/robo/`). A CONFERIR na primeira rodada.

O CAMINHO DO CÓDIGO DE DOIS FATORES
    1. O robô entra, o malote pede o código: o robô guarda o pote e o
       formulário no cofre e devolve AVISO («digite o código»). O aviso vai pelos
       canais do processo (painel, tarefa, e-mail).
    2. O oficial digita o código na tela (`/automacao/malote/codigo`), que o
       grava no cofre (`malote_tjma_codigo`) e pede uma rodada.
    3. A rodada seguinte retoma o MESMO pote, manda o código, apaga-o do cofre
       e segue. Código velho (mais de 15 minutos) não se usa: o malote já o terá
       esquecido, e mandá-lo só gastaria uma tentativa.

O QUE ELE NÃO FAZ
    Não responde, não encaminha, não devolve documento. Não digita senha em
    lugar nenhum fora do formulário do malote. Não grava senha nem código fora
    do cofre, nem no log, nem no relato. Sem `pode_agir` ele entra e CONTA os
    não lidos, sem abrir nenhum — abrir é ciência, e quem a libera é o oficial.
    O cadastro é o de sempre (`malote_agente.rodada`): aviso de fraude vai à
    lista de fraudes, o resto vira expediente em Processos → «Entradas», e
    nenhuma tarefa nasce daqui.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin

BASE = "https://malote.tjma.jus.br"
URL_LOGIN = BASE + "/malotedigital/login.jsf"
URL_INICIAL = BASE + "/malotedigital/inicial.jsf"
URL_LER = BASE + "/malotedigital/pages/documentos/documentoLer.jsf"
URL_TOPO = BASE + "/malotedigital/pages/documentos/documentoLerTopo.jsf"
URL_PDF = BASE + "/malotedigital/pages/documentos/documentoLeitorPDF.jsf"

#: Os três itens do cofre. A credencial é do tipo SENHA, com os campos
#: `usuario` e `senha`, e quem a cadastra é o oficial, na tela do cofre.
CREDENCIAL = "malote_tjma"
SESSAO = "malote_tjma_sessao"
CODIGO = "malote_tjma_codigo"

CABECALHO_DA_LEITURA = "X-Malote-Resultado-Leitura"
SUFIXO_DO_BOTAO = ":btnPrepararArquivoInterno"
VALIDADE_DO_CODIGO = timedelta(minutes=15)
#: Uma rodada não abre mais que isto: um dia normal tem de 0 a 15. Passar
#: disso é sinal de que a lista não está esvaziando (o POST não deu ciência)
#: e o robô ficaria girando.
TETO_POR_RODADA = 60
TIMEOUT_S = 60

LOGADO, LOGIN, DOIS_FATORES, DESCONHECIDA = "LOGADO", "LOGIN", "DOIS_FATORES", "DESCONHECIDA"

CATALOGO = (
    {"codigo": "MALOTE_CIENCIA_DIARIA", "nome": "Malote — ciência diária e cadastro",
     "setor": "GESTAO", "funcao": "malote_robo.ciencia_diaria", "timeout_s": 1800,
     "agenda": {"dias": [0, 1, 2, 3, 4], "horarios": ["08:00"]},
     "descricao": "Às 8h dos dias úteis: entra no Malote Digital com a senha do cofre, ABRE os não "
                  "lidos (é a ciência), baixa os PDFs e cadastra — fraude na lista de fraudes, o resto "
                  "em Processos → Entradas, sem tarefa. Sem «pode agir» só conta os não lidos. Se o "
                  "malote pedir o código de dois fatores, avisa e espera o código na tela."},
)


class MaloteRoboError(RuntimeError):
    """Falha da rodada, com a frase pronta para o relato."""


class PrecisaDoCodigo(MaloteRoboError):
    """O malote pediu o código de dois fatores e não há código válido no cofre."""


# ------------------------------------------------------------------ a página


class _LeitorDePagina(HTMLParser):
    """Formulários (com os campos) e âncoras com `onclick`, do jeito que o
    navegador os enviaria. Só a biblioteca padrão: o servidor não ganha
    dependência nova por causa de um formulário."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.formularios: list[dict] = []
        self.ancoras: list[dict] = []
        self._form: dict | None = None
        self._select: dict | None = None
        self._ancora: dict | None = None
        self.texto: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k: (v if v is not None else "") for k, v in attrs}
        if tag == "form":
            self._form = {"id": a.get("id", ""), "name": a.get("name", ""),
                          "action": a.get("action", ""), "campos": []}
            self.formularios.append(self._form)
        elif tag == "input" and self._form is not None:
            self._form["campos"].append({"tag": "input", "name": a.get("name", ""), "id": a.get("id", ""),
                                         "type": (a.get("type") or "text").lower(),
                                         "value": a.get("value", ""), "checked": "checked" in a,
                                         "disabled": "disabled" in a})
        elif tag == "textarea" and self._form is not None:
            self._form["campos"].append({"tag": "textarea", "name": a.get("name", ""), "id": a.get("id", ""),
                                         "type": "textarea", "value": "", "checked": False,
                                         "disabled": "disabled" in a})
        elif tag == "select" and self._form is not None:
            self._select = {"tag": "select", "name": a.get("name", ""), "id": a.get("id", ""),
                            "type": "select", "value": None, "primeiro": None, "checked": False,
                            "disabled": "disabled" in a}
            self._form["campos"].append(self._select)
        elif tag == "option" and self._select is not None:
            valor = a.get("value", "")
            if self._select["primeiro"] is None:
                self._select["primeiro"] = valor
            if "selected" in a:
                self._select["value"] = valor
        elif tag == "a":
            self._ancora = {"onclick": a.get("onclick", ""), "texto": ""}
            self.ancoras.append(self._ancora)

    def handle_endtag(self, tag):
        if tag == "form":
            self._form = None
        elif tag == "select" and self._select is not None:
            if self._select["value"] is None:
                self._select["value"] = self._select["primeiro"] or ""
            self._select = None
        elif tag == "a":
            self._ancora = None

    def handle_data(self, data):
        self.texto.append(data)
        if self._ancora is not None:
            self._ancora["texto"] += data


def ler_pagina(html: str) -> _LeitorDePagina:
    leitor = _LeitorDePagina()
    leitor.feed(html or "")
    leitor.close()
    return leitor


def _texto(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html or "")).split())


def serializar(formulario: dict, *, extra: dict | None = None, trocar: dict | None = None) -> list[tuple[str, str]]:
    """O mesmo `serializarFormulario` do malote: sem botões, sem desmarcados, sem desabilitados."""
    trocar = trocar or {}
    pares: list[tuple[str, str]] = []
    for c in formulario["campos"]:
        nome, tipo = c["name"], c["type"]
        if not nome or c["disabled"] or tipo in ("submit", "button", "reset", "file", "image"):
            continue
        if tipo in ("checkbox", "radio") and not c["checked"]:
            continue
        pares.append((nome, trocar.get(nome, c["value"] or "")))
    for nome, valor in (extra or {}).items():
        pares.append((nome, valor))
    return pares


def pagina(html: str) -> str:
    """Em que página o robô está: LOGADO, LOGIN, DOIS_FATORES ou DESCONHECIDA."""
    texto = _texto(html)
    if re.search(r"Fazer Logoff", texto, re.IGNORECASE):
        return LOGADO
    leitor = ler_pagina(html)
    for f in leitor.formularios:
        nomes = {c["name"] for c in f["campos"]}
        if "Login" in nomes and "Senha" in nomes:
            return LOGIN
    if re.search(r"c[óo]digo|token|autentica|dois fatores|duplo fator|2FA|verifica", texto, re.IGNORECASE) \
            and campo_do_codigo(leitor) is not None:
        return DOIS_FATORES
    return DESCONHECIDA


def campo_do_codigo(leitor: _LeitorDePagina) -> tuple[dict, dict] | None:
    """O formulário e o campo onde o malote espera o código — o primeiro campo
    de texto que não é login, senha nem estado do JSF."""
    for f in leitor.formularios:
        for c in f["campos"]:
            if c["type"] in ("text", "number", "tel", "password") and c["name"] \
                    and c["name"] not in ("Login", "Senha") and "ViewState" not in c["name"]:
                return f, c
    return None


def _botao(formulario: dict, *, termina_em: str = "") -> dict | None:
    for c in formulario["campos"]:
        if c["type"] == "submit" and c["name"] and (not termina_em or c["id"].endswith(termina_em)
                                                    or c["name"].endswith(termina_em)):
            return c
    return None


def _parametros_do_jsfcljs(onclick: str) -> tuple[str, dict] | None:
    """`jsfcljs(document.getElementById('FORM'),{'a':'b',...},'')` → ('FORM', {'a': 'b'})."""
    m = re.search(r"jsfcljs\(document\.getElementById\('([^']+)'\),\{([^}]*)\}", onclick or "")
    if not m:
        return None
    return m.group(1), dict(re.findall(r"'([^']*)'\s*:\s*'([^']*)'", m.group(2)))


def _nao_lidos_da_pagina(html: str) -> list[dict]:
    """Cada linha da lista de não lidos: o id interno, o código de rastreabilidade e o texto."""
    saida: list[dict] = []
    vistos: set[str] = set()
    for linha in re.findall(r"<tr\b.*?</tr>", html or "", re.DOTALL | re.IGNORECASE):
        ids = re.findall(r"prepararArquivoInterno\(this,\s*'(\d+)'\)", linha)
        if not ids:
            continue
        # A linha de fora (a tabela que contém a de dentro) também casa: fica a menor.
        if len(set(ids)) > 1:
            continue
        ident = ids[0]
        if ident in vistos:
            continue
        vistos.add(ident)
        cod = re.search(r'codigoRastreabilidadeDocumento[^>]*>\s*(\d+)', linha) \
            or re.search(r"\b(8\d{13})\b", _texto(linha))
        saida.append({"id": ident, "codigo": cod.group(1) if cod else None, "texto": _texto(linha)[:300]})
    return saida


# ------------------------------------------------------------------ o pote de cookies


def _exportar_cookies(sessao) -> list[dict]:
    return [{"name": c.name, "value": c.value, "domain": c.domain, "path": c.path,
             "expires": c.expires, "secure": bool(c.secure)} for c in sessao.cookies]


def _importar_cookies(sessao, cookies: list[dict]) -> None:
    for c in cookies or ():
        sessao.cookies.set(c["name"], c["value"], domain=c.get("domain") or "", path=c.get("path") or "/",
                           expires=c.get("expires"), secure=bool(c.get("secure")))


# ------------------------------------------------------------------ o cliente


class ClienteMalote:
    """Fala com o Malote Digital como o navegador falaria. `sessao` é um
    `requests.Session` (os testes passam um falso com a mesma cara)."""

    def __init__(self, sessao=None, *, timeout: int = TIMEOUT_S):
        if sessao is None:
            import requests
            sessao = requests.Session()
            sessao.headers["User-Agent"] = "CartorioGestao-robo-do-malote"
        self.s = sessao
        self.timeout = timeout
        self.ultima = ""
        self.url_ultima = ""

    def _get(self, url: str):
        r = self.s.get(url, timeout=self.timeout)
        self.ultima, self.url_ultima = r.text, getattr(r, "url", "") or url
        return r

    def _post(self, url: str, pares: list[tuple[str, str]]):
        r = self.s.post(url, data=urlencode(pares).encode("utf-8"), timeout=self.timeout,
                        headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
        self.ultima, self.url_ultima = r.text, getattr(r, "url", "") or url
        return r

    def estado(self) -> str:
        """Abre a página inicial e diz onde se está (a sessão pode ter caído)."""
        r = self._get(URL_INICIAL)
        return pagina(r.text)

    def entrar(self, usuario: str, senha: str) -> str:
        r = self._get(URL_LOGIN)
        if pagina(r.text) == LOGADO:
            return LOGADO
        leitor = ler_pagina(r.text)
        f = next((f for f in leitor.formularios if {"Login", "Senha"} <= {c["name"] for c in f["campos"]}), None)
        if f is None:
            raise MaloteRoboError("A página de entrada do malote não tem o formulário de login esperado.")
        botao = _botao(f)
        pares = serializar(f, trocar={"Login": usuario, "Senha": senha},
                           extra={botao["name"]: botao["value"]} if botao else None)
        r = self._post(urljoin(r.url or URL_LOGIN, f["action"].split(";")[0] or URL_LOGIN), pares)
        return pagina(r.text)

    def formulario_do_codigo(self) -> dict | None:
        """O formulário do 2FA da última página, pronto para guardar no cofre."""
        achado = campo_do_codigo(ler_pagina(self.ultima))
        if not achado:
            return None
        f, campo = achado
        return {"formulario": f, "campo": campo["name"], "url": self.url_ultima or URL_LOGIN}

    def mandar_codigo(self, guardado: dict, codigo: str) -> str:
        f = guardado["formulario"]
        botao = _botao(f)
        pares = serializar(f, trocar={guardado["campo"]: codigo},
                           extra={botao["name"]: botao["value"]} if botao else None)
        r = self._post(urljoin(guardado.get("url") or URL_LOGIN, f["action"].split(";")[0] or URL_LOGIN), pares)
        return pagina(r.text)

    def abrir_nao_lidos(self) -> tuple[str, list[dict]]:
        """O clique no menu «Não Lidos»: devolve a página e as linhas."""
        r = self._get(URL_INICIAL)
        if pagina(r.text) != LOGADO:
            raise MaloteRoboError("A sessão do malote caiu no meio da rodada.")
        leitor = ler_pagina(r.text)
        ancora = next((a for a in leitor.ancoras if "Não Lidos" in " ".join(a["texto"].split())
                       and "jsfcljs" in a["onclick"]), None)
        if ancora is None:
            raise MaloteRoboError("O menu do malote não tem o item «Não Lidos» — a tela mudou.")
        form_id, params = _parametros_do_jsfcljs(ancora["onclick"])
        f = next((f for f in leitor.formularios if f["id"] == form_id), None)
        if f is None:
            raise MaloteRoboError("O formulário do menu do malote não foi achado — a tela mudou.")
        r = self._post(urljoin(r.url or URL_INICIAL, f["action"].split(";")[0]), serializar(f, extra=params))
        return r.text, _nao_lidos_da_pagina(r.text)

    def ler(self, html_da_lista: str, ident: str) -> bytes:
        """ABRE o documento — é a ciência — e devolve o PDF."""
        leitor = ler_pagina(html_da_lista)
        f = next((f for f in leitor.formularios
                  if any(c["id"] == "idDocumentoLeitura" or c["name"] == "idDocumentoLeitura"
                         for c in f["campos"])), None)
        if f is None:
            raise MaloteRoboError("A lista de não lidos não tem o campo idDocumentoLeitura — a tela mudou.")
        botao = next((c for c in f["campos"] if c["id"] == "btnPrepararArquivoInterno"
                      or c["id"].endswith(SUFIXO_DO_BOTAO) or c["name"].endswith(SUFIXO_DO_BOTAO)), None)
        if botao is None:
            raise MaloteRoboError("A lista de não lidos não tem o botão de preparar a leitura — a tela mudou.")
        nome_id = next(c["name"] for c in f["campos"]
                       if c["id"] == "idDocumentoLeitura" or c["name"] == "idDocumentoLeitura")
        pares = serializar(f, trocar={nome_id: ident}, extra={botao["name"]: botao["value"]})
        r = self.s.post(urljoin(URL_INICIAL, f["action"].split(";")[0]), data=urlencode(pares).encode("utf-8"),
                        timeout=self.timeout,
                        headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
        resultado = (r.headers.get(CABECALHO_DA_LEITURA) or "").strip().lower()
        if resultado == "corrompido":
            raise MaloteRoboError(f"O malote diz que o documento {ident} está corrompido.")
        if resultado != "sucesso":
            raise MaloteRoboError(f"O malote não preparou o documento {ident} (resposta «{resultado or 'vazia'}»).")
        self.s.get(URL_LER, timeout=self.timeout)
        self.s.get(URL_TOPO, timeout=self.timeout)
        pdf = self.s.get(URL_PDF, timeout=self.timeout).content
        if not pdf[:5].startswith(b"%PDF"):
            raise MaloteRoboError(f"O documento {ident} foi aberto (ciência dada), mas o que veio não é PDF.")
        return pdf


# ------------------------------------------------------------------ o processo


def nome_do_arquivo(codigo: str, nome_original: str | None) -> str:
    nome = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", (nome_original or "documento.pdf")).strip(" .") or "documento.pdf"
    if not nome.lower().endswith(".pdf"):
        nome += ".pdf"
    return f"MALOTE_{codigo}_{nome}"[:180]


def _cofre(ctx):
    import automacao_cofre as COFRE
    return COFRE, COFRE.caminho_do_cofre(ctx.pasta_dados)


def _ler_ou_vazio(COFRE, caminho, nome: str) -> dict:
    try:
        return COFRE.ler(nome, caminho=caminho, quem="robô do malote", processo="MALOTE_CIENCIA_DIARIA")
    except COFRE.ItemInexistente:
        return {}


def _codigo_valido(COFRE, caminho) -> str | None:
    """O código digitado pelo oficial, se tiver menos de 15 minutos."""
    try:
        meta = COFRE.metadados(CODIGO, caminho=caminho)
    except COFRE.ItemInexistente:
        return None
    quando = meta.get("alterado_em") or meta.get("criado_em") or ""
    try:
        idade = datetime.now() - datetime.fromisoformat(str(quando)[:19])
    except ValueError:
        idade = VALIDADE_DO_CODIGO * 2
    campos = _ler_ou_vazio(COFRE, caminho, CODIGO)
    COFRE.remover(CODIGO, por="robô do malote", caminho=caminho)   # usado ou velho, não fica
    if idade > VALIDADE_DO_CODIGO:
        return None
    return (campos.get("codigo") or "").strip() or None


def _guardar_sessao(COFRE, caminho, cliente: ClienteMalote, formulario_2fa: dict | None = None) -> None:
    campos = {"cookies": json.dumps(_exportar_cookies(cliente.s), ensure_ascii=False)}
    if formulario_2fa:
        campos["formulario_2fa"] = json.dumps(formulario_2fa, ensure_ascii=False)
    COFRE.gravar(SESSAO, campos, tipo=COFRE.TOKEN, por="robô do malote", caminho=caminho)


def _guardar_pagina_para_conferir(ctx, html: str, nome: str) -> str:
    """A página que o robô não reconheceu (ou o 2FA da primeira vez), para conferência."""
    from malote_agente import archive_root_de
    pasta = archive_root_de(ctx.pasta_dados) / "malote" / "robo"
    pasta.mkdir(parents=True, exist_ok=True)
    alvo = pasta / f"{datetime.now():%Y%m%d_%H%M%S}_{nome}.html"
    alvo.write_text(re.sub(r'(name="(?:Senha|csrf)"[^>]*value=")[^"]*', r"\1", html or ""), encoding="utf-8")
    return str(alvo)


def _entrar_com_o_cofre(ctx, cliente: ClienteMalote) -> str:
    """Entra no malote: retoma o pote de cookies, usa o código se houver, ou entra com a senha."""
    COFRE, caminho = _cofre(ctx)
    sessao = _ler_ou_vazio(COFRE, caminho, SESSAO)
    if sessao.get("cookies"):
        _importar_cookies(cliente.s, json.loads(sessao["cookies"]))
    guardado = json.loads(sessao["formulario_2fa"]) if sessao.get("formulario_2fa") else None
    if guardado:
        codigo = _codigo_valido(COFRE, caminho)
        # código recusado ou sessão do 2FA vencida: recomeça pelo login, logo abaixo
        if codigo and cliente.mandar_codigo(guardado, codigo) == LOGADO:
            _guardar_sessao(COFRE, caminho, cliente)
            return LOGADO
    if cliente.estado() == LOGADO:
        return LOGADO
    cred = _ler_ou_vazio(COFRE, caminho, CREDENCIAL)
    if not cred.get("usuario") or not cred.get("senha"):
        raise MaloteRoboError(f"A credencial «{CREDENCIAL}» não está no cofre (campos usuario e senha). "
                              "Cadastre-a em Administrativo → Automação → Cofre.")
    situacao = cliente.entrar(cred["usuario"], cred["senha"])
    if situacao == LOGADO:
        _guardar_sessao(COFRE, caminho, cliente)
        return LOGADO
    if situacao == DOIS_FATORES:
        formulario = cliente.formulario_do_codigo()
        _guardar_sessao(COFRE, caminho, cliente, formulario)
        if not guardado:          # a página do 2FA nunca foi vista: guarda-se a primeira para conferir
            _guardar_pagina_para_conferir(ctx, cliente.ultima, "pedido_do_codigo")
        raise PrecisaDoCodigo("O Malote Digital pediu o código de dois fatores. Digite-o em "
                              "Administrativo → Automação → «Malote: código de dois fatores»; o robô "
                              "roda de novo logo depois.")
    if situacao == LOGIN:
        raise MaloteRoboError("O malote recusou a entrada (voltou à tela de login): confira o usuário e a "
                              f"senha da credencial «{CREDENCIAL}» no cofre.")
    arquivo = _guardar_pagina_para_conferir(ctx, cliente.ultima, "pagina_desconhecida")
    raise MaloteRoboError(f"Depois do login o malote mostrou uma página que o robô não reconhece; ela foi "
                          f"guardada para conferência em {arquivo}.")


def _copia_do_banco(con, banco: Path) -> str:
    """A cópia antes de gravar, como o `malote_agente.main` (regra da casa)."""
    from pasta_das_copias import destino_da_copia
    copia = destino_da_copia(Path(f"antes_malote_robo_{datetime.now():%Y%m%d_%H%M%S_%f}.sqlite3"), Path(banco))
    con.execute("VACUUM INTO ?", (str(copia),))
    if not copia.is_file() or copia.stat().st_size == 0:
        raise MaloteRoboError(f"A cópia do banco não saiu ({copia}); nada foi cadastrado.")
    return str(copia)


def ciencia_diaria(ctx, *, cliente: ClienteMalote | None = None, cadastrar=None, copiar=None) -> dict:
    """O processo MALOTE_CIENCIA_DIARIA (contrato de `automacao_processos`)."""
    import automacao_cofre as COFRE
    import malote_agente as MA
    cliente = cliente or ClienteMalote()
    try:
        _entrar_com_o_cofre(ctx, cliente)
    except PrecisaDoCodigo as aviso:
        return {"situacao": "AVISO", "relato": str(aviso), "achados": [], "acoes": [],
                "erro": "aguardando o código de dois fatores"}
    except COFRE.CofreTrancado:
        return {"situacao": "AVISO", "relato": "O cofre da automação está trancado: o robô do malote não "
                "tem como ler a senha. Desbloqueie o cofre e peça uma rodada.", "achados": [], "acoes": [],
                "erro": "cofre trancado"}
    except (MaloteRoboError, COFRE.CofreError) as erro:
        return {"situacao": "ERRO", "relato": str(erro)[:600], "achados": [], "acoes": [], "erro": str(erro)[:500]}
    except Exception as erro:                       # noqa: BLE001 — rede, malote fora do ar
        return {"situacao": "ERRO", "relato": f"Não deu para entrar no malote: {type(erro).__name__}: {erro}"[:600],
                "achados": [], "acoes": [], "erro": str(erro)[:500]}

    html, linhas = cliente.abrir_nao_lidos()
    if not ctx.processo.get("pode_agir"):
        return {"situacao": "AVISO" if linhas else "OK",
                "relato": (f"{len(linhas)} documento(s) não lido(s) no malote; nenhum aberto (o processo "
                           "está sem «pode agir»: abrir é dar ciência)." if linhas
                           else "Nenhum documento não lido no malote."),
                "achados": [{"codigo": l["codigo"], "linha": l["texto"]} for l in linhas], "acoes": []}

    from malote_agente import SUBPASTA_ENTRADA, archive_root_de, capa_do_pdf
    entrada = archive_root_de(ctx.pasta_dados) / SUBPASTA_ENTRADA
    entrada.mkdir(parents=True, exist_ok=True)
    abertos: list[dict] = []
    falhas: list[str] = []
    falharam: set[str] = set()
    while linhas and len(abertos) + len(falhas) < TETO_POR_RODADA:
        tentou = False
        for l in linhas:
            if l["id"] in falharam or any(a["id"] == l["id"] for a in abertos):
                continue
            tentou = True
            try:
                pdf = cliente.ler(html, l["id"])
            except MaloteRoboError as erro:
                falharam.add(l["id"])
                falhas.append(f"{l['id']}: {erro}")
                continue
            temp = entrada / f".baixando_{l['id']}.pdf"
            temp.write_bytes(pdf)
            capa = capa_do_pdf(temp) or {}
            codigo = capa.get("codigo") or l.get("codigo") or l["id"]
            if l.get("codigo") and capa.get("codigo") and capa["codigo"] != l["codigo"]:
                falharam.add(l["id"])
                conferir = entrada.parent / "robo"
                conferir.mkdir(parents=True, exist_ok=True)
                temp.replace(conferir / f"CONFERIR_{l['id']}.pdf")
                falhas.append(f"{l['id']}: a capa diz {capa['codigo']} e a lista dizia {l['codigo']}; "
                              f"o arquivo NÃO foi cadastrado e ficou em {conferir}")
                continue
            alvo = entrada / nome_do_arquivo(codigo, capa.get("nome_original"))
            if alvo.exists():
                temp.unlink()
            else:
                temp.rename(alvo)
            abertos.append({"id": l["id"], "codigo": codigo, "arquivo": alvo.name,
                            "assunto": capa.get("assunto"), "remetente": capa.get("remetente")})
        if not tentou:
            break
        html, linhas = cliente.abrir_nao_lidos()   # a lista encolhe; a página seguinte aparece
    COFRE_, caminho = _cofre(ctx)
    try:
        _guardar_sessao(COFRE_, caminho, cliente)
    except COFRE.CofreError:
        pass

    resumo: dict[str, Any] = {"cadastrados": 0, "fraudes": [], "erros": []}
    copia = None
    if abertos:
        with ctx.db.connect() as con:
            try:
                copia = (copiar or _copia_do_banco)(con, Path(ctx.db.db_path))
                resumo = (cadastrar or (lambda c: MA.rodada(c, ctx.pasta_dados, confirmar=True)))(con)
            except Exception as erro:            # noqa: BLE001 — os PDFs ficam na entrada
                falhas.append(f"cadastro: {type(erro).__name__}: {erro}")
    acoes = [{"acao": "abriu no malote (ciência)", "codigo": a["codigo"], "arquivo": a["arquivo"]} for a in abertos]
    if copia:
        acoes.append({"acao": "cópia do banco antes de cadastrar", "arquivo": copia})
    relato = (f"{len(abertos)} documento(s) aberto(s) no malote (ciência dada) e baixado(s); "
              f"{resumo.get('cadastrados', 0)} expediente(s) em Processos → Entradas; "
              f"{len(resumo.get('fraudes') or [])} aviso(s) de fraude levado(s) à lista.")
    if not abertos and not falhas:
        relato = "Nenhum documento não lido no malote."
    if falhas or resumo.get("erros"):
        relato += f" {len(falhas) + len(resumo.get('erros') or [])} falha(s): " + \
            "; ".join((falhas + list(resumo.get("erros") or []))[:5])
    situacao = "ERRO" if (falhas or resumo.get("erros")) else "OK"
    return {"situacao": situacao, "relato": relato[:1500],
            "achados": abertos + [{"falha": f} for f in falhas], "acoes": acoes}
