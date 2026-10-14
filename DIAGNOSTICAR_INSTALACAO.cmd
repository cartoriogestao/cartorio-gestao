@echo off
setlocal
cd /d "%~dp0"
title Cartorio Gestao - Diagnostico da Instalacao
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS%" (
  echo Windows PowerShell nao encontrado.
  pause
  exit /b 1
)
"%PS%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\diagnostico_instalacao.ps1" -SourceRootOverride "%~dp0"
echo.
pause
