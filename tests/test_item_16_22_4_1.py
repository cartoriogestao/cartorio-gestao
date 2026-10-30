"""O item 16.22.4.1 na caixa «Acrescentar item pela tabela».

Pedido da substituta em 30/10/2026: na seção em que se escolhe a tabela
(a 16.3, a 16.9, a do crédito rural) e se digita o valor, tem de dar para
acrescentar a averbação de retificação de memorial descritivo decorrente de
certificação de georreferenciamento no SIGEF/INCRA.

O cadastro desse serviço tem total R$ 0,00 — o preço não mora nele. O texto
do item manda os emolumentos da tabela 16.9 com redução de ½ na base (o valor
da área total do imóvel). `calcular_item` já faz esse corte. O que faltava
era um caminho na tela para informar o valor, e uma trava para a busca por
código não gravar o zero.

COM IMÓVEL DE R$ 100.000,00 a base que a 16.9 vê é R$ 50.000,00, faixa
16.9.11 (R$ 45.851,30 a R$ 57.314,07) da vigência 10022: emolumento R$ 419,24,
total R$ 469,55. Sem o corte, os mesmos R$ 100.000,00 cairiam na 16.9.14
(emolumento R$ 817,87). Os números são os da tabela, copiados de
`tests/custas_reais.json`.

O `codigo_ato` gravado é `16.22.4.1`, não o subitem 16.9.11: o selo procura
o código exato. A base gravada continua o valor do imóvel — o selo é quem
manda a metade ao tribunal (`base_calculo_do_selo_ri`). Gravar a metade aqui
cobraria a faixa certa no caixa e a faixa de baixo no selo.
"""
from __future__ import annotations

import re
import sqlite3

import emolumentos as EMOL
from seguranca_web import numero_digitado

from banco_de_teste import conexao_de_teste

CODIGO = "16.22.4.1"
ATALHO = "tj:16.22.4.1"
SERVICO = 90221
DESCRICAO = (
    "Averbação de retificação de memorial descritivo decorrente de "
    "certificação de georreferenciamento no SIGEF/INCRA"
)

# Faixas da vigência 10022, copiadas de tests/custas_reais.json.
# A 16.9.11 é a da base pela metade (R$ 50.000,00). A 16.9.14 é a que os
# R$ 100.000,00 inteiros ocupariam — se o teste cair nela, o corte não rodou.
FAIXA_METADE = (
    "16.9.11", "45.851,30", "57.314,07",
    "419,24", "12,58", "16,77", "16,77", "4,19", "469,55",
)
FAIXA_CHEIA = (
    "16.9.14", "89.553,27", "111.941,56",
    "817,87", "24,54", "32,71", "32,71", "8,18", "916,01",
)
# A 16.3.14 é a faixa do registro com valor declarado para os mesmos
# R$ 100.000,00. Serve para ver que o atalho não desviou as outras tabelas.
FAIXA_16_3 = (
    "16.3.14", "89.553,27", "111.941,56",
    "1.636,01", "49,08", "65,44", "65,44", "16,36", "1.832,33",
)


