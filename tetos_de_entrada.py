"""Os tetos do que entra por arquivo — LX12, 19/10/2026 (LS02, M1–M5).

POR QUE EXISTE
    A auditoria LS02 achou arquivos pequenos que viram coisa enorme dentro do
    servidor: um `.odt` de 1 KB que descompacta em gigabytes (zip-bomba), um
    `<text:s text:c="2000000000"/>` que pede dois bilhões de espaços, um PDF
    de MediaBox gigante ou um TIFF de milhares de quadros que viram bitmap de
    gigabytes, um PDF de mil páginas que vira mil chamadas PAGAS à IA, e um
    POST anônimo de 200 MB lido inteiro antes de qualquer recusa. O servidor é
    um processo só: derrubá-lo derruba o balcão inteiro.

    O oficial decidiu: teto em tudo, com padrão GENEROSO — nenhum arquivo de
    verdade da casa chega perto. Os números moram aqui, num lugar só, e não
    espalhados pelos módulos: seis tetos de "200 MB" escritos à mão
    divergiriam no primeiro ajuste.

POR QUE O AJUSTE É PELO AMBIENTE
    `CG_TETO_<NOME>` (ex.: `CG_TETO_PAGINAS=5000`) manda sobre o padrão. Quem
    lê o teto é função sem banco — a leitura do zip, a miniatura da ficha —, e
    o ajuste pelo ambiente do serviço já é o caminho da casa para o que não
    tem tela (`SELO_MARGEM_ODT`, `SELO_MARGEM_SAIDA`). Valor que não é inteiro
    positivo é ignorado: um teto zerado por engano recusaria tudo.
"""
from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

MB = 1024 * 1024

#: Os padrões. Ajuste pelo ambiente (`CG_TETO_<NOME>`), não aqui.
TETOS: dict[str, int] = {
    # Descompactado: o total do pacote e cada membro sozinho.
    "zip_bytes": 200 * MB,
    # O ZIP da exportação do E-Ofício é o único pacote grande de verdade: o
    # acervo montado dele tem 364 MB em SQLite (nota do `backup.py`), e os
    # `.jsonl`, texto puro, não pesam menos. Com o teto geral a carga legítima
    # seria recusada; com este, a zip-bomba ainda para antes de encher o disco
    # (e `extrair` confere o espaço livre).
    "acervo_bytes": 8 * 1024 * MB,
    "zip_entradas": 20_000,
    # Espaços de um `<text:s text:c="N"/>` do ODF.
    "text_c": 1_000,
    # Páginas de PDF e quadros de TIFF que se convertem em imagem.
    "paginas": 2_000,
    # Área do bitmap de UMA página renderizada (100 Mpx ≈ 300 MB em RGB).
    "pixels_por_pagina": 100_000_000,
    # Páginas por leitura de documentos pela IA — cada uma é chamada paga.
    "ia_paginas": 50,
    # Corpo de POST sem login (o webhook do WhatsApp).
    "corpo_anonimo_bytes": 2 * MB,
}

_PEDACO = 1024 * 1024


class TetoExcedido(ValueError):
    """O arquivo passou de um teto. A mensagem diz qual e o que fazer."""


def valor(nome: str) -> int:
    """O teto `nome`: o do ambiente (`CG_TETO_<NOME>`), se for inteiro > 0;
    senão o padrão de `TETOS`."""
    padrao = TETOS[nome]
    texto = (os.environ.get(f"CG_TETO_{nome.upper()}") or "").strip()
    try:
        ajustado = int(texto)
    except ValueError:
        return padrao
    return ajustado if ajustado > 0 else padrao


def _em_mb(n: int) -> str:
    return f"{n / MB:,.0f} MB".replace(",", ".")


def conferir_pacote(pacote: zipfile.ZipFile, *, teto_bytes: int | None = None) -> None:
    """Recusa o pacote com entradas demais ou que descompacta além do teto.

    Confere pelo que o índice do zip DECLARA, antes de ler qualquer membro —
    é barato e pega a zip-bomba comum. A que mente no índice é pega por
    `ler_membro`/`extrair`, que cortam na leitura.
    """
    infos = pacote.infolist()
    teto_n = valor("zip_entradas")
    if len(infos) > teto_n:
        raise TetoExcedido(
            f"O arquivo compactado tem {len(infos)} itens; o teto é {teto_n}. "
            f"Confira se é mesmo o arquivo certo (CG_TETO_ZIP_ENTRADAS ajusta).")
    teto_b = teto_bytes or valor("zip_bytes")
    total = sum(max(i.file_size, 0) for i in infos)
    if total > teto_b:
        raise TetoExcedido(
            f"O arquivo compactado se abre em {_em_mb(total)}; o teto é "
            f"{_em_mb(teto_b)}. Confira se é mesmo o arquivo certo "
            f"(CG_TETO_ZIP_BYTES ajusta).")


