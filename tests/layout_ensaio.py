"""O que os testes do layout novo usam: a trava, o leitor de páginas e a lista de rotas.

A TRAVA EXISTE PORQUE ESTES TESTES CLICAM EM TUDO
    Eles abrem toda tela e mandam todo formulário, sem saber o que cada um faz. Há
    formulário que chama a Central, que faz backup, que abre o LibreOffice, que reinicia o
    serviço. A máquina dos testes pode ser a da produção, e por isso uma lista de «rotas
    perigosas» não basta: ela envelhece na tarde em que se escreve, e a primeira rota nova
    fica de fora. A trava é um gancho de auditoria do Python (`sys.addaudithook`), que vale
    para o processo inteiro, inclusive para as linhas de execução:

    - nada sai da máquina, nem pergunta ao DNS;
    - nenhum programa é chamado, nem o Windows abre arquivo;
    - nada se grava fora das pastas temporárias;
    - nada se lê da pasta de uma instalação real, e assim a credencial de lá não existe aqui;
    - nada se lista nas pastas das pessoas: as telas de importar procuram a exportação real em
      Downloads e Documentos, e levariam dado de verdade para o banco de ensaio.

    O banco fica de fora porque o driver fala em C, e o gancho não o enxerga. É o DSN de
    teste que o protege, e `conferir_que_e_banco_de_teste` recusa o resto.

    O que foi barrado fica anotado em `tentativas`, e não é defeito: é o teste chegando no
    limite do que pode fazer. Com a trava desligada, o gancho só devolve.

O LEITOR LÊ O QUE O SERVIDOR RECEBE, E NÃO A APARÊNCIA
    `ler_pagina` guarda o que importa para os guardas: formulários com o que o navegador
    mandaria, links, identificadores, as marcas de fase e de passo, e as caixas tortas. Ela
    não guarda o HTML: são centenas de páginas de centenas de KB, vezes papéis e molduras.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import threading
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

RAIZ = Path(__file__).resolve().parent.parent
SENHA = "Senha#12345"
PAPEIS = ("ADMIN", "MANAGER", "USER", "AUDITOR")
LAYOUTS = ("antigo", "novo")


# ------------------------------------------------------------------- a trava

class AcaoBloqueada(PermissionError):
    """O teste tentou fazer o que não pode. Nada aconteceu."""


_trava = {"ligada": False, "poupada": None, "permitidas": [], "reais": [], "pessoais": [], "liberadas": [],
          "tentativas": [], "portas_locais": frozenset()}
_instalada = [False]

_EVENTOS_DE_PROGRAMA = {"subprocess.Popen", "os.system", "os.startfile", "os.startfile/2", "os.exec",
                        "os.spawn", "os.posix_spawn", "os.fork", "os.forkpty", "pty.spawn"}
_EVENTOS_DE_REDE = {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr",
                    "socket.sendto", "socket.sendmsg", "smtplib.connect", "ftplib.connect", "http.client.connect",
                    "urllib.Request"}
_EVENTOS_DE_REGISTRO = {"winreg.CreateKey", "winreg.DeleteKey", "winreg.DeleteValue", "winreg.SetValue"}
# Evento -> posições dos caminhos que ele escreve.
_EVENTOS_DE_ARQUIVO = {"os.remove": (0,), "os.rename": (0, 1), "os.mkdir": (0,), "os.rmdir": (0,),
                       "os.link": (0, 1), "os.symlink": (0, 1), "os.truncate": (0,), "os.chmod": (0,),
                       "os.utime": (0,), "shutil.move": (0, 1), "shutil.rmtree": (0,), "shutil.copyfile": (1,),
                       "shutil.copytree": (1,), "shutil.chown": (0,), "tempfile.mkstemp": (), "tempfile.mkdtemp": ()}
_ESCREVE = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC


def _normal(caminho) -> str:
    return os.path.normcase(os.path.abspath(os.fsdecode(caminho)))


def _dentro(caminho: str, pastas) -> bool:
    return any(caminho == p or caminho.startswith(p + os.sep) for p in pastas)


def _barrar(oque: str, excecao=AcaoBloqueada):
    _trava["tentativas"].append(oque)
    raise excecao(f"Teste do layout: barrado pela trava ({oque}).")


def _ao_abrir(args) -> None:
    caminho, modo, bandeiras = (tuple(args) + (None, None, None))[:3]
    if not isinstance(caminho, (str, bytes, os.PathLike)):
        return
    escreve = bool(modo and set(str(modo)) & set("wax+")) or (
        isinstance(bandeiras, int) and bool(bandeiras & _ESCREVE))
    alvo = _normal(caminho)
    if escreve and not _dentro(alvo, _trava["permitidas"]):
        _barrar(f"gravar {caminho}")
    if not escreve and _dentro(alvo, _trava["reais"]):
        _barrar(f"ler {caminho}", FileNotFoundError)


_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


def _so_o_aparelho_da_mesa(evento, args) -> bool:
    """A conexão com uma porta desta máquina que o ensaio abriu — o selador de mentira, que é servidor
    TLS numa porta local (`selador_falso`). Ensaio de atos das Notas, 03/11/2026: a lavratura das Notas
    sela pelo aparelho, e não pelo selo digitado como a do Registro Civil. Nada sai da máquina."""
    portas = _trava["portas_locais"]
    if not portas:
        return False
    try:
        if evento == "socket.connect":
            endereco = args[1]
            return (isinstance(endereco, tuple) and str(endereco[0]) in _LOOPBACK
                    and int(endereco[1]) in portas)
        if evento == "socket.getaddrinfo":
            return str(args[0]) in _LOOPBACK and args[1] is not None and int(args[1]) in portas
        if evento == "http.client.connect":
            return str(args[1]) in _LOOPBACK and int(args[2]) in portas
        if evento == "urllib.Request":
            from urllib.parse import urlsplit
            u = urlsplit(str(args[0]))
            return u.hostname in _LOOPBACK and u.port in portas
    except (IndexError, TypeError, ValueError):
        return False
    return False


def _gancho(evento, args) -> None:
    if not _trava["ligada"] or _trava["poupada"] is threading.current_thread():
        return
    if evento == "open":
        _ao_abrir(args)
    elif evento in _EVENTOS_DE_PROGRAMA:
        _barrar(f"programa: {evento} {str(args[:2])[:160]}")
    elif evento in _EVENTOS_DE_REDE:
        if _so_o_aparelho_da_mesa(evento, args):
            return
        _barrar(f"rede: {evento} {str(args[-1] if evento == 'socket.connect' else args[:2])[:120]}")
    elif evento in _EVENTOS_DE_REGISTRO:
        _barrar(f"registro do Windows: {evento}")
    elif evento in ("os.listdir", "os.scandir"):
        if args and isinstance(args[0], (str, bytes, os.PathLike)):
            alvo = _normal(args[0])
            if _dentro(alvo, _trava["pessoais"]) and not _dentro(alvo, _trava["liberadas"]):
                _barrar(f"listar {args[0]}", FileNotFoundError)
    elif evento == "ctypes.dlopen" and "pkcs" in str(args[0]).lower():
        _barrar(f"token A3: {args[0]}")
    elif evento in _EVENTOS_DE_ARQUIVO:
        for n in _EVENTOS_DE_ARQUIVO[evento]:
            if n < len(args) and isinstance(args[n], (str, bytes, os.PathLike)) \
                    and not _dentro(_normal(args[n]), _trava["permitidas"]):
                _barrar(f"mexer em arquivo: {evento} {args[n]}")


def pastas_de_instalacao_real() -> list[str]:
    """Onde mora uma instalação de verdade, menos o Python que está rodando este teste."""
    bases = [os.environ.get("PROGRAMDATA"), r"C:\ProgramData", os.environ.get("ProgramFiles"),
             os.environ.get("ProgramFiles(x86)"), os.environ.get("APPDATA")]
    candidatas = [Path(b) / "CartorioGestao" for b in bases if b]
    candidatas += [Path.home() / ".cartorio_gestao", Path(r"C:\CartorioGestao_Copias")]
    return [_normal(c) for c in candidatas]


def ligar_trava(*pastas_de_gravar, portas_locais=()) -> None:
    """`portas_locais`: as portas de 127.0.0.1 que o ensaio pode chamar (o selador de mentira).
    Qualquer outra conexão continua barrada."""
    _trava["portas_locais"] = frozenset(int(p) for p in portas_locais)
    if not _instalada[0]:
        sys.addaudithook(_gancho)
        _instalada[0] = True
    python = (_normal(sys.prefix), _normal(sys.base_prefix))
    _trava["permitidas"] = sorted({_normal(p) for p in (tempfile.gettempdir(), *pastas_de_gravar)})
    _trava["pessoais"] = [_normal(Path.home().parent)]
    _trava["liberadas"] = sorted({_normal(p) for p in (RAIZ, *python, *_trava["permitidas"], *(x for x in sys.path if x))})
    _trava["reais"] = [r for r in pastas_de_instalacao_real()
                       if not any(_dentro(p, [r]) for p in python)]
    _trava["ligada"] = True


def desligar_trava() -> None:
    _trava["ligada"] = False
    _trava["portas_locais"] = frozenset()


def poupar_esta_linha(poupar: bool = True) -> None:
    """Só para o teste de navegador: quem abre o Chrome é esta linha, e o servidor fica noutra."""
    _trava["poupada"] = threading.current_thread() if poupar else None


def tentativas() -> list[str]:
    return list(_trava["tentativas"])


def trava_ligada() -> bool:
    return _trava["ligada"]


def conferir_que_e_banco_de_teste(db) -> None:
    """Estes testes mandam todo formulário. Num banco de verdade, seria o fim dele."""
    alvo = os.environ.get("CG_PG_DSN", "")
    if not alvo and "CG_TEST_BACKEND" not in os.environ:
        pasta = _normal(getattr(db, "path", "") or "")
        assert pasta.startswith(_normal(tempfile.gettempdir())), f"banco fora da pasta temporária: {pasta}"
        return
    assert re.search(r"dbname=\S*(teste|test|cartorio_gw)", alvo) or re.search(r"port=(5435|5491)\b", alvo), (
        f"O DSN não é de teste: {alvo!r}. Estes testes mandam todo formulário da casa.")


# ------------------------------------------------------------------- entrar

def token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def criar_usuario(app, usuario: str, papel: str, nome: str = "") -> None:
    try:
        app.extensions["db"].create_user(usuario, nome or f"Operador {papel.title()} Exemplo", SENHA, papel)
    except Exception:                                              # noqa: BLE001 - já existe
        pass


def entrar(app, usuario: str, papel: str, layout: str | None = None, nome: str = ""):
    """Um cliente de teste com a sessão da pessoa e, se pedido, o layout escolhido por ela."""
    criar_usuario(app, usuario, papel, nome)
    c = app.test_client()
    r = c.post("/login", data={"username": usuario, "password": SENHA,
                               "csrf_token": token(c.get("/login").get_data(as_text=True))},
               follow_redirects=True)
    assert r.status_code == 200, r.status_code
    if layout:
        escolher_layout(app, c, layout)
    return c


def escolher_layout(app, c, layout: str) -> None:
    pagina = c.get("/").get_data(as_text=True)
    r = c.post("/preferencias/layout", data={"layout": layout, "next": "/", "csrf_token": token(pagina)})
    assert r.status_code == 302, r.status_code


# ------------------------------------------------------------------- o leitor

_SEM_FECHAMENTO = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
                   "source", "track", "wbr"}
# O HTML dispensa o fechamento de `p`, `li`, `td` e `option`, e por isso eles não entram na conta.
_CAIXAS = {"main", "nav", "aside", "section", "article", "header", "footer", "div", "form", "details",
           "summary", "table", "fieldset", "select", "ul", "ol", "dialog", "template", "textarea", "button",
           "label"}


def _classes(a: dict) -> list[str]:
    return (a.get("class") or "").split()


class Pagina(HTMLParser):
    """O que o servidor receberia e o que a tela promete, lidos do HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pilha: list[tuple[str, dict]] = []
        self.tortas: list[str] = []
        self.formularios: list[dict] = []
        self.soltos: list[dict] = []        # campos com `form="id"`, fora do formulário
        self.aninhados = 0
        self.links: list[dict] = []
        self.ids: Counter = Counter()
        self.recursos: list[str] = []
        self.fases: list[dict] = []
        self.regua: list[dict] = []
        self.abas: list[dict] = []
        self.passos_nav: list[dict] = []
        self.passos_porta: list[str] = []
        self.passos_bloco: list[str] = []
        self.quadros: list[dict] = []
        self.flashes: list[tuple[str, str]] = []
        self.titulo = ""
        self.cabecalho = ""
        self.atual = {"mod": [], "sec": [], "sub": []}
        self.marcas: Counter = Counter()
        self.html_layout = ""
        self.tem_doctype = False
        self.texto_antes_do_doctype = False
        self._form = None
        self._select = None
        self._textarea = None
        self._no_titulo = False
        self._no_cabecalho = 0
        self._flash = None

    # O caminho até aqui, do mais de fora para o mais de dentro.
    def _dentro(self, tag: str) -> bool:
        return any(p[0] == tag for p in self.pilha)

    def _com_classe(self, classe: str) -> bool:
        return any(classe in _classes(p[1]) for p in self.pilha)

    def _no_conteudo(self) -> bool:
        return self._com_classe("content")

    def _passo(self):
        return next((p[1]["data-passo"] for p in reversed(self.pilha) if "data-passo" in p[1]), None)

    def _fase(self):
        return next((p[1]["data-fase"] for p in reversed(self.pilha) if "data-fase" in p[1]), None)

    def handle_decl(self, decl):
        if decl.lower().startswith("doctype"):
            self.tem_doctype = True

    def handle_data(self, data):
        if self._no_titulo:
            self.titulo += data
        if self._no_cabecalho:
            self.cabecalho += data
        if self._textarea is not None:
            self._textarea["valor"] += data
        if self._select is not None and self._select.get("_opcao") is not None:
            self._select["_opcao"]["texto"] += data
        if self._flash is not None:
            self._flash[1] += data
        # A marca BOM de um molde salvo com ela sai antes do doctype, e o navegador a descarta.
        if not self.tem_doctype and data.replace("\ufeff", "").strip():
            self.texto_antes_do_doctype = True

    def handle_starttag(self, tag, attrs):
        a = {k: (v if v is not None else "") for k, v in attrs}
        if tag == "option" and self._select is not None:
            opcao = {"valor": a.get("value"), "selecionada": "selected" in a, "desligada": "disabled" in a, "texto": ""}
            self._select["opcoes"].append(opcao)
            self._select["_opcao"] = opcao
            return
        self._anotar(tag, a)
        if tag not in _SEM_FECHAMENTO and tag in _CAIXAS:
            self.pilha.append((tag, a))
        if tag == "title":
            self._no_titulo = True
        if "page-heading" in _classes(a):
            self._no_cabecalho = len(self.pilha)
        if "flash" in _classes(a):
            self._flash = [next((c for c in _classes(a) if c != "flash"), ""), "", len(self.pilha)]

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _SEM_FECHAMENTO and tag in _CAIXAS and self.pilha and self.pilha[-1][0] == tag:
            self.pilha.pop()

    def handle_endtag(self, tag):
        if tag == "title":
            self._no_titulo = False
        if tag == "textarea" and self._textarea is not None:
            self._textarea = None
        if tag == "option" and self._select is not None:
            self._select["_opcao"] = None
        if tag == "select" and self._select is not None:
            self._fechar_select()
        if tag == "form":
            self._form = None
        if tag in _CAIXAS:
            if self._flash is not None and tag == "div" and len(self.pilha) == self._flash[2]:
                self.flashes.append((self._flash[0], self._flash[1].strip()))
                self._flash = None
            if self._no_cabecalho and len(self.pilha) == self._no_cabecalho:
                self._no_cabecalho = 0
            if not self.pilha or self.pilha[-1][0] != tag:
                self.tortas.append(f"</{tag}> depois de <{self.pilha[-1][0] if self.pilha else 'nada'}>")
                # O navegador procura a abertura mais próxima: o leitor faz o mesmo.
                for i in range(len(self.pilha) - 1, -1, -1):
                    if self.pilha[i][0] == tag:
                        del self.pilha[i:]
                        break
            else:
                self.pilha.pop()

    def close(self):
        super().close()
        for tag, _a in self.pilha:
            self.tortas.append(f"<{tag}> sem fechar")

    def _anotar(self, tag, a):
        if a.get("id"):
            self.ids[a["id"]] += 1
        if tag == "html":
            self.html_layout = a.get("data-layout", "")
        for classe in _classes(a):
            if classe in ("cg-app", "cg-corpo", "cg-apoio", "cg-modulos", "cg-topo", "cg-migalhas", "cg-regua",
                          "cg-gravar", "cg-ficha", "app-sidebar", "cg-quadro"):
                self.marcas[classe] += 1
        if a.get("id") == "app-sidebar":
            self.marcas["app-sidebar"] += 1
        for marca in ("data-prod-rapida", "data-ajuda-gaveta", "data-agente-gaveta", "data-cg-troca"):
            if marca in a:
                self.marcas[marca] += 1
        if tag == "script" and a.get("src"):
            self.recursos.append(a["src"])
        if tag == "link" and a.get("href") and (a.get("rel") or "") in ("stylesheet", "icon"):
            self.recursos.append(a["href"])
        if tag == "img" and a.get("src"):
            self.recursos.append(a["src"])
        if tag == "a" and "href" in a:
            self.links.append({"href": a["href"], "classes": _classes(a), "no_conteudo": self._no_conteudo()})
            classes = _classes(a)
            if "atual" in classes:
                for chave, classe in (("mod", "cg-mod"), ("sec", "cg-sec"), ("sub", "cg-subaba")):
                    if classe in classes:
                        self.atual[chave].append(a["href"])
        if "data-fase" in a:
            self.fases.append({"fase": a["data-fase"], "tag": tag, "so_trava": "data-cg-so-trava" in a,
                               "barra": "data-cg-barra" in a, "classes": _classes(a)})
        if "data-cg-regua" in a:
            self.regua.append({"chave": a.get("data-chave", ""), "inicial": a.get("data-inicial", ""),
                               "foco": a.get("data-foco", "")})
        if "data-cg-fase" in a:
            self.abas.append({"fase": a["data-cg-fase"], "travada": "data-travada" in a,
                              "classes": _classes(a), "href": a.get("href", "")})
        if "data-cg-passos" in a:
            self.passos_nav.append({"form": a["data-cg-passos"], "inicial": a.get("data-inicial", "")})
        if "data-passo-ir" in a:
            self.passos_porta.append(a["data-passo-ir"])
        if "data-passo" in a:
            self.passos_bloco.append(a["data-passo"])
        if tag == "details" and "cg-quadro" in _classes(a):
            self.quadros.append({"id": a.get("id", ""), "aberto": "open" in a})
        if self._dentro("template"):
            return
        if tag == "form":
            if self._form is not None:
                self.aninhados += 1
            self._form = {"action": a.get("action"), "method": (a.get("method") or "get").lower(),
                          "id": a.get("id", ""), "campos": [], "botoes": [], "no_conteudo": self._no_conteudo(),
                          "enctype": a.get("enctype", ""), "novalidate": "novalidate" in a,
                          "rascunho": "data-rascunho" in a, "classes": _classes(a), "fase": self._fase()}
            self.formularios.append(self._form)
            return
        if tag not in ("input", "select", "textarea", "button"):
            return
        tipo = (a.get("type") or ("submit" if tag == "button" else tag if tag != "input" else "text")).lower()
        campo = {"nome": a.get("name", ""), "tag": tag, "tipo": tipo, "valor": a.get("value", ""),
                 "marcado": "checked" in a, "obrigatorio": "required" in a, "padrao": a.get("pattern", ""),
                 "desligado": "disabled" in a or self._desligado_em_volta(), "passo": self._passo(),
                 "recolhido": self._dentro("details"), "na_barra": self._com_classe("cg-gravar"),
                 "form_attr": a.get("form", ""), "min": a.get("min", ""), "max": a.get("max", ""),
                 "maxlength": a.get("maxlength", ""), "placeholder": a.get("placeholder", ""),
                 "formaction": a.get("formaction"), "formmethod": (a.get("formmethod") or "").lower(),
                 "formtarget": a.get("formtarget"),
                 "multiplo": "multiple" in a, "opcoes": [], "somente_leitura": "readonly" in a}
        if tag == "select":
            campo["_opcao"] = None
            self._select = campo
        elif tag == "textarea":
            self._textarea = campo
        self._guardar_campo(campo)

    def _desligado_em_volta(self) -> bool:
        return any(p[0] == "fieldset" and "disabled" in p[1] for p in self.pilha)

    def _guardar_campo(self, campo):
        submete = campo["tag"] == "button" or campo["tipo"] in ("submit", "image")
        if campo["tipo"] in ("button", "reset"):
            return
        if campo["form_attr"]:
            self.soltos.append(campo)
        elif self._form is not None:
            self._form["botoes" if submete else "campos"].append(campo)

    def _fechar_select(self):
        campo, self._select = self._select, None
        campo.pop("_opcao", None)


