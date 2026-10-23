"""O kit de sandbox público: monta a pasta, recusa a produção, carrega sem duplicar
e sobe sem falar com a rede.

POR QUE ESTES TESTES EXISTEM
    Em 12/10/2026 um sandbox ligado SEM a variável de dados abriu o banco de uma
    instalação real: `app.get_data_dir()` cai em `%PROGRAMDATA%\\CartorioGestao`
    quando `CARTORIO_GESTAO_DATA` está vazia. O kit (`tools/iniciar_sandbox.py`)
    existe para isso nunca mais acontecer com quem baixa o programa do GitHub —
    e as recusas dele são a parte que mais precisa de guarda.
"""
from __future__ import annotations

import os
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from tools import carga_de_demonstracao as CARGA  # noqa: E402
from tools import iniciar_sandbox as KIT  # noqa: E402


# ------------------------------------------------------------------ a pasta


def test_a_pasta_do_sandbox_nasce_com_a_marca_e_o_programdata_proprio(tmp_path):
    pasta = tmp_path / "sb"
    ambiente = KIT.preparar_pasta(pasta)
    assert (pasta / KIT.MARCA).is_file()
    assert (pasta / "programdata" / "CartorioGestao").is_dir()
    assert (pasta / "arquivos").is_dir()
    assert ambiente["CARTORIO_GESTAO_SANDBOX"] == "1"
    assert Path(ambiente["CARTORIO_GESTAO_DATA"]) == pasta.resolve()
    # credenciais, secret.key e perfil do LibreOffice moram em PROGRAMDATA:
    # ele tem de apontar para DENTRO do sandbox.
    assert Path(ambiente["PROGRAMDATA"]).resolve().is_relative_to(pasta.resolve())
    assert Path(ambiente["CARTORIO_GESTAO_COPIAS"]).resolve().is_relative_to(pasta.resolve())
    # de novo, na mesma pasta: não recusa (o banco que ela tiver é do kit)
    (pasta / KIT.NOME_DO_BANCO).write_bytes(b"")
    assert KIT.preparar_pasta(pasta)["CARTORIO_GESTAO_DATA"] == ambiente["CARTORIO_GESTAO_DATA"]


def test_recusa_a_pasta_da_producao_e_o_que_esta_dentro_ou_em_volta(tmp_path, monkeypatch):
    pd = tmp_path / "pd"
    monkeypatch.setattr(KIT, "_PROGRAMDATA_ORIGINAL", str(pd))
    producao = pd / "CartorioGestao"
    for alvo in (producao, producao / "sub", pd):
        with pytest.raises(KIT.SandboxRecusado, match="instalação real"):
            KIT.preparar_pasta(alvo)
    assert not producao.exists(), "a recusa veio depois de criar alguma coisa"


@pytest.mark.skipif(os.name != "nt", reason="caminho do Windows: fora dele a "
                    "contrabarra não separa pastas e `C:\\ProgramData` não existe")
def test_recusa_o_caminho_fixo_do_windows_qualquer_que_seja_o_programdata():
    """Separado do teste de cima porque só se prova no Windows.

    No macOS e no Linux `C:\\ProgramData\\CartorioGestao` é UM nome de arquivo
    relativo à pasta corrente, e não a pasta de `C:\\ProgramData` — a recusa
    não tem o que reconhecer. O teste já falhava assim antes dos lotes LX
    (`base_antes_dos_lotes.log`); a instalação real é Windows.
    """
    with pytest.raises(KIT.SandboxRecusado):
        KIT.conferir_pasta_de_dados(r"C:\ProgramData\CartorioGestao")


def test_recusa_pasta_com_install_json_ou_banco_que_o_kit_nao_criou(tmp_path):
    instalada = tmp_path / "instalada"
    instalada.mkdir()
    (instalada / "install.json").write_text("{}", encoding="utf-8")
    with pytest.raises(KIT.SandboxRecusado, match="install.json"):
        KIT.preparar_pasta(instalada)

    alheia = tmp_path / "alheia"
    alheia.mkdir()
    (alheia / KIT.NOME_DO_BANCO).write_bytes(b"")
    with pytest.raises(KIT.SandboxRecusado, match=KIT.MARCA):
        KIT.preparar_pasta(alheia)
    assert not (alheia / KIT.MARCA).exists()


def test_recusa_as_portas_da_instalacao_real():
    for porta in (8765, 8766):
        with pytest.raises(KIT.SandboxRecusado, match="instalação real"):
            KIT.conferir_porta(porta)


def test_recusa_rodar_de_dentro_da_pasta_instalada():
    with pytest.raises(KIT.SandboxRecusado, match="cópia baixada"):
        KIT.conferir_raiz_do_programa(Path(r"C:\Program Files\CartorioGestao"))


# ---------------------------------------------------------- a trava de rede


