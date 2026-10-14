$ErrorActionPreference='Stop'
$Dest=Join-Path $env:LOCALAPPDATA 'CartorioGestaoCliente'
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
foreach($f in @('localizar_servidor.ps1','diagnostico_cliente.ps1','configurar_servidor.ps1')){
  Copy-Item (Join-Path $PSScriptRoot $f) (Join-Path $Dest $f) -Force
}
$shell=New-Object -ComObject WScript.Shell
$start=Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Cartorio Gestao'
New-Item -ItemType Directory -Force -Path $start | Out-Null
$ps="$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
foreach($path in @((Join-Path $start 'Cartorio Gestao.lnk'),(Join-Path ([Environment]::GetFolderPath('Desktop')) 'Cartorio Gestao.lnk'))){
  $lnk=$shell.CreateShortcut($path)
  $lnk.TargetPath=$ps
  $lnk.Arguments="-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $Dest 'localizar_servidor.ps1')`""
  $lnk.IconLocation="$env:SystemRoot\System32\shell32.dll,14"
  $lnk.WorkingDirectory=$Dest
  $lnk.Save()
}
$diag=$shell.CreateShortcut((Join-Path $start 'Diagnostico do Acesso.lnk'))
$diag.TargetPath=$ps
$diag.Arguments="-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $Dest 'diagnostico_cliente.ps1')`""
$diag.WorkingDirectory=$Dest
$diag.Save()
$config=$shell.CreateShortcut((Join-Path $start 'Configurar Servidor.lnk'))
$config.TargetPath=$ps
$config.Arguments="-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $Dest 'configurar_servidor.ps1')`""
$config.WorkingDirectory=$Dest
$config.Save()
Write-Host 'Acesso instalado. O atalho Cartorio Gestao vai localizar o servidor automaticamente.' -ForegroundColor Green
Write-Host 'Se a descoberta falhar, use Configurar Servidor no Menu Iniciar.'
& (Join-Path $Dest 'localizar_servidor.ps1')
exit 0
