"""Encerrar a ficha por AV já lavrada e selada — 18/11/2026.

    Pedido do oficial: «vamos encerrar a matrícula 2874 (já tem averbação)».
    A AV de encerramento já estava no livro e selada, mas lavrada sem a marca
    «Este ato encerra a matrícula». O caminho «Encerrar esta matrícula»
    lavraria outra averbação — o que não pode.

O QUE ESTES TESTES PROTEGEM
    1. A ação marca a ficha encerrada sem lavrar ato, sem selo e sem cobrança.
    2. A data do encerramento é a do ato de referência.
    3. Motivo curto, AV sem selo, ato de outra ficha e ficha já encerrada
       são recusados.
    4. Só ADMIN/MANAGER; robô (eh_robo) não entra.
    5. O «Reabrir» que já existe continua sendo o caminho de volta.
    6. A tela avisa para usar esta opção em vez de lavrar outra AV.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"

TEOR_ENCERRA = ("AV-07/2.874 - ENCERRAMENTO DA ESCRITURACAO NO LIVRO E "
                "TRANSPORTE PARA FICHA. O imovel passa a constar da 4.031.")


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


def _entrar(app, usuario: str):
    c = app.test_client()
    c.post("/login",
           data={"username": usuario, "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("balcao", "QUEM ATENDE", SENHA, "USER")
    db.create_user("robo_ri", "Robo de Exemplo RI", SENHA, "USER", eh_robo=1)
    return {**cg_casa, "cliente": _entrar(cg_casa["app"], "mario")}


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _matricula(con, numero="2874"):
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
               tipo_ficha, criado_em)
           VALUES (?, '2-P', '2-P', 'ATIVA', 'ACERVO', '2026-11-17T10:00')""",
        (numero,))
    return int(cur.lastrowid)


def _ato(con, matricula_id, *, numero=7, teor=TEOR_ENCERRA,
         data_ato="2026-11-17", selo="AVESVD0000000000000000000001"):
    from ri_schema import hash_ato
    h = hash_ato(str(matricula_id), "AV", numero, data_ato, teor, None)
    cur = con.execute(
        """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, teor,
               teor_formato, cancelado, acervo, origem, hash_ato, lavrado_em,
               selo_texto)
           VALUES (?, 'AV', ?, ?, ?, 'texto', 0, 0, 'MANUAL', ?,
                   '2026-11-17T13:36', ?)""",
        (matricula_id, numero, data_ato, teor, h, selo))
    return int(cur.lastrowid)


def _ficha_com_av(casa, *, selo="AVESVD0000000000000000000001"):
    con = _con(casa)
    with con:
        mid = _matricula(con)
        ato_id = _ato(con, mid, selo=selo)
        con.execute(
            """INSERT INTO ri_partes (matricula_id, nome, papel, proprietario,
                   proprietario_ativo, origem)
               VALUES (?, 'JOSE DA SILVA', 'proprietario', 1, 1, 'MANUAL')""",
            (mid,))
    con.close()
    return mid, ato_id


def _encerrar(casa, mid, ato_id, *, motivo="transporte para a matricula 4031",
              destino="4031", cliente=None):
    c = cliente or casa["cliente"]
    html = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    return c.post(f"/registro-imoveis/{mid}/encerrar-por-ato",
                  data={"csrf_token": _token(html), "ato_id": ato_id,
                        "motivo": motivo, "destino": destino},
                  follow_redirects=True)


def test_a_tela_oferece_encerrar_pela_av_ja_lavrada(casa):
    mid, _ato_id = _ficha_com_av(casa)
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Já existe AV de encerramento?" in html
    assert "Use esta opção em vez de lavrar outra" in html
    assert 'action="/registro-imoveis/%s/encerrar-por-ato"' % mid in html
    assert "Continuar sem encerrar a ficha?" in html


def test_encerra_pela_av_sem_lavrar_ato_nem_pedir_selo(casa):
    mid, ato_id = _ficha_com_av(casa)
    html = _encerrar(casa, mid, ato_id).get_data(as_text=True)

    con = _con(casa)
    m = con.execute("SELECT * FROM ri_matriculas WHERE id=?", (mid,)).fetchone()
    atos = [dict(r) for r in con.execute(
        "SELECT id, numero, selo_texto FROM ri_atos WHERE matricula_id=?",
        (mid,))]
    ativos = con.execute(
        """SELECT COUNT(*) FROM ri_partes
            WHERE matricula_id=? AND proprietario_ativo=1""", (mid,)).fetchone()[0]
    log = con.execute(
        """SELECT action, details FROM audit_logs
            WHERE action='RI_MATRICULA_ENCERRADA_POR_ATO'
            ORDER BY id DESC LIMIT 1""").fetchone()
    con.close()

    assert m["encerrada"] == 1
    assert m["situacao"] == "ENCERRADA"
    assert m["data_encerramento"] == "2026-11-17"
    assert "Destino: 4031." in (m["motivo_encerramento"] or "")
    assert "AV-07" in (m["motivo_encerramento"] or "")
    assert [a["id"] for a in atos] == [ato_id], (
        f"nao pode lavrar ato novo: {atos}")
    assert atos[0]["selo_texto"] == "AVESVD0000000000000000000001"
    assert ativos == 0
    assert "Nenhum ato novo foi lavrado" in html
    assert log is not None
    assert "AV-07" in (log["details"] or "")


