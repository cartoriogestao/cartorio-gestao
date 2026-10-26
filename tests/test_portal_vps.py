"""A parte do portal que mora na VPS (`vps/portal/portal_vps.py`) — 26/10/2026.

Sem banco da casa e sem rede de fora: o programa sobe em 127.0.0.1, numa
porta qualquer, com um SQLite temporário, e é exercitado pelo HTTP como o
Apache o exercitaria. O que se guarda aqui:
  - a página pública dá a MESMA resposta para «não existe» e «código errado»;
  - o limite de erros por IP e por número trava até o código certo;
  - número e código só viajam no corpo (POST), nunca na URL;
  - a API recusa sem o token, e recusa o lote inteiro se vier campo a mais;
  - sem HTTPS (o cabeçalho do Apache), nada se atende.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import acompanhamento_cliente as ACOMP  # noqa: E402

TOKEN = "v" * 48
NUMERO = "2026.10.123"


def _modulo():
    espec = importlib.util.spec_from_file_location(
        "portal_vps", RAIZ / "vps" / "portal" / "portal_vps.py")
    m = importlib.util.module_from_spec(espec)
    espec.loader.exec_module(m)
    return m


@pytest.fixture()
def vps(tmp_path):
    m = _modulo()
    portal = m.Portal(str(tmp_path / "portal.sqlite3"), TOKEN, prefixo="/portal",
                      serventia="Serventia de Exemplo", contato="Fale conosco")
    servidor = m.servir(portal, "127.0.0.1", 0)
    fio = threading.Thread(target=servidor.serve_forever, daemon=True)
    fio.start()
    base = f"http://127.0.0.1:{servidor.server_address[1]}/portal"
    yield {"m": m, "portal": portal, "base": base}
    servidor.shutdown()
    servidor.server_close()


def _pedir(url, *, dados=None, json_=None, token=None, https=True, metodo=None):
    corpo = None
    cab = {}
    if dados is not None:
        corpo = urllib.parse.urlencode(dados).encode()
        cab["Content-Type"] = "application/x-www-form-urlencoded"
    if json_ is not None:
        corpo = json.dumps(json_).encode()
        cab["Content-Type"] = "application/json"
    if token:
        cab["Authorization"] = f"Bearer {token}"
    if https:
        cab["X-Forwarded-Proto"] = "https"
    req = urllib.request.Request(url, data=corpo, headers=cab, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def _retrato(codigo="ABCDEFGH", **extra):
    pdf = b"%PDF-1.4 recibo de teste"
    return {"numero": NUMERO, "codigo_hash": ACOMP.hash_do_codigo(codigo),
            "situacao_publica": "aguardando documento/exigência",
            "previsao": "2026-11-05", "atualizado_em": "2026-10-25T14:30",
            "atribuicao": "Registro de Imóveis", "expira_em": "2027-10-20",
            "recibos": [{"nome": "recibo-12-2026.pdf",
                         "sha256": hashlib.sha256(pdf).hexdigest(),
                         "pdf": base64.b64encode(pdf).decode()}], **extra}


def _subir(vps, *retratos):
    return _pedir(vps["base"] + "/api/retratos", json_={"retratos": list(retratos)},
                  token=TOKEN)


def test_a_api_recusa_sem_o_token(vps):
    status, _, _ = _pedir(vps["base"] + "/api/retratos", json_={"retratos": []},
                          token="errado" * 8)
    assert status == 401
    assert _pedir(vps["base"] + "/api/saude")[0] == 401
    assert _pedir(vps["base"] + "/api/saude", token=TOKEN)[0] == 200


def test_sem_https_nada_se_atende(vps):
    assert _pedir(vps["base"] + "/", https=False)[0] == 403


def test_campo_a_mais_recusa_o_lote_inteiro(vps):
    status, _, corpo = _subir(vps, _retrato(interessado="FULANO"))
    assert status == 400 and b"interessado" in corpo
    assert vps["portal"].contar() == 0


def test_pdf_que_chegou_diferente_e_recusado(vps):
    r = _retrato()
    r["recibos"][0]["sha256"] = "0" * 64
    assert _subir(vps, r)[0] == 400


def test_consulta_certa_mostra_a_situacao_e_o_recibo(vps):
    assert _subir(vps, _retrato())[0] == 200
    status, cab, corpo = _pedir(vps["base"] + "/consultar",
                                dados={"numero": NUMERO, "codigo": "abcd-efgh"})
    texto = corpo.decode()
    assert status == 200 and "aguardando documento/exigência" in texto
    assert "05/11/2026" in texto and "recibo-12-2026.pdf" in texto
    assert cab["Cache-Control"] == "no-store"
    assert "default-src 'none'" in cab["Content-Security-Policy"]
    status, cab, pdf = _pedir(vps["base"] + "/recibo", dados={
        "numero": NUMERO, "codigo": "ABCDEFGH", "nome": "recibo-12-2026.pdf"})
    assert status == 200 and pdf.startswith(b"%PDF-")
    assert cab["Content-Type"] == "application/pdf"


def test_nao_existe_e_codigo_errado_dao_a_mesma_pagina(vps):
    _subir(vps, _retrato())
    _, _, errado = _pedir(vps["base"] + "/consultar",
                          dados={"numero": NUMERO, "codigo": "ZZZZZZZZ"})
    _, _, inexistente = _pedir(vps["base"] + "/consultar",
                               dados={"numero": "2026.10.58", "codigo": "ZZZZZZZZ"})
    # o número volta preenchido no campo, e é a única diferença
    assert errado.replace(NUMERO.encode(), b"#") == \
        inexistente.replace(b"2026.10.58", b"#")
    assert "não conferem".encode() in errado


def test_o_recibo_nao_sai_sem_o_codigo_certo(vps):
    _subir(vps, _retrato())
    status, cab, corpo = _pedir(vps["base"] + "/recibo", dados={
        "numero": NUMERO, "codigo": "ZZZZZZZZ", "nome": "recibo-12-2026.pdf"})
    assert not corpo.startswith(b"%PDF")


def test_erro_demais_trava_o_numero_ate_com_o_codigo_certo(vps):
    m, portal = vps["m"], vps["portal"]
    _subir(vps, _retrato())
    for i in range(m.ERROS_POR_NUMERO):
        # IPs diferentes: a trava do NÚMERO pega quem distribui as tentativas
        assert portal.consultar(NUMERO, "ZZZZZZZZ", f"198.51.100.{i}")[0] == "nao_confere"
    assert portal.consultar(NUMERO, "ABCDEFGH", "198.51.100.200")[0] == "muitas"


def test_erro_demais_trava_o_ip(vps):
    m, portal = vps["m"], vps["portal"]
    _subir(vps, _retrato())
    for i in range(m.ERROS_POR_IP):
        portal.consultar(f"2026.10.{900 + i}", "ZZZZZZZZ", "198.51.100.7")
    assert portal.consultar(NUMERO, "ABCDEFGH", "198.51.100.7")[0] == "muitas"
    assert portal.consultar(NUMERO, "ABCDEFGH", "198.51.100.8")[0] == "ok"


def test_o_ip_vem_do_apache_e_nao_do_comeco_da_lista(vps):
    """O Apache acrescenta o IP real no FIM do X-Forwarded-For."""
    m = vps["m"]
    for i in range(m.ERROS_POR_IP):
        req = urllib.request.Request(
            vps["base"] + "/consultar", method="POST",
            data=urllib.parse.urlencode({"numero": "2026.10.1", "codigo": "Z"}).encode(),
            headers={"X-Forwarded-Proto": "https",
                     "X-Forwarded-For": f"10.0.0.{i}, 198.51.100.50"})
        urllib.request.urlopen(req, timeout=20).read()
    assert vps["portal"]._travado("ip:198.51.100.50", m.ERROS_POR_IP, m.JANELA_IP)


def test_a_ordem_de_remover_apaga_o_retrato_e_o_recibo(vps):
    _subir(vps, _retrato())
    assert _subir(vps, {"numero": NUMERO, "remover": True})[0] == 200
    assert vps["portal"].contar() == 0
    assert vps["portal"].recibo(NUMERO, "recibo-12-2026.pdf") is None


def test_o_vencido_sai_sozinho(vps):
    _subir(vps, _retrato(expira_em="2020-01-01"))
    vps["portal"].limpar()
    assert vps["portal"].contar() == 0


def test_o_formulario_manda_por_post_e_nao_na_url(vps):
    _, _, corpo = _pedir(vps["base"] + "/")
    texto = corpo.decode()
    assert 'method="post"' in texto and 'action="/portal/consultar"' in texto
    # GET com o código na URL não consulta nada
    status, _, _ = _pedir(vps["base"] + f"/consultar?numero={NUMERO}&codigo=ABCDEFGH")
    assert status == 404


# ------------------------------------------------- o comprovante (26/10/2026)

def texto_do_pdf(pdf: bytes) -> str:
    """O texto que o PDF desenha (as strings dos `Tj`), na ordem. O comprovante
    sai sem compressão de propósito: é o que deixa o teste ler o que ele leva."""
    import re
    pedacos = []
    for m in re.finditer(rb"\(((?:\\.|[^\\)])*)\) Tj", pdf):
        bruto = re.sub(rb"\\(.)", rb"\1", m.group(1))
        pedacos.append(bruto.decode("cp1252"))
    return "\n".join(pedacos)


def _com_comprovante(**extra):
    base = {"entrada": "2026-10-20", "servico": "Registro do título: compra e venda",
            "exigencias": ["Apresentar a certidão de casamento atualizada.",
                           "Recolher o ITBI."],
            "pronto": False}
    base.update(extra)
    return _retrato(**base)


def test_o_comprovante_sai_em_pdf_com_o_essencial_e_o_codigo_mascarado(vps):
    """Decisão do oficial em 26/10/2026: o PDF que o cliente baixa é um
    comprovante com as informações essenciais — e o código vai mascarado."""
    assert _subir(vps, _com_comprovante())[0] == 200
    status, cab, pagina = _pedir(vps["base"] + "/consultar",
                                 dados={"numero": NUMERO, "codigo": "ABCDEFGH"})
    assert status == 200 and "comprovante de acompanhamento" in pagina.decode()
    assert "Recolher o ITBI." in pagina.decode()
    status, cab, pdf = _pedir(vps["base"] + "/comprovante",
                              dados={"numero": NUMERO, "codigo": "abcd-efgh"})
    assert status == 200 and pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    assert cab["Content-Type"] == "application/pdf"
    assert "comprovante-2026-10-123.pdf" in cab["Content-Disposition"]
    texto = texto_do_pdf(pdf)
    for esperado in ("COMPROVANTE DE ACOMPANHAMENTO", "Serventia de Exemplo",
                     f"Protocolo: {NUMERO}", "••••-••GH", "Data de entrada: 20/10/2026",
                     "Atribuição: Registro de Imóveis",
                     "Serviço pedido: Registro do título: compra e venda",
                     "Situação atual: aguardando documento/exigência",
                     "25/10/2026 14:30", "Prazo previsto: 05/11/2026",
                     "Pronto para retirar: Ainda não",
                     "1. Apresentar a certidão de casamento atualizada.",
                     "2. Recolher o ITBI.", "Contato da serventia: Fale conosco"):
        assert esperado in texto, esperado
    # o código inteiro é a senha da consulta: não vai no PDF, em forma nenhuma
    for codigo in ("ABCDEFGH", "ABCD-EFGH", "abcdefgh", "ABCD"):
        assert codigo not in texto


def test_o_comprovante_nao_sai_sem_o_codigo_certo(vps):
    _subir(vps, _com_comprovante())
    _, _, corpo = _pedir(vps["base"] + "/comprovante",
                         dados={"numero": NUMERO, "codigo": "ZZZZZZZZ"})
    assert not corpo.startswith(b"%PDF")


def test_o_retrato_antigo_sem_os_campos_do_comprovante_ainda_entra(vps):
    """O servidor de antes não manda os campos novos: o portal aceita, e o
    comprovante diz o que não sabe em vez de inventar."""
    assert _subir(vps, _retrato(situacao_publica="pronto para retirar"))[0] == 200
    _, _, pdf = _pedir(vps["base"] + "/comprovante",
                       dados={"numero": NUMERO, "codigo": "ABCDEFGH"})
    texto = texto_do_pdf(pdf)
    assert "Data de entrada: não informada" in texto
    assert "Pronto para retirar: Sim" in texto and "Nenhuma." in texto


@pytest.mark.parametrize("campo, valor", [
    ("servico", "Escritura de BEATRIZ, CPF 000.000.001-91"),
    ("servico", "Registro com valor de R$ 120.000,00"),
    ("exigencias", ["Pagar a diferença de 57,30 no balcão."]),
    ("exigencias", ["Trazer o contrato social do CNPJ 00.000.000/0001-00."]),
    ("exigencias", ["x" * 401]),
    ("exigencias", ["uma"] * 11),
    ("pronto", "sim"),
    ("entrada", "20/10/2026"),
])
def test_texto_do_comprovante_com_cara_de_documento_ou_valor_recusa_o_lote(vps, campo, valor):
    status, _, corpo = _subir(vps, _com_comprovante(**{campo: valor}))
    assert status == 400, corpo
    assert vps["portal"].contar() == 0


def test_o_banco_que_ja_existia_ganha_as_colunas_do_comprovante(tmp_path):
    import sqlite3
    m = _modulo()
    caminho = tmp_path / "antigo.sqlite3"
    con = sqlite3.connect(caminho)
    con.executescript("""CREATE TABLE retratos (numero TEXT PRIMARY KEY,
        codigo_hash TEXT NOT NULL, situacao TEXT NOT NULL, previsao TEXT,
        atualizado_em TEXT, atribuicao TEXT, expira_em TEXT NOT NULL,
        recebido_em TEXT NOT NULL);""")
    con.close()
    portal = m.Portal(str(caminho), TOKEN, exigir_https=False)
    portal.receber(json.dumps({"retratos": [_com_comprovante()]}).encode())
    estado, r = portal.consultar(NUMERO, "ABCDEFGH", "198.51.100.1")
    assert estado == "ok" and r["entrada"] == "2026-10-20"
    assert r["exigencias"] == ["Apresentar a certidão de casamento atualizada.",
                               "Recolher o ITBI."]


def test_o_formato_do_hash_e_o_mesmo_nas_duas_pontas():
    m = _modulo()
    for _ in range(3):
        c = ACOMP.gerar_codigo()
        h = ACOMP.hash_do_codigo(c)
        assert m.RE_HASH.match(h)
        assert m.confere(c, h) and m.confere(ACOMP.formatar_codigo(c).lower(), h)
        assert not m.confere("ZZZZZZZZ", h)
    assert m.ALFABETO == ACOMP.ALFABETO
