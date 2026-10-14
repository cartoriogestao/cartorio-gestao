# -*- coding: utf-8 -*-
"""Adapters do motor: HTML (mesmos claros do quadro), ODT e PDF.

PDF/ODT reusam `rc_certidao_odt.arquivo_da_certidao` + `impressao_pdf` —
não reinventam LibreOffice. Prévia RESUMO deixa de ser a frase
“sai o quadro CNJ” e passa a renderizar o quadro pelos mesmos claros.
"""
from __future__ import annotations

import base64
import re
from typing import Any

from modelos_motor_contexto import (
    claros_do_contexto,
    contexto_de_exemplo,
    corrigir_pessoas_naturais,
    eh_template_termo,
)
from modelos_motor_html import escapar, html_para_texto_impressao, parece_html

# Autoria neutra do ODT gerado pelo motor (2b). Nunca o nome de quem desenhou
# o molde: vale o nome da serventia (`{{serventia.nome}}`, do cadastro) e, sem
# ele, o nome do sistema.
AUTOR_SISTEMA = "Cartório Gestão"
# semente genérica de `serventia.PADRAO` — não serve de autor
_NOMES_PLACEHOLDER = {"", "NOME DA SERVENTIA"}


# Rótulos amigáveis para a prévia HTML (ordem aproximada do Anexo CNJ)
_ROTULOS_NASC = (
    ("@nomenascido", "Nome"),
    ("@cpfnascido", "CPF"),
    ("@matriculanascido", "Matrícula"),
    ("@datanascimentoextensoCN", "Data de nascimento"),
    ("@dianascimento", "Dia"),
    ("@mesnascimento", "Mês"),
    ("@anonascimento", "Ano"),
    ("@horanascimento", "Hora"),
    ("@naturalidade_cidade", "Naturalidade"),
    ("@naturalidade_uf", "UF naturalidade"),
    ("@local_nascimento", "Local de nascimento"),
    ("@municipio_nascimento", "Município de nascimento"),
    ("@uf_nascimento", "UF nascimento"),
    ("@sexonascido", "Sexo"),
    ("@possuigemeos", "Gêmeo"),
    ("@nomegemeos", "Nome do(s) gêmeo(s)"),
    ("@genitor1_nome", "Genitor 1"),
    ("@genitor1_municipio", "Município genitor 1"),
    ("@genitor1_uf", "UF genitor 1"),
    ("@genitor1_avos", "Avós genitor 1"),
    ("@genitor2_nome", "Genitor 2"),
    ("@genitor2_municipio", "Município genitor 2"),
    ("@genitor2_uf", "UF genitor 2"),
    ("@genitor2_avos", "Avós genitor 2"),
    ("@DATAREGISTROEXTENSOSN", "Data de registro"),
    ("@declaracaonascidovivo", "DNV"),
    ("@averbacoes", "Anotaçoes/Averbações"),
)

_ROTULOS_CASAM = (
    ("@nomesconjuges", "Cônjuges"),
    ("@datacelebracaoextenso", "Data da celebração"),
    ("@regimebens", "Regime de bens"),
    ("@conj1_nome", "Cônjuge 1"),
    ("@conj1_cpf", "CPF cônjuge 1"),
    ("@conj1_nomepos", "Nome após — cônjuge 1"),
    ("@conj2_nome", "Cônjuge 2"),
    ("@conj2_cpf", "CPF cônjuge 2"),
    ("@conj2_nomepos", "Nome após — cônjuge 2"),
    ("@matriculacasamento", "Matrícula"),
    ("@DATAREGISTROEXTENSOSN", "Data de registro"),
    ("@averbacoes", "Anotaçoes/Averbações"),
)

