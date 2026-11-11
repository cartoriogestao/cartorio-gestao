"""A tela de lançar registro de acervo no RCPJ/RTD.

Confere o que o domínio não vê: quem entra, o anexo, a ficha, a listagem,
a auditoria, e que /rcpj-rtd/novo continua gastando número e pedindo selo.

Nomes e CNPJ são fictícios.
"""
from __future__ import annotations

import sqlite3
import sys
from io import BytesIO
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from tests.conftest import cg_login  # noqa: E402

PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
       b"trailer<</Root 1 0 R>>\n%%EOF\n")
SENHA = "Senha#12345"
CNPJ = "00.000.000/0001-91"


def _token(html: str) -> str:
    import re
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _entrar(casa, papel: str):
    casa["db"].create_user("balcao", "ESCREVENTE DE EXEMPLO", SENHA, papel)
    cg_login(casa["c"], "balcao", SENHA)
    return casa


def _con(casa) -> sqlite3.Connection:
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _formulario(**extra) -> dict:
    dados = {
        "serie": "PJ_A", "volume": "5", "numero_ordem": "342",
        "folha_inicial": "25V", "folha_final": "30",
        "data_registro": "2021-03-15", "protocolo": "2021.05.88",
        "natureza": "Estatuto de associação",
        "requerente_nome": "SINDICATO DE EXEMPLO DE CIDADE EXEMPLO",
        "requerente_documento": CNPJ,
        "teor": "Resumo de exemplo do estatuto, sem pessoa real.",
        "selos_antigos": "SELO-ANTIGO-EXEMPLO-2021",
        "lista_presenca_livro": "",
    }
    dados.update(extra)
    return dados


def _postar(casa, **extra):
    html = casa["c"].get("/rcpj-rtd/acervo").get_data(as_text=True)
    dados = _formulario(**extra)
    dados["csrf_token"] = _token(html)
    dados["arquivo"] = (BytesIO(PDF), "estatuto-exemplo.pdf")
    return casa["c"].post(
        "/rcpj-rtd/acervo", data=dados, content_type="multipart/form-data",
        follow_redirects=True)


def test_a_lista_oferece_o_lancamento_e_a_tela_explica_o_que_nao_faz(cg_casa):
    _entrar(cg_casa, "USER")
    lista = cg_casa["c"].get("/rcpj-rtd").get_data(as_text=True)
    assert 'href="/rcpj-rtd/acervo"' in lista
    html = cg_casa["c"].get("/rcpj-rtd/acervo").get_data(as_text=True)
    assert "Lançar registro de acervo" in html
    assert 'name="numero_ordem"' in html
    assert 'name="folha_inicial"' in html
    assert 'name="protocolo"' in html
    assert 'name="selos_antigos"' in html
    assert 'name="lista_presenca_livro"' in html
    assert 'name="arquivo"' in html
    assert "enquadramento_cnma" not in html
    assert "Selo e cobrança" not in html
    novo = cg_casa["c"].get("/rcpj-rtd/novo").get_data(as_text=True)
    assert 'name="selo"' in novo
    assert "Selo e cobrança" in novo
    assert 'name="volume"' not in novo


def test_user_lanca_anexa_e_a_auditoria_diz_quem_foi(cg_casa):
    _entrar(cg_casa, "USER")
    con = _con(cg_casa)
    lugares = con.execute("SELECT COUNT(*) n FROM nu_lugares").fetchone()["n"]
    numeracao = con.execute("SELECT COUNT(*) n FROM nu_numeracao").fetchone()["n"]
    selos = con.execute("SELECT COUNT(*) n FROM sd_selos").fetchone()["n"]
    con.close()
    resp = _postar(cg_casa)
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Registro de acervo lançado no Livro A-5" in html
    assert "não emitiu selo" in html.lower() or "Não emitiu selo" in html
    assert "estatuto-exemplo.pdf" in html
    assert ">ACERVO<" in html or "<strong>ACERVO</strong>" in html
    assert "fls. 25V a 30" in html
    assert "SELO-ANTIGO-EXEMPLO-2021" in html
    assert "2021.05.88" in html
    con = _con(cg_casa)
    reg = con.execute(
        "SELECT * FROM rg_registros WHERE numero=342").fetchone()
    assert reg["origem"] == "ACERVO"
    assert reg["criado_por"] == "ESCREVENTE DE EXEMPLO"
    ato = con.execute(
        "SELECT * FROM rg_atos WHERE registro_id=?", (reg["id"],)).fetchone()
    assert ato["selo"] in (None, "")
    assert ato["livro_id"] is None
    assert con.execute("SELECT COUNT(*) n FROM nu_lugares").fetchone()["n"] == lugares
    assert con.execute("SELECT COUNT(*) n FROM nu_numeracao").fetchone()["n"] == numeracao
    assert con.execute("SELECT COUNT(*) n FROM sd_selos").fetchone()["n"] == selos
    anexo = con.execute(
        """SELECT original_name FROM attachments
            WHERE entity_type='RG_REGISTRO' AND entity_id=?""",
        (reg["id"],)).fetchone()
    assert anexo["original_name"] == "estatuto-exemplo.pdf"
    aud = con.execute(
        """SELECT username_snapshot, action FROM audit_logs
            WHERE action='RG_REGISTRO_ACERVO' ORDER BY id DESC LIMIT 1"""
    ).fetchone()
    assert aud["username_snapshot"] == "balcao"
    lista = cg_casa["c"].get("/rcpj-rtd").get_data(as_text=True)
    assert "ACERVO" in lista
    assert "SINDICATO DE EXEMPLO DE CIDADE EXEMPLO" in lista
    con.close()


