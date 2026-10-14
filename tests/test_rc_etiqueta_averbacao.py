"""Etiqueta ODT da averbação RCPN: lavrou, selo, medidas e arquivo."""
from __future__ import annotations

import io
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import etiqueta as ETQ
import rc_assento as RC
import rc_etiqueta_averbacao as RCETQ
import rc_schema as RCS


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(RCS.SCHEMA)
    for tabela, coluna, tipo in getattr(RCS, "MIGRACOES", ()):
        try:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
        except sqlite3.OperationalError:
            pass
    # minimo para assento
    con.execute(
        """INSERT INTO rc_assentos(
               serie, especie, numero, nome, data_ato, situacao, origem,
               criado_em, livro_volume)
           VALUES ('RC_A','NASCIMENTO',1,'Fulano','2026-01-01','ATIVO',
                   'MANUAL','2026-01-01T00:00:00','A-1')""")
    return con


def test_teor_ganha_lavrou_na_lavratura():
    """Averbacao generica ainda ganha linha «Lavrado por:»; CPF nao."""
    con = _con()
    r = RC.averbar(con, 1, teor="Averbo retificacao de grafia do nome do pai.",
                   agora="2026-09-08T12:00:00", usuario="Jean Santos")
    ato = con.execute("SELECT teor, criado_por FROM rc_atos WHERE id=?",
                      (r["ato_id"],)).fetchone()
    assert "Lavrado por: Jean Santos." in ato["teor"]
    assert ato["criado_por"] == "Jean Santos"
    # CPF: lavratura parcial sem «Lavrado por:» — usuario entra apos o selo.
    import rc_cpf as CPF
    r2 = RC.averbar(con, 1, teor=CPF.texto_averbacao("00000001597"),
                    agora="2026-09-08T12:00:00", usuario="Jean Santos",
                    fundamento="art. 347 do Código de Normas do TJMA")
    ato2 = con.execute("SELECT teor FROM rc_atos WHERE id=?",
                       (r2["ato_id"],)).fetchone()
    assert ato2["teor"] == "Averbo neste assento o CPF n. 000.000.015-97."
    assert "Lavrado por:" not in ato2["teor"]


def test_sincronizar_reescreve_teor_cpf_apos_selo():
    """Apos selar, teor CPF fica curto: CPF. selo. data. usuario (sem função se desconhecida)."""
    import rc_cpf as CPF
    con = _con()
    r = RC.averbar(con, 1, teor=CPF.texto_averbacao("00000001597"),
                   agora="2026-09-08T12:00:00", usuario="Jean Santos",
                   fundamento="art. 347 do Código de Normas do TJMA")
    con.execute("UPDATE rc_atos SET selo=? WHERE id=?",
                ("AVERBA000000WOGST2V2BKC6LG79", r["ato_id"]))
    t1 = RCETQ.sincronizar_teor_do_ato(con, r["ato_id"])
    t2 = RCETQ.sincronizar_teor_do_ato(con, r["ato_id"])
    esperado = (
        "Averbo neste assento o CPF n. 000.000.015-97. "
        "AVERBA000000WOGST2V2BKC6LG79. 08/09/2026. Jean Santos.")
    assert t1 == esperado
    assert t2 == t1
    assert "Lavrado por:" not in t1
    assert "art. 347" not in t1


def test_sincronizar_teor_cpf_com_funcao_do_usuario():
    """Com users.funcao cadastrada, o teor fecha com nome, cargo."""
    import rc_cpf as CPF
    con = _con()
    con.execute(
        """CREATE TABLE users (
               id INTEGER PRIMARY KEY, username TEXT, full_name TEXT,
               funcao TEXT)""")
    con.execute(
        "INSERT INTO users(id, username, full_name, funcao) "
        "VALUES (1, 'jean', 'Jean Santos', "
        "'Tabelião e Oficial de Registro')")
    r = RC.averbar(con, 1, teor=CPF.texto_averbacao("00000001597"),
                   agora="2026-09-08T12:00:00", usuario="Jean Santos",
                   fundamento="art. 347 do Código de Normas do TJMA")
    con.execute("UPDATE rc_atos SET selo=? WHERE id=?",
                ("AVERBA000000WOGST2V2BKC6LG79", r["ato_id"]))
    teor = RCETQ.sincronizar_teor_do_ato(con, r["ato_id"])
    assert teor == (
        "Averbo neste assento o CPF n. 000.000.015-97. "
        "AVERBA000000WOGST2V2BKC6LG79. 08/09/2026. "
        "Jean Santos, Tabelião e Oficial de Registro.")


def test_sincronizar_acrescenta_selo_sem_duplicar_generico():
    con = _con()
    r = RC.averbar(con, 1, teor="Averbo retificacao de grafia do sobrenome.",
                   agora="2026-09-08T12:00:00", usuario="Jean Santos")
    con.execute("UPDATE rc_atos SET selo=? WHERE id=?",
                ("AVESVD000000TESTESELO0001", r["ato_id"]))
    t1 = RCETQ.sincronizar_teor_do_ato(con, r["ato_id"])
    t2 = RCETQ.sincronizar_teor_do_ato(con, r["ato_id"])
    assert t1.count("Selo: AVESVD000000TESTESELO0001.") == 1
    assert t2 == t1
    assert "Lavrado por: Jean Santos." in t1


def test_odt_contem_teor_lavrou_selo_e_refs():
    import rc_cpf as CPF
    con = _con()
    r = RC.averbar(con, 1, teor=CPF.texto_averbacao("00000001597"),
                   agora="2026-09-08T12:00:00", usuario="Debora",
                   fundamento="art. 347 do Código de Normas do TJMA")
    con.execute("UPDATE rc_atos SET selo=? WHERE id=?",
                ("AVESVD000000ABCDEFGH00001", r["ato_id"]))
    RCETQ.sincronizar_teor_do_ato(con, r["ato_id"])
    dados = RCETQ.dados_da_etiqueta(con, r["ato_id"],
                                   sv={"unit_name": "Cartório Teste"})
    m = ETQ.medidas(lambda: {}, ETQ.AVERBACAO_RCPN)
    odt = RCETQ.arquivo_odt(dados, m)
    assert odt[:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(odt)) as z:
        xml = z.read("content.xml").decode("utf-8")
        styles = z.read("styles.xml").decode("utf-8")
    assert "Debora" in xml
    assert "AVESVD000000ABCDEFGH00001" in xml
    assert "Averbo neste assento" in xml
    assert "08/09/2026" in xml
    assert "Lavrado por:" not in xml
    assert xml.count("Debora") == 1
    assert "assento 1" in xml
    assert "5.5000cm" in styles or "5.5cm" in styles
    assert "fo:page-width" in styles


def test_chaves_gravadas_averbacao():
    assert ETQ.chave_gravada(ETQ.AVERBACAO_RCPN, "etiqueta_largura_mm") \
        == "etiqueta_averbacao_largura_mm"
    assert ETQ.chave_gravada(ETQ.AVERBACAO_RCPN, "etiqueta_margem_mm") \
        == "etiqueta_averbacao_margem_mm"
