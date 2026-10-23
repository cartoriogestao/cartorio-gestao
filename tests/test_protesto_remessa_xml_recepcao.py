"""Recepcao XML da CRA grava origem_xml_* na mesma transacao do lote."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import protesto_remessa as PRM
from nucleo_schema import init_nucleo_schema
from pt_schema import init_pt_schema
from test_protesto_cra_xml import _arquivo_xml


@pytest.fixture()
def con():
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    # `pt_atos.livro_id` aponta para `nu_livros`, e o PostgreSQL nativo
    # cobra a chave estrangeira ja na criacao: o nucleo vem antes.
    init_nucleo_schema(c)
    init_pt_schema(c)
    yield c
    c.close()


def _sv():
    return {"livro_apontamento": "1", "folha_apontamento": "1"}


def test_receber_xml_grava_origem_na_mesma_transacao(con):
    """**CONTRATO MUDADO EM 14/10/2026** — ordem do oficial: «agora é tudo
    produção». O lote entrava com o ambiente que o chamador mandasse, e a
    rota manda «HOMOLOGACAO» quando o formulário vem sem o campo; agora todo
    lote XML entra como de PRODUÇÃO, mande o chamador o que mandar."""
    bruto = _arquivo_xml()
    visto = PRM.conferir_xml(con, bruto, "HOMOLOGACAO")
    assert len(visto["lotes"]) == 1
    lote = visto["lotes"][0]
    assert lote["origem_xml_ambiente"] == "PRODUCAO"
    assert len(lote["origem_xml_hash_lote"]) == 64
    assert len(lote["origem_xml_chave"]) == 64

    r = PRM.receber_xml(
        con, bruto, ambiente="HOMOLOGACAO", agora="2026-09-30T12:00:00",
        data_extenso="30 de setembro de 2026", sv=_sv(), apontar=False,
        confirmar=False, usuario="teste")
    remessa_id = r["lotes"][0]["remessa_id"]
    row = con.execute(
        "SELECT origem_xml_ambiente, origem_xml_hash_lote, origem_xml_chave "
        "FROM pt_remessas WHERE id=?", (remessa_id,)
    ).fetchone()
    assert row["origem_xml_ambiente"] == "PRODUCAO"
    assert row["origem_xml_hash_lote"] == lote["origem_xml_hash_lote"]
    assert row["origem_xml_chave"] == lote["origem_xml_chave"]


def test_receber_xml_duplicado_recusa_pela_chave(con):
    bruto = _arquivo_xml()
    kwargs = dict(
        ambiente="HOMOLOGACAO", agora="2026-09-30T12:00:00",
        data_extenso="30 de setembro de 2026", sv=_sv(), apontar=False,
        confirmar=False, usuario="teste")
    PRM.receber_xml(con, bruto, **kwargs)
    with pytest.raises(PRM.RemessaError, match="idempot"):
        PRM.receber_xml(con, bruto, **kwargs)


def test_homologacao_pedida_entra_como_producao_e_nao_duplica(con):
    """**CONTRATO MUDADO EM 14/10/2026.** Este teste se chamava
    `test_ambientes_distintos_nao_colidem` e cobrava que o mesmo lote
    entrasse duas vezes, uma por ambiente. Com tudo em produção, «o mesmo
    lote pedido como homologação» é o mesmo lote de produção — e a segunda
    entrada é recusada pela chave, que é o que impede apontar duas vezes."""
    bruto = _arquivo_xml()
    kwargs = dict(
        agora="2026-09-30T12:00:00", data_extenso="30 de setembro de 2026",
        sv=_sv(), apontar=False, confirmar=False, usuario="teste")
    PRM.receber_xml(con, bruto, ambiente="HOMOLOGACAO", **kwargs)
    with pytest.raises(PRM.RemessaError, match="idempot"):
        PRM.receber_xml(con, bruto, ambiente="PRODUCAO", **kwargs)
    assert con.execute("SELECT COUNT(*) FROM pt_remessas").fetchone()[0] == 1
    assert con.execute(
        "SELECT origem_xml_ambiente FROM pt_remessas").fetchone()[0] == "PRODUCAO"
