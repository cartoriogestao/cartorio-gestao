"""A parte da pesquisa de satisfação que mora na VPS (`vps/pesquisa/pesquisa_vps.py`)
— 26/10/2026.

Sem banco da casa e sem rede de fora: o programa sobe em 127.0.0.1, numa
porta qualquer, com um SQLite temporário, e é exercitado pelo HTTP como o
Apache o exercitaria. O que se guarda aqui:
  - a API recusa sem o token, e recusa o lote inteiro se vier campo a mais
    (nome, e-mail, protocolo — a lista é fechada);
  - o banco da VPS não guarda o código, só o hash;
  - o convite responde UMA vez; «não existe» e «vencido» dão a mesma resposta;
  - a resposta sai da VPS quando o servidor confirma; o convite continua
    dizendo «já respondido»;
  - sem HTTPS (o cabeçalho do Apache), nada se atende.

Testes escritos para a máquina do merge (26/10/2026: nada de pytest nesta
máquina, por ordem do oficial).
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sqlite3
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

TOKEN = "p" * 48
CODIGO = base64.b32encode(b"\x01" * 20).decode("ascii")       # 32 caracteres A-Z2-7
OUTRO = base64.b32encode(b"\x02" * 20).decode("ascii")


def _modulo():
    espec = importlib.util.spec_from_file_location(
        "pesquisa_vps", RAIZ / "vps" / "pesquisa" / "pesquisa_vps.py")
    m = importlib.util.module_from_spec(espec)
    espec.loader.exec_module(m)
    return m


@pytest.fixture()
def vps(tmp_path):
    m = _modulo()
    pesquisa = m.Pesquisa(str(tmp_path / "pesquisa.sqlite3"), TOKEN, prefixo="/pesquisa",
                          serventia="Serventia de Exemplo")
    servidor = m.servir(pesquisa, "127.0.0.1", 0)
    fio = threading.Thread(target=servidor.serve_forever, daemon=True)
    fio.start()
    base = f"http://127.0.0.1:{servidor.server_address[1]}/pesquisa"
    yield {"m": m, "pesquisa": pesquisa, "base": base, "banco": tmp_path / "pesquisa.sqlite3"}
    servidor.shutdown()
    servidor.server_close()


def _pedir(url, *, dados=None, json_=None, token=None, https=True, metodo=None):
    corpo = None
    cab = {}
    if json_ is not None:
        corpo = json.dumps(json_).encode("utf-8")
        cab["Content-Type"] = "application/json"
    elif dados is not None:
        corpo = urllib.parse.urlencode(dados).encode("utf-8")
        cab["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        cab["Authorization"] = f"Bearer {token}"
    if https:
        cab["X-Forwarded-Proto"] = "https"
    req = urllib.request.Request(url, data=corpo, headers=cab, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def _chave(m, codigo=CODIGO):
    return m.chave_do_codigo(codigo)


def _convite(m, codigo=CODIGO, **extra):
    vence = (date.today() + timedelta(days=30)).isoformat()
    return {"chave": _chave(m, codigo), "atribuicao": "RI",
            "dia": date.today().isoformat(), "expira_em": vence, **extra}


def _empurrar(vps, *convites, token=TOKEN):
    return _pedir(vps["base"] + "/api/convites", json_={"convites": list(convites)},
                  token=token)


def test_a_chave_e_o_mesmo_calculo_do_servidor(vps):
    """A VPS e o servidor (`satisfacao_envio.chave_na_vps`) calculam igual."""
    import satisfacao_envio as ENVIO
    assert vps["m"].chave_do_codigo(CODIGO) == ENVIO.chave_na_vps(CODIGO)
    assert vps["m"].chave_do_codigo(CODIGO) == hashlib.sha256(CODIGO.encode()).hexdigest()


def test_api_recusa_sem_token(vps):
    status, _ = _empurrar(vps, _convite(vps["m"]), token="errado" * 8)
    assert status == 401
    status, _ = _pedir(vps["base"] + "/api/respostas")
    assert status == 401


def test_sem_https_nada_se_atende(vps):
    status, _ = _pedir(vps["base"] + f"/r/{CODIGO}", https=False)
    assert status == 403


def test_lote_com_campo_a_mais_e_recusado_inteiro(vps):
    m = vps["m"]
    status, corpo = _empurrar(vps, _convite(m, OUTRO),
                              _convite(m, email="cliente@exemplo.invalid"))
    assert status == 400 and "não guarda" in json.loads(corpo)["motivo"]
    assert vps["pesquisa"].contar()["convites"] == 0
    status, _ = _empurrar(vps, _convite(m, protocolo="2026.10.1"))
    assert status == 400


def test_o_banco_da_vps_nao_guarda_o_codigo(vps):
    assert _empurrar(vps, _convite(vps["m"]))[0] == 200
    _pedir(vps["base"] + f"/r/{CODIGO}", dados={"nota": "5", "comentario": "Bom"})
    bruto = Path(vps["banco"]).read_bytes()
    assert CODIGO.encode() not in bruto
    with sqlite3.connect(vps["banco"]) as con:
        colunas = {r[1] for r in con.execute("PRAGMA table_info(convites)")}
    assert colunas == {"chave", "atribuicao", "dia", "expira_em", "recebido_em",
                       "respondido_em"}


def test_formulario_responde_uma_vez(vps):
    assert _empurrar(vps, _convite(vps["m"]))[0] == 200
    status, html = _pedir(vps["base"] + f"/r/{CODIGO}")
    assert status == 200 and 'name="nota"' in html and "Registro de Imóveis" in html
    status, html = _pedir(vps["base"] + f"/r/{CODIGO}",
                          dados={"nota": "4", "comentario": "<b>atendimento</b> rápido"})
    assert status == 200 and "Obrigado" in html
    status, html = _pedir(vps["base"] + f"/r/{CODIGO}",
                          dados={"nota": "1", "comentario": "de novo"})
    assert "já foi respondido" in html
    status, html = _pedir(vps["base"] + f"/r/{CODIGO}")
    assert "já foi respondido" in html
    respostas = vps["pesquisa"].respostas()
    assert len(respostas) == 1 and respostas[0]["nota"] == 4
    # Sem a hora: só o dia.
    assert respostas[0]["dia"] == date.today().isoformat()


def test_nota_fora_de_1_a_5_nao_grava(vps):
    assert _empurrar(vps, _convite(vps["m"]))[0] == 200
    status, html = _pedir(vps["base"] + f"/r/{CODIGO}", dados={"nota": "9"})
    assert status == 400 and "nota de 1 a 5" in html
    assert vps["pesquisa"].respostas() == []


def test_inexistente_e_vencido_dao_a_mesma_resposta(vps):
    m = vps["m"]
    ontem = (date.today() - timedelta(days=1)).isoformat()
    assert _empurrar(vps, _convite(m, OUTRO, expira_em=ontem))[0] == 200
    s1, h1 = _pedir(vps["base"] + f"/r/{CODIGO}")
    s2, h2 = _pedir(vps["base"] + f"/r/{OUTRO}")
    assert s1 == s2 == 404 and h1 == h2


def test_o_servidor_puxa_e_confirma(vps):
    m = vps["m"]
    assert _empurrar(vps, _convite(m))[0] == 200
    _pedir(vps["base"] + f"/r/{CODIGO}", dados={"nota": "5", "comentario": ""})
    status, corpo = _pedir(vps["base"] + "/api/respostas", token=TOKEN)
    respostas = json.loads(corpo)["respostas"]
    assert status == 200 and [r["chave"] for r in respostas] == [_chave(m)]
    assert set(respostas[0]) == {"chave", "nota", "comentario", "dia"}
    status, corpo = _pedir(vps["base"] + "/api/respostas/confirmar",
                           json_={"chaves": [_chave(m)]}, token=TOKEN)
    assert status == 200 and json.loads(corpo)["apagadas"] == 1
    assert vps["pesquisa"].respostas() == []
    # O convite continua: o link diz «já respondido», e reenviar não reabre.
    assert _empurrar(vps, _convite(m))[0] == 200
    assert "já foi respondido" in _pedir(vps["base"] + f"/r/{CODIGO}")[1]


def test_vencido_sai_com_a_resposta_na_limpeza(vps):
    m = vps["m"]
    assert _empurrar(vps, _convite(m))[0] == 200
    vps["pesquisa"].responder(CODIGO, 3, "", "10.0.0.1")
    vps["pesquisa"].limpar(hoje=date.today() + timedelta(days=31))
    assert vps["pesquisa"].contar() == {"convites": 0, "respostas": 0}


def test_ordem_de_remover_leva_so_a_chave(vps):
    m = vps["m"]
    assert _empurrar(vps, _convite(m))[0] == 200
    assert _empurrar(vps, {"chave": _chave(m), "remover": True, "nome": "x"})[0] == 400
    assert _empurrar(vps, {"chave": _chave(m), "remover": True})[0] == 200
    assert vps["pesquisa"].contar()["convites"] == 0
