# -*- coding: utf-8 -*-
"""Emitir/baixar o JSON CRC/ON-RCPN sem chamar a API.

Opção local enquanto a API CRC não está em uso operacional: o balcão
baixa o mesmo corpo que `montar`/`emitir` montam (`{certidao, registro}`),
conforme `certidao_swagger` / certificate-json.
"""
from __future__ import annotations

import glob
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import onrcpn_certidao_api as API
import rc_pedidos as PED

SENHA = "Senha#12345"
SELO_DO_REGISTRO = "BRCXXX00000037Z7UYDS1EOW8G07"
CNS = "000000"

# Chaves do schema Certidao no swagger (FONTES_EXTERNAS/onrcpn/certidao_swagger.json).
CHAVES_CERTIDAO_SWAGGER = {
    "plataformaId", "tipo_registro", "tipo_certidao", "transcricao",
    "cartorio_cns", "selo", "cod_selo", "modalidade",
    "cota_emolumentos", "cota_emolumentos_isento",
}


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    c = cg_casa["c"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.set_settings({"serventia_cns": CNS})
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _assento(casa) -> int:
    con = _con(casa)
    with con:
        con.execute(
            """INSERT INTO rc_assentos(serie, especie, numero, matricula, nome,
                   data_ato, data_fato, dados_json, situacao, origem, criado_em)
               VALUES ('RC_A','NASCIMENTO',19552,
                       '00000001552026100042166000123445',
                       'MARIA EDUARDA SANTANA',
                       '2026-09-01','2026-08-28','{}','ATIVO','SISTEMA',
                       '2026-09-10T09:00:00')""")
        aid = con.execute("SELECT id FROM rc_assentos").fetchone()["id"]
        con.execute(
            """INSERT INTO rc_atos(assento_id, tipo, folha, numero_ordem,
                   rotulo, data_ato, selo, origem, criado_em)
               VALUES (?,'REGISTRO',166,19552,'166','2026-09-01',?,'SISTEMA',
                       '2026-09-10T09:00:00')""",
            (aid, SELO_DO_REGISTRO))
        for papel, quem, ordem in (("PAI", "MANOEL SANTANA", 1),
                                   ("MAE", "JOSEFA SANTANA", 2)):
            con.execute(
                """INSERT INTO rc_pessoas(assento_id, papel, nome, ordem,
                       origem, criado_em)
                   VALUES (?,?,?,?,'SISTEMA','2026-09-10T09:00:00')""",
                (aid, papel, quem, ordem))
    con.close()
    return aid


# ---------------------------------------------------- o corpo (domínio)


def test_corpo_crc_reusa_montar_e_chaves_do_swagger_certidao(casa):
    """(a) JSON keys match swagger Certidao / house builder — sem esquema
    paralelo."""
    aid = _assento(casa)
    con = _con(casa)
    montado = PED.montar(con, aid, cns=CNS)
    corpo = PED.corpo_crc(con, aid, cns=CNS)
    con.close()

    assert set(corpo.keys()) == {"certidao", "registro"}
    assert corpo["certidao"] == montado["certidao"]
    assert corpo["registro"] == montado["registro"]

    # Toda chave emitida pela casa está no contrato Certidao.
    extras = set(corpo["certidao"]) - CHAVES_CERTIDAO_SWAGGER
    assert not extras, f"chaves fora do swagger Certidao: {extras}"

    # O que a casa sempre manda (mesmo com _sem_vazios) bate com o contrato.
    for chave in ("plataformaId", "tipo_registro", "cartorio_cns",
                  "modalidade", "cota_emolumentos_isento"):
        assert chave in corpo["certidao"], chave
    assert corpo["certidao"]["tipo_registro"] == "nascimento"
    assert "matricula" in corpo["registro"]


def test_corpo_crc_da_eletronica_prefere_corpo_enviado(casa):
    """Se já houve envio, baixa o corpo congelado — não remonta."""
    aid = _assento(casa)
    congelado = {
        "certidao": {"plataformaId": "x", "tipo_registro": "nascimento",
                     "cartorio_cns": CNS, "modalidade": "eletronica",
                     "cota_emolumentos_isento": False},
        "registro": {"nome_completo": "CONGELADO", "matricula": "1" * 32},
    }
    con = _con(casa)
    with con:
        con.execute(
            """INSERT INTO rc_certidoes_eletronicas(
                   assento_id, pedido_id, ambiente, tipo_registro,
                   tipo_certidao, modalidade, certidao_id, corpo_enviado,
                   corpo_hash, situacao, criada_em)
               VALUES (?,NULL,'HOMOLOGACAO','nascimento','','eletronica',
                       'id-central',?,?, 'CRIADA','2026-09-10T10:00:00')""",
            (aid, json.dumps(congelado, ensure_ascii=False), "abc"))
        eid = con.execute(
            "SELECT id FROM rc_certidoes_eletronicas").fetchone()["id"]
    corpo = PED.corpo_crc_da_eletronica(con, eid, cns=CNS)
    con.close()
    assert corpo == congelado
    assert corpo["registro"]["nome_completo"] == "CONGELADO"


# ------------------------------------------- a rota (sem rede)


def test_rota_assento_baixa_json_sem_chamar_a_rede(casa, monkeypatch):
    """(b) application/json attachment; spy da API não é atingido."""
    aid = _assento(casa)
    batidas = {"n": 0}

    def _proibido(*a, **k):
        batidas["n"] += 1
        raise AssertionError("a rota de JSON não pode falar com a Central")

    monkeypatch.setattr(API, "_bater", _proibido)
    monkeypatch.setattr(API, "criar", _proibido)
    monkeypatch.setattr(API, "tem_credencial", lambda **k: False)

    html = casa["c"].get(f"/rcpn/{aid}/certidao-eletronica").get_data(as_text=True)
    assert "Emitir JSON (CRC)" in html
    assert f"/rcpn/{aid}/certidao-eletronica/json" in html

    r = casa["c"].get(f"/rcpn/{aid}/certidao-eletronica/json")
    assert r.status_code == 200, r.status_code
    assert "application/json" in (r.mimetype or r.content_type or "")
    disp = r.headers.get("Content-Disposition", "")
    assert "attachment" in disp
    assert ".json" in disp

    corpo = json.loads(r.get_data(as_text=True))
    assert set(corpo.keys()) == {"certidao", "registro"}
    assert set(corpo["certidao"]) <= CHAVES_CERTIDAO_SWAGGER
    assert batidas["n"] == 0


def test_rota_eletronica_baixa_corpo_enviado_sem_rede(casa, monkeypatch):
    aid = _assento(casa)
    congelado = {
        "certidao": {"plataformaId": "p", "tipo_registro": "nascimento",
                     "cartorio_cns": CNS, "modalidade": "eletronica",
                     "cota_emolumentos_isento": True},
        "registro": {"nome_completo": "JA ENVIADO", "matricula": "2" * 32},
    }
    con = _con(casa)
    with con:
        con.execute(
            """INSERT INTO rc_certidoes_eletronicas(
                   assento_id, pedido_id, ambiente, tipo_registro,
                   tipo_certidao, modalidade, certidao_id, corpo_enviado,
                   corpo_hash, situacao, criada_em)
               VALUES (?,NULL,'HOMOLOGACAO','nascimento','','eletronica',
                       NULL,?, 'h', 'CRIADA','2026-09-10T10:00:00')""",
            (aid, json.dumps(congelado, ensure_ascii=False)))
        eid = con.execute(
            "SELECT id FROM rc_certidoes_eletronicas").fetchone()["id"]
    con.close()

    batidas = {"n": 0}

    def _proibido(*a, **k):
        batidas["n"] += 1
        raise AssertionError("download do corpo_enviado não pode ir à rede")

    monkeypatch.setattr(API, "_bater", _proibido)
    monkeypatch.setattr(API, "criar", _proibido)

    r = casa["c"].get(f"/rcpn/certidao-eletronica/{eid}/json")
    assert r.status_code == 200
    assert "application/json" in (r.mimetype or r.content_type or "")
    assert "attachment" in r.headers.get("Content-Disposition", "")
    assert json.loads(r.get_data(as_text=True)) == congelado
    assert batidas["n"] == 0
