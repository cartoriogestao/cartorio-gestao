"""GUARDAR A REVISÃO DA MINUTA SEM LAVRAR — 15/09/2026.

    «tres atos devem ficar em pe, quero revisar no sistema e poder lavrar
     efetivamente (selando) depois»
    «deixe tudo pronto para comecar, revisar e encerrar qualquer ato no ri»

O BURACO. «Revisar» pode levar mais de uma sentada: o oficial abre a minuta,
    conserta uma vírgula, e é chamado ao balcão. Sem esta rota a correção só
    existia DENTRO do formulário de lavrar — quem saísse da tela perdia o
    trabalho, e no dia seguinte ou redigitava tudo ou lavrava com o erro
    dentro. **E ato lavrado não se edita**: o conserto seria uma averbação.

O QUE ESTES TESTES PROTEGEM
    1. Guardar muda o teor e **não lavra nada** — sem ato, sem número, sem
       selo, e a minuta continua na fila.
    2. É o MESMO formulário de lavrar, por `formaction` — e não um segundo com
       os mesmos campos, que divergiria no dia em que a tela ganhasse um campo.
    3. Campo que a tela não mandou **não se apaga**: `None` quer dizer «não
       mexi», e não «esvazie».
    4. Teor em branco não se guarda.
    5. Minuta já lavrada não se revisa — ela é a procedência do que está no
       livro.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_minuta as RIMIN

SENHA = "Senha#12345"

TEOR = ("AV-04/3.110 - CANCELAMENTO INTEGRAL DE HIPOTECA CEDULAR DE 1o GRAU, "
        "conforme o titulo apresentado.")
TEOR_REVISTO = ("AV-04/3.110 - CANCELAMENTO INTEGRAL DE HIPOTECA CEDULAR DE "
                "1o GRAU, conforme o titulo apresentado e a anuencia do "
                "credor, que fica arquivada nesta serventia.")


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


def _entrar(app, usuario: str):
    c = app.test_client()
    c.post("/login",
           data={"username": usuario, "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


# ------------------------------------------------- o aparelho desta bancada
#
# SEM SELADOR NAO SE LAVRA NADA desde 16/09/2026 — relato #77 mais o item 1
# («se falhar o selo, sempre suspender o ato»). Esta bancada fala de outra
# coisa; o selador esta aqui para o ato chegar a existir. Ver
# `tests/selador_de_bancada.py`.


@pytest.fixture(autouse=True)
def _o_selador_desta_bancada(cg_casa):
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(cg_casa) as aparelho:
        yield aparelho


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    db.create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("balcao", "QUEM ATENDE", SENHA, "USER")
    return {**cg_casa, "cliente": _entrar(cg_casa["app"], "jean")}


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _casa_com_minuta(casa):
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
                   tipo_ficha, criado_em)
               VALUES ('3110', '2-Q', '2-Q', 'ATIVO', 'ACERVO',
                       '2026-09-14T10:27')""")
        mid = int(cur.lastrowid)
        minuta_id = RIMIN.criar(
            con, matricula_id=mid, tipo="AV", teor=TEOR, numero_pretendido=4,
            natureza_titulo="Cancelamento de hipoteca cedular",
            agora="2026-09-15T08:00", origem=RIMIN.DESFEITO_DE_ATO,
            origem_chave="ri_atos:3728 AV-04")
    con.close()
    return mid, minuta_id


def _guardar(casa, mid, minuta_id, cliente=None, **campos):
    c = cliente or casa["cliente"]
    html = c.get(f"/registro-imoveis/{mid}?minuta={minuta_id}").get_data(
        as_text=True)
    dados = {"csrf_token": _token(html), "tipo": "AV", "numero": 4,
             "teor": TEOR_REVISTO}
    dados.update(campos)
    return c.post(f"/registro-imoveis/minuta/{minuta_id}/guardar", data=dados,
                  follow_redirects=True)


def _minuta(casa, minuta_id):
    con = _con(casa)
    r = con.execute("SELECT * FROM ri_minutas WHERE id=?",
                    (minuta_id,)).fetchone()
    con.close()
    return r


# ------------------------------------------------- guarda e não lavra nada


