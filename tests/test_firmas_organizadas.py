"""As firmas são uma coisa só, e estavam em três lugares.

Pedidos do oficial em 27/08/2026, pela janela da ajuda:

  «Reconhecimento e reconhecer firma estão injustificadamente separados. Há que
   fazer uma organização racional dos módulos, especialmente o reconhecimento de
   firma, reconhecimentos e cartões de autógrafo.»

  «Assinaturas digitalizadas deveria ser campo dos cartões de assinatura, não
   faz sentido mais esse campo para dividir e complicar a localização e o
   trabalho com as firmas.»

O QUE MUDOU, E O QUE NÃO
    «Reconhecimentos» era a LISTA do que já foi reconhecido, e vivia no menu ao
    lado do ATO de reconhecer — duas entradas com quase o mesmo nome. Agora o
    menu tem uma porta só, e as três telas se alcançam por abas.

    As telas **continuam três**, e de propósito: cada uma faz uma coisa —
    lavrar, consultar, cadastrar. Fundir tudo numa página só poria a busca
    paginada por cima do balcão, que é o oposto do que ele pediu.

    E «assinaturas digitalizadas» não é um campo: é o **mutirão** que traz os
    arquivos do E-Ofício para dentro. Saiu do menu e passou a ser chamado da
    tela dos cartões, com o número do que falta ao lado — medido no banco vivo:
    **1.106 dos 4.062 cartões ainda não têm autógrafo**, e sem autógrafo não se
    reconhece por semelhança.
"""
from __future__ import annotations

import glob
import re
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


@pytest.fixture(scope="module")
def cliente(tmp_path_factory):
    from app import create_app
    from database import Database

    dados = tmp_path_factory.mktemp("dados")
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    Database(banco).create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


def _menu(html: str) -> str:
    return html[html.find("<nav>"):html.find("</nav>")]


# ------------------------------------------------- o menu tem uma porta só


def test_o_menu_nao_tem_duas_entradas_de_reconhecimento(cliente):
    """Duas entradas com quase o mesmo nome é escolher no escuro."""
    nav = _menu(cliente.get("/").get_data(as_text=True))
    assert "/notas/reconhecimento" in nav
    assert nav.count("/notas/reconhecimentos") == 0, (
        "a lista voltou ao menu, ao lado do ato de reconhecer")


def test_o_mutirao_das_assinaturas_saiu_do_menu(cliente):
    """Ele não é uma tela de consulta: é o que abastece os cartões."""
    nav = _menu(cliente.get("/").get_data(as_text=True))
    assert "/notas/assinaturas" not in nav


# ----------------------------------------- mas as três telas continuam vivas


@pytest.mark.parametrize("caminho", [
    "/notas/reconhecimento", "/notas/reconhecimentos", "/notas/cartoes",
    "/notas/assinaturas",
])
def test_as_telas_continuam_de_pe(cliente, caminho):
    """Tirar do menu não é apagar — quem tinha o endereço continua chegando."""
    assert cliente.get(caminho).status_code == 200


@pytest.mark.parametrize("caminho", [
    "/notas/reconhecimento", "/notas/reconhecimentos", "/notas/cartoes",
])
def test_as_tres_telas_se_alcancam_por_abas(cliente, caminho):
    """De qualquer uma delas se vê as outras duas."""
    html = cliente.get(caminho).get_data(as_text=True)
    corpo = html[html.find("</nav>"):]      # fora do menu lateral
    for destino in ("/notas/reconhecimento", "/notas/reconhecimentos",
                    "/notas/cartoes"):
        assert destino in corpo, f"{caminho} não oferece {destino}"


def test_a_aba_da_tela_atual_vem_destacada(cliente):
    """Aba sem destaque é o mesmo escuro de antes, com mais cliques."""
    html = cliente.get("/notas/cartoes").get_data(as_text=True)
    corpo = html[html.find("</nav>"):]
    assert re.search(r'class="button primary"[^>]*href="[^"]*/notas/cartoes"',
                     corpo)


# ------------------------------------- o autógrafo é do cartão, e o número também


def test_a_tela_dos_cartoes_diz_quantos_estao_sem_autografo(cliente):
    """Sem autógrafo não se reconhece por semelhança — o número é operacional."""
    html = cliente.get("/notas/cartoes").get_data(as_text=True)
    assert "sem autógrafo" in html


def test_o_mutirao_e_chamado_da_tela_dos_cartoes(cliente):
    html = cliente.get("/notas/cartoes").get_data(as_text=True)
    assert "/notas/assinaturas" in html[html.find("</nav>"):]
