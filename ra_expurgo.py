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

from typing import Any

import ri_frases
from bd_nativo import banco


class ExpurgoError(ValueError):
    """Erro de regra, com frase pronta para o balcão."""


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


def compor_ata(*, registro_numero: Any, ato: dict, motivo: str, agora: str,
               usuario: Any, minuta_id: Any = None, con: Any = None) -> str:
    """O texto da ata. **Só monta — não grava e não decide.**

    Ela é escrita para ser lida por gente, meses depois, e por isso diz o que
    aconteceu em vez de listar campos: o que era o ato, o que estava escrito
    nele, por que saiu e para onde foi.

    O TEXTO SAIU DAQUI — LF06B (19/10/2026): a redação é o papel
    RI_LIVRO3_ATA_EXPURGO (tela de Modelos), que NÃO é o do Livro 2 — as duas
    atas contam coisas diferentes. Aqui fica o que cada claro vale. A ata é
    gravada com o desfazer e lá fica: editar o modelo muda só as atas novas.
    Com `con`, vale o ajuste da casa; sem ele, o padrão.
    """
    return ri_frases.frase(
        "RI_LIVRO3_ATA_EXPURGO", con,
        registro_numero=registro_numero,
        rotulo=f"{_texto(ato.get('tipo'))}-{_texto(ato.get('numero'))}",
        data_ato=_texto(ato.get("data_ato")) or "data não informada",
        agora=agora, minuta_id=minuta_id,
        usuario=_texto(usuario) or "usuário não identificado",
        motivo=_texto(motivo) or "não informado",
        teor=(_texto(ato.get("teor")) or _texto(ato.get("motivo_cancelamento"))
              or "(o ato não tinha teor escrito)"))


def registrar(con: Any, *, registro_id: int,
              registro_numero: Any, ato: dict, motivo: str, agora: str,
              usuario: Any, minuta_id: Any = None) -> int:
    """Grava a ata. ESCREVE. Devolve o `id`.

    **Chamada de dentro da transação que desfaz o ato**, e não depois: é isso
    que impede a ata existir sem o desfazer, e o desfazer sem a ata.
    """
    ata = compor_ata(registro_numero=registro_numero, ato=ato, motivo=motivo,
                     agora=agora, usuario=usuario, minuta_id=minuta_id,
                     con=con)
    return int(banco(con).escrever(
        """INSERT INTO ra_expurgos(registro_id, registro_numero, ato_rotulo,
                                   ato_tipo, ato_numero, ato_data, ato_selo,
                                   ato_teor, minuta_id, motivo, ata,
                                   expurgado_em, expurgado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (int(registro_id), registro_numero,
         f"{_texto(ato.get('tipo'))}-{_texto(ato.get('numero'))}",
         ato.get("tipo"), ato.get("numero"), ato.get("data_ato"),
         ato.get("selo"), ato.get("teor") or ato.get("motivo_cancelamento"),
         minuta_id, _texto(motivo) or None, ata, agora,
         _texto(usuario) or None))[0]["id"])


def um(con: Any, expurgo_id: int) -> dict | None:
    """Uma ata, ou `None`. Só lê."""
    linha = banco(con).um("SELECT * FROM ra_expurgos WHERE id=%s",
                          (int(expurgo_id),))
    return dict(linha) if linha else None


def listar(con: Any, registro_id: int | None = None
           ) -> list[dict]:
    """As atas — de um registro, ou da casa inteira. Só lê."""
    if registro_id is None:
        linhas = banco(con).ler(
            "SELECT * FROM ra_expurgos ORDER BY id DESC")
    else:
        linhas = banco(con).ler(
            "SELECT * FROM ra_expurgos WHERE registro_id=%s ORDER BY id DESC",
            (int(registro_id),))
    return [dict(x) for x in linhas]
