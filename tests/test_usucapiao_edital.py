"""O edital e a ciencia aos entes — relatos #30 e #21, 2a parte.

O RITO TEM TRES ATOS QUE PRODUZEM PAPEL, e ate 30/08/2026 so um deles tinha
modelo. `EDITAL` e `CIENCIA_ENTES` eram etapas com nome e **sem papel**: quem
chegasse nelas escrevia o documento a mao, e dois editais sairiam diferentes.

O QUE ESTES TESTES GUARDAM

    **Que o edital consigna a falta de origem, quando e o caso.** Art. 755, § 2o
    do Codigo de Normas manda dizer **expressamente** — e um edital que cala
    sobre isso e edital que se refaz.

    **Que o prazo do edital nao conta da disponibilizacao.** Sao dois «primeiro
    dia util seguinte» encadeados; quem le com pressa conta de um so, e num
    edital errar por um dia e recomecar.

    **Que os entes sao TRES e saem os tres.** Avisar dois e esquecer o terceiro
    e vicio que so aparece quando o que faltou reclamar — depois de o registro
    estar feito.

    **Que o teor fica guardado**, como na notificacao: o edital que se publicou
    e o de entao.
"""
from __future__ import annotations

import glob
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import us_notificacao as UN                                      # noqa: E402
import usucapiao as US                                           # noqa: E402

AGORA = "2026-08-30T10:00"
SERVENTIA = {"oficial": "MARIO EXEMPLO DOS SANTOS", "cargo": "Oficial",
             "nome": "Serventia Extrajudicial de Cidade Exemplo/MA"}


@pytest.fixture()
def con(cg_db, cg_db_path):
    c = sqlite3.connect(str(cg_db_path))
    c.row_factory = sqlite3.Row
    yield c
    c.close()


@pytest.fixture()
def processo_id(con):
    pid = US.autuar(con, numero="5", modalidade="ORDINARIA", agora=AGORA,
                    requerente_nome="JOÃO BATISTA DE SOUSA",
                    imovel_descricao="Terreno urbano de 12m por 30m",
                    imovel_municipio="Cidade Exemplo", usuario="mario")
    con.execute("UPDATE us_processos SET imovel_area=?, posse_tempo_alegado=? "
                "WHERE id=?", ("360,00 m²", "há mais de quinze anos", pid))
    con.commit()
    return pid


# ------------------------------------------------------------- o edital


def test_o_edital_traz_o_que_a_norma_exige(con, processo_id):
    r = US.publicar_edital(con, processo_id, agora=AGORA,
                           serventia=SERVENTIA,
                           hoje_extenso="Cidade Exemplo/MA, 30 de agosto de 2026")
    for pedaco in ("EDITAL DE USUCAPIÃO EXTRAJUDICIAL", "216-A",
                   "JOÃO BATISTA DE SOUSA", "Terreno urbano",
                   "quinze", "755"):
        assert pedaco in r["teor"], f"faltou «{pedaco}» no edital"


def test_sem_origem_registraria_o_edital_DIZ(con, processo_id):
    """**Art. 755, § 2º manda consignar expressamente.** Um edital que cala
    sobre isso é edital que se refaz."""
    r = US.publicar_edital(con, processo_id, agora=AGORA, serventia=SERVENTIA,
                           imovel_sem_origem=True)
    assert "CONSIGNA-SE EXPRESSAMENTE" in r["teor"]
    assert "755, § 2º" in r["teor"]


def test_com_origem_o_edital_nao_afirma_o_que_nao_e(con, processo_id):
    """Dizer que não tem origem quando tem é afirmação falsa num papel que a
    serventia assina."""
    r = US.publicar_edital(con, processo_id, agora=AGORA, serventia=SERVENTIA)
    assert "CONSIGNA-SE EXPRESSAMENTE" not in r["teor"]


def test_o_edital_remete_ao_artigo_do_prazo_em_vez_de_afirmar_data(con,
                                                                   processo_id):
    """**O prazo não conta da disponibilização.**

    São dois «primeiro dia útil seguinte» encadeados, e quem calcula é
    `us_tjma.inicio_do_prazo`, que sabe dos feriados desta comarca. O papel
    remete ao artigo em vez de afirmar uma data que o montador não tem como
    saber.
    """
    r = US.publicar_edital(con, processo_id, agora=AGORA, serventia=SERVENTIA)
    assert "art. 755, § 1º" in r["teor"]


