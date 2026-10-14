"""
Testes da ABA do que so o oficial pode informar, e do AVISO dela.

POR QUE ELES EXISTEM
    O pedido do oficial, em 26/08/2026, foi exatamente este: "crie um aviso no
    sistema para atualizar e disponibilize uma aba para incluir depois". As
    duas metades sao testadas aqui — a aba e o aviso —, porque **documentacao
    nao avisa ninguem** e aba sem aviso e aba que ninguem abre.

    O AVISO APARECE EM QUALQUER TELA, e nao numa so. Aviso raro que mora num
    canto e aviso que ninguem ve — e este e o que trava o balcao quando o
    sistema voltar.
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

# O PEDACO DO AVISO QUE CABE NUMA LINHA do template. Procurar a frase inteira
# quebrava aqui porque o template a parte em duas — e o teste falhava por
# formatacao, e nao por regra.
AVISO = "coisa(s) esperando você"


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


def declarar(s):
    """Roda o que a carga roda no fim — é quem declara as pendências."""
    import acervo_carga as AC
    from database import Database

    db = Database(s["banco"])
    with db.transaction() as con:
        con.row_factory = sqlite3.Row
        AC.semear_numeracao(con, agora=db.now(), usuario="carga")


def informar(s, chave: str, **extra):
    tela = s["c"].get("/implantacao").get_data(as_text=True)
    dados = {"csrf_token": _token(tela)}
    dados.update(extra)
    return s["c"].post(f"/implantacao/{chave}/informar", data=dados,
                       follow_redirects=True)


# ------------------------------------------------------------- a aba


def test_a_aba_abre_e_diz_para_que_serve(s):
    html = s["c"].get("/implantacao").get_data(as_text=True)
    assert "O que falta você informar" in html
    assert "seis atribuições" in html
    # Sistema novo: a lista é vazia, e a tela DIZ por quê em vez de só mostrar
    # nada.
    assert "Nenhuma pendência aberta" in html
    assert "não soube informar sozinha" in html


def test_a_aba_esta_no_menu(s):
    html = s["c"].get("/").get_data(as_text=True)
    assert "/implantacao" in html


def test_a_aba_lista_por_atribuicao_com_o_motivo(s):
    declarar(s)
    html = s["c"].get("/implantacao").get_data(as_text=True)
    assert "Protesto" in html and "Registro Civil" in html
    assert "Livro de Registro de Protestos" in html
    assert "Livro D" in html                    # proclamas, do RCPN
    # Cada linha diz POR QUE ninguém mais sabe e O QUE acontece sem resposta.
    assert "livro físico" in html
    assert "número 1" in html


# ------------------------------------------------------------- o aviso


def test_o_aviso_NAO_aparece_em_sistema_novo(s):
    # Aviso que soa em sistema vazio é aviso que ninguém ouve.
    html = s["c"].get("/").get_data(as_text=True)
    assert AVISO not in html


def test_o_aviso_aparece_em_QUALQUER_tela(s):
    declarar(s)
    for caminho in ("/", "/protesto/titulos", "/nucleo/livros"):
        html = s["c"].get(caminho).get_data(as_text=True)
        assert AVISO in html, caminho
        assert "/implantacao" in html


def test_o_aviso_compacto_expande_os_detalhes(s):
    declarar(s)
    html = s["c"].get("/").get_data(as_text=True)
    assert "flash-compact" in html
    assert "Ver implantação" in html
    assert 'data-aviso-expand' in html
    assert 'aria-expanded="false"' in html
    assert 'id="aviso-implantacao-detalhe"' in html
    assert "flash-compact-detalhe" in html
    assert re.search(r"livro\s+físico", html)
    assert "número 1" in html
    linha = re.search(
        r'<div class="flash-compact-linha">.*?</div>', html, re.DOTALL)
    assert linha, "a linha compacta do aviso sumiu"
    trecho = linha.group(0)
    assert not re.search(r"livro\s+físico", trecho)
    assert "número 1" not in trecho
    assert "antes de o balcão andar" not in trecho.lower()


def test_o_aviso_some_quando_tudo_for_respondido(s):
    declarar(s)
    assert AVISO in s["c"].get("/").get_data(as_text=True)
    con = _con(s)
    chaves = [r["chave"] for r in con.execute(
        "SELECT chave FROM nu_implantacao WHERE situacao='ABERTA'")]
    for chave in chaves:
        informar(s, chave, acao="dispensar",
                 motivo="conferido com o oficial nesta data")
    html = s["c"].get("/").get_data(as_text=True)
    assert AVISO not in html


def test_o_aviso_e_de_quem_responde_pela_serventia(cg_casa):
    # Informar o número de um livro é decisão de quem responde pela serventia,
    # e não do balcão.
    s = _sessao(cg_casa, papel="AUDITOR")
    declarar(s)
    html = s["c"].get("/").get_data(as_text=True)
    assert AVISO not in html
    assert s["c"].post("/implantacao/x/informar").status_code in (302, 403, 400)


# ---------------------------------------------------------- informar


def test_informar_o_numero_pela_aba(s):
    declarar(s)
    html = informar(s, "numeracao:PT_PROTESTO", acao="informar", proximo="2157",
                    observacao="conferido no Livro 9, folha 200"
                    ).get_data(as_text=True)
    assert "passa a ser 2157" in html

    con = _con(s)
    assert con.execute("SELECT proximo FROM nu_numeracao WHERE serie='PT_PROTESTO'"
                       ).fetchone()[0] == 2157
    p = con.execute("SELECT * FROM nu_implantacao WHERE chave='numeracao:PT_PROTESTO'"
                    ).fetchone()
    assert p["situacao"] == "RESOLVIDA" and p["valor"] == "2157"
    assert p["resolvida_por"] == "MARIO EXEMPLO DOS SANTOS"
    # E ela sai da lista de abertas, mas aparece nas respondidas.
    tela = s["c"].get("/implantacao").get_data(as_text=True)
    assert "Já respondidas" in tela and "Livro 9, folha 200" in tela


def test_registrar_a_decisao_pela_aba(s):
    declarar(s)
    import implantacao as IMP
    chave = IMP.CATALOGO_DE_DECISOES[0]["chave"]
    html = informar(s, chave, acao="informar",
                    observacao="encerrei o Livro 6 com termo de que nada foi "
                               "lançado").get_data(as_text=True)
    assert "Decisão registrada" in html
    assert _con(s).execute(
        "SELECT situacao FROM nu_implantacao WHERE chave=?",
        (chave,)).fetchone()[0] == "RESOLVIDA"


def test_dispensar_sem_motivo_avisa_e_nao_grava(s):
    declarar(s)
    html = informar(s, "numeracao:RC_D", acao="dispensar", motivo="não"
                    ).get_data(as_text=True)
    assert "motivo escrito" in html
    assert _con(s).execute(
        "SELECT situacao FROM nu_implantacao WHERE chave='numeracao:RC_D'"
    ).fetchone()[0] == "ABERTA"


def test_numero_que_baixaria_o_contador_avisa_e_volta(s):
    # Quem recusa é `escrituracao.fixar_numeracao`, e o balcão lê a mensagem
    # dela — não um 500.
    declarar(s)
    informar(s, "numeracao:PT_PROTESTO", acao="informar", proximo="2157")
    con = _con(s)
    with con:
        con.execute("UPDATE nu_numeracao SET maior_em_uso=2156 "
                    "WHERE serie='PT_PROTESTO'")
        con.execute("UPDATE nu_implantacao SET situacao='ABERTA' "
                    "WHERE chave='numeracao:PT_PROTESTO'")
    html = informar(s, "numeracao:PT_PROTESTO", acao="informar", proximo="10"
                    ).get_data(as_text=True)
    assert "repetiria número de ordem" in html


def test_reabrir_pela_aba(s):
    declarar(s)
    informar(s, "numeracao:RC_D", acao="dispensar",
             motivo="achei que não se usava nesta casa")
    informar(s, "numeracao:RC_D", acao="reabrir")
    con = _con(s)
    p = con.execute("SELECT * FROM nu_implantacao WHERE chave='numeracao:RC_D'"
                    ).fetchone()
    assert p["situacao"] == "ABERTA"
    # O que foi escrito FICA: engano se conserta à vista.
    assert "achei que não se usava" in p["observacao"]
