"""O LOTE DE ASSINATURA PELO WINDOWS — queixa do oficial, 30/10/2026.

    «Mais horrível ainda ter que colocar 20 vezes o PIN do certificado.»

Cada `a3_windows.assinar_pdf` abre um PowerShell novo. `assinar_pdfs` assina N
PDFs num PowerShell só, para o contexto do provedor do token ficar aberto entre
um e outro.

**O POWERSHELL AQUI É SIMULADO**, e nenhum destes testes abre o token. O que eles
não provam é justamente a hipótese: que o driver não peça o PIN de novo. Essa
prova é a primeira assinatura real.

O QUE ESTES TESTES GUARDAM
      - **um único processo para N PDFs**, e os PDFs por arquivo, nunca em argv;
      - o formato de cada assinatura é o de `assinar_pdf`;
      - **para na primeira falha do token**, e o que já saiu volta;
      - o prazo cresce com o lote;
      - o serviço local tem a rota, com as travas de origem de sempre;
      - **o cliente pergunta antes** e reconhece o serviço antigo sem mandar nada.
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import a3_servico_local as SVC  # noqa: E402
import a3_windows as A3W  # noqa: E402
import assinar_com_a3 as A3  # noqa: E402

PDFS = [b"%PDF-1.4 um", b"%PDF-1.4 dois", b"%PDF-1.4 tres"]


class _Feito:
    def __init__(self, codigo=0, saida=""):
        self.returncode = codigo
        self.stdout = saida.encode("utf-8")
        self.stderr = b""


class _PowerShell:
    """O `subprocess.run` simulado: lê a lista, «assina» e anota item a item.

    `falha_em` é a posição em que o token falha; `morre_em`, a posição em que o
    processo estoura o prazo, com os anteriores já anotados.
    """

    def __init__(self, falha_em=None, texto="O PIN errado foi apresentado",
                 morre_em=None):
        self.falha_em, self.texto, self.morre_em = falha_em, texto, morre_em
        self.chamadas = []

    def __call__(self, cmd, **k):
        self.chamadas.append((list(cmd), k))
        lista = Path(cmd[cmd.index("-Lista") + 1])
        resultado = Path(cmd[cmd.index("-Resultado") + 1])
        with open(resultado, "a", encoding="utf-8") as anota:
            for i, linha in enumerate(lista.read_text(encoding="utf-8").splitlines()):
                entrada, saida = linha.split("\t")
                if i == self.morre_em:
                    raise subprocess.TimeoutExpired(cmd, k.get("timeout"))
                if i == self.falha_em:
                    anota.write(f"FALHOU\t{i}\tABCDEF01: {self.texto}\n")
                    return _Feito(4)
                Path(saida).write_bytes(b"P7S:" + Path(entrada).read_bytes())
                anota.write(f"OK\t{i}\tABCDEF0123\n")
                anota.flush()
        return _Feito(0)


def _simular(monkeypatch, **k) -> _PowerShell:
    ps = _PowerShell(**k)
    monkeypatch.setattr(A3W.subprocess, "run", ps)
    return ps


# ---------------------------------------------------------- um processo só


def test_um_unico_processo_para_n_pdfs(monkeypatch):
    ps = _simular(monkeypatch)
    feito = A3W.assinar_pdfs(PDFS)
    assert len(ps.chamadas) == 1
    assert feito["falha"] is None
    assert [x["indice"] for x in feito["assinados"]] == [0, 1, 2]
    assert [x["p7s"] for x in feito["assinados"]] == [b"P7S:" + x for x in PDFS]
    assert {x["thumbprint"] for x in feito["assinados"]} == {"ABCDEF0123"}


def test_a_lista_vai_por_arquivo_e_nada_do_pdf_passa_em_argv(monkeypatch):
    ps = _simular(monkeypatch)
    A3W.assinar_pdfs(PDFS)
    cmd = ps.chamadas[0][0]
    assert not any("%PDF" in str(x) for x in cmd)
    assert "-Lista" in cmd and "-Resultado" in cmd
    assert "-Pdf" not in cmd


def test_o_thumbprint_vai_limpo(monkeypatch):
    ps = _simular(monkeypatch)
    A3W.assinar_pdfs(PDFS[:1], thumbprint="ab:cd 12")
    cmd = ps.chamadas[0][0]
    assert cmd[cmd.index("-Thumb") + 1] == "ABCD12"


def test_lista_vazia_ou_pdf_vazio_recusa_sem_chamar_o_powershell(monkeypatch):
    monkeypatch.setattr(A3W.subprocess, "run",
                        lambda *a, **k: pytest.fail("não devia chamar"))
    with pytest.raises(A3W.A3WindowsError, match="vazio"):
        A3W.assinar_pdfs([])
    with pytest.raises(A3W.A3WindowsError, match="vazio"):
        A3W.assinar_pdfs([PDFS[0], b""])


def test_o_prazo_cresce_com_o_lote(monkeypatch):
    ps = _simular(monkeypatch)
    A3W.assinar_pdfs(PDFS[:1])
    A3W.assinar_pdfs(PDFS)
    um, tres = (k["timeout"] for _, k in ps.chamadas)
    assert um == A3W.prazo_do_lote(1)
    assert tres == A3W.prazo_do_lote(3)
    assert um >= A3W.PRAZO_SEGUNDOS
    assert tres > um


# ---------------------------------------------------------- o formato


def test_o_formato_do_lote_e_o_de_um_so():
    """Mesmo PKCS#7: as linhas que decidem o formato estão nos dois scripts."""
    for trecho in ("O=ICP-Brasil", "HasPrivateKey",
                   "'2.16.840.1.101.3.4.2.1'", "ExcludeRoot",
                   "Pkcs9SigningTime", "SignedCms ($ci, $false)",
                   "ComputeSignature($s, $false)"):
        assert trecho in A3W._SCRIPT, trecho
        assert trecho in A3W._SCRIPT_LOTE, trecho