def ler_pagina(html: str) -> Pagina:
    p = Pagina()
    p.feed(html)
    p.close()
    # Os campos soltos entram no formulário que eles apontam, como no navegador.
    por_id = {f["id"]: f for f in p.formularios if f["id"]}
    for campo in p.soltos:
        f = por_id.get(campo["form_attr"])
        if f is not None:
            f["botoes" if (campo["tag"] == "button" or campo["tipo"] in ("submit", "image")) else "campos"].append(campo)
    p.titulo = re.sub(r"\s+", " ", p.titulo).strip()
    p.cabecalho = re.sub(r"\s+", " ", p.cabecalho).strip()
    return p


def valor_do_select(campo: dict) -> list[str]:
    opcoes = campo["opcoes"]
    def valor(o):
        return o["valor"] if o["valor"] is not None else o["texto"].strip()
    marcadas = [valor(o) for o in opcoes if o["selecionada"] and not o["desligada"]]
    if campo["multiplo"]:
        return marcadas
    if marcadas:
        return marcadas[-1:]
    livres = [valor(o) for o in opcoes if not o["desligada"]]
    return livres[:1]


def como_o_navegador_manda(formulario: dict, botao: dict | None = None) -> list[tuple[str, str]]:
    """Os pares que o navegador mandaria, sem ninguém mexer em nada na tela."""
    pares: list[tuple[str, str]] = []
    for c in formulario["campos"]:
        if not c["nome"] or c["desligado"] or c["tipo"] == "file":
            continue
        if c["tipo"] in ("checkbox", "radio"):
            if c["marcado"]:
                pares.append((c["nome"], c["valor"] or "on"))
        elif c["tag"] == "select":
            pares.extend((c["nome"], v) for v in valor_do_select(c))
        else:
            pares.append((c["nome"], c["valor"]))
    if botao is not None and botao["nome"] and not botao["desligado"]:
        pares.append((botao["nome"], botao["valor"]))
    return pares


