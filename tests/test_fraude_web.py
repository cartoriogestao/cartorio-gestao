"""
Testes das TELAS da lista de atencao para fraudes.

POR QUE ELES EXISTEM
    Buraco de tela nao aparece em teste de dominio, e este modulo e todo sobre
    tela: uma lista que ninguem consulta e uma pasta com outro nome.

    O que eles conferem, alem de abrir:

    Que o ALERTA APARECE ONDE O ATO ACONTECE — na ficha do titulo —, e nao
    numa aba. Aviso que chega depois de o escrevente ter lancado o ato chegou
    tarde.

    Que a CONSULTA E DE TODOS. Por o balcao atras de perfil seria deixar a
    informacao longe de quem precisa dela no momento em que ela serve.

    Que a LISTA e de quem recebe as comunicacoes — oficial e gerente.

    E que o RASTRO se grava quando o operador reconhece, e nao ao mostrar: se
    um ato fraudado passar apesar do aviso, a pergunta e "o sistema avisou?".
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


def incluir(s, **extra):
    tela = s["c"].get("/fraudes").get_data(as_text=True)
    dados = {"csrf_token": _token(tela), "papel": "ENVOLVIDO",
             "origem": "Ofício 123/2026, recebido pelo malote"}
    dados.update(extra)
    return s["c"].post("/fraudes/incluir", data=dados, follow_redirects=True)


def titulo_com(s, *, devedor: str, documento: str = "04785512388") -> int:
    """Um título apontado, com aquele devedor. O domínio grava; a tela lê."""
    import protesto as PT
    from database import Database

    sv = {"unit_name": "SERVENTIA", "ri_cns": "000000",
          "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
    db = Database(s["banco"])
    agora = db.now()
    with db.transaction() as con:
        con.row_factory = sqlite3.Row
        tid = PT.cadastrar_titulo(con, {
            "apresentante_codigo": "001", "apresentante_nome": "BANCO",
            "especie": "DMI", "numero_titulo": "84713/1",
            "nosso_numero": "N1", "data_emissao": "2026-01-05",
            "data_vencimento": "2026-02-05", "valor": "100.00",
            "saldo": "100.00", "praca_protesto": "CIDADE EXEMPLO",
            "cedente": {"nome": "LOJA CENTRAL", "documento": "00000017000149"},
            "devedores": [{"nome": devedor, "CPF": documento,
                           "enderecos": [{"endereco": "RUA GRANDE, 10",
                                          "cidade": "Cidade Exemplo",
                                          "uf": "MA"}]}],
        }, origem="CRA", origem_chave="lote:1", agora=agora)
        PT.lancar_apontamento(con, tid, sv=sv, agora=agora, data_extenso="x")
    return tid


# --------------------------------------------------------------- a lista


def test_a_lista_abre_e_diz_para_que_serve(s):
    html = s["c"].get("/fraudes").get_data(as_text=True)
    assert "Atenção para fraudes" in html
    assert "malote" in html
    # A lista vazia diz o que fazer, em vez de só mostrar nada.
    assert "A lista está vazia" in html
    # E a regra que mais importa está escrita na tela.
    assert "não trava o ato" in html


def test_os_dois_links_estao_no_menu(s):
    html = s["c"].get("/").get_data(as_text=True)
    assert "/fraudes/consultar" in html
    assert "/fraudes" in html


def test_incluir_pela_tela(s):
    html = incluir(s, nome="José da Silva", documento="047.855.123-88",
                   origem_orgao="Corregedoria-Geral",
                   observacao="uso de CPF de terceiro").get_data(as_text=True)
    assert "entrou na lista de atenção" in html

    a = _con(s).execute("SELECT * FROM fr_alertas").fetchone()
    assert a["nome_norm"] == "jose da silva"
    assert a["documento"] == "04785512388"
    assert a["criado_por"] == "MARIO EXEMPLO DOS SANTOS"


def test_sem_procedencia_avisa_e_nao_grava(s):
    html = incluir(s, nome="José", origem="").get_data(as_text=True)
    assert "de onde veio a comunicação" in html
    assert _con(s).execute("SELECT COUNT(*) c FROM fr_alertas").fetchone()["c"] == 0


def test_tirar_da_lista_exige_motivo(s):
    incluir(s, nome="José da Silva")
    aid = _con(s).execute("SELECT id FROM fr_alertas").fetchone()["id"]
    tela = s["c"].get("/fraudes").get_data(as_text=True)
    html = s["c"].post(f"/fraudes/{aid}/situacao",
                       data={"csrf_token": _token(tela), "motivo": "não"},
                       follow_redirects=True).get_data(as_text=True)
    assert "não se apaga sem explicação" in html
    assert _con(s).execute(
        "SELECT situacao FROM fr_alertas").fetchone()[0] == "ATIVO"


def test_a_lista_tambem_e_do_escrevente(cg_casa):
    # Era só de quem recebe as comunicações (ADMIN/MANAGER); a 3.6.160
    # (21/09/2026) abriu-a ao perfil USER, e o oficial confirmou em 11/10/2026:
    # «manter abertas».
    s = _sessao(cg_casa, papel="USER")
    assert s["c"].get("/fraudes").status_code == 200


# ------------------------------------------------------------ a consulta


def test_a_consulta_e_de_TODOS(cg_casa):
    # Pôr o balcão atrás de perfil seria deixar a informação longe de quem
    # precisa dela no momento em que ela serve.
    s = _sessao(cg_casa, papel="USER")
    assert s["c"].get("/fraudes/consultar").status_code == 200


def test_a_consulta_acha_e_diz_de_onde_veio(s):
    incluir(s, nome="José da Silva", origem="Ofício 123/2026",
            origem_orgao="Corregedoria-Geral")
    html = s["c"].get("/fraudes/consultar?nome=jose+da+silva").get_data(as_text=True)
    assert "Envolvido em fraude" in html
    assert "Ofício 123/2026" in html
    assert "Corregedoria-Geral" in html
    # E diz que bateu por NOME, que é o achado fraco.
    assert "bateu pelo <strong>nome</strong>" in html


def test_a_consulta_que_nao_acha_diz_que_nao_achou(s):
    html = s["c"].get("/fraudes/consultar?nome=ninguem").get_data(as_text=True)
    assert "Nada na lista de atenção" in html


def test_o_documento_e_o_achado_FORTE(s):
    incluir(s, documento="04785512388")
    html = s["c"].get(
        "/fraudes/consultar?documento=047.855.123-88").get_data(as_text=True)
    assert "bateu pelo <strong>documento</strong>" in html
    assert "não tem homônimo" in html


def test_a_consulta_mostra_o_que_a_casa_JA_TEM(s):
    # A comunicação chega depois do fato.
    titulo_com(s, devedor="JOSÉ DA SILVA")
    incluir(s, nome="José da Silva")
    html = s["c"].get("/fraudes/consultar?nome=jose+da+silva").get_data(as_text=True)
    assert "O que esta casa já tem desse nome" in html
    assert "devedor de protesto" in html


# ------------------------------------- o alerta ONDE O ATO ACONTECE


def test_o_alerta_aparece_na_FICHA_DO_TITULO(s):
    """O ponto do pedido: o sistema alerta quando o ato é cadastrado.

    Aviso que aparece depois de o escrevente já ter lançado o ato é aviso que
    chegou tarde — por isso ele vem no alto da ficha, antes dos atos.
    """
    tid = titulo_com(s, devedor="JOSÉ DA SILVA")
    incluir(s, nome="José da Silva", papel="ENVOLVIDO",
            origem="Ofício 123/2026")
    html = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "Atenção para fraudes" in html
    assert "Envolvido em fraude" in html
    assert "devedor" in html
    assert "Ofício 123/2026" in html


def test_o_alerta_confere_TODAS_as_partes_do_titulo(s):
    # Um título tem devedor e credor. Conferir um só deixaria o outro passar.
    tid = titulo_com(s, devedor="MARIA SOUZA")
    incluir(s, nome="LOJA CENTRAL", papel="ENVOLVIDO")
    html = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "Atenção para fraudes" in html
    assert "credor" in html


def test_a_VITIMA_aparece_com_o_aviso_dela_e_nao_com_o_do_envolvido(s):
    tid = titulo_com(s, devedor="MARIA VÍTIMA")
    incluir(s, nome="Maria Vítima", papel="VITIMA")
    html = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "Vítima de fraude" in html
    assert "quem se protege" in html
    assert "segue normalmente" in html


def test_titulo_sem_nome_na_lista_NAO_mostra_alerta(s):
    tid = titulo_com(s, devedor="PESSOA COMUM")
    incluir(s, nome="Outra Pessoa")
    html = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "Atenção para fraudes —" not in html


def test_a_ficha_do_titulo_NAO_grava_conferencia_ao_mostrar(s):
    # Tela de leitura que grava fica presa no `busy_timeout` enquanto outro
    # balcão lavra. O rastro se grava quando o operador reconhece.
    tid = titulo_com(s, devedor="JOSÉ DA SILVA")
    incluir(s, nome="José da Silva")
    s["c"].get(f"/protesto/{tid}")
    s["c"].get(f"/protesto/{tid}")
    assert _con(s).execute(
        "SELECT COUNT(*) c FROM fr_conferencias").fetchone()["c"] == 0


# --------------------------------------------------------------- o rastro


def test_registrar_a_conferencia_deixa_o_rastro(s):
    tid = titulo_com(s, devedor="JOSÉ DA SILVA")
    incluir(s, nome="José da Silva")
    aid = _con(s).execute("SELECT id FROM fr_alertas").fetchone()["id"]

    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    s["c"].post(f"/fraudes/{aid}/conferir", data={
        "csrf_token": _token(ficha), "decisao": "PROSSEGUIU",
        "onde": "protesto — ficha do título", "referencia": "84713/1",
        "nome": "JOSÉ DA SILVA",
        "observacao": "conferi o RG; é outra pessoa, mesma homonímia",
        "volta": f"/protesto/{tid}"}, follow_redirects=True)

    c = _con(s).execute("SELECT * FROM fr_conferencias").fetchone()
    assert c["decisao"] == "PROSSEGUIU"
    assert c["conferido_por"] == "MARIO EXEMPLO DOS SANTOS"
    assert "homonímia" in c["observacao"]

    # E o rastro aparece na lista, que é onde se pergunta "o sistema avisou?".
    html = s["c"].get("/fraudes").get_data(as_text=True)
    assert "Alertas que apareceram no balcão" in html
    assert "prosseguiu" in html


# ---------------------------- as outras portas: RCPN, RCPJ/RTD e Livro 3
#
# UMA MACRO SO serve as quatro fichas (`_fraude.html`). Escrever o bloco quatro
# vezes daria quatro versoes divergentes do aviso que mais importa — e a
# consistencia aqui nao e estetica: e o operador achar a mesma coisa, com as
# mesmas palavras, em qualquer atribuicao.


def assento_de(s, *, nome: str) -> int:
    """Um assento de nascimento, gravado direto — a tela só consulta."""
    from database import Database
    db = Database(s["banco"])
    agora = db.now()
    with db.transaction() as con:
        cur = con.execute(
            """INSERT INTO rc_assentos(serie, especie, nome, data_ato,
                   dados_json, situacao, origem, criado_em)
               VALUES ('RC_A','NASCIMENTO',?,?, '{}', 'ATIVO','MANUAL',?)""",
            (nome, agora[:10], agora))
        return int(cur.lastrowid)


def registro_de(s, *, requerente: str, documento: str = "") -> int:
    from database import Database
    db = Database(s["banco"])
    agora = db.now()
    with db.transaction() as con:
        cur = con.execute(
            """INSERT INTO rg_registros(atribuicao, serie, numero, natureza,
                   requerente_nome, requerente_documento, situacao, origem,
                   criado_em)
               VALUES (3,'PJ_A',1,'Estatuto',?,?,'ATIVO','MANUAL',?)""",
            (requerente, documento, agora))
        return int(cur.lastrowid)


def livro3_de(s, *, parte: str, papel: str = "emitente") -> int:
    from database import Database
    db = Database(s["banco"])
    agora = db.now()
    with db.transaction() as con:
        cur = con.execute(
            """INSERT INTO ra_registros(numero, natureza, situacao, origem,
                   criado_em)
               VALUES (1,'Cédula de crédito rural','ATIVO','MANUAL',?)""",
            (agora,))
        rid = int(cur.lastrowid)
        con.execute(
            """INSERT INTO ra_partes(registro_id, nome, papel, origem)
               VALUES (?,?,?,'MANUAL')""", (rid, parte, papel))
        return rid


def test_o_alerta_aparece_no_ASSENTO_do_RCPN(s):
    aid = assento_de(s, nome="JOSÉ DA SILVA")
    incluir(s, nome="José da Silva", papel="ENVOLVIDO")
    html = s["c"].get(f"/rcpn/{aid}").get_data(as_text=True)
    assert "Atenção para fraudes" in html
    assert "registrado" in html


def test_o_alerta_aparece_no_REGISTRO_do_RCPJ(s):
    rid = registro_de(s, requerente="ASSOCIAÇÃO ALFA",
                      documento="00000017000149")
    incluir(s, documento="00.000.017/0001-49", papel="ENVOLVIDO")
    html = s["c"].get(f"/rcpj-rtd/{rid}").get_data(as_text=True)
    assert "Atenção para fraudes" in html
    assert "requerente" in html
    # Bateu por DOCUMENTO, que é o achado forte.
    assert "não tem homônimo" in html


def test_o_alerta_aparece_nas_PARTES_do_LIVRO_3(s):
    rid = livro3_de(s, parte="MARIA SOUZA", papel="avalista")
    incluir(s, nome="Maria Souza", papel="VITIMA")
    html = s["c"].get(f"/livro3/{rid}").get_data(as_text=True)
    assert "Atenção para fraudes" in html
    assert "avalista" in html
    # E a vítima recebe o aviso DELA, e não o do envolvido.
    assert "quem se protege" in html


def test_as_QUATRO_fichas_usam_a_MESMA_macro(s):
    """A consistência aqui não é estética.

    O operador tem de achar a mesma coisa, com as mesmas palavras, em qualquer
    atribuição. Quatro cópias do bloco divergiriam na primeira correção.
    """
    incluir(s, nome="JOSÉ DA SILVA", papel="ENVOLVIDO")
    telas = [
        f"/protesto/{titulo_com(s, devedor='JOSÉ DA SILVA')}",
        f"/rcpn/{assento_de(s, nome='JOSÉ DA SILVA')}",
        f"/rcpj-rtd/{registro_de(s, requerente='JOSÉ DA SILVA')}",
        f"/livro3/{livro3_de(s, parte='JOSÉ DA SILVA')}",
    ]
    for caminho in telas:
        html = s["c"].get(caminho).get_data(as_text=True)
        assert "Atenção para fraudes — Envolvido em fraude" in html, caminho
        assert "Registrar a conferência" in html, caminho
        assert "antes de lavrar" in html, caminho


def protocolo_de(s, *, interessado: str, documento: str = "") -> int:
    """Um protocolo do balcão — o «ato requerido» do pedido do oficial."""
    from database import Database
    db = Database(s["banco"])
    agora = db.now()
    with db.transaction() as con:
        cur = con.execute(
            """INSERT INTO cx_protocolos(numero, data_abertura, atribuicao,
                   interessado, interessado_documento, assunto, situacao,
                   criado_em)
               VALUES ('2026.0001', ?, 'NOTAS', ?, ?, 'escritura', 'ABERTO',
                       ?)""",
            (agora[:10], interessado, documento or None, agora))
        return int(cur.lastrowid)


def test_o_alerta_aparece_no_PROTOCOLO_DO_BALCAO(s):
    """O «ato requerido» do pedido: "alerta quando um ato for REQUERIDO ou
    cadastrado".

    O protocolo é onde o cliente chega, dá o nome e pede o ato. Avisar só
    quando o ato for lavrado seria avisar depois de a casa ter trabalhado.
    """
    pid = protocolo_de(s, interessado="JOSÉ DA SILVA")
    incluir(s, nome="José da Silva", papel="ENVOLVIDO",
            origem="Ofício 123/2026")
    html = s["c"].get(f"/caixa/protocolos/{pid}").get_data(as_text=True)
    assert "Atenção para fraudes" in html
    assert "interessado" in html
    assert "Ofício 123/2026" in html


def test_protocolo_de_quem_nao_esta_na_lista_nao_alerta(s):
    pid = protocolo_de(s, interessado="PESSOA COMUM")
    incluir(s, nome="Outra Pessoa")
    html = s["c"].get(f"/caixa/protocolos/{pid}").get_data(as_text=True)
    assert "Atenção para fraudes —" not in html


# --------------------------- as duas ultimas portas: Notas e Registro de Imoveis


def ato_de_notas(s, *, parte: str, qualificacao: str = "outorgante") -> int:
    from database import Database
    from pt_schema import normalizar_nome
    db = Database(s["banco"])
    agora = db.now()
    with db.transaction() as con:
        cur = con.execute(
            """INSERT INTO nt_atos(tipo, data, situacao, criado_em)
               VALUES ('ESCRITURA', ?, 'EM_LAVRATURA', ?)""",
            (agora[:10], agora))
        aid = int(cur.lastrowid)
        con.execute(
            """INSERT INTO nt_ato_partes(ato_id, nome, nome_norm, documento,
                   qualificacao, criado_em)
               VALUES (?,?,?,NULL,?,?)""",
            (aid, parte, normalizar_nome(parte), qualificacao, agora))
        return aid


def matricula_de(s, *, parte: str, papel: str = "adquirente") -> int:
    from database import Database
    db = Database(s["banco"])
    agora = db.now()
    with db.transaction() as con:
        cur = con.execute(
            """INSERT INTO ri_matriculas(numero, livro, criado_em)
               VALUES ('1', '2', ?)""", (agora,))
        mid = int(cur.lastrowid)
        con.execute(
            """INSERT INTO ri_partes(matricula_id, nome, papel)
               VALUES (?,?,?)""", (mid, parte, papel))
        return mid


def test_o_alerta_aparece_no_ATO_DAS_NOTAS(s):
    aid = ato_de_notas(s, parte="JOSÉ DA SILVA")
    incluir(s, nome="José da Silva", papel="ENVOLVIDO")
    html = s["c"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert "Atenção para fraudes" in html
    assert "outorgante" in html


def test_o_alerta_aparece_na_MATRICULA_DO_RI(s):
    """E ele vem AO LADO da consulta ao CNIB, que já roda ali.

    São duas listas diferentes, de fontes diferentes, e nenhuma substitui a
    outra: o CNIB é indisponibilidade; esta é fraude comunicada pelo malote.
    """
    mid = matricula_de(s, parte="MARIA SOUZA")
    incluir(s, nome="Maria Souza", papel="VITIMA")
    html = s["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Atenção para fraudes" in html
    assert "adquirente" in html
    assert "quem se protege" in html


def test_a_consulta_acha_nas_SEIS_atribuicoes(s):
    """A comunicação chega depois do fato, e o fato pode estar em qualquer
    atribuição."""
    titulo_com(s, devedor="JOSÉ DA SILVA")
    assento_de(s, nome="JOSÉ DA SILVA")
    registro_de(s, requerente="JOSÉ DA SILVA")
    livro3_de(s, parte="JOSÉ DA SILVA")
    ato_de_notas(s, parte="JOSÉ DA SILVA")
    matricula_de(s, parte="JOSÉ DA SILVA")

    html = s["c"].get("/fraudes/consultar?nome=jose+da+silva").get_data(as_text=True)
    for oque in ("devedor de protesto", "assento do Registro Civil",
                 "requerente de registro do RCPJ/RTD", "parte no Livro 3",
                 "parte em ato das Notas", "parte em matrícula do RI"):
        assert oque in html, oque
