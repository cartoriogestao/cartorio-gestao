"""Marca os cancelamentos da matrícula 1.197 que ficaram sem vínculo no acervo.

Pedido (balcão do RI, 20/11/2026): na matrícula 1.197
(`ri_matriculas` id 4967) os atos de acervo têm cancelamento no teor, mas
`ri_atos.cancelado` ficou 0:

  - R-4 (id 4726) e R-5 (id 4727) ← cancelados pela AV-06 (id 4728)
  - R-2 desta matrícula ← cancelado pela AV-3 (id 4725)

NÃO TOCA nos atos 8423 e 4979. Não sela. Não reescreve teor nem hash.

COMO USAR (no servidor, com o banco da casa):

    python tools/marcar_cancelamentos_matricula_1197.py CAMINHO_DO_BANCO
    python tools/marcar_cancelamentos_matricula_1197.py CAMINHO_DO_BANCO --confirmar

Sem `--confirmar` só mede e mostra o plano. Com `--confirmar` copia o banco
(VACUUM INTO / shutil) e grava os UPDATEs.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import banco_pg  # noqa: E402
from bd_nativo import banco  # noqa: E402

MATRICULA_ID = 4967
MATRICULA_NUMERO = "1197"
# (ato_cancelado_id, cancelado_por_ato_id)
PARES_FIXOS = (
    (4726, 4728),  # R-4 ← AV-06
    (4727, 4728),  # R-5 ← AV-06
)
AV3_ID = 4725
PROIBIDOS = frozenset({8423, 4979})


class Recusa(SystemExit):
    pass


def _backup(caminho: Path) -> Path:
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = caminho.with_name(f"{caminho.stem}.ANTES-CANCEL-1197-{carimbo}{caminho.suffix}")
    import pasta_das_copias as _PC
    destino = _PC.destino_da_copia(destino, caminho)
    try:
        con = __import__("sqlite3").connect(str(caminho))
        con.execute(f"VACUUM INTO '{destino}'")
        con.close()
    except Exception:
        shutil.copy2(caminho, destino)
    return destino


def medir(bd) -> dict:
    m = bd.um("SELECT id, numero, livro, tipo_ficha FROM ri_matriculas WHERE id=%s",
              (MATRICULA_ID,))
    if not m:
        raise Recusa(f"RECUSO: matrícula id {MATRICULA_ID} não existe.")
    if str(m["numero"]).replace(".", "") != MATRICULA_NUMERO.replace(".", ""):
        raise Recusa(
            f"RECUSO: id {MATRICULA_ID} não é a matrícula {MATRICULA_NUMERO} "
            f"(número={m['numero']!r}).")
    atos = {int(r["id"]): dict(r) for r in bd.ler(
        """SELECT id, tipo, numero, cancelado, cancelado_por_ato_id, natureza_titulo
             FROM ri_atos WHERE matricula_id=%s""", (MATRICULA_ID,))}
    for proibido in PROIBIDOS:
        if proibido in atos:
            raise Recusa(f"RECUSO: o ato {proibido} está nesta matrícula — não mexo.")
    for alvo_id, por_id in PARES_FIXOS:
        if alvo_id not in atos or por_id not in atos:
            raise Recusa(f"RECUSO: falta o ato {alvo_id} ou {por_id} na matrícula {MATRICULA_ID}.")
    r2 = bd.um("""SELECT id, tipo, numero, cancelado, cancelado_por_ato_id
                    FROM ri_atos WHERE matricula_id=%s AND tipo='R' AND numero=2""",
               (MATRICULA_ID,))
    if not r2:
        raise Recusa("RECUSO: não achei R-2 nesta matrícula.")
    if int(r2["id"]) in PROIBIDOS:
        raise Recusa(f"RECUSO: R-2 é o ato proibido {r2['id']}.")
    if AV3_ID not in atos or atos[AV3_ID]["tipo"] != "AV":
        raise Recusa(f"RECUSO: a AV-3 (id {AV3_ID}) não está como esperado.")
    plano = []
    for alvo_id, por_id in PARES_FIXOS:
        a = atos[alvo_id]
        plano.append({"alvo_id": alvo_id, "por_id": por_id,
                      "rotulo": f"{a['tipo']}-{int(a['numero']):02d}",
                      "ja_cancelado": int(a["cancelado"] or 0),
                      "ja_por": a["cancelado_por_ato_id"]})
    plano.append({"alvo_id": int(r2["id"]), "por_id": AV3_ID,
                  "rotulo": f"R-{int(r2['numero']):02d}",
                  "ja_cancelado": int(r2["cancelado"] or 0),
                  "ja_por": r2["cancelado_por_ato_id"]})
    return {"matricula": dict(m), "plano": plano}


def aplicar(bd, plano: list[dict]) -> int:
    n = 0
    for item in plano:
        if int(item["alvo_id"]) in PROIBIDOS or int(item["por_id"]) in PROIBIDOS:
            raise Recusa("RECUSO: plano tocaria ato proibido.")
        if item["ja_cancelado"] == 1 and int(item["ja_por"] or 0) == int(item["por_id"]):
            continue
        bd.escrever(
            "UPDATE ri_atos SET cancelado=1, cancelado_por_ato_id=%s WHERE id=%s AND matricula_id=%s",
            (int(item["por_id"]), int(item["alvo_id"]), MATRICULA_ID))
        n += 1
    return n


def main() -> int:
    for saida in (sys.stdout, sys.stderr):
        try:
            saida.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("banco")
    ap.add_argument("--confirmar", action="store_true",
                    help="grava de verdade — sem isto, só mede")
    args = ap.parse_args()
    caminho = Path(args.banco)
    if not caminho.is_file():
        print(f"Não achei o banco em: {caminho}", file=sys.stderr)
        return 1
    con = banco_pg.conectar(caminho)
    bd = banco(con)
    try:
        medicao = medir(bd)
    except Recusa as e:
        print(str(e), file=sys.stderr)
        con.close()
        return 2
    m = medicao["matricula"]
    print(f"=== Matrícula {m['numero']} (id={m['id']}, livro {m.get('livro')}, "
          f"{m.get('tipo_ficha')}) ===\n")
    for item in medicao["plano"]:
        estado = ("já marcado" if item["ja_cancelado"] and int(item["ja_por"] or 0) == item["por_id"]
                  else f"cancelado={item['ja_cancelado']} por={item['ja_por']}")
        print(f"  {item['rotulo']} id={item['alvo_id']} ← ato {item['por_id']}  ({estado})")
    if not args.confirmar:
        print("\nSó medi. Para gravar: acrescente --confirmar")
        con.close()
        return 0
    copia = _backup(caminho)
    print(f"\nCópia antes: {copia}")
    n = aplicar(bd, medicao["plano"])
    con.commit()
    print(f"Marcados: {n} ato(s).")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
