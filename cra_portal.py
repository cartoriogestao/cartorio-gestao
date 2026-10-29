"""O PORTAL DA CRA-MA — entrar, ler os boletos de repasse e gerar o boleto.

Ordem do oficial (29/10/2026): «as guias, configure para a automação emitir.
Posso colocar as senhas no cofre pra entrar.» A API da CRA (o WSDL de 21
operações, `cra21_api`) não tem operação de repasse: o boleto de repasse SÓ
sai do portal, menu Retorno → «Boletos de repasse», botão «GERAR BOLETO».
Este módulo é o transporte e a leitura das páginas — nada de banco aqui. Quem
decide e grava é `protesto_repasse_portal`.

A TÉCNICA: HTTP COM SESSÃO, E NÃO NAVEGADOR SEM TELA
    O portal é PHP que monta a página no servidor: o login é um formulário
    comum (`login`, `senha`, `NTISPOSTBACK`, botão `confirmar` — lido numa
    visita anônima à página de entrada em 29/10/2026, sem CAPTCHA e sem
    script que mexa na senha antes do envio), e cada link do menu é um
    `admin.php?acao=<token>`. Por isso basta o que a casa já tem: a
    biblioteca padrão (`urllib`, com os cookies da sessão) sobre o TLS da casa
    (`centrais_http.contexto_tls`: cadeia normal, TLS 1.2+), a trava do
    sandbox (`centrais_trava_sandbox`) e o `lxml` para ler a página — os dois
    últimos já estão em `requirements.txt`. O navegador sem tela (Playwright)
    existe só entre as dependências de TESTE, precisaria do Chromium no
    servidor e seria a parte mais frágil da rotina.

    O token do `acao=` não se monta: segue-se o link que a página oferece,
    pelo TEXTO do menu. Montar o endereço seria adivinhar o que o portal
    escreveria.

AS TRÊS RECUSAS
    - CAPTCHA ou segundo fator no login: `DesafioNoLogin`. O robô PARA, e a
      guia vira pendência «emita à mão». Nunca se contorna.
    - Login recusado: `LoginRecusado`. Não se tenta de novo na mesma rodada —
      senha errada repetida bloqueia a conta.
    - Página que não tem o que se espera (o menu, a tabela, o botão):
      `PaginaDesconhecida`, com o que faltou. O portal mudou, e quem confere
      é gente.

A SENHA NÃO SAI DAQUI. Ela chega de `automacao_cofre` pela mão de quem chama,
vai no corpo do POST do login e em nenhum outro lugar: o rastro (`passos`)
guarda o método, o caminho sem a consulta, o status e o tempo — nunca o corpo.
"""
from __future__ import annotations

import http.cookiejar
import io
import re
import secrets
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

import centrais_http as HTTP
import centrais_trava_sandbox as TRAVA

#: A entrada do portal: a raiz redireciona para cá (medido em 29/10/2026).
URL_DO_PORTAL = "https://crama.crabr.com.br/crama/site/admin.php"
#: O item do cofre da automação e os campos dele (Automação → Cofre).
NOME_NO_COFRE = "cra_portal"
CAMPOS_NO_COFRE = ("usuario", "senha")
PRAZO_S = 40
TETO_DA_RESPOSTA = 16 * 1024 * 1024

BOLETOS, PENDENTES, EXCLUIDOS = "BOLETOS", "PENDENTES", "EXCLUIDOS"

#: O que, na página, quer dizer «o portal está pedindo mais que usuário e
#: senha». Comparado sem acento e sem caixa. Frases inteiras, e não «token»
#: solto: a página de entrada tem scripts de certificado digital que não são
#: desafio nenhum.
SINAIS_DE_DESAFIO = (
    "captcha", "g-recaptcha", "hcaptcha", "cf-turnstile",
    "codigo de verificacao", "codigo enviado", "segundo fator",
    "autenticacao em duas etapas", "autenticacao de dois fatores",
    "dois fatores", "two-factor", "verificacao em duas etapas",
)
#: O mesmo, pelo nome do campo do formulário.
CAMPOS_DE_DESAFIO = re.compile(r"captcha|otp|2fa|mfa|totp|codigo_?verifica", re.I)


