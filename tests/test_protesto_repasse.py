"""
Testes do repasse ao apresentante (LG05) — guia ao IEPTB e repasse direto.

O QUE ELES CONFEREM
      - pagamento lançado e sem repasse É a pendência, com o prazo do primeiro
        dia útil seguinte (Lei 9.492/1997, art. 19, § 2º) e o atraso contado;
      - título da Central vai pela guia do IEPTB; título do balcão, direto;
      - a guia segue GERADA → REGISTRADA → PAGA → CONCILIADA, e cada passo
        recusa o que não é a vez dele;
      - valor que não fecha não concilia, e a mensagem diz a diferença;
      - guia cancelada devolve os pagamentos à pendência;
      - repasse direto acima de R$ 300,00 só por cheque ou depósito (CN-MA
        art. 926, § 1º), e sempre com comprovante;
      - o mesmo pagamento não se repassa duas vezes;
      - o acervo do E-Ofício não vira pendência.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import protesto as PT                            # noqa: E402
import protesto_repasse as REP                   # noqa: E402
from bd_nativo import banco as nativo            # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from pt_schema import init_pt_schema             # noqa: E402

PAGO = "2026-10-16T10:00:00"     # uma sexta-feira: o prazo cai na segunda
HOJE = "2026-10-21"
AGORA = HOJE + "T09:00:00"
EXTENSO = "dezesseis dias do mês de outubro do ano de dois mil e vinte e seis"
SV = {"unit_name": "SERVENTIA DE TESTE", "serventia_titular": "TABELIÃO DE TESTE",
      "serventia_titulo": "Tabelião", "ri_cns": "000000",
      "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}


def banco():
    con = conexao_de_teste()
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


def pago(con, *, origem="CRA", chave="REP:1", valor_pago=None,
         saldo="1482.78", numero="REP/1") -> dict:
    d = {"especie": "DMI", "numero_titulo": numero,
         "data_emissao": "2026-07-21", "data_vencimento": "2026-09-05",
         "valor": saldo, "saldo": saldo, "praca_protesto": "CIDADE EXEMPLO",
         "tipo_moeda": "1", "tipo_protesto": "C", "motivo_protesto": "1",
         "apresentante_codigo": "999", "apresentante_nome": "BANCO FICTICIO",
         "cedente": {"nome": "CREDOR FICTICIO", "documento": "00000000000000",
                     "cidade": "Cidade Exemplo", "uf": "MA"},
         "devedores": [{"nome": "DEVEDOR FICTICIO", "CPF": "00000000000",
                        "enderecos": [{"endereco": "Rua X", "bairro": "Centro",
                                       "cidade": "Cidade Exemplo", "uf": "MA"}]}]}
    tid = PT.cadastrar_titulo(con, d, origem=origem,
                              origem_chave=None if origem == "MANUAL" else chave,
                              agora=PAGO)
    PT.lancar_apontamento(con, tid, sv=SV, agora=PAGO, data_extenso=EXTENSO)
    # em espécie: PIX só se lavra com o crédito conferido (29/10/2026)
    r = PT.lancar_pagamento(con, tid, sv=SV, agora=PAGO, data_extenso=EXTENSO,
                            valor_pago=valor_pago, forma_pagamento="ESPECIE")
    return {"titulo_id": tid, "ato_id": r["ato_id"]}


# ------------------------------------------------------------ a pendência


def test_pagamento_sem_repasse_e_pendencia_com_prazo_do_primeiro_dia_util():
    con = banco()
    p = pago(con)
    [linha] = REP.pendentes(con, hoje=HOJE)
    assert linha["ato_id"] == p["ato_id"]
    assert linha["canal"] == "IEPTB"
    assert linha["prazo"] == "2026-10-19"        # sexta paga, segunda repassa
    assert linha["dias_de_atraso"] == 2
    assert linha["vencido"] is True


def test_o_feriado_da_casa_empurra_o_prazo():
    con = banco()
    pago(con)
    from datetime import date
    [linha] = REP.pendentes(con, hoje=HOJE, feriados={date(2026, 10, 19)})
    assert linha["prazo"] == "2026-10-20"


def test_o_valor_e_o_pago_quando_informado_e_o_declarado_quando_nao():
    con = banco()
    pago(con, chave="REP:1", valor_pago="1000,00")
    pago(con, chave="REP:2", numero="REP/2")
    a, b = REP.pendentes(con, hoje=HOJE)
    assert (a["valor_centavos"], a["valor_de"]) == (100000, "PAGO")
    assert (b["valor_centavos"], b["valor_de"]) == (148278, "SALDO")


def test_pagamento_do_acervo_nao_vira_pendencia():
    con = banco()
    p = pago(con)
    nativo(con).escrever("UPDATE pt_atos SET origem='EOFICIO' WHERE id=%s",
                         (p["ato_id"],))
    assert REP.pendentes(con, hoje=HOJE) == []


def test_pagamento_cancelado_sai_da_pendencia():
    con = banco()
    p = pago(con)
    nativo(con).escrever("UPDATE pt_atos SET cancelado=1 WHERE id=%s",
                         (p["ato_id"],))
    assert REP.pendentes(con, hoje=HOJE) == []


def test_o_relatorio_separa_os_dois_canais():
    con = banco()
    pago(con)
    pago(con, origem="MANUAL", numero="REP/B", saldo="250.00")
    rel = REP.relatorio(con, hoje=HOJE)
    assert rel["por_canal"]["IEPTB"]["titulos"] == 1
    assert rel["por_canal"]["DIRETO"]["total_centavos"] == 25000
    assert rel["vencidos"] == 2


# ---------------------------------------------------------------- a guia


def test_a_guia_junta_os_pagamentos_da_central_e_deixa_o_do_balcao():
    con = banco()
    pago(con)
    pago(con, origem="MANUAL", numero="REP/B")
    g = REP.gerar_guia(con, hoje=HOJE, agora=AGORA)
    assert (g["numero"], g["titulos"], g["total_centavos"]) == (1, 1, 148278)
    guia = REP.guia(con, g["guia_id"])
    assert "REP/1" in guia["relacao"] and "REP/B" not in guia["relacao"]
    assert [p["canal"] for p in REP.pendentes(con, hoje=HOJE)] == ["DIRETO"]


def test_titulo_do_balcao_pedido_na_guia_e_recusado():
    con = banco()
    p = pago(con, origem="MANUAL")
    with pytest.raises(REP.RepasseError, match="direto ao apresentante"):
        REP.gerar_guia(con, hoje=HOJE, agora=AGORA, ato_ids=[p["ato_id"]])


def test_o_mesmo_pagamento_nao_entra_em_duas_guias():
    con = banco()
    p = pago(con)
    REP.gerar_guia(con, hoje=HOJE, agora=AGORA)
    with pytest.raises(REP.RepasseError, match="não está"):
        REP.gerar_guia(con, hoje=HOJE, agora=AGORA, ato_ids=[p["ato_id"]])


def test_a_guia_anda_ate_conciliada_e_o_repasse_se_cumpre_no_pagamento():
    con = banco()
    pago(con)
    g = REP.gerar_guia(con, hoje=HOJE, agora=AGORA)
    REP.registrar_guia(con, g["guia_id"], identificador="IEPTB-2026-000123",
                       vencimento="2026-10-23", agora=AGORA)
    REP.pagar_guia(con, g["guia_id"], paga_em=HOJE, comprovante="AUT 998877",
                   agora=AGORA)
    guia = REP.guia(con, g["guia_id"])
    assert [r["situacao"] for r in guia["repasses"]] == ["REPASSADO"]
    assert REP.relatorio(con, hoje=HOJE)["a_conciliar"][0]["id"] == g["guia_id"]
    REP.conciliar_guia(con, g["guia_id"], valor_confirmado="1.482,78",
                       referencia="Aviso IEPTB 4455", agora=AGORA)
    assert REP.guia(con, g["guia_id"])["situacao"] == "CONCILIADA"


def test_valor_que_nao_fecha_nao_concilia_e_diz_a_diferenca():
    con = banco()
    pago(con)
    g = REP.gerar_guia(con, hoje=HOJE, agora=AGORA)
    REP.registrar_guia(con, g["guia_id"], identificador="IEPTB-2026-000123",
                       vencimento=None, agora=AGORA)
    REP.pagar_guia(con, g["guia_id"], paga_em=HOJE, comprovante="AUT 998877",
                   agora=AGORA)
    with pytest.raises(REP.RepasseError, match="diferença de R\\$ -0,78"):
        REP.conciliar_guia(con, g["guia_id"], valor_confirmado="1.482,00",
                           referencia="Aviso IEPTB 4455", agora=AGORA)
    assert REP.guia(con, g["guia_id"])["situacao"] == "PAGA"


def test_guia_sem_registro_nao_se_paga():
    con = banco()
    pago(con)
    g = REP.gerar_guia(con, hoje=HOJE, agora=AGORA)
    with pytest.raises(REP.RepasseError, match="REGISTRADA"):
        REP.pagar_guia(con, g["guia_id"], paga_em=HOJE, comprovante="AUT 1",
                       agora=AGORA)


def test_guia_cancelada_devolve_os_pagamentos_a_pendencia():
    con = banco()
    pago(con)
    g = REP.gerar_guia(con, hoje=HOJE, agora=AGORA)
    REP.cancelar_guia(con, g["guia_id"], motivo="Relação gerada com erro",
                      agora=AGORA)
    assert len(REP.pendentes(con, hoje=HOJE)) == 1
    nova = REP.gerar_guia(con, hoje=HOJE, agora=AGORA)
    assert nova["numero"] == 2


def test_guia_paga_nao_se_cancela():
    con = banco()
    pago(con)
    g = REP.gerar_guia(con, hoje=HOJE, agora=AGORA)
    REP.registrar_guia(con, g["guia_id"], identificador="IEPTB-1-2026",
                       vencimento=None, agora=AGORA)
    REP.pagar_guia(con, g["guia_id"], paga_em=HOJE, comprovante="AUT 1",
                   agora=AGORA)
    with pytest.raises(REP.RepasseError, match="PAGA"):
        REP.cancelar_guia(con, g["guia_id"], motivo="Mudança de ideia", agora=AGORA)


# ------------------------------------------------------------ o repasse direto


def test_repasse_direto_do_balcao_com_comprovante():
    con = banco()
    p = pago(con, origem="MANUAL", saldo="250.00")
    r = REP.registrar_direto(con, p["ato_id"], forma="ESPECIE",
                             comprovante="Recibo assinado nº 12",
                             repassado_em="2026-10-19", hoje=HOJE, agora=AGORA)
    assert r["no_prazo"] is True
    assert REP.pendentes(con, hoje=HOJE) == []


def test_acima_de_trezentos_reais_o_repasse_nao_sai_em_especie():
    con = banco()
    p = pago(con, origem="MANUAL")
    with pytest.raises(REP.RepasseError, match="art. 926, § 1º"):
        REP.registrar_direto(con, p["ato_id"], forma="ESPECIE",
                             comprovante="Recibo 13", repassado_em=HOJE,
                             hoje=HOJE, agora=AGORA)
    r = REP.registrar_direto(con, p["ato_id"], forma="DEPOSITO",
                             comprovante="Depósito 556677", repassado_em=HOJE,
                             hoje=HOJE, agora=AGORA)
    assert r["no_prazo"] is False


def test_repasse_direto_sem_comprovante_e_recusado():
    con = banco()
    p = pago(con, origem="MANUAL", saldo="100.00")
    with pytest.raises(REP.RepasseError, match="comprovante"):
        REP.registrar_direto(con, p["ato_id"], forma="ESPECIE", comprovante="",
                             repassado_em=HOJE, hoje=HOJE, agora=AGORA)


def test_titulo_da_central_nao_se_repassa_direto():
    con = banco()
    p = pago(con)
    with pytest.raises(REP.RepasseError, match="guia do IEPTB"):
        REP.registrar_direto(con, p["ato_id"], forma="DEPOSITO",
                             comprovante="Depósito 1", repassado_em=HOJE,
                             hoje=HOJE, agora=AGORA)


def test_o_mesmo_pagamento_nao_se_repassa_direto_duas_vezes():
    con = banco()
    p = pago(con, origem="MANUAL", saldo="100.00")
    REP.registrar_direto(con, p["ato_id"], forma="ESPECIE", comprovante="Recibo 1",
                         repassado_em=HOJE, hoje=HOJE, agora=AGORA)
    with pytest.raises(REP.RepasseError, match="não está pendente"):
        REP.registrar_direto(con, p["ato_id"], forma="ESPECIE",
                             comprovante="Recibo 2", repassado_em=HOJE,
                             hoje=HOJE, agora=AGORA)


def test_o_banco_recusa_o_segundo_repasse_vivo_do_mesmo_pagamento():
    # A regra mora no índice, e não só na conferência de cima.
    con = banco()
    p = pago(con, origem="MANUAL", saldo="100.00")
    REP.registrar_direto(con, p["ato_id"], forma="ESPECIE", comprovante="Recibo 1",
                         repassado_em=HOJE, hoje=HOJE, agora=AGORA)
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        nativo(con).escrever(
            """INSERT INTO pt_repasses(ato_id, titulo_id, canal, valor_centavos,
                   valor_de, recebido_em, prazo, situacao, criado_em)
               VALUES (%s,%s,'DIRETO',1,'SALDO','2026-10-16','2026-10-19',
                       'REPASSADO',%s)""", (p["ato_id"], p["titulo_id"], AGORA))
