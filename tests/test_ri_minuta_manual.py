"""NOVA MINUTA DIGITADA NA FICHA — origem MANUAL.

    `RIMIN.criar` existia, validava tipo e teor, e a constante MANUAL estava
    no módulo. Nenhuma tela a chamava. Função pronta sem porta: o defeito
    que este projeto já pagou seis vezes.

O QUE ESTES TESTES PROTEGEM
    1. A ficha oferece o formulário «Nova minuta» mesmo sem fila — senão a
       primeira minuta da matrícula não teria por onde nascer.
    2. O POST chama `RIMIN.criar` com origem MANUAL e a linha cai no painel
       «Minutas a revisar e lavrar», com os botões que já existiam.
    3. Não lavra nada: sem ato, sem número tomado, sem selo.
    4. Teor em branco e tipo que não é ato do RI não entram.
    5. Quem atende também cria — escrever o texto é o trabalho do balcão.
       Descartar continua sendo do oficial.
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

TEOR = ("AV-07/4.016 — Averbação de alteração de denominação do imóvel, "
        "conforme o título apresentado nesta serventia.")


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


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("balcao", "QUEM ATENDE", SENHA, "USER")
    return {**cg_casa, "cliente": _entrar(cg_casa["app"], "mario")}


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _ficha(con, numero="4016"):
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
               tipo_ficha, criado_em)
           VALUES (?, '2-Q', '2-Q', 'ATIVO', 'ACERVO', '2026-09-14T10:27')""",
        (numero,))
    return int(cur.lastrowid)


def _casa_com_ficha(casa, numero="4016"):
    con = _con(casa)
    with con:
        mid = _ficha(con, numero)
    con.close()
    return mid


def _criar(casa, mid, cliente=None, **campos):
    c = cliente or casa["cliente"]
    html = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    dados = {"csrf_token": _token(html), "tipo": "AV", "teor": TEOR,
             "numero": 7, "data_ato": "2026-09-15",
             "natureza_titulo": "Alteracao de denominacao",
             "protocolo": "1581"}
    dados.update(campos)
    return c.post(f"/registro-imoveis/{mid}/minuta", data=dados,
                  follow_redirects=True)


# ------------------------------------------ a tela chama a função


def test_a_ficha_oferece_nova_minuta_mesmo_sem_fila(casa):
    """Sem o formulário, a primeira minuta não nasce. Relato: MANUAL órfã."""
    mid = _casa_com_ficha(casa)
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)

    assert "Nova minuta" in html
    assert f'action="/registro-imoveis/{mid}/minuta"' in html
    assert 'name="csrf_token"' in html
    assert 'name="tipo"' in html
    assert 'name="numero"' in html
    assert 'name="data_ato"' in html
    assert 'name="natureza_titulo"' in html
    assert 'name="protocolo"' in html
    assert 'name="teor"' in html
    # Ainda não há fila: o painel só aparece depois de guardar.
    assert "Minutas a revisar e lavrar" not in html


def test_a_tela_e_a_rota_chamam_criar_manual():
    """Varredor: se a porta sumir, MANUAL volta a ser constante sem dono."""
    codigo = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    assert "def ri_minuta_criar" in codigo
    assert "origem=RIMIN.MANUAL" in codigo
    assert "RIMIN.criar" in codigo
    # Não lavra por este caminho: criar devolve o id da minuta, e ninguém
    # aqui insere em ri_atos.
    bloco = codigo[codigo.index("def ri_minuta_criar"):
                   codigo.index("def ri_minuta_guardar")]
    assert "INSERT INTO ri_atos" not in bloco
    assert "marcar_lavrada" not in bloco

    tpl = (RAIZ / "templates" / "ri_ficha.html").read_text(encoding="utf-8")
    assert "ri_minuta_criar" in tpl
    assert "Nova minuta" in tpl
    hm = re.search(r"(?s)\{% block heading %\}(.*?)\{% endblock %\}", tpl)
    assert hm, "block heading ausente"
    assert "Nova minuta" not in hm.group(1)
    assert "ri_minuta_criar" not in hm.group(1)
    assert "<section" not in hm.group(1)
    # O heading do painel da fila não pode morar neste formulário: os testes
    # da lavratura afirmam que ele SOME quando a fila esvazia.
    form = tpl[tpl.index('id="nova-minuta"'):tpl.index('id="novo-ato"')]
    visivel = re.sub(r"\{#.*?#\}", "", form, flags=re.S)
    assert "Minutas a revisar e lavrar" not in visivel


# ------------------------------------------ o POST cria e não lavra