class PortalError(RuntimeError):
    """O portal não fez o que se esperava. A frase é para a tela."""


class DesafioNoLogin(PortalError):
    """CAPTCHA ou segundo fator: o robô para aqui, sempre."""


class LoginRecusado(PortalError):
    """O portal não aceitou o usuário e a senha do cofre."""


class PaginaDesconhecida(PortalError):
    """A página não tem o que esta rotina espera — o portal mudou."""


# ------------------------------------------------------------------ o texto


def normalizar(texto: Any) -> str:
    """Sem acento, sem caixa, espaços juntos — a régua de comparar textos."""
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.casefold().split())


def centavos(texto: Any) -> int | None:
    """«1.632,93» → 163293. None quando não é dinheiro."""
    achado = re.search(r"(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})(?!\d)", str(texto or ""))
    if not achado:
        return None
    return int(achado.group(1).replace(".", "")) * 100 + int(achado.group(2))


def data_iso(texto: Any) -> str | None:
    """«29/10/2026 09:45» → «2026-10-29». None quando não há data."""
    achado = re.search(r"(\d{2})/(\d{2})/(\d{4})", str(texto or ""))
    if not achado:
        return None
    d, m, a = (int(x) for x in achado.groups())
    try:
        return date(a, m, d).isoformat()
    except ValueError:
        return None


def so_digitos(texto: Any) -> str:
    return re.sub(r"\D", "", str(texto or ""))


# ------------------------------------------------------------------ a sessão


@dataclass
class Pagina:
    """O que o portal devolveu."""
    url: str
    status: int
    tipo: str
    corpo: bytes = field(repr=False)

    @property
    def texto(self) -> str:
        achado = re.search(r"charset=([\w-]+)", self.tipo or "", re.I)
        try:
            return self.corpo.decode(achado.group(1) if achado else "utf-8",
                                     errors="replace")
        except LookupError:
            return self.corpo.decode("utf-8", errors="replace")

    @property
    def e_pdf(self) -> bool:
        return (self.tipo or "").lower().startswith("application/pdf") or \
            self.corpo[:5] == b"%PDF-"


def _multipart(campos: list[tuple[str, str]]) -> tuple[bytes, str]:
    """O corpo `multipart/form-data` — o `enctype` do formulário do portal."""
    fronteira = "----cg" + secrets.token_hex(12)
    partes = []
    for nome, valor in campos:
        partes.append(
            f"--{fronteira}\r\nContent-Disposition: form-data; "
            f"name=\"{nome}\"\r\n\r\n{valor}\r\n".encode("utf-8"))
    partes.append(f"--{fronteira}--\r\n".encode("utf-8"))
    return b"".join(partes), f"multipart/form-data; boundary={fronteira}"


