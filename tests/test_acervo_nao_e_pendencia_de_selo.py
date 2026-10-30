"""O acervo nao vira pendencia de selo nem de cobranca — relato #13.

    «pendencias antigas e do e-oficio nao devem aparecer. Sao atos que ja
     passaram, nao tem mais relevancia e nao devem constar mais como pendencias
     atuais.»

O QUE SE MEDIU NA PRODUCAO, em 30/08/2026

    | tabela      | «sem selo» | do E-Oficio |
    |-------------|------------|-------------|
    | `nt_atos`   |        260 |     **258** |
    | `rc_atos`   |        244 |     **244** |
    | `pt_atos`   |      2.281 |   **2.281** |

    Sao **dois** atos desta casa em 2.785. Depois do conserto: **10** no total
    das quatro tabelas com movimento.

POR QUE ISTO IMPORTA MESMO SEM TELA
    `atos_sem_selo` **ainda nao tinha tela** quando isto foi escrito. Foi por isso
    que o defeito nunca chegou ao balcao.

    **Conserta-se agora para que a tela, quando nascer, nao nasca mentindo.** O
    contrario foi o que aconteceu no painel, no mesmo dia: a lista foi para a
    primeira tela da casa com 21.342 protocolos do E-Oficio dentro, e so nao
    ficou assim porque alguem mediu antes de publicar.

E O QUE SAI NAO SOME CALADO
    `quantos_do_acervo_ficaram_de_fora` responde quantos o filtro tirou. Uma
    lista que encolhe em silencio faz quem a le concluir que o trabalho acabou.
"""
from __future__ import annotations

import glob
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ato_selado as AS                                          # noqa: E402

SEM_SELO = "COALESCE(selo,'') = ''"


@pytest.fixture()
def con(cg_db, cg_db_path):
    c = sqlite3.connect(str(cg_db_path))
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _dois_atos(con):
    """Um do acervo e um desta casa, os dois sem selo e sem cobrança."""
    con.execute(
        "INSERT INTO nt_atos (id, tipo, situacao, origem, data, criado_em) "
        "VALUES (1, 'ESCRITURA', 'LAVRADO', 'EOFICIO', '1990-05-04', '1990-05-04T10:00')")
    con.execute(
        "INSERT INTO nt_atos (id, tipo, situacao, origem, data, criado_em) "
        "VALUES (2, 'ESCRITURA', 'LAVRADO', 'MANUAL', '2026-08-30', '2026-08-30T10:00')")
    con.commit()


def test_o_ato_do_acervo_nao_aparece_como_sem_selo(con):
    """**O caso que ia para a tela.** Comprar selo hoje para ato de 1990 não é
    conserto: é inventar."""
    _dois_atos(con)
    achados = AS.atos_sem_selo(con, "nt_atos")
    assert [a["id"] for a in achados] == [2], \
        "o ato do E-Ofício apareceu como pendência de hoje"


def test_o_que_ficou_de_fora_e_contado(con):
    """**Lista que encolhe em silêncio faz quem a lê concluir que o trabalho
    acabou.**"""
    _dois_atos(con)
    assert AS.quantos_do_acervo_ficaram_de_fora(con, "nt_atos", SEM_SELO) == 1


def test_tabela_sem_coluna_de_origem_nao_ganha_filtro_inventado(con):
    """**Ali não dá para separar, e inventar um filtro esconderia ato desta
    casa.** O silêncio honesto é devolver a lista inteira e contar zero."""
    sem_origem = [t for t in AS.TABELAS_DE_ATO
                  if "origem" not in {r[1] for r in con.execute(
                      f'PRAGMA table_info("{t}")')}]
    if not sem_origem:
        pytest.skip("todas as tabelas de ato têm coluna de origem")
    tabela = sem_origem[0]
    assert AS._so_o_que_esta_casa_lavrou(con, tabela) == ""
    assert AS.quantos_do_acervo_ficaram_de_fora(con, tabela, SEM_SELO) == 0


def test_o_ato_desta_casa_continua_aparecendo(con):
    """**O conserto não pode esconder o que importa.** Os cinco atos de
    18/08/2026 — selo colado como imagem — têm de continuar na lista."""
    _dois_atos(con)
    assert AS.atos_sem_selo(con, "nt_atos"), \
        "a lista ficou vazia — o filtro comeu o que a casa lavrou"


def test_toda_tabela_de_ato_responde_sem_estourar(con):
    """Tabela renomeada ou coluna que falta derrubaria a tela inteira."""
    for tabela in AS.TABELAS_DE_ATO:
        try:
            AS.atos_sem_selo(con, tabela)
        except sqlite3.OperationalError as erro:
            if "no such column: selo" in str(erro):
                continue          # `ri_atos` e `nt_cartoes` guardam noutra coluna
            raise
