"""Etiqueta ODT da averbacao RCPN — para colar na margem do livro.

POR QUE ODT, E NAO SO HTML DA TERMICA
    A faixa do livro e justa: o escrevente abre no LibreOffice, confere e
    imprime so a parte que cabe. HTML de termica resolve firma/RTD; a
    averbacao precisa de arquivo editavel.

CONTEUDO OBRIGATORIO (inspecao)
    teor da averbacao, quem lavrou, selo usado, livro/folha/termo/assento.

MEDIDAS
    Moram em etiqueta.AVERBACAO_RCPN (etiqueta_averbacao_*), independentes
    da firma e do RTD — ajustar a margem do livro nao desalinha a termica.
"""
from __future__ import annotations

import re
import sqlite3
import zipfile
from io import BytesIO
from xml.sax.saxutils import escape

import etiqueta as ETQ
import rc_certidao as RCE

MIME = "application/vnd.oasis.opendocument.text"

_MARCA_LAVROU = re.compile(r"(?im)^\s*Lavrado por:\s*.+$")
_MARCA_SELO = re.compile(r"(?im)^\s*Selo:\s*.+$")


def nome_de_quem_lavrou(con: sqlite3.Connection, criado_por) -> str:
    """Resolve o nome do escrevente a partir de rc_atos.criado_por. So LE."""
    if criado_por is None:
        return ""
    texto = str(criado_por).strip()
    if not texto or texto.lower() in {"operador", "none", "null"}:
        return ""
    if texto.isdigit():
        linha = con.execute(
            "SELECT full_name, username FROM users WHERE id=?",
            (int(texto),)).fetchone()
        if not linha:
            return ""
        return (str(linha["full_name"] or "").strip()
                or str(linha["username"] or "").strip())
    return texto


def funcao_de_quem_lavrou(con: sqlite3.Connection, criado_por) -> str:
    """Cargo/função de quem lavrou, a partir de users.funcao. Só LE.

    Não inventa: sem cadastro ou sem coluna, devolve string vazia — o teor
    de CPF fica só com o nome.
    """
    if criado_por is None:
        return ""
    texto = str(criado_por).strip()
    if not texto or texto.lower() in {"operador", "none", "null"}:
        return ""
    try:
        if texto.isdigit():
            linha = con.execute(
                "SELECT funcao FROM users WHERE id=?",
                (int(texto),)).fetchone()
        else:
            linha = con.execute(
                "SELECT funcao FROM users "
                "WHERE full_name=? OR username=? "
                "ORDER BY CASE WHEN full_name=? THEN 0 ELSE 1 END "
                "LIMIT 1",
                (texto, texto, texto)).fetchone()
    except sqlite3.OperationalError:
        return ""
    if not linha:
        return ""
    try:
        return str(linha["funcao"] or "").strip()
    except (KeyError, IndexError, TypeError):
        return ""


def teor_com_lavratura(teor: str, lavrou: str | None) -> str:
    """Acrescenta a linha Lavrado por se ainda nao estiver no teor.

    Averbacao de CPF usa formato curto com o usuario no fim da linha
    (apos o selo) — nao acrescenta «Lavrado por:».
    """
    base = (teor or "").strip()
    nome = (lavrou or "").strip()
    if not nome or not base:
        return base
    if _MARCA_LAVROU.search(base):
        return base
    # CPF: o escrevente entra no teor curto depois do selo (sincronizar).
    if " ".join(base.split()).lower().startswith("averbo neste assento o cpf"):
        return base
    return base + "\nLavrado por: " + nome + "."


def teor_com_selo(teor: str, selo: str | None) -> str:
    """Acrescenta a linha Selo se o numero existir e ainda nao estiver."""
    base = (teor or "").strip()
    numero = (selo or "").strip()
    if not numero or not base:
        return base
    if numero in base or _MARCA_SELO.search(base):
        return base
    return base + "\nSelo: " + numero + "."


def sincronizar_teor_do_ato(con: sqlite3.Connection, ato_id: int) -> str | None:
    """Garante lavrou+selo no teor a partir das colunas do ato. ESCREVE.

    Averbacao de CPF: reescreve o teor no formato curto do oficial
    (CPF + selo + data + usuario[, função]) depois que o selo existir — livro,
    etiqueta e certidao passam a ver o texto completo.
    """
    ato = con.execute("SELECT * FROM rc_atos WHERE id=?", (int(ato_id),)).fetchone()
    if not ato:
        return None
    lavrou = nome_de_quem_lavrou(con, ato["criado_por"])
    cargo = funcao_de_quem_lavrou(con, ato["criado_por"])
    import rc_cpf as CPF
    reescrito = CPF.reescrever_teor_cpf(
        ato["teor"], selo=ato["selo"], data=ato["data_ato"],
        usuario=lavrou, funcao=cargo)
    if reescrito is not None:
        novo = reescrito
    else:
        novo = teor_com_lavratura(str(ato["teor"] or ""), lavrou)
        novo = teor_com_selo(novo, ato["selo"])
    if novo != (ato["teor"] or "").strip():
        con.execute("UPDATE rc_atos SET teor=? WHERE id=?", (novo, int(ato_id)))
    return novo


