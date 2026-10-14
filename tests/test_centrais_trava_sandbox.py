"""Trava de seguranca do sandbox — deny-list + desvio para simulador.

Nenhum teste fala com a internet. Probe TCP e substitudo; a marca
CARTORIO_GESTAO_SANDBOX e ligada/desligada no proprio teste.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import centrais_http as HTTP  # noqa: E402
import centrais_trava_sandbox as TRAVA  # noqa: E402


@pytest.fixture(autouse=True)
def _limpa_marca(monkeypatch):
    monkeypatch.delenv(TRAVA.MARCA, raising=False)
    monkeypatch.delenv(TRAVA.VAR_DADOS, raising=False)
    yield


def test_fora_do_sandbox_url_intacta():
    url = "https://sirc.dataprev.gov.br/SircWs/Movimento"
    assert TRAVA.proteger_url(url) == url


def test_marca_forca_sirc_para_8917(monkeypatch):
    monkeypatch.setenv(TRAVA.MARCA, "1")
    monkeypatch.setattr(TRAVA, "_porta_aberta", lambda h, p: True)
    url = TRAVA.proteger_url("https://sirc.dataprev.gov.br/SircWs/Movimento")
    assert url == "https://127.0.0.1:8917/SircWs/Movimento"


def test_dados_sandbox_armam_trava(monkeypatch):
    monkeypatch.setenv(
        TRAVA.VAR_DADOS,
        r"C:\x\CartorioGestao\SANDBOX\dados")
    monkeypatch.setattr(TRAVA, "_porta_aberta", lambda h, p: True)
    assert TRAVA.destino_seguro("wsh.registrocivil.org.br", 443) == (
        "127.0.0.1", 8917)


def test_recusa_se_simulador_sirc_fora(monkeypatch):
    monkeypatch.setenv(TRAVA.MARCA, "1")
    monkeypatch.setattr(TRAVA, "_porta_aberta", lambda h, p: False)
    with pytest.raises(TRAVA.SandboxTravaRecusou) as exc:
        TRAVA.proteger_url("https://sirc.dataprev.gov.br/SircWs/Movimento")
    assert "8917" in str(exc.value)
    assert "RECUSADA" in str(exc.value)


def test_crc_onrcpn_resolve_cenprot_cra(monkeypatch):
    monkeypatch.setenv(TRAVA.MARCA, "1")
    monkeypatch.setattr(TRAVA, "_porta_aberta", lambda h, p: True)
    casos = [
        ("ws.registrocivil.org.br", 8917),
        ("servicosh.registrocivil.org.br", 8915),
        ("api.resolve.cenprot.org.br", 8912),
        ("wspub.cenprotnacional.org.br", 8911),
        ("crama.crabr.com.br", 8910),
    ]
    for host, porta in casos:
        assert TRAVA.destino_seguro(host, 443) == ("127.0.0.1", porta)


def test_deny_list_notas_imoveis_sem_simulador(monkeypatch):
    monkeypatch.setenv(TRAVA.MARCA, "1")
    for host in (
        "api.registrodeimoveis.org.br",
        "serventia-api.onr.org.br",
        "auth.id.onr.org.br",
        "pessoas.e-notariado.org.br",
    ):
        with pytest.raises(TRAVA.SandboxTravaRecusou) as exc:
            TRAVA.destino_seguro(host, 443)
        assert "deny-list" in str(exc.value) or "PRODUCAO" in str(exc.value)


def test_homolog_notas_liberada(monkeypatch):
    monkeypatch.setenv(TRAVA.MARCA, "1")
    assert TRAVA.destino_seguro("testes-api.registrodeimoveis.org.br", 443)[0] == (
        "testes-api.registrodeimoveis.org.br")
    assert TRAVA.destino_seguro("pessoas-hml.e-notariado.org.br", 443)[0] == (
        "pessoas-hml.e-notariado.org.br")


def test_registrar_host_producao_deny_e_simulador(monkeypatch):
    monkeypatch.setenv(TRAVA.MARCA, "1")
    monkeypatch.setattr(TRAVA, "_porta_aberta", lambda h, p: True)
    TRAVA.registrar_host_producao("exemplo-central.teste.local")
    with pytest.raises(TRAVA.SandboxTravaRecusou):
        TRAVA.destino_seguro("exemplo-central.teste.local", 443)
    TRAVA.registrar_host_producao(
        "exemplo-central.teste.local", porta_simulador=8999)
    assert TRAVA.destino_seguro("exemplo-central.teste.local", 443) == (
        "127.0.0.1", 8999)
    # limpa para nao vazar estado entre testes do processo
    with TRAVA._lock:
        TRAVA._HOSTS_PARA_SIMULADOR.pop("exemplo-central.teste.local", None)
        TRAVA._HOSTS_PRODUCAO_RECUSAR.discard("exemplo-central.teste.local")


def test_centrais_http_unico_gancho_reescreve_sirc(monkeypatch):
    monkeypatch.setenv(TRAVA.MARCA, "1")
    monkeypatch.setattr(TRAVA, "_porta_aberta", lambda h, p: True)
    visto = {}

    class _Fake:
        def request(self, *a, **k):
            pass
        def getresponse(self):
            class R:
                status = 200
                def read(self_inner):
                    return b"{}"
                def getheaders(self_inner):
                    return []
            return R()
        def close(self):
            pass

    def _abrir(esquema, host, porta, prazo, contexto):
        visto["host"] = host
        visto["porta"] = porta
        return _Fake()

    monkeypatch.setattr(HTTP, "_abrir_conexao", _abrir)
    r = HTTP.requisitar(
        "POST", "https://sirc.dataprev.gov.br/SircWs/Movimento",
        corpo=b"<x/>", tentativas=0)
    assert visto["host"] == "127.0.0.1"
    assert visto["porta"] == 8917
    assert r.status == 200


def test_centrais_http_recusa_deny_onr(monkeypatch):
    monkeypatch.setenv(TRAVA.MARCA, "1")
    with pytest.raises(HTTP.CentralHttpError) as exc:
        HTTP.requisitar(
            "GET", "https://api.registrodeimoveis.org.br/v1/x",
            tentativas=0)
    assert "RECUSADA" in str(exc.value) or "deny" in str(exc.value).lower()


# --- Notas/Imóveis (ONR/SAEC, CNIB, CCN): cobertura extra sobre a deny-list RCPN ---

HOSTS_PROD_NOTAS_RI = (
    "api.registrodeimoveis.org.br",
    "serventia-api.onr.org.br",
    "auth.id.onr.org.br",
    "pessoas.e-notariado.org.br",
)

HOSTS_HOMOLOG_NOTAS_RI = (
    "testes-api.registrodeimoveis.org.br",
    "pessoas-hml.e-notariado.org.br",
)


def test_proteger_url_recusa_producao_notas_ri(monkeypatch):
    """proteger_url (mesmo gancho de requisitar) recusa os 4 hosts de produção."""
    monkeypatch.setenv(TRAVA.MARCA, "1")
    for host in HOSTS_PROD_NOTAS_RI:
        with pytest.raises(TRAVA.SandboxTravaRecusou) as exc:
            TRAVA.proteger_url(f"https://{host}/v1/x")
        msg = str(exc.value)
        assert "RECUSADA" in msg or "deny-list" in msg or "PRODUCAO" in msg
        assert host in msg or "PRODUCAO" in msg


def test_proteger_url_homolog_onr_ccn_passa_pela_trava(monkeypatch):
    """Homolog explícita NÃO é recusada (sem rede real — só não estoura)."""
    monkeypatch.setenv(TRAVA.MARCA, "1")
    for host in HOSTS_HOMOLOG_NOTAS_RI:
        url = f"https://{host}/v1/ping"
        assert TRAVA.proteger_url(url) == url


def test_centrais_http_recusa_cnib_auth_e_ccn(monkeypatch):
    """requisitar recusa CNIB API, token CNIB e CCN produção."""
    monkeypatch.setenv(TRAVA.MARCA, "1")
    for host in (
        "serventia-api.onr.org.br",
        "auth.id.onr.org.br",
        "pessoas.e-notariado.org.br",
    ):
        with pytest.raises(HTTP.CentralHttpError) as exc:
            HTTP.requisitar("GET", f"https://{host}/x", tentativas=0)
        assert "RECUSADA" in str(exc.value) or "deny" in str(exc.value).lower()


def test_hosts_producao_conhecidos_inclui_notas_ri():
    conhecidos = TRAVA.hosts_producao_conhecidos()
    for host in HOSTS_PROD_NOTAS_RI:
        assert host in conhecidos


def test_registrar_host_producao_api_publica_boot(monkeypatch):
    """API pública: Notas pode registrar host extra em boot sem fork da trava."""
    monkeypatch.setenv(TRAVA.MARCA, "1")
    extra = "upload-prod.exemplo-rfb.local"
    TRAVA.registrar_host_producao(extra)
    try:
        with pytest.raises(TRAVA.SandboxTravaRecusou):
            TRAVA.destino_seguro(extra, 443)
        assert extra in TRAVA.hosts_producao_conhecidos()
    finally:
        with TRAVA._lock:
            TRAVA._HOSTS_PRODUCAO_RECUSAR.discard(extra)
            TRAVA._HOSTS_PARA_SIMULADOR.pop(extra, None)


def test_localhost_e_127_permitidos_no_sandbox(monkeypatch):
    monkeypatch.setenv(TRAVA.MARCA, "1")
    assert TRAVA.destino_seguro("127.0.0.1", 8899) == ("127.0.0.1", 8899)
    assert TRAVA.destino_seguro("localhost", 8899) == ("localhost", 8899)


def test_resumo_cita_deny_quando_armada(monkeypatch):
    monkeypatch.setenv(TRAVA.MARCA, "1")
    txt = TRAVA.resumo()
    assert "ARMADA" in txt
    assert "deny-list" in txt
