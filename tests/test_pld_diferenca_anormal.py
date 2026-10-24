"""O PLD/COAF de 23/10/2026 — a diferença anormal, o Protesto e a rodada diária.

Pedido do oficial ao ler o que a seleção fazia e o que não fazia: «construir»,
com a régua dele — «diferença anormal seria acima de 50%». Três peças:

  1. a hipótese do art. 162, VI do CNN (c/c art. 172 nas Notas): preço
     declarado com diferença anormal em relação à avaliação ou à base de
     cálculo — a que a inspeção de 2026 cobrou e a seleção não tinha;
  2. o Protesto na seleção (art. 159): pagamento em espécie no balcão;
  3. a seleção na rodada diária, e o caso pendente no despacho do oficial —
     e NÃO em tarefa, por causa do sigilo do art. 154.

Os valores dos teores abaixo são de exemplo; a forma das frases é a dos
registros de compra e venda medidos nesta casa.
"""
from __future__ import annotations

import inspect
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import gestor_conferencia as GC   # noqa: E402
import gestor_rotina as GR        # noqa: E402
import pld_coaf as P              # noqa: E402
from banco_de_teste import conexao_de_teste  # noqa: E402

REGISTRO = ("COMPRA E VENDA. Nos termos da escritura pública de compra e venda, procedo "
            "ao presente registro para constar que o imóvel foi ADQUIRIDO por FULANO DE "
            "TAL, decorrente da compra feita a BELTRANO DE TAL, pelo preço de R$ {preco} "
            "({extenso}). Valor atribuído como base de cálculo de emolumentos em "
            "conformidade com códigos leis 16.27 e 16.27.1, da Lei Estadual nº 9.109/2009 "
            "(Tabela de custas e emolumentos), para fins de registro: R$ {base}.")


def _registro(preco, base):
    return REGISTRO.format(preco=preco, extenso="valor por extenso", base=base)


def _hipoteses(texto, atribuicao="RI", **kw):
    return [c["hipotese"] for c in P.casos_do_texto(atribuicao, "ri_atos", 1, "2026-10-01",
                                                    texto, tipo="R", **kw)]


# ------------------------------------------------------------- a diferença anormal

def test_preco_bem_abaixo_da_base_pede_analise():
    c = P.casos_do_texto("RI", "ri_atos", 1, "2026-10-01",
                         _registro("150.000,00", "600.000,00"), tipo="R")
    assert [x["hipotese"] for x in c] == ["VALOR_DIFERENCA_ANORMAL"]
    caso = c[0]
    assert caso["especie"] == P.ANALISE and caso["situacao"] == "A_ANALISAR"
    assert "art. 162, VI" in caso["fundamento"] and "art. 172" not in caso["fundamento"]
    assert caso["valor_centavos"] == 150_000_00
    assert "75% abaixo" in caso["descricao"] and "R$ 600.000,00" in caso["descricao"]
    # O trecho mostra de onde o preço saiu, para quem confere.
    assert "pelo preço de R$ 150.000,00" in caso["trecho"]


def test_ate_cinquenta_por_cento_nao_e_anormal():
    # 43% abaixo: dentro da régua do oficial.
    assert _hipoteses(_registro("85.500,00", "150.000,00")) == []
    # Exatamente 50%: «acima de 50%» não alcança os 50.
    assert _hipoteses(_registro("100.000,00", "200.000,00")) == []


def test_um_pouco_acima_de_cinquenta_por_cento_e_anormal():
    assert _hipoteses(_registro("97.000,00", "200.000,00")) == ["VALOR_DIFERENCA_ANORMAL"]


def test_preco_muito_acima_da_referencia_tambem_e_anormal():
    c = P.casos_do_texto("RI", "ri_atos", 1, "2026-10-01",
                         _registro("400.000,00", "100.000,00"), tipo="R")
    assert [x["hipotese"] for x in c] == ["VALOR_DIFERENCA_ANORMAL"]
    assert "300% acima" in c[0]["descricao"]


