import sqlite3

from jinja2.sandbox import SandboxedEnvironment

import ri_schema
from ri_odt import (MODELO_CABECALHO_PADRAO, MODELO_FICHA_PADRAO,
                    anexar_fecho_ao_ato, ato_sem_espaco_antes_do_fecho, bloco_selo_odf,
                    html_para_odf, texto_para_odf)
from serventia import dados
import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402


def render(modelo, contexto):
    return SandboxedEnvironment(autoescape=False).from_string(modelo).render(**contexto)


def test_cabecalho_destaca_matricula_sem_data_e_traz_beatriz():
    html = render(MODELO_CABECALHO_PADRAO, {
        "m": {"numero": "8421", "cnm": "000000.2.0008421-00"},
        "serventia": {"cidade": "Cidade Exemplo", "uf": "MA",
                       "registrador": "Mario Exemplo dos Santos",
                       "substituta": "Beatriz Exemplo de Souza",
                       "titulo_registrador": "Tabelião e Oficial de Registro",
                       "titulo_substituta": "Tabeliã Registradora Substituta"},
        "ficha_numero": "1", "livro_ficha": "2", "usuario_impressao": "TESTE",
        "data_abertura_br": "07/09/2026",
    })
    odf = html_para_odf(html, compacto=True)
    # O CABEÇALHO IMPRIME EM MAIÚSCULAS, e o cadastro guarda em caixa mista —
    # 16/09/2026. O modelo tem `{{ serventia.substituta|upper }}`, e por isso
    # a troca da grafia no cadastro («corrija tudo pra … Beatriz Exemplo de
    # Souza») **não muda o cabeçalho**: ali as três linhas são
    # maiúsculas de propósito. Quem muda é a linha de assinatura da abertura,
    # que sai com o nome como ele está gravado.
    assert "BEATRIZ EXEMPLO DE SOUZA" in odf
    assert "P-celula-destaque" in odf
    assert "07/09/2026" not in odf


def test_data_de_abertura_e_primeira_informacao_da_ficha():
    assert MODELO_FICHA_PADRAO.index("DATA DE ABERTURA DA FICHA") < MODELO_FICHA_PADRAO.index("DENOMINAÇÃO")
    assert "{{ selo_abertura_odf }}" in MODELO_FICHA_PADRAO


def test_fecho_do_registro_nao_cria_linha_em_branco():
    # O molde mudou na 3.6.216 (25/09/2026): `a.teor_odf` e `a.selo_odf` já
    # chegam como parágrafos/tabela de ODF, e o `<p>` em volta deles aninhava
    # parágrafo dentro de parágrafo. A propriedade guardada é a mesma — o teor
    # só sai quando existe, e o fecho não abre linha em branco.
    assert "{% if a.teor_odf %}{{ a.teor_odf }}{% endif %}" in MODELO_FICHA_PADRAO
    assert "{% if a.fecho %}<p></p>" not in MODELO_FICHA_PADRAO


def test_somente_ultimo_paragrafo_do_ato_perde_a_margem_inferior():
    odf = ato_sem_espaco_antes_do_fecho(texto_para_odf("Primeiro.\nÚltimo."))
    assert odf.count('text:style-name="P-just"') == 1
    assert odf.count('text:style-name="P-ato-final"') == 1


def test_fecho_fica_no_mesmo_paragrafo_logo_depois_do_ponto():
    odf = anexar_fecho_ao_ato(texto_para_odf("Fim do ato."), "Cidade Exemplo/MA. Dou fé.")
    assert "Fim do ato. Cidade Exemplo/MA. Dou fé.</text:p>" in odf
    assert odf.count("<text:p") == 1


def test_dois_selos_saem_lado_a_lado_com_um_qr_para_cada_um():
    texto = ("Poder Judiciário - TJMA. Selo: REGIST000000ABCDEFGHIJKLMNO01\n"
             "Poder Judiciário - TJMA. Selo: ARQUIV000000ABCDEFGHIJKLMNO02")
    odf = bloco_selo_odf(texto, ["um.png", "dois.png"])
    assert odf.count("<table:table-row>") == 1
    assert 'Pictures/um.png' in odf
    assert 'Pictures/dois.png' in odf
    assert odf.count('style-name="Cel-selo-compacto"') == 2


def test_um_selo_ocupa_so_metade_e_nao_desenha_caixa_vazia():
    odf = bloco_selo_odf(
        "Poder Judiciário - TJMA. Selo: MATRIC000000ABCDEFGHIJKLMNO03",
        ["abertura.png"])
    assert 'table:number-columns-spanned="2"' not in odf
    assert odf.count('style-name="Cel-selo-compacto"') == 1
    assert odf.count('style-name="Tab-cab.cel"') == 1


def test_schema_guarda_selo_da_abertura_e_segundo_qr_do_ato():
    con = conexao_de_teste()
    con.executescript(ri_schema.SCHEMA)
    matricula = {r[1] for r in con.execute("PRAGMA table_info(ri_matriculas)")}
    atos = {r[1] for r in con.execute("PRAGMA table_info(ri_atos)")}
    assert {"selo_abertura_texto", "selo_abertura_qr", "selo_abertura_qr_2"} <= matricula
    assert {"selo_texto", "selo_qr", "selo_qr_2"} <= atos
