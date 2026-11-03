"""A folha do livro do RCPN em ODT — as MESMAS três colunas e a MESMA pauta
da folha impressa (`templates/rcpn_folha_impressa.html`).

O DEFEITO (03/11/2026): o «Baixar ODT» da folha saía como texto corrido —
título, termo, carimbo, linhas de assinatura e notas, um parágrafo embaixo do
outro, **sem as três colunas e sem a pauta** da coluna de notas. O ODT editável
tinha nascido assim de propósito (o anterior era a folha virada imagem, que não
se editava), e a fidelidade ficou só no PDF. Mas quem edita o termo no
LibreOffice e imprime dali imprime uma folha que não é a do livro.

AGORA o ODT é montado como a folha HTML, peça por peça, e continua editável:

    • página carta em retrato (215 × 279 mm), margens da impressão;
    • cabeçalho com o brasão, a serventia, o título do ato e Termo/Livro/Folha;
    • a faixa das assinaturas do topo (três vãos);
    • a tabela de três colunas — «Número» (6%), «Termo» (64%) e «Notas,
      Averbações e Retificações» (30%) —, com as larguras de `rc_folha.COLUNAS`;
    • a 3ª coluna PAUTADA: linhas cinza a cada `rc_folha.PAUTA_PASSO_MM`, do
      título até embaixo, e as notas escritas no mesmo passo das linhas;
    • as linhas de assinatura no fim do termo (em par a partir de quatro, ou
      quando o termo é longo), o carimbo do selo, e a marca «Frente»;
    • o VERSO, em página própria, com o mesmo cabeçalho e a mesma pauta.

O aperto do termo longo é o mesmo da folha HTML (limites por espécie, letra e
entrelinha menores, assinaturas lado a lado), para a frente caber numa página.

Só monta o pacote: não lê banco, não grava nada.
"""
from __future__ import annotations

import re
from html import unescape
from pathlib import Path
from xml.sax.saxutils import escape as _esc

import rc_folha as FOLHA
import ri_odt as RODT

# --------------------------------------------------------------- a página
#
# A folha HTML se compõe com a margem da casa (12 mm) e a impressão amplia o
# desenho até a margem da impressora (5 mm). O ODT não tem esse «zoom»: a
# página já nasce com a margem da impressão, e as medidas da composição são
# multiplicadas pela mesma razão, para o papel sair do mesmo tamanho.
MARGEM_CM = FOLHA.MARGEM_DA_IMPRESSAO_MM / 10.0
MARGEM_TOPO_CM = FOLHA.MARGEM_TOPO_MM / 10.0
LARGURA_UTIL_CM = (FOLHA.LARGURA_MM - 2 * FOLHA.MARGEM_DA_IMPRESSAO_MM) / 10.0
ALTURA_UTIL_MM = (FOLHA.ALTURA_MM - FOLHA.MARGEM_TOPO_MM
                  - FOLHA.MARGEM_DA_IMPRESSAO_MM)
ZOOM = ((FOLHA.LARGURA_MM - 2 * FOLHA.MARGEM_DA_IMPRESSAO_MM)
        / (FOLHA.LARGURA_MM - 2 * FOLHA.MARGEM_MM))