class Navegador:
    """Uma sessão no portal: cookies, TLS da casa, redirecionamento e prazo.

    `abrir` é a função que faz a requisição (a de `urllib` por padrão); os
    testes passam um portal falso no lugar, e nenhum teste fala com a rede.
    """

    def __init__(self, *, abrir: Callable[..., Any] | None = None,
                 prazo: float = PRAZO_S):
        self.cookies = http.cookiejar.CookieJar()
        if abrir is None:
            abridor = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(self.cookies),
                urllib.request.HTTPSHandler(context=HTTP.contexto_tls()))
            abrir = abridor.open
        self._abrir = abrir
        self.prazo = prazo
        self.passos: list[dict] = []

    @staticmethod
    def _url(url: str) -> str:
        try:
            url = TRAVA.proteger_url(url)
        except TRAVA.SandboxTravaRecusou as erro:
            raise PortalError(str(erro)) from erro
        p = urllib.parse.urlsplit(url)
        if p.scheme != "https" and (p.hostname or "") not in HTTP.HOSTS_LOCAIS:
            raise PortalError("O portal da CRA só se abre por https: a senha do "
                              "cartório viaja nesta conexão.")
        return url

    def _pedir(self, pedido: urllib.request.Request) -> Pagina:
        inicio = time.monotonic()
        caminho = urllib.parse.urlsplit(pedido.full_url).path
        try:
            resposta = self._abrir(pedido, timeout=self.prazo)
            status = int(getattr(resposta, "status", None) or resposta.getcode())
        except urllib.error.HTTPError as erro:
            resposta, status = erro, int(erro.code)
        except (urllib.error.URLError, OSError) as erro:
            self.passos.append({"metodo": pedido.get_method(), "caminho": caminho,
                                "status": None, "erro": type(erro).__name__})
            raise PortalError(
                f"Não consegui falar com o portal da CRA: {erro}. Confira a "
                f"internet da serventia; nada foi gerado nesta tentativa."
                if pedido.get_method() == "GET" else
                f"O portal da CRA não respondeu ao envio: {erro}. Confira no "
                f"portal se o pedido chegou antes de repetir.") from erro
        corpo = resposta.read(TETO_DA_RESPOSTA + 1)
        if len(corpo) > TETO_DA_RESPOSTA:
            raise PortalError("A resposta do portal passou do tamanho esperado.")
        final = resposta.geturl() if hasattr(resposta, "geturl") else pedido.full_url
        if urllib.parse.urlsplit(final).scheme != "https" and \
                (urllib.parse.urlsplit(final).hostname or "") not in HTTP.HOSTS_LOCAIS:
            raise PortalError("O portal redirecionou para fora do https.")
        tipo = ""
        cabecalhos = getattr(resposta, "headers", None)
        if cabecalhos is not None:
            tipo = cabecalhos.get("Content-Type", "") or ""
        self.passos.append({"metodo": pedido.get_method(), "caminho": caminho,
                            "status": status,
                            "ms": int((time.monotonic() - inicio) * 1000)})
        return Pagina(url=final, status=status, tipo=tipo, corpo=corpo)

    def abrir(self, url: str) -> Pagina:
        """GET. Ler não muda nada no portal."""
        pedido = urllib.request.Request(
            self._url(url), method="GET",
            headers={"User-Agent": HTTP.USER_AGENT_PADRAO})
        return self._pedir(pedido)

    def enviar(self, url: str, campos: list[tuple[str, str]], *,
               metodo: str = "POST") -> Pagina:
        """O formulário. POST NÃO SE REPETE AQUI: quem chama confere antes."""
        if metodo.upper() == "GET":
            consulta = urllib.parse.urlencode(campos)
            separador = "&" if "?" in url else "?"
            return self.abrir(url + (separador + consulta if consulta else ""))
        corpo, tipo = _multipart(campos)
        pedido = urllib.request.Request(
            self._url(url), data=corpo, method="POST",
            headers={"User-Agent": HTTP.USER_AGENT_PADRAO, "Content-Type": tipo})
        return self._pedir(pedido)


# ------------------------------------------------------------------ a página


def _documento(pagina: Pagina):
    from lxml import html as LH
    texto = pagina.texto.strip() or "<html><body></body></html>"
    # O `lxml` recusa texto com a declaração XML de codificação: ela sai antes.
    texto = re.sub(r"^<\?xml[^>]*\?>", "", texto)
    doc = LH.document_fromstring(texto)
    doc.make_links_absolute(pagina.url, resolve_base_href=True)
    return doc


def _texto_do_controle(el) -> str:
    partes = [el.text_content() or "", el.get("value") or "", el.get("title") or "",
              el.get("data-original-title") or "", el.get("aria-label") or ""]
    for i in el.iter("i", "span"):
        partes.append(i.get("class") or "")
    return normalizar(" ".join(partes))


def desafio(pagina: Pagina) -> str | None:
    """O sinal de CAPTCHA ou de segundo fator, se a página pede. Só lê."""
    texto = normalizar(pagina.texto)
    for sinal in SINAIS_DE_DESAFIO:
        if sinal in texto:
            return sinal
    try:
        doc = _documento(pagina)
    except Exception:  # noqa: BLE001 — página que nem se lê não é desafio
        return None
    for campo in doc.iter("input", "select", "textarea"):
        nome = f"{campo.get('name') or ''} {campo.get('id') or ''}"
        if CAMPOS_DE_DESAFIO.search(nome):
            return f"campo «{nome.strip()}»"
    return None


