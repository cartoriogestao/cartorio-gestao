"""
O ato das Notas em TEXTO CORRIDO, e o texto editado que o selo não apaga.

Ordem do oficial em 14/10/2026: «arrume os modelos dos atos de notas do
sistema. Verifiquei e a procuracao de hj tem um modelo cheio de espacos no
corpo do texto. Todas procuracoes e escrituras sao em texto corrido, sem
espacos no meio do texto».

DUAS CAUSAS, MEDIDAS NA PROCURAÇÃO 802 (PROC-18, «DETRAN - Modelo Amplos»):
    1. `notas_teor.montar` gravava cinco parágrafos — a abertura, um por
       parte, os poderes e o fecho — e colava o modelo do E-Ofício cru, com os
       espaços duplos dele; e não escrevia a nomeação do procurador. O
       precedente (209 procurações e 41 escrituras do E-Ofício) é um parágrafo
       só, do «SAIBAM» ao fecho.
    2. `atualizar_teor_para_data_de_selo` remontava o teor a partir do modelo
       na hora do selo, DEPOIS do lançamento: as 6.010 letras editadas da 802
       viraram as 2.976 do modelo cru, com «XXXXXXXXXXXXXXXXXXX» no lugar do
       veículo. Era isso que saía no termo do livro.

Os nomes, o CPF e a cidade dos testes são os fictícios da casa.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import notas_teor as NT  # noqa: E402

CPF = "000.000.001-91"


def _parte(nome, qualificacao, **mais):
    p = {"nome": nome, "qualificacao": qualificacao, "documento": CPF,
         "nacionalidade": "brasileira", "estado_civil": "solteira",
         "profissao": "lavradora", "endereco": "Rua Grande, 10, Cidade Exemplo/MA",
         "tipo_pessoa": "F", "testemunha": 0}
    p.update(mais)
    return p


# O começo do modelo PROC-18 como ele está no banco: espaço duplo dentro e a
# fileira de X onde vai o veículo.
PODERES_DO_EOFICIO = ("<p>à quem confere amplos poderes para vender o veículo : "
                      "XXXXXXXXXXXXXXXXXXX, perante DETRAN, CIRETRAN,  STRANS, "
                      "enfim  praticar os demais atos.</p>")


def _corpo(teor: str) -> str:
    return teor.split(NT.MARCA_ASSINATURAS)[0]


def _montar(partes, poderes=PODERES_DO_EOFICIO, tipo="PROCURACAO"):
    return NT.montar(tipo, partes, poderes, data_extenso="14 de outubro de 2026",
                     cidade="Cidade Exemplo", uf="MA",
                     lavrado_nome="CARLA EXEMPLO", lavrado_titulo="Escrevente")


# ------------------------------------------------------------ texto corrido

def test_a_procuracao_sai_num_paragrafo_so_e_sem_espaco_duplo():
    teor = _montar([_parte("MARIO EXEMPLO", "OUTORGANTE"),
                    _parte("BEATRIZ EXEMPLO", "PROCURADOR")])
    corpo = _corpo(teor)
    assert len(re.findall(r"<p[\s>]", corpo)) == 1
    plano = re.sub(r"<[^>]+>", "", corpo)
    assert not re.search(r"\S {2,}\S", plano)
    assert "veículo :" not in plano and "veículo:" in plano
    assert plano.startswith("SAIBAM") and plano.rstrip().endswith("assina.")


def test_a_procuracao_nomeia_o_procurador_como_o_precedente():
    plano = re.sub(r"<[^>]+>", "", _corpo(_montar(
        [_parte("MARIO EXEMPLO", "OUTORGANTE"), _parte("BEATRIZ EXEMPLO", "PROCURADOR")])))
    assert "compareceu como OUTORGANTE: MARIO EXEMPLO" in plano
    assert ("me foi dito que nomeia e constitui seu(sua) bastante PROCURADOR(A): "
            "BEATRIZ EXEMPLO") in plano
    # o modelo continua a frase do procurador, e não abre frase solta
    assert re.search(r"Cidade Exemplo/MA, à quem confere amplos poderes", plano)
    assert "na qualidade de" not in plano


def test_varios_outorgantes_e_procuradores_vao_no_plural():
    plano = re.sub(r"<[^>]+>", "", _corpo(_montar([
        _parte("MARIO EXEMPLO", "OUTORGANTE"), _parte("CARLA EXEMPLO", "OUTORGANTE"),
        _parte("BEATRIZ EXEMPLO", "OUTORGADO"), _parte("JOSE EXEMPLO", "PROCURADOR")])))
    assert "compareceram como OUTORGANTES: MARIO EXEMPLO" in plano
    assert "; e CARLA EXEMPLO" in plano
    assert "nomeiam e constituem seus bastantes PROCURADORES: BEATRIZ EXEMPLO" in plano


def test_papel_que_nao_e_o_obvio_continua_escrito():
    plano = re.sub(r"<[^>]+>", "", _corpo(_montar([
        _parte("MARIO EXEMPLO", "OUTORGANTE"), _parte("CARLA EXEMPLO", "ANUENTE"),
        _parte("BEATRIZ EXEMPLO", "PROCURADOR")])))
    assert "na qualidade de ANUENTE" in plano


def test_sem_procurador_no_quadro_o_texto_marca_e_a_pendencia_aparece():
    teor = _montar([_parte("MARIO EXEMPLO", "OUTORGANTE")])
    assert "[PROCURADOR — INCLUA O OUTORGADO NO QUADRO PARTES]" in teor
    from ri_modelos_atos import pendencias
    assert any("PROCURADOR" in m for m in pendencias(teor))


def test_modelo_com_varios_paragrafos_e_quebras_vira_uma_linha():
    teor = _montar([_parte("MARIO EXEMPLO", "OUTORGANTE"),
                    _parte("BEATRIZ EXEMPLO", "PROCURADOR")],
                   poderes="<p>a quem confere poderes</p>\n<p>para vender<br/>e  receber</p>")
    corpo = _corpo(teor)
    assert len(re.findall(r"<p[\s>]", corpo)) == 1
    assert "<br" not in corpo
    assert "a quem confere poderes para vender e receber." in corpo


def test_a_escritura_sai_corrida_e_o_fecho_diz_quem_assina():
    teor = _montar([_parte("MARIO EXEMPLO", "VENDEDOR"),
                    _parte("BEATRIZ EXEMPLO", "COMPRADOR")],
                   poderes="<p>objeto   do ato.</p><p>segunda cláusula.</p>",
                   tipo="ESCRITURA")
    corpo = _corpo(teor)
    plano = re.sub(r"<[^>]+>", "", corpo)
    assert len(re.findall(r"<p[\s>]", corpo)) == 1
    assert "como VENDEDOR, MARIO EXEMPLO" in plano and "; e como COMPRADOR, BEATRIZ" in plano
    assert "objeto do ato. segunda cláusula." in plano
    assert "Assinam o ato MARIO EXEMPLO, VENDEDOR; BEATRIZ EXEMPLO, COMPRADOR." in plano
    assert "[ASSINANTES" not in plano


def test_as_linhas_de_assinatura_continuam_proprias():
    teor = _montar([_parte("MARIO EXEMPLO", "OUTORGANTE"),
                    _parte("BEATRIZ EXEMPLO", "PROCURADOR")])
    assert NT.MARCA_ASSINATURAS in teor
    assert teor.split(NT.MARCA_ASSINATURAS)[1].count("_________________") == 3


# ------------------------------------------------------------ o claro de X

def test_a_fileira_de_x_do_modelo_e_campo_em_branco():
    assert NT.claros_de_x(PODERES_DO_EOFICIO) == ["XXXXXXXXXXXXXXXXXXX"]
    assert NT.claros_de_x("<p>Livro XXX, folha XX</p>") == []
    assert NT.claros_de_x("<p>placa NMU3765</p>") == []


# ------------------------------------------------------------ a data do selo

@pytest.fixture
def con():
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE nt_atos (id INTEGER PRIMARY KEY, tipo TEXT, data TEXT, hora TEXT,
            teor TEXT, teor_formato TEXT, modelo_codigo TEXT, modelo_valores TEXT,
            lavrado_nome TEXT, lavrado_titulo TEXT);
        CREATE TABLE nt_modelos (codigo TEXT PRIMARY KEY, corpo TEXT, origem TEXT,
            ativo INTEGER);
        CREATE TABLE nt_ato_partes (id INTEGER PRIMARY KEY, ato_id INTEGER, nome TEXT,
            documento TEXT, testemunha INTEGER, ordem INTEGER, qualificacao TEXT,
            tipo_pessoa TEXT, nacionalidade TEXT, estado_civil TEXT, profissao TEXT,
            endereco TEXT);
        INSERT INTO nt_modelos VALUES ('PROC-18', '<p>a quem confere XXXXXXXX</p>',
                                       'EOFICIO', 1);
        INSERT INTO nt_modelos VALUES ('NT-PROC', '<p>Aos [DIA POR EXTENSO] ([DIA EM ALGARISMOS]) dias</p>',
                                       'SISTEMA', 1);
    """)
    yield c
    c.close()


