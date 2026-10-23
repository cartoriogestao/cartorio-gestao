"""Leitor de remessa XML da CRA21, sem qualquer escrita ou chamada de rede.

O retorno real de RemessaPendente (23/09/2026) usa hd/tr/tl e atributos do
layout FEBRABAN. O leitor legado, protesto_arquivo, espera linhas TXT de 600
posições. Esta ponte confere o XML ORIGINAL antes de projetar seus campos em
memória para o conferidor de títulos existente. Não é uma porta de importação.
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from xml.sax.saxutils import quoteattr

import protesto_arquivo as PA
import protesto_cra_imagens as PCIMG


LIMITE_BYTES = PCIMG.LIMITE_XML

# FEBRABAN: Layout de Transmissão de Arquivo de Protesto, remessa XML,
# campos h01..h17, t01..t52 e trailer t01..t08. Cada grupo soma 600 posições.
LARGURAS = {
    "hd": (1, 3, 40, 8, 3, 3, 3, 6, 4, 4, 4, 4, 6, 3, 7, 497, 4),
    "tr": (1, 3, 15, 45, 45, 14, 45, 8, 20, 2, 15, 3, 11, 8, 8, 3,
           14, 14, 20, 1, 1, 1, 45, 3, 14, 11, 45, 8, 20, 2, 2, 10,
           1, 8, 10, 1, 8, 2, 20, 10, 6, 10, 5, 15, 3, 1, 8, 1, 1,
           10, 19, 4),
    "tl": (1, 3, 40, 8, 5, 18, 521, 4),
}
assert all(sum(campos) == 600 for campos in LARGURAS.values())


class RemessaXmlError(ValueError):
    """Resposta da CRA fora do layout medido, pronta para explicar na tela."""


@dataclass(frozen=True)
class PreviaXml:
    nome_arquivo: str
    lotes: int
    titulos: int
    sha256: str
    conteudo_fixo: str  # somente em memória; nunca enviar à rota de receber
    trailer_xml: tuple[int, ...]
    hashes_lotes: tuple[str, ...]  # identidade do título, independente das imagens
    imagens: tuple[dict, ...] = ()


def chave_idempotencia(ambiente: str, hash_lote: str) -> str:
    """Identidade futura de um lote XML, separada por ambiente CRA.

    Não grava sozinha. A chave e persistida com UNIQUE na mesma transacao do
    lote em `protesto_remessa.receber_xml`.
    """
    ambiente = ambiente.upper().strip()
    if ambiente not in ("HOMOLOGACAO", "PRODUCAO"):
        raise RemessaXmlError("Ambiente CRA inválido para identificar o lote.")
    if len(hash_lote) != 64 or any(c not in "0123456789abcdef" for c in hash_lote):
        raise RemessaXmlError("Hash do lote XML inválido.")
    return hashlib.sha256(f"CRA21-XML:{ambiente}:{hash_lote}".encode()).hexdigest()


def _hash_lote(lote: list[ET.Element]) -> str:
    # Ordem dos atributos no XML e indentação não mudam o conteúdo. Valores
    # originais Unicode e espaços dos campos são preservados.
    campos = []
    for e in lote:
        atributos = dict(e.attrib)
        if e.tag == "tr" and "t51" in atributos:
            atributos["t51"] = ""  # imagem/indicador não altera a identidade do lote
        campos.append((e.tag, sorted(atributos.items())))
    canonico = json.dumps(campos, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def parece_xml(conteudo: str | bytes) -> bool:
    inicio = conteudo[:200]
    if isinstance(inicio, bytes):
        inicio = inicio.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
        return inicio.startswith((b"<?xml", b"<remessa"))
    inicio = inicio.lstrip("\ufeff \t\r\n").lower()
    return inicio.startswith(("<?xml", "<remessa"))


def _texto(conteudo: str | bytes) -> str:
    if isinstance(conteudo, bytes):
        if len(conteudo) > LIMITE_BYTES:
            raise RemessaXmlError("O XML excede 64 MB; use o fluxo de arquivos grandes.")
        try:
            return conteudo.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                return conteudo.decode("iso-8859-1")
            except UnicodeDecodeError as erro:
                raise RemessaXmlError("Não consegui ler a codificação do XML.") from erro
    if len(conteudo.encode("utf-8")) > LIMITE_BYTES:
        raise RemessaXmlError("O XML excede 64 MB; use o fluxo de arquivos grandes.")
    return conteudo.lstrip("\ufeff")


def _inteiro(elemento: ET.Element, atributo: str) -> int:
    valor = elemento.get(atributo, "")
    if not valor or not valor.isascii() or not valor.isdigit():
        raise RemessaXmlError(f"{elemento.tag}.{atributo} deve conter só dígitos.")
    return int(valor)


def _data(elemento: ET.Element, atributo: str) -> None:
    valor = elemento.get(atributo, "")
    try:
        datetime.strptime(valor, "%d%m%Y")
    except ValueError as erro:
        raise RemessaXmlError(f"{elemento.tag}.{atributo} não é data DDMMAAAA válida.") from erro


def _linha(elemento: ET.Element) -> str:
    prefixo = "h" if elemento.tag == "hd" else "t"
    partes = []
    esperados = {f"{prefixo}{i:02}" for i in range(1, len(LARGURAS[elemento.tag]) + 1)}
    extras = set(elemento.attrib) - esperados
    if extras:
        raise RemessaXmlError(
            f"{elemento.tag} trouxe atributo fora do layout: {', '.join(sorted(extras))}.")
    for i, largura in enumerate(LARGURAS[elemento.tag], 1):
        nome = f"{prefixo}{i:02}"
        valor = elemento.get(nome, "")
        if elemento.tag == "tr" and nome == "t51":
            valor = ""  # ZIP fica em separado, nunca na projeção de 600 posições
        if len(valor) > largura:
            raise RemessaXmlError(
                f"{elemento.tag}.{nome} tem {len(valor)} caracteres; o máximo é {largura}.")
        partes.append(valor.ljust(largura))
    return "".join(partes)


def _filhos(raiz: ET.Element) -> list[ET.Element]:
    todos = []
    for filho in raiz:
        if filho.tag == "nome_arquivo":
            continue
        if filho.tag == "comarca":
            if set(filho.attrib) - {"CodMun"}:
                raise RemessaXmlError("Comarca trouxe atributo desconhecido.")
            todos.extend(filho)
        else:
            todos.append(filho)
    return todos


def ler(conteudo: str | bytes) -> PreviaXml:
    """Confere XML e gera linhas temporárias de 600 posições para prévia.

    A CRA escapou os delimitadores de atributos como ``&quot;`` no retorno
    medido. Desfazemos SOMENTE esse escape, preservando ``&amp;`` dentro
    dos valores para o parser XML fazer a decodificação correta. DTD e
    entidades customizadas são recusados antes do parser.
    """
    texto = _texto(conteudo)
    if not parece_xml(texto):
        raise RemessaXmlError("O arquivo não começa como remessa XML da CRA.")
    if "<!DOCTYPE" in texto.upper() or "<!ENTITY" in texto.upper():
        raise RemessaXmlError("XML com DTD ou entidade customizada não é aceito.")
    if "&quot;" in texto[:120]:
        texto = texto.replace("&quot;", '"')
    try:
        raiz = ET.fromstring(texto)
    except ET.ParseError as erro:
        raise RemessaXmlError(f"XML da remessa não abre: {erro}.") from erro
    if raiz.tag in ("relatorio", "erro"):
        codigo = (raiz.findtext("codigo") or "").strip()
        mensagem = (raiz.findtext("ocorrencia") or raiz.findtext("mensagem") or "").strip()
        detalhe = f" (código {codigo})" if codigo else ""
        raise RemessaXmlError(
            f"A CRA informou: {mensagem or 'relatório sem títulos'}{detalhe}. "
            "Esta resposta não contém remessas para receber.")
    if raiz.tag != "remessa":
        raise RemessaXmlError(
            f"O XML recebido tem raiz <{str(raiz.tag)[:100]}>; "
            "era esperada uma remessa da CRA (<remessa>).")
    if raiz.attrib:
        raise RemessaXmlError(
            "A remessa trouxe atributos não previstos na raiz: "
            + ", ".join(sorted(raiz.attrib)) + ".")
    nome = (raiz.findtext("nome_arquivo") or "").strip()
    if len(nome) > 100:
        raise RemessaXmlError("Nome do arquivo excessivamente longo.")

    lotes: list[list[ET.Element]] = []
    atual: list[ET.Element] = []
    for filho in _filhos(raiz):
        if filho.tag == "hd":
            if atual:
                raise RemessaXmlError("Novo cabeçalho antes de fechar o lote anterior.")
            atual = [filho]
        elif filho.tag == "tr":
            if not atual:
                raise RemessaXmlError("Título sem cabeçalho de lote.")
            atual.append(filho)
        elif filho.tag == "tl":
            if not atual:
                raise RemessaXmlError("Trailer sem cabeçalho de lote.")
            atual.append(filho)
            lotes.append(atual)
            atual = []
        else:
            raise RemessaXmlError(f"Elemento inesperado na remessa: {filho.tag}.")
    if atual or not lotes:
        raise RemessaXmlError("A remessa não tem lote completo (hd, tr, tl).")

    linhas = []
    saldos_trailer = []
    hashes_lotes = []
    imagens = []
    total_imagens = 0
    for numero, lote in enumerate(lotes, 1):
        hd, *titulos, tl = lote
        if not titulos:
            raise RemessaXmlError(f"Lote {numero} sem título.")
        if (hd.get("h01") != "0" or tl.get("t01") != "9" or
                (hd.get("h05"), hd.get("h06"), hd.get("h07")) != ("BFO", "SDT", "TPR")):
            raise RemessaXmlError(f"Lote {numero} não é remessa BFO/SDT/TPR.")
        if hd.get("h02") != tl.get("t02"):
            raise RemessaXmlError(f"Lote {numero}: apresentante difere no trailer.")
        _data(hd, "h04")
        if hd.get("h04") != tl.get("t04"):
            raise RemessaXmlError(f"Lote {numero}: data difere no trailer.")
        if _inteiro(hd, "h10") != len(titulos):
            raise RemessaXmlError(f"Lote {numero}: h10 difere da quantidade de títulos.")
        if _inteiro(hd, "h11") + _inteiro(hd, "h12") != len(titulos):
            raise RemessaXmlError(f"Lote {numero}: indicações mais originais não fecham.")
        seguranca = sum(_inteiro(hd, f"h{i:02}") for i in range(9, 13))
        if _inteiro(tl, "t05") != seguranca:
            raise RemessaXmlError(f"Lote {numero}: somatório de segurança do trailer não fecha.")
        saldos = 0
        for sequencial, titulo in enumerate(titulos, 1):
            try:
                arquivos = PCIMG.ler_zip(titulo.get("t51", ""))
            except PCIMG.ImagemCraError as erro:
                raise RemessaXmlError(f"Lote {numero}, título {sequencial}: {erro}") from erro
            if arquivos:
                total_imagens += sum(len(a["conteudo"]) for a in arquivos)
                if total_imagens > PCIMG.LIMITE_TOTAL:
                    raise RemessaXmlError("As imagens da remessa excedem 100 MB descompactados.")
                imagens.append({"lote": numero, "sequencial": sequencial, "arquivos": arquivos})
            if titulo.get("t01") != "1" or titulo.get("t02") != hd.get("h02"):
                raise RemessaXmlError(f"Lote {numero}: título de outro apresentante.")
            _data(titulo, "t14")
            if titulo.get("t15") not in ("99999999", "00000000"):
                _data(titulo, "t15")
            _inteiro(titulo, "t17")
            saldos += _inteiro(titulo, "t18")
        if _inteiro(tl, "t06") != saldos:
            raise RemessaXmlError(f"Lote {numero}: saldo do trailer não fecha.")
        sequenciais = [
            _inteiro(hd, "h17"),
            *(_inteiro(titulo, "t52") for titulo in titulos),
            _inteiro(tl, "t08"),
        ]
        if sequenciais != list(range(sequenciais[0], sequenciais[0] + len(lote))):
            raise RemessaXmlError(f"Lote {numero}: sequência dos registros não fecha.")
        linhas.extend(_linha(elemento) for elemento in lote)
        saldos_trailer.append(saldos)
        hash_lote = _hash_lote(lote)
        if hash_lote in hashes_lotes:
            raise RemessaXmlError(
                f"Lote {numero} repete outro lote idêntico neste XML.")
        hashes_lotes.append(hash_lote)
        # A projeção serve para aproveitar o leitor dos campos legados. A
        # validação AUTORITATIVA de contagem/soma acima é a do XML; o leitor
        # TXT chama t05 de quantidade de linhas e daria falso alarme.
        if len(PA.ler("\n".join(_linha(e) for e in lote)).titulos) != len(titulos):
            raise RemessaXmlError(f"Lote {numero}: leitor de campos perdeu título.")

    bruto = conteudo if isinstance(conteudo, bytes) else conteudo.encode("utf-8")
    return PreviaXml(
        nome_arquivo=nome,
        lotes=len(lotes),
        titulos=sum(len(lote) - 2 for lote in lotes),
        sha256=hashlib.sha256(bruto).hexdigest(),
        conteudo_fixo="\n".join(linhas),
        trailer_xml=tuple(saldos_trailer),
        hashes_lotes=tuple(hashes_lotes),
        imagens=tuple(imagens),
    )


# ------------------------------------------------------------ o que SAI em XML
#
# A CRA RECEBE A CONFIRMAÇÃO EM XML, E NÃO O TEXTO DE 600 POSIÇÕES — medido na
# homologação em 11/10/2026: o texto em `userDados` volta «10000 — 1.5 ARQUIVO
# XML CORROMPIDO»; o mesmo arquivo em XML voltou «0000 — 10 títulos» em
# 13/10/2026 (`C2371609.263`). O formato é o do exemplo oficial da P21
# (`EXEMPLO_CONFIRMACAO_RETORNO`, repositório público manual-cra-21): raiz
# `<confirmacao>` ou `<retorno>`, os mesmos `hd`/`tr`/`tl` da remessa e os
# valores SEM o preenchimento de espaços (numéricos ficam com os zeros).
#
# O ANDAMENTO NÃO TEM RAIZ AQUI, de propósito: ele não é o arquivo de 600
# posições em XML. Pela `Retorno` (raiz `<andamento>` e `<retorno>`) a CRA
# devolveu resposta vazia e não o registrou; o caminho é a `TituloComplemento`,
# com o XML `<complementos>` do manual da P21, montado por
# `protesto_cra_envio.montar_complemento` — aceito com «2322» em 13/10/2026.
# Ver DOCUMENTACAO/CRA_HOMOLOGACAO_TESTE_2026-10-13.md.
RAIZ_DE_SAIDA = {"SDTBFOCRT": "confirmacao", "SDTBFORTP": "retorno"}
_TAG_DO_REGISTRO = {"0": ("hd", "h"), "1": ("tr", "t"), "9": ("tl", "t")}


def escrever_xml(texto: str, tipo: str) -> str:
    """O arquivo de 600 posições, no XML que a CRA21 recebe. Só calcula."""
    raiz = RAIZ_DE_SAIDA.get(str(tipo or "").strip())
    if not raiz:
        raise RemessaXmlError(
            f"O arquivo do tipo «{tipo}» não tem formato XML medido para envio "
            f"à CRA. O andamento vai pela TituloComplemento, em XML próprio "
            f"(protesto_cra_envio.montar_complemento).")
    saida = ['<?xml version="1.0" encoding="ISO-8859-1"?>', f"<{raiz}>"]
    for numero, linha in enumerate(
            (x for x in str(texto or "").replace("\r", "").split("\n") if x.strip()),
            start=1):
        if len(linha) != 600 or linha[:1] not in _TAG_DO_REGISTRO:
            raise RemessaXmlError(
                f"A linha {numero} do arquivo não é um registro de 600 posições "
                f"(tem {len(linha)}) — gere o arquivo de novo antes de enviar.")
        tag, letra = _TAG_DO_REGISTRO[linha[:1]]
        pos, campos = 0, []
        for i, largura in enumerate(LARGURAS[tag], start=1):
            campos.append(f"{letra}{i:02d}={quoteattr(linha[pos:pos + largura].strip())}")
            pos += largura
        saida.append(f"<{tag} " + " ".join(campos) + "/>")
    saida.append(f"</{raiz}>")
    return "\n".join(saida)
