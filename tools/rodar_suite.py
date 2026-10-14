"""Executa a suíte com paralelismo conservador e configurável.

O padrão usa metade dos processadores lógicos, limitado a seis trabalhadores:
SQLite e geração de documentos têm bastante espera de disco, mas abrir um
processo por núcleo nesta máquina só aumenta disputa de memória. Para medir
outro valor sem editar os atalhos, defina ``CARTORIO_TEST_WORKERS``.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys


def trabalhadores_padrao(processadores: int | None = None) -> int:
    logicos = processadores if processadores is not None else (os.cpu_count() or 4)
    return min(6, max(2, logicos // 2))


def trabalhadores() -> int:
    informado = os.environ.get("CARTORIO_TEST_WORKERS", "").strip()
    if not informado:
        return trabalhadores_padrao()
    try:
        valor = int(informado)
    except ValueError as erro:
        raise SystemExit(
            "CARTORIO_TEST_WORKERS deve ser um inteiro positivo"
        ) from erro
    if valor < 1:
        raise SystemExit("CARTORIO_TEST_WORKERS deve ser um inteiro positivo")
    return valor


def argumentos_pytest(rapida: bool, extras: list[str]) -> list[str]:
    args: list[str] = []
    if rapida:
        args += ["-m", "not lento"]
    if importlib.util.find_spec("xdist") is not None:
        args += ["-n", str(trabalhadores()), "--dist", "loadfile"]
    else:
        print("AVISO: pytest-xdist ausente; a suíte rodará sem paralelismo.")
    return args + ["--durations=20"] + extras


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--rapida", action="store_true")
    grupo.add_argument("--completa", action="store_true")
    conhecidos, extras = parser.parse_known_args(argv)
    args = argumentos_pytest(conhecidos.rapida, extras)
    if "-n" in args:
        print(f"Suite com {args[args.index('-n') + 1]} trabalhadores paralelos.")
    import pytest
    return int(pytest.main(args))


if __name__ == "__main__":
    raise SystemExit(main())
