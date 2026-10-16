"""A CERTIDÃO DAS NOTAS — pedido do oficial, 15/10/2026.

    «precisa emitir certidão do notas, com selo e etc, inclusive busca quando
     não disser o ato»

O PRECEDENTE (acervo do E-Ofício, só leitura): 10 selos de certidão das
Notas em 7 protocolos de 2023–2024, todos por `/selo/notas/atos-em-geral`
(`AtosEmGeral`): `13.12.1` × 1 em 6, `13.12.3` com a quantidade = folhas a
mais (1, 1 e 6) em selo PRÓPRIO, `13.12.4` × 1 uma vez. Nenhum selo de busca
13.13 e nenhum texto de certidão guardado.

O QUE ESTES TESTES GUARDAM
    - o domínio: ato identificado → inteiro teor com a margem; busca pela
      parte → positiva ou negativa, e o tipo sai do que se achou;
    - número por exercício, teor congelado e sha256;
    - o selo na forma medida, a folha acrescida em selo próprio, a eletrônica
      sozinha, e a busca 13.13 por último — com o «.9» marcado na tela quando
      o ato foi identificado;
    - a certidão registrada como tabela de ato (sem isso, ela some);
    - a tela no menu, o PDF/odt com o carimbo, e o cancelamento.

Nada fala com o aparelho: `selar_o_ato_lavrado` é um gravador.
"""
from __future__ import annotations

import re
import sqlite3
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ato_selado as AS                                         # noqa: E402
import notas_certidao as NCE                                    # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-10-15T10:00:00"


# ------------------------------------------------------------- o domínio


def test_a_certidao_e_tabela_de_ato():
    assert "nt_certidoes" in AS.TABELAS_DE_ATO
    assert AS.COLUNA_DO_SELO["nt_certidoes"] == "selo"


def test_os_itens_na_forma_medida():
    assert NCE.itens_do_selo(1) == [("13.12.1", 1)]
    assert NCE.itens_do_selo(7) == [("13.12.1", 1), ("13.12.3", 6)]
    assert NCE.itens_do_selo(3, eletronica=True) == [("13.12.4", 1)]


def test_o_envelope_e_o_atos_em_geral_medido():
    env = NCE.envelope(codigo="13.12.1", quantidade=1,
                       escrevente="Mario Santos", versao_tabela="0520260101",
                       parte={"nome": "FULANA DE TAL",
                              "documento": "000.000.001-91"})
    assert env == {"ato": {"codigo": "13.12.1",
                           "codigoTabelaCusta": "0520260101"},
                   "escrevente": "Mario Santos",
                   "partes": {"nomePartes": [],
                              "parteAto": [{"documento": "00000000191",
                                            "nome": "FULANA DE TAL"}]},
                   "quantidade": 1}
    isento = NCE.envelope(codigo="13.12.1", quantidade=1, escrevente="M",
                          versao_tabela="0520260101", parte={"nome": "X"},
                          isento=True, motivo_isencao="hipossuficiência")
    assert isento["isento"] == {"value": True, "motivo": "HIPOSSUFICIÊNCIA"}


@pytest.fixture()
def s(cg_casa):
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA,
                              "ADMIN")
    cg_casa["db"].set_settings({"selo_tabela_custas_em": "20260101"})
    c = cg_casa["app"].test_client()
    tela = c.get("/login").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', tela).group(1)
    c.post("/login", data={"username": "mario", "password": SENHA,
                           "csrf_token": token}, follow_redirects=True)
    return {"c": c, "banco": cg_casa["banco"]}


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def _ato(s, *, situacao="LAVRADO", teor="<p>OUTORGANTE: JOSÉ DA SILVA ...</p>",
         data="2015-03-10") -> int:
    con = _con(s)
    with con:
        cur = con.execute(
            """INSERT INTO nt_atos(tipo, livro, folha, data, situacao, teor,
                   natureza, criado_em)
               VALUES ('ESCRITURA','12','30',?,?,?,'COMPRA E VENDA',?)""",
            (data, situacao, teor, AGORA))
        aid = int(cur.lastrowid)
        for nome, doc, testemunha in (("JOSÉ DA SILVA", "00000000191", 0),
                                      ("BELTRANO TESTEMUNHA", "00000000272", 1)):
            con.execute(
                """INSERT INTO nt_ato_partes(ato_id, nome, documento,
                       qualificacao, testemunha, criado_em)
                   VALUES (?,?,?,'OUTORGANTE VENDEDOR',?,?)""",
                (aid, nome, doc, testemunha, AGORA))
    con.close()
    return aid


