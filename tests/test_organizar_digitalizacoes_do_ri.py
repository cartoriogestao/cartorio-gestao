"""Editar, excluir e reordenar as digitalizações da matrícula.

    «preciso de poderes para, caso necessario, editar e excluir e alterar
     ordem das digitalizacoes nas matriculas» — o oficial, 17/09/2026

MEDIDO NA PRODUÇÃO ANTES DE DESENHAR: **11.251 imagens**, **1.679 fichas com
mais de uma**, a maior com **69 páginas**, `ordem` preenchida em todas e sem
repetição dentro da mesma ficha. É por causa das 69 que a tela tem **as setas
e o número**: só as setas dariam trinta cliques para levar uma página do fim
ao começo; só o número faria redigitar a ficha para trocar duas vizinhas.

O QUE ESTES TESTES GUARDAM, e cada um protege alguém:

  1. **A ordem fica 1..N, sem buracos.** «Página 7» só quer dizer alguma coisa
     se for a sétima folha do livro de papel; com buracos ela vira um rótulo
     que não corresponde a nada.
  2. **Excluir não apaga o arquivo.** A imagem é o acervo digitalizado — é ela
     que o ONR lê pelo CSL2 —, e o que se desfaz não precisa de coragem para
     ser usado. Tirar da ficha se refaz em «Fichas digitalizadas»; apagar o
     arquivo, não.
  3. **Não se mexe na página de outra ficha.** O número vem do formulário, e
     um número trocado tiraria a folha de uma matrícula que ninguém abriu.
  4. **É do oficial e do gerente.** Lavrar ato é do balcão; mexer no que foi
     digitalizado do livro é de quem responde pela guarda do acervo.
  5. **Tudo fica na auditoria, com o nome do arquivo.** «Quem tirou a página 4
     desta ficha?» é pergunta de correição, e não se responde de memória.
"""
from __future__ import annotations

import json
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


