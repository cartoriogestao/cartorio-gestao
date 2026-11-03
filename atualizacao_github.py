"""A versão nova no GitHub: avisar, e baixar o pacote para a tela de atualizações. SÓ LÊ A REDE.

Pedido do oficial, 02/11/2026: «uma notificação que avisa quando sai nova versão no github», «dentro do
sistema», com «um botão facilitado para puxar a atualização e atualizar de dentro do sistema» — «simples e
segura, sem ter que selecionar cgu no computador, nem colocar sha e hash», «apenas com a senha do oficial».

O QUE VEM DO GITHUB E O QUE NÃO VEM
    Cada versão publicada é uma «Release» do repositório, com a etiqueta `vX.Y.Z` e dois arquivos: o pacote
    `.cgu` e o `.cgu.sha256` ao lado (`tools/publicar_versao.py`). Daqui sai só isso: a versão, o pacote e o
    SHA-256. **Quem garante que o pacote é da serventia não é o GitHub, é a assinatura**: o pacote segue
    para `update_manager.validate_and_stage`, que confere a assinatura contra a chave cadastrada nesta
    instalação e recusa o que ela não fechar — mesmo que alguém mexesse na página do GitHub.

SEM REDE, SEM AVISO
    A consulta tem prazo curto e nunca derruba nada: falhou, o aviso só não aparece, e a tela diz quando foi
    a última consulta que deu certo. A resposta fica guardada em `updates/github.json`, e o aviso lê dali —
    nenhuma tela espera a rede.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

REPOSITORIO = "cartoriogestao/cartorio-gestao"
API = "https://api.github.com/repos/{repo}/releases/latest"
PRAZO_DA_REDE_S = 15
#: De quanto em quanto tempo o servidor pergunta sozinho.
INTERVALO_S = 24 * 60 * 60
#: O endereço de baixar redireciona para o depósito de arquivos do GitHub; nada fora daqui se baixa.
HOSTS_PERMITIDOS = frozenset({"api.github.com", "github.com", "objects.githubusercontent.com",
                              "release-assets.githubusercontent.com"})
NOME_DO_GUARDADO = "github.json"
_ETIQUETA = re.compile(r"^v?(\d+(?:\.\d+){1,3})$")
_SHA = re.compile(r"\b([0-9a-f]{64})\b")


class GitHubIndisponivel(RuntimeError):
    """A consulta ou o download não deram certo. A frase vai para a tela."""


def versao_em_tupla(versao: str) -> tuple[int, ...]:
    m = _ETIQUETA.match(str(versao or "").strip())
    if not m:
        raise ValueError(f"versão fora do formato: {versao!r}")
    return tuple(int(x) for x in m.group(1).split("."))


def e_mais_nova(publicada: str, instalada: str) -> bool:
    try:
        return versao_em_tupla(publicada) > versao_em_tupla(instalada)
    except ValueError:
        return False


def _conferir_endereco(url: str) -> str:
    partes = urlsplit(url)
    if partes.scheme != "https" or (partes.hostname or "").lower() not in HOSTS_PERMITIDOS:
        raise GitHubIndisponivel(f"Endereço fora do GitHub recusado: {partes.hostname or url!r}.")
    return url


def _abrir(url: str, abrir: Callable | None = None):
    pedido = urllib.request.Request(_conferir_endereco(url), headers={
        "Accept": "application/vnd.github+json", "User-Agent": "CartorioGestao-atualizador"})
    return (abrir or urllib.request.urlopen)(pedido, timeout=PRAZO_DA_REDE_S)


def ler_release(dados: dict) -> dict[str, Any]:
    """Da resposta da API, o que importa: a versão, o pacote e o arquivo do SHA. Só calcula."""
    m = _ETIQUETA.match(str(dados.get("tag_name") or ""))
    if not m:
        raise GitHubIndisponivel("A versão publicada não tem etiqueta no formato vX.Y.Z.")
    arquivos = {str(a.get("name") or ""): a for a in dados.get("assets") or []}
    pacote = next((a for n, a in arquivos.items() if n.lower().endswith(".cgu")), None)
    sha = next((a for n, a in arquivos.items() if n.lower().endswith(".cgu.sha256")), None)
    return {
        "versao": m.group(1),
        "nome": str(dados.get("name") or dados.get("tag_name") or ""),
        "publicada_em": str(dados.get("published_at") or ""),
        "pagina": str(dados.get("html_url") or ""),
        "notas": str(dados.get("body") or "")[:4000],
        "pacote_nome": pacote["name"] if pacote else "",
        "pacote_url": pacote.get("browser_download_url", "") if pacote else "",
        "pacote_bytes": int(pacote.get("size") or 0) if pacote else 0,
        "sha_url": sha.get("browser_download_url", "") if sha else "",
    }


def consultar(repositorio: str = REPOSITORIO, *, abrir: Callable | None = None) -> dict[str, Any]:
    """A última versão publicada. Levanta `GitHubIndisponivel` com a frase do motivo."""
    try:
        with _abrir(API.format(repo=repositorio), abrir) as resposta:
            return ler_release(json.loads(resposta.read(2_000_000).decode("utf-8")))
    except GitHubIndisponivel:
        raise
    except Exception as exc:                                   # noqa: BLE001 — a rede falha de mil jeitos
        raise GitHubIndisponivel(f"Não foi possível consultar o GitHub: {exc}") from exc


# ------------------------------------------------------------------ o guardado

def guardado(pasta_updates: Path) -> dict[str, Any]:
    try:
        return json.loads((Path(pasta_updates) / NOME_DO_GUARDADO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def atualizar_guardado(pasta_updates: Path, repositorio: str = REPOSITORIO, *,
                       abrir: Callable | None = None) -> dict[str, Any]:
    """Consulta e guarda. Falha também se guarda (com a última resposta boa intacta)."""
    pasta = Path(pasta_updates)
    pasta.mkdir(parents=True, exist_ok=True)
    antes = guardado(pasta)
    agora = datetime.now().isoformat(timespec="seconds")
    try:
        novo = {**antes, "release": consultar(repositorio, abrir=abrir), "consultado_em": agora, "erro": ""}
    except GitHubIndisponivel as exc:
        novo = {**antes, "tentado_em": agora, "erro": str(exc)}
    (pasta / NOME_DO_GUARDADO).write_text(json.dumps(novo, ensure_ascii=False, indent=2), encoding="utf-8")
    return novo


def versao_nova(pasta_updates: Path, instalada: str) -> dict[str, Any] | None:
    """O aviso: a versão publicada, quando ela é mais nova que a instalada e tem pacote. Só LÊ o guardado."""
    release = guardado(pasta_updates).get("release") or {}
    if release.get("pacote_url") and e_mais_nova(release.get("versao", ""), instalada):
        return release
    return None


# ------------------------------------------------------------------ baixar

def baixar(release: dict, pasta_destino: Path, *, limite_bytes: int,
           abrir: Callable | None = None) -> tuple[Path, str]:
    """Baixa o pacote e o SHA publicado ao lado. Devolve (arquivo, SHA esperado).

    O SHA do GitHub é só a integridade do download; a autoria quem prova é a assinatura, adiante."""
    if not release.get("pacote_url") or not release.get("sha_url"):
        raise GitHubIndisponivel("A versão publicada não tem o pacote .cgu e o .cgu.sha256 ao lado.")
    try:
        with _abrir(release["sha_url"], abrir) as resposta:
            achado = _SHA.search(resposta.read(4096).decode("utf-8", "replace").lower())
    except GitHubIndisponivel:
        raise
    except Exception as exc:                                   # noqa: BLE001
        raise GitHubIndisponivel(f"Não foi possível baixar o SHA-256: {exc}") from exc
    if not achado:
        raise GitHubIndisponivel("O arquivo .sha256 publicado não traz um SHA-256.")
    pasta = Path(pasta_destino)
    pasta.mkdir(parents=True, exist_ok=True)
    nome = re.sub(r"[^A-Za-z0-9._-]", "_", release.get("pacote_nome") or "pacote.cgu")
    destino = pasta / f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_github_{nome}"
    soma, total = hashlib.sha256(), 0
    try:
        with _abrir(release["pacote_url"], abrir) as resposta, destino.open("wb") as saida:
            _conferir_endereco(getattr(resposta, "url", None) or release["pacote_url"])
            while True:
                bloco = resposta.read(1024 * 1024)
                if not bloco:
                    break
                total += len(bloco)
                if total > limite_bytes:
                    raise GitHubIndisponivel(
                        f"O pacote passou do limite de {limite_bytes // 1024 // 1024} MB.")
                soma.update(bloco)
                saida.write(bloco)
    except GitHubIndisponivel:
        destino.unlink(missing_ok=True)
        raise
    except Exception as exc:                                   # noqa: BLE001
        destino.unlink(missing_ok=True)
        raise GitHubIndisponivel(f"Não foi possível baixar o pacote: {exc}") from exc
    if soma.hexdigest() != achado.group(1):
        destino.unlink(missing_ok=True)
        raise GitHubIndisponivel("O pacote baixado não confere com o SHA-256 publicado.")
    return destino, achado.group(1)


# ------------------------------------------------------------------ o vigia

_linha: list[threading.Thread] = []


def iniciar_vigia(pasta_updates: Path, repositorio: str = REPOSITORIO) -> bool:
    """Pergunta ao GitHub ao subir o servidor e depois uma vez por dia. Uma linha só por processo."""
    if any(t.is_alive() for t in _linha):
        return False

    def laco():
        while True:
            try:
                atualizar_guardado(pasta_updates, repositorio)
            except Exception:                                  # noqa: BLE001 — o vigia não cai
                pass
            time.sleep(INTERVALO_S)

    _linha[:] = [threading.Thread(target=laco, name="atualizacao-github", daemon=True)]
    _linha[0].start()
    return True
