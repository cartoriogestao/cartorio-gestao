"""O ODT da folha do livro do RCPN sai COM as três colunas e COM a pauta.

Pedido de 03/11/2026: o «Baixar ODT» da folha (`/rcpn/<id>/folha/papel?
formato=odt`) saía como texto corrido — sem a tabela de três colunas e sem as
linhas da coluna de notas. A folha HTML impressa tinha as duas coisas.

O que estes testes guardam, nas três espécies (nascimento, casamento, óbito):
    • a frente e o verso têm, cada um, a tabela de TRÊS colunas, com os títulos
      e as larguras de `rc_folha.COLUNAS`;
    • a 3ª coluna é PAUTADA (um fio cinza a cada 5 mm, linha por linha) e as notas são
      escritas nela, no passo da pauta;
    • o termo, o carimbo do selo e as linhas de assinatura ficam na coluna do
      termo; o número de ordem, sozinho, na primeira;
    • a página é carta em retrato e o texto continua editável;
    • convertido pelo LibreOffice, sai em DUAS páginas (frente e verso), e a
      frente leva as assinaturas.

Dados FICTÍCIOS.
"""
from __future__ import annotations

import io
import os
import shutil
import struct
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

import rc_folha as FOLHA
import rc_folha_odt as FOLHA_ODT
from test_folha_nascimento_selo_e_assinaturas import _escrevente, _registro
from test_folha_obito_1pagina_20261103 import _obito_longo
from test_rc_folha_tela import (  # noqa: F401
    casa, _con, _nascimento, _obito, _casamento,
)

N = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
    "xlink": "http://www.w3.org/1999/xlink",
}
ESPECIES = {
    "NASCIMENTO": (_nascimento, "MARIA ENSAIO NASCIMENTO", "8687"),
    "CASAMENTO": (_casamento, "JOAO ENSAIO CASAMENTO", "40"),
    "OBITO": (_obito, "ANTONIO ENSAIO OBITO", "244"),
}


def _q(prefixo: str, nome: str) -> str:
    return "{%s}%s" % (N[prefixo], nome)


def _texto(el) -> str:
    """O texto do elemento; parágrafos separados por espaço."""
    pars = list(el.iter(_q("text", "p"))) or [el]
    return " ".join(" ".join("".join(p.itertext()).split()) for p in pars).strip()


def _baixar(casa, aid) -> zipfile.ZipFile:
    r = casa["cliente"].get(f"/rcpn/{aid}/folha/papel?formato=odt")
    assert r.status_code == 200
    assert r.mimetype == "application/vnd.oasis.opendocument.text"
    return zipfile.ZipFile(io.BytesIO(r.data))


def _estilos_de_celula(raiz) -> dict:
    estilos = {}
    for st in raiz.iter(_q("style", "style")):
        if st.get(_q("style", "family")) == "table-cell":
            estilos[st.get(_q("style", "name"))] = st
    return estilos


def _tabelas_de_colunas(raiz) -> list:
    return [t for t in raiz.iter(_q("table", "table"))
            if (t.get(_q("table", "name")) or "").startswith("FolhaColunas")]


def _celulas_do_corpo(tabela) -> list:
    corpo = [r for r in tabela.findall(_q("table", "table-row"))]
    assert len(corpo) == 1, "a tabela das colunas tem uma linha de corpo"
    return corpo[0].findall(_q("table", "table-cell"))


