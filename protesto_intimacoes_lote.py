"""O PDF com várias intimações entregues — separado por aviso, pelo QR.

Pedido do oficial, 15/10/2026: «implantar a api que permita juntar um pdf com
vários arquivos de intimações e o agente separa e sobe no título respectivo o
aviso entregue». E, sobre a leitura: «pq a IA precisaria ler o nome de quem
recebeu? acho que não precisa» — e não precisa: o CN-MA pede a PROVA do
recebimento (art. 921, § 6º, I), e a prova é o papel assinado anexado.

**POR ISSO NÃO HÁ IA AQUI.** O aviso sai impresso com um QR que diz qual
aviso ele é (`conteudo_do_qr`), e a folha escaneada se identifica sozinha,
lida pelo OpenCV que já está instalado — sem custo e sem mandar nada para
fora da casa. A folha sem QR (o verso) fica com o aviso da folha anterior; a
que vem antes de qualquer QR, ou cujo QR não se lê, aparece na conferência
dizendo isso, e não some.

**CONFERIR E REGISTRAR SÃO DOIS PASSOS**, como na remessa da CRA: `conferir`
não grava nada; `registrar_um` lavra a intimação pessoal (pelo caminho de
sempre, `protesto_aviso.registrar_entrega`) e anexa ao aviso só as folhas
dele. Um aviso por vez, cada um na sua transação — um que falha não derruba
os outros.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from io import BytesIO
from pathlib import Path
from typing import Any

import protesto_aviso as AV

PREFIXO = "CG-AVISO"
QR = re.compile(rf"^{PREFIXO}:(?P<id>\d+):(?P<numero>\d+)/(?P<ano>\d{{4}}):"
                r"(?P<protocolo>[0-9A-Za-z]*)$")
LIMITE_DO_LOTE = 100 * 1024 * 1024        # 100 MB
LIMITE_DE_PAGINAS = 400
# A RESOLUÇÃO DA LEITURA. 150 dpi lê o QR de 2,5 cm com folga; a segunda
# passada, em 300, é para o papel escaneado em baixa ou torto.
DPI_DE_LEITURA = (150, 300)


class LoteError(ValueError):
    """Erro de regra do lote, com a frase pronta para o balcão."""


# --------------------------------------------------------------- o QR do aviso


def conteudo_do_qr(aviso: Any, protocolo: Any = "") -> str:
    """O que vai DENTRO do QR do aviso. Só calcula.

    O `id` acha o aviso; o número/ano CONFEREM — um QR de outra instalação, ou
    de um aviso apagado e renumerado, cairia num aviso errado se o `id`
    sozinho decidisse. O protocolo do título vai junto para quem ler o QR com
    o celular saber de que título é.
    """
    protocolo = re.sub(r"[^0-9A-Za-z]", "", str(protocolo or ""))
    return (f"{PREFIXO}:{int(aviso['id'])}:{int(aviso['numero'])}/"
            f"{int(aviso['ano'])}:{protocolo}")


def png_do_qr(conteudo: str) -> bytes:
    """O PNG do QR. Só calcula. Correção de erro alta (`h`): o papel volta
    dobrado, carimbado e assinado por cima."""
    import segno
    buf = BytesIO()
    segno.make(conteudo, error="h").save(buf, kind="png", scale=10, border=2)
    return buf.getvalue()


def ler_conteudo(texto: Any) -> dict | None:
    """O QR lido, em partes — ou None se não é QR de aviso desta casa."""
    achado = QR.match(str(texto or "").strip())
    if not achado:
        return None
    return {"aviso_id": int(achado["id"]), "numero": int(achado["numero"]),
            "ano": int(achado["ano"]), "protocolo": achado["protocolo"]}


# ------------------------------------------------------------- ler o PDF


def _abrir(pdf: bytes):
    try:
        import pymupdf as fitz
    except ImportError:  # pragma: no cover — versões antigas
        import fitz
    if not pdf:
        raise LoteError("O arquivo está vazio.")
    if len(pdf) > LIMITE_DO_LOTE:
        raise LoteError(
            f"O PDF passa de {LIMITE_DO_LOTE // 1024 // 1024} MB. Escaneie em "
            f"partes menores, ou com resolução menor.")
    if not bytes(pdf).startswith(b"%PDF"):
        raise LoteError("O arquivo não é um PDF. Escaneie o maço em PDF.")
    try:
        doc = fitz.open(stream=bytes(pdf), filetype="pdf")
    except Exception as erro:  # noqa: BLE001 — o fitz tem várias exceções
        raise LoteError("O PDF não abre — salve de novo do scanner.") from erro
    if doc.page_count == 0:
        raise LoteError("O PDF não tem nenhuma página.")
    if doc.page_count > LIMITE_DE_PAGINAS:
        raise LoteError(
            f"O PDF tem {doc.page_count} páginas; o limite é "
            f"{LIMITE_DE_PAGINAS}. Separe em maços menores.")
    return doc


def _qrs_da_pagina(pagina) -> list[str]:
    """Os textos de QR achados numa página, tentando as duas resoluções."""
    import cv2
    import numpy as np
    detector = cv2.QRCodeDetector()
    for dpi in DPI_DE_LEITURA:
        pix = pagina.get_pixmap(dpi=dpi, colorspace="gray")
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width)
        try:
            ok, textos, _pontos, _ = detector.detectAndDecodeMulti(img)
        except cv2.error:
            ok, textos = False, ()
        achados = [t for t in (textos or ()) if t] if ok else []
        if not achados:
            texto, _pts, _ = detector.detectAndDecode(img)
            achados = [texto] if texto else []
        if achados:
            return achados
    return []


def ler_paginas(pdf: bytes) -> list[dict]:
    """Cada página com o aviso que o QR dela diz. NÃO grava e NÃO decide."""
    doc = _abrir(pdf)
    paginas = []
    for i, pagina in enumerate(doc):
        textos = _qrs_da_pagina(pagina)
        nossos = [x for x in (ler_conteudo(t) for t in textos) if x]
        # O MESMO AVISO DUAS VEZES NA FOLHA é um aviso só — a folha inteira
        # escaneada com o canhoto ainda preso, por exemplo.
        nossos = list({q["aviso_id"]: q for q in nossos}.values())
        paginas.append({
            "pagina": i + 1,
            "qr": nossos[0] if len(nossos) == 1 else None,
            "qr_em_conflito": len({q["aviso_id"] for q in nossos}) > 1,
            "outros_qr": len(textos) - len(nossos),
        })
    return paginas


def agrupar(paginas: list[dict]) -> dict:
    """As páginas juntadas por aviso. Só calcula.

    A página com QR abre um aviso; a sem QR é o verso, e fica com o aviso de
    antes. **O mesmo aviso em dois trechos separados não se junta calado**: é
    papel fora de ordem, e quem confere precisa ver.
    """
    grupos: list[dict] = []
    soltas: list[int] = []
    for p in paginas:
        if p["qr_em_conflito"]:
            soltas.append(p["pagina"])
            continue
        if p["qr"]:
            ultimo = grupos[-1] if grupos else None
            if ultimo and ultimo["aviso_id"] == p["qr"]["aviso_id"] \
                    and ultimo["paginas"][-1] == p["pagina"] - 1:
                ultimo["paginas"].append(p["pagina"])
            else:
                grupos.append({**p["qr"], "paginas": [p["pagina"]]})
        elif grupos and grupos[-1]["paginas"][-1] == p["pagina"] - 1:
            grupos[-1]["paginas"].append(p["pagina"])
        else:
            soltas.append(p["pagina"])
    vistos: dict[int, int] = {}
    for g in grupos:
        vistos[g["aviso_id"]] = vistos.get(g["aviso_id"], 0) + 1
    for g in grupos:
        g["repetido"] = vistos[g["aviso_id"]] > 1
    return {"grupos": grupos, "soltas": soltas,
            "paginas": len(paginas)}


# -------------------------------------------------------------- conferir


def _situacao_do_grupo(con: sqlite3.Connection, g: dict) -> dict:
    aviso = AV.ler(con, g["aviso_id"])
    if not aviso:
        return {"acao": "RECUSA", "porque": "o aviso do QR não existe nesta casa"}
    if (int(aviso["numero"]), int(aviso["ano"])) != (g["numero"], g["ano"]):
        return {"acao": "RECUSA", "porque": (
            f"o QR diz aviso {g['numero']}/{g['ano']}, e o aviso deste número "
            f"interno é {aviso['numero']}/{aviso['ano']} — QR de outro papel")}
    if g["repetido"]:
        return {"acao": "RECUSA", "porque": (
            "este aviso aparece em dois trechos do PDF — confira a ordem das "
            "folhas e escaneie de novo")}
    if aviso["situacao"] in ("EMITIDO", "NAO_ENTREGUE"):
        return {"acao": "REGISTRA", "porque": (
            "escolha o desfecho: entregue (lavra a intimação pessoal) ou a "
            "tentativa que o canhoto anota — as folhas ficam anexadas")}
    if aviso["situacao"] in ("ENTREGUE", "EDITAL"):
        return {"acao": "ANEXA", "porque": (
            f"o desfecho já está registrado ({aviso['situacao'].lower()}); "
            f"só anexa as folhas como comprovante")}
    return {"acao": "RECUSA", "porque": (
        f"o aviso está {aviso['situacao']} — não recebe comprovante")}


def conferir(con: sqlite3.Connection, pdf: bytes) -> dict:
    """O que o PDF traz, aviso por aviso. NÃO GRAVA NADA."""
    lido = agrupar(ler_paginas(pdf))
    for g in lido["grupos"]:
        g.update(_situacao_do_grupo(con, g))
        aviso = AV.ler(con, g["aviso_id"])
        if aviso:
            tit = con.execute(
                "SELECT numero_titulo, protocolo FROM pt_titulos WHERE id=?",
                (int(aviso["titulo_id"]),)).fetchone()
            g["devedor_nome"] = aviso["devedor_nome"]
            g["numero_titulo"] = tit["numero_titulo"] if tit else None
            g["protocolo_titulo"] = tit["protocolo"] if tit else None
    lido["sha256"] = hashlib.sha256(bytes(pdf)).hexdigest()
    lido["prontos"] = sum(1 for g in lido["grupos"] if g["acao"] != "RECUSA")
    return lido


# ----------------------------------------------------- guardar entre os passos


def caminho_do_lote(pasta_de_arquivos: Any, sha256: str) -> Path:
    """Onde o PDF espera entre a conferência e o registro. O nome é o hash do
    conteúdo — e só hash: o nome que vem do formulário não vira caminho."""
    if not re.fullmatch(r"[0-9a-f]{64}", str(sha256 or "")):
        raise LoteError("O lote não foi reconhecido. Envie o PDF de novo.")
    return Path(pasta_de_arquivos) / "Protesto" / "Intimacoes" / "lotes" / \
        f"{sha256}.pdf"


def guardar_lote(pasta_de_arquivos: Any, pdf: bytes) -> str:
    """Grava o PDF do maço para o segundo passo. Devolve o hash."""
    sha = hashlib.sha256(bytes(pdf)).hexdigest()
    destino = caminho_do_lote(pasta_de_arquivos, sha)
    destino.parent.mkdir(parents=True, exist_ok=True)
    if not destino.exists():
        destino.write_bytes(bytes(pdf))
    return sha


def ler_lote(pasta_de_arquivos: Any, sha256: str) -> bytes:
    arquivo = caminho_do_lote(pasta_de_arquivos, sha256)
    if not arquivo.exists():
        raise LoteError("O PDF deste lote não está mais aqui. Envie de novo.")
    return arquivo.read_bytes()


def fatia(pdf: bytes, paginas: list[int]) -> bytes:
    """Só as folhas de um aviso, num PDF próprio. Só calcula."""
    try:
        import pymupdf as fitz
    except ImportError:  # pragma: no cover — versões antigas
        import fitz
    origem = _abrir(pdf)
    novo = fitz.open()
    for n in paginas:
        novo.insert_pdf(origem, from_page=int(n) - 1, to_page=int(n) - 1)
    # O MESMO RECORTE SAI COM OS MESMOS BYTES: sem metadados e sem o
    # identificador novo que o PDF ganha a cada gravação. É o que deixa a
    # trava de comprovante repetido (sha256 em `guardar_comprovante`)
    # reconhecer o mesmo lote registrado duas vezes — medido: com o
    # identificador novo, dois recortes iguais davam dois hashes diferentes.
    novo.set_metadata({})
    return novo.tobytes(garbage=3, deflate=True, no_new_id=True)


# -------------------------------------------------------------- registrar


ENTREGUE = "ENTREGUE"


def registrar_um(con: sqlite3.Connection, pdf: bytes, aviso_id: int, *,
                 quando: str | None, pasta_de_arquivos: Any, agora: str,
                 desfecho: Any = ENTREGUE, observacao: str | None = None,
                 usuario: str | None = None,
                 usuario_id: int | None = None) -> dict:
    """Registra UM aviso do lote. ESCREVE.

    **CONFERE DE NOVO**, a partir do PDF guardado: entre a tela e o clique o
    aviso pode ter sido registrado por outra pessoa, e o que vale é o que o
    banco diz agora. A entrega passa por `registrar_entrega` — o mesmo caminho
    do botão —, e o comprovante por `guardar_comprovante`.
    """
    lido = agrupar(ler_paginas(pdf))
    grupo = next((g for g in lido["grupos"]
                  if g["aviso_id"] == int(aviso_id)), None)
    if grupo is None:
        raise LoteError(f"O aviso {aviso_id} não está neste PDF.")
    situacao = _situacao_do_grupo(con, grupo)
    if situacao["acao"] == "RECUSA":
        raise LoteError(f"Aviso {grupo['numero']}/{grupo['ano']}: "
                        f"{situacao['porque']}.")
    # O MESMO PAPEL NÃO REGISTRA DUAS VEZES — conferido ANTES de lavrar: uma
    # tentativa registrada de novo viraria uma segunda tentativa que ninguém
    # fez, e o edital se fundamentaria em ida ao endereço que não houve.
    parte = fatia(pdf, grupo["paginas"])
    if AV.ja_tem_este_comprovante(con, int(aviso_id), parte):
        raise LoteError(f"Aviso {grupo['numero']}/{grupo['ano']}: estas folhas "
                        f"já foram registradas — nada foi feito de novo.")
    ato_id = None
    feito = situacao["acao"]
    if situacao["acao"] == "REGISTRA":
        entregue = str(desfecho or "").strip().upper() == ENTREGUE
        if not entregue and AV._inteiro(desfecho) not in AV.TODOS_OS_MOTIVOS:
            raise LoteError(f"Aviso {grupo['numero']}/{grupo['ano']}: escolha "
                            f"o desfecho — entregue, ou o motivo da tentativa.")
        r = AV.registrar_entrega(
            con, int(aviso_id), entregue=entregue, agora=agora,
            quando=(quando or None), entregador=AV.ENTREGADOR_DA_CASA,
            motivo=(None if entregue else desfecho),
            observacao=(observacao or "canhoto lido do PDF do lote, pelo QR "
                        "do aviso"),
            usuario=usuario)
        ato_id = r["ato_id"]
        feito = "ENTREGA" if entregue else "TENTATIVA"
    anexo = AV.guardar_comprovante(
        con, int(aviso_id),
        nome=f"intimacao-{grupo['numero']}-{grupo['ano']}.pdf",
        conteudo=parte,
        pasta_de_arquivos=pasta_de_arquivos, agora=agora,
        usuario_id=usuario_id)
    return {"aviso_id": int(aviso_id), "acao": feito,
            "ato_id": ato_id, "anexo_id": anexo["anexo_id"],
            "paginas": grupo["paginas"],
            "aviso": f"{grupo['numero']}/{grupo['ano']}"}
