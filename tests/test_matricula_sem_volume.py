"""Ficha nova não vai para volume de papel.

Decisão do oficial em 27/08/2026, corrigindo o próprio pedido anterior:

  «Sobre a questão do protocolo, é livro 1 mesmo, falha minha. A ideia do meu
   pedido era que não trabalhássemos com livros como 2-S se estamos com sistema
   de fichas indefinido. Nesse sistema, não faz sentido livro 2-S.»

O QUE A MEDIÇÃO MOSTROU
    Há **20 volumes** de Livro 2 no banco, com os números **entrelaçados**: o
    2S vai de 8 a 4013, o 2A de 1 a 713, o 2C de 209 a 2667. Não são vinte
    séries — é UMA sequência da serventia, repartida em livros de papel
    conforme foram sendo escritos. Só **um** número se repete em 1.701
    matrículas, e é o defeito de 18/08/2026.

    A escolha de volume na tela de abrir matrícula era pior que inútil: vinte
    opções que devolvem todas o MESMO número (4014, conferido uma a uma), com a
    única diferença de carimbar no registro novo o nome de um livro fechado há
    décadas.

O QUE NÃO MUDOU, E POR QUÊ
    O volume das 1.701 matrículas do acervo **fica**. Ali ele é informação
    real: diz em que volume a ficha de papel está guardada, e quem for à
    estante precisa dela.

UM ENGANO MEU, QUE VALE FICAR REGISTRADO
    Lendo `ri_numeracao` crua — 20 linhas com `proximo_numero` diferentes —
    concluí que escolher `2A` abriria a matrícula 714, e cheguei a dizer isso
    ao oficial. **Não abriria**: `proximo_numero()` conta pela série e devolve
    4014 para qualquer volume. As 20 linhas são sobras da importação de
    13/08/2026, e nada as usa.

    Dado cru não é resposta: a resposta é o que a função devolve.
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


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    c = cg_casa["cliente"]
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _acervo_com_volumes(casa):
    """O acervo desta casa em miniatura: uma sequência, três volumes."""
    con = _con(casa)
    with con:
        for numero, volume in ((1, "2-A"), (713, "2A"), (2667, "2-C"),
                               (4013, "2S")):
            con.execute(
                """INSERT INTO ri_matriculas (numero, livro, livro_norm,
                       situacao, origem, criado_em)
                   VALUES (?,?,?, 'ATIVA', 'EOFICIO', '2020-01-01T00:00:00')""",
                (str(numero), volume, volume.replace("-", "")))
        # E as sobras do contador por volume, como a importação as deixou.
        for volume, proximo in (("2", 4012), ("2A", 714), ("2C", 2668),
                                ("2S", 4014)):
            con.execute(
                """INSERT INTO ri_numeracao (livro, proximo_numero, maior_em_uso,
                       fixado_em, observacao)
                   VALUES (?,?,?, '2026-08-13T16:56:54', 'importação')""",
                (volume, proximo, proximo - 1))


def _abrir(casa, **extra):
    html = casa["cliente"].get("/registro-imoveis/nova").get_data(as_text=True)
    dados = {"csrf_token": _token(html), "logradouro": "RUA DAS FLORES"}
    dados.update(extra)
    return casa["cliente"].post("/registro-imoveis/nova", data=dados,
                                follow_redirects=True)


# ------------------------------------------------- a tela não pede volume


def test_a_tela_nao_pede_volume(casa):
    _acervo_com_volumes(casa)
    html = casa["cliente"].get("/registro-imoveis/nova").get_data(as_text=True)
    corpo = html[html.find("</nav>"):]
    assert 'name="livro"' not in corpo, (
        "a escolha de volume voltou — eram vinte opções para o mesmo número")


def test_a_tela_diz_o_numero_que_vai_sair(casa):
    """Número que só aparece depois de gravar é número que ninguém confere."""
    _acervo_com_volumes(casa)
    html = casa["cliente"].get("/registro-imoveis/nova").get_data(as_text=True)
    assert "4014" in html
    assert "Livro 2" in html


# ------------------------------------------- a matrícula nova nasce na série


def test_a_matricula_nova_entra_na_serie_e_sem_volume(casa):
    _acervo_com_volumes(casa)
    _abrir(casa)
    nova = _con(casa).execute(
        "SELECT * FROM ri_matriculas ORDER BY id DESC LIMIT 1").fetchone()
    assert nova["numero"] == "4014"
    assert nova["livro"] == "2", "a ficha nova foi carimbada com volume de papel"


def test_o_numero_e_da_serventia_e_nao_do_volume(casa):
    """Duas matrículas seguidas continuam a sequência da casa."""
    _acervo_com_volumes(casa)
    _abrir(casa)
    _abrir(casa)
    numeros = [r["numero"] for r in _con(casa).execute(
        "SELECT numero FROM ri_matriculas ORDER BY id DESC LIMIT 2")]
    assert numeros == ["4015", "4014"]


def test_o_volume_do_acervo_continua_onde_estava(casa):
    """Ele diz em que livro de papel a ficha está guardada — é informação real."""
    _acervo_com_volumes(casa)
    _abrir(casa)
    antigas = _con(casa).execute(
        "SELECT livro FROM ri_matriculas WHERE origem='EOFICIO'").fetchall()
    assert sorted(r["livro"] for r in antigas) == ["2-A", "2-C", "2A", "2S"]


# ----------------------------------- o contador conta pela série, e sempre contou


def test_qualquer_volume_devolve_o_mesmo_proximo(casa):
    """As 20 linhas do contador são sobras; quem responde é a função.

    Foi lendo a coluna crua que eu concluí — e disse ao oficial — que escolher
    `2A` abriria a matrícula 714. Não abriria.
    """
    import ri_correcoes as RC
    _acervo_com_volumes(casa)
    con = _con(casa)
    for volume in ("2", "2A", "2C", "2S", "2-A"):
        assert RC.proximo_numero(con, volume) == 4014, (
            f"o volume {volume} devolveu número próprio — a numeração voltou a "
            f"ser por volume, que é o defeito de 18/08/2026")


def test_a_tela_de_numeracao_mostra_a_serie_antes_dos_volumes(casa):
    """Tela que mostra só o dado cru deixa quem lê concluir errado sozinho."""
    _acervo_com_volumes(casa)
    html = casa["cliente"].get(
        "/registro-imoveis/numeracao").get_data(as_text=True)
    assert "O que vale — a série" in html
    assert "volume(s) no acervo" in html
    # E o quadro da série vem ANTES do dos volumes.
    assert html.index("O que vale") < html.index("como o acervo os guardou")
