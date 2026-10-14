"""
Testes das TELAS da ajuda do sistema.

POR QUE TELA, E NAO SO DOMINIO
    "Buraco de tela nao aparece em teste de dominio" e a licao que se repetiu
    cinco vezes nesta revisao. E aqui ha uma segunda razao: o pedido do oficial
    — "apenas para o administrador, COM OPCAO DE EXPANDIR" — so se cumpre de
    verdade se a expansao existir NA TELA. Testar so o dominio provaria que a
    funcao existe, e nao que alguem consegue chama-la.

O QUE ELES CONFEREM
      - o ADMIN entra; o escrevente NAO, e a tela diz quem pode;
      - o escrevente mandando POST direto na rota tambem e recusado — pelo
        DOMINIO, sem passar por tela nenhuma;
      - CONFIGURAR e so do ADMIN, mesmo depois de a consulta ser aberta para
        todos: quem muda a regra nao pode ser quem a regra alcanca;
      - EXPANDIR PELA TELA funciona, e depois dela o escrevente entra;
      - a CHAVE vai para o ARQUIVO, e nao para o banco;
      - "Ver o que sairia" NAO manda nada — quem manda dado para fora tem
        direito de ver antes;
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
    return {"app": app, "c": c, "banco": banco, "dados": dados}


@pytest.fixture()
def admin(cg_casa):
    return _sessao(cg_casa, "ADMIN")


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


# ------------------------------------------------------- quem entra


def test_o_administrador_entra(admin):
    html = admin["c"].get("/ajuda").get_data(as_text=True)
    assert "Perguntar" in html
    assert "não está liberada" not in html


def test_o_escrevente_nao_entra_e_a_tela_diz_quem_pode(cg_casa):
    """O pedido do oficial em 26/08/2026: por enquanto, só o administrador."""
    s = _sessao(cg_casa, "USER")
    html = s["c"].get("/ajuda").get_data(as_text=True)
    assert "não está liberada para o seu perfil" in html
    assert "ADMIN" in html


def test_o_menu_esconde_a_ajuda_de_quem_nao_pode(cg_casa):
    s = _sessao(cg_casa, "USER")
    html = s["c"].get("/").get_data(as_text=True)
    assert "Ajuda do sistema</a>" not in html


def test_o_menu_mostra_a_ajuda_para_o_administrador(admin):
    html = admin["c"].get("/").get_data(as_text=True)
    assert "Ajuda do sistema" in html


def test_o_escrevente_mandando_POST_direto_tambem_e_recusado(cg_casa):
    """A tela esconde por educação; o DOMÍNIO recusa por dever.

    Este teste não passa por tela nenhuma: manda o POST na rota, como faria
    quem digitasse a URL.
    """
    s = _sessao(cg_casa, "USER")
    html = s["c"].get("/").get_data(as_text=True)
    resposta = s["c"].post("/ajuda",
                           data={"csrf_token": _token(html),
                                 "pergunta": "uma dúvida qualquer",
                                 "acao": "perguntar"},
                           follow_redirects=True)
    texto = resposta.get_data(as_text=True)
    assert resposta.status_code == 200
    assert "liberada" in texto
    con = _con(s)
    assert con.execute(
        "SELECT COUNT(*) c FROM aj_consultas").fetchone()["c"] == 0
    con.close()


def test_configurar_e_so_do_administrador(cg_casa):
    s = _sessao(cg_casa, "MANAGER")
    resposta = s["c"].get("/ajuda/configurar")
    assert resposta.status_code in (302, 403)


# --------------------------------------------------- a opção de expandir


def test_expandir_pela_tela_e_depois_o_escrevente_entra(admin, tmp_path):
    """A OUTRA METADE DO PEDIDO: «com opção de expandir».

    Não basta a função existir no domínio — o oficial tem de conseguir
    chamá-la sozinho, num sábado, sem programador no meio.
    """
    html = admin["c"].get("/ajuda/configurar").get_data(as_text=True)
    assert "Hoje só o administrador consulta" in html
    admin["c"].post("/ajuda/configurar",
                    data={"csrf_token": _token(html), "acao": "perfis",
                          "perfis": ["MANAGER", "USER"],
                          "motivo": "abrir para o balcão"},
                    follow_redirects=True)
    con = _con(admin)
    import ajuda as AJ
    assert AJ.pode_usar(con, "USER")
    linha = con.execute("SELECT * FROM aj_config WHERE id=1").fetchone()
    assert "abrir para o balcão" in linha["alterada_motivo"]
    con.close()


def test_a_mudanca_de_acesso_fica_na_auditoria(admin):
    html = admin["c"].get("/ajuda/configurar").get_data(as_text=True)
    admin["c"].post("/ajuda/configurar",
                    data={"csrf_token": _token(html), "acao": "perfis",
                          "perfis": ["USER"], "motivo": "teste"},
                    follow_redirects=True)
    con = _con(admin)
    linha = con.execute(
        "SELECT * FROM audit_logs WHERE action='AJUDA_ACESSO_ALTERADO'"
    ).fetchone()
    con.close()
    assert linha is not None


def test_configurar_continua_so_do_admin_depois_de_expandir(cg_casa):
    """Quem muda a regra não pode ser quem a regra alcança."""
    dono = _sessao(cg_casa, "ADMIN")
    html = dono["c"].get("/ajuda/configurar").get_data(as_text=True)
    dono["c"].post("/ajuda/configurar",
                   data={"csrf_token": _token(html), "acao": "perfis",
                         "perfis": ["USER"]}, follow_redirects=True)
    # O mesmo banco, agora com um escrevente.
    from database import Database
    Database(dono["banco"]).create_user("escrevente", "ANA", SENHA, "USER")
    c = dono["app"].test_client()
    c.post("/login", data={"username": "escrevente", "password": SENHA,
                           "csrf_token": _token(
                               c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    assert "Perguntar" in c.get("/ajuda").get_data(as_text=True)
    assert c.get("/ajuda/configurar").status_code in (302, 403)


# --------------------------------------------------------- a chave


def test_a_chave_vai_para_o_arquivo_e_nao_para_o_banco(admin):
    """O banco viaja no backup, e o backup já saiu da serventia.

    **O ARQUIVO É `agente.cred` DESDE 14/09/2026**, e o nome sai do seletor em
    vez de ser escrito aqui: o dia em que ele mudar de nome outra vez, este
    teste continua medindo a mesma coisa — o que está em disco —, e não o nome
    que ele tinha quando foi escrito.
    """
    import agente_provedores as PROV
    html = admin["c"].get("/ajuda/configurar").get_data(as_text=True)
    admin["c"].post("/ajuda/configurar",
                    data={"csrf_token": _token(html), "acao": "chave",
                          "api_key": "sk-ant-teste-1234567890"},
                    follow_redirects=True)
    arquivo = PROV.caminho_da_credencial(admin["dados"])
    assert arquivo.is_file()
    assert "sk-ant-teste" in arquivo.read_text(encoding="utf-8")
    # E não está em lugar nenhum do banco.
    con = _con(admin)
    tabelas = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    achou = False
    for t in tabelas:
        linhas = con.execute(f'SELECT * FROM "{t}"').fetchall()
        if any("sk-ant-teste" in str(dict(x)) for x in linhas):
            achou = True
    con.close()
    assert not achou, "a chave da API entrou no banco"


def test_chave_com_forma_errada_e_recusada(admin):
    html = admin["c"].get("/ajuda/configurar").get_data(as_text=True)
    resposta = admin["c"].post(
        "/ajuda/configurar",
        data={"csrf_token": _token(html), "acao": "chave",
              "api_key": "isto nao e uma chave"}, follow_redirects=True)
    assert "não tem forma de chave" in resposta.get_data(as_text=True)
    # **E NADA FOI GRAVADO.** Recusar depois de gravar seria pior que não
    # recusar: o arquivo ficaria com a chave errada e a tela diria que deu
    # certo. Nenhum dos dois nomes pode existir — o de hoje e o de antes da
    # mudança, que alguém pode ter deixado no disco.
    assert not (admin["dados"] / "agente.cred").is_file()
    assert not (admin["dados"] / "claude.cred").is_file()


def test_sem_chave_a_tela_avisa(admin):
    html = admin["c"].get("/ajuda").get_data(as_text=True)
    assert "chave da API ainda não foi informada" in html


# ------------------------------------------------ ver antes de mandar


def test_ver_o_que_sairia_nao_manda_nada(admin):
    """Quem manda dado para fora tem direito de ver o que está mandando."""
    html = admin["c"].get("/ajuda").get_data(as_text=True)
    resposta = admin["c"].post(
        "/ajuda", data={"csrf_token": _token(html), "acao": "prever",
                        "pergunta": "o CPF 000.000.048-55 não passa",
                        "assunto": "ERRO"}, follow_redirects=True)
    texto = resposta.get_data(as_text=True)
    assert "Nada foi enviado" in texto

    # A CONFERÊNCIA É NA PRÉVIA, e não na página inteira — de propósito.
    #
    # O CPF inteiro APARECE na página, no campo onde a pessoa o digitou, e
    # isso está certo: ele está no navegador de quem o escreveu, e apagá-lo
    # faria o escrevente perder o que digitou. O que não pode sair com ele é
    # o texto que VAI para fora.
    #
    # Uma asserção sobre a página toda pegaria o campo e daria falso positivo
    # — foi o que aconteceu na primeira versão deste teste.
    previa = texto.split("O que sairia da serventia", 1)[1]
    assert "[CPF_01]" in previa
    assert "000.000.048-55" not in previa
    con = _con(admin)
    assert con.execute(
        "SELECT COUNT(*) c FROM aj_consultas").fetchone()["c"] == 0
    con.close()


def test_post_antigo_nao_consegue_desligar_a_protecao(admin):
    html = admin["c"].get("/ajuda").get_data(as_text=True)
    resposta = admin["c"].post(
        "/ajuda", data={"csrf_token": _token(html), "acao": "prever",
                        "pergunta": "CPF 000.000.048-55",
                        "assunto": "ERRO", "mascarar": "0"},
        follow_redirects=True)
    previa = resposta.get_data(as_text=True).split(
        "O que sairia da serventia", 1)[1]
    assert "000.000.048-55" not in previa
    assert "[CPF_01]" in previa


def test_a_tela_nao_oferece_excecao_sem_mascara(admin):
    html = admin["c"].get("/ajuda").get_data(as_text=True)
    assert 'name="mascarar"' not in html
    assert "Mandar CPF e telefone por inteiro" not in html
    assert "não pode ser desativada" in html


def test_abrir_a_tela_nao_grava_nada(admin):
    """GET não abre transação de escrita."""
    admin["c"].get("/ajuda")
    admin["c"].get("/ajuda")
    con = _con(admin)
    assert con.execute(
        "SELECT COUNT(*) c FROM aj_consultas").fetchone()["c"] == 0
    con.close()


def test_a_tela_diz_que_a_ajuda_nao_decide(admin):
    """É a regra do usucapião, e ela precisa estar onde a pessoa lê."""
    html = admin["c"].get("/ajuda").get_data(as_text=True)
    assert "auxilia; não decide" in html
