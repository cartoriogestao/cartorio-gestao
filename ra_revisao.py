"""O QUE REVISAR ANTES DE SELAR, no Livro 3 — item 2 da fila do oficial.

No Livro 2 isto é `ri_revisao.py`, de 15/09/2026, e nasceu de um pedido dele:
*«criar um campo (se não houver) para notas de revisão no sistema a serem
baixadas antes da lavratura»*.

**A NOTA NÃO TRAVA NADA.** Quem decide se o ato sai é quem assina — a nota
avisa. É a mesma régua do CNIB, das fraudes e do usucapião, e há teste que
varre os nomes públicos deste módulo procurando verbo de recusa.

**BAIXAR EXIGE ESCREVER O QUE SE DECIDIU.** Sem isso a baixa apaga a pergunta
sem respondê-la, e a mesma volta amanhã — e na terceira vez ninguém lê mais.
E **baixada não some**: fica na ficha com a decisão escrita, porque é ela que
a correição lê.

**TABELA PRÓPRIA, E A RAZÃO É A CHAVE.** Em `ri_revisoes` as duas estrangeiras
apontam para `ri_matriculas` e `ri_atos`; uma nota do Livro 3 não tem matrícula
nenhuma. Dar àquela tabela um par livro/registro faria a chave estrangeira do
RI deixar de valer para metade das linhas — **e chave estrangeira que só vale
às vezes não vale**.

**A REGRA, PORÉM, É A MESMA — e isso se guarda por teste.** Os pisos do assunto
e da nota e as palavras das situações são lidos de `ri_revisao`, e não
reescritos aqui: duas cópias divergem no primeiro conserto, e aí a mesma casa
passaria a exigir coisas diferentes em dois livros.

**E ELA ALCANÇA A MINUTA, o que a do Livro 2 não faz.** Aqui a minuta é onde o
ato mora antes de existir; a nota que diz «conferir a área antes de lavrar»
tem de estar pendurada nela, e não num ato que ainda não há.
"""
from __future__ import annotations

from typing import Any

from bd_nativo import banco

# AS PALAVRAS E OS PISOS SÃO OS DO LIVRO 2, lidos de lá. Ver o cabeçalho.
from ri_revisao import ABERTA, BAIXADA, ORIGENS, SITUACOES  # noqa: F401

# Os dois pisos do Livro 2, medidos no código dele em 21/09/2026: três letras
# para o assunto e dez para a nota e para a decisão.
MINIMO_DO_ASSUNTO = 3
MINIMO_DO_TEXTO = 10


class RevisaoError(ValueError):
    """Erro de regra, com frase pronta para o balcão — vira `flash(danger)`."""


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


def anotar(con, *, registro_id: int, assunto: str,
           nota: str, agora: str, ato_id=None, minuta_id=None,
           origem: str = "MANUAL", usuario=None) -> int:
    """Anota o que precisa ser conferido. ESCREVE. Devolve o `id`.

    **A nota pode ficar no registro, num ato ou numa minuta** — e a da minuta
    é a que mais importa, porque é a que se lê antes de o ato existir.
    """
    assunto, nota = _texto(assunto), _texto(nota)
    if len(assunto) < MINIMO_DO_ASSUNTO:
        raise RevisaoError(
            "Escreva o assunto da nota — é ele que aparece na lista, e é por "
            "ele que quem abre a ficha sabe do que se trata.")
    if len(nota) < MINIMO_DO_TEXTO:
        raise RevisaoError(
            f"Escreva a nota com pelo menos {MINIMO_DO_TEXTO} letras. Uma "
            f"nota que não explica o que conferir não ajuda quem vai conferir.")
    if origem not in ORIGENS:
        raise RevisaoError(f"Origem de nota desconhecida: {origem!r}.")
    bd = banco(con)
    if bd.um("SELECT 1 AS x FROM ra_registros WHERE id=%s",
             (int(registro_id),)) is None:
        raise RevisaoError("Registro do Livro 3 não encontrado.")
    # A NOTA NÃO CAI NA FICHA DE OUTRO REGISTRO. Ninguém desconfia de uma nota
    # que aparece onde se esperava encontrar alguma.
    if ato_id and bd.um(
            "SELECT 1 AS x FROM ra_atos WHERE id=%s AND registro_id=%s",
            (int(ato_id), int(registro_id))) is None:
        raise RevisaoError("Esse ato não é deste registro.")
    if minuta_id and bd.um(
            "SELECT 1 AS x FROM ra_minutas WHERE id=%s AND registro_id=%s",
            (int(minuta_id), int(registro_id))) is None:
        raise RevisaoError("Essa minuta não é deste registro.")
    return int(bd.escrever(
        """INSERT INTO ra_revisoes(registro_id, ato_id, minuta_id, assunto,
                                   nota, origem, situacao, anotada_em,
                                   anotada_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (int(registro_id), ato_id, minuta_id, assunto, nota, origem, ABERTA,
         agora, _texto(usuario) or None))[0]["id"])


def baixar(con, revisao_id: int, *, decisao: str,
           agora: str, usuario=None) -> None:
    """Fecha a nota, **com o que se decidiu escrito dentro**. ESCREVE."""
    decisao = _texto(decisao)
    if len(decisao) < MINIMO_DO_TEXTO:
        raise RevisaoError(
            f"Escreva o que você decidiu, com pelo menos {MINIMO_DO_TEXTO} "
            f"letras — «ok» e «conferi» não respondem à pergunta que a nota "
            f"fez, e é esta linha que a correição lê.")
    bd = banco(con)
    linha = bd.um("SELECT situacao FROM ra_revisoes WHERE id=%s",
                  (int(revisao_id),))
    if not linha:
        raise RevisaoError("Nota de revisão não encontrada.")
    if _texto(linha["situacao"]) == BAIXADA:
        raise RevisaoError(
            "Esta nota já foi baixada. Se há coisa nova a dizer, anote outra "
            "— assim ficam as duas, e a ordem em que se decidiu.")
    bd.escrever(
        """UPDATE ra_revisoes SET situacao=%s, baixa_decisao=%s, baixada_em=%s,
               baixada_por=%s WHERE id=%s""",
        (BAIXADA, decisao, agora, _texto(usuario) or None, int(revisao_id)))


def do_registro(con, registro_id: int, *,
                so_abertas: bool = False) -> list[dict]:
    """As notas daquele registro. Só lê.

    **As baixadas vêm juntas, de propósito**: a decisão escrita é o que se lê
    meses depois, e uma ficha que só mostra o que falta esconde justamente a
    resposta.
    """
    sql = "SELECT * FROM ra_revisoes WHERE registro_id=%s"
    params: list = [int(registro_id)]
    if so_abertas:
        sql += " AND situacao=%s"
        params.append(ABERTA)
    return banco(con).ler(sql + " ORDER BY id", params)


def abertas(con) -> list[dict]:
    """Tudo o que espera conferência no Livro 3, da casa inteira. Só lê."""
    return banco(con).ler(
        """SELECT r.*, g.numero AS registro_numero
             FROM ra_revisoes r JOIN ra_registros g ON g.id = r.registro_id
            WHERE r.situacao=%s ORDER BY r.id""", (ABERTA,))
