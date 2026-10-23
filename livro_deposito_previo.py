"""O Livro de Controle de Depósito Prévio — arts. 188, III, e 195 a 202 do Código
de Normas do MA.

POR QUE EXISTE (LG08, 19/10/2026)
    «No Livro de Controle de Depósito Prévio, o delegatário deverá indicar, no
    mínimo: I - o número do protocolo do título ou do pedido de serviço; II - a
    data do depósito; III - o valor depositado; IV - a data da conversão do
    depósito em emolumentos, com a identificação do ato praticado; V - a data
    da devolução do valor depositado, com a justificativa, quando o ato não for
    praticado; e VI - a descrição completa do orçamento, inclusive seus
    acréscimos» (art. 198).

    O depósito já existe — Caixa → Depósito prévio (`cx_depositos`) —, mas
    como CADASTRO DE SALDO. Medido em 19/10/2026: usar o depósito só baixa o
    saldo (e lança no caixa SE o caixa estiver aberto); devolver acrescenta a
    data e o motivo ao fim da `observacao`. Não há coluna para a data da
    conversão nem para a da devolução, e o orçamento é, no máximo, um item do
    catálogo.

LER, E NÃO MUDAR O CAIXA
    Este módulo NÃO muda o caixa: muda-lo é outra conversa (regra de dinheiro
    que já entrou, e telas que três atribuições usam). Ele monta o livro com o
    que existe — o cadastro e o RASTRO: cada uso e cada devolução feitos pela
    tela gravam `DEPOSITO_PREVIO_USADO` / `DEPOSITO_PREVIO_DEVOLVIDO` em
    `audit_logs`, com a data, o valor e o protocolo ou o motivo, ainda que o
    caixa esteja fechado; o débito que o selo faz no depósito do protocolo
    fica em `cx_deposito_usos` (LT06). E diz, depósito a depósito, o que falta para o art.
    198 — em vez de imprimir a coluna vazia como se estivesse cheia.

    O que o rastro não explica (depósito trazido do E-Ofício, uso anterior ao
    rastro) aparece como DIFERENÇA: valor depositado, menos o convertido, menos
    o devolvido, contra o saldo do cadastro.

O ORÇAMENTO (LD06, 21/10/2026)
    O depósito passou a guardar o orçamento congelado no dia em que entrou —
    os itens com os emolumentos e cada fundo (`caixa_depositos.
    orcamento_do_deposito`) —, e a coluna VI o lê. O depósito de antes disso
    continua com a falta dita por extenso.

Só LÊ. PostgreSQL nativo, pelo `bd_nativo`.
"""
from __future__ import annotations

import json
import re
from typing import Any

import caixa_depositos as DEP
from bd_nativo import banco
from caixa_schema import centavos, reais

USADO, DEVOLVIDO = "DEPOSITO_PREVIO_USADO", "DEPOSITO_PREVIO_DEVOLVIDO"


def _detalhes(texto: Any) -> dict:
    try:
        lido = json.loads(texto or "{}")
    except (TypeError, ValueError):
        return {}
    return lido if isinstance(lido, dict) else {}


def _movimentos(bd) -> dict[int, list[dict]]:
    """Os usos e as devoluções do rastro, por depósito, na ordem em que
    aconteceram."""
    saida: dict[int, list[dict]] = {}
    for x in bd.ler(
            """SELECT ts, action, entity_id, details FROM audit_logs
                WHERE entity_type = 'DEPOSITO' AND action IN (%s, %s)
                  AND entity_id IS NOT NULL
                ORDER BY ts, id""", (USADO, DEVOLVIDO)):
        d = _detalhes(x["details"])
        if x["action"] == USADO:
            mov = {"tipo": "CONVERSAO", "data": str(x["ts"])[:10],
                   "valor": centavos(d.get("usado")),
                   "protocolo": str(d.get("protocolo") or "").strip()}
        else:
            mov = {"tipo": "DEVOLUCAO", "data": str(x["ts"])[:10],
                   "valor": centavos(d.get("valor")),
                   "motivo": str(d.get("motivo") or "").strip()}
        saida.setdefault(int(x["entity_id"]), []).append(mov)
    for deposito, movs in _debitos_do_selo(bd).items():
        saida.setdefault(deposito, []).extend(movs)
    for movs in saida.values():
        movs.sort(key=lambda m: m["data"])
    return saida