# ------------------------------------------------------------------- as rotas

def regras_de_leitura(app) -> list:
    return sorted((r for r in app.url_map.iter_rules() if "GET" in r.methods and r.endpoint != "static"),
                  key=lambda r: r.rule)


def regras_que_gravam(app) -> list:
    return sorted((r for r in app.url_map.iter_rules() if "POST" in r.methods), key=lambda r: r.rule)


def casar(app, endereco: str, metodo: str = "GET"):
    """A regra que atende aquele endereço, ou None. Só lê a tabela de rotas: nada se abre."""
    from werkzeug.exceptions import HTTPException
    from werkzeug.routing import RequestRedirect

    partes = urlsplit(endereco)
    caminho = partes.path or "/"
    try:
        return app.url_map.bind("localhost").match(caminho, method=metodo, return_rule=True)[0]
    except RequestRedirect:
        return "redireciona"
    except HTTPException:
        return None


def consulta(endereco: str) -> dict:
    return dict(parse_qsl(urlsplit(endereco).query, keep_blank_values=True))


# ------------------------------------------------------------------- o que toda página cumpre

_ISENTOS_DO_TOKEN = {"whatsapp_webhook", "ccn_ponte_resultado"}
# Texto de molde que sobra na tela, e campo que recebeu o nada do Python.
_TEXTO_CRU = re.compile(r"\{\{[^}]*\}\}|\{%[^%]*%\}|value=\"None\"|>\s*None\s*<|\bUndefined\b")
_SO_O_NADA = re.compile(r"value=\"None\"|>\s*None\s*<|\bUndefined\b")
# Estas telas ensinam a escrever modelo, e citam as chaves de propósito.
_CITAM_O_MOLDE = re.compile(r"modelos|/whatsapp/config")


