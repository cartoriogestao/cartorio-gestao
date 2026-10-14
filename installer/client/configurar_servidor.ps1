param([string]$Endereco='')
$ErrorActionPreference='Stop'
$StateDir=Join-Path $env:LOCALAPPDATA 'CartorioGestaoCliente'
$StateFile=Join-Path $StateDir 'servidor.txt'
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
if(-not $Endereco){
  Write-Host 'Informe o IP ou nome do computador servidor.' -ForegroundColor Cyan
  Write-Host 'Exemplos: 192.168.1.10   ou   SERVIDOR-CARTORIO'
  $Endereco=Read-Host 'Servidor'
}
$Endereco=($Endereco -as [string]).Trim()
if(-not $Endereco){Write-Host 'Nenhum endereco informado.' -ForegroundColor Red; exit 1}
if($Endereco -notmatch '^https?://'){$Endereco='http://' + $Endereco}
if($Endereco -notmatch ':\d+($|/)'){$Endereco=$Endereco.TrimEnd('/') + ':8765'}
$Endereco=$Endereco.TrimEnd('/')
try{
  $r=Invoke-WebRequest -UseBasicParsing -Uri ($Endereco + '/saude') -TimeoutSec 4
  if($r.StatusCode -ne 200){throw 'Resposta inesperada'}
}catch{
  Write-Host "Nao foi possivel acessar $Endereco" -ForegroundColor Red
  Write-Host 'Confirme se o servidor esta ligado, se a porta 8765 esta liberada e se as maquinas estao na mesma rede.'
  exit 2
}
Set-Content -Path $StateFile -Value $Endereco -Encoding ASCII
Write-Host "Servidor salvo: $Endereco" -ForegroundColor Green
Start-Process $Endereco
exit 0
