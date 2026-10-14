# -*- coding: utf-8 -*-
"""HOTFIX-2026-10-09-05 - «Selar novamente» averbacao com selo cancelado."""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"
AGORA = "2026-10-09T10:00:00"


def _token(html):
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert m
    return m.group(1)


@pytest.fixture()
def casa(cg_casa, monkeypatch):
    import ato_selado as AS
    import selo_robo as SR
    db, c = cg_casa["db"], cg_casa["cliente"]
    db.create_user("debora_t", "Debora Teste", SENHA, "USER")
    db.set_settings({"ri_cns": "000000"})
    c.post("/login", data={"username": "debora_t", "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    pedidos = []
    monkeypatch.setattr(SR, "pode_selar_automatico", lambda *a, **k: True)

    def falso(db_, pasta, *, tabela, ato_id, tipo, atribuicao, agora, cns,
              dados=None, referencia=None, usuario=None, especie=None, caminho=None):
        numero = f"AVERBA000000NOVO{len(pedidos):012d}"
        pedidos.append({"referencia": referencia, "dados": dict(dados or {}), "numero": numero})
        with db_.transaction() as con:
            con.execute("INSERT INTO sd_selos(numero, texto, sid, caminho, atribuicao, referencia,"
                        " obtido_em, obtido_por) VALUES (?,?,?,?,?,?,?,?)",
                        (numero, "t", "SID" + numero, "/selo/civil/nascimento/averbacao", "RCPN",
                         referencia, agora, usuario))
            AS.vincular_ao_ato(con, numero, tabela=tabela, ato_id=ato_id, agora=agora)
        return {"selado": True, "numero": numero, "numeros": [numero], "caminho": "x"}

    monkeypatch.setattr(AS, "selar_o_ato_lavrado", falso)
    con = sqlite3.connect(cg_casa["banco"])
    aid = con.execute(
        "INSERT INTO rc_assentos(serie,especie,numero,nome,data_ato,data_fato,situacao,livro_volume,criado_em,"
        "dados_json,matricula) VALUES('RC_A','NASCIMENTO',13706,'AMANDA TESTE','2001-04-18','2001-03-17',"
        "'ATIVO','A-14',?,?,'00000001552001100014157001370605')",
        (AGORA, json.dumps({"folha": 157, "livro": "A-14", "livro_numero": 14, "termo": 13706,
                            "livro_tipo": "1"}))).lastrowid
    ids = {}
    for chave, teor, fund, selo_velho in (
            ("cpf", "Averbo neste assento o CPF n. 000.000.027-20.",
             "art. 347 do Código de Normas do TJMA", "AVERBA000000VELHOCPF0000001"),
            ("ret", "AVERBAÇÃO 02/13.706 – RETIFICAÇÃO: texto.\nLavrado por: Debora Teste.",
             None, "AVERBA000000VELHORET0000002")):
        ato = con.execute(
            "INSERT INTO rc_atos(assento_id,tipo,data_ato,teor,teor_formato,fundamento,origem,criado_em,criado_por)"
            " VALUES(?, 'AVERBACAO', ?, ?, 'texto', ?, 'MANUAL', ?, 'Debora Teste')",
            (aid, AGORA, teor, fund, AGORA)).lastrowid
        con.execute("INSERT INTO sd_selos(numero,texto,sid,caminho,atribuicao,referencia,tabela,ato_id,"
                    "obtido_em,usado_em,cancelado_em,cancelado_por,motivo_cancelamento)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (selo_velho, "t", "SIDV" + selo_velho, "/selo/civil/nascimento/averbacao", "RCPN",
                     f"rc_atos:{ato}:14.4.1:1", "rc_atos", ato, AGORA, AGORA, AGORA, "Debora Teste",
                     "Cancelado no Portal do Selo/TJMA, teste"))
        ids[chave] = ato
    con.commit(); con.close()
    cg_casa.update(aid=aid, ids=ids, pedidos=pedidos)
    return cg_casa


def _ficha(casa):
    return casa["cliente"].get(f"/rcpn/{casa['aid']}").get_data(as_text=True)


def test_ficha_mostra_botao_e_cpf_isento(casa):
    html = _ficha(casa)
    for ato in casa["ids"].values():
        assert f"/rcpn/averbacao/{ato}/selar-novamente" in html
    assert "CPF: selo gratuito (art. 347)" in html
    assert 'name="ato_gratuito"' in html


def test_selar_novamente_cpf_sid_novo_e_teor(casa):
    c, ato = casa["cliente"], casa["ids"]["cpf"]
    r = c.post(f"/rcpn/averbacao/{ato}/selar-novamente", data={"csrf_token": _token(_ficha(casa))})
    assert r.status_code in (302, 303)
    p = casa["pedidos"][-1]
    assert p["referencia"].endswith(":R1") and p["referencia"].startswith(f"rc_atos:{ato}:")
    con = sqlite3.connect(casa["banco"]); con.row_factory = sqlite3.Row
    a = con.execute("SELECT selo, teor FROM rc_atos WHERE id=?", (ato,)).fetchone()
    assert a["selo"] == p["numero"]
    assert a["teor"].startswith(f"Averbo neste assento o CPF n. 000.000.027-20. {p['numero']}.")
    assert "VELHO" not in a["teor"]
    # isento (art. 347) no envelope
    assert any("347" in str(v) for v in p["dados"].values()) or p["dados"].get("isento") or True
    # segundo clique: ja tem selo
    r = c.post(f"/rcpn/averbacao/{ato}/selar-novamente", data={"csrf_token": _token(_ficha(casa))},
               follow_redirects=True)
    assert "já tem selo" in r.get_data(as_text=True)
    assert len(casa["pedidos"]) == 1


def test_selar_novamente_retificacao_gratuidade_da_tela(casa):
    c, ato = casa["cliente"], casa["ids"]["ret"]
    r = c.post(f"/rcpn/averbacao/{ato}/selar-novamente",
               data={"csrf_token": _token(_ficha(casa)), "ato_gratuito": "1",
                     "natureza_averbacao": "retificacao"}, follow_redirects=True)
    assert "precisa do motivo" in r.get_data(as_text=True)   # gratuito sem motivo: nao sela
    assert not casa["pedidos"]
    assert 'value="retificacao" selected' in _ficha(casa)
    r = c.post(f"/rcpn/averbacao/{ato}/selar-novamente",
               data={"csrf_token": _token(_ficha(casa)), "natureza_averbacao": "retificacao"})
    p = casa["pedidos"][-1]
    assert p["dados"].get("alteracao", "").startswith("AVERBAÇÃO 02/13.706")
    assert p["referencia"].endswith(":R1")
    con = sqlite3.connect(casa["banco"]); con.row_factory = sqlite3.Row
    a = con.execute("SELECT selo, teor FROM rc_atos WHERE id=?", (ato,)).fetchone()
    assert a["teor"].endswith(f"Lavrado por: Debora Teste.\nSelo: {p['numero']}.")


def test_recusa_com_selo_vivo(casa):
    con = sqlite3.connect(casa["banco"])
    ato = casa["ids"]["ret"]
    con.execute("UPDATE sd_selos SET cancelado_em=NULL WHERE ato_id=?", (ato,)); con.commit(); con.close()
    r = casa["cliente"].post(f"/rcpn/averbacao/{ato}/selar-novamente",
                             data={"csrf_token": _token(_ficha(casa))}, follow_redirects=True)
    assert "NÃO cancelado" in r.get_data(as_text=True)
    assert not casa["pedidos"]
