# INSTALA O SUPERUSUARIO NO SERVIDOR PRINCIPAL (docs/SUPERUSUARIO.md).
# Rode como Administrador, da pasta do sistema instalado:
#   powershell -ExecutionPolicy Bypass -File installer\instalar_operador.ps1
#
# O que faz (e pode rodar de novo):
#   1. cria <dados>\operador\operador.cred a partir do exemplo, legivel so por
#      Administradores, SYSTEM e a conta da tarefa;
#   2. gera <dados>\operador\iniciar_operador.cmd com as variaveis do banco que
#      o servico do servidor usa (copiadas do iniciar_servidor_servico.cmd), e
#      aponta OPERADOR_AMBIENTE para ele: a ponte rele o arquivo a cada pedido;
#   3. monta o POSTO (<dados>\operador\posto): a pasta de onde o superusuario
#      trabalha, por qualquer porta;
#   4. com o operador.cred dizendo como ele fala com a Anthropic, registra a
#      tarefa agendada CartorioGestaoOperador (a ponte: Telegram e tela do
#      sistema; ao iniciar o Windows, reinicia se cair);
#   5. com OPERADOR_APP=1, registra a CartorioGestaoOperadorApp (o Remote
#      Control, para o app do Claude).
# NAO baixa nem instala o Claude Code, e nao escreve chave nenhuma.
#
# -Conta: a conta que roda as tarefas. O padrao e a conta de quem instala (o
# Windows pede a senha dela), porque o Claude Code guarda as conversas e o
# login no perfil do usuario e a execucao como SYSTEM nao esta documentada.
# Arquivo em ASCII de proposito (PowerShell 5 le UTF-8 sem BOM errado).
param([string]$Conta = "$env:USERDOMAIN\$env:USERNAME")
$ErrorActionPreference = 'Stop'
$TaskName = 'CartorioGestaoOperador'
$TaskDoApp = 'CartorioGestaoOperadorApp'
$InstallDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$DataDir = Join-Path $env:ProgramData 'CartorioGestao'
$OperadorDir = Join-Path $DataDir 'operador'
$Cred = Join-Path $OperadorDir 'operador.cred'
$Lancador = Join-Path $OperadorDir 'iniciar_operador.cmd'
$LancadorDoApp = Join-Path $OperadorDir 'iniciar_operador_app.cmd'
$Python = Join-Path $DataDir 'runtime\Scripts\python.exe'
$ServicoCmd = Join-Path $DataDir 'iniciar_servidor_servico.cmd'

function Parar([string]$Texto) { Write-Host "PAROU: $Texto" -ForegroundColor Red; exit 1 }

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$p = New-Object Security.Principal.WindowsPrincipal($id)
if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { Parar 'rode como Administrador.' }
if (-not (Test-Path (Join-Path $InstallDir 'operador\posto.py'))) { Parar "o sistema em $InstallDir ainda nao tem o superusuario desta versao (atualize o sistema)." }
if (-not (Test-Path $Python)) { Parar "nao achei o Python do servidor em $Python." }

New-Item -ItemType Directory -Force -Path $OperadorDir | Out-Null
if (-not (Test-Path $Cred)) {
    Copy-Item (Join-Path $InstallDir 'operador\operador_cred.exemplo') $Cred
    Write-Host "Criei $Cred"
}
# So Administradores, SYSTEM e a conta da tarefa leem a pasta do operador. O
# SYSTEM precisa: e ele quem roda o servidor, e a tela do sistema deixa o
# pedido na bandeja desta pasta.
& icacls.exe $OperadorDir /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' "${Conta}:(OI)(CI)F" | Out-Null

