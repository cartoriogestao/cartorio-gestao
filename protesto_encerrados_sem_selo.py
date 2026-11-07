"""Desistências e cancelamentos sem selo. Só lê.

A lista «Protestos lavrados sem selo» só mostra o ato PROTESTO de título que
continua PROTESTADO. A desistência e o cancelamento sem selo não cabem lá, e
também não entram em «Atos a refazer ou a selar» quando quem lavrou não é o
robô. Esta leitura é a página que junta os dois.

O E-Ofício fica numa lista à parte. O botão que sela o protesto lavrado não
os sela, e esta página também não sela.
"""
from __future__ import annotations

from typing import Any

from bd_nativo import banco

TIPOS = ("DESISTENCIA", "RETIRADA", "CANCELAMENTO")
SITUACOES = ("DESISTIDO", "CANCELADO")
ACERVO = "EOFICIO"


def _data_br(valor: Any) -> str:
    texto = str(valor or "")[:10]
    if len(texto) == 10 and texto[4] == "-":
        return f"{texto[8:10]}/{texto[5:7]}/{texto[:4]}"
    return texto


def _da_casa(linha: dict) -> bool:
    origem_ato = str(linha.get("origem_ato") or "").strip().upper()
    origem_titulo = str(linha.get("origem_titulo") or "").strip().upper()
    return ACERVO not in (origem_ato, origem_titulo)


def listar(con) -> dict:
    """As desistências e os cancelamentos sem selo. Só LÊ.

    Sem selo quer dizer coluna vazia e, quando o razão existe, nenhuma linha
    viva em `sd_selos`. Devolve `da_casa` e `acervo`.
    """
    bd = banco(con)
    razao = ""
    if bd.tem_tabela("sd_selos"):
        razao = """
           AND NOT EXISTS (
               SELECT 1 FROM sd_selos s
                WHERE s.tabela = 'pt_atos' AND s.ato_id = a.id
                  AND s.cancelado_em IS NULL)"""
    tipos = ",".join(["%s"] * len(TIPOS))
    situacoes = ",".join(["%s"] * len(SITUACOES))
    linhas = bd.ler(
        f"""SELECT a.id AS ato_id, a.tipo, a.origem AS origem_ato, a.data_ato,
                   t.id AS titulo_id, t.numero_titulo, t.protocolo, t.situacao,
                   t.origem AS origem_titulo,
                   (SELECT d.nome FROM pt_devedores d
                     WHERE d.titulo_id = t.id ORDER BY d.id LIMIT 1) AS devedor
              FROM pt_atos a
              JOIN pt_titulos t ON t.id = a.titulo_id
             WHERE COALESCE(a.cancelado, 0) = 0
               AND a.tipo IN ({tipos})
               AND t.situacao IN ({situacoes})
               AND (a.selo IS NULL OR btrim(a.selo) = ''){razao}
             ORDER BY a.data_ato DESC, a.id DESC""",
        [*TIPOS, *SITUACOES])
    devidos: dict[int, str] = {}
    ids = sorted({int(r["titulo_id"]) for r in linhas})
    if ids and bd.tem_tabela("pt_emolumentos_diferidos"):
        marcas = ",".join(["%s"] * len(ids))
        for item in bd.ler(
                f"""SELECT titulo_id, descricao FROM pt_emolumentos_diferidos
                     WHERE situacao = 'PENDENTE' AND titulo_id IN ({marcas})
                     ORDER BY id""", ids):
            texto = str(item.get("descricao") or "").strip()
            if not texto:
                continue
            chave = int(item["titulo_id"])
            devidos[chave] = texto if chave not in devidos else f"{devidos[chave]}; {texto}"
    da_casa: list[dict] = []
    acervo: list[dict] = []
    for linha in linhas:
        ficha = {
            "ato_id": int(linha["ato_id"]),
            "titulo_id": int(linha["titulo_id"]),
            "numero_titulo": linha.get("numero_titulo") or "",
            "protocolo": linha.get("protocolo") or "",
            "situacao": linha.get("situacao") or "",
            "tipo": linha.get("tipo") or "",
            "origem_ato": linha.get("origem_ato") or "",
            "data_ato": _data_br(linha.get("data_ato")),
            "devedor": linha.get("devedor") or "",
            "devido": devidos.get(int(linha["titulo_id"]), ""),
        }
        (da_casa if _da_casa(linha) else acervo).append(ficha)
    return {"da_casa": da_casa, "acervo": acervo}
