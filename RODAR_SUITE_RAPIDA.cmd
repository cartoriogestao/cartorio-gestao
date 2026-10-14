@echo off
REM Gate rapido da suite pytest - exclui testes marcados como lento.
REM NAO roda a suite completa. Use sem -m para a suite inteira.
setlocal
set ROOT=%~dp0
set PY=C:\ProgramData\CartorioGestao\runtime\Scripts\python.exe
cd /d "%ROOT%"
REM O executor escolhe metade dos processadores, no maximo seis; para medir
REM outro valor, defina CARTORIO_TEST_WORKERS. A trava do conftest recusa
REM outra suite na mesma arvore.
"%PY%" "tools\rodar_suite.py" --rapida %*
set "CODIGO=%ERRORLEVEL%"
endlocal & exit /b %CODIGO%
