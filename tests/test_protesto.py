"""
Testes do Protesto — o cadastro do titulo e o apontamento, ligados ao nucleo.

O QUE ELES CONFEREM
    A regra, e nao "a funcao devolveu alguma coisa":

      - titulo que o contrato da CRA recusa nao entra no banco;
      - titulo de CRA/CENPROT sem chave de origem nao entra — sem ela a
        carga nao e repetivel;
      - reapresentar a mesma (origem, origem_chave) devolve o id que ja
        existe, em vez de duplicar o titulo;
      - o apontamento ocupa lugar no Livro de Apontamento (52 por face, sem
        verso) e muda a situacao do titulo para APONTADO;
      - um titulo nao se aponta duas vezes;
      - a intimacao registra o modo e NAO calcula prazo nenhum — o acervo
        nao tem essa data, e a regra de contagem e do oficial;
      - titulo nao apontado nao se intima; edital sem codigo e recusado;
        intimacao pessoal sem exito seguida de edital sao duas linhas;
      - o protesto ocupa lugar no Livro de Registro de Protestos (1 por
        face, com verso) e exige titulo ja intimado;
      - a desistencia so cabe ANTES do protesto lavrado, e nao ocupa livro;
      - o pagamento cabe em qualquer ponto do ciclo (apontado, intimado ou
        protestado), ocupa o Livro de Registro de Pagamentos (120 por
        folha, sem verso) e recusa titulo em situacao final;
      - o cancelamento so cabe titulo PROTESTADO, exige hipotese do
        catalogo (nao "Erro Material" generico) e fundamento proprio do
        caso, com pelo menos dez letras.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import protesto as PT                            # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from pt_schema import init_pt_schema             # noqa: E402

AGORA = "2026-08-24T09:00:00"
EXTENSO = "vinte e quatro dias do mês de agosto do ano de dois mil e vinte e seis"
SV = {
    "unit_name": "SERVENTIA EXTRAJUDICIAL DO OFÍCIO ÚNICO DE CIDADE EXEMPLO",
    "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
    "serventia_titulo": "Tabelião e Oficial de Registro",
    "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
}


def banco() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


def titulo_bom() -> dict:
    """O mesmo titulo de `test_protesto_cra.titulo_bom()` — real, mascarado."""
    return {
        "especie": "DMI",
        "numero_titulo": "84713/1",
        "data_emissao": "2022-07-21",
        "data_vencimento": "2022-09-05",
        "valor": "1482.78",
        "saldo": "1482.78",
        "praca_protesto": "CIDADE EXEMPLO",
        "tipo_moeda": "1",
        "tipo_protesto": "C",
        "motivo_protesto": "1",
        "cedente": {"nome": "«mascarado»", "documento": "00000000000000",
                   "cidade": "Cidade Exemplo", "uf": "MA"},
        "devedores": [{"nome": "«mascarado»", "CNPJ": "00000000000000",
                      "enderecos": [{"endereco": "Rua X", "bairro": "Centro",
                                    "cidade": "Cidade Exemplo", "uf": "MA"}]}],
    }


# --------------------------------------------------------------- o cadastro


def test_cadastra_titulo_em_ordem():
    con = banco()
    titulo_id = PT.cadastrar_titulo(con, titulo_bom(), origem="MANUAL", agora=AGORA)
    tit = PT.titulo(con, titulo_id)
    assert tit["especie"] == "DMI"
    assert tit["numero_titulo"] == "84713/1"
    assert tit["valor_centavos"] == 148278
    assert tit["saldo_centavos"] == 148278
    assert tit["situacao"] == "RECEBIDO"
    devedores = PT.devedores_do(con, titulo_id)
    assert len(devedores) == 1
    assert devedores[0]["documento_tipo"] == "CNPJ"
    assert devedores[0]["cidade"] == "Cidade Exemplo"


def test_titulo_que_o_contrato_da_cra_recusa_nao_entra():
    con = banco()
    ruim = titulo_bom()
    ruim["devedores"] = []
    with pytest.raises(PT.ProtestoError) as erro:
        PT.cadastrar_titulo(con, ruim, origem="MANUAL", agora=AGORA)
    assert "ao menos um devedor" in str(erro.value)
    assert con.execute("SELECT COUNT(*) n FROM pt_titulos").fetchone()["n"] == 0


def test_titulo_de_cra_sem_chave_de_origem_e_recusado():
    con = banco()
    with pytest.raises(PT.ProtestoError) as erro:
        PT.cadastrar_titulo(con, titulo_bom(), origem="CRA", agora=AGORA)
    assert "chave de origem" in str(erro.value)


def test_origem_desconhecida_e_recusada():
    con = banco()
    with pytest.raises(PT.ProtestoError):
        PT.cadastrar_titulo(con, titulo_bom(), origem="SERASA", agora=AGORA)


def test_carga_e_repetivel_por_construcao():
    # A mesma chave de origem duas vezes devolve o MESMO id, nao duplica.
    con = banco()
    id1 = PT.cadastrar_titulo(con, titulo_bom(), origem="CRA",
                              origem_chave="REMESSA-1:84713/1", agora=AGORA)
    id2 = PT.cadastrar_titulo(con, titulo_bom(), origem="CRA",
                              origem_chave="REMESSA-1:84713/1", agora=AGORA)
    assert id1 == id2
    assert con.execute("SELECT COUNT(*) n FROM pt_titulos").fetchone()["n"] == 1


# ----------------------------------------------------------- o apontamento


def test_lanca_apontamento_e_ocupa_o_livro():
    con = banco()
    titulo_id = PT.cadastrar_titulo(con, titulo_bom(), origem="MANUAL", agora=AGORA)
    lugar = PT.lancar_apontamento(con, titulo_id, sv=SV, agora=AGORA,
                                  data_extenso=EXTENSO, usuario="TESTE")
    assert lugar["numero_ordem"] == 1
    assert lugar["folha"] == 1
    assert lugar["verso"] is False

    ato = PT.atos_do(con, titulo_id)[0]
    assert ato["tipo"] == "APONTAMENTO"
    assert ato["folha"] == 1
    assert ato["numero_ordem"] == 1

    tit = PT.titulo(con, titulo_id)
    assert tit["situacao"] == "APONTADO"


def test_cinquenta_e_dois_apontamentos_cabem_numa_face_so():
    # PT_APONTAMENTO: 52 por face, sem verso — medido no acervo em 21/08/2026.
    con = banco()
    for i in range(52):
        titulo_id = PT.cadastrar_titulo(
            con, titulo_bom(), origem="CRA", origem_chave=f"LOTE:{i}", agora=AGORA)
        lugar = PT.lancar_apontamento(con, titulo_id, sv=SV, agora=AGORA,
                                      data_extenso=EXTENSO)
        assert lugar["folha"] == 1
    # O quinquagesimo terceiro vai para a folha seguinte.
    titulo_id = PT.cadastrar_titulo(
        con, titulo_bom(), origem="CRA", origem_chave="LOTE:52", agora=AGORA)
    lugar = PT.lancar_apontamento(con, titulo_id, sv=SV, agora=AGORA,
                                  data_extenso=EXTENSO)
    assert lugar["folha"] == 2
    assert lugar["numero_ordem"] == 53


def test_nao_aponta_titulo_inexistente():
    con = banco()
    with pytest.raises(PT.ProtestoError, match="não encontrado"):
        PT.lancar_apontamento(con, 999, sv=SV, agora=AGORA, data_extenso=EXTENSO)


def test_nao_aponta_duas_vezes():
    con = banco()
    titulo_id = PT.cadastrar_titulo(con, titulo_bom(), origem="MANUAL", agora=AGORA)
    PT.lancar_apontamento(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    with pytest.raises(PT.ProtestoError, match="não se aponta de novo"):
        PT.lancar_apontamento(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)


# ------------------------------------------------------------ a intimacao


def _titulo_apontado(con) -> int:
    titulo_id = PT.cadastrar_titulo(con, titulo_bom(), origem="MANUAL", agora=AGORA)
    PT.lancar_apontamento(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    return titulo_id


def test_intimacao_pessoal_registra_e_nao_calcula_prazo():
    con = banco()
    titulo_id = _titulo_apontado(con)
    resultado = PT.lancar_intimacao(con, titulo_id, modo="PESSOAL", agora=AGORA,
                                    comprovante="AR 123, assinado por João")
    assert resultado["modo"] == "PESSOAL"

    ato = PT.atos_do(con, titulo_id)[-1]
    assert ato["tipo"] == "INTIMACAO"
    # A igualdade exata prova que nenhum campo de prazo ou vencimento entrou.
    detalhe = json.loads(ato["detalhe_json"])
    assert detalhe == {"modo": "PESSOAL", "digital": False,
                       "comprovante": "AR 123, assinado por João"}

    tit = PT.titulo(con, titulo_id)
    assert tit["situacao"] == "INTIMADO"


def test_intimacao_por_edital_exige_codigo():
    con = banco()
    titulo_id = _titulo_apontado(con)
    with pytest.raises(PT.ProtestoError, match="código do edital"):
        PT.lancar_intimacao(con, titulo_id, modo="EDITAL", agora=AGORA)


def test_intimacao_por_edital_com_codigo():
    con = banco()
    titulo_id = _titulo_apontado(con)
    resultado = PT.lancar_intimacao(con, titulo_id, modo="EDITAL", agora=AGORA,
                                    codigo_edital="ED-2026-014")
    assert resultado["codigo_edital"] == "ED-2026-014"


def test_modo_de_intimacao_desconhecido_e_recusado():
    con = banco()
    titulo_id = _titulo_apontado(con)
    with pytest.raises(PT.ProtestoError, match="Modo de intimação desconhecido"):
        PT.lancar_intimacao(con, titulo_id, modo="TELEFONE", agora=AGORA)


def test_nao_intima_titulo_que_ainda_nao_foi_apontado():
    con = banco()
    titulo_id = PT.cadastrar_titulo(con, titulo_bom(), origem="MANUAL", agora=AGORA)
    with pytest.raises(PT.ProtestoError, match="só se intima título já apontado"):
        PT.lancar_intimacao(con, titulo_id, modo="PESSOAL", agora=AGORA)


def test_intimacao_pessoal_sem_exito_seguida_de_edital_sao_duas_linhas():
    con = banco()
    titulo_id = _titulo_apontado(con)
    PT.lancar_intimacao(con, titulo_id, modo="PESSOAL", agora=AGORA,
                        comprovante="não encontrado no endereço")
    PT.lancar_intimacao(con, titulo_id, modo="EDITAL", agora=AGORA,
                        codigo_edital="ED-2026-014")
    intimacoes = [a for a in PT.atos_do(con, titulo_id) if a["tipo"] == "INTIMACAO"]
    assert len(intimacoes) == 2
    assert PT.titulo(con, titulo_id)["situacao"] == "INTIMADO"


# --------------------------------------------------- o protesto e a desistencia


def _titulo_intimado(con) -> int:
    titulo_id = _titulo_apontado(con)
    PT.lancar_intimacao(con, titulo_id, modo="PESSOAL", agora=AGORA,
                        comprovante="AR 123")
    return titulo_id


def test_lanca_protesto_e_ocupa_o_livro_de_registro_de_protestos():
    con = banco()
    titulo_id = _titulo_intimado(con)
    lugar = PT.lancar_protesto(con, titulo_id, sv=SV, agora=AGORA,
                              data_extenso=EXTENSO, usuario="TESTE")
    assert lugar["numero_ordem"] == 1
    assert lugar["folha"] == 1
    assert lugar["verso"] is False

    ato = next(a for a in PT.atos_do(con, titulo_id) if a["tipo"] == "PROTESTO")
    assert ato["folha"] == 1
    assert ato["verso"] == 0

    assert PT.titulo(con, titulo_id)["situacao"] == "PROTESTADO"


def test_o_segundo_protesto_vai_para_o_verso_da_mesma_folha():
    # PT_PROTESTO: 1 por FACE, com verso, sem folha nova — medido no acervo:
    # os livros 7 e 8 fecharam com mais registros que folhas.
    con = banco()
    t1 = _titulo_intimado(con)
    PT.lancar_protesto(con, t1, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    t2 = _titulo_intimado(con)
    lugar2 = PT.lancar_protesto(con, t2, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    assert lugar2["folha"] == 1
    assert lugar2["verso"] is True


def test_nao_protesta_titulo_que_nao_foi_intimado():
    con = banco()
    titulo_id = _titulo_apontado(con)
    with pytest.raises(PT.ProtestoError, match="só se protesta título já intimado"):
        PT.lancar_protesto(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)


def test_nao_protesta_duas_vezes():
    con = banco()
    titulo_id = _titulo_intimado(con)
    PT.lancar_protesto(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    with pytest.raises(PT.ProtestoError, match="só se protesta título já intimado"):
        PT.lancar_protesto(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)


def test_lanca_desistencia_antes_do_protesto():
    con = banco()
    titulo_id = _titulo_intimado(con)
    resultado = PT.lancar_desistencia(con, titulo_id, motivo="Credor pagou por fora",
                                      agora=AGORA)
    assert resultado["motivo"] == "Credor pagou por fora"
    assert PT.titulo(con, titulo_id)["situacao"] == "DESISTIDO"
    ato = next(a for a in PT.atos_do(con, titulo_id) if a["tipo"] == "DESISTENCIA")
    assert ato["livro_id"] is None


def test_desistencia_exige_motivo():
    con = banco()
    titulo_id = _titulo_apontado(con)
    with pytest.raises(PT.ProtestoError, match="motivo da desistência"):
        PT.lancar_desistencia(con, titulo_id, motivo="  ", agora=AGORA)


def test_nao_desiste_de_protesto_ja_lavrado():
    con = banco()
    titulo_id = _titulo_intimado(con)
    PT.lancar_protesto(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    with pytest.raises(PT.ProtestoError, match="antes do protesto lavrado"):
        PT.lancar_desistencia(con, titulo_id, motivo="Credor pagou por fora", agora=AGORA)


# ------------------------------------------------------------- o pagamento


@pytest.mark.parametrize("preparar", ["apontado", "intimado", "protestado"])
def test_lanca_pagamento_em_qualquer_ponto_do_ciclo(preparar):
    con = banco()
    if preparar == "apontado":
        titulo_id = _titulo_apontado(con)
    elif preparar == "intimado":
        titulo_id = _titulo_intimado(con)
    else:
        titulo_id = _titulo_intimado(con)
        PT.lancar_protesto(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)

    lugar = PT.lancar_pagamento(con, titulo_id, sv=SV, agora=AGORA,
                               data_extenso=EXTENSO, valor_pago="1482.78")
    assert lugar["folha"] == 1
    assert lugar["verso"] is False

    ato = next(a for a in PT.atos_do(con, titulo_id) if a["tipo"] == "PAGAMENTO")
    detalhe = json.loads(ato["detalhe_json"])
    assert detalhe == {"valor_pago_centavos": 148278}

    assert PT.titulo(con, titulo_id)["situacao"] == "PAGO"


def test_cento_e_vinte_pagamentos_cabem_numa_folha_so():
    # PT_PAGAMENTO: 120 por folha, sem verso — medido no acervo (Livro 1,
    # ordens 826 a 2145 em 11 folhas, exatamente 120 por folha).
    con = banco()
    for i in range(120):
        titulo_id = PT.cadastrar_titulo(
            con, titulo_bom(), origem="CRA", origem_chave=f"PAG:{i}", agora=AGORA)
        lugar = PT.lancar_pagamento(con, titulo_id, sv=SV, agora=AGORA,
                                    data_extenso=EXTENSO)
        assert lugar["folha"] == 1
    titulo_id = PT.cadastrar_titulo(
        con, titulo_bom(), origem="CRA", origem_chave="PAG:120", agora=AGORA)
    lugar = PT.lancar_pagamento(con, titulo_id, sv=SV, agora=AGORA,
                               data_extenso=EXTENSO)
    assert lugar["folha"] == 2
    assert lugar["numero_ordem"] == 121


@pytest.mark.parametrize("situacao_final", ["PAGO", "DESISTIDO"])
def test_nao_paga_titulo_em_situacao_final(situacao_final):
    con = banco()
    titulo_id = _titulo_apontado(con)
    if situacao_final == "PAGO":
        PT.lancar_pagamento(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    else:
        PT.lancar_desistencia(con, titulo_id, motivo="erro na apresentação",
                              agora=AGORA)
    with pytest.raises(PT.ProtestoError, match="não há como registrar pagamento"):
        PT.lancar_pagamento(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)


def test_pagamento_sem_valor_informado_grava_detalhe_vazio():
    con = banco()
    titulo_id = _titulo_apontado(con)
    PT.lancar_pagamento(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    ato = next(a for a in PT.atos_do(con, titulo_id) if a["tipo"] == "PAGAMENTO")
    assert json.loads(ato["detalhe_json"]) == {}


# ---------------------------------------------------------- o cancelamento


def _titulo_protestado(con) -> int:
    titulo_id = _titulo_intimado(con)
    PT.lancar_protesto(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    return titulo_id


@pytest.mark.parametrize("hipotese", list(PT.CATALOGO_CANCELAMENTO))
def test_cancela_com_cada_hipotese_do_catalogo(hipotese):
    con = banco()
    titulo_id = _titulo_protestado(con)
    resultado = PT.lancar_cancelamento(
        con, titulo_id, hipotese=hipotese,
        fundamento="Conferido o título apresentado pela parte interessada.",
        agora=AGORA)
    assert resultado["hipotese"] == hipotese
    assert resultado["fundamento_legal"] == PT.CATALOGO_CANCELAMENTO[hipotese]["fundamento_legal"]
    assert PT.titulo(con, titulo_id)["situacao"] == "CANCELADO"


def test_hipotese_fora_do_catalogo_e_recusada():
    con = banco()
    titulo_id = _titulo_protestado(con)
    with pytest.raises(PT.ProtestoError, match="Hipótese de cancelamento desconhecida"):
        PT.lancar_cancelamento(con, titulo_id, hipotese="ERRO_MATERIAL",
                               fundamento="Título já pago antes do protesto.",
                               agora=AGORA)


def test_cancelamento_exige_fundamento_proprio():
    con = banco()
    titulo_id = _titulo_protestado(con)
    with pytest.raises(PT.ProtestoError, match="fundamento do cancelamento"):
        PT.lancar_cancelamento(con, titulo_id, hipotese="PAGAMENTO",
                               fundamento="ok", agora=AGORA)


def test_nao_cancela_titulo_que_nao_foi_protestado():
    con = banco()
    titulo_id = _titulo_intimado(con)
    with pytest.raises(PT.ProtestoError, match="só se cancela protesto já lavrado"):
        PT.lancar_cancelamento(con, titulo_id, hipotese="PAGAMENTO",
                               fundamento="Título pago antes do protesto.",
                               agora=AGORA)