def _tabela(*, descricao: str = DESCRICAO, ativo: int = 1):
    con = conexao_de_teste()
    con.execute("""CREATE TABLE cx_vigencias (
                       codigo INTEGER PRIMARY KEY,
                       vigente INTEGER NOT NULL DEFAULT 0)""")
    con.execute("""CREATE TABLE cx_faixas (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       tabela INTEGER, vigencia INTEGER, de TEXT, ate TEXT,
                       codigo_tj TEXT, emolumentos TEXT, ferc TEXT, femp TEXT,
                       fadep TEXT, ferrfis TEXT, total TEXT)""")
    con.execute("""CREATE TABLE cx_servicos (
                       codigo INTEGER PRIMARY KEY, codigo_tj TEXT,
                       descricao TEXT, descricao_norm TEXT,
                       ativo INTEGER NOT NULL DEFAULT 1)""")
    con.execute("""CREATE TABLE cx_servico_valores (
                       servico INTEGER, vigencia INTEGER, emolumentos TEXT,
                       ferc TEXT, femp TEXT, fadep TEXT, ferrfis TEXT,
                       total TEXT)""")
    con.execute("INSERT INTO cx_vigencias (codigo, vigente) VALUES (10022, 1)")
    for tabela, faixa in ((EMOL.TABELA_RI_16_9, FAIXA_METADE),
                          (EMOL.TABELA_RI_16_9, FAIXA_CHEIA),
                          (EMOL.TABELA_RI, FAIXA_16_3)):
        codigo_tj, de, ate, emol, ferc, femp, fadep, ferrfis, total = faixa
        con.execute(
            """INSERT INTO cx_faixas (tabela, vigencia, de, ate, codigo_tj,
                                      emolumentos, ferc, femp, fadep, ferrfis,
                                      total)
               VALUES (?, 10022, ?,?,?,?,?,?,?,?,?)""",
            (tabela, de, ate, codigo_tj, emol, ferc, femp, fadep, ferrfis, total))
    con.execute(
        """INSERT INTO cx_servicos (codigo, codigo_tj, descricao,
                                    descricao_norm, ativo)
           VALUES (?,?,?,?,?)""",
        (SERVICO, CODIGO, descricao, EMOL._norm(descricao), ativo))
    con.execute(
        """INSERT INTO cx_servico_valores
               (servico, vigencia, emolumentos, ferc, femp, fadep, ferrfis, total)
           VALUES (?, 10022, '0,00','0,00','0,00','0,00','0,00','0,00')""",
        (SERVICO,))
    con.commit()
    return con


def test_a_lista_oficial_de_faixas_nao_mudou():
    """O atalho não entra em TABELAS_FAIXA: aquele mapa é o número interno
    da faixa (1 a 9), e misturar o 16.22.4.1 ali mudaria o seletor das outras."""
    assert list(EMOL.TABELAS_FAIXA) == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert EMOL.TABELAS_FAIXA[5].startswith("16.3 —")
    assert EMOL.TABELAS_FAIXA[6].startswith("16.9 —")
    assert all(CODIGO not in rotulo for rotulo in EMOL.TABELAS_FAIXA.values())
    assert set(EMOL.ATALHOS_NA_FAIXA) == {ATALHO}
    assert numero_digitado(ATALHO) is None
    assert EMOL.codigo_tj_do_atalho(ATALHO) == CODIGO
    assert EMOL.codigo_tj_do_atalho("5") is None
    assert EMOL.codigo_tj_do_atalho("tj:16.3") is None


def test_cem_mil_cai_na_16_9_com_metade_da_base():
    """R$ 100.000,00 de imóvel → base R$ 50.000,00 → 16.9.11, R$ 469,55.

    O código do item é o 16.22.4.1. O 16.9.11 é a faixa que deu o preço, e
    não o ato: o selo não conhece o subitem.
    """
    con = _tabela()
    item = EMOL.calcular_item(con, servico=SERVICO, base="100.000,00")
    assert item["codigo_tj"] == CODIGO
    assert item["origem_valor"] == "FAIXA_METADE_16.9"
    assert item["emolumentos"] == "419,24"
    assert item["ferc"] == "12,58"
    assert item["femp"] == "16,77"
    assert item["fadep"] == "16,77"
    assert item["ferrfis"] == "4,19"
    assert item["total"] == "469,55"
    assert item["base_calculo"] == "100.000,00"
    assert item["acima_do_teto"] is False
    assert "45.851,30" in item["faixa"]
    assert "57.314,07" in item["faixa"]
    assert item["descricao"].startswith(DESCRICAO)
    assert "tabela 16.9" in item["descricao"]
    assert item["total"] != "916,01"


def test_sem_descricao_no_cadastro_o_item_ainda_diz_o_que_e():
    """A faixa 16.9 não descreve esta averbação. Cadastro em branco não pode
    deixar o protocolo só com o parêntese da base."""
    con = _tabela(descricao="")
    item = EMOL.calcular_item(con, servico=SERVICO, base="100.000,00")
    assert item["descricao"].startswith(
        "Averbação de retificação de memorial descritivo")
    assert "SIGEF/INCRA" in item["descricao"]
    assert "tabela 16.9" in item["descricao"]


