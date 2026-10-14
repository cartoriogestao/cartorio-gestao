$ErrorActionPreference='Stop'
$TaskName='CartorioGestaoServidor'
$InstallDir=Join-Path $env:ProgramFiles 'CartorioGestao'
$DataDir=Join-Path $env:ProgramData 'CartorioGestao'
$RuntimePython=Join-Path $DataDir 'runtime\Scripts\python.exe'
function IsAdmin{$id=[Security.Principal.WindowsIdentity]::GetCurrent();$p=New-Object Security.Principal.WindowsPrincipal($id);$p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)}
if(-not (IsAdmin)){Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"";exit}
if(-not (Test-Path $RuntimePython)){throw 'Runtime do Cartorio Gestao nao encontrado. Reexecute o instalador do servidor.'}
$env:CARTORIO_GESTAO_DATA=$DataDir
& $RuntimePython (Join-Path $InstallDir 'admin_cli.py') force-network | Out-Null
$n=(& $RuntimePython (Join-Path $InstallDir 'admin_cli.py') network-config) | ConvertFrom-Json
$http=[int]$n.port;$udp=8766
Get-NetFirewallRule -DisplayName 'Cartorio Gestao - HTTP' -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
Get-NetFirewallRule -DisplayName 'Cartorio Gestao - Descoberta' -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName 'Cartorio Gestao - HTTP' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $http -RemoteAddress LocalSubnet -Profile Any | Out-Null
New-NetFirewallRule -DisplayName 'Cartorio Gestao - Descoberta' -Direction Inbound -Action Allow -Protocol UDP -LocalPort $udp -RemoteAddress LocalSubnet -Profile Any | Out-Null
try{Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue | Out-Null}catch{}
Start-Sleep -Seconds 1
Start-ScheduledTask -TaskName $TaskName
Write-Host "Rede reparada. HTTP TCP $http e descoberta UDP $udp liberados para a sub-rede local." -ForegroundColor Green
Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object {$_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*'} | ForEach-Object {Write-Host "http://$($_.IPAddress):$http"}
Read-Host 'Pressione ENTER para fechar'