_ROTULOS_OBITO = (
    ("@nomefalecido", "Nome"),
    ("@cpffalecido", "CPF"),
    ("@matriculaobito", "Matrícula"),
    ("@dataobitoextenso", "Data do óbito"),
    ("@horaobito", "Hora"),
    ("@sexofalecido", "Sexo"),
    ("@idadefalecido", "Idade"),
    ("@datanascimentofalecido", "Data de nascimento"),
    ("@estadocivilfalecido", "Estado civil"),
    ("@conjugefalecido", "Cônjuge"),
    ("@naturalidadefalecido", "Naturalidade"),
    ("@localfalecimento", "Local do falecimento"),
    ("@municipio_falecimento", "Município do falecimento"),
    ("@uf_falecimento", "UF falecimento"),
    ("@causamorte", "Causa da morte"),
    ("@medicoobito", "Médico"),
    ("@crmobito", "CRM"),
    ("@filiacaofalecido", "Filiação"),
    ("@declarantefalecido", "Declarante"),
    ("@localsepultamento", "Sepultamento"),
    ("@municipio_sepultamento", "Município sepultamento"),
    ("@uf_sepultamento", "UF sepultamento"),
    ("@deixoubens", "Deixou bens"),
    ("@deixoufilhos", "Deixou filhos"),
    ("@profissao", "Profissão"),
    ("@cor_raca", "Cor/raça"),
    ("@domicilio", "Domicílio"),
    ("@numero_do", "Nº da DO"),
    ("@eleitor", "Título de eleitor"),
    ("@DATAREGISTROEXTENSOSN", "Data de registro"),
    ("@averbacoes", "Anotaçoes/Averbações"),
)


def _rotulos(especie: str):
    e = str(especie or "").upper()
    if e == "NASCIMENTO":
        return _ROTULOS_NASC
    if e in ("CASAMENTO", "CASAMENTO_RELIGIOSO"):
        return _ROTULOS_CASAM
    if e == "OBITO":
        return _ROTULOS_OBITO
    return _ROTULOS_NASC + _ROTULOS_CASAM + _ROTULOS_OBITO


def html_do_quadro(
    contexto: dict,
    claros: dict[str, str] | None = None,
    *,
    papel: str = "A4",
    certidao: dict | None = None,
    sv: dict | None = None,
) -> str:
    """HTML de prévia do RESUMO com os mesmos claros do ODT/quadro.

    `papel=seguranca`: fundo branco, sem brasão (quadro CNJ só).
    Sem selo, sem numeração, sem gravação.
    """
    claros = claros or claros_do_contexto(contexto, certidao, sv)
    especie = str(contexto.get("especie") or "").upper()
    titulo = str(contexto.get("titulo") or f"CERTIDÃO DE {especie}").upper()
    serv = contexto.get("serventia") if isinstance(contexto.get("serventia"), dict) else {}
    fundo = "#ffffff"
    # papel segurança: branco sem brasão (contrato aprovado)
    brasao = ""  # nunca na prévia API 2a
    linhas = []
    vistos = set()
    for chave, rotulo in _rotulos(especie):
        if chave in vistos:
            continue
        vistos.add(chave)
        valor = str(claros.get(chave) or "").strip()
        if valor in ("", " "):
            continue
        linhas.append(
            f"<tr><th>{escapar(rotulo)}</th>"
            f"<td>{escapar(valor)}</td></tr>"
        )
    # rodapé só com {{serventia.*}} — valores vindos do contexto/sv
    rodape_parts = []
    for k, rot in (
        ("nome", "Serventia"),
        ("cns", "CNS"),
        ("cidade", "Cidade"),
        ("uf", "UF"),
        ("endereco", "Endereço"),
        ("titular", "Oficial"),
    ):
        v = str(serv.get(k) or "").strip()
        if v:
            rodape_parts.append(f"<span><b>{escapar(rot)}:</b> {escapar(v)}</span>")
    rodape = " · ".join(rodape_parts)
    css = f"""
    body{{font-family: "Times New Roman", Times, serif; font-size:11pt;
         background:{fundo}; color:#000; margin:1.5cm;}}
    h1{{font-size:14pt; text-align:center; margin:0 0 .8cm;}}
    table{{width:100%; border-collapse:collapse;}}
    th,td{{border:1px solid #333; padding:4px 6px; vertical-align:top;}}
    th{{width:38%; text-align:left; background:#f7f7f7; font-weight:bold;
       font-size:8pt; text-transform:uppercase;}}
    td{{font-size:11pt;}}
    .rodape{{margin-top:1cm; font-size:9pt; border-top:1px solid #999;
             padding-top:.4cm;}}
    .aviso{{font-size:8pt; color:#555; margin-bottom:.6cm;}}
    """
    return (
        "<!doctype html><html lang=pt-BR><head><meta charset=utf-8>"
        f"<title>{escapar(titulo)}</title><style>{css}</style></head><body>"
        f"{brasao}"
        f"<p class=aviso>Prévia do motor de fidelidade — sem selo, sem "
        f"numeração, sem gravação. Papel: {escapar(papel)}.</p>"
        f"<h1>{escapar(titulo)}</h1>"
        f"<table>{''.join(linhas)}</table>"
        f"<div class=rodape>{rodape}</div>"
        "</body></html>"
    )


