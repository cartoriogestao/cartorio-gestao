@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Cartorio Gestao - Instalador do Servidor

set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS%" (
  echo.
  echo ERRO: Windows PowerShell nao foi encontrado neste computador.
  echo O instalador precisa do Windows PowerShell 5.1 ou superior.
  echo.
  pause
  exit /b 10
)

if /I "%~1"=="--elevated" goto :RUN

"%PS%" -NoProfile -ExecutionPolicy Bypass -Command "$p=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent()); if($p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){exit 0}else{exit 1}" >nul 2>&1
if not errorlevel 1 goto :RUN

echo.
echo Cartorio Gestao 3.2.1
echo O Windows vai pedir permissao de Administrador para instalar o servidor.
echo Confirme SIM na janela de Controle de Conta de Usuario.
echo.

"%PS%" -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -ArgumentList '--elevated' -WorkingDirectory '%~dp0.' -Verb RunAs"
set "ELEV_RC=%ERRORLEVEL%"
if not "%ELEV_RC%"=="0" (
  echo.
  echo Nao foi possivel solicitar a elevacao automaticamente.
  echo Codigo: %ELEV_RC%
  echo.
  echo Clique com o botao direito em INSTALAR_SERVIDOR.cmd e escolha
  echo "Executar como administrador".
  echo.
  pause
  exit /b 11
)
echo.
echo Janela de instalacao aberta com permissao de Administrador.
echo Acompanhe a instalacao na outra janela.
echo.
pause
exit /b 0

:RUN
echo.
echo ============================================================
echo          CARTORIO GESTAO - INSTALACAO DO SERVIDOR
echo ============================================================
echo.
echo Esta janela permanecera aberta ate o fim da instalacao.
echo Se houver erro, ele sera mostrado aqui e gravado em log.
echo.

"%PS%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\instalar_servidor.ps1" -SourceRootOverride "%~dp0." 2>"%~dp0ERRO_POWERSHELL.txt"
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo Instalacao finalizada com sucesso.
  echo Voce pode fechar esta janela.
) else (
  echo A instalacao NAO foi concluida. Codigo de erro: %RC%
  echo.
  echo Execute DIAGNOSTICAR_INSTALACAO.cmd se precisar gerar um diagnostico.
  echo O log principal fica em:
  echo C:\ProgramData\CartorioGestao\logs\instalacao.log
)
echo.
pause
exit /b %RC%
