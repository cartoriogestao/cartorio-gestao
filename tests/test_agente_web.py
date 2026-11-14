"""
Testes da TELA que sobrou do agente do sistema: a configuração dos provedores.

O CONSOLE SAIU EM 14/11/2026 (ordem do oficial: «é um projeto abandonado»); o
superusuário tem tela própria (`tests/test_operador_web.py`). A configuração
ficou porque as chaves dela servem à Ajuda, ao WhatsApp, às revisões e à
automação.

POR QUE TELA, E NAO SO DOMINIO
    "Buraco de tela nao aparece em teste de dominio" e a licao que se repetiu
    seis vezes nesta casa — e com o agente ela vale mais que nunca: um agente
    com dez ferramentas prontas e nenhuma tela e um agente que ninguem usa. O
    que estes testes provam e que **o oficial consegue chegar nele**.

O QUE ELES CONFEREM
      - o console, a gaveta e as sessoes nao existem mais; a configuracao e
        so do ADMIN;
      - A CHAVE VAI PARA O ARQUIVO, e nao para o banco;
      - CAMPO VAZIO NAO APAGA NADA — quem apaga e o botao que diz que apaga;
      - A ESCRITA NASCE DESLIGADA, e so liga por clique;
      - o teto digitado na tela e PRESO no limite duro, e a tela diz o que
        passou a valer;
      - GET nao grava nada.
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


def _sessao(tmp_path, papel: str = "ADMIN"):
    from app import create_app
    from database import Database

    dados = tmp_path / "dados"
    # `parents`: o teste do menu cria uma sessão por papel, cada uma na sua
    # pasta — mesmo usuário em dois bancos diferentes, e não duas vezes no
    # mesmo banco.
    dados.mkdir(parents=True, exist_ok=True)
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    Database(banco).create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                                SENHA, papel)
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco, "dados": dados}


@pytest.fixture()
def admin(tmp_path):
    return _sessao(tmp_path, "ADMIN")


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def _pasta(s) -> Path:
    return s["dados"]


# ------------------------------------------------------- quem entra


def test_o_console_do_agente_saiu_e_a_configuracao_ficou(admin):
    """06/10/2026: «apenas não aparecer mais»; 14/11/2026: o console, a gaveta e
    as sessões foram apagados («é um projeto abandonado»). A configuração dos
    provedores fica, só do ADMIN."""
    menu = admin["c"].get("/").get_data(as_text=True)
    assert "Agente do sistema" not in menu and "Agente — configurar" not in menu
    assert "agente.js" not in menu and "agente-chamar" not in menu
    for rota in ("/agente", "/agente/gaveta", "/agente/sessao/1", "/agente/andamento/1"):
        assert admin["c"].get(rota).status_code == 404, rota
    assert admin["c"].get("/agente/configurar").status_code == 200


def test_o_menu_esconde_o_agente_de_quem_nao_pode(tmp_path):
    for papel in ("USER", "MANAGER"):
        s = _sessao(tmp_path / papel, papel)
        menu = s["c"].get("/").get_data(as_text=True)
        assert "Agente do sistema" not in menu, f"{papel} viu o agente no menu"
        # e a tela de configuração, que também é do admin, também não abre
        assert s["c"].get("/agente/configurar").status_code == 403


# ------------------------------------------------------------- a chave


def _gravar_chave(s, provedor="deepseek", chave="sk-teste-12345678"):
    html = s["c"].get("/agente/configurar").get_data(as_text=True)
    return s["c"].post("/agente/configurar",
                       data={"csrf_token": _token(html), "acao": "chave",
                             "provedor": provedor, "api_key": chave},
                       follow_redirects=True)


def test_a_chave_vai_para_o_arquivo_e_nao_para_o_banco(admin):
    """**O BANCO VAI NO BACKUP, E O BACKUP SAI DA SERVENTIA.**"""
    import agente_provedores as PROV

    _gravar_chave(admin)
    arquivo = PROV.caminho_da_credencial(_pasta(admin))
    assert arquivo.exists(), "a chave não foi para o arquivo"
    assert "sk-teste-12345678" in arquivo.read_text(encoding="utf-8")
    # e o banco não sabe dela — nem no valor da config, nem no arquivo todo
    con = _con(admin)
    valores = [r["valor"] for r in con.execute(
        "SELECT valor FROM ag_config")]
    con.close()
    assert not any("sk-teste" in v for v in valores)
    assert b"sk-teste-12345678" not in Path(admin["banco"]).read_bytes()


def test_a_chave_gravada_aparece_mascarada(admin):
    _gravar_chave(admin)
    html = admin["c"].get("/agente/configurar").get_data(as_text=True)
    assert "5678" in html
    assert "sk-teste-12345678" not in html


def test_campo_de_chave_em_branco_nao_apaga_nada(admin):
    """**O CAMPO VAZIO É A ARMADILHA DESTE FORMULÁRIO.**

    `gravar_chave` recebe vazio como ordem de apagar — é assim que se desliga um
    provedor. Se o campo em branco chegasse até lá, quem abrisse a tela e
    salvasse outra coisa apagaria a chave sem saber.
    """
    import agente_provedores as PROV

    _gravar_chave(admin)
    html = admin["c"].get("/agente/configurar").get_data(as_text=True)
    resposta = admin["c"].post("/agente/configurar",
                               data={"csrf_token": _token(html),
                                     "acao": "chave", "provedor": "deepseek",
                                     "api_key": ""},
                               follow_redirects=True)
    assert "nada foi gravado e nada foi apagado" in resposta.get_data(as_text=True)
    assert PROV.tem_chave(_pasta(admin), "deepseek")


def test_apagar_a_chave_e_por_botao_proprio(admin):
    import agente_provedores as PROV

    _gravar_chave(admin)
    html = admin["c"].get("/agente/configurar").get_data(as_text=True)
    admin["c"].post("/agente/configurar",
                    data={"csrf_token": _token(html), "acao": "apagar_chave",
                          "provedor": "deepseek"}, follow_redirects=True)
    assert not PROV.tem_chave(_pasta(admin), "deepseek")


def test_a_chave_da_ajuda_e_emprestada_para_a_anthropic(admin):
    """A casa já informou a chave do Claude na Ajuda; pedir de novo seria pedir
    duas vezes a mesma coisa — e alguém acabaria gravando a errada."""
    import agente_provedores as PROV

    (_pasta(admin) / PROV.ARQUIVO_DA_AJUDA).write_text(
        '{"api_key": "sk-ant-da-ajuda"}', encoding="utf-8")
    assert PROV.tem_chave(_pasta(admin), "claude")
    html = admin["c"].get("/agente/configurar").get_data(as_text=True)
    assert "emprestada" in html


# ------------------------------------------------------------ a escrita


def test_a_escrita_nasce_desligada(admin):
    """**CAPACIDADE NASCE DESLIGADA** — a mesma regra da ajuda."""
    import agente_schema as AGS

    con = _con(admin)
    assert AGS.escrita_ligada(con) is False
    con.close()


def test_ligar_a_escrita_pela_tela(admin):
    import agente_schema as AGS

    html = admin["c"].get("/agente/configurar").get_data(as_text=True)
    resposta = admin["c"].post(
        "/agente/configurar",
        data={"csrf_token": _token(html), "acao": "config",
              "provedor_padrao": "deepseek", "modelo_padrao": "deepseek-chat",
              "teto_de_turnos": "10", "teto_de_sessoes": "5",
              "escrita_ligada": "on"}, follow_redirects=True)
    assert "escrita LIGADA" in resposta.get_data(as_text=True)
    con = _con(admin)
    assert AGS.escrita_ligada(con) is True
    assert AGS.teto_de_turnos(con) == 10
    con.close()


def test_o_teto_digitado_e_preso_no_limite(admin):
    """Quem digita 900 na tela não pode achar que tem 900.

    Prender calado e DIZER o que valeu é melhor que recusar: a tela mostra o
    número que passou a valer, e a diferença fica visível em vez de virar um
    erro que ninguém sabe explicar.
    """
    import agente_schema as AGS

    html = admin["c"].get("/agente/configurar").get_data(as_text=True)
    resposta = admin["c"].post(
        "/agente/configurar",
        data={"csrf_token": _token(html), "acao": "config",
              "teto_de_turnos": "900", "teto_de_sessoes": "900"},
        follow_redirects=True)
    texto = resposta.get_data(as_text=True)
    assert f"até {AGS.TETO_MAXIMO_DE_TURNOS} turnos" in texto
    con = _con(admin)
    assert AGS.teto_de_turnos(con) == AGS.TETO_MAXIMO_DE_TURNOS
    assert AGS.teto_de_sessoes(con) == AGS.TETO_MAXIMO_DE_SESSOES
    con.close()


def test_a_tela_de_configurar_mostra_os_provedores(admin):
    """DeepSeek é a razão de o seletor existir — e o pedido do oficial."""
    html = admin["c"].get("/agente/configurar").get_data(as_text=True)
    for nome in ("DeepSeek", "Claude", "GPT", "Grok"):
        assert nome in html, f"o provedor {nome} não aparece na tela"


# ------------------------------------------------------- GET não grava


def test_GET_nao_grava_nada(admin):
    """Tela de leitura que grava fica presa no `busy_timeout` enquanto outro
    balcão lavra — e nenhuma das duas telas precisa escrever para aparecer."""
    con = _con(admin)
    antes = [tuple(r) for r in con.execute("SELECT * FROM ag_config")]
    con.close()
    for _ in range(2):
        admin["c"].get("/agente/configurar")
    con = _con(admin)
    assert con.execute(
        "SELECT COUNT(*) c FROM ag_sessoes").fetchone()["c"] == 0
    depois = [tuple(r) for r in con.execute("SELECT * FROM ag_config")]
    con.close()
    assert antes == depois


# --------------------------------------------------- a sessão desenhada


# ------------------------------------- a mudança proposta (LS03, M4 — LX13)


def test_ligar_a_escrita_nao_desliga_a_confirmacao(admin):
    """**M4.** A caixa do «aplicar sozinho» é outra, e nasce desmarcada: o
    formulário que liga a escrita sem marcá-la deixa o agente só propondo."""
    import agente_schema as AGS

    html = admin["c"].get("/agente/configurar").get_data(as_text=True)
    assert "aplicar sozinho" in html
    admin["c"].post(
        "/agente/configurar",
        data={"csrf_token": _token(html), "acao": "config",
              "provedor_padrao": "deepseek", "modelo_padrao": "",
              "teto_de_turnos": "10", "teto_de_sessoes": "5",
              "escrita_ligada": "on"}, follow_redirects=True)
    con = _con(admin)
    assert AGS.escrita_ligada(con) is True
    assert AGS.escrita_sem_confirmacao(con) is False
    con.close()


