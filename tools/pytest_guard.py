"""Guarda uma execucao pytest contra concorrencia e arvore mutante.

Uma suite mede uma versao. Se outra suite disputa os mesmos recursos, ou se o
codigo muda no meio da medicao, o resultado deixa de pertencer a uma versao e
uma falha pode se multiplicar por centenas. Este modulo falha cedo e explica o
motivo, em vez de deixar a execucao produzir um relatorio enganoso.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


IGNORAR_PASTAS = {
    ".git", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__",
    "build", "dist", "dist_unico", "output", "runtime", "tmp", "updates",
}

# Arquivos que alteram o comportamento ou as afirmacoes da suite. Artefatos,
# bancos e logs ficam de fora para que o proprio teste nao invalide a medicao.
EXTENSOES_VIGIADAS = {
    ".cmd", ".css", ".html", ".ini", ".js", ".json", ".md", ".ps1",
    ".py", ".txt", ".xsd",
}


def estado_da_arvore(raiz: Path) -> dict[str, tuple[int, int]]:
    """Retrato barato por nome, tamanho e mtime, com poda antes da varredura.

    ``os.scandir`` já traz os metadados da entrada no mesmo passeio do
    diretório. Evitar ``Path.stat`` e ``relative_to`` para cada arquivo faz
    diferença porque esta função roda periodicamente durante toda a suíte.
    """
    raiz = raiz.resolve()
    estado: dict[str, tuple[int, int]] = {}

    def visitar(base: Path, relativo: str = "") -> None:
        try:
            entradas = os.scandir(base)
        except OSError:
            return
        with entradas:
            for entrada in entradas:
                nome = entrada.name
                rel = f"{relativo}/{nome}" if relativo else nome
                try:
                    if entrada.is_dir(follow_symlinks=False):
                        if nome not in IGNORAR_PASTAS:
                            visitar(Path(entrada.path), rel)
                        continue
                    if not entrada.is_file(follow_symlinks=False):
                        continue
                    if os.path.splitext(nome)[1].lower() not in EXTENSOES_VIGIADAS:
                        continue
                    stat = entrada.stat(follow_symlinks=False)
                    estado[rel.replace("\\", "/")] = (
                        stat.st_size, stat.st_mtime_ns,
                    )
                except OSError:
                    # Sumir durante a leitura é, por si só, uma mudança.
                    estado[rel.replace("\\", "/")] = (-1, -1)

    visitar(raiz)
    return estado


def diferencas(
    antes: dict[str, tuple[int, int]], depois: dict[str, tuple[int, int]],
) -> list[str]:
    return sorted(
        nome for nome in set(antes) | set(depois)
        if antes.get(nome) != depois.get(nome)
    )


def codigo_de_saida(exitstatus: int, arvore_invalidada: bool) -> int:
    """Uma medicao invalidada nunca pode parecer aprovada para o chamador."""
    if arvore_invalidada and exitstatus == 0:
        return 2
    return exitstatus


class TravaDaSuite:
    """Trava nao bloqueante, exclusiva por caminho da arvore."""

    def __init__(self, raiz: Path):
        chave = hashlib.sha256(str(raiz.resolve()).casefold().encode()).hexdigest()[:16]
        self.caminho = Path(tempfile.gettempdir()) / f"cartorio_gestao_pytest_{chave}.lock"
        self._arquivo = None

    def adquirir(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        arquivo = self.caminho.open("a+b")
        arquivo.seek(0, os.SEEK_END)
        if arquivo.tell() == 0:
            arquivo.write(b"0")
            arquivo.flush()
        arquivo.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(arquivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as erro:
            arquivo.close()
            raise RuntimeError(
                "ja existe outra suite pytest executando nesta arvore; "
                "aguarde-a terminar antes de iniciar outra"
            ) from erro
        self._arquivo = arquivo

    def liberar(self) -> None:
        arquivo, self._arquivo = self._arquivo, None
        if arquivo is None:
            return
        try:
            arquivo.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(arquivo.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(arquivo.fileno(), fcntl.LOCK_UN)
        finally:
            arquivo.close()
