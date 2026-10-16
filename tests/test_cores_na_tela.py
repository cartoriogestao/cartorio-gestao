"""A cor do modulo chega a tela — relato #32 do oficial.

O QUE ESTES TESTES GUARDAM

    **Que a cor chega em TODA tela, e nao tela a tela.** Ela vai no contexto
    global: ligada uma a uma, a primeira tela que alguem criasse amanha
    nasceria sem cor **e sem aviso de que nasceu** — foi o que aconteceu com a
    janela da ajuda antes de ela ir para o `base.html`.

    **Que o menu carrega as OITO cores**, e nao so a da tela atual: ele mostra
    os oito grupos ao mesmo tempo, e a marca de cada um e a cor DELE.

    **Que a cor vem com o NOME.** A cor sozinha diz «mudou de modulo»; ela nao
    diz para qual. Quem chega numa tela pelo link de outra precisa das duas
    coisas — cor sem nome e adivinhacao.

    **Que o painel nao tem cor de modulo.** Ele e a tela de todos; pinta-lo com
    a cor de um faria parecer que pertence aquele.
"""
from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import modulos as M                                              # noqa: E402

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return achado.group(1) if achado else ""


@pytest.fixture(scope="module")
def cliente(tmp_path_factory):
    from app import create_app
    from database import Database

    dados = tmp_path_factory.mktemp("dados")
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    Database(banco).create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA,
                                "ADMIN")
    # O PROTESTO ESTA DESLIGADO DE FABRICA desde 01/09/2026 — ordem do
    # oficial. Estes testes exercitam as TELAS dele, e por isso o LIGAM
    # aqui, de proposito e a vista: eles provam que o modulo funciona
    # quando ele voltar, que e o que «fica para um futuro» quer dizer.
    Database(banco).set_settings({"modulo_protesto_ligado": "1"})
    c = app.test_client()
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


# (endereço, chave do módulo esperado)
TELAS = [
    ("/notas", "NOTAS"),
    ("/registro-imoveis", "RI"),
    ("/rcpn", "RCPN"),
    ("/protesto", "PROTESTO"),
    ("/expedientes", "MALOTE"),
    ("/caixa", "ADM"),
    ("/importar-padrao", "LIVROS"),
]


@pytest.mark.parametrize("endereco,chave", TELAS)
def test_cada_tela_recebe_a_cor_do_seu_modulo(cliente, endereco, chave):
    html = cliente.get(endereco, follow_redirects=True).get_data(as_text=True)
    esperada = M.POR_CHAVE[chave]["cor"]
    achada = re.search(r"--mod-cor:(#[0-9a-f]{6})", html)
    assert achada, f"{endereco} veio sem cor de módulo"
    assert achada.group(1) == esperada, (
        f"{endereco} veio com {achada.group(1)} e o módulo {chave} é "
        f"{esperada}")


@pytest.mark.parametrize("endereco,chave", TELAS)
def test_cada_tela_diz_o_NOME_do_modulo(cliente, endereco, chave):
    """**Cor sem nome é adivinhação.** Ela diz «mudou»; não diz para qual."""
    html = cliente.get(endereco, follow_redirects=True).get_data(as_text=True)
    etiqueta = re.search(r'modulo-etiqueta">([^<]+)<', html)
    assert etiqueta, f"{endereco} veio sem a etiqueta do módulo"
    assert etiqueta.group(1).strip() == M.POR_CHAVE[chave]["nome"]


def test_o_painel_nao_tem_cor_de_modulo(cliente):
    """**Ele é a tela de todos.**"""
    html = cliente.get("/").get_data(as_text=True)
    assert "--mod-cor:" not in html
    assert "modulo-etiqueta" not in html


def test_o_menu_carrega_as_cores_de_todos_os_modulos(cliente):
    """O menu mostra os oito grupos ao mesmo tempo — a marca de cada um é a cor
    dele, e não a da tela em que se está."""
    html = cliente.get("/").get_data(as_text=True)
    for m in M.MODULOS:
        chave = m["chave"].lower().replace("_", "-")
        assert f"--mod-{chave}:{m['cor']}" in html, \
            f"a cor de {m['nome']} não chegou ao menu"


def test_todo_grupo_do_menu_tem_a_marca_da_propria_cor():
    """Grupo sem marca é grupo que não se distingue — e a cor existe para
    distinguir."""
    html = (RAIZ / "templates" / "base.html").read_text(encoding="utf-8")
    grupos = html.count('<details class="nav-modulo"')
    marcados = html.count("--cor-do-grupo:")
    assert marcados == grupos, (
        f"há {grupos} grupos no menu e {marcados} com marca de cor — "
        f"grupo novo nasce sem a marca se ninguém a puser")


def test_nenhuma_cor_de_modulo_esta_escrita_no_css():
    """**Escrita lá, seria a segunda fonte**, e módulo novo entraria no menu
    com a cor de outro porque alguém copiaria a linha vizinha."""
    css = (RAIZ / "static" / "app.css").read_text(encoding="utf-8")
    assert not re.findall(r"--mod-[a-z-]+\s*:\s*#[0-9a-f]", css), (
        "há cor de módulo escrita à mão no app.css — ela sai de "
        "`modulos.folha_de_estilo()`")


def test_a_cor_nao_pinta_a_tela_inteira():
    """**Fundo colorido cansa a vista de quem passa o dia nele.**

    A cor marca três lugares discretos — a faixa do alto, a etiqueta e a marca
    do menu —, e não o corpo da página.
    """
    css = (RAIZ / "static" / "app.css").read_text(encoding="utf-8")
    for regra in ("body{background:var(--mod-cor",
                  ".content{background:var(--mod-cor",
                  ".main{background:var(--mod-cor"):
        assert regra not in css, f"a cor do módulo pinta o fundo: {regra}"
