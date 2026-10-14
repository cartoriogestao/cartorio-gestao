$StateDir=Join-Path $env:LOCALAPPDATA 'CartorioGestaoCliente'
Write-Host '=== Cartorio Gestao - Diagnostico do Cliente ===' -ForegroundColor Cyan
Write-Host "Computador: $env:COMPUTERNAME"
Write-Host 'IPv4 ativos:'
Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object {$_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*'} | ForEach-Object { Write-Host "  $($_.IPAddress)" }
Write-Host 'Perfil das redes:'
Get-NetConnectionProfile -ErrorAction SilentlyContinue | Select-Object Name,InterfaceAlias,NetworkCategory | Format-Table -AutoSize
$locator=Join-Path $PSScriptRoot 'localizar_servidor.ps1'
Write-Host 'Testando descoberta automatica...'
& $locator -NoOpen
Write-Host "Log do localizador: $(Join-Path $StateDir 'localizador.log')"
Write-Host 'Se a descoberta falhar, verifique se ambos estao na mesma rede/VLAN e se nao ha isolamento de clientes.'
Read-Host 'Pressione ENTER para fechar'
