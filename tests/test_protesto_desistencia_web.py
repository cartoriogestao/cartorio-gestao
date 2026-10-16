"""
Testes das TELAS da desistencia — o passo dos tres turnos.

POR QUE ELES EXISTEM SEPARADOS DOS DE DOMINIO
    Buraco de tela nao aparece em teste de dominio. Foi assim com o devedor,
    com o apontamento, com a numeracao, com a remessa e com o aviso.

    Estes conferem o caminho do balcao: o arquivo sobe pelo formulario, a
    conferencia mostra titulo a titulo o que a casa tem, e so o que foi
    MARCADO entra.
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
EXEMPLO = (Path(__file__).parent / "cra_desistencia_exemplo.txt").read_bytes()
REMESSA = (Path(__file__).parent / "cra_remessa_exemplo.txt").read_bytes()
PROTOCOLO = "2608030003"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _sessao(cg_casa, papel: str = "ADMIN"):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    cg_casa['db'].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                                SENHA, papel)
    # O PROTESTO ESTA DESLIGADO DE FABRICA desde 01/09/2026 — ordem do
    # oficial. Estes testes exercitam as TELAS dele, e por isso o LIGAM
    # aqui, de proposito e a vista: eles provam que o modulo funciona
    # quando ele voltar, que e o que «fica para um futuro» quer dizer.
    cg_casa['db'].set_settings({"modulo_protesto_ligado": "1"})
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco}


@pytest.fixture()
def s(cg_casa):
    return _sessao(cg_casa)


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def titulo_apontado(s, *, protocolo: str = PROTOCOLO) -> int:
    import protesto as PT
    from database import Database

    sv = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
          "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
    db = Database(s["banco"])
    agora = db.now()
    with db.transaction() as con:
        con.row_factory = sqlite3.Row
        tid = PT.cadastrar_titulo(con, {
            "apresentante_codigo": "001", "apresentante_nome": "BANCO DO BRASIL",
            "especie": "DMI", "numero_titulo": "NF-74654-/1",
            "nosso_numero": "N1", "data_emissao": "2026-07-01",
            "data_vencimento": "2026-08-01", "valor": "221.00",
            "saldo": "221.00", "praca_protesto": "CIDADE EXEMPLO",
            "cedente": {"nome": "LOJA", "documento": "00000017000149"},
            "devedores": [{"nome": "M M FERREIRA BEZERRIL MELLO",
                           "CNPJ": "00000017000149",
                           "enderecos": [{"endereco": "RUA GRANDE, 10",
                                          "cidade": "Cidade Exemplo",
                                          "uf": "MA"}]}],
        }, origem="CRA", origem_chave="lote:1", agora=agora)
        PT.lancar_apontamento(con, tid, sv=sv, agora=agora, data_extenso="x")
        con.execute("UPDATE pt_titulos SET protocolo=? WHERE id=?",
                    (protocolo, tid))
    return tid


def conferir(s, conteudo=EXEMPLO, nome="DP0010508.261"):
    tela = s["c"].get("/protesto/desistencias").get_data(as_text=True)
    return s["c"].post(
        "/protesto/desistencias/conferir",
        data={"csrf_token": _token(tela), "arquivo": (BytesIO(conteudo), nome)},
        content_type="multipart/form-data", follow_redirects=True)


def aplicar(s, *, protocolos=(PROTOCOLO,), conteudo=EXEMPLO):
    html = conferir(s, conteudo).get_data(as_text=True)
    achado = re.search(r'name="conteudo" value="([^"]*)"', html)
    assert achado, "a conferência não devolveu o arquivo para o passo seguinte"
    dados = {"csrf_token": _token(html),
             "conteudo": achado.group(1).replace("&#34;", '"')
                                        .replace("&amp;", "&")
                                        .replace("&lt;", "<")
                                        .replace("&gt;", ">"),
             "nome_arquivo": "DP0010508.261",
             "protocolo": list(protocolos)}
    return s["c"].post("/protesto/desistencias/aplicar", data=dados,
                       follow_redirects=True)


# ------------------------------------------------------------- a lista


def test_a_lista_abre_e_diz_o_que_fazer(s):
    html = s["c"].get("/protesto/desistencias").get_data(as_text=True)
    assert "Desistências" in html
    assert "Nenhum arquivo de desistência recebido ainda" in html
    assert "três turnos" in html            # o motivo, e não só a tela


def test_a_desistencia_esta_no_menu(s):
    # A lista mora em `/protesto` desde a 3.6.193 (24/09/2026); o endereço
    # antigo só redireciona, e o redirecionamento não traz menu — 14/10/2026.
    html = s["c"].get("/protesto").get_data(as_text=True)
    assert "/protesto/desistencias" in html


# --------------------------------------------------------- a conferência


def test_a_conferencia_mostra_o_titulo_e_NAO_GRAVA(s):
    titulo_apontado(s)
    html = conferir(s).get_data(as_text=True)
    assert "Nada foi gravado ainda" in html
    assert PROTOCOLO in html
    assert "NF-74654-/1" in html
    con = _con(s)
    assert con.execute(
        "SELECT COUNT(*) c FROM pt_desistencias").fetchone()["c"] == 0
    assert con.execute("SELECT situacao FROM pt_titulos").fetchone()[0] == "APONTADO"


def test_titulo_que_a_casa_nao_tem_aparece_dito(s):
    html = conferir(s).get_data(as_text=True)
    assert "SEM TÍTULO" in html
    assert "sem título nesta casa" in html or "Nenhum título desta casa" in html


def test_arquivo_de_600_avisa_onde_ele_se_abre(s):
    # A própria pasta `desistencia` do Proton Drive guarda um arquivo de 600.
    html = conferir(s, REMESSA).get_data(as_text=True)
    assert "600" in html
    assert "remessa da CRA" in html


def test_sem_escolher_arquivo_avisa_e_volta(s):
    tela = s["c"].get("/protesto/desistencias").get_data(as_text=True)
    html = s["c"].post("/protesto/desistencias/conferir",
                       data={"csrf_token": _token(tela)},
                       content_type="multipart/form-data",
                       follow_redirects=True).get_data(as_text=True)
    assert "Escolha o arquivo" in html


# ------------------------------------------------------------ aplicar


def test_aplicar_desiste_do_titulo_marcado(s):
    tid = titulo_apontado(s)
    html = aplicar(s).get_data(as_text=True)
    assert "Desistência aplicada em 1 título" in html

    con = _con(s)
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] == "DESISTIDO"
    ato = con.execute(
        "SELECT * FROM pt_atos WHERE tipo='DESISTENCIA'").fetchone()
    assert ato["origem"] == "CRA"
    assert "001" in ato["detalhe_json"]


def test_o_que_NAO_foi_marcado_nao_entra(s):
    titulo_apontado(s)
    html = aplicar(s, protocolos=()).get_data(as_text=True)
    assert "Nenhum título foi marcado" in html
    assert _con(s).execute(
        "SELECT situacao FROM pt_titulos").fetchone()[0] == "APONTADO"


def test_a_ficha_do_arquivo_mostra_o_que_foi_desistido(s):
    titulo_apontado(s)
    aplicar(s)
    con = _con(s)
    did = con.execute("SELECT id FROM pt_desistencias").fetchone()["id"]
    html = s["c"].get(f"/protesto/desistencias/{did}").get_data(as_text=True)
    assert "Desistência recebida" in html
    assert "NF-74654-/1" in html
    assert "baixar" in html


def test_o_arquivo_baixa_como_chegou(s):
    titulo_apontado(s)
    aplicar(s)
    did = _con(s).execute("SELECT id FROM pt_desistencias").fetchone()["id"]
    r = s["c"].get(f"/protesto/desistencias/{did}/arquivo")
    assert r.status_code == 200
    assert "ISO-8859-1" in r.headers["Content-Type"]
    assert b"BANCO DO BRASIL" in r.data


def test_aplicar_de_novo_nao_cria_outro_registro(s):
    # O caso do segundo turno: o arquivo volta, e fica gravado uma vez só.
    titulo_apontado(s)
    aplicar(s)
    html = aplicar(s).get_data(as_text=True)
    assert "Desistência aplicada em 0 título" in html
    assert _con(s).execute(
        "SELECT COUNT(*) c FROM pt_desistencias").fetchone()["c"] == 1


def test_arquivo_que_nao_existe_nao_estoura(s):
    assert s["c"].get("/protesto/desistencias/9999").status_code == 404


def test_aplicar_e_de_quem_atende_e_a_lista_e_de_todos(cg_casa):
    s = _sessao(cg_casa, papel="AUDITOR")
    tela = s["c"].get("/protesto/desistencias")
    assert tela.status_code == 200
    r = s["c"].post("/protesto/desistencias/aplicar",
                    data={"csrf_token": _token(tela.get_data(as_text=True)),
                          "conteudo": EXEMPLO.decode("latin-1"),
                          "protocolo": [PROTOCOLO]})
    assert r.status_code in (302, 403)
    assert _con(s).execute(
        "SELECT COUNT(*) c FROM pt_desistencias").fetchone()["c"] == 0