def _campo_de_senha(doc) -> Any:
    for campo in doc.iter("input"):
        if (campo.get("type") or "").lower() == "password":
            return campo
    return None


def esta_dentro(pagina: Pagina) -> bool:
    """A sessão entrou: a página não pede senha e oferece algum link do sistema."""
    doc = _documento(pagina)
    if _campo_de_senha(doc) is not None:
        return False
    return any((a.get("href") or "").startswith("http") for a in doc.iter("a"))


def _valores_do_formulario(form) -> list[tuple[str, str]]:
    """Os campos que o navegador mandaria, sem os botões (quem chama põe o seu)."""
    campos = []
    for el in form.iter("input", "select", "textarea"):
        nome = el.get("name")
        if not nome or el.get("disabled") is not None:
            continue
        tipo = (el.get("type") or "").lower()
        if el.tag == "input" and tipo in ("submit", "button", "image", "reset", "file"):
            continue
        if el.tag == "input" and tipo in ("checkbox", "radio") and el.get("checked") is None:
            continue
        if el.tag == "select":
            escolhida = [o for o in el.iter("option") if o.get("selected") is not None]
            opcao = (escolhida or list(el.iter("option")) or [None])[0]
            valor = "" if opcao is None else (opcao.get("value")
                                             if opcao.get("value") is not None
                                             else opcao.text_content())
            campos.append((nome, str(valor).strip()))
            continue
        valor = el.text_content() if el.tag == "textarea" else (el.get("value") or "")
        campos.append((nome, valor))
    return campos


def entrar(nav: Navegador, usuario: str, senha: str, *,
           url: str = URL_DO_PORTAL) -> Pagina:
    """O login. ESCREVE no portal só a sessão. Para no desafio; não repete."""
    if not str(usuario or "").strip() or not str(senha or ""):
        raise LoginRecusado("Falta o usuário ou a senha do portal da CRA no cofre "
                            f"(item «{NOME_NO_COFRE}», campos «usuario» e «senha»).")
    pagina = nav.abrir(url)
    sinal = desafio(pagina)
    if sinal:
        raise DesafioNoLogin(f"A entrada do portal pede mais que usuário e senha "
                             f"({sinal}). O robô não contorna: emita à mão.")
    if esta_dentro(pagina):
        return pagina
    doc = _documento(pagina)
    senha_el = _campo_de_senha(doc)
    form = None if senha_el is None else next(
        (a for a in senha_el.iterancestors("form")), None)
    if form is None:
        raise PaginaDesconhecida("Não achei o formulário de entrada do portal.")
    nome_senha = senha_el.get("name") or "senha"
    nome_usuario = None
    for campo in form.iter("input"):
        if (campo.get("type") or "text").lower() in ("text", "email") and campo.get("name"):
            nome_usuario = campo.get("name")
            break
    if not nome_usuario:
        raise PaginaDesconhecida("Não achei o campo do usuário no formulário do portal.")
    campos = [(n, v) for n, v in _valores_do_formulario(form)
              if n not in (nome_usuario, nome_senha)]
    botao = next((b for b in form.iter("button", "input")
                  if (b.get("type") or ("submit" if b.tag == "button" else "text")
                      ).lower() == "submit" and b.get("name")), None)
    if botao is not None:
        campos.append((botao.get("name"), botao.get("value") or ""))
    campos += [(nome_usuario, str(usuario).strip()), (nome_senha, str(senha))]
    resposta = nav.enviar(form.get("action") or pagina.url, campos,
                          metodo=(form.get("method") or "POST"))
    sinal = desafio(resposta)
    if sinal:
        raise DesafioNoLogin(f"Depois do usuário e da senha, o portal pediu mais "
                             f"({sinal}). O robô não contorna: emita à mão.")
    if not esta_dentro(resposta):
        raise LoginRecusado("O portal da CRA não aceitou o usuário e a senha do "
                            f"cofre (item «{NOME_NO_COFRE}»). O robô não tenta de "
                            "novo nesta rodada: confira a senha no cofre.")
    return resposta


