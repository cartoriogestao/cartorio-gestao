"""As notas de revisão do ato do Registro de Imóveis.

O QUE ELAS SÃO, E POR QUE VIRARAM TABELA
    O ato chega ao sistema por importação — a minuta foi escrita fora, revista
    fora, e entra aqui para ser conferida e selada. A revisão quase sempre
    deixa coisa para olhar antes de o ato valer: uma área que cresceu 35%, um
    remanescente que ninguém apurou, um emolumento que falta escrever.

    Até 15/09/2026 esse resto morava numa conversa e num `.docx` ao lado, e
    quem selava dias depois não tinha como saber que havia o que olhar. Agora
    mora no ato, e a ficha o mostra.

A NOTA NÃO TRAVA, E ISSO É DELIBERADO
    Quando ela existe, o ato **já está lavrado**: travar seria desfazer ato,
    e desfazer ato é decisão do delegatário, nunca de uma lista. É a regra do
    CNIB, das fraudes e do usucapião outra vez — o módulo prepara e avisa;
    quem decide é quem assina. Há teste que varre os nomes públicos daqui
    procurando `recusar`, `impedir`, `travar` e `bloquear`.

BAIXAR EXIGE ESCREVER O QUE SE DECIDIU
    Sem isso a baixa é um clique que apaga a pergunta sem respondê-la, e a
    correição lê «conferido» sem saber conferido como. É a dispensa com
    motivo escrito do usucapião, aplicada aqui.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from bd_nativo import banco

# As duas situações, e não mais: ou a nota espera alguém, ou alguém respondeu.
ABERTA = "ABERTA"
BAIXADA = "BAIXADA"
SITUACOES = (ABERTA, BAIXADA)

# De onde a nota veio. `IMPORTACAO` é a que o próprio sistema anota ao trazer
# um ato de fora — e é a que mais importa, porque ninguém a digitou e por isso
# ninguém se lembra dela.
ORIGENS = ("MANUAL", "IMPORTACAO", "REVISAO")


class RevisaoError(ValueError):
    """Erro de regra, com mensagem pronta para o balcão."""


def _linha(con: sqlite3.Connection, revisao_id: int) -> dict | None:
    return banco(con).um("SELECT * FROM ri_revisoes WHERE id=%s",
                         (int(revisao_id),))


def anotar(con: sqlite3.Connection, *, matricula_id: int, assunto: str,
           nota: str, agora: str, ato_id: Any = None,
           origem: str = "MANUAL", usuario: Any = None) -> dict:
    """Anota o que falta conferir naquele ato. ESCREVE.

    `ato_id` vazio quer dizer que a nota é da matrícula inteira, e não de um
    ato — o caso de «esta ficha veio de importação, confira a cadeia».
    """
    assunto = (assunto or "").strip()
    texto = (nota or "").strip()
    if len(assunto) < 3:
        raise RevisaoError("A nota de revisão precisa de um assunto — em três "
                           "palavras, o que se vai conferir.")
    if len(texto) < 10:
        raise RevisaoError("Escreva o que precisa ser conferido, com pelo "
                           "menos dez letras. Nota que não diz o que olhar "
                           "não ajuda quem for olhar.")
    if origem not in ORIGENS:
        raise RevisaoError(
            f"Origem {origem!r} não existe. As que há são: {', '.join(ORIGENS)}.")

    bd = banco(con)
    if not bd.um("SELECT 1 AS um FROM ri_matriculas WHERE id=%s",
                 (int(matricula_id),)):
        raise RevisaoError(f"Matrícula {matricula_id} não encontrada.")
    if ato_id is not None:
        dono = bd.um("SELECT matricula_id FROM ri_atos WHERE id=%s",
                     (int(ato_id),))
        if not dono:
            raise RevisaoError(f"Ato {ato_id} não encontrado.")
        # O ato tem de ser DESTA matrícula. Sem esta conferência, um id trocado
        # penduraria a nota na ficha de outro imóvel — e ninguém desconfia de
        # uma nota que aparece onde se esperava encontrar alguma.
        if int(dono["matricula_id"]) != int(matricula_id):
            raise RevisaoError(
                f"O ato {ato_id} é da matrícula {dono['matricula_id']}, e não da "
                f"{matricula_id}. A nota ficaria na ficha errada.")

    novo = bd.escrever(
        """INSERT INTO ri_revisoes
           (matricula_id, ato_id, assunto, nota, origem, situacao,
            anotada_em, anotada_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (int(matricula_id), int(ato_id) if ato_id is not None else None,
         assunto, texto, origem, ABERTA, agora, usuario))[0]["id"]
    return {"id": int(novo), "assunto": assunto, "situacao": ABERTA}


