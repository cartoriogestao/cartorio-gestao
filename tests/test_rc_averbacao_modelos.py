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
    # Título e aspas mudaram por decisão do oficial em 15/10/2026 (relato #127):
    # era «– RETIFICAÇÃO: Em …» e a data correta saía sem aspas.
    assert r["teor"].startswith("AVERBAÇÃO 01/13.706 – RETIFICAÇÃO DA DATA DO REGISTRO: "
                                "Em 9 de Outubro de 2026, de ofício")
    assert "“dezoito de abril de dois mil” ao invés de “18 de Abril de 2001 (18/04/2001)”" in r["teor"]
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


# ---------------------------------------------------------------------------
# Relato #127 (15/10/2026): modelo genérico de erro material (art. 110) e o
# modelo da data virando um caso pronto dele. Até a decisão do oficial de
# 15/10/2026 o texto era letra por letra o de 09/10; ela mudou exatamente duas
# coisas, e só elas: o título («– RETIFICAÇÃO:» passou a «– RETIFICAÇÃO DA DATA
# DO REGISTRO:») e a data correta, que passou a ir entre aspas.
# ---------------------------------------------------------------------------
TEXTO_DA_DATA_DEPOIS_DO_127 = (
    "AVERBAÇÃO 01/13.706 – RETIFICAÇÃO DA DATA DO REGISTRO: Em 9 de Outubro de 2026, de "
    "ofício, por se tratar "
    "de erro que não exige qualquer indagação para a constatação imediata de necessidade de "
    "sua correção, venho retificar A DATA DO REGISTRO deste assento, que na época do registro "
    "foi grafada erroneamente como sendo “dezoito de abril de dois mil” ao invés de “18 de "
    "Abril de 2001 (18/04/2001)”, conforme a sequência dos termos vizinhos (termo 13.703, de "
    "09/04/2001; termo 13.705, de 09/04/2001; termo 13.708, de 20/04/2001) e a data de "
    "nascimento do registrando, 17/03/2001, constante do próprio assento; diante disto faço "
    "constar a data correta do registro, dando cumprimento ao Artigo 110, §§1º e 3º, da Lei "
    "6.015/1973, retificando o assento. O referido é verdade e dou fé. Cidade Exemplo/MA, "
    "09/10/2026. Eu, Mario, Escrevente Autorizado, o subscrevi.")


def _assento():
    con = _banco()
    return con, dict(con.execute("SELECT * FROM rc_assentos WHERE id=99").fetchone())


def test_modelo_da_data_sai_letra_por_letra_como_decidido():
    # O texto da averbação 431 com só as duas mudanças que o oficial decidiu.
    con, a = _assento()
    v = RAM.sugestoes(con, "retificacao-data-registro", a,
                      {"nome": "Mario", "funcao": "Escrevente Autorizado"})
    v["data_averbacao"] = "2026-10-09"
    r = RAM.montar("retificacao-data-registro", v, a)
    assert r["teor"] == TEXTO_DA_DATA_DEPOIS_DO_127
    assert r["fundamento"] == ("Art. 110 da Lei 6.015/1973 - erro na data do registro "
                               "(de “dezoito de abril de dois mil” para 18/04/2001)")


def _generico(con, a, correcoes, **extra):
    v = RAM.sugestoes(con, "retificacao-erro-material", a,
                      {"nome": "Mario Exemplo", "funcao": "Escrevente Autorizado"})
    v.update(data_averbacao="2026-10-15", correcoes=correcoes, **extra)
    return RAM.montar("retificacao-erro-material", v, a)


