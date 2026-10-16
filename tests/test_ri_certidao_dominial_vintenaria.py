# -*- coding: utf-8 -*-
"""Certidão dominial / vintenária — mapas e filtro de atos."""
from __future__ import annotations

import ato_selado as AS
import ri_dominial as RIDOM
import ri_odt as ODT
from ri_schema import TIPOS_CERTIDAO


def test_tipos_miolo_e_selo_alinhados():
    assert set(TIPOS_CERTIDAO) == set(ODT.MIOLO_DA_CERTIDAO)
    assert set(TIPOS_CERTIDAO) == set(AS.CODIGO_DA_CERTIDAO_DO_RI)
    assert "DOMINIAL" in TIPOS_CERTIDAO
    assert "VINTENARIA" in TIPOS_CERTIDAO
    assert AS.CODIGO_DA_CERTIDAO_DO_RI["DOMINIAL"] == "16.24.4"
    assert AS.CODIGO_DA_CERTIDAO_DO_RI["VINTENARIA"] == "16.24.4"
    assert ODT.MIOLO_DA_CERTIDAO["DOMINIAL"] == "RI_CERTIDAO_DOMINIAL"
    assert ODT.MIOLO_DA_CERTIDAO["VINTENARIA"] == "RI_CERTIDAO_VINTENARIA"


def test_cadeia_dominial_por_natureza():
    atos = [
        {"tipo": "R", "numero": 1, "natureza_titulo": "Compra e Venda",
         "teor": "R-1/1 - COMPRA E VENDA. Fulano...", "data_ato": "2010-01-10",
         "cancelado": 0},
        {"tipo": "R", "numero": 2, "natureza_titulo": "Hipoteca",
         "teor": "R-2/1 - HIPOTECA...", "data_ato": "2015-03-01",
         "cancelado": 0},
        {"tipo": "R", "numero": 3, "natureza_titulo": "Doação",
         "teor": "R-3/1 - DOAÇÃO...", "data_ato": "2020-05-05",
         "cancelado": 0},
    ]
    cadeia = RIDOM.cadeia_dominial(atos, rotulo=lambda a: f"R-{a['numero']}")
    assert [a["numero"] for a in cadeia] == [1, 3]
    assert all(not a["conferir"] for a in cadeia)


def test_vintenaria_janela_e_onus():
    from datetime import date
    hoje = date(2026, 9, 28)
    atos = [
        {"tipo": "R", "numero": 1, "natureza_titulo": "Compra e Venda",
         "teor": "x", "data_ato": "2000-01-01", "cancelado": 0},
        {"tipo": "R", "numero": 2, "natureza_titulo": "Compra e Venda",
         "teor": "x", "data_ato": "2018-06-01", "cancelado": 0},
        {"tipo": "R", "numero": 3, "natureza_titulo": "Hipoteca",
         "teor": "R-3 - HIPOTECA", "data_ato": "2019-01-01", "cancelado": 0},
    ]
    pack = RIDOM.conteudo_vintenaria(atos, anos=20, rotulo=lambda a: f"R-{a['numero']}", hoje=hoje)
    assert pack["anos"] == 20
    assert [a["numero"] for a in pack["dominio"]] == [2]
    assert [a["numero"] for a in pack["onus"]] == [3]


def test_itens_selo_dominial():
    itens = AS.itens_da_certidao_do_ri("DOMINIAL", folhas=1)
    assert itens == [("16.24.4", 1)]
    itens2 = AS.itens_da_certidao_do_ri("VINTENARIA", folhas=3)
    assert itens2 == [("16.24.4", 1), ("16.24.4.1", 2)]