def baixar(con: sqlite3.Connection, revisao_id: int, *, decisao: str,
           agora: str, usuario: Any = None) -> dict:
    """Dá baixa na nota, escrevendo o que se decidiu. ESCREVE."""
    texto = (decisao or "").strip()
    if len(texto) < 10:
        raise RevisaoError(
            "Escreva o que você conferiu e decidiu, com pelo menos dez "
            "letras. É isso que a correição vai ler no lugar da pergunta.")
    linha = _linha(con, revisao_id)
    if not linha:
        raise RevisaoError(f"Nota de revisão {revisao_id} não encontrada.")
    if linha["situacao"] == BAIXADA:
        raise RevisaoError(
            f"Esta nota já foi baixada em {linha['baixada_em']}. O que foi "
            f"decidido continua escrito nela.")

    banco(con).escrever(
        """UPDATE ri_revisoes
           SET situacao=%s, baixada_em=%s, baixada_por=%s, baixa_decisao=%s
           WHERE id=%s""",
        (BAIXADA, agora, usuario, texto, int(revisao_id)))
    return {"id": int(revisao_id), "situacao": BAIXADA, "decisao": texto}


def da_matricula(con: sqlite3.Connection, matricula_id: int,
                 *, so_abertas: bool = False) -> list[dict]:
    """As notas daquela matrícula, das mais novas para as mais antigas. SÓ LÊ."""
    sql = """SELECT r.*, a.tipo AS ato_tipo, a.numero AS ato_numero
             FROM ri_revisoes r
             LEFT JOIN ri_atos a ON a.id = r.ato_id
             WHERE r.matricula_id=%s"""
    if so_abertas:
        sql += f" AND r.situacao='{ABERTA}'"
    sql += " ORDER BY r.id DESC"
    return banco(con).ler(sql, (int(matricula_id),))


def do_ato(con: sqlite3.Connection, ato_id: int,
           *, so_abertas: bool = False) -> list[dict]:
    """As notas daquele ato. SÓ LÊ."""
    sql = "SELECT * FROM ri_revisoes WHERE ato_id=%s"
    if so_abertas:
        sql += f" AND situacao='{ABERTA}'"
    sql += " ORDER BY id DESC"
    return banco(con).ler(sql, (int(ato_id),))


def abertas(con: sqlite3.Connection) -> list[dict]:
    """Tudo o que espera conferência, da casa inteira. SÓ LÊ.

    É a tela que se abre antes de selar o dia: o ato, a matrícula e o que
    falta olhar em cada um.
    """
    return banco(con).ler(
        f"""SELECT r.*, m.numero AS matricula_numero, m.livro AS matricula_livro,
                   a.tipo AS ato_tipo, a.numero AS ato_numero, a.data_ato
            FROM ri_revisoes r
            JOIN ri_matriculas m ON m.id = r.matricula_id
            LEFT JOIN ri_atos a ON a.id = r.ato_id
            WHERE r.situacao='{ABERTA}'
            ORDER BY r.anotada_em DESC, r.id DESC""")


# NÃO HÁ `quantas_abertas` AQUI, e ela chegou a existir.
#
# Escrevi uma função que contava as notas abertas, e nenhuma tela a chamava:
# a tela das revisões conta pelo tamanho da lista que já pediu, e a ficha da
# matrícula também. **Função pronta sem chamador é a arma que alguém religa
# depois** — já aconteceu cinco vezes neste projeto —, e o varredor
# `test_funcao_sem_tela` a pegou na primeira suíte. Apagada, e não desligada.
#
# Quem precisar do número conta o que `da_matricula(..., so_abertas=True)` ou
# `abertas()` devolvem: uma fonte só, que é a mesma que a tela mostra.
