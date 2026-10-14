"""O ATO QUE ENCERRA A FICHA — pedido do oficial em 15/09/2026.

    «deixe tudo pronto para comecar, revisar e encerrar qualquer ato no ri»

O BURACO QUE ISTO FECHA, e ele so apareceu quando as minutas da 3.110
    voltaram para a fila. A AV-06 daquela ficha **e** a averbacao de
    encerramento: o teor dela diz «ENCERRAMENTO DA ESCRITURACAO NO LIVRO E
    TRANSPORTE PARA FICHA».

    Lavra-la pela tela de atos deixava a ficha ABERTA — `ri_lavrar_ato` nao
    mexe nas marcas do encerramento. E fecha-la depois pelo botao «Encerrar
    esta matricula» **lavra outra averbacao**: a ficha terminaria com AV-06 e
    AV-07, as duas dizendo encerramento, e quem a lesse nao saberia qual vale
    — numa ficha que ja foi transportada para outra.

O QUE ESTES TESTES PROTEGEM
    1. O ato encerra a ficha no MESMO passo, sem lavrar um segundo.
    2. A data do encerramento e a do ATO, e nao a de hoje.
    3. A titularidade atual e zerada, como no encerramento pelo botao.
    4. Sem motivo escrito o ato NAO e lavrado — a recusa e antes, e nao depois.
    5. Encerrar e do oficial: quem atende lavra e nao encerra, e a recusa
       derruba o ato inteiro.
    6. O aviso da minuta LEMBRA de marcar, e nao marca sozinho.
    7. O caminho antigo — encerrar pelo botao — continua lavrando a averbacao.
    8. As marcas do encerramento moram num lugar so.
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

TEOR_ENCERRA = ("AV-06/3.110 - ENCERRAMENTO DA ESCRITURACAO NO LIVRO E "
                "TRANSPORTE PARA FICHA. O imovel passa a constar da 4.016.")
TEOR_COMUM = ("AV-04/3.110 - CANCELAMENTO INTEGRAL DE HIPOTECA CEDULAR DE 1o "
              "GRAU, conforme o titulo apresentado.")


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


def _ficha(con, numero="3110"):
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
               tipo_ficha, criado_em)
           VALUES (?, '2-Q', '2-Q', 'ATIVO', 'ACERVO', '2026-09-14T10:27')""",
        (numero,))
    return int(cur.lastrowid)


def _casa_com_minuta(casa, *, teor=TEOR_ENCERRA, numero=6):
    con = _con(casa)
    with con:
        mid = _ficha(con)
        minuta_id = RIMIN.criar(
            con, matricula_id=mid, tipo="AV", teor=teor,
            numero_pretendido=numero, agora="2026-09-15T08:00",
            origem=RIMIN.DESFEITO_DE_ATO, origem_chave="ri_atos:3730 AV-06")
    con.close()
    return mid, minuta_id


def _lavrar_encerrando(casa, mid, minuta_id, *, numero=6, cliente=None,
                       motivo="transporte para a ficha da matricula 4.016",
                       destino="4016", teor=TEOR_ENCERRA, encerra="1"):
    c = cliente or casa["cliente"]
    html = c.get(f"/registro-imoveis/{mid}?minuta={minuta_id}").get_data(
        as_text=True)
    return c.post(f"/registro-imoveis/{mid}/atos",
                  data={"csrf_token": _token(html), "tipo": "AV",
                        "numero": numero, "data_ato": "2026-09-16",
                        "natureza_titulo": "Anuencia para baixa de hipoteca cedular",
                        "codigo_tj": "16.22.2",
                        "teor": teor, "minuta_id": minuta_id,
                        "encerra": encerra, "encerra_motivo": motivo,
                        "encerra_destino": destino,
                        # O CONTRATO MUDOU EM 15/09/2026, e nao por minha mao:
                        # ato cujo selo NAO sai deixou de ser mantido — ele
                        # entra na cadeia e sai marcado como cancelado, a menos
                        # que quem lavra marque a autorizacao expressa.
                        #
                        #   No ensaio nao ha selador configurado, entao o selo
                        #   nunca sai. Sem esta marca, a rota cancelaria o ato
                        #   e voltaria antes do encerramento — e estes testes,
                        #   que sao do ENCERRAMENTO, ficariam medindo o selo.
                        "_removido_lavrar_sem_selo": "0"},
                  follow_redirects=True)


# --------------------------------------------- encerra sem lavrar dois atos


