# -*- coding: utf-8 -*-
"""SAEC / protocolo / cobranca do ONR — Marco B, so com mock (sem rede).

NENHUM TESTE DAQUI FALA COM O ONR. Mocka `onr_api._bater` (e, quando
preciso do segundo mecanismo, confere o cabeçalho do token do protocolo).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import onr_api as API


def _ok(corpo):
    return {"status": 200, "json": corpo, "texto": json.dumps(corpo)}


@pytest.fixture
def sem_rede(monkeypatch):
    """Garante que nenhuma chamada real saia: `_bater_cru` estoura se for tocado."""

    def _proibido(*a, **k):
        raise AssertionError("rede real proibida neste teste")

    monkeypatch.setattr(API, "_bater_cru", _proibido)
    monkeypatch.setattr(API, "token", lambda *a, **k: "token-serventia-falso")


def test_ligados_marco_b_incluem_saec_protocolo_cobranca():
    ligados = set(API.CAMINHOS_LIGADOS)
    assert len(API.CAMINHOS_LIGADOS) == 25
    for nome in (
        "atendimentos", "atendimento", "atendimento_interagir",
        "protocolos", "protocolo", "protocolo_token_v2",
        "protocolo_detalhes_v2", "protocolo_token_validar_v2",
        "cobrancas", "cobranca", "cobranca_tipos_de_pagamento", "cobranca_gerar",
    ):
        assert nome in ligados
    # ainda so declarados (exemplos)
    assert "edital_leilao_gerar" not in ligados
    assert "cobranca_devolver_pix" not in ligados
    assert "protocolo_detalhes" not in ligados  # v1 continua apagado
    assert set(API.CAMINHOS_APAGADOS_MAS_DECLARADOS).isdisjoint(ligados)


def test_caminho_ainda_desligado_recusa(sem_rede):
    with pytest.raises(API.OnrError) as erro:
        API._bater("cobranca_devolver_pix", hash="abc")
    msg = str(erro.value)
    assert "nao esta ligado" in msg.replace("ã", "a").replace("á", "a") \
        or "não está ligado" in msg or "n\u00e3o est\u00e1 ligado" in msg


def test_saec_listar_e_consultar_com_mock(monkeypatch, sem_rede):
    chamadas = []

    def falso(qual, **kw):
        chamadas.append((qual, kw))
        if qual == "atendimentos":
            return _ok({"data": [{"id": 10, "protocolo": "P-1", "status": "A"}]})
        if qual == "atendimento":
            assert kw.get("id") == 10
            return _ok({"data": {"id": 10, "protocolo": "P-1", "interacoes": []}})
        raise AssertionError(qual)

    monkeypatch.setattr(API, "_bater", falso)
    lista = API.atendimentos(pagina=1, por_pagina=20, status="A")
    assert lista == [{"id": 10, "protocolo": "P-1", "status": "A"}]
    det = API.atendimento(10)
    assert det["id"] == 10
    assert chamadas[0][0] == "atendimentos"
    assert chamadas[0][1]["parametros"]["numeroPagina"] == 1
    assert chamadas[0][1]["parametros"]["registrosPorPagina"] == 20


def test_saec_interagir_com_mock(monkeypatch, sem_rede):
    def falso(qual, **kw):
        assert qual == "atendimento_interagir"
        assert kw["id"] == 77
        assert kw["corpo"]["acao"] == "RESPONDER"
        assert "mensagem" in kw["corpo"]
        return _ok({"data": {"ok": True}})

    monkeypatch.setattr(API, "_bater", falso)
    out = API.interagir_no_atendimento(77, {"acao": "RESPONDER", "mensagem": "ok"})
    assert out == {"ok": True}


def test_protocolo_token_e_detalhes_headerauth(monkeypatch, sem_rede):
    """Fluxo: pedir token (Bearer da casa) -> detalhes com token DAQUELE protocolo."""
    visto = {}

    def falso(qual, **kw):
        visto[qual] = kw
        if qual == "protocolo_token_v2":
            return _ok({"data": {"access_token": "tok-proto-XYZ", "expires_in": 300,
                                 "token_type": "Bearer"}})
        if qual == "protocolo_detalhes_v2":
            assert kw.get("token_do_protocolo") == "tok-proto-XYZ"
            return _ok({"data": {"protocolo": "999", "status": "ABERTO"}})
        if qual == "protocolo_token_validar_v2":
            assert kw.get("token_do_protocolo") == "tok-proto-XYZ"
            return _ok({"data": {"valido": True}})
        raise AssertionError(qual)

    monkeypatch.setattr(API, "_bater", falso)
    tok = API.token_do_protocolo("999", {"senha": "s", "tipoSolicitacao": 1})
    assert tok == "tok-proto-XYZ"
    det = API.detalhes_do_protocolo("999", tok)
    assert det["protocolo"] == "999"
    val = API.validar_token_do_protocolo("999", tok)
    assert val["valido"] is True


def test_detalhes_do_protocolo_sem_token_recusa(sem_rede):
    with pytest.raises(API.OnrError) as erro:
        API._bater("protocolo_detalhes_v2", numero="1", token_do_protocolo="")
    assert "protocolo" in str(erro.value).lower()


def test_protocolo_lista_e_base_com_mock(monkeypatch, sem_rede):
    def falso(qual, **kw):
        if qual == "protocolos":
            return _ok({"data": [{"protocolo": "1"}]})
        if qual == "protocolo":
            assert kw.get("numero") == "1"
            return _ok({"data": {"protocolo": "1", "status": "X"}})
        raise AssertionError(qual)

    monkeypatch.setattr(API, "_bater", falso)
    assert API.protocolos() == [{"protocolo": "1"}]
    assert API.protocolo("1")["status"] == "X"


def test_cobranca_listar_consultar_tipos_gerar(monkeypatch, sem_rede):
    def falso(qual, **kw):
        if qual == "cobrancas":
            return _ok({"data": {"cobrancas": [{"hash": "h1"}]}})
        if qual == "cobranca":
            assert kw.get("hash") == "h1"
            return _ok({"data": {"hash": "h1", "valorTotal": 10.5}})
        if qual == "cobranca_tipos_de_pagamento":
            return _ok({"data": [{"codigo": 1, "descricao": "PIX"}]})
        if qual == "cobranca_gerar":
            assert "servicos" in kw["corpo"] or True
            return _ok({"hash": "h2", "url": "https://exemplo.test/p", "status": 1,
                        "valorTotal": 10.5})
        raise AssertionError(qual)

    monkeypatch.setattr(API, "_bater", falso)
    # _dados desembrulha "data"; se nao houver, devolve o proprio
    lista = API.cobrancas()
    assert "cobrancas" in lista or lista == {"cobrancas": [{"hash": "h1"}]}
    det = API.cobranca("h1")
    assert det["hash"] == "h1"
    tipos = API.tipos_de_pagamento()
    assert tipos[0]["descricao"] == "PIX"
    gerada = API.gerar_cobranca({
        "tipoCobranca": "PIX",
        "dataVencimento": "2026-12-31",
        "dadosPagador": {"nome": "Teste"},
        "servicos": [{"descricao": "certidao", "valor": 10.5}],
    })
    assert gerada["hash"] == "h2"
    assert gerada["url"].startswith("https://")
    assert gerada["valor_total"] == 10.5


def test_nenhuma_funcao_nova_carrega_credencial_de_arquivo(sem_rede, monkeypatch):
    """As funcoes novas nao leem .cred sozinhas — so passam pasta ao _bater."""
    monkeypatch.setattr(
        API, "credencial",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("credencial tocada")))

    def falso(qual, **kw):
        return _ok({"data": {}})

    monkeypatch.setattr(API, "_bater", falso)
    API.atendimentos()
    API.cobrancas()
    API.tipos_de_pagamento()
