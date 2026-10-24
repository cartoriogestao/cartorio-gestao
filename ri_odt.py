"""
Geracao de documentos ODF (.odt) para o Registro de Imoveis.

Escrito sobre a biblioteca padrao: um .odt e um ZIP com XML dentro, entao nao
ha dependencia nova para instalar em cada maquina.

Por que .odt e nao .docx: e o formato nativo do LibreOffice, pedido pela
serventia, e o Word tambem abre desde a versao 2007. Gera um arquivo so que
serve nas duas situacoes.

O modelo da ficha e escrito em HTML simples pelo proprio usuario. Aqui ele
vira paragrafos ODF. O teor herdado do E-Oficio ja e XHTML, entao passa pelo
mesmo caminho sem conversao extra.
"""
from __future__ import annotations
from certidao_texto import sem_linha_de_assinatura_a_mao

import re
import zipfile
from html.parser import HTMLParser
from io import BytesIO
from xml.sax.saxutils import escape

MIME = "application/vnd.oasis.opendocument.text"

MANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2">
 <manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>
 <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
 <manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>
__IMAGENS__
</manifest:manifest>
"""

# O NOME DO ESTILO QUE ABRE A PÁGINA 1 SEM O CABEÇALHO DE PÁGINA — ver
# `gerar_odt`, parâmetro `cabecalho_a_partir_da_pagina_2`. Quem monta o corpo
# usa este nome de estilo (herda a centralização de "P-centro") no ÚNICO
# parágrafo que deve começar a página 1; o resto do documento nunca o
# repete, porque `style:master-page-name` dispara a troca de página-mestre
# toda vez que um parágrafo com esse estilo começa.
ESTILO_PAGINA_1 = "P-inicio-pagina-1"

NS = (
    'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
    'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
    'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
    'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
    'xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" '
    'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
    'xmlns:xlink="http://www.w3.org/1999/xlink" '
    'xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"'
)

# Estilos da tabela usada no cabecalho.
#
# POR QUE UMA TABELA DE VERDADE, E NAO TABULACAO
#   A primeira tentativa alinhou as duas colunas com paradas de tabulacao. Nao
#   funcionou por dois motivos: o cabecalho mora em styles.xml, e o estilo com
#   as paradas estava sendo declarado so em content.xml — de onde o cabecalho
#   nao enxerga; e, mesmo corrigido isso, nome comprido invade a coluna do
#   lado, porque tabulacao nao quebra linha. Celula de tabela quebra.
#
#   Bordas invisiveis: a tabela e so o esqueleto do alinhamento, nao se ve.
ESTILOS_TABELA = """
  <style:style style:name="Tab-cab" style:family="table">
   <style:table-properties style:width="16cm" table:align="center"
     fo:margin-top="0.1cm" fo:margin-bottom="0.1cm"/>
  </style:style>
  <style:style style:name="Tab-cab.col" style:family="table-column">
   <style:table-column-properties style:column-width="8cm"
     style:use-optimal-column-width="false"/>
  </style:style>
  <style:style style:name="Tab-cab.cel" style:family="table-cell">
   <style:table-cell-properties fo:padding="0.05cm" fo:border="none"/>
  </style:style>
  <!-- Celula com moldura visivel: e assim que o cabecalho do modelo em papel
       se organiza — uma grade de caixas, nao linhas soltas. -->
  <style:style style:name="Cel-grade" style:family="table-cell">
   <style:table-cell-properties fo:padding="0.1cm" fo:border="0.5pt solid #000000"
     style:vertical-align="middle"/>
  </style:style>
  <style:style style:name="P-celula" style:family="paragraph" style:parent-style-name="Standard">
   <style:paragraph-properties fo:text-align="center" fo:margin-bottom="0cm"/>
   <!-- 10pt: "BEATRIZ EXEMPLO DE SOUZA" nao cabe em 8cm a 12pt e
        quebra em duas linhas, deixando o cabecalho torto. -->
   <style:text-properties fo:font-size="10pt"/>
  </style:style>
  <style:style style:name="P-celula-destaque" style:family="paragraph" style:parent-style-name="Standard">
   <style:paragraph-properties fo:text-align="center" fo:margin-bottom="0cm"/>
   <style:text-properties fo:font-size="12pt"/>
  </style:style>

  <!-- Quadro do selo, copiado do modelo em papel: uma caixa larga com dois
       selos lado a lado, separados por um vao. As bordas ficam so por fora —
       as divisoes internas sao invisiveis, senao viram uma grade. Arial 6pt,
       que e o corpo de letra do selo no modelo. -->
  <style:style style:name="Tab-selo" style:family="table">
   <style:table-properties style:width="16cm" table:align="center"
     fo:margin-top="0.15cm" fo:margin-bottom="0.25cm"/>
  </style:style>
  <style:style style:name="Tab-selo.c1" style:family="table-column">
   <style:table-column-properties style:column-width="5.9cm"/>
  </style:style>
  <style:style style:name="Tab-selo.c2" style:family="table-column">
   <style:table-column-properties style:column-width="2.1cm"/>
  </style:style>
  <style:style style:name="Cel-selo-ini" style:family="table-cell">
   <style:table-cell-properties fo:padding="0.12cm"
     fo:border-top="0.06pt solid #000000" fo:border-bottom="0.06pt solid #000000"
     fo:border-left="0.06pt solid #000000" fo:border-right="none"/>
  </style:style>
  <style:style style:name="Cel-selo-meio" style:family="table-cell">
   <style:table-cell-properties fo:padding="0.12cm"
     fo:border-top="0.06pt solid #000000" fo:border-bottom="0.06pt solid #000000"
     fo:border-left="none" fo:border-right="none"/>
  </style:style>
  <style:style style:name="Cel-selo-fim" style:family="table-cell">
   <style:table-cell-properties fo:padding="0.12cm"
     fo:border-top="0.06pt solid #000000" fo:border-bottom="0.06pt solid #000000"
     fo:border-left="none" fo:border-right="0.06pt solid #000000"/>
  </style:style>
  <style:style style:name="P-selo-cel" style:family="paragraph" style:parent-style-name="Standard">
   <!-- Alinhado a esquerda, e nao justificado como no modelo em Word: o selo
        tem poucas palavras por linha e a justificacao abre buracos enormes
        entre elas. -->
   <style:paragraph-properties fo:text-align="start" fo:margin-bottom="0cm"/>
   <style:text-properties style:font-name="Arial" fo:font-size="6pt"/>
  </style:style>
  <style:style style:name="Tab-selos-compactos" style:family="table">
   <!-- ESPACO EM BRANCO NO LIVRO E ONDE SE INSERE TEXTO DEPOIS. Pedido do
        oficial em 15/09/2026: «diminua os espacos entre o final do texto e as
        listras, nao eh pra ter espaco sobrando pra falsificar e inserir texto
        no meio». Era 0,12 cm em cima e 0,15 embaixo; agora o carimbo encosta
        no fim do ato. -->
   <style:table-properties style:width="16cm" table:align="center"
     fo:margin-top="0.02cm" fo:margin-bottom="0.04cm"/>
  </style:style>
  <!-- A grade de dentro de CADA carimbo: QR a esquerda, texto ao lado. Sem
       borda — a borda de fora e a da celula do carimbo. -->
  <style:style style:name="Tab-selo-interno" style:family="table">
   <style:table-properties style:width="7.7cm" table:align="left"
     fo:margin-top="0cm" fo:margin-bottom="0cm"/>
  </style:style>
  <style:style style:name="Col-selo-qr" style:family="table-column">
   <style:table-column-properties style:column-width="1.45cm"
     style:use-optimal-column-width="false"/>
  </style:style>
  <style:style style:name="Col-selo-texto" style:family="table-column">
   <style:table-column-properties style:column-width="6.25cm"
     style:use-optimal-column-width="false"/>
  </style:style>
  <style:style style:name="Cel-selo-interna" style:family="table-cell">
   <style:table-cell-properties fo:padding="0.02cm" fo:border="none"
     style:vertical-align="middle"/>
  </style:style>
  <style:style style:name="P-selo-rotulo" style:family="paragraph" style:parent-style-name="Standard">
   <style:paragraph-properties fo:text-align="start" fo:margin-bottom="0cm"
     fo:margin-top="0cm"/>
   <style:text-properties style:font-name="Arial" fo:font-size="5pt"
     fo:font-weight="bold" fo:color="#555555"/>
  </style:style>
  <!-- A LARGURA INTEIRA, DA CERTIDAO — 17/09/2026. Medido a 5,5 pt: a
       linha de valores da certidao mede 9,61 cm e o link 6,97 cm, e a coluna
       de texto de meia largura tem 6,25 cm — as duas quebravam. A certidao
       tem UM selo (691 em 691 no razao), e por isso pode ocupar tudo; o ato
       da ficha pode ter dois, e continua com meia largura. -->
  <style:style style:name="Col-selo-texto-larga" style:family="table-column">
   <style:table-column-properties style:column-width="14.25cm"
     style:use-optimal-column-width="false"/>
  </style:style>
  <style:style style:name="Col-selo-inteiro" style:family="table-column">
   <style:table-column-properties style:column-width="16cm"
     style:use-optimal-column-width="false"/>
  </style:style>
  <style:style style:name="Tab-selo-interno-largo" style:family="table">
   <style:table-properties style:width="15.7cm" table:align="left"
     fo:margin-top="0cm" fo:margin-bottom="0cm"/>
  </style:style>
  <style:style style:name="Col-selo-compacto" style:family="table-column">
   <style:table-column-properties style:column-width="8cm"
     style:use-optimal-column-width="false"/>
  </style:style>
  <style:style style:name="Cel-selo-compacto" style:family="table-cell">
   <style:table-cell-properties fo:padding="0.08cm" fo:border="0.5pt solid #000000"
     style:vertical-align="middle"/>
  </style:style>
  <!-- O CARIMBO DE UMA LINHA, DO LIVRO — 16/09/2026. Ordem do oficial:
       «nao faz sentido qr code de selo e link de acesso a consulta de selo no
       livro. Vamos trabalhar numa etiqueta mais compacta, preferencia que
       ocupe apenas uma linha, com as outras informacoes».

       E UM PARAGRAFO, E NAO UMA TABELA: tabela tem altura de celula e
       alinhamento vertical: para uma linha so ela gasta o dobro do espaco em
       branco — e espaco em branco no livro e onde cabe uma linha que ninguem
       lavrou. O quadro e a borda do proprio paragrafo.

       QUANDO A ETIQUETA E MAIOR QUE A LINHA ele quebra, e nao corta: medido
       nos 1.965 selos do RI desta casa, 1.955 cabem numa linha a 5,5 pt; os
       dez que sobram sao averbacoes de valor alto. Cortar esconderia um
       fundo cobrado. -->
  <style:style style:name="P-selo-linha" style:family="paragraph" style:parent-style-name="Standard">
   <style:paragraph-properties fo:text-align="start" fo:margin-top="0.02cm"
     fo:margin-bottom="0.04cm" fo:line-height="105%" fo:padding="0.05cm"
     fo:border="0.5pt solid #000000"/>
   <style:text-properties style:font-name="Arial" fo:font-size="5.5pt"/>
  </style:style>
  <style:style style:name="P-selo-compacto" style:family="paragraph" style:parent-style-name="Standard">
   <style:paragraph-properties fo:text-align="start" fo:margin-bottom="0cm"
     fo:margin-top="0cm" fo:line-height="105%"/>
   <style:text-properties style:font-name="Arial" fo:font-size="5.5pt"/>
  </style:style>
  <style:style style:name="P-cabecalho" style:family="paragraph" style:parent-style-name="Standard">
   <style:paragraph-properties fo:text-align="center" fo:margin-bottom="0cm"/>
   <style:text-properties fo:font-size="10pt"/>
  </style:style>
"""

STYLES = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles {NS} office:version="1.2">
 <office:styles>
  <style:style style:name="Standard" style:family="paragraph">
   <style:text-properties style:font-name="Times New Roman" fo:font-size="12pt"/>
  </style:style>
  <style:style style:name="P-centro" style:family="paragraph" style:parent-style-name="Standard">
   <style:paragraph-properties fo:text-align="center"/>
  </style:style>
  <style:style style:name="P-just" style:family="paragraph" style:parent-style-name="Standard">
   <style:paragraph-properties fo:text-align="justify" fo:margin-top="0cm" fo:margin-bottom="0.06cm"/>
  </style:style>
  <style:style style:name="P-ato-cab" style:family="paragraph" style:parent-style-name="Standard">
   <style:paragraph-properties fo:text-align="justify" fo:margin-top="0.04cm" fo:margin-bottom="0cm"/>
  </style:style>
  <!-- A LISTRA COLA NO TEXTO — pedido do oficial em 15/09/2026: «diminua os
       espacos entre o final do texto e as listras, nao eh pra ter espaco
       sobrando pra falsificar e inserir texto no meio». Eram 0,25 cm em cima,
       0,10 de recheio e 0,25 embaixo: **0,60 cm de branco** em volta de cada
       risca, e uma ficha com dez atos abria seis centimetros de espaco onde
       cabe linha que ninguem lavrou. Agora sao 0,13 cm ao todo, e a risca
       continua visivel. -->
  <style:style style:name="P-separa-ato" style:family="paragraph" style:parent-style-name="Standard">
   <style:paragraph-properties fo:border-bottom="0.06cm double #000000" fo:border-top="none" fo:border-left="none" fo:border-right="none" fo:padding-bottom="0.03cm" fo:margin-top="0.04cm" fo:margin-bottom="0.04cm"/>
  </style:style>
  <style:style style:name="T-negrito" style:family="text">
   <style:text-properties fo:font-weight="bold"/>
  </style:style>
  <style:style style:name="T-italico" style:family="text">
   <style:text-properties fo:font-style="italic"/>
  </style:style>
  <style:style style:name="T-sublinhado" style:family="text">
   <style:text-properties style:text-underline-style="solid" style:text-underline-width="auto"/>
  </style:style>
  <style:style style:name="T-tachado-vermelho" style:family="text">
   <style:text-properties fo:color="#c62828" style:text-line-through-style="solid"
     style:text-line-through-type="single"/>
  </style:style>
  <style:style style:name="T-destaque-amarelo" style:family="text">
   <style:text-properties fo:background-color="#fff59d"/>
  </style:style>
  <style:style style:name="T-destaque-vermelho" style:family="text">
   <style:text-properties fo:background-color="#ffcdd2"/>
  </style:style>
 </office:styles>
 <office:automatic-styles>{ESTILOS_TABELA}
  <style:page-layout style:name="pm1">
   <style:page-layout-properties fo:page-width="21cm" fo:page-height="29.7cm"
     fo:margin-top="1.5cm" fo:margin-bottom="2cm" fo:margin-left="2.5cm" fo:margin-right="2.5cm">
    <style:footnote-sep style:width="0.018cm" style:distance-before-sep="0.101cm"
      style:distance-after-sep="0.101cm" style:line-style="solid" style:rel-width="25%"/>
   </style:page-layout-properties>
   <!-- O cabecalho e repetido em toda folha e precisa de respiro ate o texto:
        sem a margem de baixo, a primeira linha do corpo encosta nele. -->
   <style:header-style>
    <style:header-footer-properties fo:min-height="3.2cm" fo:margin-bottom="0.8cm"
      style:dynamic-spacing="true" fo:border-bottom="0.06pt solid #000000"
      fo:padding-bottom="0.15cm"/>
   </style:header-style>
  </style:page-layout>
 </office:automatic-styles>
 <office:master-styles>
  <style:master-page style:name="Standard" style:page-layout-name="pm1">
   <style:header>__CABECALHO__</style:header>
  </style:master-page>
 </office:master-styles>
</office:document-styles>
"""

# Larguras de coluna pedidas pelos modelos, descobertas em tempo de execucao.
# Chave = nome do estilo, valor = XML. Fica aqui, e nao dentro do conversor,
# porque o mesmo estilo precisa entrar nos dois arquivos do pacote.
ESTILOS_EXTRA: dict[str, str] = {}

