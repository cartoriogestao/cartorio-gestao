@echo off
rem Agente do malote (agente 13) - o malote do dia num clique so.
rem 1) leva a lista de fraudes mais nova de DOCUMENTOS_OFICIAL (fraudes_do_malote_AAAA-MM-DD.json)
rem    para a lista de fraudes do sistema, sem expediente e sem tarefa (ordem de 13/10/2026);
rem 2) cadastra o resto da pasta de entrada como expediente, em nome do oficial
rem    (settings.malote_cadastra_em_nome_de). Uma copia do banco so, antes de tudo.
rem A mesma pessoa do mesmo aviso nao entra duas vezes, e arquivo ja cadastrado nao repete.
chcp 65001 >nul
set PY=C:\ProgramData\CartorioGestao\runtime\Scripts\python.exe
set AQUI=%~dp0..
set DOC=%AQUI%\..\..\DOCUMENTOS_OFICIAL
set BANCO=C:\ProgramData\CartorioGestao\cartorio_gestao.sqlite3
set ARQ=
for /f "delims=" %%F in ('dir /b /o:n "%DOC%\fraudes_do_malote_2026-*.json" 2^>nul') do set ARQ=%%F
echo Copiando o banco antes de gravar. Leva cerca de 3 minutos, sem mostrar nada.
echo NAO feche esta janela e NAO abra o comando outra vez.
echo.
if defined ARQ (
  echo Lista de fraudes: %ARQ%
  "%PY%" "%AQUI%\malote_fraudes.py" --banco "%BANCO%" --carregar "%DOC%\%ARQ%" --aprovar todas --aplicar --pagina "%DOC%\fraudes_do_malote_aplicadas.html"
  if errorlevel 1 goto falhou
  set SEMCOPIA=--sem-copia
) else (
  echo Nenhuma lista de fraudes nova.
  set SEMCOPIA=
)
echo.
echo Cadastrando o resto da entrada como expediente...
"%PY%" "%AQUI%\malote_agente.py" --banco "%BANCO%" --confirmar %SEMCOPIA% --saida "%DOC%\malote_%date:~6,4%-%date:~3,2%-%date:~0,2%.html"
if errorlevel 1 goto falhou
echo.
echo Terminou. Pressione uma tecla para fechar.
pause >nul
exit /b 0
:falhou
echo.
echo PAROU COM ERRO - nada foi gravado depois do erro. Mostre esta janela ao Claude.
pause >nul
exit /b 1
