"""A ASSINATURA DO INSTRUMENTO DE PROTESTO — 15/10/2026.

O botão «Assinar com o A3» da tela dos instrumentos: o papel da impressão vira
PDF, o serviço local assina PELO REPOSITÓRIO DO WINDOWS (o caminho dos sites;
o PKCS#11 do SafeSign falha nesta casa) e devolve o PKCS#7 com o PDF dentro —
o formato dos instrumentos que a casa mandou à CENPROT.

Sem token: uma chave RSA de ensaio faz o papel do A3, pela peça que a casa já
tem (`cades.assinar`), e o pacote sai no mesmo formato.

O QUE ESTES TESTES GUARDAM
      - **o assinado se guarda** (o PDF e o `.p7s` na pasta da casa) e a fila
        de assinatura passa a dizer quem assinou e quando;
      - **assinatura que embrulha outro papel não entra**, e nada se grava;
      - a rota liga os fios: o PDF da impressão vai ao serviço, e a recusa
        do serviço volta como frase, e não como HTTP 500;
      - **o PIN não passa pelo sistema**: a tela não tem campo de PIN;
      - o serviço local responde na rota nova, e só com certificado
        ICP-Brasil (o filtro mora no PowerShell — o teste confere que ele
        está lá).
"""
from __future__ import annotations

import base64
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from prova_de_intimacao import juntar_prova  # noqa: E402

import a3_windows as A3W  # noqa: E402
import cades  # noqa: E402
import protesto as PT  # noqa: E402
import protesto_instrumento as PI  # noqa: E402

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding, rsa  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

from test_protesto_aviso_web import _con, _token, s, titulo_apontado  # noqa: E402,F401

SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
PDF = b"%PDF-1.4\n% instrumento de ensaio\n1 0 obj<<>>endobj\n%%EOF\n"


@pytest.fixture(scope="module")
def chave_e_cert():
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,
                                         "MARIO EXEMPLO:00000000191")])
    agora = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome)
            .public_key(chave.public_key()).serial_number(515151)
            .not_valid_before(agora - timedelta(days=1))
            .not_valid_after(agora + timedelta(days=30))
            .sign(chave, hashes.SHA256()))
    return chave, cert.public_bytes(serialization.Encoding.DER)


def _assinar(chave_e_cert, conteudo: bytes) -> bytes:
    chave, cert = chave_e_cert
    return cades.assinar(
        conteudo, cert,
        lambda dados: chave.sign(dados, padding.PKCS1v15(), hashes.SHA256()))


def _instrumento(s) -> int:
    tid = titulo_apontado(s)
    con = _con(s)
    with con:
        PT.lancar_intimacao(con, tid, modo="PESSOAL",
                            agora="2026-10-10T10:00:00")
        con.execute("UPDATE pt_titulos SET motivo_protesto='1' WHERE id=?",
                    (tid,))
        juntar_prova(con, tid)   # a prova da intimação (29/10/2026)
        PT.lancar_protesto(con, tid, sv=SV, agora="2026-10-14T10:00:00",
                           data_extenso="x")
        r = PI.emitir(con, tid, serventia=SV["unit_name"],
                      agora="2026-10-14T11:00:00")
    con.close()
    return r["id"]


# ------------------------------------------------------- guardar (domínio)