def test_o_script_reaproveita_o_certificado_e_a_chave():
    s = A3W._SCRIPT_LOTE
    assert s.count("ComputeSignature") == 1          # numa função só
    assert "$usado = $cert" in s
    assert "Assinar-Um $usado" in s
    assert "$chave = Abrir-Chave $cert" in s


def test_o_script_so_tenta_o_certificado_seguinte_se_a_chave_nao_esta_ali():
    """Um parar por engano custa um clique; um seguir por engano custa o token."""
    s = A3W._SCRIPT_LOTE
    assert "if (-not (Chave-Fora-Daqui $t)) { break }" in s
    assert r"\bchaves?\b" in s and "keyset" in s
    assert "cancel" in s and r"\bpin\b" in s


# ---------------------------------------------------------- a parada


def test_a_primeira_falha_do_token_para_e_devolve_o_que_saiu(monkeypatch):
    ps = _simular(monkeypatch, falha_em=1)
    feito = A3W.assinar_pdfs(PDFS)
    assert len(ps.chamadas) == 1
    assert [x["indice"] for x in feito["assinados"]] == [0]
    assert "PIN não foi aceito" in feito["falha"]


def test_janela_cancelada_diz_que_foi_cancelada(monkeypatch):
    _simular(monkeypatch, falha_em=0, texto="A ação foi cancelada pelo usuário")
    feito = A3W.assinar_pdfs(PDFS)
    assert feito["assinados"] == []
    assert "cancelada" in feito["falha"]


def test_o_prazo_vencido_devolve_o_que_ja_estava_assinado(monkeypatch):
    _simular(monkeypatch, morre_em=2)
    feito = A3W.assinar_pdfs(PDFS)
    assert [x["indice"] for x in feito["assinados"]] == [0, 1]
    assert "sem resposta" in feito["falha"]


