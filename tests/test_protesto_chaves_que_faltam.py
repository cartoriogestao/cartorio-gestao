"""AS CHAVES DA CENPROT QUE FALTAM: a lista, a categoria e a gravacao.

O QUE ELES CONFEREM
      - cada titulo sem chave cai numa categoria so, com o motivo;
      - o titulo NASCIDO AQUI e ja apontado leva a chave que o apontamento lhe
        daria, com a data do apontamento no fim;
      - o que VEIO DO ACERVO sem chave NAO recebe chave composta;
      - o irmao do protocolo empresta a chave, e o pedido da CENPROT cujo
        irmao e OUTRO pedido fica para o oficial;
      - a lista NAO GRAVA; gravar so nos ids dados, e nunca por cima.

Dados ficticios: IBGE e serventia de exemplo, nenhum nome de verdade.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import protesto as PT                            # noqa: E402
import protesto_cenprot as CP                    # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from pt_schema import init_pt_schema             # noqa: E402

AGORA = "2026-10-30T09:00:00"
EXTENSO = "trinta dias do mes de outubro do ano de dois mil e vinte e seis"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabeliao e Oficial de Registro",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
CONFIGURACAO = (("ibge_uf", "12"), ("ibge_municipio", "34567"),
                ("ibge_cartorio", "3"))


@pytest.fixture()
def con():
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    init_nucleo_schema(c)
    init_pt_schema(c)
    c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    yield c
    c.close()


def _configurar(con):
    con.executemany("INSERT OR REPLACE INTO settings VALUES (?, ?)", CONFIGURACAO)


def _titulo(con, origem="CRA", chave_origem="LOTE:1", chave=None, protocolo=None):
    dados = {
        "especie": "DMI", "numero_titulo": "1/1", "data_emissao": "2026-07-21",
        "data_vencimento": "2026-09-05", "valor": "100.00", "saldo": "100.00",
        "praca_protesto": "CIDADE EXEMPLO", "tipo_moeda": "1",
        "tipo_protesto": "C", "motivo_protesto": "1",
        "cedente": {"nome": "mascarado", "documento": "00000000000000",
                    "cidade": "Cidade Exemplo", "uf": "MA"},
        "devedores": [{"nome": "mascarado", "CNPJ": "00000000000000",
                       "enderecos": [{"endereco": "Rua X", "bairro": "Centro",
                                      "cidade": "Cidade Exemplo", "uf": "MA"}]}],
    }
    if chave:
        dados["chave_cenprot"] = chave
    tid = PT.cadastrar_titulo(con, dados, origem=origem, origem_chave=chave_origem,
                              agora=AGORA)
    if protocolo:
        con.execute("UPDATE pt_titulos SET protocolo=? WHERE id=?", (protocolo, tid))
    return tid


def _apontar_sem_chave(con, tid, agora=AGORA):
    """Aponta com a configuracao fora: o titulo fica apontado e sem chave,
    como os de origem CENPROT ficavam antes da correcao."""
    guardado = con.execute("SELECT key, value FROM settings").fetchall()
    con.execute("DELETE FROM settings")
    PT.lancar_apontamento(con, tid, sv=SV, agora=agora, data_extenso=EXTENSO)
    con.executemany("INSERT INTO settings VALUES (?, ?)",
                    [tuple(r) for r in guardado])


def _chave(con, tid):
    return con.execute("SELECT chave_cenprot FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()["chave_cenprot"]


def _por_id(con):
    return {linha["id"]: linha for linha in CP.chaves_que_faltam(con)}


def test_nascido_aqui_e_apontado_leva_a_chave_do_apontamento(con):
    tid = _titulo(con, origem="CENPROT", chave_origem="CENPROT-PEDIDO:1")
    _apontar_sem_chave(con, tid, agora="2026-10-21T13:29:45")
    _configurar(con)
    linha = _por_id(con)[tid]
    assert linha["categoria"] == "calcular"
    assert linha["chave_proposta"] == CP.compor_chave(
        ibge="1234567", sequencial=1, cartorio="03", data="2026-10-21")
    assert linha["chave_proposta"].endswith("261021")
    assert not _chave(con, tid), "a lista nao grava"


def test_o_sequencial_continua_do_maior_ja_usado(con):
    _configurar(con)
    _titulo(con, chave_origem="L:9", chave=CP.compor_chave(
        ibge="1234567", sequencial=40, cartorio="03", data="2026-10-01"))
    a = _titulo(con, origem="MANUAL", chave_origem=None)
    b = _titulo(con, origem="CENPROT", chave_origem="CENPROT-PEDIDO:2")
    _apontar_sem_chave(con, a)
    _apontar_sem_chave(con, b)
    linhas = _por_id(con)
    assert CP.decompor_chave(linhas[a]["chave_proposta"])["sequencial"] == "0000041"
    assert CP.decompor_chave(linhas[b]["chave_proposta"])["sequencial"] == "0000042"


def test_o_que_veio_do_acervo_sem_chave_nao_recebe_chave_composta(con):
    _configurar(con)
    tid = _titulo(con, chave_origem="tbAvisoProtesto:123")
    _apontar_sem_chave(con, tid)
    linha = _por_id(con)[tid]
    assert linha["categoria"] == "acervo_sem_chave"
    assert linha["chave_proposta"] is None


def test_sem_protocolo_e_nao_apontado(con):
    _configurar(con)
    sem_protocolo = _titulo(con, origem="MANUAL", chave_origem=None)
    linhas = _por_id(con)
    assert linhas[sem_protocolo]["categoria"] in ("sem_protocolo", "nao_apontado")
    con.execute("UPDATE pt_titulos SET protocolo='2610300009' WHERE id=?",
                (sem_protocolo,))
    assert _por_id(con)[sem_protocolo]["categoria"] == "nao_apontado"


def test_o_irmao_do_protocolo_empresta_a_chave(con):
    _configurar(con)
    chave = CP.compor_chave(ibge="1234567", sequencial=9, cartorio="03",
                            data="2026-10-30")
    # O irmao chega com a chave DEPOIS: no apontamento ele ainda nao estava.
    tid = _titulo(con, chave_origem="L:2", protocolo="2610300001")
    _apontar_sem_chave(con, tid)
    _titulo(con, chave_origem="L:1", chave=chave, protocolo="2610300001")
    linha = _por_id(con)[tid]
    assert (linha["categoria"], linha["chave_proposta"]) == ("copiar_do_irmao", chave)


def test_pedido_cenprot_com_irmao_de_outro_pedido_fica_para_o_oficial(con):
    _configurar(con)
    chave = CP.compor_chave(ibge="1234567", sequencial=9, cartorio="03",
                            data="2026-10-30")
    tid = _titulo(con, origem="CENPROT", chave_origem="CENPROT-PEDIDO:1",
                  protocolo="2610300001")
    _apontar_sem_chave(con, tid)
    _titulo(con, origem="CENPROT", chave_origem="CENPROT-PEDIDO:2", chave=chave,
            protocolo="2610300001")
    linha = _por_id(con)[tid]
    assert linha["categoria"] == "decisao_do_oficial"
    with pytest.raises(CP.CenprotError):
        CP.gravar_chaves_que_faltam(con, [tid])
    assert not _chave(con, tid)


def test_gravar_so_nos_ids_dados_e_com_o_sequencial_do_momento(con):
    a = _titulo(con, origem="CENPROT", chave_origem="CENPROT-PEDIDO:1")
    b = _titulo(con, origem="CENPROT", chave_origem="CENPROT-PEDIDO:2")
    _apontar_sem_chave(con, a)
    _apontar_sem_chave(con, b)
    _configurar(con)
    gravados = CP.gravar_chaves_que_faltam(con, [b])
    assert [g["id"] for g in gravados] == [b]
    assert not _chave(con, a)
    assert CP.decompor_chave(_chave(con, b))["sequencial"] == "0000001"


def test_gravar_exige_ids(con):
    with pytest.raises(CP.CenprotError):
        CP.gravar_chaves_que_faltam(con, [])


def test_gravar_nunca_por_cima(con):
    _configurar(con)
    tid = _titulo(con, origem="CENPROT", chave_origem="CENPROT-PEDIDO:1")
    _apontar_sem_chave(con, tid)
    con.execute("UPDATE pt_titulos SET chave_cenprot='12345670000500103261030' "
                "WHERE id=?", (tid,))
    with pytest.raises(CP.CenprotError):
        CP.gravar_chaves_que_faltam(con, [tid])
    assert _chave(con, tid) == "12345670000500103261030"
