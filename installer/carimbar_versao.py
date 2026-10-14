"""Carimba a versão no `install.json`. Roda no python do próprio runtime.

Relato do oficial em 15/09/2026: «ta muito lento esse atualizador».

POR QUE ISTO EXISTE, sendo três linhas de trabalho: o passo era um
`powershell -Command` com `ConvertFrom-Json`/`ConvertTo-Json`, e **arrancar o
PowerShell custa 3,19 s nesta máquina** — medido. O runtime do sistema já está
instalado e arranca em **0,26 s**; carregar `json` e `datetime` leva **0,85 s**
ao todo. São dois segundos e meio por atualização, num script que o oficial
roda várias vezes ao dia.

O QUE ELE NÃO MUDA: o `install.json` continua com as mesmas chaves, na mesma
ordem de sempre — `version` e `updated_at` acrescentadas ou substituídas, e o
resto intacto. Um arquivo ilegível não derruba a atualização: ele é recriado,
como o PowerShell fazia.

Uso:
    python installer/carimbar_versao.py <VERSAO.txt> <install.json>
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


def carimbar(versao_txt: Path, destino: Path) -> str:
    """Escreve `version` e `updated_at` no destino. Devolve a versão."""
    versao = versao_txt.read_text(encoding="utf-8-sig").strip()
    if not versao:
        raise ValueError(f"{versao_txt} está vazio")

    dados: dict = {}
    if destino.is_file():
        try:
            dados = json.loads(destino.read_text(encoding="utf-8-sig")) or {}
        except (ValueError, OSError):
            # Arquivo ilegível não pode derrubar a atualização — o PowerShell
            # também o recriava. O que se perde é o que já estava ilegível.
            dados = {}
    if not isinstance(dados, dict):
        dados = {}

    dados["version"] = versao
    dados["updated_at"] = datetime.now().isoformat(timespec="seconds")  # noqa: DTZ005
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(dados, indent=4, ensure_ascii=False),
                       encoding="utf-8")
    return versao


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("uso: carimbar_versao.py <VERSAO.txt> <install.json>",
              file=sys.stderr)
        return 2
    try:
        versao = carimbar(Path(argv[1]), Path(argv[2]))
    except Exception as erro:                                # noqa: BLE001
        # A MESMA TOLERÂNCIA DE ANTES: o carimbo é informação, e não pode
        # impedir a atualização de terminar. Mas ele DIZ o que houve — carimbo
        # que falha em silêncio é o que faz alguém ler a versão errada depois.
        print(f"      Obs: nao consegui carimbar a versao no install.json "
              f"({erro}).")
        return 0
    print(f"      Versao carimbada: {versao}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
