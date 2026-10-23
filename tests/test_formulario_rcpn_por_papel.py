"""O formulário do assento arrumado pelo papel que o escrevente tem na mão —
13/10/2026.

    «vamos reorganizar os campos de formulario dos registros de nascimento,
     casamento e obito, ele eh muito segmentado hoje, com separacoes que nao
     fazem sentido. vamos separar os campos de preenchimento de forma racional
     e apenas por criterio de facilidade para o operador, a logica deve ser
     cumprir os requisitos presentes na lei 6015 e no codigo de normas do
     tjma» — o oficial

O QUE ESTES TESTES GUARDAM
    **A ordem das três espécies**: o fato (o que está na DNV, na DO, na
    habilitação), a pessoa de quem é o assento, os genitores com os seus pais,
    as perguntas do óbito, quem declara e testemunha — e o termo, a matrícula e
    o selo por último.
    **As perguntas do óbito (art. 80; art. 255 do Código de Normas) estão no
    formulário e chegam ao termo** — antes só se respondiam depois de lavrar,
    e o termo saía sem elas.
    **Nenhum nome de campo sumiu**: a rota, o rascunho e a conferência leem os
    mesmos.

Nomes fictícios, como em todo teste desta casa.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import rc_marcas_do_obito as MARCA                               # noqa: E402
from test_testemunha_fantasma_20261009 import (                  # noqa: E402,F401
    FOLHAS, _con, _lavrar_do_rascunho, _rascunho_obito, casa)

ANTES = (Path(__file__).resolve().parent.parent / "templates"
         / "atrib_rcpn_novo.html")


def _ordem(html: str, *marcos: str) -> list[int]:
    return [html.index(m) for m in marcos]


def test_nascimento_na_ordem_do_papel(casa):
    html = casa["c"].get("/rcpn/novo/nascimento").get_data(as_text=True)
    p = _ordem(html, "Dados do nascimento", 'name="dnv"', 'name="ibge_local"',
               "Dados do registrado", 'name="cor_raca"',
               "Mãe — filiação 1 e avós maternos", 'name="prog2f1_nome"',
               "Pai — filiação 2 e avós paternos", 'name="prog2f2_nome"',
               'name="declarante_nome"', 'name="testemunha_nome"',
               "Termo, matrícula e selo", 'name="teor"', 'name="matricula"')
    assert p == sorted(p)
    assert "Dados para a remessa do IBGE" not in html
    assert "Perguntas obrigatórias do óbito" not in html


def test_obito_na_ordem_do_papel_com_as_perguntas_do_art_80(casa):
    html = casa["c"].get("/rcpn/novo/obito").get_data(as_text=True)
    p = _ordem(html, "Dados do óbito", 'name="numero_do"', 'name="causa_morte"',
               "Dados do falecido", "Mãe — filiação 1",
               "Perguntas obrigatórias do óbito", 'name="testamento"',
               'name="declarante_nome"', "Termo, matrícula e selo")
    assert p == sorted(p)
    for chave in MARCA.CHAVES:
        assert f'name="{chave}"' in html, chave
    assert "o declarante não sabe" in html
    assert "avós maternos" not in html          # o óbito não pede avós


def test_casamento_cada_conjuge_seguido_dos_seus_pais(casa):
    html = casa["c"].get("/rcpn/novo/casamento").get_data(as_text=True)
    p = _ordem(html, "Dados da celebração", 'name="regime_bens"',
               "Primeiro cônjuge", "Mãe do primeiro cônjuge",
               "Pai do primeiro cônjuge", "Segundo cônjuge",
               "Mãe do segundo cônjuge", "Pai do segundo cônjuge",
               'name="testemunha_nome"', "Termo, matrícula e selo")
    assert p == sorted(p)


def test_nenhum_nome_de_campo_sumiu_do_formulario():
    """Os `name=` da tela antiga, guardada na arrumação, continuam todos."""
    import re
    antigo = {"data_fato", "hora_fato", "local_fato_nome", "local_fato_endereco",
              "nao_tem_local_fato", "naturalidade_declarada", "cor_raca",
              "causa_morte", "atestante", "atestante_documento",
              "local_sepultamento", "testamento", "ibge_local", "ibge_gemeo",
              "dnv", "numero_do", "natureza_obito", "local_obito", "nome",
              "matricula", "teor", "regime_bens", "habilitacao_serventia",
              "habilitacao_selo", "selo", "prog1f1_nome", "prog2f1_nome",
              "prog1f2_nome", "prog2f2_nome"}
    agora = set(re.findall(r'name="([a-z0-9_]+)"', ANTES.read_text(encoding="utf-8")))
    assert antigo <= agora, antigo - agora


def test_as_respostas_do_obito_entram_no_termo_da_lavratura(casa):
    dados = _rascunho_obito() | {"obito_eleitor": "SIM",
                                 "obito_possui_bens": "NAO",
                                 "obito_possui_filho": "SIM",
                                 "obito_desconhecido": "NAO"}
    aid, _ = _lavrar_do_rascunho(casa, dados, FOLHAS[0])
    con = _con(casa)
    a = con.execute("SELECT * FROM rc_assentos WHERE id=?", (aid,)).fetchone()
    con.close()
    assert (a["obito_eleitor"], a["obito_possui_bens"],
            a["obito_possui_filho"]) == ("SIM", "NAO", "SIM")
    teor = a["teor"] or ""
    assert "Era eleitora." in teor     # a falecida é do sexo F (LD01)
    assert "Não deixou bens." in teor
    assert "Deixou filhos." in teor


# ------------------------------------------------ o que a lei pede (13/10/2026)
#
# «quero acrescentar» e «tem campos condicionais, cuidar para nao exigir o
# preenchimento deles para todos os casos» — o oficial.

import re as _re                                                  # noqa: E402

import rc_assento as RC                                           # noqa: E402
import rc_modelos_do_livro as ML                                  # noqa: E402

NOVOS = {
    "nascimento": RC.CAMPOS_DA_LEI_POR_ESPECIE["NASCIMENTO"],
    "obito": RC.CAMPOS_DA_LEI_POR_ESPECIE["OBITO"],
    "casamento": RC.CAMPOS_DA_LEI_POR_ESPECIE["CASAMENTO"],
}


ABREM_BLOCO = {"registro_tardio"}


def test_os_campos_novos_estao_na_tela_e_nenhum_e_exigido(casa):
    for slug, campos in NOVOS.items():
        html = casa["c"].get(f"/rcpn/novo/{slug}").get_data(as_text=True)
        for c in campos:
            m = _re.search(r'<(?:input|select|textarea)[^>]*name="%s"[^>]*>' % c, html)
            assert m, (slug, c)
            assert "required" not in m.group(0), (slug, c)
            # e mora num bloco condicional, que o script mostra só quando cabe
            # — menos a marca do registro tardio (21/10/2026), que é ela
            # mesma a chave que abre o bloco do tardio.
            if c in ABREM_BLOCO:
                continue
            assert "data-se-campo" in html[:m.start()][-2500:], (slug, c)


def test_sem_dado_novo_o_termo_fica_como_era():
    assert ML.frase_do_conjuge_do_falecido({}, "solteiro") == "Era solteiro."
    assert ML.frase_do_conjuge_do_falecido({}, "") == ""
    assert ML.frase_dos_filhos_do_falecido({}, "Deixou filhos.") == "Deixou filhos."
    assert ML.frase_dos_herdeiros({}) == ""
    assert ML.frase_do_casamento_anterior({}, "nubente1") == ""
    assert ML.frase_do_pacto({}) == ""
    assert ML.frase_do_casamento_dos_pais({}) == ""


def test_as_frases_novas_com_dado():
    a = {"obito_conjuge_nome": "ANA EXEMPLO", "obito_conjuge_situacao": "PRE_MORTO",
         "obito_conjuge_cartorio": "Cartório de Cidade Exemplo/MA",
         "obito_filhos": "JOÃO EXEMPLO, 20 anos\nMARIA EXEMPLO, 15 anos\n",
         "obito_herdeiros_menores": "SIM",
         "nubente2_conjuge_anterior": "PEDRO EXEMPLO",
         "nubente2_dissolucao_data": "2019-05-03",
         "pacto_data": "2026-01-10", "pacto_serventia": "Tabelionato Exemplo/MA",
         "pais_casamento_lugar": "Cidade Exemplo/MA"}
    assert ML.frase_do_conjuge_do_falecido(a, "viúvo") == (
        "Era viúvo, sendo cônjuge pré-morto ANA EXEMPLO, com casamento "
        "registrado em Cartório de Cidade Exemplo/MA.")
    assert ML.frase_dos_filhos_do_falecido(a, "Deixou filhos.") == (
        "Deixou os filhos: JOÃO EXEMPLO, 20 anos; MARIA EXEMPLO, 15 anos.")
    assert ML.frase_dos_herdeiros(a) == " Deixou herdeiros menores ou interditados."
    assert ML.frase_do_casamento_anterior(a, "nubente2") == (
        ", tendo sido casado(a) com PEDRO EXEMPLO, casamento dissolvido em 03/05/2019")
    assert ML.frase_do_pacto(a) == (", conforme escritura de pacto antenupcial "
                                    "lavrada em 10/01/2026 nas notas de "
                                    "Tabelionato Exemplo/MA")
    assert ML.frase_do_casamento_dos_pais(a) == ", casados entre si em Cidade Exemplo/MA"


def test_o_obito_com_conjuge_filhos_e_herdeiros_chega_ao_termo(casa):
    dados = _rascunho_obito() | {
        "pessoa_estado_civil": "casada",
        "obito_conjuge_situacao": "SOBREVIVENTE",
        "obito_conjuge_nome": "JOSE CONJUGE EXEMPLO",
        "obito_conjuge_cartorio": "Ofício Exemplo/MA",
        "obito_possui_filho": "SIM",
        "obito_filhos": "FILHO UM EXEMPLO, 30 anos\nFILHO DOIS EXEMPLO, 25 anos",
        "obito_possui_bens": "SIM", "obito_herdeiros_menores": "NAO",
        "obito_eleitor": "SIM", "obito_desconhecido": "NAO"}
    aid, _ = _lavrar_do_rascunho(casa, dados, FOLHAS[1])
    con = _con(casa)
    a = con.execute("SELECT * FROM rc_assentos WHERE id=?", (aid,)).fetchone()
    con.close()
    teor = a["teor"] or ""
    assert "cônjuge sobrevivente JOSE CONJUGE EXEMPLO" in teor
    assert "com casamento registrado em Ofício Exemplo/MA" in teor
    assert "Deixou os filhos: FILHO UM EXEMPLO, 30 anos; FILHO DOIS EXEMPLO, 25 anos." in teor
    assert "Deixou bens. Não deixou herdeiros menores nem interditados." in teor


def test_registro_gratuito_nao_mostra_protocolo_nem_cobranca(casa):
    """«tire esse campo de protocolo para cobrança de selo nos registros
    gratuitos, de nascimento e óbito» — o oficial, 13/10/2026."""
    fonte = ANTES.read_text(encoding="utf-8")
    assert "{% if not (nascimento or obito or natimorto) %}" in fonte
    for slug in ("nascimento", "obito"):
        html = casa["c"].get(f"/rcpn/novo/{slug}").get_data(as_text=True)
        assert 'name="protocolo_id"' not in html, slug
        assert 'name="cobrar"' not in html, slug
        assert 'name="cobrar_protocolo_item"' not in html, slug