@pytest.mark.parametrize("especie", sorted(ESPECIES))
def test_frente_e_verso_tem_as_tres_colunas_e_a_pauta(casa, especie):
    montar, nome, numero = ESPECIES[especie]
    _escrevente(casa)
    aid = montar(casa)
    _registro(casa, aid, criado_por="Elisa Ficticia de Teste")
    z = _baixar(casa, aid)
    raiz = ET.fromstring(z.read("content.xml"))

    tabelas = _tabelas_de_colunas(raiz)
    assert len(tabelas) == 2, "frente e verso, cada um com as três colunas"
    estilos = _estilos_de_celula(raiz)
    for tabela in tabelas:
        colunas = tabela.findall(_q("table", "table-column"))
        assert len(colunas) == 3
        cab = tabela.find(_q("table", "table-header-rows"))
        assert cab is not None, "os títulos repetem como cabeçalho da tabela"
        titulos = [_texto(c) for c in cab.iter(_q("table", "table-cell"))]
        assert titulos == [c["titulo"] for c in FOLHA.COLUNAS]
        num, termo, notas = _celulas_do_corpo(tabela)
        # A 3ª coluna é pautada: uma linha da pauta por parágrafo, com o fio
        # cinza embaixo, da altura toda da coluna.
        linhas = notas.findall(_q("text", "p"))
        assert len(linhas) >= FOLHA_ODT.PAUTA_LINHAS, "coluna de notas sem pauta"
        assert {p.get(_q("text", "style-name")) for p in linhas} == {"FL-nota"}
        # A 1ª e a 2ª colunas são lisas.
        for lisa in (num, termo):
            assert all(p.get(_q("text", "style-name")) != "FL-nota"
                       for p in lisa.iter(_q("text", "p")))
    nota = [st for st in raiz.iter(_q("style", "style"))
            if st.get(_q("style", "name")) == "FL-nota"][0]
    props = nota.find(_q("style", "paragraph-properties"))
    assert "solid" in props.get(_q("fo", "border-bottom"))
    assert props.get(_q("style", "join-border")) == "false"
    # entrelinha + fio = o passo da pauta da folha HTML (5 mm)
    passo = (float(props.get(_q("fo", "line-height")).rstrip("cm"))
             + FOLHA_ODT.FIO_DA_PAUTA_PT * 2.54 / 72)
    assert abs(passo - FOLHA.PAUTA_PASSO_MM / 10) < 0.001

    frente, verso = tabelas
    num, termo, _notas = _celulas_do_corpo(frente)
    assert _texto(num) == numero, "a 1ª coluna leva o número de ordem"
    assert nome in _texto(termo), "o termo fica na coluna do meio"
    assert nome not in _texto(num), "a 1ª coluna leva só o número"
    assert "_" * 45 in _texto(termo), "as linhas de assinatura ficam no termo"
    assert "Elisa Ficticia de Teste, Escrevente Autorizada" in _texto(termo)
    vnum, vtermo, vnotas = _celulas_do_corpo(verso)
    assert _texto(vnum) == _texto(vtermo) == _texto(vnotas) == ""

    paragrafos = [_texto(p) for p in raiz.iter(_q("text", "p"))]
    assert "Frente" in paragrafos and "Verso" in paragrafos
    # O verso começa em página nova.
    assert 'fo:break-before="page"' in z.read("content.xml").decode("utf-8")

    # Carta em retrato.
    estilos_xml = z.read("styles.xml").decode("utf-8")
    assert 'fo:page-width="21.5cm"' in estilos_xml
    assert 'fo:page-height="27.9cm"' in estilos_xml


def test_as_larguras_sao_as_da_folha_html(casa):
    aid = _nascimento(casa)
    raiz = ET.fromstring(_baixar(casa, aid).read("content.xml"))
    larguras = {}
    for st in raiz.iter(_q("style", "style")):
        if st.get(_q("style", "family")) == "table-column":
            props = st.find(_q("style", "table-column-properties"))
            larguras[st.get(_q("style", "name"))] = float(
                props.get(_q("style", "column-width")).rstrip("cm"))
    frente = _tabelas_de_colunas(raiz)[0]
    cols = [larguras[c.get(_q("table", "style-name"))]
            for c in frente.findall(_q("table", "table-column"))]
    total = sum(cols)
    assert abs(total - FOLHA_ODT.LARGURA_UTIL_CM) < 0.01
    for medida, c in zip(cols, FOLHA.COLUNAS):
        assert abs(medida / total - c["largura"]) < 0.002


def test_a_pauta_cobre_a_coluna_e_a_nota_cai_nas_linhas():
    assert FOLHA_ODT.PAUTA_LINHAS >= FOLHA.PAUTA_LINHAS
    linhas = FOLHA_ODT.linhas_da_nota(
        "Averbacao de 2026-11-01: texto ficticio de teste " * 4
        + "https://selo.exemplo.invalid/" + "X" * 80)
    assert len(linhas) > 4
    assert all(FOLHA_ODT._peso(ln) <= FOLHA_ODT.LETRAS_POR_LINHA_DA_NOTA
               for ln in linhas)


def test_as_notas_vao_na_coluna_pautada(casa):
    aid = _nascimento(casa)
    con = _con(casa)
    with con:
        con.execute(
            "INSERT INTO rc_atos (assento_id, tipo, teor, data_ato, criado_em)"
            " VALUES (?, 'AVERBACAO', ?, '2026-11-01', '2026-11-01T10:00')",
            (aid, "Averbacao ficticia de teste."))
    raiz = ET.fromstring(_baixar(casa, aid).read("content.xml"))
    num, termo, notas = _celulas_do_corpo(_tabelas_de_colunas(raiz)[0])
    assert "Averbacao ficticia de teste." in _texto(notas)
    assert "Averbacao ficticia" not in _texto(termo)
    linhas = [_texto(p) for p in notas.findall(_q("text", "p"))]
    # a nota vem primeiro, e a pauta continua depois dela até embaixo
    assert linhas[0].startswith("Averbacao de 2026-11-01")
    assert len(linhas) == FOLHA_ODT.PAUTA_LINHAS
    assert linhas[-1] == ""


