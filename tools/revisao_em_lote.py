"""A revisão dos atos PASSADOS por um agente — sem depender da API.

    «e dar uma opção para revisar todos atos passados utilizando um agente,
     não necessariamente a api» — o oficial, 06/10/2026

O CAMINHO, EM TRÊS PASSOS
    1. exportar — um arquivo por ato, mascarado pela MESMA barreira da ajuda,
       com o contexto (no RI: a ficha e os atos ANTERIORES àquele; nas Notas:
       as partes) e o `INSTRUCAO.md` com a régua do revisor antes da lavratura.
       Lotes de 25. O mapa da máscara fica em `_mapas/`, fora do que o agente lê.
    2. um agente lê os lotes (esta sessão do Claude Code, um subagente, outra
       sessão) e escreve `resultados/<lote>.jsonl`, uma linha por ato.
    3. importar — devolve os nomes, e grava cada revisão em `rv_revisoes` com
       `origem='AGENTE'`, com a MESMA identidade de texto do revisor antes da
       lavratura (atribuição, alvo e hash do texto). O gestor transforma os
       apontamentos em tarefa para a qualificação.

O QUE ELE NÃO FAZ: não corrige ato. Ato lavrado se corrige por averbação, e
quem decide é quem assina.

    python tools/revisao_em_lote.py exportar --banco BANCO --saida PASTA
           [--desde 2026-09-10] [--com-acervo] [--atribuicoes RI,NOTAS,LIVRO3]
    python tools/revisao_em_lote.py importar --banco BANCO --pasta PASTA
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent.parent
if str(AQUI) not in sys.path:
    sys.path.insert(0, str(AQUI))

import revisao_previa as RV  # noqa: E402
from gestor_expedientes import desmascarar, mascarar  # noqa: E402

TAMANHO_DO_LOTE = 25

FORMATO = """
## Como responder

Para CADA arquivo `.txt` do lote, escreva UMA linha em `resultados/<lote>.jsonl`:

    {"arquivo": "<nome do .txt>", "achados": [{"gravidade": "GRAVE" | "ATENCAO",
      "o_que": "...", "trecho": "...", "por_que": "..."}], "parecer": "..."}

