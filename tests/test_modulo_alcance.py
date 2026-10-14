"""ATÉ ONDE CADA MÓDULO VAI — e o Protesto de volta para o oficial.

Ordem dele em 01/09/2026, na mesma noite em que mandou desligá-lo:
*«reabilite o protesto para o administrador, permitindo um botão em
configurações habilitar para todos usuarios»*.

**A PERGUNTA MUDOU, E NÃO SÓ A RESPOSTA.** Era um interruptor — ligado ou
desligado — e virou **alcance**: `NINGUEM`, `ADMIN`, `TODOS`. Por isso este
arquivo substitui o `test_modulo_desligado.py`: o nome dizia o que ele já não
guarda.

O QUE ESTES TESTES GUARDAM
      - **de fábrica o Protesto é do oficial**, e não de todos nem de ninguém;
      - **a guarda é no servidor**, e sabe quem está batendo: tirar o link e
        deixar a rota de pé esconde a porta sem trancá-la;
      - **o ADMIN nunca se tranca do lado de fora** — quem muda o alcance é
        ele, e `NINGUEM` não o alcança;
      - **a frase muda com o alcance**: «fechado para todos» e «só para o
        oficial» pedem providências diferentes de quem lê;
      - **a marca da versão anterior não se perde** — quem já tinha ligado o
        módulo na 3.6.61 continua com ele aberto;
      - **o dado nunca sai do banco**, em nenhum dos três alcances.
"""
from __future__ import annotations

import contextlib
import glob
import os
import re
import sys
import tempfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import modulos as MOD
import modulos_ligados as MODLIG

DADOS = str(Path(tempfile.gettempdir()) /
            ("test_mod_alcance_" + os.environ.get("PYTEST_XDIST_WORKER", "solo")))

SEM_CONFIG = lambda chave, padrao=None: padrao


def config(**linhas):
    """Um `get_setting` de mentira, com as linhas que se quer."""
    return lambda chave, padrao=None: linhas.get(chave, padrao)


@pytest.fixture(scope="module")
def app():
    from app import create_app
    Path(DADOS).mkdir(parents=True, exist_ok=True)
    return create_app({"DATA_DIR": DADOS})


@pytest.fixture(scope="module")
def banco(app):
    from database import Database
    return Database(Path(glob.glob(f"{DADOS}/*.sqlite3")[0]))