def _endpoint_de(regra) -> str:
    return getattr(regra, "endpoint", "")


def _sem_scripts(html: str) -> str:
    return re.sub(r"<(script|style|textarea)\b.*?</\1>", "", html, flags=re.S | re.I)


def conferir_pagina(app, p: Pagina, html: str, layout: str, endereco: str, papel: str = "ADMIN") -> dict[str, list[str]]:
    """O que uma página promete, olhada sozinha. Devolve {guarda: [o que está errado]}."""
    achados: dict[str, list[str]] = {}

    def anota(guarda, oque):
        achados.setdefault(guarda, []).append(oque)

    casca, velha = p.marcas["cg-app"] > 0, p.marcas["app-sidebar"] > 0
    if casca and velha:
        anota("moldura", "as duas molduras na mesma página")
    if layout == "antigo" and casca:
        anota("moldura", "a moldura nova para quem escolheu a antiga")
    if layout == "novo" and velha:
        anota("moldura", "a moldura antiga para quem escolheu a nova")
    if casca:
        if p.html_layout != "novo":
            anota("moldura", 'falta data-layout="novo"')
        if p.texto_antes_do_doctype or not p.tem_doctype:
            anota("moldura", "algo saiu antes do doctype: o include de base.html escapou do if")
        if p.marcas["cg-corpo"] != 1 or p.marcas["cg-apoio"] != 1:
            anota("moldura", "a casca saiu pela metade")
        if not p.atual["mod"]:
            anota("lugar", "a barra não marca o módulo da tela")
        # O auditor não lança produtividade: `_produtividade_rapida.html` não sai para ele.
        if p.marcas["data-prod-rapida"] != (0 if papel == "AUDITOR" else 1):
            anota("apoio", f"produtividade rápida {p.marcas['data-prod-rapida']} vez(es)")
        if p.marcas["data-ajuda-gaveta"] > 1 or p.marcas["data-agente-gaveta"] > 1:
            anota("apoio", "gaveta repetida")

    for t in p.tortas:
        anota("caixas", t)
    if p.aninhados:
        anota("caixas", f"{p.aninhados} formulário(s) dentro de formulário: o navegador ignora o de dentro")

    # No layout antigo as marcas ficam no HTML sem efeito: ninguém carrega o fases.js.
    if layout == "novo":
        _conferir_fases(p, anota)
        _conferir_passos(p, anota)
        _conferir_quadros(p, html, anota)
    _conferir_formularios(app, p, endereco, anota)
    _conferir_links(app, p, anota)

    regua = _SO_O_NADA if _CITAM_O_MOLDE.search(endereco) else _TEXTO_CRU
    cru = regua.search(_sem_scripts(html))
    if cru:
        anota("texto_cru", cru.group(0)[:60])
    return achados


