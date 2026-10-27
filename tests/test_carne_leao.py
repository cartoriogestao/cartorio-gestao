"""O CARNÊ-LEÃO E O LIVRO-CAIXA DO TITULAR — regime de caixa, dedutíveis e a tabela.

A TABELA DA MAIOR PARTE DESTES TESTES É FICTÍCIA, de propósito: faixas
redondas (até 1.000 isento; até 2.000 a 10% menos 100; acima, 20% menos 300)
que ninguém confunde com a da Receita. A NACIONAL (`TABELAS_NACIONAIS`, ordem do
oficial de 26/10/2026) tem teste próprio, contra o exemplo da Receita.

As respostas do oficial de 26/10/2026 têm teste cada uma: depósito só no ato,
prazo no último dia do mês seguinte, excesso levado até dezembro, «outra
entrada» respondida por quem lança, e os fundos tirados pela configuração.

Pessoas e documentos fictícios (mario, beatriz, carla).
"""
from __future__ import annotations

import csv as _csv
import io
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import caixa_depositos as DEP  # noqa: E402
import carne_leao as CL  # noqa: E402
import despesas as DP  # noqa: E402
import livro_diario as LD  # noqa: E402
import oficial_obrigacoes as OO  # noqa: E402
from bd_nativo import banco  # noqa: E402
from conftest import cg_login  # noqa: E402

HOJE = "2026-10-26"
AGORA = "2026-10-26T10:00:00"
FAIXAS_FICTICIAS = "1.000,00; 0; 0\n2.000,00; 10; 100,00\n; 20; 300,00"
FONTE = "Tabela fictícia do teste, sem valor de verdade nenhum"
FUSO = timezone(timedelta(hours=-3))


@pytest.fixture
def casa(cg_casa_logada):
    return cg_casa_logada


def _tabela(db, vigencia="2026-01-01", faixas=FAIXAS_FICTICIAS, descricao="Fictícia A"):
    with db.transaction() as con:
        return CL.cadastrar_tabela(con, vigencia_inicio=vigencia, descricao=descricao,
                                   fonte=FONTE, faixas_texto=faixas, por="mario", agora=AGORA)


