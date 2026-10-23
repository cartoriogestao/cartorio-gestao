"""O AVISO DO SELO ANTES DE EMITIR A CERTIDÃO — relato do oficial 10/09/2026.

    «nao estou conseguindo emitir selo gratuito para certidao do marcos dione.
     Na ultima o selo que era pra ser gratuito foi pago»

O QUE ACONTECEU, medido na produção:

    O assento 1233 (nascimento de 1996) veio do **ARQUIVO** e não tem selo de
    registro. A regra que o oficial deu em 09/09 presume **segunda via** nesse
    caso — e a tela, obedecendo-a, comprou um `CERTID` **pago** sem dizer que
    ia comprar. O escrevente só descobriu lendo o selo.

O QUE ESTES TESTES GUARDAM:

      - **a tela diz, antes de emitir, se o selo vai ser cobrado** — e o caso
        do assento importado sem selo de registro é o que ganha faixa de
        aviso, porque é o que custou dinheiro;
      - **a 1ª via de um assento lavrado aqui continua gratuita**, usando o
        selo do registro, e a tela diz qual é;
      - e **a regra é lida da mesma função que sela**, e não copiada — duas
        cópias divergiriam e a tela passaria a prometer o que o selo não faz.
"""
from __future__ import annotations

import itertools
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import rc_certidao as RCE
import nucleo_schema
import rc_schema
from banco_de_teste import conexao_de_teste  # noqa: E402

AGORA = "2026-09-10T16:00:00"


@pytest.fixture()
def con(tmp_path):
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    # `rc_atos.livro_id` aponta para `nu_livros` (FK): o PostgreSQL cobra a
    # FK na criacao, e o banco da casa cria o nucleo antes do RCPN.
    nucleo_schema.init_nucleo_schema(c)
    rc_schema.init_rc_schema(c)
    # `rc_certidoes` nasce em `rc_certidao.py`, e nao em `rc_schema` — o
    # predicado da 1a via conta as certidoes ativas, e sem a tabela ele
    # estoura em vez de responder.
    RCE.init_rc_certidao_schema(c)
    yield c
    c.close()


# **A CHAVE DE ORIGEM E UNICA, e `rc_assentos` tem `UNIQUE(origem,
# origem_chave)`.** A primeira versao deste ajudante montava a chave de
# `origem` e `especie`, e o teste que percorre as tres origens com e sem selo
# pedia o mesmo assento duas vezes — `IntegrityError` no segundo.
#
# Um contador resolve, e ele mora aqui de proposito: o que o teste guarda e a
# regra do selo, e nao a chave.
_SEQUENCIA = itertools.count(1)


def _assento(con, *, origem="MANUAL", especie="NASCIMENTO") -> int:
    cur = con.execute(
        """INSERT INTO rc_assentos(serie, especie, numero, matricula, nome,
               data_ato, data_fato, dados_json, origem, origem_chave, criado_em)
           VALUES ('RC_A',?,?,?,?,?,?,'{}',?,?,?)""",
        (especie, 9313, "0" * 32, "Braulio Galvao Oliveira Ribeiro",
         "1996-06-12", "1987-04-02", origem,
         f"chave-{origem}-{especie}-{next(_SEQUENCIA)}", AGORA))
    return int(cur.lastrowid)


def _registro_selado(con, assento_id, selo="REGNAS000000ABC"):
    con.execute(
        """INSERT INTO rc_atos(assento_id, tipo, selo, data_ato, criado_em)
           VALUES (?,?,?,?,?)""",
        (assento_id, "REGISTRO", selo, "1996-06-12", AGORA))


# ======================================= o caso que custou dinheiro

def test_assento_importado_sem_selo_de_registro_avisa_que_vai_cobrar(con):
    """**É o caso do Marcos Dione**, e é o único que ganha faixa de aviso."""
    aid = _assento(con, origem="ARQUIVO")
    v = RCE.como_vai_selar(con, aid)
    assert v["via"] == "SEGUNDA"
    assert v["cobra"] is True
    assert v["avisar"] is True
    assert "COBRADO" in v["porque"]
    # E diz o caminho de saída, que é a marcação manual.
    assert "gratuito" in v["porque"].lower()


def test_o_eoficio_avisa_igual(con):
    """As duas origens importadas estão na mesma regra — medido."""
    aid = _assento(con, origem="EOFICIO")
    assert RCE.como_vai_selar(con, aid)["avisar"] is True