def _conferir_fases(p: Pagina, anota) -> None:
    abas = {a["fase"] for a in p.abas}
    pedidas = {f["fase"] for f in p.fases}
    if not p.regua:
        for fase in sorted(pedidas):
            anota("fases", f"quadro com data-fase={fase} numa tela sem régua")
        return
    if len(p.regua) > 1:
        anota("fases", "mais de uma régua")
    regua = p.regua[0]
    if regua["inicial"] not in abas:
        anota("fases", f"a fase inicial {regua['inicial']!r} não está na régua {sorted(abas)}")
    if regua["foco"] and regua["foco"] not in abas:
        anota("fases", f"a fase de foco {regua['foco']!r} não está na régua")
    if not any("fases.js" in r for r in p.recursos):
        anota("fases", "régua sem fases.js")
    if not p.marcas["cg-ficha"]:
        anota("fases", "régua sem a caixa da ficha")
    for fase in sorted(pedidas - abas):
        anota("fases", f"quadro de uma fase sem porta: {fase}")
    por_fase = {f["fase"] for f in p.fases if not f["so_trava"] and not f["barra"]}
    for a in p.abas:
        if a["fase"] not in por_fase and not a["travada"]:
            anota("fases", f"aba em branco: {a['fase']}")
    if len(abas) != len(p.abas):
        anota("fases", "aba repetida na régua")


