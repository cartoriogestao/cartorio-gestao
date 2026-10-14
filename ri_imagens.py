"""
As fichas digitalizadas do Registro de Imoveis — achar o arquivo no disco.

O PROBLEMA, EM UMA LINHA
    O banco guarda `00003967.0001`. No disco o arquivo e `00003967.0001.TIF`.

POR QUE ISSO DERRUBOU TUDO DE UMA VEZ
    O `.0001` NAO E EXTENSAO: e o numero da pagina da ficha. A matricula 3967
    tem as paginas .0001, .0002 e assim por diante. Quem le o nome supoe
    extensao e casa por igualdade exata — e ai basta o arquivo real ter
    qualquer sufixo para as 3.689 imagens falharem juntas, em silencio, com a
    tela dizendo "0 localizadas" sem dizer por que.

    Foi assim que isto chegou como "as imagens nao estao funcionando".

COMO SE CASA AGORA
    Tres chaves para o mesmo arquivo: o nome inteiro, o nome sem a ultima
    extensao, e os dois em caixa baixa. Windows nao distingue maiuscula de
    minuscula no nome de arquivo; o indice tambem nao deve distinguir.

    E a varredura e em profundidade. A primeira versao descia um nivel so, e a
    pasta do E-Oficio nem sempre e plana.

O QUE ESTE MODULO NAO RESOLVE
    Pasta errada. Nenhum casamento esperto encontra arquivo que nao esta la —
    por isso `diagnostico()` devolve os dois lados, o que o banco espera e o
    que o disco tem, para a tela mostrar lado a lado. Erro que se explica
    sozinho custa cinco segundos; erro mudo custa uma semana.
"""
from __future__ import annotations

import os
from pathlib import Path


def chaves(nome: str) -> list[str]:
    """As formas pelas quais um nome pode ser procurado ou encontrado.

    Sempre em caixa baixa, e sempre com a variante sem a ultima extensao.
    """
    limpo = (nome or "").strip()
    if not limpo:
        return []
    saida = [limpo.lower()]
    sem_ext = limpo.rsplit(".", 1)[0]
    if sem_ext and sem_ext != limpo:
        saida.append(sem_ext.lower())
    return saida


def indexar(raiz: str | Path) -> tuple[dict[str, str], int, list[str]]:
    """Varre a pasta em profundidade e indexa por todas as chaves.

    Devolve (indice, quantos arquivos, alguns nomes de exemplo). O exemplo
    serve para a tela mostrar como sao os arquivos que ELA encontrou, ao lado
    dos nomes que o banco procura.

    `setdefault` de proposito: havendo o mesmo nome em duas pastas, o primeiro
    encontrado vence e o segundo nao o sobrescreve calado. Se isso importar um
    dia, `duplicados()` acha.
    """
    indice: dict[str, str] = {}
    arquivos = 0
    exemplos: list[str] = []
    for atual, _dirs, nomes in os.walk(str(raiz)):
        for nome in nomes:
            arquivos += 1
            if len(exemplos) < 5:
                exemplos.append(nome)
            caminho = str(Path(atual) / nome)
            for chave in chaves(nome):
                indice.setdefault(chave, caminho)
    return indice, arquivos, exemplos


def achar(nome_no_banco: str, indice: dict[str, str]) -> str | None:
    """O caminho do arquivo, ou None. Procura por todas as chaves."""
    for chave in chaves(nome_no_banco):
        caminho = indice.get(chave)
        if caminho:
            return caminho
    return None


def duplicados(raiz: str | Path) -> dict[str, list[str]]:
    """Nomes que aparecem em mais de uma pasta.

    A carga assume que o nome e unico entre as pastas — e a razao de indexar
    por nome em vez de pelo `id_path`, que o E-Oficio nao exportou. Se a
    suposicao quebrar, e melhor descobrir por aqui do que por uma ficha que
    abre a matricula errada.
    """
    vistos: dict[str, list[str]] = {}
    for atual, _dirs, nomes in os.walk(str(raiz)):
        for nome in nomes:
            vistos.setdefault(nome.lower(), []).append(str(Path(atual) / nome))
    return {k: v for k, v in vistos.items() if len(v) > 1}


