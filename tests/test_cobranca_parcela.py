# -*- coding: utf-8 -*-
"""A Parcela Express emite um link de Pix, boleto e cartão. Sem rede."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest

import cobranca as CB
import cobranca_parcela as PX
from bd_nativo import banco
from despesas_inter import Resposta

AGORA = datetime(2026, 11, 5, 15, 0, tzinfo=timezone(timedelta(hours=-3)))
PAGADOR = {"nome": "FULANA DE TAL", "documento": "000.000.001-91", "email": "",
           "logradouro": "Rua Um", "numero": "10", "complemento": "", "bairro": "Centro",
           "cidade": "Cidade Exemplo", "uf": "MA", "cep": "65000-000"}

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


# ------------------------------------- o caixa geral (oficial, 05/11/2026)

def _abrir_caixa(con, operador: str, dia: str) -> int:
    return int(banco(con).escrever(
        """INSERT INTO cx_caixas (data, operador_nome, aberto_em, situacao)
           VALUES (%s, %s, %s, 'ABERTO') RETURNING id""",
        (dia, operador, f"{dia}T08:00:00"))[0]["id"])


def _cobranca_paga(db, protocolo_id: int) -> int:
    with db.transaction() as con:
        i = CB.cadastrar(
            con, agora=AGORA, por="balcao", banco_codigo=CB.PARCELA, ambiente="sandbox",
            protocolo_id=protocolo_id, valor_centavos=12345, vencimento="2026-11-20",
            pagador=PAGADOR, mensagem="Emolumentos.", forma_pedida="PIX")
        CB.gravar_resposta(con, i, {
            "situacao": CB.RECEBIDA, "banco_id": "pos:venda-1", "valor_recebido": 12345,
            "data_pagamento": "2026-11-05", "forma_recebida": "PIX",
            "banco_status": "PAID"}, por="automação", agora=AGORA)
    return i


@pytest.fixture
def protocolo(cg_casa_logada):
    db = cg_casa_logada["db"]
    with db.transaction() as con:
        p = banco(con).escrever(
            """INSERT INTO cx_protocolos (numero, data_abertura, interessado,
                   interessado_documento, criado_em)
               VALUES ('2026.11.900', '2026-11-05', 'FULANA DE TAL', '00000000191',
                       '2026-11-05T09:00:00') RETURNING id""", ())
        protocolo_id = int(p[0]["id"])
        banco(con).escrever(
            """INSERT INTO cx_protocolo_atos (protocolo_id, descricao, valor_total)
               VALUES (%s, 'Certidão', '123,45')""", (protocolo_id,))
    return {**cg_casa_logada, "protocolo_id": protocolo_id}


def _quitado(db, protocolo_id: int) -> int:
    with db.connect() as con:
        linha = banco(con).um(
            "SELECT COALESCE(quitado, 0) AS quitado FROM cx_protocolo_atos WHERE protocolo_id = %s",
            (protocolo_id,))
    return int(linha["quitado"])


def test_paga_com_caixa_geral_aberto_entra_e_nao_quita(protocolo):
    db, pid = protocolo["db"], protocolo["protocolo_id"]
    with db.transaction() as con:
        geral = _abrir_caixa(con, CB.OPERADOR_DO_CAIXA_GERAL, "2026-11-05")
        escrevente = _abrir_caixa(con, "ESCREVENTE EXEMPLO", "2026-11-05")
    i = _cobranca_paga(db, pid)
    with db.connect() as con:
        c = CB.cobranca(con, i)
        dep = banco(con).um("SELECT * FROM cx_depositos WHERE id = %s", (c["deposito_id"],))
        lanc = banco(con).um("SELECT * FROM cx_lancamentos WHERE id = %s", (dep["lancamento_id"],))
        no_escrevente = banco(con).um(
            "SELECT id FROM cx_lancamentos WHERE caixa_id = %s", (escrevente,))
    assert c["situacao"] == CB.LANCADA
    assert lanc["caixa_id"] == geral and lanc["forma_pagamento"] == "PIX"
    assert dep["protocolo_id"] == pid
    assert no_escrevente is None
    assert _quitado(db, pid) == 0


def test_sem_caixa_geral_fica_pendente_mesmo_com_caixa_de_escrevente(protocolo):
    db, pid = protocolo["db"], protocolo["protocolo_id"]
    with db.transaction() as con:
        escrevente = _abrir_caixa(con, "ESCREVENTE EXEMPLO", "2026-11-05")
        ontem = _abrir_caixa(con, CB.OPERADOR_DO_CAIXA_GERAL, "2026-11-04")
    i = _cobranca_paga(db, pid)
    with db.connect() as con:
        c = CB.cobranca(con, i)
        depositos = banco(con).ler("SELECT id FROM cx_depositos WHERE protocolo_id = %s", (pid,))
        lancamentos = banco(con).ler(
            "SELECT id FROM cx_lancamentos WHERE caixa_id IN (%s, %s)", (escrevente, ontem))
    assert c["situacao"] == CB.RECEBIDA and not c["deposito_id"]
    assert depositos == [] and lancamentos == []
    assert _quitado(db, pid) == 0
    with db.transaction() as con, pytest.raises(CB.CobrancaError, match="caixa geral"):
        CB.lancar_no_caixa(con, i, por="balcao", agora=AGORA, caixa_id=escrevente)


def test_ao_abrir_o_caixa_geral_o_pendente_entra_e_nao_quita(protocolo):
    db, pid = protocolo["db"], protocolo["protocolo_id"]
    i = _cobranca_paga(db, pid)
    with db.transaction() as con:
        assert CB.recolher_no_caixa_geral(con, por="balcao", agora=AGORA) == []
        _abrir_caixa(con, CB.OPERADOR_DO_CAIXA_GERAL, "2026-11-05")
        feitos = CB.recolher_no_caixa_geral(con, por="balcao", agora=AGORA)
        de_novo = CB.recolher_no_caixa_geral(con, por="balcao", agora=AGORA)
    assert len(feitos) == 1 and de_novo == []
    with db.connect() as con:
        assert CB.cobranca(con, i)["situacao"] == CB.LANCADA
    assert _quitado(db, pid) == 0


def test_a_tela_abre_o_caixa_geral_e_recolhe_o_pendente(protocolo):
    db, pid, c = protocolo["db"], protocolo["protocolo_id"], protocolo["c"]
    i = _cobranca_paga(db, pid)
    pagina = c.get("/caixa").get_data(as_text=True)
    assert "Abrir o caixa geral de hoje" in pagina
    assert "Lançar no meu caixa" not in c.get(f"/caixa/cobranca/{i}").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', pagina).group(1)
    r = c.post("/caixa", data={"csrf_token": token, "acao": "abrir_geral"}, follow_redirects=True)
    assert r.status_code == 200
    assert "Caixa geral aberto" in r.get_data(as_text=True)
    with db.connect() as con:
        cobranca = CB.cobranca(con, i)
        caixa = CB.caixa_geral_de_hoje(con, datetime.now().date())
    assert cobranca["situacao"] == CB.LANCADA and caixa
    assert _quitado(db, pid) == 0