# A altura do recanto pautado no papel: a mesma conta de
# `rc_folha._pauta_que_cabe`, já na escala do papel (o que fica fora da pauta
# também cresce com o zoom). Passos inteiros, para a última linha fechar.
PAUTA_PASSO_CM = FOLHA.PAUTA_PASSO_MM / 10.0
PAUTA_ALTURA_MM = float(
    int((ALTURA_UTIL_MM - FOLHA.RESERVA_FORA_DA_PAUTA_MM * ZOOM)
        // FOLHA.PAUTA_PASSO_MM) * FOLHA.PAUTA_PASSO_MM)
PAUTA_LINHAS = int(PAUTA_ALTURA_MM // FOLHA.PAUTA_PASSO_MM)

# O aperto do termo longo — os MESMOS limites da folha HTML
# (`rcpn_folha_impressa.html`, 03/11/2026): o óbito aperta antes.
LIMITES_DO_TERMO = {"OBITO": (1200, 1900)}
LIMITES_PADRAO = (1650, 2300)

BRASAO = Path(__file__).resolve().parent / "static" / "brasao.jpg"


def limites_do_termo(especie: str | None) -> tuple[int, int]:
    """(longo, muito longo) em letras, por espécie. Só calcula."""
    return LIMITES_DO_TERMO.get(str(especie or "").upper(), LIMITES_PADRAO)


def letras_do_termo(termo: str | None) -> int:
    """Quantas letras o termo tem sem as marcas (o `striptags|length`)."""
    sem = re.sub(r"<[^>]*>", "", termo or "")
    return len(" ".join(unescape(sem).split()))


def aperto_do_termo(termo: str | None, especie: str | None,
                    com_carimbo: bool) -> dict:
    """Letra, entrelinha e assinaturas da face, como as classes da folha HTML."""
    letras = letras_do_termo(termo)
    longo, muito = limites_do_termo(especie)
    eh_longo, eh_muito = letras > longo, letras > muito
    letra, entrelinha = 10.5, 135
    if eh_longo:
        letra, entrelinha = 9.5, 126
    if eh_muito:
        letra, entrelinha = 9.0, 120
        if com_carimbo:
            letra, entrelinha = 8.5, 115
    vao_ass_mm = 9.0
    if eh_longo:
        vao_ass_mm = 7.0 if com_carimbo else 8.0
    return {"letras": letras, "longo": eh_longo, "muito_longo": eh_muito,
            "letra_pt": letra, "entrelinha": entrelinha,
            "vao_assinatura_mm": vao_ass_mm}


# ---------------------------------------------------------------- a pauta
# A pauta é feita de PARÁGRAFOS, um por linha: entrelinha fixa e um fio cinza
# embaixo de cada um (sem juntar bordas). Imagem de fundo em célula de tabela
# o LibreOffice 25 não desenha (testado em 03/11/2026) e o Word também não —
# parágrafo com borda os dois desenham, e quem edita escreve EM CIMA da linha
# e o Enter puxa outra linha pautada.
FIO_DA_PAUTA_PT = 0.5
_FIO_CM = FIO_DA_PAUTA_PT * 2.54 / 72
ENTRELINHA_DA_PAUTA_CM = round(PAUTA_PASSO_CM - _FIO_CM, 4)
LETRA_DA_NOTA_PT = 8.5
# Quantas letras "médias" cabem numa linha da coluna de notas (meia letra-
# -quadrada por letra; maiúscula conta 1,4). As notas do sistema já entram
# quebradas nessa medida, para cada linha escrita cair numa linha da pauta.
_LARGURA_NOTA_CM = LARGURA_UTIL_CM * FOLHA.COLUNAS[2]["largura"] - 0.26
LETRAS_POR_LINHA_DA_NOTA = int(
    _LARGURA_NOTA_CM / (LETRA_DA_NOTA_PT * 0.5 * 2.54 / 72))


def _peso(palavra: str) -> float:
    return sum(1.4 if c.isupper() else 1.0 for c in palavra)


def linhas_da_nota(texto: str, cabe: int = 0) -> list[str]:
    """Quebra a nota em linhas que cabem numa linha da pauta."""
    cabe = cabe or LETRAS_POR_LINHA_DA_NOTA
    linhas, atual, usado = [], [], 0.0
    for palavra in (texto or "").split():
        while _peso(palavra) > cabe:  # palavra (URL, selo) maior que a linha
            corte = len(palavra)
            while corte > 1 and _peso(palavra[:corte]) > cabe:
                corte -= 1
            if atual:
                linhas.append(" ".join(atual))
                atual, usado = [], 0.0
            linhas.append(palavra[:corte])
            palavra = palavra[corte:]
        p = _peso(palavra) + (1 if atual else 0)
        if atual and usado + p > cabe:
            linhas.append(" ".join(atual))
            atual, usado = [], 0.0
            p = _peso(palavra)
        if palavra:
            atual.append(palavra)
            usado += p
    if atual:
        linhas.append(" ".join(atual))
    return linhas


def _pauta(notas: list[str]) -> str:
    """A coluna de notas: as notas, linha a linha, e o resto da pauta vazio,
    até completar `PAUTA_LINHAS` linhas."""
    linhas = [ln for n in notas for ln in linhas_da_nota(n)]
    linhas += [""] * max(0, PAUTA_LINHAS - len(linhas))
    return "".join(_p("FL-nota", ln) for ln in linhas)


# --------------------------------------------------------------- os estilos
def _larguras_cm() -> list[float]:
    return [round(LARGURA_UTIL_CM * c["largura"], 3) for c in FOLHA.COLUNAS]


def _estilos(apertos: list[dict]) -> str:
    """Os estilos automáticos da folha (vão para o content.xml)."""
    l_num, l_termo, l_notas = _larguras_cm()
    borda = "1.2pt solid #000000"
    fina = "0.6pt solid #000000"
    selo_cm = round(l_termo - 0.3, 2)
    s = [
        # Página nova para o verso.
        '<style:style style:name="FL-quebra" style:family="paragraph" '
        'style:parent-style-name="Standard"><style:paragraph-properties '
        'fo:break-before="page" fo:text-align="center" fo:margin-top="0cm" '
        'fo:margin-bottom="0.06cm"/><style:text-properties fo:font-size="10.5pt"/>'
        '</style:style>',
        '<style:style style:name="FL-brasao" style:family="paragraph" '
        'style:parent-style-name="Standard"><style:paragraph-properties '
        'fo:text-align="center" fo:margin-top="0cm" fo:margin-bottom="0.06cm"/>'
        '<style:text-properties fo:font-size="10.5pt"/></style:style>',
        '<style:style style:name="FL-cab" style:family="paragraph" '
        'style:parent-style-name="Standard"><style:paragraph-properties '
        'fo:text-align="center" fo:margin-top="0cm" fo:margin-bottom="0cm" '
        'fo:line-height="112%"/><style:text-properties '
        'style:font-name="Times New Roman" fo:font-size="10.5pt"/></style:style>',
        '<style:style style:name="FL-cab-titulo" style:family="paragraph" '
        'style:parent-style-name="FL-cab"><style:paragraph-properties '
        'fo:margin-top="0.05cm"/></style:style>',
        '<style:style style:name="FL-loc-esq" style:family="paragraph" '
        'style:parent-style-name="Standard"><style:paragraph-properties '
        'fo:text-align="start" fo:margin-top="0cm" fo:margin-bottom="0cm"/>'
        '<style:text-properties fo:font-size="9.5pt"/></style:style>',
        '<style:style style:name="FL-loc-meio" style:family="paragraph" '
        'style:parent-style-name="FL-loc-esq"><style:paragraph-properties '
        'fo:text-align="center"/></style:style>',
        '<style:style style:name="FL-loc-dir" style:family="paragraph" '
        'style:parent-style-name="FL-loc-esq"><style:paragraph-properties '
        'fo:text-align="end"/></style:style>',
        '<style:style style:name="FL-negrito" style:family="text">'
        '<style:text-properties fo:font-weight="bold"/></style:style>',
        # A linha Termo/Livro/Folha: três vãos sem borda.
        f'<style:style style:name="FL-tab-loc" style:family="table">'
        f'<style:table-properties style:width="{LARGURA_UTIL_CM}cm" '
        'table:align="margins" fo:margin-top="0.05cm" fo:margin-bottom="0.1cm"/>'
        '</style:style>',
        f'<style:style style:name="FL-col-terco" style:family="table-column">'
        f'<style:table-column-properties style:column-width='
        f'"{round(LARGURA_UTIL_CM / 3, 3)}cm"/></style:style>',
        '<style:style style:name="FL-cel-lisa" style:family="table-cell">'
        '<style:table-cell-properties fo:padding="0cm" fo:border="none"/>'
        '</style:style>',
        # A faixa das assinaturas do topo: 5 mm, risco grosso embaixo.
        f'<style:style style:name="FL-tab-faixa" style:family="table">'
        f'<style:table-properties style:width="{LARGURA_UTIL_CM}cm" '
        'table:align="margins" fo:margin-top="0cm" fo:margin-bottom="0cm"/>'
        '</style:style>',
        '<style:style style:name="FL-lin-faixa" style:family="table-row">'
        '<style:table-row-properties style:row-height="0.54cm" '
        'style:use-optimal-row-height="false"/></style:style>',
        f'<style:style style:name="FL-cel-faixa" style:family="table-cell">'
        f'<style:table-cell-properties fo:padding="0cm" fo:border-top="none" '
        f'fo:border-left="none" fo:border-bottom="{borda}" '
        f'fo:border-right="{fina}"/></style:style>',
        f'<style:style style:name="FL-cel-faixa-fim" style:family="table-cell">'
        f'<style:table-cell-properties fo:padding="0cm" fo:border-top="none" '
        f'fo:border-left="none" fo:border-right="none" '
        f'fo:border-bottom="{borda}"/></style:style>',
        '<style:style style:name="FL-vazio" style:family="paragraph" '
        'style:parent-style-name="Standard"><style:paragraph-properties '
        'fo:margin-top="0cm" fo:margin-bottom="0cm"/><style:text-properties '
        'fo:font-size="2pt"/></style:style>',
        # AS TRÊS COLUNAS.
        f'<style:style style:name="FL-tab-colunas" style:family="table">'
        f'<style:table-properties style:width="{LARGURA_UTIL_CM}cm" '
        'table:align="margins" fo:margin-top="0cm" fo:margin-bottom="0cm" '
        'style:may-break-between-rows="false"/></style:style>',
        f'<style:style style:name="FL-col-numero" style:family="table-column">'
        f'<style:table-column-properties style:column-width="{l_num}cm" '
        'style:use-optimal-column-width="false"/></style:style>',
        f'<style:style style:name="FL-col-termo" style:family="table-column">'
        f'<style:table-column-properties style:column-width="{l_termo}cm" '
        'style:use-optimal-column-width="false"/></style:style>',
        f'<style:style style:name="FL-col-notas" style:family="table-column">'
        f'<style:table-column-properties style:column-width="{l_notas}cm" '
        'style:use-optimal-column-width="false"/></style:style>',
        f'<style:style style:name="FL-cel-titulo" style:family="table-cell">'
        f'<style:table-cell-properties fo:padding-top="0.08cm" '
        f'fo:padding-bottom="0.08cm" fo:padding-left="0.1cm" '
        f'fo:padding-right="0.1cm" fo:border-top="none" fo:border-left="none" '
        f'fo:border-right="none" fo:border-bottom="{borda}" '
        'style:vertical-align="bottom"/></style:style>',
        '<style:style style:name="FL-titulo-col" style:family="paragraph" '
        'style:parent-style-name="Standard"><style:paragraph-properties '
        'fo:text-align="center" fo:margin-top="0cm" fo:margin-bottom="0cm"/>'
        '<style:text-properties style:font-name="Arial" fo:font-size="8pt"/>'
        '</style:style>',
        f'<style:style style:name="FL-lin-corpo" style:family="table-row">'
        f'<style:table-row-properties style:min-row-height='
        f'"{PAUTA_ALTURA_MM / 10:g}cm" style:keep-together="always"/>'
        '</style:style>',
        f'<style:style style:name="FL-cel-numero" style:family="table-cell">'
        f'<style:table-cell-properties fo:padding-top="0.13cm" '
        f'fo:padding-bottom="0.13cm" fo:padding-left="0.04cm" '
        f'fo:padding-right="0.04cm" fo:border-top="none" fo:border-left="none" '
        f'fo:border-bottom="none" fo:border-right="{borda}" '
        'style:vertical-align="top"/></style:style>',
        '<style:style style:name="FL-numero" style:family="paragraph" '
        'style:parent-style-name="Standard"><style:paragraph-properties '
        'fo:text-align="center" fo:margin-top="0.2cm" fo:margin-bottom="0cm"/>'
        '<style:text-properties fo:font-size="8.5pt"/></style:style>',
        f'<style:style style:name="FL-cel-termo" style:family="table-cell">'
        f'<style:table-cell-properties fo:padding="0.13cm" fo:border-top="none" '
        f'fo:border-left="none" fo:border-bottom="none" '
        f'fo:border-right="{borda}" style:vertical-align="top"/></style:style>',
        # A 3ª COLUNA PAUTADA: uma linha da pauta por parágrafo (ver _pauta).
        f'<style:style style:name="FL-cel-notas" style:family="table-cell">'
        f'<style:table-cell-properties fo:padding-top="0cm" '
        f'fo:padding-bottom="0cm" fo:padding-left="0.13cm" '
        f'fo:padding-right="0.13cm" fo:border="none" '
        'style:vertical-align="top"/></style:style>',
        f'<style:style style:name="FL-nota" style:family="paragraph" '
        f'style:parent-style-name="Standard"><style:paragraph-properties '
        f'fo:text-align="start" fo:margin-top="0cm" fo:margin-bottom="0cm" '
        f'fo:line-height="{ENTRELINHA_DA_PAUTA_CM:g}cm" fo:padding="0cm" '
        f'fo:border-top="none" fo:border-left="none" fo:border-right="none" '
        f'fo:border-bottom="{FIO_DA_PAUTA_PT:g}pt solid #999999" '
        'style:join-border="false"/><style:text-properties '
        f'fo:font-size="{LETRA_DA_NOTA_PT:g}pt"/></style:style>',
        '<style:style style:name="FL-marca-face" style:family="paragraph" '
        'style:parent-style-name="Standard"><style:paragraph-properties '
        'fo:text-align="end" fo:margin-top="0.08cm" fo:margin-bottom="0cm"/>'
        '<style:text-properties style:font-name="Arial" fo:font-size="7.5pt" '
        'fo:color="#555555"/></style:style>',
        # O carimbo do selo cabe na coluna do termo (o padrão tem 16 cm).
        f'<style:style style:name="FL-tab-selo" style:family="table">'
        f'<style:table-properties style:width="{selo_cm}cm" table:align="left" '
        'fo:margin-top="0.05cm" fo:margin-bottom="0.05cm"/></style:style>',
        f'<style:style style:name="FL-col-selo" style:family="table-column">'
        f'<style:table-column-properties style:column-width="{selo_cm}cm" '
        'style:use-optimal-column-width="false"/></style:style>',
        f'<style:style style:name="FL-tab-selo-int" style:family="table">'
        f'<style:table-properties style:width="{round(selo_cm - 0.3, 2)}cm" '
        'table:align="left" fo:margin-top="0cm" fo:margin-bottom="0cm"/>'
        '</style:style>',
        f'<style:style style:name="FL-col-selo-txt" style:family="table-column">'
        f'<style:table-column-properties style:column-width='
        f'"{round(selo_cm - 0.3 - 1.45, 2)}cm" '
        'style:use-optimal-column-width="false"/></style:style>',
        # Assinaturas.
        f'<style:style style:name="FL-tab-ass" style:family="table">'
        f'<style:table-properties style:width="{round(l_termo - 0.26, 2)}cm" '
        'table:align="left" fo:margin-top="0cm" fo:margin-bottom="0cm"/>'
        '</style:style>',
        f'<style:style style:name="FL-col-ass" style:family="table-column">'
        f'<style:table-column-properties style:column-width='
        f'"{round((l_termo - 0.26) / 2, 3)}cm"/></style:style>',
        '<style:style style:name="FL-cel-ass" style:family="table-cell">'
        '<style:table-cell-properties fo:padding-left="0.1cm" '
        'fo:padding-right="0.1cm" fo:padding-top="0cm" fo:padding-bottom="0cm" '
        'fo:border="none"/></style:style>',
        '<style:style style:name="FL-ass-nome" style:family="paragraph" '
        'style:parent-style-name="Standard"><style:paragraph-properties '
        'fo:text-align="center" fo:margin-top="0cm" fo:margin-bottom="0cm" '
        'fo:keep-together="always"/><style:text-properties fo:font-size="9.5pt"/>'
        '</style:style>',
    ]
    # Por face: o termo e as linhas de assinatura com o aperto da face.
    for i, ap in enumerate(apertos):
        s.append(
            f'<style:style style:name="FL-termo-{i}" style:family="paragraph" '
            f'style:parent-style-name="Standard"><style:paragraph-properties '
            f'fo:text-align="justify" fo:margin-top="0cm" fo:margin-bottom="0cm" '
            f'fo:line-height="{ap["entrelinha"]}%"/><style:text-properties '
            f'style:font-name="Times New Roman" fo:font-size="{ap["letra_pt"]:g}pt"/>'
            '</style:style>')
        vao = ap["vao_assinatura_mm"] / 10
        s.append(
            f'<style:style style:name="FL-ass-linha-{i}" style:family="paragraph" '
            f'style:parent-style-name="Standard"><style:paragraph-properties '
            f'fo:text-align="center" fo:margin-top="{vao:g}cm" '
            'fo:margin-bottom="0cm" fo:line-height="100%" '
            'fo:keep-with-next="always"/><style:text-properties '
            'fo:font-size="10.5pt"/></style:style>')
        s.append(
            f'<style:style style:name="FL-ass-linha-par-{i}" '
            f'style:family="paragraph" style:parent-style-name="FL-ass-linha-{i}">'
            '<style:text-properties fo:font-size="7.5pt"/></style:style>')
    return "".join(s)


# ----------------------------------------------------------------- as peças
def _p(estilo: str, texto: str = "", *, negrito: bool = False) -> str:
    if not texto:
        return f'<text:p text:style-name="{estilo}"/>'
    t = _esc(str(texto))
    if negrito:
        t = f'<text:span text:style-name="FL-negrito">{t}</text:span>'
    return f'<text:p text:style-name="{estilo}">{t}</text:p>'


def _tamanho_do_brasao() -> tuple[float, float]:
    """(largura, altura) em cm do brasão a 15 mm de altura, como no HTML."""
    altura = round(1.5 * ZOOM, 2)
    try:
        from PIL import Image
        with Image.open(BRASAO) as im:
            w, h = im.size
        return round(altura * w / h, 2), altura
    except Exception:  # noqa: BLE001 — sem Pillow, o brasão sai quadrado
        return altura, altura


def _cabecalho(cab: dict, imagens: dict, primeira: bool) -> str:
    """Brasão, serventia, título do ato e Termo/Livro/Folha. Só monta."""
    estilo_1 = "FL-brasao" if primeira else "FL-quebra"
    partes = []
    if BRASAO.is_file():
        imagens.setdefault("brasao.jpg", (BRASAO.read_bytes(), "image/jpeg"))
        w, h = _tamanho_do_brasao()
        partes.append(
            f'<text:p text:style-name="{estilo_1}">'
            f'<draw:frame draw:style-name="Fr-qr" text:anchor-type="as-char" '
            f'svg:width="{w}cm" svg:height="{h}cm"><draw:image '
            'xlink:href="Pictures/brasao.jpg" xlink:type="simple" '
            'xlink:show="embed" xlink:actuate="onLoad"/></draw:frame></text:p>')
    else:
        partes.append(_p(estilo_1))
    titular = str(cab.get("titular") or "")
    qualidade = str(cab.get("titular_qualidade") or "")
    partes.append(_p("FL-cab", cab.get("pais") or ""))
    partes.append(_p("FL-cab", cab.get("unidade") or "", negrito=True))
    linha_titular = (f'<text:span text:style-name="FL-negrito">{_esc(titular)}'
                     '</text:span>')
    if qualidade:
        linha_titular += f" — {_esc(qualidade)}"
    partes.append(f'<text:p text:style-name="FL-cab">{linha_titular}</text:p>')
    partes.append(_p("FL-cab", cab.get("endereco") or ""))
    partes.append(_p("FL-cab", cab.get("contato") or ""))
    partes.append(_p("FL-cab-titulo", cab.get("titulo_do_ato") or "",
                     negrito=True))

    def loc(estilo, rotulo, valor):
        return ('<table:table-cell table:style-name="FL-cel-lisa" '
                f'office:value-type="string"><text:p text:style-name="{estilo}">'
                f'<text:span text:style-name="FL-negrito">{rotulo}: '
                f'{_esc(str(valor or ""))}</text:span></text:p></table:table-cell>')

    partes.append(
        '<table:table table:name="FolhaLocalizacao" '
        'table:style-name="FL-tab-loc">'
        '<table:table-column table:style-name="FL-col-terco" '
        'table:number-columns-repeated="3"/><table:table-row>'
        + loc("FL-loc-esq", "Termo", cab.get("termo"))
        + loc("FL-loc-meio", "Livro", cab.get("livro"))
        + loc("FL-loc-dir", "Folha", cab.get("folha"))
        + "</table:table-row></table:table>")
    return "".join(partes)


def _faixa_de_assinaturas() -> str:
    """Os três vãos do topo, onde as testemunhas assinam atravessando."""
    cel = ('<table:table-cell table:style-name="{e}" office:value-type="string">'
           '<text:p text:style-name="FL-vazio"/></table:table-cell>')
    return ('<table:table table:name="FolhaFaixaDoTopo" '
            'table:style-name="FL-tab-faixa">'
            '<table:table-column table:style-name="FL-col-terco" '
            'table:number-columns-repeated="3"/>'
            '<table:table-row table:style-name="FL-lin-faixa">'
            + cel.format(e="FL-cel-faixa") + cel.format(e="FL-cel-faixa")
            + cel.format(e="FL-cel-faixa-fim")
            + "</table:table-row></table:table>")


def _termo_odf(termo: str, i: int) -> str:
    """O termo em parágrafos editáveis, na letra da face.

    A folha HTML mostra o termo com `white-space: pre-wrap`: a quebra de linha
    que o texto traz É quebra no papel. Aqui ela vira `<br>` antes de passar
    pelo conversor, que juntaria as linhas.
    """
    termo = (termo or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not termo:
        return f'<text:p text:style-name="FL-termo-{i}"/>'
    odf = RODT.html_para_odf(termo.replace("\n", "<br>"))
    return re.sub(r'(<text:p\b[^>]*?)text:style-name="[^"]*"',
                  rf'\1text:style-name="FL-termo-{i}"', odf)


def _carimbo_na_coluna(carimbo_odf: str) -> str:
    """O carimbo do selo com a largura da coluna do termo (padrão: 16 cm)."""
    return (carimbo_odf
            .replace('table:style-name="Tab-selos-compactos"',
                     'table:style-name="FL-tab-selo"')
            .replace('table:style-name="Col-selo-inteiro"',
                     'table:style-name="FL-col-selo"')
            .replace('table:style-name="Tab-selo-interno-largo"',
                     'table:style-name="FL-tab-selo-int"')
            .replace('table:style-name="Col-selo-texto-larga"',
                     'table:style-name="FL-col-selo-txt"'))


def _uma_assinatura(a: dict, estilo_linha: str) -> str:
    nome = str(a.get("nome") or "")
    qualidade = str(a.get("qualidade") or "")
    rotulo = nome + (", " if nome and qualidade else "") + qualidade
    return (f'<text:p text:style-name="{estilo_linha}">{"_" * 45}</text:p>'
            + _p("FL-ass-nome", rotulo))


def _assinaturas(assinaturas: list[dict], i: int, em_par: bool) -> str:
    """As linhas de quem assina, embaixo do termo. Em par: tabela sem borda."""
    if not assinaturas:
        return ""
    if not em_par:
        return "".join(_uma_assinatura(a, f"FL-ass-linha-{i}")
                       for a in assinaturas)
    linhas = []
    for k in range(0, len(assinaturas), 2):
        par = assinaturas[k:k + 2]
        celulas = "".join(
            '<table:table-cell table:style-name="FL-cel-ass" '
            'office:value-type="string">'
            + _uma_assinatura(a, f"FL-ass-linha-par-{i}")
            + "</table:table-cell>" for a in par)
        if len(par) < 2:
            celulas += ('<table:table-cell table:style-name="FL-cel-ass" '
                        'office:value-type="string"><text:p '
                        'text:style-name="FL-vazio"/></table:table-cell>')
        linhas.append(f"<table:table-row>{celulas}</table:table-row>")
    return ('<table:table table:name="FolhaAssinaturas{0}" '
            'table:style-name="FL-tab-ass">'
            '<table:table-column table:style-name="FL-col-ass" '
            'table:number-columns-repeated="2"/>'.format(i)
            + "".join(linhas) + "</table:table>")


def _colunas(face: dict, i: int, ap: dict, carimbo_odf: str) -> str:
    """A tabela das três colunas de uma face. Só monta."""
    titulos = "".join(
        '<table:table-cell table:style-name="FL-cel-titulo" '
        f'office:value-type="string">{_p("FL-titulo-col", c["titulo"])}'
        "</table:table-cell>" for c in FOLHA.COLUNAS)
    numero = str(face.get("numero") or "")
    assinaturas = face.get("assinaturas") or []
    em_par = (len(assinaturas) >= FOLHA.ASSINATURAS_EM_PAR_A_PARTIR_DE
              or ap["longo"])
    termo = _termo_odf(face.get("termo") or "", i)
    if carimbo_odf:
        termo += _carimbo_na_coluna(carimbo_odf)
    termo += _assinaturas(assinaturas, i, em_par)
    notas = _pauta(list(face.get("notas_coluna") or []))
    return (
        f'<table:table table:name="FolhaColunas{i}" '
        'table:style-name="FL-tab-colunas">'
        '<table:table-column table:style-name="FL-col-numero"/>'
        '<table:table-column table:style-name="FL-col-termo"/>'
        '<table:table-column table:style-name="FL-col-notas"/>'
        f"<table:table-header-rows><table:table-row>{titulos}"
        "</table:table-row></table:table-header-rows>"
        '<table:table-row table:style-name="FL-lin-corpo">'
        '<table:table-cell table:style-name="FL-cel-numero" '
        f'office:value-type="string">{_p("FL-numero", numero)}'
        "</table:table-cell>"
        '<table:table-cell table:style-name="FL-cel-termo" '
        f'office:value-type="string">{termo}</table:table-cell>'
        '<table:table-cell table:style-name="FL-cel-notas" '
        f'office:value-type="string">{notas}</table:table-cell>'
        "</table:table-row></table:table>")


def gerar(ctx: dict, *, titulo: str = "", etiqueta: str = "",
          prefixo_qr: str = "qr-rcpn") -> bytes:
    """O .odt da folha do livro, frente e verso, a partir do mesmo contexto da
    folha HTML (`_contexto_folha_do_assento`). Só monta o pacote.

    `etiqueta` é o selo do REGISTRO: o carimbo (QR, número e valores) sai na
    coluna do termo da face que já traz o carimbo na folha HTML.
    """
    faces = list(ctx.get("faces") or [])
    especie = ctx.get("especie") or (ctx.get("assento") or {}).get("especie")
    cab = ctx.get("cabecalho") or {}
    imagens: dict = {}
    apertos, carimbos = [], []
    for face in faces:
        carimbo = ""
        if etiqueta and face.get("carimbo"):
            carimbo = RODT.carimbo_compacto_odf(
                etiqueta, rotulo="SELO DIGITAL DO TJMA", imagens=imagens,
                prefixo_qr=prefixo_qr)
        carimbos.append(carimbo)
        apertos.append(aperto_do_termo(face.get("termo"), especie,
                                       bool(carimbo)))
    corpo = []
    for i, face in enumerate(faces):
        if cab:
            corpo.append(_cabecalho(cab, imagens, primeira=(i == 0)))
        elif i:
            corpo.append(_p("FL-quebra"))
        if FOLHA.FAIXA_DE_ASSINATURAS_NO_TOPO:
            corpo.append(_faixa_de_assinaturas())
        corpo.append(_colunas(face, i, apertos[i], carimbos[i]))
        corpo.append(_p("FL-marca-face", face.get("rotulo") or ""))
    return RODT.gerar_odt(
        "".join(corpo), titulo=titulo, imagens=imagens,
        pagina_largura_cm=FOLHA.LARGURA_MM / 10,
        pagina_altura_cm=FOLHA.ALTURA_MM / 10,
        margem_cm=MARGEM_CM,
        estilos_do_conteudo=_estilos(apertos))