def test_preco_igual_a_base_nao_seleciona():
    # O caso comum: o preço É a base (não houve avaliação maior).
    assert _hipoteses(_registro("100.296,74", "100.296,74")) == []


def test_sem_referencia_nao_se_presume_nada():
    assert _hipoteses("COMPRA E VENDA pelo preço de R$ 90.000,00, pago por transferência.") == []


def test_sem_preco_nao_se_presume_nada():
    # Doação não tem preço: a hipótese da diferença não se aplica.
    assert "VALOR_DIFERENCA_ANORMAL" not in _hipoteses(
        "DOAÇÃO. Para fins de registro: R$ 300.000,00.")


def test_a_referencia_do_cadastro_vale_quando_o_teor_cala():
    texto = "COMPRA E VENDA pelo preço de R$ 50.000,00."
    assert _hipoteses(texto, referencia=200_000_00) == ["VALOR_DIFERENCA_ANORMAL"]


def test_o_preco_do_cadastro_vale_quando_existe():
    # Nas Notas o preço está em `valor_transacao`; o teor pode não dizer «preço».
    c = P.casos_do_texto("NOTAS", "nt_atos", 1, "2026-10-01",
                         "escritura de compra e venda; avaliado em R$ 500.000,00.",
                         tipo="ESCRITURA", preco=100_000_00)
    assert [x["hipotese"] for x in c] == ["VALOR_DIFERENCA_ANORMAL"]
    assert "art. 162, VI c/c art. 172" in c[0]["fundamento"]


def test_o_limite_e_a_regua_do_oficial():
    assert P.LIMITE_DIFERENCA_ANORMAL == 0.50
    assert P.diferenca_anormal(None, 100) is None
    assert P.diferenca_anormal(100, 0) is None


# ------------------------------------------------------------- a seleção, com o banco

@pytest.fixture()
def con():
    c = conexao_de_teste()
    c.executescript("""
        CREATE TABLE ri_matriculas (id INTEGER PRIMARY KEY, numero TEXT);
        CREATE TABLE ri_atos (id INTEGER PRIMARY KEY, matricula_id INTEGER, tipo TEXT,
            numero INTEGER, data_ato TEXT, teor TEXT, base_calculo_centavos INTEGER,
            cancelado INTEGER DEFAULT 0);
        CREATE TABLE ri_partes (id INTEGER PRIMARY KEY, ato_id INTEGER, nome TEXT,
            documento_numero TEXT, qualificacao TEXT, papel TEXT);
        CREATE TABLE pt_titulos (id INTEGER PRIMARY KEY, numero_titulo TEXT,
            protocolo TEXT, valor_centavos INTEGER, apresentante_nome TEXT);
        CREATE TABLE pt_devedores (id INTEGER PRIMARY KEY, titulo_id INTEGER, nome TEXT,
            documento_numero TEXT);
        CREATE TABLE pt_atos (id INTEGER PRIMARY KEY, titulo_id INTEGER, tipo TEXT,
            data_ato TEXT, detalhe_json TEXT, cancelado INTEGER DEFAULT 0);
    """)
    c.execute("INSERT INTO ri_matriculas VALUES (1, '9001')")
    c.execute("INSERT INTO ri_atos VALUES (1, 1, 'R', 2, '2026-10-01', ?, 60000000, 0)",
              (_registro("150.000,00", "600.000,00"),))
    c.execute("INSERT INTO ri_partes VALUES (1, 1, 'FULANO DE TAL', '000', 'comprador', "
              "'adquirente')")
    c.execute("INSERT INTO pt_titulos VALUES (1, 'NF-1', '2610010001', 15000000, "
              "'CREDORA EXEMPLO')")
    c.execute("INSERT INTO pt_titulos VALUES (2, 'NF-2', '2610010002', 15000000, "
              "'CREDORA EXEMPLO')")
    c.execute("INSERT INTO pt_titulos VALUES (3, 'NF-3', '2610010003', 5000000, "
              "'CREDORA EXEMPLO')")
    c.execute("INSERT INTO pt_devedores VALUES (1, 1, 'DEVEDOR EXEMPLO', '111')")
    # Espécie de R$ 150 mil: entra. PIX do mesmo valor: não. Espécie de R$ 50 mil: não.
    c.execute("""INSERT INTO pt_atos VALUES (1, 1, 'PAGAMENTO', '2026-10-02',
                 '{"valor_pago_centavos": 15000000, "forma_pagamento": "ESPECIE"}', 0)""")
    c.execute("""INSERT INTO pt_atos VALUES (2, 2, 'PAGAMENTO', '2026-10-02',
                 '{"valor_pago_centavos": 15000000, "forma_pagamento": "PIX"}', 0)""")
    c.execute("""INSERT INTO pt_atos VALUES (3, 3, 'PAGAMENTO', '2026-10-02',
                 '{"valor_pago_centavos": 5000000, "forma_pagamento": "ESPECIE"}', 0)""")
    c.commit()
    return c


