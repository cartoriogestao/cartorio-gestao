@echo off
REM ======================================================================
REM  Cartorio Gestao - SANDBOX DE DEMONSTRACAO (dados ficticios)
REM
REM  Liga uma instalacao isolada, so nesta maquina, em http://127.0.0.1:8899
REM  Nao instala nada no Windows, nao cria tarefa agendada, nao mexe em
REM  firewall e nao toca em instalacao real. Os dados ficam na pasta
REM  sandbox_dados, ao lado deste arquivo. Apagar a pasta apaga o sandbox.
REM
REM  Opcoes (repassadas ao tools\iniciar_sandbox.py):
REM    --porta 8900      outra porta
REM    --dados PASTA     outra pasta de dados (so de sandbox)
REM    --sem-navegador   nao abre o navegador
REM    --apagar          apaga a pasta do sandbox (pede confirmacao)
REM
REM  Qual Python: o da variavel CG_PYTHON, se houver; senao o .venv desta
REM  pasta; senao o "py -3" do Windows; senao o "python" do PATH.
REM ======================================================================
setlocal
cd /d "%~dp0"
set "PYEXE="
set "PYARGS="
if defined CG_PYTHON set "PYEXE=%CG_PYTHON%"
if not defined PYEXE if exist ".venv\Scripts\python.exe" set "PYEXE=%~dp0.venv\Scripts\python.exe"
if not defined PYEXE (
    where py >nul 2>nul && (set "PYEXE=py" & set "PYARGS=-3")
)
if not defined PYEXE (
    where python >nul 2>nul && set "PYEXE=python"
)
if not defined PYEXE (
    echo.
    echo Nao achei o Python nesta maquina.
    echo Instale o Python 3.11 ou mais novo ^(python.org^), marcando
    echo "Add python.exe to PATH", e depois rode, nesta pasta:
    echo     python -m pip install -r requirements.txt
    echo e abra este INICIAR_SANDBOX.cmd de novo.
    echo.
    pause
    exit /b 1
)
"%PYEXE%" %PYARGS% "tools\iniciar_sandbox.py" %*
set "CODIGO=%ERRORLEVEL%"
if "%CODIGO%"=="9009" (
    echo.
    echo O Windows abriu o atalho da Loja em vez do Python. Instale o Python 3.11+
    echo de python.org e rode este arquivo de novo.
)
if not "%CODIGO%"=="0" pause
endlocal & exit /b %CODIGO%
