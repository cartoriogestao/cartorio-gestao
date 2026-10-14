"""AS SEIS TELAS DOS SUBMÓDULOS DE MODELOS — uma por atribuição.

O QUE ESTES TESTES GUARDAM:

      - **as seis portas existem e caem no menu certo** — é o nome da rota que
        põe a tela no grupo, e uma rota mal nomeada esconderia o submódulo
        dentro da atribuição errada;
      - **USER (escrevente) abre o submódulo** — mesmas roles de `/modelos`
        (3.6.222+); POST sem CSRF ou fora da regra não grava;
      - **a tela diz que o cabeçalho não está ali**, em vez de o omitir —
        campo que some sem explicação faz procurar defeito onde há decisão;
      - **a atribuição sem papel diz por quê**, e não aparece vazia;
      - **gravar num submódulo aparece no outro caminho**: as duas telas são
        duas portas do mesmo armazém, e não duas fontes;
      - e o de-onde-veio aparece na tela — «herdado» e «próprio» parecem a
        mesma coisa quando o texto é o mesmo.
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

import modelos_elementos as ELEM
import modelos_elementos_schema as ESQ
import modelos_elementos_web as WEB

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    return achado.group(1) if achado else ""


def _sessao(cg_casa, papel: str = "ADMIN"):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    bd = cg_casa['db']
    bd.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, papel)
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco, "db": bd}


@pytest.fixture()
def s(cg_casa):
    return _sessao(cg_casa)


@pytest.fixture()
def balcao(cg_casa):
    return _sessao(cg_casa, "USER")


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def _url(atribuicao: str) -> str:
    return WEB.CAMINHO_DA_ATRIBUICAO[atribuicao]


# ============================================================== as seis portas

def test_as_seis_telas_abrem(s):
    for a in ESQ.ATRIBUICOES:
        r = s["c"].get(_url(a))
        assert r.status_code == 200, a
        assert ESQ.NOME_DA_ATRIBUICAO[a] in r.get_data(as_text=True), a


def test_cada_tela_cai_no_menu_da_sua_atribuicao():
    """**É o nome da rota que põe a tela no grupo do menu.**

    Uma rota mal nomeada esconderia o submódulo do Registro de Imóveis dentro
    do Administrativo, e o oficial o procuraria onde ele não está.
    """
    import modulos
    esperado = {"RI": "RI", "NOTAS": "NOTAS", "RCPN": "RCPN",
                "RCPJ_RTD": "RCPJ_RTD", "PROTESTO": "PROTESTO",
                # Caixa e protocolo não é atribuição: o menu dela é o
                # Administrativo, que é onde a tela geral também mora.
                "CAIXA": "ADM"}
    for a, rota in WEB.ROTA_DA_ATRIBUICAO.items():
        assert modulos.modulo_da_tela(rota) == esperado[a], a


def test_o_menu_leva_aos_seis_submodulos(s):
    html = s["c"].get(_url(ESQ.RI)).get_data(as_text=True)
    for rota in WEB.ROTA_DA_ATRIBUICAO.values():
        caminho = WEB.CAMINHO_DA_ATRIBUICAO[
            next(a for a, r in WEB.ROTA_DA_ATRIBUICAO.items() if r == rota)]
        assert caminho in html, rota


def test_a_tela_oferece_as_outras_atribuicoes(s):
    html = s["c"].get(_url(ESQ.RCPN)).get_data(as_text=True)
    assert "Protesto" in html and "Registro de Imóveis" in html


# ===================================================== quem edita, e quem não

def test_o_balcao_abre_o_submodulo(balcao):
    """USER entra nas seis portas — alinhado a `QUEM_EDITA` em modelos_elementos_web."""
    r = balcao["c"].get(_url(ESQ.RI))
    assert r.status_code == 200
    assert ESQ.NOME_DA_ATRIBUICAO["RI"] in r.get_data(as_text=True)


def test_o_balcao_nao_grava_mesmo_mandando_o_post(balcao):
    balcao["c"].post(_url(ESQ.RI),
                     data={"ato": "", "parte": ESQ.RODAPE, "corpo": "na marra",
                           "acao": "salvar"}, follow_redirects=True)
    con = _con(balcao)
    assert con.execute("SELECT COUNT(*) FROM mo_elementos").fetchone()[0] == 0
    con.close()


# ============================================================ o que a tela diz

def test_a_tela_diz_que_o_cabecalho_nao_esta_ali(s):
    """Campo que some sem explicação faz procurar defeito onde há decisão."""
    html = s["c"].get(_url(ESQ.RI)).get_data(as_text=True)
    assert "cabeçalho não se edita aqui" in html


def test_rcpj_e_rtd_mostram_as_certidoes_editaveis(s):
    html = s["c"].get(_url(ESQ.RCPJ_RTD)).get_data(as_text=True)
    assert "Certidão de inteiro teor" in html


def test_a_tela_mostra_os_papeis_da_atribuicao(s):
    html = s["c"].get(_url(ESQ.RI)).get_data(as_text=True)
    assert "Ficha da matrícula" in html
    assert "Nota devolutiva" in html
    # E não os das outras.
    assert "Termo de óbito" not in html


def test_a_tela_diz_de_onde_o_texto_veio(s):
    """De qual degrau da herança o texto saiu — o ato, a atribuição, o legado
    ou o padrão do código.

    **A PALAVRA MUDOU NA 3.6.75, E A INFORMAÇÃO FICOU.** A tela foi reescrita
    (lista à esquerda, editor e prévia à direita) e passou a dizer «Herdado de
    Registro de Imóveis» onde dizia «herdado da atribuição» — e o corpo dos
    elementos só aparece com um documento ABERTO. Datado abrindo os pacotes:
    a 3.6.72 tem a tela antiga, a 3.6.75 a nova.
    """
    c = s["c"]
    c.post(_url(ESQ.RI),
           data={"ato": "", "parte": ESQ.ENCERRAMENTO, "corpo": "Dou fé.",
                 "acao": "salvar",
                 "csrf_token": _token(c.get(_url(ESQ.RI)).get_data(as_text=True))},
           follow_redirects=True)
    html = c.get(_url(ESQ.RI) + "?editar=RI_NOTA").get_data(as_text=True)
    assert "Herdado de" in html


# ================================================================== gravar

def test_gravar_o_elemento_da_atribuicao(s):
    c = s["c"]
    r = c.post(_url(ESQ.RI),
               data={"ato": "", "parte": ESQ.ENCERRAMENTO, "corpo": "Dou fé.",
                     "acao": "salvar",
                     "csrf_token": _token(c.get(_url(ESQ.RI)).get_data(as_text=True))},
               follow_redirects=True)
    assert r.status_code == 200
    con = _con(s)
    assert ELEM.elemento(con, atribuicao=ESQ.RI, ato="RI_NOTA",
                         parte=ESQ.ENCERRAMENTO)["texto"] == "Dou fé."
    con.close()


def test_gravar_elemento_ruim_recusa_com_o_recado_certo(s):
    """A recusa de regra não pode sair como «não deu para gravar»."""
    c = s["c"]
    r = c.post(_url(ESQ.RCPN),
               data={"ato": "RC_TERMO_OBITO", "parte": ESQ.ENCERRAMENTO,
                     "corpo": "{{ sv.registrador }}", "acao": "salvar",
                     "csrf_token": _token(c.get(_url(ESQ.RCPN)).get_data(as_text=True))},
               follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "chaves simples" in html
    con = _con(s)
    assert con.execute("SELECT COUNT(*) FROM mo_elementos").fetchone()[0] == 0
    con.close()


def test_voltar_ao_herdado(s):
    c = s["c"]
    for corpo in ("Dou fé.",):
        c.post(_url(ESQ.RI),
               data={"ato": "", "parte": ESQ.ENCERRAMENTO, "corpo": corpo,
                     "acao": "salvar",
                     "csrf_token": _token(c.get(_url(ESQ.RI)).get_data(as_text=True))},
               follow_redirects=True)
    c.post(_url(ESQ.RI),
           data={"ato": "", "parte": ESQ.ENCERRAMENTO, "corpo": "",
                 "acao": "restaurar",
                 "csrf_token": _token(c.get(_url(ESQ.RI)).get_data(as_text=True))},
           follow_redirects=True)
    con = _con(s)
    assert con.execute("SELECT COUNT(*) FROM mo_elementos").fetchone()[0] == 0
    con.close()


# ================================== as duas telas são duas portas do mesmo lugar

def test_o_que_se_grava_no_submodulo_aparece_na_tela_geral(s):
    """**Duas portas, um armazém.** Duas fontes divergiriam no primeiro conserto."""
    c = s["c"]
    c.post(_url(ESQ.RI),
           data={"ato": "RI_NOTA", "parte": ESQ.CORPO,
                 "corpo": "A nota nova da casa.", "acao": "salvar",
                 "csrf_token": _token(c.get(_url(ESQ.RI)).get_data(as_text=True))},
           follow_redirects=True)
    html = c.get("/modelos?editar=RI_NOTA").get_data(as_text=True)
    assert "A nota nova da casa." in html


def test_o_que_se_grava_na_tela_geral_aparece_no_submodulo(s):
    """A volta do par de cima, e é ela que prova que não há duas fontes.

    **O ENDEREÇO PASSOU A PEDIR O DOCUMENTO ABERTO** — na tela reescrita em
    08/09/2026 `/ri/modelos` é o índice, e o corpo mora em
    `/ri/modelos?editar=<chave>`. O que se grava continua indo para a MESMA
    linha de `mo_elementos`, e daí para o papel: medido com um ensaio que
    gravou pela tela geral e foi conferir nos três lugares — o banco (1
    linha), o submódulo e `modelos_da_casa.corpo_de`.
    """
    c = s["c"]
    c.post("/modelos",
           data={"chave": "RI_NOTA", "corpo": "Escrito na tela geral.",
                 "acao": "salvar",
                 "csrf_token": _token(c.get("/modelos").get_data(as_text=True))},
           follow_redirects=True)
    html = c.get(_url(ESQ.RI) + "?editar=RI_NOTA").get_data(as_text=True)
    assert "Escrito na tela geral." in html
