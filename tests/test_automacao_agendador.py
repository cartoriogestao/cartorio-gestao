"""O instalador da tarefa — Agendador do Windows e launchd do macOS, gerados e não executados."""
from __future__ import annotations

import plistlib
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import automacao_agendador as AG  # noqa: E402


def _lancamento(tmp_path, raiz, dados, python, destino=None):
    return AG.Lancamento(raiz=raiz, pasta_dados=dados, python=python, destino=destino or tmp_path / "saida",
                         ambiente={"CARTORIO_GESTAO_DATA": str(dados), "CG_PG_DSN": "host=127.0.0.1 port=5432 user=cg dbname=cartorio"},
                         usuario="EXEMPLO\\mario")


def test_o_launchd_tem_o_guardiao_no_login_e_o_despachante_a_cada_minuto(tmp_path):
    l = _lancamento(tmp_path, PurePosixPath("/Applications/CartorioGestao"),
                    PurePosixPath("/Users/exemplo/Library/Application Support/CartorioGestao"),
                    PurePosixPath("/usr/local/bin/python3"),
                    PurePosixPath("/Users/exemplo/Library/Application Support/CartorioGestao/automacao_instalador"))
    arquivos = AG.LaunchdDoMacOS().arquivos(l)
    desp = plistlib.loads(arquivos[f"{AG.ROTULO_DESPACHANTE}.plist"].encode())
    guar = plistlib.loads(arquivos[f"{AG.ROTULO_GUARDIAO}.plist"].encode())
    assert desp["StartInterval"] == 60 and desp["ProgramArguments"][-1] == "--tique"
    assert guar["RunAtLoad"] and guar["KeepAlive"] and guar["LimitLoadToSessionType"] == "Aqua"
    assert desp["EnvironmentVariables"]["CG_PG_DSN"].startswith("host=")
    for texto in arquivos.values():
        assert "C:\\" not in texto and "powershell" not in texto.lower() and "schtasks" not in texto
    assert "launchctl bootstrap" in arquivos["instalar_launchd.sh"]


def test_o_agendador_do_windows_registra_as_duas_tarefas_na_sessao_do_usuario(tmp_path):
    l = _lancamento(tmp_path, PureWindowsPath("D:/Programa"), PureWindowsPath("D:/Dados"),
                    PureWindowsPath("D:/Programa/runtime/python.exe"))
    arquivos = AG.AgendadorDoWindows().arquivos(l)
    ps1 = arquivos["registrar_tarefas.ps1"]
    assert AG.TAREFA_GUARDIAO in ps1 and AG.TAREFA_DESPACHANTE in ps1
    assert "-AtLogOn" in ps1 and "-RepetitionInterval (New-TimeSpan -Minutes 1)" in ps1
    assert "-LogonType Interactive" in ps1 and "Priority 7" in ps1
    assert "/inheritance:r" in ps1                       # a ACL do cofre
    assert "--tique" in arquivos["automacao_despachante.cmd"]
    assert "automacao_guardiao.py" in arquivos["automacao_guardiao.cmd"]
    assert all("\r\n" in t for t in arquivos.values())


def test_gerar_escreve_e_nao_executa(tmp_path):
    l = _lancamento(tmp_path, RAIZ, tmp_path / "dados", Path(sys.executable))
    escritos = AG.gerar(l)
    nomes = {p.name for p in escritos}
    assert {"registrar_tarefas.ps1", "instalar_launchd.sh", f"{AG.ROTULO_DESPACHANTE}.plist"} <= nomes
    assert all(p.is_file() for p in escritos)


def test_as_tarefas_chamam_os_lancadores_que_gerar_escreve(tmp_path):
    # 27/10/2026, instalação da 3.7.5: as tarefas chamavam `destino/*.cmd` e
    # `gerar` escreve em `destino/windows/*.cmd` — o despachante saía com 1 a
    # cada minuto. O caminho que o .ps1 registra tem de ser um arquivo escrito.
    import re
    l = _lancamento(tmp_path, RAIZ, tmp_path / "dados", Path(sys.executable))
    escritos = {str(p) for p in AG.gerar(l, ("windows",))}
    ps1 = (Path(l.destino) / "windows" / "registrar_tarefas.ps1").read_text(encoding="utf-8")
    chamados = re.findall(r"/d /c \"([^\"]+\.cmd)\"", ps1)
    assert len(chamados) == 2
    for caminho in chamados:
        assert caminho in escritos, caminho


def test_o_modulo_da_automacao_nao_tem_caminho_de_windows_escrito():
    """Portabilidade: nada de `C:\\` nem de comando exclusivo do Windows fora das funções de dois ramos."""
    for nome in ("automacao.py", "automacao_cofre.py", "automacao_guardiao.py", "automacao_processos.py",
                 "automacao_avisos.py", "automacao_web.py", "automacao_schema.py"):
        texto = (RAIZ / nome).read_text(encoding="utf-8")
        assert "C:\\\\" not in texto and 'r"C:' not in texto, nome
        assert "shell=True" not in texto, nome