def test_extrai_numeros_registro_anterior():
    texto = ("Desmembrada da Matricula nº 3307, LIVRO: 2-R; "
             "unificação Matrícula 2558 e Matriculas 2557")
    nums = RIDOM.extrair_numeros_registro_anterior(texto)
    assert "3307" in nums
    assert "2558" in nums
    assert "2557" in nums
    # 2.765 -> 2765
    assert RIDOM.extrair_numeros_registro_anterior("MATRICULA 2.765, Livro 2-P") == ["2765"]
    assert RIDOM.normalizar_numero_matricula("0293") == "293"
    assert RIDOM.sugerir_numeros_origem(
        "MATRICULA 3236 DO LIVRO 2-R", numero_atual="3359") == ["3236"]
    # nao sugere a propria
    assert RIDOM.sugerir_numeros_origem(
        "Matrícula 3359", numero_atual="3359") == []


def test_parsear_numeros_digitados():
    assert RIDOM.parsear_numeros_digitados("2040, 1.990 e 3020") == ["2040", "1990", "3020"]


# ---------------------------------------------------------------------------
# PELA TELA — 14/10/2026. Os testes de cima guardam os mapas e a régua; estes
# guardam o que se PERDEU em 28/09: a ficha oferecer os dois tipos, a emissão
# montar a cadeia com as matrículas de origem (só as que existem) e a
# vintenária respeitar os anos. Sem eles a régua continuaria verde com a
# funcionalidade fora do ar — que é exatamente o que aconteceu.
# ---------------------------------------------------------------------------
import re
import sqlite3

import pytest


