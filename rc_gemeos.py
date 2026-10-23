"""Gêmeos — art. 234, e as duas regras que ele traz.

    «Art. 234. No caso de gêmeos, deverá constar **no assento de cada um** a
     **ordem de nascimento**.
     Parágrafo único. Os gêmeos que tiverem o **prenome igual** deverão ser
     inscritos com **duplo prenome ou nome completo diverso**, de modo que
     possam distinguir-se.»

SÃO DOIS ASSENTOS, E NÃO UM
    «no assento de cada um» — e o modelo do E-Ofício desta casa confirma: ele é
    um termo por criança, com a frase que aponta para o irmão («É o primeiro
    gêmeo a nascer, irmão de …, matrícula n.º …»). Um termo só para os dois faria
    dois registros caberem num número — e cada pessoa tem o seu.

E `ibge_gemeo` NÃO RESPONDE ESTA PERGUNTA
    O campo que já existe é o do **IBGE** — 1 não é gêmeo, 2 gêmeo, 3 trigêmeo ou
    mais, 9 ignorado. Ele diz **se** é gêmeo; o art. 234 exige **qual é a
    ordem**. Usar um pelo outro faria o assento cumprir a remessa e descumprir a
    lei — e é a mesma armadilha da palavra que quer dizer duas coisas em dois
    lugares, que este projeto já pagou três vezes.

A SEGUNDA REGRA É UMA RECUSA, E ELA PROTEGE OS DOIS
    Gêmeos com o mesmo prenome «deverão ser inscritos com duplo prenome ou nome
    completo diverso, **de modo que possam distinguir-se**». Dois irmãos com
    nome idêntico, mesma filiação e mesma data de nascimento são duas pessoas
    que nenhum documento separa — e o estrago aparece a vida inteira, em
    matrícula de escola, em conta de banco, em benefício.

    **Este módulo não recusa o registro**: ele **avisa**, com o artigo, antes de
    lavrar. Registro de nascimento é imperativo legal (art. 250), e quem decide
    é o oficial.
"""
from __future__ import annotations

import sqlite3

from bd_nativo import banco
import unicodedata
from typing import Any


class GemeosError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


ARTIGO = "art. 234 do Código de Normas do TJMA"

# O FATO DE SER GEMEO E REQUISITO LEGAL DO ASSENTO — art. 233, III, que repete o
# art. 54 da Lei 6.015/1973. Nao e informacao acessoria.
E_REQUISITO_DO_ASSENTO = (
    "o fato de ser gêmeo é **requisito legal do assento** (art. 233, III, que "
    "repete o art. 54 da Lei nº 6.015/1973) — e não informação acessória")

ORDEM_OBRIGATORIA = (
    "no caso de gêmeos, deverá constar **no assento de cada um** a ordem de "
    "nascimento (art. 234)")

PRENOME_IGUAL = (
    "os gêmeos que tiverem o prenome igual deverão ser inscritos com **duplo "
    "prenome ou nome completo diverso**, de modo que possam distinguir-se "
    "(art. 234, parágrafo único)")

# O CAMPO DO IBGE E OUTRO, e a diferenca importa.
O_CAMPO_DO_IBGE_NAO_SERVE = (
    "`ibge_gemeo` diz **se** é gêmeo — 1 não é, 2 gêmeo, 3 trigêmeo ou mais, 9 "
    "ignorado. O art. 234 exige **qual é a ordem**, e um campo não responde a "
    "outra pergunta")

# O CODIGO DO IBGE QUE DIZ QUE HOUVE PARTO MULTIPLO. Medido em
# `ibge_remessa.GEMEO`: o 1 e parto unico e o 9 e ignorado.
CODIGOS_DE_PARTO_MULTIPLO = (2, 3)


def _texto(v: Any) -> str:
    """O valor como texto, e vazio quando não há. Nunca `str(v or "")`."""
    if v is None:
        return ""
    return str(v).strip()


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t)
                   if unicodedata.category(c) != "Mn")


def prenome(nome: Any) -> str:
    """O primeiro nome, sem acento e em maiúsculas. Só calcula.

    SEM ACENTO E SEM CAIXA porque «José» e «JOSE» são o mesmo prenome para quem
    tem de distinguir dois irmãos — e `UPPER` do SQLite é ASCII, o que já deixou
    o CNIB sem achar ninguém por nome.
    """
    partes = _texto(nome).split()
    return _sem_acento(partes[0]).upper() if partes else ""


def prenomes_se_distinguem(nomes: list[str]) -> dict:
    """Se os prenomes dos gêmeos se distinguem. Só calcula.

    **NÃO RECUSA — AVISA.** Registro de nascimento é imperativo legal (art. 250),
    e quem decide é o oficial. Mas o aviso sai **antes** de lavrar, com o artigo:
    dois irmãos com nome idêntico, mesma filiação e mesma data de nascimento são
    duas pessoas que nenhum documento separa.
    """
    limpos = [n for n in (_texto(x) for x in nomes) if n]
    if len(limpos) < 2:
        return {"distinguem": True, "aviso": "", "repetidos": []}
    # O NOME COMPLETO DIVERSO JA RESOLVE, e e o que o paragrafo unico permite:
    # «duplo prenome **ou** nome completo diverso».
    completos = [_sem_acento(n).upper() for n in limpos]
    if len(set(completos)) == len(completos):
        return {"distinguem": True, "aviso": "", "repetidos": []}
    repetidos = sorted({n for n in limpos
                        if completos.count(_sem_acento(n).upper()) > 1})
    return {
        "distinguem": False,
        "repetidos": repetidos,
        "aviso": ("Estes gêmeos ficariam com o mesmo nome: "
                  + ", ".join(f"«{n}»" for n in repetidos)
                  + ". O art. 234, parágrafo único manda inscrevê-los com duplo "
                    "prenome ou nome completo diverso, de modo que possam "
                    "distinguir-se — dois irmãos com nome idêntico, mesma "
                    "filiação e mesma data de nascimento são duas pessoas que "
                    "nenhum documento separa."),
    }


