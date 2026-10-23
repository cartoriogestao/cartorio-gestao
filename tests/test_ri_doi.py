"""A declaração do RI no formato do DOI-Web — `ri_doi`, 22/10/2026.

Cada teste guarda um defeito do arquivo de setembro/2026 que o sistema gerou e
que precisou ser corrigido à mão antes de o DOI-Web aceitar.
"""
from datetime import date

import ri_doi

TEOR_4019 = ("<p>R-01/4019 – TÍTULO DE DOMÍNIO SOB CONDIÇÃO RESOLUTIVA. CONDIÇÕES DE "
             "PAGAMENTO: a prazo, em 17 (dezessete) prestações anuais de R$ 453,34 "
             "(quatrocentos e cinquenta e três reais e trinta e quatro centavos), "
             "vencendo-se a primeira em 22 de agosto de 2020. ATO GRATUITO.</p>")
TEOR_4014 = ("CONDIÇÕES DE PAGAMENTO: pagamento a prazo, em 17 (dezessete) prestações "
             "anuais, sendo a primeira no valor de R$ 425,52 (quatrocentos e vinte e "
             "cinco reais e cinquenta e dois centavos), com vencimento indicado no "
             "título em 22 de agosto de 2020, observadas as demais condições.")
TEOR_DOACAO = ("R-02/4020 – DOAÇÃO. Nos termos da Escritura Pública de Doação de Imóvel "
               "Rural, lavrada no Livro nº 10-N, os DOADORES doaram o imóvel "
               "denominado CHÁCARA PAI E FILHOS - PARCELA 2, situado na zona rural, "
               "com CCIR do INCRA nº 1100430001912.")


def _ato(teor, numero=1, tipo="R", data="2026-09-23"):
    return {"id": 1, "tipo": tipo, "numero": numero, "data_ato": data, "teor": teor,
            "natureza_titulo": ""}


def _matricula(**kw):
    m = {"numero": "4019", "rural_urbano": "RURAL", "area_valor": "20,61",
         "incra": "1021720108551", "logradouro": "Lote nº 46 - P.A. Vale do Jordão",
         "cnm": ""}
    m.update(kw)
    return m


PARTES = [{"id": 1, "papel": "transmitente", "nome": "INCRA",
           "documento_numero": "00.000.001/0000-55", "participacao": "100"},
          {"id": 2, "papel": "adquirente", "nome": "BENEFICIÁRIO",
           "documento_numero": "000.000.001-91", "participacao": "100"}]


def _dados(**kw):
    d = {"operacao": "73", "data_negocio": "2017-08-22", "valor_operacao": "7706,83",
         "valor_base_itbi_nao_consta": "1", "forma_pagamento": "7",
         "folha_ato": "2-2v"}
    d.update(kw)
    return d


def test_parcelas_se_leem_nas_duas_redacoes_dos_titulos_do_incra():
    assert ri_doi.parcelas_do_teor(TEOR_4019) == {
        "quantidade": 17, "valor": 453.34, "primeira": date(2020, 8, 22)}
    assert ri_doi.parcelas_do_teor(TEOR_4014) == {
        "quantidade": 17, "valor": 425.52, "primeira": date(2020, 8, 22)}
    assert ri_doi.parcelas_do_teor(TEOR_DOACAO) is None


def test_o_valor_pago_segue_o_precedente_da_4014_entregue_em_agosto():
    # Controle 3226: 6 × 425,52 = 2.553,12 e última parcela 2036-08-01.
    par = ri_doi.parcelas_do_teor(TEOR_4014)
    assert ri_doi.pagamento_a_prazo(par, "2026-08-18") == {
        "ultima_parcela": "2036-08-01", "valor_pago_ate_ato": 2553.12, "vencidas": 6}
    # A 4019 é de 23/09: a parcela de 22/08/2026 já venceu — são 7.
    par = ri_doi.parcelas_do_teor(TEOR_4019)
    assert ri_doi.pagamento_a_prazo(par, "2026-09-23")["valor_pago_ate_ato"] == 3173.38