def test_o_assinado_se_guarda_e_a_fila_diz_quem_assinou(s, chave_e_cert,
                                                        tmp_path):
    iid = _instrumento(s)
    con = _con(s)
    with con:
        r = PI.guardar_assinatura(
            con, iid, pdf=PDF, p7s=_assinar(chave_e_cert, PDF),
            pasta_de_arquivos=tmp_path, agora="2026-10-15T12:00:00",
            usuario="MARIO EXEMPLO DOS SANTOS")
    assert r["instrumento_id"] == iid
    assert "MARIO EXEMPLO" in (r["assinado_por"] or "")
    pasta = tmp_path / "Protesto" / "Instrumentos"
    assert (pasta / f"instrumento-{r['numero']}-{r['ano']}.pdf").read_bytes() == PDF
    p7s = (pasta / f"instrumento-{r['numero']}-{r['ano']}.p7s").read_bytes()
    linha = con.execute("SELECT * FROM as_documentos WHERE entidade=? "
                        "AND entidade_id=?",
                        (PI.ENTIDADE_DA_ASSINATURA, iid)).fetchone()
    assert linha["assinado_em"] == "2026-10-15T12:00:00"
    assert linha["caminho_assinado"].endswith(".p7s")
    tid = con.execute("SELECT titulo_id FROM pt_instrumentos WHERE id=?",
                      (iid,)).fetchone()[0]
    # É este .p7s que vai para dentro do XML da CENPROT.
    assert PI.assinado_do_titulo(con, tid) == p7s


def test_assinatura_de_outro_papel_nao_entra_e_nada_se_grava(s, chave_e_cert,
                                                             tmp_path):
    iid = _instrumento(s)
    outro = PDF.replace(b"ensaio", b"OUTRO ")
    con = _con(s)
    with pytest.raises(PI.InstrumentoError, match="não confere"):
        PI.guardar_assinatura(
            con, iid, pdf=PDF, p7s=_assinar(chave_e_cert, outro),
            pasta_de_arquivos=tmp_path, agora="2026-10-15T12:00:00")
    assert not (tmp_path / "Protesto").exists()
    linha = con.execute("SELECT assinado_em FROM as_documentos WHERE "
                        "entidade=? AND entidade_id=?",
                        (PI.ENTIDADE_DA_ASSINATURA, iid)).fetchone()
    assert linha["assinado_em"] is None


def test_sem_assinatura_guardada_o_titulo_nao_tem_instrumento_assinado(s):
    iid = _instrumento(s)
    con = _con(s)
    tid = con.execute("SELECT titulo_id FROM pt_instrumentos WHERE id=?",
                      (iid,)).fetchone()[0]
    assert PI.assinado_do_titulo(con, tid) is None


# ------------------------------------------------------------- a rota


def _postar(s, iid):
    tela = s["c"].get("/protesto/instrumentos").get_data(as_text=True)
    return s["c"].post(f"/protesto/instrumentos/{iid}/assinar",
                       data={"csrf_token": _token(tela)},
                       follow_redirects=True)


def test_a_rota_assina_o_pdf_da_impressao(s, chave_e_cert, monkeypatch):
    import assinar_com_a3 as A3
    import impressao_pdf as IMPPDF
    monkeypatch.setattr(IMPPDF, "pdf_de_odt", lambda odt, **k: PDF)
    vistos = []

    def servico(pdf, *, thumbprint=None):
        vistos.append(pdf)
        return {"ok": True, "cms_b64": base64.b64encode(
            _assinar(chave_e_cert, pdf)).decode("ascii")}

    monkeypatch.setattr(A3, "assinar_pdf_pelo_windows", servico)
    iid = _instrumento(s)
    r = _postar(s, iid)
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert vistos == [PDF]
    assert "assinado por" in html
    con = _con(s)
    assert con.execute("SELECT assinado_em FROM as_documentos WHERE "
                       "entidade=? AND entidade_id=?",
                       (PI.ENTIDADE_DA_ASSINATURA, iid)).fetchone()[0]


def test_a_recusa_do_servico_volta_como_frase(s, monkeypatch):
    import assinar_com_a3 as A3
    import impressao_pdf as IMPPDF
    monkeypatch.setattr(IMPPDF, "pdf_de_odt", lambda odt, **k: PDF)

    def recusa(pdf, *, thumbprint=None):
        raise A3.AssinarComA3Error("a assinatura foi cancelada na janela do token.")

    monkeypatch.setattr(A3, "assinar_pdf_pelo_windows", recusa)
    iid = _instrumento(s)
    r = _postar(s, iid)
    assert r.status_code == 200
    assert "cancelada na janela do token" in r.get_data(as_text=True)


