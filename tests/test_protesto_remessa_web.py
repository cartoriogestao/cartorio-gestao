"""
Testes das TELAS da remessa da CRA — o passo do meio-dia.

POR QUE ELES EXISTEM SEPARADOS DOS DE DOMINIO
    A revisao ato por ato de 25/08/2026 achou o mesmo defeito tres vezes:
    funcao de dominio pronta e testada que NENHUMA TELA CHAMA. `ler()` sabia
    ler a remessa desde o comeco, e o balcao nao tinha por onde receber.

    Buraco de tela nao aparece em teste de dominio. Estes conferem o caminho
    inteiro: o arquivo sobe pelo formulario, a conferencia mostra, o
    recebimento grava, e a confirmacao baixa em ISO-8859-1.
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
EXEMPLO = (Path(__file__).parent / "cra_remessa_exemplo.txt").read_bytes()
RETORNO = (Path(__file__).parent / "cra_retorno_exemplo.txt").read_bytes()


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


def conferir(s, conteudo=EXEMPLO, nome="B0001307.221"):
    """Sobe o arquivo pelo formulário, como o escrevente faz."""
    tela = s["c"].get("/protesto/remessas").get_data(as_text=True)
    from io import BytesIO
    return s["c"].post(
        "/protesto/remessas/conferir",
        data={"csrf_token": _token(tela),
              "arquivo": (BytesIO(conteudo), nome)},
        content_type="multipart/form-data", follow_redirects=True)


def receber(s, conteudo=EXEMPLO, **extra):
    resposta = conferir(s, conteudo)
    html = resposta.get_data(as_text=True)
    achado = re.search(r'name="conteudo" value="([^"]*)"', html)
    assert achado, "a conferência não devolveu o arquivo para o passo seguinte"
    dados = {"csrf_token": _token(html),
             "conteudo": achado.group(1).replace("&#34;", '"')
                                        .replace("&amp;", "&")
                                        .replace("&lt;", "<")
                                        .replace("&gt;", ">"),
             "nome_arquivo": "B0001307.221", "apontar": "1"}
    dados.update(extra)
    return s["c"].post("/protesto/remessas/receber", data=dados,
                       follow_redirects=True)


# ------------------------------------------------------------- a lista


def test_a_lista_abre_e_diz_o_que_fazer(s):
    html = s["c"].get("/protesto/remessas").get_data(as_text=True)
    assert "Remessa da CRA" in html
    # Lista vazia que so mostra nada faz o operador achar que quebrou.
    assert "Nenhuma remessa recebida ainda" in html
    assert 'name="arquivo"' in html


def test_a_remessa_esta_no_menu(s):
    html = s["c"].get("/protesto/titulos",
                      follow_redirects=True).get_data(as_text=True)
    assert "/protesto/remessas" in html


# --------------------------------------------------------- a conferência


def test_a_conferencia_mostra_o_lote_e_NAO_GRAVA(s):
    html = conferir(s).get_data(as_text=True)
    assert "Nada foi gravado ainda" in html
    assert "Apresentante 001" in html
    con = _con(s)
    assert con.execute("SELECT COUNT(*) c FROM pt_remessas").fetchone()["c"] == 0
    assert con.execute("SELECT COUNT(*) c FROM pt_titulos").fetchone()["c"] == 0


def test_xml_da_cra_conferencia_oferece_recebimento_sem_gravar(s):
    from test_protesto_cra_xml import _arquivo_xml

    html = conferir(s, _arquivo_xml(), "exemplo.xml").get_data(as_text=True)
    assert "Remessa XML da CRA" in html
    assert 'action="/protesto/remessas/receber"' in html
    assert 'name="origem_xml_token"' in html
    assert 'name="origem_xml_ambiente"' in html
    con = _con(s)
    assert con.execute("SELECT COUNT(*) c FROM pt_remessas").fetchone()["c"] == 0
    assert con.execute("SELECT COUNT(*) c FROM pt_titulos").fetchone()["c"] == 0


def test_receber_xml_pela_tela_grava_origem_xml(s):
    from test_protesto_cra_xml import _arquivo_xml

    resposta = conferir(s, _arquivo_xml(), "exemplo.xml")
    html = resposta.get_data(as_text=True)
    achado = re.search(r'name="origem_xml_token" value="([0-9a-f]{64})"', html)
    assert achado
    dados = {"csrf_token": _token(html), "origem_xml_token": achado.group(1),
             "nome_arquivo": "exemplo.xml", "apontar": "1",
             "origem_xml_ambiente": "HOMOLOGACAO"}
    # 14/10/2026: a conferência manda PRODUCAO no campo escondido, e mesmo
    # um formulário antigo com HOMOLOGACAO entra como produção — «agora é
    # tudo produção». Até 13/10 o lote entrava marcado de homologação.
    assert 'name="origem_xml_ambiente" value="PRODUCAO"' in html
    html = s["c"].post("/protesto/remessas/receber", data=dados,
                       follow_redirects=True).get_data(as_text=True)
    assert "Remessa recebida" in html
    con = _con(s)
    remessa = con.execute("SELECT * FROM pt_remessas").fetchone()
    assert remessa["origem_xml_ambiente"] == "PRODUCAO"
    assert remessa["origem_xml_hash_lote"]
    assert remessa["origem_xml_chave"]


def test_a_conferencia_devolve_o_arquivo_para_o_passo_seguinte(s):
    # Senao o escrevente teria de escolher o arquivo duas vezes.
    html = conferir(s).get_data(as_text=True)
    assert 'name="conteudo"' in html


def test_arquivo_que_nao_e_remessa_avisa_e_volta(s):
    # AS PASTAS DO E-OFICIO MENTEM: ha remessa dentro de `Retorno`.
    html = conferir(s, RETORNO).get_data(as_text=True)
    assert "não é uma remessa" in html
    assert "Remessa da CRA" in html          # voltou para a lista


def test_sem_escolher_arquivo_avisa_e_volta(s):
    tela = s["c"].get("/protesto/remessas").get_data(as_text=True)
    html = s["c"].post("/protesto/remessas/conferir",
                       data={"csrf_token": _token(tela)},
                       content_type="multipart/form-data",
                       follow_redirects=True).get_data(as_text=True)
    assert "Escolha o arquivo" in html


# ------------------------------------------------------------ receber


def test_receber_grava_aponta_e_confirma(s):
    html = receber(s).get_data(as_text=True)
    assert "Remessa recebida" in html

    con = _con(s)
    remessa = con.execute("SELECT * FROM pt_remessas").fetchone()
    assert remessa["recebidos"] == 1 and remessa["apontados"] == 1
    assert remessa["nome_arquivo"] == "B0001307.221"

    tit = con.execute("SELECT * FROM pt_titulos").fetchone()
    assert tit["situacao"] == "APONTADO" and tit["protocolo"]
    assert tit["remessa_id"] == remessa["id"]

    confirmacao = con.execute(
        "SELECT * FROM pt_retornos WHERE tipo='SDTBFOCRT'").fetchone()
    assert confirmacao and confirmacao["id"] == remessa["confirmacao_id"]


def test_a_ficha_do_lote_mostra_o_que_entrou_e_a_confirmacao(s):
    receber(s)
    con = _con(s)
    remessa_id = con.execute("SELECT id FROM pt_remessas").fetchone()["id"]
    html = s["c"].get(f"/protesto/remessas/{remessa_id}").get_data(as_text=True)
    assert "Remessa recebida" in html
    assert "baixar" in html
    assert "aviso de intimação" in html      # o passo seguinte do roteiro


def test_a_confirmacao_baixa_em_iso_8859_1(s):
    # O arquivo de 600 posicoes nunca foi UTF-8: acento em dois bytes
    # empurraria todos os campos da linha para a direita.
    receber(s)
    con = _con(s)
    confirmacao_id = con.execute(
        "SELECT id FROM pt_retornos WHERE tipo='SDTBFOCRT'").fetchone()["id"]
    r = s["c"].get(f"/protesto/retornos/{confirmacao_id}/arquivo")
    assert r.status_code == 200
    assert "ISO-8859-1" in r.headers["Content-Type"]
    assert b"SDTBFOCRT" in r.data


def test_a_remessa_baixa_como_chegou(s):
    # Quando a Central reclamar de um titulo, e este teor que se le.
    receber(s)
    con = _con(s)
    remessa_id = con.execute("SELECT id FROM pt_remessas").fetchone()["id"]
    r = s["c"].get(f"/protesto/remessas/{remessa_id}/arquivo")
    assert r.status_code == 200
    assert b"BFOSDTTPR" in r.data


def test_receber_a_mesma_remessa_duas_vezes_avisa_e_nao_grava(s):
    receber(s)
    con = _con(s)
    antes = con.execute("SELECT COUNT(*) c FROM pt_titulos").fetchone()["c"]
    html = receber(s).get_data(as_text=True)
    assert "já entrou" in html
    depois = _con(s).execute(
        "SELECT COUNT(*) c FROM pt_titulos").fetchone()["c"]
    assert depois == antes


def test_apontar_desmarcado_deixa_o_titulo_esperando(s):
    receber(s, apontar="0")
    con = _con(s)
    assert con.execute("SELECT situacao FROM pt_titulos").fetchone()[0] == "RECEBIDO"
    assert con.execute("SELECT COUNT(*) c FROM pt_atos").fetchone()["c"] == 0


def test_lote_sem_arquivo_no_formulario_avisa_e_volta(s):
    tela = s["c"].get("/protesto/remessas").get_data(as_text=True)
    html = s["c"].post("/protesto/remessas/receber",
                       data={"csrf_token": _token(tela), "conteudo": ""},
                       follow_redirects=True).get_data(as_text=True)
    assert "não veio junto" in html


def test_lote_que_nao_existe_nao_estoura(s):
    assert s["c"].get("/protesto/remessas/9999").status_code == 404


def test_receber_e_de_quem_atende_e_a_lista_e_de_todos(cg_casa):
    # Consultar e de todo mundo, o AUDITOR incluido; receber, nao — e ato
    # que aponta titulo, e apontamento nao se desfaz.
    s = _sessao(cg_casa, papel="AUDITOR")
    tela = s["c"].get("/protesto/remessas")
    assert tela.status_code == 200
    # Com o token: o que recusa e o PAPEL, e nao o CSRF.
    r = s["c"].post("/protesto/remessas/receber",
                    data={"csrf_token": _token(tela.get_data(as_text=True)),
                          "conteudo": EXEMPLO.decode("latin-1")})
    assert r.status_code in (302, 403)
    con = _con(s)
    assert con.execute("SELECT COUNT(*) c FROM pt_remessas").fetchone()["c"] == 0
