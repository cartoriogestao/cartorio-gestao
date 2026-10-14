param([string]$SourceRootOverride='')
$ErrorActionPreference = 'Stop'
$TaskName = 'CartorioGestaoServidor'
$RuleHttp = 'Cartorio Gestao - HTTP'
$RuleDiscovery = 'Cartorio Gestao - Descoberta'
$SourceRoot = if($SourceRootOverride){[IO.Path]::GetFullPath($SourceRootOverride.Trim([char]34).Trim().TrimEnd('\'))}else{(Resolve-Path (Join-Path $PSScriptRoot '..')).Path}
$InstallDir = Join-Path $env:ProgramFiles 'CartorioGestao'
$DataDir = Join-Path $env:ProgramData 'CartorioGestao'
$RuntimeDir = Join-Path $DataDir 'runtime'
$LogDir = Join-Path $DataDir 'logs'
$Log = Join-Path $LogDir 'instalacao.log'
$TempLog = Join-Path $env:TEMP 'CartorioGestao_instalacao.log'

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
function Log([string]$Text) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Text"
    try { Add-Content -Path $TempLog -Value $line -Encoding UTF8 } catch {}
    try { Add-Content -Path $Log -Value $line -Encoding UTF8 } catch {}
    Write-Host $Text
}
function Copy-Tree([string]$From,[string]$To) {
    New-Item -ItemType Directory -Force -Path $To | Out-Null
    & robocopy.exe $From $To /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XD .venv __pycache__ dist dist_unico build runtime updates /XF *.pyc *.zip | Out-Null
    $rc=$LASTEXITCODE
    if($rc -ge 8){ throw "Falha ao copiar arquivos do programa. Codigo robocopy: $rc" }
}
function Copy-DataTree([string]$From,[string]$To) {
    New-Item -ItemType Directory -Force -Path $To | Out-Null
    & robocopy.exe $From $To /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP /XD runtime updates /XF cartorio_gestao.sqlite3 cartorio_gestao.sqlite3-wal cartorio_gestao.sqlite3-shm | Out-Null
    $rc=$LASTEXITCODE
    if($rc -ge 8){ throw "Falha ao copiar dados antigos. Codigo robocopy: $rc" }
}
function Test-Python([string]$Exe,[string[]]$Prefix=@()) {
    if(-not $Exe){return $false}
    try {
        & $Exe @Prefix -c "import sys; assert sys.version_info >= (3,11)" 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}
function Find-Python {
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if($launcher){
        foreach($tag in @('-3.13','-3.12','-3.11')){
            if(Test-Python $launcher.Source @($tag)){ return @{Exe=$launcher.Source; Prefix=@($tag)} }
        }
    }
    $direct = @()
    foreach($v in @('314','313','312','311')){
        $direct += (Join-Path $env:ProgramFiles "Python$v\python.exe")
        $direct += (Join-Path $env:LOCALAPPDATA "Programs\Python\Python$v\python.exe")
    }
    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if($cmd){$direct += $cmd.Source}
    foreach($candidate in ($direct | Select-Object -Unique)){
        if((Test-Path $candidate) -and (Test-Python $candidate)){ return @{Exe=$candidate; Prefix=@()} }
    }
    return $null
}
function Create-Runtime([hashtable]$PythonInfo) {
    if(Test-Path $RuntimeDir){Remove-Item $RuntimeDir -Recurse -Force}
    Log ("Criando ambiente privado com " + $PythonInfo.Exe + ' ' + ($PythonInfo.Prefix -join ' '))
    & $PythonInfo.Exe @($PythonInfo.Prefix) -m venv $RuntimeDir
    if($LASTEXITCODE -ne 0){throw 'Falha ao criar o ambiente Python privado.'}
    $py = Join-Path $RuntimeDir 'Scripts\python.exe'
    if(-not (Test-Path $py)){throw 'O ambiente Python foi criado sem python.exe.'}
    return $py
}
function Ensure-Dependencies([string]$RuntimePython) {
    & $RuntimePython -c "import flask,waitress" 2>$null
    if($LASTEXITCODE -eq 0){Log 'Flask e Waitress ja estao disponiveis no ambiente privado.'; return}

    # Reaproveita pacotes de uma v3/v3.1 antiga se houver ambiente virtual compativel.
    $oldVenvCandidates = New-Object System.Collections.Generic.List[string]
    $oldVenvCandidates.Add((Join-Path $SourceRoot '.venv'))
    $oldVenvCandidates.Add('C:\CartorioGestao\.venv')
    foreach($base in @((Join-Path $env:USERPROFILE 'Downloads'),(Join-Path $env:USERPROFILE 'Desktop'))){
        if(Test-Path $base){
            Get-ChildItem $base -Directory -ErrorAction SilentlyContinue | Where-Object {$_.Name -like 'CartorioGestao*' -or $_.Name -like 'malote_digital*'} | ForEach-Object {
                $oldVenvCandidates.Add((Join-Path $_.FullName '.venv'))
            }
        }
    }
    foreach($oldVenv in ($oldVenvCandidates | Select-Object -Unique)){
        $oldPy=Join-Path $oldVenv 'Scripts\python.exe'
        $oldSite=Join-Path $oldVenv 'Lib\site-packages'
        if((Test-Path $oldPy) -and (Test-Path $oldSite)){
            $newVer=& $RuntimePython -c "import sys;print(str(sys.version_info[0])+'.'+str(sys.version_info[1]))" 2>$null
            $oldVer=& $oldPy -c "import sys;print(str(sys.version_info[0])+'.'+str(sys.version_info[1]))" 2>$null
            if($newVer -eq $oldVer){
                Log "Tentando reaproveitar bibliotecas da instalacao anterior: $oldVenv"
                & robocopy.exe $oldSite (Join-Path $RuntimeDir 'Lib\site-packages') /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
                & $RuntimePython -c "import flask,waitress" 2>$null
                if($LASTEXITCODE -eq 0){Log 'Bibliotecas reaproveitadas com sucesso.'; return}
            }
        }
    }

    Log 'Instalando Flask e Waitress. Esta etapa pode usar a Internet.'
    & $RuntimePython -m pip install --disable-pip-version-check --no-input -r (Join-Path $InstallDir 'requirements.txt')
    if($LASTEXITCODE -ne 0){throw 'Nao foi possivel instalar Flask/Waitress. Verifique a conexao com a Internet, proxy ou antivirus.'}
    & $RuntimePython -c "import flask,waitress"
    if($LASTEXITCODE -ne 0){throw 'Flask/Waitress foram instalados, mas o teste de importacao falhou.'}
}
function Configure-Firewall([int]$HttpPort,[int]$DiscoveryPort) {
    Log "Configurando Firewall do Windows: TCP $HttpPort e UDP $DiscoveryPort para a rede local."
    try {
        if(Get-Command New-NetFirewallRule -ErrorAction SilentlyContinue){
            Get-NetFirewallRule -DisplayName $RuleHttp -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
            Get-NetFirewallRule -DisplayName $RuleDiscovery -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
            New-NetFirewallRule -DisplayName $RuleHttp -Direction Inbound -Action Allow -Protocol TCP -LocalPort $HttpPort -RemoteAddress LocalSubnet -Profile Any | Out-Null
            New-NetFirewallRule -DisplayName $RuleDiscovery -Direction Inbound -Action Allow -Protocol UDP -LocalPort $DiscoveryPort -RemoteAddress LocalSubnet -Profile Any | Out-Null
            return
        }
    } catch { Log ('Aviso: cmdlets de firewall falharam; usando netsh. ' + $_.Exception.Message) }
    & netsh.exe advfirewall firewall delete rule name="$RuleHttp" | Out-Null
    & netsh.exe advfirewall firewall delete rule name="$RuleDiscovery" | Out-Null
    & netsh.exe advfirewall firewall add rule name="$RuleHttp" dir=in action=allow protocol=TCP localport=$HttpPort remoteip=localsubnet profile=any | Out-Null
    if($LASTEXITCODE -ne 0){throw 'Falha ao criar regra TCP no Firewall do Windows.'}
    & netsh.exe advfirewall firewall add rule name="$RuleDiscovery" dir=in action=allow protocol=UDP localport=$DiscoveryPort remoteip=localsubnet profile=any | Out-Null
    if($LASTEXITCODE -ne 0){throw 'Falha ao criar regra UDP no Firewall do Windows.'}
}
function Stop-OldServer {
    try { Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Out-Null } catch {}
    try { Disable-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Out-Null } catch {}
    if(Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue){
        Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
            try {
                $proc=Get-Process -Id $_.OwningProcess -ErrorAction Stop
                if($proc.Path -like '*python*' -or $proc.ProcessName -like 'python*'){
                    Log "Encerrando servidor anterior na porta 8765 (PID $($_.OwningProcess))."
                    Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
                }
            } catch {}
        }
    }
}
function Register-ServerTask([string]$ServiceCmd) {
    Log 'Configurando inicializacao automatica com o Windows.'
    try {
        $action=New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\cmd.exe" -Argument "/d /c `"$ServiceCmd`""
        $trigger=New-ScheduledTaskTrigger -AtStartup
        $principal=New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
        # -Priority 3 = ACIMA DO NORMAL, e este numero foi MEDIDO em
        # 24/09/2026, nao consultado: tarefa registrada com 3 produz processo
        # AboveNormal; com 4 e 5, Normal; com 7, BelowNormal.
        #
        # E 7 ERA O QUE ESTAVA AQUI — nao escrito, mas herdado: sem -Priority,
        # o padrao do Agendador de Tarefas do Windows e 7. O servidor do
        # balcao nascia ABAIXO DO NORMAL, atras de qualquer navegador ou
        # backup, e a classe se herda para o cmd, o python e as doze linhas do
        # waitress. Medido no mesmo dia, com a maquina ocupada, o pior
        # atendimento passava de 10 segundos; com a prioridade certa, 0,23 s.
        #
        # O app tambem se reserva sozinho no arranque (`recursos_da_maquina`,
        # chamado de `app.main`), e DE PROPOSITO os dois dizem a mesma coisa:
        # esta linha conserta instalacao nova, e aquela chamada conserta as
        # maquinas onde a tarefa ja existe registrada com o padrao antigo.
        $settings=New-ScheduledTaskSettingsSet -Priority 3 -StartWhenAvailable -RestartCount 99 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        $task=New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings
        Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
        Enable-ScheduledTask -TaskName $TaskName | Out-Null
        return
    } catch { Log ('Aviso: modulo ScheduledTasks falhou; usando schtasks.exe. ' + $_.Exception.Message) }
    # ESTE CAMINHO DE SOCORRO NASCE EM PRIORIDADE 7, e nao ha como evitar:
    # `schtasks.exe /Create` nao tem opcao de prioridade — so importando XML,
    # que e justamente o que este caminho existe para nao precisar fazer.
    # Quem conserta e o proprio servidor, que se reserva no arranque
    # (`recursos_da_maquina`, chamado de `app.main`). Fica escrito aqui para
    # ninguem descobrir sozinho, daqui a um ano, que o socorro vinha manco.
    & schtasks.exe /Delete /TN $TaskName /F 2>$null | Out-Null
    $tr = "`"$env:SystemRoot\System32\cmd.exe`" /d /c `"$ServiceCmd`""
    & schtasks.exe /Create /TN $TaskName /SC ONSTART /RU SYSTEM /RL HIGHEST /TR $tr /F | Out-Null
    if($LASTEXITCODE -ne 0){throw 'Nao foi possivel criar a tarefa de inicializacao automatica.'}
}
function Start-ServerTask {
    try { Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop; return } catch {}
    & schtasks.exe /Run /TN $TaskName | Out-Null
}
function Test-Health([int]$Port,[int]$Seconds=30) {
    for($i=0;$i -lt $Seconds;$i++){
        Start-Sleep -Seconds 1
        try {
            $r=Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/saude" -TimeoutSec 2
            if($r.StatusCode -eq 200){return $true}
        } catch {}
    }
    return $false
}
function Create-Shortcut([string]$Path,[string]$Target,[string]$Arguments,[string]$WorkDir,[string]$Icon='') {
    $shell=New-Object -ComObject WScript.Shell
    $lnk=$shell.CreateShortcut($Path)
    $lnk.TargetPath=$Target
    $lnk.Arguments=$Arguments
    $lnk.WorkingDirectory=$WorkDir
    if($Icon){$lnk.IconLocation=$Icon}
    $lnk.Save()
}

try {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    if(-not (Test-Admin)){throw 'O instalador nao esta com permissao de Administrador. Feche e execute INSTALAR_SERVIDOR.cmd novamente.'}
    Log 'Iniciando instalacao do Cartorio Gestao 3.2.1.'
    Log "Origem: $SourceRoot"
    Log "Programa: $InstallDir"
    Log "Dados: $DataDir"

    foreach($required in @('app.py','database.py','requirements.txt','templates\login.html','installer\client\localizar_servidor.ps1')){
        if(-not (Test-Path (Join-Path $SourceRoot $required))){throw "Pacote incompleto: arquivo ausente $required. Extraia todo o ZIP antes de instalar."}
    }

    Stop-OldServer
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    if($SourceRoot.TrimEnd('\') -ne $InstallDir.TrimEnd('\')){Copy-Tree $SourceRoot $InstallDir}

    $runtimePython=Join-Path $RuntimeDir 'Scripts\python.exe'
    $runtimeOk=$false
    if(Test-Path $runtimePython){
        & $runtimePython -c "import sys,flask,waitress; assert sys.version_info >= (3,11)" 2>$null
        $runtimeOk=($LASTEXITCODE -eq 0)
        if($runtimeOk){Log 'Ambiente Python privado existente esta valido.'}
    }
    if(-not $runtimeOk){
        $pyInfo=Find-Python
        if(-not $pyInfo){
            $winget=Get-Command winget.exe -ErrorAction SilentlyContinue
            if($winget){
                Log 'Python 3.11+ nao encontrado. Tentando instalar Python 3.12 automaticamente com winget.'
                & $winget.Source install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
                if($LASTEXITCODE -ne 0){Log "winget terminou com codigo $LASTEXITCODE; procurando Python novamente."}
                Start-Sleep -Seconds 2
                $pyInfo=Find-Python
            }
        }
        if(-not $pyInfo){throw 'Python 3.11 ou superior nao foi encontrado. Instale Python 3.11+ marcando Add Python to PATH e execute este instalador novamente.'}
        $runtimePython=Create-Runtime $pyInfo
        Ensure-Dependencies $runtimePython
    }

    $OldData=Join-Path $env:APPDATA 'CartorioGestao'
    $oldDb=Join-Path $OldData 'cartorio_gestao.sqlite3'
    $newDb=Join-Path $DataDir 'cartorio_gestao.sqlite3'
    $env:CARTORIO_GESTAO_DATA=$DataDir
    if((Test-Path $oldDb) -and -not (Test-Path $newDb)){
        Log "Migrando dados da versao anterior: $OldData"
        Copy-DataTree $OldData $DataDir
        & $runtimePython -c "import sqlite3,sys; a=sqlite3.connect(sys.argv[1]); b=sqlite3.connect(sys.argv[2]); a.backup(b); b.close(); a.close()" $oldDb $newDb
        if($LASTEXITCODE -ne 0){throw 'Falha ao migrar o banco SQLite anterior.'}
    }
    if((Test-Path $oldDb) -and (Test-Path $newDb)){
        & $runtimePython (Join-Path $InstallDir 'admin_cli.py') migrate-data-paths $OldData $DataDir | Out-Null
    }

    & $runtimePython (Join-Path $InstallDir 'admin_cli.py') force-network | Out-Null
    if($LASTEXITCODE -ne 0){throw 'Falha ao preparar configuracao de rede.'}
    $networkJson=& $runtimePython (Join-Path $InstallDir 'admin_cli.py') network-config
    $network=$networkJson | ConvertFrom-Json
    $HttpPort=[int]$network.port
    $DiscoveryPort=[int]$network.discovery_port
    Configure-Firewall $HttpPort $DiscoveryPort

    $ServiceCmd=Join-Path $DataDir 'iniciar_servidor_servico.cmd'
    @(
        '@echo off',
        "set `"CARTORIO_GESTAO_DATA=$DataDir`"",
        "cd /d `"$InstallDir`"",
        "`"$runtimePython`" `"$(Join-Path $InstallDir 'app.py')`" --service >> `"$(Join-Path $LogDir 'servidor.log')`" 2>&1"
    ) | Set-Content -Path $ServiceCmd -Encoding ASCII
    Register-ServerTask $ServiceCmd

    $startMenu=Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\Cartorio Gestao'
    New-Item -ItemType Directory -Force -Path $startMenu | Out-Null
    $psExe="$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
    $locator=Join-Path $InstallDir 'installer\client\localizar_servidor.ps1'
    try {
        foreach($shortcutPath in @((Join-Path $startMenu 'Cartorio Gestao.lnk'),(Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'Cartorio Gestao.lnk'))){
            Create-Shortcut $shortcutPath $psExe "-NoProfile -ExecutionPolicy Bypass -File `"$locator`"" $InstallDir "$env:SystemRoot\System32\shell32.dll,14"
        }
        Create-Shortcut (Join-Path $startMenu 'Diagnostico de Rede.lnk') $psExe "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $InstallDir 'installer\diagnostico_servidor.ps1')`"" $InstallDir
        Create-Shortcut (Join-Path $startMenu 'Reparar acesso de rede.lnk') $psExe "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $InstallDir 'installer\reparar_rede.ps1')`"" $InstallDir
    } catch { Log ('Aviso: nao foi possivel criar algum atalho. ' + $_.Exception.Message) }

    $uninstallKey='HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\CartorioGestao'
    New-Item -Path $uninstallKey -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name DisplayName -Value 'Cartorio Gestao' -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name DisplayVersion -Value '3.2.1' -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name Publisher -Value 'Sistema interno da serventia' -PropertyType String -Force | Out-Null
    $uninstallCmd="powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $InstallDir 'installer\desinstalar_servidor.ps1')`""
    New-ItemProperty -Path $uninstallKey -Name UninstallString -Value $uninstallCmd -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name InstallLocation -Value $InstallDir -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name NoModify -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name NoRepair -Value 0 -PropertyType DWord -Force | Out-Null

    $installInfo=@{version='3.2.1';install_dir=$InstallDir;data_dir=$DataDir;task_name=$TaskName;installed_at=(Get-Date).ToString('s')} | ConvertTo-Json
    Set-Content -Path (Join-Path $DataDir 'install.json') -Value $installInfo -Encoding UTF8

    Start-ServerTask
    Log 'Aguardando o servidor responder localmente.'
    $ok=Test-Health $HttpPort 35
    if(-not $ok){
        Log 'A tarefa automatica ainda nao respondeu; tentando iniciar o servidor diretamente uma vez.'
        Start-Process -FilePath "$env:SystemRoot\System32\cmd.exe" -ArgumentList @('/d','/c',"`"$ServiceCmd`"") -WindowStyle Hidden
        $ok=Test-Health $HttpPort 20
    }
    if(-not $ok){throw "Arquivos instalados, mas o servidor nao respondeu na porta $HttpPort. Verifique $LogDir\servidor.log e execute DIAGNOSTICAR_INSTALACAO.cmd."}

    Log 'Instalacao concluida com sucesso.'
    Write-Host ''
    Write-Host 'Enderecos para acesso na rede:' -ForegroundColor Green
    if(Get-Command Get-NetIPAddress -ErrorAction SilentlyContinue){
        Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object {$_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*'} | ForEach-Object {Write-Host "  http://$($_.IPAddress):$HttpPort"}
    }
    Write-Host ''
    Write-Host 'Nos outros computadores, instale apenas o pacote Acesso Cliente.'
    Start-Process "http://127.0.0.1:$HttpPort"
    exit 0
} catch {
    try {New-Item -ItemType Directory -Force -Path $LogDir | Out-Null}catch{}
    Log ('ERRO: ' + $_.Exception.Message)
    Write-Host ''
    Write-Host 'A INSTALACAO NAO FOI CONCLUIDA.' -ForegroundColor Red
    Write-Host ('Motivo: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host ''
    Write-Host ('Log: ' + $Log)
    Write-Host ('Log alternativo: ' + $TempLog)
    exit 1
}