def _lancamento(db, dia, valor, *, natureza="RECEBIMENTO", forma="DINHEIRO",
                descricao="Certidão", emolumentos=None, ferc=None, estornado=0,
                sentido="ENTRADA", receita_do_titular=None):
    with db.transaction() as con:
        return banco(con).escrever(
            """INSERT INTO cx_lancamentos (data, natureza, sentido, forma_pagamento,
                   descricao, valor, emolumentos, ferc, estornado, criado_em,
                   receita_do_titular)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (dia, natureza, sentido, forma, descricao, valor, emolumentos, ferc,
             estornado, AGORA, receita_do_titular))[0]["id"]


def _despesa_ld(db, dia, valor, descricao="Energia elétrica da serventia"):
    with db.transaction() as con:
        return LD.lancar_despesa(con, hoje=HOJE, agora=AGORA, por="mario", data=dia,
                                 descricao=descricao, documento_especie="Fatura",
                                 valor=valor, documento_numero="1")


def _apurar(db, comp):
    with db.connect() as con:
        return CL.apurar(con, comp)


# ------------------------------------------------------- a tabela progressiva

def test_a_tabela_ficticia_calcula_faixa_a_faixa():
    faixas = CL.ler_faixas(FAIXAS_FICTICIAS)
    assert [f["aliquota_bp"] for f in faixas] == [0, 1000, 2000]
    assert CL.calcular_imposto(90000, faixas)["imposto"] == 0          # isento
    assert CL.calcular_imposto(150000, faixas)["imposto"] == 5000      # 150 - 100
    r = CL.calcular_imposto(300000, faixas)                             # 600 - 300
    assert (r["faixa"], r["imposto"]) == (3, 30000)
    # Arredondamento meio para cima, ao centavo: 1.000,05 × 10% = 100,005.
    assert CL.calcular_imposto(100005, faixas)["imposto"] == 1          # 100,01 - 100
    assert CL.calcular_imposto(-5, faixas)["imposto"] == 0


@pytest.mark.parametrize("texto, trecho", [
    ("", "ao menos uma faixa"),
    ("1.000,00; 0; 0\n2.000,00; 10; 100,00", "última faixa"),
    ("; 0; 0\n2.000,00; 10; 100,00", "só a última"),
    ("2.000,00; 0; 0\n1.000,00; 10; 0\n; 20; 0", "maior que o da anterior"),
    ("1.000,00; dez; 0\n; 20; 0", "Alíquota ilegível"),
    ("1.000,00; 0\n; 20; 0", "Linha 1"),
])
def test_faixa_mal_escrita_e_recusada(texto, trecho):
    with pytest.raises(CL.CarneLeaoError, match=trecho):
        CL.ler_faixas(texto)


def test_tabela_sem_fonte_nao_entra_e_vigencia_repetida_pede_anular(casa):
    db = casa["db"]
    with db.transaction() as con, pytest.raises(CL.CarneLeaoError, match="de onde vem"):
        CL.cadastrar_tabela(con, vigencia_inicio="2026-01-01", descricao="Fictícia",
                            fonte="", faixas_texto=FAIXAS_FICTICIAS, por="mario", agora=AGORA)
    primeira = _tabela(db)
    with pytest.raises(CL.CarneLeaoError, match="Anule a anterior"):
        _tabela(db)
    with db.transaction() as con:
        CL.anular_tabela(con, primeira, motivo="Faixa digitada errada no cadastro",
                         por="mario", agora=AGORA)
    _tabela(db, descricao="Fictícia B")
    with db.connect() as con:
        lista = CL.tabelas(con)
    assert [t["descricao"] for t in lista if not t["anulada_em"]] == ["Fictícia B"]
    assert any(t["anulada_em"] for t in lista)          # a anulada fica


def test_sem_tabela_nao_ha_imposto_e_a_tela_diz(casa):
    a = _apurar(casa["db"], "2026-09")
    assert a["imposto"] is None and a["tabela"] is None
    assert any("tabela progressiva" in x for x in a["avisos"])


def test_vale_a_tabela_do_dia_primeiro_e_a_do_meio_do_mes_avisa(casa):
    db = casa["db"]
    _tabela(db, vigencia="2026-01-01", descricao="Fictícia A")
    _tabela(db, vigencia="2026-09-15", faixas="; 50; 0", descricao="Fictícia B")
    _lancamento(db, "2026-09-10", "1.500,00", emolumentos="1.500,00")
    setembro = _apurar(db, "2026-09")
    assert setembro["tabela"]["descricao"] == "Fictícia A" and setembro["imposto"] == 5000
    assert any("meio do mês" in x for x in setembro["avisos"])
    assert _apurar(db, "2026-10")["tabela"]["descricao"] == "Fictícia B"


# ------------------------------------------------------- a receita do mês

def test_a_receita_do_caixa_e_so_o_emolumento_e_deixa_de_fora_o_que_nao_e_receita(casa):
    db = casa["db"]
    _lancamento(db, "2026-09-02", "130,00", emolumentos="100,00", ferc="30,00")
    _lancamento(db, "2026-09-03", "50,00", ferc="10,00")              # emolumento = 40
    _lancamento(db, "2026-09-04", "80,00")         # sem separação: 80 ÷ 1,12 = 71,43
    _lancamento(db, "2026-09-05", "999,00", forma="DEPOSITO_PREVIO",
                descricao="Uso do depósito prévio nº 1")              # entrou antes
    _lancamento(db, "2026-09-05", "777,00", estornado=1)              # estornado
    _lancamento(db, "2026-09-06", "200,00", descricao="SALDO INICIAL do caixa")
    _lancamento(db, "2026-09-07", "0,00", emolumentos="25,00")        # gratuidade
    _lancamento(db, "2026-09-08", "60,00", natureza="OUTRA_ENTRADA",
                descricao="Ressarcimento a identificar")
    _lancamento(db, "2026-09-09", "300,00", natureza="DEPOSITO_PREVIO",
                descricao="Depósito prévio nº DP2026.09.1")         # o livro dele conta
    _lancamento(db, "2026-10-01", "1.000,00", emolumentos="1.000,00")  # outro mês
    a = _apurar(db, "2026-09")
    assert a["caixa"] == 10000 + 4000 + 7143
    assert a["sem_discriminacao"] == 8000 and a["fundos_estimados"] == 857
    assert [o["valor"] for o in a["outras_entradas"]] == [6000]
    assert any("sem a separação dos fundos" in x for x in a["avisos"])
    assert any("outra entrada" in x for x in a["avisos"])


def test_o_deposito_previo_so_vira_receita_quando_o_ato_e_praticado(casa):
    db = casa["db"]
    with db.transaction() as con:
        DEP.init_usos_schema(con)
        d = DEP.criar(con, valor_centavos=50000, depositante="BEATRIZ EXEMPLO",
                      agora="2026-09-10T09:00:00", hoje=date(2026, 9, 10))
        DEP.debitar(con, d["id"] if "id" in d else d["deposito_id"], 30000,
                    agora="2026-10-05T09:00:00", quem="carla",
                    motivo="Quitação do item pelo depósito prévio (selo)")
    # Decisão do oficial (26/10/2026): só no mês da conversão, e sem os fundos
    # (300 ÷ 1,12 = 267,86, pela configuração padrão).
    assert _apurar(db, "2026-09")["deposito_na_conta"] == 0
    outubro = _apurar(db, "2026-10")
    assert outubro["deposito_na_conta"] == 26786 and outubro["deposito"]["convertido"] == 30000
    setembro = _apurar(db, "2026-09")
    assert setembro["deposito"]["recebido"] == 50000 and setembro["deposito"]["convertido"] == 0
    assert not hasattr(CL, "NO_RECEBIMENTO")


def test_receita_pelo_selo_e_pelo_caixa_aparecem_lado_a_lado(casa):
    db = casa["db"]
    with db.transaction() as con:
        banco(con).escrever(
            """INSERT INTO sd_selos (numero, texto, atribuicao, referencia, ambiente,
                   obtido_em, usado_em) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            ("TESTE145100000000000000000001",
             ("Selo: TESTE1451000000000000000000 01/09/2026 10:00:00, Ato: 14.5.1, "
              "Parte(s): FULANA DE TESTE, Total R$ 50,00 Emol R$ 40,00 FERC R$ 10,00 "
              "Consulte em https://selo.exemplo.invalid"), "NOTAS", "protocolo 2026.09.1",
             "PRODUCAO", "2026-09-01T10:00:00", "2026-09-01T10:00:00"))
    _lancamento(db, "2026-10-02", "50,00", emolumentos="40,00", ferc="10,00")
    setembro, outubro = _apurar(db, "2026-09"), _apurar(db, "2026-10")
    assert (setembro["selo"]["receita"], setembro["receita"]) == (4000, 0)
    assert (outubro["selo"]["receita"], outubro["receita"]) == (0, 4000)