def test_o_edital_guarda_o_teor(con, processo_id):
    r = US.publicar_edital(con, processo_id, agora=AGORA, serventia=SERVENTIA)
    guardado = con.execute("SELECT teor_expedido, tipo FROM us_movimentos "
                           "WHERE id=?", (r["movimento_id"],)).fetchone()
    assert guardado["tipo"] == "EDITAL"
    assert guardado["teor_expedido"] == r["teor"]


def test_a_data_da_disponibilizacao_manda_no_movimento(con, processo_id):
    """**Ela é de quem publica, e não «hoje»** — é dela que saem os dois saltos,
    e supor hoje faria o prazo começar no dia errado."""
    r = US.publicar_edital(con, processo_id, agora=AGORA, serventia=SERVENTIA,
                           disponibilizado_em="2026-09-02")
    quando = con.execute("SELECT data_movimento FROM us_movimentos WHERE id=?",
                         (r["movimento_id"],)).fetchone()[0]
    assert quando == "2026-09-02"


def test_edital_sem_descricao_do_imovel_e_recusado(con):
    """Edital que não descreve o imóvel não avisa terceiro nenhum."""
    pid = US.autuar(con, numero="6", modalidade="ORDINARIA", agora=AGORA,
                    requerente_nome="FULANO", usuario="mario")
    with pytest.raises(UN.NotificacaoError) as e:
        US.publicar_edital(con, pid, agora=AGORA, serventia=SERVENTIA)
    assert "imóvel" in str(e.value)


# ------------------------------------------------- a ciência aos entes


def test_saem_os_TRES_oficios(con, processo_id):
    """**Avisar dois e esquecer o terceiro** é vício que só aparece quando o
    que faltou reclamar — depois de o registro estar feito."""
    r = US.dar_ciencia_aos_entes(con, processo_id, agora=AGORA,
                                 serventia=SERVENTIA)
    assert [x["ente"] for x in r] == list(UN.ENTES)
    assert len(UN.ENTES) == 3


def test_cada_oficio_nomeia_o_seu_ente(con, processo_id):
    r = US.dar_ciencia_aos_entes(con, processo_id, agora=AGORA,
                                 serventia=SERVENTIA)
    for x in r:
        assert x["ente"] in x["teor"]
        assert "216-A" in x["teor"] and "§ 3º" in x["teor"]


def test_cada_oficio_vira_movimento_com_o_destinatario(con, processo_id):
    r = US.dar_ciencia_aos_entes(con, processo_id, agora=AGORA,
                                 serventia=SERVENTIA)
    for x in r:
        linha = con.execute("SELECT * FROM us_movimentos WHERE id=?",
                            (x["movimento_id"],)).fetchone()
        assert linha["tipo"] == "CIENCIA"
        assert linha["destinatario"] == x["ente"]
        assert linha["prazo_dias"] == 15
        assert linha["teor_expedido"]


def test_ente_que_nao_existe_e_recusado():
    with pytest.raises(UN.NotificacaoError) as e:
        UN.montar_oficio_ao_ente(ente="Consórcio", processo={"numero": "1"},
                                 serventia=SERVENTIA)
    assert "União" in str(e.value)


def test_processo_encerrado_nao_publica_nem_comunica(con, processo_id):
    con.execute("UPDATE us_processos SET situacao='REGISTRADO' WHERE id=?",
                (processo_id,))
    con.commit()
    for funcao in (US.publicar_edital, US.dar_ciencia_aos_entes):
        with pytest.raises(US.UsucapiaoError):
            funcao(con, processo_id, agora=AGORA, serventia=SERVENTIA)


# ------------------------------------------------------------ os manuais


def test_os_dois_manuais_existem_e_dizem_a_base():
    for manual in (UN.MANUAL_DO_EDITAL, UN.MANUAL_DOS_ENTES):
        assert len(manual) >= 4
        for passo in manual:
            assert passo["o_que"] and passo["como"] and "base" in passo


def test_o_manual_do_edital_avisa_dos_DOIS_saltos():
    texto = " ".join(p["como"] for p in UN.MANUAL_DO_EDITAL)
    assert "dois" in texto.lower()
    assert "recomeçar o edital" in texto


def test_o_manual_dos_entes_avisa_que_a_prorrogacao_nao_e_automatica():
    """Ela depende de **solicitação justificada dentro do prazo original**."""
    texto = " ".join(p["como"] for p in UN.MANUAL_DOS_ENTES)
    assert "não é automática" in texto
