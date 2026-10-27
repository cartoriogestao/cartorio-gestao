"""O despachante da automação — o que a tarefa única do Agendador chama a cada minuto.

    python tools\\automacao_despachante.py            um tique (o padrão)
    python tools\\automacao_despachante.py --tique    o mesmo

O trabalho mora em `automacao.py` (raiz do programa), e este arquivo só o
chama: assim o caminho que o Agendador conhece fica estável, e o código que
decide viaja no pacote como qualquer outro módulo.

O ambiente é o do servidor: `CARTORIO_GESTAO_DATA`, `CG_PG_DSN` e
`CG_PG_SCHEMA` vêm do lançador que
`tools/gerar_instalador_automacao.py` gera (Windows ou macOS).
Este script não tem caminho nenhum desta máquina escrito dentro.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import automacao  # noqa: E402

if __name__ == "__main__":
    sys.exit(automacao.main(sys.argv[1:] or ["--tique"]))