def test_o_ato_encerra_a_ficha_sem_lavrar_uma_segunda_averbacao(casa):
    mid, minuta_id = _casa_com_minuta(casa)
    html = _lavrar_encerrando(casa, mid, minuta_id).get_data(as_text=True)

    con = _con(casa)
    m = con.execute("SELECT * FROM ri_matriculas WHERE id=?", (mid,)).fetchone()
    atos = [dict(r) for r in con.execute(
        "SELECT numero, teor FROM ri_atos WHERE matricula_id=? ORDER BY numero",
        (mid,))]
    mi = con.execute("SELECT situacao FROM ri_minutas WHERE id=?",
                     (minuta_id,)).fetchone()
    con.close()

    assert [a["numero"] for a in atos] == [6], (
        f"o encerramento pelo proprio ato nao pode lavrar um segundo: {atos}")
    assert m["encerrada"] == 1
    assert m["situacao"] == "ENCERRADA"
    assert mi["situacao"] == RIMIN.LAVRADA
    assert "foi ENCERRADA por este ato" in html
    assert "nenhuma averba" in html and "adicional" in html


def test_a_data_do_encerramento_e_a_do_ato(casa):
    """Nao e a de hoje: o que vale e a data em que o ato foi praticado."""
    mid, minuta_id = _casa_com_minuta(casa)
    _lavrar_encerrando(casa, mid, minuta_id)
    con = _con(casa)
    m = con.execute("SELECT * FROM ri_matriculas WHERE id=?", (mid,)).fetchone()
    con.close()
    assert m["data_encerramento"] == "2026-09-16"
    assert "transporte para a ficha" in (m["motivo_encerramento"] or "")
    assert "Destino: 4016." in (m["motivo_encerramento"] or ""), (
        "o destino vai DENTRO do motivo — nao ha coluna propria, medido")


def test_encerrar_pelo_ato_zera_a_titularidade_atual(casa):
    mid, minuta_id = _casa_com_minuta(casa)
    con = _con(casa)
    with con:
        con.execute(
            """INSERT INTO ri_partes (matricula_id, nome, papel, proprietario,
                   proprietario_ativo, origem)
               VALUES (?, 'JOSE DA SILVA', 'proprietario', 1, 1, 'MANUAL')""",
            (mid,))
    con.close()

    _lavrar_encerrando(casa, mid, minuta_id)

    con = _con(casa)
    ativos = con.execute(
        """SELECT COUNT(*) FROM ri_partes
            WHERE matricula_id=? AND proprietario_ativo=1""", (mid,)).fetchone()[0]
    todas = con.execute("SELECT COUNT(*) FROM ri_partes WHERE matricula_id=?",
                        (mid,)).fetchone()[0]
    con.close()
    assert ativos == 0, (
        "ficha encerrada nao tem dono ATUAL — o imovel passou para outra")
    assert todas == 1, "a parte nao se apaga; ela deixa de ser a atual"


def test_a_ficha_encerrada_pelo_ato_esconde_o_balcao(casa):
    mid, minuta_id = _casa_com_minuta(casa)
    _lavrar_encerrando(casa, mid, minuta_id)
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Lavrar novo ato nesta matr" not in html
    assert "Matrícula encerrada em" in html
    # E o caminho de volta continua oferecido.
    assert "Reabrir esta matrícula" in html


# ------------------------------------------------ a recusa vem antes do ato


def test_sem_motivo_o_ato_nao_e_lavrado(casa):
    """Se o ato entrasse e o encerramento falhasse, sobraria uma averbacao de
    encerramento no livro com a ficha aberta — e consertar isso exigiria outra
    averbacao."""
    mid, minuta_id = _casa_com_minuta(casa)
    html = _lavrar_encerrando(casa, mid, minuta_id, motivo="curto").get_data(
        as_text=True)
    assert "escreva o motivo do encerramento" in html.lower()

    con = _con(casa)
    quantos = con.execute("SELECT COUNT(*) FROM ri_atos WHERE matricula_id=?",
                          (mid,)).fetchone()[0]
    m = con.execute("SELECT encerrada FROM ri_matriculas WHERE id=?",
                    (mid,)).fetchone()
    mi = con.execute("SELECT situacao FROM ri_minutas WHERE id=?",
                     (minuta_id,)).fetchone()
    con.close()
    assert quantos == 0, "ato nao entra quando o encerramento e recusado"
    assert not m["encerrada"]
    assert mi["situacao"] == RIMIN.A_REVISAR, "e a minuta continua na fila"


