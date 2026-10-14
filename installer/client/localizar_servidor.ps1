param([switch]$NoOpen,[int]$DiscoveryPort=8766)
$ErrorActionPreference='SilentlyContinue'
Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
$StateDir=Join-Path $env:LOCALAPPDATA 'CartorioGestaoCliente'
$StateFile=Join-Path $StateDir 'servidor.txt'
$LogFile=Join-Path $StateDir 'localizador.log'
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
function Log([string]$Text){Add-Content -Path $LogFile -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Text" -Encoding UTF8}
function Test-Server([string]$Url){
  if(-not $Url){return $false}
  try{
    $req=[System.Net.WebRequest]::Create(($Url.TrimEnd('/') + '/saude'))
    $req.Timeout=1500
    $resp=$req.GetResponse(); $status=[int]$resp.StatusCode; $resp.Close()
    return ($status -eq 200)
  }catch{return $false}
}
Log 'Iniciando localizacao do servidor.'
$url=''
if(Test-Path $StateFile){
  $saved=(Get-Content $StateFile -Raw).Trim()
  if(Test-Server $saved){$url=$saved;Log "Servidor salvo ainda valido: $url"}
}
if(-not $url){
  for($attempt=1;$attempt -le 3 -and -not $url;$attempt++){
    $udp=New-Object System.Net.Sockets.UdpClient
    $udp.EnableBroadcast=$true
    $udp.Client.ReceiveTimeout=1400
    $bytes=[Text.Encoding]::UTF8.GetBytes('CARTORIO_GESTAO_DISCOVER_V1')
    $endpoint=New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Broadcast,$DiscoveryPort)
    try{[void]$udp.Send($bytes,$bytes.Length,$endpoint);Log "Broadcast de descoberta $attempt enviado na UDP $DiscoveryPort."}catch{}
    $remote=New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Any,0)
    try{
      $reply=$udp.Receive([ref]$remote)
      $data=[Text.Encoding]::UTF8.GetString($reply) | ConvertFrom-Json
      if($data.product -eq 'CartorioGestao' -and (Test-Server ([string]$data.url))){$url=[string]$data.url;Log "Servidor descoberto: $url"}
    }catch{}
    $udp.Close()
  }
}
# Fallback: testa vizinhos ja conhecidos pelo Windows na porta padrao.
if(-not $url){
  try{
    $neighbors=Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object {$_.IPAddress -match '^\d+\.\d+\.\d+\.\d+$' -and $_.IPAddress -notlike '224.*' -and $_.IPAddress -notlike '239.*'} | Select-Object -ExpandProperty IPAddress -Unique
    foreach($ip in $neighbors){
      $candidate="http://$ip`:8765"
      if(Test-Server $candidate){$url=$candidate;Log "Servidor encontrado por vizinhanca IP: $url";break}
    }
  }catch{}
}
if($url){
  Set-Content -Path $StateFile -Value $url -Encoding ASCII
  Write-Host "Servidor encontrado: $url" -ForegroundColor Green
  if(-not $NoOpen){Start-Process $url}
  $url
  exit 0
}
Log 'Servidor nao localizado.'
Write-Host 'O servidor Cartorio Gestao nao foi localizado automaticamente.' -ForegroundColor Red
Write-Host 'Confirme se o servidor esta ligado e se este computador esta na mesma rede local.'
Write-Host "Log: $LogFile"
if(-not $NoOpen){[System.Windows.Forms.MessageBox]::Show("Servidor Cartorio Gestao nao encontrado. Verifique a rede ou execute o Diagnostico do Acesso.`n`nLog: $LogFile",'Cartorio Gestao') | Out-Null}
exit 1