def test_a_trava_recusa_conexao_para_fora_e_deixa_a_local():
    servidor = socket.socket()
    servidor.bind(("127.0.0.1", 0))
    servidor.listen(1)
    porta = servidor.getsockname()[1]
    KIT.armar_trava_de_rede()
    try:
        antes = len(KIT.tentativas_bloqueadas())
        with pytest.raises(KIT.RedeBloqueada):
            socket.create_connection(("203.0.113.9", 443), timeout=1)
        with pytest.raises(KIT.RedeBloqueada):
            socket.getaddrinfo("servidor.exemplo.invalid", 443)
        with socket.create_connection(("127.0.0.1", porta), timeout=2):
            pass
        assert len(KIT.tentativas_bloqueadas()) == antes + 2
        # a recusa é OSError: quem já trata «rede fora do ar» trata esta também
        assert issubclass(KIT.RedeBloqueada, OSError)
    finally:
        KIT.desarmar_trava_de_rede()
        servidor.close()
    assert not KIT.trava_armada()


# ------------------------------------------------------------------ a carga


def _contagens(banco: Path) -> dict:
    con = sqlite3.connect(banco)
    try:
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("users", "nu_livros", "pp_folhas", "rc_assentos",
                          "rc_certidoes", "nt_atos", "pt_certidoes",
                          "ri_matriculas", "sd_selos")}
    finally:
        con.close()


def test_a_carga_de_demonstracao_roda_duas_vezes_sem_duplicar(cg_casa):
    (cg_casa["dados"] / KIT.MARCA).write_text("sandbox de teste", encoding="utf-8")
    db, app = cg_casa["db"], cg_casa["app"]

    primeira = CARGA.carregar(db, app=app)
    assert primeira["pulados"] == {}, primeira["pulados"]
    depois_da_primeira = _contagens(cg_casa["banco"])
    assert depois_da_primeira["users"] == len(CARGA.USUARIOS_DE_DEMONSTRACAO)
    assert depois_da_primeira["nu_livros"] > 0
    assert depois_da_primeira["rc_assentos"] == 2
    assert depois_da_primeira["nt_atos"] == 1
    assert depois_da_primeira["pt_certidoes"] == 1
    assert depois_da_primeira["ri_matriculas"] == 1

    segunda = CARGA.carregar(db, app=app)
    assert segunda["pulados"] == {}, segunda["pulados"]
    assert _contagens(cg_casa["banco"]) == depois_da_primeira

    # os usuários entram com as senhas de demonstração escritas no manual
    for usuario, _nome, papel, senha in CARGA.USUARIOS_DE_DEMONSTRACAO:
        linha = db.authenticate(usuario, senha)
        assert linha is not None and linha["role"] == papel
    # e a instalação fica presa nesta máquina, sem a descoberta UDP
    assert db.get_setting("network_host") == "127.0.0.1"
    assert db.get_setting("discovery_enabled") == "0"


def test_a_carga_recusa_banco_que_nao_e_de_sandbox(cg_casa):
    marca = cg_casa["dados"] / KIT.MARCA
    if marca.exists():
        marca.unlink()
    antes = _contagens(cg_casa["banco"])
    # recusa pela régua da pasta (banco sem a marca do kit) ou pela da carga
    with pytest.raises(KIT.SandboxRecusado, match=KIT.MARCA):
        CARGA.carregar(cg_casa["db"], app=cg_casa["app"])
    assert _contagens(cg_casa["banco"]) == antes


# ------------------------------------------------- o sistema sobe, e calado


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.lento
def test_o_sistema_sobe_no_sandbox_sem_falar_com_a_rede(tmp_path):
    """Num processo limpo, como o INICIAR_SANDBOX.cmd o sobe.

    A variável CARTORIO_GESTAO_DATA vem apontando para uma ISCA: o kit tem de
    ignorá-la e usar só a pasta dele. E toda tentativa de conexão para fora da
    máquina — Central, IA, o que for — é contada pela trava e sai no relatório.
    """
    pasta = tmp_path / "sandbox"
    isca = tmp_path / "isca"
    ambiente = dict(os.environ)
    ambiente["CARTORIO_GESTAO_DATA"] = str(isca)
    ambiente["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        [sys.executable, str(RAIZ / "tools" / "iniciar_sandbox.py"),
         "--dados", str(pasta), "--porta", str(_porta_livre()), "--conferir"],
        cwd=str(RAIZ), env=ambiente, capture_output=True, timeout=900)
    saida = r.stdout.decode("utf-8", "replace") + r.stderr.decode("utf-8", "replace")
    assert r.returncode == 0, saida
    assert "conferido /saude: HTTP 200" in saida, saida
    assert "conferido /login: HTTP 200 (faixa do sandbox presente)" in saida, saida
    assert "conexões para fora tentadas e recusadas: 0" in saida, saida
    assert "foi IGNORADA" in saida, saida
    assert (pasta / KIT.NOME_DO_BANCO).is_file()
    assert (pasta / KIT.MARCA).is_file()
    assert not isca.exists(), "o kit abriu a pasta da variável herdada"