def _selar(con, ato_id, quando):
    return NT.atualizar_teor_para_data_de_selo(
        con, ato_id, quando=quando, sv={"ri_cidade": "Cidade Exemplo", "ri_uf": "MA"},
        lavrado_nome="CARLA EXEMPLO", lavrado_titulo="Escrevente")


EDITADO = ("<p>SAIBAM quantos este público instrumento virem que, aos 14 de outubro "
           "de 2026, compareceu MARIO EXEMPLO, que nomeia BEATRIZ EXEMPLO, a quem "
           "confere poderes para vender o veículo HONDA, placa ABC1D23.</p>")


def test_o_selo_no_mesmo_dia_nao_mexe_no_texto_editado(con):
    """O caso da 802: modelo do E-Ofício, texto editado, selo no mesmo dia."""
    con.execute("INSERT INTO nt_atos (id, tipo, data, hora, teor, modelo_codigo) "
                "VALUES (1, 'PROCURACAO', '2026-10-14', '08:54', ?, 'PROC-18')", (EDITADO,))
    con.execute("INSERT INTO nt_ato_partes (ato_id, nome, testemunha, ordem, "
                "qualificacao, tipo_pessoa) VALUES (1, 'MARIO EXEMPLO', 0, 1, "
                "'OUTORGANTE', 'F')")
    r = _selar(con, 1, datetime(2026, 10, 14, 12, 1))
    teor = con.execute("SELECT teor FROM nt_atos WHERE id=1").fetchone()[0]
    assert teor == EDITADO
    assert "XXXX" not in teor
    assert r["alterou_teor"] is False and not r["aviso"]


