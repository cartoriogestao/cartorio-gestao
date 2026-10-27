"""O instalador da tarefa da automação — a única parte que muda entre Windows e macOS.

    «prepare uma migração facilitada para, no futuro, o servidor rodar em
     macOS» — o oficial, 24/10/2026

O DESPACHANTE É O MESMO; SÓ O INSTALADOR MUDA
    Nos dois sistemas são duas coisas, as duas na SESSÃO DO USUÁRIO (o token A3
    do Portal do Selo só responde com a sessão aberta):
      - o GUARDIÃO DO COFRE, no logon (pede a senha-mestra e fica de pé);
      - o DESPACHANTE, a cada minuto (`tools/automacao_despachante.py --tique`).

    Windows → Agendador de Tarefas: dois lançadores `.cmd` e um `.ps1` que
    registra as duas tarefas. macOS → launchd: dois LaunchAgents (`.plist`) e
    um `.sh` que os carrega. **Este módulo GERA os arquivos; não executa
    nenhum** — quem registra é o oficial, como administrador da máquina.

NENHUM CAMINHO DESTA MÁQUINA NO CÓDIGO
    Os caminhos (programa, dados, Python) e o ambiente do banco entram como
    argumento ou vêm do ambiente; o gerador escreve o que recebeu.
"""
from __future__ import annotations

import os
import plistlib
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROTULO_DESPACHANTE = "com.cartoriogestao.automacao.despachante"
ROTULO_GUARDIAO = "com.cartoriogestao.automacao.guardiao"
TAREFA_DESPACHANTE = "CartorioGestao-Automacao"
TAREFA_GUARDIAO = "CartorioGestao-Automacao-Guardiao"
#: As variáveis que o despachante e o guardião precisam herdar do servidor.
#: `CG_PG_DSN_RESTAURACAO` (26/10/2026): o servidor onde o teste de restauração
#: cria o banco descartável, quando não é o mesmo do banco da casa (opcional).
VARIAVEIS = ("CARTORIO_GESTAO_DATA", "CG_PG_DSN", "CG_PG_SCHEMA", "CG_PG_BIN", "CG_COFRE_AUTOMACAO",
             "CG_PG_DSN_RESTAURACAO")


@dataclass
class Lancamento:
    """O que o instalador precisa saber para escrever os arquivos."""
    raiz: Path                      # a pasta do programa
    pasta_dados: Path               # a pasta de dados (onde mora o cofre)
    python: Path                    # o Python do runtime
    destino: Path                   # onde os lançadores e o log ficam
    ambiente: dict[str, str] = field(default_factory=dict)
    usuario: str = ""               # a conta da sessão (Windows: DOMINIO\\usuario)


class Instalador:
    sistema = ""

    def arquivos(self, l: Lancamento) -> dict[str, str]:     # pragma: no cover — interface
        raise NotImplementedError