def odt_do_contexto(
    contexto: dict,
    *,
    certidao: dict | None = None,
    sv: dict | None = None,
    molde_bytes: bytes | None = None,
) -> bytes:
    """ODT preenchido pelo caminho existente (`rc_certidao_odt`)."""
    import rc_certidao_odt as ODT
    # injeta correções de gêmeo no quadro antes dos valores
    claros = claros_do_contexto(contexto, certidao, sv)
    # arquivo_da_certidao recalcula valores — precisamos que o quadro já
    # carregue possuigemeos/gemeo canônicos
    q = dict(contexto)
    # ODT.valores lê q["gemeo"] como truthy→SIM; forçamos string canônica
    # via patch temporário: passar quadro com gemeo = "SIM"/"NÃO" e
    # sobrescrever depois no zip seria complexo; em vez disso, usamos
    # arquivo_da_certidao e reaplicamos @possuigemeos/@nomegemeos no XML.
    odt = ODT.arquivo_da_certidao(q, certidao or {}, sv or {}, molde_bytes)
    # pós-processo: garantir SIM/NÃO na caixa gêmeo; 2b: autoria neutra no
    # meta e «das Pessoas Naturais» no rodapé — na GERAÇÃO, sem tocar no molde
    odt = limpar_autoria_odt(odt, autor_neutro(contexto, sv))
    return _reescrever_claros_odt(odt, {
        "@possuigemeos": claros.get("@possuigemeos", "NÃO"),
        "@nomegemeos": claros.get("@nomegemeos", ""),
        "@cpfnascido": claros.get("@cpfnascido", ""),
        "@cpffalecido": claros.get("@cpffalecido", ""),
        "@municipio_nascimento": claros.get("@municipio_nascimento", ""),
        "@uf_nascimento": claros.get("@uf_nascimento", ""),
    })


def autor_neutro(contexto: dict | None = None, sv: dict | None = None) -> str:
    """Nome que vai em `dc:creator`/`meta:initial-creator`. Só calcula.

    Ordem: `contexto.serventia.nome` → `sv.unit_name`/`sv.nome` → «Cartório
    Gestão». Placeholder genérico («NOME DA SERVENTIA») não serve.
    """
    candidatos = []
    serv = (contexto or {}).get("serventia")
    if isinstance(serv, dict):
        candidatos.append(serv.get("nome"))
    candidatos += [(sv or {}).get("unit_name"), (sv or {}).get("nome")]
    for c in candidatos:
        c = str(c or "").strip()
        if c.upper() not in _NOMES_PLACEHOLDER:
            return corrigir_pessoas_naturais(c)
    return AUTOR_SISTEMA


_META_PESSOAIS = re.compile(
    r"<meta:(?:keyword|printed-by)>.*?</meta:(?:keyword|printed-by)>"
    r"|<meta:(?:keyword|printed-by)\s*/>", re.DOTALL)


def _xml_texto(valor: str) -> str:
    from xml.sax.saxutils import escape
    return escape(str(valor or ""))