# ------------------------------------------------------------ as despesas

def test_a_marcacao_e_do_oficial_e_a_sugestao_vem_da_categoria(casa):
    db = casa["db"]
    luz = _despesa_ld(db, "2026-09-10", "200,00")
    with db.transaction() as con:
        mesa = DP.cadastrar(
            con, agora=datetime(2026, 9, 1, tzinfo=FUSO),
            por="beatriz", origem="MANUAL", chave_origem=None,
            beneficiario_nome="MOVEIS FICTICIOS", beneficiario_documento="",
            valor_centavos=150000, vencimento="2026-09-12", forma=DP.MANUAL, codigo="",
            descricao="Mesa para o balcão de atendimento", categoria="MOVEIS_EQUIPAMENTOS",
            documento_especie="Nota fiscal")
        DP.registrar_pago_fora(con, mesa, agora=datetime(2026, 9, 12, tzinfo=FUSO), hoje=HOJE,
                               por="mario", papel="ADMIN", data_pagamento="2026-09-12")
    a = _apurar(db, "2026-09")
    por_desc = {d["descricao"][:4]: d for d in a["despesas"]}
    assert por_desc["Mesa"]["sugerida"] == "BENS_DURAVEIS"
    assert por_desc["Mesa"]["sugere_dedutivel"] is False
    # Sem marcação nada se deduz, por mais que a sugestão diga.
    assert a["dedutiveis"] == 0 and a["a_classificar"] == 170000
    with db.transaction() as con:
        CL.marcar_despesa(con, luz, categoria_fiscal="CUSTEIO", dedutivel="1",
                          por="mario", agora=AGORA)
    with db.transaction() as con:      # remarcar guarda a anterior
        CL.marcar_despesa(con, luz, categoria_fiscal="CUSTEIO", dedutivel="0",
                          por="mario", agora=AGORA)
        CL.marcar_despesa(con, luz, categoria_fiscal="CUSTEIO", dedutivel="1",
                          por="mario", agora=AGORA)
    with db.connect() as con:
        historico = banco(con).ler("SELECT * FROM cl_marcacoes WHERE ld_despesa_id = %s",
                                   (luz,))
    assert len(historico) == 3 and sum(1 for m in historico if not m["substituida_em"]) == 1
    a = _apurar(db, "2026-09")
    assert a["dedutiveis"] == 20000 and a["a_classificar"] == 150000


