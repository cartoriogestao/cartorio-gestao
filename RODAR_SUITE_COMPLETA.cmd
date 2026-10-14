@echo off
REM Suite inteira, inclusive os testes marcados como lentos.
setlocal
set ROOT=%~dp0
set PY=C:\ProgramData\CartorioGestao\runtime\Scripts\python.exe
cd /d "%ROOT%"
"%PY%" "tools\rodar_suite.py" --completa %*
set "CODIGO=%ERRORLEVEL%"
endlocal & exit /b %CODIGO%
