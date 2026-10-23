"""OS ANEXOS DO ATO NA REVISÃO — o título e os documentos que o ato diz ter visto.

    «gostei do ler cada anexo uma vez, usar o modelo mais barato para transcrever
     e aviso quando passar de 40 páginas. pode também implementar no revisor um
     filtro do que é e o que não é importante antes de transcrever tudo»
                                                    — o oficial, 07/10/2026

O CAMINHO DE CADA ARQUIVO, E POR QUE NESTA ORDEM
    1. JÁ FOI LIDO? A leitura se guarda pela impressão digital do arquivo
       (`attachments.sha256`), em `rv_anexos_lidos`. A segunda revisão do mesmo
       ato — a de depois de corrigir uma vírgula — não paga o anexo de novo, e
       o mesmo RG anexado a dois atos também não.
    2. A TRIAGEM: o modelo barato vê AS PRIMEIRAS PÁGINAS (até três) e diz o
       que o documento é e se ele fundamenta o ato. Comprovante de pagamento,
       capa de protocolo e página em branco não sobem inteiros. É a parte
       barata que decide onde se gasta a cara — mas SÓ DESCARTA O QUE VIU
       INTEIRO: documento mais comprido que o que a triagem viu é lido (M7 do
       LS03; LX13, 19/10/2026). Ela via só a primeira página, e uma capa de
       «comprovante» na frente do mandado tirava o mandado do dossiê.
    3. A TRANSCRIÇÃO, só do que importa: a página que já tem texto digital se lê
       AQUI, de graça (`pypdfium2`); só a digitalizada vai como imagem ao
       modelo barato. Medido na produção em 07/10/2026: das 512 páginas anexadas
       a atos das Notas e prenotações do RI, 289 já têm texto.
    4. O TETO DE 40 PÁGINAS por ato: passou, a tela avisa, e o que passou do
       teto não é transcrito — o aviso diz quantas ficaram de fora e quais.

O QUE ELE NÃO FAZ
    - Não decide nada do ato: entrega texto para o revisor de sempre (Opus).
    - Não manda imagem quando a revisão está com máscara (`revisao_mascara`):
      página digitalizada não se mascara, e mandá-la furaria a decisão.
    - Não lê .docx/.odt: o título desta casa chega em PDF ou imagem, e o que
      não for lido aparece na lista com o motivo, em vez de sumir.

FALA COM A REDE. Roda dentro da leitura em segundo plano da revisão, com
conexão própria e fora de transação de escrita.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import tetos_de_entrada as TETO
from bd_nativo import banco

PROVEDOR = "claude"
#: O MODELO BARATO — o Haiku. `settings.revisao_modelo_anexos` troca sem versão.
MODELO_BARATO = "claude-haiku-4-5-20251001"
CHAVE_MODELO = "revisao_modelo_anexos"
#: Ordem do oficial, 07/10/2026: aviso quando passar de 40 páginas.
TETO_DE_PAGINAS = 40
#: Página com menos letras que isto se trata como digitalizada.
LETRAS_DE_PAGINA_COM_TEXTO = 200
#: Páginas por pedido de transcrição. Medido em 07/10/2026 nos anexos reais da
#: produção: a maior página vai em 310 KB de JPEG; três passariam do limite de
#: envio do transporte (900 mil caracteres). Com duas, sobra folga.
PAGINAS_POR_PEDIDO = 2
#: Documento de editor (.docx/.odt) não tem página: conta-se uma a cada tanto.
LETRAS_POR_PAGINA_DE_EDITOR = 3000
#: O lado maior da imagem. Acima de ~1.500 px o provedor reduz de todo jeito,
#: e mandar maior só gasta rede.
LADO_MAIOR_PX = 1400
PEDIDOS_SIMULTANEOS = 4
#: O que vai ao dossiê por documento — o resto é cortado com aviso.
LETRAS_POR_DOCUMENTO = 30_000
#: Quantas páginas a triagem vê (M7 do LS03). Três pegam a capa, o
#: comprovante grampeado na frente e o começo do documento de verdade; o que
#: passar disto não se descarta pela triagem (ver `ler`), e o teto de 40
#: páginas por ato continua segurando a conta.
PAGINAS_DA_TRIAGEM = 3
#: O texto de cada página com texto digital que vai à triagem.
LETRAS_POR_PAGINA_DA_TRIAGEM = 1500

EXTENSOES_DE_IMAGEM = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                       ".png": "image/png", ".webp": "image/webp",
                       ".gif": "image/gif", ".bmp": "image/bmp",
                       ".tif": "image/tiff", ".tiff": "image/tiff"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS rv_anexos_lidos (
    sha256 TEXT PRIMARY KEY,
    nome TEXT,
    paginas INTEGER,
    paginas_texto INTEGER,
    paginas_imagem INTEGER,
    tipo TEXT,
    importante INTEGER,
    motivo TEXT,
    transcricao TEXT,
    paginas_lidas INTEGER,
    paginas_triadas INTEGER,           -- quantas a triagem viu (LX13); NULL = 1
    situacao TEXT NOT NULL,            -- LIDO | TRIADO | ERRO
    modelo TEXT,
    tokens_entrada INTEGER NOT NULL DEFAULT 0,
    tokens_saida INTEGER NOT NULL DEFAULT 0,
    lido_em TEXT,
    erro TEXT
);
"""

