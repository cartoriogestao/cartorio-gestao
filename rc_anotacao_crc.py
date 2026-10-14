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
"""
from __future__ import annotations

import html as html_lib
import re
from datetime import date
from html.parser import HTMLParser
from typing import Any


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


def _extrair_bloco(html_bloco: str) -> dict[str, Any] | None:
    """Lê um bloco entre <hr>. Devolve None se não parecer comunicação."""
    plano = _texto_plano(html_bloco)
    plano_n = _corpo_normalizado(plano)
    if not plano_n:
        return None

    m_titulo = re.search(
        r"(Comunica[cç][aã]o\s+de\s+[^\n<]+)", plano, re.I)
    if not m_titulo:
        # título às vezes cola na mesma linha; tenta no início
        m_titulo = re.search(
            r"^\s*(Comunica[cç][aã]o\s+de\s+.+?)(?:\s{2,}|\n|$)",
            plano, re.I | re.M)
    if not m_titulo:
        return None
    titulo = _espacos(m_titulo.group(1))
    tipo = _tipo_do_titulo(titulo)

    codigo = _pegar(
        r"C[oó]digo\s+da\s+comunica[cç][aã]o\s*:?\s*(\d+)", plano_n)
    if not codigo:
        return None

    # Origem / destino: linhas tipicas entre o titulo e o codigo
    origem = ""
    destino = ""
    trecho_cab = plano[: m_titulo.end() + 400] if m_titulo else plano[:600]
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
            r"C[oó]digo\s+da\s+comunica[cç][aã]o\s*:?\s*\d+",
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


def _texto_compacto(c: dict, *, hoje_br: str) -> str:
    tipo_h = _titulo_humano(c["tipo"], c.get("titulo", ""))
    ind = _indicacao_registro(c)
    nome = c.get("nome_principal") or c.get("falecido") or ""
    codigo = c.get("codigo") or ""

    if c["tipo"] == "OBITO":
        fato = ""
        if c.get("data_fato"):
            fato = f", ocorrido em {c['data_fato']}"
        corpo = (
            f"ANOTAÇÃO: Aos {hoje_br}, anoto o {tipo_h} de {nome}{fato}"
        )
        if ind:
            corpo += f", registrado sob {ind}"
        if c.get("origem_serventia"):
            corpo += f", na serventia {c['origem_serventia']}"
        corpo += f" (Comunicação nº {codigo})."
        return corpo

    if c["tipo"] == "CASAMENTO":
        quem = " e ".join(c["conjuges"]) if c.get("conjuges") else nome
        corpo = f"ANOTAÇÃO: Aos {hoje_br}, anoto o {tipo_h}"
        if quem:
            corpo += f" de {quem}"
        if ind:
            corpo += f", lavrado sob {ind}"
        if c.get("data_lavratura"):
            corpo += f", em {c['data_lavratura']}"
        if c.get("origem_serventia"):
            corpo += f", na serventia {c['origem_serventia']}"
        if c.get("rename_frases"):
            corpo += ". " + "; ".join(c["rename_frases"])
        corpo += f" (Comunicação nº {codigo})."
        return corpo

    # OUTRO
    corpo = f"ANOTAÇÃO: Aos {hoje_br}, anoto o {tipo_h}"
    if nome:
        corpo += f" referente a {nome}"
    if ind:
        corpo += f" ({ind})"
    if c.get("origem_serventia"):
        corpo += f", comunicação de {c['origem_serventia']}"
    corpo += f" (Comunicação nº {codigo})."
    return corpo


def _texto_completo(c: dict, *, cidade_destino: str,
                    assinatura: str) -> str:
    tipo_h = _titulo_humano(c["tipo"], c.get("titulo", ""))
    codigo = c.get("codigo") or ""
    narrativa = c.get("texto_corpo") or ""
    # Corta «OBSERVAÇÕES» se sobrou
    narrativa = re.sub(r"(?i)\s*OBSERVA[CÇ][OÕ]ES\s*:.*$", "", narrativa).strip()

    partes = [
        f"Comunicação de {tipo_h}: Código da comunicação: {codigo} - "
        f"{narrativa}" if narrativa else
        f"Comunicação de {tipo_h}: Código da comunicação: {codigo}."
    ]
    if c.get("origem_serventia"):
        partes.append(f"Origem: {c['origem_serventia']}.")
    cidade = cidade_destino or _cidade_do_destino(c.get("destino", ""))
    partes.append(
        f"Eu, {assinatura}, que anotei. "
        f"{cidade or '______________'}, ___/___/____."
    )
    return " ".join(partes)


def _texto_fe_publica(c: dict, *, hoje_br: str, cidade_destino: str,
                      assinatura: str) -> str:
    tipo_h = _titulo_humano(c["tipo"], c.get("titulo", ""))
    origem = c.get("origem_serventia") or "serventia de origem"
    codigo = c.get("codigo") or ""
    ind = _indicacao_registro(c)
    nome = c.get("nome_principal") or c.get("falecido") or ""
    cidade = cidade_destino or _cidade_do_destino(c.get("destino", ""))

    meio = f"o {tipo_h}"
    if nome:
        meio += f" de {nome}"
    if c["tipo"] == "OBITO" and c.get("data_fato"):
        meio += f", ocorrido em {c['data_fato']}"
    if ind:
        meio += f", {ind}"
    if c.get("data_lavratura"):
        meio += f", lavrado em {c['data_lavratura']}"
    if c["tipo"] == "CASAMENTO" and c.get("rename_frases"):
        meio += ". " + "; ".join(c["rename_frases"])

    texto = (
        f"ANOTAÇÃO: Conforme comunicação recebida da {origem}, por meio "
        f"eletrônico, através da Central do Registro Civil "
        f"(Código nº {codigo}), {meio}. Dou fé. "
        f"{cidade or '______________'}, {hoje_br}."
    )
    if assinatura:
        texto += f" {assinatura}."
    return texto


def gerar(comuns: list[dict], modelo: str, *, hoje=None,
          assinatura: str | None = None, cidade_destino: str | None = None,
          especie: str | None = None) -> dict:
    """Monta os textos de anotação. NÃO ESCREVE no banco nem no assento.

    `especie` filtra por 'OBITO', 'CASAMENTO' ou None (todos).
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
            texto = _texto_compacto(c, hoje_br=hoje_br)
        elif mid == "completo":
            texto = _texto_completo(
                c, cidade_destino=cidade, assinatura=assina or ASSINATURA_PADRAO)
        else:
            texto = _texto_fe_publica(
                c, hoje_br=hoje_br, cidade_destino=cidade,
                assinatura=assina)

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