ESTILOS_AUTO = ESTILOS_TABELA + """
  <style:style style:name="P-just" style:family="paragraph" style:parent-style-name="Standard">
   <style:paragraph-properties fo:text-align="justify" fo:margin-bottom="0.15cm"/>
  </style:style>
  <style:style style:name="P-ato-final" style:family="paragraph" style:parent-style-name="Standard">
   <style:paragraph-properties fo:text-align="justify" fo:margin-bottom="0cm"/>
  </style:style>
  <style:style style:name="P-centro" style:family="paragraph" style:parent-style-name="Standard">
   <style:paragraph-properties fo:text-align="center" fo:margin-bottom="0.15cm"/>
  </style:style>
  <style:style style:name="P-separa-ato" style:family="paragraph" style:parent-style-name="Standard">
   <style:paragraph-properties fo:border-bottom="0.06cm double #000000" fo:border-top="none" fo:border-left="none" fo:border-right="none" fo:padding-bottom="0.03cm" fo:margin-top="0.04cm" fo:margin-bottom="0.04cm"/>
  </style:style>
  <style:style style:name="T-negrito" style:family="text">
   <style:text-properties fo:font-weight="bold"/>
  </style:style>
  <style:style style:name="T-italico" style:family="text">
   <style:text-properties fo:font-style="italic"/>
  </style:style>
  <style:style style:name="T-sublinhado" style:family="text">
   <style:text-properties style:text-underline-style="solid" style:text-underline-width="auto"/>
  </style:style>
  <style:style style:name="T-tachado-vermelho" style:family="text">
   <style:text-properties fo:color="#c62828" style:text-line-through-style="solid"
     style:text-line-through-type="single"/>
  </style:style>
  <style:style style:name="T-destaque-amarelo" style:family="text">
   <style:text-properties fo:background-color="#fff59d"/>
  </style:style>
  <style:style style:name="T-destaque-vermelho" style:family="text">
   <style:text-properties fo:background-color="#ffcdd2"/>
  </style:style>
  <!-- Uma caixa por selo.
       style:join-border="false" e o que impede o LibreOffice de fundir dois
       selos seguidos num quadro so: por padrao, paragrafos vizinhos com a
       mesma borda viram uma caixa unica com uma linha no meio. Cada selo tem
       de ficar na sua, como sai do sistema do tribunal. -->
  <style:style style:name="P-selo" style:family="paragraph" style:parent-style-name="Standard">
   <style:paragraph-properties fo:text-align="left" fo:margin-top="0.15cm"
     fo:margin-bottom="0.15cm" fo:border="0.5pt solid #000000" fo:padding="0.15cm"
     style:join-border="false"/>
   <style:text-properties style:font-name="Arial" fo:font-size="7pt"/>
  </style:style>
  <style:style style:name="Fr-qr" style:family="graphic">
   <style:graphic-properties style:vertical-pos="middle" style:vertical-rel="text"
     style:horizontal-pos="left" style:horizontal-rel="paragraph" style:wrap="none"/>
  </style:style>
"""


class _ParaOdf(HTMLParser):
    """Converte HTML simples em paragrafos ODF.

    Trata o que aparece de fato nas fichas: paragrafos, quebras, negrito,
    italico, sublinhado, titulos e tabelas. Tag desconhecida vira texto
    corrido, nunca erro - a ficha precisa sair mesmo com marcacao estranha.
    """

    NEGRITO = {"b", "strong"}
    ITALICO = {"i", "em"}
    SUBLINHADO = {"u", "ins"}
    TACHADO = {"s", "strike", "del"}
    BLOCO = {"p", "div", "h1", "h2", "h3", "h4", "li"}

    def __init__(self, compacto: bool = False):
        super().__init__(convert_charrefs=True)
        self.compacto = compacto
        self.saida: list[str] = []
        self._buf: list[str] = []
        self._estilos: list[str] = []
        self._centro = False
        self._na_tabela = 0
        self._linhas: list[list[tuple[str, int, str]]] = []   # tabela em construcao
        self._celulas: list[tuple[str, int, str]] = []        # linha em construcao
        self._numero_tabela = 0
        self._tab_borda = False
        self._tab_larguras: list[str] = []
        self._span_atual = 1
        self._estilo_celula_atual = "P-celula"
        self.colunas_extra: list[tuple[str, str]] = []   # (nome do estilo, largura)
        # `<p>` aberto sem atributo nenhum: e assim que o codigo desta casa
        # pede uma linha em branco, e e so por essa forma que ela sai.
        self._p_sem_atributo = False
        # Parágrafo-risca entre atos (certidão / ficha): vira P-separa-ato.
        self._separa_ato = False
        self._ato_cab = False

    def _estilo_do_mark(self, attrs: dict) -> str:
        """Destaque amarelo ou vermelho a partir de class/style do <mark>."""
        junto = ((attrs.get("style") or "") + " " + (attrs.get("class") or "")).lower()
        if any(x in junto for x in ("ffcdd2", "ef9a9a", "e57373", "destaque-vermelho")):
            return "T-destaque-vermelho"
        if any(x in junto for x in ("fff59d", "ffeb3b", "ffff00", "amarelo", "yellow")):
            return "T-destaque-amarelo"
        # fundo vermelho genérico
        if "vermelho" in junto and "tachado" not in junto:
            return "T-destaque-vermelho"
        return "T-destaque-amarelo"

    # -- paragrafos --------------------------------------------------

    def _fecha(self):
        """Fecha o paragrafo corrente.

        PARAGRAFO VAZIO SAI, E ATE 31/08/2026 ELE SUMIA. Quem escreve
        `<p></p>` no codigo esta pedindo UMA LINHA EM BRANCO — e essa e a
        unica coisa que aquela linha faz. Descarta-la e perder o pedido
        inteiro, calado.

        Foi achado medindo o relato #27 do oficial: «precisa de mais espaco
        livre para desenvolver a assinatura». Aumentei o espaco da ficha de
        tres linhas para cinco e o teste continuou dizendo ZERO — **as tres
        nunca tinham chegado ao papel**, e a linha de assinar saia colada no
        rotulo. Sao 80 `<p></p>` em sete modulos que geram `.odt`, e todos
        eram espaco que alguem pediu e nao recebeu.

        O paragrafo vazio nao leva estilo: `P-just` justificaria o nada, e
        `P-centro` o centraria. O que se quer ali e altura de linha.
        """
        texto = "".join(self._buf).strip()
        self._buf.clear()
        # Risca entre atos em LARGURA TOTAL (Beatriz 24/09/2026).
        # HTML `class="separa-ato"` ou parágrafo só de traços (`----…`)
        # vira a borda ODF `P-separa-ato` — traçinhos sozinhos paravam no
        # meio da página.
        if self._separa_ato:
            self.saida.append(SEPARADOR_DE_ATO)
            self._separa_ato = False
            self._ato_cab = False
            self._centro = False
            return
        if texto:
            visivel = " ".join(re.sub(r"<[^>]+>", " ", texto).split())
            # A LINHA DE ASSINAR NÃO É RISCA ENTRE ATOS — 14/10/2026. O
            # `<p align="center">____</p>` de `notas_teor.bloco_de_assinaturas`
            # (traslado e termo do livro, 18/09/2026) também casa com a régua
            # da risca, e desde 24/09 saía como a borda de largura total: o
            # papel ficava sem o traço curto, centrado, onde a caneta passa.
            linha_de_assinar = self._centro and set(visivel) <= {"_", " "}
            if _JA_E_UMA_RISCA.match(visivel) and not linha_de_assinar:
                self.saida.append(SEPARADOR_DE_ATO)
            else:
                if self.compacto:
                    estilo = "P-cabecalho"
                elif getattr(self, "_ato_cab", False):
                    estilo = "P-ato-cab"
                else:
                    estilo = "P-centro" if self._centro else "P-just"
                self.saida.append(
                    f'<text:p text:style-name="{estilo}">{texto}</text:p>')
        self._centro = False
        self._separa_ato = False
        self._ato_cab = False

    def _linha_em_branco(self):
        """Um paragrafo vazio, que e uma LINHA EM BRANCO no papel.

        Ele nao leva estilo de proposito: `P-just` justificaria o nada e
        `P-centro` o centraria. O que se quer ali e altura de linha.
        """
        self.saida.append("<text:p/>")

    def _fecha_celula(self, linhas_ocupadas: int = 1):
        for _ in self._estilos:
            self._buf.append("</text:span>")
        self._estilos.clear()
        self._celulas.append(("".join(self._buf).strip(), linhas_ocupadas,
                              self._estilo_celula_atual))
        self._buf.clear()

    def _emite_tabela(self):
        """Escreve a tabela ODF acumulada.

        Entende `border="1"` para moldura visivel — e assim que o cabecalho da
        ficha vira uma grade de caixas — e `rowspan`, que e o que faz a coluna
        da serventia ocupar as duas linhas, como no modelo em papel. As
        larguras vem do atributo `cols`, em centimetros.
        """
        linhas = [l for l in self._linhas if l]
        self._linhas = []
        if not linhas:
            return
        colunas = max(sum(1 for _ in l) for l in linhas)
        larguras = self._tab_larguras or []
        estilo_cel = "Cel-grade" if self._tab_borda else "Tab-cab.cel"
        self._numero_tabela += 1

        partes = [f'<table:table table:name="Tab{self._numero_tabela}" '
                  f'table:style-name="Tab-cab">']
        for i in range(colunas):
            if i < len(larguras):
                # Nome derivado da propria largura: dois modelos que pedem
                # 6.5cm compartilham o estilo, e a lista nao cresce sem fim.
                nome = "Col-" + re.sub(r"[^0-9a-zA-Z]", "-", larguras[i])
                partes.append(f'<table:table-column table:style-name="{nome}"/>')
                self.colunas_extra.append((nome, larguras[i]))
            else:
                partes.append('<table:table-column table:style-name="Tab-cab.col"/>')

        # Celula com rowspan cobre as linhas de baixo: onde ela passa, entra
        # uma celula coberta, senao a tabela sai torta.
        cobertas: dict[int, int] = {}
        for linha in linhas:
            partes.append("<table:table-row>")
            col = 0
            fila = list(linha)
            while col < colunas:
                if cobertas.get(col, 0) > 0:
                    cobertas[col] -= 1
                    partes.append("<table:covered-table-cell/>")
                    col += 1
                    continue
                if fila:
                    conteudo, span, estilo_paragrafo = fila.pop(0)
                else:
                    conteudo, span, estilo_paragrafo = "", 1, "P-celula"
                atr = (f' table:number-rows-spanned="{span}"' if span > 1 else "")
                if span > 1:
                    cobertas[col] = span - 1
                partes.append(
                    f'<table:table-cell table:style-name="{estilo_cel}"{atr} '
                    'office:value-type="string">'
                    f'<text:p text:style-name="{estilo_paragrafo}">{conteudo}</text:p>'
                    "</table:table-cell>")
                col += 1
            partes.append("</table:table-row>")
        partes.append("</table:table>")
        self.saida.append("".join(partes))

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "table":
            self._fecha()
            self._na_tabela += 1
            self._linhas = []
            self._celulas = []
            self._tab_borda = str(d.get("border") or "").strip() in ("1", "true", "sim")
            self._tab_larguras = [c.strip() for c in (d.get("cols") or "").split(",")
                                  if c.strip()]
            return
        if self._na_tabela:
            # Dentro da tabela, bloco vira quebra de linha na propria celula:
            # um <p> ali nao pode virar paragrafo solto fora da tabela.
            if tag == "tr":
                self._celulas = []
            elif tag in ("td", "th"):
                self._buf.clear()
                classes = (d.get("class") or "").split()
                self._estilo_celula_atual = (
                    "P-celula-destaque" if "matricula-destaque" in classes
                    else "P-celula")
                try:
                    self._span_atual = max(1, int(d.get("rowspan") or 1))
                except ValueError:
                    self._span_atual = 1
            elif tag in self.BLOCO and self._buf:
                self._buf.append("<text:line-break/>")
            elif tag == "br":
                self._buf.append("<text:line-break/>")
            elif tag in self.NEGRITO:
                self._estilos.append("T-negrito")
                self._buf.append('<text:span text:style-name="T-negrito">')
            elif tag in self.ITALICO:
                self._estilos.append("T-italico")
                self._buf.append('<text:span text:style-name="T-italico">')
            elif tag in self.SUBLINHADO:
                self._estilos.append("T-sublinhado")
                self._buf.append('<text:span text:style-name="T-sublinhado">')
            elif tag in self.TACHADO:
                self._estilos.append("T-tachado-vermelho")
                self._buf.append('<text:span text:style-name="T-tachado-vermelho">')
            elif tag == "mark":
                estilo = self._estilo_do_mark(d)
                self._estilos.append(estilo)
                self._buf.append(f'<text:span text:style-name="{estilo}">')
            return

        if tag in self.BLOCO:
            self._fecha()
            # `<p>` SEM ATRIBUTO E O QUE O CODIGO DESTA CASA ESCREVE quando
            # quer uma linha em branco — sao 80 assim, em sete modulos. O
            # teor guardado escreve `<p lang="pt-BR" style="...">`, que e a
            # exportacao do editor do E-Oficio: 1.057 das 1.508 matriculas
            # ganhariam linha em branco por ali, e essa e pergunta para o
            # oficial, nao decisao minha. Ver o fecho de `</p>`, abaixo.
            self._p_sem_atributo = (tag == "p" and not attrs)
            classes = (d.get("class") or "").split()
            self._separa_ato = (tag == "p" and "separa-ato" in classes)
            self._ato_cab = (tag == "p" and "ato-cab" in classes)
            if "center" in (d.get("style") or "") or d.get("align") == "center":
                self._centro = True
        elif tag == "br":
            self._buf.append("<text:line-break/>")
        elif tag in self.NEGRITO:
            self._estilos.append("T-negrito")
            self._buf.append('<text:span text:style-name="T-negrito">')
        elif tag in self.ITALICO:
            self._estilos.append("T-italico")
            self._buf.append('<text:span text:style-name="T-italico">')
        elif tag in self.SUBLINHADO:
            self._estilos.append("T-sublinhado")
            self._buf.append('<text:span text:style-name="T-sublinhado">')
        elif tag in self.TACHADO:
            self._estilos.append("T-tachado-vermelho")
            self._buf.append('<text:span text:style-name="T-tachado-vermelho">')
        elif tag == "mark":
            estilo = self._estilo_do_mark(d)
            self._estilos.append(estilo)
            self._buf.append(f'<text:span text:style-name="{estilo}">')

    def handle_endtag(self, tag):
        if self._na_tabela and tag != "table":
            if tag in ("td", "th"):
                self._fecha_celula(self._span_atual)
                self._span_atual = 1
            elif tag == "tr":
                if self._buf:
                    self._fecha_celula(self._span_atual)
                    self._span_atual = 1
                self._linhas.append(self._celulas)
                self._celulas = []
            elif tag in self.NEGRITO | self.ITALICO | self.SUBLINHADO | self.TACHADO or tag == "mark":
                if self._estilos:
                    self._estilos.pop()
                    self._buf.append("</text:span>")
            return

        if tag in self.BLOCO:
            # `<p></p>` E UMA LINHA EM BRANCO, E ELA SUMIA ATE 31/08/2026.
            #
            # `_fecha` descarta o paragrafo cujo texto fica vazio depois do
            # `.strip()` — limpeza justa para HTML colado de fora, e perda
            # silenciosa para quem escreveu `<p></p>` no codigo querendo
            # espaco. Sao 80 desses em sete modulos que geram `.odt`, e
            # nenhum chegava ao papel.
            #
            # Achado medindo o relato #27 do oficial: «precisa de mais espaco
            # livre para desenvolver a assinatura». Aumentei o espaco da ficha
            # de tres linhas para cinco e o teste continuou dizendo ZERO —
            # **as tres nunca tinham saido**, e a linha de assinar ia colada
            # no rotulo.
            #
            # A MARCA E O FECHO DE `p`, E SO DELE. Fazer isto para todo BLOCO
            # poria uma linha solta em `<div><p>a</p></div>`: ali o `</div>`
            # chega com o buffer ja esvaziado pelo `</p>` e viraria um branco
            # que ninguem pediu.
            if tag == "p" and not self._buf and self._p_sem_atributo:
                self._linha_em_branco()
                self._centro = False
                self._p_sem_atributo = False
            else:
                self._p_sem_atributo = False
                self._fecha()
        elif tag in self.NEGRITO | self.ITALICO | self.SUBLINHADO | self.TACHADO or tag == "mark":
            if self._estilos:
                self._estilos.pop()
                self._buf.append("</text:span>")
        elif tag == "table":
            if self._buf:
                self._fecha_celula(self._span_atual)
            if self._celulas:
                self._linhas.append(self._celulas)
                self._celulas = []
            self._na_tabela = max(0, self._na_tabela - 1)
            self._emite_tabela()

    def handle_data(self, data):
        """Junta o texto preservando o espaco das bordas.

        A versao anterior colapsava o espaco e o descartava nas pontas. Como o
        modelo escreve <b>DENOMINAÇÃO: </b>{{ valor }}, o espaco morria dentro
        do negrito e saia "DENOMINAÇÃO:—.LOCALIZAÇÃO:". Aqui a borda vira um
        espaco simples, que e o que o texto corrido precisa.
        """
        if not data:
            return
        antes = data[:1].isspace()
        depois = data[-1:].isspace()
        texto = " ".join(data.split())

        def sem_espaco_ainda() -> bool:
            return bool(self._buf) and not self._buf[-1].endswith(" ")

        if not texto:
            if sem_espaco_ainda():
                self._buf.append(" ")
            return
        if antes and sem_espaco_ainda():
            self._buf.append(" ")
        self._buf.append(escape(texto))
        if depois:
            self._buf.append(" ")

    def resultado(self) -> str:
        for _ in self._estilos:
            self._buf.append("</text:span>")
        self._estilos.clear()
        self._fecha()
        return "\n".join(self.saida)


