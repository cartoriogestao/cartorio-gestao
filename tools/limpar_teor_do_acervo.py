"""Tira do teor o ruído que a importação do E-Ofício deixou — só isso.

Pedido do oficial em 15/09/2026: «o teor da averbacao e da ficha da 3110 segue
cheio de espacos, um modelo que diz conferencia, nada como preparado antes»; e
depois, vendo o PDF do resultado: «joia».

O QUE SAI, e cada um foi medido na 3.110 antes de a régua ser escrita:

    'conferida'                  ← a palavra solta do mutirão de conferência
    'MATRICULA: 3.110 '          ← a ficha já imprime isso no cabeçalho
    'LIVRO: 2-Q fls. 168'        ← idem
    'DATA: 13-08-2009'           ← idem
    '.-.-.-.-.-.-.-…'            ← separador do E-Ofício; o sistema desenha o seu
    'n°9428).   DATA:'           ← espaço repetido entre palavras

    Na ficha da 3.110 são **oito linhas e quatro trechos**: 7.406 → 6.967
    caracteres, 12 → 4 linhas.

O QUE NÃO SE ENCOSTA
    **Nenhuma palavra do ato.** Não se reescreve frase, não se corrige
    ortografia, não se mexe em número, nome, data nem valor. O teor é o que
    está escrito no livro; o que sai daqui é ruído de importação.

    O recuo do começo da linha fica: em teor de acervo ele às vezes separa um
    bloco do outro, e tirá-lo mudaria a cara do texto sem pedido.

A CORRENTE DE HASH, E A DIFERENÇA ENTRE A FICHA E O ATO
    `ri_matriculas.teor` **não entra em hash nenhum** — o teor da ficha é
    cadastro, e limpá-lo não toca em prova de integridade.

    `ri_atos.teor` **entra**: `hash_ato` o recebe. Por isso, ao limpar um ATO,
    o hash é refeito, e **só quando ele é o último da ficha** — o hash de um é
    o `hash_anterior` do seguinte, e refazer a corrente inteira seria
    reescrever a história de todos. É a mesma recusa de
    `limpar_marcador_do_selo_no_teor.py`.

COMO USAR
    python tools/limpar_teor_do_acervo.py "C:\\...\\o.sqlite3" --matricula 3110
    python tools/limpar_teor_do_acervo.py "C:\\...\\o.sqlite3" --matricula 3110 --confirmar

    Sem `--confirmar` ele mostra, linha por linha, o que sairia — e nada mais.
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

import banco_pg  # noqa: E402
from bd_nativo import banco  # noqa: E402


def _atos_depois(bd, matricula_id: int, ato_id: int) -> list[dict]:
    return bd.ler(
        """SELECT id, tipo, numero FROM ri_atos
            WHERE matricula_id=%s AND id>%s ORDER BY id""",
        (int(matricula_id), int(ato_id)))


def main() -> int:
    for saida in (sys.stdout, sys.stderr):
        try:
            saida.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("banco")
    ap.add_argument("--matricula", required=True,
                    help="número da matrícula, como está no livro")
    ap.add_argument("--so-a-ficha", action="store_true",
                    help="não mexe nos atos, só no teor da ficha")
    ap.add_argument("--confirmar", action="store_true",
                    help="grava de verdade — sem isto, só mostra")
    args = ap.parse_args()

    caminho = Path(args.banco)
    if not caminho.is_file():
        print(f"Não achei o banco em: {caminho}", file=sys.stderr)
        return 1

    import ri_teor_limpo as LIMPO
    from ri_lavrar_teor import sem_fecho_antigo
    from ri_schema import hash_ato

    def limpar_ato(teor):
        """O ruído da importação **e** o marcador do selo, num passo só.

        São duas sujeiras de origens diferentes no mesmo teor: o `conferida`
        e os separadores vieram do E-Ofício; o bloco «--- Espaco reservado
        para o selo digital do TJMA ---», com `[ selo / verificacao ]` e vinte
        espaços, foi o **próprio sistema** que escreveu na lavratura, e o teor
        congela na corrente de hash.

        Juntar aqui é para o oficial rodar UM comando, e não dois, sobre a
        mesma ficha. `limpar_marcador_do_selo_no_teor.py` continua existindo
        para quem quiser só o marcador.
        """
        return LIMPO.limpar(sem_fecho_antigo(teor))

    con = banco_pg.conectar(caminho)
    bd = banco(con)
    m = bd.um("SELECT * FROM ri_matriculas WHERE numero=%s",
              (str(args.matricula).strip(),))
    if not m:
        print(f"Matrícula {args.matricula} não encontrada.", file=sys.stderr)
        con.close()
        return 1

    print(f"=== Matrícula {m['numero']}, Livro {m['livro']} (id={m['id']}) ===\n")

    planos: list[dict] = []

    # ---------------------------------------------------------- a ficha
    limpo = LIMPO.limpar(m["teor"])
    fora = LIMPO.o_que_sai(m["teor"])
    if fora and limpo != (m["teor"] or "").strip():
        print(f"--- TEOR DA FICHA: {len(m['teor'] or '')} → {len(limpo)} "
              f"caracteres, {(m['teor'] or '').count(chr(10)) + 1} → "
              f"{limpo.count(chr(10)) + 1} linha(s) ---")
        for n, linha, motivo in fora:
            print(f"  linha {n:3}  [{motivo}]")
            print(f"             {linha[:88]!r}")
        planos.append({"o_que": "ficha", "id": int(m["id"]), "teor": limpo})
        print()
    else:
        print("--- TEOR DA FICHA: nada a tirar ---\n")

    # ------------------------------------------------------------ os atos
    if not args.so_a_ficha:
        for a in bd.ler("""SELECT * FROM ri_atos WHERE matricula_id=%s
                          ORDER BY id""", (m["id"],)):
            novo = limpar_ato(a["teor"])
            saiu = LIMPO.o_que_sai(a["teor"])
            marcador = novo != LIMPO.limpar(a["teor"])
            if novo == (a["teor"] or "").strip():
                continue
            rotulo = f"{a['tipo']}-{a['numero']:02d}"
            print(f"--- {rotulo} (ato {a['id']}): "
                  f"{len(a['teor'] or '')} → {len(novo)} caracteres ---")
            for n, linha, motivo in saiu:
                print(f"  linha {n:3}  [{motivo}]")
                print(f"             {linha[:88]!r}")
            if marcador:
                print("  e o bloco «Espaco reservado para o selo digital do "
                      "TJMA», que o sistema escreveu na lavratura")
            depois = _atos_depois(bd, m["id"], a["id"])
            if depois:
                nomes = ", ".join(f"{d['tipo']}-{d['numero']:02d}"
                                  for d in depois)
                print(f"  RECUSA: há ato depois dele na ficha ({nomes}). O "
                      f"hash deste é o `hash_anterior` do seguinte, e refazer "
                      f"a corrente inteira seria reescrever a história de "
                      f"todos.")
                print()
                continue
            h = hash_ato(m["numero"], a["tipo"], a["numero"], a["data_ato"],
                         novo, a["hash_anterior"])
            print(f"  hash: {(a['hash_ato'] or '')[:16]}… → {h[:16]}…")
            print(f"  selo: {a['selo_texto'] or '—'}  (FICA — não entra no hash)")
            planos.append({"o_que": rotulo, "id": int(a["id"]),
                           "teor": novo, "hash": h,
                           "lido": (a["teor"], a["hash_ato"])})
            print()

    if not planos:
        print("Nada a fazer.")
        con.close()
        return 0

    if not args.confirmar:
        print(f"Nada foi gravado — rode de novo com --confirmar. "
              f"({len(planos)} alteração(ões) prontas.)")
        con.close()
        return 0

    selo_da_hora = datetime.now().strftime("%Y%m%d-%H%M%S")  # noqa: DTZ005
    copia = caminho.with_suffix(f".antes-de-limpar-o-teor-{selo_da_hora}.sqlite3")
    # FORA DA PASTA DO BANCO — ordem do oficial em 11/10/2026.
    import pasta_das_copias as _PC
    copia = _PC.destino_da_copia(copia, Path(caminho))
    try:
        banco_pg.copiar_para_arquivo(caminho, copia)
    except sqlite3.OperationalError:
        shutil.copy2(caminho, copia)
    print(f"Cópia do banco guardada em:\n  {copia}\n")

    agora = datetime.now().isoformat(timespec="seconds")  # noqa: DTZ005
    with con:
        # A RECUSA SE CONFERE DE NOVO, DENTRO DA TRAVA DA LAVRATURA
        # (`ri_atos.numero`, a de `ri_web`). A conferência lá de cima veio antes
        # da cópia do banco; um ato lavrado depois deste na ficha, nesse
        # meio-tempo, ficaria com o `hash_anterior` do hash que se troca aqui.
        bd.travar("ri_atos.numero")
        for plano in planos:
            if plano["o_que"] == "ficha":
                continue
            relido = bd.um("SELECT teor, hash_ato FROM ri_atos WHERE id=%s FOR UPDATE",
                           (plano["id"],))
            if (_atos_depois(bd, m["id"], plano["id"]) or not relido
                    or (relido["teor"], relido["hash_ato"]) != plano["lido"]):
                print(f"RECUSA: o {plano['o_que']} (ato {plano['id']}) mudou, ou "
                      f"ganhou ato depois dele na ficha, enquanto a cópia era "
                      f"tirada. Nada foi gravado — rode de novo para ver como "
                      f"ficou.", file=sys.stderr)
                con.close()
                return 1
        for plano in planos:
            if plano["o_que"] == "ficha":
                bd.escrever("UPDATE ri_matriculas SET teor=%s WHERE id=%s",
                            (plano["teor"], plano["id"]))
            else:
                bd.escrever("UPDATE ri_atos SET teor=%s, hash_ato=%s WHERE id=%s",
                            (plano["teor"], plano["hash"], plano["id"]))
            # O RASTRO FICA NO BANCO. Quem conferir a ficha daqui a um ano
            # precisa achar por que o texto — e o hash — mudaram.
            bd.escrever(
                """INSERT INTO audit_logs (ts, user_id, username_snapshot,
                       action, entity_type, entity_id, details)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (agora, None, "tools/limpar_teor_do_acervo.py",
                 "RI_TEOR_LIMPO",
                 "RI_MATRICULA" if plano["o_que"] == "ficha" else "RI_ATO",
                 plano["id"],
                 (f'{{"ficha": "{m["numero"]}", "onde": "{plano["o_que"]}", '
                  f'"motivo": "ruido da importacao do E-Oficio (palavra de '
                  f'conferencia, cabecalho repetido, separador e espaco '
                  f'dobrado), retirado por ordem do delegatario em '
                  f'{agora[:10]}"}}')))

    print(f"{len(planos)} teor(es) limpo(s). Nenhuma palavra do ato foi "
          f"reescrita — saiu só o ruído da importação.")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
