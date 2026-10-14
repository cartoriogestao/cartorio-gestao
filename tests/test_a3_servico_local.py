"""Testes A3-0/A3-1 — mock do serviço/processo filho (sem token real)."""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from unittest import mock

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import a3_servico_local as SVC
import assinar_com_a3 as CLI


PDF_MINIMO = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def test_validar_bind_recusa_tudo_zero():
    with pytest.raises(SystemExit, match="RECUSADO"):
        SVC.validar_bind("0.0.0.0")
    with pytest.raises(SystemExit, match="RECUSADO"):
        SVC.validar_bind("::")
    assert SVC.validar_bind("127.0.0.1") == "127.0.0.1"
    assert SVC.validar_bind("localhost") == "127.0.0.1"


def test_aetpkss1_esta_na_lista_preferida():
    nomes = [n.lower() for n in SVC.DRIVERS_CONHECIDOS]
    assert "aetpkss1.dll" in nomes
    assert nomes.index("aetpkss1.dll") < nomes.index("etpkcs11.dll")


def test_assinar_pdf_pin_vazio_recusa_sem_filho():
    with pytest.raises(SVC.ServicoA3Error, match="PIN"):
        SVC.assinar_pdf(PDF_MINIMO, pin="")


def test_assinar_pdf_nao_pdf_recusa():
    with pytest.raises(SVC.ServicoA3Error, match="PDF"):
        SVC.assinar_pdf(b"nao-e-pdf", pin="1234")


def test_chamar_filho_le_arquivo_de_erro(monkeypatch):
    def fake_run(cmd, capture_output, timeout, check):
        saida = Path(cmd[3])
        erro = Path(str(saida) + ".erro")
        erro.write_text(
            json.dumps({"erro": "nenhum token conectado nesta máquina"}),
            encoding="utf-8")
        return mock.Mock(returncode=1)

    monkeypatch.setattr(SVC.subprocess, "run", fake_run)
    monkeypatch.setattr(SVC, "detectar_driver",
                        lambda: Path("C:/Windows/System32/aetpkss1.dll"))

    with pytest.raises(SVC.ServicoA3Error, match="nenhum token"):
        SVC.assinar_pdf(PDF_MINIMO, pin="0000")


def test_chamar_filho_sucesso_cms(monkeypatch):
    def fake_run(cmd, capture_output, timeout, check):
        saida = Path(cmd[3])
        saida.write_text(json.dumps({
            "formato": "cms_anexado",
            "cms_b64": base64.b64encode(b"CMSFAKE").decode("ascii"),
            "assinatura_b64": base64.b64encode(b"SIG").decode("ascii"),
            "certificado_b64": base64.b64encode(b"CERT").decode("ascii"),
            "mecanismo": "CKM_SHA256_RSA_PKCS",
            "subject": "TESTE:000",
            "thumbprint": "AA" * 20,
        }), encoding="utf-8")
        return mock.Mock(returncode=0)

    monkeypatch.setattr(SVC.subprocess, "run", fake_run)
    monkeypatch.setattr(SVC, "detectar_driver",
                        lambda: Path("C:/Windows/System32/aetpkss1.dll"))

    out = SVC.assinar_pdf(PDF_MINIMO, pin="1234")
    assert out["formato"] == "cms_anexado"
    assert out["subject"] == "TESTE:000"
    assert base64.b64decode(out["cms_b64"]) == b"CMSFAKE"


def test_chamar_filho_sem_saida_e_segfault_simulado(monkeypatch):
    def fake_run(cmd, capture_output, timeout, check):
        return mock.Mock(returncode=139)

    monkeypatch.setattr(SVC.subprocess, "run", fake_run)
    monkeypatch.setattr(SVC, "detectar_driver",
                        lambda: Path("C:/Windows/System32/eTPKCS11.dll"))

    with pytest.raises(SVC.ServicoA3Error, match="não devolveu nada"):
        SVC.listar_certificados()


def test_resolver_driver_override_arg(monkeypatch, tmp_path):
    fake = tmp_path / "aetpkss1.dll"
    fake.write_bytes(b"MZ")
    monkeypatch.setattr(SVC, "_DRIVER_FORCADO", None)
    monkeypatch.delenv(SVC.ENV_DRIVER, raising=False)
    monkeypatch.setattr(SVC, "_ler_config_json", lambda: None)
    # caminho absoluto existe
    achado = SVC.resolver_driver(forcar=str(fake))
    assert achado == fake.resolve()


def test_resolver_driver_env(monkeypatch, tmp_path):
    fake = tmp_path / "eTPKCS11.dll"
    fake.write_bytes(b"MZ")
    monkeypatch.setattr(SVC, "_DRIVER_FORCADO", None)
    monkeypatch.setenv(SVC.ENV_DRIVER, str(fake))
    monkeypatch.setattr(SVC, "_ler_config_json", lambda: None)
    assert SVC.resolver_driver() == fake.resolve()