def test_o_selo_em_outro_dia_troca_so_a_data(con):
    con.execute("INSERT INTO nt_atos (id, tipo, data, hora, teor, modelo_codigo) "
                "VALUES (2, 'PROCURACAO', '2026-10-14', '08:54', ?, 'PROC-18')", (EDITADO,))
    r = _selar(con, 2, datetime(2026, 10, 16, 9, 0))
    linha = con.execute("SELECT data, teor FROM nt_atos WHERE id=2").fetchone()
    assert linha["data"] == "2026-10-16"
    assert linha["teor"] == EDITADO.replace("14 de outubro de 2026", "16 de outubro de 2026")
    assert r["alterou_teor"] is True


def test_data_escrita_a_mao_nao_se_reescreve_e_a_tela_avisa(con):
    livre = ("<p>SAIBAM que, aos quatorze dias do mês de outubro do ano de dois mil "
             "e vinte e seis (14/10/2026), compareceu MARIO EXEMPLO.</p>")
    con.execute("INSERT INTO nt_atos (id, tipo, data, hora, teor, modelo_codigo) "
                "VALUES (3, 'PROCURACAO', '2026-10-14', '08:54', ?, 'PROC-18')", (livre,))
    r = _selar(con, 3, datetime(2026, 10, 16, 9, 0))
    linha = con.execute("SELECT data, teor FROM nt_atos WHERE id=3").fetchone()
    assert linha["teor"] == livre
    assert linha["data"] == "2026-10-16"
    assert r["aviso"] and "NÃO foi mexido" in r["aviso"]


def test_modelo_do_sistema_troca_a_frase_da_data_e_guarda_os_valores(con):
    valores = {"dia_por_extenso": "quatorze", "dia_em_algarismos": "14",
               "mes_por_extenso": "outubro", "ano_por_extenso": "dois mil e vinte e seis",
               "ano_em_algarismos": "2026", "outro_campo": "fica"}
    teor = ("<p>Aos quatorze (14) dias do mês de outubro do ano de dois mil e vinte "
            "e seis (2026), e o escrevente acrescentou esta frase à mão.</p>")
    con.execute("INSERT INTO nt_atos (id, tipo, data, hora, teor, modelo_codigo, "
                "modelo_valores) VALUES (4, 'PROCURACAO', '2026-10-14', '08:54', ?, "
                "'NT-PROC', ?)", (teor, json.dumps(valores)))
    _selar(con, 4, datetime(2026, 10, 16, 9, 0))
    linha = con.execute("SELECT teor, modelo_valores FROM nt_atos WHERE id=4").fetchone()
    assert "dezesseis (16) dias do mês de outubro" in linha["teor"]
    assert "acrescentou esta frase à mão" in linha["teor"]
    gravados = json.loads(linha["modelo_valores"])
    assert gravados["dia_em_algarismos"] == "16" and gravados["outro_campo"] == "fica"
