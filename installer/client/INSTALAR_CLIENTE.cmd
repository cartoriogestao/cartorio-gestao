@echo off
setlocal
cd /d "%~dp0"
title Cartorio Gestao - Instalacao do Acesso Cliente
echo.
echo Instalando o acesso ao Cartorio Gestao neste computador...
echo.
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS%" (
  echo ERRO: Windows PowerShell nao encontrado.
  pause
  exit /b 1
)
"%PS%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar_cliente.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo O acesso cliente nao foi instalado corretamente.
echo Se o servidor nao for localizado automaticamente, execute CONFIGURAR_SERVIDOR.cmd.
echo.
pause
exit /b %RC%