def test_importacao_avisa_igual(con):
    """A origem gravada pelo importador novo tambem e acervo importado."""
    aid = _assento(con, origem="IMPORTACAO")
    v = RCE.como_vai_selar(con, aid)
    assert v["via"] == "SEGUNDA"
    assert v["cobra"] is True
    assert v["avisar"] is True


def test_importado_COM_selo_de_registro_e_primeira_via_gratuita(con):
    """Se o registro tem selo, a 1ª via usa ele — mesmo vindo de fora."""
    aid = _assento(con, origem="ARQUIVO")
    _registro_selado(con, aid)
    v = RCE.como_vai_selar(con, aid)
    assert v["via"] == "PRIMEIRA"
    assert v["cobra"] is False
    assert v["selo_do_registro"] == "REGNAS000000ABC"
    assert "REGNAS000000ABC" in v["porque"]


# ============================================ o assento lavrado nesta casa

def test_assento_lavrado_aqui_e_primeira_via_gratuita(con):
    aid = _assento(con, origem="MANUAL")
    _registro_selado(con, aid)
    v = RCE.como_vai_selar(con, aid)
    assert v["via"] == "PRIMEIRA" and v["cobra"] is False
    assert v["avisar"] is False


def test_lavrado_aqui_sem_selo_no_registro_manda_selar_o_registro(con):
    """Não é «compre CERTID»: é «sele o registro primeiro»."""
    aid = _assento(con, origem="MANUAL")
    v = RCE.como_vai_selar(con, aid)
    assert v["via"] == "PRIMEIRA" and v["cobra"] is False
    assert "registro ainda não tem selo" in v["porque"]


def test_a_segunda_certidao_cobra_e_nao_avisa(con):
    """Segunda via de verdade é cobrança esperada — faixa de aviso seria ruído."""
    aid = _assento(con, origem="MANUAL")
    _registro_selado(con, aid)
    con.execute(
        """INSERT INTO rc_certidoes(numero, ano, assento_id, especie, nome,
               matricula, atos_no_assento, teor, hash_teor, emitida_em)
           VALUES (1,2026,?, 'NASCIMENTO','Marcos', ?, 1, 'x', 'h', ?)""",
        (aid, "0" * 32, AGORA))
    v = RCE.como_vai_selar(con, aid)
    assert v["via"] == "SEGUNDA" and v["cobra"] is True
    assert v["avisar"] is False


def test_a_certidao_cancelada_nao_gasta_a_primeira_via(con):
    """Três tentativas sem selo foram canceladas — e a 1ª via tem de sobrar.

    Medido na produção: as certidões 16, 17 e 23 do assento 1233 saíram sem
    selo e foram canceladas. Se contassem, o escrevente perderia a gratuidade
    por causa de um defeito do sistema.
    """
    aid = _assento(con, origem="MANUAL")
    _registro_selado(con, aid)
    con.execute(
        """INSERT INTO rc_certidoes(numero, ano, assento_id, especie, nome,
               matricula, atos_no_assento, teor, hash_teor, emitida_em,
               cancelada_em, cancelada_motivo)
           VALUES (1,2026,?, 'NASCIMENTO','Marcos', ?, 1, 'x', 'h', ?, ?,
                   'emitida sem selo')""",
        (aid, "0" * 32, AGORA, AGORA))
    assert RCE.como_vai_selar(con, aid)["via"] == "PRIMEIRA"


# ================================================= a regra é uma só

def test_o_veredito_concorda_com_quem_sela(con):
    """**Duas cópias da regra divergiriam no primeiro conserto.**

    A tela prometeria uma coisa e o selo faria outra — que é o defeito que
    este aviso existe para não cometer.
    """
    for origem in ("MANUAL", "ARQUIVO", "EOFICIO"):
        for com_selo in (False, True):
            aid = _assento(con, origem=origem)
            if com_selo:
                _registro_selado(con, aid, selo=f"REGNAS-{origem}")
            primeira = RCE.eh_primeira_certidao_do_registro(
                con, aid, certidao_id=None, especie="NASCIMENTO")
            v = RCE.como_vai_selar(con, aid)
            assert (v["via"] == "PRIMEIRA") is primeira, (origem, com_selo)
            assert v["cobra"] is not primeira, (origem, com_selo)


def test_especie_sem_primeira_via_no_registro_nao_avisa(con):
    """O casamento não tem 1ª via no registro — ele vem da habilitação."""
    aid = _assento(con, origem="ARQUIVO", especie="CASAMENTO")
    v = RCE.como_vai_selar(con, aid)
    assert v["via"] == "SEGUNDA"
    assert v["avisar"] is False