def test_selecao_acha_o_registro_e_o_pagamento_em_especie(con):
    r = P.selecionar(con, desde="2026-01-01")
    assert r["novos"] == 2
    por_tabela = {(c["tabela"], c["hipotese"]) for c in P.casos(con)}
    assert por_tabela == {("ri_atos", "VALOR_DIFERENCA_ANORMAL"),
                          ("pt_atos", "ESPECIE_100MIL")}
    protesto = [c for c in P.casos(con) if c["tabela"] == "pt_atos"][0]
    assert protesto["atribuicao"] == "PROTESTO" and protesto["ato_id"] == 1
    assert protesto["situacao"] == "A_COMUNICAR" and "art. 159" in protesto["fundamento"]
    # Idempotente, como antes.
    assert P.selecionar(con, desde="2026-01-01")["novos"] == 0


def test_a_comunicacao_do_protesto_traz_o_titulo_e_o_devedor(con):
    P.selecionar(con, desde="2026-01-01")
    caso = [c for c in P.casos(con) if c["tabela"] == "pt_atos"][0]
    texto = P.montar_comunicacao(con, caso["id"])
    assert "título NF-1" in texto and "DEVEDOR EXEMPLO" in texto
    assert "R$ 150.000,00" in texto


# ------------------------------------------------------------- a rodada e o sigilo

def test_a_conferencia_avisa_o_caso_perto_do_prazo_sem_nome(con):
    P.selecionar(con, desde="2026-01-01")
    # Espécie: 30 dias da operação (02/10 → 01/11). Análise: 60 (01/10 → 30/11).
    achados = GC.regra_pld(con, date(2026, 10, 25))
    assert [a["regra"] for a in achados] == ["PLD_COAF"]
    a = achados[0]
    assert a["setor"] == "GESTAO" and a["gravidade"] == "PRAZO"
    assert a["prazo"] == "2026-11-01"
    texto = a["titulo"] + a["detalhe"]
    assert "DEVEDOR EXEMPLO" not in texto and "FULANO" not in texto
    # Vencido o da análise também aparece.
    hipoteses = {x["chave"] for x in GC.regra_pld(con, date(2026, 12, 5))}
    assert len(hipoteses) == 2


def test_a_conferencia_nao_escreve_e_respeita_o_corte(con):
    P.selecionar(con, desde="2026-01-01")
    con.execute("UPDATE pld_casos SET data_operacao='2026-09-01'")
    assert GC.regra_pld(con, date(2026, 9, 20)) == []
    # Sem a tabela (instalação sem PLD), nada — e nada é criado.
    limpo = conexao_de_teste()
    assert GC.regra_pld(limpo, date(2026, 10, 25)) == []


def test_o_caso_do_pld_nao_vira_tarefa_e_esta_na_conferencia():
    assert "PLD_COAF" in GR.REGRAS_SEM_TAREFA
    assert ("PLD_COAF", GC.regra_pld) in GC.REGRAS
    assert "PLD_COAF" in GR.ROTULOS


def test_a_rodada_diaria_seleciona_antes_da_conferencia():
    fonte = inspect.getsource(GR.rodada_diaria)
    assert fonte.index("pld_coaf.selecionar") < fonte.index("resumo = rodar(")