def test_as_outras_faixas_continuam_no_valor_cheio():
    """A 16.3 e a própria 16.9, escolhidas como faixa, não herdam o corte
    nem o código do 16.22.4.1."""
    con = _tabela()
    registro = EMOL.calcular_item(con, tabela=EMOL.TABELA_RI, base="100.000,00")
    assert registro["codigo_tj"] == "16.3.14"
    assert registro["origem_valor"] == "FAIXA"
    assert registro["emolumentos"] == "1.636,01"
    assert registro["total"] == "1.832,33"
    torrens = EMOL.calcular_item(con, tabela=EMOL.TABELA_RI_16_9, base="100.000,00")
    assert torrens["codigo_tj"] == "16.9.14"
    assert torrens["origem_valor"] == "FAIXA"
    assert torrens["emolumentos"] == "817,87"
    assert torrens["total"] == "916,01"


def test_o_atalho_acha_o_servico_ativo_da_vigencia():
    con = _tabela()
    assert EMOL.servico_pelo_codigo_tj(con, CODIGO) == SERVICO
    assert EMOL.servico_pelo_codigo_tj(con, "16.3") is None


def test_servico_inativo_nao_serve_para_o_atalho():
    con = _tabela(ativo=0)
    assert EMOL.servico_pelo_codigo_tj(con, CODIGO) is None


# ------------------------------------------------------------------- a tela


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _protocolo(banco, *, com_servico: bool = True) -> int:
    """Protocolo do balcão com a 16.9, a 16.3 e o serviço de total zero."""
    con = sqlite3.connect(str(banco))
    try:
        cur = con.execute(
            """INSERT INTO cx_protocolos (numero, data_abertura, interessado,
                                          situacao, criado_em)
               VALUES ('2026.10.162241', '2026-10-30', ?, 'ABERTO',
                       '2026-10-30T10:38:00')""",
            ("PESSOA DE TESTE",))
        protocolo_id = int(cur.lastrowid)
        con.execute("""INSERT INTO cx_vigencias (codigo, descricao, vigente,
                                                 servicos, faixas, importado_em)
                       VALUES (10022, 'Vigência de ensaio', 1, 0, 0,
                               '2026-10-30')""")
        for tabela, faixa in ((6, FAIXA_METADE), (6, FAIXA_CHEIA), (5, FAIXA_16_3)):
            codigo_tj, de, ate, emol, ferc, femp, fadep, ferrfis, total = faixa
            con.execute(
                """INSERT INTO cx_faixas (tabela, vigencia, de, ate, codigo_tj,
                                          emolumentos, ferc, femp, fadep,
                                          ferrfis, total)
                   VALUES (?, 10022, ?,?,?,?,?,?,?,?,?)""",
                (tabela, de, ate, codigo_tj, emol, ferc, femp, fadep, ferrfis,
                 total))
        if com_servico:
            con.execute(
                """INSERT INTO cx_servicos (codigo, codigo_tj, descricao,
                                            descricao_norm, ativo)
                   VALUES (?,?,?,?,1)""",
                (SERVICO, CODIGO, DESCRICAO, EMOL._norm(DESCRICAO)))
            con.execute(
                """INSERT INTO cx_servico_valores
                       (servico, vigencia, emolumentos, ferc, femp, fadep,
                        ferrfis, total)
                   VALUES (?, 10022, '0,00','0,00','0,00','0,00','0,00','0,00')""",
                (SERVICO,))
            # O vizinho de código tem preço fixo: a trava é do 16.22.4.1, não
            # de todo mundo que começa com 16.22.4.
            con.execute(
                """INSERT INTO cx_servicos (codigo, codigo_tj, descricao,
                                            descricao_norm, ativo)
                   VALUES (702, '16.22.4.2', ?, ?, 1)""",
                ("Averbação com fins de retificação",
                 EMOL._norm("Averbação com fins de retificação")))
            con.execute(
                """INSERT INTO cx_servico_valores
                       (servico, vigencia, emolumentos, ferc, femp, fadep,
                        ferrfis, total)
                   VALUES (702, 10022, '120,03','3,60','4,80','4,80','1,20',
                           '134,43')""")
        con.commit()
        return protocolo_id
    finally:
        con.close()


