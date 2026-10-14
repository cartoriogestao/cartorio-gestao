$ErrorActionPreference='SilentlyContinue'
$TaskName='CartorioGestaoServidor'
$InstallDir=Join-Path $env:ProgramFiles 'CartorioGestao'
$DataDir=Join-Path $env:ProgramData 'CartorioGestao'
$id=[Security.Principal.WindowsIdentity]::GetCurrent(); $p=New-Object Security.Principal.WindowsPrincipal($id)
if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Start-Process powershell.exe -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""; exit
}
Disable-ScheduledTask -TaskName $TaskName | Out-Null
Stop-ScheduledTask -TaskName $TaskName | Out-Null
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false | Out-Null
Get-NetFirewallRule -DisplayName 'Cartorio Gestao - HTTP' | Remove-NetFirewallRule
Get-NetFirewallRule -DisplayName 'Cartorio Gestao - Descoberta' | Remove-NetFirewallRule
Remove-Item 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\CartorioGestao' -Recurse -Force
Remove-Item (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\Cartorio Gestao') -Recurse -Force
Remove-Item (Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'Cartorio Gestao.lnk') -Force
$removeData = (Read-Host 'Deseja APAGAR tambem banco, documentos e backups? Digite APAGAR para confirmar') -eq 'APAGAR'
Remove-Item $InstallDir -Recurse -Force
if ($removeData) { Remove-Item $DataDir -Recurse -Force } else { Write-Host "Dados preservados em $DataDir" }
Write-Host 'Cartorio Gestao removido.'