def _debitos_do_selo(bd) -> dict[int, list[dict]]:
    """As conversões que quitam item: o selo, o quadro «Selo e caixa» e, desde
    o LD06, o «usar» da tela do caixa com o protocolo. Só LÊ.

    A TELA DO CAIXA NÃO É O ÚNICO LUGAR QUE CONVERTE O DEPÓSITO (LT06,
    20/10/2026). O selo pago e o quadro «Para selar este ato falta» quitam o
    item com o depósito do protocolo (`caixa_depositos.pagar_item`), e o
    rastro desse débito é `cx_deposito_usos` — com a data, o valor, o
    protocolo, o item e o ato —, e não `audit_logs`. Sem lê-lo, o livro
    mostrava a conversão como dinheiro que «saiu do saldo sem uso nem
    devolução», e o art. 198, IV, ficava sem a data e sem o ato.

    O estorno de uma reserva do selo que não saiu é a linha de valor NEGATIVO
    (`ato_selado._devolver_ao_deposito`): entra com o sinal, e a soma dos
    usos chega ao saldo do cadastro.
    """
    if not bd.tem_tabela("cx_deposito_usos"):
        return {}
    saida: dict[int, list[dict]] = {}
    for u in bd.ler(
            """SELECT u.deposito_id, u.valor_centavos, u.criado_em, u.tabela, u.ato_id,
                      p.numero AS protocolo_numero, i.codigo_ato
                 FROM cx_deposito_usos u
                 LEFT JOIN cx_protocolos p ON p.id = u.protocolo_id
                 LEFT JOIN cx_protocolo_atos i ON i.id = u.item_id
                ORDER BY u.criado_em, u.id"""):
        ato = []
        if u["codigo_ato"]:
            ato.append(f"item {u['codigo_ato']}")
        if u["tabela"] and u["ato_id"] is not None:
            ato.append(f"ato {u['tabela']} nº {u['ato_id']}")
        if int(u["valor_centavos"] or 0) < 0:
            ato.append("estorno do selo que não saiu")
        saida.setdefault(int(u["deposito_id"]), []).append({
            "tipo": "CONVERSAO", "data": str(u["criado_em"])[:10],
            "valor": int(u["valor_centavos"] or 0),
            "protocolo": str(u["protocolo_numero"] or "").strip(),
            "ato": ", ".join(ato)})
    return saida


def livro(con, *, ano: Any = None) -> dict:
    """O livro: um depósito por linha, com as seis colunas do art. 198 e o que
    falta em cada uma. Só LÊ."""
    bd = banco(con)
    filtro, params = "", ()
    # Só quatro dígitos ASCII: `isdigit()` aceitava «²», e o `int()` estourava.
    if re.fullmatch(r"[0-9]{4}", str(ano or "").strip()):
        filtro, params = " WHERE d.data >= %s AND d.data < %s", (
            f"{int(ano):04d}-01-01", f"{int(ano) + 1:04d}-01-01")
    depositos = bd.ler(
        """SELECT d.*, p.numero AS protocolo_numero, s.descricao AS servico_descricao
             FROM cx_depositos d
             LEFT JOIN cx_protocolos p ON p.id = d.protocolo_id
             LEFT JOIN cx_servicos s ON s.codigo = d.servico_codigo""" + filtro
        + " ORDER BY d.data, d.id", params)
    movimentos = _movimentos(bd)
    linhas = []
    for d in depositos:
        movs = movimentos.get(int(d["id"]), [])
        conversoes = [m for m in movs if m["tipo"] == "CONVERSAO"]
        devolucoes = [m for m in movs if m["tipo"] == "DEVOLUCAO"]
        valor, saldo = centavos(d["valor"]), centavos(d["saldo"])
        protocolo = (d["protocolo_numero"]
                     or (f"prenotação do RI nº {d['ri_protocolo_id']}"
                         if d["ri_protocolo_id"] else "")
                     or (f"ato de Notas nº {d['nt_ato_id']}" if d["nt_ato_id"] else ""))
        # O ORÇAMENTO CONGELADO NO DEPÓSITO (LD06): os itens com os fundos — os
        # acréscimos do art. 198, VI. O depósito de antes dele (ou o que entrou
        # sem serviço nem protocolo) continua dizendo a falta, e o que tem só
        # o nome do serviço mostra o nome, sem fingir que é o orçamento.
        congelado = DEP.orcamento_gravado(d)
        orcamento_linhas = DEP.linhas_do_orcamento(congelado)
        orcamento = ("; ".join(orcamento_linhas) if orcamento_linhas
                     else d["servico_descricao"] or "")
        faltas = []
        if not protocolo:
            faltas.append("I — o depósito não aponta protocolo nem pedido de serviço")
        if not congelado:
            faltas.append("VI — orçamento só pelo serviço; os acréscimos não são guardados"
                          if orcamento else
                          "VI — sem orçamento: o cadastro não aponta nem o serviço")
        elif not int((congelado.get("soma") or {}).get("total_centavos") or 0):
            faltas.append("VI — o orçamento guardado não tem valor")
        if any(not m["protocolo"] for m in conversoes):
            faltas.append("IV — conversão sem a identificação do ato praticado")
        if any(not m["motivo"] for m in devolucoes):
            faltas.append("V — devolução sem justificativa")
        explicado = valor - sum(m["valor"] for m in movs)
        diferenca = explicado - saldo
        if diferenca:
            faltas.append(
                f"IV/V — R$ {reais(diferenca)} saíram do saldo sem uso nem "
                f"devolução no rastro (depósito anterior ao rastro ou trazido "
                f"do E-Ofício)")
        linhas.append({
            "id": int(d["id"]), "numero": d["numero"] or f"id {d['id']}",
            "data": d["data"], "depositante": d["depositante"],
            "protocolo": protocolo, "valor": valor, "saldo": saldo,
            "conversoes": conversoes, "devolucoes": devolucoes,
            "orcamento": orcamento, "orcamento_linhas": orcamento_linhas,
            "encerrado": bool(d["encerrado"]),
            "diferenca": diferenca, "faltas": faltas,
        })
    return {
        "linhas": linhas,
        "total_depositado": sum(x["valor"] for x in linhas),
        "total_convertido": sum(m["valor"] for x in linhas for m in x["conversoes"]),
        "total_devolvido": sum(m["valor"] for x in linhas for m in x["devolucoes"]),
        "saldo": sum(x["saldo"] for x in linhas),
        "com_falta": sum(1 for x in linhas if x["faltas"]),
    }
