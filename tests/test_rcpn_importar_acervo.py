
"""Testes do submodulo RCPN de importacao de acervo.

O QUE ELES CONFEREM
    - a tela abre sob /rcpn/importar-acervo;
    - a previa conta sem gravar;
    - a importacao usa carregar_rcpn (origem EOFICIO) e e idempotente;
    - arquivo ZIP/SQLite monta o acervo antes da carga;
    - papel insuficiente (USER) nao entra.
"""
from __future__ import annotations

import io
import json
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — importacao de acervo
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import acervo_carga as AC  # noqa: E402

SENHA = "Senha#12345"


def _token(html: str) -> str:
    import re
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


def _sessao(cg_casa, papel: str = "ADMIN"):
    import glob
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    cg_casa['db'].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                                SENHA, papel)
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco, "dados": dados}


@pytest.fixture()
def s(cg_casa):
    return _sessao(cg_casa)


def _montar_acervo_minimo(destino: Path) -> None:
    """Um sqlite de acervo so com nascimento — o bastante para a previa."""
    con = sqlite3.connect(destino)
    con.executescript("""
        CREATE TABLE tbRegistroNascimento (
            intChave REAL, strNomeNascido TEXT, dtmDataNascimento TEXT,
            dtmDataAssento TEXT, strNumeroMatricula TEXT,
            intNumeroRegistro REAL, strLivro TEXT, strTipoLivro TEXT,
            intFolha REAL, strSexo TEXT, memTexto TEXT);
        INSERT INTO tbRegistroNascimento(
            intChave, strNomeNascido, dtmDataNascimento, dtmDataAssento,
            strNumeroMatricula, intNumeroRegistro, strLivro, strTipoLivro,
            intFolha, strSexo)
          VALUES (1,'ANA TESTE','2020-01-15 00:00:00','2020-01-20 00:00:00',
                  '123', 100, '1', 'A', 10, 'F');
        INSERT INTO tbRegistroNascimento(
            intChave, strNomeNascido, dtmDataNascimento, dtmDataAssento,
            strNumeroMatricula, intNumeroRegistro, strLivro, strTipoLivro,
            intFolha, strSexo)
          VALUES (2,'','2020-02-01 00:00:00','2020-02-02 00:00:00',
                  '124', 101, '1', 'A', 11, 'M');
    """)
    con.commit()
    con.close()


def test_a_tela_abre_sem_acervo(s):
    html = s["c"].get("/rcpn/importar-acervo").get_data(as_text=True)
    assert "Importar acervo do Registro Civil" in html
    assert "acervo não está no lugar" in html
    assert "Carregar o acervo" in html


def test_o_escrevente_abre_a_tela(cg_casa):
    # Aberta ao perfil USER na 3.6.160 (21/09/2026); confirmado pelo oficial
    # em 11/10/2026: «manter abertas».
    sessao = _sessao(cg_casa, papel="USER")
    assert sessao["c"].get("/rcpn/importar-acervo").status_code == 200


def test_previa_conta_sem_gravar(s):
    destino = Path(s["app"].config["DATA_DIR"]) / AC.NOME_ACERVO
    _montar_acervo_minimo(destino)
    html = s["c"].get("/rcpn/importar-acervo").get_data(as_text=True)
    assert "entrariam agora" in html
    assert "ANA TESTE" in html
    # Nada gravado ainda.
    con = sqlite3.connect(s["banco"])
    n = con.execute("SELECT COUNT(*) FROM rc_assentos").fetchone()[0]
    con.close()
    assert n == 0


def test_importar_e_idempotente(s):
    destino = Path(s["app"].config["DATA_DIR"]) / AC.NOME_ACERVO
    _montar_acervo_minimo(destino)
    c = s["c"]
    token = _token(c.get("/rcpn/importar-acervo").get_data(as_text=True))
    html = c.post("/rcpn/importar-acervo",
                  data={"csrf_token": token, "o_que": "importar"},
                  follow_redirects=True).get_data(as_text=True)
    assert "Importação do RCPN concluída" in html
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT nome, origem, origem_chave FROM rc_assentos"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["nome"] == "ANA TESTE"
    assert rows[0]["origem"] == "EOFICIO"
    assert rows[0]["origem_chave"] == "tbRegistroNascimento:1.0" or \
        rows[0]["origem_chave"].startswith("tbRegistroNascimento:1")
    con.close()

    token = _token(c.get("/rcpn/importar-acervo").get_data(as_text=True))
    c.post("/rcpn/importar-acervo",
           data={"csrf_token": token, "o_que": "importar"},
           follow_redirects=True)
    con = sqlite3.connect(s["banco"])
    n = con.execute("SELECT COUNT(*) FROM rc_assentos").fetchone()[0]
    con.close()
    assert n == 1


