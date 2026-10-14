"""O relatório financeiro do gestor e o resumo da semana.

O QUE ESTES TESTES GUARDAM
    **Que as quatro coisas que o caixa mistura saem separadas**: dinheiro que
    entrou, receita, troco e gratuidade. Somadas, contariam o depósito duas
    vezes e o saldo inicial como receita — medido em setembro/2026.

    **Que o «nº» do uso do depósito é o id do depósito**, e não o número
    impresso: é o que amarra R$ 51 mil de setembro a alguma coisa.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import gestor_financeiro as GF                                   # noqa: E402
import gestor_rotina as GR                                       # noqa: E402

AGORA = "2026-09-20T10:00:00"
HOJE = date(2026, 10, 6)


@pytest.fixture()
def con(cg_casa):
    cg_casa["db"].create_user("jean", "MARIO EXEMPLO DOS SANTOS", "Senha#12345", "ADMIN")
    c = sqlite3.connect(cg_casa["banco"])
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _lan(con, valor, *, natureza="RECEBIMENTO", forma="PIX", desc="CERTIDÃO",
         emol=None, excluido=0, protocolo=None, origem="MANUAL", chave=None):
    con.execute(
        """INSERT INTO cx_lancamentos (data, natureza, sentido, forma_pagamento,
               descricao, valor, emolumentos, excluido, protocolo_id, origem,
               origem_chave, criado_em)
           VALUES ('2026-09-20', ?, 'ENTRADA', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (natureza, forma, desc, valor, emol, excluido, protocolo, origem, chave, AGORA))


def test_as_quatro_coisas_do_caixa_saem_separadas(con):
    _lan(con, "100,00")                                            # receita PIX
    _lan(con, "300,00", natureza="COMPLEMENTO", forma="DINHEIRO",
         desc="SALDO INICIAL")                                     # troco
    _lan(con, "0,00", forma=None, desc="AVERBACAO CPF", emol="38,72",
         origem="ATO", chave="rc_atos:1:679")                      # gratuidade
    _lan(con, "50,00", excluido=1)                                 # excluído
    dep = con.execute(
        """INSERT INTO cx_depositos (data, depositante, valor, saldo, criado_em)
           VALUES ('2026-09-11', 'FULANO', '27.442,16', '0,00', ?)""", (AGORA,)).lastrowid
    _lan(con, "27.442,16", forma="DEPOSITO_PREVIO",
         desc=f"Uso do depósito prévio nº {dep}")                  # receita, não entrada
    r = GF.apurar_mes(con, 2026, 9)
    assert r["troco"] == 300.0
    assert r["gratuitos"] == [1, 38.72]
    assert r["excluidos"] == [1, 50.0]
    assert sum(r["receita"].values()) == pytest.approx(27542.16)
    assert r["receita"]["uso de depósito prévio (o depósito não diz a atribuição)"] == \
        pytest.approx(27442.16)
    assert r["entrou"]["PIX"] == 100.0
    assert "DEPOSITO_PREVIO" not in " ".join(r["entrou"])           # uso não é entrada
    assert r["entrou"]["Depósitos prévios abertos (cadastro de depósitos)"] == \
        pytest.approx(27442.16)


def test_a_atribuicao_vem_do_protocolo_do_ato_ou_do_deposito(con):
    p = con.execute("""INSERT INTO cx_protocolos (numero, data_abertura, atribuicao, criado_em)
                       VALUES ('2026.09.1', '2026-09-20', 'RCPN', ?)""", (AGORA,)).lastrowid
    _lan(con, "53,58", protocolo=p)
    _lan(con, "6,92", desc="RECONHECIMENTO", origem="ATO", chave="nt_reconhecimentos:9:1")
    pd = con.execute("""INSERT INTO cx_protocolos (numero, data_abertura, atribuicao, criado_em)
                        VALUES ('2026.09.2', '2026-09-20', 'RI', ?)""", (AGORA,)).lastrowid
    dep = con.execute(
        """INSERT INTO cx_depositos (data, depositante, valor, saldo, protocolo_id, criado_em)
           VALUES ('2026-09-11', 'BELTRANO', '1.000,00', '0,00', ?, ?)""", (pd, AGORA)).lastrowid
    _lan(con, "1.000,00", forma="DEPOSITO_PREVIO", desc=f"Uso do depósito prévio nº {dep}")
    _lan(con, "10,00", desc="AVULSO")
    r = GF.apurar_mes(con, 2026, 9)["receita"]
    assert r == {"RCPN": 53.58, "Notas": 6.92, "RI": 1000.0, "sem identificação": 10.0}


def test_forma_gratuito_com_valor_e_incoerencia(con):
    _lan(con, "672,60", forma="GRATUITO", desc="ATA NOTARIAL")
    assert len(GF.apurar_mes(con, 2026, 9)["incoerentes"]) == 1


