"""O pedido que a IA deixa para o escrevente fazer.

A conversa continua com a IA. O que o cliente pediu para ser feito (certidão,
firma, escritura, protesto, registro) vira uma linha aqui, no setor certo, com
o resumo que o escrevente lê. Quem lavra é ele, em Trabalho → Atendimentos e no
módulo da atribuição — este módulo não abre protocolo, não lança emolumento e
não sela.

Um pedido aberto do mesmo serviço na mesma conversa não duplica: a volta do
cliente atualiza o resumo.
"""
from __future__ import annotations

from typing import Any

from bd_nativo import banco

import wa_fila as FILA
import wa_oficio as OFICIO
import wa_schema as WA

ABERTO = "aberto"
FEITO = "feito"
SITUACOES = (ABERTO, FEITO)


def _resumo(texto: Any) -> str:
    return " ".join(str(texto or "").split())[:300]


def abrir(con: Any, conversa_id: int, *, setor: str, servico: str, resumo: str,
          orientacao: str = "", por: str = "", quando: str) -> dict:
    """Grava ou atualiza o pedido aberto. ESCREVE. Devolve {id, novo, setor}."""
    destino = FILA.setor_valido(setor) or WA.SETOR_PADRAO
    chave = OFICIO.servico_valido(servico) or OFICIO.servico_de(destino)
    texto = _resumo(resumo) or OFICIO.nome_do_servico(chave)
    bd = banco(con)
    ja = bd.um(
        """SELECT id FROM wa_pedido
            WHERE conversa_id=%s AND servico=%s AND situacao=%s
            ORDER BY id DESC LIMIT 1""",
        (int(conversa_id), chave, ABERTO))
    if ja:
        bd.escrever(
            """UPDATE wa_pedido SET resumo=%s, orientacao=%s, setor=%s, quando=%s
                WHERE id=%s""",
            (texto, (orientacao or "")[:2000], destino, quando, int(ja["id"])))
        return {"id": int(ja["id"]), "novo": False, "setor": destino, "servico": chave}
    linhas = bd.escrever(
        """INSERT INTO wa_pedido
             (conversa_id, quando, setor, servico, resumo, orientacao, situacao, por)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id""",
        (int(conversa_id), quando, destino, chave, texto,
         (orientacao or "")[:2000], ABERTO, (por or "")[:80]))
    pid = int(linhas[0]["id"])
    atual = FILA.setor_valido(
        (bd.um("SELECT setor FROM wa_conversa WHERE id=%s", (int(conversa_id),)) or {}
         ).get("setor")) or WA.SETOR_PADRAO
    bd.escrever(
        "UPDATE wa_conversa SET setor=%s, atualizado_em=%s WHERE id=%s",
        (destino, quando, int(conversa_id)))
    FILA.registrar_evento(
        con, int(conversa_id), FILA.EV_PEDIDO, quando=quando, por=por,
        nota=f"{OFICIO.nome_do_servico(chave)}: {texto}")
    return {"id": pid, "novo": True, "setor": destino, "servico": chave,
            "de": atual}


def _com_nome(linhas: list) -> list[dict]:
    saida = []
    for linha in linhas:
        item = dict(linha)
        item["servico_nome"] = OFICIO.nome_do_servico(item.get("servico"))
        item["setor_nome"] = WA.SETORES.get(item.get("setor") or "", item.get("setor") or "")
        saida.append(item)
    return saida


def abertos(con: Any, *, limite: int = 50) -> list[dict]:
    """Os pedidos que o escrevente ainda não marcou como feitos. SÓ LÊ."""
    teto = max(1, min(int(limite or 50), 100))
    linhas = banco(con).ler(
        """SELECT p.*, c.nome, c.wa_id FROM wa_pedido p
             JOIN wa_conversa c ON c.id = p.conversa_id
            WHERE p.situacao=%s
            ORDER BY p.id DESC LIMIT %s""",
        (ABERTO, teto))
    return _com_nome(linhas)


def da_conversa(con: Any, conversa_id: int) -> list[dict]:
    """Os pedidos desta conversa, o aberto primeiro. SÓ LÊ."""
    linhas = banco(con).ler(
        """SELECT * FROM wa_pedido WHERE conversa_id=%s
            ORDER BY CASE WHEN situacao=%s THEN 0 ELSE 1 END, id DESC""",
        (int(conversa_id), ABERTO))
    return _com_nome(linhas)


def concluir(con: Any, pedido_id: int, *, por: str, quando: str) -> bool:
    """O escrevente fez o trabalho. ESCREVE. Falso se não havia pedido aberto."""
    feitas = banco(con).escrever(
        """UPDATE wa_pedido SET situacao=%s, feito_em=%s, feito_por=%s
            WHERE id=%s AND situacao=%s
            RETURNING id""",
        (FEITO, quando, (por or "")[:80], int(pedido_id), ABERTO))
    return bool(feitas)