def test_guia_de_fundo_nao_e_despesa_e_nao_chega_ao_livro_caixa(casa):
    db = casa["db"]
    with db.transaction() as con:
        guia = DP.cadastrar(
            con, agora=datetime(2026, 9, 1, tzinfo=FUSO), por="beatriz", origem="MANUAL",
            chave_origem=None, beneficiario_nome="FUNDO FICTICIO", beneficiario_documento="",
            valor_centavos=90000, vencimento="2026-09-10", forma=DP.MANUAL, codigo="",
            descricao="Guia do FERJ de agosto", categoria="FUNDO_FERJ",
            documento_especie="Guia")
        DP.registrar_pago_fora(con, guia, agora=datetime(2026, 9, 10, tzinfo=FUSO), hoje=HOJE,
                               por="mario", papel="ADMIN", data_pagamento="2026-09-10")
    assert _apurar(db, "2026-09")["despesas"] == []


def test_despesa_anulada_nao_se_marca(casa):
    db = casa["db"]
    i = _despesa_ld(db, "2026-09-10", "10,00")
    with db.transaction() as con:
        LD.anular_despesa(con, i, agora=AGORA, por="mario", motivo="Lançada em duplicidade")
    with db.transaction() as con, pytest.raises(CL.CarneLeaoError, match="anulada"):
        CL.marcar_despesa(con, i, categoria_fiscal="CUSTEIO", dedutivel="1",
                          por="mario", agora=AGORA)


def test_o_excesso_de_despesa_vai_para_o_mes_seguinte_ate_dezembro(casa):
    db = casa["db"]
    _tabela(db)
    _lancamento(db, "2026-09-02", "3.000,00", emolumentos="3.000,00")
    luz = _despesa_ld(db, "2026-09-10", "500,00")
    with db.transaction() as con:
        CL.marcar_despesa(con, luz, categoria_fiscal="CUSTEIO", dedutivel="1",
                          por="mario", agora=AGORA)
        CL.lancar_avulso(con, tipo="DESPESA", data="2026-09-11", valor="500,00",
                         descricao="Assessoria contábil paga do bolso", documento="RPA 7",
                         categoria_fiscal="SERVICOS_TERCEIROS", dedutivel="1",
                         hoje=HOJE, agora=AGORA, por="mario")
    a = _apurar(db, "2026-09")
    assert (a["receita"], a["dedutiveis"], a["base"]) == (300000, 100000, 200000)
    assert a["imposto"] == 10000                       # 200 × 10% − 100, faixa 2
    # Outubro: despesa maior que a receita. Base zero, excesso à vista.
    _lancamento(db, "2026-10-02", "100,00", emolumentos="100,00")
    with db.transaction() as con:
        CL.lancar_avulso(con, tipo="DESPESA", data="2026-10-03", valor="400,00",
                         descricao="Conserto do ar-condicionado", categoria_fiscal="CUSTEIO",
                         dedutivel="1", hoje=HOJE, agora=AGORA, por="mario")
    outubro = _apurar(db, "2026-10")
    assert (outubro["base"], outubro["excesso"], outubro["imposto"]) == (0, 30000, 0)
    # Novembro: os 300 de outubro somam às deduções. 2.000 − 300 = 1.700.
    _lancamento(db, "2026-11-03", "2.000,00", emolumentos="2.000,00")
    novembro = _apurar(db, "2026-11")
    assert (novembro["excesso_anterior"], novembro["base"], novembro["excesso"]) == (30000, 170000, 0)
    assert novembro["imposto"] == 7000                 # 1.700 × 10% − 100
    with db.connect() as con:
        _, ano = CL.apurar_com_o_ano(con, "2026-11", ate="2026-11")
    assert [m["excesso_anterior"] for m in ano][-2:] == [0, 30000]
    # Janeiro recomeça: o excesso não passa de um ano para o outro.
    _lancamento(db, "2026-12-03", "10,00", emolumentos="10,00")
    with db.transaction() as con:
        CL.lancar_avulso(con, tipo="DESPESA", data="2026-12-04", valor="900,00",
                         descricao="Conserto do telhado da serventia", categoria_fiscal="CUSTEIO",
                         dedutivel="1", hoje="2026-12-31", agora=AGORA, por="mario")
    assert _apurar(db, "2026-12")["excesso"] == 89000
    assert _apurar(db, "2027-01")["excesso_anterior"] == 0


