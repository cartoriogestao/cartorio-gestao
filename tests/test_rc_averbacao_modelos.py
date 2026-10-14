# -*- coding: utf-8 -*-
"""HOTFIX-2026-10-09-04 - modelo 'Retificacao - erro na data do registro'."""
import sqlite3
import pytest
import rc_averbacao_modelos as RAM


def _banco():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE rc_assentos(id INTEGER PRIMARY KEY, serie TEXT, especie TEXT, numero INT,"
                " livro_volume TEXT, data_ato TEXT, data_fato TEXT, situacao TEXT, dados_json TEXT, nome TEXT)")
    con.execute("CREATE TABLE rc_atos(id INTEGER PRIMARY KEY, assento_id INT, tipo TEXT)")
    # A cidade do texto vem de `settings` desde 09/10/2026 (sanitização).
    con.execute("CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT)")
    con.executemany("INSERT INTO settings VALUES (?, ?)",
                    (("ri_cidade", "Cidade Exemplo"), ("ri_uf", "MA")))
    for n, d in ((13703, "2001-04-09"), (13705, "2001-04-09"), (13708, "2001-04-20")):
        con.execute("INSERT INTO rc_assentos(serie,especie,numero,livro_volume,data_ato,situacao)"
                    " VALUES('RC_A','NASCIMENTO',?,'A-14',?,'ATIVO')", (n, d))
    con.execute("INSERT INTO rc_assentos(id,serie,especie,numero,livro_volume,data_ato,data_fato,situacao,dados_json,nome)"
                " VALUES(99,'RC_A','NASCIMENTO',13706,'A-14','2001-04-18','2001-03-17','ATIVO',"
                "'{\"data_registro_teor\": \"dezoito de abril de dois mil\"}','NAIR DA SILVA GARCEZ')")
    return con


def test_sugestoes_e_texto_amanda():
    con = _banco()
    a = dict(con.execute("SELECT * FROM rc_assentos WHERE id=99").fetchone())
    v = RAM.sugestoes(con, "retificacao-data-registro", a, {"nome": "Debora", "funcao": "Escrevente Autorizada"})
    assert v["numero_av"] == "01/13.706"
    assert v["data_como_consta"] == "dezoito de abril de dois mil"
    assert v["data_correta"] == "2001-04-18"
    assert "termo 13.705, de 09/04/2001" in v["elementos_prova"]
    assert "termo 13.708, de 20/04/2001" in v["elementos_prova"]
    v["data_averbacao"] = "2026-10-09"
    r = RAM.montar("retificacao-data-registro", v, a)
    assert r["teor"].startswith("AVERBAÇÃO 01/13.706 – RETIFICAÇÃO: Em 9 de Outubro de 2026, de ofício")
    assert "“dezoito de abril de dois mil” ao invés de 18 de Abril de 2001 (18/04/2001)" in r["teor"]
    assert "Artigo 110, §§1º e 3º, da Lei 6.015/1973" in r["teor"]
    assert r["teor"].endswith("Cidade Exemplo/MA, 09/10/2026. Eu, Debora, Escrevente Autorizada, o subscrevi.")
    assert "selo" not in r["teor"].lower()
    assert r["natureza"] == "retificacao"


def test_campos_obrigatorios_e_parte():
    con = _banco()
    a = dict(con.execute("SELECT * FROM rc_assentos WHERE id=99").fetchone())
    v = RAM.sugestoes(con, "retificacao-data-registro", a, {})
    with pytest.raises(RAM.ModeloErro):
        RAM.montar("retificacao-data-registro", v, a)  # sem subscritor
    v.update(subscritor_nome="Fulana", requerente_tipo="parte")
    with pytest.raises(RAM.ModeloErro):
        RAM.montar("retificacao-data-registro", v, a)  # parte sem nome
    v["requerente_nome"] = "NAIR DA SILVA GARCEZ"
    r = RAM.montar("retificacao-data-registro", v, a)
    assert "após requerimento feito pela parte interessada, NAIR DA SILVA GARCEZ" in r["teor"]


def test_listar_por_especie():
    assert RAM.listar("NASCIMENTO")[0]["slug"] == "retificacao-data-registro"
    assert RAM.listar("PROCLAMAS") == []
