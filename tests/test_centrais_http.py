"""O cliente HTTP comum das Centrais — sem internet.

Tudo aqui roda com conexão FALSA (troca de `_abrir_conexao`) ou com um
servidor HTTP de verdade em `127.0.0.1` — nunca com Central nenhuma. Regra 3
do marco (a): nada de envio a Central, e homologação só para consulta.
"""
from __future__ import annotations

import http.server
import json
import re
import ssl
import sys
import threading
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import centrais_http as HTTP  # noqa: E402


class _RespostaFalsa:
    def __init__(self, status=200, corpo=b"", cabecalhos=None):
        self.status = status
        self._corpo = corpo
        self._cab = list((cabecalhos or {"Content-Type": "application/json"}).items())

    def read(self):
        return self._corpo

    def getheaders(self):
        return self._cab


class _ConexaoFalsa:
    """Responde, em ordem, o que estiver no roteiro: exceção ou resposta."""

    def __init__(self, roteiro, pedidos):
        self.roteiro = roteiro
        self.pedidos = pedidos

    def request(self, metodo, caminho, body=None, headers=None):
        self.pedidos.append({"metodo": metodo, "caminho": caminho,
                             "corpo": body, "cabecalhos": dict(headers or {})})
        passo = self.roteiro.pop(0)
        if isinstance(passo, BaseException):
            raise passo
        self._resposta = passo

    def getresponse(self):
        return self._resposta

    def close(self):
        pass


@pytest.fixture()
def rede(monkeypatch):
    """Troca a conexão e o relógio. Devolve (roteiro, pedidos, aberturas)."""
    roteiro, pedidos, aberturas, esperas = [], [], [], []

    def abrir(esquema, host, porta, prazo, contexto):
        aberturas.append((esquema, host, porta, prazo))
        return _ConexaoFalsa(roteiro, pedidos)

    monkeypatch.setattr(HTTP, "_abrir_conexao", abrir)
    monkeypatch.setattr(HTTP, "_dormir", esperas.append)
    return {"roteiro": roteiro, "pedidos": pedidos, "aberturas": aberturas,
            "esperas": esperas}


def test_https_nao_e_opcional():
    with pytest.raises(HTTP.CentralHttpError, match="https"):
        HTTP.requisitar("GET", "http://central.exemplo.invalid/x")


def test_http_local_so_com_permissao_explicita():
    with pytest.raises(HTTP.CentralHttpError):
        HTTP.requisitar("GET", "http://127.0.0.1:9/x")
    with pytest.raises(HTTP.CentralHttpError, match="https"):
        HTTP.requisitar("GET", "http://central.exemplo.invalid/x",
                        permitir_http_local=True)


def test_get_retenta_falha_de_transporte_e_depois_responde(rede):
    rede["roteiro"].extend([ConnectionResetError("caiu"),
                            _RespostaFalsa(200, b'{"ok": true}')])
    r = HTTP.requisitar("GET", "https://central.exemplo.invalid/api/v1?p=1",
                        tentativas=2)
    assert r.ok and r.status == 200 and r.json == {"ok": True}
    assert r.tentativas == 2
    assert rede["pedidos"][0]["caminho"] == "/api/v1?p=1"
    assert rede["esperas"] == [HTTP.ESPERA_BASE]
    assert rede["aberturas"][0][:3] == ("https", "central.exemplo.invalid", 443)


def test_get_desiste_depois_das_tentativas_com_frase_de_balcao(rede):
    rede["roteiro"].extend([TimeoutError("t1"), TimeoutError("t2"),
                            TimeoutError("t3")])
    with pytest.raises(HTTP.CentralHttpError) as erro:
        HTTP.requisitar("GET", "https://central.exemplo.invalid/", tentativas=2)
    assert erro.value.tentativas == 3
    assert "nada foi enviado" in str(erro.value)


def test_post_nao_se_repete_sozinho(rede):
    """Aprovar a mesma anuência duas vezes é um ato a mais na Central."""
    rede["roteiro"].extend([ConnectionResetError("caiu"),
                            _RespostaFalsa(200, b"{}")])
    with pytest.raises(HTTP.CentralHttpError) as erro:
        HTTP.requisitar("POST", "https://central.exemplo.invalid/processar",
                        json_corpo={"a": 1}, tentativas=3)
    assert erro.value.tentativas == 1
    assert len(rede["pedidos"]) == 1
    assert "confira na Central" in str(erro.value)


def test_post_idempotente_declarado_pode_retentar(rede):
    rede["roteiro"].extend([ConnectionResetError("caiu"),
                            _RespostaFalsa(201, b"")])
    r = HTTP.requisitar("PUT", "https://central.exemplo.invalid/x",
                        corpo="abc", retentar_escrita=True)
    assert r.status == 201 and r.json is None and r.tentativas == 2
    assert rede["pedidos"][1]["corpo"] == b"abc"