def achar_link(pagina: Pagina, texto: str) -> str | None:
    """O endereço do link cujo texto é `texto` (ou o contém). Só lê.

    O link se acha pelo que a página ESCREVE, e o endereço é o que ela
    oferece — o token do `acao=` não se monta.
    """
    alvo = normalizar(texto)
    exatos, parecidos = [], []
    for a in _documento(pagina).iter("a"):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "#")) or href.endswith("#"):
            continue
        t = normalizar(a.text_content())
        if t == alvo:
            exatos.append(href)
        elif alvo in t:
            parecidos.append(href)
    return (exatos or parecidos or [None])[0]


def abrir_boletos_de_repasse(nav: Navegador, inicio: Pagina) -> Pagina:
    """Retorno → «Boletos de repasse». Só lê."""
    url = achar_link(inicio, "Boletos de repasse")
    if not url:
        retorno = achar_link(inicio, "Retorno")
        if retorno:
            url = achar_link(nav.abrir(retorno), "Boletos de repasse")
    if not url:
        raise PaginaDesconhecida("Não achei o menu Retorno → «Boletos de repasse» "
                                 "no portal da CRA.")
    pagina = nav.abrir(url)
    if pagina.status >= 400:
        raise PaginaDesconhecida(f"A página dos boletos de repasse respondeu "
                                 f"HTTP {pagina.status}.")
    return pagina


# ------------------------------------------------------------------ as tabelas

_CHAVES = {"conta": "conta", "geracao": "geracao", "retorno": "retorno",
           "nosso numero": "nosso_numero", "repasse": "repasse", "taxa": "taxa",
           "valor": "valor", "situacao": "situacao", "movimento": "movimento"}


def _chave(cabecalho: str) -> str:
    n = normalizar(cabecalho)
    for prefixo, chave in _CHAVES.items():
        if n.startswith(prefixo):
            return chave
    return n


def _secao(tabela, cabecalhos: list[str]) -> str | None:
    """Qual das três listas é esta tabela, pelo título que vem antes dela."""
    no = tabela
    for _ in range(5):
        irmaos = list(no.itersiblings(preceding=True))[:4]
        for irmao in irmaos:
            if irmao.tag in ("table", "script", "style"):
                continue
            t = normalizar(irmao.text_content())[-200:]
            if "pendentes de geracao" in t:
                return PENDENTES
            if "excluido" in t:
                return EXCLUIDOS
            if "boleto" in t:
                return BOLETOS
        no = no.getparent()
        if no is None:
            break
        legenda = no.find("caption")
        if legenda is not None:
            t = normalizar(legenda.text_content())
            if "pendentes de geracao" in t:
                return PENDENTES
            if "excluido" in t:
                return EXCLUIDOS
    if "nosso_numero" in cabecalhos:
        return BOLETOS
    if "movimento" in cabecalhos:
        return PENDENTES
    return None


def _links_da_linha(tr) -> list[dict]:
    saida = []
    for a in tr.iter("a"):
        href = (a.get("href") or "").strip()
        if href and not href.startswith("javascript:") and not href.endswith("#"):
            saida.append({"texto": _texto_do_controle(a), "href": href})
    return saida


