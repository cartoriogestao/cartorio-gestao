"""
Testes da configuracao do selador.

A REGRA QUE MAIS IMPORTA AQUI
    A SENHA NAO ENTRA NO BANCO. O banco viaja — vai no backup e uma copia dele
    ja foi parar fora da serventia para ensaiar a correcao de 18/08. A senha
    fica num arquivo proprio da pasta de dados, ao lado do `secret.key`, que o
    backup nao alcanca.

    `test_a_senha_nunca_entra_no_banco` e
    `test_a_situacao_nunca_devolve_a_senha` existem para que isso nao volte
    atras por descuido de alguem que ache mais pratico guardar tudo junto.

A SEGUNDA REGRA
    NAO CAIR NO ENDERECO DE FABRICA. Esta casa sela em `192.168.0.200`, na rede
    local. Cair no endereco da nuvem quando a configuracao falta mandaria o
    pedido para o Tribunal — 401 no meio do atendimento, ou selo comprado duas
    vezes.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — referencia acervo_eoficio ou sqlite de producao
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import selador                                   # noqa: E402
import selador_config as SC                      # noqa: E402

AGORA = "2026-08-21T15:00:00"
LOCAL = "https://192.168.0.200:443"
USUARIO = "fulano.detal123"
SENHA = "abcde123"


def banco() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    SC.init_selador_schema(con)
    return con


# --------------------------------------------------------------- o segredo

def test_a_senha_nunca_entra_no_banco(tmp_path):
    con = banco()
    SC.gravar(con, base_url=LOCAL, usuario=USUARIO, agora=AGORA)
    SC.gravar_credencial(tmp_path, USUARIO, SENHA, agora=AGORA)
    # Varre o banco inteiro atras da senha.
    for tabela in [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]:
        for linha in con.execute(f"SELECT * FROM {tabela}"):
            for valor in tuple(linha):
                assert SENHA not in str(valor), tabela


def test_a_credencial_vive_em_arquivo_proprio_na_pasta_de_dados(tmp_path):
    SC.gravar_credencial(tmp_path, USUARIO, SENHA, agora=AGORA,
                         usuario_do_sistema="TESTE")
    alvo = SC.caminho_da_credencial(tmp_path)
    assert alvo.name == "selador.cred"
    guardado = json.loads(alvo.read_text(encoding="utf-8"))
    assert guardado["usuario"] == USUARIO and guardado["senha"] == SENHA
    assert guardado["gravado_por"] == "TESTE"
    # E nao sobra o arquivo provisorio da gravacao.
    assert not list(tmp_path.glob("*.novo"))


def test_a_situacao_nunca_devolve_a_senha(tmp_path):
    con = banco()
    SC.gravar(con, base_url=LOCAL, usuario=USUARIO, agora=AGORA)
    SC.gravar_credencial(tmp_path, USUARIO, SENHA, agora=AGORA)
    estado = SC.situacao(con, tmp_path)
    assert SENHA not in json.dumps(estado, ensure_ascii=False)
    assert estado["tem_credencial"] is True
    assert estado["usuario"] == "fu***********23"   # mascarado


def test_so_uma_funcao_no_sistema_devolve_a_senha(tmp_path):
    con = banco()
    SC.gravar(con, base_url=LOCAL, usuario=USUARIO, agora=AGORA)
    SC.gravar_credencial(tmp_path, USUARIO, SENHA, agora=AGORA)
    pronto = SC.credencial_para_autenticar(con, tmp_path)
    assert pronto["senha"] == SENHA
    assert pronto["base"] == LOCAL
    assert pronto["client_id"] == selador.CLIENT_ID


def test_a_credencial_pela_metade_e_recusada(tmp_path):
    with pytest.raises(SC.ConfigError):
        SC.gravar_credencial(tmp_path, "", SENHA, agora=AGORA)
    with pytest.raises(SC.ConfigError):
        SC.gravar_credencial(tmp_path, USUARIO, "", agora=AGORA)


def test_apagar_a_credencial_some_com_o_arquivo(tmp_path):
    SC.gravar_credencial(tmp_path, USUARIO, SENHA, agora=AGORA)
    assert SC.apagar_credencial(tmp_path) is True
    assert SC.ler_credencial(tmp_path) is None
    assert SC.apagar_credencial(tmp_path) is False


def test_credencial_corrompida_nao_derruba_a_tela(tmp_path):
    SC.caminho_da_credencial(tmp_path).write_text("{isto nao e json",
                                                  encoding="utf-8")
    assert SC.ler_credencial(tmp_path) is None


# --------------------------------------------------------------- o endereco

def test_o_sistema_nao_cai_no_endereco_de_fabrica(tmp_path):
    con = banco()
    assert SC.base_em_uso(con) is None
    SC.gravar(con, base_url=LOCAL, usuario=USUARIO, agora=AGORA)
    assert SC.base_em_uso(con) == LOCAL
    assert SC.base_em_uso(con) != selador.BASE_PRODUCAO


def test_a_tela_avisa_que_o_selador_e_da_rede_local(tmp_path):
    con = banco()
    SC.gravar(con, base_url=LOCAL, usuario=USUARIO, agora=AGORA)
    SC.gravar_credencial(tmp_path, USUARIO, SENHA, agora=AGORA)
    assert SC.situacao(con, tmp_path)["na_rede_local"] is True
    SC.gravar(con, base_url=selador.BASE_PRODUCAO, usuario=USUARIO, agora=AGORA)
    assert SC.situacao(con, tmp_path)["na_rede_local"] is False


@pytest.mark.parametrize("url,local", [
    ("https://192.168.0.200:443", True),
    ("https://10.0.0.5", True),
    ("http://172.16.4.1:8080", True),
    ("http://172.32.4.1", False),
    ("https://localhost:9443", True),
    ("https://selador.ma.portalselo.com.br:9443", False),
])
def test_o_que_e_rede_local_e_o_que_nao_e(url, local):
    assert SC._e_rede_local(url) is local


def test_endereco_sem_protocolo_e_recusado():
    con = banco()
    with pytest.raises(SC.ConfigError) as erro:
        SC.gravar(con, base_url="192.168.0.200:443", agora=AGORA)
    assert "http:// ou https://" in str(erro.value)


def test_a_barra_do_fim_do_endereco_nao_vira_barra_dupla():
    con = banco()
    SC.gravar(con, base_url=LOCAL + "/", agora=AGORA)
    assert SC.base_em_uso(con) == LOCAL


# --------------------------------------------------------------- ambiente

def test_homologacao_sem_endereco_de_homologacao_e_recusada():
    # Deixar o ambiente em homologacao sem o endereco faria o sistema selar na
    # PRODUCAO achando que era teste. Selo verdadeiro, cobrado.
    con = banco()
    with pytest.raises(SC.ConfigError) as erro:
        SC.gravar(con, base_url=LOCAL, ambiente="HOMOLOGACAO", agora=AGORA)
    assert "selar na produção achando que era teste" in str(erro.value)


def test_o_ambiente_escolhe_o_endereco():
    con = banco()
    SC.gravar(con, base_url=LOCAL, base_homologacao="https://192.168.0.200:8443",
              ambiente="HOMOLOGACAO", agora=AGORA)
    assert SC.base_em_uso(con) == "https://192.168.0.200:8443"


def test_ambiente_inventado_e_recusado():
    con = banco()
    with pytest.raises(SC.ConfigError):
        SC.gravar(con, base_url=LOCAL, ambiente="TESTE", agora=AGORA)


# ------------------------------------------------------------ o que falta

def test_sem_nada_configurado_a_tela_diz_o_que_falta(tmp_path):
    con = banco()
    estado = SC.situacao(con, tmp_path)
    assert estado["pronto"] is False
    assert len(estado["faltas"]) == 3
    assert any("rede local" in f for f in estado["faltas"])


def test_autenticar_sem_configuracao_recusa_com_a_lista(tmp_path):
    con = banco()
    with pytest.raises(SC.ConfigError) as erro:
        SC.credencial_para_autenticar(con, tmp_path)
    assert "usuário e a senha" in str(erro.value)


def test_o_teste_de_conexao_fica_gravado():
    con = banco()
    SC.gravar(con, base_url=LOCAL, agora=AGORA)
    SC.registrar_teste(con, ok=False, mensagem="tempo esgotado", agora=AGORA)
    linha = con.execute("SELECT * FROM sd_config").fetchone()
    assert linha["ultimo_teste_ok"] == 0
    assert linha["ultimo_teste_mensagem"] == "tempo esgotado"


# ------------------------------------------------------- vindo do E-Oficio

def acervo_falso(tmp_path, url=LOCAL, usuario=USUARIO, senha=SENHA) -> Path:
    caminho = tmp_path / "acervo_eoficio.sqlite3"
    con = sqlite3.connect(caminho)
    con.execute("""CREATE TABLE tbSeladorConfiguracao
                   (strUrlSelador TEXT, strUsername TEXT, strPassword TEXT)""")
    con.execute("INSERT INTO tbSeladorConfiguracao VALUES (?,?,?)",
                (url, usuario, senha))
    con.commit()
    con.close()
    return caminho


def test_importar_do_eoficio_preenche_os_dois_lugares(tmp_path):
    con = banco()
    acervo = acervo_falso(tmp_path)
    dados = tmp_path / "dados"
    resumo = SC.importar_do_eoficio(con, acervo, dados, agora=AGORA,
                                    usuario_do_sistema="TESTE")
    assert resumo["base_url"] == LOCAL
    assert resumo["na_rede_local"] is True
    assert SENHA not in json.dumps(resumo, ensure_ascii=False)
    estado = SC.situacao(con, dados)
    assert estado["pronto"] is True and estado["origem"] == "E-OFICIO"
    assert SC.credencial_para_autenticar(con, dados)["senha"] == SENHA


def test_importar_de_acervo_incompleto_recusa_dizendo_o_que_falta(tmp_path):
    con = banco()
    acervo = acervo_falso(tmp_path, senha="")
    with pytest.raises(SC.ConfigError) as erro:
        SC.importar_do_eoficio(con, acervo, tmp_path / "d", agora=AGORA)
    assert "senha" in str(erro.value)


def test_importar_sem_acervo_da_mensagem_de_balcao(tmp_path):
    con = banco()
    with pytest.raises(SC.ConfigError) as erro:
        SC.importar_do_eoficio(con, tmp_path / "nao_existe.sqlite3",
                               tmp_path, agora=AGORA)
    assert "acervo_eoficio.sqlite3" in str(erro.value)


def test_importar_de_acervo_sem_a_tabela_explica(tmp_path):
    caminho = tmp_path / "vazio.sqlite3"
    sqlite3.connect(caminho).close()
    con = banco()
    with pytest.raises(SC.ConfigError) as erro:
        SC.importar_do_eoficio(con, caminho, tmp_path, agora=AGORA)
    assert "não guardava a configuração do selador" in str(erro.value)


def test_ler_do_eoficio_nao_escreve_no_acervo(tmp_path):
    acervo = acervo_falso(tmp_path)
    antes = acervo.stat().st_mtime_ns
    SC.ler_do_eoficio(acervo)
    assert acervo.stat().st_mtime_ns == antes


# ------------------------------------------------------------- o mascarar

@pytest.mark.parametrize("valor,esperado", [
    ("nome.sobrenome", "no**********me"),
    ("abcd", "****"),
    ("ab", "**"),
    ("", ""),
    (None, ""),
])
def test_o_mascarar_mostra_so_as_pontas(valor, esperado):
    assert SC.mascarar(valor) == esperado