def html_para_odf(html: str | None, compacto: bool = False,
                  fragmentos: dict[str, str] | None = None) -> str:
    """`compacto` e para o cabecalho: mesma marcacao, corpo de letra menor.

    O cabecalho se repete em toda folha e concorre com o texto da matricula
    pelo espaco da pagina — a 12pt ele come um terco da primeira folha.

    `fragmentos` guarda pedacos que JA SAO ODF — o teor de cada ato e o quadro
    do selo. Eles nao podem passar por este conversor: ele le HTML, e diante de
    <table:table> ou <text:p> jogaria a marcacao fora e deixaria so as
    palavras. Era exatamente por isso que o selo saia sem a caixa. O modelo
    recebe uma marca no lugar, e a marca vira o fragmento no fim.
    """
    if not html:
        return ""
    p = _ParaOdf(compacto=compacto)
    p.feed(html)
    saida = p.resultado()
    # Larguras de coluna pedidas pelo modelo viram estilos automaticos. Ficam
    # em ESTILOS_EXTRA porque precisam existir tanto no content.xml quanto no
    # styles.xml — o cabecalho mora no segundo.
    for nome, largura in p.colunas_extra:
        ESTILOS_EXTRA.setdefault(
            nome,
            f'<style:style style:name="{nome}" style:family="table-column">'
            f'<style:table-column-properties style:column-width="{largura}"/>'
            "</style:style>")
    # 22/09/2026 — ficha RI: prenotação+ato no mesmo parágrafo ODF
    # Com 2+ carimbos o modelo entrega @@ODF1@@@@ODF2@@ no mesmo <p>.
    # O replace de um marcador sozinho nao casa; o residual mete
    # <table:table> dentro de <text:p> e o LibreOffice nao desenha.
    if fragmentos:
        _re_p_so_odfs = re.compile(
            r"(<text:p\b[^>]*>)(\s*(?:@@ODF\d+@@\s*)+)(</text:p>)",
            re.DOTALL,
        )

        def _expandir_p_so_odfs(m, frags=fragmentos):
            internos = re.findall(r"@@ODF\d+@@", m.group(2))
            if not internos:
                return m.group(0)
            partes = []
            for chave in internos:
                pedaco = frags.get(chave)
                if pedaco is None:
                    return m.group(0)
                partes.append(pedaco)
            return "".join(partes)

        saida = _re_p_so_odfs.sub(_expandir_p_so_odfs, saida)
    for chave, valor in (fragmentos or {}).items():
        # A marca sozinha num paragrafo: o paragrafo inteiro da lugar ao
        # fragmento, senao uma tabela ficaria dentro de um <text:p>, o que o
        # ODF nao admite.
        saida = re.sub(r'<text:p[^>]*>\s*' + re.escape(chave) + r'\s*</text:p>',
                       lambda _m, v=valor: v, saida)
        saida = saida.replace(chave, valor)
    return saida


# ------------------------------------- a linha que separa um ato do outro
#
# Pedido do oficial em 31/08/2026: «espaço não é suficiente para separar um
# ato e outro, deve ter uma linha traçada entre eles». Eu havia perguntado se
# a certidão devia trazer de volta as linhas EM BRANCO que o E-Ofício guardou
# no teor; ele respondeu com o requisito de verdade — SEPARAR — e disse que o
# meio que eu propus não cumpre. E não cumpre: branco some quando a folha
# vira, e não distingue «fim do ato» de «parágrafo novo dentro do mesmo ato».
SEPARADOR_DE_ATO = '<text:p text:style-name="P-separa-ato"/>'

# No HTML da certidão: borda CSS em 100% da largura útil (Beatriz
# 24/09/2026). Traçinhos (`----`) só iam até a metade da página.
# `html_para_odf` converte isto (e qualquer parágrafo só de riscas)
# no `SEPARADOR_DE_ATO` de borda ODF.
SEPARADOR_DE_ATO_HTML = (
    '<p class="separa-ato" style="border-bottom:0.06cm double #000;'
    'margin:0.12cm 0;padding:0;line-height:0;font-size:0;">&nbsp;</p>'
)

_PARAGRAFO = re.compile(r"<text:p[^>]*/>|<text:p[^>]*>.*?</text:p>", re.S)

# A LINHA QUE O DIGITADOR DESENHOU A MAO — um paragrafo so de tracinhos.
#
# Medido em 31/08/2026: **176 fichas ja trazem 405 dessas**, e e o achado que
# valida o pedido do oficial. Ele nao pediu coisa nova: pediu de volta o que
# esta casa fazia, e que se perdeu quando o teor virou texto corrido.
#
# Onde ela ja esta, a do sistema cede a vez — duas riscas seguidas ficam pior
# que nenhuma, e seriam 93 casos.
_JA_E_UMA_RISCA = re.compile(r"^[-_\u2013\u2014.\s]{8,}$")


def _so_digitos_de(v) -> str:
    return "".join(c for c in str(v or "") if c.isdigit()).lstrip("0")


def separar_atos(corpo_odf: str, numero_da_matricula) -> str:
    """Desenha uma LINHA entre um ato e o seguinte, no ODF já convertido.

    ONDE COMEÇA CADA ATO NÃO SE ADIVINHA. A régua é **importada** de
    `ri_numeros_do_teor.ROTULO`, medida em 28/08/2026: ela exige a **barra** e
    o número desta matrícula depois dela. O teor antigo cita atos de OUTRAS
    matrículas o tempo todo — «Transcrita no Lº 2-C, fls. 16 sob nº R-1/503» —
    e uma linha ali cortaria a ficha no meio de uma frase. Copiar o padrão
    para cá seria a `normalizar_nome` pela quarta vez: duas cópias divergem no
    primeiro conserto.

    E HÁ UM SEGUNDO GUARDA, próprio daqui: o rótulo tem de **abrir o
    parágrafo**. Citação no meio de frase não abre ato — e é exatamente assim
    que o teor antigo cita os das outras fichas.

    NÃO VAI LINHA ANTES DO PRIMEIRO. Separador serve para separar dois; um
    traço antes do primeiro ato seria régua debaixo do cabeçalho.

    E ELA NÃO ENTRA NO TEOR — só no papel. A certidão congela o corpo com
    sha256, e gravar o separador lá dentro mudaria o teor certificado. Como
    ela se desenha na impressão, **as certidões já emitidas ganham a linha ao
    serem reimpressas sem uma letra do teor mudar**.

    Substitui NO LUGAR, com `re.sub`: o que não é parágrafo — tabela, quadro
    do selo, fragmento — continua exatamente onde estava.
    """
    meu = _so_digitos_de(numero_da_matricula)
    if not meu or not corpo_odf:
        return corpo_odf or ""

    from ri_numeros_do_teor import ROTULO

    ja_houve = [False]
    anterior = [""]
    anterior_era_risca = [False]

    def marcar(achado: "re.Match") -> str:
        bruto = achado.group(0)
        # O texto VISÍVEL do parágrafo, sem as marcas: um `<text:span>` no
        # meio de `AV-2/3.231` quebraria o padrão se ele fosse procurado no
        # ODF cru.
        visivel = " ".join(re.sub(r"<[^>]+>", " ", bruto).split())
        saida = bruto
        abre = ROTULO.match(visivel)
        if abre and _so_digitos_de(abre.group(3)) == meu:
            # Não se desenha risca em cima de risca: onde o digitador já fez a
            # dele, a do sistema cede a vez. Seriam 93 casos de linha dupla.
            if ja_houve[0] and not anterior_era_risca[0]:
                saida = SEPARADOR_DE_ATO + bruto
            ja_houve[0] = True
        # Risca já desenhada (traços do digitador OU P-separa-ato
        # vindo do HTML): a próxima não empilha outra em cima.
        anterior_era_risca[0] = bool(
            _JA_E_UMA_RISCA.match(visivel)
            or 'text:style-name="P-separa-ato"' in bruto)
        anterior[0] = visivel
        return saida

    return _PARAGRAFO.sub(marcar, corpo_odf)


def texto_para_odf(texto: str | None) -> str:
    """Texto puro: cada linha vira um paragrafo, linha vazia vira espaco."""
    if not texto:
        return ""
    linhas = []
    for linha in texto.splitlines():
        linha = linha.strip()
        linhas.append(
            f'<text:p text:style-name="P-just">{escape(linha)}</text:p>' if linha
            else '<text:p text:style-name="P-just"/>'
        )
    return "\n".join(linhas)



def miolo_html_do_documento(html: str | None) -> str:
    """Extrai o miolo de documento XHTML/TX Text Control (e-Oficio).

    Teor de acervo chega como documento completo (`<?xml>`, `<html>`,
    `<head>`, `<body>`). Na certidao/ficha o envelope vira lixo tipografico
    e faz `html_em_texto_corrido` tratar o wrapper como bloco "outro",
    empurrando risca de ato indevida (Beatriz 29/09/2026, mat. 2005).
    Mesma ideia de `ri_web.teor_seguro` (`_CORPO`), centralizada aqui para
    o papel (certidao + ODT) tambem descascar.
    """
    if not html:
        return ""
    m = re.search(r"(?is)<body[^>]*>(.*)</body>", html)
    if m:
        return m.group(1)
    baixo = html.lower()
    if "<?xml" in baixo or "<html" in baixo:
        s = re.sub(r"(?is)<\?xml[^>]*\?>", "", html)
        s = re.sub(r"(?is)<head[^>]*>.*?</head>", "", s)
        s = re.sub(r"(?is)</?(?:html|body)(?:\s[^>]*)?>", "", s)
        return s
    return html


def html_em_texto_corrido(html: str | None,
                          numero_da_matricula=None) -> str:
    """Teor HTML em texto corrido (certidao RI).

    Antes, descasca envelope XHTML/TX25 via `miolo_html_do_documento`.

    Teor de acervo OCR chega com um ``<p>`` por linha da digitalizacao;
    na certidao isso vira espacamento excessivo ("certidao toda
    desordenada" — Beatriz 24/09/2026, mat. 4001). Junta o conteudo dos
    ``<p>`` consecutivos com espaco, preservando marcas internas
    (``<b>``/``<i>``), e so quebra paragrafo quando:

    - o ``<p>`` esta vazio (linha em branco pedida); ou
    - o texto visivel **abre** com o rotulo de um ato desta matricula
      (``AV-01/4.001``, ``R-1/1306``…), para a linha entre atos continuar
      existindo no papel (`separar_atos` no ODT).

    Blocos que nao sao ``<p>`` simples (tabelas, carimbos em ``<div>``)
    passam intactos e fecham o paragrafo corrido corrente.
    """
    if not html:
        return ""
    html = miolo_html_do_documento(html)
    if not html:
        return ""
    from html import unescape as _unescape
    from ri_numeros_do_teor import ROTULO

    meu = _so_digitos_de(numero_da_matricula) if numero_da_matricula is not None else ""

    # Captura cada <p>...</p> (incluindo vazio) e o que sobra entre eles.
    _P = re.compile(r"(?is)(<p(?:\s[^>]*)?>\s*</p\s*>|<p(?:\s[^>]*)?>.*?</p\s*>)")

    unidades: list[tuple[str, str]] = []
    pos = 0
    for m in _P.finditer(html):
        if m.start() > pos:
            unidades.append(("outro", html[pos:m.start()]))
        unidades.append(("p", m.group(1)))
        pos = m.end()
    if pos < len(html):
        unidades.append(("outro", html[pos:]))

    def _visivel(p_html: str) -> str:
        miolo = re.sub(r"(?is)^<p(?:\s[^>]*)?>|</p\s*>$", "", p_html)
        return " ".join(_unescape(re.sub(r"(?is)<[^>]+>", " ", miolo)).split())

    def _miolo(p_html: str) -> str:
        m = re.match(r"(?is)^<p(?:\s[^>]*)?>(.*)</p\s*>$", p_html)
        return (m.group(1) if m else "").strip()

    def _abre_ato(vis: str) -> bool:
        if not meu or not vis:
            return False
        abre = ROTULO.match(vis)
        return bool(abre and _so_digitos_de(abre.group(3)) == meu)

    saida: list[str] = []
    acc: list[str] = []

    def flush():
        nonlocal acc
        if not acc:
            return
        saida.append("<p>" + " ".join(acc) + "</p>")
        acc = []

    for tipo, ped in unidades:
        if tipo != "p":
            # Espaco/newline entre </p> e <p> NAO fecha o paragrafo corrido.
            if not (ped or "").strip():
                continue
            flush()
            saida.append(ped)
            continue
        vis = _visivel(ped)
        miolo = _miolo(ped)
        if not vis:
            flush()
            if saida and saida[-1] != "<p></p>":
                saida.append("<p></p>")
            continue
        if _abre_ato(vis):
            flush()
            if saida:
                saida.append(SEPARADOR_DE_ATO_HTML)
            acc.append(miolo)
            continue
        acc.append(miolo)
    flush()
    return "".join(saida)


def texto_para_html(texto: str | None) -> str:
    """Texto puro em paragrafos HTML.

    Contraparte de `texto_para_odf`, para quem monta HTML e nao ODF. A certidao
    e o caso: ela GRAVA o corpo renderizado no banco, em HTML, para congelar o
    teor da emissao. Passar-lhe ODF punha `<text:p text:style-name="P-just">`
    no meio da certidao — foi o que saiu impresso na certidao 6/2026.
    """
    if not texto:
        return ""
    saida = []
    for linha in texto.splitlines():
        linha = linha.strip()
        saida.append(f"<p>{escape(linha)}</p>" if linha else "<p></p>")
    return "\n".join(saida)


