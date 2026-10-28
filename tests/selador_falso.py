"""
Um selador de mentira, com TLS de verdade.

POR QUE UM SERVIDOR E NAO UM `mock`
    O que este cliente tem de dificil nao e montar JSON — e o transporte:
    aperto de mao TLS, conferencia de impressao digital do certificado, token
    que vence, 401 no meio, prazo esgotado, conexao recusada. `mock` nao
    exercita nada disso; um servidor de verdade, com certificado proprio numa
    porta local, exercita tudo.

    O certificado de teste e auto-assinado, gerado na hora (tmp) e existe SO
    para o teste (B1: a chave privada nao fica mais no repositorio).
    Ele imita o caso real: o selador desta serventia e uma maquina da rede
    local, e maquina de rede local tem certificado proprio.
"""
from __future__ import annotations

import json
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# B1 (sanitização, 05/10/2026): a chave de teste NÃO vai para o git.
# `tests/selador_teste.pem` contém PRIVATE KEY e está no .gitignore (`*.pem`).
# Por isso o certificado é GERADO NA HORA, autoassinado, numa pasta temporária
# do processo (`cryptography`, a mesma dependência que o TLS já exigia).
# Só se `cryptography` faltar é que se cai no par antigo do disco, se existir.
_PEM_DO_DISCO = Path(__file__).parent / "selador_teste.pem"
_CRT_DO_DISCO = Path(__file__).parent / "selador_teste.crt"


def _gerar_par_de_teste() -> tuple[Path, Path]:
    import atexit
    import datetime as _dt
    import ipaddress
    import shutil as _sh
    import tempfile

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Cartorio Gestao - APENAS TESTE"),
        x509.NameAttribute(NameOID.COMMON_NAME, "selador-de-teste"),
    ])
    agora = _dt.datetime.now(_dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(nome).issuer_name(nome)
        .public_key(chave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - _dt.timedelta(minutes=5))
        .not_valid_after(agora + _dt.timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        .sign(chave, hashes.SHA256())
    )
    pasta = Path(tempfile.mkdtemp(prefix="selador_teste_"))
    atexit.register(_sh.rmtree, pasta, True)
    crt_pem = cert.public_bytes(serialization.Encoding.PEM)
    chave_pem = chave.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption())
    pem, crt = pasta / "selador_teste.pem", pasta / "selador_teste.crt"
    pem.write_bytes(chave_pem + crt_pem)
    crt.write_bytes(crt_pem)
    return pem, crt


try:
    PEM, CRT = _gerar_par_de_teste()
except ImportError:                       # sem cryptography: par antigo, se houver
    PEM, CRT = _PEM_DO_DISCO, _CRT_DO_DISCO

TOKEN = "token-de-teste-123"


def impressao_digital() -> str:
    import hashlib
    return hashlib.sha256(
        ssl.PEM_cert_to_DER_cert(CRT.read_text(encoding="utf-8"))).hexdigest()


class SeladorFalso:
    """Sobe numa porta livre e conta o que recebeu."""

    def __init__(self, *, token_valido: str = TOKEN, expires_in: int = 300):
        self.pedidos: list[dict] = []
        self.token_valido = token_valido
        self.expires_in = expires_in
        self.selos_por_sid: dict[str, str] = {}
        self.recusar_com: tuple[int, dict] | None = None
        # O que o aparelho de verdade devolve além do contrato de 2017 (o
        # código de validação, 23/10/2026): vai junto no resumo, como veio.
        self.campos_a_mais: dict = {}
        self.primeira_chamada_401 = False
        self._ja_deu_401 = False
        self._contador = 0

        servidor = self

        class Mao(BaseHTTPRequestHandler):
            def log_message(self, *a):        # silencio no teste
                pass

            def _responder(self, status, corpo):
                bruto = json.dumps(corpo).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(bruto)))
                self.end_headers()
                self.wfile.write(bruto)

            def do_POST(self):                # noqa: N802
                tamanho = int(self.headers.get("Content-Length") or 0)
                corpo = self.rfile.read(tamanho) if tamanho else b""
                caminho, _, consulta = self.path.partition("?")
                servidor.pedidos.append({
                    "caminho": caminho, "consulta": consulta,
                    "cabecalhos": dict(self.headers),
                    "corpo": corpo.decode("utf-8", errors="replace")})

                if caminho.endswith("/auth") or "token" in caminho:
                    self._responder(200, {"access_token": servidor.token_valido,
                                          "expires_in": servidor.expires_in})
                    return
                if servidor.recusar_com:
                    status, corpo_erro = servidor.recusar_com
                    self._responder(status, corpo_erro)
                    return
                dado = self.headers.get("Authorization") or ""
                if (servidor.primeira_chamada_401 and not servidor._ja_deu_401):
                    servidor._ja_deu_401 = True
                    self._responder(401, {"status": 401, "error": "Unauthorized",
                                          "message": "token vencido"})
                    return
                if dado != f"Bearer {servidor.token_valido}":
                    self._responder(401, {"status": 401, "error": "Unauthorized",
                                          "message": "sem token"})
                    return
                sid = ""
                for parte in consulta.split("&"):
                    if parte.startswith("sid="):
                        sid = parte[4:]
                # O selador de verdade devolve o MESMO selo para o mesmo SID.
                if sid in servidor.selos_por_sid:
                    numero = servidor.selos_por_sid[sid]
                else:
                    servidor._contador += 1
                    numero = f"AUTENT000000TESTE{servidor._contador:010d}"[:28]
                    servidor.selos_por_sid[sid] = numero
                self._responder(200, {"resumos": [{
                    "numeroSelo": numero,
                    "textoSelo": f"Poder Judiciário – TJMA. Selo: {numero}",
                    "dataGeracao": "2026-08-24T12:00:00",
                    "saldoRemanescente": 1234.0,
                    **servidor.campos_a_mais}]})

        contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        contexto.minimum_version = ssl.TLSVersion.TLSv1_2
        contexto.load_cert_chain(PEM)
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Mao)
        self.http.daemon_threads = True
        self.http.socket = contexto.wrap_socket(self.http.socket, server_side=True)
        self.porta = self.http.server_address[1]
        self.base = f"https://127.0.0.1:{self.porta}"
        self._t = threading.Thread(target=self.http.serve_forever, daemon=True)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *a):
        self.http.shutdown()
        self.http.server_close()
        self._t.join(timeout=5)
