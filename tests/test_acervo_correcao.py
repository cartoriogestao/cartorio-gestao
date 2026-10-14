"""Corrigir dado do acervo importado — pedido do oficial em 08/09/2026.

    «quero poder editar tambem os dados dos registros e atos em geral»,
    esclarecido a seguir: «corrigir dado do acervo importado (antes deste
    sistema)».

O QUE ESTE ARQUIVO PROTEGE
    Que só os campos de dado simples (nome, endereço, RG...) sejam
    corrigíveis, nunca numeração/livro/folha/selo/situação/hash; que só a
    linha marcada como vinda do acervo (`origem='EOFICIO'`) seja alcançada —
    ato lavrado por este sistema tem de continuar seguindo o caminho da
    averbação/retificação; e que a correção sempre venha com motivo e fique
    na auditoria.
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

import acervo_correcao as AC                                     # noqa: E402

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    c = cg_casa["c"]
    cg_casa["db"].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login", data={"username": "tabeliao", "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _matricula(banco, numero="4009", origem="EOFICIO", cidade="Imperatriz"):
    con = sqlite3.connect(banco)
    con.execute(
        """INSERT INTO ri_matriculas (numero, cidade, origem, criado_em)
           VALUES (?,?,?,'2026-08-13T10:00:00')""",
        (numero, cidade, origem))
    mid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    con.commit()
    con.close()
    return mid


def _cartao(banco, nome="MARIA DA SILVA", origem="EOFICIO"):
    con = sqlite3.connect(banco)
    con.execute(
        """INSERT INTO nt_cartoes (nome, origem, criado_em)
           VALUES (?,?,'2026-08-13T10:00:00')""",
        (nome, origem))
    cid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    con.commit()
    con.close()
    return cid


# ------------------------------------------------------------ o domínio

def test_buscar_so_acha_linha_do_acervo(casa):
    _matricula(casa["banco"], numero="4009", origem="EOFICIO", cidade="Imperatriz")
    _matricula(casa["banco"], numero="4010", origem="MANUAL", cidade="Imperatriz")
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    achados = AC.buscar(con, "ri_matriculas", "400")
    con.close()
    assert {a["numero"] for a in achados} == {"4009"}


def test_obter_recusa_linha_que_nao_e_do_acervo(casa):
    mid = _matricula(casa["banco"], origem="MANUAL")
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    with pytest.raises(AC.CorrecaoError, match="não é do acervo"):
        AC.obter(con, "ri_matriculas", mid)
    con.close()


def test_corrigir_muda_o_campo_liberado(casa):
    mid = _matricula(casa["banco"], cidade="Imperatriz")
    with sqlite3.connect(casa["banco"]) as con:
        con.row_factory = sqlite3.Row
        resultado = AC.corrigir(con, "ri_matriculas", mid,
                               {"cidade": "Cidade Exemplo"},
                               "cidade errada na carga do acervo")
        con.commit()
    assert resultado["mudancas"]["cidade"]["antes"] == "Imperatriz"
    assert resultado["mudancas"]["cidade"]["depois"] == "Cidade Exemplo"
    con = sqlite3.connect(casa["banco"])
    assert con.execute("SELECT cidade FROM ri_matriculas WHERE id=?",
                       (mid,)).fetchone()[0] == "Cidade Exemplo"


def test_CORRIGIR_RECUSA_CAMPO_NAO_LIBERADO(casa):
    """A guarda de verdade: numeração, livro, folha, selo, situação, hash
    nunca passam por aqui, nem se o formulário mandar o nome certo."""
    mid = _matricula(casa["banco"])
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    for campo in ("numero", "situacao", "conferido", "origem"):
        with pytest.raises(AC.CorrecaoError, match="não pode ser corrigido"):
            AC.corrigir(con, "ri_matriculas", mid, {campo: "999"}, "motivo qualquer")
    con.close()


def test_corrigir_recusa_linha_que_nao_e_do_acervo(casa):
    mid = _matricula(casa["banco"], origem="MANUAL")
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    with pytest.raises(AC.CorrecaoError, match="não é do acervo"):
        AC.corrigir(con, "ri_matriculas", mid, {"cidade": "X"}, "motivo")
    con.close()


def test_corrigir_exige_motivo(casa):
    mid = _matricula(casa["banco"])
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    with pytest.raises(AC.CorrecaoError, match="motivo"):
        AC.corrigir(con, "ri_matriculas", mid, {"cidade": "Cidade Exemplo"}, "")
    con.close()


def test_corrigir_recusa_se_nada_mudou(casa):
    mid = _matricula(casa["banco"], cidade="Imperatriz")
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    with pytest.raises(AC.CorrecaoError, match="Nenhum campo mudou"):
        AC.corrigir(con, "ri_matriculas", mid, {"cidade": "Imperatriz"}, "motivo")
    con.close()


def test_tabela_desconhecida_e_recusada(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    with pytest.raises(AC.CorrecaoError, match="Tabela não reconhecida"):
        AC.buscar(con, "users", "tabeliao")
    con.close()


def test_pt_titulos_nao_esta_na_lista_de_tabelas():
    """Protesto fica de fora — a carga do acervo marca os títulos com
    origem CRA/CENPROT, o mesmo valor de título recebido normalmente pela
    Central, sem como distinguir um do outro só pelo `origem`."""
    assert "pt_titulos" not in AC.TABELAS


# --------------------------------------------------------------- a tela

def test_a_tela_lista_so_o_que_e_do_acervo(casa):
    _matricula(casa["banco"], numero="4009", origem="EOFICIO")
    _matricula(casa["banco"], numero="4010", origem="MANUAL")
    html = casa["c"].get(
        "/administrativo/acervo/corrigir?tabela=ri_matriculas&termo=4"
    ).get_data(as_text=True)
    assert "4009" in html
    assert "4010" not in html


def test_a_tela_de_edicao_mostra_o_valor_atual(casa):
    mid = _matricula(casa["banco"], cidade="Imperatriz")
    html = casa["c"].get(
        f"/administrativo/acervo/corrigir?tabela=ri_matriculas&id={mid}"
    ).get_data(as_text=True)
    assert 'value="Imperatriz"' in html
    assert "Motivo da correção" in html


def test_SALVAR_PELA_TELA_CORRIGE_E_AUDITA(casa):
    mid = _matricula(casa["banco"], cidade="Imperatriz")
    html = casa["c"].get(
        f"/administrativo/acervo/corrigir?tabela=ri_matriculas&id={mid}"
    ).get_data(as_text=True)
    r = casa["c"].post("/administrativo/acervo/corrigir", data={
        "csrf_token": _token(html), "acao": "salvar",
        "tabela": "ri_matriculas", "id": str(mid),
        "campo_cidade": "Cidade Exemplo",
        "motivo": "cidade errada na carga do acervo"},
        follow_redirects=True)
    assert "Corrigido" in r.get_data(as_text=True)

    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    assert con.execute("SELECT cidade FROM ri_matriculas WHERE id=?",
                       (mid,)).fetchone()["cidade"] == "Cidade Exemplo"
    auditoria = con.execute(
        "SELECT * FROM audit_logs WHERE action='ACERVO_CORRIGIDO' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    assert auditoria is not None
    assert "Cidade Exemplo" in auditoria["details"]
    assert "cidade errada na carga do acervo" in auditoria["details"]


def test_A_TELA_RECUSA_SALVAR_EM_LINHA_QUE_NAO_E_DO_ACERVO(casa):
    mid = _matricula(casa["banco"], origem="MANUAL", cidade="Imperatriz")
    html = casa["c"].get("/administrativo/acervo/corrigir").get_data(as_text=True)
    r = casa["c"].post("/administrativo/acervo/corrigir", data={
        "csrf_token": _token(html), "acao": "salvar", "tabela": "ri_matriculas",
        "id": str(mid), "campo_cidade": "Cidade Exemplo",
        "motivo": "tentativa"}, follow_redirects=True)
    assert "não é do acervo" in r.get_data(as_text=True)
    con = sqlite3.connect(casa["banco"])
    assert con.execute("SELECT cidade FROM ri_matriculas WHERE id=?",
                       (mid,)).fetchone()[0] == "Imperatriz"


def test_a_tela_funciona_para_ficha_de_firma_tambem(casa):
    cid = _cartao(casa["banco"], nome="MARIA DA SILVA")
    html = casa["c"].get(
        f"/administrativo/acervo/corrigir?tabela=nt_cartoes&id={cid}"
    ).get_data(as_text=True)
    r = casa["c"].post("/administrativo/acervo/corrigir", data={
        "csrf_token": _token(html), "acao": "salvar",
        "tabela": "nt_cartoes", "id": str(cid),
        "campo_nome": "MARIA DA SILVA SOUSA",
        "motivo": "sobrenome faltando na carga"}, follow_redirects=True)
    assert "Corrigido" in r.get_data(as_text=True)
    con = sqlite3.connect(casa["banco"])
    assert con.execute("SELECT nome FROM nt_cartoes WHERE id=?",
                       (cid,)).fetchone()[0] == "MARIA DA SILVA SOUSA"


def test_a_tela_so_e_do_administrador(casa):
    from database import Database
    Database(casa["banco"]).create_user("escrevente", "MARIA", SENHA, "USER")
    c2 = casa["app"].test_client()
    c2.post("/login", data={"username": "escrevente", "password": SENHA,
                            "csrf_token": _token(c2.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    r = c2.get("/administrativo/acervo/corrigir")
    assert r.status_code == 403
