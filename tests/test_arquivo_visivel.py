"""O QUE ABRE NA TELA, E O QUE TEM DE BAIXAR.

O DEFEITO QUE ISTO CONSERTA É DE 29/08/2026, E FICOU MEIO ANO PELA METADE
    O relato #25 do oficial pedia *«anexar documentos e **visualizar** esses
    documentos»*. `ri_documentos.e_imagem` nasceu para decidir isso, com o
    comentário «QUEM LAVRA PRECISA VER, E NAO BAIXAR», e a tela do RI põe
    `target="_blank"` no link quando o arquivo é PDF ou imagem.

    **E a única rota que servia arquivo mandava `as_attachment=True`** — o
    navegador baixava, sempre. A metade que decide estava pronta e a metade que
    serve nunca soube dela.

POR QUE A LISTA É CURTA, E POR QUE ISSO É UM TESTE E NÃO UM COMENTÁRIO
    Arquivo servido **em linha** roda na **origem do sistema**. Um `.html` ou um
    `.svg` enviado por terceiro traria o script dele para dentro da sessão de
    quem está no balcão, com o cookie de login à mão — e o balcão recebe
    arquivo de fora todo dia.

    `svg` é a armadilha: **é imagem, e é XML com `<script>`**. Pô-lo ao lado do
    `png` é o engano que esta lista existe para impedir, e um comentário não
    impediria ninguém de o acrescentar amanhã.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import arquivo_visivel as ARQVIS

# ------------------------------------------------ o que abre e o que não


@pytest.mark.parametrize("nome", [
    "titulo.pdf", "TITULO.PDF", "estatuto.png", "ata.jpg", "ata.jpeg",
    "digitalizacao.gif", "foto.webp", "scan.bmp",
])
def test_o_que_o_navegador_desenha_abre_na_tela(nome):
    assert ARQVIS.abre_na_tela(nome) is True


@pytest.mark.parametrize("nome", [
    "minuta.docx", "planilha.xlsx", "acervo.zip", "dados.json", "leia.txt",
    "pacote.p7s", "molde.odt",
])
def test_o_que_o_navegador_nao_desenha_baixa(nome):
    assert ARQVIS.abre_na_tela(nome) is False


def test_o_SVG_NAO_ABRE_NA_TELA_e_ele_e_imagem():
    """**A armadilha desta lista.** SVG é XML e carrega `<script>`: servido em
    linha, ele roda na origem do sistema com o cookie de login à mão. Quem o
    puser aqui por ser «imagem» abre a porta que a lista existe para fechar.
    """
    assert ARQVIS.abre_na_tela("assinatura.svg") is False
    assert "svg" not in ARQVIS.TIPOS_QUE_ABREM_NA_TELA


def test_o_HTML_e_o_XML_tambem_nao_abrem():
    for nome in ("pagina.html", "pagina.htm", "dados.xml", "remessa.xhtml"):
        assert ARQVIS.abre_na_tela(nome) is False, nome


def test_o_TIFF_fica_de_fora_e_o_motivo_e_outro():
    """Não é segurança: é que quase nenhum navegador o desenha. Um arquivo que
    não abre servido «em linha» vira tela em branco, que é pior que o botão de
    baixar — ninguém sabe se o documento está corrompido ou se o sistema
    quebrou."""
    assert ARQVIS.abre_na_tela("ficha.tif") is False
    assert ARQVIS.abre_na_tela("ficha.tiff") is False


def test_nome_sem_extensao_nao_abre():
    assert ARQVIS.abre_na_tela("documento") is False
    assert ARQVIS.abre_na_tela("") is False
    assert ARQVIS.abre_na_tela(None) is False


def test_arquivo_oculto_nao_e_lido_como_extensao():
    """`Path(...).suffix` e não `rsplit('.')`: um nome que **começa** com ponto
    o `rsplit` leria como extensão."""
    assert ARQVIS.extensao(".env") == ""
    assert ARQVIS.abre_na_tela(".env") is False


def test_a_extensao_dupla_vale_pela_ULTIMA():
    """`titulo.pdf.exe` é um executável, e não um PDF. Quem ler pela primeira
    serve como PDF um arquivo que não é."""
    assert ARQVIS.abre_na_tela("titulo.pdf.exe") is False
    assert ARQVIS.abre_na_tela("titulo.exe.pdf") is True


# ------------------------------------------------------- o tipo declarado


def test_o_tipo_do_pdf_e_o_do_pdf():
    assert ARQVIS.tipo_do_arquivo("titulo.pdf") == "application/pdf"
    assert ARQVIS.e_pdf("titulo.pdf") is True
    assert ARQVIS.e_pdf("estatuto.png") is False


def test_jpg_e_jpeg_declaram_o_mesmo_tipo():
    assert (ARQVIS.tipo_do_arquivo("a.jpg")
            == ARQVIS.tipo_do_arquivo("a.jpeg") == "image/jpeg")


def test_o_que_nao_abre_declara_o_generico_e_nao_None():
    """**`application/octet-stream` é justamente o tipo que diz «isto é para
    guardar, não para abrir».** Devolver `None` faria quem chama decidir
    sozinho, e um dia alguém decidiria `text/html`."""
    assert ARQVIS.tipo_do_arquivo("minuta.docx") == "application/octet-stream"
    assert ARQVIS.tipo_do_arquivo("pagina.html") == "application/octet-stream"


# -------------------------------------------------------- os cabeçalhos


def test_quem_mostra_manda_nosniff():
    """Sem ele o navegador pode ignorar o tipo declarado e adivinhar pelo
    conteúdo: um arquivo com cara de HTML servido como PDF voltaria a ser HTML,
    e a lista de cima teria sido para nada."""
    assert ARQVIS.cabecalhos_para_mostrar()["X-Content-Type-Options"] == "nosniff"


def test_a_politica_proibe_script_e_moldura_de_fora():
    politica = ARQVIS.cabecalhos_para_mostrar()["Content-Security-Policy"]
    assert "sandbox" in politica
    assert "frame-ancestors 'self'" in politica


def test_os_cabecalhos_saem_como_COPIA():
    """Uma rota que resolvesse acrescentar um cabeçalho ao que recebe estaria
    mudando o de todas as outras — e um dia alguém removeria o `nosniff` de uma
    tela sem saber que removeu de sete."""
    a = ARQVIS.cabecalhos_para_mostrar()
    a["X-Content-Type-Options"] = "mexido"
    assert ARQVIS.cabecalhos_para_mostrar()["X-Content-Type-Options"] == "nosniff"


# ------------------------------------- a régua velha e a nova concordam


def test_esta_regua_nao_e_MAIS_LARGA_que_a_do_RI():
    """**A mesma pergunta em dois lugares não pode ter duas respostas.**
    `ri_documentos.e_imagem` decide o que a tela do RI OFERECE para ver; esta
    decide o que a rota SERVE. Se esta fosse mais larga, a rota abriria em
    linha um tipo que aquela nem oferece — e o alargamento entraria sem
    ninguém rever a lista de segurança.

    O contrário é permitido, e há um caso: `ri_documentos.e_imagem` aceita
    `svg`? **Não** — as duas listas hoje coincidem, e este teste guarda que a
    de servir nunca passe à frente.
    """
    import ri_documentos as RDOC
    for extensao in ARQVIS.TIPOS_QUE_ABREM_NA_TELA:
        assert RDOC.e_imagem(f"x.{extensao}"), (
            f"a rota serviria `.{extensao}` em linha e a tela do RI nem o "
            f"oferece — as duas réguas divergiram")