def bloco_selo_html(selo_texto: str | None, emolumentos: str | None = None) -> str:
    """O quadro do selo em HTML, um paragrafo por selo.

    Sem imagem: o QR e embutido no .odt como arquivo, e no corpo gravado em
    banco nao ha onde pendurar imagem sem inflar o banco com base64.

    **A RELACAO DE EMOLUMENTOS PODE CONSTAR NO CARIMBO** - pedido do oficial
    em 15/09/2026. Espelha o RCPJ (`selo_no_papel.linha_de_valores`): o que
    o aparelho declarou (Total/Emol/FERC/...) sai na linha do carimbo, e nao
    so no fecho do teor. Se o selo nao declara valores, a linha nao aparece.
    """
    if not selo_texto and not emolumentos:
        return ""
    selos = separar_selos(selo_texto)
    if emolumentos and selos:
        selos[-1] = f"{selos[-1]} - {emolumentos}"
    elif emolumentos:
        selos = [str(emolumentos)]
    if not selos:
        return ""
    # Relacao no carimbo (mesma regua do RCPJ).
    try:
        from ri_lavrar_teor import valores_para_o_carimbo
        valores = valores_para_o_carimbo(selo_texto)
    except Exception:  # noqa: BLE001
        valores = ""
    partes = []
    for s in selos:
        partes.append(f"<p><small>{escape(' '.join(str(s).split()))}</small></p>")
    if valores:
        partes.append(
            f'<p class="selo-valores"><small><strong>Emolumentos:</strong> '
            f"{escape(valores)}</small></p>")
    return "".join(partes)


def ato_sem_espaco_antes_do_fecho(odf: str) -> str:
    """Zera somente a margem inferior do último parágrafo do teor do ato."""
    encontrados = list(re.finditer(
        r'<text:p text:style-name="P-(?:just|centro)"', odf or ""))
    if not encontrados:
        return odf
    ultimo = encontrados[-1]
    return (odf[:ultimo.start()] + '<text:p text:style-name="P-ato-final"'
            + odf[ultimo.end():])


def anexar_fecho_ao_ato(odf: str, fecho: str | None) -> str:
    """Põe o fecho após o ponto final, dentro do último parágrafo do ato."""
    ajustado = ato_sem_espaco_antes_do_fecho(odf)
    if not fecho:
        return ajustado
    fim = ajustado.rfind("</text:p>")
    texto = escape(" ".join(str(fecho).split()))
    if fim < 0:
        return f'<text:p text:style-name="P-ato-final">{texto}</text:p>'
    return ajustado[:fim] + " " + texto + ajustado[fim:]


def partes_do_carimbo(selo_texto, rotulo: str = "SELO DIGITAL DO TJMA", *,
                      feitio: str = "ato") -> dict:
    """O CONTEUDO de um carimbo, sem forma nenhuma. So calcula.

    **UMA FONTE PARA OS TRES PAPEIS** — ordem do oficial em 15/09/2026: «preze
    por esse modelo tanto no html como no odt e pdf, exatamente assim em
    todos». O que muda entre a tela e o livro e como se desenha; **o que se
    diz e um so**, e mora aqui. Duas montagens divergiriam no primeiro
    conserto, e a tela passaria a mostrar um carimbo e o papel a imprimir
    outro — que e a `normalizar_nome` pela quinta vez.

    O PDF NAO ENTRA NA CONTA porque ele nasce do `.odt`: quem converte e o
    LibreOffice. Sao dois desenhos, e nao tres.

    Devolve `{"rotulo", "numero", "linhas", "qr_texto", "texto"}`. `linhas`
    ja vem na ordem em que se le: numero, ato e data, valores. `texto` e a
    etiqueta crua daquele selo, para quem precisar ler de novo o carimbo
    congelado (`carimbos_do_html_para_odf`).

    A LINHA UNICA DE 16/09 (`linha` e `_numa_linha_so`) FOI APAGADA em
    14/10/2026 — o unico leitor dela era a tela do livro, e era ela que fazia
    a tela dizer `Emol 120,03` onde o papel dizia `Emol R$ 120,03`. Quem
    decide o que o carimbo escreve, nos dois desenhos, e `linhas_desenhadas`.
    """
    texto = str(selo_texto or "").strip()
    if not texto:
        return {"rotulo": rotulo, "numero": "", "linhas": [], "qr_texto": ""}
    try:
        import selo_no_papel as SNP
        lido = SNP.ler(texto) or {}
    except Exception:                                        # noqa: BLE001
        SNP, lido = None, {}

    numero = str(lido.get("codigo") or "").strip()
    if not numero:
        # Etiqueta que o leitor nao reconheceu: melhor o texto cru do que um
        # carimbo vazio — quem le percebe que ela esta fora de forma.
        numero = " ".join(texto.split())[:52]

    # **O QUE SE DIZ MORA EM `selo_no_papel`** — 17/09/2026. Ate aqui as
    # linhas eram montadas nesta funcao, e o molde `.odt` do RCPN montava as
    # dele por marcadores `@`: duas montagens do mesmo carimbo, que
    # divergiriam no primeiro conserto — e a divergencia seria entre dois
    # papeis assinados que falam do mesmo selo.
    linhas = ([numero] if SNP is None
              else SNP.linhas_do_carimbo(texto, numero, feitio))

    try:
        qr_texto = (SNP.link_de_consulta(numero, texto) if SNP is not None
                    else "")
    except Exception:                                        # noqa: BLE001
        qr_texto = ""
    return {"rotulo": rotulo, "numero": numero, "linhas": linhas,
            "qr_texto": qr_texto, "texto": texto}


def linhas_desenhadas(partes: dict, larga: bool = True) -> list[str]:
    """O que o carimbo ESCREVE, linha a linha — nos dois desenhos. So calcula.

    QR EM TODOS OS SELOS, INCLUSIVE NO LIVRO — ordem da corregedoria trazida
    pelo oficial em 24/09/2026. A tela e o papel do livro chegaram a dizer
    coisas diferentes do mesmo selo porque cada desenho decidia as suas
    linhas e o seu link; agora `_uma_celula_de_carimbo` (o papel) e
    `carimbo_compacto_html` (a tela) pedem a esta funcao, e so desenham.

    As linhas sao as de `partes_do_carimbo`, e o link da consulta daquele
    selo vem por ultimo. «CONFIRA EM» SO ONDE CABE, e isto e medido a 5,5 pt:
    o endereco sozinho mede 5,97 cm e cabe na coluna de meia largura (6,25
    cm); com a palavra na frente vai a 6,97 cm e quebra em duas linhas. No
    carimbo largo (certidao, livro, tela) ela entra.
    """
    linhas = [str(x) for x in (partes.get("linhas") or []) if str(x).strip()]
    if partes.get("qr_texto"):
        linhas.append(f'Confira em {partes["qr_texto"]}' if larga
                      else partes["qr_texto"])
    return linhas


def carimbos_do_ato(selo_texto, rotulo: str = "SELO DIGITAL DO TJMA", *,
                    feitio: str = "ato") -> list[dict]:
    """Um `partes_do_carimbo` por selo do ato, ja rotulados. So calcula.

    Com mais de um selo o rotulo numera — `SELO 1`, `SELO 2` —, porque «SELO
    DE AVERBACAO» duas vezes lado a lado nao diz qual e qual.
    """
    texto = str(selo_texto or "").strip()
    if not texto:
        return []
    selos = separar_selos(texto) or [texto]
    return [partes_do_carimbo(
        selo, rotulo if len(selos) == 1 else f"{rotulo} {i + 1}",
        feitio=feitio)
        for i, selo in enumerate(selos)]


def _uma_celula_de_carimbo(partes: dict, imagem_nome,
                           larga: bool = False) -> str:
    """O conteudo de UM carimbo no ODF: QR a esquerda, texto ao lado.

    **Nao decide o que dizer** — isso e de `partes_do_carimbo`, que serve este
    desenho e o do HTML. Aqui so se escolhe onde cada coisa fica no papel.
    """
    # O ENDERECO DA CONSULTA SAI ESCRITO, ao lado do QR — pedido do oficial
    # em 16/09/2026: «preciso que o carimbo da certidao saia completo com qr
    # code, link, emolumentos».
    #
    #   `partes_do_carimbo` JA O CALCULAVA e nenhum papel o imprimia: quem
    #   recebe a certidao e nao tem camera a mao ficava sem como conferir o
    #   selo. Medido: o endereco tem 59 caracteres e a coluna do texto tem
    #   cerca de 6,3 cm — a 5,5 pt ele cabe numa linha.
    #
    #   **E ELE VAI AO LIVRO desde 24/09/2026** (ordem da corregedoria: «qr
    #   code em todos os selos»): `carimbo_compacto_odf` passa por aqui com
    #   `larga=True`. O que se escreve vem de `linhas_desenhadas`, a mesma
    #   funcao que a tela pede.
    linhas = linhas_desenhadas(partes, larga=larga)
    corpo = (f'<text:p text:style-name="P-selo-rotulo">'
             f'{escape(partes["rotulo"])}</text:p>'
             + "".join(f'<text:p text:style-name="P-selo-compacto">'
                       f'{escape(l)}</text:p>' for l in linhas))

    # O QR PEQUENO — 1,3 cm. No RTDPJ mediu-se que 15 mm le tranquilo num
    # celular a poucos centimetros; aqui ele divide a metade com o texto, e
    # 1,3 cm mantem a leitura sem empurrar a linha de valores para baixo.
    qr = ""
    if imagem_nome:
        qr = ('<draw:frame draw:style-name="Fr-qr" text:anchor-type="as-char" '
              'svg:width="1.3cm" svg:height="1.3cm">'
              f'<draw:image xlink:href="Pictures/{imagem_nome}" '
              'xlink:type="simple" xlink:show="embed" '
              'xlink:actuate="onLoad"/></draw:frame>')

    # A LARGURA INTEIRA E DA CERTIDAO, e a razao e medida: a linha de
    # valores mede 9,61 cm e o link 6,97 cm a 5,5 pt, contra 6,25 cm da coluna
    # de meia largura. Ver `carimbo_do_selo_odf`.
    return (
        '<table:table table:name="SeloInterno" '
        f'table:style-name="Tab-selo-interno{"-largo" if larga else ""}">'
        '<table:table-column table:style-name="Col-selo-qr"/>'
        '<table:table-column table:style-name="Col-selo-texto'
        f'{"-larga" if larga else ""}"/>'
        '<table:table-row>'
        '<table:table-cell table:style-name="Cel-selo-interna" '
        'office:value-type="string">'
        f'<text:p text:style-name="P-selo-compacto">{qr}</text:p>'
        '</table:table-cell>'
        '<table:table-cell table:style-name="Cel-selo-interna" '
        f'office:value-type="string">{corpo}</table:table-cell>'
        '</table:table-row></table:table>')


def carimbo_do_selo_odf(selo_texto, imagem_nome=None, *,
                        rotulo: str = "SELO DIGITAL DO TJMA",
                        feitio: str = "ato",
                        por_fileira: int = 2) -> str:
    """Os carimbos do ato, DOIS POR FILEIRA. So monta o ODF.

    PEDIDO DO OFICIAL EM 15/09/2026, em duas partes. Primeiro: «Carimbo do selo
    deve ter informacoes de emolumentos, numero do selo e qr code, como nas
    outras atribuicoes» — o modelo e o do RTD/RCPJ, que ele aprovou no mesmo
    dia: rotulo, QR, numero e linha de valores, cada coisa na sua linha, e
    **nao** a frase corrida de trezentos caracteres do aparelho.

    Depois: «da pra deixar o selo mais compacto, com qrcode e texto ocupando um
    lado, e deixando o outro para o segundo selo. eventual terceiro carimbo
    iria na fileira de baixo». Entao cada carimbo ocupa **metade** da largura,
    e o terceiro desce sozinho — a grade e de 8 cm + 8 cm, e dentro de cada
    metade ha uma segunda grade com o QR a esquerda e o texto ao lado.

    E «NAO EH PRA TER ESPACO SOBRANDO PRA FALSIFICAR E INSERIR TEXTO NO MEIO»:
    as margens do quadro sao 0,02 cm em cima e 0,04 embaixo, e os paragrafos
    de dentro nao tem margem nenhuma. **Espaco em branco num livro de registro
    nao e estetica: e onde cabe uma linha que ninguem lavrou.**

    QUANDO SOBRA UMA METADE, ela sai **sem borda** — uma caixa vazia ao lado
    do selo pareceria um segundo selo que faltou, e e justamente o contrario
    do que se quer mostrar.

    POR QUE NAO SE MEXEU EM `bloco_selo_odf`: ela serve Notas, a certidao de
    inteiro teor do RCPN e o Livro 3. Trocar o carimbo de tres atribuicoes que
    ninguem pediu para trocar seria o conserto certo pelo motivo errado.
    """
    partes = carimbos_do_ato(selo_texto, rotulo, feitio=feitio)
    if not partes:
        return ""
    quantos = 1 if int(por_fileira or 2) <= 1 else 2
    imagens = (list(imagem_nome) if isinstance(imagem_nome, (list, tuple))
               else [imagem_nome])
    celulas = [_uma_celula_de_carimbo(
        pe, imagens[i] if i < len(imagens) else None, larga=(quantos == 1))
        for i, pe in enumerate(partes)]

    colunas = ('<table:table-column table:style-name="Col-selo-inteiro"/>'
               if quantos == 1 else
               '<table:table-column table:style-name="Col-selo-compacto"/>'
               '<table:table-column table:style-name="Col-selo-compacto"/>')
    saida = ['<table:table table:name="CarimboDoSelo" '
             'table:style-name="Tab-selos-compactos">' + colunas]
    for inicio in range(0, len(celulas), quantos):
        saida.append('<table:table-row>')
        fileira = celulas[inicio:inicio + quantos]
        for dentro in fileira:
            saida.append('<table:table-cell table:style-name="Cel-selo-compacto" '
                         f'office:value-type="string">{dentro}</table:table-cell>')
        if len(fileira) < quantos:
            # A metade que sobra fica INVISIVEL: caixa vazia ao lado do selo
            # pareceria um segundo selo que faltou colar.
            saida.append('<table:table-cell table:style-name="Cel-selo-interna" '
                         'office:value-type="string"><text:p '
                         'text:style-name="P-selo-compacto"/></table:table-cell>')
        saida.append('</table:table-row>')
    saida.append('</table:table>')
    return "".join(saida)


# O DESENHO DE TELA DO CARIMBO GRANDE SAIU EM 16/09/2026, e ele se chamava
# `carimbo_do_selo_html`. O gemeo de PAPEL (`carimbo_do_selo_odf`) continua
# vivo — imprime a certidao do RI, a do RCPN, o traslado das Notas e a ficha
# da digitalizacao —, mas o de TELA servia uma tela so, a do livro, e ela
# em 22/09/2026 o carimbo compacto voltou a levar QR (pedido da substituta),
# mantendo numero e emolumentos; a tela e o papel leem a mesma fonte.
#
#   NAO SE GUARDA FUNCAO «PARA O CASO DE»: nesta casa a peca pronta que
#   ninguem chama ja foi religada cinco vezes sem ninguem saber por que
#   existia. Se um dia uma tela precisar mostrar o carimbo grande, ela nasce
#   do mesmo `carimbos_do_ato`, que e a fonte do conteudo e nao mudou.




def sem_espaco_de_assinatura_da_ficha(texto: str | None) -> str:
    """Compat: só remove traços; mantém nome (delega ao helper)."""
    return sem_linha_de_assinatura_a_mao(texto)


