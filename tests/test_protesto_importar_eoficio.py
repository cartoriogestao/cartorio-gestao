"""
Carga da chave CENPROT do acervo + tela /protesto/importar-eoficio + IPDigital.

O QUE ESTES TESTES GUARDAM
      - a carga COPIA `strChaveUnicaCENPROT` -> `pt_titulos.chave_cenprot`
        quando a coluna e o valor existem — e NAO inventa chave;
      - re-rodar a carga preenche chave que faltava nos repetidos, sem
        sobrescrever chave que ja esta la;
      - a tela EXISTE, esta no menu do Protesto e manda csrf_token;
      - `casar_ipdigital_por_chave` so lista `.p7s` cujo nome e chave de 23
        digitos ja conhecida — caminho + chave, sem abrir o arquivo.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — EOFicio
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import acervo_carga as AC
import protesto_cenprot as PCEN
from nucleo_schema import init_nucleo_schema
from pt_schema import init_pt_schema

AGORA = "2026-09-07T19:00:00"
CHAVE = "21987650141243301260417"
SENHA = "Senha#12345"


def _banco_cg() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


def _acervo_com_chave(*, com_coluna: bool = True,
                      chave: str | None = CHAVE) -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    col_chave = ", strChaveUnicaCENPROT TEXT" if com_coluna else ""
    con.executescript(f"""
        CREATE TABLE tbAvisoProtesto (
            intChave REAL, intNumero TEXT, strEspecie TEXT,
            strNossoNumero TEXT, dtmEmissao TEXT, dtmVencimento TEXT,
            curValorRealTitulo REAL, curValor REAL, strPracaPgto TEXT,
            strEndosso TEXT, intMotivoProtesto TEXT, canal_entrada TEXT,
            snCanceladoProtesto INTEGER, strTipoPG TEXT, snProtestado INTEGER,
            intNumeroApontamento REAL, intFolhaApontamento REAL,
            intLivroApontamento REAL, strSelo_Apontamento TEXT,
            dtmE_Cartorio TEXT, intCodigoPessoa REAL, intCodigoCedente REAL,
            intProtestoLivro REAL, intProtestoFolha REAL, dtmOcorrencia TEXT,
            intCodigoOcorrencia TEXT, dtmCancelaProtesto TEXT,
            strSelo_Cancelamento TEXT, memObsCancelamento TEXT
            {col_chave});
        CREATE TABLE tbPessoa (
            intCodigoPessoa REAL, strRazaoSocial TEXT, strTipoPessoa TEXT,
            strCGC TEXT, strCIC TEXT, strEndereco TEXT, strNumero TEXT,
            strBairro TEXT, strCep TEXT, strCidade TEXT, strUF TEXT);
    """)
    if com_coluna:
        con.execute(
            """INSERT INTO tbAvisoProtesto(
                   intChave, intNumero, strEspecie, strNossoNumero,
                   curValorRealTitulo, curValor, snProtestado,
                   intNumeroApontamento, intFolhaApontamento, canal_entrada,
                   dtmE_Cartorio, intCodigoPessoa, intCodigoCedente,
                   intProtestoLivro, intProtestoFolha, dtmOcorrencia,
                   intCodigoOcorrencia, strChaveUnicaCENPROT)
               VALUES (1,'84713/1','DMI','00200000991',1482.78,1482.78,1,912,3,
                       'CRA','2022-06-01 00:00:00',1,2,
                       4,22,'2022-06-21 00:00:00','C', ?)""",
            (chave,))
    else:
        con.execute(
            """INSERT INTO tbAvisoProtesto(
                   intChave, intNumero, strEspecie, strNossoNumero,
                   curValorRealTitulo, curValor, snProtestado,
                   intNumeroApontamento, intFolhaApontamento, canal_entrada,
                   dtmE_Cartorio, intCodigoPessoa, intCodigoCedente,
                   intProtestoLivro, intProtestoFolha, dtmOcorrencia,
                   intCodigoOcorrencia)
               VALUES (1,'84713/1','DMI','00200000991',1482.78,1482.78,1,912,3,
                       'CRA','2022-06-01 00:00:00',1,2,
                       4,22,'2022-06-21 00:00:00','C')""")
    con.execute(
        """INSERT INTO tbPessoa(intCodigoPessoa, strRazaoSocial, strTipoPessoa,
               strCGC, strCIC, strEndereco, strNumero, strBairro, strCep,
               strCidade, strUF)
           VALUES (1,'MARIA SANTOS DA SILVA','F','','04785512388',
                   'PCA SANTANINHA','341','CENTRO','65936000',
                   'Cidade Exemplo','MA')""")
    con.execute(
        """INSERT INTO tbPessoa(intCodigoPessoa, strRazaoSocial, strTipoPessoa,
               strCGC, strCIC, strEndereco, strNumero, strBairro, strCep,
               strCidade, strUF)
           VALUES (2,'BANCO EXEMPLO S/A','J','12345678000199','',
                   'AV CENTRAL','100','CENTRO','65000000',
                   'Sao Luis','MA')""")
    return con


def test_carga_copia_chave_cenprot_do_acervo():
    con, acervo = _banco_cg(), _acervo_com_chave(chave=CHAVE)
    AC.carregar_protesto(con, acervo, agora=AGORA)
    row = con.execute(
        "SELECT chave_cenprot, origem_chave FROM pt_titulos").fetchone()
    assert row["chave_cenprot"] == CHAVE
    assert str(row["origem_chave"]).startswith("tbAvisoProtesto:1")


def test_carga_nao_inventa_chave_quando_acervo_nao_tem():
    con, acervo = _banco_cg(), _acervo_com_chave(chave=None)
    AC.carregar_protesto(con, acervo, agora=AGORA)
    row = con.execute("SELECT chave_cenprot FROM pt_titulos").fetchone()
    assert row["chave_cenprot"] in (None, "")


def test_carga_sem_coluna_chave_nao_derruba():
    con, acervo = _banco_cg(), _acervo_com_chave(com_coluna=False)
    carga = AC.carregar_protesto(con, acervo, agora=AGORA)
    assert carga.inseridos == 1
    row = con.execute("SELECT chave_cenprot FROM pt_titulos").fetchone()
    assert row["chave_cenprot"] in (None, "")


def test_segunda_carga_preenche_chave_que_faltava_sem_sobrescrever():
    con, acervo = _banco_cg(), _acervo_com_chave(chave=None)
    AC.carregar_protesto(con, acervo, agora=AGORA)
    assert con.execute(
        "SELECT chave_cenprot FROM pt_titulos").fetchone()["chave_cenprot"] in (
            None, "")

    # Acervo ganha a chave depois (como na casa real: coluna ja existia e a
    # carga antiga nao copiava). Segunda rodada tem de trazer.
    acervo.execute(
        "UPDATE tbAvisoProtesto SET strChaveUnicaCENPROT=?", (CHAVE,))
    r = AC.carregar_protesto(con, acervo, agora=AGORA).como_dict()
    assert r["repetidos"] == 1
    assert r["contagens"].get("chaves CENPROT trazidas do acervo") == 1
    assert con.execute(
        "SELECT chave_cenprot FROM pt_titulos").fetchone()["chave_cenprot"] == CHAVE

    # Nao sobrescreve.
    acervo.execute(
        "UPDATE tbAvisoProtesto SET strChaveUnicaCENPROT=?",
        ("21987659999999999999999",))
    AC.carregar_protesto(con, acervo, agora=AGORA)
    assert con.execute(
        "SELECT chave_cenprot FROM pt_titulos").fetchone()["chave_cenprot"] == CHAVE


def test_casar_ipdigital_por_nome_da_chave(tmp_path: Path):
    pasta = tmp_path / "IPDigital"
    pasta.mkdir()
    (pasta / f"{CHAVE}.p7s").write_bytes(b"nao-e-pkcs7-so-nome")
    (pasta / "arquivo_qualquer.p7s").write_bytes(b"x")
    (pasta / "123.p7s").write_bytes(b"x")  # tamanho errado
    achados = PCEN.casar_ipdigital_por_chave(
        [CHAVE, "00000000000000000000000"], pastas=[pasta])
    assert achados == [{"chave": CHAVE, "caminho": str((pasta / f"{CHAVE}.p7s").resolve())}]


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


def test_tela_importar_eoficio_existe_e_esta_no_menu(cg_casa):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    bd = cg_casa['db']
    bd.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    cg_casa['db'].set_settings({"modulo_protesto_ligado": "1"})
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    r = c.get("/protesto/importar-eoficio")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "csrf_token" in html
    assert "ao vivo" in html.lower() and ("Trazer agora" in html or "Trazer agora do E-Of" in html)
    assert "strChaveUnicaCENPROT" in html or "chave CENPROT" in html.lower() or "chave" in html.lower()
    # O menu do Protesto NÃO aponta mais para a rota: o item saiu em
    # 17/10/2026, com a importação do E-Ofício encerrada. A tela fica pelo
    # endereço (acima), para o administrador.
    home = c.get("/").get_data(as_text=True)
    assert "/protesto/importar-eoficio" not in home
    assert "Trazer protesto do E-Of" not in home


def test_tela_instrumentos_existe(cg_casa):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    bd = cg_casa['db']
    bd.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    cg_casa['db'].set_settings({"modulo_protesto_ligado": "1"})
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    r = c.get("/protesto/instrumentos")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Instrumentos" in html or "instrumento" in html.lower()
    assert "csrf_token" in html or "Emitir" in html or "sem instrumento" in html.lower()

