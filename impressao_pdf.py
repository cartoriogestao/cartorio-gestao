"""O PAPEL EM PDF — o botão de imprimir não baixa arquivo para o operador abrir.

Pedido do oficial em 01/09/2026: *«a ferramenta de impressão está baixando um
arquivo, preciso que gere o pdf para impressão nesse botão»*.

**QUEM CONVERTE É O LIBREOFFICE, e a escolha não foi de gosto: é o mesmo motor
que abre o `.odt` no balcão.** Um gerador de PDF próprio (weasyprint, reportlab)
redesenharia o papel — e o molde da certidão é desenhado à mão pelo oficial, com
as caixas do selo, as bordas pontilhadas e o QR no lugar. **Papel que sai
diferente do que o oficial desenhou é papel que ele não desenhou.** Medido nesta
máquina: nenhum dos quatro geradores está instalado, e o LibreOffice está.

**E A MEDIÇÃO QUE DECIDIU O DESENHO FOI A DO FRACASSO CALADO.** Com outra
instância do LibreOffice subindo na mesma máquina, `soffice --convert-to pdf`
saiu com **código 0 e não escreveu PDF nenhum** — duas rodadas, 564 ms e
604 ms, pasta de saída vazia nas duas.

> **E EU ESCREVI A CAUSA ERRADA AQUI NA PRIMEIRA VERSÃO.** Disse que era «o
> LibreOffice aberto, que é o normal no balcão». **Não é**: com ele aberto e
> assentado a conversão sai em **0,9 s**, medido pelo próprio módulo, e
> `--outdir` relativo também funciona. As duas falhas foram nos **seis
> segundos seguintes ao arranque** da outra instância, enquanto ela segurava a
> trava do perfil. É uma janela estreita — e é justamente a que ninguém
> reproduz de propósito, e por isso a que chega ao balcão.

**Código de saída não é prova: a prova é o arquivo existir.** Este módulo nunca
olha o código de retorno para decidir — ele olha o PDF. É a lição do `rowcount`
do recibo da DOI, e a do «zero com cara de medição», aplicadas a um processo de
fora. E como a falha é **passageira**, a segunda tentativa num perfil que
ninguém disputa resolve o caso em vez de mandar o balcão fechar programa.

**SÃO DOIS PERFIS, E A ORDEM É MEDIDA:**

    1º · o perfil de quem chamou    ~1,1 s   (1332, 1101, 1069 ms)
    2º · o perfil da casa           6 a 92 s (erráticos, mas sempre saem)

O primeiro é dez vezes mais rápido e é o que serve o dia inteiro; o segundo é o
que funciona quando o oficial está com o LibreOffice aberto. Começar pelo lento
custaria minutos por dia para evitar um caso que o rápido resolve sozinho —
e começar pelo rápido **sem conferir o arquivo** entregaria papel nenhum.

**O TEMPO É ERRÁTICO NESTA MÁQUINA, E EU NÃO ACHEI O QUE O VIRA.** Medido em
01/09/2026, sempre com o mesmo molde e o mesmo PDF de 132.469 bytes saindo:

    de manhã, três rodadas seguidas   1332 · 1101 · 1069 ms
    à tarde, todas as variantes       ~51 s, constante
    perfil recém-criado               passou de 10 minutos

**Cinquenta e um segundos constantes têm cara de espera, e não de trabalho** —
e a espera não é do perfil (o próprio e o do usuário deram o mesmo), nem dos
canos do subprocesso (`capture_output` e `DEVNULL` deram o mesmo), nem da falta
de uma instância residente (com uma de pé, deu o mesmo). As quatro foram
testadas.

**O que separa 1 s de 51 s eu não sei**, e escrever aqui um palpite seria o
comentário que afirma medição sem ter medido. O que se sabe: **o papel sai
certo nos dois casos** — e por isso o `.odt` continua a um clique e o formato
padrão é configuração, não constante.

**UMA CONVERSÃO POR VEZ.** O perfil é um diretório com trava; dois pedidos
simultâneos sobre ele brigam, e o segundo é justamente o que falha calado. O
`waitress` atende em várias linhas de execução dentro de um processo só, então
uma trava de processo basta — e cada conversão dura cerca de um segundo.

**E O `.odt` NÃO SAI DE CENA.** Quando não há LibreOffice na máquina, ou quando
ele não devolve o PDF, a tela entrega o `.odt` **e diz por quê**. Balcão parado é
pior que papel em outro formato — é a mesma regra do selo que não sai.
"""
from __future__ import annotations