def test_criar_manual_cai_no_painel_e_nao_lavra(casa):
    mid = _casa_com_ficha(casa)
    html = _criar(casa, mid).get_data(as_text=True)

    assert "Minuta na fila de revisão" in html
    assert "Nenhum ato foi lavrado" in html
    assert "Minutas a revisar e lavrar" in html, (
        "a minuta MANUAL tem de aparecer no mesmo painel das importadas")
    assert "Alteracao de denominacao" in html
    assert f"?minuta=" in html, (
        "o botão «Revisar e lavrar» é o que já existia — não uma segunda porta")
    assert "Descartar minuta" in html

    con = _con(casa)
    mi = con.execute("SELECT * FROM ri_minutas WHERE matricula_id=?",
                     (mid,)).fetchone()
    atos = con.execute("SELECT COUNT(*) FROM ri_atos WHERE matricula_id=?",
                       (mid,)).fetchone()[0]
    selos = con.execute("SELECT COUNT(*) FROM sd_selos").fetchone()[0]
    con.close()

    assert mi is not None
    assert mi["origem"] == RIMIN.MANUAL
    assert mi["situacao"] == RIMIN.A_REVISAR
    assert mi["tipo"] == "AV"
    assert mi["numero_pretendido"] == 7
    assert mi["data_pretendida"] == "2026-09-15"
    assert mi["natureza_titulo"] == "Alteracao de denominacao"
    assert mi["protocolo"] == "1581"
    assert "alteração de denominação" in mi["teor"] or "denominacao" in mi["teor"]
    assert mi["ato_id"] is None
    assert mi["criado_por"] == "MARIO EXEMPLO DOS SANTOS"
    assert atos == 0, "criar minuta NAO lavra ato"
    assert selos == 0, "criar minuta NAO pede selo"


def test_numero_pretendido_pode_ficar_em_branco(casa):
    """Não se inventa número. Quem não sabe deixa vazio; o número vem na lavratura."""
    mid = _casa_com_ficha(casa)
    _criar(casa, mid, numero="")
    con = _con(casa)
    mi = con.execute("SELECT numero_pretendido, origem FROM ri_minutas "
                     "WHERE matricula_id=?", (mid,)).fetchone()
    con.close()
    assert mi["numero_pretendido"] is None
    assert mi["origem"] == RIMIN.MANUAL


def test_teor_em_branco_nao_entra(casa):
    mid = _casa_com_ficha(casa)
    html = _criar(casa, mid, teor="   ").get_data(as_text=True)
    assert "não pode ficar em branco" in html
    con = _con(casa)
    n = con.execute("SELECT COUNT(*) FROM ri_minutas WHERE matricula_id=?",
                    (mid,)).fetchone()[0]
    con.close()
    assert n == 0


def test_tipo_que_nao_e_ato_do_ri_nao_entra(casa):
    mid = _casa_com_ficha(casa)
    html = _criar(casa, mid, tipo="X").get_data(as_text=True)
    assert "não é tipo de ato" in html
    con = _con(casa)
    n = con.execute("SELECT COUNT(*) FROM ri_minutas WHERE matricula_id=?",
                    (mid,)).fetchone()[0]
    con.close()
    assert n == 0


def test_ficha_que_nao_existe_da_404(casa):
    mid = _casa_com_ficha(casa)
    c = casa["cliente"]
    html = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    r = c.post("/registro-imoveis/999999/minuta",
               data={"csrf_token": _token(html), "tipo": "AV", "teor": TEOR})
    assert r.status_code == 404


def test_quem_atende_cria_a_minuta(casa):
    mid = _casa_com_ficha(casa)
    _criar(casa, mid, cliente=_entrar(casa["app"], "balcao"))
    con = _con(casa)
    mi = con.execute("SELECT origem, criado_por, situacao FROM ri_minutas "
                     "WHERE matricula_id=?", (mid,)).fetchone()
    con.close()
    assert mi["origem"] == RIMIN.MANUAL
    assert mi["situacao"] == RIMIN.A_REVISAR
    assert mi["criado_por"] == "QUEM ATENDE"


def test_ficha_encerrada_nao_oferece_nova_minuta(casa):
    mid = _casa_com_ficha(casa)
    con = _con(casa)
    with con:
        con.execute(
            """UPDATE ri_matriculas SET encerrada=1, situacao='ENCERRADA',
                   data_encerramento='2026-09-14' WHERE id=?""", (mid,))
    con.close()
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Nova minuta" not in html
    assert f'action="/registro-imoveis/{mid}/minuta"' not in html
