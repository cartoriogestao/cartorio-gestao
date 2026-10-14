"""
Testes da tela do selador.

O QUE ELES DEFENDEM
    Que a senha nao aparece na tela. Nem no valor de um campo, nem na mensagem
    de sucesso, nem no HTML de lugar nenhum — e o teste procura a senha inteira
    no corpo da resposta, e nao confia em inspecao visual.

    E que a tela DIZ o que falta, em vez de deixar o escrevente descobrir na
    hora de selar que o sistema nunca teve o endereco.
"""
from __future__ import annotations

import glob
import os
import re
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — pode tocar caminhos de selador/prod
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# A PASTA LEVA O NOME DO NUCLEO QUE ESTA RODANDO — e o motivo tem data.
#
# Em 30/08/2026 a suite passou a rodar em paralelo, e este arquivo ficou
# vermelho uma vez so, sem se reproduzir. A causa: o preparo abaixo APAGA esta
# pasta para comecar limpo, e o paralelismo reparte teste a teste, nao arquivo
# a arquivo. Dois nucleos pegavam dois testes DESTE arquivo ao mesmo tempo, e
# cada um apagava o banco debaixo do outro.
#
# Da para evitar pela linha de comando (`--dist loadfile`), e nao e o que se
# faz aqui: isso obriga alguem a lembrar de uma opcao para sempre, e quem
# esquecer nao recebe erro — recebe um vermelho intermitente daqui a semanas.
# **O arquivo se protege sozinho.**
DADOS = ("/tmp/test_selador_web_dados_"
         + os.environ.get("PYTEST_XDIST_WORKER", "solo"))
SENHA_DO_SELADOR = "abcde123"
USUARIO_DO_SELADOR = "fulano.detal123"
LOCAL = "https://192.168.0.200:443"


@pytest.fixture(scope="module")
def app():
    import shutil
    shutil.rmtree(DADOS, ignore_errors=True)
    from app import create_app
    return create_app({"DATA_DIR": DADOS})


@pytest.fixture(scope="module")
def cliente(app):
    from database import Database
    d = Database(Path(glob.glob(f"{DADOS}/*.sqlite3")[0]))
    try:
        d.create_user("selo", "Oficial", "Senha#12345", "ADMIN")
    except Exception:                                          # noqa: BLE001
        pass
    c = app.test_client()
    html = c.get("/login").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    c.post("/login", data={"username": "selo", "password": "Senha#12345",
                           "csrf_token": token}, follow_redirects=True)
    return c


def csrf(cliente, caminho="/selador") -> str:
    html = cliente.get(caminho).get_data(as_text=True)
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    return achado.group(1) if achado else ""


def postar(cliente, dados: dict):
    dados = dict(dados, csrf_token=csrf(cliente))
    r = cliente.post("/selador", data=dados, follow_redirects=True)
    return r.get_data().decode("utf-8", errors="replace")


# ------------------------------------------------------------------ a tela

def test_a_tela_abre_e_diz_o_que_falta(cliente):
    html = cliente.get("/selador").get_data(as_text=True)
    assert "Selador — configuração" in html
    assert "Falta para o sistema poder selar" in html
    assert "rede local" in html


def test_a_tela_avisa_que_nao_cai_no_endereco_de_fabrica(cliente):
    import selador
    html = cliente.get("/selador").get_data(as_text=True)
    assert selador.BASE_PRODUCAO in html
    assert "selo comprado duas vezes" in html


def test_a_tela_esta_no_menu(cliente):
    html = cliente.get("/selador").get_data(as_text=True)
    assert "Selador — configuração</a>" in html


# ------------------------------------------------------------- gravar

def test_gravar_a_mao_guarda_a_senha_fora_do_banco(cliente):
    import sqlite3

    import selador_config as SC
    html = postar(cliente, {"acao": "gravar", "base_url": LOCAL,
                            "ambiente": "PRODUCAO",
                            "usuario": USUARIO_DO_SELADOR,
                            "senha": SENHA_DO_SELADOR})
    assert "gravada" in html.lower()
    # A senha NAO aparece na tela.
    assert SENHA_DO_SELADOR not in html
    # Nem no banco.
    banco = Path(glob.glob(f"{DADOS}/*.sqlite3")[0])
    con = sqlite3.connect(banco)
    con.row_factory = sqlite3.Row
    for tabela in [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]:
        for linha in con.execute(f"SELECT * FROM {tabela}"):
            for valor in tuple(linha):
                assert SENHA_DO_SELADOR not in str(valor), tabela
    con.close()
    # Mas o arquivo proprio tem.
    cred = SC.ler_credencial(Path(DADOS))
    assert cred["senha"] == SENHA_DO_SELADOR


