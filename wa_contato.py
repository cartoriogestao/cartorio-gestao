"""QUEM É A PESSOA DO WHATSAPP (29/10/2026) — o cabeçalho da conversa.

    «queria que aparecesse a foto e os dados da pessoa que esta em contato
     com o cartorio» — o oficial, 29/10/2026.

A META NÃO ENTREGA A FOTO DO CLIENTE. Pela API oficial do WhatsApp chegam o
número (`wa_id`) e o nome que a pessoa pôs no perfil, e mais nada — não há
campo nem chamada para a foto do perfil de quem escreve. O que a casa tem é o
próprio cadastro: o telefone está no CARTÃO DE FIRMA (`nt_cartoes.celular` e
`telefone`, com a foto colhida no balcão em `nt_cadastro_imagens`) e no
PROTOCOLO do balcão (`cx_protocolos.telefone`). Este módulo procura o número
da conversa nos dois. SÓ LÊ.

O TELEFONE NÃO IDENTIFICA NINGUÉM SOZINHO. Família divide número, e número
muda de dono. Por isso a tela diz «cadastros com este telefone», e não «esta
pessoa é»: quem atende confere antes de falar de ato com o cliente.

COMO O NÚMERO CASA. O `wa_id` vem como 55 + DDD + número (o WhatsApp às vezes
sem o 9 da frente). Medido na produção em 29/10/2026: no cartão, 351 celulares
têm 9 dígitos (sem DDD), 195 têm 11 e 31 têm 10; no protocolo, 1.358 têm 9,
1.078 têm 11 e 84 têm 10. A régua: os 8 últimos dígitos iguais e, quando o
cadastro tem DDD, o mesmo DDD. Sem DDD no cadastro, vale (a casa atende o
próprio DDD), e a linha diz isso.

O SQL só leva o fim do número como parâmetro (`LIKE`): a conta exata é feita
aqui, em Python — recorte de texto no SQL tem teto zero em módulo novo.
"""
from __future__ import annotations

import re
from typing import Any

from bd_nativo import banco

LIMITE = 5


def _digitos(texto: Any) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def _sem_pais_nem_zero(d: str) -> str:
    if len(d) in (12, 13) and d.startswith("55"):
        d = d[2:]
    if len(d) in (11, 12) and d.startswith("0"):
        d = d[1:]
    return d


def _chave(wa_id: Any) -> tuple[str, str] | None:
    """(DDD, últimos 8 dígitos) do número do WhatsApp, ou None. O `wa_id`
    sempre traz o país: sem o 55 na frente, não é número do Brasil."""
    d = _digitos(wa_id)
    if len(d) not in (12, 13) or not d.startswith("55"):
        return None
    d = d[2:]
    return d[:2], d[-8:]


def _casa(guardado: Any, ddd: str, fim: str) -> str | None:
    """None se não casa; "" se casa com DDD; "sem DDD" se o cadastro não tem."""
    d = _sem_pais_nem_zero(_digitos(guardado))
    if len(d) < 8 or d[-8:] != fim:
        return None
    if len(d) in (10, 11):
        return "" if d[:2] == ddd else None
    return "sem DDD no cadastro"


def quem_e(con: Any, wa_id: Any) -> dict:
    """Os cartões de firma e os protocolos com o telefone desta conversa.
    `{"cartoes": [...], "protocolos": [...], "foto_cartao_id": int|None}`. SÓ LÊ."""
    vazio = {"cartoes": [], "protocolos": [], "foto_cartao_id": None}
    chave = _chave(wa_id)
    if not chave:
        return vazio
    ddd, fim = chave
    padrao = "%" + fim[-4:] + "%"
    b = banco(con)

    cartoes = []
    for r in b.ler(
            """SELECT id, numero, nome, celular, telefone FROM nt_cartoes
                WHERE celular LIKE %s OR telefone LIKE %s
                ORDER BY id DESC""", (padrao, padrao)):
        nota = _casa(r.get("celular"), ddd, fim)
        if nota is None:
            nota = _casa(r.get("telefone"), ddd, fim)
        if nota is not None:
            cartoes.append({"id": r["id"], "numero": r["numero"], "nome": r["nome"],
                            "nota": nota})
        if len(cartoes) >= LIMITE:
            break

    foto = None
    if cartoes:
        ids = [int(c["id"]) for c in cartoes]
        marcas = ", ".join(["%s"] * len(ids))
        com_foto = {int(r["cartao_id"]) for r in b.ler(
            f"SELECT DISTINCT cartao_id FROM nt_cadastro_imagens "
            f"WHERE especie='FOTO' AND cartao_id IN ({marcas})", tuple(ids))}
        for c in cartoes:
            c["tem_foto"] = int(c["id"]) in com_foto
        foto = next((c["id"] for c in cartoes if c["tem_foto"]), None)

    protocolos = []
    for r in b.ler(
            """SELECT id, numero, data_abertura, atribuicao, interessado, assunto,
                      situacao, telefone FROM cx_protocolos
                WHERE telefone LIKE %s ORDER BY id DESC""", (padrao,)):
        nota = _casa(r.get("telefone"), ddd, fim)
        if nota is not None:
            protocolos.append({k: r.get(k) for k in (
                "id", "numero", "data_abertura", "atribuicao", "interessado",
                "assunto", "situacao")} | {"nota": nota})
        if len(protocolos) >= LIMITE:
            break

    return {"cartoes": cartoes, "protocolos": protocolos, "foto_cartao_id": foto}
