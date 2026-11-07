"""Selo da desistência e do cancelamento já lavrados, depois do caixa.

Esses atos não são diferidos. O selo só entra na fila quando o emolumento
deles já está lançado no caixa (`protesto.tem_pagamento_no_caixa`) e a linha
devida está COBRADA. Sem isso a tela mostra o título e não oferece o botão.
Este módulo não sela e não cobra. O acervo fica de fora.
"""
from __future__ import annotations

from typing import Any

import protesto as PT
import selo_robo as SR
from bd_nativo import banco

TABELA = "pt_atos"
TIPOS = tuple(sorted(PT.ATOS_SO_DEPOIS_DO_CAIXA))
MARCA_DO_ACERVO = "EOFICIO"
ACAO_DA_AUDITORIA = "PROTESTO_DESFECHO_SELADO_DEPOIS"
LIMITE_POR_CLIQUE = 10
MSG_ROBO = ("Robô não sela. Desistência e cancelamento se selam pelo "
            "escrevente, em pessoa, depois do pagamento no caixa.")
MSG_CAIXA = ("Este ato só se sela depois do pagamento no caixa. Abra o "
             "caixa, cobre o emolumento na ficha e volte aqui.")


class SeloDesfechoError(ValueError):
    """Impedimento do selo do desfecho, com frase pronta para o balcão."""


def _int(valor: Any) -> int | None:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _ficha(linha: dict, motivo: str, itens: list[dict], *,
           espera_caixa: bool = False) -> dict:
    codigo = str(itens[0].get("codigo_tj") or "") if itens else ""
    return {
        "ato_id": int(linha["ato_id"]),
        "titulo_id": int(linha["titulo_id"]),
        "tipo": str(linha.get("tipo") or ""),
        "numero_titulo": linha.get("numero_titulo") or "",
        "protocolo": linha.get("protocolo") or "",
        "devedor": linha.get("devedor") or "",
        "data_ato": str(linha.get("data_ato") or "")[:10],
        "motivo": motivo,
        "itens": itens,
        "codigo_tj": codigo,
        "espera_caixa": espera_caixa,
    }


def _ler(bd, titulo_id: int | None) -> list[dict]:
    filtro = ""
    params: list[Any] = [*TIPOS, MARCA_DO_ACERVO]
    if titulo_id is not None:
        filtro = " AND a.titulo_id = %s"
        params.append(int(titulo_id))
    lugares = ",".join(["%s"] * len(TIPOS))
    return bd.ler(
        f"""SELECT a.id AS ato_id, a.titulo_id, a.tipo, a.origem, a.selo,
                   a.data_ato, t.numero_titulo, t.protocolo,
                   (SELECT d.nome FROM pt_devedores d
                     WHERE d.titulo_id = t.id ORDER BY d.id LIMIT 1) AS devedor
              FROM pt_atos a
              JOIN pt_titulos t ON t.id = a.titulo_id
             WHERE a.tipo IN ({lugares})
               AND COALESCE(a.cancelado, 0) = 0
               AND COALESCE(a.origem, '') <> %s
               AND (a.selo IS NULL OR btrim(a.selo) = ''){filtro}
             ORDER BY a.data_ato, a.id""",
        params)


def _itens_cobrados(bd, ato_id: int) -> list[dict]:
    if not bd.tem_tabela("pt_emolumentos_diferidos"):
        return []
    return bd.ler(
        """SELECT d.servico, d.quantidade, d.descricao, s.codigo_tj
             FROM pt_emolumentos_diferidos d
             JOIN cx_servicos s ON s.codigo = d.servico
            WHERE d.ato_id = %s AND d.situacao = 'COBRADO'
              AND s.codigo_tj IS NOT NULL AND btrim(s.codigo_tj) <> ''
            ORDER BY d.id""",
        (int(ato_id),))


def _classificar(con, bd, linha: dict) -> tuple[str, str, list, bool]:
    ato_id = int(linha["ato_id"])
    if not PT.tem_pagamento_no_caixa(con, ato_id):
        return "de_fora", MSG_CAIXA, [], True
    itens = _itens_cobrados(bd, ato_id)
    if not itens:
        return "de_fora", ("O caixa não tem o emolumento deste ato marcado "
                           "como cobrado. Cobre-o na ficha antes do selo."), [], False
    return "selavel", "", itens, False


def pendentes(con, *, titulo_id: int | None = None) -> dict:
    """O que já pode selar e o que ainda espera o caixa. Só LÊ."""
    bd = banco(con)
    selaveis: list[dict] = []
    esperando: list[dict] = []
    de_fora: list[dict] = []
    for linha in _ler(bd, titulo_id):
        classe, motivo, itens, espera = _classificar(con, bd, linha)
        ficha = _ficha(linha, motivo, itens, espera_caixa=espera)
        if classe == "selavel":
            selaveis.append(ficha)
        elif espera:
            esperando.append(ficha)
        else:
            de_fora.append(ficha)
    return {"selaveis": selaveis, "esperando": esperando, "de_fora": de_fora,
            "limite": LIMITE_POR_CLIQUE}


def preparar(con, *, eh_robo: Any, usuario: str | None, agora: str,
             ato_id: int | None = None) -> dict:
    """Confere o pagamento e devolve o que o clique vai selar. Não sela.

    Não grava devido: o emolumento já entrou no caixa. O selo sai normal,
    pela cobertura do lançamento, e não como diferido.
    """
    if eh_robo or SR.usuario_e_robo():
        raise SeloDesfechoError(MSG_ROBO)
    pedido = _int(ato_id)
    quadro = pendentes(con)
    if pedido is not None:
        escolhidos = [p for p in quadro["selaveis"] if int(p["ato_id"]) == pedido]
        if not escolhidos:
            motivo = next((p["motivo"] for p in
                           quadro["esperando"] + quadro["de_fora"]
                           if int(p["ato_id"]) == pedido), "")
            raise SeloDesfechoError(
                f"O ato {pedido} não entra neste selo"
                + (f": {motivo}" if motivo else
                   ". Não é desistência ou cancelamento pendente de selo."))
    else:
        escolhidos = quadro["selaveis"][:LIMITE_POR_CLIQUE]
    return {"prontos": escolhidos, "limite": LIMITE_POR_CLIQUE,
            "usuario": usuario, "agora": agora}
