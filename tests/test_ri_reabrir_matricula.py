"""Reabrir a matrícula encerrada — pedido do oficial em 15/09/2026.

    «faça o reabrir matricula»

O QUE FEZ ESTE CAMINHO NASCER, e por que ele não é conveniência de tela.
    A matrícula 3.110 foi encerrada em 14/09/2026 pela AV-06, que veio das
    minutas importadas da pasta de processos protocolados — e os **três atos
    daquele dia ficaram sem selo**. Medido na produção em 15/09: `encerrada=1`,
    e os AV-04, AV-05 e AV-06 com `selo_texto` vazio.

    Com a ficha fechada não havia o que fazer: `ri_ficha.html` esconde atrás de
    «não encerrada» as quatro coisas do balcão — lavrar registro ou averbação,
    lavrar a partir de modelo, editar cadastro e cancelar ato. Havia rota para
    ENCERRAR e **nenhuma para reabrir**: o encerramento tranca justamente o ato
    que o fecha.

O QUE ESTES TESTES PROTEGEM
    1. Reabrir devolve a ficha ao estado de aceitar atos.
    2. Reabrir **não apaga nem cancela** o ato de encerramento — ele está na
       corrente de hash, e apagá-lo seria reescrever a história.
    3. O motivo é escrito, e curto não passa.
    4. Voltar a encerrar **não lavra um segundo** «encerramento» na ficha.
    5. Quem não é ADMIN/MANAGER não reabre.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
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
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    db.create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("balcao", "QUEM ATENDE", SENHA, "USER")
    return {**cg_casa, "cliente": _entrar(cg_casa["app"], "jean")}

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _matricula(con, numero="3110"):
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
               tipo_ficha, criado_em)
           VALUES (?, '2-Q', '2-Q', 'ATIVO', 'ACERVO', '2026-09-14T10:27')""",
        (numero,))
    return int(cur.lastrowid)


def _ato(con, matricula_id, *, numero, teor="AV-0X/3.110 — ato do dia."):
    from ri_schema import hash_ato
    h = hash_ato("3110", "AV", numero, "2026-09-14", teor, None)
    cur = con.execute(
        """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, teor,
               teor_formato, cancelado, acervo, origem, hash_ato, lavrado_em)
           VALUES (?, 'AV', ?, '2026-09-14', ?, 'texto', 0, 0, 'MANUAL', ?,
                   '2026-09-14T22:00')""",
        (matricula_id, numero, teor, h))
    return int(cur.lastrowid)


def _encerrada(casa, *, com_atos=3):
    """A ficha como a produção a deixou: encerrada, com os atos sem selo."""
    con = _con(casa)
    with con:
        mid = _matricula(con)
        for n in range(4, 4 + com_atos):
            _ato(con, mid, numero=n)
        con.execute(
            """UPDATE ri_matriculas SET encerrada=1, situacao='ENCERRADA',
               motivo_encerramento=?, data_encerramento='2026-09-14'
             WHERE id=?""",
            ("Escrituração encerrada pela AV-06/3.110 e transportada para a "
             "ficha da 4.016.", mid))
    con.close()
    return mid


def _reabrir(casa, mid, motivo, cliente=None):
    c = cliente or casa["cliente"]
    html = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    return c.post(f"/registro-imoveis/{mid}/reabrir",
                  data={"csrf_token": _token(html), "motivo": motivo},
                  follow_redirects=True)


# ------------------------------------------------------------------ a volta


def test_a_ficha_encerrada_esconde_o_balcao_e_oferece_a_volta(casa):
    """O sintoma que o oficial relatou, e o botão que passa a existir."""
    mid = _encerrada(casa)
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)

    assert "Lavrar novo ato nesta matrícula" not in html
    assert "Lavrar a partir de modelo" not in html
    assert "Matrícula encerrada em" in html
    assert "Reabrir esta matrícula" in html, (
        "a ficha encerrada precisa oferecer o caminho de volta — sem ele nem "
        "o selo do ato que a fechou tem por onde sair")


def test_reabrir_devolve_o_balcao_sem_apagar_o_encerramento(casa):
    mid = _encerrada(casa)
    resposta = _reabrir(casa, mid, "selar os três atos de 14/09, que ficaram sem selo")
    html = resposta.get_data(as_text=True)

    con = _con(casa)
    m = con.execute("SELECT * FROM ri_matriculas WHERE id=?", (mid,)).fetchone()
    atos = con.execute(
        "SELECT numero, cancelado FROM ri_atos WHERE matricula_id=? ORDER BY numero",
        (mid,)).fetchall()
    con.close()

    assert not m["encerrada"]
    assert m["situacao"] == "ATIVO"
    assert m["reaberta_em"]
    assert m["reaberta_por"] == "MARIO EXEMPLO DOS SANTOS"
    assert "sem selo" in (m["motivo_reabertura"] or "")

    # O ENCERRAMENTO CONTINUA ESCRITO — reabrir não reescreve a história.
    assert [a["numero"] for a in atos] == [4, 5, 6]
    assert all(not a["cancelado"] for a in atos)
    assert m["motivo_encerramento"], "o motivo do encerramento não se apaga"
    assert m["data_encerramento"] == "2026-09-14"

    # E o balcão voltou.
    assert "Lavrar novo ato nesta matrícula" in html
    assert "Ficha reaberta em" in html, (
        "ficha reaberta tem de dizer que foi reaberta — senão fica idêntica "
        "a uma que nunca foi encerrada, com um ato de encerramento no meio")


