"""A regra da fila de merge (ci/fila.py), sem rede: só a decisão."""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "ci"))

import fila as F  # noqa: E402

DONO = "dono-exemplo"


def pr(n, **kw):
    base = dict(numero=n, criado_em=f"2026-11-10T10:{n:02d}:00Z", rascunho=False, autor=DONO,
                mesmo_repositorio=True, estado_merge="clean", suite="success", anti_leak="success",
                head=f"sha{n}", branch=f"b{n}")
    base.update(kw)
    return F.Pr(**base)


def test_verde_e_atualizado_entra():
    assert F.decidir([pr(1)], DONO) == [("mesclar", 1)]


def test_so_a_conta_proprietaria_pronta_e_do_proprio_repositorio():
    for fora in (pr(1, autor="outra-pessoa"), pr(1, rascunho=True), pr(1, mesmo_repositorio=False),
                 pr(1, rotulos={"nao-mesclar"})):
        assert F.decidir([fora], DONO) == []


def test_atras_do_main_atualiza_e_testa_de_novo_em_vez_de_mesclar():
    assert F.decidir([pr(1, estado_merge="behind")], DONO) == [("atualizar", 1), ("disparar", 1)]


def test_um_por_vez_enquanto_uma_suite_corre():
    prs = [pr(1, suite="pending", estado_merge="behind"), pr(2, estado_merge="behind", suite=None)]
    assert F.decidir(prs, DONO) == []


def test_o_verde_atualizado_passa_na_frente_do_que_espera():
    prs = [pr(1, estado_merge="behind"), pr(2)]
    assert F.decidir(prs, DONO) == [("mesclar", 2)]


def test_vermelho_fica_parado_e_a_fila_segue_com_o_proximo():
    prs = [pr(1, suite="failure"), pr(2, estado_merge="behind")]
    assert F.decidir(prs, DONO) == [("atualizar", 2), ("disparar", 2)]


def test_anti_leak_vermelho_nao_entra_mesmo_com_a_suite_verde():
    assert F.decidir([pr(1, anti_leak="failure")], DONO) == []


def test_conflito_ganha_rotulo_uma_vez_so():
    assert F.decidir([pr(1, estado_merge="dirty")], DONO) == [("marcar_conflito", 1)]
    assert F.decidir([pr(1, estado_merge="dirty", rotulos={"conflito"})], DONO) == []


def test_sem_resultado_pede_a_suite():
    assert F.decidir([pr(1, suite=None)], DONO) == [("disparar", 1)]


def test_o_mais_antigo_primeiro():
    prs = [pr(5, suite=None, estado_merge="behind"), pr(3, suite=None, estado_merge="behind")]
    assert F.decidir(prs, DONO) == [("atualizar", 3), ("disparar", 3)]


def test_bloqueado_por_outro_motivo_nao_mescla():
    assert F.decidir([pr(1, estado_merge="blocked")], DONO) == []