INSTRUCAO_TRIAGEM = """Você faz a triagem dos documentos anexados a um ato de \
cartório (Registro de Imóveis ou Tabelionato de Notas), ANTES de alguém transcrevê-los. \
Você vê as primeiras páginas do arquivo (até três). Diga o que o documento é e se ele \
FUNDAMENTA o ato — isto é, se o revisor precisa lê-lo para conferir o texto do ato. Se \
QUALQUER página vista for documento que fundamenta (mesmo depois de uma capa ou de um \
comprovante), o arquivo é importante.

IMPORTANTE (sim): título ou escritura, contrato, formal de partilha, carta de \
arrematação, mandado ou decisão judicial, certidão de matrícula ou de ônus, documento de \
identidade, CPF, certidão de nascimento ou de casamento das partes, procuração, \
guia ou certidão de ITBI/ITCMD, CCIR, ITR, CAR, planta, memorial descritivo, ART, \
certidão negativa exigida pelo ato, requerimento que descreve o pedido.
NÃO IMPORTANTE: comprovante de pagamento de emolumentos ou de boleto, capa ou etiqueta \
de protocolo, página em branco, foto ilegível, cópia repetida de outro anexo, \
propaganda, recibo de entrega.
Na dúvida, importante.

Responda SÓ com JSON: {"tipo": "nome curto do documento", "importante": true|false, \
"motivo": "uma frase"}"""

INSTRUCAO_TRANSCRICAO = """Transcreva o texto das páginas de documento a seguir, na \
ordem, fielmente: nomes, números de documento, datas, valores, áreas, medidas, \
confrontações, matrículas, cláusulas. Não resuma e não corrija. Marque o início de \
cada página com «[página N]». O que não der para ler, escreva [ilegível]. \
Carimbos e assinaturas: diga apenas [carimbo: texto legível] ou [assinatura]. \
Responda só com a transcrição."""


class AnexoIlegivel(ValueError):
    """O arquivo não abre como PDF nem imagem."""


def init_schema(con: sqlite3.Connection) -> None:
    bd = banco(con)
    bd.escrever(SCHEMA)
    # A COLUNA NOVA NO BANCO QUE JÁ EXISTE (LX13): a linha antiga fica NULL, e
    # NULL quer dizer «a triagem viu uma página», que era a regra de então.
    if not bd.tem_coluna("rv_anexos_lidos", "paginas_triadas"):
        bd.escrever("ALTER TABLE rv_anexos_lidos ADD COLUMN paginas_triadas INTEGER")
    # CONFIRMA AQUI, como o script de esquema do SQLite confirmava sozinho: a
    # escrita pega a trava do banco, e `ler` vai à rede logo depois — sem isto
    # o balcão esperava a triagem da IA para gravar (L042R).
    con.commit()


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _tem_tabela(con, nome: str) -> bool:
    return banco(con).tem_tabela(nome)


