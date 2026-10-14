$TaskName='CartorioGestaoServidor'
$InstallDir=Join-Path $env:ProgramFiles 'CartorioGestao'
$DataDir=Join-Path $env:ProgramData 'CartorioGestao'
$Runtime=Join-Path $DataDir 'runtime\Scripts\python.exe'
$http=8765;$udp=8766
if(Test-Path $Runtime){
  try{$env:CARTORIO_GESTAO_DATA=$DataDir;$n=(& $Runtime (Join-Path $InstallDir 'admin_cli.py') network-config)|ConvertFrom-Json;$http=[int]$n.port;$udp=[int]$n.discovery_port}catch{}
}
Write-Host '=== Cartorio Gestao - Diagnostico de Rede ===' -ForegroundColor Cyan
Write-Host "Computador: $env:COMPUTERNAME"
try { Write-Host "Servidor automatico: $((Get-ScheduledTask -TaskName $TaskName).State)" } catch { Write-Host 'Servidor automatico: NAO ENCONTRADO' -ForegroundColor Red }
Write-Host 'IPv4 ativos:'
Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object {$_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*'} | ForEach-Object { Write-Host "  $($_.IPAddress) -> http://$($_.IPAddress):$http" }
Write-Host "Porta HTTP configurada: TCP $http"
Write-Host "Porta de descoberta configurada: UDP $udp (compatibilidade tambem usa 8766)"
Write-Host 'Escuta TCP:'
Get-NetTCPConnection -State Listen -LocalPort $http -ErrorAction SilentlyContinue | Format-Table -AutoSize
Write-Host 'Regras de firewall:'
Get-NetFirewallRule -DisplayName 'Cartorio Gestao*' -ErrorAction SilentlyContinue | Select-Object DisplayName,Enabled,Profile,Action | Format-Table -AutoSize
try {
  $r=Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$http/saude" -TimeoutSec 3
  Write-Host "Saude local: OK ($($r.StatusCode))" -ForegroundColor Green
} catch { Write-Host "Saude local: FALHOU - $($_.Exception.Message)" -ForegroundColor Red }
Write-Host "Programa: $InstallDir"
Write-Host "Dados: $DataDir"
Read-Host 'Pressione ENTER para fechar'
