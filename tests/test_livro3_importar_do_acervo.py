"""A porta do Livro 3 para o acervo — 18/09/2026.

O PEDIDO
    «preciso que tenha campo para importar do acervo registro do livro 3 do RI,
    igual temos no livro 2» — o oficial, 18/09/2026.

    O Livro 2 tem a porta «Importações» na lista das matrículas desde sempre. O
    Livro 3 só oferecia o registro manual, um de cada vez: medido na produção no
    mesmo dia, havia **14 registros, 16 atos e ZERO partes** — as 25 partes de
    `LivroAuxiliarPartes` e as 5 averbações de `LivroAuxiliarAverbacao` ficaram
    no acervo, e a ficha do Livro 3 abria sem emitente e sem credor.

O QUE ESTES TESTES GUARDAM, E POR QUE CADA UM EXISTE
    - a tela abre, e DIZ que não achou o acervo quando não achou — ausência com
      cara de medição é o defeito silencioso desta família de telas;
    - o CAMPO do acervo funciona: aponta para outro arquivo e a prévia é a dele;
    - conferir NÃO grava, e importar é repetível (o que já está não entra de
      novo) — aqui não há como desfazer, porque acervo importado vira o livro;
    - a prévia conta o que NÃO vai entrar (parte que o `tbOrtoga` não resolve)
      em vez de dizer «0» com cara de tudo certo;
    - a porta aparece na lista do Livro 3 e nas Importações do RI;
    - USER não entra: é carga, e carga não é do balcão.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import acervo_carga as AC                                # noqa: E402

SENHA = "Senha#12345"
TELA = "/livro3/importar-do-acervo"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _sessao(cg_casa, papel: str = "ADMIN"):
    """O molde de `test_rcpn_importar_acervo.py`: app + client logado."""
    app = cg_casa["app"]
    cg_casa["db"].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                              SENHA, papel)
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": cg_casa["banco"],
            "dados": cg_casa["dados"]}


@pytest.fixture()
def s(cg_casa):
    return _sessao(cg_casa)


def _acervo_no_disco(destino: Path) -> Path:
    """Escreve no disco o acervo de ensaio do Livro 3 (o mesmo do domínio).

    O acervo de ensaio é o de `test_livro3_do_acervo.py` — duas cédulas, seis
    linhas de parte (uma aponta para pessoa que o `tbOrtoga` não conhece) e duas
    averbações. Aqui ele vira ARQUIVO, que é o que a tela lê pelo campo.
    """
    from tests.test_livro3_do_acervo import acervo_falso
    origem = acervo_falso()
    con = sqlite3.connect(destino)
    try:
        origem.backup(con)
    finally:
        con.close()
        origem.close()
    return destino


def _contar(banco: Path, tabela: str) -> int:
    con = sqlite3.connect(banco)
    try:
        return con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
    finally:
        con.close()


# ------------------------------------------------------------------ a tela


def test_a_tela_abre_e_diz_que_o_acervo_nao_esta_la(s):
    """Sem acervo, a tela ABRE e diz que não achou — não fica muda."""
    html = s["c"].get(TELA).get_data(as_text=True)
    assert "Caminho do acervo" in html
    assert "O acervo não está nesse caminho" in html
    assert "RCPN" in html          # diz ONDE carregar o arquivo


def test_o_escrevente_abre_a_carga(cg_casa):
    """A carga era só de ADMIN e MANAGER; a 3.6.160 (21/09/2026) abriu-a ao
    perfil USER, e o oficial confirmou em 11/10/2026: «manter abertas»."""
    sessao = _sessao(cg_casa, papel="USER")
    assert sessao["c"].get(TELA).status_code == 200


# ----------------------------------------------------------------- o campo


def test_o_campo_aceita_outro_caminho_e_a_previa_e_a_daquele_arquivo(s, tmp_path):
    """O CAMPO é a razão de a tela existir: aponta para outro acervo."""
    outro = _acervo_no_disco(tmp_path / "copia_de_outra_maquina.sqlite3")
    c = s["c"]
    html = c.post(TELA, data={"csrf_token": _token(c.get(TELA).get_data(as_text=True)),
                              "o_que": "conferir", "caminho": str(outro)},
                  follow_redirects=True).get_data(as_text=True)
    assert "nº 1549" in html                    # amostra do que entraria
    assert "Importar os 9 que faltam" in html   # 2 registros + 2 av + 5 partes
    # E CONFERIR NÃO GRAVOU NADA.
    assert _contar(s["banco"], "ra_registros") == 0
    assert _contar(s["banco"], "ra_partes") == 0


def test_caminho_errado_nao_derruba_a_tela(s):
    html = s["c"].post(TELA, data={"csrf_token": _token(s["c"].get(TELA).get_data(as_text=True)),
                                   "o_que": "conferir",
                                   "caminho": r"C:\nao\existe\acervo.sqlite3"},
                       follow_redirects=True).get_data(as_text=True)
    assert "Não achei o acervo" in html
    assert "O acervo não está nesse caminho" in html


# ------------------------------------------------- a prévia e a importação


def test_a_previa_vem_no_get_e_conta_o_que_nao_vai_entrar(s):
    _acervo_no_disco(Path(s["app"].config["DATA_DIR"]) / AC.NOME_ACERVO)
    html = s["c"].get(TELA).get_data(as_text=True)
    assert "A prévia" in html
    assert "registros no acervo" in html
    assert "averbações novas" in html
    assert "partes a importar" in html
    # O QUE NÃO ENTRA É CONTADO: a sexta parte aponta para pessoa que o
    # `tbOrtoga` não conhece, e o `tbPessoa` do mesmo id é OUTRA pessoa.
    assert "não resolve" in html
    assert "partes sem pessoa (não entram)" in html
    # O BOTÃO CONTA SÓ O QUE ENTRA: 2 registros + 2 averbações + 5 partes =
    # 9. A sexta parte fica de fora, e por isso não são 10.
    assert "Importar os 9 que faltam" in html
    # A PRÉVIA NÃO GRAVOU NADA.
    assert _contar(s["banco"], "ra_registros") == 0
    assert _contar(s["banco"], "ra_partes") == 0


def test_importar_traz_o_registro_as_partes_e_a_averbacao(s):
    """O que faltava: as partes e as averbações, e não só o registro."""
    _acervo_no_disco(Path(s["app"].config["DATA_DIR"]) / AC.NOME_ACERVO)
    c = s["c"]
    html = c.post(TELA, data={"csrf_token": _token(c.get(TELA).get_data(as_text=True)),
                              "o_que": "importar"},
                  follow_redirects=True).get_data(as_text=True)
    assert "Livro 3 do acervo:" in html
    assert "O que a importação fez" in html
    assert _contar(s["banco"], "ra_registros") == 2
    # 5 partes do registro (uma não resolve no `tbOrtoga`) + a da averbação.
    assert _contar(s["banco"], "ra_partes") == 6
    # O ato R-1 de cada registro + uma averbação em cada um.
    assert _contar(s["banco"], "ra_atos") == 4


def test_importar_de_novo_nao_duplica_nada(s):
    """A carga é repetível: acervo importado vira o livro, e não há desfazer."""
    _acervo_no_disco(Path(s["app"].config["DATA_DIR"]) / AC.NOME_ACERVO)
    c = s["c"]
    c.post(TELA, data={"csrf_token": _token(c.get(TELA).get_data(as_text=True)),
                       "o_que": "importar"}, follow_redirects=True)
    antes = tuple(_contar(s["banco"], t)
                  for t in ("ra_registros", "ra_partes", "ra_atos"))
    html = c.post(TELA, data={"csrf_token": _token(c.get(TELA).get_data(as_text=True)),
                              "o_que": "importar"},
                  follow_redirects=True).get_data(as_text=True)
    depois = tuple(_contar(s["banco"], t)
                   for t in ("ra_registros", "ra_partes", "ra_atos"))
    assert antes == depois
    # E a tela diz que não entrou nada, em vez de dizer que importou.
    assert "Nada novo para importar" in html


# ------------------------------------------------------------- as duas portas


def test_a_lista_do_livro_3_tem_as_duas_portas(s):
    """O mesmo desenho do RCPN: o lote do acervo e o registro digitado."""
    html = s["c"].get("/livro3").get_data(as_text=True)
    assert "Entrar com registro" in html
    assert "Importar do acervo" in html
    assert TELA in html
    assert "manual/LIVRO3_REGISTRO" in html


def test_as_importacoes_do_ri_levam_ao_livro_3(s):
    html = s["c"].get("/registro-imoveis/importacoes").get_data(as_text=True)
    assert TELA in html
    assert "Livro 3" in html
    assert "não traz o Livro 3" in html


def test_a_lista_do_livro_3_aponta_a_carga_quando_esta_vazia(s):
    html = s["c"].get("/livro3").get_data(as_text=True)
    assert "Nada aqui" in html
    assert "Importar do acervo" in html