import io
import os
import re
import base64
import shutil
import subprocess
import tempfile
import threading
import zipfile
from pathlib import Path

# ONDE O LIBREOFFICE COSTUMA ESTAR NO WINDOWS, medido nesta maquina em
# 01/09/2026 (o primeiro caminho e o desta instalacao). A lista e ordenada, e
# quem manda mesmo e a configuracao `libreoffice_caminho` — porque o dia em que
# ele mudar de lugar ninguem quer mexer no codigo para o balcao voltar a
# imprimir. E a mesma decisao da versao da tabela de custas.
CAMINHOS_CONHECIDOS: tuple[str, ...] = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
)

# O PERFIL DA CASA — o segundo caminho, para quando o do usuario esta ocupado.
#
# Mora ao lado do banco e do `selador.cred`, e **e persistente**: montado a cada
# vez, a conversao pagaria os 11 s da primeira montagem sempre.
PASTA_DO_PERFIL = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / \
    "CartorioGestao" / "libreoffice_perfil"

# Prazo largo de proposito: medido de 1 a 92 segundos, e o alto foi com a
# maquina ocupada. Prazo curto transformaria maquina carregada em papel que nao
# sai — e quem espera esta no balcao, com o cliente na frente.
PRAZO_SEGUNDOS = 180

# UMA CONVERSAO POR VEZ. Ver o cabecalho.
_UMA_DE_CADA_VEZ = threading.Lock()


class PdfError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


def onde_esta_o_conversor(get_setting=None) -> Path | None:
    """O `soffice.exe` desta maquina, ou None. So LE — nao converte nada.

    Recebe a **funcao** de ler configuracao, e nao a conexao, como o resto das
    guardas desta casa: assim da para perguntar de dentro de uma rota sem abrir
    transacao nenhuma.
    """
    if get_setting is not None:
        escrito = str(get_setting("libreoffice_caminho", "") or "").strip()
        if escrito:
            p = Path(escrito)
            return p if p.exists() else None
    for caminho in CAMINHOS_CONHECIDOS:
        p = Path(caminho)
        if p.exists():
            return p
    achado = shutil.which("soffice") or shutil.which("libreoffice")
    return Path(achado) if achado else None


# ---------------------------------------------------------------- a espera

# **A IMPRESSORA GRAVADA DENTRO DO ARQUIVO CUSTAVA 48 SEGUNDOS POR PAPEL.**
#
# Medido em 02/09/2026, contra o molde real da certidao de nascimento:
#
#     molde como esta (com a impressora)   50,6 s
#     molde sem PrinterName/PrinterSetup    2,6 s
#     o PDF que sai                        132.469 bytes nos DOIS
#
# **Vinte vezes mais rapido, com o papel identico.**
#
# O `settings.xml` de um `.odt` guarda a impressora de quem salvou o arquivo —
# aqui, `EPSON344007 (L4260 Series)`, a do oficial. Ao abrir o documento, o
# LibreOffice pergunta as capacidades dessa impressora; quando ela nao esta
# alcancavel, **ele espera o tempo limite**. Por isso a demora era CONSTANTE:
# nao era trabalho, era espera.
#
# **E ISSO EXPLICA O QUE EU NAO TINHA EXPLICADO EM 01/09/2026.** O tempo
# «erratico» que ficou escrito no `CLAUDE.md` — 1 s de manha, ~51 s a tarde,
# mais de 10 minutos num perfil novo — nao era erratico: era a impressora
# alcancavel ou nao. **Eu testei quatro suspeitas** (perfil proprio, perfil do
# usuario, instancia residente, os canos do subprocesso) **e nao olhei dentro
# do arquivo.** A causa estava no molde, a um `unzip` de distancia.
#
# **A LIMPEZA E NA CONVERSAO, E NAO NO MOLDE.** Limpar o arquivo em disco
# resolveria ate o oficial abrir o molde no LibreOffice e salvar de novo — e
# ele VAI, porque o molde e dele e ele o ajusta. Aqui a limpeza vale para os
# **sete papeis** da casa e nao depende de ninguem lembrar.
#
# **E o `.odt` que o balcao baixa NAO e tocado**: aquele e o arquivo dele,
# com as escolhas dele. O que se limpa e a copia que vai ao conversor.
_IMPRESSORA_NO_ARQUIVO = re.compile(
    r'<config:config-item config:name="(?:PrinterName|PrinterSetup)"'
    r'[^>]*>.*?</config:config-item>', re.DOTALL)