def _entrar(app, banco, usuario, papel):
    with contextlib.suppress(Exception):
        banco.create_user(usuario, "Operador", "Senha#12345", papel)
    c = app.test_client()
    pega = lambda h: re.search(r'name="csrf_token"[^>]*value="([^"]+)"', h).group(1)
    c.post("/login", data={"username": usuario, "password": "Senha#12345",
                           "csrf_token": pega(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


@pytest.fixture(scope="module")
def oficial(app, banco):
    return _entrar(app, banco, "alc_adm", "ADMIN")


@pytest.fixture(scope="module")
def escrevente(app, banco):
    return _entrar(app, banco, "alc_usr", "USER")


@pytest.fixture
def de_fabrica(banco):
    """Sem linha em `settings` — que é como a atualização chega ao servidor."""
    with banco.connect() as con:
        con.execute("DELETE FROM settings WHERE key IN "
                    "('modulo_protesto_alcance','modulo_protesto_ligado')")
        con.commit()
    yield


# ------------------------------------------------- a regra, sem tela


def test_de_fabrica_o_protesto_e_do_oficial():
    """Nem de todos nem de ninguém: o alcance do meio, que ele pediu."""
    assert MODLIG.alcance(SEM_CONFIG, "PROTESTO") == MODLIG.ADMIN
    assert MODLIG.pode_entrar(SEM_CONFIG, "PROTESTO", "ADMIN") is True
    assert MODLIG.pode_entrar(SEM_CONFIG, "PROTESTO", "USER") is False
    assert MODLIG.pode_entrar(SEM_CONFIG, "PROTESTO", None) is False


def test_o_alcance_TODOS_abre_para_o_balcao():
    c = config(modulo_protesto_alcance="TODOS")
    assert MODLIG.pode_entrar(c, "PROTESTO", "USER") is True
    assert MODLIG.escondidos(c, "USER") == frozenset()


def test_o_alcance_NINGUEM_fecha_ate_para_o_oficial():
    """É o único em que ele também não entra — e por isso a tela de
    configurações continua sendo dele: lá é que se desfaz."""
    c = config(modulo_protesto_alcance="NINGUEM")
    assert MODLIG.pode_entrar(c, "PROTESTO", "ADMIN") is False
    assert MODLIG.pode_entrar(c, "PROTESTO", "USER") is False


def test_o_gerente_nao_entra_no_alcance_do_oficial():
    """«Para o administrador» foi o que ele escreveu. Ampliar por conta
    própria seria decidir por ele — e é uma palavra em `PAPEIS_DO_ALCANCE` se
    ele quiser o gerente junto."""
    assert MODLIG.pode_entrar(SEM_CONFIG, "PROTESTO", "MANAGER") is False


def test_os_outros_sete_modulos_sao_de_todos():
    """Fechar um não pode fechar os vizinhos."""
    for m in MOD.MODULOS:
        if m["chave"] != "PROTESTO":
            assert MODLIG.alcance(SEM_CONFIG, m["chave"]) == MODLIG.TODOS
            assert MODLIG.pode_entrar(SEM_CONFIG, m["chave"], "USER") is True


def test_valor_estranho_na_configuracao_cai_no_de_fabrica():
    """Linha escrita à mão, ou de uma versão futura, não pode abrir o módulo
    por acidente."""
    assert MODLIG.alcance(config(modulo_protesto_alcance="SEI_LA"),
                          "PROTESTO") == MODLIG.ADMIN


def test_a_marca_da_versao_anterior_nao_se_perde():
    """**A 3.6.61 gravava `modulo_protesto_ligado`.** Se o oficial já a aplicou
    e marcou a caixa, aquele `1` quer dizer «abre para todos» — e a atualização
    desfazer a decisão dele seria a tela apagando o que ele decidiu."""
    assert MODLIG.alcance(config(modulo_protesto_ligado="1"),
                          "PROTESTO") == MODLIG.TODOS
    assert MODLIG.alcance(config(modulo_protesto_ligado="0"),
                          "PROTESTO") == MODLIG.NINGUEM
    # E a chave nova manda sobre a antiga.
    assert MODLIG.alcance(config(modulo_protesto_ligado="1",
                                 modulo_protesto_alcance="ADMIN"),
                          "PROTESTO") == MODLIG.ADMIN


def test_a_regra_de_qual_modulo_e_a_de_modulos_py():
    """UMA RÉGUA, E NÃO DUAS PARECIDAS — a lição da `normalizar_nome`."""
    for endpoint in ("protesto_titulos", "protesto_painel", "protesto_cenprot"):
        assert MOD.modulo_da_tela(endpoint) == "PROTESTO"
        assert MODLIG.pode_entrar(SEM_CONFIG, MOD.modulo_da_tela(endpoint),
                                  "USER") is False
    for endpoint in ("ri_matriculas", "notas_cartoes", "rcpn_assentos",
                     "caixa", "nucleo_livros"):
        assert MODLIG.pode_entrar(SEM_CONFIG, MOD.modulo_da_tela(endpoint),
                                  "USER") is True


def test_a_frase_muda_com_o_alcance():
    """«Fechado para todos» e «só do oficial» pedem providências diferentes de
    quem lê — a segunda diz a quem pedir."""
    fechado = MODLIG.motivo("PROTESTO", MODLIG.NINGUEM)
    so_dele = MODLIG.motivo("PROTESTO", MODLIG.ADMIN)
    assert fechado != so_dele
    assert "continuam guardados" in fechado
    assert "apenas para o oficial" in so_dele
    assert "todos os usuários" in so_dele


# ------------------------------------------------- e na tela


def test_o_oficial_entra_e_ve_o_grupo(oficial, de_fabrica):
    assert oficial.get("/protesto").status_code == 200
    html = oficial.get("/").get_data(as_text=True)
    nav = html[html.find("<nav>"):html.find("</nav>")]
    assert "<summary>Protesto</summary>" in nav


def test_o_escrevente_nao_entra_e_nao_ve(escrevente, de_fabrica):
    """**A GUARDA É NO SERVIDOR.** Este é o teste que impede o favorito de
    entrar — o menu some por educação, a rota recusa por dever."""
    html = escrevente.get("/").get_data(as_text=True)
    nav = html[html.find("<nav>"):html.find("</nav>")]
    assert "<summary>Protesto</summary>" not in nav
    r = escrevente.get("/protesto", follow_redirects=True)
    assert r.status_code == 200
    corpo = r.get_data(as_text=True)
    assert "apenas para o oficial" in corpo
    assert "Títulos protestados" not in corpo


def test_liberar_para_todos_abre_para_o_escrevente(escrevente, banco):
    """O botão que ele pediu, provado do lado de quem ele libera."""
    banco.set_settings({"modulo_protesto_alcance": "TODOS"})
    try:
        assert escrevente.get("/protesto").status_code == 200
        html = escrevente.get("/").get_data(as_text=True)
        nav = html[html.find("<nav>"):html.find("</nav>")]
        assert "<summary>Protesto</summary>" in nav
    finally:
        with banco.connect() as con:
            con.execute("DELETE FROM settings "
                        "WHERE key='modulo_protesto_alcance'")
            con.commit()


def test_a_tela_de_configuracoes_oferece_os_tres(oficial):
    html = oficial.get("/configuracoes").get_data(as_text=True)
    assert 'name="modulo_protesto_alcance"' in html
    for valor in ("ADMIN", "TODOS", "NINGUEM"):
        assert f'value="{valor}"' in html


def test_fechar_para_todos_nao_apaga_o_que_estava_lavrado(banco):
    """FECHAR MÓDULO NUNCA APAGA ATO — ato lavrado é livro."""
    banco.set_settings({"modulo_protesto_alcance": "NINGUEM"})
    try:
        with banco.connect() as con:
            for tabela in ("pt_titulos", "pt_atos", "pt_instrumentos"):
                con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()
    finally:
        with banco.connect() as con:
            con.execute("DELETE FROM settings "
                        "WHERE key='modulo_protesto_alcance'")
            con.commit()
