"""Livro 3: escolha de item, arquivamento por ato e retirada recuperável."""
from __future__ import annotations

import io
import re
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

import ato_selado as AS
import ra_digitalizacao as DIGI
import ra_selo as RS
from app import create_app
import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402


def _csrf(html):
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def _casa(td):
    app = create_app({"TESTING": True, "DATA_DIR": td})
    app.extensions["backup_checked"] = True
    app.extensions["cnib_verificado"] = True
    db = app.extensions["db"]
    db.create_user("admin", "Administrador", "Senha#12345", "ADMIN")
    c = app.test_client()
    login = c.get("/login").get_data(as_text=True)
    c.post("/login", data={"username": "admin", "password": "Senha#12345",
                           "csrf_token": _csrf(login)}, follow_redirects=True)
    return app, db, c


def _ato(db, *, prenotacao="11546", selo="ATO123"):
    with db.transaction() as con:
        con.execute(
            """INSERT INTO ri_protocolos(numero, data_prenotacao, situacao,
                   criado_em) VALUES (11546,'2026-09-28','ABERTO',?)""",
            (db.now(),))
        cur = con.execute(
            """INSERT INTO ra_registros(numero,livro,natureza,situacao,
                   prenotacao,criado_em) VALUES
                   (2500,'3','CEDULA_CREDITO_RURAL','ATIVO',?,?)""",
            (prenotacao, db.now()))
        rid = cur.lastrowid
        cur = con.execute(
            """INSERT INTO ra_atos(registro_id,tipo,numero,data_ato,
                   selo,criado_em) VALUES (?,'R',1,'2026-09-28',?,?)""",
            (rid, selo, db.now()))
        con.execute(
            "INSERT INTO ra_partes(registro_id,nome,papel) VALUES (?,?,?)",
            (rid, "PARTE DE TESTE", "EMITENTE"))
        return rid, cur.lastrowid


def test_seletor_inclui_subitem_1645_vigente_sem_limite_30():
    con = conexao_de_teste()
    con.executescript("""
        CREATE TABLE cx_servicos(codigo INTEGER, codigo_tj TEXT,
            descricao TEXT, ativo INTEGER);
        CREATE TABLE cx_vigencias(codigo INTEGER, vigente INTEGER);
        CREATE TABLE cx_servico_valores(servico INTEGER, vigencia INTEGER,
            total INTEGER);
        INSERT INTO cx_vigencias VALUES (1,1);
    """)
    for i in range(1, 29):
        con.execute("INSERT INTO cx_servicos VALUES (?,?,?,1)",
                    (i, f"16.45.{i}", f"Faixa {i}"))
        con.execute("INSERT INTO cx_servico_valores VALUES (?,1,100)", (i,))
    con.execute("INSERT INTO cx_servicos VALUES (99,'16.45','Cabeçalho',1)")
    con.execute("INSERT INTO cx_servico_valores VALUES (99,1,NULL)")
    codigos = [x[0] for x in RS.itens_disponiveis(con)]
    assert "16.45.23" in codigos
    assert "16.45.28" in codigos
    assert "16.45" not in codigos


def test_arquivamento_sela_folhas_e_encerra_so_depois_do_sucesso(monkeypatch):
    with TemporaryDirectory() as td:
        app, db, c = _casa(td)
        rid, aid = _ato(db)
        monkeypatch.setattr(AS, "versao_da_tabela_de_custas",
                            lambda *_: "0220260101")
        chamadas = []
        def selo_falso(*args, **kwargs):
            chamadas.append(kwargs)
            if len(chamadas) == 1:
                return {"selado": False, "motivo": "aparelho indisponível"}
            return {"selado": True, "numero": "ARQ123"}
        monkeypatch.setattr(AS, "selar_o_ato_lavrado", selo_falso)
        ficha = c.get(f"/livro3/{rid}").get_data(as_text=True)
        dados = {"csrf_token": _csrf(ficha), "folhas_arquivamento": "7"}
        c.post(f"/livro3/ato/{aid}/selar-arquivamento", data=dados,
               follow_redirects=True)
        with db.connect() as con:
            assert con.execute("SELECT situacao FROM ri_protocolos WHERE numero=11546").fetchone()[0] == "ABERTO"
            assert con.execute("SELECT selo_arquivamento FROM ra_atos WHERE id=?", (aid,)).fetchone()[0] is None
        c.post(f"/livro3/ato/{aid}/selar-arquivamento", data=dados,
               follow_redirects=True)
        with db.connect() as con:
            ato = con.execute("SELECT selo, selo_arquivamento, folhas_arquivamento FROM ra_atos WHERE id=?", (aid,)).fetchone()
            assert tuple(ato) == ("ATO123", "ARQ123", 7)
            assert con.execute("SELECT situacao FROM ri_protocolos WHERE numero=11546").fetchone()[0] == "ENCERRADO"
        assert len(chamadas) == 2
        assert chamadas[1]["dados"]["quantidade"] == 7
        c.post(f"/livro3/ato/{aid}/selar-arquivamento", data=dados,
               follow_redirects=True)
        assert len(chamadas) == 2


