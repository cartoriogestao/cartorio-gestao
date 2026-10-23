"""A PROVA DAS VARREDURAS DO LH05 — que as montagens mudaram só pelo claro novo.

O ouro do LF06C (`ouro_lf06c_termos.py`) guarda das varreduras só a contagem e
o sha256 das saídas. O LH05 (21/10/2026, os hotfixes «registro tardio» do
servidor) deu ao termo de nascimento o claro `{frase_tardio}`, e o resumo novo
de `varre.nascimento` está em `tests/test_modelos_da_casa.py`
(`_LH05_VARREDURAS`). Este script refaz as três varreduras caso a caso, na
árvore de antes do LH05 e na de agora, e exige:

    nascimento   cada caso de antes, com `frase_tardio: ""` nos valores, dá o
                 caso de agora — o texto montado não muda em nenhum (nenhum
                 caso da varredura é registro tardio)
    casamento    igual, caso a caso
    óbito        igual, caso a caso

É o mesmo colhedor do `ld01_varreduras.py`. Uso (o Python sem `CG_PG_DSN`: os
padrões saem da pasta de cada árvore):

    git archive 87b045e | tar -x -C /tmp/antes_do_lh05
    python -B lh05_varreduras.py /tmp/antes_do_lh05
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ld01_varreduras as LD01                                   # noqa: E402


def _nascimento(a, d):
    valores, texto = a[1]
    return ["ok", [{**valores, "frase_tardio": ""}, texto]]


def _igual(a, d):
    return a


REGRAS = {"varre.nascimento": _nascimento, "varre.casamento": _igual,
          "varre.obito": _igual}


def provar(raiz_de_antes: Path) -> int:
    antes, agora = LD01.colher(raiz_de_antes), LD01.colher(LD01.RAIZ)
    fora = 0
    for nome, regra in REGRAS.items():
        for a, d in zip(antes[nome], agora[nome], strict=True):
            if (regra(a, d) if a[0] == "ok" else a) != d:
                fora += 1
        print(f"{nome}: {len(antes[nome])} casos")
    print(f"{fora} caso(s) que a regra não explica")
    return 1 if fora else 0


if __name__ == "__main__":
    raise SystemExit(provar(Path(sys.argv[1]).resolve()))
