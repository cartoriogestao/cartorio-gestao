"""A NATURALIDADE QUE ESTAVA NO ASSENTO E FALTAVA NA PESSOA.

O DEFEITO, medido em 22/09/2026
    A CRC reteve **19 dos 47** nascimentos pendentes, e **17 pelo mesmo
    motivo**: «o município de nascimento do registrado não está na ficha». Só
    que estava — no campo do **ASSENTO** (`naturalidade_declarada`), e a carga
    lê o da **PESSOA** (`rc_pessoas.naturalidade_cidade`).

    Dois campos para a mesma coisa, e o balcão preenchia um. Conferido nos 19:
    **todos** têm a naturalidade escrita no assento e **nenhum** tem o campo da
    pessoa. E não é lote antigo — eles entraram um por dia, de 16 a 22/09, pelo
    caminho do teor colado: **todo assento novo saía retido**.

O QUE ESTE SCRIPT FAZ, E O QUE ELE RECUSA
    Ele chama **a mesma função que a tela passou a chamar** —
    `rc_assento._naturalidade_do_titular` —, e não uma cópia parecida: duas
    leituras da naturalidade divergiriam no primeiro conserto, e o que este
    script gravasse deixaria de ser o que o balcão grava.

    Por isso ele herda as três recusas dela, e cada uma fica declarada:

      - **município que o cadastro do IBGE não confirma** não é gravado.
        `ibge_geracao.lugar` recusa escolher município parecido, e é essa
        recusa que faz a derivação ser defensável — o campo sobe para uma
        Central nacional;
      - **pessoa que já tem naturalidade** não é tocada: campo preenchido é
        resposta de gente, e derivar por cima apagaria a correção dela;
      - **assento sem a pessoa titular** (nascimento sem REGISTRADO, óbito sem
        FALECIDO) fica de fora.

    **Só mede por padrão.** Com `--confirmar` tira cópia do banco
    (`VACUUM INTO`) antes de tocar em nada e grava a auditoria à mão, porque a
    rota não foi usada. **Rodar duas vezes dá o mesmo resultado**: a segunda
    rodada encontra as pessoas já preenchidas e as recusa.

O QUE ELE NÃO RESOLVE, E FICA DITO
    Dois dos 19 têm defeito próprio, que nenhum script conserta porque a
    resposta está no livro de papel: o termo **2948** tem data de nascimento
    posterior à do registro, e o **16062** tem o ano da matrícula (2006)
    diferente do ano do registro (2007).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import rc_assento as RC  # noqa: E402

# As espécies cujo termo declara naturalidade — as mesmas de
# `rc_assento.TITULAR_DA_NATURALIDADE`, lidas de lá e não reescritas.
ESPECIES = tuple(RC.TITULAR_DA_NATURALIDADE)


def _candidatos(con: sqlite3.Connection) -> list[sqlite3.Row]:
    """Assentos com naturalidade escrita no termo. **SÓ LÊ.**

    Quem decide se dá para gravar é `_naturalidade_do_titular`; aqui só se
    junta o que vale a pena perguntar a ela.
    """
    marcas = ", ".join("?" for _ in ESPECIES)
    return con.execute(
        f"""SELECT id, especie, numero, nome, naturalidade_declarada
            FROM rc_assentos
            WHERE especie IN ({marcas})
              AND TRIM(COALESCE(naturalidade_declarada, '')) <> ''
            ORDER BY id""", ESPECIES).fetchall()


def medir(banco: Path) -> dict:
    """Diz o que mudaria, **sem escrever**.

    Roda a derivação numa transação que é **desfeita no fim**: é a única forma
    de medir com a mesma função que grava, em vez de uma leitura parecida que
    diria outra coisa na hora de valer.
    """
    con = sqlite3.connect(str(banco))
    con.row_factory = sqlite3.Row
    try:
        con.execute("BEGIN")
        a_gravar, recusados = [], []
        for a in _candidatos(con):
            r = RC._naturalidade_do_titular(
                con, int(a["id"]), str(a["especie"] or "").upper(),
                a["naturalidade_declarada"])
            registro = {
                "assento_id": int(a["id"]), "especie": a["especie"],
                "numero": a["numero"], "nome": a["nome"],
                "declarada": a["naturalidade_declarada"],
                "cidade": r.get("cidade"), "uf": r.get("uf"),
            }
            if r.get("gravou"):
                a_gravar.append(registro)
            else:
                recusados.append({**registro, "motivo": r.get("motivo")})
        con.rollback()
        return {"a_gravar": a_gravar, "recusados": recusados}
    finally:
        con.close()


def aplicar(banco: Path) -> tuple[Path, list[dict]]:
    """Grava de verdade. Tira cópia do banco antes."""
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    copia = banco.with_name(
        f"{banco.stem}.antes-da-naturalidade-{carimbo}{banco.suffix}")
    # FORA DA PASTA DO BANCO — ordem do oficial em 11/10/2026.
    import pasta_das_copias as _PC
    copia = _PC.destino_da_copia(copia, Path(banco))
    con = sqlite3.connect(str(banco))
    con.row_factory = sqlite3.Row
    gravados: list[dict] = []
    try:
        con.execute("PRAGMA busy_timeout=15000")
        con.execute("VACUUM INTO ?", (str(copia),))
        con.execute("BEGIN IMMEDIATE")
        for a in _candidatos(con):
            r = RC._naturalidade_do_titular(
                con, int(a["id"]), str(a["especie"] or "").upper(),
                a["naturalidade_declarada"])
            if r.get("gravou"):
                gravados.append({"assento_id": int(a["id"]),
                                 "numero": a["numero"], "nome": a["nome"],
                                 "cidade": r.get("cidade"), "uf": r.get("uf")})
        con.commit()
        # A AUDITORIA À MÃO, porque a rota não foi usada.
        con.execute("BEGIN IMMEDIATE")
        for g in gravados:
            con.execute(
                """INSERT INTO audit_logs(ts, user_id, username_snapshot,
                                          action, entity_type, entity_id,
                                          details)
                   VALUES (?,?,?,?,?,?,?)""",
                (datetime.now().isoformat(timespec="seconds"), None,
                 "naturalidade_dos_assentos_do_rcpn",
                 "RCPN_NATURALIDADE_DERIVADA", "rc_assentos",
                 g["assento_id"], json.dumps(g, ensure_ascii=False)))
        con.commit()
    finally:
        con.close()
    return copia, gravados


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--banco",
                   default=r"C:\ProgramData\CartorioGestao\cartorio_gestao.sqlite3")
    p.add_argument("--confirmar", action="store_true",
                   help="grava. Sem isto, o script apenas mede.")
    args = p.parse_args()

    m = medir(Path(args.banco))
    print(f"assentos a preencher ... {len(m['a_gravar'])}")
    print(f"deixados de fora ....... {len(m['recusados'])}")
    print()
    for g in m["a_gravar"][:40]:
        print(f"   nº {str(g['numero']):<7} {(g['nome'] or '')[:30]:<30} "
              f"«{g['declarada']}» -> {g['cidade']}/{g['uf']}")
    if len(m["a_gravar"]) > 40:
        print(f"   ... e mais {len(m['a_gravar']) - 40}")
    print()
    motivos: dict[str, int] = {}
    for r in m["recusados"]:
        motivos[r["motivo"]] = motivos.get(r["motivo"], 0) + 1
    for motivo, n in sorted(motivos.items(), key=lambda x: -x[1]):
        print(f"   {n:>4}x deixado de fora: {motivo}")
    for r in m["recusados"]:
        if r["motivo"] == "o município não está no cadastro do IBGE":
            print(f"        -> nº {r['numero']}: «{r['declarada']}» "
                  f"lido como «{r['cidade']}/{r['uf']}»")

    if not args.confirmar:
        print("\nNADA FOI ALTERADO. Rode de novo com --confirmar para gravar.")
        return 0
    if not m["a_gravar"]:
        print("\nNao ha o que preencher.")
        return 0
    copia, gravados = aplicar(Path(args.banco))
    print(f"\nGRAVADO: {len(gravados)} assento(s).")
    print(f"Copia do banco antes da mudanca: {copia}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
