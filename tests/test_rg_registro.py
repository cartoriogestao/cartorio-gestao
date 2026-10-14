"""
Testes de RCPJ e RTD — abrir registro, averbar, cancelar, ligados ao nucleo.

O QUE ELES CONFEREM
    A regra, e nao "a funcao devolveu alguma coisa":

      - abrir registro exige serie conhecida de RCPJ ou RTD, e a atribuicao
        vem da serie, nunca de parametro solto;
      - cada ato — registro, averbacao, cancelamento — ocupa FOLHA PROPRIA,
        porque as series sao folha_nova (medido em tbTD_Propriedade);
      - carga repetivel: a mesma (origem, origem_chave) nao duplica;
      - so se averba ou cancela registro ATIVO; nao ha cancelamento de
        cancelamento.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import rg_registro as RG                         # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from rg_schema import init_rg_schema             # noqa: E402

AGORA = "2026-08-24T09:00:00"
EXTENSO = "vinte e quatro dias do mês de agosto do ano de dois mil e vinte e seis"
SV = {
    "unit_name": "SERVENTIA EXTRAJUDICIAL DO OFÍCIO ÚNICO DE CIDADE EXEMPLO",
    "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
    "serventia_titulo": "Tabelião e Oficial de Registro",
    "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
}


def banco() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    init_rg_schema(con)
    return con


# --------------------------------------------------------------- o registro


def test_abre_registro_de_rcpj():
    con = banco()
    r = RG.abrir_registro(con, serie="PJ_A", natureza="Estatuto de associação",
                          requerente_nome="ASSOCIAÇÃO X", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO, teor="Texto do estatuto.")
    assert r["numero_ordem"] == 1
    assert r["folha"] == 1
    reg = RG.registro(con, r["registro_id"])
    assert reg["atribuicao"] == 3
    assert reg["situacao"] == "ATIVO"
    assert reg["numero"] == 1


def test_abre_registro_de_rtd():
    con = banco()
    r = RG.abrir_registro(con, serie="TD_B", natureza="Contrato particular",
                          sv=SV, agora=AGORA, data_extenso=EXTENSO)
    reg = RG.registro(con, r["registro_id"])
    assert reg["atribuicao"] == 4


def test_serie_desconhecida_e_recusada():
    con = banco()
    with pytest.raises(RG.RgError, match="não é de RCPJ nem de RTD"):
        RG.abrir_registro(con, serie="RC_A", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO)


def test_cada_registro_ocupa_folha_propria():
    # PJ_A e folha_nova: o segundo registro vai para a folha 2, nao continua
    # na folha do primeiro — ao contrario da matricula do RI.
    con = banco()
    r1 = RG.abrir_registro(con, serie="PJ_A", sv=SV, agora=AGORA,
                           data_extenso=EXTENSO)
    r2 = RG.abrir_registro(con, serie="PJ_A", sv=SV, agora=AGORA,
                           data_extenso=EXTENSO)
    assert r1["folha"] == 1
    assert r2["folha"] == 2


def test_carga_e_repetivel_por_construcao():
    con = banco()
    r1 = RG.abrir_registro(con, serie="PJ_A", origem="EOFICIO",
                           origem_chave="ACERVO:123", sv=SV, agora=AGORA,
                           data_extenso=EXTENSO)
    r2 = RG.abrir_registro(con, serie="PJ_A", origem="EOFICIO",
                           origem_chave="ACERVO:123", sv=SV, agora=AGORA,
                           data_extenso=EXTENSO)
    assert r1["registro_id"] == r2["registro_id"]
    assert r2["reaproveitado"] is True
    assert con.execute("SELECT COUNT(*) n FROM rg_registros").fetchone()["n"] == 1


def test_registro_de_eoficio_sem_chave_e_recusado():
    con = banco()
    with pytest.raises(RG.RgError, match="chave de origem"):
        RG.abrir_registro(con, serie="PJ_A", origem="EOFICIO", sv=SV,
                          agora=AGORA, data_extenso=EXTENSO)


# -------------------------------------------------------------- a averbacao


def test_lanca_averbacao_em_folha_propria():
    con = banco()
    r = RG.abrir_registro(con, serie="TD_C", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO)
    av = RG.lancar_averbacao(con, r["registro_id"],
                             teor="Averbação de alteração de endereço.",
                             sv=SV, agora=AGORA, data_extenso=EXTENSO)
    assert av["folha"] == 2
    atos = RG.atos_do(con, r["registro_id"])
    assert [a["tipo"] for a in atos] == ["REGISTRO", "AVERBACAO"]


def test_averbacao_exige_teor():
    con = banco()
    r = RG.abrir_registro(con, serie="PJ_A", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO)
    with pytest.raises(RG.RgError, match="dez letras"):
        RG.lancar_averbacao(con, r["registro_id"], teor="curto", sv=SV,
                            agora=AGORA, data_extenso=EXTENSO)


def test_nao_averba_registro_cancelado():
    con = banco()
    r = RG.abrir_registro(con, serie="PJ_A", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO)
    RG.lancar_cancelamento(con, r["registro_id"], motivo="Erro na inscrição.",
                           sv=SV, agora=AGORA, data_extenso=EXTENSO)
    with pytest.raises(RG.RgError, match="só se averba registro ativo"):
        RG.lancar_averbacao(con, r["registro_id"], teor="Nova averbação.",
                            sv=SV, agora=AGORA, data_extenso=EXTENSO)


# ---------------------------------------------------------- o cancelamento


def test_cancela_registro_ativo():
    con = banco()
    r = RG.abrir_registro(con, serie="TD_F", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO)
    RG.lancar_cancelamento(con, r["registro_id"], motivo="Erro na inscrição.",
                           sv=SV, agora=AGORA, data_extenso=EXTENSO)
    assert RG.registro(con, r["registro_id"])["situacao"] == "CANCELADO"


def test_cancelamento_exige_motivo():
    con = banco()
    r = RG.abrir_registro(con, serie="PJ_B", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO)
    with pytest.raises(RG.RgError, match="dez letras"):
        RG.lancar_cancelamento(con, r["registro_id"], motivo="erro", sv=SV,
                               agora=AGORA, data_extenso=EXTENSO)


def test_nao_cancela_duas_vezes():
    con = banco()
    r = RG.abrir_registro(con, serie="PJ_B", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO)
    RG.lancar_cancelamento(con, r["registro_id"], motivo="Erro na inscrição.",
                           sv=SV, agora=AGORA, data_extenso=EXTENSO)
    with pytest.raises(RG.RgError, match="já está com situação"):
        RG.lancar_cancelamento(con, r["registro_id"],
                               motivo="Segunda tentativa de cancelar.",
                               sv=SV, agora=AGORA, data_extenso=EXTENSO)


# -------------------------------------------------------- a regra medida


def test_averbacao_consome_protocolo_so_no_rtd():
    # Fato medido em LEVANTAMENTO_QUATRO_ATRIBUICOES.md — ainda nao vira
    # comportamento (nao ha integracao com o protocolo geral), mas a regra
    # tem de estar certa quando a integracao vier.
    assert RG.AVERBACAO_CONSOME_PROTOCOLO[3] is False   # RCPJ
    assert RG.AVERBACAO_CONSOME_PROTOCOLO[4] is True    # RTD