O ato aqui JÁ FOI LAVRADO: GRAVE é o que exige averbação de retificação ou
compromete o ato; o resto é ATENCAO. Sem achado, `"achados": []`. Não leia a
pasta `_mapas/`. Não invente: se o texto não permite concluir, não aponte.
"""


def _atos(con, atribuicoes, desde, com_acervo):
    if "RI" in atribuicoes:
        sql = """SELECT a.id, a.matricula_id, a.tipo, a.numero, a.teor, a.natureza_titulo,
                        m.numero FROM ri_atos a JOIN ri_matriculas m ON m.id = a.matricula_id
                  WHERE COALESCE(a.cancelado,0) = 0 AND COALESCE(a.teor,'') <> ''
                    AND COALESCE(a.lavrado_em, a.data_ato, '') >= ?"""
        if not com_acervo:
            sql += " AND COALESCE(a.acervo,0) = 0"
        for aid, mid, tipo, num, teor, nat, mnum in con.execute(sql + " ORDER BY a.id", (desde,)):
            yield {"atribuicao": "RI", "alvo_id": mid, "ato_id": aid,
                   "hash": RV.hash_do_ato(tipo, teor), "rotulo": f"{tipo}-{num} da matrícula {mnum}",
                   "dossie": RV.dossie_ri_lavrado(con, aid)}
    if "NOTAS" in atribuicoes:
        for aid, tipo, teor in con.execute(
                """SELECT id, tipo, teor FROM nt_atos WHERE COALESCE(teor,'') <> ''
                      AND situacao NOT IN ('CANCELADO','EM_LAVRATURA')
                      AND COALESCE(data, '') >= ? ORDER BY id""", (desde,)):
            yield {"atribuicao": "NOTAS", "alvo_id": aid, "ato_id": aid,
                   "hash": RV.hash_do_ato(tipo, teor), "rotulo": f"{tipo} das Notas id {aid}",
                   "dossie": RV.dossie_notas(con, aid)}
    if "LIVRO3" in atribuicoes:
        for aid, rid, teor, tipo in con.execute(
                """SELECT id, registro_id, teor, tipo FROM ra_atos
                    WHERE COALESCE(teor,'') <> '' AND COALESCE(data_ato, criado_em, '') >= ?
                    ORDER BY id""", (desde,)):
            yield {"atribuicao": "LIVRO3", "alvo_id": aid, "ato_id": aid,
                   "hash": RV.hash_do_ato(tipo, teor), "rotulo": f"Livro 3, ato id {aid}",
                   "dossie": f"LIVRO 3 — REGISTRO id {rid}\n\n=== ATO JÁ LAVRADO ===\n"
                             f"Tipo: {tipo}\n{RV.normalizar(teor)}"}


def exportar(con, saida: Path, *, atribuicoes=("RI", "NOTAS", "LIVRO3"),
             desde="2026-09-10", com_acervo=False, sem_mascara=None) -> dict:
    """SEM MÁSCARA É ESCOLHA DELIBERADA, e fica escrita no INSTRUCAO.md: a regra
    da casa é mascarar por padrão. Medido em 06/10/2026, a máscara troca também
    município, nome de fazenda e número de matrícula por marcas — e a revisão
    fica cega para confrontação e numeração."""
    if sem_mascara is None:                     # a decisão do oficial (revisao_previa)
        sem_mascara = not RV.mascarar_na_revisao(con)
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "_mapas").mkdir(exist_ok=True)
    (saida / "resultados").mkdir(exist_ok=True)
    (saida / "INSTRUCAO.md").write_text(
        "# Revisão em lote dos atos lavrados\n\n"
        + ("**Exportado SEM máscara, por escolha de quem exportou.**\n\n" if sem_mascara else "")
        + RV.INSTRUCAO + "\n" + FORMATO,
        encoding="utf-8")
    indice, n = {}, 0
    for item in _atos(con, set(atribuicoes), desde, com_acervo):
        lote = f"lote_{n // TAMANHO_DO_LOTE + 1:03d}"
        nome = f"{item['atribuicao']}_{item['ato_id']}.txt"
        seguro, mapa = (item["dossie"], {}) if sem_mascara else mascarar(item["dossie"])
        (saida / lote).mkdir(exist_ok=True)
        (saida / lote / nome).write_text(seguro, encoding="utf-8")
        (saida / "_mapas" / f"{nome}.json").write_text(json.dumps(mapa, ensure_ascii=False),
                                                       encoding="utf-8")
        indice[nome] = {k: item[k] for k in ("atribuicao", "alvo_id", "ato_id", "hash", "rotulo")}
        n += 1
    (saida / "_mapas" / "indice.json").write_text(json.dumps(indice, ensure_ascii=False),
                                                  encoding="utf-8")
    return {"atos": n, "lotes": (n + TAMANHO_DO_LOTE - 1) // TAMANHO_DO_LOTE}


def importar(con, pasta: Path) -> dict:
    RV.init_schema(con)
    indice = json.loads((pasta / "_mapas" / "indice.json").read_text(encoding="utf-8"))
    gravados = repetidos = desconhecidos = 0
    agora = datetime.now().isoformat(timespec="seconds")
    for arquivo in sorted((pasta / "resultados").glob("*.jsonl")):
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            if not linha.strip():
                continue
            r = json.loads(linha)
            item = indice.get(r.get("arquivo"))
            if item is None:
                desconhecidos += 1
                continue
            mapa = json.loads((pasta / "_mapas" / f"{r['arquivo']}.json").read_text(encoding="utf-8"))
            resultado = desmascarar(RV._ler_json(json.dumps(
                {"achados": r.get("achados") or [], "parecer": r.get("parecer") or ""})), mapa)
            if con.execute("""SELECT 1 FROM rv_revisoes WHERE atribuicao=? AND alvo_id=?
                                 AND hash_texto=? AND origem='AGENTE'""",
                           (item["atribuicao"], item["alvo_id"], item["hash"])).fetchone():
                repetidos += 1
                continue
            con.execute(
                """INSERT INTO rv_revisoes (atribuicao, alvo_id, hash_texto, rotulo, dossie,
                       situacao, pedido_em, pedido_por, terminado_em, provedor, modelo,
                       resultado_json, graves, origem)
                   VALUES (?,?,?,?,?, 'PRONTA', ?, 'revisão em lote', ?, 'agente', ?, ?, ?, 'AGENTE')""",
                (item["atribuicao"], item["alvo_id"], item["hash"], item["rotulo"],
                 f"(ato {item['ato_id']}; dossiê na pasta {pasta.name})", agora, agora,
                 r.get("modelo") or "agente", json.dumps(resultado, ensure_ascii=False),
                 sum(a["gravidade"] == "GRAVE" for a in resultado["achados"])))
            gravados += 1
    con.commit()
    return {"gravados": gravados, "repetidos": repetidos, "desconhecidos": desconhecidos}


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                   # noqa: BLE001
        pass
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("exportar")
    e.add_argument("--banco", required=True)
    e.add_argument("--saida", required=True)
    e.add_argument("--desde", default="2026-09-10")
    e.add_argument("--com-acervo", action="store_true")
    e.add_argument("--atribuicoes", default="RI,NOTAS,LIVRO3")
    e.add_argument("--com-mascara", action="store_true",
                   help="mascara nomes e números (o padrão é sem máscara: decisão do oficial, 06/10/2026)")
    i = sub.add_parser("importar")
    i.add_argument("--banco", required=True)
    i.add_argument("--pasta", required=True)
    a = p.parse_args(argv)
    if a.cmd == "exportar":
        con = sqlite3.connect(f"file:{a.banco}?mode=ro", uri=True)
        print(exportar(con, Path(a.saida), atribuicoes=a.atribuicoes.split(","),
                       desde=a.desde, com_acervo=a.com_acervo,
                       sem_mascara=False if a.com_mascara else None))
    else:
        con = sqlite3.connect(a.banco, timeout=60)
        print(importar(con, Path(a.pasta)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