def _conferir_passos(p: Pagina, anota) -> None:
    portas, blocos = p.passos_porta, set(p.passos_bloco)
    if not p.passos_nav:
        if portas or blocos:
            anota("passos", f"passos sem a régua: {sorted(blocos)} {portas}")
        return
    if len(portas) != len(set(portas)):
        anota("passos", f"porta repetida: {portas}")
    if set(portas) != blocos:
        anota("passos", f"porta sem bloco, ou bloco sem porta: {sorted(set(portas) ^ blocos)}")
    if not any("fases.js" in r for r in p.recursos):
        anota("passos", "passos sem fases.js")
    por_id = {f["id"]: f for f in p.formularios if f["id"]}
    for nav in p.passos_nav:
        if nav["inicial"] not in portas:
            anota("passos", f"o passo inicial {nav['inicial']!r} não tem porta")
        f = por_id.get(nav["form"])
        if f is None:
            anota("passos", f"a régua aponta para o formulário {nav['form']!r}, que não existe")
            continue
        # O OBRIGATÓRIO FICA À VISTA DE PROPÓSITO: num passo fechado, o botão parece não fazer nada.
        sem = [c["nome"] for c in f["campos"] if c["nome"] and c["tipo"] != "hidden" and not c["passo"]
               and not c["na_barra"] and not c["obrigatorio"]]
        if sem:
            anota("passos", f"campo fora dos passos, à vista em todos: {sem[:6]}")
        # O BOTÃO DE GRAVAR mora na barra, fora dos passos, ou no último: nos outros, quem está em outro
        # passo não o acha, e ele manda o formulário pela metade. O que abre outra aba é outra coisa.
        principais = [b for b in f["botoes"] if not b["formaction"] and not b["formtarget"]]
        for b in principais:
            if b["passo"] and portas and b["passo"] != portas[-1]:
                anota("passos", f"botão de gravar no passo {b['passo']}, que não é o último: {b['valor'] or b['nome']}")


