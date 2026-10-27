"""O guardião do cofre da automação — iniciado no logon, guarda a chave só em memória.

    python tools/automacao_guardiao.py              com a janelinha da senha
    python tools/automacao_guardiao.py --sem-janela sem janela (desbloqueio pela tela local)

O trabalho mora em `automacao_guardiao.py` (raiz do programa). O ambiente
(`CARTORIO_GESTAO_DATA`, `CG_COFRE_AUTOMACAO`) vem do lançador gerado por
`tools/gerar_instalador_automacao.py`.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import automacao_guardiao  # noqa: E402

if __name__ == "__main__":
    sys.exit(automacao_guardiao.main(sys.argv[1:]))
