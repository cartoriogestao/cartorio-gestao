"""Levar o teor para o LibreOffice e trazê-lo de volta, COM A FORMATAÇÃO.

O PEDIDO DO OFICIAL, em 27/08/2026:

    «O teor do ato não sai formatado e visível como ficará completo pra quem
     lavra. Ideal seria incorporar uma suíte do LibreOffice… Se não for
     possível, possibilitar em botão facilitado a exportação do arquivo base e
     permitir a importação do arquivo odt ou docx após a edição.»

E a correção dele, em 28/08/2026, sobre a primeira entrega:

    «Negrito é fundamental para o layout da escritura, preciso de uma solução
     perfeita, é a atividade fim do cartório.»

    Ele está certo, e a primeira versão deste módulo estava errada: ela trazia
    de volta só os parágrafos, em texto cru. **Num ato notarial o negrito é o
    que separa a qualificação da cláusula, o nome da parte do corpo do texto e
    o que se lê em voz alta do que se lê em silêncio.** Trazer o teor sem ele é
    devolver um ato desformatado para ser reformatado à mão — que é pior que
    não ter exportado.

O QUE VOLTA AGORA
    **Negrito, itálico e sublinhado**, além dos parágrafos. São as três marcas
    que o gerador de `.odt` desta casa já sabia ESCREVER (`T-negrito`,
    `T-italico`, `T-sublinhado`) — a ida sempre as levou; era a volta que as
    perdia.

O PONTO DIFÍCIL, E É ELE QUE FAZ ISTO FUNCIONAR DE VERDADE
    O arquivo que volta **não é o que saiu**. Quando o escrevente abre no
    LibreOffice e salva, o programa reescreve os estilos com nomes próprios —
    `T1`, `T2`, `T3` — e a formatação passa a morar nas PROPRIEDADES daquele
    estilo, e não no nome dele.

    Por isso a leitura não procura nomes conhecidos: ela **lê a tabela de
    estilos do próprio arquivo**, resolve a herança (`style:parent-style-name`)
    e descobre quais nomes significam negrito naquele documento. Procurar
    `T-negrito` funcionaria só com o arquivo que nunca foi aberto — que é
    justamente o que não interessa.

O QUE AINDA NÃO VOLTA, e a tela diz
    Tabela, imagem, cor e tamanho de letra. O teor desta casa é feito de
    parágrafos com ênfase; prometer o resto seria entregar um teor que parece o
    do LibreOffice e não é.
"""
from __future__ import annotations

import html as _html
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import Any

import tetos_de_entrada as TETO


class TeorArquivoError(ValueError):
    """Impedimento de regra, com mensagem pronta para o balcao."""


# Os dois formatos que a volta aceita. `.doc` antigo (binario) fica de fora: ler
# aquele formato exige biblioteca propria, e o LibreOffice grava `.odt` por
# padrao — pedir «salve como .odt» e mais honesto que ler pela metade.
EXTENSOES = (".odt", ".docx")

_CONTEUDO = {".odt": "content.xml", ".docx": "word/document.xml"}

# Os espacos de nome que interessam, nos dois formatos.
_ODF = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
}
_OOXML = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

# AS TRES MARCAS QUE VOLTAM, e a etiqueta de cada uma no teor da casa.
#
#   `<b>`, `<i>` e `<u>` — que sao as que `ri_odt.html_para_odf` sabe escrever
#   de volta. Fechar o ciclo com as mesmas tres dos dois lados e o que faz a
#   ida e volta ser prova de coisa nenhuma perdida.
MARCAS = ("negrito", "italico", "sublinhado",
          "tachado_vermelho", "destaque_amarelo", "destaque_vermelho")
ETIQUETA = {"negrito": "b", "italico": "i", "sublinhado": "u",
            "tachado_vermelho": "s", "destaque_amarelo": "mark",
            "destaque_vermelho": "mark"}
ABRE_MARCA = {
    "tachado_vermelho": '<s style="color:#c62828">',
    "destaque_amarelo": '<mark style="background:#fff59d">',
    "destaque_vermelho": '<mark style="background:#ffcdd2">',
}
FECHA_MARCA = {
    "tachado_vermelho": "</s>",
    "destaque_amarelo": "</mark>",
    "destaque_vermelho": "</mark>",
}


