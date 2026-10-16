"""Sinais publicos — abertura + PDF + reconhecimento autonomo (fatia 1).

Regras medidas / oficiais (07/09/2026):
    - abertura NAO sela
    - PDF em arquivos/notas/sinais/<id>/ (sem BLOB no SQLite)
    - tabelas proprias nt_sinais_publicos / nt_sinais_reconhecimentos
    - reconhecimento autonomo usa servico 413
    - checkbox de firma «reconhecer tambem o sinal» permanece intacto
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from io import BytesIO
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"
PDF_MINIMO = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    c = cg_casa["cliente"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def test_schema_cria_tabelas_de_sinal(casa):
    con = _con(casa)
    nomes = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "nt_sinais_publicos" in nomes
    assert "nt_sinais_reconhecimentos" in nomes
    cols = {r[1] for r in con.execute("PRAGMA table_info(nt_sinais_publicos)")}
    assert "caminho_pdf" in cols
    assert "selo_abertura" not in cols  # abertura nao sela


def test_servico_sinal_e_413():
    from notas_schema import SERVICOS
    assert SERVICOS["SINAL"] == 413
    assert SERVICOS["SINAL"] == SERVICOS["SEMELHANCA"]


def test_lista_e_cria_sinal_sem_selo(casa):
    c = casa["cliente"]
    r = c.get("/notas/sinais")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Sinais públicos" in html or "Sinais publicos" in html
    assert "csrf_token" in html

    tok = _token(html)
    r2 = c.post("/notas/sinais", data={
        "csrf_token": tok,
        "acao": "novo",
        "titular": "CARTORIO DE EXEMPLO DA SILVA",
        "documento": "12345678901",
        "origem": "CNSIP",
        "data_abertura": "2026-09-07",
    }, follow_redirects=True)
    assert r2.status_code == 200
    body = r2.get_data(as_text=True)
    assert "abertura não sela" in body.lower() or "Abertura não sela" in body or "não sela" in body.lower()

    con = _con(casa)
    row = con.execute(
        "SELECT * FROM nt_sinais_publicos WHERE titular LIKE ?",
        ("%EXEMPLO%",)).fetchone()
    assert row is not None
    # nenhuma coluna de selo na abertura
    assert row["caminho_pdf"] is None


def test_upload_pdf_vai_para_disco(casa):
    con = _con(casa)
    cur = con.execute(
        """INSERT INTO nt_sinais_publicos
           (titular, titular_norm, origem, criado_em)
           VALUES ('TABELIAO TESTE', 'tabeliao teste', 'CENSEC', '2026-09-07T12:00:00')""")
    con.commit()
    sid = int(cur.lastrowid)
    con.close()

    c = casa["cliente"]
    html = c.get(f"/notas/sinais/{sid}").get_data(as_text=True)
    tok = _token(html)
    r = c.post(f"/notas/sinais/{sid}", data={
        "csrf_token": tok,
        "acao": "pdf",
        "pdf": (BytesIO(PDF_MINIMO), "sinal-central.pdf"),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert r.status_code == 200

    con = _con(casa)
    row = con.execute("SELECT * FROM nt_sinais_publicos WHERE id=?", (sid,)).fetchone()
    assert row["caminho_pdf"]
    assert "notas" in row["caminho_pdf"].replace("\\", "/")
    assert "sinais" in row["caminho_pdf"].replace("\\", "/")
    assert str(sid) in row["caminho_pdf"]
    assert row["sha256"]
    assert row["bytes"] == len(PDF_MINIMO)
    # PDF no disco, nao BLOB
    blob_cols = {r[1] for r in con.execute("PRAGMA table_info(nt_sinais_publicos)")}
    assert "pdf" not in blob_cols and "conteudo" not in blob_cols

    from pathlib import Path as P
    raiz = P(casa["db"].get_setting("archive_root", "") or
             (casa["banco"].parent / "arquivos"))
    alvo = raiz / row["caminho_pdf"]
    assert alvo.is_file()
    assert alvo.read_bytes()[:4] == b"%PDF"

    # rota serve o PDF
    pdf = c.get(f"/notas/sinais/{sid}/pdf")
    assert pdf.status_code == 200
    assert pdf.data[:4] == b"%PDF"


def test_reconhecimento_autonomo_grava_ato_com_413(casa, monkeypatch):
    """Lavra o ato com selo e conserva o serviço 413."""
    casa["db"].set_settings({"selo_tabela_custas_em": "20260101",
                              "ri_cns": "000000"})
    con = _con(casa)
    with con:
        con.execute(
            "INSERT OR REPLACE INTO cx_servicos(codigo, codigo_tj, descricao) "
            "VALUES (413, '13.17.2', 'Reconhecimento de sinal')")
    cur = con.execute(
        """INSERT INTO nt_sinais_publicos
           (titular, titular_norm, documento, origem, caminho_pdf, criado_em)
           VALUES ('OFICIAL MODELO', 'oficial modelo', '00987654321',
                   'CNSIP', 'notas/sinais/1/sinal-1.pdf', '2026-09-07T12:00:00')""")
    sid = int(cur.lastrowid)
    # cria arquivo falso no caminho esperado
    from pathlib import Path as P
    raiz = P(casa["db"].get_setting("archive_root", "") or
             (casa["banco"].parent / "arquivos"))
    pasta = raiz / "notas" / "sinais" / str(sid)
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / f"sinal-{sid}.pdf").write_bytes(PDF_MINIMO)
    con.execute("UPDATE nt_sinais_publicos SET caminho_pdf=? WHERE id=?",
                (f"notas/sinais/{sid}/sinal-{sid}.pdf", sid))
    con.commit()
    con.close()

    # evita rede: a bancada devolve um selo válido. Este teste mede o registro
    # do reconhecimento; falha de selo é coberta pela régua geral.
    import ato_selado as AS

    def _fake_selar(*a, **k):
        return {"selado": True, "numero": "SINALP000000TESTE0000000001",
                "numeros": ["SINALP000000TESTE0000000001"],
                "motivo": None}

    monkeypatch.setattr(AS, "selar_o_ato_lavrado", _fake_selar)

    c = casa["cliente"]
    html = c.get("/notas/sinais/reconhecimento").get_data(as_text=True)
    tok = _token(html)
    # precisa achar o sinal na busca
    html2 = c.get("/notas/sinais/reconhecimento?busca=OFICIAL").get_data(as_text=True)
    tok = _token(html2)
    r = c.post("/notas/sinais/reconhecimento", data={
        "csrf_token": tok,
        "acao": "reconhecer",
        "sinal_id": str(sid),
        "documento_descricao": "procuração teste",
    }, follow_redirects=True)
    assert r.status_code == 200

    con = _con(casa)
    rec = con.execute(
        "SELECT * FROM nt_sinais_reconhecimentos WHERE sinal_id=?",
        (sid,)).fetchone()
    assert rec is not None
    assert rec["servico_codigo"] == 413
    assert "SINAL PÚBLICO" in (rec["texto"] or "").upper() or "SINAL PUBLICO" in (rec["texto"] or "").upper().replace("Ú", "U")
    # nao misturou com nt_reconhecimentos
    assert con.execute("SELECT COUNT(*) FROM nt_reconhecimentos").fetchone()[0] == 0


def test_menu_tem_sinais(casa):
    html = casa["cliente"].get("/notas/sinais").get_data(as_text=True)
    assert "/notas/sinais" in html
    assert "Sinais" in html