def carimbos_do_html_para_odf(html: str) -> tuple[str, dict[str, str], dict]:
    """Troca carimbos HTML / etiquetas TX25 pelo ODF do carimbo da ficha.

    Na certidão o teor fica congelado em HTML (com `carimbo_compacto_html`).
    Na impressão, `html_para_odf` derrubava a caixa e o QR e deixava só
    parágrafos. Aqui cada carimbo vira o mesmo `carimbo_compacto_odf` da
    ficha, com imagem no pacote — pedido 22/09/2026: mesma estrutura da ficha.

    HOTFIX-2026-09-29-08 — etiquetas TX25 selo → carimbo lado a lado:
    o teor ACERVO (TX25/Word) traz selos numa tabela de 2 colunas (etiqueta
    MATRIC | PRENOT). O conversor achatava isso em Tab1+Tab2 empilhados.
    Detectamos a tabela-etiqueta TJMA e trocamos pelo carimbo compacto da
    casa, lado a lado (`por_fileira=2`), com QR. Sem resealar.
    """
    import re as _re
    if not html:
        return "", {}, {}

    fragmentos: dict[str, str] = {}
    imagens: dict = {}
    n = [0]

    def _chave() -> str:
        n[0] += 1
        return f"@@CARIMBO_CERT_{n[0]}@@"

    # 1) Tabelas-etiqueta TX25 (Poder Judiciário + "Selo: CODIGO")
    _re_selo_code = _re.compile(
        r"Selo:\s*([A-Z]{5,7}\d{6}[A-Z0-9]{10,25})", _re.I)

    def _tabelas_externas(texto: str):
        low = texto.lower()
        i = 0
        while True:
            t0 = low.find("<table", i)
            if t0 < 0:
                return
            depth = 0
            j = t0
            while j < len(texto):
                if low.startswith("<table", j):
                    depth += 1
                    j += 6
                    continue
                if low.startswith("</table>", j):
                    depth -= 1
                    j += 8
                    if depth == 0:
                        yield t0, j, texto[t0:j]
                        i = j
                        break
                    continue
                j += 1
            else:
                return

    partes_tx: list[str] = []
    ultimo = 0
    for t0, t1, bloco in _tabelas_externas(html):
        codes = _re_selo_code.findall(bloco)
        if not codes:
            continue
        if "Poder Judici" not in bloco and "TJMA" not in bloco:
            continue
        partes_tx.append(html[ultimo:t0])
        chave = _chave()
        texto_selos = "\n".join(codes)
        nomes: list = []
        for code in codes:
            png = png_do_qr_do_selo(code)
            if not png:
                nomes.append(None)
                continue
            nome = f"qr-cert-tx25-{code}.png"
            k = 2
            while nome in imagens:
                nome = f"qr-cert-tx25-{code}-{k}.png"
                k += 1
            imagens[nome] = (png, "image/png")
            nomes.append(nome)
        fragmentos[chave] = carimbo_do_selo_odf(
            texto_selos, nomes, rotulo="SELO DIGITAL DO TJMA",
            feitio="ato", por_fileira=2)
        partes_tx.append(f"<p>{chave}</p>")
        ultimo = t1
    partes_tx.append(html[ultimo:])
    html = "".join(partes_tx)

    # 2) carimbo-com-qr (fluxo já existente desde 22/09/2026)
    padrao = _re.compile(
        r'<div class="carimbo-com-qr\b[^"]*"[^>]*>.*?</div>\s*</div>',
        _re.I | _re.S,
    )
    partes: list[str] = []
    ultimo = 0
    for m in padrao.finditer(html):
        partes.append(html[ultimo:m.start()])
        bloco = m.group(0)
        rotulo = "SELO DIGITAL DO TJMA"
        rm = _re.search(r"<b>([^<]+)</b>", bloco, _re.I)
        if rm:
            rotulo = rm.group(1).strip()
        texto = ""
        # Desde 14/10/2026 a tela escreve o carimbo em LINHAS (as mesmas do
        # papel) e guarda a etiqueta crua do selo em `data-etiqueta`: relê-la
        # devolve o carimbo inteiro, e não só a primeira linha (o número).
        dm = _re.search(r'data-etiqueta="([^"]*)"', bloco)
        if dm:
            import html as _html
            texto = _html.unescape(dm.group(1)).strip()
        tm = None if texto else _re.search(
            r"</b></div>\s*<div>([^<]+)</div>", bloco, _re.I)
        if tm:
            texto = tm.group(1).strip()
        if not texto:
            sm = _re.search(r"[?&]selo=([A-Za-z0-9]+)", bloco)
            if sm:
                texto = sm.group(1)
        if not texto:
            # não reconheceu — deixa o HTML seguir o conversor comum
            partes.append(bloco)
            ultimo = m.end()
            continue
        chave = _chave()
        frag = carimbo_compacto_odf(
            texto, rotulo=rotulo, imagens=imagens,
            prefixo_qr=f"qr-cert-{n[0]}")
        fragmentos[chave] = frag
        # marca sozinha num <p> para o html_para_odf trocar o parágrafo inteiro
        partes.append(f"<p>{chave}</p>")
        ultimo = m.end()
    partes.append(html[ultimo:])
    return "".join(partes), fragmentos, imagens


def carimbo_compacto_odf(selo_texto,
                         rotulo: str = "SELO DIGITAL DO TJMA",
                         imagens: dict | None = None,
                         prefixo_qr: str = "qr-ato") -> str:
    """Carimbo do ato COM número, emolumentos, link e QR (quando houver imagem).

    PEDIDO DA SUBSTITUTA EM 22/09/2026: em todos os atos de todas as
    atribuições devem aparecer o número do selo, os emolumentos e o QR code.

    Em 16/09/2026 o livro havia ficado em uma linha sem QR (ordem do oficial
    sobre o livro físico na estante). A regra de agora vale para o carimbo
    do ATO na tela e no papel: volta o QR, mantendo número e valores.

    Se `imagens` for um dict, grava nele os PNG do QR (`nome -> (bytes, mime)`)
    para o chamador entregar ao `gerar_odt`. Sem esse dict o carimbo ainda
    sai completo (número, valores e link escritos); só o desenho do QR fica
    de fora, porque o `.odt` é um zip e a imagem precisa entrar no pacote.
    """
    texto = str(selo_texto or "").strip()
    if not texto:
        return ""
    nomes: list = []
    if imagens is not None:
        # 23/09/2026 — QR unico por selo no pacote ODT (Beatriz, mat. 582).
        # Prenotacao + ato + arquivamento compartilham o mesmo `imagens` e
        # o mesmo prefixo `qr-ato`. Numerar so por `i` (1, 2…) em CADA chamada
        # fazia todas gravarem `qr-ato-1.png` e sobrescrever o PNG: no papel
        # os tres carimbos apontavam para o QR do ultimo selo. A tela nao
        # sofria (data-URI). Nomeia pelo numero do selo (28 chars).
        for i, pe in enumerate(carimbos_do_ato(texto, rotulo, feitio="ato"),
                               start=1):
            png = png_do_qr_do_selo(pe.get("numero"))
            if not png:
                nomes.append(None)
                continue
            codigo = "".join(
                ch for ch in str(pe.get("numero") or "") if ch.isalnum())
            base = codigo or str(i)
            nome = f"{prefixo_qr}-{base}.png"
            n = 2
            while nome in imagens:
                nome = f"{prefixo_qr}-{base}-{n}.png"
                n += 1
            imagens[nome] = (png, "image/png")
            nomes.append(nome)
    return carimbo_do_selo_odf(
        texto, nomes or None, rotulo=rotulo, feitio="ato", por_fileira=1)


def carimbo_compacto_html(selo_texto,
                          rotulo: str = "SELO DIGITAL DO TJMA") -> str:
    """O mesmo carimbo do papel, na tela: número, emolumentos e QR.

    PEDIDO DA SUBSTITUTA EM 22/09/2026 — religar o QR em todos os atos.
    O conteúdo vem de `partes_do_carimbo` / `carimbos_do_ato` (fonte única);
    aqui só se desenha, com o PNG do QR em data-URI quando o `segno` estiver
    disponível.

    O QUE SE ESCREVE É `linhas_desenhadas`, A MESMA DO PAPEL — 14/10/2026.
    Até aqui a tela escrevia a linha única de 16/09 (`Emol 120,03`, sem o R$
    nos fundos, e o endereço solto), enquanto o papel do livro já saía nas
    linhas completas com «Confira em …»: dois desenhos dizendo coisas
    diferentes do mesmo selo. A etiqueta crua vai em `data-etiqueta`, para a
    certidão que congela este HTML poder relê-lo inteiro na impressão.
    """
    import base64
    partes = carimbos_do_ato(selo_texto, rotulo, feitio="ato")
    if not partes:
        return ""
    caixas = []
    for pe in partes:
        png = png_do_qr_do_selo(pe.get("numero"))
        img = ""
        if png:
            b64 = base64.b64encode(png).decode("ascii")
            img = (f'<img class="carimbo-qr" alt="QR do selo" width="56" height="56" '
                   f'src="data:image/png;base64,{b64}"/>')
        linhas = linhas_desenhadas(pe, larga=True)
        link = ""
        if pe.get("qr_texto") and linhas:
            link = (f'<div class="carimbo-link muted small">'
                    f'{escape(linhas.pop())}</div>')
        etiqueta = escape(str(pe.get("texto") or ""), {'"': "&quot;"})
        caixas.append(
            '<div class="carimbo-com-qr" '
            f'data-etiqueta="{etiqueta}" style="display:flex;gap:10px;'
            'align-items:flex-start;margin:6px 0;padding:6px;'
            'border:1px solid #ccc;border-radius:4px">'
            f'{img}'
            '<div class="carimbo-texto" style="flex:1;min-width:0">'
            f'<div><b>{escape(pe["rotulo"])}</b></div>'
            + "".join(f'<div>{escape(l)}</div>' for l in linhas)
            + f'{link}'
            '</div></div>')
    return "".join(caixas)


def bloco_selo_odf(selo_texto: str | None, imagem_nome: str | list[str | None] | tuple[str | None, ...] | None = None,
                  emolumentos: str | None = None) -> str:
    """Monta o quadro do selo digital do TJMA, com o QR Code quando houver.

    O selo e colado pelo usuario tal como o sistema do tribunal entrega; aqui
    ele apenas e reproduzido na ficha, sem reformatacao, para nao alterar o
    que foi selado.
    """
    imagens = list(imagem_nome) if isinstance(imagem_nome, (list, tuple)) else [imagem_nome]
    if not (selo_texto or any(imagens)):
        return ""

    selos = separar_selos(selo_texto)
    if emolumentos and selos:
        selos[-1] = f"{selos[-1]} — {emolumentos}"
    elif emolumentos:
        selos = [str(emolumentos)]
    if not selos:
        # Campo so com espacos: nao vale uma caixa vazia na ficha.
        return ""

    # Relacao de emolumentos no carimbo (RCPJ / selo_no_papel).
    try:
        from ri_lavrar_teor import valores_para_o_carimbo
        _valores_carimbo = valores_para_o_carimbo(selo_texto)
    except Exception:  # noqa: BLE001
        _valores_carimbo = ""

    # Ate dois selos por linha, cada qual com o proprio QR. A etiqueta inteira
    # continua intacta, apenas ganha uma composicao compacta para nao consumir
    # a ficha com caixas verticais muito altas.
    celulas = []
    for i, selo in enumerate(selos):
        dentro = ""
        imagem = imagens[i] if i < len(imagens) else None
        if imagem:
            dentro += ('<draw:frame draw:style-name="Fr-qr" text:anchor-type="as-char" '
                       'svg:width="1.25cm" svg:height="1.25cm">'
                       f'<draw:image xlink:href="Pictures/{imagem}" '
                       'xlink:type="simple" xlink:show="embed" '
                       'xlink:actuate="onLoad"/></draw:frame> ')
        dentro += escape(" ".join(str(selo).split()))
        celulas.append(dentro)

    saida = ['<table:table table:name="SelosCompactos" table:style-name="Tab-selos-compactos">',
             '<table:table-column table:style-name="Col-selo-compacto"/>'
             '<table:table-column table:style-name="Col-selo-compacto"/>']
    for inicio in range(0, len(celulas), 2):
        saida.append('<table:table-row>')
        nesta_linha = celulas[inicio:inicio + 2]
        if len(nesta_linha) == 1:
            # Um selo ocupa somente a primeira metade. A segunda célula existe
            # para conservar a grade de 8 cm, mas é invisível: não parece um
            # segundo selo esquecido.
            saida.append('<table:table-cell table:style-name="Cel-selo-compacto" '
                         'office:value-type="string">'
                         '<text:p text:style-name="P-selo-compacto">'
                         f'{nesta_linha[0]}</text:p></table:table-cell>'
                         '<table:table-cell table:style-name="Tab-cab.cel" '
                         'office:value-type="string"><text:p/></table:table-cell>')
        else:
            for conteudo in nesta_linha:
                saida.append('<table:table-cell table:style-name="Cel-selo-compacto" '
                             'office:value-type="string"><text:p '
                             f'text:style-name="P-selo-compacto">{conteudo}</text:p>'
                             '</table:table-cell>')
        saida.append('</table:table-row>')
    saida.append('</table:table>')
    if _valores_carimbo:
        # Relacao de emolumentos no carimbo (pedido do oficial 15/09/2026).
        saida.append(
            '<text:p text:style-name="P-selo">'
            '<text:span text:style-name="T-small">'
            '<text:span text:style-name="T-bold">Emolumentos do carimbo: </text:span>'
            + escape(_valores_carimbo) +
            '</text:span></text:p>')
    return "".join(saida)

# Cabecalho do selo do TJMA e, em falta dele, o proprio codigo: cinco a sete
# letras maiusculas, o CNS com seis digitos e o restante do codigo.
_CABECALHO_SELO = re.compile(r"(?=Poder\s+Judici)")
_CODIGO_SELO = re.compile(r"(?=(?<![A-Z0-9])[A-Z]{5,7}\d{6}[A-Z0-9]{15,25}\b)")
# "Selo:" ou o codigo em si — serve para saber se um pedaco ja identifica um
# selo, e portanto se o proximo codigo pertence a outro.
_ROTULO_SELO = re.compile(r"\bselo\s*:|(?<![A-Z0-9])[A-Z]{5,7}\d{6}[A-Z0-9]{10,25}\b", re.I)
_SO_CODIGO = re.compile(r"(?<![A-Z0-9])[A-Z]{5,7}\d{6}[A-Z0-9]{10,25}\b")


def separar_selos(texto: str | None) -> list[str]:
    """Quebra o texto colado em selos individuais — um por caixa.

    Um mesmo ato costuma ter mais de um selo: a prenotacao e o registro, por
    exemplo. Cada um tem de sair na sua propria caixa, como sai do sistema do
    tribunal.

    COMO SE DECIDE ONDE UM ACABA E O OUTRO COMECA
        Dentro de uma mesma linha, quebra-se pelo cabecalho "Poder
        Judiciario"; nao havendo cabecalho, pelo codigo do selo. Os dois
        criterios sao alternativos, nunca simultaneos — juntos, partiam cada
        selo em dois: cabecalho de um lado, codigo do outro.

        Entre linhas, a regra e outra. Quebra de linha nem sempre separa
        selos: um selo so, copiado do sistema do tribunal, costuma vir
        repartido em varias linhas. Entao comeca selo novo a linha que traz o
        cabecalho, ou a que traz codigo quando o selo em curso JA tem o seu.
        Dois codigos nunca cabem na mesma caixa; o resto e continuacao.
    """
    if not texto:
        return []

    def parte_um(bloco: str) -> list[str]:
        bloco = " ".join(bloco.split())
        if not bloco:
            return []
        if _CABECALHO_SELO.search(bloco):
            return [p.strip() for p in _CABECALHO_SELO.split(bloco) if p and p.strip()]

        pedacos = [p.strip() for p in _CODIGO_SELO.split(bloco) if p and p.strip()]
        # Quebrando pelo codigo, o "Selo:" que vem antes dele fica orfao. Cada
        # pedaco sem codigo gruda no proximo que tiver — o rotulo pertence ao
        # codigo que anuncia, nao a uma caixa propria.
        juntos: list[str] = []
        pendente = ""
        for p in pedacos:
            if _SO_CODIGO.search(p):
                juntos.append(f"{pendente} {p}".strip())
                pendente = ""
            else:
                pendente = f"{pendente} {p}".strip()
        if pendente:
            if juntos:
                juntos[-1] = f"{juntos[-1]} {pendente}".strip()
            else:
                juntos = [pendente]
        return juntos or [bloco]

    saida: list[str] = []
    for linha in str(texto).splitlines():
        for pedaco in parte_um(linha):
            tem_cabecalho = bool(_CABECALHO_SELO.match(pedaco))
            tem_codigo = bool(_ROTULO_SELO.match(pedaco))
            atual_tem_codigo = bool(saida and _ROTULO_SELO.search(saida[-1]))
            if not saida or tem_cabecalho or (tem_codigo and atual_tem_codigo):
                saida.append(pedaco)
            else:
                saida[-1] = f"{saida[-1]} {pedaco}".strip()
    return saida