def test_guardar_muda_o_teor_e_nao_lavra_nada(casa):
    mid, minuta_id = _casa_com_minuta(casa)
    html = _guardar(casa, mid, minuta_id).get_data(as_text=True)

    mi = _minuta(casa, minuta_id)
    con = _con(casa)
    atos = con.execute("SELECT COUNT(*) FROM ri_atos WHERE matricula_id=?",
                       (mid,)).fetchone()[0]
    selos = con.execute("SELECT COUNT(*) FROM sd_selos").fetchone()[0]
    con.close()

    assert "anuencia do credor" in mi["teor"]
    assert mi["situacao"] == RIMIN.A_REVISAR, "guardar deixa ela na fila"
    assert mi["ato_id"] is None
    assert mi["atualizado_em"]
    assert mi["atualizado_por"] == "MARIO EXEMPLO DOS SANTOS"
    assert atos == 0, "guardar NAO lavra ato"
    assert selos == 0, "guardar NAO pede selo"
    assert "Revisão guardada" in html
    assert "nenhum ato foi lavrado" in html
    # E a minuta volta aberta, com o texto revisado dentro.
    assert "anuencia do credor" in html
    # O RASTRO FICA À VISTA, e com o NOME — a mesma convenção de «Ficha
    # reaberta em … por …», que aparece na mesma tela. Duas convenções na
    # mesma ficha é como elas divergem.
    assert "revisada em" in html
    assert "MARIO EXEMPLO DOS SANTOS" in html


def test_o_texto_revisado_e_o_que_vai_ser_lavrado_depois(casa):
    """O ciclo inteiro: revisa hoje, lavra amanha, e o ato sai revisado."""
    mid, minuta_id = _casa_com_minuta(casa)
    _guardar(casa, mid, minuta_id)

    c = casa["cliente"]
    html = c.get(f"/registro-imoveis/{mid}?minuta={minuta_id}").get_data(
        as_text=True)
    c.post(f"/registro-imoveis/{mid}/atos",
           data={"csrf_token": _token(html), "tipo": "AV", "numero": 4,
                 "data_ato": "2026-09-16", "teor": TEOR_REVISTO,
                 "natureza_titulo": "Anuencia para baixa de hipoteca cedular",
                 "codigo_tj": "16.22.2",
                 "minuta_id": minuta_id}, follow_redirects=True)

    con = _con(casa)
    ato = con.execute("SELECT * FROM ri_atos WHERE matricula_id=?",
                      (mid,)).fetchone()
    con.close()
    assert ato is not None
    assert "anuencia do credor" in ato["teor"]
    assert _minuta(casa, minuta_id)["situacao"] == RIMIN.LAVRADA


def test_guardar_muda_o_numero_pretendido_e_a_natureza(casa):
    mid, minuta_id = _casa_com_minuta(casa)
    _guardar(casa, mid, minuta_id, numero=7,
             natureza_titulo="Cancelamento de hipoteca")
    mi = _minuta(casa, minuta_id)
    assert mi["numero_pretendido"] == 7
    assert mi["natureza_titulo"] == "Cancelamento de hipoteca"


def test_campo_que_a_tela_nao_mandou_nao_se_apaga(casa):
    """`None` quer dizer «nao mexi», e nao «esvazie».

    Tratar os dois como a mesma coisa faria uma revisao do teor limpar a
    natureza do titulo sem ninguem pedir — e o selo a exige.
    """
    mid, minuta_id = _casa_com_minuta(casa)
    c = casa["cliente"]
    html = c.get(f"/registro-imoveis/{mid}?minuta={minuta_id}").get_data(
        as_text=True)
    # Manda SO o teor, sem natureza nenhuma no formulario.
    c.post(f"/registro-imoveis/minuta/{minuta_id}/guardar",
           data={"csrf_token": _token(html), "teor": TEOR_REVISTO},
           follow_redirects=True)
    mi = _minuta(casa, minuta_id)
    assert mi["natureza_titulo"] == "Cancelamento de hipoteca cedular", (
        "a natureza nao foi mandada, logo nao foi mexida")
    assert mi["numero_pretendido"] == 4
    assert mi["tipo"] == "AV"
    assert "anuencia do credor" in mi["teor"]


# ------------------------------------------------------------- as recusas