def ler_boletos(pagina: Pagina) -> dict[str, list[dict]]:
    """As três listas da página «Boletos de repasse». Só lê.

    Cada linha é um dicionário pelos cabeçalhos da tabela (`conta`,
    `geracao`, `retorno`, `nosso_numero`, `repasse`, `taxa`, `valor`,
    `situacao`, `movimento`), mais os valores lidos (`*_centavos`, `*_em`) e
    os links da linha. A lista que não se reconhece fica de fora — e, se não
    se reconhece nenhuma, a página não é a que se espera.
    """
    doc = _documento(pagina)
    quadro: dict[str, list[dict]] = {BOLETOS: [], PENDENTES: [], EXCLUIDOS: []}
    achou = False
    for tabela in doc.iter("table"):
        ths = tabela.xpath(".//thead//th") or tabela.xpath(".//tr[1]/th")
        cabecalhos = [_chave(th.text_content()) for th in ths]
        if not ({"conta"} <= set(cabecalhos)
                and ({"nosso_numero"} & set(cabecalhos)
                     or {"movimento"} & set(cabecalhos))):
            continue
        secao = _secao(tabela, cabecalhos)
        if secao is None:
            continue
        achou = True
        linhas = tabela.xpath(".//tbody/tr") or tabela.xpath(".//tr[td]")
        for tr in linhas:
            celulas = tr.xpath("./td")
            if len(celulas) < 2:
                continue
            linha = {cabecalhos[i]: " ".join(c.text_content().split())
                     for i, c in enumerate(celulas[:len(cabecalhos)])}
            if not any(linha.values()) or len(celulas) == 1:
                continue
            for k in ("repasse", "taxa", "valor"):
                linha[f"{k}_centavos"] = centavos(linha.get(k))
            for k in ("geracao", "retorno", "movimento"):
                linha[f"{k}_em"] = data_iso(linha.get(k))
            linha["nosso_numero"] = so_digitos(linha.get("nosso_numero"))
            linha["situacao_norm"] = normalizar(linha.get("situacao"))
            linha["links"] = _links_da_linha(tr)
            quadro[secao].append(linha)
    if not achou:
        raise PaginaDesconhecida("A página dos boletos de repasse não tem as listas "
                                 "que se esperava (boletos e pendentes de geração).")
    return quadro


def em_aberto(boleto: dict) -> bool:
    """«AGUARDANDO PAGAMENTO» — o único que o robô registra como guia nova."""
    return "aguardando" in boleto.get("situacao_norm", "")


def pago(boleto: dict) -> bool:
    """A situação que o portal mostra depois do pagamento. A palavra exata
    está A CONFERIR (o boleto pago em 29/10 seguia «AGUARDANDO PAGAMENTO»);
    vale «PAGO» como palavra inteira — «PAGAMENTO» não conta."""
    return re.search(r"\bpago\b", boleto.get("situacao_norm", "")) is not None


# ------------------------------------------------------------------ gerar


def gerar_boleto(nav: Navegador, pagina: Pagina, *, conta: str) -> Pagina:
    """Clica em «GERAR BOLETO» para a conta. ESCREVE NO PORTAL. Não repete.

    O botão se acha pelo texto. Se há um por linha, vale o da linha da conta;
    se há um só, vale ele; mais de um sem a conta na linha é recusa — clicar
    no errado geraria o boleto de outra conta. O formulário vai com os campos
    que a página traz e, se houver um seletor com a conta entre as opções, ela
    escolhida.
    """
    doc = _documento(pagina)
    alvo = normalizar(conta)
    controles = [el for el in doc.iter("button", "input", "a")
                 if "gerar boleto" in _texto_do_controle(el)]
    if not controles:
        raise PaginaDesconhecida("Não achei o botão «GERAR BOLETO» na página dos "
                                 "boletos de repasse.")
    na_linha = [c for c in controles
                if any(alvo and alvo in normalizar(tr.text_content())
                       for tr in c.iterancestors("tr"))]
    if na_linha:
        escolhido = na_linha[0]
    elif len(controles) == 1:
        escolhido = controles[0]
    else:
        raise PaginaDesconhecida(f"Há mais de um «GERAR BOLETO» e nenhum na linha da "
                                 f"conta «{conta}»: o robô não escolhe.")
    if escolhido.tag == "a":
        href = (escolhido.get("href") or "").strip()
        if not href or href.startswith("javascript:") or href.endswith("#"):
            raise PaginaDesconhecida("O «GERAR BOLETO» do portal depende de script; o "
                                     "robô não o aciona.")
        return nav.abrir(href)
    form = next(escolhido.iterancestors("form"), None)
    if form is None:
        raise PaginaDesconhecida("O «GERAR BOLETO» não está num formulário.")
    campos = _valores_do_formulario(form)
    for sel in form.iter("select"):
        nome = sel.get("name")
        opcoes = [o for o in sel.iter("option")
                  if alvo and alvo in normalizar(o.text_content())]
        if nome and len(opcoes) == 1:
            valor = opcoes[0].get("value")
            valor = opcoes[0].text_content() if valor is None else valor
            campos = [(n, v) for n, v in campos if n != nome] + [(nome, str(valor))]
    if escolhido.get("name"):
        campos.append((escolhido.get("name"), escolhido.get("value") or ""))
    return nav.enviar(form.get("action") or pagina.url, campos,
                      metodo=(form.get("method") or "POST"))