def test_lancamento_avulso_se_anula_com_motivo_e_nao_conta(casa):
    db = casa["db"]
    with db.transaction() as con:
        i = CL.lancar_avulso(con, tipo="RECEITA", data="2026-09-20", valor="80,00",
                             descricao="Ressarcimento de gratuidade de agosto",
                             hoje=HOJE, agora=AGORA, por="mario")
    assert _apurar(db, "2026-09")["avulsas"] == 8000
    with db.transaction() as con, pytest.raises(CL.CarneLeaoError, match="por que"):
        CL.anular_avulso(con, i, motivo="", por="mario", agora=AGORA)
    with db.transaction() as con:
        CL.anular_avulso(con, i, motivo="Valor já entrou pelo caixa", por="mario", agora=AGORA)
    assert _apurar(db, "2026-09")["avulsas"] == 0
    with db.transaction() as con, pytest.raises(CL.CarneLeaoError, match="futuro"):
        CL.lancar_avulso(con, tipo="RECEITA", data="2099-01-01", valor="1,00",
                         descricao="Lançamento no futuro", hoje=HOJE, agora=AGORA,
                         por="mario")


# ------------------------------------------------------------ a exportação

def test_o_csv_diz_que_nao_e_o_leiaute_oficial_e_nao_traz_codigo_de_barras(casa):
    db = casa["db"]
    _lancamento(db, "2026-09-02", "130,00", emolumentos="100,00", ferc="30,00")
    _despesa_ld(db, "2026-09-10", "20,00")
    import csv_seguro as CSVS
    csv = CSVS.gerar(None, CL.livro_caixa_linhas(_apurar(db, "2026-09")))
    linhas = list(_csv.reader(io.StringIO(csv), delimiter=";"))
    assert "leiaute de importação do Carnê-Leão Web não está nesta casa" in csv
    receita = next(r for r in linhas if r[:3] == ["2026-09-02", "RECEITA", "Caixa"])
    assert receita[5] == "100,00"
    assert any(r[1:3] == ["DESPESA", "Livro Diário"] for r in linhas if len(r) > 2)
    assert "A CLASSIFICAR" in csv
    assert ["# IMPOSTO PELA TABELA CADASTRADA", "sem tabela"] in linhas
    assert not re.search(r"\d{44,48}", csv)              # nada de código de barras


# ------------------------------------------------------------ a agenda

def test_o_prazo_ja_vem_no_ultimo_dia_util_e_sem_regra_volta_a_ser_pergunta(casa):
    # Decisão do oficial (26/10/2026): último dia do mês seguinte, já na agenda.
    with casa["db"].connect() as con:
        ob = CL.obrigacao_da_agenda(con)
    assert ob and ob["ultimo_dia_util"] and ob["fonte"] == CL.FONTE_DO_PRAZO
    with casa["db"].transaction() as con, pytest.raises(CL.CarneLeaoError, match="fonte"):
        CL.gravar_configuracao(con, {"carne_leao_prazo_regra": CL.ULTIMO_DIA_UTIL,
                                     "carne_leao_prazo_fonte": ""})
    with casa["db"].transaction() as con:
        CL.gravar_configuracao(con, {"carne_leao_prazo_regra": ""})
    with casa["db"].connect() as con:
        assert CL.obrigacao_da_agenda(con) is None
    assert "Carnê-leão" in OO.pergunta_das_nao_medidas()["contexto"]