def test_a_duplicidade_avisa_e_nao_grava_de_novo(cg_casa):
    _entrar(cg_casa, "MANAGER")
    assert _postar(cg_casa).status_code == 200
    html = _postar(cg_casa, volume="05").get_data(as_text=True)
    assert "Já existe o nº 342 no Livro A-5" in html
    assert "Nada foi lançado" in html
    con = _con(cg_casa)
    assert con.execute(
        "SELECT COUNT(*) n FROM rg_registros WHERE numero=342").fetchone()["n"] == 1
    con.close()


def test_sem_pdf_nao_lanca(cg_casa):
    _entrar(cg_casa, "ADMIN")
    html = cg_casa["c"].get("/rcpj-rtd/acervo").get_data(as_text=True)
    dados = _formulario()
    dados["csrf_token"] = _token(html)
    resp = cg_casa["c"].post(
        "/rcpj-rtd/acervo", data=dados, follow_redirects=True)
    assert "Nada foi lançado" in resp.get_data(as_text=True)
    con = _con(cg_casa)
    assert con.execute("SELECT COUNT(*) n FROM rg_registros").fetchone()["n"] == 0
    con.close()


@pytest.mark.parametrize("papel", ["USER", "MANAGER", "ADMIN"])
def test_quem_trabalha_no_rcpj_abre_a_tela(cg_casa, papel):
    _entrar(cg_casa, papel)
    assert cg_casa["c"].get("/rcpj-rtd/acervo").status_code == 200


def test_auditor_e_anonimo_nao_lancam(cg_casa):
    cg_casa["db"].create_user("balcao", "ESCREVENTE DE EXEMPLO", SENHA, "USER")
    anon = cg_casa["app"].test_client()
    resp = anon.get("/rcpj-rtd/acervo")
    assert resp.status_code in (302, 303)
    assert "/login" in (resp.headers.get("Location") or "")
    cg_casa["db"].create_user("auditor", "AUDITOR DE EXEMPLO", SENHA, "AUDITOR")
    cg_login(cg_casa["c"], "auditor", SENHA)
    assert cg_casa["c"].get("/rcpj-rtd/acervo").status_code == 403
    token = _token(cg_casa["c"].get("/rcpj-rtd").get_data(as_text=True))
    recusa = cg_casa["c"].post(
        "/rcpj-rtd/acervo", data={"csrf_token": token, "serie": "PJ_A"})
    assert recusa.status_code == 403


def test_registro_novo_continua_gastando_numero_e_pedindo_selo(cg_casa):
    """O acervo não muda /rcpj-rtd/novo: o ato de hoje ainda numera e sela.

    A trava do caixa fica desligada aqui, como nos testes das telas de
    atribuição: o que se mede é o caminho do ato novo, não a trava.
    """
    from navegador_de_teste import postar_e_seguir

    _entrar(cg_casa, "ADMIN")
    cg_casa["db"].set_settings({"selo_trava_caixa": "DESLIGADA"})
    _postar(cg_casa)
    con = _con(cg_casa)
    antes = con.execute("SELECT COUNT(*) n FROM nu_lugares").fetchone()["n"]
    con.close()
    c = cg_casa["c"]
    token = _token(c.get("/rcpj-rtd/novo").get_data(as_text=True))
    html = postar_e_seguir(c, "/rcpj-rtd/novo", {
        "csrf_token": token, "serie": "TD_B",
        "natureza": "Contrato de locação de exemplo",
        "requerente_nome": "EMPRESA DE EXEMPLO LTDA",
        "selo": "AVESVD000000NARRKWVNJCRSVO21",
    }).get_data(as_text=True)
    assert "Assim vai sair na tira" in html or "Registro aberto" in html
    con = _con(cg_casa)
    novo = con.execute(
        """SELECT * FROM rg_registros WHERE origem='MANUAL'
            ORDER BY id DESC LIMIT 1""").fetchone()
    assert novo is not None
    assert novo["serie"] == "TD_B"
    assert novo["atribuicao"] == 4
    assert novo["numero"] == 1
    ato = con.execute(
        "SELECT * FROM rg_atos WHERE registro_id=?", (novo["id"],)).fetchone()
    assert ato["livro_id"] is not None
    assert ato["numero_ordem"] == 1
    assert ato["selo"] == "AVESVD000000NARRKWVNJCRSVO21"
    assert con.execute("SELECT COUNT(*) n FROM nu_lugares").fetchone()["n"] == antes + 1
    acervo = con.execute(
        """SELECT r.numero, r.origem, a.livro_id, a.numero_ordem
             FROM rg_registros r JOIN rg_atos a ON a.registro_id=r.id
            WHERE r.numero=342 AND a.tipo='REGISTRO'""").fetchone()
    assert acervo["origem"] == "ACERVO"
    assert acervo["livro_id"] is None
    assert acervo["numero_ordem"] == 342
    con.close()