def link_do_pdf(boleto: dict) -> str | None:
    """O link do PDF do boleto, na linha dele. Só lê."""
    preferidos = ("pdf", "imprimir", "print", "segunda via", "2a via", "visualizar",
                  "download", "baixar", "barcode", "boleto")
    for palavra in preferidos:
        for link in boleto.get("links") or ():
            if palavra in link["texto"]:
                return link["href"]
    return None


# ------------------------------------------------------------------ o PDF


_RX_LINHA = re.compile(
    r"(\d{5})\.?\s?(\d{5})\s+(\d{5})\.?\s?(\d{6})\s+(\d{5})\.?\s?(\d{6})\s+(\d)\s+(\d{14})")


def texto_do_pdf(conteudo: bytes) -> str:
    """O texto do PDF, pelo `pypdf` — o leitor de PDF da casa."""
    from pypdf import PdfReader
    try:
        leitor = PdfReader(io.BytesIO(conteudo))
        return "\n".join((p.extract_text() or "") for p in leitor.pages)
    except Exception as erro:  # noqa: BLE001 — PDF que não se lê vira recusa
        raise PortalError(f"O PDF do boleto não se lê: {type(erro).__name__}.") from erro


def ler_boleto_pdf(conteudo: bytes) -> dict:
    """O que o PDF do boleto diz. Só lê.

    A LINHA DIGITÁVEL MANDA: ela se confere pelos dígitos (a régua da casa,
    `despesas.ler_codigo_de_barras`) e traz o valor e o vencimento por dentro.
    O nosso número, o valor e o vencimento IMPRESSOS se leem também, e quem
    chama confere um contra o outro.
    """
    import despesas as DP
    texto = texto_do_pdf(conteudo)
    plano = " ".join(texto.split())
    achado = _RX_LINHA.search(plano)
    linha = "".join(achado.groups()) if achado else ""
    if not linha:
        # O PDF que sai sem espaço entre os blocos: a linha que tem 47 dígitos.
        linha = next((d for d in (so_digitos(x) for x in texto.splitlines())
                      if len(d) == 47), "")
    if not linha:
        raise PortalError("Não achei a linha digitável no PDF do boleto.")
    try:
        lido = DP.ler_codigo_de_barras(linha)
    except DP.DespesaError as erro:
        raise PortalError(f"A linha digitável do PDF não confere: {erro}") from erro
    norm = normalizar(plano)
    nosso = re.search(r"nosso numero\D{0,30}?([\d][\d./ -]{4,30}\d)", norm)
    venc = re.search(r"vencimento\D{0,30}?(\d{2}/\d{2}/\d{4})", norm)
    valor = re.search(r"valor do documento\D{0,30}?(\d{1,3}(?:\.\d{3})*,\d{2})", norm)
    benef = re.search(r"(?:beneficiario|cedente)\s*:?\s*([a-z0-9 .&/-]{3,80}?)"
                      r"(?:\s+(?:cnpj|cpf|agencia|ag\.|endereco|nosso)\b|$)", norm)
    return {"linha_digitavel": linha, "barras": lido["barras"],
            "valor_centavos": lido["valor_centavos"],
            "vencimentos": lido["vencimentos"],
            "nosso_numero": so_digitos(nosso.group(1)) if nosso else "",
            "vencimento_impresso": data_iso(venc.group(1)) if venc else None,
            "valor_impresso_centavos": centavos(valor.group(1)) if valor else None,
            "beneficiario": benef.group(1).strip().upper() if benef else ""}
