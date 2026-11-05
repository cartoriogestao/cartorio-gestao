# -*- coding: utf-8 -*-
"""A Parcela Express emite um link de Pix, boleto e cartão. Sem rede."""
from __future__ import annotations

import pytest

import cobranca as CB
import cobranca_parcela as PX
from despesas_inter import Resposta

CAMPOS = {"email": "caixa@exemplo.test", "senha": "segredo-ficticio",
          "seller_id": "seller-de-teste"}
COBRANCA = {
    "seu_numero": "2026.11.1", "valor": 15000, "vencimento": "2026-11-10",
    "pagador_nome": "Cliente Exemplo", "pagador_documento": "04785512388",
    "pagador_email": "cliente@exemplo.test",
    "pagador_endereco": '{"logradouro":"Rua de Exemplo","numero":"10",'
                        '"cep":"65936000","cidade":"Cidade Exemplo","uf":"MA",'
                        '"bairro":"Centro"}',
    "mensagem": "Emolumentos do protocolo 2026.11.1",
    "banco_id": "tok-1",
}


class Transporte:
    def __init__(self, respostas: dict):
        self.respostas = respostas
        self.chamadas = []

    def __call__(self, metodo, url, *, json_corpo=None, cabecalhos=None):
        self.chamadas.append((metodo, url, json_corpo, cabecalhos or {}))
        for trecho, resposta in self.respostas.items():
            if trecho in url:
                if isinstance(resposta, Exception):
                    raise resposta
                return resposta
        return Resposta(404, {"message": url})


def _cliente(respostas) -> tuple[PX.ClienteCobrancaParcela, Transporte]:
    t = Transporte(respostas)
    return PX.ClienteCobrancaParcela("sandbox", t, CAMPOS), t


def test_a_emissao_pede_pix_boleto_e_cartao_em_centavos():
    cliente, t = _cliente({
        PX.CAMINHO_DO_TOKEN: Resposta(200, {"access_token": "jwt", "expires_in": 3600}),
        "/v1/payment-links": Resposta(201, {"id": "id-1", "token": "tok-1",
                                            "url": "https://sandbox.parcelaexpress.com.br/l/tok-1",
                                            "status": "active"}),
    })
    assert cliente.emitir(COBRANCA) == "tok-1"
    corpo = t.chamadas[1][2]
    assert corpo["amount"] == 15000
    assert corpo["payment_methods"] == ["pix", "billet", "card"]
    assert corpo["seller_id"] == CAMPOS["seller_id"]
    assert t.chamadas[0][1].startswith(PX.ENDERECOS["sandbox"])
    assert "Bearer jwt" in t.chamadas[1][3]["Authorization"]


def test_o_cartao_pago_vira_recebida():
    lido = PX.ler({
        "token": "tok-1", "url": "https://pay.exemplo/tok-1", "status": "active",
        "sale": {"status": "paid", "form_payment": "credit", "amount": 15000,
                 "updated_at": "2026-11-10T15:00:00Z"},
    })
    assert lido["situacao"] == CB.RECEBIDA
    assert lido["forma_recebida"] == "CARTAO"
    assert lido["valor_recebido"] == 15000
    assert lido["link_pagamento"] == "https://pay.exemplo/tok-1"


def test_o_link_aberto_nao_vira_pago():
    lido = PX.ler({"token": "tok-1", "url": "https://pay.exemplo/tok-1",
                   "status": "active", "sale": {"status": "pending"}})
    assert lido["situacao"] == CB.ABERTA
    assert "forma_recebida" not in lido


def test_o_cancelamento_usa_o_id_do_link():
    cliente, t = _cliente({
        PX.CAMINHO_DO_TOKEN: Resposta(200, {"access_token": "jwt", "expires_in": 3600}),
        "/v1/payment-links/tok-1": Resposta(200, {"id": "id-real", "token": "tok-1",
                                                  "status": "active"}),
        "/cancel": Resposta(200, {}),
    })
    cliente.cancelar(COBRANCA, "cliente desistiu do ato")
    assert any(c[0] == "POST" and c[1].endswith("/id-real/cancel") for c in t.chamadas)


def test_o_pix_vai_para_a_maquininha():
    t = Transporte({
        PX.CAMINHO_DO_TOKEN: Resposta(200, {"access_token": "jwt", "expires_in": 3600}),
        "/v1/pos/payments/": Resposta(201, {"id": "venda-1"}),
    })
    cliente = PX.ClienteCobrancaParcela(
        "sandbox", t, {**CAMPOS, "terminal_id": "S1F2-TESTE"})
    assert cliente.emitir({**COBRANCA, "forma_pedida": "PIX"}) == "pos:venda-1"
    corpo = t.chamadas[1][2]
    assert corpo["terminal_id"] == "S1F2-TESTE"
    assert corpo["is_pix"] is True
    assert corpo["is_debit"] is False
    assert corpo["amount"] == 15000
    assert t.chamadas[1][1].endswith("/v1/pos/payments/" + CAMPOS["seller_id"])


def test_sem_codigo_a_maquininha_recusa():
    cliente, _t = _cliente({
        PX.CAMINHO_DO_TOKEN: Resposta(200, {"access_token": "jwt", "expires_in": 3600}),
    })
    with pytest.raises(PX.Recusa) as erro:
        cliente.emitir({**COBRANCA, "forma_pedida": "CREDITO"})
    assert "maquininha" in str(erro.value)


def test_pagamento_por_fora_pede_afirmacao_e_ciencia():
    cfg = {"cobranca_ligada": "1", "cobranca_banco": "PARCELA"}
    assert CB.instituicao_ligada(cfg).startswith("Parcela")
    with pytest.raises(CB.CobrancaError):
        CB.conferir_pagamento_por_fora(
            "DINHEIRO", cfg, afirmo=False, afirmacao="", ciencia=False)
    motivo = ("o cliente pagou em dinheiro neste atendimento de transicao "
              "porque a maquininha estava sem rede no balcao")
    feito = CB.conferir_pagamento_por_fora(
        "DINHEIRO", cfg, afirmo=True, afirmacao=motivo, ciencia=True)
    assert "dentro do sistema" in feito["ciencia"]
    assert CB.conferir_pagamento_por_fora(
        "GRATUITO", cfg, afirmo=False, afirmacao="", ciencia=False) is None
    assert CB.conferir_pagamento_por_fora(
        "DINHEIRO", {"cobranca_ligada": "0", "cobranca_banco": "PARCELA"},
        afirmo=False, afirmacao="", ciencia=False) is None


def test_o_codigo_da_maquininha_e_opcional():
    sem = PX.conferir_credencial(CAMPOS)
    assert sem["terminal_id"] == ""
    com = PX.conferir_credencial({**CAMPOS, "terminal_id": " POS-01 "})
    assert com["terminal_id"] == "POS-01"
    with pytest.raises(CB.CobrancaError):
        PX.conferir_credencial({**CAMPOS, "terminal_id": "com espaço"})


def test_a_producao_e_a_base_do_portal():
    assert PX.ENDERECOS["producao"] == "https://api-prod.parcelaexpress.com.br"
    assert PX.ENDERECOS["sandbox"].startswith("https://sandbox.")


def test_login_inexistente_diz_o_caminho():
    cliente, _t = _cliente({
        PX.CAMINHO_DO_TOKEN: Resposta(404, {"message": "not found"}),
    })
    with pytest.raises(PX.Recusa) as erro:
        cliente.emitir(COBRANCA)
    assert PX.CAMINHO_DO_TOKEN in str(erro.value)
