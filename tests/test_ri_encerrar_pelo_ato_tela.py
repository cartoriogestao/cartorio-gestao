"""Marcar ato lavrado como encerramento — tela nova (18/11/2026).

O BURACO
    A AV de encerramento já está no livro, lavrada (e muitas vezes selada),
    mas sem a marca «Este ato encerra a matrícula». A ficha segue ATIVA. O
    botão «Encerrar esta matrícula» lavraria outra AV e pediria outro selo.

O QUE ESTES TESTES PROTEGEM
    - a ficha muda de estado sem criar ato, sem mexer em teor/hash e sem
      chamar o selador;
    - só ADMIN/MANAGER; USER leva 403;
    - motivo ≥ 10; recusas (já encerrada, outro imóvel, cancelado, tipo R,
      inexistente) não gravam e não auditam sucesso;
    - auditoria `RI_MATRICULA_ENCERRADA_PELO_ATO` com os campos pedidos;
    - Reabrir desfaz e a ficha mostra «Voltar a encerrar»;
    - o quadro na ficha aparece só no caso certo.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from ri_schema import hash_ato  # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-11-18T12:00:00"
MOTIVO = "Averbação de encerramento já lavrada sem a marca na ficha"
SELO_CURTO = "AVTESTE0000000000000000000001"
TEOR_AV = "AV-02/9.900 - ENCERRAMENTO DA MATRICULA E TRANSPORTE PARA OUTRA FICHA."


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
def casa(cg_casa, monkeypatch):
    """Sem selador: qualquer chamada a `selar` falha o teste."""
    import selador_cliente as CL

    def _nao_chame(*a, **k):
        raise AssertionError("encerrar-pelo-ato nao pode chamar o selador")

    monkeypatch.setattr(CL, "selar", _nao_chame)
    db = cg_casa["db"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("gestora", "GESTORA EXEMPLO", SENHA, "MANAGER")
    db.create_user("balcao", "QUEM ATENDE", SENHA, "USER")
    return {**cg_casa,
            "admin": _entrar(cg_casa["app"], "mario"),
            "manager": _entrar(cg_casa["app"], "gestora"),
            "balcao": _entrar(cg_casa["app"], "balcao")}


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _ficha(con, numero="9900", *, encerrada=0, situacao="ATIVO",
           reaberta_em=None, data_encerramento=None):
    cur = con.execute(
        """INSERT INTO ri_matriculas
           (numero, livro, livro_norm, situacao, tipo_ficha, encerrada,
            reaberta_em, data_encerramento, criado_em)
           VALUES (?, '2', '2', ?, 'ESTRUTURADA', ?, ?, ?, ?)""",
        (numero, situacao, encerrada, reaberta_em, data_encerramento, AGORA))
    return int(cur.lastrowid)


def _ato(con, mid, *, tipo="AV", numero=1, data_ato="2026-11-10",
         teor=None, selo=SELO_CURTO, cancelado=0, lavrado_em=AGORA,
         matricula_numero="9900"):
    teor = teor or f"{tipo}-{numero:02d}/{matricula_numero} TEOR DE TESTE."
    anterior = con.execute(
        """SELECT hash_ato FROM ri_atos WHERE matricula_id=?
           ORDER BY id DESC LIMIT 1""", (mid,)).fetchone()
    ha = anterior["hash_ato"] if anterior else None
    h = hash_ato(matricula_numero, tipo, numero, data_ato, teor, ha)
    cur = con.execute(
        """INSERT INTO ri_atos
           (matricula_id, tipo, numero, data_ato, teor, teor_formato, cancelado,
            acervo, origem, selo_texto, hash_ato, hash_anterior, lavrado_em)
           VALUES (?,?,?,?,?,'texto',?,0,'MANUAL',?,?,?,?)""",
        (mid, tipo, numero, data_ato, teor, cancelado, selo, h, ha, lavrado_em))
    return int(cur.lastrowid)


def _parte(con, mid, nome="PARTE EXEMPLO DA FICHA"):
    con.execute(
        """INSERT INTO ri_partes
           (matricula_id, nome, papel, proprietario, proprietario_ativo, origem)
           VALUES (?,?,'proprietario',1,1,'MANUAL')""",
        (mid, nome))


def _caso_ativo(casa, *, com_r=False, dois_av=False):
    con = _con(casa)
    with con:
        mid = _ficha(con)
        _parte(con, mid)
        a_r = _ato(con, mid, tipo="R", numero=1, teor="R-01/9.900 COMPRA.") if com_r else None
        a1 = _ato(con, mid, tipo="AV", numero=2, teor=TEOR_AV, data_ato="2026-11-10")
        a2 = None
        if dois_av:
            a2 = _ato(con, mid, tipo="AV", numero=3,
                      teor="AV-03/9.900 OUTRO ATO POSTERIOR.",
                      data_ato="2026-11-12", selo="AVTESTE0000000000000000000002")
    con.close()
    return mid, {"r": a_r, "av": a1, "av2": a2}


def _post(cliente, mid, dados):
    html = cliente.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    corpo = dict(dados)
    corpo["csrf_token"] = _token(html)
    return cliente.post(f"/registro-imoveis/{mid}/encerrar-pelo-ato",
                        data=corpo, follow_redirects=True)


def _hashes(con, mid):
    return [dict(r) for r in con.execute(
        """SELECT id, teor, hash_ato, hash_anterior FROM ri_atos
           WHERE matricula_id=? ORDER BY id""", (mid,)).fetchall()]


def _audit_ok(con):
    return con.execute(
        """SELECT details FROM audit_logs
           WHERE action='RI_MATRICULA_ENCERRADA_PELO_ATO'""").fetchall()


# ------------------------------------------------------------------ estado


def test_marca_encerrada_com_data_do_ato_e_destino(casa):
    mid, ids = _caso_ativo(casa)
    r = _post(casa["admin"], mid,
              {"ato_id": str(ids["av"]), "motivo": MOTIVO, "destino": "9901"})
    html = r.get_data(as_text=True)
    assert "nenhum ato novo foi lavrado" in html.lower() or "Nenhum ato novo" in html
    assert "nenhum selo" in html.lower()

    con = _con(casa)
    m = con.execute("SELECT * FROM ri_matriculas WHERE id=?", (mid,)).fetchone()
    partes = con.execute(
        "SELECT proprietario_ativo FROM ri_partes WHERE matricula_id=?",
        (mid,)).fetchall()
    n_atos = con.execute(
        "SELECT COUNT(*) n FROM ri_atos WHERE matricula_id=?", (mid,)).fetchone()["n"]
    audits = _audit_ok(con)
    con.close()

    assert m["encerrada"] == 1
    assert m["situacao"] == "ENCERRADA"
    assert m["data_encerramento"] == "2026-11-10"
    assert MOTIVO in (m["motivo_encerramento"] or "")
    assert "Destino: 9901" in (m["motivo_encerramento"] or "")
    assert all(int(p["proprietario_ativo"] or 0) == 0 for p in partes)
    assert n_atos == 1
    assert len(audits) == 1


def test_manager_tambem_marca(casa):
    mid, ids = _caso_ativo(casa)
    _post(casa["manager"], mid, {"ato_id": str(ids["av"]), "motivo": MOTIVO})
    con = _con(casa)
    m = con.execute("SELECT encerrada, situacao FROM ri_matriculas WHERE id=?",
                    (mid,)).fetchone()
    con.close()
    assert m["encerrada"] == 1 and m["situacao"] == "ENCERRADA"


def test_user_leva_403_e_nada_grava(casa):
    mid, ids = _caso_ativo(casa)
    html = casa["balcao"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "encerrar-pelo-ato" not in html
    assert "Marcar ato lavrado como encerramento" not in html
    r = casa["balcao"].post(
        f"/registro-imoveis/{mid}/encerrar-pelo-ato",
        data={"csrf_token": _token(html), "ato_id": str(ids["av"]),
              "motivo": MOTIVO},
        follow_redirects=False)
    assert r.status_code == 403
    con = _con(casa)
    m = con.execute("SELECT encerrada FROM ri_matriculas WHERE id=?",
                    (mid,)).fetchone()
    assert m["encerrada"] == 0
    assert len(_audit_ok(con)) == 0
    con.close()


@pytest.mark.parametrize("motivo", ["", "   ", "curto"])
def test_motivo_curto_recusa(casa, motivo):
    mid, ids = _caso_ativo(casa)
    _post(casa["admin"], mid, {"ato_id": str(ids["av"]), "motivo": motivo})
    con = _con(casa)
    m = con.execute("SELECT encerrada FROM ri_matriculas WHERE id=?",
                    (mid,)).fetchone()
    assert m["encerrada"] == 0
    assert len(_audit_ok(con)) == 0
    con.close()


def test_nao_cria_ato_nem_muda_hash_nem_teor(casa):
    mid, ids = _caso_ativo(casa, com_r=True)
    con = _con(casa)
    antes = _hashes(con, mid)
    n_antes = len(antes)
    con.close()

    _post(casa["admin"], mid, {"ato_id": str(ids["av"]), "motivo": MOTIVO})

    con = _con(casa)
    depois = _hashes(con, mid)
    con.close()
    assert len(depois) == n_antes
    assert depois == antes


# ------------------------------------------------------------------ recusas


def test_ficha_ja_encerrada_recusa(casa):
    con = _con(casa)
    with con:
        mid = _ficha(con, encerrada=1, situacao="ENCERRADA",
                     data_encerramento="2026-11-01")
        aid = _ato(con, mid, tipo="AV", numero=1)
    con.close()
    html = _post(casa["admin"], mid,
                 {"ato_id": str(aid), "motivo": MOTIVO}).get_data(as_text=True)
    assert "já está encerrada" in html
    con = _con(casa)
    assert len(_audit_ok(con)) == 0
    con.close()


def test_ato_de_outra_matricula_recusa(casa):
    con = _con(casa)
    with con:
        mid = _ficha(con, numero="9900")
        outra = _ficha(con, numero="9901")
        _ato(con, mid, tipo="AV", numero=1)
        aid_outra = _ato(con, outra, tipo="AV", numero=1,
                         matricula_numero="9901",
                         teor="AV-01/9.901 TEOR.")
    con.close()
    _post(casa["admin"], mid,
          {"ato_id": str(aid_outra), "motivo": MOTIVO})
    con = _con(casa)
    m = con.execute("SELECT encerrada FROM ri_matriculas WHERE id=?",
                    (mid,)).fetchone()
    assert m["encerrada"] == 0
    assert len(_audit_ok(con)) == 0
    con.close()


def test_ato_cancelado_recusa(casa):
    con = _con(casa)
    with con:
        mid = _ficha(con)
        aid = _ato(con, mid, tipo="AV", numero=1, cancelado=1)
    con.close()
    _post(casa["admin"], mid, {"ato_id": str(aid), "motivo": MOTIVO})
    con = _con(casa)
    assert con.execute("SELECT encerrada FROM ri_matriculas WHERE id=?",
                       (mid,)).fetchone()["encerrada"] == 0
    assert len(_audit_ok(con)) == 0
    con.close()


def test_ato_tipo_r_recusa(casa):
    mid, ids = _caso_ativo(casa, com_r=True)
    _post(casa["admin"], mid, {"ato_id": str(ids["r"]), "motivo": MOTIVO})
    con = _con(casa)
    assert con.execute("SELECT encerrada FROM ri_matriculas WHERE id=?",
                       (mid,)).fetchone()["encerrada"] == 0
    assert len(_audit_ok(con)) == 0
    con.close()


def test_ato_inexistente_recusa(casa):
    mid, _ids = _caso_ativo(casa)
    _post(casa["admin"], mid, {"ato_id": "999999", "motivo": MOTIVO})
    con = _con(casa)
    assert con.execute("SELECT encerrada FROM ri_matriculas WHERE id=?",
                       (mid,)).fetchone()["encerrada"] == 0
    assert len(_audit_ok(con)) == 0
    con.close()


# ------------------------------------------------------------------ auditoria


def test_auditoria_guarda_campos(casa):
    mid, ids = _caso_ativo(casa)
    _post(casa["admin"], mid,
          {"ato_id": str(ids["av"]), "motivo": MOTIVO, "destino": "9901"})
    con = _con(casa)
    row = _audit_ok(con)[0]
    det = json.loads(row["details"])
    con.close()
    assert det["ato_id"] == ids["av"]
    assert det["rotulo"] == "AV-02"
    assert det["selo"] == SELO_CURTO
    assert det["motivo"] == MOTIVO
    assert det["destino"] == "9901"
    assert det["usuario"] == "mario"
    assert det["estado_anterior"]["encerrada"] == 0
    assert det["estado_anterior"]["situacao"] == "ATIVO"
    assert det["estado_anterior"]["data_encerramento"] in (None, "")


# ------------------------------------------------------------------ reabrir


def test_reabrir_desfaz_e_mostra_voltar_a_encerrar(casa):
    mid, ids = _caso_ativo(casa)
    _post(casa["admin"], mid, {"ato_id": str(ids["av"]), "motivo": MOTIVO})

    html = casa["admin"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    r = casa["admin"].post(
        f"/registro-imoveis/{mid}/reabrir",
        data={"csrf_token": _token(html),
              "motivo": "corrigir marca feita pela tela nova de encerramento"},
        follow_redirects=True)
    html = r.get_data(as_text=True)

    con = _con(casa)
    m = con.execute("SELECT encerrada, situacao, reaberta_em, data_encerramento "
                    "FROM ri_matriculas WHERE id=?", (mid,)).fetchone()
    con.close()
    assert m["encerrada"] == 0
    assert m["situacao"] == "ATIVO"
    assert m["reaberta_em"]
    assert m["data_encerramento"] == "2026-11-10"
    assert "Voltar a encerrar" in html
    assert "Marcar ato lavrado como encerramento" not in html


# ------------------------------------------------------------------ tela


def test_quadro_presente_para_admin_com_ficha_ativa(casa):
    mid, ids = _caso_ativo(casa, dois_av=True)
    html = casa["admin"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Marcar ato lavrado como encerramento" in html
    assert f'value="{ids["av2"]}"' in html
    assert "selected" in html
    # o último AV (av2) deve estar pré-selecionado
    assert re.search(
        rf'value="{ids["av2"]}"[^>]*selected|selected[^>]*value="{ids["av2"]}"',
        html)


def test_quadro_ausente_quando_encerrada(casa):
    con = _con(casa)
    with con:
        mid = _ficha(con, encerrada=1, situacao="ENCERRADA",
                     data_encerramento="2026-11-01")
        _ato(con, mid, tipo="AV", numero=1)
    con.close()
    html = casa["admin"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Marcar ato lavrado como encerramento" not in html


def test_quadro_ausente_quando_reaberta_com_data(casa):
    con = _con(casa)
    with con:
        mid = _ficha(con, encerrada=0, situacao="ATIVO",
                     reaberta_em="2026-11-15T10:00",
                     data_encerramento="2026-11-10")
        _ato(con, mid, tipo="AV", numero=1)
    con.close()
    html = casa["admin"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Voltar a encerrar" in html
    assert "Marcar ato lavrado como encerramento" not in html


def test_av_anterior_ao_ultimo_tambem_encerra(casa):
    """Decisão: não recusar AV que não é a última — só aviso na tela."""
    mid, ids = _caso_ativo(casa, dois_av=True)
    _post(casa["admin"], mid, {"ato_id": str(ids["av"]), "motivo": MOTIVO})
    con = _con(casa)
    m = con.execute("SELECT encerrada, data_encerramento FROM ri_matriculas WHERE id=?",
                    (mid,)).fetchone()
    con.close()
    assert m["encerrada"] == 1
    assert m["data_encerramento"] == "2026-11-10"
