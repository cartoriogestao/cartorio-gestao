"""Tira do teor lavrado o marcador do selo que o sistema pos la por engano.

Pedido do oficial em 15/09/2026: «preciso que revise a averbacao da 3110, o
teor foi com espacamento no meio»; e depois, sobre a AV-04: «deixe o selo,
vamos arrumar o texto so e inserir o que precisas».

O QUE ACONTECEU. `ri_lavrar_teor.versao_final_para_lavrar` compunha, na
    lavratura, «teor + relacao de emolumentos + espaco reservado para o selo».
    O espaco reservado e um desenho tipografico:

        --- Espaco reservado para o selo digital do TJMA ---
        [ selo / verificacao ]                    [ QR / autenticacao ]
        (a relacao de emolumentos pode constar no carimbo do selo)

    Aqueles **vinte espacos** no meio da segunda linha foram o que o oficial
    viu no papel. O desenho previa que o carimbo de verdade entraria depois,
    «quando o aparelho responde» — mas **o teor congela na corrente de hash**:
    o marcador entrou e nao sai mais.

    Medido em 15/09: o teor gravado do ato 3737 (AV-04/3.110) tem **dez
    linhas**, e nove nao sao do ato; a minuta de onde ele saiu e o ato original
    tem **uma**. O defeito alcanca **1 ato** em todo o banco.

    A COMPOSICAO JA FOI DESLIGADA em `ri_web.ri_lavrar_ato`
    (`com_emolumentos=False, com_espaco_selo=False`), e o carimbo passou a ler
    a etiqueta inteira do razao, com QR. Este script e so para o ato que ja
    saiu com o marcador dentro.

POR QUE UM SCRIPT, E NAO UM CLIQUE NA TELA
    Isto **mexe no teor de um ato lavrado**, o que este projeto nunca faz: o
    teor e o que esta escrito no livro, e corrigir ato lavrado e materia de
    averbacao. A excecao e deliberada e vem do delegatario, e ela se sustenta
    num ponto: **o que sai nao e texto do ato** — e um marcador que o proprio
    sistema acrescentou depois de o oficial escrever, e que ele nunca pediu.

    Por ser excecao, o script **SO MEDE por padrao**, tira copia do banco antes
    de agir, e imprime o antes e o depois.

A CORRENTE DE HASH, E A UNICA RECUSA
    `hash_ato` cobre o teor. Limpar o teor muda o hash do ato — e o hash de um
    ato e o `hash_anterior` do seguinte. **Por isso o script recusa quando ha
    ato depois dele na mesma ficha**: refazer a corrente inteira seria
    reescrever a historia de todos, e nao consertar um.

    Quando o ato e o ultimo (ou o unico), refazer o hash dele nao alcanca
    ninguem — e o hash novo passa a provar o texto que de fato esta escrito,
    que e para isso que ele existe.

    **O SELO NAO ENTRA NO HASH** (`hash_ato` recebe numero da matricula, tipo,
    numero, data, teor e hash anterior), entao o selo comprado continua valendo
    e amarrado ao ato — que foi a decisao do oficial: «deixe o selo».

COMO USAR
    python tools/limpar_marcador_do_selo_no_teor.py "C:\\...\\cartorio_gestao.sqlite3"
    python tools/limpar_marcador_do_selo_no_teor.py "C:\\...\\o.sqlite3" --ato-id 3737 --confirmar

    Sem `--ato-id`, mostra todos os atos alcancados e nao muda nada.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))


def _atingidos(con: sqlite3.Connection) -> list[sqlite3.Row]:
    """Os atos cujo teor guarda o marcador. So le."""
    from ri_lavrar_teor import MARCA_EMOLUMENTOS, MARCA_SELO
    saida = []
    for a in con.execute("""SELECT a.*, m.numero AS ficha
                              FROM ri_atos a
                              JOIN ri_matriculas m ON m.id = a.matricula_id
                             ORDER BY a.id"""):
        teor = a["teor"] or ""
        if MARCA_SELO in teor or MARCA_EMOLUMENTOS in teor:
            saida.append(a)
    return saida


def _atos_depois(con: sqlite3.Connection, ato: sqlite3.Row) -> list[sqlite3.Row]:
    """Os atos que vem depois dele na mesma ficha. So le."""
    return list(con.execute(
        """SELECT id, tipo, numero FROM ri_atos
            WHERE matricula_id=? AND id>? ORDER BY id""",
        (int(ato["matricula_id"]), int(ato["id"]))))


def main() -> int:
    # O console do Windows e cp1252, e este script escreve portugues.
    for saida in (sys.stdout, sys.stderr):
        try:
            saida.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("banco", help="caminho do arquivo .sqlite3 do sistema")
    ap.add_argument("--ato-id", type=int, default=0,
                    help="id do ato a limpar; sem isto, so lista")
    ap.add_argument("--confirmar", action="store_true",
                    help="grava de verdade — sem isto, so mostra")
    args = ap.parse_args()

    caminho = Path(args.banco)
    if not caminho.is_file():
        print(f"Não achei o banco em: {caminho}", file=sys.stderr)
        return 1

    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    from ri_lavrar_teor import sem_fecho_antigo
    from ri_schema import hash_ato

    atingidos = _atingidos(con)
    print(f"=== Atos com o marcador do selo dentro do teor: {len(atingidos)} ===")
    for a in atingidos:
        depois = _atos_depois(con, a)
        print(f"  ato {a['id']} — {a['tipo']}-{a['numero']:02d} da ficha "
              f"{a['ficha']} — lavrado em {a['lavrado_em']}")
        print(f"     linhas no teor: {(a['teor'] or '').count(chr(10)) + 1} · "
              f"atos depois dele na ficha: {len(depois)}")
    if not atingidos:
        print("  (nenhum — nada a fazer)")
        con.close()
        return 0

    if not args.ato_id:
        print("\nNada foi mudado. Passe --ato-id <id> para escolher, e depois "
              "--confirmar para gravar.")
        con.close()
        return 0

    ato = con.execute("""SELECT a.*, m.numero AS ficha
                           FROM ri_atos a JOIN ri_matriculas m ON m.id=a.matricula_id
                          WHERE a.id=?""", (args.ato_id,)).fetchone()
    if not ato:
        print(f"Ato {args.ato_id} não encontrado.", file=sys.stderr)
        con.close()
        return 1

    limpo = sem_fecho_antigo(ato["teor"]).rstrip()
    if limpo == (ato["teor"] or "").rstrip():
        print(f"\nO ato {ato['id']} não tem marcador no teor. Nada a fazer.")
        con.close()
        return 0

    depois = _atos_depois(con, ato)
    if depois:
        rotulos = ", ".join(f"{d['tipo']}-{d['numero']:02d}" for d in depois)
        print(f"\nRECUSA: o ato {ato['id']} tem atos depois dele na ficha "
              f"({rotulos}).", file=sys.stderr)
        print("  O hash dele é o `hash_anterior` do seguinte; refazer a "
              "corrente inteira seria reescrever a história de todos, e não "
              "consertar um. O caminho aqui é a averbação.", file=sys.stderr)
        con.close()
        return 1

    novo_hash = hash_ato(ato["ficha"], ato["tipo"], ato["numero"],
                         ato["data_ato"], limpo, ato["hash_anterior"])

    print(f"\n=== O que sai do teor do ato {ato['id']} "
          f"({ato['tipo']}-{ato['numero']:02d} da ficha {ato['ficha']}) ===")
    for linha in (ato["teor"] or "").split("\n")[1:]:
        print(f"  - {linha!r}")
    print(f"\n  teor: {len(ato['teor'] or '')} → {len(limpo)} caracteres; "
          f"{(ato['teor'] or '').count(chr(10)) + 1} → "
          f"{limpo.count(chr(10)) + 1} linha(s)")
    print(f"  hash: {(ato['hash_ato'] or '')[:16]}… → {novo_hash[:16]}…")
    print(f"  selo: {ato['selo_texto'] or '—'}  (FICA — o selo não entra no hash)")

    if not args.confirmar:
        print("\nNada foi gravado — rode de novo com --confirmar.")
        con.close()
        return 0

    selo_da_hora = datetime.now().strftime("%Y%m%d-%H%M%S")  # noqa: DTZ005
    copia = caminho.with_suffix(f".antes-de-limpar-o-teor-{selo_da_hora}.sqlite3")
    # FORA DA PASTA DO BANCO — ordem do oficial em 11/10/2026.
    import pasta_das_copias as _PC
    copia = _PC.destino_da_copia(copia, Path(caminho))
    try:
        con.execute("VACUUM INTO ?", (str(copia),))
    except sqlite3.OperationalError:
        shutil.copy2(caminho, copia)
    print(f"\nCópia do banco guardada em:\n  {copia}")

    agora = datetime.now().isoformat(timespec="seconds")  # noqa: DTZ005
    with con:
        con.execute("UPDATE ri_atos SET teor=?, hash_ato=? WHERE id=?",
                    (limpo, novo_hash, int(ato["id"])))
        # O RASTRO FICA NO BANCO, e nao so nesta tela. Quem conferir a ficha
        # daqui a um ano precisa achar por que o hash daquele ato mudou.
        con.execute(
            """INSERT INTO audit_logs (ts, user_id, username_snapshot, action,
                   entity_type, entity_id, details)
               VALUES (?,?,?,?,?,?,?)""",
            (agora, None, "tools/limpar_marcador_do_selo_no_teor.py",
             "RI_ATO_TEOR_CORRIGIDO", "RI_ATO", int(ato["id"]),
             (f'{{"ficha": "{ato["ficha"]}", '
              f'"ato": "{ato["tipo"]}-{ato["numero"]:02d}", '
              f'"motivo": "marcador do selo que o sistema acrescentou na '
              f'lavratura, retirado por ordem do delegatario em '
              f'{agora[:10]}", '
              f'"hash_antes": "{ato["hash_ato"]}", '
              f'"hash_depois": "{novo_hash}"}}')))

    print(f"\nTeor do ato {ato['id']} limpo, e o hash refeito sobre o texto "
          f"que de fato está escrito.")
    print("O selo continua amarrado ao ato — ele não entra no hash.")
    print("O carimbo agora sai da etiqueta inteira do razão, com QR e com a "
          "relação de emolumentos, e não do marcador que estava no teor.")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