def modelo_barato(con: sqlite3.Connection) -> str:
    if _tem_tabela(con, "settings"):
        linha = banco(con).um("SELECT value FROM settings WHERE key = %s",
                              (CHAVE_MODELO,))
        if linha and str(linha["value"]).strip():
            return str(linha["value"]).strip()
    return MODELO_BARATO


# ------------------------------------------------------------ onde estão

def anexos(con: sqlite3.Connection, origem: dict | None) -> list[dict]:
    """Os arquivos daquela entidade, do mais velho para o mais novo. Só LÊ.

    `origem` é {"entidade": "NT_ATO"|"RI_PROTOCOLO", "id": n} — o que a tela
    de lavrar tem à mão: o ato das Notas, ou a prenotação escolhida no RI.
    """
    if not origem or not origem.get("id") or not _tem_tabela(con, "attachments"):
        return []
    linhas = banco(con).ler(
        """SELECT id, original_name, stored_path, sha256, size_bytes FROM attachments
            WHERE entity_type = %s AND entity_id = %s ORDER BY id""",
        (origem["entidade"], int(origem["id"])))
    return [{"id": r["id"], "nome": r["original_name"],
             "caminho": r["stored_path"], "sha256": r["sha256"] or "",
             "tamanho": r["size_bytes"]} for r in linhas]


def assinatura(lista: list[dict]) -> str:
    """O conjunto de arquivos, para a revisão saber que os anexos mudaram."""
    return hashlib.sha256("|".join(sorted(a["sha256"] or str(a["id"])
                                          for a in lista)).encode()).hexdigest()


# ------------------------------------------------------------ as páginas

def _jpeg(imagem) -> str:
    imagem = imagem.convert("L")
    maior = max(imagem.size)
    if maior > LADO_MAIOR_PX:
        fator = LADO_MAIOR_PX / maior
        imagem = imagem.resize((int(imagem.size[0] * fator), int(imagem.size[1] * fator)))
    saida = io.BytesIO()
    imagem.save(saida, format="JPEG", quality=65)
    return base64.b64encode(saida.getvalue()).decode("ascii")


