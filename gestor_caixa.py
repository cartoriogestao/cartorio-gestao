"""O parecer do agente sobre cada caixa fechado — a conferência refeita.

    «agente completo que faça todo trabalho do oficial» — 06/10/2026

O QUE O AGENTE FAZ, E O QUE ELE NÃO FAZ
    Refaz a conta de cada caixa fechado com a MESMA função da tela
    (`caixa_schema.resumo_caixa`) e aponta o que não fecha. Ele **não grava
    `conferido_por`**: a coluna guarda o id de quem conferiu, e pôr ali o id do
    oficial afirmaria uma conferência que ele não fez. O caixa sem ponto vai
    para o visto do oficial — que pode ser dado em lote, pela tela do gestor.

MEDIDO EM 06/10/2026 nos 49 caixas fechados e não conferidos desde 10/09:
    42 sem ponto nenhum; 7 com ponto. Seis dos sete têm diferença, e cinco
    delas são exatamente **−R$ 300,00 — o troco inicial** —, o desenho de quem
    guardou o troco antes de contar a gaveta. O parecer diz isso, sem concluir:
    quem sabe é quem contou.
"""
from __future__ import annotations

import sqlite3

from bd_nativo import banco
from caixa_schema import centavos, resumo_caixa


def _brl(c: int) -> str:
    s = f"{abs(c) / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("−" if c < 0 else "") + "R$ " + s


def parecer(con: sqlite3.Connection, caixa: dict) -> list[str]:
    """Os pontos do caixa fechado; lista vazia é caixa que fecha. Só LÊ."""
    lans = banco(con).ler(
        "SELECT * FROM cx_lancamentos WHERE caixa_id = %s ORDER BY id", (caixa["id"],))
    res = resumo_caixa(lans, caixa["saldo_inicial"])
    esperado = centavos(caixa["valor_esperado"])
    contado = centavos(caixa["valor_contado"])
    diferenca = centavos(caixa["diferenca"])
    inicial = centavos(caixa["saldo_inicial"])
    pontos = []
    if res["em_especie"] != esperado:
        pontos.append(f"o esperado gravado ({_brl(esperado)}) não é o que os lançamentos "
                      f"dão hoje ({_brl(res['em_especie'])}) — lançamento mexido depois de fechar?")
    if contado - esperado != diferenca:
        pontos.append("contado menos esperado não dá a diferença gravada")
    if diferenca:
        frase = f"diferença de {_brl(diferenca)}"
        if diferenca == -inicial and inicial:
            frase += " — igual ao troco inicial: o troco foi guardado antes de contar?"
        if not (caixa["justificativa"] or "").strip():
            frase += "; SEM justificativa"
        else:
            frase += f"; justificativa: «{caixa['justificativa'].strip()[:120]}»"
        pontos.append(frase)
    vivos = [l for l in lans if not l.get("excluido") and not l.get("estornado")
             and l.get("sentido") != "ESTORNO"]
    gratis = [l for l in vivos if (l.get("forma_pagamento") or "").upper() == "GRATUITO"
              and centavos(l.get("valor")) > 0]
    if gratis:
        pontos.append(f"{len(gratis)} lançamento(s) marcado(s) GRATUITO com valor")
    sem_forma = [l for l in vivos if not l.get("forma_pagamento") and centavos(l.get("valor")) > 0]
    if sem_forma:
        soma = sum(centavos(l.get("valor")) for l in sem_forma)
        pontos.append(f"{len(sem_forma)} lançamento(s) sem forma de pagamento ({_brl(soma)}) — "
                      "não se sabe se foi dinheiro, PIX ou depósito")
    sem_motivo = [l for l in lans if l.get("excluido") and not (l.get("motivo_exclusao") or "").strip()]
    if sem_motivo:
        pontos.append(f"{len(sem_motivo)} lançamento(s) excluído(s) sem motivo")
    return pontos
