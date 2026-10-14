"""Como avisar o cliente: telefone OU e-mail, pelo menos um — ordem do oficial, 10/10/2026.

    «colocar telefone ou email como obrigatorios na prenotacao ou protocolo geral»

POR QUE ISTO EXISTE. Os dois campos sempre estiveram nas duas telas, e o balcão
os deixava em branco. Medido em 10/10/2026 na produção: das 19 prenotações
abertas pelo sistema novo, 10 têm telefone e NENHUMA tem e-mail; dos 112
protocolos gerais abertos por ele, 12 têm telefone e 1 tem e-mail. Sem contato,
a nota devolutiva e o vencimento da prenotação não chegam a ninguém — e quem
perde a prioridade é o cliente.

A REGRA É «PELO MENOS UM», E NÃO OS DOIS: muita gente do balcão não tem e-mail,
e exigir os dois faria inventar endereço. O que se recusa é o vazio e o
valor que não serve para avisar:
  - telefone com menos de 10 dígitos (sem DDD não se liga de fora da cidade);
  - e-mail sem a forma nome@dominio.algo.

VALE PARA ABRIR, E NÃO PARA EDITAR. Os registros antigos ficam como estão —
recusar a correção de outro campo de uma ficha antiga por falta de telefone
seria travar o balcão por um dado que ninguém tem à mão.
"""
from __future__ import annotations

import re

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ContatoError(ValueError):
    """Erro de regra, com a frase pronta para o balcão."""


def _digitos(v) -> str:
    return "".join(c for c in str(v or "") if c.isdigit())


def exigir(telefone, email) -> tuple[str | None, str | None]:
    """Confere o contato e devolve (telefone, email) limpos. Recusa sem nenhum válido."""
    tel = str(telefone or "").strip() or None
    mail = str(email or "").strip() or None
    if tel and not 10 <= len(_digitos(tel)) <= 13:
        raise ContatoError(
            f"O telefone «{tel}» não serve para avisar o cliente: informe com DDD "
            f"(ex.: (99) 99999-9999).")
    if mail and not _EMAIL.match(mail):
        raise ContatoError(
            f"O e-mail «{mail}» não está completo (ex.: nome@provedor.com).")
    if not tel and not mail:
        raise ContatoError(
            "Informe o telefone ou o e-mail do cliente — pelo menos um. É por ele "
            "que a serventia avisa da nota devolutiva e do prazo.")
    return tel, mail
