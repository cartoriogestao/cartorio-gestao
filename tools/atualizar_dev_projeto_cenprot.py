"""Atualiza andamento do projeto Integração CENPROT no banco sandbox."""
from __future__ import annotations

import os
import sys
from pathlib import Path

SANDBOX = Path(__file__).resolve().parent.parent
SISTEMA = SANDBOX / "sistema"
if str(SISTEMA) not in sys.path:
    sys.path.insert(0, str(SISTEMA))

import dev_projetos as DP  # noqa: E402
from database import Database  # noqa: E402


def main() -> int:
    data = os.environ.get("CARTORIO_GESTAO_DATA")
    if not data:
        data = str(SANDBOX / "dados")
        os.environ["CARTORIO_GESTAO_DATA"] = data
    db_path = Path(data) / "cartorio_gestao.sqlite3"
    if not db_path.is_file():
        print(f"Banco não encontrado: {db_path}", file=sys.stderr)
        return 1
    db = Database(db_path)
    with db.connect() as con:
        DP.init_dev_projetos_schema(con)
        pid = DP.atualizar_andamento_cenprot(con)
        con.commit()
    print(f"CENPROT atualizado (projeto_id={pid}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
