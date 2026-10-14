@echo off
setlocal
cd /d "%~dp0"
title Cartorio Gestao - Configurar Servidor
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0configurar_servidor.ps1"
echo.
pause
