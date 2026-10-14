"""Fecha os cronômetros esquecidos pela regra do expediente — para o Agendador.

    «avisa fechamento 14h15, mas encerra 14h30, com horário retroativo a 14h15,
     se não tivermos confirmação do usuário»       — o oficial, 11/10/2026

A tela já faz isso sozinha para quem está com o sistema aberto. Este script é
para quem foi embora com o navegador fechado: rodado às 14h31, ele fecha os
cronômetros sem confirmação com a hora de 14h15, e a pessoa vê o aviso na
próxima vez que entrar (`encerrados_sem_ciencia`).

Só mede por padrão; grava com `--confirmar`. O banco é o da produção se
`--banco` não for dado.

    python tools/encerrar_cronometros_esquecidos.py            (mostra)
    python tools/encerrar_cronometros_esquecidos.py --confirmar (fecha)
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import produtividade as PR  # noqa: E402

BANCO_PRODUCAO = r"C:\ProgramData\CartorioGestao\cartorio_gestao.sqlite3"


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--banco", default=BANCO_PRODUCAO)
    ap.add_argument("--confirmar", action="store_true")
    a = ap.parse_args(argv)
    con = sqlite3.connect(a.banco, timeout=30)
    try:
        con.execute("BEGIN IMMEDIATE")
        fechados = PR.encerrar_esquecidos(con)
        for f in fechados:
            print(f"{f['responsavel_nome']}: «{f['tarefa']}» {f['data_registro']} "
                  f"{f['hora_inicio']}–{f['hora_fim']} — {f['motivo']}")
        if a.confirmar:
            con.commit()
            print(f"{len(fechados)} cronômetro(s) encerrado(s).")
        else:
            con.rollback()
            print(f"{len(fechados)} seriam encerrados. Nada foi gravado (use --confirmar).")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
