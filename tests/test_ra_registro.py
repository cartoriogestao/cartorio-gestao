"""
Testes do Registro Auxiliar — o Livro 3 do RI.

O QUE ELES CONFEREM
    A regra, e nao "a funcao devolveu alguma coisa":

      - o numero sai do contador do RI (`ri_numeracao`, livro '3'), e NAO de
        uma segunda fonte propria — duas fontes para o mesmo numero e o
        defeito de 18/08/2026;
      - o contador ANDA a cada registro: sem isso o segundo registro nasceria
        com o numero do primeiro, porque os registros do Livro 3 nao moram em
        `ri_matriculas`, de onde `ri_correcoes` le;
      - o Livro 3 conta SEPARADO do Livro 2 — sao series distintas;
      - o numero do ato e continuo entre registro e averbacao: R-1, AV-2;
      - o cancelamento e uma AVERBACAO, e nao um apagamento.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ra_registro as RA                         # noqa: E402
from ra_schema import init_ra_schema             # noqa: E402
from ri_schema import init_ri_schema             # noqa: E402

AGORA = "2026-08-24T09:00:00"


def banco() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    init_ri_schema(con)      # o Livro 3 conta pelo contador do RI
    init_ra_schema(con)
    return con


def cedula(con, **kw):
    kw.setdefault("natureza", "CEDULA_CREDITO_RURAL")
    kw.setdefault("titulo_tipo", "Cédula Rural Pignoratícia e Hipotecária")
    return RA.registrar(con, agora=AGORA, **kw)


# ------------------------------------------------------------- registrar


def test_registra_cedula_de_credito_rural():
    con = banco()
    r = cedula(con, titulo_numero="40/01800-8", valor="299809.50", parcelas=6,
               vencimento_final="2028-05-10", juros="9,00")
    assert r["numero"] == 1
    assert r["rotulo"] == "R-1"
    reg = RA.registro(con, r["registro_id"])
    assert reg["livro"] == "3"
    assert reg["valor_centavos"] == 29980950
    assert reg["parcelas"] == 6
    assert reg["situacao"] == "ATIVO"


def test_natureza_fora_do_catalogo_e_recusada():
    con = banco()
    with pytest.raises(RA.RaError, match="não é do Livro 3"):
        RA.registrar(con, natureza="COMPRA_E_VENDA", agora=AGORA)


def test_registro_de_eoficio_sem_chave_e_recusado():
    con = banco()
    with pytest.raises(RA.RaError, match="chave de origem"):
        cedula(con, origem="EOFICIO")


def test_carga_e_repetivel_por_construcao():
    con = banco()
    a = cedula(con, origem="EOFICIO", origem_chave="ACERVO:1549")
    b = cedula(con, origem="EOFICIO", origem_chave="ACERVO:1549")
    assert a["registro_id"] == b["registro_id"]
    assert b["reaproveitado"] is True
    assert con.execute("SELECT COUNT(*) n FROM ra_registros").fetchone()["n"] == 1


def test_as_partes_entram_com_o_registro():
    con = banco()
    r = cedula(con, partes=[
        {"nome": "JOÃO DA SILVA", "documento_tipo": "CPF",
         "documento_numero": "12345678901", "papel": "emitente"},
        {"nome": "BANCO DO BRASIL SA", "documento_tipo": "CNPJ",
         "documento_numero": "00000010000127", "papel": "credor"},
    ])
    partes = RA.partes_do(con, r["registro_id"])
    assert [p["papel"] for p in partes] == ["emitente", "credor"]


# ------------------------------------------------------------ a numeracao


def test_o_contador_anda_e_o_segundo_registro_nao_repete_numero():
    # Os registros do Livro 3 nao moram em ri_matriculas, de onde
    # ri_correcoes le. Sem consumir o contador, os dois sairiam com 1.
    con = banco()
    assert cedula(con)["numero"] == 1
    assert cedula(con)["numero"] == 2
    assert cedula(con)["numero"] == 3


def test_o_numero_respeita_a_semente_do_contador_do_ri():
    # O acervo desta casa tem o livro 3 em 1.650 em uso. Semeado assim, o
    # proximo registro e o 1.651 — e nao o 1.
    con = banco()
    con.execute(
        """INSERT INTO ri_numeracao(livro, proximo_numero, maior_em_uso,
               observacao) VALUES ('3', 1651, 1650, 'semeado do acervo')""")
    assert cedula(con)["numero"] == 1651
    assert cedula(con)["numero"] == 1652


def test_o_livro_3_conta_separado_do_livro_2():
    # Series distintas: `ri_correcoes.serie_do_livro`. O Livro 2 em 4.014 nao
    # empurra o Livro 3.
    con = banco()
    con.execute(
        """INSERT INTO ri_numeracao(livro, proximo_numero, maior_em_uso,
               observacao) VALUES ('2', 4015, 4014, 'do acervo')""")
    assert cedula(con)["numero"] == 1


def test_proximo_numero_so_le():
    con = banco()
    antes = RA.proximo_numero(con)
    assert RA.proximo_numero(con) == antes
    assert con.execute("SELECT COUNT(*) n FROM ra_registros").fetchone()["n"] == 0


# --------------------------------------------------------------- averbar


def test_o_numero_do_ato_e_continuo_entre_registro_e_averbacao():
    con = banco()
    r = cedula(con)
    av = RA.averbar(con, r["registro_id"], teor="Averbação de prorrogação.",
                    agora=AGORA)
    assert av["rotulo"] == "AV-2"
    av2 = RA.averbar(con, r["registro_id"], teor="Averbação de liquidação.",
                     agora=AGORA)
    assert av2["rotulo"] == "AV-3"
    atos = RA.atos_do(con, r["registro_id"])
    assert [(a["tipo"], a["numero"]) for a in atos] == [("R", 1), ("AV", 2), ("AV", 3)]


def test_averbacao_exige_teor():
    con = banco()
    r = cedula(con)
    with pytest.raises(RA.RaError, match="dez letras"):
        RA.averbar(con, r["registro_id"], teor="curto", agora=AGORA)


def test_averbacao_com_natureza_fora_do_catalogo_e_recusada():
    con = banco()
    r = cedula(con)
    with pytest.raises(RA.RaError, match="não é do Livro 3"):
        RA.averbar(con, r["registro_id"], teor="Averbação qualquer aqui.",
                   natureza="COMPRA_E_VENDA", agora=AGORA)


def test_nao_averba_registro_cancelado():
    con = banco()
    r = cedula(con)
    RA.cancelar(con, r["registro_id"], motivo="Liquidação integral da cédula.",
                agora=AGORA)
    with pytest.raises(RA.RaError, match="só se averba registro ativo"):
        RA.averbar(con, r["registro_id"], teor="Nova averbação.", agora=AGORA)


# ---------------------------------------------------------- o cancelamento


def test_o_cancelamento_e_uma_averbacao_e_nao_um_apagamento():
    con = banco()
    r = cedula(con)
    c = RA.cancelar(con, r["registro_id"],
                    motivo="Liquidação integral da cédula.", agora=AGORA)
    assert c["rotulo"] == "AV-2"
    assert RA.registro(con, r["registro_id"])["situacao"] == "CANCELADO"
    ato = next(a for a in RA.atos_do(con, r["registro_id"]) if a["numero"] == 2)
    assert ato["motivo_cancelamento"] == "Liquidação integral da cédula."
    # o registro continua na ficha
    assert RA.por_numero(con, r["numero"]) is not None


def test_cancelamento_exige_motivo():
    con = banco()
    r = cedula(con)
    with pytest.raises(RA.RaError, match="dez letras"):
        RA.cancelar(con, r["registro_id"], motivo="pago", agora=AGORA)


def test_nao_cancela_duas_vezes():
    con = banco()
    r = cedula(con)
    RA.cancelar(con, r["registro_id"], motivo="Liquidação integral.", agora=AGORA)
    with pytest.raises(RA.RaError, match="já está com situação"):
        RA.cancelar(con, r["registro_id"], motivo="Segunda tentativa aqui.",
                    agora=AGORA)