def e_pasta(p: Path) -> bool:
    """`is_dir()` que nao levanta quando o caminho e de rede.

    `WinError 64 - o nome da rede nao esta mais disponivel` escapa do
    `is_dir()` do Python. Com o E-Oficio desligado, uma raiz UNC gravada nas
    configuracoes viraria erro 500 em vez de tela vazia.
    """
    try:
        return Path(p).is_dir()
    except OSError:
        return False


def indexar_varias(raizes) -> tuple[dict[str, str], int, list[str], list[Path]]:
    """Um indice so, feito de todas as pastas que abrirem.

    POR QUE PLURAL
        A tela de assinaturas media UMA pasta — a que estivesse gravada na
        configuracao. Trazidas as 3.644 firmas para dentro do acervo, a
        configuracao continuava apontando para o `\\\\servidor\\C11\\Firmas`
        morto, e a tela seguia dizendo "nenhuma assinatura localizada" com os
        arquivos ali, no disco, ao lado.

        Medir uma pasta e responder sobre todas era a falha. A ordem das
        raizes decide o desempate; quem chama e que sabe qual prefere.
    """
    indice: dict[str, str] = {}
    arquivos = 0
    exemplos: list[str] = []
    abertas: list[Path] = []
    for raiz in raizes:
        caminho = Path(raiz)
        if not e_pasta(caminho):
            continue
        abertas.append(caminho)
        parcial, n, ex = indexar(caminho)
        arquivos += n
        for chave, valor in parcial.items():
            indice.setdefault(chave, valor)
        for e in ex:
            if len(exemplos) < 5:
                exemplos.append(e)
    return indice, arquivos, exemplos, abertas


def diagnostico(nomes_no_banco: list[str], raiz: str | Path | list) -> dict:
    """Os dois lados, para a tela mostrar quando nada casar.

    Nao decide nada: mede e mostra. Quem sabe onde estao as fichas e a
    serventia, nao o sistema.

    `raiz` aceita uma pasta ou uma lista delas — ver `indexar_varias`.
    """
    raizes = list(raiz) if isinstance(raiz, (list, tuple)) else [raiz]
    rotulo = " | ".join(str(Path(r)) for r in raizes)
    indice, arquivos, exemplos, abertas = indexar_varias(raizes)
    if not abertas:
        return {"raiz_existe": False, "raiz": rotulo, "arquivos": 0,
                "achadas": 0, "perdidas": len(nomes_no_banco),
                "exemplos_disco": [], "exemplos_perdidos": nomes_no_banco[:5],
                "duplicados": 0}
    achadas, perdidos = 0, []
    for nome in nomes_no_banco:
        if achar(nome, indice):
            achadas += 1
        elif len(perdidos) < 5:
            perdidos.append(nome)
    return {
        "raiz_existe": True,
        "raiz": " | ".join(str(p) for p in abertas),
        "arquivos": arquivos,
        "achadas": achadas, "perdidas": len(nomes_no_banco) - achadas,
        "exemplos_disco": exemplos, "exemplos_perdidos": perdidos,
        "duplicados": sum(len(duplicados(p)) for p in abertas),
    }


def pillow_disponivel() -> bool:
    """Se falta o Pillow, a ficha nao abre — e o motivo nao e o caminho.

    Os arquivos sao TIFF Grupo 4, que navegador nenhum exibe. Sem a conversao
    para PNG a tela entrega o TIFF para download, e o operador ve "nao abre".
    Sao dois defeitos diferentes com o mesmo sintoma, e a tela precisa separar
    um do outro.
    """
    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True
