# -*- coding: utf-8 -*-
"""Inventário dos papéis do CATALOGO × pontos de emissão.

Uso:
    python tools/inventario_modelos.py
    python tools/inventario_modelos.py --db C:\\ProgramData\\CartorioGestao\\cartorio_gestao.sqlite3

Exit 0 se todo padrao importar e toda chave tiver tipo.
Exit 1 se faltar tipo ou padrao quebrado.
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import banco_pg  # noqa: E402
from bd_nativo import banco  # noqa: E402

_SKIP = {"__pycache__", ".git", "tmp", "tests", "node_modules", ".venv", "runtime", "DOCUMENTACAO"}


def _py_files() -> list[Path]:
    out = []
    for p in ROOT.rglob("*.py"):
        if any(x in p.parts for x in _SKIP):
            continue
        out.append(p)
    return out


def _emit_hits(chave: str, files: list[Path]) -> int:
    n = 0
    for p in files:
        try:
            if chave in p.read_text(encoding="utf-8", errors="ignore"):
                n += 1
        except OSError:
            continue
    return n


# Revisão RI 13/08 — «Grupo A» ainda sem minuta em `ri_modelos_atos` (CHECKLIST RI-14 P1).
_RI_GRUPO_A_NATUREZAS: list[tuple[str, tuple[str, ...]]] = [
    ("Promessa de compra e venda / cessão", ("promessa", "cessão")),
    ("Servidão", ("servid",)),
    ("Cessão de direitos hereditários", ("heredit",)),
    ("Dação em pagamento", ("dação", "dacao")),
    ("Bem de família", ("família", "familia")),
    ("Locação com vigência", ("locação", "locacao")),
    ("Consolidação fiduciária", ("consolida", "fiduci")),
    ("Cancelamento indisponibilidade / penhora", ("indispon", "penhora")),
    ("União estável (RI)", ("união", "uniao", "estável", "estavel")),
    ("Ação real / averbação premonitória", ("premonit", "ação real", "acao real")),
    ("Demolição", ("demoli",)),
    ("Desapropriação", ("desapropri",)),
    ("Resultado de retificação", ("retifica",)),
    ("Legitimação fundiária / de posse", ("legitima",)),
    ("CDRU / CUEM", ("cdru", "cuem")),
    ("Comodato", ("comodato",)),
    ("Tombamento", ("tombamento",)),
    ("Pagamento por serviços ambientais", ("ambient", "psa")),
]


def _ri_grupo_a_faltando() -> list[str]:
    import ri_modelos_atos as rma

    hay = " ".join(
        f"{m.get('codigo', '')} {m.get('nome', '')} {m.get('natureza', '')}".lower()
        for m in rma.MODELOS
    )
    faltam: list[str] = []
    for rotulo, pedacos in _RI_GRUPO_A_NATUREZAS:
        if not any(p in hay for p in pedacos):
            faltam.append(rotulo)
    return faltam


def _relatorio_minutas(db_path: str | None) -> None:
    import notas_modelos as nm
    import ri_modelos_atos as rma

    print("=== MINUTAS DE ATO (fora do CATALOGO de papéis) ===")
    print(f"RI ri_modelos_atos.MODELOS: {len(rma.MODELOS)}")
    por_tipo: dict[str, int] = {}
    for m in rma.MODELOS:
        por_tipo[m["tipo"]] = por_tipo.get(m["tipo"], 0) + 1
    print("  por tipo:", ", ".join(f"{k}={v}" for k, v in sorted(por_tipo.items())))

    faltam = _ri_grupo_a_faltando()
    print(f"RI Grupo A (revisão 13/08) sem cobertura heurística: {len(faltam)}")
    for item in faltam:
        print(f"  - {item}")

    seed_nt = {}
    for m in nm.MODELOS:
        t = m.get("tipo") or "?"
        seed_nt[t] = seed_nt.get(t, 0) + 1
    print(f"Notas notas_modelos.MODELOS (seed fábrica): {len(nm.MODELOS)}")
    print("  por tipo:", ", ".join(f"{k}={v}" for k, v in sorted(seed_nt.items())))

    esc = [m for m in nm.MODELOS if m.get("tipo") == "ESCRITURA"]
    decl = [m for m in esc if "declarat" in (m.get("nome") or "").lower()]
    print(f"  ESCRITURA no seed: {len(esc)} (com 'declarat' no nome: {len(decl)})")

    if db_path:
        con = banco_pg.conectar(db_path)
        bd = banco(con)
        rows = bd.ler(
            "SELECT tipo, count(*) AS n FROM nt_modelos GROUP BY tipo "
            "ORDER BY 2 DESC, tipo"
        )
        print(f"nt_modelos no banco ({db_path}):")
        for r in rows:
            print(f"  {r['tipo']}: {r['n']}")
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None)
    ap.add_argument("--estrito", action="store_true")
    ap.add_argument(
        "--minutas",
        action="store_true",
        help="Relatório RI/Notas minutas de ato + lacunas Grupo A (Ajuda #73)",
    )
    args = ap.parse_args()

    if args.minutas:
        _relatorio_minutas(args.db)
        return 0

    import modelos_da_casa as m

    erros: list[str] = []
    files = _py_files()
    print(f"CATALOGO: {len(m.CATALOGO)} chaves; py escaneados: {len(files)}")
    print(f"{'chave':28} {'tipo':12} {'padrao':48} refs")
    for e in m.CATALOGO:
        chave = e["chave"]
        tipo = e.get("tipo")
        if not tipo:
            erros.append(f"sem tipo: {chave}")
            tipo = "?"
        mod, const = e["padrao"]
        try:
            val = getattr(importlib.import_module(mod), const)
            if val is None or (isinstance(val, str) and not str(val).strip()):
                erros.append(f"padrao vazio: {chave} -> {mod}.{const}")
            pad = f"{mod}.{const}"
        except Exception as ex:  # noqa: BLE001
            erros.append(f"padrao quebrado: {chave} -> {mod}.{const}: {ex}")
            pad = f"{mod}.{const}!!"
        refs = _emit_hits(chave, files)
        if args.estrito and refs < 1:
            erros.append(f"sem referência de emissão: {chave}")
        print(f"{chave:28} {tipo:12} {pad:48} {refs}")

    if args.db:
        con = banco_pg.conectar(args.db)
        bd = banco(con)
        print(
            "DB mo_elementos=%s mo_modelos=%s"
            % (
                bd.valor("SELECT count(*) FROM mo_elementos"),
                bd.valor("SELECT count(*) FROM mo_modelos"),
            )
        )
        for r in bd.ler(
            "SELECT atribuicao, ato, parte, atualizado_por, atualizado_em "
            "FROM mo_elementos ORDER BY id"
        ):
            print("  override:", tuple(r.values()))

    if erros:
        print("FALHAS:")
        for e in erros:
            print(" -", e)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
