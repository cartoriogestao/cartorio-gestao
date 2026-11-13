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


# ------------------------------------------------- 11/11/2026: suíte na fila e teste que ainda vale


def test_suite_na_fila_do_executor_espera_em_vez_de_pedir_outra():
    # A rodada do PR espera o executor sem ter postado nem o pendente: não é «sem resultado».
    assert F.decidir([pr(1, suite=None, suite_na_fila=True)], DONO) == []
    prs = [pr(1, suite=None, suite_na_fila=True), pr(2, suite=None)]
    assert F.decidir(prs, DONO) == []


def test_verde_com_rodada_nova_na_fila_espera_ela():
    assert F.decidir([pr(1, suite_na_fila=True)], DONO) == []


def test_main_andou_longe_do_pr_e_o_verde_entra_sem_refazer():
    assert F.decidir([pr(1, teste_vencido=False)], DONO) == [("mesclar", 1)]


def test_main_andou_no_que_o_pr_toca_e_o_teste_se_refaz():
    assert F.decidir([pr(1, teste_vencido=True)], DONO) == [("disparar", 1)]


def test_teste_vencido_espera_a_suite_que_corre():
    prs = [pr(1, suite="pending"), pr(2, teste_vencido=True)]
    assert F.decidir(prs, DONO) == []


def test_sobrepoe_pelo_arquivo_do_pr_ou_pelo_de_base():
    assert not F.sobrepoe(["despesas.py", "templates/a.html"], ["wa_atendente.py"])
    assert F.sobrepoe(["despesas.py"], ["despesas.py", "tests/test_despesas.py"])
    for base in ("requirements.txt", "tests/conftest.py", "banco_pg.py", "app.py",
                 "ci/suite/rodar.sh", "ci/suite/Dockerfile"):
        assert F.sobrepoe([base], ["wa_atendente.py"]), base
    # A fila e os workflows não mudam o resultado dos testes de um PR.
    for fora in ("ci/fila.py", ".github/workflows/suite.yml", "docs/CI_EXECUTOR.md"):
        assert not F.sobrepoe([fora], ["wa_atendente.py"]), fora
    # Lista cortada: não se sabe, então refaz.
    assert F.sobrepoe(None, ["a.py"]) and F.sobrepoe(["a.py"], None)


def test_na_fila_pelo_nome_da_rodada_ou_pela_branch_antiga():
    p = pr(7, branch="feature-x")
    assert F.na_fila(p, [{"display_title": "suite #7", "event": "workflow_dispatch", "head_branch": "main"}])
    assert F.na_fila(p, [{"display_title": "Um título", "event": "pull_request_target",
                          "head_branch": "feature-x"}])
    assert not F.na_fila(p, [{"display_title": "suite #70", "event": "workflow_dispatch",
                              "head_branch": "main"}])
    assert not F.na_fila(p, [{"display_title": "suite #8", "event": "pull_request_target",
                              "head_branch": "outra"}])


class _GitHubDeEnsaio(F.GitHub):
    """Responde da tabela, sem rede."""

    def __init__(self, respostas):
        super().__init__("dono-exemplo/repo", "sem-token")
        self.respostas, self.pedidos = respostas, []

    def pedir(self, metodo, caminho, corpo=None):
        self.pedidos.append(caminho)
        for prefixo, resposta in self.respostas.items():
            if caminho.startswith(prefixo):
                return resposta
        raise AssertionError(f"pedido inesperado: {caminho}")


MAIN_TESTADO = "a" * 40


def test_julgar_o_teste_pelo_main_que_a_suite_gravou():
    gh = _GitHubDeEnsaio({
        f"/compare/{MAIN_TESTADO}...main": {"ahead_by": 2, "files": [{"filename": "despesas.py"}]},
        "/pulls/1/files": [{"filename": "wa_atendente.py"}],
    })
    p = pr(1)
    gh.julgar_o_teste(p, MAIN_TESTADO)
    assert p.teste_vencido is False
    gh.respostas["/pulls/1/files"] = [{"filename": "despesas.py"}]
    gh.julgar_o_teste(p, MAIN_TESTADO)
    assert p.teste_vencido is True


def test_julgar_o_teste_sem_o_main_gravado_usa_onde_a_branch_saiu():
    gh = _GitHubDeEnsaio({
        "/compare/main...sha1": {"merge_base_commit": {"sha": MAIN_TESTADO}},
        f"/compare/{MAIN_TESTADO}...main": {"ahead_by": 0, "files": []},
    })
    p = pr(1, teste_vencido=True)
    gh.julgar_o_teste(p, None)
    assert p.teste_vencido is False
    assert "/compare/main...sha1" in gh.pedidos


def test_julgar_o_teste_com_a_comparacao_cortada_refaz():
    gh = _GitHubDeEnsaio({
        f"/compare/{MAIN_TESTADO}...main": {
            "ahead_by": 40, "files": [{"filename": f"m{i}.py"} for i in range(F.LIMITE_DA_COMPARACAO)]},
        "/pulls/1/files": [{"filename": "x.py"}],
    })
    p = pr(1)
    gh.julgar_o_teste(p, MAIN_TESTADO)
    assert p.teste_vencido is True
