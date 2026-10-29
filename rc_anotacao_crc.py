"""Anotação a partir de comunicação CRC recebida — prévia de texto, offline.

    «vamos seguir no desenvolvimento do nosso módulo maduro e completo de RCPN»
    — o oficial, 07/09/2026

O QUE É, EM UMA FRASE
    A CRC manda HTML com comunicações de casamento, óbito e alterações de
    estado civil. Esta casa precisa **anotar à margem** dos assentos daqui.
    Este módulo **lê o HTML e monta o texto da anotação** — e só isso.

O QUE ESTE MÓDULO NÃO FAZ
    **Não anota sozinho na margem do assento.** O art. 370 manda conferir a
    compatibilidade dos atos registrários antes. Um programa que anotasse
    sozinho estaria decidindo que dois assentos são da mesma pessoa.

    **Não chama a internet.** Não há urllib, requests nem websocket: o arquivo
    HTML já veio baixado da Central, e o texto sai daqui. Offline de ponta a
    ponta.

    **Não inventa livro, folha nem termo.** Só entra o que o HTML trouxe.

A NORMA QUE ORIENTA O TEXTO — art. 369
    A anotação contém: (I) a data; (II) a indicação do registro ou averbação;
    (III) a serventia, o livro, a folha e o número do registro. Os três modelos
    abaixo cobrem esses elementos, em estilos curtos ou mais longos — a casa
    escolhe qual cola na margem.

O TEXTO DOS MODELOS MORA EM `modelos_padrao/rcpn/` (LF06C, 19/10/2026)
    «Não deveríamos ter modelos no código; deveriam estar no banco, para
     editar com mais facilidade.» — o oficial. Cada modelo é um papel do
    catálogo (`RC_ANOTACAO_CRC_COMPACTA`, `_COMPLETA`, `_FE_PUBLICA`), e cada
    frase que a comunicação pode trazer ou não — a data do óbito, o livro, a
    serventia de origem — é uma peça dele. A REGRA de qual frase entra, por
    espécie e pelo dado que veio, fica aqui, com a pontuação que as emenda. O
    que se LÊ da CRC («passou a assinar», o título do ato) não é modelo: é o
    eco do texto da Central, e também fica.
"""
from __future__ import annotations

import html as html_lib
import re
from datetime import date
from html.parser import HTMLParser
from typing import Any

import rc_textos as TEXTOS


class AnotacaoCrcError(ValueError):
    """Erro de leitura ou geração, com mensagem pronta para o balcão."""


# ------------------------------------------------------------------- modelos

MODELOS: dict[str, dict[str, str]] = {
    "compacto": {
        "id": "compacto",
        "rotulo": "Modelo 1 — Compacto",
        "descricao": "Estilo curto (indicação do ato + livro/folha/termo).",
    },
    "completo": {
        "id": "completo",
        "rotulo": "Modelo 2 — Completo",
        "descricao": "Mantém mais da narrativa da comunicação, com fechamento.",
    },
    "fe_publica": {
        "id": "fe_publica",
        "rotulo": "Modelo 3 — Com fé pública",
        "descricao": "Forma com menção à CRC e «Dou fé».",
    },
}

ASSINATURA_PADRAO = "_____, Escrevente Autorizado (a)"


# -------------------------------------------------------------- extrair HTML