def test_a_declaracao_do_ri_e_registro_de_imoveis_e_nao_notarial():
    reg = ri_doi.montar(_ato(TEOR_4019), _matricula(), PARTES, _dados(), "000000", "2198765")
    assert reg["tipoServico"] == "2" and reg["tipoAto"] == "4"
    assert reg["tipoLivro"] == "1" and reg["numeroLivro"] == "2"
    assert reg["numeroRegistroAverbacao"] == "0000001"
    assert reg["naturezaTitulo"] == "4"
    assert reg["folha"] == "2-2v"
    assert reg["existeDoiAnterior"] is False
    assert reg["codigoNacionalMatricula"] == "0000002000401998"
    assert reg["mesAnoUltimaParcela"] == "2036-08-01"
    assert reg["valorPagoAteDataAto"] == 3173.38
    assert "IndicadorNaoConstaValorBaseCalculoItbiItcmd" not in reg
    assert reg["indicadorNaoConstaValorBaseCalculoItbiItcmd"] is True
    assert ri_doi.conferir_layout(reg) == []


def test_pessoa_juridica_nao_leva_conjuge():
    reg = ri_doi.montar(_ato(TEOR_4019), _matricula(), PARTES, _dados(), "000000", "2198765")
    assert "indicadorConjuge" not in reg["alienantes"][0]      # o INCRA, CNPJ
    assert "indicadorConjuge" in reg["adquirentes"][0]         # pessoa física


def test_a_localizacao_nunca_e_o_perimetro():
    m = _matricula(descricao_perimetro="Inicia-se a descrição deste perímetro no vértice X…")
    reg = ri_doi.montar(_ato(TEOR_4019), m, PARTES, _dados(), "000000", "2198765")
    assert reg["localizacao"] == "zona rural"


def test_sem_folha_nem_valor_pago_a_declaracao_nao_entra():
    dados = _dados(folha_ato="")
    p = ri_doi.pendencias(_ato("título a prazo sem as parcelas escritas"), _matricula(), dados)
    assert any("folha" in x for x in p)
    assert any("valor pago" in x for x in p)
    assert any("última parcela" in x for x in p)


def test_frase_da_ficha_nao_vale_como_denominacao():
    m = _matricula(logradouro="situada na zona rural do Município de Cidade Exemplo")
    assert ri_doi.denominacao_sugerida(_ato(TEOR_DOACAO, numero=2), m) == \
        "CHÁCARA PAI E FILHOS - PARCELA 2"
    p = ri_doi.pendencias(_ato("sem nome"), m, _dados(
        denominacao="Município de Cidade Exemplo, Estado do Maranhão."))
    assert any("frase da ficha" in x for x in p)


def test_escritura_de_imovel_rural_que_cita_o_incra_continua_escritura():
    assert ri_doi.natureza_sugerida(_ato(TEOR_DOACAO), "67") == "2"
    assert ri_doi.natureza_sugerida(_ato(TEOR_4019), "73") == "4"


def test_o_layout_recusa_o_que_o_doi_web_recusou():
    reg = ri_doi.montar(_ato(TEOR_4019), _matricula(), PARTES, _dados(), "000000", "2198765")
    reg["mesAnoUltimaParcela"] = "08/2036"
    reg["IndicadorNaoConstaValorBaseCalculoItbiItcmd"] = True
    reg["alienantes"][0]["indicadorConjuge"] = False
    erros = ri_doi.conferir_layout(reg)
    assert any("AAAA-MM-DD" in e for e in erros)
    assert any("IndicadorNaoConsta" in e for e in erros)
    assert any("pessoa jurídica" in e for e in erros)


# ------------------------------------------------- pela tela, de ponta a ponta

import json  # noqa: E402
import re  # noqa: E402
import sqlite3  # noqa: E402

