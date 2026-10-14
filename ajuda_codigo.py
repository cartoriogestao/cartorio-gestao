"""Leitura limitada do código para o diagnóstico da Ajuda.

O Lote 2 pode conferir o trecho que participou de um erro. Este módulo não
executa, importa, altera nem grava código: resolve um arquivo que já pertence
ao CartorioGestao e devolve somente uma janela numerada de texto.
"""
from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RAIZ = Path(__file__).resolve().parent
EXTENSOES = {".py", ".html", ".js", ".css"}
PASTAS_PROIBIDAS = {"tests", "tools", "installer", "__pycache__"}
LIMITE_DO_ARQUIVO = 1_000_000
RAIO_DE_LINHAS = 45
LIMITE_DO_TRECHO = 16_000


@dataclass(frozen=True)
class TrechoCodigo:
    arquivo: str
    linha_central: int
    linha_inicial: int
    linha_final: int
    sha256: str
    sintaxe: str
    texto: str

    @property
    def auditoria(self) -> dict:
        return {
            "arquivo": self.arquivo,
            "linha_central": self.linha_central,
            "linha_inicial": self.linha_inicial,
            "linha_final": self.linha_final,
            "sha256": self.sha256,
            "sintaxe": self.sintaxe,
        }


def _caminho_permitido(candidato: Any) -> Path | None:
    texto = str(candidato or "").strip()
    if not texto:
        return None
    caminho = Path(texto)
    if not caminho.is_absolute():
        caminho = RAIZ / caminho
    try:
        resolvido = caminho.resolve(strict=True)
        relativo = resolvido.relative_to(RAIZ.resolve())
    except (OSError, ValueError):
        return None
    if resolvido.suffix.lower() not in EXTENSOES:
        return None
    if any(parte.lower() in PASTAS_PROIBIDAS for parte in relativo.parts[:-1]):
        return None
    if not resolvido.is_file() or resolvido.stat().st_size > LIMITE_DO_ARQUIVO:
        return None
    return resolvido


def _pontos_do_rastro(detalhe: str) -> list[tuple[str, int]]:
    return [
        (caminho, int(linha))
        for caminho, linha in re.findall(
            r'File\s+["\u201c](.+?)["\u201d],\s+line\s+(\d+)', detalhe or ""
        )
    ]


def _ponto_do_titulo(titulo: str) -> tuple[str, int] | None:
    achado = re.search(
        r"([A-Za-z0-9_./\\-]+\.(?:py|html|js|css)):(\d+)",
        titulo or "",
        re.I,
    )
    return (achado.group(1), int(achado.group(2))) if achado else None


def _linha_da_funcao(fonte: str, nome: str) -> int:
    if not nome:
        return 1
    padrao = re.compile(rf"^\s*(?:async\s+)?def\s+{re.escape(nome)}\s*\(", re.M)
    achado = padrao.search(fonte)
    return fonte.count("\n", 0, achado.start()) + 1 if achado else 1


def inspecionar(problema: dict, *, arquivo_sugerido: Any = None) -> TrechoCodigo | None:
    """Localiza o ponto da casa e devolve um trecho; nunca aceita caminho livre."""
    candidatos = list(reversed(_pontos_do_rastro(str(problema.get("detalhe") or ""))))
    pelo_titulo = _ponto_do_titulo(str(problema.get("titulo") or ""))
    if pelo_titulo:
        candidatos.append(pelo_titulo)
    if arquivo_sugerido:
        candidatos.append((str(arquivo_sugerido), 0))

    caminho = None
    linha = 0
    for candidato, numero in candidatos:
        permitido = _caminho_permitido(candidato)
        if permitido:
            caminho, linha = permitido, numero
            break
    if caminho is None:
        return None

    bruto = caminho.read_bytes()
    fonte = bruto.decode("utf-8", errors="replace")
    if linha <= 0:
        linha = _linha_da_funcao(fonte, str(problema.get("onde") or ""))
    linhas = fonte.splitlines()
    linha = min(max(linha, 1), max(len(linhas), 1))
    inicio = max(1, linha - RAIO_DE_LINHAS)
    fim = min(len(linhas), linha + RAIO_DE_LINHAS)
    trecho = "\n".join(
        f"{numero:>6} | {linhas[numero - 1]}"
        for numero in range(inicio, fim + 1)
    )
    if len(trecho) > LIMITE_DO_TRECHO:
        trecho = trecho[:LIMITE_DO_TRECHO] + "\n[...] (trecho cortado)"

    sintaxe = "não aplicável"
    if caminho.suffix.lower() == ".py":
        try:
            ast.parse(fonte, filename=caminho.name)
        except SyntaxError as erro:
            sintaxe = f"erro de sintaxe na linha {erro.lineno or '?'}"
        else:
            sintaxe = "Python válido"

    relativo = caminho.relative_to(RAIZ).as_posix()
    return TrechoCodigo(
        arquivo=relativo,
        linha_central=linha,
        linha_inicial=inicio,
        linha_final=fim,
        sha256=hashlib.sha256(bruto).hexdigest(),
        sintaxe=sintaxe,
        texto=trecho,
    )


