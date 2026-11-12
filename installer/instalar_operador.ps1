# INSTALA A PONTE DO SUPERUSUARIO NO SERVIDOR PRINCIPAL (docs/SUPERUSUARIO.md).
# Rode como Administrador, da pasta do sistema instalado:
#   powershell -ExecutionPolicy Bypass -File installer\instalar_operador.ps1
#
# O que faz (e pode rodar de novo):
#   1. cria <dados>\operador\operador.cred a partir do exemplo, legivel so por
#      Administradores e SYSTEM;
#   2. gera <dados>\operador\iniciar_operador.cmd com as variaveis do banco que
#      o servico do servidor usa (copiadas do iniciar_servidor_servico.cmd);
#   3. com o operador.cred preenchido, registra a tarefa agendada
#      CartorioGestaoOperador (ao iniciar o Windows, reinicia se cair).
# NAO baixa nem instala o Claude Code, e nao escreve chave nenhuma.
#
# -Conta: a conta que roda a tarefa. O padrao e a conta de quem instala (o
# Windows pede a senha dela), porque o Claude Code guarda as conversas no
# perfil do usuario e a execucao como SYSTEM nao esta documentada por ele.
# Arquivo em ASCII de proposito (PowerShell 5 le UTF-8 sem BOM errado).
param([string]$Conta = "$env:USERDOMAIN\$env:USERNAME")
$ErrorActionPreference = 'Stop'
$TaskName = 'CartorioGestaoOperador'
$InstallDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$DataDir = Join-Path $env:ProgramData 'CartorioGestao'
$OperadorDir = Join-Path $DataDir 'operador'
$Cred = Join-Path $OperadorDir 'operador.cred'
$Lancador = Join-Path $OperadorDir 'iniciar_operador.cmd'
$Python = Join-Path $DataDir 'runtime\Scripts\python.exe'
$ServicoCmd = Join-Path $DataDir 'iniciar_servidor_servico.cmd'

function Parar([string]$Texto) { Write-Host "PAROU: $Texto" -ForegroundColor Red; exit 1 }

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$p = New-Object Security.Principal.WindowsPrincipal($id)
if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { Parar 'rode como Administrador.' }
if (-not (Test-Path (Join-Path $InstallDir 'operador\ponte.py'))) { Parar "o sistema em $InstallDir ainda nao tem a pasta operador (atualize o sistema)." }
if (-not (Test-Path $Python)) { Parar "nao achei o Python do servidor em $Python." }

New-Item -ItemType Directory -Force -Path $OperadorDir | Out-Null
if (-not (Test-Path $Cred)) {
    Copy-Item (Join-Path $InstallDir 'operador\operador_cred.exemplo') $Cred
    Write-Host "Criei $Cred"
}
# So Administradores, SYSTEM e a conta da tarefa leem a pasta do operador.
& icacls.exe $OperadorDir /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' "${Conta}:(OI)(CI)F" | Out-Null

# O lancador: as variaveis do banco do servico, e a ponte.
$linhas = @('@echo off', 'rem Gerado por installer\instalar_operador.ps1. A ponte do superusuario.', 'setlocal')
if (Test-Path $ServicoCmd) {
    $linhas += Get-Content $ServicoCmd | Where-Object { $_ -match '^\s*set\s+"?(CG_|CARTORIO_GESTAO_|PG)' }
} else {
    Write-Host "Aviso: nao achei $ServicoCmd; ponha CG_PG_DSN e CG_PG_SCHEMA no operador.cred."
}
$linhas += "cd /d `"$InstallDir`""
$linhas += "`"$Python`" operador\ponte.py"
Set-Content -Path $Lancador -Value $linhas -Encoding ASCII

$claude = Get-Command claude.exe -ErrorAction SilentlyContinue
if (-not $claude) { $claude = Get-Command claude -ErrorAction SilentlyContinue }
$texto = Get-Content $Cred -Raw
function Valor([string]$Chave) {
    $m = [regex]::Match($texto, "(?m)^$Chave=(.*)$")
    if ($m.Success) { return $m.Groups[1].Value.Trim().Trim('"').Trim("'") } else { return '' }
}
$faltam = @()
foreach ($chave in @('TELEGRAM_TOKEN', 'ANTHROPIC_API_KEY')) { if (-not (Valor $chave)) { $faltam += $chave } }
$temClaude = [bool]$claude -or [bool](Valor 'OPERADOR_CLAUDE')
if ($faltam.Count -gt 0 -or -not $temClaude) {
    Write-Host ''
    Write-Host 'Ainda nao liguei a ponte. Falta:'
    if ($faltam.Count -gt 0) { Write-Host ("  - preencher em {0}: {1}" -f $Cred, ($faltam -join ', ')) }
    if (-not $temClaude) { Write-Host '  - instalar o Claude Code (https://code.claude.com/docs/en/setup) na conta da tarefa, ou dizer o caminho em OPERADOR_CLAUDE' }
    Write-Host 'Depois rode este instalador de novo.'
    exit 0
}
if ($claude -and -not (Valor 'OPERADOR_CLAUDE')) {
    Add-Content -Path $Cred -Value ("OPERADOR_CLAUDE=" + $claude.Source) -Encoding ASCII
}

$senha = Read-Host -AsSecureString "Senha da conta $Conta (para a tarefa rodar sem ninguem logado)"
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($senha)
try {
    $clara = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    $action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\cmd.exe" -Argument "/d /c `"$Lancador`""
    $trigger = New-ScheduledTaskTrigger -AtStartup
    # Prioridade abaixo do servidor (que e 3): a ponte nunca disputa com o balcao.
    $settings = New-ScheduledTaskSettingsSet -Priority 7 -StartWhenAvailable -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -User $Conta -Password $clara -RunLevel Highest -Force | Out-Null
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    $clara = $null
}
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "A ponte do superusuario esta no ar (tarefa $TaskName, conta $Conta)."
if (-not (Valor 'OPERADOR_TELEGRAM_USUARIO')) {
    Write-Host 'Agora escreva qualquer coisa para o bot no Telegram: ele responde o seu numero de usuario.'
    Write-Host "Ponha esse numero em OPERADOR_TELEGRAM_USUARIO, em $Cred, e rode este instalador de novo."
}
Write-Host ("Registro: " + (Join-Path $OperadorDir 'ponte.log'))