def test_quem_atende_lavra_mas_nao_encerra(casa):
    """Encerrar e do oficial, e a guarda e por ACAO — a rota aceita USER."""
    mid, minuta_id = _casa_com_minuta(casa)
    balcao = _entrar(casa["app"], "balcao")
    ficha = balcao.get(f"/registro-imoveis/{mid}?minuta={minuta_id}").get_data(
        as_text=True)
    assert 'name="encerra"' not in ficha, (
        "quem nao pode encerrar tambem nao ve a caixa")

    html = _lavrar_encerrando(casa, mid, minuta_id,
                              cliente=balcao).get_data(as_text=True)
    assert "do oficial" in html

    con = _con(casa)
    quantos = con.execute("SELECT COUNT(*) FROM ri_atos WHERE matricula_id=?",
                          (mid,)).fetchone()[0]
    m = con.execute("SELECT encerrada FROM ri_matriculas WHERE id=?",
                    (mid,)).fetchone()
    con.close()
    assert quantos == 0, (
        "recusar o encerramento recusa o ato inteiro — lavrar metade do que "
        "foi pedido e pior que nao lavrar")
    assert not m["encerrada"]


def test_quem_atende_lavra_normalmente_sem_a_marca(casa):
    """A guarda e da MARCA, e nao da rota: o balcao continua lavrando."""
    mid, minuta_id = _casa_com_minuta(casa, teor=TEOR_COMUM, numero=4)
    balcao = _entrar(casa["app"], "balcao")
    _lavrar_encerrando(casa, mid, minuta_id, numero=4, cliente=balcao,
                       teor=TEOR_COMUM, encerra="", motivo="", destino="")
    con = _con(casa)
    quantos = con.execute("SELECT COUNT(*) FROM ri_atos WHERE matricula_id=?",
                          (mid,)).fetchone()[0]
    m = con.execute("SELECT encerrada FROM ri_matriculas WHERE id=?",
                    (mid,)).fetchone()
    con.close()
    assert quantos == 1
    assert not m["encerrada"]


# ------------------------------------------------- o aviso lembra, nao decide


def test_a_minuta_de_encerramento_avisa_para_marcar_a_caixa(casa):
    mid, minuta_id = _casa_com_minuta(casa)
    html = casa["cliente"].get(
        f"/registro-imoveis/{mid}?minuta={minuta_id}").get_data(as_text=True)
    assert "fala de ENCERRAMENTO" in html
    # A caixa continua DESMARCADA — o aviso lembra, nao decide. Fechar uma
    # ficha por causa de uma palavra no texto seria a maquina decidindo o ato.
    assert 'name="encerra" value="1"' in html
    assert "checked" not in html.split('name="encerra"')[1][:120]


def test_minuta_comum_nao_recebe_o_aviso(casa):
    mid, minuta_id = _casa_com_minuta(casa, teor=TEOR_COMUM, numero=4)
    html = casa["cliente"].get(
        f"/registro-imoveis/{mid}?minuta={minuta_id}").get_data(as_text=True)
    assert "fala de ENCERRAMENTO" not in html


# ------------------------------------------- o caminho antigo nao muda


def test_encerrar_pelo_botao_continua_lavrando_a_averbacao(casa):
    con = _con(casa)
    with con:
        mid = _ficha(con, numero="4018")
    con.close()
    c = casa["cliente"]
    html = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    c.post(f"/registro-imoveis/{mid}/encerrar",
           data={"csrf_token": _token(html), "motivo": "unificacao",
                 "destino": "4019"}, follow_redirects=True)

    con = _con(casa)
    atos = [dict(r) for r in con.execute(
        "SELECT numero, teor FROM ri_atos WHERE matricula_id=?", (mid,))]
    m = con.execute("SELECT * FROM ri_matriculas WHERE id=?", (mid,)).fetchone()
    con.close()
    assert len(atos) == 1
    assert "ENCERRAMENTO DESTA MATR" in atos[0]["teor"]
    assert m["encerrada"] == 1
    assert "Destino: 4019." in (m["motivo_encerramento"] or "")


def test_as_marcas_do_encerramento_moram_num_lugar_so():
    """Duas copias divergiriam, e aqui a divergencia e caríssima.

    Ficha que diz `encerrada=0` com um ato de encerramento no livro aceita
    registro novo sobre imovel que ja foi transportado.
    """
    codigo = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    escrevem = re.findall(r"SET encerrada=1", codigo)
    # Duas: `_marcar_a_ficha_encerrada` e o RE-encerramento, que so religa a
    # marca (nao grava motivo nem data, porque eles ja estao no livro).
    assert len(escrevem) == 2, (
        f"{len(escrevem)} lugares escrevem as marcas do encerramento. A "
        f"funcao e `_marcar_a_ficha_encerrada`; o segundo caso e o "
        f"re-encerramento de uma ficha reaberta.")
