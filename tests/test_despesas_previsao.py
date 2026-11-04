"""O MÊS ATÉ AGORA E A PREVISÃO — o quadro do oficial na tela das despesas.

Pedido do oficial (31/10/2026): simular o livro-caixa do mês até aquele momento e prever os
gastos até o fim dele, com carnê-leão, fundos e recorrentes.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import despesas as DP
import despesas_previsao as DV
import despesas_recorrentes as RC
from tests.conftest import cg_login

AGORA = datetime(2026, 11, 3, 9, 0, tzinfo=timezone(timedelta(hours=-3)))
HOJE = AGORA.date()
CPF = "00000000191"
LISTA = "/administrativo/despesas"
RECORRENTE = {"descricao": "Folha de pagamento, salário líquido", "categoria": "PESSOAL",
              "beneficiario_nome": "BEATRIZ EXEMPLO", "beneficiario_documento": CPF,
              "forma": DP.PIX_CHAVE, "chave_pix": "beatriz@example.com", "valor": 100000,
              "dia_vencimento": 30, "antecedencia_dias": 5, "documento_especie": "Recibo",
              "primeiro_mes": "2026-11"}


def _manual(con, valor, categoria="MATERIAIS", vencimento="2026-11-20"):
    return DP.cadastrar(con, agora=AGORA, por="mario", origem="MANUAL", chave_origem=None,
                        beneficiario_nome="BEATRIZ EXEMPLO", beneficiario_documento="", valor_centavos=valor,
                        vencimento=vencimento, forma=DP.MANUAL, codigo="", descricao="Despesa de exemplo do mês",
                        categoria=categoria, documento_especie="Recibo")


def _linha(quadro, comeco):
    return next(x for x in quadro["linhas"] if x["rotulo"].startswith(comeco))


def test_os_dias_uteis_de_novembro_tiram_o_feriado():
    assert DV.ritmo_dos_dias_uteis(date(2026, 11, 3))[0] == 1, "o dia 2 é Finados"
    assert DV.ritmo_dos_dias_uteis(date(2026, 11, 1))[0] == 1, "nunca divide por zero"


def test_classificacao_pendente_nao_vira_sugestao_de_darf(cg_casa_logada, monkeypatch):
    monkeypatch.setattr(DV.CL, 'apurar', lambda c, comp: {
        'receita': 1000000, 'imposto': 184127, 'a_classificar': 1100000, 'outras_entradas': []})
    with cg_casa_logada['db'].connect() as con:
        q = DV.quadro_do_mes(con, HOJE)
        assert q['darf']['pendente'] and not q['darf']['falta_cadastrar']
        assert _linha(q, 'Carnê-leão')['valor'] == 0
        assert 'incompleta' in _linha(q, 'Carnê-leão')['nota']
        with pytest.raises(DP.DespesaError, match='incompleta'):
            DV.formulario_do_darf(con, '2026-10')
    html = cg_casa_logada['c'].get('/administrativo/despesas').get_data(as_text=True)
    assert 'apuração de 10/2026 incompleta' in html and 'Cadastrar o DARF' not in html


def test_outra_entrada_pendente_tambem_exige_conferencia(cg_casa_logada, monkeypatch):
    monkeypatch.setattr(DV.CL, 'apurar', lambda c, comp: {'imposto': 10000, 'outras_entradas': [{'valor': 100}]})
    with cg_casa_logada['db'].connect() as con:
        with pytest.raises(DP.DespesaError, match='incompleta'):
            DV.formulario_do_darf(con, '2026-10')


def test_a_projecao_segue_o_ritmo_e_no_ultimo_dia_e_o_proprio_valor():
    assert DV.projetar(10000, 5, 20) == 40000
    assert DV.projetar(10000, 20, 20) == 10000
    assert DV.projetar(0, 1, 20) == 0


def test_a_recorrente_entra_antes_de_o_aviso_abrir_e_sai_quando_carrega(cg_casa_logada):
    with cg_casa_logada["db"].transaction() as con:
        RC.cadastrar(con, RECORRENTE, por="mario", agora=AGORA)
        assert RC.do_mes(con, HOJE) == [], "o aviso ainda não abriu"
        assert DV.recorrentes_que_faltam(con, HOJE)["total"] == 100000
        RC.gerar(con, hoje=date(2026, 11, 28), agora=AGORA, por="automação")
        assert DV.recorrentes_que_faltam(con, HOJE)["total"] == 0


def test_a_de_valor_variavel_entra_pelo_ultimo_pago_e_a_nova_so_se_conta(cg_casa_logada):
    variavel = {**RECORRENTE, "descricao": "Energia elétrica do prédio", "categoria": "CONCESSIONARIAS",
                "forma": DP.BOLETO, "chave_pix": "", "valor": 0, "primeiro_mes": "2026-10"}
    with cg_casa_logada["db"].transaction() as con:
        rid = RC.cadastrar(con, variavel, por="mario", agora=AGORA - timedelta(days=60))
        assert DV.recorrentes_que_faltam(con, HOJE)["sem_valor"] == 1
        DP.banco(con).escrever(
            "INSERT INTO dp_despesas (situacao, natureza, categoria, descricao, beneficiario_nome, valor, vencimento, "
            "forma, documento_especie, origem, chave_origem, cadastrada_em, cadastrada_por) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (DP.CONCILIADA, DP.DESPESA, "CONCESSIONARIAS", "Energia de outubro", "DISTRIBUIDORA", 45000, "2026-10-30",
             DP.BOLETO, "Fatura", RC.ORIGEM, f"{rid}:2026-10", "2026-10-01T09:00:00", "mario"))
        faltam = DV.recorrentes_que_faltam(con, HOJE)
    assert (faltam["total"], faltam["estimadas"], faltam["sem_valor"]) == (45000, 1, 0)


def test_o_quadro_soma_o_que_falta_e_o_carne_leao_e_o_do_mes_anterior(cg_casa_logada, monkeypatch):
    meses = []

    def _apurar(con, comp):
        meses.append(comp)
        return {"receita": 500000, "imposto": 80000} if comp == "2026-11" else {"receita": 0, "imposto": 50000}

    monkeypatch.setattr(DV.CL, "apurar", _apurar)
    with cg_casa_logada["db"].transaction() as con:
        RC.cadastrar(con, RECORRENTE, por="mario", agora=AGORA)
        _manual(con, 30000)
        _manual(con, 20000, categoria="CARNE_LEAO")
        quadro = DV.quadro_do_mes(con, HOJE)
    assert set(meses) == {"2026-11", "2026-10"}
    assert _linha(quadro, "Despesas cadastradas")["valor"] == 50000
    assert _linha(quadro, "Recorrentes")["valor"] == 100000
    assert _linha(quadro, "Carnê-leão de 10/2026")["valor"] == 30000, "o DARF cadastrado não conta duas vezes"
    assert quadro["falta_sair"] == 180000 and quadro["previsao"] == 180000
    assert (quadro["saldo"], quadro["sobra"]) == (500000, 320000)
    assert quadro["imposto_do_mes"] == 80000, "o de novembro só se mostra"


def test_sem_tabela_progressiva_a_tela_diz_em_vez_de_mostrar_imposto(cg_casa_logada, monkeypatch):
    monkeypatch.setattr(DV.CL, "apurar", lambda con, comp: {"receita": 0, "imposto": None})
    with cg_casa_logada["db"].connect() as con:
        linha = _linha(DV.quadro_do_mes(con, HOJE), "Carnê-leão")
    assert linha["valor"] == 0 and "não foi calculado" in linha["nota"]


def test_a_despesa_cancelada_e_a_de_outro_mes_nao_entram(cg_casa_logada, monkeypatch):
    monkeypatch.setattr(DV.CL, "apurar", lambda con, comp: {"receita": 0, "imposto": None})
    with cg_casa_logada["db"].transaction() as con:
        i = _manual(con, 30000)
        DP.cancelar(con, i, agora=AGORA, por="mario", papel="ADMIN", motivo="Cadastrada por engano")
        _manual(con, 70000, vencimento="2026-12-10")
        assert _linha(DV.quadro_do_mes(con, HOJE), "Despesas cadastradas")["valor"] == 0


def test_a_vencida_que_ficou_para_tras_entra(cg_casa_logada, monkeypatch):
    monkeypatch.setattr(DV.CL, "apurar", lambda con, comp: {"receita": 0, "imposto": None})
    with cg_casa_logada["db"].transaction() as con:
        _manual(con, 30000, vencimento="2026-10-15")
        assert _linha(DV.quadro_do_mes(con, HOJE), "Despesas cadastradas")["valor"] == 30000


def test_so_o_oficial_ve_o_quadro(cg_casa_logada):
    casa = cg_casa_logada
    assert "O mês até agora" in casa["c"].get(LISTA).get_data(as_text=True)
    casa["db"].create_user("gerente", "GERENTE EXEMPLO", "Senha#12345", "MANAGER")
    c = casa["app"].test_client()
    cg_login(c, "gerente", "Senha#12345")
    assert "O mês até agora" not in c.get(LISTA).get_data(as_text=True)


def test_o_quadro_que_quebra_nao_derruba_a_tela(cg_casa_logada, monkeypatch):
    def _quebra(con, hoje):
        raise RuntimeError("conta quebrada")

    monkeypatch.setattr(DV, "quadro_do_mes", _quebra)
    r = cg_casa_logada["c"].get(LISTA)
    assert r.status_code == 200 and "não pôde ser calculado" in r.get_data(as_text=True)


def test_o_darf_vem_preenchido_com_o_valor_e_o_vencimento_do_mes_seguinte(cg_casa_logada, monkeypatch):
    monkeypatch.setattr(DV.CL, "apurar", lambda con, comp: {"receita": 0, "imposto": 123456})
    with cg_casa_logada["db"].connect() as con:
        f = DV.formulario_do_darf(con, "2026-10")
    assert (f["categoria"], f["valor"], f["forma"]) == ("CARNE_LEAO", "1.234,56", DP.ARRECADACAO)
    assert f["vencimento"] == "2026-11-30", "o último dia útil de novembro"
    assert "10/2026" in f["descricao"]
    tela = cg_casa_logada["c"].get("/administrativo/despesas/nova?carne_leao=2026-10").get_data(as_text=True)
    assert "1.234,56" in tela and "Carnê-Leão Web" in tela


def test_dezembro_vence_em_janeiro():
    assert DV.OO._ultimo_dia_util(2027, 1) == date(2027, 1, 29)


def test_sem_tabela_ou_sem_imposto_nao_ha_darf(cg_casa_logada, monkeypatch):
    with cg_casa_logada["db"].connect() as con:
        monkeypatch.setattr(DV.CL, "apurar", lambda c, comp: {"imposto": None})
        with pytest.raises(DP.DespesaError, match="tabela progressiva"):
            DV.formulario_do_darf(con, "2026-10")
        monkeypatch.setattr(DV.CL, "apurar", lambda c, comp: {"imposto": 0})
        with pytest.raises(DP.DespesaError, match="não dá imposto"):
            DV.formulario_do_darf(con, "2026-10")
        with pytest.raises(DP.DespesaError):
            DV.formulario_do_darf(con, "mês torto")


def test_o_aviso_some_quando_o_darf_esta_cadastrado(cg_casa_logada, monkeypatch):
    monkeypatch.setattr(DV.CL, "apurar", lambda c, comp: {"receita": 0, "imposto": 50000})
    with cg_casa_logada["db"].transaction() as con:
        assert DV.quadro_do_mes(con, HOJE)["darf"]["falta_cadastrar"] is True
        _manual(con, 50000, categoria="CARNE_LEAO")
        assert DV.quadro_do_mes(con, HOJE)["darf"]["falta_cadastrar"] is False


def test_o_darf_pago_fica_fora_do_relatorio_da_serventia(cg_casa_logada):
    with cg_casa_logada["db"].transaction() as con:
        i = _manual(con, 50000, categoria="CARNE_LEAO", vencimento="2026-11-20")
        DP.registrar_pago_fora(con, i, agora=AGORA, hoje="2026-11-03", por="mario", papel="ADMIN",
                               data_pagamento="2026-11-03")
        assert DP.despesa(con, i)["ld_despesa_id"] is None, "não vai ao Livro Diário"
        assert DP.relatorio_do_mes(con, "2026-11")["linhas"] == []


def test_quem_nao_e_o_titular_nao_ve_o_imposto_no_formulario(cg_casa_logada, monkeypatch):
    monkeypatch.setattr(DV.CL, "apurar", lambda c, comp: {"imposto": 123456})
    casa = cg_casa_logada
    casa["db"].create_user("gerente", "GERENTE EXEMPLO", "Senha#12345", "MANAGER")
    c = casa["app"].test_client()
    cg_login(c, "gerente", "Senha#12345")
    assert "1.234,56" not in c.get("/administrativo/despesas/nova?carne_leao=2026-10").get_data(as_text=True)


def _livro_de(valores):
    return lambda con, comp: {"despesas": 0, "fundos": {}, "receita_bruta": valores.get(comp, 0)}


def test_o_iss_preliminar_e_a_aliquota_sobre_o_selo():
    assert DV.iss_preliminar(8260443, 500) == 413022
    assert DV.iss_preliminar(8260443, 200) == 165209, "cada município tem a sua"
    assert DV.iss_preliminar(0, 500) == 0


def test_a_aliquota_nasce_em_5_e_se_troca_na_configuracao(cg_casa_logada, monkeypatch):
    monkeypatch.setattr(DV.CL, "apurar", lambda c, comp: {"receita": 0, "imposto": None})
    monkeypatch.setattr(DV.LD, "apurar", _livro_de({"2026-10": 1000000}))
    with cg_casa_logada["db"].transaction() as con:
        assert DV.aliquota_do_iss(con) == 500
        DP.gravar_configuracao(con, {**DP.configuracao(con), "despesas_aliquota_iss": "2,5"})
        q = DV.quadro_do_mes(con, HOJE)
        assert DV.aliquota_do_iss(con) == 250
    assert _linha(q, "ISS de 10/2026")["valor"] == 25000 and "2,50%" in _linha(q, "ISS de 10/2026")["nota"]


def test_a_aliquota_fora_da_faixa_e_recusada(cg_casa_logada):
    with cg_casa_logada["db"].transaction() as con:
        for torta in ("0", "101"):
            with pytest.raises(DP.DespesaError, match="percentual entre"):
                DP.gravar_configuracao(con, {**DP.configuracao(con), "despesas_aliquota_iss": torta})


def test_o_iss_do_mes_anterior_entra_na_previsao_e_o_deste_mes_so_se_mostra(cg_casa_logada, monkeypatch):
    monkeypatch.setattr(DV.CL, "apurar", lambda c, comp: {"receita": 0, "imposto": None})
    monkeypatch.setattr(DV.LD, "apurar", _livro_de({"2026-10": 1000000, "2026-11": 200000}))
    with cg_casa_logada["db"].connect() as con:
        q = DV.quadro_do_mes(con, HOJE)
    assert _linha(q, "ISS de 10/2026")["valor"] == 50000
    assert "preliminar" in _linha(q, "ISS de 10/2026")["rotulo"] and "o da guia" in _linha(q, "ISS de 10/2026")["nota"]
    assert (q["iss"]["do_mes"], q["iss"]["falta_cadastrar"]) == (10000, True)
    assert q["falta_sair"] == 50000


def test_a_guia_cadastrada_tira_o_iss_da_conta_sem_contar_duas_vezes(cg_casa_logada, monkeypatch):
    monkeypatch.setattr(DV.CL, "apurar", lambda c, comp: {"receita": 0, "imposto": None})
    monkeypatch.setattr(DV.LD, "apurar", _livro_de({"2026-10": 1000000}))
    with cg_casa_logada["db"].transaction() as con:
        _manual(con, 62000, categoria="ISS")
        q = DV.quadro_do_mes(con, HOJE)
    assert _linha(q, "ISS de 10/2026")["valor"] == 0 and q["iss"]["falta_cadastrar"] is False
    assert q["falta_sair"] == 62000, "vale o valor da guia, e não a estimativa"


def test_a_guia_vem_preenchida_sem_vencimento_e_so_para_o_titular(cg_casa_logada, monkeypatch):
    monkeypatch.setattr(DV.LD, "apurar", _livro_de({"2026-10": 1000000}))
    casa = cg_casa_logada
    with casa["db"].connect() as con:
        f = DV.formulario_do_iss(con, "2026-10", municipio="Exemplo")
        with pytest.raises(DP.DespesaError, match="não dão ISS"):
            DV.formulario_do_iss(con, "2026-09", municipio="Exemplo")
    assert (f["categoria"], f["valor"], f["beneficiario_nome"]) == ("ISS", "500,00", "Município de Exemplo")
    assert "vencimento" not in f
    assert "500,00" in casa["c"].get("/administrativo/despesas/nova?iss=2026-10").get_data(as_text=True)
    casa["db"].create_user("gerente", "GERENTE EXEMPLO", "Senha#12345", "MANAGER")
    c = casa["app"].test_client()
    cg_login(c, "gerente", "Senha#12345")
    assert "500,00" not in c.get("/administrativo/despesas/nova?iss=2026-10").get_data(as_text=True)