def test_inteiro_teor_reproduz_o_livro_e_a_margem(s):
    aid = _ato(s)
    con = _con(s)
    with con:
        r = NCE.emitir(con, hoje="2026-10-15", agora=AGORA, ato_id=aid,
                       requerente="FULANA", usuario="MARIO")
    linha = NCE.certidao(con, r["certidao_id"])
    con.close()
    assert r["tipo"] == "INTEIRO_TEOR" and r["numero"] == 1
    assert "Livro 12, folha 30" in linha["teor"]
    assert "OUTORGANTE: JOSÉ DA SILVA" in linha["teor"]
    assert "Nada mais consta à margem" in linha["teor"]
    assert len(linha["hash_certidao"]) == 64


def test_ato_em_lavratura_nao_se_certifica(s):
    aid = _ato(s, situacao="EM_LAVRATURA")
    con = _con(s)
    with pytest.raises(NCE.CertidaoNotasError, match="não foi lançado"):
        NCE.emitir(con, hoje="2026-10-15", agora=AGORA, ato_id=aid)
    con.close()


def test_a_busca_acha_pela_parte_e_nao_pela_testemunha(s):
    _ato(s)
    con = _con(s)
    assert len(NCE.buscar(con, nome="jose da silva")) == 1
    assert len(NCE.buscar(con, documento="000.000.001-91")) == 1
    assert NCE.buscar(con, nome="BELTRANO TESTEMUNHA") == []
    assert NCE.buscar(con, nome="JOSÉ DA SILVA",
                      periodo_de="2016-01-01") == []
    con.close()


def test_o_tipo_sai_do_que_a_busca_achou(s):
    _ato(s)
    con = _con(s)
    with con:
        with pytest.raises(NCE.CertidaoNotasError, match="Não se emite"):
            NCE.emitir(con, hoje="2026-10-15", agora=AGORA,
                       nome="JOSÉ DA SILVA", tipo="NEGATIVA")
        pos = NCE.emitir(con, hoje="2026-10-15", agora=AGORA,
                         nome="JOSÉ DA SILVA")
        neg = NCE.emitir(con, hoje="2026-10-15", agora=AGORA,
                         nome="NINGUÉM DE TAL")
    assert pos["tipo"] == "POSITIVA" and neg["tipo"] == "NEGATIVA"
    assert neg["numero"] == pos["numero"] + 1
    teor = NCE.certidao(con, neg["certidao_id"])["teor"]
    con.close()
    assert "NADA CONSTA" in teor


# ------------------------------------------------------------- as rotas


@pytest.fixture()
def gravador(monkeypatch):
    import certidao_folhas as CF
    monkeypatch.setattr(CF, "decidir_folhas_antes_de_emitir",
                        lambda **k: k.get("folhas_informadas") or 1)
    chamadas: list[dict] = []

    def _selar(*a, **k):
        chamadas.append(k)
        n = f"CERTID0296370TESTE{len(chamadas):06d}"
        return {"selado": True, "numero": n, "numeros": [n], "motivo": None}
    monkeypatch.setattr(AS, "selar_o_ato_lavrado", _selar)
    return chamadas


