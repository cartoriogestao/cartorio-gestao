"""Troca a chave da CENPROT pela que a CENTRAL JA USA, nos titulos da lista.

POR QUE EXISTE (PR006, 25/11/2026): a listagem da Consulta de Titulos do portal
mostrou titulos do acervo do E-Oficio protestados na Central com OUTRA chave.
A nossa foi composta pelo E-Oficio e nunca foi a da Central; quem procura por
ela nao acha o titulo. A decisao de gravar a da Central e do oficial, e a lista
e a que ele aprovou.

O ARQUIVO e um CSV com `;` e cabecalho, com pelo menos as colunas `titulo_id`,
`chave_atual` (a gravada hoje; vazia se nao ha) e `chave_central`. Colunas a
mais sao ignoradas. Fica FORA do repositorio: e dado da casa.

So SIMULA por padrao: roda a troca inteira dentro de uma transacao, com todas
as guardas de `protesto_cenprot.trocar_pela_chave_da_central`, e desfaz. Com
`--gravar`, tira antes a copia do banco, grava, e deixa uma linha de auditoria
por titulo (agente: esta ferramenta, a mando do oficial).

Nada aqui envia coisa alguma para a Central.

    python tools/trocar_chave_pela_da_central.py --banco <banco> --arquivo lista.csv
    python tools/trocar_chave_pela_da_central.py --banco <banco> --arquivo lista.csv \\
        --gravar --usuario superusuario --a-mando-de <login do oficial>
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import banco_pg  # noqa: E402
import identidade_do_robo as IDR  # noqa: E402
import protesto_cenprot as PC  # noqa: E402
from bd_nativo import banco as abrir_banco  # noqa: E402

AGENTE = "troca pela chave da Central (tools/trocar_chave_pela_da_central.py)"
COLUNAS = ("titulo_id", "chave_atual", "chave_central")


def ler_pares(caminho) -> list[dict]:
    """Os pares do CSV. Recusa o arquivo sem as tres colunas."""
    with open(caminho, newline="", encoding="utf-8-sig") as f:
        leitor = csv.DictReader(f, delimiter=";")
        faltam = [c for c in COLUNAS if c not in (leitor.fieldnames or [])]
        if faltam:
            raise SystemExit(f"O arquivo nao tem a(s) coluna(s) {', '.join(faltam)}.")
        return [{c: (linha.get(c) or "").strip() for c in COLUNAS}
                for linha in leitor if (linha.get("titulo_id") or "").strip()]


def _quem(bd, login: str) -> dict:
    quem = bd.um("SELECT id, username FROM users WHERE username = %s", (login,))
    if not quem:
        raise SystemExit(f"Nao ha usuario `{login}` neste banco.")
    return quem


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--banco", required=True)
    ap.add_argument("--arquivo", required=True, help="CSV com os pares aprovados")
    ap.add_argument("--gravar", action="store_true")
    ap.add_argument("--usuario", default="superusuario",
                    help="a conta que grava (padrao: superusuario)")
    ap.add_argument("--a-mando-de", default="", help="o login do oficial que aprovou")
    a = ap.parse_args(argv)
    if a.gravar and not a.a_mando_de.strip():
        ap.error("--gravar exige --a-mando-de: a troca e decisao do oficial")
    pares = ler_pares(a.arquivo)
    print(f"{len(pares)} par(es) no arquivo.")

    if a.gravar:
        from pasta_das_copias import destino_da_copia
        banco = Path(a.banco)
        copia = destino_da_copia(
            Path(f"antes_troca_chave_central_{datetime.now():%Y%m%d_%H%M%S}.sqlite3"), banco)
        banco_pg.copiar_para_arquivo(banco, copia)
        if not copia.is_file() or copia.stat().st_size == 0:
            raise SystemExit(f"A copia do banco nao saiu ({copia}); nada foi gravado.")
        print("copia do banco:", copia)

    con = banco_pg.conectar(a.banco, timeout=60)
    try:
        bd = abrir_banco(con)
        quem = _quem(bd, a.usuario) if a.gravar else None
        trocados = PC.trocar_pela_chave_da_central(con, pares)
        if not a.gravar:
            con.rollback()
            print(f"SIMULACAO: os {len(trocados)} passariam em todas as guardas; "
                  "nada foi gravado (use --gravar).")
            return 0
        agora = datetime.now().isoformat(timespec="seconds")
        for t in trocados:
            IDR.registrar(bd, ts=agora, user_id=quem["id"], username=quem["username"],
                          action="PROTESTO_CHAVE_DA_CENTRAL", entity_type="pt_titulos",
                          entity_id=t["titulo_id"],
                          details=json.dumps({"antes": t["chave_atual"],
                                              "depois": t["chave_central"]}),
                          agente=AGENTE, a_mando_de=a.a_mando_de.strip())
        con.commit()
        print(f"{len(trocados)} chave(s) trocada(s).")
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