def test_sem_certificado_a_frase_diz_isso(monkeypatch):
    def run(cmd, **k):
        Path(cmd[cmd.index("-Resultado") + 1]).write_text(
            "SEM_CERTIFICADO\n", encoding="utf-8")
        return _Feito(3)
    monkeypatch.setattr(A3W.subprocess, "run", run)
    feito = A3W.assinar_pdfs(PDFS)
    assert feito["assinados"] == []
    assert "Nenhum certificado" in feito["falha"]


def test_o_script_que_morre_sem_anotar_nada_vira_falha(monkeypatch):
    monkeypatch.setattr(A3W.subprocess, "run",
                        lambda cmd, **k: _Feito(1, "erro do PowerShell"))
    feito = A3W.assinar_pdfs(PDFS)
    assert feito["assinados"] == []
    assert "erro do PowerShell" in feito["falha"]


def test_ok_sem_o_arquivo_nao_conta_como_assinado(monkeypatch):
    def run(cmd, **k):
        Path(cmd[cmd.index("-Resultado") + 1]).write_text(
            "OK\t0\tABCDEF0123\n", encoding="utf-8")
        return _Feito(0)
    monkeypatch.setattr(A3W.subprocess, "run", run)
    feito = A3W.assinar_pdfs(PDFS[:1])
    assert feito["assinados"] == []
    assert feito["falha"]


# ---------------------------------------------------------- o serviço local


@pytest.fixture
def servico():
    srv = SVC.ThreadingHTTPServer(("127.0.0.1", 0), SVC.Manipulador)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()


def _postar(base, corpo, *, cabecalhos=None):
    pedido = urllib.request.Request(
        f"{base}/assinar/pdfs-windows", data=json.dumps(corpo).encode(),
        headers={"Content-Type": "application/json", **(cabecalhos or {})},
        method="POST")
    with urllib.request.urlopen(pedido, timeout=5) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def _em_b64():
    return [base64.b64encode(x).decode("ascii") for x in PDFS]


def test_a_rota_do_lote_responde_item_a_item(monkeypatch, servico):
    vistos = []

    def assinar_pdfs(lista, thumbprint=""):
        vistos.append((lista, thumbprint))
        return {"assinados": [{"indice": i, "p7s": b"P7S:" + x, "thumbprint": "ABC"}
                              for i, x in enumerate(lista)],
                "falha": None}
    monkeypatch.setattr(A3W, "assinar_pdfs", assinar_pdfs)
    status, dados = _postar(servico, {"pdfs_b64": _em_b64(), "thumbprint": "ab"})
    assert status == 200
    assert vistos == [(PDFS, "ab")]
    assert dados["ok"] is True and dados["falha"] is None
    assert dados["mecanismo"] == "windows-cryptoapi"
    assert [base64.b64decode(x["cms_b64"]) for x in dados["itens"]] == [
        b"P7S:" + x for x in PDFS]


def test_a_falha_do_token_volta_com_o_que_ja_foi_assinado(monkeypatch, servico):
    monkeypatch.setattr(A3W, "assinar_pdfs", lambda lista, thumbprint="": {
        "assinados": [{"indice": 0, "p7s": b"P7S", "thumbprint": "ABC"}],
        "falha": "o PIN não foi aceito pelo token."})
    status, dados = _postar(servico, {"pdfs_b64": _em_b64()})
    assert status == 200
    assert [x["indice"] for x in dados["itens"]] == [0]
    assert "PIN não foi aceito" in dados["falha"]


@pytest.mark.parametrize("corpo", [{}, {"pdfs_b64": []}, {"pdfs_b64": "x"}])
def test_a_rota_do_lote_recusa_corpo_sem_lista(monkeypatch, servico, corpo):
    monkeypatch.setattr(A3W, "assinar_pdfs",
                        lambda *a, **k: pytest.fail("não devia assinar"))
    with pytest.raises(urllib.error.HTTPError) as erro:
        _postar(servico, corpo)
    assert erro.value.code == 400