@pytest.fixture(autouse=True)
def _folhas_sem_chrome(monkeypatch):
    """A CONTAGEM DE FOLHAS ABRE O CHROME, e aqui ela não é o que se mede.

    Medido em 14/10/2026 com `faulthandler`: a emissão parou 5 minutos em
    `impressao_pdf.pdf_de_html_chrome` (o `communicate` de um Chrome que não
    devolveu os canos), com a máquina carregada por outras suítes. Estes
    testes medem a CADEIA, e não a contagem de folhas — que, aliás, não tem
    teste próprio nesta árvore (procurado em 14/10/2026).
    """
    import certidao_folhas
    monkeypatch.setattr(certidao_folhas, "folhas_do_html_como_certidao",
                        lambda html, **_: 1)


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _abrir(casa, numero, *, registro_anterior=None, atos=()):
    con = _con(casa)
    with con:
        mid = int(con.execute(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
                   tipo_ficha, origem, criado_em, data_abertura, cidade, uf,
                   teor, teor_formato, registro_anterior)
               VALUES (?, '2', '2', 'ATIVA', 'ESTRUTURADA', 'MANUAL',
                       '2026-10-14T09:00', '2001-02-03', 'Cidade Exemplo', 'MA',
                       '<p>IMÓVEL: FAZENDA EXEMPLO, gleba rural.</p>', 'html', ?)""",
            (numero, registro_anterior)).lastrowid)
        for i, (tipo, natureza, data, teor) in enumerate(atos, start=1):
            con.execute(
                """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato,
                       natureza_titulo, teor, teor_formato, hash_ato, lavrado_em)
                   VALUES (?, ?, ?, ?, ?, ?, 'texto', ?, '2026-10-14T09:00')""",
                (mid, tipo, i, data, natureza, teor, f"h{numero}-{i}"))
    con.close()
    return mid


def _token(html):
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _emitir(casa, mid, tipo, **extra):
    tela = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    resposta = casa["c"].post(f"/registro-imoveis/{mid}/certidao", data={
        "csrf_token": _token(tela), "tipo": tipo, "fonte_corpo": "TEXTO",
        "requerente": "FULANO DE TAL", **extra}, follow_redirects=True)
    con = _con(casa)
    linha = con.execute(
        "SELECT * FROM ri_certidoes ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    assert linha and linha["tipo"] == tipo, f"a certidão {tipo} não foi emitida"
    return str(linha["corpo"]), resposta.get_data(as_text=True)


def test_a_ficha_oferece_os_dois_tipos_e_os_campos_deles(cg_casa_logada):
    casa = cg_casa_logada
    mid = _abrir(casa, "4101", registro_anterior="Matrícula nº 4100, Livro 2")
    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    formulario = re.search(r'action="[^"]*/certidao".*?</form>', html, re.DOTALL)
    assert formulario, "a ficha não tem o formulário de emitir certidão"
    trecho = formulario.group(0)
    assert 'value="DOMINIAL"' in trecho and 'value="VINTENARIA"' in trecho
    assert 'name="anos"' in trecho, "sumiu o campo dos anos da vintenária"
    assert 'name="origens"' in trecho, "sumiu o campo das matrículas de origem"
    # A sugestão vem do registro anterior desta ficha, e só sugere.
    assert "4100" in trecho


def test_dominial_monta_a_cadeia_com_a_origem_digitada(cg_casa_logada):
    """A forma da 394/2026: o bloco da matrícula atual e um por origem — e o
    número que não existe NÃO vira bloco: volta como aviso."""
    casa = cg_casa_logada
    _abrir(casa, "4100", atos=[
        ("R", "Compra e Venda", "2005-05-05",
         "R-1/4100 - COMPRA E VENDA. Fulano vendeu a Beltrano.")])
    mid = _abrir(casa, "4101", atos=[
        ("R", "Hipoteca", "2015-03-01", "R-1/4101 - HIPOTECA. Ao banco."),
        ("R", "Doação", "2020-06-06", "R-2/4101 - DOAÇÃO. Beltrano doou.")])
    corpo, tela = _emitir(casa, mid, "DOMINIAL", origens="4100, 9898")

    assert "CADEIA DOMINIAL" in corpo
    assert "Matrícula N.º 4101 (atual)" in corpo
    assert "Matrícula N.º 4100 (origem)" in corpo
    assert "9898" not in corpo, "matrícula que não existe entrou no papel"
    assert "R-02/4101" in corpo or "R-2/4101" in corpo, "a doação sumiu da cadeia"
    assert "HIPOTECA" not in corpo.split("CADEIA DOMINIAL", 1)[1], (
        "hipoteca não transmite domínio e entrou na cadeia")
    assert "Compra e Venda" in corpo
    assert "9898" in tela, "a tela não avisou da origem que não entrou"


def test_dominial_em_branco_segue_o_registro_anterior(cg_casa_logada):
    casa = cg_casa_logada
    _abrir(casa, "4200", registro_anterior="Transcrito no CRI de Imperatriz")
    _abrir(casa, "4201", registro_anterior="Matrícula 4200, Livro 2")
    mid = _abrir(casa, "4202", registro_anterior="Matrícula nº 4.201")
    corpo, _ = _emitir(casa, mid, "DOMINIAL")
    assert "Matrícula N.º 4201 (origem)" in corpo
    assert "Matrícula N.º 4200 (origem)" in corpo
    assert corpo.index("4201 (origem)") < corpo.index("4200 (origem)")


def test_dominial_sem_origem_nao_imprime_cabecalho_de_bloco(cg_casa_logada):
    casa = cg_casa_logada
    mid = _abrir(casa, "4300")
    corpo, _ = _emitir(casa, mid, "DOMINIAL")
    assert "CADEIA DOMINIAL" in corpo
    assert "(atual)" not in corpo
    assert "NADA CONSTA" in corpo


def test_vintenaria_respeita_os_anos_escolhidos(cg_casa_logada):
    casa = cg_casa_logada
    mid = _abrir(casa, "4400", atos=[
        ("R", "Compra e Venda", "1999-01-01", "R-1/4400 - COMPRA E VENDA."),
        ("R", "Compra e Venda", "2024-01-01", "R-2/4400 - COMPRA E VENDA.")])
    corpo, _ = _emitir(casa, mid, "VINTENARIA", anos="10")
    assert "ÚLTIMOS 10 ANOS" in corpo
    assert "(10 ANOS)" in corpo.upper(), "o título não diz os anos"
    assert "R-02/4400" in corpo or "R-2/4400" in corpo
    assert "R-01/4400" not in corpo and "R-1/4400 " not in corpo, (
        "ato de fora da janela entrou na vintenária")
    # A data do período vai na forma do papel, e não crua do banco.
    assert not re.search(r"de \d{4}-\d{2}-\d{2} a", corpo)
