"""A ATA DE OCORRÊNCIA DO LIVRO 3 — o papel de quando um ato deixa de existir.

Item 6 da fila. No Livro 2 é `ri_expurgos`, e o desenho é o mesmo pela mesma
razão: **a auditoria responde «quem e quando»; a correição pergunta «o que
estava escrito naquele ato»** — e essa resposta só existe aqui, porque o ato
saiu do livro.

**A ATA NASCE DO «DEVOLVER À MINUTA»**, que é o desfazer deste livro, e as duas
coisas acontecem **na mesma transação**: ata sem ato desfeito, e ato desfeito
sem ata, são os dois jeitos de isto dar errado.

**ELA GUARDA O TEOR INTEIRO.** A minuta também o guarda, e isso não é
duplicação inútil: a minuta pode ser descartada, revisada ou reescrita — a ata
é o que ficou **como estava** no momento em que o ato saiu.
"""
from __future__ import annotations

import sqlite3
from typing import Any


class ExpurgoError(ValueError):
    """Erro de regra, com frase pronta para o balcão."""


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


def compor_ata(*, registro_numero: Any, ato: dict, motivo: str, agora: str,
               usuario: Any, minuta_id: Any = None) -> str:
    """O texto da ata. **Só monta — não grava e não decide.**

    Ela é escrita para ser lida por gente, meses depois, e por isso diz o que
    aconteceu em vez de listar campos: o que era o ato, o que estava escrito
    nele, por que saiu e para onde foi.
    """
    rotulo = f"{_texto(ato.get('tipo'))}-{_texto(ato.get('numero'))}"
    linhas = [
        "ATA DE OCORRÊNCIA — LIVRO 3 (REGISTRO AUXILIAR)",
        "",
        (f"Registro nº {registro_numero}. Ato {rotulo}, "
         f"de {_texto(ato.get('data_ato')) or 'data não informada'}."),
        "",
        (f"Em {agora}, o ato acima foi DESFEITO e devolvido à condição de "
         f"minuta"
         + (f" (minuta nº {minuta_id})" if minuta_id else "")
         + f", por {_texto(usuario) or 'usuário não identificado'}."),
        "",
        f"MOTIVO: {_texto(motivo) or 'não informado'}.",
        "",
        ("O ato não chegou a receber selo — ato com selo não se desfaz por "
         "este caminho."),
        "",
        "TEOR DO ATO DESFEITO, como estava:",
        "",
        _texto(ato.get("teor")) or _texto(ato.get("motivo_cancelamento"))
        or "(o ato não tinha teor escrito)",
        "",
        "Nada mais. Esta ata é a única cópia do que saiu do livro.",
    ]
    return "\n".join(linhas)


def registrar(con: sqlite3.Connection, *, registro_id: int,
              registro_numero: Any, ato: dict, motivo: str, agora: str,
              usuario: Any, minuta_id: Any = None) -> int:
    """Grava a ata. ESCREVE. Devolve o `id`.

    **Chamada de dentro da transação que desfaz o ato**, e não depois: é isso
    que impede a ata existir sem o desfazer, e o desfazer sem a ata.
    """
    ata = compor_ata(registro_numero=registro_numero, ato=ato, motivo=motivo,
                     agora=agora, usuario=usuario, minuta_id=minuta_id)
    cursor = con.execute(
        """INSERT INTO ra_expurgos(registro_id, registro_numero, ato_rotulo,
                                   ato_tipo, ato_numero, ato_data, ato_selo,
                                   ato_teor, minuta_id, motivo, ata,
                                   expurgado_em, expurgado_por)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (int(registro_id), registro_numero,
         f"{_texto(ato.get('tipo'))}-{_texto(ato.get('numero'))}",
         ato.get("tipo"), ato.get("numero"), ato.get("data_ato"),
         ato.get("selo"), ato.get("teor") or ato.get("motivo_cancelamento"),
         minuta_id, _texto(motivo) or None, ata, agora,
         _texto(usuario) or None))
    return int(cursor.lastrowid)


def um(con: sqlite3.Connection, expurgo_id: int) -> dict | None:
    """Uma ata, ou `None`. Só lê."""
    linha = con.execute("SELECT * FROM ra_expurgos WHERE id=?",
                        (int(expurgo_id),)).fetchone()
    return dict(linha) if linha else None


def listar(con: sqlite3.Connection, registro_id: int | None = None
           ) -> list[dict]:
    """As atas — de um registro, ou da casa inteira. Só lê."""
    if registro_id is None:
        linhas = con.execute(
            "SELECT * FROM ra_expurgos ORDER BY id DESC").fetchall()
    else:
        linhas = con.execute(
            "SELECT * FROM ra_expurgos WHERE registro_id=? ORDER BY id DESC",
            (int(registro_id),)).fetchall()
    return [dict(x) for x in linhas]