def test_teor_em_branco_nao_se_guarda(casa):
    mid, minuta_id = _casa_com_minuta(casa)
    html = _guardar(casa, mid, minuta_id, teor="   ").get_data(as_text=True)
    assert "não pode ficar em branco" in html
    assert _minuta(casa, minuta_id)["teor"] == TEOR, "o texto antigo fica"


def test_minuta_lavrada_nao_se_revisa(casa):
    """Ela e a procedencia do que esta no livro."""
    mid, minuta_id = _casa_com_minuta(casa)
    c = casa["cliente"]
    html = c.get(f"/registro-imoveis/{mid}?minuta={minuta_id}").get_data(
        as_text=True)
    c.post(f"/registro-imoveis/{mid}/atos",
           data={"csrf_token": _token(html), "tipo": "AV", "numero": 4,
                 "data_ato": "2026-09-16", "teor": TEOR,
                 "natureza_titulo": "Anuencia para baixa de hipoteca cedular",
                 "codigo_tj": "16.22.2",
                 "minuta_id": minuta_id}, follow_redirects=True)

    resposta = _guardar(casa, mid, minuta_id).get_data(as_text=True)
    assert "já saiu da fila de revisão" in resposta
    mi = _minuta(casa, minuta_id)
    assert mi["teor"] == TEOR, (
        "mudar o texto da minuta lavrada faria a prova discordar do ato que "
        "saiu dela")


def test_tipo_que_nao_e_ato_do_ri_nao_se_guarda(casa):
    mid, minuta_id = _casa_com_minuta(casa)
    html = _guardar(casa, mid, minuta_id, tipo="X").get_data(as_text=True)
    assert "não é tipo de ato" in html
    assert _minuta(casa, minuta_id)["tipo"] == "AV"


def test_numero_que_nao_e_numero_nao_se_guarda(casa):
    mid, minuta_id = _casa_com_minuta(casa)
    html = _guardar(casa, mid, minuta_id, numero="quatro").get_data(
        as_text=True)
    assert "não é um número" in html
    assert _minuta(casa, minuta_id)["numero_pretendido"] == 4


def test_minuta_que_nao_existe_da_404(casa):
    mid = _casa_com_minuta(casa)[0]
    c = casa["cliente"]
    html = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    r = c.post("/registro-imoveis/minuta/999999/guardar",
               data={"csrf_token": _token(html), "teor": TEOR_REVISTO})
    assert r.status_code == 404


# ------------------------------------------- um formulario so, e ele e o de lavrar


def test_quem_atende_revisa(casa):
    """Escrever o ato e o trabalho de quem atende; descartar e do oficial."""
    mid, minuta_id = _casa_com_minuta(casa)
    balcao = _entrar(casa["app"], "balcao")
    _guardar(casa, mid, minuta_id, cliente=balcao)
    assert "anuencia do credor" in _minuta(casa, minuta_id)["teor"]


def test_e_o_mesmo_formulario_de_lavrar(casa):
    """Dois formularios com os mesmos campos divergiriam no dia em que a tela
    ganhasse um campo — e o «guardar» passaria a perder justamente o novo."""
    mid, minuta_id = _casa_com_minuta(casa)
    html = casa["cliente"].get(
        f"/registro-imoveis/{mid}?minuta={minuta_id}").get_data(as_text=True)
    alvo = f"/registro-imoveis/minuta/{minuta_id}/guardar"
    assert f'formaction="{alvo}"' in html, (
        "o botao de guardar usa `formaction` no formulario de lavrar")
    assert f'<form method="post" action="{alvo}"' not in html, (
        "nao ha um segundo formulario com os mesmos campos")


def test_a_ficha_sem_minuta_aberta_nao_oferece_guardar(casa):
    mid = _casa_com_minuta(casa)[0]
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Guardar a revisão sem lavrar" not in html


def test_este_modulo_continua_sem_lavrar_selar_numerar_ou_cobrar():
    """`atualizar` entrou; a regua nao mudou."""
    proibidas = ("lavrar", "selar", "numerar", "cobrar", "obter_selo",
                 "emitir", "encerrar_matricula")
    achados = [n for n in dir(RIMIN)
               if not n.startswith("_")
               and any(p in n.lower() for p in proibidas)]
    assert not achados, f"nomes publicos suspeitos em ri_minuta: {achados}"
