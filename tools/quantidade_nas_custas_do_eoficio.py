"""A QUANTIDADE QUE NUNCA MULTIPLICOU NAS CUSTAS VINDAS DO E-OFICIO.

O DEFEITO, medido em 21/09/2026 no banco do balcao
    `cx_protocolo_atos.valor_total` quer dizer duas coisas conforme a origem da
    linha. O balcao, ao acrescentar um item a mao, grava **quantidade x
    unitario**; a carga do E-Oficio gravava o **unitario**, com a quantidade ao
    lado sem efeito nenhum.

    | | |
    |---|---|
    | itens vindos do E-Oficio | **32.393** |
    | deles com quantidade maior que 1 | **7.483** |
    | o que a soma do protocolo deixa de contar | **R$ 643.694,38** |
    | desses itens ja' quitados | **2** |

    O caso mais claro e' o `16.39`, que a tabela chama de «arquivamento, **por
    folha** do documento»: um protocolo com 128 folhas somava R$ 5,92.

POR QUE E' A CARGA QUE ESTAVA ERRADA, E NAO A COLUNA
    Conferido no acervo inteiro: em **185** pares (codigo do TJ, ano) com mais
    de uma quantidade o `curv_Emolumento` e' **constante**, e em **zero** ele
    escala com a quantidade. Os quatro fundos acompanham o unitario (4% de 5,92
    da' 0,23 em todas as linhas de `13.17.2`, da quantidade 1 a' 90). Logo a
    coluna do E-Oficio e' unitaria, e quem multiplicava era a tela dele.

    Os 11 pares que nao ficaram constantes **nao escalam**: sao troca de tabela
    no meio do ano (o `16.24.1` de 2020 tem 33,00 e 34,10) e itens de faixa,
    cujo valor depende da base e nao da quantidade.

O QUE ESTE SCRIPT FAZ, E O QUE ELE RECUSA
    Ele **le o acervo** (`tbProtocoloGeralCustas`, por `origem_chave`) e grava
    `quantidade x unitario`. Nao multiplica o que ja' esta gravado — e por isso
    **rodar duas vezes da' o mesmo resultado**. Recusa, declarando cada caso:

      - item **quitado** ou com lancamento no caixa: aquele dinheiro ja' entrou,
        e mudar o item faria a linha discordar do lancamento. Sai por estorno,
        que e' decisao de quem assina;
      - item cuja chave de origem **nao esta no acervo**;
      - item cujo valor gravado **nao bate** nem com o unitario nem com o
        produto: alguem mexeu nele a mao, e o script nao adivinha o que era.

    **So mede por padrao.** Com `--confirmar` ele tira copia do banco
    (`VACUUM INTO`) antes de tocar em nada, grava a auditoria a mao (a rota nao
    foi usada) e recalcula o total dos protocolos que mudaram.

    A situacao do protocolo **nao muda**: ela se deduz de quantos itens estao
    quitados, e nenhum item e' quitado nem desquitado aqui.
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

import banco_pg  # noqa: E402
import identidade_do_robo as IDR  # noqa: E402
# `banco` aqui e' o caminho do arquivo (parametro das funcoes), por isso o nome
from bd_nativo import banco as banco_nativo  # noqa: E402
from caixa_schema import centavos, reais  # noqa: E402

CAMPOS = ("emolumentos", "ferc", "fadep", "femp", "ferrfis")
COLUNA_NO_ACERVO = {
    "emolumentos": "curv_Emolumento",
    "ferc": "curv_Ferc",
    "femp": "curValor_MP",
    "fadep": "curValor_DP",
    "ferrfis": "curvalor_ferrfis",
}


def _unitario_do_acervo(acervo: sqlite3.Connection) -> dict[str, dict[str, int]]:
    """O valor unitario de cada linha de custa, em centavos, pela chave.

    A chave e' `intID`, que e' o que a carga grava em `origem_chave`. Ela vem
    como REAL no acervo (`10.0`), e por isso a comparacao e' pelo inteiro —
    a mesma pegadinha do `intChave` das tabelas do civil.
    """
    colunas = ", ".join(COLUNA_NO_ACERVO[c] for c in CAMPOS)
    por_chave: dict[str, dict[str, int]] = {}
    for linha in acervo.execute(
            f"SELECT intID, intQte, {colunas} FROM tbProtocoloGeralCustas"):
        if linha[0] is None:
            continue
        por_chave[str(int(linha[0]))] = {
            "quantidade": int(linha[1] or 1) or 1,
            **{c: centavos(f"{(linha[2 + i] or 0):.2f}".replace(".", ","))
               for i, c in enumerate(CAMPOS)},
        }
    return por_chave


def medir(banco: Path, acervo_caminho: Path) -> dict:
    """Le os dois bancos e diz o que mudaria. **NAO ESCREVE NADA.**"""
    con = banco_pg.conectar(f"file:{banco}?mode=ro", uri=True)
    # O ACERVO E' O ARQUIVO DO E-OFICIO, e continua SQLite: pela porta do
    # SQLite (LH09), que nao decide pelo nome do arquivo.
    acervo = banco_pg.conectar_sqlite(acervo_caminho)
    try:
        bd = banco_nativo(con)
        unitarios = _unitario_do_acervo(acervo)
        a_corrigir, recusados, ja_certos = [], [], 0
        for item in bd.ler(
                """SELECT id, protocolo_id, origem_chave, codigo_ato, quantidade,
                          valor_total, emolumentos, ferc, fadep, femp, ferrfis,
                          quitado, lancamento_id
                   FROM cx_protocolo_atos
                   WHERE origem='EOFICIO' AND quantidade > 1 ORDER BY id"""):
            chave = str(item["origem_chave"] or "").strip()
            fonte = unitarios.get(chave)
            if not fonte:
                recusados.append((item["id"], "a chave de origem não está no acervo"))
                continue
            if item["quitado"] or item["lancamento_id"]:
                recusados.append(
                    (item["id"], "item já quitado — esse dinheiro entrou no "
                                 "caixa, e sai por estorno"))
                continue
            quantidade = int(item["quantidade"])
            novos = {c: fonte[c] * quantidade for c in CAMPOS}
            gravado = {c: centavos(item[c]) for c in CAMPOS}
            if gravado == novos:
                ja_certos += 1
                continue
            if gravado != {c: fonte[c] for c in CAMPOS}:
                recusados.append(
                    (item["id"], "o valor gravado não bate nem com o unitário do "
                                 "acervo nem com o produto — alguém o editou"))
                continue
            a_corrigir.append({
                "id": int(item["id"]),
                "protocolo_id": int(item["protocolo_id"]),
                "codigo_ato": item["codigo_ato"],
                "quantidade": quantidade,
                "de": item["valor_total"],
                "para": reais(sum(novos.values())),
                "valores": {c: reais(v) for c, v in novos.items()},
                "diferenca": sum(novos.values()) - sum(gravado.values()),
            })
        return {
            "a_corrigir": a_corrigir,
            "recusados": recusados,
            "ja_certos": ja_certos,
            "protocolos": sorted({x["protocolo_id"] for x in a_corrigir}),
            "diferenca": sum(x["diferenca"] for x in a_corrigir),
        }
    finally:
        con.close()
        acervo.close()


def aplicar(banco: Path, medicao: dict) -> Path:
    """Grava. Tira copia do banco antes, e devolve onde ela ficou."""
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    copia = banco.with_name(
        f"{banco.stem}.antes-da-quantidade-nas-custas-{carimbo}{banco.suffix}")
    # FORA DA PASTA DO BANCO — ordem do oficial em 11/10/2026.
    import pasta_das_copias as _PC
    copia = _PC.destino_da_copia(copia, Path(banco))
    con = banco_pg.conectar(banco)
    try:
        bd = banco_nativo(con)
        banco_pg.copiar_para_arquivo(banco, copia)
        for x in medicao["a_corrigir"]:
            v = x["valores"]
            bd.escrever(
                """UPDATE cx_protocolo_atos
                   SET valor_total=%s, emolumentos=%s, ferc=%s, fadep=%s, femp=%s,
                       ferrfis=%s
                   WHERE id=%s AND quitado=0 AND lancamento_id IS NULL""",
                (x["para"], v["emolumentos"], v["ferc"], v["fadep"], v["femp"],
                 v["ferrfis"], x["id"]))
        # O TOTAL DO PROTOCOLO E' SOMA DOS ITENS, e nao um numero a parte: se
        # ele ficasse para tras, a tela mostraria os itens novos com o total
        # velho — o carimbo que mente dentro da propria linha.
        for protocolo_id in medicao["protocolos"]:
            # le a soma e grava o total na mesma linha: trava o protocolo antes
            bd._escrita()
            bd.ler("SELECT id FROM cx_protocolos WHERE id=%s FOR UPDATE",
                   (protocolo_id,))
            soma = sum(
                centavos(r["valor_total"]) for r in bd.ler(
                    "SELECT valor_total FROM cx_protocolo_atos WHERE protocolo_id=%s"
                    " ORDER BY id",
                    (protocolo_id,)))
            bd.escrever("UPDATE cx_protocolos SET valor_total=%s WHERE id=%s",
                        (reais(soma), protocolo_id))
        con.commit()
        # A AUDITORIA A MAO, porque a rota nao foi usada — a mesma forma do
        # script que normalizou a situacao dos problemas.
        for x in medicao["a_corrigir"]:
            # Quem grava por programa diz quem e e a mando de quem (26/10/2026).
            IDR.registrar(
                bd, ts=datetime.now().isoformat(timespec="seconds"), user_id=None,
                username="quantidade_nas_custas_do_eoficio",
                action="PROTOCOLO_ITEM_CORRIGIDO", entity_type="PROTOCOLO",
                entity_id=x["protocolo_id"],
                details=json.dumps({"item": x["id"], "codigo_tj": x["codigo_ato"],
                                    "quantidade": x["quantidade"],
                                    "de": x["de"], "para": x["para"]},
                                   ensure_ascii=False),
                agente="tools/quantidade_nas_custas_do_eoficio.py",
                a_mando_de=IDR.PELO_RESPONSAVEL)
        con.commit()
    finally:
        con.close()
    return copia


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--banco", default=r"C:\ProgramData\CartorioGestao\cartorio_gestao.sqlite3")
    p.add_argument("--acervo", default=r"C:\ProgramData\CartorioGestao\acervo_eoficio.sqlite3")
    p.add_argument("--confirmar", action="store_true",
                   help="grava. Sem isto, o script apenas mede.")
    args = p.parse_args()

    medicao = medir(Path(args.banco), Path(args.acervo))
    print(f"itens a corrigir ....... {len(medicao['a_corrigir'])}")
    print(f"ja' corretos ........... {medicao['ja_certos']}")
    print(f"recusados .............. {len(medicao['recusados'])}")
    print(f"protocolos atingidos ... {len(medicao['protocolos'])}")
    print(f"diferenca a mais ....... R$ {reais(medicao['diferenca'])}")
    for item_id, motivo in medicao["recusados"][:20]:
        print(f"   recusado {item_id}: {motivo}")
    if len(medicao["recusados"]) > 20:
        print(f"   ... e mais {len(medicao['recusados']) - 20}")
    for x in medicao["a_corrigir"][:5]:
        print(f"   exemplo: item {x['id']} {x['codigo_ato']} "
              f"q{x['quantidade']} — {x['de']} vira {x['para']}")

    if not args.confirmar:
        print("\nNADA FOI ALTERADO. Rode de novo com --confirmar para gravar.")
        return 0
    if not medicao["a_corrigir"]:
        print("\nNao ha o que corrigir.")
        return 0
    copia = aplicar(Path(args.banco), medicao)
    print(f"\nGRAVADO. Copia do banco antes da mudanca: {copia}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
