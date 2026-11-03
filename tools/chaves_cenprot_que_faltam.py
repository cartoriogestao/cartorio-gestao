"""Os titulos do Protesto SEM CHAVE DA CENPROT: por que, e o que se faria.

So SIMULA por padrao: lista cada titulo sem chave, a categoria
(`protesto_cenprot.chaves_que_faltam`) e a chave que levaria, e nao grava nada.
Grava SO com `--gravar --ids 1,2,3`, e so nos titulos `calcular` ou
`copiar_do_irmao` daqueles ids - a lista que o oficial aprovou.

Com `--xml ARQUIVO` confere tambem o XML baixado da Central
(`protesto_cenprot.conferir`, que so le): diz quais chaves dele entrariam nos
titulos sem chave. Para gravar as do XML, use a tela do CENPROT.

Nada aqui envia coisa alguma para a Central.

    python tools/chaves_cenprot_que_faltam.py                    (simula)
    python tools/chaves_cenprot_que_faltam.py --csv saida.csv    (simula e salva)
    python tools/chaves_cenprot_que_faltam.py --xml arquivo.xml  (simula + XML)
    python tools/chaves_cenprot_que_faltam.py --gravar --ids 12,34
"""
from __future__ import annotations

import argparse
import collections
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import banco_pg  # noqa: E402
import protesto_cenprot as PC  # noqa: E402

BANCO_PRODUCAO = r"C:\ProgramData\CartorioGestao\cartorio_gestao.sqlite3"
COLUNAS = ("id", "origem", "situacao", "protocolo", "apontado_em", "categoria",
           "chave_proposta", "motivo")


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--banco", default=BANCO_PRODUCAO)
    ap.add_argument("--csv", help="salva a lista neste arquivo")
    ap.add_argument("--xml", help="XML baixado da Central, so para conferir")
    ap.add_argument("--gravar", action="store_true")
    ap.add_argument("--ids", default="", help="ids separados por virgula")
    a = ap.parse_args(argv)
    ids = [int(x) for x in a.ids.replace(" ", "").split(",") if x]
    if a.gravar and not ids:
        ap.error("--gravar exige --ids: so se grava o que o oficial aprovou")

    con = banco_pg.conectar(a.banco, timeout=30)
    try:
        lista = PC.chaves_que_faltam(con)
        por = collections.Counter(linha["categoria"] for linha in lista)
        print(f"{len(lista)} titulo(s) sem chave da CENPROT.")
        for categoria, n in sorted(por.items()):
            print(f"  {categoria}: {n}")
        for linha in lista:
            if linha["categoria"] in ("calcular", "copiar_do_irmao",
                                      "decisao_do_oficial"):
                print("  #{id} {origem} {situacao} protocolo {protocolo}: "
                      "{categoria} -> {chave_proposta} ({motivo})".format(**linha))
        if a.csv:
            with open(a.csv, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, COLUNAS, extrasaction="ignore", delimiter=";")
                w.writeheader()
                w.writerows(lista)
            print(f"Lista salva em {a.csv}.")
        if a.xml:
            casa = PC.identidade_da_casa(PC._configuracao_da_casa(PC.banco(con)))
            r = PC.conferir(con, Path(a.xml).read_bytes(), comarca=casa["comarca"],
                            cartorio=casa["cartorio"])
            print(f"XML: {len(r['entram'])} chave(s) entrariam, "
                  f"{len(r['ja_tem'])} ja estao, {len(r['divergem'])} divergem, "
                  f"{len(r['fora'])} nao casam.")
        if a.gravar:
            gravados = PC.gravar_chaves_que_faltam(con, ids)
            con.commit()
            for g in gravados:
                print(f"  #{g['id']}: gravada {g['chave_gravada']}")
            print(f"{len(gravados)} chave(s) gravada(s).")
        else:
            con.rollback()
            print("SIMULACAO: nada foi gravado (use --gravar --ids ...).")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