def dados_da_etiqueta(con: sqlite3.Connection, ato_id: int,
                      sv: dict | None = None) -> dict:
    """Tudo o que a etiqueta imprime / o ODT leva. So LE."""
    ato = con.execute("SELECT * FROM rc_atos WHERE id=?", (int(ato_id),)).fetchone()
    if not ato:
        raise LookupError("Ato %s nao encontrado." % ato_id)
    if str(ato["tipo"] or "").upper() not in (
            "AVERBACAO", "ANOTACAO", "RETIFICACAO"):
        raise ValueError(
            "So ha etiqueta de margem para averbacao, anotacao ou retificacao.")
    assento = con.execute(
        "SELECT * FROM rc_assentos WHERE id=?", (ato["assento_id"],)).fetchone()
    if not assento:
        raise LookupError("Assento %s nao encontrado." % ato["assento_id"])
    try:
        lugar = RCE.lugar_do_assento(con, int(ato["assento_id"]))
    except sqlite3.OperationalError:
        lugar = RCE._lugar_pelo_assento(con, int(ato["assento_id"]))
    lavrou = nome_de_quem_lavrou(con, ato["criado_por"])
    cargo = funcao_de_quem_lavrou(con, ato["criado_por"])
    import rc_cpf as CPF
    reescrito = CPF.reescrever_teor_cpf(
        ato["teor"], selo=ato["selo"], data=ato["data_ato"],
        usuario=lavrou, funcao=cargo)
    if reescrito is not None:
        teor = reescrito
    else:
        teor = teor_com_selo(
            teor_com_lavratura(str(ato["teor"] or ""), lavrou), ato["selo"])
    casa = ""
    if sv:
        casa = str(sv.get("unit_name") or "").strip()
    return {
        "ato_id": int(ato["id"]),
        "assento_id": int(assento["id"]),
        "tipo": str(ato["tipo"] or ""),
        "teor": teor,
        "lavrou": lavrou,
        "selo": str(ato["selo"] or "").strip(),
        "data_ato": str(ato["data_ato"] or "")[:10],
        "fundamento": str(ato["fundamento"] or "").strip(),
        "nome": str(assento["nome"] or "").strip(),
        "matricula": str(assento["matricula"] or "").strip(),
        "especie": str(assento["especie"] or "").strip(),
        "livro": lugar.get("livro") or assento["livro_volume"] or "",
        "folha": lugar.get("folha") or "",
        "termo": lugar.get("termo") or assento["numero"] or "",
        "cartorio": casa,
    }


def _mm_to_cm(mm: float) -> str:
    return ("%.4fcm" % (float(mm) / 10.0)).replace(".0000", ".0")


def _paragrafo(texto: str, estilo: str = "P") -> str:
    linhas = (texto or "").splitlines() or [""]
    partes = []
    for i, linha in enumerate(linhas):
        if i:
            partes.append("<text:line-break/>")
        partes.append(escape(linha) if linha else "")
    corpo = "".join(partes) or " "
    return '<text:p text:style-name="%s">%s</text:p>' % (estilo, corpo)