import pytest  # noqa: E402

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    db, c = cg_casa["db"], cg_casa["cliente"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.set_settings({"ri_cns": "000000", "ri_codigo_ibge": "2198765"})
    c.post("/login", data={"username": "mario", "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa


def _titulo_de_dominio(casa) -> int:
    con = sqlite3.connect(casa["banco"])
    with con:
        cur = con.execute(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao, tipo_ficha,
                   cidade, uf, rural_urbano, area_valor, area_unidade, incra, logradouro,
                   descricao_perimetro, criado_em)
               VALUES ('4019', '2', '2', 'ATIVA', 'ESTRUTURADA', 'Cidade Exemplo', 'MA',
                       'RURAL', '20,61', 'ha', '1021720108551',
                       'Município de Cidade Exemplo, Estado do Maranhão.',
                       'Inicia-se a descrição deste perímetro no vértice X', '2026-09-15T09:00')""")
        mid = int(cur.lastrowid)
        cur = con.execute(
            """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, natureza_titulo,
                   teor, teor_formato, cancelado, acervo, origem, hash_ato, hash_anterior,
                   lavrado_em)
               VALUES (?, 'R', 1, '2026-09-23', 'Título de domínio sob condição resolutiva',
                       ?, 'html', 0, 0, 'MANUAL', 'h', NULL, '2026-09-23T09:00')""",
            (mid, TEOR_4019 + " IMÓVEL OBJETO DESTA MATRÍCULA: Lote nº 46 - P.A. Exemplo, com área"))
        aid = int(cur.lastrowid)
        for papel, nome, doc in (("transmitente", "INSTITUTO EXEMPLO", "00000001000055"),
                                 ("adquirente", "MARIO EXEMPLO", "00000000191")):
            con.execute("""INSERT INTO ri_partes (matricula_id, ato_id, papel, nome,
                               documento_numero, participacao)
                           VALUES (?,?,?,?,?, '100')""", (mid, aid, papel, nome, doc))
    con.close()
    return aid


def test_a_tela_da_ctp_sugere_do_teor_e_a_doi_sai_no_layout(casa):
    aid = _titulo_de_dominio(casa)
    c = casa["cliente"]
    html = c.get("/registro-imoveis/ctp?competencia=2026-09").get_data(as_text=True)
    assert f'name="i{aid}_folha_ato"' in html
    assert 'value="3173.38"' in html, "o valor pago não veio sugerido do teor"
    assert 'value="2036-08"' in html, "a última parcela não veio sugerida do teor"
    assert "Lote nº 46 - P.A. Exemplo" in html, "a denominação aceitou a frase da ficha"
    assert "Falta para este ato entrar na DOI" in html      # falta a folha

    # O escrevente confere e salva, com a folha
    campos = {"csrf_token": _token(html), "acao": "salvar", f"incluir_{aid}": "1"}
    for nome, valor in re.findall(rf'name="(i{aid}_[a-z_]+)"[^>]*value="([^"]*)"', html):
        campos[nome] = valor
    campos.update({f"i{aid}_operacao": "73", f"i{aid}_forma_pagamento": "7",
                   f"i{aid}_valor_operacao": "7706,83", f"i{aid}_data_negocio": "2017-08-22",
                   f"i{aid}_valor_base_itbi_nao_consta": "1", f"i{aid}_natureza_titulo": "4",
                   f"i{aid}_folha_ato": "2-2v"})
    assert c.post("/registro-imoveis/ctp?competencia=2026-09", data=campos).status_code in (200, 302)

    html = c.get("/registro-imoveis/doi?competencia=2026-09").get_data(as_text=True)
    resp = c.post("/registro-imoveis/doi?competencia=2026-09",
                  data={"csrf_token": _token(html), "acao": "gerar"})
    assert resp.mimetype == "application/json", resp.get_data(as_text=True)[:2000]
    dec = json.loads(resp.get_data(as_text=True))["declaracoes"][0]
    assert dec["tipoServico"] == "2" and dec["tipoAto"] == "4"
    assert dec["folha"] == "2-2v" and dec["naturezaTitulo"] == "4"
    assert dec["valorPagoAteDataAto"] == 3173.38
    assert dec["mesAnoUltimaParcela"] == "2036-08-01"
    assert dec["localizacao"] == "zona rural"
    assert ri_doi.conferir_layout(dec) == []
