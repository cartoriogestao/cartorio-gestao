"""O log estruturado das Centrais — sem segredo e sem dado de gente."""
from __future__ import annotations

import json
import logging
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import centrais_http as HTTP  # noqa: E402
import centrais_log as LOG  # noqa: E402
import centrais_schema as SCH  # noqa: E402


@pytest.fixture()
def con():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    SCH.init_centrais_schema(c)
    yield c
    c.close()


def test_sanitizar_tira_segredo_em_qualquer_profundidade():
    original = {"usuario": "u", "senha": "S3nha!", "x-api-key": "k",
                "cabecalhos": {"Authorization": "Bearer abc.def.ghi",
                               "Accept": "json"},
                "itens": [{"client_secret": "zz", "ok": 1}]}
    limpo = LOG.sanitizar(original)
    assert limpo["senha"] == LOG.OMITIDO and limpo["x-api-key"] == LOG.OMITIDO
    assert limpo["cabecalhos"]["Authorization"] == LOG.OMITIDO
    assert limpo["cabecalhos"]["Accept"] == "json"
    assert limpo["itens"][0] == {"client_secret": LOG.OMITIDO, "ok": 1}
    assert original["senha"] == "S3nha!"   # não muda o original


def test_cpf_e_cnpj_saem_mascarados_e_a_chave_cenprot_nao():
    texto = ("devedor 000.000.044-21 / 00000004421, empresa "
             "00.000.043/0001-77 chave 21987650141243301260417")
    m = LOG.mascarar_texto(texto)
    assert "000.000.044-21" not in m and "00000004421" not in m
    assert "00.000.043/0001-77" not in m
    assert "*********21" in m and "************77" in m
    assert "21987650141243301260417" in m      # 23 dígitos: não é CPF


def test_token_que_escapou_para_a_mensagem_some():
    m = LOG.mascarar_texto("recusou Bearer eyJhbGciOiJIUzI1NiJ9.abc.def")
    assert "eyJ" not in m and LOG.OMITIDO in m


def test_bytes_e_texto_longo():
    assert LOG.sanitizar(b"12345") == "<5 bytes>"
    assert len(LOG.mascarar_texto("x" * 5000)) <= LOG.LIMITE_DA_MENSAGEM + 1


def test_registrar_grava_e_emite_linha_json(con, caplog):
    with caplog.at_level(logging.INFO, logger="cartorio_gestao.centrais"):
        novo = LOG.registrar(con, "cenprot", "anuencias", "REQUISICAO",
                             nivel="nada", mensagem="cpf 111.222.333-44",
                             detalhe={"token": "t", "n": 2})
    linha = dict(con.execute("SELECT * FROM centrais_log WHERE id=?",
                             (novo,)).fetchone())
    assert linha["central"] == "CENPROT" and linha["nivel"] == SCH.INFO
    assert "111.222.333-44" not in linha["mensagem"]
    assert json.loads(linha["detalhe"]) == {"token": LOG.OMITIDO, "n": 2}
    emitida = json.loads(caplog.records[-1].getMessage())
    assert emitida["central"] == "CENPROT" and emitida["evento"] == "REQUISICAO"


def test_registrar_resposta_por_faixa_de_status(con):
    def resp(st):
        return HTTP.Resposta(status=st, cabecalhos={}, corpo=b"segredo",
                             texto="segredo", json=None, tentativas=1,
                             duracao_ms=12, url="https://c.invalid/x",
                             metodo="GET")
    LOG.registrar_resposta(con, "CRA", "op", resp(200))
    LOG.registrar_resposta(con, "CRA", "op", resp(404))
    LOG.registrar_resposta(con, "CRA", "op", resp(500))
    LOG.registrar_resposta(con, "CRA", "op",
                           HTTP.CentralHttpError("caiu", tentativas=3))
    niveis = [r["nivel"] for r in LOG.ultimos(con, central="cra")]
    assert niveis == [SCH.ERRO, SCH.ERRO, SCH.AVISO, SCH.INFO]
    assert all("segredo" not in (r["detalhe"] or "") for r in LOG.ultimos(con))
    assert LOG.ultimos(con, nivel="ERRO")[0]["evento"] == "FALHA_DE_TRANSPORTE"


def test_ultimos_filtra_e_ordena(con):
    for i in range(5):
        LOG.registrar(con, "ONR", f"op{i % 2}", "E")
    LOG.registrar(con, "CNIB", "op0", "E")
    assert len(LOG.ultimos(con, central="ONR")) == 5
    assert len(LOG.ultimos(con, central="ONR", operacao="op1")) == 2
    ids = [r["id"] for r in LOG.ultimos(con, limite=3)]
    assert ids == sorted(ids, reverse=True) and len(ids) == 3


def test_ultimos_sem_tabela_e_lista_vazia():
    c = sqlite3.connect(":memory:")
    assert LOG.ultimos(c) == []