def test_depois_de_gravar_a_tela_mostra_o_usuario_mascarado(cliente):
    html = cliente.get("/selador").get_data(as_text=True)
    assert "fu***********23" in html
    assert USUARIO_DO_SELADOR not in html
    assert SENHA_DO_SELADOR not in html
    assert "rede local</span>" in html


def test_a_tela_nao_repoe_a_senha_no_campo(cliente):
    html = cliente.get("/selador").get_data(as_text=True)
    campo = re.search(r'<input type="password"[^>]*>', html).group(0)
    assert "value=" not in campo
    assert "deixe em branco para manter a atual" in campo


def test_gravar_sem_trocar_a_senha_mantem_a_que_estava(cliente):
    import selador_config as SC
    postar(cliente, {"acao": "gravar", "base_url": LOCAL,
                     "ambiente": "PRODUCAO", "usuario": USUARIO_DO_SELADOR,
                     "senha": ""})
    assert SC.ler_credencial(Path(DADOS))["senha"] == SENHA_DO_SELADOR


def test_endereco_sem_protocolo_volta_com_a_mensagem(cliente):
    html = postar(cliente, {"acao": "gravar", "base_url": "192.168.0.200",
                            "ambiente": "PRODUCAO"})
    assert "http:// ou https://" in html


def test_homologacao_sem_endereco_e_recusada_na_tela(cliente):
    html = postar(cliente, {"acao": "gravar", "base_url": LOCAL,
                            "ambiente": "HOMOLOGACAO"})
    assert "achando que era teste" in html


# --------------------------------------------------------- o certificado

def test_a_tela_explica_por_que_se_fixa_o_certificado(cliente):
    html = cliente.get("/selador").get_data(as_text=True)
    assert "certificado próprio" in html
    assert "se passar pelo selador" in html
    assert "não conferido" in html


def test_sem_certificado_a_tela_avisa_que_a_senha_nao_sai(cliente):
    html = cliente.get("/selador").get_data(as_text=True)
    assert "o sistema não manda a senha da" in html
    assert "É de propósito." in html


def _trecho_do_aviso(html: str) -> str:
    """O pedaco da tela que interessa quando o teste cai — e nao o HTML todo,
    que sao dezenas de milhares de caracteres de menu."""
    marca = re.search(r"(alerta|aviso|danger|erro)", html)
    i = max(0, marca.start() - 200) if marca else 0
    return html[i:i + 900]


def test_ver_certificado_de_selador_fora_do_ar_da_frase_de_balcao(cliente):
    """A tela tem de dizer o que houve **em frase de balcao**, e nao traceback.

    QUANDO ESTE TESTE FALHAR, A MENSAGEM MOSTRA O QUE A TELA DISSE. Em
    30/08/2026 ele caiu uma vez e eu nao soube por que, porque o assert so
    dizia "falso" — a causa era a pasta de nome fixo, consertada la em cima.
    Diagnosticar custou uma corrida inteira da suite, e a corrida inteira sao
    quinze minutos.

    E as frases saem do MODULO, e nao de uma lista escrita aqui: quatro frases
    copiadas a mao sao uma segunda lista, e ela diverge no primeiro conserto do
    `_falha_de_rede` — o teste passaria a cobrar um texto que o sistema nao
    escreve mais.
    """
    import socket

    import selador_cliente as CL

    # Porta 1 de localhost: ninguém escuta ali, em máquina nenhuma. Apontar
    # para um IP de rede privada aqui seria pior do que inútil — ver o teste
    # abaixo.
    base = "https://127.0.0.1:1"
    postar(cliente, {"acao": "gravar", "base_url": base,
                     "ambiente": "PRODUCAO"})
    html = postar(cliente, {"acao": "ver_certificado"})

    # Uma frase por erro de rede que o modulo distingue, mais o arremate. Qual
    # delas sai depende de como a maquina recusa a porta 1, e isso varia.
    possiveis = [CL._falha_de_rede(base, erro) for erro in (
        socket.timeout("timed out"),
        ConnectionRefusedError("refused"),
        socket.gaierror("getaddrinfo failed"),
        OSError("outra coisa qualquer"),
    )]
    # O comeco de cada frase e estavel; o fim do arremate traz o texto do erro.
    assert any(f[:40] in html for f in possiveis), (
        "a tela nao deu frase de balcao para selador fora do ar.\n"
        "esperava comecar por alguma destas:\n  "
        + "\n  ".join(f[:40] for f in possiveis)
        + "\ne a tela disse, no trecho do aviso:\n"
        + _trecho_do_aviso(html))


