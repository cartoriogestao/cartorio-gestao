"""
Testes da certidao de inteiro teor do RCPJ, do RTD e do Livro 3.

O QUE ELES CONFEREM
    Que a certidao REPRODUZ O LIVRO, e nao redige nada: o teor sai do registro,
    e quem nao tem teor nao ganha certidao de inteiro teor — ganha a resposta
    de que o registro existe e que a copia se tira do livro fisico.

    Que os textos sao os DA CASA, medidos nas certidoes que o E-Oficio guardou:
    38 em `tbTD_Certidao` e 6 em `LivroAuxiliarCertidao`.

    E que o teor CONGELA: averbacao lavrada amanha nao muda a certidao de hoje.

    Ha tambem um teste contra o acervo REAL, que roda so onde ele existe.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — referencia acervo_eoficio ou sqlite de producao
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import atrib_certidao as CE
from nucleo_schema import init_nucleo_schema
from ra_schema import init_ra_schema
from rg_schema import init_rg_schema
from ri_schema import init_ri_schema

HOJE = "2026-08-25"
AGORA = "2026-08-25T21:00:00"
ACERVO_REAL = Path(r"C:\ProgramData\CartorioGestao") / "acervo_eoficio.sqlite3"

TEOR = ("Aos 26 dias do mês de novembro de dois mil e vinte e um, nesta cidade "
        "de Cidade Exemplo, reuniram-se em Assembleia Geral os associados.")


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    # `rg_titulos` aponta para `cx_protocolos` (FK): o PostgreSQL cobra a FK
    # na criacao, e o banco da casa cria o caixa antes. Aqui basta o esqueleto.
    con.execute("CREATE TABLE IF NOT EXISTS cx_protocolos (id INTEGER PRIMARY KEY)")
    init_rg_schema(con)
    # `ri_schema` aponta para `users` (FK): o PostgreSQL cobra a FK
    # na criacao, e o banco da casa cria `users` antes. Aqui basta o esqueleto.
    con.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)")
    init_ri_schema(con)
    init_ra_schema(con)
    CE.init_atrib_certidao_schema(con)
    return con


def registro_rg(con, *, teor=TEOR, serie="PJ_A", volume="05", numero=344,
                natureza="ATA DA ASSEMBLEIA GERAL", situacao="ATIVO",
                folha=30, data="2022-01-31", teor_no_ato=None) -> int:
    cur = con.execute(
        """INSERT INTO rg_registros(atribuicao, serie, volume, numero, natureza,
               requerente_nome, situacao, teor, origem, criado_em)
           VALUES (?,?,?,?,?,'CAIXA ESCOLAR',?,?,'EOFICIO',?)""",
        (3 if serie.startswith("PJ") else 4, serie, volume, numero, natureza,
         situacao, teor, AGORA))
    registro_id = int(cur.lastrowid)
    con.execute(
        """INSERT INTO rg_atos(registro_id, tipo, folha, numero_ordem, data_ato,
               teor, origem, criado_em)
           VALUES (?,'REGISTRO',?,?,?,?,'EOFICIO',?)""",
        (registro_id, folha, numero, data, teor_no_ato, AGORA))
    return registro_id


def registro_ra(con, *, teor=TEOR, numero=1549) -> int:
    cur = con.execute(
        """INSERT INTO ra_registros(numero, livro, natureza, titulo_tipo,
               titulo_numero, situacao, teor, origem, criado_em)
           VALUES (?,'3','CEDULA_CREDITO_RURAL','CÉDULA RURAL PIGNORATÍCIA',
                   '40/01800-8','ATIVO',?,'EOFICIO',?)""",
        (numero, teor, AGORA))
    registro_id = int(cur.lastrowid)
    con.execute(
        """INSERT INTO ra_atos(registro_id, tipo, numero, data_ato, origem,
               criado_em)
           VALUES (?,'R',1,'2020-06-08','EOFICIO',?)""", (registro_id, AGORA))
    return registro_id


# ---------------------------------------------------------------- o teor


def test_a_certidao_do_rcpj_diz_o_livro_a_folha_o_ato_e_a_data():
    # A cabeca e a das 38 certidoes do acervo: `no Livro "A-5" de Registro de
    # Pessoas Juridicas, fls. 030, ATO n. 344 datada de 31/01/2022`.
    con = banco()
    rid = registro_rg(con)
    r = CE.emitir(con, "RCPJ_RTD", rid, hoje=HOJE, agora=AGORA)
    assert r["teor"].startswith("CERTIFICO E DOU FÉ")
    assert 'no Livro "A-5" de Registro de Pessoas Jurídicas' in r["teor"]
    assert "fls. 30" in r["teor"]
    assert "ATO n. 344" in r["teor"]
    assert "datada de 31/01/2022" in r["teor"]     # data de balcão, não ISO
    assert "ATA DA ASSEMBLEIA GERAL" in r["teor"]
    assert "COM O SEGUINTE TEOR" in r["teor"]
    assert "Para conhecimento de terceiros e sua conservação" in r["teor"]
    assert TEOR in r["teor"]


def test_o_rtd_e_nomeado_pelo_registro_dele():
    con = banco()
    rid = registro_rg(con, serie="TD_B", volume="7")
    r = CE.emitir(con, "RCPJ_RTD", rid, hoje=HOJE, agora=AGORA)
    assert 'no Livro "B-7" de Registro de Títulos e Documentos' in r["teor"]


def test_o_nome_do_livro_nao_sai_duplicado():
    # Eu tinha usado `livro_nucleo.SERIES[...].nome` aqui, e saia
    # `no Livro "A-4" de Livro A do Registro Civil das Pessoas Juridicas`.
    # A certidao nomeia o REGISTRO; o livro ela ja disse entre aspas.
    con = banco()
    r = CE.emitir(con, "RCPJ_RTD", registro_rg(con), hoje=HOJE, agora=AGORA)
    assert "de Livro A do" not in r["teor"]


def test_a_certidao_do_livro_3_usa_a_frase_da_casa():
    con = banco()
    rid = registro_ra(con)
    r = CE.emitir(con, "LIVRO3", rid, hoje=HOJE, agora=AGORA)
    assert "revendo os livros próprios desta Serventia Imobiliária" in r["teor"]
    assert "Livro 3 Auxiliar de Registro Geral de Imóveis" in r["teor"]
    assert "no registro n.1549 o seguinte:-" in r["teor"]
    assert TEOR in r["teor"]


def test_sem_teor_nao_ha_certidao_de_inteiro_teor():
    # 24 dos 72 registros do RCPJ/RTD vieram do acervo sem o texto. Certidao
    # de inteiro teor sem o teor seria papel que promete o que nao entrega.
    con = banco()
    rid = registro_rg(con, teor=None)
    with pytest.raises(CE.CertidaoError) as erro:
        CE.emitir(con, "RCPJ_RTD", rid, hoje=HOJE, agora=AGORA)
    assert "existe no livro" in str(erro.value)
    assert "livro físico" in str(erro.value)
    assert con.execute("SELECT COUNT(*) FROM at_certidoes").fetchone()[0] == 0


def test_o_teor_do_ato_serve_quando_o_registro_nao_tem():
    # No RCPJ/RTD a carga poe o inteiro teor no registro E no ato. Se um
    # faltar, o outro serve — e a certidao sai.
    con = banco()
    rid = registro_rg(con, teor=None, teor_no_ato=TEOR)
    r = CE.emitir(con, "RCPJ_RTD", rid, hoje=HOJE, agora=AGORA)
    assert TEOR in r["teor"]


def test_registro_cancelado_certifica_e_diz_que_esta_cancelado():
    # Recusar seria esconder o que existe; calar seria mentir.
    con = banco()
    rid = registro_rg(con, situacao="CANCELADO")
    r = CE.emitir(con, "RCPJ_RTD", rid, hoje=HOJE, agora=AGORA)
    assert "encontra-se CANCELADO nesta Serventia" in r["teor"]


def test_atribuicao_desconhecida_e_recusada_com_frase_de_balcao():
    with pytest.raises(CE.CertidaoError) as erro:
        CE.emitir(banco(), "RCPN", 1, hoje=HOJE, agora=AGORA)
    assert "Atribuição desconhecida" in str(erro.value)


def test_registro_que_nao_existe_e_recusado():
    with pytest.raises(CE.CertidaoError) as erro:
        CE.emitir(banco(), "LIVRO3", 999, hoje=HOJE, agora=AGORA)
    assert "não encontrado" in str(erro.value)


# --------------------------------------------------------------- a emissao


def test_a_numeracao_e_por_atribuicao_e_por_exercicio():
    # O acervo tinha uma tabela de certidoes por atribuicao, e cada uma
    # numerava a sua.
    con = banco()
    a = CE.emitir(con, "RCPJ_RTD", registro_rg(con, numero=1), hoje="2026-08-25",
                  agora=AGORA)
    b = CE.emitir(con, "RCPJ_RTD", registro_rg(con, numero=2), hoje="2026-12-31",
                  agora=AGORA)
    c = CE.emitir(con, "LIVRO3", registro_ra(con, numero=1), hoje="2026-08-25",
                  agora=AGORA)
    d = CE.emitir(con, "RCPJ_RTD", registro_rg(con, numero=3), hoje="2027-01-02",
                  agora=AGORA)
    assert (a["numero"], a["ano"]) == (1, 2026)
    assert (b["numero"], b["ano"]) == (2, 2026)
    assert (c["numero"], c["ano"]) == (1, 2026)   # série própria do Livro 3
    assert (d["numero"], d["ano"]) == (1, 2027)   # exercício novo recomeça


def test_o_teor_congela_e_a_certidao_diz_quantos_atos_havia():
    con = banco()
    rid = registro_rg(con)
    r = CE.emitir(con, "RCPJ_RTD", rid, hoje=HOJE, agora=AGORA)
    assert r["atos"] == 1
    con.execute(
        """INSERT INTO rg_atos(registro_id, tipo, data_ato, teor, origem,
               criado_em)
           VALUES (?,'AVERBACAO','2026-08-26','Averbação depois.','MANUAL',?)""",
        (rid, AGORA))
    guardada = CE.certidao(con, r["certidao_id"])
    assert guardada["atos"] == 1                  # o número da emissão
    assert "Averbação depois." not in guardada["teor"]


def test_a_certidao_guarda_quem_pediu_e_para_que():
    con = banco()
    r = CE.emitir(con, "LIVRO3", registro_ra(con), hoje=HOJE, agora=AGORA,
                  requerente="BANCO DO BRASIL", finalidade="prova",
                  usuario="TABELIÃO")
    linha = CE.certidao(con, r["certidao_id"])
    assert linha["requerente"] == "BANCO DO BRASIL"
    assert linha["finalidade"] == "prova"
    assert linha["emitida_por"] == "TABELIÃO"
    assert linha["registro_numero"] == "1549"
    assert len(linha["hash_certidao"]) == 64


def test_o_hash_muda_quando_o_teor_muda():
    a = CE.hash_certidao("LIVRO3", 1, 2026, "teor um", AGORA)
    b = CE.hash_certidao("LIVRO3", 1, 2026, "teor dois", AGORA)
    assert a != b and len(a) == 64


def test_listar_separa_por_atribuicao():
    con = banco()
    CE.emitir(con, "RCPJ_RTD", registro_rg(con), hoje=HOJE, agora=AGORA)
    CE.emitir(con, "LIVRO3", registro_ra(con), hoje=HOJE, agora=AGORA)
    assert len(CE.listar(con)) == 2
    assert len(CE.listar(con, atribuicao="LIVRO3")) == 1
    assert len(CE.listar(con, atribuicao="RCPJ_RTD")) == 1


# ------------------------------------------------------------- cancelar


def test_cancelar_exige_motivo_escrito_e_guarda_o_teor():
    con = banco()
    r = CE.emitir(con, "LIVRO3", registro_ra(con), hoje=HOJE, agora=AGORA)
    with pytest.raises(CE.CertidaoError) as erro:
        CE.cancelar(con, r["certidao_id"], motivo="erro", agora=AGORA)
    assert "dez letras" in str(erro.value)
    CE.cancelar(con, r["certidao_id"], motivo="emitida sobre o registro errado",
                agora=AGORA, usuario="TABELIÃO", selo_cancelado_tjma=True)
    linha = CE.certidao(con, r["certidao_id"])
    assert int(linha["cancelada"]) == 1
    assert TEOR in linha["teor"]                  # o teor fica, como saiu
    assert linha["declaracao_selo_tjma_por"] == "TABELIÃO"
    with pytest.raises(CE.CertidaoError) as erro:
        CE.cancelar(con, r["certidao_id"], motivo="de novo, por engano",
                    agora=AGORA)
    assert "já está cancelada" in str(erro.value)


# ------------------------------------------------------------ utilidades


@pytest.mark.parametrize("serie,volume,esperado", [
    ("PJ_A", "05", "A-5"), ("TD_B", "7", "B-7"), ("PJ_A", "04", "A-4"),
    ("TD_C", None, "C"), ("TD_F", "", "F"),
])
def test_o_livro_sai_como_o_acervo_escreve(serie, volume, esperado):
    assert CE._livro_impresso(serie, volume) == esperado


def test_reconhece_o_cabecalho_antigo_dentro_do_teor():
    # O E-Oficio guardava a PAGINA INTEIRA, com o brasao e a serventia no
    # alto. Quando o teor ja o traz, o `.odt` nao poe outro em cima.
    com = ("REPÚBLICA FEDERATIVA DO BRASIL ESTADO DO MARANHÃO "
           "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO-MA " + TEOR)
    assert CE.teor_traz_cabecalho(com) is True
    assert CE.teor_traz_cabecalho(TEOR) is False
    # As duas marcas sao exigidas: uma so nao basta.
    assert CE.teor_traz_cabecalho("REPÚBLICA FEDERATIVA DO BRASIL " + TEOR) is False


# ---------------------------------------------------- contra o acervo real


@pytest.mark.skipif(not ACERVO_REAL.exists(),
                    reason="o acervo do E-Ofício não está nesta máquina")
def test_contra_o_acervo_real():
    """A certidao sobre os registros que a casa realmente lavrou."""
    import acervo_carga as AC
    from pt_schema import init_pt_schema
    from rc_schema import init_rc_schema

    con = banco()
    init_pt_schema(con)
    init_rc_schema(con)
    acervo = AC.abrir_acervo(ACERVO_REAL.parent)
    AC.carregar_rcpj_rtd(con, acervo, agora=AGORA)
    AC.carregar_registro_auxiliar(con, acervo, agora=AGORA)

    # O ato de REGISTRO que a carga passou a lavrar em 25/08/2026 — foi a
    # certidao que o cobrou, porque ela precisa da folha e da data.
    assert con.execute("SELECT COUNT(*) FROM rg_atos").fetchone()[0] == 72
    assert con.execute(
        "SELECT COUNT(*) FROM rg_atos WHERE folha IS NOT NULL").fetchone()[0] == 72
    assert con.execute(
        "SELECT COUNT(*) FROM rg_registros WHERE volume IS NOT NULL"
        ).fetchone()[0] == 72

    emitidas = recusadas = 0
    for atribuicao, tabela in (("RCPJ_RTD", "rg_registros"),
                               ("LIVRO3", "ra_registros")):
        for linha in con.execute(f"SELECT id FROM {tabela}"):
            try:
                CE.emitir(con, atribuicao, int(linha["id"]), hoje=HOJE,
                          agora=AGORA)
                emitidas += 1
            except CE.CertidaoError:
                recusadas += 1
    # Remedido em 19/09/2026: 62 emitem (antes 60 em 25/08/2026). 48 dos 72 do RCPJ/RTD e 12 dos 14 do Livro 3 tem
    # teor. Os outros 26 constam do livro e nao geram inteiro teor.
    assert emitidas == 62
    assert recusadas == 24