def test_motivo_curto_nao_encerra(casa):
    mid, ato_id = _ficha_com_av(casa)
    _encerrar(casa, mid, ato_id, motivo="curto")
    con = _con(casa)
    m = con.execute("SELECT encerrada FROM ri_matriculas WHERE id=?",
                    (mid,)).fetchone()
    con.close()
    assert not m["encerrada"]


def test_sem_destino_nao_encerra(casa):
    mid, ato_id = _ficha_com_av(casa)
    _encerrar(casa, mid, ato_id, destino="")
    con = _con(casa)
    m = con.execute("SELECT encerrada FROM ri_matriculas WHERE id=?",
                    (mid,)).fetchone()
    con.close()
    assert not m["encerrada"]


def test_av_sem_selo_nao_encerra(casa):
    mid, ato_id = _ficha_com_av(casa, selo=None)
    html = _encerrar(casa, mid, ato_id).get_data(as_text=True)
    assert "precisa estar selada" in html.lower()
    con = _con(casa)
    m = con.execute("SELECT encerrada FROM ri_matriculas WHERE id=?",
                    (mid,)).fetchone()
    con.close()
    assert not m["encerrada"]


def test_ato_de_outra_ficha_nao_encerra(casa):
    mid, _ = _ficha_com_av(casa)
    con = _con(casa)
    with con:
        outra = _matricula(con, numero="4031")
        ato_alheio = _ato(con, outra, numero=1, teor="AV-01/4.031 — outro.")
    con.close()
    html = _encerrar(casa, mid, ato_alheio).get_data(as_text=True)
    assert "não é desta matrícula" in html
    con = _con(casa)
    m = con.execute("SELECT encerrada FROM ri_matriculas WHERE id=?",
                    (mid,)).fetchone()
    con.close()
    assert not m["encerrada"]


def test_quem_atende_nao_ve_nem_encerra(casa):
    mid, ato_id = _ficha_com_av(casa)
    balcao = _entrar(casa["app"], "balcao")
    ficha = balcao.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Já existe AV de encerramento?" not in ficha
    assert "encerrar-por-ato" not in ficha
    resp = balcao.post(
        f"/registro-imoveis/{mid}/encerrar-por-ato",
        data={"csrf_token": _token(ficha), "ato_id": ato_id,
              "motivo": "quero encerrar esta ficha aqui", "destino": "4031"},
        follow_redirects=False)
    assert resp.status_code in (302, 403)
    con = _con(casa)
    encerrada = con.execute("SELECT encerrada FROM ri_matriculas WHERE id=?",
                            (mid,)).fetchone()["encerrada"]
    con.close()
    assert not encerrada


def test_robo_nao_encerra(casa):
    mid, ato_id = _ficha_com_av(casa)
    robo = _entrar(casa["app"], "robo_ri")
    ficha = robo.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    # A ficha do RI pode estar fora da lista do robô; o POST da ação nova
    # precisa cair em 403 de qualquer forma.
    token = _token(ficha) if 'csrf_token' in ficha else _token(
        casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True))
    resp = robo.post(
        f"/registro-imoveis/{mid}/encerrar-por-ato",
        data={"csrf_token": token, "ato_id": ato_id,
              "motivo": "transporte para a matricula 4031", "destino": "4031"},
        follow_redirects=False)
    assert resp.status_code == 403
    con = _con(casa)
    encerrada = con.execute("SELECT encerrada FROM ri_matriculas WHERE id=?",
                            (mid,)).fetchone()["encerrada"]
    con.close()
    assert not encerrada


def test_reabrir_depois_do_encerrar_por_ato(casa):
    mid, ato_id = _ficha_com_av(casa)
    _encerrar(casa, mid, ato_id)
    c = casa["cliente"]
    html = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Reabrir esta matrícula" in html
    depois = c.post(f"/registro-imoveis/{mid}/reabrir",
                    data={"csrf_token": _token(html),
                          "motivo": "corrigir destino digitado errado"},
                    follow_redirects=True).get_data(as_text=True)
    con = _con(casa)
    m = con.execute("SELECT * FROM ri_matriculas WHERE id=?", (mid,)).fetchone()
    numeros = [r["numero"] for r in con.execute(
        "SELECT numero FROM ri_atos WHERE matricula_id=?", (mid,))]
    con.close()
    assert not m["encerrada"]
    assert m["reaberta_em"]
    assert numeros == [7], "reabrir nao mexe no ato de referencia"
    assert "Ficha reaberta" in depois