def test_o_carimbo_do_selo_cabe_na_coluna_do_termo(casa):
    aid = _obito_longo(casa, 1617)
    raiz = ET.fromstring(_baixar(casa, aid).read("content.xml"))
    _num, termo, _notas = _celulas_do_corpo(_tabelas_de_colunas(raiz)[0])
    carimbo = [t for t in termo.iter(_q("table", "table"))
               if t.get(_q("table", "name")) == "CarimboDoSelo"]
    assert carimbo, "o carimbo do selo fica embaixo do termo, na coluna do termo"
    assert carimbo[0].get(_q("table", "style-name")) == "FL-tab-selo"
    assert "REGOBT000000YAGQMNVGI8T80C30" in _texto(termo)


def test_o_termo_longo_aperta_como_na_folha_html():
    curto = FOLHA_ODT.aperto_do_termo("x " * 500, "OBITO", True)
    assert (curto["letra_pt"], curto["longo"]) == (10.5, False)
    obito = FOLHA_ODT.aperto_do_termo("x" * 1617, "OBITO", True)
    nasc = FOLHA_ODT.aperto_do_termo("x" * 1617, "NASCIMENTO", True)
    assert obito["longo"] and obito["letra_pt"] == 9.5
    assert not nasc["longo"] and nasc["letra_pt"] == 10.5
    muito = FOLHA_ODT.aperto_do_termo("x" * 2400, "CASAMENTO", True)
    assert (muito["letra_pt"], muito["entrelinha"]) == (8.5, 115)


# ------------------------------------------- a prova no papel (LibreOffice)

def _pdf_do_odt(tmp_path, odt: bytes) -> bytes:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        pytest.skip("sem LibreOffice nesta máquina")
    entrada = tmp_path / "folha.odt"
    entrada.write_bytes(odt)
    subprocess.run(
        [soffice, f"-env:UserInstallation=file://{tmp_path}/perfil",
         "--headless", "--convert-to", "pdf", "--outdir", str(tmp_path),
         str(entrada)], check=True, capture_output=True, timeout=180)
    return (tmp_path / "folha.pdf").read_bytes()


@pytest.mark.lento
@pytest.mark.parametrize("especie", sorted(ESPECIES) + ["OBITO_LONGO"])
def test_no_papel_sao_duas_paginas_com_a_frente_inteira(casa, tmp_path, especie):
    fitz = pytest.importorskip("pymupdf")
    if especie == "OBITO_LONGO":
        aid = _obito_longo(casa, 1960)
        assinantes = ("Declarante", "Escrevente Ficticia")
    else:
        _escrevente(casa)
        aid = ESPECIES[especie][0](casa)
        _registro(casa, aid, criado_por="Elisa Ficticia de Teste")
        assinantes = ("Elisa Ficticia de Teste",)
        con = _con(casa)
        with con:
            con.execute(
                "INSERT INTO rc_atos (assento_id, tipo, teor, data_ato, criado_em)"
                " VALUES (?, 'ANOTACAO', ?, '2026-11-01', '2026-11-01T10:00')",
                (aid, "Anotacao ficticia de teste, escrita na pauta da coluna "
                      "de notas, linha a linha."))
    r = casa["cliente"].get(f"/rcpn/{aid}/folha/papel?formato=odt")
    pdf = _pdf_do_odt(tmp_path, r.data)
    destino = os.environ.get("FOLHA_ODT_SAIDA")
    if destino:  # para olhar a folha: grava o ODT e o PDF
        Path(destino).mkdir(parents=True, exist_ok=True)
        (Path(destino) / f"{especie.lower()}.odt").write_bytes(r.data)
        (Path(destino) / f"{especie.lower()}.pdf").write_bytes(pdf)
    doc = fitz.open(stream=pdf, filetype="pdf")
    paginas = [" ".join(p.get_text().split()) for p in doc]
    assert len(paginas) == 2, f"esperava frente + verso, veio {len(paginas)}"
    frente, verso = paginas
    for trecho in assinantes + ("Frente", "Notas, Averbações e Retificações"):
        assert trecho in frente, f"{trecho!r} não ficou na frente"
    assert "Verso" in verso and "Notas, Averbações e Retificações" in verso
    for trecho in assinantes:
        assert trecho not in verso
    # A pauta foi desenhada nas duas páginas: os fios da 3ª coluna.
    for pagina in doc:
        x_notas = pagina.rect.width * (1 - FOLHA.COLUNAS[2]["largura"]) * 0.95
        fios = {round(d["rect"].y1) for d in pagina.get_drawings()
                if d["rect"].x0 >= x_notas and d["rect"].height < 2}
        assert len(fios) >= FOLHA_ODT.PAUTA_LINHAS - 1, "página sem pauta"