class AgendadorDoWindows(Instalador):
    """Os dois lançadores `.cmd` e o `.ps1` que registra as duas tarefas."""
    sistema = "windows"

    def arquivos(self, l: Lancamento) -> dict[str, str]:
        sets = [f'set "{k}={v}"' for k, v in l.ambiente.items() if v]
        log = l.destino / "automacao_despachante.log"
        pythonw = l.python.with_name("pythonw.exe")
        despachante = "\r\n".join(["@echo off", *sets, f'cd /d "{l.raiz}"',
                                   f'"{l.python}" "{l.raiz / "tools" / "automacao_despachante.py"}" --tique >> "{log}" 2>&1', ""])
        guardiao = "\r\n".join(["@echo off", *sets, f'cd /d "{l.raiz}"',
                                f'start "" "{pythonw}" "{l.raiz / "tools" / "automacao_guardiao.py"}"', ""])
        cofre = l.pasta_dados / "cofre_automacao"
        usuario = l.usuario or "$env:USERDOMAIN\\$env:USERNAME"
        ps1 = f"""<#
  Registra as DUAS tarefas da automacao no Agendador do Windows (gerado por
  automacao_agendador.py; nao executado por ele). Rode como administrador.
    - {TAREFA_GUARDIAO}: no logon de {usuario}, abre o guardiao do cofre (pede a senha-mestra).
    - {TAREFA_DESPACHANTE}: a cada minuto, na sessao de {usuario}, o tique do despachante.
  As duas rodam NA SESSAO DO USUARIO: o token A3 do Portal do Selo so responde
  com a sessao aberta. As tarefas antigas (conferencia, compliance, CENSEC,
  backup, minutas do CNIB) NAO sao mexidas.
#>
$ErrorActionPreference = 'Stop'
$usuario = "{usuario}"
$cofre = "{cofre}"
New-Item -ItemType Directory -Force -Path $cofre | Out-Null
# A ACL do cofre: SYSTEM, Administradores e a conta da sessao; ninguem mais.
& icacls.exe $cofre /inheritance:r /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" "$($usuario):(OI)(CI)F" | Out-Null
& icacls.exe "{l.destino}" /grant "$($usuario):(OI)(CI)M" | Out-Null
$quem = New-ScheduledTaskPrincipal -UserId $usuario -LogonType Interactive -RunLevel Highest
$g = New-ScheduledTask -Principal $quem `
  -Action (New-ScheduledTaskAction -Execute "$env:SystemRoot\\System32\\cmd.exe" -Argument '/d /c "{l.destino / "automacao_guardiao.cmd"}"') `
  -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $usuario) `
  -Settings (New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries)
Register-ScheduledTask -TaskName '{TAREFA_GUARDIAO}' -InputObject $g -Force | Out-Null
# PRIORIDADE 7 (abaixo do normal) de proposito: o servidor do balcao nasce com 3.
$d = New-ScheduledTask -Principal $quem `
  -Action (New-ScheduledTaskAction -Execute "$env:SystemRoot\\System32\\cmd.exe" -Argument '/d /c "{l.destino / "automacao_despachante.cmd"}"') `
  -Trigger (New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) -RepetitionInterval (New-TimeSpan -Minutes 1)) `
  -Settings (New-ScheduledTaskSettingsSet -Priority 7 -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries)
Register-ScheduledTask -TaskName '{TAREFA_DESPACHANTE}' -InputObject $d -Force | Out-Null
Write-Host 'Tarefas registradas: {TAREFA_GUARDIAO} (logon) e {TAREFA_DESPACHANTE} (a cada minuto).'
"""
        return {"automacao_despachante.cmd": despachante, "automacao_guardiao.cmd": guardiao,
                "registrar_tarefas.ps1": ps1.replace("\n", "\r\n")}


class LaunchdDoMacOS(Instalador):
    """Dois LaunchAgents do usuário e o `.sh` que os carrega."""
    sistema = "macos"

    def _plist(self, l: Lancamento, rotulo: str, script: str, extra: dict, args: list[str]) -> str:
        dados = {"Label": rotulo,
                 "ProgramArguments": [str(l.python), str(l.raiz / "tools" / script), *args],
                 "WorkingDirectory": str(l.raiz),
                 "EnvironmentVariables": {k: v for k, v in l.ambiente.items() if v},
                 "StandardOutPath": str(l.destino / f"{rotulo}.log"),
                 "StandardErrorPath": str(l.destino / f"{rotulo}.log"), **extra}
        return plistlib.dumps(dados, sort_keys=False).decode("utf-8")

    def arquivos(self, l: Lancamento) -> dict[str, str]:
        despachante = self._plist(l, ROTULO_DESPACHANTE, "automacao_despachante.py",
                                  {"StartInterval": 60, "ProcessType": "Background", "Nice": 10,
                                   "LowPriorityIO": True}, ["--tique"])
        guardiao = self._plist(l, ROTULO_GUARDIAO, "automacao_guardiao.py",
                               {"RunAtLoad": True, "KeepAlive": True, "LimitLoadToSessionType": "Aqua"}, [])
        sh = f"""#!/bin/sh
# Carrega os DOIS LaunchAgents da automacao na sessao do usuario (gerado por
# automacao_agendador.py; nao executado por ele). O guardiao abre no login e
# pede a senha-mestra; o despachante roda a cada minuto. Na sessao do usuario
# porque o token A3 precisa dela.
set -e
AGENTES="$HOME/Library/LaunchAgents"
mkdir -p "$AGENTES" "{l.pasta_dados / 'cofre_automacao'}"
chmod 700 "{l.pasta_dados / 'cofre_automacao'}"
for ROTULO in {ROTULO_GUARDIAO} {ROTULO_DESPACHANTE}; do
  cp "$(dirname "$0")/$ROTULO.plist" "$AGENTES/$ROTULO.plist"
  launchctl bootout "gui/$(id -u)/$ROTULO" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$AGENTES/$ROTULO.plist"
done
echo "LaunchAgents carregados: {ROTULO_GUARDIAO} (login) e {ROTULO_DESPACHANTE} (a cada minuto)."
"""
        return {f"{ROTULO_DESPACHANTE}.plist": despachante, f"{ROTULO_GUARDIAO}.plist": guardiao,
                "instalar_launchd.sh": sh}


