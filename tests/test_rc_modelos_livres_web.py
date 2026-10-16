"""AS TELAS DOS MODELOS DO ESCREVENTE — a lista, o editor e o documento.

O QUE ESTES TESTES GUARDAM:

      - **o balcão emite, mas não escreve modelo** — uma vírgula fora do lugar
        sai em todo documento daquele tipo até alguém reparar;
      - **a tela do documento mostra o claro vazio ANTES de imprimir**, com o
        nome dele: é o «conferir e imprimir são dois botões»;
      - **a lista vazia diz por quê**, e não deixa o escrevente concluir que a
        tela quebrou;
      - **converter não grava** — e a tela diz isso, e diz o que não converteu;
      - a rota **recusa modelo de outra espécie** e volta com aviso, e não com
        HTTP 500;
      - e a tela dos modelos é do **grupo do Registro Civil**, porque a rota se
        chama `rcpn_*`.
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

import rc_assento as RC
import rc_modelos_livres as MOD

SENHA = "Senha#12345"
AGORA = "2026-09-07T10:00:00"
CNS = "000000"
SV = {"ri_cns": CNS, "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
      "escrevente": "MARIO", "funcao": "Escrevente"}

# **`lavrar_assento` NAO LAVRA EM BRANCO** — art. 54 da Lei 6.015/1973. A
# filiacao 2 e o declarante sao exigidos, e por isso entram aqui: montar o
# assento com menos do que a lei pede faria o teste falhar por outra razao que
# nao a que ele guarda.
PESSOAS = [
    {"papel": "REGISTRADO", "nome": "FULANO DE TAL", "sexo": "M",
     "naturalidade_cidade": "Cidade Exemplo", "naturalidade_uf": "MA"},
    {"papel": "MAE", "nome": "MARIA DE TAL"},
    {"papel": "PAI", "nome": "JOSE DE TAL"},
    {"papel": "DECLARANTE", "nome": "JOSE DE TAL"},
]


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    return achado.group(1) if achado else ""


def _sessao(cg_casa, papel: str = "ADMIN"):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    bd = cg_casa['db']
    bd.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, papel)
    bd.set_settings({"serventia_cns": CNS, "ri_uf": "MA",
                     "ri_cidade": "Cidade Exemplo"})
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


def _assento(s, *, especie="NASCIMENTO") -> int:
    con = _con(s)
    feito = RC.lavrar_assento(
        con, especie=especie, nome="FULANO DE TAL", sv=SV, agora=AGORA,
        data_extenso="sete de setembro de dois mil e vinte e seis",
        data_fato="2020-01-15", usuario="MARIO", pessoas=PESSOAS,
        termo_dados={"local_fato_nome": "Hospital Municipal"},
        # relato #130: o que a CRC e o SIRC exigem entra na lavratura
        ibge=({"local_nascimento": 1} if especie == "NASCIMENTO" else None),
        marcas_do_obito=({"obito_possui_bens": "NAO"}
                         if especie == "OBITO" else None))
    con.commit()
    con.close()
    return feito["assento_id"]


def _modelo(s, *, especie="NASCIMENTO", nome="Comunicação",
            corpo="Certifico que {nome}.") -> int:
    con = _con(s)
    ident = MOD.criar(con, especie=especie, nome=nome, corpo=corpo,
                      quem="MARIO", agora=AGORA)
    con.commit()
    con.close()
    return ident


# ================================================================== a lista

def test_a_lista_abre(s):
    r = s["c"].get("/rcpn/modelos")
    assert r.status_code == 200
    assert "Modelos do Registro Civil" in r.get_data(as_text=True)


def test_a_lista_vazia_diz_por_que(s):
    """Lista vazia calada faz o escrevente concluir que a tela quebrou."""
    html = s["c"].get("/rcpn/modelos").get_data(as_text=True)
    assert "Nenhum modelo cadastrado" in html


def test_a_lista_mostra_o_modelo_cadastrado(s):
    _modelo(s, nome="Termo de gêmeos")
    html = s["c"].get("/rcpn/modelos").get_data(as_text=True)
    assert "Termo de gêmeos" in html


def test_o_filtro_por_especie_filtra(s):
    _modelo(s, especie="NASCIMENTO", nome="Do nascimento")
    _modelo(s, especie="OBITO", nome="Do óbito")
    html = s["c"].get("/rcpn/modelos?especie=OBITO").get_data(as_text=True)
    assert "Do óbito" in html
    assert "Do nascimento" not in html


def test_especie_inventada_no_filtro_nao_derruba(s):
    r = s["c"].get("/rcpn/modelos?especie=PROCLAMAS")
    assert r.status_code == 200


# ================================================= quem escreve, e quem não

def test_o_balcao_ve_a_lista(balcao):
    assert balcao["c"].get("/rcpn/modelos").status_code == 200


def test_o_balcao_nao_ganha_formulario_de_cadastro(balcao):
    html = balcao["c"].get("/rcpn/modelos").get_data(as_text=True)
    assert "Cadastrar um modelo" not in html


def test_o_balcao_nao_cadastra_mesmo_mandando_o_post(balcao):
    """Esconder o botão não protege rota — a guarda é no servidor."""
    c = balcao["c"]
    c.post("/rcpn/modelos",
           data={"especie": "NASCIMENTO", "nome": "Na marra",
                 "corpo": "{nome}",
                 "csrf_token": _token(c.get("/rcpn/modelos").get_data(as_text=True))},
           follow_redirects=True)
    con = _con(balcao)
    assert MOD.listar(con) == []
    con.close()


def test_o_balcao_nao_converte(balcao):
    ident = _modelo(balcao)
    c = balcao["c"]
    r = c.post(f"/rcpn/modelos/{ident}/converter",
               data={"do_eoficio": "@nomenascido",
                     "csrf_token": _token(
                         c.get(f"/rcpn/modelos/{ident}").get_data(as_text=True))})
    assert r.status_code in (302, 403)


# ============================================================== o cadastro

def test_cadastrar_grava_e_abre_o_modelo(s):
    c = s["c"]
    r = c.post("/rcpn/modelos",
               data={"especie": "OBITO", "nome": "Comunicação mensal",
                     "corpo": "Certifico o óbito de {nome}.",
                     "csrf_token": _token(c.get("/rcpn/modelos").get_data(as_text=True))},
               follow_redirects=True)
    assert "Comunicação mensal" in r.get_data(as_text=True)
    con = _con(s)
    assert [m["especie"] for m in MOD.listar(con)] == ["OBITO"]
    con.close()


def test_cadastro_com_claro_desconhecido_recusa_e_nao_grava(s):
    """A conferência vem antes de gravar."""
    c = s["c"]
    r = c.post("/rcpn/modelos",
               data={"especie": "NASCIMENTO", "nome": "Ruim",
                     "corpo": "{naoexiste}",
                     "csrf_token": _token(c.get("/rcpn/modelos").get_data(as_text=True))},
               follow_redirects=True)
    assert "naoexiste" in r.get_data(as_text=True)
    con = _con(s)
    assert MOD.listar(con) == []
    con.close()


# =============================================================== o editor

def test_o_editor_mostra_a_lista_de_claros(s):
    ident = _modelo(s)
    html = s["c"].get(f"/rcpn/modelos/{ident}").get_data(as_text=True)
    assert "{registrado_nome}" in html
    assert "Os claros desta espécie" in html


def test_o_editor_marca_o_claro_em_uso(s):
    ident = _modelo(s, corpo="Certifico que {nome}.")
    html = s["c"].get(f"/rcpn/modelos/{ident}").get_data(as_text=True)
    assert "em uso" in html


def test_modelo_que_nao_existe_volta_para_a_lista(s):
    r = s["c"].get("/rcpn/modelos/9999", follow_redirects=True)
    assert r.status_code == 200
    assert "Não achei o modelo" in r.get_data(as_text=True)


def test_gravar_muda_o_texto(s):
    ident = _modelo(s)
    c = s["c"]
    c.post(f"/rcpn/modelos/{ident}",
           data={"acao": "salvar", "nome": "Outro nome",
                 "corpo": "Novo texto de {nome}.",
                 "csrf_token": _token(c.get(f"/rcpn/modelos/{ident}").get_data(as_text=True))},
           follow_redirects=True)
    con = _con(s)
    m = MOD.ler(con, ident)
    assert m["nome"] == "Outro nome"
    assert m["corpo"] == "Novo texto de {nome}."
    con.close()


def test_desativar_tira_da_lista_de_quem_emite_e_nao_apaga(s):
    ident = _modelo(s)
    c = s["c"]
    c.post(f"/rcpn/modelos/{ident}",
           data={"acao": "desativar",
                 "csrf_token": _token(c.get(f"/rcpn/modelos/{ident}").get_data(as_text=True))},
           follow_redirects=True)
    con = _con(s)
    assert MOD.ler(con, ident)["ativo"] == 0
    con.close()


# =========================================== a conversão do texto do E-Ofício

def test_converter_mostra_o_texto_e_NAO_grava(s):
    ident = _modelo(s, corpo="Certifico que {nome}.")
    c = s["c"]
    r = c.post(f"/rcpn/modelos/{ident}/converter",
               data={"do_eoficio": "NOME: @nomenascido",
                     "csrf_token": _token(c.get(f"/rcpn/modelos/{ident}").get_data(as_text=True))})
    html = r.get_data(as_text=True)
    assert "{registrado_nome}" in html
    assert "ainda não foi gravado" in html
    con = _con(s)
    assert MOD.ler(con, ident)["corpo"] == "Certifico que {nome}."
    con.close()


def test_converter_diz_o_que_nao_soube_converter(s):
    ident = _modelo(s)
    c = s["c"]
    r = c.post(f"/rcpn/modelos/{ident}/converter",
               data={"do_eoficio": "A @nomenascido B @numerofiliacao1",
                     "csrf_token": _token(c.get(f"/rcpn/modelos/{ident}").get_data(as_text=True))})
    assert "numerofiliacao1" in r.get_data(as_text=True)


# ============================================ o documento montado de um assento

def test_a_lista_do_assento_so_traz_a_especie_dele(s):
    aid = _assento(s, especie="NASCIMENTO")
    _modelo(s, especie="NASCIMENTO", nome="Do nascimento")
    _modelo(s, especie="OBITO", nome="Do óbito")
    html = s["c"].get(f"/rcpn/assentos/{aid}/modelos").get_data(as_text=True)
    assert "Do nascimento" in html
    assert "Do óbito" not in html


def test_o_assento_sem_modelo_diz_que_nao_ha(s):
    aid = _assento(s)
    html = s["c"].get(f"/rcpn/assentos/{aid}/modelos").get_data(as_text=True)
    assert "Não há modelo cadastrado" in html


def test_o_documento_sai_montado(s):
    aid = _assento(s)
    ident = _modelo(s, corpo="Certifico que {nome} é filho de {mae_nome}.")
    html = s["c"].get(
        f"/rcpn/assentos/{aid}/modelos/{ident}").get_data(as_text=True)
    assert "Certifico que FULANO DE TAL é filho de MARIA DE TAL." in html


def test_o_documento_avisa_o_claro_vazio_com_o_nome_dele(s):
    """**Conferir e imprimir são dois botões.**

    O avô paterno não foi declarado neste assento — e o claro dele sai vazio.
    A tela diz **qual** claro é, com o rótulo, antes de qualquer impressão.
    """
    aid = _assento(s)
    ident = _modelo(s, corpo="{nome}, neto de {avo_paterno_nome}.")
    html = s["c"].get(
        f"/rcpn/assentos/{aid}/modelos/{ident}").get_data(as_text=True)
    assert "sem dado" in html
    assert "{avo_paterno_nome}" in html


def test_o_documento_completo_nao_traz_aviso_de_vazio(s):
    aid = _assento(s)
    ident = _modelo(s, corpo="Certifico que {nome}.")
    html = s["c"].get(
        f"/rcpn/assentos/{aid}/modelos/{ident}").get_data(as_text=True)
    assert "sem dado" not in html


def test_modelo_de_outra_especie_volta_com_aviso_e_nao_com_500(s):
    aid = _assento(s, especie="NASCIMENTO")
    ident = _modelo(s, especie="OBITO", nome="Do óbito")
    r = s["c"].get(f"/rcpn/assentos/{aid}/modelos/{ident}",
                   follow_redirects=True)
    assert r.status_code == 200
    assert "Óbito" in r.get_data(as_text=True)


def test_o_balcao_emite(balcao):
    """Emitir é o trabalho do dia — escrever o modelo é que não é."""
    aid = _assento(balcao)
    ident = _modelo(balcao, corpo="Certifico que {nome}.")
    r = balcao["c"].get(f"/rcpn/assentos/{aid}/modelos/{ident}")
    assert r.status_code == 200
    assert "FULANO DE TAL" in r.get_data(as_text=True)


# =============================================== a tela é do Registro Civil

def test_as_telas_sao_do_grupo_do_registro_civil():
    """É o nome da rota que põe a tela no grupo do menu."""
    import modulos

    for rota in ("rcpn_modelos", "rcpn_modelo", "rcpn_modelo_emitir",
                 "rcpn_modelos_do_assento", "rcpn_modelo_converter"):
        assert modulos.modulo_da_tela(rota) == "RCPN", rota


def test_o_menu_leva_aos_modelos(s):
    html = s["c"].get("/rcpn/modelos").get_data(as_text=True)
    assert "Documentos avulsos" in html or "Modelos de documentos" in html


def test_a_ficha_do_assento_tem_a_porta(s):
    """**Tirar de uma lista não é dar um lugar** — e tela sem porta é a versão
    boa do mesmo defeito: existe, funciona, e ninguém chega nela.

    O balcão parte do assento aberto, e não do menu.
    """
    aid = _assento(s)
    html = s["c"].get(f"/rcpn/{aid}").get_data(as_text=True)
    assert f"/rcpn/assentos/{aid}/modelos" in html