# As variaveis do banco que o servico usa, para os dois lancadores.
$ambiente = @('@echo off', 'rem Gerado por installer\instalar_operador.ps1.', 'setlocal')
if (Test-Path $ServicoCmd) {
    $ambiente += Get-Content $ServicoCmd | Where-Object { $_ -match '^\s*set\s+"?(CG_|CARTORIO_GESTAO_|PG)' }
    # A ponte e o posto releem este arquivo a cada pedido: se o banco mudar no
    # servico, o superusuario acompanha sem reinstalar.
    $ambiente += "set `"OPERADOR_AMBIENTE=$ServicoCmd`""
} else {
    Write-Host "Aviso: nao achei $ServicoCmd; ponha CG_PG_DSN e CG_PG_SCHEMA no operador.cred."
}
$ambiente += 'set "OPERADOR_NOME=principal"'
$ambiente += "cd /d `"$InstallDir`""
# A ponte sai sozinha quando o programa dela muda no disco (o pacote de
# atualizacao): o laco a traz de volta com o novo. O ping e a espera de 30 s
# (o `timeout` nao funciona sem console).
$daPonte = $ambiente + @(':de_novo', "`"$Python`" operador\ponte.py", 'ping -n 31 127.0.0.1 >nul', 'goto de_novo')
Set-Content -Path $Lancador -Value $daPonte -Encoding ASCII

# O posto: a pasta de onde o superusuario trabalha.
$env:OPERADOR_NOME = 'principal'
if (Test-Path $ServicoCmd) { $env:OPERADOR_AMBIENTE = $ServicoCmd }
$Posto = (& $Python (Join-Path $InstallDir 'operador\posto.py') onde | Select-Object -Last 1)
if (-not $Posto) { Parar 'nao consegui montar o posto do superusuario (rode: python operador\posto.py montar).' }
Write-Host "Posto do superusuario: $Posto"

$claude = Get-Command claude.exe -ErrorAction SilentlyContinue
if (-not $claude) { $claude = Get-Command claude -ErrorAction SilentlyContinue }
$texto = Get-Content $Cred -Raw
function Valor([string]$Chave) {
    $m = [regex]::Match($texto, "(?m)^$Chave=(.*)$")
    if ($m.Success) { return $m.Groups[1].Value.Trim().Trim('"').Trim("'") } else { return '' }
}
$paga = ''
foreach ($chave in @('CLAUDE_CODE_OAUTH_TOKEN', 'OPERADOR_ASSINATURA', 'ANTHROPIC_API_KEY', 'OPERADOR_CHAVE_DA_CASA')) { if (Valor $chave) { $paga = $chave } }
$temClaude = [bool]$claude -or [bool](Valor 'OPERADOR_CLAUDE')
if (-not $paga -or -not $temClaude) {
    Write-Host ''
    Write-Host 'Ainda nao liguei a ponte. Falta:'
    if (-not $temClaude) { Write-Host '  - instalar o Claude Code (https://code.claude.com/docs/en/setup) na conta da tarefa, ou dizer o caminho em OPERADOR_CLAUDE' }
    if (-not $paga) { Write-Host ("  - dizer em {0} como ele fala com a Anthropic (a parte 1 do arquivo): pela assinatura (claude setup-token) ou pela API (uma chave)" -f $Cred) }
    Write-Host 'Depois rode este instalador de novo.'
    exit 0
}
if ($claude -and -not (Valor 'OPERADOR_CLAUDE')) {
    Add-Content -Path $Cred -Value ("OPERADOR_CLAUDE=" + $claude.Source) -Encoding ASCII
}
$caminhoDoClaude = Valor 'OPERADOR_CLAUDE'
if (-not $caminhoDoClaude -and $claude) { $caminhoDoClaude = $claude.Source }
$querOApp = (Valor 'OPERADOR_APP') -eq '1'

# O lancador da porta do app: o Remote Control, de dentro do posto. A
# assinatura, e nunca a API (com a chave no ambiente ele nem sobe).
$doApp = $ambiente + @('set "ANTHROPIC_API_KEY="', "cd /d `"$Posto`"", "`"$caminhoDoClaude`" remote-control --name `"Cartorio Principal`" --capacity 2")
Set-Content -Path $LancadorDoApp -Value $doApp -Encoding ASCII

$senha = Read-Host -AsSecureString "Senha da conta $Conta (para as tarefas rodarem sem ninguem logado)"
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($senha)
try {
    $clara = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    $trigger = New-ScheduledTaskTrigger -AtStartup
    # Prioridade abaixo do servidor (que e 3): a ponte nunca disputa com o balcao.
    $settings = New-ScheduledTaskSettingsSet -Priority 7 -StartWhenAvailable -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
    $action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\cmd.exe" -Argument "/d /c `"$Lancador`""
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -User $Conta -Password $clara -RunLevel Highest -Force | Out-Null
    if ($querOApp) {
        $acaoDoApp = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\cmd.exe" -Argument "/d /c `"$LancadorDoApp`""
        Register-ScheduledTask -TaskName $TaskDoApp -Action $acaoDoApp -Trigger $trigger -Settings $settings -User $Conta -Password $clara -RunLevel Highest -Force | Out-Null
    }
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    $clara = $null
}
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Host "A ponte do superusuario esta no ar (tarefa $TaskName, conta $Conta): atende a tela do sistema"
if (Valor 'TELEGRAM_TOKEN') {
    Write-Host 'e o Telegram.'
    if (-not (Valor 'OPERADOR_TELEGRAM_USUARIO')) {
        Write-Host 'Agora escreva qualquer coisa para o bot no Telegram: ele responde o seu numero de usuario.'
        Write-Host "Ponha esse numero em OPERADOR_TELEGRAM_USUARIO, em $Cred, e rode este instalador de novo."
    }
} else {
    Write-Host '(sem TELEGRAM_TOKEN: o Telegram fica desligado).'
}
if ($querOApp) {
    Stop-ScheduledTask -TaskName $TaskDoApp -ErrorAction SilentlyContinue | Out-Null
    Start-ScheduledTask -TaskName $TaskDoApp
    Write-Host "A porta do app do Claude esta no ar (tarefa $TaskDoApp). Ela exige o login da assinatura"
    Write-Host 'nesta conta: se nao aparecer no app, rode  claude auth login  e reinicie a tarefa.'
} else {
    Unregister-ScheduledTask -TaskName $TaskDoApp -Confirm:$false -ErrorAction SilentlyContinue
}
Write-Host ''
Write-Host 'Para provar neste servidor que a guarda e o relatorio funcionam com o Claude Code'
Write-Host 'instalado (nao gasta a API e nao toca no banco), rode:'
Write-Host ("  `"{0}`" operador\ensaio.py" -f $Python)
Write-Host ("Registro: " + (Join-Path $OperadorDir 'ponte.log'))
