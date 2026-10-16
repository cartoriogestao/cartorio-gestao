"""Os livros do Protesto que a inspeção não achou — montados do que foi lavrado.

Código de Normas do TJMA (Prov. 28/2026), lido no texto em 14/10/2026:

  art. 930 — LIVRO DE REGISTRO DE PAGAMENTOS: «todos os pagamentos recebidos
  serão lançados», com as colunas a) número de ordem; b) data do assentamento;
  c) número do protocolo do documento pago; d) natureza do documento; e) valor
  do pagamento; f) valor dos emolumentos; g) nomes do devedor e do favorecido;
  h) ocorrências — e nelas «se o pagamento se dará em espécie ou por cheque,
  com a correspondente identificação». § 2º: pode ser eletrônico, «facultativa
  sua impressão».

  art. 908 — LIVRO DE PROTOCOLO: número de ordem, natureza do documento,
  valor, apresentante, devedor e OCORRÊNCIAS; § 1º: nelas vão o resultado, a
  liquidação, a sustação judicial, a retirada pelo apresentante, o protesto ou
  a devolução por irregularidade; § 5º: averbam-se as datas da intimação, do
  pagamento, da sustação, da devolução ou da lavratura do protesto.

POR QUE ISTO EXISTE. A inspeção de 2021 marcou o Livro de Registro de
Pagamentos como IRREGULAR («inexistente»), e a de 2026 constatou de novo
(tarefas #52 e #54; relato #128). O pagamento era registrado direto no caixa e
nenhum papel o reunia; o Livro de Protocolo não tinha a coluna de ocorrências.

ESTE MÓDULO SÓ LÊ. O livro é a vista do que os atos já gravaram (`pt_atos`,
`pt_titulos`, `pt_devedores`): não há segunda gaveta para divergir da primeira.
O que o ato não guardou aparece como «não consta», e não inventado — os
pagamentos trazidos do E-Ofício não têm emolumentos nem forma de pagamento.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

import protesto_cra as CRA
from caixa_schema import reais

FORMAS = {
    "ESPECIE": "em espécie", "CHEQUE": "por cheque", "PIX": "por PIX",
    "TRANSFERENCIA": "por transferência bancária", "BOLETO": "por boleto",
    "CARTAO": "por cartão",
}


def _br(iso: Any) -> str:
    s = str(iso or "")[:10]
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if len(s) == 10 and s[4] == "-" else s


def _natureza(especie: Any) -> str:
    e = str(especie or "").strip().upper()
    return CRA.ESPECIES.get(e, e) if e else "não consta"


def _detalhe(texto: Any) -> dict:
    try:
        return json.loads(texto or "{}") or {}
    except (TypeError, ValueError):
        return {}


def _intervalo(de: str | None, ate: str | None) -> tuple[str, str]:
    """O filtro de data inclui o dia inteiro do «até», mesmo com hora gravada."""
    return (str(de or "0000-00-00")[:10], str(ate or "9999-12-31")[:10] + "z")


def livro_de_pagamentos(con: sqlite3.Connection, *, de: str | None = None,
                        ate: str | None = None) -> list[dict]:
    """As linhas do Livro de Registro de Pagamentos, na ordem do livro. Só LÊ."""
    inicio, fim = _intervalo(de, ate)
    linhas = []
    for r in con.execute(
            """SELECT a.id, a.data_ato, a.numero_ordem, a.folha, a.rotulo,
                      a.detalhe_json, a.origem,
                      (SELECT v.numero FROM nu_livros v WHERE v.id = a.livro_id) livro,
                      t.protocolo, t.especie, t.numero_titulo, t.saldo_centavos,
                      t.cedente_nome,
                      (SELECT d.nome FROM pt_devedores d WHERE d.titulo_id = t.id
                        ORDER BY d.id LIMIT 1) devedor
                 FROM pt_atos a JOIN pt_titulos t ON t.id = a.titulo_id
                WHERE a.tipo = 'PAGAMENTO' AND a.cancelado = 0
                  AND a.data_ato >= ? AND a.data_ato <= ?
                ORDER BY a.data_ato, a.id""", (inicio, fim)):
        d = _detalhe(r["detalhe_json"])
        valor = d.get("valor_pago_centavos")
        forma = FORMAS.get(str(d.get("forma_pagamento") or "").upper())
        ocorr = []
        if forma:
            ocorr.append(f"pago {forma}"
                         + (f" — {d['forma_identificacao']}"
                            if d.get("forma_identificacao") else ""))
        if r["origem"] == "EOFICIO":
            ocorr.append("pagamento registrado no E-Ofício (forma não consta)")
        linhas.append({
            "ato_id": int(r["id"]),
            "ordem": r["numero_ordem"],
            "livro": r["livro"], "folha": r["rotulo"] or r["folha"],
            "data": _br(r["data_ato"]),
            "protocolo": r["protocolo"] or "",
            "natureza": _natureza(r["especie"]),
            "titulo": r["numero_titulo"] or "",
            "valor": reais(int(valor)) if valor is not None else
                     (reais(int(r["saldo_centavos"] or 0)) + " (saldo do título)"),
            "emolumentos": (reais(int(d["emolumentos_centavos"]))
                            if d.get("emolumentos_centavos") is not None
                            else "não consta"),
            "devedor": r["devedor"] or "",
            "favorecido": r["cedente_nome"] or "",
            "ocorrencias": "; ".join(ocorr) or "forma de pagamento não consta",
        })
    return linhas


# O que se averba no Livro de Protocolo (art. 908, §§ 1º e 5º), por tipo de ato.
OCORRENCIA_DO_ATO = {
    "INTIMACAO": "intimado",
    "PAGAMENTO": "pago",
    "DESISTENCIA": "retirado pelo apresentante",
    "PROTESTO": "protestado",
    "CANCELAMENTO": "protesto cancelado",
    "SUSTACAO": "sustação judicial",
    "REVOGACAO_SUSTACAO": "sustação revogada",
    "EFEITO_SUSPENSIVO": "efeitos suspensos por ordem judicial",
}


def livro_de_protocolo(con: sqlite3.Connection, *, de: str | None = None,
                       ate: str | None = None) -> list[dict]:
    """As linhas do Livro de Protocolo, com a coluna de OCORRÊNCIAS. Só LÊ.

    A data que filtra é a do APONTAMENTO (a protocolização); as ocorrências
    trazem a data de cada ato posterior, como o § 5º manda averbar.
    """
    inicio, fim = _intervalo(de, ate)
    linhas = []
    for r in con.execute(
            """SELECT t.id, t.protocolo, t.especie, t.numero_titulo,
                      t.valor_centavos, t.apresentante_nome, t.apresentante_codigo,
                      t.situacao, a.data_ato, a.numero_ordem,
                      (SELECT d.nome FROM pt_devedores d WHERE d.titulo_id = t.id
                        ORDER BY d.id LIMIT 1) devedor
                 FROM pt_atos a JOIN pt_titulos t ON t.id = a.titulo_id
                WHERE a.tipo = 'APONTAMENTO' AND a.cancelado = 0
                  AND a.data_ato >= ? AND a.data_ato <= ?
                ORDER BY a.data_ato, a.numero_ordem, a.id""", (inicio, fim)):
        ocorr = []
        for o in con.execute(
                """SELECT tipo, data_ato, detalhe_json FROM pt_atos
                    WHERE titulo_id = ? AND cancelado = 0 AND tipo <> 'APONTAMENTO'
                    ORDER BY data_ato, id""", (int(r["id"]),)):
            rotulo = OCORRENCIA_DO_ATO.get(o["tipo"])
            if not rotulo:
                continue
            if o["tipo"] == "INTIMACAO":
                modo = str(_detalhe(o["detalhe_json"]).get("modo") or "").upper()
                rotulo += " por edital" if modo == "EDITAL" else " pessoalmente" \
                    if modo == "PESSOAL" else ""
            ocorr.append(f"{rotulo} em {_br(o['data_ato'])}")
        linhas.append({
            "titulo_id": int(r["id"]),
            "ordem": r["numero_ordem"],
            "protocolo": r["protocolo"] or "",
            "data": _br(r["data_ato"]),
            "natureza": _natureza(r["especie"]),
            "titulo": r["numero_titulo"] or "",
            "valor": reais(int(r["valor_centavos"] or 0)),
            "apresentante": r["apresentante_nome"] or r["apresentante_codigo"] or "",
            "devedor": r["devedor"] or "",
            "ocorrencias": "; ".join(ocorr) or "sem ocorrência",
        })
    return linhas