def paginas_do_arquivo(caminho: Path, nome: str) -> list[dict]:
    """[{texto, imagem()}] por página. A imagem só se gera se for pedida.

    `imagem` é uma função: gerar a imagem de quarenta páginas para usar três
    custaria memória e tempo à toa.
    """
    ext = Path(nome or str(caminho)).suffix.lower()
    if ext in EXTENSOES_DE_IMAGEM:
        def imagem(c=caminho):
            from PIL import Image
            with Image.open(c) as im:
                return _jpeg(im)
        return [{"texto": "", "imagem": imagem}]
    if ext in (".docx", ".odt"):
        # A PETIÇÃO E A MINUTA CHEGAM EM WORD — medido em 07/10/2026: seis dos
        # anexos da produção são .docx (inventário, minuta, nota de exigência).
        # O texto se lê aqui, de graça; a «página» é um pedaço de 3 mil letras.
        texto = texto_de_editor(caminho, ext)
        pedacos = [texto[i:i + LETRAS_POR_PAGINA_DE_EDITOR]
                   for i in range(0, len(texto), LETRAS_POR_PAGINA_DE_EDITOR)]
        return [{"texto": p.strip().ljust(LETRAS_DE_PAGINA_COM_TEXTO), "imagem": None}
                for p in pedacos if p.strip()]
    if ext != ".pdf":
        raise AnexoIlegivel(f"formato {ext or 'sem extensão'} não é lido pela revisão")
    import pypdfium2 as pdfium
    try:
        doc = pdfium.PdfDocument(str(caminho))
    except Exception as erro:                      # noqa: BLE001 — vira motivo na tela
        raise AnexoIlegivel(f"o PDF não abre ({type(erro).__name__})") from erro
    # O NÚMERO DE PÁGINAS TEM TETO (LX12, LS02 M3, 19/10/2026): cada página
    # tem o texto lido aqui e pode virar imagem depois; um PDF de cem mil
    # páginas prendia o servidor. A imagem já sai com o lado maior em
    # `LADO_MAIOR_PX`, e por isso a área não precisa de teto próprio.
    try:
        TETO.conferir_paginas(len(doc), "o PDF")
    except TETO.TetoExcedido as erro:
        doc.close()
        raise AnexoIlegivel(str(erro)) from erro
    paginas = []
    for i in range(len(doc)):
        pagina = doc[i]
        texto = pagina.get_textpage().get_text_bounded() or ""

        def imagem(c=caminho, i=i):
            d = pdfium.PdfDocument(str(c))
            try:
                largura, altura = d[i].get_size()
                escala = LADO_MAIOR_PX / max(largura, altura, 1)
                return _jpeg(d[i].render(scale=escala, grayscale=True).to_pil())
            finally:
                d.close()
        paginas.append({"texto": texto.strip(), "imagem": imagem})
    doc.close()
    return paginas


def texto_de_editor(caminho: Path, ext: str) -> str:
    """O texto corrido de um .docx ou .odt, parágrafo por linha. Só LÊ."""
    import html
    import zipfile
    parte = "word/document.xml" if ext == ".docx" else "content.xml"
    fim_de_paragrafo = "</w:p>" if ext == ".docx" else "</text:p>"
    try:
        with zipfile.ZipFile(caminho) as z:
            # COM TETO (LX12, LS02 M2): o anexo vem do balcão, e o XML de um
            # `.docx` de 1 KB pode se abrir em gigabytes (zip-bomba).
            TETO.conferir_pacote(z)
            xml = TETO.ler_membro(z, parte).decode("utf-8", "replace")
    except TETO.TetoExcedido as erro:
        raise AnexoIlegivel(str(erro)) from erro
    except (zipfile.BadZipFile, KeyError) as erro:
        raise AnexoIlegivel(f"o arquivo {ext} não abre ({type(erro).__name__})") from erro
    xml = xml.replace(fim_de_paragrafo, "\n")
    # Quebra de linha e tabulação dentro do parágrafo (o cabeçalho das notas
    # desta casa usa as duas) — sem isto «BRASIL» e «ESTADO» saíam grudados.
    xml = re.sub(r"<w:br[^>]*/>|<text:line-break/>", "\n", xml)
    xml = re.sub(r"<w:tab/>|<text:tab/>", " ", xml)
    linhas = (" ".join(html.unescape(re.sub(r"<[^>]+>", "", l)).split())
              for l in xml.split("\n"))
    return "\n".join(l for l in linhas if l)


def _tem_texto(pagina: dict) -> bool:
    return len(pagina["texto"]) >= LETRAS_DE_PAGINA_COM_TEXTO


# ------------------------------------------------------------ a IA barata

def _json(texto: str) -> dict:
    m = re.search(r"\{.*\}", texto or "", re.S)
    return json.loads(m.group(0)) if m else {}


def _pedir(conversar, pasta: Path, modelo: str, instrucao: str, texto: str,
           imagens: list[str]) -> dict:
    return conversar(pasta, provedor=PROVEDOR, sistema=instrucao,
                     conversa=[{"tipo": "user", "texto": texto,
                                "imagens": [{"mime": "image/jpeg", "base64": b}
                                            for b in imagens]}],
                     ferramentas=[], modelo=modelo, maximo_de_saida=4000)