def sem_a_impressora_de_quem_salvou(odt: bytes) -> bytes:
    """O mesmo `.odt`, sem a impressora que ficou gravada nele. Só calcula.

    Devolve o arquivo **inalterado** quando não há `settings.xml` (é o caso
    dos papéis que a casa monta de HTML) ou quando ele não cita impressora
    nenhuma — e devolve o original também se o arquivo não abrir como zip,
    porque **quem decide o que fazer com arquivo torto é quem converte**, e
    não esta função.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(odt)) as z:
            if "settings.xml" not in z.namelist():
                return odt
            texto = z.read("settings.xml").decode("utf-8")
            limpo = _IMPRESSORA_NO_ARQUIVO.sub("", texto)
            if limpo == texto:
                return odt
            fora = io.BytesIO()
            with zipfile.ZipFile(fora, "w", zipfile.ZIP_DEFLATED) as saida:
                for item in z.infolist():
                    dados = z.read(item.filename)
                    if item.filename == "settings.xml":
                        dados = limpo.encode("utf-8")
                    saida.writestr(item, dados)
            return fora.getvalue()
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError):
        return odt


def _tentar(conversor: Path, odt: Path, saida: Path,
            perfil: Path | None) -> bytes | None:
    """Uma tentativa. Devolve os bytes do PDF, ou **None** se ele nao saiu.

    **Nao olha o codigo de retorno**: com outra instancia do LibreOffice aberta
    ele sai 0 sem escrever arquivo nenhum. Quem responde e o PDF existir.
    """
    comando = [str(conversor)]
    if perfil is not None:
        perfil.mkdir(parents=True, exist_ok=True)
        comando.append(f"-env:UserInstallation={perfil.resolve().as_uri()}")
        comando.append("--nolockcheck")
    comando += ["--headless", "--norestore", "--convert-to", "pdf",
                "--outdir", str(saida), str(odt)]
    try:
        subprocess.run(comando, capture_output=True, timeout=PRAZO_SEGUNDOS,
                       check=False)
    except (subprocess.TimeoutExpired, OSError):
        return None
    feito = saida / (odt.stem + ".pdf")
    if feito.exists() and feito.stat().st_size > 0:
        return feito.read_bytes()
    return None



def folha_livro_inicio_do_odt(odt: bytes) -> int | None:
    """Se o .odt tem campo ODF de face do livro (frente/verso), devolve o inicio.

    `campo_folha_do_livro_odf` grava `text:expression` com
    `INT((PAGE-1)/2)+N` no cabecalho. O LibreOffice em `--headless` **nao
    recalcula** essa formula na exportacao PDF — o valor em cache (`N`) sai
    em todas as paginas. Quem chama `pdf_de_odt` usa este numero para
    reescrever o rotulo certo depois da conversao.
    """
    if not odt:
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(odt)) as z:
            for nome in ("styles.xml", "content.xml"):
                try:
                    texto = z.read(nome).decode("utf-8")
                except KeyError:
                    continue
                achado = re.search(
                    r'text:formula="ooow:INT\(\(PAGE-1\)/2\)\+(\d+)"', texto)
                if achado:
                    return int(achado.group(1))
    except (zipfile.BadZipFile, UnicodeDecodeError, ValueError):
        return None
    return None


def _pdf_wide(texto: str):
    """UTF-16LE + NUL no formato que o PDFium espera em FPDFText_SetText."""
    import ctypes
    dados = texto.encode("utf-16-le") + b"\x00\x00"
    return (ctypes.c_ushort * (len(dados) // 2)).from_buffer_copy(dados)


def _caixa_numero_apos_ancora(tp, ancora: str, devolver_texto: bool = False):
    """Caixa do numero (digitos + opcional 'v') que segue a ancora no texto."""
    sch = tp.search(ancora, match_case=False)
    occ = sch.get_next()
    if not occ:
        return None
    inicio, _tam = occ
    n = tp.count_chars()
    i = inicio
    while i < n and not (tp.get_text_range(i, 1) or "").isdigit():
        i += 1
    if i >= n:
        return None
    j = i
    while j < n:
        ch = tp.get_text_range(j, 1) or ""
        if ch.isdigit() or ch.lower() == "v":
            j += 1
        else:
            break
    if j <= i:
        return None
    caixas = [tp.get_charbox(k) for k in range(i, j)]
    # Largura extra: "1" vira "12v" sem cortar.
    esquerda = min(c[0] for c in caixas) - 0.8
    baixo = min(c[1] for c in caixas) - 0.6
    direita = max(c[2] for c in caixas) + 30.0
    cima = max(c[3] for c in caixas) + 0.6
    altura = max(c[3] - c[1] for c in caixas)
    if devolver_texto:
        # HOTFIX-FOLHAS-FV: o rotulo que ja esta impresso, para nao reescrever
        # (e trocar a fonte de) rotulo que ja saiu certo.
        return (esquerda, baixo, direita, cima, altura,
                (tp.get_text_range(i, j - i) or "").strip())
    return esquerda, baixo, direita, cima, altura


def corrigir_rotulos_folha_livro_pdf(pdf: bytes, folha_inicial: int,
                                     *, ancora: str = "FICHA") -> bytes:
    """Reescreve 1/1v/2/2v no cabecalho do PDF (face do livro).

    O campo ODF com formula PAGE chega congelado no PDF headless. Aqui cada
    pagina ganha o rotulo de `notas_livro.rotulo_folha_da_pagina`: pagina 1
    -> inicio, pagina 2 -> iniciov, pagina 3 -> inicio+1, etc.

    So mexe quando acha a ancora (padrao `FICHA`) e um numero depois dela —
    nao inventa rotulo em papel que nao e ficha/folha do livro.

    **23/09/2026 — QR DOS SELOS (Beatriz, matricula 582).** A versao antiga
    usava `pypdfium2` com `FPDFPage_GenerateContent` + `save(NO_INCREMENTAL)`.
    Medido: o LibreOffice desenha o QR no content stream, e NAO como page
    object enumeravel; o GenerateContent reconstruia o stream so com text/path
    e **apagava as 3 imagens** do PDF (carimbo com caixa vazia a esquerda).
    Agora: pdfium so LE as coordenadas; o pypdf acresce um content stream de
    tapa+texto sem regenerar a pagina — QR permanece e o rotulo muda.
    """
    if not pdf or folha_inicial is None:
        return pdf
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return pdf
    try:
        from notas_livro import rotulo_folha_da_pagina
    except ImportError:
        return pdf
    try:
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import (
            NameObject, DictionaryObject, ArrayObject, DecodedStreamObject,
        )
    except ImportError:
        return pdf

    inicio = int(folha_inicial)
    # 1) LEITURA: coordenadas do numero congelado (pdfium nao grava nada).
    caixas: list[tuple[int, float, float, float, float, float, str]] = []
    doc = pdfium.PdfDocument(pdf)
    try:
        for indice in range(len(doc)):
            pagina = doc[indice]
            tp = pagina.get_textpage()
            try:
                # HOTFIX-FOLHAS-FV: «FICHA» (RI) e «FOLHA» (Notas e demais).
                caixa = None
                for _anc in ((ancora,) if ancora != "FICHA"
                             else ("FICHA", "FOLHA")):
                    caixa = _caixa_numero_apos_ancora(tp, _anc,
                                                      devolver_texto=True)
                    if caixa is not None:
                        break
            finally:
                tp.close()
            if caixa is None:
                continue
            esquerda, baixo, direita, cima, altura, ja_impresso = caixa
            rotulo = rotulo_folha_da_pagina(inicio, indice + 1)
            if not rotulo:
                continue
            if ja_impresso.lower() == str(rotulo).lower():
                # A pagina-mestre da cadeia ja imprimiu o rotulo certo.
                continue
            caixas.append((
                indice,
                float(esquerda), float(baixo), float(direita), float(cima),
                max(float(altura) * 1.15, 7.0),
                str(rotulo),
            ))
    finally:
        doc.close()
    if not caixas:
        return pdf

    # 2) ESCRITA: overlay no content stream (pypdf), sem GenerateContent.
    reader = PdfReader(io.BytesIO(pdf))
    writer = PdfWriter()
    writer.append(reader)
    por_pagina: dict[int, list] = {}
    for item in caixas:
        por_pagina.setdefault(item[0], []).append(item)
    for page_i, itens in por_pagina.items():
        page = writer.pages[page_i]
        if "/Resources" not in page:
            page[NameObject("/Resources")] = DictionaryObject()
        res = page["/Resources"].get_object()
        if "/Font" not in res:
            res[NameObject("/Font")] = DictionaryObject()
        fonts = res["/Font"].get_object()
        if "/HelvB" not in fonts:
            fonts[NameObject("/HelvB")] = writer._add_object(DictionaryObject({
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica-Bold"),
            }))
        partes = ["q"]
        for (_, x0, y0, x1, y1, tamanho, texto) in itens:
            seguro = (texto.replace("\\", "\\\\")
                           .replace("(", "\\(")
                           .replace(")", "\\)"))
            partes.append(
                f"1 1 1 rg {x0:.3f} {y0:.3f} {x1 - x0:.3f} {y1 - y0:.3f} re f")
            partes.append(
                f"0 0 0 rg BT /HelvB {tamanho:.3f} Tf "
                f"{x0:.3f} {y0 + 0.4:.3f} Td ({seguro}) Tj ET")
        partes.append("Q")
        stream = DecodedStreamObject()
        stream.set_data("\n".join(partes).encode("latin-1"))
        stream_ref = writer._add_object(stream)
        contents = page.get("/Contents")
        if contents is None:
            page[NameObject("/Contents")] = stream_ref
        else:
            obj = contents.get_object()
            arr = ArrayObject()
            if isinstance(obj, ArrayObject):
                for c in obj:
                    arr.append(c)
            else:
                arr.append(contents)
            arr.append(stream_ref)
            page[NameObject("/Contents")] = arr
    saida = io.BytesIO()
    writer.write(saida)
    return saida.getvalue()
def _pdf_cru(odt: bytes, *, nome: str = "documento",
             get_setting=None) -> bytes:
    """A conversao em si, sem reescrever o rotulo da folha. Ver `pdf_de_odt`."""
    if not odt:
        raise PdfError("Não há documento para converter em PDF.")
    conversor = onde_esta_o_conversor(get_setting)
    if conversor is None:
        raise PdfError(
            "O LibreOffice não foi encontrado nesta máquina, e é ele quem "
            "gera o PDF. Instale-o, ou informe o caminho do programa em "
            "Administrativo → Configurações.")

    seguro = "".join(c for c in str(nome) if c.isalnum() or c in "-_") or "documento"
    with _UMA_DE_CADA_VEZ, tempfile.TemporaryDirectory(prefix="cg_pdf_") as pasta:
        area = Path(pasta)
        origem = area / (seguro + ".odt")
        # **A IMPRESSORA SAI ANTES DE O CONVERSOR VER O ARQUIVO** — 48
        # segundos por papel, medidos. Ver a nota acima de
        # `sem_a_impressora_de_quem_salvou`.
        origem.write_bytes(sem_a_impressora_de_quem_salvou(odt))
        saida = area / "saida"
        saida.mkdir()
        # 1º o perfil de quem chamou — dez vezes mais rapido.
        feito = _tentar(conversor, origem, saida, None)
        if feito is None:
            # 2º o perfil da casa — o caminho de quando ha LibreOffice aberto.
            feito = _tentar(conversor, origem, saida, PASTA_DO_PERFIL)
    if feito is None:
        # A FRASE NAO CHUTA A CAUSA. A medicao mostrou que a falha e passageira
        # (a trava do perfil durante o arranque de outra instancia), e a
        # segunda tentativa ja cobriu esse caso: se chegou aqui, foi outra
        # coisa. Mandar «feche o LibreOffice» seria dar ao balcao uma
        # providencia que provavelmente nao resolve.
        raise PdfError(
            "O LibreOffice não devolveu o PDF desta vez. Tente de novo; se "
            "insistir, o documento continua disponível em .odt e imprime "
            "igual.")
    return feito


def contar_paginas(pdf: bytes) -> int:
    """Quantas paginas o PDF tem. So LE."""
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise PdfError("Falta o pacote pypdfium2 para contar as páginas.") from exc
    doc = pdfium.PdfDocument(pdf)
    try:
        return len(doc)
    finally:
        doc.close()


def paginas_do_odt(odt: bytes, *, get_setting=None) -> int:
    """Quantas paginas o LibreOffice desenha para este `.odt`. MEDIDO.

    07/10/2026, pedido do oficial: o escrevente nao deve ter de dizer quantas
    paginas o ato tem. Quem decide a quebra e o LibreOffice; perguntar a ele e
    a unica conta que nao e palpite. Levanta `PdfError` se nao conseguiu.
    """
    return contar_paginas(_pdf_cru(odt, nome="medida", get_setting=get_setting))


def pdf_de_odt(odt: bytes, *, nome: str = "documento",
               get_setting=None) -> bytes:
    """O `.odt` da casa virado PDF. Nao grava nada no banco.

    Levanta `PdfError` — com mensagem para o balcao — quando nao ha conversor
    ou quando ele nao devolveu o papel. **Nunca devolve bytes vazios fingindo
    ter dado certo.**
    """
    feito = _pdf_cru(odt, nome=nome, get_setting=get_setting)
    # Face do livro (1, 1v, 2, 2v): a formula ODF PAGE nao e
    # recalculada no PDF headless — todas as paginas saiam com o
    # valor em cache. Medido 23/09/2026 na ficha RI (Beatriz,
    # matricula 4018). Reescreve o rotulo por pagina depois.
    inicio_folha = folha_livro_inicio_do_odt(odt)
    if inicio_folha is not None:
        feito = corrigir_rotulos_folha_livro_pdf(feito, inicio_folha)
    return feito


# --- Chrome: PDF fiel ao HTML (folha do livro). Sem mexer no template. ---

CAMINHOS_CHROME: tuple[str, ...] = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)


def onde_esta_o_chrome(get_setting=None) -> Path | None:
    """Chrome/Edge desta maquina, ou None. So LE."""
    if get_setting is not None:
        escrito = str(get_setting("chrome_caminho", "") or "").strip()
        if escrito:
            p = Path(escrito)
            return p if p.exists() else None
    for caminho in CAMINHOS_CHROME:
        p = Path(caminho)
        if p.exists():
            return p
    achado = shutil.which("chrome") or shutil.which("msedge") or shutil.which("google-chrome")
    return Path(achado) if achado else None


def _html_com_pauta_para_chrome(html: str) -> str:
    """Preserva o HTML: página, escala e pauta vêm do mesmo template da tela.

    Recriar a pauta em uma tabela mudava espaçamentos e ainda descartava
    anotações além da linha 31. O CSS de impressão já imprime o fundo.
    """
    return html


def incorporar_imagem_local(html: str, arquivo: Path, *,
                            mime: str = "image/jpeg") -> str:
    """Embute TODAS as ocorrencias de uma imagem local no HTML. So calcula.

    A folha do livro tem frente e verso, portanto o brasao aparece duas vezes.
    Substituir apenas a primeira deixava o verso apontando para ``/static``;
    ao abrir o HTML temporario por ``file://``, o Chrome nao encontra essa URL
    e imprime o icone de imagem quebrada.
    """
    if not arquivo.is_file():
        return html
    dados = base64.b64encode(arquivo.read_bytes()).decode("ascii")
    data_uri = f"data:{mime};base64,{dados}"
    padrao = rf'src="[^"]*{re.escape(arquivo.name)}"'
    return re.sub(padrao, f'src="{data_uri}"', html, flags=re.I)


def pdf_de_html_chrome(html: bytes | str, *, nome: str = "documento",
                       get_setting=None) -> bytes:
    """HTML → PDF pelo Chrome/Edge headless (igual ao navegador)."""
    if isinstance(html, str):
        html_s = html
    else:
        html_s = (html or b"").decode("utf-8", errors="replace")
    if not html_s.strip():
        raise PdfError("Nao ha HTML para converter em PDF.")
    chrome = onde_esta_o_chrome(get_setting)
    if chrome is None:
        raise PdfError(
            "Chrome/Edge nao encontrado nesta maquina — e ele quem imprime "
            "o HTML da folha em PDF. Informe chrome_caminho nas Configuracoes, "
            "ou instale o Chrome.")
    html_s = _html_com_pauta_para_chrome(html_s)
    seguro = "".join(c for c in str(nome) if c.isalnum() or c in "-_") or "documento"
    with _UMA_DE_CADA_VEZ, tempfile.TemporaryDirectory(prefix="cg_chrome_") as pasta:
        area = Path(pasta)
        html_path = area / (seguro + ".html")
        html_path.write_text(html_s, encoding="utf-8")
        pdf_path = area / (seguro + ".pdf")
        comando = [
            str(chrome),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}",
            html_path.resolve().as_uri(),
        ]
        try:
            subprocess.run(comando, capture_output=True, timeout=PRAZO_SEGUNDOS,
                           check=False)
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise PdfError(
                f"O Chrome nao respondeu ao gerar o PDF ({exc}).") from exc
        if not pdf_path.exists() or pdf_path.stat().st_size <= 0:
            raise PdfError(
                "O Chrome nao devolveu o PDF desta vez. Tente de novo; "
                "a folha em HTML (imprimir no navegador) continua disponivel.")
        return pdf_path.read_bytes()


def odt_de_pdf_visual(pdf: bytes, *, nome: str = "documento") -> bytes:
    """ODT com as paginas do PDF como imagem — visual igual ao HTML impresso.

    Largura/altura da imagem e da pagina do ODT saem do PDF real
    (pts para cm). Assim carta (215x279) nao vira A4 esticado.
    """
    if not pdf:
        raise PdfError("Nao ha PDF para montar o ODT.")
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise PdfError(
            "Falta o pacote pypdfium2 para montar o ODT visual da folha. "
            "Instale com: py -3 -m pip install pypdfium2") from exc
    from ri_odt import gerar_odt, ESTILOS_EXTRA
    import io

    doc = pdfium.PdfDocument(pdf)
    imagens: dict[str, tuple[bytes, str]] = {}
    partes: list[str] = []
    w_cm, h_cm = 21.5, 27.9
    ESTILOS_EXTRA.setdefault(
        "P-folha-chrome",
        '<style:style style:name="P-folha-chrome" style:family="paragraph">'
        '<style:paragraph-properties fo:text-align="center" '
        'fo:margin-top="0cm" fo:margin-bottom="0cm"/>'
        "</style:style>")
    ESTILOS_EXTRA.setdefault(
        "P-folha-chrome-quebra",
        '<style:style style:name="P-folha-chrome-quebra" style:family="paragraph">'
        '<style:paragraph-properties fo:break-before="page" '
        'fo:text-align="center" fo:margin-top="0cm" fo:margin-bottom="0cm"/>'
        "</style:style>")
    for i in range(len(doc)):
        page = doc[i]
        try:
            pw, ph = page.get_size()
            if pw > 0 and ph > 0:
                w_cm = round(pw * 2.54 / 72.0, 2)
                h_cm = round(ph * 2.54 / 72.0, 2)
        except Exception:
            pass
        pil = page.render(scale=150 / 72).to_pil()
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        img_name = f"folha{i + 1}.png"
        imagens[img_name] = (buf.getvalue(), "image/png")
        estilo = "P-folha-chrome-quebra" if i else "P-folha-chrome"
        partes.append(
            f'<text:p text:style-name="{estilo}">'
            f'<draw:frame draw:name="{img_name}" text:anchor-type="as-char" '
            f'svg:width="{w_cm}cm" svg:height="{h_cm}cm" '
            f'style:rel-width="scale" style:rel-height="scale">'
            f'<draw:image xlink:href="Pictures/{img_name}" '
            f'xlink:type="simple" xlink:show="embed" '
            f'xlink:actuate="onLoad"/>'
            f"</draw:frame></text:p>"
        )
    if not partes:
        raise PdfError("O PDF nao tinha paginas para o ODT.")
    return gerar_odt(
        chr(10).join(partes),
        titulo=nome,
        imagens=imagens,
        cabecalho_altura_min="0cm",
        cabecalho_borda=False,
        pagina_largura_cm=w_cm,
        pagina_altura_cm=h_cm,
        margem_cm=0.0,
    )

def arquivo_de_html(html: bytes | str, *, nome: str = "documento",
                    formato: str | None = None, get_setting=None
                    ) -> tuple[bytes, str, str, str]:
    """HTML da folha -> PDF (Chrome) ou ODT visual (paginas do PDF).

    O LibreOffice nao reproduz @page/pauta/3 colunas. O Chrome imprime
    igual ao navegador; o ODT embute as paginas do PDF (visual igual).
    O template rcpn_folha_impressa.html define a mesma escala nos tres formatos.
    """
    qual = formato_pedido(formato, get_setting)
    pdf = pdf_de_html_chrome(html, nome=nome, get_setting=get_setting)
    seguro = "".join(c for c in str(nome) if c.isalnum() or c in "-_") or "documento"
    if qual == "odt":
        odt = odt_de_pdf_visual(pdf, nome=seguro)
        return odt, TIPO_DO_FORMATO["odt"], f"{seguro}.odt", "attachment"
    return pdf, TIPO_DO_FORMATO["pdf"], f"{seguro}.pdf", ENTREGA_DO_FORMATO["pdf"]


def _tentar_fmt(conversor: Path, origem: Path, saida: Path,
                perfil: Path | None, ext: str) -> bytes | None:
    """Uma tentativa HTML/ODT -> pdf|odt. Devolve bytes ou None."""
    comando = [str(conversor)]
    if perfil is not None:
        perfil.mkdir(parents=True, exist_ok=True)
        comando.append(f"-env:UserInstallation={perfil.resolve().as_uri()}")
        comando.append("--nolockcheck")
    filtro = "pdf:writer_pdf_Export" if ext == "pdf" else "odt"
    comando += ["--headless", "--norestore", "--convert-to", filtro,
                "--outdir", str(saida), str(origem)]
    try:
        subprocess.run(comando, capture_output=True, timeout=PRAZO_SEGUNDOS,
                       check=False)
    except (subprocess.TimeoutExpired, OSError):
        return None
    # LibreOffice name: stem + .pdf/.odt
    feito = saida / (origem.stem + "." + ext)
    if feito.exists() and feito.stat().st_size > 0:
        return feito.read_bytes()
    # as vezes o filtro muda o nome
    candidatos = list(saida.glob("*." + ext))
    if candidatos and candidatos[0].stat().st_size > 0:
        return candidatos[0].read_bytes()
    return None


# ---------------------------------------------------------------- o papel

# O QUE O BOTAO ENTREGA. `pdf` e o padrao — foi o pedido —, e `odt` continua
# alcancavel, porque ha papel que o oficial abre para ajustar antes de colar no
# livro. Formato desconhecido cai no PDF, e nao estoura: o balcao clicou num
# botao, e nao escreveu o endereco.
FORMATOS: tuple[str, ...] = ("pdf", "odt")
FORMATO_PADRAO = "pdf"

TIPO_DO_FORMATO: dict[str, str] = {
    "pdf": "application/pdf",
    "odt": "application/vnd.oasis.opendocument.text",
}

# **PDF ABRE NA TELA; `.odt` BAIXA.** `inline` poe o papel no visualizador do
# navegador, que ja tem o botao de imprimir do lado — que e exatamente o que o
# oficial pediu. Um `.odt` `inline` nao abre em navegador nenhum: baixaria do
# mesmo jeito, com o nome pior.
ENTREGA_DO_FORMATO: dict[str, str] = {"pdf": "inline", "odt": "attachment"}


def formato_pedido(valor, get_setting=None) -> str:
    """Qual formato a tela pediu, ou o padrão desta serventia. Só LÊ.

    **O PADRÃO É DO OFICIAL, E NÃO MEU** — `impressao_formato_padrao` em
    `settings`. A razão está na medição do tempo, no cabeçalho: se o PDF sair
    lento no balcão dele, ele volta para o `.odt` sozinho, numa tarde, em vez
    de esperar uma versão nova. É a decisão do alcance da ajuda outra vez:
    quem decide não deveria depender de quem programa.
    """
    escolhido = str(valor or "").strip().lower()
    if escolhido in FORMATOS:
        return escolhido
    if get_setting is not None:
        da_casa = str(get_setting("impressao_formato_padrao", "") or "").strip().lower()
        if da_casa in FORMATOS:
            return da_casa
    return FORMATO_PADRAO


def papel_para_baixar(odt: bytes, *, nome: str, formato=None,
                      get_setting=None) -> tuple[bytes, str, str, str]:
    """O papel pronto para a resposta: `(conteudo, tipo, arquivo, entrega)`.

    **Nao devolve `Response`, de proposito**: assim ele se testa sem Flask, e a
    regra de «modulo de dominio primeiro, com a rota so ligando os fios» vale
    tambem para o papel. Levanta `PdfError` quando o PDF nao sai — e quem
    decide o que fazer com a recusa e a rota, que sabe para onde voltar.
    """
    qual = formato_pedido(formato, get_setting)
    # O NOME DO ARQUIVO VAI NUM CABECALHO HTTP, e cabecalho e ASCII. Um acento
    # em `Content-Disposition` quebra a resposta inteira — e os nomes de papel
    # desta casa passam por «Certidao 1/2026», com barra, que num nome de
    # arquivo do Windows nao entra. Troca-se o que nao serve, em vez de
    # confiar em quem chama.
    limpo = "".join(c if (c.isascii() and (c.isalnum() or c in "-_.")) else "-"
                    for c in str(nome or "").strip()).strip("-") or "documento"
    if qual == "odt":
        return odt, TIPO_DO_FORMATO["odt"], f"{limpo}.odt", "attachment"
    pdf = pdf_de_odt(odt, nome=limpo, get_setting=get_setting)
    return pdf, TIPO_DO_FORMATO["pdf"], f"{limpo}.pdf", "inline"
