from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path
from typing import BinaryIO


def safe_component(value: str, fallback: str = "Sem_classificacao") -> str:
    value = (value or "").strip()
    if not value:
        return fallback
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    value = value.rstrip(". ")
    return value[:120] or fallback


def nome_simples(nome) -> bool:
    """O nome é SÓ de arquivo — sem pasta, sem unidade, sem `..`. Só calcula.

    POR QUE EXISTE (LS02, 19/10/2026)
        Há tela que grava o nome do arquivo digitado no formulário e, depois,
        o junta a uma pasta do acervo (`pasta / nome`) para copiar ou servir.
        No Windows, um nome com `..\\` sobe de pasta, e um nome com `C:\\` faz
        o `/` do `pathlib` JOGAR FORA a pasta da esquerda: a cópia, que roda
        como SYSTEM, iria para onde o nome mandasse.

    As duas barras são recusadas em qualquer sistema — o servidor é Windows,
    e o teste roda no Mac; a regra tem de ser a mesma nos dois. O `:` também:
    no Windows ele é unidade (`C:x`) ou fluxo alternativo (`x.tif:y`).
    """
    texto = str(nome or "")
    if not texto.strip() or texto.strip() in (".", ".."):
        return False
    return not any(c in texto for c in ("/", "\\", ":", "\x00"))


def unique_path(folder: Path, filename: str) -> Path:
    filename = safe_component(filename, "arquivo")
    candidate = folder / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    n = 2
    while True:
        candidate = folder / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def save_upload(file_storage, target_folder: Path) -> dict:
    target_folder.mkdir(parents=True, exist_ok=True)
    original = Path(file_storage.filename or "arquivo").name
    path = unique_path(target_folder, original)
    file_storage.save(path)
    return {
        "original_name": original,
        "stored_name": path.name,
        "stored_path": str(path.resolve()),
        "sha256": hash_file(path),
        "size_bytes": path.stat().st_size,
    }


def copy_existing(source: Path, target_folder: Path) -> dict:
    target_folder.mkdir(parents=True, exist_ok=True)
    path = unique_path(target_folder, source.name)
    shutil.copy2(source, path)
    return {
        "original_name": source.name,
        "stored_name": path.name,
        "stored_path": str(path.resolve()),
        "sha256": hash_file(path),
        "size_bytes": path.stat().st_size,
    }