def e_parto_multiplo(ibge_gemeo: Any) -> bool:
    """Se o assento diz que houve parto múltiplo. Só calcula.

    **A AFINIDADE DA COLUNA CONVERTE NA ENTRADA**: `ibge_gemeo` é INTEGER, a tela
    grava `"2"` e o SQLite guarda `2`. Comparar com texto acharia zero — é a
    quarta vez que este projeto tropeça nisso, e por isso a comparação é feita
    depois de converter.
    """
    try:
        return int(ibge_gemeo) in CODIGOS_DE_PARTO_MULTIPLO
    except (TypeError, ValueError):
        return False


def o_que_falta(assento: dict) -> list[str]:
    """O que falta naquele assento de gêmeo. Só calcula."""
    faltas: list[str] = []
    if not e_parto_multiplo(assento.get("ibge_gemeo")):
        return faltas
    try:
        ordem = int(assento.get("gemeo_ordem") or 0)
    except (TypeError, ValueError):
        ordem = 0
    if ordem < 1:
        faltas.append(
            "a ordem de nascimento — o art. 234 manda que ela conste no assento "
            "de CADA um dos gêmeos")
    return faltas


def pendentes(con: sqlite3.Connection, limite: int = 500) -> list[dict]:
    """Os assentos de parto múltiplo sem a ordem de nascimento. Só lê.

    A LISTA É MEDIDA, sem tabela nova: quem sai dela é o assento que ganhou a
    ordem. É a disciplina de `inacabados.py`.
    """
    linhas = banco(con).ler(
        """SELECT id, numero, nome, data_ato, ibge_gemeo, gemeo_ordem
             FROM rc_assentos
            WHERE especie = 'NASCIMENTO'
              AND COALESCE(situacao,'ATIVO') <> 'CANCELADO'
              AND ibge_gemeo IS NOT NULL
         ORDER BY data_ato IS NULL, data_ato, id
            LIMIT %s""", (limite,))
    saida = []
    for linha in linhas:
        d = dict(linha)
        faltas = o_que_falta(d)
        if faltas:
            saida.append(dict(d, faltas=faltas))
    return saida


def quantas_pendentes(con: sqlite3.Connection) -> int:
    """Quantos assentos de gêmeo estão sem a ordem. Só lê."""
    return len(pendentes(con, limite=100000))


def irmaos(con: sqlite3.Connection, assento_id: int) -> list[dict]:
    """Os outros assentos ligados a este como gêmeos. Só lê.

    **A LIGAÇÃO É RECÍPROCA POR CONSTRUÇÃO**: a busca olha os dois lados, de modo
    que amarrar A ao B faz B aparecer em A sem ninguém precisar amarrar duas
    vezes. Depender de duas amarrações produziria o par pela metade — e o par
    pela metade é o que faz a certidão de um irmão não citar o outro.
    """
    return banco(con).ler(
        """SELECT id, numero, nome, matricula, gemeo_ordem
             FROM rc_assentos
            WHERE (gemeo_irmao_id = %s OR id = (SELECT gemeo_irmao_id
                                                 FROM rc_assentos WHERE id = %s))
              AND id <> %s
         ORDER BY gemeo_ordem NULLS FIRST, id""",
        (int(assento_id), int(assento_id), int(assento_id)))


def amarrar(con: sqlite3.Connection, assento_id: int, *, irmao_id: int,
            ordem: int, agora: str) -> None:
    """Grava a ordem de nascimento e a ligação com o irmão. GRAVA.

    **A ORDEM É DE CADA UM**, e por isso se grava um por vez: o art. 234 manda
    que ela conste no assento de cada um, e um botão que gravasse «1 e 2» de uma
    vez suporia que quem está na tela sabe a ordem dos dois.
    """
    if int(assento_id) == int(irmao_id):
        raise GemeosError("Um assento não é gêmeo de si mesmo.")
    if int(ordem) < 1:
        raise GemeosError(
            "A ordem de nascimento começa em 1 — é o primeiro a nascer.")
    bd = banco(con)
    for alvo in (assento_id, irmao_id):
        existe = bd.um("SELECT id FROM rc_assentos WHERE id=%s",
                       (int(alvo),))
        if not existe:
            raise GemeosError(f"O assento {alvo} não existe.")
    bd.escrever(
        """UPDATE rc_assentos SET gemeo_ordem=%s, gemeo_irmao_id=%s
            WHERE id=%s""", (int(ordem), int(irmao_id), int(assento_id)))


def artigos_citados() -> tuple[str, ...]:
    """Para o oficial conferir contra o Código de Normas."""
    return ("art. 54 da Lei nº 6.015/1973", "art. 233, III", "art. 234",
            "art. 234, parágrafo único", "art. 250")