def _conferir_quadros(p: Pagina, html: str, anota) -> None:
    if not p.quadros:
        return
    ids = [q["id"] for q in p.quadros]
    if not all(ids):
        anota("quadros", "quadro recolhido sem id: o endereço não o abre, e ele não volta aberto depois de gravar")
    if "cg-quadros:" not in html:
        anota("quadros", "quadro recolhido sem as ferramentas(): campo inválido num quadro fechado trava o botão")


def _conferir_formularios(app, p: Pagina, endereco: str, anota) -> None:
    for f in p.formularios:
        if f["method"] not in ("get", "post"):
            continue
        acao = f["action"] or endereco
        alvos = {acao} | {b["formaction"] for b in f["botoes"] if b.get("formaction")}
        for alvo in alvos:
            if not alvo.startswith("/") or alvo.startswith("//"):
                if alvo.startswith(("http:", "https:")):
                    continue
                anota("formularios", f"endereço que não é da casa: {alvo}")
                continue
            metodos = {f["method"]} | {b["formmethod"] for b in f["botoes"] if b.get("formmethod")}
            for metodo in metodos:
                regra = casar(app, alvo, metodo.upper())
                if regra is None:
                    anota("formularios", f"{metodo} {alvo} não tem rota")
                elif metodo == "post" and _endpoint_de(regra) not in _ISENTOS_DO_TOKEN \
                        and not any(c["nome"] == "csrf_token" for c in f["campos"]):
                    anota("formularios", f"post {alvo} sem o token")
        if any(c["tipo"] == "file" for c in f["campos"]) and "multipart" not in f["enctype"].lower():
            anota("formularios", f"{acao}: campo de arquivo em formulário sem multipart: o arquivo não vai")
    ids = {f["id"] for f in p.formularios if f["id"]}
    for campo in p.soltos:
        if campo["form_attr"] not in ids:
            anota("formularios", f"{campo['nome'] or campo['tag']} aponta para o formulário {campo['form_attr']!r}, que não existe")


def _conferir_links(app, p: Pagina, anota) -> None:
    abas = {a["fase"] for a in p.abas}
    for href in sorted({l["href"] for l in p.links}):
        if href.startswith("#"):
            alvo = href[1:]
            if alvo and alvo not in p.ids and alvo not in abas:
                anota("ancoras", href)
        elif href.startswith("/") and not href.startswith("//"):
            if href.startswith("/static/"):
                if not (RAIZ / urlsplit(href).path.lstrip("/")).exists():
                    anota("links", f"{href}: o arquivo não existe")
            elif casar(app, href, "GET") is None:
                anota("links", href)
    for src in sorted(set(p.recursos)):
        caminho = urlsplit(src).path
        if caminho.startswith("/static/") and not (RAIZ / caminho.lstrip("/")).exists():
            anota("recursos", src)