def campo_folha_do_livro_odf(folha_inicial: int) -> str:
    """Campo ODF da face do livro (193, 193v, 194…), não o número da página do PDF.

    Usa a variável PAGE do LibreOffice: frente nas páginas ímpares, verso (`v`)
    nas pares, avançando uma folha a cada duas páginas — a mesma conta de
    `notas_livro.rotulo_folha_da_pagina`. Pedido do oficial em 18/09/2026: a
    segunda página da escritura tinha de sair `193v`, e saía `194`.
    

    ATENÇÃO (23/09/2026): na exportação PDF via `soffice --headless` o LibreOffice **não recalcula** `text:expression`/`text:conditional-text` com PAGE — o valor em cache (ex.: `1`) sai em todas as páginas. `impressao_pdf.pdf_de_odt` detecta este campo e reescreve 1/1v/2/2v no PDF. O campo continua no .odt para quem abre no LibreOffice com atualização de campos."""
    inicio = int(folha_inicial)
    # Número da folha: INT((PAGE-1)/2) + início
    numero = (
        f'<text:expression text:formula="ooow:INT((PAGE-1)/2)+{inicio}" '
        f'office:value-type="float" office:value="{inicio}">{inicio}</text:expression>'
    )
    # Sufixo "v" nas páginas pares (verso).
    verso = (
        '<text:conditional-text text:condition="ooow:(PAGE rem 2)=0" '
        'text:string-value-if-true="v" text:string-value-if-false="" '
        'text:current-value="false"/>'
    )
    return numero + verso


# HOTFIX-FOLHAS-FV (08/10/2026, pedido Beatriz): «faça com que as folhas se
# modifiquem automaticamente — 48, 48 verso, 49, 49 verso — sem precisar
# modificar manualmente. EM TODAS AS ATRIBUIÇÕES.»
#
#   O CAMPO COM FORMULA PAGE NAO BASTAVA. `campo_folha_do_livro_odf` grava
#   `INT((PAGE-1)/2)+N`, e o LibreOffice nao recalcula essa expressao nem na
#   exportacao headless nem, na pratica, ao abrir o .odt para imprimir: todas
#   as paginas do termo da ata 780 sairam «FOLHA 48». O PDF so era corrigido
#   quando a ancora era «FICHA» (ficha do RI); o termo das Notas diz «FOLHA».
#
#   AGORA O ROTULO E TEXTO FIXO EM CADA PAGINA. Uma pagina-mestre por face —
#   «Folha-001» diz 48, «Folha-002» diz 48v, «Folha-003» diz 49… — ligadas por
#   `style:next-style-name`. Quem decide a quebra continua sendo o
#   LibreOffice; ao virar a pagina ele passa sozinho para a mestre seguinte, e
#   o rotulo acompanha. Nao depende de atualizar campo, nem de pos-processar o
#   PDF. Depois da ultima mestre da cadeia vale a mestre com a formula antiga
#   (rede de seguranca) — e o PDF ainda passa por
#   `impressao_pdf.corrigir_rotulos_folha_livro_pdf`.
PAGINAS_ROTULADAS = 160


def rotulo_face_da_pagina(folha_inicial: int, pagina: int) -> str:
    """Pagina 1 -> 48, 2 -> 48v, 3 -> 49… (art. 795 do Codigo de Normas)."""
    inicio = int(folha_inicial)
    numero = inicio + (int(pagina) - 1) // 2
    return f"{numero}v" if int(pagina) % 2 == 0 else str(numero)


def _cadeia_de_paginas_rotuladas(estilos: str, cabecalho_com_marca: str,
                                 marca: str, folha_inicial: int, *,
                                 primeira_sem_cabecalho: bool,
                                 paginas: int = PAGINAS_ROTULADAS) -> str:
    """Troca a(s) pagina(s)-mestre por uma cadeia com o rotulo fixo de cada face.

    `cabecalho_com_marca` e o cabecalho ODF ainda com `marca` (#FOLHA_PAGINA# ou
    #FICHA#). A pagina 1 continua sendo «Standard» (ou «Primeira», sem
    cabecalho, quando pedido) — o corpo nao precisa mudar.
    """
    def _mestre(nome, rotulo, proxima, com_cabecalho=True, extra=""):
        cab = ""
        if com_cabecalho:
            cab = ("<style:header>"
                   + cabecalho_com_marca.replace(marca, escape(rotulo))
                   + "</style:header>")
        return (f'<style:master-page style:name="{nome}" '
                f'style:page-layout-name="pm1" '
                f'style:next-style-name="{proxima}"{extra}>{cab}'
                f'</style:master-page>')

    total = max(2, int(paginas))
    nomes = ["Standard"] + [f"Folha-{k:03d}" for k in range(2, total + 1)]
    mestres = []
    if primeira_sem_cabecalho:
        mestres.append(
            '<style:master-page style:name="Primeira" '
            'style:page-layout-name="pm1" style:next-style-name="Folha-002"/>')
    for k in range(1, total + 1):
        nome = nomes[k - 1]
        proxima = nomes[k] if k < total else "Folha-resto"
        mestres.append(_mestre(nome, rotulo_face_da_pagina(folha_inicial, k),
                               proxima))
    # Rede de seguranca: alem da cadeia, o campo antigo (formula PAGE).
    mestres.append(
        '<style:master-page style:name="Folha-resto" style:page-layout-name="pm1" '
        'style:next-style-name="Folha-resto"><style:header>'
        + cabecalho_com_marca.replace(marca, campo_folha_do_livro_odf(folha_inicial))
        + "</style:header></style:master-page>")
    novo = ("<office:master-styles>\n  " + "\n  ".join(mestres)
            + "\n </office:master-styles>")
    estilos, n = re.subn(r"<office:master-styles>.*?</office:master-styles>",
                         lambda _m: novo, estilos, count=1, flags=re.S)
    if not n:
        raise RuntimeError("styles.xml sem <office:master-styles>.")
    return estilos


def gerar_odt(corpo_odf: str, titulo: str = "", cabecalho_odf: str = "",
              imagens: dict[str, tuple[bytes, str]] | None = None, *,
              cabecalho_altura_min: str = "3.2cm",
              cabecalho_margem_baixo: str = "0.8cm",
              cabecalho_borda: bool = True,
              cabecalho_a_partir_da_pagina_2: bool = False,
              folha_pagina_ajuste: int | None = None,
              folha_livro_inicio: int | None = None,
              pagina_largura_cm: float | None = None,
              pagina_altura_cm: float | None = None,
              margem_cm: float | None = None) -> bytes:
    """Monta o .odt. O mimetype tem de ser a primeira entrada e sem compressao,
    senao o LibreOffice nao reconhece o pacote.

    O cabecalho, quando informado, e repetido em todas as paginas - e como a
    ficha da serventia se apresenta: identificacao do cartorio, da matricula e
    do livro no topo de cada folha. `cabecalho_altura_min`, `cabecalho_
    margem_baixo` e `cabecalho_borda` existem porque nem todo cabecalho e do
    tamanho da ficha do RI — um cabecalho de uma linha so (Livro/Folha/Termo
    do traslado das Notas) nao precisa dos mesmos 3,2 cm reservados, e sobrava
    espaco em branco antes do texto.

    `cabecalho_a_partir_da_pagina_2=True` tira o cabecalho de PAGINA da
    primeira pagina — pedido do oficial em 07/09/2026: a primeira ja tem a
    mesma informacao (Livro/Folha/Termo) escrita no proprio corpo, entre o
    endereco da serventia e o rotulo do ato, e o cabecalho por cima duplicava.
    Quem usa isto marca, no proprio `corpo_odf`, o UNICO paragrafo que deve
    abrir a pagina 1 com `text:style-name="{ESTILO_PAGINA_1}"` — o resto (o
    cabecalho valendo da pagina 2 em diante) sai sozinho, por
    `style:next-style-name`.

    `folha_pagina_ajuste`, quando informado, faz `#FOLHA_PAGINA#` no
    `cabecalho_odf` virar um numero de pagina — a pagina 1 mostra
    `1 + ajuste`, a 2 mostra `2 + ajuste`, e assim por diante. **E a pagina
    do PDF, e nao a face do livro** (frente/verso): o sistema nao tem como
    saber, ao montar o `.odt`, quantas paginas o LibreOffice vai desenhar —
    isso so se decide na conversao. Pedido do oficial em 07/09/2026: «preciso
    que conste a pagina especifica, nao a janela que a escritura esta
    usando».

    `folha_livro_inicio`, quando informado, faz `#FOLHA_PAGINA#` seguir a face
    do livro (frente/verso): a página 1 mostra o número inicial, a 2 mostra
    `Nv`, a 3 a folha seguinte, e assim por diante. Preferível a
    `folha_pagina_ajuste` nos atos de notas — pedido 18/09/2026.
    """
    extras = "".join(ESTILOS_EXTRA.values())
    estilo_pagina_1 = (
        f'<style:style style:name="{ESTILO_PAGINA_1}" style:family="paragraph" '
        f'style:parent-style-name="P-centro" style:master-page-name="Primeira"/>'
        if cabecalho_a_partir_da_pagina_2 else "")
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content {NS} office:version="1.2">
 <office:automatic-styles>{ESTILOS_AUTO}{extras}{estilo_pagina_1}</office:automatic-styles>
 <office:body><office:text>
{corpo_odf}
 </office:text></office:body>