def test_servico_fora_do_ar_diz_onde_abrir(s, monkeypatch):
    import assinar_com_a3 as A3
    import impressao_pdf as IMPPDF
    monkeypatch.setattr(IMPPDF, "pdf_de_odt", lambda odt, **k: PDF)

    def fora(pdf, *, thumbprint=None):
        raise ConnectionRefusedError()

    monkeypatch.setattr(A3, "assinar_pdf_pelo_windows", fora)
    iid = _instrumento(s)
    html = _postar(s, iid).get_data(as_text=True)
    assert "não respondeu" in html


def test_a_tela_nao_pede_pin(s):
    _instrumento(s)
    html = s["c"].get("/protesto/instrumentos").get_data(as_text=True)
    assert "Assinar com o A3" in html
    assert 'name="pin"' not in html


# ------------------------------------------- o assinador pelo Windows


class _Feito:
    def __init__(self, codigo, saida):
        self.returncode = codigo
        self.stdout = saida.encode("utf-8")
        self.stderr = b""


def test_o_script_so_aceita_certificado_icp_brasil():
    assert "O=ICP-Brasil" in A3W._SCRIPT
    assert "HasPrivateKey" in A3W._SCRIPT


def test_assinar_pdf_le_o_arquivo_que_o_powershell_grava(monkeypatch):
    def run(cmd, **k):
        saida = Path(cmd[cmd.index("-Saida") + 1])
        saida.write_bytes(b"0\x82PKCS7")
        return _Feito(0, "OK|ABCDEF0123\r\n")

    monkeypatch.setattr(A3W.subprocess, "run", run)
    feito = A3W.assinar_pdf(PDF, thumbprint="ab:cd")
    assert feito == {"p7s": b"0\x82PKCS7", "thumbprint": "ABCDEF0123"}


def test_sem_certificado_a_frase_diz_isso(monkeypatch):
    monkeypatch.setattr(A3W.subprocess, "run",
                        lambda cmd, **k: _Feito(3, "SEM_CERTIFICADO"))
    with pytest.raises(A3W.A3WindowsError, match="Nenhum certificado"):
        A3W.assinar_pdf(PDF)


def test_chave_fora_do_token_manda_conferir_a_sessao_remota(monkeypatch):
    monkeypatch.setattr(
        A3W.subprocess, "run",
        lambda cmd, **k: _Feito(4, "FALHOU|0962D8C6: O conjunto de chaves "
                                   "não está definido."))
    with pytest.raises(A3W.A3WindowsError, match="Cartões inteligentes"):
        A3W.assinar_pdf(PDF)


def test_pdf_vazio_recusa_sem_chamar_o_powershell(monkeypatch):
    monkeypatch.setattr(A3W.subprocess, "run",
                        lambda *a, **k: pytest.fail("não devia chamar"))
    with pytest.raises(A3W.A3WindowsError, match="vazio"):
        A3W.assinar_pdf(b"")


def test_o_servico_local_responde_na_rota_do_windows(monkeypatch):
    import threading
    import urllib.request

    import a3_servico_local as SVC
    monkeypatch.setattr(A3W, "assinar_pdf",
                        lambda pdf, thumbprint="": {"p7s": b"P7S:" + pdf,
                                                    "thumbprint": "ABC"})
    servidor = SVC.ThreadingHTTPServer(("127.0.0.1", 0), SVC.Manipulador)
    porta = servidor.server_address[1]
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        corpo = json.dumps({"pdf_b64": base64.b64encode(PDF).decode()}).encode()
        pedido = urllib.request.Request(
            f"http://127.0.0.1:{porta}/assinar/pdf-windows", data=corpo,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(pedido, timeout=5) as r:
            dados = json.loads(r.read().decode("utf-8"))
    finally:
        servidor.shutdown()
        servidor.server_close()
    assert dados["ok"] is True
    assert dados["mecanismo"] == "windows-cryptoapi"
    assert base64.b64decode(dados["cms_b64"]) == b"P7S:" + PDF