def test_com_a_regra_e_a_fonte_o_prazo_entra_na_agenda_e_sai_da_pergunta(casa):
    db = casa["db"]
    with db.transaction() as con:
        CL.gravar_configuracao(con, {"carne_leao_prazo_regra": CL.ULTIMO_DIA_UTIL,
                                     "carne_leao_prazo_fonte": "Orientação escrita do contador, ficha 1"})
    with db.connect() as con:
        ob = CL.obrigacao_da_agenda(con)
    # 30/10/2026 é sexta; 31/10 é sábado.
    assert OO.proximo_vencimento(ob, date(2026, 10, 26)) == (date(2026, 10, 30),
                                                             "referência 09/2026")
    assert OO.proximo_vencimento(ob, date(2026, 10, 31)) == (date(2026, 11, 30),
                                                             "referência 10/2026")
    assert any(o["codigo"] == "CARNE_LEAO" for o in OO.agenda(date(2026, 10, 26), extras=(ob,)))
    assert "Carnê-leão" not in OO.pergunta_das_nao_medidas(("CARNE_LEAO",))["contexto"]
    # Dia fixo além do fim do mês cai no último dia.
    with db.transaction() as con:
        CL.gravar_configuracao(con, {"carne_leao_prazo_regra": CL.DIA_DO_MES,
                                     "carne_leao_prazo_dia": "31",
                                     "carne_leao_prazo_fonte": "Orientação escrita do contador, ficha 2"})
    with db.connect() as con:
        ob = CL.obrigacao_da_agenda(con)
    assert OO.proximo_vencimento(ob, date(2027, 2, 2))[0] == date(2027, 2, 28)


# ------------------------------------------- a tabela nacional e a redução

def test_a_tabela_nacional_entra_com_um_clique_e_aplica_a_reducao_da_lei_15270(casa):
    db = casa["db"]
    # As faixas guardadas são as que a tela leria da Receita, digitadas.
    lidas = CL.ler_faixas("2.428,80; 0; 0\n2.826,65; 7,5; 182,16\n3.751,05; 15; 394,16\n"
                          "4.664,68; 22,5; 675,49\n; 27,5; 908,73")
    assert all(lidas == [dict(f) for f in t["faixas"]] for t in CL.TABELAS_NACIONAIS)
    with db.transaction() as con:
        feito = CL.cadastrar_tabelas_nacionais(con, por="mario", agora=AGORA)
    assert len(feito) == 2 and all("cadastrada" in x for x in feito)
    with db.transaction() as con:
        assert all("já havia" in x for x in CL.cadastrar_tabelas_nacionais(
            con, por="mario", agora=AGORA))
    # O exemplo da Receita: R$ 6.000,00 → redução de R$ 179,75.
    _lancamento(db, "2026-09-02", "6.000,00", emolumentos="6.000,00")
    a = _apurar(db, "2026-09")
    assert a["calculo"]["imposto_da_tabela"] == 74127 and a["calculo"]["reducao"] == 17975
    assert a["imposto"] == 56152
    assert any("Lei 15.270" in x for x in a["avisos"])
    # Até R$ 5.000,00 a redução vai a R$ 312,89, sem passar do imposto.
    _lancamento(db, "2026-10-02", "4.000,00", emolumentos="4.000,00")
    assert _apurar(db, "2026-10")["imposto"] == 0
    # Antes de 2026, a tabela de maio de 2025 vale sem redução.
    _lancamento(db, "2025-09-02", "6.000,00", emolumentos="6.000,00")
    assert _apurar(db, "2025-09")["imposto"] == 74127


def test_a_parte_dos_fundos_segue_a_configuracao_do_delegatario(casa):
    db = casa["db"]
    _lancamento(db, "2026-09-04", "100,00")
    assert _apurar(db, "2026-09")["caixa"] == 8929               # 100 ÷ 1,12
    with db.transaction() as con:
        CL.gravar_configuracao(con, {"carne_leao_fundos_forma": CL.FUNDOS_DENTRO_DO_VALOR,
                                     "carne_leao_fundos_percentual": "10"})
    assert _apurar(db, "2026-09")["caixa"] == 9000               # 100 − 10%
    with db.transaction() as con:
        CL.gravar_configuracao(con, {"carne_leao_fundos_percentual": "0"})
    assert _apurar(db, "2026-09")["caixa"] == 10000
    with db.transaction() as con, pytest.raises(CL.CarneLeaoError, match="100%"):
        CL.gravar_configuracao(con, {"carne_leao_fundos_percentual": "100"})