def limpar_meta_xml(meta: str, autor: str) -> str:
    """Reescreve o meta.xml: autor neutro, sem palavras-chave/impressor pessoais."""
    autor_x = _xml_texto(autor or AUTOR_SISTEMA)
    m = meta
    m = _META_PESSOAIS.sub("", m)
    m = re.sub(r"<dc:creator>.*?</dc:creator>|<dc:creator\s*/>",
               f"<dc:creator>{autor_x}</dc:creator>", m, flags=re.DOTALL)
    m = re.sub(r"<meta:initial-creator>.*?</meta:initial-creator>"
               r"|<meta:initial-creator\s*/>",
               f"<meta:initial-creator>{autor_x}</meta:initial-creator>", m,
               flags=re.DOTALL)
    if "<office:meta>" in m:
        faltam = ""
        if "<meta:initial-creator>" not in m:
            faltam += f"<meta:initial-creator>{autor_x}</meta:initial-creator>"
        if "<dc:creator>" not in m:
            faltam += f"<dc:creator>{autor_x}</dc:creator>"
        if faltam:
            m = m.replace("<office:meta>", "<office:meta>" + faltam, 1)
    return m


def limpar_autoria_odt(odt: bytes, autor: str = "") -> bytes:
    """ODT do motor sem autoria pessoal do molde (2b — creator ODT).

    - `meta.xml`: `dc:creator` e `meta:initial-creator` = `autor` (serventia
      ou «Cartório Gestão»); `meta:keyword`/`meta:printed-by` saem.
    - `content.xml`/`styles.xml`: `dc:creator` de anotação/alteração
      registrada também vira o autor neutro; «… Civil de Pessoas Naturais»
      → «… Civil das Pessoas Naturais» (rodapé dos moldes de certidão).
    O molde do pacote NÃO é alterado — a troca é feita na geração.
    """
    import zipfile
    from io import BytesIO

    autor = autor or AUTOR_SISTEMA
    autor_x = _xml_texto(autor)
    buf = BytesIO()
    with zipfile.ZipFile(BytesIO(odt)) as zin, zipfile.ZipFile(buf, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "meta.xml":
                data = limpar_meta_xml(data.decode("utf-8"), autor).encode("utf-8")
            elif item.filename in ("content.xml", "styles.xml"):
                texto = data.decode("utf-8")
                texto = re.sub(r"<dc:creator>.*?</dc:creator>",
                               f"<dc:creator>{autor_x}</dc:creator>", texto,
                               flags=re.DOTALL)
                texto = corrigir_pessoas_naturais(texto)
                data = texto.encode("utf-8")
            info = zipfile.ZipInfo(filename=item.filename, date_time=item.date_time)
            info.compress_type = (
                zipfile.ZIP_STORED if item.filename == "mimetype"
                else zipfile.ZIP_DEFLATED)
            zout.writestr(info, data)
    return buf.getvalue()


def autoria_do_odt(odt: bytes) -> dict[str, list[str]]:
    """Lê `dc:creator`, `meta:initial-creator` e `meta:keyword` (conferência)."""
    import zipfile
    from io import BytesIO
    with zipfile.ZipFile(BytesIO(odt)) as z:
        if "meta.xml" not in z.namelist():
            return {"dc:creator": [], "meta:initial-creator": [], "meta:keyword": []}
        meta = z.read("meta.xml").decode("utf-8")
    return {
        "dc:creator": re.findall(r"<dc:creator>(.*?)</dc:creator>", meta, re.DOTALL),
        "meta:initial-creator": re.findall(
            r"<meta:initial-creator>(.*?)</meta:initial-creator>", meta, re.DOTALL),
        "meta:keyword": re.findall(r"<meta:keyword>(.*?)</meta:keyword>", meta, re.DOTALL),
    }


def _reescrever_claros_odt(odt: bytes, extras: dict[str, str]) -> bytes:
    """Substitui claros já escapados no content.xml (pós preenchimento)."""
    import zipfile
    from io import BytesIO
    from xml.sax.saxutils import escape

    buf = BytesIO()
    with zipfile.ZipFile(BytesIO(odt)) as zin, zipfile.ZipFile(buf, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "content.xml":
                texto = data.decode("utf-8")
                # Só reaplica se o marcador ainda existir (molde sem
                # preenchimento residual). Se já foi trocado, não há @chave.
                for chave, valor in extras.items():
                    if chave in texto:
                        texto = texto.replace(chave, escape(str(valor)))
                data = texto.encode("utf-8")
            info = zipfile.ZipInfo(filename=item.filename, date_time=item.date_time)
            info.compress_type = (
                zipfile.ZIP_STORED if item.filename == "mimetype"
                else zipfile.ZIP_DEFLATED)
            zout.writestr(info, data)
    return buf.getvalue()


def pdf_de_odt_bytes(odt: bytes, *, nome: str = "previa_certidao") -> bytes:
    """Converte ODT→PDF pelo LibreOffice já usado na emissão."""
    import impressao_pdf as PDF
    return PDF.pdf_de_odt(odt, nome=nome)


def sanitizar_teor_para_papel(teor: Any) -> str:
    """F01 helper: se o teor parece HTML (inclusive escapado), vira texto
    antes do papel. 2b: delega a `html_para_texto_impressao`."""
    if parece_html(teor) or "&lt;" in str(teor or "").lower():
        return html_para_texto_impressao(teor)
    return str(teor or "")


def html_de_odt(odt: bytes, *, titulo: str = "Prévia") -> str:
    """HTML aproximado do ODT preenchido (rascunho de molde, formato=html).

    Tabelas viram `<table>`, parágrafos viram `<p>`; imagens/molduras saem.
    O fiel é `formato=pdf` (LibreOffice da emissão).
    """
    import zipfile
    from io import BytesIO
    with zipfile.ZipFile(BytesIO(odt)) as z:
        x = z.read("content.xml").decode("utf-8", errors="replace")
    ini = x.find("<office:text")
    if ini >= 0:
        x = x[ini:]
    mapa = {
        "table:table": "table", "table:table-row": "tr", "table:table-cell": "td",
        "text:p": "p", "text:h": "p",
    }

    def _tag(m: re.Match) -> str:
        fecha, nome, auto = m.group(1), m.group(2), m.group(3)
        if nome in ("text:tab", "text:s"):
            return " "
        if nome == "text:line-break":
            return "<br>"
        html_nome = mapa.get(nome)
        if not html_nome:
            return ""
        if auto:
            return f"<{html_nome}></{html_nome}>"
        return f"</{html_nome}>" if fecha else f"<{html_nome}>"

    corpo = re.sub(r"<(/?)([A-Za-z][\w:.-]*)(?:\s[^<>]*?)?(/?)>", _tag, x)
    css = ("body{font-family:'Times New Roman',Times,serif;font-size:11pt;"
           "background:#fff;color:#000;margin:1.5cm}"
           "table{width:100%;border-collapse:collapse}"
           "td{border:1px solid #999;padding:2px 4px;vertical-align:top}"
           ".aviso{font-size:8pt;color:#555;margin-bottom:.6cm}")
    return ("<!doctype html><html lang=pt-BR><head><meta charset=utf-8>"
            f"<title>{escapar(titulo)}</title><style>{css}</style></head><body>"
            "<p class=aviso>Prévia do rascunho (não salvo) — HTML aproximado do "
            "molde; o fiel é o PDF. Sem selo, sem numeração, sem gravação.</p>"
            f"{corpo}</body></html>")


def resposta_previa(
    *,
    area: str,
    template_id: str,
    dados: dict | None = None,
    contexto: dict | None = None,
    certidao: dict | None = None,
    sv: dict | None = None,
    papel: str = "A4",
    formato: str = "html",
    molde_bytes: bytes | None = None,
    conteudo: Any = None,
    corpo_termo: str | None = None,
) -> dict[str, Any]:
    """Monta a resposta do contrato POST /modelos/api/previa.

    2b: `template_id` `RC_TERMO_*` (ou `area` termo) vai para o caminho do
    termo (`modelos_motor_termo.resposta_previa_termo`) — mesmo contrato,
    mais `texto` (papel) e `correcoes`.

    2c: `conteudo` NÃO SALVO substitui o persistido, pelo mesmo pipeline:
      - molde `RC_MOLDE_*`: `conteudo` = ODT em base64 (ou bytes) → vira o
        `molde_bytes` de `rc_certidao_odt.arquivo_da_certidao` (o mesmo da
        emissão); HTML = aproximação do ODT preenchido; PDF = LibreOffice;
      - termo `RC_TERMO_*`: `conteudo` = texto do corpo (`{{campo}}`,
        `{campo}` ou `@campo`) → monta pelo catálogo como a emissão.
    Resposta: `arquivo_base64` (+ alias `pdf_base64`) e `mime` corretos.
    """
    if eh_template_termo(template_id, area) and (
            contexto is None or str((contexto.get("_meta") or {}).get("fonte", ""))
            .endswith("/termo")):
        import modelos_motor_termo as TERMO
        return TERMO.resposta_previa_termo(
            area=area, template_id=template_id, dados=dados, contexto=contexto,
            sv=sv, papel=papel, formato=formato, conteudo=conteudo,
            corpo=corpo_termo)
    from modelos_motor_placeholders import (
        analisar_placeholders, conferir_bloqueados, conteudo_de_partes,
        odt_do_conteudo, texto_do_odt)
    avisos: list[str] = []
    erros: list[dict] = []
    placeholders_usados: list[str] = []
    placeholders_desconhecidos: list[str] = []
    extras: dict[str, Any] = {}

    papel_n = str(papel or "A4").strip().lower()
    if papel_n in ("seguranca", "segurança", "folha_seguranca"):
        papel_n = "seguranca"
    else:
        papel_n = "A4"

    formato_n = str(formato or "html").strip().lower()
    if formato_n not in ("html", "pdf", "odt"):
        erros.append({
            "linha": 0, "coluna": 0, "codigo": "FORMATO_INVALIDO",
            "msg": f"formato deve ser html|pdf|odt, veio {formato!r}",
        })
        return _pacote(erros=erros)

    if contexto is None:
        contexto = contexto_de_exemplo(
            dados or {}, area=area, template_id=template_id, sv=sv)

    rascunho = conteudo_de_partes(conteudo, parte="MOLDE")
    if rascunho:
        chave_molde = str(template_id or contexto.get("template_id") or "").upper()
        try:
            molde_bytes = odt_do_conteudo(rascunho)
        except ValueError as exc:
            erros.append({"linha": 0, "coluna": 0, "codigo": "CONTEUDO_INVALIDO",
                          "msg": f"{exc}. Para RC_MOLDE_* envie o .odt em base64."})
            return _pacote(erros=erros, avisos=avisos)
        avisos.append("conteudo não salvo: prévia do rascunho do molde (nada "
                      "foi gravado; o molde vigente continua valendo).")
        try:
            import modelos_moldes as MOLDES
            msg = MOLDES.conferir(chave_molde, molde_bytes) if chave_molde else None
        except Exception:  # noqa: BLE001 — conferência é aviso, não trava a prévia
            msg = None
        if msg:
            erros.append({"linha": 0, "coluna": 0, "codigo": "MOLDE_RECUSADO",
                          "msg": msg})
        texto_molde = texto_do_odt(molde_bytes)
        analise = analisar_placeholders(texto_molde, area=area,
                                        template_id=chave_molde)
        placeholders_usados = analise["placeholders_usados"]
        placeholders_desconhecidos = analise["placeholders_desconhecidos"]
        extras["conversoes"] = analise["conversoes"]
        e_blk, _a, ids = conferir_bloqueados(area, chave_molde, texto_molde)
        erros += e_blk
        extras["bloqueados_presentes"] = ids
        extras["fonte_conteudo"] = "rascunho"

    claros = claros_do_contexto(contexto, certidao, sv)
    if not rascunho:
        placeholders_usados = sorted(
            k for k, v in claros.items()
            if k.startswith("@") and str(v or "").strip() not in ("", " ")
        )

    if formato_n == "html" and not rascunho:
        html = html_do_quadro(
            contexto, claros, papel=papel_n, certidao=certidao, sv=sv)
        if papel_n == "seguranca":
            avisos.append(
                "Papel segurança: quadro em fundo branco, sem brasão.")
        return _pacote(
            html=html, paginas=1, avisos=avisos, erros=erros,
            placeholders_usados=placeholders_usados,
            placeholders_desconhecidos=placeholders_desconhecidos, **extras,
        )

    # ODT / PDF (e HTML do rascunho de molde)
    try:
        odt = odt_do_contexto(
            contexto, certidao=certidao, sv=sv, molde_bytes=molde_bytes)
    except Exception as exc:  # noqa: BLE001 — devolve erro no contrato
        erros.append({
            "linha": 0, "coluna": 0, "codigo": "ODT_FALHOU",
            "msg": str(exc),
        })
        # fallback HTML se molde ausente
        html = html_do_quadro(
            contexto, claros, papel=papel_n, certidao=certidao, sv=sv)
        avisos.append("ODT indisponível; devolvendo HTML de prévia.")
        return _pacote(
            html=html, paginas=1, avisos=avisos, erros=erros,
            placeholders_usados=placeholders_usados,
            placeholders_desconhecidos=placeholders_desconhecidos, **extras,
        )

    if formato_n == "html":
        return _pacote(
            html=html_de_odt(odt, titulo=str(contexto.get("titulo") or "Prévia")),
            paginas=1, avisos=avisos + ["HTML do rascunho é aproximado; o fiel "
                                        "é formato=pdf."],
            erros=erros, placeholders_usados=placeholders_usados,
            placeholders_desconhecidos=placeholders_desconhecidos, **extras)

    if formato_n == "odt":
        return _pacote(
            arquivo_base64=base64.b64encode(odt).decode("ascii"),
            paginas=1, avisos=avisos + ["formato=odt: bytes em arquivo_base64 "
                                        "(alias pdf_base64)."],
            erros=erros,
            placeholders_usados=placeholders_usados,
            placeholders_desconhecidos=placeholders_desconhecidos,
            mime=MIME_ODT, **extras,
        )

    try:
        pdf = pdf_de_odt_bytes(odt)
        return _pacote(
            arquivo_base64=base64.b64encode(pdf).decode("ascii"),
            paginas=1, avisos=avisos, erros=erros,
            placeholders_usados=placeholders_usados,
            placeholders_desconhecidos=placeholders_desconhecidos,
            mime=MIME_PDF, **extras,
        )
    except Exception as exc:  # noqa: BLE001
        erros.append({
            "linha": 0, "coluna": 0, "codigo": "PDF_FALHOU",
            "msg": str(exc),
        })
        return _pacote(
            arquivo_base64=base64.b64encode(odt).decode("ascii"),
            paginas=1,
            avisos=avisos + ["PDF falhou; devolvendo ODT em arquivo_base64."],
            erros=erros,
            placeholders_usados=placeholders_usados,
            placeholders_desconhecidos=placeholders_desconhecidos,
            mime=MIME_ODT, **extras,
        )


MIME_ODT = "application/vnd.oasis.opendocument.text"
MIME_PDF = "application/pdf"
MIME_HTML = "text/html; charset=utf-8"


def _pacote(**kwargs) -> dict[str, Any]:
    """Corpo do contrato. 2c: `arquivo_base64` é o campo do arquivo (PDF ou
    ODT, conforme `mime`); `pdf_base64` continua como alias (compatível com
    2a/2b e com o editor)."""
    base = {
        "html": None,
        "arquivo_base64": None,
        "pdf_base64": None,
        "mime": None,
        "paginas": None,
        "avisos": [],
        "erros": [],
        "placeholders_usados": [],
        "placeholders_desconhecidos": [],
    }
    base.update(kwargs)
    arq = base.get("arquivo_base64") or base.get("pdf_base64")
    base["arquivo_base64"] = arq
    base["pdf_base64"] = arq
    if not base.get("mime"):
        if arq:
            base["mime"] = MIME_PDF
        elif base.get("html"):
            base["mime"] = MIME_HTML
    return base
