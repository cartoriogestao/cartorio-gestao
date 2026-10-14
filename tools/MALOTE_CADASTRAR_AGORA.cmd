@echo off
rem Agente do malote (agente 13) - cadastra o que esta em PARA CADASTRAR e na
rem pasta de entrada, em nome do oficial (jean). Tira copia do banco antes.
rem Ordem do oficial em 11/10/2026. Gera o relatorio em DOCUMENTOS_OFICIAL.
chcp 65001 >nul
set PY=C:\ProgramData\CartorioGestao\runtime\Scripts\python.exe
set AQUI=%~dp0..
echo Copiando o banco antes de gravar. Leva cerca de 3 minutos, sem mostrar nada.
echo NAO feche esta janela e NAO abra o comando outra vez.
echo.
"%PY%" "%AQUI%\malote_agente.py" --banco "C:\ProgramData\CartorioGestao\cartorio_gestao.sqlite3" --confirmar --em-nome-de jean --saida "%AQUI%\..\..\DOCUMENTOS_OFICIAL\malote_%date:~6,4%-%date:~3,2%-%date:~0,2%.html"
echo.
echo Terminou. Pressione uma tecla para fechar.
pause >nul