def test_endereco_de_rede_privada_responde_coisa_diferente_em_cada_rede(cliente):
    """Por que fixar o certificado não é preciosismo.

    `192.168.0.200` é endereço de rede PRIVADA: em cada rede ele é outra
    máquina. Rodando este teste fora do cartório, esse endereço chegou a
    responder — apresentando um certificado de `commonName=default.domain`,
    que não é o selador de ninguém.

    É exatamente isso que a fixação impede: o sistema só fala com quem
    apresentar o certificado que o oficial conferiu. Sem ela, bastaria o
    computador estar na rede errada para a senha da serventia ir para um
    estranho.
    """
    import selador_config as SC
    assert SC._e_rede_local("https://192.168.0.200:443") is True


def test_fixar_certificado_de_maquina_fora_do_ar_nao_grava_nada(cliente):
    import selador_cliente as CL
    postar(cliente, {"acao": "fixar_certificado", "sha256": "00" * 32})
    import sqlite3
    banco = Path(glob.glob(f"{DADOS}/cartorio_gestao.sqlite3")[0])
    con = sqlite3.connect(banco)
    con.row_factory = sqlite3.Row
    assert CL.certificado_fixado(con) is None
    con.close()


# ---------------------------------------------------------------- o teste

def test_testar_diz_em_que_passo_parou(cliente):
    html = postar(cliente, {"acao": "testar"})
    assert "Parou em" in html


def test_o_teste_fica_na_auditoria(cliente):
    import sqlite3
    banco = Path(glob.glob(f"{DADOS}/cartorio_gestao.sqlite3")[0])
    con = sqlite3.connect(banco)
    con.row_factory = sqlite3.Row
    linhas = [dict(r) for r in con.execute(
        "SELECT * FROM audit_logs WHERE action='SELADOR_TESTADO'")]
    con.close()
    assert linhas


# ------------------------------------------------------- selo nao usado

def test_a_tela_de_selo_nao_usado_existe_e_explica_o_defeito_antigo(cliente):
    html = cliente.get("/selador").get_data(as_text=True)
    assert "Selos obtidos e não usados" in html
    assert "1.304 selos assim" in html
    assert "Nenhum." in html


# ------------------------------------------------------------- apagar

def test_apagar_a_credencial_deixa_a_tela_dizendo_o_que_falta(cliente):
    import selador_config as SC
    html = postar(cliente, {"acao": "apagar_credencial"})
    assert "não vai selar" in html
    assert SC.ler_credencial(Path(DADOS)) is None
    depois = cliente.get("/selador").get_data(as_text=True)
    assert "Faltam o usuário e a senha" in depois


def test_acao_desconhecida_nao_derruba_a_tela(cliente):
    html = postar(cliente, {"acao": "voar"})
    assert "Ação desconhecida" in html


# ------------------------------------------------------- importar do acervo

def test_importar_do_eoficio_preenche_tudo_sem_mostrar_a_senha(cliente):
    import sqlite3

    import selador_config as SC
    acervo = Path(DADOS) / "acervo_eoficio.sqlite3"
    con = sqlite3.connect(acervo)
    con.execute("""CREATE TABLE IF NOT EXISTS tbSeladorConfiguracao
                   (strUrlSelador TEXT, strUsername TEXT, strPassword TEXT)""")
    con.execute("DELETE FROM tbSeladorConfiguracao")
    con.execute("INSERT INTO tbSeladorConfiguracao VALUES (?,?,?)",
                (LOCAL, USUARIO_DO_SELADOR, SENHA_DO_SELADOR))
    con.commit()
    con.close()

    html = postar(cliente, {"acao": "importar"})
    assert "Configuração trazida do E-Ofício" in html
    assert SENHA_DO_SELADOR not in html
    assert USUARIO_DO_SELADOR not in html          # sai mascarado
    assert "só vai selar de dentro do escritório" in html
    assert SC.ler_credencial(Path(DADOS))["senha"] == SENHA_DO_SELADOR


def test_a_auditoria_do_import_nao_guarda_a_senha(cliente):
    import sqlite3
    banco = Path(glob.glob(f"{DADOS}/cartorio_gestao.sqlite3")[0])
    con = sqlite3.connect(banco)
    con.row_factory = sqlite3.Row
    linhas = [dict(r) for r in con.execute(
        "SELECT * FROM audit_logs WHERE action LIKE 'SELADOR%'")]
    con.close()
    assert linhas, "o import tem de ficar na auditoria"
    assert SENHA_DO_SELADOR not in str(linhas)
