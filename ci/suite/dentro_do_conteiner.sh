#!/bin/bash
# Roda DENTRO do contêiner, sem rede: sobe um PostgreSQL descartável e roda a suíte.
#
#   /codigo  o código do PR (somente leitura) — copiado para /tmp/trabalho
#   /saida   o relatório (suite.log, junit.xml, situacao.txt)
#
# O banco vive em /tmp (memória do contêiner) e morre com ele. Sem gravação
# síncrona: é descartável, e isso não muda o resultado dos testes.
set -u
PROCESSOS="${CG_SUITE_PROCESSOS:-12}"
SAIDA=/saida
mkdir -p "$SAIDA"

# Fora de /tmp: há varredor de teste que ignora todo caminho com «tmp» (e ignoraria
# o sistema inteiro). E um repositório git local, sem rede, para os testes que
# perguntam ao git o que é versionado.
cp -a /codigo "$HOME/trabalho"
cd "$HOME/trabalho" || exit 90
git init -q && git add -A && git -c user.name=suite -c user.email=suite@invalid commit -qm "PR em teste" || exit 94

initdb -D /tmp/pg -U cgtest -A trust -E UTF8 --locale=C.UTF-8 >/tmp/initdb.log 2>&1 || { cat /tmp/initdb.log; exit 91; }
pg_ctl -D /tmp/pg -w -l /tmp/pg.log -o "-p 55432 -c listen_addresses=127.0.0.1 -c unix_socket_directories=/tmp \
  -c max_connections=500 -c fsync=off -c synchronous_commit=off -c full_page_writes=off -c shared_buffers=1GB" start \
  >/dev/null || { cat /tmp/pg.log; exit 92; }
createdb -h 127.0.0.1 -p 55432 -U cgtest cg_teste || exit 93

export CG_TEST_BACKEND=pg
export CG_PG_DSN="host=127.0.0.1 port=55432 user=cgtest dbname=cg_teste"

inicio=$(date +%s)
# CG_SUITE_ALVO: só para investigar (a CI roda a suíte inteira).
# shellcheck disable=SC2086
python -m pytest ${CG_SUITE_ALVO:-tests} -n "$PROCESSOS" --dist loadfile -p no:cacheprovider -q -rfE \
  --junitxml="$SAIDA/junit.xml" >"$SAIDA/suite.log" 2>&1
rc=$?
echo "codigo=$rc segundos=$(( $(date +%s) - inicio )) $(tail -1 "$SAIDA/suite.log")" >"$SAIDA/situacao.txt"
cat "$SAIDA/situacao.txt"
exit $rc
