"""
Testes do emolumento a posteriori do Protesto (LG05) — cada caminho cobra certo.

O QUE ELES CONFEREM
    A regra do CN-MA art. 925, §§ 11 e 12, e não «a função devolveu algo»:

      - título da Central, de ente público ou com vencimento de até um ano é
        DIFERIDO; o resto é ANTECIPADO (depósito prévio facultado);
      - no diferido, a protocolização, a intimação e o protesto NÃO entram no
        caixa: o item fica devido;
      - o pagamento e a desistência cobram o devido pela tabela da
        PROTOCOLIZAÇÃO (§ 11, I) — e o teste tem duas tabelas com preços
        diferentes, para a data errada aparecer no valor;
      - o cancelamento cobra pela tabela do DIA DO PEDIDO (§ 11, II);
      - a certidão nunca se difere;
      - o devido não se cobra duas vezes, e o de ato cancelado não se cobra;
      - o balcão decide o regime só antes do primeiro ato.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import ato_selado as AS                          # noqa: E402
import protesto as PT                            # noqa: E402
import protesto_posteriori as POST               # noqa: E402
from bd_nativo import banco as nativo            # noqa: E402
from caixa_schema import init_caixa_schema       # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from pt_schema import init_pt_schema             # noqa: E402

PROTOCOLADO = "2026-09-21T09:00:00"     # tabela velha: item a R$ 10,00
HOJE = "2026-10-19"                     # tabela nova: item a R$ 12,00
AGORA = HOJE + "T10:00:00"
EXTENSO = "vinte e um dias do mês de setembro do ano de dois mil e vinte e seis"
SV = {"unit_name": "SERVENTIA DE TESTE", "serventia_titular": "TABELIÃO DE TESTE",
      "serventia_titulo": "Tabelião", "ri_cns": "000000",
      "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
ITEM = 901


def banco():
    con = conexao_de_teste()
    init_nucleo_schema(con)
    # `caixa_schema` aponta para `users` e para a prenotação e a matrícula do
    # RI; no banco da casa elas vêm antes — o mesmo arranjo de test_ato_selado.
    for tabela in ("users", "ri_protocolos", "ri_matriculas"):
        con.execute(f"CREATE TABLE IF NOT EXISTS {tabela} (id INTEGER PRIMARY KEY)")
    init_caixa_schema(con)
    init_pt_schema(con)
    bd = nativo(con)
    # DUAS TABELAS, DOIS PREÇOS — é o preço que denuncia a data errada.
    bd.escrever("""INSERT INTO cx_vigencias(codigo, descricao, vigente, inicio, fim)
                   VALUES (1, 'velha', 0, '2026-01-01', '2026-09-30'),
                          (2, 'nova', 1, '2026-10-01', NULL)""")
    bd.escrever("""INSERT INTO cx_servicos(codigo, codigo_tj, descricao)
                   VALUES (%s, '17.9.9', 'Item de teste')""", (ITEM,))
    for vigencia, preco in ((1, "10,00"), (2, "12,00")):
        bd.escrever(
            """INSERT INTO cx_servico_valores(servico, vigencia, emolumentos,
                   ferc, femp, fadep, ferrfis, total)
               VALUES (%s,%s,%s,'0,00','0,00','0,00','0,00',%s)""",
            (ITEM, vigencia, preco, preco))
    caixa = bd.escrever(
        """INSERT INTO cx_caixas(data, operador_nome, aberto_em, situacao)
           VALUES (%s, 'OPERADOR DE TESTE', %s, 'ABERTO') RETURNING id""",
        (HOJE, AGORA))[0]["id"]
    return con, int(caixa)


def dados(**mudar) -> dict:
    d = {"especie": "DMI", "numero_titulo": "LG05/1",
         "data_emissao": "2022-07-21", "data_vencimento": "2022-09-05",
         "valor": "1482.78", "saldo": "1482.78",
         "praca_protesto": "CIDADE EXEMPLO", "tipo_moeda": "1",
         "tipo_protesto": "C", "motivo_protesto": "1",
         "cedente": {"nome": "CREDOR FICTICIO", "documento": "00000000000000",
                     "cidade": "Cidade Exemplo", "uf": "MA"},
         "devedores": [{"nome": "DEVEDOR FICTICIO", "CNPJ": "00000000000000",
                        "enderecos": [{"endereco": "Rua X", "bairro": "Centro",
                                       "cidade": "Cidade Exemplo", "uf": "MA"}]}]}
    d.update(mudar)
    return d


def titulo(con, *, origem="CRA", chave="LG05:1", **mudar) -> int:
    return PT.cadastrar_titulo(con, dados(**mudar), origem=origem,
                               origem_chave=chave if origem != "MANUAL" else None,
                               agora=PROTOCOLADO)


def apontar(con, titulo_id, *, itens=(ITEM,)):
    """O apontamento como a rota faz: lavra e, sendo diferido, deixa devido."""
    r = PT.lancar_apontamento(con, titulo_id, sv=SV, agora=PROTOCOLADO,
                              data_extenso=EXTENSO)
    cob = POST.cobranca_do_ato(con, titulo_id, "APONTAMENTO", hoje=PROTOCOLADO)
    if cob["diferir"] and itens:
        POST.diferir(con, titulo_id=titulo_id, ato_id=r["ato_id"],
                     tipo_ato="APONTAMENTO",
                     itens=[{"servico": s} for s in itens],
                     data_do_ato=PROTOCOLADO, agora=PROTOCOLADO)
    return r


def cobrar_desfecho(con, caixa, titulo_id, ato_id, tipo):
    cob = POST.cobranca_do_ato(con, titulo_id, tipo, hoje=HOJE)
    return cob, POST.cobrar_pendentes(
        con, titulo_id, ato_do_desfecho_id=ato_id,
        data_da_tabela=cob["data_da_tabela"], caixa_id=caixa, agora=AGORA,
        hoje=HOJE, hora="10:00")


def lancamentos(con) -> list[dict]:
    return nativo(con).ler(
        "SELECT * FROM cx_lancamentos WHERE origem='ATO' ORDER BY id")


# ---------------------------------------------------------------- o regime


def test_titulo_que_veio_pela_central_e_diferido():
    con, _ = banco()
    tid = titulo(con)
    reg = POST.regime(con, tid)
    assert reg["regime"] == "DIFERIDO"
    assert reg["por"] == "CENTRAL"


def test_certidao_de_divida_ativa_do_balcao_e_diferida_pelo_paragrafo_12():
    con, _ = banco()
    tid = titulo(con, origem="MANUAL", especie="CDA")
    reg = POST.regime(con, tid)
    assert (reg["regime"], reg["por"]) == ("DIFERIDO", "ESPECIE")
    assert "§ 12, I" in reg["fundamento"]


def test_titulo_do_balcao_vencido_ha_menos_de_um_ano_e_diferido():
    con, _ = banco()
    tid = titulo(con, origem="MANUAL", data_vencimento="2026-03-01",
                 data_emissao="2026-01-10")
    reg = POST.regime(con, tid)
    assert (reg["regime"], reg["por"]) == ("DIFERIDO", "VENCIMENTO")


def test_titulo_do_balcao_vencido_ha_mais_de_um_ano_e_antecipado():
    con, _ = banco()
    tid = titulo(con, origem="MANUAL")
    reg = POST.regime(con, tid)
    assert reg["regime"] == "ANTECIPADO"
    assert "mais de um ano" in reg["motivo"]


def test_o_ano_do_vencimento_conta_o_dia_inteiro():
    # Vencido em 21/09/2025, apresentado em 21/09/2026: ainda «não ultrapassa».
    con, _ = banco()
    tid = titulo(con, origem="MANUAL", data_vencimento="2025-09-21",
                 data_emissao="2025-08-01")
    assert POST.regime(con, tid)["regime"] == "DIFERIDO"


# ------------------------------------------------------------ cada caminho


def test_protocolizacao_do_diferido_nao_entra_no_caixa_e_fica_devida():
    con, _ = banco()
    tid = titulo(con)
    cob = POST.cobranca_do_ato(con, tid, "APONTAMENTO", hoje=PROTOCOLADO)
    assert cob["diferir"] is True
    apontar(con, tid)
    assert lancamentos(con) == []
    devidos = POST.pendentes(con, tid)
    assert [(d["tipo_ato"], d["servico"]) for d in devidos] == [("APONTAMENTO", ITEM)]


def test_intimacao_e_protesto_do_diferido_tambem_ficam_devidos():
    con, _ = banco()
    tid = titulo(con)
    apontar(con, tid)
    for tipo in ("INTIMACAO", "PROTESTO"):
        cob = POST.cobranca_do_ato(con, tid, tipo, hoje=HOJE)
        assert cob["diferir"] is True
        assert cob["data_da_tabela"] is None


def test_pagamento_do_diferido_cobra_pela_tabela_da_protocolizacao():
    con, caixa = banco()
    tid = titulo(con)
    apontar(con, tid)
    pago = PT.lancar_pagamento(con, tid, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    cob, r = cobrar_desfecho(con, caixa, tid, pago["ato_id"], "PAGAMENTO")
    assert cob["data_da_tabela"] == "2026-09-21"
    assert cob["quem_paga"] == "o devedor"
    # R$ 10,00 é a tabela velha. R$ 12,00 seria a de hoje — a data errada.
    assert r["total_centavos"] == 1000
    assert [x["valor"] for x in lancamentos(con)] == ["10,00"]
    assert POST.pendentes(con, tid) == []


def test_desistencia_do_diferido_cobra_do_apresentante_pela_tabela_da_protocolizacao():
    con, caixa = banco()
    tid = titulo(con)
    apontar(con, tid)
    des = PT.lancar_desistencia(con, tid, motivo="Credor desistiu do protesto",
                                agora=AGORA)
    cob, r = cobrar_desfecho(con, caixa, tid, des["ato_id"], "DESISTENCIA")
    assert cob["quem_paga"] == "o apresentante"
    assert "§ 11, I" in cob["fundamento"]
    assert r["total_centavos"] == 1000


def test_cancelamento_do_diferido_cobra_pela_tabela_do_dia_do_pedido():
    con, caixa = banco()
    tid = titulo(con)
    apontar(con, tid)
    PT.lancar_intimacao(con, tid, modo="PESSOAL", agora=PROTOCOLADO)
    PT.lancar_protesto(con, tid, sv=SV, agora=PROTOCOLADO, data_extenso=EXTENSO)
    can = PT.lancar_cancelamento(con, tid, hipotese="PAGAMENTO",
                                 fundamento="Quitado, com o título original.",
                                 agora=AGORA)
    cob, r = cobrar_desfecho(con, caixa, tid, can["ato_id"], "CANCELAMENTO")
    assert cob["data_da_tabela"] == HOJE
    assert "§ 11, II" in cob["fundamento"]
    assert r["total_centavos"] == 1200


def test_a_certidao_nunca_se_difere_e_cobra_pela_tabela_de_hoje():
    con, _ = banco()
    cob = POST.cobranca_do_ato(con, None, "CERTIDAO", hoje=HOJE)
    assert cob["diferir"] is False and cob["cobra_diferidos"] is False
    assert cob["data_da_tabela"] == HOJE
    assert "art. 950" in cob["fundamento"]


def test_titulo_antecipado_cobra_tudo_na_hora_pela_tabela_de_hoje():
    con, _ = banco()
    tid = titulo(con, origem="MANUAL")
    for tipo in POST.MOMENTO_DO_ATO:
        cob = POST.cobranca_do_ato(con, tid, tipo, hoje=HOJE)
        assert (cob["diferir"], cob["cobra_diferidos"], cob["data_da_tabela"]) \
            == (False, False, HOJE), tipo


# ------------------------------------------------------------ as travas


def test_o_devido_nao_se_cobra_duas_vezes():
    con, caixa = banco()
    tid = titulo(con)
    apontar(con, tid)
    pago = PT.lancar_pagamento(con, tid, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    cobrar_desfecho(con, caixa, tid, pago["ato_id"], "PAGAMENTO")
    _, segunda = cobrar_desfecho(con, caixa, tid, pago["ato_id"], "PAGAMENTO")
    assert segunda["itens"] == 0
    assert len(lancamentos(con)) == 1


def test_o_devido_de_ato_cancelado_nao_se_cobra():
    # O selo que não saiu desfaz o ato — e com ele o emolumento.
    con, caixa = banco()
    tid = titulo(con)
    r = apontar(con, tid)
    nativo(con).escrever("UPDATE pt_atos SET cancelado=1 WHERE id=%s",
                         (r["ato_id"],))
    assert POST.pendentes(con, tid) == []


def test_o_mesmo_item_do_mesmo_ato_nao_fica_devido_duas_vezes():
    con, _ = banco()
    tid = titulo(con)
    r = apontar(con, tid)
    outra = POST.diferir(con, titulo_id=tid, ato_id=r["ato_id"],
                         tipo_ato="APONTAMENTO", itens=[{"servico": ITEM}],
                         data_do_ato=PROTOCOLADO, agora=PROTOCOLADO)
    assert outra["registrados"] == 0
    assert len(POST.pendentes(con, tid)) == 1


def test_item_que_a_tabela_nao_tem_estoura_ja_na_protocolizacao():
    con, _ = banco()
    tid = titulo(con)
    r = PT.lancar_apontamento(con, tid, sv=SV, agora=PROTOCOLADO,
                              data_extenso=EXTENSO)
    with pytest.raises(AS.AtoError):
        POST.diferir(con, titulo_id=tid, ato_id=r["ato_id"],
                     tipo_ato="APONTAMENTO", itens=[{"servico": 999999}],
                     data_do_ato=PROTOCOLADO, agora=PROTOCOLADO)


def test_o_balcao_decide_o_regime_antes_do_primeiro_ato():
    con, _ = banco()
    tid = titulo(con)
    POST.definir_regime(con, tid, "ANTECIPADO",
                        motivo="Apresentante é pessoa física, sem convênio")
    reg = POST.regime(con, tid)
    assert (reg["regime"], reg["por"]) == ("ANTECIPADO", "BALCAO")


def test_o_regime_nao_muda_depois_da_protocolizacao():
    con, _ = banco()
    tid = titulo(con)
    apontar(con, tid)
    with pytest.raises(POST.PosterioriError, match="antes da protocolização"):
        POST.definir_regime(con, tid, "ANTECIPADO", motivo="Mudou de ideia")


def test_mudar_o_regime_exige_motivo():
    con, _ = banco()
    tid = titulo(con)
    with pytest.raises(POST.PosterioriError, match="por que"):
        POST.definir_regime(con, tid, "ANTECIPADO", motivo="")


def test_a_ficha_estima_o_devido_pela_tabela_da_protocolizacao():
    con, _ = banco()
    tid = titulo(con)
    apontar(con, tid)
    resumo = POST.resumo_para_a_ficha(con, tid, hoje=HOJE)
    assert resumo["regime"] == "DIFERIDO"
    assert resumo["pendentes"]["total_centavos"] == 1000
    assert resumo["pode_mudar"] is False
