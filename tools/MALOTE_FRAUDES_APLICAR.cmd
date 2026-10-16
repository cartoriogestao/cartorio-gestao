@echo off
rem Lista de atencao para fraudes - leva as propostas lidas do malote (13/10/2026)
rem para a lista do sistema, em nome do oficial. Tira copia do banco antes.
rem O arquivo de propostas e o que o oficial revisou em DOCUMENTOS_OFICIAL.
chcp 65001 >nul
set PY=C:\ProgramData\CartorioGestao\runtime\Scripts\python.exe
set AQUI=%~dp0..
echo Copiando o banco antes de gravar. Leva cerca de 3 minutos, sem mostrar nada.
echo NAO feche esta janela e NAO abra o comando outra vez.
echo.
"%PY%" "%AQUI%\malote_fraudes.py" --banco "C:\ProgramData\CartorioGestao\cartorio_gestao.sqlite3" --carregar "%AQUI%\..\..\DOCUMENTOS_OFICIAL\fraudes_do_malote_2026-10-13.json" --aprovar todas --aplicar --pagina "%AQUI%\..\..\DOCUMENTOS_OFICIAL\fraudes_do_malote_aplicadas.html"
echo.
echo Terminou. Pressione uma tecla para fechar.
pause >nul