def _itens(banco, protocolo_id) -> list[dict]:
    con = sqlite3.connect(str(banco))
    con.row_factory = sqlite3.Row
    try:
        linhas = con.execute(
            """SELECT codigo_ato, descricao, quantidade, base_calculo,
                      emolumentos, valor_total, origem_valor, servico_codigo
               FROM cx_protocolo_atos WHERE protocolo_id=? ORDER BY id""",
            (protocolo_id,)).fetchall()
        return [dict(r) for r in linhas]
    finally:
        con.close()


def test_o_seletor_de_tabela_oferece_o_16_22_4_1(cg_casa_logada):
    protocolo_id = _protocolo(cg_casa_logada["banco"])
    html = cg_casa_logada["c"].get(
        f"/caixa/protocolos/{protocolo_id}").get_data(as_text=True)
    assert f'value="{ATALHO}"' in html
    assert "16.22.4.1 — Registro de Imóveis: averbação de retificação" in html
    assert 'value="5" selected' in html or 'value="5"  selected' in html
    assert f'value="{ATALHO}" selected' not in html
    assert "16.3 — Registro de Imóveis: registro com valor declarado" in html


def test_acrescentar_pela_tabela_grava_o_codigo_exato_e_o_preco(cg_casa_logada):
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo(banco)
    c = cg_casa_logada["c"]
    token = _token(c.get(f"/caixa/protocolos/{protocolo_id}").get_data(as_text=True))
    resposta = c.post(
        f"/caixa/protocolos/{protocolo_id}/itens",
        data={"acao": "acrescentar", "tabela": ATALHO,
              "base_calculo": "100.000,00", "csrf_token": token},
        follow_redirects=True).get_data(as_text=True)
    assert "469,55" in resposta
    assert CODIGO in resposta
    itens = _itens(banco, protocolo_id)
    assert len(itens) == 1
    item = itens[0]
    assert item["codigo_ato"] == CODIGO
    assert item["emolumentos"] == "419,24"
    assert item["valor_total"] == "469,55"
    assert item["origem_valor"] == "FAIXA_METADE_16.9"
    assert item["base_calculo"] == "100.000,00"
    assert item["quantidade"] == 1
    assert item["servico_codigo"] == SERVICO
    assert item["descricao"].startswith(DESCRICAO)
    assert "16.9.11" not in (item["codigo_ato"] or "")


def test_sem_valor_do_imovel_o_atalho_nao_grava(cg_casa_logada):
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo(banco)
    c = cg_casa_logada["c"]
    token = _token(c.get(f"/caixa/protocolos/{protocolo_id}").get_data(as_text=True))
    resposta = c.post(
        f"/caixa/protocolos/{protocolo_id}/itens",
        data={"acao": "acrescentar", "tabela": ATALHO, "csrf_token": token},
        follow_redirects=True).get_data(as_text=True)
    assert "valor do imóvel" in resposta
    assert _itens(banco, protocolo_id) == []


def test_valor_zero_nao_grava_o_item_de_graca(cg_casa_logada):
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo(banco)
    c = cg_casa_logada["c"]
    token = _token(c.get(f"/caixa/protocolos/{protocolo_id}").get_data(as_text=True))
    c.post(
        f"/caixa/protocolos/{protocolo_id}/itens",
        data={"acao": "acrescentar", "tabela": ATALHO,
              "base_calculo": "0,00", "csrf_token": token},
        follow_redirects=True)
    assert _itens(banco, protocolo_id) == []


