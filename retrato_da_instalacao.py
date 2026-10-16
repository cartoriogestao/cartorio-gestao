"""O retrato da instalação: o que foi instalado por atualização, arquivo a arquivo.

PARA QUE SERVE — 14/10/2026, ordem do oficial («pode construir»)
    A produção era mudada por três caminhos: o pacote `.cgu` (conferido, com
    backup e volta automática), o `ATUALIZAR_SISTEMA.cmd` (agora só para
    emergência) e a CÓPIA DIRETA de arquivos em `Program Files` pelos agentes —
    41 hotfixes assim até 09/10, e mais cinco em 13/10, depois da trava nova.
    A cópia direta tinha dois defeitos: ninguém via, e o pacote seguinte a
    SOBRESCREVIA calado se o conserto não tivesse sido espelhado no INSTALAR.

    O retrato guarda o SHA-256 de cada arquivo que a última atualização
    instalou. Com ele:
      1. a CONFERÊNCIA (diária, e na tela de Atualizações) diz quais arquivos
         da instalação mudaram fora de uma atualização;
      2. a INSPEÇÃO de um pacote novo BLOQUEIA quando ele sobrescreveria um
         arquivo mudado por fora que o pacote não traz igual — o conserto da
         produção que não chegou ao INSTALAR se perderia.

DE ONDE VEM O RETRATO
    - do PACOTE aplicado: a lista conferida (`checked_files`) da preparação que
      o aplicador marcou `APPLIED` para a versão que está rodando;
    - da EMERGÊNCIA: o `ATUALIZAR_SISTEMA.cmd` mede a instalação depois de
      copiar e anota o commit — e o que mudou nela vira PENDÊNCIA DE
      ESPELHAMENTO, até o SANDBOX ter o mesmo arquivo;
    - da MEDIÇÃO: na primeira vez, sem pacote nem emergência que expliquem a
      versão, mede-se o que está instalado (e o retrato diz que foi assim).
    - do OFICIAL: `aceitar` mede de novo e assume o estado atual como base —
      é o jeito de dizer «sei o que mudou por fora; pode sobrescrever».

O QUE ELE NÃO FAZ: não impede a cópia direta (quem tem permissão na pasta
copia); torna-a visível e impede que o pacote seguinte a apague calado.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

NOME = "retrato_da_instalacao.json"
PENDENCIAS = "pendencias_de_espelhamento.json"
# O que se confere: o que é programa. Dados, caches e sobras ficam de fora pela
# mesma lista que a cópia da atualização usa — uma régua só.
EXTENSOES = {".py", ".html", ".js", ".css", ".ps1", ".cmd", ".txt", ".json",
             ".odt", ".xsd", ".jpg", ".png", ".svg", ".ico", ".md"}


def _ignoradas() -> set[str]:
    import update_manager
    return {p.casefold() for p in update_manager.PASTAS_IGNORADAS_NA_COPIA}


def _conta(rel: str, ignoradas: set[str]) -> bool:
    """Se este caminho entra na conferência — a mesma régua de `medir`."""
    partes = rel.split("/")
    return (Path(rel).suffix.lower() in EXTENSOES
            and not any(p.casefold() in ignoradas or p.startswith(".")
                        for p in partes[:-1]))


def _sha(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


# O CACHE DA MEDIÇÃO — medido em 14/10/2026: ler os 1.834 arquivos de
# `Program Files` levou 280 s (o antivírus lê cada um). Guarda-se tamanho e
# data de cada arquivo com o SHA-256; só se lê de novo o que mudou de tamanho
# ou de data — e a cópia direta, que é o que se quer pegar, muda os dois.
CACHE = "retrato_cache.json"


def medir(install_dir: Path, updates_root: Path | None = None) -> dict[str, str]:
    """SHA-256 de cada arquivo de programa da instalação, por caminho relativo."""
    install_dir = Path(install_dir)
    ignoradas = _ignoradas()
    cache_path = Path(updates_root) / CACHE if updates_root else None
    cache: dict = {}
    if cache_path and cache_path.is_file():
        try:
            dados = json.loads(cache_path.read_text(encoding="utf-8"))
            if dados.get("raiz") == str(install_dir.resolve()):
                cache = dados.get("arquivos") or {}
        except (OSError, json.JSONDecodeError):
            cache = {}
    novo_cache: dict = {}
    saida: dict[str, str] = {}
    for raiz, pastas, arquivos in os.walk(install_dir):
        pastas[:] = [p for p in pastas if p.casefold() not in ignoradas
                     and not p.startswith(".")]
        for nome in arquivos:
            p = Path(raiz) / nome
            if p.suffix.lower() not in EXTENSOES:
                continue
            rel = p.relative_to(install_dir).as_posix()
            st = p.stat()
            visto = cache.get(rel)
            if visto and visto[0] == st.st_size and visto[1] == st.st_mtime_ns:
                sha = visto[2]
            else:
                sha = _sha(p)
            novo_cache[rel] = [st.st_size, st.st_mtime_ns, sha]
            saida[rel] = sha
    if cache_path:
        _gravar(cache_path, {"raiz": str(install_dir.resolve()), "arquivos": novo_cache})
    return saida


def _gravar(caminho: Path, dados: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, caminho)


def ler(updates_root: Path) -> dict | None:
    p = Path(updates_root) / NOME
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _do_pacote_aplicado(updates_root: Path, versao: str) -> dict | None:
    meta_path = Path(updates_root) / "staged" / versao / "_update_meta.json"
    if not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if meta.get("state") != "APPLIED":
        return None
    return {
        "versao": versao, "origem": "PACOTE",
        "commit": str((meta.get("manifest") or {}).get("source_commit") or ""),
        "pacote_sha256": str(meta.get("package_sha256") or ""),
        "assinatura": (meta.get("assinatura") or {}).get("situacao", ""),
        "arquivos": {i["path"]: i["sha256"] for i in meta.get("checked_files", [])
                     if i.get("path") and i.get("sha256")},
        "gravado_em": datetime.now().isoformat(timespec="seconds"),
    }


def vigente(updates_root: Path, install_dir: Path, versao: str) -> dict:
    """O retrato da versão que está rodando — gravado na primeira vez que se pede.

    Idempotente: se já há retrato desta versão, devolve-o como está. Senão,
    usa o pacote APPLIED desta versão; e, na falta dele, mede a instalação.
    """
    atual = ler(updates_root)
    if atual and atual.get("versao") == versao:
        return atual
    novo = _do_pacote_aplicado(updates_root, versao)
    if novo is None:
        novo = {"versao": versao, "origem": "MEDIDO",
                "observacao": "medido na instalação: nenhum pacote aplicado "
                              "explica esta versão (primeira conferência, ou "
                              "versão posta por emergência ou cópia)",
                "arquivos": medir(install_dir, updates_root),
                "gravado_em": datetime.now().isoformat(timespec="seconds")}
    _gravar(Path(updates_root) / NOME, novo)
    return novo


def conferir(updates_root: Path, install_dir: Path, versao: str) -> dict:
    """O que mudou na instalação fora de uma atualização."""
    retrato = vigente(updates_root, install_dir, versao)
    ignoradas = _ignoradas()
    # O retrato do pacote lista tudo o que o pacote trouxe; compara-se só o que
    # a medição também olha — senão o que ela não mede pareceria «sumido».
    base = {r: s for r, s in (retrato.get("arquivos") or {}).items()
            if _conta(r, ignoradas)}
    agora = medir(install_dir, updates_root)
    alterados = sorted(r for r, s in base.items() if r in agora and agora[r] != s)
    sumidos = sorted(r for r in base if r not in agora)
    novos = sorted(r for r in agora if r not in base)
    resultado = {"versao": versao, "origem": retrato.get("origem"),
                 "commit": retrato.get("commit", ""),
                 "retrato_gravado_em": retrato.get("gravado_em"),
                 "conferido_em": datetime.now().isoformat(timespec="seconds"),
                 "alterados": alterados, "sumidos": sumidos, "novos": novos,
                 "limpo": not (alterados or sumidos or novos),
                 "pendencias": pendencias(updates_root)}
    # A tela lê o último resultado, sem medir de novo a cada vez que abre.
    _gravar(Path(updates_root) / ULTIMA, resultado)
    return resultado


ULTIMA = "ultima_conferencia_da_instalacao.json"


def ultima_conferencia(updates_root: Path) -> dict | None:
    p = Path(updates_root) / ULTIMA
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def conflitos_do_pacote(updates_root: Path, install_dir: Path, versao: str,
                        arquivos_do_pacote: dict[str, str]) -> list[dict]:
    """Arquivos que o pacote sobrescreveria e que mudaram por fora na produção.

    Conflito = o arquivo instalado difere do retrato (alguém o mudou depois da
    última atualização) E o pacote traz uma versão diferente da instalada.
    Se o pacote traz exatamente o que está instalado, o conserto chegou ao
    INSTALAR — não há o que perder.
    """
    retrato = vigente(updates_root, install_dir, versao)
    base = retrato.get("arquivos") or {}
    agora = medir(install_dir, updates_root)
    conflitos = []
    for rel, sha_novo in arquivos_do_pacote.items():
        sha_instalado = agora.get(rel)
        if sha_instalado is None or rel not in base:
            continue
        if sha_instalado != base[rel] and sha_instalado != sha_novo:
            conflitos.append({"path": rel, "instalado": sha_instalado,
                              "retrato": base[rel], "pacote": sha_novo})
    return conflitos


def aceitar(updates_root: Path, install_dir: Path, versao: str, *, por: str,
            motivo: str) -> dict:
    """O oficial assume o estado instalado como base. Exige motivo escrito."""
    if len((motivo or "").strip()) < 10:
        raise ValueError("Diga em pelo menos dez letras por que o estado atual "
                         "da instalação deve virar a base.")
    novo = {"versao": versao, "origem": "ACEITO",
            "aceito_por": por, "motivo": motivo.strip(),
            "arquivos": medir(install_dir, updates_root),
            "gravado_em": datetime.now().isoformat(timespec="seconds")}
    _gravar(Path(updates_root) / NOME, novo)
    return novo


def registrar_emergencia(updates_root: Path, install_dir: Path, versao: str,
                         commit: str, sandbox: Path | None = None) -> dict:
    """Depois do `ATUALIZAR_SISTEMA.cmd`: novo retrato e as pendências de espelhar.

    O que mudou em relação ao retrato anterior entrou pela emergência; enquanto
    o SANDBOX não tiver o mesmo arquivo, a próxima promoção do SANDBOX para o
    INSTALAR apagaria o conserto. Cada um vira pendência até conferir igual.
    """
    anterior = (ler(updates_root) or {}).get("arquivos") or {}
    agora = medir(install_dir, updates_root)
    mudados = sorted(r for r, s in agora.items() if anterior.get(r) != s)
    _gravar(Path(updates_root) / NOME, {
        "versao": versao, "origem": "EMERGENCIA", "commit": commit,
        "arquivos": agora, "gravado_em": datetime.now().isoformat(timespec="seconds")})
    lista = pendencias(updates_root)
    ja = {p["path"] for p in lista}
    for rel in mudados:
        if rel not in ja:
            lista.append({"path": rel, "sha256": agora[rel], "commit": commit,
                          "desde": datetime.now().isoformat(timespec="seconds")})
    if sandbox is not None:
        lista = [p for p in lista if not _igual_no_sandbox(sandbox, p)]
    _gravar(Path(updates_root) / PENDENCIAS, {"pendencias": lista})
    return {"mudados": mudados, "pendencias": lista}


def _igual_no_sandbox(sandbox: Path, pendencia: dict) -> bool:
    p = Path(sandbox) / pendencia["path"]
    return p.is_file() and _sha(p) == pendencia["sha256"]


def pendencias(updates_root: Path, sandbox: Path | None = None) -> list[dict]:
    """As pendências de espelhamento abertas (as já espelhadas saem sozinhas)."""
    p = Path(updates_root) / PENDENCIAS
    if not p.is_file():
        return []
    try:
        lista = json.loads(p.read_text(encoding="utf-8")).get("pendencias") or []
    except (OSError, json.JSONDecodeError):
        return []
    if sandbox is not None:
        restantes = [x for x in lista if not _igual_no_sandbox(sandbox, x)]
        if len(restantes) != len(lista):
            _gravar(p, {"pendencias": restantes})
        lista = restantes
    return lista