def _copiar_com_corte(origem, destino, teto: int, nome: str) -> int:
    lidos = 0
    while True:
        pedaco = origem.read(min(_PEDACO, teto + 1 - lidos))
        if not pedaco:
            return lidos
        lidos += len(pedaco)
        if lidos > teto:
            raise TetoExcedido(
                f"«{nome}», dentro do arquivo compactado, passa de "
                f"{_em_mb(teto)} ao abrir. Confira se é mesmo o arquivo certo "
                f"(CG_TETO_ZIP_BYTES ajusta).")
        destino(pedaco)


def ler_membro(pacote: zipfile.ZipFile, nome_ou_info) -> bytes:
    """`pacote.read(nome)` com teto: confere o tamanho declarado e, depois,
    corta a leitura em teto+1 — o cabeçalho do zip pode mentir."""
    info = (nome_ou_info if isinstance(nome_ou_info, zipfile.ZipInfo)
            else pacote.getinfo(nome_ou_info))
    teto = valor("zip_bytes")
    if info.file_size > teto:
        raise TetoExcedido(
            f"«{info.filename}», dentro do arquivo compactado, se abre em "
            f"{_em_mb(info.file_size)}; o teto é {_em_mb(teto)}. Confira se é "
            f"mesmo o arquivo certo (CG_TETO_ZIP_BYTES ajusta).")
    partes: list[bytes] = []
    with pacote.open(info) as fonte:
        _copiar_com_corte(fonte, partes.append, teto, info.filename)
    return b"".join(partes)


def extrair(pacote: zipfile.ZipFile, destino: Path, *,
            teto_bytes: int | None = None) -> None:
    """`extractall` com teto: confere o índice e extrai em fluxo, cortando no
    teto do TOTAL descompactado.

    O caminho de cada membro passa pela mesma régua do `zipfile`
    (`_extract_member` tira `..`, unidade e raiz — ver `_caminho_seguro`), e
    por isso nada sai de `destino`; só a cópia dos bytes é nossa, para poder
    cortar. `teto_bytes` troca o teto do total (o acervo usa
    `valor("acervo_bytes")`).

    O DISCO TAMBÉM SE CONFERE: o que o pacote declara precisa caber no espaço
    livre de `destino`, com folga — extrair até encher o disco da pasta de
    dados pararia o banco junto.
    """
    teto = teto_bytes or valor("zip_bytes")
    conferir_pacote(pacote, teto_bytes=teto)
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    declarado = sum(max(i.file_size, 0) for i in pacote.infolist())
    livre = shutil.disk_usage(destino).free
    if declarado + 512 * MB > livre:
        raise TetoExcedido(
            f"O arquivo compactado se abre em {_em_mb(declarado)} e o disco "
            f"tem {_em_mb(livre)} livres. Libere espaço antes de carregar.")
    restante = teto
    for info in pacote.infolist():
        alvo = _caminho_seguro(info.filename, destino)
        if info.is_dir():
            alvo.mkdir(parents=True, exist_ok=True)
            continue
        alvo.parent.mkdir(parents=True, exist_ok=True)
        with pacote.open(info) as fonte, open(alvo, "wb") as saida:
            restante -= _copiar_com_corte(fonte, saida.write, restante, info.filename)


def _caminho_seguro(nome: str, destino: Path) -> Path:
    """O lugar de `nome` dentro de `destino`, com a régua de
    `zipfile.ZipFile._extract_member`: sem unidade, sem raiz, sem `..`."""
    arcname = nome.replace("/", os.path.sep)
    if os.path.altsep:
        arcname = arcname.replace(os.path.altsep, os.path.sep)
    arcname = os.path.splitdrive(arcname)[1]
    invalidas = ("", os.path.curdir, os.path.pardir)
    arcname = os.path.sep.join(x for x in arcname.split(os.path.sep)
                               if x not in invalidas)
    if os.path.sep == "\\":
        arcname = zipfile.ZipFile._sanitize_windows_name(arcname, os.path.sep)  # noqa: SLF001
    return Path(destino) / arcname


def vezes_text_c(texto) -> int:
    """Quantos espaços um `text:c` pede, entre 1 e o teto. Inválido vale 1 —
    é o que o padrão ODF diz quando o atributo falta."""
    try:
        n = int(str(texto).strip())
    except (TypeError, ValueError):
        return 1
    return max(1, min(n, valor("text_c")))


def conferir_paginas(n: int, o_que: str = "o arquivo") -> None:
    """Recusa PDF/TIFF com mais páginas (quadros) que o teto."""
    teto = valor("paginas")
    if n > teto:
        raise TetoExcedido(
            f"{o_que[:1].upper()}{o_que[1:]} tem {n} páginas; o teto é {teto}. "
            f"Separe em partes menores (CG_TETO_PAGINAS ajusta).")


def escala_que_cabe(largura_pt: float, altura_pt: float, escala: float) -> float:
    """A escala pedida, ou a menor que faz o bitmap da página caber no teto
    de pixels. Página normal não muda; a de MediaBox gigante encolhe em vez
    de virar gigabytes de memória."""
    area = max(float(largura_pt), 1.0) * max(float(altura_pt), 1.0) * escala * escala
    teto = valor("pixels_por_pagina")
    if area <= teto:
        return escala
    return escala * (teto / area) ** 0.5
