"""O OURO DO LF06B — o que as frases do Registro de Imóveis eram ANTES de sair do código.

Cada `lf06b_<parte>.py`, ao lado, tem um `chamadas()`: os montadores do RI
chamados com um contexto de teste — nomes «DE EXEMPLO», CPF de teste, nenhum
dado real de pessoa (LGPD). O `gerar()` abaixo roda essas chamadas na ÁRVORE DE
ANTES e grava `LF06B_<parte>.json`:

    o commit de antes é o 2c41e90 (o HEAD em que o LF06B começou), exportado
    sem checkout para uma pasta à parte —
        git archive 2c41e90 | tar -x -C /tmp/lf06b_antes
    e o gerador põe aquela pasta na frente do `sys.path`, de modo que os
    módulos importados são os de antes, com as f-strings ainda no código.

    python tests/fixtures/modelos_ouro/ouro_lf06b.py /tmp/lf06b_antes <parte>

**NÃO SE REGERA NA ÁRVORE DE DEPOIS**: as frases já estariam na base, e o teste
passaria a comparar a base com ela mesma. O gerador recusa rodar fora de uma
árvore que não seja a do commit gravado.

`chamadas()` é a mesma lista que o teste refaz depois da mudança
(`test_modelos_da_casa.py`, seção LF06B), saída por saída, byte a byte.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
COMMIT_DE_ANTES = "2c41e90"


def normal(valor):
    """A forma com que o valor foi gravado (tupla vira lista, chave ordenada)."""
    return json.loads(json.dumps(valor, ensure_ascii=False, sort_keys=True))


def tenta(f):
    try:
        return {"ok": f()}
    except Exception as erro:  # noqa: BLE001 — o erro também é saída
        return {"erro": f"{type(erro).__name__}: {erro}"}


def partes() -> list[str]:
    return sorted(p.stem[len("lf06b_"):] for p in AQUI.glob("lf06b_*.py"))


def parte(nome: str):
    """O módulo `lf06b_<nome>.py`, carregado pelo caminho (não pelo `sys.path`)."""
    espec = importlib.util.spec_from_file_location(f"lf06b_{nome}", AQUI / f"lf06b_{nome}.py")
    mod = importlib.util.module_from_spec(espec)
    espec.loader.exec_module(mod)
    return mod


def arquivo(nome: str) -> Path:
    return AQUI / f"LF06B_{nome}.json"


def gerar(raiz_antes: Path, nome: str) -> Path:
    """Grava o ouro da parte. SÓ NA ÁRVORE DE ANTES — ver o cabeçalho."""
    raiz_antes = Path(raiz_antes).resolve()
    if (raiz_antes / "ri_frases.py").exists():
        raise SystemExit(f"{raiz_antes} já tem o ri_frases.py: é a árvore de DEPOIS.")
    os.environ.pop("CG_PG_DSN", None)          # sem banco: o padrão sai da pasta
    os.chdir(raiz_antes)
    sys.path.insert(0, str(raiz_antes))
    saidas = {k: normal(tenta(f)) for k, f in parte(nome).chamadas().items()}
    destino = arquivo(nome)
    destino.write_text(json.dumps(
        {"_como": ("Gerado ANTES do LF06B, na árvore exportada do commit "
                   f"{COMMIT_DE_ANTES} (git archive), por ouro_lf06b.gerar. Não "
                   "regerar depois da mudança: o teste compararia a base com ela "
                   "mesma."),
         "commit": COMMIT_DE_ANTES, "parte": nome, "funcoes": saidas},
        ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return destino


def ouro(nome: str) -> dict:
    return json.loads(arquivo(nome).read_text(encoding="utf-8"))


if __name__ == "__main__":
    print(gerar(Path(sys.argv[1]), sys.argv[2]))