def test_a_outra_entrada_conta_conforme_a_resposta_de_quem_lancou(casa):
    db = casa["db"]
    _lancamento(db, "2026-09-08", "60,00", natureza="OUTRA_ENTRADA",
                descricao="Ressarcimento de gratuidade", receita_do_titular=1)
    _lancamento(db, "2026-09-08", "40,00", natureza="OUTRA_ENTRADA",
                descricao="Reembolso de cópia a terceiro", receita_do_titular=0)
    antiga = _lancamento(db, "2026-09-09", "25,00", natureza="OUTRA_ENTRADA",
                         descricao="Entrada antiga sem resposta")
    a = _apurar(db, "2026-09")
    assert [(r["origem"], r["valor"]) for r in a["receitas"]] == [("Outra entrada", 6000)]
    assert [o["valor"] for o in a["outras_entradas"]] == [2500]
    with db.transaction() as con:
        CL.marcar_outra_entrada(con, antiga, receita="1")
    assert _apurar(db, "2026-09")["receita"] == 8500
    recebimento = _lancamento(db, "2026-09-10", "10,00", emolumentos="10,00")
    with db.transaction() as con, pytest.raises(CL.CarneLeaoError, match="outra entrada"):
        CL.marcar_outra_entrada(con, recebimento, receita="1")


# ------------------------------------------------------------ as telas

def _token(c, url):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                     c.get(url).get_data(as_text=True)).group(1)


def test_as_telas_abrem_para_o_admin_e_a_marcacao_pela_tela_funciona(casa):
    c, db = casa["c"], casa["db"]
    luz = _despesa_ld(db, "2026-09-10", "200,00")
    for url in ("/administrativo/carne-leao?mes=2026-09",
                "/administrativo/carne-leao/configuracao"):
        r = c.get(url)
        assert r.status_code == 200, url
    pagina = c.get("/administrativo/carne-leao?mes=2026-09").get_data(as_text=True)
    assert "a classificar" in pagina and "sem tabela cadastrada para o mês" in pagina
    r = c.post(f"/administrativo/carne-leao/despesa/{luz}/marcar", data={
        "csrf_token": _token(c, "/administrativo/carne-leao?mes=2026-09"), "mes": "2026-09",
        "categoria_fiscal": "CUSTEIO", "dedutivel": "1"}, follow_redirects=True)
    assert r.status_code == 200 and "Marcação gravada" in r.get_data(as_text=True)
    assert _apurar(db, "2026-09")["dedutiveis"] == 20000
    r = c.post("/administrativo/carne-leao/configuracao", data={
        "csrf_token": _token(c, "/administrativo/carne-leao/configuracao"), "acao": "tabela",
        "vigencia_inicio": "2026-01-01", "descricao": "Fictícia da tela", "fonte": FONTE,
        "faixas": FAIXAS_FICTICIAS}, follow_redirects=True)
    assert "Tabela cadastrada" in r.get_data(as_text=True)
    csv = c.get("/administrativo/carne-leao/exportar?mes=2026-09")
    assert csv.status_code == 200 and "livro-caixa-2026-09.csv" in csv.headers["Content-Disposition"]


def test_quem_nao_e_admin_nao_ve_a_renda_do_titular(casa):
    db = casa["db"]
    db.create_user("carla", "CARLA EXEMPLO LIMA", "Senha#12345", "MANAGER")
    c = casa["app"].test_client()
    cg_login(c, "carla", "Senha#12345")
    for url in ("/administrativo/carne-leao", "/administrativo/carne-leao/configuracao",
                "/administrativo/carne-leao/exportar"):
        r = c.get(url)
        assert r.status_code in (302, 403), (url, r.status_code)
        assert "Receita no regime de caixa" not in r.get_data(as_text=True)