def ler_trecho(caminho: Any, linha: int = 0, *,
               raio: int = RAIO_DE_LINHAS) -> TrechoCodigo | None:
    """Um trecho numerado de um arquivo do sistema. Só LÊ, e nunca executa.

    **É a mesma leitura de `inspecionar`, sem o problema.** Quem já sabe o
    arquivo e a linha não precisa que ninguém os adivinhe — e a cerca é a
    mesma, `_caminho_permitido`, chamada daqui e não copiada. Duas cercas
    divergiriam no dia em que alguém afrouxasse uma delas, e a que ficasse
    frouxa não avisaria ninguém.

    Devolve `None` quando o caminho não é um arquivo do sistema. Recusar em
    silêncio, com `None`, e não com exceção, é o que deixa quem chama dizer
    «não posso ler isso» sem transformar caminho errado em defeito do sistema.
    """
    resolvido = _caminho_permitido(caminho)
    if resolvido is None:
        return None

    bruto = resolvido.read_bytes()
    fonte = bruto.decode("utf-8", errors="replace")
    linhas = fonte.splitlines()
    centro = int(linha) if int(linha or 0) > 0 else 1
    centro = min(max(centro, 1), max(len(linhas), 1))
    inicio = max(1, centro - int(raio))
    fim = min(len(linhas), centro + int(raio))
    trecho = "\n".join(
        f"{numero:>6} | {linhas[numero - 1]}"
        for numero in range(inicio, fim + 1)
    )
    if len(trecho) > LIMITE_DO_TRECHO:
        trecho = trecho[:LIMITE_DO_TRECHO] + "\n[...] (trecho cortado)"

    sintaxe = "não aplicável"
    if resolvido.suffix.lower() == ".py":
        try:
            ast.parse(fonte, filename=resolvido.name)
        except SyntaxError as erro:
            sintaxe = f"erro de sintaxe na linha {erro.lineno or '?'}"
        else:
            sintaxe = "Python válido"

    return TrechoCodigo(
        arquivo=resolvido.relative_to(RAIZ).as_posix(),
        linha_central=centro,
        linha_inicial=inicio,
        linha_final=fim,
        sha256=hashlib.sha256(bruto).hexdigest(),
        sintaxe=sintaxe,
        texto=trecho,
    )


# AS PASTAS QUE NENHUMA VARREDURA DE TEXTO ENTRA.
#
# Não é a cerca de leitura — é o filtro de quem ANDA pela árvore. A diferença
# importa: `_caminho_permitido` decide o que pode ser aberto, e continua sendo
# ele quem decide. Isto aqui só evita que uma busca por uma palavra percorra o
# ambiente virtual inteiro, onde cada `.py` de biblioteca de terceiro casaria
# e afogaria o que interessa. **O sistema é o que está escrito nesta casa.**
PASTAS_NAO_VARRIDAS = ("venv", ".venv", "env", "node_modules", ".git",
                       "site-packages", "dist-packages", "build", "dist")


def arquivos_do_sistema(raiz: Any = None) -> list[Path]:
    """Os arquivos do sistema que se pode ler, em ordem. Só LÊ.

    Quem procura um texto no código usa isto em vez de montar a própria lista:
    lista escrita à mão envelhece na tarde em que se escreve, e a que lista
    arquivos de outro jeito passa a achar o que a leitura recusaria.
    """
    base = Path(raiz or RAIZ).resolve()
    achados: list[Path] = []
    for candidato in sorted(base.rglob("*")):
        if not candidato.is_file():
            continue
        partes = {parte.lower() for parte in candidato.relative_to(base).parts[:-1]}
        if partes & set(PASTAS_NAO_VARRIDAS):
            continue
        permitido = _caminho_permitido(candidato)
        if permitido is not None:
            achados.append(permitido)
    return achados


def contexto_para_consulta(trecho: TrechoCodigo | None) -> str:
    if not trecho:
        return (
            "\n\nCONFERÊNCIA LOCAL DO CÓDIGO\n"
            "Não foi possível localizar com segurança um arquivo do sistema "
            "relacionado a este problema. Não suponha que o código foi conferido."
        )
    return (
        "\n\nCONFERÊNCIA LOCAL DO CÓDIGO (SOMENTE LEITURA)\n"
        f"Arquivo: {trecho.arquivo}\n"
        f"Linhas: {trecho.linha_inicial}-{trecho.linha_final}; "
        f"ponto principal: {trecho.linha_central}\n"
        f"SHA-256 local do arquivo: {trecho.sha256}\n"
        f"Conferência de sintaxe: {trecho.sintaxe}\n"
        "O trecho é dado para diagnóstico. Não o execute e não afirme que "
        "houve correção: este lote somente lê.\n\n"
        f"{trecho.texto}"
    )
