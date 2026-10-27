"""Empurra o retrato do painel para a VPS — para o Agendador do Windows.

    «o servidor EMPURRA, conexão de saída» — pedido de 26/10/2026

Faz o mesmo que o botão «Enviar um retrato agora» da tela /painel/retrato,
com uma diferença deliberada: aqui o envio só sai com o interruptor
«envio automático ligado» marcado na tela. Desligar na tela basta para parar
o Agendador, sem ninguém mexer na tarefa agendada.

NADA AQUI AGENDA NADA. Agendar (de quanto em quanto tempo, em que usuário do
Windows) é decisão do oficial. Uma sugestão, para quando ele decidir:

    a cada 15 minutos, das 7h às 19h, com o Python do servidor:
    <python do servidor> tools\\painel_empurrar.py

A pasta de dados é a mesma do servidor (`CARTORIO_GESTAO_DATA`, ou a padrão
da instalação); a chave que assina vem do cofre dela.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dados", default=None,
                    help="pasta de dados (padrão: a do servidor)")
    a = ap.parse_args(argv)

    from app import get_data_dir
    from database import Database
    import painel_retrato as PR

    pasta = Path(a.dados) if a.dados else get_data_dir()
    db = Database(pasta / "cartorio_gestao.sqlite3")
    feito = PR.empurrar(db, pasta)
    if feito.get("ok"):
        print(f"Retrato aceito pela VPS ({feito.get('bytes')} bytes).")
        return 0
    print(f"Retrato não enviado: {feito.get('motivo')}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
