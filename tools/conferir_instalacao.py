"""A conferência da instalação pela linha de comando (diária, e na emergência).

    python tools\\conferir_instalacao.py                      # confere (sai 1 se algo mudou)
    python tools\\conferir_instalacao.py emergencia --commit X --sandbox C:\\...\\SANDBOX\\sistema
    python tools\\conferir_instalacao.py aceitar --motivo "o conserto já está no INSTALAR"

`conferir` compara a instalação com o retrato da última atualização e grava o
resultado que a tela de Atualizações mostra. Sai com 1 quando há arquivo mudado
fora de uma atualização ou pendência de espelhamento — é o que um agendamento
diário usa para avisar. `emergencia` é chamado pelo `ATUALIZAR_SISTEMA.cmd`
depois de copiar. `aceitar` assume o estado instalado como base (com motivo).
Ver `retrato_da_instalacao.py`.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import retrato_da_instalacao as RET   # noqa: E402


def _dados() -> Path:
    base = os.environ.get("CARTORIO_GESTAO_DATA") or os.path.join(
        os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "CartorioGestao")
    return Path(base)


def _versao(instalacao: Path) -> str:
    v = instalacao / "VERSAO.txt"
    if v.is_file():
        return v.read_text(encoding="utf-8").strip()
    raise SystemExit(f"Não achei VERSAO.txt em {instalacao}.")


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("acao", nargs="?", default="conferir",
                    choices=("conferir", "emergencia", "aceitar"))
    ap.add_argument("--instalacao", type=Path, default=RAIZ,
                    help="a pasta do programa (padrão: a deste programa)")
    ap.add_argument("--dados", type=Path, default=None)
    ap.add_argument("--commit", default="")
    ap.add_argument("--sandbox", type=Path, default=None)
    ap.add_argument("--motivo", default="")
    a = ap.parse_args(argv)
    updates = (a.dados or _dados()) / "updates"
    versao = _versao(a.instalacao)

    if a.acao == "emergencia":
        r = RET.registrar_emergencia(updates, a.instalacao, versao, a.commit, a.sandbox)
        print(f"Emergência registrada: {len(r['mudados'])} arquivo(s) mudaram; "
              f"{len(r['pendencias'])} pendência(s) de espelhamento no SANDBOX.")
        for p in r["pendencias"]:
            print(f"  espelhar no SANDBOX: {p['path']}")
        return 0
    if a.acao == "aceitar":
        RET.aceitar(updates, a.instalacao, versao,
                    por=os.environ.get("USERNAME", "?"), motivo=a.motivo)
        print("O estado instalado virou a base da conferência.")
        return 0
    r = RET.conferir(updates, a.instalacao, versao)
    if a.sandbox is not None:
        r["pendencias"] = RET.pendencias(updates, a.sandbox)
    print(f"Versão {versao}, base: {r['origem']}. "
          + ("Nada mudou fora de uma atualização." if r["limpo"] else
             f"{len(r['alterados'])} alterado(s), {len(r['novos'])} novo(s), "
             f"{len(r['sumidos'])} sumido(s) fora de uma atualização."))
    for titulo in ("alterados", "novos", "sumidos"):
        for rel in r[titulo]:
            print(f"  {titulo[:-1]}: {rel}")
    for p in r["pendencias"]:
        print(f"  pendência de espelhamento: {p['path']}")
    return 0 if r["limpo"] and not r["pendencias"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
