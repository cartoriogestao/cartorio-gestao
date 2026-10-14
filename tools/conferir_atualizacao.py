"""Confere se a instalacao esta igual a arvore que gerou o pacote.

**SO MEDE.** Nao copia, nao apaga, nao move, nao abre o banco e nao importa o
sistema: le arquivo do disco e compara byte a byte. Rodar duas vezes da o mesmo
resultado, e rodar na duvida nao tem custo nenhum.

Por que ele existe
------------------

Em 15/09/2026 a instalacao do servidor estava com **25 arquivos a menos** que a
arvore, e os mais caros deles nao tinham cara de programa:

  `patches_natureza_averbacao.json`   lido pela correcao da natureza da averbacao
  `schemas/cargaRegistrosCompleto.xsd` lido pela carga da CRC
  `tools/*.py` (15 arquivos)          as ferramentas de conserto e de ensaio
  `pytest.ini`, `RODAR_SUITE_RAPIDA.cmd`, `.md` da raiz

O pacote `.cgu` levava todos eles — medido no proprio zip. Quem ficava para tras
era o `ATUALIZAR_SISTEMA.cmd`, que copiava **por lista de extensao**: `*.py`,
`templates\\*.html`, a pasta `static`, `modelos`, `DOCUMENTACAO`, `installer`.
Arquivo que nao casa com nenhum padrao da lista nao viaja, e **nao ha erro em
lugar nenhum**: o sistema sobe inteiro, o recurso que le aquele arquivo falha
depois, e quem descobre e o balcao.

  **A lista escrita a mao envelhece, e esta tinha 25 arquivos de defasagem.**
  O conserto foi o `.cmd` passar a espelhar a pasta inteira, com as exclusoes do
  empacotador — e este conferidor existe para medir o resultado, em vez de supor
  que chegou.

A REGUA E A DO PACOTE, E NAO UMA SEGUNDA
----------------------------------------

A lista do que e programa e do que e sobra de quem escreve o programa mora em
`tools/criar_atualizacao.py` (`iter_files`), e este modulo **importa** essa
funcao. Duas reguas para a mesma medida divergem na tarde em que uma delas for
editada — e aqui a divergencia custa recurso faltando no servidor.

Uso
---

    python tools/conferir_atualizacao.py --arvore <pasta que viaja> [--instalado <pasta>]

O `--instalado` sai de `%PROGRAMFILES%\\CartorioGestao` quando nao e informado.
Tambem aceita `--pacote arquivo.cgu`, e ai compara contra o que o pacote levou —
que e como se confere uma atualizacao que veio por outro caminho.

Saida: 0 quando a instalacao tem tudo igual; 1 quando falta ou difere alguma
coisa. **Sobrar** nao muda o codigo de saida: e aviso, e a decisao de apagar e de
quem responde pela serventia.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import criar_atualizacao  # noqa: E402  (o caminho vem de cima, nesta ordem)

# Onde o sistema mora, medido: a instalacao do servidor. Nao se adivinha a partir
# do caminho deste arquivo, porque ele roda tanto na arvore quanto no servidor.
PADRAO_INSTALADO = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "CartorioGestao"


def digest(arquivo: Path) -> str:
    h = hashlib.sha256()
    with arquivo.open("rb") as fh:
        for bloco in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def digests_dos(arquivos: list[tuple[Path, str]]) -> dict[str, str]:
    """Calcula hashes de muitos arquivos sobrepondo a espera de disco."""
    if not arquivos:
        return {}
    with ThreadPoolExecutor(max_workers=min(8, len(arquivos))) as grupo:
        valores = grupo.map(digest, (arquivo for arquivo, _ in arquivos))
        return {rel: valor for (_arquivo, rel), valor in zip(arquivos, valores)}


def da_arvore(arvore: Path) -> dict[str, str]:
    """O que o pacote levaria desta arvore — a regua do empacotador, e nao outra."""
    return digests_dos(criar_atualizacao.todos_os_arquivos(arvore))


def do_pacote(pacote: Path) -> dict[str, str]:
    with zipfile.ZipFile(pacote) as z:
        nomes = z.namelist()
        return {
            nome[len("payload/"):]: hashlib.sha256(z.read(nome)).hexdigest()
            for nome in nomes
            if nome.startswith("payload/") and not nome.endswith("/")
        }


def da_instalacao(instalado: Path) -> dict[str, str]:
    """Os arquivos de programa que estao la — mesma regua de exclusao da arvore.

    Ela e a mesma de proposito: comparar duas pastas com reguas diferentes daria
    uma lista de diferencas que so fala das reguas.
    """
    return digests_dos(list(criar_atualizacao.iter_files(instalado)))


def comparar(esperado: dict[str, str], instalado: dict[str, str]) -> tuple[list, list, list]:
    faltam = sorted(set(esperado) - set(instalado))
    diferem = sorted(k for k in set(esperado) & set(instalado) if esperado[k] != instalado[k])
    sobram = sorted(set(instalado) - set(esperado))
    return faltam, diferem, sobram


def documentos_soltos_na_raiz(instalado: Path) -> list[str]:
    """PDF largado na RAIZ da pasta do programa — ver `EXCLUDE_PDF_NA_RAIZ`.

    O pacote ja nao leva documento da raiz, e por isso a comparacao normal nao
    os enxerga: eles ficam **fora das duas listas** e o silencio pareceria casa
    em ordem. Em 15/09/2026 a raiz da pasta que viaja tinha a previa de uma
    certidao de cliente, salva ali para conferencia e esquecida — `previa_inteiro_teor_daiane.pdf`,
    com o nome de uma pessoa da casa dentro do nome do arquivo.

    Aqui a pergunta e a mesma, do outro lado: o servidor guarda documento que
    nao e programa? Nao importa se o codigo o abre (nao abre): quem copia a
    pasta para pedir ajuda, ou abre o menu Iniciar e ve o nome, esta mostrando
    dado de cliente. **A regra e so para a RAIZ** — dentro de `DOCUMENTACAO`
    os PDFs sao os modelos do RTDPJ, e sao do programa.
    """
    if not criar_atualizacao.EXCLUDE_PDF_NA_RAIZ:
        return []
    return sorted(
        p.relative_to(instalado).as_posix()
        for p in instalado.glob("*.pdf")
        if p.is_file()
    )


def imprimir(rotulo_esperado: str, faltam: list, diferem: list, sobram: list,
             soltos: list | None = None) -> int:
    print(f"Conferindo contra: {rotulo_esperado}")
    print(f"FALTAM {len(faltam)} · DIFEREM {len(diferem)} · SOBRAM {len(sobram)}")
    if faltam:
        print(f"\n--- FALTAM NA INSTALACAO ({len(faltam)}) ---")
        print("    Arquivos que o pacote leva e que nao chegaram. O recurso que os le")
        print("    falha calado, e nenhuma tela avisa.")
        for rel in faltam:
            print("  " + rel)
    if diferem:
        print(f"\n--- DIFEREM ({len(diferem)}) ---")
        print("    Estao la, com o conteudo de uma versao anterior.")
        for rel in diferem:
            print("  " + rel)
    if sobram:
        print(f"\n--- SOBRAM NA INSTALACAO ({len(sobram)}) ---")
        print("    Nao existem mais na arvore. Sao inertes enquanto o codigo nao os")
        print("    chamar, e ficam declarados: apagar e decisao de quem responde pela")
        print("    serventia. Confira antes de mexer na pasta do programa.")
        for rel in sobram:
            print("  " + rel)
    if soltos:
        print(f"\n--- DOCUMENTO SOLTO NA RAIZ DA PASTA ({len(soltos)}) ---")
        print("    Nao e programa e nao viaja no pacote — e o silencio da regra")
        print("    deixaria passar. Se for previa de papel de cliente, apague: quem")
        print("    abre a pasta esta mostrando dado de pessoa da casa.")
        for rel in soltos:
            print("  " + rel)
    if not (faltam or diferem):
        print("\nA instalacao tem tudo o que o pacote leva, igual byte a byte.")
        return 0
    print("\nA instalacao NAO esta igual. Rode o ATUALIZAR_SISTEMA.cmd na pasta SERVIDOR.")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--arvore", type=Path, help="pasta do programa na arvore de desenvolvimento")
    ap.add_argument("--pacote", type=Path, help="arquivo .cgu, para conferir o que ELE levou")
    ap.add_argument("--instalado", type=Path, default=PADRAO_INSTALADO)
    args = ap.parse_args()

    if not args.arvore and not args.pacote:
        ap.error("informe --arvore ou --pacote")
    instalado = args.instalado
    if not instalado.is_dir():
        print(f"ERRO: nao achei a instalacao em {instalado}")
        return 1

    if args.pacote:
        esperado, rotulo = do_pacote(args.pacote), f"o pacote {args.pacote.name}"
    else:
        arvore = args.arvore.resolve()
        if not (arvore / "app.py").is_file():
            # `app.py` e o marcador de "esta pasta e o programa", e nao um arquivo
            # qualquer: sem ele a comparacao inteira diria "faltam 800".
            print(f"ERRO: {arvore} nao tem app.py — nao parece ser a pasta do programa")
            return 1
        esperado, rotulo = da_arvore(arvore), f"a arvore {arvore}"

    faltam, diferem, sobram = comparar(esperado, da_instalacao(instalado))
    print(f"Instalacao: {instalado}")
    return imprimir(rotulo, faltam, diferem, sobram, documentos_soltos_na_raiz(instalado))


if __name__ == "__main__":
    sys.exit(main())
