param([string]$SourceRootOverride='')
$ErrorActionPreference='SilentlyContinue'
$SourceRoot = if($SourceRootOverride){[IO.Path]::GetFullPath($SourceRootOverride)}else{(Resolve-Path (Join-Path $PSScriptRoot '..')).Path}
$DataDir = Join-Path $env:ProgramData 'CartorioGestao'
$Out = Join-Path $env:TEMP 'CartorioGestao_diagnostico_instalacao.txt'
$lines = New-Object System.Collections.Generic.List[string]
function Add-Line([string]$s){$lines.Add($s); Write-Host $s}
function Is-Admin {
  $id=[Security.Principal.WindowsIdentity]::GetCurrent()
  $p=New-Object Security.Principal.WindowsPrincipal($id)
  return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
Add-Line 'CARTORIO GESTAO - DIAGNOSTICO DE INSTALACAO'
Add-Line ('Data: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Add-Line ('Windows: ' + [Environment]::OSVersion.VersionString)
Add-Line ('Arquitetura SO: ' + [Environment]::Is64BitOperatingSystem)
Add-Line ('PowerShell: ' + $PSVersionTable.PSVersion.ToString())
Add-Line ('Administrador: ' + (Is-Admin))
Add-Line ('Pasta do pacote: ' + $SourceRoot)
Add-Line ('ProgramFiles: ' + $env:ProgramFiles)
Add-Line ('ProgramData: ' + $env:ProgramData)
Add-Line ('TEMP: ' + $env:TEMP)
Add-Line ''
foreach($f in @('app.py','database.py','requirements.txt','installer\instalar_servidor.ps1','templates\login.html')){
  Add-Line ("Arquivo $f : " + (Test-Path (Join-Path $SourceRoot $f)))
}
Add-Line ''
$py = Get-Command py.exe -ErrorAction SilentlyContinue
$python = Get-Command python.exe -ErrorAction SilentlyContinue
$winget = Get-Command winget.exe -ErrorAction SilentlyContinue
Add-Line ('py.exe: ' + $(if($py){$py.Source}else{'nao encontrado'}))
if($py){
  foreach($tag in @('-3.13','-3.12','-3.11')){
    $v=& $py.Source $tag -c "import sys;print(sys.version)" 2>$null
    if($LASTEXITCODE -eq 0){Add-Line ("  $tag -> $v")}
  }
}
Add-Line ('python.exe: ' + $(if($python){$python.Source}else{'nao encontrado'}))
if($python){$v=& $python.Source -c "import sys;print(sys.version)" 2>$null; Add-Line ('  versao -> ' + $v)}
Add-Line ('winget.exe: ' + $(if($winget){$winget.Source}else{'nao encontrado'}))
Add-Line ''
foreach($port in @(8765,8766)){
  $listeners=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  if($port -eq 8766){
    $udp=Get-NetUDPEndpoint -LocalPort $port -ErrorAction SilentlyContinue
    Add-Line ("UDP $port em uso: " + [bool]$udp)
  } else { Add-Line ("TCP $port em uso: " + [bool]$listeners) }
}
Add-Line ''
$installLog=Join-Path $DataDir 'logs\instalacao.log'
if(Test-Path $installLog){
  Add-Line ('Ultimas linhas do log: ' + $installLog)
  Get-Content $installLog -Tail 60 | ForEach-Object {Add-Line $_}
}else{Add-Line 'Ainda nao existe log em ProgramData.'}
$lines | Set-Content -Path $Out -Encoding UTF8
Add-Line ''
Add-Line ('Diagnostico salvo em: ' + $Out)