def arquivo_odt(dados: dict, medidas: dict) -> bytes:
    """Monta o .odt da etiqueta no tamanho configurado. So calcula."""
    largura = float(medidas["etiqueta_largura_mm"])
    altura = float(medidas["etiqueta_altura_mm"])
    margem = float(medidas["etiqueta_margem_mm"])
    dx = float(medidas.get("etiqueta_deslocamento_x_mm") or 0)
    dy = float(medidas.get("etiqueta_deslocamento_y_mm") or 0)
    corpo_pt = float(medidas["etiqueta_corpo_pt"])
    entrelinha = float(medidas["etiqueta_entrelinha"])

    m_esq = max(0.0, margem + max(0.0, dx))
    m_dir = max(0.0, margem + max(0.0, -dx))
    m_sup = max(0.0, margem + max(0.0, dy))
    m_inf = max(0.0, margem + max(0.0, -dy))

    titulo = {
        "AVERBACAO": "AVERBACAO",
        "ANOTACAO": "ANOTACAO",
        "RETIFICACAO": "RETIFICACAO",
    }.get(str(dados.get("tipo") or "").upper(), "ATO")

    refs = []
    if dados.get("livro"):
        refs.append("Livro %s" % dados["livro"])
    if dados.get("folha") not in (None, ""):
        refs.append("fl. %s" % dados["folha"])
    if dados.get("termo") not in (None, ""):
        refs.append("termo %s" % dados["termo"])
    refs.append("assento %s" % dados.get("assento_id"))
    if dados.get("nome"):
        refs.append(str(dados["nome"]))

    blocos = [
        _paragrafo(dados.get("cartorio") or "", "P-cab"),
        _paragrafo(titulo, "P-tit"),
        _paragrafo(" · ".join(str(x) for x in refs if x), "P-ref"),
        _paragrafo(str(dados.get("teor") or ""), "P"),
    ]
    teor = str(dados.get("teor") or "")
    # Formato curto de CPF ja traz usuario e selo na mesma linha — nao duplicar.
    if (dados.get("lavrou") and "Lavrado por:" not in teor
            and dados["lavrou"] not in teor):
        blocos.append(_paragrafo("Lavrado por: %s." % dados["lavrou"], "P"))
    if (dados.get("selo") and ("Selo: %s" % dados["selo"]) not in teor
            and dados["selo"] not in teor):
        blocos.append(_paragrafo("Selo: %s." % dados["selo"], "P-selo"))

    fs = "%spt" % corpo_pt
    lh = "%s" % entrelinha
    ref_pt = "%spt" % max(6.0, corpo_pt - 1)
    styles = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
 xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.2">
 <office:automatic-styles>
  <style:page-layout style:name="pm1">
   <style:page-layout-properties
     fo:page-width="%s"
     fo:page-height="%s"
     style:print-orientation="portrait"
     fo:margin-top="%s"
     fo:margin-bottom="%s"
     fo:margin-left="%s"
     fo:margin-right="%s"/>
  </style:page-layout>
 </office:automatic-styles>
 <office:master-styles>
  <style:master-page style:name="Standard" style:page-layout-name="pm1"/>
 </office:master-styles>
</office:document-styles>
""" % (_mm_to_cm(largura), _mm_to_cm(altura), _mm_to_cm(m_sup),
       _mm_to_cm(m_inf), _mm_to_cm(m_esq), _mm_to_cm(m_dir))

    content = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
 xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.2">
 <office:automatic-styles>
  <style:style style:name="P" style:family="paragraph">
   <style:paragraph-properties fo:margin-top="0cm" fo:margin-bottom="0.05cm"
     fo:line-height="%s*" fo:text-align="justify"/>
   <style:text-properties style:font-name="Arial" fo:font-size="%s"
     style:font-name-asian="Arial" style:font-size-asian="%s"/>
  </style:style>
  <style:style style:name="P-cab" style:family="paragraph">
   <style:paragraph-properties fo:margin-bottom="0.05cm" fo:text-align="center"/>
   <style:text-properties style:font-name="Arial" fo:font-size="%s"
     fo:font-weight="bold" fo:text-transform="uppercase"/>
  </style:style>
  <style:style style:name="P-tit" style:family="paragraph">
   <style:paragraph-properties fo:margin-bottom="0.05cm" fo:text-align="center"/>
   <style:text-properties style:font-name="Arial" fo:font-size="%s"
     fo:font-weight="bold"/>
  </style:style>
  <style:style style:name="P-ref" style:family="paragraph">
   <style:paragraph-properties fo:margin-bottom="0.08cm" fo:text-align="left"/>
   <style:text-properties style:font-name="Arial" fo:font-size="%s"/>
  </style:style>
  <style:style style:name="P-selo" style:family="paragraph">
   <style:paragraph-properties fo:margin-top="0.05cm" fo:margin-bottom="0cm"/>
   <style:text-properties style:font-name="Courier New" fo:font-size="%s"
     fo:font-weight="bold"/>
  </style:style>
 </office:automatic-styles>
 <office:body><office:text>
%s
 </office:text></office:body>
</office:document-content>
""" % (lh, fs, fs, fs, fs, ref_pt, fs, "\n".join(blocos))

    manifest = """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2">
 <manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>
 <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
 <manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>
</manifest:manifest>
"""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        z.writestr(info, MIME)
        z.writestr("META-INF/manifest.xml", manifest)
        z.writestr("styles.xml", styles)
        z.writestr("content.xml", content)
    return buf.getvalue()


def nome_arquivo(dados: dict) -> str:
    tipo = str(dados.get("tipo") or "ato").lower()
    return "etiqueta-%s-%s.odt" % (tipo, dados.get("ato_id"))