class _TextoDoHtml(HTMLParser):
    """Tira só o texto visível, sem tags — e normaliza espaços depois."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._pedacos: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self._pedacos.append(data)

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag in ("br", "p", "div", "hr", "tr", "li"):
            self._pedacos.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("p", "div", "tr", "li", "h1", "h2", "h3", "center"):
            self._pedacos.append("\n")

    def texto(self) -> str:
        return "".join(self._pedacos)


def _texto_plano(html: str) -> str:
    p = _TextoDoHtml()
    try:
        p.feed(html)
        p.close()
    except Exception:  # noqa: BLE001 — HTML malformado ainda pode renderizar
        bruto = re.sub(r"(?i)<br\s*/?>", "\n", html)
        bruto = re.sub(r"(?i)</?(p|div|center|tr|li)[^>]*>", "\n", bruto)
        bruto = re.sub(r"(?i)<[^>]+>", " ", bruto)
        return html_lib.unescape(bruto)
    return html_lib.unescape(p.texto())


def _espacos(t: str) -> str:
    return re.sub(r"[ \t]+", " ", (t or "").replace("\r", "")).strip()


def _corpo_normalizado(t: str) -> str:
    linhas = [_espacos(x) for x in (t or "").splitlines()]
    linhas = [x for x in linhas if x]
    return " ".join(linhas)


def _tipo_do_titulo(titulo: str) -> str:
    u = (titulo or "").upper()
    if "ÓBITO" in u or "OBITO" in u:
        return "OBITO"
    if "CASAMENTO" in u:
        return "CASAMENTO"
    return "OUTRO"


def _titulo_humano(tipo: str, titulo_raw: str = "") -> str:
    if tipo == "OBITO":
        return "óbito"
    if tipo == "CASAMENTO":
        if "RELIGIOS" in (titulo_raw or "").upper():
            return "casamento religioso"
        return "casamento civil"
    t = (titulo_raw or "").strip()
    if t.lower().startswith("comunicação de"):
        return t[len("comunicação de"):].strip().lower() or "ato"
    return t.lower() or "ato"


def _pegar(padrao: str, texto: str, flags: int = re.I | re.S) -> str:
    m = re.search(padrao, texto, flags)
    return _espacos(m.group(1)) if m else ""


_INICIO_DO_TITULO = re.compile(r"Comunica[cç][aã]o\s+de(\s+)", re.I)


def _titulo_no_inicio_da_linha(plano: str) -> tuple[str, int] | None:
    """O título no começo de uma linha: o texto e onde o achado termina.

    ERA UMA EXPRESSÃO SÓ — `^\\s*(Comunicação\\s+de\\s+.+?)(?:\\s{2,}|\\n|$)`,
    com `re.M` —, e o CodeQL a acusou (alerta #189): o `.+?` e o `\\s{2,}`
    disputam os mesmos brancos, e o `^\\s*` atravessa linha em branco a
    partir de cada começo de linha. Um bloco com milhares de brancos fazia
    a conta crescer pelo quadrado. Aqui o mesmo resultado sai de uma
    passada: o começo de cada linha, os brancos pulados uma vez só, o
    prefixo conferido no lugar, e o fim procurado para a frente. Devolve o
    mesmo texto e o mesmo fim que a expressão devolvia — conferido contra
    ela em textos sorteados (29/10/2026).
    """
    n = len(plano)
    p = 0
    while p <= n:
        q = p
        while q < n and plano[q].isspace():
            q += 1
        m = _INICIO_DO_TITULO.match(plano, q)
        if m:
            # O `.+?` começa no último lugar que o `\s+` greedy deixa:
            # pelo menos um branco depois do «de», e nunca numa quebra.
            s = m.end()
            while s > m.start(1) + 1 and (s >= n or plano[s] == "\n"):
                s -= 1
            if s < n and plano[s] != "\n":
                e = s + 1
                while e < n and plano[e] != "\n" and not (
                        plano[e].isspace() and e + 1 < n
                        and plano[e + 1].isspace()):
                    e += 1
                fim = e
                if e + 1 < n and plano[e].isspace() and plano[e + 1].isspace():
                    while fim < n and plano[fim].isspace():
                        fim += 1
                elif e < n:
                    fim = e + 1
                return plano[q:e], fim
        quebra = plano.find("\n", q)
        if quebra < 0:
            return None
        p = quebra + 1
    return None


def _extrair_bloco(html_bloco: str) -> dict[str, Any] | None:
    """Lê um bloco entre <hr>. Devolve None se não parecer comunicação."""
    plano = _texto_plano(html_bloco)
    plano_n = _corpo_normalizado(plano)
    if not plano_n:
        return None

    m_titulo = re.search(
        r"(Comunica[cç][aã]o\s+de\s+[^\n<]+)", plano, re.I)
    if m_titulo:
        titulo = _espacos(m_titulo.group(1))
        fim_titulo = m_titulo.end()
    else:
        # título às vezes cola na mesma linha; tenta no início
        achado = _titulo_no_inicio_da_linha(plano)
        if not achado:
            return None
        titulo = _espacos(achado[0])
        fim_titulo = achado[1]
    tipo = _tipo_do_titulo(titulo)

    # `\s*(?::\s*)?`, e não `\s*:?\s*` (CodeQL #274, 29/10/2026): os dois
    # `\s*` em volta do `:` opcional disputavam os mesmos brancos, e uma
    # fileira deles sem número no fim custava tempo quadrático. Casa o mesmo.
    codigo = _pegar(
        r"C[oó]digo\s+da\s+comunica[cç][aã]o\s*(?::\s*)?(\d+)", plano_n)
    if not codigo:
        return None

    # Origem / destino: linhas tipicas entre o titulo e o codigo
    origem = ""
    destino = ""
    trecho_cab = plano[: fim_titulo + 400]
    linhas_cab = [_espacos(x) for x in trecho_cab.splitlines() if _espacos(x)]
    # Filtra titulo e codigo
    uteis = []
    for ln in linhas_cab:
        if re.match(r"(?i)^comunica", ln):
            continue
        if re.match(r"(?i)^c[oó]digo\s+da\s+comunica", ln):
            break
        if re.match(r"(?i)^\d{5,}$", ln):
            break
        uteis.append(ln)
    for ln in uteis:
        if re.match(r"(?i)^ao\s+", ln):
            if not destino:
                destino = re.sub(r"(?i)^ao\s+", "", ln).strip()
        elif not origem:
            origem = ln

    # Corpo: a partir de "Aos DD/MM/AAAA" ate OBSERVACOES
    corpo_m = re.search(
        r"(Aos\s+\d{1,2}/\d{1,2}/\d{4}.+?)(?:OBSERVA[CÇ][OÕ]ES\s*:|$)",
        plano_n, re.I | re.S)
    texto_corpo = _corpo_normalizado(corpo_m.group(1)) if corpo_m else ""
    if not texto_corpo:
        # fallback: tudo depois do codigo
        apos = re.split(
            r"C[oó]digo\s+da\s+comunica[cç][aã]o\s*(?::\s*)?\d+",
            plano_n, maxsplit=1, flags=re.I)
        texto_corpo = _corpo_normalizado(apos[1] if len(apos) > 1 else "")
        texto_corpo = re.sub(
            r"(?i)OBSERVA[CÇ][OÕ]ES\s*:.*$", "", texto_corpo).strip()

    data_lavratura = _pegar(
        r"Aos\s+(\d{1,2}/\d{1,2}/\d{4})", texto_corpo)
    # livro: letra + numero
    m_liv = re.search(
        r"no\s+livro\s+([A-Z])\s+n[uú]mero\s+(\d+)", texto_corpo, re.I)
    livro = ""
    if m_liv:
        livro = f"{m_liv.group(1).upper()} {m_liv.group(2)}"
    folhas = _pegar(r"folhas?\s+(\d+)", texto_corpo)
    termo = _pegar(r"termo\s+(\d+)", texto_corpo)

    conjuges: list[str] = []
    falecido = ""
    nome_principal = ""
    data_fato = ""
    rename_frases: list[str] = []

    if tipo == "CASAMENTO":
        m_cas = re.search(
            r"casamento\s+(?:civil\s+)?de\s*:\s*(.+?),\s*"
            r"a\s+qual\s+passou\s+a\s+assinar\s*:\s*(.+?),\s*e\s+(.+?),\s*"
            r"o\s+qual\s+",
            texto_corpo, re.I)
        if m_cas:
            n1, n1novo, n2 = (_espacos(m_cas.group(i)) for i in (1, 2, 3))
            conjuges = [n1, n2]
            nome_principal = n1
            if n1novo and n1novo.upper() != n1.upper():
                rename_frases.append(
                    f"{n1} passou a assinar {n1novo}")
            # conjuge 2: «continuou com o mesmo nome» — sem rename
        else:
            m_cas2 = re.search(
                r"casamento\s+(?:civil\s+)?de\s*:\s*(.+)", texto_corpo, re.I)
            if m_cas2:
                nome_principal = _espacos(m_cas2.group(1).split(",")[0])
    elif tipo == "OBITO":
        m_ob = re.search(
            r"[oó]bito\s+de\s+(.+?)\s+ocorrido\s+em\s+"
            r"(\d{1,2}/\d{1,2}/\d{4})",
            texto_corpo, re.I)
        if m_ob:
            falecido = _espacos(m_ob.group(1))
            nome_principal = falecido
            data_fato = m_ob.group(2)
        else:
            m_ob2 = re.search(r"[oó]bito\s+de\s+([A-ZÁÉÍÓÚÃÕÂÊÔÇÜ ]+)",
                              texto_corpo, re.I)
            if m_ob2:
                falecido = _espacos(m_ob2.group(1))
                nome_principal = falecido
    else:
        # OUTRO — tenta pegar nomes apos «de »
        m_out = re.search(
            r"(?:casamento|div[oó]rcio)[^.]*?\s+de\s+(.+?)(?:,|\.|CONFORME)",
            texto_corpo, re.I)
        if m_out:
            nome_principal = _espacos(m_out.group(1))[:120]

    excerpt = html_bloco.strip()
    if len(excerpt) > 800:
        excerpt = excerpt[:800] + "…"

    return {
        "tipo": tipo,
        "titulo": titulo,
        "codigo": codigo,
        "origem_serventia": origem,
        "destino": destino,
        "data_lavratura": data_lavratura,
        "livro": livro,
        "folhas": folhas,
        "termo": termo,
        "nome_principal": nome_principal,
        "conjuges": conjuges,
        "falecido": falecido,
        "data_fato": data_fato,
        "rename_frases": rename_frases,
        "texto_corpo": texto_corpo,
        "raw_excerpt": excerpt,
    }


def ler_arquivo(html: str) -> list[dict]:
    """Lê o HTML da CRC e devolve a lista de comunicações. SÓ LÊ.

    Raise AnotacaoCrcError se o HTML estiver vazio ou sem blocos reconhecíveis.
    """
    if not (html or "").strip():
        raise AnotacaoCrcError(
            "O arquivo HTML está vazio. Exporte as comunicações da CRC e "
            "envie o .html baixado.")

    # Blocos separados por <hr> (com ou sem atributos)
    partes = re.split(r"(?i)<hr\b[^>]*>", html)
    comuns: list[dict] = []
    for parte in partes:
        bloco = _extrair_bloco(parte)
        if bloco:
            comuns.append(bloco)

    if not comuns:
        raise AnotacaoCrcError(
            "Não achei comunicação nenhuma neste HTML. Confira se o arquivo "
            "é o de comunicações da CRC (títulos como «Comunicação de Óbito» "
            "ou «Comunicação de Casamento Civil», com código da comunicação).")
    return comuns


# --------------------------------------------------------------- gerar texto
#
# OS TRÊS PAPÉIS E AS PEÇAS DE CADA UM. `CHAVES_DO_MODELO` é o que a tela lê
# da casa pela busca única antes de chamar `gerar`: o papel do modelo
# escolhido e as peças que ele pode usar — e só elas, para não ir ao banco
# atrás de texto que a montagem não pede.

CHAVE_COMPACTA = "RC_ANOTACAO_CRC_COMPACTA"
CHAVE_COMPLETA = "RC_ANOTACAO_CRC_COMPLETA"
CHAVE_FE_PUBLICA = "RC_ANOTACAO_CRC_FE_PUBLICA"

CHAVES_DO_MODELO: dict[str, tuple[str, ...]] = {
    "compacto": (CHAVE_COMPACTA,
                 "RC_ANOTACAO_CRC_COMPACTA__ocorrido_em",
                 "RC_ANOTACAO_CRC_COMPACTA__registrado_sob",
                 "RC_ANOTACAO_CRC_COMPACTA__lavrado_sob",
                 "RC_ANOTACAO_CRC_COMPACTA__na_serventia",
                 "RC_ANOTACAO_CRC_COMPACTA__referente_a",
                 "RC_ANOTACAO_CRC_COMPACTA__comunicacao_de"),
    "completo": (CHAVE_COMPLETA,
                 "RC_ANOTACAO_CRC_COMPLETA__origem"),
    "fe_publica": (CHAVE_FE_PUBLICA,
                   "RC_ANOTACAO_CRC_FE_PUBLICA__ocorrido_em",
                   "RC_ANOTACAO_CRC_FE_PUBLICA__lavrado_em"),
}


def _texto_de(chave: str, textos: dict[str, str] | None) -> str:
    """O texto do papel ou da peça que vale nesta montagem. Só lê.

    O que a tela leu da casa vem em `textos`; o que não veio — a chamada sem
    conexão, o teste, a ferramenta avulsa — é o padrão da base. Texto vazio
    também cai no padrão, como no `protesto_termo.montar`: uma peça apagada
    por engano tiraria da margem um elemento do art. 369 sem ninguém ver.
    """
    return (textos or {}).get(chave) or TEXTOS.texto(chave)


def _peca(chave: str, textos: dict[str, str] | None, **claros: Any) -> str:
    """A peça com os claros preenchidos. Só calcula."""
    return _texto_de(chave, textos).format(**claros)


def _hoje_br(hoje: str | date | None) -> str:
    if hoje is None:
        d = date.today()
    elif isinstance(hoje, date):
        d = hoje
    else:
        s = str(hoje).strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}", s):
            d = date.fromisoformat(s[:10])
        elif re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", s):
            dd, mm, aa = s.split("/")
            d = date(int(aa), int(mm), int(dd))
        else:
            d = date.today()
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def _cidade_do_destino(destino: str, fallback: str = "") -> str:
    """Tenta tirar a cidade do campo destino («Ao Cidade Destino - …»)."""
    d = (destino or "").strip()
    if not d:
        return (fallback or "").strip()
    # «Cidade Destino - Registro Civil…» → Cidade Destino
    parte = d.split("-")[0].strip()
    return parte or fallback or d


def _indicacao_registro(c: dict) -> str:
    pedacos = []
    if c.get("livro"):
        pedacos.append(f"livro {c['livro']}")
    if c.get("folhas"):
        pedacos.append(f"folhas {c['folhas']}")
    if c.get("termo"):
        pedacos.append(f"termo {c['termo']}")
    return ", ".join(pedacos)


def _texto_compacto(c: dict, *, hoje_br: str,
                    textos: dict[str, str] | None = None) -> str:
    """O modelo 1 (`RC_ANOTACAO_CRC_COMPACTA`). Só calcula.

    O papel é a moldura — data, ato e código —, e `{complemento}` são as
    frases que a espécie pede e o dado permite, cada uma peça do papel. A
    ordem e a pontuação entre elas são da regra, e ficam aqui.
    """
    tipo_h = _titulo_humano(c["tipo"], c.get("titulo", ""))
    ind = _indicacao_registro(c)
    nome = c.get("nome_principal") or c.get("falecido") or ""
    codigo = c.get("codigo") or ""
    origem = c.get("origem_serventia")

    complemento = ""
    if c["tipo"] == "OBITO":
        # O «de» entra mesmo sem nome («anoto o óbito de , na serventia …»):
        # é o texto de antes, e o ouro do LF06C o guarda como estava.
        complemento = f" de {nome}"
        if c.get("data_fato"):
            complemento += _peca("RC_ANOTACAO_CRC_COMPACTA__ocorrido_em",
                                 textos, data=c["data_fato"])
        if ind:
            complemento += _peca("RC_ANOTACAO_CRC_COMPACTA__registrado_sob",
                                 textos, indicacao=ind)
        if origem:
            complemento += _peca("RC_ANOTACAO_CRC_COMPACTA__na_serventia",
                                 textos, origem=origem)
    elif c["tipo"] == "CASAMENTO":
        quem = " e ".join(c["conjuges"]) if c.get("conjuges") else nome
        if quem:
            complemento += f" de {quem}"
        if ind:
            complemento += _peca("RC_ANOTACAO_CRC_COMPACTA__lavrado_sob",
                                 textos, indicacao=ind)
        if c.get("data_lavratura"):
            complemento += f", em {c['data_lavratura']}"
        if origem:
            complemento += _peca("RC_ANOTACAO_CRC_COMPACTA__na_serventia",
                                 textos, origem=origem)
        if c.get("rename_frases"):
            complemento += ". " + "; ".join(c["rename_frases"])
    else:
        # OUTRO
        if nome:
            complemento += " " + _peca("RC_ANOTACAO_CRC_COMPACTA__referente_a",
                                       textos, nome=nome)
        if ind:
            complemento += f" ({ind})"
        if origem:
            complemento += _peca("RC_ANOTACAO_CRC_COMPACTA__comunicacao_de",
                                 textos, origem=origem)

    return _texto_de(CHAVE_COMPACTA, textos).format(
        hoje=hoje_br, ato=tipo_h, complemento=complemento, codigo=codigo)


def _texto_completo(c: dict, *, cidade_destino: str, assinatura: str,
                    textos: dict[str, str] | None = None) -> str:
    """O modelo 2 (`RC_ANOTACAO_CRC_COMPLETA`). Só calcula.

    A narrativa da comunicação entra emendada por « - »; sem ela, o código
    fecha com ponto. «Origem: …» é peça, e só entra quando a comunicação diz
    a serventia.
    """
    tipo_h = _titulo_humano(c["tipo"], c.get("titulo", ""))
    codigo = c.get("codigo") or ""
    narrativa = c.get("texto_corpo") or ""
    # Corta «OBSERVAÇÕES» se sobrou
    narrativa = re.sub(r"(?i)\s*OBSERVA[CÇ][OÕ]ES\s*:.*$", "", narrativa).strip()

    frase_origem = ""
    if c.get("origem_serventia"):
        frase_origem = " " + _peca("RC_ANOTACAO_CRC_COMPLETA__origem", textos,
                                   origem=c["origem_serventia"])
    cidade = cidade_destino or _cidade_do_destino(c.get("destino", ""))
    return _texto_de(CHAVE_COMPLETA, textos).format(
        ato=tipo_h, codigo=codigo,
        narrativa=f" - {narrativa}" if narrativa else ".",
        frase_origem=frase_origem, assinatura=assinatura,
        cidade=cidade or "______________")


def _texto_fe_publica(c: dict, *, hoje_br: str, cidade_destino: str,
                      assinatura: str,
                      textos: dict[str, str] | None = None) -> str:
    """O modelo 3 (`RC_ANOTACAO_CRC_FE_PUBLICA`). Só calcula.

    Cada claro entre o ato e o ponto traz a própria pontuação e fica vazio
    quando a comunicação não tem o dado; a data do óbito só vale no óbito, e
    os nomes novos, só no casamento.
    """
    tipo_h = _titulo_humano(c["tipo"], c.get("titulo", ""))
    origem = c.get("origem_serventia") or "serventia de origem"
    codigo = c.get("codigo") or ""
    ind = _indicacao_registro(c)
    nome = c.get("nome_principal") or c.get("falecido") or ""
    cidade = cidade_destino or _cidade_do_destino(c.get("destino", ""))

    ocorrido_em = ""
    if c["tipo"] == "OBITO" and c.get("data_fato"):
        ocorrido_em = _peca("RC_ANOTACAO_CRC_FE_PUBLICA__ocorrido_em", textos,
                            data=c["data_fato"])
    lavrado_em = ""
    if c.get("data_lavratura"):
        lavrado_em = _peca("RC_ANOTACAO_CRC_FE_PUBLICA__lavrado_em", textos,
                           data=c["data_lavratura"])
    novos_nomes = ""
    if c["tipo"] == "CASAMENTO" and c.get("rename_frases"):
        novos_nomes = ". " + "; ".join(c["rename_frases"])

    return _texto_de(CHAVE_FE_PUBLICA, textos).format(
        origem=origem, codigo=codigo, ato=tipo_h,
        de_quem=f" de {nome}" if nome else "",
        ocorrido_em=ocorrido_em,
        indicacao=f", {ind}" if ind else "",
        lavrado_em=lavrado_em, novos_nomes=novos_nomes,
        cidade=cidade or "______________", hoje=hoje_br,
        assinatura=f" {assinatura}." if assinatura else "")


def gerar(comuns: list[dict], modelo: str, *, hoje=None,
          assinatura: str | None = None, cidade_destino: str | None = None,
          especie: str | None = None,
          textos: dict[str, str] | None = None) -> dict:
    """Monta os textos de anotação. NÃO ESCREVE no banco nem no assento.

    `especie` filtra por 'OBITO', 'CASAMENTO' ou None (todos).
    `textos` é o que a tela leu da casa pela busca única — chave → texto, do
    papel e das peças de `CHAVES_DO_MODELO[modelo]`; o que faltar sai do
    padrão da base. Esta função continua pura: quem tem a conexão lê.
    Devolve ``{ok, modelo, itens:[{codigo,titulo,texto,...}], texto}``.
    """
    mid = (modelo or "").strip().lower()
    if mid not in MODELOS:
        raise AnotacaoCrcError(
            f"Modelo «{modelo}» desconhecido. Use: "
            + ", ".join(MODELOS) + ".")
    if not comuns:
        raise AnotacaoCrcError("Não há comunicações para gerar o texto.")

    filtro = (especie or "").strip().upper() or None
    if filtro and filtro not in ("OBITO", "CASAMENTO"):
        raise AnotacaoCrcError(
            "O filtro de espécie aceita só OBITO, CASAMENTO ou vazio (todos).")

    hoje_br = _hoje_br(hoje)
    assina = (assinatura if assinatura is not None else ASSINATURA_PADRAO) or ""
    cidade = (cidade_destino or "").strip()

    itens: list[dict] = []
    for c in comuns:
        if filtro and c.get("tipo") != filtro:
            continue
        if mid == "compacto":
            texto = _texto_compacto(c, hoje_br=hoje_br, textos=textos)
        elif mid == "completo":
            texto = _texto_completo(
                c, cidade_destino=cidade, assinatura=assina or ASSINATURA_PADRAO,
                textos=textos)
        else:
            texto = _texto_fe_publica(
                c, hoje_br=hoje_br, cidade_destino=cidade,
                assinatura=assina, textos=textos)

        itens.append({
            "codigo": c.get("codigo"),
            "titulo": c.get("titulo"),
            "tipo": c.get("tipo"),
            "nome_principal": c.get("nome_principal"),
            "texto": texto,
        })

    if not itens:
        raise AnotacaoCrcError(
            "Nenhuma comunicação bateu com o filtro escolhido.")

    return {
        "ok": True,
        "modelo": mid,
        "rotulo": MODELOS[mid]["rotulo"],
        "itens": itens,
        "texto": "\n\n".join(x["texto"] for x in itens),
    }


def __getattr__(nome: str):
    """Os nomes antigos dos três modelos, lidos da base dos padrões.

    O TEXTO SAIU DESTE MÓDULO NO LF06C (19/10/2026) e mora em
    `modelos_padrao/rcpn/`. `ANOTACAO_COMPACTA`, `ANOTACAO_COMPLETA` e
    `ANOTACAO_FE_PUBLICA` são os nomes que o catálogo dá aos três papéis, e
    quem os pede recebe o padrão da base — o MESMO que a anotação usa, e não
    uma cópia que ficou para trás. Nome que não é de papel continua sendo
    `AttributeError`.
    """
    if nome.startswith("__"):
        raise AttributeError(nome)
    import modelos_da_casa as _MODELOS
    return _MODELOS.constante_antiga(__name__, nome)
