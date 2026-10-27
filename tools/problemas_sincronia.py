"""LEVA OS PROBLEMAS AO DESENVOLVIMENTO, MASCARADOS — e classifica onde cada um
se reproduz.

    python tools/problemas_sincronia.py exportar --pasta <pasta do repositório privado>
    python tools/problemas_sincronia.py exportar --pasta <...> --dry-run
    python tools/problemas_sincronia.py classificar --id 35 --valor SO_PRODUCAO_DADOS --por <login>
    python tools/problemas_sincronia.py importar --pasta <...> [--dry-run]

No desenvolvimento, sem banco:

    python tools/problemas_sincronia.py responder --pasta <...> --arquivo of-0035 --estado NECESSARIO_TESTE --prova "tests/test_x.py" --nota "..." [--reproducao AQUI_FICTICIOS]
    python tools/problemas_sincronia.py conferir-retorno --pasta <...>

Na serventia, a operação (gera e não executa; sem banco):

    python tools/problemas_sincronia.py gerar-agendamento --repositorio <pasta do clone privado> --destino <pasta>

`exportar`, `classificar` e `importar` precisam de `CG_PG_DSN` e
`CG_PG_SCHEMA` no ambiente (o mesmo do servidor) e recusam se o schema não
existir: nunca criam banco. `responder` e `conferir-retorno` não abrem banco
(aceitam `--nota-arquivo` para nota de várias linhas). Não faz `git` e não envia
nada pela rede — commit e envio do repositório privado são do lançador que
`gerar-agendamento` escreve (`docs/SINCRONIA_DOS_PROBLEMAS.md`).

A linha de comando inteira mora em `problemas_sincronia.main`, na raiz (o
varredor de função sem tela só lê a raiz); este arquivo só a chama.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import problemas_sincronia as PS  # noqa: E402

for saida in (sys.stdout, sys.stderr):
    try:
        saida.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass


if __name__ == "__main__":
    raise SystemExit(PS.main())
