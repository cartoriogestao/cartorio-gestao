"""A fila genérica das Centrais — enfileirar, pegar, falhar, reprocessar.

Nenhum teste aqui fala com Central: o `enviar` é uma função falsa.
"""
from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import banco_pg  # noqa: E402
from banco_de_teste import conexao_de_teste  # noqa: E402

import centrais_fila as FILA  # noqa: E402
import centrais_schema as SCH  # noqa: E402


@pytest.fixture()
def con():
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    SCH.init_centrais_schema(c)
    yield c
    c.close()


class _BancoFalso:
    """O mínimo de `database.Database`: `transaction()` com BEGIN IMMEDIATE."""

    def __init__(self, caminho):
        self.caminho = caminho
        self.aberta = False
        banco_pg.registrar_banco(caminho)
        c = self._conectar()
        SCH.init_centrais_schema(c)
        c.commit()
        c.close()

    def _conectar(self):
        c = sqlite3.connect(self.caminho)
        c.row_factory = sqlite3.Row
        return c

    @contextmanager
    def transaction(self):
        c = self._conectar()
        self.aberta = True
        try:
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            self.aberta = False
            c.close()


@pytest.fixture()
def banco(tmp_path):
    return _BancoFalso(tmp_path / "fila.sqlite3")


def test_enfileirar_e_o_log_do_que_entrou(con):
    novo = FILA.enfileirar(con, "cenprot", "anuencia_processar", "cn_pendencias:7")
    it = FILA.item(con, novo)
    assert it["central"] == "CENPROT" and it["status"] == SCH.PENDENTE
    assert it["ambiente"] == "HOMOLOGACAO" and it["tentativas"] == 0
    assert it["criado_em"] and it["atualizado_em"]
    ev = con.execute("SELECT evento, fila_id FROM centrais_log").fetchall()
    assert [tuple(x) for x in ev] == [("ENFILEIRADO", novo)]


def test_a_mesma_chave_nao_entra_duas_vezes_por_ambiente(con):
    a = FILA.enfileirar(con, "CRA", "remessa", "arq:1", chave="B1.261")
    b = FILA.enfileirar(con, "CRA", "remessa", "arq:1", chave="B1.261")
    c = FILA.enfileirar(con, "CRA", "remessa", "arq:1", chave="B1.261",
                        ambiente="PRODUCAO")
    assert a == b and c != a


@pytest.mark.parametrize("args", [("", "op", "r"), ("CRA", "", "r"),
                                  ("CRA", "op", "")])
def test_enfileirar_recusa_o_incompleto(con, args):
    with pytest.raises(FILA.FilaError):
        FILA.enfileirar(con, *args)


def test_enfileirar_recusa_ambiente_inventado(con):
    with pytest.raises(FILA.FilaError, match="Ambiente"):
        FILA.enfileirar(con, "CRA", "op", "r", ambiente="QUALQUER")


def test_pegar_proximo_marca_e_deixa_producao_de_fora(con):
    p = FILA.enfileirar(con, "CRA", "op", "r1", ambiente="PRODUCAO")
    h = FILA.enfileirar(con, "CRA", "op", "r2")
    vez = FILA.pegar_proximo(con)
    assert vez["id"] == h and vez["status"] == SCH.PROCESSANDO
    assert vez["tentativas"] == 1
    assert FILA.pegar_proximo(con) is None              # produção não vem
    assert FILA.pegar_proximo(con, ambientes=("PRODUCAO",))["id"] == p


def test_falha_retenta_com_espera_e_depois_desiste(con):
    novo = FILA.enfileirar(con, "ONR", "indicador", "ri:1", max_tentativas=2)
    FILA.pegar_proximo(con)
    assert FILA.marcar_falha(con, novo, "caiu") == SCH.PENDENTE
    it = FILA.item(con, novo)
    assert it["erro"] == "caiu" and it["proxima_tentativa_em"]
    assert FILA.pegar_proximo(con) is None             # ainda esperando
    con.execute("UPDATE centrais_fila SET proxima_tentativa_em = "
                "'2000-01-01T00:00:00' WHERE id = ?", (novo,))
    FILA.pegar_proximo(con)
    assert FILA.marcar_falha(con, novo, "caiu de novo") == SCH.FALHOU
    assert FILA.item(con, novo)["proxima_tentativa_em"] is None


def test_falha_definitiva_nao_gasta_tentativa(con):
    novo = FILA.enfileirar(con, "CRA", "op", "r")
    FILA.pegar_proximo(con)
    assert FILA.marcar_falha(con, novo, "400 regra", definitiva=True) == SCH.FALHOU


def test_espera_cresce_e_tem_teto():
    assert [FILA.espera_da_tentativa(n) for n in (1, 2, 3, 4)] == [1, 2, 4, 8]
    assert FILA.espera_da_tentativa(30) == FILA.ESPERA_MAXIMA_MIN


def test_erro_com_cpf_e_gravado_mascarado(con):
    novo = FILA.enfileirar(con, "SIRC", "op", "r")
    FILA.marcar_falha(con, novo, "recusado: CPF 000.000.044-21 inválido",
                      definitiva=True)
    assert "000.000.044-21" not in FILA.item(con, novo)["erro"]