def test_a_busca_nao_acrescenta_o_16_22_4_1_a_zero(cg_casa_logada):
    """Pela busca não há onde digitar o valor do imóvel. O botão some e, se
    o POST vier mesmo assim, o protocolo não ganha linha de R$ 0,00."""
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo(banco)
    c = cg_casa_logada["c"]
    html = c.get(
        f"/caixa/protocolos/{protocolo_id}?busca_ato={CODIGO}"
    ).get_data(as_text=True)
    assert "depende do valor do imóvel" in html
    assert f'name="servico" value="{SERVICO}"' not in html
    fragmento = c.get(
        f"/caixa/protocolos/{protocolo_id}/atos-da-tabela?busca={CODIGO}"
    ).get_data(as_text=True)
    assert "depende do valor do imóvel" in fragmento
    assert f'name="servico" value="{SERVICO}"' not in fragmento

    token = _token(html)
    resposta = c.post(
        f"/caixa/protocolos/{protocolo_id}/itens",
        data={"acao": "acrescentar", "servico": str(SERVICO),
              "csrf_token": token},
        follow_redirects=True).get_data(as_text=True)
    assert "caixa «Tabela»" in resposta
    assert _itens(banco, protocolo_id) == []


def test_o_vizinho_16_22_4_2_continua_na_busca(cg_casa_logada):
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo(banco)
    c = cg_casa_logada["c"]
    html = c.get(
        f"/caixa/protocolos/{protocolo_id}?busca_ato=16.22.4.2"
    ).get_data(as_text=True)
    assert 'name="servico" value="702"' in html
    assert "depende do valor do imóvel" not in html


def test_a_faixa_16_3_nao_foi_desviada(cg_casa_logada):
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo(banco)
    c = cg_casa_logada["c"]
    token = _token(c.get(f"/caixa/protocolos/{protocolo_id}").get_data(as_text=True))
    c.post(
        f"/caixa/protocolos/{protocolo_id}/itens",
        data={"acao": "acrescentar", "tabela": "5",
              "base_calculo": "100.000,00", "csrf_token": token},
        follow_redirects=True)
    itens = _itens(banco, protocolo_id)
    assert len(itens) == 1
    assert itens[0]["codigo_ato"] == "16.3.14"
    assert itens[0]["origem_valor"] == "FAIXA"
    assert itens[0]["emolumentos"] == "1.636,01"
    assert itens[0]["valor_total"] == "1.832,33"


def test_sem_o_servico_na_vigencia_o_atalho_avisa(cg_casa_logada):
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo(banco, com_servico=False)
    c = cg_casa_logada["c"]
    token = _token(c.get(f"/caixa/protocolos/{protocolo_id}").get_data(as_text=True))
    resposta = c.post(
        f"/caixa/protocolos/{protocolo_id}/itens",
        data={"acao": "acrescentar", "tabela": ATALHO,
              "base_calculo": "100.000,00", "csrf_token": token},
        follow_redirects=True).get_data(as_text=True)
    assert "Não encontrei o item 16.22.4.1" in resposta
    assert _itens(banco, protocolo_id) == []


def test_o_atalho_nao_divide_pelo_numero_de_imoveis(cg_casa_logada):
    """O campo «Imóveis» é o item 16.31, da garantia em vários imóveis. Esta
    averbação não é garantia: o valor da área entra inteiro e a metade é a
    da norma, não uma divisão por imóvel."""
    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo(banco)
    c = cg_casa_logada["c"]
    token = _token(c.get(f"/caixa/protocolos/{protocolo_id}").get_data(as_text=True))
    c.post(
        f"/caixa/protocolos/{protocolo_id}/itens",
        data={"acao": "acrescentar", "tabela": ATALHO,
              "base_calculo": "100.000,00", "imoveis": "2",
              "csrf_token": token},
        follow_redirects=True)
    itens = _itens(banco, protocolo_id)
    assert len(itens) == 1
    assert itens[0]["quantidade"] == 1
    assert itens[0]["valor_total"] == "469,55"
    assert itens[0]["base_calculo"] == "100.000,00"