def test_a_rota_do_lote_tem_teto(monkeypatch, servico):
    monkeypatch.setattr(A3W, "assinar_pdfs",
                        lambda *a, **k: pytest.fail("não devia assinar"))
    demais = _em_b64()[:1] * (SVC.LIMITE_DE_PDFS_NO_LOTE + 1)
    with pytest.raises(urllib.error.HTTPError) as erro:
        _postar(servico, {"pdfs_b64": demais})
    assert erro.value.code == 400


def test_a_rota_do_lote_recusa_pagina_da_internet(monkeypatch, servico):
    """PINs errados em sequência BLOQUEIAM o token: a trava de origem vale aqui."""
    monkeypatch.setattr(A3W, "assinar_pdfs",
                        lambda *a, **k: pytest.fail("não devia assinar"))
    with pytest.raises(urllib.error.HTTPError) as erro:
        _postar(servico, {"pdfs_b64": _em_b64()},
                cabecalhos={"Origin": "https://exemplo.invalid"})
    assert erro.value.code == 403


def test_a_rota_do_lote_exige_json(monkeypatch, servico):
    monkeypatch.setattr(A3W, "assinar_pdfs",
                        lambda *a, **k: pytest.fail("não devia assinar"))
    pedido = urllib.request.Request(
        f"{servico}/assinar/pdfs-windows", data=b"pdfs_b64=x",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST")
    with pytest.raises(urllib.error.HTTPError) as erro:
        urllib.request.urlopen(pedido, timeout=5)
    assert erro.value.code == 403


def test_a_saude_anuncia_a_rota_que_o_cliente_procura():
    assert f"POST {A3.ROTA_DO_LOTE}" in SVC.status_payload()["rotas"]


# ---------------------------------------------------------- o cliente


def test_o_cliente_manda_tudo_de_uma_vez_e_com_prazo_de_lote(monkeypatch):
    enviados = []
    monkeypatch.setattr(A3, "_get", lambda caminho, **k: {
        "ok": True, "rotas": [f"POST {A3.ROTA_DO_LOTE}"]})

    def post(caminho, corpo, *, prazo):
        enviados.append((caminho, corpo, prazo))
        return {"ok": True, "itens": [], "falha": None}
    monkeypatch.setattr(A3, "_post_json", post)
    A3.assinar_pdfs_pelo_windows(PDFS)
    assert len(enviados) == 1
    caminho, corpo, prazo = enviados[0]
    assert caminho == A3.ROTA_DO_LOTE
    assert [base64.b64decode(x) for x in corpo["pdfs_b64"]] == PDFS
    # o prazo do cliente não pode vencer antes do prazo do PowerShell
    assert prazo > A3W.prazo_do_lote(len(PDFS))


def test_o_servico_antigo_e_reconhecido_sem_mandar_nada(monkeypatch):
    monkeypatch.setattr(A3, "_get", lambda caminho, **k: {
        "ok": True, "rotas": ["GET /saude", "POST /assinar/pdf-windows"]})
    monkeypatch.setattr(A3, "_post_json",
                        lambda *a, **k: pytest.fail("não devia mandar os PDFs"))
    with pytest.raises(A3.ServicoSemLote, match="versão anterior"):
        A3.assinar_pdfs_pelo_windows(PDFS)


def test_o_servico_fora_do_ar_nao_e_servico_antigo(monkeypatch):
    def fora(caminho, **k):
        raise A3.AssinarComA3Error("o serviço local não está no ar")
    monkeypatch.setattr(A3, "_get", fora)
    with pytest.raises(A3.AssinarComA3Error) as erro:
        A3.assinar_pdfs_pelo_windows(PDFS)
    assert not isinstance(erro.value, A3.ServicoSemLote)


def test_o_cliente_recusa_pdf_vazio_sem_perguntar_ao_servico(monkeypatch):
    monkeypatch.setattr(A3, "_get",
                        lambda *a, **k: pytest.fail("não devia perguntar"))
    with pytest.raises(A3.AssinarComA3Error, match="vazio"):
        A3.assinar_pdfs_pelo_windows([])