def test_reprocessar_e_local_e_so_para_quem_falhou(con):
    novo = FILA.enfileirar(con, "CRA", "op", "r")
    with pytest.raises(FILA.FilaError, match="não se reprocessa"):
        FILA.reprocessar(con, novo)
    FILA.pegar_proximo(con)
    FILA.marcar_falha(con, novo, "x", definitiva=True)
    it = FILA.reprocessar(con, novo, por="mario")
    assert it["status"] == SCH.PENDENTE and it["tentativas"] == 0
    ev = con.execute("SELECT evento, mensagem FROM centrais_log "
                     "ORDER BY id DESC LIMIT 1").fetchone()
    assert ev["evento"] == "REPROCESSO" and "mario" in ev["mensagem"]
    with pytest.raises(FILA.FilaError, match="não está na fila"):
        FILA.reprocessar(con, 9999)


def test_cancelar_e_reprocessar_o_cancelado(con):
    novo = FILA.enfileirar(con, "CRA", "op", "r")
    FILA.cancelar(con, novo, por="mario", motivo="duplicado")
    assert FILA.item(con, novo)["status"] == SCH.CANCELADO
    with pytest.raises(FILA.FilaError):
        FILA.cancelar(con, novo)
    assert FILA.reprocessar(con, novo)["status"] == SCH.PENDENTE


def test_marcar_enviado_e_confirmado(con):
    novo = FILA.enfileirar(con, "ONR", "edital", "us:3")
    FILA.pegar_proximo(con)
    FILA.marcar_enviado(con, novo, resposta_ref="PROT-1", status_http=200)
    it = FILA.item(con, novo)
    assert it["status"] == SCH.ENVIADO and it["resposta_ref"] == "PROT-1"
    assert it["enviado_em"] and it["confirmado_em"] is None
    FILA.marcar_confirmado(con, novo)
    it = FILA.item(con, novo)
    assert it["status"] == SCH.CONFIRMADO and it["resposta_ref"] == "PROT-1"


def test_devolver_presos(con):
    novo = FILA.enfileirar(con, "CRA", "op", "r")
    FILA.pegar_proximo(con)
    assert FILA.devolver_presos(con) == 0
    con.execute("UPDATE centrais_fila SET atualizado_em = "
                "'2000-01-01T00:00:00' WHERE id = ?", (novo,))
    assert FILA.devolver_presos(con) == 1
    assert FILA.item(con, novo)["status"] == SCH.PENDENTE


def test_processar_proximo_chama_a_rede_fora_da_transacao(banco):
    with banco.transaction() as c:
        novo = FILA.enfileirar(c, "CENPROT", "certidao_processar", "x:1")
    vistos = []

    def enviar(it):
        assert banco.aberta is False, "a rede rodou com transação aberta"
        vistos.append(it["id"])
        return "PROTO-9"

    feito = FILA.processar_proximo(banco, enviar)
    assert vistos == [novo]
    assert feito["status"] == SCH.ENVIADO and feito["resposta_ref"] == "PROTO-9"
    assert FILA.processar_proximo(banco, enviar) is None


def test_processar_proximo_falhas(banco):
    with banco.transaction() as c:
        a = FILA.enfileirar(c, "CRA", "op", "a")
        b = FILA.enfileirar(c, "CRA", "op", "b")

    def definitiva(it):
        raise FILA.FalhaDefinitiva("400: campo obrigatório")

    def transitoria(it):
        raise ConnectionError("caiu")

    assert FILA.processar_proximo(banco, definitiva)["status"] == SCH.FALHOU
    r = FILA.processar_proximo(banco, transitoria)
    assert r["id"] == b and r["status"] == SCH.PENDENTE
    assert r["proxima_tentativa_em"]
    with banco.transaction() as c:
        assert FILA.item(c, a)["erro"].startswith("400")


def test_processar_proximo_so_manda_producao_com_permissao(banco):
    with banco.transaction() as c:
        p = FILA.enfileirar(c, "CRA", "op", "p", ambiente="PRODUCAO")
    chamado = []
    assert FILA.processar_proximo(banco, chamado.append) is None
    assert chamado == []
    feito = FILA.processar_proximo(banco, lambda it: None,
                                   permitir_producao=True)
    assert feito["id"] == p and feito["status"] == SCH.ENVIADO


def test_resumo_falhas_e_lista_para_o_painel(con):
    a = FILA.enfileirar(con, "CRA", "op", "a")
    FILA.enfileirar(con, "CRA", "op", "b")
    FILA.enfileirar(con, "ONR", "op", "c")
    FILA.pegar_proximo(con, central="CRA")
    FILA.marcar_falha(con, a, "x", definitiva=True)
    resumo = {r["central"]: r for r in FILA.resumo_por_central(con)}
    assert resumo["CRA"]["total"] == 2 and resumo["CRA"][SCH.FALHOU] == 1
    assert resumo["ONR"][SCH.PENDENTE] == 1
    assert [f["id"] for f in FILA.ultimas_falhas(con)] == [a]
    assert FILA.ultimas_falhas(con, central="ONR") == []
    assert len(FILA.listar(con, central="cra")) == 2
    assert len(FILA.listar(con, status="pendente")) == 2


def test_painel_em_banco_sem_tabela_nao_estoura():
    c = conexao_de_teste()
    assert FILA.resumo_por_central(c) == []
    assert FILA.ultimas_falhas(c) == []
    assert FILA.listar(c) == []


def test_schema_idempotente(con):
    SCH.init_centrais_schema(con)
    SCH.init_centrais_schema(con)
    nomes = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"centrais_fila", "centrais_log"} <= nomes
