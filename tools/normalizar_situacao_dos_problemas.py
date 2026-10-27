"""A PALAVRA FORA DO VOCABULÁRIO NA LISTA DE PROBLEMAS — só mede, por padrão.

Nascido do relato #82, em 17/09/2026. A lista da ajuda conhece três situações —
`ABERTO`, `RELATADO` e `RESOLVIDO` —, e uma linha gravada com outra palavra não
é nenhuma delas: ela não aparece em vista nenhuma, e as duas vistas que existem
(a dos abertos e a dos resolvidos) se recusam a afirmar o que ela é.

Medido na produção em 17/09/2026: **uma** linha assim nos **83** problemas — o
`#77`, gravado `FECHADO` por fora do sistema (a trilha de auditoria não tem
nenhuma mudança de situação dele). A palavra **não é inválida por acaso**: quem
a escreveu queria dizer «resolvido», e é isso que o sinônimo abaixo declara.

O QUE ESTE SCRIPT CONSERTA, E O QUE ELE RECUSA CONSERTAR:

  * só a PALAVRA muda, e só quando ela está no mapa de sinônimos declarados.
    A nota, o `fechado_em` e o `fechado_por` ficam: são fato do passado, e fato
    do passado não se regrava — é a régua do `COALESCE` de `fechar`.
  * palavra que o mapa não conhece **não é adivinhada**. Converter
    `PENDENTE` em `RESOLVIDO` esconderia um problema em aberto; converter em
    `ABERTO` mostraria ao balcão um defeito que talvez já esteja consertado.
    Nos dois casos quem sabe é quem escreveu, e o caminho é a tela — vista
    «Todos», onde a linha torta aparece com o aviso de que a palavra está fora
    do vocabulário. O script diz o número de cada uma e para.

  * o `WHERE` leva o valor antigo junto: este script não toca em linha que já
    esteja certa, mesmo que a lista mude entre a medição e a escrita.
  * a mudança vai para a auditoria. A rota faz isso sozinha; quem escreve por
    fora dela precisa fazer à mão, senão o rastro fica com um buraco
    exatamente onde alguém mexeu na mão.

Sem `--confirmar` ele não escreve nada: mede, mostra o antes e o depois que
teria, e para. Com `--confirmar` tira uma cópia do banco (`VACUUM INTO`) antes
de escrever.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

# A RÉGUA É A DO MÓDULO, e não uma lista escrita aqui: duas listas de situações
# divergiriam no dia em que a quarta nascesse, e a que ficasse velha seria esta.
import ajuda_problemas as AP  # noqa: E402
import banco_pg  # noqa: E402
import identidade_do_robo as IDR  # noqa: E402
from bd_nativo import banco  # noqa: E402

for saida in (sys.stdout, sys.stderr):
    try:
        saida.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

BANCO = Path(r"C:\ProgramData\CartorioGestao\cartorio_gestao.sqlite3")
PASTA_DAS_COPIAS = Path(r"C:\ProgramData\CartorioGestao\backups")

# PALAVRA ESCRITA À MÃO -> PALAVRA DO VOCABULÁRIO. Só entra aqui o que foi
# medido: `FECHADO` foi escrita por quem queria dizer «resolvido», e é o que a
# família inteira da tela diz (`FECHAR`, `fechado_em`, `fechado_por`).
SINONIMOS: dict[str, str] = {"FECHADO": "RESOLVIDO"}


def _fora_do_vocabulario(bd) -> list[dict]:
    marcadores = ",".join(["%s"] * len(AP.SITUACOES))
    return bd.ler(
        f"""SELECT id, situacao, substr(COALESCE(fechado_em,''),1,16) AS fechado_em,
                   COALESCE(fechado_por,'') AS fechado_por,
                   COALESCE(fechado_nota,'') AS fechado_nota
              FROM aj_problemas
             WHERE COALESCE(situacao,'') NOT IN ({marcadores})
             ORDER BY id""", tuple(AP.SITUACOES))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--confirmar", action="store_true",
                    help="escreve no banco (sem isto, só mede)")
    args = ap.parse_args()

    if not BANCO.exists():
        print(f"o banco não está em {BANCO}", file=sys.stderr)
        return 1

    con = banco_pg.conectar(str(BANCO))
    bd = banco(con)
    print(f"medido em {datetime.now():%d/%m/%Y às %H:%M:%S}")  # noqa: DTZ005
    print(f"banco: {BANCO}")
    print(f"o vocabulário que a lista conhece: {', '.join(AP.SITUACOES)}")

    linhas = _fora_do_vocabulario(bd)
    if not linhas:
        print("\nNenhuma linha fora do vocabulário — nada a fazer.")
        con.close()
        return 0

    elegiveis, desconhecidas = [], []
    for linha in linhas:
        (elegiveis if linha["situacao"] in SINONIMOS else desconhecidas).append(linha)

    print(f"\n=== as linhas que a lista não mostra em vista nenhuma: {len(linhas)} ===")
    for linha in linhas:
        destino = SINONIMOS.get(linha["situacao"])
        print(f"\n   #{linha['id']}  situacao={linha['situacao']!r}"
              + (f"  ->  {destino!r}" if destino else "  ->  ? (sem sinônimo)"))
        print(f"      fechado_em  {linha['fechado_em'] or '—'}"
              f"   por  {linha['fechado_por'] or '—'}")
        nota = linha["fechado_nota"].replace("\n", " ")
        print(f"      nota  {nota[:120] or '—'}"
              + ("..." if len(nota) > 120 else ""))

    if desconhecidas:
        print("\nRECUSA: estas palavras eu não conheço, e adivinhar esconderia "
              "problema —", file=sys.stderr)
        print("  " + ", ".join(f"#{l['id']} {l['situacao']!r}"
                               for l in desconhecidas), file=sys.stderr)
        print("classifique cada uma na tela (vista «Todos», onde a linha "
              "aparece com o aviso),", file=sys.stderr)
        print("e rode este script de novo — ele não toca nelas.",
              file=sys.stderr)
        if not elegiveis:
            con.close()
            return 1

    if not args.confirmar:
        print(f"\nSÓ MEDI — {len(elegiveis)} linha(s) mudariam de palavra, e "
              f"nada mais seria tocado.")
        print("para escrever, rode de novo com --confirmar.")
        con.close()
        return 0

    PASTA_DAS_COPIAS.mkdir(parents=True, exist_ok=True)
    copia = PASTA_DAS_COPIAS / (
        f"cartorio_gestao_antes_da_situacao_fora_do_vocabulario_"
        f"{datetime.now():%Y%m%d_%H%M%S}.sqlite3")  # noqa: DTZ005
    # FORA DA PASTA DO BANCO — ordem do oficial em 11/10/2026.
    import pasta_das_copias as _PC
    copia = _PC.destino_da_copia(copia, Path(BANCO))
    banco_pg.copiar_para_arquivo(BANCO, copia)
    print(f"\ncópia do banco: {copia}")

    agora = datetime.now().isoformat(timespec="seconds")  # noqa: DTZ005
    with con:
        for linha in elegiveis:
            destino = SINONIMOS[linha["situacao"]]
            bd.escrever("UPDATE aj_problemas SET situacao=%s WHERE id=%s AND situacao=%s",
                        (destino, int(linha["id"]), linha["situacao"]))
            # A MESMA SERIALIZAÇÃO DE `db.log` (`json.dumps`, `ensure_ascii=False`),
            # e o `acao` dizendo o que a rota não tem como dizer: a rota grava
            # `fechar` e `reabrir`; esta mudança foi a palavra, e só ela.
            # Quem grava por programa diz quem e e a mando de quem (26/10/2026).
            IDR.registrar(
                bd, ts=agora, user_id=None,
                username="tools/normalizar_situacao_dos_problemas.py",
                action="AJUDA_PROBLEMA_SITUACAO", entity_type="aj_problemas",
                entity_id=int(linha["id"]),
                details=json.dumps({"acao": "normalizar",
                                    "de": linha["situacao"], "para": destino,
                                    "nota": "palavra fora do vocabulário da lista, "
                                            "escrita por fora do sistema; a nota e o "
                                            "carimbo de fechamento ficaram como estavam"},
                                   ensure_ascii=False),
                agente="tools/normalizar_situacao_dos_problemas.py",
                a_mando_de=IDR.PELO_RESPONSAVEL)

    print("\n=== como ficaram ===")
    for linha in elegiveis:
        depois = bd.um("SELECT id, situacao, fechado_em, fechado_por, "
                       "fechado_nota FROM aj_problemas WHERE id=%s",
                       (int(linha["id"]),))
        print(f"   #{depois['id']}  {linha['situacao']!r} -> {depois['situacao']!r}"
              f"   fechado_em {depois['fechado_em'] or '—'}"
              f"   por {depois['fechado_por'] or '—'}")
    print("\nAs notas e os carimbos de fechamento não foram tocados.")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
