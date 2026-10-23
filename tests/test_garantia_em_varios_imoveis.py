"""O ITEM 16.31 — a mesma garantia em mais de um imóvel, e o teto do art. 37.

A PERGUNTA DO OFICIAL, em 21/09/2026, orçando a cédula do protocolo 2026.09.46:

    «não seria caso de dividir o valor total do contrato pelo número de
     garantias?»

**NÃO — pelo número de IMÓVEIS, e dentro de cada garantia.** É o que o item
16.31 diz («quando dois ou mais imóveis forem dados em garantia; ou no caso de
penhor, quando a garantia esteja estipulada em mais de um imóvel») lido com o
16.29 («mais de um registro em razão do mesmo título, os emolumentos serão
cobrados separadamente»). O exemplo que os colegas do Maranhão fixaram em
27/08/2026, no grupo:

    «Mútuo de 200 mil com hipoteca de 1 imóvel e penhor em 2 imóveis.
     HIPOTECA: base de cálculo 200 mil.
     PENHOR: base de cálculo 100 mil para cada imóvel de localização.»

Cada TIPO de garantia guarda o valor cheio; o que se divide é cada garantia
pelos imóveis em que ELA está.

E O TETO DO ART. 37 SE MEDE E NÃO SE APLICA SOZINHO. Como ele se conta — por
tipo de garantia ou pela soma de todos os registros do mesmo título — está em
disputa entre os colegas, com ofício na corregedoria. O sistema põe os dois
números na frente de quem assina, e não corta nada: é a régua do CNIB e do
usucapião.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import emolumentos as EMOL

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "tests"))
from banco_de_teste import conexao_de_teste  # noqa: E402

# Três faixas da 16.45 e a última da 16.3, que é onde o teto do art. 37 mora.
# **Os valores são os da vigência 10022 desta casa, copiados um a um** — com os
# quatro fundos, porque é a soma deles que dá o total que o cliente paga. Uma
# bancada com fundos zerados faria o teste conferir um número que a tabela real
# não produz.
FAIXAS_16_45 = (
    #  código      de              até            emol        ferc      femp      fadep     ferrfis   total
    ("16.45.18", "207.832,92", "259.791,14", "3.797,50", "113,93", "151,90", "151,90", "37,98", "4.253,21"),
    ("16.45.20", "324.738,93", "405.923,67", "5.932,47", "177,97", "237,30", "237,30", "59,32", "6.644,36"),
    ("16.45.23", "634.255,73", "792.819,67", "11.586,44", "347,59", "463,46", "463,46", "115,86", "12.976,81"),
)
TETO = "21.380,93"


def _tabela(caminho) -> sqlite3.Connection:
    con = conexao_de_teste()
    con.execute("""CREATE TABLE cx_vigencias (codigo INTEGER PRIMARY KEY,
                   vigente INTEGER NOT NULL DEFAULT 0)""")
    con.execute("""CREATE TABLE cx_faixas (id INTEGER PRIMARY KEY AUTOINCREMENT,
                   tabela INTEGER, vigencia INTEGER, de TEXT, ate TEXT,
                   codigo_tj TEXT, emolumentos TEXT, ferc TEXT, femp TEXT,
                   fadep TEXT, ferrfis TEXT, total TEXT)""")
    con.execute("INSERT INTO cx_vigencias (codigo, vigente) VALUES (10022, 1)")
    for faixa in FAIXAS_16_45:
        codigo_tj, de, ate, emol, ferc, femp, fadep, ferrfis, total = faixa
        con.execute(
            """INSERT INTO cx_faixas (tabela, vigencia, de, ate, codigo_tj,
                                      emolumentos, ferc, femp, fadep, ferrfis,
                                      total)
               VALUES (9, 10022, ?,?,?,?,?,?,?,?,?)""",
            (de, ate, codigo_tj, emol, ferc, femp, fadep, ferrfis, total))
    # A última faixa da 16.3 — o teto do art. 37, como o TJMA o escreve.
    con.execute(
        """INSERT INTO cx_faixas (tabela, vigencia, de, ate, codigo_tj,
                                  emolumentos, ferc, femp, fadep, ferrfis, total)
           VALUES (5, 10022, '8.068.892,64', '999.999.999.999,99', '16.3.36',
                   ?, '0,00','0,00','0,00','0,00', '23.946,65')""", (TETO,))
    con.commit()
    return con


# ------------------------------------------------ a divisão pelos imóveis

def test_um_imovel_nao_divide_nada(tmp_path):
    """A cédula do protocolo 2026.09.46: cada garantia está num imóvel só."""
    con = _tabela(tmp_path / "t.sqlite3")
    item = EMOL.calcular_item(con, tabela=9, base="695.404,50")
    assert item["codigo_tj"] == "16.45.23"
    assert item["quantidade"] == 1
    assert item["base_calculo"] == "695.404,50"
    assert item["total"] == "12.976,81"


def test_a_mesma_garantia_em_dois_imoveis_divide_a_base(tmp_path):
    """R$ 695.404,50 em dois imóveis: cada registro vale metade, e são dois."""
    con = _tabela(tmp_path / "t.sqlite3")
    item = EMOL.calcular_item(con, tabela=9, base="695.404,50", imoveis=2)
    assert item["base_calculo"] == "347.702,25"
    assert item["codigo_tj"] == "16.45.20", "a metade cai noutra faixa"
    assert item["quantidade"] == 2, "um registro por imóvel"
    assert item["base_do_negocio"] == "695.404,50"


def test_dividir_pode_sair_mais_caro_que_nao_dividir(tmp_path):
    """**O guarda contra a intuição de que dividir é sempre desconto.**

    Duas faixas menores podem somar mais que uma grande, e é por isso que a
    divisão não é escolha do balcão: é o que o item 16.31 manda quando a
    garantia está em mais de um imóvel.
    """
    con = _tabela(tmp_path / "t.sqlite3")
    um = EMOL.calcular_item(con, tabela=9, base="695.404,50")
    dois = EMOL.calcular_item(con, tabela=9, base="695.404,50", imoveis=2)
    assert dois["total"] == "13.288,72"
    assert dois["total_centavos"] > um["total_centavos"]


def test_a_sobra_de_centavos_e_declarada(tmp_path):
    """Divisão que não fecha não se espalha calada: quem confere a conta
    precisa saber que a soma das bases não bate com o contrato."""
    con = _tabela(tmp_path / "t.sqlite3")
    item = EMOL.calcular_item(con, tabela=9, base="695.404,51", imoveis=2)
    assert item["sobra_centavos"] == 1
    assert item["base_calculo"] == "347.702,25"


def test_a_divisao_e_em_centavos_inteiros(tmp_path):
    """Em ponto flutuante uma divisão por três põe a base do lado errado da
    fronteira da faixa — a mesma razão de `faixa_por_valor` comparar inteiros."""
    con = _tabela(tmp_path / "t.sqlite3")
    item = EMOL.calcular_item(con, tabela=9, base="695.404,50", imoveis=3)
    assert item["base_calculo"] == "231.801,50"
    assert item["sobra_centavos"] == 0
    assert item["quantidade"] == 3


def test_o_caminho_do_servico_nao_divide(tmp_path):
    """Quem digita o código do sub-item já escolheu a faixa: dividir ali seria
    mexer numa escolha que a pessoa fez."""
    con = _tabela(tmp_path / "t.sqlite3")
    con.execute("""CREATE TABLE cx_servicos (codigo INTEGER PRIMARY KEY,
                   codigo_tj TEXT, descricao TEXT, descricao_norm TEXT,
                   ativo INTEGER DEFAULT 1)""")
    con.execute("""CREATE TABLE cx_servico_valores (servico INTEGER,
                   vigencia INTEGER, emolumentos TEXT, ferc TEXT, femp TEXT,
                   fadep TEXT, ferrfis TEXT, total TEXT)""")
    con.execute("INSERT INTO cx_servicos VALUES (1506,'16.45.23','x','x',1)")
    con.execute("""INSERT INTO cx_servico_valores VALUES
                   (1506, 10022, '11.586,44','0,00','0,00','0,00','0,00',
                    '12.976,81')""")
    item = EMOL.calcular_item(con, servico=1506, base="695.404,50", imoveis=2)
    assert item["codigo_tj"] == "16.45.23"
    assert item["quantidade"] == 1
    assert item["base_calculo"] == "695.404,50"


# --------------------------------------------------------- o teto do art. 37

def test_o_teto_sai_da_tabela_e_nao_do_codigo(tmp_path):
    """Ele muda por Resolução a cada exercício. Escrito aqui, a virada da
    tabela exigiria versão nova do sistema."""
    con = _tabela(tmp_path / "t.sqlite3")
    from caixa_schema import reais
    assert reais(EMOL.teto_geral(con)) == TETO


def test_sem_tabela_importada_o_teto_e_zero(tmp_path):
    """Instalação nova não tem faixa nenhuma, e ali «não dá para conferir» é a
    resposta certa — não um teto inventado."""
    con = conexao_de_teste()
    con.execute("""CREATE TABLE cx_vigencias (codigo INTEGER PRIMARY KEY,
                   vigente INTEGER NOT NULL DEFAULT 0)""")
    con.execute("""CREATE TABLE cx_faixas (tabela INTEGER, vigencia INTEGER,
                   ate TEXT, emolumentos TEXT)""")
    assert EMOL.teto_geral(con) == 0
    assert EMOL.garantias_acima_do_teto(
        [{"codigo_ato": "16.45.23", "emolumentos": "99.999,00"}], 0) is None


def test_um_registro_sozinho_nao_passa_do_teto(tmp_path):
    con = _tabela(tmp_path / "t.sqlite3")
    teto = EMOL.teto_geral(con)
    itens = [{"codigo_ato": "16.45.23", "emolumentos": "11.586,44"}]
    assert EMOL.garantias_acima_do_teto(itens, teto) is None


def test_os_dois_registros_da_cedula_passam_do_teto(tmp_path):
    """O caso real do protocolo 2026.09.46, que é o que fez a pergunta nascer."""
    con = _tabela(tmp_path / "t.sqlite3")
    teto = EMOL.teto_geral(con)
    itens = [{"codigo_ato": "16.45.23", "emolumentos": "11.586,44"}] * 2
    aviso = EMOL.garantias_acima_do_teto(itens, teto)
    assert aviso["registros"] == 2
    assert aviso["emolumentos"] == "23.172,88"
    assert aviso["teto"] == TETO
    assert aviso["excesso"] == "1.791,95"
    # O teto é de emolumento; o que o cliente pagaria é com os quatro fundos.
    assert aviso["total_no_teto"] == "23.946,65"


def test_o_que_nao_e_registro_de_garantia_nao_entra_na_conta():
    """Prenotação, certidão e arquivamento são outros atos, com outro teto —
    somá-los aqui acusaria teto onde não há."""
    itens = [{"codigo_ato": "16.1", "emolumentos": "20.000,00"},
             {"codigo_ato": "16.24.4", "emolumentos": "20.000,00"}]
    assert EMOL.garantias_acima_do_teto(itens, 100) is None


def test_o_16_13_1_conta_como_registro_de_garantia():
    """O texto dele manda para o 16.45 — «por cada registro das garantias reais
    ou gravames decorrentes de cédula ... os emolumentos serão os mesmos do
    item 16.45»."""
    itens = [{"codigo_ato": "16.13.1", "emolumentos": "30.000,00"}]
    assert EMOL.garantias_acima_do_teto(itens, 100) is not None


# ------------------------------------------------------------------- a tela

def _token(html: str) -> str:
    """O csrf_token da tela — a mesma leitura dos outros testes do caixa."""
    import re
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _protocolo_com_a_tabela(banco) -> int:
    """Um protocolo do balcão e as faixas da 16.45, no banco de ensaio."""
    con = sqlite3.connect(str(banco))
    try:
        cur = con.execute(
            """INSERT INTO cx_protocolos (numero, data_abertura, interessado,
                                          situacao, criado_em)
               VALUES ('2026.09.902', '2026-09-21', ?, 'ABERTO',
                       '2026-09-21T14:37:42')""",
            ("PEDRO ARRUDA VIEIRA FARIAS",))
        protocolo_id = int(cur.lastrowid)
        con.execute("""INSERT INTO cx_vigencias (codigo, descricao, vigente,
                                                 servicos, faixas, importado_em)
                       VALUES (10022, 'Vigência de ensaio', 1, 0, 0,
                               '2026-09-21')""")
        for faixa in FAIXAS_16_45:
            codigo_tj, de, ate, emol, ferc, femp, fadep, ferrfis, total = faixa
            con.execute(
                """INSERT INTO cx_faixas (tabela, vigencia, de, ate, codigo_tj,
                                          emolumentos, ferc, femp, fadep,
                                          ferrfis, total)
                   VALUES (9, 10022, ?,?,?,?,?,?,?,?,?)""",
                (de, ate, codigo_tj, emol, ferc, femp, fadep, ferrfis, total))
        con.execute(
            """INSERT INTO cx_faixas (tabela, vigencia, de, ate, codigo_tj,
                                      emolumentos, ferc, femp, fadep, ferrfis,
                                      total)
               VALUES (5, 10022, '8.068.892,64', '999.999.999.999,99',
                       '16.3.36', ?, '0,00','0,00','0,00','0,00',
                       '23.946,65')""", (TETO,))
        con.commit()
        return protocolo_id
    finally:
        con.close()


def test_a_tela_pergunta_em_quantos_imoveis_a_garantia_esta(cg_casa_logada):
    """Sem o campo, o balcão teria de dividir na mão e digitar o resultado —
    e valor digitado é justamente o que esta tela existe para não ter."""
    protocolo_id = _protocolo_com_a_tabela(cg_casa_logada["banco"])
    html = cg_casa_logada["c"].get(
        f"/caixa/protocolos/{protocolo_id}").get_data(as_text=True)
    assert 'name="imoveis"' in html
    assert "16.31" in html


def test_acrescentar_pela_faixa_divide_e_diz_que_dividiu(cg_casa_logada):
    """O item entra com a base dividida, e a frase da tela mostra a conta."""
    protocolo_id = _protocolo_com_a_tabela(cg_casa_logada["banco"])
    c = cg_casa_logada["c"]
    token = _token(c.get(f"/caixa/protocolos/{protocolo_id}").get_data(as_text=True))
    resposta = c.post(
        f"/caixa/protocolos/{protocolo_id}/itens",
        data={"acao": "acrescentar", "tabela": "9",
              "base_calculo": "695.404,50", "imoveis": "2",
              "csrf_token": token},
        follow_redirects=True).get_data(as_text=True)
    assert "347.702,25" in resposta, "a tela não diz a base de cada registro"
    assert "16.31" in resposta

    con = sqlite3.connect(str(cg_casa_logada["banco"]))
    try:
        linha = con.execute(
            """SELECT codigo_ato, quantidade, base_calculo, valor_total
               FROM cx_protocolo_atos WHERE protocolo_id=?""",
            (protocolo_id,)).fetchone()
    finally:
        con.close()
    assert linha == ("16.45.20", 2, "347.702,25", "13.288,72")


def test_a_tela_avisa_quando_as_garantias_passam_do_teto(cg_casa_logada):
    """Os dois registros da cédula de R$ 695 mil: nenhum passa sozinho, e
    somados passam. A tela põe os dois números na frente de quem assina."""
    protocolo_id = _protocolo_com_a_tabela(cg_casa_logada["banco"])
    c = cg_casa_logada["c"]
    token = _token(c.get(f"/caixa/protocolos/{protocolo_id}").get_data(as_text=True))
    for _ in range(2):
        c.post(f"/caixa/protocolos/{protocolo_id}/itens",
               data={"acao": "acrescentar", "tabela": "9",
                     "base_calculo": "695.404,50", "csrf_token": token})
    html = c.get(f"/caixa/protocolos/{protocolo_id}").get_data(as_text=True)
    assert "passam do teto" in html
    assert "23.172,88" in html, "não diz quanto a tabela deu"
    assert TETO in html, "não diz qual é o teto"
    assert "23.946,65" in html, "não diz quanto o cliente pagaria no teto"


def test_com_um_registro_so_a_tela_nao_avisa_nada(cg_casa_logada):
    """Alarme que soa sempre é alarme que ninguém ouve."""
    protocolo_id = _protocolo_com_a_tabela(cg_casa_logada["banco"])
    c = cg_casa_logada["c"]
    token = _token(c.get(f"/caixa/protocolos/{protocolo_id}").get_data(as_text=True))
    c.post(f"/caixa/protocolos/{protocolo_id}/itens",
           data={"acao": "acrescentar", "tabela": "9",
                 "base_calculo": "695.404,50", "csrf_token": token})
    html = c.get(f"/caixa/protocolos/{protocolo_id}").get_data(as_text=True)
    assert "passam do teto" not in html


def test_o_modulo_nao_corta_o_valor_sozinho():
    """**A régua do CNIB, pela enésima vez.** Como o teto se conta está em
    disputa; cortar por uma das leituras seria o sistema decidindo tese
    jurídica. Ele mede e avisa — quem decide é quem assina."""
    from pathlib import Path
    codigo = (Path(__file__).resolve().parents[1] / "emolumentos.py").read_text(
        encoding="utf-8")
    for proibido in ("def limitar_ao_teto", "def aplicar_teto",
                     "def cortar_no_teto"):
        assert proibido not in codigo, f"{proibido} decide no lugar do oficial"
