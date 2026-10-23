"""O HTML de quem escreve no sistema, mostrado SEM o que executa.

POR QUE EXISTE (auditoria LS02, 19/10/2026)
    O teor de um ato é HTML, e é HTML porque o negrito é a atividade fim do
    cartório. As telas o mostram com `|safe` — e `|safe` diz ao Jinja «isto é
    da casa, não escape». Só que o teor é escrito por quem está no balcão: o
    formulário do teor das notas grava o que vier, sem filtro nenhum. Um
    `<img src=x onerror=...>` gravado por um escrevente rodava na sessão de
    quem abrisse o ato depois — o oficial, com o token de formulário à mão e
    poder de criar ADMIN.

    O Registro de Imóveis já tinha um filtro (`ri_web.teor_seguro`), feito de
    expressões regulares; e expressão regular contra HTML perde: o
    `<svg/onload=...>` passava, porque ela procurava espaço antes do `on`.

O QUE ESTE FILTRO FAZ, E POR QUE ASSIM
    Lê o HTML com o leitor da própria biblioteca do Python e o ESCREVE DE NOVO,
    peça por peça. Nada passa cru: o texto sai escapado, cada atributo sai
    entre aspas e escapado, e etiqueta ou atributo com nome estranho não sai.
    Por isso uma diferença entre o leitor do Python e o do navegador não abre
    brecha — o navegador lê o que este módulo escreveu, e não o original.

    Sai, com o conteúdo: `script`, `iframe`, `object`, `embed`, `applet`,
    `frame`, `frameset`, `template`, `svg`, `math`, `title`, `noscript`,
    `noembed`, `noframes`.
    Sai, só a etiqueta: `base`, `link`, `meta`, `xmp`, `plaintext`, `html`,
    `head`, `body` e os comentários.
    Sai, o atributo: todo `on...`, e os de endereço (`href`, `src`...) que
    apontem para `javascript:`, `vbscript:`, `data:` que não seja imagem, ou
    `file:` — este último é o que o Chrome que imprime o PDF abriria do disco
    do servidor.

O CSS SE LÊ COMO O NAVEGADOR O LÊ (LX12, 19/10/2026 — achado M12 do LS02)
    O filtro de `url(` e `@import` procurava o texto cru, e o CSS tem escapes:
    `url(\\2f\\2f maquina/x)` é `url(//maquina/x)` para o Chrome que imprime
    o PDF, e passava. Agora o CSS (do `<style>` e do `style=`) tem os
    comentários tirados e os escapes decodificados ANTES do filtro, e o que
    sai é essa forma já decodificada — sem `\\` nem `/* */` nenhum, o
    navegador lê exatamente o texto que foi conferido.

O QUE NÃO MUDA
    Parágrafo, negrito, itálico, sublinhado, tabela, classe, `style` em linha,
    imagem por `data:image`, link — tudo o que o editor da casa e o acervo
    escrevem. O `<style>` do documento colado do Word continua, com o `</`
    de dentro neutralizado para não fechar a etiqueta antes da hora.
"""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Any

from markupsafe import Markup