def test_previa_rcpn_helper_so_le():
    from tests.test_acervo_carga import banco, acervo_falso
    con, acervo = banco(), acervo_falso()
    p1 = AC.previa_rcpn(con, acervo)
    assert p1["total_no_acervo"] >= 1
    assert p1["total_novos"] >= 1
    assert con.execute("SELECT COUNT(*) FROM rc_assentos").fetchone()[0] == 0
    # Depois da carga, a previa marca ja importados.
    AC.carregar_rcpn(con, acervo, agora="2026-09-07T12:00:00")
    p2 = AC.previa_rcpn(con, acervo)
    assert p2["total_novos"] == 0
    assert p2["total_ja"] >= 1


def test_carregar_acervo_por_sqlite_upload(s):
    # Monta um sqlite temporario e envia como upload.
    tmp = s["dados"] / "envio.sqlite3"
    _montar_acervo_minimo(tmp)
    c = s["c"]
    token = _token(c.get("/rcpn/importar-acervo").get_data(as_text=True))
    with tmp.open("rb") as fh:
        html = c.post(
            "/rcpn/importar-acervo",
            data={"csrf_token": token, "o_que": "carregar_arquivo",
                  "arquivo": (fh, "acervo_eoficio.sqlite3")},
            content_type="multipart/form-data",
            follow_redirects=True,
        ).get_data(as_text=True)
    assert "Acervo carregado" in html
    assert (Path(s["app"].config["DATA_DIR"]) / AC.NOME_ACERVO).exists()
    assert "ANA TESTE" in html


def test_carregar_acervo_por_zip_jsonl(s, tmp_path):
    export = tmp_path / "EXPORT"
    export.mkdir()
    linhas = [
        {"intChave": 9, "strNomeNascido": "ZIP NASCIDO",
         "dtmDataNascimento": "2019-01-01", "dtmDataAssento": "2019-01-02",
         "strNumeroMatricula": "999", "intNumeroRegistro": 9,
         "strLivro": "1", "strTipoLivro": "A", "intFolha": 1, "strSexo": "M"},
    ]
    with (export / "tbRegistroNascimento.jsonl").open("w", encoding="utf-8") as fh:
        for L in linhas:
            fh.write(json.dumps(L, ensure_ascii=False) + "\n")
    with (export / "MANIFESTO.jsonl").open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"tabela": "tbRegistroNascimento", "linhas": 1}) + "\n")
    with (export / "ESQUEMA.jsonl").open("w", encoding="utf-8") as fh:
        for i, col in enumerate(linhas[0], 1):
            fh.write(json.dumps({
                "tabela": "tbRegistroNascimento", "ordem": i,
                "coluna": col, "tipo": "nvarchar"}) + "\n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for p in export.iterdir():
            zf.write(p, arcname=p.name)
    buf.seek(0)
    c = s["c"]
    token = _token(c.get("/rcpn/importar-acervo").get_data(as_text=True))
    html = c.post(
        "/rcpn/importar-acervo",
        data={"csrf_token": token, "o_que": "carregar_arquivo",
              "arquivo": (buf, "export_eoficio.zip")},
        content_type="multipart/form-data",
        follow_redirects=True,
    ).get_data(as_text=True)
    assert "Acervo carregado" in html
    assert "ZIP NASCIDO" in html

def test_hub_na_lista_de_assentos(s):
    """Na lista de assentos: ler documentos e digitar. A importação do E-Ofício
    saiu por ordem do oficial em 12/10/2026 («tire aquela aba de importar do
    e-oficio, nao faz mais sentido») — a rota fica, sem link."""
    html = s["c"].get("/rcpn").get_data(as_text=True)
    assert "/rcpn/importar-acervo" not in html
    # 12/10/2026, o oficial: «não tem pq ter dois lugares para importar assentos
    # pela leitura» — a leitura mora na tela de preencher, e o card leva até ela.
    assert "Preencher pelos documentos" in html and "/rcpn/novo" in html
    assert "Digitar as informações" in html
    assert "do_acervo=1" in html


def test_importar_acervo_oferece_digitar(s):
    html = s["c"].get("/rcpn/importar-acervo").get_data(as_text=True)
    assert "Prefere digitar" in html
    assert "Digitar as informações" in html
    assert "/rcpn/novo" in html


def test_digitar_do_acervo_mostra_aviso(s):
    html = s["c"].get("/rcpn/novo?do_acervo=1").get_data(as_text=True)
    assert "Assento já lavrado" in html or "já lavrado" in html
    # 12/10/2026: o botão da importação do E-Ofício deu lugar à leitura — e, no
    # mesmo dia, a leitura passou a morar na própria tela de preencher. No
    # assento já lavrado (do acervo) não se oferece leitura: ela é para ato novo.
    assert "/rcpn/importar-acervo" not in html
    assert "Juntar os documentos e preencher os campos" not in html
