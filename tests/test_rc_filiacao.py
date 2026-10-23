"""A filiacao trocada — o achado de 30/08/2026.

COMO APARECEU
    Montando o termo de referencia a partir de um assento REAL da producao, o
    texto saiu «filho de URSULA VALENTE MIRANDA XAVIER e EVANDRO SOUSA SALES»
    — e o declarante era BRUNO. O assento tem `PAI` = VITORIA (sexo F) e `MAE`
    = BRUNO (sexo M). Nao foi o termo que errou: foi o dado que veio trocado.

O QUE ESTES TESTES GUARDAM
    **Que casal do mesmo sexo NAO entra na lista de suspeitas.** E o guarda
    mais importante daqui: uma «correcao» automatica quebraria assentos que
    estao certos. Medidos tres na producao.

    **Que um sinal so nao basta.** `PAI` sem sexo, ou `MAE` de sexo estranho
    sozinho, pode ser sexo mal preenchido na carga. Acusar isso encheria a
    lista de ruido — e lista com ruido ninguem abre duas vezes.

    **Que o modulo nao conserta.** Certidao desses assentos pode ja ter saido,
    e os dados foram para a CRC. A correcao e retificacao (art. 352), e quem a
    decide e o oficial.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import rc_filiacao as F                                        # noqa: E402


def _banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE rc_assentos (id INTEGER PRIMARY KEY, "
                "especie TEXT, numero INTEGER, nome TEXT, data_ato TEXT, "
                "situacao TEXT, origem TEXT)")
    con.execute("CREATE TABLE rc_pessoas (id INTEGER PRIMARY KEY, "
                "assento_id INTEGER, papel TEXT, nome TEXT, sexo TEXT)")

    def assento(id_, nome, situacao="ATIVO"):
        con.execute("INSERT INTO rc_assentos VALUES (?,?,?,?,?,?,?)",
                    (id_, "NASCIMENTO", id_, nome, "2026-08-13", situacao,
                     "EOFICIO"))

    def pessoa(assento_id, papel, nome, sexo):
        con.execute("INSERT INTO rc_pessoas (assento_id, papel, nome, sexo) "
                    "VALUES (?,?,?,?)", (assento_id, papel, nome, sexo))

    # 1 — TROCADO: o do papel PAI e mulher, o do papel MAE e homem.
    assento(1, "BRUNA KIARA")
    pessoa(1, "PAI", "VITORIA PAMELA", "F")
    pessoa(1, "MAE", "BRUNO SOUSA", "M")
    # 2 — CERTO
    assento(2, "CRIANCA CERTA")
    pessoa(2, "PAI", "JOAO", "M")
    pessoa(2, "MAE", "MARIA", "F")
    # 3 — CASAL DO MESMO SEXO: legitimo, e NAO e suspeita
    assento(3, "FILHO DE DOIS PAIS")
    pessoa(3, "PAI", "CARLOS", "M")
    pessoa(3, "MAE", "ANTONIO", "M")
    # 4 — SEM SEXO: sinal nenhum, e nao entra em «trocada»
    assento(4, "SEM SEXO NA FILIACAO")
    pessoa(4, "PAI", "SEM SEXO", "")
    pessoa(4, "MAE", "TAMBEM SEM", None)
    # 5 — UM SINAL SO: PAI mulher, mas MAE tambem mulher
    assento(5, "UM SINAL SO")
    pessoa(5, "PAI", "ANA", "F")
    pessoa(5, "MAE", "BEATRIZ", "F")
    # 6 — CANCELADO: nao entra
    assento(6, "CANCELADO", situacao="CANCELADO")
    pessoa(6, "PAI", "X", "F")
    pessoa(6, "MAE", "Y", "M")
    con.commit()
    return con


def test_acha_o_trocado():
    con = _banco()
    achados = F.filiacao_trocada(con)
    assert [a["numero"] for a in achados] == [1]
    a = achados[0]
    assert a["pai_nome"] == "VITORIA PAMELA" and a["pai_sexo"] == "F"
    assert a["mae_nome"] == "BRUNO SOUSA" and a["mae_sexo"] == "M"
    con.close()


def test_casal_do_mesmo_sexo_nao_e_suspeita():
    """**O GUARDA MAIS IMPORTANTE DAQUI.** Casal do mesmo sexo e assento
    legitimo; uma «correcao» automatica quebraria o que esta certo."""
    con = _banco()
    numeros = [a["numero"] for a in F.filiacao_trocada(con)]
    assert 3 not in numeros, "acusou um casal do mesmo sexo de estar trocado"
    assert 5 not in numeros
    con.close()


def test_o_mesmo_sexo_tem_lista_propria():
    """Separa-los e o que impede alguem de «corrigir» o que esta certo."""
    con = _banco()
    numeros = sorted(a["numero"] for a in F.duas_filiacoes_do_mesmo_sexo(con))
    assert numeros == [3, 5]
    con.close()


def test_um_sinal_so_nao_basta():
    """Sexo mal preenchido na carga nao e troca. Lista com ruido ninguem abre
    duas vezes."""
    con = _banco()
    numeros = [a["numero"] for a in F.filiacao_trocada(con)]
    assert 4 not in numeros
    con.close()


def test_sem_sexo_tem_lista_propria_e_vale_por_si():
    """**E o sexo que decide como o termo escreve a filiacao**, e e ele que a
    remessa do IBGE pede."""
    con = _banco()
    nomes = sorted(x["pessoa_nome"] for x in F.sem_sexo(con))
    assert nomes == ["SEM SEXO", "TAMBEM SEM"]
    con.close()


def test_cancelado_nao_entra():
    con = _banco()
    assert 6 not in [a["numero"] for a in F.filiacao_trocada(con)]
    con.close()


def test_o_resumo_nunca_e_escrito_a_mao():
    con = _banco()
    r = F.resumo(con)
    assert r == {"trocadas": 1, "mesmo_sexo": 2, "sem_sexo": 2}
    con.close()


def test_o_modulo_nao_conserta_nada():
    """Certidao desses assentos pode ja ter saido, e os dados foram para a CRC.
    Trocar aqui deixaria o nosso banco discordando da Central — pior que
    discordar de si mesmo. A correcao e retificacao, e a decisao e do oficial.
    """
    codigo = (RAIZ / "rc_filiacao.py").read_text(encoding="utf-8")
    for proibido in ("INSERT INTO", "UPDATE ", "DELETE FROM"):
        assert proibido not in codigo, f"o módulo escreve com «{proibido}»"


def test_diz_o_que_fazer_e_nao_so_que_esta_errado():
    """Lista que aponta erro sem dizer o caminho vira lista que ninguem
    resolve."""
    assert "retifica" in F.O_QUE_FAZER.lower()
    assert "352" in F.O_QUE_FAZER
    assert F.MOTIVO


def test_os_avos_acompanham_a_filiacao():
    """Se pai e mae estao trocados, o «paterno» e o «materno» estao trocados
    junto — foi o que se viu no nº 19.552, pelos sobrenomes. Consertar um sem
    o outro deixaria o assento pior do que esta."""
    assert F.AVOS_DO_PAI == ("AVO_PATERNO", "AVO_PATERNA")
    assert F.AVOS_DA_MAE == ("AVO_MATERNO", "AVO_MATERNA")
