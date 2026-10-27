"""Exporta fila de `aj_problemas` (oficial -> JSON) para import no sandbox.

Leitura no SQLite de origem (padrao: ProgramData). Nao altera o banco.

Uso tipico:

    python tools/export_problemas_fila.py
    python tools/export_problemas_fila.py --dry-run
    python tools/export_problemas_fila.py --saida ..\\dados\\problemas_oficial_20260925.json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import ajuda_problemas as AP  # noqa: E402

for saida in (sys.stdout, sys.stderr):
    try:
        saida.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

BANCO_PADRAO = Path(r"C:\ProgramData\CartorioGestao\cartorio_gestao.sqlite3")
SCHEMA_VERSION = 1
FILA_PADRAO = AP.SITUACOES[:2]  # ABERTO, RELATADO


def _colunas_upsert(con: sqlite3.Connection) -> list[str]:
    """Todas as colunas de aj_problemas exceto `id` (PK local do destino)."""
    return [
        linha[1]
        for linha in con.execute("PRAGMA table_info(aj_problemas)")
        if linha[1] != "id"
    ]


def _filtro_sql(todos_abertos: bool) -> tuple[str, tuple[str, ...]]:
    if todos_abertos:
        return "COALESCE(situacao,'') != 'RESOLVIDO'", ()
    marcas = ", ".join("?" * len(FILA_PADRAO))
    return f"situacao IN ({marcas})", tuple(FILA_PADRAO)


def _carregar_linhas(con: sqlite3.Connection, todos_abertos: bool) -> list[sqlite3.Row]:
    con.row_factory = sqlite3.Row
    where, params = _filtro_sql(todos_abertos)
    return list(
        con.execute(
            f"SELECT * FROM aj_problemas WHERE {where} ORDER BY id",
            params,
        )
    )


def _linha_para_export(row: sqlite3.Row, colunas: list[str]) -> dict:
    dados = {c: row[c] for c in colunas if c in row.keys()}
    registro = {"id_oficial": int(row["id"])}
    registro.update(dados)
    if "impressao" not in registro or not registro["impressao"]:
        raise ValueError(f"Linha id={row['id']} sem impressao (UNIQUE obrigatoria).")
    return registro


def _saida_padrao() -> Path:
    hoje = datetime.now().strftime("%Y%m%d")
    sandbox = RAIZ.parent.parent
    candidato = sandbox / f"problemas_oficial_{hoje}.json"
    if sandbox.is_dir():
        return candidato
    return Path.cwd() / f"problemas_oficial_{hoje}.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--db",
        type=Path,
        default=BANCO_PADRAO,
        help=f"SQLite de origem (padrao: {BANCO_PADRAO})",
    )
    ap.add_argument(
        "--saida",
        type=Path,
        default=None,
        help="Arquivo JSON de saida (padrao: SANDBOX/problemas_oficial_YYYYMMDD.json)",
    )
    ap.add_argument(
        "--todos-abertos",
        action="store_true",
        help="Incluir qualquer situacao exceto RESOLVIDO (fila ampliada / palavras fora do vocabulario).",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="So imprime a quantidade; nao grava arquivo.",
    )
    args = ap.parse_args()

    db = args.db.expanduser().resolve()
    if not db.is_file():
        print(f"ERRO: banco nao encontrado: {db}", file=sys.stderr)
        return 2

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        colunas = _colunas_upsert(con)
        linhas = _carregar_linhas(con, args.todos_abertos)
    finally:
        con.close()

    filtro = (
        "nao_resolvido"
        if args.todos_abertos
        else list(FILA_PADRAO)
    )
    print(f"Banco: {db}")
    print(f"Filtro: {filtro}")
    print(f"Registros: {len(linhas)}")

    if args.dry_run:
        return 0

    registros = [_linha_para_export(r, colunas) for r in linhas]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "exportado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
        "origem_db": str(db),
        "filtro": filtro,
        "total": len(registros),
        "registros": registros,
    }

    saida = (args.saida or _saida_padrao()).expanduser()
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Gravado: {saida.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