def test_status_transitorio_se_retenta_no_get(rede):
    rede["roteiro"].extend([_RespostaFalsa(503, b"ocupado"),
                            _RespostaFalsa(200, b"[1,2]")])
    r = HTTP.requisitar("GET", "https://central.exemplo.invalid/")
    assert r.status == 200 and r.json == [1, 2] and r.tentativas == 2


def test_4xx_e_5xx_voltam_como_resposta_e_nao_estouram(rede):
    rede["roteiro"].append(_RespostaFalsa(404, b'{"message": "sumiu"}'))
    r = HTTP.requisitar("GET", "https://central.exemplo.invalid/", tentativas=0)
    assert not r.ok
    assert r.como_dict() == {"status": 404, "json": {"message": "sumiu"},
                             "texto": '{"message": "sumiu"}'}
    rede["roteiro"].append(_RespostaFalsa(503, b"x"))
    assert HTTP.requisitar("GET", "https://central.exemplo.invalid/",
                           tentativas=0).status == 503


def test_json_corpo_vai_em_utf8_com_tipo(rede):
    rede["roteiro"].append(_RespostaFalsa(200, b"{}"))
    HTTP.requisitar("POST", "https://central.exemplo.invalid/x",
                    json_corpo={"nome": "Conceição"},
                    cabecalhos={"Authorization": "Bearer abc"})
    p = rede["pedidos"][0]
    assert json.loads(p["corpo"].decode("utf-8")) == {"nome": "Conceição"}
    assert p["cabecalhos"]["Content-Type"].startswith("application/json")
    assert p["cabecalhos"]["Authorization"] == "Bearer abc"


def test_user_agent_nao_carrega_dado_da_serventia(rede):
    """Nada de CNS/CNPJ escrito no código — quem quiser, passa da configuração."""
    rede["roteiro"].extend([_RespostaFalsa(200, b""), _RespostaFalsa(200, b"")])
    HTTP.requisitar("GET", "https://central.exemplo.invalid/")
    assert not re.search(r"\d", rede["pedidos"][0]["cabecalhos"]["User-Agent"])
    HTTP.requisitar("GET", "https://central.exemplo.invalid/",
                    user_agent="CartorioGestao/LIDO-DA-CONFIG")
    assert rede["pedidos"][1]["cabecalhos"]["User-Agent"].endswith("LIDO-DA-CONFIG")


def test_contexto_tls_valida_a_cadeia_e_exige_tls12():
    ctx = HTTP.contexto_tls()
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
    assert ctx.minimum_version >= ssl.TLSVersion.TLSv1_2


def test_certificado_cliente_inexistente_vira_frase(tmp_path):
    falta = HTTP.CertificadoCliente(str(tmp_path / "nao_existe.pem"))
    with pytest.raises(HTTP.CentralHttpError, match="certificado cliente"):
        HTTP.contexto_tls(falta)
    # A senha do PEM não aparece no `repr` (log, traceback).
    assert "s3gr3d0" not in repr(HTTP.CertificadoCliente("a.pem", "b.pem", "s3gr3d0"))


def test_configuracao_para_o_painel_nao_tem_segredo():
    c = HTTP.configuracao()
    assert c["tls_minimo"] == "TLS 1.2" and "GET" in c["retenta_sozinho"]


def test_smoke_servidor_local_de_verdade():
    """O caminho inteiro do `http.client`, contra 127.0.0.1 — sem internet."""
    class Manipulador(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            corpo = json.dumps({"caminho": self.path,
                                "ua": self.headers.get("User-Agent")}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *a):
            pass

    servidor = http.server.HTTPServer(("127.0.0.1", 0), Manipulador)
    t = threading.Thread(target=servidor.serve_forever, daemon=True)
    t.start()
    try:
        porta = servidor.server_address[1]
        r = HTTP.requisitar("GET", f"http://127.0.0.1:{porta}/status?x=1",
                            permitir_http_local=True, prazo=5)
        assert r.status == 200
        assert r.json == {"caminho": "/status?x=1", "ua": "CartorioGestao"}
        assert r.cabecalhos["content-type"] == "application/json"
        assert r.duracao_ms >= 0
    finally:
        servidor.shutdown()
        servidor.server_close()


def test_codigo_novo_nao_traz_dado_da_serventia_escrito():
    """Atualização do teste cart (05/10/2026): CNS, CNPJ, IP — da configuração."""
    proibidos = [re.compile(r"000000"),
                 re.compile(r"(?<![\d.])(?!127\.0\.0\.1)\d{1,3}(?:\.\d{1,3}){3}(?![\d.])"),
                 re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")]
    for nome in ("centrais_http.py", "centrais_fila.py", "centrais_log.py",
                 "centrais_schema.py", "centrais_web.py"):
        texto = (RAIZ / nome).read_text(encoding="utf-8")
        for p in proibidos:
            assert not p.search(texto), f"{nome}: {p.pattern} encontrado"