def _extensao(nome: Any) -> str:
    nome = str(nome or "").lower().strip()
    for ext in EXTENSOES:
        if nome.endswith(ext):
            return ext
    raise TeorArquivoError(
        f"Só entram arquivos {' ou '.join(EXTENSOES)}. O LibreOffice grava "
        f"`.odt` por padrão, e o Word grava `.docx` — salve num dos dois e "
        f"envie de novo.")


def _abrir(conteudo: bytes, ext: str) -> ET.Element:
    """O XML do conteúdo do arquivo — com teto do que ele descompacta.

    O TETO É DO LX12 (LS02 M1, 19/10/2026): `pacote.read` lia o `content.xml`
    sem limite, e um `.odt` de 1 KB que se abre em gigabytes (zip-bomba)
    derrubava o único processo do servidor. O teto é o da casa
    (`tetos_de_entrada`), generoso: nenhum teor de verdade chega perto.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
            TETO.conferir_pacote(pacote)
            bruto = TETO.ler_membro(pacote, _CONTEUDO[ext])
    except TETO.TetoExcedido as erro:
        raise TeorArquivoError(str(erro)) from erro
    except KeyError as erro:
        raise TeorArquivoError(
            f"Este arquivo {ext} não tem o conteúdo esperado dentro. Se ele "
            f"veio de outro programa, abra no LibreOffice e salve de novo."
        ) from erro
    except (zipfile.BadZipFile, OSError) as erro:
        raise TeorArquivoError(
            "Não consegui abrir o arquivo — ele pode estar corrompido, "
            "incompleto ou protegido por senha.") from erro
    try:
        return ET.fromstring(bruto)
    except ET.ParseError as erro:
        raise TeorArquivoError(
            "O conteúdo do arquivo está danificado. Abra no LibreOffice e "
            "salve de novo.") from erro


# ------------------------------------------------------- ler o .odt


def _estilos_do_odt(raiz: ET.Element) -> dict[str, set[str]]:
    """Quais nomes de estilo significam negrito, itálico ou sublinhado.

    LÊ A TABELA DO PRÓPRIO ARQUIVO, e não uma lista de nomes conhecidos. O
    LibreOffice reescreve os estilos com nomes próprios ao salvar — `T1`, `T2`
    —, e procurar `T-negrito` funcionaria só no arquivo que nunca foi aberto.

    RESOLVE A HERANÇA, porque o LibreOffice a usa: um estilo `T3` pode herdar
    de `T1` e só acrescentar o itálico. Sem resolver, o negrito do pai sumiria.
    """
    bruto: dict[str, tuple[set[str], str | None]] = {}
    for estilo in raiz.iter(f'{{{_ODF["style"]}}}style'):
        if estilo.get(f'{{{_ODF["style"]}}}family') != "text":
            continue
        nome = estilo.get(f'{{{_ODF["style"]}}}name')
        if not nome:
            continue
        marcas: set[str] = set()
        for props in estilo.iter(f'{{{_ODF["style"]}}}text-properties'):
            peso = (props.get(f'{{{_ODF["fo"]}}}font-weight') or "").lower()
            if peso and peso not in ("normal", "inherit"):
                marcas.add("negrito")
            estilo_letra = (props.get(f'{{{_ODF["fo"]}}}font-style') or "").lower()
            if estilo_letra in ("italic", "oblique"):
                marcas.add("italico")
            sublinha = (props.get(
                f'{{{_ODF["style"]}}}text-underline-style') or "").lower()
            if sublinha and sublinha != "none":
                marcas.add("sublinhado")
            risca = (props.get(
                f'{{{_ODF["style"]}}}text-line-through-style') or "").lower()
            if risca and risca != "none":
                marcas.add("tachado_vermelho")
            fundo = (props.get(f'{{{_ODF["fo"]}}}background-color') or "").lower()
            if fundo and fundo not in ("transparent", "none", "#ffffff", "#fff"):
                if any(x in fundo for x in ("fff59d", "ffeb3b", "ffff00", "ff0")):
                    marcas.add("destaque_amarelo")
                elif any(x in fundo for x in ("ffcdd2", "ef9a9a", "e57373", "f44336", "ffcdd")):
                    marcas.add("destaque_vermelho")
                else:
                    marcas.add("destaque_amarelo")
        pai = estilo.get(f'{{{_ODF["style"]}}}parent-style-name')
        bruto[nome] = (marcas, pai)

    # E O NOME AINDA CONTA, como último recurso: o arquivo que a casa acabou de
    # gerar e que ninguém abriu traz `T-negrito` com as propriedades no
    # `styles.xml`, que não está neste XML. Lê-lo pelo nome fecha esse caso sem
    # depender de abrir o segundo arquivo do pacote.
    for nome in list(bruto):
        for marca in MARCAS:
            if nome == f"T-{marca}":
                bruto[nome][0].add(marca)

    resolvido: dict[str, set[str]] = {}

    def resolver(nome: str, vistos: frozenset[str] = frozenset()) -> set[str]:
        if nome in resolvido:
            return resolvido[nome]
        if nome in vistos:                  # herança circular: para aqui
            return set()
        marcas, pai = bruto.get(nome, (set(), None))
        completo = set(marcas)
        if pai and pai in bruto:
            completo |= resolver(pai, vistos | {nome})
        elif pai:
            for marca in MARCAS:
                if pai == f"T-{marca}":
                    completo.add(marca)
        resolvido[nome] = completo
        return completo

    for nome in bruto:
        resolver(nome)
    # Os nomes que a casa escreve continuam valendo mesmo sem estilo declarado.
    for marca in MARCAS:
        resolvido.setdefault(f"T-{marca}", {marca})
    return resolvido


def _texto_do_odt(no: ET.Element, estilos: dict[str, set[str]],
                  herdadas: frozenset[str] = frozenset()) -> str:
    """O conteúdo de um nó, com as marcas em HTML. Só calcula."""
    partes: list[str] = []

    def escrever(texto: str | None, marcas: frozenset[str]) -> None:
        if not texto:
            return
        corpo = _html.escape(texto)
        # A ORDEM DO ANINHAMENTO É FIXA: `<b><i><u>`, sempre.
        #
        #   Envolve-se de dentro para fora — sublinhado primeiro, negrito por
        #   último —, e por isso o laço vai ao contrário. Sem ordem fixa, o
        #   mesmo trecho voltaria `<i><b>` numa vez e `<b><i>` noutra, e a
        #   ida e volta deixaria de ser prova de coisa nenhuma perdida: ela
        #   acusaria diferença onde não há.
        for marca in reversed(MARCAS):
            if marca in marcas:
                if marca in ABRE_MARCA:
                    corpo = ABRE_MARCA[marca] + corpo + FECHA_MARCA[marca]
                else:
                    etiqueta = ETIQUETA[marca]
                    corpo = f"<{etiqueta}>{corpo}</{etiqueta}>"
        partes.append(corpo)

    escrever(no.text, herdadas)
    for filho in no:
        marca = filho.tag.split("}")[-1]
        if marca == "s":                    # <text:s/> — espaços
            # COM TETO (LX12, LS02 M1): `text:c="2000000000"` pedia dois
            # bilhões de espaços — 2 GB num elemento de 30 bytes — e
            # `text:c="abc"` dava 500. Inválido vale 1, como no ODF sem c.
            quantos = filho.get(f'{{{_ODF["text"]}}}c')
            partes.append(" " * TETO.vezes_text_c(quantos or 1))
        elif marca in ("tab", "line-break"):
            partes.append(" ")
        elif marca == "span":
            nome = filho.get(f'{{{_ODF["text"]}}}style-name') or ""
            partes.append(_texto_do_odt(
                filho, estilos, herdadas | frozenset(estilos.get(nome, set()))))
        else:
            partes.append(_texto_do_odt(filho, estilos, herdadas))
        escrever(filho.tail, herdadas)
    return "".join(partes)


def _paragrafos_do_odt(conteudo: bytes) -> list[str]:
    raiz = _abrir(conteudo, ".odt")
    estilos = _estilos_do_odt(raiz)
    corpo = raiz.find(f'{{{_ODF["office"]}}}body')
    saida = []
    for p in (corpo if corpo is not None else raiz).iter(
            f'{{{_ODF["text"]}}}p'):
        # O ESTILO DO PARÁGRAFO TAMBÉM PODE MARCAR: quem seleciona a linha
        # inteira e aperta negrito no LibreOffice às vezes recebe um estilo de
        # parágrafo, e não um span.
        nome = p.get(f'{{{_ODF["text"]}}}style-name') or ""
        texto = _texto_do_odt(p, estilos, frozenset(estilos.get(nome, set())))
        texto = re.sub(r"[ \t\xa0]+", " ", texto).strip()
        if texto:
            saida.append(texto)
    return saida


# ------------------------------------------------------ ler o .docx


def _paragrafos_do_docx(conteudo: bytes) -> list[str]:
    """Os parágrafos de um `.docx`, com as marcas. Só calcula.

    No OOXML a formatação mora DENTRO de cada trecho (`<w:rPr>`), e não numa
    tabela de estilos à parte — é mais simples que o ODF, e não precisa de
    resolução de herança para o caso comum.
    """
    raiz = _abrir(conteudo, ".docx")
    w = _OOXML["w"]
    saida = []
    for p in raiz.iter(f"{{{w}}}p"):
        partes: list[str] = []
        for trecho in p.iter(f"{{{w}}}r"):
            texto = "".join(
                (t.text or "") for t in trecho.iter(f"{{{w}}}t"))
            if any(True for _ in trecho.iter(f"{{{w}}}tab")):
                texto += " "
            if not texto:
                continue
            props = trecho.find(f"{{{w}}}rPr")
            marcas = set()
            if props is not None:
                for tag, marca in (("b", "negrito"), ("i", "italico"),
                                   ("u", "sublinhado"),
                                   ("strike", "tachado_vermelho")):
                    achado = props.find(f"{{{w}}}{tag}")
                    if achado is None:
                        continue
                    # `<w:b w:val="0"/>` DESLIGA o negrito herdado do estilo.
                    valor = (achado.get(f"{{{w}}}val") or "").lower()
                    if valor in ("0", "false", "none"):
                        continue
                    marcas.add(marca)
                highlight = props.find(f"{{{w}}}highlight")
                if highlight is not None:
                    cor = (highlight.get(f"{{{w}}}val") or "").lower()
                    if cor in ("yellow", "green"):
                        marcas.add("destaque_amarelo")
                    elif cor in ("red", "magenta", "darkred", "pink"):
                        marcas.add("destaque_vermelho")
                shd = props.find(f"{{{w}}}shd")
                if shd is not None:
                    fill = (shd.get(f"{{{w}}}fill") or "").lower()
                    if fill in ("ffff00", "fff59d", "ffeb3b"):
                        marcas.add("destaque_amarelo")
                    elif fill in ("ffcdd2", "ff0000", "ffc0cb"):
                        marcas.add("destaque_vermelho")
            corpo = _html.escape(texto)
            for marca in reversed(MARCAS):  # ordem fixa, como no ODF
                if marca in marcas:
                    if marca in ABRE_MARCA:
                        corpo = ABRE_MARCA[marca] + corpo + FECHA_MARCA[marca]
                    else:
                        etiqueta = ETIQUETA[marca]
                        corpo = f"<{etiqueta}>{corpo}</{etiqueta}>"
            partes.append(corpo)
        texto = re.sub(r"[ \t\xa0]+", " ", "".join(partes)).strip()
        if texto:
            saida.append(texto)
    return saida


def ler_documento(conteudo: bytes, nome_do_arquivo: Any) -> list[str]:
    """Os parágrafos de um `.odt` ou `.docx`, com a formatação. Só calcula.

    Devolve HTML por parágrafo — o mesmo formato em que o teor desta casa é
    gravado (`teor_formato` é `html` nos 260 atos).

    NÃO ESTOURA COM TRACEBACK: arquivo trocado, corrompido ou protegido por
    senha é coisa que acontece no balcão, e o escrevente precisa de uma frase
    que diga o que fazer.
    """
    ext = _extensao(nome_do_arquivo)
    paragrafos = (_paragrafos_do_odt(conteudo) if ext == ".odt"
                  else _paragrafos_do_docx(conteudo))
    if not paragrafos:
        raise TeorArquivoError(
            "Não achei texto nenhum neste arquivo. Confira se é o documento "
            "certo — o teor tem de estar em parágrafos, e não só em tabela ou "
            "em imagem.")
    return paragrafos


# ------------------------------------------------- o teor da casa, em HTML


def paragrafos_do_html(teor: Any) -> list[str]:
    """Os parágrafos de um teor em HTML, COM as marcas. Só calcula.

    TEOR SEM `<p>` VIRA UM PARÁGRAFO SÓ, e não some: houve teor digitado à mão
    antes de o sistema montar em HTML, e perder o texto de um ato lavrado seria
    o pior desfecho possível para uma conversão.
    """
    texto = str(teor or "")
    achados = re.findall(r"<p\b[^>]*>(.*?)</p>", texto, re.S | re.I)
    if not achados:
        limpo = _limpar_menos_as_marcas(texto).strip()
        return [limpo] if limpo else []
    return [x for x in (_limpar_menos_as_marcas(b).strip() for b in achados) if x]


def _limpar_menos_as_marcas(bruto: str) -> str:
    """Tira as etiquetas que não são ênfase, e mantém as três que são."""
    limpo = re.sub(r"<br\s*/?>", " ", bruto, flags=re.I)
    limpo = re.sub(r"<\s*strong\b[^>]*>", "<b>", limpo, flags=re.I)
    limpo = re.sub(r"<\s*/\s*strong\s*>", "</b>", limpo, flags=re.I)
    limpo = re.sub(r"<\s*em\b[^>]*>", "<i>", limpo, flags=re.I)
    limpo = re.sub(r"<\s*/\s*em\s*>", "</i>", limpo, flags=re.I)
    limpo = re.sub(r"</?(?!/?(?:b|i|u)\b)[a-zA-Z][^>]*>", "", limpo)
    return re.sub(r"[ \t\xa0]+", " ", limpo)


def html_dos_paragrafos(paragrafos: list[str]) -> str:
    """De volta a HTML, na forma que o resto da casa grava. Só calcula.

    PARÁGRAFO VAZIO NÃO ENTRA: o LibreOffice grava linha em branco entre
    parágrafos, e trazê-las de volta dobraria o espaçamento a cada ida e volta.
    """
    limpos = [p.strip() for p in paragrafos if p and _sem_marcas(p).strip()]
    return "\n".join(f"<p>{p}</p>" for p in limpos)


def _sem_marcas(texto: str) -> str:
    return re.sub(r"</?[biu]>", "", texto)


def conferir_a_volta(antes: list[str], depois: list[str]) -> dict:
    """O que mudou entre o teor que saiu e o que voltou. Só calcula.

    A TELA MOSTRA ISTO ANTES DE GRAVAR, e é a peça mais importante deste
    módulo. O escrevente exportou, editou noutro programa, e vai substituir o
    teor de um ato: ele tem direito de ver o tamanho da mudança antes de ela
    acontecer.

    E CONTA O NEGRITO À PARTE. Depois da correção de 28/08/2026 — *«negrito é
    fundamental para o layout da escritura»* — o número que mais importa nesta
    conferência é quantos trechos em negrito entraram e quantos havia: se a
    volta perdesse a ênfase, é aqui que se veria.
    """
    iguais = sum(1 for a, d in zip(antes, depois) if a.strip() == d.strip())
    return {
        "paragrafos_antes": len(antes),
        "paragrafos_depois": len(depois),
        "iguais": iguais,
        "mudou": len(antes) != len(depois) or iguais != len(antes),
        "letras_antes": sum(len(_sem_marcas(p)) for p in antes),
        "letras_depois": sum(len(_sem_marcas(p)) for p in depois),
        "negrito_antes": sum(p.count("<b>") for p in antes),
        "negrito_depois": sum(p.count("<b>") for p in depois),
    }