</office:document-content>
"""
    # O número da ficha é o da FOLHA FÍSICA (frente/verso), não o da página
    # do PDF. Pedido Beatriz 23/09/2026: o papel usa frente e verso —
    # página 1 = Ficha 1, página 2 = Ficha 1v, página 3 = Ficha 2, página 4 =
    # Ficha 2v… Mesma conta de campo_folha_do_livro_odf / art. 795 (Código
    # de Normas). O modelo escreve #FICHA# e aqui vira campo ODF com fórmula
    # PAGE — se fosse texto fixo, a folha 3 sairia dizendo "FICHA Nº 1".
    # HOTFIX-FOLHAS-FV: lembra a marca e o inicio, para a cadeia de
    # paginas-mestre com o rotulo fixo de cada face (ver
    # `_cadeia_de_paginas_rotuladas`).
    _rotulo_marca, _rotulo_inicio, _rotulo_cab = None, None, None
    if "#FICHA#" in (cabecalho_odf or ""):
        _rotulo_marca, _rotulo_inicio, _rotulo_cab = "#FICHA#", 1, cabecalho_odf
    elif folha_livro_inicio is not None and "#FOLHA_PAGINA#" in (cabecalho_odf or ""):
        _rotulo_marca, _rotulo_inicio, _rotulo_cab = (
            "#FOLHA_PAGINA#", int(folha_livro_inicio), cabecalho_odf)
    cabecalho_odf = (cabecalho_odf or "").replace(
        "#FICHA#", campo_folha_do_livro_odf(1))
    if folha_livro_inicio is not None:
        # Face do livro (193, 193v…), não o número sequencial do PDF.
        cabecalho_odf = cabecalho_odf.replace(
            "#FOLHA_PAGINA#", campo_folha_do_livro_odf(int(folha_livro_inicio)))
    elif folha_pagina_ajuste is not None:
        cabecalho_odf = cabecalho_odf.replace(
            "#FOLHA_PAGINA#",
            f'<text:page-number text:select-page="current" '
            f'text:page-adjust="{int(folha_pagina_ajuste)}">'
            f'{1 + int(folha_pagina_ajuste)}</text:page-number>')
    import re as _re
    if cabecalho_odf:
        estilos = STYLES.replace("__CABECALHO__", cabecalho_odf)
        # O TAMANHO DO CABECALHO NAO E UM SO — a ficha do RI precisa dos
        # 3,2 cm de fabrica; um cabecalho de uma linha so pede bem menos, e
        # deixar o padrao sobraria em espaco em branco antes do texto.
        borda = ('fo:border-bottom="0.06pt solid #000000" ' if cabecalho_borda
                 else "")
        estilos = _re.sub(
            r'<style:header-footer-properties [^>]*/>',
            f'<style:header-footer-properties fo:min-height="{cabecalho_altura_min}" '
            f'fo:margin-bottom="{cabecalho_margem_baixo}" style:dynamic-spacing="true" '
            f'{borda}fo:padding-bottom="0.15cm"/>',
            estilos)
        if cabecalho_a_partir_da_pagina_2:
            # DUAS PAGINAS-MESTRE: "Primeira" nao tem `<style:header>` nenhum
            # — pagina sem cabecalho existe simplesmente por nao declarar um
            # —, e `style:next-style-name` faz a PROXIMA pagina (a segunda em
            # diante) cair sozinha na "Standard", que tem o cabecalho.
            estilos = estilos.replace(
                '<style:master-page style:name="Standard" style:page-layout-name="pm1">',
                '<style:master-page style:name="Primeira" style:page-layout-name="pm1" '
                'style:next-style-name="Standard"/>\n'
                '  <style:master-page style:name="Standard" style:page-layout-name="pm1">')
        if _rotulo_marca is not None:
            # HOTFIX-FOLHAS-FV: uma pagina-mestre por face, rotulo fixo.
            _cab_marca = _rotulo_cab
            if _rotulo_marca == "#FOLHA_PAGINA#":
                _cab_marca = _cab_marca.replace(
                    "#FICHA#", campo_folha_do_livro_odf(1))
            else:
                _cab_marca = _cab_marca.replace(
                    "#FOLHA_PAGINA#", campo_folha_do_livro_odf(
                        int(folha_livro_inicio or 1)))
            estilos = _cadeia_de_paginas_rotuladas(
                estilos, _cab_marca, _rotulo_marca, _rotulo_inicio,
                primeira_sem_cabecalho=cabecalho_a_partir_da_pagina_2)
    else:
        # Sem cabecalho pedido, o cabecalho tem de sumir de verdade. Deixar o
        # paragrafo vazio faz o LibreOffice reservar os 3,2 cm e desenhar o
        # traco de baixo — o que aparecia como um risco solto no topo do
        # recibo, do orcamento e do protocolo de recepcao.
        estilos = _re.sub(r"<style:header-style>.*?</style:header-style>", "",
                          STYLES, flags=_re.S)
        estilos = _re.sub(r"<style:header>__CABECALHO__</style:header>", "",
                          estilos)
    # As larguras tambem precisam existir no styles.xml: o cabecalho e
    # montado la, e sem o estilo a coluna sai com a largura que o LibreOffice
    # inventar.
    # Pagina sob medida (folha do livro carta 215x279, etc.). Padrao A4.
    # Tem de rodar DEPOIS do if/else do cabecalho, senao estilos nao existe
    # quando o termo vem sem cabecalho_odf (folha RCPN).
    #
    # **E TEM DE MEXER SO NO `<style:page-layout-properties>` — 09/09/2026.**
    # A primeira versao trocava `fo:margin-top` no styles.xml inteiro com
    # `count=1`, e `count=1` pega a PRIMEIRA ocorrencia do arquivo: antes da
    # pagina ha 4 `fo:margin-top` e 9 `fo:margin-bottom` de estilos de
    # PARAGRAFO. Resultado medido na folha do livro da Agata (termo 19566):
    # a margem que mudava era a de um paragrafo qualquer, e a PAGINA ficava
    # com os 1,5 cm / 2 cm de fabrica — a imagem de 27,91 cm entrava numa
    # area util de 24,41 cm e transbordava, jogando cada folha para paginas
    # a mais. `left` e `right` funcionavam por acaso: so existem na pagina.
    def _na_pagina(bloco: str) -> str:
        if pagina_largura_cm is not None:
            bloco = _re.sub(r'fo:page-width="[^"]+"',
                            f'fo:page-width="{float(pagina_largura_cm):g}cm"',
                            bloco)
        if pagina_altura_cm is not None:
            bloco = _re.sub(r'fo:page-height="[^"]+"',
                            f'fo:page-height="{float(pagina_altura_cm):g}cm"',
                            bloco)
        if margem_cm is not None:
            m = f"{float(margem_cm):g}cm"
            for lado in ("top", "bottom", "left", "right"):
                bloco = _re.sub(rf'fo:margin-{lado}="[^"]+"',
                                f'fo:margin-{lado}="{m}"', bloco)
        return bloco

    if (pagina_largura_cm is not None or pagina_altura_cm is not None
            or margem_cm is not None):
        estilos, quantas = _re.subn(
            r'<style:page-layout-properties\b[^>]*>',
            lambda m: _na_pagina(m.group(0)), estilos, count=1)
        if not quantas:
            raise RuntimeError(
                "styles.xml sem <style:page-layout-properties> — a pagina sob "
                "medida nao teria onde ser aplicada, e o .odt sairia no A4 de "
                "fabrica sem ninguem perceber.")

    estilos = estilos.replace("</office:automatic-styles>",
                              extras + "</office:automatic-styles>")
    imagens = imagens or {}
    entradas = "\n".join(
        f' <manifest:file-entry manifest:full-path="Pictures/{nome}" '
        f'manifest:media-type="{mime}"/>'
        for nome, (_, mime) in imagens.items()
    )
    manifesto = MANIFEST.replace("__IMAGENS__", entradas)

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("mimetype"), MIME, compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/manifest.xml", manifesto)
        z.writestr("styles.xml", estilos)
        z.writestr("content.xml", content)
        for nome, (dados, _) in imagens.items():
            z.writestr(f"Pictures/{nome}", dados)
    return buf.getvalue()


def rotulo_ato(tipo: str, numero: int, matricula: str) -> str:
    """Formato usado na ficha da serventia: R-01/4012, AV-02/4012."""
    return f"{tipo}-{int(numero):02d}/{matricula}"


def natureza_titulo_sem_rotulo(natureza: str | None, tipo: str,
                               numero: int | str,
                               matricula: str | int | None = None) -> str:
    """Tira rotulo embutido no inicio de natureza_titulo.

    A ficha ja imprime ``{{ a.rotulo }} – {{ natureza }}``. Se natureza vier
    como ``AV-01/4.020 - CERTIFICACAO…``, o papel fica com rotulo duplicado
    (relato Beatriz 25/09/2026, AV-01/4020). Aceita 4.020/4020, hifen,
    en-dash e em-dash. Sem match, devolve a natureza original.
    """
    texto = (natureza or "").strip()
    if not texto:
        return ""
    tipo_u = (tipo or "").strip().upper()
    try:
        num = int(numero)
    except (TypeError, ValueError):
        return texto
    if not tipo_u:
        return texto
    mat_dig = re.sub(r"\D", "", str(matricula or "")).lstrip("0")
    abre = re.match(
        rf"^(?:{re.escape(tipo_u)})\s*[-.]?\s*0*{num}\s*/\s*([\d.]+)\s*"
        rf"[-\u2013\u2014:]\s*",
        texto, flags=re.IGNORECASE)
    if not abre:
        abre2 = re.match(
            rf"^(?:{re.escape(tipo_u)})\s*[-.]?\s*0*{num}\s*"
            rf"[-\u2013\u2014:]\s*",
            texto, flags=re.IGNORECASE)
        if not abre2:
            return texto
        return texto[abre2.end():].strip() or texto
    if mat_dig:
        mat_no = re.sub(r"\D", "", abre.group(1)).lstrip("0")
        if mat_no and mat_no != mat_dig:
            return texto
    limpo = texto[abre.end():].strip()
    return limpo or texto


def teor_sem_cabecalho_do_ato(teor: str | None, tipo: str, numero: int | str,
                              matricula: str | int) -> str:
    """Tira do inicio do teor o cabecalho que a ficha ja imprime.

    Aceita 4.020/4020, hifen/en-dash/em-dash, quebras de linha e data
    ISO (2026-09-24) ou por extenso. Comprime brancos iniciais apos o corte.
    """
    if not teor:
        return ""
    texto = str(teor)
    bruto = texto.lstrip("\r\n\t \xa0")
    bruto = re.sub(r"^(?:<p[^>]*>\s*</p>\s*)+", "", bruto, flags=re.IGNORECASE)
    bruto = bruto.lstrip("\r\n\t \xa0")
    tipo_u = (tipo or "").strip().upper()
    try:
        num = int(numero)
    except (TypeError, ValueError):
        return texto
    mat_dig = re.sub(r"\D", "", str(matricula or "")).lstrip("0")
    if not tipo_u or not mat_dig:
        return texto

    abre = re.match(
        rf"^(?:<p[^>]*>)?\s*{re.escape(tipo_u)}\s*[-.]?\s*0*{num}\s*/\s*([\d.]+)\b\s*",
        bruto, flags=re.IGNORECASE)
    if not abre:
        return texto
    mat_no_teor = re.sub(r"\D", "", abre.group(1)).lstrip("0")
    if mat_no_teor != mat_dig:
        return texto

    resto = re.sub(r"^[-–—:]\s*", "", bruto[abre.end():])

    m_com_prot = re.match(
        r"^(.{0,360}?\bPROTOCOLO\b.{0,240}?\b(?:19|20)\d{2}(?:-\d{2}-\d{2})?)\.\s*",
        resto, flags=re.IGNORECASE | re.DOTALL)
    if m_com_prot:
        cortado = resto[m_com_prot.end():]
        cortado = re.sub(r"^(?:<p[^>]*>\s*</p>\s*)+", "", cortado, flags=re.IGNORECASE)
        cortado = cortado.lstrip("\r\n\t \xa0")
        cortado = re.sub(r"^(\r?\n){2,}", "", cortado)
        return cortado if cortado else texto

    m_nat = re.match(
        r"^([A-ZÀ-ÖØ-öø-ÿ0-9][^.\n]{0,200})\.\s*",
        resto, flags=re.DOTALL)
    if m_nat:
        cortado = resto[m_nat.end():]
        cortado = re.sub(r"^(?:<p[^>]*>\s*</p>\s*)+", "", cortado, flags=re.IGNORECASE)
        cortado = cortado.lstrip("\r\n\t \xa0")
        cortado = re.sub(r"^(\r?\n){2,}", "", cortado)
        return cortado if cortado else texto
    return texto



# ------------------------------------------------------------- modelo padrao

# Cabecalho no formato do modelo em papel da serventia: nome do servico, os
# dois delegatarios lado a lado com o titulo de cada um embaixo, e depois a
# identificacao da ficha. O bloco dos delegatarios e uma <table> de proposito:
# e o que produz as duas colunas centralizadas.
# Cabecalho no formato do modelo em papel: uma GRADE DE CAIXAS de tres
# colunas por duas linhas. A primeira coluna ocupa as duas linhas (rowspan) e
# guarda a identificacao da serventia com os dois delegatarios; a do meio traz
# matricula, CNM, data e livro; a da direita, a ficha e o usuario.
#
# As larguras vieram do proprio modelo em Word (4111, 3686 e 2351 twips),
# reduzidas na mesma proporcao para a largura util da nossa pagina.


def teor_ja_abre_com_rotulo(teor_html: str | None, tipo: str, numero: int | str,
                            matricula: str | int) -> bool:
    """True se o texto visivel ja comeca com R-01/3247 (ou R-1/3.247)."""
    if not teor_html:
        return False
    from html import unescape as _unescape
    from ri_numeros_do_teor import ROTULO
    vis = " ".join(_unescape(re.sub(r"(?is)<[^>]+>", " ", str(teor_html))).split())
    if not vis:
        return False
    abre = ROTULO.match(vis)
    if not abre:
        return False
    tipo_u = (tipo or "").strip().upper()
    try:
        num = int(numero)
    except (TypeError, ValueError):
        return False
    mat_dig = _so_digitos_de(matricula)
    if not tipo_u or not mat_dig:
        return False
    if (abre.group(1) or "").upper() != tipo_u:
        return False
    try:
        if int(abre.group(2)) != num:
            return False
    except (TypeError, ValueError):
        return False
    return _so_digitos_de(abre.group(3)) == mat_dig


def html_com_destaque_rotulo_ato(teor_html: str | None, tipo: str, numero: int | str,
                                 matricula: str | int) -> str:
    """Prefixa ``<b>R-01/3247:-</b>`` no teor da certidao se ainda nao houver.

    Na ficha o ``<h3>``/``ato-cab`` ja mostra o rotulo e o teor fica sem
    cabecalho (`teor_sem_cabecalho_do_ato`). Na certidao de inteiro teor o
    miolo so imprimia o teor — atos lavrados hoje (sem R/AV embutido no
    texto, ao contrario do acervo OCR) saiam sem destaque. Beatriz
    29/09/2026, cert. 33/2026 mat. 3247.

    Se o teor ja abre com o rotulo desta matricula (padrao acervo
    ``R-1/2.005:-``), nao repete.
    """
    html = teor_html or ""
    if teor_ja_abre_com_rotulo(html, tipo, numero, matricula):
        return html
    try:
        num = int(numero)
    except (TypeError, ValueError):
        num = numero
    rot = rotulo_ato(tipo, num, str(matricula))
    marca = f"<b>{escape(rot)}:-</b> "
    m = re.match(r"(?is)(<p(?:\s[^>]*)?>)", html)
    if m:
        return html[:m.end()] + marca + html[m.end():]
    if html.strip():
        return f"<p>{marca}</p>" + html
    return f"<p>{marca.rstrip()}</p>"


def cabecalho_certidao_compacto_html(sv: dict | None) -> str:
    """HTML do cabeçalho compacto (sem brasão — o ODF acrescenta a imagem).

    Pedido 16/09/2026: padrão Notas/RCPN, compacto, sem moldura:
      OFÍCIO ÚNICO …
      Oficial: …  ·  Substituta: …
      CNS … — Cidade/UF
    """
    from xml.sax.saxutils import escape
    s = sv or {}
    unidade = escape(str(s.get("unit_name") or s.get("nome") or ""))
    oficial = escape(str(
        s.get("serventia_titular") or s.get("registrador") or ""))
    substituta = escape(str(
        s.get("ri_substituta") or s.get("substituta") or ""))
    cns = escape(str(s.get("ri_cns") or s.get("cns") or ""))
    cidade = escape(str(s.get("ri_cidade") or s.get("cidade") or ""))
    uf = escape(str(s.get("ri_uf") or s.get("uf") or ""))
    cidade_uf = f"{cidade}/{uf}" if cidade and uf else (cidade or uf)

    pessoas = ""
    if oficial and substituta:
        pessoas = (f'<p align="center">Oficial: {oficial}'
                   f'  ·  Substituta: {substituta}</p>')
    elif oficial:
        pessoas = f'<p align="center">Oficial: {oficial}</p>'
    elif substituta:
        pessoas = f'<p align="center">Substituta: {substituta}</p>'
    linha_cns = ""
    if cns or cidade_uf:
        meio = " — ".join(
            x for x in (f"CNS {cns}" if cns else "", cidade_uf) if x)
        linha_cns = f'<p align="center">{meio}</p>'
    return (
        f'<p align="center"><b>{unidade}</b></p>'
        f"{pessoas}"
        f"{linha_cns}"
    )


def cabecalho_certidao_compacto_odf(sv: dict | None) -> tuple[str, dict]:
    """ODF do cabeçalho compacto + brasão pequeno (1,6 cm), se o arquivo existir.

    Retorna (odf, imagens). `imagens` vai para `gerar_odt(..., imagens=...)`.
    """
    brasao_odf, imagens = _brasao_do_cabecalho()
    texto_odf = html_para_odf(cabecalho_certidao_compacto_html(sv), compacto=True)
    return brasao_odf + texto_odf, imagens


def _brasao_do_cabecalho() -> tuple[str, dict]:
    """O brasão pequeno (1,6 cm) do alto da folha, se o arquivo existir."""
    imagens: dict[str, tuple[bytes, str]] = {}
    brasao_odf = ""
    from pathlib import Path as _Path
    brasao = _Path(__file__).resolve().parent / "static" / "brasao.jpg"
    if brasao.is_file():
        imagens["brasao.jpg"] = (brasao.read_bytes(), "image/jpeg")
        # P-centro: brasão centrado. Tamanho compacto (aprovado na prévia).
        brasao_odf = (
            '<text:p text:style-name="P-centro">'
            '<draw:frame draw:style-name="Fr-qr" text:anchor-type="as-char" '
            'svg:width="1.6cm" svg:height="1.6cm">'
            '<draw:image xlink:href="Pictures/brasao.jpg" '
            'xlink:type="simple" xlink:show="embed" '
            'xlink:actuate="onLoad"/></draw:frame></text:p>'
        )
    return brasao_odf, imagens


def cabecalho_certidao_completo_html(sv: dict | None) -> str:
    """HTML do cabeçalho COMPLETO da certidão (sem brasão — o ODF o põe).

    Pedido 23/09/2026 («o cabeçalho não está completo»), aprovado pela prévia
    em imagem («pode aplicar»), para as certidões do Livro 2 e do Livro 3:

      REPÚBLICA FEDERATIVA DO BRASIL / ESTADO DO MARANHÃO
      COMARCA DE <cidade>/<UF>
      SERVENTIA EXTRAJUDICIAL DO <unidade>
      <endereço completo>
      Telefone … · e-mail · CNPJ …
      <titular> — <título>
      <substituta> — Substituta
      CNS …

    **A FORMA é a das certidões do E-Ofício** (`LivroAuxiliarCertidao.Teor`
    traz República, Estado, Comarca, Serventia, endereço e telefone); **OS
    VALORES NÃO**: ali está o oficial anterior, e copiar o texto traria para o
    papel de hoje quem já não responde pela casa. Tudo sai de
    `serventia.dados`, a regra viva.

    **A COMPACTA CONTINUA EXISTINDO, de propósito**: a ficha do Livro 3
    (`ra_ficha_odt`) e a folha avulsa (`certidao_folhas`) usam a de três linhas,
    e ninguém pediu para mudá-las. Campo sem valor não sai — linha com rótulo e
    nada depois é ruído num papel assinado.
    """
    from xml.sax.saxutils import escape
    s = sv or {}

    def v(*chaves: str) -> str:
        for k in chaves:
            if s.get(k):
                return escape(str(s[k]).strip())
        return ""

    unidade = v("unit_name", "nome")
    cidade, uf = v("ri_cidade", "cidade"), v("ri_uf", "uf")
    linhas = ['<p align="center"><b>REPÚBLICA FEDERATIVA DO BRASIL</b></p>',
              '<p align="center">ESTADO DO MARANHÃO</p>']
    if cidade:
        linhas.append('<p align="center">COMARCA DE '
                      f'{cidade.upper()}{"/" + uf if uf else ""}</p>')
    if unidade:
        linhas.append('<p align="center"><b>SERVENTIA EXTRAJUDICIAL DO '
                      f'{unidade.upper()}</b></p>')
    endereco = v("endereco_completo", "serventia_endereco")
    if endereco:
        linhas.append(f'<p align="center">{endereco}</p>')
    telefone, email, cnpj = (v("serventia_telefone"), v("serventia_email"),
                             v("serventia_cnpj"))
    contato = " · ".join(x for x in (
        f"Telefone {telefone}" if telefone else "",
        email,
        f"CNPJ {cnpj}" if cnpj else "") if x)
    if contato:
        linhas.append(f'<p align="center">{contato}</p>')
    titular, titulo = v("serventia_titular", "registrador"), v("serventia_titulo")
    if titular:
        linhas.append(f'<p align="center">{titular}'
                      + (f" — {titulo}" if titulo else "") + "</p>")
    substituta = v("ri_substituta", "substituta")
    if substituta:
        linhas.append(f'<p align="center">{substituta} — Substituta</p>')
    cns = v("ri_cns", "cns")
    if cns:
        linhas.append(f'<p align="center">CNS {cns}</p>')
    return "".join(linhas)


def cabecalho_certidao_completo_odf(sv: dict | None) -> tuple[str, dict]:
    """ODF do cabeçalho completo + brasão. Mesma forma de retorno da compacta."""
    brasao_odf, imagens = _brasao_do_cabecalho()
    texto_odf = html_para_odf(cabecalho_certidao_completo_html(sv), compacto=True)
    return brasao_odf + texto_odf, imagens


# `MODELO_CABECALHO_PADRAO` — o texto de fábrica do papel RI_CABECALHO — saiu daqui no LF06A
# (19/10/2026): mora em `modelos_padrao/ri/RI_CABECALHO.txt`, com os mesmos bytes, e
# chega pela base dos padrões (`modelos_da_casa.padrao_de`). O nome antigo
# continua respondendo — ver `__getattr__` no fim deste módulo.


# Modelo baseado na ficha real da serventia (MODELO EM WORD.docx):
# cabecalho repetido por pagina, bloco de denominacao, bloco do imovel,
# e os atos separados pela linha -.-.-.- , cada um com rotulo R-01/4012.
# `MODELO_FICHA_PADRAO` — o texto de fábrica do papel RI_FICHA — saiu daqui no LF06A
# (19/10/2026): mora em `modelos_padrao/ri/RI_FICHA.txt`, com os mesmos bytes, e
# chega pela base dos padrões (`modelos_da_casa.padrao_de`). O nome antigo
# continua respondendo — ver `__getattr__` no fim deste módulo.


# O MOLDE DA CERTIDAO, E O MIOLO DE CADA TIPO — 18/09/2026, problema #75.
#
# O PEDIDO DO OFICIAL, com as palavras dele:
#
#     «nao faz sentido ter opcao de emitir certidao negativa de matricula
#      dentro da tela da matricula ... tirar a opcao de certidao negativa de
#      matricula e estrutura um modelo base, considerando os modelos de outras
#      certidoes do cartorio, para os demais modelos de certidao»
#
# Eram QUATRO tipos num molde so, separados por `{% if tipo_certidao == ... %}`
# dentro de um unico texto. Quem abria a tela de editar via o papel dos quatro
# misturado, e mexer no que e comum — o fecho, a validade, a assinatura —
# exigia mexer tambem no que e de cada um. Agora sao **um molde e um miolo por
# tipo**:
#
#     MODELO_CERTIDAO_PADRAO            o que TODA certidao tem: a abertura
#                                       ("Certifico ... neles encontrei a
#                                       MATRICULA Nº ..."), a finalidade, a
#                                       validade do art. 553, e quem assina
#                                       — em dois desenhos: o do inteiro teor,
#                                       que ja traz o cabecalho da ficha, e o
#                                       dos outros, que abre com o timbre.
#
#     MIOLO_CERTIDAO_INTEIRO_TEOR       o teor da ficha, o selo de abertura e
#                                       o selo de cada ato (nº, emolumentos, QR)
#                                       — 22/09/2026: a certidão saía só com o
#                                       texto; os carimbos existiam no contexto
#                                       e o miolo não os puxava.
#     MIOLO_CERTIDAO_ONUS               os atos restritivos, ou o NADA CONSTA
#     MIOLO_CERTIDAO_PROPRIEDADE        quem e o dono hoje
#
# **O MIOLO NAO ENTRA POR ADIVINHACAO: ENTRA ONDE O MOLDE MANDA.** O molde
# carrega `{{ miolo_do_tipo }}` — a unica emenda entre os dois —, e quem
# substitui e `ri_web.corpo_certidao`. Molde sem o marcador sai sem o texto do
# tipo, e por isso a tela de editar **recusa** gravar um molde sem ele: papel
# que afirma «inteiro teor» e nao reproduz teor nenhum e o carimbo que mente na
# sua forma mais cara (relato #79, do dia anterior).
MARCADOR_DO_MIOLO = "{{ miolo_do_tipo }}"

# `MODELO_CERTIDAO_PADRAO` — o texto de fábrica do papel RI_CERTIDAO — saiu daqui no LF06A
# (19/10/2026): mora em `modelos_padrao/ri/RI_CERTIDAO.txt`, com os mesmos bytes, e
# chega pela base dos padrões (`modelos_da_casa.padrao_de`). O nome antigo
# continua respondendo — ver `__getattr__` no fim deste módulo.


# --------------------------------------------------------- os miolos
#
# O TEXTO DE CADA TIPO, e nada mais: o que fica em volta — a abertura, a
# finalidade, a validade, quem assina — e do molde, porque e igual nos tres.
#
# **ELES SAO UM PAPEL DO CATALOGO, E NAO PEDACO ESCONDIDO NO CODIGO.** O
# oficial edita os tres na mesma tela em que edita o molde (`RI_CERTIDAO_ONUS`
# e companhia, em Administrativo → Modelos), e por isso o que esta escrito aqui
# e so o TEXTO DE FABRICA: quem ajustar, ajusta na tela.
#
# E POR QUE ELES SE MEXEM SEM ARRASTAR O MOLDE: a frase do «NADA CONSTA» de
# onus e afirmacao sobre o imovel, e a do molde e afirmacao sobre a matricula e
# a data de hoje. Separadas, cada uma se conserta sozinha.

# `MIOLO_CERTIDAO_INTEIRO_TEOR` — o texto de fábrica do papel RI_CERTIDAO_INTEIRO_TEOR — saiu daqui no LF06A
# (19/10/2026): mora em `modelos_padrao/ri/RI_CERTIDAO_INTEIRO_TEOR.txt`, com os mesmos bytes, e
# chega pela base dos padrões (`modelos_da_casa.padrao_de`). O nome antigo
# continua respondendo — ver `__getattr__` no fim deste módulo.

# O fecho «Era o que nela continha.» VAI NO MIOLO, e nao no molde, porque ele
# fecha o TEOR: a certidao de onus nao reproduz teor nenhum, e a frase ali
# afirmaria uma reproducao que nao houve.
#
# Nao vai ao papel o ato cujo texto ja esta escrito no teor — quem decide isso
# e `contexto_ficha`, com `atos_fora_do_teor` (relato #79, 17/09/2026).

# A CERTIDÃO DE ÔNUS É POSITIVA OU NEGATIVA, E SÃO DUAS PERGUNTAS — 13/10/2026,
# pedido do oficial («contemplar tanto a positiva e a negativa»). O texto imita
# as certidões que a casa emitiu em 2024 (o arquivo de certidões antigas de
# ônus, 70 positivas e 258 negativas): na positiva, «HÁ ÔNUS REAIS, assim
# caracterizados: a) R-02/2.914 …» com o ATO TRANSCRITO; na negativa, «LIVRE E
# DESEMBARAÇADO DE TODOS ÔNUS REAIS, LEGAIS OU CONVENCIONAIS». E a segunda
# pergunta do mesmo papel, a citação de ações reais ou pessoais
# reipersecutórias. Quem decide qual sai é o escrevente, com a sugestão da IA —
# ver `ri_onus_ia.py`. O título do papel muda junto (`ri_onus_ia.titulo`).
#
# `resultado_onus`, `resultado_acoes`, `itens_onus` e `itens_acoes` vêm de
# `contexto_ficha` (o que o sistema sabe) ou da escolha do balcão. O `onus` de
# antes continua no contexto, para quem tiver editado este miolo na tela.
# `MIOLO_CERTIDAO_ONUS` — o texto de fábrica do papel RI_CERTIDAO_ONUS — saiu daqui no LF06A
# (19/10/2026): mora em `modelos_padrao/ri/RI_CERTIDAO_ONUS.txt`, com os mesmos bytes, e
# chega pela base dos padrões (`modelos_da_casa.padrao_de`). O nome antigo
# continua respondendo — ver `__getattr__` no fim deste módulo.

# `MIOLO_CERTIDAO_PROPRIEDADE` — o texto de fábrica do papel RI_CERTIDAO_PROPRIEDADE — saiu daqui no LF06A
# (19/10/2026): mora em `modelos_padrao/ri/RI_CERTIDAO_PROPRIEDADE.txt`, com os mesmos bytes, e
# chega pela base dos padrões (`modelos_da_casa.padrao_de`). O nome antigo
# continua respondendo — ver `__getattr__` no fim deste módulo.

# A CADEIA DOMINIAL E A VINTENÁRIA — construídas na produção em 28/09/2026
# (3.6.233, `_apply_dominial_patch.py`, e a segunda passada do mesmo dia, a das
# matrículas de ORIGEM) e perdidas quando os pacotes da 3.6.282 em diante
# sobrescreveram aquele código, que nunca entrou na árvore. Reconstituídas em
# 14/10/2026: o texto da 3.6.233 está na cópia de segurança
# `backups_patch/dominial_origem_20260928-100959/ri_odt.py`, e o desenho dos
# BLOCOS por matrícula foi lido no corpo da única certidão emitida, a 394/2026
# (matrícula 3472 → 2667 → 2548), porque a cópia do «depois» da segunda passada
# não existe.
#
# **QUEM ESCOLHE O ATO É `ri_dominial`, E NÃO O MIOLO**: a natureza SAUIN
# reconhecida primeiro, a palavra do título do registro como apoio — e o ato
# que entrou pela palavra vem marcado `conferir`, e a emissão avisa. Os blocos
# (`cadeia_matriculas`) saem de `ri_web`: a matrícula atual e, se houver, as de
# origem — só as que EXISTEM no banco; número citado que não existe não vira
# bloco, vira aviso na tela (nunca se inventa origem).
#
# A data do período da vintenária vai em dd/mm/aaaa — a 3.6.233 imprimia a data
# crua do banco (`2006-10-14`), que é a lição da certidão 6/2026 (28/08).
# `MIOLO_CERTIDAO_DOMINIAL` — o texto de fábrica do papel RI_CERTIDAO_DOMINIAL — saiu daqui no LF06A
# (19/10/2026): mora em `modelos_padrao/ri/RI_CERTIDAO_DOMINIAL.txt`, com os mesmos bytes, e
# chega pela base dos padrões (`modelos_da_casa.padrao_de`). O nome antigo
# continua respondendo — ver `__getattr__` no fim deste módulo.

# `MIOLO_CERTIDAO_VINTENARIA` — o texto de fábrica do papel RI_CERTIDAO_VINTENARIA — saiu daqui no LF06A
# (19/10/2026): mora em `modelos_padrao/ri/RI_CERTIDAO_VINTENARIA.txt`, com os mesmos bytes, e
# chega pela base dos padrões (`modelos_da_casa.padrao_de`). O nome antigo
# continua respondendo — ver `__getattr__` no fim deste módulo.

# **A «CERTIDAO NEGATIVA DE MATRICULA» NAO TEM MIOLO, porque nao existe mais**
# — problema #75, 18/09/2026. O texto dela dizia «NADA CONSTA em nome do
# requerente nos livros de Registro de Imoveis desta Serventia», e isso nao
# certifica ESTA matricula: e busca pelo nome da pessoa nos livros todos, que e
# outra pergunta e de outra tela. Ver `ri_schema.TIPOS_CERTIDAO`.

# O TIPO ESCOLHIDO DIZ QUAL MIOLO ENTRA — e o mapa tem EXATAMENTE os tipos que
# a tela da matricula oferece. Nao e arrumacao: tipo sem miolo no mapa faria a
# certidao sair com a abertura e sem o teor, e tipo no mapa que a tela nao
# oferece e caminho aberto para o proximo codigo pedir o texto de uma certidao
# que a casa nao emite. Ha teste que compara os dois conjuntos, um contra o
# outro (`ri_schema.TIPOS_CERTIDAO` e este mapa).
MIOLO_DA_CERTIDAO: dict[str, str] = {
    "INTEIRO_TEOR": "RI_CERTIDAO_INTEIRO_TEOR",
    "ONUS": "RI_CERTIDAO_ONUS",
    "PROPRIEDADE": "RI_CERTIDAO_PROPRIEDADE",
    "DOMINIAL": "RI_CERTIDAO_DOMINIAL",
    "VINTENARIA": "RI_CERTIDAO_VINTENARIA",
}


# `MODELO_NOTA_PADRAO` — o texto de fábrica do papel RI_NOTA — saiu daqui no LF06A
# (19/10/2026): mora em `modelos_padrao/ri/RI_NOTA.txt`, com os mesmos bytes, e
# chega pela base dos padrões (`modelos_da_casa.padrao_de`). O nome antigo
# continua respondendo — ver `__getattr__` no fim deste módulo.


def carimbo_da_certidao_odf(selo_texto, *, rotulo: str = "SELO DA CERTIDÃO",
                            prefixo: str = "qr-selo-certidao"
                            ) -> tuple[str, dict]:
    """O carimbo COMPLETO da certidao, e as imagens do pacote. So monta.

        «preciso que o carimbo das certidoes (todas) saia com data e hora da
         emissao, emolumentos, qr code, link de acesso ao tj, requerente»
          — o oficial, 17/09/2026

    Devolve `(fragmento_odf, {nome: (png, tipo)})`, para quem chama entregar
    as imagens ao `gerar_odt` — o `.odt` e um zip so, e uma segunda chamada
    sobrescreveria as imagens da primeira.

    **UM QR POR SELO.** Ha certidao com dois, e um QR so poria o codigo do
    primeiro debaixo do segundo: conferir o selo errado com cara de conferido
    e pior que nao conferir.

    **SEM `segno` A CASA NAO PARA** — o papel sai com o numero e o endereco
    escritos, que e o que se digita.
    """
    texto = str(selo_texto or "").strip()
    if not texto:
        return "", {}
    imagens: dict = {}
    nomes = []
    for i, pedaco in enumerate(
            carimbos_do_ato(texto, rotulo, feitio="certidao"), start=1):
        png = png_do_qr_do_selo(pedaco["numero"])
        if not png:
            nomes.append(None)
            continue
        nome = f"{prefixo}-{i}.png"
        imagens[nome] = (png, "image/png")
        nomes.append(nome)
    return (carimbo_do_selo_odf(texto, nomes or None, rotulo=rotulo,
                                feitio="certidao", por_fileira=1),
            imagens)


def png_do_qr_do_selo(numero) -> bytes | None:
    """PNG do QR de um selo. So calcula.

    **UMA COPIA SO NA CASA** — havia tres, em `ri_web`, `rc_certidao_odt` e
    `rc_certidao_inteiro_teor`, e as certidoes do Protesto e do RCPJ/RTD
    fariam a quarta e a quinta. O que vai DENTRO do QR de um papel assinado
    nao pode ter cinco versoes.

    O QR NAO SE GUARDA NO BANCO: ele e derivado do numero do selo, o banco
    viaja no backup, e a segunda via de amanha tem de trazer o mesmo QR de
    hoje — o que ela traz, porque o selo e o mesmo.
    """
    numero = str(numero or "").strip()
    if not numero:
        return None
    try:
        import segno
        import selo_no_papel as SNP
    except ImportError:
        return None
    endereco = SNP.link_de_consulta(numero)
    if not endereco:
        return None
    try:
        from io import BytesIO
        buf = BytesIO()
        segno.make(endereco, error="m").save(buf, kind="png", scale=6,
                                             border=0)
        return buf.getvalue() or None
    except Exception:                                        # noqa: BLE001
        return None


def __getattr__(nome: str):
    """Os nomes antigos do texto de fábrica, lidos da base dos padrões.

    O TEXTO SAIU DESTE MÓDULO NO LF06A (19/10/2026) e mora em `modelos_padrao/`.
    Quem ainda importa o nome antigo recebe o padrão da base — o MESMO que o
    papel imprime, e não uma cópia que ficou para trás. Nome que não é de papel
    continua sendo `AttributeError`.
    """
    if nome.startswith("__"):
        raise AttributeError(nome)
    import modelos_da_casa as _MODELOS
    return _MODELOS.constante_antiga(__name__, nome)
