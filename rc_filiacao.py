"""A filiação do assento — e a conferência que descobriu que ela está trocada.

COMO ISTO APARECEU
    Em 30/08/2026, montando o termo de referência a partir de um assento real
    da produção, o texto saiu assim:

        «...nasceu uma criança do sexo feminino, que recebeu o nome de ZELIA
         HOLANDA XAVIER SALES, filho de **URSULA VALENTE MIRANDA XAVIER e
         EVANDRO SOUSA SALES**.»

    O declarante era BRUNO, e a ordem estava invertida. Olhando o assento: o
    registro de papel `PAI` é **VITÓRIA**, sexo F; o de papel `MAE` é **BRUNO**,
    sexo M. E os avós acompanham a troca — o «paterno» é OZAMIR **AZEVEDO**, do
    lado da Vitória; o «materno» é MOACIR **BEZERRA**, do lado do Bruno.

    **Não foi o termo que errou: foi o dado que veio trocado da carga.**

O QUE ESTE MÓDULO NÃO FAZ, E É DECISÃO
    **Não conserta nada.** Três razões, e nenhuma é cautela genérica:

      1. **Certidão desses assentos pode já ter saído** com a filiação
         invertida, e o papel que está na mão de alguém não se corrige por
         UPDATE.
      2. A carga mandou esses registros para a **CRC**. Trocar aqui deixaria
         o nosso banco discordando da Central, o que é pior que discordar de
         si mesmo.
      3. **Alguns casos podem não ser erro.** Há assentos de casais do mesmo
         sexo — medidos: três com as duas filiações masculinas —, e ali o sexo
         não denuncia troca nenhuma. Uma correção automática os quebraria.

    A correção de assento é **retificação** (art. 352), e quem a decide é o
    oficial. Este módulo mostra; a decisão é dele.

POR QUE O SEXO É O SINAL, E NÃO O NOME
    Deduzir pai e mãe do prenome seria adivinhar — e adivinhar em cima de nome
    indígena, que esta casa tem muitos, erra mais ainda: entre os 23 casos há
    três Krikati. O sexo é campo declarado, não inferência.
"""
from __future__ import annotations

import sqlite3

PAPEL_PAI = "PAI"
PAPEL_MAE = "MAE"

# OS AVOS ACOMPANHAM A FILIACAO. Se o pai e a mae estao trocados, o «paterno» e
# o «materno» estao trocados junto — foi o que se viu no nº 19.552, pelos
# sobrenomes. Consertar um sem o outro deixaria o assento pior do que esta.
AVOS_DO_PAI = ("AVO_PATERNO", "AVO_PATERNA")
AVOS_DA_MAE = ("AVO_MATERNO", "AVO_MATERNA")

# O QUE FAZ UM CASO SER **SUSPEITO**, e não «errado».
#
#   `PAI` com sexo F **e** `MAE` com sexo M, no mesmo assento. Uma coisa só —
#   um `PAI` sem sexo, ou um `MAE` de sexo estranho sozinho — não basta: pode
#   ser sexo mal preenchido na carga, e acusar isso encheria a lista de ruído.
#   **Lista com ruído ninguém abre duas vezes.**
MOTIVO = ("o registro de papel PAI está com sexo feminino e o de papel MAE "
          "com sexo masculino, no mesmo assento")

O_QUE_FAZER = ("A correção de assento lavrado é **retificação** (art. 352 do "
               "Código de Normas do TJMA), e não conserto no banco: pode já "
               "ter saído certidão com a filiação invertida, e esses dados "
               "foram para a CRC.")


class FiliacaoError(ValueError):
    """Erro de filiação, em português de balcão."""


def filiacao_trocada(con: sqlite3.Connection,
                     limite: int = 500) -> list[dict]:
    """Os assentos em que PAI e MAE parecem invertidos. **Só lê.**

    Medido na produção em 30/08/2026: **23 assentos**, todos vindos da carga
    do acervo.
    """
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        """SELECT a.id, a.numero, a.especie, a.nome, a.data_ato, a.origem,
                  p.id AS pai_id, p.nome AS pai_nome, p.sexo AS pai_sexo,
                  m.id AS mae_id, m.nome AS mae_nome, m.sexo AS mae_sexo
             FROM rc_assentos a
             JOIN rc_pessoas p ON p.assento_id = a.id AND p.papel = ?
             JOIN rc_pessoas m ON m.assento_id = a.id AND m.papel = ?
            WHERE p.sexo = 'F' AND m.sexo = 'M'
              AND COALESCE(a.situacao,'ATIVO') <> 'CANCELADO'
         ORDER BY a.data_ato IS NULL, a.data_ato DESC, a.id DESC
            LIMIT ?""", (PAPEL_PAI, PAPEL_MAE, limite))]


def duas_filiacoes_do_mesmo_sexo(con: sqlite3.Connection,
                                 limite: int = 500) -> list[dict]:
    """Os assentos com as duas filiações do mesmo sexo. **Só lê.**

    **ESTES NÃO SÃO SUSPEITA DE ERRO**, e é por isso que têm lista própria:
    casal do mesmo sexo é assento legítimo e frequente o bastante para não
    caber numa lista chamada «trocada». Separá-los é o que impede alguém de
    «corrigir» o que está certo.

    Medido na produção: três com as duas masculinas.
    """
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        """SELECT a.id, a.numero, a.nome, a.data_ato,
                  p.nome AS pai_nome, p.sexo AS pai_sexo,
                  m.nome AS mae_nome, m.sexo AS mae_sexo
             FROM rc_assentos a
             JOIN rc_pessoas p ON p.assento_id = a.id AND p.papel = ?
             JOIN rc_pessoas m ON m.assento_id = a.id AND m.papel = ?
            WHERE p.sexo = m.sexo AND p.sexo IN ('M','F')
              AND COALESCE(a.situacao,'ATIVO') <> 'CANCELADO'
         ORDER BY a.data_ato IS NULL, a.data_ato DESC, a.id DESC
            LIMIT ?""", (PAPEL_PAI, PAPEL_MAE, limite))]


def sem_sexo(con: sqlite3.Connection, limite: int = 500) -> list[dict]:
    """Filiações sem o sexo informado. **Só lê.**

    Elas não entram na lista de suspeitas — sem o sexo não há sinal nenhum —,
    mas valem por si: **é o sexo que decide como o termo escreve a filiação**,
    e é ele que a remessa do IBGE pede.
    """
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        """SELECT a.id, a.numero, a.nome, a.data_ato,
                  p.papel, p.nome AS pessoa_nome
             FROM rc_assentos a
             JOIN rc_pessoas p ON p.assento_id = a.id
            WHERE p.papel IN (?, ?)
              AND COALESCE(NULLIF(TRIM(COALESCE(p.sexo,'')),''),'') = ''
              AND COALESCE(a.situacao,'ATIVO') <> 'CANCELADO'
         ORDER BY a.data_ato IS NULL, a.data_ato DESC, a.id DESC
            LIMIT ?""", (PAPEL_PAI, PAPEL_MAE, limite))]


def resumo(con: sqlite3.Connection) -> dict:
    """As três contas juntas, para a tela não precisar fazê-las.

    **NUNCA ESCRITAS À MÃO**: o número sai da consulta. Escrito, ele mente no
    dia em que o acervo mudar — que foi o defeito do menu e o do carimbo da
    versão.
    """
    return {
        "trocadas": len(filiacao_trocada(con, limite=100000)),
        "mesmo_sexo": len(duas_filiacoes_do_mesmo_sexo(con, limite=100000)),
        "sem_sexo": len(sem_sexo(con, limite=100000)),
    }