def test_generico_com_uma_correcao():
    con, a = _assento()
    r = _generico(con, a, [{"campo": "o nome da genitora", "errado": "MARIA DE SOUSA",
                            "correto": "MARIA DE SOUZA"}],
                  documentos="certidão de nascimento da genitora, cuja cópia fica "
                             "arquivada nesta serventia.")
    assert r["teor"] == (
        "AVERBAÇÃO 01/13.706 – RETIFICAÇÃO DO NOME DA GENITORA: Em 15 de Outubro de 2026, de "
        "ofício, por se "
        "tratar de erro que não exige qualquer indagação para a constatação imediata de "
        "necessidade de sua correção, venho retificar O NOME DA GENITORA deste assento, que "
        "na época do registro foi grafado erroneamente como sendo “MARIA DE SOUSA” ao invés "
        "de “MARIA DE SOUZA”, conforme certidão de nascimento da genitora, cuja cópia fica "
        "arquivada nesta serventia; diante disto faço constar a redação correta, dando "
        "cumprimento ao Artigo 110, §§1º e 3º, da Lei 6.015/1973, retificando o assento. O "
        "referido é verdade e dou fé. Cidade Exemplo/MA, 15/10/2026. Eu, Mario Exemplo, "
        "Escrevente Autorizado, o subscrevi.")
    assert r["natureza"] == "retificacao"
    assert r["fundamento"] == ("Art. 110 da Lei 6.015/1973 - erro material: O NOME DA "
                               "GENITORA (de “MARIA DE SOUSA” para “MARIA DE SOUZA”)")


def test_generico_com_duas_correcoes_a_requerimento():
    con, a = _assento()
    r = _generico(con, a, [
        {"campo": "A NATURALIDADE", "errado": "“VILA FICTICIA/MA”", "correto": "CIDADE EXEMPLO/MA"},
        {"campo": "os nomes dos avós paternos", "errado": "JOSÉ DA SILVA e ANA DA SILVA",
         "correto": "JOSÉ DA SYLVA e ANA DA SYLVA"},
        {"campo": "", "errado": "", "correto": ""},   # linha vazia da tela: ignorada
    ], requerente_tipo="parte", requerente_nome="CARLA EXEMPLO",
        data_requerimento="2026-10-10")
    t = r["teor"]
    assert t.startswith("AVERBAÇÃO 01/13.706 – RETIFICAÇÃO DA NATURALIDADE E DOS NOMES DOS "
                        "AVÓS PATERNOS: Em 15 de Outubro de 2026, após "
                        "requerimento feito pela parte interessada, CARLA EXEMPLO, em "
                        "10/10/2026, venho retificar os seguintes elementos deste assento, "
                        "que na época do registro constaram com erro: ")
    assert ("A NATURALIDADE, grafada erroneamente como sendo “VILA FICTICIA/MA” ao invés de "
            "“CIDADE EXEMPLO/MA”; e OS NOMES DOS AVÓS PATERNOS, grafados erroneamente como sendo "
            "“JOSÉ DA SILVA e ANA DA SILVA” ao invés de “JOSÉ DA SYLVA e ANA DA SYLVA”; diante "
            "disto faço constar a redação correta, dando cumprimento ao Artigo 110") in t
    assert "conforme" not in t          # sem documento, a frase não aparece
    assert "“VILA FICTICIA" in t and "““" not in t   # aspas digitadas não dobram
    assert t.count(" A NATURALIDADE") == 1 and "; e OS NOMES" in t
    assert "erro material: A NATURALIDADE (de “VILA FICTICIA/MA” para “CIDADE EXEMPLO/MA”); " \
           "OS NOMES DOS AVÓS PATERNOS" in r["fundamento"]


def test_generico_sem_artigo_nao_adivinha_o_genero():
    con, a = _assento()
    r = _generico(con, a, [{"campo": "sobrenome do registrado", "errado": "MENESES",
                            "correto": "MENEZES"}])
    assert ("venho retificar SOBRENOME DO REGISTRADO deste assento, que na época do registro "
            "constou erroneamente como “MENESES” ao invés de “MENEZES”;") in r["teor"]
    # sem artigo, o título usa «DE» em vez de adivinhar «DO»/«DA»
    assert "– RETIFICAÇÃO DE SOBRENOME DO REGISTRADO: Em " in r["teor"]


