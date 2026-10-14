"""O EXPEDIENTE RESPONDIDO NÃO É «EM ANDAMENTO» — problema #96, 22/09/2026.

A FRASE DO RELATO
    «preciso poder encerrar expediente — nao tem opcao de encerrar», na tela
    do expediente 6, por quem o havia encerrado em 29/08/2026 como RESPONDIDO.

O QUE SE MEDIU EM 23/09/2026
    A ficha estava certa: o expediente 6 está encerrado (RESPONDIDO, com
    `completed_at`), e por isso não oferece o botão. O painel é que estava
    errado: a lista dos abertos e o contador «Expedientes ativos» escreviam à
    mão `NOT IN ('ARQUIVADO')` — metade da regra —, e o expediente 6 aparecia
    em «Expedientes em andamento» com o contador em 15 em vez de 14. Quem
    clicava nele achava uma ficha encerrada sem ter o que fazer.

A RÉGUA
    O que encerra é `expediente_tarefa.ETAPAS_QUE_ENCERRAM`, a mesma regra que
    grava `completed_at`. Estes testes cobram que a lista e o contador tratem
    como encerrado EXATAMENTE o que a ficha trata, etapa por etapa.
"""
from __future__ import annotations

import ast
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import expediente_tarefa as EXPT  # noqa: E402

# As etapas que a tela oferece, lidas do app — e não copiadas para cá.
from app import EXPEDIENT_STAGES  # noqa: E402


def _expediente(con, protocolo: str, stage: str) -> int:
    cur = con.execute(
        """INSERT INTO expedientes (internal_protocol, source, subject,
               category, received_at, stage, created_by, created_at, updated_at)
           VALUES (?, 'MALOTE', 'ofício da corregedoria', 'CORREGEDORIA',
                   '2026-08-01', ?, 1, '2026-08-01T09:00', '2026-08-01T09:00')""",
        (protocolo, stage))
    return int(cur.lastrowid)


@pytest.fixture()
def uma_de_cada(cg_casa_logada):
    """Um expediente em cada etapa que existe."""
    con = sqlite3.connect(cg_casa_logada["banco"])
    ids = {stage: _expediente(con, f"EXP-96-{stage}", stage)
           for stage in EXPEDIENT_STAGES}
    con.commit()
    con.close()
    return cg_casa_logada, ids


def test_as_etapas_que_encerram_existem_na_tela():
    """Régua que nomeia etapa que a tela não tem não encerra nada."""
    assert set(EXPT.ETAPAS_QUE_ENCERRAM) <= set(EXPEDIENT_STAGES)
    assert "RESPONDIDO" in EXPT.ETAPAS_QUE_ENCERRAM


def test_a_lista_dos_abertos_segue_a_regra_da_ficha(uma_de_cada):
    casa, ids = uma_de_cada
    abertos = {r["id"] for r in casa["db"].list_expedientes(only_open=True)}
    for stage, eid in ids.items():
        if EXPT.esta_encerrado(stage):
            assert eid not in abertos, f"{stage} aparece como aberto"
        else:
            assert eid in abertos, f"{stage} sumiu dos abertos"


def test_o_contador_de_ativos_segue_a_regra_da_ficha(uma_de_cada):
    casa, ids = uma_de_cada
    esperados = sum(1 for s in ids if not EXPT.esta_encerrado(s))
    assert casa["db"].dashboard_stats()["open_expedientes"] == esperados


def test_o_painel_nao_mostra_o_respondido_em_andamento(uma_de_cada):
    """O caso do expediente 6, dito na tela onde o Jean o viu.

    13/10/2026: o bloco de expedientes saiu do painel (ordem do oficial); o
    expediente que espera decisão aparece agora em Processos, e a regra que
    este teste guarda — encerrado não aparece como ativo — vale lá."""
    casa, _ids = uma_de_cada
    html = casa["cliente"].get("/processos").get_data(as_text=True)
    assert "EXP-96-RECEBIDO" in html
    assert "EXP-96-RESPONDIDO" not in html
    assert "EXP-96-ARQUIVADO" not in html


def test_a_lista_completa_continua_mostrando_os_encerrados(uma_de_cada):
    """Sair do painel não é sumir: a tela de expedientes mostra todos."""
    casa, ids = uma_de_cada
    todos = {r["id"] for r in casa["db"].list_expedientes()}
    assert set(ids.values()) <= todos


def test_database_nao_escreve_a_etapa_de_encerrar_a_mao():
    """O #96 foi a regra escrita três vezes, e duas delas pela metade.

    `ARQUIVADO` só existe para dizer «encerrou», então nenhum SQL de
    `database.py` pode trazê-lo entre aspas, e nenhum conjunto em Python pode
    listar as duas etapas: quem diz o que encerra é `ETAPAS_QUE_ENCERRAM`.

    `'RESPONDIDO'` sozinho no SQL é LEGÍTIMO, e a primeira versão deste teste
    o acusou por engano: é o `responded_at` de `update_expediente_stage`, a
    data em que houve RESPOSTA — outra pergunta, que não é «encerrou?».
    """
    arvore = ast.parse((RAIZ / "database.py").read_text(encoding="utf-8-sig"))
    achados = []
    for no in ast.walk(arvore):
        if (isinstance(no, ast.Constant) and isinstance(no.value, str)
                and "'ARQUIVADO'" in no.value):
            achados.append(f"linha {no.lineno}: SQL com 'ARQUIVADO' à mão")
        if isinstance(no, (ast.Set, ast.Tuple, ast.List)):
            valores = {e.value for e in no.elts if isinstance(e, ast.Constant)}
            if {"RESPONDIDO", "ARQUIVADO"} <= valores:
                achados.append(f"linha {no.lineno}: as etapas que encerram "
                               "escritas à mão")
    assert not achados, "\n".join(achados)
