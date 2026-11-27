"""O caminho facilitado do Linux (`installer/linux`, docs/SERVIDOR_LINUX.md, 27/11/2026).

O instalador só roda num Linux com apt e systemd, como root. Aqui se confere o que dá para conferir
em qualquer máquina: o script é bash válido, todo @CAMPO@ dos modelos é trocado pelo script, a
senha do banco não vai para a configuração nem para a linha de comando, e o serviço sobe o mesmo
`app.py --service` do Windows e do macOS."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

PASTA = Path(__file__).resolve().parent.parent / "installer" / "linux"
SCRIPT = (PASTA / "instalar_servidor.sh").read_text(encoding="utf-8")
UNIDADE = (PASTA / "cartorio-gestao.service").read_text(encoding="utf-8")
AMBIENTE = (PASTA / "servidor.env.exemplo").read_text(encoding="utf-8")


@pytest.mark.skipif(shutil.which("bash") is None, reason="sem bash")
def test_o_script_e_bash_valido():
    subprocess.run(["bash", "-n", str(PASTA / "instalar_servidor.sh")], check=True)


def _campos(texto: str) -> set[str]:
    return set(re.findall(r"@([A-Z_]+)@", texto))


def _trocados_pelo_script(modelo: str) -> set[str]:
    """Os @CAMPOS@ que o `sed` do script troca na linha que lê aquele modelo."""
    trocados: set[str] = set()
    for bloco in re.findall(r"sed((?:\s+-e\s+\"[^\"]+\")+)[^\n]*\n?[^\n]*" + re.escape(modelo), SCRIPT):
        trocados |= set(re.findall(r"s#@([A-Z_]+)@#", bloco))
    return trocados


@pytest.mark.parametrize("modelo, texto", [("cartorio-gestao.service", UNIDADE),
                                           ("servidor.env.exemplo", AMBIENTE)])
def test_todo_campo_do_modelo_e_trocado(modelo, texto):
    assert _campos(texto), modelo
    assert _campos(texto) <= _trocados_pelo_script(modelo)


def test_a_senha_fica_so_no_pgpass():
    assert not re.search(r"password\s*=", AMBIENTE, re.I)
    assert "PGPASSFILE=@DADOS@/.pgpass" in AMBIENTE
    # a senha não passa por argumento de processo externo (o `ps` mostraria): vai pela entrada
    # padrão do psql, e o printf é embutido do bash
    linhas_com_senha = [li for li in SCRIPT.splitlines() if "$SENHA" in li]
    assert linhas_com_senha
    assert all("psql" not in li and "echo" not in li for li in linhas_com_senha)
    assert "chmod 600" in SCRIPT and "NOSUPERUSER" in SCRIPT


def test_o_servico_sobe_o_mesmo_app_e_so_grava_nos_dados():
    assert "ExecStart=@RAIZ@/venv/bin/python app.py --service" in UNIDADE
    assert "ReadWritePaths=@DADOS@" in UNIDADE and "ProtectSystem=full" in UNIDADE
    assert "User=@CONTA@" in UNIDADE and "Requires=postgresql.service" in UNIDADE
    assert "CARTORIO_GESTAO_DATA=@DADOS@" in AMBIENTE and "CG_PG_SCHEMA=producao" in AMBIENTE


def test_o_firewall_so_e_sugerido():
    # a faixa da rede é da casa: o script mostra o comando do ufw, não o roda
    assert all(li.lstrip().startswith("echo") for li in SCRIPT.splitlines() if "ufw allow" in li)