# Saem com tudo o que têm dentro: o conteúdo deles ou executa, ou é outro
# documento, ou é imagem vetorial que carrega script — nenhum é teor. Os
# quatro últimos o navegador já não desenhava (`title` no meio da página,
# `noscript` com script ligado): tirá-los inteiros não muda o que se via.
SAI_COM_O_CONTEUDO = frozenset({
    "script", "iframe", "object", "embed", "applet", "frame", "frameset",
    "template", "svg", "math", "title", "noscript", "noembed", "noframes",
})
# Sai a etiqueta, fica o conteúdo (já filtrado). As do documento inteiro
# (`html`, `head`, `body`) vêm do teor do acervo, que chega como página
# completa; dentro da tela elas não significam nada.
SAI_A_ETIQUETA = frozenset({
    "base", "link", "meta", "xmp", "plaintext", "html", "head", "body",
})
# Os que o navegador não fecha — não entram na pilha das abertas.
VAZIAS = frozenset({
    "area", "br", "col", "hr", "img", "input", "param", "source", "track",
    "wbr", "keygen",
})
# Saem sempre (revisão de segurança de 22/10/2026, M7): `form` prende um botão
# a um formulário da TELA, e `formaction`/`action` mandam esse formulário —
# com o token e os campos — para o endereço que o teor disser. Nenhum dos
# três é teor de papel.
SAI_O_ATRIBUTO = frozenset({"form", "formaction", "action"})
# Os atributos cujo valor o navegador segue como endereço.
DE_ENDERECO = frozenset({
    "href", "src", "action", "formaction", "xlink:href", "background",
    "poster", "data", "codebase", "cite", "longdesc", "lowsrc", "dynsrc",
    "srcset", "ping", "manifest", "icon", "profile", "usemap",
})
_NOME = re.compile(r"^[a-zA-Z][a-zA-Z0-9:._-]*$")
# Espaço e caractere de controle antes do esquema: o navegador os ignora em
# `java\tscript:`, e quem filtra tem de ignorar igual.
_INVISIVEL = re.compile(r"[\x00-\x20\x7f-\x9f]+")
_ESQUEMA_PROIBIDO = ("javascript:", "vbscript:", "file:", "livescript:")
# `//maquina/pasta` e `\\maquina\pasta`: na página que o Chrome abre do disco
# para imprimir o PDF (`impressao_pdf.pdf_de_html_chrome`), o endereço sem
# esquema vira `file://maquina/...` — e o servidor vai à rede pela SMB,
# entregando a credencial da máquina a quem estiver do outro lado.
_DE_REDE = re.compile(r"^[/\\]{2}")
# No CSS, `url(` só com imagem embutida ou endereço relativo (22/10/2026, M7):
# `url(http://…)` no `style` de um teor fazia o Chrome do servidor — e o
# navegador de quem abre a tela — buscar um endereço de fora a cada abertura.
_URL_NO_CSS = re.compile(
    r"""url\(\s*(['"]?)\s*(?=[/\\]{2}|(?!data:image/)[a-z][a-z0-9+.-]*:)""", re.I)


# Um texto entre aspas no CSS que leva à rede ou ao disco. O `image-set()`
# do Chrome aceita o endereço como texto, sem `url(`.
_TEXTO_NO_CSS = re.compile(
    r"""(['"])\s*(?=[/\\]{2}|file:|javascript:|vbscript:|https?:|ftp:)""", re.I)
_COMENTARIO_DO_CSS = re.compile(r"/\*.*?(?:\*/|\Z)", re.S)
_ESCAPE_DO_CSS = re.compile(
    r"\\(?:([0-9a-fA-F]{1,6})(?:\r\n|[ \t\n\r\f])?|(\r\n|[\n\r\f])|(.)|\Z)", re.S)


def _decodificar_escapes(css: str) -> str:
    """Uma passada dos escapes do CSS, como a especificação manda. Só calcula.

    `\\2f` e `\\00002f ` são `/`; `\\` antes de outra letra é a letra; `\\`
    antes da quebra de linha some. Código zero, substituto ou fora do Unicode
    vira U+FFFD — é o que o navegador faz.
    """
    def troca(m: re.Match) -> str:
        if m.group(1):
            codigo = int(m.group(1), 16)
            if codigo == 0 or 0xD800 <= codigo <= 0xDFFF or codigo > 0x10FFFF:
                return "\ufffd"
            return chr(codigo)
        if m.group(2):
            return ""
        return m.group(3) or ""
    return _ESCAPE_DO_CSS.sub(troca, css)


def _neutralizar_css(css: str) -> str:
    """`@import`, e `url(` ou texto de rede ou de disco, viram coisa nenhuma."""
    css = re.sub(r"@import", "@x-import-bloqueado", css, flags=re.I)
    css = _URL_NO_CSS.sub(lambda m: "url(" + m.group(1) + "#", css)
    return _TEXTO_NO_CSS.sub(lambda m: m.group(1) + "#", css)