def test_titulo_junta_tres_elementos_e_fundamento_nao_corta_cedo():
    con, a = _assento()
    longo = "X" * 200
    r = _generico(con, a, [
        {"campo": "O NOME DO REGISTRADO", "errado": "JOAO " + longo, "correto": "JOÃO " + longo},
        {"campo": "A DATA DE NASCIMENTO", "errado": "01/01/2000", "correto": "02/01/2000"},
        {"campo": "OS NOMES DOS AVÓS MATERNOS", "errado": "A " + longo, "correto": "B " + longo},
    ])
    assert ("– RETIFICAÇÃO DO NOME DO REGISTRADO, DA DATA DE NASCIMENTO E DOS NOMES DOS AVÓS "
            "MATERNOS: Em ") in r["teor"]
    # O corte de 300 caracteres saiu (decisão do oficial, 15/10/2026); o limite é 2.000.
    assert len(r["fundamento"]) > 800 and not r["fundamento"].endswith("…")
    assert r["fundamento"].endswith("para “B " + longo + "”)")
    enorme = [{"campo": f"O ELEMENTO {i}", "errado": "Y" * 400, "correto": "Z" * 400}
              for i in range(1, 6)]
    f = _generico(con, a, enorme)["fundamento"]
    assert len(f) == RAM.LIMITE_DO_FUNDAMENTO == 2000 and f.endswith("…")


def test_generico_recusa_linha_pela_metade_e_falta_de_correcao():
    con, a = _assento()
    with pytest.raises(RAM.ModeloErro, match="correção 2 sem leia-se"):
        _generico(con, a, [{"campo": "O SEXO", "errado": "MASCULINO", "correto": "FEMININO"},
                           {"campo": "A HORA DE NASCIMENTO", "errado": "10:00", "correto": ""}])
    with pytest.raises(RAM.ModeloErro, match="ao menos uma correção"):
        _generico(con, a, [{"campo": "", "errado": "", "correto": ""}])
    with pytest.raises(RAM.ModeloErro, match="Nome do requerente"):
        _generico(con, a, [{"campo": "O SEXO", "errado": "M", "correto": "F"}],
                  requerente_tipo="parte")
    with pytest.raises(RAM.ModeloErro, match="Data do requerimento"):
        _generico(con, a, [{"campo": "O SEXO", "errado": "M", "correto": "F"}],
                  requerente_tipo="parte", requerente_nome="CARLA EXEMPLO",
                  data_requerimento="31/02/2026")


def test_generico_lista_em_todas_as_especies_e_le_as_linhas_do_formulario():
    # Todas as espécies com assento (decisão do oficial, 15/10/2026); proclamas não.
    for esp in ("NASCIMENTO", "CASAMENTO", "CASAMENTO_RELIGIOSO", "OBITO", "NATIMORTO",
                "AUSENCIA", "INTERDICAO", "TUTELA", "EMANCIPACAO", "UNIAO_ESTAVEL",
                "OPCAO_NACIONALIDADE", "OUTRO"):
        assert "retificacao-erro-material" in [m["slug"] for m in RAM.listar(esp)]
    assert "retificacao-erro-material" not in [m["slug"] for m in RAM.listar("PROCLAMAS")]
    # o modelo da data continua só nas três de antes
    assert "retificacao-data-registro" not in [m["slug"] for m in RAM.listar("NATIMORTO")]
    form = {"numero_av": "01/1", "correcao_campo_1": " A DATA DE NASCIMENTO ",
            "correcao_errado_1": "01/01/2000", "correcao_correto_1": "02/01/2000",
            "correcao_campo_3": "O SEXO"}
    v = RAM.valores_do_formulario("retificacao-erro-material", form)
    assert len(v["correcoes"]) == RAM.LINHAS_DE_CORRECAO
    assert v["correcoes"][0] == {"campo": "A DATA DE NASCIMENTO", "errado": "01/01/2000",
                                 "correto": "02/01/2000"}
    assert v["correcoes"][2]["campo"] == "O SEXO" and v["numero_av"] == "01/1"