def triar(conversar, pasta: Path, modelo: str, nome: str, paginas: list[dict],
          contexto: str) -> dict:
    """O que o documento é e se ele importa, pelas primeiras páginas.

    Devolve também `vistas`: quantas páginas a triagem viu. É por ela que
    `ler` sabe se o «não importante» vale para o arquivo inteiro."""
    vistas = paginas[:PAGINAS_DA_TRIAGEM]
    pergunta = (f"Ato: {contexto}\nArquivo: {nome} ({len(paginas)} página(s); "
                f"você vê as {len(vistas)} primeiras)\n")
    imagens: list[str] = []
    for n, p in enumerate(vistas, start=1):
        if _tem_texto(p):
            pergunta += f"\nTexto da página {n}:\n" + p["texto"][:LETRAS_POR_PAGINA_DA_TRIAGEM]
        else:
            imagens.append(p["imagem"]())
            pergunta += f"\nA página {n} vai como imagem (a {len(imagens)}ª imagem)."
    r = _pedir(conversar, pasta, modelo, INSTRUCAO_TRIAGEM, pergunta, imagens)
    d = _json(r.get("texto") or "")
    return {"tipo": str(d.get("tipo") or "documento")[:80],
            "importante": d.get("importante") is not False,      # na dúvida, importa
            "motivo": str(d.get("motivo") or "")[:300], "vistas": len(vistas),
            "entrada": int(r.get("entrada") or 0), "saida": int(r.get("saida") or 0)}


def transcrever(conversar, pasta: Path, modelo: str, paginas: list[dict],
                limite: int) -> tuple[str, int, int, int]:
    """(texto, páginas lidas, tokens de entrada, de saída). Até `limite` páginas.

    A página com texto digital entra como está; as digitalizadas vão ao modelo
    barato em grupos de três, quatro grupos de cada vez.
    """
    alvo = paginas[:limite]
    pedacos: dict[int, str] = {}
    grupos: list[list[int]] = []
    atual: list[int] = []
    for n, p in enumerate(alvo, start=1):
        if _tem_texto(p):
            pedacos[n] = f"[página {n}]\n{p['texto']}"
        else:
            atual.append(n)
            if len(atual) == PAGINAS_POR_PEDIDO:
                grupos.append(atual)
                atual = []
    if atual:
        grupos.append(atual)

    # AS IMAGENS SE GERAM AQUI, UMA A UMA, E SÓ A REDE VAI EM PARALELO: o PDFium
    # não pode ser usado por duas threads ao mesmo tempo (derruba o processo,
    # que é o servidor do balcão).
    prontos = [(numeros, [alvo[n - 1]["imagem"]() for n in numeros])
               for numeros in grupos]

    def um_grupo(par):
        numeros, imagens = par
        r = _pedir(conversar, pasta, modelo, INSTRUCAO_TRANSCRICAO,
                   f"Páginas {', '.join(map(str, numeros))} deste documento.", imagens)
        return numeros, r

    entrada = saida = 0
    if prontos:
        with ThreadPoolExecutor(max_workers=PEDIDOS_SIMULTANEOS) as pool:
            for numeros, r in pool.map(um_grupo, prontos):
                pedacos[numeros[0]] = (r.get("texto") or "").strip() or \
                    f"[páginas {numeros}: sem transcrição]"
                entrada += int(r.get("entrada") or 0)
                saida += int(r.get("saida") or 0)
    texto = "\n".join(pedacos[k] for k in sorted(pedacos))
    return texto, len(alvo), entrada, saida


# ------------------------------------------------------------ o conjunto

def _guardado(con, sha: str) -> dict | None:
    return banco(con).um("SELECT * FROM rv_anexos_lidos WHERE sha256 = %s", (sha,))


