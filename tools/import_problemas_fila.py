"""Legado (SQLite, sem máscara). Para levar problemas ao desenvolvimento, use `tools/problemas_sincronia.py`.

Importa fila de `aj_problemas` (JSON do oficial -> sandbox) por `impressao`.

Upsert: nunca apaga linhas que existem so no sandbox. Inserts usam o **mesmo id**
do oficial (`id_oficial` no JSON) quando livre; ao final ajusta `sqlite_sequence`.

Padrao: banco do sandbox em SANDBOX/dados. **Perigo:** `--db` apontando para
ProgramData altera producao.

Uso tipico:

    python tools/import_problemas_fila.py --entrada ..\\problemas_oficial_20260925.json
    python tools/import_problemas_fila.py --entrada arquivo.json --dry-run
    python tools/import_problemas_fila.py --realinhar-ids --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
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

# A pasta de dados do sandbox vem do ambiente (CG_SANDBOX_DADOS); o caminho
# da maquina de uma serventia nao se escreve no codigo publico.
BANCO_SANDBOX = Path(os.environ.get("CG_SANDBOX_DADOS", r"SANDBOX\dados")) / "cartorio_gestao.sqlite3"
BANCO_PRODUCAO = Path(r"C:\ProgramData\CartorioGestao\cartorio_gestao.sqlite3")

ORIGEM_ID_RE = re.compile(r"origem_id_oficial\s*=\s*(\d+)", re.I)


def _colunas_upsert(con: sqlite3.Connection) -> list[str]:
    return [
        linha[1]
        for linha in con.execute("PRAGMA table_info(aj_problemas)")
        if linha[1] != "id"
    ]


def _ler_json(caminho: Path) -> tuple[list[dict], dict]:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    meta: dict = {}
    if isinstance(bruto, list):
        return bruto, meta
    if isinstance(bruto, dict):
        meta = {k: bruto[k] for k in bruto if k != "registros"}
        regs = bruto.get("registros")
        if not isinstance(regs, list):
            raise ValueError("JSON sem chave 'registros' (lista).")
        return regs, meta
    raise ValueError("JSON deve ser lista ou objeto com 'registros'.")


def _id_oficial(reg: dict) -> int | None:
    if "id_oficial" in reg and reg["id_oficial"] is not None:
        return int(reg["id_oficial"])
    if "origem_id_oficial" in reg and reg["origem_id_oficial"] is not None:
        return int(reg["origem_id_oficial"])
    if "id" in reg and reg["id"] is not None:
        return int(reg["id"])
    return None


def _merge_nota_dev(
    existente: str | None,
    incoming: str | None,
    id_oficial: int | None,
) -> str:
    linhas: list[str] = []
    for bloco in (existente, incoming):
        if bloco and str(bloco).strip():
            linhas.extend(str(bloco).strip().splitlines())

    texto = "\n".join(linhas).strip()
    if id_oficial is not None:
        marcador = f"origem_id_oficial={id_oficial}"
        if marcador not in texto and not ORIGEM_ID_RE.search(texto):
            texto = (texto + "\n" + marcador).strip() if texto else marcador

    if "REPLICADO_SBX" not in texto:
        texto = (texto + "\nREPLICADO_SBX").strip() if texto else "REPLICADO_SBX"
    return texto


def _valores_registro(reg: dict, colunas: list[str], nota_dev: str) -> list:
    vals = []
    for col in colunas:
        if col == "nota_dev":
            vals.append(nota_dev)
        elif col in reg:
            vals.append(reg[col])
        else:
            vals.append(None)
    return vals


def _avisar_se_producao(db: Path) -> None:
    try:
        if db.resolve() == BANCO_PRODUCAO.resolve():
            print(
                "AVISO: --db aponta para o SQLite de PRODUCAO (ProgramData). "
                "Este script GRAVA no banco. Use o padrao do sandbox salvo "
                "intencao explicita de escrever na producao.",
                file=sys.stderr,
            )
    except OSError:
        pass


def importar(
    con: sqlite3.Connection,
    registros: list[dict],
    *,
    dry_run: bool,
) -> dict:
    AP.init_problemas_schema(con)
    AP.preencher_ambiente_abertura(con)
    colunas = _colunas_upsert(con)
    con.row_factory = sqlite3.Row

    inseridos = atualizados = ignorados = realinhados = 0
    erros: list[str] = []

    for reg in registros:
        impressao = (reg.get("impressao") or "").strip()
        if not impressao:
            ignorados += 1
            erros.append("registro sem impressao")
            continue

        id_of = _id_oficial(reg)
        existente = con.execute(
            "SELECT * FROM aj_problemas WHERE impressao=?", (impressao,)
        ).fetchone()

        nota_in = reg.get("nota_dev")
        nota = _merge_nota_dev(
            existente["nota_dev"] if existente else None,
            str(nota_in) if nota_in is not None else None,
            id_of,
        )
        reg_sync = dict(reg)
        reg_sync["nota_dev"] = nota
        reg_sync["ambiente_abertura"] = "OFICIAL"
        for chave in ("id_oficial", "origem_id_oficial", "id"):
            reg_sync.pop(chave, None)

        valores = _valores_registro(reg_sync, colunas, nota)

        if existente is None:
            id_insert = None
            if id_of is not None:
                if AP.id_livre(con, id_of):
                    id_insert = id_of
                else:
                    ignorados += 1
                    erros.append(
                        f"{impressao}: id oficial {id_of} ocupado no sandbox")
                    continue
            inseridos += 1
            if not dry_run:
                if id_insert is not None:
                    cols_sql = "id, " + ", ".join(colunas)
                    marcas = ", ".join("?" * (len(colunas) + 1))
                    con.execute(
                        f"INSERT INTO aj_problemas ({cols_sql}) VALUES ({marcas})",
                        [id_insert] + valores,
                    )
                else:
                    cols_sql = ", ".join(colunas)
                    marcas = ", ".join("?" * len(colunas))
                    con.execute(
                        f"INSERT INTO aj_problemas ({cols_sql}) VALUES ({marcas})",
                        valores,
                    )
        else:
            id_atual = int(existente["id"])
            if id_of is not None and id_atual != id_of:
                try:
                    if not dry_run:
                        if AP.realinhar_id_problema(
                                con, id_atual=id_atual, id_desejado=id_of,
                                impressao=impressao):
                            realinhados += 1
                    else:
                        realinhados += 1
                except ValueError as exc:
                    erros.append(f"{impressao}: {exc}")
                    ignorados += 1
                    continue
            atualizados += 1
            if not dry_run:
                sets = ", ".join(f"{c}=?" for c in colunas)
                con.execute(
                    f"UPDATE aj_problemas SET {sets} WHERE impressao=?",
                    valores + [impressao],
                )

    if not dry_run:
        AP.atualizar_sqlite_sequence(con)
        con.commit()
    return {
        "inseridos": inseridos,
        "atualizados": atualizados,
        "realinhados": realinhados,
        "ignorados": ignorados,
        "total_processados": len(registros),
        "erros_amostra": erros[:8],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--db",
        type=Path,
        default=BANCO_SANDBOX,
        help=f"SQLite destino (padrao: sandbox {BANCO_SANDBOX})",
    )
    ap.add_argument(
        "--entrada",
        type=Path,
        help="JSON exportado por export_problemas_fila.py",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula upsert sem gravar.",
    )
    ap.add_argument(
        "--realinhar-ids",
        action="store_true",
        help="Só corrige ids do piloto (origem_id_oficial na nota_dev).",
    )
    args = ap.parse_args()

    db = args.db.expanduser().resolve()
    _avisar_se_producao(db)

    if not db.is_file():
        print(f"ERRO: banco nao encontrado: {db}", file=sys.stderr)
        return 2

    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    try:
        if args.realinhar_ids:
            stats = AP.realinhar_ids_replicados(con, dry_run=args.dry_run)
            if not args.dry_run:
                AP.preencher_ambiente_abertura(con)
                con.commit()
            modo = "dry-run" if args.dry_run else "gravado"
            print(
                f"[{modo}] realinhados={stats['realinhados']} "
                f"pulados={stats['pulados']}")
            if stats["erros"]:
                print("Erros:", stats["erros"], file=sys.stderr)
            return 1 if stats["erros"] else 0

        if not args.entrada:
            print("ERRO: informe --entrada ou --realinhar-ids", file=sys.stderr)
            return 2
        entrada = args.entrada.expanduser().resolve()
        if not entrada.is_file():
            print(f"ERRO: entrada nao encontrada: {entrada}", file=sys.stderr)
            return 2

        registros, meta = _ler_json(entrada)
        print(f"Entrada: {entrada}")
        if meta:
            print(
                f"Meta export: origem_db={meta.get('origem_db', '?')} "
                f"total={meta.get('total', '?')}")
        print(f"Destino: {db}")
        print(f"Registros no arquivo: {len(registros)}")

        stats = importar(con, registros, dry_run=args.dry_run)
    finally:
        con.close()

    modo = "dry-run" if args.dry_run else "gravado"
    print(
        f"[{modo}] inseridos={stats['inseridos']} "
        f"atualizados={stats['atualizados']} "
        f"realinhados={stats['realinhados']} "
        f"ignorados={stats['ignorados']}")
    if stats["erros_amostra"]:
        print("Avisos:", stats["erros_amostra"], file=sys.stderr)
    return 1 if stats["erros_amostra"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