def test_novo_registro_usa_item_escolhido_e_folhas_do_r1(monkeypatch):
    with TemporaryDirectory() as td:
        app, db, c = _casa(td)
        monkeypatch.setattr(RS, "itens_disponiveis",
                            lambda con: [("16.45.23", "Faixa da garantia")])
        chamadas = []
        app.extensions["selar_o_ato_do_livro3"] = lambda **kw: (
            chamadas.append(("selo", kw)) or {"recado": " Selo teste.", "selado": True})
        app.extensions["arquivar_o_ato_do_livro3"] = lambda **kw: (
            chamadas.append(("arquivamento", kw)) or {"ok": True, "recado": "Arquivado."})
        html = c.get("/livro3/novo").get_data(as_text=True)
        assert 'value="16.45.23"' in html
        c.post("/livro3/novo", data={
            "csrf_token": _csrf(html), "natureza": "CEDULA_CREDITO_RURAL",
            "parte_nome": ["PARTE TESTE"], "parte_papel": ["EMITENTE"],
            "codigo_tj": "16.45.23", "natureza_titulo": "GARANTIA REAL",
            "base_calculo": "695.000,00", "prenotacao": "11546",
            "gerar_arquivamento": "1", "folhas_arquivamento": "12",
        }, follow_redirects=True)
        assert [x[0] for x in chamadas] == ["selo", "arquivamento"]
        assert chamadas[0][1]["codigo_tj"] == "16.45.23"
        assert chamadas[1][1]["folhas"] == 12
        with db.connect() as con:
            a = con.execute("SELECT codigo_tj, folhas_arquivamento FROM ra_atos ORDER BY id DESC LIMIT 1").fetchone()
            assert tuple(a) == ("16.45.23", 12)


def test_averbacao_usa_folhas_proprias(monkeypatch):
    with TemporaryDirectory() as td:
        app, db, c = _casa(td)
        rid, _ = _ato(db)
        chamadas = []
        app.extensions["selar_o_ato_do_livro3"] = lambda **kw: (
            chamadas.append(("selo", kw)) or {"recado": " Selo teste.", "selado": True})
        app.extensions["arquivar_o_ato_do_livro3"] = lambda **kw: (
            chamadas.append(("arquivamento", kw)) or {"ok": True, "recado": "Arquivado."})
        html = c.get(f"/livro3/{rid}").get_data(as_text=True)
        c.post(f"/livro3/{rid}/lancar", data={
            "csrf_token": _csrf(html), "tipo": "AVERBACAO",
            "teor": "AVERBAÇÃO DE TESTE COM DESCRIÇÃO SUFICIENTE",
            "codigo_tj": "16.22.2", "natureza_titulo": "ADITIVO",
            "gerar_arquivamento": "1", "folhas_arquivamento": "3",
        }, follow_redirects=True)
        assert [x[0] for x in chamadas] == ["selo", "arquivamento"]
        assert chamadas[1][1]["folhas"] == 3
        with db.connect() as con:
            assert con.execute("SELECT folhas_arquivamento FROM ra_atos ORDER BY id DESC LIMIT 1").fetchone()[0] == 3


def test_retirar_arquivo_da_ficha_e_do_ato_preserva_historico():
    with TemporaryDirectory() as td:
        app, db, c = _casa(td)
        rid, aid = _ato(db)
        ficha = c.get(f"/livro3/{rid}").get_data(as_text=True)
        token = _csrf(ficha)
        assert "Retirar arquivo" not in ficha
        c.post(f"/livro3/{rid}/digitalizacao",
               data={"csrf_token": token,
                     "arquivo": (io.BytesIO(b"%PDF-1.4 errado"), "errado.pdf")},
               content_type="multipart/form-data", follow_redirects=True)
        with db.connect() as con:
            anterior = DIGI.atual(con, rid)
        assert anterior and Path(anterior["digi_path"]).is_file()
        assert "Retirar arquivo enviado" in c.get(
            f"/livro3/{rid}/conferir").get_data(as_text=True)
        c.post(f"/livro3/{rid}/digitalizacao/retirar",
               data={"csrf_token": token, "motivo": "envio equivocado"},
               follow_redirects=True)
        with db.connect() as con:
            assert DIGI.atual(con, rid) is None
        assert not Path(anterior["digi_path"]).exists()
        assert list((Path(anterior["digi_path"]).parent / "historico").glob("*retirado*"))
        c.post(f"/livro3/{rid}/digitalizacao",
               data={"csrf_token": token,
                     "arquivo": (io.BytesIO(b"%PDF-1.4 correto"), "correto.pdf")},
               content_type="multipart/form-data", follow_redirects=True)
        with db.connect() as con:
            assert DIGI.atual(con, rid)["digi_nome"] == "correto.pdf"
        c.post(f"/livro3/ato/{aid}/digitalizacao",
               data={"csrf_token": token,
                     "arquivo": (io.BytesIO(b"%PDF-1.4 termo"), "termo.pdf")},
               content_type="multipart/form-data", follow_redirects=True)
        c.post(f"/livro3/ato/{aid}/digitalizacao/retirar",
               data={"csrf_token": token, "motivo": "arquivo incorreto"},
               follow_redirects=True)
        with db.connect() as con:
            assert DIGI.atual_do_ato(con, aid) is None
