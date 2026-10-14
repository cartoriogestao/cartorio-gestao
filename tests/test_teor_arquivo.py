"""Levar o teor para o LibreOffice e trazê-lo de volta.

O caminho que o oficial pediu em 27/08/2026, quando o teor voltou à lista de
problemas pela segunda vez: *«possibilitar em botão facilitado a exportação do
arquivo base e permitir a importação do arquivo odt ou docx após a edição»*.

O QUE ESTES TESTES PROTEGEM É A IDA E VOLTA. Exportar e importar o mesmo teor
tem de devolver os mesmos parágrafos — é a mesma prova do leitor de arquivo da
CRA, e pelo mesmo motivo: conversão que não fecha o ciclo perde texto sem
ninguém ver, e aqui o texto é o de um ato notarial.
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import notas_teor_arquivo as TA                              # noqa: E402
from ri_odt import gerar_odt, html_para_odf                  # noqa: E402

TEOR = ("<p>SAIBAM quantos este público instrumento virem que, aos vinte e sete "
        "dias do mês de agosto.</p>\n"
        "<p>COMPARECERAM as partes entre si justas e contratadas.</p>\n"
        "<p>E de como assim disseram, do que dou fé.</p>")


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _docx(trechos: list) -> bytes:
    """Um `.docx` de mentira, com o espaço de nome DE VERDADE.

    A primeira versão deste ajudante declarava `xmlns:w="x"` — e por isso não
    testava o que o Word grava, e sim o que o meu leitor de então tolerava.
    Agora usa o espaço de nome real: o que passa aqui passa com o arquivo do
    Word.

    Cada trecho é `"texto"` ou `("texto", "b")` para vir marcado.
    """
    def paragrafo(t):
        if isinstance(t, tuple):
            texto, marca = t
            props = f"<w:rPr><w:{marca}/></w:rPr>"
        else:
            texto, props = t, ""
        return f"<w:p><w:r>{props}<w:t>{texto}</w:t></w:r></w:p>"

    corpo = "".join(paragrafo(t) for t in trechos)
    xml = (f'<?xml version="1.0"?><w:document xmlns:w="{W}"><w:body>{corpo}'
           f'</w:body></w:document>')
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr("word/document.xml", xml)
    return saida.getvalue()


# --------------------------------------------------------- o teor em HTML


def test_os_paragrafos_saem_do_html_em_ordem():
    p = TA.paragrafos_do_html(TEOR)
    assert len(p) == 3
    assert p[0].startswith("SAIBAM quantos")
    assert p[-1].endswith("dou fé.")


def test_teor_sem_paragrafo_vira_um_paragrafo_e_nao_some():
    """Perder o texto de um ato lavrado é o pior desfecho de uma conversão."""
    assert TA.paragrafos_do_html("texto solto, sem etiqueta") == [
        "texto solto, sem etiqueta"]
    assert TA.paragrafos_do_html("") == []
    assert TA.paragrafos_do_html(None) == []


def test_o_html_de_volta_preserva_as_marcas_do_teor():
    """CORRIGIDO EM 28/08/2026, e o teste guardava a versão sem formatação.

    Ele dizia que `html_dos_paragrafos` ESCAPA o que recebe — o que estava
    certo enquanto os parágrafos eram texto cru. Agora eles chegam já em HTML,
    com `<b>`, e escapar aqui transformaria o negrito em texto visível.

    Quem escapa é o LEITOR, na hora de tirar o texto do documento: é lá que o
    `<` do usuário vira `&lt;` e o negrito vira `<b>`. Escapar duas vezes
    mostraria `&lt;b&gt;` no ato.
    """
    saida = TA.html_dos_paragrafos(["a <b>negrito</b> aqui"])
    assert saida == "<p>a <b>negrito</b> aqui</p>"


def test_paragrafo_vazio_nao_entra():
    """O LibreOffice grava linha em branco entre parágrafos.

    Trazê-las de volta dobraria o espaçamento a cada ida e volta.
    """
    assert TA.html_dos_paragrafos(["um", "", "  ", "dois"]) == \
        "<p>um</p>\n<p>dois</p>"


# ------------------------------------------------------------ a ida e volta


def test_a_ida_e_volta_devolve_os_mesmos_paragrafos():
    """A prova do leitor da CRA, aplicada ao teor."""
    antes = TA.paragrafos_do_html(TEOR)
    arquivo = gerar_odt(html_para_odf(TEOR), titulo="rascunho")
    depois = TA.ler_documento(arquivo, "rascunho.odt")
    assert depois == antes


def test_a_ida_e_volta_sobrevive_a_acento_e_a_simbolo():
    teor = ("<p>Comparação: José & Maria, R$ 1.000,00 — «aspas» e ç, ã, õ.</p>"
            "<p>Segundo parágrafo, com 5 > 3 e 2 < 4.</p>")
    arquivo = gerar_odt(html_para_odf(teor), titulo="x")
    voltou = TA.ler_documento(arquivo, "x.odt")
    assert "José &amp; Maria" in voltou[0]     # escapado, como todo HTML
    assert "R$ 1.000,00" in voltou[0]
    assert "5 &gt; 3" in voltou[1] and "2 &lt; 4" in voltou[1]
    # E o que se lê continua sendo o que foi escrito.
    import html as _h
    assert "José & Maria" in _h.unescape(voltou[0])


def test_o_docx_tambem_volta():
    p = TA.ler_documento(_docx(["Primeiro parágrafo.", "Segundo."]),
                         "editado.docx")
    assert p == ["Primeiro parágrafo.", "Segundo."]


def test_o_negrito_do_word_volta():
    """«Negrito é fundamental para o layout da escritura» — o oficial."""
    p = TA.ler_documento(_docx([("JOÃO DA SILVA", "b"), ("comum",)[0]]),
                         "editado.docx")
    assert p[0] == "<b>JOÃO DA SILVA</b>"


def test_o_word_desliga_o_negrito_com_val_zero():
    """`<w:b w:val="0"/>` DESLIGA o negrito herdado do estilo do parágrafo.

    Ler a etiqueta como «tem negrito» poria em negrito justamente o trecho que
    o escrevente tirou do negrito.
    """
    xml = (f'<?xml version="1.0"?><w:document xmlns:w="{W}"><w:body>'
           f'<w:p><w:r><w:rPr><w:b w:val="0"/></w:rPr><w:t>sem negrito</w:t>'
           f'</w:r></w:p></w:body></w:document>')
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr("word/document.xml", xml)
    assert TA.ler_documento(saida.getvalue(), "x.docx") == ["sem negrito"]


# ----------------------------------------------------- o que se recusa, e como


def test_extensao_de_fora_e_recusada_com_frase_de_balcao():
    with pytest.raises(TA.TeorArquivoError, match="LibreOffice"):
        TA.ler_documento(b"qualquer coisa", "teor.doc")
    with pytest.raises(TA.TeorArquivoError, match="odt"):
        TA.ler_documento(b"qualquer coisa", "teor.pdf")


def test_arquivo_corrompido_diz_o_que_fazer():
    """Isso acontece no balcão, e o escrevente precisa de uma frase."""
    with pytest.raises(TA.TeorArquivoError, match="corrompido"):
        TA.ler_documento(b"nao sou um zip", "teor.odt")


def test_zip_sem_o_conteudo_esperado_diz_o_que_fazer():
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr("outra_coisa.xml", "<x/>")
    with pytest.raises(TA.TeorArquivoError, match="salve de novo"):
        TA.ler_documento(saida.getvalue(), "teor.odt")


def test_documento_sem_texto_e_recusado():
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr("content.xml",
                   '<office:document-content xmlns:office="urn:oasis:names:'
                   'tc:opendocument:xmlns:office:1.0"/>')
    with pytest.raises(TA.TeorArquivoError, match="texto nenhum"):
        TA.ler_documento(saida.getvalue(), "vazio.odt")


# ----------------------------------------------- a conferência antes de gravar


def test_a_conferencia_diz_o_tamanho_da_mudanca():
    """Quem traz de volta tem direito de ver o que está trazendo."""
    antes = TA.paragrafos_do_html(TEOR)
    igual = TA.conferir_a_volta(antes, list(antes))
    assert igual["mudou"] is False
    assert igual["iguais"] == 3

    mudou = TA.conferir_a_volta(antes, antes[:2] + ["parágrafo novo"])
    assert mudou["mudou"] is True
    assert mudou["iguais"] == 2
    assert mudou["paragrafos_antes"] == mudou["paragrafos_depois"] == 3


def test_a_conferencia_conta_paragrafo_a_mais_e_a_menos():
    antes = TA.paragrafos_do_html(TEOR)
    r = TA.conferir_a_volta(antes, antes + ["um a mais"])
    assert r["paragrafos_antes"] == 3 and r["paragrafos_depois"] == 4
    assert r["mudou"] is True
    assert r["letras_depois"] > r["letras_antes"]


# ---------------------------------------------------------------------------
# O NEGRITO — «é fundamental para o layout da escritura, preciso de uma solução
# perfeita, é a atividade fim do cartório» (o oficial, 28/08/2026).
#
# Num ato notarial o negrito é o que separa a qualificação da cláusula, o nome
# da parte do corpo do texto e o que se lê em voz alta do que se lê em silêncio.
# Trazer o teor sem ele é devolver um ato desformatado para ser reformatado à
# mão — que é pior que não ter exportado.

TEOR_COM_MARCAS = (
    "<p>COMPARECEU <b>JOÃO DA SILVA</b>, brasileiro, casado, portador do CPF "
    "000.000.010-82, e disse que <i>vende</i> o imóvel <u>matriculado</u> sob "
    "o nº 4.013.</p>"
    "<p><b>CLÁUSULA PRIMEIRA:</b> o preço é de <b>R$ 185.000,00</b>.</p>"
    "<p>Cláusula <b><i>grifada e inclinada</i></b> ao mesmo tempo.</p>"
    "<p>E de como assim disseram, <b>DOU FÉ</b>.</p>")


def test_a_ida_e_volta_preserva_negrito_italico_e_sublinhado():
    """A prova que o oficial pediu, e ela é de igualdade — não de semelhança."""
    antes = TA.paragrafos_do_html(TEOR_COM_MARCAS)
    arquivo = gerar_odt(html_para_odf(TEOR_COM_MARCAS), titulo="x")
    depois = TA.ler_documento(arquivo, "x.odt")
    assert depois == antes


def test_o_negrito_aninhado_volta_na_mesma_ordem():
    """Sem ordem fixa, `<b><i>` voltaria `<i><b>` e a igualdade quebraria.

    A ida e volta deixaria de ser prova de coisa nenhuma perdida: acusaria
    diferença onde não há.
    """
    antes = TA.paragrafos_do_html(
        "<p>Cláusula <b><i>assim</i></b> escrita.</p>")
    depois = TA.ler_documento(
        gerar_odt(html_para_odf("<p>Cláusula <b><i>assim</i></b> escrita.</p>"),
                  titulo="x"), "x.odt")
    assert depois == antes == ["Cláusula <b><i>assim</i></b> escrita."]


def test_strong_e_em_viram_b_e_i():
    """O teor montado pelo sistema usa `<b>`; o colado de fora pode usar
    `<strong>`. Os dois têm de sair iguais, senão a mesma ênfase daria dois
    resultados diferentes na ida e volta."""
    assert TA.paragrafos_do_html("<p>A <strong>B</strong> e <em>C</em>.</p>") \
        == ["A <b>B</b> e <i>C</i>."]


def test_o_arquivo_QUE_O_LIBREOFFICE_SALVA_tambem_volta():
    """É este o arquivo que interessa, e não o que a casa acabou de gerar.

    Ao salvar, o LibreOffice reescreve os estilos com nomes próprios — `T1`,
    `T2` — e a formatação passa a morar nas PROPRIEDADES do estilo. Procurar
    `T-negrito` funcionaria só com o arquivo que ninguém abriu.
    """
    libre = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-content'
        ' xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"'
        ' xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"'
        ' xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"'
        ' xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0">'
        '<office:automatic-styles>'
        '<style:style style:name="T1" style:family="text">'
        '<style:text-properties fo:font-weight="bold"/></style:style>'
        '<style:style style:name="T2" style:family="text">'
        '<style:text-properties fo:font-style="italic"/></style:style>'
        '<style:style style:name="T3" style:family="text">'
        '<style:text-properties style:text-underline-style="solid"/></style:style>'
        '</office:automatic-styles>'
        '<office:body><office:text>'
        '<text:p text:style-name="P1">COMPARECEU '
        '<text:span text:style-name="T1">JOÃO DA SILVA</text:span>, e '
        '<text:span text:style-name="T2">vende</text:span> o '
        '<text:span text:style-name="T3">imóvel</text:span>.</text:p>'
        '</office:text></office:body></office:document-content>')
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr("content.xml", libre)
    assert TA.ler_documento(saida.getvalue(), "editado.odt") == [
        "COMPARECEU <b>JOÃO DA SILVA</b>, e <i>vende</i> o <u>imóvel</u>."]


def test_o_estilo_QUE_HERDA_nao_perde_o_negrito_do_pai():
    """O LibreOffice usa herança: `T4` herda de `T1` e só acrescenta o itálico.

    Sem resolver a herança, o negrito do pai sumiria — e sumiria calado, que é
    o pior jeito de perder ênfase num ato.
    """
    libre = (
        '<?xml version="1.0"?>'
        '<office:document-content'
        ' xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"'
        ' xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"'
        ' xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"'
        ' xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0">'
        '<office:automatic-styles>'
        '<style:style style:name="T1" style:family="text">'
        '<style:text-properties fo:font-weight="bold"/></style:style>'
        '<style:style style:name="T4" style:family="text"'
        ' style:parent-style-name="T1">'
        '<style:text-properties fo:font-style="italic"/></style:style>'
        '</office:automatic-styles>'
        '<office:body><office:text>'
        '<text:p>Um <text:span text:style-name="T4">trecho</text:span>.</text:p>'
        '</office:text></office:body></office:document-content>')
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr("content.xml", libre)
    assert TA.ler_documento(saida.getvalue(), "x.odt") == [
        "Um <b><i>trecho</i></b>."]


def test_peso_normal_nao_e_negrito():
    """`fo:font-weight="normal"` é o estilo que DESLIGA o negrito herdado."""
    libre = (
        '<?xml version="1.0"?>'
        '<office:document-content'
        ' xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"'
        ' xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"'
        ' xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"'
        ' xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0">'
        '<office:automatic-styles>'
        '<style:style style:name="T9" style:family="text">'
        '<style:text-properties fo:font-weight="normal"/></style:style>'
        '</office:automatic-styles>'
        '<office:body><office:text>'
        '<text:p>Um <text:span text:style-name="T9">trecho</text:span>.</text:p>'
        '</office:text></office:body></office:document-content>')
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr("content.xml", libre)
    assert TA.ler_documento(saida.getvalue(), "x.odt") == ["Um trecho."]


def test_a_conferencia_conta_o_negrito_a_parte():
    """Se a volta perdesse a ênfase, é aqui que se veria — antes de gravar."""
    antes = TA.paragrafos_do_html(TEOR_COM_MARCAS)
    sem_marcas = [TA._sem_marcas(p) for p in antes]
    r = TA.conferir_a_volta(antes, sem_marcas)
    assert r["negrito_antes"] == 5   # os cinco trechos do teor acima
    assert r["negrito_depois"] == 0
    assert r["mudou"] is True
    # E as letras são as mesmas dos dois lados: `letras_*` conta SEM as marcas,
    # justamente para que a perda de ênfase apareça no contador do negrito e
    # não se disfarce numa diferença de tamanho.
    assert r["letras_antes"] == r["letras_depois"]
    assert r["iguais"] == 0          # nenhum parágrafo ficou igual