def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def test_o_menu_e_a_ficha_levam_a_certidao(s):
    aid = _ato(s)
    menu = s["c"].get("/notas/certidoes").get_data(as_text=True)
    assert 'href="/notas/certidoes"' in menu
    ficha = s["c"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert f"/notas/certidoes?ato_id={aid}" in ficha


def test_a_tela_do_ato_identificado_marca_o_9(s):
    aid = _ato(s)
    html = s["c"].get(f"/notas/certidoes?ato_id={aid}").get_data(as_text=True)
    assert re.search(r'<option value="13\.13\.9"\s+selected>', html)
    assert "ato indicado pelo livro 12, folha 30" in html


def test_a_busca_por_nome_sugere_a_faixa_pelo_periodo(s):
    _ato(s)
    html = s["c"].get("/notas/certidoes?nome=JOSE+DA+SILVA&de=2014-01-01"
                      ).get_data(as_text=True)
    assert "13.13" in html and 'name="busca_item"' in html
    assert not re.search(r'<option value="13\.13\.9"\s+selected>', html)


def test_emitir_do_ato_sela_pelo_caminho_medido(s, gravador):
    aid = _ato(s)
    tela = s["c"].get(f"/notas/certidoes?ato_id={aid}").get_data(as_text=True)
    r = s["c"].post("/notas/certidoes/emitir",
                    data={"csrf_token": _token(tela), "ato_id": str(aid),
                          "requerente": "FULANA DE TAL", "folhas": "3",
                          "busca_formulario": "1", "busca_item": "13.13.9"},
                    follow_redirects=True)
    assert "emitida" in r.get_data(as_text=True)
    assert [g["dados"]["ato"]["codigo"] for g in gravador] == [
        "13.12.1", "13.12.3"], "o «.9» não vende selo"
    assert gravador[1]["dados"]["quantidade"] == 2
    assert all(g["caminho"] == "/selo/notas/atos-em-geral" for g in gravador)
    assert all(g["tabela"] == "nt_certidoes" for g in gravador)


def test_a_busca_por_nome_sela_a_13_13_por_ultimo(s, gravador):
    tela = s["c"].get("/notas/certidoes?nome=NINGUEM").get_data(as_text=True)
    s["c"].post("/notas/certidoes/emitir",
                data={"csrf_token": _token(tela), "nome": "NINGUÉM DE TAL",
                      "busca_formulario": "1", "busca_item": "13.13.2"},
                follow_redirects=True)
    assert [g["dados"]["ato"]["codigo"] for g in gravador] == [
        "13.12.1", "13.13.2"]
    con = _con(s)
    linha = con.execute("SELECT tipo, busca_item, cancelada FROM nt_certidoes"
                        ).fetchone()
    con.close()
    assert (linha["tipo"], linha["busca_item"], linha["cancelada"]) == (
        "NEGATIVA", "13.13.2", 0)


def test_a_eletronica_nao_ganha_busca_nem_folha(s, gravador):
    tela = s["c"].get("/notas/certidoes?nome=NINGUEM").get_data(as_text=True)
    s["c"].post("/notas/certidoes/emitir",
                data={"csrf_token": _token(tela), "nome": "NINGUÉM DE TAL",
                      "eletronica": "1", "folhas": "4",
                      "busca_formulario": "1", "busca_item": "13.13.2"},
                follow_redirects=True)
    assert [g["dados"]["ato"]["codigo"] for g in gravador] == ["13.12.4"]


def test_a_busca_sem_escolha_recusa_antes_de_numerar(s, gravador):
    tela = s["c"].get("/notas/certidoes?nome=NINGUEM").get_data(as_text=True)
    r = s["c"].post("/notas/certidoes/emitir",
                    data={"csrf_token": _token(tela), "nome": "NINGUÉM",
                          "busca_formulario": "1", "busca_item": ""},
                    follow_redirects=True)
    assert "Escolha o item da busca" in r.get_data(as_text=True)
    con = _con(s)
    assert con.execute("SELECT COUNT(*) FROM nt_certidoes").fetchone()[0] == 0
    con.close()
    assert gravador == []


def test_selo_que_nao_sai_cancela_a_certidao(s, monkeypatch):
    import certidao_folhas as CF
    monkeypatch.setattr(CF, "decidir_folhas_antes_de_emitir", lambda **k: 1)
    monkeypatch.setattr(AS, "selar_o_ato_lavrado",
                        lambda *a, **k: {"selado": False,
                                         "motivo": "aparelho fora do ar"})
    tela = s["c"].get("/notas/certidoes?nome=NINGUEM").get_data(as_text=True)
    r = s["c"].post("/notas/certidoes/emitir",
                    data={"csrf_token": _token(tela), "nome": "NINGUÉM"},
                    follow_redirects=True)
    assert "NÃO emitida" in r.get_data(as_text=True)
    con = _con(s)
    assert con.execute("SELECT cancelada FROM nt_certidoes").fetchone()[0] == 1
    con.close()


def test_o_papel_leva_o_carimbo_dos_selos(s, gravador):
    aid = _ato(s)
    tela = s["c"].get(f"/notas/certidoes?ato_id={aid}").get_data(as_text=True)
    s["c"].post("/notas/certidoes/emitir",
                data={"csrf_token": _token(tela), "ato_id": str(aid)},
                follow_redirects=True)
    con = _con(s)
    cid = con.execute("SELECT id FROM nt_certidoes").fetchone()[0]
    with con:
        con.execute(
            """INSERT INTO sd_selos (numero, texto, caminho, atribuicao,
                   referencia, tabela, ato_id, obtido_em, usado_em)
               VALUES ('CERTID000000XXXXXXXXXXXX0001', ?, ?, 'NOTAS', ?,
                       'nt_certidoes', ?, ?, ?)""",
            ("Poder Judiciário – TJMA. Selo: CERTID000000XXXXXXXXXXXX0001, "
             "15/10/2026 10:00:00, Ato: 13.12.1, Parte(s): FULANA, Total R$ "
             "48,61 Emol R$ 43,80 FERC R$ 1,31 FADEP R$ 1,75 FEMP R$ 1,75 "
             "Consulte em https://selo.tjma.jus.br",
             "/selo/notas/atos-em-geral", f"nt_certidoes:{cid}", cid, AGORA,
             AGORA))
    con.close()
    dados = s["c"].get(f"/notas/certidoes/{cid}/odt?formato=odt").data
    xml = zipfile.ZipFile(BytesIO(dados)).read("content.xml").decode("utf-8")
    texto = " ".join(re.sub(r"<[^>]+>", " ", xml).split())
    assert "CERTID000000XXXXXXXXXXXX0001" in texto
    assert "Total R$ 48,61" in texto


def test_cancelar_com_selo_exige_a_declaracao(s, gravador):
    tela = s["c"].get("/notas/certidoes?nome=NINGUEM").get_data(as_text=True)
    s["c"].post("/notas/certidoes/emitir",
                data={"csrf_token": _token(tela), "nome": "NINGUÉM"},
                follow_redirects=True)
    con = _con(s)
    cid = con.execute("SELECT id FROM nt_certidoes").fetchone()[0]
    with con:
        # o gravador não amarra o selo; aqui ele fica amarrado à mão
        con.execute("UPDATE nt_certidoes SET selo='CERTID0296370TESTE000001'"
                    " WHERE id=?", (cid,))
    con.close()
    s["c"].post(f"/notas/certidoes/{cid}/cancelar",
                data={"csrf_token": _token(tela),
                      "motivo": "emitida com o nome errado"},
                follow_redirects=True)
    con = _con(s)
    assert con.execute("SELECT cancelada FROM nt_certidoes").fetchone()[0] == 0
    con.close()
    s["c"].post(f"/notas/certidoes/{cid}/cancelar",
                data={"csrf_token": _token(tela),
                      "motivo": "emitida com o nome errado",
                      "selo_cancelado_tjma": "1"},
                follow_redirects=True)
    con = _con(s)
    assert con.execute("SELECT cancelada FROM nt_certidoes").fetchone()[0] == 1
    con.close()