def test_fundos_e_isentos_saem_do_selo(con):
    for n, marca, total in (("CERTID000000AAAAAAAAAAAAAA01", "", "100,00"),
                            ("CERTID000000AAAAAAAAAAAAAA02", " Selo Isento", "50,00")):
        texto = (f"Poder Judiciário – TJMA. Selo: {n}, 20/09/2026 10:00:00, Ato: 14.5.1,"
                 f"{marca} Total R$ {total} Emol R$ 90,00 FERC R$ 3,00 FADEP R$ 4,00 "
                 "FEMP R$ 2,00 FERRFIS R$ 1,00 Consulte em https://selo.tjma.jus.br")
        con.execute("""INSERT INTO sd_selos (numero, texto, atribuicao, obtido_em, usado_em)
                       VALUES (?, ?, 'RCPN', ?, ?)""", (n, texto, AGORA, AGORA))
    s = GF.apurar_mes(con, 2026, 9)["selos"]
    assert s["qtd"] == 1 and s["total"] == 100.0
    assert s["fundos"] == {"FERC": 3.0, "FADP": 4.0, "FEMP": 2.0, "FERRFIS": 1.0}
    assert s["isentos"][0] == 1


def test_os_arquivos_saem_e_trazem_os_numeros(con, tmp_path):
    _lan(con, "1.234,50")
    GR.rodar(con, HOJE)
    feitos = GF.escrever(con, HOJE, tmp_path)
    nomes = sorted(p.name for p in feitos)
    assert nomes == ["financeiro_2026-09.html", "financeiro_2026-10.html",
                     "resumo_semana_2026-S41.html"]
    texto = (tmp_path / "financeiro_2026-09.html").read_text(encoding="utf-8")
    assert "R$ 1.234,50" in texto
    semana = (tmp_path / "resumo_semana_2026-S41.html").read_text(encoding="utf-8")
    assert "Resumo da semana" in semana


def test_primeiro_nome_do_caixa_vira_o_nome_do_cadastro(con):
    cg = con.execute("SELECT full_name FROM users WHERE username = 'jean'").fetchone()[0]
    assert GF._nome_do_operador(con, cg.split()[0].title()) == cg
    assert GF._nome_do_operador(con, "Fulano") == "Fulano"
    assert GF._nome_do_operador(con, "") == "sem caixa"


def test_ato_do_ri_acima_de_mil_diz_de_onde_veio_o_dinheiro(con):
    def selo(n, total, partes):
        texto = (f"Poder Judiciário – TJMA. Selo: {n}, 20/09/2026 10:00:00, Ato: 16.4.3,"
                 f" Total R$ {total} Emol R$ 900,00 FERC R$ 30,00 PARTE(S): {partes}, "
                 "Consulte em https://selo.tjma.jus.br")
        con.execute("""INSERT INTO sd_selos (numero, texto, atribuicao, tabela, ato_id,
                           obtido_em, usado_em) VALUES (?, ?, 'IMOVEL', 'ri_atos', 7, ?, ?)""",
                    (n, texto, AGORA, AGORA))
    selo("REGIST000000AAAAAAAAAAAAAA01", "5.000,00", "PEDRO ARRUDA DA SILVA")
    selo("REGIST000000AAAAAAAAAAAAAA02", "2.000,00", "MARIA SEM DEPOSITO")
    selo("REGIST000000AAAAAAAAAAAAAA03", "500,00", "PEQUENO")
    con.execute("""INSERT INTO cx_depositos (data, depositante, valor, saldo, criado_em)
                   VALUES ('2026-09-11', 'Pedro Arruda da Silva', '5.000,00', '0,00', ?)""",
                (AGORA,))
    altos = GF.apurar_mes(con, 2026, 9)["ri_altos"]
    assert [x["total"] for x in altos] == [5000.0, 2000.0]
    assert "Pedro" in altos[0]["de_onde"]
    assert altos[1]["de_onde"] == ""
    texto = GF.relatorio_financeiro_html(con, 2026, 9, HOJE)
    assert "acima de R$ 1.000" in texto and "não achado" in texto


def test_nome_cortado_no_selo_ainda_acha_o_deposito(con):
    texto = ("Poder Judiciário – TJMA. Selo: REGIST000000AAAAAAAAAAAAAA09, 24/09/2026 16:32:02,"
             " Ato: 16.4.3, Total R$ 10.920,44 Emol R$ 9.000,00 PARTE(S): JOÃO FALCAO DE SOUSA,"
             " MARIA RAIMUNDA LEMOS DE SOUSA, LEANDRO LEMOS D..., Consulte em https://selo.tjma.jus.br")
    con.execute("""INSERT INTO sd_selos (numero, texto, atribuicao, tabela, ato_id, obtido_em,
                       usado_em) VALUES ('REGIST000000AAAAAAAAAAAAAA09', ?, 'IMOVEL', 'ri_atos',
                       3755, ?, ?)""", (texto, AGORA, AGORA))
    con.execute("""INSERT INTO cx_depositos (numero, data, depositante, valor, saldo, criado_em)
                   VALUES ('DP2026.09.7', '2026-09-11', 'LEANDRO LEMOS DE SOUSA', '27.442,16',
                           '0,00', ?)""", (AGORA,))
    altos = GF.apurar_mes(con, 2026, 9)["ri_altos"]
    assert "DP2026.09.7" in altos[0]["de_onde"]


def test_uso_do_deposito_com_o_protocolo_na_descricao(con):
    dep = con.execute("""INSERT INTO cx_depositos (data, depositante, valor, saldo, criado_em)
                         VALUES ('2026-09-11', 'GEAN', '100,00', '0,00', ?)""", (AGORA,)).lastrowid
    lan = GF._com_o_deposito({"descricao": f"Uso do depósito prévio nº {dep} no protocolo 2026.08.146",
                              "p_atr": None},
                             {dep: (dep, 7, None, "RI")})
    assert lan["dep_id"] == dep and lan["dep_ri"] == 7 and lan["p_atr"] == "RI"
