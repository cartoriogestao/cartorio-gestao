"""
Testes das TELAS do aviso de intimacao, da entrega e do edital.

POR QUE ELES EXISTEM SEPARADOS DOS DE DOMINIO
    Buraco de tela nao aparece em teste de dominio. Foi assim com o devedor,
    com o apontamento, com a numeracao e com a remessa: funcao pronta e
    testada que nenhuma tela chamava.

    Estes conferem o caminho inteiro do balcao: o aviso sai NA FICHA do titulo,
    a entrega se registra na tela dos avisos, o edital se publica dali, e a
    folha do dia baixa em `.odt` para afixar na parede.
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


def titulo_apontado(s) -> int:
    """Um titulo apontado, gravado pelo dominio — a tela so consulta."""
    import protesto as PT
    from database import Database

    sv = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
          "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
          "serventia_titulo": "Tabelião e Oficial de Registro",
          "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
    db = Database(s["banco"])
    agora = db.now()
    with db.transaction() as con:
        con.row_factory = sqlite3.Row
        tid = PT.cadastrar_titulo(con, {
            "apresentante_codigo": "001", "apresentante_nome": "BANCO DO BRASIL",
            "especie": "DMI", "numero_titulo": "9911/1",
            "nosso_numero": "NN9911", "data_emissao": "2026-01-05",
            "data_vencimento": "2026-02-05", "valor": "1200.00",
            "saldo": "1310.45", "praca_protesto": "CIDADE EXEMPLO",
            "cedente": {"nome": "LOJA CENTRAL LTDA",
                        "documento": "00000017000149"},
            "devedores": [{"nome": "JOSÉ DA SILVA", "CPF": "04785512388",
                           "enderecos": [{"endereco": "RUA GRANDE, 10",
                                          "bairro": "CENTRO",
                                          "cidade": "Cidade Exemplo",
                                          "uf": "MA"}]}],
        }, origem="CRA", origem_chave="lote:1", agora=agora)
        PT.lancar_apontamento(con, tid, sv=sv, agora=agora,
                              data_extenso="vinte e cinco de agosto")
    return tid


def emitir(s, titulo_id: int, **extra):
    ficha = s["c"].get(f"/protesto/{titulo_id}").get_data(as_text=True)
    dados = {"csrf_token": _token(ficha)}
    dados.update(extra)
    return s["c"].post(f"/protesto/{titulo_id}/aviso", data=dados,
                       follow_redirects=True)


def aviso_id(s) -> int:
    return _con(s).execute("SELECT MAX(id) i FROM pt_avisos").fetchone()["i"]


def registrar(s, aid: int, **extra):
    tela = s["c"].get("/protesto/avisos").get_data(as_text=True)
    dados = {"csrf_token": _token(tela)}
    dados.update(extra)
    return s["c"].post(f"/protesto/avisos/{aid}/entrega", data=dados,
                       follow_redirects=True)


# ------------------------------------------------------------- a ficha


def test_a_ficha_oferece_o_aviso_no_titulo_apontado(s):
    tid = titulo_apontado(s)
    html = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "Avisos de intimação" in html
    assert "Emitir aviso" in html
    assert "congela no aviso" in html


def test_a_ficha_NAO_oferece_aviso_de_titulo_nao_apontado(s):
    # O apontamento é o primeiro ato, e é ele que dá o protocolo do aviso.
    tid = titulo_apontado(s)
    con = _con(s)
    with con:
        con.execute("UPDATE pt_titulos SET situacao='RECEBIDO' WHERE id=?",
                    (tid,))
    html = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "Só se emite aviso de título" in html
    assert f'action="/protesto/{tid}/aviso"' not in html


def test_emitir_o_aviso_pela_ficha(s):
    tid = titulo_apontado(s)
    html = emitir(s, tid).get_data(as_text=True)
    assert "Aviso 1/" in html and "JOSÉ DA SILVA" in html

    aviso = _con(s).execute("SELECT * FROM pt_avisos").fetchone()
    assert aviso["situacao"] == "EMITIDO"
    assert aviso["endereco"] == "RUA GRANDE, 10"
    assert aviso["emitido_por"] == "MARIO EXEMPLO DOS SANTOS"


def test_endereco_do_balcao_vale_so_para_aquele_aviso(s):
    tid = titulo_apontado(s)
    emitir(s, tid, endereco="PRAÇA DA MATRIZ, 3", bairro="CENTRO")
    aviso = _con(s).execute("SELECT * FROM pt_avisos").fetchone()
    assert aviso["endereco"] == "PRAÇA DA MATRIZ, 3"
    # O cadastro do devedor não muda: o endereço melhor foi para o papel.
    dev = _con(s).execute("SELECT endereco FROM pt_devedores").fetchone()
    assert dev["endereco"] == "RUA GRANDE, 10"


def test_a_ficha_mostra_os_avisos_ja_emitidos(s):
    tid = titulo_apontado(s)
    emitir(s, tid)
    emitir(s, tid)
    html = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "2/2026" in html and "1/2026" in html
    assert "esperando desfecho" in html


# ---------------------------------------------------------- a entrega


def test_a_tela_abre_e_diz_o_que_fazer(s):
    html = s["c"].get("/protesto/avisos").get_data(as_text=True)
    assert "Avisos de intimação" in html
    # o título da lista mudou em 15/10/2026: Resolve antes do edital
    assert "Nenhum aviso não entregue esperando" in html
    assert "Nenhum aviso esperando." in html


def test_a_tela_esta_no_menu(s):
    # A lista mora em `/protesto` desde a 3.6.193 (24/09/2026); o endereço
    # antigo só redireciona, e o redirecionamento não traz menu — 14/10/2026.
    html = s["c"].get("/protesto").get_data(as_text=True)
    assert "/protesto/avisos" in html


def test_entrega_com_exito_lavra_a_intimacao(s):
    tid = titulo_apontado(s)
    emitir(s, tid)
    html = registrar(s, aviso_id(s), entregue="1",
                     recebido_por="MARIA").get_data(as_text=True)
    assert "intimação pessoal foi lavrada" in html

    con = _con(s)
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] == "INTIMADO"
    ato = con.execute("SELECT * FROM pt_atos WHERE tipo='INTIMACAO'").fetchone()
    assert '"modo": "PESSOAL"' in ato["detalhe_json"]
    assert "MARIA" in ato["detalhe_json"]


def test_entrega_sem_exito_NAO_intima_e_manda_para_o_edital(s):
    tid = titulo_apontado(s)
    emitir(s, tid)
    html = registrar(s, aviso_id(s), entregue="0", motivo="11",
                     observacao="ninguém em casa").get_data(as_text=True)
    assert "Ausente" in html
    assert "Resolve, e depois edital" in html

    con = _con(s)
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] == "APONTADO"
    assert con.execute("SELECT COUNT(*) c FROM pt_atos WHERE tipo='INTIMACAO'"
                       ).fetchone()["c"] == 0
    assert "Não entregues — Resolve, e depois edital" in html


def test_nao_entrega_sem_motivo_avisa_e_nao_grava(s):
    tid = titulo_apontado(s)
    emitir(s, tid)
    html = registrar(s, aviso_id(s), entregue="0").get_data(as_text=True)
    assert "Ausente" in html          # a mensagem lista o catálogo
    assert _con(s).execute("SELECT situacao FROM pt_avisos").fetchone()[0] == "EMITIDO"


# ------------------------------------------------------------- o edital


def test_publicar_o_edital_lavra_a_intimacao_por_edital(s):
    tid = titulo_apontado(s)
    emitir(s, tid)
    aid = aviso_id(s)
    registrar(s, aid, entregue="0", motivo="11")

    tela = s["c"].get("/protesto/avisos").get_data(as_text=True)
    html = s["c"].post(f"/protesto/avisos/{aid}/edital",
                       data={"csrf_token": _token(tela)},
                       follow_redirects=True).get_data(as_text=True)
    assert "ED-2026-0001" in html
    assert "intimação por edital foi lavrada" in html

    con = _con(s)
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] == "INTIMADO"
    edital = con.execute("SELECT * FROM pt_editais").fetchone()
    assert edital["teor"] and edital["hash_teor"]
    assert "JOSÉ DA SILVA" in edital["teor"]


def test_o_edital_baixa_em_odt_com_o_teor_congelado(s):
    tid = titulo_apontado(s)
    emitir(s, tid)
    aid = aviso_id(s)
    registrar(s, aid, entregue="0", motivo="11")
    tela = s["c"].get("/protesto/avisos").get_data(as_text=True)
    s["c"].post(f"/protesto/avisos/{aid}/edital",
                data={"csrf_token": _token(tela)}, follow_redirects=True)

    eid = _con(s).execute("SELECT id FROM pt_editais").fetchone()["id"]
    r = s["c"].get(f"/protesto/editais/{eid}.odt")
    assert r.status_code == 200
    assert "opendocument" in r.headers["Content-Type"]
    assert r.data[:2] == b"PK"                 # .odt é um zip


def test_a_folha_do_dia_junta_os_editais(s):
    tid = titulo_apontado(s)
    emitir(s, tid)
    aid = aviso_id(s)
    registrar(s, aid, entregue="0", motivo="11")
    tela = s["c"].get("/protesto/avisos").get_data(as_text=True)
    s["c"].post(f"/protesto/avisos/{aid}/edital",
                data={"csrf_token": _token(tela)}, follow_redirects=True)

    r = s["c"].get("/protesto/editais/dia.odt")
    assert r.status_code == 200
    assert r.data[:2] == b"PK"


def test_folha_de_dia_sem_edital_avisa_e_volta(s):
    html = s["c"].get("/protesto/editais/dia.odt",
                      follow_redirects=True).get_data(as_text=True)
    assert "Nenhum edital publicado" in html


def test_edital_sem_tentativa_avisa_e_volta(s):
    tid = titulo_apontado(s)
    emitir(s, tid)
    aid = aviso_id(s)
    tela = s["c"].get("/protesto/avisos").get_data(as_text=True)
    html = s["c"].post(f"/protesto/avisos/{aid}/edital",
                       data={"csrf_token": _token(tela)},
                       follow_redirects=True).get_data(as_text=True)
    assert "não foi entregue" in html
    assert _con(s).execute("SELECT COUNT(*) c FROM pt_editais").fetchone()["c"] == 0


def test_edital_que_nao_existe_nao_estoura(s):
    assert s["c"].get("/protesto/editais/9999.odt").status_code == 404


def test_emitir_e_de_quem_atende_e_a_lista_e_de_todos(cg_casa):
    s = _sessao(cg_casa, papel="AUDITOR")
    tela = s["c"].get("/protesto/avisos")
    assert tela.status_code == 200
    r = s["c"].post("/protesto/1/aviso",
                    data={"csrf_token": _token(tela.get_data(as_text=True))})
    assert r.status_code in (302, 403)
    assert _con(s).execute("SELECT COUNT(*) c FROM pt_avisos").fetchone()["c"] == 0


def test_a_tela_mostra_o_RASTRO_das_tentativas(s):
    """O que justifica o edital não é "não entregue" — é o rastro.

    Guardar as tentativas sem mostrá-las não serviria de nada: quem lê a
    ficha é quem tem de saber que se tentou duas vezes.
    """
    tid = titulo_apontado(s)
    emitir(s, tid)
    aid = aviso_id(s)
    registrar(s, aid, entregue="0", motivo="11", quando="2026-08-20",
              observacao="fui de manhã")
    html = registrar(s, aid, entregue="0", motivo="12", quando="2026-08-22",
                     observacao="voltei à tarde").get_data(as_text=True)

    assert "1ª — 2026-08-20" in html and "Ausente" in html
    assert "2ª — 2026-08-22" in html and "Fechado" in html
    assert "fui de manhã" in html and "voltei à tarde" in html

    # E a ficha do título conta a mesma história.
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "1ª — 2026-08-20" in ficha and "2ª — 2026-08-22" in ficha


def test_a_tentativa_anterior_nao_some_quando_a_segunda_da_certo(s):
    tid = titulo_apontado(s)
    emitir(s, tid)
    aid = aviso_id(s)
    registrar(s, aid, entregue="0", motivo="11", quando="2026-08-20")
    registrar(s, aid, entregue="1", quando="2026-08-22", recebido_por="MARIA")

    con = _con(s)
    assert con.execute("SELECT COUNT(*) c FROM pt_tentativas").fetchone()["c"] == 2
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "Ausente" in ficha and "entregue" in ficha