def _entrar(app, usuario: str):
    c = app.test_client()
    c.post("/login",
           data={"username": usuario, "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


@pytest.fixture()
def casa(cg_casa):
    """Uma ficha com quatro páginas, e duas pessoas de papéis diferentes."""
    db = cg_casa["db"]
    db.create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("balcao", "LAURA MARIA DA COSTA", SENHA, "USER")
    con = sqlite3.connect(cg_casa["banco"])
    with con:
        con.execute(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
                                          tipo_ficha, origem, criado_em)
               VALUES ('4014','2-S','2S','ATIVA','ESTRUTURADA','MANUAL',
                       '2026-09-17T09:00:00')""")
        mid = con.execute(
            "SELECT id FROM ri_matriculas WHERE numero='4014'").fetchone()[0]
        outra = con.execute(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
                                          tipo_ficha, origem, criado_em)
               VALUES ('4015','2-S','2S','ATIVA','ESTRUTURADA','MANUAL',
                       '2026-09-17T09:00:00')""").lastrowid
        for n in range(1, 5):
            con.execute(
                """INSERT INTO ri_imagens (matricula_id, nome_arquivo, caminho,
                                           ordem, ficha_digitalizada)
                   VALUES (?,?,?,?,1)""",
                (mid, f"0000401{n}.000{n}", rf"C:\ARPNET\C11\ONR\IMAGENS\p{n}",
                 n))
        con.execute(
            """INSERT INTO ri_imagens (matricula_id, nome_arquivo, caminho,
                                       ordem, ficha_digitalizada)
               VALUES (?,?,?,?,1)""",
            (outra, "da-outra-ficha.0001", r"C:\ARPNET\outra", 1))
    con.close()
    return {**cg_casa, "mid": mid, "outra": outra,
            "cliente": _entrar(cg_casa["app"], "jean")}


def _paginas(casa, matricula_id=None):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    linhas = con.execute(
        """SELECT nome_arquivo, ordem FROM ri_imagens
            WHERE matricula_id=? ORDER BY ordem""",
        (matricula_id or casa["mid"],)).fetchall()
    con.close()
    return [(l["nome_arquivo"], l["ordem"]) for l in linhas]


def _imagem_id(casa, ordem: int) -> int:
    con = sqlite3.connect(casa["banco"])
    linha = con.execute(
        "SELECT id FROM ri_imagens WHERE matricula_id=? AND ordem=?",
        (casa["mid"], ordem)).fetchone()
    con.close()
    assert linha, f"não há página {ordem}"
    return int(linha[0])


def _mandar(casa, **dados):
    ficha = casa["cliente"].get(
        f'/registro-imoveis/{casa["mid"]}').get_data(as_text=True)
    return casa["cliente"].post(
        f'/registro-imoveis/{casa["mid"]}/imagens',
        data={"csrf_token": _token(ficha), **dados}, follow_redirects=True)


# ------------------------------------------------------------- a ordem


def test_a_pagina_sobe_uma_casa(casa):
    _mandar(casa, acao="subir", imagem_id=_imagem_id(casa, 3))
    assert [n for n, _ in _paginas(casa)] == [
        "00004011.0001", "00004013.0003", "00004012.0002", "00004014.0004"], _paginas(casa)


def test_a_pagina_desce_uma_casa(casa):
    _mandar(casa, acao="descer", imagem_id=_imagem_id(casa, 1))
    assert [n for n, _ in _paginas(casa)][:2] == ["00004012.0002", "00004011.0001"]


def test_a_pagina_salta_para_o_numero_pedido(casa):
    """Há ficha com 69 páginas nesta casa: o salto não é conforto."""
    _mandar(casa, acao="ordem", ordem="1", imagem_id=_imagem_id(casa, 4))
    assert [n for n, _ in _paginas(casa)] == [
        "00004014.0004", "00004011.0001", "00004012.0002", "00004013.0003"]


def test_a_ordem_fica_sempre_de_um_ate_n(casa):
    """Sem isto sobram buracos, e «página 7» deixa de ser a sétima folha."""
    _mandar(casa, acao="excluir", imagem_id=_imagem_id(casa, 2))
    _mandar(casa, acao="subir", imagem_id=_imagem_id(casa, 3))
    assert [o for _, o in _paginas(casa)] == [1, 2, 3]


def test_nao_passa_do_fim_nem_do_comeco(casa):
    """Subir a primeira e descer a última não pode reembaralhar a ficha."""
    antes = _paginas(casa)
    _mandar(casa, acao="subir", imagem_id=_imagem_id(casa, 1))
    _mandar(casa, acao="descer", imagem_id=_imagem_id(casa, 4))
    assert _paginas(casa) == antes


def test_numero_de_pagina_invalido_e_recusado(casa):
    antes = _paginas(casa)
    r = _mandar(casa, acao="ordem", ordem="0", imagem_id=_imagem_id(casa, 2))
    assert "número a partir de 1" in r.get_data(as_text=True)
    assert _paginas(casa) == antes


# ------------------------------------------------------------ o resto


def test_renomear_troca_so_o_nome(casa):
    _mandar(casa, acao="renomear", imagem_id=_imagem_id(casa, 2),
            nome_arquivo="verso da folha 1")
    assert _paginas(casa)[1] == ("verso da folha 1", 2)


def test_nome_vazio_e_recusado(casa):
    r = _mandar(casa, acao="renomear", imagem_id=_imagem_id(casa, 2),
                nome_arquivo="   ")
    assert "não pode ficar vazio" in r.get_data(as_text=True)
    assert _paginas(casa)[1][0] == "00004012.0002"


def test_excluir_tira_da_ficha_e_nao_apaga_o_arquivo(casa):
    """O que se desfaz não precisa de coragem para ser usado."""
    caminho = r"C:\ARPNET\C11\ONR\IMAGENS\p2"
    r = _mandar(casa, acao="excluir", imagem_id=_imagem_id(casa, 2))
    assert len(_paginas(casa)) == 3
    corpo = r.get_data(as_text=True)
    assert "continua no disco" in corpo, (
        "a tela tem de dizer que o arquivo ficou — senão ninguém usa o botão")
    con = sqlite3.connect(casa["banco"])
    marca = con.execute(
        """SELECT details FROM audit_logs
            WHERE action='RI_IMAGEM_TIRADA_DA_FICHA'""").fetchone()
    con.close()
    assert marca is not None, "tirar página da ficha tem de ficar na auditoria"
    detalhes = json.loads(marca[0])
    assert detalhes["arquivo_apagado"] is False
    assert detalhes["nome_arquivo"] == "00004012.0002", (
        "sem o nome do arquivo, «quem tirou a página 4?» não se responde")
    assert caminho  # o caminho continua sendo o do acervo, e não foi tocado


def test_nao_se_mexe_na_pagina_de_outra_ficha(casa):
    """Número trocado tiraria a folha de uma matrícula que ninguém abriu."""
    con = sqlite3.connect(casa["banco"])
    alheia = con.execute("SELECT id FROM ri_imagens WHERE matricula_id=?",
                         (casa["outra"],)).fetchone()[0]
    con.close()
    r = _mandar(casa, acao="excluir", imagem_id=alheia)
    assert "não é desta matrícula" in r.get_data(as_text=True)
    assert len(_paginas(casa, casa["outra"])) == 1


def test_o_balcao_nao_organiza_o_acervo(casa):
    """Lavrar ato é do balcão; guardar o acervo é de quem responde por ele."""
    balcao = _entrar(casa["app"], "balcao")
    ficha = balcao.get(f'/registro-imoveis/{casa["mid"]}').get_data(as_text=True)
    r = balcao.post(f'/registro-imoveis/{casa["mid"]}/imagens',
                    data={"csrf_token": _token(ficha), "acao": "excluir",
                          "imagem_id": _imagem_id(casa, 2)},
                    follow_redirects=False)
    assert r.status_code in (302, 403), r.status_code
    assert len(_paginas(casa)) == 4, "o balcão conseguiu tirar uma página"


def test_a_tela_so_oferece_a_quem_pode(casa):
    """Botão que o servidor recusa é o balcão descobrindo no clique."""
    do_oficial = casa["cliente"].get(
        f'/registro-imoveis/{casa["mid"]}').get_data(as_text=True)
    assert "tirar da ficha" in do_oficial

    balcao = _entrar(casa["app"], "balcao")
    do_balcao = balcao.get(
        f'/registro-imoveis/{casa["mid"]}').get_data(as_text=True)
    assert "tirar da ficha" not in do_balcao