INSTALADORES: dict[str, Instalador] = {"windows": AgendadorDoWindows(), "macos": LaunchdDoMacOS()}


def do_sistema() -> Instalador:
    return INSTALADORES["windows" if sys.platform == "win32" else "macos"]


def ambiente_do_servidor(pasta_dados: Path) -> dict[str, str]:
    """O ambiente do servidor: o deste processo e, no Windows, as linhas `set` do
    `iniciar_servidor_servico.cmd` (que é quem sobe o servidor de verdade)."""
    ambiente = {k: os.environ[k] for k in VARIAVEIS if os.environ.get(k)}
    servico = Path(pasta_dados) / "iniciar_servidor_servico.cmd"
    if servico.is_file():
        import re
        for linha in servico.read_text(encoding="utf-8", errors="replace").splitlines():
            achado = re.match(r'^\s*set\s+"([A-Z_]+)=(.*)"\s*$', linha)
            if achado and achado.group(1) in VARIAVEIS:
                ambiente[achado.group(1)] = achado.group(2)
    ambiente.setdefault("CARTORIO_GESTAO_DATA", str(pasta_dados))
    return ambiente


def gerar(l: Lancamento, sistemas: tuple[str, ...] = ("windows", "macos")) -> list[Path]:
    """Escreve os arquivos de cada sistema em `destino/<sistema>/`. Não executa nada."""
    escritos = []
    for nome in sistemas:
        pasta = Path(l.destino) / nome
        pasta.mkdir(parents=True, exist_ok=True)
        for arquivo, conteudo in INSTALADORES[nome].arquivos(l).items():
            alvo = pasta / arquivo
            alvo.write_text(conteudo, encoding="utf-8", newline="")
            escritos.append(alvo)
    return escritos


def main(argv: list[str] | None = None) -> int:
    """`tools/gerar_instalador_automacao.py` — gera os instaladores; não registra nada."""
    import argparse
    import automacao_cofre as COFRE
    raiz = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description="Gera os instaladores da automação (Windows e macOS).")
    ap.add_argument("--sistema", choices=("windows", "macos", "ambos"), default="ambos")
    ap.add_argument("--dados", default=str(COFRE.pasta_de_dados()))
    ap.add_argument("--destino", default="")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--usuario", default="")
    a = ap.parse_args(argv)
    dados = Path(a.dados)
    destino = Path(a.destino) if a.destino else dados / "automacao_instalador"
    l = Lancamento(raiz=raiz, pasta_dados=dados, python=Path(a.python), destino=destino,
                   ambiente=ambiente_do_servidor(dados), usuario=a.usuario)
    sistemas = ("windows", "macos") if a.sistema == "ambos" else (a.sistema,)
    for alvo in gerar(l, sistemas):
        print(f"gerado: {alvo}")
    print(f"Nada foi registrado. Nesta máquina vale o de «{do_sistema().sistema}»: no Windows, rode "
          "registrar_tarefas.ps1 como administrador; no macOS, instalar_launchd.sh na sessão do usuário.")
    return 0