def test_motivo_curto_nao_reabre(casa):
    mid = _encerrada(casa)
    _reabrir(casa, mid, "ok")
    con = _con(casa)
    m = con.execute("SELECT encerrada, reaberta_em FROM ri_matriculas WHERE id=?",
                    (mid,)).fetchone()
    con.close()
    assert m["encerrada"] == 1
    assert not m["reaberta_em"]


def test_matricula_aberta_nao_tem_o_que_reabrir(casa):
    con = _con(casa)
    with con:
        mid = _matricula(con, numero="4016")
    con.close()
    html = _reabrir(casa, mid, "tentativa sobre ficha que está aberta").get_data(
        as_text=True)
    assert "não está encerrada" in html


def test_quem_atende_nao_reabre(casa):
    """Reabrir é do oficial — a mesma régua do encerrar."""
    mid = _encerrada(casa)
    balcao = _entrar(casa["app"], "balcao")
    # O token vem da própria ficha: sem ele o CSRF recusa ANTES do perfil, e
    # o teste passaria sem nunca ter exercitado a guarda que ele diz guardar.
    ficha = balcao.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    resposta = balcao.post(f"/registro-imoveis/{mid}/reabrir",
                           data={"csrf_token": _token(ficha),
                                 "motivo": "quero reabrir esta ficha aqui"},
                           follow_redirects=False)
    assert resposta.status_code in (302, 403)
    assert "Reabrir esta matrícula" not in ficha, (
        "quem não pode reabrir também não vê o botão")
    con = _con(casa)
    encerrada = con.execute("SELECT encerrada FROM ri_matriculas WHERE id=?",
                            (mid,)).fetchone()["encerrada"]
    con.close()
    assert encerrada == 1


# ------------------------------------------------- voltar a fechar não dobra


def test_voltar_a_encerrar_nao_lavra_um_segundo_encerramento(casa):
    """Dois «ENCERRAMENTO DESTA MATRÍCULA» na mesma ficha e ninguém sabe qual vale."""
    mid = _encerrada(casa)
    _reabrir(casa, mid, "selar os atos de 14/09 antes de fechar de novo")

    c = casa["cliente"]
    html = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Voltar a encerrar" in html, (
        "a ficha reaberta oferece voltar ao encerramento que já está no livro")

    depois = c.post(f"/registro-imoveis/{mid}/encerrar",
                    data={"csrf_token": _token(html)},
                    follow_redirects=True).get_data(as_text=True)
    assert "Nenhum ato novo foi lavrado" in depois

    con = _con(casa)
    m = con.execute("SELECT * FROM ri_matriculas WHERE id=?", (mid,)).fetchone()
    numeros = [r["numero"] for r in con.execute(
        "SELECT numero FROM ri_atos WHERE matricula_id=? ORDER BY numero", (mid,))]
    con.close()

    assert m["encerrada"] == 1
    assert m["situacao"] == "ENCERRADA"
    assert numeros == [4, 5, 6], f"lavrou ato a mais ao re-encerrar: {numeros}"
    # A marca da reabertura sai quando ela deixa de valer.
    assert not m["reaberta_em"]
    assert m["data_encerramento"] == "2026-09-14", (
        "o encerramento que vale continua sendo o do livro, e não a data de hoje")


def test_matricula_nunca_encerrada_continua_lavrando_o_ato_de_encerramento(casa):
    """O caminho normal não muda: quem nunca foi encerrada lavra a AV."""
    con = _con(casa)
    with con:
        mid = _matricula(con, numero="4017")
        _ato(con, mid, numero=1)
    con.close()

    c = casa["cliente"]
    html = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    c.post(f"/registro-imoveis/{mid}/encerrar",
           data={"csrf_token": _token(html), "motivo": "unificação",
                 "destino": "4018"}, follow_redirects=True)

    con = _con(casa)
    atos = [dict(r) for r in con.execute(
        "SELECT numero, teor FROM ri_atos WHERE matricula_id=? ORDER BY numero",
        (mid,))]
    encerrada = con.execute("SELECT encerrada FROM ri_matriculas WHERE id=?",
                            (mid,)).fetchone()["encerrada"]
    con.close()
    assert encerrada == 1
    assert len(atos) == 2, "o encerramento continua sendo lavrado como averbação"
    assert "ENCERRAMENTO DESTA MATRÍCULA" in atos[-1]["teor"]