def test_listar_candidatos_nao_carrega_dll(monkeypatch, tmp_path):
    """Garante que a listagem só olha Path.is_file — sem ctypes/WinDLL."""
    sys32 = tmp_path / "Windows" / "System32"
    sys32.mkdir(parents=True)
    (sys32 / "aetpkss1.dll").write_bytes(b"MZ")
    (sys32 / "eTPKCS11.dll").write_bytes(b"MZ")
    (sys32 / "outra_pkcs_x.dll").write_bytes(b"MZ")

    monkeypatch.setattr(SVC, "_windir", lambda: tmp_path / "Windows")
    monkeypatch.setattr(SVC, "_program_files", lambda: [])

    with mock.patch("ctypes.WinDLL", side_effect=AssertionError("não carregar")):
        with mock.patch("ctypes.CDLL", side_effect=AssertionError("não carregar")):
            lista = SVC.listar_candidatos_no_disco()

    nomes = {i["nome"] for i in lista}
    assert "aetpkss1.dll" in nomes
    assert "eTPKCS11.dll" in nomes
    assert "outra_pkcs_x.dll" in nomes


def test_status_payload_tem_candidatos(monkeypatch):
    monkeypatch.setattr(
        SVC, "listar_candidatos_no_disco",
        lambda: [{"nome": "aetpkss1.dll", "caminho": r"C:\x\aetpkss1.dll",
                  "origem": "System32"}])
    monkeypatch.setattr(
        SVC, "detectar_driver",
        lambda: Path(r"C:\x\aetpkss1.dll"))
    st = SVC.status_payload()
    assert st["ok"] is True
    assert st["candidatos"][0]["nome"] == "aetpkss1.dll"
    assert "aetpkss1.dll" in st["drivers_conhecidos"]
    assert st["ccn"] is False


def test_cliente_status_mock_http(monkeypatch):
    class Resp:
        def read(self):
            return json.dumps({
                "ok": True, "servico": "a3-local",
                "host": "127.0.0.1", "porta": 8766,
                "driver": "aetpkss1.dll", "ccn": False,
                "candidatos": [],
            }).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(CLI.urllib.request, "urlopen", lambda *a, **k: Resp())
    st = CLI.status_do_servico()
    assert st["ok"] is True
    assert st["porta"] == 8766


def test_cliente_pin_vazio():
    with pytest.raises(CLI.AssinarComA3Error, match="PIN"):
        CLI.assinar_pdf(PDF_MINIMO, pin="")


def test_cliente_servico_fora(monkeypatch):
    def boom(*a, **k):
        raise CLI.urllib.error.URLError("recusado")

    monkeypatch.setattr(CLI.urllib.request, "urlopen", boom)
    assert CLI.servico_no_ar() is False
    with pytest.raises(CLI.AssinarComA3Error, match="não está no ar"):
        CLI.status_do_servico()


def test_cliente_assinar_mock(monkeypatch):
    class Resp:
        def read(self):
            return json.dumps({
                "ok": True,
                "formato": "cms_anexado",
                "cms_b64": base64.b64encode(b"X").decode("ascii"),
                "subject": "FULANO",
                "thumbprint": "BB" * 20,
                "mecanismo": "CKM_SHA256_RSA_PKCS",
            }).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(CLI.urllib.request, "urlopen", lambda *a, **k: Resp())
    out = CLI.assinar_pdf(PDF_MINIMO, pin="9999")
    assert out["subject"] == "FULANO"


def test_handler_saude_via_servidor(monkeypatch):
    import threading
    import urllib.request

    monkeypatch.setattr(
        SVC, "listar_candidatos_no_disco",
        lambda: [{"nome": "aetpkss1.dll",
                  "caminho": r"C:\Windows\System32\aetpkss1.dll",
                  "origem": "System32"}])
    monkeypatch.setattr(
        SVC, "detectar_driver",
        lambda: Path(r"C:\Windows\System32\aetpkss1.dll"))

    servidor = SVC.ThreadingHTTPServer(("127.0.0.1", 0), SVC.Manipulador)
    porta = servidor.server_address[1]
    t = threading.Thread(target=servidor.serve_forever, daemon=True)
    t.start()
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{porta}/saude", timeout=3) as r:
            dados = json.loads(r.read().decode("utf-8"))
        assert dados["ok"] is True
        assert dados["servico"] == "a3-local"
        assert dados["ccn"] is False
        assert dados["candidatos"][0]["nome"] == "aetpkss1.dll"
        assert dados["driver"].endswith("aetpkss1.dll")
    finally:
        servidor.shutdown()
        servidor.server_close()


def test_pin_nao_aparece_no_log_message():
    msgs: list[str] = []

    class Fake:
        command = "POST"
        path = "/assinar/pdf?x=1"

        def log_message(self, fmt, *args):
            SVC.Manipulador.log_message(self, fmt, *args)

    with mock.patch.object(
            SVC.log, "info",
            side_effect=lambda m, *a: msgs.append(m % a if a else m)):
        Fake().log_message("%s", "ignored")
    assert msgs
    assert "PIN" not in "".join(msgs).upper()
    assert "/assinar/pdf" in msgs[0]
