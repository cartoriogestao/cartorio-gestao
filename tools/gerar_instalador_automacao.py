"""Gera os instaladores da automação — Agendador do Windows e launchd do macOS. NÃO REGISTRA NADA.

    python tools/gerar_instalador_automacao.py                    os dois sistemas
    python tools/gerar_instalador_automacao.py --sistema windows  só o Windows

O trabalho mora em `automacao_agendador.py`. Os arquivos saem em
`<dados>/automacao_instalador/<sistema>/`.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import automacao_agendador  # noqa: E402

if __name__ == "__main__":
    sys.exit(automacao_agendador.main(sys.argv[1:]))