def _vistas_do_css(css: str, *, neutralizando: bool = False) -> list[str]:
    """O CSS cru e cada forma por que ele passa até não ter escape nem
    comentário. A ÚLTIMA é a que sai do filtro. Só calcula.

    Decodifica mais de uma vez de propósito: `\\5c 2f` vira `\\2f` na
    primeira passada, e quem receber o resultado o decodificaria de novo.
    Sobrando `\\` depois das passadas, ele sai — nenhum escape chega ao
    navegador.

    `neutralizando` (o do `<style>`) desarma o perigo de cada forma antes
    de decodificar a seguinte: `url(\\5c\\5c maquina)` é `url(\\\\maquina)`
    para o navegador, e tem de sair `url(#...)`, e não um endereço relativo
    que só por acaso ficou inofensivo.
    """
    vistas = [css]
    atual = css
    for _ in range(4):
        while "/*" in atual:
            atual = _COMENTARIO_DO_CSS.sub("", atual)
        if neutralizando:
            atual = _neutralizar_css(atual)
        vistas.append(atual)
        seguinte = _decodificar_escapes(atual)
        if seguinte == atual:
            break
        atual = seguinte
    atual = atual.replace("\\", "")
    while "/*" in atual:
        atual = _COMENTARIO_DO_CSS.sub("", atual)
    vistas.append(atual)
    return vistas


def _css_perigoso(css: str) -> bool:
    """Este CSS vai buscar algo fora da página, ou roda script?"""
    limpo = _INVISIVEL.sub("", css).lower()
    return bool(_URL_NO_CSS.search(limpo) or _TEXTO_NO_CSS.search(limpo)) or any(
        x in limpo for x in ("expression(", "behavior:", "-moz-binding",
                             "vbscript:", "javascript:", "@import"))


def _valor_perigoso(nome: str, valor: str) -> bool:
    """O valor deste atributo leva a script, ou ao disco do servidor?"""
    limpo = _INVISIVEL.sub("", valor).lower()
    # Em qualquer atributo, e não só nos de endereço: o SMIL do SVG e o
    # `style` antigo do IE aceitavam script em atributo de outro nome.
    if limpo.startswith(_ESQUEMA_PROIBIDO) or "javascript:" in limpo:
        return True
    if nome == "style":
        return any(_css_perigoso(vista) for vista in _vistas_do_css(valor))
    if nome in DE_ENDERECO:
        if limpo.startswith("data:"):
            return not limpo.startswith("data:image/") or limpo.startswith(
                "data:image/svg")
        if _DE_REDE.match(limpo):
            return True
    return False


def _css_sem_saida(css: str) -> str:
    """O CSS do `<style>`, sem ir buscar nada fora da página. Só calcula.

    Sai a forma decodificada (`_vistas_do_css`): o filtro confere o mesmo
    texto que o navegador vai ler. Não se escapa CSS (o `>` é seletor); o
    `</` vira `<\\/`, que para o CSS é o mesmo e para o HTML não fecha a
    etiqueta por dentro. `@import` e `url(` ou texto de rede ou de disco viram
    coisa nenhuma.
    """
    css = _neutralizar_css(_vistas_do_css(css, neutralizando=True)[-1])
    return css.replace("</", "<\\/")