def _guardar(con, linha: dict) -> None:
    cols = list(linha)
    # `sha256` é a chave e a linha não tem filho: atualizar no lugar equivale ao REPLACE.
    atualiza = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "sha256")
    banco(con).escrever(f"INSERT INTO rv_anexos_lidos ({', '.join(cols)}) "
                        f"VALUES ({', '.join('%s' for _ in cols)}) "
                        f"ON CONFLICT (sha256) DO UPDATE SET {atualiza}",
                        [linha[c] for c in cols])
    con.commit()


def ler(con: sqlite3.Connection, pasta: Path, origem: dict | None, *,
        contexto: str = "", conversar=None, mascarada: bool = False) -> dict:
    """Lê os anexos da origem. Devolve {bloco, resumo, aviso, tokens}.

    `bloco` é o texto que entra no dossiê; `resumo` é a lista para a tela;
    `aviso` diz o que não foi lido e por quê. Nunca levanta por causa de um
    arquivo: o arquivo que falha vira linha com o motivo.
    """
    import functools

    import agente_provedores as AP
    # O REGISTRO DO USO DE IA (LF01) vai preso ao transporte aqui, na entrada:
    # triagem e transcrição chamam `conversar` lá dentro, em quatro linhas de
    # execução, e todas levam a mesma finalidade e a mesma origem. Documento
    # digitalizado não se mascara (ver abaixo), e por isso `mascarado=False`.
    entidade = str((origem or {}).get("entidade") or "")
    origem_ref = f"{entidade}:{(origem or {}).get('id') or ''}" if origem else ""
    conversar = functools.partial(conversar or AP.conversar, modulo="revisao_anexos",
                                  finalidade="revisao_anexos", referencia=origem_ref,
                                  atribuicao={"NT_ATO": "NOTAS", "RI_PROTOCOLO": "RI"}.get(
                                      entidade, ""),
                                  mascarado=False)
    lista = anexos(con, origem)
    if not lista:
        return {"bloco": "", "resumo": [], "aviso": "", "tokens": 0}
    if mascarada:
        return {"bloco": "", "resumo": [], "tokens": 0,
                "aviso": ("Os anexos não foram lidos: a revisão está com máscara, e "
                          "documento digitalizado não se mascara.")}
    init_schema(con)
    modelo = modelo_barato(con)
    resumo, blocos, avisos = [], [], []
    tokens = 0
    restam = TETO_DE_PAGINAS
    total_paginas = 0
    for a in lista:
        item = {"nome": a["nome"], "tipo": "", "importante": None, "motivo": "",
                "paginas": 0, "lidas": 0, "reaproveitado": False}
        resumo.append(item)
        caminho = Path(a["caminho"] or "")
        sha = a["sha256"] or ""
        if not sha and caminho.is_file():
            sha = hashlib.sha256(caminho.read_bytes()).hexdigest()
        ja = _guardado(con, sha) if sha else None
        if ja and ja["situacao"] in ("LIDO", "TRIADO"):
            # JÁ LIDO: não se paga de novo. A exceção é o importante que ficou
            # cortado pelo teto numa revisão anterior e agora cabe mais — o
            # caso raro, e aí ele se lê outra vez.
            lidas = ja["paginas_lidas"] or 0
            incompleto = bool(ja["importante"]) and lidas < (ja["paginas"] or 0)
            # O DESCARTE ANTIGO SÓ VALE SE A TRIAGEM VIU O ARQUIVO INTEIRO (M7):
            # o de antes do LX13 viu uma página, e o de várias páginas se
            # passa pela triagem de novo, com a régua de hoje.
            descarte_cego = (not ja["importante"]
                             and (ja["paginas_triadas"] or 1) < (ja["paginas"] or 0))
            if not (incompleto and restam > lidas) and not descarte_cego:
                item.update(tipo=ja["tipo"], importante=bool(ja["importante"]),
                            motivo=ja["motivo"] or "", paginas=ja["paginas"] or 0,
                            lidas=lidas, reaproveitado=True)
                total_paginas += item["paginas"]
                if ja["importante"] and ja["transcricao"]:
                    restam -= lidas
                    blocos.append(_bloco(item, ja["transcricao"]))
                continue
        if not caminho.is_file():
            item.update(motivo="o arquivo não está na pasta do sistema")
            continue
        try:
            paginas = paginas_do_arquivo(caminho, a["nome"])
        except AnexoIlegivel as erro:
            item.update(motivo=str(erro))
            continue
        if not paginas:
            item.update(motivo="o arquivo não tem página")
            continue
        item["paginas"] = len(paginas)
        total_paginas += len(paginas)
        linha = {"sha256": sha, "nome": a["nome"], "paginas": len(paginas),
                 "paginas_texto": sum(_tem_texto(p) for p in paginas),
                 "paginas_imagem": sum(not _tem_texto(p) for p in paginas),
                 "modelo": modelo, "lido_em": _agora(), "erro": None,
                 "tokens_entrada": 0, "tokens_saida": 0, "transcricao": None,
                 "paginas_lidas": 0, "paginas_triadas": None}
        try:
            t = triar(conversar, pasta, modelo, a["nome"], paginas, contexto)
            if not t["importante"] and t["vistas"] < len(paginas):
                # O QUE A TRIAGEM NÃO VIU NÃO SE DESCARTA (M7 do LS03): a capa
                # diz «comprovante», e a página 4 pode ser o mandado.
                t["importante"] = True
                t["motivo"] = (f"{t['motivo']} — a triagem viu {t['vistas']} de "
                               f"{len(paginas)} páginas, e o resto não se descarta "
                               "pela capa").lstrip(" —")
            linha.update(tipo=t["tipo"], importante=int(t["importante"]),
                         motivo=t["motivo"], tokens_entrada=t["entrada"],
                         tokens_saida=t["saida"], situacao="TRIADO",
                         paginas_triadas=t["vistas"])
            item.update(tipo=t["tipo"], importante=t["importante"], motivo=t["motivo"])
            if t["importante"] and restam > 0:
                texto, lidas, e, s = transcrever(conversar, pasta, modelo, paginas, restam)
                restam -= lidas
                linha.update(transcricao=texto, paginas_lidas=lidas, situacao="LIDO",
                             tokens_entrada=linha["tokens_entrada"] + e,
                             tokens_saida=linha["tokens_saida"] + s)
                item["lidas"] = lidas
                blocos.append(_bloco(item, texto))
        except Exception as erro:                  # noqa: BLE001 — vira motivo na tela
            linha.update(situacao="ERRO", erro=f"{type(erro).__name__}: {str(erro)[:200]}")
            item["motivo"] = "não consegui ler agora (tenta-se na próxima revisão)"
        tokens += linha["tokens_entrada"] + linha["tokens_saida"]
        if sha:
            _guardar(con, linha)

    fora = [i for i in resumo if i["importante"] and i["lidas"] < i["paginas"]]
    if total_paginas > TETO_DE_PAGINAS:
        avisos.append(
            f"Os anexos somam {total_paginas} páginas, acima do teto de "
            f"{TETO_DE_PAGINAS}. " + (
                "Ficaram sem leitura: " + "; ".join(
                    f"{i['nome']} ({i['paginas'] - i['lidas']} de {i['paginas']} pág.)"
                    for i in fora) + ". Confira esses à mão." if fora else
                "Todas as páginas importantes couberam."))
    return {"bloco": "\n\n".join(blocos), "resumo": resumo,
            "aviso": " ".join(avisos), "tokens": tokens}


def _bloco(item: dict, texto: str) -> str:
    cabeca = (f"--- {item['tipo'] or 'documento'}: {item['nome']} "
              f"({item['lidas']} de {item['paginas']} página(s) lidas) ---")
    if len(texto) > LETRAS_POR_DOCUMENTO:
        texto = texto[:LETRAS_POR_DOCUMENTO] + "\n[... cortado: documento longo]"
    return cabeca + "\n" + texto
