"""
A CHAVE DO CENPROT QUE SE CALCULA AO APONTAR o título que vem da CRA.

O QUE ELES CONFEREM
      - a CONTA, com vetores feitos à mão aqui, e não com a própria função: é a
        de `Protesto_Funcao.ChaveUnica`, do E-Ofício;
      - o SEQUENCIAL cresce sem repetir, a partir do maior já usado;
      - os DOIS TÍTULOS DO MESMO PROTOCOLO ficam com a mesma chave, e o arquivo
        só os funde por ela;
      - título que JÁ TEM CHAVE não muda, e não gasta sequencial;
      - título de ORIGEM CENPROT não recebe chave calculada: a dele vem da
        Central. O MANUAL também não;
      - FALTAR CONFIGURAÇÃO não impede o apontamento: o título fica sem chave.

O IBGE E O NÚMERO DA SERVENTIA DAQUI SÃO FICTÍCIOS, e a conta é feita sobre eles:
o verificador depende do IBGE, e por isso a chave real da prova de 30/10/2026
não se repete aqui. O que se repete é o sequencial dela, numa chave montada.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import bd_nativo                                 # noqa: E402
import protesto as PT                            # noqa: E402
import protesto_cenprot as CP                    # noqa: E402
import protesto_remessa as PRM                   # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from pt_schema import init_pt_schema             # noqa: E402

AGORA = "2026-10-30T09:00:00"
EXTENSO = "trinta dias do mês de outubro do ano de dois mil e vinte e seis"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}

# `12` + `34567` = a comarca fictícia destes testes.
COMARCA = "1234567"
CARTORIO = "03"
CONFIGURACAO = (("ibge_uf", "12"), ("ibge_municipio", "34567"),
                ("ibge_cartorio", "3"))
PESOS = "56738457667677419511020"

EXEMPLO = (Path(__file__).parent / "cra_remessa_exemplo.txt").read_bytes()


def _sem_configuracao() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


@pytest.fixture()
def con():
    c = _sem_configuracao()
    c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    c.executemany("INSERT OR REPLACE INTO settings VALUES (?, ?)", CONFIGURACAO)
    yield c
    c.close()


def _titulo(con, origem="CRA", chave_origem="LOTE:1", chave=None,
            protocolo=None) -> int:
    dados = {
        "especie": "DMI", "numero_titulo": "84713/1",
        "data_emissao": "2026-07-21", "data_vencimento": "2026-09-05",
        "valor": "1482.78", "saldo": "1482.78",
        "praca_protesto": "CIDADE EXEMPLO", "tipo_moeda": "1",
        "tipo_protesto": "C", "motivo_protesto": "1",
        "cedente": {"nome": "«mascarado»", "documento": "00000000000000",
                    "cidade": "Cidade Exemplo", "uf": "MA"},
        "devedores": [{"nome": "«mascarado»", "CNPJ": "00000000000000",
                       "enderecos": [{"endereco": "Rua X", "bairro": "Centro",
                                      "cidade": "Cidade Exemplo", "uf": "MA"}]}],
    }
    if chave:
        dados["chave_cenprot"] = chave
    tid = PT.cadastrar_titulo(con, dados, origem=origem,
                              origem_chave=chave_origem, agora=AGORA)
    if protocolo:
        con.execute("UPDATE pt_titulos SET protocolo=? WHERE id=?", (protocolo, tid))
    return tid


def _apontar(con, tid, agora=AGORA) -> dict:
    return PT.lancar_apontamento(con, tid, sv=SV, agora=agora,
                                 data_extenso=EXTENSO)


def _chave(con, tid):
    return con.execute("SELECT chave_cenprot FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()["chave_cenprot"]


def _chave_montada(sequencial: int, *, ibge=COMARCA, cartorio=CARTORIO,
                   aammdd="261030") -> str:
    """A conta escrita de novo aqui, para não provar a função por ela mesma."""
    base = f"{ibge}{sequencial:07d}0{cartorio}{aammdd}"
    soma = 0
    for digito, peso in zip(base, PESOS):
        soma += int(str(int(digito) * int(peso))[-1])
    fim = soma % 10
    return base[:14] + str(0 if fim == 0 else 10 - fim) + base[15:]


# ------------------------------------------------------------------- a conta


def test_a_conta_feita_a_mao():
    """Base 1234567 0000042 0 03 261030, último dígito de cada produto:

        5 2 1 2 0 4 5 | 0 0 0 0 0 8 4 | 0 | 0 7 | 0 6 1 0 6 0

    A soma é 51. Ela termina em 1, e o verificador é 10 - 1 = 9.
    """
    assert CP.compor_chave(ibge="1234567", sequencial=42, cartorio="03",
                           data="2026-10-30") == "12345670000042903261030"


def test_soma_que_termina_em_zero_da_verificador_zero():
    """Base 1234567 0000003 0 03 261030, último dígito de cada produto:

        5 2 1 2 0 4 5 | 0 0 0 0 0 0 1 | 0 | 0 7 | 0 6 1 0 6 0

    A soma é 40, e o verificador é 0 (e não 10).
    """
    assert CP.compor_chave(ibge="1234567", sequencial=3, cartorio="03",
                           data="2026-10-30") == "12345670000003003261030"


def test_chave_montada_com_o_sequencial_da_prova():
    """O sequencial que a CENPROT aceitou em 30/10/2026, em chave fictícia."""
    chave = CP.compor_chave(ibge=COMARCA, sequencial="0141397", cartorio="01",
                            data=AGORA)
    assert chave == _chave_montada(141397, cartorio="01")
    partes = CP.decompor_chave(chave)
    assert partes["ibge"] == COMARCA
    assert partes["sequencial"] == "0141397"
    assert partes["sequencial_cenprot"] == "0141397" + partes["verificador"]
    assert partes["cartorio"] == "01"
    assert partes["data_protocolo"] == "261030"
    assert CP.data_do_protocolo(chave) == "2026-10-30"


def test_os_pesos_sao_um_por_posicao():
    assert len(CP.PESOS_DA_CHAVE) == CP.TAMANHO_DA_CHAVE
    assert CP.PESOS_DA_CHAVE == PESOS


@pytest.mark.parametrize("campos", [
    {"ibge": "123456"},
    {"ibge": ""},
    {"cartorio": "123"},
    {"cartorio": ""},
    {"sequencial": 0},
    {"sequencial": ""},
    {"sequencial": CP.MAIOR_SEQUENCIAL + 1},
    {"data": "30/10/2026"},
    {"data": None},
])
def test_o_que_nao_tem_a_forma_nao_vira_chave(campos):
    certos = {"ibge": COMARCA, "sequencial": 1, "cartorio": CARTORIO,
              "data": "2026-10-30"}
    with pytest.raises(CP.CenprotError):
        CP.compor_chave(**{**certos, **campos})


# ---------------------------------------------------------------- o sequencial


def test_proxima_chave_e_o_maior_usado_mais_um(con):
    _titulo(con, chave_origem="L:1", chave=_chave_montada(141397))
    _titulo(con, chave_origem="L:2", chave=_chave_montada(9))
    assert CP.proxima_chave(con, data=AGORA, comarca=COMARCA,
                            cartorio=CARTORIO) == _chave_montada(141398)


def test_proxima_chave_nao_gasta_o_sequencial(con):
    _titulo(con, chave_origem="L:1", chave=_chave_montada(10))
    for _ in range(2):
        assert CP.proxima_chave(con, data=AGORA, comarca=COMARCA,
                                cartorio=CARTORIO) == _chave_montada(11)


def test_chave_torta_nao_entra_na_conta_do_sequencial(con):
    _titulo(con, chave_origem="L:1", chave="999999999")
    assert CP.proxima_chave(con, data=AGORA, comarca=COMARCA,
                            cartorio=CARTORIO) == _chave_montada(1)


def test_o_sequencial_cresce_sem_repetir_a_cada_apontamento(con):
    _titulo(con, chave_origem="L:0", chave=_chave_montada(141397))
    chaves = []
    for i in range(1, 4):
        tid = _titulo(con, chave_origem=f"L:{i}")
        resultado = _apontar(con, tid)
        chaves.append(_chave(con, tid))
        assert resultado["chave_cenprot"] == chaves[-1]
    assert chaves == [_chave_montada(141398), _chave_montada(141399),
                      _chave_montada(141400)]


def test_a_trava_vem_antes_da_leitura(con, monkeypatch):
    """Sem ela, dois apontamentos ao mesmo tempo repetem o sequencial."""
    ordem = []
    travar = bd_nativo.Banco.travar
    ler = bd_nativo.Banco.ler

    def travar_e_anotar(self, chave):
        ordem.append(chave)
        return travar(self, chave)

    def ler_e_anotar(self, sql, *args, **kw):
        if "chave_cenprot" in sql:
            ordem.append("leu")
        return ler(self, sql, *args, **kw)

    tid = _titulo(con)
    monkeypatch.setattr(bd_nativo.Banco, "travar", travar_e_anotar)
    monkeypatch.setattr(bd_nativo.Banco, "ler", ler_e_anotar)
    _apontar(con, tid)
    assert ordem.index("pt_titulos.chave_cenprot") < ordem.index("leu")


def test_a_data_da_chave_e_a_do_apontamento(con):
    tid = _titulo(con)
    _apontar(con, tid, agora="2026-11-03T08:30:00")
    assert CP.data_do_protocolo(_chave(con, tid)) == "2026-11-03"


# ------------------------------------------------- os títulos do mesmo protocolo


def test_dois_titulos_do_mesmo_protocolo_ficam_com_a_mesma_chave(con):
    primeiro = _titulo(con, chave_origem="L:1", protocolo="2610300001")
    segundo = _titulo(con, chave_origem="L:2", protocolo="2610300001")
    _apontar(con, primeiro)
    _apontar(con, segundo)
    assert _chave(con, primeiro) == _chave_montada(1)
    assert _chave(con, segundo) == _chave(con, primeiro)


def test_o_irmao_nao_gasta_sequencial(con):
    primeiro = _titulo(con, chave_origem="L:1", protocolo="2610300001")
    segundo = _titulo(con, chave_origem="L:2", protocolo="2610300001")
    terceiro = _titulo(con, chave_origem="L:3", protocolo="2610300002")
    for tid in (primeiro, segundo, terceiro):
        _apontar(con, tid)
    assert _chave(con, terceiro) == _chave_montada(2)


def test_a_chave_do_irmao_de_outro_dia_vem_inteira(con):
    """Quem fala do título na Central é a chave; ela não se refaz com outra data."""
    antiga = _chave_montada(77, aammdd="261029")
    _titulo(con, chave_origem="L:1", chave=antiga, protocolo="2610290001")
    novo = _titulo(con, chave_origem="L:2", protocolo="2610290001")
    _apontar(con, novo)
    assert _chave(con, novo) == antiga


def test_protocolo_com_duas_chaves_nao_se_escolhe(con):
    _titulo(con, chave_origem="L:1", chave=_chave_montada(1), protocolo="2610300001")
    _titulo(con, chave_origem="L:2", chave=_chave_montada(2), protocolo="2610300001")
    novo = _titulo(con, chave_origem="L:3", protocolo="2610300001")
    r = _apontar(con, novo)
    assert r["chave_cenprot"] is None
    assert not _chave(con, novo)


def test_protocolo_sem_digito_nao_casa_com_quem_nao_tem_protocolo(con):
    _titulo(con, chave_origem="L:1", chave=_chave_montada(9))
    novo = _titulo(con, chave_origem="L:2", protocolo="S/N")
    _apontar(con, novo)
    assert _chave(con, novo) == _chave_montada(10)


def test_protocolo_que_acabou_de_nascer_nao_herda_chave_de_outro(con):
    """`numero_do_protocolo` conta os do dia: com buraco, o número se repete.

    São dois do dia, e o próximo sai `...0003`, que já é de um terceiro título.
    Herdar por essa repetição poria a chave de uma pessoa no título de outra.
    """
    _titulo(con, chave_origem="L:1", protocolo="2610300001")
    alheio = _titulo(con, chave_origem="L:2", chave=_chave_montada(50),
                     protocolo="2610300003")
    novo = _titulo(con, chave_origem="L:3")
    _apontar(con, novo)
    assert con.execute("SELECT protocolo FROM pt_titulos WHERE id=?",
                       (novo,)).fetchone()["protocolo"] == "2610300003"
    assert _chave(con, novo) == _chave_montada(51)
    assert _chave(con, alheio) == _chave_montada(50)


# ------------------------------------------------------------- quem não recebe


def test_titulo_que_ja_tem_chave_nao_muda_e_nao_gasta_sequencial(con):
    ja_tinha = _chave_montada(500, aammdd="260101")
    tid = _titulo(con, chave_origem="L:1", chave=ja_tinha)
    r = _apontar(con, tid)
    assert _chave(con, tid) == ja_tinha
    assert r["chave_cenprot"] == ja_tinha
    assert CP.proxima_chave(con, data=AGORA, comarca=COMARCA,
                            cartorio=CARTORIO) == _chave_montada(501)


def test_titulo_de_origem_cenprot_nao_recebe_chave_calculada(con):
    tid = _titulo(con, origem="CENPROT", chave_origem="CENPROT-PEDIDO:1")
    r = _apontar(con, tid)
    assert r["chave_cenprot"] is None
    assert not _chave(con, tid)


def test_titulo_de_origem_cenprot_nao_herda_do_irmao(con):
    _titulo(con, chave_origem="L:1", chave=_chave_montada(9), protocolo="2610300001")
    tid = _titulo(con, origem="CENPROT", chave_origem="CENPROT-PEDIDO:1",
                  protocolo="2610300001")
    _apontar(con, tid)
    assert not _chave(con, tid)


def test_titulo_manual_nao_recebe_chave_calculada(con):
    tid = _titulo(con, origem="MANUAL", chave_origem=None)
    _apontar(con, tid)
    assert not _chave(con, tid)


def test_o_titulo_ja_apontado_nao_e_preenchido_por_apontar_outro(con):
    """Título antigo sem chave fica como está: preencher é decisão do oficial."""
    antigo = _titulo(con, chave_origem="L:1")
    con.execute("UPDATE pt_titulos SET situacao='APONTADO', protocolo='2001010001' "
                "WHERE id=?", (antigo,))
    novo = _titulo(con, chave_origem="L:2")
    _apontar(con, novo)
    assert not _chave(con, antigo)
    assert _chave(con, novo) == _chave_montada(1)


# ------------------------------------------------------- sem configuração, segue


def test_sem_a_tabela_de_configuracao_aponta_e_fica_sem_chave():
    c = _sem_configuracao()
    try:
        tid = _titulo(c)
        r = _apontar(c, tid)
        assert r["chave_cenprot"] is None
        assert not _chave(c, tid)
        assert PT.titulo(c, tid)["situacao"] == "APONTADO"
    finally:
        c.close()


def test_configuracao_torta_aponta_e_fica_sem_chave(con):
    con.execute("UPDATE settings SET value='123' WHERE key='ibge_municipio'")
    con.execute("UPDATE settings SET value='12345' WHERE key='ibge_uf'")
    tid = _titulo(con)
    r = _apontar(con, tid)
    assert r["chave_cenprot"] is None
    assert PT.titulo(con, tid)["situacao"] == "APONTADO"


def test_sem_configuracao_o_irmao_ainda_da_a_chave(con):
    _titulo(con, chave_origem="L:1", chave=_chave_montada(9), protocolo="2610300001")
    con.execute("DELETE FROM settings")
    novo = _titulo(con, chave_origem="L:2", protocolo="2610300001")
    _apontar(con, novo)
    assert _chave(con, novo) == _chave_montada(9)


# ------------------------------------------------------------ pelo lote da CRA


def test_a_remessa_recebida_grava_a_chave_no_apontamento(con):
    r = PRM.receber(con, EXEMPLO, agora=AGORA, data_extenso=EXTENSO, sv=SV)
    assert r["apontados"] == 1
    assert con.execute("SELECT chave_cenprot FROM pt_titulos").fetchone()[
        "chave_cenprot"] == _chave_montada(1)


def test_remessa_que_nao_aponta_nao_grava_chave(con):
    PRM.receber(con, EXEMPLO, agora=AGORA, data_extenso=EXTENSO, sv=SV,
                apontar=False)
    assert not con.execute("SELECT chave_cenprot FROM pt_titulos").fetchone()[
        "chave_cenprot"]