class _Filtro(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.saida: list[str] = []
        self.abertas: list[str] = []
        self.pulando: list[str] = []
        self.no_style = False

    # -- etiquetas

    def _etiqueta(self, tag: str, attrs, fecha_sozinha: bool) -> None:
        if self.pulando:
            if tag in SAI_COM_O_CONTEUDO and not fecha_sozinha:
                self.pulando.append(tag)
            return
        if tag in SAI_COM_O_CONTEUDO:
            if not fecha_sozinha:
                self.pulando.append(tag)
            return
        if tag in SAI_A_ETIQUETA or not _NOME.match(tag):
            return
        partes = [tag]
        for nome, valor in attrs:
            nome = (nome or "").lower()
            if (not _NOME.match(nome) or nome.startswith("on")
                    or nome in SAI_O_ATRIBUTO):
                continue
            if valor is None:
                partes.append(nome)
                continue
            if _valor_perigoso(nome, valor):
                continue
            if nome == "style":
                # Sai o CSS já decodificado, o mesmo que foi conferido.
                valor = _vistas_do_css(valor)[-1]
            partes.append(f'{nome}="{html.escape(valor, quote=True)}"')
        fim = " />" if fecha_sozinha else ">"
        self.saida.append("<" + " ".join(partes) + fim)
        if tag == "style" and not fecha_sozinha:
            self.no_style = True
        if not fecha_sozinha and tag not in VAZIAS:
            self.abertas.append(tag)

    def handle_starttag(self, tag, attrs):
        self._etiqueta(tag, attrs, fecha_sozinha=False)

    def handle_startendtag(self, tag, attrs):
        self._etiqueta(tag, attrs, fecha_sozinha=True)

    def handle_endtag(self, tag):
        if self.pulando:
            if tag == self.pulando[-1]:
                self.pulando.pop()
            return
        if tag in SAI_COM_O_CONTEUDO or tag in SAI_A_ETIQUETA:
            return
        if tag == "style":
            self.no_style = False
        # Só fecha o que está aberto: um `</div>` a mais no teor fecharia o
        # quadro da própria tela, e a página desmontaria a partir dali.
        if tag in self.abertas:
            del self.abertas[len(self.abertas) - 1
                             - self.abertas[::-1].index(tag)]
            self.saida.append(f"</{tag}>")

    # -- o que não é etiqueta

    def handle_data(self, data):
        if self.pulando:
            return
        if self.no_style:
            self.saida.append(_css_sem_saida(data))
            return
        self.saida.append(html.escape(data, quote=False))

    def handle_comment(self, data):
        return

    def handle_decl(self, decl):
        return

    def handle_pi(self, data):
        return

    def unknown_decl(self, data):
        return

    def fechar(self) -> str:
        self.close()
        # O que ficou aberto fecha aqui, para o teor não engolir a tela.
        for tag in reversed(self.abertas):
            self.saida.append(f"</{tag}>")
        return "".join(self.saida)


def limpar(conteudo: Any) -> str:
    """O mesmo HTML, sem o que executa. Só calcula."""
    texto = str(conteudo or "")
    if not texto:
        return ""
    filtro = _Filtro()
    filtro.feed(texto)
    return filtro.fechar()


def sem_script(conteudo: Any) -> Markup:
    """O filtro do Jinja: `{{ a.teor | sem_script }}` no lugar de `|safe`.

    Devolve `Markup` porque o resultado JÁ é seguro — e é isso que dispensa o
    `|safe` na tela, que era a porta aberta.
    """
    return Markup(limpar(conteudo))


def endereco_da_web(valor: Any) -> str:
    """O endereço, se for `http:`/`https:`; senão, texto vazio. Só calcula.

    PARA O LINK QUE VEM DE CENTRAL (LX12, 19/10/2026 — achado M9 do LS02): o
    link da assinatura do CRC, o arquivo do ONRTDPJ e os anexos das notas da
    Central iam crus para o `href`, e um `javascript:` vindo de lá rodaria no
    clique de quem está no balcão. O Jinja escapa as aspas, não o esquema.
    Vazio quer dizer «não vira link» — a tela mostra o rótulo como texto.
    """
    texto = str(valor or "").strip()
    limpo = _INVISIVEL.sub("", texto).lower()
    if limpo.startswith(("http://", "https://")) and texto.lower().startswith(
            ("http://", "https://")):
        return texto
    return ""
